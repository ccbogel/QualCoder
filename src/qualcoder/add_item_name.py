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
https://qualcoder-org.github.io/
"""

import os
import logging

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtGui import QRegularExpressionValidator

from .GUI.ui_dialog_add_item import Ui_Dialog_add_item

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogAddItemName(QtWidgets.QDialog):
    """ Dialog to get a new code or code category from user.
    Also used for Case and File adding attributes.
    Also used to rename codes/categories - for this submit an items list excluding the code/cat to change.
    Requires a name for Dialog title (and label in setupUI)
    Requires a list of dictionary 'name' items.
    Dialog returns ok if the item is not a duplicate of a name in the list.
    Returns one item through get_new_name method.
    """

    def __init__(self, app, items, title, text, reg_expression=None, parent=None):
        """ Params:
            app : App class
            items: list of dictionaries containing 'name' key
            title: String
            text: String
            validation: QRegularExpression object
            """

        super(DialogAddItemName, self).__init__(parent)
        self.existing_items = []
        self.new_item = None
        for i in items:
            self.existing_items.append(i['name'])
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_add_item()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet(f"* {{font-size:{app.settings['fontsize']}pt}} ")
        self.setWindowTitle(title)
        self.ui.label.setText(text)
        if reg_expression:
            valid_regex = QRegularExpressionValidator(reg_expression)
            self.ui.lineEdit.setValidator(valid_regex)
        self.ui.lineEdit.setFocus()

    def accept(self):
        """ On pressing accept button, check there is no duplicate.
        If no duplicate then accept end close the dialog """

        this_item = str(self.ui.lineEdit.text())
        if this_item in self.existing_items:
            QtWidgets.QMessageBox.warning(None, "    " + _("Duplicated") + " " * 20, _("This already exists"))
            return
        self.new_item = this_item
        self.close()
        super(DialogAddItemName, self).accept()

    def get_new_name(self):
        """ Get the new name. """

        return self.new_item
