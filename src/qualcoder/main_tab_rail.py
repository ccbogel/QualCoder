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
            "hover": self.bar.testAttribute(QtCore.Qt.WidgetAttribute.WA_Hover),
        }
        self.original_tooltips = {}
        self.original_texts = {}
        self.buttons_below_icon = {}  # tab page -> (button, spacer)
        self.footer = None  # widget kept at the bottom of the rail
        tab_widget.installEventFilter(self)
        self.button_spacer_height = 6  # extra height that the tab grows by

    def set_enabled(self, enabled):
        """Show the rail (True) or the normal top tabs (False)."""

        enabled = bool(enabled)
        if enabled == self.enabled:
            return
        self.enabled = enabled
        if enabled:
            self.original["widget_stylesheet"] = self.tab_widget.styleSheet()
            self.tab_widget.setProperty("main_tab_rail", True)
            # The native macOS style centres west tabs unless their position is explicit.
            self.tab_widget.setStyleSheet(
                self.original["widget_stylesheet"]
                + '\nQTabWidget[main_tab_rail="true"]::tab-bar {subcontrol-position: top left;}'
            )
            self.original_tooltips = {self.tab_widget.widget(i): self.bar.tabToolTip(i)
                                      for i in range(self.bar.count())}
            self.original_texts = {self.tab_widget.widget(i): self.bar.tabText(i)
                                   for i in range(self.bar.count())}
            self.tab_widget.setTabPosition(QtWidgets.QTabWidget.TabPosition.West)
            self.tab_widget.setIconSize(self.rail_icon_size)
            self.bar.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
            self.bar.setExpanding(False)
            self.bar.setDrawBase(False)
            self.bar.setUsesScrollButtons(True)
            # Minimum size only, so a tab with a button (AI Agent) grows to fit it
            self.bar.setStyleSheet(
                f"QTabBar {{background: transparent; border: none;}}"
                f"QTabBar::tab {{min-width: {self.tab_size}px; min-height: {self.tab_size}px; margin: 0px;"
                f" padding: 0px; border: none; background: transparent;}}"
            )
            # Titles move to tooltips and accessible names
            for index in range(self.bar.count()):
                title = self.bar.tabText(index).replace("&", "")
                if title:
                    self.bar.setTabToolTip(index, title)
                    if hasattr(self.bar, "setAccessibleTabName"):
                        self.bar.setAccessibleTabName(index, title)
                self.bar.setTabText(index, "")
            self.bar.installEventFilter(self)
        else:
            self.tab_widget.setProperty("main_tab_rail", False)
            self.tab_widget.setStyleSheet(self.original["widget_stylesheet"])
            for page in list(self.buttons_below_icon):
                self.detach_button_below_icon(page)
            self.bar.removeEventFilter(self)
            self.keyboard_focus = False
            self.bar.setStyleSheet(self.original["stylesheet"])
            self.tab_widget.setTabPosition(self.original["position"])
            self.tab_widget.setIconSize(self.original["icon_size"])
            self.bar.setExpanding(self.original["expanding"])
            self.bar.setDrawBase(self.original["draw_base"])
            self.bar.setUsesScrollButtons(self.original["scroll_buttons"])
            self.bar.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, self.original["hover"])
            for index in range(self.bar.count()):
                widget = self.tab_widget.widget(index)
                self.bar.setTabToolTip(index, self.original_tooltips.get(widget, ""))
                if widget in self.original_texts:
                    self.bar.setTabText(index, self.original_texts[widget])
                if hasattr(self.bar, "setAccessibleTabName"):
                    self.bar.setAccessibleTabName(index, "")
        self.bar.update()

    def set_footer(self, widget):
        """Keep a widget (help and settings buttons) at the bottom of the rail; None removes it."""

        if self.footer is not None and self.footer is not widget:
            self.footer.hide()
        self.footer = widget
        if widget is not None:
            widget.setParent(self.tab_widget)
        self.place_footer()

    def place_footer(self):
        """Put the footer under the tabs, at the bottom of the rail column."""

        if self.footer is None or not self.enabled:
            return
        hint = self.footer.sizeHint()
        x = self.bar.x() + max(0, (self.bar.width() - hint.width()) // 2)
        y = max(self.bar.geometry().bottom() + 8, self.tab_widget.height() - hint.height() - 8)
        self.footer.setGeometry(x, y, hint.width(), hint.height())
        self.footer.show()
        self.footer.raise_()

    def eventFilter(self, obj, event):
        if obj is self.tab_widget and event.type() in (QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.LayoutRequest):
            self.place_footer()
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

    def attach_button_below_icon(self, page, button):
        """Show a small button right under a tab's icon; the tab grows just enough to fit it."""

        index = self.tab_widget.indexOf(page)
        if index < 0:
            return
        self.detach_button_below_icon(page)
        # An empty tab button reserves the extra height, the real button is placed by hand
        spacer = QtWidgets.QWidget(self.bar)
        spacer.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        spacer.setFixedSize(button.width(), self.button_spacer_height)
        self.bar.setTabButton(index, QtWidgets.QTabBar.ButtonPosition.LeftSide, spacer)
        button.setParent(self.bar)
        button.show()
        button.raise_()
        self.position_button_below_icon(index)
        self.buttons_below_icon[page] = (button, spacer)
        self.bar.update()

    def detach_button_below_icon(self, page):
        """Remove the reserved space added by attach_button_below_icon."""

        entry = self.buttons_below_icon.pop(page, None)
        if entry is None:
            return
        index = self.tab_widget.indexOf(page)
        if index >= 0:
            self.bar.setTabButton(index, QtWidgets.QTabBar.ButtonPosition.LeftSide, None)
        entry[0].hide()
        entry[1].deleteLater()

    def position_button_below_icon(self, index):
        """Place a tab's button under its icon; hide it while the tab is scrolled out of view."""

        page = self.tab_widget.widget(index)
        entry = self.buttons_below_icon.get(page)
        if entry is None or not self.bar.isTabVisible(index):
            return
        rect = self.bar.tabRect(index)
        if rect.isEmpty():
            return
        button = entry[0]
        button_rect = self.icon_and_button_rects(index, rect, self.tab_widget.iconSize())[1]
        if button.geometry() != button_rect:
            button.setGeometry(button_rect)
        in_view = self.bar.rect().contains(button_rect)
        if button.isVisibleTo(self.bar) != in_view:
            button.setVisible(in_view)

    def icon_and_button_rects(self, index, rect, icon_size):
        """Icon rect for a tab, plus the rect of its button below the icon if it has one."""

        page = self.tab_widget.widget(index)
        entry = self.buttons_below_icon.get(page)
        icon_rect = QtCore.QRect(QtCore.QPoint(0, 0), icon_size)
        if entry is None:
            icon_rect.moveCenter(rect.center())
            return icon_rect, None
        button = entry[0]
        # Icon and button stacked and centred together
        top = rect.top() + (rect.height() - icon_size.height() - button.height()) // 2
        icon_rect.moveCenter(rect.center())
        icon_rect.moveTop(top)
        button_rect = QtCore.QRect(QtCore.QPoint(0, 0), button.size())
        button_rect.moveCenter(icon_rect.center())
        button_rect.moveTop(icon_rect.bottom() + 1)
        return icon_rect, button_rect

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
            icon_rect = self.icon_and_button_rects(index, rect, icon_size)[0]
            self.position_button_below_icon(index)
            icon = bar.tabIcon(index)
            if icon.isNull():
                continue
            mode = QtGui.QIcon.Mode.Normal if bar.isTabEnabled(index) else QtGui.QIcon.Mode.Disabled
            painter.setOpacity(1.0 if index == current else 0.7)
            icon.paint(painter, icon_rect, QtCore.Qt.AlignmentFlag.AlignCenter, mode)
            painter.setOpacity(1.0)
        painter.end()
