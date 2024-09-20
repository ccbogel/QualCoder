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
