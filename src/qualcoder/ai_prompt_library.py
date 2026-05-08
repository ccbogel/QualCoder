# -*- coding: utf-8 -*-

"""
Prompt library editor for QualCoder.

This dialog edits the Markdown-based AI prompt files managed by
``AiAgentPromptsCatalog``. Legacy ``ai_prompts.yaml`` files are still migrated by
the catalog, but they are no longer shown or edited here.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import os
import re
import shutil
from typing import Dict, List, Optional, Set, Tuple

from PyQt6 import QtCore, QtWidgets, QtGui
from PyQt6.QtGui import QClipboard, QKeySequence, QShortcut, QAction, QFont
from PyQt6.QtCore import Qt
import qtawesome as qta

from .ai_agent_prompts import AiAgentPromptsCatalog
from .GUI.ui_ai_edit_prompts import Ui_Dialog_AiPrompts
from .helpers import Message
from .confirm_delete import DialogConfirmDelete


path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

prompt_types = [
    "general",
    "search",
    "code_analysis",
    "topic_exploration",
    "text_analysis",
]

prompt_types_descriptions = {
    "general": (
        "These are general-purpose prompts from the root of the prompt library. "
        "They can be used in the general AI Agent chat."
    ),
    "search": (
        "These prompts are used in the AI search. They instruct the AI on how to decide \n"
        "whether a chunk of empirical data is related to a given code/search string or not."
    ),
    "code_analysis": (
        "These prompts are used in the chat to analyze the data that has been coded with a selected code."
    ),
    "topic_exploration": (
        "These prompts are used in the chat to analyse the results of a free search exploring a certain topic."
    ),
    "text_analysis": (
        "These prompts are used in the chat to analyze a section of text from a single empirical document."
    ),
}

prompt_scopes = ["system", "user", "project"]

prompt_scope_descriptions = {
    "system": (
        "System prompts are the defaults shipped with QualCoder. They are read-only in this editor."
    ),
    "user": (
        "User prompts are defined for your local QualCoder profile and are available in every project."
    ),
    "project": (
        "Project prompts are stored with the current project and are available to everyone opening it."
    ),
}


@dataclass
class EditorPromptRecord:
    scope: str
    prompt_type: str
    name: str
    directory: str
    description: str
    text: str
    original_file_path: str
    current_file_path: str
    is_system: bool

    def name_and_scope(self) -> str:
        return self.name + f" ({self.scope})"

    def path(self) -> str:
        if self.directory == "":
            return self.name
        return self.directory + "/" + self.name


@dataclass
class EditorFolderRecord:
    prompt_type: str
    relative_dir: str
    scopes_present: Set[str]

    def name(self) -> str:
        if self.relative_dir == "":
            return ""
        return self.relative_dir.rsplit("/", 1)[-1]


def get_item_level(item) -> int:
    """Return the depth of one tree item."""

    level = 0
    while True:
        parent = item.parent()
        if parent is None:
            break
        level += 1
        item = parent
    return level


ITEM_KIND_ROLE = Qt.ItemDataRole.UserRole + 20
ITEM_PROMPT_NAME_ROLE = Qt.ItemDataRole.UserRole + 21
ITEM_SCOPE_ROLE = Qt.ItemDataRole.UserRole + 22
ITEM_PROMPT_TYPE_ROLE = Qt.ItemDataRole.UserRole + 23
ITEM_DIRECTORY_ROLE = Qt.ItemDataRole.UserRole + 24
ITEM_FOLDER_SCOPES_ROLE = Qt.ItemDataRole.UserRole + 25
ITEM_IS_TYPE_ROOT_ROLE = Qt.ItemDataRole.UserRole + 26

ITEM_KIND_PROMPT = "prompt"
ITEM_KIND_FOLDER = "folder"
ITEM_KIND_TYPE = "type"


class DialogAiEditPrompts(QtWidgets.QDialog):
    """Dialog to edit prompts from the Markdown-based AI prompt system."""

    def __init__(self, app_, prompt_type=None, initial_prompt_name: str = "", initial_prompt_scope: str = ""):
        self.app = app_
        self.catalog = AiAgentPromptsCatalog(app_)
        self.prompt_type = self.catalog.normalize_prompt_type(prompt_type)
        self.initial_prompt_name = self.catalog._normalize_prompt_name(initial_prompt_name)
        self.initial_prompt_scope = str(initial_prompt_scope if initial_prompt_scope is not None else "").strip()
        self.prompts: List[EditorPromptRecord] = []
        self.folders: List[EditorFolderRecord] = []
        self.selected_prompt: Optional[EditorPromptRecord] = None
        self.form_updating = True
        self.catalog.migrate_legacy_prompts_once()

        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_AiPrompts()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {app_.settings["fontsize"]}pt "{app_.settings["font"]}";'
        self.setStyleSheet(font)
        treefont = f'font: {self.app.settings["treefontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.treeWidget_prompts.setStyleSheet(treefont)

        self.ui.comboBox_type.addItems(prompt_types)
        self.ui.lineEdit_name.setValidator(
            QtGui.QRegularExpressionValidator(
                QtCore.QRegularExpression(r"[a-z0-9][a-z0-9_-]{0,63}"),
                self.ui.lineEdit_name,
            )
        )
        self.ui.treeWidget_prompts.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.treeWidget_prompts.customContextMenuRequested.connect(self.open_tree_context_menu)
        self.ui.treeWidget_prompts.setDragEnabled(True)
        self.ui.treeWidget_prompts.setAcceptDrops(True)
        self.ui.treeWidget_prompts.setDropIndicatorShown(True)
        self.ui.treeWidget_prompts.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.DragDrop)
        self.ui.treeWidget_prompts.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.ui.treeWidget_prompts.installEventFilter(self)
        self.ui.treeWidget_prompts.viewport().installEventFilter(self)
        self._reload_prompts()
        if self.prompt_type is None:
            self.ui.treeWidget_prompts.collapseAll()

        self.ui.treeWidget_prompts.itemSelectionChanged.connect(self.tree_selection_changed)
        self._new_menu = QtWidgets.QMenu(self)
        self._new_prompt_action = QAction(_('Create new prompt'), self)
        self._new_folder_action = QAction(_('Create new folder'), self)
        self._new_prompt_action.triggered.connect(self.new_prompt)
        self._new_folder_action.triggered.connect(self.new_folder)
        self._new_menu.addAction(self._new_prompt_action)
        self._new_menu.addAction(self._new_folder_action)
        self.ui.pushButton_new_prompt.clicked.connect(self.open_new_menu)
        self.ui.pushButton_duplicate_prompt.clicked.connect(self.duplicate_prompt)

        self.ui.toolButton_copy.setIcon(qta.icon("mdi6.content-copy", options=[{"scale_factor": 1.4}]))
        self.ui.toolButton_copy.setFixedHeight(self.ui.pushButton_new_prompt.height())
        self.ui.toolButton_copy.setFixedWidth(self.ui.pushButton_new_prompt.height())
        self.ui.toolButton_copy.clicked.connect(self.copy_prompt_to_clipboard)

        self.ui.toolButton_paste.setFixedHeight(self.ui.pushButton_new_prompt.height())
        self.ui.toolButton_paste.setFixedWidth(self.ui.pushButton_new_prompt.height())
        self.ui.toolButton_paste.setIcon(qta.icon("mdi6.content-paste", options=[{"scale_factor": 1.4}]))
        self.ui.toolButton_paste.clicked.connect(self.paste_prompt_from_clipboard)

        self.ui.toolButton_delete.setFixedHeight(self.ui.pushButton_new_prompt.height())
        self.ui.toolButton_delete.setFixedWidth(self.ui.pushButton_new_prompt.height())
        self.ui.toolButton_delete.setIcon(qta.icon("mdi6.trash-can-outline", options=[{"scale_factor": 1.4}]))
        self.ui.toolButton_delete.setToolTip(_('Delete prompt or folder'))
        self.ui.toolButton_delete.clicked.connect(self.delete_selected)

        self.ui.lineEdit_name.editingFinished.connect(self.prompt_details_edited)
        self.ui.radioButton_system.toggled.connect(self.prompt_details_edited)
        self.ui.radioButton_user.toggled.connect(self.prompt_details_edited)
        self.ui.radioButton_project.toggled.connect(self.prompt_details_edited)
        self.ui.comboBox_type.currentTextChanged.connect(self.prompt_details_edited)
        self.ui.plainTextEdit_description.textChanged.connect(self.prompt_details_edited)
        self.ui.plainTextEdit_prompt_text.textChanged.connect(self.prompt_details_edited)

        self.ui.buttonBox.accepted.connect(self.ok)
        self.ui.buttonBox.rejected.connect(self.cancel)
        self.ui.buttonBox.helpRequested.connect(self.help)

        copy_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Copy), self.ui.treeWidget_prompts)
        copy_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        copy_shortcut.activated.connect(self.copy_prompt_to_clipboard)

        paste_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Paste), self.ui.treeWidget_prompts)
        paste_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        paste_shortcut.activated.connect(self.paste_prompt_from_clipboard)

        self.form_updating = False
        self.tree_selection_changed()

    def help(self):
        self.app.help_wiki("6.2.-AI-Prompt-Editing")

    def open_new_menu(self):
        button = self.ui.pushButton_new_prompt
        self._new_menu.popup(button.mapToGlobal(QtCore.QPoint(0, button.height())))

    def _reload_prompts(self) -> None:
        self.prompts = []
        self.folders = []
        selected_prompts: Dict[str, object] = {}
        for prompt in self.catalog.list_prompt_variants(
            prompt_type=self.prompt_type,
            include_internal=True,
            apply_init=False,
        ):
            conflict_key = str(prompt.name if prompt.name is not None else "").strip().casefold()
            if conflict_key == "":
                continue
            prev = selected_prompts.get(conflict_key)
            if prev is None:
                selected_prompts[conflict_key] = prompt
                continue
            prev_rank = self.catalog._scope_priority.get(str(prev.scope), -1)
            new_rank = self.catalog._scope_priority.get(str(prompt.scope), -1)
            if new_rank > prev_rank:
                selected_prompts[conflict_key] = prompt

        for prompt in selected_prompts.values():
            prompt_type = self.catalog.prompt_type_from_name(prompt.name)
            if prompt_type is None:
                continue
            if self.prompt_type is not None and prompt_type != self.prompt_type:
                continue
            relative_path = self.catalog.prompt_name_within_type(prompt.name)
            basename = relative_path.rsplit("/", 1)[-1]
            directory = self._relative_dir_of_prompt_path(relative_path)
            if basename.startswith("_") or self._is_hidden_relative_dir(directory):
                continue
            self.prompts.append(
                EditorPromptRecord(
                    scope=prompt.scope,
                    prompt_type=prompt_type,
                    name=basename,
                    directory=directory,
                    description=str(prompt.description if prompt.description is not None else ""),
                    text=str(prompt.content if prompt.content is not None else ""),
                    original_file_path=prompt.file_path,
                    current_file_path=prompt.file_path,
                    is_system=(prompt.scope == "system"),
                )
            )
        self._reload_folders()
        if self.selected_prompt is None and self.initial_prompt_name != "":
            initial_type = self.catalog.prompt_type_from_name(self.initial_prompt_name)
            initial_path = self.catalog.prompt_name_within_type(self.initial_prompt_name)
            initial_name = initial_path.rsplit("/", 1)[-1]
            initial_dir = self._relative_dir_of_prompt_path(initial_path)
            if initial_type is not None and initial_name != "":
                for prompt in self.prompts:
                    if (
                        prompt.prompt_type == initial_type
                        and prompt.name == initial_name
                        and prompt.directory == initial_dir
                        and (self.initial_prompt_scope == "" or prompt.scope == self.initial_prompt_scope)
                    ):
                        self.selected_prompt = prompt
                        break
        self.prompts.sort(
            key=lambda item: (
                prompt_types.index(item.prompt_type),
                item.directory.casefold(),
                prompt_scopes.index(item.scope),
                item.name.casefold(),
            )
        )
        self.folders.sort(key=lambda item: (prompt_types.index(item.prompt_type), item.relative_dir.casefold()))
        self.fill_tree()

    def _reload_folders(self) -> None:
        folders_by_key: Dict[Tuple[str, str], EditorFolderRecord] = {}
        for scope in prompt_scopes:
            for prompt_type in prompt_types:
                if self.prompt_type is not None and prompt_type != self.prompt_type:
                    continue
                for relative_dir in self._scan_scope_dirs(scope, prompt_type):
                    key = (prompt_type, relative_dir)
                    if key not in folders_by_key:
                        folders_by_key[key] = EditorFolderRecord(prompt_type=prompt_type, relative_dir=relative_dir, scopes_present=set())
                    folders_by_key[key].scopes_present.add(scope)
        self.folders = list(folders_by_key.values())

    def _refresh_tree_from_memory(self) -> None:
        """Rebuild the tree from the current in-memory prompt state without reloading prompts from disk."""

        self.prompts.sort(
            key=lambda item: (
                prompt_types.index(item.prompt_type),
                item.directory.casefold(),
                prompt_scopes.index(item.scope),
                item.name.casefold(),
            )
        )
        self._reload_folders()
        self.folders.sort(key=lambda item: (prompt_types.index(item.prompt_type), item.relative_dir.casefold()))
        self.fill_tree()

    def _scan_scope_dirs(self, scope: str, prompt_type: str) -> List[str]:
        type_root = self._type_root_dir(scope, prompt_type)
        if type_root == "" or not os.path.isdir(type_root):
            return []
        excluded_root_dirs: Set[str] = set()
        if prompt_type == "general":
            excluded_root_dirs = {
                folder for folder in (
                    self.catalog.prompt_folder_for_type(candidate_type)
                    for candidate_type in prompt_types
                    if candidate_type != "general"
                )
                if folder != ""
            }
        result: List[str] = []
        for dirpath, dirnames, _ in os.walk(type_root):
            dirnames[:] = [
                dirname for dirname in dirnames
                if not dirname.startswith("_")
                and not (
                    prompt_type == "general"
                    and os.path.normpath(dirpath) == os.path.normpath(type_root)
                    and dirname in excluded_root_dirs
                )
            ]
            rel_dir = os.path.relpath(dirpath, type_root)
            if rel_dir in (".", ""):
                continue
            normalized_dir = self._normalize_relative_dir(rel_dir)
            if normalized_dir == "" or self._is_hidden_relative_dir(normalized_dir):
                continue
            result.append(normalized_dir)
        result.sort(key=str.casefold)
        return result

    def _type_icon(self, prompt_type: str):
        if prompt_type == "general":
            return self.app.ai.general_chat_icon()
        if prompt_type == "search":
            return self.app.ai.search_icon()
        if prompt_type == "code_analysis":
            return self.app.ai.code_analysis_icon()
        if prompt_type == "topic_exploration":
            if hasattr(self.app.ai, "topic_exploration_icon"):
                return self.app.ai.topic_exploration_icon()
            return self.app.ai.topic_analysis_icon()
        if prompt_type == "text_analysis":
            return self.app.ai.text_analysis_icon()
        return self.app.ai.prompt_icon()

    def _folder_icon(self):
        return qta.icon("mdi.folder-outline", color=self.app.highlight_color())

    def _prompt_file_icon(self):
        text_color = self.ui.treeWidget_prompts.palette().color(QtGui.QPalette.ColorRole.Text).name()
        return qta.icon("mdi6.script-text-outline", color=text_color)

    @staticmethod
    def _prompt_tree_label(prompt: EditorPromptRecord) -> str:
        return prompt.name_and_scope()

    @staticmethod
    def _normalize_relative_dir(value: str) -> str:
        text = str(value if value is not None else "").strip()
        if text == "":
            return ""
        parts = [part.strip() for part in text.replace("\\", "/").split("/") if part.strip() != ""]
        return "/".join(parts)

    def _relative_dir_of_prompt_path(self, relative_path: str) -> str:
        normalized = self._normalize_relative_dir(relative_path)
        if "/" not in normalized:
            return ""
        return normalized.rsplit("/", 1)[0]

    def _join_prompt_path(self, directory: str, name: str) -> str:
        normalized_dir = self._normalize_relative_dir(directory)
        clean_name = str(name if name is not None else "").strip()
        if normalized_dir == "":
            return clean_name
        if clean_name == "":
            return normalized_dir
        return normalized_dir + "/" + clean_name

    def _is_hidden_relative_dir(self, relative_dir: str) -> bool:
        normalized = self._normalize_relative_dir(relative_dir)
        if normalized == "":
            return False
        return any(segment.startswith("_") for segment in normalized.split("/"))

    def _type_root_dir(self, scope: str, prompt_type: str) -> str:
        root = self.catalog.prompt_root_for_scope(scope)
        if root == "":
            return ""
        folder = self.catalog.prompt_folder_for_type(prompt_type)
        if folder == "":
            return root
        return os.path.join(root, folder)

    def _folder_record(self, prompt_type: str, relative_dir: str) -> Optional[EditorFolderRecord]:
        normalized = self._normalize_relative_dir(relative_dir)
        for folder in self.folders:
            if folder.prompt_type == prompt_type and folder.relative_dir == normalized:
                return folder
        return None

    def _folder_direct_children(self, prompt_type: str, parent_dir: str) -> List[EditorFolderRecord]:
        normalized_parent = self._normalize_relative_dir(parent_dir)
        result: List[EditorFolderRecord] = []
        for folder in self.folders:
            if folder.prompt_type != prompt_type:
                continue
            folder_parent = self._relative_dir_of_prompt_path(folder.relative_dir)
            if folder_parent == normalized_parent:
                result.append(folder)
        result.sort(key=lambda item: item.name().casefold())
        return result

    def _prompts_in_dir(self, prompt_type: str, relative_dir: str) -> List[EditorPromptRecord]:
        normalized_dir = self._normalize_relative_dir(relative_dir)
        result = [prompt for prompt in self.prompts if prompt.prompt_type == prompt_type and prompt.directory == normalized_dir]
        result.sort(key=lambda item: (prompt_scopes.index(item.scope), item.name.casefold()))
        return result

    def _type_display_name(self, prompt_type: str) -> str:
        if prompt_type == "general":
            return "general"
        return self.catalog.prompt_folder_for_type(prompt_type)

    def _set_prompt_item_data(self, item: QtWidgets.QTreeWidgetItem, prompt: EditorPromptRecord) -> None:
        item.setData(0, ITEM_KIND_ROLE, ITEM_KIND_PROMPT)
        item.setData(0, ITEM_PROMPT_NAME_ROLE, prompt.name)
        item.setData(0, ITEM_SCOPE_ROLE, prompt.scope)
        item.setData(0, ITEM_PROMPT_TYPE_ROLE, prompt.prompt_type)
        item.setData(0, ITEM_DIRECTORY_ROLE, prompt.directory)

    def _set_folder_item_data(self, item: QtWidgets.QTreeWidgetItem, folder: EditorFolderRecord) -> None:
        item.setData(0, ITEM_KIND_ROLE, ITEM_KIND_FOLDER)
        item.setData(0, ITEM_PROMPT_TYPE_ROLE, folder.prompt_type)
        item.setData(0, ITEM_DIRECTORY_ROLE, folder.relative_dir)
        item.setData(0, ITEM_FOLDER_SCOPES_ROLE, "|".join(sorted(folder.scopes_present)))

    def _set_type_item_data(self, item: QtWidgets.QTreeWidgetItem, prompt_type: str) -> None:
        item.setData(0, ITEM_KIND_ROLE, ITEM_KIND_TYPE)
        item.setData(0, ITEM_PROMPT_TYPE_ROLE, prompt_type)
        item.setData(0, ITEM_DIRECTORY_ROLE, "")
        item.setData(0, ITEM_IS_TYPE_ROOT_ROLE, True)

    def _make_type_item(self, prompt_type: str) -> QtWidgets.QTreeWidgetItem:
        item = QtWidgets.QTreeWidgetItem(self.ui.treeWidget_prompts)
        item.setText(0, self._type_display_name(prompt_type))
        item.setToolTip(0, prompt_types_descriptions.get(prompt_type, ""))
        item.setIcon(0, self._type_icon(prompt_type))
        font = QFont(item.font(0))
        font.setBold(True)
        item.setFont(0, font)
        item.setFlags((item.flags() | Qt.ItemFlag.ItemIsDropEnabled) & ~Qt.ItemFlag.ItemIsDragEnabled)
        self._set_type_item_data(item, prompt_type)
        return item

    def _make_folder_item(self, parent_item: QtWidgets.QTreeWidgetItem, folder: EditorFolderRecord) -> QtWidgets.QTreeWidgetItem:
        item = QtWidgets.QTreeWidgetItem(parent_item)
        item.setText(0, folder.name())
        item.setToolTip(0, "Available in: " + ", ".join(sorted(folder.scopes_present)))
        item.setIcon(0, self._folder_icon())
        item.setFlags((item.flags() | Qt.ItemFlag.ItemIsDropEnabled) & ~Qt.ItemFlag.ItemIsDragEnabled)
        self._set_folder_item_data(item, folder)
        return item

    def _make_prompt_item(self, parent_item, prompt: EditorPromptRecord) -> QtWidgets.QTreeWidgetItem:
        item = QtWidgets.QTreeWidgetItem(parent_item)
        item.setText(0, self._prompt_tree_label(prompt))
        item.setToolTip(0, prompt.description)
        item.setIcon(0, self._prompt_file_icon())
        item.setFlags((item.flags() | Qt.ItemFlag.ItemIsDragEnabled) & ~Qt.ItemFlag.ItemIsDropEnabled)
        self._set_prompt_item_data(item, prompt)
        return item

    def _populate_type_branch(
        self,
        prompt_type: str,
        parent_item,
        parent_dir: str,
        selected_path: str,
        target_item_holder: Dict[str, Optional[QtWidgets.QTreeWidgetItem]],
    ) -> None:
        for prompt in self._prompts_in_dir(prompt_type, parent_dir):
            prompt_item = self._make_prompt_item(parent_item, prompt)
            prompt_path = "|".join(self.tree_get_item_path(prompt_item))
            if prompt is self.selected_prompt or (selected_path != "" and prompt_path == selected_path):
                target_item_holder["item"] = prompt_item
        for folder in self._folder_direct_children(prompt_type, parent_dir):
            folder_item = self._make_folder_item(parent_item, folder)
            folder_path = "|".join(self.tree_get_item_path(folder_item))
            if selected_path != "" and folder_path == selected_path and target_item_holder["item"] is None:
                target_item_holder["item"] = folder_item
            self._populate_type_branch(prompt_type, folder_item, folder.relative_dir, selected_path, target_item_holder)

    def fill_tree(self):
        old_form_updating = self.form_updating
        self.form_updating = True
        try:
            selected_path = ""
            target_item_holder: Dict[str, Optional[QtWidgets.QTreeWidgetItem]] = {"item": None}
            if len(self.ui.treeWidget_prompts.selectedItems()) > 0:
                selected_path = "|".join(self.tree_get_item_path(self.ui.treeWidget_prompts.selectedItems()[0]))

            self.ui.treeWidget_prompts.clear()
            for prompt_type in prompt_types:
                if self.prompt_type is not None and prompt_type != self.prompt_type:
                    continue
                if prompt_type == "general":
                    self._populate_type_branch(prompt_type, self.ui.treeWidget_prompts, "", selected_path, target_item_holder)
                    continue
                type_item = self._make_type_item(prompt_type)
                if selected_path != "" and selected_path == self._type_display_name(prompt_type) and target_item_holder["item"] is None:
                    target_item_holder["item"] = type_item
                self._populate_type_branch(prompt_type, type_item, "", selected_path, target_item_holder)

            target_item = target_item_holder["item"]
            if target_item is not None:
                self._expand_item_ancestors(target_item)
                self.ui.treeWidget_prompts.setCurrentItem(target_item)
                target_item.setSelected(True)
            elif len(self.ui.treeWidget_prompts.selectedItems()) == 0 and selected_path != "":
                item = self.tree_find_item_by_path(selected_path.split("|"))
                if item is not None:
                    self._expand_item_ancestors(item)
                    self.ui.treeWidget_prompts.setCurrentItem(item)
                    item.setSelected(True)
            if len(self.ui.treeWidget_prompts.selectedItems()) == 0:
                first_prompt_item = self._find_first_prompt_item()
                if first_prompt_item is not None:
                    self._expand_item_ancestors(first_prompt_item)
                    self.ui.treeWidget_prompts.setCurrentItem(first_prompt_item)
                    first_prompt_item.setSelected(True)
            if len(self.ui.treeWidget_prompts.selectedItems()) > 0:
                self.ui.treeWidget_prompts.scrollToItem(
                    self.ui.treeWidget_prompts.selectedItems()[0],
                    QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible,
                )
        finally:
            self.form_updating = old_form_updating
            self.tree_selection_changed()

    def tree_get_item_path(self, item):
        path_ = []
        while item is not None:
            path_.append(item.text(0))
            item = item.parent()
        return path_[::-1]

    def tree_find_item_by_path(self, path_):
        root_item_count = self.ui.treeWidget_prompts.topLevelItemCount()
        for i in range(root_item_count):
            item = self.ui.treeWidget_prompts.topLevelItem(i)
            result = self._tree_find_item_by_path_recursive(item, path_)
            if result is not None:
                return result
        return None

    def _find_first_prompt_item(self):
        root_item_count = self.ui.treeWidget_prompts.topLevelItemCount()
        for i in range(root_item_count):
            item = self.ui.treeWidget_prompts.topLevelItem(i)
            result = self._find_first_prompt_item_recursive(item)
            if result is not None:
                return result
        return None

    def _find_first_prompt_item_recursive(self, item):
        if item is None:
            return None
        if item.data(0, ITEM_KIND_ROLE) == ITEM_KIND_PROMPT:
            return item
        for i in range(item.childCount()):
            result = self._find_first_prompt_item_recursive(item.child(i))
            if result is not None:
                return result
        return None

    def _expand_item_ancestors(self, item) -> None:
        """Expand a prompt item and all its parent nodes."""

        current = item
        while current is not None:
            current.setExpanded(True)
            current = current.parent()

    def _tree_find_item_by_path_recursive(self, item, path_):
        if not path_:
            return None
        if item.text(0) == path_[0]:
            if len(path_) == 1:
                return item
            for i in range(item.childCount()):
                child_item = item.child(i)
                result = self._tree_find_item_by_path_recursive(child_item, path_[1:])
                if result is not None:
                    return result
            return item
        return None

    def _find_prompt(self, name: str, scope: str, prompt_type: str, directory: str = "") -> Optional[EditorPromptRecord]:
        normalized_dir = self._normalize_relative_dir(directory)
        for prompt in self.prompts:
            if (
                prompt.name == name
                and prompt.scope == scope
                and prompt.prompt_type == prompt_type
                and prompt.directory == normalized_dir
            ):
                return prompt
        return None

    def tree_selection_changed(self):
        if self.form_updating:
            return
        self.selected_prompt = None
        selected_kind = ""
        if len(self.ui.treeWidget_prompts.selectedItems()) > 0:
            selected_item = self.ui.treeWidget_prompts.selectedItems()[0]
            selected_item.setExpanded(True)
            selected_kind = str(selected_item.data(0, ITEM_KIND_ROLE) or "")
            if selected_kind == ITEM_KIND_PROMPT:
                selected_name = selected_item.data(0, ITEM_PROMPT_NAME_ROLE)
                selected_scope = selected_item.data(0, ITEM_SCOPE_ROLE)
                selected_type = selected_item.data(0, ITEM_PROMPT_TYPE_ROLE)
                selected_dir = self._normalize_relative_dir(selected_item.data(0, ITEM_DIRECTORY_ROLE) or "")
                for prompt in self.prompts:
                    if (
                        prompt.name == selected_name
                        and prompt.scope == selected_scope
                        and prompt.prompt_type == selected_type
                        and prompt.directory == selected_dir
                    ):
                        self.selected_prompt = prompt
                        break

        old_form_updating = self.form_updating
        self.form_updating = True
        try:
            if self.selected_prompt is None:
                self.ui.widget_prompt_details.setEnabled(False)
                self.ui.lineEdit_name.setText("")
                self.ui.radioButton_system.setChecked(False)
                self.ui.radioButton_user.setChecked(False)
                self.ui.radioButton_project.setChecked(False)
                self.ui.comboBox_type.setCurrentText("")
                self.ui.plainTextEdit_description.setPlainText("")
                self.ui.plainTextEdit_prompt_text.setPlainText("")
                self.ui.label_uneditable.hide()
                self.ui.pushButton_duplicate_prompt.setEnabled(False)
                self.ui.toolButton_copy.setEnabled(False)
                self.ui.toolButton_paste.setEnabled(True)
                self.ui.toolButton_delete.setEnabled(selected_kind == ITEM_KIND_FOLDER)
                return

            prompt = self.selected_prompt
            self.ui.widget_prompt_details.setEnabled(True)
            self.ui.lineEdit_name.setText(prompt.name)
            self.ui.radioButton_system.setChecked(prompt.scope == "system")
            self.ui.radioButton_user.setChecked(prompt.scope == "user")
            self.ui.radioButton_project.setChecked(prompt.scope == "project")
            self.ui.comboBox_type.setCurrentText(prompt.prompt_type)
            self.ui.comboBox_type.setEnabled(self.prompt_type is None and not prompt.is_system)
            self.ui.plainTextEdit_description.setPlainText(prompt.description)
            self.ui.plainTextEdit_prompt_text.setPlainText(prompt.text)
            self.ui.pushButton_duplicate_prompt.setEnabled(True)
            self.ui.toolButton_copy.setEnabled(True)
            self.ui.toolButton_paste.setEnabled(True)
            if prompt.is_system:
                self.ui.label_uneditable.show()
                self.ui.toolButton_delete.setEnabled(False)
                self.set_prompt_details_editable(False)
            else:
                self.ui.label_uneditable.hide()
                self.ui.toolButton_delete.setEnabled(True)
                self.set_prompt_details_editable(True)
        finally:
            self.form_updating = old_form_updating

    def _default_scope_for_new_prompt(self) -> str:
        if self.app.project_path != "":
            return "project"
        return "user"

    def _selected_folder_context(self) -> Tuple[str, str]:
        if len(self.ui.treeWidget_prompts.selectedItems()) == 0:
            return self.prompt_type or "general", ""
        selected_item = self.ui.treeWidget_prompts.selectedItems()[0]
        kind = str(selected_item.data(0, ITEM_KIND_ROLE) or "")
        prompt_type = str(selected_item.data(0, ITEM_PROMPT_TYPE_ROLE) or self.prompt_type or "general")
        relative_dir = self._normalize_relative_dir(selected_item.data(0, ITEM_DIRECTORY_ROLE) or "")
        if kind == ITEM_KIND_PROMPT:
            return prompt_type, relative_dir
        if kind == ITEM_KIND_FOLDER:
            return prompt_type, relative_dir
        if kind == ITEM_KIND_TYPE:
            return prompt_type, ""
        return self.prompt_type or "general", ""

    def _selection_context_for_new_prompt(self) -> tuple[str, str, str]:
        new_type = self.prompt_type or "general"
        new_scope = self._default_scope_for_new_prompt()
        new_dir = ""
        if self.selected_prompt is not None:
            new_type = self.selected_prompt.prompt_type
            new_scope = "user" if self.selected_prompt.scope == "system" else self.selected_prompt.scope
            new_dir = self.selected_prompt.directory
            return new_type, new_scope, new_dir
        if len(self.ui.treeWidget_prompts.selectedItems()) == 0:
            return new_type, new_scope, new_dir
        selected_item = self.ui.treeWidget_prompts.selectedItems()[0]
        kind = str(selected_item.data(0, ITEM_KIND_ROLE) or "")
        if kind == ITEM_KIND_PROMPT:
            new_type = str(selected_item.data(0, ITEM_PROMPT_TYPE_ROLE) or new_type)
            selected_scope = str(selected_item.data(0, ITEM_SCOPE_ROLE) or "")
            if selected_scope:
                new_scope = selected_scope
            new_dir = self._normalize_relative_dir(selected_item.data(0, ITEM_DIRECTORY_ROLE) or "")
        elif kind == ITEM_KIND_FOLDER:
            new_type = str(selected_item.data(0, ITEM_PROMPT_TYPE_ROLE) or new_type)
            new_dir = self._normalize_relative_dir(selected_item.data(0, ITEM_DIRECTORY_ROLE) or "")
            folder_scopes = [scope for scope in str(selected_item.data(0, ITEM_FOLDER_SCOPES_ROLE) or "").split("|") if scope != ""]
            if "project" in folder_scopes and self.app.project_path != "":
                new_scope = "project"
            elif "user" in folder_scopes:
                new_scope = "user"
        elif kind == ITEM_KIND_TYPE:
            new_type = str(selected_item.data(0, ITEM_PROMPT_TYPE_ROLE) or new_type)
        if new_scope == "system":
            new_scope = self._default_scope_for_new_prompt()
        if new_scope == "project" and self.app.project_path == "":
            new_scope = "user"
        return new_type, new_scope, new_dir

    def _make_unique_name(self, base_name: str, scope: str, prompt_type: str, directory: str) -> str:
        candidate = base_name
        if candidate == "":
            candidate = "my-prompt"
        if self._find_prompt(candidate, scope, prompt_type, directory) is None:
            return candidate
        counter = 2
        while self._find_prompt(f"{candidate}-{counter}", scope, prompt_type, directory) is not None:
            counter += 1
        return f"{candidate}-{counter}"

    def new_prompt(self, clicked: bool = False, pasted_prompt: Optional[Dict[str, str]] = None):
        del clicked
        new_type, new_scope, new_dir = self._selection_context_for_new_prompt()
        if new_scope == "system":
            new_scope = self._default_scope_for_new_prompt()

        if pasted_prompt is None:
            new_name = "my-prompt"
            new_description = ""
            new_text = ""
            pasted_path = ""
        else:
            requested_name = str(pasted_prompt.get("name", "") if isinstance(pasted_prompt, dict) else "").strip()
            new_name = self._normalize_name_input(requested_name)
            new_description = str(pasted_prompt.get("description", "") if isinstance(pasted_prompt, dict) else "")
            new_text = str(pasted_prompt.get("text", "") if isinstance(pasted_prompt, dict) else "")
            pasted_path = self._normalize_relative_dir(str(pasted_prompt.get("path", "") if isinstance(pasted_prompt, dict) else ""))
            pasted_scope = str(pasted_prompt.get("scope", "") if isinstance(pasted_prompt, dict) else "").strip().lower()
            if pasted_scope in prompt_scopes:
                new_scope = pasted_scope
            if pasted_path != "":
                new_dir = self._relative_dir_of_prompt_path(pasted_path)

        if new_scope == "system":
            new_scope = self._default_scope_for_new_prompt()
        if new_scope == "project" and self.app.project_path == "":
            new_scope = "user"

        if new_name != "":
            new_name = self._make_unique_name(new_name, new_scope, new_type, new_dir)
        new_prompt = EditorPromptRecord(
            scope=new_scope,
            prompt_type=new_type,
            name=new_name,
            directory=new_dir,
            description=new_description,
            text=new_text,
            original_file_path="",
            current_file_path="",
            is_system=False,
        )
        self.prompts.append(new_prompt)
        self.prompts.sort(
            key=lambda item: (
                prompt_types.index(item.prompt_type),
                item.directory.casefold(),
                prompt_scopes.index(item.scope),
                item.name.casefold(),
            )
        )
        self.selected_prompt = new_prompt
        self.fill_tree()
        self.tree_selection_changed()
        self.ui.lineEdit_name.setFocus()
        self.ui.lineEdit_name.selectAll()

    def duplicate_prompt(self):
        if self.selected_prompt is None:
            return
        source = self.selected_prompt
        duplicate_scope = "user" if source.scope == "system" else source.scope
        duplicate_prompt = {
            "name": source.name,
            "description": source.description,
            "text": source.text,
            "path": source.path(),
            "scope": duplicate_scope,
        }
        original_selection = self.selected_prompt
        self.selected_prompt = EditorPromptRecord(
            scope=duplicate_scope,
            prompt_type=source.prompt_type,
            name=source.name,
            directory=source.directory,
            description=source.description,
            text=source.text,
            original_file_path="",
            current_file_path="",
            is_system=False,
        )
        self.new_prompt(pasted_prompt=duplicate_prompt)
        if self.selected_prompt is None:
            self.selected_prompt = original_selection

    def copy_prompt_to_clipboard(self):
        if self.selected_prompt is None:
            return
        markdown_text = self.catalog.build_prompt_markdown_document(
            self.selected_prompt.name,
            self.selected_prompt.description,
            self.selected_prompt.text,
            prompt_path=self.selected_prompt.path(),
            prompt_scope=self.selected_prompt.scope,
        )
        app = QtWidgets.QApplication.instance()
        clipboard: QClipboard = app.clipboard()
        clipboard.setText(markdown_text)

    def paste_prompt_from_clipboard(self):
        app = QtWidgets.QApplication.instance()
        clipboard: QClipboard = app.clipboard()
        raw_text = clipboard.text()
        if str(raw_text).strip() == "":
            Message(self.app, _("Edit prompts"), _("Clipboard is empty."), "warning").exec()
            return
        try:
            metadata, body = self.catalog.parse_prompt_markdown_document(raw_text)
        except Exception:
            Message(self.app, _("Edit prompts"), _("Clipboard does not contain a valid Markdown prompt."), "warning").exec()
            return
        pasted_prompt = {
            "name": str(metadata.get("name", "") if isinstance(metadata, dict) else "").strip(),
            "description": str(metadata.get("description", "") if isinstance(metadata, dict) else "").strip(),
            "path": self._normalize_relative_dir(str(metadata.get("path", "") if isinstance(metadata, dict) else "")),
            "scope": str(
                (metadata.get("Scope", "") if isinstance(metadata, dict) else "")
                or (metadata.get("scope", "") if isinstance(metadata, dict) else "")
            ).strip().lower(),
            "text": body,
        }
        self.new_prompt(pasted_prompt=pasted_prompt)

    def delete_prompt(self):
        if self.selected_prompt is None or self.selected_prompt.is_system:
            return
        msg = _('Do you really want to delete ') + f'"{self.selected_prompt.name_and_scope()}"?'
        ui = DialogConfirmDelete(self.app, msg, _('Delete Prompt'))
        if not ui.exec():
            return
        self.prompts.remove(self.selected_prompt)
        self.selected_prompt = None
        self.fill_tree()
        self.tree_selection_changed()

    def delete_selected(self):
        if len(self.ui.treeWidget_prompts.selectedItems()) == 0:
            return
        selected_item = self.ui.treeWidget_prompts.selectedItems()[0]
        kind = str(selected_item.data(0, ITEM_KIND_ROLE) or "")
        if kind == ITEM_KIND_FOLDER:
            self.delete_folder()
            return
        if kind == ITEM_KIND_PROMPT:
            self.delete_prompt()

    def _folder_absolute_path(self, scope: str, prompt_type: str, relative_dir: str) -> str:
        type_root = self._type_root_dir(scope, prompt_type)
        if type_root == "":
            return ""
        normalized_dir = self._normalize_relative_dir(relative_dir)
        if normalized_dir == "":
            return type_root
        return os.path.join(type_root, *normalized_dir.split("/"))

    def _folder_scopes_for_item(self, item: QtWidgets.QTreeWidgetItem) -> List[str]:
        return [scope for scope in str(item.data(0, ITEM_FOLDER_SCOPES_ROLE) or "").split("|") if scope != ""]

    def _choose_scope_for_folder_operation(self, item: QtWidgets.QTreeWidgetItem, action_label: str) -> Optional[str]:
        scopes = self._folder_scopes_for_item(item)
        if len(scopes) <= 1:
            return scopes[0] if scopes else None
        chosen_scope, ok = QtWidgets.QInputDialog.getItem(
            self,
            _('Choose scope'),
            _('The selected folder exists in multiple scopes. Choose the scope for this operation:'),
            scopes,
            0,
            False,
        )
        if not ok:
            return None
        return str(chosen_scope)

    def _validate_folder_name(self, name: str) -> Optional[str]:
        normalized = str(name if name is not None else "").strip()
        if normalized == "":
            Message(self.app, _('Edit prompts'), _('The folder name cannot be empty.'), "warning").exec()
            return None
        if "/" in normalized or "\\" in normalized:
            Message(self.app, _('Edit prompts'), _('Folder names must not contain "/" or "\\".'), "warning").exec()
            return None
        if normalized.startswith("_"):
            Message(self.app, _('Edit prompts'), _('Folder names must not start with "_".'), "warning").exec()
            return None
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", normalized):
            Message(
                self.app,
                _('Edit prompts'),
                _('Folder names must be filesystem-compatible. Use lowercase letters, numbers, hyphens, and underscores only.'),
                "warning",
            ).exec()
            return None
        return normalized

    def _folder_conflicts_exist(self, scope: str, prompt_type: str, target_dir: str) -> bool:
        target_abs = self._folder_absolute_path(scope, prompt_type, target_dir)
        return target_abs != "" and os.path.exists(target_abs)

    def new_folder(self) -> None:
        prompt_type, parent_dir = self._selected_folder_context()
        target_scope = "project" if self.app.project_path != "" else "user"
        folder_name, ok = QtWidgets.QInputDialog.getText(self, _('New folder'), _('Folder name:'))
        if not ok:
            return
        validated_name = self._validate_folder_name(folder_name)
        if validated_name is None:
            return
        new_relative_dir = self._join_prompt_path(parent_dir, validated_name)
        target_abs = self._folder_absolute_path(target_scope, prompt_type, new_relative_dir)
        if target_abs == "":
            return
        if os.path.exists(target_abs):
            Message(self.app, _('Edit prompts'), _('A folder with this name already exists.'), "warning").exec()
            return
        try:
            os.makedirs(target_abs, exist_ok=False)
        except OSError as err:
            Message(self.app, _('Edit prompts'), _('Could not create folder: ') + str(err), "warning").exec()
            return
        self._refresh_tree_from_memory()

    def rename_folder(self) -> None:
        if len(self.ui.treeWidget_prompts.selectedItems()) == 0:
            return
        selected_item = self.ui.treeWidget_prompts.selectedItems()[0]
        if selected_item.data(0, ITEM_KIND_ROLE) != ITEM_KIND_FOLDER:
            return
        scope = self._choose_scope_for_folder_operation(selected_item, "rename")
        if scope is None:
            return
        prompt_type = str(selected_item.data(0, ITEM_PROMPT_TYPE_ROLE) or "")
        relative_dir = self._normalize_relative_dir(selected_item.data(0, ITEM_DIRECTORY_ROLE) or "")
        current_name = relative_dir.rsplit("/", 1)[-1]
        new_name, ok = QtWidgets.QInputDialog.getText(self, _('Rename folder'), _('Folder name:'), text=current_name)
        if not ok:
            return
        validated_name = self._validate_folder_name(new_name)
        if validated_name is None or validated_name == current_name:
            return
        parent_dir = self._relative_dir_of_prompt_path(relative_dir)
        target_dir = self._join_prompt_path(parent_dir, validated_name)
        source_abs = self._folder_absolute_path(scope, prompt_type, relative_dir)
        target_abs = self._folder_absolute_path(scope, prompt_type, target_dir)
        if source_abs == "" or target_abs == "":
            return
        if os.path.exists(target_abs):
            Message(self.app, _('Edit prompts'), _('A folder with the target name already exists.'), "warning").exec()
            return
        try:
            os.rename(source_abs, target_abs)
        except OSError as err:
            Message(self.app, _('Edit prompts'), _('Could not rename folder: ') + str(err), "warning").exec()
            return
        for prompt in self.prompts:
            if prompt.scope != scope or prompt.prompt_type != prompt_type:
                continue
            if prompt.directory == relative_dir or prompt.directory.startswith(relative_dir + "/"):
                suffix = prompt.directory[len(relative_dir):].lstrip("/")
                prompt.directory = self._join_prompt_path(target_dir, suffix) if suffix != "" else target_dir
        self._refresh_tree_from_memory()

    def delete_folder(self) -> None:
        if len(self.ui.treeWidget_prompts.selectedItems()) == 0:
            return
        selected_item = self.ui.treeWidget_prompts.selectedItems()[0]
        if selected_item.data(0, ITEM_KIND_ROLE) != ITEM_KIND_FOLDER:
            return
        scope = self._choose_scope_for_folder_operation(selected_item, "delete")
        if scope is None:
            return
        prompt_type = str(selected_item.data(0, ITEM_PROMPT_TYPE_ROLE) or "")
        relative_dir = self._normalize_relative_dir(selected_item.data(0, ITEM_DIRECTORY_ROLE) or "")
        msg = _('Do you really want to delete the folder "') + relative_dir + _('" and all prompts it contains?')
        ui = DialogConfirmDelete(self.app, msg, _('Delete Folder'))
        if not ui.exec():
            return
        target_abs = self._folder_absolute_path(scope, prompt_type, relative_dir)
        try:
            shutil.rmtree(target_abs)
        except OSError as err:
            Message(self.app, _('Edit prompts'), _('Could not delete folder: ') + str(err), "warning").exec()
            return
        self.prompts = [
            prompt for prompt in self.prompts
            if not (prompt.scope == scope and prompt.prompt_type == prompt_type and (prompt.directory == relative_dir or prompt.directory.startswith(relative_dir + "/")))
        ]
        if self.selected_prompt is not None and self.selected_prompt.scope == scope and self.selected_prompt.prompt_type == prompt_type:
            if self.selected_prompt.directory == relative_dir or self.selected_prompt.directory.startswith(relative_dir + "/"):
                self.selected_prompt = None
        self._refresh_tree_from_memory()

    def open_tree_context_menu(self, position) -> None:
        item = self.ui.treeWidget_prompts.itemAt(position)
        if item is not None:
            self.ui.treeWidget_prompts.setCurrentItem(item)
        menu = QtWidgets.QMenu(self)
        selected_item = self.ui.treeWidget_prompts.currentItem()
        kind = str(selected_item.data(0, ITEM_KIND_ROLE) or "") if selected_item is not None else ""
        if kind in (ITEM_KIND_TYPE, ITEM_KIND_FOLDER, ITEM_KIND_PROMPT) or selected_item is None:
            new_folder_action = QAction(_('New folder'), self)
            new_folder_action.triggered.connect(self.new_folder)
            menu.addAction(new_folder_action)
        if kind == ITEM_KIND_FOLDER:
            rename_folder_action = QAction(_('Rename folder'), self)
            delete_folder_action = QAction(_('Delete folder'), self)
            rename_folder_action.triggered.connect(self.rename_folder)
            delete_folder_action.triggered.connect(self.delete_folder)
            menu.addAction(rename_folder_action)
            menu.addAction(delete_folder_action)
        if not menu.isEmpty():
            menu.exec(self.ui.treeWidget_prompts.viewport().mapToGlobal(position))

    def _move_prompt_to(self, prompt: EditorPromptRecord, new_type: str, new_dir: str) -> bool:
        if prompt.is_system:
            Message(self.app, _('Edit prompts'), _('System prompts cannot be moved.'), "warning").exec()
            return False
        new_type = self.catalog.normalize_prompt_type(new_type) or prompt.prompt_type
        new_dir = self._normalize_relative_dir(new_dir)
        if prompt.prompt_type != new_type:
            answer = QtWidgets.QMessageBox.question(
                self,
                _('Change prompt type'),
                _('Do you really want to change the prompt type from "') + prompt.prompt_type + _('\" to \"') + new_type + _('\"?'),
            )
            if answer != QtWidgets.QMessageBox.StandardButton.Yes:
                return False
        if self._find_prompt(prompt.name, prompt.scope, new_type, new_dir) is not None:
            Message(self.app, _('Edit prompts'), _('A prompt with the same name already exists in the target folder.'), "warning").exec()
            return False
        prompt.prompt_type = new_type
        prompt.directory = new_dir
        self.prompts.sort(
            key=lambda item: (
                prompt_types.index(item.prompt_type),
                item.directory.casefold(),
                prompt_scopes.index(item.scope),
                item.name.casefold(),
            )
        )
        self.selected_prompt = prompt
        self.fill_tree()
        QtCore.QTimer.singleShot(0, self.fill_tree)
        return True

    def _drop_target_context(self, item: Optional[QtWidgets.QTreeWidgetItem]) -> Tuple[Optional[str], Optional[str]]:
        if item is None:
            return None, None
        kind = str(item.data(0, ITEM_KIND_ROLE) or "")
        if kind == ITEM_KIND_TYPE:
            return str(item.data(0, ITEM_PROMPT_TYPE_ROLE) or ""), ""
        if kind == ITEM_KIND_FOLDER:
            return str(item.data(0, ITEM_PROMPT_TYPE_ROLE) or ""), self._normalize_relative_dir(item.data(0, ITEM_DIRECTORY_ROLE) or "")
        if kind == ITEM_KIND_PROMPT:
            return str(item.data(0, ITEM_PROMPT_TYPE_ROLE) or ""), self._normalize_relative_dir(item.data(0, ITEM_DIRECTORY_ROLE) or "")
        return None, None

    def eventFilter(self, source, event):
        if source in (self.ui.treeWidget_prompts, self.ui.treeWidget_prompts.viewport()):
            if event.type() in (QtCore.QEvent.Type.DragEnter, QtCore.QEvent.Type.DragMove):
                if self.selected_prompt is not None and not self.selected_prompt.is_system:
                    event.accept()
                    return True
            if event.type() == QtCore.QEvent.Type.Drop:
                if self.selected_prompt is None or self.selected_prompt.is_system:
                    event.ignore()
                    return True
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                if source is self.ui.treeWidget_prompts:
                    pos = self.ui.treeWidget_prompts.viewport().mapFrom(self.ui.treeWidget_prompts, pos)
                target_item = self.ui.treeWidget_prompts.itemAt(pos)
                new_type, new_dir = self._drop_target_context(target_item)
                if new_type is None:
                    event.ignore()
                    return True
                self._move_prompt_to(self.selected_prompt, new_type, new_dir)
                event.accept()
                return True
        return super().eventFilter(source, event)

    def set_prompt_details_editable(self, editable):
        self.ui.lineEdit_name.setReadOnly(not editable)
        self.ui.radioButton_system.setDisabled(True)
        self.ui.radioButton_user.setDisabled(not editable)
        self.ui.radioButton_project.setDisabled((not editable) or self.app.project_path == "")
        self.ui.comboBox_type.setDisabled(not editable or self.prompt_type is not None)
        self.ui.plainTextEdit_description.setReadOnly(not editable)
        self.ui.plainTextEdit_prompt_text.setReadOnly(not editable)

    def _normalize_name_input(self, value: str) -> str:
        return str(value if value is not None else "").strip()

    def _validate_prompt_name(self, name: str, prompt_type: str, scope: str,
                              current_prompt: Optional[EditorPromptRecord] = None,
                              directory: str = "") -> Optional[str]:
        normalized = self._normalize_name_input(name)
        if normalized == "":
            Message(self.app, _('Edit prompts'), _('The name cannot be empty.'), "warning").exec()
            return None
        if "/" in normalized or "\\" in normalized:
            Message(self.app, _('Edit prompts'), _('Prompt names must not contain "/" or "\\". Use folders in the tree instead.'), "warning").exec()
            return None
        if normalized.startswith("_"):
            Message(self.app, _('Edit prompts'), _('Prompt names must not start with "_".'), "warning").exec()
            return None
        if len(normalized) > 64:
            Message(self.app, _('Edit prompts'), _('The name must be no longer than 64 characters.'), "warning").exec()
            return None
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", normalized):
            Message(
                self.app,
                _('Edit prompts'),
                _('Prompt names must be filesystem-compatible. Use lowercase letters, numbers, hyphens, and underscores only.'),
                "warning",
            ).exec()
            return None
        for prompt in self.prompts:
            if prompt is current_prompt:
                continue
            if (
                prompt.prompt_type == prompt_type
                and prompt.scope == scope
                and prompt.directory.casefold() == self._normalize_relative_dir(directory).casefold()
                and prompt.name.casefold() == normalized.casefold()
            ):
                Message(
                    self.app,
                    _('Edit prompts'),
                    _('The name of the prompt must be unique within its folder, type, and scope.'),
                    "warning",
                ).exec()
                return None
        return normalized

    def prompt_details_edited(self):
        if self.form_updating or self.selected_prompt is None or self.selected_prompt.is_system:
            return
        prompt = self.selected_prompt
        sender_widget = QtWidgets.QApplication.instance().sender()

        if self.ui.radioButton_user.isChecked():
            new_scope = "user"
        elif self.ui.radioButton_project.isChecked():
            new_scope = "project"
        else:
            new_scope = prompt.scope
        new_type = self.catalog.normalize_prompt_type(self.ui.comboBox_type.currentText()) or prompt.prompt_type

        old_form_updating = self.form_updating
        self.form_updating = True
        try:
            if sender_widget is self.ui.lineEdit_name:
                validated_name = self._validate_prompt_name(
                    self.ui.lineEdit_name.text(),
                    new_type,
                    new_scope,
                    current_prompt=prompt,
                    directory=prompt.directory,
                )
                if validated_name is None:
                    self.ui.lineEdit_name.setText(prompt.name)
                    QtCore.QTimer.singleShot(0, self.ui.lineEdit_name.setFocus)
                    return
                prompt.name = validated_name
                self.ui.lineEdit_name.setText(validated_name)
            else:
                prompt.description = self.ui.plainTextEdit_description.toPlainText()
                prompt.text = self.ui.plainTextEdit_prompt_text.toPlainText()

            if sender_widget in (
                self.ui.radioButton_user,
                self.ui.radioButton_project,
                self.ui.comboBox_type,
            ):
                validated_name = self._validate_prompt_name(
                    prompt.name,
                    new_type,
                    new_scope,
                    current_prompt=prompt,
                    directory=prompt.directory,
                )
                if validated_name is None:
                    self.ui.radioButton_user.setChecked(prompt.scope == "user")
                    self.ui.radioButton_project.setChecked(prompt.scope == "project")
                    self.ui.comboBox_type.setCurrentText(prompt.prompt_type)
                    return
                prompt.scope = new_scope
                prompt.prompt_type = new_type
                prompt.name = validated_name
            elif sender_widget not in (self.ui.plainTextEdit_description, self.ui.plainTextEdit_prompt_text):
                prompt.description = self.ui.plainTextEdit_description.toPlainText()
                prompt.text = self.ui.plainTextEdit_prompt_text.toPlainText()

            if sender_widget in (
                self.ui.lineEdit_name,
                self.ui.radioButton_user,
                self.ui.radioButton_project,
                self.ui.comboBox_type,
            ):
                self.prompts.sort(
                    key=lambda item: (
                        prompt_types.index(item.prompt_type),
                        item.directory.casefold(),
                        prompt_scopes.index(item.scope),
                        item.name.casefold(),
                    )
                )
                self.fill_tree()
        finally:
            self.form_updating = old_form_updating

    def _target_file_path(self, prompt: EditorPromptRecord) -> str:
        type_root = self._type_root_dir(prompt.scope, prompt.prompt_type)
        if type_root == "" or prompt.name == "":
            return ""
        rel_parts = [part for part in self._normalize_relative_dir(prompt.directory).split("/") if part != ""]
        return os.path.join(type_root, *rel_parts, prompt.name + ".md")

    def _cleanup_empty_parent_dirs(self, file_path: str, scope: str) -> None:
        del file_path, scope
        return

    def ok(self):
        for prompt in self.prompts:
            if prompt.is_system:
                continue
            validated_name = self._validate_prompt_name(
                prompt.name,
                prompt.prompt_type,
                prompt.scope,
                current_prompt=prompt,
                directory=prompt.directory,
            )
            if validated_name is None:
                return
            prompt.name = validated_name

        original_paths = {
            os.path.normcase(os.path.normpath(prompt.original_file_path)): prompt
            for prompt in self.prompts
            if not prompt.is_system and str(prompt.original_file_path).strip() != ""
        }
        final_targets: Dict[str, EditorPromptRecord] = {}
        for prompt in self.prompts:
            if prompt.is_system:
                continue
            target_path = self._target_file_path(prompt)
            if target_path == "":
                Message(self.app, _('Edit prompts'), _('Could not determine a target path for one prompt.'), "warning").exec()
                return
            normalized_target = os.path.normcase(os.path.normpath(target_path))
            existing_prompt = final_targets.get(normalized_target)
            if existing_prompt is not None and existing_prompt is not prompt:
                Message(self.app, _('Edit prompts'), _('Two prompts would be written to the same file path.'), "warning").exec()
                return
            final_targets[normalized_target] = prompt
            prompt.current_file_path = target_path

        for normalized_target, prompt in final_targets.items():
            target_path = prompt.current_file_path
            if os.path.exists(target_path) and normalized_target not in original_paths:
                Message(
                    self.app,
                    _('Edit prompts'),
                    _('Saving would overwrite an existing prompt file that is not part of the current editor session: ')
                    + target_path,
                    "warning",
                ).exec()
                return

        try:
            for prompt in self.prompts:
                if prompt.is_system:
                    continue
                target_path = prompt.current_file_path
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                markdown_text = self.catalog.build_prompt_markdown_document(
                    prompt.name,
                    prompt.description,
                    prompt.text,
                    prompt_path=prompt.path(),
                    prompt_scope=prompt.scope,
                )
                with open(target_path, "w", encoding="utf-8") as handle:
                    handle.write(markdown_text)

            final_target_keys = set(final_targets.keys())
            for normalized_original, original_prompt in original_paths.items():
                if normalized_original in final_target_keys:
                    continue
                try:
                    os.remove(original_prompt.original_file_path)
                    self._cleanup_empty_parent_dirs(original_prompt.original_file_path, original_prompt.scope)
                except OSError:
                    logger.warning("Could not delete obsolete AI prompt file: %s", original_prompt.original_file_path)
        except OSError as err:
            Message(self.app, _('Edit prompts'), _('Could not save the prompt files: ') + str(err), "warning").exec()
            return

        if self.prompt_type is not None and (
            self.selected_prompt is None or self.selected_prompt.prompt_type != self.prompt_type
        ):
            msg = _(f'You must select a {self.prompt_type} prompt.')
            Message(self.app, _('Edit prompts'), msg, "warning").exec()
            return
        self.accept()

    def cancel(self):
        self.reject()
