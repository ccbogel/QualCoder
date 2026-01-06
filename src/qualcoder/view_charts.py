# -*- coding: utf-8 -*-

"""
This file is part of QualCoder.

QualCoder is free software: you can redistribute it and/or modify it under the
terms of the GNU Lesser General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version.

QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with QualCoder.
If not, see <https://www.gnu.org/licenses/>.

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
https://qualcoder-org.github.io/
"""

from collections import Counter
from copy import copy, deepcopy
import logging
import os
import pandas as pd
import plotly.express as px
import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtWidgets import QDialog
from PyQt6.QtGui import QIcon
from .simple_wordcloud import Wordcloud

from .GUI.ui_dialog_charts import Ui_DialogCharts

from .helpers import ExportDirectoryPathDialog, Message
from .report_attributes import DialogSelectAttributeParameters

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class ViewCharts(QDialog):
    """ Dialog to view various charts of codes and categories.
    """

    app = None
    conn = None
    settings = None
    categories = []
    codes = []
    files = []
    cases = []
    attributes = []  # For charts of attributes
    attribute_file_ids = []  # For filtering based on attribute selection
    attributes_msg = ""  # Tooltip msg for filtering based on attribute selection
    attribute_case_ids_and_names = []  # Used for Case heatmaps based on attribute selection
    stopwords_filepath = None

    def __init__(self, app):
        """ Set up the dialog. """

        QDialog.__init__(self)
        self.app = app
        self.settings = app.settings
        self.conn = app.conn
        self.attribute_file_ids = []
        self.attributes_msg = ""
        self.stopwords_filepath = None
        # Set up the user interface from Designer.
        self.ui = Ui_DialogCharts()
        self.ui.setupUi(self)
        integers = QtGui.QIntValidator()
        self.ui.lineEdit_filter.setValidator(integers)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.ui.pushButton_attributes.pressed.connect(self.select_attributes)
        # Get coder names from all tables
        sql = "select owner from  code_image union select owner from code_text union select owner from code_av "
        sql += " union select owner from cases union select owner from journal union select owner from attribute "
        sql += "union select owner from source union select owner from annotation union select owner from code_name "
        sql += "union select owner from code_cat"
        coders = [""]
        cur = self.app.conn.cursor()
        cur.execute(sql)
        results = cur.fetchall()
        for row in results:
            if row[0] != "":
                coders.append(row[0])
        self.ui.comboBox_coders.addItems(coders)

        self.attributes = []
        cur.execute("select name, ifnull(memo,''), caseOrFile, valuetype from attribute_type")
        result = cur.fetchall()
        self.attributes = []
        keys = 'name', 'memo', 'caseOrFile', 'valuetype'
        for row in result:
            self.attributes.append(dict(zip(keys, row)))
        self.fill_combobox_attributes()
        self.ui.radioButton_file.clicked.connect(self.fill_combobox_attributes)
        self.ui.radioButton_case.clicked.connect(self.fill_combobox_attributes)

        self.files = self.app.get_filenames()
        files_combobox_list = [""]
        for f in self.files:
            files_combobox_list.append(f['name'])
        self.ui.comboBox_file.addItems(files_combobox_list)
        self.cases = self.app.get_casenames()
        cases_combobox_list = [""]
        for f in self.cases:
            cases_combobox_list.append(f['name'])
        self.ui.comboBox_case.addItems(cases_combobox_list)
        self.ui.comboBox_case.currentIndexChanged.connect(self.clear_combobox_files)
        self.ui.comboBox_file.currentIndexChanged.connect(self.clear_combobox_cases)
        self.get_selected_categories_and_codes()
        self.ui.comboBox_pie_charts.currentIndexChanged.connect(self.show_pie_chart)
        pie_combobox_list = ['', _('Code frequency'),
                             _('Code by characters'),
                             _('Code by image area'),
                             _('Code by audio/video segments'),
                             ]
        self.ui.comboBox_pie_charts.addItems(pie_combobox_list)
        self.ui.comboBox_sunburst_charts.currentIndexChanged.connect(self.show_hierarchy_chart)
        sunburst_combobox_list = ['', _('Code frequency sunburst'),
                                  _('Code frequency treemap'),
                                  _('Code by characters sunburst'),
                                  _('Code by characters treemap'),
                                  _('Code by image area sunburst'),
                                  _('Code by image area treemap'),
                                  _('Code by A/V sunburst'),
                                  _('Code by A/V treemap')
                                  ]
        self.ui.comboBox_sunburst_charts.addItems(sunburst_combobox_list)
        self.ui.comboBox_bar_charts.currentIndexChanged.connect(self.show_bar_chart)
        bar_combobox_list = ['', _('Code frequency'),
                             _('Code by characters'),
                             _('Code by image area'),
                             _('Code by audio/video segments')
                             ]
        self.ui.comboBox_bar_charts.addItems(bar_combobox_list)
        stacked_bar_combobox_list = ['', _('Files by codes'),
                            _('Codes by files'),
                            _('Cases by codes'),
                            _("Codes by cases")
                             ]
        self.ui.comboBox_cumulative_bar.addItems(stacked_bar_combobox_list)
        self.ui.comboBox_cumulative_bar.currentIndexChanged.connect(self.show_cumulative_bar_chart)
        categories_combobox_list = [""]
        for c in self.categories:
            categories_combobox_list.append(c['name'])
        self.ui.comboBox_category.addItems(categories_combobox_list)
        # QIntValidator does not use upper limits, it is based on number of digits entered. eg 99 possible
        self.ui.lineEdit_count_limiter.setValidator(QtGui.QIntValidator(0, 50))
        self.ui.lineEdit_count_limiter.setText("0")

        self.ui.label_word_clouds.setToolTip(_("Word cloud made from coded text segments"))
        wordcloud_backgrounds = ['Black', 'White']  # Do not translate!
        self.ui.comboBox_wordcloud_background.addItems(wordcloud_backgrounds)
        wordcloud_foregrounds = ["white", "grey", "black", 'yellow', 'green', "red", "cyan", "magenta", "deepskyblue",
                                 "indigo", "lightcoral", "olive", "tan",
                                 "greys", "greens", "oranges", "pinks", "reds", "yellows", "blues",
                                 "blue to yellow", "blue to orange", "blue to red", "blue to aqua", "grey to red",
                                 "black to pink", "orange to purple", "salmon to aqua", "green to blue",
                                 "yellow to green", "aqua to pink", "river nights", "random"
                                 ]
        self.ui.comboBox_wordcloud_foreground.addItems(wordcloud_foregrounds)
        wordcloud_ngram_options = ["1", "2", "3", "4"]
        self.ui.comboBox_ngrams.addItems(wordcloud_ngram_options)
        self.ui.pushButton_stopwords.clicked.connect(self.set_stopwords_filepath)
        # QIntValidator does not use upper limits, it is based on number of digits entered. eg 999 possible
        self.ui.lineEdit_max_words.setValidator(QtGui.QIntValidator(50, 500))
        self.ui.lineEdit_max_words.setText("200")
        # QIntValidator does not use upper limits, it is based on number of digits entered. eg 9999 possible
        self.ui.lineEdit_height.setValidator(QtGui.QIntValidator(100, 2000))
        self.ui.lineEdit_width.setText("800")
        self.ui.lineEdit_width.setValidator(QtGui.QIntValidator(100, 2000))
        self.ui.lineEdit_height.setText("600")
        self.ui.pushButton_wordcloud.setIcon(qta.icon('mdi6.play', options=[{'scale_factor': 2}]))
        self.ui.pushButton_wordcloud.pressed.connect(self.show_word_cloud)
        # Attributes comboboxes. Initial radio button checked is Files
        self.ui.comboBox_char_attributes.currentIndexChanged.connect(self.character_attribute_charts)
        self.ui.comboBox_num_attributes.currentIndexChanged.connect(self.numeric_attribute_charts)
        # Heatmaps
        heatmap_combobox_list = ["", "File", "Case"]
        self.ui.comboBox_heatmap.addItems(heatmap_combobox_list)
        self.ui.comboBox_heatmap.currentIndexChanged.connect(self.make_heatmap)

    # DATA FILTERS SECTION
    def select_attributes(self):
        """ Select files based on attribute selections using DialogSelectAttributeParameters.
        Attribute selection results are a list of:

        DialogSelectAttributeParameters returns lists for each parameter selected of:
        attribute name, file or case, character or numeric, operator, list of one or two comparator values
        two comparator values are used with the 'between' operator
        ['source', 'file', 'character', '==', ["'interview'"]]
        ['case name', 'case', 'character', '==', ["'ID1'"]]

        [0] boolean or OR boolean and
        [1] ...[n] each select attribute
        [['BOOLEAN_OR'], ['Age', 'case', 'numeric', '>', ['10']], ['source', 'file', 'character', '=', ["'internal'"]]]
        Each selected attribute contains:
        [0] attribute name,
        [1] case or file
        [2] attribute type: character, numeric
        [3] modifier: > < == != like between
        [4] comparison value as list, one item or two items for between

        sqls are NOT parameterised.
        Results from multiple parameters are intersected, an AND boolean function.
        Results stored in attribute_file_ids as list of file_id integers
        """

        self.attribute_file_ids = []
        self.attributes_msg = ""
        ui = DialogSelectAttributeParameters(self.app)
        ok = ui.exec()
        if not ok:
            self.ui.pushButton_attributes.setToolTip("")
            return
        # Run a series of sql based on each selected attribute
        # Apply a set to the resulting ids to determine the final list of ids
        # use the methods in the report_attributes.py
        # using file and case parameters and selected 'and' or 'or'
        self.attribute_file_ids = ui.result_file_ids
        self.attributes_msg = ui.tooltip_msg.replace(_("Show files:"), "")
        if not self.attribute_file_ids:
            self.attributes_msg = ""
            self.ui.pushButton_attributes.setIcon(QtGui.QIcon())
        else:
            self.ui.pushButton_attributes.setIcon(qta.icon('mdi6.variable'))
        self.ui.pushButton_attributes.setToolTip(self.attributes_msg)

    def clear_combobox_files(self):
        """ Clear file selection if a case is selected.
        Clear any attributes selected.
        Called on combobox_case index change. """
        self.ui.comboBox_file.blockSignals(True)
        self.ui.comboBox_file.setCurrentIndex(0)
        self.ui.comboBox_file.blockSignals(False)
        self.attribute_file_ids = []
        self.attributes_msg = ""
        self.ui.pushButton_attributes.setToolTip("")
        self.ui.pushButton_attributes.setIcon(QtGui.QIcon())

    def clear_combobox_cases(self):
        """ Clear case selection if a file is selected.
        Clear any attributes selected.
        Called on combobox_file index change. """

        self.ui.comboBox_case.blockSignals(True)
        self.ui.comboBox_case.setCurrentIndex(0)
        self.ui.comboBox_case.blockSignals(False)
        self.attribute_file_ids = []
        self.attributes_msg = ""
        self.ui.pushButton_attributes.setToolTip("")
        self.ui.pushButton_attributes.setIcon(QtGui.QIcon())

    def set_stopwords_filepath(self):
        """ Set stopwords from a user selected file for the word cloud.
         This overrides exisitng stops words in simple_wordcloud,
         and overrides stops words file in .qualcoder configuration folder."""

        default_import_directory = os.path.expanduser("~")
        response = QtWidgets.QFileDialog.getOpenFileName(None, _('Select stopwords file'),
                                                         default_import_directory,
                                                         "Text Files (*.txt)",
                                                         options=QtWidgets.QFileDialog.Option.DontUseNativeDialog
                                                         )
        print(response)
        if response[0] == "":
            self.stopwords_filepath = None
            self.ui.pushButton_stopwords.setIcon(QIcon())
            return
        self.stopwords_filepath = response[0]
        self.ui.pushButton_stopwords.setToolTip(response[0])
        self.ui.pushButton_stopwords.setIcon(qta.icon('mdi6.file-check-outline', options=[{'scale_factor': 1.3}]))

    def get_file_ids(self):
        """ Get file ids based on file selection or case selection.
        Also returns attribute-selected file ids.
        Called by: pie, bar, hierarchy charts
        return two String values:
            attributes, case or file name;
            sql string of '' or file_ids comma separated as in (,,,) or =id
        """

        if self.attribute_file_ids:
            file_ids = ""
            for id_ in self.attribute_file_ids:
                file_ids += "," + str(id_)
            return _("Attributes: ") + self.attributes_msg + " ", f" in ({file_ids[1:]})"

        file_name = self.ui.comboBox_file.currentText()
        case_name = self.ui.comboBox_case.currentText()
        if file_name == "" and case_name == "":
            return "", ""
        if file_name != "":
            for f in self.files:
                if f['name'] == file_name:
                    return _("File: ") + file_name + " ", f"={f['id']}"
        case_id = -1
        for c in self.cases:
            if c['name'] == case_name:
                case_id = c['id']
                break
        cur = self.app.conn.cursor()
        sql = "select distinct fid from case_text where caseid=?"
        cur.execute(sql, [case_id, ])
        res = cur.fetchall()
        file_ids = ""
        for r in res:
            file_ids += "," + str(r[0])
        if file_ids == "":
            return "", ""
        return _("Case: ") + case_name + " ", f" in ({file_ids[1:]})"

    def get_selected_categories_and_codes(self):
        """ The base state contains all categories and codes.
        A selected category, via combo box selection, restricts the categories and codes.
        """

        self.codes, self.categories = self.app.get_codes_categories()
        # Extra keys for hierarchy charts
        for code in self.codes:
            code['count'] = 0
            code['parentname'] = ""
        for cat in self.categories:
            cat['count'] = 0
            cat['parentname'] = ""

        node = self.ui.comboBox_category.currentText()
        if node == "":
            return
        for category in self.categories:
            if category['name'] == node:
                node = category
                node['supercatid'] = None
                break
        """ Create a list of this category (node) and all its category children.
        Note, maximum depth of 100. """
        selected_categories = [node]
        i = 0  # Ensure an exit from loop
        new_model_changed = True
        while self.categories != [] and new_model_changed and i < 100:
            new_model_changed = False
            append_list = []
            for n in selected_categories:
                for m in self.categories:
                    if m['supercatid'] == n['catid']:
                        append_list.append(m)
            for n in append_list:
                selected_categories.append(n)
                self.categories.remove(n)
                new_model_changed = True
            i += 1
        self.categories = selected_categories
        # Remove codes that are not associated with these categories
        selected_codes = []
        for cat in self.categories:
            for code in self.codes:
                if code['catid'] == cat['catid']:
                    selected_codes.append(code)
        self.codes = selected_codes

    # CODING CHARTS SECTION
    def owner_and_subtitle_helper(self):
        """ Create subtitle with owner, selected files, cases, attributes
         return:
            String owner
            String subtitle of owner, category, case selected
         """

        subtitle = "<br><sup>"
        owner = self.ui.comboBox_coders.currentText()
        if owner == "":
            owner = '%'
            subtitle += _("Coders: all") + " "
        else:
            subtitle += _("Coder: ") + owner + " "
        if self.ui.comboBox_category.currentText() != "":
            subtitle += _("Category: ") + self.ui.comboBox_category.currentText() + " "
        if self.ui.comboBox_case.currentText() != "":
            subtitle += _("Case: ") + self.ui.comboBox_case.currentText()
        if self.ui.pushButton_attributes.toolTip() != "":
            subtitle += " " + _("Attributes: ") + self.ui.pushButton_attributes.toolTip()
        return owner, subtitle

    def helper_export_html(self, fig):
        """ Export chart. Used for all created charts to save an image to the default directory. """

        if self.ui.checkBox_export_html.isChecked():
            export_path = ExportDirectoryPathDialog(self.app, "Chart.html")
            filepath = export_path.filepath
            if filepath is None:
                return
            fig.write_html(filepath)

    def show_word_cloud(self):
        """ Show word cloud.
         Can be by file and/or by category. """

        title = _('Word cloud')
        owner, subtitle = self.owner_and_subtitle_helper()
        self.get_selected_categories_and_codes()
        cur = self.app.conn.cursor()
        values = []
        case_file_name, file_ids = self.get_file_ids()
        if case_file_name != "":
            subtitle += case_file_name
        for c in self.codes:
            sql = "select seltext from code_text where cid=? and owner like ?"
            if file_ids != "":
                sql = "select seltext from code_text where cid=? and owner like ? and fid" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res_text = cur.fetchone()
            if res_text:
                values.append(res_text[0])
        # Create image
        text = " ".join(values)
        background = self.ui.comboBox_wordcloud_background.currentText()
        foreground = self.ui.comboBox_wordcloud_foreground.currentText()
        try:
            width = int(self.ui.lineEdit_width.text())
        except ValueError:
            width = 800
            self.ui.lineEdit_width.setText("800")
        try:
            height = int(self.ui.lineEdit_height.text())
        except ValueError:
            height = 600
            self.ui.lineEdit_height.setText("600")
        try:
            max_words = int(self.ui.lineEdit_max_words.text())
        except ValueError:
            max_words = 200
            self.ui.lineEdit_max_words.setText("200")
        reverse_colors = self.ui.checkBox_reverse_range.isChecked()
        ngrams = int( self.ui.comboBox_ngrams.currentText())
        Wordcloud(self.app, text, width=width, height=height, max_words=max_words, background_color=background,
                  text_color=foreground, reverse_colors=reverse_colors, ngrams=ngrams,
                  stopwords_filepath2=self.stopwords_filepath)

    def codes_of_category_helper(self, category_name):
        """ Get child categories and codes of this category node.
        Only keep the category or code name. Used to reposition TextGraphicsItems on moving a category.

        param: node : Dictionary of category

        return: child_names : List
        """

        if category_name['cid'] is not None:
            return []
        child_names = []
        codes, categories = self.app.get_codes_categories()
        """ qdpx import quirk, but category names and code names can match. (MAXQDA, Nvivo)
        This causes hierarchy to not work correctly (eg when moving a category).
        Solution, add spaces after the code_name to separate it out. """
        for code in codes:
            for cat in categories:
                if code['name'] == cat['name']:
                    code['name'] = code['name'] + " "

        """ Create a list of this category (node) and all its category children.
        Maximum depth of 200. """
        selected_categories = [category_name]
        i = 0  # Ensure an exit from loop
        new_model_changed = True
        while categories != [] and new_model_changed and i < 200:
            new_model_changed = False
            append_list = []
            for n in selected_categories:
                for m in categories:
                    if m['supercatid'] == n['catid']:
                        append_list.append(m)
                        child_names.append(m['name'])
            for n in append_list:
                selected_categories.append(n)
                categories.remove(n)
                new_model_changed = True
            i += 1
        categories = selected_categories
        # Remove codes that are not associated with these categories
        selected_codes = []
        for cat in categories:
            for code in codes:
                if code['catid'] == cat['catid']:
                    selected_codes.append(code)
        codes = selected_codes
        for c in codes:
            child_names.append(c['name'])
        return child_names

    def show_cumulative_bar_chart(self):
        """ Cumulative bar chart of codes by files/cases or
         conversely, files/cases by codes. """

        chart_type_index = self.ui.comboBox_cumulative_bar.currentIndex()
        if chart_type_index < 1:
            return
        self.get_selected_categories_and_codes()
        if chart_type_index == 1:
            self.stacked_barchart_files_by_codes()
        if chart_type_index == 2:
            self.stacked_barchart_codes_by_files()
        if chart_type_index == 3:
            self.stacked_barchart_cases_by_codes()
        if chart_type_index == 4:
            self.stacked_barchart_codes_by_cases()
        self.ui.comboBox_cumulative_bar.setCurrentIndex(0)

    def stacked_barchart_codes_by_cases(self):
        """ Frequency of codes in each case (file collection), cumulative, for each case row.
        Index numbering matches order of options, set up in init. Need this to avoid translation issues.

        Sample data frame for cumulative bar chart display
        data = {
            'Cases': ['A', 'A', 'A', 'B', 'B', 'B', 'C', 'C', 'C'],
            'Codes': ['X', 'Y', 'Z', 'X', 'Y', 'Z', 'X', 'Y', 'Z'],
            'Counts': [10, 15, 7, 12, 10, 8, 15, 12, 10]
        }
        """

        title = _('Cumulative code count in cases by case')
        owner, subtitle = self.owner_and_subtitle_helper()
        title += subtitle
        # if a case or file selection is made: file_ids is comma separated string of file ids
        case_file_name, file_ids = self.get_file_ids()

        # Calculate
        cur = self.app.conn.cursor()
        codes = []
        cases = []
        counts = []
        for c in self.codes:
            sql = "select cases.name from cases join case_text on cases.caseid = case_text.caseid " \
                  "join code_text on code_text.fid=case_text.fid" \
                  " where cid=? and code_text.owner like ? order by cases.name asc"
            if file_ids != "":
                sql = "select cases.name from cases join case_text on cases.caseid = case_text.caseid " \
                      "join code_text on code_text.fid=case_text.fid where" \
                      " cid=? and code_text.owner like ? and code_text.fid" + file_ids + " order by cases.name asc"
            cur.execute(sql, [c['cid'], owner])
            res_text = cur.fetchall()
            sql = "select cases.name from cases join case_text on cases.caseid = case_text.caseid " \
                  " join code_image on code_image.id=case_text.fid where \
             cid=? and code_image.owner like ? order by cases.name asc"
            if file_ids != "":
                sql = "select cases.name from cases join case_text on cases.caseid = case_text.caseid " \
                      "join code_image on code_image.id=case_text.fid where " \
                      "cid=? and code_image.owner like ? and code_image.id" + file_ids + " order by cases.name asc"
            cur.execute(sql, [c['cid'], owner])
            res_image = cur.fetchall()
            sql = "select cases.name from cases join case_text on cases.caseid = case_text.caseid " \
            " join code_av on case_text.fid=code_av.id where \
            cid=? and code_av.owner like ? order by cases.name asc"
            if file_ids != "":
                sql = "select cases.name from cases join case_text on cases.caseid = case_text.caseid " \
                "join code_av code_av.id=case_text.fid where " \
                "cid=? and code_av.owner like ? and code_av.id" + file_ids + " order by cases.name asc"
            cur.execute(sql, [c['cid'], owner])
            res_av = cur.fetchall()
            file_names_long = []
            for r in res_text:
                file_names_long.append(r[0])
            for r in res_image:
                file_names_long.append(r[0])
            for r in res_av:
                file_names_long.append(r[0])
            file_code_counts = Counter(file_names_long)

            for item in file_code_counts.items():
                codes.append(c['name'])
                cases.append(item[0])
                counts.append(item[1])

        # Create stacked bar chart
        data = {
            _('Cases'): cases,
            _('Codes'): codes,
            _('Counts'): counts
        }
        df = pd.DataFrame(data)
        fig = px.bar(df,
                     x=_("Counts"),
                     y=_("Cases"),
                     color=_("Codes"),
                     orientation='h',
                     title=title
                     )
        fig.show()
        self.helper_export_html(fig)

    def stacked_barchart_cases_by_codes(self):
        """ Frequency of codes in each case (file collection), cumulative across codes, for each code row.
        Index numbering matches order of options, set up in init. Need this to avoid translation issues.

        Sample data frame for cumulative bar chart display
        data = {
            'Codes': ['A', 'A', 'A', 'B', 'B', 'B', 'C', 'C', 'C'],
            'Cases': ['X', 'Y', 'Z', 'X', 'Y', 'Z', 'X', 'Y', 'Z'],
            'Counts': [10, 15, 7, 12, 10, 8, 15, 12, 10]
        }
        """

        title = _('Cumulative code count in cases by code')
        owner, subtitle = self.owner_and_subtitle_helper()
        title += subtitle
        # if a case or file selection is made: file_ids is comma separated string of file ids
        case_file_name, file_ids = self.get_file_ids()

        # Calculate
        cur = self.app.conn.cursor()
        codes = []
        cases = []
        counts = []
        for c in self.codes:
            sql = "select cases.name from cases join case_text on cases.caseid = case_text.caseid " \
                  "join code_text on code_text.fid=case_text.fid" \
                  " where cid=? and code_text.owner like ? order by cases.name asc"
            if file_ids != "":
                sql = "select cases.name from cases join case_text on cases.caseid = case_text.caseid " \
                      "join code_text on code_text.fid=case_text.fid where" \
                      " cid=? and code_text.owner like ? and code_text.fid" + file_ids + " order by cases.name asc"
            cur.execute(sql, [c['cid'], owner])
            res_text = cur.fetchall()
            sql = "select cases.name from cases join case_text on cases.caseid = case_text.caseid " \
                  " join code_image on code_image.id=case_text.fid where \
             cid=? and code_image.owner like ? order by cases.name asc"
            if file_ids != "":
                sql = "select cases.name from cases join case_text on cases.caseid = case_text.caseid " \
                      "join code_image on code_image.id=case_text.fid where " \
                      "cid=? and code_image.owner like ? and code_image.id" + file_ids + " order by cases.name asc"
            cur.execute(sql, [c['cid'], owner])
            res_image = cur.fetchall()
            sql = "select cases.name from cases join case_text on cases.caseid = case_text.caseid " \
            " join code_av on case_text.fid=code_av.id where \
            cid=? and code_av.owner like ? order by cases.name asc"
            if file_ids != "":
                sql = "select cases.name from cases join case_text on cases.caseid = case_text.caseid " \
                "join code_av code_av.id=case_text.fid where " \
                "cid=? and code_av.owner like ? and code_av.id" + file_ids + " order by cases.name asc"
            cur.execute(sql, [c['cid'], owner])
            res_av = cur.fetchall()
            file_names_long = []
            for r in res_text:
                file_names_long.append(r[0])
            for r in res_image:
                file_names_long.append(r[0])
            for r in res_av:
                file_names_long.append(r[0])
            file_code_counts = Counter(file_names_long)

            for item in file_code_counts.items():
                codes.append(c['name'])
                cases.append(item[0])
                counts.append(item[1])

        # Create stacked bar chart
        data = {
            _('Codes'): codes,
            _('Cases'): cases,
            _('Counts'): counts
        }
        df = pd.DataFrame(data)
        fig = px.bar(df,
                     x=_("Counts"),
                     y=_("Codes"),
                     color=_("Cases"),
                     orientation='h',
                     title=title
                     )
        fig.show()
        self.helper_export_html(fig)

    def stacked_barchart_files_by_codes(self):
        """ Frequency of codes in each file, cumulative across codes, for each code row.
        Index numbering matches order of options, set up in init. Need this to avoid translation issues.

        Sample data frame for cumulative bar chart display
        data = {
            'Codes': ['A', 'A', 'A', 'B', 'B', 'B', 'C', 'C', 'C'],
            'File': ['X', 'Y', 'Z', 'X', 'Y', 'Z', 'X', 'Y', 'Z'],
            'Counts': [10, 15, 7, 12, 10, 8, 15, 12, 10]
        }
        """

        title = _('Cumulative code count in files by code')
        owner, subtitle = self.owner_and_subtitle_helper()
        title += subtitle
        # if a case or file selection is made: file_ids is comma separated string of file ids
        case_file_name, file_ids = self.get_file_ids()

        # Calculate
        cur = self.app.conn.cursor()
        codes = []
        files = []
        counts = []
        for c in self.codes:
            sql = "select source.name from code_text join source on id=code_text.fid where" \
                  " cid=? and code_text.owner like ? order by source.name asc"
            if file_ids != "":
                sql = "select source.name from code_text join source on id=code_text.fid where" \
                      " cid=? and code_text.owner like ? and fid" + file_ids + " order by source.name asc"
            cur.execute(sql, [c['cid'], owner])
            res_text = cur.fetchall()
            sql = "select source.name from code_image join source on source.id=code_image.id where \
             cid=? and code_image.owner like ? order by source.name asc"
            if file_ids != "":
                sql = "select source.name from code_image join source on source.id=code_image.id where \
                 cid=? and code_image.owner like ? and source.id" + file_ids + " order by source.name asc"
            cur.execute(sql, [c['cid'], owner])
            res_image = cur.fetchall()
            sql = "select source.name from code_av join source on source.id=code_av.id where \
            cid=? and code_av.owner like ? order by source.name asc"
            if file_ids != "":
                sql = "select source.name from code_av join source on source.id=code_av.id where \
                cid=? and code_av.owner like ? and source.id" + file_ids + " order by source.name asc"
            cur.execute(sql, [c['cid'], owner])
            res_av = cur.fetchall()
            file_names_long = []
            for r in res_text:
                file_names_long.append(r[0])
            for r in res_image:
                file_names_long.append(r[0])
            for r in res_av:
                file_names_long.append(r[0])
            file_code_counts = Counter(file_names_long)
            for item in file_code_counts.items():
                codes.append(c['name'])
                files.append(item[0])
                counts.append(item[1])
        # Create stacked bar chart
        data = {
            _('Codes'): codes,
            _('Files'): files,
            _('Counts'): counts
        }
        df = pd.DataFrame(data)
        fig = px.bar(df,
                     x=_("Counts"),
                     y=_("Codes"),
                     color=_("Files"),
                     orientation='h',
                     title=title
                     )
        fig.show()
        self.helper_export_html(fig)

    def stacked_barchart_codes_by_files(self):
        """ Frequency of codes in each file, cumulative across files, for each code row.
        Index numbering matches order of options, set up in init. Need this to avoid translation issues.

        Sample data frame for cumulative bar chart display
        data = {
            'Files': ['A', 'A', 'A', 'B', 'B', 'B', 'C', 'C', 'C'],
            'Codes': ['X', 'Y', 'Z', 'X', 'Y', 'Z', 'X', 'Y', 'Z'],
            'Counts': [10, 15, 7, 12, 10, 8, 15, 12, 10]
        }
        """

        title = _('Cumulative code count in codes by file')
        owner, subtitle = self.owner_and_subtitle_helper()
        title += subtitle
        # if a case or file selection is made: file_ids is comma separated string of file ids
        case_file_name, file_ids = self.get_file_ids()

        # Calculate
        cur = self.app.conn.cursor()
        codes = []
        files = []
        counts = []
        for c in self.codes:
            sql = "select source.name from code_text join source on id=code_text.fid where" \
                  " cid=? and code_text.owner like ? order by source.name asc"
            if file_ids != "":
                sql = "select source.name from code_text join source on id=code_text.fid where" \
                      " cid=? and code_text.owner like ? and fid" + file_ids + " order by source.name asc"
            cur.execute(sql, [c['cid'], owner])
            res_text = cur.fetchall()
            sql = "select source.name from code_image join source on source.id=code_image.id where \
             cid=? and code_image.owner like ? order by source.name asc"
            if file_ids != "":
                sql = "select source.name from code_image join source on source.id=code_image.id where \
                 cid=? and code_image.owner like ? and source.id" + file_ids + " order by source.name asc"
            cur.execute(sql, [c['cid'], owner])
            res_image = cur.fetchall()
            sql = "select source.name from code_av join source on source.id=code_av.id where \
            cid=? and code_av.owner like ? order by source.name asc"
            if file_ids != "":
                sql = "select source.name from code_av join source on source.id=code_av.id where \
                cid=? and code_av.owner like ? and source.id" + file_ids + " order by source.name asc"
            cur.execute(sql, [c['cid'], owner])
            res_av = cur.fetchall()
            file_names_long = []
            for r in res_text:
                file_names_long.append(r[0])
            for r in res_image:
                file_names_long.append(r[0])
            for r in res_av:
                file_names_long.append(r[0])
            file_code_counts = Counter(file_names_long)
            for item in file_code_counts.items():
                codes.append(c['name'])
                files.append(item[0])
                counts.append(item[1])
        # Create stacked bar chart
        data = {
            _('Files'): files,
            _('Codes'): codes,
            _('Counts'): counts
        }
        df = pd.DataFrame(data)
        fig = px.bar(df,
                     x=_("Counts"),
                     y=_("Files"),
                     color=_("Codes"),
                     orientation='h',
                     title=title
                     )
        fig.show()
        self.helper_export_html(fig)

    def show_bar_chart(self):
        """ https://www.tutorialspoint.com/plotly/plotly_bar_and_pie_chart.htm
        Index numbering matches order of options, set up in init. Need this to avoid translation issues.
        """

        chart_type_index = self.ui.comboBox_bar_charts.currentIndex()
        if chart_type_index < 1:
            return
        self.get_selected_categories_and_codes()
        if chart_type_index == 1:  # Code frequency
            self.barchart_code_frequency()
        if chart_type_index == 2:  # Code by characters
            self.barchart_code_volume_by_characters()
        if chart_type_index == 3:  # Code by image area
            self.barchart_code_volume_by_area()
        if chart_type_index == 4:  # Code by audio/video segments
            self.barchart_code_volume_by_segments()
        self.ui.comboBox_bar_charts.setCurrentIndex(0)

    def barchart_code_frequency(self):
        """ Count of codes across text, images and A/V.
        By owner.
        """

        title = _('Code count - text, images and Audio/Video')
        owner, subtitle = self.owner_and_subtitle_helper()
        cur = self.app.conn.cursor()
        values = []
        labels = []
        case_file_name, file_ids = self.get_file_ids()
        for c in self.codes:
            sql = "select count(cid) from code_text where cid=? and owner like ?"
            if file_ids != "":
                sql = "select count(cid) from code_text where cid=? and owner like ? and fid" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res_text = cur.fetchone()
            sql = "select count(cid) from code_image where cid=? and owner like ?"
            if file_ids != "":
                sql = "select count(cid) from code_image where cid=? and owner like ? and id" + file_ids

            cur.execute(sql, [c['cid'], owner])
            res_image = cur.fetchone()
            sql = "select count(cid) from code_av where cid=? and owner like ?"
            if file_ids != "":
                sql = "select count(cid) from code_av where cid=? and owner like ? and id" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res_av = cur.fetchone()
            labels.append(c['name'])
            values.append(res_text[0] + res_image[0] + res_av[0])
        # Create pandas DataFrame
        data = {'Code names': labels, 'Count': values}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['Count'] != 0
        if cutoff != "":
            mask = df['Count'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        fig = px.bar(df[mask], y='Code names', x='Count', orientation='h', title=title + subtitle)
        fig.show()
        self.helper_export_html(fig)

    def barchart_code_volume_by_characters(self):
        """ Count of codes in files text by character volume. """

        title = _('Code text by character count')
        owner, subtitle = self.owner_and_subtitle_helper()
        cur = self.app.conn.cursor()
        values = []
        labels = []
        case_file_name, file_ids = self.get_file_ids()
        for c in self.codes:
            sql = "select sum(pos1 - pos0) from code_text where cid=? and owner like ?"
            if file_ids != "":
                sql = "select sum(pos1 - pos0) from code_text where cid=? and owner like ? and fid" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res = cur.fetchone()
            labels.append(c['name'])
            values.append(res[0])
        # Create pandas DataFrame
        data = {'Code names': labels, 'Total characters': values}
        df = pd.DataFrame(data)
        mask = df['Total characters'] != 0
        cutoff = self.ui.lineEdit_filter.text()
        if cutoff != "":
            mask = df['Total characters'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        fig = px.bar(df[mask], x='Total characters', y='Code names', orientation='h', title=title + subtitle)
        fig.show()
        self.helper_export_html(fig)

    def barchart_code_volume_by_area(self):
        """ Codes by image area volume. """

        title = _('Code volume by image area (pixels)')
        owner, subtitle = self.owner_and_subtitle_helper()
        cur = self.app.conn.cursor()
        values = []
        labels = []
        case_file_name, file_ids = self.get_file_ids()
        for c in self.codes:
            sql = "select sum(cast(width as int) * cast(height as int)) from code_image where cid=? and owner like ?"
            if file_ids != "":
                sql = "select sum(cast(width as int) * cast(height as int)) from code_image where cid=? and owner like ? and id" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res = cur.fetchone()
            labels.append(c['name'])
            values.append(res[0])
        # Create pandas DataFrame
        data = {'Code names': labels, 'Pixels': values}
        df = pd.DataFrame(data)
        mask = df['Pixels'] != 0
        cutoff = self.ui.lineEdit_filter.text()
        if cutoff != "":
            mask = df['Pixels'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        fig = px.bar(df[mask], x='Pixels', y='Code names', orientation='h', title=title + subtitle)
        fig.show()
        self.helper_export_html(fig)

    def barchart_code_volume_by_segments(self):
        """ Codes by audio/video segment volume. """

        title = _('Code volume by audio/video segments (milliseconds)')
        owner, subtitle = self.owner_and_subtitle_helper()
        cur = self.app.conn.cursor()
        values = []
        labels = []
        case_file_name, file_ids = self.get_file_ids()
        for c in self.codes:
            sql = "select sum(pos1 - pos0) from code_av where cid=? and owner like ?"
            if file_ids != "":
                sql = "select sum(pos1 - pos0) from code_av where cid=? and owner like ? and id" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res = cur.fetchone()
            labels.append(c['name'])
            values.append(res[0])
        # Create pandas DataFrame
        data = {'Code names': labels, 'Total millisecs': values}
        df = pd.DataFrame(data)
        mask = df['Total millisecs'] != 0
        cutoff = self.ui.lineEdit_filter.text()
        if cutoff != "":
            mask = df['Total millisecs'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        fig = px.bar(df[mask], x='Total millisecs', y='Code names', orientation='h', title=title + subtitle)
        fig.show()
        self.helper_export_html(fig)

    def show_pie_chart(self):
        """ Various pie chart options.
        Index numbering matches order of options, set up in init
        """

        chart_type_index = self.ui.comboBox_pie_charts.currentIndex()
        if chart_type_index < 1:
            return
        self.get_selected_categories_and_codes()
        if chart_type_index == 1:  # Code frequency
            self.piechart_code_frequency()
        if chart_type_index == 2:  # Code by characters
            self.piechart_code_volume_by_characters()
        if chart_type_index == 3:  # Code by image area
            self.piechart_code_volume_by_area()
        if chart_type_index == 4:  # Code by audio/video segments
            self.piechart_code_volume_by_segments()
        self.ui.comboBox_pie_charts.setCurrentIndex(0)

    def piechart_code_frequency(self):
        """ Count of codes across text, images and A/V.
        """

        title = _('Code count - text, images and Audio/Video')
        owner, subtitle = self.owner_and_subtitle_helper()
        cur = self.app.conn.cursor()
        values = []
        labels = []
        case_file_name, file_ids = self.get_file_ids()
        for c in self.codes:
            sql = "select count(cid) from code_text where cid=? and owner like ?"
            if file_ids != "":
                sql = "select count(cid) from code_text where cid=? and owner like ? and fid" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res_text = cur.fetchone()
            sql = "select count(cid) from code_image where cid=? and owner like ?"
            if file_ids != "":
                sql = "select count(cid) from code_image where cid=? and owner like ? and id" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res_image = cur.fetchone()
            sql = "select count(cid) from code_av where cid=? and owner like ?"
            if file_ids != "":
                sql = "select count(cid) from code_av where cid=? and owner like ? and id" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res_av = cur.fetchone()
            labels.append(c['name'])
            values.append(res_text[0] + res_image[0] + res_av[0])
        # Create pandas DataFrame
        data = {'Code names': labels, 'Count': values}
        df = pd.DataFrame(data)
        mask = df['Count'] != 0
        cutoff = self.ui.lineEdit_filter.text()
        if cutoff != "":
            mask = df['Count'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        fig = px.pie(df[mask], values='Count', names='Code names', title=title + subtitle)
        fig.show()
        self.helper_export_html(fig)

    def piechart_code_volume_by_characters(self):
        """ Count of codes in files text by character volume. """

        title = _('Code text by character count')
        owner, subtitle = self.owner_and_subtitle_helper()
        cur = self.app.conn.cursor()
        values = []
        labels = []
        case_file_name, file_ids = self.get_file_ids()
        for c in self.codes:
            sql = "select sum(pos1 - pos0) from code_text where cid=? and owner like ?"
            if file_ids != "":
                sql = "select sum(pos1 - pos0) from code_text where cid=? and owner like ? and fid" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res = cur.fetchone()
            labels.append(c['name'])
            values.append(res[0])
        # Create pandas DataFrame
        data = {'Code names': labels, 'Total characters': values}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['Total characters'] != 0
        if cutoff != "":
            mask = df['Total characters'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        fig = px.pie(df[mask], values='Total characters', names='Code names', title=title + subtitle)
        fig.show()
        self.helper_export_html(fig)

    def piechart_code_volume_by_area(self):
        """ Codes by image area volume. """

        title = _('Code volume by image area (pixels)')
        owner, subtitle = self.owner_and_subtitle_helper()
        case_file_name, file_ids = self.get_file_ids()
        cur = self.app.conn.cursor()
        values = []
        labels = []
        for c in self.codes:
            sql = "select sum(cast(width as int) * cast(height as int)) from code_image where cid=? and owner like ?"
            if file_ids != "":
                sql = "select sum(cast(width as int) * cast(height as int)) from code_image where cid=? and owner like ? and id" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res = cur.fetchone()
            labels.append(c['name'])
            values.append(res[0])
        # Create pandas DataFrame
        data = {'Code names': labels, 'Total pixels': values}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['Total pixels'] != 0
        if cutoff != "":
            mask = df['Total pixels'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        fig = px.pie(df[mask], values='Total pixels', names='Code names', title=title + subtitle)
        fig.show()
        self.helper_export_html(fig)

    def piechart_code_volume_by_segments(self):
        """ Codes by audio/video segment volume. """

        title = _('Code volume by audio/video segments (milliseconds)')
        owner, subtitle = self.owner_and_subtitle_helper()
        case_file_name, file_ids = self.get_file_ids()
        values = []
        labels = []
        cur = self.app.conn.cursor()
        for c in self.codes:
            sql = "select sum(pos1 - pos0) from code_av where cid=? and owner like ?"
            if file_ids != "":
                sql = "select sum(pos1 - pos0) from code_av where cid=? and owner like ? and id" + file_ids
            cur.execute(sql, [c['cid'], owner])
            res = cur.fetchone()
            labels.append(c['name'])
            values.append(res[0])
        # Create pandas DataFrame
        data = {'Code names': labels, 'Total millisecs': values}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['Total millisecs'] != 0
        if cutoff != "":
            mask = df['Total millisecs'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        fig = px.pie(df[mask], values='Total millisecs', names='Code names', title=title + subtitle)
        fig.show()
        self.helper_export_html(fig)

    def show_hierarchy_chart(self):
        """ Disp;lay treemaps and sunburst charts.
        https://plotly.com/python/sunburst-charts/
        Index numbering matches order of options, set up in init
        """

        chart_type_index = self.ui.comboBox_sunburst_charts.currentIndex()
        if chart_type_index < 1:
            return
        self.get_selected_categories_and_codes()
        self.helper_for_matching_category_and_code_name()
        if chart_type_index == 1:  # Code frequency sunburst
            self.hierarchy_code_frequency("sunburst")
        if chart_type_index == 2:  # Code frequency treemap
            self.hierarchy_code_frequency("treemap")
        if chart_type_index == 3:  # Code by characters sunburst
            self.hierarchy_code_volume_by_characters("sunburst")
        if chart_type_index == 4:  # Code by characters treemap
            self.hierarchy_code_volume_by_characters("treemap")
        if chart_type_index == 5:  # Code by image area sunburst
            self.hierarchy_code_volume_by_area("sunburst")
        if chart_type_index == 6:  # Code by image area treemap
            self.hierarchy_code_volume_by_area("treemap")
        if chart_type_index == 7:  # Code by A/V sunburst
            self.hierarchy_code_volume_by_segments("sunburst")
        if chart_type_index == 8:  # Code by A/V treemap
            self.hierarchy_code_volume_by_segments("treemap")
        self.ui.comboBox_sunburst_charts.setCurrentIndex(0)

    def helper_for_matching_category_and_code_name(self):
        """ This is for qdpx imported projects.
        Might be a quirk of importation, but category names and code names can match.
         e.g. Maxqda, Nvivo allows a category name and a code name to be the same. (the same node).
         This causes hierarchy charts to not display.
         Solution, add spaces after the code_name to separate it out. """

        for code in self.codes:
            for cat in self.categories:
                if code['name'] == cat['name']:
                    code['name'] = code['name'] + " "

    def hierarchy_code_frequency(self, chart="sunburst"):
        """ Count of codes across text, images and A/V.
        Calculates code count and category count and displays in sunburst or treemap chart.
        """

        title = chart + _(' chart of counts of codes and categories')
        owner, subtitle = self.owner_and_subtitle_helper()
        # Get all the coded data
        case_file_name, file_ids = self.get_file_ids()
        coded_data = []
        cur = self.app.conn.cursor()
        sql_t = "select cid from code_text where owner like ?"
        if file_ids != "":
            sql_t = "select cid from code_text where owner like ? and fid" + file_ids
        cur.execute(sql_t, [owner])
        result = cur.fetchall()
        for row in result:
            coded_data.append(row)
        sql_i = "select cid from code_image where owner like ?"
        if file_ids != "":
            sql_i = "select cid from code_image where owner like ? and id" + file_ids
        cur.execute(sql_i, [owner])
        result = cur.fetchall()
        for row in result:
            coded_data.append(row)
        sql_av = "select cid from code_av where owner like ?"
        if file_ids != "":
            sql_av = "select cid from code_av where owner like ? and id" + file_ids
        cur.execute(sql_av, [owner])
        result = cur.fetchall()
        for row in result:
            coded_data.append(row)
        # Calculate the frequency of each code
        for code_ in self.codes:
            for coded_item in coded_data:
                if coded_item[0] == code_['cid']:
                    code_['count'] += 1
        # Add the code count directly to each parent category, add parentname to each code
        for category in self.categories:
            for code_ in self.codes:
                if code_['catid'] == category['catid']:
                    category['count'] += code_['count']
                    code_['parentname'] = category['name']
        # Find leaf categories, add to parent categories, and gradually remove leaves
        # Until only top categories remain
        sub_categories = copy(self.categories)
        counter = 0
        while len(sub_categories) > 0 or counter < 5000:
            # Identify parent categories
            parent_list = []
            for super_cat in sub_categories:
                for child_cat in sub_categories:
                    if super_cat['catid'] == child_cat['supercatid']:
                        child_cat['parentname'] = super_cat['name']
                        parent_list.append(super_cat)
            # Identify leaf categories
            leaf_list = []
            for category in sub_categories:
                if category not in parent_list:
                    leaf_list.append(category)
            # Add counts for each leaf category to higher category
            for leaf_category in leaf_list:
                for cat in self.categories:
                    if cat['catid'] == leaf_category['supercatid']:
                        cat['count'] += leaf_category['count']
                sub_categories.remove(leaf_category)
            counter += 1
        combined = self.categories + self.codes
        items = []
        values = []
        parents = []
        for sb_combined in combined:
            items.append(sb_combined['name'])
            values.append(sb_combined['count'])
            parents.append(sb_combined['parentname'])
        # Create pandas DataFrame and Figure
        data = {'item': items, 'value': values, 'parent': parents}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['value'] != 0
        if cutoff != "":
            mask = df['value'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        if chart == "sunburst":
            fig = px.sunburst(df[mask], names='item', parents='parent', values='value',
                              title=title + subtitle)
            fig.show()
            self.helper_export_html(fig)
        if chart == "treemap":
            fig = px.treemap(df[mask], names='item', parents='parent', values='value',
                             title=title + subtitle)
            fig.show()
            self.helper_export_html(fig)

    def hierarchy_code_volume_by_characters(self, chart="sunburst"):
        """ Count of code characters across text files.
            Calculates code count and category count and displays in sunburst or treemap chart.
        """

        title = chart + _(' chart of counts of coded text - total characters')
        owner, subtitle = self.owner_and_subtitle_helper()
        # Get all the coded data
        case_file_name, file_ids = self.get_file_ids()
        coded_data = []
        cur = self.app.conn.cursor()
        sql = "select cid, pos1-pos0 from code_text where owner like ?"
        if file_ids != "":
            sql = "select cid, pos1-pos0 from code_text where owner like ?and fid" + file_ids
        cur.execute(sql, [owner])
        result = cur.fetchall()
        for row in result:
            coded_data.append(row)
        # Calculate the frequency of each code
        for code_ in self.codes:
            for coded_item in coded_data:
                if coded_item[0] == code_['cid']:
                    code_['count'] += coded_item[1]
        # Add the code count directly to each parent category, add parentname to each code
        for category in self.categories:
            for code_ in self.codes:
                if code_['catid'] == category['catid']:
                    category['count'] += code_['count']
                    code_['parentname'] = category['name']
        # Find leaf categories, add to parent categories, and gradually remove leaves
        # Until only top categories remain
        sub_categories = copy(self.categories)
        counter = 0
        while len(sub_categories) > 0 or counter < 5000:
            # Identify parent categories
            parent_list = []
            for super_cat in sub_categories:
                for child_cat in sub_categories:
                    if super_cat['catid'] == child_cat['supercatid']:
                        child_cat['parentname'] = super_cat['name']
                        parent_list.append(super_cat)
            # Identify leaf categories
            leaf_list = []
            for category in sub_categories:
                if category not in parent_list:
                    leaf_list.append(category)
            # Add counts for each leaf category to higher category
            for leaf_category in leaf_list:
                for cat in self.categories:
                    if cat['catid'] == leaf_category['supercatid']:
                        cat['count'] += leaf_category['count']
                sub_categories.remove(leaf_category)
            counter += 1
        combined = self.categories + self.codes
        items = []
        values = []
        parents = []
        for sb_combined in combined:
            items.append(sb_combined['name'])
            values.append(sb_combined['count'])
            parents.append(sb_combined['parentname'])
        # Create pandas DataFrame and Figure
        data = {'item': items, 'value': values, 'parent': parents}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['value'] != 0
        if cutoff != "":
            mask = df['value'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        if chart == "sunburst":
            fig = px.sunburst(df[mask], names='item', parents='parent', values='value',
                              title=title + subtitle)
            fig.show()
            self.helper_export_html(fig)
        if chart == "treemap":
            fig = px.treemap(df[mask], names='item', parents='parent', values='value',
                             title=title + subtitle)
            fig.show()
            self.helper_export_html(fig)

    def hierarchy_code_volume_by_area(self, chart="sunburst"):
        """ Count of coded image areas across image files.
            Displays in sunburst or treemap chart.
        """

        title = chart + _(' chart of coded image areas - pixels')
        owner, subtitle = self.owner_and_subtitle_helper()
        # Get all the coded data
        case_file_name, file_ids = self.get_file_ids()
        coded_data = []
        cur = self.app.conn.cursor()
        sql = "select cid, cast(width as int) * cast(height as int) from code_image where owner like ?"
        if file_ids != "":
            sql = "select cid, cast(width as int) * cast(height as int) from code_image where owner like ? and id" + file_ids
        cur.execute(sql, [owner])
        result = cur.fetchall()
        for row in result:
            coded_data.append(row)
        # Calculate the frequency of each code
        for code_ in self.codes:
            for coded_item in coded_data:
                if coded_item[0] == code_['cid']:
                    code_['count'] += coded_item[1]
        # Add the code count directly to each parent category, add parentname to each code
        for category in self.categories:
            for code_ in self.codes:
                if code_['catid'] == category['catid']:
                    category['count'] += code_['count']
                    code_['parentname'] = category['name']
        # Find leaf categories, add to parent categories, and gradually remove leaves
        # Until only top categories remain
        sub_categories = copy(self.categories)
        counter = 0
        while len(sub_categories) > 0 or counter < 5000:
            # Identify parent categories
            parent_list = []
            for super_cat in sub_categories:
                for child_cat in sub_categories:
                    if super_cat['catid'] == child_cat['supercatid']:
                        child_cat['parentname'] = super_cat['name']
                        parent_list.append(super_cat)
            # Identify leaf categories
            leaf_list = []
            for category in sub_categories:
                if category not in parent_list:
                    leaf_list.append(category)
            # Add counts for each leaf category to higher category
            for leaf_category in leaf_list:
                for cat in self.categories:
                    if cat['catid'] == leaf_category['supercatid']:
                        cat['count'] += leaf_category['count']
                sub_categories.remove(leaf_category)
            counter += 1
        combined = self.categories + self.codes
        items = []
        values = []
        parents = []
        for sb_combined in combined:
            items.append(sb_combined['name'])
            values.append(sb_combined['count'])
            parents.append(sb_combined['parentname'])
        # Create pandas DataFrame and Figure
        data = {'item': items, 'value': values, 'parent': parents}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['value'] != 0
        if cutoff != "":
            mask = df['value'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        if chart == "sunburst":
            fig = px.sunburst(df[mask], names='item', parents='parent', values='value',
                              title=title + subtitle)
            fig.show()
            self.helper_export_html(fig)
        if chart == "treemap":
            fig = px.treemap(df[mask], names='item', parents='parent', values='value',
                             title=title + subtitle)
            fig.show()
            self.helper_export_html(fig)

    def hierarchy_code_volume_by_segments(self, chart="sunburst"):
        """ Count of codes segment durations across audio/video files.
            Displays in sunburst or treemap chart.
        """

        title = chart + _(' chart of coded audio/video segments - milliseconds')
        owner, subtitle = self.owner_and_subtitle_helper()
        # Get all the coded data
        case_file_name, file_ids = self.get_file_ids()
        coded_data = []
        cur = self.app.conn.cursor()
        sql = "select cid, pos1-pos0 from code_av where owner like ?"
        if file_ids != "":
            sql = "select cid, pos1-pos0 from code_av where owner like ? and id" + file_ids
        cur.execute(sql, [owner])
        result = cur.fetchall()
        for row in result:
            coded_data.append(row)
        # Calculate the frequency of each code
        for code_ in self.codes:
            for coded_item in coded_data:
                if coded_item[0] == code_['cid']:
                    code_['count'] += coded_item[1]
        # Add the code count directly to each parent category, add parentname to each code
        for category in self.categories:
            for code_ in self.codes:
                if code_['catid'] == category['catid']:
                    category['count'] += code_['count']
                    code_['parentname'] = category['name']
        # Find leaf categories, add to parent categories, and gradually remove leaves
        # Until only top categories remain
        sub_categories = copy(self.categories)
        counter = 0
        while len(sub_categories) > 0 or counter < 5000:
            # Identify parent categories
            parent_list = []
            for super_cat in sub_categories:
                for child_cat in sub_categories:
                    if super_cat['catid'] == child_cat['supercatid']:
                        child_cat['parentname'] = super_cat['name']
                        parent_list.append(super_cat)
            # Identify leaf categories
            leaf_list = []
            for category in sub_categories:
                if category not in parent_list:
                    leaf_list.append(category)
            # Add counts for each leaf category to higher category
            for leaf_category in leaf_list:
                for cat in self.categories:
                    if cat['catid'] == leaf_category['supercatid']:
                        cat['count'] += leaf_category['count']
                sub_categories.remove(leaf_category)
            counter += 1
        combined = self.categories + self.codes
        items = []
        values = []
        parents = []
        for sb_combined in combined:
            items.append(sb_combined['name'])
            values.append(sb_combined['count'])
            parents.append(sb_combined['parentname'])
        # Create pandas DataFrame and Figure
        data = {'item': items, 'value': values, 'parent': parents}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['value'] != 0
        if cutoff != "":
            mask = df['value'] >= int(cutoff)
            subtitle += _("Values") + " >= " + cutoff
        if chart == "sunburst":
            fig = px.sunburst(df[mask], names='item', parents='parent', values='value',
                              title=title + subtitle)
            fig.show()
            self.helper_export_html(fig)
        if chart == "treemap":
            fig = px.treemap(df[mask], names='item', parents='parent', values='value',
                             title=title + subtitle)
            fig.show()
            self.helper_export_html(fig)

    # ATTRIBUTES CHARTS SECTION
    def fill_combobox_attributes(self):
        """ Fill attributes if case or file is selected.
            attribute keys = name, memo, caseOrFile, valuetype
        """

        list_char = [""]
        list_num = [""]
        if self.ui.radioButton_file.isChecked():
            for a in self.attributes:
                if a['caseOrFile'] == "file" and a['valuetype'] == "character":
                    list_char.append(a['name'])
                if a['caseOrFile'] == "file" and a['valuetype'] == "numeric":
                    list_num.append(a['name'])
        else:
            for a in self.attributes:
                if a['caseOrFile'] == "case" and a['valuetype'] == "character":
                    list_char.append(a['name'])
                if a['caseOrFile'] == "case" and a['valuetype'] == "numeric":
                    list_num.append(a['name'])
        self.ui.comboBox_num_attributes.blockSignals(True)
        self.ui.comboBox_char_attributes.blockSignals(True)
        self.ui.comboBox_num_attributes.clear()
        self.ui.comboBox_char_attributes.clear()
        self.ui.comboBox_char_attributes.addItems(list_char)
        self.ui.comboBox_num_attributes.addItems(list_num)
        self.ui.comboBox_num_attributes.blockSignals(False)
        self.ui.comboBox_char_attributes.blockSignals(False)

    def character_attribute_charts(self):
        """ Character attributes are displayed as counts via bar charts. """

        file_or_case = "case"
        if self.ui.radioButton_file.isChecked():
            file_or_case = "file"
        attribute = self.ui.comboBox_char_attributes.currentText()
        title = _("Attribute bar chart")
        subtitle = "<br><sup>" + _(file_or_case) + _(" attribute: ") + attribute
        self.ui.comboBox_char_attributes.blockSignals(True)
        self.ui.comboBox_char_attributes.setCurrentIndex(0)
        self.ui.comboBox_char_attributes.blockSignals(False)

        cur = self.app.conn.cursor()
        cur.execute(
            "select value, count(value) from attribute where attr_type=? and name=? group by value order by upper(value)",
            [file_or_case, attribute])
        res = cur.fetchall()
        labels = []
        values = []
        for r in res:
            labels.append(r[0])
            values.append(r[1])
        # Create pandas DataFrame
        data = {'Value': labels, 'Count': values}
        df = pd.DataFrame(data)
        fig = px.bar(df, x='Count', y='Value', orientation='h', title=title + subtitle)
        fig.show()
        self.helper_export_html(fig)

    def numeric_attribute_charts(self):
        """ Character attributes are displayed as boxplot charts. """

        file_or_case = "case"
        if self.ui.radioButton_file.isChecked():
            file_or_case = "file"
        attribute = self.ui.comboBox_num_attributes.currentText()
        title = _("Attribute histogram")
        subtitle = "<br><sup>" + _(file_or_case) + _(" attribute: ") + attribute
        self.ui.comboBox_num_attributes.blockSignals(True)
        self.ui.comboBox_num_attributes.setCurrentIndex(0)
        self.ui.comboBox_num_attributes.blockSignals(False)

        cur = self.app.conn.cursor()
        cur.execute("select cast(value as int) from attribute where attr_type=? and name=?",
                    [file_or_case, attribute])
        res = cur.fetchall()
        values = []
        for r in res:
            values.append(r[0])
        # Create pandas DataFrame
        data = {attribute: values}
        df = pd.DataFrame(data)
        fig = px.histogram(df, x=attribute, title=title + subtitle)
        fig.show()
        self.helper_export_html(fig)

    # HEATMAP CHARTS SECTION
    def heatmap_counter_by_file_and_code(self, owner, fid, cid):
        """ Get count of codings for this code and this file.
         Use spinbox_count_max to limit maximum counts for codes.
         This is to allow a wider spread of head map colours when there are extreme count differences.
         """

        max_count = int(self.ui.lineEdit_count_limiter.text())
        count = 0
        cur = self.app.conn.cursor()
        sql_t = "select count(cid) from code_text where owner like ? and cid=? and fid=?"
        cur.execute(sql_t, [owner, cid, fid])
        result_t = cur.fetchone()
        if result_t is not None:
            count += result_t[0]
        sql_i = "select count(cid) from code_image where owner like ? and cid=? and id=?"
        cur.execute(sql_i, [owner, cid, fid])
        result_i = cur.fetchone()
        if result_i is not None:
            count += result_i[0]
        sql_av = "select count(cid) from code_av where owner like ? and cid=? and id=?"
        cur.execute(sql_av, [owner, cid, fid])
        result_av = cur.fetchone()
        if result_av is not None:
            count += result_av[0]
        if 0 < max_count < count:
            count = max_count
        return count

    def make_heatmap(self):
        """ Make a heat map based on cases or files.
        Use code count as the basic unit of measurement.
        Filters: Coder, selected category.
        Exclude from filters: Count; selected file; selected case
        TODO include in filters: Selected Attributes for Cases - uses attribute_file_ids and attributes_msg
        """

        self.get_selected_categories_and_codes()
        codes = deepcopy(self.codes)
        if len(codes) > 40:
            codes = codes[:40]
            Message(self.app, _("Too many codes"), _("Too many codes for display. Restricted to 40")).exec()
        # Filters
        heatmap_type = self.ui.comboBox_heatmap.currentText()
        if heatmap_type == "":
            return
        title = heatmap_type + " " + _("Heatmap")
        self.get_selected_categories_and_codes()
        y_labels = []
        for c in codes:
            y_labels.append(c['name'])
        category = self.ui.comboBox_category.currentText()
        self.ui.lineEdit_filter.setText("")
        self.ui.comboBox_case.setCurrentIndex(0)
        self.ui.comboBox_file.setCurrentIndex(0)
        owner, subtitle = self.owner_and_subtitle_helper()

        # Get all the coded data
        data = []
        x_labels = []
        cur = self.app.conn.cursor()
        if heatmap_type == "File":
            if not self.attribute_file_ids:
                sql = "select id, name from source order by name"
                cur.execute(sql)
                files = cur.fetchall()
            else:
                attr_msg, file_ids_txt = self.get_file_ids()
                sql = "select id, name from source where id " + file_ids_txt + " order by name"
                cur.execute(sql)
                files = cur.fetchall()
            if len(files) > 40:
                files = files[:40]
                Message(self.app, _("Too many files"), _("Too many files for display. Restricted to 40")).exec()
            for file_ in files:
                x_labels.append(file_[1])
            # Calculate the frequency of each code in each file
            # Each row is a code, each column is a file
            for code_ in codes:
                code_counts = []
                for file_ in files:
                    code_counts.append(self.heatmap_counter_by_file_and_code(owner, file_[0], code_['cid']))
                data.append(code_counts)
        if heatmap_type == "Case":
            if not self.attribute_case_ids_and_names:  # self.attribute_file_ids:
                sql = "select caseid, name from cases order by name"
                cur.execute(sql)
                cases = cur.fetchall()
                if len(cases) > 40:
                    cases = cases[:40]
                    Message(self.app, _("Too many cases"), _("Too many cases for display. Restricted to 40")).exec()
                for c in cases:
                    x_labels.append(c[1])
                # Calculate the frequency of each code in each file
                # Each row is a code, each column is a file
                for code_ in codes:
                    code_counts = []
                    for c in cases:
                        cur.execute("SELECT fid FROM case_text where caseid=?", [c[0]])
                        fids = cur.fetchall()
                        case_counts = 0
                        for fid in fids:
                            case_counts += self.heatmap_counter_by_file_and_code(owner, fid[0], code_['cid'])
                        code_counts.append(case_counts)
                    data.append(code_counts)
            else:
                attr_msg, file_ids_txt = self.get_file_ids()
                print(self.attribute_case_ids_and_names)
                for c in self.attribute_case_ids_and_names:
                    x_labels.append(c[1])
                # Calculate the frequency of each code in each file
                # Each row is a code, each column is a file
                for code_ in codes:
                    code_counts = []
                    for c in self.attribute_case_ids_and_names:
                        cur.execute("SELECT fid FROM case_text where caseid=?", [c[0]])
                        fids = cur.fetchall()
                        case_counts = 0
                        for fid in fids:
                            case_counts += self.heatmap_counter_by_file_and_code(owner, fid[0], code_['cid'])
                        code_counts.append(case_counts)
                    data.append(code_counts)
        # Create the plot
        fig = px.imshow(data,
                        labels=dict(x=heatmap_type, y="Codes", color="Count"),
                        x=x_labels,
                        y=y_labels,
                        title=title + subtitle
                        )
        fig.update_xaxes(side="top")
        fig.show()
        self.helper_export_html(fig)
        self.ui.comboBox_heatmap.blockSignals(True)
        self.ui.comboBox_heatmap.setCurrentIndex(0)
        self.ui.comboBox_heatmap.blockSignals(False)
