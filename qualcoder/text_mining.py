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
"""

from PyQt6 import QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush
import os
import sys
from copy import copy
import logging
import traceback

from .GUI.ui_dialog_text_mining import Ui_Dialog_text_mining

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogTextMining(QtWidgets.QDialog):
    """ Mine text using a range of variables.
    NOT CURRENTLY IMPLEMENTED FOR FUTURE EXPANSION
    """

    settings = None
    parent_textEdit = None
    code_names = []
    coders = [""]
    categories = []
    sources = []
    cases = []
    NAME_COLUMN = 0
    ID_COLUMN = 1
    plain_text_results = ""

    def __init__(self, settings, parent_textEdit):

        self.settings = settings
        self.parent_textEdit = parent_textEdit
        self.get_data()
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_text_mining()
        self.ui.setupUi(self)
        self.ui.tableWidget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        newfont = QtGui.QFont(settings['font'], settings['fontsize'], QtGui.QFont.Weight.Normal)
        self.setFont(newfont)
        newfont = QtGui.QFont(settings['font'], 6, QtGui.QFont.Weight.Normal)
        self.ui.label_selections.setFont(newfont)
        treefont = QtGui.QFont(settings['font'], settings['treefontsize'], QtGui.QFont.Weight.Normal)
        self.ui.treeWidget.setFont(treefont)
        self.ui.treeWidget.setSelectionMode(QtWidgets.QTreeWidget.SelectionMode.ExtendedSelection)
        self.ui.comboBox_coders.insertItems(0, self.coders)
        items = ["Bag of words", "Vocabulary and frequency"]
        self.ui.comboBox_analysis.addItems(items)
        self.fill_tree()
        self.ui.pushButton_search.clicked.connect(self.analyse)
        self.ui.pushButton_export_selected.clicked.connect(self.export_selected_file)
        self.ui.radioButton_files.toggled.connect(self.on_radio_button_toggled)
        self.ui.radioButton_files_coded.toggled.connect(self.on_radio_button_toggled)
        self.ui.radioButton_cases.toggled.connect(self.on_radio_button_toggled)
        self.ui.radioButton_cases_coded.toggled.connect(self.on_radio_button_toggled)
        self.fill_table()

    def get_data(self):
        """ Called from init.Case text sections for each case are prefixed with
        <<<filename>>>\n and suffixed with \n. """

        cur = self.settings['conn'].cursor()
        self.categories = []
        cur.execute("select name, catid, owner, date, memo, supercatid from code_cat")
        result = cur.fetchall()
        for row in result:
            self.categories.append({'name': row[0], 'catid': row[1], 'owner': row[2],
            'date': row[3], 'memo': row[4], 'supercatid': row[5]})

        self.code_names = []
        cur.execute("select name, memo, owner, date, cid, catid, color from code_name")
        result = cur.fetchall()
        for row in result:
            self.code_names.append({'name': row[0], 'memo': row[1], 'owner': row[2], 'date': row[3],
            'cid': row[4], 'catid': row[5], 'color': row[6]})

        self.coders = []
        cur.execute("select distinct owner from code_text")
        result = cur.fetchall()
        self.coders = [""]
        for row in result:
            self.coders.append(row[0])

        self.sources = []
        cur.execute("select name, id, file, owner from source order by name")
        result = cur.fetchall()
        for row in result:
            self.sources.append({'name': row[0], 'id': row[1], 'file': row[2], 'owner': row[3]})

        self.cases = []
        sql = "select caseid, cases.name, owner from cases"
        cur.execute(sql)
        result = cur.fetchall()
        for row in result:
            case = {'caseid': row[0], 'name': row[1], 'owner': row[2], 'text': ""}
            self.cases.append(case)
        for case in self.cases:
            sql = "select fid, selfirst, selend from case_text where caseid = ? order by fid, selfirst"
            cur.execute(sql, [case['caseid'], ])
            result = cur.fetchall()
            for row in result:
                for source in self.sources:
                    if source['id'] == row[0]:
                        case['text'] += "<<<" + source['name'] + ">>>\n" + source['file'][row[1] : row[2]] + "\n"

    def on_radio_button_toggled(self):
        radiobutton = self.sender()

        if radiobutton.isChecked():
            print(radiobutton.text())
        self.fill_table()

    def fill_table(self):
        """ Fill table with source names OR case names. """

        self.ui.tableWidget.setColumnCount(2)
        rows = self.ui.tableWidget.rowCount()
        for r in range(0, rows):
            self.ui.tableWidget.removeRow(0)
        files = True
        if self.ui.radioButton_files.isChecked() or self.ui.radioButton_files_coded.isChecked():
            files = True
        else:
            files = False
        if files:
            self.ui.tableWidget.setHorizontalHeaderLabels(["File name", "ID"])
            for row, details in enumerate(self.sources):
                self.ui.tableWidget.insertRow(row)
                self.ui.tableWidget.setItem(row, self.NAME_COLUMN, QtWidgets.QTableWidgetItem(details['name']))
                self.ui.tableWidget.setItem(row, self.ID_COLUMN, QtWidgets.QTableWidgetItem(str(details['id'])))

        if not files:
            self.ui.tableWidget.setHorizontalHeaderLabels(["Case name", "ID"])
            for row, details in enumerate(self.cases):
                self.ui.tableWidget.insertRow(row)
                self.ui.tableWidget.setItem(row, self.NAME_COLUMN, QtWidgets.QTableWidgetItem(details['name']))
                self.ui.tableWidget.setItem(row, self.ID_COLUMN, QtWidgets.QTableWidgetItem(str(details['caseid'])))

        self.ui.tableWidget.resizeColumnsToContents()
        self.ui.tableWidget.resizeRowsToContents()

    def fill_tree(self):
        ''' Fill tree widget, top level items are main categories and unlinked codes '''

        cats = copy(self.categories)
        codes = copy(self.code_names)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(2)
        self.ui.treeWidget.setHeaderLabels(["Name", "Id"])
        self.ui.treeWidget.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.ui.treeWidget.header().setStretchLastSection(False)
        # add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid'])])
                top_item.setIcon(0, QtGui.QIcon("GUI/icon_cat.png"))
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_list.append(c)
        for item in remove_list:
            #try:
            cats.remove(item)
            #except Exception as e:
            #    print(e, item)

        ''' Add child categories. Look at each unmatched category, iterate through tree
        to add as child then remove matched categories from the list. '''
        count = 0
        while len(cats) > 0 or count < 10000:
            remove_list = []
            #logger.debug("cats:" + str(cats))
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
                item = it.value()
                while item:  # while there is an item in the list
                    #logger.debug("While: " +  item.text(0) + "|"+ item.text(1) + ", c[catid]:" + str(c['catid']) + ", c[supercatid]:" + str(c['supercatid']))
                    if item.text(1) == 'catid:' + str(c['supercatid']):
                        child = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid'])])
                        child.setIcon(0, QtGui.QIcon("GUI/icon_cat.png"))
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
                #logger.debug("add unlinked code as top level item:" + c['name'])
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid'])])
                top_item.setIcon(0, QtGui.QIcon("GUI/icon_code.png"))
                top_item.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.BrushStyle.SolidPattern))
                top_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)

        # add codes as children
        for c in codes:
            it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
            item = it.value()
            while item:
                #logger.debug("" + item.text(0) + "|" + item.text(1) + ", c[cid]:" + str(c['cid']) + "c[catid]:" + str(c['catid']))
                if item.text(1) == 'catid:' + str(c['catid']):
                    child = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid'])])
                    child.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.BrushStyle.SolidPattern))
                    child.setIcon(0, QtGui.QIcon("GUI/icon_code.png"))
                    child.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                    item.addChild(child)
                    c['catid'] = -1  # make unmatchable
                it += 1
                item = it.value()
        self.ui.treeWidget.expandAll()

    def export_selected_file(self):
        ''' Export selected text to a plain text file, filename will have .txt ending '''

        fileName = QtWidgets.QFileDialog.getSaveFileName(None, "Save text file", os.getenv('HOME'))
        if fileName[0] == "":
            return
        fileName = fileName[0] + ".txt"
        f = open(fileName, 'w')
        f.write(self.plain_text_results)
        f.close()
        #self.log += "Coding Report Results exported to " + fileName + "\n"
        QtWidgets.QMessageBox.information(None, "Text file Export", fileName + " exported")

    def recursive_set_selected(self, item):
        ''' Set all children of this item to be selected if the item is selected.
        Recurse through any child categories '''
        #print(item.text(0), item.text(1))
        child_count = item.childCount()
        for i in range(child_count):
            if item.isSelected():
                item.child(i).setSelected(True)
            self.recursive_set_selected(item.child(i))

    def analytics(self):
        '''
        http://www.nltk.org/book/ch02.html

        words corpus
        /usr/share/dict/words

        stopwords

        Toolbox
        https://software.sil.org/toolbox/

        http://www.nltk.org/book/ch03.html

        Tokenises text but keeps apostrophes and hyphens
        re.findall(r"\w+(?:[-']\w+)*|'|[-.(]+|\S\w*", text)
        '''

    #TODO
    def analyse(self):
        ''' Fill selection label with selected options.
        Run the analysis based on combo box analyse option '''

        txt = ""

        # In tree, set all items under selected categories to be selected
        self.recursive_set_selected(self.ui.treeWidget.invisibleRootItem())
        items = self.ui.treeWidget.selectedItems()
        # get codes from selected tree items
        code_txt = []
        code_ids = []
        for i in items:
            if i.text(1)[0:3] == 'cid':
                code_ids.append(i.text(1)[4:])
                code_txt.append(i.text(0))
        txt += "Codes: " + ",".join(code_txt)

        # files or cases
        case_or_file_text = []
        case_or_file_ids = []
        files_selected = False
        if self.ui.radioButton_files.isChecked() or self.ui.radioButton_files_coded.isChecked():
            files_selected = True
        model_indexes = self.ui.tableWidget.selectionModel().selectedRows()
        for index in model_indexes:
            case_or_file_text.append(self.ui.tableWidget.item(index.row(), 0).text())
            case_or_file_ids.append(self.ui.tableWidget.item(index.row(), 1).text())
        if files_selected:
            txt += "\nFiles: " + ",".join(case_or_file_text)
        else:
            txt += "\nCases: " + ",".join(case_or_file_text)
        self.ui.label_selections.setText(txt)
        if case_or_file_ids == [] and code_ids == []:
            return
        self.get_text_result(code_ids, files_selected, case_or_file_ids)

        # analyse text result depending on analysis selection
        if self.ui.comboBox_analysis == "Bag of words":
            pass
        if self.ui.comboBox_analysis == "Vocabulary and frequency":
            pass

    def get_text_result(self, code_ids, files_selected, ids):
        '''  '''

        search_results = []
        coder = self.ui.comboBox_coders.currentText()
        cur = self.settings['conn'].cursor()

        # get coded text via selected files
        parameters = []
        if files_selected:
            sql = "select code_name.name, source.name, selfirst, selend, seltext, code_text.owner from "
            sql += "code_text "
            sql += " join code_name on code_name.cid = code_text.cid join source on fid = source.id "

            sql += " where code_name.cid in (" + ','.join(code_ids) + ") "

            sql += " and source.id in (" + ','.join(ids) + ") "
            if coder != "":
                sql += " and code_text.owner=? "
                parameters.append(coder)

            if parameters == []:
                cur.execute(sql)
            else:
                #print(sql)
                #print(parameters)
                cur.execute(sql, parameters)
            result = cur.fetchall()
            print(sql)
            for row in result:
                search_results.append(row)
                print(row)

        # get coded text via selected cases
        if not files_selected:
            sql = "select code_name.name, color, cases.name, "
            sql += "code_text.selfirst, code_text.selend, seltext, code_text.owner from code_text "
            sql += " join code_name on code_name.cid = code_text.cid "
            sql += " join (case_text join cases on cases.caseid = case_text.caseid) on "
            sql += " code_text.fid = case_text.fid "
            sql += " where code_name.cid in (" + ','.join(code_ids) + ") "
            sql += " and case_text.caseid in (" + ','.join(ids) + ") "
            sql += " and (code_text.selfirst >= case_text.selfirst and code_text.selend <= case_text.selend)"

            # need to group by or can get multiple results
            #sql += " group by cases.name, freecode.name, " + coder + ".selfirst, " + coder + ".selend"

            if coder != "":
                sql += " and code_text.owner=? "
                parameters.append(coder)

            if parameters == []:
                cur.execute(sql)
            else:
                cur.execute(sql, parameters)
            result = cur.fetchall()
            for row in result:
                search_results.append(row)
                print(row)

