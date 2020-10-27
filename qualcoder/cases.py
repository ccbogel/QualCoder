# -*- coding: utf-8 -*-

'''
Copyright (c) 2019 Colin Curtain

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
'''

import csv
import datetime
import logging
import os
import sys
import re
import traceback

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt

from add_attribute import DialogAddAttribute
from add_item_name import DialogAddItemName
from case_file_manager import DialogCaseFileManager
from confirm_delete import DialogConfirmDelete
from GUI.ui_dialog_cases import Ui_Dialog_cases
from GUI.ui_dialog_start_and_end_marks import Ui_Dialog_StartAndEndMarks
from memo import DialogMemo
from view_av import DialogViewAV
from view_image import DialogViewImage


path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception: ")  + text)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 12pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(text)
    mb.exec_()

class DialogCases(QtWidgets.QDialog):
    ''' Create, edit and delete cases.
    Assign entire text files or portions of files to cases.
    Assign attributes to cases. '''

    NAME_COLUMN = 0  # also primary key
    MEMO_COLUMN = 1
    ID_COLUMN = 2
    FILES_COLUMN = 3
    header_labels = []
    app = None
    parent_textEdit = None
    source = []
    sourceText = ""
    cases = []
    case_text = []
    selected_case = None
    selected_file = None
    display_text_links = [] # clickable links for audio video images as dictionaries of pos0, pos1, file id
    attributes = []

    def __init__(self, app, parent_textEdit):

        sys.excepthook = exception_handler
        self.app = app
        self.parent_textEdit = parent_textEdit
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_cases()
        self.ui.setupUi(self)
        try:
            w = int(self.app.settings['dialogcases_w'])
            h = int(self.app.settings['dialogcases_h'])
            if h > 50 and w > 50:
                self.resize(w, h)
        except:
            pass
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.load_cases_and_attributes()
        self.ui.pushButton_add.clicked.connect(self.add_case)
        self.ui.pushButton_delete.clicked.connect(self.delete_case)
        self.ui.tableWidget.itemChanged.connect(self.cell_modified)
        self.ui.tableWidget.cellClicked.connect(self.cell_selected)
        self.ui.pushButton_add_attribute.clicked.connect(self.add_attribute)
        self.ui.pushButton_import_cases.clicked.connect(self.import_cases_and_attributes)
        self.ui.textBrowser.setText("")
        self.ui.textBrowser.setAutoFillBackground(True)
        self.ui.textBrowser.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.textBrowser.customContextMenuRequested.connect(self.link_clicked)
        self.ui.textBrowser.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.textBrowser.customContextMenuRequested.connect(self.textEdit_menu)
        self.ui.tableWidget.itemSelectionChanged.connect(self.count_selected_items)
        self.fill_tableWidget()
        self.ui.splitter.setSizes([1, 1])
        try:
            s0 = int(self.app.settings['dialogcases_splitter0'])
            s1 = int(self.app.settings['dialogcases_splitter1'])
            if s0 > 10 and s1 > 10:
                self.ui.splitter.setSizes([s0, s1])
        except:
            pass

    def closeEvent(self, event):
        """ Save dialog and splitter dimensions. """

        self.app.settings['dialogcases_w'] = self.size().width()
        self.app.settings['dialogcases_h'] = self.size().height()
        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogcases_splitter0'] = sizes[0]
        self.app.settings['dialogcases_splitter1'] = sizes[1]

    def count_selected_items(self):
        """ Update label with the count of selected rows.
         Also clear the textedit if multiple rows are selected.
         :return
            item_count """

        indexes = self.ui.tableWidget.selectedIndexes()
        ix = []
        for i in indexes:
            ix.append(i.row())
        i = len(set(ix))
        if i > 1:
            self.ui.textBrowser.clear()
        case_name = ""
        if i == 1:
            case_name = self.ui.tableWidget.item(indexes[0].row(), 0).text()
        self.ui.label_cases.setText(_("Cases: ") + str(i) + "/" + str(len(self.cases)) + "  " + case_name)

        return i

    def load_cases_and_attributes(self):
        """ Load case and attribute details from database. Display in tableWidget.
        """

        self.source = []
        self.cases = []
        self.case_text = []

        cur = self.app.conn.cursor()
        cur.execute("select name, id, fulltext, mediapath, memo, owner, date from source")
        result = cur.fetchall()
        for row in result:
            self.source.append({'name': row[0], 'id': row[1], 'fulltext': row[2],
            'mediapath': row[3], 'memo': row[4], 'owner': row[5], 'date': row[6]})
        cur.execute("select name, memo, owner, date, caseid from cases")
        result = cur.fetchall()
        for row in result:
            sql = "select distinct case_text.fid, source.name from case_text join source on case_text.fid=source.id where caseid=? order by source.name asc"
            cur.execute(sql, [row[4], ])
            files = cur.fetchall()
            self.cases.append({'name': row[0], 'memo': row[1], 'owner': row[2], 'date': row[3],
            'caseid': row[4], 'files': files})
        cur.execute("select name from attribute_type where caseOrFile='case'")
        attribute_names = cur.fetchall()
        self.header_labels = ["Name", "Memo", "Id", "Files"]
        for i in attribute_names:
            self.header_labels.append(i[0])
        sql = "select attribute.name, value, id from attribute where attr_type='case'"
        cur.execute(sql)
        result = cur.fetchall()
        self.attributes = []
        for row in result:
            self.attributes.append(row)

    def add_attribute(self):
        """ When add button pressed, opens the addItem dialog to get new attribute text.
        Then get the attribute type through a dialog.
        AddItem dialog checks for duplicate attribute name.
        New attribute is added to the model and database. """

        cur = self.app.conn.cursor()
        cur.execute("select name from attribute_type where caseOrFile='case'")
        result = cur.fetchall()
        attribute_names = []
        for a in result:
            attribute_names.append({'name': a[0]})
        check_names = attribute_names + [{'name': 'name'}, {'name':'memo'}, {'name':'caseid'}, {'name':'date'}]
        ui = DialogAddAttribute(self.app, check_names)
        ok = ui.exec_()
        if not ok:
            return
        name = ui.new_name
        value_type = ui.value_type
        if name == "":
            return
        # update attribute_type list and database
        now_date = str(datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"))
        cur.execute("insert into attribute_type (name,date,owner,memo,caseOrFile, valuetype) values(?,?,?,?,?,?)"
            ,(name, now_date, self.app.settings['codername'], "", 'case', value_type))
        self.app.conn.commit()
        sql = "select caseid from cases"
        cur.execute(sql)
        case_ids = cur.fetchall()
        for id_ in case_ids:
            sql = "insert into attribute (name, value, id, attr_type, date, owner) values (?,?,?,?,?,?)"
            cur.execute(sql, (name, "", id_[0], 'case', now_date, self.app.settings['codername']))
        self.app.conn.commit()
        self.load_cases_and_attributes()
        self.fill_tableWidget()
        self.parent_textEdit.append(_("Attribute added to cases: ") + name + ", " + _("type: ") + value_type)
        self.app.delete_backup = False

    def import_cases_and_attributes(self):
        """ Import from a csv file with the cases and any attributes.
        The csv file must have a header row which details the attribute names.
        The csv file must be comma delimited. The first column must have the case ids.
        The attribute types are calculated from the data.
        """

        if self.cases != []:
            logger.warning(_("Cases have already been created."))
        filename = QtWidgets.QFileDialog.getOpenFileName(None, _('Select attributes file'),
            self.app.settings['directory'], "(*.csv)")[0]
        if filename == "":
            return
        if filename[-4:].lower() != ".csv":
            msg = filename + "\n" + _("is not a .csv file. File not imported")
            QtWidgets.QMessageBox.warning(None, "Warning", msg)
            self.parent_textEdit.append(msg)
            return
        values = []
        with open(filename, 'r', newline='') as f:
            reader = csv.reader(f, delimiter=',', quoting=csv.QUOTE_MINIMAL)
            try:
                for row in reader:
                    values.append(row)
            except csv.Error as e:
                logger.warning(('file %s, line %d: %s' % (filename, reader.line_num, e)))
        if len(values) <= 1:
            logger.info(_("Cannot import from csv, only one row in file"))
            return
        now_date = str(datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"))
        header = values[0]
        values = values[1:]
        # insert cases
        cur = self.app.conn.cursor()
        for v in values:
            item = {'name': v[0], 'memo': "", 'owner': self.app.settings['codername'],
                'date': now_date}
            try:
                cur.execute("insert into cases (name,memo,owner,date) values(?,?,?,?)"
                    ,(item['name'],item['memo'],item['owner'],item['date']))
                self.app.conn.commit()
                cur.execute("select last_insert_rowid()")
                item['caseid'] = cur.fetchone()[0]
                self.cases.append(item)
            except Exception as e:
                logger.error("item:" + str(item) + ", " + str(e))
        # determine attribute type
        attribute_value_type = ["character"] * len(header)
        for col, att_name in enumerate(header):
            numeric = True
            for val in values:
                try:
                    float(val[col])
                except ValueError:
                    numeric = False
            if numeric:
                attribute_value_type[col] = "numeric"
        # insert attribute types
        for col, att_name in enumerate(header):
            if col > 0:
                try:
                    cur.execute("insert into attribute_type (name,date,owner,memo, \
                    valueType, caseOrFile) values(?,?,?,?,?,?)"
                    , (att_name, now_date, self.app.settings['codername'], "",
                    attribute_value_type[col], 'case'))
                    self.app.conn.commit()
                except Exception as e:
                    logger.error(_("attribute:") + att_name + ", " + str(e))
        # insert attributes
        sql = "select name, caseid from cases"
        cur.execute(sql)
        name_and_ids = cur.fetchall()
        for n_i in name_and_ids:
            for v in values:
                if n_i[0] == v[0]:
                    for col in range(1, len(v)):
                        sql = "insert into attribute (name, value, id, attr_type, date, owner) values (?,?,?,?,?,?)"
                        cur.execute(sql, (header[col], v[col], n_i[1], 'case',
                        now_date, self.app.settings['codername']))
        self.app.conn.commit()
        self.load_cases_and_attributes()
        self.fill_tableWidget()
        msg = _("Cases and attributes imported from: ") + filename
        self.app.delete_backup = False
        self.parent_textEdit.append(msg)
        logger.info(msg)

    def add_case(self):
        """ When add case button pressed, open addItem dialog to get the case name.
        AddItem dialog checks for duplicate case name.
        New case is added to the model and database.
        Attribute placeholders are assigned to the database for this new case. """

        ui = DialogAddItemName(self.app, self.cases, _("Case"), _("Enter case name"))
        ui.exec_()
        case_name = ui.get_new_name()
        if case_name is None:
            return
        # update case list and database
        item = {'name': case_name, 'memo': "", 'owner': self.app.settings['codername'],
                 'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'files': []}
        cur = self.app.conn.cursor()
        cur.execute("insert into cases (name,memo,owner,date) values(?,?,?,?)"
            , (item['name'], item['memo'], item['owner'], item['date']))
        self.app.conn.commit()
        cur.execute("select last_insert_rowid()")
        item['caseid'] = cur.fetchone()[0]
        # add placeholder attribute values
        cur.execute("select name, valuetype from attribute_type where caseOrFile='case'")
        atts = cur.fetchall()
        for att in atts:
            cur.execute("insert into attribute(name,attr_type,value,id,date,owner) \
                values (?,?,?,?,?,?)",
                (att[0], "case", "", item['caseid'], item['date'], item['owner']))
        self.app.conn.commit()
        self.cases.append(item)
        self.fill_tableWidget()
        self.parent_textEdit.append(_("Case added: ") + item['name'])
        self.app.delete_backup = False

    def delete_case(self):
        """ When delete button pressed, case is deleted from model and database. """

        tableRows_to_delete = []  # for table widget ids
        caseNames_to_delete = ""  # for confirmDelete Dialog
        ids_to_delete = []  # for ids for cases and db

        for itemWidget in self.ui.tableWidget.selectedItems():
            tableRows_to_delete.append(int(itemWidget.row()))
            ids_to_delete.append(int(self.ui.tableWidget.item(itemWidget.row(),
            self.ID_COLUMN).text()))
            caseNames_to_delete = caseNames_to_delete + "\n" + str(self.ui.tableWidget.item(itemWidget.row(),
            self.NAME_COLUMN).text())
            #logger.debug("X:"+ str(itemWidget.row()) + "  y:"+str(itemWidget.column()) +"  "+itemWidget.text() +"  id:"+str(self.tableWidget_codes.item(itemWidget.row(),3).text()))
        tableRows_to_delete.sort(reverse=True)
        if len(caseNames_to_delete) == 0:
            return
        ui = DialogConfirmDelete(self.app, caseNames_to_delete)
        ok = ui.exec_()
        if not ok:
            return
        for id in ids_to_delete:
            for c in self.cases:
                if c['caseid'] == id:
                    self.parent_textEdit.append("Case deleted: " + c['name'])
                    self.cases.remove(c)
                    cur = self.app.conn.cursor()
                    #logger.debug(str(id) + "  "+ str(type(id)))
                    cur.execute("delete from cases where caseid = ?", [id])
                    cur.execute("delete from case_text where caseid = ?", [id])
                    sql = "delete from attribute where id=? and attr_type='case'"
                    cur.execute(sql, [id])
                    self.app.conn.commit()
        self.app.delete_backup = False
        self.fill_tableWidget()

    def cell_modified(self):
        """ If the case name has been changed in the table widget update the database.
         Cells that can be changed directly are the case name, and attributes. """

        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        if y == self.NAME_COLUMN:  # update case name
            new_text = str(self.ui.tableWidget.item(x, y).text()).strip()
            # check that no other case name has this text and this is not empty
            update = True
            if new_text == "":
                update = False
            for c in self.cases:
                if c['name'] == new_text:
                    update = False
            if update:
                cur = self.app.conn.cursor()
                cur.execute("update cases set name=? where caseid=?", (new_text, self.cases[x]['caseid']))
                self.app.conn.commit()
                self.cases[x]['name'] = new_text
            else:  # put the original text in the cell
                self.ui.tableWidget.item(x, y).setText(self.cases[x]['name'])
        if y > 2:  # update attribute value
            value = str(self.ui.tableWidget.item(x, y).text()).strip()
            attribute_name = self.header_labels[y]
            cur = self.app.conn.cursor()
            cur.execute("update attribute set value=? where id=? and name=? and attr_type='case'",
            (value, self.cases[x]['caseid'], attribute_name))
            self.app.conn.commit()
        self.app.delete_backup = False

    def cell_selected(self):
        """ Highlight case text if a file is selected.
        Indicate memo is present, update memo text, or delete memo by clearing text.
        """

        self.ui.textBrowser.clear()
        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        if x == -1:
            self.selected_case = None
            self.case_text = []
            return
        self.selected_case = self.cases[x]
        if self.count_selected_items() > 1:
            return

        #logger.debug("Selected case: " + str(self.selected_case['id']) +" "+self.selected_case['name'])'''
        # get case_text for this file
        if self.selected_file is not None:
            #logger.debug("File Selected: " + str(self.selected_file['id'])+"  "+self.selected_file['file'])
            self.case_text = []
            cur = self.app.conn.cursor()
            cur.execute("select caseid, fid, pos0, pos1, owner, date, memo from case_text where fid = ? and caseid = ?",
                [self.selected_file['id'], self.selected_case['caseid']])
            result = cur.fetchall()
            for row in result:
                self.case_text.append({'caseid': row[0], 'fid': row[1], 'pos0': row[2],
                'pos1': row[3], 'owner': row[4], 'date': row[5], 'memo': row[6]})

        # if y == self.NAME_COLUMN:
        self.view()

        if y == self.MEMO_COLUMN:
            ui = DialogMemo(self.app, _("Memo for case ") + self.cases[x]['name'],
                self.cases[x]['memo'])
            ui.exec_()
            self.cases[x]['memo'] = ui.memo
            cur = self.app.conn.cursor()
            cur.execute('update cases set memo=? where caseid=?', (self.cases[x]['memo'], self.cases[x]['caseid']))
            self.app.conn.commit()
            if self.cases[x]['memo'] == "" or self.cases[x]['memo'] is None:
                self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem())
            else:
                self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem(_("Memo")))
            self.app.delete_backup = False

        if y == self.FILES_COLUMN:
            ui = DialogCaseFileManager(self.app, self.parent_textEdit, self.cases[x])
            ui.exec_()
            # reload files count
            cur = self.app.conn.cursor()
            sql = "select distinct case_text.fid, source.name from case_text join source on case_text.fid=source.id where caseid=? order by source.name asc"
            cur.execute(sql, [self.cases[x]['caseid'], ])
            files = cur.fetchall()
            self.cases[x]['files'] = files
            self.fill_tableWidget()

    def fill_tableWidget(self):
        """ Fill the table widget with case details. """

        self.ui.label_cases.setText(_("Cases: ") + str(len(self.cases)))
        rows = self.ui.tableWidget.rowCount()
        for c in range(0, rows):
            self.ui.tableWidget.removeRow(0)

        self.ui.tableWidget.setColumnCount(len(self.header_labels))
        self.ui.tableWidget.setHorizontalHeaderLabels(self.header_labels)
        for row, c in enumerate(self.cases):
            self.ui.tableWidget.insertRow(row)
            self.ui.tableWidget.setItem(row, self.NAME_COLUMN,
            QtWidgets.QTableWidgetItem(c['name']))
            memotmp = c['memo']
            item = QtWidgets.QTableWidgetItem("")
            item.setToolTip(_("Click to edit memo"))
            if memotmp is not None and memotmp != "":
                item = QtWidgets.QTableWidgetItem(_("Memo"))
                item.setToolTip(_("Click to edit memo"))
            self.ui.tableWidget.setItem(row, self.MEMO_COLUMN, item)
            cid = c['caseid']
            if cid is None:
                cid = ""
            item = QtWidgets.QTableWidgetItem(str(cid))
            item.setFlags(QtCore.Qt.ItemIsEnabled)
            self.ui.tableWidget.setItem(row, self.ID_COLUMN, item)
            # Number of files assigned to case
            item = QtWidgets.QTableWidgetItem(str(len(c['files'])))
            item.setFlags(QtCore.Qt.ItemIsEnabled)
            item.setToolTip(_("Click to manage files for this case"))
            self.ui.tableWidget.setItem(row, self.FILES_COLUMN, item)

            # add the attribute values
            for a in self.attributes:
                for col, header in enumerate(self.header_labels):
                    if cid == a[2] and a[0] == header:
                        self.ui.tableWidget.setItem(row, col, QtWidgets.QTableWidgetItem(str(a[1])))
        self.ui.tableWidget.verticalHeader().setVisible(False)
        self.ui.tableWidget.resizeColumnsToContents()
        self.ui.tableWidget.resizeRowsToContents()
        self.ui.tableWidget.hideColumn(self.ID_COLUMN)
        if self.app.settings['showids'] == 'True':
            self.ui.tableWidget.showColumn(self.ID_COLUMN)

    def view(self):
        """ View all of the text associated with this case.
        Add links to open image files. """

        row = self.ui.tableWidget.currentRow()
        if row == -1:
            return
        if self.selected_case is None:
            return
        self.ui.textBrowser.clear()
        self.ui.textBrowser.setPlainText("")
        self.selected_file = None
        self.ui.label_filename.setText(_("Viewing text of case: ") + str(self.cases[row]['name']))
        display_text = []
        self.display_text_links = []
        cur = self.app.conn.cursor()
        cur.execute("select caseid, fid, pos0, pos1, owner, date, memo from case_text where caseid = ? order by fid, pos0",
            [self.selected_case['caseid'],])
        result = cur.fetchall()
        for row in result:
            caseText = ""
            fname = ""
            mediapath = ""
            for src in self.source:
                if src['id'] == row[1] and src['fulltext'] is not None:
                    caseText = src['fulltext'][int(row[2]):int(row[3])]
                    fname = src['name']
                if src['id'] == row[1] and src['fulltext'] is None:
                    fname = src['name']
                    mediapath = src['mediapath']
            display_text.append({'caseid': row[0], 'fid': row[1], 'pos0': row[2],
            'pos1': row[3], 'owner': row[4], 'date': row[5], 'memo': row[6],
            'text': caseText, 'name': fname, 'mediapath': mediapath})

        for c in display_text:
            if c['mediapath'] == '':  # text source
                header = "\n" + _("File: ") + c['name'] + _(" Text: ") + str(int(c['pos0'])) + ":" + str(int(c['pos1']))
                self.ui.textBrowser.append(header)
                fmt = QtGui.QTextCharFormat()
                brush = QtGui.QBrush(QtGui.QColor(QtCore.Qt.black))
                fmt.setForeground(brush)
                cursor = self.ui.textBrowser.textCursor()
                pos0 = len(self.ui.textBrowser.toPlainText()) - len(header)
                cursor.setPosition(pos0, QtGui.QTextCursor.MoveAnchor)
                pos1 = len(self.ui.textBrowser.toPlainText())
                cursor.setPosition(pos1, QtGui.QTextCursor.KeepAnchor)
                cursor.setCharFormat(fmt)
                formatB = QtGui.QTextCharFormat()
                formatB.setFontWeight(QtGui.QFont.Bold)
                cursor.mergeCharFormat(formatB)

                self.ui.textBrowser.append(c['text'])

            if c['mediapath'][:8] == "/images/":
                header = "\n" + _('Image: ') + c['name']
                self.ui.textBrowser.append(header)
                fmt = QtGui.QTextCharFormat()
                brush = QtGui.QBrush(QtGui.QColor(QtCore.Qt.blue))
                fmt.setForeground(brush)
                cursor = self.ui.textBrowser.textCursor()
                pos0 = len(self.ui.textBrowser.toPlainText()) - len(header)
                cursor.setPosition(pos0, QtGui.QTextCursor.MoveAnchor)
                pos1 = len(self.ui.textBrowser.toPlainText())
                cursor.setPosition(pos1, QtGui.QTextCursor.KeepAnchor)
                cursor.setCharFormat(fmt)
                # maybe review this approach for copying data over
                #Media data contains: {name, mediapath, owner, id, date, memo, fulltext}
                data = {'pos0': pos0, 'pos1': pos1, 'id': c['fid'], 'mediapath': c['mediapath'],
                        'owner': c['owner'], 'date': c['date'], 'memo': c['memo'], 'name': c['name']}
                self.display_text_links.append(data)

            if c['mediapath'][:7] == "/audio/" or c['mediapath'][:7] == "/video/":
                header = "\n" + _('AV media: ') + c['name']
                self.ui.textBrowser.append(header)
                fmt = QtGui.QTextCharFormat()
                brush = QtGui.QBrush(QtGui.QColor(QtCore.Qt.blue))
                fmt.setForeground(brush)
                cursor = self.ui.textBrowser.textCursor()
                pos0 = len(self.ui.textBrowser.toPlainText()) - len(header)
                cursor.setPosition(pos0, QtGui.QTextCursor.MoveAnchor)
                pos1 = len(self.ui.textBrowser.toPlainText())
                cursor.setPosition(pos1, QtGui.QTextCursor.KeepAnchor)
                cursor.setCharFormat(fmt)
                #Media data contains: {name, mediapath, owner, id, date, memo, fulltext}
                data = {'pos0': pos0, 'pos1': pos1, 'id': c['fid'], 'mediapath': c['mediapath'],
                        'owner': c['owner'], 'date': c['date'], 'memo': c['memo'], 'name': c['name']}
                self.display_text_links.append(data)

    ''' # removed images from the case text view, as they were affecting vertical position of previous text - too much white space
    document = self.ui.textBrowser.document()
                    image = QtGui.QImageReader(path).read()
                    document.addResource(QtGui.QTextDocument.ImageResource, url, QtCore.QVariant(image))
                    cursor = self.ui.textBrowser.textCursor()
                    image_format = QtGui.QTextImageFormat()
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
                    image_format.setWidth(image.width() * scaler)
                    image_format.setHeight(image.height() * scaler)
                    image_format.setName(url.toString())
                    cursor.insertImage(image_format)
                    self.ui.textBrowser.append("<br/>")'''

    def link_clicked(self, position):
        """ View image or audio/video media in dialog.
        For A/V, added try block in case VLC bindings do not work.  """

        cursor = self.ui.textBrowser.cursorForPosition(position)
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_link = None
        for item in self.display_text_links:
            if cursor.position() >= item['pos0'] and cursor.position() <= item['pos1']:
                action_link = menu.addAction(_("Open"))
        action = menu.exec_(self.ui.textBrowser.mapToGlobal(position))
        if action is None:
            return

        for item in self.display_text_links:
            if cursor.position() >= item['pos0'] and cursor.position() <= item['pos1']:
                try:
                    ui = None
                    if item['mediapath'][:6] == "/video":
                        ui = DialogViewAV(self.app, item)
                    if item['mediapath'][:6] == "/audio":
                        ui = DialogViewAV(self.app, item)
                    if item['mediapath'][:7] == "/images":
                        ui = DialogViewImage(self.app, item)
                    ui.exec_()
                except Exception as e:
                    logger.debug(str(e))
                    print(e)
                    QtWidgets.QMessageBox.warning(None, 'view av/images error', str(e), QtWidgets.QMessageBox.Ok)

    def textEdit_menu(self, position):
        """ Context menu for textEdit. Select all, Copy. """

        menu = QtWidgets.QMenu()
        action_select_all = menu.addAction(_("Select all"))
        action_copy = menu.addAction(_("Copy"))
        action = menu.exec_(self.ui.textBrowser.mapToGlobal(position))
        if action == action_select_all:
            self.ui.textBrowser.selectAll()
        if action == action_copy:
            selected_text = self.ui.textBrowser.textCursor().selectedText()
            cb = QtWidgets.QApplication.clipboard()
            cb.clear(mode=cb.Clipboard)
            cb.setText(selected_text, mode=cb.Clipboard)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    ui = DialogGetStartAndEndMarks("case one", ["file 1","file 2"])
    ui.show()
    sys.exit(app.exec_())

