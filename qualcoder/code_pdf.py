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
"""
from binascii import b2a_hex
from copy import copy, deepcopy
import datetime
import logging
from operator import itemgetter
import os
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams, LTTextBox, LTTextLine, LTTextBoxHorizontal, LTImage, LTFigure, LTCurve, LTLine, \
    LTRect
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.pdfpage import PDFPage
from pdfminer.psparser import PSLiteral  # sort of using for color conversion
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument  # for PDF meta information
# Using this for determining colourspace, e.g. colorspace': [<PDFObjRef:852>]
from pdfminer.pdftypes import PDFObjRef, resolve1
from random import randint
import re
import sqlite3
from statistics import median
import sys
import traceback
from typing import Iterable, Any
import webbrowser

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor

from .add_item_name import DialogAddItemName
from .code_in_all_files import DialogCodeInAllFiles
from .color_selector import DialogColorSelect
from .color_selector import colors, TextColor
from .confirm_delete import DialogConfirmDelete
from .helpers import Message, DialogGetStartAndEndMarks, ExportDirectoryPathDialog
from .GUI.base64_helper import *
from .GUI.ui_dialog_code_pdf import Ui_Dialog_code_pdf
from .memo import DialogMemo
from .report_attributes import DialogSelectAttributeParameters
from .reports import DialogReportCoderComparisons, DialogReportCodeFrequencies  # for isinstance()
from .report_codes import DialogReportCodes
from .report_code_summary import DialogReportCodeSummary  # for isinstance()
from .select_items import DialogSelectItems  # for isinstance()

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text_ = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text_)
    logger.error(_("Uncaught exception:") + "\n" + text_)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 12pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(text_)
    mb.exec()


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
    filenames = []
    file_ = None  # contains filename and file id returned from SelectItems
    code_text = []
    annotations = []
    undo_deleted_codes = []  # undo last deleted code(s), multiple may have been deleted at th same time, so a list

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
        sys.excepthook = exception_handler
        self.parent_textEdit = parent_textedit
        self.search_indices = []
        self.search_index = 0
        self.codes, self.categories = self.app.get_codes_categories()
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
        self.text_items = []
        self.selected_text_boxes = ""

        # Set up ui
        self.ui = Ui_Dialog_code_pdf()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        tree_font = 'font: ' + str(self.app.settings['treefontsize']) + 'pt '
        tree_font += '"' + self.app.settings['font'] + '";'
        self.ui.treeWidget.setStyleSheet(tree_font)
        doc_font = 'font: ' + str(self.app.settings['docfontsize']) + 'pt '
        doc_font += '"' + self.app.settings['font'] + '";'
        self.ui.textEdit.setStyleSheet(doc_font)
        self.ui.label_coder.setText("Coder: " + self.app.settings['codername'])
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

        # Icons marked icon_24 icons are 24x24 px but need a button of 28
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(playback_next_icon_24), "png")
        self.ui.pushButton_latest.setIcon(QtGui.QIcon(pm))
        #self.ui.pushButton_latest.pressed.connect(self.go_to_latest_coded_file)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(playback_play_icon_24), "png")
        self.ui.pushButton_next_file.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_next_file.pressed.connect(self.go_to_next_file)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(eye_doc_icon), "png")
        self.ui.pushButton_bookmark_go.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_bookmark_go.pressed.connect(self.view_original_file)
        self.ui.pushButton_bookmark_go.setToolTip(_("View original file"))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(notepad_2_icon_24), "png")
        self.ui.pushButton_document_memo.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_document_memo.pressed.connect(self.file_memo)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_right_icon_24), "png")
        self.ui.pushButton_show_codings_next.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_show_codings_next.pressed.connect(self.show_selected_code_in_text_next)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_left_icon_24), "png")
        self.ui.pushButton_show_codings_prev.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_show_codings_prev.pressed.connect(self.show_selected_code_in_text_previous)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(a2x2_grid_icon_24), "png")
        self.ui.pushButton_show_all_codings.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_show_all_codings.pressed.connect(self.show_all_codes_in_text)
        self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
        self.ui.lineEdit_search.setEnabled(False)
        self.ui.checkBox_search_all_files.stateChanged.connect(self.search_for_text)
        self.ui.checkBox_search_all_files.setEnabled(False)
        self.ui.checkBox_search_case.stateChanged.connect(self.search_for_text)
        self.ui.checkBox_search_case.setEnabled(False)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(question_icon), "png")
        self.ui.label_search_regex.setPixmap(QtGui.QPixmap(pm).scaled(22, 22))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(text_letter_t_icon), "png")
        self.ui.label_search_case_sensitive.setPixmap(QtGui.QPixmap(pm).scaled(22, 22))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(clipboard_copy_icon), "png")
        self.ui.label_search_all_files.setPixmap(QtGui.QPixmap(pm).scaled(22, 22))
        self.ui.label_pages.setPixmap(QtGui.QPixmap(pm).scaled(22, 22))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(font_size_icon), "png")
        self.ui.label_font_size.setPixmap(QtGui.QPixmap(pm).scaled(22, 22))
        self.ui.spinBox_font_adjuster.valueChanged.connect(self.pdf_text_font_size_adjuster)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(playback_back_icon), "png")
        self.ui.pushButton_previous.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_previous.setEnabled(False)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(playback_play_icon), "png")
        self.ui.pushButton_next.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_next.setEnabled(False)
        self.ui.pushButton_next.pressed.connect(self.move_to_next_search_text)
        self.ui.pushButton_previous.pressed.connect(self.move_to_previous_search_text)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(question_icon), "png")
        self.ui.pushButton_help.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_help.pressed.connect(self.help)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(tag_icon32), "png")
        self.ui.pushButton_file_attributes.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_file_attributes.pressed.connect(self.get_files_from_attributes)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(star_icon32), "png")
        self.ui.pushButton_important.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_important.pressed.connect(self.show_important_coded)
        self.ui.treeWidget.setDragEnabled(True)
        self.ui.treeWidget.setAcceptDrops(True)
        self.ui.treeWidget.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.ui.treeWidget.viewport().installEventFilter(self)
        self.ui.treeWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.treeWidget.customContextMenuRequested.connect(self.tree_menu)
        self.ui.treeWidget.itemClicked.connect(self.fill_code_label_undo_show_selected_code)
        self.ui.splitter.setSizes([150, 400])
        '''try:
            s0 = int(self.app.settings['dialogcodetext_splitter0'])
            s1 = int(self.app.settings['dialogcodetext_splitter1'])
            if s0 > 5 and s1 > 5:
                self.ui.splitter.setSizes([s0, s1])
            v0 = int(self.app.settings['dialogcodetext_splitter_v0'])
            v1 = int(self.app.settings['dialogcodetext_splitter_v1'])
            if v0 > 5 and v1 > 5:
                # 30s are for the groupboxes containing buttons
                self.ui.leftsplitter.setSizes([v1, 30, v0, 30])
        except KeyError:
            pass
        self.ui.splitter.splitterMoved.connect(self.update_sizes)
        self.ui.leftsplitter.splitterMoved.connect(self.update_sizes)'''

        # Graphics view items setup
        self.ui.graphicsView.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
        # Need this otherwise small images are centred on screen, and affect context menu position points
        self.ui.graphicsView.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.ui.graphicsView.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        #self.ui.graphicsView.customContextMenuRequested.connect(self.graphicsview_menu)
        self.ui.graphicsView.viewport().installEventFilter(self)

        self.ui.checkBox_curve.stateChanged.connect(self.update_page)
        self.ui.checkBox_image.stateChanged.connect(self.update_page)
        self.ui.checkBox_rect.stateChanged.connect(self.update_page)
        self.ui.checkBox_text.stateChanged.connect(self.update_page)
        self.ui.checkBox_line.stateChanged.connect(self.update_page)
        self.ui.checkBox_black_text.stateChanged.connect(self.update_page)
        self.ui.radioButton_objects.clicked.connect(self.update_page)
        self.ui.radioButton_text.clicked.connect(self.update_page)
        self.ui.spinBox.setEnabled(False)
        self.ui.spinBox.setMinimum(1)
        self.ui.spinBox.valueChanged.connect(self.spin_page_changed)

        self.get_files()
        self.fill_tree()

    def pdf_text_font_size_adjuster(self):
        """ Spinbox font size adjustment from 0 to -10pt. """

        self.update_page()

    def spin_page_changed(self):
        pass
        if self.pages:
            self.page_num = self.ui.spinBox.value() - 1
            self.show_page(self.page_num)

    def update_page(self):
        """ Show and hide PDF elements on page and redraw. """

        if self.pages:
            self.show_page(self.page_num)

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
            tt += "\n" + _("Codings: ") + str(res[0])
            tt += "\n" + _("From: ") + str(f['start']) + _(" to ") + str(f['end'])
            item = QtWidgets.QListWidgetItem(f['name'])
            if f['memo'] != "":
                tt += "\nMemo: " + f['memo']
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
        tt += "\n" + _("Codings: ") + str(res[0])
        tt += "\n" + _("From: ") + str(f['start']) + _(" to ") + str(f['end'])
        if self.file_['memo'] != "":
            tt += "\nMemo: " + self.file_['memo']
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
            pm = QtGui.QPixmap()
            pm.loadFromData(QtCore.QByteArray.fromBase64(tag_icon32), "png")
            self.ui.pushButton_file_attributes.setIcon(QtGui.QIcon(pm))
            self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
            if self.attributes:
                pm = QtGui.QPixmap()
                pm.loadFromData(QtCore.QByteArray.fromBase64(tag_iconyellow32), "png")
                self.ui.pushButton_file_attributes.setIcon(QtGui.QIcon(pm))
            return
        self.attributes = ui.parameters
        if len(self.attributes) == 1:  # Boolean parameter, no attributes
            pm = QtGui.QPixmap()
            pm.loadFromData(QtCore.QByteArray.fromBase64(tag_icon32), "png")
            self.ui.pushButton_file_attributes.setIcon(QtGui.QIcon(pm))
            self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
            self.get_files()
            return
        if not ui.result_file_ids:
            Message(self.app, _("Nothing found") + " " * 20, _("No matching files found")).exec()
            pm = QtGui.QPixmap()
            pm.loadFromData(QtCore.QByteArray.fromBase64(tag_icon32), "png")
            self.ui.pushButton_file_attributes.setIcon(QtGui.QIcon(pm))
            self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
            return
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(tag_iconyellow32), "png")
        self.ui.pushButton_file_attributes.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_file_attributes.setToolTip(ui.tooltip_msg)
        self.get_files(ui.result_file_ids)

    '''def update_sizes(self):
        """ Called by changed splitter size """

        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogcodetext_splitter0'] = sizes[0]
        self.app.settings['dialogcodetext_splitter1'] = sizes[1]
        v_sizes = self.ui.leftsplitter.sizes()
        self.app.settings['dialogcodetext_splitter_v0'] = v_sizes[0]
        self.app.settings['dialogcodetext_splitter_v1'] = v_sizes[1]'''

    def fill_code_label_undo_show_selected_code(self):
        """ Fill code label with currently selected item's code name and colour.
         Also, if text is highlighted, assign the text to this code.

         Called by: treewidgetitem_clicked """

        current = self.ui.treeWidget.currentItem()
        # Extra to fill right-hand side splitter details
        self.show_code_rule()

        if current.text(1)[0:3] == 'cat':
            self.ui.label_code.hide()
            self.ui.label_code.setToolTip("")
            return
        self.ui.label_code.show()
        # Set background colour of label to code color, and store current code for underlining
        for c in self.codes:
            if current.text(0) == c['name']:
                fg_color = TextColor(c['color']).recommendation
                style = "QLabel {background-color :" + c['color'] + "; color : " + fg_color + ";}"
                self.ui.label_code.setStyleSheet(style)
                self.ui.label_code.setAutoFillBackground(True)
                tt = c['name'] + "\n"
                if c['memo'] != "":
                    tt += _("Memo: ") + c['memo']
                self.ui.label_code.setToolTip(tt)
                break
        selected_text = self.ui.textEdit.textCursor().selectedText()
        if len(selected_text) > 0:
            self.mark()
        # When a code is selected undo the show selected code features
        self.highlight()
        # Reload button icons as they disappear on Windows
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_left_icon_24), "png")
        self.ui.pushButton_show_codings_prev.setIcon(QtGui.QIcon(pm))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_right_icon_24), "png")
        self.ui.pushButton_show_codings_next.setIcon(QtGui.QIcon(pm))

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
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                top_item.setToolTip(2, c['memo'])
                top_item.setToolTip(0, '')
                if len(c['name']) > 52:
                    top_item.setText(0, c['name'][:25] + '..' + c['name'][-25:])
                    top_item.setToolTip(0, c['name'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                if 'catid:' + str(c['catid']) in non_expanded:
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
                    if item.text(1) == 'catid:' + str(c['supercatid']):
                        memo = ""
                        if c['memo'] != "":
                            memo = _("Memo")
                        child = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                        child.setToolTip(2, c['memo'])
                        child.setToolTip(0, '')
                        if len(c['name']) > 52:
                            child.setText(0, c['name'][:25] + '..' + c['name'][-25:])
                            child.setToolTip(0, c['name'])
                        item.addChild(child)
                        if 'catid:' + str(c['catid']) in non_expanded:
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
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                top_item.setToolTip(2, c['memo'])
                top_item.setToolTip(0, c['name'])
                if len(c['name']) > 52:
                    top_item.setText(0, c['name'][:25] + '..' + c['name'][-25:])
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
                if item.text(1) == 'catid:' + str(c['catid']):
                    memo = ""
                    if c['memo'] != "":
                        memo = _("Memo")
                    child = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                    child.setToolTip(2, c['memo'])
                    child.setToolTip(0, c['name'])
                    if len(c['name']) > 52:
                        child.setText(0, c['name'][:25] + '..' + c['name'][-25:])
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
                    msg = "Fill code counts error\n" + str(e) + "\n"
                    msg += sql + "\n"
                    msg += "cid " + str(cid) + "\n"
                    msg += "self.file_['id'] " + str(self.file_['id']) + "\n"
                    logger.debug(msg)
                    item.setText(3, "")
            it += 1
            item = it.value()
            count += 1

    def get_codes_and_categories(self):
        """ Called from init, delete category/code.
        Also called on other coding dialogs in the dialog_list. """

        self.codes, self.categories = self.app.get_codes_categories()
        '''for c in self.codes:
            c['name'] = c['name']  # Why did I do this ?'''

    # RHS splitter details for code rule, current journal, project memo
    def show_code_rule(self):
        """ Show current journal text in right-hand side splitter pane. """

        pass
        '''self.ui.textEdit.setPlainText("")
        selected = self.ui.treeWidget.currentItem()
        if selected is None:
            return
        self.project_memo = False
        self.journal_entry = False
        self.code_rule = True
        self.ui.label_info.setText(selected.text(0))
        txt = ""
        if selected.text(1)[0:3] == 'cat':
            for c in self.categories:
                if c['catid'] == int(selected.text(1)[6:]):
                    txt += c['memo']
                    break
        else:  # Code is selected
            for c in self.codes:
                if c['cid'] == int(selected.text(1)[4:]):
                    txt += c['memo']
                    break
            self.ui.textEdit_info.show()
            # Get coded examples
            txt += "\n\n" + _("Examples:") + "\n"
            cur = self.app.conn.cursor()
            cur.execute("select seltext from code_text where length(seltext) > 0 and cid=? order by random() limit 3",
                        [int(selected.text(1)[4:])])
            res = cur.fetchall()
            for i, r in enumerate(res):
                txt += str(i + 1) + ": " + r[0] + "\n"
        self.ui.textEdit_info.setReadOnly(True)
        self.ui.textEdit_info.blockSignals(True)
        self.ui.textEdit_info.setText(txt)'''

    def show_current_journal(self):
        """ Show current journal text in right-hand side splitter pane. """

        pass
        '''journals = self.app.get_journal_texts()
        if not journals:
            self.journal_entry = False
            return
        self.project_memo = False
        self.journal_entry = journals[0]
        self.code_rule = False
        self.ui.label_info.setText(self.journal_entry['name'])
        self.ui.textEdit_info.setReadOnly(False)
        self.ui.textEdit_info.blockSignals(True)
        self.ui.textEdit_info.setText(self.journal_entry['jentry'])
        self.ui.textEdit_info.blockSignals(False)'''

    def rhs_splitter_text_changed(self):
        """ Database is updated as text is changed in textEdit_info.
        Text is updated for the current journal, or the overall project memo.
        """

        pass
        '''if self.code_rule:
            return
        cur = self.app.conn.cursor()
        txt = self.ui.textEdit.toPlainText()
        if self.journal_entry is not False:
            now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("update journal set jentry=?, date=?, owner=? where jid=?",
                        [txt, now_date, self.app.settings['codername'], self.journal_entry['jid']])
        if self.project_memo is not False:
            cur.execute("update project set memo=?", [txt])
        self.app.conn.commit()
        self.app.delete_backup = False'''

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
        if self.ui.checkBox_search_all_files.isChecked():
            """ Search for this text across all files. """
            for filedata in self.app.get_file_texts():
                try:
                    text_ = filedata['fulltext']
                    for match in pattern.finditer(text_):
                        self.search_indices.append((filedata, match.start(), len(match.group(0))))
                except re.error:
                    logger.exception('Failed searching text %s for %s', filedata['name'], self.search_term)
        else:
            try:
                if self.text:
                    for match in pattern.finditer(self.text):
                        # Get result as first dictionary item
                        source_name = self.app.get_file_texts([self.file_['id'], ])[0]
                        self.search_indices.append((source_name, match.start(), len(match.group(0))))
            except re.error:
                logger.exception('Failed searching current file for %s', self.search_term)
        if len(self.search_indices) > 0:
            self.ui.pushButton_next.setEnabled(True)
            self.ui.pushButton_previous.setEnabled(True)
        self.ui.label_search_totals.setText("0 / " + str(len(self.search_indices)))

    def move_to_previous_search_text(self):
        """ Push button pressed to move to previous search text position. """

        if self.file_ is None or self.search_indices == []:
            return
        self.search_index -= 1
        if self.search_index < 0:
            self.search_index = len(self.search_indices) - 1
        cursor = self.ui.textEdit.textCursor()
        prev_result = self.search_indices[self.search_index]
        # prev_result is a tuple containing a dictionary of
        # (name, id, fullltext, memo, owner, date) and char position and search string length
        if self.file_ is None or self.file_['id'] != prev_result[0]['id']:
            self.load_file(prev_result[0])
            self.ui.lineEdit_search.setText(self.search_term)
        cursor.setPosition(prev_result[1])
        cursor.setPosition(cursor.position() + prev_result[2], QtGui.QTextCursor.MoveMode.KeepAnchor)
        self.ui.textEdit.setTextCursor(cursor)
        self.ui.label_search_totals.setText(str(self.search_index + 1) + " / " + str(len(self.search_indices)))

    def move_to_next_search_text(self):
        """ Push button pressed to move to next search text position. """

        if self.file_ is None or self.search_indices == []:
            return
        self.search_index += 1
        if self.search_index == len(self.search_indices):
            self.search_index = 0
        cursor = self.ui.textEdit.textCursor()
        next_result = self.search_indices[self.search_index]
        # next_result is a tuple containing a dictionary of
        # (name, id, fullltext, memo, owner, date) and char position and search string length
        if self.file_ is None or self.file_['id'] != next_result[0]['id']:
            self.load_file(next_result[0])
            self.ui.lineEdit_search.setText(self.search_term)
        cursor.setPosition(cursor.position() + next_result[2])
        self.ui.textEdit.setTextCursor(cursor)

        # Highlight selected text
        cursor.setPosition(next_result[1])
        cursor.setPosition(cursor.position() + next_result[2], QtGui.QTextCursor.MoveMode.KeepAnchor)
        self.ui.textEdit.setTextCursor(cursor)
        self.ui.label_search_totals.setText(str(self.search_index + 1) + " / " + str(len(self.search_indices)))

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

        # TODO ?
        return
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
        #action_start_pos = None
        #action_end_pos = None
        action_change_pos = None
        action_unmark = None
        action_new_code = None
        action_new_invivo_code = None

        # Can have multiple coded text at this position
        for item in self.code_text:
            if cursor.position() + self.file_['start'] >= item['pos0'] and cursor.position() <= item['pos1']:
                action_unmark = QtGui.QAction(_("Unmark (U)"))
                action_code_memo = QtGui.QAction(_("Memo coded text (M)"))
                #action_start_pos = QtGui.QAction(_("Change start position (SHIFT LEFT/ALT RIGHT)"))
                #action_end_pos = QtGui.QAction(_("Change end position (SHIFT RIGHT/ALT LEFT)"))
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
        '''if action_start_pos:
            menu.addAction(action_start_pos)
        if action_end_pos:
            menu.addAction(action_end_pos)'''
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
        action_set_bookmark = menu.addAction(_("Set bookmark (B)"))
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
            self.set_important(cursor.position())
            return
        if action == action_not_important:
            self.set_important(cursor.position(), False)
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
        '''if action == action_start_pos:
            self.change_code_pos(cursor.position(), "start")
            return
        if action == action_end_pos:
            self.change_code_pos(cursor.position(), "end")
            return'''
        if action == action_set_bookmark:
            cur = self.app.conn.cursor()
            bookmark_pos = cursor.position() + self.file_['start']
            cur.execute("update project set bookmarkfile=?, bookmarkpos=?", [self.file_['id'], bookmark_pos])
            self.app.conn.commit()
            return
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

    def set_important(self, position, important=True):
        """ Set or unset importance to coded text.
        Importance is denoted using '1'
        params:
            position: textEdit character cursor position
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
                    ((not important and item['important'] == 1) or (important and item['important'] != 1)):
                coded_text_list.append(item)
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

    def coded_text_memo(self, position=None):
        """ Add or edit a memo for this coded text. """

        if position is None:
            # Called via button
            position = self.ui.textEdit.textCursor().position()
        if self.file_ is None:
            return
        coded_text_list = []
        for item in self.code_text:
            if item['pos0'] <= position + self.file_['start'] <= item['pos1'] and \
                    item['owner'] == self.app.settings['codername']:
                coded_text_list.append(item)
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
        msg = text_item['name'] + " [" + str(text_item['pos0']) + "-" + str(text_item['pos1']) + "]"
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

    def change_code_pos_message(self):  #, location, start_or_end):
        """  Called via textedit_menu. """

        msg = _("Change start position (extend SHIFT LEFT/ shrink ALT RIGHT)\nChange end position (extend SHIFT RIGHT/ shrink ALT LEFT)")
        Message(self.app, _("Use key presses") + " " * 20, msg).exec()

    def shift_code_positions(self, position):
        """ After a text file is edited - text added or deleted, code positions may be inaccurate.
         enter a positive or negative integer to shift code positions for all codes after a click position in the
         document.
         Activated by ^ At key press"""

        if self.file_ is None:
            return
        code_list = []
        for item in self.code_text:
            if item['pos0'] > position + self.file_['start']:
                code_list.append(item)
                #print(item['pos0'], ">", position + self.file_['start'])
        if not code_list:
            return
        int_dialog = QtWidgets.QInputDialog()
        int_dialog.setMinimumSize(60, 150)
        # Remove context flag does not work here
        int_dialog.setWindowFlags(int_dialog.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        msg = _("Shift codings after clicked position")
        int_dialog.setWhatsThis(msg)
        int_dialog.setToolTip(msg)
        msg2 = _("Shift code positions for all codes after you have clicked on a position in the text.\n"
                 "Back up the project before running this action.\n"
                 "This function will help if you have edited the coded text and the codes are out of position.\n"
                 "Positive numbers (moves right) or negative numbers (moves left) (-500 to 500)\n"
                 "Clicked character position: ") + str(position)
        delta_shift, ok = int_dialog.getInt(self, msg,msg2 , 0, -500, 500, 1)
        if not ok:
            return
        if delta_shift == 0:
            return
        int_dialog.done(1)  # Need this, as reactivated when called again with same int value.
        cur = self.app.conn.cursor()
        length_sql = "select length(fulltext) from source where id=?"
        cur.execute(length_sql, [self.file_['id']])
        fulltext_length = cur.fetchone()[0]
        text_sql = "select substr(fulltext,?,?), length(fulltext) from source where id=?"
        # Update code_text rows in database
        for coded in code_list:
            #print(coded['seltext'], coded['pos0'], coded['pos1'])
            new_pos0 = coded['pos0'] + delta_shift
            new_pos1 = coded['pos1'] + delta_shift
            # Get seltext and update if coded pos0 and pos1 are within bounds
            if new_pos0 > -1 and new_pos1 < fulltext_length:
                cur.execute(text_sql, [new_pos0, new_pos1 - new_pos0, self.file_['id']])
                seltext = cur.fetchone()[0]
                #print("len", fulltext_length, seltext)
                sql = "update code_text set pos0=?, pos1=?, seltext=? where ctid=?"
                cur.execute(sql, [new_pos0, new_pos1, seltext, coded['ctid']])
                self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

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

        action = menu.exec(self.ui.treeWidget.mapToGlobal(position))
        if action is not None:
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
            catid : Integer cateogry identfier
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
        for code in self.codes:
            if code['catid'] == catid:
                cur.execute("update code_name set catid=? where catid=?", [category['catid'], catid])
        cur.execute("delete from code_cat where catid=?", [catid])
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        for cat in self.categories:
            if cat['supercatid'] == catid:
                cur.execute("update code_cat set supercatid=? where supercatid=?", [category['catid'], catid])
        self.app.conn.commit()
        # Clear any orphan supercatids
        sql = "select supercatid from code_cat where supercatid not in (select catid from code_cat)"
        cur.execute(sql)
        orphans = cur.fetchall()
        sql = "update code_cat set supercatid=Null where supercatid=?"
        for orphan in orphans:
            cur.execute(sql, [orphan[0]])
        self.app.conn.commit()
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

    '''def show_memos(self):
        """ Show all memos for coded text in dialog. """

        if self.file_ is None:
            return
        text_ = ""
        cur = self.app.conn.cursor()
        sql = "select code_name.name, pos0,pos1, seltext, code_text.memo "
        sql += "from code_text join code_name on code_text.cid = code_name.cid "
        sql += "where length(code_text.memo)>0 and fid=? and code_text.owner=? order by pos0"
        cur.execute(sql, [self.file_['id'], self.app.settings['codername']])
        res = cur.fetchall()
        if not res:
            return
        for r in res:
            text_ += '[' + str(r[1]) + '-' + str(r[2]) + '] ' + _("Code: ") + r[0] + "\n"
            text_ += _("Text: ") + r[3] + "\n"
            text_ += _("Memo: ") + r[4] + "\n\n"
        ui = DialogMemo(self.app, _("Memos for file: ") + self.file_['name'], text_)
        ui.ui.pushButton_clear.hide()
        ui.ui.textEdit.setReadOnly(True)
        ui.exec()'''

    '''def show_annotations(self):
        """ Show all annotations for text in dialog. """

        if self.file_ is None:
            return
        text_ = ""
        cur = self.app.conn.cursor()
        sql = "select substr(source.fulltext,pos0+1 ,pos1-pos0), pos0, pos1, annotation.memo "
        sql += "from annotation join source on annotation.fid = source.id "
        sql += "where fid=? and annotation.owner=? order by pos0"
        cur.execute(sql, [self.file_['id'], self.app.settings['codername']])
        res = cur.fetchall()
        if not res:
            return
        for r in res:
            text_ += '[' + str(r[1]) + '-' + str(r[2]) + '] ' + "\n"
            text_ += _("Text: ") + r[0] + "\n"
            text_ += _("Annotation: ") + r[3] + "\n\n"
        ui = DialogMemo(self.app, _("Annotations for file: ") + self.file_['name'], text_)
        ui.ui.pushButton_clear.hide()
        ui.ui.textEdit.setReadOnly(True)
        ui.exec()'''

    def show_important_coded(self):
        """ Show codes flagged as important. """

        self.important = not self.important
        pm = QtGui.QPixmap()
        if self.important:
            pm.loadFromData(QtCore.QByteArray.fromBase64(star_icon_yellow32), "png")
            self.ui.pushButton_important.setToolTip(_("Showing important codings"))
        else:
            pm.loadFromData(QtCore.QByteArray.fromBase64(star_icon32), "png")
            self.ui.pushButton_important.setToolTip(_("Show codings flagged important"))
        self.ui.pushButton_important.setIcon(QtGui.QIcon(pm))
        self.get_coded_text_update_eventfilter_tooltips()

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

    def keyPressEvent(self, event):
        """
        Ctrl Z Undo last unmarking
        Ctrl F jump to search box
        A annotate - for current selection
        Q Quick Mark with code - for current selection
        B Create bookmark - at clicked position
        H Hide / Unhide top groupbox
        I Tag important
        M memo code - at clicked position
        O Shortcut to cycle through overlapping codes - at clicked position
        S search text - may include current selection
        R opens a context menu for recently used codes for marking text
        U Unmark at selected location
        V assign 'in vivo' code to selected text
        Ctrl 0 to Ctrl 9 - button presses
        # Display Clicked character position
        ^ At key. Shift code positions. May be needed after the text is edited
            (added or deleted) to shift subsequent codings.
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
            if key == QtCore.Qt.Key.Key_3:
                self.go_to_bookmark()
                return
            if key == QtCore.Qt.Key.Key_4:
                self.file_memo(self.file_)
                return
            if key == QtCore.Qt.Key.Key_5:
                self.get_files_from_attributes()
                return
            if key == QtCore.Qt.Key.Key_6:
                self.show_selected_code_in_text_previous()
                return
            if key == QtCore.Qt.Key.Key_7:
                self.show_selected_code_in_text_next()
                return
            if key == QtCore.Qt.Key.Key_8:
                self.show_all_codes_in_text()
                return
            if key == QtCore.Qt.Key.Key_9:
                self.show_important_coded()
                return
            if key == QtCore.Qt.Key.Key_0:
                self.help()
                return
        if self.ui.graphicsView.hasFocus():
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

        if not self.ui.textEdit.hasFocus():
            return

        key = event.key()
        # mod = QtGui.QGuiApplication.keyboardModifiers()
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
        if key == QtCore.Qt.Key.Key_Dollar:
            self.shift_code_positions(self.ui.textEdit.textCursor().position() + self.file_['start'])
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
        # Important  for coded text
        if key == QtCore.Qt.Key.Key_I:
            self.set_important(cursor_pos)
            return
        # Memo for current code
        if key == QtCore.Qt.Key.Key_M:
            self.coded_text_memo(cursor_pos)
            return
        # Overlapping codes cycle
        now = datetime.datetime.now()
        overlap_diff = now - self.overlap_timer
        if key == QtCore.Qt.Key.Key_O and len(self.overlaps_at_pos) > 0 and overlap_diff.microseconds > 150000:
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

    def export_option_selected(self):
        """ ComboBox export option selected. """

        #TODO
        return
        '''text_ = self.ui.comboBox_export.currentText()
        if text_ == "":
            return
        if text_ == "html":
            self.export_html_file()
        if text_ == "odt":
            self.export_odt_file()
        self.ui.comboBox_export.setCurrentIndex(0)'''

    '''def export_odt_file(self):
        """ Export text to open document format with .odt ending.
        QTextWriter supports plaintext, ODF and HTML.
        Cannot export tooltips.
        Called by export_option_selected
        """

        if len(self.ui.textEdit.document().toPlainText()) == 0:
            return
        filename = self.file_['name'] + ".odt"
        exp_dir = ExportDirectoryPathDialog(self.app, filename)
        filepath = exp_dir.filepath
        if filepath is None:
            return
        tw = QtGui.QTextDocumentWriter()
        tw.setFileName(filepath)
        tw.setFormat(b'ODF')  # byte array needed for Windows 10
        tw.write(self.ui.textEdit.document())
        msg = _("Coded text file exported: ") + filepath
        self.parent_textEdit.append(msg)
        Message(self.app, _('Coded text file exported'), msg, "information").exec()

    def export_html_file(self):
        """ Export text to html file.
        Called by export_option_selected.
        TODO export tooltips. """

        if len(self.ui.textEdit.document().toPlainText()) == 0:
            return
        html_filename = self.file_['name'] + ".html"
        exp_dir = ExportDirectoryPathDialog(self.app, html_filename)
        filepath = exp_dir.filepath
        if filepath is None:
            return
        tw = QtGui.QTextDocumentWriter()
        tw.setFileName(filepath)
        tw.setFormat(b'HTML')  # byte array needed for Windows 10
        tw.write(self.ui.textEdit.document())
        msg = _("Coded text file exported to: ") + filepath
        self.parent_textEdit.append(msg)
        Message(self.app, _('Coded text file exported'), msg, "information").exec()'''

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
            # If a show selected code was active, then clicking on a code in code tree, shows all codes and all tooltips
            if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                self.show_all_codes_in_text()
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
            if diff.microseconds < 100000:
                return False

            cursor_pos = self.ui.textEdit.textCursor().position()
            codes_here = []
            for item in self.code_text:
                if item['pos0'] <= cursor_pos + self.file_['start'] <= item['pos1'] and \
                        item['owner'] == self.app.settings['codername']:
                    codes_here.append(item)
            if len(codes_here) == 1:
                # Key event can be too sensitive, adjusted  for 150 millisecond gap
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

    def show_selected_code_in_text_next(self):
        """ Highlight only the selected code in the text. Move to next instance in text
        from the current textEdit cursor position.
        Adjust for a portion of text loaded.
        Called by: pushButton_show_codings_next
        """

        if self.file_ is None:
            return
        item = self.ui.treeWidget.currentItem()
        if item is None or item.text(1)[0:3] == 'cat':
            return
        cid = int(item.text(1)[4:])
        # Index list has to be dynamic, as a new code_text item could be created before this method is called again
        # Develop indices and tooltip coded text list
        indexes = []
        tt_code_text = []
        for ct in self.code_text:
            if ct['cid'] == cid:
                indexes.append(ct)
                tt_code_text.append(ct)
        indexes = sorted(indexes, key=itemgetter('pos0'))
        cursor = self.ui.textEdit.textCursor()
        cur_pos = cursor.position()
        end_pos = 0
        found_larger = False
        msg = "/" + str(len(indexes))
        for i, index in enumerate(indexes):
            if index['pos0'] - self.file_['start'] > cur_pos:
                cur_pos = index['pos0'] - self.file_['start']
                end_pos = index['pos1'] - self.file_['start']
                found_larger = True
                msg = str(i + 1) + msg
                break
        if not found_larger and indexes == []:
            return
        # Loop around to the highest index
        if not found_larger and indexes != []:
            cur_pos = indexes[0]['pos0'] - self.file_['start']
            end_pos = indexes[0]['pos1'] - self.file_['start']
            msg = "1" + msg
        if not found_larger:
            cursor = self.ui.textEdit.textCursor()
            cursor.setPosition(0)
            self.ui.textEdit.setTextCursor(cursor)
        self.unlight()
        msg = " " + _("Code:") + " " + msg
        # Highlight the code in the text
        color = ""
        for c in self.codes:
            if c['cid'] == cid:
                color = c['color']
        cursor.setPosition(cur_pos)
        self.ui.textEdit.setTextCursor(cursor)
        cursor.setPosition(cur_pos, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(end_pos, QtGui.QTextCursor.MoveMode.KeepAnchor)
        brush = QBrush(QColor(color))
        fmt = QtGui.QTextCharFormat()
        fmt.setBackground(brush)
        foreground_color = TextColor(color).recommendation
        fmt.setForeground(QBrush(QColor(foreground_color)))
        cursor.mergeCharFormat(fmt)
        # Update tooltips to show only this code
        self.eventFilterTT.set_codes_and_annotations(self.app, tt_code_text, self.codes, self.annotations,
                                                     self.file_)
        # Need to reload arrow icons as they dissapear on Windows
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(a2x2_color_grid_icon_24), "png")
        self.ui.pushButton_show_all_codings.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_show_codings_prev.setStyleSheet("background-color : " + color + ";color:" + foreground_color)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_left_icon_24), "png")
        self.ui.pushButton_show_codings_prev.setIcon(QtGui.QIcon(pm))
        tt = _("Show previous coding of selected code") + msg
        self.ui.pushButton_show_codings_prev.setToolTip(tt)
        self.ui.pushButton_show_codings_next.setStyleSheet("background-color : " + color + ";color:" + foreground_color)
        tt = _("Show next coding of selected code") + msg
        self.ui.pushButton_show_codings_next.setToolTip(tt)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_right_icon_24), "png")
        self.ui.pushButton_show_codings_next.setIcon(QtGui.QIcon(pm))

    def show_selected_code_in_text_previous(self):
        """ Highlight only the selected code in the text. Move to previous instance in text from
        the current textEdit cursor position.
        Called by: pushButton_show_codings_previous
        """

        if self.file_ is None:
            return
        item = self.ui.treeWidget.currentItem()
        if item is None or item.text(1)[0:3] == 'cat':
            return
        cid = int(item.text(1)[4:])
        # Index list has to be dynamic, as a new code_text item could be created before this method is called again
        # Develop indexes and tooltip coded text list
        indexes = []
        tt_code_text = []
        for ct in self.code_text:
            if ct['cid'] == cid:
                indexes.append(ct)
                tt_code_text.append(ct)
        indexes = sorted(indexes, key=itemgetter('pos0'), reverse=True)
        cursor = self.ui.textEdit.textCursor()
        cur_pos = cursor.position()
        end_pos = 0
        found_smaller = False
        msg = "/" + str(len(indexes))
        for i, index in enumerate(indexes):
            if index['pos0'] - self.file_['start'] < cur_pos - 1:
                cur_pos = index['pos0'] - self.file_['start']
                end_pos = index['pos1'] - self.file_['start']
                found_smaller = True
                msg = str(len(indexes) - i) + msg
                break
        if not found_smaller and indexes == []:
            return
        # Loop around to the highest index
        if not found_smaller and indexes != []:
            cur_pos = indexes[0]['pos0'] - self.file_['start']
            end_pos = indexes[0]['pos1'] - self.file_['start']
            msg = str(len(indexes)) + msg
        msg += " " + _("Code:") + " " + msg
        self.unlight()
        # Highlight the code in the text
        color = ""
        for c in self.codes:
            if c['cid'] == cid:
                color = c['color']
        cursor.setPosition(cur_pos)
        self.ui.textEdit.setTextCursor(cursor)
        cursor.setPosition(cur_pos, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(end_pos, QtGui.QTextCursor.MoveMode.KeepAnchor)
        brush = QBrush(QColor(color))
        fmt = QtGui.QTextCharFormat()
        fmt.setBackground(brush)
        foregroundcol = TextColor(color).recommendation
        fmt.setForeground(QBrush(QColor(foregroundcol)))
        cursor.mergeCharFormat(fmt)
        # Update tooltips to show only this code
        self.eventFilterTT.set_codes_and_annotations(self.app, tt_code_text, self.codes, self.annotations,
                                                     self.file_)
        # Need to reload arrow icons as they dissapear on Windows
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(a2x2_color_grid_icon_24), "png")
        self.ui.pushButton_show_all_codings.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_show_codings_prev.setStyleSheet("background-color : " + color + ";color:" + foregroundcol)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_left_icon_24), "png")
        self.ui.pushButton_show_codings_prev.setIcon(QtGui.QIcon(pm))
        tt = _("Show previous coding of selected code") + msg
        self.ui.pushButton_show_codings_prev.setToolTip(tt)
        self.ui.pushButton_show_codings_next.setStyleSheet("background-color : " + color + ";color:" + foregroundcol)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_right_icon_24), "png")
        self.ui.pushButton_show_codings_next.setIcon(QtGui.QIcon(pm))
        tt = _("Show next coding of selected code") + msg
        self.ui.pushButton_show_codings_next.setToolTip(tt)

    def show_all_codes_in_text(self):
        """ Opposes show selected code methods.
        Highlights all the codes in the text. """

        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(a2x2_grid_icon_24), "png")
        self.ui.pushButton_show_all_codings.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_show_codings_prev.setStyleSheet("")
        self.ui.pushButton_show_codings_next.setStyleSheet("")
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_left_icon_24), "png")
        self.ui.pushButton_show_codings_prev.setIcon(QtGui.QIcon(pm))
        tt = _("Show previous coding of selected code")
        self.ui.pushButton_show_codings_prev.setToolTip(tt)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_right_icon_24), "png")
        self.ui.pushButton_show_codings_next.setIcon(QtGui.QIcon(pm))
        tt = _("Show next coding of selected code")
        self.ui.pushButton_show_codings_next.setToolTip(tt)
        self.get_coded_text_update_eventfilter_tooltips()

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
        #self.load_file(self.file_)

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
        try:
            cur.execute("update code_text set cid=? where cid=?", [new_cid, old_cid])
            cur.execute("update code_av set cid=? where cid=?", [new_cid, old_cid])
            cur.execute("update code_image set cid=? where cid=?", [new_cid, old_cid])
            self.app.conn.commit()
        except sqlite3.Error:
            pass
        cur.execute("delete from code_name where cid=?", [old_cid, ])
        self.app.conn.commit()
        self.app.delete_backup = False
        msg = msg.replace("\n", " ")
        self.parent_textEdit.append(msg)
        self.update_dialog_codes_and_categories()
        self.get_coded_text_update_eventfilter_tooltips()

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
            print("in vivo coding. Code already exists")
            return False
        self.update_dialog_codes_and_categories()
        self.get_coded_text_update_eventfilter_tooltips()
        return True

    def update_dialog_codes_and_categories(self):
        """ Update code and category tree here and in DialogReportCodes, ReportCoderComparisons, ReportCodeFrequencies
        Using try except blocks for each instance, as instance may have been deleted. """

        self.get_codes_and_categories()
        self.fill_tree()
        self.unlight()
        self.highlight()
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
            self.parent_textEdit.append(_("Code renamed from: ") + old_name + _(" to: ") + new_name)
            self.update_dialog_codes_and_categories()
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
            self.parent_textEdit.append(_("Category renamed from: ") + old_name + _(" to: ") + new_name)

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
        '''action_next_chars = None
        action_prev_chars = None'''
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
        '''if file_ is not None and file_['characters'] > self.app.settings['codetext_chunksize']:
            action_next_chars = menu.addAction(str(self.app.settings['codetext_chunksize']) + _(" next  characters"))
            if file_['start'] > 0:
                action_prev_chars = menu.addAction(
                    str(self.app.settings['codetext_chunksize']) + _(" previous  characters"))'''
        #action_go_to_bookmark = menu.addAction(_("Go to bookmark"))
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
        '''if action == action_go_to_bookmark:
            self.go_to_bookmark()
        if action == action_next_chars:
            self.next_chars(file_, selected)
        if action == action_prev_chars:
            self.prev_chars(file_, selected)'''
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
            doc_path = self.app.project_path + "/documents/" + self.file_['mediapath'][6:]
            webbrowser.open(doc_path)
            return
        if self.file_['mediapath'][:5] == "docs:":
            doc_path = self.file_['mediapath'][5:]
            print("TO open external ", doc_path)
            webbrowser.open(doc_path)
            return
        logger.error("Cannot open text file in browser " + self.file_['mediapath'])
        print("code_text.view_original_text_file. Cannot open text file in browser " + self.file_['mediapath'])

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
        '''for r in res:
            file_ids.append(r[0])'''
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

    '''def prev_chars(self, file_, selected):
        """ Load previous text chunk of the text file.
        params:
            file_  : selected file, Dictionary
            selected:  list widget item """

        # Already at start
        if file_['start'] == 0:
            return
        file_['end'] = file_['start']
        file_['start'] = file_['start'] - self.app.settings['codetext_chunksize']
        # Forward track to the first line ending for a better start of text chunk
        line_ending = False
        i = 0
        try:
            while file_['start'] + i < file_['end'] and not line_ending:
                if file_['fulltext'][file_['start'] + i] == "\n":
                    line_ending = True
                else:
                    i += 1
        except IndexError:
            pass
        file_['start'] += i
        # Check displayed text not going before start of characters
        if file_['start'] < 0:
            file_['start'] = 0
        # Update tooltip for listItem
        tt = selected.toolTip()
        tt2 = tt.split("From: ")[0]
        tt2 += "\n" + _("From: ") + str(file_['start']) + _(" to ") + str(file_['end'])
        selected.setToolTip(tt2)
        # Load file section into textEdit
        self.load_file(file_)

    def next_chars(self, file_, selected):
        """ Load next text chunk of the text file.
        params:
            file_  : selected file, Dictionary
            selected:  list widget item """

        # First time
        if file_['start'] == 0 and file_['end'] == file_['characters']:
            # Backtrack to the first line ending for a better end of text chunk
            i = self.app.settings['codetext_chunksize']
            line_ending = False
            while i > 0 and not line_ending:
                if file_['fulltext'][i] == "\n":
                    line_ending = True
                else:
                    i -= 1
            if i <= 0:
                file_['end'] = self.app.settings['codetext_chunksize']
            else:
                file_['end'] = i
        else:
            file_['start'] = file_['start'] + self.app.settings['codetext_chunksize']
            # Backtrack from start to next line ending for a better start of text chunk
            line_ending = False
            try:
                while file_['start'] > 0 and not line_ending:
                    if file_['fulltext'][file_['start']] == "\n":
                        line_ending = True
                    else:
                        file_['start'] -= 1
            except IndexError:
                pass
            # Backtrack from end to next line ending for a better end of text chunk
            i = self.app.settings['codetext_chunksize']
            if file_['start'] + i >= file_['characters']:
                i = file_['characters'] - file_['start'] - 1  # To prevent Index out of range error
            line_ending = False
            while i > 0 and not line_ending:
                if file_['fulltext'][file_['start'] + i] == "\n":
                    line_ending = True
                else:
                    i -= 1
            file_['end'] = file_['start'] + i
            # Check displayed text going past end of characters
            if file_['end'] >= file_['characters']:
                file_['end'] = file_['characters'] - 1

        # Update tooltip for listItem
        tt = selected.toolTip()
        tt2 = tt.split("From: ")[0]
        tt2 += "\n" + _("From: ") + str(file_['start']) + _(" to ") + str(file_['end'])
        selected.setToolTip(tt2)
        # Load file section into textEdit
        self.load_file(file_)'''

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
        Files menu option. """

        sql = "SELECT code_text.fid FROM code_text join source on source.id=code_text.fid \
            where code_text.owner=? and lower(source.mediapath)='%pdf' order by code_text.date desc limit 1"
        cur = self.app.conn.cursor()
        cur.execute(sql, [self.app.settings['codername'], ])
        result = cur.fetchone()
        if result is None:
            return
        for i, f in enumerate(self.filenames):
            if f['id'] == result[0]:
                self.ui.listWidget.setCurrentRow(i)
                self.load_file(f)
                self.search_term = ""
                break

    '''def go_to_bookmark(self):
        """ Find bookmark, open the file and highlight the bookmarked character.
        Adjust for start of text file, as this may be a smaller portion of the full text file.

        The currently loaded text portion may not contain the bookmark.
        Solution - reset the file start and end marks to the entire file length and
        load the entire text file.
        """

        cur = self.app.conn.cursor()
        cur.execute("select bookmarkfile, bookmarkpos from project")
        result = cur.fetchone()
        for i, f in enumerate(self.filenames):
            if f['id'] == result[0]:
                f['start'] = 0
                if f['end'] != f['characters']:
                    msg = _("Entire text file will be loaded")
                    Message(self.app, _('Information'), msg).exec()
                f['end'] = f['characters']
                try:
                    self.ui.listWidget.setCurrentRow(i)
                    self.load_file(f)
                    self.search_term = ""
                    # Set text cursor position and also highlight one character, to show location.
                    text_cursor = self.ui.textEdit.textCursor()
                    text_cursor.setPosition(result[1])
                    endpos = result[1] - 1
                    if endpos < 0:
                        endpos = 0
                    text_cursor.setPosition(endpos, QtGui.QTextCursor.MoveMode.KeepAnchor)
                    self.ui.textEdit.setTextCursor(text_cursor)
                except Exception as e:
                    logger.debug(str(e))
                break'''

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
        #TODO fix text start and end
        if "start" not in self.file_:
            self.file_['start'] = 0
        sql_values = []
        file_result = self.app.get_file_texts([file_['id']])[0]
        if "end" not in self.file_:
            self.file_['end'] = len(file_result['fulltext'])
        sql_values.append(int(file_result['id']))
        self.text = file_result['fulltext'][self.file_['start']:self.file_['end']]
        self.ui.textEdit.setPlainText(self.text)
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        self.show_all_codes_in_text()  # Deactivates the show_selected_code if this is active
        self.setWindowTitle(_("Code text: ") + self.file_['name'])
        self.ui.lineEdit_search.setEnabled(True)
        self.ui.checkBox_search_case.setEnabled(True)
        self.ui.checkBox_search_all_files.setEnabled(True)
        self.search_for_text()
        self.load_pdf()
        self.ui.spinBox.setMinimum(1)
        self.ui.spinBox.setMaximum(len(self.pages))
        print("len pages:", len(self.pages))
        self.ui.spinBox.setToolTip(_("Pages: ") + str(len(self.pages)))
        self.ui.spinBox.setEnabled(True)
        self.show_page(self.page_num)

    def load_pdf(self):
        """ Load page elements for all pages in the PDF.
        """

        self.ui.spinBox.setValue(1)
        filepath = None
        if self.file_['mediapath'][:6] == "/docs/":
            filepath = self.app.project_path + "/documents/" + self.file_['mediapath'][6:]
        if self.file_['mediapath'][:5] == "docs:":
            filepath = self.file_['mediapath'][5:]
        if not filepath:
            logger.error("Cannot open pdf file" + self.file_['mediapath'])
            print("Cannot open pdf file " + self.file_['mediapath'])
            return
        pdf_file = open(filepath, 'rb')
        resource_manager = PDFResourceManager()
        laparams = LAParams()
        device = PDFPageAggregator(resource_manager, laparams=laparams)
        interpreter = PDFPageInterpreter(resource_manager, device)
        #self.get_resources()
        pages_generator = PDFPage.get_pages(pdf_file)  # generator PDFpage objects
        self.pages = []
        self.page_num = 0
        for i, page in enumerate(pages_generator):
            self.page_dict = {'pagenum': i}
            print(f'Processing page: {i + 1}')
            self.page_dict['mediabox'] = page.mediabox
            self.page_dict['text'] = []
            self.page_dict['lines'] = []
            self.page_dict['curves'] = []
            self.page_dict['images'] = []
            self.page_dict['rect'] = []
            interpreter.process_page(page)
            layout = device.get_result()
            for lobj in layout:
                self.get_item_and_hierarchy(page, lobj)
            self.pages.append(self.page_dict)
        self.get_page_text()  # get full text to match sqlite stored text

    def get_item_and_hierarchy(self, page, lobj: Any, depth=0):
        """ Get item details add to page_dict, with depth and all its descendants.
        Objets added to self.page_dict, with depth counter
        """

        if isinstance(lobj, LTLine):
            #print("LTLINE", lobj.__dir__())
            # left, btm, right, top = lobj.x0, lobj.y0, lobj.x1, lobj.y1
            line_dict = {'x0': lobj.x0, 'y0': page.mediabox[3] - lobj.y0, 'y1': page.mediabox[3] - lobj.y1,
                         'x1': lobj.x1, 'linewidth': lobj.linewidth, 'stroke': lobj.stroke, 'fill': lobj.fill,
                         'stroking_color': lobj.stroking_color, 'non_stroking_color': lobj.non_stroking_color,
                         'pts': lobj.pts, 'depth': depth}
            self.page_dict['lines'].append(line_dict)

        if isinstance(lobj, LTRect):
            #print("LTRECT", lobj, type(lobj))
            rect_dict = {"x": lobj.bbox[0], "y": page.mediabox[3] - lobj.bbox[1] - lobj.height,
                         "w": lobj.width, "h": lobj.height,
                         "linewidth": lobj.linewidth, "stroke": lobj.stroke, "fill": lobj.fill,
                         "stroking_color": lobj.stroking_color,
                         "non_stroking_color": lobj.non_stroking_color, 'is_empty': lobj.is_empty(),
                         'depth': depth}
            self.page_dict['rect'].append(rect_dict)

        if isinstance(lobj, LTCurve):
            """ LTCurve can be a LTRect, LTImage or LTLine. The LTRect can contain a LTImage. """
            # print(lobj.__dir__())
            # left, btm, right, top = lobj.x0, lobj.y0, lobj.x1, lobj.y1
            curve_dict = {'x0': lobj.x0, 'y0': page.mediabox[3] - lobj.y0, 'y1': page.mediabox[3] - lobj.y1,
                          'x1': lobj.x1, 'linewidth': lobj.linewidth, 'stroke': lobj.stroke, 'fill': lobj.fill,
                          'stroking_color': lobj.stroking_color, 'non_stroking_color': lobj.non_stroking_color,
                          'is_empty': lobj.is_empty(),  # 'analyze': lobj.analyze(laparams),
                          'evenodd': lobj.evenodd,
                          'pts': [QtCore.QPointF(p[0], page.mediabox[3] - p[1]) for p in lobj.pts],
                          'depth': depth}
            self.page_dict['curves'].append(curve_dict)

        if isinstance(lobj, LTTextLine):
            # y-coordinates are the distance from the bottom of the page
            #  left, bottom, right, and top
            #print("LTTEXTLINE", obj.__dir__())
            left, btm, right, top, text = lobj.x0, lobj.y0, lobj.x1, lobj.y1, lobj.get_text()
            textline_dict = {'left': left, 'btm': page.mediabox[3] - btm,
                             'top': page.mediabox[3] - top,
                             'right': right, 'text': text, 'depth': depth}
            char_font_sizes = []
            fontnames = []
            colors = []
            for ltchar in lobj:
                fontname, fontsize, color = self.get_char_info(ltchar)
                char_font_sizes.append(fontsize)
                fontnames.append(fontname)  # TODO get most common
                colors.append(color)
            fontname = fontnames[0]
            if fontname.find("+") > 0:
                fontname = fontname.split("+")[1]
            textline_dict['fontname'] = fontname
            textline_dict['fontsize'] = int(median(char_font_sizes))
            textline_dict['color'] = colors[0]
            self.page_dict['text'].append(textline_dict)

        if isinstance(lobj, LTTextBox):
            # y-coordinates are the distance from the bottom of the page
            #  left, bottom, right, and top
            for textline in lobj:
                #print("TEXTLINE", textline.__dir__())
                # LTTextLineHorizontal
                left, btm, right, top, text = textline.x0, textline.y0, textline.x1, textline.y1, textline.get_text()
                textline_dict = {'left': left, 'btm': page.mediabox[3] - btm, 'top': page.mediabox[3] - top,
                                 'right': right, 'text': text, 'depth': depth}
                char_font_sizes = []
                fontnames = []
                colors = []
                for ltchar in textline:
                    fontname, fontsize, color = self.get_char_info(ltchar)
                    char_font_sizes.append(fontsize)
                    fontnames.append(fontname)  # TODO get most common
                    colors.append(color)
                '''fontname = fontnames[0]  # Not using this information
                if fontname.find("+") > 0:
                    # print(fontname)
                    fontname = fontname.split("+")[1]
                textline_dict['fontname'] = fontname'''
                textline_dict['fontsize'] = int(median(char_font_sizes))
                textline_dict['color'] = colors[0]
                self.page_dict['text'].append(textline_dict)

        if isinstance(lobj, LTImage):
            #print("IMG", lobj.__dir__())
            #print("BBOX - x,y,w,h", lobj.bbox)

            img_dict = {"name": lobj.name, "x": lobj.bbox[0], "y": page.mediabox[3] - lobj.bbox[1] - lobj.height,
                        "w": lobj.width, "h": lobj.height,
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

            if lobj.stream:
                img_dict['pixmap'] = None
                file_stream = lobj.stream.get_rawdata()
                file_ext = self.get_image_type(file_stream[0:4])
                img_dict['filetype'] = file_ext
                qp = QtGui.QPixmap()
                qp.loadFromData(file_stream)
                qpscaled = qp.scaled(int(img_dict['w']), int(img_dict['h']))
                img_dict['pixmap'] = qpscaled
            if not img_dict['pixmap'].isNull():
                self.page_dict['images'].append(img_dict)
            # saved_file = save_image(lobj, page_number, images_folder)

        if isinstance(lobj, LTFigure):
            """ LTFigure objects are containers for other LT* objects, so recurse through the children.
             LTRect, LTChar, LTCurve, LTLine """

            for obj in lobj:
                self.get_item_and_hierarchy(page, obj, depth=depth + 1)

        if isinstance(lobj, Iterable):
            for obj in lobj:
                self.get_item_and_hierarchy(page, obj, depth=depth + 1)

    def get_page_text(self):
        """ Get page text to match QualCoder text import. """

        filepath = None
        if self.file_['mediapath'][:6] == "/docs/":
            filepath = self.app.project_path + "/documents/" + self.file_['mediapath'][6:]
        if self.file_['mediapath'][:5] == "docs:":
            filepath = self.file_['mediapath'][5:]
        if not filepath:
            logger.error("Cannot open pdf file" + self.file_['mediapath'])
            print("Cannot open pdf file " + self.file_['mediapath'])
            return
        file_obj = open(filepath, 'rb')
        parser = PDFParser(file_obj)
        doc = PDFDocument(parser=parser)
        parser.set_document(doc)
        # Potential error with encrypted PDF
        rsrcmgr = PDFResourceManager()
        laparams = LAParams()
        laparams.char_margin = 1.0
        laparams.word_margin = 1.0
        device = PDFPageAggregator(rsrcmgr, laparams=laparams)
        interpreter = PDFPageInterpreter(rsrcmgr, device)
        self.full_text = ""
        for i, page in enumerate(PDFPage.create_pages(doc)):
            page_text = ""
            interpreter.process_page(page)
            layout = device.get_result()
            for lt_obj in layout:
                if isinstance(lt_obj, LTTextBox) or isinstance(lt_obj, LTTextLine):
                    page_text += lt_obj.get_text() + "\n"  # add line to paragraph spacing for visual format
            # Remove excess line endings, include those with one blank space on a line
            page_text = page_text.replace('\n \n', '\n')
            page_text = page_text.replace('\n\n\n', '\n\n')
            # Fix Pdfminer recognising invalid unicode characters.
            page_text = page_text.replace(u"\uE002", "Th")
            page_text = page_text.replace(u"\uFB01", "fi")
            self.pages[i]['plain_text'] = page_text
            self.full_text += page_text
        '''print("++++++FULL TEXT++++++++")
        print(self.full_text)'''

    def show_page(self, page_num):
        """ Display pdf page, using the PDF objects. """

        page = self.pages[page_num]
        page_rect = page['mediabox']
        self.ui.textEdit.setText("")
        text_edit_text = ""
        #if self.ui.radioButton_objects.isChecked():
        #    text_edit_text = "PAGE RECT: " + str(page_rect) + "\n"
        self.scene = QtWidgets.QGraphicsScene()
        self.ui.graphicsView.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)  #RenderHint.SmoothPixmapTransform)  # Antialiasing
        self.scene.setSceneRect(QtCore.QRectF(0, 0, page_rect[2], page_rect[3]))
        self.ui.graphicsView.setScene(self.scene)
        #self.ui.graphicsView.setBackgroundBrush(QtCore.Qt.GlobalColor.white)
        self.scene.setBackgroundBrush(QtCore.Qt.GlobalColor.white)
        self.scene.installEventFilter(self)  # TODO Later
        gray_pen = QtGui.QPen(QtCore.Qt.GlobalColor.gray, 1, QtCore.Qt.PenStyle.SolidLine)
        gray_dotted_pen = QtGui.QPen(QtCore.Qt.GlobalColor.gray, 1, QtCore.Qt.PenStyle.DotLine)
        self.scene.addRect(0, 0, page_rect[2], page_rect[3], gray_pen)
        counter = 0
        # Not sure to display these rects
        if self.ui.checkBox_rect.isChecked():
            for r in page['rect']:
                counter += 1
                #if self.ui.radioButton_objects.isChecked():
                #    text_edit_text += "RECT: " + str(r) + "\n"
                item = self.scene.addRect(r['x'], r['y'], r['w'], r['h'])
                #print("PAGE", self.page_num + 1, "RECT", r)
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
                #if self.ui.radioButton_objects.isChecked():
                #    text_edit_text += "CURVE: " + str(c) + "\n"
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
                '''if self.ui.radioButton_objects.isChecked():
                    text_edit_text += "IMAGE: " + str(img) + "\n"
                    self.put_image_into_textedit(img, counter)'''
                # Add pixmap to textEdit
                item = self.scene.addPixmap(img['pixmap'])
                item.setPos(img['x'], img['y'])

        if self.ui.checkBox_line.isChecked():
            for line in page['lines']:
                counter += 1
                if self.ui.radioButton_objects.isChecked():
                    text_edit_text += "LINE: " + str(line) + "\n"
                color = QtCore.Qt.GlobalColor.black
                if line['stroke']:
                    color = self.get_qcolor(line['stroking_color'])
                if line['fill']:
                    color = self.get_qcolor(line['non_stroking_color'])
                line_pen = QtGui.QPen(color, line['linewidth'], QtCore.Qt.PenStyle.SolidLine)
                item = self.scene.addLine(line['x0'], line['y0'], line['x1'], line['y1'], line_pen)

        if self.ui.checkBox_text.isChecked():
            self.text_items = []
            for t in page['text']:
                counter += 1
                if self.ui.radioButton_objects.isChecked():
                    text_edit_text += "TEXT: " +str(t) + "\n"
                item = self.scene.addText(t['text'])
                item.setPos(t['left'], t['top'])
                # print(i['fontname'], type(t['fontname']), t['fontsize'], type(t['fontsize']))
                '''font = QtGui.QFont(t['fontname'], t['fontsize'])
                print(t['fontname'])'''
                #font_size = QtGui.QFont(self.app.settings['font'], font_size)
                adjustment = self.ui.spinBox_font_adjuster.value()
                font_size = t['fontsize'] + adjustment  # e.g. minus 2 helps stop text overlaps
                if font_size < 4:
                    font_size = 4
                font = QtGui.QFont("Noto Sans", font_size)
                item.setFont(font)
                ttip = f"x:{int(t['left'])}, y:{int(t['top'])} {t['text']}"
                item.setToolTip(ttip)
                color = self.get_qcolor(t['color'])
                if self.ui.checkBox_black_text.isChecked():
                    color = QtCore.Qt.GlobalColor.black
                item.setDefaultTextColor(color)  # TODO option to set black only
                # Interaction
                item.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextEditorInteraction)
                item.setFlags(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
                self.text_items.append(item)
                '''item.setFlags(
                    QGraphicsItem::ItemIsFocusable | QGraphicsItem::ItemIsMovable | QGraphicsItem::ItemIsSelectable | ti->flags())'''
        text_edit_text += "\n\nOBJECTS: " + str(counter)

        if self.ui.radioButton_objects.isChecked():
            self.ui.textEdit.setText(text_edit_text)
        if self.ui.radioButton_text.isChecked():
            self.ui.textEdit.setText(page['plain_text'])

    def get_qcolor(self, pdf_color) -> QtGui.QColor:
        """  Get a pdf_color which can be in various formatos.
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

    def spin_page_changed(self):
        pass
        if self.pages:
            self.page_num = self.ui.spinBox.value() - 1
            self.show_page(self.page_num)

    def get_coded_text_update_eventfilter_tooltips(self):
        """ Called by load_file, and from other dialogs on update.
        Tooltips are for all coded_text or only for important if important is flagged.
        """

        if self.file_ is None:
            return
        sql_values = [int(self.file_['id']), self.app.settings['codername'], self.file_['start'], self.file_['end']]
        # Get code text for this file and for this coder
        self.code_text = []
        # seltext length, longest first, so overlapping shorter text is superimposed.
        sql = "select code_text.ctid, code_text.cid, fid, seltext, pos0, pos1, code_text.owner, code_text.date, " \
              "code_text.memo, important, name"
        sql += " from code_text join code_name on code_text.cid = code_name.cid"
        sql += " where fid=? and code_text.owner=? "
        # For file text which is currently loaded
        sql += " and pos0 >=? and pos1 <=? "
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

        if self.text is None or self.text == "":
            return
        cursor = self.ui.textEdit.textCursor()
        cursor.setPosition(0, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(len(self.text) - 1, QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(QtGui.QTextCharFormat())

    def highlight(self):
        """ Apply text highlighting to current file.
        If no colour has been assigned to a code, those coded text fragments are coloured gray.
        Each code text item contains: fid, date, pos0, pos1, seltext, cid, status, memo,
        name, owner.
        For defined colours in color_selector, make text light on dark, and conversely dark on light
        """

        if self.file_ is None:
            return
        if self.text is not None:
            # Add coding highlights
            codes = {x['cid']: x for x in self.codes}
            for item in self.code_text:
                fmt = QtGui.QTextCharFormat()
                cursor = self.ui.textEdit.textCursor()
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
                        cursor.setPosition(int(note['pos0']) - self.file_['start'],
                                           QtGui.QTextCursor.MoveMode.MoveAnchor)
                        cursor.setPosition(int(note['pos1']) - self.file_['start'],
                                           QtGui.QTextCursor.MoveMode.KeepAnchor)
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
                        if j['pos0'] >= i['pos0'] and j['pos1'] <= i['pos1']:
                            overlaps.append([j['pos0'], j['pos1']])
                        elif i['pos0'] >= j['pos0'] and i['pos1'] <= j['pos1']:
                            overlaps.append([i['pos0'], i['pos1']])
                        elif j['pos0'] > i['pos0']:
                            overlaps.append([j['pos0'], i['pos1']])
                        else:  # j['pos0'] < i['pos0']:
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

    def mark(self):
        """ Mark selected text in file with currently selected code.
       Need to check for multiple same codes at same pos0 and pos1.
       Update recent_codes list.
       Adjust for start of text file, as this may be a smaller portion of the full text file.
       """

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
        selected_text = self.ui.textEdit.textCursor().selectedText()
        pos0 = self.ui.textEdit.textCursor().selectionStart() + self.file_['start']
        pos1 = self.ui.textEdit.textCursor().selectionEnd() + self.file_['start']
        if pos0 == pos1:
            return
        # Add the coded section to code text, add to database and update GUI
        coded = {'cid': cid, 'fid': int(self.file_['id']), 'seltext': selected_text,
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
        self.code_text.append(coded)
        #self.highlight()
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
        # Need to remove from recent_codes, if there and add back in first position
        for item in self.recent_codes:
            if item == tmp_code:
                self.recent_codes.remove(item)
                break
        self.recent_codes.insert(0, tmp_code)
        if len(self.recent_codes) > 10:
            self.recent_codes = self.recent_codes[:10]
        self.update_file_tooltip()

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

    def unmark(self, location):
        """ Remove code marking by this coder from selected text in current file.
        Called by text_edit_context_menu
        Adjust for start of text file, as this may be a smaller portion of the full text file.

        param:
            location: text cursor location, Integer
        """

        if self.file_ is None:
            return
        unmarked_list = []
        for item in self.code_text:
            if item['pos0'] <= location + self.file_['start'] <= item['pos1'] and \
                    item['owner'] == self.app.settings['codername']:
                unmarked_list.append(item)
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
                                            + str(item['pos0']) + "-" + str(item['pos1']) + _(" for: ") + self.file_[
                                                'name'])
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
                                        + str(item['pos0']) + _(" for: ") + self.file_['name'])
        self.get_coded_text_update_eventfilter_tooltips()


    '''def get_cases_codings_annotations(self):
        """ Get all linked cases, coded text and annotations for this file.
         For editing mode. """

        cur = self.app.conn.cursor()
        sql = "select ctid, cid, pos0, pos1, seltext, owner from code_text where fid=?"
        cur.execute(sql, [self.file_['id']])
        res = cur.fetchall()
        self.ed_codetext = []
        for r in res:
            self.ed_codetext.append({'ctid': r[0], 'cid': r[1], 'pos0': r[2], 'pos1': r[3], 'seltext': r[4],
                                     'owner': r[5], 'npos0': r[2], 'npos1': r[3]})
        sql = "select anid, pos0, pos1 from annotation where fid=?"
        cur.execute(sql, [self.file_['id']])
        res = cur.fetchall()
        self.ed_annotations = []
        for r in res:
            self.ed_annotations.append({'anid': r[0], 'pos0': r[1], 'pos1': r[2],
                                        'npos0': r[1], 'npos1': r[2]})
        sql = "select id, pos0, pos1 from case_text where fid=?"
        cur.execute(sql, [self.file_['id']])
        res = cur.fetchall()
        self.ed_casetext = []
        for r in res:
            self.ed_casetext.append({'id': r[0], 'pos0': r[1], 'pos1': r[2],
                                     'npos0': r[1], 'npos1': r[2]})
        self.no_codes_annotes_cases = False
        if self.ed_casetext == [] and self.ed_annotations == [] and self.ed_codetext == []:
            self.no_codes_annotes_cases = True'''

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

        url = "https://github.com/ccbogel/QualCoder/wiki/07-Coding-Text"
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
        """ Code_text contains the coded text to be displayed in a tooptip.
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
                            text_ += " [ctid:" + str(item['ctid']) + "]"
                        text_ += "<br />" + seltext
                        if item['memo'] != "":
                            text_ += "<br /><em>" + _("MEMO: ") + item['memo'] + "</em>"
                        if item['important'] == 1:
                            text_ += "<br /><em>IMPORTANT</em>"
                        text_ += "</p>"
                        multiple += 1
                    except Exception as e:
                        msg = "Codes ToolTipEventFilter Exception\n" + str(e) + ". Possible key error: \n"
                        msg += str(item)
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
