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

import logging
import os

from PyQt6 import QtGui, QtWidgets, QtCore

from .GUI.ui_dialog_colour_selector import Ui_Dialog_colour_selector


path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class TextColor:
    """ Returns light or dark depending on the code color. """

    white_text = [
        "#EB7333", "#E65100", "#C54949", "#B71C1C", "#CB5E3C", "#BF360C",
        "#FA58F4", "B76E95", "#9F3E72", "#880E4F", "#7D26CD",  "#1B5E20",
        "#487E4B", "#1B5E20", "#5E9179", "#AC58FA", "#5E9179", "#9090E3",
        "#6B6BDA", "#4646D1", "#3498DB", "#6D91C6", "#3D6CB3", "#0D47A1",
        "#9090E3", "#5882FA", "#9651D7"]
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

# www.color-blindness.com/coblis-color-blindness-simulator/
# https://imagecolorpicker.com/en
colors_red_weak = [
    "#FBF4D0", "#FAF2B3", "#FBF598", "#FCF892", "#efe000", "#F6EDE0", "#F2E4CF", "#EAD4AB", "#E5C584", "#E0B75B",
    "#F6ECCE", "#F3E2A9", "#F2DB81", "#F1D559", "#F1D02F", "#EFE3E2", "#E6D3D1", "#D5B5B0", "#C7978C", "#BD7C66",
    "#F3E8E1", "#EBDBD0", "#DFC4AD", "#D5AD87", "#CD9860", "#F0DFCE", "#DFC19D", "#CFA46B", "#C08939", "#B2710F",
    "#F6E5CD", "#EBCC9C", "#E0B56B", "#D69F38", "#CC8B0F", "#E4D5D3", "#C8AEA9", "#AD877E", "#966454", "#854626",
    "#E8D9D0", "#D0B6A1", "#B89373", "#A37343", "#905615", "#DCD2DD", "#B7A6BD", "#937C9E", "#705481", "#563264",
    "#EEE3E8", "#E5D4DB", "#D3B6C3", "#C398AC", "#B77D96", "#ECE4F9", "#E1D5F9", "#CAB8FA", "#B69CFB", "#A582FB",
    "#DAD6F7", "#B2AFF0", "#8489EC", "#3764E5", "#2D45BF", "#E6E2F9", "#D6D2F9", "#B4B2FB", "#8F90FC", "#5F71FD",
    "#DBDBD0", "#B5B9A2", "#8F9775", "#697648", "#44561E", "#E6E7E3", "#CCCFC7", "#B1B8AB", "#96A190", "#7C8A75",
    "#E6EFDF", "#D5EACA", "#C6E8B7", "#B7E7A4", "#9AE977", "#F1F3DD", "#E8EFCA", "#D8E9A4", "#C9E67B", "#BBE652",
    "#EBEDA6", "#E6EC7D", "#E0EC54", "#DAED36", "#D0EC00", "#E4F0F1", "#D2EBEC", "#C1E9EB", "#B1EAEA", "#89DFE5",
    "#D9DAF5", "#AFB7ED", "#8393E6", "#4C71E0", "#1951C0", "#D8E0F4", "#BACCF2", "#9AB9F3", "#6091D6", "#4F83FB",
    "#D4D8EB", "#A6B3D7", "#798EC4", "#486AB1", "#05489D", "#EBE7E8", "#DAD7D8", "#CAC7C8", "#BAB7B8", "#AAA7A8"
    ]

