# -*- coding: utf-8 -*-

"""
Copyright (c) 2022 Colin Curtain

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
"""

from copy import copy
import logging
import os
import pandas as pd
import plotly.express as px
import sys
import traceback

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtWidgets import QDialog

from .GUI.ui_dialog_charts import Ui_DialogCharts

# from .helpers import Message

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    txt = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(txt)
    logger.error(_("Uncaught exception: ") + txt)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 12pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(txt)
    mb.exec()


class ViewCharts(QDialog):
    """ Dialog to view various charts of codes and categories.
    """

    app = None
    conn = None
    settings = None
    categories = []
    code_names = []
    dialog_list = []

    def __init__(self, app):
        """ Set up the dialog. """

        sys.excepthook = exception_handler
        QDialog.__init__(self)
        self.app = app
        self.settings = app.settings
        self.conn = app.conn
        # Set up the user interface from Designer.
        self.ui = Ui_DialogCharts()
        self.ui.setupUi(self)
        integers = QtGui.QIntValidator()
        self.ui.lineEdit_filter.setValidator(integers)

        # Temporary hide widgets
        self.ui.label_tree.hide()
        self.ui.comboBox_tree_charts.hide()
        self.ui.label_select_case.hide()
        self.ui.comboBox_case.hide()
        self.ui.label_select_file.hide()
        self.ui.comboBox_file.hide()
        self.ui.pushButton_attributes.hide()
        # Very temp:
        self.ui.label_coder.hide()
        self.ui.comboBox_coders.hide()

        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)

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
        self.code_names, self.categories = app.get_codes_categories()
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

    def show_bar_chart(self):
        """ https://www.tutorialspoint.com/plotly/plotly_bar_and_pie_chart.htm
        """

        chart_type = self.ui.comboBox_bar_charts.currentText()
        if chart_type == "":
            return
        if chart_type == "Code frequency":
            self.barchart_code_frequency()
        if chart_type == "Code by characters":
            self.barchart_code_volume_by_characters()
        if chart_type == "Code by image area":
            self.barchart_code_volume_by_area()
        if chart_type == "Code by audio/video segments":
            self.barchart_code_volume_by_segments()
        self.ui.comboBox_bar_charts.setCurrentIndex(0)

    def barchart_code_frequency(self):
        """ Count of codes across text, images and A/V.
        """

        cur = self.app.conn.cursor()
        values = []
        labels = []
        for c in self.code_names:
            sql = "select count(cid) from code_text where cid=?"
            cur.execute(sql, [c['cid']])
            res_text = cur.fetchone()
            sql = "select count(cid) from code_image where cid=?"
            cur.execute(sql, [c['cid']])
            res_image = cur.fetchone()
            sql = "select count(cid) from code_av where cid=?"
            cur.execute(sql, [c['cid']])
            res_av = cur.fetchone()
            labels.append(c['name'])
            values.append(res_text[0] + res_image[0] + res_av[0])
        title = _('Code count - text, images and Audio/Video')
        # Create pandas DataFrame
        data = {'Code names': labels, 'Count': values}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['Count'] != 0
        if cutoff != "":
            mask = df['Count'] >= int(cutoff)
            title += "<br><sup>" + _("Values") + " >= " + cutoff + "<sup>"
        fig = px.bar(df[mask], y='Code names', x='Count', orientation='h', title=title)
        fig.show()

    def barchart_code_volume_by_characters(self):
        """ Count of codes in files text by character volume. """

        cur = self.app.conn.cursor()
        values = []
        labels = []
        for c in self.code_names:
            sql = "select sum(pos1 - pos0) from code_text where cid=?"
            cur.execute(sql, [c['cid']])
            res = cur.fetchone()
            labels.append(c['name'])
            values.append(res[0])
        title = _('Code text by character count')
        # Create pandas DataFrame
        data = {'Code names': labels, 'Total characters': values}
        df = pd.DataFrame(data)
        mask = df['Total characters'] != 0
        cutoff = self.ui.lineEdit_filter.text()
        if cutoff != "":
            mask = df['Total characters'] >= int(cutoff)
            title += "<br><sup>" + _("Values") + " >= " + cutoff + "<sup>"
        fig = px.bar(df[mask], x='Total characters', y='Code names', orientation='h', title=title)
        fig.show()

    def barchart_code_volume_by_area(self):
        """ Codes by image area volume. """

        cur = self.app.conn.cursor()
        values = []
        labels = []
        for c in self.code_names:
            sql = "select sum(cast(width as int) * cast(height as int)) from code_image where cid=?"
            cur.execute(sql, [c['cid']])
            res = cur.fetchone()
            labels.append(c['name'])
            values.append(res[0])
        title = _('Code volume by image area (pixels)')
        # Create pandas DataFrame
        data = {'Code names': labels, 'Pixels': values}
        df = pd.DataFrame(data)
        mask = df['Pixels'] != 0
        cutoff = self.ui.lineEdit_filter.text()
        if cutoff != "":
            mask = df['Pixels'] >= int(cutoff)
            title += "<br><sup>" + _("Values") + " >= " + cutoff + "<sup>"
        fig = px.bar(df[mask], x='Pixels', y='Code names', orientation='h', title=title)
        fig.show()

    def barchart_code_volume_by_segments(self):
        """ Codes by audio/video segment volume. """

        cur = self.app.conn.cursor()
        values = []
        labels = []
        for c in self.code_names:
            sql = "select sum(pos1 - pos0) from code_av where cid=?"
            cur.execute(sql, [c['cid']])
            res = cur.fetchone()
            labels.append(c['name'])
            values.append(res[0])
        title = _('Code volume by audio/video segments (milliseconds)')
        # Create pandas DataFrame
        data = {'Code names': labels, 'Total millisecs': values}
        df = pd.DataFrame(data)
        mask = df['Total millisecs'] != 0
        cutoff = self.ui.lineEdit_filter.text()
        if cutoff != "":
            mask = df['Total millisecs'] >= int(cutoff)
            title += "<br><sup>" + _("Values") + " >= " + cutoff + "<sup>"
        fig = px.bar(df[mask], x='Total millisecs', y='Code names', orientation='h', title=title)
        fig.show()

    def show_pie_chart(self):
        """
        https://plotly.com/python/pie-charts/
        https://www.tutorialspoint.com/plotly/plotly_bar_and_pie_chart.htm
        """

        chart_type = self.ui.comboBox_pie_charts.currentText()
        if chart_type == "":
            return

        if chart_type == "Code frequency":
            self.piechart_code_frequency()
        if chart_type == "Code by characters":
            self.piechart_code_volume_by_characters()
        if chart_type == "Code by image area":
            self.piechart_code_volume_by_area()
        if chart_type == "Code by audio/video segments":
            self.piechart_code_volume_by_segments()
        self.ui.comboBox_pie_charts.setCurrentIndex(0)

    def piechart_code_frequency(self):
        """ Count of codes across text, images and A/V.
        """

        cur = self.app.conn.cursor()
        values = []
        labels = []
        for c in self.code_names:
            sql = "select count(cid) from code_text where cid=?"
            cur.execute(sql, [c['cid']])
            res_text = cur.fetchone()
            sql = "select count(cid) from code_image where cid=?"
            cur.execute(sql, [c['cid']])
            res_image = cur.fetchone()
            sql = "select count(cid) from code_av where cid=?"
            cur.execute(sql, [c['cid']])
            res_av = cur.fetchone()
            labels.append(c['name'])
            values.append(res_text[0] + res_image[0] + res_av[0])
        title = _('Code count - text, images and Audio/Video')
        # Create pandas DataFrame
        data = {'Code names': labels, 'Count': values}
        df = pd.DataFrame(data)
        mask = df['Count'] != 0
        cutoff = self.ui.lineEdit_filter.text()
        if cutoff != "":
            mask = df['Count'] >= int(cutoff)
            title += "<br><sup>" + _("Values") + " >= " + cutoff + "<sup>"
        fig = px.pie(df[mask], values='Count', names='Code names', title=title)
        fig.show()

    def piechart_code_volume_by_characters(self):
        """ Count of codes in files text by character volume. """

        cur = self.app.conn.cursor()
        values = []
        labels = []
        for c in self.code_names:
            sql = "select sum(pos1 - pos0) from code_text where cid=?"
            cur.execute(sql, [c['cid']])
            res = cur.fetchone()
            labels.append(c['name'])
            values.append(res[0])
        title = _('Code text by character count')
        # Create pandas DataFrame
        data = {'Code names': labels, 'Total characters': values}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['Total characters'] != 0
        if cutoff != "":
            mask = df['Total characters'] >= int(cutoff)
            title += "<br><sup>" + _("Values") + " >= " + cutoff + "<sup>"
        fig = px.pie(df[mask], values='Total characters', names='Code names', title=title)
        fig.show()

    def piechart_code_volume_by_area(self):
        """ Codes by image area volume. """

        cur = self.app.conn.cursor()
        values = []
        labels = []
        for c in self.code_names:
            sql = "select sum(cast(width as int) * cast(height as int)) from code_image where cid=?"
            cur.execute(sql, [c['cid']])
            res = cur.fetchone()
            labels.append(c['name'])
            values.append(res[0])
        title = _('Code volume by image area (pixels)')
        # Create pandas DataFrame
        data = {'Code names': labels, 'Total pixels': values}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['Total pixels'] != 0
        if cutoff != "":
            mask = df['Total pixels'] >= int(cutoff)
            title += "<br><sup>" + _("Values") + " >= " + cutoff + "<sup>"
        fig = px.pie(df[mask], values='Total pixels', names='Code names', title=title)
        fig.show()

    def piechart_code_volume_by_segments(self):
        """ Codes by audio/video segment volume. """

        cur = self.app.conn.cursor()
        values = []
        labels = []
        for c in self.code_names:
            sql = "select sum(pos1 - pos0) from code_av where cid=?"
            cur.execute(sql, [c['cid']])
            res = cur.fetchone()
            labels.append(c['name'])
            values.append(res[0])
        title = _('Code volume by audio/video segments (milliseconds)')
        # Create pandas DataFrame
        data = {'Code names': labels, 'Total millisecs': values}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['Total millisecs'] != 0
        if cutoff != "":
            mask = df['Total millisecs'] >= int(cutoff)
            title += "<br><sup>" + _("Values") + " >= " + cutoff + "<sup>"
        fig = px.pie(df[mask], values='Total millisecs', names='Code names', title=title)
        fig.show()

    def show_hierarchy_chart(self):
        """
        https://plotly.com/python/sunburst-charts/
        """

        chart_type = self.ui.comboBox_sunburst_charts.currentText()
        if chart_type == "":
            return
        if chart_type == "Code frequency sunburst":
            self.hierarchy_code_frequency("sunburst")
        if chart_type == "Code frequency treemap":
            self.hierarchy_code_frequency("treemap")
        if chart_type == "Code by characters sunburst":
            self.hierarchy_code_volume_by_characters("sunburst")
        if chart_type == "Code by characters treemap":
            self.hierarchy_code_volume_by_characters("treemap")
        if chart_type == "Code by image area sunburst":
            self.hierarchy_code_volume_by_area("sunburst")
        if chart_type == "Code by image area treemap":
            self.hierarchy_code_volume_by_area("treemap")
        if chart_type == "Code by A/V sunburst":
            self.hierarchy_code_volume_by_segments("sunburst")
        if chart_type == "Code by A/V treemap":
            self.hierarchy_code_volume_by_segments("treemap")
        self.ui.comboBox_sunburst_charts.setCurrentIndex(0)

    def hierarchy_code_frequency(self, chart="sunburst"):
        """ Count of codes across text, images and A/V.
        Calculates code count and category count and displays in sunburst or treemap chart.
        """

        # Get categories nd codes as dictionaries with a count key and parentname key
        cur = self.app.conn.cursor()
        sb_categories = []
        cur.execute("select name, catid, owner, supercatid from code_cat order by lower(name)")
        result = cur.fetchall()
        for row in result:
            sb_categories.append({'name': row[0], 'catid': row[1], 'owner': row[2],
                                  'supercatid': row[3],
                                  'count': 0, 'parentname': ""})
        sb_codes = []
        cur.execute("select name, owner, cid, catid, color from code_name order by lower(name)")
        result = cur.fetchall()
        for row in result:
            sb_codes.append({'name': row[0], 'owner': row[1],
                             'cid': row[2], 'catid': row[3], 'color': row[4],
                             'count': 0, 'parentname': ""})
        # Get all the coded data
        self.file_ids = []  # temp to resolve later
        sb_coded_data = []
        if True:
            cur.execute("select cid, owner, fid from code_text")
            result = cur.fetchall()
            for row in result:
                if row[2] in self.file_ids or self.file_ids == []:
                    sb_coded_data.append(row)
            cur.execute("select cid, owner, id from code_image")
            result = cur.fetchall()
            for row in result:
                if row[2] in self.file_ids or self.file_ids == []:
                    sb_coded_data.append(row)
            cur.execute("select cid, owner, id from code_av")
            result = cur.fetchall()
            for row in result:
                if row[2] in self.file_ids or self.file_ids == []:
                    sb_coded_data.append(row)
        # Calculate the frequency of each code
        for code_ in sb_codes:
            for coded_item in sb_coded_data:
                if coded_item[0] == code_['cid']:
                    code_['count'] += 1
        # Add the code count directly to each parent category, add parentname to each code
        for category in sb_categories:
            for code_ in sb_codes:
                if code_['catid'] == category['catid']:
                    category['count'] += code_['count']
                    code_['parentname'] = category['name']
        # Find leaf categories, add to parent categories, and gradually remove leaves
        # Until only top categories remain
        sub_categories = copy(sb_categories)
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
                for cat in sb_categories:
                    if cat['catid'] == leaf_category['supercatid']:
                        cat['count'] += leaf_category['count']
                sub_categories.remove(leaf_category)
            counter += 1
        combined = sb_categories + sb_codes
        items = []
        values = []
        parents = []
        for sb_combined in combined:
            items.append(sb_combined['name'])
            values.append(sb_combined['count'])
            parents.append(sb_combined['parentname'])
        # data = dict(item=items, value=values, parent=parents) # OLDER
        # Create pandas DataFrame
        data = {'item': items, 'value': values, 'parent': parents}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['value'] != 0
        subtitle = ""
        if cutoff != "":
            mask = df['value'] >= int(cutoff)
            subtitle += "<br><sup>" + _("Values") + " >= " + cutoff + "<sup>"
        if chart == "sunburst":
            fig = px.sunburst(df[mask], names='item', parents='parent', values='value',
                              title=_('Sunburst chart of counts of codes and categories') + subtitle)
            fig.show()
        if chart == "treemap":
            fig = px.treemap(df[mask], names='item', parents='parent', values='value',
                             title=_('Treemap of counts of codes and categories') + subtitle)
            fig.show()

    def hierarchy_code_volume_by_characters(self, chart="sunburst"):
        """ Count of code characters across text files.
            Calculates code count and category count and displays in sunburst or treemap chart.
        """

        # Get categories nd codes as dictionaries with a count key and parentname key
        cur = self.app.conn.cursor()
        sb_categories = []
        cur.execute("select name, catid, owner, supercatid from code_cat order by lower(name)")
        result = cur.fetchall()
        for row in result:
            sb_categories.append({'name': row[0], 'catid': row[1], 'owner': row[2],
                                  'supercatid': row[3],
                                  'count': 0, 'parentname': ""})
        sb_codes = []
        cur.execute("select name, owner, cid, catid, color from code_name order by lower(name)")
        result = cur.fetchall()
        for row in result:
            sb_codes.append({'name': row[0], 'owner': row[1],
                             'cid': row[2], 'catid': row[3], 'color': row[4],
                             'count': 0, 'parentname': ""})
        # Get all the coded data
        self.file_ids = []  # temp to resolve later
        sb_coded_data = []
        if True:
            cur.execute("select cid, owner, fid, pos1-pos0 from code_text")
            result = cur.fetchall()
            for row in result:
                if row[2] in self.file_ids or self.file_ids == []:
                    sb_coded_data.append(row)
        # Calculate the frequency of each code
        for code_ in sb_codes:
            for coded_item in sb_coded_data:
                if coded_item[0] == code_['cid']:
                    code_['count'] += coded_item[3]
        # Add the code count directly to each parent category, add parentname to each code
        for category in sb_categories:
            for code_ in sb_codes:
                if code_['catid'] == category['catid']:
                    category['count'] += code_['count']
                    code_['parentname'] = category['name']
        # Find leaf categories, add to parent categories, and gradually remove leaves
        # Until only top categories remain
        sub_categories = copy(sb_categories)
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
                for cat in sb_categories:
                    if cat['catid'] == leaf_category['supercatid']:
                        cat['count'] += leaf_category['count']
                sub_categories.remove(leaf_category)
            counter += 1
        combined = sb_categories + sb_codes
        items = []
        values = []
        parents = []
        for sb_combined in combined:
            items.append(sb_combined['name'])
            values.append(sb_combined['count'])
            parents.append(sb_combined['parentname'])
        #data = dict(item=items, value=values, parent=parents)  # OLDER
        # Create pandas DataFrame
        data = {'item': items, 'value': values, 'parent': parents}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['value'] != 0
        subtitle = ""
        if cutoff != "":
            mask = df['value'] >= int(cutoff)
            subtitle += "<br><sup>" + _("Values") + " >= " + cutoff + "<sup>"
        if chart == "sunburst":
            fig = px.sunburst(df[mask], names='item', parents='parent', values='value',
                              title=_('Sunburst chart of coded text - characters') + subtitle)
            fig.show()
        if chart == "treemap":
            fig = px.treemap(df[mask], names='item', parents='parent', values='value',
                             title=_('Treemap of coded text - characters') + subtitle)
            fig.show()

    def hierarchy_code_volume_by_area(self, chart="sunburst"):
        """ Count of coded image areas across image files.
            Displays in sunburst or treemap chart.
        """

        # Get categories nd codes as dictionaries with a count key and parentname key
        cur = self.app.conn.cursor()
        sb_categories = []
        cur.execute("select name, catid, owner, supercatid from code_cat order by lower(name)")
        result = cur.fetchall()
        for row in result:
            sb_categories.append({'name': row[0], 'catid': row[1], 'owner': row[2],
                                  'supercatid': row[3],
                                  'count': 0, 'parentname': ""})
        sb_codes = []
        cur.execute("select name, owner, cid, catid, color from code_name order by lower(name)")
        result = cur.fetchall()
        for row in result:
            sb_codes.append({'name': row[0], 'owner': row[1],
                             'cid': row[2], 'catid': row[3], 'color': row[4],
                             'count': 0, 'parentname': ""})
        # Get all the coded data
        self.file_ids = []  # temp to resolve later
        sb_coded_data = []
        if True:
            cur.execute("select cid, owner, id, cast(width as int) * cast(height as int) from code_image")
            result = cur.fetchall()
            for row in result:
                if row[2] in self.file_ids or self.file_ids == []:
                    sb_coded_data.append(row)
        # Calculate the frequency of each code
        for code_ in sb_codes:
            for coded_item in sb_coded_data:
                if coded_item[0] == code_['cid']:
                    code_['count'] += coded_item[3]
        # Add the code count directly to each parent category, add parentname to each code
        for category in sb_categories:
            for code_ in sb_codes:
                if code_['catid'] == category['catid']:
                    category['count'] += code_['count']
                    code_['parentname'] = category['name']
        # Find leaf categories, add to parent categories, and gradually remove leaves
        # Until only top categories remain
        sub_categories = copy(sb_categories)
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
                for cat in sb_categories:
                    if cat['catid'] == leaf_category['supercatid']:
                        cat['count'] += leaf_category['count']
                sub_categories.remove(leaf_category)
            counter += 1
        combined = sb_categories + sb_codes
        items = []
        values = []
        parents = []
        for sb_combined in combined:
            items.append(sb_combined['name'])
            values.append(sb_combined['count'])
            parents.append(sb_combined['parentname'])
        #data = dict(item=items, value=values, parent=parents)# OLDER
        # Create pandas DataFrame
        data = {'item': items, 'value': values, 'parent': parents}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['value'] != 0
        subtitle = ""
        if cutoff != "":
            mask = df['value'] >= int(cutoff)
            subtitle += "<br><sup>" + _("Values") + " >= " + cutoff + "<sup>"
        if chart == "sunburst":
            fig = px.sunburst(df[mask], names='item', parents='parent', values='value',
                              title=_('Sunburst chart of coded image areas - pixels') + subtitle)
            fig.show()
        if chart == "treemap":
            fig = px.treemap(df[mask], names='item', parents='parent', values='value',
                             title=_('Treemap of coded image areas - pixels') + subtitle)
            fig.show()

    def hierarchy_code_volume_by_segments(self, chart="sunburst"):
        """ Count of codes segment durations across audio/video files.
            Displays in sunburst or treemap chart.
        """

        # Get categories nd codes as dictionaries with a count key and parentname key
        cur = self.app.conn.cursor()
        sb_categories = []
        cur.execute("select name, catid, owner, supercatid from code_cat order by lower(name)")
        result = cur.fetchall()
        for row in result:
            sb_categories.append({'name': row[0], 'catid': row[1], 'owner': row[2],
                                  'supercatid': row[3],
                                  'count': 0, 'parentname': ""})
        sb_codes = []
        cur.execute("select name, owner, cid, catid, color from code_name order by lower(name)")
        result = cur.fetchall()
        for row in result:
            sb_codes.append({'name': row[0], 'owner': row[1],
                             'cid': row[2], 'catid': row[3], 'color': row[4],
                             'count': 0, 'parentname': ""})
        # Get all the coded data
        self.file_ids = []  # temp to resolve later
        sb_coded_data = []
        if True:
            cur.execute("select cid, owner, id, pos1-pos0 from code_av")
            result = cur.fetchall()
            for row in result:
                if row[2] in self.file_ids or self.file_ids == []:
                    sb_coded_data.append(row)
        # Calculate the frequency of each code
        for code_ in sb_codes:
            for coded_item in sb_coded_data:
                if coded_item[0] == code_['cid']:
                    code_['count'] += coded_item[3]
        # Add the code count directly to each parent category, add parentname to each code
        for category in sb_categories:
            for code_ in sb_codes:
                if code_['catid'] == category['catid']:
                    category['count'] += code_['count']
                    code_['parentname'] = category['name']
        # Find leaf categories, add to parent categories, and gradually remove leaves
        # Until only top categories remain
        sub_categories = copy(sb_categories)
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
                for cat in sb_categories:
                    if cat['catid'] == leaf_category['supercatid']:
                        cat['count'] += leaf_category['count']
                sub_categories.remove(leaf_category)
            counter += 1
        combined = sb_categories + sb_codes
        items = []
        values = []
        parents = []
        for sb_combined in combined:
            items.append(sb_combined['name'])
            values.append(sb_combined['count'])
            parents.append(sb_combined['parentname'])
        #data = dict(item=items, value=values, parent=parents)  # older
        # Create pandas DataFrame
        data = {'item': items, 'value': values, 'parent': parents}
        df = pd.DataFrame(data)
        cutoff = self.ui.lineEdit_filter.text()
        mask = df['value'] != 0
        subtitle = ""
        if cutoff != "":
            mask = df['value'] >= int(cutoff)
            subtitle += "<br><sup>" + _("Values") + " >= " + cutoff + "<sup>"
        if chart == "sunburst":
            fig = px.sunburst(df[mask], names='item', parents='parent', values='value',
                              title=_('Sunburst chart of coded audio/video segments - milliseconds') + subtitle)
            fig.show()
        if chart == "treemap":
            fig = px.treemap(df[mask], names='item', parents='parent', values='value',
                             title=_('Treemap of coded image audio/video segments - milliseconds') + subtitle)
            fig.show()
