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
https://qualcoder.org/
"""


from copy import copy, deepcopy
import datetime
# import difflib  # Slow, kept this in case need to revert to it. Now using diff_match_patch
import diff_match_patch
import emoji
import html
import logging
from operator import itemgetter
import os
import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/
from random import randint
import re
import sqlite3
import unicodedata
import webbrowser

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor
# Required for the _export_odt_clean method which generates native ODF files with ranged annotations using odfpy
from odf.opendocument import OpenDocumentText  # Required for _export_odt_clean method
from odf import text as odf_text, office as odf_office, dc as odf_dc, style as odf_style  # Need for _export_odt_clean
from odf.namespaces import OFFICENS, DRAWNS  # Required for _export_odt_clean method

from .add_item_name import DialogAddItemName
from .ai_agent_prompts import AiAgentPromptsCatalog, prompt_name_and_scope
from .ai_prompt_library import DialogAiEditPrompts
from .ai_search_dialog import DialogAiSearch
from .ai_chat import ai_chat_signal_emitter
from .code_in_all_files import DialogCodeInAllFiles
from .color_selector import DialogColorSelect, colour_ranges, colors, TextColor, show_codes_of_colour_range
from .confirm_delete import DialogConfirmDelete
from .helpers import Message, DialogGetStartAndEndMarks, ExportDirectoryPathDialog, NumberBar, CodeResizeHandle, \
    ToolTipEventFilter, init_persistent_tree_header, restore_persistent_tree_widths
from .GUI.ui_dialog_code_text import Ui_Dialog_code_text
from .memo import DialogMemo
from .report_attributes import DialogSelectAttributeParameters
from .ris import Ris
from .select_items import DialogSelectItems  # For isinstance()
from .speakers import DialogSpeakers, speaker_coder_name
from .coder_names import DialogCoderNames

ai_search_analysis_max_count = 10  # How many chunks of data are analysed in the second stage

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class CodingMargin(QtWidgets.QWidget):
    """ Draws side bars adjacent to the text and code names.
    Uses a track-packing algorithm so that overlapping codes occupy distinct
    vertical lanes. Embedded in a container widget (widget_code_margin_left /
    widget_code_margin_right). Scroll synchronization
    with the editor is handled via signal-slot from the editor's vertical
    scrollbar.

    The 'side' parameter controls visual layout:
    - 'left':  lanes stack right-to-left (lane 0 nearest text), names at far left.
    - 'right': lanes stack left-to-right (lane 0 nearest text), names at far right.
    """

    def __init__(self, editor, dialog_code_text, side='left'):
        super().__init__()
        self.editor = editor
        self.dialog = dialog_code_text
        self.side = side  # 'left' or 'right'
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._emit_context_menu_to_dialog)
        self.setMouseTracking(True)
        self.setMinimumWidth(120)

    def _emit_context_menu_to_dialog(self, position):
        if hasattr(self.dialog, 'coding_margin_context_menu'):
            self.dialog.coding_margin_context_menu(position, self)

    def _compute_lane_layout(self):
        """ Track-packing algorithm. Returns (ctid_columns, sorted_codes,
        current_fid), or (None, [], None) if the layout cannot be computed. """

        if not self.dialog.file_ or not self.dialog.code_text:
            return None, [], None

        current_fid = self.dialog.file_['id']
        important_only = getattr(self.dialog, 'important', False)

        sorted_codes = sorted(
            [c for c in self.dialog.code_text
             if c.get('fid') == current_fid
             and (not important_only or c.get('important') == 1)],
            key=lambda x: x.get('pos0', 0)
        )

        ctid_columns = {}
        tracks = []
        for code in sorted_codes:
            ctid = code.get('ctid')
            if ctid is None:
                continue
            placed = False
            for i, track_end in enumerate(tracks):
                if track_end <= code['pos0']:
                    tracks[i] = code['pos1']
                    ctid_columns[ctid] = i
                    placed = True
                    break
            if not placed:
                tracks.append(code['pos1'])
                ctid_columns[ctid] = len(tracks) - 1

        return ctid_columns, sorted_codes, current_fid

    def paintEvent(self, event):
        if not self.dialog.file_ or not self.dialog.code_text:
            return
        try:
            painter = QtGui.QPainter(self)
            font = QtGui.QFont(self.dialog.app.settings['font'], 9)
            painter.setFont(font)
            offset = self.editor.contentOffset()
            block = self.editor.firstVisibleBlock()

            ctid_columns, _sorted_codes, current_fid = self._compute_lane_layout()
            if current_fid is None:
                return

            drawn_ctids = set()

            while block.isValid():
                rect = self.editor.blockBoundingGeometry(block).translated(offset)
                if rect.top() > self.height():
                    break
                if rect.bottom() >= 0:
                    self.draw_code_bars(painter, block, rect, drawn_ctids, current_fid, ctid_columns)
                block = block.next()
        except Exception as e:
            logger.debug(f"CodingMargin paintEvent error: {e}")

    def draw_code_bars(self, painter, block, rect, drawn_ctids, current_fid, ctid_columns):
        """ Draw a coloured vertical bar per overlapping code on this block,
        plus the code name at the appropriate edge (only once per segment) """

        file_start = self.dialog.file_.get('start', 0)
        block_start = block.position() + file_start
        block_end = block_start + block.length()

        names_drawn_by_line = {}
        margin_width = self.width()

        important_only = getattr(self.dialog, 'important', False)
        layout = block.layout()

        bar_w = 3
        lane_step = 10

        for code in self.dialog.code_text:
            if code.get('fid') != current_fid:
                continue
            if important_only and code.get('important') != 1:
                continue
            ctid = code.get('ctid')
            if ctid is None:
                continue

            if code['pos0'] < block_end and code['pos1'] > block_start:
                col_index = ctid_columns.get(ctid, 0)

                if self.side == 'right':
                    offset_x = 12 + (col_index * lane_step)
                else:  # 'left'
                    offset_x = margin_width - 15 - (col_index * lane_step)

                color_hex = code.get('color', '#cccccc')
                color = QtGui.QColor(color_hex)
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.setBrush(color)

                start_rel = max(code['pos0'], block_start) - block_start
                end_rel = min(code['pos1'], block_end) - block_start
                start_rel = max(0, min(start_rel, max(0, block.length() - 1)))
                end_rel = max(start_rel + 1, min(end_rel, block.length()))
                start_line = layout.lineForTextPosition(start_rel)
                end_line = layout.lineForTextPosition(max(start_rel, end_rel - 1))

                if start_line.isValid() and end_line.isValid():
                    first_line = start_line.lineNumber()
                    last_line = end_line.lineNumber()
                    for line_number in range(first_line, last_line + 1):
                        line = layout.lineAt(line_number)
                        if not line.isValid():
                            continue
                        painter.drawRect(
                            offset_x,
                            int(rect.top() + line.y()),
                            bar_w,
                            max(1, int(line.height()))
                        )
                else:
                    painter.drawRect(offset_x, int(rect.top()), bar_w, int(rect.height()))

                if ctid not in drawn_ctids and code['pos0'] >= block_start:
                    painter.setPen(color.darker(150))
                    raw_name = code.get('name', '')
                    _fm = painter.fontMetrics()
                    if self.side == 'right':
                        _lanes_end_x = 12 + (col_index + 1) * lane_step
                        _available_w = max(0, margin_width - _lanes_end_x - 5)
                    else:  # 'left'
                        _lanes_start_x = margin_width - 15 - (col_index + 1) * lane_step
                        _available_w = max(0, _lanes_start_x - 5 - 5)
                    name = _fm.elidedText(
                        raw_name, QtCore.Qt.TextElideMode.ElideRight, _available_w)

                    if start_line.isValid():
                        line_number = start_line.lineNumber()
                        names_on_line = names_drawn_by_line.get(line_number, 0)
                        y_pos = int(rect.top() + start_line.y()
                                    + painter.fontMetrics().ascent()
                                    + (names_on_line * 12))
                        names_drawn_by_line[line_number] = names_on_line + 1
                    else:
                        names_on_line = names_drawn_by_line.get(-1, 0)
                        y_pos = int(rect.top() + painter.fontMetrics().ascent()
                                    + (names_on_line * 12))
                        names_drawn_by_line[-1] = names_on_line + 1

                    if self.side == 'right':
                        name_w = painter.fontMetrics().horizontalAdvance(name)
                        x_pos = max(margin_width - name_w - 5, 18)
                    else:  # 'left'
                        x_pos = 5

                    painter.drawText(x_pos, y_pos, name)
                    drawn_ctids.add(ctid)

    def _code_at_position(self, pos):
        """ Return the code_text item under the given QPoint, or None.
        Matches both the coloured stripe and the code name label"""

        if not self.dialog.file_ or not self.dialog.code_text:
            return None

        ctid_columns, _sorted, current_fid = self._compute_lane_layout()
        if current_fid is None:
            return None

        margin_width = self.width()
        bar_w = 3
        lane_step = 10

        offset = self.editor.contentOffset()
        block = self.editor.firstVisibleBlock()
        file_start = self.dialog.file_.get('start', 0)
        important_only = getattr(self.dialog, 'important', False)

        stripe_hit = None
        label_hit = None

        font = QtGui.QFont(self.dialog.app.settings['font'], 9)
        fm = QtGui.QFontMetrics(font)

        while block.isValid():
            rect = self.editor.blockBoundingGeometry(block).translated(offset)
            if rect.top() > self.height():
                break
            if rect.bottom() < 0:
                block = block.next()
                continue

            block_start = block.position() + file_start
            block_end = block_start + block.length()
            layout = block.layout()

            seen_ctids_in_block = set()
            names_drawn_by_line = {}

            for code in self.dialog.code_text:
                if code.get('fid') != current_fid:
                    continue
                if important_only and code.get('important') != 1:
                    continue
                ctid = code.get('ctid')
                if ctid is None:
                    continue
                if not (code['pos0'] < block_end and code['pos1'] > block_start):
                    continue

                col_index = ctid_columns.get(ctid, 0)
                if self.side == 'right':
                    offset_x = 12 + (col_index * lane_step)
                else:
                    offset_x = margin_width - 15 - (col_index * lane_step)

                start_rel = max(code['pos0'], block_start) - block_start
                end_rel = min(code['pos1'], block_end) - block_start
                start_rel = max(0, min(start_rel, max(0, block.length() - 1)))
                end_rel = max(start_rel + 1, min(end_rel, block.length()))
                start_line = layout.lineForTextPosition(start_rel)
                end_line = layout.lineForTextPosition(max(start_rel, end_rel - 1))

                if start_line.isValid() and end_line.isValid():
                    first_line = start_line.lineNumber()
                    last_line = end_line.lineNumber()
                    for line_number in range(first_line, last_line + 1):
                        line = layout.lineAt(line_number)
                        if not line.isValid():
                            continue
                        stripe_rect = QtCore.QRect(
                            offset_x,
                            int(rect.top() + line.y()),
                            bar_w,
                            max(1, int(line.height())))
                        if stripe_rect.contains(pos):
                            stripe_hit = code

                if ctid not in seen_ctids_in_block and code['pos0'] >= block_start:
                    raw_name = code.get('name', '')
                    if self.side == 'right':
                        _lanes_end_x = 12 + (col_index + 1) * lane_step
                        _available_w = max(0, margin_width - _lanes_end_x - 5)
                    else:  # 'left'
                        _lanes_start_x = margin_width - 15 - (col_index + 1) * lane_step
                        _available_w = max(0, _lanes_start_x - 5 - 5)
                    name = fm.elidedText(
                        raw_name, QtCore.Qt.TextElideMode.ElideRight, _available_w)
                    if start_line.isValid():
                        line_number = start_line.lineNumber()
                        names_on_line = names_drawn_by_line.get(line_number, 0)
                        y_pos = int(rect.top() + start_line.y()
                                    + fm.ascent()
                                    + (names_on_line * 12))
                        names_drawn_by_line[line_number] = names_on_line + 1
                    else:
                        names_on_line = names_drawn_by_line.get(-1, 0)
                        y_pos = int(rect.top() + fm.ascent() + (names_on_line * 12))
                        names_drawn_by_line[-1] = names_on_line + 1

                    name_w = fm.horizontalAdvance(name)
                    if self.side == 'right':
                        x_pos = max(margin_width - name_w - 5, 18)
                    else:
                        x_pos = 5

                    label_rect = QtCore.QRect(
                        x_pos,
                        y_pos - fm.ascent(),
                        name_w,
                        fm.height())
                    if label_rect.contains(pos):
                        label_hit = code
                    seen_ctids_in_block.add(ctid)

            block = block.next()

        return stripe_hit if stripe_hit is not None else label_hit

    def mouseMoveEvent(self, event):
        """ hover over a code -> show tooltip """

        try:
            code = self._code_at_position(event.pos())
        except Exception as e:
            logger.debug(f"CodingMargin hit-test error: {e}")
            code = None

        if code is None:
            QtWidgets.QToolTip.hideText()
            self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            super().mouseMoveEvent(event)
            return

        try:
            tooltip_html = self.dialog._build_code_tooltip_html(code)
        except Exception as e:
            logger.debug(f"CodingMargin tooltip build error: {e}")
            tooltip_html = code.get('name', '')

        QtWidgets.QToolTip.showText(event.globalPosition().toPoint(),
                                    tooltip_html,
                                    self)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        """ left-click on stripe/label -> select that exact coded segment in editor. """

        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            try:
                code = self._code_at_position(event.pos())
            except Exception as e:
                logger.debug(f"CodingMargin click hit-test error: {e}")
                code = None
            if code is not None and self.dialog.file_ is not None:
                file_start = self.dialog.file_.get('start', 0)
                pos0 = code['pos0'] - file_start
                pos1 = code['pos1'] - file_start
                text_len = len(self.dialog.ui.plainTextEdit.toPlainText())
                pos0 = max(0, min(pos0, text_len))
                pos1 = max(0, min(pos1, text_len))
                cursor = self.dialog.ui.plainTextEdit.textCursor()
                cursor.setPosition(pos0, QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(pos1, QtGui.QTextCursor.MoveMode.KeepAnchor)
                self.dialog.ui.plainTextEdit.setTextCursor(cursor)
                self.dialog.ui.plainTextEdit.ensureCursorVisible()
                event.accept()
                return
        super().mousePressEvent(event)

    def leaveEvent(self, event):
        QtWidgets.QToolTip.hideText()
        self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)


class DialogCodeText(QtWidgets.QWidget):
    """ Code management. Add, delete codes. Mark and unmark text.
    Add memos and colors to codes.
    Trialled using setHtml for documents, but on marking text Html formatting was replaced, also
    on unmarking text, the unmark was not immediately cleared (needed to reload the file). """

    def __init__(self, app, parent_textedit, tab_reports):

        super(DialogCodeText, self).__init__()
        self.app = app
        self.tab_reports = tab_reports  # Tab widget reports, used for updates to codes in other tabs
        self.parent_textEdit = parent_textedit
        self.layout_direction = "LtoR"
        self.ui = Ui_Dialog_code_text()
        self.ui.setupUi(self)

        self.default_new_code_color = None  # Alternatively have a hex defined colour
        self.important = False  # Show/hide important codes
        self.recent_codes = []  # List of recent codes (up to 5) for textedit context menu
        self.file_ = None  # Contains current filename and file id
        self.code_text = []  # List of coded segments for the curent file
        self.undo_deleted_codes = []  # To restore recently deleted codes
        self.attributes = []  # Show selected files using these attributes in list widget
        self.tree_sort_option = "all asc"  # all asc, all desc, cat then code asc
        self.show_codes_like_filter = ""  # gets filled when text strings are used to show specific code names
        self.show_codes_colour_filter = ""  # gets filled when a code colur is selected

        # Get data
        self.annotations = self.app.get_annotations()
        self.codes, self.categories = self.app.get_codes_categories()
        self.get_recent_codes()  # After codes obtained!

        # Search text variables
        self.search_threshold = 3  # Three characters entered before search can begin
        self.search_indices = []  # List of file data, start, end, start_line, start char, String len
        self.search_index = 0
        self.search_term = ""
        self.selected_code_index = 0

        # Overlapping coded text details
        self.overlaps_at_pos = []
        self.overlaps_at_pos_idx = 0

        # Autocode variables
        self.autocode_history = []  # List dictionaries of autocode history {title, list of dictionary of sql commands}
        self.autocode_all_first_last_within = "all"  # Autocode all or first or last or within another code in a file
        self.autocode_frag_all_first_within = "all"  # Autocode all instances or within another code in a file

        # Timers to reduce overly sensitive key events: overlap, re-size oversteps by multiple characters
        self.code_resize_timer = 0
        self.code_resize_timer = datetime.datetime.now()
        self.overlap_timer = 0
        self.overlap_timer = datetime.datetime.now()

        # Variables associated with right-hand side splitter, for project memo, code rule
        self.project_memo = False
        self.code_rule = False

        # Variables for right pane toggle
        self.right_pane_size = 260  # Default size, remembers last size before collapse

        # Visual options for code stripes margin and highlight style.
        # show_margin_stripes and highlight_style are INDEPENDENT preferences,
        # persisted under separate keys and changed via the margin context menu <- L
        try:
            saved_pref = self.app.settings.get('codetext_show_margin_stripes', 'False')
            if isinstance(saved_pref, bool):
                self.show_margin_stripes = saved_pref
            else:
                self.show_margin_stripes = str(saved_pref).lower() == 'true'
        except (KeyError, AttributeError):
            self.show_margin_stripes = False  # (default: margin hidden)

        try:
            saved_style = self.app.settings.get('codetext_highlight_style', None)
        except (KeyError, AttributeError):
            saved_style = None

        if saved_style in ('marker', 'underline'):
            self.highlight_style = saved_style
        else:
            # Backwards-compatible default derived from margin visibility.
            self.highlight_style = 'underline' if self.show_margin_stripes else 'marker'

        # Variables for Edit mode
        self.text = ""
        self.ed_codetext = []
        self.ed_annotations = []
        self.ed_casetext = []
        self.prev_text = ""
        self.code_deletions = []
        self.edit_mode = False
        self.edit_pos = 0
        self.no_codes_annotes_cases = None
        self.edit_mode_has_changed = False
        self.ui.groupBox_edit_mode.hide()
        lbl_font = f'font: {self.app.settings["fontsize"] - 2}pt "{self.app.settings["font"]}";'
        self.ui.label_editing.setStyleSheet(lbl_font)
        ee = f'{_("EDITING TEXT MODE (Ctrl+E)")} '
        ee += _(
            "Avoid selecting sections of text with a combination of not underlined (not coded / annotated / "
            "case-assigned) and underlined (coded, annotated, case-assigned).")
        ee += " " + _(
            "Positions of the underlying codes / annotations / case-assigned may not correctly adjust if text is "
            "typed over or deleted.")
        self.ui.label_editing.setText(ee)
        self.ui.pushButton_edit_next.setIcon(qta.icon('mdi6.arrow-right'))
        self.ui.pushButton_edit_next.clicked.connect(lambda pressed: self.edit_mode_find("next"))
        self.ui.pushButton_edit_prev.setIcon(qta.icon('mdi6.arrow-left'))
        self.ui.pushButton_edit_prev.clicked.connect(lambda pressed: self.edit_mode_find("previous"))
        self.ui.label_edit_case_sensitive.setPixmap(qta.icon('mdi6.format-letter-case').pixmap(22, 22))
        self.ui.checkBox_edit_case_sensitive.stateChanged.connect(self.edit_mode_find)
        self.ui.lineEdit_edit_search.returnPressed.connect(self.edit_mode_find)
        self.edit_pos = 0
        self.edit_mode = False
        # Revert to original if edit text caused problems
        self.edit_original_source = None
        self.edit_original_source_id = None
        self.edit_original_codes = None
        self.edit_original_annotations = None
        self.edit_original_case_assignment = None
        self.edit_original_cutoff_datetime = None
        
        # For Code Resize Handles Experimental
        self.active_handles = []

        # Setup up widgets
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        tree_font = f'font: {self.app.settings["treefontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.treeWidget.setStyleSheet(tree_font)
        if 'docfont' not in self.app.settings:
            self.app.settings['docfont'] = self.app.settings['font']
        doc_font = f'font: {self.app.settings["docfontsize"]}pt "{self.app.settings["docfont"]}";'
        self.ui.plainTextEdit.setStyleSheet(doc_font)
        self.ui.lineEdit_coder.setText(self.app.settings['codername'])
        self.ui.pushButton_coder.clicked.connect(self.edit_coder_names)
        self.ui.plainTextEdit.setPlainText("")
        self.ui.plainTextEdit.setAutoFillBackground(True)
        self.ui.plainTextEdit.setToolTip("")
        self.ui.plainTextEdit.setMouseTracking(True)
        self.ui.plainTextEdit.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.ui.plainTextEdit.installEventFilter(self)
        self.eventFilterTT = ToolTipEventFilter()
        self.ui.plainTextEdit.installEventFilter(self.eventFilterTT)
        self.ui.plainTextEdit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.plainTextEdit.customContextMenuRequested.connect(self.text_edit_menu)
        self.ui.plainTextEdit.cursorPositionChanged.connect(self.overlapping_codes_in_text)
        self.ui.plainTextEdit.verticalScrollBar().valueChanged.connect(self.hide_resize_handles)

        self.ui.textEdit_info.setReadOnly(True)
        self.ui.listWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.listWidget.customContextMenuRequested.connect(self.file_menu)
        self.ui.listWidget.setStyleSheet(tree_font)
        self.ui.listWidget.selectionModel().selectionChanged.connect(self.file_selection_changed)
        self.search_threshold = 3  # 3 character threshold for text search
        self.ui.lineEdit_search.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.lineEdit_search.customContextMenuRequested.connect(self.lineedit_search_menu)
        self.ui.lineEdit_search.returnPressed.connect(self.move_to_next_search_text)
        self.ui.tabWidget.currentChanged.connect(self.tab_changed)
        self.ui.tabWidget.setCurrentIndex(0)  # Defaults to list of documents

        self.files = []
        self.get_files()

        # Buttons under files list
        self.ui.pushButton_latest.setIcon(qta.icon('mdi6.arrow-collapse-right'))
        self.ui.pushButton_latest.pressed.connect(self.go_to_latest_coded_file)
        self.ui.pushButton_next_file.setIcon(qta.icon('mdi6.arrow-right'))
        self.ui.pushButton_next_file.pressed.connect(self.go_to_next_file)
        self.ui.pushButton_bookmark_go.setIcon(qta.icon('mdi6.bookmark'))
        self.ui.pushButton_bookmark_go.pressed.connect(self.go_to_bookmark)
        self.ui.pushButton_document_memo.setIcon(qta.icon('mdi6.text-long'))
        self.ui.pushButton_document_memo.pressed.connect(self.active_file_memo)
        self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_file_attributes.pressed.connect(self.get_files_from_attributes)
        self.ui.pushButton_clear_filter_file.setIcon(qta.icon('mdi6.filter-off-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_clear_filter_file.pressed.connect(self.clear_file_filter)
        self.ui.pushButton_clear_filter_file.setToolTip(_("Clear file filter"))
        self.ui.pushButton_clear_filter_file.setVisible(False)  # hidden until a filter is active
        # Widgets under codes tree
        self.ui.pushButton_find_code.setIcon(qta.icon('mdi6.card-search-outline', options=[{'scale-factor': 1.3}]))
        self.ui.pushButton_find_code.pressed.connect(self.find_code_in_tree)
        self.ui.pushButton_show_codings_next.setIcon(qta.icon('mdi6.arrow-right'))
        self.ui.pushButton_show_codings_next.pressed.connect(self.show_selected_code_in_text_next)
        self.ui.pushButton_show_codings_prev.setIcon(qta.icon('mdi6.arrow-left'))
        self.ui.pushButton_show_codings_prev.pressed.connect(self.show_selected_code_in_text_previous)
        self.ui.pushButton_show_all_codings.setIcon(qta.icon('mdi6.text-search'))
        self.ui.pushButton_show_all_codings.pressed.connect(self.show_all_codes_in_text)
        self.ui.pushButton_show_all_codings.setIcon(qta.icon('mdi6.text-search', options=[{'scale-factor': 1.2}]))
        self.ui.pushButton_show_all_codings.pressed.connect(self.show_all_codes_in_text)
        self.ui.pushButton_important.setIcon(qta.icon('mdi6.star-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_important.pressed.connect(self.show_important_coded)
        self.ui.pushButton_clear_filter_code.setIcon(qta.icon('mdi6.filter-off-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_clear_filter_code.pressed.connect(self.clear_code_filter)
        self.ui.pushButton_clear_filter_code.setToolTip(_("Clear code filter"))
        self.ui.pushButton_clear_filter_code.setVisible(False)  # hidden until a filter is active        
        self.ui.lineEdit_code_filter.textChanged.connect(lambda textchanged: self.show_codes_like(self.ui.lineEdit_code_filter.text()))

        # Right hand side splitter buttons
        self.ui.pushButton_code_rule.setIcon(qta.icon('mdi6.text-shadow'))
        self.ui.pushButton_code_rule.pressed.connect(self.show_code_rule)
        self.ui.pushButton_journal.hide()
        self.ui.pushButton_project_memo.setIcon(qta.icon('mdi6.file-document-outline'))
        self.ui.pushButton_project_memo.pressed.connect(self.show_project_memo)
        self.ui.textEdit_info.tabChangesFocus()
        
        # Header buttons
        self.ui.pushButton_annotate.setIcon(qta.icon('mdi6.text-box-edit-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_annotate.pressed.connect(self.annotate)
        self.ui.pushButton_show_annotations.setIcon(
            qta.icon('mdi6.text-search-variant', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_show_annotations.pressed.connect(self.show_annotations)
        self.ui.pushButton_coding_memo.setIcon(qta.icon('mdi6.text-box-edit', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_coding_memo.pressed.connect(self.coded_text_memo)
        self.ui.pushButton_show_memos.setIcon(qta.icon('mdi6.text-search', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_show_memos.pressed.connect(self.show_memos)
        self.ui.pushButton_mark_speakers.setIcon(qta.icon('mdi6.pin-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_mark_speakers.pressed.connect(self.mark_speakers)
        self.ui.pushButton_auto_code.setIcon(qta.icon('mdi6.mace'))
        self.ui.pushButton_auto_code.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.pushButton_auto_code.customContextMenuRequested.connect(self.button_auto_code_menu)
        self.ui.pushButton_auto_code.clicked.connect(self.auto_code)
        self.ui.pushButton_auto_code_frag_this_file.setIcon(qta.icon('mdi6.magic-staff'))
        self.ui.pushButton_auto_code_frag_this_file.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.pushButton_auto_code_frag_this_file.customContextMenuRequested.connect(self.button_auto_code_frag_menu)
        self.ui.pushButton_auto_code_frag_this_file.pressed.connect(self.auto_code_sentences)
        self.ui.pushButton_auto_code_surround.setIcon(qta.icon('mdi6.spear'))
        self.ui.pushButton_auto_code_surround.pressed.connect(self.button_autocode_surround)
        self.ui.pushButton_auto_code_undo.setIcon(qta.icon('mdi6.undo'))
        self.ui.pushButton_auto_code_undo.pressed.connect(self.undo_autocoding)
        self.ui.pushButton_default_new_code_color.setIcon(qta.icon('mdi6.palette', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_default_new_code_color.pressed.connect(self.set_default_new_code_color)
        self.ui.label_exports.setPixmap(qta.icon('mdi6.export').pixmap(22, 22))

        self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
        self.ui.lineEdit_search.setEnabled(False)
        self.ui.checkBox_search_all_files.stateChanged.connect(self.search_for_text)
        self.ui.checkBox_search_all_files.setEnabled(False)
        self.ui.checkBox_search_case.stateChanged.connect(self.search_for_text)
        self.ui.checkBox_search_case.setEnabled(False)
        self.ui.label_search_regex.setPixmap(qta.icon('mdi6.help').pixmap(22, 22))
        self.ui.label_search_case_sensitive.setPixmap(qta.icon('mdi6.format-letter-case').pixmap(22, 22))
        self.ui.label_search_all_files.setPixmap(qta.icon('mdi6.text-box-multiple-outline').pixmap(22, 22))
        self.ui.pushButton_font.setIcon(qta.icon('mdi6.format-size', options=[{'scale_factor': 1.3}]))
        tt = _("Select document font and size.") + f"\n{self.app.settings['docfontsize']} {self.app.settings['font']}"
        self.ui.pushButton_font.setToolTip(tt)
        self.ui.pushButton_font.clicked.connect(self.change_document_font)
        self.ui.pushButton_previous.setIcon(qta.icon('mdi6.arrow-left', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_previous.setEnabled(False)
        self.ui.pushButton_next.setIcon(qta.icon('mdi6.arrow-right', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_next.setEnabled(False)
        self.ui.pushButton_next.pressed.connect(self.move_to_next_search_text)
        self.ui.pushButton_previous.pressed.connect(self.move_to_previous_search_text)
        self.ui.pushButton_help.setIcon(qta.icon('mdi6.help'))
        self.ui.pushButton_help.pressed.connect(self.help)
        self.ui.pushButton_right_side_pane.setIcon(qta.icon('mdi6.arrow-expand-left', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_right_side_pane.pressed.connect(self.show_right_side_pane)
        self.ui.pushButton_delete_all_codes.setIcon(qta.icon('mdi6.delete-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_delete_all_codes.pressed.connect(self.delete_all_codes_from_file)
        self.ui.pushButton_edit.setIcon(qta.icon('mdi6.text-box-edit-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_edit.pressed.connect(self.edit_mode_toggle)
        self.ui.pushButton_exit_edit.setIcon(qta.icon('mdi6.text-box-check-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_exit_edit.pressed.connect(self.edit_mode_toggle)
        self.ui.pushButton_undo_edit.setIcon(qta.icon('mdi6.undo', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_undo_edit.pressed.connect(self.undo_edited_text)
        self.ui.comboBox_export.currentIndexChanged.connect(self.export_option_selected)
        # Tree widget
        self.ui.treeWidget.setDragEnabled(True)
        self.ui.treeWidget.setAcceptDrops(True)
        self.ui.treeWidget.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.ui.treeWidget.viewport().installEventFilter(self)
        self.ui.treeWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.treeWidget.customContextMenuRequested.connect(self.tree_menu)
        self.ui.treeWidget.itemPressed.connect(self.fill_code_label_with_selected_code)
        init_persistent_tree_header(self.ui.treeWidget, self.app, 'dialogcodetext_tree_widths')

        self.ui.splitter.setSizes([150, 400, 0])  # 3 values; right pane starts collapsed <- L
        try:
            s0 = int(self.app.settings['dialogcodetext_splitter0'])
            s1 = int(self.app.settings['dialogcodetext_splitter1'])
            if s0 > 5 and s1 > 5:
                self.ui.splitter.setSizes([s0, s1, 0])  # 3 values, right pane collapsed
            v0 = int(self.app.settings['dialogcodetext_splitter_v0'])
            v1 = int(self.app.settings['dialogcodetext_splitter_v1'])
            if v0 > 5 and v1 > 5:
                self.ui.leftsplitter.setSizes([v0, v1, 30])
        except KeyError:
            pass
        # Restore remembered right pane size (but keep panel collapsed until user opens it)
        try:
            s2 = int(self.app.settings['dialogcodetext_splitter2'])
            if s2 > 5:
                self.right_pane_size = s2
        except KeyError:
            pass
        self.ui.splitter.splitterMoved.connect(self.update_sizes)
        self.ui.leftsplitter.splitterMoved.connect(self.update_sizes)

        # Add paragraph numbers widget
        self.number_bar = NumberBar(self.ui.plainTextEdit)
        layout = QtWidgets.QVBoxLayout(self.ui.lineNumbers)
        layout.setContentsMargins(0, 0, 0, 0)  # Remove margins if needed
        layout.addWidget(self.number_bar)
        self.ui.lineNumbers.setLayout(layout)

        # expose the margin context menu over the line numbers widget too <- L
        self.ui.lineNumbers.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.lineNumbers.customContextMenuRequested.connect(
            lambda pos: self.coding_margin_context_menu(pos, self.ui.lineNumbers))

        # Initialize coding margin INSIDE the .ui container widget
        # (widget_code_margin_left or widget_code_margin_right). Qt's layout
        # manages its size. Default side is 'left'; user can switch via menu <- L
        try:
            saved_side = self.app.settings.get('codetext_margin_side', 'left')
            if saved_side not in ('left', 'right'):
                saved_side = 'left'
            self.margin_side = saved_side
        except (KeyError, AttributeError):
            self.margin_side = 'left'
        self.coding_margin = CodingMargin(self.ui.plainTextEdit, self, side=self.margin_side)

        # Inject the margin widget into the chosen container (mirroring the
        # NumberBar pattern used for self.ui.lineNumbers)
        self._coding_margin_layout_left = QtWidgets.QVBoxLayout(self.ui.widget_code_margin_left)
        self._coding_margin_layout_left.setContentsMargins(0, 0, 0, 0)
        self._coding_margin_layout_right = QtWidgets.QVBoxLayout(self.ui.widget_code_margin_right)
        self._coding_margin_layout_right.setContentsMargins(0, 0, 0, 0)

        # make widget_code_margin_left, plainTextEdit and widget_code_margin_right
        # user-resizable by wrapping them inside a horizontal QSplitter
        self._text_margins_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self._text_margins_splitter.setHandleWidth(4)
        self._text_margins_splitter.setChildrenCollapsible(False)

        # Switch margin containers' size policy from Fixed to Preferred so
        # the splitter can resize them. plainTextEdit keeps Expanding
        for _margin_w in (self.ui.widget_code_margin_left,
                          self.ui.widget_code_margin_right):
            _sp = _margin_w.sizePolicy()
            _sp.setHorizontalPolicy(QtWidgets.QSizePolicy.Policy.Preferred)
            _margin_w.setSizePolicy(_sp)

        # detach the three widgets from horizontalLayout and reinsert them
        # into the splitter, preserving order <- L
        _hlayout = self.ui.widget_textEdit.layout()
        _insert_index = _hlayout.indexOf(self.ui.widget_code_margin_left)
        for _w in (self.ui.widget_code_margin_left,
                   self.ui.plainTextEdit,
                   self.ui.widget_code_margin_right):
            _hlayout.removeWidget(_w)
            self._text_margins_splitter.addWidget(_w)
        _hlayout.insertWidget(_insert_index, self._text_margins_splitter)

        # give plainTextEdit a non-zero stretch factor so the editor keeps
        # most of the horizontal space by default <- L
        self._text_margins_splitter.setStretchFactor(
            self._text_margins_splitter.indexOf(self.ui.plainTextEdit), 1)

        self._install_coding_margin_in_side(self.margin_side)

        # apply initial visibility based on persisted preference <- L
        self.coding_margin.setVisible(self.show_margin_stripes)
        self._set_margin_container_visibility(self.show_margin_stripes)
        self.ui.lineNumbers.setToolTip(_("Right click for highlighting options"))

        # sync margin redraw with editor scroll <- L
        self.ui.plainTextEdit.verticalScrollBar().valueChanged.connect(self.coding_margin.update)

        self.app.project_events.project_data_changed.connect(self._on_project_data_changed)
        self.fill_tree()
        # These signals after the tree is filled the first time
        self.ui.treeWidget.itemCollapsed.connect(self.get_collapsed)
        self.ui.treeWidget.itemExpanded.connect(self.get_collapsed)
        self.ui.treeWidget.itemClicked.connect(self.tree_item_clicked)

        # Variables and widgets for AI search
        self.ai_search_results = []
        self.ai_search_code_name = ''
        self.ai_search_code_memo = ''
        self.ai_search_file_ids = []
        self.ai_search_code_ids = []
        self.ai_search_similar_chunk_list = []
        self.ai_search_chunks_pos = 0
        self.ai_search_running = False
        self.ai_search_current_result_index = None
        self.ai_search_prompt = None
        self.ai_search_ai_model = None
        self.ai_include_coded_segments = None
        self.ai_search_found = False
        self.ai_search_analysis_counter = 0
        self.ai_search_session_id = 0
        self.ui.pushButton_ai_search.pressed.connect(self.ai_search_clicked)
        self.ui.listWidget_ai.selectionModel().selectionChanged.connect(self.ai_search_selection_changed)
        self.ai_search_listview_action_label = None
        self.ui.listWidget_ai.clicked.connect(self.ai_search_list_clicked)
        self.ui.ai_progressBar.setVisible(False)
        self.ui.ai_progressBar.setStyleSheet(f"""
            QProgressBar::chunk {{
                background-color: {self.app.highlight_color()};
            }}
        """)
        self.ai_search_spinner_sequence = ['', '.', '..', '...']
        self.ai_search_spinner_index = 0
        self.ai_search_spinner_timer = QtCore.QTimer(self)
        self.ai_search_spinner_timer.timeout.connect(self.ai_search_update_spinner)
        self.update_ai_menu_options()

    @staticmethod
    def _text_analysis_prompt_menu_leaf(relative_path: str) -> str:
        """Return the leaf label for one text-analysis prompt menu item."""

        normalized = str(relative_path if relative_path is not None else "").replace("\\", "/").strip("/")
        if normalized == "":
            return ""
        return normalized.rsplit("/", 1)[-1]

    def _text_analysis_prompt_folder_icon(self):
        """Return the same folder icon used by the prompt library."""

        return qta.icon("mdi.folder-outline", color=self.app.highlight_color())

    def _text_analysis_prompt_file_icon(self, menu):
        """Return the same prompt file icon used by the prompt library."""

        text_color = menu.palette().color(QtGui.QPalette.ColorRole.Text).name()
        return qta.icon("mdi6.script-text-outline", color=text_color)

    def _populate_text_analysis_prompt_menu(self, menu, prompts_catalog, prompt_records) -> None:
        """Populate one prompt menu, mirroring the prompt library folder structure."""

        menu_tree = {"prompts": [], "folders": {}}
        for prompt in prompt_records:
            relative_path = prompts_catalog.prompt_name_within_type(prompt.name)
            parts = [part for part in relative_path.split("/") if part != ""]
            if len(parts) == 0:
                continue
            current_branch = menu_tree
            for part in parts[:-1]:
                current_branch = current_branch["folders"].setdefault(part, {"prompts": [], "folders": {}})
            current_branch["prompts"].append((relative_path, prompt))

        def populate_branch(parent_menu, branch) -> None:
            for branch_relative_path, prompt_record in branch["prompts"]:
                action = parent_menu.addAction(self._text_analysis_prompt_menu_leaf(branch_relative_path))
                action.setToolTip(prompt_record.description)
                action.setIcon(self._text_analysis_prompt_file_icon(parent_menu))
                action.setProperty('submenu', 'ai_text_analysis')
                action.setData(prompt_record)
            for folder_name, child_branch in branch["folders"].items():
                submenu = parent_menu.addMenu(folder_name)
                submenu.setToolTipsVisible(True)
                submenu.setIcon(self._text_analysis_prompt_folder_icon())
                populate_branch(submenu, child_branch)

        populate_branch(menu, menu_tree)

    def _ai_menu_options_enabled(self) -> bool:
        """Return whether AI-specific text-coding actions should be enabled."""

        return self.app.settings.get('ai_enable', 'False') == 'True'

    def update_ai_menu_options(self):
        """Refresh AI-specific controls inside the text-coding workspace."""

        self.ui.pushButton_ai_search.setEnabled(self._ai_menu_options_enabled())

    def _ai_search_scope_id(self):
        return id(self)

    def _ai_search_scope_active(self) -> bool:
        ai = getattr(self.app, 'ai', None)
        if ai is None or not hasattr(ai, 'has_active_runs'):
            return False
        try:
            return bool(ai.has_active_runs('ai_search', self._ai_search_scope_id()))
        except Exception as err:
            logger.warning(err)
            return False

    def _ai_search_scope_status(self) -> str:
        ai = getattr(self.app, 'ai', None)
        if ai is None or not hasattr(ai, 'get_scope_status'):
            return 'idle'
        try:
            return str(ai.get_scope_status('ai_search', self._ai_search_scope_id())).strip() or 'idle'
        except Exception:
            return 'idle'

    def _cancel_ai_search_scope(self, wait_ms: int = 5000) -> bool:
        ai = getattr(self.app, 'ai', None)
        if ai is None:
            return True
        if hasattr(ai, 'cancel_scope'):
            return bool(ai.cancel_scope('ai_search', self._ai_search_scope_id(), wait_ms=wait_ms))
        return bool(ai.cancel(ask=False))

    def help(self):
        """ Open help for transcribe section in browser. """
        self.app.help_wiki("4.1.-Coding-Text")

    def _build_code_tooltip_html(self, code):  # <- L
        """ Build the tooltip HTML for a single coded segment """

        seltext = code.get('seltext', '') or ''
        seltext = seltext.replace("\n", "").replace("\r", "")
        # Readable cut-off, not halfway through a word (mirrors ToolTipEventFilter)
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

        color = TextColor(code.get('color', '#cccccc')).recommendation
        text_ = '<p style="background-color:' + code.get('color', '#cccccc') + "; color:" + color + '"><em>'
        text_ += code.get('name', '') + "</em>"
        if self.app.settings['showids']:
            text_ += " [ctid:" + str(code.get('ctid', '')) + "]"
        text_ += " (" + str(code.get('owner', '')) + ")"
        text_ += "<br />" + seltext
        if code.get('memo', '') != "":
            memo_text = code['memo']
            if len(memo_text) > 150:
                memo_text = memo_text[:150] + "..."
            text_ += "<br /><em>" + _("MEMO: ") + memo_text + "</em>"
        if code.get('important') == 1:
            text_ += "<br /><em>" + _("IMPORTANT") + "</em>"
        text_ += "</p>"
        return text_

    # Helpers to relocate the coding margin between left/right <- L
    def _install_coding_margin_in_side(self, side):
        """ Move the CodingMargin widget into the left or right container. """

        if side not in ('left', 'right'):
            side = 'left'

        for lay in (self._coding_margin_layout_left, self._coding_margin_layout_right):
            if lay is None:
                continue
            idx = lay.indexOf(self.coding_margin)
            if idx >= 0:
                lay.takeAt(idx)

        if side == 'right':
            self._coding_margin_layout_right.addWidget(self.coding_margin)
        else:
            self._coding_margin_layout_left.addWidget(self.coding_margin)

        self.margin_side = side
        self.coding_margin.side = side

    def _set_margin_container_visibility(self, visible):  # <- L
        """ Show or hide the active container so the layout reclaims its space
        when the margin is turned off. """

        if self.margin_side == 'right':
            self.ui.widget_code_margin_right.setVisible(visible)
            self.ui.widget_code_margin_left.setVisible(False)
        else:
            self.ui.widget_code_margin_left.setVisible(visible)
            self.ui.widget_code_margin_right.setVisible(False)

    def coding_margin_context_menu(self, position, source_widget):  # <- L
        """ Right-click context menu over the CodingMargin widget.
        - If the click hits a code stripe/label: show code actions.
        - Otherwise: show the margin-configuration menu. """

        clicked_code = None
        if isinstance(source_widget, CodingMargin):
            try:
                clicked_code = source_widget._code_at_position(position)
            except Exception as e:
                logger.debug(f"CodingMargin context-menu hit-test error: {e}")
                clicked_code = None

        if clicked_code is not None and self.file_ is not None:
            self._coding_margin_code_actions_menu(clicked_code, source_widget, position)
            return

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")

        if self.show_margin_stripes:
            action_visibility = menu.addAction(_("Hide code stripes margin"))
        else:
            action_visibility = menu.addAction(_("Show code stripes margin"))

        menu.addSeparator()

        action_move_left = None
        action_move_right = None
        if self.margin_side == 'right':
            action_move_left = menu.addAction(_("Move margin to the left"))
        else:
            action_move_right = menu.addAction(_("Move margin to the right"))

        menu.addSeparator()

        style_menu = menu.addMenu(_("Highlight style"))
        action_style_marker = None
        action_style_underline = None
        if self.highlight_style != 'marker':
            action_style_marker = style_menu.addAction(_("Marker"))
        if self.highlight_style != 'underline':
            action_style_underline = style_menu.addAction(_("Underline"))

        global_pos = source_widget.mapToGlobal(position)
        action = menu.exec(global_pos)
        if action is None:
            return

        if action == action_visibility:
            self._toggle_margin_visibility_only()
            return
        if action == action_move_left:
            self._set_margin_side('left')
            return
        if action == action_move_right:
            self._set_margin_side('right')
            return
        if action == action_style_marker:
            self._set_highlight_style('marker')
            return
        if action == action_style_underline:
            self._set_highlight_style('underline')
            return

    def _coding_margin_code_actions_menu(self, code, source_widget, position):  # <- L
        """ Context menu with actions specific to the code clicked in the margin """

        if code is None or self.file_ is None:
            return

        file_start = self.file_.get('start', 0)
        text_len = len(self.ui.plainTextEdit.toPlainText())
        editor_pos = code['pos0'] - file_start
        editor_pos = max(0, min(editor_pos, max(0, text_len - 1)))

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")

        action_unmark = menu.addAction(_("Unmark (U)"))
        action_code_memo = menu.addAction(_("Memo coded text (M)"))
        action_resize = menu.addAction(_("Resize"))
        action_annotate = menu.addAction(_("Annotate (A)"))
        action_change_code = menu.addAction(_("Change code"))

        global_pos = source_widget.mapToGlobal(position)
        action = menu.exec(global_pos)
        if action is None:
            return

        # RRoute to per-ctid variants so every action affects ONLY the
        # exact segment clicked in the margin (no DialogSelectItems re-prompt on
        # overlapping codes). The cursor is still moved for visual feedback <- L
        cursor = self.ui.plainTextEdit.textCursor()
        cursor.setPosition(editor_pos)
        self.ui.plainTextEdit.setTextCursor(cursor)

        if action == action_unmark:
            self._margin_unmark_ctid(code)
            return
        if action == action_code_memo:
            self._margin_coded_text_memo_ctid(code)
            return
        if action == action_resize:
            self._margin_resize_ctid(code)
            return
        if action == action_annotate:
            self._margin_annotate_ctid(code)
            return
        if action == action_change_code:
            self._margin_change_code_ctid(code)
            return

    # Per-ctid action variants used ONLY by the margin code-actions menu.
    # They operate on the exact coded segment clicked in the margin (identified
    # by ctid), without re-prompting via DialogSelectItems when codes overlap <- L
    def _margin_unmark_ctid(self, code):
        """ Unmark the exact coded segment (by ctid) clicked in the margin. """

        if self.file_ is None or code is None or code.get('ctid') is None:
            return
        self.clear_edit_variables()
        # Locate the live item in self.code_text by ctid (deepcopy for undo)
        target = next((c for c in self.code_text if c.get('ctid') == code['ctid']), code)
        self.undo_deleted_codes = deepcopy([target])
        cur = self.app.conn.cursor()
        cur.execute("delete from code_text where ctid=?", [code['ctid']])
        self.app.conn.commit()
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        self.update_file_tooltip()
        self.app.delete_backup = False

    def _margin_coded_text_memo_ctid(self, code):  # <- L
        """ Add/edit memo for the exact coded segment (by ctid) clicked. """

        if self.file_ is None or code is None or code.get('ctid') is None:
            return
        text_item = next((c for c in self.code_text if c.get('ctid') == code['ctid']), None)
        if text_item is None:
            return
        msg = f"{text_item.get('name', '')} [{text_item['pos0']} - {text_item['pos1']}]"
        ui = DialogMemo(self.app, _("Memo for Coded text: ") + msg, text_item['memo'], "show", text_item['seltext'])
        ui.exec()
        memo = ui.memo
        if memo == text_item['memo']:
            return
        cur = self.app.conn.cursor()
        cur.execute("update code_text set memo=? where ctid=?", (memo, text_item['ctid']))
        self.app.conn.commit()
        text_item['memo'] = memo
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def _margin_change_code_ctid(self, code):  # <- L
        """ Change the exact coded segment (by ctid) clicked to another code. """

        if self.file_ is None or code is None or code.get('ctid') is None:
            return
        codes_list = deepcopy(self.codes)
        to_remove = next((c for c in codes_list if c['cid'] == code['cid']), None)
        if to_remove:
            codes_list.remove(to_remove)
        ui = DialogSelectItems(self.app, codes_list, _("Select replacement code"), "single")
        ok = ui.exec()
        if not ok:
            return
        replacement_code = ui.get_selected()
        if not replacement_code:
            return
        cur = self.app.conn.cursor()
        try:
            cur.execute("update code_text set cid=? where ctid=?", [replacement_code['cid'], code['ctid']])
            self.app.conn.commit()
        except sqlite3.IntegrityError:
            pass
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def _margin_annotate_ctid(self, code):  # <- L
        """ Add/edit/remove an annotation over the EXACT range (pos0-pos1) of
        the coded segment clicked in the margin. Mirrors annotate() but is
        bound to the segment's range instead of the editor selection. """

        if self.file_ is None or code is None:
            return
        self.clear_edit_variables()
        pos0 = code['pos0']  # absolute (already includes file offset)
        pos1 = code['pos1']
        # Find an existing annotation overlapping this exact range for this file
        item = None
        details = ""
        for note in self.annotations:
            if note['fid'] == self.file_['id'] and \
                    ((note['pos0'] <= pos0 <= note['pos1']) or (note['pos0'] <= pos1 <= note['pos1'])):
                item = note
                details = f"{item['owner']} {item['date']}"
                break

        # New annotation over the segment range
        if item is None:
            item = {'fid': int(self.file_['id']), 'pos0': pos0, 'pos1': pos1,
                    'memo': "", 'owner': self.app.settings['codername'],
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
                item['anid'] = cur.fetchone()[0]
                self.annotations.append(item)
                self.parent_textEdit.append(_("Annotation added at position: ")
                                            + str(item['pos0']) + "-" + str(item['pos1']) + _(" for: ")
                                            + self.file_['name'])
                self.get_coded_text_update_eventfilter_tooltips()
            return

        # Edit existing annotation
        ui = DialogMemo(self.app, _("Annotation: ") + details, item['memo'])
        ui.exec()
        item['memo'] = ui.memo
        if item['memo'] != "":
            item['date'] = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
            cur = self.app.conn.cursor()
            cur.execute("update annotation set memo=?, date=? where anid=?",
                        (item['memo'], item['date'], item['anid']))
            self.app.conn.commit()
            self.app.delete_backup = False
            self.annotations = self.app.get_annotations()
            self.get_coded_text_update_eventfilter_tooltips()
            return

        # Blank memo -> delete the annotation
        cur = self.app.conn.cursor()
        cur.execute("delete from annotation where anid=?", (item['anid'],))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.annotations = self.app.get_annotations()
        self.parent_textEdit.append(_("Annotation removed from position ")
                                    + str(item['pos0']) + _(" for: ") + self.file_['name'])
        self.get_coded_text_update_eventfilter_tooltips()

    def _margin_resize_ctid(self, code):
        """ Show resize handles bound to the EXACT coded segment (by ctid)
        clicked in the margin, without the DialogSelectItems prompt. """

        if self.file_ is None or code is None or code.get('ctid') is None:
            return
        code_to_handle = next((c for c in self.code_text if c.get('ctid') == code['ctid']), None)
        if code_to_handle is None:
            return
        self.hide_resize_handles()

        # Create start handle
        cursor_start = self.ui.plainTextEdit.textCursor()
        cursor_start.setPosition(max(0, code_to_handle['pos0'] - self.file_['start']))
        rect_start = self.ui.plainTextEdit.cursorRect(cursor_start)
        h_start = CodeResizeHandle(self.ui.plainTextEdit, True, code_to_handle, self)
        # start teardrop tip is at its top-right corner -> shift left by full width
        h_start.move(rect_start.x() - h_start.width(), rect_start.y())
        self.active_handles.append(h_start)

        # Create end handle
        cursor_end = self.ui.plainTextEdit.textCursor()
        cursor_end.setPosition(min(len(self.ui.plainTextEdit.toPlainText()),
                                   code_to_handle['pos1'] - self.file_['start']))
        rect_end = self.ui.plainTextEdit.cursorRect(cursor_end)
        h_end = CodeResizeHandle(self.ui.plainTextEdit, False, code_to_handle, self)
        # end teardrop tip is at its top-left corner -> align directly to the cursor x
        h_end.move(rect_end.x(), rect_end.y())
        self.active_handles.append(h_end)

    def _toggle_margin_visibility_only(self):
        """ Independent visibility toggle (does NOT alter highlight_style). """

        self.show_margin_stripes = not self.show_margin_stripes
        try:
            self.app.settings['codetext_show_margin_stripes'] = (
                'True' if self.show_margin_stripes else 'False')
        except (TypeError, AttributeError):
            pass

        if hasattr(self, 'coding_margin') and self.coding_margin is not None:
            self.coding_margin.setVisible(self.show_margin_stripes)
        self._set_margin_container_visibility(self.show_margin_stripes)

        if hasattr(self, 'coding_margin') and self.coding_margin is not None:
            self.coding_margin.update()

    def _set_margin_side(self, side):  # <- L
        """ Move the coding margin to the requested side and persist. """

        if side not in ('left', 'right'):
            return
        if side == self.margin_side:
            return

        self._install_coding_margin_in_side(side)
        try:
            self.app.settings['codetext_margin_side'] = side
        except (TypeError, AttributeError):
            pass

        self._set_margin_container_visibility(self.show_margin_stripes)

        if hasattr(self, 'coding_margin') and self.coding_margin is not None:
            self.coding_margin.update()

    def _set_highlight_style(self, style):  # <- L
        """ Switch in-text highlight style between 'marker' and 'underline'. """

        if style not in ('marker', 'underline'):
            return
        if style == self.highlight_style:
            return

        self.highlight_style = style
        try:
            self.app.settings['codetext_highlight_style'] = style
        except (TypeError, AttributeError):
            pass

        if self.file_ is not None and self.ui.plainTextEdit.toPlainText() != "":
            self.unlight()
            self.highlight()

    def show_right_side_pane(self):
        """ Toggle visibility of the right side pane (groupBox_info).
        Uses splitter sizes to detect actual visibility, since the widget can be
        visible but collapsed to zero width.
        Remembers the panel size before collapsing and restores it. """

        sizes = self.ui.splitter.sizes()
        if sizes[2] > 5:
            # Remember current size before collapsing
            self.right_pane_size = sizes[2]
            self.ui.splitter.setSizes([sizes[0], sizes[1] + sizes[2], 0])
            self.ui.pushButton_right_side_pane.setIcon(
                qta.icon('mdi6.arrow-expand-left', options=[{'scale_factor': 1.3}]))
        else:
            # Restore previous size
            new_right = self.right_pane_size
            new_center = sizes[1] - new_right if sizes[1] > new_right else sizes[1]
            self.ui.splitter.setSizes([sizes[0], new_center, new_right])
            self.ui.pushButton_right_side_pane.setIcon(
                qta.icon('mdi6.arrow-collapse-right', options=[{'scale_factor': 1.3}]))

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

    def change_document_font(self):
        """ Change document text font and size. """

        tt = self.ui.pushButton_font.toolTip()
        size_and_font = tt.split("\n")[1]
        size, font = size_and_font.split(" ", 1)
        font_ui = DialogFontAndSize(self.app, size, font)
        ok = font_ui.exec()
        if not ok:
            return
        size, font = font_ui.get_size_and_font()
        self.app.settings['docfontsize'] = int(size)
        self.app.settings['docfont'] = font
        doc_font = f'font: {size}pt "{font}";'
        self.ui.plainTextEdit.setStyleSheet(doc_font)
        tt = _("Select document font and size.") + "\n"
        tt += f"{size} {font}"
        self.ui.pushButton_font.setToolTip(tt)

    def find_code_in_tree(self):
        """ Find a code by name in the codes tree and select it. """

        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
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
        matches = []
        while iterator.value():
            item = iterator.value()
            if "cid" in item.text(1):
                cid = int(item.text(1)[4:])
                code_ = next((code_ for code_ in self.codes if code_['cid'] == cid), None)
                if search_text in code_['name']:
                    matches.append(code_)
            iterator += 1
        if not matches:
            Message(self.app, _("Match not found"), _("No code with matching text found.")).exec()
            return

        # Get one selected code from one or more codes.
        selected = None
        if len(matches) > 1:
            ui = DialogSelectItems(self.app, matches, _("Select code"), "single")
            ok = ui.exec()
            if not ok:
                return
            selected = ui.get_selected()
            if not selected:
                return
        else:
            selected = matches[0]

        # Set selected in tree
        item = None
        iterator = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        while iterator.value():
            item = iterator.value()
            if "cid" in item.text(1):
                cid = int(item.text(1)[4:])
                if cid == selected['cid']:
                    self.ui.treeWidget.setCurrentItem(item)
                    break
            iterator += 1

        # Expand parents
        parent = item.parent()
        while parent is not None:
            parent.setExpanded(True)
            parent = parent.parent()

    def get_recent_codes(self):
        """ Get recently used codes. Must have loaded all codes first.
        recent codes are stored as space delimited text in project table.
        Add code id to recent codes list, if code is present. """

        self.recent_codes = []
        cur = self.app.conn.cursor()
        cur.execute("select recently_used_codes from project")
        res = cur.fetchone()
        if not res:
            return
        if res[0] == "" or res[0] is None:
            return
        recent_codes_text = res[0].split()
        for code_id in recent_codes_text:
            try:
                cid = int(code_id)
                for code_ in self.codes:
                    if cid == code_['cid']:
                        self.recent_codes.append(code_)
            except ValueError:
                pass

    def get_collapsed(self, item):
        """ On category collapse or expansion signal, find the collapsed parent category items.
        This will fill the self.app.collapsed_categories and is the expanded/collapsed tree is then replicated across
        other areas of the app. """

        # print(item.text(0), item.text(1), "Expanded:", item.isExpanded())
        if item.text(1)[:3] == "cid":
            return
        if not item.isExpanded() and item.text(1) not in self.app.collapsed_categories:
            self.app.collapsed_categories.append(item.text(1))
        if item.isExpanded() and item.text(1) in self.app.collapsed_categories:
            self.app.collapsed_categories.remove(item.text(1))

    def get_files(self, ids=None, sort="name asc", preserve_current_file: bool = False):
        """ Get files with additional details and fill list widget.
         Called by: init, get_files_from_attributes, show_files_like
         Args:
            ids : list, fill with ids to limit file selection.
            sort : String Sort options, name asc, name, desc, case asc, case desc
            preserve_current_file: Reload the currently displayed file after rebuilding
                the list when it is still present in the filtered result set.
         """

        if ids is None:
            ids = []
        preserved_file = deepcopy(self.file_) if preserve_current_file and self.file_ is not None else None
        selection_model = self.ui.listWidget.selectionModel()
        selection_blocker = QtCore.QSignalBlocker(selection_model) if selection_model is not None else None
        self.ui.listWidget.clear()
        self.files = self.app.get_text_filenames(ids)
        # Fill additional details about each file in the memo
        cur = self.app.conn.cursor()
        sql_length = "select length(fulltext), fulltext from source where id=?"
        sql_codings = "select count(cid) from code_text_visible where fid=?"
        sql_case = "SELECT group_concat(cases.name) from cases join case_text on case_text.caseid=cases.caseid " \
                   "where case_text.fid=?"
        for file_ in self.files:
            cur.execute(sql_length, [file_['id'], ])
            res_length = cur.fetchone()
            if res_length is None:  # Safety catch
                res_length = [0, ""]
            tt = _("Date: ") + file_['date'].split()[0] + "\n"  # Date without timestamp
            cur.execute(sql_case, [file_['id']])
            res_cases = cur.fetchone()
            file_['case'] = ""
            if res_cases and res_cases[0] is not None:
                tt += _("Case: ") + str(res_cases[0]) + "\n"
                file_['case'] = str(res_cases[0])
            tt += _("Characters: ") + str(res_length[0])
            file_['characters'] = res_length[0]
            file_['start'] = 0
            file_['end'] = res_length[0]
            file_['fulltext'] = res_length[1]

            cur.execute(sql_codings, [file_['id']])
            res_codings = cur.fetchone()
            tt += f'\n{_("Codings:")} {res_codings[0]}'
            tt += f"\n{_('From:')} {file_['start']} - {file_['end']}"
            if file_['memo'] != "":
                tt += f"\n{_('Memo')}: {file_['memo']}"

            if file_['risid']:
                ris = Ris(self.app)
                ris.get_references(file_['risid'])
                if ris.refs:
                    reference = ris.refs[0]['vancouver']
                    tt += f"\n{_('REF')}: {reference}"

            file_['tooltip'] = tt

        # Sorting the file list
        if sort == "name asc":
            self.files = sorted(self.files, key=lambda x: x['name'])
        if sort == "name desc":
            self.files = sorted(self.files, key=lambda x: x['name'], reverse=True)
        if sort == "case asc":
            self.files = sorted(self.files, key=lambda x: x['case'])
        if sort == "case desc":
            self.files = sorted(self.files, key=lambda x: x['case'], reverse=True)
        if sort == "date asc":
            self.files = sorted(self.files, key=lambda x: x['date'])
        if sort == "date desc":
            self.files = sorted(self.files, key=lambda x: x['date'], reverse=True)
        # Fill list widget
        for file_ in self.files:
            item = QtWidgets.QListWidgetItem(file_['name'])
            item.setToolTip(file_['tooltip'])
            self.ui.listWidget.addItem(item)
        restored = False
        if preserved_file is not None:
            for file_ in self.files:
                if file_['id'] != preserved_file['id']:
                    continue
                for key in ("start", "end", "start_line"):
                    if key in preserved_file:
                        file_[key] = preserved_file[key]
                self.load_file(file_)
                restored = True
                break
        if not restored:
            self.file_ = None
            self.code_text = []  # Must be before clearing textEdit, as next calls cursorChanged
            self.ui.plainTextEdit.setPlainText("")
        del selection_blocker

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
        file_size = {'characters': res[0], 'start': 0, 'end': res[0], 'fulltext': res[1]}
        sql_codings = "select count(cid) from code_text_visible where fid=?"
        cur.execute(sql_codings, [self.file_['id']])
        res = cur.fetchone()
        tt += f"\n{_('Codings:')} {res[0]}"
        tt += f"\n{_('From:')} {file_size['start']} - {file_size['end']}"
        if self.file_['memo'] != "":
            tt += f"\n{_('Memo')}: {self.file_['memo']}"
        # Find item to update tooltip
        items = self.ui.listWidget.findItems(self.file_['name'], Qt.MatchFlag.MatchExactly)
        if len(items) == 0:
            return
        items[0].setToolTip(tt)

    def get_files_from_attributes(self, refresh_only: bool = False):
        """ Select files based on attribute selections.
        Attribute results are a dictionary of:
        first item is a Boolean AND or OR list item
        Followed by each attribute list item

        Args:
            refresh_only: Recompute an already active attribute filter without reopening
                the selection dialog.
        """

        if refresh_only and len(self.attributes) <= 1:
            return

        # Clear ui
        self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
        ui = DialogSelectAttributeParameters(self.app)
        previous_attributes = deepcopy(self.attributes)
        ui.fill_parameters(deepcopy(self.attributes))
        temp_attributes = deepcopy(self.attributes)
        if refresh_only:
            ui.make_parameter_list()
            ui.get_results_case_ids()
            ui.get_results_file_ids()
            ui.get_results_message()
        else:
            self.attributes = []
            ok = ui.exec()
            if not ok:
                self.attributes = temp_attributes
                self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable', options=[{'scale_factor': 1.3}]))
                self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
                if self.attributes:
                    self.ui.pushButton_file_attributes.setIcon(
                        qta.icon('mdi6.variable-box', options=[{'scale_factor': 1.3}]))
                return
        self.attributes = ui.parameters
        if len(self.attributes) == 1:  # Boolean parameter, no attributes
            if refresh_only and len(previous_attributes) > 1:
                self.clear_file_filter()
                return
            self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable', options=[{'scale_factor': 1.3}]))
            self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
            self.get_files(preserve_current_file=True)
            return
        if not ui.result_file_ids:
            if not refresh_only:
                Message(self.app, _("Nothing found") + " " * 20, _("No matching files found")).exec()
                self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable', options=[{'scale_factor': 1.3}]))
                self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
                return
            selection_model = self.ui.listWidget.selectionModel()
            selection_blocker = QtCore.QSignalBlocker(selection_model) if selection_model is not None else None
            self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable-box', options=[{'scale_factor': 1.3}]))
            self.ui.pushButton_file_attributes.setToolTip(ui.tooltip_msg)
            self.ui.listWidget.clear()
            self.files = []
            self.file_ = None
            self.code_text = []
            self.ui.plainTextEdit.setPlainText("")
            self.ui.pushButton_clear_filter_file.setVisible(True)
            self.ui.pushButton_clear_filter_file.setStyleSheet("background-color: #1e90ff; color: white;")
            del selection_blocker
            return
        self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable-box', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_file_attributes.setToolTip(ui.tooltip_msg)
        self.get_files(ui.result_file_ids, preserve_current_file=True)
        self.ui.pushButton_clear_filter_file.setVisible(True)
        self.ui.pushButton_clear_filter_file.setStyleSheet("background-color: #1e90ff; color: white;")  # blue

    def update_sizes(self):
        """ Called by changed splitter size """

        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogcodetext_splitter0'] = sizes[0]
        self.app.settings['dialogcodetext_splitter1'] = sizes[1]
        # Remember right pane size if it is visible
        if len(sizes) > 2 and sizes[2] > 5:
            self.right_pane_size = sizes[2]
            self.app.settings['dialogcodetext_splitter2'] = sizes[2]
        v_sizes = self.ui.leftsplitter.sizes()
        self.app.settings['dialogcodetext_splitter_v0'] = v_sizes[0]
        self.app.settings['dialogcodetext_splitter_v1'] = v_sizes[1]

    def fill_code_label_with_selected_code(self):
        """ Fill code label with currently selected item's code name and colour.
         Also, if text is highlighted, assign the text to this code.

         Called by: treewidgetitem_clicked """

        current = self.ui.treeWidget.currentItem()
        if current is None:
            return
        # Only update right-hand side splitter if it was already showing code rules <- L
        # Do not overwrite journal or project memo views
        if self.code_rule:
            self.show_code_rule()
        if current.text(1)[0:3] == 'cat':
            style = f"QLabel {{background-color:transparent;}}"
            self.ui.label_code.setStyleSheet(style)
            tooltip = ""
            if self.show_codes_like_filter:
                tooltip = _("Filtered: ") + self.show_codes_like_filter
            if self.show_codes_colour_filter:
                tooltip = _("Filtered: ") + self.show_codes_colour_filter
            self.ui.label_code.setToolTip(tooltip)
            return
        # Set background colour of label to code color, and store current code for underlining
        for c in self.codes:
            if int(current.text(1)[4:]) == c['cid']:
                fg_color = TextColor(c['color']).recommendation
                style = f"QLabel {{background-color:{c['color']}; color: {fg_color};}}"
                self.ui.label_code.setStyleSheet(style)
                self.ui.label_code.setAutoFillBackground(True)
                tooltip = f"{c['name']}\n"
                if c['memo'] != "":
                    tooltip += _("Memo: ") + c['memo']
                if self.show_codes_like_filter:
                    tooltip += "\n" + _("Filtered: ") + self.show_codes_like_filter
                if self.show_codes_colour_filter:
                    tooltip += "\n" + _("Filtered: ") + self.show_codes_colour_filter
                self.ui.label_code.setToolTip(tooltip)
                break
        selected_text = self.ui.plainTextEdit.textCursor().selectedText()
        if len(selected_text) > 0 and not (QtWidgets.QApplication.mouseButtons() & Qt.MouseButton.RightButton):
            self.mark()
        # When a code is selected undo the show selected code features
        self.highlight()
        # Reload button icons as they disappear on Windows
        self.ui.pushButton_show_codings_prev.setIcon(qta.icon('mdi6.arrow-left', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_show_codings_next.setIcon(qta.icon('mdi6.arrow-right', options=[{'scale_factor': 1.3}]))

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes.
        The Count column counts the number of times that code has been used by selected coder in selected file.
        Keep record of non-expanded items, then re-enact these items when treee fill is called again. """

        cats = deepcopy(self.categories)
        codes = deepcopy(self.codes)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(4)
        self.ui.treeWidget.setHeaderLabels([_("Name"), _("Id"), _("Memo"), _("Count")])
        if not self.app.settings['showids']:
            self.ui.treeWidget.setColumnHidden(1, True)
        else:
            self.ui.treeWidget.setColumnHidden(1, False)

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
                self.ui.treeWidget.addTopLevelItem(top_item)
                if f"catid:{c['catid']}" in self.app.collapsed_categories:
                    top_item.setExpanded(False)
                else:
                    top_item.setExpanded(True)
                remove_list.append(c)
        for item in remove_list:
            cats.remove(item)
        ''' Add child categories: place each category under its parent. Break when no progress
         is made (a cycle or a dangling supercatid), then place any leftovers at top level so a
         category branch is never lost or hidden because of corruption. <- L '''
        count = 0
        while cats and count < 10000:
            remove_list = []
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
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
        # Fallback: never lose a category. Any with a missing/cyclic parent goes to top level. <- L
        for c in cats:
            memo = _("Memo") if c['memo'] != "" else ""
            top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
            top_item.setToolTip(2, c['memo'])
            top_item.setToolTip(0, '')
            if len(c['name']) > 52:
                top_item.setText(0, f"{c['name'][:25]}..{c['name'][-25:]}")
                top_item.setToolTip(0, c['name'])
            self.ui.treeWidget.addTopLevelItem(top_item)
        # Add codes, with sub-code nesting. A code is top level only when it has neither a
        # parent category (catid) nor a parent code (supercid). The rest are nested under
        # their category (catid:) or under their parent code (cid:). <- L

        def _make_code_item(code_dict):
            """ Build a styled tree item for a code. Sub-codes share this styling. <- L """
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

        # Index every node already in the tree (categories) by its id text for O(1) lookup. <- L
        node_index = {}
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        while it.value():
            node_index[it.value().text(1)] = it.value()
            it += 1
        # Top level codes: no category and no parent code.
        remove_items = []
        for c in codes:
            if c['catid'] is None and c.get('supercid') is None:
                node = _make_code_item(c)
                self.ui.treeWidget.addTopLevelItem(node)
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
        # Fallback: never lose a code. Any code with a dangling parent goes to top level. <- L
        for c in codes:
            node = _make_code_item(c)
            self.ui.treeWidget.addTopLevelItem(node)
            node_index[f"cid:{c['cid']}"] = node

        if self.tree_sort_option == "all asc":
            self.ui.treeWidget.sortByColumn(0, QtCore.Qt.SortOrder.AscendingOrder)
        if self.tree_sort_option == "all desc":
            self.ui.treeWidget.sortByColumn(0, QtCore.Qt.SortOrder.DescendingOrder)
        # Show the code tree expanded from the start: sub-code branches are visible by default;
        # categories the user had collapsed are restored to their collapsed state. <- L
        self.ui.treeWidget.expandAll()
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        while it.value():
            node = it.value()
            if node.text(1) in self.app.collapsed_categories:
                node.setExpanded(False)
            it += 1
        self.fill_code_counts_in_tree()
        restore_persistent_tree_widths(
            self.ui.treeWidget,
            default_width_factors={0: 0.70, 2: 0.15, 3: 0.15}
        )

    def fill_code_counts_in_tree(self):
        """ Calculate the frequency of each code and category for this coder and the selected file.
        Add a list item to each code that can be used to display in treeWidget.
        If the tab 'AI assisted coding' is active, the codings will be counted
        across all files, not only the currently selected one, because the AI assisted 
        coding is not working on a per-file basis.
        """

        ai_assisted_coding = self.ui.tabWidget.currentIndex() == 1
        if self.file_ is None and not ai_assisted_coding:
            # delete count if no file selected
            iterator = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
            while iterator.value():
                item = iterator.value()
                item.setText(3, '')
                iterator += 1  # Move to the next item
            return

        cur = self.app.conn.cursor()
        code_counts = []
        for c in self.codes:
            parameters = [c['cid']]
            if ai_assisted_coding:
                sql = "select code_name.catid, count(code_text_visible.cid) from code_text_visible join code_name " \
                      "on code_name.cid=code_text_visible.cid where code_text_visible.cid=?"
            else:  # documents
                sql = "select code_name.catid, count(code_text_visible.cid) from code_text_visible join code_name " \
                      "on code_name.cid=code_text_visible.cid where code_text_visible.cid=?" \
                      "and code_text_visible.fid=?"
                parameters.append(self.file_['id'])
            cur.execute(sql, parameters)
            result = cur.fetchone()
            code_counts.append([c['cid'], result[0], result[1]])

        # Sub-code roll-up. Build own counts, the parent/children maps and an effective
        # category for each code (a sub-code is attributed to its top ancestor's category). <- L
        own_count = {cc[0]: cc[2] for cc in code_counts}
        code_by_cid = {c['cid']: c for c in self.codes}
        children_of = {}
        for c in self.codes:
            sup = c.get('supercid')
            if sup is not None:
                children_of.setdefault(sup, []).append(c['cid'])

        def _effective_catid(cid):
            """ Resolve a (possibly nested) code to the catid of its top ancestor code. <- L """
            seen = set()
            cur_c = code_by_cid.get(cid)
            while cur_c is not None and cur_c['cid'] not in seen:
                seen.add(cur_c['cid'])
                if cur_c['catid'] is not None:
                    return cur_c['catid']
                sup_ = cur_c.get('supercid')
                if sup_ is None:
                    return None
                cur_c = code_by_cid.get(sup_)
            return None

        eff_catid = {cc[0]: _effective_catid(cc[0]) for cc in code_counts}
        total_cache = {}

        def _code_total(cid_):
            """ Code count rolled up with all descendant sub-codes. Memoized, cycle-safe.
            Args:
                cid_ : Integer
            """
            if cid_ in total_cache:
                return total_cache[cid_]
            total_cache[cid_] = own_count.get(cid_, 0)  # Seed guards against cycles
            total_count = own_count.get(cid_, 0)
            for child_cid in children_of.get(cid_, []):
                total_count += _code_total(child_cid)
            total_cache[cid_] = total_count
            return total_count

        categories = deepcopy(self.categories)
        # Set up category counts
        for category in categories:
            category['count'] = 0
        # Add each code's own count to its effective category (sub-codes roll up to the
        # category of their top ancestor code, not to a raw catid that is None). <- L
        for category in categories:
            for code in code_counts:
                if eff_catid.get(code[0]) == category['catid']:
                    category['count'] += code[2]
        # Find leaf categories, add to above categories, and gradually remove leaves
        # until only top categories are left
        sub_categories = copy(categories)
        counter = 0
        while len(sub_categories) > 0 or counter < 10000:
            leaf_list = []
            branch_list = []
            for cat in sub_categories:
                for cat2 in sub_categories:
                    if cat['catid'] == cat2['supercatid']:
                        branch_list.append(cat)
            for category in sub_categories:
                if category not in branch_list:
                    leaf_list.append(category)
            # Add totals higher category
            for leaf_category in leaf_list:
                for category in categories:
                    if category['catid'] == leaf_category['supercatid']:
                        category['count'] += leaf_category['count']
                sub_categories.remove(leaf_category)
            counter += 1

        # Fill tree item counts
        iterator = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        while iterator.value():
            item = iterator.value()
            if item.text(1).startswith("catid"):
                catid = int(item.text(1)[6:])
                for category in categories:
                    if catid == category['catid']:
                        item.setText(3, str(category['count']))
            else:
                cid = int(item.text(1)[4:])
                own_n = own_count.get(cid, 0)
                if cid in children_of:
                    total_n = _code_total(cid)
                    item.setText(3, f"{own_n} ({total_n})" if total_n != own_n else str(own_n))
                else:
                    item.setText(3, str(own_n))
            iterator += 1  # Move to the next item

    def tree_item_clicked(self, item, column):
        """ Use to quicky open memo. """

        if column == 2:
            self.add_edit_cat_or_code_memo(item)

    def get_codes_and_categories(self):
        """ Called from init, delete category/code.
        Also called on other coding dialogs in the dialog_list. """

        self.codes, self.categories = self.app.get_codes_categories()

    # Right Hand Side splitter details for code rule, project memo # And Journal <- L
    def show_code_rule(self):
        """ Show text in right-hand side splitter pane. """

        selected = self.ui.treeWidget.currentItem()
        if selected is None:
            return
        self.project_memo = False
        self.code_rule = True
        self.ui.textEdit_info.setReadOnly(True)
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
            cur.execute(
                "select seltext from code_text_visible where length(seltext) > 0 and cid=? order by random() limit 3",
                [int(selected.text(1)[4:])])
            res = cur.fetchall()
            for i, r in enumerate(res):
                txt += f"{i + 1}: {r[0]}\n"
        self.ui.textEdit_info.setReadOnly(True)
        self.ui.textEdit_info.blockSignals(True)
        self.ui.textEdit_info.setText(txt)
        # Add blockSignals around setText in show_code_rule <- L
        self.ui.textEdit_info.blockSignals(False)

    def show_project_memo(self):
        """ Show project memo in right-hand side splitter pane """

        cur = self.app.conn.cursor()
        cur.execute("select memo from project")
        res = cur.fetchone()
        self.project_memo = True
        self.code_rule = False
        self.ui.textEdit_info.setReadOnly(True)
        self.ui.label_info.setText(_("Project memo"))
        self.ui.textEdit_info.blockSignals(True)
        self.ui.textEdit_info.setText(res[0])
        self.ui.textEdit_info.blockSignals(False)
            
    # Header section widgets
    def delete_all_codes_from_file(self):
        """ Delete all codes from this file by this coder. """

        if self.file_ is None:
            return
        msg = _("Delete all codings in this file made by ") + self.app.settings['codername']
        ui = DialogConfirmDelete(self.app, msg)
        ok = ui.exec()
        if not ok:
            return
        cur = self.app.conn.cursor()
        sql = "delete from code_text where fid=? and owner=?"
        cur.execute(sql, (self.file_['id'], self.app.settings['codername']))
        self.app.conn.commit()
        self.get_coded_text_update_eventfilter_tooltips()
        self.app.delete_backup = False
        msg = _("All codes by ") + self.app.settings['codername'] + _(" deleted from ") + self.file_['name']
        self.parent_textEdit.append(msg)

    # Search for text methods
    def search_for_text(self):
        """ Find indices of matching text.
        Resets current search_index.
        If all files is checked then searches for all matching text across all text files
        and displays the file text and current position to user.
        If case-sensitive is checked then text searched is matched for case sensitivity.
        search_type start search options 3,or 5 chars.
        Enter pressed is also a search option.
        """

        if self.file_ is None:
            return
        if not self.search_indices:
            self.ui.pushButton_next.setEnabled(False)
            self.ui.pushButton_previous.setEnabled(False)
        self.search_indices = []
        self.search_index = -1
        self.search_term = self.ui.lineEdit_search.text()
        if self.search_threshold == 3 and len(self.search_term) < 3:
            self.ui.label_search_totals.setText("")
            return
        if self.search_threshold == 5 and len(self.search_term) < 5:
            self.ui.label_search_totals.setText("")
            return
        self.ui.label_search_totals.setText("0 / 0")
        pattern = None
        flags = 0
        if not self.ui.checkBox_search_case.isChecked():
            flags |= re.IGNORECASE
        try:
            pattern = re.compile(self.search_term, flags)
        except re.error as e_:
            logger.warning('re error Bad escape ' + str(e_))
        if pattern is None:
            return
        self.search_indices = []
        if self.ui.checkBox_search_all_files.isChecked():
            """ Search for this text across all files. """
            # print("searching all files")
            for filedata in self.app.get_file_texts():
                try:
                    text_ = filedata['fulltext']
                    for match in pattern.finditer(text_):
                        self.search_indices.append((filedata, match.start(), len(match.group(0))))
                except re.error:
                    logger.exception('Failed searching text %s for %s', filedata['name'], self.search_term)
        else:
            # print("searching 1 file", self.file_['name'])
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
        self.ui.label_search_totals.setText(f"0 / {len(self.search_indices)}")

    def move_to_next_search_text(self):
        """ Push button pressed to move to next search text position. """

        if self.file_ is None or self.search_indices == []:
            return
        self.search_term = self.ui.lineEdit_search.text()
        if self.search_threshold == 3 and len(self.search_term) < 3:
            self.ui.label_search_totals.setText("")
            self.search_indices = []
            self.search_index = 0
            return
        if self.search_threshold == 5 and len(self.search_term) < 5:
            self.ui.label_search_totals.setText("")
            self.search_indices = []
            self.search_index = 0
            return
        self.search_index += 1
        if self.search_index >= len(self.search_indices):
            self.search_index = 0
        cursor = self.ui.plainTextEdit.textCursor()
        next_result = self.search_indices[self.search_index]
        # next_result is a tuple containing a dictionary of
        # ({name, id, fullltext, memo, owner, date}, char position, search string length)
        if self.file_ is None or self.file_['id'] != next_result[0]['id']:
            for x in range(self.ui.listWidget.count()):
                if self.ui.listWidget.item(x).text() == next_result[0]['name']:
                    self.ui.listWidget.blockSignals(True)
                    self.ui.listWidget.setCurrentRow(x)
                    self.ui.listWidget.blockSignals(False)
            self.load_file(next_result[0])
            self.ui.lineEdit_search.setText(self.search_term)
        cursor.setPosition(cursor.position() + next_result[2])
        self.ui.plainTextEdit.setTextCursor(cursor)
        # Highlight selected text
        cursor.setPosition(next_result[1])
        cursor.setPosition(cursor.position() + next_result[2], QtGui.QTextCursor.MoveMode.KeepAnchor)
        self.ui.plainTextEdit.setTextCursor(cursor)
        self.ui.label_search_totals.setText(f"{self.search_index + 1} / {len(self.search_indices)}")
        self.scroll_text_into_view()

    def move_to_previous_search_text(self):
        """ Push button pressed to move to previous search text position. """

        if self.file_ is None or self.search_indices == []:
            return
        self.search_term = self.ui.lineEdit_search.text()
        if self.search_threshold == 3 and len(self.search_term) < 3:
            self.ui.label_search_totals.setText("")
            self.search_indices = []
            self.search_index = 0
            return
        if self.search_threshold == 5 and len(self.search_term) < 5:
            self.ui.label_search_totals.setText("")
            self.search_indices = []
            self.search_index = 0
            return
        self.search_index -= 1
        if self.search_index < 0:
            self.search_index = len(self.search_indices) - 1
        cursor = self.ui.plainTextEdit.textCursor()
        prev_result = self.search_indices[self.search_index]
        # prev_result is a tuple containing a dictionary of
        # (name, id, fullltext, memo, owner, date) and char position and search string length
        if self.file_ is None or self.file_['id'] != prev_result[0]['id']:
            self.load_file(prev_result[0])
            self.ui.lineEdit_search.setText(self.search_term)
        cursor.setPosition(prev_result[1])
        cursor.setPosition(cursor.position() + prev_result[2], QtGui.QTextCursor.MoveMode.KeepAnchor)
        self.ui.plainTextEdit.setTextCursor(cursor)
        self.ui.label_search_totals.setText(f"{self.search_index + 1} / {len(self.search_indices)}")
        self.scroll_text_into_view()

    def lineedit_search_menu(self, position):
        """ Option to change from automatic search on 3 characters or 5 character to search.
         Enter is alway a search option. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        action_char3 = QtGui.QAction(_("Automatic search 3 or more characters"))
        action_char5 = QtGui.QAction(_("Automatic search 5 or more characters"))
        if self.search_threshold != 3:
            menu.addAction(action_char3)
        if self.search_threshold != 5:
            menu.addAction(action_char5)
        action = menu.exec(self.ui.lineEdit_search.mapToGlobal(position))
        if action is None:
            return
        if action == action_char3:
            self.search_threshold = 3
            self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
            return
        if action == action_char5:
            self.search_threshold = 5
            self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
            return

    def button_auto_code_menu(self, position):
        """ Options to auto-code all instances, first instance or last instance in a file.
        For Exact text matches. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        msg = ""
        if self.autocode_all_first_last_within == "all":
            msg = " *"
        else:
            msg = ""
        action_all = QtGui.QAction(_("all matches in file") + msg)
        if self.autocode_all_first_last_within == "first":
            msg = " *"
        else:
            msg = ""
        action_first = QtGui.QAction(_("first match in file") + msg)
        if self.autocode_all_first_last_within == "last":
            msg = " *"
        else:
            msg = ""
        action_last = QtGui.QAction(_("last match in file") + msg)
        if self.autocode_all_first_last_within.startswith("code_within_code "):
            msg = f" * cid:{self.autocode_all_first_last_within.split(' ')[1]}"
        else:
            msg = ""
        action_code_within_code = QtGui.QAction(_("code within code") + msg)
        menu.addAction(action_all)
        menu.addAction(action_first)
        menu.addAction(action_last)
        menu.addAction(action_code_within_code)
        action = menu.exec(self.ui.pushButton_auto_code.mapToGlobal(position))
        if action is None:
            return
        if action == action_all:
            self.autocode_all_first_last_within = "all"
        if action == action_first:
            self.autocode_all_first_last_within = "first"
        if action == action_last:
            self.autocode_all_first_last_within = "last"
        if action == action_code_within_code:
            ui = DialogSelectItems(self.app, self.codes, _("Select code"), "single")
            ok = ui.exec()
            if not ok:
                return
            code_ = ui.get_selected()
            if not code_:
                return
            self.autocode_all_first_last_within = f"code_within_code {code_['cid']}"

    def button_auto_code_frag_menu(self, position):
        """ Options to auto-code all instances, first instance or last instance in a file.
        For fragments of a sentence to code the full sentence. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        msg = ""
        if self.autocode_frag_all_first_within == "all":
            msg = " *"
        else:
            msg = ""
        action_all = QtGui.QAction(_("all matches in file") + msg)
        if self.autocode_frag_all_first_within == "first":
            msg = " *"
        else:
            msg = ""
        action_first = QtGui.QAction(_("first match in file") + msg)
        if self.autocode_frag_all_first_within == "last":
            msg = " *"
        else:
            msg = ""
        if self.autocode_frag_all_first_within.startswith("code_within_code "):
            msg = f" * cid:{self.autocode_frag_all_first_within.split(' ')[1]}"
        else:
            msg = ""
        action_code_within_code = QtGui.QAction(_("code within code") + msg)
        menu.addAction(action_all)
        menu.addAction(action_first)
        menu.addAction(action_code_within_code)
        action = menu.exec(self.ui.pushButton_auto_code.mapToGlobal(position))
        if action is None:
            return
        if action == action_all:
            self.autocode_frag_all_first_within = "all"
        if action == action_first:
            self.autocode_frag_all_first_within = "first"
        if action == action_code_within_code:
            ui = DialogSelectItems(self.app, self.codes, _("Select code"), "single")
            ok = ui.exec()
            if not ok:
                return
            code_ = ui.get_selected()
            if not code_:
                return
            self.autocode_frag_all_first_within = f"code_within_code {code_['cid']}"

    def text_edit_recent_codes_menu(self, position):
        """ Alternative context menu.
        Shows a list of recent codes to select from.
        Called by R key press in the text edit pane, only if there is some selected text.
        Add """

        if self.ui.plainTextEdit.toPlainText() == "":
            return
        selected_text = self.ui.plainTextEdit.textCursor().selectedText()
        if selected_text == "":
            return
        if len(self.recent_codes) == 0:
            return
        menu = QtWidgets.QMenu()
        for i, item in enumerate(self.recent_codes):
            menu.addAction(item['name'] + f' &{i + 1}')
        action = menu.exec(self.ui.plainTextEdit.mapToGlobal(position))
        if action is None:
            return
        # Remaining actions will be the submenu codes
        self.recursive_set_current_item(self.ui.treeWidget.invisibleRootItem(), action.text()[:-3])
        self.mark()

    def text_edit_menu(self, position):
        """ Context menu for textEdit.
        Mark, unmark, annotate, copy, memo coded, coded importance. """

        if self.ui.plainTextEdit.toPlainText() == "" or self.edit_mode:
            return
        cursor = self.ui.plainTextEdit.cursorForPosition(position)
        selected_text = self.ui.plainTextEdit.textCursor().selectedText()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"font-size:{self.app.settings['fontsize']}pt")
        menu.setToolTipsVisible(True)
        action_code_memo = None
        action_edit_annotate = None
        action_important = None
        action_mark = None
        action_not_important = None
        action_change_code = None
        action_unmark = None
        action_new_code = None
        action_new_invivo_code = None
        submenu_ai_text_analysis = None  # ? Not used
        action_show_handles = None

        # Can have multiple coded text at this position
        for item in self.code_text:
            if cursor.position() + self.file_['start'] >= item['pos0'] and cursor.position() <= item['pos1']:
                action_unmark = QtGui.QAction(_("Unmark (U)"))
                action_code_memo = QtGui.QAction(_("Memo coded text (M)"))
                # removed action_start_pos, action_end_pos, action_change_pos <- L
                if item['important'] is None or item['important'] > 1:
                    action_important = QtGui.QAction(_("Add important mark (I)"))
                if item['important'] == 1:
                    action_not_important = QtGui.QAction(_("Remove important mark"))
                action_change_code = QtGui.QAction(_("Change code"))
                action_show_handles = QtGui.QAction(_("Resize"))
        if selected_text != "":
            if self.ui.treeWidget.currentItem() is not None:
                action_mark = menu.addAction(_("Mark (Q)"))
            # Use up to 10 recent codes
            if len(self.recent_codes) > 0:
                submenu = menu.addMenu(_("Mark with recent code (R)"))
                for item in self.recent_codes:
                    submenu.addAction(item['name'])
            action_new_code = menu.addAction(_("Mark with new code (N)"))
            action_new_invivo_code = menu.addAction(_("in vivo code (V)"))

        if action_unmark:
            menu.addAction(action_unmark)
        if action_code_memo:
            menu.addAction(action_code_memo)
        if action_important:
            menu.addAction(action_important)
        if action_not_important:
            menu.addAction(action_not_important)
        if action_change_code:
            menu.addAction(action_change_code)
        if action_show_handles:
            menu.addAction(action_show_handles)

        action_annotate = menu.addAction(_("Annotate (A)"))
        action_copy = menu.addAction(_("Copy to clipboard"))
        action_copy_metadata = menu.addAction(_("Copy with metadata"))
        if selected_text == "" and self.is_annotated(cursor.position()):
            action_edit_annotate = menu.addAction(_("Edit annotation"))
        action_set_bookmark = menu.addAction(_("Set bookmark (B)"))
        if selected_text != "":
            submenu_ai_text_analysis = menu.addMenu(_("AI Text Analysis"))
            submenu_ai_text_analysis.setToolTipsVisible(True)
            if self._ai_menu_options_enabled():
                submenu_ai_text_analysis.setEnabled(True)
                prompts_catalog = AiAgentPromptsCatalog(self.app)
                prompt_records = prompts_catalog.list_visible_prompt_variants(prompt_type='text_analysis')
                self._populate_text_analysis_prompt_menu(submenu_ai_text_analysis, prompts_catalog, prompt_records)
                if len(prompt_records) > 0:
                    submenu_ai_text_analysis.addSeparator()
                ac = submenu_ai_text_analysis.addAction(_('Edit text analysis prompts'))
                ac.setProperty('submenu', 'ai_text_analysis_prompts')
            else:
                submenu_ai_text_analysis.setEnabled(False)
        action_hide_top_groupbox = None
        action_show_top_groupbox = None
        if self.ui.groupBox.isHidden():
            action_show_top_groupbox = menu.addAction(_("Show control panel (H)"))
        if not self.ui.groupBox.isHidden():
            action_hide_top_groupbox = menu.addAction(_("Hide control panel (H)"))

        action = menu.exec(self.ui.plainTextEdit.mapToGlobal(position))
        if action is None:
            return
        if action == action_important:
            self.set_important(cursor.position())
            return
        if action == action_not_important:
            self.set_important(cursor.position(), False)
            return
        if selected_text != "" and action == action_copy:
            self.copy_selected_text_to_clipboard(False)
            return
        if selected_text != "" and action == action_copy_metadata:
            self.copy_selected_text_to_clipboard(True)
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
        if action == action_set_bookmark:
            cur = self.app.conn.cursor()
            bookmark_pos = cursor.position() + self.file_['start']
            cur.execute("update project set bookmarkfile=?, bookmarkpos=?", [self.file_['id'], bookmark_pos])
            self.app.conn.commit()
            return
        if action == action_change_code:
            self.change_code_to_another_code(cursor.position())
            return
        # ---  handles experimental
        if action == action_show_handles:
            self.display_handles_for_code(cursor.position())
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
        if action.property('submenu') == 'ai_text_analysis':
            if self.file_ is None:
                Message(self.app, _('Warning'), _("No file was selected"), "warning").exec()
                return
            selected_text = self.ui.plainTextEdit.textCursor().selectedText()
            start_pos = self.ui.plainTextEdit.textCursor().selectionStart() + self.file_['start']
            ai_chat_signal_emitter.newTextChatSignal.emit(int(self.file_['id']),
                                                          self.file_['name'],
                                                          selected_text,
                                                          start_pos,
                                                          action.data())
            return
        if action.property('submenu') == 'ai_text_analysis_prompts':
            DialogAiEditPrompts(self.app, 'text_analysis').exec()
            return
        # Remaining actions will be the submenu codes
        self.recursive_set_current_item(self.ui.treeWidget.invisibleRootItem(), action.text())
        self.mark()

    def mark_with_new_code(self, in_vivo: bool = False):
        """ Create new code. If text selected, mark selected text.
        Called through text_edit_menu or N key press - with selected text.
        Args:
            in_vivo : Boolean if True use in vivo text selection as code name """

        # Get selected category, if any
        tree_item = self.ui.treeWidget.currentItem()
        catid = None
        if tree_item is not None and tree_item.text(1)[0:3] == 'cat':
            catid = int(tree_item.text(1)[6:])
        codes_copy = deepcopy(self.codes)
        if not in_vivo:
            self.add_code(catid)
        else:
            self.add_code(catid, code_name=self.ui.plainTextEdit.textCursor().selectedText())
        new_code = None
        for c in self.codes:
            if c not in codes_copy:
                new_code = c
        if new_code is None and not in_vivo:
            # Not a new code and not an in vivo coding
            return
        if new_code is None and in_vivo:
            # Find existing code name that matches in vivo selection
            new_code = None
            for c in self.codes:
                if c['name'] == self.ui.plainTextEdit.textCursor().selectedText():
                    new_code = c
        self.recursive_set_current_item(self.ui.treeWidget.invisibleRootItem(), new_code['name'])
        self.mark()

    def change_code_to_another_code(self, position: int):
        """ Change code to another code.
        Args:
            position: Integer - text cursor position
        """

        # Get coded segments at this position
        if self.file_ is None:
            return
        coded_text_list = []
        for item in self.code_text:
            if item['pos0'] <= position + self.file_['start'] <= item['pos1']:
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
        replacement_code = ui.get_selected()
        if not replacement_code:
            return
        cur = self.app.conn.cursor()
        sql = "update code_text set cid=? where ctid=?"
        try:
            cur.execute(sql, [replacement_code['cid'], text_item['ctid']])
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
        Args:
            item : QTreeWidgetItem - usually root
            text_ : String
        """

        child_count = item.childCount()
        for i in range(child_count):
            if item.child(i).text(1)[0:3] == "cid" and (item.child(i).text(0) == text_
                                                        or item.child(i).toolTip(0) == text_):
                self.ui.treeWidget.setCurrentItem(item.child(i))
            self.recursive_set_current_item(item.child(i), text_)

    def is_annotated(self, position: int):
        """ Check if position is annotated to provide annotation menu option.
        Args:
            position: Integer - location in text document
        Returns:
            True or False
        """

        for note in self.annotations:
            if (note['pos0'] <= position + self.file_['start'] <= note['pos1']) \
                    and note['fid'] == self.file_['id']:
                return True
        return False

    def set_important(self, position: int, important: bool = True):
        """ Set or unset importance to coded text.
        Importance is denoted using '1'
        Args:
            position: textEdit character cursor position
            important: boolean, default True """

        # Need to get coded segments at this position
        if position is None:
            # Called via button
            position = self.ui.plainTextEdit.textCursor().position()
        if self.file_ is None:
            return
        coded_text_list = []
        for item in self.code_text:
            if item['pos0'] <= position + self.file_['start'] <= item['pos1'] and \
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

    def active_file_memo(self):
        """ Send active file to file_memo method.
        Called by pushButton_document_memo for loaded text.
        """

        self.file_memo(self.file_)

    def file_memo(self, file_):
        """ Open file memo to view or edit.
        Called by pushButton_document_memo for loaded text, via active_file_memo
        and through file_menu for any file.
        Args:
            file_ : Dictionary of file values
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
        items = self.ui.listWidget.findItems(file_['name'], Qt.MatchFlag.MatchExactly)
        if len(items) == 1:
            tt = items[0].toolTip()
            memo_pos = (tt.find(_("Memo:")))
            new_tt = f"{tt[:memo_pos]} {_('Memo:')} {file_['memo']}"
            items[0].setToolTip(new_tt)
        self.app.delete_backup = False

    def coded_text_memo(self, position:None|int=None):
        """ Add or edit a memo for this coded text.
        Args:
            position : Current text cursor position
        """

        if position is None:
            # Called via button
            position = self.ui.plainTextEdit.textCursor().position()
        if self.file_ is None:
            return
        coded_text_list = []
        for item in self.code_text:
            if item['pos0'] <= position + self.file_['start'] <= item['pos1']:
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
        msg = f"{text_item['name']} [{text_item['pos0']} - {text_item['pos1']}]"
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
                    and text_item['owner'] == i['owner']:
                i['memo'] = memo
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def shift_code_positions(self, position: int):
        """ After a text file is edited - text added or deleted, code positions may be inaccurate.
         enter a positive or negative integer to shift code positions for all codes after a click position in the
         document.
         Activated by ^ At key press
         Args:
            position : Integer - location  in text, characters
         """

        if self.file_ is None:
            return
        code_list = []
        for item in self.code_text:
            if item['pos0'] > position + self.file_['start']:
                code_list.append(item)
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
        delta_shift, ok = int_dialog.getInt(self, msg, msg2, 0, -500, 500, 1)
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
            # print(coded['seltext'], coded['pos0'], coded['pos1'])
            new_pos0 = coded['pos0'] + delta_shift
            new_pos1 = coded['pos1'] + delta_shift
            # Get seltext and update if coded pos0 and pos1 are within bounds
            if new_pos0 > -1 and new_pos1 < fulltext_length:
                cur.execute(text_sql, [new_pos0, new_pos1 - new_pos0, self.file_['id']])
                seltext = cur.fetchone()[0]
                # print("len", fulltext_length, seltext)
                sql = "update code_text set pos0=?, pos1=?, seltext=? where ctid=?"
                cur.execute(sql, [new_pos0, new_pos1, seltext, coded['ctid']])
                self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def copy_selected_text_to_clipboard(self, metadata: bool = False):
        """ Copy text to clipboard for external use.
        For example adding text to another document.
        Args:
            metadata : Bool.
        """

        text = self.ui.plainTextEdit.textCursor().selectedText()
        if metadata:
            start_pos = self.ui.plainTextEdit.textCursor().selectionStart() + self.file_['start']
            end_pos = self.ui.plainTextEdit.textCursor().selectionEnd() + self.file_['start']
            text += f"\nFile: {self.file_['name']} [{start_pos} - {end_pos}] "
            codes = ""
            for coded in self.code_text:
                if coded['pos0'] <= start_pos <= coded['pos1'] or coded['pos0'] <= end_pos <= coded['pos1'] or \
                        (start_pos <= coded['pos0'] and coded['pos1'] <= end_pos):
                    codes += f"{coded['name']}; "
            if codes:
                text += f"\nCodes: {codes}"
            # Add reference, if any
            cur = self.app.conn.cursor()
            cur.execute("select risid from source where source.id=?", [self.file_['id']])
            print(self.file_['id'])
            ris_res = cur.fetchone()
            print("ris_res", ris_res)
            if ris_res[0]:
                ris = Ris(self.app)
                ris.get_references(ris_res[0])
                if ris.refs:
                    text += "\n" + _("Reference: ") + ris.refs[0]['apa']
        cb = QtWidgets.QApplication.clipboard()
        cb.setText(text)

    def tree_menu(self, position):
        """ Context menu for treewidget code/category items.
        Add, rename, memo, move or delete code or category. Change code color.
        Assign selected text to current hovered code. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        selected = self.ui.treeWidget.currentItem()
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
            action_add_subcode = menu.addAction(_("Add a new sub-code to code"))  # <- L
        action_cat_show_coded_files = None
        if selected is not None and selected.text(1)[0:3] == 'cat':
            action_expand_collapse = menu.addAction(_("Expand or collapse branch"))
            action_cat_show_coded_files = menu.addAction(_("Show coded files"))
        if selected is not None and selected.text(1)[0:3] == 'cid' and selected.childCount() > 0:
            action_expand_collapse = menu.addAction(_("Expand or collapse branch"))  # <- L
        modify_menu = menu.addMenu(_("Modify"))
        action_rename = modify_menu.addAction(_("Rename F2"))
        action_edit_memo = modify_menu.addAction(_("View or edit memo"))
        action_merge_category = None
        action_move_category = None
        if selected is not None and selected.text(1)[0:3] == 'cat':
            action_merge_category = modify_menu.addAction(_("Merge category into category"))
            action_move_category = modify_menu.addAction(_("Move category under category"))
        action_delete = modify_menu.addAction(_("Delete"))
        action_color = None
        action_show_coded_media = None
        action_move_code = None
        action_move_multi_codes = None
        action_merge_code_into_code = None
        if selected is not None and selected.text(1)[0:3] == 'cid':
            action_color = modify_menu.addAction(_("Change code color"))
            action_show_coded_media = menu.addAction(_("Show coded files"))
            action_move_code = modify_menu.addAction(_("Move code to"))
            action_move_multi_codes = modify_menu.addAction(_("Move multiple codes"))
            action_merge_code_into_code = modify_menu.addAction(_("Merge code into code"))  # <- L
        filter_menu = menu.addMenu(_("Filter"))
        action_show_codes_like = filter_menu.addAction(_("Show codes like") + ": " + self.show_codes_like_filter)
        action_show_codes_colour = filter_menu.addAction(_("Show codes of colour") + f": {self.show_codes_colour_filter}")
        sort_menu = menu.addMenu(_("Sort"))
        action_all_asc = sort_menu.addAction(_("Sort ascending"))
        action_all_desc = sort_menu.addAction(_("Sort descending"))
        action_cat_then_code_asc = sort_menu.addAction(_("Sort category then code ascending"))

        action = menu.exec(self.ui.treeWidget.mapToGlobal(position))
        if action is not None:
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
                return
            if action == action_show_codes_colour:
                self.show_codes_of_color()
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
                supercid = int(selected.text(1).split(":")[1])  # <- L
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
                self.merge_code_into_code(selected)  # <- L
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
                self.delete_category_or_code(selected)
            if action == action_cat_show_coded_files:
                branch_codes = self.recursive_get_branch_codes(selected, [])
                DialogCodeInAllFiles(self.app, branch_codes, "File", selected.text(0))
                self.get_coded_text_update_eventfilter_tooltips()
                return
            if selected is not None and action == action_show_coded_media:
                to_find = int(selected.text(1)[4:])
                found = next((code for code in self.codes if code['cid'] == to_find), None)
                if found:
                    DialogCodeInAllFiles(self.app, found)
                    self.get_coded_text_update_eventfilter_tooltips()

    def recursive_get_branch_codes(self, item, branch_codes):
        """ Set all children of this item to be expanded or collapsed.
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
                self.recursive_get_branch_codes(item.child(i), branch_codes)  # also gather sub-codes nested under this code (supercid) <- L
            if item.child(i).text(1)[0:3] == "cat":
                self.recursive_get_branch_codes(item.child(i), branch_codes)
        return branch_codes

    def recursive_expand_collapse_branch(self, item, expand_toggle: bool):
        """ Set all children of this item to be expanded or collapsed.
        Recurse through all child categories.
        Args:
            item: QTreeWidgetItem
            expand_toggle: boolean
        """

        child_count = item.childCount()
        for i in range(child_count):
            item.setExpanded(expand_toggle)
            self.recursive_expand_collapse_branch(item.child(i), expand_toggle)

    def recursive_non_merge_item(self, item, no_merge_list):
        """ Find matching item to be the current selected item.
        Recurse through any child categories.
        Tried to use QTreeWidget.finditems - but this did not find matching item text
        Called by: textEdit recent codes menu option
        Required for: merge_category()
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

    def move_category(self, catid: int):
        """ Select another category to move this category underneath.
        Args:
            catid : Integer category identifier
        """

        do_not_merge_list = []
        do_not_merge_list = self.recursive_non_merge_item(self.ui.treeWidget.currentItem(), do_not_merge_list)
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
        ui = DialogSelectItems(self.app, category_list, _("Select blank or category"), "single")
        ok = ui.exec()
        if not ok:
            return
        category = ui.get_selected()
        current_cat_name = self.ui.treeWidget.currentItem().text(0)
        if category['name'] == '':
            cur.execute("update code_cat set supercatid=Null where catid=?", [catid])
            self.app.conn.commit()
            self.parent_textEdit.append(_("Moved category: ") + current_cat_name + " → Top level")
        else:
            cur.execute("update code_cat set supercatid=? where catid=?", [category['catid'], catid])
            self.app.conn.commit()
            self.parent_textEdit.append(_("Moved category: ") + current_cat_name + " → " + category['name'])
        self.update_dialog_codes_and_categories()

    def merge_category(self, catid: int):
        """ Select another category to merge this category into.
        Args:
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
            # Always record merge info in target category memo  <- L
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
            print(e_)
            self.app.conn.rollback()  # Revert all changes
            self.update_dialog_codes_and_categories()
            raise
        self.update_dialog_codes_and_categories(["code_cat", "code_name"])

    def move_multiple_codes(self):
        """ Move multiple codes to another category. """

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
        self.update_dialog_codes_and_categories(["code_name"])

    def move_code(self, selected):
        """ Move code to another category, or code or to none (top level).
        Uses a list selection which represents the codes tree.
        Args:
            selected : QTreeWidgetItem
         """

        items_list = [{'name': " ", 'catid': -1, 'cid': -1}]  # Default blank item
        iterator = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        while iterator.value():
            can_append = True
            item = iterator.value()
            depth = 0
            current = item
            # Get depth and if circular reference present
            while current.parent() is not None:
                if current.text(1) == selected.text(1):
                    can_append = False
                current = current.parent()
                depth += 1
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
            iterator +=1
        ui = DialogSelectItems(self.app, items_list, _("Select blank or category or code"), "single")
        ok = ui.exec()
        if not ok:
            return
        destination = ui.get_selected()
        #print(destination)
        selected_cid = int(selected.text(1)[4:])
        cur = self.app.conn.cursor()
        if destination['catid'] == -1 and destination['cid'] == -1:  # move to top level
            cur.execute("update code_name set catid=null, supercid=null where cid=?", [selected_cid])
        elif destination['cid'] > 0:  # Move under another code
            cur.execute("update code_name set catid=null, supercid=? where cid=?", [destination['cid'], selected_cid])
        else:  # Move under a category
            cur.execute("update code_name set catid=?, supercid=null where cid=?", [destination['catid'], selected_cid])
        self.app.conn.commit()
        self.update_dialog_codes_and_categories(["code_name"])

    def show_memos(self):
        """ Show all memos for coded text in dialog. """

        if self.file_ is None:
            return
        text_ = ""
        cur = self.app.conn.cursor()
        sql = "select code_name.name, pos0,pos1, seltext, code_text_visible.memo, code_text_visible.owner "
        sql += "from code_text_visible join code_name on code_text_visible.cid = code_name.cid "
        sql += "where length(code_text_visible.memo)>0 and fid=? order by pos0"
        cur.execute(sql, [self.file_['id']])
        res = cur.fetchall()
        if not res:
            return
        for r in res:
            text_ += f'[{r[1]}-{r[2]}] ' + _("Code: ") + f'{r[0]}'
            text_ += " (" + r[5] + ")\n"  # coder/owner
            text_ += _("Text: ") + f"{r[3]}\n"
            text_ += _("Memo: ") + f"{r[4]}\n\n"
        ui = DialogMemo(self.app, _("Memos for file: ") + self.file_['name'], text_)
        ui.ui.pushButton_clear.hide()
        ui.ui.textEdit.setReadOnly(True)
        ui.exec()

    def show_annotations(self):
        """ Show all annotations for text in dialog. """

        if self.file_ is None:
            return
        text_ = ""
        cur = self.app.conn.cursor()
        sql = "select substr(source.fulltext,pos0+1 ,pos1-pos0), pos0, pos1, annotation_visible.memo "
        sql += "from annotation_visible join source on annotation_visible.fid = source.id "
        sql += "where fid=? order by pos0"
        cur.execute(sql, [self.file_['id']])
        res = cur.fetchall()
        if not res:
            return
        for r in res:
            text_ += f"[{r[1]}-{r[2]}] \n"
            text_ += _("Text: ") + f"{r[0]}\n"
            text_ += _("Annotation: ") + r[3] + "\n\n"
        ui = DialogMemo(self.app, _("Annotations for file: ") + self.file_['name'], text_)
        ui.ui.pushButton_clear.hide()
        ui.ui.textEdit.setReadOnly(True)
        ui.exec()

    def show_important_coded(self):
        """ Show codes flagged as important. """

        self.important = not self.important
        if self.important:
            self.ui.pushButton_important.setToolTip(_("Showing important codings"))
            self.ui.pushButton_important.setIcon(qta.icon('mdi6.star'))
        else:
            self.ui.pushButton_important.setToolTip(_("Show codings flagged important"))
            self.ui.pushButton_important.setIcon(qta.icon('mdi6.star-outline'))
        self.get_coded_text_update_eventfilter_tooltips()

    def show_codes_like(self, preset:str|None=None):
        """ Show all codes if text is empty.
         Show selected codes that contain entered text.
         The input dialog is too narrow, so it is re-created.
         Args:
             preset: None of called from tree_menu, or a string value if called from filer_code_text line edit
        """

        case_sensitive = True
        if preset is None:
            dialog = QtWidgets.QDialog(None)
            dialog.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
            dialog.setWindowTitle(_("Show some codes"))
            dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
            dlg_text = _("Show codes containing the text. (Blank for all)") + "\n"
            if self.show_codes_like_filter:
                dlg_text += _("Filter: ") + self.show_codes_like_filter
            lbl = QtWidgets.QLabel(dlg_text)
            line = QtWidgets.QLineEdit()
            chkbox = QtWidgets.QCheckBox(_("Case sensitive"))
            btnbox = QtWidgets.QDialogButtonBox()
            btnbox.setStandardButtons(QtWidgets.QDialogButtonBox.StandardButton.Ok|QtWidgets.QDialogButtonBox.StandardButton.Cancel)
            layout = QtWidgets.QVBoxLayout()
            layout.addWidget(lbl)
            layout.addWidget(chkbox)
            layout.addWidget(line)
            layout.addWidget(btnbox)
            dialog.setLayout(layout)
            btnbox.rejected.connect(dialog.reject)
            btnbox.accepted.connect(dialog.accept)
            dialog.resize(200, 60)
            ok = dialog.exec()
            if not ok:
                return
            self.show_codes_colour_filter = ""
            case_sensitive = chkbox.isChecked()
            self.show_codes_like_filter = line.text()
        else:
            self.show_codes_like_filter = preset

        root = self.ui.treeWidget.invisibleRootItem()
        self.recursive_traverse(root, "")  # Show all codes in tree
        root = self.ui.treeWidget.invisibleRootItem()
        self.recursive_traverse(root, self.show_codes_like_filter, case_sensitive)
        if self.show_codes_like_filter == "":
            self.ui.label_code.setPixmap(QtGui.QPixmap())
            self.ui.label_code.setToolTip("")
            self.ui.pushButton_clear_filter_code.setVisible(False)
            self.ui.pushButton_clear_filter_code.setStyleSheet("")
        else:
            self.ui.label_code.setPixmap(qta.icon('mdi6.filter-outline').pixmap(22, 22))
            self.ui.label_code.setToolTip(_("Filtered: ") + self.show_codes_like_filter)
            self.ui.pushButton_clear_filter_code.setVisible(True)
            self.ui.pushButton_clear_filter_code.setStyleSheet("background-color: #1e90ff; color: white;")

    def show_codes_of_color(self):
        """ Show all codes in colour range in code tree., ir all codes if no selection.
        Show selected codes that are of a selected colour.
        Note: The code color needs to be in English - not translated. As the code colour ranges are in English.
        """

        ui = DialogSelectItems(self.app, colour_ranges, _("Select code colors"), "single")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        self.show_codes_colour_filter = selected['name']  # colour range name
        if self.show_codes_colour_filter == "all":
            self.show_codes_colour_filter = ""
        show_codes_of_colour_range(self.app, self.ui.treeWidget, self.codes, selected)
        self.show_codes_like_filter = ""
        if self.show_codes_colour_filter == "":
            self.ui.label_code.setPixmap(QtGui.QPixmap())
            self.ui.label_code.setToolTip("")
            self.ui.pushButton_clear_filter_code.setVisible(False)  # for clear filter code<- L
            self.ui.pushButton_clear_filter_code.setStyleSheet("")
        else:
            self.ui.label_code.setPixmap(qta.icon('mdi6.filter-outline').pixmap(22, 22))
            self.ui.label_code.setToolTip(_("Filtered: ") + self.show_codes_colour_filter)
            self.ui.pushButton_clear_filter_code.setVisible(True)
            self.ui.pushButton_clear_filter_code.setStyleSheet("background-color: #1e90ff; color: white;")  # blue

    def clear_code_filter(self):
        """ Clear any active code filter (show codes like or show codes of colour)
        and restore all codes in the tree. """

        self.show_codes_like_filter = ""
        self.show_codes_colour_filter = ""
        self.ui.lineEdit_code_filter.setText("")
        root = self.ui.treeWidget.invisibleRootItem()
        self.recursive_traverse(root, "")  # Show all codes
        self.ui.label_code.setPixmap(QtGui.QPixmap())
        self.ui.label_code.setToolTip("")
        self.ui.pushButton_clear_filter_code.setVisible(False)
        self.ui.pushButton_clear_filter_code.setStyleSheet("")  # Reset style

    def clear_file_filter(self):
        """ Clear any active file filter (show files like, case files, attributes)
        and reload all files. """
        self.attributes = []
        self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
        self.get_files()  # reload all files without filter
        self.ui.pushButton_clear_filter_file.setVisible(False)
        self.ui.pushButton_clear_filter_file.setStyleSheet("")  # reset blue style

    def recursive_traverse(self, item, text_: str = "", case_sensitive: bool = False):
        """ Find all children codes of this item that match or not and hide or unhide based on 'text'.
        Recurse through all child categories and sub-codes. A code stays visible if it matches or
        if any of its descendant sub-codes matches, so a match is never hidden under a
        non-matching parent code. Returns True if this item or any descendant matches. <- L
        Called by: show_codes_like
        Args:
            item: a QTreeWidgetItem
            text_:  Text string for matching with code names
            case_sensitive:  Bool
        """

        child_count = item.childCount()
        any_visible_descendant = False
        for i in range(child_count):
            child = item.child(i)
            is_code = "cid:" in child.text(1)
            # Recurse first so we know whether any descendant matches. <- L
            descendant_match = self.recursive_traverse(child, text_, case_sensitive)
            if text_ == "":
                if is_code:
                    child.setHidden(False)
                any_visible_descendant = True
                continue
            self_match = False
            if is_code:
                cid = int(child.text(1)[4:])
                c = next((cc for cc in self.codes if cc['cid'] == cid), None)
                if c is not None:
                    if case_sensitive:
                        self_match = text_ in c['name']
                    else:
                        self_match = text_.lower() in c['name'].lower()
            visible = self_match or descendant_match
            if is_code:
                child.setHidden(not visible)
            if visible:
                any_visible_descendant = True
        return any_visible_descendant

    def keyPressEvent(self, event):
        """
        A annotate - for current selection
        B Create bookmark - at clicked position
        Shift B - go to bookmark
        C New category
        Ctrl F jump to search box
        H Hide / Unhide top groupbox
        I Tag important
        L Show codes like
        M memo code - at clicked position
        N new code
        O Shortcut to cycle through overlapping codes - at clicked position
        Q Quick Mark with code - for current selection
        R opens a context menu for recently used codes for marking text
        Ctrl R - Reverse from left to right to right to left
        S search text - may include current selection
        U Unmark at selected location
        V assign 'in vivo' code to selected text
        Ctrl Z Undo last unmarking

        Ctrl 0 to Ctrl 9 - button presses
        ! Display Clicked character position
        ^ Alt key. Shift code positions. May be needed after the text is edited
            (added or deleted) to shift subsequent codings.
        F2 Rename code or category
        """

        key = event.key()
        mods = event.modifiers()

        # Ctrl + F jump to search box
        if key == QtCore.Qt.Key.Key_F and mods == QtCore.Qt.KeyboardModifier.ControlModifier:
            self.ui.lineEdit_search.setFocus()
            return
        # Ctrl Z undo last unmarked coding # TODO expand function
        if key == QtCore.Qt.Key.Key_Z and mods == QtCore.Qt.KeyboardModifier.ControlModifier:
            self.undo_last_unmarked_code()
            return
        # Ctrl R Display Right to Left (Arabic, Hebrew).
        if key == QtCore.Qt.Key.Key_R and mods == QtCore.Qt.KeyboardModifier.ControlModifier:
            if self.layout_direction == "LtoR":
                self.ui.plainTextEdit.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
                self.layout_direction = "RtoL"
                option = self.ui.plainTextEdit.document().defaultTextOption()
                option.setTextDirection(Qt.LayoutDirection.RightToLeft)
                option.setAlignment(Qt.AlignmentFlag.AlignRight)
                self.ui.plainTextEdit.document().setDefaultTextOption(option)
            else:
                self.layout_direction = "LtoR"
                option = self.ui.plainTextEdit.document().defaultTextOption()
                option.setTextDirection(Qt.LayoutDirection.LeftToRight)
                option.setAlignment(Qt.AlignmentFlag.AlignLeft)
                self.ui.plainTextEdit.document().setDefaultTextOption(option)
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
        # Rename code or category
        if self.ui.treeWidget.hasFocus() and key == QtCore.Qt.Key.Key_F2:
            selected = self.ui.treeWidget.currentItem()
            self.rename_category_or_code(selected)
            return
        if not self.ui.plainTextEdit.hasFocus():
            return
        # Ignore all other key events if edit mode is active
        if self.edit_mode:
            return

        key = event.key()
        # mod = QtGui.QGuiApplication.keyboardModifiers()
        cursor_pos = self.ui.plainTextEdit.textCursor().position()
        selected_text = self.ui.plainTextEdit.textCursor().selectedText()
        codes_here = []
        for item in self.code_text:
            if item['pos0'] <= cursor_pos + self.file_['start'] <= item['pos1']:
                codes_here.append(item)
        # ! display character position
        if key == QtCore.Qt.Key.Key_Exclam:
            Message(self.app, _("Text position") + " " * 20, _("Character position: ") + str(cursor_pos)).exec()
            return
        # $ shift code positions
        if key == QtCore.Qt.Key.Key_Dollar:
            self.shift_code_positions(self.ui.plainTextEdit.textCursor().position() + self.file_['start'])
            return
        # Annotate selected
        if key == QtCore.Qt.Key.Key_A and selected_text != "":
            self.annotate()
            return
        # Go to bookmark
        if key == QtCore.Qt.Key.Key_B and mods == QtCore.Qt.KeyboardModifier.ShiftModifier:
            self.go_to_bookmark()
            return
        # Bookmark
        if key == QtCore.Qt.Key.Key_B and self.file_ is not None:
            text_pos = self.ui.plainTextEdit.textCursor().position() + self.file_['start']
            cur = self.app.conn.cursor()
            cur.execute("update project set bookmarkfile=?, bookmarkpos=?", [self.file_['id'], text_pos])
            self.app.conn.commit()
            return
        # New category
        if key == QtCore.Qt.Key.Key_C:
            # if category already selected, add new category to that
            supercatid = None
            selected = self.ui.treeWidget.currentItem()
            if selected is not None and selected.text(1)[0:3] == 'cat':
                supercatid = int(selected.text(1)[6:])
            self.add_category(supercatid)
            return
        # Hide unHide top groupbox
        if key == QtCore.Qt.Key.Key_H:
            self.ui.groupBox.setHidden(not (self.ui.groupBox.isHidden()))
            return
        # Important  for coded text
        if key == QtCore.Qt.Key.Key_I:
            self.set_important(cursor_pos)
            return
        # Show codes like
        if key == QtCore.Qt.Key.Key_L:
            self.show_codes_like()
        # Memo for current code
        if key == QtCore.Qt.Key.Key_M:
            self.coded_text_memo(cursor_pos)
            return
        if key == QtCore.Qt.Key.Key_N:  # and self.ui.plainTextEdit.textCursor().selectedText() != '':
            self.mark_with_new_code(False)
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
        if key == QtCore.Qt.Key.Key_R and self.file_ is not None and self.ui.plainTextEdit.textCursor().selectedText() != "":
            self.text_edit_recent_codes_menu(self.ui.plainTextEdit.cursorRect().topLeft())
            return
        # Search, with or without selected
        if key == QtCore.Qt.Key.Key_S and self.file_ is not None:
            if selected_text == "":
                self.ui.lineEdit_search.setFocus()

    def highlight_selected_overlap(self):
        """ Highlight the current overlapping text code, by placing formatting on top. """

        self.overlaps_at_pos_idx += 1
        if self.overlaps_at_pos_idx >= len(self.overlaps_at_pos):
            self.overlaps_at_pos_idx = 0
        item = self.overlaps_at_pos[self.overlaps_at_pos_idx]
        # Remove formatting
        cursor = self.ui.plainTextEdit.textCursor()
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

    # - def overlapping_codes_in_text(self):
    # -    """ When coded text is clicked on.
    # -    Only enabled if two or more codes are here.
    # -    Adjust for when portion of full text file loaded.
    # -    Called by: textEdit cursor position changed. """
    # - 
    # -    self.overlaps_at_pos = []
    # -    self.overlaps_at_pos_idx = 0
    # -    pos = self.ui.plainTextEdit.textCursor().position()
    # -    for item in self.code_text:
    # -        if item['pos0'] <= pos + self.file_['start'] <= item['pos1']:
    # -            self.overlaps_at_pos.append(item)
    # -    if len(self.overlaps_at_pos) < 2:
    # -        self.overlaps_at_pos = []
    # -        self.overlaps_at_pos_idx = 0
            
    # --- for handles experimental

    def overlapping_codes_in_text(self):
        """ When coded text is clicked on.
        Only enabled if two or more codes are here.
        Adjust for when portion of full text file loaded.
        Called by: textEdit cursor position changed. """

        # Hide handles if the user clicks elsewhere in the editor
        if hasattr(self, 'active_handles') and self.active_handles:
            self.hide_resize_handles()

        self.overlaps_at_pos = []
        self.overlaps_at_pos_idx = 0
        pos = self.ui.plainTextEdit.textCursor().position()
        for item in self.code_text:
            if item['pos0'] <= pos + self.file_['start'] <= item['pos1']:
                self.overlaps_at_pos.append(item)
        if len(self.overlaps_at_pos) < 2:
            self.overlaps_at_pos = []
            self.overlaps_at_pos_idx = 0

    def export_option_selected(self):
        """ ComboBox export option selected.
        Routes the expanded comboBox options to their corresponding export methods.
        indexes:
        0
        1 odt highlight
        2 odt comment
        3 odt report
        4 txt
        5 html
        6 codebook
        """

        # Must use indexes not names for translations, if there are translations
        # export_option = self.ui.comboBox_export.currentText()
        index = self.ui.comboBox_export.currentIndex()
        if index == 0:
            return
        if index == 1:
            self.export_odt_file("highlight")
        elif index == 2:
            self.export_odt_file("comment")
        elif index == 3:
            self.export_odt_file("report")
        elif index == 4:
            self.export_tagged_text()
        elif index == 5:
            self.export_html_file()
        elif index == 6:
            self.export_codebook()
        self.ui.comboBox_export.setCurrentIndex(0)

    def export_odt_file(self, mode:str="highlight"):
        """ Export text to open file format with .odt ending.
        Args:
            mode: String - 'highlight', 'comment', or 'report'
        """

        if self.file_ is None or self.ui.plainTextEdit.toPlainText() == "":
            return
        project_header, apa_cite = self._export_project_header()
        filename = f"{self.file_['name']}_{mode}.odt"
        exp_dir = ExportDirectoryPathDialog(self.app, filename)
        filepath = exp_dir.filepath
        if filepath is None:
            return

        plain_text = self.ui.plainTextEdit.document().toPlainText()
        current_fid = self.file_['id']
        offset = self.file_['start']
        codes_in_file = [c for c in self.code_text if c['fid'] == current_fid]

        # Build the file using QTextDocument
        doc = QtGui.QTextDocument()
        cursor = QtGui.QTextCursor(doc)

        # Header: project + file name only
        header_fmt = QtGui.QTextCharFormat()
        header_fmt.setFontWeight(QtGui.QFont.Weight.Bold)
        header_fmt.setFontPointSize(16)
        cursor.insertText(project_header + "\n", header_fmt)
        cursor.insertText(_("File: ") + self.file_['name'] + "\n", header_fmt)
        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        cursor.insertText(_("Generated report: ") + now_date + "\n\n", header_fmt)
        
        norm_fmt = QtGui.QTextCharFormat()
        norm_fmt.setFontPointSize(12)

        # Content by mode
        if mode == "highlight":
            self._export_odt_highlighted(cursor, plain_text, codes_in_file, offset, norm_fmt)
        elif mode == "comment":
            self._export_odt_clean(filepath, plain_text, codes_in_file, offset)
            return
        elif mode == "report":
            journal_text = None
            cur = self.app.conn.cursor()
            base_name = self.file_['name']
            cur.execute("select name, jentry from journal where name=? or name like ?",
                        [base_name, base_name + "\\_%"])
            journal_results = cur.fetchall()
            if journal_results:
                # Combine all journals linked to this file
                combined = ""
                for jr in journal_results:
                    j_name = jr[0]
                    j_text = jr[1] if jr[1] else ""
                    if j_text.strip():
                        combined += f"── {j_name} ──\n{j_text}\n\n"
                if combined.strip():
                    reply = QtWidgets.QMessageBox.question(
                        self, _("Include journal"),
                        _("Journals are linked to this file. Include them in the report?"),
                        QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                        QtWidgets.QMessageBox.StandardButton.Yes)
                    if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                        journal_text = combined.strip()
            self._export_odt_analytical(cursor, plain_text, codes_in_file, offset, norm_fmt, header_fmt, journal_text)

        # Append citation at end (highlighted and analytical modes)
        cite_fmt = QtGui.QTextCharFormat()
        cite_fmt.setFontPointSize(12)
        cite_label_fmt = QtGui.QTextCharFormat()
        cite_label_fmt.setFontPointSize(12)
        cite_label_fmt.setFontWeight(QtGui.QFont.Weight.Bold)
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        cursor.insertText("\n\n", norm_fmt)
        cursor.insertText(_("Software citation") + "\n", cite_label_fmt)
        cursor.insertText(apa_cite + "\n", cite_fmt)
        # Write file
        tw = QtGui.QTextDocumentWriter()
        tw.setFileName(filepath)
        tw.setFormat(b'ODF')
        tw.write(doc)
        msg = _("Coded text file exported: ") + filepath
        self.parent_textEdit.append(msg)
        Message(self.app, _('Coded text file exported'), msg, "information").exec()
    
    # _export_project_header helper method #Now Footer
    def _export_project_header(self):
        """ Return project name and APA software citation string for export. """  

        project_name = os.path.basename(self.app.project_path).replace(".qda", "")  
        header = f"{_('Project')}: {project_name}"
        apa_cite = ("Curtain, C., & Dröge, K. (2026). QualCoder (Version 4.0) "  
                    "[Computer software]. https://github.com/ccbogel/QualCoder/releases/")
        return header, apa_cite
        
    # ODT highlighted mode
    def _export_odt_highlighted(self, cursor, plain_text, codes_in_file, offset, norm_fmt):
        """ ODT highlighted mode: full text with background-colored coded segments
        and code name tags at the end of each segment. """

        boundaries = {0, len(plain_text)}
        for c in codes_in_file:
            p0 = max(0, int(c['pos0']) - offset)
            p1 = min(len(plain_text), int(c['pos1']) - offset)
            boundaries.add(p0)
            boundaries.add(p1)
        boundaries = sorted(list(boundaries))

        end_tags = {}
        for c in codes_in_file:
            p1 = min(len(plain_text), int(c['pos1']) - offset)
            if p1 not in end_tags:
                end_tags[p1] = []
            end_tags[p1].append({'name': c['name'], 'color': c.get('color', '#cccccc')})

        for i in range(len(boundaries) - 1):
            b_start = boundaries[i]
            b_end = boundaries[i + 1]
            chunk_text = plain_text[b_start:b_end]
            if not chunk_text:
                continue
            active_codes = []
            for c in codes_in_file:
                p0 = max(0, int(c['pos0']) - offset)
                p1 = min(len(plain_text), int(c['pos1']) - offset)
                if p0 <= b_start and p1 >= b_end:
                    active_codes.append(c)
            if not active_codes:
                cursor.insertText(chunk_text, norm_fmt)
            else:
                fmt = QtGui.QTextCharFormat(norm_fmt)
                color = active_codes[0].get('color', '#cccccc')
                fmt.setBackground(QBrush(QColor(color)))
                fg = TextColor(color).recommendation
                fmt.setForeground(QBrush(QColor(fg)))
                cursor.insertText(chunk_text, fmt)
            if b_end in end_tags:
                for tag in end_tags[b_end]:
                    tag_fmt = QtGui.QTextCharFormat()
                    tag_fmt.setBackground(QBrush(QColor(tag['color'])))
                    fg = TextColor(tag['color']).recommendation
                    tag_fmt.setForeground(QBrush(QColor(fg)))
                    tag_fmt.setFontWeight(QtGui.QFont.Weight.Bold)
                    tag_fmt.setFontPointSize(12)
                    cursor.insertText(f" [{tag['name']}] ", tag_fmt)
                del end_tags[b_end]
    
    # ODT clean reading mode
    def _export_odt_clean(self, filepath, plain_text, codes_in_file, offset):
        """ ODT clean reading mode: plain text with code names as native ODF
        comments (annotations) spanning their corresponding coded segments.
        Uses odfpy to produce a proper ODF file with ranged annotations.
        """

        project_header, apa_cite = self._export_project_header()
        doc = OpenDocumentText()

        # Styles
        header_st = odf_style.Style(name="ExportHeader", family="paragraph")
        header_st.addElement(odf_style.TextProperties(fontsize="16pt", fontweight="bold"))
        doc.styles.addElement(header_st)

        normal_st = odf_style.Style(name="ExportNormal", family="paragraph")
        normal_st.addElement(odf_style.TextProperties(fontsize="12pt"))
        doc.styles.addElement(normal_st)

        # Header
        doc.text.addElement(odf_text.P(stylename=header_st, text=project_header))
        doc.text.addElement(odf_text.P(stylename=header_st, text=_("File: ") + self.file_['name']))
        report_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        doc.text.addElement(odf_text.P(stylename=header_st, text=_("Generated report: ") + report_date))
        doc.text.addElement(odf_text.P(stylename=normal_st, text=""))

        # Prepare annotation boundaries
        ann_counter = 0
        for c in codes_in_file:
            c['_ann_name'] = f"code_{ann_counter}"
            ann_counter += 1

        ann_starts = {}
        ann_ends = {}
        for c in codes_in_file:
            p0 = max(0, int(c['pos0']) - offset)
            p1 = min(len(plain_text), int(c['pos1']) - offset)
            ann_starts.setdefault(p0, []).append(c)
            ann_ends.setdefault(p1, []).append(c)

        boundaries = {0, len(plain_text)}
        for c in codes_in_file:
            boundaries.add(max(0, int(c['pos0']) - offset))
            boundaries.add(min(len(plain_text), int(c['pos1']) - offset))
        for i, ch in enumerate(plain_text):
            if ch == '\n':
                boundaries.add(i)
                boundaries.add(i + 1)
        boundaries = sorted(boundaries)

        # Build ODF paragraphs
        current_p = odf_text.P(stylename=normal_st)
        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S")

        for idx in range(len(boundaries) - 1):
            b_start = boundaries[idx]
            b_end = boundaries[idx + 1]
            chunk = plain_text[b_start:b_end]

            if chunk == '\n':
                doc.text.addElement(current_p)
                current_p = odf_text.P(stylename=normal_st)
                continue

            if b_start in ann_starts:
                for c in ann_starts[b_start]:
                    ann = odf_office.Annotation(name=c['_ann_name'])
                    if (DRAWNS, 'name') in ann.attributes:
                        del ann.attributes[(DRAWNS, 'name')]
                    ann.attributes[(OFFICENS, 'name')] = c['_ann_name']
                    ann.addElement(odf_dc.Creator(text=c.get('owner', '')))
                    ann.addElement(odf_dc.Date(text=now_date))
                    comment_text = c['name']
                    if c.get('memo') and str(c['memo']).strip():
                        comment_text += "\nMemo: " + str(c['memo'])
                    ann.addElement(odf_text.P(text=comment_text))
                    current_p.addElement(ann)

            if chunk:
                current_p.addText(chunk)

            if b_end in ann_ends:
                for c in ann_ends[b_end]:
                    current_p.addElement(odf_office.AnnotationEnd(name=c['_ann_name']))

        doc.text.addElement(current_p)

        # Save
        doc.save(filepath)
        msg = _("Coded text file exported: ") + filepath
        self.parent_textEdit.append(msg)
        Message(self.app, _('Coded text file exported'), msg, "information").exec()         
        
    # ODT analytical report
    def _export_odt_analytical(self, cursor, plain_text, codes_in_file, offset, norm_fmt, title_fmt, journal_text=None):
        """ ODT analytical report: frequency table, co-occurrence table, 
        coded segments with memos, highlighted full file, and optional journal. """ 

        from collections import defaultdict  
        total_chars = max(len(plain_text), 1)  

        code_memo_lookup = {c['cid']: c.get('memo', '') for c in self.codes} 
        cat_lookup = {c['catid']: c['name'] for c in self.categories}
        code_cat_lookup = {}
        for c in self.codes:
            if c.get('catid') and c['catid'] in cat_lookup:
                code_cat_lookup[c['cid']] = cat_lookup[c['catid']]

        seg_co_occurrences = defaultdict(set)
        for i, c1 in enumerate(codes_in_file): 
            for j, c2 in enumerate(codes_in_file): 
                if j <= i or c1['cid'] == c2['cid']:  
                    continue 
                if c1['pos0'] < c2['pos1'] and c2['pos0'] < c1['pos1']:  
                    seg_co_occurrences[(c1['pos0'], c1['pos1'], c1['cid'])].add(c2['name'])  
                    seg_co_occurrences[(c2['pos0'], c2['pos1'], c2['cid'])].add(c1['name'])  

        title_fmt = QtGui.QTextCharFormat()
        title_fmt.setFontPointSize(14)
        title_fmt.setFontWeight(QtGui.QFont.Weight.Bold)
        norm_fmt = QtGui.QTextCharFormat()
        norm_fmt.setFontPointSize(12)
        it_fmt = QtGui.QTextCharFormat()
        it_fmt.setFontItalic(True)
        it_fmt.setFontPointSize(12)
        bold_fmt = QtGui.QTextCharFormat()
        bold_fmt.setFontPointSize(12)
        bold_fmt.setFontWeight(QtGui.QFont.Weight.Bold)

        table_fmt = QtGui.QTextTableFormat()
        table_fmt.setBorder(0.5)
        table_fmt.setCellPadding(4)
        table_fmt.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)

        head_fmt = QtGui.QTextCharFormat()
        head_fmt.setFontWeight(QtGui.QFont.Weight.Bold)
        head_fmt.setFontPointSize(12)
        head_fmt.setBackground(QBrush(QColor("#e0e0e0")))

        # 1. CODE FREQUENCY TABLE
        cursor.insertText(_("Code Frequency Table") + "\n\n", title_fmt)
        code_stats = {}
        for c in codes_in_file:
            c_name = c['name']
            c_len = c['pos1'] - c['pos0']
            if c_name not in code_stats:
                code_stats[c_name] = {
                    'cid': c['cid'], 'color': c.get('color', '#cccccc'),
                    'len': 0, 'freq': 0, 'owners': set(),
                    'first_date': c.get('date', ''), 'last_date': c.get('date', '')
                }
            code_stats[c_name]['len'] += c_len
            code_stats[c_name]['freq'] += 1
            code_stats[c_name]['owners'].add(c['owner'])
            c_date = c.get('date', '')
            if c_date and c_date < code_stats[c_name]['first_date']:
                code_stats[c_name]['first_date'] = c_date
            if c_date and c_date > code_stats[c_name]['last_date']:
                code_stats[c_name]['last_date'] = c_date

        freq_rows = len(code_stats) + 1
        freq_table = cursor.insertTable(freq_rows, 5, table_fmt)
        freq_headers = [_("Code"), _("Frequency / Coverage"), _("Coder(s)"),
                        _("First coded"), _("Last coded")]
        for col, text in enumerate(freq_headers): 
            freq_table.cellAt(0, col).firstCursorPosition().insertText(text, head_fmt) 

        row = 1  
        for c_name, stats in sorted(code_stats.items()):  
            cell_cursor = freq_table.cellAt(row, 0).firstCursorPosition() 
            c_fmt = QtGui.QTextCharFormat()
            c_fmt.setFontPointSize(12)
            c_fmt.setBackground(QBrush(QColor(stats['color'])))
            fg = TextColor(stats['color']).recommendation
            c_fmt.setForeground(QBrush(QColor(fg)))
            cell_cursor.insertText(c_name, c_fmt)
            perc = (stats['len'] / total_chars) * 100
            freq_table.cellAt(row, 1).firstCursorPosition().insertText(
                f"{stats['freq']} ({perc:.1f}%)", norm_fmt)
            freq_table.cellAt(row, 2).firstCursorPosition().insertText(
                ", ".join(sorted(stats['owners'])), norm_fmt)
            first_d = stats['first_date'][:16] if stats['first_date'] else ""
            last_d = stats['last_date'][:16] if stats['last_date'] else ""
            freq_table.cellAt(row, 3).firstCursorPosition().insertText(first_d, norm_fmt)
            freq_table.cellAt(row, 4).firstCursorPosition().insertText(last_d, norm_fmt)
            row += 1

        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)

        # 2. CODE CO-OCCURRENCES
        cursor.insertText("\n\n" + _("Code Co-occurrences") + "\n\n", title_fmt)
        co_occur = defaultdict(int)
        for i, c1 in enumerate(codes_in_file):
            for j, c2 in enumerate(codes_in_file):
                if j <= i or c1['cid'] == c2['cid']:
                    continue
                if c1['pos0'] < c2['pos1'] and c2['pos0'] < c1['pos1']:
                    pair = tuple(sorted([c1['name'], c2['name']]))
                    co_occur[pair] += 1

        if co_occur:
            co_rows = len(co_occur) + 1
            co_table = cursor.insertTable(co_rows, 3, table_fmt)
            co_headers = [_("Code A"), _("Code B"), _("Co-occurrence frequency")]
            for col, text in enumerate(co_headers):
                co_table.cellAt(0, col).firstCursorPosition().insertText(text, head_fmt)
            r = 1
            for pair, count in sorted(co_occur.items(), key=lambda x: -x[1]):
                co_table.cellAt(r, 0).firstCursorPosition().insertText(pair[0], norm_fmt)
                co_table.cellAt(r, 1).firstCursorPosition().insertText(pair[1], norm_fmt)
                co_table.cellAt(r, 2).firstCursorPosition().insertText(str(count), norm_fmt)
                r += 1
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        else:
            cursor.insertText(_("No co-occurrences found in this file.") + "\n", norm_fmt)

        # 3. CODES AND MEMOS TABLE
        cursor.insertText("\n\n" + _("Codes and Memos") + "\n\n", title_fmt)
        codes_with_memos = {}
        for c in codes_in_file:
            cid = c['cid']
            if cid not in codes_with_memos:
                codes_with_memos[cid] = {
                    'name': c['name'],
                    'color': c.get('color', '#cccccc'),
                    'memo': code_memo_lookup.get(cid, ''),
                    'category': code_cat_lookup.get(cid, '')
                }
        if codes_with_memos:
            cm_rows = len(codes_with_memos) + 1
            cm_table = cursor.insertTable(cm_rows, 3, table_fmt)
            cm_headers = [_("Code"), _("Category"), _("Memo")]
            for col, text in enumerate(cm_headers):
                cm_table.cellAt(0, col).firstCursorPosition().insertText(text, head_fmt)
            cm_row = 1
            for cid, info in sorted(codes_with_memos.items(), key=lambda x: x[1]['name']):
                c_fmt = QtGui.QTextCharFormat()
                c_fmt.setFontPointSize(12)
                c_fmt.setBackground(QBrush(QColor(info['color'])))
                fg = TextColor(info['color']).recommendation
                c_fmt.setForeground(QBrush(QColor(fg)))
                cm_table.cellAt(cm_row, 0).firstCursorPosition().insertText(info['name'], c_fmt)
                cm_table.cellAt(cm_row, 1).firstCursorPosition().insertText(info['category'], norm_fmt)
                memo_text = info['memo'] if info['memo'] else _("No memo")
                # Replace newlines and common separators to keep memo in a single cell
                memo_text = memo_text.replace('\r\n', ' | ').replace('\n', ' | ').replace('\r', ' | ')  
                cm_table.cellAt(cm_row, 2).firstCursorPosition().insertText(memo_text, norm_fmt)
                cm_row += 1
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        # Separator between codes table and individual coded segments
        cursor.insertText("\n\n", norm_fmt)
        separator_fmt = QtGui.QTextCharFormat()
        separator_fmt.setFontPointSize(14)
        separator_fmt.setFontWeight(QtGui.QFont.Weight.Bold)
        cursor.insertText(_("Coded Segments") + "\n", separator_fmt)
        cursor.insertText("\n", norm_fmt)
        codes_sorted = sorted(codes_in_file, key=lambda x: x['pos0'])
        for c in codes_sorted:
            p0 = max(0, int(c['pos0']) - offset)
            p1 = min(len(plain_text), int(c['pos1']) - offset)
            seg = plain_text[p0:p1]
            cat_name = code_cat_lookup.get(c['cid'], '')

            color = c.get('color', '#cccccc')
            fg = TextColor(color).recommendation
            c_header_fmt = QtGui.QTextCharFormat()
            c_header_fmt.setFontPointSize(12)
            c_header_fmt.setBackground(QBrush(QColor(color)))
            c_header_fmt.setForeground(QBrush(QColor(fg)))
            c_header_bold = QtGui.QTextCharFormat(c_header_fmt)
            c_header_bold.setFontWeight(QtGui.QFont.Weight.Bold)

            cursor.insertText(f"[{c['pos0']}-{c['pos1']}] ", c_header_bold)
            if cat_name:
                cursor.insertText(f"{_('Category')}: {cat_name}, ", c_header_fmt)
            cursor.insertText(f"{_('Code')}: {c['name']}", c_header_fmt)
            if c.get('important') == 1:
                cursor.insertText(" ★", c_header_bold)
            coding_datetime = c.get('date', '')[:16] if c.get('date') else ''  
            cursor.insertText(f",  {_('Coder')}: {c['owner']} ({coding_datetime})", c_header_fmt)
            cursor.insertText("\n", norm_fmt)
            cursor.insertText("\n", norm_fmt)
            cursor.insertText(seg, it_fmt)
            cursor.insertText("\n\n", norm_fmt)

            coded_memo = c.get('memo', '')
            if coded_memo and str(coded_memo).strip():
                cursor.insertText(f"[{_('Coded memo')}: {coded_memo}]\n", norm_fmt)
            else:  
                cursor.insertText(f"[{_('Coded memo')}: {_('No coded memo')}]\n", norm_fmt)

            co_key = (c['pos0'], c['pos1'], c['cid'])
            co_codes = seg_co_occurrences.get(co_key, set())
            if co_codes:
                cursor.insertText(f"[{_('Co-occurring codes')}: {', '.join(sorted(co_codes))}]\n", norm_fmt)
            cursor.insertText("\n", norm_fmt)

        # 5. HIGHLIGHTED FULL FILE <- L #20260325
        cursor.insertText("\n\n", norm_fmt)
        cursor.insertText("\n", norm_fmt)
        cursor.insertText(_("Full File (highlight)") + "\n\n", title_fmt)
        self._export_odt_highlighted(cursor, plain_text, codes_in_file, offset, norm_fmt)

        # 6. FILE MEMO
        if self.file_ and self.file_.get('memo', '').strip():
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
            cursor.insertText("\n\n" + _("File Memo") + "\n\n", title_fmt)
            cursor.insertText(self.file_['memo'] + "\n", norm_fmt)

        # 7. FILE JOURNAL (if provided)
        if journal_text:
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
            cursor.insertText("\n\n" + _("File Journal") + "\n\n", title_fmt)
            cursor.insertText(journal_text + "\n", norm_fmt)
            
    # Export text to an HTML file with highlighted coded segments and code name tags
    def export_html_file(self):
        """ Export text to an HTML file with highlighted coded segments and code name tags,
        matching the structure of the ODT highlighted export. """
 
        if self.file_ is None or self.ui.plainTextEdit.toPlainText() == "":
            return
        project_header, apa_cite = self._export_project_header()
        plain_text = self.ui.plainTextEdit.document().toPlainText()
        current_fid = self.file_['id']
        offset = self.file_['start']
        codes_in_file = [c for c in self.code_text if c['fid'] == current_fid]
 
        boundaries = {0, len(plain_text)}
        for c in codes_in_file:
            p0 = max(0, int(c['pos0']) - offset)
            p1 = min(len(plain_text), int(c['pos1']) - offset)
            boundaries.add(p0)
            boundaries.add(p1)
        boundaries = sorted(list(boundaries))
 
        end_tags = {}
        for c in codes_in_file:
            p1 = min(len(plain_text), int(c['pos1']) - offset)
            if p1 not in end_tags:
                end_tags[p1] = []
            end_tags[p1].append({'name': c['name'], 'color': c.get('color', '#cccccc'),
                                 'memo': c.get('memo', '')})
 
        html_chunks = []
        for i in range(len(boundaries) - 1):
            b_start = boundaries[i]
            b_end = boundaries[i + 1]
            chunk_text = plain_text[b_start:b_end]
            if not chunk_text:
                continue
            safe_text = html.escape(chunk_text).replace('\n', '<br>\n')
            active_codes = []
            for c in codes_in_file:
                p0 = max(0, int(c['pos0']) - offset)
                p1 = min(len(plain_text), int(c['pos1']) - offset)
                if p0 <= b_start and p1 >= b_end:
                    active_codes.append(c)
            if not active_codes:
                html_chunks.append(safe_text)
            else:
                color = active_codes[0].get('color', '#cccccc')
                fg = TextColor(color).recommendation
                titles = []
                for ac in active_codes:
                    t = html.escape(ac['name'])
                    if ac.get('memo'):
                        t += f" — Memo: {html.escape(str(ac['memo']))}"
                    titles.append(t)
                title_attr = html.escape(" | ".join(titles))
                span = (f'<span style="background-color:{color};color:{fg};" '
                        f'title="{title_attr}">{safe_text}</span>')
                html_chunks.append(span)
            if b_end in end_tags:
                for tag in end_tags[b_end]:
                    fg = TextColor(tag['color']).recommendation
                    tag_html = (f'<span style="background-color:{tag["color"]};color:{fg};'
                                f'font-weight:bold;font-size:12pt;padding:1px 3px;'
                                f'border-radius:2px;margin:0 2px;">'
                                f'[{html.escape(tag["name"])}]</span>')
                    html_chunks.append(tag_html)
                del end_tags[b_end]
 
        html_body = "".join(html_chunks)
        escaped_name = html.escape(self.file_['name'])
        escaped_header = html.escape(project_header)
        escaped_apa = html.escape(apa_cite)
        final_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>{escaped_header} — {escaped_name}</title>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
               max-width: 900px; margin: 40px auto; padding: 20px;
               line-height: 1.8; font-size: 12px; color: #333;
               background-color: #f9f9f9; }}
        .header {{ border-bottom: 2px solid #2c3e50; padding-bottom: 15px;
                   margin-bottom: 25px; }}
        .header h1 {{ font-size: 1.4em; margin: 0; color: #2c3e50; }}
        .header h2 {{ font-size: 1.1em; margin: 10px 0 0 0; color: #555; }}
        .content {{ background: white; padding: 30px; border-radius: 6px;
                    box-shadow: 0 1px 4px rgba(0,0,0,0.08); }}
        span[title] {{ cursor: help; border-radius: 2px; padding: 1px 0; }}
        .footer {{ margin-top:30px; padding-top:10px; border-top:1px solid #ccc;
                   font-size:12pt; color:#666; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{escaped_header}</h1>
        <h2>{_("File:")} {escaped_name}</h2>
    </div>
    <div class="content">
        {html_body}
    </div>
    <div class="footer">
        <b>{_("Software citation")}</b><br>
        {escaped_apa}
    </div>
</body>
</html>"""
 
        html_filename = self.file_['name'] + ".html"
        exp_dir = ExportDirectoryPathDialog(self.app, html_filename)
        filepath = exp_dir.filepath
        if filepath is None:
            return
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(final_html)
        msg = _("Coded text file exported to: ") + filepath
        self.parent_textEdit.append(msg)
        Message(self.app, _('Coded html file exported'), msg, "information").exec()

    def export_tagged_text(self):
        """ Export a text file with code tags.
         code tags are surrounded by double braces:
         {{codename{{some coded text}}codename}}. """
 
        if len(self.ui.plainTextEdit.document().toPlainText()) == 0:
            return
        if self.file_ is None:
            return
        plain_text = self.ui.plainTextEdit.document().toPlainText()
        # Prepare code text with name and ordering
        code_text2 = deepcopy(self.code_text)
        code_ids_used = []
        for ct in code_text2:
            for c in self.codes:
                if ct['cid'] == c['cid']:
                    ct['codename'] = c['name']
                    code_ids_used.append(c['cid'])
                    break
        code_ids_used = list(set(code_ids_used))
 
        # Prepare text
        tagged_text = ""
        for i, c in enumerate(plain_text):
            for ct in code_text2:
                if ct['pos0'] == i:
                    tagged_text += "{{" + ct['codename'] + "{{"
                if ct['pos1'] == i:
                    tagged_text += "}}" + ct['codename'] + "}}"
            tagged_text += c
 
        # Add project header
        project_header, apa_cite = self._export_project_header()  # footer
        tagged_text = (f"{project_header}\n{_('File:')} {self.file_['name']}\n\n"
                       f"{tagged_text}\n")
 
        # Add Codes list
        codes_list = []
        for cd in self.codes:
            if cd['cid'] in code_ids_used:
                category = None
                for cat in self.categories:
                    if cd['catid'] == cat['catid']:
                        category = cat['name']
                codes_list.append([cd['name'], cd['memo'], category])
        tagged_text += "\n\n\n" + _("CODES LIST") + "\n"
        for cd in codes_list:
            tagged_text += cd[0]
            if cd[2] is not None:
                tagged_text += f" -- {_('CATEGORY')}: {cd[2]}"
            if cd[1] != "":
                tagged_text += f" -- {_('CODE MEMO')}: {cd[1]}"
            tagged_text += '\n'
 
        # Citation at end
        tagged_text += f"\n\n{_('Software citation')}\n{apa_cite}\n"
 
        export_filename = self.file_['name'] + "_tagged.txt"
        exp_dir = ExportDirectoryPathDialog(self.app, export_filename)
        filepath = exp_dir.filepath
        if filepath is None:
            return
        with open(filepath, 'w', encoding='utf-8') as text_file:
            text_file.write(tagged_text)
        msg = _("Coded text file exported to: ") + filepath
        self.parent_textEdit.append(msg)
        Message(self.app, _('Coded text file exported'), msg, "information").exec()
        
    # Export a codebook text file
    def export_codebook(self):
        """ Export a codebook text file with only codes used in the current file.
        Format: Category>>CodeName[TAB]Memo """

        if self.file_ is None:
            return
        cur = self.app.conn.cursor()
        cur.execute("select distinct cid from code_text where fid=?", [self.file_['id']])
        used_cids = [r[0] for r in cur.fetchall()]
        if not used_cids:
            Message(self.app, _("No codes"),
                    _("This file has no assigned codes to export."), "information").exec()
            return
        lines = []
        for cid in used_cids:
            for code in self.codes:
                if code['cid'] == cid:
                    cat_path = ""
                    if code['catid'] is not None:
                        for cat in self.categories:
                            if cat['catid'] == code['catid']:
                                cat_path = cat['name'] + " >> "
                                break
                    memo = str(code.get('memo', '')).replace('\n', ' ').strip()
                    lines.append(f"{cat_path}{code['name']}\t{memo}")
                    break
        lines.sort()
        text_content = "\n".join(lines)
        filename = self.file_['name'] + "_codebook.txt"
        exp_dir = ExportDirectoryPathDialog(self.app, filename)
        filepath = exp_dir.filepath
        if filepath is None:
            return
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(text_content)
        msg = _("Codebook exported to: ") + filepath
        self.parent_textEdit.append(msg)
        Message(self.app, _('Codebook exported'), msg, "information").exec()

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

        # request a margin redraw on editor resize so stripes follow text reflow <- L
        if object_ is self.ui.plainTextEdit and event.type() == QtCore.QEvent.Type.Resize:
            if hasattr(self, 'coding_margin') and self.coding_margin is not None:
                self.coding_margin.update()

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
            # Scroll the tree when dragged item it as top or bottom edges
            if event.type() == QtCore.QEvent.Type.DragMove:
                vsb = self.ui.treeWidget.verticalScrollBar()
                item = self.ui.treeWidget.currentItem()  # Not used
                top = self.ui.treeWidget.visualRect(self.ui.treeWidget.indexAt(self.ui.treeWidget.rect().topLeft())).bottom()
                bottom = self.ui.treeWidget.viewport().height()
                y = event.position().toPoint().y()
                if y < top + 8:  # Margin 0f 8
                    vsb.setValue(vsb.value() - 1)
                if y > bottom - 8:  # Margin of 8
                    vsb.setValue(vsb.value() + 1)
                return True
        # Change start and end code positions using alt arrow left and alt arrow right
        # and shift arrow left, shift arrow right
        if type(event) == QtGui.QKeyEvent and object_ is self.ui.plainTextEdit:
            key = event.key()
            mod = event.modifiers()
            first_key_press = event.type() == QtCore.QEvent.Type.KeyPress and not event.isAutoRepeat()
            # using timer for a lot of things
            now = datetime.datetime.now()
            diff = now - self.code_resize_timer
            if diff.microseconds < 100000:
                if mod in (QtCore.Qt.KeyboardModifier.AltModifier, QtCore.Qt.KeyboardModifier.ShiftModifier) \
                        and key in (QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Right):
                    return True  # consume rapid shift + left clicks, etc. without changing selection
                else:
                    return False
            # Ctrl + E Edit mode - must be detected here as Ctrl E is overridden in editable textEdit
            if key == QtCore.Qt.Key.Key_E and mod == QtCore.Qt.KeyboardModifier.ControlModifier and first_key_press:
                self.edit_mode_toggle()
                return True
            # Ignore all other key events if edit mode is active
            if self.edit_mode:
                return False
            cursor_pos = self.ui.plainTextEdit.textCursor().position()
            codes_here = []
            for item in self.code_text:
                if item['pos0'] <= cursor_pos + self.file_['start'] <= item['pos1']:
                    codes_here.append(item)
            code_ = None
            if len(codes_here) == 0:
                return False
            if len(codes_here) > 1 and mod in (
                    QtCore.Qt.KeyboardModifier.AltModifier, QtCore.Qt.KeyboardModifier.ShiftModifier) \
                    and key in (QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Right):
                ui = DialogSelectItems(self.app, codes_here, _("Select a code"), "single")
                ok = ui.exec()
                if not ok:
                    return True
                code_ = ui.get_selected()
                if not code_:
                    return True
            if len(codes_here) == 1:
                code_ = codes_here[0]
            # Key event can be too sensitive, adjusted  for 150 millisecond gap
            self.code_resize_timer = datetime.datetime.now()
            if key == QtCore.Qt.Key.Key_Left and mod == QtCore.Qt.KeyboardModifier.AltModifier:
                self.shrink_to_left(code_)
                return True
            if key == QtCore.Qt.Key.Key_Right and mod == QtCore.Qt.KeyboardModifier.AltModifier:
                self.shrink_to_right(code_)
                return True
            if key == QtCore.Qt.Key.Key_Left and mod == QtCore.Qt.KeyboardModifier.ShiftModifier:
                self.extend_left(code_)
                return True
            if key == QtCore.Qt.Key.Key_Right and mod == QtCore.Qt.KeyboardModifier.ShiftModifier:
                self.extend_right(code_)
                return True
        return False

    def extend_left(self, code_):
        """ Shift left arrow.
        Args:
            code_: code Dictionary
        """

        if not code_:
            return
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
        """ Shift right arrow.
        Args:
            code_: code Dictionary
        """

        if not code_:
            return
        if code_['pos1'] + 1 >= len(self.ui.plainTextEdit.toPlainText()):
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
        """ Alt left arrow, shrinks code from the right end of the code.
        Args:
            code_: code Dictionary
        """

        if not code_:
            return
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
        """ Alt right arrow shrinks code from the left end of the code.
        Args:
            code_: code Dictionary
        """

        if not code_:
            return
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
        cursor = self.ui.plainTextEdit.textCursor()
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
            cursor = self.ui.plainTextEdit.textCursor()
            cursor.setPosition(0)
            self.ui.plainTextEdit.setTextCursor(cursor)
        self.unlight()
        msg = " " + _("Code:") + " " + msg
        # Highlight the code in the text
        color = ""
        for c in self.codes:
            if c['cid'] == cid:
                color = c['color']
        cursor.setPosition(cur_pos)
        self.ui.plainTextEdit.setTextCursor(cursor)
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
        # Need to reload icons as they disappear on Windows
        self.ui.pushButton_show_all_codings.setIcon(qta.icon('mdi6.grid'))
        self.ui.pushButton_show_codings_prev.setStyleSheet(f"background-color: {color}; color:{foreground_color}")
        self.ui.pushButton_show_codings_prev.setIcon(qta.icon('mdi6.arrow-left'))
        tt = _("Show previous coding of selected code") + msg
        self.ui.pushButton_show_codings_prev.setToolTip(tt)
        self.ui.pushButton_show_codings_next.setStyleSheet(f"background-color: {color}; color:{foreground_color}")
        tt = _("Show next coding of selected code") + msg
        self.ui.pushButton_show_codings_next.setToolTip(tt)
        self.ui.pushButton_show_codings_next.setIcon(qta.icon('mdi6.arrow-right'))

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
        cursor = self.ui.plainTextEdit.textCursor()
        cur_pos = cursor.position()
        end_pos = 0
        found_smaller = False
        msg = f"/{len(indexes)}"
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
        self.ui.plainTextEdit.setTextCursor(cursor)
        cursor.setPosition(cur_pos, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(end_pos, QtGui.QTextCursor.MoveMode.KeepAnchor)
        brush = QBrush(QColor(color))
        fmt = QtGui.QTextCharFormat()
        fmt.setBackground(brush)
        foreground_colour = TextColor(color).recommendation
        fmt.setForeground(QBrush(QColor(foreground_colour)))
        cursor.mergeCharFormat(fmt)
        # Update tooltips to show only this code
        self.eventFilterTT.set_codes_and_annotations(self.app, tt_code_text, self.codes, self.annotations,
                                                     self.file_)
        # Need to reload icons as they disapear on Windows
        self.ui.pushButton_show_all_codings.setIcon(qta.icon('mdi6.grid'))
        self.ui.pushButton_show_codings_prev.setStyleSheet(f"background-color: {color};color:{foreground_colour}")
        self.ui.pushButton_show_codings_prev.setIcon(qta.icon('mdi6.arrow-left'))
        tt = _("Show previous coding of selected code") + msg
        self.ui.pushButton_show_codings_prev.setToolTip(tt)
        self.ui.pushButton_show_codings_next.setStyleSheet(f"background-color: {color};color:{foreground_colour}")
        self.ui.pushButton_show_codings_next.setIcon(qta.icon('mdi6.arrow-right'))
        tt = _("Show next coding of selected code") + msg
        self.ui.pushButton_show_codings_next.setToolTip(tt)

    def show_all_codes_in_text(self):
        """ Opposes show selected code methods.
        Highlights all the codes in the text. """

        self.ui.pushButton_show_all_codings.setIcon(qta.icon('mdi6.grid-off'))
        self.ui.pushButton_show_codings_prev.setStyleSheet("")
        self.ui.pushButton_show_codings_next.setStyleSheet("")
        self.ui.pushButton_show_codings_prev.setIcon(qta.icon('mdi6.arrow-left'))
        tt = _("Show previous coding of selected code")
        self.ui.pushButton_show_codings_prev.setToolTip(tt)
        self.ui.pushButton_show_codings_next.setIcon(qta.icon('mdi6.arrow-right'))
        tt = _("Show next coding of selected code")
        self.ui.pushButton_show_codings_next.setToolTip(tt)
        self.get_coded_text_update_eventfilter_tooltips()

    def item_moved_update_data(self, item, parent):
        """ Called from drop event in treeWidget view port.
        identify code or category to move.
        Also merge codes if one code is dropped on another code.
        Args:
            item : QTreeWidgetItem
            parent : QTreeWidgetItem
        """

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
                # would make the branch disappear and corrupt the tree. <- L
                if self._category_is_descendant(supercatid, self.categories[found]['catid']):
                    Message(self.app, _("Cannot move category"),
                            _("Cannot move a category under one of its own sub-categories.")).exec()
                    return
                self.categories[found]['supercatid'] = supercatid
            cur = self.app.conn.cursor()
            cur.execute("update code_cat set supercatid=? where catid=?",
                        [self.categories[found]['supercatid'], self.categories[found]['catid']])
            self.app.conn.commit()
            self.update_dialog_codes_and_categories(["code_cat"])
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
                # Move code to top level: clear both parents. <- L
                self.codes[found]['catid'] = None
                self.codes[found]['supercid'] = None
            else:
                if parent.text(1).split(':')[0] == 'cid':
                    parent_cid = int(parent.text(1).split(':')[1])
                    # Ctrl held while dropping a code on a code merges (previous behaviour);
                    # otherwise the code is nested as a sub-code. <- L
                    ctrl = bool(QtWidgets.QApplication.keyboardModifiers() &
                                QtCore.Qt.KeyboardModifier.ControlModifier)
                    if ctrl:
                        self.merge_codes(self.codes[found], parent)
                        return
                    if parent_cid == self.codes[found]['cid']:
                        return  # cannot nest under itself
                    if self._code_is_descendant(parent_cid, self.codes[found]['cid']):
                        Message(self.app, _("Cannot nest code"),
                                _("Cannot move a code under one of its own sub-codes.")).exec()
                        return
                    # Nest as a sub-code (mutually exclusive with category). <- L
                    self.codes[found]['supercid'] = parent_cid
                    self.codes[found]['catid'] = None
                else:
                    # Dropped onto a category. <- L
                    catid = int(parent.text(1).split(':')[1])
                    self.codes[found]['catid'] = catid
                    self.codes[found]['supercid'] = None

            cur = self.app.conn.cursor()
            cur.execute("update code_name set catid=?, supercid=? where cid=?",
                        [self.codes[found]['catid'], self.codes[found].get('supercid'),
                         self.codes[found]['cid']])
            self.app.conn.commit()
            self.app.delete_backup = False
            self.update_dialog_codes_and_categories(["code_name"])

    def _code_is_descendant(self, candidate_cid, ancestor_cid):
        """ Return True if candidate_cid is ancestor_cid or one of its descendant sub-codes.
        Used to prevent cycles when nesting a code under another code. <- L """
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

    def _category_is_descendant(self, candidate_catid, ancestor_catid):
        """ Return True if candidate_catid is ancestor_catid or one of its descendant
        sub-categories. Used to prevent cycles when moving a category under another. <- L """
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

    def merge_code_into_code(self, selected):
        """ Merge the selected code into another code chosen from a list.
        Reuses merge_codes (the same logic used by drag-and-drop with Ctrl). The source code
        and all of its descendant sub-codes are excluded from the candidate targets to avoid
        creating a supercid cycle when merging a code into one of its own sub-codes. <- L
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
            if not self._code_is_descendant(c['cid'], src_cid):
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
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        while it.value():
            node = it.value()
            if node.text(1) == f"cid:{target['cid']}":
                target_item = node
                break
            it += 1
        if target_item is None:
            return
        self.merge_codes(source_code, target_item)

    def merge_codes(self, item, parent):
        """ Merge code with another code.
        Called by item_moved_update_data when a code is moved onto another code.
        code text unique(cid,fid,pos0,pos1, owner)
        Args:
            item : Dictionary code item
            parent : QTreeWidgetItem
        """

        # Check item dropped on itself, an error can occur on Ubuntu 22.04.
        if item['name'] == parent.text(0):
            return
        # Prevent a supercid cycle <- L
        target_cid = int(parent.text(1).split(':')[1])
        if self._code_is_descendant(target_cid, item['cid']):
            Message(self.app, _("Cannot merge code"),
                    _("Cannot merge a code into itself or one of its own sub-codes.")).exec()
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
        # Always record merge info in target code memo  <- L
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
            # Re-parent the merged code's sub-codes onto the target code (no orphans). <- L
            cur.execute("update code_name set supercid=?, catid=null where supercid=?", [new_cid, old_cid])
            cur.execute("delete from code_name where cid=?", [old_cid, ])
            self.app.conn.commit()
        except Exception as e_:
            print(e_)
            self.app.conn.rollback()  # Revert all changes
            raise
        self.app.delete_backup = False
        msg = msg.replace("\n", " ")
        self.parent_textEdit.append(msg)
        self.update_dialog_codes_and_categories(["code_name", "code_text", "code_av", "code_image"])
        self.get_coded_text_update_eventfilter_tooltips()

    def add_code(self, catid:int|None=None, code_name:str="", supercid:int|None=None):
        """ Use add_item dialog to get new code text. Add_code_name dialog checks for
        duplicate code name. A random color is selected for the code, or a color has been pre-set by the user.
        New code is added to data and database.
        Args:
            catid : None to add code without category, catid Integer to add to category.
            code_name : String : Used for 'in vivo' coding where name is preset by in vivo text selection.
            supercid : None, or Integer to add the code as a sub-code of another code. <- L
        Returns:
            True  - new code added, False - code exists or could not be added
        """

        # Mutual exclusivity: a sub-code never belongs to a category as well. <- L
        if supercid is not None:
            catid = None
        if code_name == "":
            ui = DialogAddItemName(self.app, self.codes, _("Add new code"), _("Code name"))
            ui.exec()
            code_name = ui.get_new_name()
            if code_name is None:
                return False
        code_color = colors[randint(0, len(colors) - 1)]
        if self.default_new_code_color:
            code_color = self.default_new_code_color
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
            print("in vivo coding. Code already exists")
            return False
        self.update_dialog_codes_and_categories(["code_name"])
        self.get_coded_text_update_eventfilter_tooltips()
        return True

    def update_dialog_codes_and_categories(self, tables: list[str]|None = None):
        """Refresh the local dialog after code/category changes and optionally notify other dialogs.

        Args:
            tables: Optional list of changed database table names to emit to the project event bus.
                Use an empty list for a local-only refresh without notifying other dialogs.
        """

        self.get_codes_and_categories()
        self.fill_tree()
        self.unlight()
        self.highlight()
        self.get_coded_text_update_eventfilter_tooltips()

        if self.app.project_events is not None:
            self.app.project_events.emit_table_changes(tables, source=self)

    def _on_project_data_changed(self, tables, source):
        """Handle project change events from other dialogs.

        Args:
            tables: Changed database table names.
            source: Event emitter, ignored when it is this dialog.
        """

        if source is self or not isinstance(tables, list):
            return
        tables = set(tables)
        if ("attribute" in tables or "attribute_type" in tables) and len(self.attributes) > 1:
            self.get_files_from_attributes(refresh_only=True)
        if "code_cat" not in tables and "code_name" not in tables:
            if "code_text" not in tables:
                return
            # only code_text has changed
            ai_assisted_coding = self.ui.tabWidget.currentIndex() == 1
            if self.file_ is not None:
                self.get_coded_text_update_eventfilter_tooltips()
            if self.file_ is not None or ai_assisted_coding:
                self.fill_code_counts_in_tree()
            return
        # codes or categories have changed, so refresh all
        self.get_codes_and_categories()
        self.fill_tree()
        self.get_coded_text_update_eventfilter_tooltips()

    def add_category(self, supercatid:int|None=None):
        """ Add a new category.
        Note: the addItem dialog does the checking for duplicate category names
        Args:
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
        self.update_dialog_codes_and_categories(["code_cat"])
        self.app.delete_backup = False
        self.parent_textEdit.append(_("New category: ") + item['name'])

    def delete_category_or_code(self, selected):
        """ Determine if selected item is a code or category before deletion.
        Args:
            selected: QTreeWidgetItem
        """

        if selected.text(1)[0:3] == 'cat':
            self.delete_category(selected)
            return  # Avoid error as selected is now None
        if selected.text(1)[0:3] == 'cid':
            self.delete_code(selected)

    def delete_code(self, selected):
        """ Find code, remove from database, refresh and code data and fill treeWidget.
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
        # Re-parent this code's sub-codes so they are not orphaned by the deletion. <- L
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
        # Remove from recent codes
        for item in self.recent_codes:
            if item['name'] == code_['name']:
                self.recent_codes.remove(item)
                break
        self.update_dialog_codes_and_categories(["code_name", "code_text", "code_av", "code_image"])
        self.app.delete_backup = False

    def delete_category(self, selected):
        """ Find category, remove from database, refresh categories and code data
        and fill treeWidget.
        Args:
            selected: QTreeWidgetItem
        """

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
        # An extra check. Fix 'lost' categories if present.
        sql = "update code_cat set supercatid=null where supercatid is not null and supercatid not in " \
              "(select catid from code_cat)"
        cur.execute(sql)
        self.app.conn.commit()
        self.update_dialog_codes_and_categories(["code_cat", "code_name"])
        self.app.delete_backup = False
        self.parent_textEdit.append(_("Category deleted: ") + category['name'])

    def add_edit_cat_or_code_memo(self, selected):
        """ View and edit a memo for a category or code.
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
        self.update_dialog_codes_and_categories(changed_tables)

    def rename_category_or_code(self, selected):
        """ Rename a code or category.
        Check that the code or category name is not currently in use.
        Args:
            selected : QTreeWidgetItem """

        if selected.text(1)[0:3] == 'cid':
            found_code = None
            check_codes = []
            for code_ in self.codes:
                if code_['cid'] == int(selected.text(1)[4:]):
                    found_code = code_
                else:
                    check_codes.append(code_)
            ui = DialogAddItemName(self.app, check_codes, _("Rename code"), _("Code name"))
            ui.ui.lineEdit.setText(found_code['name'])
            ui.exec()
            new_name = ui.get_new_name()
            if new_name is None or new_name == found_code['name']:
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
            self.parent_textEdit.append(_("Code renamed from: ") + f"{old_name} --> {new_name}")
            self.update_dialog_codes_and_categories(["code_name"])
            return

        if selected.text(1)[0:3] == 'cat':
            found_cat = None
            check_categories = []
            for category in self.categories:
                if category['catid'] == int(selected.text(1)[6:]):
                    found_cat = category
                else:
                    check_categories.append(category)
            ui = DialogAddItemName(self.app, check_categories, _("Rename category"), _("Category name"))
            ui.ui.lineEdit.setText(found_cat['name'])
            ui.exec()
            new_name = ui.get_new_name()
            if new_name is None or new_name == found_cat['name']:
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
            self.update_dialog_codes_and_categories(["code_cat"])
            self.parent_textEdit.append(_("Category renamed from: ") + f"{old_name} --> {new_name}")

    def change_code_color(self, selected):
        """ Change the colour of the currently selected code.
        Args:
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
        self.update_dialog_codes_and_categories(["code_name"])

    def file_menu(self, position):
        """ Context menu for listWidget files to get to the next file and
        to go to the file with the latest codings by this coder.
        Sorting files.
        Each file dictionary item in self.files contains:
        {'id', 'name', 'memo', 'characters'= number of characters in the file,
        'start' = showing characters from this position, 'end' = showing characters to this position}

        Args:
            position :
        """

        selected = self.ui.listWidget.currentItem()
        if not selected:
            return
        file_ = next((f for f in self.files if f['name'] == selected.text()), None)
        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        action_next = None
        action_latest = None
        action_next_chars = None
        action_prev_chars = None
        action_show_files_like = None
        action_show_case_files = None
        action_show_by_attribute = None
        action_memo = menu.addAction(_("Open memo"))
        action_view_original_text = None
        if file_ is not None and file_['mediapath'] is not None and len(file_['mediapath']) > 6 and \
                (file_['mediapath'][:6] == '/docs/' or file_['mediapath'][:5] == 'docs:'):
            action_view_original_text = menu.addAction(_("view original text file"))
        if len(self.app.get_text_filenames()) > 1:
            if len(self.files) != 1:
                action_next = menu.addAction(_("Next file"))
            action_latest = menu.addAction(_("File with latest coding"))
            action_show_files_like = menu.addAction(_("Show files like"))
            action_show_by_attribute = menu.addAction(_("Show files by attributes"))
            action_show_case_files = menu.addAction(_("Show case files"))
        if file_ is not None and file_['characters'] > self.app.settings['codetext_chunksize']:
            action_next_chars = menu.addAction(str(self.app.settings['codetext_chunksize']) + _(" next  characters"))
            if file_['start'] > 0:
                action_prev_chars = menu.addAction(
                    str(self.app.settings['codetext_chunksize']) + _(" previous  characters"))
        action_go_to_bookmark = menu.addAction(_("Go to bookmark"))
        action_mark_speakers = menu.addAction(_("Mark speakers"))
        sort_menu = QtWidgets.QMenu(_("Sort"))
        sort_menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        action_sort_name_asc = sort_menu.addAction(_("Sort by name ascending"))
        action_sort_name_desc = sort_menu.addAction(_("Sort by name descending"))
        action_sort_case_asc = sort_menu.addAction(_("Sort by case ascending"))
        action_sort_case_desc = sort_menu.addAction(_("Sort by case descending"))
        action_sort_date_asc = sort_menu.addAction(_("Sort by date ascending"))
        action_sort_date_desc = sort_menu.addAction(_("Sort by date descending"))
        menu.addMenu(sort_menu)
        action = menu.exec(self.ui.listWidget.mapToGlobal(position))
        if action is None:
            return
        if action == action_memo:
            self.file_memo(file_)
        if action == action_view_original_text:
            self.view_original_text_file()
        if action == action_next:
            self.go_to_next_file()
        if action == action_latest:
            self.go_to_latest_coded_file()
        if action == action_go_to_bookmark:
            self.go_to_bookmark()
        if action == action_next_chars:
            self.next_chars(file_, selected)
        if action == action_prev_chars:
            self.prev_chars(file_, selected)
        if action == action_show_files_like:
            self.show_files_like()
        if action == action_show_case_files:
            self.show_case_files()
        if action == action_show_by_attribute:
            self.get_files_from_attributes()
        if action == action_mark_speakers:
            self.mark_speakers()
        if action == action_sort_name_asc:
            self.get_files(None, "name asc")
        if action == action_sort_name_desc:
            self.get_files(None, "name desc")
        if action == action_sort_case_asc:
            self.get_files(None, "case asc")
        if action == action_sort_case_desc:
            self.get_files(None, "case desc")
        if action == action_sort_date_asc:
            self.get_files(None, "date asc")
        if action == action_sort_date_desc:
            self.get_files(None, "date desc")

    def view_original_text_file(self):
        """ View original text file.
         param:
         mediapath: String '/docs/' for internal 'docs:/' for external """

        if self.file_['mediapath'][:6] == "/docs/":
            doc_path = self.app.project_path + "/documents/" + self.file_['mediapath'][6:]
            webbrowser.open(doc_path)
            return
        if self.file_['mediapath'][:5] == "docs:":
            doc_path = self.file_['mediapath'][5:]
            webbrowser.open(doc_path)
            return
        logger.error(_("Cannot open text file in browser ") + self.file_['mediapath'])
        print(f"code_text.view_original_text_file. Cannot open text file in browser {self.file_['mediapath']}")

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
            self.ui.pushButton_clear_filter_file.setVisible(False)  # reset filter button when showing all <- L
            self.ui.pushButton_clear_filter_file.setStyleSheet("")
            return
        cur = self.app.conn.cursor()
        cur.execute('select fid from case_text where caseid=?', [selection['id']])
        res = cur.fetchall()
        file_ids = [r[0] for r in res]
        self.get_files(file_ids)
        self.ui.pushButton_clear_filter_file.setVisible(True)  # <- L
        self.ui.pushButton_clear_filter_file.setStyleSheet("background-color: #1e90ff; color: white;")  # blue

    def show_files_like(self):
        """ Show files that contain specified filename text.
        If blank, show all files. """

        dialog = QtWidgets.QInputDialog(None)  # use None to make it a standalone floating window <- L
        dialog.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
        dialog.setWindowTitle(_("Show files like"))
        dialog.setWindowFlags(dialog.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog.setLabelText(_("Show files containing the text. (Blank for all)"))
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        text_ = str(dialog.textValue())
        if text_ == "":
            self.get_files()
            self.ui.pushButton_clear_filter_file.setVisible(False)  # hide filter button when showing all <- L
            self.ui.pushButton_clear_filter_file.setStyleSheet("")
            return
        cur = self.app.conn.cursor()
        cur.execute("select id from source where name like ? and "  # restrict to text files only <- L
                    "(mediapath is null or mediapath like '/docs/%' or mediapath like 'docs:%')",
                    ['%' + text_ + '%'])
        res = cur.fetchall()
        file_ids = [r[0] for r in res]
        self.get_files(file_ids)
        self.ui.pushButton_clear_filter_file.setVisible(True)  # clear filter file <- L
        self.ui.pushButton_clear_filter_file.setStyleSheet("background-color: #1e90ff; color: white;")  # blue

    def prev_chars(self, file_, selected):
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
                # ... + i - 1] Want to include the line break in the chunk, text[start:i] would otherwise exclude it
                if file_['fulltext'][file_['start'] + i - 1] == "\n":
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
                # [i - 1] Want to include the line break in the chunk, and text[start:i] would otherwise exclude it
                if file_['fulltext'][i - 1] == "\n":
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
                    if file_['fulltext'][file_['start'] - 1] == "\n":
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
                if file_['fulltext'][file_['start'] + i - 1] == "\n":
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
        self.load_file(file_)

    def go_to_next_file(self):
        """ Go to next file in list. Button. """

        if self.file_ is None:
            self.load_file(self.files[0])
            self.ui.listWidget.setCurrentRow(0)
            return
        for i in range(0, len(self.files) - 1):
            if self.file_ == self.files[i]:
                found = self.files[i + 1]
                self.ui.listWidget.setCurrentRow(i + 1)
                self.load_file(found)
                self.search_term = ""
                return

    def go_to_latest_coded_file(self):
        """ Go and open file with the latest coding. Button. """

        sql = "SELECT fid FROM code_text where owner=? order by date desc limit 1"
        cur = self.app.conn.cursor()
        cur.execute(sql, [self.app.settings['codername'], ])
        result = cur.fetchone()
        if result is None:
            return
        for i, f in enumerate(self.files):
            if f['id'] == result[0]:
                self.ui.listWidget.setCurrentRow(i)
                self.load_file(f)
                self.search_term = ""
                break

    def go_to_bookmark(self):
        """ Find bookmark, open the file and highlight the bookmarked character.
        Adjust for start of text file, as this may be a smaller portion of the full text file.

        The currently loaded text portion may not contain the bookmark.
        Solution - reset the file start and end marks to the entire file length and
        load the entire text file.
        """

        cur = self.app.conn.cursor()
        cur.execute("select bookmarkfile, bookmarkpos from project")
        result = cur.fetchone()
        for i, f in enumerate(self.files):
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
                    text_cursor = self.ui.plainTextEdit.textCursor()
                    text_cursor.setPosition(result[1])
                    endpos = result[1] - 1
                    if endpos < 0:
                        endpos = 0
                    text_cursor.setPosition(endpos, QtGui.QTextCursor.MoveMode.KeepAnchor)
                    self.ui.plainTextEdit.setTextCursor(text_cursor)
                except Exception as e:
                    logger.debug(str(e))
                break

    def edit_coder_names(self):
        ui_coder_names = DialogCoderNames(self.app, extended_options=False)
        if (ui_coder_names.exec() == QtWidgets.QDialog.DialogCode.Accepted and
                ui_coder_names.coder_names_changed):
            self.update_coder_names()

    def update_coder_names(self):
        """Update ui elements related to the coder names,
        also close contents in tab_reports since they must 
        update coder names as well."""
        # Update UI as coders visibility may have changed
        self.annotations = self.app.get_annotations()
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        self.ui.lineEdit_coder.setText(self.app.settings['codername'])
        # close contents in tab_reports since they must update coder names as well 
        contents = self.tab_reports.layout()
        if contents:
            for i in reversed(range(contents.count())):
                contents.itemAt(i).widget().close()
                contents.itemAt(i).widget().setParent(None)

    def mark_speakers(self):
        if self.file_ is not None:
            ui_speaker = DialogSpeakers(self.app, self.file_['id'], self.file_['name'])
            if ui_speaker.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                self.update_dialog_codes_and_categories(["code_name", "code_text"])
                if self.app.conn is not None and speaker_coder_name not in self.app.get_coder_names_in_project(
                        only_visible=True):
                    msg = _(
                        'Coder "{}" is currently hidden. Do you want to make it visible, to see the speaker codings?').format(
                        speaker_coder_name)
                    msg_box = Message(self.app, _('Speaker coding'), msg, 'Information')
                    msg_box.setStandardButtons(
                        QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
                    msg_box.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Yes)
                    reply = msg_box.exec()
                    if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                        cur = self.app.conn
                        cur.execute('update coder_names set visibility=1 where name=?', (speaker_coder_name,))
                        cur.commit()
                        self.update_coder_names()

        else:
            Message(self.app, _('Mark speakers'), _('No text file selected.'), 'critical').exec()

    def listwidgetitem_view_file(self):
        """ When listwidget item is pressed load the file.
        The selected file is then displayed for coding.
        Note: file segment is also loaded from listWidget context menu """

        if len(self.files) == 0:
            return
        item_name = self.ui.listWidget.currentItem().text()
        for f in self.files:
            if f['name'] == item_name:
                self.file_ = f
                self.load_file(self.file_)
                self.search_term = ""
                break

    def file_selection_changed(self):
        """ File selection changed. """

        row = self.ui.listWidget.currentRow()
        if row < 0 or row >= len(self.files):
            return
        if not self.ui.checkBox_search_all_files.isChecked():
            self.ui.lineEdit_search.setText("")
            self.ui.pushButton_next.setEnabled(False)
            self.ui.pushButton_previous.setEnabled(False)
            self.search_indices = []
            self.search_index = 0
            self.search_term = ""
            self.selected_code_index = 0

        self.load_file(self.files[row])

    def load_file(self, file_):
        """ Load and display file text for this file.
        Set the file as a selected item in the list widget. (due to the search text function searching across files).
        Get and display coding highlights.
        Called from:
            view_file_dialog, context_menu
        Args:
            file_ : dictionary of name, id, memo, characters, start, end, fulltext
        """

        self.ui.listWidget.blockSignals(True)
        for x in range(self.ui.listWidget.count()):
            if self.ui.listWidget.item(x).text() == file_['name']:
                self.ui.listWidget.setCurrentRow(x)
                break
        self.ui.listWidget.blockSignals(False)
        self.file_ = file_
        if "start" not in self.file_:
            self.file_['start'] = 0
        sql_values = []
        try:
            file_result = self.app.get_file_texts([file_['id']])[0]
        except IndexError:
            # Error occurs when file opened here but also deleted in ManageFiles
            self.file_ = None
            return
        if "end" not in self.file_:
            self.file_['end'] = len(file_result['fulltext'])
        sql_values.append(int(file_result['id']))
        # Determine start line
        if self.file_['start'] == 0:
            self.file_['start_line'] = 1
        else:
            text_before = file_result['fulltext'][0:self.file_['start']]
            lines = text_before.splitlines()
            self.file_['start_line'] = len(lines) + 1
        self.number_bar.set_first_line(self.file_['start_line'], do_update=False)
        self.text = file_result['fulltext'][self.file_['start']:self.file_['end']]
        # having '\n' at the end of the text sometimes creates an empty line in QTextEdit, so omit it
        if self.text.endswith('\n'):
            self.text = self.text[:-1]
        self.detect_text_direction()
        self.ui.plainTextEdit.setPlainText(self.text)

        # margin visibility handled via layout container; sync with preference <- L
        if hasattr(self, 'coding_margin') and self.coding_margin is not None:
            self.coding_margin.setVisible(self.show_margin_stripes)
        self._set_margin_container_visibility(self.show_margin_stripes)

        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        self.show_all_codes_in_text()  # Deactivates the show_selected_code if this is active
        self.setWindowTitle(_("Code text: ") + self.file_['name'])
        self.ui.lineEdit_search.setEnabled(True)
        self.ui.checkBox_search_case.setEnabled(True)
        self.ui.checkBox_search_all_files.setEnabled(True)

        # ensure the margin is repainted with the new file's codes <- L
        if hasattr(self, 'coding_margin') and self.coding_margin is not None:
            self.coding_margin.update()

    def detect_text_direction(self):
        for char in self.text:
            bidi = unicodedata.bidirectional(char)
            if bidi == "L":
                self.layout_direction = "LtoR"
                option = self.ui.plainTextEdit.document().defaultTextOption()
                option.setTextDirection(Qt.LayoutDirection.LeftToRight)
                option.setAlignment(Qt.AlignmentFlag.AlignLeft)
                self.ui.plainTextEdit.document().setDefaultTextOption(option)
                return
            if bidi in ("R", "AL"):
                self.ui.plainTextEdit.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
                self.layout_direction = "RtoL"
                option = self.ui.plainTextEdit.document().defaultTextOption()
                option.setTextDirection(Qt.LayoutDirection.RightToLeft)
                option.setAlignment(Qt.AlignmentFlag.AlignRight)
                self.ui.plainTextEdit.document().setDefaultTextOption(option)
                return

    def get_coded_text_update_eventfilter_tooltips(self):
        """ Called by load_file, and from other dialogs on update.
        Tooltips are for all coded_text or only for important if important is flagged.
        """

        if self.file_ is None:
            return
        sql_values = [int(self.file_['id']), self.file_['start'], self.file_['end']]
        # Get code text for this file and for visible coders
        self.code_text = []
        # seltext length, longest first, so overlapping shorter text is superimposed.
        sql = "select code_text_visible.ctid, code_text_visible.cid, fid, seltext, pos0, pos1, code_text_visible.owner, code_text_visible.date, " \
              "code_text_visible.memo, important, name"
        sql += " from code_text_visible join code_name on code_text_visible.cid = code_name.cid"
        sql += " where fid=?"
        # For file text which is currently loaded
        sql += " and pos0 >=? and pos1 <=? "
        sql += "order by length(seltext) desc, important asc"
        cur = self.app.conn.cursor()
        cur.execute(sql, sql_values)
        code_results = cur.fetchall()
        keys = 'ctid', 'cid', 'fid', 'seltext', 'pos0', 'pos1', 'owner', 'date', 'memo', 'important', 'name'
        for row in code_results:
            item = dict(zip(keys, row))  # ajustado
            # inject 'color' so CodingMargin can use it directly <- L
            for c in self.codes:
                if c['cid'] == item['cid']:
                    item['color'] = c['color']
                    break
            if 'color' not in item:
                item['color'] = '#cccccc'
            self.code_text.append(item)
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
        cursor = self.ui.plainTextEdit.textCursor()
        cursor.setPosition(0, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(len(self.text), QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(QtGui.QTextCharFormat())

    def _apply_format_to_code_item(self, item, codes_lookup):  # <- L
        """ Apply highlight formatting to a single coded text item.
        Extracted from highlight() so it can be reused by the incremental
        refresh path in mark(). Honors self.highlight_style and important state.
        Wraps mergeCharFormat with setUpdatesEnabled(False/True) to coalesce
        paints (critical in 'marker' mode on large files). """

        if self.file_ is None:
            return
        fmt = QtGui.QTextCharFormat()
        cursor = self.ui.plainTextEdit.textCursor()
        cursor.setPosition(int(item['pos0'] - self.file_['start']),
                           QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(int(item['pos1'] - self.file_['start']),
                           QtGui.QTextCursor.MoveMode.KeepAnchor)
        color = codes_lookup.get(item['cid'], {}).get('color', "#777777")

        if self.highlight_style == 'underline':
            fmt.setUnderlineStyle(QtGui.QTextCharFormat.UnderlineStyle.DashUnderline)
            fmt.setUnderlineColor(QColor(color))
        else:
            brush = QBrush(QColor(color))
            fmt.setBackground(brush)
            text_brush = QBrush(QColor(TextColor(color).recommendation))
            fmt.setForeground(text_brush)

        if item.get('memo', '') != "":
            fmt.setFontItalic(True)
        else:
            fmt.setFontItalic(False)
        if item.get('important'):
            fmt.setFontWeight(QtGui.QFont.Weight.Bold)

        self.ui.plainTextEdit.setUpdatesEnabled(False)
        try:
            cursor.mergeCharFormat(fmt)
        finally:
            self.ui.plainTextEdit.setUpdatesEnabled(True)

    def _mark_incremental_refresh(self, new_coded):  # <- L
        """ Lightweight refresh after a single mark() insertion.
        Replaces the full cascade (get_coded_text_update_eventfilter_tooltips ->
        unlight -> highlight) with the minimum steps needed after marking ONE
        new code:
          1) format the new code's range only
          2) refresh the tooltip event filter with the updated self.code_text
          3) apply overlap underlines that involve the new code only
             (skipped in 'underline' mode or when 'important' filter is on)
          4) repaint the side margin """

        if self.file_ is None:
            return
        codes_lookup = {x['cid']: x for x in self.codes}
        # 1) Format the newly added code only (skip if 'important' filter is on
        #    and this new code is not important, to stay consistent with the
        #    filtered view and the margin). <- L
        if not (self.important and new_coded.get('important') != 1):
            self._apply_format_to_code_item(new_coded, codes_lookup)
        # 2) Refresh tooltip event filter (uses self.code_text, already extended)
        if self.important:
            imp_coded = [c for c in self.code_text if c.get('important') == 1]
            self.eventFilterTT.set_codes_and_annotations(
                self.app, imp_coded, self.codes, self.annotations, self.file_)
        else:
            self.eventFilterTT.set_codes_and_annotations(
                self.app, self.code_text, self.codes, self.annotations, self.file_)
        # 3) Underline overlaps that involve the new code (O(n) instead of O(n^2))
        if not self.important and getattr(self, 'highlight_style', 'marker') != 'underline':
            self._apply_overlap_underlines_for_code(new_coded)
        # 4) Repaint the side margin
        if hasattr(self, 'coding_margin') and self.coding_margin is not None:
            self.coding_margin.update()

    def _apply_overlap_underlines_for_code(self, new_coded):  # <- L
        """ Underline the overlap regions between 'new_coded' and the rest of
        self.code_text. Same visual style as apply_underline_to_overlaps but
        O(n) instead of O(n^2): only the new code is compared against existing
        ones. Batches mergeCharFormat inside one setUpdatesEnabled window. """

        if self.file_ is None:
            return
        new_p0 = new_coded['pos0']
        new_p1 = new_coded['pos1']
        if new_p0 == new_p1:
            return

        cursor = self.ui.plainTextEdit.textCursor()
        fmt = QtGui.QTextCharFormat()
        fmt.setUnderlineStyle(QtGui.QTextCharFormat.UnderlineStyle.SingleUnderline)
        if self.app.settings['stylesheet'] == 'dark':
            fmt.setUnderlineColor(QColor("#000000"))
        else:
            fmt.setUnderlineColor(QColor("#FFFFFF"))

        self.ui.plainTextEdit.setUpdatesEnabled(False)
        try:
            for other in self.code_text:
                if other is new_coded:
                    continue
                if (other.get('ctid') is not None
                        and new_coded.get('ctid') is not None
                        and other['ctid'] == new_coded['ctid']):
                    continue
                o_p0 = other['pos0']
                o_p1 = other['pos1']
                ov_start = max(new_p0, o_p0)
                ov_end = min(new_p1, o_p1)
                if ov_start >= ov_end:
                    continue
                cursor.setPosition(ov_start - self.file_['start'],
                                   QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(ov_end - self.file_['start'],
                                   QtGui.QTextCursor.MoveMode.KeepAnchor)
                cursor.mergeCharFormat(fmt)
        finally:
            self.ui.plainTextEdit.setUpdatesEnabled(True)

    def highlight(self):
        """ Apply text highlighting to current file.
        If no colour has been assigned to a code, those coded text fragments are coloured gray.
        Each code text item contains: fid, date, pos0, pos1, seltext, cid, status, memo,
        name, owner.
        For defined colours in color_selector, make text light on dark, and conversely dark on light
        """

        if self.file_ is None or self.ui.plainTextEdit.toPlainText() == "":
            # still refresh the side margin so it clears properly <- L
            if hasattr(self, 'coding_margin') and self.coding_margin is not None:
                self.coding_margin.update()
            return
        # Add coding highlights
        codes = {x['cid']: x for x in self.codes}
        for item in self.code_text:
            fmt = QtGui.QTextCharFormat()
            cursor = self.ui.plainTextEdit.textCursor()
            cursor.setPosition(int(item['pos0'] - self.file_['start']), QtGui.QTextCursor.MoveMode.MoveAnchor)
            cursor.setPosition(int(item['pos1'] - self.file_['start']), QtGui.QTextCursor.MoveMode.KeepAnchor)
            color = codes.get(item['cid'], {}).get('color', "#777777")  # default gray

            # choose between underline-only and full background fill <- L
            if self.highlight_style == 'underline':
                fmt.setUnderlineStyle(QtGui.QTextCharFormat.UnderlineStyle.DashUnderline)
                fmt.setUnderlineColor(QColor(color))
            else:
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
                cursor.mergeCharFormat(fmt)  # merge so underline composes correctly <- L
            # Show all codes, as important button not selected
            if not self.important:
                cursor.mergeCharFormat(fmt)  # merge so underline composes correctly <- L

        # Add annotation marks - these are in bold, important codings are also bold
        for note in self.annotations:
            if len(self.file_.keys()) > 0:  # will be zero if using autocode and no file is loaded
                # Cursor pos could be negative if annotation was for an earlier text portion
                cursor = self.ui.plainTextEdit.textCursor()
                if note['fid'] == self.file_['id'] and \
                        0 <= int(note['pos0']) - self.file_['start'] < int(note['pos1']) - self.file_['start'] <= \
                        len(self.ui.plainTextEdit.toPlainText()):
                    cursor.setPosition(int(note['pos0']) - self.file_['start'],
                                       QtGui.QTextCursor.MoveMode.MoveAnchor)
                    cursor.setPosition(int(note['pos1']) - self.file_['start'],
                                       QtGui.QTextCursor.MoveMode.KeepAnchor)
                    format_bold = QtGui.QTextCharFormat()
                    format_bold.setFontWeight(QtGui.QFont.Weight.Bold)
                    cursor.mergeCharFormat(format_bold)
        self.apply_underline_to_overlaps()

        # refresh the side margin widget after highlights change <- L
        if hasattr(self, 'coding_margin') and self.coding_margin is not None:
            self.coding_margin.update()

    def apply_underline_to_overlaps(self):
        """ Apply underline format to coded text sections which are overlapping.
        Qt underline options: # NoUnderline, SingleUnderline, DashUnderline, DotLine, DashDotLine, WaveUnderline
        Adjust for start of text file, as this may be a smaller portion of the full text file.
        """

        if self.important:
            return
        # skip in 'underline' mode to preserve per-code dashed coloured <- L
        # underlines (a flat mono-coloured underline would hide the code colour).
        if getattr(self, 'highlight_style', 'marker') == 'underline':
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
        cursor = self.ui.plainTextEdit.textCursor()
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
        self.clear_edit_variables()
        item = self.ui.treeWidget.currentItem()
        if item is None:
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec()
            return
        if item.text(1).split(':')[0] == 'catid':  # Cannot mark with category
            return
        cid = int(item.text(1).split(':')[1])
        selected_text = self.ui.plainTextEdit.textCursor().selectedText()
        pos0 = self.ui.plainTextEdit.textCursor().selectionStart() + self.file_['start']
        pos1 = self.ui.plainTextEdit.textCursor().selectionEnd() + self.file_['start']
        if pos0 == pos1:
            return

        # Add the coded section to code text, add to database and update GUI
        coded = {'cid': cid, 'fid': int(self.file_['id']), 'seltext': selected_text,
                 'pos0': pos0, 'pos1': pos1, 'owner': self.app.settings['codername'], 'memo': "",
                 'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                 'important': None}
        # inject name and color from self.codes so CodingMargin and the
        # incremental refresh can use them directly without re-querying the DB. <- L
        for _c in self.codes:
            if _c['cid'] == cid:
                coded['name'] = _c['name']
                coded['color'] = _c['color']
                break
        if 'color' not in coded:
            coded['color'] = '#cccccc'

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
        # capture the new ctid so the incremental refresh can identify
        # this exact segment (used to skip self-overlap) <- L
        cur.execute("select last_insert_rowid()")
        coded['ctid'] = cur.fetchone()[0]
        self.code_text.append(coded)  # moved AFTER ctid is known <- L
        self.app.conn.commit()
        self.app.delete_backup = False

        # Add AI interpretation?
        if self.ui.tabWidget.currentIndex() == 1:  # ai search
            ai_search_result = self.get_overlapping_ai_search_result()
            if ai_search_result is not None:
                memo = _("AI interpretation: ") + ai_search_result["interpretation"]
                memo += _("\n\nAI search prompt: ") + prompt_name_and_scope(self.ai_search_prompt)
                memo += _("\nAI model: ") + self.ai_search_ai_model

                msg = '<p style="font-size: ' + str(self.app.settings['fontsize']) + 'pt">'
                msg += _("Do you want to store the AI interpretation in a memo together with the coding?<br/><br/>")
                msg += '<i>' + memo.replace('\n', '<br/>') + '</i></p>'
                reply = QtWidgets.QMessageBox.question(
                    self, _('AI Interpretation'), msg,
                    QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                    QtWidgets.QMessageBox.StandardButton.Yes
                )
                if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                    # Dictionary with cid fid seltext owner date name color memo
                    cur = self.app.conn.cursor()
                    cur.execute(
                        "update code_text set memo=? where cid=? and fid=? and seltext=? and pos0=? and pos1=? and owner=?",
                        (memo, coded['cid'], coded['fid'], coded['seltext'], coded['pos0'],
                         coded['pos1'],
                         coded['owner']))
                    self.app.conn.commit()
                    self.code_text[len(self.code_text) - 1]['memo'] = memo

        # Replace the full cascade <- L
        # (get_coded_text_update_eventfilter_tooltips -> unlight -> highlight)
        # by an incremental refresh that only formats the new code's range and
        # the overlaps it introduces. On large files with many codes this turns
        # a slow op into a near-instant one with no visible difference.
        self._mark_incremental_refresh(coded)  # was get_coded_text_update_eventfilter_tooltips() <- L
        self.fill_code_counts_in_tree()
        # Update recent_codes
        tmp_code = None
        for c in self.codes:
            if c['cid'] == cid:
                tmp_code = c
        if tmp_code is None:
            return
        # Need to remove from recent_codes, if there and add back in first position, and update project recently_used_codes
        for item in self.recent_codes:
            if item == tmp_code:
                self.recent_codes.remove(item)
                break
        self.recent_codes.insert(0, tmp_code)
        if len(self.recent_codes) > 9:
            self.recent_codes = self.recent_codes[:9]
        recent_codes_string = ""
        for r in self.recent_codes:
            recent_codes_string += f" {r['cid']}"
        recent_codes_string = recent_codes_string[1:]
        cur.execute("update project set recently_used_codes=?", [recent_codes_string])
        self.app.conn.commit()

        self.update_file_tooltip()  # Number of codes applied

    def undo_last_unmarked_code(self):
        """ Restore the last deleted code(s).
        One code or multiple, depends on what was selected when the unmark method was used.
        Requires self.undo_deleted_codes
        Called by : ? """

        if not self.undo_deleted_codes:
            return
        self.clear_edit_variables()
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
        """ Remove code marking by all visible coders from selected text in current file.
        Called by text_edit_context_menu
        Adjust for start of text file, as this may be a smaller portion of the full text file.

        Args:
            location: text cursor location, Integer
        """

        if self.file_ is None:
            return
        self.clear_edit_variables()
        unmarked_list = []
        for item in self.code_text:
            if item['pos0'] <= location + self.file_['start'] <= item['pos1']:
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
        Args:
        cursor_pos : None or integer
        """

        if self.file_ is None:
            Message(self.app, _('Warning'), _("No file was selected"), "warning").exec()
            return
        self.clear_edit_variables()
        pos0 = self.ui.plainTextEdit.textCursor().selectionStart()
        pos1 = self.ui.plainTextEdit.textCursor().selectionEnd()
        text_length = len(self.ui.plainTextEdit.toPlainText())
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
                    details = f"{item['owner']} {item['date']}"
                    break
        if cursor_pos is not None:  # Try point position, if cursor is on an annotation, but no text selected
            for note in self.annotations:
                if cursor_pos + self.file_['start'] >= note['pos0'] and cursor_pos <= note['pos1'] + self.file_['start'] \
                        and note['fid'] == self.file_['id']:
                    item = note  # use existing annotation
                    details = f"{item['owner']} {item['date']}"
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

    def button_autocode_surround(self):
        """ Autocode with selected code using start and end marks.
         Uses selected files.
         Line ending text representation \\n is replaced with the actual line ending character.
         Activated by: self.ui.pushButton_auto_code_surround
         Regex is not used for this function
         """

        self.clear_edit_variables()
        item = self.ui.treeWidget.currentItem()
        if item is None or item.text(1)[0:3] == 'cat':
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec()
            return
        ui = DialogGetStartAndEndMarks("Autocoding", "Autocoding surround")
        ok = ui.exec()
        if not ok:
            return
        start_mark = ui.get_start_mark()
        if "\\n" in start_mark:
            start_mark = start_mark.replace("\\n", "\n")
        end_mark = ui.get_end_mark()
        if "\\n" in end_mark:
            end_mark = end_mark.replace("\\n", "\n")
        if start_mark == "" or end_mark == "":
            Message(self.app, _('Warning'), _("Cannot have blank text marks"), "warning").exec()
            return

        ui = DialogSelectItems(self.app, self.files, _("Select files to code"), "many")
        ok = ui.exec()
        if not ok:
            return
        files = ui.get_selected()
        if len(files) == 0:
            return

        msg = _("Code text using start and end marks: ")
        msg += _("\nUsing ") + start_mark + _(" and ") + end_mark + "\n"
        cur = self.app.conn.cursor()
        cid = int(item.text(1)[4:])
        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")

        # Find text chunks and insert coded into database
        already_assigned = 0
        entries = 0
        undo_list = []
        for f in files:
            text_starts = [match.start() for match in re.finditer(re.escape(start_mark), f['fulltext'])]
            text_ends = [match.start() for match in re.finditer(re.escape(end_mark), f['fulltext'])]
            emojis = emoji.emoji_list(f['fulltext'])
            try:
                for start_pos in text_starts:
                    # pos1 = -1  # Default if not found. Not Used
                    text_end_iterator = 0
                    try:
                        while start_pos >= text_ends[text_end_iterator]:
                            text_end_iterator += 1
                    except IndexError:
                        text_end_iterator = -1
                    if text_end_iterator >= 0:
                        pos1 = text_ends[text_end_iterator]

                        # Check if already coded in this file for this coder
                        sql = "select cid from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?"
                        cur.execute(sql, [cid, f['id'], start_pos, pos1, self.app.settings['codername']])
                        res = cur.fetchone()
                        if res is None:
                            seltext = f['fulltext'][start_pos: pos1]

                            # Check and add emoji character length, after seltext is selected
                            for emo in emojis:
                                if emo['match_end'] < start_pos:
                                    # Emojis can be 2 or more characters in length
                                    start_pos += emo['match_end'] - emo['match_start']
                                    pos1 += emo['match_end'] - emo['match_start']
                                if start_pos <= emo['match_end'] <= pos1:
                                    pos1 += emo['match_end'] - emo['match_start']

                            sql = "insert into code_text (cid, fid, seltext, pos0, pos1, owner, date, memo) values(?,?,?,?,?,?,?,?)"
                            cur.execute(sql, (cid, f['id'], seltext, start_pos, pos1,
                                              self.app.settings['codername'], now_date, ""))
                            # Add to undo auto-coding history
                            undo = {
                                "sql": "delete from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?",
                                "cid": cid, "fid": f['id'], "pos0": start_pos, "pos1": pos1,
                                "owner": self.app.settings['codername']
                            }
                            undo_list.append(undo)
                            entries += 1
                        else:
                            already_assigned += 1
                self.app.conn.commit()
            except Exception as e_:
                print(e_)
                self.app.conn.rollback()  # Revert all changes
                raise
        # Add to undo auto-coding history
        if len(undo_list) > 0:
            name = _("Coding using start and end marks") + _("\nCode: ") + item.text(0)
            name += _("\nWith start mark: ") + start_mark + _("\nEnd mark: ") + end_mark
            undo_dict = {"name": name, "sql_list": undo_list}
            self.autocode_history.insert(0, undo_dict)

        # Update filter for tooltip and update code colours
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        msg += str(entries) + _(" new coded sections found.") + "\n"
        if already_assigned > 0:
            msg += f"{already_assigned} " + _("previously coded.") + "\n"
        self.parent_textEdit.append(msg)
        Message(self.app, "Autocode surround", msg).exec()
        self.app.delete_backup = False

    def undo_autocoding(self):
        """ Present a list of choices for the undo operation.
         Use selects and undoes the chosen autocoding operation.
         The autocode_history is a list of dictionaries with 'name' and 'sql_list' """

        if not self.autocode_history:
            return
        ui = DialogSelectItems(self.app, self.autocode_history, _("Select auto-codings to undo"), "single")
        ok = ui.exec()
        if not ok:
            return
        self.clear_edit_variables()
        undo = ui.get_selected()
        # Run all sqls
        cur = self.app.conn.cursor()
        try:
            for i in undo['sql_list']:
                cur.execute(i['sql'], [i['cid'], i['fid'], i['pos0'], i['pos1'], i['owner']])
            self.app.conn.commit()
        except Exception as e_:
            print(e_)
            self.app.conn.rollback()  # Revert all changes
            raise
        self.autocode_history.remove(undo)
        self.parent_textEdit.append(_("Undo autocoding: ") + f"{undo['name']}\n")

        # Update filter for tooltip and update code colours
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()

    def auto_code_sentences(self):
        """ Code full sentence based on text fragment.
        Activated via self.ui.pushButton_auto_code_frag_this_file
        Opens a dialog to select text files for autocoding.
        Button Right-click options are: all (default), first, last, code within code.
        """

        ui = DialogSelectItems(self.app, self.files, _("Select files to code"), "many")
        ok = ui.exec()
        if not ok:
            return
        files = ui.get_selected()
        if len(files) == 0:
            return
        item = self.ui.treeWidget.currentItem()
        if item is None or item.text(1)[0:3] == 'cat':
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec()
            return
        self.clear_edit_variables()
        cid = int(item.text(1).split(':')[1])
        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
        dialog.setWindowTitle(_("Code sentence"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog.setLabelText(_("Auto code sentence using this text fragment:"))
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        find_text = dialog.textValue()
        if find_text == "":
            return
        dialog_sentence_end = QtWidgets.QInputDialog(None)
        dialog_sentence_end.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
        dialog_sentence_end.setWindowTitle(_("Code sentence"))
        dialog_sentence_end.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog_sentence_end.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog_sentence_end.setToolTip("Use \\n for line ending")
        dialog_sentence_end.setLabelText(
            _("Define sentence ending. Default is period space.\nUse \\n for line ending:"))
        dialog_sentence_end.setTextValue(". ")
        dialog_sentence_end.resize(200, 40)
        ok2 = dialog_sentence_end.exec()
        if not ok2:
            return
        ending = dialog_sentence_end.textValue()
        if ending == "":
            return
        ending = ending.replace("\\n", "\n")

        cur = self.app.conn.cursor()
        msg = ""
        undo_list = []

        # Regex
        regex_pattern = None
        if self.ui.checkBox_auto_regex.isChecked():
            try:
                regex_pattern = re.compile(find_text)
            except re.error as e_:
                logger.warning('re error Bad escape ' + str(e_))
                Message(self.app, _("Regex compilation error"), str(e_))
            if regex_pattern is None:
                return

        try:
            for f in files:
                sentences = f['fulltext'].split(ending)
                pos0 = 0
                codes_added = 0
                surround_codes = []
                if self.autocode_frag_all_first_within.startswith("code_within_code"):
                    cur.execute("select pos0,pos1 from code_text where cid=? and fid=? and owner=?",
                                [int(self.autocode_frag_all_first_within.split()[1]), f['id'],
                                 self.app.settings['codername']])
                    surround_codes = cur.fetchall()
                    if not surround_codes:
                        return

                emojis = emoji.emoji_list(f['fulltext'])

                for sentence in sentences:
                    if (find_text in sentence and not regex_pattern) or (
                            regex_pattern and regex_pattern.search(sentence)):
                        i = {'cid': cid, 'fid': int(f['id']), 'seltext': str(sentence),
                             'pos0': pos0, 'pos1': pos0 + len(sentence),
                             'owner': self.app.settings['codername'], 'memo': "",
                             'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}

                        # Check and add emoji character length
                        for emo in emojis:
                            if emo['match_end'] < i['pos0']:
                                # Emojis can be 2 or more characters in length
                                i['pos0'] += emo['match_end'] - emo['match_start']
                                i['pos1'] += emo['match_end'] - emo['match_start']
                            if i['pos0'] <= emo['match_end'] <= i['pos1']:
                                i['pos1'] += emo['match_end'] - emo['match_start']

                        # For code within a code, if selected
                        found_code_in_code = False
                        if self.autocode_frag_all_first_within.startswith("code_within_code"):
                            for surround_code in surround_codes:
                                if i['pos0'] >= surround_code[0] and i['pos1'] <= surround_code[1]:
                                    found_code_in_code = True
                                    # print("Found", surround_code[0], "[", i['pos0'], i['pos1'], "]", surround_code[1], sentence)

                        if self.autocode_frag_all_first_within in ("all", "first") or found_code_in_code:
                            try:
                                codes_added += 1
                                cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,\
                                    owner,memo,date) values(?,?,?,?,?,?,?,?)",
                                            (i['cid'], i['fid'], i['seltext'], i['pos0'],
                                             i['pos1'], i['owner'], i['memo'], i['date']))
                                # Store a list of undo sql
                                undo = {
                                    "sql": "delete from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?",
                                    "cid": i['cid'], "fid": i['fid'], "pos0": i['pos0'], "pos1": i['pos1'],
                                    "owner": i['owner']
                                }
                                undo_list.append(undo)
                                self.app.conn.commit()
                            except Exception as e:  # Possible Unique constraint fail
                                print("Autocode insert error ", str(e))
                                logger.debug(_("Autocode insert error ") + str(e))
                    pos0 += len(sentence) + len(ending)  # move forward
                    if codes_added == 1 and self.autocode_frag_all_first_within == "first":
                        break
                if codes_added > 0:
                    msg += _("File: ") + f"{f['name']} {codes_added}" + _(" added codes") + "\n"
        except Exception as e_:
            print(e_)
            self.app.conn.rollback()  # revert all changes
            # undo_list = []
            raise
        if len(undo_list) > 0:
            name = _("Sentence coding: ") + _("\nCode: ") + item.text(0)
            name += _("\nWith: ") + find_text + _("\nUsing line ending: ") + ending
            undo_dict = {"name": name, "sql_list": undo_list}
            self.autocode_history.insert(0, undo_dict)
        self.parent_textEdit.append(_("Automatic code sentence in files:")
                                    + _("\nCode: ") + item.text(0)
                                    + _("\nWith text fragment: ")
                                    + find_text
                                    + _("\nUsing line ending: ")
                                    + ending + "\n" + msg)
        self.app.delete_backup = False
        # Update tooltip filter and code tree code counts
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()

    def auto_code(self):
        """ Autocode text in one file or all files with currently selected code.
        Button menu option to auto-code all, first or last instances in files, or to code within an existing code.
        Split multiple find texts with pipe |
        Activated using self.ui.pushButton_auto_code
        """

        code_item = self.ui.treeWidget.currentItem()
        if code_item is None or code_item.text(1)[0:3] == 'cat':
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec()
            return
        cid = int(code_item.text(1).split(':')[1])
        # Input dialog too narrow, so code below to widen dialog
        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
        dialog.setWindowTitle(_("Automatic coding"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog.setToolTip(_("Use | to code multiple texts"))
        if self.ui.checkBox_auto_regex.isChecked():
            dialog.setLabelText(_("Auto code files with the current code using Regex:") + "\n" + code_item.text(0))
        else:
            dialog.setLabelText(_("Auto code files with the current code for this text:") + "\n" + code_item.text(0))
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        find_text = str(dialog.textValue())
        if find_text == "" or find_text is None:
            return
        texts_ = find_text.split('|')
        tmp = list(set(texts_))
        find_texts = []
        for t in tmp:
            if t != "":
                find_texts.append(t)
        # Regex, pipe | has different meaning, so do not split into separate texts
        if self.ui.checkBox_auto_regex.isChecked():
            find_texts = [find_text]
        if len(self.files) == 0:
            return
        ui = DialogSelectItems(self.app, self.files, _("Select files to code"), "many")
        ok = ui.exec()
        if not ok:
            return
        files = ui.get_selected()
        if len(files) == 0:
            return
        self.clear_edit_variables()

        # Regex
        regex_pattern = None
        if self.ui.checkBox_auto_regex.isChecked():
            try:
                regex_pattern = re.compile(find_texts[0])
            except re.error as e_:
                logger.warning('Regex error Bad escape ' + str(e_))
                Message(self.app, _("Regex compilation error"), str(e_))
            if regex_pattern is None:
                return

        found_instances = 0
        undo_list = []
        msg = _("Autocode Text") + f": {self.autocode_all_first_last_within} : {find_texts}"
        if self.ui.checkBox_auto_regex.isChecked():
            msg += " : Using REGEX"
        msg += "\n"
        cur = self.app.conn.cursor()
        try:
            for find_txt in find_texts:
                for f in files:
                    cur.execute("select name, id, fulltext, memo, owner, date from source where id=? and "
                                "(mediapath is null or mediapath like '/docs/%' or mediapath like 'docs:%')",
                                [f['id']])
                    current_file = cur.fetchone()
                    # Rare but possible no result is returned.
                    if current_file is None:
                        logger.error(f"File not found,  file id: {f['id']}")
                        continue
                    file_text = current_file[2]
                    emojis = emoji.emoji_list(file_text)
                    text_starts = []
                    text_ends = []
                    if regex_pattern:
                        for match in regex_pattern.finditer(file_text):
                            text_starts.append(match.start())
                            text_ends.append(match.end())
                    else:
                        text_starts = [match.start() for match in re.finditer(re.escape(find_txt), file_text)]
                        text_ends = [match.end() for match in re.finditer(re.escape(find_txt), file_text)]
                    # print("TEXT STARTS FOUND", len(text_starts), f['name'])
                    msg += f"{f['name']}: {len(text_starts)}. "

                    # Trim to first instance if option selected
                    if self.autocode_all_first_last_within == "first" and len(text_starts) > 1:
                        text_starts = [text_starts[0]]
                        text_ends = [text_ends[0]]
                    # Trim to last instance if option selected
                    if self.autocode_all_first_last_within == "last" and len(text_starts) > 1:
                        text_starts = [text_starts[-1]]
                        text_ends = [text_ends[-1]]
                    # Trim to within_existing_code instances if this option is selected
                    if self.autocode_all_first_last_within.startswith("code_within_code"):
                        cur.execute("select pos0,pos1 from code_text where cid=? and fid=? and owner=?",
                                    [int(self.autocode_all_first_last_within.split()[1]), f['id'],
                                     self.app.settings['codername']])
                        res = cur.fetchall()
                        within_starts = []
                        within_ends = []
                        for r in res:
                            for i in range(0, len(text_starts)):
                                if text_starts[i] >= r[0] and text_ends[i] <= r[1]:
                                    within_starts.append(text_starts[i])
                                    within_ends.append(text_ends[i])
                        text_starts = within_starts
                        text_ends = within_ends

                    # Add new items to database
                    for index in range(len(text_starts)):
                        seltext = str(find_txt)
                        # Using Regex, need to get each matching text
                        if self.ui.checkBox_auto_regex.isChecked():
                            pos0 = text_starts[index] + 1  # need +1 for substr()
                            length = text_ends[index] - pos0 + 1
                            cur.execute("select substr(fulltext,?,?) from source where id=?", [pos0, length, int(f['id'])])
                            res = cur.fetchone()
                            if res:
                                seltext = res[0]

                        pos0 = text_starts[index]
                        pos1 = text_ends[index]
                        # Have the seltext, now adjust pos0, pos1 for emoji length, by adding to the character positions
                        for emo in emojis:
                            if emo['match_end'] < pos0:
                                # Emojis can be 2 or more characters in length
                                pos0 += emo['match_end'] - emo['match_start']
                                pos1 += emo['match_end'] - emo['match_start']
                        item = {'cid': cid, 'fid': int(f['id']), 'seltext': seltext,
                                'pos0': pos0, 'pos1': pos1,
                                'owner': self.app.settings['codername'], 'memo': "",
                                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
                        try:
                            found_instances += 1
                            cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,\
                                owner,memo,date) values(?,?,?,?,?,?,?,?)",
                                        [item['cid'], item['fid'], item['seltext'], item['pos0'],
                                         item['pos1'], item['owner'], item['memo'], item['date']])
                            # Record a list of undo sql
                            undo = {
                                "sql": "delete from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?",
                                "cid": item['cid'], "fid": item['fid'], "pos0": item['pos0'], "pos1": item['pos1'],
                                "owner": item['owner']}
                            undo_list.append(undo)
                        except sqlite3.IntegrityError as err:
                            # print(_("Autocode insert error ") + str(err))  # Possible a duplicate entry
                            logger.debug(_("Autocode insert error ") + str(err))
                        self.app.delete_backup = False
                self.app.conn.commit()
        except Exception as err:
            print(err)
            self.app.conn.rollback()  # Revert all changes
            logger.error(f"auto_code rollback. {err}")
            self.parent_textEdit.append(_("Autocoding error: ") + str(err))
            # undo_list = []
            raise
        if len(undo_list) > 0:
            name = _("Text coding: ") + _("\nCode: ") + code_item.text(0)
            name += _("\nWith: ") + find_text
            undo_dict = {"name": name, "sql_list": undo_list}
            self.autocode_history.insert(0, undo_dict)
        # Update action log, tooltip filter and code tree code counts
        self.parent_textEdit.append(msg)
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()

    # Methods for Editing mode
    def undo_edited_text(self):
        """ Revert to the text prior to it being edited. """

        if self.edit_original_source is None:
            print("Should not occur")
            return
        cursor = self.app.conn.cursor()
        cursor.execute("update source set fulltext=? where id=?",
                       [self.edit_original_source, self.edit_original_source_id])
        # print("source id:", self.edit_original_source_id)
        # print("Source: ", self.edit_original_source)
        # print("Codes:", self.edit_original_codes)
        for c in self.edit_original_codes:
            cursor.execute("update code_text set seltext=?, pos0=?, pos1=? where ctid=?",
                           [c[1], c[2], c[3], c[0]])
        # print("annotes:", self.edit_original_annotations)
        for a in self.edit_original_annotations:
            cursor.execute("update annotation set pos0=?, pos1=? where anid=?",
                           [a[1], a[2], a[0]])
        # print("Case assignment", self.edit_original_case_assignment)
        for ca in self.edit_original_case_assignment:
            cursor.execute("update case_text set pos0=?, pos1=? where caseid=?",
                           [ca[1], ca[2], ca[0]])
        self.clear_edit_variables()
        self.ui.plainTextEdit.installEventFilter(self.eventFilterTT)
        self.annotations = self.app.get_annotations()
        self.load_file(self.file_)
        self.update_file_tooltip()
        self.highlight()
        text_cursor = self.ui.plainTextEdit.textCursor()
        if self.edit_pos > len(self.ui.plainTextEdit.toPlainText()):
            self.edit_pos = len(self.ui.plainTextEdit.toPlainText()) - 1
        text_cursor.setPosition(self.edit_pos, QtGui.QTextCursor.MoveMode.MoveAnchor)
        self.ui.plainTextEdit.setTextCursor(text_cursor)
        msg = _("Text reverted to prior to edit")
        Message(self.app, _("Undo last edited text"), msg).exec()

    def clear_edit_variables(self):
        """ Called by undo pushbutton, or any coding, annotating, unmarking """

        self.edit_original_source = None
        self.edit_original_codes = None
        self.edit_original_annotations = None
        self.edit_original_case_assignment = None
        self.edit_original_cutoff_datetime = None
        self.edit_original_source_id = None
        self.ui.pushButton_undo_edit.setEnabled(False)

    def edit_mode_toggle(self):
        """ Activate or deactivate edit mode.
        When activated, hide most widgets, remove tooltips, remove text edit menu.
        Called: event filter Ctrl+E, or button press
        The edit mode toggle fires multiple times. so the initial edit_pos changes from the correct pos to 0
        """

        if self.file_ is None:
            return

        self.edit_mode = not self.edit_mode
        if self.edit_mode:
            self.edit_mode_on()
            self.ui.pushButton_undo_edit.setEnabled(True)
            return
        self.edit_mode_off()

    def edit_mode_on(self):
        """ Hide most widgets, remove tooltips, remove text edit menu.
        Need to load entire file, if only a section is currently loaded. """

        if self.file_ is None:
            return

        # Copy existing source and code_text codes and annotations and case text
        self.edit_original_source_id = self.file_['id']
        self.edit_original_annotations = []
        self.edit_original_codes = []
        self.edit_original_case_assignment = []
        self.edit_original_cutoff_datetime = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        cursor = self.app.conn.cursor()
        cursor.execute("select id, fulltext from source where id=?", [self.file_['id']])
        res_source = cursor.fetchone()
        self.edit_original_source = res_source[1]
        cursor.execute("select ctid, seltext,pos0,pos1 from code_text where fid=?", [self.file_['id']])
        res_codes = cursor.fetchall()
        if res_codes:
            self.edit_original_codes = res_codes
        cursor.execute("select anid, pos0,pos1 from annotation where fid=?", [self.file_['id']])
        res_annotations = cursor.fetchall()
        if res_annotations:
            self.edit_original_annotations = res_annotations
        cursor.execute("select id,pos0,pos1 from case_text where fid=?", [self.file_['id']])
        res_case = cursor.fetchall()
        if res_case:
            self.edit_original_case_assignment = res_case

        # Hide the coding margin (and its container) during edit mode <- L
        if hasattr(self, 'coding_margin') and self.coding_margin is not None:
            self.coding_margin.hide()
        self._set_margin_container_visibility(False)

        temp_edit_pos = self.ui.plainTextEdit.textCursor().position() + self.file_['start']
        if temp_edit_pos > 0:
            self.edit_pos = temp_edit_pos
        self.ui.groupBox.hide()
        self.ui.groupBox_edit_mode.show()
        self.ui.listWidget.setEnabled(False)
        self.ui.widget_left.hide()
        self.ui.groupBox_file_buttons.setEnabled(False)
        self.ui.groupBox_file_buttons.setMaximumSize(4000, 4000)
        self.ui.groupBox_coding_buttons.setEnabled(False)
        self.ui.treeWidget.setEnabled(False)
        file_result = self.app.get_file_texts([self.file_['id']])[0]
        if self.file_['end'] != len(file_result['fulltext']) and self.file_['start'] != 0:
            self.file_['start'] = 0
            self.file_['end'] = len(file_result['fulltext'])
            self.text = file_result['fulltext']
            self.ui.plainTextEdit.setPlainText(self.text)
        self.prev_text = copy(self.text)
        self.ui.plainTextEdit.removeEventFilter(self.eventFilterTT)
        self.get_cases_codings_annotations()
        self.ui.plainTextEdit.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextEditorInteraction |
            Qt.TextInteractionFlag.TextEditable
        )
        self.ed_highlight()
        self.edit_mode_has_changed = False
        self.ui.plainTextEdit.textChanged.connect(self.update_positions)
        text_cursor = self.ui.plainTextEdit.textCursor()
        if self.edit_pos >= len(self.text):
            self.edit_pos = len(self.text) - 1
        text_cursor.setPosition(self.edit_pos, QtGui.QTextCursor.MoveMode.MoveAnchor)
        self.ui.plainTextEdit.setTextCursor(text_cursor)

    def edit_mode_off(self):
        """ Show widgets.
        Try and set cursor position to 'current text' position.
        but this may have changed. """

        self.ui.groupBox.show()
        self.ui.groupBox_edit_mode.hide()
        self.ui.listWidget.setEnabled(True)
        self.ui.groupBox_file_buttons.setEnabled(True)
        self.ui.groupBox_file_buttons.setMaximumSize(4000, 30)
        self.ui.groupBox_coding_buttons.setEnabled(True)
        self.ui.treeWidget.setEnabled(True)
        self.ui.widget_left.show()
        self.prev_text = ""
        if self.edit_mode_has_changed:
            self.text = self.ui.plainTextEdit.toPlainText()
            self.file_['fulltext'] = self.text
            self.file_['end'] = len(self.text)
            cur = self.app.conn.cursor()
            cur.execute("update source set fulltext=? where id=?", (self.text, self.file_['id']))
            self.app.conn.commit()
            for item in self.code_deletions:
                cur.execute(item)
            self.app.conn.commit()
            self.code_deletions = []
            self.ed_update_codings()
            self.ed_update_annotations()
            self.ed_update_casetext()
            # Update vectorstore
            if self.app.settings['ai_enable'] == 'True':
                self.app.ai.sources_vectorstore.import_document(self.file_['id'], self.file_['name'], self.text)

        self.ui.plainTextEdit.setTextInteractionFlags(
            # make the textEdit read only by removing the 'TextEditable' flag
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.ui.plainTextEdit.installEventFilter(self.eventFilterTT)
        self.annotations = self.app.get_annotations()
        self.load_file(self.file_)
        self.update_file_tooltip()
        self.highlight()
        text_cursor = self.ui.plainTextEdit.textCursor()
        if self.edit_pos > len(self.ui.plainTextEdit.toPlainText()):
            self.edit_pos = len(self.ui.plainTextEdit.toPlainText()) - 1
        text_cursor.setPosition(self.edit_pos, QtGui.QTextCursor.MoveMode.MoveAnchor)
        self.ui.plainTextEdit.setTextCursor(text_cursor)

        # repaint the margin after exiting edit mode. load_file (called
        # above) already restores visibility based on settings <- L
        if hasattr(self, 'coding_margin') and self.coding_margin is not None:
            self.coding_margin.update()

    def edit_mode_find(self, direction:str="next"):
        """  Move forward or backward through the edit document.
        Uses REGEX.
        Args:
            direction: string '', next, previous """

        if direction == "":
            direction = "next"
        cursor = self.ui.plainTextEdit.textCursor()
        search_term = self.ui.lineEdit_edit_search.text()
        if search_term == "":
            return
        pattern = None
        flags = 0
        if not self.ui.checkBox_edit_case_sensitive.isChecked():
            flags |= re.IGNORECASE
        try:
            pattern = re.compile(search_term, flags)
        except re.error as err:
            logger.warning(f're module error Bad escape {err}')
        if pattern is None:
            return
        result = None
        try:
            if direction == "next":
                for match in pattern.finditer(self.text):
                    if match.start() > cursor.position():
                        result = match.start()
                        break
            else:  # previous
                matches = []
                for match in pattern.finditer(self.text):
                    matches.insert(0, match.start())
                for match in matches:
                    if match + len(search_term) < cursor.position():
                        result = match
                        break
        except re.error:
            logger.exception('Failed searching text for %s', search_term)
        if result is None:
            return
        cursor.setPosition(result)
        self.ui.plainTextEdit.setTextCursor(cursor)
        cursor.setPosition(cursor.position() + len(search_term), QtGui.QTextCursor.MoveMode.KeepAnchor)
        self.ui.plainTextEdit.setTextCursor(cursor)

    def update_positions(self):
        """ Update positions for code text, annotations and case text as each character changes
        via adding or deleting. uses diff-match-patch module much faster than difflib, with large text files
        that are annotated, coded, cased.

        diff_match_patch.diff_main() Output:
        Adding X at pos 0
            [(1, 'X'), (0, "I rea...")]
        Adding X at pos 4
            [(0, 'I re'), (1, 'X'), (0, "ally...")]
        Adding X at end of file
            [(0, "...appy to pay €200."), (1, 'X')]
        Removing 'really'
            [(0, 'I '), (-1, 'really'), (0, " like ...")]
        """

        self.edit_mode_has_changed = True
        if self.no_codes_annotes_cases:
            return

        self.text = self.ui.plainTextEdit.toPlainText()
        diff = diff_match_patch.diff_match_patch()
        diff_list = diff.diff_main(self.prev_text, self.text)
        # print(diff_list)
        extending = True
        preceding_pos = 0
        chars_len = 0
        pre_chars_len = 0
        post_chars_len = 0
        if len(diff_list) == 2 and diff_list[0][0] == 1:
            # print("Add at start")
            chars_len = len(diff_list[0][1])
            pre_chars_len = 0
            preceding_pos = 0
        if len(diff_list) == 2 and diff_list[0][0] == -1:
            # print("Remove from start")
            extending = False
            chars_len = len(diff_list[0][1])
            pre_chars_len = 0
            preceding_pos = 0
            post_chars_len = len(diff_list[1][1])
        if len(diff_list) == 2 and diff_list[1][0] == 1:
            # print("Add at end")
            chars_len = len(diff_list[1][1])
            pre_chars_len = len(diff_list[0][1])
            preceding_pos = pre_chars_len - 1
        if len(diff_list) == 2 and diff_list[1][0] == -1:
            # print("Remove from end")
            extending = False
            chars_len = len(diff_list[1][1])
            post_chars_len = 0
            pre_chars_len = len(diff_list[0][1])
            preceding_pos = pre_chars_len - 1
        if len(diff_list) == 3 and diff_list[1][0] == 1:
            # print("Add in middle")
            chars_len = len(diff_list[1][1])
            pre_chars_len = len(diff_list[0][1])
            preceding_pos = pre_chars_len - 1
        if len(diff_list) == 3 and diff_list[1][0] == -1:
            # print("Delete from middle")
            extending = False
            chars_len = len(diff_list[1][1])
            pre_chars_len = len(diff_list[0][1])
            preceding_pos = pre_chars_len - 1
            post_chars_len = len(diff_list[2][1])
        # Adding characters
        if extending:
            for c in self.ed_codetext:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= preceding_pos and \
                        c['newpos0'] >= preceding_pos - pre_chars_len:
                    c['newpos0'] += chars_len
                    c['newpos1'] += chars_len
                    # Also check and apply start of code is at start of text
                    if c['pos0'] == 0:
                        c['newpos0'] = 0
                    changed = True
                if not changed and c['newpos0'] is not None and c['newpos0'] < preceding_pos < c['newpos1']:
                    c['newpos1'] += chars_len

            for c in self.ed_annotations:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= preceding_pos and \
                        c['newpos0'] >= preceding_pos - pre_chars_len:
                    c['newpos0'] += chars_len
                    c['newpos1'] += chars_len
                    changed = True
                if c['newpos0'] is not None and not changed and c['newpos0'] < preceding_pos < c['newpos1']:
                    c['newpos1'] += chars_len

            for c in self.ed_casetext:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= preceding_pos and \
                        c['newpos0'] >= preceding_pos - pre_chars_len:
                    c['newpos0'] += chars_len
                    # check and apply start of case is included
                    if c['pos0'] == 0:
                        c['newpos0'] = 0
                    c['newpos1'] += chars_len
                    changed = True
                if c['newpos0'] is not None and not changed and c['newpos0'] < preceding_pos < c['newpos1']:
                    c['newpos1'] += chars_len
            self.ed_highlight()
            self.prev_text = copy(self.text)
            return
        # Removing characters
        if not extending:
            for c in self.ed_codetext:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= preceding_pos and \
                        c['newpos0'] >= preceding_pos - pre_chars_len:
                    c['newpos0'] -= chars_len
                    if c['newpos0'] < 0:
                        c['newpos0'] = 0
                    c['newpos1'] -= chars_len
                    changed = True
                # Remove, as entire text is being removed (e.g. copy replace)
                if c['newpos0'] is not None and not changed and c['newpos0'] >= preceding_pos and \
                        c['newpos1'] < preceding_pos - pre_chars_len + post_chars_len:
                    c['newpos0'] -= chars_len
                    if c['newpos0'] < 0:
                        c['newpos0'] = 0
                    c['newpos1'] -= chars_len
                    changed = True
                    self.code_deletions.append(f"delete from code_text where ctid={c['ctid']}")
                    c['newpos0'] = None
                if c['newpos0'] is not None and not changed and c['newpos0'] < preceding_pos <= c['newpos1']:
                    c['newpos1'] -= chars_len
                    if c['newpos1'] < c['newpos0']:
                        self.code_deletions.append(f"delete from code_text where ctid={c['ctid']}")
                        c['newpos0'] = None

            for c in self.ed_annotations:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= preceding_pos and \
                        c['newpos0'] >= preceding_pos - pre_chars_len:
                    c['newpos0'] -= chars_len
                    if c['newpos0'] < 0:
                        c['newpos0'] = 0
                    c['newpos1'] -= chars_len
                    changed = True
                    # Remove, as entire text is being removed (e.g. copy replace)
                    if not changed and c['newpos0'] >= preceding_pos and \
                            c['newpos1'] < preceding_pos - pre_chars_len + post_chars_len:
                        c['newpos0'] -= chars_len
                        c['newpos1'] -= chars_len
                        changed = True
                        self.code_deletions.append(f"delete from annotations where anid={c['anid']}")
                        c['newpos0'] = None
                if c['newpos0'] is not None and not changed and c['newpos0'] < preceding_pos <= c['newpos1']:
                    c['newpos1'] -= chars_len
                    if c['newpos1'] < c['newpos0']:
                        self.code_deletions.append(f"delete from annotation where anid={c['anid']}")
                        c['newpos0'] = None

            for c in self.ed_casetext:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= preceding_pos and \
                        c['newpos0'] >= preceding_pos - pre_chars_len:
                    c['newpos0'] -= chars_len
                    if c['newpos0'] < 0:
                        c['newpos0'] = 0
                    c['newpos1'] -= chars_len
                    changed = True
                # Remove, as entire text is being removed (e.g. copy replace)
                if c['newpos0'] is not None and not changed and c['newpos0'] >= preceding_pos and \
                        c['newpos1'] < preceding_pos - pre_chars_len + post_chars_len:
                    c['newpos0'] -= chars_len
                    if c['newpos0'] < 0:
                        c['newpos0'] = 0
                    c['newpos1'] -= chars_len
                    changed = True
                    self.code_deletions.append(f"delete from case_text where id={c['id']}")
                    c['newpos0'] = None
                if c['newpos0'] is not None and not changed and c['newpos0'] < preceding_pos <= c['newpos1']:
                    c['newpos1'] -= chars_len
                    if c['newpos1'] < c['newpos0']:
                        self.code_deletions.append(f"delete from case_text where id={c['id']}")
                        c['newpos0'] = None
        self.ed_highlight()
        self.prev_text = copy(self.text)

    '''def update_positions_difflib(self):
        """ OLD keep in case needed in future. 
        Update positions for code text, annotations and case text as each character changes
        via adding or deleting.

        Output: adding an e at pos 4:
        ---

        +++

        @@ -4,0 +5 @@

        +e
        """
        
        self.edit_mode_has_changed = True

        # No need to update positions (unless entire file is a case)
        if self.no_codes_annotes_cases or not self.edit_mode:
            return
        self.text = self.ui.plainTextEdit.toPlainText()
        # n is how many context lines to show
        d = list(difflib.unified_diff(self.prev_text, self.text, n=0))
        if len(d) < 4:
            return
        char = d[3]
        position = d[2][4:]  # Removes prefix @@ -
        position = position[:-4]  # Removes suffix space@@\n
        previous = position.split(" ")[0]
        pre_start = int(previous.split(",")[0])
        pre_chars = None
        try:
            pre_chars = previous.split(",")[1]
        except IndexError:
            pass
        post = position.split(" ")[1]
        post_start = int(post.split(",")[0])
        post_chars = None
        try:
            post_chars = post.split(",")[1]
        except IndexError:
            pass
        # No additions or deletions
        if pre_start == post_start and pre_chars == post_chars:
            self.highlight()
            self.prev_text = copy(self.text)
            return

        """
        Adding 'X' at inserted position 5, note: None as no number is provided from difflib
        +X  previous 4 0  post 5 None

        Adding 'qda' at inserted position 5 (After 'This')
        +q  previous 4 0  post 5 3

        Removing 'X' from position 5, note None
        -X  previous 5 None  post 4 0

        Removing 'the' from position 13
        -t  previous 13 3  post 12 0
        """
        if pre_chars is None:
            pre_chars = 1
        pre_chars = -1 * int(pre_chars)  # String if not None
        if post_chars is None:
            post_chars = 1
        post_chars = int(post_chars)  # String if not None
        # print("XXX", char, " previous", pre_start, pre_chars, " post", post_start, post_chars)
        # Adding characters
        if char[0] == "+":
            for c in self.ed_codetext:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= pre_start and c['newpos0'] >= pre_start + -1 * pre_chars:
                    c['newpos0'] += pre_chars + post_chars
                    c['newpos1'] += pre_chars + post_chars
                    changed = True
                if not changed and c['newpos0'] < pre_start < c['newpos1']:
                    c['newpos1'] += pre_chars + post_chars
            for c in self.ed_annotations:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= pre_start and c['newpos0'] >= pre_start + -1 * pre_chars:
                    c['newpos0'] += pre_chars + post_chars
                    c['newpos1'] += pre_chars + post_chars
                    changed = True
                if c['newpos0'] is not None and not changed and c['newpos0'] < pre_start < c['newpos1']:
                    c['newpos1'] += pre_chars + post_chars
            for c in self.ed_casetext:
                changed = False
                # print("newpos0", c['newpos0'], "pre start", pre_start)
                if c['newpos0'] is not None and c['newpos0'] >= pre_start and c['newpos0'] >= pre_start + -1 * pre_chars:
                    c['newpos0'] += pre_chars + post_chars
                    c['newpos1'] += pre_chars + post_chars
                    changed = True
                if c['newpos0'] is not None and not changed and c['newpos0'] < pre_start < c['newpos1']:
                    c['newpos1'] += pre_chars + post_chars
            self.ed_highlight()
            self.prev_text = copy(self.text)
            return

        # Removing characters
        if char[0] == "-":
            for c in self.ed_codetext:
                changed = False
                # print("CODE newpos0", c['newpos0'], "pre start", pre_start, pre_chars, post_chars)
                if c['newpos0'] is not None and c['newpos0'] >= pre_start and c['newpos0'] >= pre_start + -1 * pre_chars:
                    c['newpos0'] += pre_chars + post_chars
                    c['newpos1'] += pre_chars + post_chars
                    changed = True
                # Remove, as entire text is being removed (e.g. copy replace)
                # print(changed, c['newpos0'],  pre_start, c['newpos1'], pre_chars, post_chars)
                # print(c['newpos0'], ">",  pre_start, "and", c['newpos1'], "<", pre_start + -1*pre_chars + post_chars)
                if c['newpos0'] is not None and not changed and c['newpos0'] >= pre_start and \
                        c['newpos1'] < pre_start + -1 * pre_chars + post_chars:
                    c['newpos0'] += pre_chars + post_chars
                    c['newpos1'] += pre_chars + post_chars
                    changed = True
                    self.code_deletions.append("delete from code_text where ctid=" + str(c['ctid']))
                    c['newpos0'] = None
                if c['newpos0'] is not None and not changed and c['newpos0'] < pre_start <= c['newpos1']:
                    c['newpos1'] += pre_chars + post_chars
                    if c['newpos1'] < c['newpos0']:
                        self.code_deletions.append("delete from code_text where ctid=" + str(c['ctid']))
                        c['newpos0'] = None
            for c in self.ed_annotations:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= pre_start and c['newpos0'] >= pre_start + -1 * pre_chars:
                    c['newpos0'] += pre_chars + post_chars
                    c['newpos1'] += pre_chars + post_chars
                    changed = True
                    # Remove, as entire text is being removed (e.g. copy replace)
                    # print(changed, c['newpos0'],  pre_start, c['newpos1'], pre_chars, post_chars)
                    # print(c['newpos0'], ">",  pre_start, "and", c['newpos1'], "<", pre_start + -1*pre_chars + post_chars)
                    if not changed and c['newpos0'] >= pre_start and c['newpos1'] < pre_start + -1 * pre_chars + post_chars:
                        c['newpos0'] += pre_chars + post_chars
                        c['newpos1'] += pre_chars + post_chars
                        changed = True
                        self.code_deletions.append("delete from annotations where anid=" + str(c['anid']))
                        c['newpos0'] = None
                if c['newpos0'] is not None and not changed and c['newpos0'] < pre_start <= c['newpos1']:
                    c['newpos1'] += pre_chars + post_chars
                    if c['newpos1'] < c['newpos0']:
                        self.code_deletions.append("delete from annotation where anid=" + str(c['anid']))
                        c['newpos0'] = None
            for c in self.ed_casetext:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= pre_start and c['newpos0'] >= pre_start + -1 * pre_chars:
                    c['newpos0'] += pre_chars + post_chars
                    c['newpos1'] += pre_chars + post_chars
                    changed = True
                # Remove, as entire text is being removed (e.g. copy replace)
                # print(changed, c['newpos0'],  pre_start, c['nepos1'], pre_chars, post_chars)
                # print(c['newpos0'], ">",  pre_start, "and", c['nepos1'], "<", pre_start + -1*pre_chars + post_chars)
                if c['newpos0'] is not None and not changed and c['newpos0'] >= pre_start and \
                        c['newpos1'] < pre_start + -1 * pre_chars + post_chars:
                    c['newpos0'] += pre_chars + post_chars
                    c['newpos1'] += pre_chars + post_chars
                    changed = True
                    self.code_deletions.append("delete from case_text where id=" + str(c['id']))
                    c['newpos0'] = None
                if c['newpos0'] is not None and not changed and c['newos0'] < pre_start <= c['newpos1']:
                    c['newpos1'] += pre_chars + post_chars
                    if c['newpos1'] < c['newpos0']:
                        self.code_deletions.append("delete from case_text where id=" + str(c['id']))
                        c['newpos0'] = None
        self.ed_highlight()
        self.prev_text = copy(self.text)'''

    def ed_highlight(self):
        """ Add coding and annotation highlights. """

        if not self.edit_mode:
            return
        self.remove_formatting()
        format_ = QtGui.QTextCharFormat()
        format_.setFontFamily(self.app.settings['font'])
        format_.setFontPointSize(self.app.settings['docfontsize'])
        self.ui.plainTextEdit.blockSignals(True)
        cursor = self.ui.plainTextEdit.textCursor()
        for item in self.ed_casetext:
            if item['newpos0'] is not None:
                cursor.setPosition(int(item['newpos0']), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(int(item['newpos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
                format_.setFontUnderline(True)
                format_.setUnderlineColor(QtCore.Qt.GlobalColor.green)
                cursor.setCharFormat(format_)
        for item in self.ed_annotations:
            if item['newpos0'] is not None:
                cursor.setPosition(int(item['newpos0']), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(int(item['newpos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
                format_.setFontUnderline(True)
                format_.setUnderlineColor(QtCore.Qt.GlobalColor.yellow)
                cursor.setCharFormat(format_)
        for item in self.ed_codetext:
            if item['newpos0'] is not None:
                cursor.setPosition(int(item['newpos0']), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(int(item['newpos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
                format_.setFontUnderline(True)
                format_.setUnderlineColor(QtCore.Qt.GlobalColor.red)
                cursor.setCharFormat(format_)
        self.ui.plainTextEdit.blockSignals(False)

    def remove_formatting(self):
        """ Remove formatting from text edit on changed text.
         Useful when pasting mime data (rich text or html) from clipboard. """

        self.ui.plainTextEdit.blockSignals(True)
        format_ = QtGui.QTextCharFormat()
        format_.setFontFamily(self.app.settings['font'])
        format_.setFontPointSize(self.app.settings['docfontsize'])
        cursor = self.ui.plainTextEdit.textCursor()
        cursor.setPosition(0, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(len(self.ui.plainTextEdit.toPlainText()), QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(format_)
        self.ui.plainTextEdit.blockSignals(False)

    def get_cases_codings_annotations(self):
        """ Get all linked cases, coded text and annotations for this file.
         For editing mode. """

        cur = self.app.conn.cursor()
        sql = "select ctid, cid, pos0, pos1, seltext, owner from code_text where fid=?"
        cur.execute(sql, [self.file_['id']])
        res = cur.fetchall()
        self.ed_codetext = []
        for r in res:
            self.ed_codetext.append({'ctid': r[0], 'cid': r[1], 'pos0': r[2], 'pos1': r[3], 'seltext': r[4],
                                     'owner': r[5], 'newpos0': r[2], 'newpos1': r[3]})
        sql = "select anid, pos0, pos1 from annotation where fid=?"
        cur.execute(sql, [self.file_['id']])
        res = cur.fetchall()
        self.ed_annotations = []
        for r in res:
            self.ed_annotations.append({'anid': r[0], 'pos0': r[1], 'pos1': r[2],
                                        'newpos0': r[1], 'newpos1': r[2]})
        sql = "select id, pos0, pos1 from case_text where fid=?"
        cur.execute(sql, [self.file_['id']])
        res = cur.fetchall()
        self.ed_casetext = []
        for r in res:
            self.ed_casetext.append({'id': r[0], 'pos0': r[1], 'pos1': r[2],
                                     'newpos0': r[1], 'newpos1': r[2]})
        self.no_codes_annotes_cases = False
        if self.ed_casetext == [] and self.ed_annotations == [] and self.ed_codetext == []:
            self.no_codes_annotes_cases = True

    def ed_update_casetext(self):
        """ Update linked case text positions. """

        sql = "update case_text set pos0=?, pos1=? where id=? and (pos0 !=? or pos1 !=?)"
        cur = self.app.conn.cursor()
        for c in self.ed_casetext:
            if c['newpos1'] >= len(self.text):
                c['newpos1'] = len(self.text)
            if c['newpos0'] is not None:
                cur.execute(sql, [c['newpos0'], c['newpos1'], c['id'], c['newpos0'], c['newpos1']])
            else:
                cur.execute("delete from case_text where id=?", [c['id']])
        self.app.conn.commit()

    def ed_update_annotations(self):
        """ Update annotation positions. """

        sql = "update annotation set pos0=?, pos1=? where anid=? and (pos0 !=? or pos1 !=?)"
        cur = self.app.conn.cursor()
        for a in self.ed_annotations:
            if a['newpos0'] is not None:
                cur.execute(sql, [a['newpos0'], a['newpos1'], a['anid'], a['newpos0'], a['newpos1']])
            if a['newpos1'] is None:
                cur.execute("delete from annotation where anid=?", [a['anid']])
        self.app.conn.commit()

    def ed_update_codings(self):
        """ Update coding positions and seltext. """

        cur = self.app.conn.cursor()
        sql = "update code_text set pos0=?, pos1=?, seltext=? where ctid=?"
        for c in self.ed_codetext:
            if c['newpos0'] is not None:
                seltext = self.text[c['newpos0']:c['newpos1']]
                cur.execute(sql, [c['newpos0'], c['newpos1'], seltext, c['ctid']])
            if c['newpos1'] >= len(self.text):
                cur.execute("delete from code_text where ctid=?", [c['ctid']])
        self.app.conn.commit()

    # AI functions

    def tab_changed(self):
        """Will be called when the user changes between the tabs "documents" and
        "AI assistance"
        """
        self.fill_code_counts_in_tree()

    def ai_search_clicked(self):
        """ Start the AI search (if the AI is ready and edit_mode is not active).   
        
        This will open a DialogAISearch to collect the search parameters and then 
        start phase 1 of the search, looking for suitable chunks of data in the vectorstore.
        """
        if self.edit_mode:
            msg = _('Please finish editing the text before starting an AI search.')
            Message(self.app, _('AI Search'), msg, "warning").exec()
            return
        if self.app.ai.get_status() == 'disabled':
            msg = _('The AI is disabled. Go to "AI > Setup Wizard" first.')
            Message(self.app, _('AI Search'), msg, "warning").exec()
            return
        if self.ai_search_running:
            msg = _('The AI is already performing a search. Please stop it before starting a new one.')
            Message(self.app, _('AI Search'), msg, "warning").exec()
            return
        if not self.app.ai.is_ready():
            msg = _('The AI is busy, please wait a moment and retry.')
            Message(self.app, _('AI Search'), msg, "warning").exec()
            return

        # Get currently selected item in code tree
        code_item = self.ui.treeWidget.currentItem()
        if code_item is None:  # nothing selected
            selected_id = -1
            selected_is_code = False
        elif code_item.text(1)[0:3] == 'cat':  # category selected
            selected_id = int(code_item.text(1).split(':')[1])
            selected_is_code = False
        else:  # code selected
            selected_id = int(code_item.text(1).split(':')[1])
            selected_is_code = True

        ui = DialogAiSearch(self.app, 'search', selected_id, selected_is_code, self.tree_sort_option)
        ret = ui.exec()
        if ret == QtWidgets.QDialog.DialogCode.Accepted:
            self.ai_search_code_name = ui.selected_code_name
            self.ai_search_code_memo = ui.selected_code_memo
            self.ai_include_coded_segments = ui.include_coded_segments
            self.ai_search_file_ids = ui.selected_file_ids
            self.ai_search_code_ids = ui.selected_code_ids
            self.ai_search_similar_chunk_list = []
            self.ai_search_chunks_pos = 0
            self.ai_search_results = []
            self.ai_search_prompt = ui.current_prompt
            self.ai_search_ai_model = self.app.ai_models[int(self.app.settings['ai_model_index'])]['name']

            # Prepare the UI
            self.ai_search_running = True
            self.ui.pushButton_ai_search.setText(self.ai_search_code_name)
            self.ui.pushButton_ai_search.setStyleSheet('text-align: left')
            self.ui.listWidget_ai.clear()
            self.ai_search_current_result_index = None
            self.ai_search_spinner_timer.start(500)
            self.ui.plainTextEdit.setPlainText(_('Searching for related data, please wait...'))

            # Phase 1: find similar chunks of data from the vectorstore
            self.ai_search_session_id += 1
            current_session_id = int(self.ai_search_session_id)
            self.ai_search_chunks_pos = 0
            self.app.ai.retrieve_similar_data(
                lambda chunks, session_id=current_session_id: self.ai_search_prepare_analysis(chunks, session_id),
                self.ai_search_code_name,
                self.ai_search_code_memo,
                self.ai_search_file_ids,
                scope_type='ai_search',
                scope_id=self._ai_search_scope_id(),
                group_id=f'ai-search-{self._ai_search_scope_id()}-{current_session_id}',
            )

    def ai_search_prepare_analysis(self, chunks, session_id=None):
        """ Prepare and start the second step of the AI search. 
        
        This will clean up the list of data found in the first stage of the search and then 
        start step 2, the deeper analysis with the choosen search prompt.
        """

        if session_id is not None and int(session_id) != int(self.ai_search_session_id):
            return
        if self._ai_search_scope_status() == 'canceled':
            self.ai_search_running = False
            self.ui.plainTextEdit.setPlainText('')
            return
        if chunks is None or len(chunks) == 0:
            self.ui.plainTextEdit.setPlainText('')
            msg = _('AI: No related data found for "') + self.ai_search_code_name + '".'
            Message(self.app, _('AI Search'), msg, "warning").exec()
            self.ai_search_running = False
            return

        # 1) Check if we search for data related to a code (instead of freetext) and filter out 
        # chunks that are already coded with this code. This way, we find new data only.  
        if (not self.ai_include_coded_segments) and self.ai_search_code_ids is not None and len(
                self.ai_search_code_ids) > 0:
            filtered_chunks = []
            for chunk in chunks:
                chunk_already_coded = False
                chunk_source_id = chunk.metadata['id']
                chunk_start = chunk.metadata['start_index']
                chunk_end = chunk_start + len(chunk.page_content)
                code_ids_str = "(" + ", ".join(map(str, self.ai_search_code_ids)) + ")"
                codings_sql = f'select pos0, pos1 from code_text_visible where fid={chunk_source_id} AND cid in {code_ids_str}'
                cur = self.app.conn.cursor()
                cur.execute(codings_sql)
                codings = cur.fetchall()
                for row in codings:
                    # Calculate the overlap by finding the maximum start position and the minimum end position
                    coding_start = int(row[0])
                    coding_end = int(row[1])
                    overlap_start = max(chunk_start, coding_start)
                    overlap_end = min(chunk_end, coding_end)
                    if overlap_start < overlap_end:
                        # found an overlap. If it is more then 10% of the coding, skip this chunk
                        overlap_len = overlap_end - overlap_start
                        coding_len = coding_end - coding_start
                        if overlap_len > 0.1 * coding_len:
                            chunk_already_coded = True
                            break
                if not chunk_already_coded:
                    filtered_chunks.append(chunk)
            # finally: replace the chunks list with the filtered one
            chunks = filtered_chunks

        if len(chunks) == 0:
            self.ui.plainTextEdit.setPlainText('')
            msg = _('AI: No new data found for "') + self.ai_search_code_name + _(
                '" beside what has already been coded with this code.')
            Message(self.app, _('AI Search'), msg, "warning").exec()
            self.ai_search_running = False
            return

        self.ui.plainTextEdit.setPlainText(
            _('Potentially related data found, inspecting it closer. Please be patient...'))

        # 2) Send the first "ai_search_analysis_max_count" chunks to the llm for further analysis 
        self.ai_search_similar_chunk_list = chunks  # save to allow analyzing more chunks later
        self.ai_search_chunks_pos = 0  # position of the next chunk to be analyzed
        self.ai_search_analysis_counter = 0  # counter to stop analyzing after ai_search_analysis_max_count
        self.ai_search_found = False  # Becomes True if any new data has been found
        self.ai_search_analyze_next_chunk(session_id=session_id)

    def ai_search_analyze_next_chunk(self, session_id=None):
        """Step 2 of the AI search: 
        Selects the next chunk of data found in step 1 of the search and analyzes it closer, 
        using the selected search prompt.
        This will be repeated until: 
        1) 'ai_search_analysis_max_count' is reached (in which case the analysis is paused and
        the user has to click on 'find more' to continue), or 
        2) 'len(self.ai_search_similar_chunk_list)' is reached, meaning that all the 
        chunks found in step 1 have been analyzed and the search is finished."""

        if self.ai_search_chunks_pos < len(self.ai_search_similar_chunk_list):
            # still chunks left for analysis            
            if self.ai_search_analysis_counter < ai_search_analysis_max_count:
                # ai_search_analysis_max_count not reached
                self.ai_search_running = True
                current_session_id = int(self.ai_search_session_id if session_id is None else session_id)
                self.app.ai.search_analyze_chunk(
                    lambda doc, session_id=current_session_id: self.ai_search_analyze_next_chunk_callback(doc, session_id),
                    self.ai_search_similar_chunk_list[self.ai_search_chunks_pos],
                    self.ai_search_code_name,
                    self.ai_search_code_memo,
                    self.ai_search_prompt,
                    scope_type='ai_search',
                    scope_id=self._ai_search_scope_id(),
                    group_id=f'ai-search-{self._ai_search_scope_id()}-{current_session_id}',
                )
            else:  # ai_search_analysis_max_count reached
                self.ai_search_running = False
                if len(self.ai_search_results) == 0:  # nothing found
                    self.ai_search_update_listview_action()
                    self.ui.plainTextEdit.setPlainText('')
                    msg = _('The closer inspection of the first ') + str(self.ai_search_chunks_pos) + \
                          _('pieces of data yielded no results. You can continue to inspect more by clicking on "find '
                            'more" in the list on the left.')
                    Message(self.app, _('AI Search'), msg, "warning").exec()
        else:  # search finished
            self.ai_search_running = False
            if len(self.ai_search_results) == 0:  # nothing found
                self.ui.plainTextEdit.setPlainText('')
                self.ai_search_update_listview_action()
                msg = _(
                    'Upon closer inspection, no pieces of data relevant to your search query could be identified. '
                    'Please start a new search.')
                Message(self.app, _('AI Search'), msg, "warning").exec()

        self.ai_search_update_listview_action()

    def ai_search_analyze_next_chunk_callback(self, doc, session_id=None):
        """Callback for ai_search_analyze_next_chunk: 
        If the AI has finished analyzing the chunk of data, this callback function collects the results, 
        updates the UI and starts the analysis of the next chunk. 
        """

        if session_id is not None and int(session_id) != int(self.ai_search_session_id):
            return
        if not self.ai_search_running:  # Search has been cancelled
            return
        if doc is not None:
            self.ai_search_results.append(doc)
            item_text = f'{doc["metadata"]["name"]}: '
            item_text += '"' + str(doc['quote']).replace('\n', ' ') + '"'
            item = QtWidgets.QListWidgetItem(item_text)
            item_tooltip = '<p>' + _('Quote: ') + f'<i>"{doc["quote"]}"</i></p>'
            item_tooltip += '<p>' + _('AI interpretation: ') + doc["interpretation"] + '</p>'
            item.setToolTip(item_tooltip)
            self.ui.listWidget_ai.insertItem(len(self.ai_search_results) - 1, item)
            if not self.ai_search_found:  # first item found
                self.ai_search_found = True
                item.setSelected(True)
                self.ai_search_selection_changed()

        # analyze next
        self.ai_search_chunks_pos += 1
        self.ai_search_analysis_counter += 1
        if self._ai_search_scope_status() != 'canceled':
            self.ai_search_analyze_next_chunk(session_id=session_id)
        else:
            self.ai_search_running = False

    def ai_search_update_listview_action(self):
        """Adding a special item to the end of the list view that can be clicked for certain actions:
        - Find more: Shown if there are still chunks of empirical data left from stage 1 to be analyzed in stage 2 
        - Stop search: Shown if a search is actually running in the background
        - (search finished): Shown if all results from stage 1 have already been analyzed  
        """
        # add action item to the list if necessary
        if self.ui.listWidget_ai.count() <= len(self.ai_search_results):
            self.ui.listWidget_ai.addItem('')
            self.ai_search_listview_action_label = None
        action_item = self.ui.listWidget_ai.item(self.ui.listWidget_ai.count() - 1)
        if self.ai_search_listview_action_label is None:
            self.ai_search_listview_action_label = QtWidgets.QLabel('')
            self.ai_search_listview_action_label.setStyleSheet(
                f'QLabel {{color: {self.app.highlight_color()}; text-decoration: underline; margin-left: 2px; }}')
            self.ui.listWidget_ai.setItemWidget(action_item, self.ai_search_listview_action_label)

        if self.ai_search_running:
            # Stop search
            action_item.setText('')
            self.ai_search_listview_action_label.setText(_('>> Searching (click here to cancel)') +
                                                         self.ai_search_spinner_sequence[self.ai_search_spinner_index])
            self.ai_search_listview_action_label.setToolTip(_('Click here to stop the search'))
            self.ai_search_listview_action_label.setVisible(True)
        elif self.ai_search_chunks_pos < len(self.ai_search_similar_chunk_list):
            # Find more
            action_item.setText('')
            self.ai_search_listview_action_label.setText(_('>> Find more...'))
            self.ai_search_listview_action_label.setToolTip(_('Click here to analyze more data'))
            self.ai_search_listview_action_label.setVisible(True)
        else:
            # Search finished
            self.ai_search_listview_action_label.setText('')
            self.ai_search_listview_action_label.setToolTip('')
            self.ai_search_listview_action_label.setVisible(False)
            if self._ai_search_scope_status() == 'errored':
                action_item.setText(_('(search aborted due to an error)'))
            elif self._ai_search_scope_status() == 'canceled':
                action_item.setText('(search canceled)')
            else:
                action_item.setText(_('(search finished)'))

    def ai_search_list_clicked(self):
        """ Checks if the special action item at the end of the list was clicked 
        and performs the corresponding action ('find more', 'stop search', etc.).
        If a normal item in the list was clicked, 'self.ai_search_selection_changed()' is
        called."""

        row = self.ui.listWidget_ai.currentRow()
        if row < len(self.ai_search_results):  # clicked on a search result
            self.ai_search_selection_changed()
        else:  # clicked on "stop search" or "find more"
            selection_model = self.ui.listWidget_ai.selectionModel()
            selection_model.blockSignals(True)  # stop selection_change from beeing issued
            if self.ai_search_running:  # stop search
                msg = _('Do you want to stop the search?')
                msg_box = Message(self.app, _("Open file"), msg, "information")
                msg_box.setStandardButtons(
                    QtWidgets.QMessageBox.StandardButton.Ok | QtWidgets.QMessageBox.StandardButton.Abort)
                msg_box.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Ok)
                ret = msg_box.exec()
                if ret == QtWidgets.QMessageBox.StandardButton.Ok:
                    self._cancel_ai_search_scope(wait_ms=5000)
                    self.ai_search_running = False
                    self.ai_search_update_listview_action()
            else:  # 'find more' item or "finished search"
                if self.ai_search_chunks_pos >= len(self.ai_search_similar_chunk_list):
                    msg = _('There are no more pieces of data to analyze for this search. Please start a new search.')
                    Message(self.app, _('AI Search'), msg, "warning").exec()
                elif self.ai_search_running or (not self.app.ai.is_ready()):
                    msg = _('The AI is busy. Please wait a moment and retry.')
                    Message(self.app, _('AI Search'), msg, "warning").exec()
                else:
                    self.ai_search_analysis_counter = 0  # counter to stop analyzing after ai_search_analysis_max_count
                    self.ai_search_running = True
                    self.ai_search_spinner_timer.start()
                    self.ai_search_analyze_next_chunk()
            # reselect the item that was active before:
            if self.ai_search_current_result_index is not None:
                self.ui.listWidget_ai.setCurrentRow(self.ai_search_current_result_index)
            else:
                self.ui.listWidget_ai.clearSelection()
            selection_model.blockSignals(False)

    def ai_search_selection_changed(self):
        """Load the document corresponding to the selected AI search result in the textView 
        and select the quote that the AI chose."""

        if self.ai_search_results is None or len(self.ai_search_results) == 0:
            return

        if len(self.ui.listWidget_ai.selectedIndexes()) > 0:
            row = self.ui.listWidget_ai.selectedIndexes()[0].row()
        else:
            self.ai_search_current_result_index = None
            return

        if row == len(self.ai_search_results):
            # out of bounds, must be the action item
            return

        self.ai_search_current_result_index = row
        doc = self.ai_search_results[self.ai_search_current_result_index]
        id_ = doc['metadata']['id']
        quote_start = doc['quote_start']
        quote_end = quote_start + len(doc['quote'])
        self.open_doc_selection(id_, quote_start, quote_end)

    def open_doc_selection(self, doc_id, sel_start, sel_end):
        """ Open document and select a certain part. """

        for i, f in enumerate(self.files):
            if f['id'] == doc_id:
                f['start'] = 0
                if f['end'] != f['characters']:  # partially loaded
                    msg = _("Entire text file will be loaded")
                    Message(self.app, _('Information'), msg).exec()
                f['end'] = f['characters']
                try:
                    self.ui.listWidget.setCurrentRow(i)
                    self.load_file(f)
                    # Set text cursor position
                    doc_len = len(self.ui.plainTextEdit.toPlainText())
                    start = max(0, int(sel_start))
                    endpos = int(sel_end)
                    if endpos <= start:
                        endpos = start + 1
                    if doc_len > 0:
                        if start >= doc_len:
                            start = doc_len - 1
                        endpos = min(max(start + 1, endpos), doc_len)
                    else:
                        start = 0
                        endpos = 0
                    text_cursor = self.ui.plainTextEdit.textCursor()
                    text_cursor.setPosition(start)
                    text_cursor.setPosition(endpos, QtGui.QTextCursor.MoveMode.KeepAnchor)
                    self.ui.plainTextEdit.setTextCursor(text_cursor)
                    self.ui.plainTextEdit.setFocus()
                    QtCore.QTimer.singleShot(0, self.scroll_text_into_view)  # scroll into view after window is updated
                except Exception as e:
                    logger.debug(str(e))
                break

    def scroll_text_into_view(self):
        """Scroll so the current selection is centered in the viewport."""

        editor = self.ui.plainTextEdit
        original_cursor = editor.textCursor()
        if not original_cursor.hasSelection():
            editor.centerCursor()
            return

        # Center on the middle of the selected span to avoid edge-biased scrolling.
        sel_start = original_cursor.selectionStart()
        sel_end = original_cursor.selectionEnd()
        mid_pos = sel_start + ((sel_end - sel_start) // 2)

        target_cursor = QtGui.QTextCursor(editor.document())
        target_cursor.setPosition(mid_pos)

        # QPlainTextEdit centers based on the active cursor position.
        editor.setTextCursor(target_cursor)
        editor.centerCursor()
        # Restore original selection highlight.
        editor.setTextCursor(original_cursor)
        
    def ai_search_update_spinner(self):
        """ Updating the ai_progressBar and the text spinner in the list view to indicate to the user that 
        an AI search is running in the background. """
        if self._ai_search_scope_status() in ('finished', 'errored', 'canceled', 'idle'):
            self.ai_search_running = False
        if self.ai_search_running:
            self.ui.ai_progressBar.setVisible(True)
            self.ai_search_spinner_index = (self.ai_search_spinner_index + 1) % len(self.ai_search_spinner_sequence)
            self.ai_search_update_listview_action()
        else:
            self.ui.ai_progressBar.setVisible(False)
            self.ai_search_spinner_timer.stop()
            self.ai_search_update_listview_action()

    def get_overlapping_ai_search_result(self):
        """
        Retrieves the single document from self.ai_search_results that has the longest overlap 
        with the text selection defined in the text editor within the UI.
        This is used in 'self.mark()' to determine if the AI has analyzed a certain text passage and
        we can suggest adding the interpretation to the coding memo.

        Returns:
            best_doc (dict or None): The document with the longest overlap if overlapping documents 
                exist; otherwise, None.
        """

        if self.ui.tabWidget.currentIndex() != 1:  # not in ai search mode
            return None

        # Get the adjusted start and end positions from the text editor's current selection
        pos0 = self.ui.plainTextEdit.textCursor().selectionStart() + self.file_['start']
        pos1 = self.ui.plainTextEdit.textCursor().selectionEnd() + self.file_['start']
        if pos0 == pos1:
            return None

        best_doc = None
        max_overlap_length = 0

        for doc in self.ai_search_results:
            quote_start = doc['quote_start']
            quote_end = quote_start + len(doc['quote'])

            # Check for any intersection between the quote interval and the selection interval
            if quote_start <= pos1 and quote_end >= pos0:
                # Calculate the overlap length
                overlap_start = max(quote_start, pos0)
                overlap_end = min(quote_end, pos1)
                overlap_length = overlap_end - overlap_start

                # Update the best_doc if this document has a longer overlap
                if overlap_length > max_overlap_length:
                    max_overlap_length = overlap_length
                    best_doc = doc

        return best_doc

    def display_handles_for_code(self, position):
        """ Display interactive drag handles to resize a code's boundaries. """

        if self.file_ is None:
            return
        coded_text_list = []
        for item in self.code_text:
            if item['pos0'] <= position + self.file_['start'] <= item['pos1']:
                coded_text_list.append(item)
        if not coded_text_list:
            return
        code_to_handle = coded_text_list[-1]
        if len(coded_text_list) > 1:
            ui = DialogSelectItems(self.app, coded_text_list, _("Select code to resize"), "single")
            if ui.exec():
                code_to_handle = ui.get_selected()
            else:
                return
        self.hide_resize_handles()

        # Create start handle
        cursor_start = self.ui.plainTextEdit.textCursor()
        cursor_start.setPosition(max(0, code_to_handle['pos0'] - self.file_['start']))
        rect_start = self.ui.plainTextEdit.cursorRect(cursor_start)
        h_start = CodeResizeHandle(self.ui.plainTextEdit, True, code_to_handle, self)
        h_start.move(rect_start.x() - 6, rect_start.y() + 2)
        self.active_handles.append(h_start)

        # Create end handle
        cursor_end = self.ui.plainTextEdit.textCursor()
        cursor_end.setPosition(min(len(self.ui.plainTextEdit.toPlainText()), code_to_handle['pos1'] - self.file_['start']))
        rect_end = self.ui.plainTextEdit.cursorRect(cursor_end)
        h_end = CodeResizeHandle(self.ui.plainTextEdit, False, code_to_handle, self)
        h_end.move(rect_end.x() - 6, rect_end.y() + 2)
        self.active_handles.append(h_end)

    def hide_resize_handles(self):
        """ Remove all active resize handles from the screen. """
        for h in getattr(self, 'active_handles', []):
            h.hide()
            h.deleteLater()
        self.active_handles = []

    def update_code_position_from_handle(self, code_item, new_pos, is_start, orig_pos0, orig_pos1):
        """ Receive final drop coordinates from a handle and update the database. """
        if is_start:
            if new_pos >= code_item['pos1']:
                code_item['pos0'] = orig_pos0  # Revert visually
                self.hide_resize_handles()
                self.unlight()
                self.highlight()
                return
            code_item['pos0'] = new_pos
        else:
            if new_pos <= code_item['pos0']:
                code_item['pos1'] = orig_pos1  # Revert visually
                self.hide_resize_handles()
                self.unlight()
                self.highlight()
                return
            code_item['pos1'] = new_pos

        cur = self.app.conn.cursor()
        cur.execute("select substr(fulltext,?,?) from source where id=?",
                    [code_item['pos0'] + 1, code_item['pos1'] - code_item['pos0'], code_item['fid']])
        res = cur.fetchone()
        
        if not res:
            # Revert on extraction error
            code_item['pos0'] = orig_pos0
            code_item['pos1'] = orig_pos1
            self.hide_resize_handles()
            self.unlight()
            self.highlight()
            return
        seltext = res[0]

        try:
            sql = "update code_text set pos0=?, pos1=?, seltext=? where ctid=?"
            cur.execute(sql, [code_item['pos0'], code_item['pos1'], seltext, code_item['ctid']])
            self.app.conn.commit()
            self.app.delete_backup = False
        except sqlite3.IntegrityError:
            self.app.conn.rollback()
            # Revert in-memory positions to undo temporary highlight
            code_item['pos0'] = orig_pos0
            code_item['pos1'] = orig_pos1
            Message(self.app, _("Duplicate Error"),
                    _("This code already exists at this exact location."), "warning").exec()
        self.hide_resize_handles()
        self.get_coded_text_update_eventfilter_tooltips()


class DialogFontAndSize(QtWidgets.QDialog):
    """ Get font and size. For plaintextedit text. """

    def __init__(self, app, size, font, parent=None):
        super().__init__(parent)
        style = f'font: {app.settings["fontsize"]}pt "{app.settings["font"]}";'
        self.setStyleSheet(style)
        self.setWindowTitle(_("Font and size"))
        self.resize(300, 100)
        self.setMaximumWidth(300)
        layout = QtWidgets.QVBoxLayout()
        self.font_combo = QtWidgets.QFontComboBox()
        index = self.font_combo.findText(font, QtCore.Qt.MatchFlag.MatchFixedString)
        if index == -1:
            index = 0
        self.font_combo.setCurrentIndex(index)
        layout.addWidget(self.font_combo)
        self.font_size_combo = QtWidgets.QComboBox()
        self.font_size_combo.addItems(["8", "10", "12", "14", "16", "18", "20", "22"])
        index = self.font_size_combo.findText(size, QtCore.Qt.MatchFlag.MatchFixedString)
        if index == -1:
            index = 0
        self.font_size_combo.setCurrentIndex(index)
        layout.addWidget(self.font_size_combo)

        bbox = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)
        self.setLayout(layout)

    def get_size_and_font(self):
        return self.font_size_combo.currentText(), self.font_combo.currentText()


# see https://www.freeformatter.com/html-entities.html
entities = {"&": "&amp;", '"': '&quot;', "'": "&#39;", "<": "&lt;", ">": "&gt;", "–": "&ndash;", "—": "&mdash;",
            "€": "&euro;", "‘": "&lsquo;", "’": "&rsquo;", "“": "&ldquo;", "”": "&rdquo;", "…": "&hellip;",
            "™": "&trade;", "£": "&pound;"}
