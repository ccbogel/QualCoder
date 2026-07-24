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
https://qualcoder.org/
"""

import atexit
import bisect
import datetime
from copy import copy, deepcopy
import logging
import re
import os
import sqlite3

import weakref
import webbrowser # For: Open original file

import fitz  # PyMuPDF
import qtawesome as qta  # https://pictogrammers.com/library/mdi/

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor

from collections import defaultdict

from .code_in_all_files import DialogCodeInAllFiles
from .code_tree import CodeTreeController
from .color_selector import DialogColorSelect
from .color_selector import TextColor
from .coder_names import DialogCoderNames  # Coder change as in code_text
from .speakers import DialogSpeakers, speaker_coder_name  # Mark speakers
from .helpers import Message, init_persistent_tree_header, \
    DialogGetStartAndEndMarks  # tree width persistence and autocode marks
from .GUI.ui_dialog_code_pdf import Ui_Dialog_code_pdf
from .memo import DialogMemo
from .report_attributes import DialogSelectAttributeParameters
from .select_items import DialogSelectItems
# IA
from .ai_agent_prompts import AiAgentPromptsCatalog  # PromptsList removed; new Markdown-based catalog
from .ai_prompt_library import DialogAiEditPrompts  # Dialog moved from ai_prompts to ai_prompt_library
from .ai_chat import ai_chat_signal_emitter

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

# Word tuple indices: (x0, y0, x1, y1, pos0, pos1, line_id)
W_X0, W_Y0, W_X1, W_Y1, W_POS0, W_POS1, W_LINE = 0, 1, 2, 3, 4, 5, 6

# Vertical separation between pages, in PDF points
PAGE_GAP = 14 

# Memory budget for pixmaps (~256 MB)
CACHE_BUDGET_BYTES = 256 * 1024 * 1024  
ZOOM_MIN, ZOOM_MAX = 0.5, 3.0


def _word_flags():
    """
    Extraction flags: expand ligatures (fi -> f i) so that the text matches.
    """

    try:
        return fitz.TEXTFLAGS_WORDS & ~fitz.TEXT_PRESERVE_LIGATURES
    except AttributeError:
        return None

def _page_words_raw(page):
    """ Reads the raw word tuples of ONE page once, so both text variants
    (lines and joined paragraphs) can be built from a single extraction.
    Returns:
        (raw word tuples, rotation matrix)
    """

    flags = _word_flags()
    if flags is not None:
        raw = page.get_text("words", flags=flags)
    else:
        raw = page.get_text("words")
    return raw, page.rotation_matrix


def _build_page_text(raw, rot, offset, join_lines=False):
    """
    Deterministic text reconstruction from raw word tuples:
        "" before the first word, "\n\n" between blocks,
        "\n" between lines of the same block (or " " when join_lines is True,
        so each block reads as one whole paragraph),
        " " between words on the same line, and ALWAYS "\n" at the end of the page.
    Word rects are transformed with rotation_matrix so that they match
    the page exactly as it is rendered (get_pixmap applies the rotation).
    line_id keeps incrementing on every visual line change regardless of
    join_lines: highlight rectangles are still drawn per visual line.
    Args:
        raw: word tuples from _page_words_raw
        rot: rotation matrix
        offset: Integer, starting character position of this page in the fulltext
        join_lines: Boolean, True joins the lines of a block into one paragraph
    Returns:
        (page_text: str, words: list[tuple], final_offset: int)
    """

    parts = []
    words = []
    pos = offset
    prev_block = None
    prev_line = None
    line_id = -1
    for x0, y0, x1, y1, wtext, bno, lno, _wno in raw:
        wtext = wtext.replace("\x00", "")
        if wtext == "":
            continue
        if prev_block is None:
            sep = ""
        elif bno != prev_block:
            sep = "\n\n"
        elif lno != prev_line:
            sep = " " if join_lines else "\n"
        else:
            sep = " "
        if sep:
            parts.append(sep)
            pos += len(sep)
        if prev_block != bno or prev_line != lno:
            line_id += 1
        parts.append(wtext)
        rect = fitz.Rect(x0, y0, x1, y1) * rot
        rect.normalize()
        words.append((float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1),
                      pos, pos + len(wtext), line_id))
        pos += len(wtext)
        prev_block, prev_line = bno, lno
    parts.append("\n")  # Page limit, always present even if the page is empty
    pos += 1
    return "".join(parts), words, pos


def _extract_page(page, offset, join_lines=False):
    """ Extracts the words from ONE page in natural reading order (PDF content flow
    order, which preserves columns in digital documents). See _build_page_text. """

    raw, rot = _page_words_raw(page)
    return _build_page_text(raw, rot, offset, join_lines)


def extract_pdf_highlights(filepath):
    """
    Detects highlight annotations in a PDF.
    Returns a list of {'page': page index, 'quads': [fitz.Rect, ...] in ROTATED page
    coordinates (the same space as the extractor's word rects), 'color': '#RRGGBB'}.
    Empty list when the PDF has no highlights or cannot be read.
    """

    out = []
    try:
        doc = fitz.open(filepath)
    except Exception as err:
        logger.warning(f"extract_pdf_highlights: {filepath} {err}")
        return out
    try:
        for i, page in enumerate(doc):
            rot = page.rotation_matrix
            annot = page.first_annot
            while annot is not None:
                try:
                    if annot.type[0] == fitz.PDF_ANNOT_HIGHLIGHT:
                        stroke = (annot.colors or {}).get('stroke')
                        if stroke and len(stroke) >= 3:
                            color = "#{:02X}{:02X}{:02X}".format(
                                int(round(stroke[0] * 255)), int(round(stroke[1] * 255)),
                                int(round(stroke[2] * 255)))
                        else:
                            color = "#F7FE2E"  # PDF default highlight yellow
                        quads = []
                        vertices = annot.vertices
                        if vertices:
                            for k in range(0, len(vertices) - 3, 4):
                                pts = vertices[k:k + 4]
                                rect = fitz.Rect(min(p[0] for p in pts), min(p[1] for p in pts),
                                                 max(p[0] for p in pts), max(p[1] for p in pts)) * rot
                                rect.normalize()
                                quads.append(rect)
                        else:
                            rect = fitz.Rect(annot.rect) * rot
                            rect.normalize()
                            quads.append(rect)
                        if quads:
                            content = (annot.info or {}).get('content', '') or ''
                            out.append({'page': i, 'quads': quads, 'color': color,
                                        'memo': content.strip()})
                except Exception as err:
                    logger.debug(f"extract_pdf_highlights annot: {err}")
                annot = annot.next
    finally:
        doc.close()
    return out


def extract_pdf_annotations(filepath):
    """
    Non-highlight annotations WITH text content (sticky notes, free text, comments
    on underline/strikeout, etc.), for appending to the file memo on import.
    Highlight comments are NOT included here: they go to the memo of their coded
    segment when highlight coding is accepted.
    Returns a list of {'page': 1-based page number, 'type': annot type name,
    'content': text} in document order.
    """

    out = []
    try:
        doc = fitz.open(filepath)
    except Exception as err:
        logger.warning(f"extract_pdf_annotations: {filepath} {err}")
        return out
    try:
        for i, page in enumerate(doc):
            annot = page.first_annot
            while annot is not None:
                try:
                    if annot.type[0] != fitz.PDF_ANNOT_HIGHLIGHT:
                        content = ((annot.info or {}).get('content', '') or '').strip()
                        if content:
                            out.append({'page': i + 1,
                                        'type': annot.type[1] if len(annot.type) > 1 else '',
                                        'content': content})
                except Exception as err:
                    logger.debug(f"extract_pdf_annotations annot: {err}")
                annot = annot.next
    finally:
        doc.close()
    return out


def pdf_highlights_to_positions(filepath, highlights, progress_callback=None):
    """
    Maps highlight quads to character positions of the stored fulltext, using the
    SAME word map as the paragraph extractor (join_lines=True), so pos0/pos1 land
    exactly on the imported text.
    Args:
        filepath: PDF path
        highlights: output of extract_pdf_highlights
        progress_callback: callable(step, total) or None; called per page while
            building the word map and per highlight while matching.
    Returns:
        List of {'pos0': int, 'pos1': int, 'color': '#RRGGBB'}, ordered by pos0.
    """

    if not highlights:
        return []
    try:
        doc = fitz.open(filepath)
    except Exception as err:
        logger.warning(f"pdf_highlights_to_positions: {filepath} {err}")
        return []
    page_words = []
    try:
        total_steps = len(doc) + len(highlights)
        step = 0
        offset = 0
        for page in doc:
            raw, rot = _page_words_raw(page)
            _text, words, offset = _build_page_text(raw, rot, offset, join_lines=True)
            page_words.append(words)
            step += 1
            if progress_callback is not None:
                progress_callback(step, total_steps)
    finally:
        doc.close()
    results = []
    for hl in highlights:
        step += 1
        if progress_callback is not None:
            progress_callback(step, total_steps)
        words = page_words[hl['page']] if hl['page'] < len(page_words) else []
        pos0 = None
        pos1 = None
        for w in words:
            w_rect = fitz.Rect(w[0], w[1], w[2], w[3])
            w_area = max(1e-6, w_rect.get_area())
            for quad in hl['quads']:
                inter = fitz.Rect(w_rect)
                inter.intersect(quad)
                if inter.is_empty:
                    continue
                # The word counts as highlighted when at least half of it is covered.
                if inter.get_area() / w_area >= 0.5:
                    pos0 = w[4] if pos0 is None else min(pos0, w[4])
                    pos1 = w[5] if pos1 is None else max(pos1, w[5])
                    break
        if pos0 is not None and pos1 is not None and pos1 > pos0:
            results.append({'pos0': int(pos0), 'pos1': int(pos1), 'color': hl['color'],
                            'memo': hl.get('memo', '')})
    results.sort(key=lambda r: r['pos0'])
    return results


def extract_pdf_fulltext(filepath, progress_callback=None, join_lines=False):
    """
    Extracts ONLY the fulltext of a PDF, for importing in manage_files.
    It MUST produce exactly the same text that the viewer reconstructs, otherwise
    the coding positions cannot be mapped to the page.
    Args:
        filepath: PDF path
        progress_callback: callable(current_page: int, total: int) or None
        join_lines: Boolean, True joins the lines of each block into one paragraph
    Returns:
        String fulltext
    """

    doc = fitz.open(filepath)
    try:
        if doc.needs_pass:
            raise ValueError(_("PDF is password protected"))
        total = len(doc)
        parts = []
        offset = 0
        for i, page in enumerate(doc):
            page_text, _words, offset = _extract_page(page, offset, join_lines)
            parts.append(page_text)
            if progress_callback is not None:
                progress_callback(i + 1, total)
        return "".join(parts)
    finally:
        doc.close()


# Global registry of live PDF worker threads. An abandoned QThread keeps the
# Python process alive after the last window closes (the console never returns),
# so the workers register themselves here and are force-stopped on ANY exit path:
# aboutToQuit covers every way the Qt application quits (even when the coding tab
# never receives its closeEvent), and atexit is the final belt at interpreter
# shutdown. Safe: the workers only READ the PDF file, never the project database.
_ACTIVE_PDF_WORKERS = weakref.WeakSet()
_QUIT_HOOK_INSTALLED = False


def stop_all_pdf_workers():
    """ Stops (and, as a last resort, terminates) every live PDF worker thread. """

    for worker in list(_ACTIVE_PDF_WORKERS):
        try:
            if worker.isRunning():
                worker.stop()
                if not worker.wait(1500):
                    logger.warning("PDF worker did not stop on quit; terminating")
                    worker.terminate()
                    worker.wait(1000)
        except RuntimeError:
            pass  # C++ object already deleted


def _register_pdf_worker(worker):
    """ Adds the worker to the registry and installs the quit hooks once. """

    global _QUIT_HOOK_INSTALLED
    _ACTIVE_PDF_WORKERS.add(worker)
    if not _QUIT_HOOK_INSTALLED:
        app_ = QtCore.QCoreApplication.instance()
        if app_ is not None:
            app_.aboutToQuit.connect(stop_all_pdf_workers)
            atexit.register(stop_all_pdf_workers)
            _QUIT_HOOK_INSTALLED = True


class PdfTextWorker(QtCore.QThread):
    """
    Extracts the text and word map of all pages in the background.
    Opens its OWN fitz document (a Document should not be shared
    between threads). Emits progress and the complete result when finished.
    """

    progress = QtCore.pyqtSignal(int, int)  # Current_page, total.
    finished_ok = QtCore.pyqtSignal(dict)  # {'fulltext':..., 'pages':[...]}
    failed = QtCore.pyqtSignal(str)

    def __init__(self, filepath, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self._stop = False
        _register_pdf_worker(self)

    def stop(self):
        self._stop = True

    def run(self):
        doc = None
        try:
            doc = fitz.open(self.filepath)
            total = len(doc)
            # Both text variants are built from a SINGLE raw read per page:
            # 'lines' (one "\n" per visual line, the historical layout) and
            # 'joined' (block lines joined into whole paragraphs). The dialog
            # verifies which one matches the imported fulltext, so files
            # imported either way keep working side by side.
            pages = []
            parts = []
            pages_j = []
            parts_j = []
            offset = 0
            offset_j = 0
            for i, page in enumerate(doc):
                if self._stop:
                    return
                raw, rot = _page_words_raw(page)
                rect = page.rect
                page_text, words, new_offset = _build_page_text(raw, rot, offset, join_lines=False)
                pages.append({'width': float(rect.width), 'height': float(rect.height),
                              'char_start': offset, 'char_end': new_offset,
                              'words': words,
                              '_pos1': [w[W_POS1] for w in words]})
                parts.append(page_text)
                offset = new_offset
                page_text_j, words_j, new_offset_j = _build_page_text(raw, rot, offset_j, join_lines=True)
                pages_j.append({'width': float(rect.width), 'height': float(rect.height),
                                'char_start': offset_j, 'char_end': new_offset_j,
                                'words': words_j,
                                '_pos1': [w[W_POS1] for w in words_j]})
                parts_j.append(page_text_j)
                offset_j = new_offset_j
                if i % 5 == 0 or i == total - 1:
                    self.progress.emit(i + 1, total)
            if not self._stop:
                self.finished_ok.emit({'fulltext': "".join(parts), 'pages': pages,
                                       'fulltext_joined': "".join(parts_j), 'pages_joined': pages_j})
        except Exception as err:
            logger.warning(f"PdfTextWorker: {err}")
            if not self._stop:
                self.failed.emit(str(err))
        finally:
            if doc is not None:
                doc.close()


class PdfRenderWorker(QtCore.QThread):
    """
    Renders pages to image in the background with a REPLACEABLE queue:
    each view request replaces the pending ones, so that when scrolling
    quickly, only what remains visible is rendered. Thread's own fitz
    document.
    """

    image_ready = QtCore.pyqtSignal(int, float, float, QtGui.QImage)  # Page, zoom, dpr, image.

    def __init__(self, filepath, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self._queue = []
        self._mutex = QtCore.QMutex()
        self._cond = QtCore.QWaitCondition()
        self._stop = False
        _register_pdf_worker(self)

    def set_requests(self, requests):
        """
        Replaces the pending queue with the new list of (page, zoom, dpr).
        """

        self._mutex.lock()
        self._queue = list(requests)
        self._cond.wakeAll()
        self._mutex.unlock()

    def stop(self):
        self._mutex.lock()
        self._stop = True
        self._queue = []
        self._cond.wakeAll()
        self._mutex.unlock()

    def run(self):
        doc = None
        try:
            doc = fitz.open(self.filepath)
        except Exception as err:
            logger.warning(f"PdfRenderWorker open: {err}")
            return
        try:
            while True:
                self._mutex.lock()
                while not self._queue and not self._stop:
                    self._cond.wait(self._mutex)
                if self._stop:
                    self._mutex.unlock()
                    break
                page_idx, zoom, dpr = self._queue.pop(0)
                self._mutex.unlock()
                try:
                    page = doc.load_page(page_idx)
                    scale = zoom * dpr
                    # Safety limit to avoid creating giant images: 5000 px per side
                    # is sharp beyond ZOOM_MAX on any screen; the previous 12000 px
                    # produced 400-780 MB pixmaps on large-format pages (plans,
                    # posters, scanned maps), several of which were kept by the
                    # visible-pages cache and could also outlive the 3 s stop wait.
                    max_side = max(page.rect.width, page.rect.height) * scale
                    if max_side > 5000:
                        scale = 5000 / max(page.rect.width, page.rect.height)
                    mat = fitz.Matrix(scale, scale)
                    # annots=False: PDF annotations (highlights, notes) are NOT painted
                    # in the coding view, so the page shows only QualCoder's own layers.
                    pix = page.get_pixmap(matrix=mat, alpha=False, annots=False)
                    img = QtGui.QImage(pix.samples, pix.width, pix.height, pix.stride,
                                       QtGui.QImage.Format.Format_RGB888).copy()
                    if not self._stop:
                        self.image_ready.emit(page_idx, zoom, dpr, img)
                except Exception as err:
                    logger.debug(f"PdfRenderWorker page {page_idx}: {err}")
        finally:
            doc.close()


class PdfPageItem(QtWidgets.QGraphicsItem):
    """
    Lightweight item per page. Draws the cached pixmap (scaled to the page rect in PDF points,
    sharp when the render zoom matches the view zoom) and, on top of it, the coding layers:
        - text_marks: translucent rects with the code color
        - area_marks: rects with border and soft fill
        - search_rects / current_search: search highlight
        - sel_rects: text selection in progress
        - drag_rect: area rectangle in progress (drag)
    """

    def __init__(self, view, idx, width, height):
        super().__init__()
        self.view = view
        self.idx = idx
        self.w = width
        self.h = height
        self.text_marks = []   # [(QRectF, QColor, coding_dict)]
        self.area_marks = []   # [(QRectF, QColor base, coding_dict)]
        self.annot_marks = []  # [(QRectF, annotation_dict)] anotaciones. Annotations
        self.sel_rects = []
        self.search_rects = []
        self.current_search = []
        self.drag_rect = None

    def boundingRect(self):
        return QtCore.QRectF(0, 0, self.w, self.h)

    def paint(self, painter, option, widget=None):
        rect = self.boundingRect()
        painter.fillRect(rect, QColor(255, 255, 255))
        entry = self.view.pixmap_cache.get(self.idx)
        if entry is not None:
            pm = entry['pixmap']
            painter.drawPixmap(rect, pm, QtCore.QRectF(pm.rect()))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QtGui.QPen(QColor(170, 170, 175), 0))
        painter.drawRect(rect)
        # Text codings: style shared with code_text ('marker' = translucent fill, 'underline' = dashed underline)
        if getattr(self.view.dialog, 'highlight_style', 'marker') == 'underline':
            for mark_rect, _color, info in self.text_marks:
                pen = QtGui.QPen(QColor(info['color']), 1.2, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                painter.setPen(pen)
                y_under = mark_rect.bottom() - 0.8
                painter.drawLine(QtCore.QPointF(mark_rect.left(), y_under),
                                 QtCore.QPointF(mark_rect.right(), y_under))
            painter.setPen(Qt.PenStyle.NoPen)
        else:
            # Marker: on overlaps colors do NOT blend; only the code most recently applied to
            # the segment (latest date; ctid only breaks same-second ties) shows over the text.
            # Painted newest-to-oldest, filling each area once (clipping out what was already
            # painted with a region), so the text stays legible even with many codes stacked.
            # Every code's identity is still given by the margin bars.
            if self.text_marks:
                painter.save()
                painter.setPen(Qt.PenStyle.NoPen)
                painted_region = QtGui.QRegion()
                for mark_rect, _color, info in sorted(
                        self.text_marks,
                        key=lambda m: (m[2].get('date', ''), m[2].get('ctid', 0)),
                        reverse=True):
                    aligned = mark_rect.toAlignedRect()
                    remaining = QtGui.QRegion(aligned).subtracted(painted_region)
                    if remaining.isEmpty():
                        continue
                    painter.setClipRegion(remaining)
                    fill = QColor(info['color'])
                    fill.setAlpha(110)
                    painter.fillRect(mark_rect, fill)
                    painted_region = painted_region.united(aligned)
                painter.restore()
        # Annotations: wavy underline in its own color (purple), distinct from codings and
        # from the search highlight. Always drawn, whatever the highlight style; hovering
        # shows the memo in a tooltip.
        if self.annot_marks:
            pen = QtGui.QPen(QColor(126, 87, 194), 1.1)
            pen.setCosmetic(True)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(pen)
            for mark_rect, _note in self.annot_marks:
                y_base = mark_rect.bottom() - 0.2
                path = QtGui.QPainterPath()
                x = mark_rect.left()
                right = mark_rect.right()
                path.moveTo(x, y_base)
                up = True
                while x < right:
                    nx = min(x + 2.0, right)  # Half period ~2 pt
                    path.lineTo(nx, y_base - 1.0 if up else y_base + 1.0)  # amplitud 1 pt. Amplitude 1 pt
                    up = not up
                    x = nx
                painter.drawPath(path)
            painter.setPen(Qt.PenStyle.NoPen)
        for s_rect in self.search_rects:
            painter.fillRect(s_rect, QColor(255, 213, 79, 110))
        for s_rect in self.current_search:
            painter.fillRect(s_rect, QColor(255, 152, 0, 130))
            painter.setPen(QtGui.QPen(QColor(230, 110, 0), 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(s_rect)
            painter.setPen(Qt.PenStyle.NoPen)
        # Text selection in progress
        for sel_rect in self.sel_rects:
            painter.fillRect(sel_rect, QColor(0, 120, 215, 80))
        # Coded areas (border + soft fill)
        captions = getattr(self.view.dialog, 'show_code_captions', 0)
        for area_rect, base_color, info in self.area_marks:
            pen = QtGui.QPen(base_color, 1.2, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            fill = QColor(base_color)
            fill.setAlpha(45)
            painter.setBrush(fill)
            painter.drawRect(area_rect)
            # Optional caption over the area: name (1) or name + memo (2).
            if captions >= 1:
                label = info.get('name', '')
                if captions == 2 and info.get('memo'):
                    label += ": " + info['memo']
                if label:
                    painter.save()
                    cap_font = painter.font()
                    cap_font.setPointSizeF(8.0)
                    painter.setFont(cap_font)
                    fm = painter.fontMetrics()
                    bg = QtCore.QRectF(area_rect.left(), area_rect.top(),
                                       fm.horizontalAdvance(label) + 4, fm.height() + 2)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(255, 255, 255, 230))
                    painter.drawRect(bg)
                    painter.setPen(QColor(20, 20, 20))
                    painter.drawText(QtCore.QPointF(bg.left() + 2, bg.top() + fm.ascent() + 1), label)
                    painter.restore()
        # Area rectangle in progress (drag)
        if self.drag_rect is not None:
            pen = QtGui.QPen(QColor(0, 120, 215), 1.6, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            fill = QColor(0, 120, 215)
            fill.setAlpha(30)
            painter.setBrush(fill)
            painter.drawRect(self.drag_rect)
        # Interactive resize of an area (parity with view_image): live red dashed rectangle + 4 corner handles
        dlg = self.view.dialog
        area_rs = getattr(dlg, 'area_to_resize', None)
        if area_rs is not None and area_rs.get('pdf_page') == self.idx:
            live = QtCore.QRectF(float(area_rs['x1']), float(area_rs['y1']),
                                 float(area_rs['width']), float(area_rs['height']))
            pen = QtGui.QPen(QColor('#ff0000'), 1.6, Qt.PenStyle.DashLine)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(live)
            painter.setPen(QtGui.QPen(QColor('#aa0000'), 0))
            painter.setBrush(QColor('#ff0000'))
            for h_rect in dlg._area_handle_rects(area_rs).values():
                painter.drawRect(h_rect)


class PdfView(QtWidgets.QGraphicsView):
    """
    Document view. The scene is in PDF points; the zoom is the view transformation,
    so items are NOT re-created when zooming. Rendering of visible pages is scheduled with
    a short timer (debounce) and delegated to the PdfRenderWorker.
    LRU cache of pixmaps with a byte budget.
    """

    def __init__(self, dialog):
        super().__init__()
        self.dialog = dialog
        self.scene_ = QtWidgets.QGraphicsScene(self)
        self.setScene(self.scene_)
        self.items_ = []
        self.page_tops = []
        self.page_sizes = []
        self.max_page_width = 595.0
        self.zoom = 1.0
        self.mode = "text"  # "text" o "area"
        self.single_page_mode = False  # True: one page shown at a time; False: whole document
        self.current_single_page = 0
        self.pixmap_cache = {}  # Page -> {'zoom','dpr','pixmap','bytes'}
        self._cache_order = []  # LRU order of page keys
        self.setRenderHints(QtGui.QPainter.RenderHint.Antialiasing |
                            QtGui.QPainter.RenderHint.SmoothPixmapTransform |
                            QtGui.QPainter.RenderHint.TextAntialiasing)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        # Initial cursor for the default mode (text): the text-selection I-beam.
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
        if self.dialog.app.settings.get('stylesheet', '') in ('dark', 'rainbow'):
            self.setBackgroundBrush(QColor(45, 45, 48))
        else:
            self.setBackgroundBrush(QColor(208, 209, 212))
        self.render_timer = QtCore.QTimer(self)
        self.render_timer.setSingleShot(True)
        self.render_timer.setInterval(30)
        self.render_timer.timeout.connect(self._render_visible)
        self._press_anchor = None      # Character anchor (int) where the drag starts
        self._press_word = None        # Word (pos0, pos1) under the click, for the single-click fallback
        self._text_moved = False       # True if there was a real drag (not a single click)
        self._text_dragging = False
        self._area_page = None
        self._area_origin = None
        self._dragging_area = False
        self._area_resize = None  # {'handle': esquina, 'orig': (x, y, w, h)}. {'handle': corner, 'orig': (x, y, w, h)}

    # Document and scene
    def clear_document(self):
        self._area_resize = None
        self.current_single_page = 0
        self.items_ = []
        self.page_tops = []
        self.page_sizes = []
        self.pixmap_cache = {}
        self._cache_order = []
        self.scene_.clear()
        self.resetTransform()
        self.zoom = 1.0

    def set_document(self, sizes):
        """
        Creates one item per page, stacked vertically and centered.
        Args:
            sizes: list of (width, height) in PDF points.
        """

        self.clear_document()
        self.page_sizes = list(sizes)
        if not sizes:
            return
        self.max_page_width = max(w for w, _h in sizes)
        y = float(PAGE_GAP)
        for i, (w, h) in enumerate(sizes):
            item = PdfPageItem(self, i, w, h)
            item.setPos(PAGE_GAP + (self.max_page_width - w) / 2.0, y)
            self.scene_.addItem(item)
            self.items_.append(item)
            self.page_tops.append(y)
            y += h + PAGE_GAP
        self.scene_.setSceneRect(0, 0, self.max_page_width + 2 * PAGE_GAP, y)
        self._full_scene_height = y
        if self.single_page_mode:
            self._apply_single_page(0)

    def page_at(self, scene_pos):
        """
        Returns (page_index, local_point) for a scene position,
        or None if it is outside of any page.
        """

        if not self.items_:
            return None
        idx = bisect.bisect_right(self.page_tops, scene_pos.y()) - 1
        if idx < 0:
            idx = 0
        if idx >= len(self.items_):
            idx = len(self.items_) - 1
        item = self.items_[idx]
        local = scene_pos - item.pos()
        if -2 <= local.x() <= item.w + 2 and -PAGE_GAP <= local.y() <= item.h + PAGE_GAP:
            return idx, QtCore.QPointF(local.x(), local.y())
        return None

    def center_page_index(self):
        """
        Page under the center of the viewport, for the page indicator.
        """

        if not self.items_:
            return 0
        if self.single_page_mode:
            return self.current_single_page
        center = self.mapToScene(self.viewport().rect().center())
        idx = bisect.bisect_right(self.page_tops, center.y()) - 1
        return max(0, min(idx, len(self.items_) - 1))

    # Zoom and navigation.
    def set_zoom(self, zoom):
        zoom = max(ZOOM_MIN, min(ZOOM_MAX, zoom))
        if abs(zoom - self.zoom) < 0.0005:
            return
        self.zoom = zoom
        self.setTransform(QtGui.QTransform().scale(zoom, zoom))
        self.dialog.update_zoom_label(zoom)
        self._schedule_render()

    def fit_width(self):
        if not self.page_sizes:
            return
        avail = max(50, self.viewport().width() - 18)
        self.set_zoom(avail / (self.max_page_width + 2 * PAGE_GAP))

    def set_view_mode(self, single_page):
        """
        Switches between whole-document view (all pages stacked, the default) and
        single-page view (one page at a time, navigated with the page controls).
        Keeps the page the user was reading.
        """

        single_page = bool(single_page)
        if single_page == self.single_page_mode:
            return
        current = self.current_single_page if self.single_page_mode else self.center_page_index()
        self.single_page_mode = single_page
        if not self.items_:
            return
        if single_page:
            self._apply_single_page(current)
        else:
            for it in self.items_:
                it.setVisible(True)
            self.scene_.setSceneRect(0, 0, self.max_page_width + 2 * PAGE_GAP,
                                     getattr(self, '_full_scene_height', 0) or
                                     (self.page_tops[-1] + self.page_sizes[-1][1] + PAGE_GAP))
            self.verticalScrollBar().setValue(int(self.page_tops[current] * self.zoom) - 4)
        self._schedule_render()

    def _apply_single_page(self, idx):
        """ Shows only the page idx: the scene rect is restricted to that page, the
        other page items are hidden (their geometry is kept, so all the character
        and area coordinates remain valid). """

        if not self.items_:
            return
        idx = max(0, min(idx, len(self.items_) - 1))
        self.current_single_page = idx
        for i, it in enumerate(self.items_):
            it.setVisible(i == idx)
        self.scene_.setSceneRect(0, self.page_tops[idx] - PAGE_GAP,
                                 self.max_page_width + 2 * PAGE_GAP,
                                 self.page_sizes[idx][1] + 2 * PAGE_GAP)
        self.verticalScrollBar().setValue(int((self.page_tops[idx] - PAGE_GAP) * self.zoom))
        self.dialog.update_page_indicator(idx)

    def goto_page(self, idx):
        if not self.items_:
            return
        idx = max(0, min(idx, len(self.items_) - 1))
        if self.single_page_mode:
            self._apply_single_page(idx)
        else:
            self.verticalScrollBar().setValue(int(self.page_tops[idx] * self.zoom) - 4)
        self._schedule_render()

    def scroll_to_scene_rect(self, scene_rect):
        if self.single_page_mode and self.items_:
            target = bisect.bisect_right(self.page_tops, scene_rect.center().y()) - 1
            target = max(0, min(target, len(self.items_) - 1))
            if target != self.current_single_page:
                self._apply_single_page(target)
        self.ensureVisible(scene_rect, 60, 120)
        self._schedule_render()

    # On-demand rendering.
    def _schedule_render(self):
        margin = getattr(self.dialog, 'coding_margin', None)
        if margin is not None:
            margin.update()
        if getattr(self.dialog, 'active_handles', None):
            self.dialog.reposition_resize_handles()
        self.render_timer.start(30)

    def _visible_range(self):
        if self.single_page_mode and self.items_:
            return self.current_single_page, self.current_single_page
        rect = self.mapToScene(self.viewport().rect()).boundingRect()
        first = bisect.bisect_right(self.page_tops, rect.top()) - 1
        last = bisect.bisect_right(self.page_tops, rect.bottom()) - 1
        first = max(0, min(first, len(self.items_) - 1))
        last = max(0, min(last, len(self.items_) - 1))
        return first, last

    def _render_visible(self):
        if not self.items_:
            return
        first, last = self._visible_range()
        self.dialog.update_page_indicator(self.center_page_index())
        dpr = float(self.devicePixelRatioF())
        needed = []
        lo = max(0, first - 1)
        hi = min(len(self.items_) - 1, last + 1)
        for p in range(lo, hi + 1):
            entry = self.pixmap_cache.get(p)
            if (entry is None or abs(entry['zoom'] - self.zoom) > 0.01
                    or abs(entry['dpr'] - dpr) > 0.01):
                needed.append((p, self.zoom, dpr))
            else:
                self._touch(p)
        if needed and self.dialog.render_worker is not None:
            self.dialog.render_worker.set_requests(needed)
        self._evict(lo, hi)

    def _touch(self, key):
        try:
            self._cache_order.remove(key)
        except ValueError:
            pass
        self._cache_order.append(key)

    def store_pixmap(self, page_idx, zoom, dpr, image):
        """
        Receives the rendered image (render thread) and saves it in the cache.
        It is only kept if the zoom is still relevant.
        """

        if page_idx >= len(self.items_):
            return
        pm = QtGui.QPixmap.fromImage(image)
        self.pixmap_cache[page_idx] = {'zoom': zoom, 'dpr': dpr, 'pixmap': pm,
                                       'bytes': pm.width() * pm.height() * 4}
        self._touch(page_idx)
        self.items_[page_idx].update()
        first, last = self._visible_range()
        self._evict(max(0, first - 1), min(len(self.items_) - 1, last + 1))

    def _evict(self, keep_lo, keep_hi):
        total = sum(e['bytes'] for e in self.pixmap_cache.values())
        if total <= CACHE_BUDGET_BYTES:
            return
        keep = set(range(keep_lo, keep_hi + 1))
        for key in list(self._cache_order):
            if total <= CACHE_BUDGET_BYTES:
                break
            if key in keep:
                continue
            entry = self.pixmap_cache.pop(key, None)
            if entry is not None:
                total -= entry['bytes']
                if key < len(self.items_):
                    self.items_[key].update()
            try:
                self._cache_order.remove(key)
            except ValueError:
                pass

    # View events.
    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self._schedule_render()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_render()

    def showEvent(self, event):
        super().showEvent(event)
        self._schedule_render()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
            self.set_zoom(self.zoom * factor)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            hit = self.page_at(scene_pos)
            area_rs = getattr(self.dialog, 'area_to_resize', None)
            if area_rs is not None:
                if hit is not None and hit[0] == area_rs.get('pdf_page'):
                    local = hit[1]
                    grabbed = False
                    for h_type, h_rect in self.dialog._area_handle_rects(area_rs).items():
                        pad = 2.0 / max(self.zoom, 0.05)
                        if h_rect.adjusted(-pad, -pad, pad, pad).contains(local):
                            self._area_resize = {
                                'handle': h_type,
                                'orig': (float(area_rs['x1']), float(area_rs['y1']),
                                         float(area_rs['width']), float(area_rs['height']))}
                            grabbed = True
                            break
                    if grabbed:
                        event.accept()
                        return
                    inside = (area_rs['x1'] <= local.x() <= area_rs['x1'] + area_rs['width']
                              and area_rs['y1'] <= local.y() <= area_rs['y1'] + area_rs['height'])
                    if inside:
                        # Dragging the body of the rectangle moves the entire area.
                        self._area_resize = {
                            'handle': 'MOVE',
                            'orig': (float(area_rs['x1']), float(area_rs['y1']),
                                     float(area_rs['width']), float(area_rs['height'])),
                            'grab': (local.x() - float(area_rs['x1']),
                                     local.y() - float(area_rs['y1']))}
                        self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
                        event.accept()
                        return
                    self.dialog.cancel_interactive_area_resize()
                else:
                    self.dialog.cancel_interactive_area_resize()
            # Like code_text: a click on the viewer hides the resize teardrops (the teardrops capture their own clicks and do not pass through here)
            if self.dialog.active_handles:
                self.dialog.hide_resize_handles()
            if self.mode == "area":
                if hit is not None:
                    idx, local = hit
                    w, h = self.page_sizes[idx]
                    if 0 <= local.x() <= w and 0 <= local.y() <= h:
                        self._area_page = idx
                        self._area_origin = local
                        self._dragging_area = True
                        self.items_[idx].drag_rect = QtCore.QRectF(local, local)
                        self.items_[idx].update()
                event.accept()
                return
            # Text mode
            self._text_dragging = True
            self._text_moved = False
            caret = None
            word = None
            if hit is not None and self.dialog.text_ready():
                caret = self.dialog.char_at(hit[0], hit[1])
                word = self.dialog.word_at(hit[0], hit[1])
            # The word under the click is remembered for the single-click fallback
            # (click without drag = select the word, as before).
            self._press_word = (word[W_POS0], word[W_POS1]) if word is not None else None
            if caret is not None:
                self._press_anchor = caret
                self.dialog.set_selection(caret, caret)  # empty caret; drag extends it
            else:
                self._press_anchor = None
                self.dialog.clear_selection()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        scene_pos = self.mapToScene(event.position().toPoint())
        hit = self.page_at(scene_pos)
        area_rs = getattr(self.dialog, 'area_to_resize', None)
        if self._area_resize is not None and area_rs is not None:
            page_idx = area_rs.get('pdf_page')
            if page_idx is not None and page_idx < len(self.items_):
                item = self.items_[page_idx]
                local = scene_pos - item.pos()
                lx = min(max(local.x(), 0.0), item.w)
                ly = min(max(local.y(), 0.0), item.h)
                ox, oy, ow, oh = self._area_resize['orig']
                right, bottom = ox + ow, oy + oh
                min_size = 5.0
                h_type = self._area_resize['handle']
                if h_type == 'MOVE':  # Dragging the body: move without changing size
                    gx, gy = self._area_resize['grab']
                    nx = min(max(lx - gx, 0.0), max(0.0, item.w - ow))
                    ny = min(max(ly - gy, 0.0), max(0.0, item.h - oh))
                    area_rs['x1'], area_rs['y1'] = nx, ny
                    area_rs['width'], area_rs['height'] = ow, oh
                elif h_type == 'TL':  # Superior izquierda: mueve X izquierda e Y superior. Top left: moves left X and top Y
                    nx = min(lx, right - min_size)
                    ny = min(ly, bottom - min_size)
                    area_rs['x1'], area_rs['y1'] = nx, ny
                    area_rs['width'], area_rs['height'] = right - nx, bottom - ny
                elif h_type == 'TR':  # Superior derecha: mueve X derecha e Y superior. Top right: moves right X and top Y
                    nr = max(lx, ox + min_size)
                    ny = min(ly, bottom - min_size)
                    area_rs['x1'], area_rs['y1'] = ox, ny
                    area_rs['width'], area_rs['height'] = nr - ox, bottom - ny
                elif h_type == 'BL':  # Inferior izquierda: mueve X izquierda e Y inferior. Bottom left: moves left X and bottom Y
                    nx = min(lx, right - min_size)
                    nb = max(ly, oy + min_size)
                    area_rs['x1'], area_rs['y1'] = nx, oy
                    area_rs['width'], area_rs['height'] = right - nx, nb - oy
                else:  # BR, inferior derecha: mueve X derecha e Y inferior. BR, bottom right: moves right X and bottom Y
                    nr = max(lx, ox + min_size)
                    nb = max(ly, oy + min_size)
                    area_rs['x1'], area_rs['y1'] = ox, oy
                    area_rs['width'], area_rs['height'] = nr - ox, nb - oy
                item.update()
            event.accept()
            return
        if self._dragging_area and self._area_page is not None:
            idx = self._area_page
            item = self.items_[idx]
            local = scene_pos - item.pos()
            lx = min(max(local.x(), 0.0), item.w)
            ly = min(max(local.y(), 0.0), item.h)
            item.drag_rect = QtCore.QRectF(self._area_origin, QtCore.QPointF(lx, ly)).normalized()
            item.update()
            event.accept()
            return
        if (self._text_dragging and (event.buttons() & Qt.MouseButton.LeftButton)
                and self._press_anchor is not None and self.dialog.text_ready()):
            if hit is not None:
                caret = self.dialog.char_at(hit[0], hit[1])
                if caret is not None:
                    a = self._press_anchor
                    if caret != a:
                        self._text_moved = True
                    self.dialog.set_selection(min(a, caret), max(a, caret))
            event.accept()
            return
        if not event.buttons():
            if hit is not None:
                self.dialog.maybe_tooltip(hit[0], hit[1], event.globalPosition().toPoint())
            else:
                QtWidgets.QToolTip.hideText()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._area_resize is not None:
                self._area_resize = None
                self.viewport().setCursor(Qt.CursorShape.CrossCursor if self.mode == "area"
                                          else Qt.CursorShape.IBeamCursor)  # Cross in area, I-beam in text.
                self.dialog.commit_area_resize()
                event.accept()
                return
            if self._dragging_area and self._area_page is not None:
                idx = self._area_page
                item = self.items_[idx]
                rect = item.drag_rect
                item.drag_rect = None
                item.update()
                self._dragging_area = False
                self._area_page = None
                self._area_origin = None
                if rect is not None and rect.width() > 4 and rect.height() > 4:
                    self.dialog.area_ready(idx, rect)
                event.accept()
                return
            # End of text drag
            if self._text_dragging:
                if not self._text_moved:
                    # Single click without drag: select the whole word (same quick
                    # behavior as before). With a drag, instead, the selection is
                    # exact-character.
                    if self._press_word is not None:
                        self.dialog.set_selection(self._press_word[0], self._press_word[1])
                    else:
                        self.dialog.clear_selection()
                self._text_dragging = False
                self._text_moved = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.mode == "text":
            scene_pos = self.mapToScene(event.position().toPoint())
            hit = self.page_at(scene_pos)
            if hit is not None and self.dialog.text_ready():
                word = self.dialog.word_at(hit[0], hit[1])
                if word is not None:
                    # Double click: select the whole word. The anchor stays at its
                    # start in case the user drags afterwards (character extension).
                    self._text_dragging = True
                    self._text_moved = False
                    self._press_anchor = word[W_POS0]
                    self._press_word = (word[W_POS0], word[W_POS1])
                    self.dialog.set_selection(word[W_POS0], word[W_POS1])
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        self.dialog.view_menu(event.pos(), event.globalPos())
        event.accept()

    def keyPressEvent(self, event):
        if self.dialog.handle_key(event):
            event.accept()
            return
        super().keyPressEvent(event)


class PdfResizeHandle(QtWidgets.QWidget):
    """
    Visual drag handle for resizing TEXT codings over the PDF viewer.
    Mirror of the CodeResizeHandle from helpers:
    the start one points top-right and the end one points top-left.
    Dragging snaps to the exact character.
    """

    def __init__(self, view, is_start, code_item, main_dialog):
        super().__init__(view.viewport())
        self.view = view
        self.is_start = is_start
        self.code_item = code_item
        self.main_dialog = main_dialog
        # Original positions in case we need to revert
        self.orig_pos0 = code_item['pos0']
        self.orig_pos1 = code_item['pos1']
        self.setCursor(QtCore.Qt.CursorShape.SizeHorCursor)
        self.setFixedSize(20, 26)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._color = self.code_item.get('color', '#0078d7')
        self.dragging = False
        self.show()
        self.raise_()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        w = self.width()
        radius = w / 2.0
        path = QtGui.QPainterPath()
        if self.is_start:
            path.moveTo(w, 0)
            path.lineTo(w, radius)
            path.arcTo(0, 0, w, w, 0, -270)
        else:
            path.moveTo(0, 0)
            path.lineTo(0, radius)
            path.arcTo(0, 0, w, w, 180, 270)
        path.closeSubpath()
        painter.setPen(QtGui.QPen(QtGui.QColor("#333333"), 1))
        painter.setBrush(QtGui.QBrush(QtGui.QColor(self._color)))
        painter.drawPath(path)

    def _char_at_global(self, global_pos):
        """
        Character position under the global cursor position, with CHARACTER
        precision, or None. Allows resizing a coding boundary to an exact
        character, consistent with drag selection.
        """

        vp = self.view.viewport().mapFromGlobal(global_pos)
        scene_pos = self.view.mapToScene(vp)
        hit = self.view.page_at(scene_pos)
        if hit is None:
            return None
        return self.main_dialog.char_at(hit[0], hit[1])

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.dragging = True

    def mouseMoveEvent(self, event):
        if not self.dragging:
            return
        new_pos = self._char_at_global(event.globalPosition().toPoint())
        if new_pos is None:
            return
        # In-memory update for live visual feedback.
        if self.is_start:
            if new_pos < self.code_item['pos1']:
                self.code_item['pos0'] = new_pos
        else:
            if new_pos > self.code_item['pos0']:
                self.code_item['pos1'] = new_pos
        self.main_dialog.rebuild_marks()
        self.main_dialog.reposition_resize_handles()

    def mouseReleaseEvent(self, event):
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return
        self.dragging = False
        new_pos = self._char_at_global(event.globalPosition().toPoint())
        if new_pos is None:
            # Released outside of a word: confirm the current live position.
            new_pos = self.code_item['pos0'] if self.is_start else self.code_item['pos1']
        self.main_dialog.update_code_position_from_handle(
            self.code_item, new_pos, self.is_start, self.orig_pos0, self.orig_pos1)


DEFAULT_PDF_CODING_MARGIN_WIDTH = 120
MINIMUM_PDF_CODING_MARGIN_WIDTH = 30


class PdfCodingMargin(QtWidgets.QWidget):
    """
    Code stripe margin next to the PDF viewer, mirror of the CodingMargin from code_text:
    track-packing of lanes for overlaps, code name on the edge, tooltip, click to select the segment,
    and context menu forwarded to the dialog. The vertical geometry is obtained by projecting the word
    rects of each page onto the viewer's viewport.
    The 'side' parameter controls the visual layout:
    -'left': lanes stack from right to left (lane 0 next to the viewer) and names go on the left edge.
    -'right': lanes stack from left to right and names go on the right edge.
    """

    BAR_W = 3
    LANE_STEP = 10

    def __init__(self, view, dialog, side='left'):
        super().__init__()
        self.view = view
        self.dialog = dialog
        self.side = side  # 'left' o 'right'
        self._hovered_tooltip_code_key = None
        self.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._emit_context_menu_to_dialog)
        self.setMouseTracking(True)
        self.setMinimumWidth(MINIMUM_PDF_CODING_MARGIN_WIDTH)

    def _emit_context_menu_to_dialog(self, position):
        if hasattr(self.dialog, 'coding_margin_context_menu'):
            self.dialog.coding_margin_context_menu(position, self)

    # Contrast helpers, mirror of CodingMargin in code_text: hue-preserving label
    # colors that stay readable on light and dark backgrounds (WCAG ratio).
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
        background_luminance = cls._relative_luminance(background_color)
        return light_candidate if background_luminance < 0.5 else dark_candidate

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
        """Return a stable identifier for one hovered coding (text or area)."""

        if code is None:
            return None
        ctid = code.get('ctid')
        if ctid is not None:
            return ('ctid', ctid)
        imid = code.get('imid')
        if imid is not None:
            return ('imid', imid)
        return ('range', code.get('fid'), code.get('pos0'), code.get('pos1'), code.get('cid'))

    def wheelEvent(self, event):
        """
        Mouse wheel over the margin = scroll the document, same as over the PDF view.
        The event is rebuilt with the position remapped onto the view viewport and
        forwarded: preserves native speed, trackpad pixel deltas, and Ctrl+wheel still
        zooms (AnchorUnderMouse with the remapped position).
        """

        target = self.view.viewport()
        pos = QtCore.QPointF(target.mapFromGlobal(event.globalPosition().toPoint()))
        forwarded = QtGui.QWheelEvent(pos, event.globalPosition(), event.pixelDelta(),
                                      event.angleDelta(), event.buttons(), event.modifiers(),
                                      event.phase(), event.inverted())  # Qt6: no source().
        QtWidgets.QApplication.sendEvent(target, forwarded)
        event.accept()

    def _text_segments_and_span(self, code):
        """
        Returns (segments, span, left_x) of a TEXT coding: segments (top_v,
        height_v, is_start) in viewport, vertical span (scene_top, scene_bot) in
        SCENE coordinates (or None if no rects), and the scene left_x of the top
        segment (to tie-break lanes by column). Scene coordinates are independent
        of scroll and zoom, so lane packing stays stable while scrolling.
        """

        segments = []
        scene_top = None
        scene_bot = None
        left_x = None
        if not (self.dialog.pages and self.dialog.extracted_ok and self.view.items_):
            return segments, None, 0.0
        pages = self.dialog._pages_spanning(code['pos0'], code['pos1'])
        for k, page_idx in enumerate(pages):
            if page_idx >= len(self.view.items_):
                continue
            rects = self.dialog.rects_for_range(page_idx, code['pos0'], code['pos1'])
            if not rects:
                continue
            y0 = min(r.top() for r in rects)
            y1 = max(r.bottom() for r in rects)
            x0 = min(r.left() for r in rects)
            item = self.view.items_[page_idx]
            scene_pt_top = item.mapToScene(QtCore.QPointF(x0, y0))
            scene_pt_bot = item.mapToScene(QtCore.QPointF(0.0, y1))
            # Viewport (to paint)
            top_v = self.view.mapFromScene(scene_pt_top).y()
            bot_v = self.view.mapFromScene(scene_pt_bot).y()
            segments.append((top_v, max(2, bot_v - top_v), k == 0))
            # Scene (for lane packing)
            s_top, s_bot = scene_pt_top.y(), scene_pt_bot.y()
            if scene_top is None:
                left_x = scene_pt_top.x()  # x of the first (top) segment
            scene_top = s_top if scene_top is None else min(scene_top, s_top)
            scene_bot = s_bot if scene_bot is None else max(scene_bot, s_bot)
        span = None if scene_top is None else (scene_top, scene_bot)
        return segments, span, (left_x if left_x is not None else 0.0)

    def _area_segments_and_span(self, area):
        """
        Returns (segments, span, left_x) of a coded image AREA. The area lives on a
        single page and vertically spans from y1 to y1+height (page points). A
        single segment, with is_start=True so its name is drawn in the margin like
        text codings. left_x is the scene x of the area's left edge (to tie-break
        lanes by column).
        """

        if not self.view.items_:
            return [], None, 0.0
        page_idx = area.get('pdf_page')
        if page_idx is None or page_idx >= len(self.view.items_):
            return [], None, 0.0
        x0 = float(area.get('x1', 0) or 0)
        y0 = float(area.get('y1', 0) or 0)
        y1 = y0 + float(area.get('height', 0) or 0)
        item = self.view.items_[page_idx]
        scene_pt_top = item.mapToScene(QtCore.QPointF(x0, y0))
        scene_pt_bot = item.mapToScene(QtCore.QPointF(x0, y1))
        top_v = self.view.mapFromScene(scene_pt_top).y()
        bot_v = self.view.mapFromScene(scene_pt_bot).y()
        segments = [(top_v, max(2, bot_v - top_v), True)]
        return segments, (scene_pt_top.y(), scene_pt_bot.y()), scene_pt_top.x()

    def _compute_layout(self):
        """
        Lane packing by real VERTICAL OVERLAP (not by character range), for TEXT
        and AREA codings together, in a single pass. Packing by vertical overlap
        is what makes the margin correct in MULTI-COLUMN documents (two codings in
        different columns may not overlap in characters but do overlap on screen)
        and also lets text and area bars mix without overlapping each other.
        Returns an ordered list of bars: [(code, lane, segments)], where `code` is
        the coding dict (text or area).
        """

        if not self.dialog.file_:
            return []
        current_fid = self.dialog.file_['id']
        important_only = getattr(self.dialog, 'important', False)
        # (top_escena, bot_escena, x_izq_escena, code, segmentos)
        raw = []
        # Text codings
        for code in self.dialog.code_text:
            if code.get('fid') != current_fid or code.get('ctid') is None:
                continue
            if important_only and code.get('important') != 1:
                continue
            segments, span, left_x = self._text_segments_and_span(code)
            if span is not None:
                raw.append((span[0], span[1], left_x, code, segments))
        # Area codings (code_image with pdf_page)
        for area in self.dialog.code_areas:
            if area.get('id') != current_fid:
                continue
            if important_only and area.get('important') != 1:
                continue
            segments, span, left_x = self._area_segments_and_span(area)
            if span is not None:
                raw.append((span[0], span[1], left_x, area, segments))
        # Order by scene top; tie-break by left x (column) so that at the same height
        # the left column takes lanes before the right one and each column's bars tend
        # to group in their own lane.
        raw.sort(key=lambda e: (e[0], e[2]))
        ordered_items = []
        lane_bottoms = []
        for s_top, s_bot, _lx, code, segments in raw:
            placed = False
            for i, lb in enumerate(lane_bottoms):
                if lb <= s_top:  # No vertical overlap with what is already placed
                    lane_bottoms[i] = s_bot
                    ordered_items.append((code, i, segments))
                    placed = True
                    break
            if not placed:
                lane_bottoms.append(s_bot)
                ordered_items.append((code, len(lane_bottoms) - 1, segments))
        return ordered_items

    def _offset_x(self, col_index):
        if self.side == 'right':
            return 12 + (col_index * self.LANE_STEP)
        return self.width() - 15 - (col_index * self.LANE_STEP)

    def _name_geometry(self, painter_or_fm, col_index, raw_name):
        """
        (elided text, x) of the name depending on the side, formulas from code_text.
        """

        margin_width = self.width()
        fm = painter_or_fm
        if self.side == 'right':
            lanes_end_x = 12 + (col_index + 1) * self.LANE_STEP
            available_w = max(0, margin_width - lanes_end_x - 5)
        else:
            lanes_start_x = margin_width - 15 - (col_index + 1) * self.LANE_STEP
            available_w = max(0, lanes_start_x - 5 - 5)
        name = fm.elidedText(raw_name, QtCore.Qt.TextElideMode.ElideRight, available_w)
        if self.side == 'right':
            x_pos = max(margin_width - fm.horizontalAdvance(name) - 5, 18)
        else:
            x_pos = 5
        return name, x_pos

    def paintEvent(self, event):
        if not self.dialog.file_ or not (self.dialog.code_text or self.dialog.code_areas):
            return
        try:
            painter = QtGui.QPainter(self)
            font = QtGui.QFont(self.dialog.app.settings['font'], 9)
            painter.setFont(font)
            fm = painter.fontMetrics()
            background_color = self.view.viewport().palette().color(
                QtGui.QPalette.ColorRole.Base)
            names_drawn_at = {}
            for code, col_index, segments in self._compute_layout():
                offset_x = self._offset_x(col_index)
                color = QtGui.QColor(code.get('color', '#cccccc'))
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.setBrush(color)
                drew_any = False
                for top_v, height_v, _is_start in segments:
                    if top_v > self.height() or top_v + height_v < 0:
                        continue
                    painter.drawRect(offset_x, int(top_v), self.BAR_W, int(height_v))
                    drew_any = True
                # Name displayed once, next to the start of the segment (like code_text).
                if drew_any and segments:
                    top_v = segments[0][0]
                    if segments[0][2] and -12 <= top_v <= self.height():
                        slot = int(top_v // 12)
                        stack = names_drawn_at.get(slot, 0)
                        y_pos = int(top_v + fm.ascent() + stack * 12)
                        names_drawn_at[slot] = stack + 1
                        name, x_pos = self._name_geometry(fm, col_index, code.get('name', ''))
                        painter.setPen(self._label_color_for_background(color, background_color))
                        painter.drawText(x_pos, y_pos, name)
        except Exception as err:
            logger.debug(f"PdfCodingMargin paintEvent: {err}")

    def _code_at_position(self, pos):
        """
        Coding under the point: stripe or name label. May be a text coding or an
        image area.
        """

        if not self.dialog.file_ or not (self.dialog.code_text or self.dialog.code_areas):
            return None
        font = QtGui.QFont(self.dialog.app.settings['font'], 9)
        fm = QtGui.QFontMetrics(font)
        stripe_hit = None
        label_hit = None
        names_drawn_at = {}
        for code, col_index, segments in self._compute_layout():
            offset_x = self._offset_x(col_index)
            for top_v, height_v, _is_start in segments:
                stripe = QtCore.QRect(offset_x - 1, int(top_v), self.BAR_W + 2, int(height_v))
                if stripe.contains(pos):
                    stripe_hit = code
            if segments and segments[0][2]:
                top_v = segments[0][0]
                if -12 <= top_v <= self.height():
                    slot = int(top_v // 12)
                    stack = names_drawn_at.get(slot, 0)
                    y_pos = int(top_v + fm.ascent() + stack * 12)
                    names_drawn_at[slot] = stack + 1
                    name, x_pos = self._name_geometry(fm, col_index, code.get('name', ''))
                    label = QtCore.QRect(x_pos, y_pos - fm.ascent(),
                                         fm.horizontalAdvance(name), fm.height())
                    if label.contains(pos):
                        label_hit = code
        return stripe_hit if stripe_hit is not None else label_hit

    def mouseMoveEvent(self, event):
        """
        Hovering over a code shows its tooltip. Needs improvement.
        """

        try:
            code = self._code_at_position(event.pos())
        except Exception as err:
            logger.debug(f"PdfCodingMargin hit-test: {err}")
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
        except Exception as err:
            logger.debug(f"PdfCodingMargin tooltip: {err}")
            tooltip_html = code.get('name', '')
        self._set_tooltip_style_for_code(code)
        QtWidgets.QToolTip.showText(event.globalPosition().toPoint(), tooltip_html, self)
        self._hovered_tooltip_code_key = code_key
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        """
        Left-click on the stripe or name: selects that exact segment
        in the viewer and brings it into view.
        """

        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            try:
                code = self._code_at_position(event.pos())
            except Exception as err:
                logger.debug(f"PdfCodingMargin click: {err}")
                code = None
            if code is not None and self.dialog.file_ is not None:
                if 'pos0' in code:
                    # Text coding: bring into view and select the segment.
                    pages = self.dialog._pages_spanning(code['pos0'], code['pos1'])
                    if pages and pages[0] < len(self.view.items_):
                        rects = self.dialog.rects_for_range(pages[0], code['pos0'], code['pos1'])
                        if rects:
                            item = self.view.items_[pages[0]]
                            self.view.scroll_to_scene_rect(item.mapRectToScene(rects[0]))
                    if self.dialog.text_ready():
                        self.dialog.set_selection(code['pos0'], code['pos1'])
                else:
                    # Image area: bring its rectangle into view.
                    page_idx = code.get('pdf_page')
                    if page_idx is not None and page_idx < len(self.view.items_):
                        item = self.view.items_[page_idx]
                        rect = QtCore.QRectF(float(code.get('x1', 0) or 0),
                                             float(code.get('y1', 0) or 0),
                                             float(code.get('width', 0) or 0),
                                             float(code.get('height', 0) or 0))
                        self.view.scroll_to_scene_rect(item.mapRectToScene(rect))
                    self.dialog.clear_selection()
                event.accept()
                return
        super().mousePressEvent(event)

    def leaveEvent(self, event):
        QtWidgets.QToolTip.hideText()
        self._clear_tooltip_style()
        self._hovered_tooltip_code_key = None
        self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
        super().leaveEvent(event)


class DialogCodePdf(QtWidgets.QWidget):
    """
    Text: Word selection on the page -> `code_text` (pos0/pos1 on the imported fulltext).
    Image Area: Rectangle on the page -> `code_image` with `pdf_page` (existing convention,
    compatible with `view_image` and reports).
    Maintains the external contract: `__init__(app, parent_textedit, tab_reports)`,
    `get_files(ids)`, `update_dialog_codes_and_categories(tables)`,
    and `_on_project_data_changed(tables, source)`.
    """

    def __init__(self, app, parent_textedit, tab_reports):
        super().__init__()
        self.app = app
        self.parent_textEdit = parent_textedit
        self.tab_reports = tab_reports
        # Codes and categories
        self.codes = []
        self.categories = []
        self.annotations = self.app.get_annotations()
        self.codes, self.categories = self.app.get_codes_categories()
        self.recent_codes = []
        self.get_recent_codes()
        self.tree_sort_option = "all asc"
        self.default_new_code_color = None
        self.show_code_captions = 0  # 0 hidden, 1 name, 2 name+memo
        self.important = False  # Filter: show only important codings
        # Files and status of the loaded document
        self.files = []
        self.file_ = None
        self.attributes = []  # File filter by attributes.
        self._coding_nav_idx = -1  # Navigation between codings (buttons below the tree).
        self._pending_bookmark_pos = None  # Bookmark position to apply once the file text is ready.
        self._pending_selection = None  # Range to highlight once text is ready; for external references (AI chat, links).
        self.active_handles = []   # Text resize teardrops (like code_text).
        self.area_to_resize = None  # Area en resize interactivo (como view_image). Area during interactive resize (like view_image).
        # View preferences SHARED with code_text (same settings keys): margin stripes, highlight style, and margin side.
        # Whatever is saved in code_text is visible here and vice versa.
        try:
            saved_pref = self.app.settings.get('codetext_show_margin_stripes', 'False')
            if isinstance(saved_pref, bool):
                self.show_margin_stripes = saved_pref
            else:
                self.show_margin_stripes = str(saved_pref).lower() == 'true'
        except (KeyError, AttributeError):
            self.show_margin_stripes = False
        try:
            saved_style = self.app.settings.get('codetext_highlight_style', None)
        except (KeyError, AttributeError):
            saved_style = None
        if saved_style in ('marker', 'underline'):
            self.highlight_style = saved_style
        else:
            self.highlight_style = 'underline' if self.show_margin_stripes else 'marker'
        try:
            saved_side = self.app.settings.get('codetext_margin_side', 'left')
            if saved_side not in ('left', 'right'):
                saved_side = 'left'
            self.margin_side = saved_side
        except (KeyError, AttributeError):
            self.margin_side = 'left'
        self.code_text = []   # Text codings of the current file.
        self.code_areas = []  # Area codings (code_image with pdf_page).
        self.undo_deleted_codes = []
        self.undo_deleted_areas = []
        self.pages = []           # Word map per page (from the worker)
        self._page_starts = []
        self.text = ""            # Extracted full text (== DB when extracted_ok)
        self.extracted_ok = False  # The extracted text matches the imported text
        self._text_variants = None  # {'lines': {...}, 'joined': {...}} from the text worker
        self.active_text_variant = "lines"  # Which reconstruction matches the stored fulltext
        self._mismatch_warned = False
        self.total_pages = 0
        self.selection = None     # (pos0, pos1) o None. (pos0, pos1) or None
        self._sel_pages = set()
        self._marked_pages = set()
        self._search_pages = set()
        # Busqueda. Search
        self.search_indices = []
        self.search_index = -1
        # Workers
        self.render_worker = None
        self.text_worker = None
        # UI
        self.ui = Ui_Dialog_code_pdf()
        self.ui.setupUi(self)
        ts = self.app.settings
        self.setStyleSheet(f'font: {ts["fontsize"]}pt "{ts["font"]}";')
        try:
            tree_font = f'font: {ts["treefontsize"]}pt "{ts["font"]}";'
            self.ui.treeWidget.setStyleSheet(tree_font)
            self.ui.listWidget.setStyleSheet(tree_font)
        except KeyError:
            pass
        # Replace the QGraphicsView from the .ui with the PDF view,
        # inside widget_pdf alongside the margin containers (like in code_text)
        self.view = PdfView(self)
        pdf_layout = self.ui.widget_pdf.layout()
        idx = pdf_layout.indexOf(self.ui.graphicsView)
        pdf_layout.removeWidget(self.ui.graphicsView)
        self.ui.graphicsView.hide()
        self.ui.graphicsView.deleteLater()
        pdf_layout.insertWidget(idx, self.view)
        # Code margin inside the chosen container (just like code_text)
        self.coding_margin = PdfCodingMargin(self.view, self, side=self.margin_side)
        self._coding_margin_layout_left = QtWidgets.QVBoxLayout(self.ui.widget_code_margin_left)
        self._coding_margin_layout_left.setContentsMargins(0, 0, 0, 0)
        self._coding_margin_layout_right = QtWidgets.QVBoxLayout(self.ui.widget_code_margin_right)
        self._coding_margin_layout_right.setContentsMargins(0, 0, 0, 0)
        # Resizable margins and viewer wrapped in an internal splitter
        self._pdf_margins_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self._pdf_margins_splitter.setHandleWidth(4)
        self._pdf_margins_splitter.setChildrenCollapsible(False)
        for _margin_w in (self.ui.widget_code_margin_left,
                          self.ui.widget_code_margin_right):
            _sp = _margin_w.sizePolicy()
            _sp.setHorizontalPolicy(QtWidgets.QSizePolicy.Policy.Preferred)
            _margin_w.setSizePolicy(_sp)
        _insert_index = pdf_layout.indexOf(self.ui.widget_code_margin_left)
        for _w in (self.ui.widget_code_margin_left,
                   self.view,
                   self.ui.widget_code_margin_right):
            pdf_layout.removeWidget(_w)
            self._pdf_margins_splitter.addWidget(_w)
        pdf_layout.insertWidget(_insert_index, self._pdf_margins_splitter)
        self._pdf_margins_splitter.setStretchFactor(
            self._pdf_margins_splitter.indexOf(self.view), 1)
        # Persistent user-resizable margin width (mirror of code_text): the width the
        # user drags is stored in config.ini and restored on the next open.
        self.coding_margin_width = self._get_saved_coding_margin_width()
        self._coding_margin_width_is_restoring = False
        self._coding_margin_restore_attempts = 0
        self._coding_margin_width_ready = False
        self.coding_margin_width_save_timer = QtCore.QTimer(self)
        self.coding_margin_width_save_timer.setSingleShot(True)
        self.coding_margin_width_save_timer.timeout.connect(self.persist_coding_margin_width_setting)
        self._pdf_margins_splitter.splitterMoved.connect(self.on_coding_margin_splitter_moved)
        self._install_coding_margin_in_side(self.margin_side)
        self._sync_coding_margin_background()
        self.coding_margin.setVisible(self.show_margin_stripes)
        self._set_margin_container_visibility(self.show_margin_stripes)
        QtCore.QTimer.singleShot(0, self._apply_coding_margin_width)
        QtCore.QTimer.singleShot(60, self._apply_coding_margin_width)
        # Synchronize margin repainting with the viewer scroll.
        self.view.verticalScrollBar().valueChanged.connect(self.coding_margin.update)
        # Splitter sizes: defaults and then restored from settings (config.ini),
        # like code_text, so the file-list width (leftsplitter) and the left-column
        # width (splitter) persist when re-entering the module and across sessions.
        self.ui.splitter.setSizes([280, 920])
        self.ui.leftsplitter.setSizes([200, 480])
        try:
            s0 = int(self.app.settings['dialogcodepdf_splitter0'])
            s1 = int(self.app.settings['dialogcodepdf_splitter1'])
            if s0 > 5 and s1 > 5:
                self.ui.splitter.setSizes([s0, s1])
        except (KeyError, ValueError, TypeError):
            pass
        try:
            v0 = int(self.app.settings['dialogcodepdf_splitter_v0'])
            v1 = int(self.app.settings['dialogcodepdf_splitter_v1'])
            if v0 > 5 and v1 > 5:
                self.ui.leftsplitter.setSizes([v0, v1])
        except (KeyError, ValueError, TypeError):
            pass
        self.ui.splitter.splitterMoved.connect(self.update_sizes)
        self.ui.leftsplitter.splitterMoved.connect(self.update_sizes)
        
        self.ui.pushButton_help.setIcon(qta.icon('mdi6.help'))
        self.ui.pushButton_previous.setIcon(qta.icon('mdi6.arrow-left', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_next.setIcon(qta.icon('mdi6.arrow-right', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_previous_page.setIcon(qta.icon('mdi6.arrow-left', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_next_page.setIcon(qta.icon('mdi6.arrow-right', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_zoom_out.setIcon(qta.icon('mdi6.magnify-minus-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_zoom_in.setIcon(qta.icon('mdi6.magnify-plus-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_fit_width.setIcon(qta.icon('mdi6.fit-to-page-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_mode_text.setIcon(qta.icon('mdi6.cursor-text', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_mode_area.setIcon(qta.icon('mdi6.vector-square', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_important.setIcon(qta.icon('mdi6.star-outline', options=[{'scale_factor': 1.3}]))
        
        # Buttons below file list and tree
        self.ui.pushButton_latest.setIcon(qta.icon('mdi6.arrow-collapse-right'))
        self.ui.pushButton_next_file.setIcon(qta.icon('mdi6.arrow-right'))
        self.ui.pushButton_document_memo.setIcon(qta.icon('mdi6.text-long'))
        self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_clear_filter_file.setIcon(qta.icon('mdi6.filter-off-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_clear_filter_file.setToolTip(_("Clear file filter"))
        
        self.ui.pushButton_show_codings_prev.setIcon(qta.icon('mdi6.arrow-left'))
        self.ui.pushButton_show_codings_next.setIcon(qta.icon('mdi6.arrow-right'))
        self.ui.pushButton_find_code.setIcon(qta.icon('mdi6.card-search-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_clear_filter_code.setIcon(qta.icon('mdi6.filter-remove-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_clear_filter_code.setToolTip(_("Clear code filter"))

        self.ui.lineEdit_search.setToolTip(_("Search text. 3 or more characters, or press Enter."))
        self.ui.lineEdit_code_filter.setToolTip(_("Show codes containing the text"))
        self.ui.checkBox_search_case.setToolTip(_("Case sensitive search"))
        self.ui.label_code.setToolTip(_("No code selected"))
        
        self.ui.label_coder.setText(_("Coder:"))  # The name moves to lineEdit_coder
        self.ui.lineEdit_coder.setText(ts.get('codername', ''))
        self.ui.pushButton_coder.setToolTip(_("Coder visibility"))
        self.ui.pushButton_coder.clicked.connect(self.edit_coder_names)
        self.ui.label_zoom.setText("100%")
        self.ui.lineEdit_page.setValidator(QtGui.QIntValidator(1, 999999, self))
        # Conexiones: busqueda. Connections: search
        self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
        # Enter: if there are no matches yet, force the search (allows <3 chars); if there are, go to the next one.
        self.ui.lineEdit_search.returnPressed.connect(
            lambda: self.move_to_next_search_text() if self.search_indices else self.search_for_text(force=True))
        self.ui.checkBox_search_case.stateChanged.connect(lambda _s: self.search_for_text(force=True))
        self.ui.pushButton_previous.clicked.connect(self.move_to_previous_search_text)
        self.ui.pushButton_next.clicked.connect(self.move_to_next_search_text)
        # Conexiones: navegacion y zoom. Connections: navigation and zoom
        self.ui.pushButton_previous_page.clicked.connect(self.previous_page)
        self.ui.pushButton_next_page.clicked.connect(self.next_page)
        self.ui.lineEdit_page.editingFinished.connect(self.goto_page_from_edit)
        self.ui.comboBox_page_view.currentIndexChanged.connect(self.change_page_view_mode)
        # Restore the persisted page view mode (0 whole document, 1 single page),
        # same pattern as the coding margin width. Signals blocked: applying the
        # saved mode must not re-persist it.
        try:
            saved_view = int(self.app.settings.get('dialogcodepdf_page_view', 0))
        except (TypeError, ValueError, AttributeError):
            saved_view = 0
        if saved_view == 1:
            self.ui.comboBox_page_view.blockSignals(True)
            self.ui.comboBox_page_view.setCurrentIndex(1)
            self.ui.comboBox_page_view.blockSignals(False)
            self.view.set_view_mode(True)
        self.ui.pushButton_zoom_in.clicked.connect(self.zoom_in)
        self.ui.pushButton_zoom_out.clicked.connect(self.zoom_out)
        self.ui.pushButton_fit_width.clicked.connect(self.view.fit_width)
        # Conexiones: modos e importante. Connections: modes and "important" status
        self.ui.pushButton_mode_text.clicked.connect(lambda: self.set_mode("text"))
        self.ui.pushButton_mode_area.clicked.connect(lambda: self.set_mode("area"))
        self.ui.pushButton_mode_text.setToolTip(_("Code text  (T)"))
        self.ui.pushButton_mode_area.setToolTip(_("Code area / image  (E)"))
        self.ui.pushButton_important.clicked.connect(self.show_important_coded)
        # Captions over areas, default new-code color, and annotation/memo viewers.
        self.ui.pushButton_captions.setIcon(qta.icon('mdi6.closed-caption-outline', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_captions.clicked.connect(self.captions_options)
        self.ui.pushButton_default_new_code_color.setIcon(qta.icon('mdi6.palette', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_default_new_code_color.clicked.connect(self.set_default_new_code_color)
        self.ui.pushButton_show_annotations.setIcon(qta.icon('mdi6.text-search-variant', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_show_annotations.clicked.connect(self.show_annotations)
        self.ui.pushButton_show_memos.setIcon(qta.icon('mdi6.text-search', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_show_memos.clicked.connect(self.show_memos)
        # Mark speakers y autocodificado, paridad con code_text. Mark speakers and autocoding, parity with code_text
        self.autocode_history = []  # Autocoding history for undo
        self.autocode_all_first_last_within = "all"
        self.autocode_frag_all_first_within = "all"
        self.ui.pushButton_mark_speakers.setIcon(qta.icon('mdi6.pin-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_mark_speakers.pressed.connect(self.mark_speakers)
        self.ui.pushButton_auto_code.setIcon(qta.icon('mdi6.mace'))
        self.ui.pushButton_auto_code.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.pushButton_auto_code.customContextMenuRequested.connect(self.button_auto_code_menu)
        self.ui.pushButton_auto_code.clicked.connect(self.auto_code)
        self.ui.pushButton_auto_code_frag_this_file.setIcon(qta.icon('mdi6.magic-staff'))
        self.ui.pushButton_auto_code_frag_this_file.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.pushButton_auto_code_frag_this_file.customContextMenuRequested.connect(self.button_auto_code_frag_menu)
        self.ui.pushButton_auto_code_frag_this_file.pressed.connect(self.auto_code_sentences)
        self.ui.pushButton_auto_code_surround.setIcon(qta.icon('mdi6.spear'))
        self.ui.pushButton_auto_code_surround.pressed.connect(self.button_autocode_surround)
        self.ui.pushButton_auto_code_undo.setIcon(qta.icon('mdi6.undo'))
        self.ui.pushButton_auto_code_undo.pressed.connect(self.undo_autocoding)
        self.ui.pushButton_help.clicked.connect(lambda: self.app.help_wiki("4.3.-Coding-Text-on-PDFs"))

        # Bookmark button: jumps to the saved file and position (key B saves them).
        try:
            self.ui.pushButton_bookmark_go.setIcon(qta.icon('mdi6.bookmark', options=[{'scale_factor': 1.3}]))
            self.ui.pushButton_bookmark_go.setToolTip(_("Go to bookmark (press B to set)"))
            self.ui.pushButton_bookmark_go.clicked.connect(self.go_to_bookmark)
        except AttributeError:
            pass
        
        try:
            self.ui.comboBox_exports.currentIndexChanged.connect(self.export_option_selected)
        except AttributeError:
            pass

        # Connections: files and tree
        self.ui.listWidget.currentRowChanged.connect(self.file_selection_changed)
        self.ui.listWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.listWidget.customContextMenuRequested.connect(self.file_menu)
        # Shared code tree controller: tree loading, common context menu, drag and drop
        # reparenting, F2-F6 shortcuts and category branch deletion live in code_tree.py,
        # so the four coding pages no longer duplicate this logic by hand.
        self.code_tree = CodeTreeController(self.app, self.ui.treeWidget, self)
        self.ui.treeWidget.customContextMenuRequested.connect(self.code_tree.tree_menu)
        self.code_tree.fill_counts_callback = self.fill_code_counts_in_tree
        self.code_tree.coded_files_callback = self.coded_media_dialog
        self.code_tree.on_codes_deleted = self.remove_deleted_codes_from_recent
        self.code_tree.on_code_renamed = self.rename_code_in_recent
        self.code_tree.find_code_callback = self.find_code_in_tree
        self.code_tree.show_codes_like_callback = self.show_codes_like
        self.code_tree.show_codes_of_colour_callback = self.show_codes_of_color
        self.code_tree.codes_changed.connect(self.update_dialog_codes_and_categories)
        self.ui.treeWidget.itemClicked.connect(self.tree_item_clicked)
        self.ui.treeWidget.itemSelectionChanged.connect(self.fill_code_label)
        self.ui.treeWidget.itemCollapsed.connect(self.get_collapsed)
        self.ui.treeWidget.itemExpanded.connect(self.get_collapsed)
        # Enable the tree's internal drag-and-drop. Without this the drop never reaches the
        # eventFilter, codes/sub-codes cannot be nested nor categories moved, and the cycle guards
        # never fire.
        self.ui.treeWidget.setDragEnabled(True)
        self.ui.treeWidget.setAcceptDrops(True)
        self.ui.treeWidget.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.ui.treeWidget.setDefaultDropAction(Qt.DropAction.MoveAction)  # Mover (no copiar) al soltar. Move (not copy) on drop.
        self.ui.treeWidget.setDropIndicatorShown(True)  # Show the drop target indicator.
        self.ui.treeWidget.viewport().installEventFilter(self)  # Drag and drop of codes
        # Tree column-width persistence (config.ini). Replaces the automatic resize.
        # It goes here (not in the state block above) because it needs self.ui to already exist.
        init_persistent_tree_header(self.ui.treeWidget, self.app, 'dialogcodepdf_tree_widths')
        # Connections: buttons below the file list
        self.ui.pushButton_latest.clicked.connect(self.go_to_latest_coded_file)
        self.ui.pushButton_next_file.clicked.connect(self.go_to_next_file)
        self.ui.pushButton_document_memo.clicked.connect(lambda: self.file_memo())
        self.ui.pushButton_file_attributes.clicked.connect(self.get_files_from_attributes)
        self.ui.pushButton_clear_filter_file.clicked.connect(self.clear_file_filter)
        self.ui.pushButton_clear_filter_file.setVisible(False)
        # Connections: buttons below the code tree
        self.ui.pushButton_show_codings_prev.clicked.connect(self.show_previous_coding)
        self.ui.pushButton_show_codings_next.clicked.connect(self.show_next_coding)
        self.ui.pushButton_find_code.clicked.connect(self.find_code_in_tree)
        self.ui.lineEdit_code_filter.textEdited.connect(self.show_codes_like)
        self.ui.pushButton_clear_filter_code.clicked.connect(self.clear_code_filter)
        self.ui.pushButton_clear_filter_code.setVisible(False)
        self.code_tree.fill_tree()
        self.get_files()
        # para show codes like
        self.show_codes_like_filter = ""
        self.show_codes_colour_filter = ""
        if getattr(self.app, "project_events", None) is not None:
            self.app.project_events.project_data_changed.connect(self._on_project_data_changed)

    def update_sizes(self):
        """
        Saves the splitter sizes to settings when the user drags them (parity with
        code_text.update_sizes). On reopening the module, the __init__ block
        restores them, so the file-list width and the left-column width persist.
        """

        sizes = self.ui.splitter.sizes()
        if len(sizes) >= 2:
            self.app.settings['dialogcodepdf_splitter0'] = sizes[0]
            self.app.settings['dialogcodepdf_splitter1'] = sizes[1]
        v_sizes = self.ui.leftsplitter.sizes()
        if len(v_sizes) >= 2:
            self.app.settings['dialogcodepdf_splitter_v0'] = v_sizes[0]
            self.app.settings['dialogcodepdf_splitter_v1'] = v_sizes[1]

    # Files
    def _file_tooltip(self, file_):
        """
        File tooltip in the list: date, cases, characters, and codings.
        """

        cur = self.app.conn.cursor()
        tt = _("Date: ") + f"{file_['date'].split()[0]}\n"
        cur.execute("SELECT group_concat(cases.name) from cases join case_text on "
                    "case_text.caseid=cases.caseid where case_text.fid=?", [file_['id']])
        res_cases = cur.fetchone()
        if res_cases and res_cases[0] is not None:
            tt += _("Case: ") + f"{res_cases[0]}\n"
        tt += _("Characters: ") + str(file_.get('characters', 0))
        cur.execute("select count(cid) from code_text_visible where fid=?", [file_['id']])
        text_codings = cur.fetchone()[0]
        cur.execute("select count(cid) from code_image_visible where id=? and pdf_page is not null",
                    [file_['id']])
        area_codings = cur.fetchone()[0]
        tt += f"\n{_('Codings:')} {text_codings + area_codings}"
        if file_['memo'] != "":
            tt += f"\n{_('Memo:')} {file_['memo']}"
        return tt

    def get_files(self, ids=None, sort: str = "name asc", preserve_current_file: bool = False):
        """        Populates the list of PDF files. Contract used by manage_files.
        Args:
            ids: List of IDs to restrict, or None.
            sort: name asc, name desc, date asc, date desc.
            preserve_current_file: Reload the currently displayed file after rebuilding
                the list when it is still present in the filtered result set. Port of
                upstream 11c7f05.
        """

        if ids is None:
            ids = []
        preserved_file_id = self.file_['id'] if preserve_current_file and self.file_ is not None else None
        self.stop_workers()
        self.ui.listWidget.blockSignals(True)
        self.ui.listWidget.clear()
        self.files = self.app.get_pdf_filenames(ids)
        cur = self.app.conn.cursor()
        for file_ in self.files:
            cur.execute("select length(fulltext), fulltext from source where id=?", [file_['id']])
            res_length = cur.fetchone()
            if res_length is None:
                res_length = [0, ""]
            file_['characters'] = res_length[0] if res_length[0] is not None else 0
            file_['start'] = 0
            file_['end'] = file_['characters']
            file_['fulltext'] = res_length[1] if res_length[1] is not None else ""
            file_['tooltip'] = self._file_tooltip(file_)
        if sort == "name asc":
            self.files = sorted(self.files, key=lambda x: x['name'].lower())
        if sort == "name desc":
            self.files = sorted(self.files, key=lambda x: x['name'].lower(), reverse=True)
        if sort == "date asc":
            self.files = sorted(self.files, key=lambda x: x['date'])
        if sort == "date desc":
            self.files = sorted(self.files, key=lambda x: x['date'], reverse=True)
        # Sort by case: the menu already offered it but it was a silent no-op.
        if sort in ("case asc", "case desc"):
            cur.execute("select case_text.fid, group_concat(cases.name) from cases "
                        "join case_text on case_text.caseid=cases.caseid group by case_text.fid")
            case_map = {r[0]: (r[1] or "") for r in cur.fetchall()}
            self.files = sorted(self.files,
                                key=lambda x: (case_map.get(x['id'], ""), x['name'].lower()),
                                reverse=(sort == "case desc"))
        for file_ in self.files:
            item = QtWidgets.QListWidgetItem(file_['name'])
            item.setToolTip(file_['tooltip'])
            self.ui.listWidget.addItem(item)
        # Restore the current file if still listed
        restored_row = -1
        if preserved_file_id is not None:
            for idx, file_ in enumerate(self.files):
                if file_['id'] == preserved_file_id:
                    restored_row = idx
                    break
        if restored_row >= 0:
            self.ui.listWidget.setCurrentRow(restored_row)  # With signals blocked
        self.ui.listWidget.blockSignals(False)
        if restored_row >= 0:
            self.load_file(self.files[restored_row])
        else:
            self.file_ = None
            self._clear_loaded_state()

    def update_file_tooltip(self):
        if self.file_ is None:
            return
        self.file_['tooltip'] = self._file_tooltip(self.file_)
        items = self.ui.listWidget.findItems(self.file_['name'], Qt.MatchFlag.MatchExactly)
        if len(items) == 1:
            items[0].setToolTip(self.file_['tooltip'])

    def file_selection_changed(self, row):
        if row < 0 or row >= len(self.files):
            return
        self.load_file(self.files[row])

    def file_menu(self, position):
        """        File list context menu: memo.
        """

        item = self.ui.listWidget.itemAt(position)
        if item is None:
            return
            
        file_ = next((f for f in self.files if f['name'] == item.text()), None)
        if file_ is None:
            return

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        
        action_next = None
        action_latest = None
        action_show_files_like = None
        action_show_case_files = None
        action_show_by_attribute = None
        
        action_memo = menu.addAction(_("Open memo"))
        action_view_original_file = None
        # Layout conversion: only for the file currently loaded, once both text
        # variants are available from the worker. Reuses the restructuring engine,
        # which relocates codings, annotations and case assignments in the new text.
        action_to_paragraphs = None
        action_to_lines = None
        if self.file_ is not None and file_['id'] == self.file_['id'] and \
                self._text_variants is not None and self.extracted_ok:
            if self.active_text_variant == "lines":
                action_to_paragraphs = menu.addAction(_("Restructure to whole paragraphs (join lines)"))
            else:
                action_to_lines = menu.addAction(_("Restructure to one line per visual line"))
        
        # Display options (using .get() to avoid errors if mediapath does not exist)
        mediapath = file_.get('mediapath') or ""
        if len(mediapath) > 6 and (mediapath[:6] == '/docs/' or mediapath[:5] == 'docs:'):
            action_view_original_file = menu.addAction(_("View original file"))
            
        # Navigation and filtering options
        if len(self.app.get_pdf_filenames()) > 1:
            if len(self.files) != 1:
                action_next = menu.addAction(_("Next file"))
            action_latest = menu.addAction(_("File with latest coding"))
            action_show_files_like = menu.addAction(_("Show files like"))
            action_show_by_attribute = menu.addAction(_("Show files by attributes"))
            action_show_case_files = menu.addAction(_("Show case files"))
            
        sort_menu = QtWidgets.QMenu(_("Sort"))
        sort_menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        action_sort_name_asc = sort_menu.addAction(_("Sort by name ascending"))
        action_sort_name_desc = sort_menu.addAction(_("Sort by name descending"))
        action_sort_case_asc = sort_menu.addAction(_("Sort by case ascending"))
        action_sort_case_desc = sort_menu.addAction(_("Sort by case descending"))
        action_sort_date_asc = sort_menu.addAction(_("Sort by date ascending"))
        action_sort_date_desc = sort_menu.addAction(_("Sort by date descending"))
        menu.addMenu(sort_menu)
        
        action = menu.exec(self.ui.listWidget.mapToGlobal(position))
        if action is None:
            return

        if action == action_to_paragraphs:
            self.restructure_layout("joined")
            return
        if action == action_to_lines:
            self.restructure_layout("lines")
            return
        if action == action_memo:
            self.file_memo(file_)
        if action == action_view_original_file:
            self.view_original_pdf_file(file_)  # the clicked file, not the loaded one
        if action == action_next:
            self.go_to_next_file()
        if action == action_latest:
            self.go_to_latest_coded_file()
        if action == action_show_files_like:
            self.show_files_like()
        if action == action_show_case_files:
            self.show_case_files()
        if action == action_show_by_attribute:
            self.get_files_from_attributes()
        if action == action_sort_name_asc:
            self.get_files(None, "name asc")
        if action == action_sort_name_desc:
            self.get_files(None, "name desc")
        if action == action_sort_case_asc:
            self.get_files(None, "case asc")
        if action == action_sort_case_desc:
            self.get_files(None, "case desc")
        if action == action_sort_date_asc:
            self.get_files(None, "date asc")
        if action == action_sort_date_desc:
            self.get_files(None, "date desc")

    def view_original_pdf_file(self, file_=None):
        """        View the original PDF of the given file (or the loaded one). It previously always
        used self.file_: with another file under the click the wrong PDF opened, and with
        no file loaded it crashed on None.
        """
        if file_ is None:
            file_ = self.file_
        if file_ is None:
            return
        mediapath = file_.get('mediapath') or ""
        if mediapath[:6] == "/docs/":
            webbrowser.open(self.app.project_path + "/documents/" + mediapath[6:])
            return
        if mediapath[:5] == "docs:":
            webbrowser.open(mediapath[5:])

    def show_case_files(self):
        """        Show files of specified case. Or show all files.
        """
        cases = self.app.get_casenames()
        cases.insert(0, {"name": _("Show all files"), "id": -1})
        ui = DialogSelectItems(self.app, cases, _("Select case"), "single")
        ok = ui.exec()
        if not ok:
            return
        selection = ui.get_selected()
        if not selection:
            return
        if selection['id'] == -1:
            self.get_files()
            self.ui.pushButton_clear_filter_file.setVisible(False)
            self.ui.pushButton_clear_filter_file.setStyleSheet("")
            return
        cur = self.app.conn.cursor()
        cur.execute('select fid from case_text where caseid=?', [selection['id']])
        res = cur.fetchall()
        file_ids = [r[0] for r in res]
        self.get_files(file_ids)
        self.ui.pushButton_clear_filter_file.setVisible(True)
        self.ui.pushButton_clear_filter_file.setStyleSheet("background-color: #1e90ff; color: white;")

    def show_files_like(self):
        """        Show files that contain specified filename text.
        """
        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
        dialog.setWindowTitle(_("Show files like"))
        dialog.setWindowFlags(dialog.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog.setLabelText(_("Show files containing the text. (Blank for all)"))
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        text_ = str(dialog.textValue())
        if text_ == "":
            self.get_files()
            self.ui.pushButton_clear_filter_file.setVisible(False)
            self.ui.pushButton_clear_filter_file.setStyleSheet("")
            return
        cur = self.app.conn.cursor()
        cur.execute("select id from source where name like ? and "
                    "(mediapath is null or mediapath like '/docs/%' or mediapath like 'docs:%')",
                    ['%' + text_ + '%'])
        res = cur.fetchall()
        file_ids = [r[0] for r in res]
        self.get_files(file_ids)
        self.ui.pushButton_clear_filter_file.setVisible(True)
        self.ui.pushButton_clear_filter_file.setStyleSheet("background-color: #1e90ff; color: white;")

    def file_memo(self, file_=None):
        """        View or edit the file memo.
        """

        if file_ is None:
            file_ = self.file_
        if file_ is None:
            return
        ui = DialogMemo(self.app, _("Memo for file: ") + file_['name'], file_['memo'])
        ui.exec()
        memo = ui.memo
        if memo == file_['memo']:
            return
        file_['memo'] = memo
        cur = self.app.conn.cursor()
        cur.execute("update source set memo=? where id=?", (memo, file_['id']))
        self.app.conn.commit()
        self.app.delete_backup = False
        file_['tooltip'] = self._file_tooltip(file_)
        items = self.ui.listWidget.findItems(file_['name'], Qt.MatchFlag.MatchExactly)
        if len(items) == 1:
            items[0].setToolTip(file_['tooltip'])

    def _clear_loaded_state(self):
        """        Clears the entire state of the loaded document.
        """

        self.hide_resize_handles()
        self.area_to_resize = None
        self.view.clear_document()
        self.pages = []
        self._page_starts = []
        self.text = ""
        self.extracted_ok = False
        self._mismatch_warned = False
        self.total_pages = 0
        self.code_text = []
        self.code_areas = []
        self.selection = None
        self._sel_pages = set()
        self._marked_pages = set()
        self._search_pages = set()
        self.search_indices = []
        self.search_index = -1
        self.ui.label_search_totals.setText("0 / 0")
        self.ui.lineEdit_page.setText("")
        self.ui.label_pages.setText("/ 0")
        self.ui.label_status.setText("")

    def _resolve_filepath(self, file_):
        """        mediapath '/docs/x' -> project_path/documents/x; 'docs:x' -> ruta absoluta.

        mediapath '/docs/x' -> project_path/documents/x; 'docs:x' -> absolute path.
        """

        mediapath = file_.get('mediapath') or ""
        if mediapath[:6] == "/docs/":
            return f"{self.app.project_path}/documents/{mediapath[6:]}"
        if mediapath[:5] == "docs:":
            return mediapath[5:]
        return None

    def load_file(self, file_):
        """        Loads a PDF: reads page sizes in the GUI thread (fast, metadata only)
        to show the view instantly and starts the two workers (render and text extraction).
        """

        self.stop_workers()
        self._clear_loaded_state()
        self.file_ = file_
        filepath = self._resolve_filepath(file_)
        if filepath is None or not os.path.exists(filepath):
            Message(self.app, _("Warning"),
                    _("Cannot open file. Bad file link: ") + str(file_.get('mediapath')),
                    "warning").exec()
            self.file_ = None
            return
        try:
            doc = fitz.open(filepath)
        except Exception as err:
            Message(self.app, _("Warning"), _("Cannot open file: ") + f"{filepath}\n{err}",
                    "warning").exec()
            self.file_ = None
            return
        if doc.needs_pass:
            Message(self.app, _("Warning"), _("PDF is password protected"), "warning").exec()
            doc.close()
            self.file_ = None
            return
        sizes = []
        for page in doc:
            rect = page.rect
            sizes.append((float(rect.width), float(rect.height)))
        doc.close()
        self.total_pages = len(sizes)
        self.view.set_document(sizes)
        self.ui.label_pages.setText(f"/ {self.total_pages}")
        self.ui.lineEdit_page.setText("1")
        self.ui.label_status.setText(_("Reading text..."))
        # Render worker (the view requests the visible pages)
        self.render_worker = PdfRenderWorker(filepath, self)
        self.render_worker.image_ready.connect(self.on_image_ready)
        self.render_worker.start()
        # Text extraction worker (words + positions)
        self.text_worker = PdfTextWorker(filepath, self)
        self.text_worker.progress.connect(self.on_text_progress)
        self.text_worker.finished_ok.connect(self.on_text_ready)
        self.text_worker.failed.connect(self.on_text_failed)
        self.text_worker.start()
        
        # Fits the zoom to the page width and places the document at the top.
        def init_view():
            self.view.fit_width()
            self.view.verticalScrollBar().setValue(0)
            self.view.horizontalScrollBar().setValue(0)
            
        # Defer to the next event-loop cycle, when the widget already has its final size
        # (fit_width needs the real viewport width).
        QtCore.QTimer.singleShot(0, init_view)
        self.fill_code_counts_in_tree()

    def stop_workers(self):
        """ Stops the extraction and render threads. If a thread does not finish
        within the grace period (e.g. a very large page mid-render), it is
        terminated as a last resort: an abandoned QThread keeps the Python
        process alive after the application window closes. The workers only READ
        the PDF file (never the project database), so terminating them cannot
        corrupt any data. """

        for worker in (self.text_worker, self.render_worker):
            if worker is not None:
                try:
                    worker.stop()
                    if not worker.wait(3000):
                        logger.warning("PDF worker did not stop in time; terminating")
                        worker.terminate()
                        worker.wait(1000)
                except RuntimeError:
                    pass
        self.text_worker = None
        self.render_worker = None

    def on_image_ready(self, page_idx, zoom, dpr, image):
        # Ignore images from a worker that was already replaced (fast file switching).
        if self.sender() is not self.render_worker:
            return
        try:
            self.view.store_pixmap(page_idx, zoom, dpr, image)
        except RuntimeError:
            pass

    def on_text_progress(self, current, total):
        if self.sender() is not self.text_worker:
            return
        try:
            self.ui.label_status.setText(_("Reading text...") + f" {current}/{total}")
        except RuntimeError:
            pass

    def on_text_failed(self, msg):
        if self.sender() is not self.text_worker:
            return
        try:
            self.ui.label_status.setText("")
            Message(self.app, _("Warning"), _("Could not read PDF text: ") + msg, "warning").exec()
            # AREAS do not depend on the word map: load them so existing codings do not
            # vanish from the viewer or the margin.
            self.get_coded_text_update_eventfilter_tooltips()
        except RuntimeError:
            pass

    def on_text_ready(self, data):
        """        Word map ready. Verifies that the reconstructed text matches the imported fulltext;
        otherwise, TEXT coding is disabled (positions would not be reliable) but AREAS remain available.
        """

        if self.file_ is None:
            return
        # Discard signals from a previous worker: when switching files quickly, the previous PDF's
        # finished_ok may arrive queued AFTER self.file_ changed, comparing old text against the new file.
        if self.sender() is not self.text_worker:
            return
        try:
            db_text = self.file_.get('fulltext') or ""
            # Two reconstruction variants arrive from the worker: 'lines' (historical,
            # one newline per visual line) and 'joined' (block lines joined into whole
            # paragraphs). The one matching the imported fulltext becomes active, so
            # files imported either way coexist in the same project. Both are kept so
            # a file can be restructured from one layout to the other on demand.
            self._text_variants = {
                'lines': {'fulltext': data['fulltext'], 'pages': data['pages']},
                'joined': {'fulltext': data.get('fulltext_joined', data['fulltext']),
                           'pages': data.get('pages_joined', data['pages'])}}
            active = 'lines'
            if db_text == self._text_variants['joined']['fulltext'] and \
                    db_text != self._text_variants['lines']['fulltext']:
                active = 'joined'
            self.active_text_variant = active
            self.pages = self._text_variants[active]['pages']
            self._page_starts = [p['char_start'] for p in self.pages]
            self.text = self._text_variants[active]['fulltext']
            self.extracted_ok = (db_text == self.text)
            self.ui.label_status.setText("")
            self.fill_code_label()
            if not self.extracted_ok and not self._mismatch_warned:
                self._mismatch_warned = True
                self._offer_restructure()
            self.get_coded_text_update_eventfilter_tooltips()
            self._apply_pending_bookmark()  # If a bookmark jump for this file was requested, pages/positions are now available.
            self._apply_pending_selection()  # External references (AI chat, links): highlight and reveal the requested range.
        except RuntimeError:
            pass

    def text_ready(self):
        """        Text selection requires word map AND database match.
        """

        return bool(self.pages) and self.extracted_ok

    # Codings: loading and drawing
    def get_coded_text_update_eventfilter_tooltips(self):
        """        Reloads code_text and code_image of the current file and redraws layers.
        Name retained for compatibility with the code ported from the tree.
        """

        if self.file_ is None:
            return
        cur = self.app.conn.cursor()
        sql = ("select code_text_visible.ctid, code_text_visible.cid, code_text_visible.fid, "
               "code_text_visible.seltext, code_text_visible.pos0, code_text_visible.pos1, "
               "code_text_visible.owner, ifnull(code_text_visible.memo,''), "
               "code_text_visible.important, code_name.name, code_name.color, "
               "code_text_visible.date "
               "from code_text_visible join code_name on code_name.cid=code_text_visible.cid "
               "where code_text_visible.fid=? order by code_text_visible.pos0")
        cur.execute(sql, [self.file_['id']])
        keys = ('ctid', 'cid', 'fid', 'seltext', 'pos0', 'pos1', 'owner', 'memo',
                'important', 'name', 'color', 'date')
        self.code_text = [dict(zip(keys, row)) for row in cur.fetchall()]
        sql = ("select code_image_visible.imid, code_image_visible.id, code_image_visible.x1, "
               "code_image_visible.y1, code_image_visible.width, code_image_visible.height, "
               "code_image_visible.cid, ifnull(code_image_visible.memo,''), "
               "code_image_visible.date, code_image_visible.owner, code_image_visible.important, "
               "code_image_visible.pdf_page, code_name.name, code_name.color "
               "from code_image_visible join code_name on code_name.cid=code_image_visible.cid "
               "where code_image_visible.id=? and pdf_page is not null and width>0 and height>0")
        cur.execute(sql, [self.file_['id']])
        keys = ('imid', 'id', 'x1', 'y1', 'width', 'height', 'cid', 'memo', 'date',
                'owner', 'important', 'pdf_page', 'name', 'color')
        self.code_areas = [dict(zip(keys, row)) for row in cur.fetchall()]
        if self.area_to_resize is not None:
            self.area_to_resize = next(
                (a for a in self.code_areas if a['imid'] == self.area_to_resize.get('imid')), None)
        # Project annotations (filtered by file when drawing)
        self.annotations = self.app.get_annotations()
        self.rebuild_marks()

    def _pages_spanning(self, pos0, pos1):
        """        Page indices crossed by the character range [pos0, pos1).
        """

        if not self._page_starts:
            return []
        first = bisect.bisect_right(self._page_starts, pos0) - 1
        last = bisect.bisect_right(self._page_starts, max(pos0, pos1 - 1)) - 1
        first = max(0, first)
        last = max(first, min(last, len(self.pages) - 1))
        return list(range(first, last + 1))

    def rects_for_range(self, page_idx, pos0, pos1):
        """        Rects (in page points) covering the character range, merging consecutive
        words on the same line. The BOUNDARY words are clipped at character level
        (interpolation), so the highlight starts and ends at the exact character
        and not at the whole word. Interior words are painted in full.
        """

        page = self.pages[page_idx]
        words = page['words']
        pos1_list = page['_pos1']
        i = bisect.bisect_right(pos1_list, pos0)
        rects = []
        current = None
        current_line = None
        while i < len(words):
            w = words[i]
            if w[W_POS0] >= pos1:
                break
            # Character-level clipping within the word (interpolation).
            # Only affects boundary words; interior words remain whole.
            c0 = pos0 if pos0 > w[W_POS0] else w[W_POS0]
            c1 = pos1 if pos1 < w[W_POS1] else w[W_POS1]
            lx = self._interp_x(w, c0)
            rx = self._interp_x(w, c1)
            if rx < lx:
                lx, rx = rx, lx
            w_rect = QtCore.QRectF(lx, w[W_Y0], rx - lx, w[W_Y1] - w[W_Y0])
            if current is None or w[W_LINE] != current_line:
                if current is not None:
                    rects.append(current)
                current = w_rect
                current_line = w[W_LINE]
            else:
                current = current.united(w_rect)
            i += 1
        if current is not None:
            rects.append(current)
        return rects

    def rebuild_marks(self):
        """        Rebuilds the coding layers on the page items.
        """

        if not self.view.items_:
            return
        affected = set(self._marked_pages)
        for idx in self._marked_pages:
            if idx < len(self.view.items_):
                self.view.items_[idx].text_marks = []
                self.view.items_[idx].area_marks = []
                self.view.items_[idx].annot_marks = []
        self._marked_pages = set()
        # Text layers (require matching word map)
        if self.pages and self.extracted_ok:
            visibles = [c for c in self.code_text
                        if not (self.important and c['important'] != 1)]
            ordenados = sorted(visibles, key=lambda c: (c['pos0'], c['pos1']))
            # tupla. This tuple's color is NOT used when painting: paint reads info['color']
            # and resolves overlaps with newest-wins clipping; kept only for tuple shape.
            for coding in ordenados:
                color = QColor(coding['color'])
                for page_idx in self._pages_spanning(coding['pos0'], coding['pos1']):
                    if page_idx >= len(self.view.items_):
                        continue
                    for rect in self.rects_for_range(page_idx, coding['pos0'], coding['pos1']):
                        self.view.items_[page_idx].text_marks.append((rect, color, coding))
                        self._marked_pages.add(page_idx)
        # Area layers (independent of text)
        for area in self.code_areas:
            if self.important and area['important'] != 1:
                continue
            page_idx = area['pdf_page']
            if page_idx is None or page_idx >= len(self.view.items_):
                continue
            rect = QtCore.QRectF(area['x1'], area['y1'], area['width'], area['height'])
            self.view.items_[page_idx].area_marks.append((rect, QColor(area['color']), area))
            self._marked_pages.add(page_idx)
        # Annotation layer (text range, mapped like text codings). Always shown (not gated by
        # the important filter), in parity with code_text.
        if self.pages and self.extracted_ok and self.annotations and self.file_ is not None:
            fid = self.file_['id']
            for note in self.annotations:
                if note.get('fid') != fid:
                    continue
                p0, p1 = note.get('pos0'), note.get('pos1')
                if p0 is None or p1 is None or p1 <= p0:
                    continue
                for page_idx in self._pages_spanning(p0, p1):
                    if page_idx >= len(self.view.items_):
                        continue
                    for rect in self.rects_for_range(page_idx, p0, p1):
                        self.view.items_[page_idx].annot_marks.append((rect, note))
                        self._marked_pages.add(page_idx)
        for idx in affected | self._marked_pages:
            if idx < len(self.view.items_):
                self.view.items_[idx].update()
        if getattr(self, 'coding_margin', None) is not None:
            self.coding_margin.update()

    # Text and area selection
    def word_at(self, page_idx, point):
        """        Word under the point (local page coordinates), or None.
        """

        if page_idx >= len(self.pages):
            return None
        tol = 1.0
        x, y = point.x(), point.y()
        for w in self.pages[page_idx]['words']:
            if w[W_X0] - tol <= x <= w[W_X1] + tol and w[W_Y0] - tol <= y <= w[W_Y1] + tol:
                return w
        return None

    def _interp_char(self, w, x):
        """        Interpolates the character position (offset in the fulltext) within word w
        from the local x coordinate. Distributes the range [pos0, pos1) uniformly
        across the word rect width. O(1), no extra extraction: does not affect
        opening or scrolling speed.
        """

        pos0, pos1 = w[W_POS0], w[W_POS1]
        n = pos1 - pos0
        if n <= 0:
            return pos0
        width = w[W_X1] - w[W_X0]
        if width <= 0:
            return pos0
        frac = (x - w[W_X0]) / width
        if frac <= 0.0:
            return pos0
        if frac >= 1.0:
            return pos1
        return pos0 + int(round(frac * n))

    def _interp_x(self, w, char_pos):
        """        Inverse of _interp_char: local x coordinate of the left edge of character
        char_pos within word w. Consistent with _interp_char, so that the
        highlight starts and ends exactly where the cursor marks.
        """

        pos0, pos1 = w[W_POS0], w[W_POS1]
        n = pos1 - pos0
        if n <= 0:
            return w[W_X0]
        frac = (char_pos - pos0) / n
        if frac < 0.0:
            frac = 0.0
        elif frac > 1.0:
            frac = 1.0
        return w[W_X0] + frac * (w[W_X1] - w[W_X0])

    def _point_rect_dist2(self, x, y, w):
        """        Squared distance from point (x, y) to word w's rect (0 if the point is
        inside). Used to pick the nearest word in 2D, so a click does not jump
        columns: a click in the right column resolves to a right-column word, even
        if there is text at the same height in the left column.
        """

        if x < w[W_X0]:
            dx = w[W_X0] - x
        elif x > w[W_X1]:
            dx = x - w[W_X1]
        else:
            dx = 0.0
        if y < w[W_Y0]:
            dy = w[W_Y0] - y
        elif y > w[W_Y1]:
            dy = y - w[W_Y1]
        else:
            dy = 0.0
        return dx * dx + dy * dy

    def char_at(self, page_idx, point):
        """        Character position (offset in the fulltext) under the point, with CHARACTER
        precision (not word). The target line is chosen by 2D proximity (not just
        Y), which keeps selection correct in MULTI-COLUMN documents: the left and
        right columns share a vertical band, but each is a block with its own
        line_id, and the nearest word in 2D fixes the correct column. If the point
        falls outside any word, it anchors to the nearest edge of the closest word
        on that same line, so dragging stays continuous. Returns None if the page
        has no words.
        """

        if page_idx >= len(self.pages):
            return None
        words = self.pages[page_idx]['words']
        if not words:
            return None
        x, y = point.x(), point.y()
        tol = 1.0
        # 1) Word that contains the point in 2D: fixes the line (and thus the
        # column) directly and unambiguously.
        target_line = None
        for w in words:
            if w[W_X0] - tol <= x <= w[W_X1] + tol and w[W_Y0] - tol <= y <= w[W_Y1] + tol:
                target_line = w[W_LINE]
                break
        # 2) No word under the point (margins, gutter between columns, gap between
        # lines): the nearest word in 2D fixes the line. The 2D distance respects
        # the horizontal separation between columns.
        if target_line is None:
            nearest = min(words, key=lambda w: self._point_rect_dist2(x, y, w))
            target_line = nearest[W_LINE]
        line_words = [w for w in words if w[W_LINE] == target_line]
        line_words.sort(key=lambda w: w[W_X0])
        # Left of the whole line: start of the first word.
        if x <= line_words[0][W_X0]:
            return line_words[0][W_POS0]
        # Right of the whole line: end of the last word.
        if x >= line_words[-1][W_X1]:
            return line_words[-1][W_POS1]
        # Inside or between words.
        for i, w in enumerate(line_words):
            if x <= w[W_X1]:
                if x >= w[W_X0]:
                    return self._interp_char(w, x)  # Inside the word
                # In the gap before this word: to the nearest edge.
                prev = line_words[i - 1]
                gap_mid = (prev[W_X1] + w[W_X0]) * 0.5
                return prev[W_POS1] if x < gap_mid else w[W_POS0]
        return line_words[-1][W_POS1]

    def set_selection(self, pos0, pos1):
        self.selection = (pos0, pos1)
        self._apply_selection_rects()

    def clear_selection(self):
        if self.selection is None:
            return
        self.selection = None
        self._apply_selection_rects()

    def _apply_selection_rects(self):
        previous = set(self._sel_pages)
        for idx in previous:
            if idx < len(self.view.items_):
                self.view.items_[idx].sel_rects = []
        self._sel_pages = set()
        if self.selection is not None and self.pages:
            pos0, pos1 = self.selection
            for page_idx in self._pages_spanning(pos0, pos1):
                if page_idx >= len(self.view.items_):
                    continue
                rects = self.rects_for_range(page_idx, pos0, pos1)
                if rects:
                    self.view.items_[page_idx].sel_rects = rects
                    self._sel_pages.add(page_idx)
        for idx in previous | self._sel_pages:
            if idx < len(self.view.items_):
                self.view.items_[idx].update()

    def area_ready(self, page_idx, rect):
        """        Codes the drawn area with the code selected in the tree, like in view_image: the code is
        chosen BEFORE drawing. If no code is selected (or a category is), it warns and does not code.
        """

        if self.file_ is None:
            return
        cid = self._current_tree_cid()
        if cid is None:
            Message(self.app, _("Coded area"), _("Select a code in the list first."),
                    "warning").exec()
            return
        self.mark_area(cid, page_idx, QtCore.QRectF(rect))

    def _current_tree_cid(self):
        item = self.ui.treeWidget.currentItem()
        if item is None:
            return None
        if item.text(1).split(':')[0] != 'cid':
            return None
        return int(item.text(1).split(':')[1])

    # Tooltips
    def _codings_at(self, page_idx, point):
        """        Text and area codings under a point on the page.
        """

        texts_here = []
        areas_here = []
        word = self.word_at(page_idx, point) if self.pages else None
        if word is not None:
            char_pos = word[W_POS0]
            for coding in self.code_text:
                if coding['pos0'] <= char_pos < coding['pos1']:
                    texts_here.append(coding)
        for area in self.code_areas:
            if area['pdf_page'] != page_idx:
                continue
            if (area['x1'] <= point.x() <= area['x1'] + area['width']
                    and area['y1'] <= point.y() <= area['y1'] + area['height']):
                areas_here.append(area)
        return texts_here, areas_here

    def _annotations_at(self, page_idx, point):
        """        Annotations under a point on the page, by the character range of the word
        under the cursor.
        """

        notes_here = []
        if not self.annotations or self.file_ is None:
            return notes_here
        word = self.word_at(page_idx, point) if self.pages else None
        if word is None:
            return notes_here
        char_pos = word[W_POS0]
        fid = self.file_['id']
        for note in self.annotations:
            if note.get('fid') != fid:
                continue
            p0, p1 = note.get('pos0'), note.get('pos1')
            if p0 is None or p1 is None:
                continue
            if p0 <= char_pos < p1:
                notes_here.append(note)
        return notes_here

    def maybe_tooltip(self, page_idx, point, global_pos):
        texts_here, areas_here = self._codings_at(page_idx, point)
        notes_here = self._annotations_at(page_idx, point)
        if not texts_here and not areas_here and not notes_here:
            QtWidgets.QToolTip.hideText()
            return
        lines = []
        for coding in texts_here:
            line = f"{coding['name']}  [{coding['owner']}]"
            if coding['important'] == 1:
                line += " *"
            if coding['memo'] != "":
                line += "\n  " + _("Memo:") + " " + coding['memo'][:120]
            lines.append(line)
        for area in areas_here:
            line = _("Area:") + f" {area['name']}  [{area['owner']}]"
            if area['important'] == 1:
                line += " *"
            if area['memo'] != "":
                line += "\n  " + _("Memo:") + " " + area['memo'][:120]
            lines.append(line)
        for note in notes_here:
            memo = (note.get('memo', '') or '').strip()
            if memo:
                lines.append(_("Annotation:") + " " + memo[:150])
            else:
                lines.append(_("Annotation"))
        QtWidgets.QToolTip.showText(global_pos, "\n".join(lines), self.view)

    # Marcado. Mark
    def mark(self):
        """        Marks the text selection with the selected code from the tree. Shortcut: Q.
        (Areas are coded when drawn, see area_ready.)
        """

        if self.file_ is None:
            Message(self.app, _('Warning'), _("No file was selected"), "warning").exec()
            return
        cid = self._current_tree_cid()
        if cid is None:
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec()
            return
        if self.selection is None:
            return
        if not self.extracted_ok:
            Message(self.app, _('Warning'),
                    _("Text coding is disabled for this file. Re-import the PDF."),
                    "warning").exec()
            return
        pos0, pos1 = self.selection
        if pos0 == pos1:
            return
        seltext = self.text[pos0:pos1]
        coded = {'cid': cid, 'fid': int(self.file_['id']), 'seltext': seltext,
                 'pos0': pos0, 'pos1': pos1, 'owner': self.app.settings['codername'],
                 'memo': "",
                 'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                 'important': None}
        cur = self.app.conn.cursor()
        # Avoid exact duplicate
        cur.execute("select ctid from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?",
                    (coded['cid'], coded['fid'], coded['pos0'], coded['pos1'], coded['owner']))
        if cur.fetchall():
            return
        cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,memo,date,important) "
                    "values(?,?,?,?,?,?,?,?,?)",
                    (coded['cid'], coded['fid'], coded['seltext'], coded['pos0'], coded['pos1'],
                     coded['owner'], coded['memo'], coded['date'], coded['important']))
        self.app.conn.commit()
        if getattr(self.app, "project_events", None) is not None:
            self.app.project_events.emit_table_changes(['code_text'], source=self)
        self.app.delete_backup = False
        self._update_recent_codes(cid)
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        self.update_file_tooltip()
        # Selection is preserved: useful for applying multiple codes to the same text

    def mark_area(self, cid, page_idx, rect):
        """ Inserts the drawn area into code_image with pdf_page (compatible
        with view_image, view_graph and existing reports).
        param: cid int; page_idx int (0-based); rect QtCore.QRectF in page points
        """

        if self.file_ is None:
            return
        item = {'id': int(self.file_['id']),
                'x1': int(round(rect.x())), 'y1': int(round(rect.y())),
                'width': max(1, int(round(rect.width()))),
                'height': max(1, int(round(rect.height()))),
                'cid': cid, 'memo': "",
                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                'owner': self.app.settings['codername'], 'important': None,
                'pdf_page': int(page_idx)}
        cur = self.app.conn.cursor()
        cur.execute("insert into code_image (id,x1,y1,width,height,cid,memo,date,owner,"
                    "important,pdf_page) values(?,?,?,?,?,?,?,?,?,?,?)",
                    (item['id'], item['x1'], item['y1'], item['width'], item['height'],
                     item['cid'], item['memo'], item['date'], item['owner'],
                     item['important'], item['pdf_page']))
        self.app.conn.commit()
        if getattr(self.app, "project_events", None) is not None:
            self.app.project_events.emit_table_changes(['code_image'], source=self)
        self.app.delete_backup = False
        self._update_recent_codes(cid)
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        self.update_file_tooltip()
        self.fill_code_label()

    def remove_deleted_codes_from_recent(self, cids):
        """ Drop deleted codes from the recent codes list. Called from the
        shared code tree controller after code or branch deletion.
        Args:
            cids: List of Integer code ids
        """
        self.recent_codes = [c for c in self.recent_codes if c['cid'] not in cids]

    def rename_code_in_recent(self, old_name, new_name):
        """ Rename a code inside the recent codes list. Called from the
        shared code tree controller after a code rename.
        Args:
            old_name: String
            new_name: String
        """
        for item in self.recent_codes:
            if item['name'] == old_name:
                item['name'] = new_name
                break

    def _update_recent_codes(self, cid):
        """        Moves the code to the front of the recents and persists them in project.
        """

        tmp_code = None
        for code_ in self.codes:
            if code_['cid'] == cid:
                tmp_code = code_
        if tmp_code is None:
            return
        for item in self.recent_codes:
            if item['cid'] == cid:
                self.recent_codes.remove(item)
                break
        self.recent_codes.insert(0, tmp_code)
        if len(self.recent_codes) > 10:
            self.recent_codes = self.recent_codes[:10]
        recent_codes_string = " ".join(str(r['cid']) for r in self.recent_codes)
        cur = self.app.conn.cursor()
        cur.execute("update project set recently_used_codes=?", [recent_codes_string])
        self.app.conn.commit()

    def annotate(self, pos0=None, pos1=None):  # cursor_pos was never used
        """        Adds, edits or deletes an annotation over the current text selection. Reuses DialogMemo:
        if the memo is left empty it deletes the annotation, if it changes it updates it, and if
        it did not exist it creates it.
        """
        if self.file_ is None:
            Message(self.app, _('Warning'), _("No file was selected"), "warning").exec()
            return
            
        # Explicit range (e.g. from the margin
        # menu, over the clicked segment) or, if not given, the current selection.
        if pos0 is None or pos1 is None:
            if self.selection is None:
                return
            pos0, pos1 = self.selection
        
        item = None
        for note in self.annotations:
            if note['fid'] == self.file_['id'] and (note['pos0'] <= pos0 and pos1 <= note['pos1']):
                item = note
                break
        
        # Editar o crear (usando DialogMemo como en code_text.py)
        details = f"{item['owner']} {item['date']}" if item else ""
        memo_text = item['memo'] if item else ""
        ui = DialogMemo(self.app, _("Annotation: ") + details, memo_text)
        if not ui.exec():
            return
            
        cur = self.app.conn.cursor()
        now = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        
        if item and ui.memo == "":
            cur.execute("delete from annotation where anid=?", [item['anid']])
        
        elif item and ui.memo != item['memo']:
            cur.execute("update annotation set memo=?, date=? where anid=?", 
                        (ui.memo, now, item['anid']))
            
        elif not item and ui.memo != "":
            cur.execute("insert into annotation (fid, pos0, pos1, memo, owner, date) values(?,?,?,?,?,?)",
                        (self.file_['id'], pos0, pos1, ui.memo, self.app.settings['codername'], now))
        
        self.app.conn.commit()
        self.app.delete_backup = False
        
        # Refrescar estado
        self.annotations = self.app.get_annotations()
        self.get_coded_text_update_eventfilter_tooltips()

    def _edit_annotation(self, note):
        """        Edits or deletes an existing annotation with DialogMemo (empty memo =
        delete, changed memo = update). Used from the context menu when clicking on
        an existing annotation.
        """

        if note is None or self.file_ is None:
            return
        details = f"{note.get('owner', '')} {note.get('date', '')}"
        ui = DialogMemo(self.app, _("Annotation: ") + details, note.get('memo', '') or '')
        if not ui.exec():
            return
        cur = self.app.conn.cursor()
        now = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        if ui.memo == "":
            cur.execute("delete from annotation where anid=?", [note['anid']])
        elif ui.memo != (note.get('memo', '') or ''):
            cur.execute("update annotation set memo=?, date=? where anid=?",
                        (ui.memo, now, note['anid']))
        else:
            return  # No changes
        self.app.conn.commit()
        self.app.delete_backup = False
        self.annotations = self.app.get_annotations()
        self.get_coded_text_update_eventfilter_tooltips()

    def _delete_annotation(self, note):
        """        Deletes an existing annotation without going through the dialog.
        """

        if note is None or 'anid' not in note:
            return
        cur = self.app.conn.cursor()
        cur.execute("delete from annotation where anid=?", [note['anid']])
        self.app.conn.commit()
        self.app.delete_backup = False
        self.annotations = self.app.get_annotations()
        self.get_coded_text_update_eventfilter_tooltips()

    def coded_memo(self, texts_here=None, areas_here=None):
        """        Views or edits the memo of the coding(s) under the selection (text or area) with
        DialogMemo and saves it to code_text or code_image. Shortcut M.
        """
        
        if texts_here is None or areas_here is None:
            texts_here, areas_here = self._get_context_codings()
            
        selected = self._select_codings(texts_here, areas_here, _("Select coding for memo"))
        if not selected: return
        
        cur = self.app.conn.cursor()
        for entry in selected:
            ref = entry['ref']
            # Memo header by type: text -> positions, area -> page and rect.
            if entry['type'] == 'text':
                titulo = (_("Memo for coded segment: ") + ref['name'] +
                          f" [{ref['pos0']}-{ref['pos1']}]")
            else:
                pagina = (ref.get('pdf_page') or 0) + 1
                titulo = (_("Memo for coded area: ") + ref['name'] +
                          f" [{_('Page')} {pagina}: {ref['x1']},{ref['y1']} "
                          f"{ref['width']}x{ref['height']}]")
            ui = DialogMemo(self.app, titulo, ref['memo'])
            if ui.exec():
                if entry['type'] == 'text':
                    cur.execute("update code_text set memo=? where ctid=?", (ui.memo, ref['ctid']))
                else:
                    cur.execute("update code_image set memo=? where imid=?", (ui.memo, ref['imid']))
        self.app.conn.commit()
        self.get_coded_text_update_eventfilter_tooltips()

    def _update_recent_codes_menu(self):
        """        Shows a popup menu with the recently used codes and marks the selection with the chosen
        code. Shortcut R.
        """
        if not self.recent_codes:
            return
        menu = QtWidgets.QMenu()
        for i, item in enumerate(self.recent_codes):
            act = menu.addAction(item['name'])
            act.setData(item['cid'])
        action = menu.exec(QtGui.QCursor.pos())
        if action:
            cid = action.data()
            self.recursive_set_current_item(self.ui.treeWidget.invisibleRootItem(), 
                                            next(c['name'] for c in self.codes if c['cid'] == cid))
            self.mark()

    def mark_with_new_code(self, in_vivo=False):
        """        Creates a new code and marks with it. In vivo: the name is the selected text.
        """

        # In vivo requires a valid text selection (its name comes from it): if there is none, do
        # nothing, neither open the new-code dialog nor fail (e.g. the V shortcut in area mode).
        if in_vivo and (self.selection is None or not self.extracted_ok):
            return
        codes_copy = deepcopy(self.codes)
        if in_vivo and self.selection is not None and self.extracted_ok:
            name = " ".join(self.text[self.selection[0]:self.selection[1]].split())[:40]
            if name == "":
                return
            self.code_tree.add_code(catid=None, code_name=name)
        else:
            self.code_tree.add_code()
        new_code = None
        for code_ in self.codes:
            if code_ not in codes_copy:
                new_code = code_
        if new_code is None and in_vivo:
            name = " ".join(self.text[self.selection[0]:self.selection[1]].split())[:40]
            for code_ in self.codes:
                if code_['name'] == name:
                    new_code = code_
        if new_code is None:
            return
        self.recursive_set_current_item(self.ui.treeWidget.invisibleRootItem(), new_code['name'])
        self.mark()

    def recursive_set_current_item(self, item, text_):
        """        Selects in the tree the code whose name matches.
        """

        child_count = item.childCount()
        for i in range(child_count):
            if item.child(i).text(1)[0:3] == "cid" and \
                    (item.child(i).text(0) == text_ or item.child(i).toolTip(0) == text_):
                self.ui.treeWidget.setCurrentItem(item.child(i))
            self.recursive_set_current_item(item.child(i), text_)

    # Desmarcar, memo, importante. Unmark, memo, important.
    def _select_codings(self, texts_here, areas_here, title):
        """        Returns the list of chosen codings (dialog if there are several).
        """

        entries = []
        for coding in texts_here:
            entries.append({'name': coding['name'], 'type': 'text', 'ref': coding})
        for area in areas_here:
            entries.append({'name': area['name'], 'type': 'area', 'ref': area})
        if not entries:
            return []
        if len(entries) == 1:
            return entries
        ui = DialogSelectItems(self.app, entries, title, "multi")
        ok = ui.exec()
        if not ok:
            return []
        return ui.get_selected()

    def _get_context_codings(self):
        """        Retrieves TEXT codings based on the current selection (clicked word or highlighted text).
        Deliberately ignores image areas to require manual action and prevent accidental deletions.
        """
        texts_here = []
        areas_here = []  # Always empty for keyboard shortcuts (area protection).
        
        if self.selection is not None:
            sel_p0, sel_p1 = self.selection
            # Validates if the coding overlaps with the selected word/text..
            for coding in self.code_text:
                if coding['pos0'] < sel_p1 and coding['pos1'] > sel_p0:
                    texts_here.append(coding)
                    
        return texts_here, areas_here

    def unmark(self, texts_here=None, areas_here=None):
        """        Removes the coding(s) under the current selection (clicked word or highlighted text),
        deleting them from code_text or code_image. If there are several, it asks which to remove.
        Shortcut U.
        """
        
        if texts_here is None or areas_here is None:
            texts_here, areas_here = self._get_context_codings()
        
        selected = self._select_codings(texts_here, areas_here, _("Select code to unmark"))
        if not selected: return
        
        cur = self.app.conn.cursor()
        changed = set()
        # Save what is deleted
        # BEFORE deleting: without this the undo lists stayed empty forever and
        # "Undo last unmark" never showed in the menu.
        self.undo_deleted_codes = []
        self.undo_deleted_areas = []
        for entry in selected:
            if entry['type'] == 'text':
                self.undo_deleted_codes.append(dict(entry['ref']))
                cur.execute("delete from code_text where ctid=?", [entry['ref']['ctid']])
                changed.add('code_text')
            else:
                self.undo_deleted_areas.append(dict(entry['ref']))
                cur.execute("delete from code_image where imid=?", [entry['ref']['imid']])
                changed.add('code_image')
        self.app.conn.commit()
        if changed and getattr(self.app, "project_events", None):
            self.app.project_events.emit_table_changes(sorted(changed), source=self)
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()

    def undo_last_unmarked_code(self):
        """        Restores the last deleted codings (text and area).
        """

        if not self.undo_deleted_codes and not self.undo_deleted_areas:
            return
        cur = self.app.conn.cursor()
        changed = set()
        for item in self.undo_deleted_codes:
            cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,memo,date,important) "
                        "values(?,?,?,?,?,?,?,?,?)",
                        (item['cid'], item['fid'], item['seltext'], item['pos0'], item['pos1'],
                         item['owner'], item['memo'],
                         datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                         item['important']))
            changed.add('code_text')
        for item in self.undo_deleted_areas:
            cur.execute("insert into code_image (id,x1,y1,width,height,cid,memo,date,owner,"
                        "important,pdf_page) values(?,?,?,?,?,?,?,?,?,?,?)",
                        (item['id'], item['x1'], item['y1'], item['width'], item['height'],
                         item['cid'], item['memo'],
                         datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                         item['owner'], item['important'], item['pdf_page']))
            changed.add('code_image')
        self.app.conn.commit()
        if changed and getattr(self.app, "project_events", None) is not None:
            self.app.project_events.emit_table_changes(sorted(changed), source=self)
        self.undo_deleted_codes = []
        self.undo_deleted_areas = []
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        self.update_file_tooltip()

    def toggle_important(self, texts_here=None, areas_here=None):
        """        Toggles the "important" flag on the selected codings (text or area). Shortcut I.
        """
        if texts_here is None or areas_here is None:
            texts_here, areas_here = self._get_context_codings()
            
        selected = self._select_codings(texts_here, areas_here, _("Select coding to flag important"))
        if not selected: return
        
        cur = self.app.conn.cursor()
        for entry in selected:
            ref = entry['ref']
            new_flag = None if ref['important'] == 1 else 1
            if entry['type'] == 'text':
                cur.execute("update code_text set important=? where ctid=?", (new_flag, ref['ctid']))
            else:
                cur.execute("update code_image set important=? where imid=?", (new_flag, ref['imid']))
        self.app.conn.commit()
        self.get_coded_text_update_eventfilter_tooltips()

    def change_code_for_segment(self, text_item=None, area_item=None):
        """        Changes the code (cid) of ONE already-coded segment: text (by ctid) or image area
        (by imid). Uses the SAME popup as code_text (DialogSelectItems, "single" mode), with
        the code list minus the current one. If the new one already codes that exact segment
        it warns and does not duplicate. Used from the margin menu.
        """

        if self.file_ is None or not self.codes:
            return
        current = area_item if area_item is not None else text_item
        if current is None:
            return
        # Code list without the current one, in the same popup as code_text.
        codes_list = deepcopy(self.codes)
        to_remove = next((c for c in codes_list if c['cid'] == current.get('cid')), None)
        if to_remove:
            codes_list.remove(to_remove)
        if not codes_list:
            return
        ui = DialogSelectItems(self.app, codes_list, _("Select replacement code"), "single")
        if not ui.exec():
            return
        replacement_code = ui.get_selected()
        if not replacement_code:
            return
        new_cid = replacement_code['cid']
        cur = self.app.conn.cursor()
        changed = None
        if area_item is not None:
            try:
                cur.execute("update code_image set cid=? where imid=?", [new_cid, area_item['imid']])
                self.app.conn.commit()
            except sqlite3.IntegrityError:
                Message(self.app, _("Change code"),
                        _("That area is already coded with the chosen code."), "warning").exec()
                return
            changed = 'code_image'
        else:
            try:
                cur.execute("update code_text set cid=? where ctid=?", [new_cid, text_item['ctid']])
                self.app.conn.commit()
            except sqlite3.IntegrityError:
                Message(self.app, _("Change code"),
                        _("That text segment is already coded with the chosen code."), "warning").exec()
                return
            changed = 'code_text'
        self.app.delete_backup = False
        if changed and getattr(self.app, "project_events", None) is not None:
            self.app.project_events.emit_table_changes([changed], source=self)
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()

    # Coder change, Mark speakers and autocoding, ported from code_text.py and adapted
    # to this module (absolute positions over the fulltext, no edit mode).

    def edit_coder_names(self):
        """Open the coder names dialog and refresh the view if names changed."""

        ui_coder_names = DialogCoderNames(self.app, extended_options=False)
        if (ui_coder_names.exec() == QtWidgets.QDialog.DialogCode.Accepted and
                ui_coder_names.coder_names_changed):
            self.update_coder_names()

    def update_coder_names(self):
        """Update ui elements related to the coder names, also close contents in
        tab_reports since they must update coder names as well.
        """

        self.annotations = self.app.get_annotations()
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        self.ui.lineEdit_coder.setText(self.app.settings['codername'])
        # Close tab_reports contents, they must update coder names as well
        contents = self.tab_reports.layout()
        if contents:
            for i in reversed(range(contents.count())):
                contents.itemAt(i).widget().close()
                contents.itemAt(i).widget().setParent(None)

    def mark_speakers(self):
        """Open the Mark Speakers dialog for the current pdf file.
        Speaker codings are stored on the fulltext, so they display in this view.
        """

        if self.file_ is None:
            Message(self.app, _('Mark speakers'), _('No file was selected.'), 'critical').exec()
            return
        ui_speaker = DialogSpeakers(self.app, self.file_['id'], self.file_['name'])
        if ui_speaker.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.update_dialog_codes_and_categories(["code_name", "code_text"])
            if self.app.conn is not None and speaker_coder_name not in self.app.get_coder_names_in_project(
                    only_visible=True):
                msg = _(
                    'Coder "{}" is currently hidden. Do you want to make it visible, to see the speaker codings?').format(
                    speaker_coder_name)
                msg_box = Message(self.app, _('Speaker coding'), msg, 'Information')
                msg_box.setStandardButtons(
                    QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
                msg_box.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Yes)
                reply = msg_box.exec()
                if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                    cur = self.app.conn
                    cur.execute('update coder_names set visibility=1 where name=?', (speaker_coder_name,))
                    cur.commit()
                    self.update_coder_names()

    def _after_autocode_refresh(self):
        """Notify other dialogs and refresh this view after autocoding changes."""

        if getattr(self.app, "project_events", None) is not None:
            self.app.project_events.emit_table_changes(['code_text'], source=self)
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        self.update_file_tooltip()

    def button_auto_code_menu(self, position):
        """Options to auto-code all instances, first instance or last instance in a file.
        For Exact text matches.
        """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        msg = " *" if self.autocode_all_first_last_within == "all" else ""
        action_all = QtGui.QAction(_("all matches in file") + msg)
        msg = " *" if self.autocode_all_first_last_within == "first" else ""
        action_first = QtGui.QAction(_("first match in file") + msg)
        msg = " *" if self.autocode_all_first_last_within == "last" else ""
        action_last = QtGui.QAction(_("last match in file") + msg)
        if self.autocode_all_first_last_within.startswith("code_within_code "):
            msg = f" * cid:{self.autocode_all_first_last_within.split(' ')[1]}"
        else:
            msg = ""
        action_code_within_code = QtGui.QAction(_("code within code") + msg)
        menu.addAction(action_all)
        menu.addAction(action_first)
        menu.addAction(action_last)
        menu.addAction(action_code_within_code)
        action = menu.exec(self.ui.pushButton_auto_code.mapToGlobal(position))
        if action is None:
            return
        if action == action_all:
            self.autocode_all_first_last_within = "all"
        if action == action_first:
            self.autocode_all_first_last_within = "first"
        if action == action_last:
            self.autocode_all_first_last_within = "last"
        if action == action_code_within_code:
            ui = DialogSelectItems(self.app, self.codes, _("Select code"), "single")
            ok = ui.exec()
            if not ok:
                return
            code_ = ui.get_selected()
            if not code_:
                return
            self.autocode_all_first_last_within = f"code_within_code {code_['cid']}"

    def button_auto_code_frag_menu(self, position):
        """Options to auto-code all instances, first instance or last instance in a file.
        For fragments of a sentence to code the full sentence.
        """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        msg = " *" if self.autocode_frag_all_first_within == "all" else ""
        action_all = QtGui.QAction(_("all matches in file") + msg)
        msg = " *" if self.autocode_frag_all_first_within == "first" else ""
        action_first = QtGui.QAction(_("first match in file") + msg)
        if self.autocode_frag_all_first_within.startswith("code_within_code "):
            msg = f" * cid:{self.autocode_frag_all_first_within.split(' ')[1]}"
        else:
            msg = ""
        action_code_within_code = QtGui.QAction(_("code within code") + msg)
        menu.addAction(action_all)
        menu.addAction(action_first)
        menu.addAction(action_code_within_code)
        action = menu.exec(self.ui.pushButton_auto_code_frag_this_file.mapToGlobal(position))
        if action is None:
            return
        if action == action_all:
            self.autocode_frag_all_first_within = "all"
        if action == action_first:
            self.autocode_frag_all_first_within = "first"
        if action == action_code_within_code:
            ui = DialogSelectItems(self.app, self.codes, _("Select code"), "single")
            ok = ui.exec()
            if not ok:
                return
            code_ = ui.get_selected()
            if not code_:
                return
            self.autocode_frag_all_first_within = f"code_within_code {code_['cid']}"

    def auto_code(self):
        """Autocode text in one pdf file or all pdf files with currently selected code.
        Button menu option to auto-code all, first or last instances in files, or within an existing code.
        Split multiple find texts with pipe |
        Las posiciones se calculan sobre el fulltext, como el resto del modulo (indices de
        cadena de Python). Positions are computed over the fulltext, like the rest of this
        module (Python string indices).
        """

        code_item = self.ui.treeWidget.currentItem()
        if code_item is None or code_item.text(1).split(':')[0] != 'cid':
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec()
            return
        cid = int(code_item.text(1).split(':')[1])
        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
        dialog.setWindowTitle(_("Automatic coding"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog.setToolTip(_("Use | to code multiple texts"))
        if self.ui.checkBox_auto_regex.isChecked():
            dialog.setLabelText(_("Auto code files with the current code using Regex:") + "\n" + code_item.text(0))
        else:
            dialog.setLabelText(_("Auto code files with the current code for this text:") + "\n" + code_item.text(0))
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        find_text = str(dialog.textValue())
        if find_text == "" or find_text is None:
            return
        texts_ = find_text.split('|')
        find_texts = [t for t in list(set(texts_)) if t != ""]
        # Regex: pipe | has another meaning, do not split
        if self.ui.checkBox_auto_regex.isChecked():
            find_texts = [find_text]
        if len(self.files) == 0:
            return
        ui = DialogSelectItems(self.app, self.files, _("Select files to code"), "many")
        ok = ui.exec()
        if not ok:
            return
        files = ui.get_selected()
        if len(files) == 0:
            return
        regex_pattern = None
        if self.ui.checkBox_auto_regex.isChecked():
            try:
                regex_pattern = re.compile(find_texts[0])
            except re.error as e_:
                logger.warning('Regex error Bad escape ' + str(e_))
                Message(self.app, _("Regex compilation error"), str(e_)).exec()
            if regex_pattern is None:
                return

        found_instances = 0
        undo_list = []
        msg = _("Autocode Text") + f": {self.autocode_all_first_last_within} : {find_texts}"
        if self.ui.checkBox_auto_regex.isChecked():
            msg += " : Using REGEX"
        msg += "\n"
        cur = self.app.conn.cursor()
        try:
            for find_txt in find_texts:
                for f in files:
                    cur.execute("select name, id, fulltext from source where id=? and "
                                "(mediapath like '/docs/%' or mediapath like 'docs:%')", [f['id']])
                    current_file = cur.fetchone()
                    if current_file is None:
                        logger.error(f"File not found, file id: {f['id']}")
                        continue
                    file_text = current_file[2]
                    if regex_pattern:
                        text_starts = [match.start() for match in regex_pattern.finditer(file_text)]
                        text_ends = [match.end() for match in regex_pattern.finditer(file_text)]
                    else:
                        text_starts = [match.start() for match in re.finditer(re.escape(find_txt), file_text)]
                        text_ends = [match.end() for match in re.finditer(re.escape(find_txt), file_text)]
                    msg += f"{f['name']}: {len(text_starts)}. "
                    if self.autocode_all_first_last_within == "first" and len(text_starts) > 1:
                        text_starts = [text_starts[0]]
                        text_ends = [text_ends[0]]
                    if self.autocode_all_first_last_within == "last" and len(text_starts) > 1:
                        text_starts = [text_starts[-1]]
                        text_ends = [text_ends[-1]]
                    if self.autocode_all_first_last_within.startswith("code_within_code"):
                        cur.execute("select pos0,pos1 from code_text where cid=? and fid=? and owner=?",
                                    [int(self.autocode_all_first_last_within.split()[1]), f['id'],
                                     self.app.settings['codername']])
                        res = cur.fetchall()
                        within_starts = []
                        within_ends = []
                        for r in res:
                            for i in range(0, len(text_starts)):
                                if text_starts[i] >= r[0] and text_ends[i] <= r[1]:
                                    within_starts.append(text_starts[i])
                                    within_ends.append(text_ends[i])
                        text_starts = within_starts
                        text_ends = within_ends
                    for index in range(len(text_starts)):
                        pos0 = text_starts[index]
                        pos1 = text_ends[index]
                        # seltext from the
                        # fulltext: exact also with regex
                        seltext = file_text[pos0:pos1]
                        item = {'cid': cid, 'fid': int(f['id']), 'seltext': seltext,
                                'pos0': pos0, 'pos1': pos1,
                                'owner': self.app.settings['codername'], 'memo': "",
                                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
                        try:
                            found_instances += 1
                            cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,"
                                        "owner,memo,date) values(?,?,?,?,?,?,?,?)",
                                        [item['cid'], item['fid'], item['seltext'], item['pos0'],
                                         item['pos1'], item['owner'], item['memo'], item['date']])
                            undo = {
                                "sql": "delete from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?",
                                "cid": item['cid'], "fid": item['fid'], "pos0": item['pos0'], "pos1": item['pos1'],
                                "owner": item['owner']}
                            undo_list.append(undo)
                        except sqlite3.IntegrityError as err:
                            logger.debug(_("Autocode insert error ") + str(err))  # Posible duplicado. Possible duplicate
                        self.app.delete_backup = False
                self.app.conn.commit()
        except Exception as err:
            print(err)
            self.app.conn.rollback()  # Revert all changes
            logger.error(f"auto_code rollback. {err}")
            self.parent_textEdit.append(_("Autocoding error: ") + str(err))
            raise
        if len(undo_list) > 0:
            name = _("Text coding: ") + _("\nCode: ") + code_item.text(0)
            name += _("\nWith: ") + find_text
            undo_dict = {"name": name, "sql_list": undo_list}
            self.autocode_history.insert(0, undo_dict)
        self.parent_textEdit.append(msg)
        self._after_autocode_refresh()

    def auto_code_sentences(self):
        """Code full sentence based on text fragment, in selected pdf files.
        Button right-click options are: all (default), first, code within code.
        """

        if len(self.files) == 0:
            return
        ui = DialogSelectItems(self.app, self.files, _("Select files to code"), "many")
        ok = ui.exec()
        if not ok:
            return
        files = ui.get_selected()
        if len(files) == 0:
            return
        item = self.ui.treeWidget.currentItem()
        if item is None or item.text(1).split(':')[0] != 'cid':
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec()
            return
        cid = int(item.text(1).split(':')[1])
        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
        dialog.setWindowTitle(_("Code sentence"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog.setLabelText(_("Auto code sentence using this text fragment:"))
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        find_text = dialog.textValue()
        if find_text == "":
            return
        dialog_sentence_end = QtWidgets.QInputDialog(None)
        dialog_sentence_end.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
        dialog_sentence_end.setWindowTitle(_("Code sentence"))
        dialog_sentence_end.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog_sentence_end.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog_sentence_end.setToolTip("Use \\n for line ending")
        dialog_sentence_end.setLabelText(
            _("Define sentence ending. Default is period space.\nUse \\n for line ending:"))
        dialog_sentence_end.setTextValue(". ")
        dialog_sentence_end.resize(200, 40)
        ok2 = dialog_sentence_end.exec()
        if not ok2:
            return
        ending = dialog_sentence_end.textValue()
        if ending == "":
            return
        ending = ending.replace("\\n", "\n")

        cur = self.app.conn.cursor()
        msg = ""
        undo_list = []
        regex_pattern = None
        if self.ui.checkBox_auto_regex.isChecked():
            try:
                regex_pattern = re.compile(find_text)
            except re.error as e_:
                logger.warning('re error Bad escape ' + str(e_))
                Message(self.app, _("Regex compilation error"), str(e_)).exec()
            if regex_pattern is None:
                return
        try:
            for f in files:
                # self.files has no fulltext, fetch from DB
                cur.execute("select fulltext from source where id=?", [f['id']])
                res_text = cur.fetchone()
                if res_text is None or res_text[0] is None:
                    continue
                fulltext = res_text[0]
                sentences = fulltext.split(ending)
                pos0 = 0
                codes_added = 0
                surround_codes = []
                if self.autocode_frag_all_first_within.startswith("code_within_code"):
                    cur.execute("select pos0,pos1 from code_text where cid=? and fid=? and owner=?",
                                [int(self.autocode_frag_all_first_within.split()[1]), f['id'],
                                 self.app.settings['codername']])
                    surround_codes = cur.fetchall()
                    if not surround_codes:
                        continue
                for sentence in sentences:
                    if (find_text in sentence and not regex_pattern) or (
                            regex_pattern and regex_pattern.search(sentence)):
                        i = {'cid': cid, 'fid': int(f['id']), 'seltext': str(sentence),
                             'pos0': pos0, 'pos1': pos0 + len(sentence),
                             'owner': self.app.settings['codername'], 'memo': "",
                             'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
                        found_code_in_code = False
                        if self.autocode_frag_all_first_within.startswith("code_within_code"):
                            for surround_code in surround_codes:
                                if i['pos0'] >= surround_code[0] and i['pos1'] <= surround_code[1]:
                                    found_code_in_code = True
                        if self.autocode_frag_all_first_within in ("all", "first") or found_code_in_code:
                            try:
                                codes_added += 1
                                cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,"
                                            "owner,memo,date) values(?,?,?,?,?,?,?,?)",
                                            (i['cid'], i['fid'], i['seltext'], i['pos0'],
                                             i['pos1'], i['owner'], i['memo'], i['date']))
                                undo = {
                                    "sql": "delete from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?",
                                    "cid": i['cid'], "fid": i['fid'], "pos0": i['pos0'], "pos1": i['pos1'],
                                    "owner": i['owner']}
                                undo_list.append(undo)
                                self.app.conn.commit()
                            except Exception as e:
                                logger.debug(_("Autocode insert error ") + str(e))
                    pos0 += len(sentence) + len(ending)  # Avanzar. Move forward
                    if codes_added == 1 and self.autocode_frag_all_first_within == "first":
                        break
                if codes_added > 0:
                    msg += _("File: ") + f"{f['name']} {codes_added}" + _(" added codes") + "\n"
        except Exception as e_:
            print(e_)
            self.app.conn.rollback()  # Revert all changes
            raise
        if len(undo_list) > 0:
            name = _("Sentence coding: ") + _("\nCode: ") + item.text(0)
            name += _("\nWith: ") + find_text + _("\nUsing line ending: ") + ending
            undo_dict = {"name": name, "sql_list": undo_list}
            self.autocode_history.insert(0, undo_dict)
        self.parent_textEdit.append(_("Automatic code sentence in files:")
                                    + _("\nCode: ") + item.text(0)
                                    + _("\nWith text fragment: ") + find_text
                                    + _("\nUsing line ending: ") + ending + "\n" + msg)
        self.app.delete_backup = False
        self._after_autocode_refresh()

    def button_autocode_surround(self):
        """Autocode with selected code using start and end marks in selected pdf files.
        Line ending text representation \\n is replaced with the actual line ending character.
        Regex is not used for this function.
        """

        item = self.ui.treeWidget.currentItem()
        if item is None or item.text(1).split(':')[0] != 'cid':
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec()
            return
        ui = DialogGetStartAndEndMarks("Autocoding", "Autocoding surround")
        ok = ui.exec()
        if not ok:
            return
        start_mark = ui.get_start_mark()
        if "\\n" in start_mark:
            start_mark = start_mark.replace("\\n", "\n")
        end_mark = ui.get_end_mark()
        if "\\n" in end_mark:
            end_mark = end_mark.replace("\\n", "\n")
        if start_mark == "" or end_mark == "":
            Message(self.app, _('Warning'), _("Cannot have blank text marks"), "warning").exec()
            return
        ui = DialogSelectItems(self.app, self.files, _("Select files to code"), "many")
        ok = ui.exec()
        if not ok:
            return
        files = ui.get_selected()
        if len(files) == 0:
            return

        msg = _("Code text using start and end marks: ")
        msg += _("\nUsing ") + start_mark + _(" and ") + end_mark + "\n"
        cur = self.app.conn.cursor()
        cid = int(item.text(1).split(':')[1])
        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        already_assigned = 0
        entries = 0
        undo_list = []
        for f in files:
            # self.files has no fulltext, fetch from DB
            cur.execute("select fulltext from source where id=?", [f['id']])
            res_text = cur.fetchone()
            if res_text is None or res_text[0] is None:
                continue
            fulltext = res_text[0]
            text_starts = [match.start() for match in re.finditer(re.escape(start_mark), fulltext)]
            text_ends = [match.start() for match in re.finditer(re.escape(end_mark), fulltext)]
            try:
                for start_pos in text_starts:
                    text_end_iterator = 0
                    try:
                        while start_pos >= text_ends[text_end_iterator]:
                            text_end_iterator += 1
                    except IndexError:
                        text_end_iterator = -1
                    if text_end_iterator >= 0:
                        pos1 = text_ends[text_end_iterator]
                        # Check if already coded by this coder
                        sql = "select cid from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?"
                        cur.execute(sql, [cid, f['id'], start_pos, pos1, self.app.settings['codername']])
                        res = cur.fetchone()
                        if res is None:
                            seltext = fulltext[start_pos: pos1]
                            sql = ("insert into code_text (cid, fid, seltext, pos0, pos1, owner, date, memo) "
                                   "values(?,?,?,?,?,?,?,?)")
                            cur.execute(sql, (cid, f['id'], seltext, start_pos, pos1,
                                              self.app.settings['codername'], now_date, ""))
                            undo = {
                                "sql": "delete from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?",
                                "cid": cid, "fid": f['id'], "pos0": start_pos, "pos1": pos1,
                                "owner": self.app.settings['codername']}
                            undo_list.append(undo)
                            entries += 1
                        else:
                            already_assigned += 1
                self.app.conn.commit()
            except Exception as e_:
                print(e_)
                self.app.conn.rollback()  # Revert all changes
                raise
        if len(undo_list) > 0:
            name = _("Coding using start and end marks") + _("\nCode: ") + item.text(0)
            name += _("\nWith start mark: ") + start_mark + _("\nEnd mark: ") + end_mark
            undo_dict = {"name": name, "sql_list": undo_list}
            self.autocode_history.insert(0, undo_dict)
        msg += str(entries) + _(" new coded sections found.") + "\n"
        if already_assigned > 0:
            msg += f"{already_assigned} " + _("previously coded.") + "\n"
        self.parent_textEdit.append(msg)
        Message(self.app, "Autocode surround", msg).exec()
        self.app.delete_backup = False
        self._after_autocode_refresh()

    def undo_autocoding(self):
        """Present a list of choices for the undo operation.
        User selects and undoes the chosen autocoding operation.
        The autocode_history is a list of dictionaries with 'name' and 'sql_list'.
        """

        if not self.autocode_history:
            return
        ui = DialogSelectItems(self.app, self.autocode_history, _("Select auto-codings to undo"), "single")
        ok = ui.exec()
        if not ok:
            return
        undo = ui.get_selected()
        cur = self.app.conn.cursor()
        try:
            for i in undo['sql_list']:
                cur.execute(i['sql'], [i['cid'], i['fid'], i['pos0'], i['pos1'], i['owner']])
            self.app.conn.commit()
        except Exception as e_:
            print(e_)
            self.app.conn.rollback()  # Revert all changes
            raise
        self.autocode_history.remove(undo)
        self.parent_textEdit.append(_("Undo autocoding: ") + f"{undo['name']}\n")
        self._after_autocode_refresh()

    def show_important_coded(self):
        """        Toggles the filter to show only important codings.
        """

        self.important = not self.important
        try:
            if self.important:
                self.ui.pushButton_important.setToolTip(_("Showing important codings"))
                self.ui.pushButton_important.setIcon(qta.icon('mdi6.star', options=[{'scale_factor': 1.3}]))
            else:
                self.ui.pushButton_important.setToolTip(_("Show codings flagged important"))
                self.ui.pushButton_important.setIcon(qta.icon('mdi6.star-outline', options=[{'scale_factor': 1.3}]))
        except Exception as err:
            logger.debug(f"icono important: {err}")
        self.rebuild_marks()

    def captions_options(self):
        """        Cycles the caption mode over coded areas: 0 hidden, 1 name, 2 name + memo.
        """
        self.show_code_captions += 1
        if self.show_code_captions > 2:
            self.show_code_captions = 0
        # Just repaint: mark data does not change.
        for it in self.view.items_:
            it.update()

    def set_default_new_code_color(self):
        """        Sets a default colour for new codes instead of the random one (parity with code_text).
        """
        tmp_code = {'name': 'new', 'color': None}
        ui = DialogColorSelect(self.app, tmp_code)
        if not ui.exec():
            return
        color = ui.get_color()
        if color is not None:
            self.ui.pushButton_default_new_code_color.setStyleSheet(f'background-color: {color}')
        self.default_new_code_color = color

    def show_annotations(self):
        """        Shows all annotations for the file in a read-only dialog (parity with code_text).
        """
        if self.file_ is None:
            return
        cur = self.app.conn.cursor()
        sql = "select substr(source.fulltext,pos0+1 ,pos1-pos0), pos0, pos1, annotation_visible.memo "
        sql += "from annotation_visible join source on annotation_visible.fid = source.id "
        sql += "where fid=? order by pos0"
        cur.execute(sql, [self.file_['id']])
        res = cur.fetchall()
        if not res:
            Message(self.app, _("Annotations"), _("There are no annotations for this file."),
                    "Information").exec()
            return
        text_ = ""
        for r in res:
            text_ += f"[{r[1]}-{r[2]}] \n"
            text_ += _("Text: ") + f"{r[0]}\n"
            text_ += _("Annotation: ") + r[3] + "\n\n"
        ui = DialogMemo(self.app, _("Annotations for file: ") + self.file_['name'], text_)
        ui.ui.pushButton_clear.hide()
        ui.ui.textEdit.setReadOnly(True)
        ui.exec()

    def show_memos(self):
        """        Shows the coding memos for the file in a read-only dialog: text (parity with
        code_text) and areas (PDF specific).
        """
        if self.file_ is None:
            return
        text_ = ""
        cur = self.app.conn.cursor()
        # Coded-text memos.
        sql = "select code_name.name, pos0, pos1, seltext, code_text_visible.memo, code_text_visible.owner "
        sql += "from code_text_visible join code_name on code_text_visible.cid = code_name.cid "
        sql += "where length(code_text_visible.memo)>0 and fid=? order by pos0"
        cur.execute(sql, [self.file_['id']])
        for r in cur.fetchall():
            text_ += f"[{r[1]}-{r[2]}] " + _("Code: ") + f"{r[0]} ({r[5]})\n"
            text_ += _("Text: ") + f"{r[3]}\n"
            text_ += _("Memo: ") + f"{r[4]}\n\n"
        sql_a = "select code_name.name, pdf_page, x1, y1, width, height, code_image_visible.memo, code_image_visible.owner "
        sql_a += "from code_image_visible join code_name on code_image_visible.cid = code_name.cid "
        sql_a += "where length(code_image_visible.memo)>0 and code_image_visible.id=? order by pdf_page, y1"
        cur.execute(sql_a, [self.file_['id']])
        for r in cur.fetchall():
            pagina = (r[1] or 0) + 1
            text_ += f"[{_('Page')} {pagina}: {r[2]},{r[3]} {r[4]}x{r[5]}] " + _("Code: ") + f"{r[0]} ({r[7]})\n"
            text_ += _("Memo: ") + f"{r[6]}\n\n"
        if text_ == "":
            Message(self.app, _("Memos"), _("There are no coding memos for this file."),
                    "Information").exec()
            return
        ui = DialogMemo(self.app, _("Memos for file: ") + self.file_['name'], text_)
        ui.ui.pushButton_clear.hide()
        ui.ui.textEdit.setReadOnly(True)
        ui.exec()

    # Busqueda. Search.
    def search_for_text(self, _text=None, force=False):
        """        Searches the extracted text (independent of the database, rects come from the word map).
        3 or more characters, or Enter to force.
        """

        term = self.ui.lineEdit_search.text()
        self._clear_search_rects()
        self.search_indices = []
        self.search_index = -1
        if not self.pages or term == "" or (len(term) < 3 and not force):
            self.ui.label_search_totals.setText("0 / 0")
            return
        case_sensitive = self.ui.checkBox_search_case.isChecked()
        haystack = self.text if case_sensitive else self.text.lower()
        needle = term if case_sensitive else term.lower()
        start = 0
        while len(self.search_indices) < 5000:
            found = haystack.find(needle, start)
            if found == -1:
                break
            self.search_indices.append((found, found + len(needle)))
            start = found + 1
        if not self.search_indices:
            self.ui.label_search_totals.setText("0 / 0")
            return
        # Highlight all matches only if they are few (performance)
        if len(self.search_indices) <= 400:
            for pos0, pos1 in self.search_indices:
                for page_idx in self._pages_spanning(pos0, pos1):
                    if page_idx >= len(self.view.items_):
                        continue
                    rects = self.rects_for_range(page_idx, pos0, pos1)
                    if rects:
                        self.view.items_[page_idx].search_rects.extend(rects)
                        self._search_pages.add(page_idx)
        self.search_index = -1
        self.move_to_next_search_text()

    def _clear_search_rects(self):
        for idx in self._search_pages:
            if idx < len(self.view.items_):
                self.view.items_[idx].search_rects = []
                self.view.items_[idx].current_search = []
                self.view.items_[idx].update()
        self._search_pages = set()

    def _show_current_search(self):
        """        Highlights the current search match (search_index) with an emphasized color and
        scrolls the viewer to it, updating the "current / total" counter.
        """
        if not self.search_indices or self.search_index < 0:
            return
        for idx in list(self._search_pages):
            if idx < len(self.view.items_):
                self.view.items_[idx].current_search = []
        pos0, pos1 = self.search_indices[self.search_index]
        first_scene_rect = None
        for page_idx in self._pages_spanning(pos0, pos1):
            if page_idx >= len(self.view.items_):
                continue
            rects = self.rects_for_range(page_idx, pos0, pos1)
            if rects:
                item = self.view.items_[page_idx]
                item.current_search = rects
                self._search_pages.add(page_idx)
                item.update()
                if first_scene_rect is None:
                    first_scene_rect = rects[0].translated(item.pos())
        for idx in self._search_pages:
            if idx < len(self.view.items_):
                self.view.items_[idx].update()
        self.ui.label_search_totals.setText(f"{self.search_index + 1} / {len(self.search_indices)}")
        if first_scene_rect is not None:
            self.view.scroll_to_scene_rect(first_scene_rect)

    def move_to_next_search_text(self):
        if not self.search_indices:
            return
        self.search_index = (self.search_index + 1) % len(self.search_indices)
        self._show_current_search()

    def move_to_previous_search_text(self):
        if not self.search_indices:
            return
        self.search_index = (self.search_index - 1) % len(self.search_indices)
        self._show_current_search()

    # Navegacion, zoom y modos. Navigation, zoom and modes
    def update_page_indicator(self, page_idx):
        if self.total_pages == 0:
            return
        self.ui.lineEdit_page.blockSignals(True)
        if not self.ui.lineEdit_page.hasFocus():
            self.ui.lineEdit_page.setText(str(page_idx + 1))
        self.ui.lineEdit_page.blockSignals(False)

    def update_zoom_label(self, zoom):
        self.ui.label_zoom.setText(f"{int(round(zoom * 100))}%")

    def goto_page_from_edit(self):
        try:
            page = int(self.ui.lineEdit_page.text()) - 1
        except ValueError:
            return
        self.view.goto_page(page)

    def change_page_view_mode(self, index):
        """ Combobox: 0 = whole document (continuous scroll), 1 = single page.
        The choice is persisted to config.ini, like the coding margin width. """

        self.view.set_view_mode(index == 1)
        self.app.settings['dialogcodepdf_page_view'] = int(index)
        try:
            self.app.write_config_ini(self.app.settings, self.app.ai_models)
        except Exception as e_:
            logger.debug(f"Could not persist page view setting: {e_}")

    def next_page(self):
        self.view.goto_page(self.view.center_page_index() + 1)

    def previous_page(self):
        self.view.goto_page(self.view.center_page_index() - 1)

    def zoom_in(self):
        self.view.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.view.set_zoom(self.view.zoom * 1.2)

    def zoom_out(self):
        self.view.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.view.set_zoom(self.view.zoom / 1.2)

    def set_mode(self, mode):
        self.view.mode = mode
        self.ui.pushButton_mode_text.setChecked(mode == "text")
        self.ui.pushButton_mode_area.setChecked(mode == "area")
        if mode == "area":
            self.view.viewport().setCursor(Qt.CursorShape.CrossCursor)
            # Clear any text selection when switching to area mode.
            self.clear_selection()
        else:
            # Text-selection cursor (I-beam) in text mode.
            self.view.viewport().setCursor(Qt.CursorShape.IBeamCursor)

    def fill_code_label(self):
        """        Color chip (under the tree) with the current code; the name goes in the tooltip.
        """

        item = self.ui.treeWidget.currentItem()
        if item is None or item.text(1).split(':')[0] == 'catid':
            self.ui.label_code.setStyleSheet("")
            self.ui.label_code.setToolTip(_("No code selected"))
            return
        cid = int(item.text(1).split(':')[1])
        for code_ in self.codes:
            if code_['cid'] == cid:
                self.ui.label_code.setStyleSheet(
                    f"background-color:{code_['color']}; border: 1px solid #808080; border-radius:3px;")
                tip = _("Code: ") + code_['name']
                if code_['memo'] != "":
                    tip += "\n" + _("Memo: ") + code_['memo']
                self.ui.label_code.setToolTip(tip)
                return

    def handle_key(self, event):
        """        Shortcuts shared by the view and the dialog. Returns True if handled.
        """
        key = event.key()
        mods = event.modifiers()
        
        # codigo in vivo, etc. Plain keys only: before, Ctrl+Q marked, Ctrl+A annotated,
        # Ctrl+V created an in vivo code, etc.
        if key == Qt.Key.Key_Q and mods == Qt.KeyboardModifier.NoModifier:
            self.mark()
            return True
        if key == Qt.Key.Key_U and mods == Qt.KeyboardModifier.NoModifier:
            self.unmark()
            return True
        if key == Qt.Key.Key_A and mods == Qt.KeyboardModifier.NoModifier:
            self.annotate()
            return True
        if key == Qt.Key.Key_I and mods == Qt.KeyboardModifier.NoModifier:
            self.toggle_important()
            return True
        if key == Qt.Key.Key_M and mods == Qt.KeyboardModifier.NoModifier:
            self.coded_memo()
            return True
        if key == Qt.Key.Key_R and mods == Qt.KeyboardModifier.NoModifier:
            self._update_recent_codes_menu()
            return True
        if key == Qt.Key.Key_V and mods == Qt.KeyboardModifier.NoModifier:
            self.mark_with_new_code(in_vivo=True)
            return True
        if key == Qt.Key.Key_N and mods == Qt.KeyboardModifier.NoModifier:
            # The context menu advertised
            # "(N)" without a handler.
            self.mark_with_new_code()
            return True
        # Switch coding mode: T = text, E = area/image (like the mode buttons).
        if key == Qt.Key.Key_T and mods == Qt.KeyboardModifier.NoModifier:
            self.set_mode("text")
            return True
        if key == Qt.Key.Key_E and mods == Qt.KeyboardModifier.NoModifier:
            self.set_mode("area")
            return True
        if key == Qt.Key.Key_Plus or key == Qt.Key.Key_Equal:
            self.zoom_in()
            return True
        if key == Qt.Key.Key_Minus:
            self.zoom_out()
            return True
        if key == Qt.Key.Key_PageDown:
            self.next_page()
            return True
        if key == Qt.Key.Key_PageUp:
            self.previous_page()
            return True
        if key == Qt.Key.Key_F and mods == Qt.KeyboardModifier.ControlModifier:
            self.ui.lineEdit_search.setFocus()
            self.ui.lineEdit_search.selectAll()
            return True
        # Tree widget menu item keys F2 - F6, handled by the shared controller.
        if self.ui.treeWidget.hasFocus():
            if self.code_tree.handle_key_press(event):
                return True
        if key == Qt.Key.Key_F2 and mods == Qt.KeyboardModifier.NoModifier:
            selected = self.ui.treeWidget.currentItem()
            if selected is not None:
                self.code_tree.rename_category_or_code(selected)
                return True
        # Bookmark: saves current file and position (text selection if any, otherwise the start of the centered page).
        if key == Qt.Key.Key_B and mods == Qt.KeyboardModifier.NoModifier and self.file_ is not None:
            pos = None
            if self.selection is not None:
                pos = self.selection[0]
            elif self._page_starts:
                pos = self._page_starts[self.view.center_page_index()]
            if pos is not None:
                pos_abs = pos + self.file_.get('start', 0)
                cur = self.app.conn.cursor()
                cur.execute("update project set bookmarkfile=?, bookmarkpos=?", [self.file_['id'], pos_abs])
                self.app.conn.commit()
                self.ui.label_status.setText(_("Bookmark set"))
            return True
        return False

    def keyPressEvent(self, event):
        if self.handle_key(event):
            return
        super().keyPressEvent(event)

    # AI prompt submenu helpers, ported from code_text.py for parity.
    def _ai_menu_options_enabled(self) -> bool:
        """Return whether AI-specific coding actions should be enabled."""

        return self.app.settings.get('ai_enable', 'False') == 'True'

    @staticmethod
    def _text_analysis_prompt_menu_leaf(relative_path: str) -> str:
        """Return the leaf label for one text-analysis prompt menu item."""

        normalized = str(relative_path if relative_path is not None else "").replace("\\", "/").strip("/")
        if normalized == "":
            return ""
        return normalized.rsplit("/", 1)[-1]

    def _text_analysis_prompt_folder_icon(self):
        """Return the same folder icon used by the prompt library."""

        return qta.icon("mdi.folder-outline", color=self.app.highlight_color())

    def _text_analysis_prompt_file_icon(self, menu):
        """Return the same prompt file icon used by the prompt library."""

        text_color = menu.palette().color(QtGui.QPalette.ColorRole.Text).name()
        return qta.icon("mdi6.script-text-outline", color=text_color)

    def _populate_text_analysis_prompt_menu(self, menu, prompts_catalog, prompt_records) -> None:
        """Populate one prompt menu, mirroring the prompt library folder structure."""

        menu_tree = {"prompts": [], "folders": {}}
        for prompt in prompt_records:
            relative_path = prompts_catalog.prompt_name_within_type(prompt.name)
            parts = [part for part in relative_path.split("/") if part != ""]
            if len(parts) == 0:
                continue
            current_branch = menu_tree
            for part in parts[:-1]:
                current_branch = current_branch["folders"].setdefault(part, {"prompts": [], "folders": {}})
            current_branch["prompts"].append((relative_path, prompt))

        def populate_branch(parent_menu, branch) -> None:
            for branch_relative_path, prompt_record in branch["prompts"]:
                action = parent_menu.addAction(self._text_analysis_prompt_menu_leaf(branch_relative_path))
                action.setToolTip(prompt_record.description)
                action.setIcon(self._text_analysis_prompt_file_icon(parent_menu))
                action.setProperty('submenu', 'ai_text_analysis')
                action.setData(prompt_record)
            for folder_name, child_branch in branch["folders"].items():
                submenu = parent_menu.addMenu(folder_name)
                submenu.setToolTipsVisible(True)
                submenu.setIcon(self._text_analysis_prompt_folder_icon())
                populate_branch(submenu, child_branch)

        populate_branch(menu, menu_tree)

    # Context menu of the view
    def view_menu(self, viewport_pos, global_pos):
        scene_pos = self.view.mapToScene(viewport_pos)
        hit = self.view.page_at(scene_pos)
        texts_here, areas_here = [], []
        notes_here = []
        if hit is not None:
            texts_here, areas_here = self._codings_at(hit[0], hit[1])
            notes_here = self._annotations_at(hit[0], hit[1])
        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        action_mark = None
        action_mark_new = None
        action_in_vivo = None
        recent_actions = []
        if self.selection is not None and self.extracted_ok:
            action_mark = menu.addAction(_("Mark (Q)"))
            if self.recent_codes:
                recent_menu = menu.addMenu(_("Mark with recent code (R)"))
                for code_ in self.recent_codes:
                    act = recent_menu.addAction(code_['name'])
                    act.setData(code_['cid'])
                    recent_actions.append(act)
            action_mark_new = menu.addAction(_("Mark with new code (N)"))
            action_in_vivo = menu.addAction(_("in vivo code (V)"))
        action_annotate = None
        if self.selection is not None and self.extracted_ok:
            action_annotate = menu.addAction(_("Annotate (A)"))
        action_unmark = None
        action_memo = None
        action_important = None
        action_resize_text = None
        action_area_interactive = None
        if texts_here or areas_here:
            menu.addSeparator()
            action_unmark = menu.addAction(_("Unmark (U)"))
            action_memo = menu.addAction(_("Memo for coded segment (M)"))
            action_important = menu.addAction(_("Add important mark (I)"))
            if texts_here:
                action_resize_text = menu.addAction(_("Resize"))
            if areas_here:
                action_area_interactive = menu.addAction(_("Move or resize area"))
        action_edit_annot = None
        action_delete_annot = None
        if notes_here:
            menu.addSeparator()
            action_edit_annot = menu.addAction(_("Edit annotation"))
            action_delete_annot = menu.addAction(_("Delete annotation"))
        action_copy = None
        if self.selection is not None:
            menu.addSeparator()
            action_copy = menu.addAction(_("Copy selected text"))
            
            # Text Analysis with AI Submenu
            if self.extracted_ok:
                submenu_ai_text_analysis = menu.addMenu(_("AI Text Analysis"))
                submenu_ai_text_analysis.setToolTipsVisible(True)
                if self._ai_menu_options_enabled():  # Parity with code_text.py; settings-based check
                    submenu_ai_text_analysis.setEnabled(True)
                    # New Markdown catalog, same pattern as code_text.py
                    prompts_catalog = AiAgentPromptsCatalog(self.app)
                    prompt_records = prompts_catalog.list_visible_prompt_variants(prompt_type='text_analysis')
                    self._populate_text_analysis_prompt_menu(submenu_ai_text_analysis, prompts_catalog, prompt_records)
                    if len(prompt_records) > 0:
                        submenu_ai_text_analysis.addSeparator()
                    ac = submenu_ai_text_analysis.addAction(_('Edit text analysis prompts'))
                    ac.setProperty('submenu', 'ai_text_analysis_prompts')
                else:
                    submenu_ai_text_analysis.setEnabled(False)

        action_undo = None
        if self.undo_deleted_codes or self.undo_deleted_areas:
            action_undo = menu.addAction(_("Undo last unmark"))
        menu.addSeparator()
        margin_menu = menu.addMenu(_("Code stripes margin"))
        if self.show_margin_stripes:
            action_margin_visibility = margin_menu.addAction(_("Hide code stripes margin"))
        else:
            action_margin_visibility = margin_menu.addAction(_("Show code stripes margin"))
        action_margin_left = None
        action_margin_right = None
        if self.margin_side == 'right':
            action_margin_left = margin_menu.addAction(_("Move margin to the left"))
        else:
            action_margin_right = margin_menu.addAction(_("Move margin to the right"))
        style_menu = menu.addMenu(_("Highlight style"))
        action_style_marker = None
        action_style_underline = None
        if self.highlight_style != 'marker':
            action_style_marker = style_menu.addAction(_("Marker"))
        if self.highlight_style != 'underline':
            action_style_underline = style_menu.addAction(_("Underline"))
        menu.addSeparator()
        action_goto = menu.addAction(_("Go to page"))
        action_fit = menu.addAction(_("Fit page width"))
        action = menu.exec(global_pos)
        if action is None:
            return
        if action == action_mark:
            self.mark()
            return
        if action == action_annotate:
            self.annotate()
            return
        if action == action_edit_annot:
            if len(notes_here) == 1:
                note = notes_here[0]
            else:
                note = self._select_single(
                    [{'name': (n.get('memo', '') or _("Annotation"))[:40], 'ref': n}
                     for n in notes_here], _("Select annotation to edit"))
            if note is not None:
                self._edit_annotation(note)
            return
        if action == action_delete_annot:
            if len(notes_here) == 1:
                note = notes_here[0]
            else:
                note = self._select_single(
                    [{'name': (n.get('memo', '') or _("Annotation"))[:40], 'ref': n}
                     for n in notes_here], _("Select annotation to delete"))
            if note is not None:
                self._delete_annotation(note)
            return
        if action in recent_actions:
            cid = action.data()
            self.recursive_set_current_item(self.ui.treeWidget.invisibleRootItem(),
                                            next(c['name'] for c in self.codes if c['cid'] == cid))
            self.mark()
            return
        if action == action_mark_new:
            self.mark_with_new_code()
            return
        if action == action_in_vivo:
            self.mark_with_new_code(in_vivo=True)
            return
        if action == action_unmark:
            self.unmark(texts_here, areas_here)
            return
        if action == action_memo:
            self.coded_memo(texts_here, areas_here)
            return
        if action == action_important:
            self.toggle_important(texts_here, areas_here)
            return
        if action == action_resize_text:
            target = self._select_single(
                [{'name': c['name'], 'ref': c} for c in texts_here], _("Select code to resize"))
            if target is not None:
                self.show_resize_handles(target)
            return
        if action == action_area_interactive:
            target = self._select_single(
                [{'name': a['name'], 'ref': a} for a in areas_here], _("Select area to resize"))
            if target is not None:
                self.start_interactive_area_resize(target)
            return
        if action == action_copy:
            pos0, pos1 = self.selection
            QtWidgets.QApplication.clipboard().setText(self.text[pos0:pos1])
            return
        if action == action_undo:
            self.undo_last_unmarked_code()
            return
        if action == action_margin_visibility:
            self._toggle_margin_visibility_only()
            return
        if action == action_margin_left:
            self._set_margin_side('left')
            return
        if action == action_margin_right:
            self._set_margin_side('right')
            return
        if action == action_style_marker:
            self._set_highlight_style('marker')
            return
        if action == action_style_underline:
            self._set_highlight_style('underline')
            return
        if action == action_goto:
            number, ok = QtWidgets.QInputDialog.getInt(self, _("Go to page"), _("Page number:"),
                                                       self.view.center_page_index() + 1, 1,
                                                       max(1, self.total_pages), 1)
            if ok:
                self.view.goto_page(number - 1)
            return
        if action == action_fit:
            self.view.fit_width()
            return
        # self.export_page_image()

        if action.property('submenu') == 'ai_text_analysis':
            if self.file_ is None:
                Message(self.app, _('Warning'), _("No file was selected"), "warning").exec()
                return
            pos0, pos1 = self.selection
            selected_text = self.text[pos0:pos1]
            ai_chat_signal_emitter.newTextChatSignal.emit(
                int(self.file_['id']),
                self.file_['name'],
                selected_text,
                pos0,  # pos0 is already absolute over the full text of this view
                action.data()
            )
            return
        if action.property('submenu') == 'ai_text_analysis_prompts':
            ui = DialogAiEditPrompts(self.app, 'text_analysis')
            ui.exec()
            return

    def export_page_image(self): # Triggers disabled; will be changed to creating a file source from the PDF page image.
        """        Exports the current page as PNG at 2x.
        """

        if self.file_ is None:
            return
        filepath = self._resolve_filepath(self.file_)
        if filepath is None:
            return
        page_idx = self.view.center_page_index()
        suggested = f"{os.path.splitext(self.file_['name'])[0]}_p{page_idx + 1}.png"
        out_path, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self, _("Export current page as image"),
            os.path.join(os.path.expanduser("~"), suggested), "PNG (*.png)")
        if not out_path:
            return
        try:
            doc = fitz.open(filepath)
            page = doc.load_page(page_idx)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            pix.save(out_path)
            doc.close()
            self.parent_textEdit.append(_("Page exported: ") + out_path)
        except Exception as err:
            Message(self.app, _("Warning"), str(err), "warning").exec()

    # Tree of codes and categories
    def get_codes_and_categories(self):
        """        Reload codes and categories from the database.
        """

        self.codes, self.categories = self.app.get_codes_categories()

    def get_recent_codes(self):
        """        Recently used codes, saved as space-separated ids
        in the project table. Requires self.codes already loaded.
        """

        self.recent_codes = []
        cur = self.app.conn.cursor()
        try:
            cur.execute("select recently_used_codes from project")
            res = cur.fetchone()
        except sqlite3.OperationalError:
            return
        if not res or res[0] == "" or res[0] is None:
            return
        for code_id in res[0].split():
            try:
                cid = int(code_id)
            except ValueError:
                continue
            for code_ in self.codes:
                if cid == code_['cid']:
                    self.recent_codes.append(code_)

    def fill_code_counts_in_tree(self):
        """        Frequency of each code and category for this coder and file.
        Includes both text codings (code_text) and area codings (code_image with pdf_page).
        For subcodes, displays "own (total)" when the values differ.
        """

        if self.file_ is None:
            return
        cur = self.app.conn.cursor()
        own_counts = {}
        cur.execute("select cid, count(cid) from code_text_visible where fid=? group by cid",
                    [self.file_['id']])
        for row in cur.fetchall():
            own_counts[row[0]] = own_counts.get(row[0], 0) + row[1]
        cur.execute("select cid, count(cid) from code_image_visible where id=? and "
                    "pdf_page is not null group by cid", [self.file_['id']])
        for row in cur.fetchall():
            own_counts[row[0]] = own_counts.get(row[0], 0) + row[1]
        
        # Sub-code totals: own + all descendants (memoized, cycle-safe).
        code_children = {}
        for c in self.codes:
            sup = c.get('supercid')
            if sup is not None:
                code_children.setdefault(sup, []).append(c['cid'])
        total_counts = {}

        def _code_total(cid_, _seen=None):
            if _seen is None:
                _seen = set()
            if cid_ in total_counts:
                return total_counts[cid_]
            if cid_ in _seen:
                return own_counts.get(cid_, 0)
            _seen.add(cid_)
            total = own_counts.get(cid_, 0)
            for child_cid in code_children.get(cid_, []):
                total += _code_total(child_cid, _seen)
            total_counts[cid_] = total
            return total
        for c in self.codes:
            _code_total(c['cid'])

        categories = deepcopy(self.categories)
        for category in categories:
            category['count'] = 0
        # Each code with a category contributes its TOTAL (own + nested); sub-codes thus
        # roll up to the category of their top ancestor.
        for category in categories:
            for c in self.codes:
                if c['catid'] == category['catid']:
                    category['count'] += total_counts.get(c['cid'], 0)
                    
        # Propagate from leaf nodes to parent categories.
        sub_categories = copy(categories)
        counter = 0
        while len(sub_categories) > 0 and counter < 10000:
            leaf_list = []
            branch_list = []
            for cat in sub_categories:
                for cat2 in sub_categories:
                    if cat['catid'] == cat2['supercatid']:
                        branch_list.append(cat)
            for category in sub_categories:
                if category not in branch_list:
                    leaf_list.append(category)
            for leaf_category in leaf_list:
                for category in categories:
                    if category['catid'] == leaf_category['supercatid']:
                        category['count'] += leaf_category['count']
                sub_categories.remove(leaf_category)
            counter += 1
        # Populate the tree items with the counts.
        iterator = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        while iterator.value():
            item = iterator.value()
            if item.text(1).startswith("catid"):
                catid = int(item.text(1)[6:])
                for category in categories:
                    if catid == category['catid']:
                        item.setText(3, str(category['count']))
            else:
                # Code: own count, and "own (total)" when they differ because of sub-codes.
                cid = int(item.text(1)[4:])
                own = own_counts.get(cid, 0)
                total = total_counts.get(cid, own)
                if total != own:
                    item.setText(3, f"{own} ({total})")
                else:
                    item.setText(3, str(own))
            iterator += 1

    def tree_item_clicked(self, item, column):
        """        The memo column opens the memo. Clicking a code while a text selection or a
        pending area is active immediately applies the code.
        """

        if item is None:
            return
        if column == 2:
            self.code_tree.add_edit_cat_or_code_memo(item)
            return
        if item.text(1)[0:3] == 'cid':
            if self.selection is not None:
                self.mark()
        self.fill_code_label()

    def get_collapsed(self, item):
        """        Preserves the expanded/collapsed state of categories across dialogs.
        """

        if item.text(1)[0:3] == "cid":
            return
        if item.isExpanded() and item.text(1) in self.app.collapsed_categories:
            self.app.collapsed_categories.remove(item.text(1))
        if not item.isExpanded() and item.text(1) not in self.app.collapsed_categories:
            self.app.collapsed_categories.append(item.text(1))

    def coded_media_dialog(self, code_dict, category_name=""):
        """        Displays all media coded with this code (or category branch) in a
        separate modal dialog and refreshes the layers when returning.
        """

        DialogCodeInAllFiles(self.app, code_dict, "File", category_name)
        self.get_coded_text_update_eventfilter_tooltips()

    def _drop_would_cycle(self, dragged, target):
        """ True if dropping 'dragged' onto 'target' would create a cycle (target is the dragged item
        itself or one of its descendants). Qt ignores such drops and never delivers the Drop event,
        so this is used to force-accept the DragMove so the Drop reaches item_moved_update_data,
        which shows the cycle message. """

        d = dragged.text(1)
        t = target.text(1)
        try:
            if d[0:3] == 'cid' and t[0:4] == 'cid:':
                return self.code_tree.code_is_descendant(int(t.split(':')[1]), int(d.split(':')[1]))
            if d[0:3] == 'cat' and t[0:6] == 'catid:':
                return self.code_tree.category_is_descendant(int(t.split(':')[1]), int(d.split(':')[1]))
        except (ValueError, IndexError):
            return False
        return False

    def update_dialog_codes_and_categories(self, tables=None):
        """        Refresh this dialog after code/category changes and notify the rest of the dialogs via the project's event bus.
        Args:
            tables : list of changed tables to emit, [] for local refresh only.
        """

        try:
            # The dialog may have been destroyed (e.g., tab reconstructed
            # with an open memo dialog on top). In that case, the local
            # refresh is skipped but notification is still sent via the bus.
            self.ui.treeWidget.objectName()
            dialog_alive = True
        except RuntimeError:
            dialog_alive = False
        if dialog_alive:
            self.get_codes_and_categories()
            self.code_tree.fill_tree()
            self.get_coded_text_update_eventfilter_tooltips()
        if getattr(self.app, "project_events", None) is not None:
            self.app.project_events.emit_table_changes(tables, source=self)

    def _on_project_data_changed(self, tables, source):
        """        Handles change events emitted by other dialogs.
        Args:
            tables : changed tables.
            source : emitter; ignored when it is this same dialog.
        """

        try:
            # Ignore events delivered to a destroyed dialog
            self.ui.treeWidget.objectName()
        except RuntimeError:
            return
        if source is self or not isinstance(tables, list):
            return
        tables = set(tables)
        # Attributes changed in another dialog: recompute the active filter. Port of upstream 0ce9817
        if ("attribute" in tables or "attribute_type" in tables) and len(self.attributes) > 1:
            self.get_files_from_attributes(refresh_only=True)
        code_tree_changed = "code_cat" in tables or "code_name" in tables
        if code_tree_changed:
            self.get_codes_and_categories()
            self.code_tree.fill_tree()
            self.get_coded_text_update_eventfilter_tooltips()
            return
        # Fulltext changed elsewhere (a layout restructuring, or a text file edited in
        # another dialog): reloading the current file re-verifies the page mapping
        # (extracted_ok) and refreshes text, codings and margins; without this the
        # dialog keeps stale positions.
        if "source" in tables and self.file_ is not None:
            self.load_file(self.file_)
            return
        if ("code_text" in tables or "code_image" in tables) and self.file_ is not None:
            self.get_coded_text_update_eventfilter_tooltips()
            self.fill_code_counts_in_tree()

    # Drag y drop, cierre. Drag and drop, close
    def eventFilter(self, object_, event):
        """        Drop in the tree viewport: move or nest codes and categories.
        """

        if object_ is self.ui.treeWidget.viewport():
            # Dropping an item onto its own subtree: Qt ignores that DragMove and never delivers
            # the Drop, so item_moved_update_data's cycle guard never runs. We force it to be
            # accepted so the Drop arrives and the message is shown.
            if event.type() == QtCore.QEvent.Type.DragMove:
                arrastrado = self.ui.treeWidget.currentItem()
                destino = self.ui.treeWidget.itemAt(event.position().toPoint())
                if arrastrado is not None and destino is not None and \
                        self._drop_would_cycle(arrastrado, destino):
                    event.setDropAction(Qt.DropAction.MoveAction)
                    event.accept()
                    return True
            elif event.type() == QtCore.QEvent.Type.Drop:
                item = self.ui.treeWidget.currentItem()
                if item is None:  # Fallback to first selected item.
                    seleccionados = self.ui.treeWidget.selectedItems()
                    if seleccionados:
                        item = seleccionados[0]
                parent = self.ui.treeWidget.itemAt(event.position().toPoint())
                if item is not None:
                    self.code_tree.item_moved_update_data(item, parent)
                    return True
        return super().eventFilter(object_, event)

    # Filter unification (dialog and real-time in a single method)
    def show_codes_like(self, filter_text=None):
        """        Filters the code tree by name.
        If filter_text is None or bool (comes from the menu), it opens a dialog.
        If it is a string (comes from the lineEdit textEdited), it applies it live.
        """
        if filter_text is None or isinstance(filter_text, bool):
            dialog = QtWidgets.QInputDialog(None)
            dialog.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
            dialog.setWindowTitle(_("Show codes"))
            dialog.setLabelText(_("Show codes containing the text. (Blank for all)"))
            if not dialog.exec():
                return
            text_ = str(dialog.textValue())
            
            # Synchronize the lineEdit for visual consistency.
            self.ui.lineEdit_code_filter.blockSignals(True)
            self.ui.lineEdit_code_filter.setText(text_)
            self.ui.lineEdit_code_filter.blockSignals(False)
        else:
            text_ = str(filter_text)
            
        case_sensitive = False 
        root = self.ui.treeWidget.invisibleRootItem()
        self.recursive_traverse(root, text_, case_sensitive)
        
        active = bool(text_)
        self.ui.pushButton_clear_filter_code.setVisible(active)
        if active:
            self.ui.pushButton_clear_filter_code.setStyleSheet("background-color: #1e90ff; color: white;")
        else:
            self.ui.pushButton_clear_filter_code.setStyleSheet("")

    def show_codes_of_color(self):
        """        Filters the code tree by color range.
        """
        from .color_selector import colour_ranges, show_codes_of_colour_range
        ui = DialogSelectItems(self.app, colour_ranges, _("Select code colors"), "single")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        if not selected:
            return
        show_codes_of_colour_range(self.app, self.ui.treeWidget, self.codes, selected)
        self.ui.pushButton_clear_filter_code.setVisible(True)
        self.ui.pushButton_clear_filter_code.setStyleSheet("background-color: #1e90ff; color: white;")

    # Implementación centralizada. Centralized implementation
    def clear_code_filter(self):
        """        Clears the filter and shows the entire tree.
        """
        self.ui.lineEdit_code_filter.setText("")
        root = self.ui.treeWidget.invisibleRootItem()
        self.recursive_traverse(root, "")
        self.ui.pushButton_clear_filter_code.setVisible(False)
        self.ui.pushButton_clear_filter_code.setStyleSheet("")

    def closeEvent(self, event):
        """        Stops the rendering and extraction threads on close.
        """

        self.stop_workers()
        event.accept()

    # Buttons below the file list
    def go_to_next_file(self):
        """        Opens the next file in the list.
        """

        if not self.files:
            return
        if self.file_ is None:
            self.ui.listWidget.setCurrentRow(0)
            return
        for i in range(0, len(self.files) - 1):
            if self.file_['id'] == self.files[i]['id']:
                self.ui.listWidget.setCurrentRow(i + 1)
                return

    def go_to_latest_coded_file(self):
        """        Opens the PDF with the most recent coding (text or area).
        """

        sql = ("select fid from ("
               "select code_text_visible.fid as fid, code_text_visible.date as date "
               "from code_text_visible join source on source.id=code_text_visible.fid "
               "where lower(source.mediapath) like '%.pdf' "
               "union all "
               "select code_image_visible.id as fid, code_image_visible.date as date "
               "from code_image_visible join source on source.id=code_image_visible.id "
               "where lower(source.mediapath) like '%.pdf' and code_image_visible.pdf_page is not null"
               ") order by date desc limit 1")
        cur = self.app.conn.cursor()
        cur.execute(sql)
        result = cur.fetchone()
        if result is None:
            return
        for i, filedata in enumerate(self.files):
            if filedata['id'] == result[0]:
                self.ui.listWidget.setCurrentRow(i)
                break

    def get_files_from_attributes(self, refresh_only: bool = False):
        """        Filters the file list by attributes.
        The result of the dialog is: first item boolean AND/OR and then each attribute.
        Args:
            refresh_only: Recompute an already active attribute filter without reopening
                the selection dialog, when another dialog changes attributes. Port of
                upstream 0ce9817.
        """

        if refresh_only and len(self.attributes) <= 1:
            return
        self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
        ui = DialogSelectAttributeParameters(self.app)
        previous_attributes = deepcopy(self.attributes)
        ui.fill_parameters(deepcopy(self.attributes))  # copy: the dialog must not mutate the state
        temp_attributes = deepcopy(self.attributes)
        if refresh_only:  # Recompute without opening the dialog
            ui.make_parameter_list()
            ui.get_results_case_ids()
            ui.get_results_file_ids()
            ui.get_results_message()
        else:
            self.attributes = []
            ok = ui.exec()
            if not ok:
                self.attributes = temp_attributes
                try:
                    self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable', options=[{'scale_factor': 1.3}]))
                    if self.attributes:
                        self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable-box', options=[{'scale_factor': 1.3}]))
                except Exception:
                    pass
                self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
                return
        self.attributes = ui.parameters
        if len(self.attributes) == 1:  # Only the boolean, without attributes.
            if refresh_only and len(previous_attributes) > 1:  # The active filter became empty
                self.clear_file_filter()
                return
            try:
                self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable', options=[{'scale_factor': 1.3}]))
            except Exception:
                pass
            self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
            self.clear_file_filter()
            return
        if not ui.result_file_ids:
            if not refresh_only:
                Message(self.app, _("Nothing found") + " " * 20, _("No matching files found")).exec()
                try:
                    self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable', options=[{'scale_factor': 1.3}]))
                except Exception:
                    pass
                self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
                return  # It used to fall through; the flow is explicit now
            # refresh_only: the active filter no longer matches any file, empty the list
            self.stop_workers()
            self.ui.listWidget.blockSignals(True)
            self.ui.listWidget.clear()
            self.ui.listWidget.blockSignals(False)
            self.files = []
            self.file_ = None
            self._clear_loaded_state()
            try:
                self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable-box', options=[{'scale_factor': 1.3}]))
            except Exception:
                pass
            self.ui.pushButton_file_attributes.setToolTip(ui.tooltip_msg)
            self.ui.pushButton_clear_filter_file.setVisible(True)
            self.ui.pushButton_clear_filter_file.setStyleSheet("background-color: #1e90ff; color: white;")
            return
            return
        try:
            self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable-box', options=[{'scale_factor': 1.3}]))
        except Exception:
            pass
        self.ui.pushButton_file_attributes.setToolTip(ui.tooltip_msg)
        self.get_files(ui.result_file_ids, preserve_current_file=True)  # Keeps the open file
        self.ui.pushButton_clear_filter_file.setVisible(True)
        self.ui.pushButton_clear_filter_file.setStyleSheet("background-color: #1e90ff; color: white;")

    def clear_file_filter(self):
        """
        Clears the file filter and reloads the complete list.
        """

        self.attributes = []
        try:
            self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable', options=[{'scale_factor': 1.3}]))
        except Exception:
            pass
        self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
        self.get_files()
        self.ui.pushButton_clear_filter_file.setVisible(False)
        self.ui.pushButton_clear_filter_file.setStyleSheet("")

    # Buttons below the code tree.
    def find_code_in_tree(self):
        """
        Searches for a code by name in the tree and selects it.
        """

        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
        dialog.setWindowTitle(_("Search for code"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        msg = _("Find and select first code that matches text.") + "\n"
        msg += _("Enter text to match all or partial code:")
        dialog.setLabelText(msg)
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        search_text = dialog.textValue()
        # Clear selection and gather matches.
        self.ui.treeWidget.setCurrentItem(None)
        self.ui.treeWidget.clearSelection()
        matches = []
        iterator = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        while iterator.value():
            item = iterator.value()
            if "cid" in item.text(1):
                cid = int(item.text(1)[4:])
                code_ = next((c for c in self.codes if c['cid'] == cid), None)
                if code_ is not None and search_text in code_['name']:
                    matches.append(code_)
            iterator += 1
        if not matches:
            Message(self.app, _("Match not found"), _("No code with matching text found.")).exec()
            return
        # Choose one if there are multiple matches.
        if len(matches) > 1:
            ui = DialogSelectItems(self.app, matches, _("Select code"), "single")
            ok = ui.exec()
            if not ok:
                return
            selected = ui.get_selected()
            if not selected:
                return
        else:
            selected = matches[0]
        # Select in the tree and expand parents.
        item = None
        iterator = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        while iterator.value():
            item = iterator.value()
            if "cid" in item.text(1) and int(item.text(1)[4:]) == selected['cid']:
                self.ui.treeWidget.setCurrentItem(item)
                break
            iterator += 1
        if item is not None:
            parent = item.parent()
            while parent is not None:
                parent.setExpanded(True)
                parent = parent.parent()
        self.fill_code_label()

    def recursive_traverse(self, item, text_="", case_sensitive=False):
        """
        Hide or show child codes depending on whether they match 'text'. Recurse through
        categories and sub-codes: a code stays visible if it matches or if any of its descendant
        sub-codes matches, so a match is never hidden under a non-matching parent code. Categories
        are not hidden (same as the canonical module). Returns True if this item or any descendant matches.
        Called by: show_codes_like
        """

        child_count = item.childCount()
        any_visible_descendant = False
        for i in range(child_count):
            child = item.child(i)
            is_code = "cid:" in child.text(1)
            # Recurse first so we know whether any descendant matches.
            descendant_match = self.recursive_traverse(child, text_, case_sensitive)
            if text_ == "":
                if is_code:
                    child.setHidden(False)
                any_visible_descendant = True
                continue
            self_match = False
            if is_code:
                cid = int(child.text(1)[4:])
                c = next((cc for cc in self.codes if cc['cid'] == cid), None)
                if c is not None:
                    if case_sensitive:
                        self_match = text_ in c['name']
                    else:
                        self_match = text_.lower() in c['name'].lower()
            visible = self_match or descendant_match
            if is_code:
                child.setHidden(not visible)
            if visible:
                any_visible_descendant = True
        return any_visible_descendant

    def _coding_targets(self):
        """
        Navigable codings of the file in reading order.
        If a code is selected in the tree, navigates only its codings.
        """

        targets = []
        cid_filter = self._current_tree_cid()
        if self.pages and self.extracted_ok:
            for coding in self.code_text:
                if cid_filter is not None and coding['cid'] != cid_filter:
                    continue
                pages = self._pages_spanning(coding['pos0'], coding['pos1'])
                if not pages or pages[0] >= len(self.view.items_):
                    continue
                page_idx = pages[0]
                rects = self.rects_for_range(page_idx, coding['pos0'], coding['pos1'])
                if not rects:
                    continue
                scene_rect = self.view.items_[page_idx].mapRectToScene(rects[0])
                targets.append((page_idx, scene_rect.y(), scene_rect))
        for area in self.code_areas:
            if cid_filter is not None and area['cid'] != cid_filter:
                continue
            page_idx = area['pdf_page']
            if page_idx is None or page_idx >= len(self.view.items_):
                continue
            rect = QtCore.QRectF(area['x1'], area['y1'], area['width'], area['height'])
            scene_rect = self.view.items_[page_idx].mapRectToScene(rect)
            targets.append((page_idx, scene_rect.y(), scene_rect))
        targets.sort(key=lambda t: (t[0], t[1]))
        return targets

    def show_next_coding(self):
        """
        Scrolls the viewport to the next coding.
        """

        targets = self._coding_targets()
        if not targets:
            return
        self._coding_nav_idx = (self._coding_nav_idx + 1) % len(targets)
        self.view.scroll_to_scene_rect(targets[self._coding_nav_idx][2])

    def show_previous_coding(self):
        """        Scrolls the viewport to the previous coding.
        """

        targets = self._coding_targets()
        if not targets:
            return
        self._coding_nav_idx = (self._coding_nav_idx - 1) % len(targets)
        self.view.scroll_to_scene_rect(targets[self._coding_nav_idx][2])

    # Bookmark: go to the saved position (key B saves it).
    def go_to_bookmark(self):
        """
        Reads the project bookmark (file + position) and jumps to it. If the bookmark is in a
        different file from the list, it loads that file and applies the jump once its text is ready.
        """

        cur = self.app.conn.cursor()
        cur.execute("select bookmarkfile, bookmarkpos from project")
        row = cur.fetchone()
        if not row or not row[0]:
            Message(self.app, _("Bookmark"), _("No bookmark has been set.")).exec()
            return
        bm_fid = int(row[0])
        bm_pos = int(row[1] or 0)
        target_row = next((i for i, f in enumerate(self.files) if int(f['id']) == bm_fid), -1)
        if target_row == -1:
            Message(self.app, _("Bookmark"),
                    _("The bookmarked file is not in this PDF list.")).exec()
            return
        self._pending_bookmark_pos = bm_pos
        if self.file_ is not None and int(self.file_['id']) == bm_fid:
            # Already the current file.
            if self.pages:
                self._apply_pending_bookmark()
            # If still extracting, on_text_ready will apply it.
        else:
            # Load the bookmarked file.
            if self.ui.listWidget.currentRow() == target_row:
                # Same row emits no signal: load directly.
                self.load_file(self.files[target_row])
            else:
                self.ui.listWidget.setCurrentRow(target_row)

    def open_doc_selection(self, doc_id, sel_start=0, sel_end=0):
        """
        Opens the given document and, once its text is ready, highlights and reveals
        the range [sel_start, sel_end). Signature equivalent to code_text's, so
        __main__ can redirect PDF references here (mark speakers from Manage files,
        AI chat references, qualcoder:// links).

        Args:
            doc_id: source id, Integer
            sel_start: selection start character position, Integer
            sel_end: selection end character position, Integer
        """

        target_row = next((i for i, f in enumerate(self.files) if int(f['id']) == int(doc_id)), -1)
        if target_row == -1:
            Message(self.app, _("PDF file"),
                    _("The file is not in this PDF list.")).exec()
            return
        self._pending_selection = (int(sel_start), int(sel_end)) if sel_end > sel_start else None
        if self.file_ is not None and int(self.file_['id']) == int(doc_id):
            # Already the current file.
            if self.pages:
                self._apply_pending_selection()
            # If still extracting, on_text_ready will apply it.
        else:
            if self.ui.listWidget.currentRow() == target_row:
                # Same row emits no signal: load directly.
                self.load_file(self.files[target_row])
            else:
                self.ui.listWidget.setCurrentRow(target_row)

    def _apply_pending_selection(self):
        """
        If a range is pending for the already-loaded file, highlights it (only when the
        text matches the DB) and scrolls the viewer to it (to the rect when reliable,
        or to the page as a fallback).
        """

        sel = self._pending_selection
        if sel is None or self.file_ is None:
            return
        self._pending_selection = None
        pos0 = max(0, sel[0] - self.file_.get('start', 0))
        pos1 = max(pos0 + 1, sel[1] - self.file_.get('start', 0))
        pages = self._pages_spanning(pos0, pos1)
        if not pages or pages[0] >= len(self.view.items_):
            return
        page_idx = pages[0]
        rects = []
        if self.extracted_ok:
            self.set_selection(pos0, pos1)
            rects = self.rects_for_range(page_idx, pos0, pos1)
        if rects:
            scene_rect = self.view.items_[page_idx].mapRectToScene(rects[0])
            self.view.scroll_to_scene_rect(scene_rect)
        else:
            self.view.goto_page(page_idx)

    def _apply_pending_bookmark(self):
        """
        If a bookmark is pending for the already-loaded file, scrolls the viewer to its position
        (to the word rect when text is reliable, or to the page as a fallback).
        """

        pos = self._pending_bookmark_pos
        if pos is None or self.file_ is None:
            return
        self._pending_bookmark_pos = None
        pos_in_file = max(0, pos - self.file_.get('start', 0))
        pages = self._pages_spanning(pos_in_file, pos_in_file + 1)
        if not pages or pages[0] >= len(self.view.items_):
            return
        page_idx = pages[0]
        rects = self.rects_for_range(page_idx, pos_in_file, pos_in_file + 1) if self.extracted_ok else []
        if rects:
            scene_rect = self.view.items_[page_idx].mapRectToScene(rects[0])
            self.view.scroll_to_scene_rect(scene_rect)
        else:
            self.view.goto_page(page_idx)

    # Code margin (shared with code_text)
    def _build_code_tooltip_html(self, code):
        """
        HTML tooltip of a coded segment (text or image area).
        """

        is_area = 'pos0' not in code  # las areas no tienen pos0. Areas have no pos0
        color = TextColor(code.get('color', '#cccccc')).recommendation
        text_ = '<p style="background-color:' + code.get('color', '#cccccc') + "; color:" + color + '"><em>'
        text_ += code.get('name', '') + "</em>"
        if self.app.settings['showids']:
            if is_area:
                text_ += " [imid:" + str(code.get('imid', '')) + "]"
            else:
                text_ += " [ctid:" + str(code.get('ctid', '')) + "]"
        text_ += " (" + str(code.get('owner', '')) + ")"
        if is_area:
            page_no = (code.get('pdf_page', 0) or 0) + 1
            text_ += "<br />" + _("Coded area") + " - " + _("Page") + " " + str(page_no)
        else:
            seltext = code.get('seltext', '') or ''
            seltext = seltext.replace("\n", "").replace("\r", "")
            if len(seltext) > 90:
                pre = seltext[0:40].split(' ')
                post = seltext[len(seltext) - 40:].split(' ')
                try:
                    pre = pre[:-1]
                except IndexError:
                    pass
                try:
                    post = post[1:]
                except IndexError:
                    pass
                seltext = " ".join(pre) + " ... " + " ".join(post)
            text_ += "<br />" + seltext
        if code.get('memo', '') != "":
            memo_text = code['memo']
            if len(memo_text) > 150:
                memo_text = memo_text[:150] + "..."
            text_ += "<br /><em>" + _("MEMO: ") + memo_text + "</em>"
        if code.get('important') == 1:
            text_ += "<br /><em>" + _("IMPORTANT") + "</em>"
        text_ += "</p>"
        return text_

    def _install_coding_margin_in_side(self, side):
        """
        Moves the margin widget to the left or right container.
        """

        if side not in ('left', 'right'):
            side = 'left'
        for lay in (self._coding_margin_layout_left, self._coding_margin_layout_right):
            if lay is None:
                continue
            idx = lay.indexOf(self.coding_margin)
            if idx >= 0:
                lay.takeAt(idx)
        if side == 'right':
            self._coding_margin_layout_right.addWidget(self.coding_margin)
        else:
            self._coding_margin_layout_left.addWidget(self.coding_margin)
        self.margin_side = side
        self.coding_margin.side = side

    def _sync_coding_margin_background(self):
        """Keep the coding margin area aligned with the PDF viewer background."""

        viewer_palette = self.view.viewport().palette()
        background_color = viewer_palette.color(QtGui.QPalette.ColorRole.Base)
        background_hex = background_color.name()
        for widget in (
                self.ui.widget_code_margin_left,
                self.ui.widget_code_margin_right,
                self.coding_margin):
            palette = widget.palette()
            palette.setColor(QtGui.QPalette.ColorRole.Window, background_color)
            palette.setColor(QtGui.QPalette.ColorRole.Base, background_color)
            widget.setPalette(palette)
            widget.setAutoFillBackground(True)
        self._pdf_margins_splitter.setStyleSheet(
            "QSplitter::handle {"
            f" background-color: {background_hex};"
            " border: 0px;"
            " margin: 0px;"
            " padding: 0px;"
            "}"
        )
        self.coding_margin.update()

    def _get_saved_coding_margin_width(self) -> int:
        """Return the stored coding margin width, or the default width."""

        try:
            width = int(self.app.settings.get('dialogcodepdf_coding_margin_width',
                                              DEFAULT_PDF_CODING_MARGIN_WIDTH))
        except (TypeError, ValueError, AttributeError):
            width = DEFAULT_PDF_CODING_MARGIN_WIDTH
        if width <= 0:
            return DEFAULT_PDF_CODING_MARGIN_WIDTH
        return max(MINIMUM_PDF_CODING_MARGIN_WIDTH, width)

    def _apply_coding_margin_width(self):
        """Apply the stored coding margin width to the active side of the splitter."""

        if not hasattr(self, '_pdf_margins_splitter') or self._pdf_margins_splitter is None:
            return
        if not self.show_margin_stripes:
            return
        total_width = self._pdf_margins_splitter.width()
        if total_width <= 0:
            sizes = self._pdf_margins_splitter.sizes()
            total_width = sum(sizes)
        if total_width <= 0 or total_width < self.coding_margin_width + 200:
            if self._coding_margin_restore_attempts < 20:
                self._coding_margin_restore_attempts += 1
                QtCore.QTimer.singleShot(30, self._apply_coding_margin_width)
            return
        self._coding_margin_restore_attempts = 0
        margin_width = min(self.coding_margin_width,
                           max(MINIMUM_PDF_CODING_MARGIN_WIDTH, total_width - 200))
        viewer_width = max(200, total_width - margin_width)
        if self.margin_side == 'right':
            sizes = [0, viewer_width, margin_width]
        else:
            sizes = [margin_width, viewer_width, 0]
        self._coding_margin_width_is_restoring = True
        try:
            with QtCore.QSignalBlocker(self._pdf_margins_splitter):
                self._pdf_margins_splitter.setSizes(sizes)
        finally:
            self._coding_margin_width_is_restoring = False
        self._coding_margin_width_ready = True

    def on_coding_margin_splitter_moved(self, pos=None, index=None):
        """Track coding margin width changes and persist the active width."""

        if self._coding_margin_width_is_restoring or not self.show_margin_stripes:
            return
        if not self._coding_margin_width_ready:
            return
        sizes = self._pdf_margins_splitter.sizes()
        if len(sizes) < 3:
            return
        width = sizes[2] if self.margin_side == 'right' else sizes[0]
        width = int(width)
        if width < MINIMUM_PDF_CODING_MARGIN_WIDTH:
            return
        self.coding_margin_width = width
        self.app.settings['dialogcodepdf_coding_margin_width'] = width
        self.coding_margin_width_save_timer.start(400)

    def persist_coding_margin_width_setting(self):
        """Write the coding margin width to config.ini after drag operations settle."""

        try:
            self.app.write_config_ini(self.app.settings, self.app.ai_models)
        except Exception as e_:
            logger.debug(f"Could not persist coding margin width setting: {e_}")

    def _set_margin_container_visibility(self, visible):
        """
        Shows or hides the active container so that the layout recovers the space
        when the margin is turned off.
        """

        if self.margin_side == 'right':
            self.ui.widget_code_margin_right.setVisible(visible)
            self.ui.widget_code_margin_left.setVisible(False)
        else:
            self.ui.widget_code_margin_left.setVisible(visible)
            self.ui.widget_code_margin_right.setVisible(False)

    def coding_margin_context_menu(self, position, source_widget):
        """
        Right-click on the margin: if it falls on a stripe or name,
        code actions; otherwise, margin configuration (visibility,
        side, and highlight style), same as code_text.
        """

        clicked_code = None
        if isinstance(source_widget, PdfCodingMargin):
            try:
                clicked_code = source_widget._code_at_position(position)
            except Exception as err:
                logger.debug(f"Margen menu hit-test: {err}")
                clicked_code = None
        if clicked_code is not None and self.file_ is not None:
            self._coding_margin_code_actions_menu(clicked_code, source_widget, position)
            return

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        if self.show_margin_stripes:
            action_visibility = menu.addAction(_("Hide code stripes margin"))
        else:
            action_visibility = menu.addAction(_("Show code stripes margin"))
        menu.addSeparator()
        action_move_left = None
        action_move_right = None
        if self.margin_side == 'right':
            action_move_left = menu.addAction(_("Move margin to the left"))
        else:
            action_move_right = menu.addAction(_("Move margin to the right"))
        menu.addSeparator()
        style_menu = menu.addMenu(_("Highlight style"))
        action_style_marker = None
        action_style_underline = None
        if self.highlight_style != 'marker':
            action_style_marker = style_menu.addAction(_("Marker"))
        if self.highlight_style != 'underline':
            action_style_underline = style_menu.addAction(_("Underline"))
        global_pos = source_widget.mapToGlobal(position)
        action = menu.exec(global_pos)
        if action is None:
            return
        if action == action_visibility:
            self._toggle_margin_visibility_only()
            return
        if action == action_move_left:
            self._set_margin_side('left')
            return
        if action == action_move_right:
            self._set_margin_side('right')
            return
        if action == action_style_marker:
            self._set_highlight_style('marker')
            return
        if action == action_style_underline:
            self._set_highlight_style('underline')

    def _coding_margin_code_actions_menu(self, code, source_widget, position):
        """
        Actions on the exact segment clicked in the margin, without prompting
        again with DialogSelectItems even if there are overlaps. Distinguishes
        text codings from image areas: each is routed to its variant
        (unmark/coded_memo/toggle_important accept texts and areas; area resize
        uses the viewer's interactive resize).
        """

        if code is None or self.file_ is None:
            return
        is_area = 'pos0' not in code  # las areas no tienen pos0. Areas have no pos0
        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        action_unmark = menu.addAction(_("Unmark (U)"))
        memo_label = _("Memo coded area") if is_area else _("Memo coded text (M)")
        action_code_memo = menu.addAction(memo_label)
        action_resize = menu.addAction(_("Resize"))
        action_important = menu.addAction(_("Toggle important"))
        # Change the segment's code (text or area) and annotate (text only),
        # like the viewer menu.
        action_change_code = menu.addAction(_("Change code"))
        action_annotate = None
        if not is_area:
            action_annotate = menu.addAction(_("Annotate"))
        global_pos = source_widget.mapToGlobal(position)
        action = menu.exec(global_pos)
        if action is None:
            return
        if is_area:
            target = next((a for a in self.code_areas if a.get('imid') == code.get('imid')), code)
            if action == action_unmark:
                self.unmark([], [target])
                return
            if action == action_code_memo:
                self.coded_memo([], [target])
                return
            if action == action_resize:
                self.start_interactive_area_resize(target)
                return
            if action == action_change_code:
                self.change_code_for_segment(area_item=target)
                return
            if action == action_important:
                self.toggle_important([], [target])
            return
        target = next((c for c in self.code_text if c.get('ctid') == code.get('ctid')), code)
        if action == action_unmark:
            self.unmark([target], [])
            return
        if action == action_code_memo:
            self.coded_memo([target], [])
            return
        if action == action_resize:
            self.show_resize_handles(target)
            return
        if action == action_change_code:
            self.change_code_for_segment(text_item=target)
            return
        if action == action_annotate:
            self.annotate(pos0=target['pos0'], pos1=target['pos1'])
            return
        if action == action_important:
            self.toggle_important([target], [])

    def _toggle_margin_visibility_only(self):
        """
        Toggles ONLY the margin visibility (does not touch highlight_style)
        and persists the shared preference.
        """

        self.show_margin_stripes = not self.show_margin_stripes
        try:
            self.app.settings['codetext_show_margin_stripes'] = (
                'True' if self.show_margin_stripes else 'False')
        except (TypeError, AttributeError):
            pass
        if getattr(self, 'coding_margin', None) is not None:
            self.coding_margin.setVisible(self.show_margin_stripes)
        self._set_margin_container_visibility(self.show_margin_stripes)
        if self.show_margin_stripes:
            self._apply_coding_margin_width()
        if getattr(self, 'coding_margin', None) is not None:
            self.coding_margin.update()

    def _set_margin_side(self, side):
        """
        Moves the margin to the requested side and persists the preference.
        """

        if side not in ('left', 'right') or side == self.margin_side:
            return
        self._install_coding_margin_in_side(side)
        try:
            self.app.settings['codetext_margin_side'] = side
        except (TypeError, AttributeError):
            pass
        self._set_margin_container_visibility(self.show_margin_stripes)
        if self.show_margin_stripes:
            self._apply_coding_margin_width()
        if getattr(self, 'coding_margin', None) is not None:
            self.coding_margin.update()

    def _set_highlight_style(self, style):
        """
        Changes the highlight style between 'marker' and 'underline',
        persists the shared preference and repaints the layers.
        """

        if style not in ('marker', 'underline') or style == self.highlight_style:
            return
        self.highlight_style = style
        try:
            self.app.settings['codetext_highlight_style'] = style
        except (TypeError, AttributeError):
            pass
        self.rebuild_marks()

    # Resizing of codings (text and areas)
    def _select_single(self, entries, title):
        """
        Returns the chosen 'ref' when there are multiple options (name only), or the only one directly.
        """

        if not entries:
            return None
        if len(entries) == 1:
            return entries[0]['ref']
        ui = DialogSelectItems(self.app, entries, title, "single")
        ok = ui.exec()
        if not ok:
            return None
        selected = ui.get_selected()
        if not selected:
            return None
        return selected['ref']

    def _text_handle_anchor(self, code_item, is_start):
        """
        Viewport point (word edge, bottom of the line) where to anchor the
        tip of the teardrop, or None if it is not projectable.
        """

        if not (self.pages and self.extracted_ok and self.view.items_):
            return None
        pages = self._pages_spanning(code_item['pos0'], code_item['pos1'])
        if not pages:
            return None
        page_idx = pages[0] if is_start else pages[-1]
        if page_idx >= len(self.view.items_):
            return None
        rects = self.rects_for_range(page_idx, code_item['pos0'], code_item['pos1'])
        if not rects:
            return None
        if is_start:
            rect = rects[0]
            point = QtCore.QPointF(rect.left(), rect.bottom())
        else:
            rect = rects[-1]
            point = QtCore.QPointF(rect.right(), rect.bottom())
        item = self.view.items_[page_idx]
        return self.view.mapFromScene(item.mapToScene(point))

    def show_resize_handles(self, code_item):
        """
        Creates the two teardrops (start and end) for the exact segment,
        like _margin_resize_ctid of code_text.
        """

        if code_item is None or code_item.get('ctid') is None:
            return
        if not self.text_ready():
            Message(self.app, _("Warning"),
                    _("Text coding is disabled for this file."), "warning").exec()
            return
        self.cancel_interactive_area_resize()
        self.hide_resize_handles()
        target = next((c for c in self.code_text if c.get('ctid') == code_item['ctid']), None)
        if target is None:
            return
        anchor_start = self._text_handle_anchor(target, True)
        anchor_end = self._text_handle_anchor(target, False)
        if anchor_start is None or anchor_end is None:
            return
        h_start = PdfResizeHandle(self.view, True, target, self)
        # The tip of the start teardrop is at its top right corner.
        h_start.move(anchor_start.x() - h_start.width(), anchor_start.y())
        self.active_handles.append(h_start)
        h_end = PdfResizeHandle(self.view, False, target, self)
        # The tip of the end teardrop is at its top left corner.
        h_end.move(anchor_end.x(), anchor_end.y())
        self.active_handles.append(h_end)

    def hide_resize_handles(self):
        """
        Removes all active resize handles.
        """

        for h in getattr(self, 'active_handles', []):
            h.hide()
            h.deleteLater()
        self.active_handles = []

    def reposition_resize_handles(self):
        """
        Relocates the teardrops after scroll, zoom, or position changes.
        If the segment no longer exists or the text is no longer available, they are hidden.
        """

        if not self.active_handles:
            return
        if not self.text_ready():
            self.hide_resize_handles()
            return
        for h in list(self.active_handles):
            if next((c for c in self.code_text
                     if c.get('ctid') == h.code_item.get('ctid')), None) is None \
                    and h.code_item not in self.code_text:
                self.hide_resize_handles()
                return
            anchor = self._text_handle_anchor(h.code_item, h.is_start)
            if anchor is None:
                continue
            if h.is_start:
                h.move(anchor.x() - h.width(), anchor.y())
            else:
                h.move(anchor.x(), anchor.y())
            h.raise_()

    def update_code_position_from_handle(self, code_item, new_pos, is_start, orig_pos0, orig_pos1):
        """
        Receives the final position of the teardrop and updates the database.
        Ported from code_text (same validations and revert).
        """

        if is_start:
            if new_pos >= code_item['pos1']:
                code_item['pos0'] = orig_pos0  # Revertir visualmente. Revert visually.
                self.hide_resize_handles()
                self.rebuild_marks()
                return
            code_item['pos0'] = new_pos
        else:
            if new_pos <= code_item['pos0']:
                code_item['pos1'] = orig_pos1  # Revertir visualmente. Revert visually.
                self.hide_resize_handles()
                self.rebuild_marks()
                return
            code_item['pos1'] = new_pos
        cur = self.app.conn.cursor()
        cur.execute("select substr(fulltext,?,?) from source where id=?",
                    [code_item['pos0'] + 1, code_item['pos1'] - code_item['pos0'], code_item['fid']])
        res = cur.fetchone()
        if not res:
            code_item['pos0'] = orig_pos0
            code_item['pos1'] = orig_pos1
            self.hide_resize_handles()
            self.rebuild_marks()
            return
        seltext = res[0]
        try:
            cur.execute("update code_text set pos0=?, pos1=?, seltext=? where ctid=?",
                        [code_item['pos0'], code_item['pos1'], seltext, code_item['ctid']])
            self.app.conn.commit()
            if getattr(self.app, "project_events", None) is not None:
                self.app.project_events.emit_table_changes(['code_text'], source=self)
            self.app.delete_backup = False
        except sqlite3.IntegrityError:
            self.app.conn.rollback()
            code_item['pos0'] = orig_pos0
            code_item['pos1'] = orig_pos1
            self.hide_resize_handles()
            self.rebuild_marks()
            return
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        # Rebind the handles to the reloaded dict and relocate them.
        for h in self.active_handles:
            refreshed = next((c for c in self.code_text
                              if c.get('ctid') == code_item['ctid']), None)
            if refreshed is not None:
                h.code_item = refreshed
                h.orig_pos0 = refreshed['pos0']
                h.orig_pos1 = refreshed['pos1']
        self.reposition_resize_handles()

    def _area_handle_rects(self, area):
        """
        Rects (page coordinates) of the 4 corner handles, with
        a constant screen size (~12 px) independent of zoom.
        """

        s = 12.0 / max(self.view.zoom, 0.05)
        x, y = float(area['x1']), float(area['y1'])
        w, h = float(area['width']), float(area['height'])
        return {'TL': QtCore.QRectF(x, y, s, s),
                'TR': QtCore.QRectF(x + w - s, y, s, s),
                'BL': QtCore.QRectF(x, y + h - s, s, s),
                'BR': QtCore.QRectF(x + w - s, y + h - s, s, s)}

    def start_interactive_area_resize(self, area):
        """
        Activates interactive area resizing (red corner handles, like view_image).
        """

        self.hide_resize_handles()
        target = next((a for a in self.code_areas if a['imid'] == area['imid']), None)
        if target is None:
            return
        self.area_to_resize = target
        page_idx = target['pdf_page']
        if page_idx is not None and page_idx < len(self.view.items_):
            self.view.items_[page_idx].update()

    def cancel_interactive_area_resize(self):
        """
        Deactivates interactive area resizing without saving.
        """

        if self.area_to_resize is None:
            return
        page_idx = self.area_to_resize.get('pdf_page')
        # Restore values from the database in case of an incomplete drag.
        self.area_to_resize = None
        self.view._area_resize = None
        self.get_coded_text_update_eventfilter_tooltips()
        if page_idx is not None and page_idx < len(self.view.items_):
            self.view.items_[page_idx].update()

    def commit_area_resize(self):
        """
        Saves the final size of the resized area to the database,
        with the same validations as view_image.
        """

        area = self.area_to_resize
        if area is None:
            return
        page_idx = area['pdf_page']
        page_w, page_h = self.view.page_sizes[page_idx] if page_idx < len(self.view.page_sizes) \
            else (None, None)
        x = max(0, int(round(area['x1'])))
        y = max(0, int(round(area['y1'])))
        w = max(5, int(round(area['width'])))
        h = max(5, int(round(area['height'])))
        if page_w is not None:
            if x + w > page_w:
                w = int(page_w) - x
            if y + h > page_h:
                h = int(page_h) - y
        cur = self.app.conn.cursor()
        try:
            cur.execute("update code_image set x1=?, y1=?, width=?, height=? where imid=?",
                        (x, y, w, h, area['imid']))
            self.app.conn.commit()
            if getattr(self.app, "project_events", None) is not None:
                self.app.project_events.emit_table_changes(['code_image'], source=self)
            self.app.delete_backup = False
        except sqlite3.IntegrityError:
            self.app.conn.rollback()
            Message(self.app, _("Duplicate Error"),
                    _("This exact coded area already exists."), "warning").exec()
        # Same as view_image: upon confirmation, it exits resize mode.
        self.area_to_resize = None
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        if page_idx is not None and page_idx < len(self.view.items_):
            self.view.items_[page_idx].update()

    # Restructuring of imported files using the previous method.
    def _offer_restructure(self):
        """
        Warning of mismatched text (typical of files imported with the previous method)
        with the option to restructure the file to the new extractor, remapping its codings.
        """

        msg = _("The text extracted from this PDF does not match the imported text.") + "\n"
        msg += _("This usually means the file was imported with the previous method.") + "\n\n"
        msg += _("Restructure this file to the new method now?") + "\n"
        msg += _("The stored text will be updated. Its codings (all coders), annotations and "
                 "case assignments will be relocated in the new text.") + "\n"
        msg += _("Segments that cannot be located exactly keep their original quote and are "
                 "reported for review.") + "\n\n"
        msg += _("If you answer No, text coding stays disabled for this file. "
                 "Area coding and search still work.")
        reply = QtWidgets.QMessageBox.question(
            self, _("Text mismatch"), msg,
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No)
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            self.restructure_to_new_extraction()

    def _locate_segment_in_new_text(self, fragment, old_pos0, old_len_total, new_text):
        """
        Locates the fragment in the new text. Returns (pos0, pos1) or None if it cannot be located.
        First, it searches for literal occurrences; if there are none, it retries with flexible spacing
        (extractors differ in spaces and line breaks). With multiple occurrences, it chooses the one
        closest to the original relative position.
        """

        if not fragment:
            return None
        candidates = []
        start = new_text.find(fragment)
        while start != -1 and len(candidates) < 200:
            candidates.append((start, start + len(fragment)))
            start = new_text.find(fragment, start + 1)
        if not candidates:
            tokens = fragment.split()
            if not tokens or len(tokens) > 600:
                return None
            try:
                pattern = re.compile(r"[ \t\r\n]+".join(re.escape(t) for t in tokens))
            except re.error:
                return None
            for match in pattern.finditer(new_text):
                candidates.append((match.start(), match.end()))
                if len(candidates) >= 200:
                    break
        if not candidates:
            return None
        rel = old_pos0 / max(1, old_len_total)
        best = min(candidates, key=lambda c: abs(c[0] / max(1, len(new_text)) - rel))
        return best

    def restructure_layout(self, target_variant):
        """
        Converts the CURRENT file between text layouts ('lines' <-> 'joined') by
        activating the target variant and running the standard restructuring, which
        rewrites source.fulltext and relocates codings, annotations and case
        assignments in the new text. Known limitation of 'joined': block detection
        is the PDF's own; headings inside a block, lists, poetry or hyphenated
        line-end words ("investiga- cion") may not read perfectly.
        Args:
            target_variant: "lines" or "joined"
        """

        if self.file_ is None or self._text_variants is None or \
                target_variant not in self._text_variants:
            return
        target = self._text_variants[target_variant]
        db_text = self.file_.get('fulltext') or ""
        if db_text == target['fulltext']:
            self.ui.label_status.setText(_("The file already uses this layout."))
            return
        msg = _("Convert this PDF's stored text to the selected layout?") + "\n\n"
        msg += _("The stored text will be rewritten and its codings (all coders), "
                 "annotations and case assignments will be relocated in the new text. "
                 "Segments that cannot be located exactly keep their original quote "
                 "and are reported for review.")
        reply = QtWidgets.QMessageBox.question(
            self, _("Restructure layout"), msg,
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No)
        if reply != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        self.active_text_variant = target_variant
        self.pages = target['pages']
        self._page_starts = [p['char_start'] for p in self.pages]
        self.text = target['fulltext']
        self.restructure_to_new_extraction()

    def restructure_to_new_extraction(self):
        """
        Restructures the current file to the new extractor: updates source.fulltext
        and relocates code_text (all coders), annotation, and case_text by locating each
        fragment in the new text. Those that cannot be located keep their original citation
        and are relocated proportionally, reporting them for review. All in a single transaction:
        upon any error, it reverts without changes.
        """

        if self.file_ is None or not self.pages or self.text == "":
            return
        old_text = self.file_.get('fulltext') or ""
        new_text = self.text
        if old_text == new_text:
            return
        fid = self.file_['id']
        old_len = len(old_text)
        new_len = len(new_text)
        cur = self.app.conn.cursor()
        approx = []  # [(type, name, owner, fragment)] for the report

        def proporcional(pos0, pos1):
            n0 = min(new_len, max(0, round(pos0 / max(1, old_len) * new_len)))
            n1 = min(new_len, n0 + max(1, pos1 - pos0))
            return n0, n1

        # Text codings, from all coders
        cur.execute("select cid, name from code_name")
        code_names = dict(cur.fetchall())
        cur.execute("select ctid, cid, owner, pos0, pos1, seltext from code_text where fid=?", [fid])
        ct_rows = cur.fetchall()
        updates_ct = []
        for ctid, cid, owner, pos0, pos1, seltext in ct_rows:
            frag = seltext if seltext else old_text[pos0:pos1]
            loc = self._locate_segment_in_new_text(frag, pos0, old_len, new_text)
            if loc is None:
                n0, n1 = proporcional(pos0, pos1)
                # Keeps the original citation as evidence; only the position is approximate.
                updates_ct.append((n0, n1, seltext, ctid))
                approx.append((_("Code"), code_names.get(cid, str(cid)), owner, frag))
            else:
                n0, n1 = loc
                updates_ct.append((n0, n1, new_text[n0:n1], ctid))
        # Annotations
        updates_an = []
        try:
            cur.execute("select anid, pos0, pos1, owner from annotation where fid=?", [fid])
            an_rows = cur.fetchall()
        except sqlite3.OperationalError:
            an_rows = []
        for anid, pos0, pos1, owner in an_rows:
            frag = old_text[pos0:pos1]
            loc = self._locate_segment_in_new_text(frag, pos0, old_len, new_text)
            if loc is None:
                n0, n1 = proporcional(pos0, pos1)
                approx.append((_("Annotation"), str(anid), owner, frag))
            else:
                n0, n1 = loc
            updates_an.append((n0, n1, anid))
        # Case links on the text.
        cur.execute("select case_text.id, cases.name, case_text.owner, case_text.pos0, "
                    "case_text.pos1 from case_text join cases on cases.caseid=case_text.caseid "
                    "where case_text.fid=?", [fid])
        cs_rows = cur.fetchall()
        updates_cs = []
        for row_id, case_name, owner, pos0, pos1 in cs_rows:
            if pos0 <= 0 and pos1 >= old_len:
                # Entire file assigned to the case: cover the entire new text.
                updates_cs.append((0, new_len, row_id))
                continue
            frag = old_text[pos0:pos1]
            loc = self._locate_segment_in_new_text(frag, pos0, old_len, new_text)
            if loc is None:
                n0, n1 = proporcional(pos0, pos1)
                approx.append((_("Case"), case_name, owner, frag))
            else:
                n0, n1 = loc
            updates_cs.append((n0, n1, row_id))
        # Apply all or nothing.
        try:
            cur.execute("update source set fulltext=? where id=?", (new_text, fid))
            cur.executemany("update code_text set pos0=?, pos1=?, seltext=? where ctid=?",
                            updates_ct)
            if updates_an:
                cur.executemany("update annotation set pos0=?, pos1=? where anid=?", updates_an)
            if updates_cs:
                cur.executemany("update case_text set pos0=?, pos1=? where id=?", updates_cs)
            self.app.conn.commit()
        except Exception as err:
            self.app.conn.rollback()
            logger.error(f"Reestructuracion fallida (fid {fid}): {err}")
            Message(self.app, _("Error"),
                    _("Restructure failed. No changes were made.") + f"\n{err}",
                    "warning").exec()
            return
        self.app.delete_backup = False
        if getattr(self.app, "project_events", None) is not None:
            self.app.project_events.emit_table_changes(
                ['source', 'code_text', 'annotation', 'case_text'], source=self)
        # Report
        msg = _("File restructured to the new method.") + "\n"
        msg += _("Codings:") + f" {len(ct_rows)}, " + _("annotations:") + f" {len(an_rows)}, "
        msg += _("case links:") + f" {len(cs_rows)}."
        if approx:
            msg += "\n\n" + _("Relocated approximately, please review:") + f" {len(approx)}\n"
            for kind, name, owner, frag in approx[:12]:
                snippet = " ".join(frag.split())[:60]
                msg += f"- {kind} [{name}] ({owner}): {snippet}\n"
            if len(approx) > 12:
                msg += _("... and more, see the log file.") + "\n"
            for kind, name, owner, frag in approx:
                logger.warning(f"Reubicacion aproximada (fid {fid}): {kind} [{name}] "
                               f"({owner}): {frag[:200]}")
        else:
            msg += "\n" + _("All segments were relocated exactly.")
        # Report dialog with the option to save it to a journal.
        ventana = Message(self.app, _("Restructure complete"), msg)
        ventana.setIcon(QtWidgets.QMessageBox.Icon.Information)
        boton_journal = None
        if approx:
            boton_journal = ventana.addButton(_("Save report to journal"),
                                              QtWidgets.QMessageBox.ButtonRole.ActionRole)
        ventana.addButton(QtWidgets.QMessageBox.StandardButton.Close)
        ventana.exec()
        if boton_journal is not None and ventana.clickedButton() is boton_journal:
            self._save_restructure_report_to_journal(ct_rows, an_rows, cs_rows, approx)
        # Reload: the file dict is the same object used by the list.
        self.file_['fulltext'] = new_text
        self.load_file(self.file_)

    def _save_restructure_report_to_journal(self, ct_rows, an_rows, cs_rows, approx):
        """
        Saves the restructure report to a new journal, including ALL approximately relocated
        citations (not just the 12 shown in the dialog), leaving a permanent, reviewable record.
        """

        if self.file_ is None:
            return
        now = datetime.datetime.now().astimezone()
        fecha = now.strftime("%Y-%m-%d %H:%M:%S")
        owner = self.app.settings['codername']
        # Full report body (not truncated).
        lineas = [
            _("PDF restructure report"),
            _("File:") + f" {self.file_['name']}",
            _("Date:") + f" {fecha}",
            _("Coder:") + f" {owner}",
            "",
            _("Codings:") + f" {len(ct_rows)}, " + _("annotations:") + f" {len(an_rows)}, "
            + _("case links:") + f" {len(cs_rows)}.",
            _("Segments relocated approximately (need review):") + f" {len(approx)}",
            "",
        ]
        for kind, name, owner_seg, frag in approx:
            frag_limpio = " ".join(frag.split())[:500]
            lineas.append(f"- {kind} [{name}] ({owner_seg}): {frag_limpio}")
        jentry = "\n".join(lineas)
        # Valid journal name: only letters, digits, underscore, hyphen and space (no dots or
        # colons), and unique (the journal table requires it).
        base = os.path.splitext(self.file_['name'])[0]
        nombre = re.sub(r"[^\w -]", "_", f"Restructure {base} {now.strftime('%Y-%m-%d %H%M%S')}")
        cur = self.app.conn.cursor()
        intento = nombre
        sufijo = 2
        while True:
            try:
                cur.execute("insert into journal(name,jentry,owner,date) values(?,?,?,?)",
                            (intento, jentry, owner, fecha))
                self.app.conn.commit()
                break
            except sqlite3.IntegrityError:
                self.app.conn.rollback()
                intento = f"{nombre}_{sufijo}"
                sufijo += 1
                if sufijo > 50:
                    Message(self.app, _("Journal"),
                            _("Could not create the journal entry."), "warning").exec()
                    return
        self.app.delete_backup = False
        self.parent_textEdit.append(_("Restructure report saved to journal: ") + intento)
        Message(self.app, _("Journal"),
                _("Report saved to journal:") + f"\n{intento}").exec()

    def export_option_selected(self):
        """
        Routes the option chosen in the export combobox to the corresponding method (highlighted
        PDF or ODT report) and resets the combobox to index 0.
        """
        text = self.ui.comboBox_exports.currentText().lower()
        if "pdf highlight" in text:
            self.export_pdf_highlight()
        elif "odt report" in text:
            self.export_odt_report()
        self.ui.comboBox_exports.setCurrentIndex(0)

    def export_pdf_highlight(self):
        """
        Exports a copy of the original PDF with the text and area codings as native annotations
        (highlight for text, rectangle for areas), each carrying the code name, its memo and the
        coder.
        """
        if self.file_ is None:
            return
        filepath = self._resolve_filepath(self.file_)
        if filepath is None or not os.path.exists(filepath):
            Message(self.app, _("Warning"), _("Cannot open original file."), "warning").exec()
            return

        suggested = f"{os.path.splitext(self.file_['name'])[0]}_highlighted.pdf"
        out_path, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self, _("Export highlighted PDF"),
            os.path.join(os.path.expanduser("~"), suggested), "PDF (*.pdf)")
        if not out_path:
            return

        # Without a reliable word map (extraction running or mismatch) text rects would be
        # misplaced: skip them with a notice and export areas only.
        include_text = self.text_ready()
        if self.code_text and not include_text:
            Message(self.app, _("Warning"),
                    _("Text codings will be skipped: the extracted text is not ready or "
                      "does not match the imported text. Only area codings will be "
                      "exported."), "warning").exec()
        try:
            doc = fitz.open(filepath)

            for coding in (self.code_text if include_text else []):
                c_name = coding.get('name', '')
                c_color = coding.get('color', '#cccccc')
                c_memo = coding.get('memo', '')
                c_owner = coding.get('owner', '')

                rgb = (int(c_color[1:3], 16)/255.0, int(c_color[3:5], 16)/255.0, int(c_color[5:7], 16)/255.0)

                content_str = f"Code: {c_name}"
                if c_memo:
                    content_str += f"\nMemo: {c_memo}"

                pages = self._pages_spanning(coding['pos0'], coding['pos1'])
                for page_idx in pages:
                    if page_idx >= len(doc):
                        continue
                    page = doc.load_page(page_idx)
                    rects = self.rects_for_range(page_idx, coding['pos0'], coding['pos1'])
                    if rects:
                        quads_list = []
                        for r in rects:
                            quads_list.append(fitz.Rect(r.x(), r.y(), r.right(), r.bottom()).quad)
                        annot = page.add_highlight_annot(quads=quads_list)
                        annot.set_colors(stroke=rgb)
                        annot.set_info(title=c_owner, content=content_str)
                        annot.update()

            for area in self.code_areas:
                page_idx = area.get('pdf_page')
                if page_idx is None or page_idx >= len(doc):
                    continue
                c_name = area.get('name', '')
                c_color = area.get('color', '#cccccc')
                c_memo = area.get('memo', '')
                c_owner = area.get('owner', '')

                rgb = (int(c_color[1:3], 16)/255.0, int(c_color[3:5], 16)/255.0, int(c_color[5:7], 16)/255.0)

                content_str = f"Area Code: {c_name}"
                if c_memo:
                    content_str += f"\nMemo: {c_memo}"

                page = doc.load_page(page_idx)
                fitz_rect = fitz.Rect(area['x1'], area['y1'], area['x1'] + area['width'], area['y1'] + area['height'])
                annot = page.add_rect_annot(fitz_rect)
                annot.set_colors(stroke=rgb)
                annot.set_info(title=c_owner, content=content_str)
                annot.update()

            doc.save(out_path)
            doc.close()
            msg = _("Highlighted PDF exported: ") + out_path
            self.parent_textEdit.append(msg)
            Message(self.app, _('Success'), msg, "information").exec()
        except Exception as err:
            logger.exception("Error exporting highlighted PDF")
            Message(self.app, _("Error"), str(err), "warning").exec()

    def export_odt_report(self):
        """
        Exports an ODT analytical report of the current file (without dumping the document's full
        text). Built with a native QTextDocument, it includes: a code frequency table (text and
        areas), a co-occurrence table (text overlaps and geometric intersection of areas on the
        same page), the coded text segments with their co-occurring codes and memos, the area
        segments with their cropped PDF image, and the software citation.
        """
        if self.file_ is None:
            return

        suggested = f"{os.path.splitext(self.file_['name'])[0]}_report.odt"
        out_path, _filter = QtWidgets.QFileDialog.getSaveFileName(
            self, _("Export ODT Report"),
            os.path.join(os.path.expanduser("~"), suggested), "ODT (*.odt)")
        if not out_path:
            return

        try:
            doc = QtGui.QTextDocument()
            cursor = QtGui.QTextCursor(doc)

            # Estilos y formatos
            header_fmt = QtGui.QTextCharFormat()
            header_fmt.setFontWeight(QtGui.QFont.Weight.Bold)
            header_fmt.setFontPointSize(16)

            title_fmt = QtGui.QTextCharFormat()
            title_fmt.setFontPointSize(14)
            title_fmt.setFontWeight(QtGui.QFont.Weight.Bold)

            norm_fmt = QtGui.QTextCharFormat()
            norm_fmt.setFontPointSize(12)
            
            it_fmt = QtGui.QTextCharFormat(norm_fmt)
            it_fmt.setFontItalic(True)

            table_fmt = QtGui.QTextTableFormat()
            table_fmt.setBorder(0.5)
            table_fmt.setCellPadding(4)
            table_fmt.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)

            head_fmt = QtGui.QTextCharFormat()
            head_fmt.setFontWeight(QtGui.QFont.Weight.Bold)
            head_fmt.setFontPointSize(12)
            head_fmt.setBackground(QBrush(QColor("#e0e0e0")))

            # Cabecera
            try:
                project_name = os.path.basename(self.app.project_path).replace(".qda", "")
            except AttributeError:
                project_name = "Project"

            cursor.insertText(f"Project: {project_name}\n", header_fmt)
            cursor.insertText(f"File: {self.file_['name']}\n", header_fmt)
            report_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
            cursor.insertText(f"Generated report: {report_date}\n\n", header_fmt)

            seg_co_occurrences = defaultdict(set)
            area_co_occurrences = defaultdict(set)
            co_occur = defaultdict(int)
            
            for i, c1 in enumerate(self.code_text):
                for j, c2 in enumerate(self.code_text):
                    if j <= i or c1['cid'] == c2['cid']:
                        continue
                    if c1['pos0'] < c2['pos1'] and c2['pos0'] < c1['pos1']:
                        seg_co_occurrences[(c1['pos0'], c1['pos1'], c1['cid'])].add(c2['name'])
                        seg_co_occurrences[(c2['pos0'], c2['pos1'], c2['cid'])].add(c1['name'])
                        pair = tuple(sorted([c1['name'], c2['name']]))
                        co_occur[pair] += 1

            for i, a1 in enumerate(self.code_areas):
                for j, a2 in enumerate(self.code_areas):
                    if j <= i or a1['cid'] == a2['cid']:
                        continue
                    if a1['pdf_page'] == a2['pdf_page']:
                        if (a1['x1'] < a2['x1'] + a2['width'] and a1['x1'] + a1['width'] > a2['x1'] and
                            a1['y1'] < a2['y1'] + a2['height'] and a1['y1'] + a1['height'] > a2['y1']):
                            area_co_occurrences[a1['imid']].add(a2['name'])
                            area_co_occurrences[a2['imid']].add(a1['name'])
                            pair = tuple(sorted([a1['name'], a2['name']]))
                            co_occur[pair] += 1

            cursor.insertText("Code Frequency Table\n\n", title_fmt)
            code_stats = {}
            all_codings = self.code_text + self.code_areas
            for c in all_codings:
                c_name = c['name']
                if c_name not in code_stats:
                    code_stats[c_name] = {
                        'color': c.get('color', '#cccccc'),
                        'freq': 0, 
                        'owners': set()
                    }
                code_stats[c_name]['freq'] += 1
                code_stats[c_name]['owners'].add(c.get('owner', ''))

            if code_stats:
                freq_rows = len(code_stats) + 1
                freq_table = cursor.insertTable(freq_rows, 3, table_fmt)
                freq_headers = ["Code", "Frequency", "Coder(s)"]
                for col, text in enumerate(freq_headers):
                    freq_table.cellAt(0, col).firstCursorPosition().insertText(text, head_fmt)

                row = 1
                for c_name, stats in sorted(code_stats.items()):
                    cell_cursor = freq_table.cellAt(row, 0).firstCursorPosition()
                    c_fmt = QtGui.QTextCharFormat()
                    c_fmt.setFontPointSize(12)
                    c_fmt.setBackground(QBrush(QColor(stats['color'])))
                    fg = TextColor(stats['color']).recommendation
                    c_fmt.setForeground(QBrush(QColor(fg)))
                    cell_cursor.insertText(c_name, c_fmt)

                    freq_table.cellAt(row, 1).firstCursorPosition().insertText(str(stats['freq']), norm_fmt)
                    freq_table.cellAt(row, 2).firstCursorPosition().insertText(", ".join(sorted(stats['owners'])), norm_fmt)
                    row += 1

                cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
                cursor.insertText("\n\n", norm_fmt)

            cursor.insertText("Code Co-occurrences\n\n", title_fmt)
            if co_occur:
                co_rows = len(co_occur) + 1
                co_table = cursor.insertTable(co_rows, 3, table_fmt)
                co_headers = ["Code A", "Code B", "Co-occurrence frequency"]
                for col, text in enumerate(co_headers):
                    co_table.cellAt(0, col).firstCursorPosition().insertText(text, head_fmt)
                r = 1
                for pair, count in sorted(co_occur.items(), key=lambda x: -x[1]):
                    co_table.cellAt(r, 0).firstCursorPosition().insertText(pair[0], norm_fmt)
                    co_table.cellAt(r, 1).firstCursorPosition().insertText(pair[1], norm_fmt)
                    co_table.cellAt(r, 2).firstCursorPosition().insertText(str(count), norm_fmt)
                    r += 1
                cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
                cursor.insertText("\n\n", norm_fmt)
            else:
                cursor.insertText("No co-occurrences found in this file.\n\n", norm_fmt)

            if self.code_text:
                cursor.insertText("Coded Text Segments\n\n", title_fmt)
                codes_sorted = sorted(self.code_text, key=lambda x: x.get('pos0', 0))
                for c in codes_sorted:
                    p0 = c.get('pos0', 0)
                    p1 = c.get('pos1', 0)
                    seg = c.get('seltext', '')
                    if not seg and self.text:
                        offset = self.file_.get('start', 0)
                        seg = self.text[max(0, p0 - offset):max(0, p1 - offset)]

                    color = c.get('color', '#cccccc')
                    fg = TextColor(color).recommendation
                    c_header_fmt = QtGui.QTextCharFormat()
                    c_header_fmt.setFontPointSize(12)
                    c_header_fmt.setBackground(QBrush(QColor(color)))
                    c_header_fmt.setForeground(QBrush(QColor(fg)))
                    c_header_bold = QtGui.QTextCharFormat(c_header_fmt)
                    c_header_bold.setFontWeight(QtGui.QFont.Weight.Bold)

                    cursor.insertText(f"[{p0}-{p1}] ", c_header_bold)
                    cursor.insertText(f"Code: {c['name']}, Coder: {c.get('owner', '')}\n\n", c_header_fmt)
                    
                    cursor.insertText(seg + "\n\n", it_fmt)
                    
                    co_key = (c['pos0'], c['pos1'], c['cid'])
                    co_codes = seg_co_occurrences.get(co_key, set())
                    if co_codes:
                        cursor.insertText(f"[Co-occurring codes: {', '.join(sorted(co_codes))}]\n\n", norm_fmt)

                    coded_memo = c.get('memo', '')
                    if coded_memo and str(coded_memo).strip():
                        cursor.insertText(f"[Coded memo: {coded_memo}]\n\n", norm_fmt)

            if self.code_areas:
                cursor.insertText("Coded Areas (Pages)\n\n", title_fmt)
                
                pdf_doc = None
                filepath = self._resolve_filepath(self.file_)
                if filepath and os.path.exists(filepath):
                    pdf_doc = fitz.open(filepath)

                areas_sorted = sorted(self.code_areas, key=lambda x: x.get('pdf_page', 0))
                for a in areas_sorted:
                    page_idx = a.get('pdf_page', 0)
                    page = page_idx + 1
                    color = a.get('color', '#cccccc')
                    fg = TextColor(color).recommendation
                    a_header_fmt = QtGui.QTextCharFormat()
                    a_header_fmt.setFontPointSize(12)
                    a_header_fmt.setBackground(QBrush(QColor(color)))
                    a_header_fmt.setForeground(QBrush(QColor(fg)))
                    a_header_bold = QtGui.QTextCharFormat(a_header_fmt)
                    a_header_bold.setFontWeight(QtGui.QFont.Weight.Bold)

                    cursor.insertText(f"[Page {page}] ", a_header_bold)
                    cursor.insertText(f"Code: {a.get('name', '')}, Coder: {a.get('owner', '')}\n\n", a_header_fmt)
                    
                    coords = f"Coordinates: X:{a.get('x1')}, Y:{a.get('y1')}, Width:{a.get('width')}, Height:{a.get('height')}\n\n"
                    cursor.insertText(coords, norm_fmt)

                    if pdf_doc is not None and page_idx < len(pdf_doc):
                        w = a.get('width', 0)
                        h = a.get('height', 0)
                        if w > 0 and h > 0:
                            pdf_page = pdf_doc.load_page(page_idx)
                            rect = fitz.Rect(a.get('x1'), a.get('y1'), a.get('x1') + w, a.get('y1') + h)
                            # Render at 2x for sharpness.
                            pix = pdf_page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect, alpha=False)
                            qimg = QtGui.QImage(pix.samples, pix.width, pix.height, pix.stride,
                                                QtGui.QImage.Format.Format_RGB888).copy()
                            # Register the image as a named resource (so the ODF writer embeds it) and cap
                            # the displayed width so it does not overflow the page.
                            img_name = f"coded_area_{a.get('imid', id(a))}"
                            doc.addResource(QtGui.QTextDocument.ResourceType.ImageResource,
                                            QtCore.QUrl(img_name), qimg)
                            img_fmt = QtGui.QTextImageFormat()
                            img_fmt.setName(img_name)
                            max_w = 480.0
                            if qimg.width() > max_w:
                                img_fmt.setWidth(max_w)
                                img_fmt.setHeight(qimg.height() * max_w / qimg.width())
                            cursor.insertImage(img_fmt)
                            cursor.insertText("\n\n", norm_fmt)

                    co_codes_area = area_co_occurrences.get(a['imid'], set())
                    if co_codes_area:
                        cursor.insertText(f"[Co-occurring codes: {', '.join(sorted(co_codes_area))}]\n\n", norm_fmt)

                    coded_memo = a.get('memo', '')
                    if coded_memo and str(coded_memo).strip():
                        cursor.insertText(f"[Coded memo: {coded_memo}]\n\n", norm_fmt)

                if pdf_doc is not None:
                    pdf_doc.close()

            # 5. Software Citation
            apa_cite = ("Curtain C, Dröge K, Missaghieh--Poncet J, Salomón L. (2026) "
                        "QualCoder 4.0 [Computer software]. Retrieved from "
                        "https://github.com/ccbogel/QualCoder/releases")
            cursor.insertText("\nSoftware citation\n", title_fmt)
            cursor.insertText(apa_cite + "\n", norm_fmt)

            tw = QtGui.QTextDocumentWriter()
            tw.setFileName(out_path)
            tw.setFormat(b'ODF')
            tw.write(doc)

            msg = _("ODT Report exported: ") + out_path
            self.parent_textEdit.append(msg)
            Message(self.app, _('Success'), msg, "information").exec()
        except Exception as err:
            logger.exception("Error exporting ODT Report")
            Message(self.app, _("Error"), str(err), "warning").exec()
