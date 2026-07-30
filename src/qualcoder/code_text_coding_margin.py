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
https://qualcoder-org.github.io
https://qualcoder.wordpress.com/
https://qualcoder.org/
"""


import logging
from PyQt6 import QtCore, QtGui, QtWidgets
from .color_selector import TextColor


logger = logging.getLogger(__name__)


DEFAULT_CODING_MARGIN_WIDTH = 100
MINIMUM_CODING_MARGIN_WIDTH = 30
MINIMUM_CODING_MARGIN_LABEL_WIDTH = 60

class CodingMargin(QtWidgets.QWidget):
    """ Draws side bars adjacent to the text and code names.
    Uses a track-packing algorithm so that overlapping codes occupy distinct
    vertical lanes. Embedded in a container widget (widget_code_margin_left /
    widget_code_margin_right). Scroll synchronization
    with the editor is handled via signal-slot from the editor's vertical
    scrollbar.

    The 'side' parameter controls visual layout:
    - 'left':  lanes stack right-to-left (lane 0 nearest text), names at far left.
    - 'right': lanes stack left-to-right (lane 0 nearest text), names at far right.
    """

    def __init__(self, editor, dialog_code_text, side='left'):
        super().__init__()
        self.editor = editor
        self.dialog = dialog_code_text
        self.side = side  # 'left' or 'right'
        self._hovered_tooltip_code_key = None
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._emit_context_menu_to_dialog)
        self.setMouseTracking(True)
        self.setMinimumWidth(MINIMUM_CODING_MARGIN_WIDTH)

    def _emit_context_menu_to_dialog(self, position):
        if hasattr(self.dialog, 'coding_margin_context_menu'):
            self.dialog.coding_margin_context_menu(position, self)

    def _set_tooltip_style_for_code(self, code):
        """Match the tooltip widget colors to the hovered code."""

        tooltip_color = code.get('color', '#cccccc')
        tooltip_text_color = TextColor(tooltip_color).recommendation
        self.setStyleSheet(
            "QToolTip {"
            f" background-color: {tooltip_color};"
            f" color: {tooltip_text_color};"
            f" border: 1px solid {tooltip_color};"
            "}"
        )

    def _clear_tooltip_style(self):
        """Restore the default tooltip styling when no code tooltip is active."""

        self.setStyleSheet("")

    @staticmethod
    def _tooltip_code_key(code):
        """Return a stable identifier for one hovered coded segment."""

        if code is None:
            return None
        ctid = code.get('ctid')
        if ctid is not None:
            return ('ctid', ctid)
        return ('range', code.get('fid'), code.get('pos0'), code.get('pos1'), code.get('cid'))

    def _compute_lane_layout(self):
        """ Track-packing algorithm. Returns (ctid_columns, sorted_codes,
        current_fid), or (None, [], None) if the layout cannot be computed. """

        if not self.dialog.file_ or not self.dialog.code_text:
            return None, [], None

        current_fid = self.dialog.file_['id']
        important_only = getattr(self.dialog, 'important', False)

        sorted_codes = sorted(
            [c for c in self.dialog.code_text
             if c.get('fid') == current_fid
             and (not important_only or c.get('important') == 1)],
            key=lambda x: x.get('pos0', 0)
        )

        ctid_columns = {}
        tracks = []
        for code in sorted_codes:
            ctid = code.get('ctid')
            if ctid is None:
                continue
            placed = False
            for i, track_end in enumerate(tracks):
                if track_end <= code['pos0']:
                    tracks[i] = code['pos1']
                    ctid_columns[ctid] = i
                    placed = True
                    break
            if not placed:
                tracks.append(code['pos1'])
                ctid_columns[ctid] = len(tracks) - 1

        return ctid_columns, sorted_codes, current_fid

    @staticmethod
    def _relative_luminance(color: QtGui.QColor) -> float:
        """Return the WCAG relative luminance for one QColor."""

        def channel_luminance(value: int) -> float:
            normalized = value / 255.0
            if normalized <= 0.03928:
                return normalized / 12.92
            return ((normalized + 0.055) / 1.055) ** 2.4

        red = channel_luminance(color.red())
        green = channel_luminance(color.green())
        blue = channel_luminance(color.blue())
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    @classmethod
    def _contrast_ratio(cls, first: QtGui.QColor, second: QtGui.QColor) -> float:
        """Return the WCAG contrast ratio for two QColors."""

        first_luminance = cls._relative_luminance(first)
        second_luminance = cls._relative_luminance(second)
        lighter = max(first_luminance, second_luminance)
        darker = min(first_luminance, second_luminance)
        return (lighter + 0.05) / (darker + 0.05)

    @classmethod
    def _label_color_for_background(cls, base_color: QtGui.QColor,
                                    background_color: QtGui.QColor,
                                    minimum_ratio: float = 4.5) -> QtGui.QColor:
        """Return a hue-preserving label color that meets the target contrast."""

        if cls._contrast_ratio(base_color, background_color) >= minimum_ratio:
            return base_color

        hue, saturation, lightness, alpha = base_color.getHsl()
        if hue < 0:
            hue = 0
            saturation = 0

        light_candidate = None
        for new_lightness in range(lightness + 1, 256):
            candidate = QtGui.QColor.fromHsl(hue, saturation, new_lightness, alpha)
            if cls._contrast_ratio(candidate, background_color) >= minimum_ratio:
                light_candidate = candidate
                break

        dark_candidate = None
        for new_lightness in range(lightness - 1, -1, -1):
            candidate = QtGui.QColor.fromHsl(hue, saturation, new_lightness, alpha)
            if cls._contrast_ratio(candidate, background_color) >= minimum_ratio:
                dark_candidate = candidate
                break

        if light_candidate is None:
            return dark_candidate if dark_candidate is not None else base_color
        if dark_candidate is None:
            return light_candidate

        light_delta = abs(light_candidate.lightness() - lightness)
        dark_delta = abs(dark_candidate.lightness() - lightness)
        return light_candidate if light_delta <= dark_delta else dark_candidate

    def paintEvent(self, event):
        try:
            painter = QtGui.QPainter(self)
            background_color = self.editor.viewport().palette().color(QtGui.QPalette.ColorRole.Base)
            painter.fillRect(event.rect(), background_color)
            if not self.dialog.file_ or not self.dialog.code_text:
                return
            font = QtGui.QFont(self.dialog.app.settings['font'], 9)
            painter.setFont(font)
            offset = self.editor.contentOffset()
            block = self.editor.firstVisibleBlock()

            ctid_columns, _sorted_codes, current_fid = self._compute_lane_layout()
            if current_fid is None:
                return

            drawn_ctids = set()

            while block.isValid():
                rect = self.editor.blockBoundingGeometry(block).translated(offset)
                if rect.top() > self.height():
                    break
                if rect.bottom() >= 0:
                    self.draw_code_bars(painter, block, rect, drawn_ctids, current_fid, ctid_columns)
                block = block.next()
        except Exception as e:
            logger.debug(f"CodingMargin paintEvent error: {e}")

    def draw_code_bars(self, painter, block, rect, drawn_ctids, current_fid, ctid_columns):
        """ Draw a coloured vertical bar per overlapping code on this block,
        plus the code name at the appropriate edge (only once per segment) """

        file_start = self.dialog.file_.get('start', 0)
        block_start = block.position() + file_start
        block_end = block_start + block.length()

        names_drawn_by_line = {}
        margin_width = self.width()
        show_labels = margin_width >= MINIMUM_CODING_MARGIN_LABEL_WIDTH
        background_color = self.editor.viewport().palette().color(QtGui.QPalette.ColorRole.Base)

        important_only = getattr(self.dialog, 'important', False)
        layout = block.layout()

        bar_w = 3
        lane_step = 10

        for code in self.dialog.code_text:
            if code.get('fid') != current_fid:
                continue
            if important_only and code.get('important') != 1:
                continue
            ctid = code.get('ctid')
            if ctid is None:
                continue

            if code['pos0'] < block_end and code['pos1'] > block_start:
                col_index = ctid_columns.get(ctid, 0)

                if self.side == 'right':
                    offset_x = 12 + (col_index * lane_step)
                else:  # 'left'
                    offset_x = margin_width - 15 - (col_index * lane_step)

                color_hex = code.get('color', '#cccccc')
                color = QtGui.QColor(color_hex)
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.setBrush(color)

                start_rel = max(code['pos0'], block_start) - block_start
                end_rel = min(code['pos1'], block_end) - block_start
                start_rel = max(0, min(start_rel, max(0, block.length() - 1)))
                end_rel = max(start_rel + 1, min(end_rel, block.length()))
                start_line = layout.lineForTextPosition(start_rel)
                end_line = layout.lineForTextPosition(max(start_rel, end_rel - 1))

                if start_line.isValid() and end_line.isValid():
                    first_line = start_line.lineNumber()
                    last_line = end_line.lineNumber()
                    for line_number in range(first_line, last_line + 1):
                        line = layout.lineAt(line_number)
                        if not line.isValid():
                            continue
                        painter.drawRect(
                            offset_x,
                            int(rect.top() + line.y()),
                            bar_w,
                            max(1, int(line.height()))
                        )
                else:
                    painter.drawRect(offset_x, int(rect.top()), bar_w, int(rect.height()))

                if show_labels and ctid not in drawn_ctids and code['pos0'] >= block_start:
                    painter.setPen(self._label_color_for_background(color, background_color))
                    raw_name = code.get('name', '')
                    _fm = painter.fontMetrics()
                    if self.side == 'right':
                        _lanes_end_x = 12 + (col_index + 1) * lane_step
                        _available_w = max(0, margin_width - _lanes_end_x - 5)
                    else:  # 'left'
                        _lanes_start_x = margin_width - 15 - (col_index + 1) * lane_step
                        _available_w = max(0, _lanes_start_x - 5 - 5)
                    name = _fm.elidedText(
                        raw_name, QtCore.Qt.TextElideMode.ElideRight, _available_w)

                    if start_line.isValid():
                        line_number = start_line.lineNumber()
                        names_on_line = names_drawn_by_line.get(line_number, 0)
                        y_pos = int(rect.top() + start_line.y()
                                    + painter.fontMetrics().ascent()
                                    + (names_on_line * 12))
                        names_drawn_by_line[line_number] = names_on_line + 1
                    else:
                        names_on_line = names_drawn_by_line.get(-1, 0)
                        y_pos = int(rect.top() + painter.fontMetrics().ascent()
                                    + (names_on_line * 12))
                        names_drawn_by_line[-1] = names_on_line + 1

                    if self.side == 'right':
                        name_w = painter.fontMetrics().horizontalAdvance(name)
                        x_pos = max(margin_width - name_w - 5, 18)
                    else:  # 'left'
                        x_pos = 5

                    painter.drawText(x_pos, y_pos, name)
                    drawn_ctids.add(ctid)

    def _code_at_position(self, pos):
        """ Return the code_text item under the given QPoint, or None.
        Matches both the coloured stripe and the code name label"""

        if not self.dialog.file_ or not self.dialog.code_text:
            return None

        ctid_columns, _sorted, current_fid = self._compute_lane_layout()
        if current_fid is None:
            return None

        margin_width = self.width()
        show_labels = margin_width >= MINIMUM_CODING_MARGIN_LABEL_WIDTH
        bar_w = 3
        lane_step = 10

        offset = self.editor.contentOffset()
        block = self.editor.firstVisibleBlock()
        file_start = self.dialog.file_.get('start', 0)
        important_only = getattr(self.dialog, 'important', False)

        stripe_hit = None
        label_hit = None

        font = QtGui.QFont(self.dialog.app.settings['font'], 9)
        fm = QtGui.QFontMetrics(font)

        while block.isValid():
            rect = self.editor.blockBoundingGeometry(block).translated(offset)
            if rect.top() > self.height():
                break
            if rect.bottom() < 0:
                block = block.next()
                continue

            block_start = block.position() + file_start
            block_end = block_start + block.length()
            layout = block.layout()

            seen_ctids_in_block = set()
            names_drawn_by_line = {}

            for code in self.dialog.code_text:
                if code.get('fid') != current_fid:
                    continue
                if important_only and code.get('important') != 1:
                    continue
                ctid = code.get('ctid')
                if ctid is None:
                    continue
                if not (code['pos0'] < block_end and code['pos1'] > block_start):
                    continue

                col_index = ctid_columns.get(ctid, 0)
                if self.side == 'right':
                    offset_x = 12 + (col_index * lane_step)
                else:
                    offset_x = margin_width - 15 - (col_index * lane_step)

                start_rel = max(code['pos0'], block_start) - block_start
                end_rel = min(code['pos1'], block_end) - block_start
                start_rel = max(0, min(start_rel, max(0, block.length() - 1)))
                end_rel = max(start_rel + 1, min(end_rel, block.length()))
                start_line = layout.lineForTextPosition(start_rel)
                end_line = layout.lineForTextPosition(max(start_rel, end_rel - 1))

                if start_line.isValid() and end_line.isValid():
                    first_line = start_line.lineNumber()
                    last_line = end_line.lineNumber()
                    for line_number in range(first_line, last_line + 1):
                        line = layout.lineAt(line_number)
                        if not line.isValid():
                            continue
                        stripe_rect = QtCore.QRect(
                            offset_x,
                            int(rect.top() + line.y()),
                            bar_w,
                            max(1, int(line.height())))
                        if stripe_rect.contains(pos):
                            stripe_hit = code

                if show_labels and ctid not in seen_ctids_in_block and code['pos0'] >= block_start:
                    raw_name = code.get('name', '')
                    if self.side == 'right':
                        _lanes_end_x = 12 + (col_index + 1) * lane_step
                        _available_w = max(0, margin_width - _lanes_end_x - 5)
                    else:  # 'left'
                        _lanes_start_x = margin_width - 15 - (col_index + 1) * lane_step
                        _available_w = max(0, _lanes_start_x - 5 - 5)
                    name = fm.elidedText(
                        raw_name, QtCore.Qt.TextElideMode.ElideRight, _available_w)
                    if start_line.isValid():
                        line_number = start_line.lineNumber()
                        names_on_line = names_drawn_by_line.get(line_number, 0)
                        y_pos = int(rect.top() + start_line.y()
                                    + fm.ascent()
                                    + (names_on_line * 12))
                        names_drawn_by_line[line_number] = names_on_line + 1
                    else:
                        names_on_line = names_drawn_by_line.get(-1, 0)
                        y_pos = int(rect.top() + fm.ascent() + (names_on_line * 12))
                        names_drawn_by_line[-1] = names_on_line + 1

                    name_w = fm.horizontalAdvance(name)
                    if self.side == 'right':
                        x_pos = max(margin_width - name_w - 5, 18)
                    else:
                        x_pos = 5

                    label_rect = QtCore.QRect(
                        x_pos,
                        y_pos - fm.ascent(),
                        name_w,
                        fm.height())
                    if label_rect.contains(pos):
                        label_hit = code
                    seen_ctids_in_block.add(ctid)

            block = block.next()

        return stripe_hit if stripe_hit is not None else label_hit

    def mouseMoveEvent(self, event):
        """ hover over a code -> show tooltip """

        try:
            code = self._code_at_position(event.pos())
        except Exception as e:
            logger.debug(f"CodingMargin hit-test error: {e}")
            code = None

        if code is None:
            if self._hovered_tooltip_code_key is not None:
                QtWidgets.QToolTip.hideText()
                self._clear_tooltip_style()
                self._hovered_tooltip_code_key = None
            self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            super().mouseMoveEvent(event)
            return

        code_key = self._tooltip_code_key(code)
        if code_key == self._hovered_tooltip_code_key:
            self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
            super().mouseMoveEvent(event)
            return

        try:
            tooltip_html = self.dialog._build_code_tooltip_html(code)
        except Exception as e:
            logger.debug(f"CodingMargin tooltip build error: {e}")
            tooltip_html = code.get('name', '')

        self._set_tooltip_style_for_code(code)
        QtWidgets.QToolTip.showText(event.globalPosition().toPoint(),
                                    tooltip_html,
                                    self)
        self._hovered_tooltip_code_key = code_key
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        super().mouseMoveEvent(event)

    def wheelEvent(self, event):
        """Forward mouse-wheel scrolling to the associated text editor."""

        QtWidgets.QApplication.sendEvent(self.editor.viewport(), event)
        if event.isAccepted():
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event):
        """ left-click on stripe/label -> select that exact coded segment in editor. """

        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            try:
                code = self._code_at_position(event.pos())
            except Exception as e:
                logger.debug(f"CodingMargin click hit-test error: {e}")
                code = None
            if code is not None and self.dialog.file_ is not None:
                file_start = self.dialog.file_.get('start', 0)
                pos0 = code['pos0'] - file_start
                pos1 = code['pos1'] - file_start
                text_len = len(self.dialog.ui.plainTextEdit.toPlainText())
                pos0 = max(0, min(pos0, text_len))
                pos1 = max(0, min(pos1, text_len))
                cursor = self.dialog.ui.plainTextEdit.textCursor()
                cursor.setPosition(pos0, QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(pos1, QtGui.QTextCursor.MoveMode.KeepAnchor)
                self.dialog.ui.plainTextEdit.setTextCursor(cursor)
                self.dialog.ui.plainTextEdit.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
                self.dialog.ui.plainTextEdit.ensureCursorVisible()
                event.accept()
                return
        super().mousePressEvent(event)

    def leaveEvent(self, event):
        QtWidgets.QToolTip.hideText()
        self._clear_tooltip_style()
        self._hovered_tooltip_code_key = None
        self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)
