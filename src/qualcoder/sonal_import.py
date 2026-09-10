# -*- coding: utf-8 -*-

"""
This file is part of QualCoder.

QualCoder is free software: you can redistribute it and/or modify it under the
terms of the GNU Lesser General Public License as published by the Free Software
Foundation, either version 3 of the license, or (at your option) any later version.

QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with QualCoder.
If not, see <https://www.gnu.org/licenses/>.

Authors: Colin Curtain C, Kai Droege, Justin Missaghieh--Poncet, Lorenzo Salomon
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
https://qualcoder.org/
"""

import datetime
import json
import logging
import os
import re
import sqlite3
import tempfile
import zipfile
from html.parser import HTMLParser

from PyQt6 import QtWidgets

from .helpers import Message

logger = logging.getLogger(__name__)


class SonalImport:
    """ Import a Sonal (SonalPi) project into a new QualCoder database.

    A Sonal corpus is described by a ``.crp`` JSON file (thematiques/categories,
    variables, dictionary and the list of interviews) that references one
    ``.sonal`` file per interview. The whole corpus may be bundled as a
    ``.zip`` archive, or the ``.crp`` and ``.sonal`` files may live together in
    a folder.

    Each ``.sonal`` file is an HTML document. The transcription lives inside a
    ``<div id="contenuText">`` container, split into segments
    (``<span class="lblseg ...">``) that hold word spans
    (``<span data-rk=".." ...>word</span>``). Codes/categories ("thematiques")
    are stored as CSS classes (``cat_001`` ...) applied to the word spans.
    """

    def __init__(self, app, parent_textedit):
        super(SonalImport, self).__init__()

        self.app = app
        self.parent_textEdit = parent_textedit
        response = QtWidgets.QFileDialog.getOpenFileName(
            None, _('Select Sonal corpus file'),
            self.app.settings['directory'],
            "Sonal corpus (*.crp *.zip)")
        if response[0] == "":
            return
        self.selected_path = response[0]
        self.parent_textEdit.append(_('Beginning import from Sonal project'))
        self.parent_textEdit.append(self.selected_path)
        try:
            self.load_and_import()
            if self.app.settings['ai_enable'] == 'True':
                self.app.ai.sources_vectorstore.update_vectorstore()
        except Exception as exc:
            logger.warning("Sonal import failed", exc_info=True)
            self.parent_textEdit.append(
                _('Data import unsuccessful from ') + f"{self.selected_path}\n{exc}")

    def load_and_import(self):
        """ Resolve the corpus ``.crp`` JSON and the ``.sonal`` files.

        The user may select either a ``.crp`` file (the ``.sonal`` files are then
        expected next to it in the same folder) or a ``.zip`` archive that
        bundles the ``.crp`` together with the ``.sonal`` files.
        """

        ext = os.path.splitext(self.selected_path)[1].lower()
        if ext == ".zip":
            self.import_from_zip(self.selected_path)
        else:
            folder = os.path.dirname(self.selected_path)
            with open(self.selected_path, 'r', encoding='utf-8-sig') as fh:
                corpus_json = json.load(fh)
            self.import_corpus(corpus_json, folder)

    def import_from_zip(self, zip_path):
        """ Extract a Sonal ``.zip`` archive to a temporary folder and import it. """

        with tempfile.TemporaryDirectory() as tmp_dir:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(tmp_dir)
            crp_path = None
            for name in os.listdir(tmp_dir):
                if name.lower().endswith(".crp"):
                    crp_path = os.path.join(tmp_dir, name)
                    break
            if crp_path is None:
                self.parent_textEdit.append(
                    _("No .crp file found inside the selected archive"))
                return
            with open(crp_path, 'r', encoding='utf-8-sig') as fh:
                corpus_json = json.load(fh)
            self.import_corpus(corpus_json, tmp_dir)

    def import_corpus(self, corpus_json, base_folder):
        """ Drive the import once the corpus JSON and base folder are known.

        Args:
            corpus_json : dict with tabThm, tabVar, tabDic, tabEnt keys
            base_folder : folder containing the referenced ``.sonal`` files
        """

        cur_qc = self.app.conn.cursor()
        owner = self.app.settings['codername']
        nowdate = datetime.datetime.now().astimezone().strftime("%Y%m%d_%H")

        tab_thm = corpus_json.get("tabThm", []) or []
        tab_var = corpus_json.get("tabVar", []) or []
        tab_dic = corpus_json.get("tabDic", []) or []
        tab_ent = corpus_json.get("tabEnt", []) or []

        # Project memo
        cur_qc.execute("update project set memo=?", ["Migrated from Sonal."])
        self.app.conn.commit()
        self.parent_textEdit.append(_("Project memo imported"))

        cid_by_code = self.import_thematiques(cur_qc, tab_thm, owner, nowdate)

        attr_name_by_v, dic_label_by_vm = self.import_variables(
            cur_qc, tab_var, tab_dic, owner, nowdate)

        nb_docs = 0
        nb_codings = 0
        nb_skipped = 0
        for ent in tab_ent:
            rtr_path = ent.get("rtrPath", "")
            name = ent.get("nom", "")
            if not name:
                name = os.path.splitext(os.path.basename(rtr_path))[0]
            sonal_path = os.path.join(base_folder, rtr_path)
            if not os.path.isfile(sonal_path):
                self.parent_textEdit.append(
                    _("Sonal file not found, skipped: ") + rtr_path)
                nb_skipped += 1
                continue
            with open(sonal_path, 'r', encoding='utf-8-sig') as fh:
                sonal_html = fh.read()

            fulltext, codings, tab_dat, notes = self.parse_sonal_html(
                sonal_html, cid_by_code)

            fid, inserted = self.insert_source(
                cur_qc, name, fulltext, notes, owner, nowdate)
            if not inserted:
                continue
            nb_docs += 1
            self.app.conn.commit()

            # Import attribute values for this interview (tabDat).
            for dat in tab_dat or []:
                v = dat.get("v")
                m = dat.get("m")
                attr_name = attr_name_by_v.get(v)
                if attr_name is None or m is None:
                    continue
                value = dic_label_by_vm.get((v, m), str(m))
                try:
                    cur_qc.execute(
                        "insert into attribute (name, value, id, owner, date, "
                        "attr_type) values (?,?,?,?,?,?)",
                        [attr_name, value, fid, owner, nowdate, "file"])
                except sqlite3.IntegrityError:
                    pass
            self.app.conn.commit()

            # Insert codings (cid, seltext, pos0, pos1) for this document.
            for cid, seltext, pos0, pos1 in codings:
                try:
                    cur_qc.execute(
                        "insert into code_text (cid, fid, seltext, pos0, pos1, "
                        "memo, owner, date) values (?,?,?,?,?,?,?,?)",
                        [cid, fid, seltext, pos0, pos1, "", owner, nowdate])
                    nb_codings += 1
                except sqlite3.IntegrityError:
                    pass
            self.app.conn.commit()

        self.parent_textEdit.append(str(nb_docs) + _(" documents imported"))
        self.parent_textEdit.append(str(nb_codings) + _(" codings imported"))
        if nb_skipped:
            self.parent_textEdit.append(
                str(nb_skipped) + _(" Sonal files not found and skipped"))
        self.parent_textEdit.append(_("Sonal project imported"))
        Message(self.app, _("Sonal imported"), _("Sonal imported")).exec()
        self.app.write_config_ini(self.app.settings, self.app.ai_models)

    def import_thematiques(self, cur_qc, tab_thm, owner, nowdate):
        """ Import Sonal thematiques as QualCoder codes and categories.

        Sonal thematiques form a tree through the ``rang`` indentation level
        (0 = top level). Parent thematiques become QualCoder categories; every
        thematique also becomes a code, placed in its parent's category.

        Returns:
            cid_by_code : mapping of Sonal category code -> QualCoder code id
        """

        ordered_thm = list(tab_thm)
        # Build the parent map from the rang indentation hierarchy.
        parent_of = {}
        stack = []  # list of (rang, code)
        for thm in ordered_thm:
            try:
                rang = int(thm.get("rang", 0) or 0)
            except (TypeError, ValueError):
                rang = 0
            code = thm.get("code", "")
            while stack and stack[-1][0] >= rang:
                stack.pop()
            parent_of[code] = stack[-1][1] if stack else None
            stack.append((rang, code))

        # A thematique is a category holder when at least one other thematique
        # declares it as its parent.
        has_children = set()
        for code, parent in parent_of.items():
            if parent is not None:
                has_children.add(parent)

        # Create categories for the holder thematiques.
        catid_by_code = {}
        for thm in ordered_thm:
            code = thm.get("code", "")
            if not code or code not in has_children:
                continue
            name = thm.get("nom", code)
            try:
                cur_qc.execute(
                    "insert into code_cat (name, owner, date, memo, supercatid) "
                    "values (?,?,?,?,?)",
                    [name, owner, nowdate, thm.get("description", "") or "", None])
                catid_by_code[code] = cur_qc.lastrowid
            except sqlite3.IntegrityError:
                cur_qc.execute("select catid from code_cat where name=?", [name])
                row = cur_qc.fetchone()
                catid_by_code[code] = row[0] if row else None

        # Set the category hierarchy (supercatid) from the parent map.
        for thm in ordered_thm:
            code = thm.get("code", "")
            catid = catid_by_code.get(code)
            if catid is None:
                continue
            parent = parent_of.get(code)
            parent_catid = catid_by_code.get(parent) if parent else None
            if parent_catid is not None:
                cur_qc.execute(
                    "update code_cat set supercatid=? where catid=?",
                    [parent_catid, catid])
        self.app.conn.commit()
        self.parent_textEdit.append(
            str(len(catid_by_code)) + _(" code categories imported"))

        # Create a code for every thematique, placed in its parent's category.
        cid_by_code = {}
        default_color = "#DDE600"
        for thm in ordered_thm:
            code = thm.get("code", "")
            if not code:
                continue
            name = thm.get("nom", code)
            color = thm.get("couleur", "") or default_color
            parent = parent_of.get(code)
            catid = catid_by_code.get(parent) if parent else None
            try:
                cur_qc.execute(
                    "insert into code_name (name, memo, catid, owner, date, color) "
                    "values (?,?,?,?,?,?)",
                    [name, thm.get("description", "") or "", catid, owner, nowdate,
                     color])
                cid_by_code[code] = cur_qc.lastrowid
            except sqlite3.IntegrityError:
                cur_qc.execute("select cid from code_name where name=?", [name])
                row = cur_qc.fetchone()
                cid_by_code[code] = row[0] if row else None
        self.app.conn.commit()
        self.parent_textEdit.append(str(len(cid_by_code)) + _(" codes imported"))
        return cid_by_code

    def import_variables(self, cur_qc, tab_var, tab_dic, owner, nowdate):
        """ Import Sonal variables (tabVar) and dictionary (tabDic) as attributes.

        Returns:
            attr_name_by_v : mapping of variable id -> attribute name
            dic_label_by_vm: mapping of (variable id, modality id) -> label
        """

        attr_name_by_v = {}
        for var in tab_var:
            v = var.get("v")
            lib = var.get("lib", "")
            if v is None or not lib:
                continue
            try:
                cur_qc.execute(
                    "insert into attribute_type (name, valuetype, caseOrFile, memo, "
                    "owner, date) values (?,?,?,?,?,?)",
                    [lib, "character", "file", "", owner, nowdate])
            except sqlite3.IntegrityError:
                pass
            attr_name_by_v[v] = lib
        self.app.conn.commit()
        self.parent_textEdit.append(
            str(len(attr_name_by_v)) + _(" attribute types imported"))

        dic_label_by_vm = {}
        for entry in tab_dic:
            v = entry.get("v")
            m = entry.get("m")
            lib = entry.get("lib")
            if v is not None and m is not None and lib:
                dic_label_by_vm[(v, m)] = lib
        return attr_name_by_v, dic_label_by_vm

    def insert_source(self, cur_qc, name, fulltext, notes, owner, nowdate):
        """ Insert a transcription as a QualCoder source, handling name clashes.

        Returns:
            (fid, inserted) where inserted is False if the source could not be
            created.
        """

        memo = notes or ""
        try:
            cur_qc.execute(
                "insert into source (name, fulltext, memo, owner, date, mediapath) "
                "values (?,?,?,?,?,?)",
                [name, fulltext, memo, owner, nowdate, None])
            return cur_qc.lastrowid, True
        except sqlite3.IntegrityError:
            pass
        # Duplicate file name: append a counter until it is unique.
        i = 1
        while True:
            unique_name = f"{name}_{i}"
            cur_qc.execute("select id from source where name=?", [unique_name])
            if cur_qc.fetchone() is not None:
                i += 1
                continue
            try:
                cur_qc.execute(
                    "insert into source (name, fulltext, memo, owner, date, "
                    "mediapath) values (?,?,?,?,?,?)",
                    [unique_name, fulltext, memo, owner, nowdate, None])
                return cur_qc.lastrowid, True
            except sqlite3.IntegrityError:
                i += 1

    def parse_sonal_html(self, html_text, cid_by_code):
        """ Parse a ``.sonal`` HTML document.

        Rebuild the plain transcription text from the word spans while tracking
        the character position of every span, then turn the ``cat_XXX`` classes
        carried by each word span into contiguous (cid, seltext, pos0, pos1)
        codings.

        Args:
            html_text  : full content of the ``.sonal`` file
            cid_by_code: mapping of Sonal category code -> QualCoder code id
        Returns:
            (fulltext, codings, tab_dat, notes)
            fulltext  : reconstructed plain text
            codings   : list of (cid, seltext, pos0, pos1)
            tab_dat   : list of attribute value entries for this interview
            notes     : interview notes string (may be "")
        """

        tab_dat = []
        json_blocks = self._extract_script_blocks(html_text)
        dat_json = json_blocks.get("dat-json")
        if dat_json:
            try:
                parsed = json.loads(dat_json)
                if isinstance(parsed, dict):
                    tab_dat = parsed.get("tabDat", []) or []
                elif isinstance(parsed, list):
                    tab_dat = parsed
            except json.JSONDecodeError:
                tab_dat = []

        notes = self._extract_notes(html_text)
        contenu = self._extract_contenu_text(html_text)

        parser = _SonalContentParser(cid_by_code)
        parser.feed(contenu)
        parser.close()
        fulltext = parser.fulltext
        codings = self._merge_codings(fulltext, parser.ranges_by_code)
        return fulltext, codings, tab_dat, notes

    def _merge_codings(self, fulltext, ranges_by_code):
        """ Merge contiguous/overlapping ranges per code into codings. """

        codings = []
        for cid, ranges in ranges_by_code.items():
            ranges.sort()
            merged = []
            for start, end in ranges:
                if merged and start <= merged[-1][1]:
                    m_start, _ = merged[-1]
                    new_end = max(merged[-1][1], end)
                    merged[-1] = (m_start, new_end)
                else:
                    merged.append((start, end))
            for start, end in merged:
                if end > start:
                    codings.append((cid, fulltext[start:end], start, end))
        return codings

    @staticmethod
    def _extract_script_blocks(html_text):
        """ Return a dict of ``id -> json text`` for every
        ``<script id="*-json" type="application/json">`` block. """

        blocks = {}
        pattern = re.compile(
            r'<script[^>]*id="([^"]*-json)"[^>]*>(.*?)</script>',
            re.DOTALL | re.IGNORECASE)
        for match in pattern.finditer(html_text):
            blocks[match.group(1)] = match.group(2).strip()
        return blocks

    @staticmethod
    def _extract_notes(html_text):
        """ Extract the interview notes from the ``#txtnotes`` div. """

        match = re.search(
            r'<div[^>]*id="txtnotes"[^>]*>(.*?)</div>',
            html_text, re.DOTALL | re.IGNORECASE)
        if not match:
            return ""
        inner = re.sub(r'<[^>]+>', '', match.group(1))
        return inner.strip()

    @staticmethod
    def _extract_contenu_text(html_text):
        """ Extract the inner HTML of the ``<div id="contenuText">`` container. """

        match = re.search(
            r'<div[^>]*id="contenuText"[^>]*>(.*)',
            html_text, re.DOTALL | re.IGNORECASE)
        if not match:
            return ""
        inner = match.group(1)
        body_match = re.search(r'</body>', inner, re.IGNORECASE)
        if body_match:
            inner = inner[:body_match.start()]
        return inner


