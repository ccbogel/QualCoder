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

import datetime
import logging
from pathlib import Path
import rispy
from PyQt6 import QtWidgets

from .manage_references_import import ATTACHMENT_TAGS, existing_reference_signatures, \
    import_progress_dialog, reference_signature

logger = logging.getLogger(__name__)

country_names = [
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Antigua & Deps", "Argentina", "Armenia", "Australia",
    "Austria", "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh", "Barbados", "Belarus", "Belgium", "Belize", "Benin",
    "Bhutan", "Bolivia", "Bosnia Herzegovina", "Botswana", "Brazil", "Brunei", "Bulgaria", "Burkina", "Burundi",
    "Cambodia", "Cameroon", "Canada", "Cape Verde", "Central African Republic", "Chad", "Chile", "China", "Colombia",
    "Comoros","Congo", "Costa Rica", "Croatia", "Cuba", "Cyprus", "Czech Republic", "Denmark", "Djibouti", "Dominica",
    "Dominican Republic", "East Timor", "Ecuador", "Egypt", "El Salvador", "Equatorial Guinea", "Eritrea", "Estonia",
    "Ethiopia", "Fiji", "Finland", "France", "Gabon", "Gambia", "Georgia", "Germany", "Ghana", "Greece", "Grenada",
    "Guatemala", "Guinea", "Guinea-Bissau", "Guyana", "Haiti", "Honduras", "Hungary", "Iceland", "India", "Indonesia",
    "Iran", "Iraq", "Ireland", "Israel", "Italy", "Ivory Coast", "Jamaica", "Japan", "Jordan", "Kazakhstan", "Kenya",
    "Kiribati", "North Korea", "South Korea", "Kosovo", "Kuwait", "Kyrgyzstan", "Laos", "Latvia", "Lebanon", "Lesotho",
    "Liberia", "Libya", "Liechtenstein", "Lithuania", "Luxembourg", "Macedonia", "Madagascar", "Malawi", "Malaysia",
    "Maldives", "Mali", "Malta", "Marshall Islands", "Mauritania", "Mauritius", "Mexico", "Micronesia", "Moldova",
    "Monaco", "Mongolia", "Montenegro", "Morocco", "Mozambique", "Myanmar", "Namibia", "Nauru", "Nepal",
    "Netherlands", "New Zealand", "Nicaragua", "Niger", "Nigeria", "Norway", "Oman", "Pakistan", "Palau", "Panama",
    "Papua New Guinea", "Paraguay", "Peru", "Philippines", "Poland", "Portugal", "Qatar", "Romania",
    "Russian Federation", "Rwanda", "St Kitts & Nevis", "St Lucia", "Saint Vincent & the Grenadines",
    "Samoa", "San Marino", "Sao Tome & Principe", "Saudi Arabia", "Senegal", "Serbia", "Seychelles", "Sierra Leone",
    "Singapore", "Slovakia", "Slovenia", "Solomon Islands", "Somalia", "South Africa", "South Sudan", "Spain",
    "Sri Lanka", "Sudan", "Suriname", "Swaziland", "Sweden", "Switzerland", "Syria", "Taiwan", "Tajikistan",
    "Tanzania", "Thailand", "Togo", "Tonga", "Trinidad & Tobago", "Tunisia", "Turkey", "Turkmenistan", "Tuvalu",
    "Uganda", "Ukraine", "United Arab Emirates", "United Kingdom", "United States", "Uruguay", "Uzbekistan",
    "Vanuatu", "Vatican City", "Venezuela", "Vietnam", "Yemen", "Zambia", "Zimbabwe"]


