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
import re
import shutil
import sqlite3

from PyQt6 import QtCore, QtWidgets

from .helpers import Message

logger = logging.getLogger(__name__)

# Max item names listed per preview section. Counts are always complete
MAX_LISTED_ITEMS = 200


class MergeCancelled(Exception):
    """ Raised when the user cancels from the progress dialog. """


class MergeProgress:
    """ Progress dialog for the merge phases. Keeps the interface responsive and
    raises MergeCancelled when the user cancels. No-op without a running application.
    """

    def __init__(self, app, parent=None):

        self.dialog = None
        if QtWidgets.QApplication.instance() is None:
            return
        self.dialog = QtWidgets.QProgressDialog("", _("Cancel"), 0, 100, parent)
        self.dialog.setWindowTitle(_("Merge projects"))
        self.dialog.setWindowModality(QtCore.Qt.WindowModality.ApplicationModal)
        self.dialog.setMinimumDuration(400)  # Do not flash on a small project
        self.dialog.setAutoClose(False)
        self.dialog.setAutoReset(False)
        self.dialog.setStyleSheet(f'font: {app.settings["fontsize"]}pt "{app.settings["font"]}";')
        self.dialog.setValue(0)

    def phase(self, label, value, repaint=True):
        """ Move to the next phase. repaint=False skips event processing, which is required
        while the merge transaction is open: repainting lets timers in other dialogs run,
        and they write to the shared connection.
        """

        if self.dialog is None:
            return
        self.dialog.setLabelText(label)
        self.dialog.setValue(value)
        if repaint:
            self.check()

    def tick(self, index, total, base, span, every=100):
        """ Update from inside a long loop, at intervals. """

        if self.dialog is None or index % every or not total:
            return
        self.dialog.setValue(base + int(span * index / total))
        self.check()

    def check(self):
        """ Repaint and raise if the user pressed Cancel. """

        if self.dialog is None:
            return
        QtWidgets.QApplication.processEvents()
        if self.dialog.wasCanceled():
            raise MergeCancelled()

    def hide(self):
        if self.dialog is not None:
            self.dialog.hide()

    def restart(self):
        """ Re-arm after hide(), which otherwise stops the dialog re-appearing. """

        if self.dialog is None:
            return
        self.dialog.reset()  # Also clears the cancel flag
        self.dialog.setValue(0)

    def close(self):
        if self.dialog is not None:
            self.dialog.close()
            self.dialog = None


