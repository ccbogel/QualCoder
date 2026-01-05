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

from PyQt6 import QtWidgets, QtCore
import os
import logging

from .GUI.ui_dialog_confirm_delete import Ui_Dialog_confirmDelete

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogConfirmDelete(QtWidgets.QDialog):
    """ Generic conform delete dialog, showing some text.
    Called by: DialogManageFiles, attributes, cases, casefilemanager,
    code_text, journals

    param:
        text: a string for display """

    def __init__(self, app, text, title=""):

        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_confirmDelete()
        self.ui.setupUi(self)
        self.setMinimumSize(260, 80)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {app.settings["fontsize"]}pt '
        font += f'"{app.settings["font"]}";'
        self.setStyleSheet(font)
        self.ui.label.setText(text)
        if title != "":
            self.setWindowTitle(title)
        self.adjustSize()
