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

# EXPERIMENTAL. Imports references from a local Zotero install (7 or newer) using its
# local HTTP API (read-only, no authentication). Imports references and optionally their PDF
# attachments, linking them to their reference.

import datetime
import json
import logging
import os
import re
import shutil
import tempfile
import urllib.request

from PyQt6 import QtWidgets, QtCore

from rispy import TAG_KEY_MAPPING

from .helpers import Message
from .manage_references_import import import_progress_dialog

logger = logging.getLogger(__name__)

# Local Zotero API (user library = users/0).
ZOTERO_BASE = "http://localhost:23119/api/users/0"
HTTP_TIMEOUT = 8

# Zotero itemType -> RIS TY code
TYPE_MAP = {
    "journalArticle": "JOUR", "book": "BOOK", "bookSection": "CHAP",
    "conferencePaper": "CONF", "thesis": "THES", "report": "RPRT",
    "magazineArticle": "MGZN", "newspaperArticle": "NEWS", "webpage": "ELEC",
    "blogPost": "ELEC", "manuscript": "UNPB", "patent": "PAT", "preprint": "JOUR",
    "encyclopediaArticle": "CHAP", "dictionaryEntry": "CHAP",
    "presentation": "GEN", "document": "GEN",
}


class ZoteroImport:
    """
    Imports references (and optionally PDF attachments) from a local Zotero via its HTTP API.
    """

    def __init__(self, app, parent_text_edit, refs_dialog):
        """
        refs_dialog: refs_dialog: the DialogReferenceManager instance, reused for the PDF
        import and linking.
        """
        self.app = app
        self.parent_text_edit = parent_text_edit
        self.refs_dialog = refs_dialog

    # local API

    def _emit_project_table_changes(self, tables):
        """Notify other open dialogs about changed project tables."""

        if getattr(self.app, "project_events", None) is not None:
            self.app.project_events.emit_table_changes(tables, source=self)

    def _get(self, path, want_json=True):
        """
        GET to the local Zotero API. Returns json, bytes, or None on failure.
        """
        url = ZOTERO_BASE + path
        try:
            req = urllib.request.Request(url, headers={
                "Zotero-API-Version": "3",
                "zotero-allowed-request": "1"})  # avoids the 403 "Request not allowed"
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                data = resp.read()
            if want_json:
                return json.loads(data.decode("utf-8"))
            return data
        except Exception as err:
            logger.warning(f"Zotero local API GET failed: {url} : {err}")
            return None

    def _api_available(self):
        """
        True if Zotero is open and its API answers.
        """
        return self._get("/items?limit=1&format=json") is not None

    def _fetch_collections(self):
        """
        List of collections as (key, name).
        """
        cols = self._get("/collections?format=json&limit=100")
        out = []
        if cols:
            for c in cols:
                d = c.get("data", {})
                out.append((c.get("key", d.get("key", "")), d.get("name", "")))
        return out

    def _fetch_top_items(self, collection_key=None, progress_cb=None):
        """
        Fetches all top-level items, paginated; progress_cb(n) is called after each page with
        the running total, for feedback on large libraries.
        """
        items = []
        start = 0
        limit = 100
        base = f"/collections/{collection_key}/items/top" if collection_key else "/items/top"
        while True:
            batch = self._get(f"{base}?format=json&limit={limit}&start={start}")
            if not batch:
                break
            items.extend(batch)
            if progress_cb:
                progress_cb(len(items))
            if len(batch) < limit:
                break
            start += limit
            if start > 100000:  # tope de seguridad. Safety cap.
                break
        return items

    def _fetch_attachments(self, progress_cb=None):
        """
        progress_cb(n) recibe el total acumulado. Fetches all library attachments in one
        paginated sweep, to map them to their parent reference without a per-reference call.
        """
        items = []
        start = 0
        limit = 100
        while True:
            batch = self._get(f"/items?format=json&itemType=attachment&limit={limit}&start={start}")
            if not batch:
                break
            items.extend(batch)
            if progress_cb:
                progress_cb(len(items))
            if len(batch) < limit:
                break
            start += limit
            if start > 200000:  # tope de seguridad. Safety cap.
                break
        return items

    # Zotero to RIS mapping

    def _creators_to_tags(self, creators):
        """
        Divide creadores en autores (AU) y editores (A2), unidos con "; ". Splits creators into
        authors (AU) and editors (A2), joined with "; ".
        """
        authors = []
        editors = []
        for c in creators or []:
            if c.get("lastName") or c.get("firstName"):
                name = c.get("lastName") or ""  # the key may exist holding None
                if c.get("firstName"):
                    name = f"{name}, {c.get('firstName') or ''}".strip(", ")
            else:
                name = c.get("name", "")
            if not name:
                continue
            if c.get("creatorType") == "editor":
                editors.append(name)
            else:
                authors.append(name)
        tags = []
        if authors:
            tags.append(("AU", "; ".join(authors)))
        if editors:
            tags.append(("A2", "; ".join(editors)))
        return tags

    def _item_to_ris_tags(self, data):
        """
        Converts a Zotero item data dict into RIS (tag, value) pairs.
        """
        tags = [("TY", TYPE_MAP.get(data.get("itemType", ""), "GEN"))]
        if data.get("title"):
            tags.append(("TI", data["title"]))
        tags.extend(self._creators_to_tags(data.get("creators")))
        # Year (4 digits) and full date.
        date_ = data.get("date", "")
        if date_:
            m = re.search(r"\d{4}", date_)
            if m:
                tags.append(("PY", m.group(0)))
            tags.append(("DA", date_))
        # Journal or secondary title (book, proceedings)
        if data.get("publicationTitle"):
            tags.append(("JO", data["publicationTitle"]))
        for k in ("bookTitle", "proceedingsTitle", "encyclopediaTitle", "dictionaryTitle"):
            if data.get(k):
                tags.append(("T2", data[k]))
                break
        if data.get("series"):
            tags.append(("T3", data["series"]))
        if data.get("volume"):
            tags.append(("VL", data["volume"]))
        if data.get("issue"):
            tags.append(("IS", data["issue"]))
        # Pages: split start and end
        pages = data.get("pages", "")
        if pages:
            pages_norm = pages.replace("\u2013", "-").replace("\u2014", "-")
            pp = re.split(r"\s*-\s*", pages_norm, maxsplit=1)
            tags.append(("SP", pp[0].strip()))
            if len(pp) > 1 and pp[1].strip():
                tags.append(("EP", pp[1].strip()))
        if data.get("publisher"):
            tags.append(("PB", data["publisher"]))
        if data.get("place"):
            tags.append(("CY", data["place"]))
        if data.get("ISBN"):
            tags.append(("SN", data["ISBN"]))
        elif data.get("ISSN"):
            tags.append(("SN", data["ISSN"]))
        if data.get("DOI"):
            tags.append(("DO", data["DOI"]))
        if data.get("url"):
            tags.append(("UR", data["url"]))
        if data.get("abstractNote"):
            tags.append(("AB", data["abstractNote"]))
        if data.get("language"):
            tags.append(("LA", data["language"]))
        if data.get("edition"):
            tags.append(("ET", data["edition"]))
        kw = [t.get("tag", "") for t in data.get("tags", []) if t.get("tag")]
        if kw:
            tags.append(("KW", "; ".join(kw)))
        return tags

    def _insert_reference(self, item, risid, commit=True):
        """
        Inserts the ris rows for one reference; commit=False defers the commit for fast batch
        inserts.
        """
        data = item.get("data", {})
        cur = self.app.conn.cursor()
        for tag, value in self._item_to_ris_tags(data):
            if value is None or str(value) == "":
                continue
            longtag = TAG_KEY_MAPPING.get(tag, tag.lower())
            cur.execute("insert into ris (risid, tag, longtag, value) values (?,?,?,?)",
                        [risid, tag, longtag, str(value)])
        if commit:
            self.app.conn.commit()
        self._emit_project_table_changes(['ris'])

    def _ensure_ref_attributes(self):
        """
        Creates the Ref_* attribute types if missing (as ris.RisImport.create_file_attributes).
        """
        now_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur = self.app.conn.cursor()
        ref_vars = {'Ref_Authors': 'character', 'Ref_Title': 'character', 'Ref_Type': 'character',
                    'Ref_Year': 'numeric', 'Ref_Journal': 'character'}
        for key in ref_vars:
            cur.execute("select name from attribute_type where name=?", [key])
            if not cur.fetchone():
                cur.execute("insert into attribute_type (name,date,owner,memo,caseOrFile,valuetype) "
                            "values(?,?,?,?,?,?)",
                            (key, now_date, self.app.settings['codername'], "", 'file', ref_vars[key]))
        self.app.conn.commit()
        self.app.delete_backup = False
        self._emit_project_table_changes(['attribute_type'])

    # PDF attachments

    def _doc_attachments(self, attachments):
        """
        All PDF/EPUB attachments from a list of attachment 'data' dicts (from the parent map).
        A reference may have several; all are imported, as in the .ris import.
        """

        out = []
        for d in attachments:
            if d.get("itemType") != "attachment":
                continue
            ct = (d.get("contentType") or "").lower()
            fn = (d.get("filename") or d.get("title") or "").lower()
            if ct in ("application/pdf", "application/epub+zip") or fn.endswith((".pdf", ".epub")):
                out.append(d)
        return out

    def _attachment_filename(self, attach):
        """
        Target file name for the attachment, without downloading it (to detect duplicates).
        """
        if attach.get("linkMode") == "linked_file" and attach.get("path"):
            return os.path.basename(attach["path"].replace("\\", "/"))
        filename = attach.get("filename") or attach.get("title") or "attachment"
        low = filename.lower()
        if not (low.endswith(".pdf") or low.endswith(".epub")):
            ct = (attach.get("contentType") or "").lower()
            filename += ".epub" if "epub" in ct else ".pdf"
        return filename

    def _attachment_to_local_file(self, attach, tmp_dir=None):
        """
        Returns a local path to the attachment file (PDF or EPUB), or None. Downloads via the
        API, or uses a linked file path, or the default Zotero storage folder.
        """
        filename = self._attachment_filename(attach)
        # Linked external file: use its path
        if attach.get("linkMode") == "linked_file" and attach.get("path"):
            p = attach["path"]
            if os.path.isfile(p) and p.lower().endswith((".pdf", ".epub")):
                return p
        key = attach.get("key", "")
        # Download via the local API.
        if key:
            blob = self._get(f"/items/{key}/file", want_json=False)
            if blob:
                try:
                    # One temp dir per session (created by run(), cleaned at the end); before, one
                    # mkdtemp per attachment was created and never removed.
                    base_dir = tmp_dir if tmp_dir else tempfile.mkdtemp(prefix="qc_zotero_")
                    tmp_path = os.path.join(base_dir, filename)
                    with open(tmp_path, "wb") as f:
                        f.write(blob)
                    return tmp_path
                except Exception as err:
                    logger.warning(f"Zotero attachment write failed: {err}")
            # Fallback: default Zotero storage folder
            guess = os.path.join(os.path.expanduser("~"), "Zotero", "storage", key, filename)
            if os.path.isfile(guess):
                return guess
        return None

    # main flow 

    def _item_label(self, data):
        """
        Readable label of a Zotero reference for the duplicate message.
        """
        title = data.get("title") or _("(untitled)")
        author = ""
        creators = data.get("creators") or []
        if creators:
            c = creators[0]
            author = c.get("lastName") or c.get("name") or ""
        year = ""
        m = re.search(r"\d{4}", data.get("date", "") or "")
        if m:
            year = m.group(0)
        label = title
        if author:
            label = author + " - " + label
        if year:
            label += f" ({year})"
        return label

    def run(self):
        """
        Entry point: checks the API, chooses scope, and opens the preview dialog with the
        reference list, checkboxes to choose which to import, and the duplicate status of each
        reference and its attachment. Inserts only the chosen ones.
        """
        if not self._api_available():
            Message(self.app, _("Zotero import"),
                    _("Could not connect to the local Zotero API.") + "\n\n" +
                    _("Requirements:") + "\n" +
                    _("- Zotero open and running (version 7 or newer).") + "\n" +
                    _("- Enable the local API in Zotero: Settings, Advanced, General, and check "
                      "'Allow other applications on this computer to communicate with Zotero'.") + "\n" +
                    _("- If you cannot find that option: Settings, Advanced, Config Editor, set "
                      "extensions.zotero.httpServer.enabled to true.") + "\n" +
                    _("Then restart Zotero."),
                    "warning").exec()
            return
        collection_key = self._choose_scope()
        if collection_key is False:  # cancelado. Cancelled.
            return

        # Fetch top-level references with a progress dialog.
        fetch_progress = QtWidgets.QProgressDialog(
            _("Fetching references from Zotero..."), None, 0, 0, self.refs_dialog)
        fetch_progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        fetch_progress.setWindowTitle(_("Zotero import"))
        fetch_progress.setMinimumDuration(0)
        fetch_progress.show()

        def _on_fetch_refs(count):
            fetch_progress.setLabelText(_("References fetched: ") + str(count))
            QtWidgets.QApplication.processEvents()

        items = self._fetch_top_items(collection_key if collection_key else None, _on_fetch_refs)
        if not items:
            fetch_progress.setRange(0, 1)
            fetch_progress.setValue(1)
            Message(self.app, _("Zotero import"), _("No references were found."), "Information").exec()
            return

        # Fetch all attachments in one sweep and map them to their parent reference, to know each
        # reference's attachment without a per-reference HTTP call (which froze on large
        # libraries).
        def _on_fetch_attach(count):
            fetch_progress.setLabelText(_("Attachments scanned: ") + str(count))
            QtWidgets.QApplication.processEvents()

        attachment_items = self._fetch_attachments(_on_fetch_attach)
        fetch_progress.setRange(0, 1)
        fetch_progress.setValue(1)  # Reaches max, auto-closes.
        attach_by_parent = {}
        for att in attachment_items:
            d = att.get("data", {})
            parent = d.get("parentItem")
            if parent:
                attach_by_parent.setdefault(parent, []).append(d)

        # Build the dialog rows: label, reference duplicate, and attachment data.
        existing_sigs = self.refs_dialog._existing_reference_signatures()
        cur = self.app.conn.cursor()
        cur.execute("select lower(name) from source")
        existing_names = set(r[0] for r in cur.fetchall() if r[0] is not None)
        seen_sigs = set()
        seen_attach = set()
        rows = []
        candidates = []  # paralelo a rows: (item, [adjuntos]). Parallel to rows: (item, [attachments]).
        any_attachment = False
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        try:
            for i, it in enumerate(items):
                data = it.get("data", {})
                sig = self.refs_dialog._reference_signature(self._item_to_ris_tags(data))
                ref_dup = bool(sig) and (sig in existing_sigs or sig in seen_sigs)
                if sig:
                    seen_sigs.add(sig)
                attaches = self._doc_attachments(attach_by_parent.get(it.get("key", ""), []))
                attach_label = ""
                attach_dup = False
                if attaches:
                    any_attachment = True
                    names = [self._attachment_filename(a) for a in attaches]
                    # Label: first name, plus "(+N)" if more
                    attach_label = names[0] if len(names) == 1 else f"{names[0]} (+{len(names) - 1})"
                    for nm in names:
                        low = nm.lower()
                        if low in existing_names or low in seen_attach:
                            attach_dup = True
                        else:
                            seen_attach.add(low)
                rows.append({"label": self._item_label(data), "ref_duplicate": ref_dup,
                             "attachment": attach_label, "attachment_duplicate": attach_dup})
                candidates.append((it, attaches))
                if i % 200 == 0:
                    QtWidgets.QApplication.processEvents()
        finally:
            # In a finally: a failure midway must not leave the wait cursor stuck
            QtWidgets.QApplication.restoreOverrideCursor()

        # Preview dialog with checkboxes.
        from .manage_references_import import DialogImportReferences
        dialog = DialogImportReferences(self.app, self.refs_dialog, rows,
                                        allow_attachments=any_attachment, attachments_default=any_attachment)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            dialog.deleteLater()
            return
        selected = sorted(dialog.selected_indices())
        want_attachments = dialog.import_attachments()
        dialog.deleteLater()  # One per import, not kept.
        if not selected:
            Message(self.app, _("Zotero import"), _("No references were selected."), "Information").exec()
            return
        chosen = [candidates[i] for i in selected]  # [(item, [adjuntos]), ...]. [(item, [attachments]), ...].

        # Insert the chosen references with a progress bar and a single commit at the end.
        self._ensure_ref_attributes()
        cur.execute("select coalesce(max(risid), 0) from ris")
        next_risid = cur.fetchone()[0]
        pairs = []  # (risid, [adjuntos]). (risid, [attachments]).
        if chosen:
            insert_progress = QtWidgets.QProgressDialog(
                _("Importing references"), None, 0, len(chosen), self.refs_dialog)
            insert_progress.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
            insert_progress.setWindowTitle(_("Zotero import"))
            insert_progress.setMinimumDuration(0)
            insert_progress.show()
            done = 0
            for it, attaches in chosen:
                next_risid += 1
                self._insert_reference(it, next_risid, commit=False)
                pairs.append((next_risid, attaches))
                done += 1
                if done % 25 == 0 or done == len(chosen):
                    insert_progress.setValue(done)
                    QtWidgets.QApplication.processEvents()
            self.app.conn.commit()  # Single commit for all refs.
        self.refs_dialog.get_data()

        # Download and link all attachments of each chosen reference (if requested); repeated names
        # become numbered copies.
        linked = 0
        not_retrieved = 0
        if want_attachments:
            to_link = [(risid, atts) for risid, atts in pairs if atts]
            total = sum(len(atts) for _risid, atts in to_link)
            if total:
                tmp_dir = tempfile.mkdtemp(prefix="qc_zotero_")  # directorio unico de sesion. Single session dir.
                first_name = self._attachment_filename(to_link[0][1][0])
                progress = import_progress_dialog(self.refs_dialog, total, first_name)
                done = 0
                try:
                    for risid, atts in to_link:
                        for att in atts:
                            QtWidgets.QApplication.processEvents()
                            done += 1
                            progress.setValue(done)
                            path_ = self._attachment_to_local_file(att, tmp_dir)
                            if not path_:
                                not_retrieved += 1
                                continue
                            progress.setLabelText(os.path.basename(path_.replace("\\", "/")))
                            fid = self.refs_dialog._import_attachment_file(path_, progress,
                                                                           notify=False)
                            if fid is None:
                                not_retrieved += 1
                                continue
                            # Silenced per attachment: one event after the batch
                            self.refs_dialog.link_reference_to_files(risid, fid, notify=False)
                            linked += 1
                finally:
                    # In a finally: a failure midway must leave neither the bar stuck
                    # nor the temp dir behind.
                    progress.close()
                    progress.deleteLater()
                    shutil.rmtree(tmp_dir, ignore_errors=True)
                if linked > 0 and getattr(self.app, "project_events", None) is not None:
                    # One event for the whole attachment batch, not one per file
                    self.app.project_events.emit_table_changes(['source', 'attribute'], source=None)
        self.refs_dialog.get_data()

        msg = _("References imported: ") + f"{len(pairs)}"
        if want_attachments:
            msg += "\n" + _("Attachments linked: ") + f"{linked}"
            if not_retrieved:
                msg += "\n" + _("Attachments not retrieved: ") + f"{not_retrieved}"
        Message(self.app, _("Zotero import"), msg, "Information").exec()

    def _choose_scope(self):
        """
        Returns the chosen collection key, "" for the whole library, or False if cancelled.
        """
        cols = self._fetch_collections()
        if not cols:
            return ""  # sin colecciones: biblioteca completa. No collections: whole library.
        options = [_("Whole library")]
        keys = [""]
        for key, name in sorted(cols, key=lambda x: (x[1] or "").lower()):
            options.append(name)
            keys.append(key)
        choice, ok = QtWidgets.QInputDialog.getItem(
            self.refs_dialog, _("Zotero import"), _("Import from:"), options, 0, False)
        if not ok:
            return False
        return keys[options.index(choice)]