class DialogMergePreview(QtWidgets.QDialog):
    """ Read only preview of what a merge would add, by section with counts and names.
    Nothing is written yet, so Cancel leaves the project untouched.
    """

    def __init__(self, app, sections, path_s, parent=None):

        super(DialogMergePreview, self).__init__(parent)
        self.app = app
        self.sections = sections
        self.setWindowTitle(_("Merge preview"))
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.resize(760, 580)
        self.setStyleSheet(f'font: {app.settings["fontsize"]}pt "{app.settings["font"]}";')
        layout = QtWidgets.QVBoxLayout(self)
        header = QtWidgets.QLabel(_("Merging: ") + f"{path_s}\n" + _("Into: ") + f"{app.project_path}")
        header.setWordWrap(True)
        layout.addWidget(header)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels([_("Item"), _("Count")])
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.NoSelection)
        layout.addWidget(self.tree)
        self.fill_tree()
        note = QtWidgets.QLabel(
            _("Existing values in the destination project are not over-written, apart from blank attribute values."))
        note.setWordWrap(True)
        layout.addWidget(note)
        self.checkbox_journal = QtWidgets.QCheckBox(_("Save this report to a journal"))
        self.checkbox_journal.setToolTip(_("The report is stored as a journal entry, merged or cancelled"))
        layout.addWidget(self.checkbox_journal)
        button_box = QtWidgets.QDialogButtonBox()
        merge_button = button_box.addButton(_("Merge"), QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole)
        merge_button.setDefault(True)
        button_box.addButton(_("Cancel"), QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def fill_tree(self):
        """ One top level row per section, item names as children. """

        # Expand a short report, otherwise open the warnings only
        total_items = sum(len(s['items']) for s in self.sections)
        expand_all = total_items <= 40
        for section in self.sections:
            top = QtWidgets.QTreeWidgetItem([section['title'], section['detail']])
            if section['warning']:
                for column in (0, 1):
                    top.setForeground(column, QtCore.Qt.GlobalColor.red)
            for item in section['items']:
                top.addChild(QtWidgets.QTreeWidgetItem([item, ""]))
            self.tree.addTopLevelItem(top)
            if section['warning'] or (expand_all and section['items']):
                top.setExpanded(True)
        self.tree.resizeColumnToContents(0)

    def save_to_journal(self):
        """ True if the report should be stored as a journal entry. """

        return self.checkbox_journal.isChecked()


class MergeProjects:
    """ Merge one external Qualcoder project (source) database into existing project (destination).
    Copies unmatched files from source project folders to destination project folders.
    Adds new (unmatched) source categories to destination database.
    Adds new (unmatched) source code names to destination database.
    Adds journals and stored_sql to destination database, only if they have unique names,
    Adds text codings, text annotations, image codings, av codings to destination database.
    Adds cases and case_text (links to text file segments and images and A/V)
    Add attributes for files and cases.
    Existing attribute values in destination are not over-written, unless already blank
     """

    def __init__(self, app, path_s, show_preview=True):
        self.app = app
        self.path_s = path_s  # Path to source project folder
        self.conn_s = None  # Source project that is to be merged from
        # The merge runs in one transaction. Other open dialogs have timers that write and commit
        # on app.conn, and progress repaints let them run, so use a connection of our own
        self.conn_d = None  # Destination project - the currently opened project
        self.path_d = self.app.project_path  # Path to destination project folder
        self.summary_msg = _("Merging: ") + self.path_s + "\n" + _("Into: ") + self.app.project_path + "\n"
        self.projects_merged = False
        self.source_s = []  # source text from Source project
        self.code_text_s = []  # coded text segments from Source project
        self.annotations_s = []  # annotations from Source project
        self.journals_s = []
        self.stored_sql_s = []
        self.code_image_s = []  # coded image areas from Source project
        self.code_av_s = []  # coded A/V segments from Source project
        self.codes_s = []  # codes from Source project
        self.categories_s = []  # code cats from Source project
        self.attribute_types_s = []  # For new attributes that are not existing in the destination database
        self.attributes_s = []  # values for Case and File attributes
        self.cases_s = []
        self.case_text_s = []  # case text and links to non-text files
        self.preview_sections = []  # Read only summary of what would be added
        self.merge_cancelled = False
        self.copied_files = []  # Removed again if the merge is cancelled
        self.progress = MergeProgress(self.app)
        # Connecting to a missing file would create an empty database in the user folder
        db_path_s = Path(self.path_s) / 'data.qda'
        if not db_path_s.is_file():
            self.summary_msg += _("No data.qda database found in the selected folder.") + "\n"
            self.progress.close()
            Message(self.app, _('Project not merged'), _("Not a QualCoder project")).exec()
            return
        self.conn_s = sqlite3.connect(db_path_s)
        # timeout lets a write by another dialog finish rather than fail outright
        self.conn_d = sqlite3.connect(Path(self.path_d) / 'data.qda', timeout=30)
        save_journal = False
        try:
            self.progress.phase(_("Reading the project to merge"), 2)
            loaded = self.get_source_data()
            if loaded:
                self.progress.phase(_("Preparing the preview"), 10)
                self.preview_sections = self.build_preview()
        except MergeCancelled:
            self.cancel_merge(save_journal=False)
            return
        if not loaded:
            self.close_connections()
            Message(self.app, _('Project not merged'), _("Project not merged")).exec()
            return
        self.progress.hide()
        if show_preview:
            preview_dialog = DialogMergePreview(self.app, self.preview_sections, self.path_s)
            proceed = preview_dialog.exec()
            save_journal = preview_dialog.save_to_journal()
            if not proceed:
                self.cancel_merge(save_journal)
                return
        # Everything below is one transaction, so a cancel or an error rolls the project back
        try:
            self.progress.restart()
            self.progress.phase(_("Copying files"), 15)
            self.copy_source_files_into_destination()
            msg, backup_name = self.app.save_backup("_Pre-merge")
            self.summary_msg += f"\n{msg}"
            # From here the transaction is open, so no more event processing and no cancel.
            # The database phase runs well under a second even on a very large project
            self.progress.phase(_("Merging"), 40, repaint=False)
            self.insert_sources_get_new_file_ids()
            self.update_coding_file_ids()
            self.insert_categories()
            self.update_code_cid_and_insert_code()
            self.insert_coding_and_journal_data()
            self.insert_cases()
            self.insert_new_attribute_types()
            self.insert_attributes()
            self.conn_d.commit()  # One transaction for the whole merge
        except MergeCancelled:
            self.conn_d.rollback()
            self.cancel_merge(save_journal)
            return
        except Exception as err:
            # Broad on purpose: an escaping error would leave an open transaction and a modal
            # progress dialog on screen
            self.conn_d.rollback()
            self.remove_copied_files()
            logger.exception("Merge projects failed")
            self.summary_msg += "\n" + _("Merge failed, no changes were made. ") + f"{err}\n"
            self.close_connections()
            Message(self.app, _('Project not merged'), _("Merge failed") + f"\n{err}").exec()
            return
        try:
            self.progress.phase(_("Finishing"), 95, repaint=False)
            # Update vectorstore
            if self.app.settings['ai_enable'] == 'True':
                self.app.ai.sources_vectorstore.update_vectorstore()
        except Exception as err:
            # The merge itself is committed, so report and carry on
            logger.exception("Vectorstore update after merge failed")
            self.summary_msg += _("Could not update the AI vectorstore: ") + f"{err}\n"
        self.summary_msg += "\n" + _("Finished merging ") + f"{self.path_s}  --> {self.path_d}\n"
        self.summary_msg += _(
            "Existing values in destination project are not over-written, apart from blank attribute values.") + "\n"
        # One event for the whole merge, not one per inserted row
        self._emit_project_table_changes(
            ['source', 'code_name', 'code_cat', 'code_text', 'code_image', 'code_av',
             'cases', 'case_text', 'attribute', 'attribute_type', 'journal', 'annotation'])
        self.projects_merged = True
        self.app.delete_backup = False
        if save_journal:
            self.save_report_to_journal(merged=True)
        self.close_connections()
        Message(self.app, _('Project merged'), _("Review the action log for details.")).exec()

    def cancel_merge(self, save_journal):
        """ Undo anything copied, report and release the source project. """

        self.merge_cancelled = True
        self.remove_copied_files()
        self.summary_msg += "\n" + _("Merge cancelled. No changes were made.") + "\n"
        if save_journal and self.preview_sections:
            self.save_report_to_journal(merged=False)
        self.close_connections()
        Message(self.app, _('Project not merged'), _("Merge cancelled")).exec()

    def remove_copied_files(self):
        """ Delete media files copied during a merge that did not complete. """

        for file_path in self.copied_files:
            try:
                Path(file_path).unlink(missing_ok=True)
            except OSError as err:
                logger.warning(f"Could not remove {file_path}: {err}")
        self.copied_files = []

    def close_connections(self):
        """ Close the progress dialog and release both project databases. """

        self.progress.close()
        for name in ('conn_s', 'conn_d'):
            conn = getattr(self, name)
            if conn is None:
                continue
            try:
                conn.close()
            except sqlite3.Error as err:
                logger.warning(f"Closing {name}: {err}")
            setattr(self, name, None)

    def _emit_project_table_changes(self, tables):
        """Notify other open dialogs about changed project tables."""

        if getattr(self.app, "project_events", None) is not None:
            self.app.project_events.emit_table_changes(tables, source=self)

    def build_preview(self):
        """ Read only summary of what the merge would add. Runs after get_source_data and
        before anything is written.
        Return: [{'title': str, 'detail': str, 'items': [str], 'warning': bool}, ...]
        """

        cur_s = self.conn_s.cursor()
        cur_d = self.conn_d.cursor()
        sections = []

        def add(title, detail, items=None, warning=False):
            items = list(items or [])
            # Cap the listed names, the section count still carries the full figure
            if len(items) > MAX_LISTED_ITEMS:
                remaining = len(items) - MAX_LISTED_ITEMS
                items = items[:MAX_LISTED_ITEMS] + [_("and more, not listed: ") + str(remaining)]
            sections.append({'title': title, 'detail': detail, 'items': items, 'warning': warning})

        # Files
        new_files = []
        matched_files = []
        length_warnings = []
        for src in self.source_s:
            cur_d.execute("select id, length(fulltext) from source where name=?", [src['name']])
            res = cur_d.fetchone()
            if res is None:
                new_files.append(src['name'])
                continue
            matched_files.append(src['name'])
            if src['fulltext_len'] is not None and src['fulltext_len'] != res[1]:
                length_warnings.append(
                    src['name'] + " " + _("source: ") + f"{src['fulltext_len']} " +
                    _("destination: ") + f"{res[1]}")
        add(_("Files to add"), str(len(new_files)), new_files)
        add(_("Files already in this project"), str(len(matched_files)), matched_files)
        if length_warnings:
            add(_("Warning: different text lengths for the same file name"),
                str(len(length_warnings)), length_warnings, warning=True)

        # Media files to copy into the project folders
        files_to_copy = []
        for folder_name in ("audio", "documents", "images", "video"):
            source_dir = Path(self.path_s) / folder_name
            if not source_dir.is_dir():
                continue
            for file_ in source_dir.iterdir():
                if file_.is_file() and not (Path(self.app.project_path) / folder_name / file_.name).exists():
                    files_to_copy.append(f"{folder_name}/{file_.name}")
        add(_("Media files to copy"), str(len(files_to_copy)), files_to_copy)

        # Categories. get_source_data already removed names present in the destination
        cur_s.execute("select count(*) from code_cat")
        total_cats = cur_s.fetchone()[0]
        new_cat_names = [c['name'] for c in self.categories_s]
        add(_("Code categories to add"), str(len(new_cat_names)), new_cat_names)
        add(_("Code categories already in this project"), str(total_cats - len(new_cat_names)))

        # Codes
        cur_d.execute("select name from code_name")
        dest_code_names = [r[0] for r in cur_d.fetchall()]
        new_codes = [c['name'] for c in self.codes_s if c['name'] not in dest_code_names]
        matched_codes = [c['name'] for c in self.codes_s if c['name'] in dest_code_names]
        add(_("Codes to add"), str(len(new_codes)), new_codes)
        add(_("Codes matched to existing codes"), str(len(matched_codes)), matched_codes)

        # Codings. Counts are what will actually be added, so rows already in the destination
        # and duplicates inside the source are excluded. New codes and files get placeholder keys
        cur_d.execute("select name, id from source")
        dest_file_ids = {r[0]: r[1] for r in cur_d.fetchall()}
        cur_d.execute("select name, cid from code_name")
        dest_code_ids = {r[0]: r[1] for r in cur_d.fetchall()}
        source_code_names = {c['cid']: c['name'] for c in self.codes_s}
        source_file_names = {s['id']: s['name'] for s in self.source_s}

        def code_key(cid):
            """ Destination cid, or a placeholder for a code not there yet. """

            name = source_code_names.get(cid)
            if name is None:
                return None  # No code row in the source
            return dest_code_ids.get(name, ('new_code', name))

        def file_key(fid):
            """ Destination file id, or a placeholder for a file not there yet. """

            name = source_file_names.get(fid)
            if name is None:
                return None  # No file row in the source
            return dest_file_ids.get(name, ('new_file', name))

        def split_new(rows, dest_sql, key_builder):
            """ Return (to_add, already_there, orphans) for the source rows. """

            cur_d.execute(dest_sql)
            seen = set(cur_d.fetchall())
            to_add, already_there, orphans = 0, 0, 0
            for row in rows:
                key = key_builder(row)
                if key is None:
                    orphans += 1
                    continue
                if key in seen:
                    already_there += 1
                    continue
                seen.add(key)
                to_add += 1
            return to_add, already_there, orphans

        def text_key(c):
            cid, fid = code_key(c['cid']), file_key(c['fid'])
            return None if cid is None or fid is None else (cid, fid, c['pos0'], c['pos1'], c['owner'])

        def image_key(c):
            cid, fid = code_key(c['cid']), file_key(c['fid'])
            if cid is None or fid is None:
                return None
            return cid, fid, c['x1'], c['y1'], c['width'], c['height'], c['owner'], c['pdf_page']

        def av_key(c):
            cid, fid = code_key(c['cid']), file_key(c['fid'])
            return None if cid is None or fid is None else (cid, fid, c['pos0'], c['pos1'], c['owner'])

        def annotation_key(a):
            fid = file_key(a['fid'])
            return None if fid is None else (fid, a['pos0'], a['pos1'], a['owner'])

        orphan_total = 0
        text_add, text_old, orphans = split_new(
            self.code_text_s, "select cid, fid, pos0, pos1, owner from code_text", text_key)
        orphan_total += orphans
        pdf_rows = [c for c in self.code_image_s if c['pdf_page'] is not None]
        image_rows = [c for c in self.code_image_s if c['pdf_page'] is None]
        image_sql = "select cid, id, x1, y1, width, height, owner, pdf_page from code_image"
        pdf_add, pdf_old, orphans = split_new(pdf_rows, image_sql, image_key)
        orphan_total += orphans
        image_add, image_old, orphans = split_new(image_rows, image_sql, image_key)
        orphan_total += orphans
        av_add, av_old, orphans = split_new(
            self.code_av_s, "select cid, id, pos0, pos1, owner from code_av", av_key)
        orphan_total += orphans
        annot_add, annot_old, orphans = split_new(
            self.annotations_s, "select fid, pos0, pos1, owner from annotation", annotation_key)
        orphan_total += orphans
        add(_("Coded text segments to add"), str(text_add))
        add(_("Coded PDF areas to add"), str(pdf_add))
        add(_("Coded image areas to add"), str(image_add))
        add(_("Coded audio/video segments to add"), str(av_add))
        add(_("Text annotations to add"), str(annot_add))
        already_there = text_old + pdf_old + image_old + av_old + annot_old
        if already_there > 0:
            add(_("Codings already in this project, not duplicated"), str(already_there))
        if orphan_total > 0:
            add(_("Codings skipped, missing code or file in the source project"),
                str(orphan_total), warning=True)

        # Cases. A source case whose name is in the destination is skipped with its links
        cur_d.execute("select name from cases")
        dest_case_names = [r[0] for r in cur_d.fetchall()]
        new_cases = [c for c in self.cases_s if c['name'] not in dest_case_names]
        skipped_cases = [c['name'] for c in self.cases_s if c['name'] in dest_case_names]
        new_case_ids = [c['caseid'] for c in new_cases]
        # Inserted only when both case and file resolve
        case_links = len([ct for ct in self.case_text_s
                          if ct['caseid'] in new_case_ids and ct['fid'] in source_file_names])
        add(_("Cases to add"), str(len(new_cases)), [c['name'] for c in new_cases])
        add(_("Cases skipped, name already in this project"), str(len(skipped_cases)), skipped_cases)
        add(_("Case file links to add"), str(case_links))

        # Journals and stored queries
        cur_d.execute("select name from journal")
        dest_journal_names = [r[0] for r in cur_d.fetchall()]
        new_journals = [j['name'] for j in self.journals_s if j['name'] not in dest_journal_names]
        skipped_journals = [j['name'] for j in self.journals_s if j['name'] in dest_journal_names]
        add(_("Journals to add"), str(len(new_journals)), new_journals)
        add(_("Journals skipped, name already in this project"), str(len(skipped_journals)), skipped_journals)
        cur_d.execute("select title from stored_sql")
        dest_sql_titles = [r[0] for r in cur_d.fetchall()]
        new_sql = [s['title'] for s in self.stored_sql_s if s['title'] not in dest_sql_titles]
        add(_("Stored queries to add"), str(len(new_sql)), new_sql)

        # Attributes. get_source_data already removed types present in the destination
        add(_("Attribute types to add"), str(len(self.attribute_types_s)),
            [f"{a['name']} ({a['caseOrFile']})" for a in self.attribute_types_s])
        # Values carry over for files, and for cases being added
        attribute_values = len([a for a in self.attributes_s
                                if (a['attr_type'] == "file" and a['id'] in source_file_names)
                                or (a['attr_type'] == "case" and a['id'] in new_case_ids)])
        add(_("Attribute values"), str(attribute_values))
        return sections

    def report_text(self, merged):
        """ Plain text preview for the journal entry. merged: False if cancelled. """

        lines = [_("Merge preview"), "",
                 _("Merging: ") + self.path_s,
                 _("Into: ") + self.path_d,
                 _("Date: ") + datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                 _("Result: ") + (_("merged") if merged else _("cancelled, no changes were made")),
                 ""]
        for section in self.preview_sections:
            lines.append(f"{section['title']}: {section['detail']}")
            for item in section['items']:
                lines.append(f"    {item}")
        return "\n".join(lines)

    def save_report_to_journal(self, merged):
        """ Store the report as a journal entry. Journal names must be unique. """

        now = datetime.datetime.now().astimezone()
        date = now.strftime("%Y-%m-%d %H:%M:%S")
        owner = self.app.settings['codername']
        # Valid journal name: no dots or colons, and unique
        name = re.sub(r"[^\w -]", "_", f"Merge preview {Path(self.path_s).stem} {now.strftime('%Y-%m-%d %H%M%S')}")
        jentry = self.report_text(merged)
        cur = self.conn_d.cursor()
        attempt = name
        suffix = 2
        while True:
            try:
                cur.execute("insert into journal(name,jentry,owner,date) values(?,?,?,?)",
                            (attempt, jentry, owner, date))
                self.conn_d.commit()
                break
            except sqlite3.IntegrityError:
                self.conn_d.rollback()
                attempt = f"{name}_{suffix}"
                suffix += 1
                if suffix > 50:
                    logger.warning("Could not create the merge preview journal entry")
                    return
        self.app.delete_backup = False
        self.summary_msg += _("Merge report saved to journal: ") + attempt + "\n"
        self._emit_project_table_changes(['journal'])

    def insert_categories(self):
        """ Insert categories into destination code_cat table.
         The categories have already been filtered to remove any names that match names
         in the destination database.
         """

        cur_d = self.conn_d.cursor()
        # Insert top level categories
        remove_list = []
        for c in self.categories_s:
            if c['supercatname'] is None:
                self.summary_msg += _("Adding top level category: ") + c['name'] + "\n"
                cur_d.execute("insert into code_cat (name,memo,owner,date,supercatid) values(?,?,?,?,?)",
                              (c['name'], c['memo'], c['owner'], c['date'], c['supercatid']))
                remove_list.append(c)
        for item in remove_list:
            self.categories_s.remove(item)

        ''' Add sub-categories. look at each unmatched category, iterate through
        to add as child, then remove from the list '''
        count = 0
        while len(self.categories_s) > 0 and count < 1000:
            remove_list = []
            for c in self.categories_s:
                # This needs to be repeated as it is changes
                cur_d.execute("select catid from code_cat where name=?", [c['supercatname']])
                res_category = cur_d.fetchone()
                if res_category is not None:
                    remove_list.append(c)
                    sql = "insert into code_cat (name, memo, owner, date, supercatid) values (?,?,?,?,?)"
                    cur_d.execute(sql, [c['name'], c['memo'], c['owner'], c['date'], res_category[0]])
                    self.summary_msg += _("Adding sub-category: ") + f"{c['name']} --> {c['supercatname']}\n"
            for item in remove_list:
                self.categories_s.remove(item)
            count += 1

        if len(self.categories_s) > 0:
            self.summary_msg += str(len(self.categories_s)) + _(" categories not added") + "\n"
            logger.debug("Categories NOT added:\n" + str(self.categories_s))

    def update_code_cid_and_insert_code(self):
        """ Update the cid to the one already in Destination.code_name.
        Check for no matches and insert these into the Destination.code_name table.
        """

        cur_d = self.conn_d.cursor()
        cur_d.execute("select name, catid from code_cat")
        dest_categories = cur_d.fetchall()

        sql = "select cid, name from code_name"
        cur_d.execute(sql)
        res = cur_d.fetchall()
        for code_dest in res:
            for code_source in self.codes_s:
                if code_source['name'] == code_dest[1]:
                    code_source['newcid'] = code_dest[0]

        # Insert unmatched code names
        for code_s in self.codes_s:
            if code_s['newcid'] == -1:
                # Fill category id using matching category name
                for cat in dest_categories:
                    if cat[0] == code_s['catname']:
                        code_s['catid'] = cat[1]
                cur_d.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,?,?,?,?)",
                              (code_s['name'], code_s['memo'], code_s['owner'], code_s['date'], code_s['catid'],
                               code_s['color']))
                cur_d.execute("select last_insert_rowid()")
                cid = cur_d.fetchone()[0]
                code_s['newcid'] = cid
                code_s['inserted'] = True
                self.summary_msg += _("Adding code name: ") + code_s['name'] + "\n"

        # Resolve sub-code parents (supercid) for newly inserted codes, by parent code name.
        # Only inserted codes are touched, so the destination's existing hierarchy is preserved.
        name_to_newcid = {}
        for code_s in self.codes_s:
            if code_s['newcid'] != -1:
                name_to_newcid.setdefault(code_s['name'], code_s['newcid'])
        cur_d.execute("select cid, name from code_name")
        for r in cur_d.fetchall():
            name_to_newcid.setdefault(r[1], r[0])
        for code_s in self.codes_s:
            if code_s.get('inserted') and code_s.get('supercodename'):
                parent_newcid = name_to_newcid.get(code_s['supercodename'])
                if parent_newcid is not None and parent_newcid != code_s['newcid']:
                    cur_d.execute("update code_name set supercid=?, catid=null where cid=?",
                                  [parent_newcid, code_s['newcid']])

        # Update code_text, code_image, code_av cids to destination values
        new_cids = {code_s['cid']: code_s['newcid'] for code_s in self.codes_s}
        for rows in (self.code_text_s, self.code_image_s, self.code_av_s):
            for row in rows:
                row['newcid'] = new_cids.get(row['cid'], -1)

    def insert_coding_and_journal_data(self):
        """ Coding fid and cid have been updated, annotation fid has been updated.
        Insert code_text, code_image, code_av, journal and stored_sql data into Destination project. """

        cur_d = self.conn_d.cursor()
        # Earlier db versions did not have unique journal name
        # Need to identify duplicate journal names and not import them
        cur_d.execute("select name from journal")
        j_names_res = cur_d.fetchall()
        j_names = [j[0] for j in j_names_res]
        '''for j in j_names_res:
            j_names.append(j[0])'''
        for j in self.journals_s:
            # Possible to have two identical journal names in earlier db versions
            if j['name'] not in j_names:
                cur_d.execute("insert into journal (name, jentry, date, owner) values(?,?,?,?)",
                              (j['name'], j['jentry'], j['date'], j['owner']))
                self.summary_msg += _("Adding journal: ") + j['name'] + "\n"
        for s in self.stored_sql_s:
            # Cannot have two identical stored_sql titles, using 'or ignore'
            cur_d.execute("insert or ignore into stored_sql (title, description, grouper, ssql) values(?,?,?,?)",
                          (s['title'], s['description'], s['grouper'], s['ssql']))
        # A/V goes in before coded text, so code_text.avid can be remapped to the new avid.
        # code_av and code_image have no unique constraint, so 'insert or ignore' would not stop
        # duplicates: existing rows are matched by key set, which keeps a repeated merge idempotent
        skipped_orphans = 0
        avid_map = {}
        cur_d.execute("select avid, cid, id, pos0, pos1, owner from code_av")
        existing_av = {}
        for row in cur_d.fetchall():
            existing_av.setdefault(tuple(row[1:]), row[0])
        self.progress.phase(_("Merging audio/video codings"), 40, repaint=False)
        for c in self.code_av_s:
            if c['newcid'] == -1 or c['newfid'] == -1:
                skipped_orphans += 1
                continue
            key = (c['newcid'], c['newfid'], c['pos0'], c['pos1'], c['owner'])
            if key in existing_av:
                c['newavid'] = existing_av[key]
            else:
                cur_d.execute(
                    "insert into code_av (cid, id,pos0,pos1,memo,owner,date,important) values(?,?,?,?,?,?,?,?)",
                    [c["newcid"], c["newfid"], c["pos0"], c["pos1"], c["memo"], c["owner"], c["date"],
                     c["important"]])
                c['newavid'] = cur_d.lastrowid
                existing_av[key] = c['newavid']
            if c['avid'] is not None:
                avid_map[c['avid']] = c['newavid']
        if len(self.code_av_s) > 0:
            self.summary_msg += _("Merging coded audio/video segments") + "\n"
        self.progress.phase(_("Merging coded text"), 55, repaint=False)
        for c in self.code_text_s:
            if c['newcid'] == -1 or c['newfid'] == -1:
                skipped_orphans += 1
                continue
            c['newavid'] = avid_map.get(c['avid']) if c['avid'] is not None else None
            cur_d.execute("insert or ignore into code_text (cid,fid,seltext,pos0,pos1,owner,\
                memo,date, important, avid) values(?,?,?,?,?,?,?,?,?,?)", (c['newcid'], c['newfid'],
                                                                           c['seltext'], c['pos0'], c['pos1'],
                                                                           c['owner'], c['memo'], c['date'],
                                                                           c['important'], c['newavid']))
        if len(self.code_text_s) > 0:
            self.summary_msg += _("Merging coded text") + "\n"
        for a in self.annotations_s:
            if a['newfid'] == -1:
                skipped_orphans += 1
                continue
            cur_d.execute("insert or ignore into annotation (fid,pos0,pos1,memo,owner,date) values(?,?,?,?,?,?)",
                          [a["newfid"], a["pos0"], a["pos1"], a["memo"], a["owner"], a["date"]])
        if len(self.annotations_s) > 0:
            self.summary_msg += _("Merging annotations") + "\n"
        cur_d.execute("select cid, id, x1, y1, width, height, owner, pdf_page from code_image")
        existing_images = set(cur_d.fetchall())
        self.progress.phase(_("Merging coded image and PDF areas"), 75, repaint=False)
        for c in self.code_image_s:
            if c['newcid'] == -1 or c['newfid'] == -1:
                skipped_orphans += 1
                continue
            key = (c['newcid'], c['newfid'], c['x1'], c['y1'], c['width'], c['height'], c['owner'], c['pdf_page'])
            if key in existing_images:
                continue
            cur_d.execute(
                "insert into code_image (cid, id,x1,y1,width,height,memo,owner,date,important,pdf_page) "
                "values(?,?,?,?,?,?,?,?,?,?,?)",
                [c["newcid"], c["newfid"], c["x1"], c["y1"], c["width"], c["height"], c["memo"], c["owner"], c["date"],
                 c["important"], c["pdf_page"]])
            existing_images.add(key)
        if len(self.code_image_s) > 0:
            self.summary_msg += _("Merging coded image areas") + "\n"
        if skipped_orphans > 0:
            # Source codings whose code or file row is missing
            self.summary_msg += _("Codings skipped, missing code or file: ") + f"{skipped_orphans}\n"

    def insert_cases(self):
        """ Insert case data into destination.
        First remove all existing matching case names and the associated case text data.
        """

        cur_d = self.conn_d.cursor()
        # Remove all duplicate cases and case text lists from source data
        cur_d.execute("select name from cases")
        res_cases_dest = cur_d.fetchall()
        existing_case_names = [r[0] for r in res_cases_dest]
        '''for r in res_cases_dest:
            existing_case_names.append(r[0])'''
        remove_case_list = []
        for case_s in self.cases_s:
            if case_s['name'] in existing_case_names:
                remove_case_list.append(case_s)
        removed_case_text_list = []
        for removed_case in remove_case_list:
            self.cases_s.remove(removed_case)
            for case_text in self.case_text_s:
                if case_text['caseid'] == removed_case['caseid']:
                    removed_case_text_list.append(case_text)
        for removed_case_text in removed_case_text_list:
            self.case_text_s.remove(removed_case_text)

        # Insert new cases into destination
        new_case_ids = []
        for case_s in self.cases_s:
            cur_d.execute("insert into cases (name, memo, owner, date) values (?,?,?,?)",
                          [case_s['name'], case_s['memo'], case_s['owner'], case_s['date']])
            cur_d.execute("select last_insert_rowid()")
            case_id = cur_d.fetchone()[0]
            case_s['newcaseid'] = case_id
            new_case_ids.append(case_id)
            self.summary_msg += _("Adding case: ") + case_s['name'] + "\n"
        # Update newcaseid and newfid in case_text
        for case_text in self.case_text_s:
            for case_s in self.cases_s:
                if case_s['caseid'] == case_text['caseid']:
                    case_text['newcaseid'] = case_s['newcaseid']
            for file_ in self.source_s:
                # fid is a source id. Matching newid loses links or points them at the wrong file
                if case_text['fid'] == file_['id']:
                    case_text['newfid'] = file_['newid']
        # Insert case text if newfileid is not -1 and newcaseid is not -1
        for c in self.case_text_s:
            if c['newcaseid'] > -1 and c['newfid'] > -1:
                cur_d.execute("insert into case_text (caseid,fid,pos0,pos1,owner,date,memo) values(?,?,?,?,?,?,?)",
                              [c['newcaseid'], c['newfid'], c['pos0'], c['pos1'], c['owner'], c['date'], c['memo']])
        # Create attribute placeholders for the destination case attributes
        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        sql_attribute_types = 'select name from attribute_type where caseOrFile ="case"'
        cur_d.execute(sql_attribute_types)
        res_attr_types = cur_d.fetchall()
        # Placeholders for cases, so attr_type is case, not file
        sql_attribute = "insert or ignore into attribute (name, attr_type, value, id, date, owner) " \
                        "values(?,'case','',?,?,?)"
        for id_ in new_case_ids:
            for attribute_name in res_attr_types:
                cur_d.execute(sql_attribute, [attribute_name[0], id_, now_date, self.app.settings['codername']])

    def insert_sources_get_new_file_ids(self):
        """ Insert Source.source into Destination.source, unless source file name is already present.
        update newfid in source_s and code_text_s.
        Update the av_text_id link to link A/V to the corresponding transcript.
        """

        new_source_file_ids = []
        cur_d = self.conn_d.cursor()
        for src in self.source_s:
            cur_d.execute("select id, length(fulltext) from source where name=?", [src['name']])
            res = cur_d.fetchone()
            if res is not None:
                # Existing same named source file is in the destination database
                src['newid'] = res[0]
                # Warn user if the source and destination fulltexts are different lengths
                # Occurs if one of the texts was edited or replaced
                # Check fulltext for not None, as might be image, audio, video
                if src['fulltext_len'] is not None and src['fulltext_len'] != res[1]:
                    msg = _("Warning! Inaccurate coding positions. Text lengths different for same text file: ")
                    msg += src['name'] + "\n"
                    msg += _("Import project file text length: ") + f"{src['fulltext_len']}  "
                    msg += _("Destination project file text length: ") + str(res[1]) + "\n"
                    self.summary_msg += msg
            else:
                # To update the av_text_id after all new ids have been generated
                cur_s = self.conn_s.cursor()
                cur_s.execute("select fulltext from source where id=?", [src['id']])
                fulltext = cur_s.fetchone()[0]
                cur_d.execute(
                    "insert into source(name,fulltext,mediapath,memo,owner,date, av_text_id) values(?,?,?,?,?,?,?)",
                    (src['name'], fulltext, src['mediapath'], src['memo'], src['owner'], src['date'], None))
                cur_d.execute("select last_insert_rowid()")
                id_ = cur_d.fetchone()[0]
                src['newid'] = id_
                new_source_file_ids.append(id_)

        # Need to find matching av_text_filename to get its id to link as the av_text_id
        for src in self.source_s:
            if src['av_text_filename'] != "":
                cur_d.execute("select id from source where name=?", [src['av_text_filename']])
                res = cur_d.fetchone()
                if res is not None:
                    cur_d.execute("update source set av_text_id=? where id=?", [res[0], src['newid']])

        # Create attribute placeholders for the destination file attributes
        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        sql_attribute_types = 'select name from attribute_type where caseOrFile ="file"'
        cur_d.execute(sql_attribute_types)
        res_attr_types = cur_d.fetchall()
        sql_attribute = "insert into attribute (name, attr_type, value, id, date, owner) values(?,'file','',?,?,?)"
        for id_ in new_source_file_ids:
            for attribute_name in res_attr_types:
                cur_d.execute(sql_attribute, [attribute_name[0], id_, now_date, self.app.settings['codername']])

    def update_coding_file_ids(self):
        """ Update the file ids in the codings and annotations data. """

        new_ids = {src['id']: src['newid'] for src in self.source_s}
        for rows in (self.code_text_s, self.annotations_s, self.code_image_s, self.code_av_s):
            for row in rows:
                row['newfid'] = new_ids.get(row['fid'], -1)

    def copy_source_files_into_destination(self):
        """ Copy source files into destination project.
        Do not copy over existing files.
        """

        folders = ["audio", "documents", "images", "video"]
        to_copy = []
        for folder_name in folders:
            source_dir = Path(self.path_s) / folder_name  # self.path_s + "/" + folder_name
            if not source_dir.is_dir():
                continue
            dest_dir = Path(self.app.project_path) / folder_name
            for file_ in source_dir.iterdir():
                # iterdir yields absolute paths. Joining one replaces the destination folder
                if file_.is_file() and not (dest_dir / file_.name).exists():
                    to_copy.append((file_, dest_dir / file_.name))
        for index, (source_file, dest_path) in enumerate(to_copy):
            # Media can be large, so cancel is checked on every file and inside each one
            self.progress.tick(index, len(to_copy), 15, 20, every=1)
            try:
                self.copy_one_file(source_file, dest_path)
                self.copied_files.append(dest_path)
                self.summary_msg += _("File copied: ") + f"{source_file.name}\n"
            except shutil.SameFileError:
                pass
            except PermissionError:
                self.summary_msg += f"{source_file.name} " + _("NOT copied. Permission error")

    def copy_one_file(self, source_file, dest_path):
        """ Copy in chunks, so Cancel responds part way through a large video.
        A cancel removes the partial file before raising.
        """

        chunk = 8 * 1024 * 1024
        try:
            with open(source_file, 'rb') as f_in, open(dest_path, 'wb') as f_out:
                while True:
                    buffer = f_in.read(chunk)
                    if not buffer:
                        break
                    f_out.write(buffer)
                    self.progress.check()
        except MergeCancelled:
            Path(dest_path).unlink(missing_ok=True)
            raise
        shutil.copystat(source_file, dest_path)

    def insert_new_attribute_types(self):
        """ Insert new attribute types  for cases and files.
        Insert placeholders for the new attribute types.
        To be performed after Cases and files have been inserted.
        """

        cur_d = self.conn_d.cursor()
        cur_d.execute("select id from source")
        res_file_ids = cur_d.fetchall()
        cur_d.execute("select caseid from cases")
        res_case_ids = cur_d.fetchall()
        # Insert new attribute type and placeholder in attribute table
        for a in self.attribute_types_s:
            cur_d.execute("insert into attribute_type (name,date,owner,memo,caseOrFile, valuetype) values(?,?,?,?,?,?)",
                          (a['name'], a['date'], a['owner'], a['memo'], a['caseOrFile'], a['valuetype']))
            self.summary_msg += _("Adding attribute (") + a['caseOrFile'] + "): " + a['name'] + "\n"
            # Create attribute placeholders for new attributes, does NOT create for existing destination attributes
            if a['caseOrFile'] == "file":
                for id_ in res_file_ids:
                    sql = "insert into attribute (name, value, id, attr_type, date, owner) values (?,?,?,?,?,?)"
                    cur_d.execute(sql, (a['name'], "", id_[0], "file", a['date'], a['owner']))
            if a['caseOrFile'] == "case":
                for id_ in res_case_ids:
                    sql = "insert into attribute (name, value, id, attr_type, date, owner) values (?,?,?,?,?,?)"
                    cur_d.execute(sql, (a['name'], "", id_[0], "case", a['date'], a['owner']))

    def insert_attributes(self):
        """ Insert new attribute values for files and cases.
         Need to use destination file and case ids.
         Example attribute:
         {'name': 'age', 'attr_type': 'file', 'value': '100', 'id': 4, 'newid': -1, 'date': '2022-03-14 10:35:27', 'owner': 'default'}
         """

        # Only update if value does not over-write an existing placeholder attribute value
        sql_update = "update attribute set value=? where name=? and id=? and attr_type=? and value=''"
        # Insert if a placeholder is missing
        sql_insert = "insert into attribute (name,id,attr_type,value,date,owner) values (?,?,?,?,?,?)"
        attribute_count = 0
        cur_d = self.conn_d.cursor()
        for a in self.attributes_s:
            if a['attr_type'] == "file":
                source_dict = next((item for item in self.source_s if item["id"] == a['id']), {'newid': -1})
                a['newid'] = source_dict['newid']
            if a['attr_type'] == "case":
                case_dict = next((item for item in self.cases_s if item["caseid"] == a['id']), {'newcaseid': -1})
                a['newid'] = case_dict['newcaseid']
            # Only update or insert value does not over-write an existing placeholder attribute value
            if a['newid'] != -1:
                # Check placeholder exists, if not then insert values
                cur_d.execute("select * from attribute where name=? and id=? and attr_type=?",
                              [a['name'], a['newid'], a['attr_type']])
                res = cur_d.fetchall()
                if not res:
                    cur_d.execute(sql_insert,
                                  (a['name'], a['newid'], a['attr_type'], a['value'], a['date'], a['owner']))
                    attribute_count += 1
                else:
                    cur_d.execute(sql_update, (a['value'], a['name'], a['newid'], a['attr_type']))
                    attribute_count += 1
        if attribute_count > 0:
            self.summary_msg += _("Added attribute values for cases and files: n=") + str(attribute_count) + "\n"

    def get_source_data(self) -> bool:
        """ Load the database data into Lists of Dictionaries.
        Return:
            True or False if data could be loaded
        """

        self.journals_s = []
        self.stored_sql_s = []
        self.codes_s = []
        self.categories_s = []
        self.code_text_s = []
        self.annotations_s = []
        self.code_image_s = []
        self.code_av_s = []
        self.cases_s = []
        self.case_text_s = []
        self.source_s = []
        self.attribute_types_s = []
        self.attributes_s = []
        cur_s = self.conn_s.cursor()
        # Database version must be v5 or higher
        try:
            cur_s.execute("select databaseversion from project")
            version = cur_s.fetchone()
        except sqlite3.DatabaseError as err:
            logger.warning(f"Merge source project: {err}")
            version = None
        if version is None or version[0] is None:
            self.summary_msg += _("Could not read the source project database.") + "\n"
            self.summary_msg += _("Project not merged") + "\n"
            return False
        if version[0] in ("v1", "v2", "v3", "v4"):
            self.summary_msg += _("Need to update the source project database.") + "\n"
            self.summary_msg += _("Please open the source project using QualCoder. Then close the project.") + "\n"
            self.summary_msg += _("This will update the database schema. Then try merging again.")
            self.summary_msg += _("Project not merged") + "\n"
            return False
        # Journal data
        sql_journal = "select name, jentry, date, owner from journal"
        cur_s.execute(sql_journal)
        res_journals = cur_s.fetchall()
        for i in res_journals:
            src = {"name": i[0], "jentry": i[1], "date": i[2], "owner": i[3]}
            self.journals_s.append(src)
        # Stored sql data
        sql_stored_sql = "select title, description, grouper, ssql from stored_sql"
        cur_s.execute(sql_stored_sql)
        res_stored_sqls = cur_s.fetchall()
        for i in res_stored_sqls:
            src = {"title": i[0], "description": i[1], "grouper": i[2], "ssql": i[3]}
            self.stored_sql_s.append(src)
        # Source data
        # length(fulltext) only. Holding every document's text would cost as much memory as
        # the project itself. The text is fetched per file when it is inserted
        sql_source = "select id, name, length(fulltext),mediapath,memo,owner,date,av_text_id from source"
        cur_s.execute(sql_source)
        res_source = cur_s.fetchall()
        # Later update av_text_id
        for i in res_source:
            src = {"id": i[0], "newid": -1, "name": i[1], "fulltext_len": i[2], "mediapath": i[3], "memo": i[4],
                   "owner": i[5], "date": i[6], "av_text_id": i[7], "av_text_filename": ""}
            self.source_s.append(src)
        # The av_text_id is not enough to recreate linkages. Need the referenced text file name.
        for i in self.source_s:
            if i['av_text_id'] is not None:
                cur_s.execute("select name from source where id=?", [i['av_text_id']])
                res = cur_s.fetchone()
                if res is not None:
                    i['av_text_filename'] = res[0]
        # Category data
        sql_codecats = "select catid, supercatid, name, memo, owner, date from code_cat"
        cur_s.execute(sql_codecats)
        res_codecats = cur_s.fetchall()
        for i in res_codecats:
            ccat = {"catid": i[0], "supercatid": i[1], "supercatname": None,
                    "name": i[2], "memo": i[3], "owner": i[4], "date": i[5], }
            self.categories_s.append(ccat)
        # Remove categories from the source list, that are already present in the destination database
        cur_d = self.conn_d.cursor()
        cur_d.execute("select name from code_cat")
        res_dest_catnames = cur_d.fetchall()
        dest_cat_names_list = [r[0] for r in res_dest_catnames]
        '''for r in res_dest_catnames:
            dest_cat_names_list.append(r[0])'''
        temp_source_cats = []
        for cat in self.categories_s:
            if cat['name'] not in dest_cat_names_list:
                temp_source_cats.append(cat)
        self.categories_s = temp_source_cats
        # Add reference to linked supercat using category name
        for cat in self.categories_s:
            cur_s.execute("select name from code_cat where catid=?", [cat['supercatid']])
            res = cur_s.fetchone()
            if res is not None:
                cat['supercatname'] = res[0]
        # Code data
        sql_codenames = "select cid, name, memo, owner, date, color, catid, supercid from code_name"
        cur_s.execute(sql_codenames)
        res_codes = cur_s.fetchall()
        for i in res_codes:
            code_s = {"cid": i[0], "newcid": -1, "name": i[1], "memo": i[2], "owner": i[3], "date": i[4], "color": i[5],
                      "catid": i[6], "catname": None, "supercid": i[7], "supercodename": None}
            self.codes_s.append(code_s)
        # Get and fill category name if code is in a category
        for code_s in self.codes_s:
            cur_s.execute("select name from code_cat where catid=?", [code_s['catid']])
            res = cur_s.fetchone()
            if res is not None:
                code_s['catname'] = res[0]
        # Fill parent code name if this is a sub-code (nested under another code via supercid)
        for code_s in self.codes_s:
            if code_s['supercid'] is not None:
                cur_s.execute("select name from code_name where cid=?", [code_s['supercid']])
                res = cur_s.fetchone()
                if res is not None:
                    code_s['supercodename'] = res[0]
        # Code text data. avid links a transcript coding to its A/V segment, remapped on insert
        sql_codetext = "select cid, fid, seltext, pos0, pos1, owner, date, memo, important, avid from code_text"
        cur_s.execute(sql_codetext)
        res_codetext = cur_s.fetchall()
        for i in res_codetext:
            ct = {"cid": i[0], "newcid": -1, "fid": i[1], "newfid": -1, "seltext": i[2], "pos0": i[3], "pos1": i[4],
                  "owner": i[5], "date": i[6], "memo": i[7], "important": i[8], "avid": i[9], "newavid": None}
            self.code_text_s.append(ct)
        # Text annotations data
        sql_annotations = "select fid, pos0, pos1, memo, owner, date from annotation"
        cur_s.execute(sql_annotations)
        res_annot = cur_s.fetchall()
        for i in res_annot:
            an = {"fid": i[0], "newfid": -1, "pos0": i[1], "pos1": i[2], "memo": i[3], "owner": i[4], "date": i[5]}
            self.annotations_s.append(an)
        # Code image data. pdf_page is the page of an area coded on a PDF.
        # Databases older than v10 lack the column, so select a null placeholder
        cur_s.execute("pragma table_info(code_image)")
        code_image_columns = [r[1] for r in cur_s.fetchall()]
        pdf_page_column = "pdf_page" if "pdf_page" in code_image_columns else "null"
        sql_code_img = "select cid, id, x1, y1, width, height, memo, date, owner, important, " \
                       f"{pdf_page_column} from code_image"
        cur_s.execute(sql_code_img)
        res_code_img = cur_s.fetchall()
        for i in res_code_img:
            cimg = {"cid": i[0], "newcid": -1, "fid": i[1], "newfid": -1, "x1": i[2], "y1": i[3],
                    "width": i[4], "height": i[5], "memo": i[6], "date": i[7], "owner": i[8], "important": i[9],
                    "pdf_page": i[10]}
            self.code_image_s.append(cimg)
        # Code AV data. avid is kept to remap code_text.avid
        sql_code_av = "select cid, id, pos0, pos1, owner, date, memo, important, avid from code_av"
        cur_s.execute(sql_code_av)
        res_code_av = cur_s.fetchall()
        for i in res_code_av:
            c_av = {"cid": i[0], "newcid": -1, "fid": i[1], "newfid": -1, "pos0": i[2], "pos1": i[3],
                    "owner": i[4], "date": i[5], "memo": i[6], "important": i[7], "avid": i[8], "newavid": None}
            self.code_av_s.append(c_av)
        # Case data
        sql_cases = "select caseid, name, memo, owner, date from cases"
        cur_s.execute(sql_cases)
        res_cases = cur_s.fetchall()
        for i in res_cases:
            c = {"caseid": i[0], "newcaseid": -1, "name": i[1], "memo": i[2], "owner": i[3], "date": i[4]}
            self.cases_s.append(c)
        sql_case_text = "select caseid, fid, pos0, pos1, owner, date, memo from case_text"
        cur_s.execute(sql_case_text)
        res_case_text = cur_s.fetchall()
        for i in res_case_text:
            c = {"caseid": i[0], "newcaseid": -1, "fid": i[1], "newfid": -1, "pos0": i[2], "pos1": i[3],
                 "owner": i[4], "date": i[5], "memo": i[6]}
            self.case_text_s.append(c)
        # Attribute type data
        sql_attr_type = "select name, memo, date, owner, caseOrFile, valuetype from attribute_type"
        cur_s.execute(sql_attr_type)
        res_attr_type_s = cur_s.fetchall()
        keys = 'name', 'memo', 'date', 'owner', 'caseOrFile', 'valuetype'
        temp_attribute_types_s = []
        for row in res_attr_type_s:
            temp_attribute_types_s.append(dict(zip(keys, row)))
        # Remove matching attribute type names
        cur_d = self.conn_d.cursor()
        cur_d.execute("select name from attribute_type")
        res_attr_name_dest = cur_d.fetchall()
        attribute_names_dest = [r[0] for r in res_attr_name_dest]
        '''for r in res_attr_name_dest:
            attribute_names_dest.append(r[0])'''
        self.attribute_types_s = []
        for r in temp_attribute_types_s:
            if r['name'] not in attribute_names_dest:
                self.attribute_types_s.append(r)
        # Attribute data
        sql_attributes = "select name, attr_type, value, id, date ,owner from attribute"
        cur_s.execute(sql_attributes)
        res_attributes = cur_s.fetchall()
        for i in res_attributes:
            attribute = {"name": i[0], "attr_type": i[1], "value": i[2], "id": i[3], "newid": -1, "date": i[4],
                         "owner": i[5]}
            self.attributes_s.append(attribute)
        return True