class Ris:
    """ Load ris list of dictionaries.
        Format RIS to Vancouver or APA for display.
        References in RIS can be poorly created often due to how the researcher created them. """

    app = None
    refs = []

    def __init__(self, app):
        self.app = app

    def get_references(self, selected_ris:int|None=None):
        """ As list of dictionaries with risid and summary.
        Args:
            selected_ris: Integer risid
        """

        self.refs = []
        cur = self.app.conn.cursor()
        if not selected_ris:
            cur.execute("select distinct risid from ris order by risid")
        else:
            cur.execute("select distinct risid from ris where risid=?", [selected_ris])
        ris_ids_res = cur.fetchall()
        if not ris_ids_res:  # May be empty if selected_ris is incorrect or no references present
            return
        for ris_id in ris_ids_res:
            ref = {'risid': ris_id[0]}
            details = str(ris_id[0]) + " "
            cur.execute("select tag, longtag, value from ris where risid=?", [ris_id[0]])
            ris_result = cur.fetchall()
            jnl_or_secondary_title = ""
            for tpl in ris_result:
                ref[tpl[0]] = tpl[2]
                ref[tpl[1]] = tpl[2]
                details += f"{tpl[0]} - {tpl[1]} - {tpl[2]}\n"
                if tpl[0] == 'JO':
                    jnl_or_secondary_title = tpl[2]
                if jnl_or_secondary_title == "" and tpl[0] == 'JF':
                    jnl_or_secondary_title = tpl[2]
                if jnl_or_secondary_title == "" and tpl[0] == 'T2':
                    jnl_or_secondary_title = tpl[2]
            ref['details'] = details
            ref['journal_or_secondary'] = jnl_or_secondary_title
            # This is use in Manage files display
            ref['journal_vol_issue'] = jnl_or_secondary_title + " "
            # Volume and issue
            volume = None
            issue = None
            ref['volume'] = ""
            ref['issue'] = ""
            for tpl in ris_result:
                if 'VL' in tpl:
                    volume = tpl[2]
                    ref['volume'] = tpl[2]
                if volume is None and 'VO' in tpl:
                    volume = tpl[2]
                    ref['volume'] = tpl[2]
                if 'IS' in tpl:
                    issue = tpl[2]
                    ref['issue'] = tpl[2]
            if volume and issue:
                ref['journal_vol_issue'] += f"{volume} ({issue})"
            # Without these defaults, a reference lacking title or type broke get_data, tooltips
            # and the manager's sorts (KeyError on ref['TI'] / ref['TY']).
            if 'TI' not in ref:
                ref['TI'] = ""
            if 'TY' not in ref:
                ref['TY'] = ""
            if 'PY' not in ref:
                ref['PY'] = ""
            if 'authors' not in ref:
                ref['authors'] = ""
            if 'keywords' not in ref:
                ref['keywords'] = ""
            ref['vancouver'], ref['apa'] = self.format_vancouver_and_apa(ref)
            self.refs.append(ref)

    def format_vancouver_and_apa(self, ref:dict[str,str]):
        """ Format items in list for display as Vancouver style and APA style.
            Vancouver:
            Title.  authors (or editor)
            journal name, year, date, volume, issue, pages
            publisher (and place) issn, url
            APA:
            authors (year). title, journal volume issue (page numbers) URL
        Args:
            ref : Dictionary
         """

        title = ""
        authors = ""
        published_year = ""
        periodical_name = ""
        volume = None
        issue = None
        editor = None
        edition = None
        pages = None
        end_page = None
        publisher = None
        issn = None
        url = None
        doi = None

        # Get the first title based on this order
        for tag in ("TI", "T1", "ST", "TT"):
            try:
                title = f"{ref[tag]}.\n"
                break
            except KeyError:
                pass
        # Authors
        for tag in ("AU", "A1", "A2", "A3", "A4"):
            try:
                authors += " " + ref[tag]
            except KeyError:
                pass
        if authors != "":
            authors = authors[1:] + "\n"
        # Editor
        if 'ED' in ref:
            editor = f"Editor: {ref['ED']} \n"
        # Publication year
        if 'PY' in ref:
            published_year = ref['PY']
        if published_year == "" and 'Y1' in ref:
            published_year = ref['Y1']
        # Publisher
        if 'PB' in ref:
            publisher = ref['PB']
            if 'PP' in ref:
                publisher += f" {ref['PP']}"
        # ISSN
        if 'SN' in ref:
            issn = f"ISSN: {ref['SN']}"
        # Journal name, T2 tag is often used for this
        for tag in ("JO", "JF", "T2", "JA", "J1", "J2"):
            try:
                if periodical_name == "":
                    periodical_name = f"{ref[tag]} "
                    continue
            except KeyError:
                pass
        # Edition
        if 'ET' in ref:
            edition = ref['ET']
        # Volume and issue
        if 'VL' in ref:
            volume = f" Vol.{ref['VL']}"
        if volume is None and 'VO' in ref:
            volume = " Vol." + ref['VO']
        if 'IS' in ref:
            issue = ref['IS']
        volume_and_or_issue = ""
        if volume and issue:
            volume_and_or_issue = volume + f"({issue}) "
        if volume is None and issue:
            volume_and_or_issue += " " + issue + " "
        if volume_and_or_issue == "" and edition:
            volume_and_or_issue = "Edn. " + edition
        # Pages
        if 'SP' in ref:
            pages = ref['SP']
        if 'EP' in ref:
            end_page = ref['EP']
        if pages and end_page is not None:
            pages += "-" + end_page
        if pages:
            pages = " pp." + pages
            pages = pages.strip()
        # URL
        if 'UR' in ref:
            url = ref['UR']
            if 'Y2' in ref:
                url += f" Accessed: {ref['Y2']}"
        if 'DO' in ref:
            doi = f"doi: {ref['DO']}"

        # Wrap up Vancouver style reference
        vancouver = title + authors
        if editor:
            vancouver += editor
        # Periodicals
        vancouver += periodical_name + published_year + " " + volume_and_or_issue
        if pages:
            vancouver += pages
        vancouver += "\n"
        # Other published
        if publisher:
            vancouver += publisher + " "
        # Extra information
        if issn:
            vancouver += issn + "\n"
        # Links
        if url:
            vancouver += url + "\n"
        if doi:
            vancouver += doi
        # Clean up
        vancouver = vancouver.replace("  ", " ")
        vancouver = vancouver.strip()

        # Wrap up APA style, American Psychological Association reference style v 7
        # authors(year).title, journal volume issue(page numbers) URL
        apa = authors.replace(";", ",")
        if editor:
            apa += editor
        apa += " "
        if published_year != "":
            apa += f"({published_year}). "
        if title != "":
            apa += f"{self.apa_title(title)}"
        if periodical_name != "":
            apa += f"{periodical_name}, "
        if volume_and_or_issue != "":
            apa += f"{volume_and_or_issue}. "
        if pages:
            apa += f"({pages})"
        if url is not None:
            apa += f" {url}"
        if doi is not None:
            apa += f" {doi}"
        # Clean up
        apa = apa.replace(" ,", ",")
        apa = apa.replace(" .", ".")
        apa = apa.replace("  ", " ")
        apa = apa.strip()
        return vancouver, apa

    def apa_title(self, title:str) -> str:
        """ APA 7 Sentence case. And after . : -
         Keep names Titled - not easy to do, but have added country names. """

        if title == "":
            return ""
        text_list = title.split()
        # Ignore the first word, should be sentence case already.
        for i in range(1, len(text_list)):
            # Keep uppercase acronyms as is, and keep Sentence case after . : -
            if len(text_list[i]) > 1 and text_list[i].isupper():
                continue
            if text_list[i - 1][-1] in ('.', ':', '-'):
                text_list[i] = text_list[i].capitalize()
                continue
            text_list[i] = text_list[i].lower()
        apa_title = " ".join(text_list)
        # Find and capitalise country names
        for country_name in country_names:
            if country_name.lower() in apa_title:
                apa_title = apa_title.replace(country_name.lower(), country_name)
        return apa_title


