# -*- coding: utf-8 -*-

"""
Copyright (c) 2021 Colin Curtain

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

from copy import copy, deepcopy
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

from color_selector import TextColor
from GUI.base64_helper import *
from GUI.ui_dialog_report_codings import Ui_Dialog_reportCodings
from GUI.ui_dialog_report_comparisons import Ui_Dialog_reportComparisons
from GUI.ui_dialog_report_code_frequencies import Ui_Dialog_reportCodeFrequencies
from helpers import Message, msecs_to_hours_mins_secs, msecs_to_mins_and_secs, DialogCodeInImage, DialogCodeInAV, DialogCodeInText, ExportDirectoryPathDialog
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
    te = []  # Case matrix (table) [row][col] of textEditWidget results
    # Variables for search restrictions
    file_ids = ""
    case_ids = ""
    attribute_selection = []
    # Text positions in the main textEdit for right-click context menu to View original file
    text_links = []
    # Text positions in the matrix textEdits for right-click context menu to View original file
    # list of dictionaries of row, col, textEdit, list of links
    matrix_links = []

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
        doc_font = 'font: ' + str(self.app.settings['docfontsize']) + 'pt '
        doc_font += '"' + self.app.settings['font'] + '";'
        self.ui.textEdit.setStyleSheet(doc_font)
        self.ui.treeWidget.installEventFilter(self)  # For H key
        self.ui.label_counts.setStyleSheet(treefont)
        self.ui.listWidget_files.setStyleSheet(treefont)
        self.ui.listWidget_files.installEventFilter(self)  # For H key
        self.ui.listWidget_files.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.ui.listWidget_cases.setStyleSheet(treefont)
        self.ui.listWidget_cases.installEventFilter(self)  # For H key
        self.ui.listWidget_cases.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.ui.listWidget_cases.itemSelectionChanged.connect(self.case_selection_changed)
        self.ui.label_matrix.hide()
        self.ui.comboBox_matrix.setEnabled(False)
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
        self.ui.label_exports.setPixmap(pm.scaled(22, 22))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(a2x2_color_grid_icon_24), "png")
        self.ui.label_matrix.setPixmap(pm)
        options = [_("Top categories"), _("Categories"), _("Codes")]
        self.ui.comboBox_matrix.addItems(options)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(notepad_pencil_red_icon), "png")
        self.ui.label_memos.setPixmap(pm)
        options = [_("None"), _("Code text memos"), _("All memos"), _("Annotations")]
        self.ui.comboBox_memos.addItems(options)
        cur = self.app.conn.cursor()
        sql = "select count(name) from attribute_type"
        cur.execute(sql)
        res = cur.fetchone()
        if res[0] == 0:
            self.ui.pushButton_attributeselect.setEnabled(False)
        self.ui.pushButton_attributeselect.clicked.connect(self.select_attributes)
        self.ui.comboBox_export.currentIndexChanged.connect(self.export_option_selected)
        self.ui.comboBox_export.setEnabled(False)
        self.ui.textEdit.installEventFilter(self)  # for H key
        self.ui.textEdit.setReadOnly(True)
        self.ui.textEdit.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.textEdit.customContextMenuRequested.connect(self.textEdit_menu)
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
        self.eventFilterTT = ToolTip_EventFilter()
        self.ui.textEdit.installEventFilter(self.eventFilterTT)

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

        self.code_names, self.categories = self.app.get_codes_categories()
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
        # Add top level categories
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

        # Add unlinked codes as top level items
        remove_items = []
        for c in codes:
            if c['catid'] is None:
                #logger.debug("add unlinked code:" + c['name'])
                memo = ""
                if c['memo'] != "":
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                top_item.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.SolidPattern))
                color = TextColor(c['color']).recommendation
                top_item.setForeground(0, QBrush(QtGui.QColor(color)))
                top_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)  # | Qt.ItemIsDragEnabled)
                top_item.setToolTip(2, c['memo'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)

        # Add codes as children
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
                    color = TextColor(c['color']).recommendation
                    child.setForeground(0, QBrush(QtGui.QColor(color)))
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
        filename = "Report_codings.txt"
        e = ExportDirectoryPathDialog(self.app, filename)
        filepath = e.filepath
        if filepath is None:
            return
        ''' https://stackoverflow.com/questions/39422573/python-writing-weird-unicode-to-csv
        Using a byte order mark so that other software recognises UTF-8
        '''
        data = self.ui.textEdit.toPlainText()
        f = open(filepath, 'w', encoding='utf-8-sig')
        f.write(data)
        f.close()
        msg = _('Report exported: ') + filepath
        Message(self.app, _('Report exported'), msg, "information").exec_()
        self.parent_textEdit.append(msg)

    def export_odt_file(self):
        """ Export report to open document format with .odt ending.
        QTextWriter supports plaintext, ODF and HTML .
        """

        if len(self.ui.textEdit.document().toPlainText()) == 0:
            return
        filename = "Report_codings.odt"
        e = ExportDirectoryPathDialog(self.app, filename)
        filepath = e.filepath
        if filepath is None:
            return
        tw = QtGui.QTextDocumentWriter()
        tw.setFileName(filepath)
        tw.setFormat(b'ODF')  # byte array needed for Windows 10
        tw.write(self.ui.textEdit.document())
        msg = _("Report exported: ") + filepath
        self.parent_textEdit.append(msg)
        Message(self.app, _('Report exported'), msg, "information").exec_()

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
        filename = "Report_codings.csv"
        e = ExportDirectoryPathDialog(self.app, filename)
        filepath = e.filepath
        if filepath is None:
            return
        with open(filepath, 'w', encoding ='utf-8-sig', newline='') as csvfile:
            filewriter = csv.writer(csvfile, delimiter=',',
                quotechar='"', quoting=csv.QUOTE_MINIMAL)
            filewriter.writerow(codes_set)  # header row
            for row in csv_data:
                filewriter.writerow(row)
        msg = _('Report exported: ') + filepath
        Message(self.app, _('Report exported'), msg, "information").exec_()
        self.parent_textEdit.append(msg)

    def export_html_file(self):
        """ Export report to a html file. Create folder of images and change refs to the
        folder.
        TODO: Possibly have picture data in base64 so there is no need for a separate folder.
        TODO: REVIEW HTML EXPORT - some errors with images and a/v
        """

        if len(self.ui.textEdit.document().toPlainText()) == 0:
            return
        filename = "Report_codings.html"
        e = ExportDirectoryPathDialog(self.app, filename)
        filepath = e.filepath
        if filepath is None:
            return
        tw = QtGui.QTextDocumentWriter()
        tw.setFileName(filepath)
        tw.setFormat(b'HTML')  # byte array needed for Windows 10
        tw.setCodec(QTextCodec.codecForName('UTF-8'))  # for Windows 10
        tw.write(self.ui.textEdit.document())

        need_media_folders = False
        for item in self.html_links:
            if item['image'] is not None or item['avname'] is not None:
                need_media_folders = True
        if need_media_folders:
            # Create folder of images and media and change html links
            foldername = filepath[:-5]
            foldername_without_path = foldername.split('/')[-1]
            try:
                os.mkdir(foldername)
                os.mkdir(foldername + "/audio")
                os.mkdir(foldername + "/video")
            except Exception as e:
                logger.warning(_("html folder creation error ") + str(e))
                Message(self.app, _("Folder creation"), foldername + _(" error ") + str(e), "critical").exec_()
                return
        html = ""
        try:
            with open(filepath, 'r') as f:
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
                this needs to be upper case for the replace method to work:  c:  =>  C: '''
                #TODO Check, this may fail on Windows now
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
                    Message(self.app, _("HTML folder creation error"), str(e), "warning").exec_()

        with open(filepath, 'w', encoding='utf-8-sig') as f:
            f.write(html)
        msg = _("Report exported to: ") + filepath
        if need_media_folders:
            msg += "\n" + _("Media folder: ") + foldername
        self.parent_textEdit.append(msg)
        Message(self.app, _('Report exported'), msg, "information").exec_()

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

    def case_selection_changed(self):
        """ Show or hide the case matrix options.
         Show if cases are selected. """

        self.ui.label_matrix.hide()
        self.ui.comboBox_matrix.setEnabled(False)
        for item in self.ui.listWidget_cases.selectedItems():
            if item.text() != "":
                self.ui.label_matrix.show()
                self.ui.comboBox_matrix.setEnabled(True)

    def search(self):
        """ Search for selected codings.
        There are three main search pathways.
        1:  file selection only.
        2: case selection combined with files selection. (No files selected presumes ALL files)
        3: attribute selection, which may include files or cases.
        """

        # Get variables for search: search text, coders, codes, files,cases, attributes
        coder = self.ui.comboBox_coders.currentText()
        self.html_links = []  # For html file output with media
        search_text = self.ui.lineEdit.text()
        self.get_selected_files_and_cases()

        # Select all code items under selected categories
        self.recursive_set_selected(self.ui.treeWidget.invisibleRootItem())
        items = self.ui.treeWidget.selectedItems()
        if len(items) == 0:
            msg = _("No codes have been selected.")
            Message(self.app, _('No codes'), msg, "warning").exec_()
            return
        if self.file_ids == "" and self.case_ids == "" and self.attribute_selection == []:
            msg = _("No files, cases or attributes have been selected.")
            Message(self.app, _('Nothing selected'), msg, "warning").exec_()
            return

        # Prepare results table and results lists
        rows = self.ui.tableWidget.rowCount()
        for r in range(0, rows):
            self.ui.tableWidget.removeRow(0)
        self.text_results = []
        self.image_results = []
        self.av_results = []

        file_or_case = ""  # Default for attributes selection
        if self.file_ids != "":
            file_or_case = "File"
        if self.case_ids != "":
            file_or_case = "Case"

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
        important = self.ui.checkBox_important.isChecked()

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
        self.html_links = []

        # FILES ONLY SEARCH
        parameters = []
        if self.file_ids != "" and self.case_ids == "":
            # Coded text
            sql = "select code_name.name, color, source.name, pos0, pos1, seltext, "
            sql += "code_text.owner, fid, code_text.memo, code_name.memo, source.memo "
            sql += " from code_text join code_name "
            sql += "on code_name.cid = code_text.cid join source on fid = source.id "
            sql += "where code_name.cid in (" + code_ids + ") "
            sql += "and source.id in (" + self.file_ids + ") "
            if coder != "":
                sql += " and code_text.owner=? "
                parameters.append(coder)
            if search_text != "":
                sql += " and seltext like ? "
                parameters.append("%" + str(search_text) + "%")
            if important:
                sql += " and code_text.important=1 "
            if parameters == []:
                cur.execute(sql)
            else:
                #logger.info("SQL:" + sql)
                #logger.info("Parameters:" + str(parameters))
                cur.execute(sql, parameters)
            result = cur.fetchall()
            keys = 'codename', 'color', 'file_or_casename', 'pos0', 'pos1', 'text', 'coder', 'fid', 'coded_memo', 'codename_memo', 'source_memo'
            for row in result:
                self.text_results.append(dict(zip(keys, row)))
            for r in self.text_results:
                r['file_or_case'] = file_or_case

            # Coded images
            parameters = []
            sql = "select code_name.name, color, source.name, x1, y1, width, height,"
            sql += "code_image.owner, source.mediapath, source.id, code_image.memo, "
            sql += "code_name.memo, source.memo "
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
            if important:
                sql += " and code_image.important=1 "
            if parameters == []:
                cur.execute(sql)
            else:
                #logger.info("SQL:" + sql)
                #logger.info("Parameters:" + str(parameters))
                cur.execute(sql, parameters)
            result = cur.fetchall()
            keys = 'codename', 'color', 'file_or_casename', 'x1', 'y1', 'width', 'height', 'coder', 'mediapath', 'fid', \
                   'coded_memo', 'codename_memo', 'source_memo'
            for row in result:
                self.image_results.append(dict(zip(keys, row)))
            for r in self.image_results:
                r['file_or_case'] = file_or_case

            # Coded audio and video, also looks for search_text in coded segment memo
            parameters = []
            sql = "select code_name.name, color, source.name, pos0, pos1, code_av.memo, "
            sql += " code_av.owner, source.mediapath, source.id, code_name.memo, source.memo "
            sql += " from code_av join code_name "
            sql += "on code_name.cid = code_av.cid join source on code_av.id = source.id "
            sql += "where code_name.cid in (" + code_ids + ") "
            sql += "and source.id in (" + self.file_ids + ") "
            if coder != "":
                sql += " and code_av.owner=? "
                parameters.append(coder)
            if search_text != "":
                sql += " and code_av.memo like ? "
                parameters.append("%" + str(search_text) + "%")
            if important:
                sql += " and code_av.important=1 "
            if parameters == []:
                cur.execute(sql)
            else:
                #logger.info("SQL:" + sql)
                #logger.info("Parameters:" + str(parameters))
                cur.execute(sql, parameters)
            result = cur.fetchall()
            keys = 'codename', 'color', 'file_or_casename', 'pos0', 'pos1', 'coded_memo', 'coder', 'mediapath', 'fid',\
                   'codename_memo', 'source_memo'
            for row in result:
                self.av_results.append(dict(zip(keys, row)))
            for r in self.av_results:
                r['file_or_case'] = file_or_case
                if r['file_or_casename'] is None:
                    msg = _("Backup project then: delete from code_av where ") + "id=" + str(i[9])
                    Message(self.app, _("No media name in AV results"), msg, "warning").exec_()
                    logger.error("None value for a/v media name in AV results\n" + str(i))
                text = str(r['file_or_casename']) + " "
                if len(r['coded_memo']) > 0:
                    text += "\nMemo: " + r['coded_memo']
                text += " " + msecs_to_hours_mins_secs(r['pos0']) +" - " + msecs_to_hours_mins_secs(r['pos1'])
                r['text'] = text
                self.html_links.append({'imagename': None, 'image': None,
                    'avname': r['mediapath'], 'av0': str(int(r['pos0'] / 1000)), 'av1': str(int(r['pos1'] / 1000)), 'avtext': text})

        # CASES AND FILES SEARCH
        # Default to all files if none are selected, otherwise limit to the selected files
        if self.case_ids != "":
            # Coded text
            sql = "select code_name.name, color, cases.name, "
            sql += "code_text.pos0, code_text.pos1, seltext, code_text.owner, code_text.fid, "
            sql += "cases.memo, code_text.memo, code_name.memo, source.memo "
            sql += "from code_text join code_name on code_name.cid = code_text.cid "
            sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
            sql += "code_text.fid = case_text.fid "
            sql += "join source on source.id=code_text.fid "
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
            results = cur.fetchall()
            keys = 'codename', 'color', 'file_or_casename', 'pos0', 'pos1', 'text', 'coder', 'fid', \
                   'cases_memo', 'coded_memo', 'codename_memo', 'source_memo'
            for row in results:
                self.text_results.append(dict(zip(keys, row)))
            for r in self.text_results:
                r['file_or_case'] = file_or_case

            # Coded images
            parameters = []
            sql = "select code_name.name, color, cases.name, "
            sql += "x1, y1, width, height, code_image.owner,source.mediapath, source.id, "
            sql += "code_image.memo, cases.memo, code_name.memo, source.memo from "
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
            imgresults = cur.fetchall()
            keys = 'codename', 'color', 'file_or_casename', 'x1', 'y1', 'width', 'height', 'coder', 'mediapath', 'fid', \
                   'coded_memo', 'case_memo', 'codename_memo', 'source_memo'
            for row in imgresults:
                self.image_results.append(dict(zip(keys, row)))
            for r in self.image_results:
                r['file_or_case'] = file_or_case

            # Coded audio and video
            avresults = []
            parameters = []
            av_sql = "select distinct code_name.name, color, cases.name as case_name, "
            av_sql += "code_av.pos0, code_av.pos1, code_av.owner,source.mediapath, source.id, "
            av_sql += "code_av.memo as coded_memo, cases.memo as case_memo, code_name.memo, source.memo "
            av_sql += " from code_av join code_name on code_name.cid = code_av.cid "
            av_sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
            av_sql += "code_av.id = case_text.fid "
            av_sql += " join source on case_text.fid = source.id "
            av_sql += "where code_name.cid in (" + code_ids + ") "
            av_sql += "and case_text.caseid in (" + self.case_ids + ") "
            if self.file_ids != "":
                av_sql += " and source.id in (" + self.file_ids + ")"
            if coder != "":
                av_sql += " and code_av.owner=? "
                parameters.append(coder)
            if search_text != "":
                av_sql += " and code_av.memo like ? "
                parameters.append("%" + str(search_text) + "%")
            if parameters == []:
                cur.execute(av_sql)
            else:
                #logger.info("SQL:" + av_sql + "\nParameters:" + str(parameters))
                cur.execute(av_sql, parameters)
            avresults = cur.fetchall()
            keys = 'codename', 'color', 'file_or_casename', 'pos0', 'pos1', \
                   'coder', 'mediapath', 'fid', 'coded_memo', 'case_memo', 'codename_memo', 'source_memo'
            for row in avresults:
                self.av_results.append(dict(zip(keys, row)))
            for r in self.av_results:
                r['file_or_case'] = file_or_case
                if r['file_or_casename'] is None:
                    msg = _("Backup project then: delete from code_av where ") + "id=" + str(i[9])
                    Message(self.app, _("No media name in AV results"), msg, "warning").exec_()
                    logger.error("None value for a/v media name in AV results\n" + str(i))
                text = str(r['file_or_casename']) + " "
                if len(r['coded_memo']) > 0:
                    text += "\nMemo: " + r['coded_memo']
                text += " " + msecs_to_hours_mins_secs(r['pos0']) + " - " + msecs_to_hours_mins_secs(r['pos1'])
                r['text'] = text
                self.html_links.append({'imagename': None, 'image': None,
                                        'avname': r['mediapath'], 'av0': str(int(r['pos0'] / 1000)),
                                        'av1': str(int(r['pos1'] / 1000)), 'avtext': text})

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

            # Find file_ids matching criteria, nested sqls for each parameter
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

            # Find case_ids matching criteria, nested sqls for each parameter
            # Can get multiple case ids
            sql = ""
            if len(case_sql) > 0:
                sql = case_sql[0]
                del case_sql[0]
            while len(case_sql) > 0:
                    sql += " and id in ( " + case_sql[0] + ") "
                    del case_sql[0]
            #logger.debug(sql)
            cur.execute(sql)
            results = cur.fetchall()
            case_ids = ""
            for i in results:
                case_ids += "," + str(i[0])
            if len(case_ids) > 0:
                case_ids = case_ids[1:]
            #logger.debug("case_ids: " + case_ids)

            # Text from attribute selection
            sql = ""
            # first sql is for cases with/without file parameters
            if case_ids != "":
                sql = "select code_name.name, color, cases.name, "
                sql += "code_text.pos0, code_text.pos1, seltext, code_text.owner, code_text.fid, "
                sql += "code_text.memo, cases.memo, code_name.memo, source.memo "
                sql += "from code_text join code_name on code_name.cid=code_text.cid "
                sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
                sql += "code_text.fid = case_text.fid "
                sql += "join source on source.id=code_text.fid "
                sql += "where code_name.cid in (" + code_ids + ") "
                sql += "and case_text.caseid in (" + case_ids + ") "
                sql += "and (code_text.pos0 >= case_text.pos0 and code_text.pos1 <= case_text.pos1) "
                if file_ids != "":
                    sql += "and code_text.fid in (" + file_ids + ") "
            else:
                # This sql is for file parameters only
                sql = "select code_name.name, color, source.name, pos0, pos1, seltext, "
                sql += "code_text.owner, fid, code_text.memo, code_name.memo, source.memo "
                sql += "from code_text join code_name "
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
            results = cur.fetchall()
            keys = 'codename', 'color', 'file_or_casename', 'pos0', 'pos1', 'text', 'coder', 'fid', 'coded_memo', 'codename_memo', 'source_memo'
            for row in results:
                self.text_results.append(dict(zip(keys, row)))
            for r in self.text_results:
                r['file_or_case'] = file_or_case

            # Images from attribute selection
            sql = ""
            # first sql is for cases with/without file parameters
            if case_ids != "":
                sql = "select code_name.name, color, cases.name, "
                sql += "x1, y1, width, height, code_image.owner,source.mediapath, source.id, code_image.memo, "
                sql += " code_name.memo, source.memo "
                sql += "from code_image join code_name on code_name.cid = code_image.cid "
                sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
                sql += "code_image.id = case_text.fid "
                sql += " join source on case_text.fid = source.id "
                sql += "where code_name.cid in (" + code_ids + ") "
                sql += "and case_text.caseid in (" + case_ids + ") "
                if file_ids != "":
                    sql += "and case_text.fid in (" + file_ids + ") "
            else:
                # This sql is for file parameters only
                sql = "select code_name.name, color, source.name, x1, y1, width, height,"
                sql += "code_image.owner, source.mediapath, source.id, code_image.memo, "
                sql += " code_name.memo, source.memo "
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
            imgresults = cur.fetchall()
            keys = 'codename', 'color', 'file_or_casename', 'x1', 'y1', 'width', 'height', 'coder', 'mediapath', 'fid', \
                   'coded_memo', 'codename_memo', 'source_memo'
            for row in imgresults:
                self.image_results.append(dict(zip(keys, row)))
            for r in self.image_results:
                r['file_or_case'] = file_or_case

            # Audio and video from attribute selection
            sql = ""
            # First sql is for cases with/without file parameters
            if case_ids != "":
                sql = "select code_name.name, color, cases.name, "
                sql += "code_av.pos0, code_av.pos1, code_av.memo, code_av.owner,"
                sql += "source.mediapath, source.id, code_name.memo, source.memo "
                sql += "from code_av join code_name on code_name.cid = code_av.cid "
                sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
                sql += "code_av.id = case_text.fid "
                sql += " join source on case_text.fid = source.id "
                sql += "where code_name.cid in (" + code_ids + ") "
                sql += "and case_text.caseid in (" + case_ids + ") "
                if file_ids != "":
                    sql += "and case_text.fid in (" + file_ids + ") "
            else:
                # This sql is for file parameters only
                sql = "select code_name.name, color, source.name, code_av.pos0, "
                sql += "code_av.pos1, code_av.memo,"
                sql += "code_av.owner, source.mediapath, source.id,  code_name.memo, source.memo "
                sql += "from code_av join code_name "
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
            keys = 'codename', 'color', 'file_or_casename', 'pos0', 'pos1', 'coded_memo', 'coder', 'mediapath', 'fid',\
                   'codename_memo', 'source_memo'
            for row in result:
                self.av_results.append(dict(zip(keys, row)))
            for r in self.av_results:
                r['file_or_case'] = file_or_case
                if r['file_or_casename'] is None:
                    msg = _("Backup project then: delete from code_av where ") + "id=" + str(i[9])
                    Message(self.app, _("No media name in AV results"), msg, "warning").exec_()
                    logger.error("None value for a/v media name in AV results\n" + str(i))
                text = str(r['file_or_casename']) + " "
                if len(r['coded_memo']) > 0:
                    text += "\nMemo: " + r['coded_memo']
                text += " " + msecs_to_hours_mins_secs(r['pos0']) +" - " + msecs_to_hours_mins_secs(r['pos1'])
                r['text'] = text
                self.html_links.append({'imagename': None, 'image': None,
                    'avname': r['mediapath'], 'av0': str(int(r['pos0'] / 1000)), 'av1': str(int(r['pos1'] / 1000)), 'avtext': text})
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

        #TODO memo choices = _("None"), _("Coding memos"), _("All memos"), _("Annotations"), _("All")
        #self.ui.comboBox_memos

        self.text_links = []
        self.matrix_links = []

        # Put results into the textEdit.document
        # Add textedit positioning for context on clicking appropriate heading in results
        choice = self.ui.comboBox_memos.currentText()
        for row in self.text_results:
            self.heading(row)
            self.ui.textEdit.insertPlainText(row['text'] + "\n")
            if choice in ("All memos", "Code text memos") and row['coded_memo'] != "":
                self.ui.textEdit.insertPlainText(_("Coded memo: ") + row['coded_memo'] + "\n")
            self.text_links.append(row)
        for i, row in enumerate(self.image_results):
            self.heading(row)
            self.put_image_into_textedit(row, i, self.ui.textEdit)
            self.text_links.append(row)
        for i, row in enumerate(self.av_results):
            self.heading(row)
            self.ui.textEdit.insertPlainText(row['text'] + "\n")
            self.text_links.append(row)

        self.eventFilterTT.set_positions(self.text_links)

        # Fill case matrix or clear third splitter pane.
        matrix_option = self.ui.comboBox_matrix.currentText()
        if self.case_ids == "":
            self.ui.tableWidget.setColumnCount(0)
            self.ui.tableWidget.setRowCount(0)
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
        # Scale to max 300 wide or high. perhaps add option to change maximum limit?
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
        if img['coded_memo'] != "":
            text_edit.insertPlainText(_("Memo: ") + img['coded_memo'] + "\n")

    def heading(self, item):
        """ Takes a dictionary item and creates a html heading for the coded text portion.
        Inserts the heading into the main textEdit.
        Fills the textedit_start and textedit_end link positions
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

        head = "\n" + _("[VIEW] ")
        head += item['codename'] + ", "
        choice = self.ui.comboBox_memos.currentText()
        if choice == "All memos" and item['codename_memo'] != "":
            head += _("Code memo: ") + item['codename_memo'] + "<br />"
        head += _("File: ") + filename + ", "
        if choice == "All memos" and item['source_memo'] != "":
            head += _(" File memo: ") + item['source_memo']
        if item['file_or_case'] == 'Case':
            head += " " + _("Case: " ) + item['file_or_casename']
            if choice == "All memos":
                cur = self.app.conn.cursor()
                cur.execute("select memo from cases where name=?", [item['file_or_casename']])
                res = cur.fetchone()
                if res is not None and res != "":
                    head += ", " + _("Case memo: ") + res[0]
        head += ", " + _("Coder: ") + item['coder'] + "<br />"

        cursor = self.ui.textEdit.textCursor()
        fmt = QtGui.QTextCharFormat()
        pos0 = len(self.ui.textEdit.toPlainText())
        item['textedit_start'] = pos0
        #self.ui.textEdit.append(self.heading(row))
        self.ui.textEdit.append(head)
        cursor.setPosition(pos0, QtGui.QTextCursor.MoveAnchor)
        pos1 = len(self.ui.textEdit.toPlainText())
        cursor.setPosition(pos1, QtGui.QTextCursor.KeepAnchor)
        brush = QBrush(QtGui.QColor(item['color']))
        fmt.setBackground(brush)
        text_brush = QBrush(QtGui.QColor(TextColor(item['color']).recommendation))
        fmt.setForeground(text_brush)
        cursor.setCharFormat(fmt)
        item['textedit_end'] = len(self.ui.textEdit.toPlainText())

    def textEdit_menu(self, position):
        """ Context menu for textEdit.
        To view coded in context. """

        if self.ui.textEdit.toPlainText() == "":
            return
        cursor_context_pos = self.ui.textEdit.cursorForPosition(position)
        pos = cursor_context_pos.position()
        selected_text = self.ui.textEdit.textCursor().selectedText()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")

        # Check that there is a link to view at this location before showing menu option
        action_view = None
        found = None
        for row in self.text_results:
            if pos >= row['textedit_start'] and pos < row['textedit_end']:
                found = True
                break
        for row in self.image_results:
            if pos >= row['textedit_start'] and pos < row['textedit_end']:
                found = True
                break
        for row in self.av_results:
            if pos >= row['textedit_start'] and pos < row['textedit_end']:
                found = True
                break
        if found:
            action_view = menu.addAction(_("View in context"))

        action_copy = None
        if selected_text != "":
            action_copy = menu.addAction(_("Copy to clipboard"))
        action_copy_all = menu.addAction(_("Copy all to clipboard"))
        action = menu.exec_(self.ui.textEdit.mapToGlobal(position))
        if action is None:
            return
        if action == action_view:
            self.show_context_from_text_edit(cursor_context_pos)
        if action == action_copy:
            cb = QtWidgets.QApplication.clipboard()
            cb.clear(mode=cb.Clipboard)
            cb.setText(selected_text, mode=cb.Clipboard)
        if action == action_copy_all:
            cb = QtWidgets.QApplication.clipboard()
            cb.clear(mode=cb.Clipboard)
            text = self.ui.textEdit.toPlainText()
            cb.setText(text, mode=cb.Clipboard)

    def show_context_from_text_edit(self, cursor_context_pos):
        """ Heading (code, file, owner) in textEdit clicked so show context of coding in dialog.
        Called by: textEdit.cursorPositionChanged, after results are filled.
        text/image/av results contain textedit_start and textedit_end which map the cursor position to the specific result.
        Called by context menu.
        """

        pos = cursor_context_pos.position()
        # Check the clicked position for a text result
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
                return

    def matrix_heading(self, item, textEdit):
        """ Takes a dictionary item and creates a heading for the coded text portion.
        Also adds the textEdit start and end character positions for this text in this text edit
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
        choice = self.ui.comboBox_memos.currentText()
        head = "\n" + _("[VIEW] ")
        head += item['codename'] + ", "
        if choice == "All memos" and item['codename_memo'] != "":
            head += _("Code memo: ") + item['codename_memo'] + "<br />"
        head += _("File: ") + filename + ", "
        if choice == "All memos" and item['source_memo'] != "":
            head += _(" File memo: ") + item['source_memo']
        if item['file_or_case'] == 'Case:':
            head += " " + item['file_or_case'] + ": " + item['file_or_casename'] + ", "
            if choice == "All memos":
                cur = self.app.conn.cursor()
                cur.execute("select memo from cases where name=?", [item['file_or_casename']])
                res = cur.fetchone()
                if res is not None and res != "":
                    head += ", " + _("Case memo: ") + res[0]
        head += item['coder'] + "\n"

        cursor = textEdit.textCursor()
        fmt = QtGui.QTextCharFormat()
        pos0 = len(textEdit.toPlainText())
        item['textedit_start'] = pos0
        #self.ui.textEdit.append(self.heading(row))
        textEdit.append(head)
        cursor.setPosition(pos0, QtGui.QTextCursor.MoveAnchor)
        pos1 = len(textEdit.toPlainText())
        cursor.setPosition(pos1, QtGui.QTextCursor.KeepAnchor)
        brush = QBrush(QtGui.QColor(item['color']))
        fmt.setBackground(brush)
        text_brush = QBrush(QtGui.QColor(TextColor(item['color']).recommendation))
        fmt.setForeground(text_brush)
        cursor.setCharFormat(fmt)
        item['textedit_end'] = len(textEdit.toPlainText())

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

        # Do not overwrite positions in original text_links object
        text_results = deepcopy(text_results)
        image_results = deepcopy(image_results)
        av_results = deepcopy(av_results)

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

        # Clear and fill tableWidget
        doc_font = 'font: ' + str(self.app.settings['docfontsize']) + 'pt '
        doc_font += '"' + self.app.settings['font'] + '";'
        self.ui.tableWidget.setStyleSheet(doc_font)
        self.ui.tableWidget.setColumnCount(len(horizontal_labels))
        self.ui.tableWidget.setHorizontalHeaderLabels(horizontal_labels)
        self.ui.tableWidget.setRowCount(len(cases))
        self.ui.tableWidget.setVerticalHeaderLabels(vertical_labels)
        # Need to create a table of separate textEdits for reference for cursorPositionChanged event.
        self.te = []
        for row, case in enumerate(cases):
            column_list = []
            for col, colname in enumerate(horizontal_labels):
                tedit = QtWidgets.QTextEdit("")
                tedit.setReadOnly(True)
                tedit.setContextMenuPolicy(Qt.CustomContextMenu)
                tedit.customContextMenuRequested.connect(self.table_textEdit_menu)
                column_list.append(tedit)
            self.te.append(column_list)
        self.matrix_links = []
        choice = self.ui.comboBox_memos.currentText()
        for row, case in enumerate(cases):
            for col, colname in enumerate(horizontal_labels):
                for t in text_results:
                    if t['file_or_casename'] == vertical_labels[row] and t['codename'] == horizontal_labels[col]:
                        t['row'] = row
                        t['col'] = col
                        self.te[row][col].append(self.matrix_heading(t, self.te[row][col]))
                        if choice in ("All memos", "Code text memos") and row['coded_memo'] != "":
                            self.ui.textEdit.insertPlainText("\n" + _("Coded memo: ") + row['coded_memo'] + "\n")
                        self.matrix_links.append(t)
                        self.te[row][col].insertPlainText(t['text'] + "\n" + _("Coded memo: ") + row['coded_memo'] + "\n")
                for av in av_results:
                    if av['file_or_casename'] == vertical_labels[row] and av['codename'] == horizontal_labels[col]:
                        av['row'] = row
                        av['col'] = col
                        self.te[row][col].append(self.matrix_heading(av, self.te[row][col]))
                        self.matrix_links.append(av)
                        self.te[row][col].insertPlainText(av['text'] + "\n")
                for counter, im in enumerate(image_results):
                    if im['file_or_casename'] == vertical_labels[row] and im['codename'] == horizontal_labels[col]:
                        im['row'] = row
                        im['col'] = col
                        self.te[row][col].append(self.matrix_heading(im, self.te[row][col]))
                        self.matrix_links.append(im)
                        self.put_image_into_textedit(im, counter, self.te[row][col])
                self.ui.tableWidget.setCellWidget(row, col, self.te[row][col])
        self.ui.tableWidget.resizeRowsToContents()
        self.ui.tableWidget.resizeColumnsToContents()
        # maximise the space from one column or one row
        if self.ui.tableWidget.columnCount() == 1:
            self.ui.tableWidget.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        if self.ui.tableWidget.rowCount() == 1:
            self.ui.tableWidget.verticalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
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

        # Do not overwrite positions in original text_links object
        text_results = deepcopy(text_results)
        image_results = deepcopy(image_results)
        av_results = deepcopy(av_results)

        # All categories within selection
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
                    add_cat = True
                    for tl in top_level:
                        if tl['name'] == item.parent().text(0):
                            add_cat = False
                    if add_cat:
                        top_level.append({'name': item.parent().text(0), 'cat': item.parent().text(1)})
                        horizontal_labels.append(item.parent().text(0))

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

        # Clear and fill the tableWidget
        doc_font = 'font: ' + str(self.app.settings['docfontsize']) + 'pt '
        doc_font += '"' + self.app.settings['font'] + '";'
        self.ui.tableWidget.setStyleSheet(doc_font)
        self.ui.tableWidget.setColumnCount(len(horizontal_labels))
        self.ui.tableWidget.setHorizontalHeaderLabels(horizontal_labels)
        self.ui.tableWidget.setRowCount(len(cases))
        self.ui.tableWidget.setVerticalHeaderLabels(vertical_labels)
        # Need to create a table of separate textEdits for reference for cursorPositionChanged event.
        self.te = []
        choice = self.ui.comboBox_memos.currentText()
        for row, case in enumerate(cases):
            column_list = []
            for col, colname in enumerate(horizontal_labels):
                tedit = QtWidgets.QTextEdit("")
                tedit.setReadOnly(True)
                tedit.setContextMenuPolicy(Qt.CustomContextMenu)
                tedit.customContextMenuRequested.connect(self.table_textEdit_menu)
                column_list.append(tedit)
            self.te.append(column_list)
        self.matrix_links = []
        for row, case in enumerate(cases):
            for col, colname in enumerate(horizontal_labels):
                self.te[row][col].setReadOnly(True)
                for t in res_text_categories:
                    if t['file_or_casename'] == vertical_labels[row] and t['top'] == horizontal_labels[col]:
                        t['row'] = row
                        t['col'] = col
                        self.te[row][col].append(self.matrix_heading(t, self.te[row][col]))
                        self.matrix_links.append(t)
                        self.te[row][col].insertPlainText(t['text'] + "\n")
                for av in res_av_categories:
                    if av['file_or_casename'] == vertical_labels[row] and av['top'] == horizontal_labels[col]:
                        av['row'] = row
                        av['col'] = col
                        self.te[row][col].append(self.matrix_heading(av, self.te[row][col]))
                        self.matrix_links.append(av)
                        self.te[row][col].append(av['text'] + "\n")
                for counter, im in enumerate(res_image_categories):
                    if im['file_or_casename'] == vertical_labels[row] and im['top'] == horizontal_labels[col]:
                        im['row'] = row
                        im['col'] = col
                        self.te[row][col].insertHtml(self.matrix_heading(im, self.te[row][col]))
                        self.matrix_links.append(im)
                        self.put_image_into_textedit(im, counter, self.te[row][col])
                self.ui.tableWidget.setCellWidget(row, col, self.te[row][col])
        self.ui.tableWidget.resizeRowsToContents()
        self.ui.tableWidget.resizeColumnsToContents()
        # Maximise the space from one column or one row
        if self.ui.tableWidget.columnCount() == 1:
            self.ui.tableWidget.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        if self.ui.tableWidget.rowCount() == 1:
            self.ui.tableWidget.verticalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
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

        # Do not overwrite positions in original text_links object
        text_results = deepcopy(text_results)
        image_results = deepcopy(image_results)
        av_results = deepcopy(av_results)

        # Get top level categories
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
                top_id = None
                while not_top:
                    item = item.parent()
                    if self.ui.treeWidget.indexOfTopLevelItem(item) > -1:
                        not_top = False
                        sub_code['top'] = item.text(0)
                        top_id = item.text(1)
                        sub_codes.append(sub_code)
                add_cat = True
                for tl in top_level:
                    if tl['name'] == sub_code['top']:  #item.parent().text(0):
                        add_cat = False
                if add_cat and top_id is not None:
                    top_level.append({'name': sub_code['top'], 'cat': top_id})
                    horizontal_labels.append(sub_code['top'])

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

        # Clear and fill the tableWidget
        doc_font = 'font: ' + str(self.app.settings['docfontsize']) + 'pt '
        doc_font += '"' + self.app.settings['font'] + '";'
        self.ui.tableWidget.setStyleSheet(doc_font)
        self.ui.tableWidget.setColumnCount(len(horizontal_labels))
        self.ui.tableWidget.setHorizontalHeaderLabels(horizontal_labels)
        self.ui.tableWidget.setRowCount(len(cases))
        self.ui.tableWidget.setVerticalHeaderLabels(vertical_labels)
        # Need to create a table of separate textEdits for reference for cursorPositionChanged event.
        self.te = []
        for row, case in enumerate(cases):
            column_list = []
            for col, colname in enumerate(horizontal_labels):
                tedit = QtWidgets.QTextEdit("")
                tedit.setReadOnly(True)
                tedit.setContextMenuPolicy(Qt.CustomContextMenu)
                tedit.customContextMenuRequested.connect(self.table_textEdit_menu)
                column_list.append(tedit)
            self.te.append(column_list)
        self.matrix_links = []
        choice = self.ui.comboBox_memos.currentText()
        for row, case in enumerate(cases):
            for col, colname in enumerate(horizontal_labels):
                self.te[row][col].setReadOnly(True)
                for t in res_text_categories:
                    if t['file_or_casename'] == vertical_labels[row] and t['top'] == horizontal_labels[col]:
                        t['row'] = row
                        t['col'] = col
                        self.te[row][col].append(self.matrix_heading(t, self.te[row][col]))
                        self.matrix_links.append(t)
                        self.te[row][col].append(t['text'] + "\n")
                for av in res_av_categories:
                    if av['file_or_casename'] == vertical_labels[row] and av['top'] == horizontal_labels[col]:
                        av['row'] = row
                        av['col'] = col
                        self.te[row][col].append(self.matrix_heading(i, self.te[row][col]))
                        self.matrix_links.append(av)
                        self.te[row][col].append(av['text'] + "\n")  # The time duration
                for counter, im in enumerate(res_image_categories):
                    if im['file_or_casename'] == vertical_labels[row] and im['top'] == horizontal_labels[col]:
                        im['row'] = row
                        im['col'] = col
                        self.te[row][col].append(self.matrix_heading(im, self.te[row][col]))
                        self.matrix_links.append(im)
                        self.put_image_into_textedit(im, counter, self.te[row][col])
                self.ui.tableWidget.setCellWidget(row, col, self.te[row][col])
        self.ui.tableWidget.resizeRowsToContents()
        self.ui.tableWidget.resizeColumnsToContents()
        # Maximise the space from one column or one row
        if self.ui.tableWidget.columnCount() == 1:
            self.ui.tableWidget.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        if self.ui.tableWidget.rowCount() == 1:
            self.ui.tableWidget.verticalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.ui.splitter.setSizes([100, 300, 300])

    def table_textEdit_menu(self, position):
        """ Context menu for textEdit.
        To view coded in context. """

        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        te = self.te[x][y]
        text = te.toPlainText()
        if text == "":
            return
        cursor_context_pos = te.cursorForPosition(position)
        pos = cursor_context_pos.position()
        #print("POS:", pos, "row",x, "col",y, "text",text)
        selected_text = te.textCursor().selectedText()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")

        # Check that there is a link to view at this location before showing menu option
        action_view = None
        found = None
        for m in self.matrix_links:
            if m['row'] == x and m['col'] == y and pos >= m['textedit_start'] and pos < m['textedit_end']:
                found = True
        if found:
            action_view = menu.addAction(_("View in context"))
        action_copy = None
        if selected_text != "":
            action_copy = menu.addAction(_("Copy to clipboard"))
        action_copy_all = menu.addAction(_("Copy all to clipboard"))
        action = menu.exec_(te.mapToGlobal(position))
        if action is None:
            return
        if action == action_copy:
            cb = QtWidgets.QApplication.clipboard()
            cb.clear(mode=cb.Clipboard)
            cb.setText(selected_text, mode=cb.Clipboard)
        if action == action_copy_all:
            cb = QtWidgets.QApplication.clipboard()
            cb.clear(mode=cb.Clipboard)
            text = te.toPlainText()
            cb.setText(text, mode=cb.Clipboard)
        if action == action_view:
            for m in self.matrix_links:
                if m['row'] == x and m['col'] == y and pos >= m['textedit_start'] and pos < m['textedit_end']:
                    if 'mediapath' not in m:
                        ui = DialogCodeInText(self.app, m)
                        ui.exec_()
                        return
                    if m['mediapath'][0:7] in ('images:', '/images'):
                        ui = DialogCodeInImage(self.app, m)
                        ui.exec_()
                        return
                    if m['mediapath'][0:6] in ('audio:', 'video:', '/audio', '/video'):
                        ui = DialogCodeInAV(self.app, m)
                        ui.exec_()
                        return

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
    """ Used to add a dynamic tooltip for the textBrowser.
    The tool top text is presented according to its position in the text.
    """

    media_data = None

    def set_positions(self, media_data):
        """ Code_text contains the positions for the tooltip to be displayed.

        param:
            media_data: List of dictionaries of the text contains: pos0, pos1
        """

        self.media_data = media_data

    def eventFilter(self, receiver, event):
        # QtGui.QToolTip.showText(QtGui.QCursor.pos(), tip)
        if event.type() == QtCore.QEvent.ToolTip:
            helpEvent = QHelpEvent(event)
            cursor = QtGui.QTextCursor()
            cursor = receiver.cursorForPosition(helpEvent.pos())
            pos = cursor.position()
            receiver.setToolTip("")
            if self.media_data is None:
                return super(ToolTip_EventFilter, self).eventFilter(receiver, event)
            for item in self.media_data:
                if item['textedit_start'] <= pos and item['textedit_end'] >= pos:
                    receiver.setToolTip(_("Right click to view"))
        # Call Base Class Method to Continue Normal Event Processing
        return super(ToolTip_EventFilter, self).eventFilter(receiver, event)



