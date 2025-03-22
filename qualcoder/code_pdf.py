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
from binascii import b2a_hex
from copy import deepcopy
import datetime
import logging
import os
from pdfminer.converter import PDFPageAggregator
# Unused LTFigure, LTTextBox, LTTextBoxHorizontal
from pdfminer.layout import LAParams, LTTextLine, LTImage, LTCurve, LTLine, LTRect
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.pdfpage import PDFPage
from pdfminer.psparser import PSLiteral  # Partly using for color conversion
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument  # for PDF meta information
# Using this for determining colourspace, e.g. colorspace': [<PDFObjRef:852>]
from pdfminer.pdftypes import PDFObjRef, resolve1
import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/
from random import randint
import re
import sqlite3
from statistics import median
from typing import Iterable, Any
import webbrowser

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor

from .add_item_name import DialogAddItemName
from .code_in_all_files import DialogCodeInAllFiles
from .color_selector import DialogColorSelect
from .color_selector import colors, TextColor, colour_ranges, show_codes_of_colour_range
from .confirm_delete import DialogConfirmDelete
from .helpers import Message, ExportDirectoryPathDialog
from .GUI.ui_dialog_code_pdf import Ui_Dialog_code_pdf
from .memo import DialogMemo
from .report_attributes import DialogSelectAttributeParameters
from .reports import DialogReportCoderComparisons, DialogReportCodeFrequencies  # for isinstance()
from .report_codes import DialogReportCodes
from .report_code_summary import DialogReportCodeSummary  # for isinstance()
from .select_items import DialogSelectItems  # for isinstance()

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogCodePdf(QtWidgets.QWidget):
    """ Code management. Add, delete codes. Mark and unmark text.
    Add memos and colors to codes.
    View Pdf with coding on Pdf text.
    View in side page Text or Pdf Objects. """

    NAME_COLUMN = 0
    ID_COLUMN = 1
    MEMO_COLUMN = 2
    app = None
    parent_textEdit = None
    tab_reports = None  # Tab widget reports, used for updates to codes
    codes = []
    recent_codes = []  # list of recent codes (up to 5) for textedit context menu
    categories = []
    tree_sort_option = "all asc"  # all desc, cat then code asc
    filenames = []
    file_ = None  # contains filename and file id returned from SelectItems
    code_text = []
    annotations = []
    undo_deleted_codes = []  # undo last deleted code(s), multiple may have been deleted at th same time, so a list
    different_text_lengths = False
    metadata = ""

    # Overlapping coded text details
    overlaps_at_pos = []
    overlaps_at_pos_idx = 0

    # Search text variables
    search_indices = []
    search_index = 0
    search_term = ""
    search_type = "3"  # 3 chars or 5 chars or 1 for Enter
    selected_code_index = 0
    important = False  # Show/hide important codes
    attributes = []  # Show selected files using these attributes in list widget

    # Timers to reduce overly sensitive key events: overlap, re-size oversteps by multiple characters
    code_resize_timer = 0
    overlap_timer = 0
    text = ""

    # Variables associated with right-hand side splitter, for project memo, current journal, code rule

    def __init__(self, app, parent_textedit, tab_reports):

        super(DialogCodePdf, self).__init__()
        self.app = app
        self.tab_reports = tab_reports
        self.parent_textEdit = parent_textedit
        self.search_indices = []
        self.search_index = 0
        self.codes, self.categories = self.app.get_codes_categories()
        self.tree_sort_option = "all asc"
        self.annotations = self.app.get_annotations()
        self.recent_codes = []
        self.autocode_history = []
        self.undo_deleted_codes = []
        self.journal = False
        self.project_memo = False
        self.code_rule = False
        self.important = False
        self.attributes = []
        self.code_resize_timer = datetime.datetime.now()
        self.overlap_timer = datetime.datetime.now()

        # Set up PDF variables
        self.pages = []
        self.scene = None
        self.page_num = 0
        self.total_pages = 0
        self.full_text = ""
        self.page_full_text = ""
        self.metadata = ""
        self.selected_graphic_textboxes = []
        self.pdf_object_info_text = ""  # Contains details of PDF page objects
        self.page_dict = {}  # Temporary variable used when loading PDF pages

        # Set up ui
        self.ui = Ui_Dialog_code_pdf()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        tree_font = f'font: {self.app.settings["treefontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.treeWidget.setStyleSheet(tree_font)
        doc_font = f'font: {self.app.settings["docfontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.textEdit.setStyleSheet(doc_font)
        self.ui.label_coder.setText(f"Coder: {self.app.settings['codername']}")
        self.ui.textEdit.setPlainText("")
        self.ui.textEdit.setAutoFillBackground(True)
        self.ui.textEdit.setToolTip("")
        self.ui.textEdit.setMouseTracking(True)
        self.ui.textEdit.setReadOnly(True)
        self.ui.textEdit.installEventFilter(self)
        self.eventFilterTT = ToolTipEventFilter()
        self.ui.textEdit.installEventFilter(self.eventFilterTT)
        self.ui.textEdit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.textEdit.customContextMenuRequested.connect(self.text_edit_menu)
        self.ui.textEdit.cursorPositionChanged.connect(self.overlapping_codes_in_text)
        self.ui.listWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.listWidget.customContextMenuRequested.connect(self.file_menu)
        self.ui.listWidget.setStyleSheet(tree_font)
        self.ui.listWidget.selectionModel().selectionChanged.connect(self.file_selection_changed)
        self.ui.lineEdit_search.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.lineEdit_search.customContextMenuRequested.connect(self.lineedit_search_menu)

        self.ui.pushButton_latest.setIcon(qta.icon('mdi6.arrow-collapse-right', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_latest.pressed.connect(self.go_to_latest_coded_file)
        self.ui.pushButton_next_file.setIcon(qta.icon('mdi6.arrow-right', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_next_file.pressed.connect(self.go_to_next_file)
        self.ui.pushButton_object_info.setIcon(qta.icon('mdi6.magnify', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_object_info.pressed.connect(self.show_pdf_object_info)
        self.ui.pushButton_view_original.setIcon(qta.icon('mdi6.eye-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_view_original.pressed.connect(self.view_original_file)
        self.ui.pushButton_view_original.setToolTip(_("View original file"))
        self.ui.pushButton_document_memo.setIcon(qta.icon('mdi6.text-box-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_document_memo.pressed.connect(self.file_memo)

        self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
        self.ui.lineEdit_search.setEnabled(False)
        self.ui.checkBox_search_case.stateChanged.connect(self.search_for_text)
        self.ui.checkBox_search_case.setEnabled(False)
        self.ui.label_search_regex.setPixmap(qta.icon('mdi6.text-search').pixmap(22, 22))
        self.ui.label_search_case_sensitive.setPixmap(qta.icon('mdi6.format-letter-case').pixmap(22, 22))
        self.ui.pushButton_export.setIcon(qta.icon('mdi6.export', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_export.pressed.connect(self.export_pdf_image)
        self.ui.label_font_size.setPixmap(qta.icon('mdi6.format-size').pixmap(22, 22))

        # Pages widgets
        self.ui.label_pages.setText("")
        self.ui.pushButton_next_page.setIcon(qta.icon('mdi6.arrow-right', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_next_page.pressed.connect(self.next_page)
        self.ui.pushButton_previous_page.setIcon(qta.icon('mdi6.arrow-left', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_previous_page.pressed.connect(self.previous_page)
        self.ui.pushButton_last_page.setIcon(qta.icon('mdi6.arrow-collapse-right', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_last_page.pressed.connect(self.last_page)
        self.ui.pushButton_goto_page.setIcon(qta.icon('mdi6.book-search-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_goto_page.pressed.connect(self.goto_page)

        self.ui.pushButton_previous.setIcon(qta.icon('mdi6.arrow-left', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_previous.setEnabled(False)
        self.ui.pushButton_previous.pressed.connect(self.move_to_previous_search_text)
        self.ui.pushButton_next.setIcon(qta.icon('mdi6.arrow-right', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_next.setEnabled(False)
        self.ui.pushButton_next.pressed.connect(self.move_to_next_search_text)
        self.ui.pushButton_help.setIcon(qta.icon('mdi6.help'))
        self.ui.pushButton_help.pressed.connect(self.help)
        self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.tag-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_file_attributes.pressed.connect(self.get_files_from_attributes)
        self.ui.pushButton_important.setIcon(qta.icon('mdi6.star-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_important.pressed.connect(self.show_important_coded)
        self.ui.treeWidget.setDragEnabled(True)
        self.ui.treeWidget.setAcceptDrops(True)
        self.ui.treeWidget.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.ui.treeWidget.viewport().installEventFilter(self)
        self.ui.treeWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.treeWidget.customContextMenuRequested.connect(self.tree_menu)
        self.ui.treeWidget.itemClicked.connect(self.fill_code_label)
        self.ui.textEdit_2.setReadOnly(True)  # Code examples
        self.ui.splitter.setSizes([150, 400, 150])
        self.ui.splitter_2.setSizes([100, 0])

        # Graphics view items setup
        self.ui.graphicsView.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
        # Need this otherwise images are centred on screen, and affect context menu position points
        self.ui.graphicsView.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.ui.graphicsView.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.graphicsView.customContextMenuRequested.connect(self.graphicsview_menu)
        self.ui.graphicsView.viewport().installEventFilter(self)

        self.ui.checkBox_curve.stateChanged.connect(self.update_page)
        self.ui.checkBox_image.stateChanged.connect(self.update_page)
        self.ui.checkBox_rect.stateChanged.connect(self.update_page)
        self.ui.checkBox_text.stateChanged.connect(self.update_page)
        self.ui.checkBox_line.stateChanged.connect(self.update_page)
        self.ui.checkBox_black_text.stateChanged.connect(self.update_page)
        self.ui.comboBox_fontsize.setCurrentIndex(2)
        self.ui.comboBox_fontsize.currentIndexChanged.connect(self.update_page)

        self.get_files()
        self.fill_tree()
        msg = _("QualCoder roughly displays PDFs.")
        msg += "\n" + _("Some images will not display and image masks and rotations will not work.")
        msg += "\n" + _("Original fonts or bold or italic are not applied.")
        msg += "\n" + _("There is not enough information in pdfminer to accurately display polygon curves.")
        msg += "\n" + _("Plain text must match exactly for Code PDF to work correctly.")
        msg += "\n" + _("A warning will display if the parsed PDF text does not match the database stored plain text.")
        msg += "\n" + _("Plain text of PDFs loaded in to QualCoder before version 3.4 will not have the plain text positions correct for PDF display.")
        msg += "\n" + _("This means coding stripes will show in incorrect positions.")
        msg += "\n" + _("Similarly, if the PDF plain text has beeen edited in any way, this will affect coding stripes display.")
        Message(self.app, _("Information") + " " * 20, msg).exec()

    def goto_page(self):
        if self.pages:
            text, ok = QtWidgets.QInputDialog.getInt(None, 'Go to page', f'1 - {len(self.pages)}')
            if not ok or not text:
                return
            if int(text) < 1 or int(text) > len(self.pages) - 1:
                return
            self.page_num = int(text) - 1
            self.ui.label_pages.setText(f"{self.page_num + 1}/{len(self.pages)}")
            self.show_page()

    def last_page(self):
        if self.pages:
            self.page_num = len(self.pages) - 1
            self.ui.label_pages.setText(f"{self.page_num + 1}/{len(self.pages)}")
            self.show_page()

    def next_page(self):
        if self.pages:
            self.page_num += 1
            if self.page_num > len(self.pages) - 1:
                self.page_num = len(self.pages) - 1
            self.ui.label_pages.setText(f"{self.page_num + 1}/{len(self.pages)}")
            self.show_page()

    def previous_page(self):
        if self.pages:
            self.page_num -= 1
            if self.page_num < 0:
                self.page_num = 0
            self.ui.label_pages.setText(f"{self.page_num + 1}/{len(self.pages)}")
            self.show_page()

    def update_page(self):
        """ Show and hide PDF elements on page and redraw. """

        if self.pages:
            self.show_page()

    def get_files(self, ids=None):
        """ Get pdf files with additional details and fill list widget.
         Called by: init, get_files_from_attributes, show_files_like
         param:
         ids: list, fill with ids to limit file selection.
         """

        if ids is None:
            ids = []
        self.ui.listWidget.clear()
        self.filenames = self.app.get_pdf_filenames(ids)
        # Fill additional details about each file in the memo
        cur = self.app.conn.cursor()
        sql = "select length(fulltext), fulltext from source where id=?"
        sql_codings = "select count(cid) from code_text where fid=? and owner=?"
        for f in self.filenames:
            cur.execute(sql, [f['id'], ])
            res = cur.fetchone()
            if res is None:  # Safety catch
                res = [0, ""]
            tt = _("Characters: ") + str(res[0])
            f['characters'] = res[0]
            f['start'] = 0
            f['end'] = res[0]
            f['fulltext'] = res[1]
            cur.execute(sql_codings, [f['id'], self.app.settings['codername']])
            res = cur.fetchone()
            tt += f"\n{_('Codings:')} {res[0]}"
            tt += f"\n{_('From:')} {f['start']} - {f['end']}"
            item = QtWidgets.QListWidgetItem(f['name'])
            if f['memo'] != "":
                tt += f"\nMemo: {f['memo']}"
            item.setToolTip(tt)
            self.ui.listWidget.addItem(item)
        self.file_ = None
        self.code_text = []  # Must be before clearing textEdit, as next calls cursorChanged
        self.ui.textEdit.setText("")

    def update_file_tooltip(self):
        """ Create tooltip for file containing characters, codings and from: to: if partially loaded.
        Called by get_files, updates to add, remove codings, text edits.
        Requires self.file_ """

        if self.file_ is None:
            return
        cur = self.app.conn.cursor()
        sql = "select length(fulltext), fulltext from source where id=?"
        cur.execute(sql, [self.file_['id'], ])
        res = cur.fetchone()
        if res is None:  # Safety catch
            res = [0, ""]
        tt = _("Characters: ") + str(res[0])
        f = {'characters': res[0], 'start': 0, 'end': res[0], 'fulltext': res[1]}
        sql_codings = "select count(cid) from code_text where fid=? and owner=?"
        cur.execute(sql_codings, [self.file_['id'], self.app.settings['codername']])
        res = cur.fetchone()
        tt += f"\n{_('Codings:')} {res[0]}"
        tt += f"\n{_('From:')} {f['start']} - {f['end']}"
        if self.file_['memo'] != "":
            tt += f"\nMemo: {self.file_['memo']}"
        # Find item to update tooltip
        items = self.ui.listWidget.findItems(self.file_['name'], Qt.MatchFlag.MatchExactly)
        if len(items) == 0:
            return
        items[0].setToolTip(tt)

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
            self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.tag-outline'))
            self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
            if self.attributes:
                self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.tag'))
            return
        self.attributes = ui.parameters
        if len(self.attributes) == 1:  # Boolean parameter, no attributes
            self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.tag-outline'))
            self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
            self.get_files()
            return
        if not ui.result_file_ids:
            Message(self.app, _("Nothing found") + " " * 20, _("No matching files found")).exec()
            self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.tag-outline'))
            self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
            return
        self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.tag'))
        self.ui.pushButton_file_attributes.setToolTip(ui.tooltip_msg)
        self.get_files(ui.result_file_ids)

    def fill_code_label(self):
        """ Fill code label with currently selected item's code name and colour.
         Also, if text or graphics textbox(es) is highlighted, assign the text to this code.

         Called by: treewidgetitem_clicked """

        current = self.ui.treeWidget.currentItem()
        if current.text(1)[0:3] == 'cat':
            self.ui.label_code.hide()
            self.ui.label_code.setToolTip("")
            return
        self.show_code_rule()
        self.ui.label_code.show()
        # Set background colour of label to code color, and store current code for underlining
        for c in self.codes:
            if current.text(0) == c['name']:
                fg_color = TextColor(c['color']).recommendation
                style = f"QLabel {{background-color :{c['color']}; color:{fg_color};}}"
                self.ui.label_code.setStyleSheet(style)
                self.ui.label_code.setAutoFillBackground(True)
                tt = f"{c['name']}\n"
                if c['memo'] != "":
                    tt += _("Memo: ") + c['memo']
                self.ui.label_code.setToolTip(tt)
                break
        # Selected text via textEdit OR via selected text boxes.
        selected_text = self.ui.textEdit.textCursor().selectedText()
        if self.scene is not None:
            self.selected_graphic_textboxes = self.scene.selectedItems()
            if len(selected_text) > 0 and len(self.selected_graphic_textboxes) == 0:
                self.mark()
            ''' When using search text, textEdit text may be selected as well as the text_box.
            So in this circumstance can select textbox directly or via search text to codet the selected text boxes. '''
            if len(self.selected_graphic_textboxes) > 0:
                self.mark(by_text_boxes=True)
        # When a code is selected undo the show selected code features
        self.highlight()

    def tree_traverse_for_non_expanded(self, item, non_expanded):
        """ Find all categories and codes
        Recurse through all child categories.
        Called by: fill_tree
        param:
            item: a QTreeWidgetItem
            list of non-expanded categories as Sring if catid:#
        """

        child_count = item.childCount()
        for i in range(child_count):
            if "catid:" in item.child(i).text(1) and not item.child(i).isExpanded():
                non_expanded.append(item.child(i).text(1))
            self.tree_traverse_for_non_expanded(item.child(i), non_expanded)

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes.
        The Count column counts the number of times that code has been used by selected coder in selected file.
        Keep record of non-expanded items, then re-enact these items when treee fill is called again. """

        non_expanded = []
        self.tree_traverse_for_non_expanded(self.ui.treeWidget.invisibleRootItem(), non_expanded)
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
                    memo = _("Memo")
                top_item = QtWidgets.QTreeWidgetItem([c['name'], f'catid:{c["catid"]}', memo])
                top_item.setToolTip(2, c['memo'])
                top_item.setToolTip(0, '')
                if len(c['name']) > 52:
                    top_item.setText(0, f"{c['name'][:25]}..{c['name'][-25:]}")
                    top_item.setToolTip(0, c['name'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                if f"catid:{c['catid']}" in non_expanded:
                    top_item.setExpanded(False)
                else:
                    top_item.setExpanded(True)
                remove_list.append(c)
        for item in remove_list:
            cats.remove(item)
        ''' Add child categories. look at each unmatched category, iterate through tree
         to add as child, then remove matched categories from the list '''
        count = 0
        while len(cats) > 0 and count < 10000:
            remove_list = []
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
                item = it.value()
                count2 = 0
                while item and count2 < 10000:  # while there is an item in the list
                    if item.text(1) == f'catid:{c["supercatid"]}':
                        memo = ""
                        if c['memo'] != "":
                            memo = _("Memo")
                        child = QtWidgets.QTreeWidgetItem([c['name'], f'catid:{c["catid"]}', memo])
                        child.setToolTip(2, c['memo'])
                        child.setToolTip(0, '')
                        if len(c['name']) > 52:
                            child.setText(0, f"{c['name'][:25]}..{c['name'][-25:]}")
                            child.setToolTip(0, c['name'])
                        item.addChild(child)
                        if f"catid:{c['catid']}" in non_expanded:
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
                    memo = _("Memo")
                top_item = QtWidgets.QTreeWidgetItem([c['name'], f'cid:{c["cid"]}', memo])
                top_item.setToolTip(2, c['memo'])
                top_item.setToolTip(0, c['name'])
                if len(c['name']) > 52:
                    top_item.setText(0, f"{c['name'][:25]}..{c['name'][-25:]}")
                    top_item.setToolTip(0, c['name'])
                top_item.setBackground(0, QBrush(QColor(c['color']), Qt.BrushStyle.SolidPattern))
                color = TextColor(c['color']).recommendation
                top_item.setForeground(0, QBrush(QColor(color)))
                top_item.setFlags(
                    Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable |
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled)
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)
        # Add codes as children
        for c in codes:
            it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
            item = it.value()
            count = 0
            while item and count < 10000:
                if item.text(1) == f'catid:{c["catid"]}':
                    memo = ""
                    if c['memo'] != "":
                        memo = _("Memo")
                    child = QtWidgets.QTreeWidgetItem([c['name'], f'cid:{c["cid"]}', memo])
                    child.setToolTip(2, c['memo'])
                    child.setToolTip(0, c['name'])
                    if len(c['name']) > 52:
                        child.setText(0, f"{c['name'][:25]}..{c['name'][-25:]}")
                        child.setToolTip(0, c['name'])
                    child.setBackground(0, QBrush(QColor(c['color']), Qt.BrushStyle.SolidPattern))
                    color = TextColor(c['color']).recommendation
                    child.setForeground(0, QBrush(QColor(color)))
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
        Called by: fill_tree
        """

        if self.file_ is None:
            return
        cur = self.app.conn.cursor()
        sql = "select count(cid) from code_text where cid=? and fid=? and owner=?"
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        count = 0
        while item and count < 10000:
            if item.text(1)[0:4] == "cid:":
                cid = str(item.text(1)[4:])
                try:
                    cur.execute(sql, [cid, self.file_['id'], self.app.settings['codername']])
                    result = cur.fetchone()
                    if result[0] > 0:
                        item.setText(3, str(result[0]))
                        item.setToolTip(3, self.app.settings['codername'])
                    else:
                        item.setText(3, "")
                except Exception as e:
                    msg = f"Fill code counts error\n{e}\n{sql}\n"
                    msg += f"cid: {cid}\n"
                    msg += "self.file_['id'] " + f"{self.file_['id']}\n"
                    logger.debug(msg)
                    item.setText(3, "")
            it += 1
            item = it.value()
            count += 1

    def get_codes_and_categories(self):
        """ Called from init, delete category/code.
        Also called on other coding dialogs in the dialog_list. """

        self.codes, self.categories = self.app.get_codes_categories()

    # Header section widgets

    # Search for text methods
    def search_for_text(self):
        """ On text changed in lineEdit_search OR Enter pressed, find indices of matching text.
        Only where text is >=3 OR 5 characters long. Or Enter is pressed (search_type==1).
        Resets current search_index.
        If all files is checked then searches for all matching text across all text files
        and displays the file text and current position to user.
        If case-sensitive is checked then text searched is matched for case sensitivity.
        """

        if self.file_ is None:
            return
        if not self.search_indices:
            self.ui.pushButton_next.setEnabled(False)
            self.ui.pushButton_previous.setEnabled(False)
        self.search_indices = []
        self.search_index = -1
        self.search_term = self.ui.lineEdit_search.text()
        self.ui.label_search_totals.setText("0 / 0")
        if len(self.search_term) < int(self.search_type):
            return
        #TODO some errors to fix
        pattern = None
        flags = 0
        if not self.ui.checkBox_search_case.isChecked():
            flags |= re.IGNORECASE
        '''if self.ui.checkBox_search_escaped.isChecked():
            pattern = re.compile(re.escape(self.search_term), flags)
        else:
            try:
                pattern = re.compile(self.search_term, flags)
            except:
                logger.warning('Bad escape')'''
        try:
            pattern = re.compile(self.search_term, flags)
        except re.error as e_:
            logger.warning('re error Bad escape ' + str(e_))
        if pattern is None:
            return
        self.search_indices = []
        # Search only this document
        try:
            displayed_text = self.file_['fulltext']  # self.ui.textEdit.toPlainText()
            if displayed_text != "":
                for match in pattern.finditer(displayed_text):
                    # Get result. char position and search string length
                    self.search_indices.append((match.start(), len(match.group(0))))
        except re.error:
            logger.exception('Failed searching current file for %s', self.search_term)
        if len(self.search_indices) > 0:
            self.ui.pushButton_next.setEnabled(True)
            self.ui.pushButton_previous.setEnabled(True)
        self.ui.label_search_totals.setText(f"0 / {len(self.search_indices)}")

    def move_to_next_search_text(self):
        """ Push button pressed to move to next search text position.
        next_result = [char position, search string length]
        """

        if self.file_ is None or self.search_indices == []:
            return
        self.search_index += 1
        if self.search_index == len(self.search_indices):
            self.search_index = 0
        next_result = self.search_indices[self.search_index]
        for p in self.pages:
            if p['plain_text_start'] <= next_result[0] < p['plain_text_end']:
                self.page_num = p['pagenum']
                self.ui.label_pages.setText(f"{self.page_num + 1}")
                self.show_page()
                break
        # Highlight selected text
        cursor = self.ui.textEdit.textCursor()
        start_pos = next_result[0] - self.pages[self.page_num]['plain_text_start']
        end_pos = start_pos + next_result[1]
        cursor.setPosition(start_pos)
        self.ui.textEdit.setTextCursor(cursor)
        cursor.setPosition(end_pos, QtGui.QTextCursor.MoveMode.KeepAnchor)
        self.ui.textEdit.setTextCursor(cursor)
        self.ui.label_search_totals.setText(f"{self.search_index + 1} / {len(self.search_indices)}")
        # Select relevant text boxes
        for tb in self.pages[self.page_num]['text_boxes']:
            if tb['pos0'] <= next_result[0] < tb['pos1']:
                x = tb['graphic_item_ref'].pos().x()
                y = tb['graphic_item_ref'].pos().y()
                #print("pos", tb['graphic_item_ref'].boundingRect())
                path = QtGui.QPainterPath()
                self.scene.setSelectionArea(path)
                path.addRect(x + 2, y + 6, 1, 1)
                self.scene.setSelectionArea(path)
                break

    def move_to_previous_search_text(self):
        """ Push button pressed to move to previous search text position.
        """

        if self.file_ is None or self.search_indices == []:
            return
        self.search_index -= 1
        if self.search_index < 0:
            self.search_index = len(self.search_indices) - 1
        previous_result = self.search_indices[self.search_index]
        for p in self.pages:
            if p['plain_text_start'] <= previous_result[0] < p['plain_text_end']:
                self.page_num = p['pagenum']
                self.ui.label_pages.setText(f"{self.page_num + 1}")
                self.show_page()
                break
        # Highlight selected text
        start_pos = previous_result[0] - self.pages[self.page_num]['plain_text_start']
        end_pos = start_pos + previous_result[1]
        cursor = self.ui.textEdit.textCursor()
        cursor.setPosition(start_pos)
        self.ui.textEdit.setTextCursor(cursor)
        cursor.setPosition(end_pos, QtGui.QTextCursor.MoveMode.KeepAnchor)
        self.ui.textEdit.setTextCursor(cursor)
        self.ui.label_search_totals.setText(f"{self.search_index + 1} / {len(self.search_indices)}")
        # Select relevant text boxes
        for tb in self.pages[self.page_num]['text_boxes']:
            if tb['pos0'] <= previous_result[0] < tb['pos1']:
                x = tb['graphic_item_ref'].pos().x()
                y = tb['graphic_item_ref'].pos().y()
                #print("pos", tb['graphic_item_ref'].boundingRect())
                path = QtGui.QPainterPath()
                self.scene.setSelectionArea(path)
                path.addRect(x + 2, y + 6, 1, 1)
                self.scene.setSelectionArea(path)
                break

    def lineedit_search_menu(self, position):
        """ Option to change from automatic search on 3 characters or more to press Enter to search """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_char3 = QtGui.QAction(_("Automatic search 3 or more characters"))
        action_char5 = QtGui.QAction(_("Automatic search 5 or more characters"))
        action_enter = QtGui.QAction(_("Press Enter to search"))
        if self.search_type != "3":
            menu.addAction(action_char3)
        if self.search_type != "5":
            menu.addAction(action_char5)
        if self.search_type != "Enter":
            menu.addAction(action_enter)
        action = menu.exec(self.ui.lineEdit_search.mapToGlobal(position))
        if action is None:
            return
        if action == action_char3:
            self.search_type = 3
            self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
            self.ui.lineEdit_search.returnPressed.disconnect(self.search_for_text)
            return
        if action == action_char5:
            self.search_type = 5
            self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
            self.ui.lineEdit_search.returnPressed.disconnect(self.search_for_text)
            return
        if action == action_enter:
            self.search_type = 1
            self.ui.lineEdit_search.textEdited.disconnect(self.search_for_text)
            self.ui.lineEdit_search.returnPressed.connect(self.search_for_text)
            return

    def show_pdf_object_info(self):
        """ show the pdf object in information dialog. """

        if self.pdf_object_info_text == "":
            return
        msg = f"{self.pdf_object_info_text}\nMETADATA:\n{self.metadata}"
        ui = DialogMemo(self.app, _("PDF objects"), msg)
        ui.ui.pushButton_clear.hide()
        ui.exec()

    def text_edit_recent_codes_menu(self, position):
        """ Alternative context menu.
        Shows a list of recent codes to select from.
        Called by R key press in the text edit pane, only if there is some selected text. """

        if self.ui.textEdit.toPlainText() == "":
            return
        selected_text = self.ui.textEdit.textCursor().selectedText()
        if selected_text == "":
            return
        if len(self.recent_codes) == 0:
            return
        menu = QtWidgets.QMenu()
        for item in self.recent_codes:
            menu.addAction(item['name'])
        action = menu.exec(self.ui.textEdit.mapToGlobal(position))
        if action is None:
            return
        # Remaining actions will be the submenu codes
        self.recursive_set_current_item(self.ui.treeWidget.invisibleRootItem(), action.text())
        self.mark()

    def text_edit_menu(self, position):
        """ Context menu for textEdit.
        Mark, unmark, annotate, copy, memo coded, coded importance. """

        cursor = self.ui.textEdit.cursorForPosition(position)
        selected_text = self.ui.textEdit.textCursor().selectedText()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_annotate = None
        action_copy = None
        action_code_memo = None
        action_edit_annotate = None
        action_important = None
        action_mark = None
        action_not_important = None
        action_change_code = None
        action_change_pos = None
        action_unmark = None
        action_new_code = None
        action_new_invivo_code = None

        # Can have multiple coded text at this position
        for item in self.code_text:
            if cursor.position() + self.file_['start'] >= item['pos0'] and cursor.position() <= item['pos1']:
                action_unmark = QtGui.QAction(_("Unmark (U)"))
                action_code_memo = QtGui.QAction(_("Memo coded text (M)"))
                action_change_pos = QtGui.QAction(_("Change code position key presses"))
                if item['important'] is None or item['important'] > 1:
                    action_important = QtGui.QAction(_("Add important mark (I)"))
                if item['important'] == 1:
                    action_not_important = QtGui.QAction(_("Remove important mark"))
                action_change_code = QtGui.QAction(_("Change code"))
        if action_unmark:
            menu.addAction(action_unmark)
        if action_code_memo:
            menu.addAction(action_code_memo)
        if action_change_pos:
            menu.addAction(action_change_pos)
        if action_important:
            menu.addAction(action_important)
        if action_not_important:
            menu.addAction(action_not_important)
        if action_change_code:
            menu.addAction(action_change_code)
        if selected_text != "":
            if self.ui.treeWidget.currentItem() is not None:
                action_mark = menu.addAction(_("Mark (Q)"))
            # Use up to 10 recent codes
            if len(self.recent_codes) > 0:
                submenu = menu.addMenu(_("Mark with recent code (R)"))
                for item in self.recent_codes:
                    submenu.addAction(item['name'])
            action_annotate = menu.addAction(_("Annotate (A)"))
            action_copy = menu.addAction(_("Copy to clipboard"))
            action_new_code = menu.addAction(_("Mark with new code"))
            action_new_invivo_code = menu.addAction(_("in vivo code (V)"))
        if selected_text == "" and self.is_annotated(cursor.position()):
            action_edit_annotate = menu.addAction(_("Edit annotation"))
        action_hide_top_groupbox = None
        action_show_top_groupbox = None
        if self.ui.groupBox.isHidden():
            action_show_top_groupbox = menu.addAction(_("Show control panel (H)"))
        if not self.ui.groupBox.isHidden():
            action_hide_top_groupbox = menu.addAction(_("Hide control panel (H)"))
        action = menu.exec(self.ui.textEdit.mapToGlobal(position))
        if action is None:
            return
        if action == action_important:
            self.set_important(position=cursor.position(), ctid=None, important=True)
            return
        if action == action_not_important:
            self.set_important(position=cursor.position(), ctid=None, important=False)
            return
        if selected_text != "" and action == action_copy:
            self.copy_selected_text_to_clipboard()
            return
        if selected_text != "" and self.ui.treeWidget.currentItem() is not None and action == action_mark:
            self.mark()
            return
        if action == action_annotate:
            self.annotate()
            return
        if action == action_edit_annotate:
            # Used fora point text press rather than a selected text
            self.annotate(cursor.position())
            return
        if action == action_unmark:
            self.unmark(cursor.position())
            return
        if action == action_code_memo:
            self.coded_text_memo(cursor.position())
            return
        if action == action_change_pos:
            self.change_code_pos_message()
        if action == action_change_code:
            self.change_code_to_another_code(cursor.position())
            return
        if action == action_show_top_groupbox:
            self.ui.groupBox.setVisible(True)
            return
        if action == action_hide_top_groupbox:
            self.ui.groupBox.setVisible(False)
            return
        if action == action_new_code:
            self.mark_with_new_code()
            return
        if action == action_new_invivo_code:
            self.mark_with_new_code(in_vivo=True)
            return
        # Remaining actions will be the submenu codes
        self.recursive_set_current_item(self.ui.treeWidget.invisibleRootItem(), action.text())
        self.mark()

    def mark_with_new_code(self, in_vivo=False):
        """ Create new code and mark selected text.
        param:
            in_vivo : Boolean if True use in vivio text selection as code name """

        codes_copy = deepcopy(self.codes)
        if not in_vivo:
            self.add_code()
        else:
            self.add_code(catid=None, code_name=self.ui.textEdit.textCursor().selectedText())
        new_code = None
        for c in self.codes:
            if c not in codes_copy:
                new_code = c
        if new_code is None and not in_vivo:
            # not a new code and not an in vivo coding
            return
        if new_code is None and in_vivo:
            # Find existing code name that matches in vivo selection
            new_code = None
            for c in self.codes:
                if c['name'] == self.ui.textEdit.textCursor().selectedText():
                    new_code = c
        self.recursive_set_current_item(self.ui.treeWidget.invisibleRootItem(), new_code['name'])
        self.mark()

    def change_code_to_another_code(self, position):
        """ Change code to another code """

        # Get coded segments at this position
        if self.file_ is None:
            return
        coded_text_list = []
        for item in self.code_text:
            if item['pos0'] <= position + self.file_['start'] <= item['pos1'] and \
                    item['owner'] == self.app.settings['codername']:
                coded_text_list.append(item)
        if not coded_text_list:
            return
        text_item = []
        if len(coded_text_list) == 1:
            text_item = coded_text_list[0]
        # Multiple codes at this position to select from
        if len(coded_text_list) > 1:
            ui = DialogSelectItems(self.app, coded_text_list, _("Select codes"), "single")
            ok = ui.exec()
            if not ok:
                return
            text_item = ui.get_selected()
        if not text_item:
            return
        # Get replacement code
        codes_list = deepcopy(self.codes)
        to_remove = None
        for code_ in codes_list:
            if code_['cid'] == text_item['cid']:
                to_remove = code_
        if to_remove:
            codes_list.remove(to_remove)
        ui = DialogSelectItems(self.app, codes_list, _("Select replacement code"), "single")
        ok = ui.exec()
        if not ok:
            return
        replacememt_code = ui.get_selected()
        if not replacememt_code:
            return
        cur = self.app.conn.cursor()
        sql = "update code_text set cid=? where ctid=?"
        try:
            cur.execute(sql, [replacememt_code['cid'], text_item['ctid']])
            self.app.conn.commit()
        except sqlite3.IntegrityError:
            pass
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()
        self.display_page_text_objects()

    def recursive_set_current_item(self, item, text_):
        """ Set matching item to be the current selected item.
        Recurse through any child categories.
        Tried to use QTreeWidget.finditems - but this did not find matching item text
        Called by: textEdit recent codes menu option
        Required for: mark()
        param:
            item : QTreeWidgetItem - usually root
            text_ : String
        """

        child_count = item.childCount()
        for i in range(child_count):
            if item.child(i).text(1)[0:3] == "cid" and (item.child(i).text(0) == text_
            or item.child(i).toolTip(0) == text_):
                self.ui.treeWidget.setCurrentItem(item.child(i))
            self.recursive_set_current_item(item.child(i), text_)

    def is_annotated(self, position):
        """ Check if position is annotated to provide annotation menu option.
        Returns True or False """

        for note in self.annotations:
            if (note['pos0'] <= position + self.file_['start'] <= note['pos1']) \
                    and note['fid'] == self.file_['id']:
                return True
        return False

    def set_important(self, position=None, ctid=None, important=True):
        """ Set or unset importance to coded text.
        Importance is denoted using '1'
        Coded text items may be based ona text cursor location, if selected by the text edit,
        or may be based on a ctid if selected via the graphics scene.
        params:
            position: textEdit character cursor position
            ctid: the code text integer for the specific coded segment
            important: boolean, default True """

        # Need to get coded segments at this position
        if position is None:
            # Called via button
            position = self.ui.textEdit.textCursor().position()
        if self.file_ is None:
            return
        coded_text_list = []
        for item in self.code_text:
            if item['pos0'] <= position + self.file_['start'] <= item['pos1'] and \
                    item['owner'] == self.app.settings['codername'] and \
                    ((not important and item['important'] == 1) or (important and item['important'] != 1)) and \
                    ctid is None:
                coded_text_list.append(item)
            if ctid is not None and ctid == item['ctid']:
                coded_text_list.append(item)
                break
        if not coded_text_list:
            return
        text_items = []
        if len(coded_text_list) == 1:
            text_items = [coded_text_list[0]]
        # Multiple codes at this position to select from
        if len(coded_text_list) > 1:
            ui = DialogSelectItems(self.app, coded_text_list, _("Select codes"), "multi")
            ok = ui.exec()
            if not ok:
                return
            text_items = ui.get_selected()
        if not text_items:
            return
        importance = None
        if important:
            importance = 1
        cur = self.app.conn.cursor()
        sql = "update code_text set important=? where ctid=?"
        for item in text_items:
            cur.execute(sql, [importance, item['ctid']])
            self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()
        self.update_page()

    def coded_text_memo(self, position=None, ctid=None):
        """ Add or edit a memo for this coded text.
        Coded text items may be based ona text cursor location, if selected by tthe text edit,
        or may be based on a ctid if selected via the graphics scene.
        param:
            position: QTextCursor position
            ctid: the code text integer for the specific coded segment
        """

        if position is None:
            # Called via button
            position = self.ui.textEdit.textCursor().position()
        if self.file_ is None:
            return
        coded_text_list = []
        for item in self.code_text:
            if item['pos0'] <= position + self.file_['start'] <= item['pos1'] and \
                    item['owner'] == self.app.settings['codername'] and ctid is None:
                coded_text_list.append(item)
            if ctid is not None and ctid == item['ctid']:
                coded_text_list.append(item)
                break
        if not coded_text_list:
            return
        text_item = None
        if len(coded_text_list) == 1:
            text_item = coded_text_list[0]
        # Multiple codes at this position to select from
        if len(coded_text_list) > 1:
            ui = DialogSelectItems(self.app, coded_text_list, _("Select code to memo"), "single")
            ok = ui.exec()
            if not ok:
                return
            text_item = ui.get_selected()
        if text_item is None:
            return
        # Dictionary with cid fid seltext owner date name color memo
        msg = f"{text_item['name']} [{text_item['pos0']}-{text_item['pos1']}]"
        ui = DialogMemo(self.app, _("Memo for Coded text: ") + msg, text_item['memo'], "show", text_item['seltext'])
        ui.exec()
        memo = ui.memo
        if memo == text_item['memo']:
            return
        cur = self.app.conn.cursor()
        cur.execute("update code_text set memo=? where cid=? and fid=? and seltext=? and pos0=? and pos1=? and owner=?",
                    (memo, text_item['cid'], text_item['fid'], text_item['seltext'], text_item['pos0'],
                     text_item['pos1'],
                     text_item['owner']))
        self.app.conn.commit()
        for i in self.code_text:
            if text_item['cid'] == i['cid'] and text_item['seltext'] == i['seltext'] \
                    and text_item['pos0'] == i['pos0'] and text_item['pos1'] == i['pos1'] \
                    and text_item['owner'] == self.app.settings['codername']:
                i['memo'] = memo
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()
        self.update_page()

    def change_code_pos_message(self):
        """  Called via textedit_menu. """

        msg = _("Change start position (extend SHIFT LEFT/ shrink ALT RIGHT)\nChange end position (extend SHIFT RIGHT/ shrink ALT LEFT)")
        Message(self.app, _("Use key presses") + " " * 20, msg).exec()

    def copy_selected_text_to_clipboard(self):
        """ Copy text to clipboard for external use.
        For example adding text to another document. """

        selected_text = self.ui.textEdit.textCursor().selectedText()
        cb = QtWidgets.QApplication.clipboard()
        cb.setText(selected_text)

    def tree_menu(self, position):
        """ Context menu for treewidget code/category items.
        Add, rename, memo, move or delete code or category. Change code color.
        Assign selected text to current hovered code. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
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
            action_show_coded_media = menu.addAction(_("Show coded files"))
            action_move_code = menu.addAction(_("Move code to"))
        action_show_codes_like = menu.addAction(_("Show codes like"))
        action_show_codes_of_colour = menu.addAction(_("Show codes of colour"))
        action_all_asc = menu.addAction(_("Sort ascending"))
        action_all_desc = menu.addAction(_("Sort descending"))
        action_cat_then_code_asc = menu.addAction(_("Sort category then code ascending"))
        action = menu.exec(self.ui.treeWidget.mapToGlobal(position))
        if action is not None:
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
            if action == action_show_codes_like:
                self.show_codes_like()
            if selected is not None and action == action_color:
                self.change_code_color(selected)
            if action == action_add_category:
                self.add_category()
            if action == action_add_code:
                self.add_code()
            if action == action_merge_category:
                catid = int(selected.text(1).split(":")[1])
                self.merge_category(catid)
            if action == action_add_code_to_category:
                catid = int(selected.text(1).split(":")[1])
                self.add_code(catid)
            if action == action_add_category_to_category:
                catid = int(selected.text(1).split(":")[1])
                self.add_category(catid)
            if selected is not None and action == action_move_code:
                self.move_code(selected)
            if selected is not None and action == action_rename:
                self.rename_category_or_code(selected)
            if selected is not None and action == action_edit_memo:
                self.add_edit_cat_or_code_memo(selected)
            if selected is not None and action == action_delete:
                self.delete_category_or_code(selected)
            if selected is not None and action == action_show_coded_media:
                found_code = None
                tofind = int(selected.text(1)[4:])
                for code in self.codes:
                    if code['cid'] == tofind:
                        found_code = code
                        break
                if found_code:
                    self.coded_media_dialog(found_code)

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
        param:
            catid : Integer category identifier
        """

        do_not_merge_list = []
        do_not_merge_list = self.recursive_non_merge_item(self.ui.treeWidget.currentItem(), do_not_merge_list)
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
        except:
            self.app.conn.rollback() # Revert all changes
            self.update_dialog_codes_and_categories()
            raise                
        self.update_dialog_codes_and_categories()

    def move_code(self, selected):
        """ Move code to another category or to no category.
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
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()

    def show_important_coded(self):
        """ Show codes flagged as important.
        Applies to both text edit and graphic scene. """

        self.important = not self.important
        if self.important:
            self.ui.pushButton_important.setToolTip(_("Showing important codings"))
            self.ui.pushButton_important.setIcon(qta.icon('mdi6.star'))

        else:
            self.ui.pushButton_important.setToolTip(_("Show codings flagged important"))
            self.ui.pushButton_important.setIcon(qta.icon('mdi6.star-outline'))
        self.get_coded_text_update_eventfilter_tooltips()
        self.display_page_text_objects()

    def show_codes_like(self):
        """ Show all codes if text is empty.
         Show selected codes that contain entered text.
         The input dialog is too narrow, so it is re-created. """

        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        dialog.setWindowTitle(_("Show some codes"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog.setLabelText(_("Show codes containing the text. (Blank for all)"))
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        text_ = str(dialog.textValue())
        root = self.ui.treeWidget.invisibleRootItem()
        self.recursive_traverse(root, text_)

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
        Looks at tooltip also because the code text may be shortened to 50 characters for display, and the tooltip
        is not shortened.
        Recurse through all child categories.
        Called by: show_codes_like
        param:
            item: a QTreeWidgetItem
            text:  Text string for matching with code names
        """

        child_count = item.childCount()
        for i in range(child_count):
            if "cid:" in item.child(i).text(1) and len(text_) > 0 and text_ not in item.child(i).text(0) and \
                    text_ not in item.child(i).toolTip(0):
                item.child(i).setHidden(True)
            if "cid:" in item.child(i).text(1) and text_ == "":
                item.child(i).setHidden(False)
            self.recursive_traverse(item.child(i), text_)

    def show_code_rule(self):
        """ Show code examples in right-hand side splitter pane. """

        self.ui.textEdit_2.setPlainText("")
        selected = self.ui.treeWidget.currentItem()
        if selected is None:
            self.ui.textEdit_2.setText("")
            return
        if selected.text(1)[0:3] == 'cat':
            return
        else:  # Code is selected
            for c in self.codes:
                if c['cid'] == int(selected.text(1)[4:]):
                    txt = f"{_('CODE:')} {c['name']}\n{_('MEMO:')}\n{c['memo']}\n"
                    break
            # Get coded examples
            txt += f"\n{_('EXAMPLES:')}\n"
            cur = self.app.conn.cursor()
            cur.execute("select seltext from code_text where length(seltext) > 0 and cid=? order by random() limit 3",
                        [int(selected.text(1)[4:])])
            res = cur.fetchall()
            for i, r in enumerate(res):
                txt += f"{i + 1}: {r[0]}\n"
        self.ui.textEdit_2.setText(txt)

    def keyPressEvent(self, event):
        """
        Ctrl Z Undo last unmarking
        Ctrl F jump to search box
        A annotate - for current selection - text edit only
        Q Quick Mark with code - for current selection
        H Hide / Unhide top groupbox
        I Tag important
        L Show codes like
        M memo code - at clicked position - text edit only
        O Shortcut to cycle through overlapping codes - at clicked position- text edit only
        S search text - may include current selection
        R opens a context menu for recently used codes for marking text
        U Unmark at selected location
        V assign 'in vivo' code to selected text - text edit only
        Ctrl 0 to Ctrl 9 - button presses
        # Display Clicked character position
        + Zoom in
        -Zoom out
        """

        key = event.key()
        mods = event.modifiers()

        # Ctrl + F jump to search box
        if key == QtCore.Qt.Key.Key_F and mods == QtCore.Qt.KeyboardModifier.ControlModifier:
            self.ui.lineEdit_search.setFocus()
            return
        # Ctrl Z undo last unmarked coding
        if key == QtCore.Qt.Key.Key_Z and mods == QtCore.Qt.KeyboardModifier.ControlModifier:
            self.undo_last_unmarked_code()
            return
        # Ctrl 0 to 9
        if mods & QtCore.Qt.KeyboardModifier.ControlModifier:
            if key == QtCore.Qt.Key.Key_1:
                self.go_to_next_file()
                return
            if key == QtCore.Qt.Key.Key_2:
                self.go_to_latest_coded_file()
                return
            if key == QtCore.Qt.Key.Key_4:
                self.file_memo(self.file_)
                return
            if key == QtCore.Qt.Key.Key_5:
                self.get_files_from_attributes()
                return
            '''if key == QtCore.Qt.Key.Key_8:
                self.show_all_codes_in_text()  # Not used
                return'''
            if key == QtCore.Qt.Key.Key_9:
                self.show_important_coded()
                return
            if key == QtCore.Qt.Key.Key_0:
                self.help()
                return
        if self.ui.graphicsView.hasFocus() and self.scene is not None:
            if key == QtCore.Qt.Key.Key_Plus:
                if self.ui.graphicsView.transform().isScaling() and self.ui.graphicsView.transform().determinant() > 10:
                    return
                self.ui.graphicsView.scale(1.1, 1.1)
                return
            if key == QtCore.Qt.Key.Key_Minus:
                if self.ui.graphicsView.transform().isScaling() and self.ui.graphicsView.transform().determinant() < 0.1:
                    return
                self.ui.graphicsView.scale(0.9, 0.9)
                return
        # Hide unHide top groupbox
        if key == QtCore.Qt.Key.Key_H:
            self.ui.groupBox.setHidden(not (self.ui.groupBox.isHidden()))
            return
        # Show codes like
        if key == QtCore.Qt.Key.Key_L:
            self.show_codes_like()
        # Quick mark selected
        if key == QtCore.Qt.Key.Key_Q:
            self.selected_graphic_textboxes = self.scene.selectedItems()
            if len(self.selected_graphic_textboxes) == 0:
                return
            self.mark(by_text_boxes=True)
            return
        # Recent codes selection
        if key == QtCore.Qt.Key.Key_R and len(self.recent_codes) > 0:
            self.selected_graphic_textboxes = self.scene.selectedItems()
            if len(self.selected_graphic_textboxes) == 0:
                return
            # Can only be single selection, as text boxes re-drawn selection is lost.
            ui = DialogSelectItems(self.app, self.recent_codes, _("Select code"), "single")
            ok = ui.exec()
            if not ok:
                return
            selection = ui.get_selected()
            self.recursive_set_current_item(self.ui.treeWidget.invisibleRootItem(), selection['name'])
            self.mark(by_text_boxes=True)
            return
        # Unmark text boxes
        ''' Review graphicsview_menu for code for this action '''
        '''if key == QtCore.Qt.Key.Key_U:
            self.selected_graphic_textboxes = self.scene.selectedItems()
            if len(self.selected_graphic_textboxes) == 0:
                return
            print("U")
            #self.unmark(cursor_pos)
            return
        # TODO MORE'''

        if not self.ui.textEdit.hasFocus():
            return
        cursor_pos = self.ui.textEdit.textCursor().position()
        selected_text = self.ui.textEdit.textCursor().selectedText()
        codes_here = []
        for item in self.code_text:
            if item['pos0'] <= cursor_pos + self.file_['start'] <= item['pos1'] and \
                    item['owner'] == self.app.settings['codername']:
                codes_here.append(item)
        # Hash display character position
        if key == QtCore.Qt.Key.Key_Exclam:
            Message(self.app, _("Text position") + " " * 20, _("Character position: ") + str(cursor_pos)).exec()
            return
        # Annotate selected
        if key == QtCore.Qt.Key.Key_A and selected_text != "":
            self.annotate()
            return
        # Bookmark
        if key == QtCore.Qt.Key.Key_B and self.file_ is not None:
            text_pos = self.ui.textEdit.textCursor().position() + self.file_['start']
            cur = self.app.conn.cursor()
            cur.execute("update project set bookmarkfile=?, bookmarkpos=?", [self.file_['id'], text_pos])
            self.app.conn.commit()
            return
        # Hide unHide top groupbox
        if key == QtCore.Qt.Key.Key_H:
            self.ui.groupBox.setHidden(not (self.ui.groupBox.isHidden()))
            return
        # Important for coded text
        if key == QtCore.Qt.Key.Key_I:
            self.set_important(position=cursor_pos, ctid=None)
            return
        # Memo for current code
        if key == QtCore.Qt.Key.Key_M:
            self.coded_text_memo(position=cursor_pos, ctid=None)
            return
        # Overlapping codes cycle
        now = datetime.datetime.now()
        overlap_diff = now - self.overlap_timer
        if key == QtCore.Qt.Key.Key_O and len(self.overlaps_at_pos) > 0 and overlap_diff.microseconds > 100000:
            self.overlap_timer = datetime.datetime.now()
            self.highlight_selected_overlap()
            return
        # Quick mark selected
        if key == QtCore.Qt.Key.Key_Q and selected_text != "":
            self.mark()
            return
        # Unmark at text position
        if key == QtCore.Qt.Key.Key_U:
            self.unmark(cursor_pos)
            return
        # Create or assign in vivo code to selected text
        if key == QtCore.Qt.Key.Key_V and selected_text != "":
            self.mark_with_new_code(in_vivo=True)
            return
        # Recent codes context menu
        if key == QtCore.Qt.Key.Key_R and self.file_ is not None and self.ui.textEdit.textCursor().selectedText() != "":
            self.text_edit_recent_codes_menu(self.ui.textEdit.cursorRect().topLeft())
            return
        # Search, with or without selected
        if key == QtCore.Qt.Key.Key_S and self.file_ is not None:
            if selected_text == "":
                self.ui.lineEdit_search.setFocus()
            else:
                self.ui.lineEdit_search.setText(selected_text)
                self.search_for_text()
                self.ui.pushButton_next.setFocus()

    def highlight_selected_overlap(self):
        """ Highlight the current overlapping text code, by placing formatting on top. """

        self.overlaps_at_pos_idx += 1
        if self.overlaps_at_pos_idx >= len(self.overlaps_at_pos):
            self.overlaps_at_pos_idx = 0
        item = self.overlaps_at_pos[self.overlaps_at_pos_idx]
        # Remove formatting
        cursor = self.ui.textEdit.textCursor()
        cursor.setPosition(int(item['pos0'] - self.file_['start']), QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(int(item['pos1'] - self.file_['start']), QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(QtGui.QTextCharFormat())
        # Reapply formatting
        color = ""
        for code in self.codes:
            if code['cid'] == item['cid']:
                color = code['color']
        fmt = QtGui.QTextCharFormat()
        brush = QBrush(QColor(color))
        fmt.setBackground(brush)
        if item['important']:
            fmt.setFontWeight(QtGui.QFont.Weight.Bold)
        fmt.setForeground(QBrush(QColor(TextColor(color).recommendation)))
        cursor.setCharFormat(fmt)
        self.apply_underline_to_overlaps()

    def overlapping_codes_in_text(self):
        """ When coded text is clicked on.
        Only enabled if two or more codes are here.
        Adjust for when portion of full text file loaded.
        Called by: textEdit cursor position changed. """

        if self.file_ is None:
            return
        self.overlaps_at_pos = []
        self.overlaps_at_pos_idx = 0
        pos = self.ui.textEdit.textCursor().position()
        for item in self.code_text:
            if item['pos0'] <= pos + self.file_['start'] <= item['pos1']:
                # logger.debug("Code name for selected pos0:" + str(item['pos0'])+" pos1:"+str(item['pos1'])
                self.overlaps_at_pos.append(item)
        if len(self.overlaps_at_pos) < 2:
            self.overlaps_at_pos = []
            self.overlaps_at_pos_idx = 0

    def export_pdf_image(self):
        """ Export graphics scene """

        filename = "PDF_page.png"
        e_dir = ExportDirectoryPathDialog(self.app, filename)
        filepath = e_dir.filepath
        if filepath is None:
            return
        max_x = self.scene.width()
        max_y = self.scene.height()
        rect_area = QtCore.QRectF(0.0, 0.0, max_x + 10, max_y + 10)  # Source area
        image = QtGui.QImage(int(max_x + 10), int(max_y + 10), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        # Render method requires QRectF NOT QRect. painter, target area, source area
        self.scene.render(painter, QtCore.QRectF(image.rect()), rect_area)
        painter.end()
        image.save(filepath)
        Message(self.app, _("PDF Image exported"), filepath).exec()

    def eventFilter(self, object_, event):
        """ Using this event filter to identify treeWidgetItem drop events.
        http://doc.qt.io/qt-5/qevent.html#Type-enum
        QEvent::Drop 63 A drag and drop operation is completed (QDropEvent).
        https://stackoverflow.com/questions/28994494/why-does-qtreeview-not-fire-a-drop-or-move-event-during-drag-and-drop

        Also use it to detect key events in the textedit.
        These are used to extend or shrink a text coding.
        Only works if clicked on a code (text cursor is in the coded text).
        Shrink start and end code positions using alt arrow left and alt arrow right
        Extend start and end code positions using shift arrow left, shift arrow right
        Ctrl E Enter and exit Edit Mode
        """

        if object_ is self.ui.treeWidget.viewport():
            '''# If a show selected code was active, then clicking on a code in code tree, shows all codes and all tooltips
            if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                self.show_all_codes_in_text()'''
            if event.type() == QtCore.QEvent.Type.Drop:
                item = self.ui.treeWidget.currentItem()
                # event position is QPointF, itemAt requires toPoint
                parent = self.ui.treeWidget.itemAt(event.position().toPoint())
                self.item_moved_update_data(item, parent)
                return True
        # Change start and end code positions using alt arrow left and alt arrow right
        # and shift arrow left, shift arrow right

        if type(event) == QtGui.QKeyEvent and self.ui.textEdit.hasFocus():
            key = event.key()
            mod = event.modifiers()
            # using timer for a lot of things
            now = datetime.datetime.now()
            diff = now - self.code_resize_timer
            # timer sensitivity is reduced compared to Code_text as scene redraw adds time.
            if diff.microseconds < 10000:
                return False

            cursor_pos = self.ui.textEdit.textCursor().position()
            codes_here = []
            for item in self.code_text:
                if item['pos0'] <= cursor_pos + self.file_['start'] <= item['pos1'] and \
                        item['owner'] == self.app.settings['codername']:
                    codes_here.append(item)
            if len(codes_here) == 1:
                # Key event can be too sensitive, adjusted  for millisecond gap
                self.code_resize_timer = datetime.datetime.now()
                if key == QtCore.Qt.Key.Key_Left and mod == QtCore.Qt.KeyboardModifier.AltModifier:
                    self.shrink_to_left(codes_here[0])
                    return True
                if key == QtCore.Qt.Key.Key_Right and mod == QtCore.Qt.KeyboardModifier.AltModifier:
                    self.shrink_to_right(codes_here[0])
                    return True
                if key == QtCore.Qt.Key.Key_Left and mod == QtCore.Qt.KeyboardModifier.ShiftModifier:
                    self.extend_left(codes_here[0])
                    return True
                if key == QtCore.Qt.Key.Key_Right and mod == QtCore.Qt.KeyboardModifier.ShiftModifier:
                    self.extend_right(codes_here[0])
                    return True
        return False

    def extend_left(self, code_):
        """ Shift left arrow.
        param:
            code_ """

        if code_['pos0'] < 1:
            return
        code_['pos0'] -= 1
        cur = self.app.conn.cursor()
        text_sql = "select substr(fulltext,?,?) from source where id=?"
        cur.execute(text_sql, [code_['pos0'] + 1, code_['pos1'] - code_['pos0'], code_['fid']])
        seltext = cur.fetchone()[0]
        sql = "update code_text set pos0=?, seltext=? where ctid=?"
        cur.execute(sql, (code_['pos0'], seltext, code_['ctid']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()
        self.display_page_text_objects()

    def extend_right(self, code_):
        """ Shift right arrow. """

        if code_['pos1'] + 1 >= len(self.ui.textEdit.toPlainText()):
            return
        code_['pos1'] += 1
        cur = self.app.conn.cursor()
        text_sql = "select substr(fulltext,?,?) from source where id=?"
        cur.execute(text_sql, [code_['pos0'] + 1, code_['pos1'] - code_['pos0'], code_['fid']])
        seltext = cur.fetchone()[0]
        sql = "update code_text set pos1=?, seltext=? where ctid=?"
        cur.execute(sql,
                    (code_['pos1'], seltext, code_['ctid']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()
        self.display_page_text_objects()

    def shrink_to_left(self, code_):
        """ Alt left arrow, shrinks code from the right end of the code. """

        if code_['pos1'] <= code_['pos0'] + 1:
            return
        code_['pos1'] -= 1
        cur = self.app.conn.cursor()
        text_sql = "select substr(fulltext,?,?) from source where id=?"
        cur.execute(text_sql, [code_['pos0'] + 1, code_['pos1'] - code_['pos0'], code_['fid']])
        seltext = cur.fetchone()[0]
        sql = "update code_text set pos1=?, seltext=? where ctid=?"
        cur.execute(sql, (code_['pos1'], seltext, code_['ctid']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()
        self.display_page_text_objects()

    def shrink_to_right(self, code_):
        """ Alt right arrow shrinks code from the left end of the code. """

        if code_['pos0'] >= code_['pos1'] - 1:
            return
        code_['pos0'] += 1
        cur = self.app.conn.cursor()
        text_sql = "select substr(fulltext,?,?) from source where id=?"
        cur.execute(text_sql, [code_['pos0'] + 1, code_['pos1'] - code_['pos0'], code_['fid']])
        seltext = cur.fetchone()[0]
        sql = "update code_text set pos0=?, seltext=? where ctid=?"
        cur.execute(sql, (code_['pos0'], seltext, code_['ctid']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()
        self.display_page_text_objects()

    '''def show_all_codes_in_text(self):
        """ Opposes show selected code methods.
        Highlights all the codes in the text. """

        self.ui.pushButton_show_all_codings.setIcon(qta.icon('mdi6.grid-large'))
        self.get_coded_text_update_eventfilter_tooltips()'''

    def coded_media_dialog(self, code_dict):
        """ Display all coded media for this code, in a separate modal dialog.
        Coded media comes from ALL files for this coder.
        Need to store textedit start and end positions so that code in context can be used.
        Called from tree_menu.
        Re-load coded text as codes may have changed.
        param:
            code_dict : code dictionary
        """

        DialogCodeInAllFiles(self.app, code_dict)
        self.get_coded_text_update_eventfilter_tooltips()

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
        """ Merge code with another code.
        Called by item_moved_update_data when a code is moved onto another code.
                param:
            item : Dictionary code item
            parent : QTreeWidgetItem
        """

        # Check item dropped on itself. Error can occur on Ubuntu 22.04.
        if item['name'] == parent.text(0):
            return

        msg = '<p style="font-size:' + str(self.app.settings['fontsize']) + 'px">'
        msg += _("Merge code: ") + item['name'] + _(" into code: ") + parent.text(0) + '</p>'
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

            cur.execute("delete from code_name where cid=?", [old_cid, ])
            self.app.conn.commit()
        except:
            self.app.conn.rollback() # revert all changes 
            raise                
        self.app.delete_backup = False
        msg = msg.replace("\n", " ")
        self.parent_textEdit.append(msg)
        self.update_dialog_codes_and_categories()
        self.get_coded_text_update_eventfilter_tooltips()
        self.display_page_text_objects()

    def add_code(self, catid=None, code_name=""):
        """ Use add_item dialog to get new code text. Add_code_name dialog checks for
        duplicate code name. A random color is selected for the code.
        New code is added to data and database.
        param:
            catid : None to add to without category, catid to add to category.
            code_name : String : Used for 'in vivo' coding where name is preset by in vivo text selection.
        return:
            True  - new code added, False - code exists or could not be added
        """

        if code_name == "":
            ui = DialogAddItemName(self.app, self.codes, _("Add new code"), _("Code name"))
            ui.exec()
            code_name = ui.get_new_name()
            if code_name is None:
                return False
        code_color = colors[randint(0, len(colors) - 1)]
        item = {'name': code_name, 'memo': "", 'owner': self.app.settings['codername'],
                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'catid': catid,
                'color': code_color}
        cur = self.app.conn.cursor()
        try:
            cur.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,?,?,?,?)",
                        (item['name'], item['memo'], item['owner'], item['date'], item['catid'], item['color']))
            self.app.conn.commit()
            self.app.delete_backup = False
            cur.execute("select last_insert_rowid()")
            cid = cur.fetchone()[0]
            item['cid'] = cid
            self.parent_textEdit.append(_("New code: ") + item['name'])
        except sqlite3.IntegrityError:
            # Can occur with in vivo coding
            return False
        self.update_dialog_codes_and_categories()
        self.get_coded_text_update_eventfilter_tooltips()
        return True

    def update_dialog_codes_and_categories(self):
        """ Update code and category tree here and in DialogReportCodes, ReportCoderComparisons, ReportCodeFrequencies
        Using try except blocks for each instance, as instance may have been deleted. """

        self.get_codes_and_categories()
        self.fill_tree()
        self.get_coded_text_update_eventfilter_tooltips()

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
                if isinstance(c, DialogReportCodeSummary):
                    c.get_codes_and_categories()
                    c.fill_tree()

    def add_category(self, supercatid=None):
        """ When button pressed, add a new category.
        Note: the addItem dialog does the checking for duplicate category names
        param:
            supercatid : None to add without category, supercatid to add to category. """

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
        ui = DialogConfirmDelete(self.app, _("Code: ") + selected.text(0))
        ok = ui.exec()
        if not ok:
            return
        cur = self.app.conn.cursor()
        cur.execute("delete from code_name where cid=?", [code_['cid'], ])
        cur.execute("delete from code_text where cid=?", [code_['cid'], ])
        cur.execute("delete from code_av where cid=?", [code_['cid'], ])
        cur.execute("delete from code_image where cid=?", [code_['cid'], ])
        self.app.conn.commit()
        self.app.delete_backup = False
        self.update_dialog_codes_and_categories()
        self.parent_textEdit.append(_("Code deleted: ") + code_['name'] + "\n")
        # Remove from recent codes
        for item in self.recent_codes:
            if item['name'] == code_['name']:
                self.recent_codes.remove(item)
                break
        self.update_dialog_codes_and_categories()
        self.display_page_text_objects()

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
        ui = DialogConfirmDelete(self.app, _("Category: ") + selected.text(0))
        ok = ui.exec()
        if not ok:
            return
        cur = self.app.conn.cursor()
        cur.execute("update code_name set catid=null where catid=?", [category['catid'], ])
        cur.execute("update code_cat set supercatid=null where catid = ?", [category['catid'], ])
        cur.execute("delete from code_cat where catid = ?", [category['catid'], ])
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False
        self.parent_textEdit.append(_("Category deleted: ") + category['name'])

    def add_edit_cat_or_code_memo(self, selected):
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
            ui.exec()
            memo = ui.memo
            if memo != self.codes[found]['memo']:
                self.codes[found]['memo'] = memo
                cur = self.app.conn.cursor()
                cur.execute("update code_name set memo=? where cid=?", (memo, self.codes[found]['cid']))
                self.app.conn.commit()
                self.app.delete_backup = False
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
            if memo == "":
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, "")
            else:
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, _("Memo"))
                self.parent_textEdit.append(_("Memo for category: ") + self.categories[found]['name'])
        self.update_dialog_codes_and_categories()

    def rename_category_or_code(self, selected):
        """ Rename a code or category.
        Check that the code or category name is not currently in use.
        param:
            selected : QTreeWidgetItem """

        if selected.text(1)[0:3] == 'cid':
            code_ = None
            for c in self.codes:
                if c['cid'] == int(selected.text(1)[4:]):
                    code_ = c
            new_name, ok = QtWidgets.QInputDialog.getText(self, _("Rename code"),
                                                          _("New code name:") + " " * 40, QtWidgets.QLineEdit.EchoMode.Normal,
                                                          code_['name'])
            if not ok or new_name == '':
                return
            # Check that no other code has this name
            for c in self.codes:
                if c['name'] == new_name:
                    Message(self.app, _("Name in use"),
                            new_name + _(" is already in use, choose another name."), "warning").exec()
                    return
            # Find the code in the list
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                    found = i
            if found == -1:
                return
            # Rename in recent codes
            for item in self.recent_codes:
                if item['name'] == self.codes[found]['name']:
                    item['name'] = new_name
                    break
            # Update codes list and database
            cur = self.app.conn.cursor()
            cur.execute("update code_name set name=? where cid=?", (new_name, self.codes[found]['cid']))
            self.app.conn.commit()
            self.app.delete_backup = False
            old_name = self.codes[found]['name']
            self.parent_textEdit.append(f'{_("Code renamed:")} {old_name} -> {new_name}')
            self.update_dialog_codes_and_categories()
            self.display_page_text_objects()
            return

        if selected.text(1)[0:3] == 'cat':
            cat = None
            for c in self.categories:
                if c['catid'] == int(selected.text(1)[6:]):
                    cat = c
            new_name, ok = QtWidgets.QInputDialog.getText(self, _("Rename category"), _("New category name:") + " " * 40,
                                                          QtWidgets.QLineEdit.EchoMode.Normal, cat['name'])
            if not ok or new_name == '':
                return
            # Check that no other category has this name
            for c in self.categories:
                if c['name'] == new_name:
                    msg = _("This code name is already in use.")
                    Message(self.app, _("Duplicate code name"), msg, "warning").exec()
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
            self.parent_textEdit.append(f'{_("Category renamed:")} {old_name} -> {new_name}')

    def change_code_color(self, selected):
        """ Change the colour of the currently selected code.
        param:
            selected : QTreeWidgetItem """

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
        self.update_dialog_codes_and_categories()
        self.display_page_text_objects()

    def file_menu(self, position):
        """ Context menu for listWidget files to get to the next file and
        to go to the file with the latest codings by this coder.
        Each file dictionary item in self.filenames contains:
        {'id', 'name', 'memo', 'characters'= number of characters in the file,
        'start' = showing characters from this position, 'end' = showing characters to this position}

        param:
            position : """

        selected = self.ui.listWidget.currentItem()
        file_ = None
        if selected is not None:
            for f in self.filenames:
                if selected.text() == f['name']:
                    file_ = f
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_next = None
        action_latest = None
        action_show_files_like = None
        action_show_case_files = None
        action_show_by_attribute = None
        action_memo = None
        if file_ is not None and self.file_ is not None:
            action_memo = menu.addAction(_("Open memo"))
        action_view_original_file = None
        if file_ is not None and self.file_ is not None and file_['mediapath'] is not None and \
                len(file_['mediapath']) > 6 and \
                (file_['mediapath'][:6] == '/docs/' or file_['mediapath'][:5] == 'docs:'):
            action_view_original_file = menu.addAction(_("View original text file"))
        if len(self.filenames) > 1:
            action_next = menu.addAction(_("Next file"))
            action_latest = menu.addAction(_("File with latest coding"))
            action_show_files_like = menu.addAction(_("Show files like"))
            action_show_by_attribute = menu.addAction(_("Show files by attributes"))
            action_show_case_files = menu.addAction(_("Show case files"))
        action = menu.exec(self.ui.listWidget.mapToGlobal(position))
        if action is None:
            return
        if action == action_memo:
            self.file_memo(file_)
        if action == action_view_original_file:
            self.view_original_file()
        if action == action_next:
            self.go_to_next_file()
        if action == action_latest:
            self.go_to_latest_coded_file()
        if action == action_show_files_like:
            self.show_files_like()
        if action == action_show_case_files:
            self.show_case_files()
        if action == action_show_by_attribute:
            self.get_files_from_attributes()

    def view_original_file(self):
        """ View original pdf file. Opens in browser or other OS default software.
         param:
         mediapath: String '/docs/' for internal 'docs:/' for external """

        if self.file_ is None:
            return
        if self.file_['mediapath'][:6] == "/docs/":
            doc_path = f"{self.app.project_path}/documents/{self.file_['mediapath'][6:]}"
            webbrowser.open(doc_path)
            return
        if self.file_['mediapath'][:5] == "docs:":
            doc_path = self.file_['mediapath'][5:]
            webbrowser.open(doc_path)
            return
        logger.error("Cannot open text file in browser " + self.file_['mediapath'])

    def show_case_files(self):
        """ Show files of specified case.
        Or show all files. """

        cases = self.app.get_casenames()
        cases.insert(0, {"name": _("Show all files"),  "id": -1})
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
        file_ids = [r[0] for r in res]
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
        cur.execute('select id from source where name like ?', [f'%{text_}%'])
        res = cur.fetchall()
        file_ids = [r[0] for r in res]
        self.get_files(file_ids)

    def go_to_next_file(self):
        """ Go to next file in list. Button. """

        if self.file_ is None:
            self.load_file(self.filenames[0])
            self.ui.listWidget.setCurrentRow(0)
            return
        for i in range(0, len(self.filenames) - 1):
            if self.file_ == self.filenames[i]:
                found = self.filenames[i + 1]
                self.ui.listWidget.setCurrentRow(i + 1)
                self.load_file(found)
                self.search_term = ""
                return

    def go_to_latest_coded_file(self):
        """ Go and open file with the latest coding.
        Files menu option.
        """

        sql = "SELECT code_text.fid FROM code_text join source on source.id=code_text.fid \
            where code_text.owner=? and lower(source.mediapath) like '%pdf' order by code_text.date desc limit 1"
        cur = self.app.conn.cursor()
        cur.execute(sql, [self.app.settings['codername']])
        result = cur.fetchone()
        if result is None:
            return
        for i, filedata in enumerate(self.filenames):
            if filedata['id'] == result[0]:
                self.ui.listWidget.setCurrentRow(i)
                self.load_file(filedata)
                self.search_term = ""
                break

    def listwidgetitem_view_file(self):
        """ When listwidget item is pressed load the file.
        The selected file is then displayed for coding.
        Note: file segment is also loaded from listWidget context menu """

        if len(self.filenames) == 0:
            return
        item_name = self.ui.listWidget.currentItem().text()
        for f in self.filenames:
            if f['name'] == item_name:
                self.file_ = f
                self.load_file(self.file_)
                self.search_term = ""
                break

    def file_memo(self, file_=None):
        """ Open file memo to view or edit.
        Called by pushButton_document_memo for loaded text, via active_file_memo
        and through file_menu for any file.
        param: file_ : Dictionary of file values
        """

        if file_ is None:
            file_ = self.file_
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
        items = self.ui.listWidget.findItems(file_['name'], Qt.MatchFlag.MatchExactly)
        if len(items) == 1:
            tt = items[0].toolTip()
            memo_pos = (tt.find(_("Memo:")))
            new_tt = tt[:memo_pos] + _("Memo: ") + file_['memo']
            items[0].setToolTip(new_tt)
        self.app.delete_backup = False

    def file_selection_changed(self):
        """ File selection changed. """

        row = self.ui.listWidget.currentRow()
        self.load_file(self.filenames[row])

    def load_file(self, file_):
        """ Load and display file pdf object in qgraphicsscene and text for this file.
        Set the file as a selected item in the list widget.
        (due to the search text function searching across files).
        Get and display coding highlights.

        Called from:
            view_file_dialog, context_menu
        param: file_ : dictionary of name, id, memo, characters, start, end, fulltext
        """

        if file_ is None:
            return
        for x in range(self.ui.listWidget.count()):
            if self.ui.listWidget.item(x).text() == file_['name']:
                self.ui.listWidget.item(x).setSelected(True)

        self.file_ = file_
        if "start" not in self.file_:
            self.file_['start'] = 0
        sql_values = []
        file_result = self.app.get_file_texts([file_['id']])
        if not file_result:
            self.file_ = None
            self.ui.textEdit.clear()
            self.scene = QtWidgets.QGraphicsScene()
            self.ui.graphicsView.setScene(self.scene)
            return
        file_result = file_result[0]
        if "end" not in self.file_:
            self.file_['end'] = len(file_result['fulltext'])
        sql_values.append(int(file_result['id']))
        # self.text = file_result['fulltext'][self.file_['start']:self.file_['end']]  # tod remove
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        #self.show_all_codes_in_text()  # Deactivates the show_selected_code if this is active. Show selected Not used
        self.setWindowTitle(_("Code text: ") + self.file_['name'])
        self.ui.lineEdit_search.setEnabled(True)
        self.ui.checkBox_search_case.setEnabled(True)
        self.search_for_text()
        self.load_pdf_pages()
        self.ui.label_pages.setText("1")
        self.ui.label_pages.setToolTip(_("Pages: ") + f"{len(self.pages)}")
        self.show_page()

    def load_pdf_pages(self):
        """ Load page elements for all pages in the PDF.
        # next_result is a tuple containing a dictionary of
        # (name, id, fullltext, memo, owner, date) and char position and search string length
        Called by: next_search_result
        """

        self.ui.label_pages.setText("1")
        filepath = None
        if self.file_['mediapath'][:6] == "/docs/":
            filepath = f"{self.app.project_path}/documents/{self.file_['mediapath'][6:]}"
        if self.file_['mediapath'][:5] == "docs:":
            filepath = self.file_['mediapath'][5:]
        if not filepath:
            logger.error("Cannot open pdf file" + self.file_['mediapath'])
            print("Cannot open pdf file " + self.file_['mediapath'])
            return
        self.get_pdf_metadata(filepath)
        pdf_file = open(filepath, 'rb')
        resource_manager = PDFResourceManager()
        laparams = LAParams()
        device = PDFPageAggregator(resource_manager, laparams=laparams)
        interpreter = PDFPageInterpreter(resource_manager, device)
        pages_generator = PDFPage.get_pages(pdf_file)  # generator PDFpage objects
        self.pages = []
        self.page_num = 0
        document_text = ""
        self.page_end_index = 0  # text end of page
        self.text_pos0 = 0  # character pos
        for i, page in enumerate(pages_generator):
            self.page_text = ""
            self.page_dict = {'pagenum': i, 'mediabox': page.mediabox, 'text_boxes': [], 'lines': [], 'curves': [],
                              'images': [], 'rect': [], 'plain_text': [], 'plain_text_start': 0, 'plain_text_end': 0}
            interpreter.process_page(page)
            layout = device.get_result()
            for lobj in layout:
                self.get_pdf_items_and_hierarchy(page, lobj)
            self.page_dict['plain_text'] = self.page_text
            self.page_dict['plain_text_start'] = self.page_end_index
            self.page_end_index += len(self.page_text)
            self.page_dict['plain_text_end'] = self.page_end_index
            self.pages.append(self.page_dict)
            document_text += self.page_text
        self.different_text_lengths = False
        if len(document_text) != len(self.file_['fulltext']):
            msg = _("Parsing the PDF text.") + "\n"
            msg += _("Texts do not match. PDF imported before 3.4 QualCodr version or the PDF text has been edited.")
            msg += _("\nView PDF but cannot code. Code positions will appear wrongly.\nCharacter difference: ")
            msg += str(abs(len(document_text) - len(self.file_['fulltext'])))
            Message(self.app, _("Warning"), msg, "warning").exec()
            self.different_text_lengths = True

    def get_pdf_items_and_hierarchy(self, page, lobj: Any, depth=0):
        """ Get item details add to page_dict, with depth and all its descendants.
        Objects added to self.page_dict, with depth counter.
        LTFigure objects are not listed in the if statements, as they are containers for other objects,
         and are iterated, via the isinstance(Iteratable).
        """

        if isinstance(lobj, LTLine):
            #print("LTLINE", lobj.__dir__())
            # left, btm, right, top = lobj.x0, lobj.y0, lobj.x1, lobj.y1
            line_dict = {'x0': round(lobj.x0,3), 'y0': round(page.mediabox[3] - lobj.y0,3), 'y1': round(page.mediabox[3] - lobj.y1,3),
                         'x1': round(lobj.x1,3), 'linewidth': lobj.linewidth, 'stroke': lobj.stroke, 'fill': lobj.fill,
                         'stroking_color': lobj.stroking_color, 'non_stroking_color': lobj.non_stroking_color,
                         'pts': lobj.pts, 'depth': depth}
            self.page_dict['lines'].append(line_dict)

        if isinstance(lobj, LTRect):
            #print("LTRECT", lobj, type(lobj))
            rect_dict = {"x": round(lobj.bbox[0],3), "y": round(page.mediabox[3] - lobj.bbox[1] - lobj.height,3),
                         "w": round(lobj.width,3), "h": round(lobj.height,3),
                         "linewidth": lobj.linewidth, "stroke": lobj.stroke, "fill": lobj.fill,
                         "stroking_color": lobj.stroking_color,
                         "non_stroking_color": lobj.non_stroking_color, 'is_empty': lobj.is_empty(),
                         'depth': depth}
            self.page_dict['rect'].append(rect_dict)

        if isinstance(lobj, LTCurve):
            """ LTCurve can be a LTRect, LTImage or LTLine. The LTRect can contain a LTImage. """
            # print(lobj.__dir__())
            # left, btm, right, top = lobj.x0, lobj.y0, lobj.x1, lobj.y1
            curve_dict = {'x0': round(lobj.x0,3), 'y0': round(page.mediabox[3] - lobj.y0,3),
                          'y1': round(page.mediabox[3] - lobj.y1,3),
                          'x1': round(lobj.x1,3), 'linewidth': lobj.linewidth, 'stroke': lobj.stroke, 'fill': lobj.fill,
                          'stroking_color': lobj.stroking_color, 'non_stroking_color': lobj.non_stroking_color,
                          'is_empty': lobj.is_empty(),  # 'analyze': lobj.analyze(laparams),
                          'evenodd': lobj.evenodd,
                          'pts': [QtCore.QPointF(p[0], page.mediabox[3] - p[1]) for p in lobj.pts],
                          'depth': depth}
            self.page_dict['curves'].append(curve_dict)

        if isinstance(lobj, LTTextLine):  # or isinstance(lobj, LTTextBox):
            # y-coordinates are the distance from the bottom of the page
            #  left, bottom, right, and top
            #print("LTTEXTLINE", obj.__dir__())
            left, btm, right, top, text_ = lobj.x0, lobj.y0, lobj.x1, lobj.y1, lobj.get_text()
            text_dict = {'left': round(left, 3), 'btm': round(page.mediabox[3] - btm, 3),
                             'top': round(page.mediabox[3] - top, 3),
                             'right': round(right, 3), 'text': text_, 'pos0': self.text_pos0,
                         'pos1': self.text_pos0 + len(text_) + 1, 'graphic_item_ref': None,
                         'bold': False, 'depth': depth}
            # Fix Pdfminer recognising invalid unicode characters.
            text_dict['text'] = text_dict['text'].replace(u"\uE002", "Th")
            text_dict['text'] = text_dict['text'].replace(u"\uFB01", "fi")
            self.full_text += text_dict['text'] #+ "\n"  # add line to paragraph spacing for visual format
            self.page_text += text_dict['text'] #+ "\n"
            self.text_pos0 += len(text_dict['text'])
            text_dict['pos1'] = self.text_pos0
            char_font_sizes = []
            #fontnames = []
            colors = []
            #bold = False
            for ltchar in lobj:
                fontname, fontsize, color = self.get_char_info(ltchar)
                char_font_sizes.append(fontsize)
                #if "bold" in fontname.lower():
                #    bold = True
                #fontnames.append(fontname)  # TODO get most common
                colors.append(color)
            '''fontname = fontnames[0]
            if fontname.find("+") > 0:
                fontname = fontname.split("+")[1]
            text_dict['fontname'] = fontname'''
            text_dict['fontsize'] = int(median(char_font_sizes))
            text_dict['color'] = colors[0]
            self.page_dict['text_boxes'].append(text_dict)

        if isinstance(lobj, LTImage):
            #print("IMG", lobj.__dir__())
            #print("BBOX - x,y,w,h", lobj.bbox)
            img_dict = {"name": lobj.name, "x": round(lobj.bbox[0],3),
                        "y": round(page.mediabox[3] - lobj.bbox[1] - lobj.height,3),
                        "w": round(lobj.width,3), "h": round(lobj.height,3),
                        'imagemask': lobj.imagemask, 'colorspace': lobj.colorspace,
                        'depth': depth}
            #'voverlap':lobj.voverlap(), 'vdistance':lobj.vdistance(),
            if isinstance(lobj.colorspace[0], PDFObjRef):
                values = resolve1(lobj.colorspace[0])
                cspace = []
                for v in values:
                    if isinstance(v, PDFObjRef):
                        vres = resolve1(v)
                        cspace.append(vres)
                    else:
                        cspace.append(v)
                img_dict['colorspace'] = cspace
            img_dict['stream'] = lobj.stream
            img_dict['pixmap'] = None
            if lobj.stream:
                file_stream = lobj.stream.get_rawdata()
                file_ext = self.get_image_type(file_stream[0:4])
                img_dict['filetype'] = file_ext
                qp = QtGui.QPixmap()
                qp.loadFromData(file_stream)
                img_dict['pixmap'] = qp.scaled(int(img_dict['w']), int(img_dict['h']))
                if qp.isNull():
                    img_dict['pixmap'] = None
                '''else:  # Potential to extract some images.
                    file_name = QtWidgets.QFileDialog.getSaveFileName(self, 'Save File', '', '*.jpg')
                    qp.save(file_name[0])  # tuple of path and type'''
            self.page_dict['images'].append(img_dict)

        if isinstance(lobj, Iterable):
            # Includes LTFigure objects
            # Must not iterate the TextLines within the TextBox - otherwise double ups occur
            for obj in lobj:
                self.get_pdf_items_and_hierarchy(page, obj, depth=depth + 1)

    def show_page(self):
        """ Display pdf page, using the PDF objects. Only checked pdf objects are displayed.
        Coded text segments are shown in their QGraphicsTextItems. """

        page = self.pages[self.page_num]
        # Start and end marks for code positioning in textEdit display
        self.file_['start'] = page['plain_text_start']
        self.file_['end'] = page['plain_text_end']
        page_rect = page['mediabox']
        self.ui.textEdit.setText("")
        text_edit_text = ""
        self.pdf_object_info_text = ""
        #    text_edit_text = "PAGE RECT: " + str(page_rect) + "\n"
        self.scene = QtWidgets.QGraphicsScene()
        self.ui.graphicsView.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)  #RenderHint.SmoothPixmapTransform)  # Antialiasing
        self.scene.setSceneRect(QtCore.QRectF(0, 0, page_rect[2], page_rect[3]))
        self.ui.graphicsView.setScene(self.scene)
        self.scene.setBackgroundBrush(QtCore.Qt.GlobalColor.white)
        self.scene.installEventFilter(self)
        gray_pen = QtGui.QPen(QtCore.Qt.GlobalColor.gray, 1, QtCore.Qt.PenStyle.SolidLine)
        self.scene.addRect(0, 0, page_rect[2], page_rect[3], gray_pen)
        counter = 0
        if self.ui.checkBox_rect.isChecked():
            for r in page['rect']:
                counter += 1
                self.pdf_object_info_text += f"RECT: {r}\n"
                item = self.scene.addRect(r['x'], r['y'], r['w'], r['h'])
                if r['fill']:
                    color = self.get_qcolor(r['non_stroking_color'])
                    item.setPen(QtGui.QPen(QtGui.QBrush(QtCore.Qt.BrushStyle.NoBrush), 0))  # Border
                    item.setBrush(color)
                if r['stroke']:
                    color = self.get_qcolor(r['stroking_color'])
                    item.setPen(QtGui.QPen(color, r['linewidth']))  # Border
        if self.ui.checkBox_curve.isChecked():
            # https://stackoverflow.com/questions/63016214/drawing-multi-point-curve-with-pyqt5
            # addPath QPainterPath - maybe?
            for c in page['curves']:
                counter += 1
                self.pdf_object_info_text += f"CURVE: {c}\n"
                if c['stroke'] and not c['fill']:
                    item = QtGui.QPolygonF(c['pts'])
                    color = self.get_qcolor(c['stroking_color'])
                    brush = QtGui.QBrush(QtCore.Qt.BrushStyle.NoBrush)
                    pen = QtGui.QPen(color, c['linewidth'], QtCore.Qt.PenStyle.SolidLine)  # Border
                    self.scene.addPolygon(item, pen, brush)
                if c['fill'] and not c['stroke']:
                    brush = QtGui.QColor(self.get_qcolor(c['non_stroking_color']))  # Fill
                    pen = QtGui.QPen(QtGui.QBrush(QtCore.Qt.BrushStyle.NoBrush), 0)  # Border
                    item = QtGui.QPolygonF(c['pts'])
                    self.scene.addPolygon(item,pen , brush)
        # Images before or after curves?
        # Seems better here, but sometimes overlaps
        if self.ui.checkBox_image.isChecked():
            for img in page['images']:
                counter += 1
                self.pdf_object_info_text += "IMAGE:\n"
                for k in img:
                    self.pdf_object_info_text += f"{k}: {img[k]}\n"
                self.pdf_object_info_text += "\n"
                if img['pixmap']:
                    qpixmap_item = self.scene.addPixmap(img['pixmap'])
                    qpixmap_item.setPos(img['x'], img['y'])
                else:
                    # Do not use placeholder question mark icon
                    '''pixmap = QtGui.QPixmap()
                    pixmap.loadFromData(QtCore.QByteArray.fromBase64(question_icon), "png")
                    pixmap = pixmap.scaled(int(img['w']), int(img['h']))
                    qpixmap_item = self.scene.addPixmap(pixmap)
                    qpixmap_item.setPos(img['x'], img['y'])'''
                    pass
        if self.ui.checkBox_line.isChecked():
            for line in page['lines']:
                counter += 1
                self.pdf_object_info_text += f"LINE: {line}\n"
                color = QtCore.Qt.GlobalColor.black
                if line['stroke']:
                    color = self.get_qcolor(line['stroking_color'])
                if line['fill']:
                    color = self.get_qcolor(line['non_stroking_color'])
                line_pen = QtGui.QPen(color, line['linewidth'], QtCore.Qt.PenStyle.SolidLine)
                self.scene.addLine(line['x0'], line['y0'], line['x1'], line['y1'], line_pen)
        self.display_page_text_objects()
        counter += len(page['text_boxes'])
        text_edit_text += f"\n\nOBJECTS: {counter}"
        self.pdf_object_info_text += "\n" + _("TEXT START CHARACTER POSITION: ") + str(page['plain_text_start']) + "\n"
        self.pdf_object_info_text += _("TEXT END CHARACTER POSITION: ") + str(page['plain_text_end']) + "\n"
        self.pdf_object_info_text += _("NUMBER OF CHARACTERS: ") + str(page['plain_text_end'] - page['plain_text_start'])
        self.ui.textEdit.setText(page['plain_text'])
        self.get_coded_text_update_eventfilter_tooltips()

    def display_page_text_objects(self):
        """ PDF text graphics objects are shown on scene.
         Update the highlighting of these objects when codes are marked / unmarked or changed in some way,
          e.g. changed code colour.
          Called by: show_page, extend_left, extend_right, shrink_left, shrink_right, merge_codes, delete_code,
          mark, unmark, undo_last_unmarked, rename_category_or_code, change_code_color, change_code_to_another_code
        """

        if not self.file_:
            return
        for graphics_item in self.scene.items():
            if isinstance(graphics_item, QtWidgets.QGraphicsTextItem):
                self.scene.removeItem(graphics_item)

        if not self.ui.checkBox_text.isChecked():
            return
        page = self.pages[self.page_num]
        for text_box in page['text_boxes']:
            self.pdf_object_info_text += f"TEXT: {text_box}\n"
            display_text = text_box['text']
            # remove line ending to shrink textbox size
            if display_text[-1] == "\n":
                display_text = display_text[:-1] + " "
            item = self.scene.addText(display_text)
            item.setPos(text_box['left'], text_box['top'])
            '''print(i['fontname'], type(t['fontname']), t['fontsize'], type(t['fontsize']))
            font = QtGui.QFont(t['fontname'], t['fontsize']) '''
            adjustment = int(self.ui.comboBox_fontsize.currentText())
            font_size = text_box['fontsize'] + adjustment  # e.g. minus 2 helps stop text overlaps
            if font_size < 4:
                font_size = 4
            font = QtGui.QFont(self.app.settings['font'], font_size)
            item.setFont(font)
            color = self.get_qcolor(text_box['color'])
            if self.ui.checkBox_black_text.isChecked():
                color = QtCore.Qt.GlobalColor.black
            item.setDefaultTextColor(color)
            self.format_text_box(item, text_box)
            # Interaction
            item.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditorInteraction)
            item.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
            text_box['graphic_item_ref'] = item

    def format_text_box(self, item, text_item):
        """ Apply code backgrounds to text.
         Loop through coded text and match any at this position.
         if self.important checked and this is not important. Do not colour.
         param:
            item: QGraphicsTextItem
            text_item: dictionary of pdf text item data """

        cursor = item.textCursor()
        codes_for_item = []

        for code_ in self.code_text:
            if code_['pos0'] <= text_item['pos0'] < code_['pos1']:
                codes_for_item.append(code_)
            if text_item['pos0'] < code_['pos0'] < text_item['pos1']:
                codes_for_item.append(code_)
            # Code starts within text_item text and continues beyond it
            if code_['pos0'] < text_item['pos1'] < code_['pos1']:
                codes_for_item.append(code_)
            #print(f"Code {code_['seltext']} {code_['pos0']} - {code_['pos1']}")
        if not codes_for_item:
            return
        tooltip_list = []
        for graphics_item_code in codes_for_item:
            # When important flag selected only show important coded text items
            if self.important and graphics_item_code['important'] is None:
                continue
            pos0 = int(graphics_item_code['pos0'] - text_item['pos0'])
            if pos0 < 0:
                pos0 = 0
            pos1 = int(graphics_item_code['pos1'] - text_item['pos0'])
            if pos1 > len(text_item['text']):
                pos1 = len(text_item['text']) - 1
            cursor.setPosition(pos0, QtGui.QTextCursor.MoveMode.MoveAnchor) # Or zero
            cursor.setPosition(pos1, QtGui.QTextCursor.MoveMode.KeepAnchor)
            color = graphics_item_code['color']
            brush = QBrush(QColor(color))
            fmt = QtGui.QTextCharFormat()
            fmt.setBackground(brush)
            # Foreground depends on the defined need_white_text color in color_selector
            foreground_color = TextColor(color).recommendation
            fmt.setForeground(QBrush(QColor(foreground_color)))
            '''if text_item['bold']:
                fmt.setFontWeight(QtGui.QFont.Weight.Bold)'''
            cursor.mergeCharFormat(fmt)
            #cursor.setCharFormat(fmt)
            tooltip_item_text = graphics_item_code['name']
            if graphics_item_code['memo'] is not None and graphics_item_code['memo'] != "":
                tooltip_item_text += "\n" + _("Memo: ") + graphics_item_code['memo']
            if graphics_item_code['important'] == 1:
                tooltip_item_text += "\n" + _("Important")
            tooltip_list.append(tooltip_item_text)
        tooltip_list = list(set(tooltip_list))
        tooltip_list.sort()
        item.setToolTip("\n".join(tooltip_list))

    def graphicsview_menu(self, position):
        """ Menu for unmarking codes, code memos and important marking.
        Also for selecting recent codes for marking. """

        scene_item = self.ui.graphicsView.itemAt(position)
        if scene_item is None:
            return
        if not isinstance(scene_item, QtWidgets.QGraphicsTextItem):
            return
        text_box = None
        for tb in self.pages[self.page_num]['text_boxes']:
            if tb['graphic_item_ref'] == scene_item:
                text_box = tb
                break
        if not text_box:
            return
        # Get codes applied to text box
        codes_in_text_box = []
        for code_ in self.code_text:
            # Need code_ is not in .. otherwise same code can be added multiple times
            if code_['pos0'] <= text_box['pos0'] < code_['pos1'] and code_ not in codes_in_text_box:
                codes_in_text_box.append(code_)
            if text_box['pos0'] < code_['pos0'] < text_box['pos1'] and code_ not in codes_in_text_box:
                codes_in_text_box.append(code_)
            # Code starts within text_item text and continues beyond it
            if code_['pos0'] < text_box['pos1'] < code_['pos1'] and code_ not in codes_in_text_box:
                codes_in_text_box.append(code_)

        # Menu for graphics view area
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        ''' Cannot mark selected textboxes. as soon as context menu appears, textbox selections are removed.
        action_mark = None
        '''
        action_unmark = None
        action_memo = None
        action_important = None
        action_remove_important = None
        important_codes = []
        if codes_in_text_box:
            action_memo = menu.addAction(_("Code memo"))
            for c in codes_in_text_box:
                if c['important'] == 1:
                    important_codes.append(c)
            if len(codes_in_text_box) > len(important_codes):
                action_important = menu.addAction(_("Flag important"))
            if important_codes:
                action_remove_important = menu.addAction(_("Remove important flag"))
            action_unmark = menu.addAction(_("Unmark"))

        action = menu.exec(self.ui.graphicsView.mapToGlobal(position))
        if action == action_unmark:
            if len(codes_in_text_box) > 1:
                ui = DialogSelectItems(self.app, codes_in_text_box, _("Select code to unmark"), "single")
                ok = ui.exec()
                if not ok:
                    return
                to_unmark = ui.get_selected()
                if to_unmark is None:
                    return
                self.unmark(position=None, ctid=to_unmark['ctid'])
            else:
                if codes_in_text_box:
                    self.unmark(position=None, ctid=codes_in_text_box[0]['ctid'])
            return
        if action == action_memo:
            if len(codes_in_text_box) > 1:
                ui = DialogSelectItems(self.app, codes_in_text_box, _("Select code to memo"), "single")
                ok = ui.exec()
                if not ok:
                    return
                to_memo = ui.get_selected()
                if to_memo is None:
                    return
                self.coded_text_memo(position=None, ctid=to_memo['ctid'])
            else:
                self.coded_text_memo(position=None, ctid=codes_in_text_box[0]['ctid'])
            return
        if action == action_important:
            if len(codes_in_text_box) > 1:
                ui = DialogSelectItems(self.app, codes_in_text_box, _("Select code for important flag"), "single")
                ok = ui.exec()
                if not ok:
                    return
                to_make_important = ui.get_selected()
                if to_make_important is None:
                    return
                self.set_important(position=None, ctid=to_make_important['ctid'], important=True)
            else:
                self.set_important(position=None, ctid=codes_in_text_box[0]['ctid'], important=True)
            #self.set_important(position=cursor.position(), ctid=None, important=True)
            return
        if action == action_remove_important:
            if len(codes_in_text_box) > 1:
                ui = DialogSelectItems(self.app, codes_in_text_box, _("Select code to remove important flag"), "single")
                ok = ui.exec()
                if not ok:
                    return
                remove_important = ui.get_selected()
                if remove_important is None:
                    return
                self.set_important(position=None, ctid=remove_important['ctid'], important=False)
            else:
                self.set_important(position=None, ctid=codes_in_text_box[0]['ctid'], important=False)
            return

    def get_qcolor(self, pdf_color) -> QtGui.QColor:
        """  Get a pdf_color which can be in various formats.
        Return a QColor object.
        A float or integer
        A list with one numeric element --> (0=black -> gray -> 1=white)
        A list with one String element (PSLiteral)
        A 3-value color is RGB
        A 4-value color is CMYK
        param:
            int, float or tuple.
        return:
            QColor object
        """

        color = QtCore.Qt.GlobalColor.green  # Wild Green default color
        if isinstance(pdf_color, float) or isinstance(pdf_color, int):  # gray scale 0 to 1
            int_col = int(pdf_color * 255)
            color = QtGui.QColor(int_col, int_col, int_col)
        if isinstance(pdf_color, (tuple, list)) and len(pdf_color) == 1:  # gray scale 0 to 1
            if isinstance(pdf_color[0], (float, int)):
                int_col = int(pdf_color[0] * 255)
                color = QtGui.QColor(int_col, int_col, int_col)
            if isinstance(pdf_color[0], PSLiteral):
                #print(pdf_color[0], pdf_color[0].name)  # /'P0'  P0
                pass
                # Will have a Green object, use default color

        if isinstance(pdf_color, (tuple, list)) and len(pdf_color) == 3:  # rgb
            try:
                color = QtGui.QColor()
                color.setRgbF(pdf_color[0], pdf_color[1], pdf_color[2])
            except Exception as e:
                #print("RGB", e)
                pass
        if isinstance(pdf_color, (tuple, list)) and len(pdf_color) == 4:  # cmyk
            try:
                color = QtGui.QColor()
                color.setCmykF(pdf_color[0], pdf_color[1], pdf_color[2], pdf_color[3])
            except Exception as e:
                #print(e)
                pass
        return color

    def get_coded_text_update_eventfilter_tooltips(self):
        """ Called by load_file, and from other dialogs on update.
        Tooltips are for all coded_text or only for important if important is flagged.
        """

        if self.file_ is None:
            return
        sql_values = [int(self.file_['id']), self.app.settings['codername']]  # , self.file_['start'], self.file_['end']]
        # Get code text for this file and for this coder
        self.code_text = []
        # seltext length, longest first, so overlapping shorter text is superimposed.
        sql = "select code_text.ctid, code_text.cid, fid, seltext, pos0, pos1, code_text.owner, code_text.date, " \
              "code_text.memo, important, name"
        sql += " from code_text join code_name on code_text.cid = code_name.cid"
        sql += " where fid=? and code_text.owner=? "
        # sql += " and pos0 >=? and pos1 <=? "  # problem area, removed
        sql += "order by length(seltext) desc, important asc"
        cur = self.app.conn.cursor()
        cur.execute(sql, sql_values)
        code_results = cur.fetchall()
        keys = 'ctid', 'cid', 'fid', 'seltext', 'pos0', 'pos1', 'owner', 'date', 'memo', 'important', 'name'
        for row in code_results:
            self.code_text.append(dict(zip(keys, row)))

        # Update filter for tooltip and redo formatting
        if self.important:
            imp_coded = []
            for c in self.code_text:
                if c['important'] == 1:
                    imp_coded.append(c)
            self.eventFilterTT.set_codes_and_annotations(self.app, imp_coded, self.codes, self.annotations,
                                                         self.file_)
        else:
            self.eventFilterTT.set_codes_and_annotations(self.app, self.code_text, self.codes, self.annotations,
                                                         self.file_)
        self.unlight()
        self.highlight()

    def unlight(self):
        """ Remove all text highlighting from current file. """

        if self.ui.textEdit.toPlainText() == "":
            return
        cursor = self.ui.textEdit.textCursor()
        cursor.setPosition(0, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(abs(len(self.ui.textEdit.toPlainText()) - 1), QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(QtGui.QTextCharFormat())

    def highlight(self):
        """ Apply text highlighting to current file.
        If no colour has been assigned to a code, those coded text fragments are coloured gray.
        Each code text item contains: fid, date, pos0, pos1, seltext, cid, status, memo,
        name, owner.
        For defined colours in color_selector, make text light on dark, and conversely dark on light
        """

        if self.file_ is None or self.ui.textEdit.toPlainText() == "":
            return
        # Add coding highlights
        codes = {x['cid']: x for x in self.codes}
        for item in self.code_text:
            fmt = QtGui.QTextCharFormat()
            cursor = self.ui.textEdit.textCursor()
            '''print(f"len text {len(self.ui.textEdit.toPlainText())} TEXTEDIT page {self.page_num} pos0 {item['pos0'] - self.file_['start']}"
                  f" pos1 {item['pos1'] - self.file_['start']}"
                  f" page plain text end {self.pages[self.page_num]['plain_text_end']}")  # tmp'''
            if item['pos0'] > self.pages[self.page_num]['plain_text_end'] or item['pos1'] < self.pages[self.page_num]['plain_text_start']:
                continue
            cursor.setPosition(int(item['pos0'] - self.file_['start']), QtGui.QTextCursor.MoveMode.MoveAnchor)
            cursor.setPosition(int(item['pos1'] - self.file_['start']), QtGui.QTextCursor.MoveMode.KeepAnchor)
            color = codes.get(item['cid'], {}).get('color', "#777777")  # default gray
            brush = QBrush(QColor(color))
            fmt.setBackground(brush)
            # Foreground depends on the defined need_white_text color in color_selector
            text_brush = QBrush(QColor(TextColor(color).recommendation))
            fmt.setForeground(text_brush)
            # Highlight codes with memos - these are italicised
            # Italics also used for overlapping codes
            if item['memo'] != "":
                fmt.setFontItalic(True)
            else:
                fmt.setFontItalic(False)
            # Bold important codes
            if item['important']:
                fmt.setFontWeight(QtGui.QFont.Weight.Bold)
            # Use important flag for ONLY showing important codes (button selected)
            if self.important and item['important'] == 1:
                cursor.setCharFormat(fmt)
            # Show all codes, as important button not selected
            if not self.important:
                cursor.setCharFormat(fmt)

        # Add annotation marks - these are in bold, important codings are also bold
        for note in self.annotations:
            if len(self.file_.keys()) > 0:  # will be zero if using autocode and no file is loaded
                # Cursor pos could be negative if annotation was for an earlier text portion
                cursor = self.ui.textEdit.textCursor()
                if note['fid'] == self.file_['id'] and \
                        0 <= int(note['pos0']) - self.file_['start'] < int(note['pos1']) - self.file_['start'] <= \
                        len(self.ui.textEdit.toPlainText()):
                    cursor.setPosition(int(note['pos0']) - self.file_['start'], QtGui.QTextCursor.MoveMode.MoveAnchor)
                    cursor.setPosition(int(note['pos1']) - self.file_['start'], QtGui.QTextCursor.MoveMode.KeepAnchor)
                    format_bold = QtGui.QTextCharFormat()
                    format_bold.setFontWeight(QtGui.QFont.Weight.Bold)
                    cursor.mergeCharFormat(format_bold)
        self.apply_underline_to_overlaps()

    def apply_underline_to_overlaps(self):
        """ Apply underline format to coded text sections which are overlapping.
        Qt underline options: # NoUnderline, SingleUnderline, DashUnderline, DotLine, DashDotLine, WaveUnderline
        Adjust for start of text file, as this may be a smaller portion of the full text file.
        """

        if self.important:
            return
        overlaps = []
        for i in self.code_text:
            for j in self.code_text:
                if j != i:
                    if j['pos0'] <= i['pos0'] <= j['pos1']:
                        if (j['pos0'] >= i['pos0'] and j['pos1'] <= i['pos1']) and (j['pos0'] != j['pos1']):
                            overlaps.append([j['pos0'], j['pos1']])
                        elif (i['pos0'] >= j['pos0'] and i['pos1'] <= j['pos1']) and (i['pos0'] != i['pos1']):
                            overlaps.append([i['pos0'], i['pos1']])
                        elif j['pos0'] > i['pos0'] and (j['pos0'] != i['pos1']):
                            overlaps.append([j['pos0'], i['pos1']])
                        elif j['pos1'] != i['pos0']:  # j['pos0'] < i['pos0']:
                            overlaps.append([j['pos1'], i['pos0']])
        cursor = self.ui.textEdit.textCursor()
        for o in overlaps:
            fmt = QtGui.QTextCharFormat()
            fmt.setUnderlineStyle(QtGui.QTextCharFormat.UnderlineStyle.SingleUnderline)
            if self.app.settings['stylesheet'] == 'dark':
                fmt.setUnderlineColor(QColor("#000000"))
            else:
                fmt.setUnderlineColor(QColor("#FFFFFF"))
            cursor.setPosition(o[0] - self.file_['start'], QtGui.QTextCursor.MoveMode.MoveAnchor)
            cursor.setPosition(o[1] - self.file_['start'], QtGui.QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(fmt)

    def mark(self, by_text_boxes=False):
        """ Mark selected text in file with currently selected code.
        Need to check for multiple same codes at same pos0 and pos1.
        Update recent_codes list.
        Adjust for start of text file, as this may be a smaller portion of the full text file.

        Code selected graphics textboxes. Textboxes are selected via mouse drag.
        Graphics textboxes are referenced within pages[page_num][text_box] dictionary.
        Textboxes often overlap, so link up for one coded segment:
        CHAR POS: 706 - 818, CHAR POS: 865 - 976, CHAR POS: 976 - 1078

        param:
            by_text_boxes: Bool: True = coding by text boxes, False = coding by Text Edit
        """

        if self.different_text_lengths and by_text_boxes:
            msg = _("PDF loaded text does not match Imported PDF text length.") + "\n"
            msg += _("Mark using the right hand side text pane.")
            Message(self.app, _("Cannot mark"), msg).exec()
            return
        if self.file_ is None:
            Message(self.app, _('Warning'), _("No file was selected"), "warning").exec()
            return
        item = self.ui.treeWidget.currentItem()
        if item is None:
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec()
            return
        if item.text(1).split(':')[0] == 'catid':  # must be a code
            return
        cid = int(item.text(1).split(':')[1])

        pos0 = -1
        pos1 = -1

        if by_text_boxes:
            # Mark by Graphics Text Boxes
            selected_boxes = []
            for textbox in self.pages[self.page_num]['text_boxes']:
                for graphic_textbox in self.selected_graphic_textboxes:
                    if textbox['graphic_item_ref'] == graphic_textbox:
                        selected_boxes.append(textbox)
            # Go through the text_boxes character positions
            # Link up boxes so that one string of coded text is applied.
            # for tb in selected_boxes:
            #    print("CHAR POS:", tb['pos0'], tb['pos1'])
            linked_positions = []

            pos0 = selected_boxes[0]['pos0']
            pos1 = selected_boxes[0]['pos1']
            seltext = selected_boxes[0]['text']
            selected_boxes.pop(0)
            for box in selected_boxes:
                if box['pos0'] == pos1:
                    pos1 = box['pos1']
                    seltext += box['text']
        else:
            # Mark by TextEdit
            seltext = self.ui.textEdit.textCursor().selectedText()
            pos0 = self.ui.textEdit.textCursor().selectionStart() + self.file_['start']
            pos1 = self.ui.textEdit.textCursor().selectionEnd() + self.file_['start']

        if pos0 == pos1:
            return

        # Add the coded section to code text, add to database and update GUI
        coded = {'cid': cid, 'fid': int(self.file_['id']), 'seltext': seltext,
                 'pos0': pos0, 'pos1': pos1, 'owner': self.app.settings['codername'], 'memo': "",
                 'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                 'important': None}

        # Check for an existing duplicated marking first
        cur = self.app.conn.cursor()
        cur.execute("select * from code_text where cid = ? and fid=? and pos0=? and pos1=? and owner=?",
                    (coded['cid'], coded['fid'], coded['pos0'], coded['pos1'], coded['owner']))
        result = cur.fetchall()
        if len(result) > 0:
            # The event can trigger multiple times, so do not present a warning to the user
            return
        cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,\
            memo,date, important) values(?,?,?,?,?,?,?,?,?)", (coded['cid'], coded['fid'],
                                                               coded['seltext'], coded['pos0'], coded['pos1'],
                                                               coded['owner'],
                                                               coded['memo'], coded['date'], coded['important']))
        self.app.conn.commit()
        self.app.delete_backup = False
        # Update filter for tooltip and update code colours
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()

        # Update recent_codes
        tmp_code = None
        for c in self.codes:
            if c['cid'] == cid:
                tmp_code = c
        if tmp_code is None:
            return
        # Need to remove from recent_codes, if there, and add back in first position
        for item in self.recent_codes:
            if item == tmp_code:
                self.recent_codes.remove(item)
                break
        self.recent_codes.insert(0, tmp_code)
        if len(self.recent_codes) > 10:
            self.recent_codes = self.recent_codes[:10]
        self.update_file_tooltip()
        self.display_page_text_objects()

    def undo_last_unmarked_code(self):
        """ Restore the last deleted code(s).
        One code or multiple, depends on what was selected when the unmark method was used.
        Requires self.undo_deleted_codes """

        if not self.undo_deleted_codes:
            return
        cur = self.app.conn.cursor()
        for item in self.undo_deleted_codes:
            cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,\
                memo,date, important) values(?,?,?,?,?,?,?,?,?)", (item['cid'], item['fid'],
                                                                   item['seltext'], item['pos0'], item['pos1'],
                                                                   item['owner'],
                                                                   item['memo'], item['date'], item['important']))
        self.app.conn.commit()
        self.undo_deleted_codes = []
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        self.display_page_text_objects()

    def unmark(self, position=None, ctid=None):
        """ Remove code marking by this coder from selected text in current file.
        Called by text_edit_context_menu, graphicsview_menu
        Adjust for start of text file, as this may be a smaller portion of the full text file.
        Coded text items may be based ona text cursor location, if selected by the text edit,
        or may be based on a ctid if selected via the graphics scene.
        param:
            position: QTextCursor position Integer
            ctid: the code text integer for the specific coded segment
        """

        if self.file_ is None:
            return
        unmarked_list = []
        for item in self.code_text:
            if position and item['pos0'] <= position + self.file_['start'] <= item['pos1'] and \
                    item['owner'] == self.app.settings['codername']:
                unmarked_list.append(item)
            if ctid and ctid == item['ctid']:
                unmarked_list.append(item)
                break
        if not unmarked_list:
            return
        to_unmark = []
        if len(unmarked_list) == 1:
            to_unmark = [unmarked_list[0]]
        # Multiple codes to select from
        if len(unmarked_list) > 1:
            ui = DialogSelectItems(self.app, unmarked_list, _("Select code to unmark"), "multi")
            ok = ui.exec()
            if not ok:
                return
            to_unmark = ui.get_selected()
        if to_unmark is None:
            return
        self.undo_deleted_codes = deepcopy(to_unmark)
        # Delete from db, remove from coding and update highlights
        cur = self.app.conn.cursor()
        for item in to_unmark:
            cur.execute("delete from code_text where ctid=?", [item['ctid']])
            self.app.conn.commit()
        # Update filter for tooltip and update code colours
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        self.update_file_tooltip()
        self.app.delete_backup = False
        self.display_page_text_objects()

    def annotate(self, cursor_pos=None):
        """ Add view, or remove an annotation for selected text.
        Annotation positions are displayed as bold text.
        Adjust for start of text file, as this may be a smaller portion of the full text file.

        Called via context menu, button
        """

        if self.file_ is None:
            Message(self.app, _('Warning'), _("No file was selected"), "warning").exec()
            return
        pos0 = self.ui.textEdit.textCursor().selectionStart()
        pos1 = self.ui.textEdit.textCursor().selectionEnd()
        text_length = len(self.ui.textEdit.toPlainText())
        if pos0 >= text_length or pos1 > text_length:
            return
        item = None
        details = ""
        annotation = ""
        # Find annotation at this position for this file
        if cursor_pos is None:
            for note in self.annotations:
                if ((note['pos0'] <= pos0 + self.file_['start'] <= note['pos1']) or
                    (note['pos0'] <= pos1 + self.file_['start'] <= note['pos1'])) \
                        and note['fid'] == self.file_['id']:
                    item = note  # use existing annotation
                    details = item['owner'] + " " + item['date']
                    break
        if cursor_pos is not None:  # Try point position, if cursor is on an annotation, but no text selected
            for note in self.annotations:
                if cursor_pos + self.file_['start'] >= note['pos0'] and cursor_pos <= note['pos1'] + self.file_['start'] \
                        and note['fid'] == self.file_['id']:
                    item = note  # use existing annotation
                    details = item['owner'] + " " + item['date']
                    pos0 = cursor_pos
                    pos1 = cursor_pos
                    break
        # Exit this method if no text selected and there is no annotation at this position
        if pos0 == pos1 and item is None:
            return

        # Add new item to annotations, add to database and update GUI
        if item is None:
            item = {'fid': int(self.file_['id']), 'pos0': pos0 + self.file_['start'],
                    'pos1': pos1 + self.file_['start'],
                    'memo': str(annotation), 'owner': self.app.settings['codername'],
                    'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'anid': -1}
            ui = DialogMemo(self.app, _("Annotation: ") + details, item['memo'])
            ui.exec()
            item['memo'] = ui.memo
            if item['memo'] != "":
                cur = self.app.conn.cursor()
                cur.execute("insert into annotation (fid,pos0, pos1,memo,owner,date) \
                    values(?,?,?,?,?,?)", (item['fid'], item['pos0'], item['pos1'],
                                           item['memo'], item['owner'], item['date']))
                self.app.conn.commit()
                self.app.delete_backup = False
                cur.execute("select last_insert_rowid()")
                anid = cur.fetchone()[0]
                item['anid'] = anid
                self.annotations.append(item)
                self.parent_textEdit.append(_("Annotation added at position: ")
                                            + f"{item['pos0']}-{item['pos1']} {_('for:')} {self.file_['name']}")
                self.get_coded_text_update_eventfilter_tooltips()
            return

        # Edit existing annotation
        ui = DialogMemo(self.app, _("Annotation: ") + details, item['memo'])
        ui.exec()
        item['memo'] = ui.memo
        if item['memo'] != "":
            item['date'] = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
            cur = self.app.conn.cursor()
            sql = "update annotation set memo=?, date=? where anid=?"
            cur.execute(sql, (item['memo'], item['date'], item['anid']))
            self.app.conn.commit()
            self.app.delete_backup = False

            self.annotations = self.app.get_annotations()
            self.get_coded_text_update_eventfilter_tooltips()
            return

        # If blank delete the annotation
        if item['memo'] == "":
            cur = self.app.conn.cursor()
            cur.execute("delete from annotation where pos0 = ?", (item['pos0'],))
            self.app.conn.commit()
            self.app.delete_backup = False
            self.annotations = self.app.get_annotations()
            self.parent_textEdit.append(_("Annotation removed from position ")
                                        + f"{item['pos0']} {_('for:')} {self.file_['name']}")
        self.get_coded_text_update_eventfilter_tooltips()

    def get_pdf_metadata(self, filepath):
        """  """

        fp = open(filepath, 'rb')
        parser = PDFParser(fp)
        doc = PDFDocument(parser)
        info = doc.info  # tmp
        self.metadata = ""
        if info:
            for k, v in info[0].items():
                # print(k,v)
                self.metadata += k + " = "
                try:
                    self.metadata += v.decode('UTF-8', errors="ignore")
                except AttributeError as e:
                    self.metadata += str(e)
                self.metadata += "\n"
    @staticmethod
    def get_image_type(stream_first_4_bytes) -> str:
        """Find out the image file type based on the magic number comparison of the first 4 (or 2) bytes.
        See https://en.wikipedia.org/wiki/List_of_file_signatures """

        file_type = None
        bytes_as_hex = b2a_hex(stream_first_4_bytes)
        if bytes_as_hex.startswith(b'ffd8'):
            file_type = '.jpeg'
        elif bytes_as_hex == '89504e47':
            file_type = '.png'
        elif bytes_as_hex == '47494638':
            file_type = '.gif'
        elif bytes_as_hex.startswith(b'424d'):
            file_type = '.tiff'
        elif bytes_as_hex.startswith(b'4d4d'):
            file_type = '.bmp'
        return file_type

    @staticmethod
    def get_char_info(ob) -> tuple:
        """Font, fontsize and color info of LTChar if available, otherwise defaults
        """

        #print(ob, ob.__dir__())
        color = 0  # Default Black
        fontname = "ITC Officina Sans Book Regular"
        fontsize = 10
        if hasattr(ob, 'fontname'):
            fontname = ob.fontname
            # print(ob.fontname)
        if hasattr(ob, 'size'):
            fontsize = ob.size
        if hasattr(ob, 'graphicstate'):
            # Color may be None
            try:
                color = ob.graphicstate.ncolor
            except TypeError:
                pass
            if color is None:
                try:
                    color = ob.graphicstate.scolor
                except TypeError:
                    pass
        if color is None:
            color = 0
        return fontname, fontsize, color

    @staticmethod
    def help():
        """ Open help for transcribe section in browser. """

        url = "https://github.com/ccbogel/QualCoder/wiki/4.3.-Coding-Text-on-PDFs"
        webbrowser.open(url)


class ToolTipEventFilter(QtCore.QObject):
    """ Used to add a dynamic tooltip for the textEdit.
    The tool top text is changed according to its position in the text.
    If over a coded section the codename(s) or Annotation note are displayed in the tooltip.
    """

    codes = None
    code_text = None
    annotations = None
    file_id = None
    offset = 0
    app = None

    def set_codes_and_annotations(self, app, code_text, codes, annotations, file_):
        """ Code_text contains the coded text to be displayed in a tooltip.
        Annotations - a mention is made if current position is annotated

        param:
            code_text: List of dictionaries of the coded text contains: pos0, pos1, seltext, cid, memo
            codes: List of dictionaries contains id, name, color
            annotations: List of dictionaries of
            offset: integer 0 if all the text is loaded, other numbers mean a portion of the text is loaded,
            beginning at the offset
        """

        self.app = app
        self.code_text = code_text
        self.codes = codes
        self.annotations = annotations
        self.file_id = file_['id']
        self.offset = file_['start']
        for item in self.code_text:
            for c in self.codes:
                if item['cid'] == c['cid']:
                    item['name'] = c['name']
                    item['color'] = c['color']

    def eventFilter(self, receiver, event):
        # QtGui.QToolTip.showText(QtGui.QCursor.pos(), tip)
        if event.type() == QtCore.QEvent.Type.ToolTip:
            cursor = receiver.cursorForPosition(event.pos())
            pos = cursor.position()
            receiver.setToolTip("")
            text_ = ""
            multiple_msg = '<p style="color:#f89407">' + _("Press O to cycle overlapping codes") + "</p>"
            multiple = 0
            # Occasional None type error
            if self.code_text is None:
                # Call Base Class Method to Continue Normal Event Processing
                return super(ToolTipEventFilter, self).eventFilter(receiver, event)
            for item in self.code_text:
                if item['pos0'] - self.offset <= pos <= item['pos1'] - self.offset and \
                        item['seltext'] is not None:
                    seltext = item['seltext']
                    seltext = seltext.replace("\n", "")
                    seltext = seltext.replace("\r", "")
                    # Selected text with a readable cut off, not cut off halfway through a word.
                    if len(seltext) > 90:
                        pre = seltext[0:40].split(' ')
                        post = seltext[len(seltext) - 40:].split(' ')
                        try:
                            pre = pre[:-1]
                        except IndexError:
                            pass
                        try:
                            post = post[1:]
                        except IndexError:
                            pass
                        seltext = " ".join(pre) + " ... " + " ".join(post)
                    try:
                        color = TextColor(item['color']).recommendation
                        text_ += '<p style="background-color:' + item['color'] + "; color:" + color + '"><em>'
                        text_ += item['name'] + "</em>"
                        if self.app.settings['showids']:
                            text_ += f" [ctid:{item['ctid']}]"
                        text_ += "<br />" + seltext
                        if item['memo'] != "":
                            text_ += "<br /><em>" + _("MEMO: ") + item['memo'] + "</em>"
                        if item['important'] == 1:
                            text_ += "<br /><em>IMPORTANT</em>"
                        text_ += "</p>"
                        multiple += 1
                    except Exception as e:
                        msg = f"Codes ToolTipEventFilter Exception\n{e} Possible key error:\n{item}"
                        logger.error(msg)
            if multiple > 1:
                text_ = multiple_msg + text_
            # Check annotations
            for ann in self.annotations:
                if ann['pos0'] - self.offset <= pos <= ann['pos1'] - self.offset and self.file_id == ann['fid']:
                    text_ += "<p>" + _("ANNOTATED:") + ann['memo'] + "</p>"
            if text_ != "":
                receiver.setToolTip(text_)
        # Call Base Class Method to Continue Normal Event Processing
        return super(ToolTipEventFilter, self).eventFilter(receiver, event)


class GraphicsScene(QtWidgets.QGraphicsScene):
    """ set the scene for the graphics objects and re-draw events. """

    def __init__(self, parent=None):
        super(GraphicsScene, self).__init__(parent)
        self.parent = parent
        self.scene_width = 700
        self.scene_height = 560
        # parent = None
        self.setSceneRect(QtCore.QRectF(0, 0, self.scene_width, self.scene_height))

    '''def mouseMoveEvent(self, mouse_event):
        """ On mouse move, an item might be repositioned so need to redraw all the link_items.
        This slows re-drawing down, but is dynamic. """

        super(GraphicsScene, self).mousePressEvent(mouse_event)
        #for item in self.items():'''

    def mousePressEvent(self, mouseEvent):
        super(GraphicsScene, self).mousePressEvent(mouseEvent)
        position = QtCore.QPointF(mouseEvent.scenePos())
        print(position.x(), position.y())
        #logger.debug("pressed here: " + str(position.x()) + ", " + str(position.y()))
        for item in self.items(): # item is QGraphicsProxyWidget
            print(item)

    def mouseReleaseEvent(self, mouseEvent):
        """ On mouse release, an item might be repositioned so need to redraw all the
        link_items """

        super(GraphicsScene, self).mouseReleaseEvent(mouseEvent)
