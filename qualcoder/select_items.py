# -*- coding: utf-8 -*-

"""
Copyright (c) 2022 Colin Curtain

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
https://qualcoder.wordpress.com/
"""

from PyQt6 import QtCore, QtWidgets
import os
import sys
import logging
import traceback

from .GUI.ui_dialog_select_items import Ui_Dialog_selectitems
from .helpers import Message

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception: ") + text)
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), text)


class DialogSelectItems(QtWidgets.QDialog):
    """
    Requires a list of dictionaries. This list must have a dictionary item called 'name'
    which is displayed to the user.
    The setupui method requires a title string for the dialog title and a selection mode:
    "single" or any other text which equates to many.

    User selects one or more names from the list depending on selection mode.
    getSelected method returns the selected dictionary object(s).
    """

    dict_list = None
    selectedname = None
    title = None

    def __init__(self, app_, data, title, selection_mode):
        """ present list of names to user for selection.

        params:
            data: list of dictionaries containing the key 'name'
            title: Dialog title, String
            selectionmode: 'single' or anything else for 'multiple', String
        """

        sys.excepthook = exception_handler
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_selectitems()
        self.ui.setupUi(self)
        font = 'font: ' + str(app_.settings['fontsize']) + 'pt '
        font += '"' + app_.settings['font'] + '";'
        self.setStyleSheet(font)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.setWindowTitle(title)
        self.selection_mode = selection_mode
        # Check data exists
        if len(data) == 0:
            Message(app_, _('Dictionary is empty'), _("No data to select from"), "warning")
        # Check for 'name' key
        no_name_key = False

        for d in data:
            if not d['name']:
                no_name_key = True
        if no_name_key:
            text = _("This data does not contain names to select from")
            Message(app_, _('Dictionary has no "name" key'), text, "warning")

        self.dict_list = data
        self.model = ListModel(self.dict_list)
        self.ui.listView.setModel(self.model)
        if self.selection_mode == "single":
            self.ui.listView.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        else:
            self.ui.listView.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.ui.listView.doubleClicked.connect(self.accept)

    def get_selected(self):
        """ Get a selected dictionary  or a list of dictionaries depending on the
        selection mode.

        return: list if Dictionaries of {name, data} """

        if self.selection_mode == "single":
            current = self.ui.listView.currentIndex().row()
            if current == -1:
                return []
            return self.dict_list[int(current)]
        else:
            selected = []
            for item in self.ui.listView.selectedIndexes():
                selected.append(self.dict_list[item.row()])
            return selected


class ListModel(QtCore.QAbstractListModel):
    def __init__(self, dict_list, parent=None):
        super(ListModel, self).__init__(parent)
        sys.excepthook = exception_handler
        self.list = dict_list

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self.list)

    # TODO Signature of method ListModel.data() does not match signature of the base method in class QAbstractItemModel
    def data(self, index, role):
        if role == QtCore.Qt.ItemDataRole.DisplayRole:  # show just the name
            rowitem = self.list[index.row()]
            return QtCore.QVariant(rowitem['name'])
        elif role == QtCore.Qt.ItemDataRole.UserRole:  # return the whole python object
            rowitem = self.list[index.row()]
            return rowitem
        return QtCore.QVariant()
