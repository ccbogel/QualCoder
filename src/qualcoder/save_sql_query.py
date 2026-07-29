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

Authors: Colin Curtain C, Kai Dröge, Justin Missaghieh--Poncet, Lorenzo Salomón
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
https://qualcoder-org.github.io
https://qualcoder.org/
"""

import logging
from PyQt6 import QtWidgets, QtCore

from .GUI.ui_save_query import Ui_DialogSaveQuery

logger = logging.getLogger(__name__)


class DialogSaveSql(QtWidgets.QDialog):
    """
    Obtains query name and group for saving into stored_sql.
    Called from:
         report_sql.save_query
    """

    def __init__(self, app_, parent=None):

        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_DialogSaveQuery()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {app_.settings["fontsize"]}pt "{app_.settings["font"]}";'
        self.setStyleSheet(font)
        self.name = ""
        self.grouper = ""
        self.description = ""

    def accept(self):
        """ Accept button overridden method """

        self.name = self.ui.lineEdit_name.text()
        self.grouper = self.ui.lineEdit_group.text()
        self.description = self.ui.textEdit.toPlainText()
        super().accept()
