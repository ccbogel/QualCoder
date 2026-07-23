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
https://qualcoder-org.github.io
https://qualcoder.org/
"""

from copy import deepcopy
import datetime
import logging
from random import randint
import sqlite3

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor

from .add_item_name import DialogAddItemName
from .color_selector import DialogColorSelect, colors, TextColor
from .confirm_delete import DialogConfirmDelete
from .helpers import Message, restore_persistent_tree_widths
from .memo import DialogMemo
from .select_items import DialogSelectItems

logger = logging.getLogger(__name__)


class CodeTreeController(QtCore.QObject):
    """ Owns the shared behaviour of a codes treeWidget for a coding dialog.
    Host protocol:
    The host dialog must provide: codes (list of dict), categories (list of dict)
    and parent_textEdit. Both lists are read live, never cached here.
    Optional callbacks, set after construction:
        fill_counts_callback() - fill the Count column after fill_tree
        coded_files_callback(code_or_codes, title) - one code dict, or a list for a category branch
        find_code_callback(), show_codes_like_callback(), show_codes_of_colour_callback()
        on_codes_deleted(cids), on_code_renamed(old_name, new_name) - host cache cleanup
    Signals:
        menu_requested(menu, selected_item) - emitted before the context menu is shown
        codes_changed(list_of_table_names) - emitted after every database change
    """

    # Built QMenu and selected QTreeWidgetItem (or None), emitted before menu.exec
    menu_requested = QtCore.pyqtSignal(object, object)
    # List of changed database table names, emitted after every database change
    codes_changed = QtCore.pyqtSignal(list)

    def __init__(self, app, tree_widget: QtWidgets.QTreeWidget, host,
                 column_width_factors: dict | None = None):
        """
        Args:
            app: App object
            tree_widget: the QTreeWidget the dialog already owns (from its .ui)
            host: the coding dialog, see the host protocol in the class docstring
            column_width_factors: Dictionary or None, passed to restore_persistent_tree_widths
        """

        super().__init__(tree_widget)
        self.app = app
        self.tree = tree_widget
        self.host = host
        self.tree_sort_option = "all asc"  # all asc, all desc, cat and code asc
        self.column_width_factors = column_width_factors if column_width_factors is not None \
            else {0: 0.70, 2: 0.15, 3: 0.15}
        # Optional host callbacks, see class docstring
        self.fill_counts_callback = None
        self.coded_files_callback = None
        self.find_code_callback = None
        self.show_codes_like_callback = None
        self.show_codes_of_colour_callback = None
        self.on_codes_deleted = None
        self.on_code_renamed = None

    # Live views over the host's data, never cached here.
    @property
    def codes(self) -> list:
        return self.host.codes

    @property
    def categories(self) -> list:
        return self.host.categories

    @property
    def parent_textEdit(self):
        return self.host.parent_textEdit

    # tree fill

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes.
        The Count column is filled by the host through fill_counts_callback.
        Keep record of non-expanded items, then re-enact these items when tree fill is called again. """

        cats = deepcopy(self.categories)
        codes = deepcopy(self.codes)
        self.tree.clear()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels([_("Name"), _("Id"), _("Memo"), _("Count")])
        if not self.app.settings['showids']:
            self.tree.setColumnHidden(1, True)
        else:
            self.tree.setColumnHidden(1, False)

        # Add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                memo = ""
                if c['memo'] != "":
                    memo = _("Memo")
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                top_item.setToolTip(2, c['memo'])
                top_item.setToolTip(0, '')
                if len(c['name']) > 52:
                    top_item.setText(0, f"{c['name'][:25]}..{c['name'][-25:]}")
                    top_item.setToolTip(0, c['name'])
                self.tree.addTopLevelItem(top_item)
                if f"catid:{c['catid']}" in self.app.collapsed_categories:
                    top_item.setExpanded(False)
                else:
                    top_item.setExpanded(True)
                remove_list.append(c)
        for item in remove_list:
            cats.remove(item)
        ''' Add child categories: place each category under its parent. Break when no progress
         is made (a cycle or a dangling supercatid), then place any leftovers at top level so a
         category branch is never lost or hidden because of corruption. '''
        count = 0
        while cats and count < 10000:
            remove_list = []
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.tree)
                item = it.value()
                count2 = 0
                while item and count2 < 10000:  # while there is an item in the list
                    if item.text(1) == f"catid:{c['supercatid']}":
                        memo = ""
                        if c['memo'] != "":
                            memo = _("Memo")
                        child = QtWidgets.QTreeWidgetItem([c['name'], f"catid:{c['catid']}", memo])
                        child.setToolTip(2, c['memo'])
                        child.setToolTip(0, '')
                        if len(c['name']) > 52:
                            child.setText(0, f"{c['name'][:25]}..{c['name'][-25:]}")
                            child.setToolTip(0, c['name'])
                        item.addChild(child)
                        if f"catid:{c['catid']}" in self.app.collapsed_categories:
                            child.setExpanded(False)
                        else:
                            child.setExpanded(True)
                        remove_list.append(c)
                        break
                    it += 1
                    item = it.value()
                    count2 += 1
            if not remove_list:
                break  # cycle or dangling parent: remaining categories placed at top level below
            for item in remove_list:
                cats.remove(item)
            count += 1
        # Fallback: never lose a category. Any with a missing/cyclic parent goes to top level.
        for c in cats:
            memo = _("Memo") if c['memo'] != "" else ""
            top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
            top_item.setToolTip(2, c['memo'])
            top_item.setToolTip(0, '')
            if len(c['name']) > 52:
                top_item.setText(0, f"{c['name'][:25]}..{c['name'][-25:]}")
                top_item.setToolTip(0, c['name'])
            self.tree.addTopLevelItem(top_item)
        # Add codes, with sub-code nesting. A code is top level only when it has neither a
        # parent category (catid) nor a parent code (supercid). The rest are nested under
        # their category (catid:) or under their parent code (cid:).

        def _make_code_item(code_dict):
            """ Build a styled tree item for a code. Sub-codes share this styling. """
            memo_ = _("Memo") if code_dict['memo'] != "" else ""
            code_item = QtWidgets.QTreeWidgetItem([code_dict['name'], f"cid:{code_dict['cid']}", memo_])
            code_item.setToolTip(2, code_dict['memo'])
            code_item.setToolTip(0, '')
            if len(code_dict['name']) > 52:
                code_item.setText(0, f"{code_dict['name'][:25]}..{code_dict['name'][-25:]}")
                code_item.setToolTip(0, code_dict['name'])
            code_item.setBackground(0, QBrush(QColor(code_dict['color']), Qt.BrushStyle.SolidPattern))
            code_item.setForeground(0, QBrush(QColor(TextColor(code_dict['color']).recommendation)))
            code_item.setFlags(
                Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable |
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled)
            return code_item

        # Index every node already in the tree (categories) by its id text for O(1) lookup.
        node_index = {}
        it = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while it.value():
            node_index[it.value().text(1)] = it.value()
            it += 1
        # Top level codes: no category and no parent code.
        remove_items = []
        for c in codes:
            if c['catid'] is None and c.get('supercid') is None:
                node = _make_code_item(c)
                self.tree.addTopLevelItem(node)
                node_index[f"cid:{c['cid']}"] = node
                remove_items.append(c)
        for c in remove_items:
            codes.remove(c)
        # Remaining codes: nest under category or parent code. Iterate because a parent code
        # may itself be a not-yet-placed sub-code. Each pass places every code whose parent
        # already exists; the loop ends when all are placed or no further progress is possible.
        count = 0
        while codes and count < 10000:
            remove_items = []
            for c in codes:
                if c.get('supercid') is not None:
                    parent_key = f"cid:{c['supercid']}"
                else:
                    parent_key = f"catid:{c['catid']}"
                parent_node = node_index.get(parent_key)
                if parent_node is not None:
                    node = _make_code_item(c)
                    parent_node.addChild(node)
                    node_index[f"cid:{c['cid']}"] = node
                    remove_items.append(c)
            if not remove_items:
                break  # remaining codes have a missing/cyclic parent: placed at top level below
            for c in remove_items:
                codes.remove(c)
            count += 1
        # Fallback: never lose a code. Any code with a dangling parent goes to top level.
        for c in codes:
            node = _make_code_item(c)
            self.tree.addTopLevelItem(node)
            node_index[f"cid:{c['cid']}"] = node

        if self.tree_sort_option == "all asc":
            self.tree.sortByColumn(0, QtCore.Qt.SortOrder.AscendingOrder)
        if self.tree_sort_option == "all desc":
            self.tree.sortByColumn(0, QtCore.Qt.SortOrder.DescendingOrder)
        # Show the code tree expanded from the start: sub-code branches are visible by default;
        # categories the user had collapsed are restored to their collapsed state.
        self.tree.expandAll()
        it = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while it.value():
            node = it.value()
            if node.text(1) in self.app.collapsed_categories:
                node.setExpanded(False)
            it += 1
        if self.fill_counts_callback is not None:
            self.fill_counts_callback()
        restore_persistent_tree_widths(
            self.tree,
            default_width_factors=self.column_width_factors
        )

    # context menu

    def tree_menu(self, position):
        """
        Context menu for treewidget code/category items.
        Add, rename, memo, move or delete code or category. Change code color.
        Emits menu_requested(menu, selected) before showing, so the host dialog
        can append its own page-specific entries.
        """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        selected = self.tree.currentItem()
        action_add_code_to_category = None
        action_add_category_to_category = None
        action_expand_collapse = None
        if selected is not None and selected.text(1)[0:3] == 'cat':
            action_add_code_to_category = menu.addAction(_("Add new code to category"))
            action_add_category_to_category = menu.addAction(_("Add a new category to category"))
        action_add_code = menu.addAction(_("Add a new code"))
        action_add_category = menu.addAction(_("Add a new category"))
        action_add_subcode = None
        if selected is not None and selected.text(1)[0:3] == 'cid':
            action_add_subcode = menu.addAction(_("Add a new sub-code to code"))
        action_cat_show_coded_files = None
        if selected is not None and selected.text(1)[0:3] == 'cat':
            action_expand_collapse = menu.addAction(_("Expand or collapse branch"))
            if self.coded_files_callback is not None:
                action_cat_show_coded_files = menu.addAction(_("Show coded files"))
        if selected is not None and selected.text(1)[0:3] == 'cid' and selected.childCount() > 0:
            action_expand_collapse = menu.addAction(_("Expand or collapse branch"))
        modify_menu = menu.addMenu(_("Modify"))
        action_rename = modify_menu.addAction(_("Rename F2"))
        action_edit_memo = modify_menu.addAction(_("View or edit memo F3"))
        action_merge_category = None
        action_move_category = None
        if selected is not None and selected.text(1)[0:3] == 'cat':
            action_merge_category = modify_menu.addAction(_("Merge category into category"))
            action_move_category = modify_menu.addAction(_("Move category under category F6"))
        action_delete = None
        if selected is not None and selected.text(1)[0:3] == 'cid':
            action_delete = modify_menu.addAction(_("Delete F4"))
        action_delete_branch = None
        if selected is not None and selected.text(1)[0:3] == 'cat':
            # Cascade deletion of the whole branch, only offered for categories.
            action_delete_branch = modify_menu.addAction(_("Delete category branch F4"))
        action_color = None
        action_show_coded_media = None
        action_move_code = None
        action_move_multi_codes = None
        action_merge_code_into_code = None
        if selected is not None and selected.text(1)[0:3] == 'cid':
            action_color = modify_menu.addAction(_("Change code color F5"))
            if self.coded_files_callback is not None:
                action_show_coded_media = menu.addAction(_("Show coded files"))
            action_move_code = modify_menu.addAction(_("Move code to F6"))
            action_move_multi_codes = modify_menu.addAction(_("Move multiple codes"))
            action_merge_code_into_code = modify_menu.addAction(_("Merge code into code"))
        action_find_code = None
        if self.find_code_callback is not None:
            action_find_code = menu.addAction(_("Find code"))
        action_show_codes_like = None
        action_show_codes_colour = None
        if self.show_codes_like_callback is not None or self.show_codes_of_colour_callback is not None:
            filter_menu = menu.addMenu(_("Filter"))
            if self.show_codes_like_callback is not None:
                like_filter = getattr(self.host, 'show_codes_like_filter', "")
                action_show_codes_like = filter_menu.addAction(_("Show codes like") + ": " + like_filter)
            if self.show_codes_of_colour_callback is not None:
                colour_filter = getattr(self.host, 'show_codes_colour_filter', "")
                action_show_codes_colour = filter_menu.addAction(_("Show codes of colour") + f": {colour_filter}")
        sort_menu = menu.addMenu(_("Sort"))
        action_all_asc = sort_menu.addAction(_("Sort ascending"))
        action_all_desc = sort_menu.addAction(_("Sort descending"))
        action_cat_then_code_asc = sort_menu.addAction(_("Sort category then code ascending"))

        # Let the host dialog add its own entries before the menu is shown.
        self.menu_requested.emit(menu, selected)

        action = menu.exec(self.tree.mapToGlobal(position))
        if action is None:
            return
        if action == action_all_asc:
            self.tree_sort_option = "all asc"
            self.fill_tree()
            return
        if action == action_all_desc:
            self.tree_sort_option = "all desc"
            self.fill_tree()
            return
        if action == action_cat_then_code_asc:
            self.tree_sort_option = "cat and code asc"
            self.fill_tree()
            return
        if action == action_show_codes_like:
            self.show_codes_like_callback()
            return
        if action == action_show_codes_colour:
            self.show_codes_of_colour_callback()
            return
        if action == action_find_code:
            self.find_code_callback()
            return
        if selected is not None and action == action_color:
            self.change_code_color(selected)
        if action == action_add_category:
            self.add_category()
            return
        if action == action_add_code:
            self.add_code()
            return
        if action == action_merge_category:
            catid = int(selected.text(1).split(":")[1])
            self.merge_category(catid)
            return
        if action == action_move_category:
            catid = int(selected.text(1).split(":")[1])
            self.move_category(catid)
            return
        if action == action_add_code_to_category:
            catid = int(selected.text(1).split(":")[1])
            self.add_code(catid)
            return
        if action == action_add_subcode and selected is not None:
            supercid = int(selected.text(1).split(":")[1])
            self.add_code(supercid=supercid)
            return
        if action == action_add_category_to_category:
            catid = int(selected.text(1).split(":")[1])
            self.add_category(catid)
            return
        if selected is not None and action == action_move_code:
            self.move_code(selected)
            return
        if action == action_move_multi_codes:
            self.move_multiple_codes()
            return
        if action == action_merge_code_into_code and selected is not None:
            self.merge_code_into_code(selected)
            return
        if action == action_expand_collapse:
            expand_toggle = not selected.isExpanded()
            self.recursive_expand_collapse_branch(selected, expand_toggle)
            return
        if selected is not None and action == action_rename:
            self.rename_category_or_code(selected)
        if selected is not None and action == action_edit_memo:
            self.add_edit_cat_or_code_memo(selected)
        if selected is not None and action == action_delete:
            self.delete_code(selected)
        if selected is not None and action == action_delete_branch:
            self.delete_category_branch(selected)
            return  # Avoid error as selected is now None
        if action == action_cat_show_coded_files:
            branch_codes = self.recursive_get_branch_codes(selected, [])
            self.coded_files_callback(branch_codes, selected.text(0))
            return
        if selected is not None and action == action_show_coded_media:
            to_find = int(selected.text(1)[4:])
            found = next((code for code in self.codes if code['cid'] == to_find), None)
            if found:
                self.coded_files_callback(found, "")

    # keyboard and drag/drop

    def handle_key_press(self, event) -> bool:
        """
        Tree widget menu item keys F2 - F6. Called from the host keyPressEvent
        when the treeWidget has focus. Returns True when the key was handled.
        Args:
            event: QKeyEvent
        """

        selected = self.tree.currentItem()
        if selected is None:
            return False
        key = event.key()
        if key == QtCore.Qt.Key.Key_F2:
            self.rename_category_or_code(selected)
            return True
        if key == QtCore.Qt.Key.Key_F3:
            self.add_edit_cat_or_code_memo(selected)
            return True
        if key == QtCore.Qt.Key.Key_F4:
            if selected.text(1)[0:3] == 'cat':
                self.delete_category_branch(selected)
            else:
                self.delete_code(selected)
            return True
        if key == QtCore.Qt.Key.Key_F5 and selected.text(1)[0:3] == 'cid':
            self.change_code_color(selected)
            return True
        if key == QtCore.Qt.Key.Key_F6:
            if selected.text(1)[0:3] == 'cat':
                self.move_category(int(selected.text(1).split(":")[1]))
            else:
                self.move_code(selected)
            return True
        return False

    def handle_tree_viewport_event(self, event) -> bool:
        """
        Drop and DragMove handling for the treeWidget viewport. Available for hosts
        that prefer delegating the whole viewport branch of their eventFilter.
        Args:
            event: QEvent
        Returns:
            True when the event was consumed
        """

        if event.type() == QtCore.QEvent.Type.Drop:
            item = self.tree.currentItem()
            # event position is QPointF, itemAt requires toPoint
            parent = self.tree.itemAt(event.position().toPoint())
            self.item_moved_update_data(item, parent)
            return True
        # Scroll the tree when the dragged item is at the top or bottom edges
        if event.type() == QtCore.QEvent.Type.DragMove:
            vsb = self.tree.verticalScrollBar()
            top = self.tree.visualRect(self.tree.indexAt(self.tree.rect().topLeft())).bottom()
            bottom = self.tree.viewport().height()
            y = event.position().toPoint().y()
            if y < top + 8:  # Margin of 8
                vsb.setValue(vsb.value() - 1)
            if y > bottom - 8:  # Margin of 8
                vsb.setValue(vsb.value() + 1)
            return True
        return False

    def item_moved_update_data(self, item: QtWidgets.QTreeWidgetItem, parent: QtWidgets.QTreeWidgetItem):
        """
        Called from drop event in treeWidget view port.
        Identify code or category to move.
        Also merge codes if one code is dropped on another code with Ctrl held.
        Args:
            item : QTreeWidgetItem
            parent : QTreeWidgetItem
        """

        if item is None:
            return
        # Find the category in the list
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
                    # Parent is a code, a category cannot nest under a code.
                    return
                supercatid = int(parent.text(1).split(':')[1])
                if supercatid == self.categories[found]['catid']:
                    # Cannot be its own parent.
                    return
                # Guard against cycles: moving a category under one of its own sub-categories
                # would make the branch disappear and corrupt the tree.
                if self.category_is_descendant(supercatid, self.categories[found]['catid']):
                    Message(self.app, _("Cannot move category"),
                            _("Cannot move a category under one of its own sub-categories.")).exec()
                    return
                self.categories[found]['supercatid'] = supercatid
            cur = self.app.conn.cursor()
            cur.execute("update code_cat set supercatid=? where catid=?",
                        [self.categories[found]['supercatid'], self.categories[found]['catid']])
            self.app.conn.commit()
            self.app.delete_backup = False
            self.codes_changed.emit(["code_cat"])
            return

        # Find the code in the list
        if item.text(1)[0:3] == 'cid':
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(item.text(1)[4:]):
                    found = i
            if found == -1:
                return
            if parent is None:
                # Move code to top level: clear both parents.
                self.codes[found]['catid'] = None
                self.codes[found]['supercid'] = None
            else:
                if parent.text(1).split(':')[0] == 'cid':
                    parent_cid = int(parent.text(1).split(':')[1])
                    # Ctrl held while dropping a code on a code merges (previous behaviour);
                    # otherwise the code is nested as a sub-code.
                    ctrl = bool(QtWidgets.QApplication.keyboardModifiers() &
                                QtCore.Qt.KeyboardModifier.ControlModifier)
                    if ctrl:
                        self.merge_codes(self.codes[found], parent)
                        return
                    if parent_cid == self.codes[found]['cid']:
                        return  # cannot nest under itself
                    if self.code_is_descendant(parent_cid, self.codes[found]['cid']):
                        Message(self.app, _("Cannot nest code"),
                                _("Cannot move a code under one of its own sub-codes.")).exec()
                        return
                    # Nest as a sub-code (mutually exclusive with category).
                    self.codes[found]['supercid'] = parent_cid
                    self.codes[found]['catid'] = None
                else:
                    # Dropped onto a category.
                    catid = int(parent.text(1).split(':')[1])
                    self.codes[found]['catid'] = catid
                    self.codes[found]['supercid'] = None

            cur = self.app.conn.cursor()
            cur.execute("update code_name set catid=?, supercid=? where cid=?",
                        [self.codes[found]['catid'], self.codes[found].get('supercid'),
                         self.codes[found]['cid']])
            self.app.conn.commit()
            self.app.delete_backup = False
            self.codes_changed.emit(["code_name"])

    def code_is_descendant(self, candidate_cid, ancestor_cid) -> bool:
        """
        Return True if candidate_cid is ancestor_cid or one of its descendant sub-codes.
        Used to prevent cycles when nesting a code under another code.
        """
        if candidate_cid == ancestor_cid:
            return True
        children = {}
        for c in self.codes:
            sup = c.get('supercid')
            if sup is not None:
                children.setdefault(sup, []).append(c['cid'])
        stack = list(children.get(ancestor_cid, []))
        seen = set()
        while stack:
            cid = stack.pop()
            if cid == candidate_cid:
                return True
            if cid in seen:
                continue
            seen.add(cid)
            stack.extend(children.get(cid, []))
        return False

    def category_is_descendant(self, candidate_catid, ancestor_catid) -> bool:
        """
        Return True if candidate_catid is ancestor_catid or one of its descendant
        sub-categories. Used to prevent cycles when moving a category under another.
        """
        if candidate_catid == ancestor_catid:
            return True
        children = {}
        for c in self.categories:
            sup = c.get('supercatid')
            if sup is not None:
                children.setdefault(sup, []).append(c['catid'])
        stack = list(children.get(ancestor_catid, []))
        seen = set()
        while stack:
            catid = stack.pop()
            if catid == candidate_catid:
                return True
            if catid in seen:
                continue
            seen.add(catid)
            stack.extend(children.get(catid, []))
        return False

    # recursive tree helpers

    def recursive_get_branch_codes(self, item, branch_codes) -> list:
        """
        Gather all code dictionaries below this item, including sub-codes.
        Recurse through all child categories.
        Args:
            item: QTreeWidgetItem
            branch_codes: List of code dictionaries
        """

        child_count = item.childCount()
        for i in range(child_count):
            if item.child(i).text(1)[0:3] == "cid":
                cid = int(item.child(i).text(1)[4:])
                for code_ in self.codes:
                    if cid == code_['cid']:
                        branch_codes.append(code_)
                        break
                self.recursive_get_branch_codes(item.child(i), branch_codes)  # also gather sub-codes nested under this code (supercid)
            if item.child(i).text(1)[0:3] == "cat":
                self.recursive_get_branch_codes(item.child(i), branch_codes)
        return branch_codes

    def recursive_expand_collapse_branch(self, item, expand_toggle: bool):
        """
        Set all children of this item to be expanded or collapsed.
        Recurse through all child categories.
        Args:
            item: QTreeWidgetItem
            expand_toggle: boolean
        """

        child_count = item.childCount()
        for i in range(child_count):
            item.setExpanded(expand_toggle)
            self.recursive_expand_collapse_branch(item.child(i), expand_toggle)

    def recursive_non_merge_item(self, item, no_merge_list) -> list:
        """
        Find child category ids below the item, as strings.
        Required for merge_category() and move_category().
        Args:
            item : QTreeWidgetItem
            no_merge_list : List of child Category ids (as Strings)
        """

        child_count = item.childCount()
        for i in range(child_count):
            if item.child(i).text(1)[0:3] == "cat":
                no_merge_list.append(item.child(i).text(1)[6:])
            self.recursive_non_merge_item(item.child(i), no_merge_list)
        return no_merge_list

    # add

    def add_code(self, catid: int | None = None, code_name: str = "", supercid: int | None = None) -> bool:
        """
        Use add_item dialog to get new code text. Add_code_name dialog checks for
        duplicate code name. A random color is selected for the code, or a color has been pre-set by the user.
        New code is added to data and database.
        Args:
            catid : None to add code without category, catid Integer to add to category.
            code_name : String : Used for 'in vivo' coding where name is preset by in vivo text selection.
            supercid : None, or Integer to add the code as a sub-code of another code.
        Returns:
            True  - new code added, False - code exists or could not be added
        """

        # Mutual exclusivity: a sub-code never belongs to a category as well.
        if supercid is not None:
            catid = None
        if code_name == "":
            ui = DialogAddItemName(self.app, self.codes, _("Add new code"), _("Code name"))
            ui.exec()
            code_name = ui.get_new_name()
            if code_name is None:
                return False
        code_color = colors[randint(0, len(colors) - 1)]
        default_color = getattr(self.host, 'default_new_code_color', None)
        if default_color:
            code_color = default_color
        item = {'name': code_name, 'memo': "", 'owner': self.app.settings['codername'],
                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'catid': catid,
                'color': code_color, 'supercid': supercid}
        cur = self.app.conn.cursor()
        try:
            cur.execute("insert into code_name (name,memo,owner,date,catid,color,supercid) values(?,?,?,?,?,?,?)",
                        (item['name'], item['memo'], item['owner'], item['date'], item['catid'], item['color'],
                         item['supercid']))
            self.app.conn.commit()
            self.app.delete_backup = False
            cur.execute("select last_insert_rowid()")
            cid = cur.fetchone()[0]
            item['cid'] = cid
            self.parent_textEdit.append(_("New code: ") + item['name'])
        except sqlite3.IntegrityError:
            # Can occur with in vivo coding
            logger.debug("in vivo coding. Code already exists")
            return False
        self.codes_changed.emit(["code_name"])
        return True

    def add_category(self, supercatid: int | None = None):
        """
        Add a new category.
        Note: the addItem dialog does the checking for duplicate category names
        Args:
            supercatid : None to add without category, supercatid to add to category.
        """

        ui = DialogAddItemName(self.app, self.categories, _("Category"), _("Category name"))
        ui.exec()
        new_category_name = ui.get_new_name()
        if new_category_name is None:
            return
        item = {'name': new_category_name, 'cid': None, 'memo': "",
                'owner': self.app.settings['codername'],
                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
        cur = self.app.conn.cursor()
        cur.execute("insert into code_cat (name, memo, owner, date, supercatid) values(?,?,?,?,?)",
                    (item['name'], item['memo'], item['owner'], item['date'], supercatid))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.parent_textEdit.append(_("New category: ") + item['name'])
        self.codes_changed.emit(["code_cat"])

    # delete

    def delete_code(self, selected: QtWidgets.QTreeWidgetItem):
        """
        Find code, remove from database, refresh code data and fill treeWidget.
        Args:
            selected: QTreeWidgetItem
        """

        # Find the code in the list, check to delete
        found = -1
        for i in range(0, len(self.codes)):
            if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                found = i
        if found == -1:
            return
        code_ = self.codes[found]
        ui = DialogConfirmDelete(self.app, _("Code: ") + selected.text(0))
        ok = ui.exec()
        if not ok:
            return
        cur = self.app.conn.cursor()
        # Re-parent this code's sub-codes so they are not orphaned by the deletion.
        if code_.get('supercid') is not None:
            # Was itself a sub-code: lift its children to the grandparent code.
            cur.execute("update code_name set supercid=? where supercid=?", [code_['supercid'], code_['cid']])
        else:
            # Was top level (possibly under a category): move children into that category (or top level).
            cur.execute("update code_name set supercid=null, catid=? where supercid=?",
                        [code_['catid'], code_['cid']])
        cur.execute("delete from code_name where cid=?", [code_['cid'], ])
        cur.execute("delete from code_text where cid=?", [code_['cid'], ])
        cur.execute("delete from code_av where cid=?", [code_['cid'], ])
        cur.execute("delete from code_image where cid=?", [code_['cid'], ])
        self.app.conn.commit()
        self.app.delete_backup = False
        self.parent_textEdit.append(_("Code deleted: ") + code_['name'] + "\n")
        # Let the host clean its own caches, such as the recent codes list.
        if self.on_codes_deleted is not None:
            self.on_codes_deleted([code_['cid']])
        self.codes_changed.emit(["code_name", "code_text", "code_av", "code_image"])

    def get_branch_catids_and_cids(self, catid: int) -> tuple:
        """
        Gather every category and code that hangs below a category, including the category itself.
        Sub-codes (supercid) nested under branch codes are collected too.
        Read straight from the database, not from the cached host codes / categories, so a
        stale dialog snapshot can never delete or miss the wrong rows.
        Iterative walk, so cyclic or malformed data cannot cause infinite recursion.
        Args:
            catid: Integer, category id of the branch root
        Returns:
            Tuple: (list of category ids, list of code ids)
        """

        cur = self.app.conn.cursor()
        cur.execute("select catid, supercatid from code_cat")
        db_cats = cur.fetchall()
        cur.execute("select cid, catid, supercid from code_name")
        db_codes = cur.fetchall()
        catids = [catid]
        i = 0
        while i < len(catids):
            for cat_ in db_cats:
                if cat_[1] == catids[i] and cat_[0] not in catids:
                    catids.append(cat_[0])
            i += 1
        cids = []
        for code_ in db_codes:
            if code_[1] in catids and code_[0] not in cids:
                cids.append(code_[0])
        i = 0
        while i < len(cids):
            for code_ in db_codes:
                if code_[2] == cids[i] and code_[0] not in cids:
                    cids.append(code_[0])
            i += 1
        return catids, cids

    def delete_category_branch(self, selected: QtWidgets.QTreeWidgetItem):
        """
        Delete a category and everything underneath it: nested categories, codes, sub-codes
        and all the codings (text, audio/video, image) made with those codes.
        Unlike Delete, which only removes the category and re-parents its contents,
        this cascades down the whole branch. All writes run in a single transaction.
        Args:
            selected: QTreeWidgetItem
        """

        if selected is None or selected.text(1)[0:3] != 'cat':
            return
        cur = self.app.conn.cursor()
        cur.execute("select catid, name from code_cat where catid=?", [int(selected.text(1)[6:]), ])
        res = cur.fetchone()
        if res is None:  # Already deleted elsewhere, the tree item is stale
            self.codes_changed.emit([])
            return
        category = {'catid': res[0], 'name': res[1]}
        catids, cids = self.get_branch_catids_and_cids(category['catid'])
        # Count the codings that will be lost, so the user knows what is at stake.
        # One grouped scan per table, instead of one query per code.
        cids_set = set(cids)
        codings = 0
        for table in ("code_text", "code_av", "code_image"):
            cur.execute(f"select cid, count(*) from {table} group by cid")
            for row in cur.fetchall():
                if row[0] in cids_set:
                    codings += row[1]
        msg = _("Category branch") + ": " + category['name'] + "\n\n"
        msg += _("All categories and codes under this category will also be deleted.") + "\n"
        msg += _("All codings made with these codes across all files will be deleted.") + "\n\n"
        msg += _("Categories to delete") + f": {len(catids)}\n"
        msg += _("Codes to delete") + f": {len(cids)}\n"
        msg += _("Codings to delete") + f": {codings}\n\n"
        msg += _("Make a project backup first. This action cannot be undone.")
        ui = DialogConfirmDelete(self.app, msg)
        # Cancel is the default button here, so a stray Enter cannot wipe out the branch.
        button_box = ui.findChild(QtWidgets.QDialogButtonBox)
        if button_box is not None:
            ok_button = button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
            cancel_button = button_box.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel)
            if ok_button is not None:
                ok_button.setAutoDefault(False)
                ok_button.setDefault(False)
            if cancel_button is not None:
                cancel_button.setAutoDefault(True)
                cancel_button.setDefault(True)
                cancel_button.setFocus()
        ok = ui.exec()
        if not ok:
            return
        try:
            for cid in cids:
                cur.execute("delete from code_text where cid=?", [cid, ])
                cur.execute("delete from code_av where cid=?", [cid, ])
                cur.execute("delete from code_image where cid=?", [cid, ])
                cur.execute("delete from code_name where cid=?", [cid, ])
                # Saved graphs: drop nodes and links pointing at this code, so that a reused
                # cid cannot silently re-bind an old graph node to an unrelated code.
                cur.execute("delete from gr_cdct_text_item where cid=?", [cid, ])
                cur.execute("delete from gr_cdct_line_item where fromcid=? or tocid=?", [cid, cid])
                cur.execute("delete from gr_free_line_item where fromcid=? or tocid=?", [cid, cid])
            for cat_id in catids:
                cur.execute("delete from code_cat where catid=?", [cat_id, ])
                cur.execute("delete from gr_cdct_text_item where catid=?", [cat_id, ])
                cur.execute("delete from gr_cdct_line_item where fromcatid=? or tocatid=?", [cat_id, cat_id])
                cur.execute("delete from gr_free_line_item where fromcatid=? or tocatid=?", [cat_id, cat_id])
            # Drop the deleted codes from the stored recently used codes.
            cur.execute("select recently_used_codes from project")
            recent_res = cur.fetchone()
            if recent_res is not None and recent_res[0]:
                keep = []
                for token in recent_res[0].split():
                    try:
                        if int(token) in cids:
                            continue
                    except ValueError:
                        pass
                    keep.append(token)
                cur.execute("update project set recently_used_codes=?", [" ".join(keep), ])
            # Extra check. Clear any dangling references left behind by the deletion.
            cur.execute("update code_cat set supercatid=null where supercatid is not null and supercatid not in "
                        "(select catid from code_cat)")
            cur.execute("update code_name set catid=null where catid is not null and catid not in "
                        "(select catid from code_cat)")
            cur.execute("update code_name set supercid=null where supercid is not null and supercid not in "
                        "(select cid from code_name)")
            self.app.conn.commit()
        except Exception as e_:
            logger.warning(e_)
            self.app.conn.rollback()  # Revert all changes
            self.codes_changed.emit([])
            raise
        # Let the host clean its own caches, such as the recent codes list.
        if self.on_codes_deleted is not None:
            self.on_codes_deleted(cids)
        self.app.delete_backup = False
        msg = _("Category branch deleted") + ": " + category['name'] + ". "
        msg += _("Categories") + f": {len(catids)}, " + _("Codes") + f": {len(cids)}, "
        msg += _("Codings") + f": {codings}"
        self.parent_textEdit.append(msg)
        self.codes_changed.emit(["code_cat", "code_name", "code_text", "code_av", "code_image"])

    # memo, rename, colour

    def add_edit_cat_or_code_memo(self, selected: QtWidgets.QTreeWidgetItem):
        """
        View and edit a memo for a category or code.
        Args:
            selected: QTreeWidgetItem
        """

        changed_tables = []
        if selected.text(1)[0:3] == 'cid':
            # Find the code in the list
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                    found = i
            if found == -1:
                return
            ui = DialogMemo(self.app, _("Memo for Code: ") + self.codes[found]['name'], self.codes[found]['memo'])
            ui.exec()
            memo = ui.memo
            if memo != self.codes[found]['memo']:
                self.codes[found]['memo'] = memo
                cur = self.app.conn.cursor()
                cur.execute("update code_name set memo=? where cid=?", (memo, self.codes[found]['cid']))
                self.app.conn.commit()
                self.app.delete_backup = False
                changed_tables = ["code_name"]
            if memo == "":
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, "")
            else:
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, _("Memo"))
                self.parent_textEdit.append(_("Memo for code: ") + self.codes[found]['name'])

        if selected.text(1)[0:3] == 'cat':
            # Find the category in the list
            found = -1
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                    found = i
            if found == -1:
                return
            ui = DialogMemo(self.app, _("Memo for Category: ") + self.categories[found]['name'],
                            self.categories[found]['memo'])
            ui.exec()
            memo = ui.memo
            if memo != self.categories[found]['memo']:
                self.categories[found]['memo'] = memo
                cur = self.app.conn.cursor()
                cur.execute("update code_cat set memo=? where catid=?", (memo, self.categories[found]['catid']))
                self.app.conn.commit()
                self.app.delete_backup = False
                changed_tables = ["code_cat"]
            if memo == "":
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, "")
            else:
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, _("Memo"))
                self.parent_textEdit.append(_("Memo for category: ") + self.categories[found]['name'])
        self.codes_changed.emit(changed_tables)

    def rename_category_or_code(self, selected: QtWidgets.QTreeWidgetItem):
        """
        Rename a code or category.
        Check that the code or category name is not currently in use.
        Args:
            selected : QTreeWidgetItem
        """

        if selected.text(1)[0:3] == 'cid':
            found_code = None
            check_codes = []
            for code_ in self.codes:
                if code_['cid'] == int(selected.text(1)[4:]):
                    found_code = code_
                else:
                    check_codes.append(code_)
            if found_code is None:
                return
            ui = DialogAddItemName(self.app, check_codes, _("Rename code"), _("Code name"))
            ui.ui.lineEdit.setText(found_code['name'])
            ui.exec()
            new_name = ui.get_new_name()
            if new_name is None or new_name == found_code['name']:
                return
            old_name = found_code['name']
            # Let the host update its own caches, such as the recent codes list.
            if self.on_code_renamed is not None:
                self.on_code_renamed(old_name, new_name)
            # Update codes list and database
            cur = self.app.conn.cursor()
            cur.execute("update code_name set name=? where cid=?", (new_name, found_code['cid']))
            self.app.conn.commit()
            self.app.delete_backup = False
            self.parent_textEdit.append(_("Code renamed from: ") + f"{old_name} --> {new_name}")
            self.codes_changed.emit(["code_name"])
            return

        if selected.text(1)[0:3] == 'cat':
            found_cat = None
            check_categories = []
            for category in self.categories:
                if category['catid'] == int(selected.text(1)[6:]):
                    found_cat = category
                else:
                    check_categories.append(category)
            if found_cat is None:
                return
            ui = DialogAddItemName(self.app, check_categories, _("Rename category"), _("Category name"))
            ui.ui.lineEdit.setText(found_cat['name'])
            ui.exec()
            new_name = ui.get_new_name()
            if new_name is None or new_name == found_cat['name']:
                return
            old_name = found_cat['name']
            # Update category list and database
            cur = self.app.conn.cursor()
            cur.execute("update code_cat set name=? where catid=?", (new_name, found_cat['catid']))
            self.app.conn.commit()
            self.app.delete_backup = False
            self.parent_textEdit.append(_("Category renamed from: ") + f"{old_name} --> {new_name}")
            self.codes_changed.emit(["code_cat"])

    def change_code_color(self, selected: QtWidgets.QTreeWidgetItem):
        """
        Change the colour of the currently selected code.
        Args:
            selected : QTreeWidgetItem
        """

        cid = int(selected.text(1)[4:])
        found = -1
        for i in range(0, len(self.codes)):
            if self.codes[i]['cid'] == cid:
                found = i
        if found == -1:
            return
        ui = DialogColorSelect(self.app, self.codes[found])
        ok = ui.exec()
        if not ok:
            return
        new_color = ui.get_color()
        if new_color is None:
            return
        selected.setBackground(0, QBrush(QColor(new_color), Qt.BrushStyle.SolidPattern))
        # Update codes list, database and color markings
        self.codes[found]['color'] = new_color
        cur = self.app.conn.cursor()
        cur.execute("update code_name set color=? where cid=?",
                    (self.codes[found]['color'], self.codes[found]['cid']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.codes_changed.emit(["code_name"])

    # move

    def move_code(self, selected: QtWidgets.QTreeWidgetItem):
        """
        Move code to another category, or code or to none (top level).
        Uses a list selection which represents the codes tree.
        Args:
            selected : QTreeWidgetItem
         """

        items_list = [{'name': " ", 'catid': -1, 'cid': -1}]  # Default blank item
        iterator = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            can_append = True
            item = iterator.value()
            depth = 0
            current = item
            while current.parent() is not None:
                current = current.parent()
                depth += 1
                if current.text(1) == selected.text(1):
                    can_append = False
            prefix = ""
            if depth > 0:
                prefix = "  " * (depth - 1) * 2 + "└─"  # U2514 U2500
            name = prefix + item.text(0)
            cid = -1
            catid = -1
            if "cid" in item.text(1):
                cid = int(item.text(1)[4:])
            else:
                catid = int(item.text(1)[6:])
                name += " " + _("[CATEGORY]")
            # Check the same item is not the same selected item
            if item.text(1) == selected.text(1) and item.text(2) == selected.text(2):
                can_append = False
            memo = item.toolTip(2)
            if can_append:
                items_list.append({'name': name, 'catid': catid, 'cid': cid, 'memo': memo})
            iterator += 1
        ui = DialogSelectItems(self.app, items_list, _("Move code: Select blank or category or code"), "single")
        ok = ui.exec()
        if not ok:
            return
        destination = ui.get_selected()
        selected_cid = int(selected.text(1)[4:])
        cur = self.app.conn.cursor()
        if destination['catid'] == -1 and destination['cid'] == -1:  # move to top level
            cur.execute("update code_name set catid=null, supercid=null where cid=?", [selected_cid])
        elif destination['cid'] > 0:  # Move under another code
            # Belt and braces: never write a supercid cycle, even if the selection list
            # was built from a stale or corrupted tree.
            if self.code_is_descendant(destination['cid'], selected_cid):
                Message(self.app, _("Cannot move code"),
                        _("Cannot move a code under itself or one of its own sub-codes.")).exec()
                return
            cur.execute("update code_name set catid=null, supercid=? where cid=?", [destination['cid'], selected_cid])
        else:  # Move under a category
            cur.execute("update code_name set catid=?, supercid=null where cid=?", [destination['catid'], selected_cid])
        self.app.conn.commit()
        self.app.delete_backup = False
        self.codes_changed.emit(["code_name"])

    def move_multiple_codes(self):
        """
        Move multiple codes to another category.
        """

        cur = self.app.conn.cursor()
        cur.execute("select code_name.name, code_cat.name, cid from code_name left join code_cat on "
                    "code_cat.catid=code_name.catid order by upper(code_cat.name) asc, upper(code_name.name) asc")
        res = cur.fetchall()
        code_list = []
        for r in res:
            name = r[0]
            if r[1] is not None:
                name = r[1] + " ← " + r[0]
            code_list.append({'name': name, 'cid': r[2]})
        ui = DialogSelectItems(self.app, code_list, _("Select codes"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_codes = ui.get_selected()
        cur.execute("select name, catid from code_cat order by upper(name)")
        res = cur.fetchall()
        category_list = [{'name': "", 'catid': None}]
        for r in res:
            category_list.append({'name': r[0], 'catid': r[1]})
        ui = DialogSelectItems(self.app, category_list, _("Select blank or category"), "single")
        ok = ui.exec()
        if not ok:
            return
        category = ui.get_selected()
        for s in selected_codes:
            # Moving to a category (or to blank) removes any sub-code nesting.
            cur.execute("update code_name set catid=?, supercid=null where cid=?", [category['catid'], s['cid']])
            self.app.conn.commit()
            self.parent_textEdit.append(_("Code moved.") + s['name'].replace(" ← ", "/") + " → " + category['name'])
        self.app.delete_backup = False
        self.codes_changed.emit(["code_name"])

    def move_category(self, catid: int):
        """
        Select another category to move this category underneath.
        Args:
            catid : Integer category identifier
        """

        do_not_merge_list = []
        do_not_merge_list = self.recursive_non_merge_item(self.tree.currentItem(), do_not_merge_list)
        do_not_merge_list.append(str(catid))
        do_not_merge_ids_string = f"({','.join(do_not_merge_list)})"
        sql = "select name, catid, supercatid from code_cat where catid not in "
        sql += do_not_merge_ids_string + " order by name"
        cur = self.app.conn.cursor()
        cur.execute(sql)
        res = cur.fetchall()
        category_list = [{'name': "", 'catid': None, 'supercatid': None}]
        for r in res:
            category_list.append({'name': r[0], 'catid': r[1], "supercatid": r[2]})
        ui = DialogSelectItems(self.app, category_list, _("Move category: Select blank or category"), "single")
        ok = ui.exec()
        if not ok:
            return
        category = ui.get_selected()
        current_cat_name = self.tree.currentItem().text(0)
        if category['name'] == '':
            cur.execute("update code_cat set supercatid=Null where catid=?", [catid])
            self.app.conn.commit()
            self.parent_textEdit.append(_("Moved category: ") + current_cat_name + " → Top level")
        else:
            cur.execute("update code_cat set supercatid=? where catid=?", [category['catid'], catid])
            self.app.conn.commit()
            self.parent_textEdit.append(_("Moved category: ") + current_cat_name + " → " + category['name'])
        self.app.delete_backup = False
        self.codes_changed.emit(["code_cat"])

    # merge

    def merge_category(self, catid: int):
        """ Select another category to merge this category into.
        Args:
            catid : Integer category identifier
        """

        do_not_merge_list = []
        do_not_merge_list = self.recursive_non_merge_item(self.tree.currentItem(), do_not_merge_list)
        do_not_merge_list.append(str(catid))
        do_not_merge_ids_string = "(" + ",".join(do_not_merge_list) + ")"
        sql = "select name, catid, supercatid from code_cat where catid not in "
        sql += do_not_merge_ids_string + " order by name"
        cur = self.app.conn.cursor()
        cur.execute(sql)
        res = cur.fetchall()
        category_list = [{'name': "", 'catid': None, 'supercatid': None}]
        for r in res:
            category_list.append({'name': r[0], 'catid': r[1], "supercatid": r[2]})
        ui = DialogSelectItems(self.app, category_list, _("Select blank or category"), "single")
        ok = ui.exec()
        if not ok:
            return
        category = ui.get_selected()
        try:
            # Always record merge info in target category memo
            source_cat = None
            for c in self.categories:
                if c['catid'] == catid:
                    source_cat = c
                    break
            if source_cat is not None and category['catid'] is not None:
                target_cat = None
                for c in self.categories:
                    if c['catid'] == category['catid']:
                        target_cat = c
                        break
                if target_cat is not None:
                    merge_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
                    source_memo = (source_cat.get('memo', '') or '').strip()
                    source_owner = source_cat.get('owner', self.app.settings['codername'])
                    merged_block = f"\n\n[{_('Merged from category:')} {source_cat['name']}, {_('Coder:')} {source_owner}, {_('Merger date:')} {merge_date}]"
                    if source_memo:
                        merged_block += f"\n{source_memo}"
                    target_memo = target_cat.get('memo', '') or ''
                    new_memo = (target_memo + merged_block).strip()
                    cur.execute("update code_cat set memo=? where catid=?", [new_memo, category['catid']])
                    target_cat['memo'] = new_memo
            for code in self.codes:
                if code['catid'] == catid:
                    cur.execute("update code_name set catid=? where catid=?", [category['catid'], catid])
            cur.execute("delete from code_cat where catid=?", [catid])
            for cat in self.categories:
                if cat['supercatid'] == catid:
                    cur.execute("update code_cat set supercatid=? where supercatid=?", [category['catid'], catid])
            # Clear any orphan supercatids
            sql = "select supercatid from code_cat where supercatid not in (select catid from code_cat)"
            cur.execute(sql)
            orphans = cur.fetchall()
            sql = "update code_cat set supercatid=Null where supercatid=?"
            for orphan in orphans:
                cur.execute(sql, [orphan[0]])
            self.app.conn.commit()
        except Exception as e_:
            logger.warning(e_)
            self.app.conn.rollback()  # Revert all changes
            self.codes_changed.emit([])
            raise
        self.app.delete_backup = False
        self.codes_changed.emit(["code_cat", "code_name"])

    def merge_code_into_code(self, selected: QtWidgets.QTreeWidgetItem):
        """
        Merge the selected code into another code chosen from a list.
        Reuses merge_codes (the same logic used by drag-and-drop with Ctrl). The source code
        and all of its descendant sub-codes are excluded from the candidate targets to avoid
        creating a supercid cycle when merging a code into one of its own sub-codes.
        Args:
            selected: QTreeWidgetItem
        """

        if selected is None or selected.text(1)[0:3] != 'cid':
            return
        src_cid = int(selected.text(1)[4:])
        source_code = next((c for c in self.codes if c['cid'] == src_cid), None)
        if source_code is None:
            return
        # Candidate targets: every code that is not the source nor a descendant of the source.
        target_list = []
        for c in self.codes:
            if not self.code_is_descendant(c['cid'], src_cid):
                target_list.append({'name': c['name'], 'cid': c['cid']})
        if not target_list:
            Message(self.app, _("Merge code into code"),
                    _("There is no other code to merge into.")).exec()
            return
        target_list = sorted(target_list, key=lambda x: x['name'].lower())
        ui = DialogSelectItems(self.app, target_list, _("Select code to merge into"), "single")
        ok = ui.exec()
        if not ok:
            return
        target = ui.get_selected()
        if not target:
            return
        # merge_codes expects the target as a QTreeWidgetItem, so find it in the tree.
        target_item = None
        it = QtWidgets.QTreeWidgetItemIterator(self.tree)
        while it.value():
            node = it.value()
            if node.text(1) == f"cid:{target['cid']}":
                target_item = node
                break
            it += 1
        if target_item is None:
            return
        self.merge_codes(source_code, target_item)

    def merge_codes(self, item: dict, parent: QtWidgets.QTreeWidgetItem):
        """
        Merge code with another code.
        Called by item_moved_update_data when a code is moved onto another code with Ctrl held.
        code text unique(cid,fid,pos0,pos1, owner)
        Args:
            item : Dictionary code item
            parent : QTreeWidgetItem
        """

        # Check item dropped on itself
        if item['name'] == parent.text(0):
            return
        # Prevent a supercid cycle
        target_cid = int(parent.text(1).split(':')[1])
        if self.code_is_descendant(target_cid, item['cid']):
            Message(self.app, _("Cannot merge code"),
                    _("Cannot merge a code into itself or one of its own sub-codes.")).exec()
            return
        msg = '<p style="font-size:' + str(self.app.settings['fontsize']) + 'px">'
        msg += _("Merge code: ") + item['name'] + _(" into code: ") + parent.text(0) + '</p>'
        reply = QtWidgets.QMessageBox.question(self.tree, _('Merge codes'),
                                               msg, QtWidgets.QMessageBox.StandardButton.Yes,
                                               QtWidgets.QMessageBox.StandardButton.No)
        if reply == QtWidgets.QMessageBox.StandardButton.No:
            return
        cur = self.app.conn.cursor()
        old_cid = item['cid']
        new_cid = int(parent.text(1).split(':')[1])
        # Always record merge info in target code memo
        target_code = None
        for c in self.codes:
            if c['cid'] == new_cid:
                target_code = c
                break
        if target_code is not None:
            merge_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
            source_memo = item.get('memo', '').strip()
            source_owner = item.get('owner', self.app.settings['codername'])
            merged_block = f"\n\n[{_('Merged from code:')} {item['name']}, {_('Coder:')} {source_owner}, {_('Merger date:')} {merge_date}]"
            if source_memo:
                merged_block += f"\n{source_memo}"
            target_memo = target_code.get('memo', '') or ''
            new_memo = (target_memo + merged_block).strip()
            cur.execute("update code_name set memo=? where cid=?", [new_memo, new_cid])
            target_code['memo'] = new_memo
        # Update cid for each coded segment in text, av, image. Delete where there is an Integrity error
        ct_sql = "select ctid from code_text where cid=?"
        cur.execute(ct_sql, [old_cid])
        ct_res = cur.fetchall()
        try:
            for ct in ct_res:
                try:
                    cur.execute("update code_text set cid=? where ctid=?", [new_cid, ct[0]])
                except sqlite3.IntegrityError:
                    cur.execute("delete from code_text where ctid=?", [ct[0]])
            av_sql = "select avid from code_av where cid=?"
            cur.execute(av_sql, [old_cid])
            av_res = cur.fetchall()
            for av in av_res:
                try:
                    cur.execute("update code_av set cid=? where avid=?", [new_cid, av[0]])
                except sqlite3.IntegrityError:
                    cur.execute("delete from code_av where avid=?", [av[0]])
            img_sql = "select imid from code_image where cid=?"
            cur.execute(img_sql, [old_cid])
            img_res = cur.fetchall()
            for img in img_res:
                try:
                    cur.execute("update code_image set cid=? where imid=?", [new_cid, img[0]])
                except sqlite3.IntegrityError:
                    cur.execute("delete from code_image where imid=?", [img[0]])
            # Re-parent the merged code's sub-codes onto the target code (no orphans).
            cur.execute("update code_name set supercid=?, catid=null where supercid=?", [new_cid, old_cid])
            cur.execute("delete from code_name where cid=?", [old_cid, ])
            self.app.conn.commit()
        except Exception as e_:
            logger.warning(e_)
            self.app.conn.rollback()  # Revert all changes
            raise
        self.app.delete_backup = False
        # Let the host clean its own caches, such as the recent codes list.
        if self.on_codes_deleted is not None:
            self.on_codes_deleted([old_cid])
        msg = msg.replace("\n", " ")
        self.parent_textEdit.append(msg)
        self.codes_changed.emit(["code_name", "code_text", "code_av", "code_image"])