class RisImport:
    """ Import an RIS format bibliography and store in database.
    References in RIS can be poorly created often due to how the researcher created them.
    Also, get PubMed Nbib file and convert to RIS to import.

    Create these variables for the sources
    Ref_Type (Type of Reference) – character variable
    Ref_Author (authors list) – character
    Ref_Title – character
    Ref_Year (of publication) – numeric
    Ref_journal
    """

    def __init__(self, app, parent_text_edit, refs_dialog=None):
        """ Args:
            refs_dialog: DialogReferenceManager, used for the preview dialog, duplicate detection
                and attachment import. Without it, everything is imported without asking.
        """

        self.app = app
        self.parent_text_edit = parent_text_edit
        self.refs_dialog = refs_dialog
        self.imported_filepath = ""
        response = QtWidgets.QFileDialog.getOpenFileNames(None, _('Select RIS or NBIB references file'),
                                                          self.app.settings['directory'],
                                                          "(*.ris *.RIS *.nbib *.txt)")  # native OS dialog
        imports = response[0]
        if imports:
            file_path = imports[0]
            self.imported_filepath = file_path  # Original path.
            if file_path.endswith(".nbib"):
                file_path = self.nbib_to_ris(file_path)
            self.create_file_attributes()
            self.create_file_placeholder_attributes()
            self.import_ris_file(file_path)

    def _emit_project_table_changes(self, tables):
        """Notify other open dialogs about changed project tables."""

        if getattr(self.app, "project_events", None) is not None:
            self.app.project_events.emit_table_changes(tables, source=self)

    def create_file_attributes(self):
        """ Creates the attributes for Ref_Authors, Ref_Title, Ref_Type, Ref_Year, Ref_Journal """

        now_date = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        cur = self.app.conn.cursor()
        ref_vars = {'Ref_Authors': 'character', 'Ref_Title': 'character', 'Ref_Type': 'character',
                    'Ref_Year': 'numeric', 'Ref_Journal': 'character'}
        created = False
        for key in ref_vars:
            cur.execute("select name from attribute_type where name=?", [key])
            res = cur.fetchone()
            if not res:
                cur.execute("insert into attribute_type (name,date,owner,memo,caseOrFile, valuetype) values(?,?,?,?,?,?)",
                        (key, now_date, self.app.settings['codername'], "", 'file', ref_vars[key]))
                self.app.conn.commit()
                created = True
        self.app.delete_backup = False
        if created:
            self._emit_project_table_changes(['attribute_type'])

    def create_file_placeholder_attributes(self):
        """ Creates empty placeholder attributes for each file.
         Duplicated the methods manage_files.check_attribute_placeholders """

        cur = self.app.conn.cursor()
        sql = "select id from source "
        cur.execute(sql)
        sources = cur.fetchall()
        sql = 'select name from attribute_type where caseOrFile ="file"'
        cur.execute(sql)
        attr_types = cur.fetchall()
        attr_types = ["Ref_Authors", "Ref_Title", "Ref_Type", "Ref_Year", "Ref_Journal"]
        insert_sql = "insert into attribute (name, attr_type, value, id, date, owner) values(?,'file','',?,?,?)"
        created = False
        for source in sources:
            for att in attr_types:
                sql = "select value from attribute where id=? and name=?"
                cur.execute(sql, [source[0], att])
                res = cur.fetchone()
                if res is None:
                    placeholders = [att, source[0], datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    self.app.settings['codername']]
                    cur.execute(insert_sql, placeholders)
                    self.app.conn.commit()
                    created = True
        if created:
            self._emit_project_table_changes(['attribute'])

    def import_ris_file(self, filepath):
        """
        Reads the .ris/.nbib file, builds the candidate reference list
        (with reference and attachment duplicate status) and opens the preview dialog to choose
        which to import. Inserts only the chosen ones and links all their PDF/EPUB attachments
        (if requested). A reference may have several attachments (e.g. PDF and EPUB, or two L1
        lines); all of them are imported. List tags: 'A1', 'A2', 'A3', 'A4', 'AU', 'KW', 'N1' #
        authors, KW keywords, N1 Notes longtag is the extended wording of a tag tag_keys is the
        dictionary of 2 char short tag keys (e.g. AU) and the longtag wording
        """

        # List tags: rispy defaults plus the link tags (attachments), so multiple
        # attachments per reference are captured as a list instead of rispy keeping only the first
        # one.
        default_list_tags = getattr(rispy.RisParser, "DEFAULT_LIST_TAGS",
                                    ['A1', 'A2', 'A3', 'A4', 'AU', 'KW', 'N1', 'UR'])
        list_tags = list(default_list_tags) + list(ATTACHMENT_TAGS)
        tag_keys = rispy.TAG_KEY_MAPPING
        longtag_to_tag = dict((v, k) for k, v in tag_keys.items())
        cur = self.app.conn.cursor()
        cur.execute("select max(risid) from ris")
        res = cur.fetchone()
        max_risid = 0
        if res is not None and res[0] is not None:
            max_risid = res[0]
        with open(filepath, 'r', encoding="utf-8", errors="surrogateescape") as ris_file:
            entries = rispy.load(ris_file, list_tags=list_tags)

        # .ris folder, to resolve relative attachment paths.
        ris_dir = str(Path(self.imported_filepath).parent) if self.imported_filepath \
            else str(Path(filepath).parent)
        existing_sigs = self.project_signatures()
        cur.execute("select lower(name) from source")
        existing_names = set(r[0] for r in cur.fetchall() if r[0] is not None)
        seen_sigs = set()
        seen_attach = set()
        rows = []
        candidates = []  # paralelo a rows: Parallel: (triples, [paths]).
        any_attachment = False
        unresolved = 0  # Cited but missing.

        for entry in entries:
            try:
                del entry['id']
            except KeyError:
                pass
            triples = []  # For the ris table.
            attach_values = []  # Individual attachment values.
            for longtag in entry:
                raw = entry[longtag]
                tag = longtag_to_tag.get(longtag)
                if not tag:
                    continue  # Unknown tag: skip the field.
                # Collect each attachment separately (do not join). Detection is by link TAG, not
                # by long name: Zotero writes PDFs in L1 and EPUBs in L4, whose long name is
                # 'figure'. No extension filter here either: the raw value may carry spaces,
                # description suffixes or URL escapes.
                if tag in ATTACHMENT_TAGS:
                    for v in (raw if isinstance(raw, list) else [raw]):
                        if isinstance(v, str) and v.strip():
                            attach_values.append(v)
                # Join lists for the ris table.
                value = "; ".join(str(x) for x in raw) if isinstance(raw, list) else raw
                if not isinstance(value, str):
                    continue
                triples.append((tag, longtag, value))
            if not triples:
                continue
            sig = reference_signature([(t, v) for t, _lt, v in triples])
            ref_dup = bool(sig) and (sig in existing_sigs or sig in seen_sigs)
            if sig:
                seen_sigs.add(sig)
            if not self.refs_dialog and ref_dup:
                continue  # No dialog: skip.
            # Resolve all attachments of the reference (PDF and EPUB), without repeating paths.
            attach_paths = []
            if self.refs_dialog:
                for v in attach_values:
                    p = self.refs_dialog._resolve_attachment_path(v, ris_dir)
                    if p and p not in attach_paths:
                        attach_paths.append(p)
                    elif p is None:
                        unresolved += 1
            attach_label = ""
            attach_dup = False
            if attach_paths:
                any_attachment = True
                names = [Path(p.replace("\\", "/")).name for p in attach_paths]
                # Label: first name, plus "(+N)" if more
                attach_label = names[0] if len(names) == 1 else f"{names[0]} (+{len(names) - 1})"
                for nm in names:
                    low = nm.lower()
                    if low in existing_names or low in seen_attach:
                        attach_dup = True
                    else:
                        seen_attach.add(low)
            rows.append({"label": self._entry_label(triples), "ref_duplicate": ref_dup,
                         "attachment": attach_label, "attachment_duplicate": attach_dup})
            candidates.append((triples, attach_paths))

        if not rows:
            self.parent_text_edit.append(_("No references found in: ") + filepath + "\n========")
            return

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
            return
        chosen = [candidates[i] for i in selected]

        # Insert the chosen references, one commit.
        new_entries = 0
        pairs = []  # (risid, [attachment paths]).
        for triples, attach_paths in chosen:
            max_risid += 1
            for tag, longtag, value in triples:
                cur.execute("insert into ris (risid,tag,longtag,value) values (?,?,?,?)",
                            [max_risid, tag, longtag, value])
            pairs.append((max_risid, attach_paths))
            new_entries += 1
        self.app.conn.commit()
        if new_entries > 0:
            self._emit_project_table_changes(['ris'])
        if self.refs_dialog:
            self.refs_dialog.get_data()

        # Link all attachments of each chosen reference if requested; repeated names become
        # numbered copies.
        linked = 0
        failed = 0  # Attachments that could not be read.
        if want_attachments and self.refs_dialog:
            to_link = [(risid, paths) for risid, paths in pairs if paths]
            total = sum(len(paths) for _risid, paths in to_link)
            if total:
                first_name = Path(to_link[0][1][0].replace("\\", "/")).name
                progress = import_progress_dialog(self.refs_dialog, total, first_name)
                done = 0
                try:
                    for risid, paths in to_link:
                        for path_ in paths:
                            QtWidgets.QApplication.processEvents()
                            done += 1
                            progress.setValue(done)
                            progress.setLabelText(Path(path_.replace("\\", "/")).name)
                            fid = self.refs_dialog._import_attachment_file(path_, progress,
                                                                           notify=False)
                            if fid is None:
                                failed += 1
                                continue
                            # Silenced per attachment: one event after the batch
                            self.refs_dialog.link_reference_to_files(risid, fid, notify=False)
                            linked += 1
                finally:
                    # No autoClose: close it, in a finally so a failure midway does not leave the
                    # bar stuck on screen.
                    progress.close()
                    progress.deleteLater()
            if linked > 0 and getattr(self.app, "project_events", None) is not None:
                # One event for the whole attachment batch, not one per file
                self.app.project_events.emit_table_changes(['source', 'attribute'], source=None)
            self.refs_dialog.get_data()

        msg = _("Bibliography loaded from: ") + filepath + "\n"
        msg += _("References imported: ") + str(new_entries)
        if want_attachments:
            msg += "\n" + _("Attachments linked: ") + str(linked)
            # What did not make it is reported, instead of vanishing without a trace.
            if failed:
                msg += "\n" + _("Attachments not imported: ") + str(failed)
        if unresolved:
            msg += "\n" + _("Attachment files not found: ") + str(unresolved)
        self.parent_text_edit.append(msg + "\n========")

    def project_signatures(self):
        """
        Signatures already in the project.
        """

        if self.refs_dialog:
            return self.refs_dialog._existing_reference_signatures()
        return existing_reference_signatures(self.app.conn)

    def entry_exists(self, entry):
        """
        Check if this entry already exists in the project. Signature based detection
        (title|year|authors), tolerant to accents, punctuation, case, and to the imported
        reference carrying more or fewer fields than the stored one. The previous version
        required ALL fields to match and ran one query per field, so a single differing datum
        (or an added DOI) made it look new. A reference without a title has no signature and
        counts as new.
        Args:
            entry: dictionary of longtag and value, as returned by rispy
        Returns:
            Boolean
        """

        longtag_to_tag = dict((v, k) for k, v in rispy.TAG_KEY_MAPPING.items())
        pairs = []
        for longtag, raw in entry.items():
            tag = longtag_to_tag.get(longtag)
            if not tag:
                continue
            value = "; ".join(str(x) for x in raw) if isinstance(raw, list) else raw
            if isinstance(value, str):
                pairs.append((tag, value))
        sig = reference_signature(pairs)
        if not sig:
            return False
        return sig in self.project_signatures()

    def _entry_label(self, triples):
        """
        Readable label of a reference (author - title (year)) for the selection dialog.
        """

        tagvals = {}
        for tag, _longtag, value in triples:
            tagvals.setdefault(tag, value)
        title = tagvals.get('TI') or tagvals.get('T1') or _("(untitled)")
        authors = tagvals.get('AU') or tagvals.get('A1') or ""
        year = tagvals.get('PY') or tagvals.get('Y1') or ""
        label = title
        if authors:
            label = authors.split(';')[0].strip() + " - " + label
        if year:
            label += f" ({year})"
        return label

    def nbib_to_ris(self, nbib_filepath):
        """ Create a temporary ris file from the PubMed nbib file.
         Stored in .qualcoder """

        # To find abstract and add the subsequent lines, without adding unknown lines to another tag
        abstract_tag = False

        ris_data = ""
        with open(nbib_filepath, "r", encoding="utf-8", errors="backslashreplace") as nbib_file:
            for line in nbib_file:
                line = line.rstrip()
                # print(line)
                if line.startswith("PMID"):  # new record
                    ris_data += "TY  - JOUR"
                if line == "":  # End of nbib record
                    abstract_tag = False
                    ris_data += "\nER  -\n\n"
                else:
                    tag = nbib_tags.get(line[:6])
                    data = line[6:]
                    if line.startswith("AB  - "):
                        abstract_tag = True
                    elif abstract_tag and tag not in (None, ""):
                        abstract_tag = False
                    if tag is not None and tag != "":
                        ris_data += "\n" + tag + data
                    elif tag is not None and abstract_tag and tag == "":  # Continued line for abstract
                        ris_data += " " + data
        # Add final record tag
        ris_data += "\nER  -\n\n"

        ris_file_path = Path(self.app.confighome) / "temp_nbib_to_ris.ris"
        with open(ris_file_path, "w", encoding="utf-8") as ris_data_file:
            ris_data_file.write(ris_data)
        return ris_file_path


