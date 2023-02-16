# -*- coding: utf-8 -*-

"""
Copyright (c) 2023 Colin Curtain

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

from copy import deepcopy
import logging
import os
import sys
import traceback

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush


from .color_selector import colors, colors_red_weak, colors_red_blind, colors_green_weak, colors_green_blind, TextColor
from .GUI.ui_dialog_code_colours import Ui_Dialog_code_colors


path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

ROWS = 12
COLS = 10


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text_ = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text_)
    logger.error(_("Uncaught exception: ") + text_)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 12pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(text_)
    mb.exec()


class DialogCodeColorScheme(QtWidgets.QDialog):
    """ Edit codes colour scheme.  """

    app = None
    parent_textEdit = None
    selected_colors = []

    def __init__(self, app, parent_textedit, tab_reports):
        """
        """

        super(DialogCodeColorScheme, self).__init__()
        sys.excepthook = exception_handler
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

        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        tree_font = 'font: ' + str(self.app.settings['treefontsize']) + 'pt '
        tree_font += '"' + self.app.settings['font'] + '";'
        self.ui.treeWidget.setStyleSheet(tree_font)
        self.ui.treeWidget.viewport().installEventFilter(self)
        self.ui.treeWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.treeWidget.customContextMenuRequested.connect(self.tree_menu)
        self.ui.treeWidget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.ui.pushButton_clear_selection_codes.pressed.connect(self.ui.treeWidget.clearSelection)
        self.ui.pushButton_clear_selection.pressed.connect(self.ui.tableWidget.clearSelection)
        self.ui.tableWidget.itemSelectionChanged.connect(self.update_selected_colors)
        self.fill_tree()
        self.fill_table()
        self.ui.pushButton_perspective.pressed.connect(self.change_perspective)
        self.ui.pushButton_apply.pressed.connect(self.apply_colors_to_codes)

    def get_codes_and_categories(self):
        """ Called from init, delete category/code, event_filter """

        self.codes, self.categories = self.app.get_codes_categories()

    def apply_colors_to_codes(self):
        """  """

        pass

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
                if c['memo'] != "" and c['memo'] is not None:
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                top_item.setToolTip(0, c['name'])
                if len(c['name']) > 52:
                    top_item.setText(0, c['name'][:25] + '..' + c['name'][-25:])
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
                while item and count2 < 10000:  # while there is an item in the list
                    if item.text(1) == 'catid:' + str(c['supercatid']):
                        memo = ""
                        if c['memo'] != "" and c['memo'] is not None:
                            memo = "Memo"
                        child = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                        child.setToolTip(0, c['name'])
                        if len(c['name']) > 52:
                            child.setText(0, c['name'][:25] + '..' + c['name'][-25:])
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
                if c['memo'] != "" and c['memo'] is not None:
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                top_item.setToolTip(0, c['name'])
                if len(c['name']) > 52:
                    top_item.setText(0, c['name'][:25] + '..' + c['name'][-25:])
                    top_item.setToolTip(0, c['name'])
                top_item.setToolTip(2, c['memo'])
                top_item.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.BrushStyle.SolidPattern))
                color = TextColor(c['color']).recommendation
                top_item.setForeground(0, QBrush(QtGui.QColor(color)))
                top_item.setFlags(
                    Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable |
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled)
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)

        # Add codes as children to categories
        for c in codes:
            it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
            item = it.value()
            count = 0
            while item and count < 10000:
                if item.text(1) == 'catid:' + str(c['catid']):
                    memo = ""
                    if c['memo'] != "" and c['memo'] is not None:
                        memo = "Memo"
                    child = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                    child.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.BrushStyle.SolidPattern))
                    color = TextColor(c['color']).recommendation
                    child.setForeground(0, QBrush(QtGui.QColor(color)))
                    child.setToolTip(0, c['name'])
                    if len(c['name']) > 52:
                        child.setText(0, c['name'][:25] + '..' + c['name'][-25:])
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

    def tree_menu(self, position):
        """ Context menu for treewidget items.
        TODO """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        selected = self.ui.treeWidget.currentItem()

        action = menu.exec(self.ui.treeWidget.mapToGlobal(position))
        if action is None:
            return
        return

    def update_selected_colors(self):
        """ Update colour list. """

        self.selected_colors = []
        for i in self.ui.tableWidget.selectedItems():
            self.selected_colors.append(colors[i.row() * COLS + i.column()])
        #print(self.selected_colors)

    def change_perspective(self):
        """ Change colours for different vision perspectives. """

        self.perspective_idx += 1
        if self.perspective_idx >= len(self.perspective):
            self.perspective_idx = 0
        self.fill_table()
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
                '''ttip = ""
                for c in self.used_colors:
                    if code_color == c[0]:
                        text = "*"
                        ttip += c[1] + "\n"'''
                item = QtWidgets.QTableWidgetItem(text)
                #item.setToolTip(ttip)
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
        #self.ui.tableWidget.resizeColumnsToContents()
        #self.ui.tableWidget.resizeRowsToContents()

