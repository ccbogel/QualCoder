# -*- coding: utf-8 -*-

"""
Copyright (c) 2020 Colin Curtain

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

import logging
import os
import sys
import traceback

from PyQt5 import QtGui, QtWidgets, QtCore

from GUI.ui_dialog_colour_selector import Ui_Dialog_colour_selector


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

colors = ["#F8E0E0","#F6CECE","#F5A9A9","#F78181","#FA5858","#F8E6E0","#F6D8CE","#F5BCA9","#F79F81","#FA8258",
    "#F8ECE0","#F6E3CE","#F5D0A9","#F7BE81","#FAAC58","#F5ECCE","#F3E2A9","#F5DA81","#F7D358","#FACC2E",
    "#F5F6CE","#F2F5A9","#F2F5A9","#F4FA58","#F7FE2E","#D0F5A9","#BEF781","#ACFA58","#9AFE2E","#80FF00",
    "#E0F8E0","#CEF6CE","#A9F5A9","#81F781","#58FA58","#CEF6E3","#A9F5D0","#81F7BE","#58FAAC","#2EFE9A",
    "#CEF6F5","#A9F5F2","#81F7F3","#58FAF4","#2EFEF7","#CEE3F6","#A9D0F5","#81BEF7","#3498DB","#5882FA",
    "#ECE0F8","#E3CEF6","#D0A9F5","#BE81F7","#AC58FA","#F8E0F7","#F6CEF5","#F5A9F2","#F781F3","#FA58F4",
    "#F8E0E6","#F6CED8","#F5A9BC","#F7819F","#FA5882","#F0F0F0","#EAEAEA","#E6E6E6","#D8D8D8","#BDBDBD",
    "#0D47A1","#311B92","#4A148C","#880E4F","#B71C1C","#BF360C","#E65100","#FF6F00","#33691E","#1B5E20"]

COLS = 10
ROWS = 8


class DialogColorSelect(QtWidgets.QDialog):
    """ Dialog to select colour for code. """

    selected_color = None

    def __init__(self, prev_color, parent=None):

        super(DialogColorSelect, self).__init__(parent)
        sys.excepthook = exception_handler
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_colour_selector()
        self.ui.setupUi(self)
        self.setupUi()
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        self.selected_color = prev_color
        # preset with the current colour
        palette = self.ui.label_colour_old.palette()
        c = QtGui.QColor(self.selected_color)
        palette.setColor(QtGui.QPalette.Window, c)
        self.ui.label_colour_old.setPalette(palette)
        self.ui.label_colour_old.setAutoFillBackground(True)

    def color_selected(self):
        """ Get colour selection from table widget. """

        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        self.selected_color = colors[x * COLS + y]
        palette = self.ui.label_colour_new.palette()
        c = QtGui.QColor(self.selected_color)
        palette.setColor(QtGui.QPalette.Window, c)
        self.ui.label_colour_new.setPalette(palette)
        self.ui.label_colour_new.setAutoFillBackground(True)

    def get_color(self):
        """ Get the selected color from selected table widget cell. """

        return self.selected_color

    def accept(self):
        """ Overrride accept button. """

        super(DialogColorSelect, self).accept()

    def setupUi(self):
        """ Eight rows of ten columns of colours. """

        self.ui.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.ui.tableWidget.setColumnCount(COLS)
        self.ui.tableWidget.setRowCount(ROWS)
        for row in range(0, ROWS):
            self.ui.tableWidget.setRowHeight(row, 31)
            for col in range(0, COLS):
                self.ui.tableWidget.setColumnWidth(col, 52)
                item = QtWidgets.QTableWidgetItem()
                codeColor = colors[row * COLS + col]
                item.setBackground(QtGui.QBrush(QtGui.QColor(codeColor)))
                item.setFlags(item.flags() ^ QtCore.Qt.ItemIsEditable)
                self.ui.tableWidget.setItem(row, col, item)
        self.ui.tableWidget.cellClicked.connect(self.color_selected)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    ui = DialogColorSelect("#101010")
    ui.show()
    sys.exit(app.exec_())
