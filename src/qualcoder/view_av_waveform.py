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

Author: Colin Curtain C, Kai Dröge, Justin Missaghieh--Poncet, Lorenzo Salomón
https://github.com/ccbogel/QualCoder
https://qualcoder-org.github.io
https://qualcoder.wordpress.com/
https://qualcoder.org/
"""

import logging
import os
import shutil
import subprocess
import threading

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, pyqtSignal

from .helpers import msecs_to_hours_mins_secs

try:
    _("-")
except NameError:
    def _(text):
        return text



class WaveformSeekBar(QtWidgets.QWidget):
    """ Interactive waveform + seek + segment-selection bar. """

    # ms position where the user clicked (a click, not a drag) -> the host seeks
    positionClicked = pyqtSignal(int)
    # current selection (start_ms, end_ms); emitted live while dragging and on release.
    # An empty/cleared selection is signalled as (0, 0).
    selectionChanged = pyqtSignal(int, int)
    # Right-click: (segment_dict_or_None, global_QPoint). Host builds the menu.
    segmentContextRequested = pyqtSignal(object, object)
    # A coded band was resized by dragging an edge: (segment_dict, new_pos0_ms, new_pos1_ms)
    segmentResized = pyqtSignal(object, int, int)

    # How close (in pixels) a press+release must be to count as a click rather than a drag.
    CLICK_TOLERANCE_PX = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self._duration_ms = 0
        self._position_ms = 0
        self._waveform = None          # QPixmap or None
        self._no_wave_msg = ""         # hint shown in the wave area when there is no image
        self._segments = []            # list of dicts: pos0, pos1, color, codename, cid, avid, _lane
        self._lane_count = 1

        # Selection state
        self._sel_start_ms = None
        self._sel_end_ms = None
        self._dragging = False
        self._press_x = None

        # Edge-resize state (dragging a coded band's start/end edge)
        self._resize_seg = None        # segment currently being dragged
        self._resize_edge = None       # 'start' or 'end'
        self._edge_grab_px = 6         # how close to an edge counts as grabbing it
        self._resize_avid = None       # avid of the segment whose handles are active

        # Layout metrics (pixels)
        self._top_pad = 4              # space above waveform
        self._wave_height = 56         # height of the waveform band
        self._lane_height = 6          # base lane height (no labels)
        self._lane_height_labels = 16  # lane height when code names are shown
        self._lane_gap = 1
        self._bottom_pad = 2
        self._show_labels = True       # draw code names on the bands (flat view only)

        # Track view: one lane per code with a left header column; no text on the bands.
        self._track_view = False
        self._header_w = 110           # width of the code-header column
        self._track_row_h = 14         # height of one sub-row inside a code lane
        self._track_gap = 2            # vertical gap between code lanes
        self._collapsed = set()        # cids drawn as a single row (header click toggles)
        self._tracks = []              # [{cid, name, color, rows, count, top, height}]
        # Lanes can be hidden when an external SegmentTracksView shows the bands.
        self._lanes_visible = True
        self._left_inset = 0           # left offset to align with an external tracks widget
        self._right_inset = 0          # right gutter (e.g. the tracks list scrollbar width)

        self.setMouseTracking(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                           QtWidgets.QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(self._min_height())
        self.setToolTip("")
        # Drive the context menu from the right mouse button instead of the OS context-menu
        # event, which is not reliably delivered when the widget becomes a native window
        # (e.g. alongside an embedded VLC video). See mousePressEvent.
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        # Resize handles clear when focus moves elsewhere.
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

    def focusOutEvent(self, event):
        self.clear_resize()
        super().focusOutEvent(event)

    def _lane_h(self):
        return self._lane_height_labels if self._show_labels else self._lane_height

    def set_duration(self, ms):
        """ Total media duration in milliseconds. """
        self._duration_ms = int(ms) if ms and ms > 0 else 0
        self.update()

    def set_position(self, ms):
        """ Current playhead position in milliseconds. Called from the play timer. """
        self._position_ms = int(ms) if ms and ms > 0 else 0
        self.update()

    def set_waveform_pixmap(self, pixmap):
        """ Optional waveform image (QPixmap). It is rescaled to the widget width on paint. """
        self._waveform = pixmap
        self.update()

    def set_no_waveform_message(self, msg):
        """ Hint drawn in the wave area when no waveform image is available
        (e.g. ffmpeg missing). Empty string clears it. """
        self._no_wave_msg = msg or ""
        self.update()

    def set_segments(self, segments):
        """ List of coded segment dicts. Each needs at least pos0, pos1 (ms).
        Optional keys used for display: color (hex string), codename, cid, avid. """
        self._segments = [dict(s) for s in (segments or [])]
        self._pack_lanes()
        self.setMinimumHeight(self._min_height())
        self.updateGeometry()
        self.update()

    def clear_selection(self):
        self._sel_start_ms = None
        self._sel_end_ms = None
        self._dragging = False
        self._press_x = None
        self.update()

    def set_selection(self, start_ms, end_ms):
        """ Set the visible selection overlay programmatically (e.g. from the Start/End
        segment buttons). Does not emit selectionChanged. """
        if start_ms is None or end_ms is None:
            self._sel_start_ms = None
            self._sel_end_ms = None
        else:
            self._sel_start_ms = int(start_ms)
            self._sel_end_ms = int(end_ms)
        self.update()

    @property
    def show_labels(self):
        return self._show_labels

    def set_show_labels(self, value):
        """ Show or hide code names on the coded bands. """
        self._show_labels = bool(value)
        self.setMinimumHeight(self._min_height())
        self.updateGeometry()
        self.update()

    def toggle_labels(self):
        self.set_show_labels(not self._show_labels)
        return self._show_labels

    def set_track_view(self, value):
        """ 
        Switch between the track view (lanes per code) and the flat stacked view.
        """
        self._track_view = bool(value)
        self._pack_lanes()
        self.setMinimumHeight(self._min_height())
        self.updateGeometry()
        self.update()

    def toggle_track_view(self):
        self.set_track_view(not self._track_view)
        return self._track_view

    def set_lanes_visible(self, value):
        """
        Hide the lane bands (an external tracks widget shows them); the wave tint,
        selection, playhead and segment right-click on the wave remain.
        """
        self._lanes_visible = bool(value)
        self.setMinimumHeight(self._min_height())
        self.updateGeometry()
        self.update()

    def set_left_inset(self, px):
        """
        Left inset so the wave timeline aligns with an external tracks widget.
        """
        self._left_inset = max(int(px), 0)
        self.update()

    def set_right_inset(self, px):
        """
        Right gutter so the wave timeline matches the tracks list viewport width
        and both playheads stay aligned.
        """
        self._right_inset = max(int(px), 0)
        self.update()

    def get_selection(self):
        """
        Return (start_ms, end_ms) normalised, or None.
        """
        if self._sel_start_ms is None or self._sel_end_ms is None:
            return None
        a, b = self._sel_start_ms, self._sel_end_ms
        return (min(a, b), max(a, b))

    # Geometry helpers
    def _min_height(self):
        if not self._lanes_visible and not self._track_view:
            return self._top_pad + self._wave_height + self._bottom_pad
        if self._track_view:
            h = self._top_pad + self._wave_height + self._track_gap
            for t in self._tracks:
                h += t['height'] + self._track_gap
            return h + self._bottom_pad
        lanes = max(self._lane_count, 1)
        return (self._top_pad + self._wave_height +
                lanes * (self._lane_h() + self._lane_gap) + self._bottom_pad)

    def _x0(self):
        """
        Left edge of the timeline area (after the header column in track view).
        """
        return self._header_w if self._track_view else self._left_inset

    def _timeline_w(self):
        return max(self.width() - self._x0() - self._right_inset, 1)

    def _wave_rect(self):
        return QtCore.QRect(self._x0(), self._top_pad, self._timeline_w(), self._wave_height)

    def _x_to_ms(self, x):
        if self._duration_ms <= 0 or self.width() <= 0:
            return 0
        x = max(self._x0(), min(x, self._x0() + self._timeline_w())) - self._x0()
        return int(x / self._timeline_w() * self._duration_ms)

    def _ms_to_x(self, ms):
        if self._duration_ms <= 0 or self.width() <= 0:
            return 0
        # VLC can report out-of-range positions: clamp to avoid Qt int32 overflow in drawLine.
        ms = max(0, min(int(ms), self._duration_ms))
        return self._x0() + int(ms / self._duration_ms * self._timeline_w())

    def _pack_lanes(self):
        """
        Greedy lane assignment so overlapping segments draw on separate rows. In
        track view segments are grouped by code: one lane per code, sub-rows only where
        segments of the SAME code overlap; collapsed codes draw in a single row.
        """
        self._tracks = []
        self._lane_count = 1
        if not self._track_view:
            lanes_end = []  # end ms of last segment placed in each lane
            for s in sorted(self._segments, key=lambda x: (x.get('pos0', 0), x.get('pos1', 0))):
                placed = False
                for lane_idx, end_ms in enumerate(lanes_end):
                    if s.get('pos0', 0) >= end_ms:
                        s['_lane'] = lane_idx
                        lanes_end[lane_idx] = s.get('pos1', 0)
                        placed = True
                        break
                if not placed:
                    s['_lane'] = len(lanes_end)
                    lanes_end.append(s.get('pos1', 0))
            self._lane_count = max(len(lanes_end), 1)
            return
        # Track view: group by cid, ordered by code name
        groups = {}
        for s in self._segments:
            groups.setdefault(s.get('cid'), []).append(s)
        top = self._top_pad + self._wave_height + self._track_gap
        for cid in sorted(groups, key=lambda c: str(groups[c][0].get('codename', '') or '').lower()):
            segs = sorted(groups[cid], key=lambda x: (x.get('pos0', 0), x.get('pos1', 0)))
            collapsed = cid in self._collapsed
            rows_end = []
            for s in segs:
                if collapsed:
                    s['_trow'] = 0
                    continue
                placed = False
                for row_idx, end_ms in enumerate(rows_end):
                    if s.get('pos0', 0) >= end_ms:
                        s['_trow'] = row_idx
                        rows_end[row_idx] = s.get('pos1', 0)
                        placed = True
                        break
                if not placed:
                    s['_trow'] = len(rows_end)
                    rows_end.append(s.get('pos1', 0))
            rows = 1 if collapsed else max(len(rows_end), 1)
            height = rows * self._track_row_h + (rows - 1) * 1 + 4  # 2 px padding top/bottom
            track = {'cid': cid, 'name': str(segs[0].get('codename', '') or ''),
                     'color': segs[0].get('color') or '#888888', 'rows': rows,
                     'count': len(segs), 'top': top, 'height': height}
            for s in segs:
                s['_track'] = track
            self._tracks.append(track)
            top += height + self._track_gap

    def _segment_band_rect(self, s):
        """
        Screen rect of a segment's band in the current view mode.
        """
        x0 = self._ms_to_x(s.get('pos0', 0))
        x1 = self._ms_to_x(s.get('pos1', 0))
        if x1 < x0:
            x0, x1 = x1, x0
        w = max(x1 - x0, 2)
        if not self._lanes_visible and not self._track_view:
            wr = self._wave_rect()
            return QtCore.QRect(x0, wr.top(), w, wr.height())
        if self._track_view:
            track = s.get('_track')
            if track is None:
                return QtCore.QRect(x0, self._top_pad + self._wave_height, w, self._track_row_h)
            row = s.get('_trow', 0)
            top = track['top'] + 2 + row * (self._track_row_h + 1)
            return QtCore.QRect(x0, top, w, self._track_row_h)
        lane = s.get('_lane', 0)
        top = (self._top_pad + self._wave_height + lane * (self._lane_h() + self._lane_gap))
        return QtCore.QRect(x0, top, w, self._lane_h())

    def _track_at(self, y):
        for t in self._tracks:
            if t['top'] <= y <= t['top'] + t['height']:
                return t
        return None

    def _segment_at(self, x, y):
        """ Return the segment dict whose band contains the point, else None. """
        for s in self._segments:
            if self._segment_band_rect(s).contains(x, y):
                return s
        return None

    def activate_resize(self, segment):
        """ Turn on the drag handles for this segment (host calls from the context menu). """
        if segment is None or segment.get('avid') is None:
            return
        self._resize_avid = segment.get('avid')
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.update()

    def clear_resize(self):
        """ Hide the drag handles. """
        if self._resize_avid is not None or self._resize_seg is not None:
            self._resize_avid = None
            self._resize_seg = None
            self._resize_edge = None
            self.unsetCursor()
            self.update()

    def cancel_interaction(self):
        """ Abort any in-progress drag/resize (e.g. after switching windows mid-action). """
        if self._dragging or self._resize_seg is not None or self._press_x is not None:
            self._dragging = False
            self._resize_seg = None
            self._resize_edge = None
            self._press_x = None
            self.unsetCursor()
            self.update()

    def _resize_target_seg(self):
        """ The segment whose handles are active, resolved live from current segments. """
        if self._resize_avid is None:
            return None
        for s in self._segments:
            if s.get('avid') == self._resize_avid:
                return s
        return None

    def _edge_at(self, x, y):
        """ If (x, y) is near an edge of the active-resize segment, return (segment, 'start'|'end').
        Only the segment with active handles is resizable. """
        seg = self._resize_target_seg()
        if seg is None:
            return None, None
        band = self._segment_band_rect(seg)
        if not (band.top() - 2 <= y <= band.bottom() + 2):
            return None, None
        x0 = self._ms_to_x(seg.get('pos0', 0))
        x1 = self._ms_to_x(seg.get('pos1', 0))
        if abs(x - x0) <= self._edge_grab_px:
            return seg, 'start'
        if abs(x - x1) <= self._edge_grab_px:
            return seg, 'end'
        return None, None

    # Mouse handling
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            # Right-click -> request a context menu (robust across native windows)
            seg = self._segment_at(int(event.position().x()), int(event.position().y()))
            self.segmentContextRequested.emit(seg, event.globalPosition().toPoint())
            return
        if event.button() != Qt.MouseButton.LeftButton or self._duration_ms <= 0:
            return super().mousePressEvent(event)
        px = int(event.position().x())
        py = int(event.position().y())
        # Header column: a click on a code header collapses/expands that lane.
        if self._track_view and px < self._header_w:
            track = self._track_at(py)
            if track is not None:
                cid = track['cid']
                if cid in self._collapsed:
                    self._collapsed.discard(cid)
                else:
                    self._collapsed.add(cid)
                self._pack_lanes()
                self.setMinimumHeight(self._min_height())
                self.updateGeometry()
                self.update()
            return
        # If handles are active and we press on an edge, start resizing
        seg, edge = self._edge_at(px, py)
        if seg is not None:
            self._resize_seg = seg
            self._resize_edge = edge
            self.setCursor(Qt.CursorShape.SizeHorCursor)
            return
        # Pressing elsewhere hides the handles, then proceeds normally
        if self._resize_avid is not None:
            self.clear_resize()
        self._press_x = px
        self._dragging = True
        ms = self._x_to_ms(self._press_x)
        self._sel_start_ms = ms
        self._sel_end_ms = ms
        self.update()

    def mouseMoveEvent(self, event):
        x = int(event.position().x())
        y = int(event.position().y())
        # Safety: if a drag/resize is in progress but no button is actually held (the release
        # was lost, e.g. when switching to another window), cancel it so input isn't stuck.
        if (self._dragging or self._resize_seg is not None) and \
                event.buttons() == Qt.MouseButton.NoButton:
            self._dragging = False
            self._resize_seg = None
            self._resize_edge = None
            self._press_x = None
            self.unsetCursor()
        if self._resize_seg is not None and self._duration_ms > 0:
            ms = self._x_to_ms(x)
            if self._resize_edge == 'start':
                self._resize_seg['pos0'] = max(0, min(ms, self._resize_seg.get('pos1', 0) - 1))
            else:
                self._resize_seg['pos1'] = min(self._duration_ms,
                                               max(ms, self._resize_seg.get('pos0', 0) + 1))
            QtWidgets.QToolTip.showText(
                event.globalPosition().toPoint(),
                f"{self._fmt(self._resize_seg.get('pos0', 0))} - {self._fmt(self._resize_seg.get('pos1', 0))}",
                self)
            self.update()
            return
        if self._dragging and self._duration_ms > 0:
            self._sel_end_ms = self._x_to_ms(x)
            sel = self.get_selection()
            if sel:
                QtWidgets.QToolTip.showText(
                    event.globalPosition().toPoint(),
                    f"{self._fmt(sel[0])} - {self._fmt(sel[1])}", self)
            self.update()
        else:
            # Hover: resize cursor near an edge, else show tooltip
            hover_seg, _hover_edge = self._edge_at(x, y)
            if hover_seg is not None:
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            else:
                self.unsetCursor()
            seg = self._segment_at(x, y)
            if seg is not None:
                name = str(seg.get('codename', '') or '')
                rng = f"{self._fmt(seg.get('pos0', 0))} - {self._fmt(seg.get('pos1', 0))}"
                tip = f"{name}\n{rng}" if name else rng
                memo = str(seg.get('memo', '') or '').strip()
                if memo:
                    if len(memo) > 600:
                        memo = memo[:600] + "…"
                    tip += f"\n\n{memo}"
            else:
                tip = self._fmt(self._x_to_ms(x))
            QtWidgets.QToolTip.showText(event.globalPosition().toPoint(), tip, self)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mouseReleaseEvent(event)
        # Finish an edge resize
        if self._resize_seg is not None:
            seg = self._resize_seg
            self._resize_seg = None
            self._resize_edge = None
            self.unsetCursor()
            self.segmentResized.emit(seg, int(seg.get('pos0', 0)), int(seg.get('pos1', 0)))
            return
        if not self._dragging:
            return super().mouseReleaseEvent(event)
        self._dragging = False
        release_x = int(event.position().x())
        if self._press_x is not None and abs(release_x - self._press_x) <= self.CLICK_TOLERANCE_PX:
            # Treat as a click -> seek, no selection
            self.clear_selection()
            self.selectionChanged.emit(0, 0)
            self.positionClicked.emit(self._x_to_ms(release_x))
            return
        sel = self.get_selection()
        if sel:
            self.selectionChanged.emit(sel[0], sel[1])
        self.update()

    def contextMenuEvent(self, event):
        seg = self._segment_at(int(event.pos().x()), int(event.pos().y()))
        self.segmentContextRequested.emit(seg, event.globalPos())

    def resizeEvent(self, event):
        self.update()
        super().resizeEvent(event)

    #  Painting
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        pal = self.palette()
        base = pal.color(QtGui.QPalette.ColorRole.Base)
        text_col = pal.color(QtGui.QPalette.ColorRole.Text)

        wave_rect = self._wave_rect()
        # Background of the waveform band
        painter.fillRect(wave_rect, base)

        # Waveform image, scaled to the current width
        if self._waveform is not None and not self._waveform.isNull():
            scaled = self._waveform.scaled(
                wave_rect.width(), wave_rect.height(),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(wave_rect.topLeft(), scaled)
        else:
            # No waveform available: draw a faint centre line so the bar is still usable
            mid = wave_rect.center().y()
            pen = QtGui.QPen(text_col)
            pen.setWidth(1)
            painter.setPen(pen)
            painter.setOpacity(0.25)
            painter.drawLine(0, mid, wave_rect.width(), mid)
            painter.setOpacity(1.0)
            if self._no_wave_msg:
                painter.setOpacity(0.55)
                painter.setPen(QtGui.QPen(text_col))
                painter.drawText(wave_rect, Qt.AlignmentFlag.AlignCenter, self._no_wave_msg)
                painter.setOpacity(1.0)

        # Non-cumulative tint: painted on a Source-composed overlay, so the most recent
        # coding wins on overlaps.
        if self._segments and self._duration_ms > 0:
            tint = QtGui.QImage(self.width(), wave_rect.height(),
                                QtGui.QImage.Format.Format_ARGB32_Premultiplied)
            tint.fill(QtGui.QColor(0, 0, 0, 0))
            tint_painter = QtGui.QPainter(tint)
            tint_painter.setCompositionMode(QtGui.QPainter.CompositionMode.CompositionMode_Source)
            for s in sorted(self._segments, key=lambda x: x.get('avid') or 0):
                seg_col = QtGui.QColor(s.get('color') or '#888888')
                if not seg_col.isValid():
                    seg_col = QtGui.QColor('#888888')
                seg_col.setAlpha(46)
                tx0 = self._ms_to_x(s.get('pos0', 0))
                tx1 = self._ms_to_x(s.get('pos1', 0))
                if tx1 < tx0:
                    tx0, tx1 = tx1, tx0
                tint_painter.fillRect(QtCore.QRect(tx0, 0, max(tx1 - tx0, 2), wave_rect.height()),
                                      seg_col)
            tint_painter.end()
            painter.drawImage(QtCore.QPoint(0, wave_rect.top()), tint)

        # Header column with one entry per code (track view)
        label_font = painter.font()
        label_font.setPointSize(8)
        fm = QtGui.QFontMetrics(label_font)
        if self._track_view:
            painter.setFont(label_font)
            sep = QtGui.QColor(text_col)
            sep.setAlpha(40)
            for t in self._tracks:
                chip = QtGui.QColor(t['color'])
                if not chip.isValid():
                    chip = QtGui.QColor('#888888')
                cy = t['top'] + t['height'] // 2
                painter.fillRect(QtCore.QRect(6, cy - 5, 10, 10), chip)
                painter.setPen(QtGui.QPen(text_col))
                count_txt = str(t['count'])
                count_w = fm.horizontalAdvance(count_txt)
                name_w = self._header_w - 22 - count_w - 8
                elided = fm.elidedText(t['name'], Qt.TextElideMode.ElideRight, max(name_w, 10))
                painter.drawText(QtCore.QRect(20, t['top'], max(name_w, 10), t['height']),
                                 int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), elided)
                painter.setOpacity(0.6)
                painter.drawText(QtCore.QRect(self._header_w - count_w - 6, t['top'], count_w + 2, t['height']),
                                 int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), count_txt)
                painter.setOpacity(1.0)
                painter.setPen(QtGui.QPen(sep))
                sep_y = t['top'] + t['height'] + self._track_gap // 2
                painter.drawLine(0, sep_y, self.width(), sep_y)
            painter.setPen(QtGui.QPen(sep))
            painter.drawLine(self._header_w - 1, self._top_pad, self._header_w - 1, self.height())

        # Coded segment bands
        lane_h = self._lane_h()
        lanes_drawn = self._lanes_visible or self._track_view
        for s in self._segments:
            band_rect = self._segment_band_rect(s)
            x0 = band_rect.left()
            w = band_rect.width()
            x1 = x0 + w
            top = band_rect.top()
            lane_h = band_rect.height()
            color = QtGui.QColor(s.get('color') or '#888888')
            if not color.isValid():
                color = QtGui.QColor('#888888')
            if lanes_drawn:
                painter.fillRect(band_rect, color)
            if self._track_view:
                border = QtGui.QColor(color).darker(140)
                painter.setPen(QtGui.QPen(border))
                painter.drawRect(band_rect.adjusted(0, 0, -1, -1))
            # Active-resize handles (only on the segment chosen via right-click -> Resize)
            if self._resize_avid is not None and s.get('avid') == self._resize_avid:
                handle_top = wave_rect.top()
                handle_h = (top + lane_h) - handle_top
                for hx in (x0, x1):
                    painter.fillRect(QtCore.QRect(hx - 2, handle_top, 4, handle_h),
                                     QtGui.QColor(20, 20, 20))
                    painter.fillRect(QtCore.QRect(hx - 1, handle_top, 2, handle_h),
                                     QtGui.QColor(255, 255, 255))
            # Code name on the band, only when lane bands are drawn (with lanes hidden the band
            # rect is the tinted wave span and names leaked onto the waveform).
            if lanes_drawn and not self._track_view and self._show_labels and w > 26:
                name = str(s.get('codename', '') or '')
                if name:
                    # Pick a contrasting text colour for this band
                    luma = 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
                    txt_color = QtGui.QColor('#000000') if luma > 140 else QtGui.QColor('#ffffff')
                    painter.setFont(label_font)
                    painter.setPen(QtGui.QPen(txt_color))
                    elided = fm.elidedText(name, Qt.TextElideMode.ElideRight, w - 6)
                    painter.drawText(QtCore.QRect(x0 + 3, top, w - 6, lane_h),
                                     int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                                     elided)

        # Current selection overlay (made prominent so Start/End marking is clearly visible)
        sel = self.get_selection()
        if sel is not None:
            sx0 = self._ms_to_x(sel[0])
            sx1 = self._ms_to_x(sel[1])
            full_h = self.height()
            sel_col = QtGui.QColor(25, 118, 210)  # blue, to match the blue waveform palette
            if sx1 > sx0:
                fill = QtGui.QColor(sel_col)
                fill.setAlpha(80)
                painter.fillRect(QtCore.QRect(sx0, 0, max(sx1 - sx0, 1), full_h), fill)
            pen = QtGui.QPen(sel_col)
            pen.setWidth(2 if sx1 != sx0 else 3)
            painter.setPen(pen)
            painter.drawLine(sx0, 0, sx0, full_h)
            if sx1 != sx0:
                painter.drawLine(sx1, 0, sx1, full_h)

        # Playhead
        px = self._ms_to_x(self._position_ms)
        pen = QtGui.QPen(QtGui.QColor('#d33'))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawLine(px, 0, px, self._top_pad + self._wave_height)

        painter.end()

    #  Small helper (kept local so the widget has no external deps)
    @staticmethod
    def _fmt(msecs):
        """ Format milliseconds as h:mm:ss for tooltips. """
        secs_total = int(msecs / 1000)
        h = secs_total // 3600
        m = (secs_total % 3600) // 60
        s = secs_total % 60
        if h > 0:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"


# Shared waveform image generation (used by code_av, view_av and manage_files)
logger = logging.getLogger(__name__)

# Serialise ffmpeg runs so a bulk import does not spawn many processes at once
_generation_lock = threading.Lock()


def waveform_colour(stylesheet):
    """
    Waveform colour matching the app theme.
    """
    return '#4a9eff' if stylesheet in ("dark", "rainbow") else '#1f6fb2'



class SegmentTracksView(QtWidgets.QWidget):
    """
    Scrollable list of coded-segment bars, separate from the waveform: one lane per
    code, sub-rows only where the same code overlaps, and a bar click selects its time
    span. Lives inside a QScrollArea.
    """

    # Left click on a bar: the host selects the segment's time span
    segmentClicked = pyqtSignal(object)
    # Right click: (segment_dict_or_None, global QPoint); host builds the menu
    segmentContextRequested = pyqtSignal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._duration_ms = 0
        self._position_ms = 0
        self._segments = []
        self._tracks = []
        self._collapsed = set()
        self._selected_avid = None
        self._row_h = 10               # 25% thinner bars than the first iteration
        self._row_gap = 1
        self._label_h = 18             # code name + total time line above each lane
        self._track_gap = 4
        self._pad = 2
        self._indent = 14              # horizontal indent per hierarchy level
        # Code tree hierarchy (categories, parent codes, sub-codes) for ordering and
        # collapsing branches as in the tree.
        self._codes_struct = []
        self._cats_struct = []
        self._collapsed_cats = set()   # catids drawn as one combined row
        self.setMouseTracking(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                           QtWidgets.QSizePolicy.Policy.Fixed)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)

    def set_duration(self, ms):
        self._duration_ms = int(ms) if ms and ms > 0 else 0
        self.update()

    def set_position(self, ms):
        self._position_ms = int(ms) if ms and ms > 0 else 0
        self.update()

    def set_code_structure(self, codes, categories):
        """
        Take the tree hierarchy (codes and categories) to order the lanes like the
        tree and allow collapsing branches.
        """
        self._codes_struct = [dict(c) for c in (codes or [])]
        self._cats_struct = [dict(c) for c in (categories or [])]
        self._pack()
        self.setMinimumHeight(self._content_height())
        self.updateGeometry()
        self.update()

    def set_segments(self, segments):
        self._segments = [dict(s) for s in (segments or [])]
        avids = {s.get('avid') for s in self._segments}
        if self._selected_avid not in avids:
            self._selected_avid = None
        self._pack()
        self.setMinimumHeight(self._content_height())
        self.updateGeometry()
        self.update()

    def clear(self):
        self.set_segments([])

    def _ordered_blocks(self):
        """
        Hierarchical order as in the code tree: categories (with sub-categories),
        their codes and sub-codes, then codes with no category. Only branches with
        segments. Returns blocks ('cat', cat, depth) / ('code', code, depth, cids).
        """
        groups = {}
        for s in self._segments:
            groups.setdefault(s.get('cid'), []).append(s)
        if not self._codes_struct:
            # No structure: flat alphabetical order (previous behaviour)
            blocks = []
            for cid in sorted(groups, key=lambda c: str(groups[c][0].get('codename', '') or '').lower()):
                code = {'cid': cid, 'name': str(groups[cid][0].get('codename', '') or ''),
                        'color': groups[cid][0].get('color') or '#888888', 'supercid': None}
                code['_path'] = [code['name']]
                blocks.append(('code', code, 0, [cid]))
            return blocks, groups
        subcodes = {}
        for c in self._codes_struct:
            if c.get('supercid') is not None:
                subcodes.setdefault(c['supercid'], []).append(c)
        cats_by_super = {}
        for cat in self._cats_struct:
            cats_by_super.setdefault(cat.get('supercatid'), []).append(cat)
        codes_by_cat = {}
        for c in self._codes_struct:
            if c.get('supercid') is None:
                codes_by_cat.setdefault(c.get('catid'), []).append(c)

        def branch_cids(code):
            out = [code['cid']]
            for sc in subcodes.get(code['cid'], []):
                out += branch_cids(sc)
            return out

        def name_key(x):
            return str(x.get('name', '') or '').lower()

        blocks = []

        def walk_code(code, depth, path):
            b_cids = branch_cids(code)
            if not any(c in groups for c in b_cids):
                return
            code = dict(code)
            code['_path'] = path + [str(code.get('name', '') or '')]
            blocks.append(('code', code, depth, b_cids))
            if code['cid'] not in self._collapsed:
                for sc in sorted(subcodes.get(code['cid'], []), key=name_key):
                    walk_code(sc, depth + 1, code['_path'])

        def cat_has_segments(cat):
            for child in cats_by_super.get(cat['catid'], []):
                if cat_has_segments(child):
                    return True
            for code in codes_by_cat.get(cat['catid'], []):
                if any(c in groups for c in branch_cids(code)):
                    return True
            return False

        def cat_branch_cids(cat):
            out = []
            for child in cats_by_super.get(cat['catid'], []):
                out += cat_branch_cids(child)
            for code in codes_by_cat.get(cat['catid'], []):
                out += branch_cids(code)
            return out

        def walk_cat(cat, depth, path):
            if not cat_has_segments(cat):
                return
            cat = dict(cat)
            cat['_path'] = path + [str(cat.get('name', '') or '')]
            blocks.append(('cat', cat, depth, cat_branch_cids(cat)))
            if cat['catid'] in self._collapsed_cats:
                return
            for child in sorted(cats_by_super.get(cat['catid'], []), key=name_key):
                walk_cat(child, depth + 1, cat['_path'])
            for code in sorted(codes_by_cat.get(cat['catid'], []), key=name_key):
                walk_code(code, depth + 1, cat['_path'])

        for cat in sorted(cats_by_super.get(None, []), key=name_key):
            walk_cat(cat, 0, [])
        for code in sorted(codes_by_cat.get(None, []), key=name_key):
            walk_code(code, 0, [])
        # Codes with segments missing from the structure (edge case: just created)
        known = {c['cid'] for c in self._codes_struct}
        for cid in sorted(set(groups) - known):
            code = {'cid': cid, 'name': str(groups[cid][0].get('codename', '') or ''),
                    'color': groups[cid][0].get('color') or '#888888', 'supercid': None}
            code['_path'] = [code['name']]
            blocks.append(('code', code, 0, [cid]))
        return blocks, groups

    def _pack(self):
        self._tracks = []
        blocks, groups = self._ordered_blocks()
        top = self._pad
        for kind, node, depth, b_cids in blocks:
            if kind == 'cat':
                collapsed = node['catid'] in self._collapsed_cats
                # A category always shows one summary row with every branch bar; collapsing hides
                # the child lanes.
                segs = []
                for c in b_cids:
                    segs += groups.get(c, [])
                segs.sort(key=lambda x: (x.get('pos0', 0), x.get('pos1', 0)))
                rows = 1 if segs else 0
                height = self._label_h + (rows * self._row_h + 4 if rows else 0)
                total_ms = sum(max(s.get('pos1', 0) - s.get('pos0', 0), 0) for s in segs)
                track = {'kind': 'cat', 'catid': node['catid'], 'cid': None,
                         'name': str(node.get('name', '') or ''),
                         'path': node.get('_path') or [str(node.get('name', '') or '')],
                         'color': None, 'depth': depth, 'rows': rows, 'count': len(segs),
                         'total_ms': total_ms, 'top': top, 'height': height,
                         'collapsed': collapsed, 'overview_segs': segs}
                if collapsed:
                    for s in segs:
                        s['_trow'] = 0
                        s['_track'] = track
                self._tracks.append(track)
                top += height + self._track_gap
                continue
            # code block
            cid = node['cid']
            collapsed = cid in self._collapsed
            segs = []
            if collapsed:
                for c in b_cids:
                    segs += groups.get(c, [])
            else:
                segs = list(groups.get(cid, []))
            segs.sort(key=lambda x: (x.get('pos0', 0), x.get('pos1', 0)))
            rows_end = []
            for s in segs:
                if collapsed:
                    s['_trow'] = 0
                    continue
                placed = False
                for row_idx, end_ms in enumerate(rows_end):
                    if s.get('pos0', 0) >= end_ms:
                        s['_trow'] = row_idx
                        rows_end[row_idx] = s.get('pos1', 0)
                        placed = True
                        break
                if not placed:
                    s['_trow'] = len(rows_end)
                    rows_end.append(s.get('pos1', 0))
            rows = 1 if collapsed else max(len(rows_end), 1)
            if not segs:
                rows = 0
            height = self._label_h + (rows * self._row_h + (max(rows - 1, 0)) * self._row_gap + 4 if rows else 0)
            total_ms = sum(max(s.get('pos1', 0) - s.get('pos0', 0), 0)
                           for c in b_cids for s in groups.get(c, []))
            track = {'kind': 'code', 'catid': None, 'cid': cid,
                     'name': str(node.get('name', '') or ''),
                     'path': node.get('_path') or [str(node.get('name', '') or '')],
                     'color': node.get('color') or (segs[0].get('color') if segs else '#888888'),
                     'depth': depth, 'rows': rows, 'count': len(segs),
                     'total_ms': total_ms, 'top': top, 'height': height,
                     'collapsed': collapsed}
            for s in segs:
                s['_track'] = track
            self._tracks.append(track)
            top += height + self._track_gap

    def _content_height(self):
        h = self._pad
        for t in self._tracks:
            h += t['height'] + self._track_gap
        return max(h + self._pad, self._row_h + 2 * self._pad)

    def _ms_to_x(self, ms):
        if self._duration_ms <= 0:
            return 0
        ms = max(0, min(int(ms), self._duration_ms))  # clamp: avoids int32 overflow
        return int(ms / self._duration_ms * max(self.width(), 1))

    def _band_rect(self, s):
        x0 = self._ms_to_x(s.get('pos0', 0))
        x1 = self._ms_to_x(s.get('pos1', 0))
        if x1 < x0:
            x0, x1 = x1, x0
        track = s.get('_track')
        if track is None:
            return QtCore.QRect(x0, self._pad, max(x1 - x0, 2), self._row_h)
        top = (track['top'] + self._label_h + 2 +
               s.get('_trow', 0) * (self._row_h + self._row_gap))
        return QtCore.QRect(x0, top, max(x1 - x0, 2), self._row_h)

    def _segment_at(self, x, y):
        for s in self._segments:
            if self._band_rect(s).contains(x, y):
                return s
        return None

    def _track_at(self, y):
        for t in self._tracks:
            if t['top'] <= y <= t['top'] + t['height']:
                return t
        return None

    def mousePressEvent(self, event):
        x = int(event.position().x())
        y = int(event.position().y())
        if event.button() == Qt.MouseButton.RightButton:
            self.segmentContextRequested.emit(self._segment_at(x, y),
                                              event.globalPosition().toPoint())
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)
        track = self._track_at(y)
        if track is not None and y <= track['top'] + self._label_h:
            # Click on the name line collapses/expands the code, or the branch for a category.
            if track.get('kind') == 'cat':
                catid = track['catid']
                if catid in self._collapsed_cats:
                    self._collapsed_cats.discard(catid)
                else:
                    self._collapsed_cats.add(catid)
            else:
                cid = track['cid']
                if cid in self._collapsed:
                    self._collapsed.discard(cid)
                else:
                    self._collapsed.add(cid)
            self._pack()
            self.setMinimumHeight(self._content_height())
            self.updateGeometry()
            self.update()
            return
        seg = self._segment_at(x, y)
        if seg is not None:
            self._selected_avid = seg.get('avid')
            self.update()
            self.segmentClicked.emit(seg)

    def mouseMoveEvent(self, event):
        seg = self._segment_at(int(event.position().x()), int(event.position().y()))
        if seg is not None:
            name = str(seg.get('codename', '') or '')
            rng = (msecs_to_hours_mins_secs(seg.get('pos0', 0)) + " - " +
                   msecs_to_hours_mins_secs(seg.get('pos1', 0)))
            tip = f"{name}\n{rng}" if name else rng
            memo = str(seg.get('memo', '') or '').strip()
            if memo:
                tip += "\n" + memo
            QtWidgets.QToolTip.showText(event.globalPosition().toPoint(), tip, self)
        super().mouseMoveEvent(event)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, False)
        pal = self.palette()
        base = pal.color(QtGui.QPalette.ColorRole.Base)
        text_col = pal.color(QtGui.QPalette.ColorRole.Text)
        painter.fillRect(QtCore.QRect(0, 0, self.width(), self.height()), base)
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)
        fm = QtGui.QFontMetrics(font)
        sep = QtGui.QColor(text_col)
        sep.setAlpha(40)
        for t in self._tracks:
            ly = t['top']
            x_base = 4 + t.get('depth', 0) * self._indent
            chevron = "\u25be " if not t.get('collapsed') else "\u25b8 "
            path_txt = " > ".join(t.get('path') or [t['name']])
            if t.get('kind') == 'cat':
                # Category header: chevron + italic path, no chip; its summary row below.
                painter.setPen(QtGui.QPen(text_col))
                cat_font = QtGui.QFont(painter.font())
                cat_font.setItalic(True)
                painter.setFont(cat_font)
                total_txt = ". " + _("Total: ") + msecs_to_hours_mins_secs(t['total_ms'])
                avail = max(self.width() - x_base - 8, 10)
                name_avail = max(avail - fm.horizontalAdvance(total_txt), 24)
                elided = fm.elidedText(chevron + path_txt, Qt.TextElideMode.ElideRight, name_avail)
                painter.drawText(QtCore.QRect(x_base, ly, avail, self._label_h),
                                 int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                                 elided + total_txt)
                cat_font.setItalic(False)
                painter.setFont(cat_font)
                # Category summary row (always, expanded too)
                if t['rows']:
                    row_top = ly + self._label_h + 2
                    for s in t.get('overview_segs', []):
                        sx0 = self._ms_to_x(s.get('pos0', 0))
                        sx1 = self._ms_to_x(s.get('pos1', 0))
                        if sx1 < sx0:
                            sx0, sx1 = sx1, sx0
                        band = QtCore.QRect(sx0, row_top, max(sx1 - sx0, 2), self._row_h)
                        s_col = QtGui.QColor(s.get('color') or '#888888')
                        if not s_col.isValid():
                            s_col = QtGui.QColor('#888888')
                        painter.fillRect(band, s_col)
                        painter.setPen(QtGui.QPen(QtGui.QColor(s_col).darker(140)))
                        painter.drawRect(band.adjusted(0, 0, -1, -1))
            else:
                # No colour chip before the code name (user preference).
                painter.setPen(QtGui.QPen(text_col))
                prefix = chevron if t['count'] else ""
                total_txt = ". " + _("Total: ") + msecs_to_hours_mins_secs(t['total_ms'])
                avail = max(self.width() - x_base - 22, 10)
                name_avail = max(avail - fm.horizontalAdvance(total_txt), 24)
                elided = fm.elidedText(prefix + path_txt, Qt.TextElideMode.ElideRight, name_avail)
                painter.drawText(QtCore.QRect(x_base, ly, avail, self._label_h),
                                 int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                                 elided + total_txt)
            painter.setPen(QtGui.QPen(sep))
            sep_y = t['top'] + t['height'] + self._track_gap // 2
            painter.drawLine(0, sep_y, self.width(), sep_y)
        for s in self._segments:
            band = self._band_rect(s)
            color = QtGui.QColor(s.get('color') or '#888888')
            if not color.isValid():
                color = QtGui.QColor('#888888')
            painter.fillRect(band, color)
            selected = (self._selected_avid is not None and
                        s.get('avid') == self._selected_avid)
            border = QtGui.QColor(color).darker(180 if selected else 140)
            pen = QtGui.QPen(border)
            pen.setWidth(2 if selected else 1)
            painter.setPen(pen)
            painter.drawRect(band.adjusted(0, 0, -1, -1))
        if self._duration_ms > 0:
            px = self._ms_to_x(self._position_ms)
            painter.setPen(QtGui.QPen(QtGui.QColor(200, 30, 30), 2))
            painter.drawLine(px, 0, px, self.height())
        painter.end()


# Bump when the waveform rendering changes: cached PNGs with an older or absent
# version are regenerated automatically.
WAVEFORM_PNG_VERSION = "3"

# Default when the optional block below is disabled: external ffmpeg only.
USE_PYAV = False
_pyav_render_waveform = None

# ==================== OPTIONAL PyAV waveform backend (BEGIN) =====================
# Renders the waveform by decoding audio with the PyAV library (pip package "av",
# FFmpeg bundled in the wheel, no external ffmpeg install needed).
# To DISABLE this backend, wrap everything between BEGIN and END in a pair of
# triple single-quotes (one line with three quotes before BEGIN and one after
# END): the module falls back to the external ffmpeg path automatically. "av" is NOT in requirements.txt; without it installed this
# block deactivates itself silently.
try:
    import av as _av
except ImportError:
    _av = None


def _pyav_render(media_path, out_path, colour, width=1020, height=100):
    """
    PyAV waveform PNG, showwavespic style: per-block min/max + RMS mapped to
    columns; ints normalised by dtype full scale, not per frame.
    """
    container = _av.open(media_path)
    astreams = [st for st in container.streams if st.type == 'audio']
    if not astreams:
        container.close()
        return False
    stream = astreams[0]
    block = 1024
    block_mins = []
    block_maxs = []
    block_rms = []
    carry = None
    import numpy as _np
    for frame in container.decode(stream):
        samples = frame.to_ndarray()
        # Normalise by the ORIGINAL dtype BEFORE the mono mix: mean() converts
        # packed (1, n) ints to float and scaling was skipped (solid band).
        orig_dtype = samples.dtype
        if samples.ndim > 1:  # channels x n -> mono mix
            samples = samples.mean(axis=0)
        if orig_dtype.kind == 'i':
            samples = samples.astype('float64') / float(_np.iinfo(orig_dtype).max)
        elif orig_dtype.kind == 'u':
            half = float(_np.iinfo(orig_dtype).max) / 2.0
            samples = (samples.astype('float64') - half) / half
        if carry is not None:
            import numpy as _np
            samples = _np.concatenate((carry, samples))
            carry = None
        n_full = (len(samples) // block) * block
        for i in range(0, n_full, block):
            chunk = samples[i:i + block]
            block_mins.append(float(chunk.min()))
            block_maxs.append(float(chunk.max()))
            ac = chunk.astype('float64')
            ac = ac - ac.mean()  # drop DC offset (painted a full block)
            block_rms.append(float((ac ** 2).mean() ** 0.5))
        if n_full < len(samples):
            carry = samples[n_full:]
    if carry is not None and len(carry):
        block_mins.append(float(carry.min()))
        block_maxs.append(float(carry.max()))
        ac = carry.astype('float64')
        ac = ac - ac.mean()
        block_rms.append(float((ac ** 2).mean() ** 0.5))
    container.close()
    if not block_mins:
        return False
    img = QtGui.QImage(width, height, QtGui.QImage.Format.Format_ARGB32)
    img.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(img)
    painter.setPen(QtGui.QColor(colour))
    mid = height // 2
    total_blocks = len(block_mins)
    # RMS body + faint peak outline: pure min/max saturates with hot audio
    peak_col = QtGui.QColor(colour)
    peak_col.setAlpha(90)
    body_col = QtGui.QColor(colour)
    for x in range(width):
        b0 = x * total_blocks // width
        b1 = max(b0 + 1, (x + 1) * total_blocks // width)
        mn = max(-1.0, min(1.0, min(block_mins[b0:b1])))
        mx = max(-1.0, min(1.0, max(block_maxs[b0:b1])))
        rms = min(1.0, max(block_rms[b0:b1]))
        painter.setPen(peak_col)
        y0 = mid - int(mx * (mid - 1))
        y1 = mid - int(mn * (mid - 1))
        painter.drawLine(x, min(y0, y1), x, max(y0, y1) if y1 != y0 else min(y0, y1) + 1)
        painter.setPen(body_col)
        rh = max(1, int(rms * (mid - 1)))
        painter.drawLine(x, mid - rh, x, mid + rh)
    painter.end()
    img.setText("qc_wave_version", WAVEFORM_PNG_VERSION)
    tmp_path = out_path + ".tmp.png"
    img.save(tmp_path, "PNG")
    os.replace(tmp_path, out_path)
    return True


if _av is not None:
    USE_PYAV = True
    _pyav_render_waveform = _pyav_render
# ===================== OPTIONAL PyAV waveform backend (END) ======================


def waveform_png_is_current(path):
    """
    Cached PNG exists and carries the current render version; older caches
    regenerate.
    """
    if not os.path.exists(path):
        return False
    img = QtGui.QImage(path)
    if img.isNull():
        return False
    return img.text("qc_wave_version") == WAVEFORM_PNG_VERSION


def waveform_backend_available():
    """
    True if any waveform backend can run: PyAV, or external ffmpeg.
    """
    return USE_PYAV or shutil.which("ffmpeg") is not None


def generate_waveform_png(media_path, out_path, colour, timeout=30):
    """
    Build the waveform image with ffmpeg. Blocking; safe to run in a worker thread
    (no Qt objects are touched). Argument list, no shell, so paths with quotes or shell
    metacharacters are safe. Returns True if the image exists afterwards.
    """

    if not media_path:
        return False
    if waveform_png_is_current(out_path):
        return True
    if USE_PYAV and _pyav_render_waveform is not None:
        try:
            with _generation_lock:
                if _pyav_render_waveform(media_path, out_path, colour):
                    return True
        except Exception as e_:  # fall back to external ffmpeg below
            logger.warning(f"PyAV waveform failed, falling back to ffmpeg: {e_}")
    if shutil.which("ffmpeg") is None:
        return False
    # Write to a temp name and rename at the end: readers checking os.path.exists(out_path)
    # never see a half-written image (atomic on the same filesystem).
    tmp_path = out_path + ".tmp.png"
    cmd = ['ffmpeg', '-y', '-i', media_path, '-filter_complex',
           f'aformat=channel_layouts=mono,showwavespic=s=1020x100:colors={colour}',
           '-frames:v', '1', '-update', '1', tmp_path]
    try:
        with _generation_lock:
            subprocess.run(cmd, timeout=timeout,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(tmp_path):
                # Stamp the render version on the ffmpeg output too
                stamped = QtGui.QImage(tmp_path)
                if not stamped.isNull():
                    stamped.setText("qc_wave_version", WAVEFORM_PNG_VERSION)
                    stamped.save(tmp_path, "PNG")
                os.replace(tmp_path, out_path)
    except Exception as e_:
        logger.warning(f"Waveform build error: {e_}")
        return False
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
    return os.path.exists(out_path)


def generate_waveform_png_async(media_path, out_path, colour, timeout=30):
    """
    Run generate_waveform_png in a daemon thread so the UI never blocks.
    Returns the Thread; poll thread.is_alive() (e.g. with a QTimer) or fire-and-forget.
    """

    thread = threading.Thread(target=generate_waveform_png,
                              args=(media_path, out_path, colour, timeout), daemon=True)
    thread.start()
    return thread
