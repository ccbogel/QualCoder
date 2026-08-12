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
https://qualcoder.wordpress.com/
https://qualcoder-org.github.io
https://qualcoder.org/
"""

import pymupdf
import logging

from PyQt6 import QtCore, QtGui, QtWidgets

logger = logging.getLogger(__name__)


class PdfPreviewWidget(QtWidgets.QWidget):
    """
    Shared PDF preview widget: rendered page in the centre, boundable < > navigation
    and in-memory rendering with document closing. Used by DialogPdfPagesToImages
    (converter) and DialogPdfPreview (viewer).
    """

    ZOOM_MIN = 25
    ZOOM_MAX = 200
    ZOOM_STEP = 25

    def __init__(self, filepath:str, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.total_pages = 0
        self.preview_page = 0  # base 0
        self.page_min = 0
        self.page_max = 0
        self.zoom = 100  # percent of the fitted size
        self._rendering = False  # re-entrancy guard: setPixmap/resize can trigger nested resize events
        self._render_key = None  # (page, zoom, scale) of the last render, to skip identical renders
        try:
            doc = pymupdf.open(filepath)
            self.total_pages = len(doc)
            doc.close()
        except Exception as err:
            logger.warning(f"PdfPreviewWidget: {filepath} {err}")
        self.page_max = max(0, self.total_pages - 1)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label_preview = QtWidgets.QLabel()
        self.label_preview.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.scroll_area.setMinimumSize(380, 380)
        self.scroll_area.setWidget(self.label_preview)
        layout.addWidget(self.scroll_area, stretch=1)
        nav = QtWidgets.QHBoxLayout()
        self.btn_prev = QtWidgets.QPushButton("<")
        self.btn_prev.setMaximumWidth(40)
        self.btn_prev.clicked.connect(lambda: self.change_preview_page(-1))
        self.label_page = QtWidgets.QLabel("")
        self.label_page.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.btn_next = QtWidgets.QPushButton(">")
        self.btn_next.setMaximumWidth(40)
        self.btn_next.clicked.connect(lambda: self.change_preview_page(1))
        nav.addStretch(1)
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.label_page)
        nav.addWidget(self.btn_next)
        nav.addStretch(1)
        self.btn_zoom_out = QtWidgets.QPushButton("−")
        self.btn_zoom_out.setMaximumWidth(40)
        self.btn_zoom_out.setToolTip(_("Zoom out"))
        self.btn_zoom_out.clicked.connect(lambda: self.change_zoom(-self.ZOOM_STEP))
        self.label_zoom = QtWidgets.QLabel("100%")
        self.label_zoom.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.label_zoom.setMinimumWidth(44)
        self.btn_zoom_in = QtWidgets.QPushButton("+")
        self.btn_zoom_in.setMaximumWidth(40)
        self.btn_zoom_in.setToolTip(_("Zoom in"))
        self.btn_zoom_in.clicked.connect(lambda: self.change_zoom(self.ZOOM_STEP))
        nav.addWidget(self.btn_zoom_out)
        nav.addWidget(self.label_zoom)
        nav.addWidget(self.btn_zoom_in)
        nav.addStretch(1)
        layout.addLayout(nav)
        self.render_preview()

    def set_page_limits(self, page_min:int, page_max:int):
        """
        Bounds navigation (0-based) and repositions the previewed page.
        """

        self.page_min = max(0, page_min)
        self.page_max = min(max(0, self.total_pages - 1), max(self.page_min, page_max))
        self.preview_page = min(max(self.preview_page, self.page_min), self.page_max)
        self.render_preview()

    def change_preview_page(self, delta:int):
        nueva = self.preview_page + delta
        if self.page_min <= nueva <= self.page_max:
            self.preview_page = nueva
            self.render_preview()

    def change_zoom(self, delta:int):
        """
        Steps the zoom within ZOOM_MIN..ZOOM_MAX percent of the fitted size.
        """

        new_zoom = min(self.ZOOM_MAX, max(self.ZOOM_MIN, self.zoom + delta))
        if new_zoom != self.zoom:
            self.zoom = new_zoom
            self.render_preview()

    def render_preview(self):
        """
        Renders the previewed page in memory at the real zoomed size (no pixmap
        scaling) and always closes the document (no handle retained).
        Re-entrancy guard: label resizes can move scrollbars and fire nested
        resize/layout events; re-entering here recurses at C level and kills the
        process on Windows.
        """

        if self._rendering:
            return
        self._rendering = True
        try:
            self.do_render()
        finally:
            self._rendering = False

    def do_render(self):
        if self.total_pages == 0:
            self.label_preview.setText(_("Cannot open: ") + self.filepath)
            self.label_preview.adjustSize()
            self.label_page.setText("0/0")
            self.label_zoom.setText("")
            for btn in (self.btn_prev, self.btn_next, self.btn_zoom_out, self.btn_zoom_in):
                btn.setEnabled(False)
            return
        # maximumViewportSize ignores scrollbar visibility, so the fitted size is
        # stable and scrollbar toggling cannot re-trigger renders.
        viewport = self.scroll_area.maximumViewportSize()
        try:
            doc = pymupdf.open(self.filepath)
            try:
                page = doc.load_page(self.preview_page)
                page_w = max(1.0, page.rect.width)
                page_h = max(1.0, page.rect.height)
                fit = min((viewport.width() - 4) / page_w, (viewport.height() - 4) / page_h)
                scale = fit * self.zoom / 100.0
                # Clamp render size: at least 1 px, at most ~5000 px per side
                scale = max(1.0 / min(page_w, page_h), min(scale, 5000.0 / max(page_w, page_h)))
                render_key = (self.preview_page, self.zoom, round(scale, 4))
                if render_key == self._render_key:
                    self.update_controls()
                    return
                pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False, annots=False)  # PDF highlights/notes not painted in the preview
                # bytes() detaches the buffer from PyMuPDF before the doc is closed
                image = QtGui.QImage(bytes(pix.samples), pix.width, pix.height, pix.stride,
                                     QtGui.QImage.Format.Format_RGB888).copy()
            finally:
                doc.close()
        except Exception as err:
            logger.warning(f"render_preview: {self.filepath} {err}")
            self.label_preview.setText(_("Cannot open: ") + self.filepath)
            self.label_preview.adjustSize()
            return
        pixmap = QtGui.QPixmap.fromImage(image)
        self.label_preview.setPixmap(pixmap)
        self.label_preview.resize(pixmap.size())
        self._render_key = render_key
        self.update_controls()

    def update_controls(self):
        self.label_page.setText(f"{self.preview_page + 1}/{self.total_pages}")
        self.label_zoom.setText(f"{self.zoom}%")
        self.btn_prev.setEnabled(self.preview_page > self.page_min)
        self.btn_next.setEnabled(self.preview_page < self.page_max)
        self.btn_zoom_out.setEnabled(self.zoom > self.ZOOM_MIN)
        self.btn_zoom_in.setEnabled(self.zoom < self.ZOOM_MAX)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.render_preview()


class DialogPdfPreview(QtWidgets.QDialog):
    """
    PDF viewer for Manage files, in the style of the image converter: navigable
    preview of all pages, no editing. The stored fulltext of a PDF is NOT
    editable: it must match, character by character, the text extracted from
    the pages. To work with an editable text, "Convert to txt" creates a new
    text source with a copy of the PDF's text.
    """

    def __init__(self, app, filepath:str, filename:str, parent=None, show_convert_txt:bool=True):
        super().__init__(parent)
        self.app = app
        self.convert_txt_requested = False
        self.setWindowTitle(_("View PDF") + f" - {filename}")
        self.setMinimumSize(520, 560)
        layout = QtWidgets.QVBoxLayout(self)
        self.preview = PdfPreviewWidget(filepath, self)
        layout.addWidget(self.preview, stretch=1)
        buttons = QtWidgets.QHBoxLayout()
        # Optional: Manage references opens the same viewer without the txt copy.
        self.btn_convert_txt = None
        if show_convert_txt:
            self.btn_convert_txt = QtWidgets.QPushButton(_("Convert to txt"))
            self.btn_convert_txt.setToolTip(
                _("Create a new editable text file with a copy of this PDF's text"))
            self.btn_convert_txt.clicked.connect(self.request_convert_txt)
            buttons.addWidget(self.btn_convert_txt)
        btn_close = QtWidgets.QPushButton(_("Close"))
        btn_close.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(btn_close)
        layout.addLayout(buttons)

    def request_convert_txt(self):
        """
        Flags the txt copy request; the caller (view) runs extract_pdf_text_copy,
        which already validates scanned PDFs and duplicate names.
        """

        self.convert_txt_requested = True
        self.accept()

    @property
    def total_pages(self):
        return self.preview.total_pages


class DialogPdfPagesToImages(QtWidgets.QDialog):
    """
    Dialog to convert PDF pages into images, print-preview style: navigable page
    preview, page range selection (1-based) and output resolution. Returns the chosen
    range and resolution; the caller (pdf_to_images) performs the conversion.
    """

    def __init__(self, app, filepath:str, filename:str, parent=None):
        super().__init__(parent)
        self.app = app
        self.setWindowTitle(_("Pdf pages to images") + f" - {filename}")
        self.setMinimumSize(520, 560)
        layout = QtWidgets.QVBoxLayout(self)
        self.preview = PdfPreviewWidget(filepath, self)
        layout.addWidget(self.preview, stretch=1)
        # Range and resolution
        form = QtWidgets.QHBoxLayout()
        form.addWidget(QtWidgets.QLabel(_("From page")))
        self.spin_from = QtWidgets.QSpinBox()
        self.spin_from.setRange(1, max(1, self.preview.total_pages))
        self.spin_from.setValue(1)
        self.spin_from.valueChanged.connect(self.range_changed)
        form.addWidget(self.spin_from)
        form.addWidget(QtWidgets.QLabel(_("To page")))
        self.spin_to = QtWidgets.QSpinBox()
        self.spin_to.setRange(1, max(1, self.preview.total_pages))
        self.spin_to.setValue(max(1, self.preview.total_pages))
        self.spin_to.valueChanged.connect(self.range_changed)
        form.addWidget(self.spin_to)
        form.addStretch(1)
        form.addWidget(QtWidgets.QLabel(_("Resolution")))
        self.combo_dpi = QtWidgets.QComboBox()
        # 72 dpi reproduces the previous behaviour; higher resolution gives sharper
        # images for coding (larger files).
        self.combo_dpi.addItems(["72", "150", "300"])
        form.addWidget(self.combo_dpi)
        form.addWidget(QtWidgets.QLabel(_("dpi")))
        layout.addLayout(form)
        # Botones. Buttons
        # Manual button row instead of QDialogButtonBox: guarantees the layout on
        # every platform style. "Convert current page" left-aligned; "Convert" and
        # "Cancel" right-aligned.
        buttons = QtWidgets.QHBoxLayout()
        self.btn_current_page = QtWidgets.QPushButton(_("Convert current page"))
        self.btn_current_page.setToolTip(_("Convert only the page shown in the preview"))
        # Pins the range to the previewed page and accepts, reusing the whole
        # conversion pipeline unchanged (dpi, duplicates, progress).
        self.btn_current_page.clicked.connect(self.convert_current_page)
        buttons.addWidget(self.btn_current_page)
        buttons.addStretch(1)
        self.btn_convert = QtWidgets.QPushButton(_("Convert"))
        self.btn_convert.setDefault(True)
        self.btn_convert.clicked.connect(self.accept)
        buttons.addWidget(self.btn_convert)
        btn_cancel = QtWidgets.QPushButton(_("Cancel"))
        btn_cancel.clicked.connect(self.reject)
        buttons.addWidget(btn_cancel)
        layout.addLayout(buttons)

    @property
    def total_pages(self):
        return self.preview.total_pages

    def convert_current_page(self):
        """
        Pins the range to the previewed page and accepts. Order matters: spin_to
        first (if the page is below the range, range_changed pulls spin_from down
        with it), then spin_from; the from <= to invariant holds both ways.
        """

        page = self.preview.preview_page + 1  # a base 1. To 1-based.
        self.spin_to.setValue(page)
        self.spin_from.setValue(page)
        self.accept()

    def get_range_and_dpi(self):
        """ 
        return: (0-based first page, 0-based last page inclusive, dpi Integer). 
        """

        return self.spin_from.value() - 1, self.spin_to.value() - 1, int(self.combo_dpi.currentText())

    def range_changed(self):
        """ 
        Keeps from <= to and the previewed page inside the range. 
        """

        if self.spin_from.value() > self.spin_to.value():
            if self.sender() is self.spin_from:
                self.spin_to.setValue(self.spin_from.value())
            else:
                self.spin_from.setValue(self.spin_to.value())
        self.preview.set_page_limits(self.spin_from.value() - 1, self.spin_to.value() - 1)

