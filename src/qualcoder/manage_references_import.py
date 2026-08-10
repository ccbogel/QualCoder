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
https://qualcoder.wordpress.com/
https://qualcoder-org.github.io
https://qualcoder.org/
"""

# Preview dialog to import references (from .ris or Zotero). Shows a table with
# every detected reference, a checkbox per row to choose which to import, and the duplicate status
# of both the reference and its attachment. New items are checked by default. It does not insert
# anything: it only returns which rows were chosen and whether to import attachments.

import logging
import re
import unicodedata

from PyQt6 import QtCore, QtGui, QtWidgets

from .GUI.ui_dialog_manage_references_import import Ui_DialogImportReferences

logger = logging.getLogger(__name__)

# RIS tags that make up a signature.
SIGNATURE_TAGS = ('TI', 'T1', 'PY', 'Y1', 'AU', 'A1', 'A2', 'A3', 'A4')

# Attachment types QualCoder can import as a text file. Single source of truth for the .ris
# collector, the path resolver and the attachment importer.
ATTACHMENT_EXTENSIONS = ('.pdf', '.epub')

# RIS link tags that can carry an attachment. Zotero writes PDFs in L1 and other attachments (EPUB
# for instance) in L4, which in RIS means image and rispy maps to 'figure'; looking only at L1/L2
# therefore dropped EPUBs silently. All four are accepted and _resolve_attachment_path decides,
# since it only returns a path when the file exists and is of a supported type.
ATTACHMENT_TAGS = ('L1', 'L2', 'L3', 'L4')


def normalise_for_signature(text):
    """ Lowercase, accent-folded, punctuation stripped, whitespace collapsed. """

    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", text)).strip()


def reference_signature(tag_value_pairs):
    """ Builds a normalized signature (title|year|authors) to detect duplicate references, from
    (tag, value) pairs in RIS format. Returns the signature, or None if there is no title (then
    it is not deduplicated, to avoid grouping references with insufficient data).
    """

    title = ""
    year = ""
    authors = []
    for tag, value in tag_value_pairs:
        if value is None:
            continue
        t = str(tag).upper()
        v = str(value).strip()
        if not v:
            continue
        if t in ("TI", "T1") and not title:
            title = v
        elif t in ("PY", "Y1") and not year:
            m = re.search(r"\d{4}", v)
            year = m.group(0) if m else v
        elif t in ("AU", "A1", "A2", "A3", "A4"):
            authors.append(v)
    if not title:
        return None
    return normalise_for_signature(title) + "|" + year + "|" + normalise_for_signature("; ".join(authors))


def existing_reference_signatures(conn):
    """ Set of signatures of the references already in the project. One query for the whole
    project, instead of one query per tag per reference as the previous detection did.
    """

    cur = conn.cursor()
    placeholders = ",".join("?" * len(SIGNATURE_TAGS))
    cur.execute(f"select risid, tag, value from ris where tag in ({placeholders}) order by risid",
                list(SIGNATURE_TAGS))
    by_risid = {}
    for risid, tag, value in cur.fetchall():
        by_risid.setdefault(risid, []).append((tag, value))
    signatures = set()
    for risid, pairs in by_risid.items():
        sig = reference_signature(pairs)
        if sig:
            signatures.add(sig)
    return signatures

# Colour for the "duplicate" status text (readable on light and dark themes).
DUPLICATE_COLOR = "#d9534f"


def import_progress_dialog(parent, total, first_label=""):
    """ Import progress dialog, with the same settings as manage_files.import_files: window modal,
    Importing title, no minimum duration and no autoReset/autoClose (without them Qt hides it
    on reaching the maximum, and with a single file it closed before the page by page
    extraction started). The caller must close it when finished.
    Args:
        parent: parent widget
        total: number of steps, Integer
        first_label: label shown before the first step, String
    Returns:
        QProgressDialog
    """

    progress = QtWidgets.QProgressDialog(first_label, None, 0, total, parent)
    progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
    progress.setWindowTitle(_("Importing"))
    progress.setMinimumDuration(0)  # Show immediately
    progress.setAutoReset(False)
    progress.setAutoClose(False)
    progress.show()
    return progress


class DialogImportReferences(QtWidgets.QDialog):
    """ Preview with checkbox selection to import references from .ris or Zotero. rows: rows: list
    of dicts, one per candidate reference, with keys label, ref_duplicate, attachment,
    attachment_duplicate. The order of rows is preserved; selected_indices() returns indices
    into it.
    """

    COL_CHECK = 0
    COL_REFERENCE = 1
    COL_STATUS = 2
    COL_ATTACHMENT = 3
    COL_ATTACHMENT_STATUS = 4

    def __init__(self, app, parent, rows, allow_attachments=True, attachments_default=True):
        super().__init__(parent)
        self.app = app
        self.rows = rows if rows else []
        self.ui = Ui_DialogImportReferences()
        self.ui.setupUi(self)
        self.setStyleSheet(f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";')

        # Translated headers.
        self.ui.tableWidget.setHorizontalHeaderLabels(
            [_("Import"), _("Reference"), _("Status"), _("Attachment"), _("Attachment status")])

        # Long text elided in the middle and single-line, so columns fit without a horizontal
        # scrollbar; full name on hover.
        self.ui.tableWidget.setWordWrap(False)
        self.ui.tableWidget.setTextElideMode(QtCore.Qt.TextElideMode.ElideMiddle)

        # Attachments checkbox.
        self.ui.checkBox_import_attachments.setChecked(bool(attachments_default) and bool(allow_attachments))
        self.ui.checkBox_import_attachments.setEnabled(bool(allow_attachments))

        self._fill_table()

        self.ui.pushButton_select_all.clicked.connect(lambda: self._set_all(True))
        self.ui.pushButton_select_none.clicked.connect(lambda: self._set_all(False))
        self.ui.pushButton_select_new.clicked.connect(self._select_new)
        self.ui.tableWidget.itemChanged.connect(self._on_item_changed)
        self.ui.tableWidget.cellDoubleClicked.connect(self._toggle_row)
        self._update_summary()


    def _ro_item(self, text):
        """ Read-only cell. """
        item = QtWidgets.QTableWidgetItem(str(text))
        item.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled | QtCore.Qt.ItemFlag.ItemIsSelectable)
        return item

    def _fill_table(self):
        tw = self.ui.tableWidget
        tw.blockSignals(True)  # Avoid itemChanged while filling.
        tw.setRowCount(len(self.rows))
        dup_brush = QtGui.QBrush(QtGui.QColor(DUPLICATE_COLOR))
        for r, row in enumerate(self.rows):
            ref_dup = bool(row.get("ref_duplicate"))
            attachment = row.get("attachment") or ""
            attach_dup = bool(row.get("attachment_duplicate"))

            # Column 0: checkbox, new ones checked
            check = QtWidgets.QTableWidgetItem()
            check.setFlags(QtCore.Qt.ItemFlag.ItemIsUserCheckable | QtCore.Qt.ItemFlag.ItemIsEnabled |
                           QtCore.Qt.ItemFlag.ItemIsSelectable)
            check.setCheckState(QtCore.Qt.CheckState.Unchecked if ref_dup else QtCore.Qt.CheckState.Checked)
            tw.setItem(r, self.COL_CHECK, check)

            # Column 1: reference label (full text in tooltip)
            ref_item = self._ro_item(row.get("label", ""))
            ref_item.setToolTip(row.get("label", ""))
            tw.setItem(r, self.COL_REFERENCE, ref_item)

            # Column 2: reference status
            status_item = self._ro_item(_("Duplicate") if ref_dup else _("New"))
            if ref_dup:
                status_item.setForeground(dup_brush)
            tw.setItem(r, self.COL_STATUS, status_item)

            # Column 3: attachment name (full text in tooltip)
            attach_name_item = self._ro_item(attachment if attachment else "—")
            if attachment:
                attach_name_item.setToolTip(attachment)
            tw.setItem(r, self.COL_ATTACHMENT, attach_name_item)

            # Column 4: attachment status
            if not attachment:
                attach_status = "—"
            elif attach_dup:
                attach_status = _("Duplicate")
            else:
                attach_status = _("New")
            attach_item = self._ro_item(attach_status)
            if attachment and attach_dup:
                attach_item.setForeground(dup_brush)
            tw.setItem(r, self.COL_ATTACHMENT_STATUS, attach_item)
        tw.blockSignals(False)

        # Short columns fit their content; Reference
        # and Attachment share the rest, so everything fits and the status stays visible.
        header = tw.horizontalHeader()
        Resize = QtWidgets.QHeaderView.ResizeMode
        header.setSectionResizeMode(self.COL_CHECK, Resize.ResizeToContents)
        header.setSectionResizeMode(self.COL_REFERENCE, Resize.Stretch)
        header.setSectionResizeMode(self.COL_STATUS, Resize.ResizeToContents)
        header.setSectionResizeMode(self.COL_ATTACHMENT, Resize.Stretch)
        header.setSectionResizeMode(self.COL_ATTACHMENT_STATUS, Resize.ResizeToContents)

    # ---------------- selection ----------------

    def _set_all(self, checked):
        state = QtCore.Qt.CheckState.Checked if checked else QtCore.Qt.CheckState.Unchecked
        tw = self.ui.tableWidget
        tw.blockSignals(True)
        for r in range(tw.rowCount()):
            item = tw.item(r, self.COL_CHECK)
            if item is not None:
                item.setCheckState(state)
        tw.blockSignals(False)
        self._update_summary()

    def _select_new(self):
        """ Checks only the non-duplicate ones. """
        tw = self.ui.tableWidget
        tw.blockSignals(True)
        for r, row in enumerate(self.rows):
            item = tw.item(r, self.COL_CHECK)
            if item is not None:
                item.setCheckState(QtCore.Qt.CheckState.Unchecked if row.get("ref_duplicate")
                                   else QtCore.Qt.CheckState.Checked)
        tw.blockSignals(False)
        self._update_summary()

    def _toggle_row(self, row, _column):
        """ Double-click a row toggles its checkbox. """
        if _column == self.COL_CHECK:
            # The first click of the double-click already toggled the native checkbox; toggling
            # again would revert it.
            return
        item = self.ui.tableWidget.item(row, self.COL_CHECK)
        if item is None:
            return
        new_state = (QtCore.Qt.CheckState.Unchecked if item.checkState() == QtCore.Qt.CheckState.Checked
                     else QtCore.Qt.CheckState.Checked)
        item.setCheckState(new_state)

    def _on_item_changed(self, item):
        if item.column() == self.COL_CHECK:
            self._update_summary()

    def _update_summary(self):
        total = len(self.rows)
        chosen = len(self.selected_indices())
        self.ui.label_summary.setText(_("Selected: ") + f"{chosen} / {total}")

    # ---------------- results ----------------

    def selected_indices(self):
        """ Indices into rows of the checked rows. """
        tw = self.ui.tableWidget
        out = []
        for r in range(tw.rowCount()):
            item = tw.item(r, self.COL_CHECK)
            if item is not None and item.checkState() == QtCore.Qt.CheckState.Checked:
                out.append(r)
        return out

    def import_attachments(self):
        """ True if attachments are to be imported. """
        return self.ui.checkBox_import_attachments.isChecked()
