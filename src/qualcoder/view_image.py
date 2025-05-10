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

from copy import deepcopy
import datetime
import fitz
import html
from io import BytesIO
import logging
import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/
from random import randint
import sqlite3
import webbrowser

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, QBuffer
from PyQt6.QtGui import QBrush

from .add_item_name import DialogAddItemName
from .code_in_all_files import DialogCodeInAllFiles
from .color_selector import DialogColorSelect
from .color_selector import colors, TextColor, colour_ranges, show_codes_of_colour_range
from .confirm_delete import DialogConfirmDelete
from .GUI.ui_dialog_code_image import Ui_Dialog_code_image
from .GUI.ui_dialog_view_image import Ui_Dialog_view_image
from .move_resize_rectangle import DialogMoveResizeRectangle
from .helpers import ExportDirectoryPathDialog, Message
from .memo import DialogMemo
from .report_attributes import DialogSelectAttributeParameters
from .reports import DialogReportCoderComparisons, DialogReportCodeFrequencies  # for isinstance()
from .report_codes import DialogReportCodes
from .select_items import DialogSelectItems

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogCodeImage(QtWidgets.QDialog):
    """ View and code images. Create codes and categories.  """

    app = None
    parent_textEdit = None
    tab_reports = None  # Tab widget reports, used for updates to codes
    pixmap = None
    scene = None
    files = []  # List of Dictionaries
    file_ = None  # Dictionary with name, memo, id, mediapath?
    codes = []
    categories = []
    tree_sort_option = "all asc"  # all desc, cat then code asc
    selection = None  # Initial code rectangle point
    scale = 1.0
    code_areas = []
    important = False  # Show/hide important flagged codes
    attributes = []
    undo_deleted_code = None  # Undo last deleted code
    degrees = 0  # For image rotation
    show_code_captions = 0  # 0 = no, 1 = code name, 2 = codename + memo
    pdf_page = None  # display at 1
    pdf_total_pages = None  # Total pages in pdf

    def __init__(self, app, parent_textedit, tab_reports):
        """ Show list of image files.
        On select, Show a scalable and scrollable image.
        Can add a memo to image
        The slider values range from 9 to 99 with intervals of 3.
        """

        super(DialogCodeImage, self).__init__()
        self.app = app
        self.tab_reports = tab_reports
        self.parent_textEdit = parent_textedit
        self.codes = []
        self.categories = []
        self.files = []
        self.undo_deleted_code = None
        self.file_ = None
        self.log = ""
        self.scale = 1.0
        self.selection = None
        self.important = False
        self.attributes = []
        self.degrees = 0
        self.get_codes_and_categories()
        self.tree_sort_option = "all asc"
        self.show_code_captions = 0
        self.pdf_page = None
        self.pdf_total_pages = None
        self.default_new_code_color = None
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_code_image()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.ui.splitter.setSizes([100, 300])
        self.scene = QtWidgets.QGraphicsScene()
        self.ui.graphicsView.setScene(self.scene)
        self.ui.graphicsView.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
        # Need this otherwise small images are centred on screen, and affect context menu position points
        self.ui.graphicsView.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.scene.installEventFilter(self)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        tree_font = f'font: {self.app.settings["treefontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.treeWidget.setStyleSheet(tree_font)
        self.ui.label_image.setStyleSheet(tree_font)  # Usually smaller font
        self.ui.label_coder.setText(_("Coder: ") + self.app.settings['codername'])
        self.setWindowTitle(_("Image coding"))
        self.ui.horizontalSlider.valueChanged[int].connect(self.redraw_scene)
        self.ui.horizontalSlider.setToolTip(_("Key + or W zoom in. Key - or Q zoom out"))

        self.ui.pushButton_default_new_code_color.setIcon(qta.icon('mdi6.palette', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_default_new_code_color.pressed.connect(self.set_default_new_code_color)
        self.ui.pushButton_export.setIcon(qta.icon('mdi6.export', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_export.pressed.connect(self.export_html_file)
        self.ui.pushButton_export.setEnabled(False)
        self.ui.listWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.listWidget.customContextMenuRequested.connect(self.file_menu)
        self.ui.listWidget.setStyleSheet(tree_font)
        self.get_files()
        self.ui.listWidget.selectionModel().selectionChanged.connect(self.file_selection_changed)
        self.ui.treeWidget.setDragEnabled(True)
        self.ui.treeWidget.setAcceptDrops(True)
        self.ui.treeWidget.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.ui.treeWidget.viewport().installEventFilter(self)
        self.ui.listWidget.installEventFilter(self)
        self.ui.treeWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.treeWidget.customContextMenuRequested.connect(self.tree_menu)
        # Header widgets
        self.ui.pushButton_zoom_in.setIcon(qta.icon('mdi6.magnify-plus-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_zoom_in.pressed.connect(self.zoom_in)
        self.ui.pushButton_zoom_out.setIcon(qta.icon('mdi6.magnify-minus-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_zoom_out.pressed.connect(self.zoom_out)
        self.ui.pushButton_rotate_counter.setIcon(
            qta.icon('mdi6.file-rotate-left-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_rotate_counter.pressed.connect(self.rotate_counter)
        self.ui.pushButton_rotate_clock.setIcon(
            qta.icon('mdi6.file-rotate-right-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_rotate_clock.pressed.connect(self.rotate_clockwise)
        self.ui.label_coded_area_icon.setPixmap(qta.icon('mdi6.grid').pixmap(22, 22))
        self.ui.pushButton_captions.setIcon(qta.icon('mdi6.closed-caption-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_captions.pressed.connect(self.captions_options)
        self.ui.pushButton_important.setIcon(qta.icon('mdi6.star-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_important.pressed.connect(self.show_important_coded)
        self.ui.pushButton_find_code.setIcon(qta.icon('mdi6.card-search-outline', options=[{'scale-factor': 1.2}]))
        self.ui.pushButton_find_code.pressed.connect(self.find_code_in_tree)
        # Widgets under File list
        self.ui.pushButton_latest.setIcon(qta.icon('mdi6.arrow-collapse-right', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_latest.pressed.connect(self.go_to_latest_coded_file)
        self.ui.pushButton_next_file.setIcon(qta.icon('mdi6.arrow-right', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_next_file.pressed.connect(self.go_to_next_file)
        self.ui.pushButton_document_memo.setIcon(qta.icon('mdi6.text-box-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_document_memo.pressed.connect(self.active_file_memo)
        self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_file_attributes.pressed.connect(self.get_files_from_attributes)
        # Header - Pdf widgets
        self.pdf_controls_toggle()
        self.ui.pushButton_next_page.setIcon(qta.icon('mdi6.arrow-right', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_next_page.pressed.connect(self.next_page)
        self.ui.pushButton_previous_page.setIcon(qta.icon('mdi6.arrow-left', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_previous_page.pressed.connect(self.previous_page)
        self.ui.pushButton_last_page.setIcon(qta.icon('mdi6.arrow-collapse-right', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_last_page.pressed.connect(self.last_page)
        self.ui.pushButton_goto_page.setIcon(qta.icon('mdi6.book-search-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_goto_page.pressed.connect(self.goto_page)
        self.ui.label_pdf.setPixmap(qta.icon('mdi6.file-pdf-box').pixmap(26, 26))

        try:
            s0 = int(self.app.settings['dialogcodeimage_splitter0'])
            s1 = int(self.app.settings['dialogcodeimage_splitter1'])
            # 30 is for the button box
            self.ui.splitter.setSizes([s0, 30, s1])
            h0 = int(self.app.settings['dialogcodeimage_splitter_h0'])
            h1 = int(self.app.settings['dialogcodeimage_splitter_h1'])
            if h0 > 1 and h1 > 1:
                self.ui.splitter_2.setSizes([h0, h1])
        except KeyError:
            pass
        self.ui.splitter.splitterMoved.connect(self.update_sizes)
        self.ui.splitter_2.splitterMoved.connect(self.update_sizes)
        self.fill_tree()
        # These signals after the tree is filled the first time
        self.ui.treeWidget.itemCollapsed.connect(self.get_collapsed)
        self.ui.treeWidget.itemExpanded.connect(self.get_collapsed)

    def update_sizes(self):
        """ Called by changed splitter sizes """

        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogcodeimage_splitter0'] = sizes[0]
        self.app.settings['dialogcodeimage_splitter1'] = sizes[2]
        sizes = self.ui.splitter_2.sizes()
        self.app.settings['dialogcodeimage_splitter_h0'] = sizes[0]
        self.app.settings['dialogcodeimage_splitter_h1'] = sizes[1]

    def get_codes_and_categories(self):
        """ Called from init, delete category/code, event_filter """

        self.codes, self.categories = self.app.get_codes_categories()

    def set_default_new_code_color(self):
        """ New code colours are usually generated randomly.
         This overrides the random approach, by setting a colout. """

        tmp_code = {'name': 'new', 'color': None}
        ui = DialogColorSelect(self.app, tmp_code)
        ok = ui.exec()
        if not ok:
            return
        color = ui.get_color()
        if color is not None:
            self.ui.pushButton_default_new_code_color.setStyleSheet(f'background-color: {color}')
        self.default_new_code_color = color

    def find_code_in_tree(self):
        """ Find a code by name in the codes tree and select it.
        """

        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        dialog.setWindowTitle(_("Search for code"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        msg = _("Find and select first code that matches text.") + "\n"
        msg += _("Enter text to match all or partial code:")
        dialog.setLabelText(msg)
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        search_text = dialog.textValue()

        # Remove selections and search for matching item text
        self.ui.treeWidget.setCurrentItem(None)
        self.ui.treeWidget.clearSelection()
        item = None
        iterator = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        while iterator.value():
            item = iterator.value()
            if "cid" in item.text(1):
                cid = int(item.text(1)[4:])
                code_ = next((code_ for code_ in self.codes if code_['cid'] == cid), None)
                if search_text in code_['name']:
                    self.ui.treeWidget.setCurrentItem(item)
                    break
            iterator += 1
        if item is None:
            Message(self.app, _("Match not found"), _("No code with matching text found.")).exec()
            return
        # Expand parents
        parent = item.parent()
        while parent is not None:
            parent.setExpanded(True)
            parent = parent.parent()

    def show_important_coded(self):
        """ Show codes flagged as important. """

        self.important = not self.important
        if self.important:
            self.ui.pushButton_important.setToolTip(_("Showing important codings"))
            self.ui.pushButton_important.setIcon(qta.icon('mdi6.star'))
        else:
            self.ui.pushButton_important.setToolTip(_("Show codings flagged important"))
            self.ui.pushButton_important.setIcon(qta.icon('mdi6.star-outline'))
        self.redraw_scene()

    def get_coded_areas(self):
        """ Get the coded area details for the rectangles for the image file by current coder.
        Order by area descending so when items are drawn to the scene. First largest to smallest on top.
        Called by load file, update_dialog_codes_and_categories,coded_media_dialog, undo_last_unmarked_code.
        """

        if self.file_ is None:
            return
        cur = self.app.conn.cursor()
        self.code_areas = []
        if self.pdf_page is not None:
            sql = "select imid,id,x1, y1, width, height, code_image.memo, code_image.date, code_image.owner, " \
                  "code_image.cid, important, code_name.name, code_name.color, pdf_page from code_image " \
                  "join code_name on code_name.cid=code_image.cid " \
                  " where code_image.id=? and code_image.owner=? and width > 0 and height > 0 and pdf_page=?" \
                  " order by width*height desc"
            cur.execute(sql, [self.file_['id'], self.app.settings['codername'], self.pdf_page])
        else:  # Images, jpg, png
            sql = "select imid,id,x1, y1, width, height, code_image.memo, code_image.date, code_image.owner, " \
                  "code_image.cid, important, code_name.name, code_name.color, pdf_page from code_image " \
                  "join code_name on code_name.cid=code_image.cid " \
                  " where code_image.id=? and code_image.owner=? and width > 0 and height > 0" \
                  " order by width*height desc"
            cur.execute(sql, [self.file_['id'], self.app.settings['codername']])
        results = cur.fetchall()
        keys = 'imid', 'id', 'x1', 'y1', 'width', 'height', 'memo', 'date', 'owner', 'cid', 'important', 'name', \
            'color', 'pdf_page'
        for row in results:
            self.code_areas.append(dict(zip(keys, row)))

    def get_files(self, ids=None):
        """ Load the image and pdf file data.
        Exclude those image and pdf file data where there are bad links.
        Fill List widget with the files.
        param:
            ids : list of Integer ids to restrict files """

        if ids is None:
            ids = []
        bad_links = self.app.check_bad_file_links()
        bad_link_sql = ""
        for bad_link in bad_links:
            bad_link_sql += f",{bad_link['id']}"
        if len(bad_link_sql) > 0:
            bad_link_sql = f' and id not in ({bad_link_sql[1:]}) '

        self.ui.listWidget.clear()
        cur = self.app.conn.cursor()
        sql = "select name, id, memo, owner, date, mediapath from source where "
        sql += "(substr(mediapath,1,7) in ('/images', 'images:')) or "
        sql += "(lower(substr(mediapath, -4)) = '.pdf') "
        sql += bad_link_sql + " "
        if ids:
            str_ids = list(map(str, ids))
            sql += " and id in (" + ",".join(str_ids) + ")"
        sql += " order by name"
        cur.execute(sql)
        result = cur.fetchall()
        self.files = []
        keys = 'name', 'id', 'memo', 'owner', 'date', 'mediapath'
        for row in result:
            self.files.append(dict(zip(keys, row)))
        for f in self.files:
            item = QtWidgets.QListWidgetItem(f['name'])
            item.setToolTip(f['memo'])
            self.ui.listWidget.addItem(item)
        self.clear_file()

    def get_files_from_attributes(self):
        """ Select files based on attribute selections.
        Attribute results are a dictionary of:
        first item is a Boolean AND or OR list item
        Followed by each attribute list item
        """

        # Clear ui
        self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
        ui = DialogSelectAttributeParameters(self.app)
        ui.fill_parameters(self.attributes)
        temp_attributes = deepcopy(self.attributes)
        self.attributes = []
        ok = ui.exec()
        if not ok:
            self.attributes = temp_attributes
            self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable'))
            self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
            if self.attributes:
                self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable-box'))
            return
        self.attributes = ui.parameters
        if len(self.attributes) == 1:
            self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable'))
            self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
            self.get_files()
            return
        if not ui.result_file_ids:
            Message(self.app, _("Nothing found") + " " * 20, _("No matching files found")).exec()
            self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable'))
            self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
            return
        self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable'))
        self.ui.pushButton_file_attributes.setToolTip(ui.tooltip_msg)
        self.get_files(ui.result_file_ids)

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes. """

        cats = deepcopy(self.categories)
        codes = deepcopy(self.codes)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(4)
        self.ui.treeWidget.setHeaderLabels([_("Name"), _("Id"), _("Memo"), _("Count")])
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
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                top_item.setToolTip(0, c['name'])
                if len(c['name']) > 52:
                    top_item.setText(0, c['name'][:25] + '..' + c['name'][-25:])
                    top_item.setToolTip(0, c['name'])
                top_item.setToolTip(2, c['memo'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                if f"catid:{c['catid']}" in self.app.collapsed_categories:
                    top_item.setExpanded(False)
                else:
                    top_item.setExpanded(True)
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
                    if item.text(1) == f"catid:{c['supercatid']}":
                        memo = ""
                        if c['memo'] != "":
                            memo = "Memo"
                        child = QtWidgets.QTreeWidgetItem([c['name'], f"catid:{c['catid']}", memo])
                        child.setToolTip(0, c['name'])
                        if len(c['name']) > 52:
                            child.setText(0, c['name'][:25] + '..' + c['name'][-25:])
                            child.setToolTip(0, c['name'])
                        child.setToolTip(2, c['memo'])
                        item.addChild(child)
                        if f"catid:{c['catid']}" in self.app.collapsed_categories:
                            child.setExpanded(False)
                        else:
                            child.setExpanded(True)
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
                top_item = QtWidgets.QTreeWidgetItem([c['name'], f"cid:{c['cid']}", memo])
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
                if item.text(1) == f"catid:{c['catid']}":
                    memo = ""
                    if c['memo'] != "":
                        memo = "Memo"
                    child = QtWidgets.QTreeWidgetItem([c['name'], f"cid:{c['cid']}", memo])
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
        # self.ui.treeWidget.expandAll()
        if self.tree_sort_option == "all asc":
            self.ui.treeWidget.sortByColumn(0, QtCore.Qt.SortOrder.AscendingOrder)
        if self.tree_sort_option == "all desc":
            self.ui.treeWidget.sortByColumn(0, QtCore.Qt.SortOrder.DescendingOrder)
        self.fill_code_counts_in_tree()

    def fill_code_counts_in_tree(self):
        """ Count instances of each code for current coder and in the selected file.
        Called by: fill_tree """

        if self.file_ is None:
            return
        cur = self.app.conn.cursor()
        sql = "select count(cid) from code_image where cid=? and id=? and owner=?"
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        count = 0
        while item and count < 10000:
            if item.text(1)[0:4] == "cid:":
                cid = str(item.text(1)[4:])
                cur.execute(sql, [cid, self.file_['id'], self.app.settings['codername']])
                result = cur.fetchone()
                if result[0] > 0:
                    item.setText(3, str(result[0]))
                else:
                    item.setText(3, "")
            it += 1
            item = it.value()
            count += 1

    def get_collapsed(self, item):
        """ On category collapse or expansion signal, find the collapsed parent category items.
        This will fill the self.app.collapsed_categories and is the expanded/collapsed tree is then replicated across
        other areas of the app. """

        #print(item.text(0), item.text(1), "Expanded:", item.isExpanded())
        if item.text(1)[:3] == "cid":
            return
        if not item.isExpanded() and item.text(1) not in self.app.collapsed_categories:
            self.app.collapsed_categories.append(item.text(1))
        if item.isExpanded() and item.text(1) in self.app.collapsed_categories:
            self.app.collapsed_categories.remove(item.text(1))

    def active_file_memo(self):
        """ Send active file to file_memo method.
        Called by pushButton_document_memo for loaded text.
        """

        self.file_memo(self.file_)

    def file_memo(self, file_):
        """ Open file memo to view or edit.
        Called by pushButton_document_memo for loaded text, via active_file_memo
        and through file_menu for any file.
        param: file_ : Dictionary of file values
        """

        if file_ is None:
            return
        ui = DialogMemo(self.app, _("Memo for file: ") + file_['name'], file_['memo'])
        ui.exec()
        memo = ui.memo
        if memo == file_['memo']:
            return
        file_['memo'] = memo
        cur = self.app.conn.cursor()
        cur.execute("update source set memo=? where id=?", (memo, file_['id']))
        self.app.conn.commit()
        self.get_files()
        self.ui.listWidget.clear()
        for f in self.files:
            item = QtWidgets.QListWidgetItem(f['name'])
            item.setToolTip(f['memo'])
            self.ui.listWidget.addItem(item)
        self.app.delete_backup = False

    def go_to_latest_coded_file(self):
        """ Vertical splitter button activates this """

        sql = "SELECT id FROM code_image where owner=? order by date desc limit 1"
        cur = self.app.conn.cursor()
        cur.execute(sql, [self.app.settings['codername'], ])
        result = cur.fetchone()
        if result is None:
            return
        for i, f in enumerate(self.files):
            if f['id'] == result[0]:
                self.file_ = f
                self.ui.listWidget.setCurrentRow(i)
                self.load_file()
                break

    def go_to_next_file(self):
        """ Vertical splitter button activates this.
         Assumes one or more items in the list widget.
         As the coding dialog will not open with no AV files. """

        if self.file_ is None:
            self.file_ = self.files[0]
            self.ui.listWidget.setCurrentRow(0)
            self.load_file()
            return
        for i in range(0, len(self.files) - 1):
            if self.file_ == self.files[i]:
                found = self.files[i + 1]
                self.file_ = found
                self.ui.listWidget.setCurrentRow(i + 1)
                self.load_file()
                return

    def file_menu(self, position):
        """ Context menu to select the next image alphabetically, or
         to select the image that was most recently coded """

        if len(self.files) == 0:
            return
        selected = self.ui.listWidget.currentItem()
        file_ = None
        for f in self.files:
            if selected.text() == f['name']:
                file_ = f
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_memo = menu.addAction(_("Open memo"))
        action_next = menu.addAction(_("Next file"))
        action_latest = menu.addAction(_("File with latest coding"))
        action_show_files_like = menu.addAction(_("Show files like"))
        action_show_case_files = menu.addAction(_("Show case files"))
        action_show_by_attribute = menu.addAction(_("Show files by attributes"))
        action = menu.exec(self.ui.listWidget.mapToGlobal(position))
        if action == action_memo:
            self.file_memo(file_)
        if action == action_next:
            self.go_to_next_file()
            return
        if action == action_latest:
            self.go_to_latest_coded_file()
            return
        if action == action_show_files_like:
            self.show_files_like()
        if action == action_show_case_files:
            self.show_case_files()
        if action == action_show_by_attribute:
            self.get_files_from_attributes()

    def show_case_files(self):
        """ Show files of specified case.
        Or show all files. """

        cases = self.app.get_casenames()
        cases.insert(0, {"name": _("Show all files"), "id": -1})
        ui = DialogSelectItems(self.app, cases, _("Select case"), "single")
        ok = ui.exec()
        if not ok:
            return
        selection = ui.get_selected()
        if not selection:
            return
        if selection['id'] == -1:
            self.get_files()
            return
        cur = self.app.conn.cursor()
        cur.execute('select fid from case_text where caseid=?', [selection['id']])
        res = cur.fetchall()
        file_ids = []
        for r in res:
            file_ids.append(r[0])
        self.get_files(file_ids)

    def show_files_like(self):
        """ Show files that contain specified filename text.
        If blank, show all files. """

        dialog = QtWidgets.QInputDialog(self)
        dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        dialog.setWindowTitle(_("Show files like"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog.setLabelText(_("Show files containing the text. (Blank for all)"))
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        text_ = str(dialog.textValue())
        if text_ == "":
            self.get_files()
            return
        cur = self.app.conn.cursor()
        cur.execute('select id from source where name like ?', ['%' + text_ + '%'])
        res = cur.fetchall()
        file_ids = [r[0] for r in res]
        '''for r in res:
            file_ids.append(r[0])'''
        self.get_files(file_ids)

    def file_selection_changed(self):
        """ Item selected so fill current file variable and load. """

        if len(self.files) == 0:
            return
        item_name = self.ui.listWidget.currentItem().text()
        for f in self.files:
            if f['name'] == item_name:
                self.file_ = f
                self.load_file()
                break

    def clear_file(self):
        """ When image removed clear all details.
        Called by null file in load_file, and from ManageFiles.delete. """

        self.file_ = None
        self.selection = None
        self.scale = 1.0
        items = list(self.scene.items())
        for i in range(items.__len__()):
            self.scene.removeItem(items[i])
        self.setWindowTitle(_("Image coding"))

    def pdf_controls_toggle(self, active=False):
        """ Toggle pdf controls on or off depending on file selection. """

        self.ui.pushButton_goto_page.setEnabled(active)
        self.ui.pushButton_last_page.setEnabled(active)
        self.ui.label_pages.setEnabled(active)
        self.ui.pushButton_next_page.setEnabled(active)
        self.ui.pushButton_previous_page.setEnabled(active)

    def goto_page(self):
        text, ok = QtWidgets.QInputDialog.getInt(None, 'Go to page', f'1 - {self.pdf_total_pages}')
        if not ok or not text:
            return
        self.pdf_page = int(text) - 1
        if self.pdf_page < 1:
            self.pdf_page = 0
        if self.pdf_page > self.pdf_total_pages - 1:
            self.pdf_page = self.pdf_total_pages - 1
        self.ui.label_pages.setText(f"{self.pdf_page + 1}/{self.pdf_total_pages}")
        self.load_file()

    def last_page(self):
        self.pdf_page = self.pdf_total_pages - 1
        self.ui.label_pages.setText(f"{self.pdf_page + 1}/{self.pdf_total_pages}")
        self.load_file()

    def next_page(self):
        self.pdf_page += 1
        if self.pdf_page > self.pdf_total_pages - 1:
            self.pdf_page = self.pdf_total_pages - 1
        self.ui.label_pages.setText(f"{self.pdf_page + 1}/{self.pdf_total_pages}")
        self.load_file()

    def previous_page(self):
        self.pdf_page -= 1
        if self.pdf_page < 0:
            self.pdf_page = 0
        self.ui.label_pages.setText(f"{self.pdf_page + 1}/{self.pdf_total_pages}")
        self.load_file()

    def load_file(self):
        """ Add image to scene if it exists. If not exists clear the GUI and variables.
        Called by: select_image_menu, file_selection_changed, pdf page changed
        """

        self.degrees = 0
        self.ui.label_coded_area.setText("Coded area")
        self.ui.label_coded_area.setToolTip("")
        image = None
        source_path = ""
        # Images source
        if self.file_['mediapath'][0:7] == "/images":
            source_path = self.app.project_path + self.file_['mediapath']  # Internal
            image = QtGui.QImage(source_path)
            self.pdf_controls_toggle()
            self.pdf_page = None
            self.pdf_total_pages = None
            self.ui.label_pages.setText("")
        if self.file_['mediapath'][0:7] == "images:":
            source_path = self.file_['mediapath'][7:]  # Linked
            image = QtGui.QImage(source_path)
            self.pdf_controls_toggle()
            self.pdf_page = None
            self.pdf_total_pages = None
            self.ui.label_pages.setText("")

        # PDF source
        if self.file_['mediapath'][-4:].lower() == ".pdf":
            if self.file_['mediapath'][:6] == "/docs/":
                source_path = f"{self.app.project_path}/documents/{self.file_['mediapath'][6:]}"
            if self.file_['mediapath'][:5] == "docs:":
                source_path = self.file_['mediapath'][5:]
            fitz_pdf = fitz.open(source_path)  # Use pymupdf to get page images
            if not self.pdf_page:
                self.pdf_page = 0
            self.pdf_total_pages = 0
            for page in fitz_pdf:
                self.pdf_total_pages += 1
                if page.number == self.pdf_page:
                    # Only need the current page image of interest
                    pixmap = page.get_pixmap()
                    pixmap.save(os.path.join(self.app.confighome, f"tmp_pdf_page.png"))

            source_path = os.path.join(self.app.confighome, f"tmp_pdf_page.png")
            image = QtGui.QImage(source_path)
            self.pdf_controls_toggle(True)
            self.ui.label_pages.setText(f"{self.pdf_page + 1}/{self.pdf_total_pages}")

        if image.isNull():
            self.clear_file()
            Message(self.app, _("Image Error"), _("Cannot open: ", "warning") + source_path).exec()
            logger.warning("Cannot open image: " + source_path)
            return

        items = list(self.scene.items())
        for i in range(items.__len__()):
            self.scene.removeItem(items[i])
        self.setWindowTitle(_("Image: ") + self.file_['name'])
        self.ui.pushButton_export.setEnabled(True)
        self.pixmap = QtGui.QPixmap.fromImage(image)
        pixmap_item = QtWidgets.QGraphicsPixmapItem(QtGui.QPixmap.fromImage(image))
        pixmap_item.setPos(0, 0)
        self.scene.setSceneRect(QtCore.QRectF(0, 0, self.pixmap.width(), self.pixmap.height()))
        self.scene.addItem(pixmap_item)
        self.ui.horizontalSlider.setValue(99)

        # Scale initial picture by height to mostly fit inside scroll area
        # Tried other methods e.g. sizes of components, but nothing was correct.
        # - 30 - 100   are slider and groupbox approx heights
        if self.pixmap.height() > self.height() - 30 - 100:
            scale = (self.height() - 30 - 100) / self.pixmap.height()
            slider_value = int(scale * 100)
            if slider_value > 100:
                slider_value = 100
            self.ui.horizontalSlider.setValue(slider_value)
        self.get_coded_areas()
        self.draw_coded_areas()
        self.fill_code_counts_in_tree()

    def update_dialog_codes_and_categories(self):
        """ Update code and category tree here and in DialogReportCodes, ReportCoderComparisons, ReportCodeFrequencies
        Using try except blocks for each instance, as instance may have been deleted. """

        self.get_codes_and_categories()
        self.fill_tree()
        self.get_coded_areas()
        self.draw_coded_areas()

        contents = self.tab_reports.layout()
        if contents:
            for i in reversed(range(contents.count())):
                c = contents.itemAt(i).widget()
                if isinstance(c, DialogReportCodes):
                    c.get_codes_categories_coders()
                    c.fill_tree()
                if isinstance(c, DialogReportCoderComparisons):
                    c.get_data()
                    c.fill_tree()
                if isinstance(c, DialogReportCodeFrequencies):
                    c.get_data()
                    c.fill_tree()

    def redraw_scene(self):
        """ Resize image. Triggered by user change in slider. Or resize or move of a coded area.
        Called by unmark, and Menu rotate action, as all items need to be redrawn. """

        if self.pixmap is None:
            return
        self.scale = (self.ui.horizontalSlider.value() + 1) / 100
        height = int(self.scale * self.pixmap.height())
        pixmap = self.pixmap.scaledToHeight(height, QtCore.Qt.TransformationMode.FastTransformation)
        transform = QtGui.QTransform().rotate(self.degrees)
        pixmap = pixmap.transformed(transform)
        pixmap_item = QtWidgets.QGraphicsPixmapItem(pixmap)
        pixmap_item.setPos(0, 0)
        self.scene.clear()
        self.scene.addItem(pixmap_item)
        self.draw_coded_areas()
        scale_text = _("Scale: ") + f"{int(self.scale * 100)}%"
        self.ui.horizontalSlider.setToolTip(scale_text)
        msg = _("Width") + f": {self.pixmap.width()} " + _("Height") + f": {self.pixmap.height()}\n"
        msg += f"{scale_text} " + _("Rotation") + f": {self.degrees}\u00b0"
        self.ui.label_image.setText(msg)

    def draw_coded_areas(self):
        """ Draw coded areas with scaling. This coder is shown in dashed rectangles.
        Other coders are shown via dotline rectangles.
        Remove items first, as this is called after a coded area is unmarked. """

        if self.file_ is None:
            return
        # Error catch re pdf coded areas. some coded areas still present even if page changed by 1
        if self.pdf_page is not None:
            tmp_coded_areas = []
            for area in self.code_areas:
                if area['pdf_page'] == self.pdf_page:
                    tmp_coded_areas.append(area)
            self.code_areas = tmp_coded_areas

        for coded in self.code_areas:
            if coded['id'] == self.file_['id']:
                color = None
                tooltip = ""
                code_name = ""
                code_memo = ""
                for c in self.codes:
                    if c['cid'] == coded['cid']:
                        code_name = c['name']
                        code_memo = c['memo']
                        tooltip = f"{c['name']} ({coded['owner']})"
                        if self.app.settings['showids']:
                            tooltip += f"[imid:{coded['imid']}]"
                        if coded['memo'] != "":
                            tooltip += f"\nMemo: {coded['memo']}"
                            code_memo = f"\nMemo: {coded['memo']}"
                        if coded['important'] == 1:
                            tooltip += "\n" + _("IMPORTANT")
                        color = QtGui.QColor(c['color'])
                # Warn of exact overlapping code(s)
                overlaps = ""
                for coded2 in self.code_areas:
                    if coded2['x1'] == coded['x1'] and coded2['y1'] == coded['y1'] and \
                            coded2['width'] == coded['width'] and coded2['height'] == coded['height'] and \
                            coded2['owner'] == coded['owner'] and coded2['cid'] != coded['cid']:
                        code_name2 = ""
                        for c2 in self.codes:
                            if c2['cid'] == coded2['cid']:
                                code_name2 = c2['name']
                                break
                        overlaps += "\n" + _("Overlaps exactly with") + f": {code_name2}\n"
                if overlaps:
                    tooltip += overlaps

                # Degrees 0
                x = coded['x1'] * self.scale
                y = coded['y1'] * self.scale
                width = coded['width'] * self.scale
                height = coded['height'] * self.scale
                if self.degrees == 90:
                    y = (coded['x1']) * self.scale
                    x = (self.pixmap.height() - coded['y1'] - coded['height']) * self.scale
                    height = coded['width'] * self.scale
                    width = coded['height'] * self.scale
                if self.degrees == 180:
                    x = (self.pixmap.width() - coded['x1'] - coded['width']) * self.scale
                    y = (self.pixmap.height() - coded['y1'] - coded['height']) * self.scale
                    width = coded['width'] * self.scale
                    height = coded['height'] * self.scale
                if self.degrees == 270:
                    y = (self.pixmap.width() - coded['x1'] - coded['width']) * self.scale
                    x = (coded['y1']) * self.scale
                    height = coded['width'] * self.scale
                    width = coded['height'] * self.scale
                rect_item = QtWidgets.QGraphicsRectItem(x, y, width, height)
                rect_item.setPen(QtGui.QPen(color, 2, QtCore.Qt.PenStyle.DashLine))
                rect_item.setToolTip(tooltip)
                if coded['owner'] == self.app.settings['codername']:
                    if self.important and coded['important'] == 1:
                        self.scene.addItem(rect_item)
                    if not self.important:
                        self.scene.addItem(rect_item)
                if self.show_code_captions == 1:
                    self.caption(x, y, code_name)
                if self.show_code_captions == 2:
                    self.caption(x, y, code_name + code_memo)

    def captions_options(self):
        """ Hide captions (0). Show captions (1). Show captions with memos (2) """

        self.show_code_captions += 1
        if self.show_code_captions > 2:
            self.show_code_captions = 0
        self.redraw_scene()

    def caption(self, x, y, code_name):
        """ Add captions to coded areas. """

        text_item = QtWidgets.QGraphicsTextItem()
        text_item.setDefaultTextColor(QtGui.QColor("#000000"))
        html_text = code_name.replace('\n', '<br />')
        text_item.setHtml(f"<div style='background-color:#FFFFFF;'>{html_text}</div>")
        # Style.StyleNormal 400  Segoe UI 9
        text_item.setPos(x, y)
        self.scene.addItem(text_item)

    def export_html_file(self):
        """ Export the QGraphicsScene as a png image with transparent background.
               Called by QButton_export.
               """

        filename = self.file_['name'].replace(".", "_") + ".html"
        export_dir = ExportDirectoryPathDialog(self.app, filename)
        filepath = export_dir.filepath
        if filepath is None:
            return
        pic_width = self.pixmap.width() * self.scale
        pic_height = self.pixmap.height() * self.scale
        if self.degrees in (90, 270):
            pic_width, pic_height = pic_height, pic_width
        rect_area = QtCore.QRectF(0.0, 0.0, pic_width, pic_height)
        image = QtGui.QImage(int(pic_width), int(pic_height), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        # Render method requires QRectF NOT QRect
        self.scene.render(painter, QtCore.QRectF(image.rect()), rect_area)
        painter.end()
        # Convert to base64 as String not bytes
        byte_array = QtCore.QByteArray()
        buffer = QBuffer(byte_array)
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        image.save(buffer, 'PNG')
        base64_string = byte_array.toBase64().data().decode("UTF-8")
        # Create html file
        h = "<!DOCTYPE html>\n<html>\n<head>\n<title>Coded Image</title>\n</head>\n"
        h += "<body>\n<div>\n"
        h += f"<h1>{html.escape(filename)}</h1>\n"
        h += '<img src="data:image/png;base64,' + base64_string + '" usemap="#coded_areas" />'
        # Create image map
        h += "<map name='coded_areas'>\n"
        for c in self.code_areas:
            # Coordinates are x1,y1 to x2,y2 for a rectangle. Adjust for scale and rotation.
            # Degrees 0
            x1 = c['x1'] * self.scale
            y1 = c['y1'] * self.scale
            x2 = x1 + c['width'] * self.scale
            y2 = y1 + c['height'] * self.scale
            if self.degrees == 90:
                y1 = (c['x1']) * self.scale
                x1 = (self.pixmap.height() - c['y1'] - c['height']) * self.scale
                y2 = y1 + c['width'] * self.scale
                x2 = x1 + c['height'] * self.scale
            if self.degrees == 180:
                x1 = (self.pixmap.width() - c['x1'] - c['width']) * self.scale
                y1 = (self.pixmap.height() - c['y1'] - c['height']) * self.scale
                x2 = x1 + c['width'] * self.scale
                y2 = y1 + c['height'] * self.scale
            if self.degrees == 270:
                y1 = (self.pixmap.width() - c['x1'] - c['width']) * self.scale
                x1 = (c['y1']) * self.scale
                y2 = y1 + c['width'] * self.scale
                x2 = x1 + c['height'] * self.scale
            tag = '<area shape="rect" coords="' + str(x1) + "," + str(y1) + ","
            tag += str(x2) + "," + str(y2) + '" '
            tag += 'title="' + html.escape(c['name'])
            if c['memo'] != "":
                tag += html.escape('\n' + c['memo'])
            tag += '" href="#1" >\n'
            h += tag
        h += "</map>\n"
        if self.file_['memo'] != "":
            h += '<h2>Image memo</h2>\n'
            h += f"<p>{html.escape(self.file_['memo'])}</p>\n"
        h += "</div>\n</body>\n</html>"
        with open(filepath, 'w', encoding='utf-8-sig') as f:
            f.write(h)
        Message(self.app, _("Image exported"), filepath).exec()

    def tree_menu(self, position):
        """ Context menu for treewidget items.
        Add, rename, memo, move or delete code or category. Change code color. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        selected = self.ui.treeWidget.currentItem()
        action_add_code_to_category = None
        action_add_category_to_category = None
        action_merge_category = None
        if selected is not None and selected.text(1)[0:3] == 'cat':
            action_add_code_to_category = menu.addAction(_("Add new code to category"))
            action_add_category_to_category = menu.addAction(_("Add a new category to category"))
            action_merge_category = menu.addAction(_("Merge category into category"))
        action_add_code = menu.addAction(_("Add a new code"))
        action_add_category = menu.addAction(_("Add a new category"))
        action_rename = menu.addAction(_("Rename"))
        action_edit_memo = menu.addAction(_("View or edit memo"))
        action_delete = menu.addAction(_("Delete"))
        action_color = None
        action_show_coded_media = None
        action_move_code = None
        if selected is not None and selected.text(1)[0:3] == 'cid':
            action_color = menu.addAction(_("Change code color"))
            action_move_code = menu.addAction(_("Move code to"))
            action_show_coded_media = menu.addAction(_("Show coded text and media"))
        action_show_codes_like = menu.addAction(_("Show codes like"))
        action_show_codes_of_colour = menu.addAction(_("Show codes of colour"))
        action_all_asc = menu.addAction(_("Sort ascending"))
        action_all_desc = menu.addAction(_("Sort descending"))
        action_cat_then_code_asc = menu.addAction(_("Sort category then code ascending"))
        action = menu.exec(self.ui.treeWidget.mapToGlobal(position))
        if action is None:
            return
        if action == action_show_codes_of_colour:
            self.show_codes_of_color()
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
        if selected is not None and selected.text(1)[0:3] == 'cid' and action == action_color:
            self.change_code_color(selected)
        if selected is not None and action == action_move_code:
            self.move_code(selected)
        if action == action_add_category:
            self.add_category()
        if action == action_add_category_to_category:
            catid = int(selected.text(1).split(":")[1])
            self.add_category(catid)
        if action == action_add_code:
            self.add_code()
        if action == action_merge_category:
            catid = int(selected.text(1).split(":")[1])
            self.merge_category(catid)
        if action == action_add_code_to_category:
            catid = int(selected.text(1).split(":")[1])
            self.add_code(catid)
        if action == action_show_codes_like:
            self.show_codes_like()
            return
        if selected is not None and action == action_rename:
            self.rename_category_or_code(selected)
        if selected is not None and action == action_edit_memo:
            self.add_edit_code_memo(selected)
        if selected is not None and action == action_delete:
            self.delete_category_or_code(selected)
        if selected is not None and action == action_show_coded_media:
            found = None
            to_find = int(selected.text(1)[4:])
            for code in self.codes:
                if code['cid'] == to_find:
                    found = code
                    break
            if found:
                self.coded_media_dialog(found)

    def coded_media_dialog(self, code_dict):
        """ Display all coded media for this code, in a separate modal dialog.
        Coded media comes from ALL files for this coder.
        Need to store textedit start and end positions so that code in context can be used.
        Called from tree_menu.
        Re-load the codings may have changed.
        param:
            code_dict : code dictionary
        """

        DialogCodeInAllFiles(self.app, code_dict)
        self.get_coded_areas()
        self.redraw_scene()

    def move_code(self, selected):
        """ Move code to another category or to no category in the tree.
        Uses a list selection.
        param:
            selected : QTreeWidgetItem
         """

        cid = int(selected.text(1)[4:])
        cur = self.app.conn.cursor()
        cur.execute("select name, catid from code_cat order by name")
        res = cur.fetchall()
        category_list = [{'name': "", 'catid': None}]
        for r in res:
            category_list.append({'name': r[0], 'catid': r[1]})
        ui = DialogSelectItems(self.app, category_list, _("Select blank or category"), "single")
        ok = ui.exec()
        if not ok:
            return
        category = ui.get_selected()
        cur.execute("update code_name set catid=? where cid=?", [category['catid'], cid])
        self.update_dialog_codes_and_categories()

    def show_codes_like(self):
        """ Show all codes if text parameter is empty.
         Show selected codes that contain entered text.
         Input dialog is narrow, so some code below to make it wider. """

        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        dialog.setWindowTitle(_("Show codes containing"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog.setLabelText(_("Show codes containing text.\n(Blank for all)"))
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        txt = str(dialog.textValue())
        root = self.ui.treeWidget.invisibleRootItem()
        self.recursive_traverse(root, txt)

    def show_codes_of_color(self):
        """ Show all codes in colour range in code tree., ir all codes if no selection.
        Show selected codes that are of a selected colour.
        """

        ui = DialogSelectItems(self.app, colour_ranges, _("Select code colors"), "single")
        ok = ui.exec()
        if not ok:
            return
        selected_color = ui.get_selected()
        show_codes_of_colour_range(self.app, self.ui.treeWidget, self.codes, selected_color)

    def recursive_traverse(self, item, text_):
        """ Find all children codes of this item that match or not and hide or unhide based on 'text'.
        Recurse through all child categories.
        Called by: show_codes_like
        param:
            item: a QTreeWidgetItem
            text_:  Text string for matching with code names
        """

        child_count = item.childCount()
        for i in range(child_count):
            if "cid:" in item.child(i).text(1) and len(text_) > 0 and \
                    (text_ not in item.child(i).text(0) or text_ not in item.child(i).toolTip(0)):
                item.child(i).setHidden(True)
            if "cid:" in item.child(i).text(1) and text_ == "":
                item.child(i).setHidden(False)
            self.recursive_traverse(item.child(i), text_)

    def keyPressEvent(self, event):
        """
        Ctrl Z Undo last unmarking
        H hide / show top group box
        Ctrl 0 to Ctrl 9 - button presses
        + or W  Zoom out
        - or Q Zoom in
        Ctrl 0 to Ctrl 5 Buttons and Help
        Ctrl G - Gray image with highlighted codings
        L Show codes like
        """

        key = event.key()
        mods = event.modifiers()

        if key == QtCore.Qt.Key.Key_H:
            self.ui.groupBox_2.setHidden(not (self.ui.groupBox_2.isHidden()))
            return
        # Show codes like
        if key == QtCore.Qt.Key.Key_L:
            self.show_codes_like()
        # Ctrl Z undo last unmarked coding
        if key == QtCore.Qt.Key.Key_Z and mods == QtCore.Qt.KeyboardModifier.ControlModifier:
            self.undo_last_unmarked_code()
            return
        if key == QtCore.Qt.Key.Key_Minus or key == QtCore.Qt.Key.Key_Q:
            self.zoom_out()
            return
        if key == QtCore.Qt.Key.Key_Plus or key == QtCore.Qt.Key.Key_W:
            self.zoom_in()
            return
        # Ctrl 0 to 9, G
        if mods & QtCore.Qt.KeyboardModifier.ControlModifier:
            if key == QtCore.Qt.Key.Key_G:
                self.image_highlight("gray")
                return
            if key == QtCore.Qt.Key.Key_1:
                self.go_to_next_file()
                return
            if key == QtCore.Qt.Key.Key_2:
                self.go_to_latest_coded_file()
                return
            if key == QtCore.Qt.Key.Key_3:
                self.file_memo(self.file_)
                return
            if key == QtCore.Qt.Key.Key_4:
                self.get_files_from_attributes()
                return
            if key == QtCore.Qt.Key.Key_5:
                self.show_important_coded()
                return
            if key == QtCore.Qt.Key.Key_0:
                self.help()
                return

    def zoom_out(self):
        v = self.ui.horizontalSlider.value()
        v -= 3
        if v < self.ui.horizontalSlider.minimum():
            return
        self.ui.horizontalSlider.setValue(v)

    def zoom_in(self):
        v = self.ui.horizontalSlider.value()
        v += 3
        if v > self.ui.horizontalSlider.maximum():
            return
        self.ui.horizontalSlider.setValue(v)

    def image_highlight(self, image_operation="gray", coded_area=None, code_id=None):
        """ Gray, blurred or solarised image with coloured coded highlight(s).
        Highlight all coded area, or selected coded area, or all areas coded by one specific code.
        Takes a few seconds to build and show image.
        :param: coded_area Dictionary of coded area
        :param: coded_id Integer code id
        """

        img = self.pixmap.toImage()
        buffer = QBuffer()
        buffer.open(QBuffer.ReadWrite)
        img.save(buffer, "PNG")
        pil_img = Image.open(BytesIO(buffer.data()))
        background = ImageOps.grayscale(pil_img)  # Default gray
        if image_operation == "solarize":
            background = ImageOps.solarize(pil_img)  # Invert all pixel values above a threshold.
        if image_operation == "blur":
            background = pil_img.filter(ImageFilter.GaussianBlur(radius=10))
        highlights = Image.new('RGB', (background.width, background.height))
        highlights.paste(background, (0, 0))
        draw = ImageDraw.Draw(highlights)
        if coded_area:
            # Highlight ONE coded area
            try:
                # Needs tuple of left, top, right, bottom
                coded_img = pil_img.crop((coded_area['x1'], coded_area['y1'], coded_area['x1'] + coded_area['width'],
                                          coded_area['y1'] + coded_area['height']))
                img_with_border = ImageOps.expand(coded_img, border=3, fill=coded_area['color'])
                # highlights.paste(coded_img, (int(ca['x1']), int(ca['y1']))) # No border
                highlights.paste(img_with_border, (int(coded_area['x1']), int(coded_area['y1'])))
                self.text_box(draw, background.width, (coded_area['x1'], coded_area['y1']), coded_area['name'],
                              coded_area['memo'])
            except SystemError as e_:
                logger.debug(e_)
        else:
            # Highlight all coded areas
            for coded in self.code_areas:
                try:
                    # Needs tuple of left, top, right, bottom
                    coded_img = pil_img.crop(
                        (coded['x1'], coded['y1'], coded['x1'] + coded['width'], coded['y1'] + coded['height']))
                    img_with_border = ImageOps.expand(coded_img, border=3, fill=coded['color'])
                    if code_id == coded['cid']:
                        # Specific code id selected to highlight all of this code
                        highlights.paste(img_with_border, (int(coded['x1']), int(coded['y1'])))
                        self.text_box(draw, background.width, (coded['x1'], coded['y1']), coded['name'], coded['memo'])
                    if not code_id:
                        # No specific code or coded area selected.
                        highlights.paste(img_with_border, (int(coded['x1']), int(coded['y1'])))
                        self.text_box(draw, background.width, (coded['x1'], coded['y1']), coded['name'], coded['memo'])
                except SystemError as e_:
                    logger.debug(e_)
                    print(e_)
                    print("Crop img: x1", coded['x1'], "y1", coded['y1'], "x2", coded['x1'] + coded['width'], "y2",
                          coded['y1'] + coded['height'])
                    print("Main img: w", background.width, "h", background.height)
        highlights.show()

    def text_box(self, draw, background_width, position, text, memo):
        """ Draw codename caption if show_code_captions=1, or codename plus memo if show_code_captions=2. """

        if self.show_code_captions == 0:
            return
        font = ImageFont.load_default()
        try:
            font_path = os.path.join(self.app.confighome, 'DroidSansMono.ttf')
            font = ImageFont.truetype(font_path, size=int(background_width / 90))
        except OSError:
            pass
        if self.show_code_captions == 2 and memo != "":
            text += "\n" + memo
        bounding_box = draw.textbbox(position, text, font=font)
        draw.rectangle(bounding_box, fill="white")
        draw.text(position, text, font=font, fill="black")

    @staticmethod
    def help():
        """ Open help for transcribe section in browser. """

        url = "https://github.com/ccbogel/QualCoder/wiki/4.4.-Coding-Images"
        webbrowser.open(url)

    def eventFilter(self, object_, event):
        """ Using this event filter to identify treeWidgetItem drop events.
        http://doc.qt.io/qt-5/qevent.html#Type-enum
        QEvent::Drop	63	A drag and drop operation is completed (QDropEvent).
        https://stackoverflow.com/questions/28994494/why-does-qtreeview-not-fire-a-drop-or-move-event-during-drag-and-drop
        Also use eventFilter for QGraphicsView.
        """

        if object_ is self.ui.treeWidget.viewport():
            if event.type() == QtCore.QEvent.Type.Drop:
                item = self.ui.treeWidget.currentItem()
                # event position is QPointF, itemAt requires toPoint
                parent = self.ui.treeWidget.itemAt(event.position().toPoint())
                self.item_moved_update_data(item, parent)
                self.update_dialog_codes_and_categories()
                return True
        if object_ is self.scene:
            if type(event) == QtWidgets.QGraphicsSceneMouseEvent and event.button() == Qt.MouseButton.LeftButton:
                pos = event.buttonDownScenePos(Qt.MouseButton.LeftButton)
                self.fill_coded_area_label(self.find_coded_areas_for_pos(pos))
                if event.type() == QtCore.QEvent.Type.GraphicsSceneMousePress:
                    p0 = event.buttonDownScenePos(Qt.MouseButton.LeftButton)
                    self.selection = p0
                    return True
                if event.type() == QtCore.QEvent.Type.GraphicsSceneMouseRelease:
                    p1 = event.lastScenePos()
                    self.create_code_area(p1)
                    return True
            if type(event) == QtWidgets.QGraphicsSceneMouseEvent and event.button() == Qt.MouseButton.RightButton:
                if event.type() == QtCore.QEvent.Type.GraphicsSceneMousePress:
                    p = event.buttonDownScenePos(Qt.MouseButton.RightButton)
                    self.scene_context_menu(p)
                    return True
        return False

    def scene_context_menu(self, pos):
        """ Scene context menu for setting importance, unmarking coded areas and adding memos. """

        # Outside image area, no context menu
        for item in self.scene.items():
            if type(item) == QtWidgets.QGraphicsPixmapItem:
                if pos.x() > item.boundingRect().width() or pos.y() > item.boundingRect().height():
                    self.selection = None
                    return
        global_pos = QtGui.QCursor.pos()
        items = self.find_coded_areas_for_pos(pos)
        # Menu for show/hide top panel
        if not items:
            menu = QtWidgets.QMenu()
            menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            action_rotate = menu.addAction(_("Rotate clockwise"))
            action_rotate_counter = menu.addAction(_("Rotate counter-clockwise"))
            action_highlight_gray = menu.addAction(_("Highlight area - gray"))
            action_highlight_solarize = menu.addAction(_("Highlight area - solarize"))
            action_highlight_blur = menu.addAction(_("Highlight area - blur"))
            action_hide_top_groupbox = None
            action_show_top_groupbox = None
            if self.ui.groupBox_2.isHidden():
                action_show_top_groupbox = menu.addAction(_("Show control panel"))
            if not self.ui.groupBox_2.isHidden():
                action_hide_top_groupbox = menu.addAction(_("Hide control panel"))
            action = menu.exec(global_pos)
            if action is None:
                return
            if action == action_highlight_gray:
                self.image_highlight()
            if action == action_highlight_solarize:
                self.image_highlight("solarize")
            if action == action_highlight_blur:
                self.image_highlight("blur")
            if action == action_show_top_groupbox:
                self.ui.groupBox_2.setVisible(True)
            if action == action_hide_top_groupbox:
                self.ui.groupBox_2.setVisible(False)
            if action == action_rotate:
                self.rotate_clockwise()
            if action == action_rotate_counter:
                self.rotate_counter()
            return
        item = items[0]
        if len(items) > 1:
            ui = DialogSelectItems(self.app, items, _("Select code"), "single")
            ok = ui.exec()
            if not ok:
                return
            item = ui.get_selected()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_memo = menu.addAction(_('Memo'))
        action_unmark = menu.addAction(_('Unmark'))
        action_move_resize = menu.addAction(_("Move or resize"))
        action_important = None
        if item['important'] is None or item['important'] != 1:
            action_important = menu.addAction(_("Add important mark"))
        action_not_important = None
        if item['important'] == 1:
            action_not_important = menu.addAction(_("Remove important mark"))
        action_highlight_gray = menu.addAction(_("Highlight this area - gray"))
        action_highlight_solarize = menu.addAction(_("Highlight this area - solarize"))
        action_highlight_blur = menu.addAction(_("Highlight this area - blur"))
        action_highlight_code_gray = menu.addAction(_("Highlight this code - gray"))
        action_highlight_code_solarize = menu.addAction(_("Highlight this code - solarize"))
        action_highlight_code_blur = menu.addAction(_("Highlight this code - blur"))

        action = menu.exec(global_pos)
        if action is None:
            return
        if action == action_highlight_gray:
            self.image_highlight("gray", item)
        if action == action_highlight_code_gray:
            self.image_highlight("gray", None, item['cid'])
        if action == action_highlight_solarize:
            self.image_highlight("solarize", item)
        if action == action_highlight_code_solarize:
            self.image_highlight("solarize", None, item['cid'])
        if action == action_highlight_blur:
            self.image_highlight("blur", item)
        if action == action_highlight_code_blur:
            self.image_highlight("blur", None, item['cid'])

        if action == action_memo:
            self.coded_area_memo(item)
        if action == action_unmark:
            self.unmark(item)
        if action == action_important:
            self.set_coded_importance(item)
        if action == action_not_important:
            self.set_coded_importance(item, False)
        if action == action_move_resize:
            self.move_or_resize_coding(item)
        items = self.find_coded_areas_for_pos(pos)
        self.fill_coded_area_label(items)

    def rotate_clockwise(self):
        self.degrees += 90
        if self.degrees > 270:
            self.degrees = 0
        self.redraw_scene()

    def rotate_counter(self):
        self.degrees -= 90
        if self.degrees < 0:
            self.degrees = 270
        self.redraw_scene()

    def move_or_resize_coding(self, item):
        """ Move or resize a coding rectangle, in pixels.

        params:
        :name item: Dictionary of image id, x1, y1, width, height, memo, date, owner, cid, important
        """

        ui = DialogMoveResizeRectangle(self.app)
        ui.exec()
        item['x1'] += ui.move_x
        if item['x1'] < 0:
            item['x1'] = 0
        # x is past the image size, so resize to 10 wide and 11 back from image x edge
        if item['x1'] + 11 > self.pixmap.width():
            item['x1'] = self.pixmap.width() - 11
            item['width'] = 10
        item['y1'] += ui.move_y
        if item['y1'] < 0:
            item['y1'] = 0
        # y is past the image size, so resize to 10 wide and 11 back from image y edge
        if item['y1'] + 11 > self.pixmap.height():
            item['y1'] = self.pixmap.height() - 11
            item['height'] = 10
        item['width'] += ui.resize_x
        if item['width'] < 10:
            item['width'] = 10
        if item['x1'] + item['width'] > self.pixmap.width():
            overreach = item['x1'] + item['width'] - self.pixmap.width()
            item['width'] -= overreach + 1
        item['height'] += ui.resize_y
        if item['height'] < 10:
            item['height'] = 10
        if item['y1'] + item['height'] > self.pixmap.height():
            overreach = item['y1'] + item['height'] - self.pixmap.height()
            item['height'] -= overreach + 1
        cur = self.app.conn.cursor()
        cur.execute("update code_image set x1=?,y1=?,width=?,height=? where imid=?",
                    (item['x1'], item['y1'], item['width'], item['height'], item['imid']))
        self.app.conn.commit()
        self.redraw_scene()
        self.app.delete_backup = False

    def find_coded_areas_for_pos(self, pos):
        """ Find any coded areas for this position AND for this coder.

        params:
        :name pos:
        :type pos:
        returns: [] or coded items
        """

        if self.file_ is None:
            return
        # Reposition pos based on rotation
        pix_h_scaled = self.pixmap.height() * self.scale
        pix_w_scaled = self.pixmap.width() * self.scale
        if self.degrees == 90:
            pos = QtCore.QPointF(pos.y(), pix_h_scaled - pos.x())
        if self.degrees == 180:
            pos = QtCore.QPointF(pix_w_scaled - pos.x(), pix_h_scaled - pos.y())
        if self.degrees == 270:
            pos = QtCore.QPointF(pix_w_scaled - pos.y(), pos.x())
        items = []
        for item in self.code_areas:
            if item['id'] == self.file_['id'] and item['owner'] == self.app.settings['codername']:
                if item['x1'] * self.scale <= pos.x() <= (item['x1'] + item['width']) * self.scale \
                        and item['y1'] * self.scale <= pos.y() <= (
                        item['y1'] + item['height']) * self.scale:
                    items.append(item)
        return items

    def fill_coded_area_label(self, items):
        """ Fill details of label about the currently clicked on coded area.
        Called by: right click scene menu, """

        if not items:
            return
        msg = ""
        tooltip = ""
        for i in items:
            for c in self.codes:
                if c['cid'] == i['cid']:
                    codename = c['name']
                    msg += codename
            msg += f"\nx:{int(i['x1'])} y:{int(i['y1'])}"
            msg += f" w:{int(i['width'])} h:{int(i['height'])}"
            area = i['width'] * i['height']
            pic_area = self.pixmap.width() * self.pixmap.height()
            percent_area = round(area / pic_area * 100, 2)
            msg += f" area: {percent_area}%\n"
            tooltip = msg + "\n" + i['memo']
        self.ui.label_coded_area.setText(msg)
        self.ui.label_coded_area.setToolTip(tooltip)

    def set_coded_importance(self, item, important=True):
        """ Set or unset importance to coded image item.
        Importance is denoted using '1'
        params:
            item: dictionary of coded area
            important: boolean, default True """

        importance = None
        if important:
            importance = 1
        item['important'] = importance
        cur = self.app.conn.cursor()
        cur.execute('update code_image set important=? where imid=?', (importance, item['imid']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.draw_coded_areas()

    def coded_area_memo(self, item):
        """ Add memo to this coded area.
        param:
            item : dictionary of coded area """

        ui = DialogMemo(self.app, _("Memo for code: ") + item['name'],
                        item['memo'])
        ui.exec()
        memo = ui.memo
        if memo != item['memo']:
            item['memo'] = memo
            cur = self.app.conn.cursor()
            cur.execute('update code_image set memo=? where imid=?', (ui.memo, item['imid']))
            self.app.conn.commit()
            self.app.delete_backup = False
        # Re-draw to update memos in tooltips
        self.draw_coded_areas()

    def undo_last_unmarked_code(self):
        """ Restore the last deleted code.
        Requires self.undo_deleted_code """

        if not self.undo_deleted_code:
            return
        item = self.undo_deleted_code
        cur = self.app.conn.cursor()
        cur.execute(
            "insert into code_image (id,x1,y1,width,height,cid,memo,date,owner, important, pdf_page) "
            "values(?,?,?,?,?,?,?,?,?,?,?)",
            (item['id'], item['x1'], item['y1'], item['width'], item['height'], item['cid'], item['memo'],
             item['date'], item['owner'], item['important'], item['pdf_page']))
        self.app.conn.commit()
        self.undo_deleted_code = []
        self.get_coded_areas()
        self.redraw_scene()
        self.fill_code_counts_in_tree()
        self.app.delete_backup = False

    def unmark(self, item):
        """ Remove coded area.
        param:
            item : dictionary of coded area """

        self.undo_deleted_code = deepcopy(item)
        cur = self.app.conn.cursor()
        cur.execute("delete from code_image where imid=?", [item['imid'], ])
        self.app.conn.commit()
        self.get_coded_areas()
        self.redraw_scene()
        self.fill_code_counts_in_tree()
        self.app.delete_backup = False

    def create_code_area(self, p1):
        """ Create coded area coordinates from mouse release.
        The point and width and height must be based on the original image size,
        so add in scale factor.
        param:
            p1 : QtCore.QPointF of mouse release """

        if self.pixmap is None:
            return
        code_ = self.ui.treeWidget.currentItem()
        if code_ is None:
            return
        if code_.text(1)[0:3] == 'cat':
            return
        cid = int(code_.text(1)[4:])  # must be integer
        code_name = code_.text(0)
        pix_h_scaled = self.pixmap.height() * self.scale
        pix_w_scaled = self.pixmap.width() * self.scale
        width = p1.x() - self.selection.x()
        height = p1.y() - self.selection.y()
        x = self.selection.x()
        y = self.selection.y()
        # Reposition x and y and width, height based on rotation
        if self.degrees == 90:
            x = y
            # Need to use the p1 x point (mouse release point) as the y low values are reversed on the right hand side
            y = pix_h_scaled - p1.x()
            width, height = height, width
        if self.degrees == 180:
            x = pix_w_scaled - p1.x()
            y = pix_h_scaled - p1.y()
        if self.degrees == 270:
            y = x
            # Need to use the p1 y point (mouse release point) as the y low values are reversed on the left hand side
            x = pix_w_scaled - p1.y()
            width, height = height, width
        if width < 0:
            x = x + width
            width = abs(width)
        if height < 0:
            y = y + height
            height = abs(height)
        # Outside image area, do not code
        for item in self.scene.items():
            if type(item) == QtWidgets.QGraphicsPixmapItem:
                if x + width > item.boundingRect().width() or y + height > item.boundingRect().height():
                    self.selection = None
                    return
        x_unscaled = round(x / self.scale)
        y_unscaled = round(y / self.scale)
        width_unscaled = round(width / self.scale)
        height_unscaled = round(height / self.scale)
        if width_unscaled < 10 or height_unscaled < 10:
            return
        item = {'imid': None, 'id': self.file_['id'], 'x1': x_unscaled, 'y1': y_unscaled,
                'width': width_unscaled, 'height': height_unscaled, 'owner': self.app.settings['codername'],
                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                'cid': cid, 'memo': '', 'important': None, 'name': code_name, 'color': '#777777',
                'pdf_page': self.pdf_page}
        for c in self.codes:
            if c['cid'] == cid:
                item['color'] = c['color']
        cur = self.app.conn.cursor()
        cur.execute(
            "insert into code_image (id,x1,y1,width,height,cid,memo,date,owner, important, pdf_page) values(?,?,?,?,?,?"
            ",?,?,?,null,?)",
            (item['id'], item['x1'], item['y1'], item['width'], item['height'], cid, item['memo'],
             item['date'], item['owner'], self.pdf_page))
        self.app.conn.commit()
        cur.execute("select last_insert_rowid()")
        imid = cur.fetchone()[0]
        item['imid'] = imid
        self.code_areas.append(item)
        self.redraw_scene()
        self.selection = None
        self.app.delete_backup = False
        self.fill_code_counts_in_tree()

    def item_moved_update_data(self, item, parent):
        """ Called from drop event in treeWidget view port.
        identify code or category to move.
        Also merge codes if one code is dropped on another code.
        param:
            item : QTreeWidgetItem
            parent : QTreeWidgetItem """

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
                    # parent is code (leaf) cannot add child
                    return
                supercatid = int(parent.text(1).split(':')[1])
                if supercatid == self.categories[found]['catid']:
                    # something went wrong
                    logger.debug("supercatid== self.categories[found][catid]")
                    return
                self.categories[found]['supercatid'] = supercatid
            cur = self.app.conn.cursor()
            cur.execute("update code_cat set supercatid=? where catid=?",
                        [self.categories[found]['supercatid'], self.categories[found]['catid']])
            self.app.conn.commit()
            self.update_dialog_codes_and_categories()
            self.app.delete_backup = False
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
            self.update_dialog_codes_and_categories()
            self.app.delete_backup = False

    def recursive_non_merge_item(self, item, no_merge_list):
        """ Find matching item to be the current selected item.
        Recurse through any child categories.
        Tried to use QTreeWidget.finditems - but this did not find matching item text
        Called by: textEdit recent codes menu option
        Required for: merge_category()
        """

        child_count = item.childCount()
        for i in range(child_count):
            if item.child(i).text(1)[0:3] == "cat":
                no_merge_list.append(item.child(i).text(1)[6:])
            self.recursive_non_merge_item(item.child(i), no_merge_list)
        return no_merge_list

    def merge_category(self, catid):
        """ Select another category to merge this category into.
        params:
            catid: Integer category id that is to be merged and removed. """

        do_not_merge_list = []
        do_not_merge_list = self.recursive_non_merge_item(self.ui.treeWidget.currentItem(), do_not_merge_list)
        do_not_merge_list.append(str(catid))
        do_not_merge_ids_str = "(" + ",".join(do_not_merge_list) + ")"
        sql = "select name, catid, supercatid from code_cat where catid not in "
        sql += do_not_merge_ids_str + " order by name"
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
            for code in self.codes:
                if code['catid'] == catid:
                    cur.execute("update code_name set catid=? where catid=?", [category['catid'], catid])
            cur.execute("delete from code_cat where catid=?", [catid])
            self.update_dialog_codes_and_categories()
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
            print(e_)
            self.app.conn.rollback()  # revert all changes
            self.update_dialog_codes_and_categories()
            raise
        self.update_dialog_codes_and_categories()

    def merge_codes(self, item, parent):
        """ Merge code with another code.
        Called by item_moved_update_data when a code is moved onto another code.
        param:
            item : QTreeWidgetItem
            parent : QTreeWidgetItem
        """

        # Check item dropped on itself. Error can occur on Ubuntu 22.04.
        if item['name'] == parent.text(0):
            return

        msg = _("Merge code: ") + item['name'] + " ==> " + parent.text(0)
        reply = QtWidgets.QMessageBox.question(self, _('Merge codes'),
                                               msg, QtWidgets.QMessageBox.StandardButton.Yes,
                                               QtWidgets.QMessageBox.StandardButton.No)
        if reply == QtWidgets.QMessageBox.StandardButton.No:
            return
        cur = self.app.conn.cursor()
        old_cid = item['cid']
        new_cid = int(parent.text(1).split(':')[1])
        # Update cid for each coded segment in text, av, image. Delete where there is an Integrity error
        ct_sql = "select ctid from code_text where cid=?"
        cur.execute(ct_sql, [old_cid])
        ct_res = cur.fetchall()
        try:
            for ct in ct_res:
                try:
                    cur.execute("update code_text set cid=? where ctid=?", [new_cid, ct[0]])
                except sqlite3.IntegrityError as e_:
                    # print(ct, e_)
                    cur.execute("delete from code_text where ctid=?", [ct[0]])
            av_sql = "select avid from code_av where cid=?"
            cur.execute(av_sql, [old_cid])
            av_res = cur.fetchall()
            for av in av_res:
                try:
                    cur.execute("update code_av set cid=? where avid=?", [new_cid, av[0]])
                except sqlite3.IntegrityError as e_:
                    # print(e_)
                    cur.execute("delete from code_av where avid=?", [av[0]])
            img_sql = "select imid from code_image where cid=?"
            cur.execute(img_sql, [old_cid])
            img_res = cur.fetchall()
            for img in img_res:
                try:
                    cur.execute("update code_image set cid=? where imid=?", [new_cid, img[0]])
                except sqlite3.IntegrityError as e_:
                    # print(e_)
                    cur.execute("delete from code_image where imid=?", [img[0]])

            cur.execute("delete from code_name where cid=?", [old_cid, ])
            self.app.conn.commit()
        except Exception as e_:
            print(e_)
            self.app.conn.rollback()  # revert all changes
            raise
        self.parent_textEdit.append(msg)
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False

    def add_code(self, catid=None):
        """  Use add_item dialog to get new code text. Add_code_name dialog checks for
        duplicate code name. A random color is selected for the code.
        New code is added to data and database.
        param:
            catid : None to add to without category, catid to add to category. """

        ui = DialogAddItemName(self.app, self.codes, _("Add new code"), _("Code name"))
        ui.exec()
        new_code_name = ui.get_new_name()
        if new_code_name is None:
            return
        code_color = colors[randint(0, len(colors) - 1)]
        if self.default_new_code_color:
            code_color = self.default_new_code_color
        item = {'name': new_code_name, 'memo': "", 'owner': self.app.settings['codername'],
                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'catid': catid,
                'color': code_color}
        cur = self.app.conn.cursor()
        cur.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,?,?,?,?)",
                    (item['name'], item['memo'], item['owner'], item['date'], item['catid'], item['color']))
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        self.parent_textEdit.append(_("New code: ") + item['name'])
        self.app.delete_backup = False

    def add_category(self, supercatid=None):
        """ Add a new category.
        Note: the addItem dialog does the checking for duplicate category names
        param:
            suoercatid : None to add without category, supercatid to add to category. """

        ui = DialogAddItemName(self.app, self.categories, _("Category"), _("Category name"))
        ui.exec()
        new_category_text = ui.get_new_name()
        if new_category_text is None:
            return
        # add to database
        item = {'name': new_category_text, 'cid': None, 'memo': "",
                'owner': self.app.settings['codername'],
                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
        cur = self.app.conn.cursor()
        cur.execute("insert into code_cat (name, memo, owner, date, supercatid) values(?,?,?,?,?)",
                    (item['name'], item['memo'], item['owner'], item['date'], supercatid))
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        self.parent_textEdit.append(_("New category: ") + item['name'])
        self.app.delete_backup = False

    def delete_category_or_code(self, selected):
        """ Delete the selected category or code.
        If category deleted, sublevel items are retained.
        param:
            selected : QTreeWidgetItem """

        if selected.text(1)[0:3] == 'cat':
            self.delete_category(selected)
            return  # Avoids error as selected is now None
        if selected.text(1)[0:3] == 'cid':
            self.delete_code(selected)

    def delete_code(self, selected):
        """ Find code, remove from database, refresh and code_name data and fill
        treeWidget.
        param:
            selected : QTreeWidgetItem """

        # Find the code_in the list, check to delete
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
        self.parent_textEdit.append(_("Code deleted: ") + code_['name'])
        cur = self.app.conn.cursor()
        cur.execute("delete from code_name where cid=?", [code_['cid'], ])
        cur.execute("delete from code_image where cid=?", [code_['cid'], ])
        cur.execute("delete from code_av where cid=?", [code_['cid'], ])
        cur.execute("delete from code_text where cid=?", [code_['cid'], ])
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False

    def delete_category(self, selected):
        """ Find category, remove from database, refresh categories and code data
        and fill treeWidget. Sublevel items are retained.
        param:
            selected : QTreeWidgetItem """

        found = -1
        for i in range(0, len(self.categories)):
            if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                found = i
        if found == -1:
            return
        category = self.categories[found]
        ui = DialogConfirmDelete(self.app, _("Category: ") + selected.text(0))
        ok = ui.exec()
        if not ok:
            return
        self.parent_textEdit.append(_("Category deleted: ") + category['name'])
        cur = self.app.conn.cursor()
        cur.execute("update code_name set catid=null where catid=?", [category['catid'], ])
        cur.execute("update code_cat set supercatid=null where catid = ?", [category['catid'], ])
        cur.execute("delete from code_cat where catid = ?", [category['catid'], ])
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False

    def add_edit_code_memo(self, selected):
        """ View and edit a memo.
        param:
            selected : QTreeWidgetItem """

        if selected.text(1)[0:3] == 'cid':
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                    found = i
            if found == -1:
                return
            ui = DialogMemo(self.app, _("Memo for Code ") + self.codes[found]['name'],
                            self.codes[found]['memo'])
            ui.exec()
            memo = ui.memo
            if memo == "":
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, "")
            else:
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, _("Memo"))
            # Update codes list and database
            if memo != self.codes[found]['memo']:
                self.codes[found]['memo'] = memo
                cur = self.app.conn.cursor()
                cur.execute("update code_name set memo=? where cid=?", (memo, self.codes[found]['cid']))
                self.app.conn.commit()
                self.app.delete_backup = False

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
            if memo == "":
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, "")
            else:
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, _("Memo"))
            # update codes list and database
            if memo != self.categories[found]['memo']:
                self.categories[found]['memo'] = memo
                cur = self.app.conn.cursor()
                cur.execute("update code_cat set memo=? where catid=?", (memo, self.categories[found]['catid']))
                self.app.conn.commit()
                self.app.delete_backup = False
        self.update_dialog_codes_and_categories()

    def rename_category_or_code(self, selected):
        """ Rename a code or category. Checks that the proposed code or category name is
        not currently in use.
        param:
            selected : QTreeWidgetItem """

        if selected.text(1)[0:3] == 'cid':
            new_name, ok = QtWidgets.QInputDialog.getText(self, _("Rename code"), _("New code name:") + " " * 30,
                                                          QtWidgets.QLineEdit.EchoMode.Normal, selected.text(0))
            if not ok or new_name == '':
                return
            # Check that no other code has this text
            for c in self.codes:
                if c['name'] == new_name:
                    Message(self.app, _("Name in use"), new_name + _(" Choose another name"), "warning").exec()
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
            old_name = self.codes[found]['name']
            self.update_dialog_codes_and_categories()
            self.parent_textEdit.append(_("Code renamed: ") +
                                        old_name + " ==> " + new_name)
            self.app.delete_backup = False
            return

        if selected.text(1)[0:3] == 'cat':
            new_name, ok = QtWidgets.QInputDialog.getText(self, _("Rename category"), _("New category name:"),
                                                          QtWidgets.QLineEdit.EchoMode.Normal, selected.text(0))
            if not ok or new_name == '':
                return
            # Check that no other category has this text
            for c in self.categories:
                if c['name'] == new_name:
                    msg = _("This category name is already in use")
                    Message(self.app, _("Duplicate category name"), msg, "warning").exec()
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
            old_name = self.categories[found]['name']
            # self.categories[found]['name'] = new_name
            # selected.setData(0, QtCore.Qt.DisplayRole, new_name)
            self.parent_textEdit.append(_("Category renamed from: ") +
                                        f"{old_name} ==> {new_name}")
            self.update_dialog_codes_and_categories()
            self.app.delete_backup = False

    def change_code_color(self, selected):
        """ Change the color of the currently selected code.
        param:
            selected : QTreeWidgetItem """

        cid = int(selected.text(1)[4:])
        found = -1
        for i in range(0, len(self.codes)):
            if self.codes[i]['cid'] == cid:
                found = i
        if found == -1:
            return
        ui = DialogColorSelect(self.app, self.codes[found])  # ['color'])
        ok = ui.exec()
        if not ok:
            return
        new_color = ui.get_color()
        if new_color is None:
            return
        selected.setBackground(0, QBrush(QtGui.QColor(new_color), Qt.BrushStyle.SolidPattern))
        # Update codes list and database
        self.codes[found]['color'] = new_color
        cur = self.app.conn.cursor()
        cur.execute("update code_name set color=? where cid=?",
                    (self.codes[found]['color'], self.codes[found]['cid']))
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False


class DialogViewImage(QtWidgets.QDialog):
    """ View image. View and edit displayed memo.
    Show a scalable and scrollable image.
    The slider values range from 10 to 99.

    Linked images have 'image:' at start of mediapath
    """

    app = None
    image_data = None
    pixmap = None
    scene = None
    degrees = 0  # for rotation

    def __init__(self, app, image_data, parent=None):
        """ Image_data contains: {name, mediapath, owner, id, date, memo, fulltext}
        mediapath may be a link as: 'images:path'
        """

        self.app = app
        self.image_data = image_data
        self.degrees = 0
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_view_image()
        self.ui.setupUi(self)
        font = f"font: {self.app.settings['fontsize']}pt "
        font += f'"{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        abs_path = ""
        if "images:" in self.image_data['mediapath']:
            abs_path = self.image_data['mediapath'][7:]  # Remove images:
        else:
            abs_path = self.app.project_path + self.image_data['mediapath']
        self.setWindowTitle(abs_path)
        image = QtGui.QImage(abs_path)
        if image.isNull():
            Message(self.app, _('Image error'), _("Cannot open: ") + abs_path, "warning").exec()
            self.close()
            return

        self.scene = QtWidgets.QGraphicsScene()
        self.ui.graphicsView.setScene(self.scene)
        # Need this otherwise small images are centred on screen, and affect context menu position points
        self.ui.graphicsView.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.scene.installEventFilter(self)
        self.pixmap = QtGui.QPixmap.fromImage(image)
        pixmap_item = QtWidgets.QGraphicsPixmapItem(QtGui.QPixmap.fromImage(image))
        pixmap_item.setPos(0, 0)
        self.scene.setSceneRect(QtCore.QRectF(0, 0, self.pixmap.width(), self.pixmap.height()))
        self.scene.addItem(pixmap_item)
        self.ui.horizontalSlider.setValue(99)
        self.ui.horizontalSlider.valueChanged[int].connect(self.redraw_scene)
        self.ui.horizontalSlider.setToolTip(_("Key + or W zoom in. Key - or Q zoom out"))
        self.ui.textEdit.setText(self.image_data['memo'])
        tt = _("L rotate clockwise\nR rotate anti-clockwise\n+ - zoom in and out")
        self.ui.graphicsView.setToolTip(tt)

        # Scale initial picture by height to mostly fit inside scroll area
        # Tried other methods e.g. sizes of components, but nothing was correct.
        # - 30 - 80  are slider and textedit heights
        if self.pixmap.height() > self.height() - 30 - 80:
            scale = (self.height() - 30 - 80) / self.pixmap.height()
            slider_value = int(scale * 100)
            if slider_value > 100:
                slider_value = 100
            self.ui.horizontalSlider.setValue(slider_value)

    def redraw_scene(self):
        """ Resize image. Triggered by user change in slider or + - keys
        """

        if self.pixmap is None:
            return
        scale = (self.ui.horizontalSlider.value() + 1) / 100
        height = int(scale * self.pixmap.height())
        pixmap = self.pixmap.scaledToHeight(height, QtCore.Qt.TransformationMode.FastTransformation)
        transform = QtGui.QTransform().rotate(self.degrees)
        pixmap = pixmap.transformed(transform)
        pixmap_item = QtWidgets.QGraphicsPixmapItem(pixmap)
        pixmap_item.setPos(0, 0)
        self.scene.clear()
        self.scene.addItem(pixmap_item)
        self.ui.graphicsView.update()
        w_h = _("Width: ") + str(pixmap.size().width()) + _(" Height: ") + str(pixmap.size().height())
        msg = w_h + _(" Scale: ") + str(int(scale * 100)) + "%"
        self.ui.horizontalSlider.setToolTip(msg)

    def zoom_out(self):
        v = self.ui.horizontalSlider.value()
        v -= 3
        if v < self.ui.horizontalSlider.minimum():
            return
        self.ui.horizontalSlider.setValue(v)

    def zoom_in(self):
        v = self.ui.horizontalSlider.value()
        v += 3
        if v > self.ui.horizontalSlider.maximum():
            return
        self.ui.horizontalSlider.setValue(v)

    def eventFilter(self, object_, event):
        """ Using this event filter to apply key events.
        Key events on scene
        + and- keys
        L and R rotation
        """

        # Hide / unHide top groupbox
        if type(event) == QtGui.QKeyEvent:
            key = event.key()
            if key == QtCore.Qt.Key.Key_Minus or key == QtCore.Qt.Key.Key_Q:
                self.zoom_out()
                return True
            if key == QtCore.Qt.Key.Key_Plus or key == QtCore.Qt.Key.Key_W:
                self.zoom_in()
                return True
            if key == QtCore.Qt.Key.Key_L:
                self.degrees -= 90
                if self.degrees < 0:
                    self.degrees = 270
                self.redraw_scene()
                return True
            if key == QtCore.Qt.Key.Key_R:
                self.degrees += 90
                if self.degrees > 270:
                    self.degrees = 0
                self.redraw_scene()
                return True
        return False
