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
"""

from PyQt6 import QtWidgets, QtCore
import os
import sys
import logging
import traceback

from .GUI.ui_attribute import Ui_DialogAddAttribute
from .helpers import Message

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

class DialogAddAttribute(QtWidgets.QDialog):
    """
    Dialog to get a new code or code category from user.
    Also used for Case and File adding attributes.
    Requires a name for Dialog title (and label in setupUI)
    Requires a list of dictionary 'name' items.
    Dialog returns ok if the item is not a duplicate of a name in the list.
    """

    def __init__(self, app, parent=None):
        super(DialogAddAttribute, self).__init__(parent)

        self.app = app
        self.new_name = ""
        self.value_type = "character"
        self.existing_names = ['Ref_Type', 'Ref_Author', 'Ref_Title', 'Ref_Year', 'Ref_Journal']
        cur = self.app.conn.cursor()
        sql = "select name from attribute_type"
        cur.execute(sql)
        res = cur.fetchall()
        for r in res:
            self.existing_names.append(r[0])

        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_DialogAddAttribute()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = 'font: ' + str(app.settings['fontsize']) + 'pt '
        font += '"' + app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.ui.radioButton_character.setChecked(True)
        self.ui.lineEdit_name.setFocus()

    def accept(self):
        """ On pressing accept button, check there is no duplicate name.
        If no duplicate then accept and return True. """

        self.value_type = "character"
        new_name = str(self.ui.lineEdit_name.text())
        duplicate = False
        if new_name in self.existing_names:
            duplicate = True
            msg = _("This attribute name already exists in cases, files or journals.")
            msg += "\n" + _("Or is reserved for bibliography attributes:")
            msg += "\n" + "Ref_Type, Ref_Author, Ref_Title, Ref_Year, Ref_Journal"
            Message(self.app, _("Duplicate"), msg, "warning").exec()
            self.new_name = ""
            self.done(0)
        if duplicate is False:
            self.new_name = new_name
        if self.ui.radioButton_numeric.isChecked():
            self.value_type = "numeric"
        self.done(1)
