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

    data = None
    groups = []
    data_refined = None
    model = None
    title = None

    def __init__(self, app_, data, title, selection_mode):
        """ present list of names to user for selection.
        Can use comboBox to select groups of items to reduce the length of the list.
        The group key is used with View_graph

        params:
            data: list of dictionaries containing the key 'name'
            title: Dialog title, String
            selectionmode: 'single' or anything else for 'multiple', String
        """

        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_selectitems()
        self.ui.setupUi(self)
        font = f'font: {app_.settings["fontsize"]}pt "{app_.settings["font"]}";'
        self.setStyleSheet(font)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.setWindowTitle(title)
        self.data = data
        self.selection_mode = selection_mode
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

    def fill_list(self):
        """ Show data items considering comboBox group selection. """

        self.data_refined = copy.copy(self.data)
        grouper = self.ui.comboBox.currentText()
        if not self.groups or grouper == "All":
            self.model = ListModel(self.data_refined)
            self.ui.listView.setModel(self.model)
            return

        self.data_refined = [d for d in self.data if d['group'] == grouper]
        self.model = ListModel(self.data_refined)
        self.ui.listView.setModel(self.model)

    def get_selected(self):
        """ Get a selected dictionary  or a list of dictionaries depending on the
        selection mode.

        return: list if Dictionaries of {name, data} """

        if self.selection_mode == "single":
            current = self.ui.listView.currentIndex().row()
            if current == -1:
                return []
            return self.data_refined[int(current)]
        else:
            selected = []
            for item in self.ui.listView.selectedIndexes():
                selected.append(self.data_refined[item.row()])
            return selected


class ListModel(QtCore.QAbstractListModel):
    def __init__(self, data_list, parent=None):
        super(ListModel, self).__init__(parent)
        self.list = data_list

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self.list)

    def data(self, index, role):
        if role == QtCore.Qt.ItemDataRole.DisplayRole:  # show just the name
            row_item = self.list[index.row()]
            return QtCore.QVariant(row_item['name'])
        elif role == QtCore.Qt.ItemDataRole.UserRole:  # return the whole python object
            row_item = self.list[index.row()]
            return row_item
        return QtCore.QVariant()
