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
"""

from copy import deepcopy, copy
import logging
import os
import qtawesome as qta

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush


from .color_selector import colors, colors_red_weak, colors_red_blind, colors_green_weak, colors_green_blind, TextColor
from .GUI.ui_dialog_code_colours import Ui_Dialog_code_colors


path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

ROWS = 12
COLS = 10


class DialogCodeColorScheme(QtWidgets.QDialog):
    """ Edit codes colour scheme.  """

    app = None
    parent_textEdit = None
    original_code_colors = []
    selected_colors = []

    def __init__(self, app, parent_textedit):
        """ """

        super(DialogCodeColorScheme, self).__init__()
        self.app = app
        self.parent_textEdit = parent_textedit
        self.codes = []
        self.categories = []
        self.get_codes_and_categories()
        self.perspective = [_("Normal vision"), _("Red weak"), _("Red blind"), _("Green weak"), _("Green blind")]
        self.perspective_idx = 0
        self.selected_colors = []
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_code_colors()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.ui.splitter.setSizes([100, 300])
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        tree_font = f'font: {self.app.settings["treefontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.treeWidget.setStyleSheet(tree_font)
        self.ui.treeWidget.viewport().installEventFilter(self)
        self.ui.treeWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        #self.ui.treeWidget.customContextMenuRequested.connect(self.tree_menu)
        self.ui.treeWidget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.ui.pushButton_clear_selection_codes.pressed.connect(self.ui.treeWidget.clearSelection)
        self.ui.pushButton_clear_selection.pressed.connect(self.ui.tableWidget.clearSelection)
        self.ui.tableWidget.setTabKeyNavigation(False)
        self.ui.tableWidget.itemSelectionChanged.connect(self.update_selected_colors)
        self.fill_tree()
        self.fill_table()
        self.ui.pushButton_perspective.pressed.connect(self.change_perspective)
        self.ui.pushButton_apply.pressed.connect(self.apply_colors_to_codes)
        self.ui.pushButton_undo.setIcon(qta.icon('mdi6.undo'))
        self.ui.pushButton_undo.pressed.connect(self.undo_color_changes)

    def get_codes_and_categories(self):
        """ Called from init, delete category/code, event_filter """

        self.codes, self.categories = self.app.get_codes_categories()
        # Add perspective color key
        for c in self.codes:
            c['perspective'] = c['color']
        self.original_code_colors = deepcopy(self.codes)

    def undo_color_changes(self):
        """  """

        cur = self.app.conn.cursor()
        sql = "update code_name set color=? where cid=?"
        for c in self.original_code_colors:
            cur.execute(sql, [c['color'], c['cid']])
        self.app.conn.commit()
        self.get_codes_and_categories()
        self.perspective_idx = 0
        self.fill_tree()
        self.fill_table()

    def apply_colors_to_codes(self):
        """ Apply selected colours to selected codes, """

        if not self.selected_colors:
            return
        all_tree_items = self.ui.treeWidget.selectedItems()
        if not all_tree_items:
            return
        color_list = copy(self.selected_colors)
        code_items = [t for t in all_tree_items if t.text(1)[:3] == "cid"]
        while len(color_list) < len(code_items):
            color_list += self.selected_colors
        cur = self.app.conn.cursor()
        sql = "update code_name set color=? where cid=?"
        i = -1
        for ci in code_items:
            i += 1
            # code_ids are String "cid:5", update perspective color
            for code_ in self.codes:
                if int(ci.text(1)[4:]) == code_['cid']:
                    code_['color'] = color_list[i]
                    code_['perspective'] = color_list[i]
                    ci.setBackground(0, QBrush(QtGui.QColor(color_list[i]), Qt.BrushStyle.SolidPattern))
                    color = TextColor(color_list[i]).recommendation
                    ci.setForeground(0, QBrush(QtGui.QColor(color)))
                    cur.execute(sql, [color_list[i], int(ci.text(1)[4:])])
        self.app.conn.commit()
        self.perspective_idx = 4
        self.change_perspective()
        self.ui.treeWidget.clearSelection()
        self.ui.tableWidget.clearSelection()

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes. """

        cats = deepcopy(self.categories)
        codes = deepcopy(self.codes)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(3)
        self.ui.treeWidget.setHeaderLabels([_("Codes tree"), _("Id"), _("Memo")])
        if not self.app.settings['showids']:
            self.ui.treeWidget.setColumnHidden(1, True)
        else:
            self.ui.treeWidget.setColumnHidden(1, False)
        self.ui.treeWidget.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.ui.treeWidget.header().setStretchLastSection(False)
        # Add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                memo = ""
                if c['memo'] != "":
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], f'catid:{c["catid"]}', memo])
                top_item.setToolTip(0, c['name'])
                if len(c['name']) > 52:
                    top_item.setText(0, f"{c['name'][:25]}..{c['name'][-25:]}")
                    top_item.setToolTip(0, c['name'])
                top_item.setToolTip(2, c['memo'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_list.append(c)
        for item in remove_list:
            cats.remove(item)

        ''' Add child categories. Look at each unmatched category, iterate through tree
        to add as child, then remove matched categories from the list. '''
        count = 0
        while len(cats) > 0 and count < 10000:
            remove_list = []
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
                item = it.value()
                count2 = 0
                while item and count2 < 10000:
                    if item.text(1) == f'catid:{c["supercatid"]}':
                        memo = ""
                        if c['memo'] != "":
                            memo = "Memo"
                        child = QtWidgets.QTreeWidgetItem([c['name'], f'catid:{c["catid"]}', memo])
                        child.setToolTip(0, c['name'])
                        if len(c['name']) > 52:
                            child.setText(0, f"{c['name'][:25]}..{c['name'][-25:]}")
                            child.setToolTip(0, c['name'])
                        child.setToolTip(2, c['memo'])
                        item.addChild(child)
                        remove_list.append(c)
                    it += 1
                    item = it.value()
                    count2 += 1
            for item in remove_list:
                cats.remove(item)
            count += 1

        # Add unlinked codes as top level items
        remove_items = []
        for c in codes:
            if c['catid'] is None:
                memo = ""
                if c['memo'] != "":
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], f'cid:{c["cid"]}', memo])
                top_item.setToolTip(0, c['name'])
                if len(c['name']) > 52:
                    top_item.setText(0, f"{c['name'][:25]}..{c['name'][-25:]}")
                    top_item.setToolTip(0, c['name'])
                top_item.setToolTip(2, c['memo'])
                top_item.setBackground(0, QBrush(QtGui.QColor(c['perspective']), Qt.BrushStyle.SolidPattern))
                color = TextColor(c['color']).recommendation
                top_item.setForeground(0, QBrush(QtGui.QColor(color)))
                top_item.setFlags(
                    Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable |
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled)
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)

        # Add codes as children of categories
        for c in codes:
            it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
            item = it.value()
            count = 0
            while item and count < 10000:
                if item.text(1) == f'catid:{c["catid"]}':
                    memo = ""
                    if c['memo'] != "":
                        memo = "Memo"
                    child = QtWidgets.QTreeWidgetItem([c['name'], f'cid:{c["cid"]}', memo])
                    child.setBackground(0, QBrush(QtGui.QColor(c['perspective']), Qt.BrushStyle.SolidPattern))
                    color = TextColor(c['color']).recommendation
                    child.setForeground(0, QBrush(QtGui.QColor(color)))
                    child.setToolTip(0, c['name'])
                    if len(c['name']) > 52:
                        child.setText(0, f"{c['name'][:25]}..{c['name'][-25:]}")
                        child.setToolTip(0, c['name'])
                    child.setToolTip(2, c['memo'])
                    child.setFlags(
                        Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable |
                        Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled)
                    item.addChild(child)
                    c['catid'] = -1  # Make unmatchable
                it += 1
                item = it.value()
                count += 1
        self.ui.treeWidget.expandAll()

    def update_selected_colors(self):
        """ Update colour list. Prior to applying colors. """

        self.selected_colors = []
        for i in self.ui.tableWidget.selectedItems():
            self.selected_colors.append(colors[i.row() * COLS + i.column()])

    def change_perspective(self):
        """ Change colours for different vision perspectives. """

        self.perspective_idx += 1
        if self.perspective_idx >= len(self.perspective):
            self.perspective_idx = 0
        self.fill_table()

        # Update code perspective color for filling tree background
        for c in self.codes:
            color_index = colors.index(c['color'])
            if self.perspective_idx == 0:
                c['perspective'] = colors[color_index]
            if self.perspective_idx == 1:
                c['perspective'] = colors_red_weak[color_index]
            if self.perspective_idx == 2:
                c['perspective'] = colors_red_blind[color_index]
            if self.perspective_idx == 3:
                c['perspective'] = colors_green_weak[color_index]
            if self.perspective_idx == 4:
                c['perspective'] = colors_green_blind[color_index]
        self.fill_tree()
        self.ui.label_perspective.setText(_("Perspective: ") + self.perspective[self.perspective_idx])

    def fill_table(self):
        """ Twelve rows of ten columns of colours.
        normal, red weak, red blind, green weak, green blind
        param:
        color_range: String
        """

        self.ui.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        for r in range(self.ui.tableWidget.rowCount()):
            self.ui.tableWidget.removeRow(0)
        self.ui.tableWidget.setColumnCount(COLS)
        self.ui.tableWidget.setRowCount(ROWS)
        self.ui.tableWidget.verticalHeader().setVisible(False)
        self.ui.tableWidget.horizontalHeader().setVisible(False)
        for row in range(0, ROWS):
            for col in range(0, COLS):
                code_color = colors[row * COLS + col]
                text = ""
                item = QtWidgets.QTableWidgetItem(text)
                if self.perspective_idx == 0:
                    item.setBackground(QtGui.QBrush(QtGui.QColor(code_color)))
                if self.perspective_idx == 1:
                    item.setBackground(QtGui.QBrush(QtGui.QColor(colors_red_weak[row * COLS + col])))
                if self.perspective_idx == 2:
                    item.setBackground(QtGui.QBrush(QtGui.QColor(colors_red_blind[row * COLS + col])))
                if self.perspective_idx == 3:
                    item.setBackground(QtGui.QBrush(QtGui.QColor(colors_green_weak[row * COLS + col])))
                if self.perspective_idx == 4:
                    item.setBackground(QtGui.QBrush(QtGui.QColor(colors_green_blind[row * COLS + col])))
                item.setForeground(QtGui.QBrush(QtGui.QColor(TextColor(code_color).recommendation)))
                item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
                item.setFont(QtGui.QFont("Times", 10))
                self.ui.tableWidget.setItem(row, col, item)
                self.ui.tableWidget.setColumnWidth(col, 38)
            self.ui.tableWidget.setRowHeight(row, 22)


