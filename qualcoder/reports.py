# -*- coding: utf-8 -*-

"""
Copyright (c) 2020 Colin Curtain

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
import csv
import datetime
import logging
import os
import platform
from shutil import copyfile
import sys
import traceback
import vlc

from PyQt5 import QtGui, QtWidgets, QtCore
from PyQt5.Qt import QHelpEvent
from PyQt5.QtCore import Qt, QTextCodec
from PyQt5.QtGui import QBrush

from GUI.base64_helper import *
from GUI.ui_dialog_report_codings import Ui_Dialog_reportCodings
from GUI.ui_dialog_report_comparisons import Ui_Dialog_reportComparisons
from GUI.ui_dialog_report_code_frequencies import Ui_Dialog_reportCodeFrequencies
#from GUI.ui_dialog_code_context_image import Ui_Dialog_code_context_image

from helpers import Message, msecs_to_mins_and_secs, DialogCodeInImage, DialogCodeInAV, DialogCodeInText
from report_attributes import DialogSelectAttributeParameters
from select_items import DialogSelectItems

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception: ") + text)
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), text)


class DialogReportCodeFrequencies(QtWidgets.QDialog):
    """ Show code and category frequencies, overall and for each coder.
    This is for text, image and av coding. """

    app = None
    parent_textEdit = None
    coders = []
    categories = []
    codes = []
    coded = []  # to refactor name
    file_ids = []

    def __init__(self, app, parent_textEdit):

        sys.excepthook = exception_handler
        self.app = app
        self.parent_textEdit = parent_textEdit
        self.get_data()
        self.calculate_code_frequencies()
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_reportCodeFrequencies()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        self.ui.pushButton_exporttext.pressed.connect(self.export_text_file)
        #icon = QtGui.QIcon(QtGui.QPixmap('GUI/doc_export_icon.png'))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(doc_export_icon), "png")
        self.ui.pushButton_exporttext.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_exportcsv.pressed.connect(self.export_csv_file)
        #icon = QtGui.QIcon(QtGui.QPixmap('GUI/doc_export_csv_icon.png'))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(doc_export_csv_icon), "png")
        self.ui.pushButton_exportcsv.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_select_files.pressed.connect(self.select_files)

        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        font = 'font: ' + str(self.app.settings['treefontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.ui.treeWidget.setStyleSheet(font)
        self.ui.treeWidget.setSelectionMode(QtWidgets.QTreeWidget.ExtendedSelection)
        self.fill_tree()

    def select_files(self):
        """ Report code frequencies for all files or selected files. """

        filenames = self.app.get_filenames()
        if len(filenames) == 0:
            return
        ui = DialogSelectItems(self.app, filenames, _("Select files to view"), "many")
        ok = ui.exec_()
        tooltip = _("Files selected: ")
        self.file_ids = []
        if ok:
            selected_files = ui.get_selected()  # list of dictionaries
            files_text = ""
            for row in selected_files:
                self.file_ids.append(row['id'])
                files_text += "\n" + row['name']
            files_text = files_text[2:]
            tooltip += files_text
            if len(self.file_ids) > 0:
                self.ui.pushButton_select_files.setToolTip(tooltip)
        self.get_data()
        self.calculate_code_frequencies()
        self.fill_tree()

    def get_data(self):
        """ Called from init. gets coders, code_names and categories.
        Calls calculate_code_frequency - for each code.
        Adds a list item that is ready to be used by the treeWidget to display multiple
        columns with the coder frequencies.
        Not using  app.get_data method as this adds extra columns for each end user
        """

        cur = self.app.conn.cursor()
        self.categories = []
        cur.execute("select name, catid, owner, date, memo, supercatid from code_cat order by lower(name)")
        result = cur.fetchall()
        for row in result:
            self.categories.append({'name': row[0], 'catid': row[1], 'owner': row[2],
            'date': row[3], 'memo': row[4], 'supercatid': row[5],
            'display_list': [row[0], 'catid:' + str(row[1])]})
        self.codes = []
        cur.execute("select name, memo, owner, date, cid, catid, color from code_name order by lower(name)")
        result = cur.fetchall()
        for row in result:
            self.codes.append({'name': row[0], 'memo': row[1], 'owner': row[2], 'date': row[3],
            'cid': row[4], 'catid': row[5], 'color': row[6],
            'display_list': [row[0], 'cid:' + str(row[4])]})

        self.coders = []
        cur.execute("select distinct owner from code_text union select distinct owner from code_image union select distinct owner from code_av")
        result = cur.fetchall()
        self.coders = []
        for row in result:
            self.coders.append(row[0])
        self.coded = []
        if True:
            cur.execute("select cid, owner, fid from code_text")
            result = cur.fetchall()
            for row in result:
                if row[2] in self.file_ids or self.file_ids == []:
                    self.coded.append(row)
            cur.execute("select cid, owner, id from code_image")
            result = cur.fetchall()
            for row in result:
                if row[2] in self.file_ids or self.file_ids == []:
                    self.coded.append(row)
            cur.execute("select cid, owner, id from code_av")
            result = cur.fetchall()
            for row in result:
                if row[2] in self.file_ids or self.file_ids == []:
                    self.coded.append(row)

    def calculate_code_frequencies(self):
        """ Calculate the frequency of each code for all coders and the total.
        Add a list item to each code that can be used to display in treeWidget.
        For codings in code_image, code_text.
        """

        for c in self.codes:
            total = 0
            for cn in self.coders:
                count = 0
                for cit in self.coded:
                    if cit[1] == cn and cit[0] == c['cid']:
                        count += 1
                        total += 1
                c['display_list'].append(count)
            c['display_list'].append(total)

        # add the number of codes directly under each category to the category
        for cat in self.categories:
            # magic 3 = cat name, cat id and total columns
            cat_list = [0] * (len(self.coders) + 3)
            for c in self.codes:
                if c['catid'] == cat['catid']:
                    for i in range(2, len(c['display_list'])):
                        cat_list[i] += c['display_list'][i]
            cat_list = cat_list[2:]
            for count in cat_list:
                cat['display_list'].append(count)

        # find leaf categories, add to above categories, and gradually remove leaves
        # until only top categories are left
        sub_cats = copy(self.categories)
        counter = 0
        while len(sub_cats) > 0 or counter < 10000:
            leaf_list = []
            branch_list = []
            for c in sub_cats:
                for c2 in sub_cats:
                    if c['catid'] == c2['supercatid']:
                        branch_list.append(c)
            for cat in sub_cats:
                if cat not in branch_list:
                    leaf_list.append(cat)
            # add totals for each coder and overall total to higher category
            for leaf_cat in leaf_list:
                for cat in self.categories:
                    if cat['catid'] == leaf_cat['supercatid']:
                        for i in range(2, len(cat['display_list'])):
                            cat['display_list'][i] += leaf_cat['display_list'][i]
                sub_cats.remove(leaf_cat)
            counter += 1

        # temp
        # header
        header = ["Code Tree", "Id"]
        for coder in self.coders:
            header.append(coder)
        header.append("Total")

    def depthgauge(self, item):
        """ Get depth for treewidget item. """

        depth = 0
        while item.parent() is not None:
            item = item.parent()
            depth += 1
        return depth

    def export_text_file(self):
        """ Export coding frequencies to text file. """

        shortname = self.app.project_name.split(".qda")[0]
        filename = shortname + " code frequencies.txt"
        options = QtWidgets.QFileDialog.DontResolveSymlinks | QtWidgets.QFileDialog.ShowDirsOnly
        directory = QtWidgets.QFileDialog.getExistingDirectory(None,
            _("Select directory to save file"), self.app.last_export_directory, options)
        if directory == "":
            return
        if directory != self.app.last_export_directory:
            self.app.last_export_directory = directory
        if os.path.exists(directory + "/" + filename):
            mb = QtWidgets.QMessageBox()
            mb.setWindowTitle(_("File exists"))
            mb.setText(_("Overwrite?"))
            mb.setStandardButtons(QtWidgets.QMessageBox.Yes|QtWidgets.QMessageBox.No)
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            if mb.exec_() == QtWidgets.QMessageBox.No:
                return
        filename = directory + "/" + filename
        f = open(filename, 'w')
        text = _("Code frequencies") + "\n"
        text += self.app.project_name + "\n"
        text += _("Date: ") + datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S") + "\n"

        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        item_total_position = 1 + len(self.coders)
        while item:
            self.depthgauge(item)
            cat = False
            if item.text(1).split(':')[0] == "catid":
                cat = True
            prefix = ""
            for i in range(0, self.depthgauge(item)):
                prefix += "--"
            if cat:
                text += "\n" + prefix + _("Category: ") + item.text(0)  # + ", " + item.text(1)
                text += ", Frequency: " + item.text(item_total_position)
            else:
                text += "\n" + prefix + _("Code: ") + item.text(0)  # + ", " + item.text(1)
                text += _(", Frequency: ") + item.text(item_total_position)
            it += 1
            item = it.value()
        f.write(text)
        f.close()
        Message(self.app, _('Text file Export'), filename + _(" exported")).exec_()
        self.parent_textEdit.append(_("Coding frequencies text file exported to: ") + filename)

    def export_csv_file(self):
        """ Export data as csv. """

        shortname = self.app.project_name.split(".qda")[0]
        filename = shortname + " code frequencies.csv"
        options = QtWidgets.QFileDialog.DontResolveSymlinks | QtWidgets.QFileDialog.ShowDirsOnly
        directory = QtWidgets.QFileDialog.getExistingDirectory(None,
            _("Select directory to save file"), self.app.last_export_directory, options)
        if directory == "":
            return
        if directory != self.app.last_export_directory:
            self.app.last_export_directory = directory
        filename = directory + "/" + filename
        if os.path.exists(filename):
            mb = QtWidgets.QMessageBox()
            mb.setWindowTitle(_("File exists"))
            mb.setText(_("Overwrite?"))
            mb.setStandardButtons(QtWidgets.QMessageBox.Yes|QtWidgets.QMessageBox.No)
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            if mb.exec_() == QtWidgets.QMessageBox.No:
                return
        data = ""
        header = [_("Code Tree"), "Id"]
        for coder in self.coders:
            header.append(coder)
        header.append("Total")
        data += ",".join(header) + "\n"

        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        item_total_position = 1 + len(self.coders)
        while item:
            line = ""
            for i in range(0, len(header)):
                line += "," + item.text(i)
            data += line[1:] + "\n"
            #self.depthgauge(item)
            it += 1
            item = it.value()
        f = open(filename, 'w')
        f.write(data)
        f.close()
        Message(self.app, _('Csv file Export'), filename + _(" exported")).exec_()
        self.parent_textEdit.append(_("Coding frequencies csv file exported to: ") + filename)

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes.
        """

        self.ui.treeWidget.clear()

        cats = copy(self.categories)
        codes = copy(self.codes)
        self.ui.treeWidget.clear()
        header = [_("Code Tree"), "Id"]
        for coder in self.coders:
            header.append(coder)
        header.append("Total")
        self.ui.treeWidget.setColumnCount(len(header))
        self.ui.treeWidget.setHeaderLabels(header)
        if self.app.settings['showids'] == 'False':
            self.ui.treeWidget.setColumnHidden(1, True)
        else:
            self.ui.treeWidget.setColumnHidden(1, False)
        self.ui.treeWidget.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.ui.treeWidget.header().setStretchLastSection(False)
        # add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                display_list = []
                for i in c['display_list']:
                    display_list.append(str(i))
                top_item = QtWidgets.QTreeWidgetItem(display_list)
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_list.append(c)
        for item in remove_list:
            #try:
            cats.remove(item)
            #except Exception as e:
            #    logger.debug(str(e) + " item:" + str(item))

        ''' Add child categories. Look at each unmatched category, iterate through tree to
        add as child then remove matched categories from the list. '''
        count = 0
        while len(cats) > 0 or count < 10000:
            remove_list = []
            #logger.debug("cats:" + str(cats))
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
                item = it.value()
                while item:  # while there is an item in the list
                    #logger.debug("While: ", item.text(0), item.text(1), c['catid'], c['supercatid'])
                    if item.text(1) == 'catid:' + str(c['supercatid']):
                        display_list = []
                        for i in c['display_list']:
                            display_list.append(str(i))
                        child = QtWidgets.QTreeWidgetItem(display_list)
                        item.addChild(child)
                        #logger.debug("Adding: " + c['name'])
                        remove_list.append(c)
                    it += 1
                    item = it.value()
            for item in remove_list:
                cats.remove(item)
            count += 1

        # add unlinked codes as top level items
        remove_items = []
        for c in codes:
            if c['catid'] is None:
                #logger.debug("c[catid] is None: new top item c[name]:" + c['name'])
                display_list = []
                for i in c['display_list']:
                    display_list.append(str(i))
                top_item = QtWidgets.QTreeWidgetItem(display_list)
                top_item.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.SolidPattern))
                top_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)

        # add codes as children
        for c in codes:
            it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
            item = it.value()
            while item:
                #logger.debug("for c in codes, item:" + item.text(0) +"|" + item.text(1) + ", c[cid]:" + str(c['cid']) +", c[catid]:" + str(c['catid']))
                if item.text(1) == 'catid:' + str(c['catid']):
                    display_list = []
                    for i in c['display_list']:
                        display_list.append(str(i))
                    child = QtWidgets.QTreeWidgetItem(display_list)
                    child.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.SolidPattern))
                    child.setFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                    item.addChild(child)
                    c['catid'] = -1  # make unmatchable
                it += 1
                item = it.value()
        self.ui.treeWidget.expandAll()


