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
"""

import datetime
import os
import re
import sys
import logging
import traceback

from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import Qt

from .GUI.ui_case_file_manager import Ui_Dialog_case_file_manager
from .confirm_delete import DialogConfirmDelete
from .helpers import DialogGetStartAndEndMarks, Message
from .view_av import DialogViewAV
from .view_image import DialogViewImage

ID = 0
NAME = 1
FULLTEXT = 2
MEDIAPATH = 3
MEMO = 4
OWNER = 5
DATE = 6
AV_TEXT_ID = 7

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogCaseFileManager(QtWidgets.QDialog):
    """ Dialog to manipulate files for a case.
    Add files to case, add all text or text portions from a text file.
    Remove file from a case. View file.
    """

    app = None
    parent_textEdit = None
    case = None
    allfiles = []
    casefiles = []
    case_text = []
    selected_text_file = None
    header_labels = ["id", "File name", "Assigned"]
    attributes = []

    def __init__(self, app_, parent_text_edit, case):

        self.app = app_
        self.parent_textEdit = parent_text_edit
        self.case = case
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_case_file_manager()
        self.ui.setupUi(self)
        try:
            w = int(self.app.settings['dialogcasefilemanager_w'])
            h = int(self.app.settings['dialogcasefilemanager_h'])
            if h > 50 and w > 50:
                self.resize(w, h)
        except KeyError:
            pass
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt '
        font += f'"{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        font2 = f'font: {self.app.settings["treefontsize"]}pt '
        font2 += f'"{self.app.settings["font"]}";'
        self.ui.tableWidget.setStyleSheet(font2)
        self.ui.tableWidget.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.ui.tableWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.tableWidget.customContextMenuRequested.connect(self.table_menu)
        self.ui.tableWidget.doubleClicked.connect(self.double_clicked_to_view)
        self.ui.tableWidget.selectionModel().selectionChanged.connect(self.row_selection_changed)

        self.ui.label_case.setText(_("Case: ") + self.case['name'])
        self.ui.pushButton_auto_assign.clicked.connect(self.automark)
        self.ui.pushButton_add_files.clicked.connect(self.add_files_to_case)
        self.ui.pushButton_remove.clicked.connect(self.remove_files_from_case)
        self.ui.textBrowser.setText("")
        self.ui.textBrowser.setAutoFillBackground(True)
        self.ui.textBrowser.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.textBrowser.customContextMenuRequested.connect(self.text_browser_menu)
        self.ui.textBrowser.setOpenLinks(False)
        self.ui.checkBox_hide.stateChanged.connect(self.show_or_hide_rows)
        try:
            s0 = int(self.app.settings['dialogcasefilemanager_splitter0'])
            s1 = int(self.app.settings['dialogcasefilemanager_splitter1'])
            if s0 > 10 and s1 > 10:
                self.ui.splitter.setSizes([s0, s1])
        except KeyError:
            pass
        self.get_files()
        self.get_attributes()
        self.fill_table()

    def get_attributes(self):

        self.header_labels = ["id", "File name", "Assigned"]
        cur = self.app.conn.cursor()
        sql = "select name from attribute_type where caseOrFile='file'"
        cur.execute(sql)
        result = cur.fetchall()
        self.attribute_names = []
        for n in result:
            self.header_labels.append(n[0])
            self.attribute_names.append({'name': n[0]})
        sql = "select attribute.name, value, id from attribute join attribute_type on \
                attribute_type.name=attribute.name where attribute_type.caseOrFile='file'"
        cur.execute(sql)
        result = cur.fetchall()
        self.attributes = []
        for row in result:
            self.attributes.append(row)

    def closeEvent(self, event):
        """ Save dialog and splitter dimensions. """

        self.app.settings['dialogcasefilemanager_w'] = self.size().width()
        self.app.settings['dialogcasefilemanager_h'] = self.size().height()
        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogcasefilemanager_splitter0'] = sizes[0]
        self.app.settings['dialogcasefilemanager_splitter1'] = sizes[1]

    def get_files(self):
        """ Get files for this case. """

        cur = self.app.conn.cursor()
        sql = "select distinct case_text.fid, source.name from case_text join source on case_text.fid=source.id where "
        sql += "caseid=? order by lower(source.name) asc"
        cur.execute(sql, [self.case['caseid'], ])
        self.casefiles = cur.fetchall()
        sql = "select id, name, fulltext, mediapath, memo, owner, date, av_text_id from  source order by source.name asc"
        cur.execute(sql)
        self.allfiles = cur.fetchall()
        msg = _("Files linked: ") + f"{len(self.casefiles)} / {len(self.allfiles)}"
        self.ui.label_files_linked.setText(msg)

    def table_menu(self, position):
        """ Context menu to add and remove files to case. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_add = menu.addAction(_("Add files to case"))
        action_remove = menu.addAction(_("Remove files from case"))
        action = menu.exec(self.ui.tableWidget.mapToGlobal(position))
        if action == action_add:
            self.add_files_to_case()
        if action == action_remove:
            self.remove_files_from_case()

    def add_files_to_case(self):
        """ When select file button is pressed a dialog of filenames is presented to the user.
        The entire text of the selected files is then added to the selected case.
        """

        index_list = self.ui.tableWidget.selectionModel().selectedIndexes()
        rows = []
        for i in index_list:
            rows.append(i.row())
        rows = list(set(rows))  # duplicate rows due to multiple columns
        if len(rows) == 0:
            return
        selected_files = []
        for r in rows:
            selected_files.append(self.allfiles[r])
        msg = ""
        for file_ in selected_files:
            msg += self.add_file_to_case(file_)
        # Update messages and table widget
        self.get_files()
        self.show_or_hide_rows()
        Message(self.app, _("File added to case"), msg, "information").exec()
        self.parent_textEdit.append(msg)
        self.app.delete_backup = False

    def add_file_to_case(self, file_):
        """ The entire text of the selected file is added to the selected case.
        Also, a non-text file is linked to the case here. The text positions will be 0 and 0.
        param:
            file_: tuple of id, name,fulltext, mediapath, memo, owner, date
        return:
            msg: string message for link process or error
        """

        cur = self.app.conn.cursor()
        text_len = 0
        if file_[2] is not None:
            text_len = len(file_[2]) - 1
        link = {'caseid': self.case['caseid'], 'fid': file_[0], 'pos0': 0,
                'pos1': text_len, 'owner': self.app.settings['codername'],
                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'memo': ""}

        # Check for an existing duplicated linked file first
        cur.execute("select * from case_text where caseid = ? and fid=? and pos0=? and pos1=?",
                    (link['caseid'], link['fid'], link['pos0'], link['pos1']))
        result = cur.fetchall()
        if len(result) > 0:
            msg = _("This file has already been linked to this case ") + f"{file_[1]}\n"
            return msg
        # Even non-text files can be assigned to the case here
        sql = "insert into case_text (caseid, fid, pos0, pos1, owner, date, memo) values(?,?,?,?,?,?,?)"
        cur.execute(sql, (link['caseid'], link['fid'], link['pos0'], link['pos1'],
                          link['owner'], link['date'], link['memo']))
        self.app.conn.commit()
        msg = f'{file_[1]} {_("added to case.")}\n'

        # Update table entry assigned to Yes
        rows = self.ui.tableWidget.rowCount()
        for row in range(0, rows):
            fid = int(self.ui.tableWidget.item(row, 0).text())
            if fid == file_[0]:  # file_[0] is fid
                item = QtWidgets.QTableWidgetItem(_("Yes"))
                item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
                self.ui.tableWidget.setItem(row, 2, item)
        return msg

    def remove_files_from_case(self):
        """ Remove selected files from case. """

        index_list = self.ui.tableWidget.selectionModel().selectedIndexes()
        rows = []
        for i in index_list:
            rows.append(i.row())
        rows = list(set(rows))  # duplicate rows due to multiple columns
        if len(rows) == 0:
            return
        selected_files = []
        remove_msg = ""
        for r in rows:
            selected_files.append(self.allfiles[r])
            remove_msg += "\n" + self.allfiles[r][1]
        del_ui = DialogConfirmDelete(self.app, remove_msg)
        ok = del_ui.exec()
        if not ok:
            return
        cur = self.app.conn.cursor()
        sql = "delete from case_text where caseid=? and fid=?"
        for f in selected_files:
            try:
                cur.execute(sql, [self.case['caseid'], f[0]])
                self.app.conn.commit()
                self.parent_textEdit.append(f"{f[1]} removed from case {self.case['name']}")
            except Exception as e:
                print(e)
                logger.debug(str(e))
        # Update assigned files and table widget
        self.get_files()
        self.fill_table()
        self.app.delete_backup = False

    def show_or_hide_rows(self):
        """ Show or hide table rows if check box hide is checked or not. """

        rows = self.ui.tableWidget.rowCount()
        if self.ui.checkBox_hide.isChecked():
            for r in range(0, rows):
                # Text present so hide
                if len(self.ui.tableWidget.item(r, 2).text()) > 0:
                    self.ui.tableWidget.hideRow(r)
            return
        for r in range(0, rows):
            self.ui.tableWidget.showRow(r)

    def fill_table(self):
        """ Fill list widget with file details. """

        rows = self.ui.tableWidget.rowCount()
        for r in range(0, rows):
            self.ui.tableWidget.removeRow(0)
        self.ui.tableWidget.setColumnCount(len(self.header_labels))
        self.ui.tableWidget.setHorizontalHeaderLabels(self.header_labels)

        for row, f in enumerate(self.allfiles):
            self.ui.tableWidget.insertRow(row)
            item = QtWidgets.QTableWidgetItem(str(f[0]))
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget.setItem(row, 0, item)
            item = QtWidgets.QTableWidgetItem(f[1])
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget.setItem(row, 1, item)
            # Mark Yes if assigned
            assigned = ""
            for i in self.casefiles:
                if f[0] == i[0]:
                    assigned = _("Yes")
            item = QtWidgets.QTableWidgetItem(assigned)
            item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
            self.ui.tableWidget.setItem(row, 2, item)
            for a in self.attributes:
                for col, header in enumerate(self.header_labels):
                    if f[0] == a[2] and a[0] == header:
                        string_value = ''
                        if a[1] is not None:
                            string_value = str(a[1])
                        if header == "Ref_Authors":
                            string_value = string_value.replace(";", "\n")
                        item = QtWidgets.QTableWidgetItem(string_value)
                        if header in ("Ref_Authors", "Ref_Title", "Ref_Type", "Ref_Year"):
                            item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled)
                        self.ui.tableWidget.setItem(row, col, item)

        self.ui.tableWidget.hideColumn(0)
        if self.app.settings['showids']:
            self.ui.tableWidget.showColumn(0)
        self.ui.tableWidget.resizeColumnsToContents()

    def double_clicked_to_view(self):
        """ Double-click on a row allow viewing of that file.
        rows begin at 0  to n.
        param:
            row: signal emitted by doubleclick event """

        # TODO need this method? better in init to go to view_file
        self.view_file()

    def row_selection_changed(self):
        """ Row selection changed.
        If first row is text, show the text in textEdit. """

        index_list = self.ui.tableWidget.selectionModel().selectedIndexes()
        rows = []
        for i in index_list:
            rows.append(i.row())
        rows = list(set(rows))  # duplicate rows due to multiple columns
        if len(rows) == 0:
            return
        self.ui.textBrowser.setText("")
        self.selected_text_file = None
        index = rows[0]
        # A fulltext source is displayed if fulltext is present
        # If the mediapath is None, this represents an A/V transcribed file
        self.ui.label_file.setText(_("Displayed file: ") + self.allfiles[index][NAME])
        if self.allfiles[index][FULLTEXT] != "" and self.allfiles[index][FULLTEXT] is not None:
            self.selected_text_file = self.allfiles[index]
            self.ui.textBrowser.setText(self.allfiles[index][FULLTEXT])
            self.load_case_text()
            self.unlight()
            self.highlight()
            return

    def view_file(self):
        """ Open image or media file to view.
         Check media file link works, as media may have moved.
         Text files are displayed via row_selection_changed. """

        index_list = self.ui.tableWidget.selectionModel().selectedIndexes()
        index = None
        if len(index_list) > 0:
            index = index_list[0].row()
        if index is None:
            return

        # Need the data as a dictionary to view images and audio/video
        dictionary = {'name': self.allfiles[index][NAME], 'mediapath': self.allfiles[index][MEDIAPATH],
                      'owner': self.allfiles[index][OWNER], 'id': self.allfiles[index][0],
                      'date': self.allfiles[index][DATE],
                      'memo': self.allfiles[index][MEMO], 'fulltext': self.allfiles[index][FULLTEXT],
                      'av_text_id': self.allfiles[index][AV_TEXT_ID]}
        # Mediapath will be None for a .transcribed empty text media entry, and 'docs:' for a linked text document
        if self.allfiles[index][MEDIAPATH] is None or self.allfiles[index][MEDIAPATH][0:5] == 'docs:':
            return
        # Added checks to test for media presence
        if self.allfiles[index][MEDIAPATH][:6] in ("/video", "video:"):
            if self.allfiles[index][MEDIAPATH][:6] == "video:":
                abs_path = self.allfiles[index][MEDIAPATH].split(':')[1]
                if not os.path.exists(abs_path):
                    return
            if self.allfiles[index][MEDIAPATH][:6] == "/video":
                abs_path = self.app.project_path + self.allfiles[index][MEDIAPATH]
                if not os.path.exists(abs_path):
                    return
            ui_av = DialogViewAV(self.app, dictionary)
            ui_av.exec()
        if self.allfiles[index][MEDIAPATH][:6] in ("/audio", "audio:"):
            if self.allfiles[index][MEDIAPATH][0:6] == "audio:":
                abs_path = self.allfiles[index][MEDIAPATH].split(':')[1]
                if not os.path.exists(abs_path):
                    return
            if self.allfiles[index][MEDIAPATH][0:6] == "/audio":
                abs_path = self.app.project_path + self.allfiles[index][MEDIAPATH]
                if not os.path.exists(abs_path):
                    return
            ui_av = DialogViewAV(self.app, dictionary)
            ui_av.exec()
        if self.allfiles[index][MEDIAPATH][:7] in ("/images", "images:"):
            if self.allfiles[index][MEDIAPATH][0:7] == "images:":
                abs_path = self.allfiles[index][MEDIAPATH].split(':')[1]
                if not os.path.exists(abs_path):
                    return
            if self.allfiles[index][MEDIAPATH][0:7] == "/images":
                abs_path = self.app.project_path + self.allfiles[index][MEDIAPATH]
                if not os.path.exists(abs_path):
                    return
            # Requires {name, mediapath, owner, id, date, memo, fulltext}
            ui_img = DialogViewImage(self.app, dictionary)
            ui_img.exec()

    def load_case_text(self):
        """ Load case text for selected_text_file.
         Called by: view_file. """

        self.case_text = []
        if self.selected_text_file is None:
            return
        cur = self.app.conn.cursor()
        cur.execute("select caseid, fid, pos0, pos1, owner, date, memo from case_text where fid = ? and caseid = ?",
                    [self.selected_text_file[ID], self.case['caseid']])
        result = cur.fetchall()
        for row in result:
            self.case_text.append({'caseid': row[0], 'fid': row[1], 'pos0': row[2],
                                   'pos1': row[3], 'owner': row[4], 'date': row[5], 'memo': row[6]})

    def text_browser_menu(self, position):
        """ Context menu for textBrowser. Mark, unmark, copy, select all. """

        if self.ui.textBrowser.toPlainText() == "":
            return
        cursor = self.ui.textBrowser.cursorForPosition(position)
        selected_text = self.ui.textBrowser.textCursor().selectedText()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_select_all = None
        action_mark = None
        action_unmark = None
        action_copy = None
        if selected_text == "":
            action_select_all = menu.addAction(_("Select all"))
        if selected_text != "" and not self.is_marked():
            action_mark = menu.addAction(_("Mark"))
        if selected_text != "":
            action_copy = menu.addAction(_("Copy"))
        for item in self.case_text:
            if item['pos0'] <= cursor.position() <= item['pos1']:
                action_unmark = menu.addAction(_("Unmark"))
                break
        action = menu.exec(self.ui.textBrowser.mapToGlobal(position))
        if action is None:
            return
        if action == action_mark:
            self.mark()
        if action == action_unmark:
            self.unmark(position)
        if action == action_copy:
            self.copy_selected_text_to_clipboard()
        if action == action_select_all:
            self.ui.textBrowser.selectAll()

    def is_marked(self):
        """ Check current text selection and return False if not marked and True if marked. """

        pos0 = self.ui.textBrowser.textCursor().selectionStart()
        pos1 = self.ui.textBrowser.textCursor().selectionEnd()
        for c in self.case_text:
            if c['pos0'] <= pos0 <= c['pos1']:
                return True
            if c['pos0'] <= pos1 <= c['pos1']:
                return True
        return False

    def copy_selected_text_to_clipboard(self):

        selected_text = self.ui.textBrowser.textCursor().selectedText()
        cb = QtWidgets.QApplication.clipboard()
        cb.setText(selected_text)

    def unlight(self):
        """ Remove all text highlighting from current file. """

        if self.selected_text_file is None:
            return
        if self.selected_text_file[FULLTEXT] is None:
            return
        cursor = self.ui.textBrowser.textCursor()
        try:
            cursor.setPosition(0, QtGui.QTextCursor.MoveMode.MoveAnchor)
            cursor.setPosition(len(self.selected_text_file[FULLTEXT]) - 1, QtGui.QTextCursor.MoveMode.KeepAnchor)
            cursor.setCharFormat(QtGui.QTextCharFormat())
        except Exception as e:
            logger.debug(f"{e}\n Unlight, text length: {len(self.ui.textBrowser.toPlainText())}")

    def highlight(self):
        """ Apply text highlighting to current file.
        Highlight text of selected case with red underlining.
        #format_.setForeground(QtGui.QColor("#990000")) """

        if self.selected_text_file is None:
            return
        if self.selected_text_file[FULLTEXT] is None:
            return
        format_ = QtGui.QTextCharFormat()
        cursor = self.ui.textBrowser.textCursor()
        for item in self.case_text:
            try:
                cursor.setPosition(int(item['pos0']), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(int(item['pos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
                format_.setFontUnderline(True)
                format_.setUnderlineColor(QtCore.Qt.GlobalColor.red)
                cursor.setCharFormat(format_)
            except Exception as err:
                msg = f"highlight, text length {len(self.ui.textBrowser.toPlainText())}"
                msg += f"\npos0: {item['pos0']}, pos1: {item['pos1']}\n{err}"
                logger.debug(msg)

    def mark(self):
        """ Mark selected text in file with this case. """

        if self.selected_text_file is None:
            return
        # selectedText = self.textBrowser.textCursor().selectedText()
        pos0 = self.ui.textBrowser.textCursor().selectionStart()
        pos1 = self.ui.textBrowser.textCursor().selectionEnd()
        if pos0 == pos1:
            return
        # Add new item to case_text list and database and update GUI
        item = {'caseid': self.case['caseid'],
                'fid': self.selected_text_file[ID],
                'pos0': pos0, 'pos1': pos1,
                'owner': self.app.settings['codername'],
                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                'memo': ""}
        self.case_text.append(item)
        self.highlight()

        cur = self.app.conn.cursor()
        # Check for an existing duplicated linkage first
        cur.execute("select * from case_text where caseid=? and fid=? and pos0<=? and pos1>=?",
                    (item['caseid'], item['fid'], item['pos0'], item['pos1']))
        result = cur.fetchall()
        if len(result) > 0:
            Message(self.app, _("Already Linked"),
                    _("This segment has already been linked to this case"), "warning").exec()
            return
        cur.execute("insert into case_text (caseid,fid, pos0, pos1, owner, date, memo) values(?,?,?,?,?,?,?)",
                    (
                    item['caseid'], item['fid'], item['pos0'], item['pos1'], item['owner'], item['date'], item['memo']))
        self.app.conn.commit()
        # File may not be assigned in the table widget as Yes
        self.get_files()
        self.fill_table()
        self.app.delete_backup = False

    def unmark(self, position):
        """ Remove case marking from selected text in selected file. """

        if self.selected_text_file is None:
            return
        if len(self.case_text) == 0:
            return
        cursor = self.ui.textBrowser.cursorForPosition(position)
        self.ui.textBrowser.setTextCursor(cursor)

        location = self.ui.textBrowser.textCursor().selectionStart()
        unmarked = None
        for item in self.case_text:
            if item['pos0'] <= location <= item['pos1']:
                unmarked = item
        if unmarked is None:
            return

        # Delete from database, remove from case_text and update gui
        cur = self.app.conn.cursor()
        cur.execute("delete from case_text where fid=? and caseid=? and pos0=? and pos1=?",
                    (unmarked['fid'], unmarked['caseid'], unmarked['pos0'], unmarked['pos1']))
        self.app.conn.commit()
        if unmarked in self.case_text:
            self.case_text.remove(unmarked)
        self.unlight()
        self.highlight()
        # The file may be assigned Yes in the table widget but should be empty
        self.get_files()
        self.fill_table()
        self.app.delete_backup = False

    def automark(self):
        """ Automark text in one or more files with selected case.
        Each selected_file is a tuple of id, name,fulltext, mediapath, memo, owner, date
        """

        index_list = self.ui.tableWidget.selectionModel().selectedIndexes()
        rows = []
        for i in index_list:
            rows.append(i.row())
        rows = list(set(rows))  # duplicate rows due to multiple columns
        if len(rows) == 0:
            return
        selected_files = []
        filenames = ""
        for r in rows:
            if self.allfiles[r][2] is not None and self.allfiles[r][2] != "":
                selected_files.append(self.allfiles[r])
                filenames += self.allfiles[r][1] + " "
        ui_se = DialogGetStartAndEndMarks(self.case['name'], filenames)
        ok = ui_se.exec()
        if not ok:
            return
        start_mark = ui_se.get_start_mark()
        end_mark = ui_se.get_end_mark()
        if start_mark == "" or end_mark == "":
            Message(self.app, _("Warning"), _('Cannot have blank text marks'), "warning").exec()
            return
        msg = _("Auto assign text to case: ") + self.case['name']
        msg += _("\nUsing ") + start_mark + _(" and ") + end_mark + _("\nIn files:\n")
        msg += filenames
        warning_msg = ""
        already_assigned = ""
        entries = 0
        cur = self.app.conn.cursor()
        for f in selected_files:
            cur.execute("select name, id, fulltext, memo, owner, date from source where id=?",
                        [f[0]])
            currentfile = cur.fetchone()
            text = currentfile[2]
            text_starts = [match.start() for match in re.finditer(re.escape(start_mark), text)]
            text_ends = [match.start() for match in re.finditer(re.escape(end_mark), text)]
            # Add new code linkage items to database
            already_assigned = ""
            for start_pos in text_starts:
                text_end_iterator = 0
                try:
                    while start_pos >= text_ends[text_end_iterator]:
                        text_end_iterator += 1
                except IndexError:
                    text_end_iterator = -1
                    warning_msg += _("Auto assign. Could not find an end mark: ") + f"{f[1]}  {end_mark}\n"
                if text_end_iterator >= 0:
                    pos1 = text_ends[text_end_iterator]
                    item = {'caseid': self.case['caseid'], 'fid': f[0],
                            'pos0': start_pos, 'pos1': pos1,
                            'owner': self.app.settings['codername'],
                            'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'memo': ""}
                    # Check if already assigned to case_text
                    sql = "select id from case_text where caseid=? and fid=? and pos0=? and pos1=?"
                    cur.execute(sql, [item['caseid'], item['fid'], item['pos0'], item['pos1']])
                    res = cur.fetchone()
                    if res is None:
                        sql = "insert into case_text (caseid,fid,pos0,pos1,owner,date,memo) values(?,?,?,?,?,?,?)"
                        cur.execute(sql, (item['caseid'], item['fid'], item['pos0'], item['pos1'],
                                          item['owner'], item['date'], item['memo']))
                        entries += 1
                        self.app.conn.commit()
                    else:
                        already_assigned = _("\nAlready assigned.")
        # Update messages and table widget
        self.get_files()
        self.fill_table()
        # Text file is loaded in browser then update the highlights
        self.load_case_text()
        self.highlight()
        msg += f"\n{entries}" + _(" sections found.")
        Message(self.app, _("File added to case"), f"{msg}\n{warning_msg}\n{already_assigned}").exec()
        self.parent_textEdit.append(msg)
        self.parent_textEdit.append(warning_msg)
        self.app.delete_backup = False
