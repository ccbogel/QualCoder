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


class MainTabRail(QtCore.QObject):
    """Switch a QTabWidget between normal top tabs and a vertical, icon-only rail on the left."""

    def __init__(self, tab_widget, highlight_color, tab_size=44, icon_size=22):
        super().__init__(tab_widget)
        self.tab_widget = tab_widget
        self.bar = tab_widget.tabBar()
        self.highlight_color = highlight_color  # callable returning a colour name
        self.tab_size = tab_size
        self.rail_icon_size = QtCore.QSize(icon_size, icon_size)
        self.keyboard_focus = False
        self.enabled = False
        # Original look, restored when going back to top tabs
        self.original = {
            "position": tab_widget.tabPosition(),
            "icon_size": tab_widget.iconSize(),
            "expanding": self.bar.expanding(),
            "draw_base": self.bar.drawBase(),
            "scroll_buttons": self.bar.usesScrollButtons(),
            "stylesheet": self.bar.styleSheet(),
        }
        self.original_tooltips = {}

    def set_enabled(self, enabled):
        """Show the rail (True) or the normal top tabs (False)."""

        enabled = bool(enabled)
        if enabled == self.enabled:
            return
        self.enabled = enabled
        if enabled:
            self.original_tooltips = {self.tab_widget.widget(i): self.bar.tabToolTip(i)
                                      for i in range(self.bar.count())}
            self.tab_widget.setTabPosition(QtWidgets.QTabWidget.TabPosition.West)
            self.tab_widget.setIconSize(self.rail_icon_size)
            self.bar.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
            self.bar.setExpanding(False)
            self.bar.setDrawBase(False)
            self.bar.setUsesScrollButtons(True)
            # Titles stay as tab text (for screen readers) but are only shown as tooltips
            self.bar.setStyleSheet(
                f"QTabBar {{background: transparent; border: none;}}"
                f"QTabBar::tab {{width: {self.tab_size}px; height: {self.tab_size}px; margin: 0px;"
                f" padding: 0px; border: none; background: transparent;}}"
            )
            self.update_tooltips()
            self.bar.installEventFilter(self)
        else:
            self.bar.removeEventFilter(self)
            self.keyboard_focus = False
            self.bar.setStyleSheet(self.original["stylesheet"])
            self.tab_widget.setTabPosition(self.original["position"])
            self.tab_widget.setIconSize(self.original["icon_size"])
            self.bar.setExpanding(self.original["expanding"])
            self.bar.setDrawBase(self.original["draw_base"])
            self.bar.setUsesScrollButtons(self.original["scroll_buttons"])
            for index in range(self.bar.count()):
                self.bar.setTabToolTip(index, self.original_tooltips.get(self.tab_widget.widget(index), ""))
        self.bar.update()

    def update_tooltips(self):
        """Use each tab title as its tooltip."""

        for index in range(self.bar.count()):
            text = self.bar.tabText(index).replace("&", "")
            if text:
                self.bar.setTabToolTip(index, text)

    def eventFilter(self, obj, event):
        if obj is self.bar:
            event_type = event.type()
            if event_type == QtCore.QEvent.Type.Paint:
                self.paint_rail()
                return True
            if event_type == QtCore.QEvent.Type.FocusIn:
                self.keyboard_focus = event.reason() in (QtCore.Qt.FocusReason.TabFocusReason,
                                                         QtCore.Qt.FocusReason.BacktabFocusReason,
                                                         QtCore.Qt.FocusReason.ShortcutFocusReason)
            elif event_type == QtCore.QEvent.Type.FocusOut:
                self.keyboard_focus = False
            if event_type in (QtCore.QEvent.Type.HoverMove, QtCore.QEvent.Type.HoverLeave,
                              QtCore.QEvent.Type.Leave):
                self.bar.update()
        return super().eventFilter(obj, event)

    def paint_rail(self):
        """Draw upright icons, a soft highlight for the current tab and a hover tint."""

        bar = self.bar
        painter = QtGui.QPainter(bar)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        highlight = QtGui.QColor(self.highlight_color())
        hover_index = -1
        if bar.underMouse():
            hover_index = bar.tabAt(bar.mapFromGlobal(QtGui.QCursor.pos()))
        current = bar.currentIndex()
        icon_size = self.tab_widget.iconSize()
        for index in range(bar.count()):
            if not bar.isTabVisible(index):
                continue
            rect = bar.tabRect(index)
            if rect.isEmpty():
                continue
            box = QtCore.QRectF(rect.adjusted(5, 3, -5, -3))
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            if index == current:
                fill = QtGui.QColor(highlight)
                fill.setAlpha(55)
                painter.setBrush(fill)
                painter.drawRoundedRect(box, 8, 8)
                painter.setBrush(highlight)
                painter.drawRoundedRect(QtCore.QRectF(rect.left() + 1, box.top() + 9, 3, box.height() - 18), 1.5, 1.5)
                if bar.hasFocus() and self.keyboard_focus:
                    painter.setPen(QtGui.QPen(highlight, 1.5))
                    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                    painter.drawRoundedRect(box.adjusted(0.75, 0.75, -0.75, -0.75), 8, 8)
                    painter.setPen(QtCore.Qt.PenStyle.NoPen)
            elif index == hover_index and bar.isTabEnabled(index):
                fill = QtGui.QColor(highlight)
                fill.setAlpha(25)
                painter.setBrush(fill)
                painter.drawRoundedRect(box, 8, 8)
            icon = bar.tabIcon(index)
            if icon.isNull():
                continue
            mode = QtGui.QIcon.Mode.Normal if bar.isTabEnabled(index) else QtGui.QIcon.Mode.Disabled
            painter.setOpacity(1.0 if index == current else 0.7)
            icon_rect = QtCore.QRect(QtCore.QPoint(0, 0), icon_size)
            icon_rect.moveCenter(box.toRect().center())
            icon.paint(painter, icon_rect, QtCore.Qt.AlignmentFlag.AlignCenter, mode)
            painter.setOpacity(1.0)
        painter.end()