colors_red_blind = [
    "#FFF3D0", "#FFF0B9", "#FFF1BC", "#FFF4CC", "#F9DD00", "#F5EDE0", "#EFE5CF", "#E4D6AC", "#DAC985", "#D1BD5D",
    "#F7EBCE", "#F3E2A9", "#F0DC82", "#EED659", "#EBD22F", "#EAE4E3", "#DCD7D3", "#C3BCB3", "#ACA492", "#9B906E",
    "#F0E9E1", "#E5DDD1", "#D3C9AF", "#C2B58B", "#B3A464", "#EAE1CF", "#D2C69F", "#BCAD6F", "#A7963D", "#948418",
    "#F1E7CE", "#E0d19E", "#CEBC6D", "#BEAA3B", "#AF9C18", "#DDD7D5", "#B9B3AC", "#979183", "#7B735A", "#695F2C",
    "#E3DBD1", "#C4BAA3", "#A69B76", "#8C7F47", "#766919", "#D6D4DE", "#A9ABC0", "#7E84A4", "#55618A", "#394770",
    "#E9E5E9", "#DBD7DD", "#BFBDC8", "#A5A5B4", "#9192A1", "#E6E6FB", "#D4D9FC", "#B2C1FF", "#91ABFF", "#749AFF",
    "#D4D8F8", "#A4B4F4", "#6B90F3", "#006FED", "#0057B7", "#E2E3FA", "#CFD4FA", "#A3B6FF", "#7399FF", "#337FFF",
    "#E1D9CF", "#BFB6A1", "#9D9373", "#7C7146", "#5B511D", "#EBE5E2", "#D3CDC6", "#BCB5AA", "#A49D8E", "#8D8673",
    "#F4EBDD", "#EFE3C7", "#EDDFB2", "#EDDC9F", "#F2DC73", "#FAF0DC", "#F7EAC8", "#F3E2A1", "#F2DC78", "#F3DA4F",
    "#FBE8A4", "#FCE57B", "#FEE452", "#FFE43A", "#FDE100", "#F1ECEF", "#EAE5E9", "#E6E2E6", "#E4E0E5", "#D7D5DF",
    "#D8DAF5", "#ACB8EE", "#7B95E7", "#3A74E3", "#0057B7", "#DEDEF3", "#C3C9F1", "#A8B6F1", "#798ED2", "#4A84FC",
    "#D7D7EA", "#ABB2D7", "#7F8DC3", "#4F69B0", "#00499B", "#ECE7E7", "#DCD7D7", "#CBC7C7", "#BBB7B7", "#ABA7A8"
    ]

colors_green_weak = [
    "#FBF2DF", "#FAF0CA", "#FBF3AC", "#FCF7A1", "#F3DC61", "#FCEAE4", "#FCE1D2", "#F8CFA9", "#F4BF81", "#F0B157",
    "#FBE9D7", "#FBDEB6", "#FBD695", "#FCD073", "#FDCA51", "#FBDFE0", "#F2CFCE", "#E2B1A7", "#D5937E", "#CB7853",
    "#FCE4E2", "#F8D7CE", "#EDBFA8", "#E3A87F", "#DB9354", "#FDDBCD", "#EDBC98", "#DD9F64", "#CD842D", "#BD6D00",
    "#FFE2D1", "#FAC799", "#F0AF64", "#E5992E", "#D98600", "#F0D1D1", "#D4AAA3", "#B98474", "#A16145", "#8F430A",
    "#F5D5CE", "#DCB29C", "#C58F6B", "#AE6F38", "#995304", "#E7CEDB", "#C1A4B7", "#9C7A93", "#7B536F", "#63324B",
    "#FADFE6", "#F0D0D8", "#DFB3BA", "#D1959C", "#C77A7D", "#F7E0F7", "#EBD2F4", "#D3B7EF", "#BD9CEE", "#AA84ED",
    "#E3D3F5", "#B7AFEA", "#888ADE", "#4368D2", "#2D49AF", "#F0DFF8", "#DED0F6", "#B9B1F3", "#8D92F4", "#3F75F1",
    "#E6D7D3", "#BEB5A7", "#97947A", "#70734E", "#4A5323", "#F1E3E5", "#D5CBCB", "#B9B4B0", "#9D9E95", "#82877B",
    "#EDECE6", "#E0E5D4", "#D1E3C2", "#C2E2B2", "#A2E496", "#F4F1E7", "#EDECD7", "#E0E5B6", "#D1E197", "#C2E17E",
    "#EEEAC0", "#E7E8A8", "#E1E893", "#DAEA82", "#D1E86B", "#EDECF7", "#DAE7F5", "#C7E6F7", "#B6E7F8", "#8CDCF4",
    "#E1D8F5", "#B3B6EC", "#8094E2", "#3474D8", "#1954B0", "#E0DDF7", "#BDCAF6", "#98B8F8", "#5693DC", "#2087F7",
    "#DCD5ED", "#AAB1DA", "#778FC7", "#3C6CB3", "#054B8F", "#F6E3E9", "#E5D4D9", "#D4C4C9", "#C3B4B9", "#B2A5A9"
    ]

