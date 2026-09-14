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
Improvements to this script : M Beligné
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


def _normalise_id(value):
    """Normalise IDs that Sonal may serialise as either numbers or strings."""
    return "" if value is None else str(value).strip()


def _speaker_name(name):
    """Remove the trailing question mark used by Sonal to mark interviewers."""
    name = str(name or "").strip()
    return name[:-1].rstrip() if name.endswith("?") else name


def _speaker_roles(tab_loc):
    """Return interviewer and interviewee indexes using Sonal's naming rule."""
    interviewers = []
    interviewees = []
    for index, name in enumerate(tab_loc or []):
        if index == 0 or not str(name or "").strip():
            continue
        if str(name).strip().endswith("?"):
            interviewers.append(index)
        else:
            interviewees.append(index)
    return interviewers, interviewees


def _is_inside_folder(path, folder):
    """Return False for traversal paths and paths on another Windows drive."""
    try:
        return os.path.commonpath([folder, path]) == folder
    except ValueError:
        return False


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

        used_thematiques = self.find_used_thematiques(tab_ent, base_folder)
        cid_by_code = self.import_thematiques(
            cur_qc, tab_thm, owner, nowdate, used_thematiques)

        attr_info_by_v, dic_label_by_vm = self.import_variables(
            cur_qc, tab_var, tab_dic, owner, nowdate)

        nb_docs = 0
        nb_codings = 0
        nb_skipped = 0
        for ent in tab_ent:
            rtr_path = ent.get("rtrPath", "")
            name = ent.get("nom", "")
            if not name:
                name = os.path.splitext(os.path.basename(rtr_path))[0]
            base_path = os.path.abspath(base_folder)
            sonal_path = os.path.abspath(os.path.join(base_path, rtr_path))
            if not _is_inside_folder(sonal_path, base_path):
                self.parent_textEdit.append(
                    _("Sonal path outside the corpus folder, skipped: ") + rtr_path)
                nb_skipped += 1
                continue
            if not os.path.isfile(sonal_path):
                self.parent_textEdit.append(
                    _("Sonal file not found, skipped: ") + rtr_path)
                nb_skipped += 1
                continue
            with open(sonal_path, 'r', encoding='utf-8-sig') as fh:
                sonal_html = fh.read()

            tab_loc = ent.get("tabLoc", []) or []
            tab_dat = ent.get("tabDat", []) or []
            notes = ent.get("notes", "") or ""
            fulltext, codings = self.parse_sonal_html(
                sonal_html, cid_by_code, tab_loc)

            fid, inserted = self.insert_source(
                cur_qc, name, fulltext, notes, owner, nowdate)
            if not inserted:
                continue
            nb_docs += 1
            self.app.conn.commit()

            # Import one file value per variable. Speaker variables only use
            # respondents, as interviewers are marked by a trailing question mark.
            interviewer_indexes, interviewee_indexes = _speaker_roles(tab_loc)
            if tab_loc and not interviewer_indexes:
                self.parent_textEdit.append(
                    _("No interviewer marked with a trailing '?' in: ") + name)
            values = self.attribute_values(
                tab_dat, attr_info_by_v, dic_label_by_vm,
                interviewee_indexes, tab_loc)
            for attr_name, value in values.items():
                cur_qc.execute(
                    "insert into attribute (name, value, id, owner, date, "
                    "attr_type) values (?,?,?,?,?,?)",
                    [attr_name, value, fid, owner, nowdate, "file"])
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

    def find_used_thematiques(self, tab_ent, base_folder):
        """ Return thematic CSS classes actually used in the transcriptions. """

        used = set()
        class_pattern = re.compile(r'class=["\']([^"\']*)["\']', re.IGNORECASE)
        base_path = os.path.abspath(base_folder)
        for ent in tab_ent:
            rtr_path = ent.get("rtrPath", "")
            sonal_path = os.path.abspath(os.path.join(base_path, rtr_path))
            if not rtr_path or not _is_inside_folder(sonal_path, base_path):
                continue
            if not os.path.isfile(sonal_path):
                continue
            with open(sonal_path, 'r', encoding='utf-8-sig') as fh:
                contenu = self._extract_contenu_text(fh.read())
            for match in class_pattern.finditer(contenu):
                used.update(cls for cls in match.group(1).split()
                            if cls.startswith("cat_"))
        return used

    def import_thematiques(self, cur_qc, tab_thm, owner, nowdate,
                           used_thematiques):
        """ Import Sonal thematiques as QualCoder codes and categories.

        Sonal thematiques form a tree through the ``rang`` indentation level
        (0 = top level). Parent thematiques become QualCoder categories. Their
        twin code is only created when the parent is directly used in text.
        Leaf codes remain available even when they have not been used yet.

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

        # Leaf codes are always imported.
        # A parent gets a twin code only when its CSS class occurs in a transcription.
        cid_by_code = {}
        default_color = "#DDE600"
        for thm in ordered_thm:
            code = thm.get("code", "")
            if not code:
                continue
            is_parent = code in has_children
            if is_parent and code not in used_thematiques:
                continue
            name = thm.get("nom", code)
            color = thm.get("couleur", "") or default_color
            if is_parent:
                catid = catid_by_code.get(code)
            else:
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
        """ Import global Sonal variable definitions as file attributes.

        Returns:
            attr_info_by_v : mapping of variable id -> name and scope
            dic_label_by_vm: mapping of (variable id, modality id) -> label
        """

        attr_info_by_v = {}
        for var in tab_var:
            v = _normalise_id(var.get("v"))
            lib = var.get("lib", "")
            if not v or not lib:
                continue
            try:
                cur_qc.execute(
                    "insert into attribute_type (name, valuetype, caseOrFile, memo, "
                    "owner, date) values (?,?,?,?,?,?)",
                    [lib, "character", "file", "", owner, nowdate])
            except sqlite3.IntegrityError:
                pass
            attr_info_by_v[v] = {
                "name": lib,
                "scope": str(var.get("champ", "gen") or "gen").lower(),
            }
        self.app.conn.commit()
        self.parent_textEdit.append(
            str(len(attr_info_by_v)) + _(" attribute types imported"))

        dic_label_by_vm = {}
        for entry in tab_dic:
            v = _normalise_id(entry.get("v"))
            m = _normalise_id(entry.get("m"))
            if v and m:
                dic_label_by_vm[(v, m)] = entry.get("lib", "") or ""
        return attr_info_by_v, dic_label_by_vm

    @staticmethod
    def attribute_values(tab_dat, attr_info_by_v, dic_label_by_vm,
                         interviewee_indexes, tab_loc):
        """ Build one file-level value for each variable in an interview. """

        rows_by_v = {}
        for dat in tab_dat or []:
            key = _normalise_id(dat.get("v"))
            if key in attr_info_by_v:
                rows_by_v.setdefault(key, []).append(dat)

        values = {}
        for v, info in attr_info_by_v.items():
            rows = rows_by_v.get(v, [])
            if info["scope"] == "gen":
                row = next(
                    (item for item in rows
                     if _normalise_id(item.get("l")).lower() == "all"),
                    None)
                values[info["name"]] = SonalImport.modality_label(
                    v, row, dic_label_by_vm)
                continue

            speaker_values = []
            for index in interviewee_indexes:
                row = next(
                    (item for item in rows
                     if _normalise_id(item.get("l")) == str(index)),
                    None)
                value = SonalImport.modality_label(v, row, dic_label_by_vm)
                if value:
                    name = _speaker_name(tab_loc[index])
                    speaker_values.append((name, value))
            distinct = {value for _, value in speaker_values}
            if len(speaker_values) <= 1 or len(distinct) == 1:
                values[info["name"]] = speaker_values[0][1] if speaker_values else ""
            else:
                values[info["name"]] = "; ".join(
                    f"{name}: {value}" for name, value in speaker_values)
        return values

    @staticmethod
    def modality_label(variable_id, row, dic_label_by_vm):
        """ Resolve a modality, keeping Sonal's zero modality empty. """

        if row is None:
            return ""
        modality = _normalise_id(row.get("m"))
        if modality in ("", "0"):
            return ""
        return dic_label_by_vm.get((variable_id, modality), str(row.get("m")))

    def insert_source(self, cur_qc, name, fulltext, notes, owner, nowdate):
        """ Insert a transcription as a QualCoder source, handling name clashes.

        Returns:
            (fid, inserted) where inserted is False if the source could not be
            created.
        """

        memo = notes or ""
        unique_name = name
        i = 1
        cur_qc.execute("select id from source where name=?", [unique_name])
        while cur_qc.fetchone() is not None:
            unique_name = f"{name}_{i}"
            i += 1
            cur_qc.execute("select id from source where name=?", [unique_name])

        # The name is known to be free. Any integrity error now represents a
        # real database problem and must not be retried forever.
        cur_qc.execute(
            "insert into source (name, fulltext, memo, owner, date, mediapath) "
            "values (?,?,?,?,?,?)",
            [unique_name, fulltext, memo, owner, nowdate, None])
        return cur_qc.lastrowid, True

    def parse_sonal_html(self, html_text, cid_by_code, tab_loc):
        """ Parse transcription text and codings from a ``.sonal`` document.

        Metadata and speaker names come from the corpus ``.crp``. The HTML is
        only used for the transcription structure and thematic CSS classes.
        """

        contenu = self._extract_contenu_text(html_text)
        parser = _SonalContentParser(cid_by_code, tab_loc)
        parser.feed(contenu)
        parser.close()
        fulltext = parser.fulltext
        codings = self._merge_codings(fulltext, parser.ranges_by_code)
        return fulltext, codings

    def _merge_codings(self, fulltext, ranges_by_code):
        """ Merge ranges, keeping whitespace only when it connects coded text. """

        codings = []
        for cid, ranges in ranges_by_code.items():
            ranges = sorted(
                (start, end) for start, end in ranges if end > start)
            merged = []
            component_end = None
            text_start = None
            text_end = None
            for start, end in ranges:
                if component_end is None or start > component_end:
                    if text_start is not None:
                        merged.append((text_start, text_end))
                    component_end = end
                    text_start = None
                    text_end = None
                else:
                    component_end = max(component_end, end)
                if fulltext[start:end].strip():
                    if text_start is None:
                        text_start = start
                    text_end = max(text_end or end, end)
            if text_start is not None:
                merged.append((text_start, text_end))
            for start, end in merged:
                codings.append((cid, fulltext[start:end], start, end))
        return codings

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

    The current Sonal structure is::

        <span class="lblseg ... ligloc" data-loc="1" ...>
            <span data-rk="1" ... class="cat_001">word</span>
            <span data-rk="2" ...>word2</span>
            ...
        </span>

    ``data-loc`` is an index into ``tabEnt[].tabLoc`` for the current interview
    in the ``.crp`` file. The ``ligloc`` class marks a segment where the speaker
    changes; it is normally carried by the outer ``lblseg`` span, rather than by
    a nested speaker span.

    Word spans carry codings through ``cat_XXX`` CSS classes. Anonymised word
    spans contribute their displayed text normally. Speaker prefixes are read
    from ``tabEnt[].tabLoc`` and inserted before text positions are recorded.
    """

    def __init__(self, cid_by_code, tab_loc):
        super().__init__(convert_charrefs=True)
        self.cid_by_code = cid_by_code
        self.tab_loc = tab_loc or []
        self.current_loc = None
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
        if is_lblseg:
            if self.fulltext_parts:
                self.fulltext_parts.append("\n")
                self._fulltext_len += 1
            raw_loc = ad.get("data-loc")
            loc = self.current_loc
            if raw_loc not in (None, ""):
                try:
                    loc = int(raw_loc)
                except (TypeError, ValueError):
                    pass
            if loc is None:
                loc = 0
            if loc != self.current_loc:
                if 0 <= loc < len(self.tab_loc) and self.tab_loc[loc]:
                    speaker = _speaker_name(self.tab_loc[loc])
                else:
                    speaker = f"Speaker {loc}"
                prefix = f"{speaker}: "
                self.fulltext_parts.append(prefix)
                self._fulltext_len += len(prefix)
                self.current_loc = loc
        is_word = ("data-rk" in ad) and not is_lblseg and ("ligloc" not in classes)
        # Speaker helper spans are not repeated because the prefix comes from .crp.
        produces_text = not is_lblseg and ("ligloc" not in classes)
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
        if (frame.get("ligloc") and self.fulltext_parts
                and not self.fulltext_parts[-1].endswith(("\n", " "))):
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