# PubMed nbib to ris reference tags
nbib_tags = {
            "PMID- ": "ID  - ",  # PubMed ID
            "TI  - ": "TI  - ",  # Title
            "JT  - ": "T2  - ",  # Journal Title
            "TA  - ": "JO  - ",  # Journal Abbreviation
            "AU  - ": "AU  - ",  # Author
            "DP  - ": "PY  - ",  # Publication Year
            "VI  - ": "VL  - ",  # Volume
            "IP  - ": "IS  - ",  # Issue
            "PG  - ": "SP  - ",  # Start Page
            "LID - ": "DO  - ",  # DOI
            "AB  - ": "AB  - ",  # Abstract
            "PL  - ": "CY  - ",  # Place of Publication
            "PB  - ": "PB  - ",  # Publisher
            "ED  - ": "ED  - ",  # Editor
            "MH  - ": "KW  - ",  # Keywords
            "      ": ""    # line continuation, e.g. abstract
        }
# "FAU - ": "AU  - ",  # Full Author Name - seems superfluous, but might have to review this


# ris reference tags
ref_types = {
'ABST': 'Abstract',
'ADVS': 'Audiovisual material',
'AGGR': 'Aggregated Database',
'ANCIENT': 'Ancient Text',
'ART': 'Art Work',
'BILL': 'Bill',
'BLOG': 'Blog',
'BOOK': 'Whole book',
'CASE': 'Case',
'CHAP': 'Book chapter',
'CHART': 'Chart',
'CLSWK': 'Classical Work',
'COMP': 'Computer program',
'CONF': 'Conference proceeding',
'CPAPER': 'Conference paper',
'CTLG': 'Catalog',
'DATA': 'Data file',
'DBASE': 'Online Database',
'DICT': 'Dictionary',
'EBOOK': 'Electronic Book',
'ECHAP': 'Electronic Book Section',
'EDBOOK': 'Edited Book',
'EJOUR': 'Electronic Article',
'WEB': 'Web Page',
'ENCYC': 'Encyclopedia',
'EQUA': 'Equation',
'FIGURE': 'Figure',
'GEN': 'Generic',
'GOVDOC': 'Government Document',
'GRANT': 'Grant',
'HEAR': 'Hearing',
'ICOMM': 'Internet Communication',
'INPR': 'In Press',
'JFULL': 'Journal (full)',
'JOUR': 'Journal',
'LEGAL': 'Legal Rule or Regulation',
'MANSCPT': 'Manuscript',
'MAP': 'Map',
'MGZN': 'Magazine article',
'MPCT': 'Motion picture',
'MULTI': 'Online Multimedia',
'MUSIC': 'Music score',
'NEWS': 'Newspaper',
'PAMP': 'Pamphlet',
'PAT': 'Patent',
'PCOMM': 'Personal communication',
'RPRT': 'Report',
'SER': 'Serial publication',
'SLIDE': 'Slide',
'SOUND': 'Sound recording',
'STAND': 'Standard',
'STAT': 'Statute',
'THES': 'Thesis/Dissertation',
'UNBILL': 'Unenacted Bill',
'UNPB': 'Unpublished work',
'VIDEO': 'Video recording'
}


