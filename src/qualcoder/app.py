#!/usr/bin/python
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

import configparser
import datetime
import locale as py_locale
import logging
import os
from pathlib import Path
import platform
from PyQt6 import QtCore, QtGui, QtWidgets
import shutil
import sys
import sqlite3
import urllib.request
import urllib.error as urllib_err
import webbrowser
import zipfile
from copy import copy

from qualcoder.ai_llm import get_default_ai_models, update_ai_models
from qualcoder.helpers import get_default_user_directory, Message
from qualcoder.speakers import speaker_coder_name

qc_config_folder = Path('~').expanduser() / '.qualcoder'
logger = logging.getLogger(__name__)
BUILTIN_LANGUAGE_LABELS = [
    ("de", "Deutsch"),
    ("en", "English"),
    ("es", "Español"),
    ("fr", "Français")
]


class ProjectEventBus(QtCore.QObject):
    """Application-wide event bus for project database changes.
    This is used to notify other dialogs (e.g. reports) of changes to the project database,
    so they can update their UI (e.g the code tree)."""

    project_data_changed = QtCore.pyqtSignal(list, object)

    def __init__(self, parent=None):
        """Queue project change notifications until the next event-loop turn."""

        super().__init__(parent)
        self._pending_table_changes = []
        self._dispatch_scheduled = False

    def emit_table_changes(self, tables: list[str] | None, source=None):
        """Emit one project-change event for changed database tables.

        Args:
            tables: List of database table names that changed. An empty list means that no
                project-wide event is emitted.
            source: Optional object identifying the emitter. Subscribers can compare this to
                themselves to ignore events that originated from the same dialog instance.
        """

        if tables is None:
            return
        if len(tables) == 0:
            return
        self._pending_table_changes.append((list(tables), source))
        if self._dispatch_scheduled:
            return
        self._dispatch_scheduled = True
        QtCore.QTimer.singleShot(0, self._dispatch_pending_table_changes)

    @QtCore.pyqtSlot()
    def _dispatch_pending_table_changes(self):
        """Emit pending project-change events after the current UI callback returns."""

        self._dispatch_scheduled = False
        pending = self._pending_table_changes
        self._pending_table_changes = []
        for tables, source in pending:
            self.project_data_changed.emit(tables, source)



