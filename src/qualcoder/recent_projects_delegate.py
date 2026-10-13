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

from PyQt6 import QtCore, QtGui, QtWidgets

DATE_ROLE = QtCore.Qt.ItemDataRole.UserRole + 1
PATH_ROLE = QtCore.Qt.ItemDataRole.UserRole + 2


class RecentProjectDelegate(QtWidgets.QStyledItemDelegate):
    """Two-line rows for the recent projects drop-down: name and date, then the path."""

    def __init__(self, colors, parent=None):
        super().__init__(parent)
        self.colors = colors  # callable returning a dict with text, secondary and highlight

    def sizeHint(self, option, index):
        height = option.fontMetrics.height() * 2 + 16
        return QtCore.QSize(max(option.rect.width(), 200), height)

    def paint(self, painter, option, index):
        colors = self.colors()
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = option.rect
        highlight = QtGui.QColor(colors.get("highlight", "#3daee9"))
        selected = bool(option.state & QtWidgets.QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QtWidgets.QStyle.StateFlag.State_MouseOver)
        if selected or hovered:
            fill = QtGui.QColor(highlight)
            fill.setAlpha(45 if selected else 22)
            painter.fillRect(rect, fill)
        if selected:
            painter.fillRect(QtCore.QRect(rect.left(), rect.top(), 3, rect.height()), highlight)
        inner = rect.adjusted(10, 6, -10, -6)
        name = index.data(QtCore.Qt.ItemDataRole.DisplayRole) or ""
        date = index.data(DATE_ROLE) or ""
        path = index.data(PATH_ROLE) or ""
        line_height = option.fontMetrics.height()
        name_font = QtGui.QFont(option.font)
        name_font.setBold(True)
        # Date on the right of the first line
        date_width = option.fontMetrics.horizontalAdvance(date) if date else 0
        painter.setFont(option.font)
        painter.setPen(QtGui.QColor(colors.get("secondary", "#808080")))
        top_line = QtCore.QRect(inner.left(), inner.top(), inner.width(), line_height)
        painter.drawText(top_line, QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter, date)
        # Project name, elided before the date
        painter.setFont(name_font)
        painter.setPen(QtGui.QColor(colors.get("text", "#000000")))
        name_width = max(20, inner.width() - date_width - 8)
        name_text = QtGui.QFontMetrics(name_font).elidedText(name, QtCore.Qt.TextElideMode.ElideRight, name_width)
        painter.drawText(QtCore.QRect(inner.left(), inner.top(), name_width, line_height),
                         QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter, name_text)
        # Path on the second line, elided in the middle
        painter.setFont(option.font)
        painter.setPen(QtGui.QColor(colors.get("secondary", "#808080")))
        path_text = option.fontMetrics.elidedText(path, QtCore.Qt.TextElideMode.ElideMiddle, inner.width())
        painter.drawText(QtCore.QRect(inner.left(), inner.top() + line_height + 2, inner.width(), line_height),
                         QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter, path_text)
        painter.restore()