colors_green_blind = [
    "#FFF0E9", "#FFEDDD", "#FFEFDC", "#FFF2E3", "#FFD698", "#FFE9E6", "#FFDFD4", "#FACEA9", "#F2C081", "#EAB456",
    "#FFE7DD", "#FFDCBE", "#FFD4A0", "#FFCE83", "#FFC865", "#FDDEE0", "#F0D0CE", "#D7B6A7", "#C19E7C", "#B18A50",
    "#FFE3E2", "#FAD7CE", "#E8C1A8", "#D8AE7E", "#CA9C52", "#FFDACD", "#E9BE98", "#D2A563", "#BC8E2A", "#A67D00",
    "#FFE1D4", "#F7C898", "#E7B363", "#D6A12B", "#C49300", "#F0D1D1", "#CCADA2", "#A98B72", "#8D6E43", "#785A00",
    "#F6D4CE", "#D8B49C", "#BA956A", "#9E7936", "#846300", "#E6CEDB", "#B8A7B6", "#8D8292", "#675F6D", "#4F4649",
    "#FCDFE6", "#EDD1D7", "#D2B8B9", "#BBA09A", "#A98D7A", "#F7E1F7", "#E4D5F4", "#C0BFEE", "#9CABEB", "#7C9CE9",
    "#E2D4F5", "#ACB2E9", "#7192DD", "#1476D0", "#005D9E", "#F2DEF8", "#DCD1F5", "#ACB6F2", "#719CF2", "#0085EB",
    "#F2D3D4", "#CEB0A8", "#AA8E7B", "#876D4F", "#654D25", "#FCDFE6", "#E2C7CB", "#C9B0B1", "#AF9896", "#96817C",
    "#FFE7E8", "#FFDCD6", "#FED7C5", "#FFD4B6", "#FFD5A3", "#FFEDEB", "#FFE6DC", "#FFDBBE", "#FFD5A4", "#FFD293",
    "#FFE4CD", "#FFE0BE", "#FFDEB4", "#FFDEB2", "#FFDBA8", "#FFE7F8", "#F5E0F6", "#EFDCF9", "#ECDBFB", "#DBD1F7",
    "#E5D6F6", "#B1B6EC", "#7797E1", "#1479D7", "#005C9D", "#EBDAF8", "#C9C7F7", "#A5B5F9", "#6A90DD", "#008BF5",
    "#E4D3ED", "#B1AFDA", "#7C8DC7", "#3C6CB3", "#004E85", "#FDE1E9", "#ECD1D9", "#DAC2C9", "#C9B2B9", "#B8A3A9"
    ]

COLS = 10
ROWS = 12


def color_matcher(hex_color):
    """ Match a colour similar to a color in the colors list.
    Used with REFI import """

    if len(hex_color) != 7:
        return "#D8D8D8"  # light gray
    test_r = int(hex_color[1:3], 16)
    test_g = int(hex_color[3:5], 16)
    test_b = int(hex_color[5:7], 16)

    best_match = ["#D8D8D8", 255.0]  # light gray default, colour difference
    for c in colors:
        r = int(c[1:3], 16)
        g = int(c[3:5], 16)
        b = int(c[5:7], 16)
        diff = (abs(r - test_r) + abs(g - test_g) + abs(b - test_b)) / 3
        if diff < best_match[1]:
            best_match = [c, diff]
    return best_match[0]


