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
https://qualcoder-org.github.io
https://qualcoder.org/
"""

import copy
import logging
import os

from PyQt6 import QtCore, QtWidgets

from .GUI.ui_dialog_select_items import Ui_Dialog_selectitems
from .helpers import Message

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogSelectItems(QtWidgets.QDialog):
    """
    Requires a list of dictionaries. This list must have a dictionary item called 'name'
    Which is displayed to the user.
    Optionally have a dictionary item called 'group' (Used in View_graph)
    The group can be selected using the comboBox to limit items shown.
    The setupui method requires a title string for the dialog title and a selection mode:
    "single" or any other text which equates to many.

    User selects one or more names from the list depending on selection mode.
    getSelected method returns the selected dictionary object(s).

    Called by by ViewGraph, DialogCodeText, DialogCodeAV, DialogCodeImage
    """

    def __init__(self, app_, data, title, selection_mode, preselected=None, with_checkboxes=False):
        """ present list of names to user for selection.
        Can use comboBox to select groups of items to reduce the length of the list.
        The group key is used with View_graph
        Args:
            app : App class
            data: list of dictionaries containing the key 'name'
            title: Dialog title, String
            selection_mode: 'single' or anything else for 'multiple', String
            preselected: optional list of dictionaries (or plain ids) already selected
                by the caller; the matching rows are shown selected so the user can
                check and adjust the current selection. Matched by 'id' when both
                sides have one, else by 'name'.
            with_checkboxes: if True (and not single selection) each row gets a tick
                box, so items can be selected by ticking the box OR with Ctrl/Shift +
                click. get_selected returns the union of ticked and highlighted rows.
        """

        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_selectitems()
        self.ui.setupUi(self)
        font = f'font: {app_.settings["fontsize"]}pt "{app_.settings["font"]}";'
        self.setStyleSheet(font)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.setWindowTitle(title)
        self.groups = []
        self.data_refined = None
        self.model = None
        self.data = data
        self.selection_mode = selection_mode
        self.preselected = preselected if preselected else []
        # Casillas solo en modo multiple. Checkboxes only make sense for multi-select.
        self.with_checkboxes = bool(with_checkboxes) and selection_mode != "single"
        # Estado de marcado persistente por identidad (sobrevive a reconstruir el modelo,
        # p. ej. al cambiar de grupo). Persistent check state keyed by identity, so it
        # survives model rebuilds (e.g. changing the group filter).
        self._checked_keys = set()
        for p in self.preselected:
            self._checked_keys.add(self._item_key(p))
        # Check data exists
        if len(self.data) == 0:
            Message(app_, _('Dictionary is empty'), _("No data to select from"), "warning")
        # Check for 'name' key
        no_name_key = False

        # Get groups key from data, for combobox to reduce selection list
        self.groups = []
        for d in self.data:
            if not d['name']:
                no_name_key = True
            try:
                self.groups.append(d['group'])
            except KeyError:
                pass
        if no_name_key:
            text = _("This data does not contain names to select from")
            Message(app_, _('Dictionary has no "name" key'), text, "warning")
        self.ui.comboBox.hide()
        if self.groups:
            self.groups = list(set(self.groups))
            self.groups.insert(0, _("All"))
            self.ui.comboBox.setEnabled(True)
            self.ui.comboBox.show()
            self.ui.comboBox.addItems(self.groups)

        if self.selection_mode == "single":
            self.ui.listView.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        else:
            self.ui.listView.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.ui.listView.doubleClicked.connect(self.accept)
        self.model = None
        self.fill_list()
        self.ui.comboBox.currentIndexChanged.connect(self.fill_list)

    @staticmethod
    def _item_key(d):
        """ Stable identity for a data row (or a plain id): ('id', value) when an
        id is present, else ('name', value). Used for preselection matching and to
        persist tick state across model rebuilds. """

        if isinstance(d, dict):
            if d.get('id') is not None:
                return 'id', d['id']
            return 'name', d.get('name')
        return 'id', d

    def fill_list(self):
        """ Show data items considering comboBox group selection. """

        self.data_refined = copy.copy(self.data)
        grouper = self.ui.comboBox.currentText()
        if not self.groups or grouper == "All":
            self.model = ListModel(self.data_refined, checkable=self.with_checkboxes,
                                   checked_keys=self._checked_keys, key_func=self._item_key)
            self.ui.listView.setModel(self.model)
            self._apply_preselection()
            return

        self.data_refined = [d for d in self.data if d['group'] == grouper]
        self.model = ListModel(self.data_refined, checkable=self.with_checkboxes,
                               checked_keys=self._checked_keys, key_func=self._item_key)
        self.ui.listView.setModel(self.model)
        self._apply_preselection()

    def _apply_preselection(self):
        """ Show the caller's current selection so it can be checked and adjusted.

        With checkboxes enabled the preselected rows are already ticked (seeded into
        checked_keys), and they are deliberately NOT highlighted: a highlight would
        also count as selected (see get_selected), so unticking a box would not
        actually deselect the file. Only the tick represents selection in that mode.

        Without checkboxes the rows are highlighted, matched by 'id' when both sides
        have one, otherwise by 'name'. """

        if not self.preselected:
            return
        if self.with_checkboxes:
            # Ticks already reflect the preselection; move the current index to the
            # first ticked row for keyboard navigation, without highlighting it.
            for row, d in enumerate(self.data_refined):
                if self._item_key(d) in self._checked_keys:
                    selection_model = self.ui.listView.selectionModel()
                    if selection_model is not None:
                        selection_model.setCurrentIndex(
                            self.model.index(row, 0),
                            QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)
                    break
            return
        selection_model = self.ui.listView.selectionModel()
        if selection_model is None:
            return
        keys = set()
        for p in self.preselected:
            if isinstance(p, dict):
                if 'id' in p:
                    keys.add(('id', p['id']))
                if 'name' in p:
                    keys.add(('name', p['name']))
            else:
                keys.add(('id', p))
        first_index = None
        for row, d in enumerate(self.data_refined):
            matched = ('id' in d and ('id', d['id']) in keys) or ('name', d.get('name')) in keys
            if not matched:
                continue
            index = self.model.index(row, 0)
            if first_index is None:
                first_index = index
            if self.selection_mode == "single":
                self.ui.listView.setCurrentIndex(index)
                return
            selection_model.select(index, QtCore.QItemSelectionModel.SelectionFlag.Select)
        if first_index is not None:
            # current index without clearing the multi-selection
            selection_model.setCurrentIndex(first_index, QtCore.QItemSelectionModel.SelectionFlag.NoUpdate)

    def get_selected(self):
        """ Get a selected dictionary  or a list of dictionaries depending on the
        selection mode.

        With checkboxes enabled, the multiple-selection result is the UNION of ticked
        rows and highlighted (Ctrl/Shift + click) rows, so either mechanism works.

        return: list if Dictionaries of {name, data} """

        if self.selection_mode == "single":
            current = self.ui.listView.currentIndex().row()
            if current == -1:
                return []
            return self.data_refined[int(current)]
        else:
            highlighted_rows = {item.row() for item in self.ui.listView.selectedIndexes()}
            selected = []
            for row, d in enumerate(self.data_refined):
                is_highlighted = row in highlighted_rows
                is_ticked = self.with_checkboxes and self._item_key(d) in self._checked_keys
                if is_highlighted or is_ticked:
                    selected.append(d)
            return selected


class ListModel(QtCore.QAbstractListModel):
    def __init__(self, data_list, parent=None, checkable=False, checked_keys=None, key_func=None):
        super(ListModel, self).__init__(parent)
        self.list = data_list
        self.checkable = checkable
        # Conjunto compartido de identidades marcadas (lo mantiene el dialogo).
        # Shared set of ticked identities (owned by the dialog).
        self.checked_keys = checked_keys if checked_keys is not None else set()
        self.key_func = key_func if key_func is not None else (lambda d: ('name', d.get('name')))

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self.list)

    def flags(self, index):
        base_flags = super(ListModel, self).flags(index)
        if self.checkable and index.isValid():
            return base_flags | QtCore.Qt.ItemFlag.ItemIsUserCheckable
        return base_flags

    def data(self, index, role):
        if not index.isValid():
            return QtCore.QVariant()
        if role == QtCore.Qt.ItemDataRole.DisplayRole:  # show just the name
            row_item = self.list[index.row()]
            return QtCore.QVariant(row_item['name'])
        elif role == QtCore.Qt.ItemDataRole.CheckStateRole and self.checkable:
            row_item = self.list[index.row()]
            ticked = self.key_func(row_item) in self.checked_keys
            return QtCore.Qt.CheckState.Checked if ticked else QtCore.Qt.CheckState.Unchecked
        elif role == QtCore.Qt.ItemDataRole.ToolTipRole:  # show full text on hover
            row_item = self.list[index.row()]
            try:
                row_item['memo']
                return row_item.get('tooltip', row_item['memo'])
            except KeyError:
                return row_item.get('tooltip', row_item['name'])
        elif role == QtCore.Qt.ItemDataRole.UserRole:  # return the whole python object
            row_item = self.list[index.row()]
            return row_item
        return QtCore.QVariant()

    def setData(self, index, value, role=QtCore.Qt.ItemDataRole.EditRole):
        """ Handle the user ticking / unticking a checkbox. The new state is stored
        in the shared checked_keys set so it survives model rebuilds and is read back
        by DialogSelectItems.get_selected. """

        if role == QtCore.Qt.ItemDataRole.CheckStateRole and self.checkable and index.isValid():
            # El valor puede llegar como Qt.CheckState o como int, segun la version de Qt.
            # value may arrive as a Qt.CheckState or as an int, depending on the Qt build.
            if isinstance(value, QtCore.Qt.CheckState):
                ticked = value == QtCore.Qt.CheckState.Checked
            else:
                ticked = int(value) == QtCore.Qt.CheckState.Checked.value
            key = self.key_func(self.list[index.row()])
            if ticked:
                self.checked_keys.add(key)
            else:
                self.checked_keys.discard(key)
            self.dataChanged.emit(index, index, [role])
            return True
        return super(ListModel, self).setData(index, value, role)
