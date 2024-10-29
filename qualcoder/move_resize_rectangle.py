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

from PyQt6 import QtCore, QtWidgets, QtGui
import os
import logging

from .GUI.ui_move_resize_rectangle import Ui_Dialog_move_resize_rect

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogMoveResizeRectangle(QtWidgets.QDialog):
    """ Dialog to obtain integers for move or resize a coded image rectangle.
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
        font = f'font: {app.settings["fontsize"]}pt "{app.settings["font"]}";'
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
