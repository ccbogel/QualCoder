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
https://qualcoder.wordpress.com/
'''

from PyQt5 import QtCore, QtGui, QtWidgets
from GUI.ui_dialog_journals import Ui_Dialog_journals
from confirm_delete import DialogConfirmDelete
import datetime
import os
import logging

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogJournals(QtWidgets.QDialog):
    '''  View, create, export, rename and delete journals. '''

    NAME_COLUMN = 0
    DATE_COLUMN = 1
    OWNER_COLUMN = 2
    journals = []
    current_jid = None
    settings = None
    parent_textEdit = None
    textDialog = None

    def __init__(self, settings, parent_textEdit, parent=None):
        super(DialogJournals, self).__init__(parent)  # overrride accept method
        self.settings = settings
        self.parent_textEdit = parent_textEdit
        self.journals = []
        self.current_jid = None
        cur = self.settings['conn'].cursor()
        cur.execute("select name, date, jentry, owner, jid from journal")
        result = cur.fetchall()
        for row in result:
            self.journals.append({'name':row[0], 'date':row[1], 'jentry':row[2], 'owner':row[3], 'jid': row[4]})
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_journals()
        self.ui.setupUi(self)
        newfont = QtGui.QFont(settings['font'], settings['fontsize'], QtGui.QFont.Normal)
        self.setFont(newfont)
        self.ui.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        #self.ui.tableWidget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)

        for row, details in enumerate(self.journals):
            self.ui.tableWidget.insertRow(row)
            self.ui.tableWidget.setItem(row, self.NAME_COLUMN, QtWidgets.QTableWidgetItem(details['name']))
            item = QtWidgets.QTableWidgetItem(details['date'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.DATE_COLUMN, item)
            item = QtWidgets.QTableWidgetItem(details['owner'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.OWNER_COLUMN, item)

        self.ui.tableWidget.verticalHeader().setVisible(False)
        self.ui.tableWidget.resizeColumnsToContents()
        self.ui.tableWidget.resizeRowsToContents()
        self.ui.tableWidget.itemChanged.connect(self.cell_modified)
        self.ui.tableWidget.itemSelectionChanged.connect(self.table_selection_changed)
        self.ui.textEdit.textChanged.connect(self.text_changed)
        self.ui.pushButton_create.clicked.connect(self.create)
        self.ui.pushButton_export.clicked.connect(self.export)
        self.ui.pushButton_delete.clicked.connect(self.delete)

    def view(self):
        ''' View and edit journal contents in the textEdit '''

        x = self.ui.tableWidget.currentRow()
        if x == -1:
            self.current_jid = None
            self.ui.textEdit.setPlainText("")
            return
        self.current_jid = self.journals[x]['jid']
        self.ui.textEdit.blockSignals(True)
        self.ui.textEdit.setPlainText(self.journals[x]['jentry'])
        self.ui.textEdit.blockSignals(False)

    def text_changed(self):
        ''' journal entry is changed on changes to text edit.
        The signal is switched off when a different journal is loaded.
        Changes are not saved to database until dialog is closed.
        '''

        if self.current_jid is None:
            return
        #logger.debug("self.current_jid:" + str(self.current_jid))
        for j in range(0, len(self.journals)):
            if self.journals[j]['jid'] == self.current_jid:
                current_j = j
        self.journals[current_j]['jentry'] = self.ui.textEdit.toPlainText()

    def closeEvent(self, event):
        ''' Save journal text changes to database. '''

        cur = self.settings['conn'].cursor()
        for j in self.journals:
            cur.execute("select jentry from journal where jid=?", (j['jid'], ))
            result = cur.fetchone()
            result = result[0]
            if result != j['jentry']:
                cur.execute("update journal set jentry=? where jid=?",
                    (j['jentry'], j['jid']))
                self.parent_textEdit.append("Journal modified: " + j['name'])
        self.settings['conn'].commit()

    def create(self):
        ''' Create a new journal by entering text into the dialog '''

        self.current_jid = None
        self.ui.textEdit.setPlainText("")
        name, ok = QtWidgets.QInputDialog.getText(self, 'New journal', 'Enter the journal name:')
        if not ok:
            return
        if name is None or name == "":
            QtWidgets.QMessageBox.warning(None, 'Warning', "No name was entered",
                QtWidgets.QMessageBox.Ok)
            return
        # check for non-unique name
        if any(d['name'] == name for d in self.journals):
            QtWidgets.QMessageBox.warning(None, 'Warning', "Journal name in use",
                QtWidgets.QMessageBox.Ok)
            return

        # update database
        journal = {'name':name, 'jentry': '', 'owner':self.settings['codername'],
            'date':datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'jid':None}
        cur = self.settings['conn'].cursor()
        cur.execute("insert into journal(name,jentry,owner,date) values(?,?,?,?)",
            (journal['name'], journal['jentry'], journal['owner'], journal['date']))
        self.settings['conn'].commit()
        cur.execute("select last_insert_rowid()")
        jid = cur.fetchone()
        journal['jid'] = jid[0]
        self.parent_textEdit.append("Journal created:" + journal['name'])

        # clear and refill table widget
        for r in self.journals:
            self.ui.tableWidget.removeRow(0)
        self.journals.append(journal)
        for row, itm in enumerate(self.journals):
            self.ui.tableWidget.insertRow(row)
            item = QtWidgets.QTableWidgetItem(itm['name'])
            self.ui.tableWidget.setItem(row, self.NAME_COLUMN, item)
            item = QtWidgets.QTableWidgetItem(itm['date'])
            self.ui.tableWidget.setItem(row, self.DATE_COLUMN, item)
            item = QtWidgets.QTableWidgetItem(itm['owner'])
            self.ui.tableWidget.setItem(row, self.OWNER_COLUMN, item)
        self.ui.tableWidget.resizeColumnsToContents()
        self.ui.tableWidget.resizeRowsToContents()

        newest = len(self.journals) - 1
        if newest < 0:
            return
        self.ui.tableWidget.setCurrentCell(newest, 0)
        self.ui.textEdit.setFocus()

    def export(self):
        ''' Export journal to a plain text file, filename will have .txt ending '''

        x = self.ui.tableWidget.currentRow()
        if x == -1:
            return
        filename = self.journals[x]['name']
        filename += ".txt"
        options = QtWidgets.QFileDialog.DontResolveSymlinks | QtWidgets.QFileDialog.ShowDirsOnly
        directory = QtWidgets.QFileDialog.getExistingDirectory(None,
            "Select directory to save file", os.getenv('HOME'), options)
        if directory:
            filename = directory + "/" + filename
            data = self.journals[x]['jentry']
            f = open(filename, 'w')
            f.write(data)
            f.close()
            msg = "Journal exported to:\n" + str(filename)
            QtWidgets.QMessageBox.information(None, "Journal export", msg)
            self.parent_textEdit.append(msg)

    def delete(self):
        ''' Delete journal from database and update model and widget. '''

        x = self.ui.tableWidget.currentRow()
        if x == -1:
            return
        journalname = self.journals[x]['name']
        #logger.debug(("Delete row: " + str(x)))
        ui = DialogConfirmDelete(self.journals[x]['name'])
        ok = ui.exec_()

        if ok:
            cur = self.settings['conn'].cursor()
            cur.execute("delete from journal where name = ?", [journalname])
            self.settings['conn'].commit()
            for item in self.journals:
                if item['name'] == journalname:
                    self.journals.remove(item)
            self.ui.tableWidget.removeRow(x)
            self.parent_textEdit.append("Journal deleted: " + journalname)

    def table_selection_changed(self):
        ''' Update the journal text for the current selection. '''

        row = self.ui.tableWidget.currentRow()
        try:
            self.current_jid = self.journals[row]['jid']
            self.view()
            self.ui.label_jname.setText("Journal: " + self.journals[row]['name'])
        except IndexError:
            # occurs when journal deleted
            self.ui.label_jname("No journal selected")

    def cell_modified(self):
        ''' If the journal name has been changed in the table widget update the database
        '''

        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        if y == self.NAME_COLUMN:
            new_name = self.ui.tableWidget.item(x, y).text().strip()
            # check that no other journal has this name and it is not empty
            update = True
            if new_name == "":
                update = False
            for c in self.journals:
                if c['name'] == new_name:
                    update = False
            if update:
                # update source list and database
                cur = self.settings['conn'].cursor()
                cur.execute("update journal set name=? where name=?",
                    (new_name, self.journals[x]['name']))
                self.settings['conn'].commit()
                self.journals[x]['name'] = new_name
                self.parent_textEdit.append("Journal name changed: " + new_name)
            else:  # put the original text in the cell
                self.ui.tableWidget.item(x, y).setText(self.journals[x]['name'])

