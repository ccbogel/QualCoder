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
from typing import Dict, List, Optional

from PyQt6 import QtCore, QtWidgets, QtGui
from PyQt6.QtGui import QClipboard, QKeySequence, QShortcut
from PyQt6.QtCore import Qt
import qtawesome as qta

from .ai_agent_prompts import AiAgentPromptsCatalog
from .GUI.ui_ai_edit_prompts import Ui_Dialog_AiPrompts
from .helpers import Message
from .confirm_delete import DialogConfirmDelete


path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

prompt_types = [
    "search",
    "code_analysis",
    "topic_exploration",
    "text_analysis",
]

prompt_types_descriptions = {
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
    description: str
    text: str
    original_file_path: str
    current_file_path: str
    is_system: bool

    def name_and_scope(self) -> str:
        return self.name + f" ({self.scope})"


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


class DialogAiEditPrompts(QtWidgets.QDialog):
    """Dialog to edit prompts from the Markdown-based AI prompt system."""

    def __init__(self, app_, prompt_type=None):
        self.app = app_
        self.catalog = AiAgentPromptsCatalog(app_)
        self.prompt_type = self.catalog.normalize_prompt_type(prompt_type)
        self.prompts: List[EditorPromptRecord] = []
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
                QtCore.QRegularExpression(r"[a-z0-9-]*(?:/[a-z0-9-]*)*"),
                self.ui.lineEdit_name,
            )
        )
        self._reload_prompts()
        if self.prompt_type is None:
            self.ui.treeWidget_prompts.collapseAll()

        self.ui.treeWidget_prompts.itemSelectionChanged.connect(self.tree_selection_changed)
        self.ui.pushButton_new_prompt.clicked.connect(self.new_prompt)
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
        self.ui.toolButton_delete.clicked.connect(self.delete_prompt)

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

    def _reload_prompts(self) -> None:
        self.prompts = []
        for prompt in self.catalog.list_prompt_variants(include_internal=True, apply_init=False):
            prompt_type = self.catalog.prompt_type_from_name(prompt.name)
            if prompt_type is None:
                continue
            if self.prompt_type is not None and prompt_type != self.prompt_type:
                continue
            basename = self.catalog.prompt_name_within_type(prompt.name).rsplit("/", 1)[-1]
            if basename.startswith("_"):
                continue
            self.prompts.append(
                EditorPromptRecord(
                    scope=prompt.scope,
                    prompt_type=prompt_type,
                    name=self.catalog.prompt_name_within_type(prompt.name),
                    description=str(prompt.description if prompt.description is not None else ""),
                    text=str(prompt.content if prompt.content is not None else ""),
                    original_file_path=prompt.file_path,
                    current_file_path=prompt.file_path,
                    is_system=(prompt.scope == "system"),
                )
            )
        self.prompts.sort(key=lambda item: (prompt_types.index(item.prompt_type), prompt_scopes.index(item.scope), item.name.casefold()))
        self.fill_tree()

    def _type_icon(self, prompt_type: str):
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

    def fill_tree(self):
        old_form_updating = self.form_updating
        self.form_updating = True
        try:
            selected_path = ""
            if len(self.ui.treeWidget_prompts.selectedItems()) > 0:
                selected_path = "|".join(self.tree_get_item_path(self.ui.treeWidget_prompts.selectedItems()[0]))

            self.ui.treeWidget_prompts.clear()
            for prompt_type in prompt_types:
                if self.prompt_type is not None and prompt_type != self.prompt_type:
                    continue
                type_item = QtWidgets.QTreeWidgetItem(self.ui.treeWidget_prompts)
                type_item.setText(0, prompt_type)
                type_item.setToolTip(0, prompt_types_descriptions.get(prompt_type, ""))
                type_item.setIcon(0, self._type_icon(prompt_type))

                for scope in prompt_scopes:
                    scope_item = QtWidgets.QTreeWidgetItem(type_item)
                    scope_item.setText(0, scope)
                    scope_item.setToolTip(0, prompt_scope_descriptions.get(scope, ""))
                    scope_item.setIcon(0, self.app.ai.prompt_scope_icon())
                    for prompt in [p for p in self.prompts if p.prompt_type == prompt_type and p.scope == scope]:
                        prompt_item = QtWidgets.QTreeWidgetItem(scope_item)
                        prompt_item.setText(0, prompt.name)
                        prompt_item.setToolTip(0, prompt.description)
                        prompt_item.setIcon(0, self.app.ai.prompt_icon())
                        if prompt is self.selected_prompt:
                            prompt_item.setSelected(True)
                        elif selected_path != "" and "|".join([prompt_type, scope, prompt.name]) == selected_path:
                            prompt_item.setSelected(True)

            if len(self.ui.treeWidget_prompts.selectedItems()) == 0 and selected_path != "":
                item = self.tree_find_item_by_path(selected_path.split("|"))
                if item is not None:
                    item.setSelected(True)
                    item.setExpanded(True)
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

    def _find_prompt(self, name: str, scope: str, prompt_type: str) -> Optional[EditorPromptRecord]:
        for prompt in self.prompts:
            if prompt.name == name and prompt.scope == scope and prompt.prompt_type == prompt_type:
                return prompt
        return None

    def tree_selection_changed(self):
        if self.form_updating:
            return
        self.selected_prompt = None
        if len(self.ui.treeWidget_prompts.selectedItems()) > 0:
            selected_item = self.ui.treeWidget_prompts.selectedItems()[0]
            selected_item.setExpanded(True)
            if get_item_level(selected_item) == 2:
                selected_name = selected_item.text(0)
                selected_scope = selected_item.parent().text(0)
                selected_type = selected_item.parent().parent().text(0)
                self.selected_prompt = self._find_prompt(selected_name, selected_scope, selected_type)

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
                self.ui.toolButton_delete.setEnabled(False)
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

    def _selection_context_for_new_prompt(self) -> tuple[str, str]:
        new_type = self.prompt_type or "search"
        new_scope = self._default_scope_for_new_prompt()
        if self.selected_prompt is not None:
            new_type = self.selected_prompt.prompt_type
            new_scope = "user" if self.selected_prompt.scope == "system" else self.selected_prompt.scope
            return new_type, new_scope
        if len(self.ui.treeWidget_prompts.selectedItems()) == 0:
            return new_type, new_scope
        selected_item = self.ui.treeWidget_prompts.selectedItems()[0]
        item_level = get_item_level(selected_item)
        if item_level == 0:
            new_type = selected_item.text(0)
        elif item_level == 1:
            new_type = selected_item.parent().text(0)
            new_scope = selected_item.text(0)
        if new_scope == "system":
            new_scope = self._default_scope_for_new_prompt()
        if new_scope == "project" and self.app.project_path == "":
            new_scope = "user"
        return new_type, new_scope

    def _make_unique_name(self, base_name: str, scope: str, prompt_type: str) -> str:
        candidate = base_name
        if candidate == "":
            candidate = "my-prompt"
        if self._find_prompt(candidate, scope, prompt_type) is None:
            return candidate
        counter = 2
        while self._find_prompt(f"{candidate}-{counter}", scope, prompt_type) is not None:
            counter += 1
        return f"{candidate}-{counter}"

    def new_prompt(self, clicked: bool = False, pasted_prompt: Optional[Dict[str, str]] = None):
        new_type, new_scope = self._selection_context_for_new_prompt()
        if new_scope == "system":
            new_scope = self._default_scope_for_new_prompt()

        if pasted_prompt is None:
            new_name = "my-prompt"
            new_description = ""
            new_text = ""
        else:
            requested_name = str(pasted_prompt.get("name", "") if isinstance(pasted_prompt, dict) else "").strip()
            new_name = self._normalize_name_input(requested_name)
            new_description = str(pasted_prompt.get("description", "") if isinstance(pasted_prompt, dict) else "")
            new_text = str(pasted_prompt.get("text", "") if isinstance(pasted_prompt, dict) else "")

        if new_name != "":
            new_name = self._make_unique_name(new_name, new_scope, new_type)
        new_prompt = EditorPromptRecord(
            scope=new_scope,
            prompt_type=new_type,
            name=new_name,
            description=new_description,
            text=new_text,
            original_file_path="",
            current_file_path="",
            is_system=False,
        )
        self.prompts.append(new_prompt)
        self.prompts.sort(key=lambda item: (prompt_types.index(item.prompt_type), prompt_scopes.index(item.scope), item.name.casefold()))
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
        }
        original_selection = self.selected_prompt
        self.selected_prompt = EditorPromptRecord(
            scope=duplicate_scope,
            prompt_type=source.prompt_type,
            name=source.name,
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
            self.selected_prompt.description,
            self.selected_prompt.text,
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

    def set_prompt_details_editable(self, editable):
        self.ui.lineEdit_name.setReadOnly(not editable)
        self.ui.radioButton_system.setDisabled(True)
        self.ui.radioButton_user.setDisabled(not editable)
        self.ui.radioButton_project.setDisabled((not editable) or self.app.project_path == "")
        self.ui.comboBox_type.setDisabled(not editable or self.prompt_type is not None)
        self.ui.plainTextEdit_description.setReadOnly(not editable)
        self.ui.plainTextEdit_prompt_text.setReadOnly(not editable)

    def _normalize_name_input(self, value: str) -> str:
        text = str(value if value is not None else "").strip()
        if text == "":
            return ""
        parts = [segment.strip() for segment in text.replace("\\", "/").split("/")]
        parts = [segment for segment in parts if segment != ""]
        return "/".join(parts)

    def _validate_prompt_name(self, name: str, prompt_type: str, scope: str,
                              current_prompt: Optional[EditorPromptRecord] = None) -> Optional[str]:
        normalized = self._normalize_name_input(name)
        if normalized == "":
            Message(self.app, _('Edit prompts'), _('The name cannot be empty.'), "warning").exec()
            return None
        segments = normalized.split("/")
        for segment in segments:
            if segment.startswith("_"):
                Message(self.app, _('Edit prompts'), _('Prompt names must not start with "_".'), "warning").exec()
                return None
            if self.catalog.slugify_prompt_filename(segment) != segment:
                Message(
                    self.app,
                    _('Edit prompts'),
                    _('Prompt names must be filesystem-compatible. Use lowercase letters, numbers, and hyphens only.'),
                    "warning",
                ).exec()
                return None
        for prompt in self.prompts:
            if prompt is current_prompt:
                continue
            if prompt.prompt_type == prompt_type and prompt.scope == scope and prompt.name.casefold() == normalized.casefold():
                Message(
                    self.app,
                    _('Edit prompts'),
                    _('The name of the prompt must be unique within its type and scope.'),
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
                validated_name = self._validate_prompt_name(self.ui.lineEdit_name.text(), new_type, new_scope, current_prompt=prompt)
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
                validated_name = self._validate_prompt_name(prompt.name, new_type, new_scope, current_prompt=prompt)
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
                self.prompts.sort(key=lambda item: (prompt_types.index(item.prompt_type), prompt_scopes.index(item.scope), item.name.casefold()))
                self.fill_tree()
        finally:
            self.form_updating = old_form_updating

    def _target_file_path(self, prompt: EditorPromptRecord) -> str:
        root = self.catalog.prompt_root_for_scope(prompt.scope)
        folder = self.catalog.prompt_folder_for_type(prompt.prompt_type)
        rel_parts = [part for part in prompt.name.split("/") if part != ""]
        if root == "" or folder == "" or len(rel_parts) == 0:
            return ""
        return os.path.join(root, folder, *rel_parts) + ".md"

    def _cleanup_empty_parent_dirs(self, file_path: str, scope: str) -> None:
        root = self.catalog.prompt_root_for_scope(scope)
        if root == "":
            return
        current_dir = os.path.dirname(file_path)
        root_norm = os.path.normcase(os.path.normpath(root))
        while current_dir and os.path.normcase(os.path.normpath(current_dir)) != root_norm:
            try:
                os.rmdir(current_dir)
            except OSError:
                break
            current_dir = os.path.dirname(current_dir)

    def ok(self):
        for prompt in self.prompts:
            if prompt.is_system:
                continue
            validated_name = self._validate_prompt_name(prompt.name, prompt.prompt_type, prompt.scope, current_prompt=prompt)
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
                    os.path.basename(target_path)[:-3],
                    prompt.description,
                    prompt.text,
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
