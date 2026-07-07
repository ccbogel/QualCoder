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
https://qualcoder-org.github.io
https://qualcoder.wordpress.com/
https://qualcoder.org/
"""

import datetime
import logging
import os
import sqlite3
from random import randint

import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtWidgets import QDialog

from .add_item_name import DialogAddItemName
from .code_in_all_files import DialogCodeInAllFiles
from .color_selector import TextColor, colors
from .GUI.ui_dialog_organiser_assist import Ui_DialogOrganiserAssist
from .GUI.ui_dialog_organiser_assist_split import Ui_DialogOrganiserAssistSplit
from .helpers import DialogCodeInAV, DialogCodeInImage, DialogCodeInText, Message

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

# Tree item target kinds
KIND_NO_CATEGORY = "no_category"
KIND_CATEGORY = "category"
KIND_CODE = "code"


class CodeOrganiserAssist(QDialog):
    """
    Manually organise the codes system using selection lists
    """

    app = None
    parent_text_edit = None

    def __init__(self, app, parent_text_edit):
        super(CodeOrganiserAssist, self).__init__()
        self.app = app
        self.parent_text_edit = parent_text_edit
        QDialog.__init__(self)
        self.ui = Ui_DialogOrganiserAssist()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)

        self.codes = []
        self.categories = []
        self.code_freq = {}  # cid -> total codings across text, image and A/V
        self.temp_id = -1  # Negative ids for not yet saved codes and categories
        self.pending_segment_moves = []  # [{'new_cid': temp cid, 'code_text': [ctids], 'code_image': [imids], 'code_av': [avids]}]
        self.changed = False

        self.ui.pushButton_create_category.setIcon(qta.icon('mdi6.pencil-plus-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_create_category.pressed.connect(self.create_category)
        self.ui.pushButton_create_code.setIcon(qta.icon('mdi6.tag-plus-outline'))
        self.ui.pushButton_create_code.pressed.connect(self.create_code)
        self.ui.pushButton_split.setIcon(qta.icon('mdi6.call-split'))
        self.ui.pushButton_split.pressed.connect(self.split_item)
        self.ui.pushButton_undo.setIcon(qta.icon('mdi6.undo'))
        self.ui.pushButton_undo.pressed.connect(self.discard_changes)
        self.ui.pushButton_apply.pressed.connect(self.apply_changes)
        self.ui.pushButton_apply.setEnabled(False)
        self.ui.pushButton_remove.pressed.connect(self.remove_codes_from_container)
        self.ui.pushButton_add.pressed.connect(self.add_codes_to_container)
        # List filters, as in code text <- L style
        self.ui.pushButton_clear_filter_in.setIcon(qta.icon('mdi6.filter-off-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_clear_filter_in.pressed.connect(self.clear_filter_in)
        self.ui.pushButton_clear_filter_in.setToolTip(_("Clear filter"))
        self.ui.pushButton_clear_filter_in.setVisible(False)  # hidden until a filter is active
        self.ui.pushButton_clear_filter_out.setIcon(qta.icon('mdi6.filter-off-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_clear_filter_out.pressed.connect(self.clear_filter_out)
        self.ui.pushButton_clear_filter_out.setToolTip(_("Clear filter"))
        self.ui.pushButton_clear_filter_out.setVisible(False)  # hidden until a filter is active
        self.ui.lineEdit_filter_in.textChanged.connect(self.apply_filters)
        self.ui.lineEdit_filter_out.textChanged.connect(self.apply_filters)
        self.ui.treeWidget_categories.itemSelectionChanged.connect(self.fill_code_lists)
        # Right-click context menus: Show coded files, as in code text
        self.ui.treeWidget_categories.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.treeWidget_categories.customContextMenuRequested.connect(self.tree_context_menu)
        self.ui.listWidget_in.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.listWidget_in.customContextMenuRequested.connect(
            lambda position: self.list_context_menu(self.ui.listWidget_in, position))
        self.ui.listWidget_out.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.listWidget_out.customContextMenuRequested.connect(
            lambda position: self.list_context_menu(self.ui.listWidget_out, position))
        self.load_model()
        msg = _("BACK UP PROJECT before applying changes to the codes tree.\n"
                "Changes are only saved to the database when Apply is pressed.")
        self.parent_text_edit.append(_("Code organiser assist") + "\n" + msg)

    def load_model(self):
        """
        Load or reload codes and categories from the database.
        Discards any pending changes. Code frequencies are counted across
        coded text, image and A/V for all coders, as in code frequencies
        """

        self.codes, self.categories = self.app.get_codes_categories()
        self.code_freq = {}
        cur = self.app.conn.cursor()
        for table in ('code_text', 'code_image', 'code_av'):
            cur.execute(f"select cid, count(*) from {table} group by cid")  # noqa: S608 fixed table names
            for cid, count in cur.fetchall():
                self.code_freq[cid] = self.code_freq.get(cid, 0) + count
        self.pending_segment_moves = []
        self.temp_id = -1
        self.changed = False
        self.ui.pushButton_apply.setEnabled(False)
        self.fill_tree()

    def mark_changed(self):
        """
        Flag unsaved changes and enable Apply
        """

        self.changed = True
        self.ui.pushButton_apply.setEnabled(True)

    def discard_changes(self):
        """
        Discard pending changes and reload the codes tree from the
        database, after confirmation
        """

        if self.changed:
            reply = QtWidgets.QMessageBox.question(
                self, _("Discard changes"),
                _("Discard all pending changes and reload the codes tree?"),
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No)
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                return
        self.load_model()

    # hhelpers

    def category_name(self, catid):
        """
        Return the category name for a catid, or empty string. 
        """

        for category in self.categories:
            if category['catid'] == catid:
                return category['name']
        return ""

    def code_by_cid(self, cid):
        """
        Return the code dictionary for a cid, or None.
        """

        for code in self.codes:
            if code['cid'] == cid:
                return code
        return None

    def is_code_or_descendant(self, cid, target_cid):
        """
        True if target_cid is cid itself or a descendant sub-code of cid.
        Used to prevent sub-code cycles.
        Args:
            cid : Integer, potential ancestor code
            target_cid : Integer, the code that would become the parent
        """

        node = target_cid
        seen = set()
        while node is not None and node not in seen:
            if node == cid:
                return True
            seen.add(node)
            code = self.code_by_cid(node)
            node = code.get('supercid') if code else None
        return False

    def category_by_catid(self, catid):
        """
        Return the category dictionary for a catid, or None
        """

        for category in self.categories:
            if category['catid'] == catid:
                return category
        return None

    def is_category_or_descendant(self, catid, target_catid):
        """
        True if target_catid is catid itself or a descendant sub-category
        of catid. Used to prevent category cycles.
        Args:
            catid : Integer, potential ancestor category
            target_catid : Integer, the category that would become the parent
        """

        node = target_catid
        seen = set()
        while node is not None and node not in seen:
            if node == catid:
                return True
            seen.add(node)
            category = self.category_by_catid(node)
            node = category.get('supercatid') if category else None
        return False

    def branch_frequency(self, catid):
        """
        Total codings of all codes in a category branch, including codes
        in descendant sub-categories and their descendant sub-codes, as in
        the code frequencies report. Args: catid : Integer
        """

        return sum(self.code_freq.get(code['cid'], 0) for code in self.collect_branch_codes(catid))

    def no_category_frequency(self):
        """
        Total codings of uncategorised top level codes and their
        descendant sub-codes
        """

        branch_cids = [c['cid'] for c in self.codes if c['catid'] is None and c.get('supercid') is None]
        added = True
        while added:
            added = False
            for code in self.codes:
                if code.get('supercid') in branch_cids and code['cid'] not in branch_cids:
                    branch_cids.append(code['cid'])
                    added = True
        return sum(self.code_freq.get(cid, 0) for cid in branch_cids)

    # Tree of categories, codes and sub-codes

    def fill_tree(self):
        """
        Fill the tree: categories, sub-categories, codes and sub-codes.
        A first '(No category)' item groups uncategorised codes.
        The previous selection is preserved when possible. 
        """

        previous = self.selected_target()
        self.ui.treeWidget_categories.blockSignals(True)
        self.ui.treeWidget_categories.clear()
        no_cat_item = QtWidgets.QTreeWidgetItem([_("(No category)"), str(self.no_category_frequency())])
        no_cat_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, (KIND_NO_CATEGORY, None))
        no_cat_item.setTextAlignment(1, QtCore.Qt.AlignmentFlag.AlignRight)
        self.ui.treeWidget_categories.addTopLevelItem(no_cat_item)
        # Categories, parents before children
        remaining_categories = list(self.categories)
        category_items = {}
        for category in list(remaining_categories):
            if category['supercatid'] is None:
                item = self.make_category_item(category)
                self.ui.treeWidget_categories.addTopLevelItem(item)
                category_items[category['catid']] = item
                remaining_categories.remove(category)
        safety_count = 0
        while remaining_categories and safety_count < 100:
            safety_count += 1
            for category in list(remaining_categories):
                parent_item = category_items.get(category['supercatid'])
                if parent_item is not None:
                    item = self.make_category_item(category)
                    parent_item.addChild(item)
                    category_items[category['catid']] = item
                    remaining_categories.remove(category)
        # Codes, parent codes before their sub-codes
        remaining_codes = list(self.codes)
        code_items = {}
        for code in list(remaining_codes):
            if code.get('supercid') is None:
                item = self.make_code_item(code)
                if code['catid'] is not None and code['catid'] in category_items:
                    category_items[code['catid']].addChild(item)
                else:
                    no_cat_item.addChild(item)
                code_items[code['cid']] = item
                remaining_codes.remove(code)
        safety_count = 0
        while remaining_codes and safety_count < 100:
            safety_count += 1
            for code in list(remaining_codes):
                parent_item = code_items.get(code['supercid'])
                if parent_item is not None:
                    item = self.make_code_item(code)
                    parent_item.addChild(item)
                    code_items[code['cid']] = item
                    remaining_codes.remove(code)
        self.ui.treeWidget_categories.expandAll()
        self.ui.treeWidget_categories.resizeColumnToContents(0)
        self.ui.treeWidget_categories.resizeColumnToContents(1)
        self.ui.treeWidget_categories.blockSignals(False)
        # Restore previous selection, or default to '(No category)'
        item_to_select = no_cat_item
        if previous[0] == KIND_CATEGORY and previous[1] in category_items:
            item_to_select = category_items[previous[1]]
        if previous[0] == KIND_CODE and previous[1] in code_items:
            item_to_select = code_items[previous[1]]
        self.ui.treeWidget_categories.setCurrentItem(item_to_select)
        self.fill_code_lists()

    def make_category_item(self, category):
        """
        Build a tree item for a category, with the total codings of its
        branch in the Count column, as in the code frequencies report
        """

        item = QtWidgets.QTreeWidgetItem([category['name'] + (" *" if category['catid'] < 0 else ""),
                                          str(self.branch_frequency(category['catid']))])
        item.setData(0, QtCore.Qt.ItemDataRole.UserRole, (KIND_CATEGORY, category['catid']))
        item.setTextAlignment(1, QtCore.Qt.AlignmentFlag.AlignRight)
        return item

    def make_code_item(self, code):
        """
        Build a tree item for a code, coloured with the code colour,
        with its own total codings in the Count column
        """

        item = QtWidgets.QTreeWidgetItem([code['name'] + (" *" if code['cid'] < 0 else ""),
                                          str(self.code_freq.get(code['cid'], 0))])
        item.setData(0, QtCore.Qt.ItemDataRole.UserRole, (KIND_CODE, code['cid']))
        item.setTextAlignment(1, QtCore.Qt.AlignmentFlag.AlignRight)
        color = code.get('color')
        if color:
            item.setBackground(0, QtGui.QBrush(QtGui.QColor(color)))
            item.setForeground(0, QtGui.QBrush(QtGui.QColor(TextColor(color).recommendation)))
        return item

    def selected_target(self):
        """
        Return the selected tree target.
        Returns:
            kind String KIND_NO_CATEGORY / KIND_CATEGORY / KIND_CODE or None,
            id Integer catid or cid, or None
        """

        item = self.ui.treeWidget_categories.currentItem()
        if item is None:
            return None, None
        data = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if data is None:
            return None, None
        return data[0], data[1]

    # Code lists

    def fill_code_lists(self):
        """
        Fill the left list (items in the selected container) and the
        right list (items not in it). The container is a category, a code
        (whose sub-codes are managed), or '(No category)'.
        Codes are always listed. Categories are also listed as movable items
        when the container is a category or '(No category)', so category
        hierarchies can be re-organised with the same transfer buttons
        """

        self.ui.listWidget_in.clear()
        self.ui.listWidget_out.clear()
        kind, id_ = self.selected_target()
        if kind is None:
            self.ui.label_in.setText(_("Items in the selection"))
            self.ui.pushButton_remove.setEnabled(False)
            self.ui.pushButton_add.setEnabled(False)
            return
        self.ui.pushButton_add.setEnabled(True)
        # Removing an item from '(No category)' has no meaning
        self.ui.pushButton_remove.setEnabled(kind != KIND_NO_CATEGORY)
        if kind == KIND_NO_CATEGORY:
            self.ui.label_in.setText(_("Codes and categories without parent"))
        if kind == KIND_CATEGORY:
            self.ui.label_in.setText(_("In: ") + self.category_name(id_))
        if kind == KIND_CODE:
            code = self.code_by_cid(id_)
            self.ui.label_in.setText(_("Sub-codes of: ") + (code['name'] if code else ""))
        # Categories as movable items, except when a code is the container
        if kind in (KIND_NO_CATEGORY, KIND_CATEGORY):
            for category in self.categories:
                if kind == KIND_CATEGORY and category['catid'] == id_:
                    continue  # The selected category itself is not listed
                in_selection = False
                if kind == KIND_NO_CATEGORY:
                    in_selection = category['supercatid'] is None
                if kind == KIND_CATEGORY:
                    in_selection = category['supercatid'] == id_
                if in_selection:
                    self.add_category_list_item(self.ui.listWidget_in, category, show_location=False)
                else:
                    self.add_category_list_item(self.ui.listWidget_out, category, show_location=True)
        for code in self.codes:
            if kind == KIND_CODE and code['cid'] == id_:
                continue  # The parent code itself is not listed
            in_selection = False
            if kind == KIND_NO_CATEGORY:
                in_selection = code['catid'] is None and code.get('supercid') is None
            if kind == KIND_CATEGORY:
                in_selection = code['catid'] == id_
            if kind == KIND_CODE:
                in_selection = code.get('supercid') == id_
            if in_selection:
                self.add_code_list_item(self.ui.listWidget_in, code, show_location=False)
            else:
                self.add_code_list_item(self.ui.listWidget_out, code, show_location=True)
        self.apply_filters()

    def apply_filters(self):
        """
        Apply the name filters to both lists, hiding non-matching items.
        The clear filter button is shown and highlighted blue while a filter
        is active, as in code text. Filters persist across list refreshes.
        """

        self.apply_filter_to_list(self.ui.listWidget_in, self.ui.lineEdit_filter_in,
                                  self.ui.pushButton_clear_filter_in)
        self.apply_filter_to_list(self.ui.listWidget_out, self.ui.lineEdit_filter_out,
                                  self.ui.pushButton_clear_filter_out)

    @staticmethod
    def apply_filter_to_list(list_widget, line_edit, clear_button):
        """
        Hide list items not matching the filter text, case insensitive.
        Args:
            list_widget : QListWidget
            line_edit : QLineEdit with the filter text
            clear_button : QPushButton, shown blue while the filter is active
        """

        filter_text = line_edit.text().lower()
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            item.setHidden(filter_text != "" and filter_text not in item.text().lower())
        if filter_text == "":
            clear_button.setVisible(False)
            clear_button.setStyleSheet("")
        else:
            clear_button.setVisible(True)
            clear_button.setStyleSheet("background-color: #1e90ff; color: white;")  # blue

    def clear_filter_in(self):
        """
        Clear the left list filter and show all its items
        """

        self.ui.lineEdit_filter_in.setText("")

    def clear_filter_out(self):
        """
        Clear the right list filter and show all its items
        """

        self.ui.lineEdit_filter_out.setText("")

    # Context menus: Show coded files

    def tree_context_menu(self, position):
        """
        Right-click menu on the tree: Show coded files for a code or a
        category, as in code text. Args: position : QPoint
        """

        item = self.ui.treeWidget_categories.itemAt(position)
        if item is None:
            return
        kind, id_ = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if kind not in (KIND_CODE, KIND_CATEGORY):
            return
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_show_coded_files = menu.addAction(_("Show coded files"))
        action = menu.exec(self.ui.treeWidget_categories.viewport().mapToGlobal(position))
        if action == action_show_coded_files:
            item_kind = 'code' if kind == KIND_CODE else 'category'
            self.show_coded_files(item_kind, id_)

    def list_context_menu(self, list_widget, position):
        """
        Right-click menu on a bottom list: Show coded files for the
        clicked code or category. Args: list_widget : QListWidget, position : QPoint
        """

        item = list_widget.itemAt(position)
        if item is None:
            return
        item_kind, item_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_show_coded_files = menu.addAction(_("Show coded files"))
        action = menu.exec(list_widget.viewport().mapToGlobal(position))
        if action == action_show_coded_files:
            self.show_coded_files(item_kind, item_id)

    def collect_branch_codes(self, catid):
        """
        Collect all saved codes in a category branch: codes in the
        category and in all its descendant sub-categories, plus all their
        descendant sub-codes. Unsaved codes (negative cid) are excluded.
        Args: catid : Integer. Returns: List of code dictionaries
        """

        cat_ids = [catid]
        added = True
        while added:
            added = False
            for category in self.categories:
                if category['supercatid'] in cat_ids and category['catid'] not in cat_ids:
                    cat_ids.append(category['catid'])
                    added = True
        branch_codes = [c for c in self.codes if c['catid'] in cat_ids and c['cid'] > 0]
        branch_cids = [c['cid'] for c in branch_codes]
        added = True
        while added:
            added = False
            for code in self.codes:
                if code.get('supercid') in branch_cids and code['cid'] not in branch_cids and code['cid'] > 0:
                    branch_codes.append(code)
                    branch_cids.append(code['cid'])
                    added = True
        return branch_codes

    def show_coded_files(self, item_kind, item_id):
        """
        Open the coded files dialog, as in code text.
        A code shows all its coded media. A category shows the coded media
        of all codes in its branch.
        Args:
            item_kind : String 'code' or 'category'
            item_id : Integer cid or catid
        """

        if item_kind == 'code':
            code = self.code_by_cid(item_id)
            if code is None:
                return
            if code['cid'] < 0:
                Message(self.app, _("Show coded files"),
                        _("This code is not saved yet and has no coded files. Apply changes first.")).exec()
                return
            # DialogCodeInAllFiles execs itself in its constructor
            DialogCodeInAllFiles(self.app, code)
            return
        if item_kind == 'category':
            branch_codes = self.collect_branch_codes(item_id)
            if not branch_codes:
                Message(self.app, _("Show coded files"),
                        _("This category has no saved codes.")).exec()
                return
            # DialogCodeInAllFiles execs itself in its constructor
            DialogCodeInAllFiles(self.app, branch_codes, "File", self.category_name(item_id))

    def add_code_list_item(self, list_widget, code, show_location=False):
        """
        
        Add a code to a list widget, with its colour and current location.
        Args:
            list_widget : QListWidget
            code : Dictionary of code details
            show_location : Boolean, append current category or parent code name
        """

        text = code['name']
        if show_location:
            if code['catid'] is not None:
                text += "   [" + self.category_name(code['catid']) + "]"
            elif code.get('supercid') is not None:
                parent = self.code_by_cid(code['supercid'])
                if parent is not None:
                    text += "   [" + _("sub-code of ") + parent['name'] + "]"
        if code['cid'] < 0:
            text += " *"  # Not yet saved
        item = QtWidgets.QListWidgetItem(text)
        item.setData(QtCore.Qt.ItemDataRole.UserRole, ('code', code['cid']))
        color = code.get('color')
        if color:
            item.setBackground(QtGui.QBrush(QtGui.QColor(color)))
            item.setForeground(QtGui.QBrush(QtGui.QColor(TextColor(color).recommendation)))
        list_widget.addItem(item)

    def add_category_list_item(self, list_widget, category, show_location=False):
        """
        Add a category to a list widget, with its current parent category.
        Args:
            list_widget : QListWidget
            category : Dictionary of category details
            show_location : Boolean, append current parent category name
        """

        text = _("Category: ") + category['name']
        if show_location and category['supercatid'] is not None:
            text += "   [" + self.category_name(category['supercatid']) + "]"
        if category['catid'] < 0:
            text += " *"  # Not yet saved
        item = QtWidgets.QListWidgetItem(text)
        item.setData(QtCore.Qt.ItemDataRole.UserRole, ('category', category['catid']))
        list_widget.addItem(item)

    def remove_codes_from_container(self):
        """
        Move selected items in the left list out of the selected container.
        A code removed from a category becomes uncategorised. A sub-code
        removed from a code stops being a sub-code. A category removed from
        a category becomes top level. Model change only, applied on Apply
        """

        kind, id_ = self.selected_target()
        if kind not in (KIND_CATEGORY, KIND_CODE):
            return
        selected = self.ui.listWidget_in.selectedItems()
        if not selected:
            return
        for item in selected:
            item_kind, item_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if item_kind == 'code':
                code = self.code_by_cid(item_id)
                if code is None:
                    continue
                if kind == KIND_CATEGORY:
                    code['catid'] = None
                if kind == KIND_CODE:
                    code['supercid'] = None
            if item_kind == 'category' and kind == KIND_CATEGORY:
                category = self.category_by_catid(item_id)
                if category is not None:
                    category['supercatid'] = None
        self.mark_changed()
        self.fill_tree()

    def add_codes_to_container(self):
        """
        Move selected items in the right list into the selected container.
        Codes: into a category catid is set and supercid cleared; into a code
        the code becomes a sub-code; into '(No category)' both are cleared.
        Categories: into a category supercatid is set; into '(No category)'
        they become top level. Categories cannot be placed under codes.
        Cycles are prevented for both sub-codes and sub-categories.
        Model change only, applied on Apply. 
        """

        kind, id_ = self.selected_target()
        if kind is None:
            return
        selected = self.ui.listWidget_out.selectedItems()
        if not selected:
            return
        skipped_cycle = []
        skipped_invalid = []
        for item in selected:
            item_kind, item_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if item_kind == 'code':
                code = self.code_by_cid(item_id)
                if code is None:
                    continue
                if kind == KIND_NO_CATEGORY:
                    code['catid'] = None
                    code['supercid'] = None
                if kind == KIND_CATEGORY:
                    code['catid'] = id_
                    code['supercid'] = None
                if kind == KIND_CODE:
                    # Prevent self-parenting and cycles in the sub-code chain
                    if self.is_code_or_descendant(item_id, id_):
                        skipped_cycle.append(code['name'])
                        continue
                    code['supercid'] = id_
                    code['catid'] = None
            if item_kind == 'category':
                category = self.category_by_catid(item_id)
                if category is None:
                    continue
                if kind == KIND_CODE:
                    # A category cannot be placed under a code
                    skipped_invalid.append(category['name'])
                    continue
                if kind == KIND_NO_CATEGORY:
                    category['supercatid'] = None
                if kind == KIND_CATEGORY:
                    # Prevent self-parenting and cycles in the category chain
                    if self.is_category_or_descendant(item_id, id_):
                        skipped_cycle.append(category['name'])
                        continue
                    category['supercatid'] = id_
        self.mark_changed()
        self.fill_tree()
        if skipped_cycle:
            Message(self.app, _("Move items"),
                    _("Not moved, would create a circular chain:\n") + "\n".join(skipped_cycle),
                    "warning").exec()
        if skipped_invalid:
            Message(self.app, _("Move items"),
                    _("Categories cannot be placed under a code:\n") + "\n".join(skipped_invalid),
                    "warning").exec()

    # Create category and code

    def create_category(self):
        """
        Create a new category in the model. If a category is selected in
        the tree, the new category is created inside it. Applied on Apply
        """

        ui = DialogAddItemName(self.app, self.categories, _("Category"), _("Category name"))
        ui.exec()
        new_name = ui.get_new_name()
        if new_name is None:
            return
        kind, id_ = self.selected_target()
        supercatid = id_ if kind == KIND_CATEGORY else None
        category = {'name': new_name, 'catid': self.temp_id, 'supercatid': supercatid,
                    'memo': "", 'owner': self.app.settings['codername'],
                    'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
        self.temp_id -= 1
        self.categories.append(category)
        self.mark_changed()
        self.fill_tree()

    def create_code(self):
        """
        Create a new code in the model, placed in the selected category,
        or as a sub-code of the selected code. Applied on Apply
        """

        ui = DialogAddItemName(self.app, self.codes, _("Add new code"), _("Code name"))
        ui.exec()
        new_name = ui.get_new_name()
        if new_name is None:
            return
        kind, id_ = self.selected_target()
        catid = id_ if kind == KIND_CATEGORY else None
        supercid = id_ if kind == KIND_CODE else None
        code = {'name': new_name, 'cid': self.temp_id, 'catid': catid, 'supercid': supercid,
                'color': colors[randint(0, len(colors) - 1)], 'memo': "",
                'owner': self.app.settings['codername'],
                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
        self.temp_id -= 1
        self.codes.append(code)
        self.mark_changed()
        self.fill_tree()

    # Split code or category

    def split_item(self):
        """
        Split the selected code or category.
        An item selected in either bottom list has priority, then the tree
        selection: a code splits its coded segments, a category splits its
        child codes and sub-categories
        """

        selected = self.ui.listWidget_in.selectedItems() or self.ui.listWidget_out.selectedItems()
        if selected:
            item_kind, item_id = selected[0].data(QtCore.Qt.ItemDataRole.UserRole)
            if item_kind == 'code':
                self.split_code(self.code_by_cid(item_id))
                return
            if item_kind == 'category':
                self.split_category(item_id)
                return
        kind, id_ = self.selected_target()
        if kind == KIND_CODE:
            self.split_code(self.code_by_cid(id_))
            return
        if kind == KIND_CATEGORY:
            self.split_category(id_)
            return
        Message(self.app, _("Split"), _("Select a code or category in a list, or in the tree.")).exec()

    def split_code(self, code):
        """
        Split a code: divide its coded segments (text, image, A/V) between
        the original code and a new code. The new code is placed alongside the
        original (same category, or same parent code). Applied on Apply.
        Args:
            code : Dictionary of code details
        """

        if code is None:
            return
        if code['cid'] < 0:
            Message(self.app, _("Split code"),
                    _("This code is not saved yet and has no coded segments. Apply changes first.")).exec()
            return
        cur = self.app.conn.cursor()
        segments = []  # (table, id, display text, preview data dictionary)
        sql = "select code_text.ctid, source.name, code_text.pos0, code_text.pos1, code_text.seltext, " \
              "code_text.owner, source.id " \
              "from code_text join source on source.id = code_text.fid where code_text.cid=? order by source.name, pos0"
        cur.execute(sql, [code['cid']])
        for row in cur.fetchall():
            snippet = (row[4] or "").replace("\n", " ")
            if len(snippet) > 60:
                snippet = snippet[:60] + "..."
            display = _("Text: ") + f"{row[1]} [{row[2]}-{row[3]}] {snippet}"
            preview = {'codename': code['name'], 'color': code['color'], 'file_or_casename': row[1],
                       'pos0': row[2], 'pos1': row[3], 'text': row[4], 'coder': row[5], 'fid': row[6],
                       'file_or_case': 'File'}
            segments.append(('code_text', row[0], display, preview))
        sql = "select code_image.imid, source.name, code_image.x1, code_image.y1, code_image.width, " \
              "code_image.height, code_image.owner, source.mediapath, source.id, ifnull(code_image.memo,''), " \
              "code_image.pdf_page " \
              "from code_image join source on source.id = code_image.id where code_image.cid=? order by source.name"
        cur.execute(sql, [code['cid']])
        for row in cur.fetchall():
            display = _("Image: ") + f"{row[1]} (x:{row[2]}, y:{row[3]})"
            preview = {'codename': code['name'], 'color': code['color'], 'file_or_casename': row[1],
                       'x1': row[2], 'y1': row[3], 'width': row[4], 'height': row[5], 'coder': row[6],
                       'mediapath': row[7], 'fid': row[8], 'memo': row[9], 'pdf_page': row[10],
                       'file_or_case': 'File'}
            segments.append(('code_image', row[0], display, preview))
        sql = "select code_av.avid, source.name, code_av.pos0, code_av.pos1, code_av.owner, " \
              "source.mediapath, source.id, ifnull(code_av.memo,'') " \
              "from code_av join source on source.id = code_av.id where code_av.cid=? order by source.name, pos0"
        cur.execute(sql, [code['cid']])
        for row in cur.fetchall():
            display = _("A/V: ") + f"{row[1]} [{row[2]} - {row[3]} msecs]"
            preview = {'codename': code['name'], 'color': code['color'], 'file_or_casename': row[1],
                       'pos0': row[2], 'pos1': row[3], 'coder': row[4], 'text': '',
                       'mediapath': row[5], 'fid': row[6], 'memo': row[7], 'file_or_case': 'File'}
            segments.append(('code_av', row[0], display, preview))
        if not segments:
            Message(self.app, _("Split code"), _("This code has no coded segments to split.")).exec()
            return
        ui = DialogSplitItem(self.app, _("Split code: ") + code['name'], self.codes, segments)
        if ui.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        new_name, moved = ui.get_result()
        if new_name is None or not moved:
            return
        new_code = {'name': new_name, 'cid': self.temp_id, 'catid': code['catid'],
                    'supercid': code.get('supercid'),
                    'color': colors[randint(0, len(colors) - 1)], 'memo': "",
                    'owner': self.app.settings['codername'],
                    'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
        self.temp_id -= 1
        self.codes.append(new_code)
        move = {'new_cid': new_code['cid'], 'code_text': [], 'code_image': [], 'code_av': []}
        for item_tuple in moved:
            move[item_tuple[0]].append(item_tuple[1])
        self.pending_segment_moves.append(move)
        self.mark_changed()
        self.fill_tree()

    def split_category(self, catid):
        """
        Split a category: divide its child codes and sub-categories between
        the original category and a new category. Applied on Apply.
        Args:
            catid : Integer, the category to split
        """

        children = []  # ('code'/'category', id, display text, preview data)
        for code in self.codes:
            if code['catid'] == catid:
                children.append(('code', code['cid'], _("Code: ") + code['name'], code))
        for category in self.categories:
            if category['supercatid'] == catid:
                children.append(('category', category['catid'], _("Category: ") + category['name'], None))
        if not children:
            Message(self.app, _("Split category"),
                    _("This category has no codes or sub-categories to split.")).exec()
            return
        ui = DialogSplitItem(self.app, _("Split category: ") + self.category_name(catid),
                             self.categories, children)
        if ui.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        new_name, moved = ui.get_result()
        if new_name is None or not moved:
            return
        source = None
        for category in self.categories:
            if category['catid'] == catid:
                source = category
                break
        new_category = {'name': new_name, 'catid': self.temp_id,
                        'supercatid': source['supercatid'] if source else None,
                        'memo': "", 'owner': self.app.settings['codername'],
                        'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
        self.temp_id -= 1
        self.categories.append(new_category)
        for item_tuple in moved:
            kind, id_ = item_tuple[0], item_tuple[1]
            if kind == 'code':
                code = self.code_by_cid(id_)
                if code is not None:
                    code['catid'] = new_category['catid']
            else:
                for category in self.categories:
                    if category['catid'] == id_:
                        category['supercatid'] = new_category['catid']
        self.mark_changed()
        self.fill_tree()

    # Apply

    def apply_changes(self):
        """
        Apply all pending model changes to the database:
        insert new categories and codes (parents before children so temporary
        negative ids can be resolved), update code catids and supercids,
        update category supercatids, move coded segments from split codes,
        then repair any dangling references. Asks for confirmation first,
        to avoid accidental changes
        """

        new_category_count = len([c for c in self.categories if c['catid'] < 0])
        new_code_count = len([c for c in self.codes if c['cid'] < 0])
        segment_move_count = sum(len(m['code_text']) + len(m['code_image']) + len(m['code_av'])
                                 for m in self.pending_segment_moves)
        msg = _("Apply all pending changes to the codes tree?") + "\n\n"
        msg += _("New categories: ") + str(new_category_count) + "\n"
        msg += _("New codes: ") + str(new_code_count) + "\n"
        msg += _("Coded segments moved by splits: ") + str(segment_move_count) + "\n\n"
        msg += _("This will modify the project database.")
        reply = QtWidgets.QMessageBox.question(
            self, _("Apply changes"), msg,
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No)
        if reply == QtWidgets.QMessageBox.StandardButton.No:
            return
        cur = self.app.conn.cursor()
        catid_map = {}  # temp negative catid -> database catid
        cid_map = {}  # temp negative cid -> database cid
        # Insert new categories, parents before children
        new_categories = [c for c in self.categories if c['catid'] < 0]
        safety_count = 0
        while new_categories and safety_count < 100:
            safety_count += 1
            for category in list(new_categories):
                supercatid = category['supercatid']
                if supercatid is not None and supercatid < 0:
                    if supercatid not in catid_map:
                        continue  # Parent not inserted yet
                    supercatid = catid_map[supercatid]
                try:
                    cur.execute("insert into code_cat (name, memo, owner, date, supercatid) values(?,?,?,?,?)",
                                (category['name'], category['memo'], category['owner'], category['date'], supercatid))
                    self.app.conn.commit()
                    cur.execute("select last_insert_rowid()")
                    catid_map[category['catid']] = cur.fetchone()[0]
                except sqlite3.IntegrityError as err:
                    logger.debug("%s %s", err, category['name'])
                    catid_map[category['catid']] = None
                new_categories.remove(category)
        # Insert new codes, parent codes before their sub-codes
        new_codes = [c for c in self.codes if c['cid'] < 0]
        safety_count = 0
        while new_codes and safety_count < 100:
            safety_count += 1
            for code in list(new_codes):
                supercid = code.get('supercid')
                if supercid is not None and supercid < 0:
                    if supercid not in cid_map:
                        continue  # Parent code not inserted yet
                    supercid = cid_map[supercid]
                catid = code['catid']
                if catid is not None and catid < 0:
                    catid = catid_map.get(catid)
                if supercid is not None:
                    catid = None  # A sub-code never belongs to a category as well
                try:
                    cur.execute("insert into code_name (name,memo,owner,date,catid,color,supercid) "
                                "values(?,?,?,?,?,?,?)",
                                (code['name'], code['memo'], code['owner'], code['date'], catid,
                                 code['color'], supercid))
                    self.app.conn.commit()
                    cur.execute("select last_insert_rowid()")
                    cid_map[code['cid']] = cur.fetchone()[0]
                except sqlite3.IntegrityError as err:
                    logger.debug("%s %s", err, code['name'])
                    cid_map[code['cid']] = None
                new_codes.remove(code)
        # Update pre-existing categories: supercatid may point to a new category
        for category in self.categories:
            if category['catid'] > 0:
                supercatid = category['supercatid']
                if supercatid is not None and supercatid < 0:
                    supercatid = catid_map.get(supercatid)
                cur.execute("update code_cat set supercatid=? where catid=?", [supercatid, category['catid']])
        self.app.conn.commit()
        # Update pre-existing codes: catid and supercid from the model,
        # resolving references to newly inserted items
        for code in self.codes:
            if code['cid'] > 0:
                catid = code['catid']
                if catid is not None and catid < 0:
                    catid = catid_map.get(catid)
                supercid = code.get('supercid')
                if supercid is not None and supercid < 0:
                    supercid = cid_map.get(supercid)
                if supercid is not None:
                    catid = None  # Mutual exclusivity, supercid wins
                cur.execute("update code_name set catid=?, supercid=? where cid=?",
                            [catid, supercid, code['cid']])
        self.app.conn.commit()
        # Move coded segments for split codes
        for move in self.pending_segment_moves:
            new_cid = cid_map.get(move['new_cid'])
            if new_cid is None:
                continue
            for ctid in move['code_text']:
                try:
                    cur.execute("update code_text set cid=? where ctid=?", [new_cid, ctid])
                except sqlite3.IntegrityError:
                    cur.execute("delete from code_text where ctid=?", [ctid])
            for imid in move['code_image']:
                try:
                    cur.execute("update code_image set cid=? where imid=?", [new_cid, imid])
                except sqlite3.IntegrityError:
                    cur.execute("delete from code_image where imid=?", [imid])
            for avid in move['code_av']:
                try:
                    cur.execute("update code_av set cid=? where avid=?", [new_cid, avid])
                except sqlite3.IntegrityError:
                    cur.execute("delete from code_av where avid=?", [avid])
        self.app.conn.commit()
        # Repair dangling references, mirrors code_organiser
        cur.execute("update code_cat set supercatid=null where supercatid is not null and supercatid not in "
                    "(select catid from code_cat)")
        cur.execute("update code_name set supercid=null where supercid is not null and supercid not in "
                    "(select cid from code_name)")
        cur.execute("update code_name set catid=null where supercid is not null and catid is not null")
        self.app.conn.commit()
        # Break any sub-code cycles, mirrors code_organiser
        cur.execute("select cid, supercid from code_name")
        code_parent = {row[0]: row[1] for row in cur.fetchall()}
        for start in list(code_parent.keys()):
            seen = set()
            node = start
            while node is not None and node in code_parent:
                if node in seen:
                    cur.execute("update code_name set supercid=null where cid=?", [node])
                    code_parent[node] = None
                    break
                seen.add(node)
                node = code_parent[node]
        self.app.conn.commit()
        # Wrap up
        self.app.delete_backup = False
        self.parent_text_edit.append(_("Code tree re-organised."))
        Message(self.app, _("Code organiser assist"), _("Changes applied to the codes tree")).exec()
        self.load_model()

    def reject(self):
        """
        Confirm before discarding unsaved changes
        """

        if self.changed:
            reply = QtWidgets.QMessageBox.question(
                self, _("Unsaved changes"),
                _("There are unsaved changes. Close without applying them?"),
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No)
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                return
        super().reject()


class DialogSplitItem(QDialog):
    """
    Popup dialog to split a code or a category.
    Shows a name field for the new item, and two lists: what stays in the
    original (left) and what moves to the new item (right), with > and <
    buttons to move the selection between lists
    """

    def __init__(self, app, title, existing_items, items, parent=None):
        """ 
        Args:
            app : App class
            title : String, window title including the source name
            existing_items : List of dictionaries with 'name' key, to avoid duplicates
            items : List of tuples (kind_or_table, id, display text, preview data)
        """

        super(DialogSplitItem, self).__init__(parent)
        self.app = app
        self.existing_names = [i['name'] for i in existing_items]
        QDialog.__init__(self)
        self.ui = Ui_DialogOrganiserAssistSplit()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet(f"* {{font-size:{app.settings['fontsize']}pt}} ")
        self.setWindowTitle(title)
        self.ui.label_source.setText(title)
        self.ui.pushButton_move.pressed.connect(self.move_to_new)
        self.ui.pushButton_keep.pressed.connect(self.keep_in_original)
        self.ui.pushButton_preview.setIcon(qta.icon('mdi6.eye-outline'))
        self.ui.pushButton_preview.pressed.connect(self.preview_selected)
        self.ui.listWidget_keep.itemDoubleClicked.connect(self.preview_item)
        self.ui.listWidget_move.itemDoubleClicked.connect(self.preview_item)
        for item_tuple in items:
            list_item = QtWidgets.QListWidgetItem(item_tuple[2])
            list_item.setData(QtCore.Qt.ItemDataRole.UserRole, item_tuple)
            self.ui.listWidget_keep.addItem(list_item)

    def preview_selected(self):
        """
        Preview the selected item in either list, in contexto
        """

        selected = self.ui.listWidget_keep.selectedItems() or self.ui.listWidget_move.selectedItems()
        if not selected:
            Message(self.app, _("View in context"), _("Select an item to preview.")).exec()
            return
        self.preview_item(selected[0])

    def preview_item(self, list_item):
        """
        Open the view-in-context dialog for a list item.
        Coded text, image and A/V segments open in their context dialogs.
        A code opens all its coded media (as in 'view coded media').
        Args:
            list_item : QListWidgetItem
        """

        item_tuple = list_item.data(QtCore.Qt.ItemDataRole.UserRole)
        kind = item_tuple[0]
        preview = item_tuple[3] if len(item_tuple) > 3 else None
        if preview is None and kind != 'category':
            return
        if kind == 'code_text':
            ui = DialogCodeInText(self.app, preview)
            ui.exec()
            return
        if kind == 'code_image':
            if not preview.get('mediapath'):
                Message(self.app, _("View in context"), _("Media file not found.")).exec()
                return
            ui = DialogCodeInImage(self.app, preview)
            ui.exec()
            return
        if kind == 'code_av':
            if not preview.get('mediapath'):
                Message(self.app, _("View in context"), _("Media file not found.")).exec()
                return
            ui = DialogCodeInAV(self.app, preview)
            ui.exec()
            return
        if kind == 'code':
            # DialogCodeInAllFiles execs itself in its constructor
            DialogCodeInAllFiles(self.app, preview)
            return
        Message(self.app, _("View in context"),
                _("Preview is available for codes and coded segments, not for categories.")).exec()

    def move_to_new(self):
        """
        Move selected items from the keep list to the move list
        """

        for item in self.ui.listWidget_keep.selectedItems():
            row = self.ui.listWidget_keep.row(item)
            self.ui.listWidget_move.addItem(self.ui.listWidget_keep.takeItem(row))

    def keep_in_original(self):
        """
        Move selected items from the move list back to the keep list
        """

        for item in self.ui.listWidget_move.selectedItems():
            row = self.ui.listWidget_move.row(item)
            self.ui.listWidget_keep.addItem(self.ui.listWidget_move.takeItem(row))

    def accept(self):
        """
        Validate the new name and that something is moved
        """

        new_name = self.ui.lineEdit_new_name.text().strip()
        if new_name == "":
            Message(self.app, _("Split"), _("Enter a name for the new item.")).exec() # Falta añadir diferenciador entre categoría o código
            return
        if new_name in self.existing_names:
            Message(self.app, _("Split"), _("This name already exists. Choose another name.")).exec()
            return
        if self.ui.listWidget_move.count() == 0:
            Message(self.app, _("Split"), _("Move at least one item to the new item.")).exec() # Falta añadir diferenciador entre categoría o código
            return
        super().accept()

    def get_result(self):
        """ 
        Returns:
            new name String or None, list of moved item tuples (kind_or_table, id, display text, preview data) 
        """

        new_name = self.ui.lineEdit_new_name.text().strip()
        if new_name == "":
            return None, []
        moved = []
        for i in range(self.ui.listWidget_move.count()):
            moved.append(self.ui.listWidget_move.item(i).data(QtCore.Qt.ItemDataRole.UserRole))
        return new_name, moved