class App(object):
    """ General methods for loading settings and recent project stored in .qualcoder folder.
    Savable settings does not contain project name, project path or db connection.
    """

    def __init__(self):
        self.version = "QualCoder 4.0 Beta"  # Must start with 'QualCoder '
        self.citation = f"Citation:\nCurtain C, Dröge K, Missaghieh--Poncet J, Salomón L. (2026) {self.version} [Computer software].\n"
        self.citation += f"Retrieved from https://github.com/ccbogel/QualCoder/releases/tag/{self.version}"
        self.conn = None
        self.project_path = ""
        self.project_name = ""
        self.collapsed_categories = []  # Used across app for consistent expanded/contracted categories in codes tree.
        self.last_export_directory = ""  # Default export location, which may be different from the working directory
        self.delete_backup = True  # Can delete the most current back up if the project has not been altered
        self.delete_backup_path_name = ""
        self.userhome = str(Path('~').expanduser())
        self.confighome = str(qc_config_folder)
        self.configpath = str(qc_config_folder / 'config.ini')
        self.persist_path = str(qc_config_folder / 'recent_projects.txt')
        self.pending_ai_model_upgrade_offer = None
        self.settings, self.ai_models = self.load_settings()
        self.last_export_directory = copy(self.settings['directory'])
        self.ai = None
        # Sentence transformer embedding function. It is stored here so it must not be reloaded every time a project is opened.
        self.ai_embedding_function = None
        self.project_events = ProjectEventBus()

    def read_previous_project_paths(self):
        """ Recent project paths are stored in .qualcoder/recent_projects.txt
        Remove paths that no longer exist.
        Moving from only listing the previous project path to: date opened | previous project path.
        Write a new file in order of most recent opened to older and without duplicate projects.
        """

        previous = []
        try:
            with open(self.persist_path, 'r', encoding='utf-8') as f:
                try:
                    for line in f:
                        previous.append(line.strip())
                except UnicodeDecodeError:
                    pass  # Older projects might have non-utf8 characters
        except FileNotFoundError:
            logger.info('No previous projects found')

        # Add paths that exist
        interim_result = []
        for p in previous:
            splt = p.split("|")
            proj_path = ""
            if len(splt) == 1:
                proj_path = splt[0]
            if len(splt) == 2:
                proj_path = splt[1]
            if Path(proj_path).exists():
                interim_result.append(p)

        # Remove duplicate project names, keep the most recent
        interim_result.sort(reverse=True)
        result = []
        proj_paths = []
        for i in interim_result:
            splt = i.split("|")
            proj_path = ""
            if len(splt) == 1:
                proj_path = splt[0]
            if len(splt) == 2:
                proj_path = splt[1]
            if proj_path not in proj_paths:
                proj_paths.append(proj_path)
                result.append(i)

        # Write the latest projects file in order of most recently opened and without duplicate projects
        with open(self.persist_path, 'w', encoding='utf-8') as f:
            for i, line in enumerate(result):
                if i < 8:
                    f.write(line)
                    f.write("\n")  # text mode: os.linesep would produce \r\r\n on Windows
        return result

    def append_recent_project(self, new_path: str):
        """ Add project path as first entry to .qualcoder/recent_projects.txt
        Args:
            new_path String filepath to project
        """

        if new_path == "":
            return
        nowdate = datetime.datetime.now().astimezone().strftime("%Y-%m-%d_%H:%M:%S")
        # Result is a list of strings containing yyyy-mm-dd:hh:mm:ss|projectpath
        result = self.read_previous_project_paths()
        dated_path = nowdate + "|" + new_path
        # The path is the last '|' field; legacy lines are bare paths without a date.
        # Remove any existing entry for this project and re-add it with a fresh date.
        # Previously, a legacy-format line at result[0] (no '|') silently skipped the
        # append forever, so new projects were never saved to the recent list.
        result = [line for line in result if line.split("|")[-1] != new_path]
        result.append(dated_path)
        result.sort()
        if len(result) > 8:
            result = result[(len(result) - 8):]
        with open(self.persist_path, 'w', encoding='utf-8') as f:
            for line in result:
                f.write(line)
                f.write("\n")  # text mode: os.linesep would produce \r\r\n on Windows

    def get_most_recent_projectpath(self):
        """ Get most recent project path from .qualcoder/recent_projects.txt
        Return:
            path - String or None
        """

        result = self.read_previous_project_paths()
        if result:
            return result[0]
        return None

    def get_builtin_i18n_dir(self):
        """Return the directory that contains bundled translation files."""

        i18n_dir = str(Path(__file__).resolve().parent / 'i18n')
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            i18n_dir = str(Path(sys._MEIPASS) / 'qualcoder' / 'i18n')
        return i18n_dir

    def get_user_i18n_dir(self):
        """Return the user directory for additional translations."""

        return str(Path(self.confighome) / 'i18n')

    def get_user_language_zip_path(self, lang_code):
        """Return the expected zip package path for one user language."""

        return str(Path(self.get_user_i18n_dir()) / f'{lang_code}.zip')

    def get_builtin_language_labels(self):
        """Return the language labels shown in the settings dialog."""

        return list(BUILTIN_LANGUAGE_LABELS)

    def get_initial_language_code(self):
        """Return the best initial language code based on the system locale."""

        available_codes = {code for code, _label in self.get_builtin_language_labels()}
        available_codes.update(self.get_complete_user_language_codes())
        if 'en' not in available_codes:
            available_codes.add('en')

        candidates = []
        try:
            for entry in QtCore.QLocale.system().uiLanguages():
                if entry:
                    candidates.append(entry)
        except Exception:
            pass
        try:
            locale_name = QtCore.QLocale.system().name()
            if locale_name:
                candidates.append(locale_name)
        except Exception:
            pass
        try:
            default_locale = py_locale.getdefaultlocale()[0]
            if default_locale:
                candidates.append(default_locale)
        except Exception:
            pass

        seen = set()
        for candidate in candidates:
            normalized = candidate.replace('-', '_')
            parts = [p for p in normalized.split('_') if p]
            if not parts:
                continue
            primary = parts[0].lower()
            if primary in seen:
                continue
            seen.add(primary)
            if primary in available_codes:
                return primary
        return 'en'

    @staticmethod
    def _is_valid_language_code(code):
        if not code:
            return False
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-@")
        return all(char in allowed for char in code)

    def _find_available_language_codes(self, directory, extension):
        if not Path(directory).is_dir():
            return set()
        codes = set()
        suffix = f".{extension.lower()}"
        for entry in os.scandir(directory):
            if not entry.is_file():
                continue
            name = entry.name
            if not name.lower().endswith(suffix):
                continue
            code = os.path.splitext(name)[0]
            if self._is_valid_language_code(code):
                codes.add(code)
        return codes

    def get_user_language_zip_codes(self):
        """Return language codes from user zip packages."""

        user_i18n_dir = self.get_user_i18n_dir()
        if not Path(user_i18n_dir).is_dir():
            return []

        codes = []
        for entry in os.scandir(user_i18n_dir):
            if not entry.is_file() or not entry.name.lower().endswith('.zip'):
                continue
            code = os.path.splitext(entry.name)[0]
            if not self._is_valid_language_code(code):
                continue
            codes.append(code)
        return sorted(set(codes))

    def get_complete_user_language_codes(self):
        """Return language codes that have both user .qm and .mo files."""

        user_i18n_dir = self.get_user_i18n_dir()
        qm_codes = self._find_available_language_codes(user_i18n_dir, 'qm')
        mo_codes = self._find_available_language_codes(user_i18n_dir, 'mo')
        zip_codes = set(self.get_user_language_zip_codes())
        return sorted((qm_codes & mo_codes) | zip_codes)

    def sync_current_language_zip(self, lang_code:str):
        """Extract one current-language zip package when it is new or files are missing."""

        zip_path = self.get_user_language_zip_path(lang_code)
        if not Path(zip_path).exists():
            return False
        required_names = (f'{lang_code}.qm', f'{lang_code}.mo')
        optional_name = f'{lang_code}.txt'

        user_i18n_dir = self.get_user_i18n_dir()
        Path(user_i18n_dir).mkdir(exist_ok=True)
        zip_mtime = os.path.getmtime(zip_path)
        target_paths = {
            'qm': str(Path(user_i18n_dir) / f'{lang_code}.qm'),
            'mo': str(Path(user_i18n_dir) / f'{lang_code}.mo')
        }
        needs_update = False
        for extension, target_path in target_paths.items():
            if not Path(target_path).exists() or os.path.getmtime(target_path) < zip_mtime:
                needs_update = True
                break
        if not needs_update:
            return False

        with zipfile.ZipFile(zip_path, 'r') as zip_file:
            for required_name in required_names:
                try:
                    zip_file.getinfo(required_name)
                except KeyError as err:
                    raise FileNotFoundError(
                        f'Language package "{Path(zip_path).name}" must contain '
                        f'"{required_names[0]}" and "{required_names[1]}" in the zip root.'
                    ) from err
            for extension, target_path in target_paths.items():
                lang_data = zip_file.read(f'{lang_code}.{extension}')
                with open(target_path, 'wb') as file_:
                    file_.write(lang_data)
            try:
                lang_data = zip_file.read(optional_name)
                txt_path = Path(user_i18n_dir) / f'{lang_code}.txt'
                with open(txt_path, 'wb') as file_:
                    file_.write(lang_data)
            except KeyError:
                pass
        return True

    def get_language_file_path(self, lang_code, extension):
        """Return the newest translation file for one language and extension."""

        candidates = []
        for directory in (self.get_builtin_i18n_dir(), self.get_user_i18n_dir()):
            candidate = Path(directory) / f"{lang_code}.{extension}"
            if Path(candidate).exists():
                candidates.append(str(candidate))
        if not candidates:
            return None
        return max(candidates, key=os.path.getmtime)

    def language_has_runtime_files(self, lang_code):
        """Check if a language can be loaded with both gettext and Qt translations."""

        return (self.get_language_file_path(lang_code, 'qm') is not None and
                self.get_language_file_path(lang_code, 'mo') is not None)

    def create_connection(self, project_path: str):
        """ Create connection to recent project.
        Args:
            project_path: str
        """

        self.project_path = project_path
        self.project_name = Path(project_path).name
        self.conn = sqlite3.connect(Path(project_path) / 'data.qda')

    def get_project_memo(self) -> str:
        # Might be called from a different thread (ai asynch operations), so have to create a new database connection
        conn = sqlite3.connect(Path(self.project_path) / 'data.qda')
        cur = conn.cursor()
        cur.execute("select memo from project")
        memo = cur.fetchone()[0]
        return memo

    def get_category_names(self):
        """
        Returns:
            List of dictionaries of catid, name memo, date, supercatid, owner
        """
        cur = self.conn.cursor()
        cur.execute("select name, ifnull(memo,''), owner, date, catid, supercatid from code_cat order by lower(name)")
        result = cur.fetchall()
        res = []
        keys = 'name', 'memo', 'owner', 'date', 'catid', 'supercatid'
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def get_code_names(self, cids: list[int] | None = None):
        """
        Args:
            cids : List of cids as Integers, or None for all
        Returns:
            List of dictionaries of cid, name memo, date, catid, color, owner
        """

        cur = self.conn.cursor()
        if not cids:
            cur.execute(
                "select name, ifnull(memo,''), owner, date, cid, catid, color, supercid from code_name order by lower(name)")
        if cids:
            cids_str = ",".join(map(str, cids))
            sql = "select name, ifnull(memo,''), owner, date, cid, catid, color, supercid from code_name where "
            sql += f"cid in ({cids_str}) order by lower(name)"
            cur.execute(sql)
        result = cur.fetchall()
        res = []
        keys = 'name', 'memo', 'owner', 'date', 'cid', 'catid', 'color', 'supercid'
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def get_filenames(self, ids: list[int] | None = None):
        """ Get all filenames.
        Args:
            ids: List of ids or none

        Returns:
            List of dictionaries of id, name memo, mediapath, date
        """

        if ids is None:
            ids = []
        sql = "select id, name, ifnull(memo,''), date from source "
        if ids:
            ids_str = ",".join(map(str, ids))
            sql += f" where id in ({ids_str}) "
        sql += "order by lower(name)"
        cur = self.conn.cursor()
        cur.execute(sql)
        result = cur.fetchall()
        res = []
        keys = 'id', 'name', 'memo', 'date'
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def get_casenames(self):
        """ Get all case names. As id, name, memo.
        Returns:
            List of dictionaries of name memo, id, date
        """

        cur = self.conn.cursor()
        cur.execute("select caseid, name, ifnull(memo,''), date from cases order by lower(name)")
        result = cur.fetchall()
        res = []
        keys = 'id', 'name', 'memo', 'date'
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def get_text_filenames(self, ids: list[int] | None = None):
        """ Get filenames, id, memo and mediapath of text files.
        Args:
            ids: list of Integer ids for a restricted list of files.
        Returns:
            List of dictionaries of id, name memo, mediapath, date, risid
        """

        if ids is None:
            ids = []
        sql = "select id, name, ifnull(memo,''), mediapath, date, risid from source where \
        (mediapath is Null or mediapath like '/docs/%' or mediapath like 'docs:%') "
        if ids:
            ids_str = ",".join(map(str, ids))
            sql += f" and id in ({ids_str}) "
        sql += "order by lower(name)"
        cur = self.conn.cursor()
        cur.execute(sql)
        result = cur.fetchall()
        res = []
        keys = 'id', 'name', 'memo', 'mediapath', 'date', 'risid'
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def get_text_fulltext(self, id_, start_pos=None, length=None) -> str:
        """Extracts text from the database in the document with the given id_.
        Args:
            id_ (int): document id
            start_pos (int): position of the first character, 0 if None
            length (int): number of characters to retrieve, all if None
        Returns:
            str: text
        """
        cur = self.conn.cursor()
        sql = f"SELECT fulltext FROM source WHERE id={id_}"
        cur.execute(sql)
        res = cur.fetchone()
        if res is None:
            return ''
        else:
            if start_pos is None:
                start_pos = 0
            if length is None:
                length = len(res[0])
            return res[0][start_pos:start_pos + length]

    def get_line_numbers(self, full_text: str, quote_start: int, quote_end: int):
        """Determines line numbers of a quote

        Args:
            full_text (str): doc fulltext
            quote_start (int): character position where the quote starts
            quote_end (int): end position

        Returns:
            int, int: line numbers of start and end position of quote
        """
        lines = full_text.splitlines()
        cumulative_length = 0
        start_line_number = 0
        end_line_number = 0

        # Iterate through each line and find the line numbers
        for i, line in enumerate(lines):
            cumulative_length += len(line) + 1  # +1 for the newline character
            # Determine if the start position falls within this line
            if start_line_number == 0 and cumulative_length > quote_start:
                start_line_number = i + 1  # Line numbers are usually 1-indexed
            # Determine if the end position falls within this line
            if end_line_number == 0 and cumulative_length > quote_end:
                end_line_number = i + 1  # Line numbers are usually 1-indexed
                break  # We can break early since both start and end line numbers are found

        return start_line_number, end_line_number

    def get_pdf_filenames(self, ids: list[int] | None = None):
        """ Get id, filenames, memo and mediapath of pdf text files.
        Args:
            ids: list of Integer ids for a restricted list of files, or None.
        Returns:
            List of dictionaries of id, name memo, mediapath, date, risid
        """

        if ids is None:
            ids = []
        sql = "select id, name, ifnull(memo,''), mediapath, date, risid from source " \
              "where mediapath is not Null and(mediapath " \
              "like '/docs/%' or mediapath like 'docs:%') and (mediapath like '%.pdf' or mediapath like '%.PDF')"
        if ids:
            ids_str = ",".join(map(str, ids))
            sql += f" and id in ({ids_str})"
        sql += "order by lower(name)"
        cur = self.conn.cursor()
        cur.execute(sql)
        result = cur.fetchall()
        res = []
        keys = 'id', 'name', 'memo', 'mediapath', 'date', 'risid'
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def get_image_filenames(self, ids: list[int] | None = None):
        """ Get filenames of image files only.
        Args:
            ids: list of Integer ids for a restricted list of files, or None.
        Returns:
            List of dictionaries of id, name, memo, mediapath, date, risid
        """

        if ids is None:
            ids = []
        sql = "select id, name, ifnull(memo,''), mediapath, date, risid from source where " \
              "mediapath like '/images/%' or mediapath like 'images:%'"
        if ids:
            ids_str = ",".join(map(str, ids))
            sql += f" and id in ({ids_str})"
        sql += " order by lower(name)"
        cur = self.conn.cursor()
        cur.execute(sql)
        result = cur.fetchall()
        res = []
        keys = 'id', 'name', 'memo', 'mediapath', 'date', 'risid'
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def get_image_and_pdf_filenames(self, ids: list[int] | None = None):
        """ Get filenames of image and pdf files.
        Args:
            ids: list of Integer ids for a restricted list of files, or None.
        Returns:
            List of dictionaries of id, name, memo, mediapath, date, risid
        """

        if ids is None:
            ids = []

        sql = "select id, name, ifnull(memo,''),mediapath, date, risid from source where "
        sql += "(substr(mediapath,1,7) in ('/images', 'images:')) or "
        sql += "(lower(substr(mediapath, -4)) = '.pdf') "

        if ids:
            ids_str = ",".join(map(str, ids))
            sql += f" and id in ({ids_str})"
        sql += " order by lower(name)"
        cur = self.conn.cursor()
        cur.execute(sql)
        result = cur.fetchall()
        res = []
        keys = 'id', 'name', 'memo', 'mediapath', 'date', 'risid'
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def get_av_filenames(self, ids: list[int] | None = None):
        """ Get filenames of audio video files only.
        Args:
            ids: list of Integer ids for a restricted list of files.
        Returns:
            List of dictionaries of id, name, memo, mediapath, date, risid
        """

        if ids is None:
            ids = []
        sql = "select id, name, ifnull(memo,''), mediapath, date, risid from source where "
        sql += "(mediapath like '/audio/%' or mediapath like 'audio:%' or " \
               "mediapath like '/video/%' or mediapath like 'video:%') "
        if ids:
            ids_str = ",".join(map(str, ids))
            sql += f" and id in ({ids_str})"
        sql += " order by lower(name)"
        cur = self.conn.cursor()
        cur.execute(sql)
        result = cur.fetchall()
        res = []
        keys = 'id', 'name', 'memo', 'mediapath', 'date', 'risid'
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def get_annotations(self):
        """ Get annotations for text files for all visible coders.
        Returns:
            List of dictionaries of anid, fid, memo, date, pos0, pos1, owner
        """

        cur = self.conn.cursor()
        cur.execute("select anid, fid, pos0, pos1, memo, owner, date from annotation_visible")
        result = cur.fetchall()
        res = []
        keys = 'anid', 'fid', 'pos0', 'pos1', 'memo', 'owner', 'date'
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def get_codes_categories(self):
        """ Gets all the codes, categories.
        Called from code_text, code_av, code_image, reports, report_relations.
        Returns:
            List of dictionaries of Codes cid, name, memo, date, catid, color, owner
            List of dictionaries of Categories catid, name, memo, date, supercatid, owner
        """

        cur = self.conn.cursor()
        categories = []
        cur.execute("select name, catid, owner, date, ifnull(memo,''), supercatid from code_cat order by lower(name)")
        result = cur.fetchall()
        keys = 'name', 'catid', 'owner', 'date', 'memo', 'supercatid'
        for row in result:
            categories.append(dict(zip(keys, row)))
        codes = []
        cur = self.conn.cursor()
        cur.execute(
            "select name, ifnull(memo,''), owner, date, cid, catid, color, supercid from code_name order by lower(name)")
        result = cur.fetchall()
        keys = 'name', 'memo', 'owner', 'date', 'cid', 'catid', 'color', 'supercid'
        for row in result:
            codes.append(dict(zip(keys, row)))
        return codes, categories

    def check_bad_file_links(self, id_: int | None = None):
        """ Check all linked files are present.
        Will not state a bad link to an internally created text file.
        Called from MainWindow.open_project, Manage_files, view_av.
        Args:
            id_ : Integer or none for a specific file
         Returns:
             dictionary of id,name, mediapath for bad links
         """
        cur = self.conn.cursor()
        sql = "select id, name, mediapath from source where \
                substr(mediapath,1,6) = 'audio:' \
                or substr(mediapath,1,5) = 'docs:' \
                or substr(mediapath,1,7) = 'images:' \
                or substr(mediapath,1,6) = 'video:' order by name"
        if id_ is not None:
            sql = "select id, name, mediapath from source where id=?"
            cur.execute(sql, [id_])
        else:
            cur.execute(sql)
        result = cur.fetchall()
        bad_links = []
        for r in result:
            if r[2] is None:  # Internally created text file
                continue
            if r[2][0:5] == "docs:" and not Path(r[2][5:]).exists():
                bad_links.append({'name': r[1], 'mediapath': r[2], 'id': r[0]})
            if r[2][0:7] == "images:" and not Path(r[2][7:]).exists():
                bad_links.append({'name': r[1], 'mediapath': r[2], 'id': r[0]})
            if r[2][0:6] == "video:" and not Path(r[2][6:]).exists():
                bad_links.append({'name': r[1], 'mediapath': r[2], 'id': r[0]})
            if r[2][0:6] == "audio:" and not Path(r[2][6:]).exists():
                bad_links.append({'name': r[1], 'mediapath': r[2], 'id': r[0]})
        return bad_links

    def write_config_ini(self, settings, ai_models):
        """ Stores settings for fonts, current coder, directory, and window sizes in .qualcoder folder
        Called by qualcoder.App.load_settings, qualcoder.MainWindow.open_project, settings.DialogSettings
        """

        config = configparser.ConfigParser()
        config['DEFAULT'] = settings
        # add AI models
        if len(ai_models) == 0:
            ai_models = get_default_ai_models()
        for model in ai_models:
            model_section = 'ai_model_' + model['name']
            config[model_section] = {}
            config[model_section]['desc'] = model['desc']
            config[model_section]['access_info_url'] = model['access_info_url']
            config[model_section]['large_model'] = model['large_model']
            config[model_section]['large_model_context_window'] = model['large_model_context_window']
            config[model_section]['fast_model'] = model['fast_model']
            config[model_section]['fast_model_context_window'] = model['fast_model_context_window']
            config[model_section]['reasoning_effort'] = model['reasoning_effort']
            config[model_section]['api_base'] = model['api_base']
            config[model_section]['api_key'] = model['api_key']

        with open(self.configpath, 'w', encoding='utf-8') as configfile:
            config.write(configfile)

    def _load_config_ini(self):
        """ load config settings, and convert some to Integer or Boolean. """

        config = configparser.ConfigParser()
        try:
            config.read(self.configpath, 'utf-8')
            default = config['DEFAULT']
            result = dict(default)
        except UnicodeDecodeError as err:
            logger.warning(f"_load_config_init, character decoding error: {err}")
            print(f"Could not load config.ini\n{err}")
            msg = _("Cannot load config.ini.\nCharacter decoding error.\nUsing QualCoder default settings.")
            print(msg)
            Message(self, _("Cannot load config.ini file"), msg).exec()
            return self.default_settings, get_default_ai_models()

        if 'fontsize' in default:
            result['fontsize'] = default.getint('fontsize')
        if 'docfontsize' in default:
            result['docfontsize'] = default.getint('docfontsize')
        if 'treefontsize' in default:
            result['treefontsize'] = default.getint('treefontsize')
        if 'backup_num' in default:
            result['backup_num'] = default.getint('backup_num')
        if 'ai_permissions' in default:
            result['ai_permissions'] = default.getint('ai_permissions')
        if 'showids' in default:
            if default['showids'] == "False":
                result['showids'] = False
            else:
                result['showids'] = True
        if 'report_text_context_characters' in default:
            result['report_text_context_characters'] = default.getint('report_text_context_characters')

        # load AI model list
        ai_models = []
        for section in config.sections():
            if section.startswith('ai_model_'):
                model = {
                    'name': section[9:],
                    'desc': config[section].get('desc', ''),
                    'access_info_url': config[section].get('access_info_url', ''),
                    'large_model': config[section].get('large_model', ''),
                    'large_model_context_window': config[section].get('large_model_context_window', '32768'),
                    'fast_model': config[section].get('fast_model', ''),
                    'fast_model_context_window': config[section].get('fast_model_context_window', '32768'),
                    'reasoning_effort': config[section].get('reasoning_effort', ''),
                    'api_base': config[section].get('api_base', ''),
                    'api_key': config[section].get('api_key', '')
                }
                ai_models.append(model)
        if len(ai_models) == 0:  # no models loaded, create default
            ai_models = get_default_ai_models()
        else:
            try:
                current_ai_model_index = int(result.get('ai_model_index', -1))
            except ValueError:
                current_ai_model_index = 0
            ai_models, result['ai_model_index'], self.pending_ai_model_upgrade_offer = update_ai_models(
                ai_models, current_ai_model_index, result
            )
        return result, ai_models

    def check_and_add_additional_settings(self, settings_data, ai_models):
        """ Newer features include width and height settings for many dialogs and main window.
        timestamp format.
        dialog_crossovers IS dialog relations
        :param settings_data:  dictionary of most or all settings
        :param ai_models:
        :return: dictionary of all settings
        """

        dict_len = len(settings_data)
        settings_updated = False
        keys = ['mainwindow_geometry',
                'dialogcasefilemanager_w', 'dialogcasefilemanager_h',
                'dialogcodetext_splitter0', 'dialogcodetext_splitter1',
                'dialogcodetext_splitter_v0', 'dialogcodetext_splitter_v1',
                'dialogcodetext_coding_margin_width',
                'codetext_show_margin_stripes',
                'codetext_highlight_style',
                'dialogcodepdf_coding_margin_width',
                'dialogcodepdf_page_view',
                'dialogcodeimage_splitter0', 'dialogcodeimage_splitter1',
                'dialogcodeimage_splitter_h0', 'dialogcodeimage_splitter_h1',
                'dialogreportcodes_splitter0', 'dialogreportcodes_splitter1',
                'dialogreportcodes_splitter_v0', 'dialogreportcodes_splitter_v1',
                'dialogreportcodes_splitter_v2',
                'dialogjournals_splitter0', 'dialogjournals_splitter1',
                'dialogsql_splitter_h0', 'dialogsql_splitter_h1',
                'dialogsql_splitter_v0', 'dialogsql_splitter_v1',
                'dialogcasefilemanager_splitter0', 'dialogcasefilemanager_splitter1',
                'timestampformat', 'speakernameformat',
                'video_w', 'video_h',
                'codeav_abs_pos_x', 'codeav_abs_pos_y',
                'viewav_abs_pos_x', 'viewav_abs_pos_y',
                'viewav_video_pos_x', 'viewav_video_pos_y',
                'codeav_video_pos_x', 'codeav_video_pos_y',
                'dialogcodeav_splitter_0', 'dialogcodeav_splitter_1',
                'dialogcodeav_splitter_h0', 'dialogcodeav_splitter_h1',
                'dialogcodecrossovers_w', 'dialogcodecrossovers_h',
                'dialogcodecrossovers_splitter0', 'dialogcodecrossovers_splitter1',
                'dialogmanagelinks_w', 'dialogmanagelinks_h',
                'ai_search_tree_widths',
                'dialogcodetext_tree_widths', 'dialogcodepdf_tree_widths',
                'dialogcodeimage_tree_widths', 'dialogcodeav_tree_widths',
                'dialogreport_code_summary_tree_widths', 'dialogreportcodes_tree_widths',
                'dialogreportcodesbysegments_tree_widths', 'dialogreportcomparecoderfile_tree_widths',
                'dialogreportexactmatches_tree_widths', 'dialogreportrelations_tree_widths',
                'dialogreportcodefrequencies_tree_widths', 'dialogreportcodercomparisons_tree_widths',
                'dialogcodecolorscheme_tree_widths',
                'docfontsize', 'showids',
                'dialogreport_file_summary_splitter0', 'dialogreport_file_summary_splitter0',
                'dialogreport_code_summary_splitter0', 'dialogreport_code_summary_splitter0',
                'stylesheet', 'backup_num',
                'report_text_context_characters', 'report_text_context_style',
                'ai_enable', 'ai_first_startup', 'ai_model_index', 'ai_chat_sidebar',
                'ai_permissions', 'ai_extended_logging', 'ai_model_upgrade_offers_seen',
                'ai_chat_sidebar_width', 'ai_chat_splitter_output_bottom'
                ]
        for key in keys:
            if key not in settings_data:
                settings_data[key] = 0
                settings_updated = True
                if key == "mainwindow_geometry":
                    settings_data[key] = ""
                if key == "timestampformat":
                    settings_data[key] = "[hh.mm.ss]"
                if key == "speakernameformat":
                    settings_data[key] = "[]"
                if key == "backup_num":
                    settings_data[key] = 5
                if key == 'showids':
                    settings_data[key] = False
                if key == 'codetext_show_margin_stripes':
                    settings_data[key] = True
                if key == 'codetext_highlight_style':
                    settings_data[key] = 'marker'
                if key.endswith('_tree_widths'):
                    settings_data[key] = ""
                if key == 'report_text_context_style':
                    settings_data[key] = "Bold"
                if key == 'report_text_context_characters':
                    settings_data[key] = 150
                if key == 'ai_enable':
                    settings_data[key] = 'False'
                if key == 'ai_first_startup':
                    settings_data[key] = 'True'
                if key == 'ai_model_index':
                    settings_data[key] = '0'
                if key == 'ai_permissions':
                    settings_data[key] = 1
                if key == 'ai_extended_logging':
                    settings_data[key] = 'False'
                if key == 'ai_model_upgrade_offers_seen':
                    settings_data[key] = ''
                if key == 'ai_chat_sidebar':
                    settings_data[key] = 'False'
                if key == 'ai_chat_sidebar_width':
                    settings_data[key] = 320
                if key == 'ai_chat_splitter_output_bottom':
                    settings_data[key] = 80
                if key == 'dialogcodetext_coding_margin_width':
                    settings_data[key] = 100
                if key == 'dialogcodepdf_coding_margin_width':
                    settings_data[key] = 120
                if key == 'dialogcodepdf_page_view':
                    settings_data[key] = 0

        ai_permissions = settings_data.get('ai_permissions', 1)
        if ai_permissions not in (0, 1, 2):
            settings_data['ai_permissions'] = 1
            settings_updated = True

        # Check AI models
        if len(ai_models) == 0:  # No models loaded, create default
            ai_models = get_default_ai_models()

        # Write out new ini file, if needed
        if settings_updated or len(settings_data) > dict_len:
            self.write_config_ini(settings_data, ai_models)
        return settings_data, ai_models

    def merge_settings_with_default_stylesheet(self, settings):
        """ Stylesheet is coded to avoid potential data file import errors with pyinstaller.
        Various options for colour schemes:
        original, dark, blue, green, orange, purple, yellow, rainbow, native

        Orange #f89407

        Wild: QWidget {background: qlineargradient( x1:0 y1:0, x2:1 y2:0, stop:0 cyan, stop:1 blue);}
        color: qlineargradient(spread:pad, x1:0 y1:0, x2:1 y2:0, stop:0 rgba(0, 0, 0, 255),
        stop:1 rgba(255, 255, 255, 255));
        """

        style_dark = "* {font-size: 12px; background-color: #2a2a2a; color:#eeeeee;}\n\
        QWidget:focus {border: 2px solid #f89407;}\n\
        QDialog {border: 1px solid #707070;}\n\
        QFileDialog {font-size: 12px}\n\
        QFileDialog QListView {font-size: 12px;}\n\
        QFileDialog QAbstractItemView {font-size: 12px;}\n\
        QCheckBox {border: None}\n\
        QCheckBox::indicator {border: 2px solid #808080; background-color: #2a2a2a;}\n\
        QCheckBox::indicator::checked {border: 2px solid #808080; background-color: orange;}\n\
        QComboBox {border: 1px solid #707070;}\n\
        QComboBox:hover {border: 2px solid #ffaa00;}\n\
        QGroupBox {border: None;}\n\
        QGroupBox:focus {border: 3px solid #ffaa00;}\n\
        QHeaderView::section {background-color: #505050; color: #ffce42;}\n\
        QLabel {border: none;}\n\
        QLabel#label_search_regex {background-color:#858585;}\n\
        QLabel#label_search_case_sensitive {background-color:#858585;}\n\
        QLabel#label_search_all_files {background-color:#858585;}\n\
        QLabel#label_font_size {background-color:#858585;}\n\
        QLabel#label_search_all_journals {background-color:#858585;}\n\
        QLabel#label_exports {background-color:#858585;}\n\
        QLabel#label_time_3 {background-color:#858585;}\n\
        QLabel#label_volume {background-color:#858585;}\n\
        QLabel#ai_output {background-color: #2a2a2a;}\n\
        QLabel:disabled {color: #707070;}\n\
        QLineEdit {border: 1px solid #858585;}\n\
        QListWidget::item:selected {border-left: 3px solid red; color: #eeeeee;}\n\
        QMenuBar::item:selected {background-color: #3498db; }\n\
        QMenu {border: 1px solid #858585;}\n\
        QMenu::item:selected {background-color: #3498db;}\n\
        QMenu::item:disabled {color: #707070;}\n\
        QPushButton {background-color: #858585;}\n\
        QPushButton:hover {border: 2px solid #ffaa00;}\n\
        QRadioButton::indicator {border: 2px solid #858585; background-color: None;}\n\
        QRadioButton::indicator::checked {border: 2px solid #858585; background-color: orange;}\n\
        QSlider::handle:horizontal {background-color: #f89407;}\n\
        QSplitter::handle {background-color: #909090;}\n\
        QSplitter::handle:horizontal {width: 2px;}\n\
        QSplitter::handle:vertical {height: 2px;}\n\
        QSplitterHandle:hover {}\n\
        QSplitter::handle:horizontal:hover {background-color: red;}\n\
        QSplitter::handle:vertical:hover {background-color: red;}\n\
        QSplitter::handle:pressed {background-color: red;}\n\
        QTabBar {border: 2px solid #858585;}\n\
        QTabBar::tab {border: 1px solid #858585; padding-left: 6px; padding-right: 6px;}\n\
        QTabBar::tab:selected {border: 2px solid #858585; background-color: #707070; margin-left: 3px;}\n\
        QTabBar::tab:!selected {border: 2px solid #858585; background-color: #2a2a2a; margin-left: 3px;}\n\
        QTabWidget::pane {border: 1px solid #858585;}\n\
        QTableWidget {border: 1px solid #ffaa00; gridline-color: #707070;}\n\
        QTableWidget:focus {border: 3px solid #ffaa00;}\n\
        QTextBrowser::document::link {color:red;}\n\
        QTextEdit {border: 1px solid #ffaa00; selection-color: #000000; selection-background-color:#ffffff;}\n\
        QTextEdit:focus {border: 2px solid #ffaa00;}\n\
        QToolTip {background-color: #2a2a2a; color:#eeeeee; border: 1px solid #f89407; }\n\
        QTreeWidget {font-size: 12px;}\n\
        QTreeView {background-color: #484848}\n\
        QTreeView::branch:selected {border-left: 2px solid red; color: #eeeeee;}"
        style_dark = style_dark.replace("* {font-size: 12", f"* {{font-size: {settings.get('fontsize')}")
        style_dark = style_dark.replace("QFileDialog {font-size: 12",
                                        f"QFileDialog {{font-size: {settings.get('fontsize')}")
        style_dark = style_dark.replace("QFileDialog QListView {font-size: 12",
                                        f"QFileDialog QListView {{font-size: {settings.get('fontsize')}")
        style_dark = style_dark.replace("QFileDialog QAbstractItemView {font-size: 12",
                                        f"QFileDialog QAbstractItemView {{font-size: {settings.get('fontsize')}")
        style_dark = style_dark.replace("QTreeWidget {font-size: 12",
                                        f"QTreeWidget {{font-size: {settings.get('treefontsize')}")
        style = "* {font-size: 12px; color: #000000;}\n\
        QWidget {background-color: #efefef; color: #000000; border: none;}\n\
        QWidget:focus {border: 1px solid #f89407;}\n\
        QMainWindow {background-color: #efefef}\n\
        QDialog {border: 1px solid #808080; background-color: #efefef;}\n\
        QFileDialog {font-size: 12px;}\n\
        QFileDialog QListView {font-size: 12px;}\n\
        QFileDialog QAbstractItemView {font-size: 12px;}\n\
        QComboBox {border: 1px solid #707070; background-color: #fafafa;}\n\
        QComboBox:hover,QPushButton:hover {border: 2px solid #f89407;}\n\
        QGroupBox {border-right: 1px solid #707070; border-bottom: 1px solid #707070; background-color: #efefef}\n\
        QGroupBox:focus {border: 3px solid #f89407;}\n\
        QPushButton {border-style: outset; border-width: 2px; border-radius: 2px; border-color: beige; padding: 2px;}\n\
        QPushButton:pressed {border-style: inset; background-color: white;}\n\
        QGraphicsView {border: 1px solid #808080}\n\
        QHeaderView::section {background-color: #f9f9f9}\n\
        QLineEdit {border: 1px solid #707070; background-color: #fafafa;}\n\
        QListWidget::item:selected {border-left: 2px solid red; color: #000000;}\n\
        QMenu {background-color: #efefef; border: 1px solid #808080;}\n\
        QMenu::item:selected {background-color: #fafafa;}\n\
        QMenu::item:disabled {background-color: #efefef; color: #707070;}\n\
        QRadioButton{background-color: None;}\n\
        QRadioButton::indicator {border: 2px solid #858585; background-color: None;}\n\
        QRadioButton::indicator::checked {border: 2px solid #858585; background-color: efefef;}\n\
        QSpinBox {border: 1px solid #808080;}\n\
        QSplitter::handle {background-color: #808080;}\n\
        QSplitter::handle:horizontal {width: 2px;}\n\
        QSplitter::handle:vertical {height: 2px;}\n\
        QSplitterHandle:hover {}\n\
        QSplitter::handle:horizontal:hover {background-color: red;}\n\
        QSplitter::handle:vertical:hover {background-color: red;}\n\
        QSplitter::handle:pressed {background-color: red;}\n\
        QTableWidget {border: 1px solid #f89407; gridline-color: #707070}\n\
        QTableWidget:focus {border: 3px solid #f89407;}\n\
        QTabBar {border: 2px solid #808080;}\n\
        QTabBar::tab {background-color: #f9f9f9; border-top: #f9f9f9 4px solid; padding-left: 6px; padding-right: 6px;}\n\
        QTabBar::tab:selected {background-color: #f9f9f9; border-top: 3px solid #f89407; border-bottom: 3px solid #f89407;}\n\
        QTabWidget {background-color: #ffffff; border: none}\n\
        QTextEdit {background-color: #fcfcfc; selection-color: #ffffff; selection-background-color:#000000;}\n\
        QTextEdit:focus {border: 2px solid #f89407;}\n\
        QPlainTextEdit {background-color: #fcfcfc; selection-color: #ffffff; selection-background-color:#000000;}\n\
        QPlainTextEdit:focus {border: 2px solid #f89407;}\n\
        QToolTip {background-color: #fffacd; color:#000000; border: 1px solid #f89407; }\n\
        QTreeWidget {font-size: 12px;}\n\
        QTreeView::branch:selected {border-left: 2px solid red; color: #000000;}"
        style = style.replace("* {font-size: 12", f"* {{font-size: {settings.get('fontsize')}")
        style = style.replace("QFileDialog {font-size: 12",
                              f"QFileDialog {{font-size: {settings.get('fontsize')}")
        style = style.replace("QFileDialog QListView {font-size: 12",
                              f"QFileDialog QListView {{font-size: {settings.get('fontsize')}")
        style = style.replace("QFileDialog QAbstractItemView {font-size: 12",
                              f"QFileDialog QAbstractItemView {{font-size: {settings.get('fontsize')}")
        style = style.replace("QTreeWidget {font-size: 12",
                              f"QTreeWidget {{font-size: {settings.get('treefontsize')}")
        # Keep the active application palette and only override link colors.
        palette = QtWidgets.QApplication.instance().palette()
        palette.setColor(QtGui.QPalette.ColorRole.Link, QtGui.QColor(self.highlight_color()))
        palette.setColor(QtGui.QPalette.ColorRole.LinkVisited, QtGui.QColor(self.highlight_color()))
        if self.settings['stylesheet'] == "native":
            def blend_colors(first: QtGui.QColor, second: QtGui.QColor, first_ratio: float) -> QtGui.QColor:
                second_ratio = 1.0 - first_ratio
                return QtGui.QColor(
                    round(first.red() * first_ratio + second.red() * second_ratio),
                    round(first.green() * first_ratio + second.green() * second_ratio),
                    round(first.blue() * first_ratio + second.blue() * second_ratio)
                )

            active_highlight = palette.color(QtGui.QPalette.ColorGroup.Active, QtGui.QPalette.ColorRole.Highlight)
            active_highlighted_text = palette.color(
                QtGui.QPalette.ColorGroup.Active, QtGui.QPalette.ColorRole.HighlightedText)
            inactive_base = palette.color(QtGui.QPalette.ColorGroup.Inactive, QtGui.QPalette.ColorRole.Base)
            inactive_highlight = blend_colors(active_highlight, inactive_base, 0.55)
            palette.setColor(QtGui.QPalette.ColorGroup.Inactive, QtGui.QPalette.ColorRole.Highlight,
                             inactive_highlight)
            palette.setColor(QtGui.QPalette.ColorGroup.Inactive, QtGui.QPalette.ColorRole.HighlightedText,
                             active_highlighted_text)
            if platform.system() == "Darwin":
                native_dark = False
                try:
                    native_dark = QtGui.QGuiApplication.styleHints().colorScheme() == QtCore.Qt.ColorScheme.Dark
                except AttributeError:
                    native_dark = palette.color(QtGui.QPalette.ColorRole.Window).lightness() < 128
                tooltip_background = QtGui.QColor("#2b2b2b" if native_dark else "#f7f7f7")
                tooltip_text = QtGui.QColor("#ffffff" if native_dark else "#000000")
                tooltip_base_role = getattr(
                    QtGui.QPalette.ColorRole, "ToolTipBase", QtGui.QPalette.ColorRole.Base)
                tooltip_text_role = getattr(
                    QtGui.QPalette.ColorRole, "ToolTipText", QtGui.QPalette.ColorRole.Text)
                for color_group in (
                        QtGui.QPalette.ColorGroup.Active,
                        QtGui.QPalette.ColorGroup.Inactive,
                        QtGui.QPalette.ColorGroup.Disabled,
                ):
                    palette.setColor(color_group, tooltip_base_role, tooltip_background)
                    palette.setColor(color_group, tooltip_text_role, tooltip_text)
                QtWidgets.QToolTip.setPalette(palette)
        QtWidgets.QApplication.instance().setPalette(palette)
        if self.settings['stylesheet'] == 'dark':
            return style_dark
        style_rainbow = style_dark
        if self.settings['stylesheet'] == 'original':
            # Force dark button foregrounds so qtawesome icons remain readable on the light button background.
            style = style.replace("QPushButton {border-style: outset; ",
                                  "QPushButton {border-style: outset; background-color: #dddddd; color: #202020; ")
            style += "\nQToolButton {color: #202020;}"
        if self.settings['stylesheet'] == 'rainbow':
            style_rainbow += "\nQDialog {background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0.2 black, " \
                             "stop:0.27 red, stop:0.31 yellow, stop:0.35 green, stop:0.39 #306eff, stop:0.42 blue, " \
                             "stop:0.45 darkMagenta, stop:0.5 black);}"
            style_rainbow += "\nQFrame#line {background-color: none;}"
            style_rainbow += "\nQFrame#line_2 {background-color: none;}"
            style_rainbow += "\nQFrame#line_3 {background-color: none;}"
            style_rainbow += "\nQFrame#line_4 {background-color: none;}"
            style_rainbow += "\nQSlider {background-color: none;}"
            style_rainbow += "\nQGroupBox {background-color: none;}"
            return style_rainbow
        if self.settings['stylesheet'] == "orange":
            style = style.replace("#efefef", "#ffcba4")
            style = style.replace("#f89407", "#306eff")
        if self.settings['stylesheet'] == "yellow":
            style = style.replace("#efefef", "#f9e79f")
        if self.settings['stylesheet'] == "green":
            style = style.replace("#efefef", "#c8e6c9")
            style = style.replace("#f89407", "#ea202c")
        if self.settings['stylesheet'] == "blue":
            style = style.replace("#efefef", "#cbe9fa")
            style = style.replace("#f89407", "#303f9f")
        if self.settings['stylesheet'] == "purple":
            style = style.replace("#efefef", "#dfe2ff")
            style = style.replace("#f89407", "#ca1b9a")
        if self.settings['stylesheet'] == "native":
            style = "* {font-size: 12px;}"
            style += "\nQGroupBox { border: none; background-color: transparent;}"
            if platform.system() == "Darwin":
                native_dark = False
                try:
                    native_dark = QtGui.QGuiApplication.styleHints().colorScheme() == QtCore.Qt.ColorScheme.Dark
                except AttributeError:
                    palette = QtWidgets.QApplication.instance().palette()
                    native_dark = palette.color(QtGui.QPalette.ColorRole.Window).lightness() < 128
                if native_dark:
                    style += "\nQToolTip {background-color: #2b2b2b; color: #ffffff; border: 1px solid #5f5f5f;}"
                else:
                    style += "\nQToolTip {background-color: #f7f7f7; color: #000000; border: 1px solid #bdbdbd;}"
        ''' # Keep this as a test area for parsable / unparsable style sheet lines
        style_lines = style.split("\n")
        for i, sl in enumerate(style_lines):
            print(i + 1, sl)
        style_lines = style_lines[0:15]  # Test bed for parsing
        style = "\n".join(style_lines)
        print("\nSTYLE\n", style)'''
        return style

    def highlight_color(self):
        """ Get the default highlight color, depending on the current style
        """
        if self.settings['stylesheet'] == 'dark':
            return '#f89407'
        if self.settings['stylesheet'] == 'rainbow':
            return '#f89407'
        if self.settings['stylesheet'] == "orange":
            return "#306eff"
        if self.settings['stylesheet'] == "yellow":
            return "#306eff"
        if self.settings['stylesheet'] == "green":
            return "#ea202c"
        if self.settings['stylesheet'] == "blue":
            return "#303f9f"
        if self.settings['stylesheet'] == "purple":
            return "#ca1b9a"
        if self.settings['stylesheet'] == "native":
            palette = QtWidgets.QApplication.instance().palette()
            color_role = getattr(
                QtGui.QPalette.ColorRole,
                "Accent",
                QtGui.QPalette.ColorRole.Highlight,
            )
            return palette.color(color_role).name(QtGui.QColor.NameFormat.HexRgb)
        return '#f89407'  # Default

    def qtawesome_icon_color(self):
        """Get the default qtawesome icon color for the current QualCoder style."""
        stylesheet = self.settings['stylesheet']
        if stylesheet in ('dark', 'rainbow'):
            return QtGui.QColor('#eeeeee')
        if stylesheet == 'native':
            palette = QtWidgets.QApplication.instance().palette()
            return palette.color(QtGui.QPalette.ColorRole.Text)
        return QtGui.QColor('#202020')

    def qtawesome_icon_color_disabled(self):
        """Get the default disabled qtawesome icon color for the current QualCoder style."""
        stylesheet = self.settings['stylesheet']
        if stylesheet in ('dark', 'rainbow'):
            return QtGui.QColor('#707070')
        if stylesheet == 'native':
            palette = QtWidgets.QApplication.instance().palette()
            return palette.color(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.Text)
        return QtGui.QColor('#7a7a7a')

    def load_settings(self):
        result, ai_models = self._load_config_ini()
        # Check keys
        if (not len(result) or 'codername' not in result.keys() or 'stylesheet' not in result.keys() or
                'speakernameformat' not in result.keys()):
            # create default:
            ai_models = get_default_ai_models()
            self.write_config_ini(self.default_settings, ai_models)
            logger.info('Initialized config.ini')
            result, ai_models = self._load_config_ini()
        # codername is also legacy, v2.8 plus keeps current coder name in database project table
        if result['codername'] == "":
            result['codername'] = "default"
        result, ai_models = self.check_and_add_additional_settings(result, ai_models)
        # TODO TEMPORARY delete, legacy
        if result['speakernameformat'] == 0:
            result['speakernameformat'] = "[]"
        if result['stylesheet'] == 0:
            result['stylesheet'] = "native"
        return result, ai_models

    @property
    def default_settings(self):
        """ Standard Settings for config.ini file. """

        return {
            'backup_num': 5,
            'codername': 'default',
            'font': 'Noto Sans',
            'fontsize': 12,
            'docfontsize': 12,
            'treefontsize': 12,
            'directory': get_default_user_directory(),
            'showids': False,
            'language': self.get_initial_language_code(),
            'backup_on_open': True,
            'backup_av_files': True,
            'timestampformat': "[hh.mm.ss]",
            'speakernameformat': "[]",
            'mainwindow_geometry': '',
            'dialogcodetext_splitter0': 1,
            'dialogcodetext_splitter1': 1,
            'dialogcodetext_splitter_v0': 1,
            'dialogcodetext_splitter_v1': 1,
            'dialogcodetext_coding_margin_width': 100,
            'codetext_show_margin_stripes': True,
            'codetext_highlight_style': 'marker',
            'dialogcodepdf_coding_margin_width': 120,
            'dialogcodepdf_page_view': 0,
            'dialogcodeimage_splitter0': 1,
            'dialogcodeimage_splitter1': 1,
            'dialogcodeimage_splitter_h0': 1,
            'dialogcodeimage_splitter_h1': 1,
            'dialogreportcodes_splitter0': 1,
            'dialogreportcodes_splitter1': 1,
            'dialogreportcodes_splitter_v0': 30,
            'dialogreportcodes_splitter_v1': 30,
            'dialogreportcodes_splitter_v2': 30,
            'dialogjournals_splitter0': 1,
            'dialogjournals_splitter1': 1,
            'dialogsql_splitter_h0': 1,
            'dialogsql_splitter_h1': 1,
            'dialogsql_splitter_v0': 1,
            'dialogsql_splitter_v1': 1,
            'dialogcasefilemanager_w': 0,
            'dialogcasefilemanager_h': 0,
            'dialogcasefilemanager_splitter0': 1,
            'dialogcasefilemanager_splitter1': 1,
            'video_w': 0,
            'video_h': 0,
            'viewav_video_pos_x': 0,
            'viewav_video_pos_y': 0,
            'codeav_video_pos_x': 0,
            'codeav_video_pos_y': 0,
            'codeav_abs_pos_x': 0,
            'codeav_abs_pos_y': 0,
            'dialogcodeav_splitter_0': 0,
            'dialogcodeav_splitter_1': 0,
            'dialogcodeav_splitter_h0': 0,
            'dialogcodeav_splitter_h1': 0,
            'viewav_abs_pos_x': 0,
            'viewav_abs_pos_y': 0,
            'dialogcodecrossovers_w': 0,
            'dialogcodecrossovers_h': 0,
            'dialogcodecrossovers_splitter0': 0,
            'dialogcodecrossovers_splitter1': 0,
            'dialogmanagelinks_w': 0,
            'dialogmanagelinks_h': 0,
            'bookmark_file_id': 0,
            'bookmark_pos': 0,
            'dialogreport_file_summary_splitter0': 100,
            'dialogreport_file_summary_splitter1': 100,
            'dialogreport_code_summary_splitter0': 100,
            'dialogreport_code_summary_splitter1': 100,
            'ai_search_tree_widths': '',
            'dialogcodetext_tree_widths': '',
            'dialogcodepdf_tree_widths': '',
            'dialogcodeimage_tree_widths': '',
            'dialogcodeav_tree_widths': '',
            'dialogreport_code_summary_tree_widths': '',
            'dialogreportcodes_tree_widths': '',
            'dialogreportcodesbysegments_tree_widths': '',
            'dialogreportcomparecoderfile_tree_widths': '',
            'dialogreportexactmatches_tree_widths': '',
            'dialogreportrelations_tree_widths': '',
            'dialogreportcodefrequencies_tree_widths': '',
            'dialogreportcodercomparisons_tree_widths': '',
            'dialogcodecolorscheme_tree_widths': '',
            'stylesheet': 'native',
            'report_text_context_chars': 150,
            'report_text_context-style': 'Bold',
            'ai_enable': 'False',
            'ai_first_startup': 'True',
            'ai_model_index': -1,
            'ai_permissions': 1,
            'ai_extended_logging': 'False',
            'ai_model_upgrade_offers_seen': '',
            'ai_chat_sidebar': 'False',
            'ai_chat_sidebar_width': 320,
            'ai_chat_splitter_output_bottom': 80
        }

    def get_file_texts(self, file_ids: list[int] | None = None):
        """ Get the texts of all text files as a list of dictionaries.
        Called by DialogCodeText.search_for_text
        Args:
            fileids - a list of fileids or None
        Returns:
            List of Dictionaries of file details
        """

        cur = self.conn.cursor()
        if file_ids is not None:
            cur.execute(
                "select name, id, fulltext, ifnull(memo, ''), owner, date, mediapath from "
                "source where id in (?) and fulltext is not null order by name", file_ids)
        else:
            cur.execute(
                "select name, id, fulltext, ifnull(memo,''), owner, date, mediapath "
                "from source where fulltext is not null order by name")
        keys = 'name', 'id', 'fulltext', 'memo', 'owner', 'date', 'mediapath'
        result = []
        for row in cur.fetchall():
            result.append(dict(zip(keys, row)))
        return result

    def get_pdf_file_texts(self, file_ids=None):
        """ Get the texts of all text files as a list of dictionaries.
        Called by DialogCodePdf.search_for_text
        Args:
            fileids - a list of fileids or None
        Returns:
            List of Dictionaries of pdf file details
        """

        cur = self.conn.cursor()
        if file_ids is not None:
            cur.execute(
                "select name, id, fulltext, ifnull(memo, ''), owner, date, mediapath from "
                "source where id in (?) and fulltext is not null and mediapath is not Null and "
                "(mediapath like '/docs/%' or mediapath like 'docs:%') and "
                "(mediapath like '%.pdf' or mediapath like '%.PDF') order by name", file_ids)
        else:
            cur.execute(
                "select name, id, fulltext, ifnull(memo,''), owner, date, mediapath "
                "from source where fulltext is not null and mediapath is not Null and "
                "(mediapath like '/docs/%' or mediapath like 'docs:%') and "
                "(mediapath like '%.pdf' or mediapath like '%.PDF') order by name")
        keys = 'name', 'id', 'fulltext', 'memo', 'owner', 'date', 'mediapath'
        result = []
        for row in cur.fetchall():
            result.append(dict(zip(keys, row)))
        return result

    def get_journal_texts(self, journal_ids: list[int] | None = None):
        """ Get the texts of all journals as a list of dictionaries.
        Called by DialogJournals.search_for_text
        Args:
            jids - a list of journal jids or None
        Returns:
            List of Dictionaries of journal data
        """

        cur = self.conn.cursor()
        if journal_ids is not None:
            cur.execute(
                "select name, jid, jentry, owner, date from journal where jid in (?)",
                journal_ids
            )
        else:
            cur.execute("select name, jid, jentry, owner, date from journal order by date desc")
        keys = 'name', 'jid', 'jentry', 'owner', 'date'
        result = []
        for row in cur.fetchall():
            result.append(dict(zip(keys, row)))
        return result

    def get_last_project_coder(self) -> str:
        """Returns the last coder name stored in the project table or
        an empty string if nothing is found there (old dab version 1-4)"""
        if self.conn is None:
            return ""
        cur = self.conn.cursor()
        try:
            cur.execute("SELECT codername FROM project")
            res = cur.fetchone()
            if res is not None and res[0] is not None:
                return res[0]
        except sqlite3.OperationalError:  # db vers. 1-4 did not have codername in project table
            return ""

    def update_coder_names(self):
        """
        Collects names from the 'owner' field in all tables, and updates the
        table 'coder_names' accordingly. The table will be created if not present.

        The function also creates views that filter out invisible coders for the
        following tables:
        code_image --> code_image_visible
        code_text  --> code_text_visible
        code_av    --> code_av_visible
        annotation --> annotation_visible
        """
        if self.conn is None:
            return
        system_coder_names = [speaker_coder_name]  # in the future, we could add '🤖 AI' to the list, and more...

        cur = self.conn.cursor()
        initial_changes = self.conn.total_changes

        try:
            # create table 'coder_names' if not already present
            sql = """
                CREATE TABLE IF NOT EXISTS coder_names (
                    name TEXT UNIQUE NOT NULL,
                    visibility INTEGER NOT NULL DEFAULT 1 CHECK (visibility IN (0, 1))
                );
            """
            cur.execute(sql)

            # Collect used coder names from all tables and add them to 'coder_names'.
            # Visibility will default to 1 (True)
            sql = """
                INSERT OR IGNORE INTO coder_names (name)
                    SELECT owner FROM code_image WHERE owner IS NOT NULL
                    UNION SELECT owner FROM code_text WHERE owner IS NOT NULL
                    UNION SELECT owner FROM code_av WHERE owner IS NOT NULL
                    UNION SELECT owner FROM code_name WHERE owner IS NOT NULL
                    UNION SELECT owner FROM code_cat WHERE owner IS NOT NULL
                    UNION SELECT owner FROM cases WHERE owner IS NOT NULL
                    UNION SELECT owner FROM case_text WHERE owner IS NOT NULL
                    UNION SELECT owner FROM attribute WHERE owner IS NOT NULL
                    UNION SELECT owner FROM attribute_type WHERE owner IS NOT NULL
                    UNION SELECT owner FROM source WHERE owner IS NOT NULL
                    UNION SELECT owner FROM annotation WHERE owner IS NOT NULL
                    UNION SELECT owner FROM journal WHERE owner IS NOT NULL
                    UNION SELECT owner FROM manage_files_display WHERE owner IS NOT NULL
                    UNION SELECT owner FROM files_filter WHERE owner IS NOT NULL;
            """
            cur.execute(sql)

            # Ensure current coder is added and visible
            sql = """
                INSERT INTO coder_names (name, visibility) 
                VALUES (?, 1) 
                ON CONFLICT(name) 
                DO UPDATE SET visibility = 1
                WHERE coder_names.visibility <> 1
            """
            cur.execute(sql, (self.settings['codername'],))

            # Ensure last coder from project is added
            last_project_coder = self.get_last_project_coder()
            if last_project_coder != "":
                cur.execute("INSERT OR IGNORE INTO coder_names (name) VALUES (?)", (last_project_coder,))

                # Ensure system coder names are added
            for name in system_coder_names:
                cur.execute("INSERT OR IGNORE INTO coder_names (name) VALUES (?)", (name,))

            # create views
            cur.execute("""
                CREATE VIEW IF NOT EXISTS code_image_visible AS
                SELECT t.*
                FROM code_image t
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM coder_names c
                    WHERE c.name = t.owner
                        AND c.visibility = 0
                );
            """)
            cur.execute("""
                CREATE VIEW IF NOT EXISTS code_text_visible AS
                SELECT t.*
                FROM code_text t
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM coder_names c
                    WHERE c.name = t.owner
                        AND c.visibility = 0
                );
            """)
            cur.execute("""
                CREATE VIEW IF NOT EXISTS code_av_visible AS
                SELECT t.*
                FROM code_av t
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM coder_names c
                    WHERE c.name = t.owner
                        AND c.visibility = 0
                );
            """)
            cur.execute("""
                CREATE VIEW IF NOT EXISTS annotation_visible AS
                SELECT t.*
                FROM annotation t
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM coder_names c
                    WHERE c.name = t.owner
                        AND c.visibility = 0
                );
            """)
            if self.conn.total_changes != initial_changes:
                self.delete_backup = False
            self.conn.commit()
        except Exception as err:
            logger.error(err)
            print(err)
            self.conn.rollback()
            raise

    def get_coder_names_in_project(self, only_visible=False):
        """ Get all coder names from all tables and from the config.ini file
        Design flaw is that current codername is not stored in a specific table in Database Versions 1 to 4.
        Coder name is stored in Database version 5.
        Current coder name is in position 0.

        Returns:
            List of String coder names
        """

        if self.conn is None:
            return [self.settings['codername']]

        coder_names = []
        try:
            self.update_coder_names()
            cur = self.conn.cursor()
            if only_visible:
                sql = "select name from coder_names where visibility = 1"
            else:
                sql = "select name from coder_names"
            cur.execute(sql)
            res = cur.fetchall()
            for r in res:
                coder_names.append(r[0])
        except sqlite3.OperationalError:
            pass
        return coder_names

    def save_backup(self, suffix: str = ""):
        """ Save a date and hours stamped backup.
        Do not back up if the name already exists.
        A backup can be generated in the subsequent hour.
        Args:
            suffix : String to add to end of backup name. Use this for special ops
        Returns:
            msg: String: for textedit display
            backup: String: full project path for backup
        """

        nowdate = datetime.datetime.now().astimezone().strftime("%Y%m%d_%H")  # -%S")
        backup = f"{self.project_path[0:-4]}_BKUP_{nowdate}{suffix}.qda"
        # USED IN 3.8 - 3.8.2 CAUSED CONFUSION backup = os.path.join(self.settings['directory'], f"{self.project_name[:-4]}_BKUP_{nowdate}{suffix}.qda")
        # Do not try and create another backup with same date and hour, unless suffix present
        result = Path(backup).exists()
        if result and suffix == "":
            return f"Backup exists already with this name: {backup}", backup
        msg = ""
        backup_ignore_patterns = (
            'search.sqlite',
            'search.sqlite-*',
            '*.sqlite-shm',
            '*.sqlite-wal',
            '*.sqlite-journal',
        )
        if self.settings['backup_av_files'] == 'True':
            try:
                shutil.copytree(self.project_path, backup, ignore=shutil.ignore_patterns(*backup_ignore_patterns))
            except FileExistsError as err:
                msg = _("There is already a backup with this name")
                print(f"{err}\nmsg")
                logger.warning(_(msg) + f"\n{err}")
            except shutil.Error as err:
                msg = _("Project backup could not be fully created.") + " " + str(err)
                logger.warning(msg)
        else:
            try:
                shutil.copytree(
                    self.project_path,
                    backup,
                    ignore=shutil.ignore_patterns(
                        *backup_ignore_patterns,
                        '*.mp3', '*.wav', '*.mp4', '*.mov', '*.ogg', '*.wmv',
                        '*.MP3', '*.WAV', '*.MP4', '*.MOV', '*.OGG', '*.WMV'
                    )
                )
                msg = _("WARNING: audio and video files NOT backed up. See settings.") + "\n"
            except FileExistsError as err:
                msg = _("There is already a backup with this name")
                logger.warning(_(msg) + f"\n{err}")
            except shutil.Error as err:
                msg = _("Project backup could not be fully created.") + " " + str(err)
                logger.warning(msg)
        if not Path(backup).exists():
            return msg, backup
        msg += _("Project backup created: ") + backup
        # Delete backup path - delete the backup if no changes occurred in the project during the session
        self.delete_backup_path_name = backup
        return msg, backup

    def help_wiki(self, page_path: str):
        """ Open website doc help page in https://qualcoder.org.
        Assumes English pages are present as a default.
        Args:
            page_path : String : specific page
        """

        lang = self.settings['language']
        try:
            urllib.request.urlopen(f"https://qualcoder.org/doc/{lang}/{page_path}")
        except urllib_err.HTTPError as err:
            logger.warning(f"App.help_wiki:\nhttps://qualcoder.org/doc/{lang}/{page_path}\n{err}")
            if err.code == 404:
                lang = "en"
        webbrowser.open(f"https://qualcoder.org/doc/{lang}/{page_path}")