class DialogColorSelect(QtWidgets.QDialog):
    """ Dialog to select colour for code.
    Useful site for colours: https://www.tutorialrepublic.com/html-reference/html-color-picker.php
    """

    selected_color = None
    used_colors = []
    categories = []

    def __init__(self, app, code_, parent=None):

        super(DialogColorSelect, self).__init__(parent)
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_colour_selector()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.app = app
        font = f'font: {app.settings["fontsize"]}pt '
        font += f'"{app.settings["font"]}";'
        self.setStyleSheet(font)
        self.selected_color = code_['color']
        self.ui.tableWidget.setStyleSheet("border: none; font-size: 10px")
        self.ui.tableWidget.setTabKeyNavigation(False)
        cur = app.conn.cursor()
        cur.execute("select color, name from code_name order by name")
        self.used_colors = cur.fetchall()
        self.fill_table()
        # Preset with the current colour
        if code_['color']:
            fg_color = TextColor(code_['color']).recommendation
            style = "QLabel {background-color :" + code_['color'] + "; color : " + fg_color + ";}"
            self.ui.label_colour_old.setStyleSheet(style)
        self.ui.label_colour_old.setAutoFillBackground(True)
        self.ui.label_colour_old.setToolTip(_("Current colour"))
        self.ui.label_colour_old.setText(code_['name'])
        self.ui.label_colour_new.setToolTip(_("New colour"))
        self.ui.label_colour_new.setText(code_['name'])
        self.ui.radioButton_normal.toggled.connect(self.on_clicked)
        self.ui.radioButton_red_weak.toggled.connect(self.on_clicked)
        self.ui.radioButton_red_blind.toggled.connect(self.on_clicked)
        self.ui.radioButton_green_weak.toggled.connect(self.on_clicked)
        self.ui.radioButton_green_blind.toggled.connect(self.on_clicked)

    def on_clicked(self):
        if self.ui.radioButton_normal.isChecked():
            self.fill_table()
        if self.ui.radioButton_red_weak.isChecked():
            self.fill_table("red_weak")
        if self.ui.radioButton_red_blind.isChecked():
            self.fill_table("red_blind")
        if self.ui.radioButton_green_weak.isChecked():
            self.fill_table("green_weak")
        if self.ui.radioButton_green_blind.isChecked():
            self.fill_table("green_blind")

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
        """ Override accept button. """

        super(DialogColorSelect, self).accept()

    def fill_table(self, color_range="normal"):
        """ Twelve rows of ten columns of colours.
        normal, red weak, red blind, green weak, green blind
        param:
        color_range: String
        """

        self.ui.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        for r in range(self.ui.tableWidget.rowCount()):
            self.ui.tableWidget.removeRow(0)
        self.ui.tableWidget.setColumnCount(COLS)
        self.ui.tableWidget.setRowCount(ROWS)
        self.ui.tableWidget.verticalHeader().setVisible(False)
        self.ui.tableWidget.horizontalHeader().setVisible(False)
        for row in range(0, ROWS):
            for col in range(0, COLS):
                code_color = colors[row * COLS + col]
                text = ""
                ttip = ""
                for c in self.used_colors:
                    if code_color == c[0]:
                        text = "*"
                        ttip += f"{c[1]}\n"
                item = QtWidgets.QTableWidgetItem(text)
                item.setToolTip(ttip)
                if color_range == "normal":
                    item.setBackground(QtGui.QBrush(QtGui.QColor(code_color)))
                if color_range == "red_weak":
                    item.setBackground(QtGui.QBrush(QtGui.QColor(colors_red_weak[row * COLS + col])))
                if color_range == "red_blind":
                    item.setBackground(QtGui.QBrush(QtGui.QColor(colors_red_blind[row * COLS + col])))
                if color_range == "green_weak":
                    item.setBackground(QtGui.QBrush(QtGui.QColor(colors_green_weak[row * COLS + col])))
                if color_range == "green_blind":
                    item.setBackground(QtGui.QBrush(QtGui.QColor(colors_green_blind[row * COLS + col])))
                item.setForeground(QtGui.QBrush(QtGui.QColor(TextColor(code_color).recommendation)))
                item.setFlags(item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
                item.setFont(QtGui.QFont("Times", 10))
                self.ui.tableWidget.setItem(row, col, item)
                self.ui.tableWidget.setColumnWidth(col, 38)
            self.ui.tableWidget.setRowHeight(row, 22)
        self.ui.tableWidget.cellClicked.connect(self.color_selected)