class DialogReportCoderComparisons(QtWidgets.QDialog):
    """ Compare coded text sequences between coders using Cohen's Kappa. """

    app = None
    parent_textEdit = None
    coders = []
    selected_coders = []
    categories = []
    code_names = []
    file_summaries = []
    comparisons = ""

    def __init__(self, app, parent_textEdit):

        sys.excepthook = exception_handler
        self.app = app
        self.parent_textEdit = parent_textEdit
        self.comparisons = ""
        self.get_data()
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_reportComparisons()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        self.ui.pushButton_run.setEnabled(False)
        self.ui.pushButton_run.pressed.connect(self.calculate_statistics)
        #icon = QtGui.QIcon(QtGui.QPixmap('GUI/cogs_icon.png'))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(cogs_icon), "png")
        self.ui.pushButton_run.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_clear.pressed.connect(self.clear_selection)
        #icon = QtGui.QIcon(QtGui.QPixmap('GUI/clear_icon.png'))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(clear_icon), "png")
        self.ui.pushButton_clear.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_exporttext.pressed.connect(self.export_text_file)
        #icon = QtGui.QIcon(QtGui.QPixmap('GUI/doc_export_icon.png'))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(doc_export_icon), "png")
        self.ui.pushButton_exporttext.setIcon(QtGui.QIcon(pm))
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        font = 'font: ' + str(self.app.settings['treefontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.ui.treeWidget.setStyleSheet(font)
        self.ui.treeWidget.setSelectionMode(QtWidgets.QTreeWidget.ExtendedSelection)
        self.ui.comboBox_coders.insertItems(0, self.coders)
        self.ui.comboBox_coders.currentTextChanged.connect(self.coder_selected)
        self.fill_tree()

    def get_data(self):
        """ Called from init. gets coders, code_names, categories, file_summaries.
        Images are not loaded. """

        self.code_names, self.categories = self.app.get_data()
        cur = self.app.conn.cursor()
        sql = "select owner from  code_image union select owner from code_text union select owner from code_av"
        cur.execute(sql)
        result = cur.fetchall()
        self.coders = [""]
        for row in result:
            self.coders.append(row[0])
        cur.execute('select id, length(fulltext) from source where (mediapath is Null or substr(mediapath,1,5)="docs:")')
        self.file_summaries = cur.fetchall()

    def coder_selected(self):
        """ Select coders for comparison - only two coders can be selected. """

        coder = self.ui.comboBox_coders.currentText()
        if coder == "":
            return
        if len(self.selected_coders) == 0:
            self.selected_coders.append(coder)
            self.ui.label_selections.setText(coder)
        if len(self.selected_coders) == 1 and self.selected_coders[0] != coder:
            self.selected_coders.append(coder)
            coder1 = self.ui.label_selections.text()
            self.ui.label_selections.setText(coder1 + " , " + coder)
        if len(self.selected_coders) == 2:
            self.ui.pushButton_run.setEnabled(True)

    def clear_selection(self):
        """ Clear the coder selection and tree widget statistics. """

        self.selected_coders = []
        self.ui.pushButton_run.setEnabled(False)
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        while item:  # while there is an item in the list
            if item.text(1)[0:4] == 'cid:':
                item.setText(2, "")
                item.setText(3, "")
                item.setText(4, "")
                item.setText(5, "")
                item.setText(6, "")
            it += 1
            item = it.value()
        self.ui.label_selections.setText(_("No coders selected"))

    def export_text_file(self):
        """ Export coding comparison statistics to text file. """

        shortname = self.app.project_name.split(".qda")[0]
        filename = shortname + " coder comparison.txt"
        options = QtWidgets.QFileDialog.DontResolveSymlinks | QtWidgets.QFileDialog.ShowDirsOnly
        directory = QtWidgets.QFileDialog.getExistingDirectory(None,
            _("Select directory to save file"), self.app.last_export_directory, options)
        if directory == "":
            return
        if directory != self.app.last_export_directory:
            self.app.last_export_directory = directory
        filename = directory + "/" + filename
        if os.path.exists(filename):
            mb = QtWidgets.QMessageBox()
            mb.setWindowTitle(_("File exists"))
            mb.setText(_("Overwrite?"))
            mb.setStandardButtons(QtWidgets.QMessageBox.Yes|QtWidgets.QMessageBox.No)
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            if mb.exec_() == QtWidgets.QMessageBox.No:
                return
        f = open(filename, 'w')
        f.write(self.app.project_name + "\n")
        f.write(_("Date: ") + datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S") + "\n")
        f.write(self.comparisons)
        f.close()
        logger.info(_("Coder comparisons report exported to ") + filename)
        mb = QtWidgets.QMessageBox()
        mb.setIcon(QtWidgets.QMessageBox.Warning)
        mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        mb.setWindowTitle(_('Text file export'))
        msg = _("Coder comparison text file exported to: ") + filename
        mb.setText(msg)
        mb.exec_()
        self.parent_textEdit.append(msg)

    def calculate_statistics(self):
        """ Iterate through tree widget, for all cids
        For each code_name calculate the two-coder comparison statistics. """

        self.comparisons = "====" + _("CODER COMPARISON") + "====\n" + _("Selected coders: ")
        self.comparisons += self.selected_coders[0] + ", " + self.selected_coders[1] + "\n"

        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        while item:  # while there is an item in the list
            #logger.debug("While: ", item.text(0), item.text(1), c['catid'], c['supercatid'])
            if item.text(1)[0:4] == 'cid:':
                #logger.debug(item.text(0), item.text(1))
                agreement = self.calculate_agreement_for_code_name(int(item.text(1)[4:]))
                item.setText(2, str(agreement['agreement']) + "%")
                item.setText(3, str(agreement['dual_percent']) + "%")
                item.setText(4, str(agreement['uncoded_percent']) + "%")
                item.setText(5, str(agreement['disagreement']) + "%")
                item.setText(6, str(agreement['kappa']))
                self.comparisons += "\n" + item.text(0) + " (" + item.text(1) + ")\n"
                self.comparisons += _("agreement: ") + str(agreement['agreement']) + "%"
                self.comparisons += _(", dual coded: ") + str(agreement['dual_percent']) + "%"
                self.comparisons += _(", uncoded: ") + str(agreement['uncoded_percent']) + "%"
                self.comparisons += _(", disagreement: ") + str(agreement['disagreement']) + "%"
                self.comparisons += ", Kappa: " + str(agreement['kappa'])
            it += 1
            item = it.value()

    def calculate_agreement_for_code_name(self, cid):
        """ Calculate the two-coder statistics for this cid
        Percentage agreement.
        Get the start and end positions in all files (source table) for this cid
        Look at each file separately to ge the commonly coded text.
        Each character that is coded by coder 1 or coder 2 is incremented, resulting in a list of 0, 1, 2
        where 0 is no codings at all, 1 is coded by only one coder and 2 is coded by both coders.
        'Disagree%':'','A not B':'','B not A':'','K':''
        """

        #logger.debug("Code id: " + str(cid))
        # coded0 and coded1 are the total characters coded by coder 0 and coder 1
        total = {'dual_coded': 0, 'single_coded': 0, 'uncoded': 0, 'characters': 0, 'coded0': 0, 'coded1': 0}
        # loop through each source file
        cur = self.app.conn.cursor()
        sql = "select pos0,pos1,fid from code_text where fid=? and cid=? and owner=?"
        for f in self.file_summaries:
            #logger.debug("file summary ", f)
            cur.execute(sql, [f[0], cid, self.selected_coders[0]])
            result0 = cur.fetchall()
            cur.execute(sql, [f[0], cid, self.selected_coders[1]])
            result1 = cur.fetchall()
            #logger.debug("result0: " + str(result0))
            #logger.debug("result1: " + str(result1))
            # determine the same characters coded by both coders, by adding 1 to each coded character
            char_list = [0] * f[1]
            for coded in result0:
                #print(coded[0], coded[1])  # tmp
                for char in range(coded[0], coded[1]):
                    char_list[char] += 1
                    total['coded0'] += 1
            for coded in result1:
                for char in range(coded[0], coded[1]):
                    char_list[char] += 1
                    total['coded1'] += 1
            uncoded = 0
            single_coded = 0
            dual_coded = 0
            for char in char_list:
                if char == 0:
                    uncoded += 1
                if char == 1:
                    single_coded += 1
                if char == 2:
                    dual_coded += 1
            #logger.debug("file:" + f[0] + " dual:" + str(dual_coded) + " single:" + str(single_coded) + " uncoded:" + str(uncoded))
            total['dual_coded'] += dual_coded
            total['single_coded'] += single_coded
            total['uncoded'] += uncoded
            total['characters'] += f[1]
        total['agreement'] = round(100 * (total['dual_coded'] + total['uncoded']) / total['characters'], 2)
        total['dual_percent'] = round(100 * total['dual_coded'] / total['characters'], 2)
        total['uncoded_percent'] = round(100 * total['uncoded'] / total['characters'], 2)
        total['disagreement'] = round(100 - total['agreement'], 2)
        # Cohen's Kappa
        '''
        https://en.wikipedia.org/wiki/Cohen%27s_kappa

        k = Po - Pe     Po is proportionate agreement (both coders coded this text / all coded text))
            -------     Pe is probability of random agreement
            1  - Pe

            Pe = Pyes + Pno
            Pyes = proportion Yes by A multiplied by proportion Yes by B
                 = total['coded0']/total_coded * total['coded1]/total_coded

            Pno = proportion No by A multiplied by proportion No by B
                = (total_coded - total['coded0']) / total_coded * (total_coded - total['coded1]) / total_coded

        IMMEDIATE BELOW IS INCORRECT - RESULTS IN THE TOTAL AGREEMENT SCORE
        Po = total['agreement'] / 100
        Pyes = total['coded0'] / total['characters'] * total['coded1'] / total['characters']
        Pno = (total['characters'] - total['coded0']) / total['characters'] * (total['characters'] - total['coded1']) / total['characters']

        BELOW IS BETTER - ONLY LOOKS AT PROPORTIONS OF CODED CHARACTERS
        NEED TO CONFIRM THIS IS THE CORRECT APPROACH
        '''
        total['kappa'] = "zerodiv"
        try:
            unique_codings = total['coded0'] + total['coded1'] - total['dual_coded']
            Po = total['dual_coded'] / unique_codings
            Pyes = total['coded0'] / unique_codings * total['coded1'] / unique_codings
            Pno = (unique_codings - total['coded0']) / unique_codings * (unique_codings - total['coded1']) / unique_codings
            Pe = Pyes * Pno
            kappa = round((Po - Pe) / (1 - Pe), 4)
            total['kappa'] = kappa
        except ZeroDivisionError:
            msg = _("ZeroDivisionError. unique_codings:") + str(unique_codings)
            logger.debug(msg)
        return total

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes. """

        cats = copy(self.categories)
        codes = copy(self.code_names)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(7)
        self.ui.treeWidget.setHeaderLabels([_("Code Tree"), "Id","Agree %", "A and B %", "Not A Not B %", "Disagree %", "Kappa"])
        self.ui.treeWidget.hideColumn(1)
        if self.app.settings['showids'] == 'True':
            self.ui.treeWidget.showColumn(1)
        self.ui.treeWidget.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.ui.treeWidget.header().setStretchLastSection(False)
        # add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']) ])
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_list.append(c)
        for item in remove_list:
            #try:
            cats.remove(item)
            #except Exception as e:
            #    logger.debug(str(e) + " item:" + str(item))

        ''' Add child categories. Look at each unmatched category, iterate through tree to
        add as child then remove matched categories from the list. '''
        count = 0
        while len(cats) > 0 or count < 10000:
            remove_list = []
            #logger.debug("cats:" + str(cats))
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
                item = it.value()
                while item:  # while there is an item in the list
                    #logger.debug("While: ", item.text(0), item.text(1), c['catid'], c['supercatid'])
                    if item.text(1) == 'catid:' + str(c['supercatid']):
                        child = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']) ])
                        item.addChild(child)
                        #logger.debug("Adding: " + c['name'])
                        remove_list.append(c)
                    it += 1
                    item = it.value()
            for item in remove_list:
                cats.remove(item)
            count += 1

        # add unlinked codes as top level items
        remove_items = []
        for c in codes:
            if c['catid'] is None:
                #logger.debug("c[catid] is None: new top item c[name]:" + c['name'])
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']) ])
                top_item.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.SolidPattern))
                top_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)

        # add codes as children
        for c in codes:
            it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
            item = it.value()
            while item:
                #logger.debug("for c in codes, item:" + item.text(0) +"|" + item.text(1) + ", c[cid]:" + str(c['cid']) +", c[catid]:" + str(c['catid']))
                if item.text(1) == 'catid:' + str(c['catid']):
                    child = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']) ])
                    child.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.SolidPattern))
                    child.setFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
                    item.addChild(child)
                    c['catid'] = -1  # make unmatchable
                it += 1
                item = it.value()
        self.ui.treeWidget.expandAll()


class DialogReportCodes(QtWidgets.QDialog):
    """ Get reports on coded text/images/audio/video using a range of variables:
        Files, Cases, Coders, text limiters, Attribute limiters.
        Export reports as plain text, ODT, html or csv.

        Text context of a coded text portion is shown in the thord splitter pan in a text edit.
        Case matrix is also shown in a qtablewidget in the third splitter pane.
        If a case matrix is displayed, the text-in-context method overrides it and replaces the matrix with the text in context.
        TODO - export case matrix
    """

    app = None
    parent_textEdit = None
    code_names = []
    coders = [""]
    categories = []
    files = []
    cases = []
    html_links = []  # For html output with media link (images, av)
    text_results = []
    image_results = []
    av_results = []
    # variables for search restrictions
    file_ids = ""
    case_ids = ""
    attribute_selection = []

    def __init__(self, app, parent_textEdit):
        super(DialogReportCodes, self).__init__()
        sys.excepthook = exception_handler
        self.app = app
        self.parent_textEdit = parent_textEdit
        self.get_codes_categories_coders()
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_reportCodings()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        treefont = 'font: ' + str(self.app.settings['treefontsize']) + 'pt '
        treefont += '"' + self.app.settings['font'] + '";'
        self.ui.treeWidget.setStyleSheet(treefont)
        self.ui.treeWidget.installEventFilter(self)  # For H key
        self.ui.label_counts.setStyleSheet(treefont)
        self.ui.listWidget_files.setStyleSheet(treefont)
        self.ui.listWidget_files.installEventFilter(self)  # For H key
        self.ui.listWidget_files.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.ui.listWidget_cases.setStyleSheet(treefont)
        self.ui.listWidget_cases.installEventFilter(self)  # For H key
        self.ui.listWidget_cases.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.ui.treeWidget.setSelectionMode(QtWidgets.QTreeWidget.ExtendedSelection)
        self.ui.comboBox_coders.insertItems(0, self.coders)
        self.fill_tree()
        self.ui.pushButton_search.clicked.connect(self.search)
        #icon = QtGui.QIcon(QtGui.QPixmap('GUI/cogs_icon.png'))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(cogs_icon), "png")
        self.ui.pushButton_search.setIcon(QtGui.QIcon(pm))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(doc_export_icon), "png")
        self.ui.label_exports.setPixmap(pm)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(a2x2_color_grid_icon_24), "png")
        self.ui.label_matrix.setPixmap(pm)
        options = [_("Top categories"), _("Categories"), _("Codes")]
        self.ui.comboBox_matrix.addItems(options)
        cur = self.app.conn.cursor()
        sql = "select count(name) from attribute_type"
        cur.execute(sql)
        res = cur.fetchone()
        if res[0] == 0:
            self.ui.pushButton_attributeselect.setEnabled(False)
        self.ui.pushButton_attributeselect.clicked.connect(self.select_attributes)
        self.ui.comboBox_export.currentIndexChanged.connect(self.export_option_selected)
        self.ui.comboBox_export.setEnabled(False)
        self.eventFilterTT = ToolTip_EventFilter()
        self.ui.textEdit.installEventFilter(self.eventFilterTT)
        self.ui.textEdit.installEventFilter(self)  # for H key
        self.ui.textEdit.setReadOnly(True)
        self.ui.splitter.setSizes([100, 200, 0])
        try:
            s0 = int(self.app.settings['dialogreportcodes_splitter0'])
            s1 = int(self.app.settings['dialogreportcodes_splitter1'])
            if s0 > 10 and s1 > 10:
                self.ui.splitter.setSizes([s0, s1, 0])
            v0 = self.app.settings['dialogreportcodes_splitter_v0']
            v1 = self.app.settings['dialogreportcodes_splitter_v1']
            v2 = self.app.settings['dialogreportcodes_splitter_v2']
            self.ui.splitter_vert.setSizes([v0, v1, v2])
        except:
            pass
        self.ui.splitter.splitterMoved.connect(self.splitter_sizes)
        self.ui.splitter_vert.splitterMoved.connect(self.splitter_sizes)
        self.ui.treeWidget.itemSelectionChanged.connect(self.display_counts)
        self.get_files_and_cases()
        self.ui.listWidget_files.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.listWidget_files.customContextMenuRequested.connect(self.listwidget_files_menu)
        self.ui.listWidget_cases.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.listWidget_cases.customContextMenuRequested.connect(self.listwidget_cases_menu)

    def splitter_sizes(self, pos, index):
        """ Detect size changes in splitter and store in app.settings variable. """

        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogreportcodes_splitter0'] = sizes[0]
        self.app.settings['dialogreportcodes_splitter1'] = sizes[1]
        sizes_vert = self.ui.splitter_vert.sizes()
        self.app.settings['dialogreportcodes_splitter_v0'] = sizes_vert[0]
        self.app.settings['dialogreportcodes_splitter_v1'] = sizes_vert[1]
        self.app.settings['dialogreportcodes_splitter_v2'] = sizes_vert[2]

    def get_files_and_cases(self):
        """ Get source files with additional details and fill files list widget.
        Get cases and fill case list widget
        Called from : init, manage_files.delete manage_files.delete_button_multiple_files
        """

        self.ui.listWidget_files.clear()
        self.files = self.app.get_filenames()
        # Fill additional details about each file in the memo
        cur = self.app.conn.cursor()
        sql = "select length(fulltext), mediapath from source where id=?"
        sql_text_codings = "select count(cid) from code_text where fid=?"
        sql_av_codings = "select count(cid) from code_av where id=?"
        sql_image_codings = "select count(cid) from code_image where id=?"
        item = QtWidgets.QListWidgetItem("")
        item.setToolTip(_("No file selection"))
        self.ui.listWidget_files.addItem(item)
        for f in self.files:
            cur.execute(sql, [f['id'], ])
            res = cur.fetchone()
            if res is None:  # safety catch
                res = [0]
            tt = ""
            if res[1] is None or res[1][0:5] == "docs:":
                tt += _("Text file\n")
                tt += _("Characters: ") + str(res[0])
            if res[1] is not None and (res[1][0:7] == "images:" or res[1][0:7] == "/images"):
                tt += _("Image")
            if res[1] is not None and (res[1][0:6] == "audio:" or res[1][0:6] == "/audio"):
                tt += _("Audio")
            if res[1] is not None and (res[1][0:6] == "video:" or res[1][0:6] == "/video"):
                tt += _("Video")
            cur.execute(sql_text_codings, [f['id']])
            txt_res = cur.fetchone()
            cur.execute(sql_av_codings, [f['id']])
            av_res = cur.fetchone()
            cur.execute(sql_image_codings, [f['id']])
            img_res = cur.fetchone()
            tt += _("\nCodings: ")
            if txt_res[0] > 0:
                tt += str(txt_res[0])
            if av_res[0] > 0:
                tt += str(av_res[0])
            if img_res[0] > 0:
                tt += str(img_res[0])
            item = QtWidgets.QListWidgetItem(f['name'])
            if f['memo'] is not None and f['memo'] != "":
                tt += _("\nMemo: ") + f['memo']
            item.setToolTip(tt)
            self.ui.listWidget_files.addItem(item)

        self.ui.listWidget_cases.clear()
        self.cases = self.app.get_casenames()
        item = QtWidgets.QListWidgetItem("")
        item.setToolTip(_("No case selection"))
        self.ui.listWidget_cases.addItem(item)
        for c in self.cases:
            tt= ""
            item = QtWidgets.QListWidgetItem(c['name'])
            if c['memo'] is not None and c['memo'] != "":
                tt = _("Memo: ") + c['memo']
            item.setToolTip(tt)
            self.ui.listWidget_cases.addItem(item)

    def get_codes_categories_coders(self):
        """ Called from init, delete category. Load codes, categories, and coders. """

        self.code_names, self.categories = self.app.get_data()
        cur = self.app.conn.cursor()
        self.coders = []
        cur.execute("select distinct owner from code_text")
        result = cur.fetchall()
        self.coders = [""]
        for row in result:
            self.coders.append(row[0])

    def get_selected_files_and_cases(self):
        """ Fill file_ids and case_ids Strings used in the search.
        Clear attribute selection.
         Called by: search """

        selected_files = []
        self.file_ids = ""
        for item in self.ui.listWidget_files.selectedItems():
            selected_files.append(item.text())
            for f in self.files:
                if f['name'] == item.text():
                    self.file_ids += "," + str(f['id'])
        if len(self.file_ids) > 0:
            self.file_ids = self.file_ids[1:]
        selected_cases = []
        self.case_ids = ""
        for item in self.ui.listWidget_cases.selectedItems():
            selected_cases.append(item.text())
            for c in self.cases:
                if c['name'] == item.text():
                    self.case_ids += "," + str(c['id'])
        if len(self.case_ids) > 0:
            self.case_ids = self.case_ids[1:]
        self.display_counts()

    def listwidget_files_menu(self, position):
        """ Context menu for file selection. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_all_files = menu.addAction(_("Select all files"))
        action_files_like = menu.addAction(_("Select files like"))
        action_files_none = menu.addAction(_("Select none"))
        action = menu.exec_(self.ui.listWidget_files.mapToGlobal(position))
        if action == action_all_files:
            self.ui.listWidget_files.selectAll()
            self.ui.listWidget_files.item(0).setSelected(False)
        if action == action_files_none:
            for i in range(self.ui.listWidget_files.count()):
                self.ui.listWidget_files.item(i).setSelected(False)
        if action == action_files_like:
            # Input dialog narrow, so code below
            dialog = QtWidgets.QInputDialog(None)
            dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            dialog.setWindowTitle(_("Select some files"))
            dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
            dialog.setInputMode(QtWidgets.QInputDialog.TextInput)
            dialog.setLabelText(_("Show files containing text"))
            dialog.resize(200, 20)
            ok = dialog.exec_()
            if not ok:
                return
            text = str(dialog.textValue())
            for i in range(self.ui.listWidget_files.count()):
                item_name = self.ui.listWidget_files.item(i).text()
                if text in item_name:
                    self.ui.listWidget_files.item(i).setSelected(True)
                else:
                    self.ui.listWidget_files.item(i).setSelected(False)

    def listwidget_cases_menu(self, position):
        """ Context menu for case selection. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_all_cases = menu.addAction(_("Select all cases"))
        action_cases_like = menu.addAction(_("Select cases like"))
        action_cases_none = menu.addAction(_("Select none"))
        action = menu.exec_(self.ui.listWidget_cases.mapToGlobal(position))
        if action == action_all_cases:
            self.ui.listWidget_cases.selectAll()
            self.ui.listWidget_cases.item(0).setSelected(False)
        if action == action_cases_none:
            for i in range(self.ui.listWidget_cases.count()):
                self.ui.listWidget_cases.item(i).setSelected(False)
        if action == action_cases_like:
            # Input dialog narrow, so code below
            dialog = QtWidgets.QInputDialog(None)
            dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            dialog.setWindowTitle(_("Select some cases"))
            dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
            dialog.setInputMode(QtWidgets.QInputDialog.TextInput)
            dialog.setLabelText(_("Select cases containing text"))
            dialog.resize(200, 20)
            ok = dialog.exec_()
            if not ok:
                return
            text = str(dialog.textValue())
            for i in range(self.ui.listWidget_cases.count()):
                item_name = self.ui.listWidget_cases.item(i).text()
                if text in item_name:
                    self.ui.listWidget_cases.item(i).setSelected(True)
                else:
                    self.ui.listWidget_cases.item(i).setSelected(False)

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes. """

        cats = copy(self.categories)
        codes = copy(self.code_names)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(4)
        self.ui.treeWidget.setHeaderLabels([_("Name"), "Id", _("Memo"), _("Count")])
        self.ui.treeWidget.header().setToolTip(_("Codes and categories"))
        if self.app.settings['showids'] == 'False':
            self.ui.treeWidget.setColumnHidden(1, True)
        else:
            self.ui.treeWidget.setColumnHidden(1, False)
        self.ui.treeWidget.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.ui.treeWidget.header().setStretchLastSection(False)
        # add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                memo = ""
                if c['memo'] != "":
                    memo = _("Memo")
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                top_item.setToolTip(2, c['memo'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_list.append(c)
        for item in remove_list:
            cats.remove(item)

        ''' Add child categories. Look at each unmatched category, iterate through tree
        to add as child then remove matched categories from the list. '''
        count = 0
        while len(cats) > 0 and count < 10000:
            remove_list = []
            #logger.debug(cats)
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
                item = it.value()
                count2 = 0
                while item and count2 < 10000:  # while there is an item in the list
                    #logger.debug("While item in list: " + item.text(0) + "|" + item.text(1) + ", c[catid]:" + str(c['catid']) + ", supercatid:" + str(c['supercatid']))
                    if item.text(1) == 'catid:' + str(c['supercatid']):
                        memo = ""
                        if c['memo'] != "":
                            memo = "Memo"
                        child = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                        child.setToolTip(2, c['memo'])
                        item.addChild(child)
                        #logger.debug("Adding item: " + c['name'])
                        remove_list.append(c)
                    it += 1
                    item = it.value()
                    count2 += 1
            for item in remove_list:
                cats.remove(item)
            count += 1

        # add unlinked codes as top level items
        remove_items = []
        for c in codes:
            if c['catid'] is None:
                #logger.debug("add unlinked code:" + c['name'])
                memo = ""
                if c['memo'] != "":
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                top_item.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.SolidPattern))
                top_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)  # | Qt.ItemIsDragEnabled)
                top_item.setToolTip(2, c['memo'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)

        # add codes as children
        for c in codes:
            it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
            item = it.value()
            count = 0
            while item and count < 10000:
                #logger.debug("add codes as children, item:" + item.text(0) + "|" + item.text(1) + ", c[id]:" + str(c['cid']) + ", c[catid]:" + str(c['catid']))
                if item.text(1) == 'catid:' + str(c['catid']):
                    memo = ""
                    if c['memo'] != "":
                        memo = _("Memo")
                    child = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                    child.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.SolidPattern))
                    child.setFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)  # | Qt.ItemIsDragEnabled)
                    child.setToolTip(2, c['memo'])
                    item.addChild(child)
                    c['catid'] = -1  # make unmatchable
                it += 1
                item = it.value()
                count += 1
        self.fill_code_counts_in_tree()
        self.ui.treeWidget.expandAll()

    def fill_code_counts_in_tree(self):
        """ Count instances of each code from all coders and all files. """

        cur = self.app.conn.cursor()
        sql = "select count(cid) from code_text where cid=? union "
        sql += "select count(cid) from code_av where cid=? union "
        sql += "select count(cid) from code_image where cid=?"
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        count = 0
        while item and count < 10000:
            #print(item.text(0), item.text(1), item.text(2), item.text(3))
            if item.text(1)[0:4] == "cid:":
                cid = str(item.text(1)[4:])
                cur.execute(sql, [cid, cid, cid])  # , self.app.settings['codername']])
                result = cur.fetchall()
                total = 0
                for row in result:
                    total = total + row[0]
                if total > 0:
                    item.setText(3, str(total))
                else:
                    item.setText(3, "")
            it += 1
            item = it.value()
            count += 1

    def export_option_selected(self):
        """ ComboBox export option selected. """

        #TODO add case matrix as csv, xlsx options
        text = self.ui.comboBox_export.currentText()
        if text == "":
            return
        if text == "html":
            self.export_html_file()
        if text == "odt":
            self.export_odt_file()
        if text == "txt":
            self.export_text_file()
        if text == "csv":
            self.export_csv_file()

    def export_text_file(self):
        """ Export report to a plain text file with .txt ending.
        QTextWriter supports plaintext, ODF and HTML.
        BUT QTextWriter does not support utf-8-sig
        """

        if len(self.ui.textEdit.document().toPlainText()) == 0:
            return
        file_tuple = QtWidgets.QFileDialog.getSaveFileName(None, _("Save text file"),
            self.app.last_export_directory)
        filename = file_tuple[0]
        if filename == "":
            return
        tmp = filename.split("/")[-1]
        directory = filename[:len(filename) - len(tmp)]
        if directory != self.app.last_export_directory:
            self.app.last_export_directory = directory
        filename = filename + ".txt"
        if os.path.exists(filename):
            mb = QtWidgets.QMessageBox()
            mb.setWindowTitle(_("File exists"))
            mb.setText(_("Overwrite?"))
            mb.setStandardButtons(QtWidgets.QMessageBox.Yes|QtWidgets.QMessageBox.No)
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            if mb.exec_() == QtWidgets.QMessageBox.No:
                return
        ''' https://stackoverflow.com/questions/39422573/python-writing-weird-unicode-to-csv
        Using a byte order mark so that other software recognised UTF-8
        '''
        data = self.ui.textEdit.toPlainText()
        f = open(filename, 'w', encoding='utf-8-sig')
        f.write(data)
        f.close()

        self.parent_textEdit.append(_("Report exported: ") + filename)
        mb = QtWidgets.QMessageBox()
        mb.setIcon(QtWidgets.QMessageBox.Warning)
        mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        mb.setWindowTitle(_('Report exported'))
        mb.setText(filename)
        mb.exec_()

    def export_odt_file(self):
        """ Export report to open document format with .odt ending.
        QTextWriter supports plaintext, ODF and HTML .
        """

        if len(self.ui.textEdit.document().toPlainText()) == 0:
            return
        file_tuple = QtWidgets.QFileDialog.getSaveFileName(None, _("Save Open Document Text file"),
            self.app.last_export_directory)
        filename = file_tuple[0]
        if filename == "":
            return
        tmp = filename.split("/")[-1]
        directory = filename[:len(filename) - len(tmp)]
        if directory != self.app.last_export_directory:
            self.app.last_export_directory = directory
        filename = filename + ".odt"
        if os.path.exists(filename):
            mb = QtWidgets.QMessageBox()
            mb.setWindowTitle(_("File exists"))
            mb.setText(_("Overwrite?"))
            mb.setStandardButtons(QtWidgets.QMessageBox.Yes|QtWidgets.QMessageBox.No)
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            if mb.exec_() == QtWidgets.QMessageBox.No:
                return
        tw = QtGui.QTextDocumentWriter()
        tw.setFileName(filename)
        tw.setFormat(b'ODF')  # byte array needed for Windows 10
        tw.write(self.ui.textEdit.document())
        self.parent_textEdit.append(_("Report exported: ") + filename)
        mb = QtWidgets.QMessageBox()
        mb.setIcon(QtWidgets.QMessageBox.Warning)
        mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        mb.setWindowTitle(_('Report exported'))
        mb.setText(filename)
        mb.exec_()

    def export_csv_file(self):
        """ Export report to csv file.
        Export coded data as csv with codes as column headings.
        Draw data from self.text_results, self.image_results, self.av_results
        First need to determine number of columns based on the distinct number of codes in the results.
        Then the number of rows based on the most frequently assigned code.
        Each data cell contains coded text, or the memo if A/V or image and the file or case name.
        """

        if self.text_results == [] and self.image_results == [] and self.av_results == []:
            return

        codes_all = []
        codes_set = []
        codes_freq_list = []

        #print("TEXT")  # tmp
        for i in self.text_results:
            codes_all.append(i['codename'])
            #print(i)
        #print("IMAGES")  # tmp
        for i in self.image_results:
            codes_all.append(i['codename'])
            #print(i)
        #print("AUDIO/VIDEO")  # tmp
        for i in self.av_results:
            codes_all.append(i['codename'])
            #print(i)

        codes_set = list(set(codes_all))
        codes_set.sort()
        for x in codes_set:
            codes_freq_list.append(codes_all.count(x))

        #print(codes_all)
        #print(codes_set)
        #print(codes_freq_list)

        ncols = len(codes_set)
        nrows = sorted(codes_freq_list)[-1]
        #print("ncols:", ncols, "nrows:", nrows)

        # Prepare data rows for csv writer
        csv_data = []
        for r in range(0, nrows):
            row = []
            for c in range(0, ncols):
                row.append("")
            csv_data.append(row)

        # Look at each code and fill column with data
        for col, code in enumerate(codes_set):
            row = 0
            for i in self.text_results:
                if i['codename'] == code:
                    d = i['text'] + "\n" + i['file_or_casename']
                     # Add file id if results are based on attribute selection
                    if i['file_or_case'] == "":
                        d += " fid:" + str(i['fid'])
                    csv_data[row][col]  = d
                    row += 1
            for i in self.image_results:
                if i['codename'] == code:
                    d = i['memo']
                    if d == "":
                        d = "NO MENO"
                    d += "\n" + i['file_or_casename']
                    # Add filename if results are based on attribute selection
                    if i['file_or_case'] == "":
                        d += " " + i['mediapath'][8:]
                    csv_data[row][col] = d
                    row +=1
            for i in self.av_results:
                if i['codename'] == code:
                    d = i['memo']
                    if d == "":
                        d = "NO MEMO"
                    d += "\n"
                    # av 'text' contains video/filename, time slot and memo, so trim some out
                    trimmed = i['text'][6:]
                    pos = trimmed.find(']')
                    trimmed = trimmed[:pos + 1]
                    # Add case name as well as file name and time slot
                    if i['file_or_case'] != "File":
                        trimmed = i['file_or_casename'] + " " + trimmed
                    d += trimmed
                    csv_data[row][col] = d
                    row += 1

        file_tuple = QtWidgets.QFileDialog.getSaveFileName(None, _("Save CSV file"),
            self.app.last_export_directory)
        filename = file_tuple[0]
        if filename == "":
            return
        tmp = filename.split("/")[-1]
        directory = filename[:len(filename) - len(tmp)]
        if directory != self.app.last_export_directory:
            self.app.last_export_directory = directory
        filename = filename + ".csv"
        if os.path.exists(filename):
            mb = QtWidgets.QMessageBox()
            mb.setWindowTitle(_("File exists"))
            mb.setText(_("Overwrite?"))
            mb.setStandardButtons(QtWidgets.QMessageBox.Yes|QtWidgets.QMessageBox.No)
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            if mb.exec_() == QtWidgets.QMessageBox.No:
                return
        with open(filename, 'w', encoding ='utf-8-sig', newline='') as csvfile:
            filewriter = csv.writer(csvfile, delimiter=',',
                quotechar='"', quoting=csv.QUOTE_MINIMAL)
            filewriter.writerow(codes_set)  # header row
            for row in csv_data:
                filewriter.writerow(row)
        mb = QtWidgets.QMessageBox()
        mb.setIcon(QtWidgets.QMessageBox.Warning)
        mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        mb.setWindowTitle(_('Report exported'))
        mb.setText(filename)
        mb.exec_()

    def export_html_file(self):
        """ Export report to a html file. Create folder of images and change refs to the
        folder.
        TODO: Possibly have picture data in base64 so there is no need for a separate folder.
        """

        if len(self.ui.textEdit.document().toPlainText()) == 0:
            return
        file_tuple = QtWidgets.QFileDialog.getSaveFileName(None, _("Save html file"),
            self.app.last_export_directory)
        filename = file_tuple[0]
        if filename == "":
            return
        tmp = filename.split("/")[-1]
        directory = filename[:len(filename) - len(tmp)]
        if directory != self.app.last_export_directory:
            self.app.last_export_directory = directory
        filename = filename + ".html"
        if os.path.exists(filename):
            mb = QtWidgets.QMessageBox()
            mb.setWindowTitle(_("File exists"))
            mb.setText(_("Overwrite?"))
            mb.setStandardButtons(QtWidgets.QMessageBox.Yes|QtWidgets.QMessageBox.No)
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            if mb.exec_() == QtWidgets.QMessageBox.No:
                return
        tw = QtGui.QTextDocumentWriter()
        tw.setFileName(filename)
        tw.setFormat(b'HTML')  # byte array needed for Windows 10
        tw.setCodec(QTextCodec.codecForName('UTF-8'))  # for Windows 10
        tw.write(self.ui.textEdit.document())

        need_media_folders = False
        for item in self.html_links:
            if item['image'] is not None or item['avname'] is not None:
                need_media_folders = True
        if need_media_folders:
            # Create folder of images and media and change html links
            foldername = filename[:-5]
            foldername_without_path = foldername.split('/')[-1]
            try:
                os.mkdir(foldername)
                os.mkdir(foldername + "/audio")
                os.mkdir(foldername + "/video")
            except Exception as e:
                logger.warning(_("html folder creation error ") + str(e))
                QtWidgets.QMessageBox.warning(None, _("Folder creation"), foldername + _(" error"))
                return
        html = ""
        try:
            with open(filename, 'r') as f:
                html = f.read()
        except Exception as e:
            logger.warning(_('html file reading error:') + str(e))
            return

        for item in self.html_links:
            if item['imagename'] is not None:
                #print("===================")
                #print("IMG PATH ", item['imagename'])
                # item['imagename'] is in this format: 0-/images/filename.jpg  # where 0- is the counter
                imagename = item['imagename'].replace('/images/', '')
                #print("IMG NAME: ", imagename)
                folder_link = filename[:-5] + "/" + imagename
                #print("FOLDER LINK:", folder_link)
                item['image'].save(folder_link)
                html_link = foldername_without_path + "/" + imagename
                ''' Replace html links, with fix for Windows 10, item[imagename] contains a lower case directory but
                this needs to be upper case for the replace method to work:  c:  =>  C:
                '''
                #TODO this may fail on Windows now
                unreplaced_html = copy(html)  # for Windows 10 directory name upper/lower case issue
                html = html.replace(item['imagename'], html_link)
                if unreplaced_html == html:
                    html = html.replace(item['imagename'][0].upper() + item['imagename'][1:], html_link)
                #print("Windows 10 not replacing issue ", item['imagename'], html_link)
                #logger.debug("Windows 10 not replacing issue: item[imagename]: " + item['imagename'] + ", html_link: " + html_link)

            if item['avname'] is not None:
                try:
                    # Add audio/video to folder
                    mediatype = ""
                    if item['avname'][0:6] in ("/video", "video:"):
                        mediatype = "video"
                    if item['avname'][0:6] in ("/audio", "audio:"):
                        mediatype = "audio"
                    # Remove link prefix and note if link or not
                    linked = False
                    av_path = item['avname']
                    if av_path[0:6] == "video:":
                        av_path = av_path[6:]
                        linked = True
                    if av_path[0:6] == "audio:":
                        linked = True
                        av_path = av_path[6:]
                    av_filepath_dest = ""
                    if not linked and not os.path.isfile(foldername + av_path):
                        copyfile(self.app.project_path + item['avname'], foldername + av_path)
                        av_filepath_dest = foldername + av_path
                    # Extra work to check and copy a Linked file
                    if mediatype == "video" and linked:
                        av_filepath = av_path.split("/")[-1]
                        if not os.path.isfile(foldername + "/video/" + av_path.split('/')[-1]):
                            av_filepath_dest = foldername + "/video/" + av_path.split('/')[-1]
                            copyfile(av_path, av_filepath_dest)
                    if mediatype == "audio" and linked:
                        av_filename = av_path.split("/")[-1]
                        if not os.path.isfile(foldername + "/audio/" + av_path.split('/')[-1]):
                            av_filepath_dest = foldername + "/video/" + av_path.split('/')[-1]
                            copyfile(av_path + item['avname'], av_filepath_dest)

                    extension = item['avname'][item['avname'].rfind('.') + 1:]
                    extra = "</p><" + mediatype + " controls>"
                    extra += '<source src="' + av_filepath_dest
                    extra += '#t=' + item['av0'] +',' + item['av1'] + '"'
                    extra += ' type="' + mediatype + '/' + extension + '">'
                    extra += '</' + mediatype + '><p>'
                    print("EXTRA:", extra)
                    # hopefully only one location with video/link: [mins.secs - mins.secs]
                    location = html.find(item['avtext'])
                    location = location + len(['avtext'])- 1
                    tmp = html[:location] + extra + html[location:]
                    html = tmp
                except Exception as e:
                    logger.debug(str(e))
                    QtWidgets.QMessageBox.warning(None, _("HTML file creation exception"), str(e))

        with open(filename, 'w') as f:
            f.write(html)
        msg = _("Report exported to: ") + filename
        if need_media_folders:
            msg += "\n" + _("Media folder: ") + foldername
        self.parent_textEdit.append(msg)
        mb = QtWidgets.QMessageBox()
        mb.setIcon(QtWidgets.QMessageBox.Warning)
        mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        mb.setWindowTitle(_('Report exported'))
        mb.setText(msg)
        mb.exec_()

    def eventFilter(self, object, event):
        """ Used to detect key events in the textedit.
        H Hide / Unhide top groupbox
        """

        # change start and end code positions using alt arrow left and alt arrow right
        # and shift arrow left, shift arrow right
        # QtGui.QKeyEvent = 7
        if type(event) == QtGui.QKeyEvent and (self.ui.textEdit.hasFocus() or self.ui.treeWidget.hasFocus() or \
            self.ui.listWidget_files.hasFocus() or self.ui.listWidget_cases.hasFocus()):
            key = event.key()
            mod = event.modifiers()
            # Hide unHide top groupbox
            if key == QtCore.Qt.Key_H:
                self.ui.groupBox.setHidden(not(self.ui.groupBox.isHidden()))
                return True
        return False

    def recursive_set_selected(self, item):
        """ Set all children of this item to be selected if the item is selected.
        Recurse through any child categories.
        Called by: search
        """

        #logger.debug("recurse this item:" + item.text(0) + "|" item.text(1))
        child_count = item.childCount()
        for i in range(child_count):
            if item.isSelected():
                item.child(i).setSelected(True)
            self.recursive_set_selected(item.child(i))

    def display_counts(self):
        """ Fill counts label with counts of selected codes/files/cases attributes. """

        self.recursive_set_selected(self.ui.treeWidget.invisibleRootItem())
        items = self.ui.treeWidget.selectedItems()
        codes_count = 0
        for i in items:
            if i.text(1)[0:3] == 'cid':
                codes_count += 1
        codes = _("Codes: ") + str(codes_count) + "/" + str(len(self.code_names))
        files_count = len(self.file_ids.split(","))
        if self.file_ids == "":
            files_count = 0
        filenames = self.app.get_filenames()
        files = _("Files: ") + str(files_count) + "/" + str(len(filenames))
        cases_count = len(self.case_ids.split(","))
        if self.case_ids == "":
            cases_count = 0
        casenames = self.app.get_casenames()
        cases = _("Cases: ") + str(cases_count) + "/" + str(len(casenames))
        attribute_count = len(self.attribute_selection)
        cur = self.app.conn.cursor()
        sql = "select count(name) from attribute_type"
        cur.execute(sql)
        result = cur.fetchone()
        if result is None:
            result = [0]
        attributes = _("Attributes: ") + str(attribute_count) + "/" + str(result[0])
        msg = codes + "  " + files+ "  " + cases + "  " + attributes
        self.ui.label_counts.setText(msg)

    def search(self):
        """ Search for selected codings.
        There are three main search pathways.
        1:  file selection only.
        2: case selection combined with files selection. (No files selected presumes ALL files)
        3: attribute selection, which may include files or cases.
        """

        # Get variables for search: search text, coders, codes, files,cases, attributes
        try:
            # self.ui.textEdit.blockSignals(True) - does not work when filling textedit
            self.ui.textEdit.cursorPositionChanged.disconnect(self.show_context_of_clicked_heading)
        except:
            pass
        coder = self.ui.comboBox_coders.currentText()
        self.html_links = []  # For html file output with media
        search_text = self.ui.lineEdit.text()
        self.get_selected_files_and_cases()

        # Select all code items under selected categories
        self.recursive_set_selected(self.ui.treeWidget.invisibleRootItem())
        items = self.ui.treeWidget.selectedItems()
        if len(items) == 0:
            mb = QtWidgets.QMessageBox()
            mb.setIcon(QtWidgets.QMessageBox.Warning)
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            mb.setWindowTitle(_('No codes'))
            msg = _("No codes have been selected.")
            mb.setText(msg)
            mb.exec_()
            return
        if self.file_ids == "" and self.case_ids == "" and self.attribute_selection == []:
            mb = QtWidgets.QMessageBox()
            mb.setIcon(QtWidgets.QMessageBox.Warning)
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            mb.setWindowTitle(_('Nothing selected'))
            msg = _("No files, cases or attributes have been selected.")
            mb.setText(msg)
            mb.exec_()
            return

        # Prepare results table
        rows = self.ui.tableWidget.rowCount()
        for r in range(0, rows):
            self.ui.tableWidget.removeRow(0)

        # Add search terms to textEdit
        self.ui.comboBox_export.setEnabled(True)
        self.ui.textEdit.clear()
        self.ui.textEdit.insertPlainText(_("Search parameters") + "\n==========\n")
        if coder == "":
            self.ui.textEdit.insertPlainText(_("Coding by: All coders") + "\n")
        else:
            self.ui.textEdit.insertPlainText(_("Coding by: ") + coder + "\n")
        codes_string = _("Codes: ") + "\n"
        for i in items:
            codes_string += i.text(0) + ". "
        self.ui.textEdit.insertPlainText(codes_string)

        cur = self.app.conn.cursor()
        parameters = ""
        if self.attribute_selection != []:
            self.file_ids = ""
            for i in range(self.ui.listWidget_files.count()):
                self.ui.listWidget_files.item(i).setSelected(False)
            self.case_ids = ""
            for i in range(self.ui.listWidget_cases.count()):
                self.ui.listWidget_cases.item(i).setSelected(False)
            self.display_counts()
            parameters += _("\nAttributes:\n")
            for a in self.attribute_selection:
                parameters += a[0] + " " + a[3] + " "
                for b in a[4]:  # a[4] is a list
                    parameters += b + ","
                parameters += "\n"
        if self.file_ids != "" and self.attribute_selection == []:
            parameters += _("\nFiles:\n")
            cur.execute("select name from source where id in (" + self.file_ids + ") order by name")
            res = cur.fetchall()
            for r in res:
                parameters += r[0] + ", "
        if self.case_ids != "":
            parameters += _("\nCases:\n")
            cur.execute("select name from cases where caseid in (" + self.case_ids + ") order by name")
            res = cur.fetchall()
            for r in res:
                parameters += r[0] + ", "

        self.ui.textEdit.insertPlainText(parameters + "\n")
        if search_text != "":
            self.ui.textEdit.insertPlainText("\n" + _("Search text: ") + search_text + "\n")
        self.ui.textEdit.insertPlainText("\n==========\n")

        # Get selected codes
        code_ids = ""
        for i in items:
            if i.text(1)[0:3] == 'cid':
                code_ids += "," + i.text(1)[4:]
        code_ids = code_ids[1:]
        #logger.debug("File ids\n",self.file_ids, type(self.file_ids))
        #logger.debug("Case ids\n",self.case_ids, type(self.case_ids))
        self.text_results = []
        self.image_results = []
        self.av_results = []

        # FILES ONLY SEARCH
        parameters = []
        if self.file_ids != "" and self.case_ids == "":
            # Coded text
            sql = "select code_name.name, color, source.name, pos0, pos1, seltext, "
            sql += "code_text.owner, fid from code_text join code_name "
            sql += "on code_name.cid = code_text.cid join source on fid = source.id "
            sql += "where code_name.cid in (" + code_ids + ") "
            sql += "and source.id in (" + self.file_ids + ") "
            if coder != "":
                sql += " and code_text.owner=? "
                parameters.append(coder)
            if search_text != "":
                sql += " and seltext like ? "
                parameters.append("%" + str(search_text) + "%")
            if parameters == []:
                cur.execute(sql)
            else:
                #logger.info("SQL:" + sql)
                #logger.info("Parameters:" + str(parameters))
                cur.execute(sql, parameters)
            result = cur.fetchall()
            for row in result:
                self.text_results.append(row)

            # Coded images
            parameters = []
            sql = "select code_name.name, color, source.name, x1, y1, width, height,"
            sql += "code_image.owner, source.mediapath, source.id, code_image.memo "
            sql += " from code_image join code_name "
            sql += "on code_name.cid = code_image.cid join source on code_image.id = source.id "
            sql += "where code_name.cid in (" + code_ids + ") "
            sql += "and source.id in (" + self.file_ids + ") "
            if coder != "":
                sql += " and code_image.owner=? "
                parameters.append(coder)
            if search_text != "":
                sql += " and code_image.memo like ? "
                parameters.append("%" + str(search_text) + "%")
            if parameters == []:
                cur.execute(sql)
            else:
                #logger.info("SQL:" + sql)
                #logger.info("Parameters:" + str(parameters))
                cur.execute(sql, parameters)
            result = cur.fetchall()
            for row in result:
                self.image_results.append(row)

            # Coded audio and video, also looks for search_text in coded segment memo
            parameters = []
            sql = "select code_name.name, color, source.name, pos0, pos1, code_av.memo, "
            sql += "code_av.owner, source.mediapath, source.id from code_av join code_name "
            sql += "on code_name.cid = code_av.cid join source on code_av.id = source.id "
            sql += "where code_name.cid in (" + code_ids + ") "
            sql += "and source.id in (" + self.file_ids + ") "
            if coder != "":
                sql += " and code_av.owner=? "
                parameters.append(coder)
            if search_text != "":
                sql += " and code_av.memo like ? "
                parameters.append("%" + str(search_text) + "%")
            if parameters == []:
                cur.execute(sql)
            else:
                #logger.info("SQL:" + sql)
                #logger.info("Parameters:" + str(parameters))
                cur.execute(sql, parameters)
            result = cur.fetchall()
            for row in result:
                self.av_results.append(row)

        # CASES AND FILES SEARCH
        # Default to all files if none are selected, otherwise limit to the selected files
        if self.case_ids != "":
            # Coded text
            sql = "select code_name.name, color, cases.name, "
            sql += "code_text.pos0, code_text.pos1, seltext, code_text.owner, code_text.fid from "
            sql += "code_text join code_name on code_name.cid = code_text.cid "
            sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
            sql += "code_text.fid = case_text.fid "
            sql += "where code_name.cid in (" + code_ids + ") "
            sql += "and case_text.caseid in (" + self.case_ids + ") "
            if self.file_ids != "":
                sql += " and code_text.fid in (" + self.file_ids + ")"
            sql += "and (code_text.pos0 >= case_text.pos0 and code_text.pos1 <= case_text.pos1)"
            if coder != "":
                sql += " and code_text.owner=? "
                parameters.append(coder)
            if search_text != "":
                sql += " and seltext like ? "
                parameters.append("%" + str(search_text) + "%")
            if parameters == []:
                cur.execute(sql)
            else:
                cur.execute(sql, parameters)
            result = cur.fetchall()
            for row in result:
                self.text_results.append(row)

            # Coded images
            parameters = []
            sql = "select code_name.name, color, cases.name, "
            sql += "x1, y1, width, height, code_image.owner,source.mediapath, source.id, "
            sql += "code_image.memo from "
            sql += "code_image join code_name on code_name.cid = code_image.cid "
            sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
            sql += "code_image.id = case_text.fid "
            sql += " join source on case_text.fid = source.id "
            sql += "where code_name.cid in (" + code_ids + ") "
            sql += "and case_text.caseid in (" + self.case_ids + ") "
            if self.file_ids != "":
                sql += " and source.id in (" + self.file_ids + ")"
            if coder != "":
                sql += " and code_image.owner=? "
                parameters.append(coder)
            if search_text != "":
                sql += " and code_image.memo like ? "
                parameters.append("%" + str(search_text) + "%")
            if parameters == []:
                cur.execute(sql)
            else:
                #logger.info("SQL:" + sql)
                #logger.info("Parameters:" + str(parameters))
                cur.execute(sql, parameters)
            result = cur.fetchall()
            for row in result:
                self.image_results.append(row)

            # Coded audio and video
            parameters = []
            sql = "select code_name.name, color, cases.name, "
            sql += "code_av.pos0, code_av.pos1, code_av.memo, code_av.owner,source.mediapath, "
            sql += "source.id from "
            sql += "code_av join code_name on code_name.cid = code_av.cid "
            sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
            sql += "code_av.id = case_text.fid "
            sql += " join source on case_text.fid = source.id "
            sql += "where code_name.cid in (" + code_ids + ") "
            sql += "and case_text.caseid in (" + self.case_ids + ") "
            if self.file_ids != "":
                sql += " and source.id in (" + self.file_ids + ")"
            if coder != "":
                sql += " and code_av.owner=? "
                parameters.append(coder)
            if search_text != "":
                sql += " and code_av.memo like ? "
                parameters.append("%" + str(search_text) + "%")
            if parameters == []:
                cur.execute(sql)
            else:
                #logger.info("SQL:" + sql)
                #logger.info("Parameters:" + str(parameters))
                cur.execute(sql, parameters)
            result = cur.fetchall()
            for row in result:
                self.av_results.append(row)

        # ATTRIBUTES ONLY SEARCH
        # get coded text and images from attribute selection
        if self.attribute_selection != []:
            logger.debug("attributes:" + str(self.attribute_selection))
            # convert each row into sql and add to case or file lists
            file_sql = []
            case_sql = []
            for a in self.attribute_selection:
                #print(a)
                sql = " select id from attribute where attribute.name = '" + a[0] + "' "
                sql += " and attribute.value " + a[3] + " "
                if a[3] in ('in', 'not in', 'between'):
                    sql += "("
                sql += ','.join(a[4])
                if a[3] in ('in', 'not in', 'between'):
                    sql += ")"
                if a[2] == 'numeric':
                    sql = sql.replace(' attribute.value ', ' cast(attribute.value as real) ')
                if a[1] == "file":
                    sql += " and attribute.attr_type='file' "
                    file_sql.append(sql)
                else:
                    sql += " and attribute.attr_type='case' "
                    case_sql.append(sql)

            # find file_ids matching criteria, nested sqls for each parameter
            sql = ""
            if len(file_sql) > 0:
                sql = file_sql[0]
                del file_sql[0]
            while len(file_sql) > 0:
                    sql += " and id in ( " + file_sql[0] + ") "
                    del file_sql[0]
            logger.debug(sql)
            cur.execute(sql)
            result = cur.fetchall()
            file_ids = ""
            for i in result:
                file_ids += "," + str(i[0])
            if len(file_ids) > 0:
                file_ids = file_ids[1:]
            logger.debug("file_ids: " + file_ids)

            # find case_ids matching criteria, nested sqls for each parameter
            # can get multiple case ids
            sql = ""
            if len(case_sql) > 0:
                sql = case_sql[0]
                del case_sql[0]
            while len(case_sql) > 0:
                    sql += " and id in ( " + case_sql[0] + ") "
                    del case_sql[0]
            logger.debug(sql)
            cur.execute(sql)
            result = cur.fetchall()
            case_ids = ""
            for i in result:
                case_ids += "," + str(i[0])
            if len(case_ids) > 0:
                case_ids = case_ids[1:]
            logger.debug("case_ids: " + case_ids)

            # text from attribute selection
            sql = ""
            # first sql is for cases with/without file parameters
            if case_ids != "":
                sql = "select code_name.name, color, cases.name, "
                sql += "code_text.pos0, code_text.pos1, seltext, code_text.owner, code_text.fid from "
                sql += "code_text join code_name on code_name.cid = code_text.cid "
                sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
                sql += "code_text.fid = case_text.fid "
                sql += "where code_name.cid in (" + code_ids + ") "
                sql += "and case_text.caseid in (" + case_ids + ") "
                sql += "and (code_text.pos0 >= case_text.pos0 and code_text.pos1 <= case_text.pos1) "
                if file_ids != "":
                    sql += "and code_text.fid in (" + file_ids + ") "
            else:
                # second sql is for file parameters only
                sql = "select code_name.name, color, source.name, pos0, pos1, seltext, "
                sql += "code_text.owner, fid from code_text join code_name "
                sql += "on code_name.cid = code_text.cid join source on fid = source.id "
                sql += "where code_name.cid in (" + code_ids + ") "
                sql += "and source.id in (" + file_ids + ") "
            if coder != "":
                sql += " and code_text.owner=? "
                parameters.append(coder)
            if search_text != "":
                sql += " and seltext like ? "
                parameters.append("%" + str(search_text) + "%")
            if parameters == []:
                cur.execute(sql)
            else:
                cur.execute(sql, parameters)
            result = cur.fetchall()
            for row in result:
                self.text_results.append(row)

            # images from attribute selection
            sql = ""
            # first sql is for cases with/without file parameters
            if case_ids != "":
                sql = "select code_name.name, color, cases.name, "
                sql += "x1, y1, width, height, code_image.owner,source.mediapath, source.id, code_image.memo "
                sql += "from code_image join code_name on code_name.cid = code_image.cid "
                sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
                sql += "code_image.id = case_text.fid "
                sql += " join source on case_text.fid = source.id "
                sql += "where code_name.cid in (" + code_ids + ") "
                sql += "and case_text.caseid in (" + case_ids + ") "
                if file_ids != "":
                    sql += "and case_text.fid in (" + file_ids + ") "
            else:
                # second sql is for file parameters only
                sql = "select code_name.name, color, source.name, x1, y1, width, height,"
                sql += "code_image.owner, source.mediapath, source.id, code_image.memo "
                sql += " from code_image join code_name "
                sql += "on code_name.cid = code_image.cid join source on code_image.id = source.id "
                sql += "where code_name.cid in (" + code_ids + ") "
                sql += "and source.id in (" + file_ids + ") "
            if coder != "":
                sql += " and code_image.owner=? "
            if search_text != "":
                sql += " and code_image.memo like ? "
                parameters.append("%" + str(search_text) + "%")
                parameters.append(coder)
            if parameters == []:
                cur.execute(sql)
            else:
                #logger.info("SQL:" + sql)
                #logger.info("Parameters:" + str(parameters))
                cur.execute(sql, parameters)
            result = cur.fetchall()
            for row in result:
                self.image_results.append(row)

            # audio and video from attribute selection
            sql = ""
            # first sql is for cases with/without file parameters
            if case_ids != "":
                sql = "select code_name.name, color, cases.name, "
                sql += "code_av.pos0, code_av.pos1, code_av.memo, code_av.owner,"
                sql += "source.mediapath, source.id from "
                sql += "code_av join code_name on code_name.cid = code_av.cid "
                sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
                sql += "code_av.id = case_text.fid "
                sql += " join source on case_text.fid = source.id "
                sql += "where code_name.cid in (" + code_ids + ") "
                sql += "and case_text.caseid in (" + case_ids + ") "
                if file_ids != "":
                    sql += "and case_text.fid in (" + file_ids + ") "
            else:
                # second sql is for file parameters only
                sql = "select code_name.name, color, source.name, code_av.pos0, "
                sql += "code_av.pos1, code_av.memo,"
                sql += "code_av.owner, source.mediapath, source.id from code_av join code_name "
                sql += "on code_name.cid = code_av.cid join source on code_av.id = source.id "
                sql += "where code_name.cid in (" + code_ids + ") "
                sql += "and source.id in (" + file_ids + ") "
            if coder != "":
                sql += " and code_av.owner=? "
                parameters.append(coder)
            if search_text != "":
                sql += " and code_av.memo like ? "
                parameters.append("%" + str(search_text) + "%")
            result = []
            if parameters == []:
                cur.execute(sql)
                result = cur.fetchall()
            else:
                #logger.debug("SQL:" + sql)
                try:
                    cur.execute(sql, parameters)
                    result = cur.fetchall()
                except Exception as e:
                    logger.debug(str(e))
                    logger.debug("SQL:\n" + sql)
                    logger.debug("Parameters:\n" + str(parameters))
            for row in result:
                self.av_results.append(row)

        self.fill_text_edit_with_search_results()

    def fill_text_edit_with_search_results(self):
        """ The textEdit.document is filled with the search results.
        Results are drawn from the textEdit.document to fill reports in .txt and .odt formats.
        Results are drawn from the textEdit.document and html_links variable to fill reports in html format.
        Results are drawn from self.text_results, self.image_results and self.av_results to prepare a csv file.
        The results are converted from tuples to dictionaries.
        As results are added to the textEdit, positions for the headings (code, file, codername) are recorded for
        right-click context menu to display contextualised coding in another dialog.
        """

        fileOrCase = ""  # default for attributes selection
        if self.file_ids != "":
            fileOrCase = "File"
        if self.case_ids != "":
            fileOrCase = "Case"

        # convert results to dictionaries for ease of use
        tmp = []
        for i in self.text_results:
            tmp.append({'codename': i[0], 'color': i[1], 'file_or_casename': i[2], 'pos0': i[3],
                'pos1': i[4], 'text': i[5], 'coder': i[6], 'fid': i[7], 'file_or_case': fileOrCase})
        self.text_results = tmp
        tmp = []
        for i in self.image_results:
            tmp.append({'codename': i[0], 'color': i[1], 'file_or_casename': i[2], 'x1': i[3],
                'y1': i[4], 'width': i[5], 'height': i[6], 'coder': i[7], 'mediapath': i[8],
                'fid': i[9], 'memo': i[10], 'file_or_case': fileOrCase})
        self.image_results = tmp
        tmp = []
        for i in self.av_results:
            # prepare additional text describing coded segment
            text = ""
            if i[7] is None:
                msg = "Should not have a None value for a/v media name.\n"
                msg += str(i)
                msg += "\nFirst backup project then: delete from code_av where id=" + str(i[9])
                QtWidgets.QMessageBox.information(None, _("No media name in AV results"), msg)
                logger.error("None value for a/v media name in AV results\n" + str(i))
            if i[7] is not None:
                text = i[7] + ": "
            secs0 = int(i[3] / 1000)
            mins = int(secs0 / 60)
            remainder_secs = str(secs0 - mins * 60)
            if len(remainder_secs) == 1:
                remainder_secs = "0" + remainder_secs
            text += " [" + str(mins) + ":" + remainder_secs
            secs1 = int(i[4] / 1000)
            mins = int(secs1 / 60)
            remainder_secs = str(secs1 - mins * 60)
            if len(remainder_secs) == 1:
                remainder_secs = "0" + remainder_secs
            text += " - " + str(mins) + ":" + remainder_secs + "]"
            self.html_links.append({'imagename': None, 'image': None,
                'avname': i[7], 'av0': str(secs0), 'av1': str(secs1), 'avtext': text})
            if len(i[5]) > 0:
                text += "\nMemo: " + i[5]
            tmp.append({'codename': i[0], 'color': i[1], 'file_or_casename': i[2],
            'pos0': i[3], 'pos1': i[4], 'memo': i[5], 'coder': i[6], 'mediapath': i[7],
                'fid': i[8], 'file_or_case': fileOrCase, 'text': text})
        self.av_results = tmp

        # Put results into the textEdit.document
        # Add textedit positioning for context on clicking appropriate heading in results
        # block signals of text cursor moving when filling text edit - stops context dialog appearing

        for row in self.text_results:
            row['textedit_start'] = len(self.ui.textEdit.toPlainText())
            self.ui.textEdit.insertHtml(self.html_heading(row))
            row['textedit_end'] = len(self.ui.textEdit.toPlainText())
            self.ui.textEdit.insertPlainText(row['text'] + "\n")
        for i, row in enumerate(self.image_results):
            row['textedit_start'] = len(self.ui.textEdit.toPlainText())
            self.ui.textEdit.insertHtml(self.html_heading(row))
            row['textedit_end'] = len(self.ui.textEdit.toPlainText())
            self.put_image_into_textedit(row, i, self.ui.textEdit)
        for i, row in enumerate(self.av_results):
            row['textedit_start'] = len(self.ui.textEdit.toPlainText())
            self.ui.textEdit.insertHtml(self.html_heading(row))
            row['textedit_end'] = len(self.ui.textEdit.toPlainText())
            self.ui.textEdit.insertPlainText(row['text'] + "\n")

        self.eventFilterTT.setTextResults(self.text_results)
        self.ui.textEdit.cursorPositionChanged.connect(self.show_context_of_clicked_heading)

        # Fill case matrix or clear third splitter pane.
        matrix_option = self.ui.comboBox_matrix.currentText()
        if self.case_ids == "":
            self.ui.splitter.replaceWidget(2, QtWidgets.QTableWidget())
        elif matrix_option == "Categories":
            self.fill_matrix_categories(self.text_results, self.image_results, self.av_results, self.case_ids)
        elif matrix_option == "Top categories":
            self.fill_matrix_top_categories(self.text_results, self.image_results, self.av_results, self.case_ids)
        else:
            self.fill_matrix_codes(self.text_results, self.image_results, self.av_results, self.case_ids)

    def put_image_into_textedit(self, img, counter, text_edit):
        """ Scale image, add resource to document, insert image.
        """

        path = self.app.project_path + img['mediapath']
        if img['mediapath'][0:7] == "images:":
            path = img['mediapath'][7:]
        document = text_edit.document()
        image = QtGui.QImageReader(path).read()
        image = image.copy(img['x1'], img['y1'], img['width'], img['height'])
        # scale to max 300 wide or high. perhaps add option to change maximum limit?
        scaler = 1.0
        scaler_w = 1.0
        scaler_h = 1.0
        if image.width() > 300:
            scaler_w = 300 / image.width()
        if image.height() > 300:
            scaler_h = 300 / image.height()
        if scaler_w < scaler_h:
            scaler = scaler_w
        else:
            scaler = scaler_h
        # Need unique image names or the same image from the same path is reproduced
        #print("REPORTS IMG MEDIAPATH", img['mediapath'])

        # Default for an image  stored in the project folder.
        #imagename = self.app.project_path + '/images/' + str(counter) + '-' + img['mediapath']
        imagename = str(counter) + '-' + img['mediapath']
        # Check and change path for a linked image file
        if img['mediapath'][0:7] == "images:":
            #imagename = self.app.project_path + '/images/' + str(counter) + '-' + "/images/" + img['mediapath'].split('/')[-1]
            imagename = str(counter) + '-' + "/images/" + img['mediapath'].split('/')[-1]
        # imagename is now:
        # 0-/images/filename.jpg  # where 0- is the counter 1-, 2- etc

        url = QtCore.QUrl(imagename)
        document.addResource(QtGui.QTextDocument.ImageResource, url, QtCore.QVariant(image))
        cursor = text_edit.textCursor()
        image_format = QtGui.QTextImageFormat()
        image_format.setWidth(image.width() * scaler)
        image_format.setHeight(image.height() * scaler)
        image_format.setName(url.toString())
        cursor.insertImage(image_format)
        text_edit.insertHtml("<br />")
        self.html_links.append({'imagename': imagename, 'image': image,
            'avname': None, 'av0': None, 'av1': None, 'avtext': None})
        if img['memo'] != "":
            text_edit.insertPlainText(_("Memo: ") + img['memo'] + "\n")

    def html_heading(self, item):
        """ Takes a dictionary item and creates a html heading for the coded text portion.
        param:
            item: dictionary of code, file_or_casename, positions, text, coder
        """

        cur = self.app.conn.cursor()
        cur.execute("select name from source where id=?", [item['fid']])
        filename = ""
        try:  # In case no filename results, rare possibility
            filename = cur.fetchone()[0]
        except:
            pass

        html = "<br />"
        html += _("[VIEW] ")
        html += "<em><span style=\"background-color:" + item['color'] + "\">"
        html += item['codename'] + "</span>, "
        html += _("File: ")  + filename + ", "
        html += " "+ item['file_or_case'] + ": " + item['file_or_casename']
        html += ", " + item['coder'] + "</em><br />"
        return html

    def show_context_of_clicked_heading(self):
        """ Heading (code, file, owner) in textEdit clicked so show context of coding in dialog.
        Called by: textEdit.cursorPositionChanged, after results are filled.
        text/image/av results contain textedit_start and textedit_end which map the cursor position to the specific result.
        """

        pos = self.ui.textEdit.textCursor().position()
        # Check the clicked position for a text result
        found = None
        for row in self.text_results:
            if pos >= row['textedit_start'] and pos < row['textedit_end']:
                ui = DialogCodeInText(self.app, row)
                ui.exec_()
                return
        # Check the position for an image result
        for row in self.image_results:
            if pos >= row['textedit_start'] and pos < row['textedit_end']:
                ui = DialogCodeInImage(self.app, row)
                ui.exec_()
                return
        # Check the position for an a/v result
        for row in self.av_results:
            if pos >= row['textedit_start'] and pos < row['textedit_end']:
                ui = DialogCodeInAV(self.app, row)
                ui.exec_()
                break

    def fill_matrix_codes(self, text_results, image_results, av_results, case_ids):
        """ Fill a tableWidget with rows of cases and columns of codes.
        First identify all codes.
        Fill tableWidget with columns of codes and rows of cases.
        Called by: fill_text_edit_with_search_results
        param:
            text_results : list of dictionary text result items
            image_results : list of dictionary image result items
            av_results : list of dictionary av result items
            case_ids : list of case ids
        """

        # Get selected codes (Matrix columns)
        items = self.ui.treeWidget.selectedItems()
        horizontal_labels = []  # column (code) labels
        for item in items:
            #print(item.text(0), item.text(1))
            if item.text(1)[:3] == "cid":
                horizontal_labels.append(item.text(0))  #, 'cid': item.text(1)})

        # Get cases (rows)
        cur = self.app.conn.cursor()
        cur.execute("select caseid, name from cases where caseid in (" + case_ids + ")")
        cases = cur.fetchall()
        vertical_labels = []
        for c in cases:
            vertical_labels.append(c[1])

        # Dynamically replace the existing table widget. Because, the tablewidget may
        # already have been replaced with a textEdit (file selection the view text in context)
        self.ta = QtWidgets.QTableWidget()
        self.ta.setColumnCount(len(horizontal_labels))
        self.ta.setHorizontalHeaderLabels(horizontal_labels)
        self.ta.setRowCount(len(cases))
        self.ta.setVerticalHeaderLabels(vertical_labels)
        # Tried lots of things to get the below signal to work.
        # Need to create a table of separate textEdits for reference for cursorPositionChanged event.
        # Gave up.
        self.te = []
        for row, case in enumerate(cases):
            inner = []
            for col, colname in enumerate(horizontal_labels):
                tedit = QtWidgets.QTextEdit("")
                tedit.setReadOnly(True)
                #tedit.cursorPositionChanged.connect(lambda: self.test_matrix_textEdit(tedit))
                inner.append(tedit)
            self.te.append(inner)
        for row, case in enumerate(cases):
            for col, colname in enumerate(horizontal_labels):
                '''self.te[row][col].setContextMenuPolicy(Qt.CustomContextMenu)
                self.te[row][col].customContextMenuRequested.connect(lambda: self.matrix_text_edit_menu(self.te[row][col]))'''
                for t in text_results:
                    if t['file_or_casename'] == vertical_labels[row] and t['codename'] == horizontal_labels[col]:
                        self.te[row][col].insertHtml(self.html_heading(t).replace("[VIEW]", ""))
                        self.te[row][col].insertPlainText(t['text'] + "\n")
                for a in av_results:
                    if a['file_or_casename'] == vertical_labels[row] and a['codename'] == horizontal_labels[col]:
                        self.te[row][col].insertHtml(self.html_heading(a).replace("[VIEW]", ""))
                        self.te[row][col].insertPlainText(a['text'] + "\n")
                for counter, i in enumerate(image_results):
                    if i['file_or_casename'] == vertical_labels[row] and i['codename'] == horizontal_labels[col]:
                        self.te[row][col].insertHtml(self.html_heading(i).replace("[VIEW]", ""))
                        self.put_image_into_textedit(i, counter, self.te[row][col])
                self.ta.setCellWidget(row, col, self.te[row][col])
        self.ta.resizeRowsToContents()
        self.ta.resizeColumnsToContents()
        # maximise the space from one column or one row
        if self.ta.columnCount() == 1:
            self.ta.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        if self.ta.rowCount() == 1:
            self.ta.verticalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.ui.splitter.replaceWidget(2, self.ta)
        self.ui.splitter.setSizes([100, 300, 300])

    def fill_matrix_categories(self, text_results, image_results, av_results, case_ids):
        """ Fill a tableWidget with rows of cases and columns of categories.
        First identify the categories. Then map all codes which are directly assigned to the categories.
        Fill tableWidget with columns of categories and rows of cases.
        Called by: fill_text_edit_with_search_results
        param:
            text_results : list of dictionary text result items
            image_results : list of dictionary image result items
            av_results : list of dictionary av result items
            case_ids : list of case ids
        """

        # G categories
        items = self.ui.treeWidget.selectedItems()
        top_level = []  # the categories at any level
        horizontal_labels = []
        sub_codes = []
        for item in items:
            #print(item.text(0), item.text(1), "root", root)
            if item.text(1)[0:3] == "cat":
                top_level.append({'name': item.text(0), 'cat': item.text(1)})
                horizontal_labels.append(item.text(0))
            # Find sub-code and traverse upwards to map to category
            if item.text(1)[0:3] == 'cid':
                #print("sub", item.text(0), item.text(1))
                not_top = True
                sub_code = {'codename': item.text(0), 'cid': item.text(1)}
                # May be None of a top level code - as this will have no parent
                if item.parent() is not None:
                    sub_code['top'] = item.parent().text(0)
                    sub_codes.append(sub_code)

        # Add category name - which will match the tableWidget column category name
        res_text_categories = []
        for i in text_results:
            # Replaces the top-level name by mapping to the correct top-level category name (column)
            # Codes will not have 'top' key
            for s in sub_codes:
                if i['codename'] == s['codename']:
                    i['top'] = s['top']
            if "top" in i:
                res_text_categories.append(i)

        res_image_categories = []
        for i in image_results:
            # Replaces the top-level name by mapping to the correct top-level category name (column)
            # Codes will not have 'top' key
            for s in sub_codes:
                if i['codename'] == s['codename']:
                    i['top'] = s['top']
            if "top" in i:
                res_image_categories.append(i)

        res_av_categories = []
        for i in av_results:
            # Replaces the top-level name by mapping to the correct top-level category name (column)
            # Codes will not have 'top' key
            for s in sub_codes:
                if i['codename'] == s['codename']:
                    i['top'] = s['top']
            if "top" in i:
                res_av_categories.append(i)

        cur = self.app.conn.cursor()
        cur.execute("select caseid, name from cases where caseid in (" + case_ids + ")")
        cases = cur.fetchall()
        vertical_labels = []
        for c in cases:
            vertical_labels.append(c[1])

        # Dynamically replace the existing table widget. Because, the tablewidget may
        # Already have been replaced with a textEdit (file selection the view text in context)
        ta = QtWidgets.QTableWidget()
        ta.setColumnCount(len(horizontal_labels))
        ta.setHorizontalHeaderLabels(horizontal_labels)
        ta.setRowCount(len(cases))
        ta.setVerticalHeaderLabels(vertical_labels)
        for row, case in enumerate(cases):
            for col, colname in enumerate(horizontal_labels):
                txt_edit = QtWidgets.QTextEdit("")
                txt_edit.setReadOnly(True)
                for t in res_text_categories:
                    if t['file_or_casename'] == vertical_labels[row] and t['top'] == horizontal_labels[col]:
                        txt_edit.insertHtml(self.html_heading(t).replace("[VIEW]", ""))
                        txt_edit.insertPlainText(t['text'] + "\n")
                for a in res_av_categories:
                    if a['file_or_casename'] == vertical_labels[row] and a['top'] == horizontal_labels[col]:
                        txt_edit.insertHtml(self.html_heading(a).replace("[VIEW]", ""))
                        txt_edit.insertPlainText(a['text'] + "\n")
                for counter, i in enumerate(res_image_categories):
                    if i['file_or_casename'] == vertical_labels[row] and i['top'] == horizontal_labels[col]:
                        txt_edit.insertHtml(self.html_heading(i).replace("[VIEW]", ""))
                        self.put_image_into_textedit(i, counter, txt_edit)
                ta.setCellWidget(row, col, txt_edit)
        ta.resizeRowsToContents()
        ta.resizeColumnsToContents()
        # Maximise the space from one column or one row
        if ta.columnCount() == 1:
            ta.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        if ta.rowCount() == 1:
            ta.verticalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.ui.splitter.replaceWidget(2, ta)
        self.ui.splitter.setSizes([100, 300, 300])

    def fill_matrix_top_categories(self, text_results, image_results, av_results, case_ids):
        """ Fill a tableWidget with rows of cases and columns of categories.
        First identify top-level categories. Then map all other codes to the
        top-level categories.
        Fill tableWidget with columns of top-level categories and rows of cases.
        Called by: fill_text_edit_with_search_results
        param:
            text_results : list of dictionary text result items
            image_results : list of dictionary image result items
            av_results : list of dictionary av result items
            case_ids : list of case ids
        """

        # get top level categories
        items = self.ui.treeWidget.selectedItems()
        top_level = []
        horizontal_labels = []
        sub_codes = []
        for item in items:
            root = self.ui.treeWidget.indexOfTopLevelItem(item)
            #print(item.text(0), item.text(1), "root", root)
            if root > -1 and item.text(1)[0:3] == "cat":
                top_level.append({'name': item.text(0), 'cat': item.text(1)})
                horizontal_labels.append(item.text(0))
            # Find sub-code and traverse upwards to map to top-level category
            if root == -1 and item.text(1)[0:3] == 'cid':
                #print("sub", item.text(0), item.text(1))
                not_top = True
                sub_code = {'codename': item.text(0), 'cid': item.text(1)}
                while not_top:
                    item = item.parent()
                    if self.ui.treeWidget.indexOfTopLevelItem(item) > -1:
                        not_top = False
                        sub_code['top'] = item.text(0)
                        sub_codes.append(sub_code)

        # Add the top-level name - which will match the tableWidget column category name
        res_text_categories = []
        for i in text_results:
            # Replaces the top-level name by mapping to the correct top-level category name (column)
            # Codes will not have 'top' key
            for s in sub_codes:
                if i['codename'] == s['codename']:
                    i['top'] = s['top']
            if "top" in i:
                res_text_categories.append(i)

        res_image_categories = []
        for i in image_results:
            # Replaces the top-level name by mapping to the correct top-level category name (column)
            # Codes will not have 'top' key
            for s in sub_codes:
                if i['codename'] == s['codename']:
                    i['top'] = s['top']
            if "top" in i:
                res_image_categories.append(i)

        res_av_categories = []
        for i in av_results:
            # Replaces the top-level name by mapping to the correct top-level category name (column)
            # Codes will not have 'top' key
            for s in sub_codes:
                if i['codename'] == s['codename']:
                    i['top'] = s['top']
            if "top" in i:
                res_av_categories.append(i)

        cur = self.app.conn.cursor()
        cur.execute("select caseid, name from cases where caseid in (" + case_ids + ")")
        cases = cur.fetchall()
        vertical_labels = []
        for c in cases:
            vertical_labels.append(c[1])

        # Dynamically replace the existing table widget. Because, the tablewidget may
        # Already have been replaced with a textEdit (file selection the view text in context)
        ta = QtWidgets.QTableWidget()
        ta.setColumnCount(len(horizontal_labels))
        ta.setHorizontalHeaderLabels(horizontal_labels)
        ta.setRowCount(len(cases))
        ta.setVerticalHeaderLabels(vertical_labels)
        for row, case in enumerate(cases):
            for col, colname in enumerate(horizontal_labels):
                txt_edit = QtWidgets.QTextEdit("")
                txt_edit.setReadOnly(True)
                for t in res_text_categories:
                    if t['file_or_casename'] == vertical_labels[row] and t['top'] == horizontal_labels[col]:
                        txt_edit.insertHtml(self.html_heading(t).replace("[VIEW]", ""))
                        txt_edit.insertPlainText(t['text'] + "\n")
                for a in res_av_categories:
                    if a['file_or_casename'] == vertical_labels[row] and a['top'] == horizontal_labels[col]:
                        txt_edit.insertHtml(self.html_heading(a).replace("[VIEW]", ""))
                        txt_edit.insertPlainText(a['text'] + "\n")
                for counter, i in enumerate(res_image_categories):
                    if i['file_or_casename'] == vertical_labels[row] and i['top'] == horizontal_labels[col]:
                        txt_edit.insertHtml(self.html_heading(i).replace("[VIEW]", ""))
                        self.put_image_into_textedit(i, counter, txt_edit)
                ta.setCellWidget(row, col, txt_edit)
        ta.resizeRowsToContents()
        ta.resizeColumnsToContents()
        # Maximise the space from one column or one row
        if ta.columnCount() == 1:
            ta.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        if ta.rowCount() == 1:
            ta.verticalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.ui.splitter.replaceWidget(2, ta)
        self.ui.splitter.setSizes([100, 300, 300])

    def select_attributes(self):
        """ Select attributes from case or file attributes for search method.
        Text values will be quoted.print("i[7]:  ", i[7])  # tmp
        """

        self.ui.splitter.setSizes([300, 300, 0])
        self.file_ids = ""
        for i in range(self.ui.listWidget_files.count()):
            self.ui.listWidget_files.item(i).setSelected(False)
        self.case_ids = ""
        for i in range(self.ui.listWidget_cases.count()):
            self.ui.listWidget_cases.item(i).setSelected(False)
        self.display_counts()
        ui = DialogSelectAttributeParameters(self.app)
        ok = ui.exec_()
        if not ok:
            self.attribute_selection = []
            return
        self.attribute_selection = ui.parameters
        label = _("Attributes: ")
        logger.debug("Attributes selected:" + str(self.attribute_selection))
        for att in self.attribute_selection:
            label += att[0] + " " + att[3] + " "
            label += ','.join(att[4])
            label += "| "
        self.display_counts()


class ToolTip_EventFilter(QtCore.QObject):
    """ Used to add a dynamic tooltip for the textEdit.
    wording to left click for context of text in the original file are displayed in the tooltip.
    """

    text_results = None

    def setTextResults(self, text_results):
        self.text_results = text_results

    def eventFilter(self, receiver, event):
        #QtGui.QToolTip.showText(QtGui.QCursor.pos(), tip)
        if event.type() == QtCore.QEvent.ToolTip:
            helpEvent = QHelpEvent(event)
            cursor = QtGui.QTextCursor()
            cursor = receiver.cursorForPosition(helpEvent.pos())
            pos = cursor.position()
            receiver.setToolTip("")
            if self.text_results is not None:
                for item in self.text_results:
                    if pos >= item['textedit_start'] and pos < item['textedit_end']:
                        msg = _("Click to view coding in the original file.")
                        receiver.setToolTip(msg)
        #Call Base Class Method to Continue Normal Event Processing
        return super(ToolTip_EventFilter, self).eventFilter(receiver, event)

