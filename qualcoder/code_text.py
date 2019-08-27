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
from GUI.ui_dialog_codes import Ui_Dialog_codes
from memo import DialogMemo
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


class DialogCodeText(QtWidgets.QDialog):
    ''' Code management. Add, delete codes. Mark and unmark text.
    Add memos and colors to codes.
    Trialled using setHtml for documents, but on marking text Html formattin was replaced, also
    on unmarking text, the unmark was not immediately cleared (needed to reload the file) '''

    NAME_COLUMN = 0
    ID_COLUMN = 1
    MEMO_COLUMN = 2
    settings = None
    parent_textEdit = None
    codes = []
    categories = []
    filenames = []
    filename = {}  # contains filename and file id returned from SelectFile
    sourceText = None
    code_text = []
    annotations = []
    search_indices = []
    search_index = 0
    eventFilter = None

    def __init__(self, settings, parent_textEdit):

        sys.excepthook = exception_handler
        self.settings = settings
        self.parent_textEdit = parent_textEdit
        self.codes = []
        self.categories = []
        self.filenames = []
        self.annotations = []
        self.search_indices = []
        self.search_index = 0
        self.get_codes_categories()
        cur = self.settings['conn'].cursor()
        cur.execute("select id, name from source where mediapath is Null")
        result = cur.fetchall()
        for row in result:
            self.filenames.append({'id': row[0], 'name': row[1]})
        cur.execute("select anid, fid, pos0, pos1, memo, owner, date from annotation where owner=?",
            [self.settings['codername'], ])
        result = cur.fetchall()
        for row in result:
            self.annotations.append({'anid': row[0], 'fid': row[1], 'pos0': row[2],
            'pos1': row[3], 'memo': row[4], 'owner': row[5], 'date': row[6]})

        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_codes()
        self.ui.setupUi(self)
        newfont = QtGui.QFont(settings['font'], settings['fontsize'], QtGui.QFont.Normal)
        self.setFont(newfont)
        treefont = QtGui.QFont(settings['font'], settings['treefontsize'], QtGui.QFont.Normal)
        self.ui.treeWidget.setFont(treefont)
        self.ui.label_coder.setText("Coder: " + settings['codername'])
        self.ui.label_file.setText("File: Not selected")
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
        self.ui.pushButton_view_file.clicked.connect(self.view_file)
        self.ui.pushButton_auto_code.clicked.connect(self.auto_code)
        #self.ui.checkBox_show_coders.stateChanged.connect(self.view_file)
        self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
        self.ui.pushButton_search_results.setEnabled(False)
        self.ui.pushButton_search_results.pressed.connect(self.move_to_next_search_text)
        self.ui.treeWidget.setDragEnabled(True)
        self.ui.treeWidget.setAcceptDrops(True)
        self.ui.treeWidget.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.ui.treeWidget.viewport().installEventFilter(self)
        self.ui.treeWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.treeWidget.customContextMenuRequested.connect(self.tree_menu)
        self.ui.treeWidget.itemClicked.connect(self.fill_code_label)
        self.ui.splitter.setSizes([150, 400])
        self.fill_tree()

    def fill_code_label(self):
        """ Fill code label with currently selected item's code name. """

        current = self.ui.treeWidget.currentItem()
        if current.text(1)[0:3] == 'cat':
            self.ui.label_code.setText(_("NO CODE SELECTED"))
            return
        self.ui.label_code.setText("Code: " + current.text(0))

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes. """

        cats = deepcopy(self.categories)
        codes = deepcopy(self.codes)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(3)
        self.ui.treeWidget.setHeaderLabels([_("Name"), _("Id"), _("Memo")])
        self.ui.treeWidget.setColumnHidden(1, True)
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
                top_item.setIcon(0, QtGui.QIcon("GUI/icon_cat.png"))
                top_item.setToolTip(0, c['owner'] + "\n" + c['date'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_list.append(c)
        for item in remove_list:
            #try:
            cats.remove(item)
            #except Exception as e:
            #    logger.debug(e, item)

        ''' add child categories. look at each unmatched category, iterate through tree
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
                        child.setIcon(0, QtGui.QIcon("GUI/icon_cat.png"))
                        child.setToolTip(0, c['owner'] + "\n" + c['date'])
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
                top_item.setIcon(0, QtGui.QIcon("GUI/icon_code.png"))
                top_item.setToolTip(0, c['owner'] + "\n" + c['date'])
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
                    child.setIcon(0, QtGui.QIcon("GUI/icon_code.png"))
                    child.setToolTip(0, c['owner'] + "\n" + c['date'])
                    child.setFlags(Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
                    item.addChild(child)
                    c['catid'] = -1  # make unmatchable
                it += 1
                item = it.value()
        self.ui.treeWidget.expandAll()

    def get_codes_categories(self):
        """ Called from init, delete category/code. """

        self.categories = []
        cur = self.settings['conn'].cursor()
        cur.execute("select name, catid, owner, date, memo, supercatid from code_cat")
        result = cur.fetchall()
        for row in result:
            self.categories.append({'name': row[0], 'catid': row[1], 'owner': row[2],
            'date': row[3], 'memo': row[4], 'supercatid': row[5]})

        self.codes = []
        cur = self.settings['conn'].cursor()
        cur.execute("select name, memo, owner, date, cid, catid, color from code_name")
        result = cur.fetchall()
        for row in result:
            self.codes.append({'name': row[0], 'memo': row[1], 'owner': row[2], 'date': row[3],
            'cid': row[4], 'catid': row[5], 'color': row[6]})

    def search_for_text(self):
        """ On text changed in lineEdit_search, find indices of matching text.
        Only where text is two or more characters long.
        Resets current search_index.
        """

        if len(self.search_indices) == 0:
            self.ui.pushButton_search_results.setEnabled(False)
        self.search_indices = []
        self.search_index = -1
        text = self.ui.lineEdit_search.text()
        self.ui.pushButton_search_results.setText("0 / 0")
        if len(text) < 2 or len(self.ui.textEdit.toPlainText()) == 0:
            return
        self.search_indices = [match.start() for match in re.finditer(re.escape(text), self.sourceText)]
        if len(self.search_indices) > 0:
            self.ui.pushButton_search_results.setEnabled(True)
        self.ui.pushButton_search_results.setText("0 / " + str(len(self.search_indices)))

    def move_to_next_search_text(self):
        """ Push button pressed to move to next search text position. """

        self.search_index += 1
        if self.search_index == len(self.search_indices):
            self.search_index = 0
        cur = self.ui.textEdit.textCursor()
        cur.setPosition(self.search_indices[self.search_index])
        cur.setPosition(cur.position() + len(self.ui.lineEdit_search.text()), QtGui.QTextCursor.KeepAnchor)
        self.ui.textEdit.setTextCursor(cur)
        self.ui.pushButton_search_results.setText(str(self.search_index + 1) + " / " + str(len(self.search_indices)))

    def textEdit_menu(self, position):
        """ Context menu for textEdit. Mark, unmark, annotate, copy. """

        menu = QtWidgets.QMenu()
        ActionItemMark = menu.addAction(_("Mark"))
        ActionItemUnmark = menu.addAction(_("Unmark"))
        ActionItemAnnotate = menu.addAction(_("Annotate"))
        ActionItemCopy = menu.addAction(_("Copy to clipboard"))
        action = menu.exec_(self.ui.textEdit.mapToGlobal(position))
        if action == ActionItemCopy:
            self.copy_selected_text_to_clipboard()
        if action == ActionItemMark:
            self.mark()
        cursor = self.ui.textEdit.cursorForPosition(position)
        if action == ActionItemUnmark:
            self.unmark(cursor.position())
        if action == ActionItemAnnotate:
            self.annotate(cursor.position())

    def copy_selected_text_to_clipboard(self):
        """ Copy text to clipboard for external use.
        For example adding text to another document. """

        selectedText = self.ui.textEdit.textCursor().selectedText()
        cb = QtWidgets.QApplication.clipboard()
        cb.clear(mode=cb.Clipboard)
        cb.setText(selectedText, mode=cb.Clipboard)

    def tree_menu(self, position):
        """ Context menu for treewidget items.
        Add, rename, memo, move or delete code or category. Change code color. """

        menu = QtWidgets.QMenu()
        selected = self.ui.treeWidget.currentItem()
        #logger.debug("Selected parent: " + selected.parent())
        #index = self.ui.treeWidget.currentIndex()
        ActionItemAddCode = menu.addAction(_("Add a new code"))
        ActionItemAddCategory = menu.addAction(_("Add a new category"))
        ActionItemRename = menu.addAction(_("Rename"))
        ActionItemEditMemo = menu.addAction(_("View or edit memo"))
        ActionItemDelete = menu.addAction(_("Delete"))
        if selected is not None and selected.text(1)[0:3] == 'cid':
            ActionItemChangeColor = menu.addAction(_("Change code color"))

        action = menu.exec_(self.ui.treeWidget.mapToGlobal(position))
        if selected is not None and selected.text(1)[0:3] == 'cid' and action == ActionItemChangeColor:
            self.change_code_color(selected)
        if action == ActionItemAddCategory:
            self.add_category()
        if action == ActionItemAddCode:
            self.add_code()
        if selected is not None and action == ActionItemRename:
            self.rename_category_or_code(selected)
        if selected is not None and action == ActionItemEditMemo:
            self.add_edit_memo(selected)
        if selected is not None and action == ActionItemDelete:
            self.delete_category_or_code(selected)
            return

    def eventFilter(self, object, event):
        """ Using this event filter to identfiy treeWidgetItem drop events.
        http://doc.qt.io/qt-5/qevent.html#Type-enum
        QEvent::Drop 63 A drag and drop operation is completed (QDropEvent).
        https://stackoverflow.com/questions/28994494/why-does-qtreeview-not-fire-a-drop-or-move-event-during-drag-and-drop
        """

        if object is self.ui.treeWidget.viewport():
            if event.type() == QtCore.QEvent.Drop:
                item = self.ui.treeWidget.currentItem()
                parent = self.ui.treeWidget.itemAt(event.pos())
                self.item_moved_update_data(item, parent)
                self.get_codes_categories()
                self.fill_tree()
        return False

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
            cur = self.settings['conn'].cursor()
            cur.execute("update code_cat set supercatid=? where catid=?",
            [self.categories[found]['supercatid'], self.categories[found]['catid']])
            self.settings['conn'].commit()

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

            cur = self.settings['conn'].cursor()
            cur.execute("update code_name set catid=? where cid=?",
            [self.codes[found]['catid'], self.codes[found]['cid']])
            self.settings['conn'].commit()

    def merge_codes(self, item, parent):
        """ Merge code or category with another code or category.
        Called by item_moved_update_data when a code is moved onto another code. """

        msg = _("Merge code: ") + item['name'] + _(" into code: ") + parent.text(0)
        reply = QtWidgets.QMessageBox.question(None, _('Merge codes'),
        msg, QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.No:
            return
        cur = self.settings['conn'].cursor()
        old_cid = item['cid']
        new_cid = int(parent.text(1).split(':')[1])
        try:
            cur.execute("update code_text set cid=? where cid=?", [new_cid, old_cid])
            cur.execute("update code_image set cid=? where cid=?", [new_cid, old_cid])
            cur.execute("update code_av set cid=? where cid=?", [new_cid, old_cid])
            self.settings['conn'].commit()
        except Exception as e:
            e = str(e)
            msg = _("Cannot merge codes, unmark overlapping text first. ") + e
            QtWidgets.QInformationDialog(None, _("Cannot merge"), msg)
            return
        cur.execute("delete from code_name where cid=?", [old_cid, ])
        self.settings['conn'].commit()
        msg = msg.replace("\n", " ")
        self.parent_textEdit.append(msg)
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
        item = {'name': newCodeText, 'memo': "", 'owner': self.settings['codername'],
        'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),'catid': None,
        'color': code_color}
        cur = self.settings['conn'].cursor()
        cur.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,?,?,?,?)"
            , (item['name'], item['memo'], item['owner'], item['date'], item['catid'], item['color']))
        self.settings['conn'].commit()
        cur.execute("select last_insert_rowid()")
        cid = cur.fetchone()[0]
        item['cid'] = cid
        self.codes.append(item)
        top_item = QtWidgets.QTreeWidgetItem([item['name'], 'cid:' + str(item['cid']), ""])
        top_item.setIcon(0, QtGui.QIcon("GUI/icon_code.png"))
        color = item['color']
        top_item.setBackground(0, QBrush(QtGui.QColor(color), Qt.SolidPattern))
        self.ui.treeWidget.addTopLevelItem(top_item)
        self.ui.treeWidget.setCurrentItem(top_item)
        self.parent_textEdit.append(_("New code: ") + item['name'])

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
        'owner': self.settings['codername'],
        'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        cur = self.settings['conn'].cursor()
        cur.execute("insert into code_cat (name, memo, owner, date, supercatid) values(?,?,?,?,?)"
            , (item['name'], item['memo'], item['owner'], item['date'], None))
        self.settings['conn'].commit()
        cur.execute("select last_insert_rowid()")
        catid = cur.fetchone()[0]
        item['catid'] = catid
        self.categories.append(item)
        # update widget
        top_item = QtWidgets.QTreeWidgetItem([item['name'], 'catid:' + str(item['catid']), ""])
        top_item.setIcon(0, QtGui.QIcon("GUI/icon_cat.png"))
        self.ui.treeWidget.addTopLevelItem(top_item)
        self.parent_textEdit.append(_("New category: ") + item['name'])

    def delete_category_or_code(self, selected):
        """ Determine if selected item is a code or category before deletion. """

        if selected.text(1)[0:3] == 'cat':
            self.delete_category(selected)
            return  # avoid error as selected is now None
        if selected.text(1)[0:3] == 'cid':
            self.delete_code(selected)

    def delete_code(self, selected):
        """ Find code, remove from database, refresh and code data and fill treeWidget.
        """

        # find the code in the list, check to delete
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
        cur = self.settings['conn'].cursor()
        cur.execute("delete from code_name where cid=?", [code_['cid'], ])
        cur.execute("delete from code_text where cid=?", [code_['cid'], ])
        cur.execute("delete from code_image where cid=?", [code_['cid'], ])
        cur.execute("delete from code_av where cid=?", [code_['cid'], ])
        self.settings['conn'].commit()
        selected = None
        self.get_codes_categories()
        self.fill_tree()
        self.parent_textEdit.append(_("Code deleted: ") + code_['name'] + "\n")
        # update filter for tooltip
        self.eventFilterTT.setCodes(self.code_text, self.codes)

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
        cur = self.settings['conn'].cursor()
        cur.execute("update code_name set catid=null where catid=?", [category['catid'], ])
        cur.execute("update code_cat set supercatid=null where catid = ?", [category['catid'], ])
        cur.execute("delete from code_cat where catid = ?", [category['catid'], ])
        self.settings['conn'].commit()
        selected = None
        self.get_codes_categories()
        self.fill_tree()
        self.parent_textEdit.append(_("Category deleted: ") + category['name'])

    def add_edit_memo(self, selected):
        """ View and edit a memo for a category or code. """

        if selected.text(1)[0:3] == 'cid':
            # find the code in the list
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                    found = i
            if found == -1:
                return
            ui = DialogMemo(self.settings, _("Memo for Code: ") + self.codes[found]['name'], self.codes[found]['memo'])
            ui.exec_()
            memo = ui.memo
            if memo != self.codes[found]['memo']:
                self.codes[found]['memo'] = memo
                cur = self.settings['conn'].cursor()
                cur.execute("update code_name set memo=? where cid=?", (memo, self.codes[found]['cid']))
                self.settings['conn'].commit()
            if memo == "":
                selected.setData(2, QtCore.Qt.DisplayRole, "")
            else:
                selected.setData(2, QtCore.Qt.DisplayRole, _("Memo"))
                self.parent_textEdit.append(_("Memo for code: ") + self.codes[found]['name'])

        if selected.text(1)[0:3] == 'cat':
            # find the category in the list
            found = -1
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                    found = i
            if found == -1:
                return
            ui = DialogMemo(self.settings, _("Memo for Category: ") + self.categories[found]['name'], self.categories[found]['memo'])
            ui.exec_()
            memo = ui.memo
            if memo != self.categories[found]['memo']:
                self.categories[found]['memo'] = memo
                cur = self.settings['conn'].cursor()
                cur.execute("update code_cat set memo=? where catid=?", (memo, self.categories[found]['catid']))
                self.settings['conn'].commit()
            if memo == "":
                selected.setData(2, QtCore.Qt.DisplayRole, "")
            else:
                selected.setData(2, QtCore.Qt.DisplayRole, _("Memo"))
                self.parent_textEdit.append(_("Memo for category: ") + self.categories[found]['name'])

    def rename_category_or_code(self, selected):
        """ Rename a code or category.
        Check that the code or category name is not currently in use. """

        if selected.text(1)[0:3] == 'cid':
            new_name, ok = QtWidgets.QInputDialog.getText(self, _("Rename code"),
                _("New code name:"), QtWidgets.QLineEdit.Normal, selected.text(0))
            if not ok or new_name == '':
                return
            # check that no other code has this text
            for c in self.codes:
                if c['name'] == new_name:
                    QtWidgets.QMessageBox.warning(None, _("Name in use"),
                    new_name + _(" is already in use, choose another name."), QtWidgets.QMessageBox.Ok)
                    return
            # find the code in the list
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                    found = i
            if found == -1:
                return
            # update codes list and database
            cur = self.settings['conn'].cursor()
            cur.execute("update code_name set name=? where cid=?", (new_name, self.codes[found]['cid']))
            self.settings['conn'].commit()
            old_name = self.codes[found]['name']
            self.codes[found]['name'] = new_name
            selected.setData(0, QtCore.Qt.DisplayRole, new_name)
            self.parent_textEdit.append(_("Code renamed from: ") + old_name + _(" to: ") + new_name)
            # update filter for tooltip
            self.eventFilterTT.setCodes(self.code_text, self.codes)
            return

        if selected.text(1)[0:3] == 'cat':
            new_name, ok = QtWidgets.QInputDialog.getText(self, _("Rename category"), _("New category name:"),
            QtWidgets.QLineEdit.Normal, selected.text(0))
            if not ok or new_name == '':
                return
            # check that no other category has this text
            for c in self.categories:
                if c['name'] == new_name:
                    msg = _("This code name is already in use.")
                    QtWidgets.QMessageBox.warning(None, _("Duplicate code name"), msg, QtWidgets.QMessageBox.Ok)
                    return
            # find the category in the list
            found = -1
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                    found = i
            if found == -1:
                return
            # update category list and database
            cur = self.settings['conn'].cursor()
            cur.execute("update code_cat set name=? where catid=?",
            (new_name, self.categories[found]['catid']))
            self.settings['conn'].commit()
            old_name = self.categories[found]['name']
            self.categories[found]['name'] = new_name
            selected.setData(0, QtCore.Qt.DisplayRole, new_name)
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
        #update codes list, database and color markings
        self.codes[found]['color'] = new_color
        cur = self.settings['conn'].cursor()
        cur.execute("update code_name set color=? where cid=?",
        (self.codes[found]['color'], self.codes[found]['cid']))
        self.settings['conn'].commit()
        self.highlight()

    def view_file(self):
        """ When view file button is pressed a dialog of filenames is presented to the user.
        The selected file is then displayed for coding. """

        ui = DialogSelectFile(self.filenames, "Select file to view", "single")
        ok = ui.exec_()
        sql_values = []
        if ok:
            # filename is dictionary with id and name
            self.filename = ui.get_selected()
            cur = self.settings['conn'].cursor()
            cur.execute("select name, id, fulltext, memo, owner, date from source where id=?",
                [self.filename['id']])
            file_result = cur.fetchone()
            sql_values.append(int(file_result[1]))
            self.sourceText = file_result[2]
            self.ui.label_file.setText("File " + str(file_result[1]) + " : " + file_result[0])

            # get code text for this file and for this coder, or all coders
            self.code_text = []
            codingsql = "select cid, fid, seltext, pos0, pos1, owner, date, memo from code_text"
            codingsql += " where fid=? "
            if not self.ui.checkBox_show_coders.isChecked():
                codingsql += " and owner=? "
                sql_values.append(self.settings['codername'])
            cur.execute(codingsql, sql_values)
            code_results = cur.fetchall()
            for row in code_results:
                self.code_text.append({'cid': row[0], 'fid': row[1], 'seltext': row[2],
                'pos0': row[3], 'pos1':row[4], 'owner': row[5], 'date': row[6], 'memo': row[7]})
            self.ui.textEdit.setPlainText(self.sourceText)
            # update filter for tooltip
            self.eventFilterTT.setCodes(self.code_text, self.codes)
            # clear search indices and lineEdit
            self.ui.lineEdit_search.setText("")
            self.search_indices = []
            self.search_index = 0
            # redo formatting
            self.unlight()
            self.highlight()
        else:
            self.ui.textEdit.clear()

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

        if self.sourceText is None:
            return
        fmt = QtGui.QTextCharFormat()
        cursor = self.ui.textEdit.textCursor()

        # add coding highlights
        for item in self.code_text:
            cursor.setPosition(int(item['pos0']), QtGui.QTextCursor.MoveAnchor)
            cursor.setPosition(int(item['pos1']), QtGui.QTextCursor.KeepAnchor)
            color = "#F8E0E0"  # default light red
            for fcode in self.codes:
                if fcode['cid'] == item['cid']:
                    color = fcode['color']
            fmt.setBackground(QtGui.QBrush(QtGui.QColor(color)))
            # highlight codes with memos - these are italicised
            if item['memo'] is not None and item['memo'] != "":
                fmt.setFontItalic(True)
            else:
                fmt.setFontItalic(False)
                fmt.setFontWeight(QtGui.QFont.Normal)
            cursor.setCharFormat(fmt)

        # add annotation marks - these are in bold
        for note in self.annotations:
            if len(self.filename.keys()) > 0:  # will be zero if using autocode and no file is loaded
                if note['fid'] == self.filename['id']:
                    cursor.setPosition(int(note['pos0']), QtGui.QTextCursor.MoveAnchor)
                    cursor.setPosition(int(note['pos1']), QtGui.QTextCursor.KeepAnchor)
                    formatB = QtGui.QTextCharFormat()
                    formatB.setFontWeight(QtGui.QFont.Bold)
                    cursor.mergeCharFormat(formatB)

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
        # add the coded section to code text, add to database and update GUI
        coded = {'cid': cid, 'fid': int(self.filename['id']), 'seltext': selectedText,
        'pos0': pos0, 'pos1': pos1, 'owner': self.settings['codername'], 'memo': "",
        'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        self.code_text.append(coded)
        self.highlight()
        cur = self.settings['conn'].cursor()

        # check for an existing duplicated marking first
        cur.execute("select * from code_text where cid = ? and fid=? and pos0=? and pos1=? and owner=?",
            (coded['cid'], coded['fid'], coded['pos0'], coded['pos1'], coded['owner']))
        result = cur.fetchall()
        if len(result) > 0:
            QtWidgets.QMessageBox.warning(None, _("Already Coded"),
            _("This segment has already been coded with this code by ") + coded['owner'], QtWidgets.QMessageBox.Ok)
            return

        #TODO should not get sqlite3.IntegrityError:
        #TODO UNIQUE constraint failed: code_text.cid, code_text.fid, code_text.pos0, code_text.pos1
        try:
            cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,\
                memo,date) values(?,?,?,?,?,?,?,?)", (coded['cid'], coded['fid'],
                coded['seltext'], coded['pos0'], coded['pos1'], coded['owner'],
                coded['memo'], coded['date']))
            self.settings['conn'].commit()
        except Exception as e:
            logger.debug(str(e))
        # update filter for tooltip
        self.eventFilterTT.setCodes(self.code_text, self.codes)

    def coded_in_text(self):
        """ When coded text is clicked on, the code name is displayed in the label above
        the text edit widget. """

        labelText = _("Coded: ")
        self.ui.label_coded.setText(labelText)
        pos = self.ui.textEdit.textCursor().position()
        for item in self.code_text:
            if item['pos0'] <= pos and item['pos1'] >= pos:
                # logger.debug("Code name for selected pos0:" + str(item['pos0'])+" pos1:"+str(item['pos1'])
                for code in self.codes:
                    if code['cid'] == item['cid']:
                        labelText = _("Coded: ") + code['name']
        self.ui.label_coded.setText(labelText)

    def unmark(self, location):
        """ Remove code marking by this coder from selected text in current file. """

        if self.filename == {}:
            return
        unmarked = None
        for item in self.code_text:
            if location >= item['pos0'] and location <= item['pos1'] and item['owner'] == self.settings['codername']:
                unmarked = item
        if unmarked is None:
            return

        # delete from db, remove from coding and update highlights
        cur = self.settings['conn'].cursor()
        cur.execute("delete from code_text where cid=? and pos0=? and pos1=? and owner=?",
            (unmarked['cid'], unmarked['pos0'], unmarked['pos1'], self.settings['codername']))
        self.settings['conn'].commit()
        if unmarked in self.code_text:
            self.code_text.remove(unmarked)

        # update filter for tooltip and update code colours
        self.eventFilterTT.setCodes(self.code_text, self.codes)
        self.unlight()
        self.highlight()

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
        # find existing annotation at this position for this file
        for note in self.annotations:
            if location >= note['pos0'] and location <= note['pos1'] and note['fid'] == self.filename['id']:
                item = note  # use existing annotation
                details = item['owner'] + " " + item['date']
        # exit method if no text selected and there is not annotation at this position
        if pos0 == pos1 and item is None:
            return
        # add new item to annotations, add to database and update GUI
        if item is None:
            item = {'fid': int(self.filename['id']), 'pos0': pos0, 'pos1': pos1,
            'memo': str(annotation), 'owner': self.settings['codername'],
            'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'anid': -1}
        ui = DialogMemo(self.settings, _("Annotation: ") + details, item['memo'])
        ui.exec_()
        item['memo'] = ui.memo
        if item['memo'] != "":
            cur = self.settings['conn'].cursor()
            cur.execute("insert into annotation (fid,pos0, pos1,memo,owner,date) \
                values(?,?,?,?,?,?)" ,(item['fid'], item['pos0'], item['pos1'],
                item['memo'], item['owner'], item['date']))
            self.settings['conn'].commit()
            cur.execute("select last_insert_rowid()")
            anid = cur.fetchone()[0]
            item['anid'] = anid
            self.annotations.append(item)
            self.highlight()
            self.parent_textEdit.append(_("Annotation added at position: ") \
                + str(item['pos0']) + "-" + str(item['pos1']) + _(" for: ") + self.filename['name'])
        # if blank delete the annotation
        if item['memo'] == "":
            cur = self.settings['conn'].cursor()
            cur.execute("delete from annotation where pos0 = ?", (item['pos0'], ))
            self.settings['conn'].commit()
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
        dialog.setInputMode(QtWidgets.QInputDialog.TextInput)
        dialog.setLabelText(_("Autocode files with the current code for this text:") +"\n" + item.text(0))
        dialog.resize(200, 20)
        ok = dialog.exec_()
        if not ok:
            return
        findText = str(dialog.textValue())
        if findText == "" or findText is None:
            return
        ui = DialogSelectFile(self.filenames, _("Select file to view"), "many")
        ok = ui.exec_()
        if not ok:
            return
        files = ui.get_selected()
        if len(files) == 0:
            return
        filenames = ""
        for f in files:
            filenames += f['name'] + " "
            cur = self.settings['conn'].cursor()
            cur.execute("select name, id, fulltext, memo, owner, date from source where id=? and mediapath is Null",
                [f['id']])
            currentfile = cur.fetchone()
            text = currentfile[2]
            textStarts = [match.start() for match in re.finditer(re.escape(findText), text)]
            # add new items to database
            for startPos in textStarts:
                item = {'cid': cid, 'fid': int(f['id']), 'seltext': str(findText),
                'pos0': startPos, 'pos1': startPos + len(findText),
                'owner': self.settings['codername'], 'memo': "",
                'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                cur = self.settings['conn'].cursor()
                cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,\
                    owner,memo,date) values(?,?,?,?,?,?,?,?)"
                    , (item['cid'], item['fid'], item['seltext'], item['pos0'],
                    item['pos1'], item['owner'], item['memo'], item['date']))
                self.settings['conn'].commit()

                # if this is the currently open file update the code text list and GUI
                if f['id'] == self.filename['id']:
                    self.code_text.append(item)
            self.highlight()
            self.parent_textEdit.append(_("Automatic coding in files: ") + filenames \
                + _(". with text: ") + findText)
        # update filter for tooltip
        self.eventFilterTT.setCodes(self.code_text, self.codes)


class ToolTip_EventFilter(QtCore.QObject):
    """ Used to add a dynamic tooltip for the textEdit.
    The tool top text is changed according to its position in the text.
    If over a coded section the codename is displayed in the tooltip.
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

    def eventFilter(self, receiver, event):
        #QtGui.QToolTip.showText(QtGui.QCursor.pos(), tip)
        if event.type() == QtCore.QEvent.ToolTip:
            helpEvent = QHelpEvent(event)
            cursor = QtGui.QTextCursor()
            cursor = receiver.cursorForPosition(helpEvent.pos())
            pos = cursor.position()
            receiver.setToolTip("")
            displayText = ""
            # occasional None type error
            if self.code_text is None:
                #Call Base Class Method to Continue Normal Event Processing
                return super(ToolTip_EventFilter, self).eventFilter(receiver, event)
            for item in self.code_text:
                if item['pos0'] <= pos and item['pos1'] >= pos:
                    if displayText == "":
                        displayText = item['name']
                    else:  # can have multiple codes on same selected area
                        try:
                            displayText += "\n" + item['name']
                        except Exception as e:
                            msg = "Codes ToolTipEventFilter " + str(e) + ". Possible key error: "
                            msg += str(item) + "\n" + self.code_text
                            logger.error(msg)
            if displayText != "":
                receiver.setToolTip(displayText)

        #Call Base Class Method to Continue Normal Event Processing
        return super(ToolTip_EventFilter, self).eventFilter(receiver, event)
