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

from copy import deepcopy
import datetime
import logging
import os
from random import randint
import re
import sys
import traceback

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.Qt import QHelpEvent
from PyQt5.QtCore import Qt  # for context menu
from PyQt5.QtGui import QBrush

from add_item_name import DialogAddItemName
from color_selector import DialogColorSelect
from color_selector import colors
from confirm_delete import DialogConfirmDelete
from information import DialogInformation
from GUI.ui_dialog_code_text import Ui_Dialog_code_text
from memo import DialogMemo
from qtmodels import DictListModel, ListObjectModel
from select_file import DialogSelectFile

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception:") + "\n" + text)
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), text)

def msecs_to_mins_and_secs(msecs):
    """ Convert milliseconds to minutes and seconds.
    msecs is an integer. Minutes and seconds output is a string.
    called by: coded_media_dialog   """

    secs = int(msecs / 1000)
    mins = int(secs / 60)
    remainder_secs = str(secs - mins * 60)
    if len(remainder_secs) == 1:
        remainder_secs = "0" + remainder_secs
    return str(mins) + "." + remainder_secs


class DialogCodeText(QtWidgets.QWidget):
    ''' Code management. Add, delete codes. Mark and unmark text.
    Add memos and colors to codes.
    Trialled using setHtml for documents, but on marking text Html formatting was replaced, also
    on unmarking text, the unmark was not immediately cleared (needed to reload the file) '''

    NAME_COLUMN = 0
    ID_COLUMN = 1
    MEMO_COLUMN = 2
    app = None
    dialog_list = None
    parent_textEdit = None
    codes = []
    categories = []
    filenames = []
    filename = None  # contains filename and file id returned from SelectFile
    sourceText = None
    code_text = []
    annotations = []
    search_indices = []
    search_index = 0
    eventFilter = None

    def __init__(self, app, parent_textEdit, dialog_list):

        super(DialogCodeText, self).__init__()
        self.app = app
        self.dialog_list = dialog_list
        sys.excepthook = exception_handler
        self.parent_textEdit = parent_textEdit
        self.codes = []
        self.categories = []
        self.filenames = self.app.get_text_filenames()
        self.annotations = self.app.get_annotations()
        self.search_indices = []
        self.search_index = 0
        self.get_codes_and_categories()
        self.ui = Ui_Dialog_code_text()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        font = 'font: ' + str(self.app.settings['treefontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.ui.treeWidget.setStyleSheet(font)
        self.ui.label_coder.setText("Coder: " + self.app.settings['codername'])
        self.ui.textEdit.setPlainText("")
        self.ui.textEdit.setAutoFillBackground(True)
        self.ui.textEdit.setToolTip("")
        self.ui.textEdit.setMouseTracking(True)
        self.ui.textEdit.setReadOnly(True)
        self.eventFilterTT = ToolTip_EventFilter()
        self.ui.textEdit.installEventFilter(self.eventFilterTT)
        self.ui.textEdit.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.textEdit.customContextMenuRequested.connect(self.textEdit_menu)
        self.ui.textEdit.cursorPositionChanged.connect(self.coded_in_text)
        self.ui.pushButton_view_file.clicked.connect(self.view_file_dialog)
        self.ui.pushButton_auto_code.clicked.connect(self.auto_code)
        self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
        self.ui.lineEdit_search.setEnabled(False)
        self.ui.checkBox_search_all_files.stateChanged.connect(self.search_for_text)
        self.ui.checkBox_search_all_files.setEnabled(False)
        self.ui.checkBox_search_case.stateChanged.connect(self.search_for_text)
        self.ui.checkBox_search_case.setEnabled(False)
        self.ui.pushButton_previous.setEnabled(False)
        self.ui.pushButton_next.setEnabled(False)
        self.ui.pushButton_next.pressed.connect(self.move_to_next_search_text)
        self.ui.pushButton_previous.pressed.connect(self.move_to_previous_search_text)
        self.ui.comboBox_codes_in_text.activated.connect(self.combo_code_activated)
        self.ui.comboBox_codes_in_text.setEnabled(False)
        self.ui.label_codes_count.setEnabled(False)
        self.ui.label_codes_clicked_in_text.setEnabled(False)
        self.ui.treeWidget.setDragEnabled(True)
        self.ui.treeWidget.setAcceptDrops(True)
        self.ui.treeWidget.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.ui.treeWidget.viewport().installEventFilter(self)
        self.ui.treeWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.treeWidget.customContextMenuRequested.connect(self.tree_menu)
        self.ui.treeWidget.itemClicked.connect(self.fill_code_label)
        self.ui.splitter.setSizes([150, 400])
        #self.ui.leftsplitter.setSizes([100, 0])
        self.fill_tree()
        self.setAttribute(Qt.WA_QuitOnClose, False)

    def fill_code_label(self):
        """ Fill code label with currently selected item's code name and colour.
         Also, if text is highlighted, assign the text to this code. """

        current = self.ui.treeWidget.currentItem()
        if current.text(1)[0:3] == 'cat':
            self.ui.label_code.setText(_("NO CODE SELECTED"))
            self.ui.label_code.setStyleSheet("QLabel { background-color : None; }");
            return
        self.ui.label_code.setText("Code: " + current.text(0))
        # update background colour of label and store current code for underlining
        code_for_underlining = None
        for c in self.codes:
            if current.text(0) == c['name']:
                palette = self.ui.label_code.palette()
                code_color = QtGui.QColor(c['color'])
                palette.setColor(QtGui.QPalette.Window, code_color)
                self.ui.label_code.setPalette(palette)
                self.ui.label_code.setAutoFillBackground(True)
                code_for_underlining = c
                break
        selected_text = self.ui.textEdit.textCursor().selectedText()
        if len(selected_text) > 0:
            self.mark()
        self.underline_text_of_this_code(code_for_underlining)

    def underline_text_of_this_code(self, code_for_underlining):
        """ User interface, highlight coded text selections for the currently selected code.
        Qt underline options: # NoUnderline, SingleUnderline, DashUnderline, DotLine, DashDotLine, WaveUnderline
        param:
            code_for_underlining: dictionary of the code to be underlined """

        # Remove all underlining
        selstart = 0
        selend = len(self.ui.textEdit.toPlainText())
        format = QtGui.QTextCharFormat()
        format.setUnderlineStyle(QtGui.QTextCharFormat.NoUnderline)
        cursor = self.ui.textEdit.textCursor()
        cursor.setPosition(selstart)
        cursor.setPosition(selend, QtGui.QTextCursor.KeepAnchor)
        cursor.mergeCharFormat(format)
        # Apply underlining in for selected coded text
        format = QtGui.QTextCharFormat()
        format.setUnderlineStyle(QtGui.QTextCharFormat.DashUnderline)
        format.setUnderlineStyle(QtGui.QTextCharFormat.DashUnderline)
        cursor = self.ui.textEdit.textCursor()
        for coded_text in self.code_text:
            if coded_text['cid'] == code_for_underlining['cid']:
                cursor.setPosition(int(coded_text['pos0']), QtGui.QTextCursor.MoveAnchor)
                cursor.setPosition(int(coded_text['pos1']), QtGui.QTextCursor.KeepAnchor)
                cursor.mergeCharFormat(format)

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes.
        The Count column counts the number of times that code has been used by selected coder in selected file. """

        cats = deepcopy(self.categories)
        codes = deepcopy(self.codes)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(4)
        self.ui.treeWidget.setHeaderLabels([_("Name"), _("Id"), _("Memo"), _("Count")])
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
            #try:
            cats.remove(item)
            #except Exception as e:
            #    logger.debug(e, item)

        ''' Add child categories. look at each unmatched category, iterate through tree
         to add as child, then remove matched categories from the list '''
        count = 0
        while len(cats) > 0 or count < 10000:
            remove_list = []
            #logger.debug("Cats: " + str(cats))
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
                item = it.value()
                while item:  # while there is an item in the list
                    if item.text(1) == 'catid:' + str(c['supercatid']):
                        memo = ""
                        if c['memo'] != "":
                            memo = _("Memo")
                        child = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                        child.setToolTip(2, c['memo'])
                        item.addChild(child)
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
                memo = ""
                if c['memo'] != "":
                    memo = _("Memo")
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                top_item.setToolTip(2, c['memo'])
                top_item.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.SolidPattern))
                top_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)

        # add codes as children
        for c in codes:
            it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
            item = it.value()
            while item:
                if item.text(1) == 'catid:' + str(c['catid']):
                    memo = ""
                    if c['memo'] != "":
                        memo = _("Memo")
                    child = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                    child.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.SolidPattern))
                    child.setToolTip(2, c['memo'])
                    child.setFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
                    item.addChild(child)
                    c['catid'] = -1  # Make unmatchable
                it += 1
                item = it.value()
        self.ui.treeWidget.expandAll()
        self.fill_code_counts_in_tree()

    def fill_code_counts_in_tree(self):
        """ Count instances of each code for current coder and in the selected file. """

        if self.filename is None:
            return
        cur = self.app.conn.cursor()
        sql = "select count(cid) from code_text where cid=? and fid=? and owner=?"
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        while item:
            #print(item.text(0), item.text(1), item.text(2), item.text(3))
            if item.text(1)[0:4] == "cid:":
                cid = str(item.text(1)[4:])
                cur.execute(sql, [cid, self.filename['id'], self.app.settings['codername']])
                result = cur.fetchone()
                if result[0] > 0:
                    item.setText(3, str(result[0]))
                else:
                    item.setText(3, "")
            it += 1
            item = it.value()

    def get_codes_and_categories(self):
        """ Called from init, delete category/code. """

        self.codes, self.categories = self.app.get_data()
        cur = self.app.conn.cursor()

    def search_for_text(self):
        """ On text changed in lineEdit_search, find indices of matching text.
        Only where text is two or more characters long.
        Resets current search_index.
        If all files is checked then searches for all matching text across all text files
        and displays the file text and current position to user.
        If case sensitive is checked then text searched is matched for case sensitivity.
        """

        if self.filename is None:
            return
        if len(self.search_indices) == 0:
            self.ui.pushButton_next.setEnabled(False)
            self.ui.pushButton_previous.setEnabled(False)
        self.search_indices = []
        self.search_index = -1
        search_term = self.ui.lineEdit_search.text()
        self.ui.label_search_totals.setText("0 / 0")
        if len(search_term) >= 2:
            pattern = None
            flags = 0
            if not self.ui.checkBox_search_case.isChecked():
                flags |= re.IGNORECASE
            '''if self.ui.checkBox_search_escaped.isChecked():
                pattern = re.compile(re.escape(search_term), flags)
            else:
                try:
                    pattern = re.compile(search_term, flags)
                except:
                    logger.warning('Bad escape')'''
            try:
                pattern = re.compile(search_term, flags)
            except:
                logger.warning('Bad escape')

            if pattern is not None:
                self.search_indices = []
                if self.ui.checkBox_search_all_files.isChecked():
                    """ Search for this text across all files. Show each file in textEdit
                    """
                    for filedata in self.app.get_file_texts():
                        try:
                            text = filedata['fulltext']
                            for match in pattern.finditer(text):
                                self.search_indices.append((filedata,match.start(),len(match.group(0))))
                        except:
                            logger.exception('Failed searching text %s for %s',filedata['name'],search_term)
                else:
                    try:
                        if self.sourceText:
                            for match in pattern.finditer(self.sourceText):
                                # Get result as first dictionary item
                                filedata = self.app.get_file_texts([self.filename['id'], ])[0]
                                self.search_indices.append((filedata,match.start(), len(match.group(0))))
                    except:
                        logger.exception('Failed searching current file for %s',search_term)
                if len(self.search_indices) > 0:
                    self.ui.pushButton_next.setEnabled(True)
                    self.ui.pushButton_previous.setEnabled(True)
                self.ui.label_search_totals.setText("0 / " + str(len(self.search_indices)))

    def move_to_previous_search_text(self):
        """ Push button pressed to move to previous search text position. """

        self.search_index -= 1
        if self.search_index == -1:
            self.search_index = len(self.search_indices) - 1
        cur = self.ui.textEdit.textCursor()
        prev_result = self.search_indices[self.search_index]
        # prev_result is a tuple containing a dictonary of {name, id, fullltext, memo, owner, date} and char position and search string length
        if self.filename is None or self.filename['id'] != prev_result[0]['id']:
            self.load_file(prev_result[0])
        cur.setPosition(prev_result[1])
        cur.setPosition(cur.position() + prev_result[2], QtGui.QTextCursor.KeepAnchor)
        self.ui.textEdit.setTextCursor(cur)
        self.ui.label_search_totals.setText(str(self.search_index + 1) + " / " + str(len(self.search_indices)))

    def move_to_next_search_text(self):
        """ Push button pressed to move to next search text position. """

        self.search_index += 1
        if self.search_index == len(self.search_indices):
            self.search_index = 0
        cur = self.ui.textEdit.textCursor()
        next_result = self.search_indices[self.search_index]
        # next_result is a tuple containing a dictonary of {name, id, fullltext, memo, owner, date} and char position and search string length
        if self.filename is None or self.filename['id'] != next_result[0]['id']:
            self.load_file(next_result[0])
        cur.setPosition(next_result[1])
        cur.setPosition(cur.position() + next_result[2], QtGui.QTextCursor.KeepAnchor)
        self.ui.textEdit.setTextCursor(cur)
        self.ui.label_search_totals.setText(str(self.search_index + 1) + " / " + str(len(self.search_indices)))

    def textEdit_menu(self, position):
        """ Context menu for textEdit. Mark, unmark, annotate, copy. """

        cursor = self.ui.textEdit.cursorForPosition(position)
        selectedText = self.ui.textEdit.textCursor().selectedText()
        menu = QtWidgets.QMenu()
        action_unmark = None
        for item in self.code_text:
            if cursor.position() >= item['pos0'] and cursor.position() <= item['pos1']:
                action_unmark = menu.addAction(_("Unmark"))
                break
        if selectedText != "":
            if self.ui.treeWidget.currentItem() is not None:
                action_mark = menu.addAction(_("Mark"))
            action_annotate = menu.addAction(_("Annotate"))
            action_copy = menu.addAction(_("Copy to clipboard"))
        action = menu.exec_(self.ui.textEdit.mapToGlobal(position))
        if selectedText != "" and action == action_copy:
            self.copy_selected_text_to_clipboard()
        if selectedText != "" and self.ui.treeWidget.currentItem() is not None and action == action_mark:
            self.mark()
        cursor = self.ui.textEdit.cursorForPosition(position)
        if selectedText != "" and action == action_annotate:
            self.annotate(cursor.position())
        if action == action_unmark:
            self.unmark(cursor.position())

    def copy_selected_text_to_clipboard(self):
        """ Copy text to clipboard for external use.
        For example adding text to another document. """

        selectedText = self.ui.textEdit.textCursor().selectedText()
        cb = QtWidgets.QApplication.clipboard()
        cb.clear(mode=cb.Clipboard)
        cb.setText(selectedText, mode=cb.Clipboard)

    def tree_menu(self, position):
        """ Context menu for treewidget items.
        Add, rename, memo, move or delete code or category. Change code color.
        Assign selected text to current hovered code. """

        selected_text = self.ui.textEdit.textCursor().selectedText()
        menu = QtWidgets.QMenu()
        selected = self.ui.treeWidget.currentItem()
        #logger.debug("Selected parent: " + selected.parent())
        #index = self.ui.treeWidget.currentIndex()
        '''ActionAssignSelectedText = None
        if selected_text != "" and selected is not None and selected.text(1)[0:3] == 'cid':
            ActionAssignSelectedText = menu.addAction("Assign selected text")'''
        ActionItemAddCode = menu.addAction(_("Add a new code"))
        ActionItemAddCategory = menu.addAction(_("Add a new category"))
        ActionItemRename = menu.addAction(_("Rename"))
        ActionItemEditMemo = menu.addAction(_("View or edit memo"))
        ActionItemDelete = menu.addAction(_("Delete"))
        ActionItemChangeColor = None
        ActionShowCodedMedia = None
        if selected is not None and selected.text(1)[0:3] == 'cid':
            ActionItemChangeColor = menu.addAction(_("Change code color"))
            ActionShowCodedMedia = menu.addAction(_("Show coded text and media"))
        action = menu.exec_(self.ui.treeWidget.mapToGlobal(position))
        if action is not None :
            '''if selected is not None and action == ActionAssignSelectedText:
                self.mark()'''
            if selected is not None and action == ActionItemChangeColor:
                self.change_code_color(selected)
            elif action == ActionItemAddCategory:
                self.add_category()
            elif action == ActionItemAddCode:
                self.add_code()
            elif selected is not None and action == ActionItemRename:
                self.rename_category_or_code(selected)
            elif selected is not None and action == ActionItemEditMemo:
                self.add_edit_memo(selected)
            elif selected is not None and action == ActionItemDelete:
                self.delete_category_or_code(selected)
            elif selected is not None and action == ActionShowCodedMedia:
                found = None
                tofind = int(selected.text(1)[4:])
                for code in self.codes:
                    if code['cid'] == tofind:
                        found = code
                        break
                if found:
                    self.coded_media_dialog(found)

    def eventFilter(self, object, event):
        """ Using this event filter to identify treeWidgetItem drop events.
        http://doc.qt.io/qt-5/qevent.html#Type-enum
        QEvent::Drop 63 A drag and drop operation is completed (QDropEvent).
        https://stackoverflow.com/questions/28994494/why-does-qtreeview-not-fire-a-drop-or-move-event-during-drag-and-drop
        """

        if object is self.ui.treeWidget.viewport():
            if event.type() == QtCore.QEvent.Drop:
                item = self.ui.treeWidget.currentItem()
                parent = self.ui.treeWidget.itemAt(event.pos())
                self.item_moved_update_data(item, parent)
        return False

    def coded_media_dialog(self, data):
        """ Display all coded media for this code, in a separate modal dialog.
        Coded media comes from ALL files and ALL coders.
        param:
            data: code dictionary
        """
        ui = DialogInformation("Coded text : " + data['name'], " ")
        cur = self.app.conn.cursor()
        CODENAME = 0
        COLOR = 1
        SOURCE_NAME = 2
        POS0 = 3
        POS1 = 4
        SELTEXT = 5
        OWNER = 6
        sql = "select code_name.name, color, source.name, pos0, pos1, seltext, code_text.owner from "
        sql += "code_text "
        sql += " join code_name on code_name.cid = code_text.cid join source on fid = source.id "
        sql += " where code_name.cid =" + str(data['cid']) + " "
        sql += " order by source.name, pos0, code_text.owner "
        cur.execute(sql)
        results = cur.fetchall()
        # Text
        for row in results:
            title = '<span style=\"background-color:' + row[COLOR] + '\">'
            title += " File: <em>" + row[SOURCE_NAME] + "</em></span>"
            title += ", Coder: <em>" + row[OWNER] + "</em> "
            title += ", " + str(row[POS0]) + " - " + str(row[POS1])
            ui.ui.textEdit.insertHtml(title)
            ui.ui.textEdit.append(row[SELTEXT] + "\n\n")

        # Images
        sql = "select code_name.name, color, source.name, x1, y1, width, height,"
        sql += "code_image.owner, source.mediapath, source.id, code_image.memo "
        sql += " from code_image join code_name "
        sql += "on code_name.cid = code_image.cid join source on code_image.id = source.id "
        sql += "where code_name.cid =" + str(data['cid']) + " "
        sql += " order by source.name, code_image.owner "
        cur.execute(sql)
        results = cur.fetchall()
        for counter, row in enumerate(results):
            ui.ui.textEdit.insertHtml('<span style=\"background-color:' + row[COLOR] + '\">File: ' + row[8] + '</span>')
            ui.ui.textEdit.insertHtml('<br />Coder: ' + row[7] + '<br />')
            img = {'mediapath': row[8], 'x1': row[3], 'y1': row[4], 'width': row[5], 'height': row[6]}
            self.put_image_into_textedit(img, counter, ui.ui.textEdit)
            ui.ui.textEdit.append("Memo: " + row[10] + "\n\n")

        # Media
        sql = "select code_name.name, color, source.name, pos0, pos1, code_av.memo, "
        sql += "code_av.owner, source.mediapath, source.id from code_av join code_name "
        sql += "on code_name.cid = code_av.cid join source on code_av.id = source.id "
        sql += "where code_name.cid = " + str(data['cid']) + " "
        sql += " order by source.name, code_av.owner "
        cur.execute(sql)
        results = cur.fetchall()
        for row in results:
            ui.ui.textEdit.insertHtml('<span style=\"background-color:' + row[COLOR] + '\">File: ' + row[7] + '</span>')
            start = msecs_to_mins_and_secs(row[3])
            end = msecs_to_mins_and_secs(row[4])
            ui.ui.textEdit.insertHtml('<br />[' + start + ' - ' + end + '] Coder: ' + row[6])
            ui.ui.textEdit.append("Memo: " + row[5] + "\n\n")
        ui.exec_()

    def put_image_into_textedit(self, img, counter, text_edit):
        """ Scale image, add resource to document, insert image.
        A counter is important as each image slice needs a unique name, counter adds
        the uniqueness to the name.
        Called by: coded_media_dialog
        param:
            img: image data dictionary with file location and width, height, position data
            counter: a changing counter is needed to make discrete different images
            text_edit:  the widget that shows the data

        """

        path = self.app.project_path + img['mediapath']
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
        # need unique image names or the same image from the same path is reproduced
        imagename = self.app.project_path + '/images/' + str(counter) + '-' + img['mediapath']
        url = QtCore.QUrl(imagename)
        document.addResource(QtGui.QTextDocument.ImageResource, url, QtCore.QVariant(image))
        cursor = text_edit.textCursor()
        image_format = QtGui.QTextImageFormat()
        image_format.setWidth(image.width() * scaler)
        image_format.setHeight(image.height() * scaler)
        image_format.setName(url.toString())
        cursor.insertImage(image_format)
        text_edit.insertHtml("<br />")

    def item_moved_update_data(self, item, parent):
        """ Called from drop event in treeWidget view port.
        identify code or category to move.
        Also merge codes if one code is dropped on another code. """

        # find the category in the list
        if item.text(1)[0:3] == 'cat':
            found = -1
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(item.text(1)[6:]):
                    found = i
            if found == -1:
                return
            if parent is None:
                self.categories[found]['supercatid'] = None
            else:
                if parent.text(1).split(':')[0] == 'cid':
                    # parent is code (leaf) cannot add child
                    return
                supercatid = int(parent.text(1).split(':')[1])
                if supercatid == self.categories[found]['catid']:
                    # something went wrong
                    return
                self.categories[found]['supercatid'] = supercatid
            cur = self.app.conn.cursor()
            cur.execute("update code_cat set supercatid=? where catid=?",
            [self.categories[found]['supercatid'], self.categories[found]['catid']])
            self.app.conn.commit()
            self.update_dialog_codes_and_categories()
            self.app.delete_backup = False
            return

        # find the code in the list
        if item.text(1)[0:3] == 'cid':
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(item.text(1)[4:]):
                    found = i
            if found == -1:
                return
            if parent is None:
                self.codes[found]['catid'] = None
            else:
                if parent.text(1).split(':')[0] == 'cid':
                    # parent is code (leaf) cannot add child, but can merge
                    self.merge_codes(self.codes[found], parent)
                    return
                catid = int(parent.text(1).split(':')[1])
                self.codes[found]['catid'] = catid

            cur = self.app.conn.cursor()
            cur.execute("update code_name set catid=? where cid=?",
            [self.codes[found]['catid'], self.codes[found]['cid']])
            self.app.conn.commit()
            self.app.delete_backup = False
            self.update_dialog_codes_and_categories()

    def merge_codes(self, item, parent):
        """ Merge code or category with another code or category.
        Called by item_moved_update_data when a code is moved onto another code. """

        msg = _("Merge code: ") + item['name'] + _(" into code: ") + parent.text(0)
        reply = QtWidgets.QMessageBox.question(None, _('Merge codes'),
        msg, QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.No:
            return
        cur = self.app.conn.cursor()
        old_cid = item['cid']
        new_cid = int(parent.text(1).split(':')[1])
        try:
            cur.execute("update code_text set cid=? where cid=?", [new_cid, old_cid])
            cur.execute("update code_av set cid=? where cid=?", [new_cid, old_cid])
            cur.execute("update code_image set cid=? where cid=?", [new_cid, old_cid])
            self.app.conn.commit()
        except Exception as e:
            e = str(e)
            msg = _("Cannot merge codes, unmark overlapping text first. ") + e
            QtWidgets.QInformationDialog(None, _("Cannot merge"), msg)
            return
        cur.execute("delete from code_name where cid=?", [old_cid, ])
        self.app.conn.commit()
        self.app.delete_backup = False
        msg = msg.replace("\n", " ")
        self.parent_textEdit.append(msg)
        self.update_dialog_codes_and_categories()
        # update filter for tooltip
        self.eventFilterTT.setCodes(self.code_text, self.codes)

    def add_code(self):
        """ Use add_item dialog to get new code text. Add_code_name dialog checks for
        duplicate code name. A random color is selected for the code.
        New code is added to data and database. """

        ui = DialogAddItemName(self.codes, _("Add new code"))
        ui.exec_()
        newCodeText = ui.get_new_name()
        if newCodeText is None:
            return
        code_color = colors[randint(0, len(colors) - 1)]
        item = {'name': newCodeText, 'memo': "", 'owner': self.app.settings['codername'],
        'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),'catid': None,
        'color': code_color}
        cur = self.app.conn.cursor()
        cur.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,?,?,?,?)"
            , (item['name'], item['memo'], item['owner'], item['date'], item['catid'], item['color']))
        self.app.conn.commit()
        self.app.delete_backup = False
        cur.execute("select last_insert_rowid()")
        cid = cur.fetchone()[0]
        item['cid'] = cid
        self.parent_textEdit.append(_("New code: ") + item['name'])
        self.update_dialog_codes_and_categories()
        self.get_coded_text_update_eventfilter_tooltips()

    def update_dialog_codes_and_categories(self):
        """ Update code and category tree in DialogCodeImage, DialogCodeAV,
        DialogCodeText, DialogReportCodes.
        Not using isinstance for other classes as could not import the classes to test
        against. There was an import error.
        Using try except blocks for each instance, as instance may have been deleted. """

        for d in self.dialog_list:
            if isinstance(d, DialogCodeText):
                try:
                    d.get_codes_and_categories()
                    d.fill_tree()
                    d.unlight()
                    d.highlight()
                    d.get_coded_text_update_eventfilter_tooltips()
                except RuntimeError as e:
                    pass
            if str(type(d)) == "<class 'view_av.DialogCodeAV'>":
                try:
                    d.get_codes_and_categories()
                    d.fill_tree()
                    d.load_segments()
                    d.unlight()
                    d.highlight()
                    d.get_coded_text_update_eventfilter_tooltips()
                except RuntimeError as e:
                    pass
            if str(type(d)) == "<class 'view_image.DialogCodeImage'>":
                try:
                    d.get_codes_and_categories()
                    d.fill_tree()
                    d.get_coded_areas()
                    d.draw_coded_areas()
                except RuntimeError as e:
                    pass
            if str(type(d)) == "<class 'reports.DialogReportCodes'>":
                try:
                    d.get_data()
                    d.fill_tree()
                except RuntimeError as e:
                    pass

    def add_category(self):
        """ When button pressed, add a new category.
        Note: the addItem dialog does the checking for duplicate category names
        Add the new category as a top level item. """

        ui = DialogAddItemName(self.categories, _("Category"))
        ui.exec_()
        newCatText = ui.get_new_name()
        if newCatText is None:
            return
        item = {'name': newCatText, 'cid': None, 'memo': "",
        'owner': self.app.settings['codername'],
        'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        cur = self.app.conn.cursor()
        cur.execute("insert into code_cat (name, memo, owner, date, supercatid) values(?,?,?,?,?)"
            , (item['name'], item['memo'], item['owner'], item['date'], None))
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False
        self.parent_textEdit.append(_("New category: ") + item['name'])

    def delete_category_or_code(self, selected):
        """ Determine if selected item is a code or category before deletion. """

        if selected.text(1)[0:3] == 'cat':
            self.delete_category(selected)
            return  # Avoid error as selected is now None
        if selected.text(1)[0:3] == 'cid':
            self.delete_code(selected)

    def delete_code(self, selected):
        """ Find code, remove from database, refresh and code data and fill treeWidget.
        """

        # Find the code in the list, check to delete
        found = -1
        for i in range(0, len(self.codes)):
            if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                found = i
        if found == -1:
            return
        code_ = self.codes[found]
        ui = DialogConfirmDelete(_("Code: ") + selected.text(0))
        ok = ui.exec_()
        if not ok:
            return
        cur = self.app.conn.cursor()
        cur.execute("delete from code_name where cid=?", [code_['cid'], ])
        cur.execute("delete from code_text where cid=?", [code_['cid'], ])
        cur.execute("delete from code_av where cid=?", [code_['cid'], ])
        cur.execute("delete from code_image where cid=?", [code_['cid'], ])
        self.app.conn.commit()
        self.app.delete_backup = False
        selected = None
        self.update_dialog_codes_and_categories()
        self.parent_textEdit.append(_("Code deleted: ") + code_['name'] + "\n")

    def delete_category(self, selected):
        """ Find category, remove from database, refresh categories and code data
        and fill treeWidget. """

        found = -1
        for i in range(0, len(self.categories)):
            if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                found = i
        if found == -1:
            return
        category = self.categories[found]
        ui = DialogConfirmDelete(_("Category: ") + selected.text(0))
        ok = ui.exec_()
        if not ok:
            return
        cur = self.app.conn.cursor()
        cur.execute("update code_name set catid=null where catid=?", [category['catid'], ])
        cur.execute("update code_cat set supercatid=null where catid = ?", [category['catid'], ])
        cur.execute("delete from code_cat where catid = ?", [category['catid'], ])
        self.app.conn.commit()
        selected = None
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False
        self.parent_textEdit.append(_("Category deleted: ") + category['name'])

    def add_edit_memo(self, selected):
        """ View and edit a memo for a category or code. """

        if selected.text(1)[0:3] == 'cid':
            # Find the code in the list
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                    found = i
            if found == -1:
                return
            ui = DialogMemo(self.app, _("Memo for Code: ") + self.codes[found]['name'], self.codes[found]['memo'])
            ui.exec_()
            memo = ui.memo
            if memo != self.codes[found]['memo']:
                self.codes[found]['memo'] = memo
                cur = self.app.conn.cursor()
                cur.execute("update code_name set memo=? where cid=?", (memo, self.codes[found]['cid']))
                self.app.conn.commit()
                self.app.delete_backup = False
            if memo == "":
                selected.setData(2, QtCore.Qt.DisplayRole, "")
            else:
                selected.setData(2, QtCore.Qt.DisplayRole, _("Memo"))
                self.parent_textEdit.append(_("Memo for code: ") + self.codes[found]['name'])

        if selected.text(1)[0:3] == 'cat':
            # Find the category in the list
            found = -1
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                    found = i
            if found == -1:
                return
            ui = DialogMemo(self.app, _("Memo for Category: ") + self.categories[found]['name'], self.categories[found]['memo'])
            ui.exec_()
            memo = ui.memo
            if memo != self.categories[found]['memo']:
                self.categories[found]['memo'] = memo
                cur = self.app.conn.cursor()
                cur.execute("update code_cat set memo=? where catid=?", (memo, self.categories[found]['catid']))
                self.app.conn.commit()
                self.app.delete_backup = False
            if memo == "":
                selected.setData(2, QtCore.Qt.DisplayRole, "")
            else:
                selected.setData(2, QtCore.Qt.DisplayRole, _("Memo"))
                self.parent_textEdit.append(_("Memo for category: ") + self.categories[found]['name'])
        self.update_dialog_codes_and_categories()

    def rename_category_or_code(self, selected):
        """ Rename a code or category.
        Check that the code or category name is not currently in use. """

        if selected.text(1)[0:3] == 'cid':
            new_name, ok = QtWidgets.QInputDialog.getText(self, _("Rename code"),
                _("New code name:"), QtWidgets.QLineEdit.Normal, selected.text(0))
            if not ok or new_name == '':
                return
            # Check that no other code has this name
            for c in self.codes:
                if c['name'] == new_name:
                    QtWidgets.QMessageBox.warning(None, _("Name in use"),
                    new_name + _(" is already in use, choose another name."), QtWidgets.QMessageBox.Ok)
                    return
            # Find the code in the list
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                    found = i
            if found == -1:
                return
            # Update codes list and database
            cur = self.app.conn.cursor()
            cur.execute("update code_name set name=? where cid=?", (new_name, self.codes[found]['cid']))
            self.app.conn.commit()
            self.app.delete_backup = False
            old_name = self.codes[found]['name']
            self.parent_textEdit.append(_("Code renamed from: ") + old_name + _(" to: ") + new_name)
            self.update_dialog_codes_and_categories()
            return

        if selected.text(1)[0:3] == 'cat':
            new_name, ok = QtWidgets.QInputDialog.getText(self, _("Rename category"), _("New category name:"),
            QtWidgets.QLineEdit.Normal, selected.text(0))
            if not ok or new_name == '':
                return
            # Check that no other category has this name
            for c in self.categories:
                if c['name'] == new_name:
                    msg = _("This code name is already in use.")
                    QtWidgets.QMessageBox.warning(None, _("Duplicate code name"), msg, QtWidgets.QMessageBox.Ok)
                    return
            # Find the category in the list
            found = -1
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                    found = i
            if found == -1:
                return
            # Update category list and database
            cur = self.app.conn.cursor()
            cur.execute("update code_cat set name=? where catid=?",
            (new_name, self.categories[found]['catid']))
            self.app.conn.commit()
            self.app.delete_backup = False
            old_name = self.categories[found]['name']
            self.update_dialog_codes_and_categories()
            self.parent_textEdit.append(_("Category renamed from: ") + old_name + _(" to: ") + new_name)

    def change_code_color(self, selected):
        """ Change the colour of the currently selected code. """

        cid = int(selected.text(1)[4:])
        found = -1
        for i in range(0, len(self.codes)):
            if self.codes[i]['cid'] == cid:
                found = i
        if found == -1:
            return
        ui = DialogColorSelect(self.codes[found]['color'])
        ok = ui.exec_()
        if not ok:
            return
        new_color = ui.get_color()
        if new_color is None:
            return
        selected.setBackground(0, QBrush(QtGui.QColor(new_color), Qt.SolidPattern))
        # Update codes list, database and color markings
        self.codes[found]['color'] = new_color
        cur = self.app.conn.cursor()
        cur.execute("update code_name set color=? where cid=?",
        (self.codes[found]['color'], self.codes[found]['cid']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.update_dialog_codes_and_categories()

    def view_file_dialog(self):
        """ When view file button is pressed a dialog of filenames is presented to the user.
        The selected file is then displayed for coding. """

        ui = DialogSelectFile(self.filenames, "Select file to view", "single")
        ok = ui.exec_()
        if ok:
            # filename is dictionary with id and name
            self.filename = ui.get_selected()
            self.load_file(self.filename)
        else:
            self.ui.textEdit.clear()

    def load_file(self, filedata):
        """ Load and display file text for this file.
        Get and display coding highlights. """

        self.filename = filedata
        sql_values = []
        file_result = self.app.get_file_texts([filedata['id']])[0]
        sql_values.append(int(file_result['id']))
        self.sourceText = file_result['fulltext']
        self.ui.textEdit.setPlainText(self.sourceText)
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        self.setWindowTitle(_("Code text: ") + self.filename['name'])
        self.ui.lineEdit_search.setEnabled(True)
        self.ui.checkBox_search_case.setEnabled(True)
        self.ui.checkBox_search_all_files.setEnabled(True)
        self.ui.lineEdit_search.setText("")
        self.ui.label_search_totals.setText("0 / 0")

    def get_coded_text_update_eventfilter_tooltips(self):
        """ Called by load_file, and from other dialogs on update. """

        if self.filename is None:
            return
        sql_values = [int(self.filename['id']), self.app.settings['codername']]
        # Get code text for this file and for this coder
        self.code_text = []
        # seltext length, longest first, so overlapping shorter text is superimposed.
        codingsql = "select cid, fid, seltext, pos0, pos1, owner, date, memo from code_text"
        codingsql += " where fid=? and owner=? order by length(seltext) desc"
        cur = self.app.conn.cursor()
        cur.execute(codingsql, sql_values)
        code_results = cur.fetchall()
        for row in code_results:
            self.code_text.append({'cid': row[0], 'fid': row[1], 'seltext': row[2],
            'pos0': row[3], 'pos1': row[4], 'owner': row[5], 'date': row[6], 'memo': row[7]})
        # Update filter for tooltip and redo formatting
        self.eventFilterTT.setCodes(self.code_text, self.codes)
        self.unlight()
        self.highlight()

    def unlight(self):
        """ Remove all text highlighting from current file. """

        if self.sourceText is None:
            return
        cursor = self.ui.textEdit.textCursor()
        cursor.setPosition(0, QtGui.QTextCursor.MoveAnchor)
        cursor.setPosition(len(self.sourceText) - 1, QtGui.QTextCursor.KeepAnchor)
        cursor.setCharFormat(QtGui.QTextCharFormat())

    def highlight(self):
        """ Apply text highlighting to current file.
        If no colour has been assigned to a code, those coded text fragments are coloured gray.
        Each code text item contains: fid, date, pos0, pos1, seltext, cid, status, memo,
        name, owner. """

        if self.sourceText is not None:
            fmt = QtGui.QTextCharFormat()
            cursor = self.ui.textEdit.textCursor()

            # Add coding highlights
            #TODO use different brush style to highlight overlaps - might be too hard to implement
            codes = {x['cid']:x for x in self.codes}
            for item in self.code_text:
                cursor.setPosition(int(item['pos0']), QtGui.QTextCursor.MoveAnchor)
                cursor.setPosition(int(item['pos1']), QtGui.QTextCursor.KeepAnchor)
                color = codes.get(item['cid'],{}).get('color',"#F8E0E0")  # default light red
                brush = QtGui.QBrush(QtGui.QColor(color))
                fmt.setBackground(brush)
                # Highlight codes with memos - these are italicised
                if item['memo'] is not None and item['memo'] != "":
                    fmt.setFontItalic(True)  #TODO I dont think this works, perhaps delete
                else:
                    fmt.setFontItalic(False)
                    fmt.setFontWeight(QtGui.QFont.Normal)
                cursor.setCharFormat(fmt)

            # Add annotation marks - these are in bold
            for note in self.annotations:
                if len(self.filename.keys()) > 0:  # will be zero if using autocode and no file is loaded
                    if note['fid'] == self.filename['id']:
                        cursor.setPosition(int(note['pos0']), QtGui.QTextCursor.MoveAnchor)
                        cursor.setPosition(int(note['pos1']), QtGui.QTextCursor.KeepAnchor)
                        formatB = QtGui.QTextCharFormat()
                        formatB.setFontWeight(QtGui.QFont.Bold)
                        cursor.mergeCharFormat(formatB)
        self.apply_overline_to_overlaps()

    def apply_overline_to_overlaps(self):
        """ Apply overline format to coded text sections which are overlapping. """

        overlapping = []
        overlaps = []
        for i in self.code_text:
            #print(item['pos0'], type(item['pos0']), item['pos1'], type(item['pos1']))
            for j in self.code_text:
                if j != i:
                    if j['pos0'] <= i['pos0'] and j['pos1'] >= i['pos0']:
                        #print("overlapping: j0", j['pos0'], j['pos1'],"- i0", i['pos0'], i['pos1'])
                        if j['pos0'] >= i['pos0'] and j['pos1'] <= i['pos1']:
                            overlaps.append([j['pos0'], j['pos1']])
                        elif i['pos0'] >= j['pos0'] and i['pos1'] <= j['pos1']:
                            overlaps.append([i['pos0'], i['pos1']])
                        elif j['pos0'] > i['pos0']:
                            overlaps.append([j['pos0'], i['pos1']])
                        else:  # j['pos0'] < i['pos0']:
                            overlaps.append([j['pos1'], i['pos0']])
        #print(overlaps)
        cursor = self.ui.textEdit.textCursor()
        fmt = QtGui.QTextCharFormat()
        for o in overlaps:
            fmt = QtGui.QTextCharFormat()
            fmt.setFontOverline(True)
            cursor.setPosition(o[0], QtGui.QTextCursor.MoveAnchor)
            cursor.setPosition(o[1], QtGui.QTextCursor.KeepAnchor)
            cursor.mergeCharFormat(fmt)

    def combo_code_activated(self):
        """ Combobox code item clicked on.
        highlight this coded text. """

        current_text = self.ui.comboBox_codes_in_text.currentText()
        #print(current_text)
        current_code = None
        for code in self.codes:
            if code['name'] == current_text:
                current_code = code
                break
        if current_code is None:
            return
        #print(current_code)
        pos = self.ui.textEdit.textCursor().position()
        codes_here = []
        for item in self.code_text:
            if item['pos0'] <= pos and item['pos1'] >= pos and item['cid'] == current_code['cid']:
                current_coded_text = item
                break
        #print(current_coded_text)
        # remove formatting
        cursor = self.ui.textEdit.textCursor()
        cursor.setPosition(int(item['pos0']), QtGui.QTextCursor.MoveAnchor)
        cursor.setPosition(int(item['pos1']), QtGui.QTextCursor.KeepAnchor)
        cursor.setCharFormat(QtGui.QTextCharFormat())
        # reapply formatting
        fmt = QtGui.QTextCharFormat()
        brush = QtGui.QBrush(QtGui.QColor(current_code['color']))
        fmt.setBackground(brush)
        cursor.setCharFormat(fmt)

        self.apply_overline_to_overlaps()

    def coded_in_text(self):
        """ When coded text is clicked on, the code names at this location are
        displayed in the combobox above the text edit widget.
        Only enabled if 2 or more codes are here. """

        self.ui.comboBox_codes_in_text.setEnabled(False)
        self.ui.label_codes_count.setEnabled(False)
        self.ui.label_codes_clicked_in_text.setEnabled(False)
        pos = self.ui.textEdit.textCursor().position()
        codes_here = []
        for item in self.code_text:
            if item['pos0'] <= pos and item['pos1'] >= pos:
                # logger.debug("Code name for selected pos0:" + str(item['pos0'])+" pos1:"+str(item['pos1'])
                for code in self.codes:
                    if code['cid'] == item['cid']:
                        codes_here.append(code)
        # can show multiple codes for this location
        fontsize = "font-size:" + str(self.app.settings['treefontsize']) + "pt; "
        self.ui.comboBox_codes_in_text.clear()
        code_names = []
        for i, c in enumerate(codes_here):
            code_names.append(c['name'])
        #print(codes_here)
        if len(codes_here) > 1:
            self.ui.comboBox_codes_in_text.setEnabled(True)
            self.ui.label_codes_count.setEnabled(True)
            self.ui.label_codes_clicked_in_text.setEnabled(True)

        self.ui.label_codes_count.setText(str(len(code_names)))
        self.ui.comboBox_codes_in_text.addItems(code_names)
        for i in range(0, len(code_names)):
            self.ui.comboBox_codes_in_text.setItemData(i, code_names[i], QtCore.Qt.ToolTipRole)

    def select_tree_item_by_code_name(self, codename):
        """ Set a tree item code. This sill call fill_code_label and
         put the selected code in the top left code label and
         underline matching text in the textedit.
         param:
            codename: a string of the codename
         """

        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        while item:
            if item.text(0) == codename:
                self.ui.treeWidget.setCurrentItem(item)
            it += 1
            item = it.value()
        self.fill_code_label()

    def mark(self):
        """ Mark selected text in file with currently selected code.
       Need to check for multiple same codes at same pos0 and pos1.
       """

        if self.filename == {}:
            QtWidgets.QMessageBox.warning(None, _('Warning'), _("No file was selected"), QtWidgets.QMessageBox.Ok)
            return
        item = self.ui.treeWidget.currentItem()
        if item is None:
            QtWidgets.QMessageBox.warning(None, _('Warning'), _("No code was selected"), QtWidgets.QMessageBox.Ok)
            return
        if item.text(1).split(':')[0] == 'catid':  # must be a code
            return
        cid = int(item.text(1).split(':')[1])
        selectedText = self.ui.textEdit.textCursor().selectedText()
        pos0 = self.ui.textEdit.textCursor().selectionStart()
        pos1 = self.ui.textEdit.textCursor().selectionEnd()
        # Add the coded section to code text, add to database and update GUI
        coded = {'cid': cid, 'fid': int(self.filename['id']), 'seltext': selectedText,
        'pos0': pos0, 'pos1': pos1, 'owner': self.app.settings['codername'], 'memo': "",
        'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        self.code_text.append(coded)
        self.highlight()
        # Check for an existing duplicated marking first
        cur = self.app.conn.cursor()
        cur.execute("select * from code_text where cid = ? and fid=? and pos0=? and pos1=? and owner=?",
            (coded['cid'], coded['fid'], coded['pos0'], coded['pos1'], coded['owner']))
        result = cur.fetchall()
        if len(result) > 0:
            QtWidgets.QMessageBox.warning(None, _("Already Coded"),
            _("This segment has already been coded with this code by ") + coded['owner'], QtWidgets.QMessageBox.Ok)
            return
        try:
            cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,\
                memo,date) values(?,?,?,?,?,?,?,?)", (coded['cid'], coded['fid'],
                coded['seltext'], coded['pos0'], coded['pos1'], coded['owner'],
                coded['memo'], coded['date']))
            self.app.conn.commit()
            self.app.delete_backup = False
        except Exception as e:
            logger.debug(str(e))
        # Update filter for tooltip
        self.eventFilterTT.setCodes(self.code_text, self.codes)
        self.fill_code_counts_in_tree()

    def unmark(self, location):
        """ Remove code marking by this coder from selected text in current file. """

        if self.filename == {}:
            return
        unmarked_list = []
        for item in self.code_text:
            if location >= item['pos0'] and location <= item['pos1'] and item['owner'] == self.app.settings['codername']:
                unmarked_list.append(item)
        if unmarked_list == []:
            return
        to_unmark = None
        if len(unmarked_list) == 1:
            to_unmark = unmarked_list[0]
        # multiple codes to selet from
        if len(unmarked_list) > 1:
            ui = DialogSelectFile(unmarked_list, _("Select code to unmark"), "single")
            ok = ui.exec_()
            if not ok:
                return
            to_unmark = ui.get_selected()
        if to_unmark is None:
            return

        # Delete from db, remove from coding and update highlights
        cur = self.app.conn.cursor()
        cur.execute("delete from code_text where cid=? and pos0=? and pos1=? and owner=?",
            (to_unmark['cid'], to_unmark['pos0'], to_unmark['pos1'], self.app.settings['codername']))
        self.app.conn.commit()
        self.app.delete_backup = False
        if to_unmark in self.code_text:
            self.code_text.remove(to_unmark)

        # Update filter for tooltip and update code colours
        self.eventFilterTT.setCodes(self.code_text, self.codes)
        self.unlight()
        self.highlight()
        self.fill_code_counts_in_tree()

    def annotate(self, location):
        """ Add view, or remove an annotation for selected text.
        Annotation positions are displayed as bold text.
        """

        if self.filename == {}:
            QtWidgets.QMessageBox.warning(None, _('Warning'), _("No file was selected"))
            return
        pos0 = self.ui.textEdit.textCursor().selectionStart()
        pos1 = self.ui.textEdit.textCursor().selectionEnd()
        text_length = len(self.ui.textEdit.toPlainText())
        if pos0 >= text_length or pos1 >= text_length:
            return
        item = None
        details = ""
        annotation = ""
        # Find annotation at this position for this file
        for note in self.annotations:
            if location >= note['pos0'] and location <= note['pos1'] and note['fid'] == self.filename['id']:
                item = note  # use existing annotation
                details = item['owner'] + " " + item['date']
        # Exit this method if no text selected and there is no annotation at this position
        if pos0 == pos1 and item is None:
            return
        # Add new item to annotations, add to database and update GUI
        if item is None:
            item = {'fid': int(self.filename['id']), 'pos0': pos0, 'pos1': pos1,
            'memo': str(annotation), 'owner': self.app.settings['codername'],
            'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'anid': -1}
        ui = DialogMemo(self.app, _("Annotation: ") + details, item['memo'])
        ui.exec_()
        item['memo'] = ui.memo
        if item['memo'] != "":
            cur = self.app.conn.cursor()
            cur.execute("insert into annotation (fid,pos0, pos1,memo,owner,date) \
                values(?,?,?,?,?,?)" ,(item['fid'], item['pos0'], item['pos1'],
                item['memo'], item['owner'], item['date']))
            self.app.conn.commit()
            self.app.delete_backup = False
            cur.execute("select last_insert_rowid()")
            anid = cur.fetchone()[0]
            item['anid'] = anid
            self.annotations.append(item)
            self.highlight()
            self.parent_textEdit.append(_("Annotation added at position: ") \
                + str(item['pos0']) + "-" + str(item['pos1']) + _(" for: ") + self.filename['name'])
        # If blank delete the annotation
        if item['memo'] == "":
            cur = self.app.conn.cursor()
            cur.execute("delete from annotation where pos0 = ?", (item['pos0'], ))
            self.app.conn.commit()
            self.app.delete_backup = False
            for note in self.annotations:
                if note['pos0'] == item['pos0'] and note['fid'] == item['fid']:
                    self.annotations.remove(note)
            self.parent_textEdit.append(_("Annotation removed from position ") \
                + str(item['pos0']) + _(" for: ") + self.filename['name'])
        self.unlight()
        self.highlight()

    def auto_code(self):
        """ Autocode text in one file or all files with currently selected code.
        """

        item = self.ui.treeWidget.currentItem()
        if item is None:
            QtWidgets.QMessageBox.warning(None, _('Warning'), _("No code was selected"),
                QtWidgets.QMessageBox.Ok)
            return
        if item.text(1)[0:3] == 'cat':
            return
        cid = int(item.text(1).split(':')[1])
        # Input dialog too narrow, so code below
        dialog = QtWidgets.QInputDialog(None)
        dialog.setWindowTitle(_("Automatic coding"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.TextInput)
        dialog.setToolTip(_("Use | to code multiple texts"))
        dialog.setLabelText(_("Autocode files with the current code for this text:") +"\n" + item.text(0))
        dialog.resize(200, 20)
        ok = dialog.exec_()
        if not ok:
            return
        find_text = str(dialog.textValue())
        if find_text == "" or find_text is None:
            return
        texts = find_text.split('|')
        tmp = list(set(texts))
        texts = []
        for t in tmp:
            if t != "":
                texts.append(t)

        ui = DialogSelectFile(self.filenames, _("Select file to view"), "many")
        ok = ui.exec_()
        if not ok:
            return
        files = ui.get_selected()
        if len(files) == 0:
            return

        for txt in texts:
            filenames = ""
            for f in files:
                filenames += f['name'] + " "
                cur = self.app.conn.cursor()
                cur.execute("select name, id, fulltext, memo, owner, date from source where id=? and mediapath is Null",
                    [f['id']])
                currentfile = cur.fetchone()
                text = currentfile[2]
                textStarts = [match.start() for match in re.finditer(re.escape(txt), text)]
                # Add new items to database
                for startPos in textStarts:
                    item = {'cid': cid, 'fid': int(f['id']), 'seltext': str(txt),
                    'pos0': startPos, 'pos1': startPos + len(txt),
                    'owner': self.app.settings['codername'], 'memo': "",
                    'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                    cur = self.app.conn.cursor()
                    cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,\
                        owner,memo,date) values(?,?,?,?,?,?,?,?)"
                        , (item['cid'], item['fid'], item['seltext'], item['pos0'],
                        item['pos1'], item['owner'], item['memo'], item['date']))
                    self.app.conn.commit()
                    self.app.delete_backup = False

                    # If this is the currently open file update the code text list and GUI
                    if f['id'] == self.filename['id']:
                        self.code_text.append(item)
                self.highlight()
                self.parent_textEdit.append(_("Automatic coding in files: ") + filenames \
                    + _(". with text: ") + txt)

        # Update tooltip filter and code tree code counts
        self.eventFilterTT.setCodes(self.code_text, self.codes)
        self.fill_code_counts_in_tree()


class ToolTip_EventFilter(QtCore.QObject):
    """ Used to add a dynamic tooltip for the textEdit.
    The tool top text is changed according to its position in the text.
    If over a coded section the codename(s) are displayed in the tooltip.
    """

    codes = None
    code_text = None

    def setCodes(self, code_text, codes):
        self.code_text = code_text
        self.codes = codes
        for item in self.code_text:
            for c in self.codes:
                if item['cid'] == c['cid']:
                    item['name'] = c['name']
                    item['color'] = c['color']

    def eventFilter(self, receiver, event):
        #QtGui.QToolTip.showText(QtGui.QCursor.pos(), tip)
        if event.type() == QtCore.QEvent.ToolTip:
            helpEvent = QHelpEvent(event)
            cursor = QtGui.QTextCursor()
            cursor = receiver.cursorForPosition(helpEvent.pos())
            pos = cursor.position()
            receiver.setToolTip("")
            displayText = ""
            # Occasional None type error
            if self.code_text is None:
                #Call Base Class Method to Continue Normal Event Processing
                return super(ToolTip_EventFilter, self).eventFilter(receiver, event)
            for item in self.code_text:
                if item['pos0'] <= pos and item['pos1'] >= pos and item['seltext'] is not None:
                    # keep the snippets short
                    seltext = item['seltext']
                    seltext = seltext.replace("\n", "")
                    seltext = seltext.replace("\r", "")
                    # if selected text is long just show start end snippets with a readable cut off (ie not cut off halway through a word)
                    if len(seltext) > 90:
                        pretext = seltext[0:40].split(' ')
                        posttext = seltext[len(seltext) - 40:].split(' ')
                        try:
                            pretext = pretext[:-1]
                        except:
                            pass
                        try:
                            posttext = posttext[1:]
                        except:
                            pass
                        seltext = " ".join(pretext) + " ... " + " ".join(posttext)
                    if displayText == "":
                        try:
                            displayText = '<p style="background-color:' + item['color'] + '"><em>' + item['name'] + "</em><br />" + seltext + "</p>"
                        except Exception as e:
                            msg = "Codes ToolTipEventFilter Exception\n" + str(e) + ". Possible key error: \n"
                            msg += str(item)
                            logger.error(msg)
                    else:  # Can have multiple codes on same selected area
                        try:
                            displayText += '<p style="background-color:' + item['color'] + '"><em>' + item['name'] + "</em><br />" + seltext + "</p>"
                        except Exception as e:
                            msg = "Codes ToolTipEventFilter Exception\n" + str(e) + ". Possible key error: \n"
                            msg += str(item)
                            logger.error(msg)
            if displayText != "":
                receiver.setToolTip(displayText)

        #Call Base Class Method to Continue Normal Event Processing
        return super(ToolTip_EventFilter, self).eventFilter(receiver, event)
