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

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import Qt
import datetime
import re
from GUI.ui_dialog_cases import Ui_Dialog_cases
from GUI.ui_dialog_attribute_type import Ui_Dialog_attribute_type
from view_image import DialogViewImage
from add_item_name import DialogAddItemName
from confirm_delete import DialogConfirmDelete
from memo import DialogMemo
from select_file import DialogSelectFile
from GUI.ui_dialog_start_and_end_marks import Ui_Dialog_StartAndEndMarks
import csv
import os
import logging

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogCases(QtWidgets.QDialog):
    ''' Create, edit and delete cases.
    Assign entire text files or portions of files to cases.
    Assign attributes to cases. '''

    NAME_COLUMN = 0  # also primary key
    MEMO_COLUMN = 1
    ID_COLUMN = 2
    settings = None
    parent_textEdit = None
    source = []
    sourceText = ""
    cases = []
    case_text = []
    selected_case = None
    selected_file = None
    caseTextViewed = []
    attributes = []

    def __init__(self, settings, parent_textEdit):

        self.settings = settings
        self.parent_textEdit = parent_textEdit
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_cases()
        self.ui.setupUi(self)
        newfont = QtGui.QFont(settings['font'], settings['fontsize'], QtGui.QFont.Normal)
        self.setFont(newfont)
        self.load_cases_and_attributes()
        self.ui.pushButton_add.clicked.connect(self.add_case)
        self.ui.pushButton_delete.clicked.connect(self.delete_case)
        self.ui.tableWidget.itemChanged.connect(self.cell_modified)
        self.ui.tableWidget.cellClicked.connect(self.cell_selected)
        self.ui.pushButton_addfiles.clicked.connect(self.add_file_to_case)
        self.ui.pushButton_openfile.clicked.connect(self.select_file)
        self.ui.pushButton_add_attribute.clicked.connect(self.add_attribute)
        self.ui.pushButton_autoassign.clicked.connect(self.automark)
        self.ui.pushButton_view.clicked.connect(self.view)
        self.ui.pushButton_import_cases.clicked.connect(self.import_cases_and_attributes)
        self.ui.textBrowser.setText("")
        self.ui.textBrowser.setAutoFillBackground(True)
        self.ui.textBrowser.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.textBrowser.customContextMenuRequested.connect(self.textBrowser_menu)
        self.ui.textBrowser.setOpenLinks(False)
        self.ui.textBrowser.anchorClicked.connect(self.image_link_clicked)
        self.fill_tableWidget()
        self.ui.splitter.setSizes([1, 1, 0])

    def load_cases_and_attributes(self):
        '''Load case and attribute details from database. Display in tableWidget.
        '''

        self.source = []
        self.cases = []
        self.case_text = []

        cur = self.settings['conn'].cursor()
        cur.execute("select name, id, fulltext, imagepath, memo, owner, date from source")
        result = cur.fetchall()
        for row in result:
            self.source.append({'name': row[0], 'id': row[1], 'fulltext': row[2],
            'imagepath': row[3], 'memo': row[4], 'owner': row[5], 'date': row[6]})
        cur.execute("select name, memo, owner, date, caseid from cases")
        result = cur.fetchall()
        for row in result:
            self.cases.append({'name': row[0], 'memo': row[1], 'owner': row[2], 'date': row[3],
            'caseid': row[4]})
        cur.execute("select name from attribute_type where caseOrFile='case'")
        attribute_names = cur.fetchall()
        self.headerLabels = ["Name", "Memo", "Id"]
        for i in attribute_names:
            self.headerLabels.append(i[0])
        sql = "select attribute.name, value, id from attribute where attr_type='case'"
        cur.execute(sql)
        result = cur.fetchall()
        self.attributes = []
        for row in result:
            self.attributes.append(row)

    def add_attribute(self):
        ''' When add button pressed, opens the addItem dialog to get new attribute text.
        Then get the attribute type through a dialog.
        AddItem dialog checks for duplicate attribute name.
        New attribute is added to the model and database '''

        cur = self.settings['conn'].cursor()
        cur.execute("select name from attribute_type where caseOrFile='case'")
        result = cur.fetchall()
        attribute_names = []
        for a in result:
            attribute_names.append({'name': a[0]})
        check_names = attribute_names + [{'name': 'name'}, {'name':'memo'}, {'name':'caseid'}, {'name':'date'}]
        ui = DialogAddItemName(check_names, "New attribute name")
        ui.exec_()
        name = ui.get_new_name()
        if name is None or name == "":
            return
        Dialog_type = QtWidgets.QDialog()
        ui = Ui_Dialog_attribute_type()
        ui.setupUi(Dialog_type)
        ok = Dialog_type.exec_()
        valuetype = "character"
        if ok and ui.radioButton_numeric.isChecked():
            valuetype = "numeric"
        #self.attribute_names.append({'name': name})
        # update attribute_type list and database
        now_date = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        cur = self.settings['conn'].cursor()
        cur.execute("insert into attribute_type (name,date,owner,memo,caseOrFile, valuetype) values(?,?,?,?,?,?)"
            ,(name, now_date, self.settings['codername'], "", 'case', valuetype))
        self.settings['conn'].commit()
        sql = "select caseid from cases"
        cur.execute(sql)
        case_ids = cur.fetchall()
        for id_ in case_ids:
            sql = "insert into attribute (name, value, id, attr_type, date, owner) values (?,?,?,?,?,?)"
            cur.execute(sql, (name, "", id_[0], 'case', now_date, self.settings['codername']))
        self.settings['conn'].commit()
        self.load_cases_and_attributes()
        self.fill_tableWidget()
        self.parent_textEdit.append("Attribute added to cases: " + name + ", type: " + valuetype)

    def textBrowser_menu(self, position):
        ''' Context menu for textBrowser. Mark, unmark, annotate, copy. '''

        menu = QtWidgets.QMenu()
        if self.ui.textBrowser.toPlainText() == "":
            return
        ActionItemMark = menu.addAction("Mark")
        ActionItemUnmark = menu.addAction("Unmark")
        ActionItemCopy = menu.addAction("Copy")
        action = menu.exec_(self.ui.textBrowser.mapToGlobal(position))
        if action == ActionItemMark:
            self.mark()
        if action == ActionItemUnmark:
            self.unmark()
        if action == ActionItemCopy:
            self.copy_selected_text_to_clipboard()

    def copy_selected_text_to_clipboard(self):
        '''  '''

        selectedText = self.ui.textBrowser.textCursor().selectedText()
        cb = QtWidgets.QApplication.clipboard()
        cb.clear(mode=cb.Clipboard)
        cb.setText(selectedText, mode=cb.Clipboard)

    def import_cases_and_attributes(self):
        ''' Import from a csv file with the cases and any attributes.
        The csv file must have a header row which details the attribute names.
        The csv file must be comma delimited. The first column must have the case ids.
        The attribute types are calculated from the data.
        '''

        if self.cases != []:
            logger.warning("Cases have already been created.")
        filename = QtWidgets.QFileDialog.getOpenFileName(None, 'Select attributes file',
            self.settings['directory'], "(*.csv)")[0]
        if filename == "":
            return
        if filename[-4:].lower() != ".csv":
            msg = filename + "\nis not a .csv file.\nFile not imported"
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
            logger.info("Cannot import from csv, only one row in file")
            return
        now_date = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        header = values[0]
        values = values[1:]
        # insert cases
        cur = self.settings['conn'].cursor()
        for v in values:
            item = {'name': v[0], 'memo': "", 'owner': self.settings['codername'],
                'date': now_date}
            try:
                cur.execute("insert into cases (name,memo,owner,date) values(?,?,?,?)"
                    ,(item['name'],item['memo'],item['owner'],item['date']))
                self.settings['conn'].commit()
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
                    , (att_name, now_date, self.settings['codername'], "",
                    attribute_value_type[col], 'case'))
                    self.settings['conn'].commit()
                except Exception as e:
                    logger.error("attribute:" + att_name + ", " + str(e))
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
                        now_date, self.settings['codername']))
        self.settings['conn'].commit()
        self.load_cases_and_attributes()
        self.fill_tableWidget()
        msg = "Cases and attributes from " + filename + " imported."
        self.parent_textEdit.append(msg)
        logger.info(msg)

    def add_case(self):
        """ When add case button pressed, open addItem dialog to get the ase name.
        AddItem dialog checks for duplicate case name.
        New case is added to the model and database.
        Attribute placeholders are assigned to the database for this new case. """

        ui = DialogAddItemName(self.cases, "Case")
        ui.exec_()
        newCaseText = ui.get_new_name()
        if newCaseText is None:
            return
        # update case list and database
        item = {'name': newCaseText, 'memo': "", 'owner': self.settings['codername'],
                 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        cur = self.settings['conn'].cursor()
        cur.execute("insert into cases (name,memo,owner,date) values(?,?,?,?)"
            ,(item['name'],item['memo'],item['owner'],item['date']))
        self.settings['conn'].commit()
        cur.execute("select last_insert_rowid()")
        item['caseid'] = cur.fetchone()[0]
        # add placeholder attribute values
        cur.execute("select name, valuetype from attribute_type where caseOrFile='case'")
        atts = cur.fetchall()
        for att in atts:
            cur.execute("insert into attribute(name,attr_type,value,id,date,owner) \
                values (?,?,?,?,?,?)",
                (att[0], "case", "", item['caseid'], item['date'], item['owner']))
        self.settings['conn'].commit()
        self.cases.append(item)
        self.fill_tableWidget()
        self.parent_textEdit.append("Case added: " + item['name'])

    def delete_case(self):
        ''' When delete button pressed, case is deleted from model and database '''

        tableRowsToDelete = []  # for table widget ids
        caseNamesToDelete = ""  # for confirmDelete Dialog
        idsToDelete = []  # for ids for cases and db

        for itemWidget in self.ui.tableWidget.selectedItems():
            tableRowsToDelete.append(int(itemWidget.row()))
            idsToDelete.append(int(self.ui.tableWidget.item(itemWidget.row(),
            self.ID_COLUMN).text()))
            caseNamesToDelete = caseNamesToDelete + "\n" + str(self.ui.tableWidget.item(itemWidget.row(),
            self.NAME_COLUMN).text())
            #logger.debug("X:"+ str(itemWidget.row()) + "  y:"+str(itemWidget.column()) +"  "+itemWidget.text() +"  id:"+str(self.tableWidget_codes.item(itemWidget.row(),3).text()))
        tableRowsToDelete.sort(reverse=True)
        if len(caseNamesToDelete) == 0:
            return
        ui = DialogConfirmDelete(caseNamesToDelete)
        ok = ui.exec_()
        if not ok:
            return
        for id in idsToDelete:
            for c in self.cases:
                if c['caseid'] == id:
                    self.parent_textEdit.append("Case deleted: " + c['name'])
                    self.cases.remove(c)
                    cur = self.settings['conn'].cursor()
                    #logger.debug(str(id) + "  "+ str(type(id)))
                    cur.execute("delete from cases where caseid = ?", [id])
                    cur.execute("delete from case_text where caseid = ?", [id])
                    sql = "delete from attribute where id=? and attr_type='case'"
                    cur.execute(sql, [id])
                    self.settings['conn'].commit()
        self.fill_tableWidget()

    def cell_modified(self):
        ''' If the case name has been changed in the table widget update the database '''

        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        if y == self.NAME_COLUMN:  # update case name
            newText = str(self.ui.tableWidget.item(x, y).text()).strip()
            # check that no other case name has this text and this is not empty
            update = True
            if newText == "":
                update = False
            for c in self.cases:
                if c['name'] == newText:
                    update = False
            if update:
                cur = self.settings['conn'].cursor()
                cur.execute("update cases set name=? where caseid=?", (newText, self.cases[x]['caseid']))
                self.settings['conn'].commit()
                self.cases[x]['name'] = newText
            else:  # put the original text in the cell
                self.ui.tableWidget.item(x, y).setText(self.cases[x]['name'])
        if y > 2:  # update attribute value
            value = str(self.ui.tableWidget.item(x, y).text()).strip()
            attribute_name = self.headerLabels[y]
            cur = self.settings['conn'].cursor()
            cur.execute("update attribute set value=? where id=? and name=? and attr_type='case'",
            (value, self.cases[x]['caseid'], attribute_name))
            self.settings['conn'].commit()

    def cell_selected(self):
        '''
        Highlight case text if a file is selected.
        Indicate memo is present, update memo text, or delete memo by clearing text.
        '''

        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()

        if x == -1:
            self.selected_case = None
            self.ui.textBrowser.clear()
            self.case_text = []
            return
        self.selected_case = self.cases[x]
        # clear case text viewed if the caseid has changed
        if self.caseTextViewed != [] and self.caseTextViewed[0]['caseid'] != self.selected_case['caseid']:
            self.caseTextViewed = []
            self.case_text = []
            self.ui.textBrowser.clear()
        self.unlight()
        #logger.debug("Selected case: " + str(self.selected_case['id']) +" "+self.selected_case['name'])
        # get case_text for this file
        if self.selected_file is not None:
            #logger.debug("File Selected: " + str(self.selected_file['id'])+"  "+self.selected_file['file'])
            self.case_text = []
            cur = self.settings['conn'].cursor()
            cur.execute("select caseid, fid, pos0, pos1, owner, date, memo from case_text where fid = ? and caseid = ?",
                [self.selected_file['id'], self.selected_case['caseid']])
            result = cur.fetchall()
            for row in result:
                self.case_text.append({'caseid': row[0], 'fid': row[1], 'pos0': row[2],
                'pos1': row[3], 'owner': row[4], 'date': row[5], 'memo': row[6]})
        self.highlight()

        if y == self.MEMO_COLUMN:
            ui = DialogMemo(self.settings, "Memo for case " + self.cases[x]['name'],
                self.cases[x]['memo'])
            ui.exec_()
            self.cases[x]['memo'] = ui.memo
            cur = self.settings['conn'].cursor()
            cur.execute('update cases set memo=? where caseid=?', (self.cases[x]['memo'], self.cases[x]['caseid']))
            self.settings['conn'].commit()
            if self.cases[x]['memo'] == "":
                self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem())
            else:
                self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem("Yes"))

    def fill_tableWidget(self):
        ''' Fill the table widget with case details '''

        rows = self.ui.tableWidget.rowCount()
        for c in range(0, rows):
            self.ui.tableWidget.removeRow(0)

        self.ui.tableWidget.setColumnCount(len(self.headerLabels))
        self.ui.tableWidget.setHorizontalHeaderLabels(self.headerLabels)
        for row, c in enumerate(self.cases):
            self.ui.tableWidget.insertRow(row)
            self.ui.tableWidget.setItem(row, self.NAME_COLUMN,
            QtWidgets.QTableWidgetItem(c['name']))
            memotmp = c['memo']
            if memotmp is not None and memotmp != "":
                self.ui.tableWidget.setItem(row, self.MEMO_COLUMN,
                QtWidgets.QTableWidgetItem("Yes"))
            cid = c['caseid']
            if cid is None:
                cid = ""
            self.ui.tableWidget.setItem(row, self.ID_COLUMN, QtWidgets.QTableWidgetItem(str(cid)))
            # add the attribute values
            for a in self.attributes:
                for col, header in enumerate(self.headerLabels):
                    if cid == a[2] and a[0] == header:
                        self.ui.tableWidget.setItem(row, col, QtWidgets.QTableWidgetItem(str(a[1])))
        self.ui.tableWidget.verticalHeader().setVisible(False)
        self.ui.tableWidget.resizeColumnsToContents()
        self.ui.tableWidget.resizeRowsToContents()
        self.ui.tableWidget.hideColumn(self.ID_COLUMN)
        if self.settings['showIDs']:
            self.ui.tableWidget.showColumn(self.ID_COLUMN)

    def add_file_to_case(self):
        ''' When select file button is pressed a dialog of filenames is presented to the user.
        The entire text of the selected file is then added to the selected case.
        '''

        x = self.ui.tableWidget.currentRow()
        if x == -1:
            QtWidgets.QMessageBox.warning(None, 'Warning', "No case was selected")
            return
        ui = DialogSelectFile(self.source,
        "Select entire file for case: " + self.cases[x]['name'], "single")
        ok = ui.exec_()
        if not ok:
            return
        casefile = ui.get_selected()
        logger.debug(casefile)
        text_len = 0
        if casefile['fulltext'] is not None:
            text_len = len(casefile['fulltext'])
        newlink = {'caseid': self.cases[x]['caseid'], 'fid': casefile['id'], 'pos0': 0,
        'pos1': text_len, 'owner': self.settings['codername'],
        'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'memo': ""}

        cur = self.settings['conn'].cursor()
        # check for an existing duplicated liked file first
        cur.execute("select * from case_text where caseid = ? and fid=? and pos0=? and pos1=?",
            (newlink['caseid'], newlink['fid'], newlink['pos0'], newlink['pos1']))
        result = cur.fetchall()
        if len(result) > 0:
            QtWidgets.QMessageBox.warning(None, "Already Linked",
            "This file has already been linked to this case")
            return
        cur.execute("insert into case_text (caseid, fid, pos0, pos1, owner, date, memo) values(?,?,?,?,?,?,?)"
            ,(newlink['caseid'],newlink['fid'],newlink['pos0'],newlink['pos1'],
            newlink['owner'],newlink['date'], newlink['memo']))
        self.settings['conn'].commit()
        msg = casefile['name'] + " added to case. "
        QtWidgets.QMessageBox.information(None, "File added to case", msg)
        self.parent_textEdit.append(msg)

    def select_file(self):
        ''' When open file button is pressed a dialog of filenames is presented to the user.
        The selected file is then used to view and for assigning text portions to cases

        Start with clear selection to save confusion of loading file text and not having it
        highlighted for a currently selected case '''

        self.ui.tableWidget.clearSelection()
        self.case_text = []
        ui = DialogSelectFile(self.source, "Select file to view", "single")
        ok = ui.exec_()
        if not ok:
            return
        # selected_file is dictionary with id and name
        self.selected_file = ui.get_selected()
        if self.selected_file['fulltext'] is not None:
            chars = str(len(self.selected_file['fulltext']))
            self.ui.label_filename.setText("File: " + self.selected_file['name'] + " [chars: " + chars + "]")
            self.ui.textBrowser.setText(self.selected_file['fulltext'])
            self.caseTextViewed = []
            self.unlight()
            self.highlight()
        else:
            self.ui.textBrowser.setText("")
            ui = DialogViewImage(self.settings, self.selected_file)
            ui.exec_()
            memo = ui.ui.textEdit.toPlainText()
            if self.selected_file['memo'] != memo:
                self.selected_file['memo'] = memo
                cur = self.settings['conn'].cursor()
                cur.execute('update source set memo=? where id=?',
                    (self.selected_file['memo'], self.selected_file['id']))
                self.settings['conn'].commit()

    def unlight(self):
        ''' Remove all text highlighting from current file '''

        if self.selected_file is None:
            return
        if self.selected_file['fulltext'] is None:
            return
        cursor = self.ui.textBrowser.textCursor()
        try:
            cursor.setPosition(0, QtGui.QTextCursor.MoveAnchor)
            cursor.setPosition(len(self.selected_file['fulltext']) - 1, QtGui.QTextCursor.KeepAnchor)
            cursor.setCharFormat(QtGui.QTextCharFormat())
        except Exception as e:
            logger.debug((str(e) + "\n unlight, text length" +str(len(self.textBrowser.toPlainText()))))

    def highlight(self):
        ''' Apply text highlighting to current file.
        Highlight text of selected case with red underlining.
        #format_.setForeground(QtGui.QColor("#990000")) '''

        if self.selected_file is None:
            return
        if self.selected_file['fulltext'] is None:
            return
        format_ = QtGui.QTextCharFormat()
        cursor = self.ui.textBrowser.textCursor()
        for item in self.case_text:
            try:
                cursor.setPosition(int(item['pos0']), QtGui.QTextCursor.MoveAnchor)
                cursor.setPosition(int(item['pos1']), QtGui.QTextCursor.KeepAnchor)
                format_.setFontUnderline(True)
                format_.setUnderlineColor(QtCore.Qt.red)
                cursor.setCharFormat(format_)
            except:
                msg = "highlight, text length " + str(len(self.ui.textBrowser.toPlainText()))
                msg += "\npos0:" + str(item['pos0']) + ", pos1:" + str(item['pos1'])
                logger.debug(msg)

    def view(self):
        ''' View all of the text associated with this case.
        Add links to open image files. '''

        row = self.ui.tableWidget.currentRow()
        if row == -1:
            return
        if self.selected_case is None:
            return
        self.selected_file = None
        self.ui.label_filename.setText("Viewing text of case: " + str(self.cases[row]['name']))
        self.ui.textBrowser.clear()
        self.caseTextViewed = []
        cur = self.settings['conn'].cursor()
        cur.execute("select caseid, fid, pos0, pos1, owner, date, memo from case_text where caseid = ? order by fid, pos0",
            [self.selected_case['caseid'],])
        result = cur.fetchall()
        for row in result:
            caseText = ""
            sourcename = ""
            imagepath = ""
            for src in self.source:
                if src['id'] == row[1] and src['fulltext'] is not None:
                    caseText = src['fulltext'][int(row[2]):int(row[3])]
                    sourcename = src['name']
                if src['id'] == row[1] and src['fulltext'] is None:
                    sourcename = src['name']
                    imagepath = src['imagepath']
            self.caseTextViewed.append({'caseid': row[0], 'fid': row[1], 'pos0': row[2],
            'pos1': row[3], 'owner': row[4], 'date': row[5], 'memo': row[6],
            'text': caseText, 'sourcename': sourcename, 'imagepath': imagepath})

        for c in self.caseTextViewed:
            if c['imagepath'] == '':
                self.ui.textBrowser.append("<b>" + "File: " + c['sourcename'] + " Text: " +
                str(int(c['pos0'])) + ":" + str(int(c['pos1'])) + "</b>")
                self.ui.textBrowser.append(c['text'])
            else:
                self.ui.textBrowser.append('<b><a href="' + c['imagepath'] + '"> Image: ' + c['sourcename'] + '</a></b>')
                path = self.settings['path'] + '/images/' + c['imagepath']
                url = QtCore.QUrl(path)
                document = self.ui.textBrowser.document()
                image = QtGui.QImageReader(path).read()
                document.addResource(QtGui.QTextDocument.ImageResource, url, QtCore.QVariant(image))
                cursor = self.ui.textBrowser.textCursor()
                image_format = QtGui.QTextImageFormat()
                scaler = 1.0
                scaler_w =1.0
                scaler_h = 1.0
                if image.width() > 400:
                    scaler_w = 400 / image.width()
                if image.height() > 400:
                    scaler_h = 400 / image.height()
                if scaler_w < scaler_h:
                    scaler = scaler_w
                else:
                    scaler = scaler_h

                image_format.setWidth(image.width() * scaler)
                image_format.setHeight(image.height() * scaler)
                image_format.setName(url.toString())
                cursor.insertImage(image_format)
                #self.ui.textBrowser.append('<img src="' + path + '" style="width:100px;height:100px;"/>')

    def image_link_clicked(self, url):
        ''' View image in dialog. '''

        x = -1
        for i in range(0, len(self.source)):
            if url.toString() == self.source[i]['imagepath']:
                x = i
        if x == -1:
            return
        ui = DialogViewImage(self.settings, self.source[x])
        ui.exec_()
        memo = ui.ui.textEdit.toPlainText()
        if self.source[x]['memo'] != memo:
            self.source[x]['memo'] = memo
            cur = self.settings['conn'].cursor()
            cur.execute('update source set memo=? where id=?', (self.source[x]['memo'], self.source[x]['id']))
            self.settings['conn'].commit()

    def mark(self):
        ''' Mark selected text in file with currently selected case '''

        if self.selected_file is None:
            return
        row = self.ui.tableWidget.currentRow()
        if row == -1:
            return
        #selectedText = self.textBrowser.textCursor().selectedText()
        pos0 = self.ui.textBrowser.textCursor().selectionStart()
        pos1 = self.ui.textBrowser.textCursor().selectionEnd()
        # add new item to case_text list and database and update GUI
        item = {'caseid': int(self.cases[row]['caseid']), 'fid': int(self.selected_file['id']),
        'pos0': pos0, 'pos1': pos1, 'owner': self.settings['codername'],
        'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'memo': ""}
        self.case_text.append(item)
        self.highlight()

        cur = self.settings['conn'].cursor()
        # check for an existing duplicated linkage first
        cur.execute("select * from case_text where caseid = ? and fid=? and pos0=? and pos1=?",
            (item['caseid'], item['fid'], item['pos0'], item['pos1']))
        result = cur.fetchall()
        if len(result) > 0:
            QtWidgets.QMessageBox.warning(None, "Already Linked",
                "This segment has already been linked to this case")
            return
        cur.execute("insert into case_text (caseid,fid, pos0, pos1, owner, date, memo) values(?,?,?,?,?,?,?)"
            ,(item['caseid'],item['fid'],item['pos0'],item['pos1'],item['owner'],item['date'],item['memo']))
        self.settings['conn'].commit()

    def unmark(self):
        ''' Remove case marking from selected text in selected file '''

        if self.selected_file is None:
            return
        if len(self.case_text) == 0:
            return
        location = self.ui.textBrowser.textCursor().selectionStart()
        unmarked = None
        for item in self.case_text:
            if location >= item['pos0'] and location <= item['pos1']:
                unmarked = item
        if unmarked is None:
            return

        # delete from database, remove from case_text and update gui
        cur = self.settings['conn'].cursor()
        cur.execute("delete from case_text where fid=? and caseid=? and pos0=? and pos1=?",
            (unmarked['fid'], unmarked['caseid'], unmarked['pos0'], unmarked['pos1']))
        self.settings['conn'].commit()
        if unmarked in self.case_text:
            self.case_text.remove(unmarked)
        self.unlight()
        self.highlight()

    def automark(self):
        ''' Automark text in one or more files with selected case.
        '''

        row = self.ui.tableWidget.currentRow()
        if row == -1:
            QtWidgets.QMessageBox.warning(None, 'Warning', "No case was selected")
            return
        ui = DialogSelectFile(self.source, "Select file(s) to assign case", "many")
        ok = ui.exec_()
        if not ok:
            return
        files = ui.get_selected()
        if len(files) == 0:
            QtWidgets.QMessageBox.warning(None, 'Warning', "No file was selected")
            return
        #logger.debug(str(files))
        #logger.debug(str(type(files)))
        filenames = ""
        for f in files:
            filenames += f['name'] + " "
        ui = DialogGetStartAndEndMarks(self.cases[row]['name'], filenames)
        ok = ui.exec_()
        if not ok:
            return
        start_mark = ui.get_start_mark()
        end_mark = ui.get_end_mark()
        if start_mark == "" or end_mark == "":
            QtWidgets.QMessageBox.warning(None, 'Warning', "Cannot have blank text marks")
            return
        warnings = 0
        for f in files:
            cur = self.settings['conn'].cursor()
            cur.execute("select name, id, fulltext, memo, owner, date from source where id=?",
                [f['id']])
            currentfile = cur.fetchone()
            text = currentfile[2]
            textStarts = [match.start() for match in re.finditer(re.escape(start_mark), text)]
            textEnds = [match.start() for match in re.finditer(re.escape(end_mark), text)]
            #logger.debug(textStarts, textEnds)
            #add new code linkage items to database
            for startPos in textStarts:
                pos1 = -1  # default if not found
                textEndIterator = 0
                try:
                    while startPos >= textEnds[textEndIterator]:
                        textEndIterator += 1
                except IndexError:
                    textEndIterator = -1
                    warnings += 1
                    logger.warning(f['name'] + ". Could not find end mark: " + end_mark)

                if textEndIterator >= 0:
                    pos1 = textEnds[textEndIterator]
                    item = {'caseid': int(self.cases[row]['caseid']), 'fid': int(f['id']),
                    'pos0': startPos, 'pos1': pos1,
                    'owner': self.settings['codername'],
                    'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'memo': ""}

                    cur = self.settings['conn'].cursor()
                    cur.execute("insert into case_text (caseid,fid,pos0,pos1,owner,date,memo) values(?,?,?,?,?,?,?)"
                        ,(item['caseid'], item['fid'], item['pos0'], item['pos1'],
                          item['owner'], item['date'], item['memo']))
                    self.settings['conn'].commit()
        if warnings > 0:
            QtWidgets.QMessageBox.warning(None, 'Warning',
                 str(warnings) + " end mark did not match up")
        self.ui.tableWidget.clearSelection()


class DialogGetStartAndEndMarks(QtWidgets.QDialog):
    ''' This dialog gets the start and end mark text to allow file text to be
    automatically assigned to the currently selected case.
    It requires the name of the selected case and the filenames - for display purposes only.
    Methods return the user's choices for the startmark text and the endmark text.
    '''

    caseName = ""

    def __init__(self, case_name, filenames):

        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_StartAndEndMarks()
        self.ui.setupUi(self)
        self.ui.label_case.setText(case_name)
        self.ui.label_files.setText("Files: " + str(filenames))

    def get_start_mark(self):
        return str(self.ui.lineEdit_startmark.text())

    def get_end_mark(self):
        return str(self.ui.lineEdit_endmark.text())


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    ui = DialogGetStartAndEndMarks("case one", ["file 1","file 2"])
    ui.show()
    sys.exit(app.exec_())