class _SonalContentParser(HTMLParser):
    """ Walk the segment/word spans and rebuild plain text + coded ranges.

    The Sonal structure is::

        <span class="lblseg ..." ...>
            <span class="ligloc" ...>Speaker</span>
            <span data-rk="1" ... class="cat_001">word</span>
            <span data-rk="2" ...>word2</span>
            ...
        </span>

    Word spans carry coded text through ``cat_XXX`` CSS classes. The lblseg
    container and the ligloc/anon helper spans are walked but only the word
    spans contribute codings; ligloc (speaker) and anon (anonymised) spans
    contribute their text so the transcription stays readable.
    """

    def __init__(self, cid_by_code):
        super().__init__(convert_charrefs=True)
        self.cid_by_code = cid_by_code
        self.fulltext_parts = []
        self._fulltext_len = 0
        # Stack of open span frames: {"word": bool, "text": bool, "start": int,
        #                             "codes": [cid, ...]}
        self.stack = []
        # cid -> list of (start, end) character ranges in the rebuilt text.
        self.ranges_by_code = {}

    @property
    def fulltext(self):
        text = "".join(self.fulltext_parts)
        # Normalise non-breaking / narrow no-break spaces to regular spaces.
        # Single-character to single-character, so positions are preserved.
        return text.replace("\xa0", " ").replace("\u202F", " ")

    def handle_starttag(self, tag, attrs):
        if tag != "span":
            return
        ad = dict(attrs)
        classes = (ad.get("class") or "").split()
        is_lblseg = "lblseg" in classes
        if is_lblseg and self.fulltext_parts:
            # Insert a line break between segments so words do not run together.
            self.fulltext_parts.append("\n")
            self._fulltext_len += 1
        is_word = ("data-rk" in ad) and not is_lblseg and ("ligloc" not in classes)
        # Anything that is not the lblseg container contributes its text.
        produces_text = not is_lblseg
        frame = {
            "word": is_word,
            "text": produces_text,
            "ligloc": "ligloc" in classes,
            "start": self._fulltext_len if produces_text else None,
            "codes": [],
        }
        if is_word:
            for cls in classes:
                if cls.startswith("cat_"):
                    cid = self.cid_by_code.get(cls)
                    if cid is not None:
                        frame["codes"].append(cid)
        self.stack.append(frame)

    def handle_startendtag(self, tag, attrs):
        # Self-closing span (rare): treat as a full open+close.
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag != "span" or not self.stack:
            return
        frame = self.stack.pop()
        if not frame["text"]:
            return
        end = self._fulltext_len
        for cid in frame["codes"]:
            self.ranges_by_code.setdefault(cid, []).append((frame["start"], end))
        if frame.get("ligloc") and not self.fulltext_parts[-1].endswith(("\n", " ")):
            # Separate the speaker label from the words that follow.
            self.fulltext_parts.append(" ")
            self._fulltext_len += 1

    def handle_data(self, data):
        if not self.stack:
            return
        frame = self.stack[-1]
        if not frame["text"]:
            return
        self.fulltext_parts.append(data)
        self._fulltext_len += len(data)
