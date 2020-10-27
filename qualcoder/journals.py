# -*- coding: utf-8 -*-

'''
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
'''

from PyQt5 import QtCore, QtWidgets
import datetime
import os
import re
import sys
import logging
import traceback

from add_item_name import DialogAddItemName
from confirm_delete import DialogConfirmDelete
from GUI.ui_dialog_journals import Ui_Dialog_journals

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception: ") + text)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 12pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(text)
    mb.exec_()


class DialogJournals(QtWidgets.QDialog):
    '''  View, create, export, rename and delete journals. '''

    NAME_COLUMN = 0
    DATE_COLUMN = 1
    OWNER_COLUMN = 2
    journals = []
    current_jid = None
    app = None
    parent_textEdit = None
    textDialog = None

    def __init__(self, app, parent_textEdit, parent=None):

        super(DialogJournals, self).__init__(parent)  # overrride accept method
        sys.excepthook = exception_handler
        self.app = app
        self.parent_textEdit = parent_textEdit
        self.journals = []
        self.current_jid = None
        cur = self.app.conn.cursor()
        cur.execute("select name, date, jentry, owner, jid from journal")
        result = cur.fetchall()
        for row in result:
            self.journals.append({'name':row[0], 'date':row[1], 'jentry':row[2], 'owner':row[3], 'jid': row[4]})
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_journals()
        self.ui.setupUi(self)
        try:
            w = int(self.app.settings['dialogjournals_w'])
            h = int(self.app.settings['dialogjournals_h'])
            if h > 50 and w > 50:
                self.resize(w, h)
        except:
            pass
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.ui.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        #self.ui.tableWidget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        try:
            s0 = int(self.app.settings['dialogjournals_splitter0'])
            s1 = int(self.app.settings['dialogjournals_splitter1'])
            if s0 > 10 and s1 > 10:
                self.ui.splitter.setSizes([s0, s1])
        except:
            pass
        self.ui.label_jcount.setText(_("Journals: ") + str(len(self.journals)))
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
        """ View and edit journal contents in the textEdit """

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
        """ journal entry is changed on changes to text edit.
        The signal is switched off when a different journal is loaded.
        Changes are not saved to database until dialog is closed.
        """

        if self.current_jid is None:
            return
        #logger.debug("self.current_jid:" + str(self.current_jid))
        for j in range(0, len(self.journals)):
            if self.journals[j]['jid'] == self.current_jid:
                current_j = j
        self.journals[current_j]['jentry'] = self.ui.textEdit.toPlainText()
        self.app.delete_backup = False

    def closeEvent(self, event):
        """ Save journal text changes to database.
        Save dialog and splitter dimensions. """

        self.app.settings['dialogjournals_w'] = self.size().width()
        self.app.settings['dialogjournals_h'] = self.size().height()
        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogjournals_splitter0'] = sizes[0]
        self.app.settings['dialogjournals_splitter1'] = sizes[1]

        cur = self.app.conn.cursor()
        for j in self.journals:
            cur.execute("select jentry from journal where jid=?", (j['jid'], ))
            result = cur.fetchone()
            result = result[0]
            if result != j['jentry']:
                cur.execute("update journal set jentry=? where jid=?",
                    (j['jentry'], j['jid']))
                self.parent_textEdit.append(_("Journal modified: ") + j['name'])
        self.app.conn.commit()

    def create(self):
        """ Create a new journal by entering text into the dialog. """

        self.current_jid = None
        self.ui.textEdit.setPlainText("")

        ui = DialogAddItemName(self.app, self.journals, _('New Journal'), _('Journal name'))
        ui.exec_()
        name = ui.get_new_name()
        if name is None:
            return
        # Check for unusual characters in filename that would affect exporting
        valid = re.match('^[\ \w-]+$', name) is not None
        if not valid:
            mb = QtWidgets.QMessageBox()
            mb.setIcon(QtWidgets.QMessageBox.Warning)
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            mb.setWindowTitle(_('Warning - invalid characters'))
            msg = _("In the journal name use only: a-z, A-z 0-9 - space")
            mb.setText(msg)
            mb.exec_()
            return

        # update database
        journal = {'name':name, 'jentry': '', 'owner':self.app.settings['codername'],
            'date':datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'jid':None}
        cur = self.app.conn.cursor()
        cur.execute("insert into journal(name,jentry,owner,date) values(?,?,?,?)",
            (journal['name'], journal['jentry'], journal['owner'], journal['date']))
        self.app.conn.commit()
        cur.execute("select last_insert_rowid()")
        jid = cur.fetchone()
        journal['jid'] = jid[0]
        self.parent_textEdit.append(_("Journal created: ") + journal['name'])

        # clear and refill table widget
        for r in self.journals:
            self.ui.tableWidget.removeRow(0)
        self.journals.append(journal)
        self.ui.label_jcount.setText(_("Journals: ") + str(len(self.journals)))

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
        """ Export journal to a plain text file, filename will have .txt ending. """

        x = self.ui.tableWidget.currentRow()
        if x == -1:
            return
        filename = self.journals[x]['name']
        filename += ".txt"
        options = QtWidgets.QFileDialog.DontResolveSymlinks | QtWidgets.QFileDialog.ShowDirsOnly
        directory = QtWidgets.QFileDialog.getExistingDirectory(None,
            _("Select directory to save file"), self.app.last_export_directory, options)
        if directory:
            if directory != self.app.last_export_directory:
                self.app.last_export_directory = directory
            filename = directory + "/" + filename
            if os.path.exists(filename):
                mb = QtWidgets.QMessageBox()
                mb.setWindowTitle(_("File exists"))
                mb.setText(_("Overwrite?"))
                mb.setStandardButtons(QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
                mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
                if mb.exec_() == QtWidgets.QMessageBox.No:
                    return
            data = self.journals[x]['jentry']
            f = open(filename, 'w')
            f.write(data)
            f.close()
            msg = _("Journal exported to: ") + str(filename)
            mb = QtWidgets.QMessageBox()
            mb.setIcon(QtWidgets.QMessageBox.Warning)
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            mb.setWindowTitle(_('Journal export'))
            mb.setText(msg)
            mb.exec_()
            self.parent_textEdit.append(msg)

    def delete(self):
        """ Delete journal from database and update model and widget. """

        x = self.ui.tableWidget.currentRow()
        if x == -1:
            return
        journalname = self.journals[x]['name']
        #logger.debug(("Delete row: " + str(x)))
        ui = DialogConfirmDelete(self.app, self.journals[x]['name'])
        ok = ui.exec_()

        if ok:
            cur = self.app.conn.cursor()
            cur.execute("delete from journal where name = ?", [journalname])
            cur = self.app.conn.commit()
            for item in self.journals:
                if item['name'] == journalname:
                    self.journals.remove(item)
            self.ui.tableWidget.removeRow(x)
            self.parent_textEdit.append(_("Journal deleted: ") + journalname)
            self.ui.label_jcount.setText(_("Journals: ") + str(len(self.journals)))

    def table_selection_changed(self):
        """ Update the journal text for the current selection. """

        row = self.ui.tableWidget.currentRow()
        try:
            self.current_jid = self.journals[row]['jid']
            self.view()
            self.ui.label_jname.setText(_("Journal: ") + self.journals[row]['name'])
        except IndexError:
            # occurs when journal deleted
            self.ui.label_jname.setText(_("No journal selected"))

    def cell_modified(self):
        """ If the journal name has been changed in the table widget update the database
        """

        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        if y == self.NAME_COLUMN:
            new_name = self.ui.tableWidget.item(x, y).text().strip()
            # check that no other journal has this name and it is not empty
            update = True
            if new_name == "":
                mb = QtWidgets.QMessageBox()
                mb.setIcon(QtWidgets.QMessageBox.Warning)
                mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
                mb.setWindowTitle(_('Warning'))
                mb.setText(_("No name was entered"))
                mb.exec_()
                update = False
            for c in self.journals:
                if c['name'] == new_name:
                    mb = QtWidgets.QMessageBox()
                    mb.setIcon(QtWidgets.QMessageBox.Warning)
                    mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
                    mb.setWindowTitle(_('Warning'))
                    mb.setText(_("Journal name in use"))
                    mb.exec_()
                    update = False
            # Check for unusual characters in filename that would affect exporting
            valid = re.match('^[\ \w-]+$', new_name) is not None
            if not valid:
                mb = QtWidgets.QMessageBox()
                mb.setIcon(QtWidgets.QMessageBox.Warning)
                mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
                mb.setWindowTitle(_('Warning - invalid characters'))
                mb.setText(_("In the jornal name use only: a-z, A-z 0-9 - space"))
                mb.exec_()
                update = False
            if update:
                # update source list and database
                cur = self.app.conn.cursor()
                cur.execute("update journal set name=? where name=?",
                    (new_name, self.journals[x]['name']))
                self.app.conn.commit()
                self.journals[x]['name'] = new_name
                self.parent_textEdit.append(_("Journal name changed: ") + new_name)
            else:  # put the original text in the cell
                self.ui.tableWidget.item(x, y).setText(self.journals[x]['name'])

