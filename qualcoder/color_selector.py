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

import logging
import os
import sys
import traceback

from PyQt6 import QtGui, QtWidgets, QtCore

from .GUI.ui_dialog_colour_selector import Ui_Dialog_colour_selector


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


class TextColor:
    """ Returns light or dark depending on the code color. """

    white_text = [
        "#EB7333", "#E65100", "#C54949", "#B71C1C", "#CB5E3C", "#BF360C",
        "#FA58F4", "B76E95", "#9F3E72", "#880E4F", "#7D26CD",  "#1B5E20",
        "#487E4B", "#1B5E20", "#5E9179", "#AC58FA", "#5E9179", "#9090E3",
        "#6B6BDA", "#4646D1", "#3498DB", "#6D91C6", "#3D6CB3", "#0D47A1",
        "#9090E3"]
    recommendation = "#000000"

    def __init__(self, color):
        if color in self.white_text:
            self.recommendation = "#eeeeee"
        else:
            self.recommendation = "#000000"


colors = [
    "#F5F6CE", "#F2F5A9", "#F4FA58", "#F7FE2E", "#DDE600", "#F8ECE0", "#F6E3CE", "#F5D0A9", "#F7BE81", "#FAAC58",
    "#F5ECCE", "#F3E2A9", "#F5DA81", "#F7D358", "#FACC2E", "#F8E0E0", "#F6CECE", "#F5A9A9", "#F78181", "#FA5858",
    "#F8E6E0", "#F6D8CE", "#F5BCA9", "#F79F81", "#FA8258", "#FADCCC", "#F5B999", "#F09666", "#EB7333", "#E65100",
    "#FFE2CC", "#FFC599", "#FFA866", "#FF8B33", "#FF6F00", "#F0D1D1", "#E2A4A4", "#D37676", "#C54949", "#B71C1C",
    "#F2D6CE", "#E5AE9D", "#D8866D", "#CB5E3C", "#BF360C", "#E7CEDB", "#CF9EB8", "#B76E95", "#9F3E72", "#880E4F",
    "#F8E0E6", "#F6CED8", "#F5A9BC", "#F7819F", "#FA5882", "#F8E0F7", "#F6CEF5", "#F5A9F2", "#F781F3", "#FA58F4",
    "#E4D3F5", "#CAA8EB", "#B07CE1", "#9651D7", "#7D26CD", "#ECE0F8", "#E3CEF6", "#D0A9F5", "#BE81F7", "#AC58FA",
    "#D1DED2", "#A3BEA5", "#769E78", "#487E4B", "#1B5E20", "#DEE9E4", "#BED3C9", "#9EBDAE", "#7EA793", "#5E9179",
    "#CEF6E3", "#A9F5D0", "#81F7BE", "#58FAAC", "#00FF7F", "#E0F8E0", "#CEF6CE", "#A9F5A9", "#81F781", "#58FA58",
    "#D0F5A9", "#BEF781", "#ACFA58", "#9AFE2E", "#80FF00", "#CEF6F5", "#A9F5F2", "#81F7F3", "#58FAF4", "#00F0F0",
    "#DADAF5", "#B5B5EC", "#9090E3", "#6B6BDA", "#4646D1", "#CEE3F6", "#A9D0F5", "#81BEF7", "#3498DB", "#5882FA",
    "#CEDAEC", "#9EB5D9", "#6D91C6", "#3D6CB3", "#0D47A1", "#E8E8E8", "#D8D8D8", "#C8C8C8", "#B8B8B8", "#A8A8A8"
    ]

COLS = 10
ROWS = 12


class DialogColorSelect(QtWidgets.QDialog):
    """ Dialog to select colour for code.
    Useful site for colours: https://www.tutorialrepublic.com/html-reference/html-color-picker.php
    """

    selected_color = None
    used_colors = []

    def __init__(self, app, code_, parent=None):

        super(DialogColorSelect, self).__init__(parent)
        sys.excepthook = exception_handler
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_colour_selector()
        self.ui.setupUi(self)
        cur = app.conn.cursor()
        cur.execute("select color, name from code_name order by name")
        self.used_colors = cur.fetchall()
        self.setup_ui()
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = 'font: ' + str(app.settings['fontsize']) + 'pt '
        font += '"' + app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.selected_color = code_['color']
        # preset with the current colour
        fg_color = TextColor(code_['color']).recommendation
        style = "QLabel {background-color :" + code_['color'] + "; color : " + fg_color + ";}"
        self.ui.label_colour_old.setStyleSheet(style)
        self.ui.label_colour_old.setAutoFillBackground(True)
        self.ui.label_colour_old.setToolTip(_("Current colour"))
        self.ui.label_colour_old.setText(code_['name'])
        self.ui.label_colour_new.setToolTip(_("New colour"))
        self.ui.label_colour_new.setText(code_['name'])

    def color_selected(self):
        """ Get colour selection from table widget. """

        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        self.selected_color = colors[x * COLS + y]
        fg_color = TextColor(self.selected_color).recommendation
        style = "QLabel {background-color :" + self.selected_color + "; color : " + fg_color + ";}"
        self.ui.label_colour_new.setStyleSheet(style)
        self.ui.label_colour_new.setToolTip(_("New colour: ") + self.selected_color)
        self.ui.label_colour_new.setAutoFillBackground(True)

    def get_color(self):
        """ Get the selected color from selected table widget cell. """

        return self.selected_color

    def accept(self):
        """ Overrride accept button. """

        super(DialogColorSelect, self).accept()

    def setup_ui(self):
        """ Eight rows of ten columns of colours. """

        self.ui.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.ui.tableWidget.setColumnCount(COLS)
        self.ui.tableWidget.setRowCount(ROWS)
        self.ui.tableWidget.verticalHeader().setVisible(False)
        self.ui.tableWidget.horizontalHeader().setVisible(False)
        for row in range(0, ROWS):
            self.ui.tableWidget.setRowHeight(row, 31)
            for col in range(0, COLS):
                self.ui.tableWidget.setColumnWidth(col, 52)
                code_color = colors[row * COLS + col]
                text = ""
                ttip = ""
                for c in self.used_colors:
                    if code_color == c[0]:
                        text = "*"
                        ttip += c[1] + "\n"
                item = QtWidgets.QTableWidgetItem(text)
                item.setToolTip(ttip)
                item.setBackground(QtGui.QBrush(QtGui.QColor(code_color)))
                item.setForeground(QtGui.QBrush(QtGui.QColor(TextColor(code_color).recommendation)))
                item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
                self.ui.tableWidget.setItem(row, col, item)
        self.ui.tableWidget.cellClicked.connect(self.color_selected)
