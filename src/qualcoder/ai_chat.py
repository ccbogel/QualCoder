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

Author: Kai Droege (kaixxx)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
https://qualcoder-org.github.io/
"""

from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import Qt, QEvent, QObject, pyqtSignal
from PyQt6.QtGui import QCursor, QGuiApplication, QAction, QPalette, QShortcut, QKeySequence, QStandardItemModel, QStandardItem
from PyQt6.QtWidgets import QTextEdit
import qtawesome as qta

from langchain_core.messages.human import HumanMessage
from langchain_core.messages.ai import AIMessage
from langchain_core.messages.system import SystemMessage
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.documents.base import Document
from markdown_it import MarkdownIt

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import json
import html as html_lib
import logging
import traceback
import os
import sqlite3
import webbrowser
import re
import threading
import time
import unicodedata
from urllib.parse import urlencode, quote, unquote

from .ai_search_dialog import DialogAiSearch
from .GUI.ui_ai_chat import Ui_Dialog_ai_chat
from .helpers import Message
from .confirm_delete import DialogConfirmDelete
from .ai_agent_prompts import AiAgentPromptsCatalog, AgentPromptRecord, prompt_name_and_scope
from .ai_llm import extract_ai_memo, ai_quote_search, strip_think_blocks, AICancelled
from .ai_mcp_server import AiMcpServer
from .error_dlg import qt_exception_hook
from .html_parser import html_to_text

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

topic_analysis_max_chunks = 30
code_analysis_max_segments_total = 200
code_analysis_min_segment_coverage = 0.30

MARKDOWN_RENDERER = MarkdownIt(
    "commonmark",
    options_update={
        "breaks": True,
        "html": False,
        "typographer": True,
    },
).enable(["table", "strikethrough"])
MARKDOWN_INTERNAL_LINK_PATTERN = re.compile(
    r"<a\s+href=(['\"])(?:coding|chunk|quote|action):.*?</a>",
    re.IGNORECASE | re.DOTALL,
)
MARKDOWN_HR_IMAGE_CACHE: Dict[str, str] = {}
PROMPT_SLASH_REF_PATTERN = re.compile(r"(?<!\S)/(?!/)[^\s`<>\[\]{}\"']+")


def markdown_hr_image_data_uri(color: str) -> str:
    """Return a 1x1 PNG data URI in the requested color for Qt rich text."""

    qcolor = QtGui.QColor(str(color if color is not None else "").strip())
    if not qcolor.isValid():
        qcolor = QtGui.QColor("#e6e6e6")
    cache_key = qcolor.name()
    cached = MARKDOWN_HR_IMAGE_CACHE.get(cache_key, "")
    if cached != "":
        return cached

    image = QtGui.QImage(1, 1, QtGui.QImage.Format.Format_ARGB32)
    image.fill(qcolor)
    byte_array = QtCore.QByteArray()
    buffer = QtCore.QBuffer(byte_array)
    buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    data_uri = "data:image/png;base64," + bytes(byte_array.toBase64()).decode("ascii")
    MARKDOWN_HR_IMAGE_CACHE[cache_key] = data_uri
    return data_uri


def render_markdown_to_html(text: str, hr_color: str = "#e6e6e6", hr_width_px: int = 600) -> str:
    """Render AI Markdown for QLabel output while preserving internal QualCoder links."""

    source_text = str(text if text is not None else "")
    preserved_links: List[str] = []
    try:
        hr_width_px = max(1, int(hr_width_px))
    except (TypeError, ValueError):
        hr_width_px = 600

    def preserve_quote_link(match: re.Match) -> str:
        token = f"@@QUALCODER_QUOTE_LINK_{len(preserved_links)}@@"
        preserved_links.append(match.group(0))
        return token

    markdown_text = MARKDOWN_INTERNAL_LINK_PATTERN.sub(preserve_quote_link, source_text)
    rendered_html = MARKDOWN_RENDERER.render(markdown_text).strip()
    if rendered_html == "":
        rendered_html = "<p></p>"

    for idx, link_html in enumerate(preserved_links):
        rendered_html = rendered_html.replace(f"@@QUALCODER_QUOTE_LINK_{idx}@@", link_html)

    rendered_html = re.sub(
        r"<code([^>]*)>",
        r"""<code\1 style="font-family: Consolas, 'Courier New', monospace;">""",
        rendered_html,
    )
    rendered_html = re.sub(
        r"<hr\s*/?>",
        (
            '<div style="margin: 8px 0;">'
            f'<img src="{markdown_hr_image_data_uri(hr_color)}" width="{hr_width_px}" height="1" />'
            '</div>'
        ),
        rendered_html,
        flags=re.IGNORECASE,
    )
    for old, new in (
            ("<p>", '<p style="margin: 0 0 8px 0;">'),
            ("<h1>", '<h1 style="margin: 10px 0 8px 0; font-weight: normal; font-size: 1.6em;">'),
            ("<h2>", '<h2 style="margin: 8px 0 8px 0; font-weight: normal; font-size: 1.45em;">'),
            ("<h3>", '<h3 style="margin: 8px 0 8px 0; font-weight: normal; font-size: 1.3em;">'),
            ("<h4>", '<h4 style="margin: 8px 0 8px 0; font-weight: normal; font-size: 1.15em;">'),
            ("<h5>", '<h5 style="margin: 8px 0 8px 0; font-weight: normal; font-size: 1.05em;">'),
            ("<h6>", '<h6 style="margin: 8px 0 8px 0; font-weight: normal; font-size: 1em;">'),
            ("<ul>", '<ul style="margin: 0 0 8px 0;">'),
            ("<ol>", '<ol style="margin: 0 0 8px 0;">'),
            ("<blockquote>", '<blockquote style="margin: 0 0 8px 12px; padding-left: 8px; border-left: 3px solid #999999;">'),
            ("<pre>", '<pre style="margin: 0 0 8px 0; padding: 8px; border: 1px solid #999999; white-space: pre-wrap;">'),
            ("<table>", '<table cellspacing="0" cellpadding="6" style="margin: 0 0 8px 0; border-collapse: collapse;">'),
            ("<th>", '<th style="border: 1px solid #999999; text-align: left;">'),
            ("<td>", '<td style="border: 1px solid #999999;">'),
    ):
        rendered_html = rendered_html.replace(old, new)

    return f'<div style="margin-top: 4px;">{rendered_html}</div>'

class AIChatSignalEmitter(QObject):
    newTextChatSignal = pyqtSignal(int, str, str, int, object)  # will start a new text analysis chat

ai_chat_signal_emitter = AIChatSignalEmitter()  # Create a global instance of the signal emitter


class PrefixedComboBox(QtWidgets.QComboBox):
    """Draw a prefix in the closed combobox without changing the popup item texts."""

    def __init__(self, prefix: str = "", parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._display_prefix = prefix

    def set_display_prefix(self, prefix: str):
        self._display_prefix = prefix
        self.update()

    def paintEvent(self, event):
        painter = QtWidgets.QStylePainter(self)
        option = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(option)
        if self._display_prefix:
            option.currentText = self._display_prefix if not option.currentText else f"{self._display_prefix} {option.currentText}"
        painter.drawComplexControl(QtWidgets.QStyle.ComplexControl.CC_ComboBox, option)
        painter.drawControl(QtWidgets.QStyle.ControlElement.CE_ComboBoxLabel, option)


class PromptCompletionListWidget(QtWidgets.QListWidget):
    """Popup list for inline `/prompt` completion in the AI chat input."""

    popupHidden = pyqtSignal()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.popupHidden.emit()


class PromptSlashReferenceHighlighter(QtGui.QSyntaxHighlighter):
    """Highlight `/prompt` references in the AI chat input."""

    def __init__(self, document, records_provider, enabled_provider, style_provider):
        super().__init__(document)
        self.records_provider = records_provider
        self.enabled_provider = enabled_provider
        self.style_provider = style_provider

    def highlightBlock(self, text: str) -> None:
        try:
            if not self.enabled_provider():
                return
            prompt_names = {
                str(prompt.name if prompt.name is not None else '').strip('/').casefold()
                for prompt in self.records_provider()
            }
            prompt_names.discard('')
            styles = self.style_provider()
        except Exception:
            return

        for match in PROMPT_SLASH_REF_PATTERN.finditer(text):
            token = match.group(0).strip()
            prompt_name = token[1:].rstrip('/.,;:!?').casefold()
            if prompt_name not in prompt_names:
                continue
            fmt = QtGui.QTextCharFormat()
            valid_style = styles.get("valid", {})
            fmt.setBackground(QtGui.QBrush(valid_style.get("background", QtGui.QColor())))
            self.setFormat(match.start(), match.end() - match.start(), fmt)


class DialogAIChat(QtWidgets.QDialog):
    """ AI chat window
    """    
    app = None
    parent_textEdit = None
    chat_history_conn = None
    current_chat_idx = -1
    current_streaming_chat_idx = -1
    chat_msg_list = [] 
    is_updating_chat_window = False
    ai_semantic_search_chunks = []
    last_export_dir = ''
    # filenames = []

    def _analysis_prompt_display_name_and_scope(self, prompt: AgentPromptRecord, analysis_type: str) -> str:
        """Return the prompt label shown in analysis chat summaries."""

        prompt_label = prompt_name_and_scope(prompt)
        prefixes = {
            "code_analysis": "code-analysis/",
            "topic_exploration": "topic-exploration/",
            "text_analysis": "text-analysis/",
        }
        prefix = prefixes.get(analysis_type, "")
        if prefix != "" and prompt_label.startswith(prefix):
            return prompt_label[len(prefix):]
        return prompt_label

    def __init__(self, app, parent_text_edit: QTextEdit, main_window: QtWidgets.QMainWindow):

        self.app = app
        self.parent_textEdit = parent_text_edit
        self.main_window = main_window
        # Set up the user interface from Designer.
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_ai_chat()
        self.ui.setupUi(self)
        self.setup_ai_permissions_combobox()
        self.ui.comboBox_ai_permissions.currentIndexChanged.connect(self.ai_permissions_changed)
        self.load_ai_permissions()
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        # self.ui.scrollArea_ai_output.verticalScrollBar().rangeChanged.connect(self.ai_output_scroll_to_bottom)
        self.ui.plainTextEdit_question.installEventFilter(self)
        self.ui.plainTextEdit_question.viewport().installEventFilter(self)
        self.ui.pushButton_question.pressed.connect(self.button_question_clicked)
        self.ui.progressBar_ai.setMaximum(100)
        self.ui.plainTextEdit_question.setPlaceholderText(_('<your question>'))
        self.ui.pushButton_new_analysis.clicked.connect(self.button_new_clicked)
        self.ui.pushButton_delete.clicked.connect(self.delete_chat)
        self.chat_list_model = QStandardItemModel(self)
        self.ui.treeView_chat_list.setModel(self.chat_list_model)
        self.ui.treeView_chat_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.ui.treeView_chat_list.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.shortcut_delete_chat = QShortcut(QKeySequence("Delete"), self.ui.treeView_chat_list)
        self.shortcut_delete_chat.setContext(QtCore.Qt.ShortcutContext.WidgetShortcut)
        self.shortcut_delete_chat.activated.connect(self.delete_chat)
        # Enable editing of items on double click and when pressing F2
        self.ui.treeView_chat_list.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.DoubleClicked |
            QtWidgets.QAbstractItemView.EditTrigger.EditKeyPressed
        )
        self.ui.treeView_chat_list.selectionModel().selectionChanged.connect(self.chat_list_selection_changed)
        self.chat_list_model.itemChanged.connect(self.chat_list_item_changed)
        self.ui.treeView_chat_list.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.treeView_chat_list.customContextMenuRequested.connect(self.open_context_menu)
        self.ui.comboBox_ai_chats.setModel(self.chat_list_model)
        self.ui.comboBox_ai_chats.setModelColumn(0)
        self.ui.comboBox_ai_chats.setMinimumContentsLength(1)
        self.ui.comboBox_ai_chats.setSizeAdjustPolicy(
            QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        combo_size_policy = self.ui.comboBox_ai_chats.sizePolicy()
        combo_size_policy.setHorizontalPolicy(QtWidgets.QSizePolicy.Policy.Ignored)
        self.ui.comboBox_ai_chats.setSizePolicy(combo_size_policy)
        self.ui.comboBox_ai_chats.setMinimumWidth(0)
        combo_view = QtWidgets.QTreeView(self.ui.comboBox_ai_chats)
        combo_view.setRootIsDecorated(False)
        combo_view.header().setVisible(False)
        self.ui.comboBox_ai_chats.setView(combo_view)
        self.ui.comboBox_ai_chats.currentIndexChanged.connect(self.combo_chat_selection_changed)
        self.ui.toolButton_close_sidebar.pressed.connect(self.close_sidebar_view)
        self.ui.toolButton_edit_title.pressed.connect(self.edit_title)
        self.ai_output_splitter_is_restoring = True
        self.ui.splitter_ai_output.splitterMoved.connect(self.on_ai_output_splitter_moved)
        self.ui.ai_output.linkHovered.connect(self.on_linkHovered)
        self.ui.ai_output.linkActivated.connect(self.on_linkActivated)
        self.ui.pushButton_help.pressed.connect(self.help)
        self.ui.pushButton_undo.pressed.connect(self._undo_ai_changes_shortcut)
        self.shortcut_undo_ai_changes = QShortcut(QKeySequence("Ctrl+Shift+U"), self)
        self.shortcut_undo_ai_changes.activated.connect(self._undo_ai_changes_shortcut)
        ai_chat_signal_emitter.newTextChatSignal.connect(self.new_text_chat)
        self.agent_prompts_catalog = AiAgentPromptsCatalog(self.app)
        self.ai_mcp_server = AiMcpServer(self.app)
        self.ai_prompt = None
        self._setup_prompt_completion()
        self.init_styles()
        self.ai_busy_timer = QtCore.QTimer(self)
        self.ai_busy_timer.timeout.connect(self.update_ai_busy)
        self.ai_busy_timer.start(100)
        self.ai_streaming_output = ''
        self.ai_stream_buffer = ""
        self.ai_stream_in_ref = False
        self.ai_stream_render_pending = False
        self.ai_stream_render_timer = QtCore.QTimer(self)
        self.ai_stream_render_timer.setSingleShot(True)
        self.ai_stream_render_timer.timeout.connect(self._flush_stream_render)
        self.curr_codings = None
        self.ai_search_code_name = None
        self.ai_search_code_memo = None
        self.chat_list = []
        self._is_updating_chat_title_item = False
        self.ai_search_file_ids = []
        self.ai_search_code_ids = []
        self.ai_text_doc_id = None
        self.ai_text_doc_name = ''
        self.ai_text_text = ''
        self.ai_text_start_pos = -1
        self._chat_ai_profile_snapshots: Dict[int, str] = {}
        self.ai_output_autoscroll = True
        self.setMinimumWidth(0)
        self.ui.widget_chat.setMinimumWidth(0)
        self.ui.scrollArea_ai_output.setMinimumWidth(0)
        self.ui.ai_output.setMinimumWidth(0)
        ai_output_size_policy = self.ui.ai_output.sizePolicy()
        ai_output_size_policy.setHorizontalPolicy(QtWidgets.QSizePolicy.Policy.Ignored)
        self.ui.ai_output.setSizePolicy(ai_output_size_policy)
        self.ui.splitter_ai_output.setStretchFactor(0, 1)
        self.ui.splitter_ai_output.setStretchFactor(1, 0)
        self.ai_output_splitter_save_timer = QtCore.QTimer(self)
        self.ai_output_splitter_save_timer.setSingleShot(True)
        self.ai_output_splitter_save_timer.timeout.connect(self.persist_ai_output_splitter_setting)
        self.ai_output_splitter_restore_attempts = 0
        self.schedule_ai_output_splitter_restore()
        self.ui.scrollArea_ai_output.verticalScrollBar().valueChanged.connect(self.on_ai_output_scroll)
        self.set_sidebar_mode(False)
        QtCore.QTimer.singleShot(0, self._hide_transient_chat_overlays)
        self._update_undo_button_state()

    def _setup_prompt_completion(self) -> None:
        """Create the prompt completion popup and initialize transient state."""

        self._prompt_completion_popup = PromptCompletionListWidget(self)
        self._prompt_completion_popup.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.SubWindow
        )
        self._prompt_completion_popup.setAttribute(
            Qt.WidgetAttribute.WA_ShowWithoutActivating,
            True,
        )
        self._prompt_completion_popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._prompt_completion_popup.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self._prompt_completion_popup.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self._prompt_completion_popup.setMouseTracking(True)
        self._prompt_completion_popup.viewport().setMouseTracking(True)
        self._prompt_completion_popup.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._prompt_completion_records: List[AgentPromptRecord] = []
        self._prompt_inline_completion: Optional[Dict[str, Any]] = None
        self._prompt_completion_guard = False
        self._prompt_completion_accepting = False
        self._prompt_completion_temporarily_disabled = False
        self._prompt_reference_styles: Dict[str, Dict[str, Any]] = {}
        self._prompt_reference_highlighter = PromptSlashReferenceHighlighter(
            self.ui.plainTextEdit_question.document(),
            lambda: self._prompt_completion_records,
            self._prompt_completion_enabled,
            lambda: self._prompt_reference_styles,
        )
        self._prompt_completion_popup.currentItemChanged.connect(
            self._prompt_completion_current_item_changed
        )
        self._prompt_completion_popup.itemClicked.connect(
            self._prompt_completion_item_clicked
        )
        self._prompt_completion_popup.itemEntered.connect(
            self._prompt_completion_item_entered
        )
        self._prompt_completion_popup.popupHidden.connect(
            self._prompt_completion_popup_hidden
        )
        self._prompt_completion_popup.hide()
        self.ui.plainTextEdit_question.textChanged.connect(self._sync_prompt_completion)
        self.ui.plainTextEdit_question.cursorPositionChanged.connect(self._sync_prompt_completion)
        self._refresh_prompt_completion_records()

    def _suspend_prompt_completion_temporarily(self) -> None:
        """Pause completion refreshes briefly so editor navigation can finish."""

        if self._prompt_completion_temporarily_disabled:
            return
        self._prompt_completion_temporarily_disabled = True
        QtCore.QTimer.singleShot(0, self._resume_prompt_completion)

    def _resume_prompt_completion(self) -> None:
        """Re-enable completion refreshes after a temporary navigation pause."""

        self._prompt_completion_temporarily_disabled = False

    def _refresh_prompt_completion_records(self) -> None:
        """Reload user-callable prompt names for the completion popup."""

        self._prompt_completion_records = self.agent_prompts_catalog.list_prompts(include_internal=False)
        if hasattr(self, "_prompt_reference_highlighter"):
            self._prompt_reference_highlighter.rehighlight()

    def _prompt_completion_enabled(self) -> bool:
        """Return whether `/prompt` completion should be active in the current chat."""

        if self.current_chat_idx < 0 or self.current_chat_idx >= len(self.chat_list):
            return False
        analysis_type = str(self.chat_list[self.current_chat_idx][2] if self.chat_list[self.current_chat_idx][2] is not None else '')
        return self._is_agent_chat_type(analysis_type)

    def _current_prompt_completion_context(self) -> Optional[Dict[str, Any]]:
        """Describe the active `/prompt` token at the caret, if any."""

        if not self._prompt_completion_enabled():
            return None
        editor = self.ui.plainTextEdit_question
        cursor = editor.textCursor()
        caret_pos = cursor.position()
        text = editor.toPlainText()
        if caret_pos < 0 or caret_pos > len(text):
            return None

        token_start = caret_pos
        while token_start > 0 and not text[token_start - 1].isspace():
            token_start -= 1

        token_end = caret_pos
        while token_end < len(text) and not text[token_end].isspace():
            token_end += 1

        if caret_pos != token_end:
            return None

        typed_token = text[token_start:caret_pos]
        full_token = text[token_start:token_end]
        if not typed_token.startswith('/') or not full_token.startswith('/'):
            return None
        if token_start > 0 and not text[token_start - 1].isspace():
            return None

        return {
            "start": token_start,
            "end": token_end,
            "typed": typed_token,
        }

    def _split_prompt_completion_query(self, typed: str) -> Tuple[str, str]:
        """Split one `/prompt/path` token into parent path and typed leaf prefix."""

        query = str(typed if typed is not None else '')
        if query.startswith('/'):
            query = query[1:]
        query = query.replace('\\', '/')
        if query.endswith('/'):
            return query.rstrip('/'), ''
        if '/' not in query:
            return '', query
        parent, leaf = query.rsplit('/', 1)
        return parent, leaf

    def _iter_prompt_completion_categories(self) -> List[str]:
        """Return all category paths derived from the currently resolved prompts."""

        categories: set[str] = set()
        for prompt in self._prompt_completion_records:
            parts = [part for part in prompt.name.split('/') if part != '']
            for idx in range(1, len(parts)):
                categories.add('/'.join(parts[:idx]))
        return sorted(categories, key=lambda item: item.casefold())

    def _is_direct_prompt_completion_child(self, full_name: str, parent: str) -> Optional[str]:
        """Return the direct child name relative to `parent`, if any."""

        normalized_full = str(full_name if full_name is not None else '').strip('/')
        normalized_parent = str(parent if parent is not None else '').strip('/')
        if normalized_full == '':
            return None
        if normalized_parent == '':
            if '/' in normalized_full:
                return None
            return normalized_full
        prefix = normalized_parent + '/'
        if not normalized_full.startswith(prefix):
            return None
        remainder = normalized_full[len(prefix):]
        if remainder == '' or '/' in remainder:
            return None
        return remainder

    def _matching_prompt_completion_items(self, prefix: str) -> List[Dict[str, Any]]:
        """Return direct matching categories and prompts for the current token."""

        self._refresh_prompt_completion_records()
        parent, leaf = self._split_prompt_completion_query(prefix)
        normalized_leaf = leaf.casefold()
        items: List[Dict[str, Any]] = []

        for category in self._iter_prompt_completion_categories():
            child_name = self._is_direct_prompt_completion_child(category, parent)
            if child_name is None or not child_name.casefold().startswith(normalized_leaf):
                continue
            full_insert = '/' + category + '/'
            items.append(
                {
                    "kind": "category",
                    "display_text": child_name + '/',
                    "insert_text": full_insert,
                    "category_path": category,
                    "sort_text": child_name.casefold(),
                    "tooltip": _('Prompt category: ') + full_insert,
                }
            )

        for prompt in self._prompt_completion_records:
            child_name = self._is_direct_prompt_completion_child(prompt.name, parent)
            if child_name is None or not child_name.casefold().startswith(normalized_leaf):
                continue
            tooltip_lines = []
            if prompt.description != '':
                tooltip_lines.append(_('Prompt description: ') + prompt.description)
            tooltip_lines.append(f'/{prompt.name}')
            tooltip_lines.append(f'[{prompt.scope}]')
            items.append(
                {
                    "kind": "prompt",
                    "display_text": child_name,
                    "insert_text": '/' + prompt.name,
                    "prompt_path": prompt.name,
                    "sort_text": child_name.casefold(),
                    "tooltip": '\n'.join(tooltip_lines),
                    "record": prompt,
                }
            )

        if parent == '':
            items.sort(
                key=lambda item: (
                    0 if item.get("kind") == "prompt" else 1,
                    item.get("sort_text", '') if item.get("kind") == "prompt" else str(item.get("category_path", '')).casefold(),
                    0 if item.get("kind") == "category" else 1,
                    str(item.get("prompt_path", '')).casefold(),
                )
            )
        else:
            items.sort(
                key=lambda item: (
                    0 if item.get("kind") == "prompt" else 1 if item.get("kind") == "category" else 2,
                    item.get("sort_text", ''),
                )
            )
        return items

    def _completion_item_data(self, item: Optional[QtWidgets.QListWidgetItem]) -> Dict[str, Any]:
        if item is None:
            return {}
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, dict):
            return data
        text = str(item.text() if item.text() is not None else '')
        return {"display_text": text, "insert_text": text, "kind": "prompt"}

    def _show_prompt_completion_popup(self, matches: List[Dict[str, Any]]) -> None:
        """Render the current match list below the input caret."""

        popup = self._prompt_completion_popup
        with QtCore.QSignalBlocker(popup):
            popup.clear()
            for match in matches:
                item = QtWidgets.QListWidgetItem(str(match.get("display_text", "")))
                item.setData(Qt.ItemDataRole.UserRole, match)
                item.setToolTip(str(match.get("tooltip", "")))
                popup.addItem(item)
            if popup.count() > 0:
                popup.setCurrentRow(0)

        cursor_rect = self.ui.plainTextEdit_question.cursorRect()
        popup_pos = self.ui.plainTextEdit_question.viewport().mapTo(
            self,
            cursor_rect.bottomLeft(),
        )
        visible_rows = min(max(1, popup.count()), 8)
        width = max(
            240,
            popup.sizeHintForColumn(0) + popup.frameWidth() * 2 + 24,
        )
        row_height = popup.sizeHintForRow(0)
        if row_height <= 0:
            row_height = popup.fontMetrics().height() + 8
        height = popup.frameWidth() * 2 + row_height * visible_rows + 4
        popup.resize(width, height)
        popup.move(popup_pos)
        popup.show()
        popup.raise_()
        self.ui.plainTextEdit_question.setFocus(Qt.FocusReason.OtherFocusReason)

    def _hide_prompt_completion_popup(self, accept: bool = False) -> None:
        """Hide the completion popup without changing inline state."""

        popup = self._prompt_completion_popup
        if popup.isVisible():
            self._prompt_completion_accepting = accept
            popup.hide()
            self._prompt_completion_accepting = False
        with QtCore.QSignalBlocker(popup):
            popup.clear()

    def _hide_transient_chat_overlays(self) -> None:
        """Hide popup widgets that can otherwise linger after tab initialization."""

        if hasattr(self, "_prompt_completion_popup"):
            self._hide_prompt_completion_popup(accept=False)
        try:
            self.ui.comboBox_ai_chats.hidePopup()
            self.ui.comboBox_ai_chats.view().hide()
        except Exception:
            pass

    def _discard_inline_prompt_completion(self) -> bool:
        """Remove the transient inline completion suffix if it is still present."""

        state = self._prompt_inline_completion
        self._prompt_inline_completion = None
        if not state:
            return False

        suffix = str(state.get("suffix", ""))
        start = int(state.get("start", -1))
        end = int(state.get("end", -1))
        editor = self.ui.plainTextEdit_question
        current_text = editor.toPlainText()
        if suffix == '' or start < 0 or end < start or end > len(current_text):
            return False
        if current_text[start:end] != suffix:
            return False

        cursor = editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QtGui.QTextCursor.MoveMode.KeepAnchor)
        if cursor.selectedText() != suffix:
            return False
        cursor.removeSelectedText()
        editor.setTextCursor(cursor)
        return True

    def _preview_prompt_completion(self, completion_text: str, context: Dict[str, Any]) -> None:
        """Insert the suggested suffix as selected text so typing can overwrite it."""

        typed = str(context.get("typed", ""))
        if len(typed) <= 1:
            self._prompt_inline_completion = None
            return
        if not completion_text.startswith(typed):
            self._prompt_inline_completion = None
            return

        suffix = completion_text[len(typed):]
        if suffix == '':
            self._prompt_inline_completion = None
            return

        editor = self.ui.plainTextEdit_question
        cursor = editor.textCursor()
        insert_start = cursor.position()
        cursor.insertText(suffix)
        cursor.setPosition(insert_start)
        cursor.setPosition(insert_start + len(suffix), QtGui.QTextCursor.MoveMode.KeepAnchor)
        editor.setTextCursor(cursor)
        self._prompt_inline_completion = {
            "start": insert_start,
            "end": insert_start + len(suffix),
            "suffix": suffix,
        }

    def _accept_prompt_completion(self) -> bool:
        """Commit the current completion selection into the editor."""

        item = self._prompt_completion_popup.currentItem()
        completion_data = self._completion_item_data(item)
        completion_text = str(completion_data.get("insert_text", ""))
        if completion_text == '':
            return False

        context = self._current_prompt_completion_context()
        if self._prompt_inline_completion is not None:
            state = self._prompt_inline_completion
            self._prompt_inline_completion = None
            cursor = self.ui.plainTextEdit_question.textCursor()
            cursor.setPosition(int(state.get("end", cursor.position())))
            cursor.clearSelection()
            self.ui.plainTextEdit_question.setTextCursor(cursor)
            self._hide_prompt_completion_popup(accept=True)
            if completion_data.get("kind") == "category":
                QtCore.QTimer.singleShot(0, self._sync_prompt_completion)
            return True

        if context is None:
            return False

        cursor = self.ui.plainTextEdit_question.textCursor()
        cursor.setPosition(int(context["start"]))
        cursor.setPosition(int(context["end"]), QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.insertText(completion_text)
        self.ui.plainTextEdit_question.setTextCursor(cursor)
        self._hide_prompt_completion_popup(accept=True)
        if completion_data.get("kind") == "category":
            QtCore.QTimer.singleShot(0, self._sync_prompt_completion)
        return True

    def _dismiss_prompt_completion(self, accept: bool = False) -> None:
        """Close prompt completion and either keep or discard the inline suggestion."""

        if accept:
            self._accept_prompt_completion()
            return
        if self._prompt_completion_guard:
            return
        self._prompt_completion_guard = True
        try:
            self._hide_prompt_completion_popup(accept=False)
            self._discard_inline_prompt_completion()
        finally:
            self._prompt_completion_guard = False

    def _move_prompt_completion_selection(self, step: int) -> bool:
        """Move the highlighted completion popup row."""

        popup = self._prompt_completion_popup
        if not popup.isVisible() or popup.count() == 0:
            return False
        current_row = popup.currentRow()
        if current_row < 0:
            current_row = 0
        new_row = max(0, min(popup.count() - 1, current_row + step))
        if new_row == current_row:
            return True
        popup.setCurrentRow(new_row)
        return True

    def _sync_prompt_completion(self) -> None:
        """Refresh popup filtering and inline preview after text/caret changes."""

        if self._prompt_completion_guard:
            return
        if self._prompt_completion_temporarily_disabled:
            return
        if not self._prompt_completion_enabled():
            self._dismiss_prompt_completion(accept=False)
            return

        self._prompt_completion_guard = True
        try:
            self._discard_inline_prompt_completion()
            context = self._current_prompt_completion_context()
            if context is None:
                self._hide_prompt_completion_popup(accept=False)
                return

            matches = self._matching_prompt_completion_items(context.get("typed", ""))
            if len(matches) == 0:
                self._hide_prompt_completion_popup(accept=False)
                return

            self._show_prompt_completion_popup(matches)
            self._preview_prompt_completion(str(matches[0].get("insert_text", "")), context)
        finally:
            self._prompt_completion_guard = False

    def _prompt_completion_current_item_changed(self, current, previous) -> None:
        """Update the inline preview when the highlighted popup row changes."""

        del previous
        if self._prompt_completion_guard or current is None:
            return
        context = self._current_prompt_completion_context()
        completion_text = str(self._completion_item_data(current).get("insert_text", ""))
        if context is None or completion_text == '':
            return

        self._prompt_completion_guard = True
        try:
            self._discard_inline_prompt_completion()
            context = self._current_prompt_completion_context()
            if context is None:
                return
            self._preview_prompt_completion(completion_text, context)
        finally:
            self._prompt_completion_guard = False

    def _prompt_completion_item_clicked(self, item) -> None:
        del item
        self._accept_prompt_completion()

    def _prompt_completion_item_entered(self, item) -> None:
        if item is not None:
            self._prompt_completion_popup.setCurrentItem(item)

    def _prompt_completion_popup_hidden(self) -> None:
        """Discard transient inline text when the popup disappears unexpectedly."""

        if (
                getattr(self, "_prompt_completion_accepting", False) or
                getattr(self, "_prompt_completion_guard", False)
        ):
            return
        self._dismiss_prompt_completion(accept=False)

    def _blend_colors(self, foreground: QtGui.QColor, background: QtGui.QColor, amount: float) -> QtGui.QColor:
        """Blend foreground into background by amount in the 0..1 range."""

        amount = max(0.0, min(1.0, float(amount)))
        if not foreground.isValid():
            foreground = QtGui.QColor("#287368")
        if not background.isValid():
            background = QtGui.QColor("#ffffff")
        red = round(foreground.red() * amount + background.red() * (1.0 - amount))
        green = round(foreground.green() * amount + background.green() * (1.0 - amount))
        blue = round(foreground.blue() * amount + background.blue() * (1.0 - amount))
        return QtGui.QColor(red, green, blue)

    def _update_prompt_reference_styles(self, background_color: QtGui.QColor) -> None:
        """Prepare contrast-aware prompt reference styles for input and chat output."""

        user_color = QtGui.QColor(str(getattr(self, "ai_user_color", "#287368")))
        if not background_color.isValid():
            background_color = self.ui.plainTextEdit_question.palette().color(
                self.ui.plainTextEdit_question.viewport().backgroundRole()
            )
        is_dark = background_color.lightness() < 128
        highlight_amount = 0.22 if is_dark else 0.10
        valid_background = self._blend_colors(user_color, background_color, highlight_amount)

        self._prompt_reference_styles = {
            "valid": {
                "foreground": user_color,
                "background": valid_background,
                "html_background": valid_background.name(),
                "html_foreground": user_color.name(),
            },
        }
        if hasattr(self, "_prompt_reference_highlighter"):
            self._prompt_reference_highlighter.rehighlight()

    def _prompt_reference_prompt_names(self) -> set[str]:
        """Return known slash-callable prompt names for the current chat."""

        return {
            str(prompt.name if prompt.name is not None else '').strip('/').casefold()
            for prompt in self._prompt_completion_records
            if str(prompt.name if prompt.name is not None else '').strip('/') != ''
        }

    def _prompt_reference_records_by_name(self) -> Dict[str, AgentPromptRecord]:
        """Return prompt records keyed by normalized slash reference name."""

        return {
            str(prompt.name if prompt.name is not None else '').strip('/').casefold(): prompt
            for prompt in self._prompt_completion_records
            if str(prompt.name if prompt.name is not None else '').strip('/') != ''
        }

    def _prompt_reference_tooltip(self, prompt: AgentPromptRecord) -> str:
        """Build tooltip text for a recognized slash prompt reference."""

        tooltip_lines = [f'/{prompt.name}']
        scope = str(prompt.scope if prompt.scope is not None else '').strip()
        if scope != '':
            tooltip_lines.append(f'[{scope}]')
        description = str(prompt.description if prompt.description is not None else '').strip()
        if description != '':
            tooltip_lines.append(description)
        return '\n'.join(tooltip_lines)

    def _prompt_reference_record_at_position(self, pos: QtCore.QPoint) -> Optional[AgentPromptRecord]:
        """Return the prompt record under a viewport position in the input editor."""

        if not self._prompt_completion_enabled():
            return None
        self._refresh_prompt_completion_records()
        editor = self.ui.plainTextEdit_question
        cursor = editor.cursorForPosition(pos)
        char_pos = cursor.position()
        text = editor.toPlainText()
        records_by_name = self._prompt_reference_records_by_name()
        if char_pos < 0 or char_pos > len(text) or len(records_by_name) == 0:
            return None
        for match in PROMPT_SLASH_REF_PATTERN.finditer(text):
            if match.start() <= char_pos <= match.end():
                prompt_name = match.group(0)[1:].rstrip('/.,;:!?').casefold()
                return records_by_name.get(prompt_name)
        return None

    def _prompt_reference_html_span(self, token: str, known: bool) -> str:
        """Render one slash reference token as styled HTML."""

        escaped_token = html_lib.escape(str(token if token is not None else ''))
        if not known:
            return escaped_token
        styles = getattr(self, "_prompt_reference_styles", {})
        valid_style = styles.get("valid", {})
        background = html_lib.escape(str(valid_style.get("html_background", "")))
        foreground = html_lib.escape(str(valid_style.get("html_foreground", self.ai_user_color)))
        prompt_name = str(token if token is not None else '')[1:].rstrip('/.,;:!?')
        href = 'promptref:' + quote(prompt_name, safe='')
        return (
            f'<a href="{href}" style="color: {foreground}; text-decoration: none;">'
            '<span style="'
            f'background-color: {background};'
            f'">{escaped_token}</span>'
            '</a>'
        )

    def _render_user_markdown_to_html(self, text: str, hr_color: str = "#e6e6e6", hr_width_px: int = 600) -> str:
        """Render user Markdown and highlight slash prompt references without altering stored text."""

        if not self._prompt_completion_enabled():
            return render_markdown_to_html(text, hr_color=hr_color, hr_width_px=hr_width_px)

        known_prompt_names = self._prompt_reference_prompt_names()
        replacements: Dict[str, str] = {}

        def replace_prompt_ref(match: re.Match) -> str:
            token = match.group(0)
            prompt_name = token[1:].rstrip('/.,;:!?').casefold()
            placeholder = f"QUALCODER_PROMPT_REF_{len(replacements)}_TOKEN"
            replacements[placeholder] = self._prompt_reference_html_span(token, prompt_name in known_prompt_names)
            return placeholder

        marked_text = PROMPT_SLASH_REF_PATTERN.sub(replace_prompt_ref, str(text if text is not None else ''))
        rendered_html = render_markdown_to_html(marked_text, hr_color=hr_color, hr_width_px=hr_width_px)
        for placeholder, replacement in replacements.items():
            rendered_html = rendered_html.replace(placeholder, replacement)
        return rendered_html

    def init_styles(self):
        """Set up the stylesheets for the ui and the chat entries
        """
        self.load_ai_permissions()
        font_css = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        dialog_bg = self.ui.pushButton_question.palette().color(QPalette.ColorRole.Button).name()
        
        self.font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(self.font)
        # Set progressBar color to default highlight color
        self.ui.progressBar_ai.setStyleSheet(f"""
            QProgressBar::chunk {{
                background-color: {self.app.highlight_color()};
            }}
        """)
        self._prompt_completion_popup.setFont(self.ui.plainTextEdit_question.font())
        self.ui.pushButton_help.setIcon(qta.icon('mdi6.help'))
        self.ui.pushButton_help.setFixedHeight(self.ui.pushButton_delete.height())
        self.ui.pushButton_help.setFixedWidth(self.ui.pushButton_help.height())
        self.ui.pushButton_undo.setIcon(qta.icon('mdi6.undo'))
        self.ui.pushButton_undo.setFixedHeight(self.ui.pushButton_delete.height())
        self.ui.pushButton_undo.setFixedWidth(self.ui.pushButton_undo.height())
        self.ui.toolButton_close_sidebar.setIcon(qta.icon('mdi6.arrow-left-bold-outline'))
        self.ui.toolButton_close_sidebar.setIconSize(QtCore.QSize(16, 16))
        self.ui.toolButton_edit_title.setIcon(qta.icon('mdi6.pencil-outline'))
        self.ui.toolButton_edit_title.setIconSize(QtCore.QSize(16, 16))
        doc_font = f'font: {self.app.settings["docfontsize"]}pt \'{self.app.settings["font"]}\';'
        self.ai_response_color = "#356399"
        self.ai_user_color = "#287368"
        self.ai_status_color = "#808080"
        self.ai_response_style = f'"{doc_font} color: #356399;"'
        self.ai_user_style = f'"{doc_font} color: #287368;"'
        self.ai_info_style = f'"{doc_font}"'
        self.ai_status_style = f'"{doc_font} color: #808080;"'
        self.ai_actions_style = f'"{doc_font}"'
        if self.app.settings['stylesheet'] in ['dark', 'rainbow']:
            self.ai_response_color = "#8FB1D8"
            self.ai_user_color = "#35998A"
            self.ai_status_color = "#B5B5B5"
            self.ai_response_style = f'"{doc_font} color: {self.ai_response_color};"'
            self.ai_user_style = f'"{doc_font} color: {self.ai_user_color};"'
            self.ai_info_style = f'"{doc_font}"'
            self.ai_status_style = f'"{doc_font} color: {self.ai_status_color};"'
        elif self.app.settings['stylesheet'] == 'native':
            # Determine whether dark or light native style is active:
            style_hints = QGuiApplication.styleHints()
            # Older versions fot PyQt6 may not have QGuiApplication.styleHints().colorScheme() e.g. PtQ66 vers 6.2.3
            try:
                if style_hints.colorScheme() == QtCore.Qt.ColorScheme.Dark:
                    self.ai_response_color = "#8FB1D8"
                    self.ai_user_color = "#35998A"
                    self.ai_status_color = "#B5B5B5"
                    self.ai_response_style = f'"{doc_font} color: {self.ai_response_color};"'
                    self.ai_user_style = f'"{doc_font} color: {self.ai_user_color};"'
                    self.ai_info_style = f'"{doc_font}"'
                    self.ai_status_style = f'"{doc_font} color: {self.ai_status_color};"'
                else:
                    self.ai_response_color = "#356399"
                    self.ai_user_color = "#287368"
                    self.ai_status_color = "#808080"
                    self.ai_response_style = f'"{doc_font} color: {self.ai_response_color};"'
                    self.ai_user_style = f'"{doc_font} color: {self.ai_user_color};"'
                    self.ai_info_style = f'"{doc_font}"'
                    self.ai_status_style = f'"{doc_font} color: {self.ai_status_color};"'
            except AttributeError as e_:
                print(f"Using older version of PyQT6? {e_}")
                logger.debug(f"Using older version of PyQT6? {e_}")
                pass
        else:
            self.ai_response_color = "#356399"
            self.ai_user_color = "#287368"
            self.ai_status_color = "#808080"
            self.ai_response_style = f'"{doc_font} color: {self.ai_response_color};"'
            self.ai_user_style = f'"{doc_font} color: {self.ai_user_color};"'
            self.ai_info_style = f'"{doc_font}"'
            self.ai_status_style = f'"{doc_font} color: {self.ai_status_color};"'
        self.ui.plainTextEdit_question.setStyleSheet(self.ai_user_style[1:-1])
        default_bg_color = self.ui.plainTextEdit_question.palette().color(self.ui.plainTextEdit_question.viewport().backgroundRole())
        self._update_prompt_reference_styles(default_bg_color)
        self.ui.ai_output.setAutoFillBackground(True)
        self.ui.ai_output.setStyleSheet(f"""
            QLabel#ai_output {{
                {doc_font}
                background-color: {default_bg_color.name()};
                border: none;
            }}
            QLabel#ai_output:focus {{
                border: none;
            }}
        """)
        self.ui.scrollArea_ai_output.setStyleSheet(f'background-color: {default_bg_color.name()};')
        default_panel_color = self.ui.widget_chat.palette().color(self.ui.widget_chat.backgroundRole())
        self.ui.comboBox_ai_chats.setStyleSheet(f"""
            QComboBox {{
                background-color: {default_panel_color.name()};
            }}
        """)
        self.ui.comboBox_ai_permissions.setStyleSheet(f"""
            QComboBox {{
                background-color: {default_panel_color.name()};
            }}
        """)
        self.update_chat_window()

    def setup_ai_permissions_combobox(self):
        """Replace the Designer combobox with a prefixed, non-editable combobox."""

        old_combo = self.ui.comboBox_ai_permissions
        new_combo = PrefixedComboBox(_("AI Permissions:"), old_combo.parentWidget())
        new_combo.setObjectName(old_combo.objectName())
        new_combo.setEnabled(old_combo.isEnabled())
        new_combo.setToolTip(old_combo.toolTip())
        new_combo.setStatusTip(old_combo.statusTip())
        new_combo.setWhatsThis(old_combo.whatsThis())
        new_combo.setAccessibleName(old_combo.accessibleName())
        new_combo.setAccessibleDescription(old_combo.accessibleDescription())
        new_combo.setSizePolicy(old_combo.sizePolicy())
        new_combo.setMinimumSize(old_combo.minimumSize())
        new_combo.setMaximumSize(old_combo.maximumSize())
        new_combo.setMinimumContentsLength(old_combo.minimumContentsLength())
        new_combo.setSizeAdjustPolicy(old_combo.sizeAdjustPolicy())
        new_combo.setFont(old_combo.font())
        for i in range(old_combo.count()):
            new_combo.addItem(old_combo.itemIcon(i), old_combo.itemText(i), old_combo.itemData(i))
        new_combo.setCurrentIndex(old_combo.currentIndex())
        layout = old_combo.parentWidget().layout()
        layout.replaceWidget(old_combo, new_combo)
        old_combo.deleteLater()
        self.ui.comboBox_ai_permissions = new_combo

    def load_ai_permissions(self):
        ai_permissions = self.app.settings.get('ai_permissions', 1)
        if ai_permissions not in (0, 1, 2):
            ai_permissions = 1
            self.app.settings['ai_permissions'] = ai_permissions
        with QtCore.QSignalBlocker(self.ui.comboBox_ai_permissions):
            self.ui.comboBox_ai_permissions.setCurrentIndex(ai_permissions)

    def ai_permissions_changed(self, index=None):
        combo_index = self.ui.comboBox_ai_permissions.currentIndex()
        if combo_index not in (0, 1, 2):
            ai_permissions = 1
        else:
            ai_permissions = combo_index
        previous_permissions = self.app.settings.get('ai_permissions', 1)
        if previous_permissions == ai_permissions:
            return
        self.app.settings['ai_permissions'] = ai_permissions
        try:
            self.app.write_config_ini(self.app.settings, self.app.ai_models)
        except Exception as e_:
            logger.debug(f"Could not persist ai permissions setting: {e_}")
        self._log_ai_permissions_env_update(previous_permissions, ai_permissions)
        
    def init_ai_chat(self, app=None):
        if app is not None:
            self.app = app
            self.ai_mcp_server = AiMcpServer(self.app)
            self.load_ai_permissions()
        # init chat history
        self.chat_history_folder = self.app.project_path + '/ai_data'
        if not os.path.exists(self.chat_history_folder):
            os.makedirs(self.chat_history_folder)
        self.chat_history_path = self.chat_history_folder + '/chat_history.sqlite'            
        self.chat_history_conn = sqlite3.connect(self.chat_history_path)
        cursor = self.chat_history_conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS chats (
                                id INTEGER PRIMARY KEY,
                                name TEXT,
                                analysis_type TEXT,
                                summary TEXT,
                                date TEXT,
                                analysis_prompt TEXT)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS chat_messages (
                                id INTEGER PRIMARY KEY,
                                chat_id INTEGER,
                                msg_type TEXT,
                                msg_author TEXT,
                                msg_content TEXT,
                                FOREIGN KEY (chat_id) REFERENCES chats(id))''')
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS topic_chat_embeddings (
                                id INTEGER PRIMARY KEY,
                                chat_id INTEGER,
                                docstore_id TEXT,
                                position INTEGER,
                                used_flag INTEGER,
                                FOREIGN KEY (chat_id) REFERENCES chats(id))''')
        self.chat_history_conn.commit()
        self.current_chat_idx = -1
        self.fill_chat_list()
        self._update_undo_button_state()
    
    def close(self):
        self.ai_output_splitter_save_timer.stop()
        self.persist_ai_output_splitter_setting()
        if self.chat_history_conn is not None:
            self.chat_history_conn.close()
            
    def help(self):
        """ Open help in browser. """
        self.app.help_wiki("5.1.-AI-chat-based-analysis")

    def _undo_ai_changes_shortcut(self):
        ai = getattr(self.app, "ai", None)
        if ai is None:
            self._update_undo_button_state()
            return
        ai.undo_ai_agent_changes()
        self._update_undo_button_state()

    def _update_undo_button_state(self):
        """Enable undo only when the current AI session has undoable changes."""

        enabled = False
        ai = getattr(self.app, "ai", None)
        if ai is not None and hasattr(ai, "has_undoable_ai_changes"):
            try:
                enabled = bool(ai.has_undoable_ai_changes())
            except Exception:
                enabled = False
        self.ui.pushButton_undo.setEnabled(enabled)

    def _get_saved_ai_output_splitter_bottom(self):
        """Return the saved bottom pane height for the AI output splitter."""

        try:
            bottom_height = int(self.app.settings.get('ai_chat_splitter_output_bottom', 80))
        except (TypeError, ValueError):
            bottom_height = 80
        return max(1, bottom_height)

    def schedule_ai_output_splitter_restore(self):
        """Restore the AI output splitter after the widget has a real visible layout."""

        self.ai_output_splitter_restore_attempts = 0
        self.ai_output_splitter_is_restoring = True
        QtCore.QTimer.singleShot(0, self.restore_ai_output_splitter)
        QtCore.QTimer.singleShot(60, self.restore_ai_output_splitter)
        QtCore.QTimer.singleShot(180, self.restore_ai_output_splitter)

    def showEvent(self, event):
        """Restore splitter geometry when the embedded chat widget becomes visible."""

        super().showEvent(event)
        self.schedule_ai_output_splitter_restore()

    def restore_ai_output_splitter(self):
        """Restore splitter position so the lower pane defaults to 80px when unset."""

        if not self.isVisible() or not self.ui.splitter_ai_output.isVisible():
            return
        saved_bottom_height = self._get_saved_ai_output_splitter_bottom()
        sizes = self.ui.splitter_ai_output.sizes()
        total_height = sum(sizes)
        if total_height <= 0:
            total_height = self.ui.splitter_ai_output.height()
        minimum_top_height = 80
        if total_height <= 0:
            # Layout is not ready yet; retry briefly, but avoid endless retries.
            if self.ai_output_splitter_restore_attempts < 20:
                self.ai_output_splitter_restore_attempts += 1
                QtCore.QTimer.singleShot(30, self.restore_ai_output_splitter)
            else:
                self.ai_output_splitter_is_restoring = False
            return
        if total_height < saved_bottom_height + minimum_top_height and self.ai_output_splitter_restore_attempts < 20:
            self.ai_output_splitter_restore_attempts += 1
            QtCore.QTimer.singleShot(30, self.restore_ai_output_splitter)
            return
        self.ai_output_splitter_restore_attempts = 0
        bottom_height = min(saved_bottom_height, max(1, total_height - minimum_top_height))
        top_height = max(1, total_height - bottom_height)
        self.ai_output_splitter_is_restoring = True
        try:
            with QtCore.QSignalBlocker(self.ui.splitter_ai_output):
                self.ui.splitter_ai_output.setSizes([top_height, bottom_height])
        finally:
            self.ai_output_splitter_is_restoring = False

    def on_ai_output_splitter_moved(self, pos=None, index=None):
        """Track splitter movement and persist the current lower pane height."""

        if getattr(self, 'ai_output_splitter_is_restoring', False):
            return
        sizes = self.ui.splitter_ai_output.sizes()
        if len(sizes) < 2:
            return
        bottom_height = int(sizes[1])
        if bottom_height <= 0:
            return
        self.app.settings['ai_chat_splitter_output_bottom'] = bottom_height
        self.ai_output_splitter_save_timer.start(400)

    def persist_ai_output_splitter_setting(self):
        """Write splitter setting to config.ini after drag operations settle."""

        try:
            self.app.write_config_ini(self.app.settings, self.app.ai_models)
        except Exception as e_:
            logger.debug(f"Could not persist ai output splitter setting: {e_}")

    def _move_left_controls_to_chat(self):
        """Place the left controls widget at the bottom of the chat area."""

        self.ui.verticalLayout_2.removeWidget(self.ui.widget_left_buttons)
        self.ui.verticalLayout_4.addWidget(self.ui.widget_left_buttons)

    def _move_left_controls_to_left(self):
        """Restore the left controls widget under the tree view."""

        self.ui.verticalLayout_4.removeWidget(self.ui.widget_left_buttons)
        self.ui.verticalLayout_2.insertWidget(1, self.ui.widget_left_buttons)

    def _move_chat_widget_to_sidebar(self):
        """Use full width below the top bar in sidebar mode."""

        self.ui.gridLayout.removeWidget(self.ui.widget_chat)
        self.ui.gridLayout.addWidget(self.ui.widget_chat, 3, 0, 1, 2)

    def _move_chat_widget_to_main(self):
        """Restore split layout with chat on the right side."""

        self.ui.gridLayout.removeWidget(self.ui.widget_chat)
        self.ui.gridLayout.addWidget(self.ui.widget_chat, 3, 1, 1, 1)

    def _detach_widget_left_from_grid(self):
        """Remove left panel from outer grid so it contributes no minimum width."""

        if self.ui.gridLayout.indexOf(self.ui.widget_left) != -1:
            self.ui.gridLayout.removeWidget(self.ui.widget_left)

    def _attach_widget_left_to_grid(self):
        """Insert left panel back into outer grid in main view."""

        if self.ui.gridLayout.indexOf(self.ui.widget_left) == -1:
            self.ui.gridLayout.addWidget(self.ui.widget_left, 3, 0, 1, 1)

    def set_sidebar_mode(self, enabled):
        """Switch dialog internals between main view and sidebar view."""

        if enabled:
            self.ui.gridLayout.setContentsMargins(0, 0, 0, 0)
            self._move_chat_widget_to_sidebar()
            self._move_left_controls_to_chat()
            self._detach_widget_left_from_grid()
            self.setMinimumWidth(0)
            self.ui.widget_chat.setMinimumWidth(0)
            self.ui.widget_top.setMinimumWidth(0)
            self.ui.comboBox_ai_chats.setMinimumWidth(0)
            self.ui.widget_left.setMinimumWidth(0)
            self.ui.widget_left.setMaximumWidth(0)
            self.ui.widget_left.setVisible(False)
            self.ui.widget_top.setVisible(True)
        else:
            self.ui.gridLayout.setContentsMargins(6, 6, 6, 6)
            self._move_chat_widget_to_main()
            self._attach_widget_left_to_grid()
            self._move_left_controls_to_left()
            self.ui.widget_left.setMaximumWidth(16777215)
            self.ui.widget_left.setVisible(True)
            self.ui.widget_top.setVisible(False)
        self._hide_transient_chat_overlays()
        self.ui.gridLayout.invalidate()
        self.updateGeometry()
        self.schedule_ai_output_splitter_restore()

    def close_sidebar_view(self):
        """Close sidebar mode and return AI chat to the main tab."""

        self.main_window.close_ai_chat_sidebar()

    def combo_chat_selection_changed(self, index):
        """Select the current chat when chosen via sidebar combo box."""

        if index < 0:
            self._set_chat_list_current_row(-1)
            return
        self._set_chat_list_current_row(index)

    def get_chat_list(self):
        """Load the current chat list from the database into self.chat_list
        """
        cursor = self.chat_history_conn.cursor()
        cursor.execute('SELECT id, name, analysis_type, summary, date, analysis_prompt FROM chats ORDER BY date DESC')
        self.chat_list = cursor.fetchall()
        if self.current_chat_idx >= len(self.chat_list):
            self.current_chat_idx = len(self.chat_list) - 1    

    def _is_agent_chat_type(self, analysis_type: str) -> bool:
        normalized = str(analysis_type if analysis_type is not None else '').strip().lower()
        return normalized in ('general chat', 'agent chat', 'topic_exploration', 'code_analysis', 'text_analysis')

    def _display_chat_type_label(self, analysis_type: str, preserve_legacy_general: bool = False) -> str:
        normalized = str(analysis_type if analysis_type is not None else '').strip().lower()
        raw_value = str(analysis_type if analysis_type is not None else '').strip()
        if normalized == 'general chat' and preserve_legacy_general:
            return raw_value or 'general chat'
        if normalized == 'agent chat':
            return _('AI Agent Chat')
        if normalized == 'code_analysis':
            return _('Code analysis')
        if normalized == 'code chat':
            return _('Code analysis (legacy)')
        if normalized == 'text_analysis':
            return _('Text analysis')
        if normalized == 'text chat':
            return _('Text analysis (legacy)')
        if normalized == 'topic_exploration':
            return _('Topic exploration')
        if normalized == 'topic chat':
            return _('Topic exploration (legacy)')
        return raw_value

    def _empty_agent_chat_alias(self) -> str:
        return _('New Agent Chat')

    def _display_chat_name(self, name: str, analysis_type: str) -> str:
        clean_name = str(name if name is not None else '').strip()
        if clean_name == '' and self._is_agent_chat_type(analysis_type):
            return self._empty_agent_chat_alias()
        return clean_name

    def _current_ai_profile_name(self) -> str:
        try:
            author = str(self.app.ai_models[int(self.app.settings['ai_model_index'])]['name']).strip()
        except Exception:
            author = ''
        return author or 'unknown'

    def _normalize_ai_profile_author(self, author: str = '', chat_idx: Optional[int] = None,
                                     fallback_to_current: bool = False) -> str:
        """Resolve display/storage author names for AI messages."""

        raw_author = str(author if author is not None else '').strip()
        if raw_author != '' and raw_author not in ('ai_agent', 'mcp_server', 'system_event'):
            return raw_author

        if chat_idx is None:
            chat_idx = self.current_chat_idx
        if chat_idx is not None and chat_idx >= 0:
            snapshot = str(self._chat_ai_profile_snapshots.get(int(chat_idx), '')).strip()
            if snapshot != '':
                return snapshot

        if fallback_to_current:
            return self._current_ai_profile_name()
        return 'unknown'

    def _capture_chat_ai_profile_snapshot(self, chat_idx: Optional[int] = None) -> str:
        """Freeze the currently selected AI profile for one chat run."""

        if chat_idx is None:
            chat_idx = self.current_chat_idx
        author = self._current_ai_profile_name()
        if chat_idx is not None and chat_idx >= 0:
            self._chat_ai_profile_snapshots[int(chat_idx)] = author
        return author

    def _clear_chat_ai_profile_snapshot(self, chat_idx: Optional[int] = None) -> None:
        """Remove a previously frozen AI profile snapshot for one chat."""

        if chat_idx is None:
            chat_idx = self.current_chat_idx
        if chat_idx is None or chat_idx < 0:
            return
        self._chat_ai_profile_snapshots.pop(int(chat_idx), None)

    def _message_heading_html(self, heading_text: str) -> str:
        safe_heading = html_lib.escape(str(heading_text if heading_text is not None else ""))
        heading_size = self.app.settings['fontsize'] + 1
        return f'<div style="margin-top: 6px; font-size: {heading_size}pt;">⦿ <b>{safe_heading}</b></div>'

    def _ai_agent_heading_html(self, author: str = '', chat_idx: Optional[int] = None,
                               fallback_to_current: bool = False) -> str:
        display_author = self._normalize_ai_profile_author(
            author,
            chat_idx=chat_idx,
            fallback_to_current=fallback_to_current,
        )
        return self._message_heading_html(f'{_("AI Agent")} ({display_author}):')
            
    def fill_chat_list(self):
        self.chat_list_model.clear()
        self.get_chat_list()
        for i in range(len(self.chat_list)):
            chat = self.chat_list[i]
            id_, name, analysis_type, summary, date, analysis_prompt = chat
            tooltip_text = self._chat_tooltip_text(chat)

            # Creating a new QListWidgetItem
            if str(analysis_type).strip().lower() == 'code_analysis':
                icon = self.app.ai.code_analysis_icon()
            elif str(analysis_type).strip().lower() == 'text_analysis':
                icon = self.app.ai.text_analysis_icon()
            elif str(analysis_type).strip().lower() == 'topic_exploration':
                icon = self.app.ai.topic_exploration_icon()
            elif self._is_agent_chat_type(analysis_type):
                icon = self.app.ai.general_chat_icon()
            elif analysis_type == 'topic chat':
                icon = self.app.ai.topic_exploration_icon()
            elif analysis_type == 'text chat':
                icon = self.app.ai.text_analysis_icon()
            elif analysis_type == 'code chat':
                icon = self.app.ai.code_analysis_icon()
            else: # unknown type, ignore this chat altogether
                continue

            item = QStandardItem(icon, self._display_chat_name(name, analysis_type))
            item.setToolTip(tooltip_text)
            item.setEditable(True)
            self.chat_list_model.appendRow(item)
            #if i == self.current_chat_idx:
            #    item.setSelected(True)
        if self.current_chat_idx >= len(self.chat_list):
            self.current_chat_idx = len(self.chat_list) - 1
        self._set_chat_list_current_row(self.current_chat_idx)
        self.chat_list_selection_changed(force_update=True)

    def _chat_tooltip_text(self, chat):
        """Build tooltip text for a chat list item."""

        id_, name, analysis_type, summary, date, analysis_prompt = chat
        display_name = self._display_chat_name(name, analysis_type)
        display_type = self._display_chat_type_label(analysis_type, preserve_legacy_general=True)
        if not self._is_agent_chat_type(analysis_type):
            return f"{display_name}\nType: {display_type}\nSummary: {summary}\nDate: {date}\nPrompt: {analysis_prompt}"
        return f"{display_name}\nType: {display_type}\nSummary: {summary}\nDate: {date}"

    def _refresh_chat_list_item(self, row: int) -> None:
        """Refresh one visible chat-list entry from self.chat_list."""

        if row < 0 or row >= len(self.chat_list):
            return
        item = self.chat_list_model.item(row)
        if item is None:
            return
        chat = self.chat_list[row]
        display_name = self._display_chat_name(chat[1], chat[2])
        self._is_updating_chat_title_item = True
        try:
            item.setText(display_name)
            item.setToolTip(self._chat_tooltip_text(chat))
        finally:
            self._is_updating_chat_title_item = False

    def _refresh_chat_name_views(self):
        """Force visible chat-title widgets to repaint after a model update."""

        self.ui.treeView_chat_list.viewport().update()
        self.ui.treeView_chat_list.update()
        self.ui.comboBox_ai_chats.view().viewport().update()
        self.ui.comboBox_ai_chats.view().update()
        self.ui.comboBox_ai_chats.update()

    def _create_text_input_dialog(self, title: str, label: str, text: str) -> QtWidgets.QInputDialog:
        """Create the standard styled text input dialog for embedded AI chat usage."""

        dialog = QtWidgets.QInputDialog(self.main_window)
        dialog.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
        dialog.setWindowTitle(title)
        dialog.setWindowFlags(dialog.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setWindowModality(QtCore.Qt.WindowModality.ApplicationModal)
        dialog.setModal(True)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog.setLabelText(label)
        dialog.setTextValue(text)
        dialog.resize(320, 20)
        return dialog

    def _rename_chat_at_row(self, row: int, new_name: str) -> bool:
        """Persist a new title for the chat at the given row."""

        if row < 0 or row >= len(self.chat_list):
            return False
        clean_name = str(new_name).strip()
        if clean_name == '':
            Message(self.app, _('AI Chat'), _('Please enter a chat title.'), icon='warning').exec()
            return False
        chat = self.chat_list[row]
        chat_id = chat[0]
        if clean_name == chat[1]:
            return False
        cursor = self.chat_history_conn.cursor()
        cursor.execute('UPDATE chats SET name = ? WHERE id = ?', (clean_name, chat_id))
        self.chat_history_conn.commit()
        updated_chat = (chat[0], clean_name, chat[2], chat[3], chat[4], chat[5])
        self.chat_list[row] = updated_chat
        self._refresh_chat_list_item(row)
        self._refresh_chat_name_views()
        self.update_chat_window()
        return True

    def _clear_stream_preview_buffers(self):
        """Clear transient streamed-preview text without touching persisted chat history."""

        self._cancel_pending_stream_render()
        self.ai_streaming_output = ''
        ai = getattr(self.app, 'ai', None)
        if ai is not None:
            try:
                ai.ai_streaming_output = ''
            except Exception:
                pass

    def _schedule_stream_render(self):
        """Coalesce streaming UI refreshes to avoid re-rendering on every chunk."""

        self.ai_stream_render_pending = True
        if not self.ai_stream_render_timer.isActive():
            self.ai_stream_render_timer.start(300)

    def _cancel_pending_stream_render(self):
        """Cancel any deferred streaming UI refresh."""

        self.ai_stream_render_pending = False
        if self.ai_stream_render_timer.isActive():
            self.ai_stream_render_timer.stop()

    def _flush_stream_render(self):
        """Apply one deferred streaming UI refresh."""

        if not self.ai_stream_render_pending:
            return
        if self.is_updating_chat_window:
            self.ai_stream_render_timer.start(300)
            return
        self.ai_stream_render_pending = False
        self.update_chat_window()

    def _chat_scope_active(self, chat_idx=None) -> bool:
        if chat_idx is None:
            chat_idx = self.current_chat_idx
        ai = getattr(self.app, 'ai', None)
        if ai is None or chat_idx is None or chat_idx < 0:
            return False
        if hasattr(ai, 'has_active_runs'):
            try:
                return bool(ai.has_active_runs('chat', chat_idx))
            except Exception:
                return False
        return False

    def _chat_scope_status(self, chat_idx=None) -> str:
        if chat_idx is None:
            chat_idx = self.current_chat_idx
        ai = getattr(self.app, 'ai', None)
        if ai is None or chat_idx is None or chat_idx < 0:
            return 'idle'
        if hasattr(ai, 'get_scope_status'):
            try:
                return str(ai.get_scope_status('chat', chat_idx)).strip() or 'idle'
            except Exception:
                return 'idle'
        return 'idle'

    def _cancel_chat_scope(self, chat_idx=None, ask: bool = False) -> bool:
        if chat_idx is None:
            chat_idx = self.current_chat_idx
        if chat_idx is None or chat_idx < 0:
            return True
        ai = getattr(self.app, 'ai', None)
        if ai is None:
            return True
        if not self._chat_scope_active(chat_idx):
            return True
        if ask:
            msg = _('Do you really want to cancel the AI operation?')
            msg_box = Message(self.app, 'AI Cancel', msg)
            msg_box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
            reply = msg_box.exec()
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                return False
        if hasattr(ai, 'cancel_scope'):
            success = bool(ai.cancel_scope('chat', chat_idx, wait_ms=5000))
        else:
            success = bool(ai.cancel(ask=False))
        if ask and not success:
            msg = _('The AI operation could not be aborted immediately. It may take a moment for the AI to be ready again.')
            Message(self.app, 'AI Cancel', msg).exec()
        self._clear_stream_preview_buffers()
        return success

    def new_chat(self, name, analysis_type, summary, analysis_prompt):
        self._clear_stream_preview_buffers()
        date = datetime.now()
        date_text = date.strftime('%Y-%m-%d %H:%M:%S')
        cursor = self.chat_history_conn.cursor()
        cursor.execute('''INSERT INTO chats (name, analysis_type, summary, date, analysis_prompt)
                            VALUES (?, ?, ?, ?, ?)''', (name, analysis_type, summary, date_text, analysis_prompt))
        self.chat_history_conn.commit()
        self.current_chat_idx = -1
        self.fill_chat_list()
        # select new chat
        self.current_chat_idx = self.find_chat_idx(cursor.lastrowid)
        self._set_chat_list_current_row(self.current_chat_idx)
        self.ai_output_autoscroll = True
        self.chat_list_selection_changed()

    def new_general_chat(self, name='', summary=''):
        if self.app.project_name == "":
            msg = _('No project open.')
            Message(self.app, _('AI not enabled'), msg, "warning").exec()
            return
        if self.app.settings['ai_enable'] != 'True':
            msg = _('The AI is disabled. Go to "AI > Setup Wizard" first.')
            Message(self.app, _('AI not enabled'), msg, "warning").exec()
            return

        self.new_chat(str(name if name is not None else ''), 'agent chat', summary, '')
        system_prompt = self._general_chat_base_system_prompt()
        self.ai_text_doc_id = None
        self.process_message('system', system_prompt)    
        self.update_chat_window()  

    def _agent_base_prompt_name(self) -> str:
        return "_agent"

    def _ai_permissions_label(self) -> str:
        """Return the current AI permissions label used in agent instructions."""

        ai_permissions = self.app.settings.get('ai_permissions', 1)
        return self._ai_permissions_label_for_value(ai_permissions)

    def _ai_permissions_label_for_value(self, ai_permissions: int) -> str:
        """Return the display label for one AI permissions value."""

        labels = {
            0: 'Read-only',
            1: 'Sandboxed',
            2: 'Full access',
        }
        return labels.get(ai_permissions, 'Sandboxed')

    def _log_ai_permissions_env_update(self, old_value: int, new_value: int) -> None:
        """Persist one hidden synthetic chat event for an AI permissions change."""

        if self.current_chat_idx < 0 or self.current_chat_idx >= len(self.chat_list):
            return
        analysis_type = str(self.chat_list[self.current_chat_idx][2])
        if not self._is_agent_chat_type(analysis_type):
            return
        old_label = self._ai_permissions_label_for_value(old_value)
        new_label = self._ai_permissions_label_for_value(new_value)
        if old_label == new_label:
            return
        content = _('System event: AI Permissions changed from "{old}" to "{new}".').format(
            old=old_label,
            new=new_label,
        )
        self.process_message('env_update', content, self.current_chat_idx)

    def _log_agent_env_update(self, content: str, chat_idx=None) -> None:
        """Persist one hidden synthetic environment event for agent chats."""

        if chat_idx is None:
            chat_idx = self.current_chat_idx
        if chat_idx is None or chat_idx < 0 or chat_idx >= len(self.chat_list):
            return
        analysis_type = str(self.chat_list[chat_idx][2])
        if not self._is_agent_chat_type(analysis_type):
            return
        event_text = str(content if content is not None else '').strip()
        if event_text == '':
            return

        curr_chat_id = self.chat_list[chat_idx][0]
        cursor = self.chat_history_conn.cursor()
        cursor.execute(
            "SELECT msg_author, msg_content FROM chat_messages "
            "WHERE chat_id=? AND msg_type='env_update' ORDER BY id DESC LIMIT 1",
            (curr_chat_id,),
        )
        row = cursor.fetchone()
        if row is not None:
            prev_author = '' if row[0] is None else str(row[0])
            prev_content = '' if row[1] is None else str(row[1]).strip()
            if prev_author == 'system_event' and prev_content == event_text:
                return

        self.process_message('env_update', event_text, chat_idx)

    def _log_chat_canceled_env_update(self, chat_idx=None, partial_response: bool = False) -> None:
        """Persist one hidden event stating that the previous assistant turn was canceled."""

        if partial_response:
            content = _(
                'System event: The previous assistant turn was canceled by the user before completion. '
                'If a partial assistant response is present in the conversation, treat it as unfinished unless '
                'the user asks you to continue it.'
            )
        else:
            content = _(
                'System event: The previous assistant turn was canceled by the user before completion and did not finish.'
            )
        self._log_agent_env_update(content, chat_idx)

    def _render_agent_prompt_content(self, content: str) -> str:
        """Replace supported runtime placeholders in the internal agent prompt."""

        if content == "":
            return ""

        template_context = {
            "CURRENT_DATE": datetime.now().date().isoformat(),
            "AI_PERMISSIONS": self._ai_permissions_label(),
            "AI_LANGUAGE": self.app.ai.get_curr_language(),
        }

        def replace_placeholder(match: re.Match) -> str:
            key = match.group(1)
            return template_context.get(key, match.group(0))

        return re.sub(r"\{\{([A-Z0-9_]+)\}\}", replace_placeholder, content)

    def _render_base_agent_prompt_record(self, prompt: AgentPromptRecord) -> str:
        """Render prompt content for inclusion in the rebuilt agent base system prompt."""

        content = str(prompt.content if prompt.content is not None else "").strip()
        if content == "":
            return ""
        if prompt.is_internal:
            return self._render_agent_prompt_content(content)
        return content

    def _collect_agent_base_prompt_context(self) -> Tuple[str, set[str]]:
        """Build the current agent base prompt and track which prompts it already includes."""

        sections: List[str] = []
        included_prompt_keys: set[str] = set()

        base_prompt = self.agent_prompts_catalog.get_internal_prompt(self._agent_base_prompt_name())
        if base_prompt is not None:
            for prompt in self.agent_prompts_catalog.expand_prompt_references([base_prompt], include_internal=True):
                prompt_key = str(prompt.name if prompt.name is not None else "").strip().casefold()
                if prompt_key == "" or prompt_key in included_prompt_keys:
                    continue
                included_prompt_keys.add(prompt_key)
                prompt_text = self._render_base_agent_prompt_record(prompt)
                if prompt_text != "":
                    sections.append(prompt_text)

        project_memo = extract_ai_memo(self.app.get_project_memo())
        if self.app.settings.get('ai_send_project_memo', 'True') == 'True' and len(project_memo) > 0:
            for prompt in self.agent_prompts_catalog.resolve_prompt_references(project_memo):
                prompt_key = str(prompt.name if prompt.name is not None else "").strip().casefold()
                if prompt_key == "" or prompt_key in included_prompt_keys:
                    continue
                included_prompt_keys.add(prompt_key)
                prompt_text = self._render_base_agent_prompt_record(prompt)
                if prompt_text != "":
                    sections.append(prompt_text)

            sections.append(
                '# Information about the current project\n\n'
                'Here is some background information about the research project the team is working on:\n'
                + project_memo
            )

        return '\n\n'.join(section for section in sections if section != ""), included_prompt_keys

    def _general_chat_base_system_prompt(self) -> str:
        """Build the base system prompt for the AI agent chat from _agent.md + project memo."""

        base_prompt, _ = self._collect_agent_base_prompt_context()
        if base_prompt == "":
            return self.app.ai.get_default_system_prompt()
        return base_prompt

    def _mcp_base_system_prompt(self) -> str:
        """Return the stable base system prompt for MCP-backed agent chats."""

        return self._general_chat_base_system_prompt().strip()

    def _build_mcp_combined_system_prompt(self, phase_prompt: str) -> str:
        """Format one phase-specific MCP task contract as a standalone system prompt."""

        phase_text = str(phase_prompt if phase_prompt is not None else "").strip()
        if phase_text == "":
            return ""
        return "# Current task contract\n\n" + phase_text

    def _resolve_turn_agent_prompts(self, user_message: str) -> List[AgentPromptRecord]:
        """Resolve explicit `/name` prompt references from one user message."""

        return self.agent_prompts_catalog.resolve_prompt_references(user_message)

    def _build_turn_prompt_message(self, prompt: AgentPromptRecord) -> str:
        """Format one loaded explicit prompt as persistent supplemental instructions."""

        header = (
            f'The user explicitly activated the prompt "/{prompt.name}" in this conversation. '
            "Treat the following text as supplemental instructions for the rest of this conversation."
        )
        content = str(prompt.content if prompt.content is not None else "").strip()
        if content == "":
            content = _("(empty prompt)")
        return header + "\n\n" + content

    def _persist_explicit_agent_prompts(self, chat_idx: int, user_message: str) -> List[AgentPromptRecord]:
        """Persist newly activated explicit prompts so they remain active in later turns."""

        prompts = self._resolve_turn_agent_prompts(user_message)
        if len(prompts) == 0:
            return []

        base_prompt_keys: set[str] = set()
        if 0 <= chat_idx < len(self.chat_list) and self._is_agent_chat_type(self.chat_list[chat_idx][2]):
            _, base_prompt_keys = self._collect_agent_base_prompt_context()

        latest_prompt_content: Dict[str, str] = {}
        for msg in reversed(self.chat_msg_list):
            if len(msg) < 5 or str(msg[2]) != 'prompt':
                continue
            prompt_name = str(msg[3] if msg[3] is not None else '').strip()
            if prompt_name == "" or prompt_name in latest_prompt_content:
                continue
            latest_prompt_content[prompt_name] = str(msg[4] if msg[4] is not None else '')

        loaded_prompts: List[AgentPromptRecord] = []
        for prompt in prompts:
            prompt_key = str(prompt.name if prompt.name is not None else '').strip().casefold()
            if prompt_key == '' or prompt_key in base_prompt_keys:
                continue
            prompt_message = self._build_turn_prompt_message(prompt)
            if latest_prompt_content.get(prompt.name, None) == prompt_message:
                continue
            self.history_add_message('prompt', prompt.name, prompt_message, chat_idx)
            loaded_prompts.append(prompt)
        return loaded_prompts

    def _persist_agent_prompt_record(self, chat_idx: int, prompt: AgentPromptRecord) -> None:
        """Persist one selected prompt as active chat context for future agent turns."""

        if prompt is None or chat_idx < 0 or chat_idx >= len(self.chat_list):
            return
        prompt_name = str(prompt.name if prompt.name is not None else '').strip()
        if prompt_name == '':
            return
        prompt_message = self._build_turn_prompt_message(prompt)
        latest_prompt_content: Optional[str] = None
        for msg in reversed(self.chat_msg_list):
            if len(msg) < 5 or str(msg[2]) != 'prompt':
                continue
            if str(msg[3] if msg[3] is not None else '').strip() != prompt_name:
                continue
            latest_prompt_content = str(msg[4] if msg[4] is not None else '')
            break
        if latest_prompt_content == prompt_message:
            return
        self.history_add_message('prompt', prompt_name, prompt_message, chat_idx)

    def _selected_source_names(self, file_ids: List[int]) -> List[str]:
        """Return ordered source names for the selected file ids."""

        normalized_ids: List[int] = []
        for raw in list(file_ids or []):
            try:
                file_id = int(raw)
            except Exception:
                continue
            if file_id > 0:
                normalized_ids.append(file_id)
        normalized_ids = list(dict.fromkeys(normalized_ids))
        if len(normalized_ids) == 0:
            return []
        placeholders = ",".join(["?"] * len(normalized_ids))
        db_path = os.path.join(self.app.project_path, 'data.qda')
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT name FROM source WHERE id IN ({placeholders}) ORDER BY CASE id "
                + " ".join(f"WHEN ? THEN {idx}" for idx in range(len(normalized_ids)))
                + " ELSE 999999 END",
                tuple(normalized_ids + normalized_ids),
            )
            rows = cursor.fetchall()
        except Exception:
            return []
        finally:
            conn.close()
        return [str(row[0]).strip() for row in rows if row is not None and row[0] is not None]

    def _topic_exploration_scope_env_update(self, topic_name: str, topic_description: str,
                                            file_ids: List[int], filter_info: Optional[Dict[str, Any]] = None) -> str:
        """Build one durable scope note for topic exploration agent chats."""

        topic_text = str(topic_name if topic_name is not None else '').strip()
        description_text = str(topic_description if topic_description is not None else '').strip()
        normalized_file_ids: List[int] = []
        for raw in list(file_ids or []):
            try:
                file_id = int(raw)
            except Exception:
                continue
            if file_id > 0 and file_id not in normalized_file_ids:
                normalized_file_ids.append(file_id)
        source_names = self._selected_source_names(normalized_file_ids)
        source_count = len(normalized_file_ids)
        filter_info = dict(filter_info) if isinstance(filter_info, dict) else {}
        no_file_filter = bool(filter_info.get("no_file_filter", False))
        no_case_filter = bool(filter_info.get("no_case_filter", False))
        has_attribute_filter = bool(filter_info.get("has_attribute_filter", False))
        case_names = [str(name).strip() for name in list(filter_info.get("selected_case_names", []) or []) if str(name).strip() != ""]
        no_filters = no_file_filter and no_case_filter and not has_attribute_filter

        lines = [
            'System event: This AI agent chat was started in topic exploration mode.',
            f'Focus topic: "{topic_text}".',
        ]
        if description_text != '':
            lines.append('User description: ' + description_text)
        if no_filters:
            lines.append('Selected material: The whole project text corpus is in scope. No file, case, or attribute filters were applied.')
        else:
            material_parts: List[str] = []
            if no_file_filter:
                material_parts.append('No explicit file filter.')
            else:
                material_parts.append('An explicit file filter is active.')
            if len(case_names) > 0:
                material_parts.append('Selected case(s): ' + ", ".join(case_names) + '.')
            elif no_case_filter:
                material_parts.append('No case filter.')
            if has_attribute_filter:
                material_parts.append('An attribute filter is active.')
            if len(source_names) == 0:
                material_parts.append('The resulting material selection is restricted to a subset of the project documents.')
            else:
                preview = ", ".join(source_names[:8])
                if len(source_names) > 8:
                    preview += ', ...'
                material_parts.append(f'Resulting documents ({source_count}): {preview}.')
            lines.append('Selected material: ' + " ".join(material_parts))
        lines.append('If additional project material would be helpful, ask the user for permission before including it.')
        return "\n".join(lines)

    def _topic_exploration_filter_summary(self, file_ids: List[int],
                                          filter_info: Optional[Dict[str, Any]] = None) -> str:
        """Build a compact material/filter summary for the chat header."""

        normalized_file_ids: List[int] = []
        for raw in list(file_ids or []):
            try:
                file_id = int(raw)
            except Exception:
                continue
            if file_id > 0 and file_id not in normalized_file_ids:
                normalized_file_ids.append(file_id)
        source_names = self._selected_source_names(normalized_file_ids)
        source_count = len(normalized_file_ids)
        filter_info = dict(filter_info) if isinstance(filter_info, dict) else {}
        no_file_filter = bool(filter_info.get("no_file_filter", False))
        no_case_filter = bool(filter_info.get("no_case_filter", False))
        has_attribute_filter = bool(filter_info.get("has_attribute_filter", False))
        case_names = [str(name).strip() for name in list(filter_info.get("selected_case_names", []) or []) if str(name).strip() != ""]

        if no_file_filter and no_case_filter and not has_attribute_filter:
            return _('Whole project corpus (no file, case, or attribute filters).')

        parts: List[str] = []
        if not no_file_filter:
            parts.append(_('explicit file filter'))
        if len(case_names) > 0:
            parts.append(_('case(s): {}').format(", ".join(case_names)))
        elif not no_case_filter:
            parts.append(_('case filter'))
        if has_attribute_filter:
            parts.append(_('attribute filter'))

        details = ", ".join(parts)
        if details == "":
            details = _('restricted material selection')

        if len(source_names) == 0:
            return _('{}; resulting document subset.').format(details[:1].upper() + details[1:])

        preview = ", ".join(source_names[:8])
        if len(source_names) > 8:
            preview += ', ...'
        return _('{}; documents ({}): {}').format(
            details[:1].upper() + details[1:],
            source_count,
            preview,
        )

    def _topic_exploration_bootstrap_contract(self, topic_name: str, topic_description: str,
                                              prompt: AgentPromptRecord) -> str:
        """Build the task contract for the first topic-exploration turn before normal agent finalization."""

        topic_text = str(topic_name if topic_name is not None else '').strip()
        description_text = str(topic_description if topic_description is not None else '').strip()
        prompt_name = str(prompt.name if prompt is not None and prompt.name is not None else '').strip()
        if description_text == '':
            description_text = _('(no description provided)')
        return (
            "Your task: "
            f'Work on a topic exploration request centered on "{topic_text}". '
            f'User description: {description_text}\n'
            f'The selected exploration prompt "/{prompt_name}" is active for this chat and should guide your analysis.\n'
            'The semantic search results for the selected material are already available in this conversation. '
            'Treat these retrieved results as the primary focus of the task. '
            'Do not make empirical claims without support from retrieved evidence. If support is uncertain, state the uncertainty clearly.'
        )

    def _topic_exploration_vector_search_uri(self, topic_name: str, topic_description: str, file_ids: List[int]) -> str:
        """Build the MCP vector-search URI used to bootstrap one topic exploration chat."""

        query_variants = self.app.ai.generate_code_descriptions(topic_name, topic_description)
        normalized_queries: List[str] = []
        seen_queries: set[str] = set()
        for candidate in list(query_variants or []):
            text = str(candidate if candidate is not None else '').strip()
            if text == '':
                continue
            key = text.casefold()
            if key in seen_queries:
                continue
            seen_queries.add(key)
            normalized_queries.append(text)
        if len(normalized_queries) == 0:
            fallback_query = str(topic_name if topic_name is not None else '').strip()
            if fallback_query != '':
                normalized_queries.append(fallback_query)

        params: List[Tuple[str, str]] = []
        for query_text in normalized_queries:
            params.append(("q", query_text))
        for raw_file_id in list(file_ids or []):
            try:
                file_id = int(raw_file_id)
            except Exception:
                continue
            if file_id > 0:
                params.append(("file_ids", str(file_id)))
        query_string = urlencode(params, doseq=True)
        if query_string == '':
            return "qualcoder://vector/search"
        return "qualcoder://vector/search?" + query_string

    def _start_mcp_agent_worker(self, messages: List[Any], chat_idx: int, worker_func,
                                *worker_args) -> None:
        """Start one MCP-backed agent worker with the standard callback wiring."""

        self.current_streaming_chat_idx = chat_idx
        self._capture_chat_ai_profile_snapshot(chat_idx)
        self.app.ai.start_query(
            worker_func,
            self.ai_mcp_message_callback,
            messages,
            chat_idx,
            *worker_args,
            progress_callback=self.ai_mcp_progress_callback,
            model_kind='large',
            scope_type='chat',
            scope_id=chat_idx,
            cancel_result={
                "chat_idx": chat_idx,
                "stream_messages": [],
                "tool_messages": [],
                "canceled": True,
                "direct_ai_message": "",
            },
        )

    def _mcp_topic_exploration_worker(self, messages: List[Any], chat_idx: int,
                                      bootstrap_spec: Dict[str, Any], signals=None) -> Dict[str, Any]:
        """Run the first topic exploration turn on top of the normal MCP agent flow."""

        result: Dict[str, Any] = {
            "chat_idx": chat_idx,
            "stream_messages": [],
            "tool_messages": [],
            "canceled": False,
            "direct_ai_message": "",
        }
        allowed_methods = {
            "initialize",
            "resources/list",
            "resources/templates/list",
            "resources/read",
            "tools/list",
            "tools/call",
        }
        spec = dict(bootstrap_spec) if isinstance(bootstrap_spec, dict) else {}
        topic_name = str(spec.get("topic_name", "")).strip()
        topic_description = str(spec.get("topic_description", "")).strip()
        file_ids = list(spec.get("file_ids", []) or [])
        prompt_name = str(spec.get("prompt_name", "")).strip()

        prompt_record = self.agent_prompts_catalog.find_prompt_variant(
            prompt_name,
            str(spec.get("prompt_scope", "")).strip(),
            prompt_type="topic_exploration",
            apply_init=False,
        )
        if prompt_record is None:
            raise ValueError(_("The selected topic exploration prompt could not be loaded."))

        history_messages: List[Any] = list(messages)
        agent_messages: List[Any] = [msg for msg in history_messages if not isinstance(msg, SystemMessage)]
        mcp_base_system_prompt = self._mcp_base_system_prompt()
        ai_change_set_id = self._begin_ai_change_set(history_messages, chat_idx)
        final_hint = ""
        tool_messages: List[Dict[str, str]] = []
        tool_messages_streamed = signals is not None and getattr(signals, "progress", None) is not None
        bootstrap_calls: List[Tuple[str, Dict[str, Any]]] = [
            ("initialize", {}),
            ("resources/list", {}),
            ("resources/templates/list", {}),
            ("resources/read", {"uri": self._topic_exploration_vector_search_uri(topic_name, topic_description, file_ids)}),
        ]
        reflection_json_schema = self._mcp_reflection_json_schema()
        max_calls_per_round = 8
        max_reflection_rounds = 4
        max_total_tool_calls = 20 + len(bootstrap_calls)
        max_queued_calls = 100
        total_tool_calls = 0
        stop_reason = ""
        latest_plan_summary = _("Prepared the initial topic exploration evidence.")
        latest_reflection_summary = ""
        pending_user_decision = None
        deferred_calls_for_next_round: List[Dict[str, Any]] = []

        def _prepare_mcp_request(method_name: str, raw_params: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
            request_params = dict(raw_params) if isinstance(raw_params, dict) else {}
            display_params = dict(request_params)
            if method_name == "tools/call" and ai_change_set_id != "":
                request_params["_ai_change_set_id"] = ai_change_set_id
            return request_params, display_params

        def append_tool_exchange(method_name: str, method_params: Dict[str, Any], rpc_response: Dict[str, Any]):
            call_content = json.dumps(
                {"action": "mcp_call", "method": method_name, "params": method_params},
                ensure_ascii=False,
            )
            result_content = self._compact_mcp_result_content(method_name, method_params, rpc_response)
            agent_messages.append(AIMessage(content=call_content))
            agent_messages.append(HumanMessage(content=result_content))
            if tool_messages_streamed:
                signals.progress.emit(json.dumps({
                    "chat_idx": chat_idx,
                    "msg_type": "tool_call",
                    "msg_author": "ai_agent",
                    "msg_content": call_content,
                }, ensure_ascii=False))
                signals.progress.emit(json.dumps({
                    "chat_idx": chat_idx,
                    "msg_type": "tool_result",
                    "msg_author": "mcp_server",
                    "msg_content": result_content,
                }, ensure_ascii=False))
            else:
                tool_messages.append({"msg_type": "tool_call", "msg_author": "ai_agent", "msg_content": call_content})
                tool_messages.append({"msg_type": "tool_result", "msg_author": "mcp_server", "msg_content": result_content})

        def append_single_instruct_log(phase: str, role: str, content: str):
            payload = json.dumps(
                {
                    "phase": str(phase if phase is not None else "").strip() or "topic_exploration",
                    "role": str(role if role is not None else "").strip() or "user",
                    "content": content,
                },
                ensure_ascii=False,
            )
            if tool_messages_streamed:
                signals.progress.emit(json.dumps({
                    "chat_idx": chat_idx,
                    "msg_type": "single_instruct",
                    "msg_author": "ai_agent",
                    "msg_content": payload,
                }, ensure_ascii=False))
            else:
                tool_messages.append({"msg_type": "single_instruct", "msg_author": "ai_agent", "msg_content": payload})

        try:
            self._emit_mcp_status_text(signals, chat_idx, _('Preparing semantic search...'), status_kind="planning")
            for method, params in bootstrap_calls:
                if self.app.ai.is_current_run_canceled():
                    result["canceled"] = True
                    return result
                request_params, display_params = _prepare_mcp_request(method, params)
                status_text = self.ai_mcp_server.describe_status_event(method, request_params)
                self._emit_mcp_status(signals, chat_idx, status_text)
                _request, response = self._run_mcp_request(method, request_params)
                total_tool_calls += 1
                append_tool_exchange(method, display_params, response)

            reflection_system_prompt = self._build_mcp_combined_system_prompt(
                self._topic_exploration_bootstrap_contract(topic_name, topic_description, prompt_record)
                + "\n\n"
                + self._mcp_reflection_system_prompt()
            )
            reflection_prompt = (
                "Reflect on whether the currently retrieved evidence is sufficient for this topic exploration and return JSON now. "
                "If not, propose only the minimal additional MCP calls needed."
            )

            def build_phase_request_message(phase_contract: str, trailing_instruction: str) -> HumanMessage:
                parts: List[str] = []
                phase_text = str(phase_contract if phase_contract is not None else "").strip()
                trailing_text = str(trailing_instruction if trailing_instruction is not None else "").strip()
                if phase_text != "":
                    parts.append(phase_text)
                if trailing_text != "":
                    parts.append(trailing_text)
                return HumanMessage(content="\n\n".join(parts).strip())

            def build_phase_messages(phase_contract: str, trailing_instruction: str) -> List[Any]:
                phase_messages: List[Any] = []
                if mcp_base_system_prompt != "":
                    phase_messages.append(SystemMessage(content=mcp_base_system_prompt))
                phase_messages.extend(agent_messages)
                phase_messages.append(build_phase_request_message(phase_contract, trailing_instruction))
                return phase_messages

            for reflection_round in range(max_reflection_rounds):
                if self.app.ai.is_current_run_canceled():
                    result["canceled"] = True
                    return result

                current_reflection_prompt = reflection_prompt
                if len(deferred_calls_for_next_round) > 0:
                    current_reflection_prompt += (
                        "\nDeferred calls from the previous execution queue "
                        f"(not yet executed because the round limit is {max_calls_per_round}):\n"
                        + json.dumps(deferred_calls_for_next_round, ensure_ascii=False)
                    )
                append_single_instruct_log(
                    "reflection",
                    "user",
                    build_phase_request_message(reflection_system_prompt, current_reflection_prompt).content,
                )
                reflection_messages = build_phase_messages(reflection_system_prompt, current_reflection_prompt)
                try:
                    reflection_data = self._invoke_json_llm_with_step_timeout(
                        reflection_messages,
                        schema_name='mcp_reflection_control',
                        response_schema=reflection_json_schema,
                        context='mcp_json_reflection',
                        step_name=_("Internal reflection"),
                        status_kind="reflection",
                        signals=signals,
                        chat_idx=chat_idx,
                    )
                except TimeoutError:
                    latest_reflection_summary = _('Internal reflection timed out; proceeding with the collected evidence.')
                    self._emit_mcp_status_text(
                        signals,
                        chat_idx,
                        latest_reflection_summary,
                        status_kind="reflection",
                    )
                    stop_reason = "reflection_timeout"
                    break

                reflection_summary = str(reflection_data.get("reflection_summary", "")).strip()
                if reflection_summary != "":
                    latest_reflection_summary = reflection_summary
                reflection_brief = str(reflection_data.get("answer_brief", "")).strip()
                if reflection_brief != "":
                    final_hint = reflection_brief
                enough_information = self._json_bool(reflection_data.get("enough_information", False), False)
                reflection_next_step_note = str(reflection_data.get("next_step_note", "")).strip()
                continue_deferred_calls = self._json_bool(
                    reflection_data.get("continue_deferred_calls", False),
                    False
                )
                revised_calls = self._normalize_mcp_calls(
                    reflection_data.get("revised_calls", []), allowed_methods, max_queued_calls
                )
                proposed_next_calls = self._normalize_mcp_calls(
                    reflection_data.get("proposed_next_calls", []), allowed_methods, max_calls_per_round
                )
                short_reflection_note = self._short_reflection_next_step_note(
                    reflection_summary,
                    reflection_next_step_note,
                )
                if short_reflection_note != "":
                    self._emit_mcp_status_text(signals, chat_idx, short_reflection_note, status_kind="reflection")
                user_decision_required = self._json_bool(reflection_data.get("user_decision_required", False), False)
                decision_question = self._normalize_progress_note(reflection_data.get("decision_question", ""), max_length=600)
                decision_context = self._normalize_progress_note(reflection_data.get("decision_context", ""), max_length=600)
                if user_decision_required and decision_question == "":
                    decision_question = short_reflection_note
                if user_decision_required and decision_question != "":
                    pending_user_decision = {
                        "phase": "reflection",
                        "question": decision_question,
                        "context": decision_context,
                        "proposed_next_calls": proposed_next_calls,
                    }
                    result["direct_ai_message"] = decision_question
                    stop_reason = "awaiting_user_decision"
                    break
                if enough_information:
                    stop_reason = "enough_information"
                    break

                current_round_calls, deferred_calls = self._split_mcp_call_queue(revised_calls, max_calls_per_round)
                if continue_deferred_calls and len(deferred_calls) > 0:
                    current_round_calls = self._merge_mcp_call_lists(current_round_calls, deferred_calls, max_calls_per_round)
                if len(current_round_calls) == 0:
                    if continue_deferred_calls and len(deferred_calls_for_next_round) > 0:
                        current_round_calls, deferred_calls = self._split_mcp_call_queue(
                            deferred_calls_for_next_round,
                            max_calls_per_round,
                        )
                    else:
                        deferred_calls = []
                deferred_calls_for_next_round = list(deferred_calls)
                if len(current_round_calls) == 0:
                    stop_reason = "no_more_valid_calls"
                    break

                for call in current_round_calls:
                    if self.app.ai.is_current_run_canceled():
                        result["canceled"] = True
                        return result
                    if total_tool_calls >= max_total_tool_calls:
                        stop_reason = "max_total_tool_calls_reached"
                        break
                    method = str(call.get("method", "")).strip()
                    params = call.get("params", {})
                    if not isinstance(params, dict):
                        params = {}
                    if method not in allowed_methods:
                        response = {
                            "jsonrpc": "2.0",
                            "id": self.ai_mcp_server.new_request_id(),
                            "error": {"code": -32601, "message": "Method not found", "data": method},
                        }
                        append_tool_exchange(method, params, response)
                        continue
                    request_params, display_params = _prepare_mcp_request(method, params)
                    status_text = self.ai_mcp_server.describe_status_event(method, request_params)
                    self._emit_mcp_status(signals, chat_idx, status_text)
                    _request, response = self._run_mcp_request(method, request_params)
                    total_tool_calls += 1
                    append_tool_exchange(method, display_params, response)
                if stop_reason == "max_total_tool_calls_reached":
                    break
            else:
                if stop_reason == "":
                    stop_reason = "max_reflection_rounds_reached"

            if pending_user_decision is not None:
                agent_state_snapshot = {
                    "type": "mcp_agent_state",
                    "latest_plan_summary": self._normalize_progress_note(latest_plan_summary, max_length=600),
                    "latest_reflection_summary": self._normalize_progress_note(latest_reflection_summary, max_length=600),
                    "final_hint": self._normalize_progress_note(final_hint, max_length=600),
                    "stop_reason": stop_reason,
                    "pending_calls": [],
                    "pending_user_decision": pending_user_decision,
                }
                agent_state_content = json.dumps(agent_state_snapshot, ensure_ascii=False)
                if tool_messages_streamed:
                    progress_payload = {
                        "chat_idx": chat_idx,
                        "msg_type": "agent_state",
                        "msg_author": "ai_agent",
                        "msg_content": agent_state_content,
                    }
                    signals.progress.emit(json.dumps(progress_payload, ensure_ascii=False))
                else:
                    tool_messages.append(
                        {
                            "msg_type": "agent_state",
                            "msg_author": "ai_agent",
                            "msg_content": agent_state_content,
                        }
                    )
                result["tool_messages"] = tool_messages
                result["stream_messages"] = []
                return result

            self._emit_mcp_status(signals, chat_idx, _('Preparing response...'))
            final_prompt = (
                "Now provide the final answer to the user in normal prose. "
                "Focus on outcomes of this turn and communicate them clearly. "
                "Do not mention internal MCP stage constraints. "
                "When referring to empirical text evidence, cite it as {REF: \"exact quote\"}. "
                "Remember: REF is invisible markup; if you want a quote to be visible, include the quoted text in normal prose and add REF in addition."
            )
            if final_hint != '':
                final_prompt += '\nHere is a draft idea from your internal reflection:\n' + final_hint
            if stop_reason not in ("", "enough_information"):
                final_prompt += (
                    "\nIf the available project evidence is incomplete, clearly state uncertainty and "
                    "mention what additional project material would help."
                )

            agent_state_snapshot = {
                "type": "mcp_agent_state",
                "latest_plan_summary": self._normalize_progress_note(latest_plan_summary, max_length=600),
                "latest_reflection_summary": self._normalize_progress_note(latest_reflection_summary, max_length=600),
                "final_hint": self._normalize_progress_note(final_hint, max_length=600),
                "stop_reason": stop_reason,
                "pending_calls": [],
                "pending_user_decision": None,
            }
            agent_state_content = json.dumps(agent_state_snapshot, ensure_ascii=False)
            if tool_messages_streamed:
                progress_payload = {
                    "chat_idx": chat_idx,
                    "msg_type": "agent_state",
                    "msg_author": "ai_agent",
                    "msg_content": agent_state_content,
                }
                signals.progress.emit(json.dumps(progress_payload, ensure_ascii=False))
            else:
                tool_messages.append(
                    {
                        "msg_type": "agent_state",
                        "msg_author": "ai_agent",
                        "msg_content": agent_state_content,
                    }
                )

            final_system_prompt = self._build_mcp_combined_system_prompt(self._mcp_final_answer_system_prompt())
            final_stream_messages = build_phase_messages(final_system_prompt, final_prompt)
            result["stream_messages"] = final_stream_messages
            result["tool_messages"] = tool_messages
            return result
        except Exception as err:
            result["error"] = _('Error during MCP-based topic exploration bootstrap: ') + str(err)
            return result
        finally:
            if ai_change_set_id != "":
                self._discard_empty_ai_change_set(ai_change_set_id)

    def _selected_code_names(self, code_ids: List[int]) -> List[str]:
        """Return ordered code names for the selected code ids."""

        normalized_ids: List[int] = []
        for raw in list(code_ids or []):
            try:
                code_id = int(raw)
            except Exception:
                continue
            if code_id > 0 and code_id not in normalized_ids:
                normalized_ids.append(code_id)
        if len(normalized_ids) == 0:
            return []
        placeholders = ",".join(["?"] * len(normalized_ids))
        db_path = os.path.join(self.app.project_path, 'data.qda')
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT name FROM code_name WHERE cid IN ({placeholders}) ORDER BY CASE cid "
                + " ".join(f"WHEN ? THEN {idx}" for idx in range(len(normalized_ids)))
                + " ELSE 999999 END",
                tuple(normalized_ids + normalized_ids),
            )
            rows = cursor.fetchall()
        except Exception:
            return []
        finally:
            conn.close()
        return [str(row[0]).strip() for row in rows if row is not None and row[0] is not None]

    def _count_code_segments_for_selection(self, code_ids: List[int], file_ids: List[int], coder_names: List[str]) -> int:
        """Count matching coded text segments for a code analysis selection."""

        normalized_code_ids: List[int] = []
        for raw in list(code_ids or []):
            try:
                code_id = int(raw)
            except Exception:
                continue
            if code_id > 0 and code_id not in normalized_code_ids:
                normalized_code_ids.append(code_id)
        if len(normalized_code_ids) == 0:
            return 0

        normalized_file_ids: List[int] = []
        for raw in list(file_ids or []):
            try:
                file_id = int(raw)
            except Exception:
                continue
            if file_id > 0 and file_id not in normalized_file_ids:
                normalized_file_ids.append(file_id)

        normalized_coders: List[str] = []
        seen_coders: set[str] = set()
        for raw in list(coder_names or []):
            coder = str(raw if raw is not None else '').strip()
            if coder == '':
                continue
            key = coder.casefold()
            if key in seen_coders:
                continue
            seen_coders.add(key)
            normalized_coders.append(coder)

        table_name = "code_text" if len(normalized_coders) > 0 else "code_text_visible"
        if table_name == "code_text_visible" and not self.ai_mcp_server._view_exists("code_text_visible"):
            return 0

        where_parts = [f"cid IN ({','.join(['?'] * len(normalized_code_ids))})"]
        params: List[Any] = list(normalized_code_ids)
        if len(normalized_file_ids) > 0:
            where_parts.append(f"fid IN ({','.join(['?'] * len(normalized_file_ids))})")
            params.extend(normalized_file_ids)
        if len(normalized_coders) > 0:
            where_parts.append(f"owner IN ({','.join(['?'] * len(normalized_coders))})")
            params.extend(normalized_coders)

        db_path = os.path.join(self.app.project_path, 'data.qda')
        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT COUNT(*) FROM {table_name} WHERE " + " AND ".join(where_parts),
                tuple(params),
            )
            row = cursor.fetchone()
            if row is None or row[0] is None:
                return 0
            return int(row[0])
        finally:
            conn.close()

    def _distribute_integer_budget(self, total_budget: int, item_count: int) -> List[int]:
        """Distribute a positive integer budget across items, preserving at least one per item."""

        if item_count <= 0:
            return []
        if total_budget <= 0:
            return [1] * item_count
        if item_count >= total_budget:
            return [1] * item_count
        base = total_budget // item_count
        remainder = total_budget % item_count
        budgets = [base] * item_count
        for idx in range(remainder):
            budgets[idx] += 1
        return [max(1, value) for value in budgets]

    def _code_analysis_segments_uri(self, cid: int, file_ids: List[int], coder_names: List[str],
                                    max_segments: int, max_chars: int) -> str:
        """Build the MCP coded-segments URI used to bootstrap one code analysis chat."""

        params: List[Tuple[str, str]] = [
            ("strategy", "diverse_by_document"),
            ("max_segments", str(max(1, int(max_segments)))),
            ("max_chars", str(max(1, int(max_chars)))),
        ]
        for raw_file_id in list(file_ids or []):
            try:
                file_id = int(raw_file_id)
            except Exception:
                continue
            if file_id > 0:
                params.append(("file_ids", str(file_id)))
        seen_coders: set[str] = set()
        for raw in list(coder_names or []):
            coder = str(raw if raw is not None else '').strip()
            if coder == '':
                continue
            key = coder.casefold()
            if key in seen_coders:
                continue
            seen_coders.add(key)
            params.append(("owner", coder))
        return f"qualcoder://codes/segments/{int(cid)}?" + urlencode(params, doseq=True)

    def _code_analysis_filter_summary(self, file_ids: List[int], coder_names: List[str],
                                      filter_info: Optional[Dict[str, Any]] = None) -> str:
        """Build a compact coder/material summary for the code analysis chat header."""

        material_summary = self._topic_exploration_filter_summary(file_ids, filter_info)
        normalized_coders: List[str] = []
        seen_coders: set[str] = set()
        for raw in list(coder_names or []):
            coder = str(raw if raw is not None else '').strip()
            if coder == '':
                continue
            key = coder.casefold()
            if key in seen_coders:
                continue
            seen_coders.add(key)
            normalized_coders.append(coder)
        if len(normalized_coders) == 0:
            return _('Visible coders; ') + material_summary
        return _('Coders: {}; ').format(", ".join(normalized_coders)) + material_summary

    def _code_analysis_scope_env_update(self, code_name: str, code_memo: str, code_ids: List[int],
                                        coder_names: List[str], file_ids: List[int],
                                        filter_info: Optional[Dict[str, Any]] = None) -> str:
        """Build one durable scope note for code analysis agent chats."""

        focus_name = str(code_name if code_name is not None else '').strip()
        memo_text = str(code_memo if code_memo is not None else '').strip()
        selected_codes = self._selected_code_names(code_ids)
        coder_summary = self._code_analysis_filter_summary(file_ids, coder_names, filter_info)

        lines = [
            'System event: This AI agent chat was started in code analysis mode.',
            f'Focus code or category: "{focus_name}".',
        ]
        if memo_text != '':
            lines.append('Code memo: ' + memo_text)
        if len(selected_codes) > 1:
            preview = ", ".join(selected_codes[:8])
            if len(selected_codes) > 8:
                preview += ', ...'
            lines.append(f'Selected subcodes ({len(selected_codes)}): {preview}')
        elif len(selected_codes) == 1:
            lines.append('Selected code: ' + selected_codes[0])
        lines.append('Selected coding scope: ' + coder_summary)
        lines.append('Base the analysis primarily on the selected coded segments.')
        lines.append('If narrowly targeted additional project material would directly help to fulfill the active analysis prompt, you may retrieve and use it.')
        lines.append('Keep any such expansion tightly focused, such as immediate same-document context, a small number of comparison passages, or directly relevant additional evidence for the selected codes.')
        lines.append('If a broader scope expansion would be helpful, ask the user for permission first.')
        return "\n".join(lines)

    def _code_analysis_bootstrap_contract(self, code_name: str, code_memo: str, prompt: AgentPromptRecord,
                                          code_ids: List[int]) -> str:
        """Build the task contract for the first code-analysis turn before normal agent finalization."""

        focus_name = str(code_name if code_name is not None else '').strip()
        memo_text = str(code_memo if code_memo is not None else '').strip()
        prompt_name = str(prompt.name if prompt is not None and prompt.name is not None else '').strip()
        selected_codes = self._selected_code_names(code_ids)
        if memo_text == '':
            memo_text = _('(no memo provided)')
        code_scope_text = _('one selected code')
        if len(selected_codes) > 1:
            code_scope_text = _('{} selected codes').format(len(selected_codes))
        return (
            "Your task: "
            f'Work on a code analysis request centered on "{focus_name}". '
            f'Code memo: {memo_text}\n'
            f'The selected analysis prompt "/{prompt_name}" is active for this chat and should guide your analysis.\n'
            f'The coded segments for {code_scope_text} are already available in this conversation as MCP resource results. '
            'Treat these coded segments as the primary focus of the task. '
            'Do not make empirical claims without support from retrieved evidence. If support is uncertain, state the uncertainty clearly.'
        )

    def _mcp_code_analysis_worker(self, messages: List[Any], chat_idx: int,
                                  bootstrap_spec: Dict[str, Any], signals=None) -> Dict[str, Any]:
        """Run the first code analysis turn on top of the normal MCP agent flow."""

        result: Dict[str, Any] = {
            "chat_idx": chat_idx,
            "stream_messages": [],
            "tool_messages": [],
            "canceled": False,
            "direct_ai_message": "",
            "direct_info_message": "",
        }
        allowed_methods = {
            "initialize",
            "resources/list",
            "resources/templates/list",
            "resources/read",
            "tools/list",
            "tools/call",
        }
        spec = dict(bootstrap_spec) if isinstance(bootstrap_spec, dict) else {}
        focus_name = str(spec.get("code_name", "")).strip()
        code_memo = str(spec.get("code_memo", "")).strip()
        file_ids = list(spec.get("file_ids", []) or [])
        code_ids = list(spec.get("code_ids", []) or [])
        coder_names = list(spec.get("coder_names", []) or [])
        prompt_name = str(spec.get("prompt_name", "")).strip()

        prompt_record = self.agent_prompts_catalog.find_prompt_variant(
            prompt_name,
            str(spec.get("prompt_scope", "")).strip(),
            prompt_type="code_analysis",
            apply_init=False,
        )
        if prompt_record is None:
            raise ValueError(_("The selected code analysis prompt could not be loaded."))

        normalized_code_ids: List[int] = []
        for raw in code_ids:
            try:
                code_id = int(raw)
            except Exception:
                continue
            if code_id > 0 and code_id not in normalized_code_ids:
                normalized_code_ids.append(code_id)
        if len(normalized_code_ids) == 0:
            raise ValueError(_("No codes are available for this code analysis."))

        history_messages: List[Any] = list(messages)
        agent_messages: List[Any] = [msg for msg in history_messages if not isinstance(msg, SystemMessage)]
        mcp_base_system_prompt = self._mcp_base_system_prompt()
        ai_change_set_id = self._begin_ai_change_set(history_messages, chat_idx)
        final_hint = ""
        tool_messages: List[Dict[str, str]] = []
        tool_messages_streamed = signals is not None and getattr(signals, "progress", None) is not None
        coverage_total_segments = 0
        coverage_loaded_segments = 0
        coverage_hit_max_char_limit = False
        segment_budgets = self._distribute_integer_budget(code_analysis_max_segments_total, len(normalized_code_ids))
        max_chars_total = max(4000, round(0.5 * (self.app.ai.large_llm_context_window * 4)))
        char_budgets = self._distribute_integer_budget(max_chars_total, len(normalized_code_ids))
        bootstrap_calls: List[Tuple[str, Dict[str, Any]]] = [
            ("initialize", {}),
            ("resources/list", {}),
            ("resources/templates/list", {}),
        ]
        for idx, code_id in enumerate(normalized_code_ids):
            bootstrap_calls.append(
                (
                    "resources/read",
                    {
                        "uri": self._code_analysis_segments_uri(
                            code_id,
                            file_ids,
                            coder_names,
                            segment_budgets[idx],
                            char_budgets[idx],
                        )
                    },
                )
            )
        reflection_json_schema = self._mcp_reflection_json_schema()
        max_calls_per_round = 8
        max_reflection_rounds = 4
        max_total_tool_calls = 20 + len(bootstrap_calls)
        max_queued_calls = 100
        total_tool_calls = 0
        stop_reason = ""
        latest_plan_summary = _("Prepared the selected coded segments for analysis.")
        latest_reflection_summary = ""
        pending_user_decision = None
        deferred_calls_for_next_round: List[Dict[str, Any]] = []

        def _prepare_mcp_request(method_name: str, raw_params: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
            request_params = dict(raw_params) if isinstance(raw_params, dict) else {}
            display_params = dict(request_params)
            if method_name == "tools/call" and ai_change_set_id != "":
                request_params["_ai_change_set_id"] = ai_change_set_id
            return request_params, display_params

        def append_tool_exchange(method_name: str, method_params: Dict[str, Any], rpc_response: Dict[str, Any]):
            call_content = json.dumps(
                {"action": "mcp_call", "method": method_name, "params": method_params},
                ensure_ascii=False,
            )
            result_content = self._compact_mcp_result_content(method_name, method_params, rpc_response)
            agent_messages.append(AIMessage(content=call_content))
            agent_messages.append(HumanMessage(content=result_content))
            if tool_messages_streamed:
                signals.progress.emit(json.dumps({
                    "chat_idx": chat_idx,
                    "msg_type": "tool_call",
                    "msg_author": "ai_agent",
                    "msg_content": call_content,
                }, ensure_ascii=False))
                signals.progress.emit(json.dumps({
                    "chat_idx": chat_idx,
                    "msg_type": "tool_result",
                    "msg_author": "mcp_server",
                    "msg_content": result_content,
                }, ensure_ascii=False))
            else:
                tool_messages.append({"msg_type": "tool_call", "msg_author": "ai_agent", "msg_content": call_content})
                tool_messages.append({"msg_type": "tool_result", "msg_author": "mcp_server", "msg_content": result_content})

        def append_single_instruct_log(phase: str, role: str, content: str):
            payload = json.dumps(
                {
                    "phase": str(phase if phase is not None else "").strip() or "code_analysis",
                    "role": str(role if role is not None else "").strip() or "user",
                    "content": content,
                },
                ensure_ascii=False,
            )
            if tool_messages_streamed:
                signals.progress.emit(json.dumps({
                    "chat_idx": chat_idx,
                    "msg_type": "single_instruct",
                    "msg_author": "ai_agent",
                    "msg_content": payload,
                }, ensure_ascii=False))
            else:
                tool_messages.append({"msg_type": "single_instruct", "msg_author": "ai_agent", "msg_content": payload})

        def accumulate_code_segment_coverage(rpc_response: Dict[str, Any]) -> None:
            nonlocal coverage_total_segments, coverage_loaded_segments, coverage_hit_max_char_limit

            if not isinstance(rpc_response, dict):
                return
            result_payload = rpc_response.get("result", None)
            if not isinstance(result_payload, dict):
                return
            contents = result_payload.get("contents", [])
            if not isinstance(contents, list):
                return
            for item in contents:
                if not isinstance(item, dict):
                    continue
                uri = str(item.get("uri", "")).split("?", 1)[0].strip()
                if re.fullmatch(r"qualcoder://codes/segments/\d+", uri) is None:
                    continue
                payload: Optional[Dict[str, Any]] = None
                text_blob = item.get("text", None)
                if isinstance(text_blob, str) and text_blob.strip() != "":
                    try:
                        parsed = json.loads(text_blob)
                    except Exception:
                        parsed = None
                    if isinstance(parsed, dict):
                        payload = parsed
                if payload is None:
                    raw_payload = item.get("payload", None)
                    if isinstance(raw_payload, dict):
                        payload = raw_payload
                if not isinstance(payload, dict):
                    continue
                selection = payload.get("selection", {})
                segments = payload.get("segments", [])
                if isinstance(selection, dict):
                    coverage_total_segments += max(0, int(selection.get("total_segments", 0) or 0))
                    coverage_hit_max_char_limit = (
                        coverage_hit_max_char_limit or bool(selection.get("hit_max_char_limit", False))
                    )
                if isinstance(segments, list):
                    coverage_loaded_segments += len(segments)

        try:
            self._emit_mcp_status_text(signals, chat_idx, _('Preparing coded segments...'), status_kind="planning")
            for method, params in bootstrap_calls:
                if self.app.ai.is_current_run_canceled():
                    result["canceled"] = True
                    return result
                request_params, display_params = _prepare_mcp_request(method, params)
                status_text = self.ai_mcp_server.describe_status_event(method, request_params)
                self._emit_mcp_status(signals, chat_idx, status_text)
                _request, response = self._run_mcp_request(method, request_params)
                total_tool_calls += 1
                append_tool_exchange(method, display_params, response)
                if method == "resources/read":
                    accumulate_code_segment_coverage(response)

            coverage_ratio = 1.0
            if coverage_total_segments > 0:
                coverage_ratio = coverage_loaded_segments / coverage_total_segments
            if coverage_hit_max_char_limit and coverage_ratio < code_analysis_min_segment_coverage:
                result["tool_messages"] = tool_messages
                result["direct_info_message"] = _(
                    'The selected coded material is too large for a meaningful first-pass code analysis in one bootstrap step. '
                    'Only {loaded} of {total} coded segments ({coverage:.1f}%) could be loaded before the character limit was reached. '
                    'Please narrow the scope by code, files, cases, attributes, or coders. '
                    'If you still want to continue, send a follow-up message such as "Analyze anyway".'
                ).format(
                    loaded=coverage_loaded_segments,
                    total=coverage_total_segments,
                    coverage=coverage_ratio * 100.0,
                )
                return result

            reflection_system_prompt = self._build_mcp_combined_system_prompt(
                self._code_analysis_bootstrap_contract(
                    focus_name,
                    code_memo,
                    prompt_record,
                    normalized_code_ids,
                )
                + "\n\n"
                + self._mcp_reflection_system_prompt()
            )
            reflection_prompt = (
                "Reflect on whether the currently retrieved evidence is sufficient for this code analysis and return JSON now. "
                "If not, propose only the minimal additional MCP calls needed."
            )

            def build_phase_request_message(phase_contract: str, trailing_instruction: str) -> HumanMessage:
                parts: List[str] = []
                phase_text = str(phase_contract if phase_contract is not None else "").strip()
                trailing_text = str(trailing_instruction if trailing_instruction is not None else "").strip()
                if phase_text != "":
                    parts.append(phase_text)
                if trailing_text != "":
                    parts.append(trailing_text)
                return HumanMessage(content="\n\n".join(parts).strip())

            def build_phase_messages(phase_contract: str, trailing_instruction: str) -> List[Any]:
                phase_messages: List[Any] = []
                if mcp_base_system_prompt != "":
                    phase_messages.append(SystemMessage(content=mcp_base_system_prompt))
                phase_messages.extend(agent_messages)
                phase_messages.append(build_phase_request_message(phase_contract, trailing_instruction))
                return phase_messages

            for reflection_round in range(max_reflection_rounds):
                if self.app.ai.is_current_run_canceled():
                    result["canceled"] = True
                    return result

                current_reflection_prompt = reflection_prompt
                if len(deferred_calls_for_next_round) > 0:
                    current_reflection_prompt += (
                        "\nDeferred calls from the previous execution queue "
                        f"(not yet executed because the round limit is {max_calls_per_round}):\n"
                        + json.dumps(deferred_calls_for_next_round, ensure_ascii=False)
                    )
                append_single_instruct_log(
                    "reflection",
                    "user",
                    build_phase_request_message(reflection_system_prompt, current_reflection_prompt).content,
                )
                reflection_messages = build_phase_messages(reflection_system_prompt, current_reflection_prompt)
                try:
                    reflection_data = self._invoke_json_llm_with_step_timeout(
                        reflection_messages,
                        schema_name='mcp_reflection_control',
                        response_schema=reflection_json_schema,
                        context='mcp_json_reflection',
                        step_name=_("Internal reflection"),
                        status_kind="reflection",
                        signals=signals,
                        chat_idx=chat_idx,
                    )
                except TimeoutError:
                    latest_reflection_summary = _('Internal reflection timed out; proceeding with the collected evidence.')
                    self._emit_mcp_status_text(
                        signals,
                        chat_idx,
                        latest_reflection_summary,
                        status_kind="reflection",
                    )
                    stop_reason = "reflection_timeout"
                    break

                reflection_summary = str(reflection_data.get("reflection_summary", "")).strip()
                if reflection_summary != "":
                    latest_reflection_summary = reflection_summary
                reflection_brief = str(reflection_data.get("answer_brief", "")).strip()
                if reflection_brief != "":
                    final_hint = reflection_brief
                enough_information = self._json_bool(reflection_data.get("enough_information", False), False)
                reflection_next_step_note = str(reflection_data.get("next_step_note", "")).strip()
                continue_deferred_calls = self._json_bool(
                    reflection_data.get("continue_deferred_calls", False),
                    False
                )
                revised_calls = self._normalize_mcp_calls(
                    reflection_data.get("revised_calls", []), allowed_methods, max_queued_calls
                )
                proposed_next_calls = self._normalize_mcp_calls(
                    reflection_data.get("proposed_next_calls", []), allowed_methods, max_calls_per_round
                )
                short_reflection_note = self._short_reflection_next_step_note(
                    reflection_summary,
                    reflection_next_step_note,
                )
                if short_reflection_note != "":
                    self._emit_mcp_status_text(signals, chat_idx, short_reflection_note, status_kind="reflection")
                user_decision_required = self._json_bool(reflection_data.get("user_decision_required", False), False)
                decision_question = self._normalize_progress_note(reflection_data.get("decision_question", ""), max_length=600)
                decision_context = self._normalize_progress_note(reflection_data.get("decision_context", ""), max_length=600)
                if user_decision_required and decision_question == "":
                    decision_question = short_reflection_note
                if user_decision_required and decision_question != "":
                    pending_user_decision = {
                        "phase": "reflection",
                        "question": decision_question,
                        "context": decision_context,
                        "proposed_next_calls": proposed_next_calls,
                    }
                    result["direct_ai_message"] = decision_question
                    stop_reason = "awaiting_user_decision"
                    break
                if enough_information:
                    stop_reason = "enough_information"
                    break

                current_round_calls, deferred_calls = self._split_mcp_call_queue(revised_calls, max_calls_per_round)
                if continue_deferred_calls and len(deferred_calls) > 0:
                    current_round_calls = self._merge_mcp_call_lists(current_round_calls, deferred_calls, max_calls_per_round)
                if len(current_round_calls) == 0:
                    if continue_deferred_calls and len(deferred_calls_for_next_round) > 0:
                        current_round_calls, deferred_calls = self._split_mcp_call_queue(
                            deferred_calls_for_next_round,
                            max_calls_per_round,
                        )
                    else:
                        deferred_calls = []
                deferred_calls_for_next_round = list(deferred_calls)
                if len(current_round_calls) == 0:
                    stop_reason = "no_more_valid_calls"
                    break

                for call in current_round_calls:
                    if self.app.ai.is_current_run_canceled():
                        result["canceled"] = True
                        return result
                    if total_tool_calls >= max_total_tool_calls:
                        stop_reason = "max_total_tool_calls_reached"
                        break
                    method = str(call.get("method", "")).strip()
                    params = call.get("params", {})
                    if not isinstance(params, dict):
                        params = {}
                    if method not in allowed_methods:
                        response = {
                            "jsonrpc": "2.0",
                            "id": self.ai_mcp_server.new_request_id(),
                            "error": {"code": -32601, "message": "Method not found", "data": method},
                        }
                        append_tool_exchange(method, params, response)
                        continue
                    request_params, display_params = _prepare_mcp_request(method, params)
                    status_text = self.ai_mcp_server.describe_status_event(method, request_params)
                    self._emit_mcp_status(signals, chat_idx, status_text)
                    _request, response = self._run_mcp_request(method, request_params)
                    total_tool_calls += 1
                    append_tool_exchange(method, display_params, response)
                if stop_reason == "max_total_tool_calls_reached":
                    break
            else:
                if stop_reason == "":
                    stop_reason = "max_reflection_rounds_reached"

            if pending_user_decision is not None:
                agent_state_snapshot = {
                    "type": "mcp_agent_state",
                    "latest_plan_summary": self._normalize_progress_note(latest_plan_summary, max_length=600),
                    "latest_reflection_summary": self._normalize_progress_note(latest_reflection_summary, max_length=600),
                    "final_hint": self._normalize_progress_note(final_hint, max_length=600),
                    "stop_reason": stop_reason,
                    "pending_calls": [],
                    "pending_user_decision": pending_user_decision,
                }
                agent_state_content = json.dumps(agent_state_snapshot, ensure_ascii=False)
                if tool_messages_streamed:
                    progress_payload = {
                        "chat_idx": chat_idx,
                        "msg_type": "agent_state",
                        "msg_author": "ai_agent",
                        "msg_content": agent_state_content,
                    }
                    signals.progress.emit(json.dumps(progress_payload, ensure_ascii=False))
                else:
                    tool_messages.append(
                        {
                            "msg_type": "agent_state",
                            "msg_author": "ai_agent",
                            "msg_content": agent_state_content,
                        }
                    )
                result["tool_messages"] = tool_messages
                result["stream_messages"] = []
                return result

            self._emit_mcp_status(signals, chat_idx, _('Preparing response...'))
            final_prompt = (
                "Now provide the final answer to the user in normal prose. "
                "Focus on outcomes of this turn and communicate them clearly. "
                "Do not mention internal MCP stage constraints. "
                "When referring to empirical text evidence, cite it as {REF: \"exact quote\"}. "
                "Remember: REF is invisible markup; if you want a quote to be visible, include the quoted text in normal prose and add REF in addition."
            )
            if final_hint != '':
                final_prompt += '\nHere is a draft idea from your internal reflection:\n' + final_hint
            if stop_reason not in ("", "enough_information"):
                final_prompt += (
                    "\nIf the available project evidence is incomplete, clearly state uncertainty and "
                    "mention what additional project material would help."
                )

            agent_state_snapshot = {
                "type": "mcp_agent_state",
                "latest_plan_summary": self._normalize_progress_note(latest_plan_summary, max_length=600),
                "latest_reflection_summary": self._normalize_progress_note(latest_reflection_summary, max_length=600),
                "final_hint": self._normalize_progress_note(final_hint, max_length=600),
                "stop_reason": stop_reason,
                "pending_calls": [],
                "pending_user_decision": None,
            }
            agent_state_content = json.dumps(agent_state_snapshot, ensure_ascii=False)
            if tool_messages_streamed:
                progress_payload = {
                    "chat_idx": chat_idx,
                    "msg_type": "agent_state",
                    "msg_author": "ai_agent",
                    "msg_content": agent_state_content,
                }
                signals.progress.emit(json.dumps(progress_payload, ensure_ascii=False))
            else:
                tool_messages.append(
                    {
                        "msg_type": "agent_state",
                        "msg_author": "ai_agent",
                        "msg_content": agent_state_content,
                    }
                )

            final_system_prompt = self._build_mcp_combined_system_prompt(self._mcp_final_answer_system_prompt())
            final_stream_messages = build_phase_messages(final_system_prompt, final_prompt)
            result["stream_messages"] = final_stream_messages
            result["tool_messages"] = tool_messages
            return result
        except Exception as err:
            result["error"] = _('Error during MCP-based code analysis bootstrap: ') + str(err)
            return result
        finally:
            if ai_change_set_id != "":
                self._discard_empty_ai_change_set(ai_change_set_id)

    def new_text_analysis(self):
        """analyze a piece of text from an empirical document"""
        if self.app.project_name == "":
            msg = _('No project open.')
            Message(self.app, _('AI not enabled'), msg, "warning").exec()
            return
        if self.app.settings['ai_enable'] != 'True':
            msg = _('The AI is disabled. Go to "AI > Setup Wizard" first.')
            Message(self.app, _('AI not enabled'), msg, "warning").exec()
            return

        msg = _('We will now switch to the text coding workspace.\n There you can open a document, select a piece of text, right click on it and choose "AI Text Analysis" from the context menu.')
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        reply = msg_box.question(
            self,
            _('AI Text Analysis'),
            msg,
            QtWidgets.QMessageBox.StandardButton.Ok | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Ok  # <--- Default button
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Ok:
            self.main_window.text_coding(task='documents')
        else:
            return

    def new_code_analysis(self):
        """Start a new code analysis as an MCP-backed AI agent chat."""
        if self.app.project_name == "":
            msg = _('No project open.')
            Message(self.app, _('AI not enabled'), msg, "warning").exec()
            return
        if self.app.settings['ai_enable'] != 'True':
            msg = _('The AI is disabled. Go to "AI > Setup Wizard" first.')
            Message(self.app, _('AI not enabled'), msg, "warning").exec()
            return
       
        ui = DialogAiSearch(self.app, 'code_analysis')
        ret = ui.exec()
        if ret == QtWidgets.QDialog.DialogCode.Accepted:
            code_name = str(ui.selected_code_name if ui.selected_code_name is not None else '').strip()
            code_memo = str(ui.selected_code_memo if ui.selected_code_memo is not None else '').strip()
            file_ids = list(ui.selected_file_ids or [])
            code_ids = list(ui.selected_code_ids or [])
            coder_names = list(ui.coder_names or [])
            filter_info = dict(ui.selected_filter_info) if isinstance(ui.selected_filter_info, dict) else {}
            prompt_record = ui.current_prompt
            if prompt_record is None:
                msg = _('The selected code analysis prompt could not be loaded.')
                Message(self.app, _('AI prompts'), msg, "warning").exec()
                return

            segment_count = self._count_code_segments_for_selection(code_ids, file_ids, coder_names)
            if segment_count == 0:
                msg = _('No codings found for this particuar combination of coder, document filter, and code.')
                Message(self.app, _('Code analysis'), msg, 'warning').exec()
                return

            summary = _('Analyzing the data coded as "{}" ({} matching segments in scope.)').format(code_name, segment_count)
            if code_memo != '':
                summary += _('\nMemo:') + f' {code_memo}'
            prompt_label = self._analysis_prompt_display_name_and_scope(prompt_record, 'code_analysis')
            summary += _('\nPrompt:') + f' {prompt_label}'
            summary += _('\nMaterial:') + ' ' + self._code_analysis_filter_summary(file_ids, coder_names, filter_info)
            logger.debug('New code analysis chat.')
            self.new_chat(_('Code analysis') + f' "{code_name}"', 'code_analysis', summary, prompt_label)
            # warn if project memo empty 
            project_memo = extract_ai_memo(self.app.get_project_memo())
            if self.app.settings.get('ai_send_project_memo', 'True') == 'True' and len(project_memo) == 0:
                msg = _('Note that it is highly recommended to use the project memo (Menu "Project > Project Memo") \
to include a short description of your project\'s research topics, questions, objectives, and the empirical \
data collected. This information will accompany every prompt sent to the AI, resulting in much more targeted results.')
                self.process_message('info', msg)

            chat_idx = self.current_chat_idx
            self._persist_agent_prompt_record(chat_idx, prompt_record)
            self.process_message(
                'env_update',
                self._code_analysis_scope_env_update(code_name, code_memo, code_ids, coder_names, file_ids, filter_info),
                chat_idx,
            )
            bootstrap_spec = {
                "code_name": code_name,
                "code_memo": code_memo,
                "code_ids": code_ids,
                "coder_names": coder_names,
                "file_ids": file_ids,
                "filter_info": filter_info,
                "prompt_name": prompt_record.name,
                "prompt_scope": prompt_record.scope,
            }
            messages = self.history_get_ai_messages()
            self._start_mcp_agent_worker(messages, chat_idx, self._mcp_code_analysis_worker, bootstrap_spec)

    def new_code_chat(self):
        """Legacy alias for starting a new code analysis chat."""

        self.new_code_analysis()
 
    def new_topic_exploration(self):
        """Start a new topic exploration as an MCP-backed AI agent chat."""
        if self.app.project_name == "":
            msg = _('No project open.')
            Message(self.app, _('AI not enabled'), msg, "warning").exec()
            return
        if self.app.settings['ai_enable'] != 'True':
            msg = _('The AI is disabled. Go to "AI > Setup Wizard" first.')
            Message(self.app, _('AI not enabled'), msg, "warning").exec()
            return
       
        ui = DialogAiSearch(self.app, 'topic_exploration')
        ret = ui.exec()
        if ret == QtWidgets.QDialog.DialogCode.Accepted:
            topic_name = str(ui.selected_code_name if ui.selected_code_name is not None else '').strip()
            topic_description = str(ui.selected_code_memo if ui.selected_code_memo is not None else '').strip()
            file_ids = list(ui.selected_file_ids or [])
            filter_info = dict(ui.selected_filter_info) if isinstance(ui.selected_filter_info, dict) else {}
            prompt_record = ui.current_prompt
            if prompt_record is None:
                msg = _('The selected topic exploration prompt could not be loaded.')
                Message(self.app, _('AI prompts'), msg, "warning").exec()
                return

            summary = _('Exploring the free topic "{}" in the data.').format(topic_name)
            if topic_description != '':
                summary += _('\nDescription:') + f' {topic_description}'
            prompt_label = self._analysis_prompt_display_name_and_scope(prompt_record, 'topic_exploration')
            summary += _('\nPrompt:') + f' {prompt_label}'
            summary += _('\nMaterial:') + ' ' + self._topic_exploration_filter_summary(file_ids, filter_info)
            logger.debug('New topic exploration chat.')
            self.new_chat(_('Topic exploration') + f' "{topic_name}"', 'topic_exploration', summary, prompt_label)
            # warn if project memo empty 
            project_memo = extract_ai_memo(self.app.get_project_memo())
            if self.app.settings.get('ai_send_project_memo', 'True') == 'True' and len(project_memo) == 0:
                msg = _('Note that it is highly recommended to use the project memo (Menu "Project > Project Memo") \
to include a short description of your project\'s research topics, questions, objectives, and the empirical \
data collected. This information will accompany every prompt sent to the AI, resulting in much more targeted results.')
                self.process_message('info', msg)

            chat_idx = self.current_chat_idx
            self._persist_agent_prompt_record(chat_idx, prompt_record)
            self.process_message(
                'env_update',
                self._topic_exploration_scope_env_update(topic_name, topic_description, file_ids, filter_info),
                chat_idx,
            )
            bootstrap_spec = {
                "topic_name": topic_name,
                "topic_description": topic_description,
                "file_ids": file_ids,
                "filter_info": filter_info,
                "prompt_name": prompt_record.name,
                "prompt_scope": prompt_record.scope,
            }
            messages = self.history_get_ai_messages()
            self._start_mcp_agent_worker(messages, chat_idx, self._mcp_topic_exploration_worker, bootstrap_spec)

    def new_topic_chat(self):
        """Legacy alias for starting a new topic exploration chat."""

        self.new_topic_exploration()

    def get_filename(self, id_) -> str:
        """Return the filename for a source id
        Args:
            id_: source id
        Returns:
            str: name | '' if nothing found
        """
        # This might be called from a different thread (ai asynch operations), so have to create a new database connection
        conn = sqlite3.connect(os.path.join(self.app.project_path, 'data.qda'))
        cur = conn.cursor()
        cur.execute(f'select name from source where id = {id_}')
        res = cur.fetchone()[0]
        if res is not None:
            return res
        else:
            return ''

    def new_topic_chat_callback(self, chunks: List[Document], chat_idx: Optional[int] = None):
        # Analyze the data found
        if chat_idx is None:
            chat_idx = self.current_chat_idx
        if self._chat_scope_status(chat_idx) == 'canceled':
            self._log_chat_canceled_env_update(chat_idx, partial_response=False)
            self.process_message('info', _('Chat has been canceled by the user.'), chat_idx)
            if chat_idx == self.current_chat_idx:
                self.update_chat_window()
            return
        if chunks is None or len(chunks) == 0:
            msg = _('Sorry, the AI could could not find any data related to "') + self.ai_search_code_name + '".'
            self.process_message('info', msg, chat_idx)
            if chat_idx == self.current_chat_idx:
                self.update_chat_window()
            return
        
        self.ai_semantic_search_chunks = chunks                
        msg = _('Found related data. Analyzing the most relevant segments closer.')
        self.process_message('info', msg)
        self.update_chat_window()
        
        # store the found chunks in the table "topic_chat_embeddings" for later
        cursor = self.chat_history_conn.cursor()
        chat_id = int(self.chat_list[chat_idx][0])
        for i in range(len(chunks)):
            cursor.execute('''
                INSERT INTO topic_chat_embeddings (chat_id, docstore_id, position, used_flag)
                VALUES (?, ?, ?, ?)
            ''', (chat_id, chunks[i].id, i, (1 if i < topic_analysis_max_chunks else 0)))
        self.chat_history_conn.commit()                                

        ai_data = []
        max_ai_data_length = round(0.5 * (self.app.ai.large_llm_context_window * 4)) 
        max_ai_data_length_reached = False  # TODO varaible not used
        ai_data_length = 0
        for i in range(0, topic_analysis_max_chunks):
            if i >= len(chunks): 
                break
            if ai_data_length >= max_ai_data_length:
                max_ai_data_length_reached = True  # TODO variable not used
                break
            chunk = chunks[i]
            fulltext = self.app.get_text_fulltext(chunk.metadata["id"])
            line_start, line_end = self.app.get_line_numbers(fulltext, 
                                                             chunk.metadata["start_index"], 
                                                             chunk.metadata["start_index"] + len(chunk.page_content))
            ai_data.append({
                'source_id': f'{chunk.metadata["id"]}_{chunk.metadata["start_index"]}_{len(chunk.page_content)}_{line_start}_{line_end}',
                'source_name': self.get_filename(int(chunk.metadata['id'])),
                'quote': chunk.page_content,
                'line_start': line_start,
                'line_end': line_end
            })
            ai_data_length += len(chunk.page_content)
        
        ai_data_json = json.dumps(ai_data)
            
        ai_instruction = (
            f'You are exploring the topic "{self.ai_search_code_name}" with the following description: "{self.ai_search_code_memo}". \n'
            f'A semantic search in the empirical data resulted in the the following list of chunks of empirical data which might be relevant '
            f'for the exploration of the given topic:\n'   
            f'{ai_data_json}\n'
            f'Your task is to analyze the given empirical data following these instructions: {self.ai_prompt.content}\n'
            f'The whole discussion should be based updon the the empirical data provided and its proper interpretation. '
            f'Do not make any assumptions which are not supported by the data. '
            f'Please mention the sources that your refer to from the given empirical data, using an html anchor tag of the following form: '
            '(<a href="chunk:{source_id}">{source_name}: {line_start} - {line_end}</a>)\n' 
            f'Always answer in the following language: "{self.app.ai.get_curr_language()}".'
        )    
        logger.debug(f'Topic chat prompt:\n{ai_instruction}')
        self.process_message('instruct', ai_instruction)
        self.update_chat_window()   
                
    def topic_chat_get_actions(self) -> List[str]:
        # Analyze more data found in the semantic search
        cursor = self.chat_history_conn.cursor()
        chat_id = int(self.chat_list[self.current_chat_idx][0])
        cursor.execute(f'''
            SELECT id, docstore_id
            FROM topic_chat_embeddings
            WHERE chat_id = {chat_id} AND used_flag = 0
            ORDER BY position
            LIMIT 1
        ''')
        if cursor.fetchone() is None: # no data left
            return []
        
        msg = '<a href="action:topic_chat_analyze_more">' + _('Analyze more data...') + '</a>'
        return [msg]
            
    def topic_chat_analyze_more(self): 
        # Analyze more data found in the semantic search
        self.ai_output_autoscroll = True
        cursor = self.chat_history_conn.cursor()
        chat_id = int(self.chat_list[self.current_chat_idx][0])
        cursor.execute(f'''
            SELECT id, docstore_id
            FROM topic_chat_embeddings
            WHERE chat_id = {chat_id} AND used_flag = 0
            ORDER BY position
            LIMIT 30
        ''')
        res = cursor.fetchall()
        
        if res and len(res) > 0:
            topic_chat_embeddings_ids = [row[0] for row in res]
            docstore_ids = [row[1] for row in res]
            chunks = self.app.ai.sources_vectorstore.faiss_db_retrieve_documents(docstore_ids)  
        else:
            chunks = None   
        
        if chunks is None or len(chunks) == 0:
            msg = _('Error: There is no more data to analyze.')
            self.process_message('info', msg)
            self.update_chat_window()  
            return
        
        msg = _('Expanding the analysis with more data.')
        self.process_message('info', msg)
        self.update_chat_window()  
                        
        # self.ai_semantic_search_chunks = chunks
        ai_data = []
        max_ai_data_length = round(0.5 * (self.app.ai.large_llm_context_window * 4)) 
        max_ai_data_length_reached = False  # TODO varaible not used
        ai_data_length = 0
        for i in range(0, len(chunks)):
            if ai_data_length >= max_ai_data_length:
                max_ai_data_length_reached = True  # TODO variable not used
                break
            chunk = chunks[i]
            fulltext = self.app.get_text_fulltext(chunk.metadata["id"])
            line_start, line_end = self.app.get_line_numbers(fulltext, 
                                                             chunk.metadata["start_index"], 
                                                             chunk.metadata["start_index"] + len(chunk.page_content))
            ai_data.append({
                'source_id': f'{chunk.metadata["id"]}_{chunk.metadata["start_index"]}_{len(chunk.page_content)}_{line_start}_{line_end}',
                'source_name': self.get_filename(int(chunk.metadata['id'])),
                'quote': chunk.page_content,
                'line_start': line_start,
                'line_end': line_end
            })
            ai_data_length += len(chunk.page_content)
        
        ai_data_json = json.dumps(ai_data)
            
        ai_instruction = (
            f'Here are more chunks of empirical data from the semantic search described at the beginning '
            'of this conversation: \n'
            f'{ai_data_json}\n\n'
            f'Considering this data, are there any important aspects we must add to the analysis above '
            f'or do we need to revise our conclusions? Make sure to not digress. Ignore any data that is '
            f'not related to the topic of this analysis. Keep your answer short. '
            f'(Do not refer to these instructions in your answer, as they are not visible to the user.)'
        )    
        
        logger.debug(f'Topic chat analyze more prompt:\n{ai_instruction}')
        self.process_message('instruct', ai_instruction)
        self.update_chat_window()
        
        # mark all newly analyzed chunks of data as 'used':
        placeholders = ','.join(['?'] * len(topic_chat_embeddings_ids))
        query = f'''
            UPDATE topic_chat_embeddings
            SET used_flag = 1
            WHERE id IN ({placeholders})
        '''
        cursor.execute(query, topic_chat_embeddings_ids)
        self.chat_history_conn.commit()

    def _text_analysis_document_uri(self, doc_id: int, start_pos: int, text_length: int) -> str:
        """Build the MCP document URI for one selected text passage."""

        params = [
            ("start", str(max(0, int(start_pos)))),
            ("length", str(max(1, int(text_length)))),
        ]
        return f"qualcoder://documents/text/{int(doc_id)}?" + urlencode(params, doseq=True)

    def _text_analysis_scope_env_update(self, doc_id: int, doc_name: str, start_pos: int, text_length: int) -> str:
        """Build one durable scope note for text analysis agent chats."""

        return "\n".join(
            [
                'System event: This AI agent chat was started in text analysis mode.',
                f'Source document: "{str(doc_name).strip()}".',
                f'Selected passage: quote:{int(doc_id)}_{int(start_pos)}_{int(text_length)} ({int(text_length)} characters).',
                'Base the analysis primarily on the selected text passage.',
                'If narrowly targeted additional material would directly help to fulfill the active analysis prompt, you may retrieve and use it.',
                'Keep any expansion tightly focused, such as immediate context from the same document or a small number of closely relevant comparison passages.',
                'If a broader scope expansion would be helpful, ask the user for permission first.',
            ]
        )

    def _text_analysis_bootstrap_contract(self, doc_name: str, prompt: AgentPromptRecord,
                                          text_length: int) -> str:
        """Build the task contract for the first text-analysis turn before normal agent finalization."""

        prompt_name = str(prompt.name if prompt is not None and prompt.name is not None else '').strip()
        source_name = str(doc_name if doc_name is not None else '').strip()
        return (
            "Your task: "
            f'Work on a text analysis request centered on the selected passage from "{source_name}". '
            f'The selected passage is {int(text_length)} characters long.\n'
            f'The selected analysis prompt "/{prompt_name}" is active for this chat and should guide your analysis.\n'
            'The selected text passage is already available in this conversation as an MCP resource result. '
            'Treat this selected passage as the primary focus of the task. '
        )

    def _mcp_text_analysis_worker(self, messages: List[Any], chat_idx: int,
                                  bootstrap_spec: Dict[str, Any], signals=None) -> Dict[str, Any]:
        """Run the first text analysis turn on top of the normal MCP agent flow."""

        result: Dict[str, Any] = {
            "chat_idx": chat_idx,
            "stream_messages": [],
            "tool_messages": [],
            "canceled": False,
            "direct_ai_message": "",
            "direct_info_message": "",
        }
        allowed_methods = {
            "initialize",
            "resources/list",
            "resources/templates/list",
            "resources/read",
            "tools/list",
            "tools/call",
        }
        spec = dict(bootstrap_spec) if isinstance(bootstrap_spec, dict) else {}
        doc_id = int(spec.get("doc_id", -1) or -1)
        doc_name = str(spec.get("doc_name", "")).strip()
        start_pos = int(spec.get("start_pos", 0) or 0)
        text_length = int(spec.get("text_length", 0) or 0)
        prompt_name = str(spec.get("prompt_name", "")).strip()
        prompt_scope = str(spec.get("prompt_scope", "")).strip()

        prompt_record = self.agent_prompts_catalog.find_prompt_variant(
            prompt_name,
            prompt_scope,
            prompt_type="text_analysis",
            apply_init=False,
        )
        if prompt_record is None:
            raise ValueError(_("The selected text analysis prompt could not be loaded."))
        if doc_id <= 0 or text_length <= 0:
            raise ValueError(_("No text passage is available for this text analysis."))

        history_messages: List[Any] = list(messages)
        agent_messages: List[Any] = [msg for msg in history_messages if not isinstance(msg, SystemMessage)]
        mcp_base_system_prompt = self._mcp_base_system_prompt()
        ai_change_set_id = self._begin_ai_change_set(history_messages, chat_idx)
        final_hint = ""
        tool_messages: List[Dict[str, str]] = []
        tool_messages_streamed = signals is not None and getattr(signals, "progress", None) is not None
        bootstrap_calls: List[Tuple[str, Dict[str, Any]]] = [
            ("initialize", {}),
            ("resources/list", {}),
            ("resources/templates/list", {}),
            ("resources/read", {"uri": self._text_analysis_document_uri(doc_id, start_pos, text_length)}),
        ]
        reflection_json_schema = self._mcp_reflection_json_schema()
        max_calls_per_round = 8
        max_reflection_rounds = 4
        max_total_tool_calls = 20 + len(bootstrap_calls)
        max_queued_calls = 100
        total_tool_calls = 0
        stop_reason = ""
        latest_plan_summary = _("Prepared the selected text passage for analysis.")
        latest_reflection_summary = ""
        pending_user_decision = None
        deferred_calls_for_next_round: List[Dict[str, Any]] = []

        def _prepare_mcp_request(method_name: str, raw_params: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
            request_params = dict(raw_params) if isinstance(raw_params, dict) else {}
            display_params = dict(request_params)
            if method_name == "tools/call" and ai_change_set_id != "":
                request_params["_ai_change_set_id"] = ai_change_set_id
            return request_params, display_params

        def append_tool_exchange(method_name: str, method_params: Dict[str, Any], rpc_response: Dict[str, Any]):
            call_content = json.dumps(
                {"action": "mcp_call", "method": method_name, "params": method_params},
                ensure_ascii=False,
            )
            result_content = self._compact_mcp_result_content(method_name, method_params, rpc_response)
            agent_messages.append(AIMessage(content=call_content))
            agent_messages.append(HumanMessage(content=result_content))
            if tool_messages_streamed:
                signals.progress.emit(json.dumps({
                    "chat_idx": chat_idx,
                    "msg_type": "tool_call",
                    "msg_author": "ai_agent",
                    "msg_content": call_content,
                }, ensure_ascii=False))
                signals.progress.emit(json.dumps({
                    "chat_idx": chat_idx,
                    "msg_type": "tool_result",
                    "msg_author": "mcp_server",
                    "msg_content": result_content,
                }, ensure_ascii=False))
            else:
                tool_messages.append({"msg_type": "tool_call", "msg_author": "ai_agent", "msg_content": call_content})
                tool_messages.append({"msg_type": "tool_result", "msg_author": "mcp_server", "msg_content": result_content})

        def append_single_instruct_log(phase: str, role: str, content: str):
            payload = json.dumps(
                {
                    "phase": str(phase if phase is not None else "").strip() or "text_analysis",
                    "role": str(role if role is not None else "").strip() or "user",
                    "content": content,
                },
                ensure_ascii=False,
            )
            if tool_messages_streamed:
                signals.progress.emit(json.dumps({
                    "chat_idx": chat_idx,
                    "msg_type": "single_instruct",
                    "msg_author": "ai_agent",
                    "msg_content": payload,
                }, ensure_ascii=False))
            else:
                tool_messages.append({"msg_type": "single_instruct", "msg_author": "ai_agent", "msg_content": payload})

        try:
            self._emit_mcp_status_text(signals, chat_idx, _('Preparing selected text passage...'), status_kind="planning")
            for method, params in bootstrap_calls:
                if self.app.ai.is_current_run_canceled():
                    result["canceled"] = True
                    return result
                request_params, display_params = _prepare_mcp_request(method, params)
                status_text = self.ai_mcp_server.describe_status_event(method, request_params)
                self._emit_mcp_status(signals, chat_idx, status_text)
                _request, response = self._run_mcp_request(method, request_params)
                total_tool_calls += 1
                append_tool_exchange(method, display_params, response)

            reflection_system_prompt = self._build_mcp_combined_system_prompt(
                self._text_analysis_bootstrap_contract(doc_name, prompt_record, text_length)
                + "\n\n"
                + self._mcp_reflection_system_prompt()
            )
            reflection_prompt = (
                "Reflect on whether the currently retrieved evidence is sufficient for this text analysis and return JSON now. "
                "If not, propose only the minimal additional MCP calls needed."
            )

            def build_phase_request_message(phase_contract: str, trailing_instruction: str) -> HumanMessage:
                parts: List[str] = []
                phase_text = str(phase_contract if phase_contract is not None else "").strip()
                trailing_text = str(trailing_instruction if trailing_instruction is not None else "").strip()
                if phase_text != "":
                    parts.append(phase_text)
                if trailing_text != "":
                    parts.append(trailing_text)
                return HumanMessage(content="\n\n".join(parts).strip())

            def build_phase_messages(phase_contract: str, trailing_instruction: str) -> List[Any]:
                phase_messages: List[Any] = []
                if mcp_base_system_prompt != "":
                    phase_messages.append(SystemMessage(content=mcp_base_system_prompt))
                phase_messages.extend(agent_messages)
                phase_messages.append(build_phase_request_message(phase_contract, trailing_instruction))
                return phase_messages

            for reflection_round in range(max_reflection_rounds):
                if self.app.ai.is_current_run_canceled():
                    result["canceled"] = True
                    return result

                current_reflection_prompt = reflection_prompt
                if len(deferred_calls_for_next_round) > 0:
                    current_reflection_prompt += (
                        "\nDeferred calls from the previous execution queue "
                        f"(not yet executed because the round limit is {max_calls_per_round}):\n"
                        + json.dumps(deferred_calls_for_next_round, ensure_ascii=False)
                    )
                append_single_instruct_log(
                    "reflection",
                    "user",
                    build_phase_request_message(reflection_system_prompt, current_reflection_prompt).content,
                )
                reflection_messages = build_phase_messages(reflection_system_prompt, current_reflection_prompt)
                try:
                    reflection_data = self._invoke_json_llm_with_step_timeout(
                        reflection_messages,
                        schema_name='mcp_reflection_control',
                        response_schema=reflection_json_schema,
                        context='mcp_json_reflection',
                        step_name=_("Internal reflection"),
                        status_kind="reflection",
                        signals=signals,
                        chat_idx=chat_idx,
                    )
                except TimeoutError:
                    latest_reflection_summary = _('Internal reflection timed out; proceeding with the collected evidence.')
                    self._emit_mcp_status_text(
                        signals,
                        chat_idx,
                        latest_reflection_summary,
                        status_kind="reflection",
                    )
                    stop_reason = "reflection_timeout"
                    break

                reflection_summary = str(reflection_data.get("reflection_summary", "")).strip()
                if reflection_summary != "":
                    latest_reflection_summary = reflection_summary
                reflection_brief = str(reflection_data.get("answer_brief", "")).strip()
                if reflection_brief != "":
                    final_hint = reflection_brief
                enough_information = self._json_bool(reflection_data.get("enough_information", False), False)
                reflection_next_step_note = str(reflection_data.get("next_step_note", "")).strip()
                continue_deferred_calls = self._json_bool(
                    reflection_data.get("continue_deferred_calls", False),
                    False
                )
                revised_calls = self._normalize_mcp_calls(
                    reflection_data.get("revised_calls", []), allowed_methods, max_queued_calls
                )
                proposed_next_calls = self._normalize_mcp_calls(
                    reflection_data.get("proposed_next_calls", []), allowed_methods, max_calls_per_round
                )
                short_reflection_note = self._short_reflection_next_step_note(
                    reflection_summary,
                    reflection_next_step_note,
                )
                if short_reflection_note != "":
                    self._emit_mcp_status_text(signals, chat_idx, short_reflection_note, status_kind="reflection")
                user_decision_required = self._json_bool(reflection_data.get("user_decision_required", False), False)
                decision_question = self._normalize_progress_note(reflection_data.get("decision_question", ""), max_length=600)
                decision_context = self._normalize_progress_note(reflection_data.get("decision_context", ""), max_length=600)
                if user_decision_required and decision_question == "":
                    decision_question = short_reflection_note
                if user_decision_required and decision_question != "":
                    pending_user_decision = {
                        "phase": "reflection",
                        "question": decision_question,
                        "context": decision_context,
                        "proposed_next_calls": proposed_next_calls,
                    }
                    result["direct_ai_message"] = decision_question
                    stop_reason = "awaiting_user_decision"
                    break
                if enough_information:
                    stop_reason = "enough_information"
                    break

                current_round_calls, deferred_calls = self._split_mcp_call_queue(revised_calls, max_calls_per_round)
                if continue_deferred_calls and len(deferred_calls) > 0:
                    current_round_calls = self._merge_mcp_call_lists(current_round_calls, deferred_calls, max_calls_per_round)
                if len(current_round_calls) == 0:
                    if continue_deferred_calls and len(deferred_calls_for_next_round) > 0:
                        current_round_calls, deferred_calls = self._split_mcp_call_queue(
                            deferred_calls_for_next_round,
                            max_calls_per_round,
                        )
                    else:
                        deferred_calls = []
                deferred_calls_for_next_round = list(deferred_calls)
                if len(current_round_calls) == 0:
                    stop_reason = "no_more_valid_calls"
                    break

                for call in current_round_calls:
                    if self.app.ai.is_current_run_canceled():
                        result["canceled"] = True
                        return result
                    if total_tool_calls >= max_total_tool_calls:
                        stop_reason = "max_total_tool_calls_reached"
                        break
                    method = str(call.get("method", "")).strip()
                    params = call.get("params", {})
                    if not isinstance(params, dict):
                        params = {}
                    if method not in allowed_methods:
                        response = {
                            "jsonrpc": "2.0",
                            "id": self.ai_mcp_server.new_request_id(),
                            "error": {"code": -32601, "message": "Method not found", "data": method},
                        }
                        append_tool_exchange(method, params, response)
                        continue
                    request_params, display_params = _prepare_mcp_request(method, params)
                    status_text = self.ai_mcp_server.describe_status_event(method, request_params)
                    self._emit_mcp_status(signals, chat_idx, status_text)
                    _request, response = self._run_mcp_request(method, request_params)
                    total_tool_calls += 1
                    append_tool_exchange(method, display_params, response)
                if stop_reason == "max_total_tool_calls_reached":
                    break
            else:
                if stop_reason == "":
                    stop_reason = "max_reflection_rounds_reached"

            if pending_user_decision is not None:
                agent_state_snapshot = {
                    "type": "mcp_agent_state",
                    "latest_plan_summary": self._normalize_progress_note(latest_plan_summary, max_length=600),
                    "latest_reflection_summary": self._normalize_progress_note(latest_reflection_summary, max_length=600),
                    "final_hint": self._normalize_progress_note(final_hint, max_length=600),
                    "stop_reason": stop_reason,
                    "pending_calls": [],
                    "pending_user_decision": pending_user_decision,
                }
                agent_state_content = json.dumps(agent_state_snapshot, ensure_ascii=False)
                if tool_messages_streamed:
                    progress_payload = {
                        "chat_idx": chat_idx,
                        "msg_type": "agent_state",
                        "msg_author": "ai_agent",
                        "msg_content": agent_state_content,
                    }
                    signals.progress.emit(json.dumps(progress_payload, ensure_ascii=False))
                else:
                    tool_messages.append(
                        {
                            "msg_type": "agent_state",
                            "msg_author": "ai_agent",
                            "msg_content": agent_state_content,
                        }
                    )
                result["tool_messages"] = tool_messages
                result["stream_messages"] = []
                return result

            self._emit_mcp_status(signals, chat_idx, _('Preparing response...'))
            final_prompt = (
                "Now provide the final answer to the user in normal prose. "
                "Focus on outcomes of this turn and communicate them clearly. "
                "Do not mention internal MCP stage constraints. "
                "When referring to empirical text evidence, cite it as {REF: \"exact quote\"}. "
                "Remember: REF is invisible markup; if you want a quote to be visible, include the quoted text in normal prose and add REF in addition."
            )
            if final_hint != '':
                final_prompt += '\nHere is a draft idea from your internal reflection:\n' + final_hint
            if stop_reason not in ("", "enough_information"):
                final_prompt += (
                    "\nIf the available project evidence is incomplete, clearly state uncertainty and "
                    "mention what additional project material would help."
                )

            agent_state_snapshot = {
                "type": "mcp_agent_state",
                "latest_plan_summary": self._normalize_progress_note(latest_plan_summary, max_length=600),
                "latest_reflection_summary": self._normalize_progress_note(latest_reflection_summary, max_length=600),
                "final_hint": self._normalize_progress_note(final_hint, max_length=600),
                "stop_reason": stop_reason,
                "pending_calls": [],
                "pending_user_decision": None,
            }
            agent_state_content = json.dumps(agent_state_snapshot, ensure_ascii=False)
            if tool_messages_streamed:
                progress_payload = {
                    "chat_idx": chat_idx,
                    "msg_type": "agent_state",
                    "msg_author": "ai_agent",
                    "msg_content": agent_state_content,
                }
                signals.progress.emit(json.dumps(progress_payload, ensure_ascii=False))
            else:
                tool_messages.append(
                    {
                        "msg_type": "agent_state",
                        "msg_author": "ai_agent",
                        "msg_content": agent_state_content,
                    }
                )

            final_system_prompt = self._build_mcp_combined_system_prompt(self._mcp_final_answer_system_prompt())
            final_stream_messages = build_phase_messages(final_system_prompt, final_prompt)
            result["stream_messages"] = final_stream_messages
            result["tool_messages"] = tool_messages
            return result
        except Exception as err:
            result["error"] = _('Error during MCP-based text analysis bootstrap: ') + str(err)
            return result
        finally:
            if ai_change_set_id != "":
                self._discard_empty_ai_change_set(ai_change_set_id)

    def new_text_chat(self, doc_id, doc_name, text, start_pos, prompt):
        """Start one text analysis chat for the selected text passage."""

        if self.app.project_name == "":
            msg = _('No project open.')
            Message(self.app, _('AI not enabled'), msg, "warning").exec()
            return
        if self.app.settings['ai_enable'] != 'True':
            msg = _('The AI is disabled. Go to "AI > Setup Wizard" first.')
            Message(self.app, _('AI not enabled'), msg, "warning").exec()
            return
        prompt_name = str(getattr(prompt, 'name', '') if prompt is not None else '').strip()
        prompt_scope = str(getattr(prompt, 'scope', 'system') if prompt is not None else 'system').strip()
        prompt_record = self.agent_prompts_catalog.find_prompt_variant(
            prompt_name,
            prompt_scope,
            prompt_type="text_analysis",
            apply_init=False,
        )
        if prompt_record is None:
            msg = _('The selected text analysis prompt could not be loaded.')
            Message(self.app, _('AI prompts'), msg, "warning").exec()
            return

        max_ai_data_length = min(
            max(4000, round(0.5 * (self.app.ai.large_llm_context_window * 4))),
            int(getattr(self.ai_mcp_server, 'max_read_length', 12000)),
        )
        if len(text) > max_ai_data_length:
            msg = _('The text is too long to be analyzed in one go. Please select a shorter passage.')
            Message(self.app, _('AI text analysis'), msg, "warning").exec()
            return

        self.main_window.ai_go_chat()  # show chat dialog

        text_length = len(text)
        summary = (
            _('Analyzing text from ')
            + f'<a href="quote:{doc_id}_{start_pos}_{text_length}">{doc_name}</a> ('
            + str(text_length)
            + _(' characters).')
        )
        summary += _('\nPrompt:') + f' {self._analysis_prompt_display_name_and_scope(prompt_record, "text_analysis")}'
        logger.debug('New text analysis chat.')
        self.new_chat(_('Text analysis') + f' "{doc_name}"', 'text_analysis', summary, prompt_name_and_scope(prompt_record))

        chat_idx = self.current_chat_idx
        self._persist_agent_prompt_record(chat_idx, prompt_record)
        self.process_message(
            'env_update',
            self._text_analysis_scope_env_update(int(doc_id), str(doc_name), int(start_pos), text_length),
            chat_idx,
        )
        bootstrap_spec = {
            "doc_id": int(doc_id),
            "doc_name": str(doc_name),
            "start_pos": int(start_pos),
            "text_length": text_length,
            "prompt_name": prompt_record.name,
            "prompt_scope": prompt_record.scope,
        }
        messages = self.history_get_ai_messages()
        self._start_mcp_agent_worker(messages, chat_idx, self._mcp_text_analysis_worker, bootstrap_spec)
        
    def delete_chat(self):
        """Deletes the currently selected chat, connected to the button
           'pushButton_delete'
        """
        if self.current_chat_idx <= -1:
            return
        chat_id = int(self.chat_list[self.current_chat_idx][0])
        chat_name = self._display_chat_name(
            self.chat_list[self.current_chat_idx][1],
            self.chat_list[self.current_chat_idx][2],
        )
        msg = _('Do you really want to delete ') + '"' + chat_name + '"?'
        ui = DialogConfirmDelete(self.app, msg, _('Delete Chat'))
        ok = ui.exec()
        if not ok:
            return
        cursor = self.chat_history_conn.cursor()
        try:
            cursor.execute('DELETE from chat_messages WHERE chat_id = ?', (chat_id,))
            cursor.execute('DELETE from chats WHERE id = ?', (chat_id,))
            self.chat_history_conn.commit()
        except Exception as e_:
            print(e_)
            self.chat_history_conn.rollback()
            raise
        self.fill_chat_list()

    def find_chat_idx(self, chat_id) -> int | None:
        """Returns the index of the chat with the id 'chat_id' in self.chat_list
        """
        if chat_id is None:
            return None 
        for i in range(len(self.chat_list)):
            if self.chat_list[i][0] == chat_id:
                return i
        return None    
    
    def update_ai_busy(self):
        """update question button + progress bar"""
        if self.app.ai is None or not self._chat_scope_active():
            self.ui.pushButton_question.setIcon(qta.icon('mdi6.message-fast-outline', color=self.app.highlight_color()))
            self.ui.pushButton_question.setToolTip(_('Send your question to the AI'))
            self.ui.progressBar_ai.setRange(0, 100)  # Stops the animation
        else:
            if self.ui.progressBar_ai.maximum() > 0: 
                spin_icon = qta.icon("mdi.loading", color=self.app.highlight_color(), animation=qta.Spin(self.ui.pushButton_question))
                self.ui.pushButton_question.setIcon(spin_icon)
                self.ui.pushButton_question.setToolTip(_('Cancel AI generation'))
                self.ui.progressBar_ai.setRange(0, 0)  # Starts the animation
        # update ai status in the statusBar of the main window
        if self.app.ai is not None:
            if self.app.ai.get_status() == 'reading data' and self.app.ai.sources_vectorstore.reading_doc != '':
                self.main_window.statusBar().showMessage(_('AI: ') + _('reading data') + ' (' + self.app.ai.sources_vectorstore.reading_doc + ')')
            else:
                self.main_window.statusBar().showMessage(_('AI: ') + _(self.app.ai.get_status()))
        else: 
            self.main_window.statusBar().showMessage('')

    def on_ai_output_scroll(self, value):
        """Normally, if the AI is generating text, the scrollArea_ai_output scrolls to the bottom
        automatically so that the new text becomes visible. 
        This function ensures the if the user scroll up during the text generation, the auto
        scrolling stops. 
        If the user scroll back down the the end, the auto scrolling is re-enabled. 

        Args:
            value (int): current scroll position
        """
        max_value = self.ui.scrollArea_ai_output.verticalScrollBar().maximum()
        if value >= max_value:
            self.ai_output_autoscroll = True
        else:
            self.ai_output_autoscroll = False

    def _build_ai_output_document(self, width_px):
        """Build a QTextDocument for the current chat HTML at the given layout width."""

        html_text = self.ui.ai_output.text()
        if html_text is None or html_text == '':
            return None
        try:
            width = max(1, int(width_px))
        except (TypeError, ValueError):
            width = max(1, int(self.ui.ai_output.width()))
        doc = QtGui.QTextDocument()
        doc.setDefaultFont(self.ui.ai_output.font())
        doc.setHtml(html_text)
        doc.setTextWidth(float(width))
        return doc

    def _document_y_for_char_position(self, doc, char_pos):
        """Return vertical y-coordinate for a character position in a QTextDocument."""

        if doc is None:
            return 0.0
        max_pos = max(0, int(doc.characterCount()) - 1)
        pos = max(0, min(int(char_pos), max_pos))
        block = doc.findBlock(pos)
        if not block.isValid():
            return 0.0
        block_top = float(doc.documentLayout().blockBoundingRect(block).top())
        layout = block.layout()
        if layout is None or layout.lineCount() == 0:
            return block_top
        rel_pos = max(0, pos - int(block.position()))
        line = layout.lineForTextPosition(rel_pos)
        if not line.isValid():
            line = layout.lineAt(max(0, layout.lineCount() - 1))
        return block_top + float(line.y())

    def capture_ai_output_top_anchor(self):
        """Capture a width-independent anchor representing the top visible text position."""

        bar = self.ui.scrollArea_ai_output.verticalScrollBar()
        scroll_value = int(bar.value())
        max_value = int(bar.maximum())
        if max_value <= 0:
            return {'mode': 'top'}
        if scroll_value >= max(0, max_value - 2):
            return {'mode': 'bottom'}
        doc = self._build_ai_output_document(self.ui.ai_output.width())
        if doc is None:
            return {'mode': 'value', 'value': scroll_value}
        pos = int(doc.documentLayout().hitTest(
            QtCore.QPointF(1.0, float(scroll_value) + 1.0),
            QtCore.Qt.HitTestAccuracy.FuzzyHit
        ))
        if pos < 0:
            pos = 0
        y_pos = self._document_y_for_char_position(doc, pos)
        offset = float(scroll_value) - y_pos
        return {'mode': 'char', 'char_pos': int(pos), 'offset': float(offset)}

    def restore_ai_output_top_anchor(self, anchor):
        """Restore a previously captured top-text anchor after layout/width changes."""

        if not isinstance(anchor, dict):
            return
        mode = str(anchor.get('mode', ''))
        bar = self.ui.scrollArea_ai_output.verticalScrollBar()
        if mode == 'bottom':
            bar.setValue(bar.maximum())
            return
        if mode == 'top':
            bar.setValue(0)
            return
        if mode == 'char':
            doc = self._build_ai_output_document(self.ui.ai_output.width())
            if doc is None:
                return
            char_pos = int(anchor.get('char_pos', 0))
            offset = float(anchor.get('offset', 0.0))
            y_pos = self._document_y_for_char_position(doc, char_pos)
            target = int(round(y_pos + offset))
            target = max(0, min(target, int(bar.maximum())))
            bar.setValue(target)
            return
        if mode == 'value':
            target = int(anchor.get('value', 0))
            target = max(0, min(target, int(bar.maximum())))
            bar.setValue(target)

    def update_chat_window(self, scroll_to_bottom=True):
        """load current chat into self.ai_output"""
        if self.current_chat_idx > -1:
            self.is_updating_chat_window = True
            try:
                html_parts = []
                self.ui.plainTextEdit_question.setEnabled(True)
                self.ui.pushButton_question.setEnabled(True)
                chat = self.chat_list[self.current_chat_idx]
                id_, name, analysis_type, summary, date, analysis_prompt = chat
                if hasattr(self, "_prompt_reference_highlighter"):
                    self._prompt_reference_highlighter.rehighlight()
                if analysis_type == 'text chat':
                    # Extract doc info from the summary field:
                    doc_info_pattern = r'<a href="quote:(\d+)_(\d+)_(\d+)">(.+?)</a>'
                    m = re.search(doc_info_pattern, summary)
                    if m:
                        try:
                            self.ai_text_doc_id = int(m.group(1))
                            self.ai_text_start_pos = int(m.group(2))
                            len_text = int(m.group(3))
                            cursor = self.app.conn.cursor()
                            sql = f'SELECT name, fulltext FROM source WHERE id = {self.ai_text_doc_id}'
                            cursor.execute(sql)
                            source = cursor.fetchone()
                            self.ai_text_doc_name = source[0]
                            self.ai_text_text = source[1][self.ai_text_start_pos:self.ai_text_start_pos + len_text] 
                        except:
                            self.ai_text_doc_id = None
                            self.ai_text_start_pos = None
                            self.ai_text_doc_name = None
                            self.ai_text_text = ''
                    else:
                        self.ai_text_doc_id = None
                        self.ai_text_start_pos = None
                        self.ai_text_doc_name = None   
                        self.ai_text_text = ''                   

                # Show title
                html_parts.append(f'<h1 style={self.ai_info_style}>{self._display_chat_name(name, analysis_type)}</h1>')
                summary_br = summary.replace('\n', '<br />')
                display_type = self._display_chat_type_label(analysis_type, preserve_legacy_general=True)
                if not self._is_agent_chat_type(analysis_type):
                    html_parts.append(
                        f"<p style={self.ai_info_style}><b>{_('Type:')}</b> {display_type}<br /><b>{_('Summary:')}</b> {summary_br}<br /><b>{_('Date:')}</b> {date}<br /><b>{_('Prompt:')}</b> {analysis_prompt}</p>"
                    )
                else:
                    html_parts.append(
                        f"<p style={self.ai_info_style}><b>{_('Type:')}</b> {display_type}<br /><b>{_('Summary:')}</b> {summary_br}<br /><b>{_('Date:')}</b> {date}</p>"
                    )
                # Show chat messages:
                agent_status_lines = []
                agent_status_author = ''
                markdown_hr_width = max(
                    1,
                    max(self.ui.ai_output.width(), self.ui.scrollArea_ai_output.viewport().width()) - 24
                )
                if self._is_agent_chat_type(analysis_type):
                    self._refresh_prompt_completion_records()

                def flush_agent_status_block():
                    nonlocal agent_status_lines, agent_status_author
                    if len(agent_status_lines) == 0:
                        return
                    # body = '<br />'.join(agent_status_lines)
                    body = "".join(agent_status_lines)
                    block = f'{self._ai_agent_heading_html(agent_status_author, chat_idx=self.current_chat_idx)}<ul>{body}</ul>'
                    html_parts.append(f'<p style={self.ai_status_style}>{block}</p>')
                    agent_status_lines = []
                    agent_status_author = ''

                for msg in self.chat_msg_list:
                    msg_type = str(msg[2])
                    if msg_type == 'agent_status':
                        raw_status = str(msg[4] if msg[4] is not None else '')
                        status_kind = ''
                        status_text = raw_status
                        try:
                            status_payload = json.loads(raw_status)
                        except Exception:
                            status_payload = None
                        if isinstance(status_payload, dict):
                            status_kind = str(status_payload.get("kind", "")).strip().lower()
                            status_text = str(status_payload.get("text", "")).strip()
                        status_line = html_lib.escape(status_text).replace('\n', '<br />')
                        if status_line.strip() == '':
                            continue
                        if status_kind in ('planning', 'reflection'):
                            status_line = f'<li>{status_line}</li>'
                        else:
                            status_line = f'<li>{status_line}</li>'
                        status_author = str(msg[3] if msg[3] is not None else '').strip()
                        if status_author == '':
                            status_author = 'unknown'
                        if len(agent_status_lines) > 0 and status_author != agent_status_author:
                            flush_agent_status_block()
                        if agent_status_author == '':
                            agent_status_author = status_author
                        agent_status_lines.append(status_line)
                        continue

                    # Only visible non-status message types flush the buffered status block.
                    if msg_type in ('user', 'ai', 'info'):
                        flush_agent_status_block()

                    if msg_type == 'user':
                        txt = self._render_user_markdown_to_html(
                            msg[4],
                            hr_color=self.ai_user_color,
                            hr_width_px=markdown_hr_width,
                        )
                        author = msg[3]
                        if author is None or author == '':
                            author = 'unkown'
                        heading = f'{_("User")} ({author}):'
                        txt = f'{self._message_heading_html(heading)}{txt}'
                        html_parts.append(f'<p style={self.ai_user_style}>{txt}</p>')
                    elif msg_type == 'ai':
                        txt = render_markdown_to_html(
                            msg[4],
                            hr_color=self.ai_response_color,
                            hr_width_px=markdown_hr_width,
                        )
                        author = msg[3]
                        txt = f'{self._ai_agent_heading_html(author, chat_idx=self.current_chat_idx)}{txt}'
                        html_parts.append(f'<p style={self.ai_response_style}>{txt}</p>')
                    elif msg_type == 'info':
                        txt = self._message_heading_html(_("Info:"))
                        txt += render_markdown_to_html(
                            msg[4],
                            hr_width_px=markdown_hr_width,
                        )
                        html_parts.append(f'<p style={self.ai_info_style}>{txt}</p>')
                flush_agent_status_block()
                # add partially streamed ai response if needed
                if self.current_chat_idx == self.current_streaming_chat_idx and len(self.app.ai.ai_streaming_output) > 0:
                    txt = self.app.ai.ai_streaming_output
                    txt = strip_think_blocks(txt)
                    if len(self.app.ai.ai_streaming_output) != len(txt) and len(txt) == 0:
                        txt = _('Thinking...')
                    txt = self.replace_references(txt, streaming=True)
                    txt = render_markdown_to_html(
                        txt,
                        hr_color=self.ai_response_color,
                        hr_width_px=markdown_hr_width,
                    )
                    txt = f'{self._ai_agent_heading_html(chat_idx=self.current_chat_idx, fallback_to_current=True)}{txt}'
                    html_parts.append(f'<div style={self.ai_response_style}>{txt}</div>')
                elif not self._chat_scope_active(self.current_chat_idx): # streaming finished, add actions
                    actions_list = []
                    if analysis_type == 'topic chat':
                        actions_list.extend(self.topic_chat_get_actions())                        
                    if len(actions_list):
                        # html += f'<p style={self.ai_actions_style}>&nbsp;</p>'
                        button_color = self.ui.pushButton_question.palette().color(QPalette.ColorRole.Button).name()
                        actions_html = '<table border="0" cellspacing="3" cellpadding="10"><tr>'
                        for action in actions_list:
                            actions_html += f'<td style="background-color: {button_color}">{action}</td>'
                        actions_html += '</tr></table>' 
                        html_parts.append(f'<p style={self.ai_actions_style}>{actions_html}</p>')
                self.ui.ai_output.setText(''.join(html_parts))
            finally:
                if scroll_to_bottom:
                    self.ai_output_scroll_to_bottom()
                    self.ui.plainTextEdit_question.setFocus()
                self.is_updating_chat_window = False
        else:
            self.ui.ai_output.setText('')
            self.ui.plainTextEdit_question.setEnabled(False)
            self.ui.pushButton_question.setEnabled(False)
            if hasattr(self, "_prompt_reference_highlighter"):
                self._prompt_reference_highlighter.rehighlight()
            
    def _strip_ref_quotes(self, raw: Any) -> str:
        """Remove wrapping quote marks from a REF payload while preserving inner text."""

        text = str(raw if raw is not None else "").strip()
        while text and (text[0] in "\"'" or unicodedata.category(text[0]) in ("Pi", "Pf")):
            text = text[1:].lstrip()
        while text and (text[-1] in "\"'" or unicodedata.category(text[-1]) in ("Pi", "Pf")):
            text = text[:-1].rstrip()
        return text

    def _text_ref_candidates(self) -> List[Dict[str, Any]]:
        """Expose the active text-analysis excerpt as a single resolver candidate."""

        source_id = self._safe_int(self.ai_text_doc_id, -1)
        start = self._safe_int(self.ai_text_start_pos, -1)
        text = str(self.ai_text_text if self.ai_text_text is not None else "")
        if source_id <= 0 or start < 0 or text.strip() == "":
            return []
        source_name = str(self.ai_text_doc_name if self.ai_text_doc_name is not None else "").strip()
        if source_name == "":
            source_name = self.get_filename(source_id)
        return [{
            "source_id": source_id,
            "source_name": source_name,
            "start": start,
            "length": len(text),
            "text": text,
        }]

    def _replace_references_from_candidates(
            self,
            text: Any,
            candidates: List[Dict[str, Any]],
            streaming: bool = False,
            streaming_placeholder: Optional[str] = None) -> str:
        """Replace {REF: ...} tags using a prepared list of evidence candidates."""

        res = str(text)
        if streaming:
            placeholder = streaming_placeholder if streaming_placeholder is not None else _('(source reference)')
            res = re.sub(r'\{REF:[^\}]*\}', placeholder, res)
            incomplete_ref = re.search(r'\{REF:[^\}]*$', res)
            if incomplete_ref:
                res = res[:incomplete_ref.start()].rstrip()
            return res

        ref_pattern = r'\{REF:\s*(.+?)\s*\}'

        def replace_ref(match):
            quote = self._strip_ref_quotes(match.group(1))
            return self._resolve_ref_quote_to_anchor(quote, candidates)

        return re.sub(ref_pattern, replace_ref, res)

    def _replace_text_references(self, text, streaming=False):
        """Replace REF tags for text-analysis chats using the shared resolver."""

        candidates = self._text_ref_candidates()
        if not candidates:
            return str(text)
        source_name = str(candidates[0].get("source_name", "")).strip()
        return self._replace_references_from_candidates(
            text,
            candidates,
            streaming=streaming,
            streaming_placeholder=f'({source_name})' if source_name != "" else _('(source reference)')
        )

    def replace_references(self, text, streaming=False, chat_idx=None):
        """Replace text-analysis and MCP/general-chat references with clickable links."""

        res = str(text)
        if self.ai_text_doc_id is not None:
            return self._replace_text_references(res, streaming=streaming)
        candidates = self._collect_ref_candidates(chat_idx)
        return self._replace_references_from_candidates(
            res,
            candidates,
            streaming=streaming,
            streaming_placeholder=_('(source reference)')
        )

    def _chat_list_current_row(self):
        index = self.ui.treeView_chat_list.currentIndex()
        if index.isValid():
            return index.row()
        return -1

    def _set_chat_list_current_row(self, row):
        if row is None or row < 0 or row >= self.chat_list_model.rowCount():
            with QtCore.QSignalBlocker(self.ui.comboBox_ai_chats):
                self.ui.comboBox_ai_chats.setCurrentIndex(-1)
            self.ui.treeView_chat_list.setCurrentIndex(QtCore.QModelIndex())
            return
        with QtCore.QSignalBlocker(self.ui.comboBox_ai_chats):
            self.ui.comboBox_ai_chats.setCurrentIndex(row)
        index = self.chat_list_model.index(row, 0)
        self.ui.treeView_chat_list.setCurrentIndex(index)

    def chat_list_selection_changed(self, selected=None, deselected=None, force_update=False):
        self._dismiss_prompt_completion(accept=False)
        current_row = self._chat_list_current_row()
        with QtCore.QSignalBlocker(self.ui.comboBox_ai_chats):
            self.ui.comboBox_ai_chats.setCurrentIndex(current_row)
        self.ui.pushButton_delete.setEnabled(current_row > -1)
        if (not force_update) and (self.current_chat_idx == current_row):
            return
        if self._cancel_chat_scope(self.current_chat_idx, ask=True):
            # AI generation is either finished or canceled, we can change to another chat
            self.current_chat_idx = current_row
            self.ui.pushButton_delete.setEnabled(self.current_chat_idx > -1)
            self.history_update_message_list()
            self.update_chat_window(scroll_to_bottom=False)
        else:  # return to previous chat
            self._set_chat_list_current_row(self.current_chat_idx)
        
    def chat_list_item_changed(self, item: QStandardItem):
        """This method is called whenever the name of a chat is edited in the list"""
        if self._is_updating_chat_title_item:
            return
        row = item.row()
        if row < 0 or row >= len(self.chat_list):
            return
        previous_name = self.chat_list[row][1]
        analysis_type = self.chat_list[row][2]
        proposed_name = str(item.text()).strip()
        if previous_name.strip() == '' and self._is_agent_chat_type(analysis_type) and proposed_name == self._empty_agent_chat_alias():
            self._refresh_chat_list_item(row)
            self._refresh_chat_name_views()
            return
        if not self._rename_chat_at_row(row, proposed_name):
            self._refresh_chat_list_item(row)
            self._refresh_chat_name_views()

    def open_context_menu(self, position):
        index = self.ui.treeView_chat_list.indexAt(position)
        if index.isValid():
            self.ui.treeView_chat_list.setCurrentIndex(index)
        context_menu = QtWidgets.QMenu(self)
        if self.chat_list_model.rowCount() > 0:
            if self.current_chat_idx > -1:
                edit_action = QAction("Edit Title", self)
                delete_action = QAction("Delete Chat", self)
                export_action = QAction("Export Chat", self)
                context_menu.addAction(edit_action)
                context_menu.addAction(delete_action)
                context_menu.addAction(export_action)
                edit_action.triggered.connect(self.edit_title)
                delete_action.triggered.connect(self.delete_chat)
                export_action.triggered.connect(self.export_chat)

            # The search function will be implemented later:
            # search_action = QAction("Search all Chats", self)
            # context_menu.addAction(search_action)
            # search_action.triggered.connect(self.search_chat)

        if len(context_menu.actions()) > 0:
            context_menu.exec(self.ui.treeView_chat_list.viewport().mapToGlobal(position))

    def edit_title(self):
        """Edit the title of the current chat"""
        row = self.current_chat_idx
        if row < 0 or row >= len(self.chat_list):
            return
        current_name = self.chat_list[row][1]
        dialog = self._create_text_input_dialog(_('Edit chat title'), _('Title:'), current_name)
        ok = dialog.exec()
        if not ok:
            return
        self._rename_chat_at_row(row, dialog.textValue())

    def export_chat(self):
        """Export the current chat into a html or txt file"""
        chat_content = self.ui.ai_output.text()
        default_file_name = self._display_chat_name(
            self.chat_list[self.current_chat_idx][1],
            self.chat_list[self.current_chat_idx][2],
        )
        default_file_name = default_file_name.replace('"', '')
        if self.last_export_dir != '':
            default_file_name = os.path.join(self.last_export_dir, default_file_name)
        else:
            default_file_name = os.path.join(os.path.dirname(self.app.project_path), default_file_name)
        options = QtWidgets.QFileDialog.Options()
        options |= QtWidgets.QFileDialog.Option.DontUseNativeDialog
        file_name, selected_filter = QtWidgets.QFileDialog.getSaveFileName(
            self, 
            _("Export Chat"), 
            default_file_name, 
            "HTML (*.html);;Text only (*.txt)", 
            options=options            
        )                
        if file_name:
            self.last_export_dir = os.path.dirname(file_name)
            if not any(file_name.endswith(ext) for ext in [".html", ".txt"]):
                if "HTML" in selected_filter:
                    file_name += ".html"
                elif "Text" in selected_filter:
                    file_name += ".txt"
            if os.path.exists(file_name):
                msg = _('The file already exists. Do you want to override it?')
                msg_box = Message(self.app, _('Export Chat'), msg, "critical")
                if msg_box.question(self, _('Export Chat'), msg) == QtWidgets.QMessageBox.StandardButton.No:
                    return
            if file_name.endswith(".html"):
                self._export_to_html(file_name, chat_content)
            elif file_name.endswith(".txt"):
                self._export_to_txt(file_name, chat_content)

    def _export_to_html(self, file_name, content):
        # Write the chat content as HTML
        with open(file_name, 'w', encoding='utf-8') as file:
            file.write("<html><head><meta charset='utf-8'></head><body>")
            file.write(content)
            file.write("</body></html>")

    def _export_to_txt(self, file_name, content):
        # Strip tags for plain text export and write the content as plain text
        from PyQt6.QtGui import QTextDocument
        document = QTextDocument()
        document.setHtml(content)
        plain_text_content = document.toPlainText()
        with open(file_name, 'w', encoding='utf-8') as file:
            file.write(plain_text_content)        
    
    """    
    def search_chat(self):
        # Fulll text search over all chats, will be implemented later
        index = self.ui.treeView_chat_list.currentIndex()
        if index.isValid():
            print(f"Searching chat: {index.data()}")
    """

    def button_new_clicked(self):
        # Create QMenu
        menu = QtWidgets.QMenu()
        menu.setStyleSheet(self.font)
        menu.setToolTipsVisible(True)

        # Add actions
        action_general_chat = menu.addAction(_('New AI Agent Chat'))
        action_general_chat.setIcon(self.app.ai.general_chat_icon())
        action_general_chat.setToolTip(_('Analyze your data together with an AI Agent.'))        
        action_topic_exploration = menu.addAction(_('New topic exploration chat'))
        action_topic_exploration.setIcon(self.app.ai.topic_exploration_icon())
        action_topic_exploration.setToolTip(_('Explore a free-search topic together with the AI agent.'))
        action_text_analysis = menu.addAction(_('New text analysis chat'))
        action_text_analysis.setIcon(self.app.ai.text_analysis_icon())
        action_text_analysis.setToolTip(_('Analyse a piece of text from your empirical data together with the AI.'))
        action_codings_analysis = menu.addAction(_('New code analysis chat'))
        action_codings_analysis.setIcon(self.app.ai.code_analysis_icon())
        action_codings_analysis.setToolTip(_('Analyze the data collected under a certain code together with the AI agent.'))

        # Obtain the bottom-left point of the button in global coordinates
        button_rect = self.ui.pushButton_new_analysis.rect()  # Get the button's rect
        bottom_left_point = button_rect.bottomLeft()  # Bottom-left point
        global_bottom_left_point = self.ui.pushButton_new_analysis.mapToGlobal(bottom_left_point)  # Map to global

        # Execute the menu at the calculated position
        action = menu.exec(global_bottom_left_point)

        # Check which action was selected and do something
        if action == action_text_analysis:
            self.new_text_analysis()
        elif action == action_codings_analysis:
            self.new_code_analysis()
        elif action == action_topic_exploration:
            self.new_topic_exploration()
        elif action == action_general_chat:
            self.new_general_chat('', '')

    def ai_output_scroll_to_bottom(self, minVal=None, maxVal=None):  # toDO minVal, maxVal unused
        #self._ai_output_scroll_to_bottom()
        # Delay the scrolling a little to make sure that the updated text is fully rendered before scrolling to the bottom: 
        QtCore.QTimer.singleShot(200, self._ai_output_scroll_to_bottom)
        
    def _ai_output_scroll_to_bottom(self):
        if self.ai_output_autoscroll:
            self.ui.scrollArea_ai_output.verticalScrollBar().setValue(self.ui.scrollArea_ai_output.verticalScrollBar().maximum())
            self.ai_output_autoscroll = True
                                
    def history_update_message_list(self, db_conn=None):
        """Update sel.chat_msg_list from the database

        Args:
            db_conn: database conncetion, if None, use defaults to self.chat:history_conn
        """
        if self.current_chat_idx > -1:
            curr_chat_id = self.chat_list[self.current_chat_idx][0]
            if db_conn is None:
                db_conn = self.chat_history_conn 
            cursor = db_conn.cursor()
            cursor.execute('SELECT * FROM chat_messages WHERE chat_id=? ORDER BY id', (curr_chat_id,))
            self.chat_msg_list = cursor.fetchall()
            self.ai_streaming_output = ''
        else:
            self.chat_msg_list.clear()
            self.ai_streaming_output = ''
    
    def history_get_ai_messages(self):
        messages = []
        latest_agent_state_id = -1
        latest_prompt_ids: Dict[str, int] = {}
        base_prompt_keys: set[str] = set()
        analysis_type = ''
        if 0 <= self.current_chat_idx < len(self.chat_list):
            analysis_type = str(self.chat_list[self.current_chat_idx][2])
        if self._is_agent_chat_type(analysis_type):
            _, base_prompt_keys = self._collect_agent_base_prompt_context()
        for msg in self.chat_msg_list:
            if msg[2] == 'agent_state':
                try:
                    msg_id = int(msg[0])
                except Exception:
                    msg_id = -1
                if msg_id > latest_agent_state_id:
                    latest_agent_state_id = msg_id
            elif msg[2] == 'prompt':
                prompt_name = str(msg[3] if msg[3] is not None else '').strip()
                if prompt_name == '':
                    continue
                if prompt_name.casefold() in base_prompt_keys:
                    continue
                try:
                    msg_id = int(msg[0])
                except Exception:
                    msg_id = -1
                prev_id = latest_prompt_ids.get(prompt_name, -1)
                if msg_id > prev_id:
                    latest_prompt_ids[prompt_name] = msg_id

        for msg in self.chat_msg_list:
            if msg[2] == 'system':
                messages.append(SystemMessage(content=msg[4]))
            elif msg[2] == 'instruct' or msg[2] == 'user':
                messages.append(HumanMessage(content=msg[4]))
            elif msg[2] == 'prompt':
                prompt_name = str(msg[3] if msg[3] is not None else '').strip()
                if prompt_name == '':
                    continue
                if prompt_name.casefold() in base_prompt_keys:
                    continue
                try:
                    msg_id = int(msg[0])
                except Exception:
                    msg_id = -1
                if msg_id != latest_prompt_ids.get(prompt_name, -1):
                    continue
                messages.append(HumanMessage(content=msg[4]))
            elif msg[2] == 'env_update':
                messages.append(HumanMessage(content=msg[4]))
            elif msg[2] == 'ai':
                messages.append(AIMessage(content=msg[4]))
            elif msg[2] == 'tool_call':
                messages.append(AIMessage(content=msg[4]))
            elif msg[2] == 'tool_result':
                messages.append(HumanMessage(content=msg[4]))
            elif msg[2] == 'agent_state':
                # keep only the newest compact agent-state snapshot across turns
                try:
                    msg_id = int(msg[0])
                except Exception:
                    msg_id = -1
                if msg_id != latest_agent_state_id:
                    continue
                state_payload = str(msg[4]).strip()
                if state_payload != '':
                    messages.append(HumanMessage(content='Agent state snapshot:\n' + state_payload))
            elif msg[2] == 'single_instruct':
                # one-shot instruction logs must not be replayed in later turns
                continue
        return messages
    
    def history_add_message(self, msg_type, msg_author, msg_content, chat_idx=None, db_conn=None, refresh=True, commit=True):
        self.ai_streaming_output = ''
        if chat_idx is None:
            chat_idx = self.current_chat_idx
        if chat_idx > -1:
            curr_chat_id = self.chat_list[chat_idx][0]
            if msg_type == 'ai':
                msg_content = self.replace_references(msg_content, chat_idx=chat_idx)
            if db_conn is None:
                db_conn = self.chat_history_conn
            cursor = db_conn.cursor()
            # Insert new message
            cursor.execute('INSERT INTO chat_messages (chat_id, msg_type, msg_author, msg_content)'
                           ' VALUES (?, ?, ?, ?)', (curr_chat_id, msg_type, msg_author, msg_content))
            if commit:
                db_conn.commit()
            if refresh:
                self.history_update_message_list(db_conn)

    def history_add_or_append_agent_status(self, status_text: str, chat_idx=None, msg_author='ai_agent'):
        """Persist one agent status line as its own DB row (not merged)."""
        if chat_idx is None:
            chat_idx = self.current_chat_idx
        if chat_idx <= -1:
            return
        if status_text is None or status_text.strip() == '':
            return
        msg_author = self._normalize_ai_profile_author(msg_author, chat_idx=chat_idx, fallback_to_current=True)
        curr_chat_id = self.chat_list[chat_idx][0]
        cursor = self.chat_history_conn.cursor()
        status_line = status_text.strip()

        # Guard against immediate duplicate callback events.
        cursor.execute(
            "SELECT msg_author, msg_content FROM chat_messages "
            "WHERE chat_id=? AND msg_type='agent_status' ORDER BY id DESC LIMIT 1",
            (curr_chat_id,),
        )
        row = cursor.fetchone()
        if row is not None:
            prev_author = '' if row[0] is None else str(row[0])
            prev_content = '' if row[1] is None else str(row[1])
            if prev_author == str(msg_author) and prev_content == status_line:
                return

        cursor.execute('INSERT INTO chat_messages (chat_id, msg_type, msg_author, msg_content)'
                       ' VALUES (?, ?, ?, ?)', (curr_chat_id, 'agent_status', msg_author, status_line))
        self.chat_history_conn.commit()
        self.history_update_message_list()

    def _chat_user_message_count(self, chat_id: int, db_conn=None) -> int:
        """Count persisted user messages for one chat."""

        if db_conn is None:
            db_conn = self.chat_history_conn
        cursor = db_conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM chat_messages WHERE chat_id=? AND msg_type='user'",
            (chat_id,),
        )
        row = cursor.fetchone()
        if row is None or row[0] is None:
            return 0
        return int(row[0])

    def _agent_chat_metadata_system_prompt(self) -> str:
        language = str(self.app.ai.get_curr_language()).strip()
        return (
            "Create concise metadata for a new AI agent chat. "
            "Return ONLY one JSON object with this shape:\n"
            "{"
            "\"name\": \"short chat title\", "
            "\"summary\": \"one short summary sentence\""
            "}\n"
            "Rules:\n"
            f"- Write both fields in {language}.\n"
            "- name must be specific, 2 to 8 words, and must not be a generic placeholder.\n"
            "- name must not contain quotes, line breaks, or ending punctuation.\n"
            "- summary must be one concise sentence, max 160 characters.\n"
            "- Base the result only on the first user message.\n"
            "- Do not output prose outside JSON.\n"
        )

    def _agent_chat_metadata_json_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "summary": {"type": "string"},
            },
            "required": ["name", "summary"],
            "additionalProperties": False,
        }

    def _sanitize_generated_chat_title(self, raw_title: str) -> str:
        title = re.sub(r'\s+', ' ', str(raw_title if raw_title is not None else '')).strip()
        title = title.strip('\'"“”‘’`')
        title = title.rstrip('.,:;!?')
        if len(title) > 80:
            title = title[:80].rstrip()
        return title

    def _sanitize_generated_chat_summary(self, raw_summary: str) -> str:
        summary = re.sub(r'\s+', ' ', str(raw_summary if raw_summary is not None else '')).strip()
        if len(summary) > 220:
            summary = summary[:220].rstrip()
        return summary

    def _queue_agent_chat_metadata_generation(self, chat_idx: int, user_message: str) -> None:
        """Generate chat title + summary after the first user turn for untitled agent chats."""

        if chat_idx < 0 or chat_idx >= len(self.chat_list):
            return
        chat = self.chat_list[chat_idx]
        chat_id, chat_name, analysis_type = chat[0], chat[1], chat[2]
        if not self._is_agent_chat_type(analysis_type):
            return
        if str(chat_name if chat_name is not None else '').strip() != '':
            return
        if self._chat_user_message_count(chat_id) != 1:
            return
        prompt_text = str(user_message if user_message is not None else '').strip()
        if prompt_text == '':
            return
        self.app.ai.start_query(
            self._generate_agent_chat_metadata_worker,
            self.agent_chat_metadata_callback,
            chat_id,
            prompt_text,
            model_kind='fast',
            scope_type='chat_title',
            scope_id=chat_id,
            cancel_result={"chat_id": chat_id, "canceled": True},
        )

    def _generate_agent_chat_metadata_worker(self, chat_id: int, user_message: str, signals=None) -> Dict[str, Any]:
        """Background worker for agent-chat metadata generation."""

        del signals
        response = self._invoke_json_llm(
            [
                SystemMessage(content=self._agent_chat_metadata_system_prompt()),
                HumanMessage(content='First user message:\n' + str(user_message)),
            ],
            schema_name='agent_chat_metadata',
            response_schema=self._agent_chat_metadata_json_schema(),
            context='agent_chat_metadata',
            model_kind='fast',
        )
        return {
            "chat_id": int(chat_id),
            "name": self._sanitize_generated_chat_title(response.get("name", "")),
            "summary": self._sanitize_generated_chat_summary(response.get("summary", "")),
        }

    def agent_chat_metadata_callback(self, result: Dict[str, Any]) -> None:
        """Persist generated chat metadata if the chat is still unnamed."""

        if not isinstance(result, dict) or result.get("canceled", False):
            return
        try:
            chat_id = int(result.get("chat_id", -1))
        except Exception:
            chat_id = -1
        if chat_id < 0:
            return
        generated_name = self._sanitize_generated_chat_title(result.get("name", ""))
        generated_summary = self._sanitize_generated_chat_summary(result.get("summary", ""))
        if generated_name == '' or generated_summary == '':
            return

        cursor = self.chat_history_conn.cursor()
        cursor.execute('SELECT name FROM chats WHERE id = ?', (chat_id,))
        row = cursor.fetchone()
        if row is None:
            return
        existing_name = str(row[0] if row[0] is not None else '').strip()
        if existing_name != '':
            return

        cursor.execute(
            "UPDATE chats SET name = ?, summary = ? "
            "WHERE id = ? AND TRIM(COALESCE(name, '')) = ''",
            (generated_name, generated_summary, chat_id),
        )
        if cursor.rowcount <= 0:
            self.chat_history_conn.rollback()
            return
        self.chat_history_conn.commit()

        row_idx = self.find_chat_idx(chat_id)
        if row_idx is None:
            self.fill_chat_list()
            return
        chat = self.chat_list[row_idx]
        self.chat_list[row_idx] = (chat[0], generated_name, chat[2], generated_summary, chat[4], chat[5])
        self._refresh_chat_list_item(row_idx)
        self._refresh_chat_name_views()
        if row_idx == self.current_chat_idx:
            self.update_chat_window(scroll_to_bottom=False)
    
    def button_question_clicked(self):
        if self._chat_scope_active():
            self._cancel_chat_scope(ask=True)
        else:
            self.send_user_question()
                    
    def send_user_question(self):
        if self.app.settings['ai_enable'] != 'True':
            msg = _('The AI is disabled. Go to "AI > Setup Wizard" first.')
            Message(self.app, _('AI not enabled'), msg, "warning").exec()
            return
        elif self.app.ai.is_busy():
            msg = _('The AI is busy generating a response. Click on the button on the right to stop.')
            Message(self.app, _('AI busy'), msg, "warning").exec()
            return
        elif not self.app.ai.is_ready():
            msg = _('The AI not yet fully loaded. Please wait and retry.')
            Message(self.app, _('AI not ready'), msg, "warning").exec()
            return
        self.ai_output_autoscroll = True
        self._dismiss_prompt_completion(accept=False)
        q = self.ui.plainTextEdit_question.toPlainText()
        if q != '':
            if self.process_message('user', q):
                self.ui.plainTextEdit_question.clear()
                QtWidgets.QApplication.processEvents()
                        
    def process_message(self, msg_type, msg_content, chat_idx=None, db_conn=None, refresh_history=True, commit_history=True) -> bool:
        #if not self.app.ai.is_ready():
        #    msg = _('The AI is busy or not yet fully loaded. Please wait a moment and retry.')
        #    Message(self.app, _('AI not ready'), msg, "warning").exec()
        #    return False
        if chat_idx is None:
            chat_idx = self.current_chat_idx
        if chat_idx <= -1:
            self.ai_streaming_output = ''
            self.chat_msg_list.clear()
            msg = _('Please select a chat or create a new one.')
            Message(self.app, _('Chat selection'), msg, "warning").exec()
            return False
             
        if msg_type == 'info':
            # info messages are only shown on screen, not send to the AI
            self.history_add_message(msg_type, '', msg_content, chat_idx, db_conn=db_conn, refresh=refresh_history, commit=commit_history)
            self.update_chat_window()
        elif msg_type == 'agent_status':
            self.history_add_or_append_agent_status(msg_content, chat_idx)
            if chat_idx == self.current_chat_idx:
                self.update_chat_window()
        elif msg_type == 'system':
            # System messages are hidden from the chat window.
            # Agent chats rebuild their system prompt fresh on every turn, so persisting it is unnecessary.
            # Other chat types still replay the stored system prompt from history.
            analysis_type = ''
            if 0 <= chat_idx < len(self.chat_list):
                analysis_type = self.chat_list[chat_idx][2]
            if not self._is_agent_chat_type(analysis_type):
                self.history_add_message(msg_type, '', msg_content, chat_idx, db_conn=db_conn, refresh=refresh_history, commit=commit_history)
        elif msg_type == 'tool_call':
            # tool messages are persisted for multi-turn MCP context, but not rendered in the chat window
            self.history_add_message(msg_type, 'ai_agent', msg_content, chat_idx, db_conn=db_conn, refresh=refresh_history, commit=commit_history)
        elif msg_type == 'tool_result':
            # tool messages are persisted for multi-turn MCP context, but not rendered in the chat window
            self.history_add_message(msg_type, 'mcp_server', msg_content, chat_idx, db_conn=db_conn, refresh=refresh_history, commit=commit_history)
        elif msg_type == 'single_instruct':
            # single_instruct messages are persisted for audit/logging, but not rendered
            # and not sent again in future turns.
            self.history_add_message(msg_type, 'ai_agent', msg_content, chat_idx, db_conn=db_conn, refresh=refresh_history, commit=commit_history)
        elif msg_type == 'prompt':
            # explicit prompt activations are persisted for future turns, but not rendered
            self.history_add_message(msg_type, '', msg_content, chat_idx, db_conn=db_conn, refresh=refresh_history, commit=commit_history)
        elif msg_type == 'agent_state':
            # compact state memory for future turns (persisted, not rendered)
            self.history_add_message(msg_type, 'ai_agent', msg_content, chat_idx, db_conn=db_conn, refresh=refresh_history, commit=commit_history)
        elif msg_type == 'env_update':
            # synthetic environment events are persisted for later turns, but not rendered
            self.history_add_message(msg_type, 'system_event', msg_content, chat_idx, db_conn=db_conn, refresh=refresh_history, commit=commit_history)
        elif msg_type == 'instruct':
            # instruct messages are only send to the AI, but not shown on screen
            # Other than system messages, instruct messages are send immediatly and will produce an answer that is shown on screen
            if chat_idx == self.current_chat_idx:
                self.history_add_message(msg_type, '', msg_content, chat_idx)
                messages = self.history_get_ai_messages()
                self.current_streaming_chat_idx = self.current_chat_idx
                self._capture_chat_ai_profile_snapshot(chat_idx)
                self.app.ai.start_stream(messages,
                                         result_callback=self.ai_message_callback,
                                         progress_callback=None,
                                         streaming_callback=self.ai_streaming_callback,
                                         error_callback=None,
                                         model_kind='large',
                                         scope_type='chat',
                                         scope_id=chat_idx)
        elif msg_type == 'user':
            # user question, shown on screen and send to the AI
            if chat_idx == self.current_chat_idx:
                self.history_add_message(msg_type, self.app.settings['codername'], msg_content, chat_idx)
                self._queue_agent_chat_metadata_generation(chat_idx, msg_content)
                messages = self.history_get_ai_messages()
                self.current_streaming_chat_idx = self.current_chat_idx
                analysis_type = ''
                if 0 <= chat_idx < len(self.chat_list):
                    analysis_type = self.chat_list[chat_idx][2]
                if self._is_agent_chat_type(analysis_type):
                    self._capture_chat_ai_profile_snapshot(chat_idx)
                    loaded_prompts = self._persist_explicit_agent_prompts(chat_idx, msg_content)
                    if len(loaded_prompts) == 1:
                        status_text = _('Loaded prompt: {name}').format(
                            name='/' + loaded_prompts[0].name
                        )
                        self.process_message(
                            'agent_status',
                            json.dumps({"kind": "prompt", "text": status_text}, ensure_ascii=False),
                            chat_idx,
                        )
                    elif len(loaded_prompts) > 1:
                        status_text = _('Loaded prompts: {names}').format(
                            names=', '.join('/' + prompt.name for prompt in loaded_prompts)
                        )
                        self.process_message(
                            'agent_status',
                            json.dumps({"kind": "prompt", "text": status_text}, ensure_ascii=False),
                            chat_idx,
                        )
                    messages = self.history_get_ai_messages()
                    self.app.ai.start_query(self._mcp_general_chat_worker,
                                            self.ai_mcp_message_callback,
                                            messages,
                                            chat_idx,
                                            progress_callback=self.ai_mcp_progress_callback,
                                            model_kind='large',
                                            scope_type='chat',
                                            scope_id=chat_idx,
                                            cancel_result={
                                                "chat_idx": chat_idx,
                                                "stream_messages": [],
                                                "tool_messages": [],
                                                "canceled": True,
                                                "direct_ai_message": "",
                                            })
                else:
                    self._capture_chat_ai_profile_snapshot(chat_idx)
                    self.app.ai.start_stream(messages,
                                             result_callback=self.ai_message_callback,
                                             progress_callback=None,
                                             streaming_callback=self.ai_streaming_callback,
                                             error_callback=self.ai_error_callback,
                                             model_kind='large',
                                             scope_type='chat',
                                             scope_id=chat_idx)
                self.update_chat_window()
        elif msg_type == 'ai':
            # ai responses.
            # create temporary db connection to make it thread safe
            db_conn = sqlite3.connect(self.chat_history_path)
            try: 
                ai_model_name = self._normalize_ai_profile_author(chat_idx=chat_idx, fallback_to_current=True)
                msg_content = strip_think_blocks(msg_content)
                self.history_add_message(msg_type, ai_model_name, msg_content, chat_idx, db_conn)
                self.ai_streaming_output = ''
                self.update_chat_window()
            finally:
                db_conn.close()
        return True    

    def _mcp_planner_system_prompt(self) -> str:
        return (
            "Your task: Plan the next steps needed to fulfill the user's request. "
            "Return ONLY one JSON object with this shape:\n"
            "{"
            "\"needs_mcp\": true|false, "
            "\"plan_summary\": \"one short user-facing note\", "
            "\"user_decision_required\": true|false, "
            "\"decision_question\": \"optional question\", "
            "\"decision_context\": \"optional short reason\", "
            "\"proposed_next_calls\": [{\"method\": \"resources/list|resources/read|resources/templates/list|initialize|tools/list|tools/call\", \"params\": {}}], "
            "\"calls\": [{\"method\": \"resources/list|resources/read|resources/templates/list|initialize|tools/list|tools/call\", \"params\": {}}], "
            "\"answer_brief\": \"optional draft answer idea\""
            "}\n"
            "Rules:\n"
            "- Allowed methods: initialize, resources/list, resources/templates/list, resources/read, tools/list, tools/call.\n"
            "- The turn already contains initialize, resources/list, and resources/templates/list. Do not repeat them with identical params.\n"
            "- Use as few calls as possible and keep them focused.\n"
            "- If you need any tool and the available tools are not already known from the current conversation context, call tools/list before planning or using tools/call.\n"
            "- Use tools/call only for tools that have already been discovered through tools/list in the current conversation context.\n"
            "- Default to user_decision_required=false.\n"
            "- Set user_decision_required=true only when the global agent rules require a user decision or confirmation.\n"
            "- If user_decision_required=true, provide one concise natural-language question in decision_question, keep calls empty, and put suggested follow-up MCP actions into proposed_next_calls.\n"
            "- If the request is clear and executable, prefer concrete calls.\n"
            "- Reading: Prefer specific reads over broad reads. Reading full empirical documents can be costly. Do this only when it is really needed.\n"
            "- Follow the current tools/list exactly when planning tools/call actions.\n"
            "- If a delete action still needs user confirmation after preview, set user_decision_required=true and keep the execute tool call in proposed_next_calls with the preview_token.\n"
            "- If the conversation contains an Agent state snapshot with pending_user_decision and the latest user message confirms it, execute pending_user_decision.proposed_next_calls now.\n"
            "- If the user explicitly asks to create or change project data now and the action is executable, prioritize execution: set needs_mcp=true and include concrete tools/call write actions in calls.\n"
            "- If the task was about collecting information and you have enough evidence in the conversation history already, initiate the final answer by "
            "setting needs_mcp=false and calls=[].\n"
            "- plan_summary must be one sentence, user-facing, <=160 characters.\n"
            "- Do not output prose outside JSON.\n"
        )

    def _mcp_reflection_system_prompt(self) -> str:
        return (
            "Your task: Review the collected evidence and action progress, then decide whether more MCP calls are needed. "
            "Return ONLY one JSON object with this shape:\n"
            "{"
            "\"enough_information\": true|false, "
            "\"reflection_summary\": \"one short user-facing note\", "
            "\"next_step_note\": \"optional short alias\", "
            "\"continue_deferred_calls\": true|false, "
            "\"user_decision_required\": true|false, "
            "\"decision_question\": \"optional question\", "
            "\"decision_context\": \"optional short reason\", "
            "\"proposed_next_calls\": [{\"method\": \"resources/list|resources/read|resources/templates/list|initialize|tools/list|tools/call\", \"params\": {}}], "
            "\"revised_calls\": [{\"method\": \"resources/list|resources/read|resources/templates/list|initialize|tools/list|tools/call\", \"params\": {}}], "
            "\"answer_brief\": \"short answer plan for final response\""
            "}\n"
            "Rules:\n"
            "- Allowed methods: initialize, resources/list, resources/templates/list, resources/read, tools/list, tools/call.\n"
            "- Initialize, resources/list, and resources/templates/list are already available in context unless explicitly changed.\n"
            "- Use as few additional calls as possible and keep them focused.\n"
            "- If you need any tool and the available tools are not already known from the current conversation context, call tools/list before planning or using tools/call.\n"
            "- Use tools/call only for tools that have already been discovered through tools/list in the current conversation context.\n"
            "- If deferred_calls are listed in the reflection prompt, decide explicitly whether they should continue unchanged by setting continue_deferred_calls=true or false.\n"
            "- If continue_deferred_calls=true, you may keep revised_calls empty to continue the deferred queue unchanged, or provide revised_calls to prepend/adjust the next steps.\n"
            "- Default to user_decision_required=false.\n"
            "- Set user_decision_required=true only when the global agent rules require a user decision or confirmation.\n"
            "- If user_decision_required=true, provide one concise natural-language question in decision_question, keep revised_calls empty, and put suggested follow-up MCP actions into proposed_next_calls.\n"
            "- If the user explicitly requested write actions, include revised_calls that execute the remaining write actions whenever this is possible.\n"
            "- If a delete action still needs user confirmation after preview, set user_decision_required=true and place the execute tool with the preview_token into proposed_next_calls.\n"
            "- Do not stop with explanations only if executable actions are still pending.\n"
            "- If the task was about collecting information and you now have enough evidence for a final answer, set enough_information=true and revised_calls=[].\n"
            "- If more information or actions are still needed, set enough_information=false and propose only the necessary revised_calls.\n"
            "- reflection_summary must be one sentence, user-facing, <=160 characters.\n"
            "- Avoid boilerplate like 'I will' or 'Next step is' unless strictly needed.\n"
            "- next_step_note is optional and only used when reflection_summary is empty.\n"
            "- Do not output prose outside JSON."
        )

    def _mcp_final_answer_system_prompt(self) -> str:
        return (
            "Your task: "
            "Provide a final answer for the user in normal prose based on the conversation and retrieved project context. "
            "Do not output JSON. "
            "Treat MCP execution as already finished for this turn and report outcomes clearly. "
            "Default to a conversational reply and keep it short (about 2–5 sentences), unless the user or an upstream instruction explicitly asks for a longer or more structured answer. "
            "Do not be superficial: if you identify several relevant aspects, go deeper on the most interesting one, then ask which of the others the user would like to explore next. "
            "You can use Markdown formatting like bullet points if that helps to keep the answer concise and clear. "
            "If you have made changes to project data through tool calls, give a short and concise summary of what you have done, but avoid repeating information discussed before. "
            "If the user asked for an execution but it could not be completed, state exactly what is missing and ask one concise follow-up question. "
            "Do not claim that tool use is forbidden unless the user explicitly said so. "
            "If information is missing, state that briefly and avoid making up details. "
            "Do not make empirical claims without support from retrieved evidence. If a claim is not supported strongly enough, state the uncertainty instead of inventing support. "            
            "When you refer to empirical text evidence, add citations in this exact form: "
            "{REF: \"exact quote from the retrieved evidence\"}. "
            "The quote inside REF must be copied exactly from retrieved evidence (no paraphrasing, no corrections, no translation). "
            "Important: REF is machine markup and the quote text inside REF is not shown as normal readable text to the user. "
            "If you want a direct quote to be visible, write the quote explicitly in normal prose and add REF separately. "
        )

    def _run_mcp_request(self, method: str, params: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
        request = {
            "jsonrpc": "2.0",
            "id": self.ai_mcp_server.new_request_id(),
            "method": method,
            "params": params,
        }
        response = self.ai_mcp_server.handle_request(request)
        return request, response

    def _compact_mcp_result_content(self, method_name: str, method_params: Dict[str, Any],
                                    rpc_response: Dict[str, Any]) -> str:
        """Return a compact MCP result payload for conversation history."""

        compact: Dict[str, Any] = {
            "action": "mcp_result",
            "method": str(method_name).strip(),
        }
        if not isinstance(rpc_response, dict):
            compact["error"] = {"message": _("Invalid MCP response.")}
            return "MCP result:\n" + json.dumps(compact, ensure_ascii=False)

        error_payload = rpc_response.get("error", None)
        if isinstance(error_payload, dict):
            compact["error"] = error_payload
            return "MCP result:\n" + json.dumps(compact, ensure_ascii=False)

        result_payload = rpc_response.get("result", None)
        if not isinstance(result_payload, dict):
            compact["result"] = result_payload
            return "MCP result:\n" + json.dumps(compact, ensure_ascii=False)

        if method_name == "resources/read":
            compact["requested_uri"] = str(method_params.get("uri", "")).strip()
            compact_contents: List[Dict[str, Any]] = []
            raw_contents = result_payload.get("contents", [])
            if isinstance(raw_contents, list):
                for item in raw_contents:
                    if not isinstance(item, dict):
                        continue
                    compact_item: Dict[str, Any] = {}
                    uri = str(item.get("uri", "")).strip()
                    if uri != "":
                        compact_item["uri"] = uri
                    text_blob = item.get("text", None)
                    if isinstance(text_blob, str) and text_blob.strip() != "":
                        try:
                            parsed_payload = json.loads(text_blob)
                        except Exception:
                            compact_item["text"] = text_blob
                        else:
                            compact_item["payload"] = parsed_payload
                    blob_value = item.get("blob", None)
                    if "payload" not in compact_item and "text" not in compact_item and blob_value is not None:
                        compact_item["blob"] = blob_value
                    if len(compact_item) > 0:
                        compact_contents.append(compact_item)
            compact["contents"] = compact_contents
            return "MCP result:\n" + json.dumps(compact, ensure_ascii=False)

        if method_name == "tools/call":
            compact["tool"] = str(method_params.get("name", "")).strip()
            compact["isError"] = bool(result_payload.get("isError", False))
            if "structuredContent" in result_payload:
                compact["payload"] = result_payload.get("structuredContent")
            elif "content" in result_payload:
                compact["result"] = result_payload.get("content")
            else:
                compact["result"] = result_payload
            return "MCP result:\n" + json.dumps(compact, ensure_ascii=False)

        compact["result"] = result_payload
        return "MCP result:\n" + json.dumps(compact, ensure_ascii=False)

    def _begin_ai_change_set(self, messages: List[Any], chat_idx: int) -> str:
        """Delegate AI change-set creation to the AI service."""
        ai = getattr(self.app, "ai", None)
        if ai is None:
            return ""
        return ai.begin_ai_change_set(messages, chat_idx)

    def _discard_empty_ai_change_set(self, set_id: str) -> None:
        """Delegate AI change-set cleanup to the AI service."""
        ai = getattr(self.app, "ai", None)
        if ai is None:
            return
        ai.discard_empty_ai_change_set(set_id)

    def _mcp_allowed_call_json_schema(self) -> Dict[str, Any]:
        """JSON schema for allowed MCP calls in planner/reflection outputs."""

        list_params = {
            "type": "object",
            "properties": {
                "cursor": {"type": "string"},
            },
            "additionalProperties": False,
        }
        empty_params = {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
        read_params = {
            "type": "object",
            "properties": {
                "uri": {"type": "string"},
                "start": {"type": ["integer", "number", "string"]},
                "length": {"type": ["integer", "number", "string"]},
            },
            "required": ["uri"],
            "additionalProperties": False,
        }
        tool_list_params = {
            "type": "object",
            "properties": {
                "cursor": {"type": "string"},
            },
            "additionalProperties": False,
        }
        tool_call_params = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "arguments": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": True,
                },
                "_ai_change_set_id": {"type": "string"},
            },
            "required": ["name", "arguments"],
            "additionalProperties": False,
        }
        return {
            "type": "object",
            "oneOf": [
                {
                    "type": "object",
                    "properties": {
                        "method": {"const": "initialize"},
                        "params": empty_params,
                    },
                    "required": ["method", "params"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {
                        "method": {"const": "resources/list"},
                        "params": list_params,
                    },
                    "required": ["method", "params"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {
                        "method": {"const": "resources/templates/list"},
                        "params": list_params,
                    },
                    "required": ["method", "params"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {
                        "method": {"const": "resources/read"},
                        "params": read_params,
                    },
                    "required": ["method", "params"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {
                        "method": {"const": "tools/list"},
                        "params": tool_list_params,
                    },
                    "required": ["method", "params"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {
                        "method": {"const": "tools/call"},
                        "params": tool_call_params,
                    },
                    "required": ["method", "params"],
                    "additionalProperties": False,
                },
            ],
            "additionalProperties": False,
        }

    def _mcp_planner_json_schema(self) -> Dict[str, Any]:
        """JSON schema for the MCP planner control response."""

        call_schema = self._mcp_allowed_call_json_schema()
        return {
            "type": "object",
            "properties": {
                "needs_mcp": {"type": "boolean"},
                "plan_summary": {"type": "string"},
                "user_decision_required": {"type": "boolean"},
                "decision_question": {"type": "string"},
                "decision_context": {"type": "string"},
                "proposed_next_calls": {"type": "array", "items": call_schema},
                "calls": {"type": "array", "items": call_schema},
                "answer_brief": {"type": "string"},
            },
            "required": [
                "needs_mcp",
                "plan_summary",
                "user_decision_required",
                "decision_question",
                "decision_context",
                "proposed_next_calls",
                "calls",
                "answer_brief",
            ],
            "additionalProperties": False,
        }

    def _mcp_reflection_json_schema(self) -> Dict[str, Any]:
        """JSON schema for the MCP reflection control response."""

        call_schema = self._mcp_allowed_call_json_schema()
        return {
            "type": "object",
            "properties": {
                "enough_information": {"type": "boolean"},
                "reflection_summary": {"type": "string"},
                "next_step_note": {"type": "string"},
                "continue_deferred_calls": {"type": "boolean"},
                "user_decision_required": {"type": "boolean"},
                "decision_question": {"type": "string"},
                "decision_context": {"type": "string"},
                "proposed_next_calls": {"type": "array", "items": call_schema},
                "revised_calls": {"type": "array", "items": call_schema},
                "answer_brief": {"type": "string"},
            },
            "required": [
                "enough_information",
                "reflection_summary",
                "next_step_note",
                "continue_deferred_calls",
                "user_decision_required",
                "decision_question",
                "decision_context",
                "proposed_next_calls",
                "revised_calls",
                "answer_brief",
            ],
            "additionalProperties": False,
        }

    def _invoke_json_llm(self, messages: List[Any], schema_name: str = '',
                         response_schema: Optional[Dict[str, Any]] = None,
                         context: str = 'mcp_json_control',
                         model_kind: str = 'large',
                         run_context=None) -> Dict[str, Any]:
        """Invoke model and parse one JSON object response."""

        response_format = None
        if response_schema is not None:
            name = str(schema_name).strip()
            if name != "":
                response_format = self.app.ai.get_response_format_json_schema(name, response_schema)

        llm_response = self.app.ai.invoke_with_logging(
            messages,
            response_format=response_format,
            context=context,
            fallback_without_response_format=True,
            model_kind=model_kind,
            run_context=run_context,
        )
        raw = strip_think_blocks(str(llm_response.content)).strip()
        raw = self._extract_first_json_object(raw)
        if raw == "":
            return {}
        try:
            data = json.loads(raw)
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        return data

    def _internal_json_step_timeouts(self) -> Tuple[float, float]:
        """Return soft/hard wall-clock timeouts for planner-like JSON steps."""

        ai_service = getattr(self.app, 'ai', None)
        if ai_service is None:
            read_timeout = float(self.app.settings.get('ai_timeout', '30.0'))
        else:
            timeout_obj = ai_service._run_timeout('large', 'invoke')
            read_timeout = float(getattr(timeout_obj, 'read', self.app.settings.get('ai_timeout', '30.0')))
        soft_timeout = max(1.0, 0.7 * read_timeout)
        hard_timeout = read_timeout + 60.0
        return soft_timeout, hard_timeout

    def _invoke_json_llm_with_step_timeout(self, messages: List[Any], schema_name: str = '',
                                           response_schema: Optional[Dict[str, Any]] = None,
                                           context: str = 'mcp_json_control',
                                           model_kind: str = 'large',
                                           step_name: str = '',
                                           status_kind: str = '',
                                           signals=None, chat_idx: int = -1) -> Dict[str, Any]:
        """Run one internal JSON LLM step with a visible soft timeout and a hard wall-clock timeout."""

        ai_service = getattr(self.app, 'ai', None)
        if ai_service is None:
            return self._invoke_json_llm(
                messages,
                schema_name=schema_name,
                response_schema=response_schema,
                context=context,
                model_kind=model_kind,
            )

        parent_context = ai_service._get_current_run_context()
        parent_run_id = str(getattr(parent_context, 'run_id', '')).strip()
        run_context = ai_service._create_run_context(
            model_kind=model_kind,
            purpose='invoke',
            scope_type='chat_internal_json',
            scope_id=chat_idx,
            group_id=parent_run_id,
            parent_run_id=parent_run_id,
        )
        run_context.worker_type = 'internal_json_step'
        ai_service._register_run_context(run_context)

        result_holder: Dict[str, Any] = {}
        error_holder: Dict[str, Exception] = {}
        finished = threading.Event()

        def _runner():
            ai_service._set_current_run_context(run_context)
            ai_service._update_run_status(run_context.run_id, 'running')
            try:
                result_holder["data"] = self._invoke_json_llm(
                    messages,
                    schema_name=schema_name,
                    response_schema=response_schema,
                    context=context,
                    model_kind=model_kind,
                    run_context=run_context,
                )
            except Exception as err:
                error_holder["error"] = err
                ai_service._update_run_status(run_context.run_id, 'errored', str(err))
            finally:
                terminal_status = 'canceled' if run_context.cancel_event.is_set() else (
                    'errored' if run_context.error_text != '' else 'finished'
                )
                ai_service._finalize_run_context(run_context, terminal_status)
                ai_service._clear_current_run_context()
                finished.set()

        thread = threading.Thread(
            target=_runner,
            name=f'qualcoder-json-step-{context}',
            daemon=True,
        )
        thread.start()

        soft_timeout, hard_timeout = self._internal_json_step_timeouts()
        step_label = str(step_name).strip() or _("Internal step")
        soft_notice_sent = False
        start_time = time.monotonic()

        while not finished.wait(0.2):
            if ai_service.is_current_run_canceled():
                ai_service._request_cancel_run(run_context)
                thread.join(1.0)
                raise AICancelled(parent_run_id if parent_run_id != '' else run_context.run_id)

            elapsed = time.monotonic() - start_time
            if not soft_notice_sent and elapsed >= soft_timeout:
                soft_notice_sent = True
                self._emit_mcp_status_text(
                    signals,
                    chat_idx,
                    _('{step} is taking longer than expected...').format(step=step_label),
                    status_kind=status_kind,
                )

            if elapsed >= hard_timeout:
                ai_service._request_cancel_run(run_context)
                thread.join(2.0)
                raise TimeoutError(step_label)

        if "error" in error_holder:
            raise error_holder["error"]
        return result_holder.get("data", {})

    def _extract_first_json_object(self, text: str) -> str:
        """Extract the first complete JSON object from mixed model output text."""

        raw = str(text if text is not None else "").strip()
        if raw == "":
            return ""
        if raw.startswith("{") and raw.endswith("}"):
            return raw

        start = -1
        depth = 0
        in_string = False
        escaped = False

        for idx, ch in enumerate(raw):
            if start < 0:
                if ch == "{":
                    start = idx
                    depth = 1
                continue

            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == "\"":
                    in_string = False
                continue

            if ch == "\"":
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return raw[start:idx + 1].strip()
        return ""

    def _is_internal_control_json_payload(self, data: Any) -> bool:
        """Return True if a parsed JSON object looks like leaked internal control output."""

        if not isinstance(data, dict) or len(data) == 0:
            return False

        normalized_keys = {str(key).strip() for key in data.keys()}
        control_keys = {
            "action",
            "method",
            "params",
            "needs_mcp",
            "calls",
            "revised_calls",
            "proposed_next_calls",
            "enough_information",
            "user_decision_required",
            "decision_question",
            "decision_context",
            "answer_brief",
            "plan_summary",
            "reflection_summary",
            "continue_deferred_calls",
            "pending_calls",
            "stop_reason",
        }
        if len(normalized_keys.intersection(control_keys)) == 0:
            return False

        action = str(data.get("action", "")).strip().lower()
        method = str(data.get("method", "")).strip().lower()
        if action == "mcp_call":
            return True
        if method.startswith("tools/") or method.startswith("resources/"):
            return True
        if "params" in data and "method" in data:
            return True
        return True

    def _is_invalid_final_output(self, text: str) -> bool:
        """Detect leaked planner/reflection JSON in a supposedly user-facing final answer."""

        raw = strip_think_blocks(str(text if text is not None else "")).strip()
        if raw == "":
            return False
        json_text = self._extract_first_json_object(raw)
        if json_text == "":
            return False
        try:
            data = json.loads(json_text)
        except Exception:
            return False
        return self._is_internal_control_json_payload(data)

    def _get_latest_user_message_text(self, chat_idx: int) -> str:
        """Return the latest persisted user message for one chat."""

        if chat_idx == self.current_chat_idx and isinstance(self.chat_msg_list, list):
            for msg in reversed(self.chat_msg_list):
                if len(msg) >= 5 and str(msg[2]) == 'user':
                    return str(msg[4] if msg[4] is not None else '').strip()

        if chat_idx < 0 or chat_idx >= len(self.chat_list):
            return ''

        db_conn = sqlite3.connect(self.chat_history_path)
        try:
            cursor = db_conn.cursor()
            cursor.execute(
                "SELECT msg_content FROM chat_messages WHERE chat_id=? AND msg_type='user' ORDER BY id DESC LIMIT 1",
                (int(self.chat_list[chat_idx][0]),),
            )
            row = cursor.fetchone()
            if row is None or row[0] is None:
                return ''
            return str(row[0]).strip()
        finally:
            db_conn.close()

    def _repair_invalid_final_output(self, invalid_text: str, chat_idx: int) -> str:
        """Attempt one repair pass when the final answer leaked internal control JSON."""

        ai_service = getattr(self.app, 'ai', None)
        if ai_service is None:
            return ''

        latest_user_message = self._get_latest_user_message_text(chat_idx)
        current_language = str(ai_service.get_curr_language()).strip()
        system_prompt = (
            "You repair invalid final answers from an AI agent. "
            "Rewrite the invalid output as one normal user-facing answer in the current conversation language. "
            "Do not output JSON. "
            "Do not output code fences. "
            "Do not mention MCP, internal planning fields, method names, params, or tool calls. "
            "Do not invent new empirical findings. "
            "If the invalid output is only an internal control action and does not support a proper final answer, "
            "say so briefly and naturally, without exposing internal JSON or field names."
        )
        repair_prompt = (
            f'Current conversation language: "{current_language}".\n'
            f'Latest user request:\n{latest_user_message}\n\n'
            f'Invalid final output:\n{invalid_text}\n\n'
            'Rewrite this now as a normal user-facing answer only.'
        )
        messages: List[Any] = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=repair_prompt),
        ]
        try:
            repaired = ai_service.invoke_with_logging(
                messages,
                context='final_answer_repair',
                fallback_without_response_format=False,
                model_kind='large',
            )
            return strip_think_blocks(str(repaired.content if repaired is not None else '')).strip()
        except Exception as err:
            logger.warning("Final answer repair failed: %s", err)
            return ''

    def _normalize_mcp_calls(self, raw_calls: Any, allowed_methods: set[str],
                             max_calls: Optional[int] = None) -> List[Dict[str, Any]]:
        """Validate and clamp model-proposed MCP calls."""

        normalized: List[Dict[str, Any]] = []
        if not isinstance(raw_calls, list):
            return normalized
        for item in raw_calls:
            if max_calls is not None and max_calls > 0 and len(normalized) >= max_calls:
                break
            if not isinstance(item, dict):
                continue
            method = str(item.get("method", "")).strip()
            if method not in allowed_methods:
                continue
            params = item.get("params", {})
            if not isinstance(params, dict):
                params = {}
            normalized.append({"method": method, "params": params})
        return normalized

    def _merge_mcp_call_lists(self, primary_calls: List[Dict[str, Any]],
                              secondary_calls: List[Dict[str, Any]],
                              max_calls: Optional[int] = None) -> List[Dict[str, Any]]:
        """Merge two MCP call lists while preserving order and removing duplicates."""

        merged: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for call_list in (primary_calls, secondary_calls):
            for call in call_list:
                if not isinstance(call, dict):
                    continue
                method = str(call.get("method", "")).strip()
                params = call.get("params", {})
                if not isinstance(params, dict):
                    params = {}
                key = self._mcp_call_key(method, params)
                if key in seen:
                    continue
                seen.add(key)
                merged.append({"method": method, "params": params})
                if max_calls is not None and max_calls > 0 and len(merged) >= max_calls:
                    return merged
        return merged

    def _split_mcp_call_queue(self, calls: List[Dict[str, Any]], round_limit: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Split queued MCP calls into this round and deferred remainder."""

        if round_limit <= 0:
            return [], list(calls)
        current_round = list(calls[:round_limit])
        deferred = list(calls[round_limit:])
        return current_round, deferred

    def _json_bool(self, value: Any, default: bool) -> bool:
        """Parse relaxed JSON boolean-like values."""

        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            text = value.strip().lower()
            if text in ("true", "1", "yes"):
                return True
            if text in ("false", "0", "no", ""):
                return False
        return default

    def _mcp_call_key(self, method: str, params: Dict[str, Any]) -> str:
        try:
            params_key = json.dumps(params, sort_keys=True, ensure_ascii=False)
        except Exception:
            params_key = str(params)
        return method + "|" + params_key

    def _emit_mcp_status(self, signals, chat_idx: int, status_text: str):
        status_msg = self._normalize_progress_note(status_text)
        if status_msg == '':
            return
        if signals is None or signals.progress is None:
            return
        payload = {"chat_idx": chat_idx, "status": status_msg}
        signals.progress.emit(json.dumps(payload, ensure_ascii=False))

    def _normalize_progress_note(self, text: Any, max_length: int = 220) -> str:
        """Normalize model progress notes for compact UI display."""

        note = str(text if text is not None else "").replace("\r", " ").replace("\n", " ")
        note = " ".join(note.split()).strip()
        if note == "":
            return ""
        if len(note) > max_length:
            note = note[: max_length - 3].rstrip() + "..."
        return note

    def _emit_mcp_status_text(self, signals, chat_idx: int, status_text: str, status_kind: str = ""):
        """Emit one free-text MCP progress line."""

        status = self._normalize_progress_note(status_text)
        if status == "":
            return
        if signals is None or signals.progress is None:
            return
        payload = {"chat_idx": chat_idx, "status": status, "status_kind": str(status_kind).strip()}
        signals.progress.emit(json.dumps(payload, ensure_ascii=False))

    def _short_reflection_next_step_note(self, reflection_summary: str,
                                         model_next_step_note: str) -> str:
        """Keep reflection content, only shorten/format it for UI display."""

        candidate = self._normalize_progress_note(reflection_summary, max_length=1000)
        if candidate == "":
            candidate = self._normalize_progress_note(model_next_step_note, max_length=1000)
        if candidate == "":
            return ""

        max_length = 160
        if len(candidate) <= max_length:
            return candidate

        # Prefer a full sentence boundary before hard truncation.
        sentence_end = max(candidate.rfind("." , 0, max_length),
                           candidate.rfind("!", 0, max_length),
                           candidate.rfind("?", 0, max_length))
        if sentence_end >= 40:
            return candidate[: sentence_end + 1].strip()
        return self._normalize_progress_note(candidate, max_length=max_length)

    def _safe_int(self, value: Any, default: int = -1) -> int:
        try:
            if value is None or isinstance(value, bool):
                return default
            return int(value)
        except Exception:
            return default

    def _tool_result_messages_for_chat(self, chat_idx: Optional[int]) -> List[str]:
        """Return raw tool_result message contents for one chat."""

        if chat_idx is None:
            chat_idx = self.current_chat_idx
        if chat_idx is None or chat_idx < 0 or chat_idx >= len(self.chat_list):
            return []
        curr_chat_id = self.chat_list[chat_idx][0]
        cursor = self.chat_history_conn.cursor()
        cursor.execute(
            "SELECT msg_content FROM chat_messages WHERE chat_id=? AND msg_type='tool_result' ORDER BY id",
            (curr_chat_id,),
        )
        rows = cursor.fetchall()
        return [str(row[0]) for row in rows if isinstance(row, tuple) and len(row) > 0 and row[0] is not None]

    def _extract_ref_candidates_from_tool_result(self, tool_result_raw: str) -> List[Dict[str, Any]]:
        """Extract evidence spans from one persisted MCP tool_result message."""

        if not isinstance(tool_result_raw, str):
            return []
        raw_text = tool_result_raw
        if raw_text.startswith("MCP result:\n"):
            raw_text = raw_text[len("MCP result:\n"):]
        elif raw_text.startswith("MCP response:\n"):
            raw_text = raw_text[len("MCP response:\n"):]
        else:
            return []
        try:
            stored_payload = json.loads(raw_text)
        except Exception:
            return []
        if not isinstance(stored_payload, dict):
            return []

        if str(stored_payload.get("action", "")).strip() == "mcp_result":
            contents = stored_payload.get("contents", [])
        else:
            result = stored_payload.get("result", {})
            if not isinstance(result, dict):
                return []
            contents = result.get("contents", [])
        if not isinstance(contents, list):
            return []

        candidates: List[Dict[str, Any]] = []
        for content in contents:
            if not isinstance(content, dict):
                continue
            uri = str(content.get("uri", "")).split("?", 1)[0]
            payload = content.get("payload", None)
            if not isinstance(payload, dict):
                text_blob = content.get("text", None)
                if not isinstance(text_blob, str) or text_blob.strip() == "":
                    continue
                try:
                    payload = json.loads(text_blob)
                except Exception:
                    continue
            if not isinstance(payload, dict):
                continue

            if re.fullmatch(r"qualcoder://codes/segments/\d+", uri):
                segments = payload.get("segments", [])
                if not isinstance(segments, list):
                    continue
                for seg in segments:
                    if not isinstance(seg, dict):
                        continue
                    source_id = self._safe_int(seg.get("fid", None), -1)
                    start = self._safe_int(seg.get("pos0", None), -1)
                    quote = str(seg.get("quote", ""))
                    if source_id <= 0 or start < 0 or quote.strip() == "":
                        continue
                    source_name = str(seg.get("source_name", "")).strip()
                    if source_name == "":
                        source_name = self.get_filename(source_id)
                    candidates.append(
                        {
                            "source_id": source_id,
                            "source_name": source_name,
                            "start": start,
                            "length": len(quote),
                            "text": quote,
                        }
                    )
                continue

            if re.fullmatch(r"qualcoder://documents/text/\d+", uri):
                source_id = self._safe_int(payload.get("id", None), -1)
                start = self._safe_int(payload.get("start", None), -1)
                excerpt = str(payload.get("text", ""))
                if source_id <= 0 or start < 0 or excerpt.strip() == "":
                    continue
                source_name = str(payload.get("name", "")).strip()
                if source_name == "":
                    source_name = self.get_filename(source_id)
                candidates.append(
                    {
                        "source_id": source_id,
                        "source_name": source_name,
                        "start": start,
                        "length": len(excerpt),
                        "text": excerpt,
                    }
                )
                continue

            if uri == "qualcoder://vector/search":
                hits = payload.get("hits", [])
                if not isinstance(hits, list):
                    continue
                for hit in hits:
                    if not isinstance(hit, dict):
                        continue
                    source_id = self._safe_int(hit.get("source_id", None), -1)
                    start = self._safe_int(hit.get("start", None), -1)
                    excerpt = str(hit.get("text", ""))
                    if source_id <= 0 or start < 0 or excerpt.strip() == "":
                        continue
                    source_name = str(hit.get("source_name", "")).strip()
                    if source_name == "":
                        source_name = self.get_filename(source_id)
                    candidates.append(
                        {
                            "source_id": source_id,
                            "source_name": source_name,
                            "start": start,
                            "length": len(excerpt),
                            "text": excerpt,
                        }
                    )
                continue

            if uri == "qualcoder://search/bm25":
                hits = payload.get("hits", [])
                if not isinstance(hits, list):
                    continue
                for hit in hits:
                    if not isinstance(hit, dict):
                        continue
                    source_id = self._safe_int(hit.get("source_id", None), -1)
                    start = self._safe_int(hit.get("start", None), -1)
                    excerpt = str(hit.get("text", ""))
                    if source_id <= 0 or start < 0 or excerpt.strip() == "":
                        continue
                    source_name = str(hit.get("source_name", "")).strip()
                    if source_name == "":
                        source_name = self.get_filename(source_id)
                    candidates.append(
                        {
                            "source_id": source_id,
                            "source_name": source_name,
                            "start": start,
                            "length": len(excerpt),
                            "text": excerpt,
                        }
                    )
                continue

            if uri == "qualcoder://search/regex":
                hits = payload.get("hits", [])
                if not isinstance(hits, list):
                    continue
                for hit in hits:
                    if not isinstance(hit, dict):
                        continue
                    source_id = self._safe_int(hit.get("source_id", None), -1)
                    start = self._safe_int(hit.get("start", None), -1)
                    excerpt = str(hit.get("text", ""))
                    if source_id <= 0 or start < 0 or excerpt.strip() == "":
                        continue
                    source_name = str(hit.get("source_name", "")).strip()
                    if source_name == "":
                        source_name = self.get_filename(source_id)
                    candidates.append(
                        {
                            "source_id": source_id,
                            "source_name": source_name,
                            "start": start,
                            "length": len(excerpt),
                            "text": excerpt,
                        }
                    )
        return candidates

    def _collect_ref_candidates(self, chat_idx: Optional[int]) -> List[Dict[str, Any]]:
        """Collect deduplicated empirical evidence spans from MCP tool results."""

        tool_results = self._tool_result_messages_for_chat(chat_idx)
        candidates: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for raw in tool_results:
            for item in self._extract_ref_candidates_from_tool_result(raw):
                source_id = self._safe_int(item.get("source_id", None), -1)
                start = self._safe_int(item.get("start", None), -1)
                text = str(item.get("text", ""))
                key = f"{source_id}|{start}|{len(text)}|{text[:120]}"
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(item)
        return candidates

    def _resolve_ref_quote_to_anchor(self, quote: str, candidates: List[Dict[str, Any]]) -> str:
        """Resolve one exact/fuzzy quote to a quote: anchor."""

        quote_text = str(quote if quote is not None else "").strip()
        if quote_text == "":
            return _('(unknown reference)')

        best_candidate: Optional[Dict[str, Any]] = None
        best_local_start = -1
        best_local_end = -1

        for item in candidates:
            segment_text = str(item.get("text", ""))
            local_start = segment_text.find(quote_text)
            if local_start > -1:
                best_candidate = item
                best_local_start = local_start
                best_local_end = local_start + len(quote_text)
                break

        if best_candidate is None:
            for item in candidates:
                segment_text = str(item.get("text", ""))
                local_start, local_end = ai_quote_search(quote_text, segment_text)
                if local_start > -1 < local_end:
                    best_candidate = item
                    best_local_start = local_start
                    best_local_end = local_end
                    break

        if best_candidate is None:
            print(quote_text)
            return _('(unknown reference)')

        source_id = self._safe_int(best_candidate.get("source_id", None), -1)
        span_start = self._safe_int(best_candidate.get("start", None), -1)
        source_name = str(best_candidate.get("source_name", "")).strip()
        if source_name == "":
            source_name = self.get_filename(source_id)
        if source_id <= 0 or span_start < 0:
            return _('(unknown reference)')

        abs_start = span_start + best_local_start
        fulltext = self.app.get_text_fulltext(source_id)
        if fulltext is None:
            return _('(unknown reference)')
        full_len = len(fulltext)
        if full_len <= 0:
            return _('(unknown reference)')
        if abs_start < 0:
            abs_start = 0
        if abs_start >= full_len:
            return _('(unknown reference)')

        abs_end = abs_start + max(1, best_local_end - best_local_start)
        if abs_end > full_len:
            abs_end = full_len
        if abs_end <= abs_start:
            abs_end = min(full_len, abs_start + 1)
            if abs_end <= abs_start:
                return _('(unknown reference)')
        abs_len = abs_end - abs_start

        line_start, line_end = self.app.get_line_numbers(fulltext, abs_start, abs_end)
        if line_start > 0 and line_end > 0:
            if line_start == line_end:
                label = f"{source_name}: {line_start}"
            else:
                label = f"{source_name}: {line_start} - {line_end}"
        else:
            label = source_name if source_name != "" else str(source_id)
        return f'(<a href="quote:{source_id}_{abs_start}_{abs_len}">{label}</a>)'

    def _mcp_general_chat_worker(self, messages: List[Any], chat_idx: int,
                                 bootstrap_calls_extra: Optional[List[Tuple[str, Dict[str, Any]]]] = None,
                                 signals=None) -> Dict[str, Any]:
        """Background worker: staged agent flow with MCP resource access."""

        result: Dict[str, Any] = {
            "chat_idx": chat_idx,
            "stream_messages": [],
            "tool_messages": [],
            "canceled": False,
            "direct_ai_message": "",
        }
        allowed_methods = {
            "initialize",
            "resources/list",
            "resources/templates/list",
            "resources/read",
            "tools/list",
            "tools/call",
        }

        ai_change_set_id = ""
        try:
            history_messages: List[Any] = list(messages)
            agent_messages: List[Any] = [msg for msg in history_messages if not isinstance(msg, SystemMessage)]
            mcp_base_system_prompt = self._mcp_base_system_prompt()
            ai_change_set_id = self._begin_ai_change_set(history_messages, chat_idx)
            final_hint = ''
            tool_messages: List[Dict[str, str]] = []
            tool_messages_streamed = signals is not None and getattr(signals, "progress", None) is not None
            bootstrap_calls: List[Tuple[str, Dict[str, Any]]] = [
                ("initialize", {}),
                ("resources/list", {}),
                ("resources/templates/list", {}),
            ]
            if isinstance(bootstrap_calls_extra, list):
                for item in bootstrap_calls_extra:
                    if not isinstance(item, tuple) or len(item) != 2:
                        continue
                    bootstrap_calls.append((str(item[0]).strip(), dict(item[1]) if isinstance(item[1], dict) else {}))
            planner_json_schema = self._mcp_planner_json_schema()
            reflection_json_schema = self._mcp_reflection_json_schema()
            max_calls_per_round = 8
            max_reflection_rounds = 4
            max_total_tool_calls = 20 + len(bootstrap_calls)
            max_queued_calls = 100
            total_tool_calls = 0
            stop_reason = ""
            def _prepare_mcp_request(method_name: str, raw_params: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
                request_params = dict(raw_params) if isinstance(raw_params, dict) else {}
                display_params = dict(request_params)
                if method_name == "tools/call" and ai_change_set_id != "":
                    request_params["_ai_change_set_id"] = ai_change_set_id
                return request_params, display_params

            def append_tool_exchange(method_name: str, method_params: Dict[str, Any], rpc_response: Dict[str, Any]):
                call_content = json.dumps(
                    {"action": "mcp_call", "method": method_name, "params": method_params},
                    ensure_ascii=False,
                )
                result_content = self._compact_mcp_result_content(method_name, method_params, rpc_response)
                agent_messages.append(AIMessage(content=call_content))
                agent_messages.append(HumanMessage(content=result_content))
                if tool_messages_streamed:
                    payload_call = {
                        "chat_idx": chat_idx,
                        "msg_type": "tool_call",
                        "msg_author": "ai_agent",
                        "msg_content": call_content,
                    }
                    signals.progress.emit(json.dumps(payload_call, ensure_ascii=False))
                    payload_result = {
                        "chat_idx": chat_idx,
                        "msg_type": "tool_result",
                        "msg_author": "mcp_server",
                        "msg_content": result_content,
                    }
                    signals.progress.emit(json.dumps(payload_result, ensure_ascii=False))
                else:
                    tool_messages.append({"msg_type": "tool_call", "msg_author": "ai_agent", "msg_content": call_content})
                    tool_messages.append({"msg_type": "tool_result", "msg_author": "mcp_server", "msg_content": result_content})

            def append_single_instruct_log(phase: str, role: str, content: str):
                payload = json.dumps(
                    {"phase": phase, "role": role, "content": content},
                    ensure_ascii=False,
                )
                if tool_messages_streamed:
                    progress_payload = {
                        "chat_idx": chat_idx,
                        "msg_type": "single_instruct",
                        "msg_author": "ai_agent",
                        "msg_content": payload,
                    }
                    signals.progress.emit(json.dumps(progress_payload, ensure_ascii=False))
                else:
                    tool_messages.append({"msg_type": "single_instruct", "msg_author": "ai_agent", "msg_content": payload})

            def build_phase_request_message(phase_contract: str, trailing_instruction: str) -> HumanMessage:
                parts: List[str] = []
                phase_text = str(phase_contract if phase_contract is not None else "").strip()
                trailing_text = str(trailing_instruction if trailing_instruction is not None else "").strip()
                if phase_text != "":
                    parts.append(phase_text)
                if trailing_text != "":
                    parts.append(trailing_text)
                return HumanMessage(content="\n\n".join(parts).strip())

            def build_phase_messages(phase_contract: str, trailing_instruction: str) -> List[Any]:
                phase_messages: List[Any] = []
                if mcp_base_system_prompt != "":
                    phase_messages.append(SystemMessage(content=mcp_base_system_prompt))
                phase_messages.extend(agent_messages)
                phase_messages.append(build_phase_request_message(phase_contract, trailing_instruction))
                return phase_messages

            # Ensure baseline environment context exists before planning.
            for method, params in bootstrap_calls:
                if self.app.ai.is_current_run_canceled():
                    result["canceled"] = True
                    return result
                request_params, display_params = _prepare_mcp_request(method, params)
                status_text = self.ai_mcp_server.describe_status_event(method, request_params)
                self._emit_mcp_status(signals, chat_idx, status_text)
                _request, response = self._run_mcp_request(method, request_params)
                total_tool_calls += 1
                append_tool_exchange(method, display_params, response)

            planner_system_prompt = self._build_mcp_combined_system_prompt(self._mcp_planner_system_prompt())
            planner_user_prompt = "Create the initial MCP plan now."
            append_single_instruct_log(
                "planning",
                "user",
                build_phase_request_message(planner_system_prompt, planner_user_prompt).content,
            )
            self._emit_mcp_status_text(signals, chat_idx, _("Working..."), status_kind="planning")
            planner_messages = build_phase_messages(planner_system_prompt, planner_user_prompt)
            try:
                plan_data = self._invoke_json_llm_with_step_timeout(
                    planner_messages,
                    schema_name='mcp_planner_control',
                    response_schema=planner_json_schema,
                    context='mcp_json_planner',
                    step_name=_("Internal planning"),
                    status_kind="planning",
                    signals=signals,
                    chat_idx=chat_idx,
                )
            except TimeoutError:
                timeout_msg = _('Internal planning timed out. Please try again.')
                self._emit_mcp_status_text(signals, chat_idx, timeout_msg, status_kind="planning")
                result["direct_ai_message"] = timeout_msg
                result["tool_messages"] = tool_messages
                result["stream_messages"] = []
                return result
            planned_calls = self._normalize_mcp_calls(plan_data.get("calls", []), allowed_methods, max_queued_calls)
            proposed_plan_calls = self._normalize_mcp_calls(
                plan_data.get("proposed_next_calls", []), allowed_methods, max_calls_per_round
            )
            needs_mcp = self._json_bool(plan_data.get("needs_mcp", True), True)
            plan_summary = str(plan_data.get("plan_summary", "")).strip()
            latest_plan_summary = plan_summary
            latest_reflection_summary = ""
            pending_user_decision = None
            if plan_summary != "":
                self._emit_mcp_status_text(signals, chat_idx, plan_summary, status_kind="planning")
            initial_brief = str(plan_data.get("answer_brief", "")).strip()
            if initial_brief != "":
                final_hint = initial_brief
            planner_user_decision_required = self._json_bool(plan_data.get("user_decision_required", False), False)
            planner_decision_question = self._normalize_progress_note(plan_data.get("decision_question", ""), max_length=600)
            planner_decision_context = self._normalize_progress_note(plan_data.get("decision_context", ""), max_length=600)
            if planner_user_decision_required and planner_decision_question == "":
                planner_decision_question = self._normalize_progress_note(plan_summary, max_length=600)
            if planner_user_decision_required and planner_decision_question != "":
                pending_user_decision = {
                    "phase": "planning",
                    "question": planner_decision_question,
                    "context": planner_decision_context,
                    "proposed_next_calls": proposed_plan_calls,
                }
                result["direct_ai_message"] = planner_decision_question
                stop_reason = "awaiting_user_decision"
            if pending_user_decision is not None:
                agent_state_snapshot = {
                    "type": "mcp_agent_state",
                    "latest_plan_summary": self._normalize_progress_note(latest_plan_summary, max_length=600),
                    "latest_reflection_summary": self._normalize_progress_note(latest_reflection_summary, max_length=600),
                    "final_hint": self._normalize_progress_note(final_hint, max_length=600),
                    "stop_reason": stop_reason,
                    "pending_calls": planned_calls if isinstance(planned_calls, list) else [],
                    "pending_user_decision": pending_user_decision,
                }
                agent_state_content = json.dumps(agent_state_snapshot, ensure_ascii=False)
                if tool_messages_streamed:
                    progress_payload = {
                        "chat_idx": chat_idx,
                        "msg_type": "agent_state",
                        "msg_author": "ai_agent",
                        "msg_content": agent_state_content,
                    }
                    signals.progress.emit(json.dumps(progress_payload, ensure_ascii=False))
                else:
                    tool_messages.append(
                        {
                            "msg_type": "agent_state",
                            "msg_author": "ai_agent",
                            "msg_content": agent_state_content,
                        }
                    )
                result["tool_messages"] = tool_messages
                result["stream_messages"] = []
                return result
            if not needs_mcp:
                planned_calls = []

            for reflection_round in range(max_reflection_rounds):
                if self.app.ai.is_current_run_canceled():
                    result["canceled"] = True
                    return result

                current_round_calls, deferred_calls = self._split_mcp_call_queue(planned_calls, max_calls_per_round)
                executed_any_call = False
                for call in current_round_calls:
                    if self.app.ai.is_current_run_canceled():
                        result["canceled"] = True
                        return result
                    if total_tool_calls >= max_total_tool_calls:
                        stop_reason = "max_total_tool_calls_reached"
                        break
                    method = str(call.get("method", "")).strip()
                    params = call.get("params", {})
                    if not isinstance(params, dict):
                        params = {}
                    if method not in allowed_methods:
                        response = {
                            "jsonrpc": "2.0",
                            "id": self.ai_mcp_server.new_request_id(),
                            "error": {"code": -32601, "message": "Method not found", "data": method},
                        }
                    else:
                        request_params, display_params = _prepare_mcp_request(method, params)
                        status_text = self.ai_mcp_server.describe_status_event(method, request_params)
                        self._emit_mcp_status(signals, chat_idx, status_text)
                        _request, response = self._run_mcp_request(method, request_params)
                        total_tool_calls += 1
                        executed_any_call = True
                    append_tool_exchange(method, display_params if method in allowed_methods else params, response)

                reflection_system_prompt = self._build_mcp_combined_system_prompt(self._mcp_reflection_system_prompt())
                reflection_prompt = "Reflect on sufficiency of the collected evidence and return JSON now."
                if plan_summary != "":
                    reflection_prompt += "\nInitial plan summary:\n" + plan_summary
                if len(deferred_calls) > 0:
                    reflection_prompt += (
                        "\nDeferred calls from the previous execution queue "
                        f"(not yet executed because the round limit is {max_calls_per_round}):\n"
                        + json.dumps(deferred_calls, ensure_ascii=False)
                    )
                append_single_instruct_log(
                    "reflection",
                    "user",
                    build_phase_request_message(reflection_system_prompt, reflection_prompt).content,
                )
                reflection_messages = build_phase_messages(reflection_system_prompt, reflection_prompt)
                try:
                    reflection_data = self._invoke_json_llm_with_step_timeout(
                        reflection_messages,
                        schema_name='mcp_reflection_control',
                        response_schema=reflection_json_schema,
                        context='mcp_json_reflection',
                        step_name=_("Internal reflection"),
                        status_kind="reflection",
                        signals=signals,
                        chat_idx=chat_idx,
                    )
                except TimeoutError:
                    latest_reflection_summary = _('Internal reflection timed out; proceeding with the collected evidence.')
                    self._emit_mcp_status_text(
                        signals,
                        chat_idx,
                        latest_reflection_summary,
                        status_kind="reflection",
                    )
                    planned_calls = []
                    stop_reason = "reflection_timeout"
                    break
                reflection_summary = str(reflection_data.get("reflection_summary", "")).strip()
                if reflection_summary != "":
                    latest_reflection_summary = reflection_summary
                reflection_brief = str(reflection_data.get("answer_brief", "")).strip()
                if reflection_brief != "":
                    final_hint = reflection_brief
                enough_information = self._json_bool(reflection_data.get("enough_information", False), False)
                reflection_next_step_note = str(reflection_data.get("next_step_note", "")).strip()
                continue_deferred_calls = self._json_bool(
                    reflection_data.get("continue_deferred_calls", False),
                    False
                )
                revised_calls = self._normalize_mcp_calls(
                    reflection_data.get("revised_calls", []), allowed_methods, max_queued_calls
                )
                proposed_next_calls = self._normalize_mcp_calls(
                    reflection_data.get("proposed_next_calls", []), allowed_methods, max_calls_per_round
                )
                if continue_deferred_calls and len(deferred_calls) > 0:
                    revised_calls = self._merge_mcp_call_lists(revised_calls, deferred_calls, max_queued_calls)
                short_reflection_note = self._short_reflection_next_step_note(
                    reflection_summary,
                    reflection_next_step_note,
                )
                if short_reflection_note != "":
                    self._emit_mcp_status_text(signals, chat_idx, short_reflection_note, status_kind="reflection")
                user_decision_required = self._json_bool(reflection_data.get("user_decision_required", False), False)
                decision_question = self._normalize_progress_note(reflection_data.get("decision_question", ""), max_length=600)
                decision_context = self._normalize_progress_note(reflection_data.get("decision_context", ""), max_length=600)
                if user_decision_required and decision_question == "":
                    decision_question = short_reflection_note
                if user_decision_required and decision_question != "":
                    planned_calls = revised_calls
                    pending_user_decision = {
                        "phase": "reflection",
                        "question": decision_question,
                        "context": decision_context,
                        "proposed_next_calls": proposed_next_calls,
                    }
                    result["direct_ai_message"] = decision_question
                    stop_reason = "awaiting_user_decision"
                    break
                if enough_information:
                    planned_calls = revised_calls
                    stop_reason = "enough_information"
                    break

                if len(revised_calls) == 0:
                    if executed_any_call:
                        replanner_system_prompt = self._build_mcp_combined_system_prompt(
                            self._mcp_planner_system_prompt()
                        )
                        replanner_user_prompt = (
                            "The previous reflection said more evidence may be needed. "
                            "Propose a revised MCP plan now."
                        )
                        append_single_instruct_log(
                            "replanning",
                            "user",
                            build_phase_request_message(replanner_system_prompt, replanner_user_prompt).content,
                        )
                        replanner_messages = build_phase_messages(replanner_system_prompt, replanner_user_prompt)
                        try:
                            replan_data = self._invoke_json_llm_with_step_timeout(
                                replanner_messages,
                                schema_name='mcp_replanner_control',
                                response_schema=planner_json_schema,
                                context='mcp_json_replanner',
                                step_name=_("Internal replanning"),
                                status_kind="planning",
                                signals=signals,
                                chat_idx=chat_idx,
                            )
                        except TimeoutError:
                            latest_plan_summary = _('Internal replanning timed out; proceeding with the current results.')
                            self._emit_mcp_status_text(
                                signals,
                                chat_idx,
                                latest_plan_summary,
                                status_kind="planning",
                            )
                            planned_calls = []
                            stop_reason = "replanner_timeout"
                            break
                        replan_summary = str(replan_data.get("plan_summary", "")).strip()
                        if replan_summary != "":
                            latest_plan_summary = replan_summary
                        if replan_summary != "":
                            self._emit_mcp_status_text(signals, chat_idx, replan_summary, status_kind="planning")
                        revised_calls = self._normalize_mcp_calls(
                            replan_data.get("calls", []), allowed_methods, max_queued_calls
                        )
                    if len(revised_calls) == 0:
                        stop_reason = "no_more_valid_calls"
                        break
                planned_calls = revised_calls
            else:
                if stop_reason == "":
                    stop_reason = "max_reflection_rounds_reached"

            if pending_user_decision is not None:
                agent_state_snapshot = {
                    "type": "mcp_agent_state",
                    "latest_plan_summary": self._normalize_progress_note(latest_plan_summary, max_length=600),
                    "latest_reflection_summary": self._normalize_progress_note(latest_reflection_summary, max_length=600),
                    "final_hint": self._normalize_progress_note(final_hint, max_length=600),
                    "stop_reason": stop_reason,
                    "pending_calls": planned_calls if isinstance(planned_calls, list) else [],
                    "pending_user_decision": pending_user_decision,
                }
                agent_state_content = json.dumps(agent_state_snapshot, ensure_ascii=False)
                if tool_messages_streamed:
                    progress_payload = {
                        "chat_idx": chat_idx,
                        "msg_type": "agent_state",
                        "msg_author": "ai_agent",
                        "msg_content": agent_state_content,
                    }
                    signals.progress.emit(json.dumps(progress_payload, ensure_ascii=False))
                else:
                    tool_messages.append(
                        {
                            "msg_type": "agent_state",
                            "msg_author": "ai_agent",
                            "msg_content": agent_state_content,
                        }
                    )
                result["tool_messages"] = tool_messages
                result["stream_messages"] = []
                return result

            self._emit_mcp_status(signals, chat_idx, _('Preparing response...'))
            final_prompt = (
                "Now provide the final answer to the user in normal prose. "
                "Focus on outcomes of this turn and communicate them clearly. "
                "Do not mention internal MCP stage constraints. "
                "When referring to empirical text evidence, cite it as {REF: \"exact quote\"}. "
                "Remember: REF is invisible markup; if you want a quote to be visible, include the quoted text in normal prose and add REF in addition."
            )
            if final_hint != '':
                final_prompt += '\nHere is a draft idea from your internal planning:\n' + final_hint
            if stop_reason not in ("", "enough_information"):
                final_prompt += (
                    "\nIf the available project evidence is incomplete, clearly state uncertainty and "
                    "mention what additional project material would help."
                )

            agent_state_snapshot = {
                "type": "mcp_agent_state",
                "latest_plan_summary": self._normalize_progress_note(latest_plan_summary, max_length=600),
                "latest_reflection_summary": self._normalize_progress_note(latest_reflection_summary, max_length=600),
                "final_hint": self._normalize_progress_note(final_hint, max_length=600),
                "stop_reason": stop_reason,
                "pending_calls": planned_calls if isinstance(planned_calls, list) else [],
                "pending_user_decision": None,
            }
            agent_state_content = json.dumps(agent_state_snapshot, ensure_ascii=False)
            if tool_messages_streamed:
                progress_payload = {
                    "chat_idx": chat_idx,
                    "msg_type": "agent_state",
                    "msg_author": "ai_agent",
                    "msg_content": agent_state_content,
                }
                signals.progress.emit(json.dumps(progress_payload, ensure_ascii=False))
            else:
                tool_messages.append(
                    {
                        "msg_type": "agent_state",
                        "msg_author": "ai_agent",
                        "msg_content": agent_state_content,
                    }
                )

            final_system_prompt = self._build_mcp_combined_system_prompt(self._mcp_final_answer_system_prompt())
            final_stream_messages = build_phase_messages(final_system_prompt, final_prompt)
            result["stream_messages"] = final_stream_messages
            result["tool_messages"] = tool_messages
        except Exception as err:
            result["error"] = _('Error during MCP-based AI agent chat: ') + str(err)
        finally:
            if ai_change_set_id != "":
                self._discard_empty_ai_change_set(ai_change_set_id)
        return result

    def ai_mcp_message_callback(self, mcp_result):
        """Called when the MCP-based AI agent chat worker has finished."""

        self.ai_streaming_output = ''
        if not isinstance(mcp_result, dict):
            self.process_message('info', _('Error: Invalid result from MCP AI agent chat worker.'), self.current_streaming_chat_idx)
            self._clear_chat_ai_profile_snapshot(self.current_streaming_chat_idx)
            self._update_undo_button_state()
            return

        chat_idx = int(mcp_result.get("chat_idx", self.current_streaming_chat_idx))
        if chat_idx < 0 or chat_idx >= len(self.chat_list):
            return

        if mcp_result.get("canceled", False):
            self._log_chat_canceled_env_update(chat_idx, partial_response=False)
            self.process_message('info', _('Chat has been canceled by the user.'), chat_idx)
            self._clear_chat_ai_profile_snapshot(chat_idx)
            self._update_undo_button_state()
            return

        err = str(mcp_result.get("error", "")).strip()
        if err != '':
            self.process_message('info', err, chat_idx)
            self._clear_chat_ai_profile_snapshot(chat_idx)
            self._update_undo_button_state()
            return

        tool_messages = mcp_result.get("tool_messages", None)
        if isinstance(tool_messages, list) and len(tool_messages) > 0:
            db_conn = sqlite3.connect(self.chat_history_path)
            try:
                for item in tool_messages:
                    if not isinstance(item, dict):
                        continue
                    msg_type = str(item.get("msg_type", "")).strip()
                    msg_content = str(item.get("msg_content", ""))
                    if msg_type in ("tool_call", "tool_result", "single_instruct", "agent_state", "env_update"):
                        self.process_message(
                            msg_type,
                            msg_content,
                            chat_idx,
                            db_conn=db_conn,
                            refresh_history=False,
                            commit_history=False,
                        )
                db_conn.commit()
                self.history_update_message_list(db_conn)
            finally:
                db_conn.close()
        self._update_undo_button_state()

        direct_ai_message = str(mcp_result.get("direct_ai_message", "")).strip()
        if direct_ai_message != "":
            self.process_message('ai', direct_ai_message, chat_idx)
            self._clear_chat_ai_profile_snapshot(chat_idx)
            self._update_undo_button_state()
            return

        direct_info_message = str(mcp_result.get("direct_info_message", "")).strip()
        if direct_info_message != "":
            self.process_message('info', direct_info_message, chat_idx)
            self._clear_chat_ai_profile_snapshot(chat_idx)
            self._update_undo_button_state()
            return

        stream_messages = mcp_result.get("stream_messages", None)
        if stream_messages is None or not isinstance(stream_messages, list) or len(stream_messages) == 0:
            self.process_message('info', _('Error: Invalid message stream from MCP AI agent chat worker.'), chat_idx)
            self._clear_chat_ai_profile_snapshot(chat_idx)
            self._update_undo_button_state()
            return

        self.current_streaming_chat_idx = chat_idx
        self._capture_chat_ai_profile_snapshot(chat_idx)
        self.app.ai.start_stream(stream_messages,
                                 result_callback=self.ai_message_callback,
                                 progress_callback=None,
                                 streaming_callback=self.ai_streaming_callback,
                                 error_callback=self.ai_error_callback,
                                 model_kind='large',
                                 scope_type='chat',
                                 scope_id=chat_idx)
        self.update_chat_window()
        self._update_undo_button_state()

    def ai_mcp_progress_callback(self, progress_msg):
        """Receive live MCP status updates from the worker thread."""
        try:
            payload = json.loads(str(progress_msg))
        except Exception:
            payload = None

        if isinstance(payload, dict):
            chat_idx = int(payload.get("chat_idx", self.current_chat_idx))
            msg_type = str(payload.get("msg_type", "")).strip()
            if msg_type in ("tool_call", "tool_result", "single_instruct", "agent_state", "env_update"):
                msg_content = str(payload.get("msg_content", ""))
                if msg_content != "":
                    self.process_message(
                        msg_type,
                        msg_content,
                        chat_idx,
                        refresh_history=False,
                            commit_history=True,
                    )
            status = str(payload.get("status", "")).strip()
            status_kind = str(payload.get("status_kind", "")).strip().lower()
        else:
            status = str(progress_msg).strip()
            chat_idx = self.current_chat_idx
            status_kind = ""
        if status == '':
            self._update_undo_button_state()
            return
        if status_kind != "":
            status = json.dumps({"kind": status_kind, "text": status}, ensure_ascii=False)
        self.process_message('agent_status', status, chat_idx)
        self._update_undo_button_state()
    
    def ai_streaming_callback(self, streamed_text):  # TODO streamed_text unused
        self._schedule_stream_render()

    def ai_stream_process_reference(self, reference):
        '''Replace a reference to the empirical data woth a clicable link'''
        return " {REFERENCE} "

    
    def ai_message_callback(self, ai_result):
        """Called if the AI has finished sending its response.
        The streamed resonse is now replaced with the final one.
        """
        chat_idx = self.current_streaming_chat_idx
        was_canceled = self._chat_scope_status(chat_idx) == 'canceled'
        self._cancel_pending_stream_render()
        if was_canceled:
            self._log_chat_canceled_env_update(chat_idx, partial_response=(ai_result != ''))
        self.ai_streaming_output = ''
        if ai_result != '':
            final_text = str(ai_result)
            if self._is_invalid_final_output(final_text):
                self.process_message('agent_status', json.dumps({
                    "kind": "repair",
                    "text": _('Repairing invalid final answer format...'),
                }, ensure_ascii=False), chat_idx)
                repaired_text = self._repair_invalid_final_output(final_text, chat_idx)
                if repaired_text != '' and not self._is_invalid_final_output(repaired_text):
                    final_text = repaired_text
                else:
                    self.process_message(
                        'info',
                        _('Error: The AI returned an internal control message instead of a final answer. Please try again.'),
                        chat_idx,
                    )
                    self._clear_chat_ai_profile_snapshot(chat_idx)
                    if was_canceled:
                        self.process_message('info', _('Chat has been canceled by the user. The partial response was kept.'), chat_idx)
                    return

            self.process_message('ai', final_text, chat_idx)
            self._clear_chat_ai_profile_snapshot(chat_idx)
            if was_canceled:
                self.process_message('info', _('Chat has been canceled by the user. The partial response was kept.'), chat_idx)
        else:
            self._clear_chat_ai_profile_snapshot(chat_idx)
            if was_canceled:
                self.process_message('info', _('Chat has been canceled by the user.'), chat_idx)
            else:
                self.process_message('info', _('Error: The AI returned an empty result. This may indicate that the AI model is not available at the moment. Try again later or choose a different model.'), chat_idx)
            
    def ai_error_callback(self, exception_type, value, tb_obj):
        """Called if the AI returns an error"""
        self._cancel_pending_stream_render()
        self.ai_streaming_output = ''

        def _safe_to_text(obj: object) -> str:
            try:
                return str(obj)
            except Exception:
                try:
                    return repr(obj)
                except Exception:
                    return '<unprintable>'

        try:
            ai_model_name = self._normalize_ai_profile_author(
                chat_idx=self.current_streaming_chat_idx,
                fallback_to_current=True,
            )
            msg = _('Error communicating with ' + ai_model_name + '\n')
            msg += exception_type.__name__ + ': ' + html_to_text(_safe_to_text(value))
            if hasattr(value, 'message'):
                msg += f' {_safe_to_text(getattr(value, "message", ""))}'
            tb = '\n'.join(traceback.format_tb(tb_obj))
            if hasattr(value, 'body'):
                tb += f'\n{_safe_to_text(getattr(value, "body", ""))}\n'
            logger.error(_("Uncaught exception: ") + msg + '\n' + tb)
            # Error msg in chat and trigger message box show
            self.process_message('info', msg, self.current_streaming_chat_idx)
            qt_exception_hook._exception_caught.emit(msg, tb)
        except Exception as err:
            fallback = _('Error while handling AI error callback: ') + _safe_to_text(err)
            logger.error(fallback)
            self.process_message('info', fallback, self.current_streaming_chat_idx)
        finally:
            self._clear_chat_ai_profile_snapshot(self.current_streaming_chat_idx)
    
    def eventFilter(self, source, event):
        editor = self.ui.plainTextEdit_question
        editor_viewport = editor.viewport()

        if source in (editor, editor_viewport) and event.type() == QEvent.Type.MouseButtonPress:
            if self._prompt_completion_popup.isVisible() or self._prompt_inline_completion is not None:
                click_pos = None
                try:
                    click_pos = event.position().toPoint()
                except Exception:
                    click_pos = None
                if click_pos is not None and source is editor:
                    click_pos = editor_viewport.mapFrom(editor, click_pos)
                self._suspend_prompt_completion_temporarily()
                self._dismiss_prompt_completion(accept=False)
                if click_pos is not None:
                    cursor = editor.cursorForPosition(click_pos)
                    editor.setTextCursor(cursor)
                    editor.setFocus(Qt.FocusReason.MouseFocusReason)
                    return True
            return super().eventFilter(source, event)

        if source is editor_viewport and event.type() == QEvent.Type.ToolTip:
            prompt = self._prompt_reference_record_at_position(event.pos())
            if prompt is not None:
                QtWidgets.QToolTip.showText(event.globalPos(), self._prompt_reference_tooltip(prompt), editor)
                return True
            QtWidgets.QToolTip.hideText()
            return True

        if event.type() == QEvent.Type.KeyPress and source is self.ui.plainTextEdit_question:
            if event.key() in (
                Qt.Key.Key_Backspace,
                Qt.Key.Key_Delete,
                Qt.Key.Key_Left,
                Qt.Key.Key_Right,
                Qt.Key.Key_Home,
                Qt.Key.Key_End,
            ):
                if self._prompt_completion_popup.isVisible() or self._prompt_inline_completion is not None:
                    self._suspend_prompt_completion_temporarily()
                    self._dismiss_prompt_completion(accept=False)
                return super().eventFilter(source, event)

            if self._prompt_completion_popup.isVisible():
                if event.key() == Qt.Key.Key_Down:
                    if self._move_prompt_completion_selection(1):
                        return True
                elif event.key() == Qt.Key.Key_Up:
                    if self._move_prompt_completion_selection(-1):
                        return True
                elif event.key() in (Qt.Key.Key_Tab, Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                        if self._accept_prompt_completion():
                            return True
                elif event.key() == Qt.Key.Key_Escape:
                    self._dismiss_prompt_completion(accept=False)
                    return True

            # Shift + Return/Enter creates a new line. Just pressing Return/Enter sends the question to the AI:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self.send_user_question()
                    return True  # Event handled
        # For all other cases, return super's eventFilter result
        return super().eventFilter(source, event)
    
    def on_linkHovered(self, link: str):

        if link:
            # Show tooltip when hovering over a link
            if link.startswith('promptref:'):
                prompt_name = unquote(link[len('promptref:'):]).strip('/').casefold()
                self._refresh_prompt_completion_records()
                prompt = self._prompt_reference_records_by_name().get(prompt_name)
                if prompt is not None:
                    QtWidgets.QToolTip.showText(QCursor.pos(), self._prompt_reference_tooltip(prompt), self.ui.ai_output)
            elif link.startswith('coding:'):
                try:
                    coding_id = link[len('coding:'):]
                    cursor = self.app.conn.cursor()
                    sql = (f'SELECT code_text.ctid, source.name, code_text.seltext '
                            f'FROM code_text JOIN source ON code_text.fid = source.id '
                            f'WHERE code_text.ctid = {coding_id}')
                    cursor.execute(sql)
                    coding = cursor.fetchone()
                except Exception as e:
                    logger.debug(f'Link: "{link}" - Error: {e}')
                    coding = None                
                if coding is not None:
                    tooltip_txt = f'{coding[1]}:\n'  # file name
                    tooltip_txt += f'"{coding[2]}"'  # seltext
                else:
                    tooltip_txt = _('Invalid source reference.')
                QtWidgets.QToolTip.showText(QCursor.pos(), tooltip_txt, self.ui.ai_output)
            elif link.startswith('chunk:'):
                try:
                    chunk_id = link[len('chunk:'):]
                    chunk_id_elem = chunk_id.split('_')
                    if len(chunk_id_elem) == 3:  # legacy format
                        source_id, start, length = chunk_id_elem
                        line_start = 0
                        line_end = 0
                    else:
                        source_id, start, length, line_start, line_end = chunk_id_elem
                    cursor = self.app.conn.cursor()
                    sql = f'SELECT name, fulltext FROM source WHERE id = {source_id}'
                    cursor.execute(sql)
                    source = cursor.fetchone()
                    tooltip_txt = f'{source[0]}: {line_start} - {line_end}\n'  # File name
                    tooltip_txt += f'"{source[1][int(start):int(start) + int(length)]}"'  # Chunk extracted from fulltext                    
                except Exception as e:
                    logger.debug(f'Link: "{link}" - Error: {e}')
                    source = None  # TODO source not used
                    tooltip_txt = _('Invalid source reference.')
                QtWidgets.QToolTip.showText(QCursor.pos(), tooltip_txt, self.ui.ai_output)
            elif link.startswith('quote:'):
                # tooltip_txt = _('Open source document')
                tooltip_txt = ''
                try:
                    quote_id = link[len('quote:'):]
                    source_id, start, length = quote_id.split('_')
                    tooltip_txt = f'"{self.app.get_text_fulltext(int(source_id), int(start), int(length))}"'
                except Exception as e:
                    print(e)
                    tooltip_txt = ''
                if tooltip_txt == '':
                    tooltip_txt = _('Error retrieving source text')
                QtWidgets.QToolTip.showText(QCursor.pos(), tooltip_txt, self.ui.ai_output)
            elif link.startswith('action:topic_chat_analyze_more'):
                tooltip_txt = _('This expands the data basis for the analysis. However, '
                                'be careful not to overdo it, as this can also dilute '
                                'the focus of the analysis.')
                QtWidgets.QToolTip.showText(QCursor.pos(), tooltip_txt, self.ui.ai_output)
        else:
            QtWidgets.QToolTip.hideText()

    def _open_text_reference(self, doc_id: int, start: int, end: int):
        """Show AI chat in sidebar mode and open the selected text span."""

        if not getattr(self.main_window, 'ai_chat_sidebar_mode', False):
            self.main_window.set_ai_chat_sidebar_mode(
                True,
                target_tab=self.main_window.ui.tab_coding
            )
        self.main_window.text_coding(
            task='documents',
            doc_id=int(doc_id),
            doc_sel_start=int(start),
            doc_sel_end=int(end)
        )
            
    def on_linkActivated(self, link: str):

        if link:
            # Open doc in coding window 
            if link.startswith('coding:'):
                try:
                    coding_id = link[len('coding:'):]
                    cursor = self.app.conn.cursor()
                    sql = (f'SELECT fid, pos0, pos1 '
                            f'FROM code_text '
                            f'WHERE code_text.ctid = {coding_id}')
                    cursor.execute(sql)
                    coding = cursor.fetchone()
                except Exception as e:
                    logger.debug(f'Link: "{link}" - Error: {e}')
                    coding = None
                if coding is not None:
                    self._open_text_reference(int(coding[0]), int(coding[1]), int(coding[2]))
                else:
                    msg = _('Invalid source reference.')
                    Message(self.app, _('AI Chat'), msg, icon='critical').exec()
            elif link.startswith('chunk:'):
                try:
                    chunk_id = link[len('chunk:'):]
                    chunk_id_elem = chunk_id.split('_')
                    if len(chunk_id_elem) == 3:  # legacy format
                        source_id, start, length = chunk_id_elem
                        line_start = 0
                        line_end = 0
                    else:
                        source_id, start, length, line_start, line_end = chunk_id_elem
                    end = int(start) + int(length)
                    self._open_text_reference(int(source_id), int(start), end)
                except Exception as e:
                    logger.debug(f'Link: "{link}" - Error: {e}')
                    source_id = None  # TODO source_id not used
                    msg = _('Invalid source reference.')
                    Message(self.app, _('AI Chat'), msg, icon='critical').exec()  
            elif link.startswith('quote:'):
                    quote_id = link[len('quote:'):]
                    source_id, start, length = quote_id.split('_')
                    end = int(start) + int(length)
                    self._open_text_reference(int(source_id), int(start), end)
            elif link.startswith('action:topic_chat_analyze_more'):
                self.topic_chat_analyze_more()
            elif link.startswith('promptref:'):
                return

# Helper:
class LlmCallbackHandler(BaseCallbackHandler):
    def __init__(self, dialog_ai_chat: DialogAIChat):
        self.dialog = dialog_ai_chat
        
    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.dialog.ai_streaming_output += token
        if not self.dialog.is_updating_chat_window:
            self.dialog.update_chat_window()        
