# -*- coding: utf-8 -*-

"""
Copyright (c) 2024 Colin Curtain

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
