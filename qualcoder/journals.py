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

from PyQt5 import QtCore, QtWidgets, QtGui
import datetime
import os
import platform
import re
import sys
import logging
import traceback

from add_item_name import DialogAddItemName
from confirm_delete import DialogConfirmDelete
from GUI.base64_helper import *
from GUI.ui_dialog_journals import Ui_Dialog_journals
from helpers import Message

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

NAME_COLUMN = 0
DATE_COLUMN = 1
OWNER_COLUMN = 2
JID_COLUMN = 3


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
    """  View, create, export, rename and delete journals. """

    journals = []
    jid = None  # journal database jid
    app = None
    parent_textEdit = None
    textDialog = None
    # variables for searching through journal(s)
    search_indices = []
    search_index = 0

    def __init__(self, app, parent_textEdit, parent=None):

        super(DialogJournals, self).__init__(parent)  # overrride accept method
        sys.excepthook = exception_handler
        self.app = app
        self.parent_textEdit = parent_textEdit
        self.journals = []
        self.current_jid = None
        self.search_indices = []
        self.search_index = 0
        cur = self.app.conn.cursor()
        cur.execute("select name, date, jentry, owner, jid from journal")
        result = cur.fetchall()
        for row in result:
            self.journals.append({'name':row[0], 'date':row[1], 'jentry':row[2], 'owner':row[3], 'jid': row[4]})
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_journals()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.ui.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        try:
            s0 = int(self.app.settings['dialogjournals_splitter0'])
            s1 = int(self.app.settings['dialogjournals_splitter1'])
            if s0 > 10 and s1 > 10:
                self.ui.splitter.setSizes([s0, s1])
        except:
            pass
        self.fill_table()
        self.ui.tableWidget.itemChanged.connect(self.cell_modified)
        self.ui.tableWidget.itemSelectionChanged.connect(self.table_selection_changed)

        self.ui.textEdit.textChanged.connect(self.text_changed)
        #icon = QtGui.QIcon(QtGui.QPixmap('GUI/pencil_icon.png'))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(pencil_icon), "png")
        self.ui.pushButton_create.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_create.clicked.connect(self.create)
        #icon = QtGui.QIcon(QtGui.QPixmap('GUI/doc_export_icon.png'))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(doc_export_icon), "png")
        self.ui.pushButton_export.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_export.clicked.connect(self.export)
        #icon = QtGui.QIcon(QtGui.QPixmap('GUI/delete_icon.png'))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(delete_icon), "png")
        self.ui.pushButton_delete.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_delete.clicked.connect(self.delete)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(doc_export_csv_icon), "png")
        self.ui.pushButton_export_all.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_export_all.clicked.connect(self.export_all_journals_as_one_file)

        # Search text in journals
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(question_icon), "png")
        self.ui.label_search_regex.setPixmap(QtGui.QPixmap(pm))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(clipboard_copy_icon), "png")
        self.ui.label_search_all_journals.setPixmap(QtGui.QPixmap(pm))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(playback_back_icon), "png")
        self.ui.pushButton_previous.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_previous.setEnabled(False)
        self.ui.pushButton_previous.pressed.connect(self.move_to_previous_search_text)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(playback_play_icon), "png")
        self.ui.pushButton_next.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_next.setEnabled(False)
        self.ui.pushButton_next.pressed.connect(self.move_to_next_search_text)
        self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
        #self.ui.lineEdit_search.setEnabled(False)
        self.ui.checkBox_search_all_journals.stateChanged.connect(self.search_for_text)
        #self.ui.checkBox_search_all_journals.setEnabled(False)

    def fill_table(self):
        """ Fill journals table """

        self.ui.tableWidget.blockSignals(True)
        rows = self.ui.tableWidget.rowCount()
        for r in range(0, rows):
            self.ui.tableWidget.removeRow(0)
        for row, details in enumerate(self.journals):
            print(row, details)
            self.ui.tableWidget.insertRow(row)
            self.ui.tableWidget.setItem(row, NAME_COLUMN, QtWidgets.QTableWidgetItem(details['name']))
            item = QtWidgets.QTableWidgetItem(details['date'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, DATE_COLUMN, item)
            item = QtWidgets.QTableWidgetItem(details['owner'])
            item.setFlags(item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, OWNER_COLUMN, item)
            item = QtWidgets.QTableWidgetItem(str(details['jid']))
            item.setFlags(item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, JID_COLUMN, item)

        self.ui.tableWidget.verticalHeader().setVisible(False)
        if self.app.settings['showids'] == 'True':
            self.ui.tableWidget.showColumn(JID_COLUMN)
        else:
            self.ui.tableWidget.hideColumn(JID_COLUMN)
        self.ui.tableWidget.resizeColumnsToContents()
        self.ui.tableWidget.resizeRowsToContents()
        self.jid = None
        self.ui.tableWidget.clearSelection()
        self.ui.tableWidget.blockSignals(False)
        self.ui.textEdit.setText("")
        self.ui.label_jcount.setText(_("Journals: ") + str(len(self.journals)))

    def export_all_journals_as_one_file(self):
        """ Export a collation of all journals as one text file. """

        text = ""
        for j in self.journals:
            text += _("Journal: ") + j['name'] + "\n"
            text += j['jentry'] + "\n========\n\n"

        options = QtWidgets.QFileDialog.DontResolveSymlinks | QtWidgets.QFileDialog.ShowDirsOnly
        directory = QtWidgets.QFileDialog.getExistingDirectory(None,
             _("Select directory to save file"), self.app.last_export_directory, options)
        if directory == "":
            return
        d = str(datetime.datetime.now().astimezone().strftime("_%Y_%m_%dT%H_%M"))
        filename = directory + "/" + "Collated_journals" + d + ".txt"
        '''if os.path.exists(filename):
            pass'''
        ''' https://stackoverflow.com/questions/39422573/python-writing-weird-unicode-to-csv
        Using a byte order mark so that other software recognises UTF-8
        '''
        f = open(filename, 'w', encoding='utf-8-sig')
        f.write(text)
        f.close()
        msg = _("Collated journals exported as text file to: ") + filename
        self.parent_textEdit.append(msg)
        Message(self.app, _("Journals exported"), msg).exec_()

    def view(self):
        """ View and edit journal contents in the textEdit """

        row = self.ui.tableWidget.currentRow()
        if row == -1:
            self.jid = None
            self.ui.textEdit.setPlainText("")
            return
        self.jid = int(self.ui.tableWidget.item(row, JID_COLUMN).text())
        self.ui.textEdit.blockSignals(True)
        self.ui.textEdit.setPlainText(self.journals[row]['jentry'])
        self.ui.textEdit.blockSignals(False)

    def text_changed(self):
        """ Journals list entry and database is updated from changes to text edit.
        The signal is switched off when a different journal is loaded.
        """

        if self.jid is None:
            return
        self.journals[self.ui.tableWidget.currentRow()]['jentry'] = self.ui.textEdit.toPlainText()
        # Update database as text is edited
        cur = self.app.conn.cursor()
        cur.execute("update journal set jentry=? where jid=?", (self.journals[self.ui.tableWidget.currentRow()]['jentry'], self.jid))
        self.app.conn.commit()
        self.app.delete_backup = False

    def closeEvent(self, event):
        """ Save splitter dimensions. """

        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogjournals_splitter0'] = sizes[0]
        self.app.settings['dialogjournals_splitter1'] = sizes[1]

    def create(self):
        """ Create a new journal by entering text into the dialog. """

        self.jid = None
        self.ui.textEdit.setPlainText("")
        self.ui.tableWidget.clearSelection()

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
        jid = cur.fetchone()[0]
        journal['jid'] = jid
        self.parent_textEdit.append(_("Journal created: ") + journal['name'])
        self.journals.append(journal)
        self.fill_table()
        newest = len(self.journals) - 1
        if newest < 0:
            return
        self.ui.tableWidget.setCurrentCell(newest, 0)
        self.jid = jid
        self.ui.textEdit.setFocus()

    def export(self):
        """ Export journal to a plain text file, filename will have .txt ending. """

        row = self.ui.tableWidget.currentRow()
        if row == -1:
            return
        filename = self.journals[row]['name']
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
            data = self.journals[row]['jentry']
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

        row = self.ui.tableWidget.currentRow()
        if row == -1:
            return
        journalname = self.journals[row]['name']
        ui = DialogConfirmDelete(self.app, self.journals[row]['name'])
        ok = ui.exec_()
        if ok:
            cur = self.app.conn.cursor()
            cur.execute("delete from journal where name = ?", [journalname])
            cur = self.app.conn.commit()
            for item in self.journals:
                if item['name'] == journalname:
                    self.journals.remove(item)
            self.fill_table()
            self.parent_textEdit.append(_("Journal deleted: ") + journalname)

    def table_selection_changed(self):
        """ Update the journal text for the current selection. """

        row = self.ui.tableWidget.currentRow()
        self.ui.label_jname.setText(_("Journal: ") + self.journals[row]['name'])
        self.jid = int(self.ui.tableWidget.item(row, JID_COLUMN).text())
        self.view()

    def cell_modified(self):
        """ If the journal name has been changed in the table widget update the database
        """

        row = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        self.jid = int(self.ui.tableWidget.item(row, JID_COLUMN).text())
        if y == self.NAME_COLUMN:
            new_name = self.ui.tableWidget.item(row, y).text().strip()
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
                mb.setText(_("In the journal name use only: a-z, A-z 0-9 - space"))
                mb.exec_()
                update = False
            if update:
                # update journals list and database
                cur = self.app.conn.cursor()
                cur.execute("update journal set name=? where name=?",
                    (new_name, self.journals[row]['name']))
                self.app.conn.commit()
                self.parent_textEdit.append(_("Journal name changed from: ") + self.journals[row]['name'] + " to: " + new_name)
                self.journals[row]['name'] = new_name
                self.ui.label_jname.setText(_("Journal: ") + self.journals[row]['name'])
            else:  # Put the original text in the cell
                self.ui.tableWidget.item(row, y).setText(self.journals[row]['name'])

    # Functions to search though the journal(s) text
    def search_for_text(self):
        """ On text changed in lineEdit_search, find indices of matching text.
        Only where text is three or more characters long.
        Resets current search_index.
        If all files is checked then searches for all matching text across all text files
        and displays the file text and current position to user.
        If case sensitive is checked then text searched is matched for case sensitivity.
        """

        if self.jid is None and not(self.ui.checkBox_search_all_journals.isChecked()):
            return
        if self.search_indices == []:
            self.ui.pushButton_next.setEnabled(False)
            self.ui.pushButton_previous.setEnabled(False)
        self.search_indices = []
        self.search_index = -1
        search_term = self.ui.lineEdit_search.text()
        self.ui.label_search_totals.setText("0 / 0")
        if len(search_term) < 3:
            return
        pattern = None
        flags = 0
        '''if not self.ui.checkBox_search_case.isChecked():
            flags |= re.IGNORECASE'''
        try:
            pattern = re.compile(search_term, flags)
        except:
            logger.warning('Bad escape')
        if pattern is None:
            print("no pattern")
            return
        self.search_indices = []
        if self.ui.checkBox_search_all_journals.isChecked():
            """ Search for this text across all journals. Show each journal in textEdit
            """
            for jdata in self.app.get_journal_texts():
                try:
                    text = jdata['fulltext']
                    for match in pattern.finditer(text):
                        self.search_indices.append((jdata, match.start(), len(match.group(0))))
                except:
                    logger.exception('Failed searching text %s for %s',jdata['name'], search_term)
        else:  # Current journal only
            row = self.ui.tableWidget.currentRow()
            try:
                print(4, "match pattern")
                for match in pattern.finditer(self.journals[row]['jentry']):
                    # Get result as first dictionary item
                    j_name = self.app.get_journal_texts([self.jid, ])[0]
                    self.search_indices.append((j_name, match.start(), len(match.group(0))))
            except:
                logger.exception('Failed searching current journal for %s', search_term)
        print(3, self.search_indices, self.search_index)
        if len(self.search_indices) > 0:
            self.ui.pushButton_next.setEnabled(True)
            self.ui.pushButton_previous.setEnabled(True)
        self.ui.label_search_totals.setText("0 / " + str(len(self.search_indices)))

    def move_to_previous_search_text(self):
        """ Push button pressed to move to previous search text position. """

        if self.current_jid is None or self.search_indices== []:
            return
        self.search_index -= 1
        if self.search_index < 0:
            self.search_index = len(self.search_indices) - 1
        cursor = self.ui.textEdit.textCursor()
        prev_result = self.search_indices[self.search_index]

        # prev_result is a tuple containing a dictonary of {name, id, fullltext, memo, owner, date} and char position and search string length
        if self.file_ is None or self.file_['id'] != prev_result[0]['id']:
            self.load_file(prev_result[0])
        cursor.setPosition(prev_result[1])
        cursor.setPosition(cursor.position() + prev_result[2], QtGui.QTextCursor.KeepAnchor)
        self.ui.textEdit.setTextCursor(cursor)
        self.ui.label_search_totals.setText(str(self.search_index + 1) + " / " + str(len(self.search_indices)))

    def move_to_next_search_text(self):
        """ Push button pressed to move to next search text position. """

        if self.current_jid is None or self.search_indices == []:
            return
        self.search_index += 1
        if self.search_index == len(self.search_indices):
            self.search_index = 0
        cursor = self.ui.textEdit.textCursor()
        next_result = self.search_indices[self.search_index]
        # next_result is a tuple containing a dictonary of {name, id, fullltext, memo, owner, date} and char position and search string length
        if self.file_ is None or self.file_['id'] != next_result[0]['id']:
            self.load_file(next_result[0])
        cursor.setPosition(next_result[1])
        cursor.setPosition(cursor.position() + next_result[2], QtGui.QTextCursor.KeepAnchor)
        self.ui.textEdit.setTextCursor(cursor)
        self.ui.label_search_totals.setText(str(self.search_index + 1) + " / " + str(len(self.search_indices)))


