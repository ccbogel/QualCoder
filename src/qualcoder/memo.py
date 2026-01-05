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

from .GUI.ui_dialog_memo import Ui_Dialog_memo
from .helpers import MarkdownHighlighter


path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogMemo(QtWidgets.QDialog):

    """ Dialog to view and edit memo text.
    """

    app = None
    title = ""
    memo = ""

    def __init__(self, app, title="", memo="", clear_button="show", tooltip=""):
        super(DialogMemo, self).__init__(parent=None)  # Overrride accept method

        self.app = app
        self.memo = memo
        self.ui = Ui_Dialog_memo()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.setWindowTitle(title)
        self.ui.textEdit.setPlainText(self.memo)
        self.ui.textEdit.setFocus()
        if tooltip != "":
            self.ui.textEdit.setToolTip(tooltip)
        if clear_button == "hide":
            self.ui.pushButton_clear.hide()
        self.ui.pushButton_clear.pressed.connect(self.clear_contents)
        highlighter = MarkdownHighlighter(self.ui.textEdit, self.app)

    def clear_contents(self):
        """ Clear all text """
        self.ui.textEdit.setPlainText("")

    def accept(self):
        """ Accepted button overridden method. """

        self.memo = self.ui.textEdit.toPlainText()
        super(DialogMemo, self).accept()
