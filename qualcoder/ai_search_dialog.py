# -*- coding: utf-8 -*-

"""
Copyright (c) 2023 Colin Curtain

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

Author: Kai Dröge (kaixxx)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
"""

import os
import sys
import logging
import traceback
import sqlite3
from copy import deepcopy

from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush

from .color_selector import TextColor
from .report_attributes import DialogSelectAttributeParameters
from .select_items import DialogSelectItems
from .GUI.ui_ai_search import Ui_Dialog_AiSearch
from .report_attributes import DialogSelectAttributeParameters
from .helpers import Message

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception: ") + text)
    if len(text) > 500:
        text = _('Shortened error message: ...') + text[-500:]
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), text)


class DialogAiSearch(QtWidgets.QDialog):
    """
    Dialog to select the options for the AI based search
    Called from code_text.py
    """
    
    attributes = []
    attribute_file_ids = []
    selected_name = ''
    selected_code_ids = -1
    selected_description = ''
    include_coded_segments = False
    selected_file_ids = []

    def __init__(self, app_, selected_id, selected_is_code):
        """Initializes the dialog

        Args:
            app_ (qualcoder App)
            selected_id (int): the id of the selected item in the codes and categories tree. -1 if no item is selected.
            selected_is_code (bool): True if the selected item is a code, False if it is a category
        """
        sys.excepthook = exception_handler
        self.app = app_
        self.code_names, self.categories = self.app.get_codes_categories()
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_AiSearch()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = 'font: ' + str(app_.settings['fontsize']) + 'pt '
        font += '"' + app_.settings['font'] + '";'
        self.setStyleSheet(font)
        treefont = 'font: ' + str(self.app.settings['treefontsize']) + 'pt '
        treefont += '"' + self.app.settings['font'] + '";'
        self.ui.treeWidget.setStyleSheet(treefont)
        self.ui.listWidget_files.setStyleSheet(treefont)
        self.ui.listWidget_files.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.ui.listWidget_cases.setStyleSheet(treefont)
        self.ui.listWidget_cases.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.ui.treeWidget.setSelectionMode(QtWidgets.QTreeWidget.SelectionMode.SingleSelection)
        self.fill_tree(selected_id, selected_is_code)   
        self.ui.buttonBox.accepted.connect(self.ok)
        self.ui.buttonBox.rejected.connect(self.cancel) 
        # attributes        
        cur = self.app.conn.cursor()
        sql = "select count(name) from attribute_type"
        cur.execute(sql)
        res = cur.fetchone()
        if res[0] == 0:
            self.ui.pushButton_attributeselect.setEnabled(False)
        self.ui.pushButton_attributeselect.clicked.connect(self.select_attributes)
        self.ui.splitter.setSizes([100, 200, 0])
        self.get_files_and_cases()

          
        
    def fill_tree(self, selected_id, selected_is_code):
        """ Fill tree widget, top level items are main categories and unlinked codes. """

        cats = deepcopy(self.categories)
        codes = deepcopy(self.code_names)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(4)
        self.ui.treeWidget.setHeaderLabels([_("Name"), "Id", _("Memo"), _("Count")])
        self.ui.treeWidget.header().setToolTip(_("Codes and categories"))
        if not self.app.settings['showids']:
            self.ui.treeWidget.setColumnHidden(1, True)
        else:
            self.ui.treeWidget.setColumnHidden(1, False)
        self.ui.treeWidget.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.ui.treeWidget.header().setStretchLastSection(False)
        # Add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                memo = ""
                if c['memo'] != "":
                    memo = _("Memo")
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                top_item.setToolTip(0, '')
                if len(c['name']) > 52:
                    top_item.setText(0, c['name'][:25] + '..' + c['name'][-25:])
                    top_item.setToolTip(0, c['name'])
                top_item.setToolTip(2, c['memo'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                if not selected_is_code and c['catid'] == selected_id:
                    top_item.setSelected(True)
                remove_list.append(c)
        for item in remove_list:
            cats.remove(item)

        ''' Add child categories. Look at each unmatched category, iterate through tree
        to add as child then remove matched categories from the list. '''
        count = 0
        while len(cats) > 0 and count < 10000:
            remove_list = []
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
                item = it.value()
                count2 = 0
                while item and count2 < 10000:  # while there is an item in the list
                    if item.text(1) == 'catid:' + str(c['supercatid']):
                        memo = ""
                        if c['memo'] != "":
                            memo = "Memo"
                        child = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                        child.setToolTip(0, '')
                        if len(c['name']) > 52:
                            child.setText(0, c['name'][:25] + '..' + c['name'][-25:])
                            child.setToolTip(0, c['name'])
                        child.setToolTip(2, c['memo'])
                        item.addChild(child)
                        if not selected_is_code and c['catid'] == selected_id:
                            child.setSelected(True)
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
                memo = ""
                if c['memo'] != "":
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                top_item.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.BrushStyle.SolidPattern))
                color = TextColor(c['color']).recommendation
                top_item.setForeground(0, QBrush(QtGui.QColor(color)))
                top_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                top_item.setToolTip(0, '')
                if len(c['name']) > 52:
                    top_item.setText(0, c['name'][:25] + '..' + c['name'][-25:])
                    top_item.setToolTip(0, c['name'])
                top_item.setToolTip(2, c['memo'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                if selected_is_code and c['cid'] == selected_id:
                    top_item.setSelected(True)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)

        # Add codes as children
        for c in codes:
            it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
            item = it.value()
            count = 0
            while item and count < 10000:
                if item.text(1) == 'catid:' + str(c['catid']):
                    memo = ""
                    if c['memo'] != "":
                        memo = _("Memo")
                    child = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                    child.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.BrushStyle.SolidPattern))
                    color = TextColor(c['color']).recommendation
                    child.setForeground(0, QBrush(QtGui.QColor(color)))
                    child.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                    child.setToolTip(0, '')
                    if len(c['name']) > 52:
                        child.setText(0, c['name'][:25] + '..' + c['name'][-25:])
                        child.setToolTip(0, c['name'])
                    child.setToolTip(2, c['memo'])
                    item.addChild(child)
                    if selected_is_code and c['cid'] == selected_id:
                        child.setSelected(True)
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

    def select_attributes(self):
        """ Select files based on attribute selections.
        Attribute results are a dictionary of:
        first item is a Boolean AND or OR list item
        Followed by each attribute list item
        """
        
        ui = DialogSelectAttributeParameters(self.app)
        ui.fill_parameters(self.attributes)
        temp_attributes = deepcopy(self.attributes)
        self.attributes = []
        ok = ui.exec()
        if not ok:
            self.attributes = temp_attributes
            self.ui.label_attributes.setText('')
            #if self.attributes:
            #    pm = QtGui.QPixmap()
            #    pm.loadFromData(QtCore.QByteArray.fromBase64(attributes_selected_icon), "png")
            #    self.ui.pushButton_attributeselect.setIcon(QtGui.QIcon(pm))
            return
        
        # Clear ui
        self.attribute_file_ids = []
        self.ui.label_attributes.setText('')
        self.ui.splitter.setSizes([300, 300, 0])
        # Remove any selected case or file ids
        self.file_ids = ""
        for i in range(self.ui.listWidget_files.count()):
            if i == 0: # all files
                self.ui.listWidget_files.item(i).setSelected(True)
            else:    
                self.ui.listWidget_files.item(i).setSelected(False)
        self.case_ids = ""
        for i in range(self.ui.listWidget_cases.count()):
            if i == 0: # all cases
                self.ui.listWidget_cases.item(i).setSelected(True)
            else:
                self.ui.listWidget_cases.item(i).setSelected(False)

        self.attributes = ui.parameters
        if len(self.attributes) == 1:
            self.ui.label_attributes.setText('')
            return
        self.ui.label_attributes.setText(ui.tooltip_msg[len(_("Show files:")):])
        self.attribute_file_ids = ui.result_file_ids

    def get_files_and_cases(self):
        """ Get source files with additional details and fill files list widget.
        Get cases and fill case list widget
        Called from : init
        """

        self.ui.listWidget_files.clear()
        self.files = self.app.get_text_filenames()
        # Fill additional details about each file in the memo
        cur = self.app.conn.cursor()
        sql = "select length(fulltext), mediapath from source where id=?"
        sql_text_codings = "select count(cid) from code_text where fid=?"
        sql_av_codings = "select count(cid) from code_av where id=?"
        sql_image_codings = "select count(cid) from code_image where id=?"
        item = QtWidgets.QListWidgetItem(_("<no file filter>"))
        item.setToolTip(_("Search in all textfiles"))
        item.setData(Qt.ItemDataRole.UserRole, -1)
        self.ui.listWidget_files.addItem(item)
        item.setSelected(True)
        for f in self.files:
            cur.execute(sql, [f['id'], ])
            res = cur.fetchone()
            if res is None:  # safety catch
                res = [0]
            tt = ""
            cur.execute(sql_text_codings, [f['id']])
            txt_res = cur.fetchone()
            #cur.execute(sql_av_codings, [f['id']])
            #av_res = cur.fetchone()
            #cur.execute(sql_image_codings, [f['id']])
            #img_res = cur.fetchone()
            tt += _("Codings: ")
            # if txt_res[0] > 0:
            tt += str(txt_res[0])
            # if av_res[0] > 0:
            #    tt += str(av_res[0])
            #if img_res[0] > 0:
            #    tt += str(img_res[0])
            item = QtWidgets.QListWidgetItem(f['name'])
            if f['memo'] != "":
                tt += _("\nMEMO: ") + f['memo']
            item.setToolTip(tt)
            item.setData(Qt.ItemDataRole.UserRole, f['id'])
            self.ui.listWidget_files.addItem(item)

        self.ui.listWidget_cases.clear()
        self.cases = self.app.get_casenames()
        item = QtWidgets.QListWidgetItem("<no case filter>")
        item.setToolTip(_("Search in all cases"))
        item.setData(Qt.ItemDataRole.UserRole, -1)
        self.ui.listWidget_cases.addItem(item)
        item.setSelected(True)
        for c in self.cases:
            tt = ""
            item = QtWidgets.QListWidgetItem(c['name'])
            if c['memo'] != "":
                tt = _("MEMO: ") + c['memo']
            item.setToolTip(tt)
            item.setData(Qt.ItemDataRole.UserRole, c['id'])
            self.ui.listWidget_cases.addItem(item)
            
    def _get_codes_from_tree(self, item: QtWidgets.QTreeWidgetItem) -> list:
        res = []
        if item.text(1)[0:3] == 'cid': # is a code
            id = int(item.text(1).split(':')[1])
            res.append(id)
        for i in range(item.childCount()):
            child = item.child(i)
            res.extend(self._get_codes_from_tree(child))
        return res
           
    def ok(self):
        """Collect the infos needed for the ai based search and the filters applied 
        (selected files, cases, attributes), then close the dialog. 
        """    
        if self.ui.tabWidget.currentIndex() == 0: # code search selected
            if len(self.ui.treeWidget.selectedItems()) == 0:
                msg = _('Please select a code or category (or use "free search" instead).')
                Message(self.app, _('No codes'), msg, "warning").exec()
                return
            else:
                item = self.ui.treeWidget.selectedItems()[0]
                self.selected_code_ids = self._get_codes_from_tree(item)
                self.selected_name = item.text(0)
                if self.ui.checkBox_send_memos.isChecked():
                    self.selected_description = item.toolTip(2)
                else:
                    self.selected_description = ''
                self.include_coded_segments = self.ui.checkBox_coded_segments.isChecked()
                item = item.parent()
                while item is not None and not isinstance(item, QtWidgets.QTreeWidget):
                    self.selected_name = f'{item.text(0)} > {self.selected_name}'
                    item = item.parent()               
        else: # free search selected
            self.selected_code_ids = None
            self.selected_name = self.ui.lineEdit_free_topic.text()
            if self.selected_name == '':
                msg = _('Please enter text in the "topic" field.')
                Message(self.app, _('No codes'), msg, "warning").exec()
                return
            self.selected_description = self.ui.textEdit_free_description.toPlainText()
        
        # file selection
        self.selected_file_ids = []
        if self.ui.listWidget_files.item(0).isSelected(): # first item selected = add all files
            for i in range(self.ui.listWidget_files.count()):
                id = self.ui.listWidget_files.item(i).data(Qt.ItemDataRole.UserRole)
                if id > -1:
                    self.selected_file_ids.append(id)
        else: # add only selected
            for item in self.ui.listWidget_files.selectedItems():
                id = item.data(Qt.ItemDataRole.UserRole)
                if id > -1:
                    self.selected_file_ids.append(id)
        
        # case filter
        if not self.ui.listWidget_cases.item(0).isSelected(): 
            # Only apply case filter if the first item (<no case filter>)  
            # is not selected.
            # The case filter will delete all files from self.selected_file_ids that 
            # do not belong to the selected cases. 
            selected_cases = []
            for item in self.ui.listWidget_cases.selectedItems():
                id = item.data(Qt.ItemDataRole.UserRole)
                if id > -1:
                    selected_cases.append(id)
            if len(selected_cases) > 0:
                selected_cases_str = "(" + ", ".join(map(str, selected_cases)) + ")"
                files_cases_sql = str('select distinct case_text.fid from case_text '
                                    'join source on case_text.fid=source.id '
                                    'where caseid in ') + selected_cases_str
                cur = self.app.conn.cursor()
                cur.execute(files_cases_sql)
                res = cur.fetchall()
                selected_cases_files = []
                for row in res:
                    selected_cases_files.append(row[0])
                # To filter out all items in self.selected_file_ids that are not also in selected_cases_files,
                # use a list comprehension to create a new list containing only elements present in both lists
                self.selected_file_ids = [x for x in self.selected_file_ids if x in selected_cases_files]
        
        # combine it with the attributes filter
        if len(self.attribute_file_ids) > 0:
            self.selected_file_ids = [x for x in self.selected_file_ids if x in self.attribute_file_ids]

        if len(self.selected_file_ids) == 0:
            msg = _('After combining all filters, there are not files left for the search. Please check your settings.')
            Message(self.app, _('No files'), msg, "warning").exec()
            return
        
        self.accept()
        
    def cancel(self):
        self.selected_name = ''
        self.selected_description = ''
        self.selected_file_ids = []
        self.reject()






