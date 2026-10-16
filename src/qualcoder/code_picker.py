# -*- coding: utf-8 -*-

"""
Keyboard-first searchable code picker for QualCoder text coding.
"""

from PyQt6 import QtCore, QtWidgets


class DialogFindAndApplyCode(QtWidgets.QDialog):
    """Search all project codes and return one selected code dictionary."""

    def __init__(self, app, codes, categories, parent=None):
        super().__init__(parent)
        self.app = app
        self.codes = list(codes)
        self.categories = list(categories)
        self.selected_code = None

        self.setWindowTitle(_("Find and apply code"))
        self.setWindowFlags(
            self.windowFlags()
            & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint
        )
        self.setMinimumWidth(520)
        self.setStyleSheet(
            f"* {{font-size:{self.app.settings['fontsize']}pt; "
            f"font-family:{self.app.settings['font']};}}"
        )

        self._code_by_cid = {code["cid"]: code for code in self.codes}
        self._category_by_id = {
            category["catid"]: category for category in self.categories
        }

        self.search_label = QtWidgets.QLabel(_("Search codes:"))
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText(_("Type part of a code name"))
        self.search_edit.setClearButtonEnabled(True)

        self.result_list = QtWidgets.QListWidget()
        self.result_list.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self.result_list.setAlternatingRowColors(True)

        self.no_results_label = QtWidgets.QLabel(_("No matching codes"))
        self.no_results_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.no_results_label.hide()

        self.help_label = QtWidgets.QLabel(
            _("Up/Down: choose code    Enter: apply    Esc: cancel")
        )
        self.help_label.setStyleSheet("color: gray;")

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.search_label)
        layout.addWidget(self.search_edit)
        layout.addWidget(self.result_list)
        layout.addWidget(self.no_results_label)
        layout.addWidget(self.help_label)

        self.search_edit.textChanged.connect(self.filter_codes)
        self.search_edit.installEventFilter(self)
        self.result_list.itemDoubleClicked.connect(self.accept_selection)

        self.filter_codes("")
        self.search_edit.setFocus()

    def _category_path(self, category_id, seen=None):
        """Return category ancestry, safely handling malformed circular paths."""
        if category_id is None:
            return []

        if seen is None:
            seen = set()

        if category_id in seen:
            return []

        seen.add(category_id)
        category = self._category_by_id.get(category_id)
        if category is None:
            return []

        return self._category_path(
            category.get("supercatid"), seen
        ) + [category["name"]]

    def _code_path(self, code, seen=None):
        """Return category/sub-code ancestry excluding the code's own name."""
        if seen is None:
            seen = set()

        cid = code["cid"]
        if cid in seen:
            return []

        seen.add(cid)
        parent_code_id = code.get("supercid")

        if parent_code_id is not None:
            parent_code = self._code_by_cid.get(parent_code_id)
            if parent_code is not None:
                return self._code_path(parent_code, seen) + [parent_code["name"]]

        return self._category_path(code.get("catid"))

    def _display_text(self, code):
        """Show code name and hierarchy context in a single result row."""
        path = self._code_path(code)
        if path:
            return f"{code['name']}    {' > '.join(path)}"
        return code["name"]

    def filter_codes(self, query):
        """Case-insensitive substring filtering of all project code names."""
        query = query.strip().casefold()

        matching_codes = [
            code
            for code in self.codes
            if query in code["name"].casefold()
        ]
        matching_codes.sort(key=lambda code: code["name"].casefold())

        self.result_list.clear()

        for code in matching_codes:
            item = QtWidgets.QListWidgetItem(self._display_text(code))
            item.setData(QtCore.Qt.ItemDataRole.UserRole, code)
            if code.get("memo"):
                item.setToolTip(code["memo"])
            self.result_list.addItem(item)

        has_results = bool(matching_codes)
        self.result_list.setVisible(has_results)
        self.no_results_label.setVisible(not has_results)

        if has_results:
            self.result_list.setCurrentRow(0)

    def accept_selection(self, item=None):
        """Accept the highlighted code, if one exists."""
        if item is None:
            item = self.result_list.currentItem()

        if item is None:
            return

        self.selected_code = item.data(QtCore.Qt.ItemDataRole.UserRole)
        self.accept()

    def _move_selection(self, direction):
        """Move the active result row while keeping focus in the search field."""
        count = self.result_list.count()
        if count == 0:
            return

        current_row = self.result_list.currentRow()
        if current_row < 0:
            current_row = 0

        new_row = max(0, min(count - 1, current_row + direction))
        self.result_list.setCurrentRow(new_row)

        current_item = self.result_list.currentItem()
        if current_item is not None:
            self.result_list.scrollToItem(
                current_item,
                QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible,
            )

    def eventFilter(self, watched, event):
        """Forward navigation keys from the search field to the result list."""
        if watched is self.search_edit and event.type() == QtCore.QEvent.Type.KeyPress:
            key = event.key()

            if key == QtCore.Qt.Key.Key_Down:
                self._move_selection(1)
                return True

            if key == QtCore.Qt.Key.Key_Up:
                self._move_selection(-1)
                return True

            if key == QtCore.Qt.Key.Key_PageDown:
                self._move_selection(10)
                return True

            if key == QtCore.Qt.Key.Key_PageUp:
                self._move_selection(-10)
                return True

            if key == QtCore.Qt.Key.Key_Home:
                self.result_list.setCurrentRow(0)
                return True

            if key == QtCore.Qt.Key.Key_End:
                last_row = self.result_list.count() - 1
                if last_row >= 0:
                    self.result_list.setCurrentRow(last_row)
                return True

            if key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                self.accept_selection()
                return True

            if key == QtCore.Qt.Key.Key_Escape:
                self.reject()
                return True

        return super().eventFilter(watched, event)

    def keyPressEvent(self, event):
        """Handle dialog-level Escape and Enter outside the search field."""
        key = event.key()

        if key == QtCore.Qt.Key.Key_Escape:
            self.reject()
            return

        if key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            self.accept_selection()
            return

        super().keyPressEvent(event)