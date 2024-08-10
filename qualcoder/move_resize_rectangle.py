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
"""

from PyQt6 import QtCore, QtWidgets, QtGui
import os
import sys
import logging
import traceback

from .GUI.ui_move_resize_rectangle import Ui_Dialog_move_resize_rect

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogMoveResizeRectangle(QtWidgets.QDialog):
    """
    Dialog to obtain integers for move or resize a coded image rectangle.
    """

    app = None
    move_x = 0
    move_y = 0
    resize_x = 0
    resize_y = 0

    def __init__(self, app, parent=None):
        super(DialogMoveResizeRectangle, self).__init__(parent)

        self.app = app
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_move_resize_rect()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = 'font: ' + str(app.settings['fontsize']) + 'pt '
        font += '"' + app.settings['font'] + '";'
        self.setStyleSheet(font)
        integer_validator = QtGui.QIntValidator()
        self.ui.lineEdit_move_horizontal.setValidator(integer_validator)
        self.ui.lineEdit_move_vetical.setValidator(integer_validator)
        self.ui.lineEdit_resize_vertical.setValidator(integer_validator)
        self.ui.lineEdit_resize_horizontal.setValidator(integer_validator)

    def accept(self):
        """ On pressing accept button, check there is no duplicate name.
        If no duplicate then accept and return True. """

        try:
            self.resize_x = int(self.ui.lineEdit_resize_horizontal.text())
        except ValueError:
            self.resize_x = 0
        try:
            self.resize_y = int(self.ui.lineEdit_resize_vertical.text())
        except ValueError:
            self.resize_y = 0
        try:
            self.move_x = int(self.ui.lineEdit_move_horizontal.text())
        except ValueError:
            self.move_x = 0
        try:
            self.move_y = int(self.ui.lineEdit_move_vetical.text())
        except ValueError:
            self.move_y = 0
        self.done(1)
