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

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
"""

import multiprocessing
import base64
import configparser
import datetime
import gettext
import json  # To get the latest GitHub release information
import logging
from logging.handlers import RotatingFileHandler
import os
import platform
import shutil
import sys
import sqlite3
import urllib.request
import webbrowser
from copy import copy
import time
import getpass

from PyQt6 import QtCore, QtGui, QtWidgets
import qtawesome as qta

from qualcoder.error_dlg import UncaughtHook
from qualcoder.attributes import DialogManageAttributes
from qualcoder.cases import DialogCases
from qualcoder.codebook import Codebook
from qualcoder.code_color_scheme import DialogCodeColorScheme
from qualcoder.code_organiser import CodeOrganiser
from qualcoder.code_text import DialogCodeText
from qualcoder.code_pdf import DialogCodePdf
from qualcoder.GUI.base64_droidsansmono_helper import DroidSansMono
from qualcoder.GUI.ui_main import Ui_MainWindow
from qualcoder.helpers import Message, ImportPlainTextCodes
from qualcoder.import_survey import DialogImportSurvey
from qualcoder.import_twitter_data import DialogImportTwitterData
from qualcoder.information import DialogInformation, menu_shortcuts_display, coding_shortcuts_display
from qualcoder.locale.base64_lang_helper import *
from qualcoder.journals import DialogJournals
from qualcoder.manage_files import DialogManageFiles
from qualcoder.manage_links import DialogManageLinks
from qualcoder.manage_references import DialogReferenceManager
from qualcoder.memo import DialogMemo
from qualcoder.refi import RefiExport, RefiImport
from qualcoder.reports import DialogReportCoderComparisons, DialogReportCodeFrequencies
from qualcoder.report_code_summary import DialogReportCodeSummary
from qualcoder.report_compare_coder_file import DialogCompareCoderByFile
from qualcoder.report_comparison_table import DialogReportComparisonTable
from qualcoder.report_codes import DialogReportCodes
from qualcoder.report_codes_by_segments import DialogCodesBySegments
from qualcoder.report_cooccurrence import DialogReportCooccurrence
from qualcoder.report_file_summary import DialogReportFileSummary
from qualcoder.report_exact_matches import DialogReportExactTextMatches
from qualcoder.report_relations import DialogReportRelations
from qualcoder.report_sql import DialogSQL
from qualcoder.ai_chat import DialogAIChat
from qualcoder.rqda import RqdaImport
from qualcoder.settings import DialogSettings
from qualcoder.special_functions import DialogSpecialFunctions
# from qualcoder.text_mining import DialogTextMining
from qualcoder.view_av import DialogCodeAV
from qualcoder.view_charts import ViewCharts
from qualcoder.view_graph import ViewGraph
from qualcoder.view_image import DialogCodeImage
from qualcoder.ai_prompts import DialogAiEditPrompts

# Check if VLC installed, for warning message for code_av
vlc = None
try:
    import vlc
except Exception as e:
    print(e)

qualcoder_version = "QualCoder 3.7"
path = os.path.abspath(os.path.dirname(__file__))
home = os.path.expanduser('~')
if not os.path.exists(home + '/.qualcoder'):
    try:
        os.mkdir(home + '/.qualcoder')
    except Exception as e:
        print("Cannot add .qualcoder folder to home directory\n" + str(e))
        raise
logfile = home + '/.qualcoder/QualCoder.log'
# Hack for Windows 10 PermissionError that stops the rotating file handler, will produce massive files.
try:
    log_file = open(logfile, "r")
    data = log_file.read()
    log_file.close()
    if len(data) > 12000:
        os.remove(logfile)
        log_file = open(logfile, "w")
        log_file.write(data[10000:])
        log_file.close()
except Exception as e:
    print(e)
logging.basicConfig(format='%(asctime)s %(levelname)s %(name)s.%(funcName)s %(message)s',
                    datefmt='%Y/%m/%d %H:%M:%S', filename=logfile)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
# The rotating file handler does not work on Windows
handler = RotatingFileHandler(logfile, maxBytes=4000, backupCount=2)
logger.addHandler(handler)

lock_timeout = 30.0  # in seconds. If a project lockfile is older (= has received no heartbeat for 30 seconds),
# it is assumed that the host process has died and the project is opened anyways
lock_heartbeat_interval = 5  # in seconds.


class ProjectLockHeartbeatWorker(QtCore.QObject):
    """
    This worker thread is invoked on opening a project and will write a regular heartbeat (timestamp) 
    to the lock file to signify that the project is still in use and the host process did not crash.    
    """
    finished = QtCore.pyqtSignal()  # Signal for indicating completion
    io_error = QtCore.pyqtSignal()  # Singal indicating an error acessing the lock file to write the heartbeat  

    def __init__(self, app, lock_file_path):
        super().__init__()
        self.app = app
        self.lock_file_path = lock_file_path
        self.is_running = True
        self.lost_connection = False

    def write_heartbeat(self):
        """Write heartbeat to the lock file every 10 seconds."""
        last_heartbeat = time.time()
        while self.is_running:
            if time.time() - last_heartbeat >= lock_heartbeat_interval:
                last_heartbeat = time.time()
                try:
                    with open(self.lock_file_path, 'w', encoding='utf-8') as lock_file:
                        lock_file.write(f"{getpass.getuser()}\n{str(time.time())}")
                    self.lost_connection = False
                except Exception as e_:  # TODO Needs specific exception, printing to find out what is needed
                    print(e_)
                    if not self.lost_connection:
                        self.io_error.emit()
                    self.lost_connection = True
            time.sleep(0.1)

    def stop(self):
        """Stop the heartbeat process."""
        self.is_running = False
        self.finished.emit()


class App(object):
    """ General methods for loading settings and recent project stored in .qualcoder folder.
    Savable settings does not contain project name, project path or db connection.
    """

    version = qualcoder_version
    conn = None
    project_path = ""
    project_name = ""
    # Can delete the most current back up if the project has not been altered
    delete_backup_path_name = ""
    delete_backup = True
    # Used as a default export location, which may be different from the working directory
    last_export_directory = ""
    ai = None
    ai_models = []
    # This is the sentence transformer embedding function. It is stored here so it must not be reloaded every time a project is opened.
    ai_embedding_function = None
    
    def __init__(self):
        self.conn = None
        self.project_path = ""
        self.project_name = ""
        self.last_export_directory = ""
        self.delete_backup = True
        self.delete_backup_path_name = ""
        self.confighome = os.path.expanduser('~/.qualcoder')
        self.configpath = os.path.join(self.confighome, 'config.ini')
        self.persist_path = os.path.join(self.confighome, 'recent_projects.txt')
        self.settings, self.ai_models = self.load_settings()
        self.last_export_directory = copy(self.settings['directory'])
        self.version = qualcoder_version

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
            if os.path.exists(proj_path):
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
                    f.write(os.linesep)
        return result

    def append_recent_project(self, new_path):
        """ Add project path as first entry to .qualcoder/recent_projects.txt
        param:
            new_path String filepath to project
        """

        if new_path == "":
            return
        nowdate = datetime.datetime.now().astimezone().strftime("%Y-%m-%d_%H:%M:%S")
        # Result is a list of strings containing yyyy-mm-dd:hh:mm:ss|projectpath
        result = self.read_previous_project_paths()
        dated_path = nowdate + "|" + new_path
        if not result:
            with open(self.persist_path, 'w', encoding='utf-8') as f:
                f.write(dated_path)
                f.write(os.linesep)
            return
        # Compare first persisted project path to the currently open project path
        if "|" in result[0]:  # safety check
            if result[0].split("|")[1] != new_path:
                result.append(dated_path)
                result.sort()
                if len(result) > 8:
                    result = result[0:8]
        with open(self.persist_path, 'w', encoding='utf-8') as f:
            for i, line in enumerate(result):
                f.write(line)
                f.write(os.linesep)

    def get_most_recent_projectpath(self):
        """ Get most recent project path from .qualcoder/recent_projects.txt """

        result = self.read_previous_project_paths()
        if result:
            return result[0]

    def create_connection(self, project_path):
        """ Create connection to recent project. """

        self.project_path = project_path
        self.project_name = project_path.split('/')[-1]
        self.conn = sqlite3.connect(os.path.join(project_path, 'data.qda'))
        
    def get_project_memo(self) -> str:
        # Might be called from a different thread (ai asynch operations), so have to create a new database connection
        conn = sqlite3.connect(os.path.join(self.project_path, 'data.qda'))
        cur = conn.cursor()
        cur.execute("select memo from project")
        memo = cur.fetchone()[0]
        return memo

    def get_category_names(self):
        cur = self.conn.cursor()
        cur.execute("select name, ifnull(memo,''), owner, date, catid, supercatid from code_cat order by lower(name)")
        result = cur.fetchall()
        res = []
        keys = 'name', 'memo', 'owner', 'date', 'catid', 'supercatid'
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def get_code_names(self):
        cur = self.conn.cursor()
        cur.execute("select name, ifnull(memo,''), owner, date, cid, catid, color from code_name order by lower(name)")
        result = cur.fetchall()
        res = []
        keys = 'name', 'memo', 'owner', 'date', 'cid', 'catid', 'color'
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def get_filenames(self):
        """ Get all filenames. As id, name, memo """
        cur = self.conn.cursor()
        cur.execute("select id, name, ifnull(memo,'') from source order by lower(name)")
        result = cur.fetchall()
        res = []
        for row in result:
            res.append({'id': row[0], 'name': row[1], 'memo': row[2]})
        return res

    def get_casenames(self):
        """ Get all case names. As id, name, memo. """
        cur = self.conn.cursor()
        cur.execute("select caseid, name, ifnull(memo,'') from cases order by lower(name)")
        result = cur.fetchall()
        res = []
        for row in result:
            res.append({'id': row[0], 'name': row[1], 'memo': row[2]})
        return res

    def get_text_filenames(self, ids=None):
        """ Get filenames, id, memo and mediapath of text files.
        param:
            ids: list of Integer ids for a restricted list of files. """

        if ids is None:
            ids = []
        sql = "select id, name, ifnull(memo,''), mediapath from source where (mediapath is Null or mediapath " \
              "like '/docs/%' or mediapath like 'docs:%') "
        if ids:
            str_ids = list(map(str, ids))
            sql += " and id in (" + ",".join(str_ids) + ")"
        sql += "order by lower(name)"
        cur = self.conn.cursor()
        cur.execute(sql)
        result = cur.fetchall()
        res = []
        keys = 'id', 'name', 'memo', 'mediapath'
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

    def get_line_numbers(self, full_text, quote_start, quote_end):
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

    def get_pdf_filenames(self, ids=None):
        """ Get id, filenames, memo and mediapath of pdf text files.
        param:
            ids: list of Integer ids for a restricted list of files. """

        if ids is None:
            ids = []
        sql = "select id, name, ifnull(memo,''), mediapath from source where mediapath is not Null and(mediapath " \
              "like '/docs/%' or mediapath like 'docs:%') and (mediapath like '%.pdf' or mediapath like '%.PDF')"
        if ids:
            str_ids = list(map(str, ids))
            sql += " and id in (" + ",".join(str_ids) + ")"
        sql += "order by lower(name)"
        cur = self.conn.cursor()
        cur.execute(sql)
        result = cur.fetchall()
        res = []
        keys = 'id', 'name', 'memo', 'mediapath'
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def get_image_filenames(self, ids=None):
        """ Get filenames of image files only.
        param:
            ids: list of Integer ids for a restricted list of files. """

        if ids is None:
            ids = []
        sql = "select id, name, ifnull(memo,'') from source where mediapath like '/images/%' or mediapath like 'images:%'"
        if ids:
            str_ids = list(map(str, ids))
            sql += " and id in (" + ",".join(str_ids) + ")"
        sql += " order by lower(name)"
        cur = self.conn.cursor()
        cur.execute(sql)
        result = cur.fetchall()
        res = []
        for row in result:
            res.append({'id': row[0], 'name': row[1], 'memo': row[2]})
        return res

    def get_av_filenames(self, ids=None):
        """ Get filenames of audio video files only.
        param:
            ids: list of Integer ids for a restricted list of files. """

        if ids is None:
            ids = []
        sql = "select id, name, ifnull(memo,'') from source where "
        sql += "(mediapath like '/audio/%' or mediapath like 'audio:%' or mediapath like '/video/%' or mediapath like 'video:%') "
        if ids:
            str_ids = list(map(str, ids))
            sql += " and id in (" + ",".join(str_ids) + ")"
        sql += " order by lower(name)"
        cur = self.conn.cursor()
        cur.execute(sql)
        result = cur.fetchall()
        res = []
        for row in result:
            res.append({'id': row[0], 'name': row[1], 'memo': row[2]})
        return res

    def get_annotations(self):
        """ Get annotations for text files. """

        cur = self.conn.cursor()
        cur.execute("select anid, fid, pos0, pos1, memo, owner, date from annotation where owner=?",
                    [self.settings['codername'], ])
        result = cur.fetchall()
        res = []
        keys = 'anid', 'fid', 'pos0', 'pos1', 'memo', 'owner', 'date'
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def get_codes_categories(self):
        """ Gets all the codes, categories.
        Called from code_text, code_av, code_image, reports, report_relations """

        cur = self.conn.cursor()
        categories = []
        cur.execute("select name, catid, owner, date, ifnull(memo,''), supercatid from code_cat order by lower(name)")
        result = cur.fetchall()
        keys = 'name', 'catid', 'owner', 'date', 'memo', 'supercatid'
        for row in result:
            categories.append(dict(zip(keys, row)))
        codes = []
        cur = self.conn.cursor()
        cur.execute("select name, ifnull(memo,''), owner, date, cid, catid, color from code_name order by lower(name)")
        result = cur.fetchall()
        keys = 'name', 'memo', 'owner', 'date', 'cid', 'catid', 'color'
        for row in result:
            codes.append(dict(zip(keys, row)))
        return codes, categories

    def check_bad_file_links(self):
        """ Check all linked files are present.
         Called from MainWindow.open_project, view_av.
         Returns:
             dictionary of id,name, mediapath for bad links
         """

        cur = self.conn.cursor()
        sql = "select id, name, mediapath from source where \
            substr(mediapath,1,6) = 'audio:' \
            or substr(mediapath,1,5) = 'docs:' \
            or substr(mediapath,1,7) = 'images:' \
            or substr(mediapath,1,6) = 'video:' order by name"
        cur.execute(sql)
        result = cur.fetchall()
        bad_links = []
        for r in result:
            if r[2][0:5] == "docs:" and not os.path.exists(r[2][5:]):
                bad_links.append({'name': r[1], 'mediapath': r[2], 'id': r[0]})
            if r[2][0:7] == "images:" and not os.path.exists(r[2][7:]):
                bad_links.append({'name': r[1], 'mediapath': r[2], 'id': r[0]})
            if r[2][0:6] == "video:" and not os.path.exists(r[2][6:]):
                bad_links.append({'name': r[1], 'mediapath': r[2], 'id': r[0]})
            if r[2][0:6] == "audio:" and not os.path.exists(r[2][6:]):
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
            ai_models = self.ai_models_create_defaults()
        for model in ai_models:
            model_section = 'ai_model_' + model['name']
            config[model_section] = {}
            config[model_section]['desc'] = model['desc']
            config[model_section]['access_info_url'] = model['access_info_url']
            config[model_section]['large_model'] = model['large_model']
            config[model_section]['large_model_context_window'] = model['large_model_context_window']
            config[model_section]['fast_model'] = model['fast_model']
            config[model_section]['fast_model_context_window'] = model['fast_model_context_window']
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
            return {}

        if 'fontsize' in default:
            result['fontsize'] = default.getint('fontsize')
        if 'docfontsize' in default:
            result['docfontsize'] = default.getint('docfontsize')
        if 'treefontsize' in default:
            result['treefontsize'] = default.getint('treefontsize')
        if 'backup_num' in default:
            result['backup_num'] = default.getint('backup_num')
        if 'codetext_chunksize' in default:
            result['codetext_chunksize'] = default.getint('codetext_chunksize')
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
                    'desc': config[section]['desc'],
                    'access_info_url': config[section]['access_info_url'],
                    'large_model': config[section]['large_model'],
                    'large_model_context_window': config[section]['large_model_context_window'],
                    'fast_model': config[section]['fast_model'],
                    'fast_model_context_window': config[section]['fast_model_context_window'],
                    'api_base': config[section]['api_base'],
                    'api_key': config[section]['api_key']
                }
                ai_models.append(model)
        if len(ai_models) == 0:  # no models loaded, create default
            ai_models = self.ai_models_create_defaults()
        return result, ai_models

    def ai_models_create_defaults(self):
        """Returns a list of the default AI model parameters
        """       
        models = [
            {
                'name': 'OpenAI_GPT4o',
                'desc': """Current default model from OpenAI, faster and cheaper than GPT4-turbo.  
                You need an API-key from OpenAI and have paid for credits in your account. 
                OpenAI will charge a small amount for every use.""",
                'access_info_url': 'https://platform.openai.com/api-keys',
                'large_model': 'gpt-4o',
                'large_model_context_window': '128000',
                'fast_model': 'gpt-4o-mini',
                'fast_model_context_window': '128000',
                'api_base': '',
                'api_key': ''
            },
            {
                'name': 'GPT-4-turbo',
                'desc': """Classic model from OpenAI, still very capable. 
                You need an API-key from OpenAI and have paid for credits in your account. 
                OpenAI will charge a small amount for every use.""",
                'access_info_url': 'https://platform.openai.com/api-keys',
                'large_model': 'gpt-4-turbo',
                'large_model_context_window': '128000',
                'fast_model': 'gpt-4o-mini',
                'fast_model_context_window': '128000',
                'api_base': '',
                'api_key': ''
            },
            {
                'name': 'Blablador',
                'desc': """A free and open source model, excellent privacy, 
but not as powerful as GPT-4. 
Blablador is free to use and runs on a server of the Helmholtz Society, 
a large non-profit research organization in Germany. To gain 
access and get an API-key, you have to identify yourself once with your 
university, ORCID, GitHub, or Google account.""",
                'access_info_url': 'https://sdlaml.pages.jsc.fz-juelich.de/ai/guides/blablador_api_access/',
                'large_model': 'alias-large',
                'large_model_context_window': '32768',
                'fast_model': 'alias-fast',
                'fast_model_context_window': '32768',
                'api_base': 'https://helmholtz-blablador.fz-juelich.de:8000/v1',
                'api_key': ''
            }
        ]
        return models

    def check_and_add_additional_settings(self, settings_data, ai_models):
        """ Newer features include width and height settings for many dialogs and main window.
        timestamp format.
        dialog_crossovers IS dialog relations
        :param settings_data:  dictionary of most or all settings
        :param ai_models:
        :return: dictionary of all settings
        """

        dict_len = len(settings_data)
        keys = ['mainwindow_geometry',
                'dialogcasefilemanager_w', 'dialogcasefilemanager_h',
                'dialogcodetext_splitter0', 'dialogcodetext_splitter1',
                'dialogcodetext_splitter_v0', 'dialogcodetext_splitter_v1',
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
                'docfontsize', 'showids',
                'dialogreport_file_summary_splitter0', 'dialogreport_file_summary_splitter0',
                'dialogreport_code_summary_splitter0', 'dialogreport_code_summary_splitter0',
                'stylesheet', 'backup_num', 'codetext_chunksize',
                'report_text_context_characters', 'report_text_context_style',
                'ai_enable', 'ai_first_startup', 'ai_model_index'
                ]
        for key in keys:
            if key not in settings_data:
                settings_data[key] = 0
                if key == "mainwindow_geometry":
                    settings_data[key] = ""
                if key == "timestampformat":
                    settings_data[key] = "[hh.mm.ss]"
                if key == "speakernameformat":
                    settings_data[key] = "[]"
                if key == "backup_num":
                    settings_data[key] = 5
                if key == "codetext_chunksize":
                    settings_data[key] = 50000
                if key == 'showids':
                    settings_data[key] = False
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
                    
        # Check AI models
        if len(ai_models) == 0:  # No models loaded, create default
            ai_models = self.ai_models_create_defaults()

        # Write out new ini file, if needed
        if len(settings_data) > dict_len:
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
        QPushButton::icon {color: #FFFFFF;}\n\
        QRadioButton::indicator {border: 1px solid #858585; background-color: #2a2a2a;}\n\
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
        QTextEdit {border: 1px solid #ffaa00; selection-color: #000000; selection-background-color:#ffffff;}\n\
        QTextEdit:focus {border: 2px solid #ffaa00;}\n\
        QToolTip {background-color: #2a2a2a; color:#eeeeee; border: 1px solid #f89407; }\n\
        QTreeWidget {font-size: 12px;}\n\
        QTreeView {background-color: #484848}\n\
        QTreeView::branch:selected {border-left: 2px solid red; color: #eeeeee;}"
        style_dark = style_dark.replace("* {font-size: 12", "* {font-size:" + str(settings.get('fontsize')))
        style_dark = style_dark.replace("QFileDialog {font-size: 12",
                                        "QFileDialog {font-size:" + str(settings.get('fontsize')))
        style_dark = style_dark.replace("QTreeWidget {font-size: 12",
                                        "QTreeWidget {font-size: " + str(settings.get('treefontsize')))
        style = "* {font-size: 12px; color: #000000;}\n\
        QWidget {background-color: #efefef; color: #000000; border: none;}\n\
        QWidget:focus {border: 1px solid #f89407;}\n\
        QDialog {border: 1px solid #808080;}\n\
        QFileDialog {font-size: 12px}\n\
        QComboBox {border: 1px solid #707070; background-color: #fafafa;}\n\
        QComboBox:hover,QPushButton:hover {border: 2px solid #f89407;}\n\
        QGroupBox {border-right: 1px solid #707070; border-bottom: 1px solid #707070;}\n\
        QGroupBox:focus {border: 3px solid #f89407;}\n\
        QPushButton {border-style: outset; border-width: 2px; border-radius: 2px; border-color: beige; padding: 2px;}\n\
        QPushButton:pressed {border-style: inset; background-color: white;}\n\
        QPushButton::icon {color: #000000;)\n\
        QGraphicsView {border: 1px solid #808080}\n\
        QHeaderView::section {background-color: #f9f9f9}\n\
        QLineEdit {border: 1px solid #707070; background-color: #fafafa;}\n\
        QListWidget::item:selected {border-left: 2px solid red; color: #000000;}\n\
        QMenu {border: 1px solid #808080;}\n\
        QMenu::item:selected {background-color: #fafafa;}\n\
        QMenu::item:disabled {color: #707070;}\n\
        QSpinBox {border: 1px solid #808080;}\n\
        QSplitter::handle {background-color: #808080;}\n\
        QSplitter::handle:horizontal {width: 2px;}\n\
        QSplitter::handle:vertical {height: 2px;}\n\
        QSplitterHandle:hover {}\n\
        QSplitter::handle:horizontal:hover {background-color: red;}\n\
        QSplitter::handle:vertical:hover {background-color: red;}\n\
        QSplitter::handle:pressed {background-color: red;}\n\
        QTableWidget {border: 1px solid #f89407; gridline-color: #707070;}\n\
        QTableWidget:focus {border: 3px solid #f89407;}\n\
        QTabBar {border: 2px solid #808080;}\n\
        QTabBar::tab {background-color: #f9f9f9; border-top: #f9f9f9 4px solid; padding-left: 6px; padding-right: 6px;}\n\
        QTabBar::tab:selected {background-color: #f9f9f9; border-top: 3px solid #f89407; border-bottom: 3px solid #f89407;}\n\
        QTabWidget {border: none;}\n\
        QTextEdit {background-color: #fcfcfc; selection-color: #ffffff; selection-background-color:#000000;}\n\
        QTextEdit:focus {border: 2px solid #f89407;}\n\
        QPlainTextEdit {background-color: #fcfcfc; selection-color: #ffffff; selection-background-color:#000000;}\n\
        QPlainTextEdit:focus {border: 2px solid #f89407;}\n\
        QToolTip {background-color: #fffacd; color:#000000; border: 1px solid #f89407; }\n\
        QTreeWidget {font-size: 12px;}\n\
        QTreeView::branch:selected {border-left: 2px solid red; color: #000000;}"
        style = style.replace("* {font-size: 12", "* {font-size:" + str(settings.get('fontsize')))
        style = style.replace("QFileDialog {font-size: 12", "QFileDialog {font-size:" + str(settings.get('fontsize')))
        style = style.replace("QTreeWidget {font-size: 12",
                              "QTreeWidget {font-size: " + str(settings.get('treefontsize')))
        if self.settings['stylesheet'] == 'dark':
            return style_dark
        style_rainbow = style_dark
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
            return palette.color(QtGui.QPalette.ColorRole.Highlight).name(QtGui.QColor.NameFormat.HexRgb)
        return '#f89407'  # Default

    def load_settings(self):
        result, ai_models = self._load_config_ini()
        # Check keys
        if (not len(result) or 'codername' not in result.keys() or 'stylesheet' not in result.keys() or
                'speakernameformat' not in result.keys()):
            # create default:
            ai_models = self.ai_models_create_defaults()
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
            'directory': os.path.expanduser('~'),
            'showids': False,
            'language': 'en',
            'backup_on_open': True,
            'backup_av_files': True,
            'timestampformat': "[hh.mm.ss]",
            'speakernameformat': "[]",
            'mainwindow_geometry': '',
            'dialogcodetext_splitter0': 1,
            'dialogcodetext_splitter1': 1,
            'dialogcodetext_splitter_v0': 1,
            'dialogcodetext_splitter_v1': 1,
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
            'stylesheet': 'native',
            'report_text_context_chars': 150,
            'report_text_context-style': 'Bold',
            'codetext_chunksize': 50000,
            'ai_enable': 'False',
            'ai_first_startup': 'True',
            'ai_model_index': -1
        }

    def get_file_texts(self, file_ids=None):
        """ Get the texts of all text files as a list of dictionaries.
        Called by DialogCodeText.search_for_text
        param:
            fileids - a list of fileids or None
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
        param:
            fileids - a list of fileids or None
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

    def get_journal_texts(self, journal_ids=None):
        """ Get the texts of all journals as a list of dictionaries.
        Called by DialogJournals.search_for_text
        param:
            jids - a list of jids or None
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

    def get_coder_names_in_project(self):
        """ Get all coder names from all tables and from the config.ini file
        Design flaw is that current codername is not stored in a specific table in Database Versions 1 to 4.
        Coder name is stored in Database version 5.
        Current coder name is in position 0.
        """

        # Try except, as there may not be an open project, and might be an older <= v4 database
        try:
            cur = self.conn.cursor()
            cur.execute("select codername from project")
            res = cur.fetchone()
            if res[0] is not None:
                self.settings['codername'] = res[0]
        except sqlite3.OperationalError:
            pass
        # For versions 1 to 4, current coder name stored in the config.ini file, so is added here.
        coder_names = [self.settings['codername']]
        try:
            cur = self.conn.cursor()
            sql = "select owner from code_image union select owner from code_text union select owner from code_av "
            sql += "union select owner from cases union select owner from source union select owner from code_name"
            cur.execute(sql)
            res = cur.fetchall()
            for r in res:
                if r[0] not in coder_names:
                    coder_names.append(r[0])
        except sqlite3.OperationalError:
            pass
        return coder_names
         
    def save_backup(self, suffix=""):
        """ Save a date and hours stamped backup.
        Do not back up if the name already exists.
        A backup can be generated in the subsequent hour.
        params:
            suffix : String to add to end of backup name. Use this for special ops
        """

        nowdate = datetime.datetime.now().astimezone().strftime("%Y%m%d_%H")  # -%S")
        backup = f"{self.project_path[0:-4]}_BKUP_{nowdate}{suffix}.qda"
        # Do not try and create another backup with same date and hour, unless suffix present
        result = os.path.exists(backup)
        if result and suffix == "":
            return f"Backup exists already with this name: {backup}", backup
        msg = ""
        if self.settings['backup_av_files'] == 'True':
            try:
                shutil.copytree(self.project_path, backup, ignore=shutil.ignore_patterns('*.lock'))
            except FileExistsError as err:
                msg = _("There is already a backup with this name")
                print(f"{err}\nmsg")
                logger.warning(_(msg) + f"\n{err}")
        else:
            shutil.copytree(self.project_path, backup,
                            ignore=shutil.ignore_patterns('*.lock', '*.mp3', '*.wav', '*.mp4', '*.mov', '*.ogg',
                                                          '*.wmv', '*.MP3',
                                                          '*.WAV', '*.MP4', '*.MOV', '*.OGG', '*.WMV'))
            # self.ui.textEdit.append(_("WARNING: audio and video files NOT backed up. See settings."))
            msg = _("WARNING: audio and video files NOT backed up. See settings.") + "\n"
        # self.ui.textEdit.append(_("Project backup created: ") + backup)
        msg += _("Project backup created: ") + backup
        # Delete backup path - delete the backup if no changes occurred in the project during the session
        self.delete_backup_path_name = backup
        return msg, backup


class MainWindow(QtWidgets.QMainWindow):
    """ Main GUI window.
    Project data is stored in a directory with .qda suffix
    core data is stored in data.qda sqlite file.
    Journal and coding dialogs can be shown non-modally - multiple dialogs open.
    There is a risk of a clash if two coding windows are open with the same file text or
    two journals open with the same journal entry.

    Note: App.settings does not contain projectName, conn or path (to database)
    app.project_name and app.project_path contain these.
    """

    project = {"databaseversion": "", "date": "", "memo": "", "about": ""}
    recent_projects = []  # a list of recent projects for the qmenu

    def __init__(self, app, force_quit=False):
        """ Set up user interface from ui_main.py file. """
        self.app = app
        self.force_quit = force_quit
        self.journal_display = None

        self.heartbeat_thread = None
        self.heartbeat_worker = None
        self.lock_file_path = ''
        self.ai_chat_window = None
        
        if platform.system() == "Windows" and self.app.settings['stylesheet'] == "native":
            # Make 'Fusion' the standard native style on Windows https://www.qt.io/blog/dark-mode-on-windows-11-with-qt-6.5
            # The default 'Windows' style seems partially broken at the moment, in combination with the native dark mode.
            # On macOS, 'Fusion' is the default style anyways (automatically chosen by Qt).
            QtWidgets.QApplication.instance().setStyle("Fusion")
       
        QtWidgets.QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        # Test of macOS menu bar
        if self.app.settings['stylesheet'] == "native":
            self.ui.menubar.setNativeMenuBar(True)
        else:
            self.ui.menubar.setNativeMenuBar(False)
        self.get_latest_github_release()
        try:
            # Restore main window geometry (size, position, maximized state) from config
            geometry_hex = self.app.settings.get('mainwindow_geometry', '')
            if geometry_hex:
                self.restoreGeometry(QtCore.QByteArray.fromHex(geometry_hex.encode('utf-8')))
        except KeyError:
            pass
        self.hide_menu_options()
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.init_ui()
        self.ui.tabWidget.setCurrentIndex(0)
        self.show()
        QtWidgets.QApplication.processEvents() 
        # Setup AI
        global AiLLM
        from qualcoder.ai_llm import AiLLM  # import after showing the UI because this takes several seconds
        self.app.ai = AiLLM(self.app, self.ui.textEdit)
        # First start? Ask if user wants to enable ai integration or not
        if self.app.settings['ai_first_startup'] == 'True' and self.app.settings['ai_enable'] == 'False':
            msg = _('Welcome\n\n\
The new AI enhanced functions in QualCoder need some additional setup. \
Do you want to enable the AI and start the setup? \
You can also do this later by starting the AI Setup Wizard from the AI menu in the main window. \
Click "Yes" to start now.')
            msg_box = QtWidgets.QMessageBox(self)
            msg_box.setWindowTitle(_('AI Integration'))
            msg_box.setText(msg)
            msg_box.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
            msg_box.addButton(QtWidgets.QMessageBox.StandardButton.Yes)
            msg_box.addButton(QtWidgets.QMessageBox.StandardButton.No)
            msg_box.addButton(QtWidgets.QMessageBox.StandardButton.Help)
            reply = None
            while reply is None or reply == QtWidgets.QMessageBox.StandardButton.Help:
                reply = msg_box.exec()
                if reply == QtWidgets.QMessageBox.StandardButton.Help:
                    webbrowser.open('https://github.com/ccbogel/QualCoder/wiki/2.3.-AI-Setup')                
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                self.ai_setup_wizard()  # (will also init the llm)
        else:
            self.app.ai.init_llm(self)      
        self.app.settings['ai_first_startup'] = 'False'
        self.app.write_config_ini(self.app.settings, self.app.ai_models)
    
    def init_ui(self):
        """ Set up menu triggers """

        # Project menu
        self.ui.actionCreate_New_Project.triggered.connect(self.new_project)
        self.ui.actionCreate_New_Project.setShortcut('Ctrl+N')
        self.ui.actionOpen_Project.triggered.connect(self.open_project)
        self.ui.actionOpen_Project.setShortcut('Ctrl+O')
        self.fill_recent_projects_menu_actions()
        self.ui.actionProject_Memo.triggered.connect(self.project_memo)
        self.ui.actionProject_Memo.setShortcut('Ctrl+M')
        self.ui.actionClose_Project.triggered.connect(self.close_project)
        self.ui.actionClose_Project.setShortcut('Alt+X')
        self.ui.actionSettings.triggered.connect(self.change_settings)
        self.ui.actionSettings.setShortcut('Alt+S')
        self.ui.actionProject_summary.triggered.connect(self.project_summary_report)
        self.ui.actionProject_Exchange_Export.triggered.connect(self.refi_project_export)
        self.ui.actionREFI_Codebook_export.triggered.connect(self.refi_codebook_export)
        self.ui.actionREFI_Codebook_import.triggered.connect(self.refi_codebook_import)
        self.ui.actionREFI_QDA_Project_import.triggered.connect(self.refi_project_import)
        self.ui.actionRQDA_Project_import.triggered.connect(self.rqda_project_import)
        self.ui.actionExport_codebook.triggered.connect(self.codebook)
        self.ui.actionExport_codebook_with_memos.triggered.connect(self.codebook_with_memos)
        self.ui.actionExit.triggered.connect(self.closeEvent)
        self.ui.actionExit.setShortcut('Ctrl+Q')
        self.ui.actionImport_plain_text_codes_list.triggered.connect(self.import_plain_text_codes)
        # Manage menu
        self.ui.actionManage_files.setShortcut('Alt+F')
        self.ui.actionManage_files.triggered.connect(self.manage_files)
        self.ui.actionManage_journals.triggered.connect(self.journals)
        self.ui.actionManage_journals.setShortcut('Alt+J')
        self.ui.actionManage_cases.triggered.connect(self.manage_cases)
        self.ui.actionManage_cases.setShortcut('Alt+C')
        self.ui.actionManage_attributes.triggered.connect(self.manage_attributes)
        self.ui.actionManage_attributes.setShortcut('Alt+A')
        self.ui.actionImport_survey_2.triggered.connect(self.import_survey)
        self.ui.actionImport_survey_2.setShortcut('Ctrl+I')
        self.ui.actionManage_bad_links_to_files.triggered.connect(self.manage_bad_file_links)
        self.ui.actionManage_references.setShortcut('Alt+R')
        self.ui.actionManage_references.triggered.connect(self.manage_references)
        self.ui.actionImport_twitter_data.triggered.connect(self.import_twitter)
        # Coding menu
        self.ui.actionCodes.triggered.connect(self.text_coding)
        self.ui.actionCodes.setShortcut('Alt+T')
        self.ui.actionAI_assisted_coding.triggered.connect(self.ai_go_search)
        self.ui.actionCode_image.triggered.connect(self.image_coding)
        self.ui.actionCode_image.setShortcut('Alt+I')
        self.ui.actionCode_audio_video.triggered.connect(self.av_coding)
        self.ui.actionCode_audio_video.setShortcut('Alt+V')
        self.ui.actionCode_pdf.triggered.connect(self.pdf_coding)
        self.ui.actionColour_scheme.setShortcut('Alt+E')
        self.ui.actionColour_scheme.triggered.connect(self.code_color_scheme)
        self.ui.actionCode_organiser.triggered.connect(self.code_organiser)
        # Reports menu
        self.ui.actionCoding_reports.setShortcut('Alt+K')
        self.ui.actionCoding_reports.triggered.connect(self.report_coding)
        self.ui.actionCoding_comparison.setShortcut('Alt+L')
        self.ui.actionCoding_comparison.triggered.connect(self.report_coding_comparison)
        self.ui.actionCoding_comparison_by_file.setShortcut('Alt+M')
        self.ui.actionCoding_comparison_by_file.triggered.connect(self.report_compare_coders_by_file)
        self.ui.actionCode_comparison_table.triggered.connect(self.report_comparison_table)
        self.ui.actionCode_frequencies.setShortcut('Alt+N')
        self.ui.actionCode_frequencies.triggered.connect(self.report_code_frequencies)
        self.ui.actionFile_summary.setShortcut('Alt+O')
        self.ui.actionFile_summary.triggered.connect(self.report_file_summary)
        self.ui.actionCode_summary.setShortcut('Alt+P')
        self.ui.actionCode_summary.triggered.connect(self.report_code_summary)
        self.ui.actionCode_relations.setShortcut('Alt+Q')
        self.ui.actionCode_relations.triggered.connect(self.report_code_relations)
        self.ui.actionCode_co_occurrence.triggered.connect(self.co_occurence)
        self.ui.actionCode_text_exact_matches.triggered.connect(self.report_exact_text_matches)
        self.ui.actionText_segments_by_codes.triggered.connect(self.text_segments_codes_table)
        self.ui.actionView_Graph.setShortcut('Alt+G')
        self.ui.actionView_Graph.triggered.connect(self.view_graph_original)
        self.ui.actionCharts.setShortcut('Alt+U')
        self.ui.actionCharts.triggered.connect(self.view_charts)
        # TODO self.ui.actionText_mining.triggered.connect(self.text_mining)
        self.ui.actionSQL_statements.setShortcut('Alt+D')
        self.ui.actionSQL_statements.triggered.connect(self.report_sql)
        # AI menu
        self.ui.actionAI_Setup_wizard.triggered.connect(self.ai_setup_wizard)
        self.ui.actionAI_Configuration.triggered.connect(self.ai_settings)
        self.ui.actionAI_Rebuild_internal_memory.triggered.connect(self.ai_rebuild_memory)
        self.ui.actionAI_Edit_Project_Memo.triggered.connect(self.project_memo)
        self.ui.actionAI_Prompts.triggered.connect(self.ai_prompts)
        self.ui.actionAI_Chat.triggered.connect(self.ai_go_chat)
        self.ui.actionAI_Search_and_Coding.triggered.connect(self.ai_go_search)
        # Help menu
        self.ui.actionContents.setShortcut('Alt+H')
        self.ui.actionContents.triggered.connect(self.help)
        self.ui.actionAbout.setShortcut('Alt+Y')
        self.ui.actionAbout.triggered.connect(self.about)
        self.ui.actionSpecial_functions.setShortcut('Alt+Z')
        self.ui.actionSpecial_functions.triggered.connect(self.special_functions)
        self.ui.actionMenu_Key_Shortcuts.triggered.connect(self.display_menu_key_shortcuts)
        # Ensure the action_log always scrolls to the very bottom once new log entries are added:
        self.ui.textEdit.verticalScrollBar().rangeChanged.connect(self.action_log_scroll_bottom)
        self.ui.textEdit.setReadOnly(True)
        self.settings_report()
        
        self.ui.tabWidget.setCurrentIndex(0)
        self.ai_chat()
        # add tab widget icons
        try:
            self.ui.tabWidget.setTabIcon(0, qta.icon('mdi6.cog', color=self.app.highlight_color()))  # Action Log
            self.ui.tabWidget.setTabIcon(1, qta.icon('mdi6.file-outline', color=self.app.highlight_color()))  # Manage
            self.ui.tabWidget.setTabIcon(2, qta.icon('mdi6.tag-text-outline', color=self.app.highlight_color()))  # Coding
            self.ui.tabWidget.setTabIcon(3, qta.icon('mdi6.format-list-group', color=self.app.highlight_color()))  # Reports
            self.ui.tabWidget.setTabIcon(4, qta.icon('mdi6.message-processing-outline', color=self.app.highlight_color()))  # Ai Chat
        except Exception as e:
            logger.log(e)
        
    def fill_recent_projects_menu_actions(self):
        """ Get the recent projects from the .qualcoder txt file.
        Add up to five recent projects to the menu. """

        self.recent_projects = self.app.read_previous_project_paths()
        if len(self.recent_projects) == 0:
            return
        # Removes the qtdesigner default action. Also clears the section when a project is closed
        # so that the options for recent projects can be updated
        self.ui.menuOpen_Recent_Project.clear()
        for i, r in enumerate(self.recent_projects):
            display_name = r
            if len(r.split("|")) == 2:
                display_name = r.split("|")[1]
            if i == 0:
                action0 = QtGui.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action0)
                action0.triggered.connect(self.project0)
            if i == 1:
                action1 = QtGui.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action1)
                action1.triggered.connect(self.project1)
            if i == 2:
                action2 = QtGui.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action2)
                action2.triggered.connect(self.project2)
            if i == 3:
                action3 = QtGui.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action3)
                action3.triggered.connect(self.project3)
            if i == 4:
                action4 = QtGui.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action4)
                action4.triggered.connect(self.project4)
            if i == 5:
                action5 = QtGui.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action5)
                action5.triggered.connect(self.project5)

    def project0(self):
        self.open_project(self.recent_projects[0])

    def project1(self):
        self.open_project(self.recent_projects[1])

    def project2(self):
        self.open_project(self.recent_projects[2])

    def project3(self):
        self.open_project(self.recent_projects[3])

    def project4(self):
        self.open_project(self.recent_projects[4])

    def project5(self):
        self.open_project(self.recent_projects[5])

    def hide_menu_options(self):
        """ No project opened, hide most menu options.
         Enable project import options.
         Called by init and by close_project. """

        # Project menu
        self.ui.actionClose_Project.setEnabled(False)
        self.ui.actionProject_Memo.setEnabled(False)
        self.ui.actionProject_Exchange_Export.setEnabled(False)
        self.ui.actionREFI_Codebook_export.setEnabled(False)
        self.ui.actionREFI_Codebook_import.setEnabled(False)
        self.ui.actionREFI_QDA_Project_import.setEnabled(True)
        self.ui.actionRQDA_Project_import.setEnabled(True)
        self.ui.actionExport_codebook.setEnabled(False)
        self.ui.actionImport_plain_text_codes_list.setEnabled(False)
        # Manage menu
        self.ui.actionManage_files.setEnabled(False)
        self.ui.actionManage_journals.setEnabled(False)
        self.ui.actionManage_cases.setEnabled(False)
        self.ui.actionManage_attributes.setEnabled(False)
        self.ui.actionImport_survey_2.setEnabled(False)
        self.ui.actionManage_bad_links_to_files.setEnabled(False)
        self.ui.actionManage_references.setEnabled(False)
        self.ui.actionImport_twitter_data.setEnabled(False)
        # Coding menu
        self.ui.actionCodes.setEnabled(False)
        self.ui.actionCode_image.setEnabled(False)
        self.ui.actionCode_audio_video.setEnabled(False)
        self.ui.actionCode_pdf.setEnabled(False)
        self.ui.actionColour_scheme.setEnabled(False)
        self.ui.actionCode_organiser.setEnabled(False)
        # Reports menu
        self.ui.actionCoding_reports.setEnabled(False)
        self.ui.actionCoding_comparison.setEnabled(False)
        self.ui.actionCoding_comparison_by_file.setEnabled(False)
        self.ui.actionCode_frequencies.setEnabled(False)
        self.ui.actionCode_relations.setEnabled(False)
        self.ui.actionCode_co_occurrence.setEnabled(False)
        self.ui.actionCode_comparison_table.setEnabled(False)
        self.ui.actionCode_text_exact_matches.setEnabled(False)
        self.ui.actionText_mining.setEnabled(False)
        self.ui.actionSQL_statements.setEnabled(False)
        self.ui.actionFile_summary.setEnabled(False)
        self.ui.actionCode_summary.setEnabled(False)
        self.ui.actionText_segments_by_codes.setEnabled(False)
        self.ui.actionCategories.setEnabled(False)
        self.ui.actionView_Graph.setEnabled(False)
        self.ui.actionCharts.setEnabled(False)
        # Help menu
        self.ui.actionSpecial_functions.setEnabled(False)

    def show_menu_options(self):
        """ Project opened, show most menu options.
         Disable project import options. """

        # Project menu
        self.ui.actionClose_Project.setEnabled(True)
        self.ui.actionProject_Memo.setEnabled(True)
        self.ui.actionProject_Exchange_Export.setEnabled(True)
        self.ui.actionREFI_Codebook_export.setEnabled(True)
        self.ui.actionREFI_Codebook_import.setEnabled(True)
        self.ui.actionREFI_QDA_Project_import.setEnabled(True)
        self.ui.actionRQDA_Project_import.setEnabled(True)
        self.ui.actionExport_codebook.setEnabled(True)
        self.ui.actionImport_plain_text_codes_list.setEnabled(True)
        # Manage menu
        self.ui.actionManage_files.setEnabled(True)
        self.ui.actionManage_journals.setEnabled(True)
        self.ui.actionManage_cases.setEnabled(True)
        self.ui.actionManage_attributes.setEnabled(True)
        self.ui.actionImport_survey_2.setEnabled(True)
        self.ui.actionManage_references.setEnabled(True)
        self.ui.actionImport_twitter_data.setEnabled(True)
        # Coding menu
        self.ui.actionCodes.setEnabled(True)
        self.ui.actionCode_image.setEnabled(True)
        self.ui.actionCode_audio_video.setEnabled(True)
        self.ui.actionCode_pdf.setEnabled(True)
        self.ui.actionColour_scheme.setEnabled(True)
        self.ui.actionCode_organiser.setEnabled(True)
        # Reports menu
        self.ui.actionCoding_reports.setEnabled(True)
        self.ui.actionCoding_comparison.setEnabled(True)
        self.ui.actionCoding_comparison_by_file.setEnabled(True)
        self.ui.actionCode_comparison_table.setEnabled(True)
        self.ui.actionCode_frequencies.setEnabled(True)
        self.ui.actionCode_relations.setEnabled(True)
        self.ui.actionCode_co_occurrence.setEnabled(True)
        self.ui.actionCode_text_exact_matches.setEnabled(True)
        self.ui.actionSQL_statements.setEnabled(True)
        self.ui.actionFile_summary.setEnabled(True)
        self.ui.actionCode_summary.setEnabled(True)
        self.ui.actionText_segments_by_codes.setEnabled(True)
        self.ui.actionCategories.setEnabled(True)
        self.ui.actionView_Graph.setEnabled(True)
        self.ui.actionCharts.setEnabled(True)
        # Help menu
        self.ui.actionSpecial_functions.setEnabled(True)

        # TODO FOR FUTURE EXPANSION text mining
        self.ui.actionText_mining.setEnabled(False)
        self.ui.actionText_mining.setVisible(False)

    def keyPressEvent(self, event):
        """ Used to open top level menus. """
        key = event.key()
        mods = QtWidgets.QApplication.keyboardModifiers()
        if mods & QtCore.Qt.KeyboardModifier.AltModifier and key == QtCore.Qt.Key.Key_1:
            self.ui.menuProject.popup(QtGui.QCursor.pos())
        if mods & QtCore.Qt.KeyboardModifier.AltModifier and key == QtCore.Qt.Key.Key_2:
            self.ui.menuFiles_and_Cases.popup(QtGui.QCursor.pos())
        if mods & QtCore.Qt.KeyboardModifier.AltModifier and key == QtCore.Qt.Key.Key_3:
            self.ui.menuCoding.popup(QtGui.QCursor.pos())
        if mods & QtCore.Qt.KeyboardModifier.AltModifier and key == QtCore.Qt.Key.Key_4:
            self.ui.menuReports.popup(QtGui.QCursor.pos())
        if mods & QtCore.Qt.KeyboardModifier.AltModifier and key == QtCore.Qt.Key.Key_5:
            self.ui.menuHelp.popup(QtGui.QCursor.pos())

    def settings_report(self):
        """ Display general settings and project summary """

        self.ui.textEdit.append("<h1>" + _("Settings") + "</h1>")
        msg = _("Coder") + ": " + self.app.settings['codername'] + "\n"
        msg += _("Font") + ": " + f"{self.app.settings['font']} {self.app.settings['fontsize']}\n"
        msg += _("Tree font size") + f": {self.app.settings['treefontsize']}\n"
        msg += _("Working directory") + f": {self.app.settings['directory']}\n"
        msg += _("Show IDs") + f": {self.app.settings['showids']}\n"
        msg += _("Language") + f": {self.app.settings['language']}\n"
        msg += _("Timestamp format") + f": {self.app.settings['timestampformat']}\n"
        msg += _("Speaker name format") + f": {self.app.settings['speakernameformat']}\n"
        msg += _("Report text context characters: ") + str(self.app.settings['report_text_context_characters']) + "\n"
        msg += _("Report text context style: ") + self.app.settings['report_text_context_style'] + "\n"
        msg += _("Backup on open") + f": {self.app.settings['backup_on_open']}\n"
        msg += _("Backup AV files") + f": {self.app.settings['backup_av_files']}\n"
        if self.app.settings['ai_enable'] == 'True':
            msg += _("AI integration is enabled") + "\n"
        else:
            msg += _("AI integration is disabled") + "\n"
        msg += _("Style") + "; " + self.app.settings['stylesheet']
        if platform.system() == "Windows":
            msg += "\n" + _("Directory (folder) paths / represents \\")
        self.ui.textEdit.append(msg)
        self.ui.textEdit.append("<p>&nbsp;</p>")
        self.ui.textEdit.textCursor().movePosition(QtGui.QTextCursor.MoveOperation.End)
        self.ui.tabWidget.setCurrentWidget(self.ui.tab_action_log)

    def text_segments_codes_table(self):
        """ Show table of text segments (rows) by codes (columns). """

        self.ui.label_reports.hide()
        ui = DialogCodesBySegments(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def report_sql(self):
        """ Run SQL statements on database. """

        self.ui.label_reports.hide()
        ui = DialogSQL(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    """def text_mining(self):
        ''' text analysis of files / cases / codings.
        NOT CURRENTLY IMPLEMENTED, FOR FUTURE EXPANSION.
        '''

        ui = DialogTextMining(self.app, self.ui.textEdit)
        ui.show()"""

    def report_coding_comparison(self):
        """ Compare two or more coders across all text files using Cohens Kappa. """

        self.ui.label_reports.hide()
        ui = DialogReportCoderComparisons(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def report_comparison_table(self):
        self.ui.label_reports.hide()
        ui = DialogReportComparisonTable(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def report_compare_coders_by_file(self):
        """ Compare two coders selection by file - text, A/V or image. """

        self.ui.label_reports.hide()
        ui = DialogCompareCoderByFile(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def report_code_frequencies(self):
        """ Show code frequencies overall and by coder. """

        self.ui.label_reports.hide()
        ui = DialogReportCodeFrequencies(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def report_code_relations(self):
        """ Show code relations in text files. """

        self.ui.label_reports.hide()
        ui = DialogReportRelations(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def co_occurence(self):
        """ Show overlapping codes in text files. """

        self.ui.label_reports.hide()
        ui = DialogReportCooccurrence(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def report_exact_text_matches(self):
        """ Show exact text coding matches in text files. """

        self.ui.label_reports.hide()
        ui = DialogReportExactTextMatches(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def report_coding(self):
        """ Report on coding and categories. """

        self.ui.label_reports.hide()
        ui = DialogReportCodes(self.app, self.ui.textEdit, self.ui.tab_coding)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def report_file_summary(self):
        """ Report on file details. """

        self.ui.label_reports.hide()
        ui = DialogReportFileSummary(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def report_code_summary(self):
        """ Report on code details. """

        self.ui.label_reports.hide()
        ui = DialogReportCodeSummary(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def view_graph_original(self):
        """ Show list or acyclic graph of codes and categories. """

        self.ui.label_reports.hide()
        ui = ViewGraph(self.app)
        ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def view_charts(self):
        """ Show charts of codes and categories. """

        self.ui.label_reports.hide()
        ui = ViewCharts(self.app)
        ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    @staticmethod
    def help():
        """ Display manual in browser. """

        webbrowser.open("https://github.com/ccbogel/QualCoder/wiki")

    def display_menu_key_shortcuts(self):
        self.ui.textEdit.append(menu_shortcuts_display)
        self.ui.textEdit.append(coding_shortcuts_display)
        self.ui.tabWidget.setCurrentWidget(self.ui.tab_action_log)
        
    def action_log_scroll_bottom(self):
        """Scrolls the action log to the very bottom, malking new entries visible."""
        self.ui.textEdit.verticalScrollBar().setValue(self.ui.textEdit.verticalScrollBar().maximum())

    def about(self):
        """ About dialog. """

        ui = DialogInformation(self.app, "About", "")
        ui.exec()

    def special_functions(self):
        """ User requested special functions dialog. """

        ui = DialogSpecialFunctions(self.app, self.ui.textEdit, self.ui.tab_coding)
        ui.exec()
        if ui.projects_merged:
            self.tab_layout_helper(self.ui.tab_manage, None)
            self.tab_layout_helper(self.ui.tab_coding, None)
            self.tab_layout_helper(self.ui.tab_reports, None)
            self.project_summary_report()

    def manage_attributes(self):
        """ Create, edit, delete, rename attributes. """

        self.ui.label_manage.hide()
        ui = DialogManageAttributes(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_manage, ui)

    def manage_references(self):
        """ Manage references. Import references. Edit references.
        Link/unlink references to files. """

        ui = DialogReferenceManager(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_manage, ui)

    def import_plain_text_codes(self):
        """ Import a list of plain text codes codebook.
        The codebook is a plain text file or csv file.
        In plain text file, Tab separates the codename from the code description.
        The >> symbol is used to assign code to category:  code>>category
        """

        ImportPlainTextCodes(self.app, self.ui.textEdit)

    def import_survey(self):
        """ Import survey flat sheet: csv file or xlsx.
        Create cases and assign attributes to cases.
        Identify qualitative questions and assign these data to the source table for
        coding and review. Modal dialog. """

        self.ui.label_manage.hide()
        ui = DialogImportSurvey(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_manage, ui)

    def import_twitter(self):
        """ Import twitter flat sheet: csv file.
        Create cases by User name.
        Create qualitative text files for each tweet.
        Assign attributes to cases and files. """

        self.ui.label_manage.hide()
        ui = DialogImportTwitterData(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_manage, ui)

    def manage_cases(self):
        """ Create, edit, delete, rename cases, add cases to files or parts of
        files, add memos to cases. """

        self.ui.label_manage.hide()
        ui = DialogCases(self.app, self.ui.textEdit)
        self.tab_layout_helper(self.ui.tab_manage, ui)

    def manage_files(self):
        """ Create text files or import files from odt, docx, html and
        plain text. Rename, delete and add memos to files.
        """

        self.ui.label_manage.hide()
        ui = DialogManageFiles(self.app, self.ui.textEdit, self.ui.tab_coding, self.ui.tab_reports)
        self.tab_layout_helper(self.ui.tab_manage, ui)

    def manage_bad_file_links(self):
        """ Fix any bad links to files.
        File names must match but paths can be different. """

        self.ui.label_manage.hide()
        ui = DialogManageLinks(self.app, self.ui.textEdit, self.ui.tab_coding)
        self.tab_layout_helper(self.ui.tab_manage, ui)
        bad_links = self.app.check_bad_file_links()
        if not bad_links:
            self.ui.actionManage_bad_links_to_files.setEnabled(False)

    def journals(self):
        """ Create and edit journals.
        From version 3.4 in a non-modal window. """

        self.ui.label_manage.hide()
        ui = DialogJournals(self.app, self.ui.textEdit)
        ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.journal_display = ui
        ui.show()

    def text_coding(self, task='documents', doc_id=None, doc_sel_start=0, doc_sel_end=0):
        """ Create edit and delete codes. Apply and remove codes and annotations to the
        text in imported text files. 
        
        task: "documents": The default, shows the tab with the text documents
              "ai_search": Shows the tab "AI Search"
        doc_id: If not None and task = "documents", this doument will be loaded in the coding window
        doc_sel_start: The character-position of the beginning of the selection in the coding window
        doc_sel_end: The end of the selection 
        """

        files = self.app.get_text_filenames()
        if len(files) > 0:
            self.ui.label_coding.hide()
            ui = DialogCodeText(self.app, self.ui.textEdit, self.ui.tab_reports)
            ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
            self.tab_layout_helper(self.ui.tab_coding, ui)
            if task == 'documents':
                ui.ui.tabWidget.setCurrentWidget(ui.ui.tab_docs)
                if doc_id is not None:
                    ui.open_doc_selection(doc_id, doc_sel_start, doc_sel_end)
            elif task == 'ai_search':
                ui.ui.tabWidget.setCurrentWidget(ui.ui.tab_ai)               
        else:
            msg = _("This project contains no text files.")
            Message(self.app, _('No text files'), msg).exec()

    def pdf_coding(self):
        """ Create edit and delete codes. Apply and remove codes  to the pdf
        text in imported pdf files. """

        files = self.app.get_pdf_filenames()
        if len(files) > 0:
            self.ui.label_coding.hide()
            ui = DialogCodePdf(self.app, self.ui.textEdit, self.ui.tab_reports)
            ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
            self.tab_layout_helper(self.ui.tab_coding, ui)
        else:
            msg = _("This project contains no pdf files.")
            Message(self.app, _('No pdf files'), msg).exec()

    def image_coding(self):
        """ Create edit and delete codes. Apply and remove codes to the image (or regions)
        """

        files = self.app.get_image_filenames()
        if len(files) > 0:
            self.ui.label_coding.hide()
            ui = DialogCodeImage(self.app, self.ui.textEdit, self.ui.tab_reports)
            ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
            self.tab_layout_helper(self.ui.tab_coding, ui)
        else:
            msg = _("This project contains no image files.")
            Message(self.app, _('No image files'), msg).exec()

    def av_coding(self):
        """ Create edit and delete codes. Apply and remove codes to segments of the
        audio or video file. Added try block in case VLC bindings do not work. """

        files = self.app.get_av_filenames()
        if len(files) == 0:
            msg = _("This project contains no audio/video files.")
            Message(self.app, _('No a/v files'), msg).exec()
            return
        if not vlc:
            msg = _("VLC is not installed. Cannot code audio/video files.")
            Message(self.app, _('Install VLC'), msg).exec()
            return
        self.ui.label_coding.hide()
        try:
            ui = DialogCodeAV(self.app, self.ui.textEdit, self.ui.tab_reports)
            ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
            self.tab_layout_helper(self.ui.tab_coding, ui)
        except Exception as err:
            logger.debug(str(err))
            Message(self.app, _("A/V Coding"), str(err), "warning").exec()

    def code_color_scheme(self):
        """ Edit code color scheme. """

        ui = DialogCodeColorScheme(self.app, self.ui.textEdit)
        ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.tab_layout_helper(self.ui.tab_coding, ui)

    def code_organiser(self):
        """ Organise codes structure. """

        self.ui.label_coding.setText("")
        ui = CodeOrganiser(self.app, self.ui.textEdit)
        ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.tab_layout_helper(self.ui.tab_reports, None)
        self.tab_layout_helper(self.ui.tab_coding, ui)

    def ai_chat(self):
        """ Add AI chat to tab. """

        self.ai_chat_window = DialogAIChat(self.app, self.ui.textEdit, self)
        self.tab_layout_helper(self.ui.tab_ai_chat, self.ai_chat_window)

    def tab_layout_helper(self, tab_widget, ui):
        """ Used when loading a coding, report or manage dialog  in to a tab widget.
         Add widget if no layout.
         If there is a layout, then remove all widgets from it and add the new widget. """

        self.ui.tabWidget.setCurrentWidget(tab_widget)
        # Check the tab has a layout and widgets
        contents = tab_widget.layout()
        if contents is None:
            # Tab has no layout so add one with widget
            layout = QtWidgets.QVBoxLayout()
            if ui is not None:
                layout.addWidget(ui)
            tab_widget.setLayout(layout)
        else:
            # Remove widgets from layout
            for i in reversed(range(contents.count())):
                contents.itemAt(i).widget().close()
                contents.itemAt(i).widget().setParent(None)
            if ui is not None:
                contents.addWidget(ui)

    def codebook(self):
        """ Export a text file code book of categories and codes.
        """

        Codebook(self.app, self.ui.textEdit)

    def codebook_with_memos(self):
        """ Export a text file code book of categories and codes with their memos.
        """

        Codebook(self.app, self.ui.textEdit, memos=True)

    def refi_project_export(self):
        """ Export the project as a qpdx zipped folder.
         Follows the REFI Project Exchange standards.
         NEED TO TEST RELATIVE EXPORTS, TIMESTAMPS AND TRANSCRIPTION
        """

        RefiExport(self.app, self.ui.textEdit, "project")

    def refi_codebook_export(self):
        """ Export the codebook as .qdc
        Follows the REFI standard version 1.0. https://www.qdasoftware.org/
        """
        #
        RefiExport(self.app, self.ui.textEdit, "codebook")

    def refi_codebook_import(self):
        """ Import a codebook .qdc into an opened project.
        Follows the REFI-QDA standard version 1.0. https://www.qdasoftware.org/
         """

        RefiImport(self.app, self.ui.textEdit, "qdc")

    def refi_project_import(self):
        """ Import a qpdx QDA project into a new project space.
        Follows the REFI standard.
        CURRENTLY IN TESTING AND NOT COMPLETE NOR VALIDATED.
         NEED TO TEST RELATIVE EXPORTS, TIMESTAMPS AND TRANSCRIPTION
         """

        self.close_project()
        self.ui.textEdit.append(_("IMPORTING REFI-QDA PROJECT"))
        msg = _(
            "Step 1: You will be asked for a new QualCoder project name.\nStep 2: You will be asked for the QDPX file.")
        Message(self.app, _('REFI-QDA import steps'), msg).exec()
        self.new_project()
        # Check project created successfully
        if self.app.project_name == "":
            Message(self.app, _("Project creation"), _("REFI-QDA Project not successfully created"), "warning").exec()
            return
        RefiImport(self.app, self.ui.textEdit, "qdpx")
        if self.app.settings['ai_enable'] == 'True':
            self.app.ai.init_llm(self, rebuild_vectorstore=True)
        self.project_summary_report()

    def rqda_project_import(self):
        """ Import an RQDA format project into a new project space. """

        self.close_project()
        self.ui.textEdit.append(_("IMPORTING RQDA PROJECT"))
        msg = _(
            "Step 1: You will be asked for a new QualCoder project name.\nStep 2: You will be asked for the RQDA file.")
        Message(self.app, _('RQDA import steps'), msg).exec()
        self.new_project()
        # check project created successfully
        if self.app.project_name == "":
            Message(self.app, _('Project creation'), _("Project not successfully created"), "critical").exec()
            return
        RqdaImport(self.app, self.ui.textEdit)
        self.project_summary_report()

    def closeEvent(self, event):
        """ Override the QWindow close event.
        Close all dialogs and database connection.
        If selected via menu option exit: event == False
        If selected via window x close: event == QtGui.QCloseEvent
        Close project will also delete a backup if a backup was made and no changes occurred.
        """

        if not self.force_quit:
            quit_msg = _("Are you sure you want to quit?")
            reply = QtWidgets.QMessageBox.question(self, 'Message', quit_msg,
                                                   QtWidgets.QMessageBox.StandardButton.Yes,
                                                   QtWidgets.QMessageBox.StandardButton.No)
            if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                # close project before the dialog list, as close project clean the dialogs
                self.close_project()
                # self.dialog_list = None
                # save main window geometry to config.ini
                self.app.settings['mainwindow_geometry'] = self.saveGeometry().toHex().data().decode('utf-8') 
                self.app.write_config_ini(self.app.settings, self.app.ai_models)
                if self.app.conn is not None:
                    try:
                        self.app.conn.commit()
                        self.app.conn.close()
                    except Exception as err:
                        print("closeEvent", err)
                        logger.warning("close event " + str(err))
                # TODO calls twice, do not know how to fix
                QtWidgets.QApplication.instance().quit()
                return
            if event is False:
                return
            else:
                event.ignore()

    def new_project(self):
        """ Create a new project folder with data.qda (sqlite) and folders for documents,
        images, audio and video.
        Note the database does not keep a table specifically for users (coders), instead
        usernames can be freely entered through the settings dialog and are collated from
        coded text, images and a/v.
        v2 has added column in code_text table to link to avid in code_av table.
        v3 has added columns in code_text, code_image, code_av for important - to mark particular important codings.
        v4 has added column ctid (autonumber) in code_text.
        v5 had added column for codername in project. added column for av_text_id in source to link A/V with text file.
            And a stored_sql table.
        v6 has tables for storage of graph items.
        v7 has memo links from graph items (text/image/av to coding memos).
        v8 has table for ris bibliography data.
        """

        self.journal_display = None
        previous_app = self.app
        self.app = App()
        if self.app.settings['directory'] == "":
            self.app.settings['directory'] = os.path.expanduser('~')
        self.app.ai = AiLLM(self.app, self.ui.textEdit)
        project_path, ok = QtWidgets.QFileDialog.getSaveFileName(self,
                                                             _("Enter project name"), self.app.settings['directory'])
        # options=QtWidgets.QFileDialog.Option.DontUseNativeDialog)
        if project_path == "":
            self.app = previous_app
            Message(self.app, _("Project"), _("No project created."), "critical").exec()
            return

        # Add suffix to project name if it already exists
        counter = 0
        extension = ""
        while os.path.exists(project_path + extension + ".qda"):
            # print("C", counter, project_path + extension + ".qda")
            if counter > 0:
                extension = f"_{counter}"
            counter += 1
        self.app.project_path = project_path + extension + ".qda"
        try:
            os.mkdir(self.app.project_path)
            os.mkdir(os.path.join(self.app.project_path, "images"))
            os.mkdir(os.path.join(self.app.project_path, "audio"))
            os.mkdir(os.path.join(self.app.project_path, "video"))
            os.mkdir(os.path.join(self.app.project_path, "documents"))
        except Exception as err:
            logger.critical(_("Project creation error ") + str(err))
            Message(self.app, _("Project"), self.app.project_path + _(" not successfully created"), "critical").exec()
            self.app = App()
            self.app.ai = AiLLM(self.app, self.ui.textEdit)
            return
        self.app.project_name = self.app.project_path.rpartition('/')[2]
        self.app.settings['directory'] = self.app.project_path.rpartition('/')[0]
        self.app.create_connection(self.app.project_path)
        cur = self.app.conn.cursor()
        cur.execute(
            "CREATE TABLE project (databaseversion text, date text, memo text,about text, bookmarkfile integer, "
            "bookmarkpos integer, codername text)")
        cur.execute(
            "CREATE TABLE source (id integer primary key, name text, fulltext text, mediapath text, memo text, "
            "owner text, date text, av_text_id integer, risid integer, unique(name))")
        cur.execute(
            "CREATE TABLE code_image (imid integer primary key,id integer,x1 integer, y1 integer, width integer, "
            "height integer, cid integer, memo text, date text, owner text, important integer)")
        cur.execute(
            "CREATE TABLE code_av (avid integer primary key,id integer,pos0 integer, pos1 integer, cid integer, "
            "memo text, date text, owner text, important integer)")
        cur.execute(
            "CREATE TABLE annotation (anid integer primary key, fid integer,pos0 integer, pos1 integer, memo text, "
            "owner text, date text, unique(fid,pos0,pos1,owner))")
        cur.execute(
            "CREATE TABLE attribute_type (name text primary key, date text, owner text, memo text, caseOrFile text, "
            "valuetype text)")
        # Database version v6 - unique constraint for attribute (name, attr_type, id)
        cur.execute(
            "CREATE TABLE attribute (attrid integer primary key, name text, attr_type text, value text, id integer, "
            "date text, owner text, unique(name,attr_type,id))")
        cur.execute(
            "CREATE TABLE case_text (id integer primary key, caseid integer, fid integer, pos0 integer, pos1 integer, "
            "owner text, date text, memo text)")
        cur.execute(
            "CREATE TABLE cases (caseid integer primary key, name text, memo text, owner text,date text, "
            "constraint ucm unique(name))")
        cur.execute(
            "CREATE TABLE code_cat (catid integer primary key, name text, owner text, date text, memo text, "
            "supercatid integer, unique(name))")
        cur.execute(
            "CREATE TABLE code_text (ctid integer primary key, cid integer, fid integer,seltext text, pos0 integer, "
            "pos1 integer, owner text, date text, memo text, avid integer, important integer, "
            "unique(cid,fid,pos0,pos1, owner))")
        cur.execute(
            "CREATE TABLE code_name (cid integer primary key, name text, memo text, catid integer, owner text,"
            "date text, color text, unique(name))")
        # Database version v6 - unique name for journal
        cur.execute("CREATE TABLE journal (jid integer primary key, name text, jentry text, date text, owner text, "
                    "unique(name))")
        cur.execute("CREATE TABLE stored_sql (title text, description text, grouper text, ssql text, unique(title))")
        # Tables to store graph. sqlite 0 is False 1 is True
        cur.execute("CREATE TABLE graph (grid integer primary key, name text, description text, "
                    "date text, scene_width integer, scene_height integer, unique(name));")
        cur.execute("CREATE TABLE gr_cdct_text_item (gtextid integer primary key, grid integer, x integer, y integer, "
                    "supercatid integer, catid integer, cid integer, font_size integer, bold integer, "
                    "isvisible integer, displaytext text);")
        cur.execute("CREATE TABLE gr_case_text_item (gcaseid integer primary key, grid integer, x integer, "
                    "y integer, caseid integer, font_size integer, bold integer, color text, displaytext text);")
        cur.execute("CREATE TABLE gr_file_text_item (gfileid integer primary key, grid integer, x integer, "
                    "y integer, fid integer, font_size integer, bold integer, color text, displaytext text);")
        cur.execute("CREATE TABLE gr_free_text_item (gfreeid integer primary key, grid integer, freetextid integer,"
                    "x integer, y integer, free_text text, font_size integer, bold integer, color text,"
                    "tooltip text, ctid integer,memo_ctid integer, memo_imid integer, memo_avid integer);")
        cur.execute("CREATE TABLE gr_cdct_line_item (glineid integer primary key, grid integer, "
                    "fromcatid integer, fromcid integer, tocatid integer, tocid integer, color text, "
                    "linewidth real, linetype text, isvisible integer);")
        cur.execute("CREATE TABLE gr_free_line_item (gflineid integer primary key, grid integer, "
                    "fromfreetextid integer, fromcatid integer, fromcid integer, fromcaseid integer,"
                    "fromfileid integer, fromimid integer, fromavid integer, tofreetextid integer, tocatid integer, "
                    "tocid integer, tocaseid integer, tofileid integer, toimid integer, toavid integer, color text,"
                    "linewidth real, linetype text);")
        cur.execute("CREATE TABLE gr_pix_item (grpixid integer primary key, grid integer, imid integer,"
                    "x integer, y integer, px integer, py integer, w integer, h integer, filepath text,"
                    "tooltip text);")
        cur.execute("CREATE TABLE gr_av_item (gr_avid integer primary key, grid integer, avid integer,"
                    "x integer, y integer, pos0 integer, pos1 integer, filepath text, tooltip text, color text);")
        cur.execute("CREATE TABLE ris (risid integer, tag text, longtag text, value text);")
        cur.execute("INSERT INTO project VALUES(?,?,?,?,?,?,?)",
                    ('v8', datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), '', qualcoder_version, 0,
                     0, self.app.settings['codername']))
        self.app.conn.commit()
        try:
            # Get and display some project details
            self.ui.textEdit.append("\n" + _("New project: ") + self.app.project_path + _(" created."))
            self.ui.textEdit.append(_("Opening: ") + self.app.project_path)
            self.setWindowTitle("QualCoder " + self.app.project_name)
            cur.execute('select sqlite_version()')
            self.ui.textEdit.append(f"SQLite version: {cur.fetchone()}")
            cur.execute("select databaseversion, date, memo, about from project")
            result = cur.fetchone()
            self.project['databaseversion'] = result[0]
            self.project['date'] = result[1]
            self.project['memo'] = result[2]
            self.project['about'] = result[3]
            self.ui.textEdit.append(_("New Project Created") + "\n========\n"
                                    + _("DB Version:") + f"{self.project['databaseversion']}\n"
                                    + _("Date: ") + f"{self.project['date']}\n"
                                    + _("About: ") + f"{self.project['about']}\n"
                                    + _("Coder:") + f"{self.app.settings['codername']}\n"
                                    + "========")
        except Exception as err:
            msg = _("Problem creating database ")
            logger.warning(f"{msg}{self.app.project_path} Exception: {err}")
            self.ui.textEdit.append(f"\n{msg}\n{self.app.project_path}")
            self.ui.textEdit.append(str(err))
            self.close_project()
            return
        # New project, so tell open project NOT to back up, as there will be nothing in there to back up
        self.open_project(self.app.project_path, "yes")
        self.ui.tabWidget.setCurrentWidget(self.ui.tab_action_log)
        # Remove widgets from each tab
        contents = self.ui.tab_reports.layout()
        if contents:
            for i in reversed(range(contents.count())):
                contents.itemAt(i).widget().close()
                contents.itemAt(i).widget().setParent(None)
        contents = self.ui.tab_coding.layout()
        if contents:
            for i in reversed(range(contents.count())):
                contents.itemAt(i).widget().close()
                contents.itemAt(i).widget().setParent(None)
        contents = self.ui.tab_manage.layout()
        if contents:
            for i in reversed(range(contents.count())):
                contents.itemAt(i).widget().close()
                contents.itemAt(i).widget().setParent(None)

    def change_settings(self, section=None, enable_ai=False):
        """ Change default settings - the coder name, font, font size.
        Language, Backup options.
        As this dialog affects all others if the coder name changes, on exit of the dialog,
        all other opened dialogs are destroyed.
        
        section = 'AI' moves to the AI settings at the bottom of the dialog
        enable_ai = if True, the AI will be enabled in settings
        """
        current_coder = self.app.settings['codername']
        current_ai_enable = self.app.settings['ai_enable']
        current_ai_model_index = int(self.app.settings['ai_model_index'])
        if current_ai_model_index >= 0:
            current_ai_api_key = self.app.ai_models[current_ai_model_index]['api_key']
        else:
            current_ai_api_key = ''
        ui = DialogSettings(self.app, section=section, enable_ai=enable_ai)
        ret = ui.exec()
        if ret == QtWidgets.QDialog.DialogCode.Rejected:  # Dialog has been canceled
            return

        self.app.settings, self.app.ai_models = self.app.load_settings()
        self.settings_report()
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.ai_chat_window.init_styles()
        
        if current_ai_enable != self.app.settings['ai_enable']:
            if self.app.settings['ai_enable'] == 'True':
                # AI is newly enabled:
                self.app.ai.init_llm(self, rebuild_vectorstore=False)
            else:  # AI is disabled
                self.app.ai.close()
        elif int(current_ai_model_index) < 0:
            # no model selected
            self.app.settings['ai_enable'] = 'False'
            self.app.ai.close()                        
        elif current_ai_model_index != self.app.settings['ai_model_index']:
            # current model has changed
            self.app.ai.init_llm(self)
        elif current_ai_api_key != self.app.ai_models[current_ai_model_index]['api_key']:
            # ai api-key has changed
            self.app.ai.init_llm(self)
            
        # Name change: Close all opened dialogs as coder name needs to change everywhere
        if current_coder != self.app.settings['codername']:
            self.ui.textEdit.append(_("Coder name changed to: ") + self.app.settings['codername'])
            # Remove widgets from each tab
            contents = self.ui.tab_reports.layout()
            if contents:
                for i in reversed(range(contents.count())):
                    contents.itemAt(i).widget().close()
                    contents.itemAt(i).widget().setParent(None)
            contents = self.ui.tab_coding.layout()
            if contents:
                for i in reversed(range(contents.count())):
                    contents.itemAt(i).widget().close()
                    contents.itemAt(i).widget().setParent(None)
            contents = self.ui.tab_manage.layout()
            if contents:
                for i in reversed(range(contents.count())):
                    contents.itemAt(i).widget().close()
                    contents.itemAt(i).widget().setParent(None)
                    
    def project_memo(self):
        """ Give the entire project a memo. """
        memo = self.app.get_project_memo()
        # If the memo is empty, add a template that defines all the necessary information for the AI  
        if memo is None or memo == '':
            memo = _('**Research topic, questions and objectives:** \n\n'
                     '**Methodology:** \n\n'
                     '**Participants and data collected:** \n\n'
                     '#####\n'
                     '(Everything below this mark is a personal note and will never be sent to the AI.)')
        ui = DialogMemo(self.app, _("Memo for project ") + self.app.project_name,
                        memo)
        ui.exec()
        if memo != ui.memo:
            cur = self.app.conn.cursor()
            cur.execute('update project set memo=?', (ui.memo,))
            self.app.conn.commit()
            self.ui.textEdit.append(_("Project memo entered."))
            self.app.delete_backup = False

    # lock file helper functions:

    def create_lock_file(self, break_existing_lock=False):
        """Create the lock file.
           break_existing_lock: if True, the lock file will be created even if it already exists
        """
        if (not break_existing_lock) and os.path.exists(self.lock_file_path):
            return False
        try:
            mode = 'w' if break_existing_lock else 'x'
            with open(self.lock_file_path, mode, encoding='utf-8') as lock_file:
                lock_file.write(f"{getpass.getuser()}\n{str(time.time())}")
            return True
        except FileExistsError:
            return False

    def delete_lock_file(self):
        """ Delete the lock file to release the lock. """

        try:
            if self.lock_file_path != '':
                os.remove(self.lock_file_path)
        except Exception as e_:  # TODO determine specific exception type to add in here, so printing e_
            print("delete_lock_file", e_)
            logger.debug(e_)

    def lock_file_io_error(self):
        msg = _('An error occured while writing to the project folder. '
                'Please close the project and try to open it again.')
        msg_box = Message(self.app, _("I/O Error"), msg, "critical")
        btn_close = msg_box.addButton(_("Close"), QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        btn_ignore = msg_box.addButton("Ignore", QtWidgets.QMessageBox.ButtonRole.RejectRole)
        msg_box.setDefaultButton(btn_close)
        msg_box.exec()
        if msg_box.clickedButton() == btn_close:
            self.close_project()
        logger.debug(msg)

    def prepare_heartbeat_thread(self):
        """ Prepare and start the heartbeat QThread. """

        self.heartbeat_thread = QtCore.QThread()
        self.heartbeat_worker = ProjectLockHeartbeatWorker(self.app, self.lock_file_path)
        self.heartbeat_worker.moveToThread(self.heartbeat_thread)
        self.heartbeat_thread.started.connect(self.heartbeat_worker.write_heartbeat)
        self.heartbeat_worker.finished.connect(self.heartbeat_thread.quit)
        self.heartbeat_worker.finished.connect(self.heartbeat_worker.deleteLater)
        self.heartbeat_thread.finished.connect(self.heartbeat_thread.deleteLater)
        self.heartbeat_worker.io_error.connect(self.lock_file_io_error)
        self.heartbeat_thread.start()

    def stop_heartbeat(self, wait=False):
        """Stop the heartbeat and delete the lock file (if it exists). """

        if self.heartbeat_worker:
            try:
                self.heartbeat_worker.stop()
                if wait:
                    self.heartbeat_thread.wait()  # Wait for the thread to properly finish
            except Exception as e_:  # TODO determine actual exception
                print(e_)
                logger.debug(e_)
        self.delete_lock_file()
        self.lock_file_path = ''

    def open_project(self, path_="", newproject="no"):
        """ Open an existing project.
        if set, also save a backup datetime stamped copy at the same time.
        Do not back up on a newly created project, as it will not contain data.
        A backup is created if settings backup is True.
        The backup is deleted, if no changes.
        Backups are created using the date and 24 hour suffix: _BKUP_yyyymmdd_hh
        Backups are not replaced within the same hour.
        Update older databases to current version mainly by adding columns and tables.
        Table constraints are not updated (code_text duplicated codings).
        param:
            path: if path is "" then get the path from a dialog, otherwise use the supplied path
            newproject: yes or no  if yes then do not make an initial backup
        """

        self.journal_display = None
        default_directory = self.app.settings['directory']
        if path_ == "" or path_ is False:
            if default_directory == "":
                default_directory = os.path.expanduser('~')
            path_ = QtWidgets.QFileDialog.getExistingDirectory(self,
                                                               _('Open project directory'), default_directory)
        if path_ == "" or path_ is False:
            return
        self.close_project()
        msg = ""
        # New path variable from recent_projects.txt contains time | path
        # Older variable only listed the project path
        path_split = path_.split("|")
        proj_path = ""
        if len(path_split) == 1:
            proj_path = path_split[0]
        if len(path_split) == 2:
            proj_path = path_split[1]
        if len(path) > 3 and proj_path[-4:] == ".qda":
            # Lock file management
            self.lock_file_path = os.path.normpath(proj_path + '/project_in_use.lock')
            if not self.create_lock_file():
                # Lock file already exists. Checking if it has timed out or not.
                with open(self.lock_file_path, 'r', encoding='utf-8') as lock_file:
                    try:
                        lock_user = lock_file.readline()[:-1]
                        lock_timestamp = float(lock_file.readline())
                    except Exception as e_:  # TODO add specific exception
                        print(e_)
                        logger.warning(e_)
                        # lock file seems corrupted/partially written. Retry once in case another instance was writing to the file at the same time:
                        time.sleep(0.5)
                        try:
                            lock_user = lock_file.readline()[:-1]
                            lock_timestamp = float(lock_file.readline())
                        except Exception as e_:  # permanent error, break the lock
                            print(e_)  # TODO determine specific exception
                            logger.warning(e_)
                            lock_user = 'unknown'
                            lock_timestamp = 0.0
                if float(time.time()) - lock_timestamp > lock_timeout:
                    # has timed out, break the lock
                    msg = _(
                        'QualCoder detected that the project was not properly closed the last time it was used by "') + lock_user + '".\n'
                    msg += _(
                        'In most cases, you can still continue your work as usual. If you encounter any problems, search for a recent backup in the project folder.')
                    logger.warning(msg)
                    msg_box = Message(self.app, _("Open file"), msg, "information")
                    msg_box.setStandardButtons(
                        QtWidgets.QMessageBox.StandardButton.Ok | QtWidgets.QMessageBox.StandardButton.Abort)
                    msg_box.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Ok)
                    ret = msg_box.exec()
                    if ret == QtWidgets.QMessageBox.StandardButton.Abort:
                        self.app.project_path = ""
                        self.app.project_name = ""
                        return
                    self.create_lock_file(break_existing_lock=True)
                else:
                    # lock is valid, project seems to be in use by other user
                    msg = _('Project cannot be opened since it\'s already in use by "') + lock_user + _(
                        '". Please retry later.')
                    logger.warning(msg)
                    Message(self.app, _("Cannot open file"), msg, "critical").exec()
                    self.app.project_path = ""
                    self.app.project_name = ""
                    return
            self.prepare_heartbeat_thread()
            try:
                self.app.create_connection(proj_path)
            except Exception as err:
                self.app.conn = None
                msg += " " + str(err)
                logger.debug(msg)
        if self.app.conn is None:
            msg += "\n" + proj_path
            Message(self.app, _("Cannot open file"), msg, "critical").exec()
            self.stop_heartbeat()
            self.app.project_path = ""
            self.app.project_name = ""
            return
        # Check that the connection is to a valid QualCoder database
        cur = self.app.conn.cursor()
        try:
            cur.execute("select databaseversion, date, memo, about from project")
            res = cur.fetchone()
            if "QualCoder" not in res[3]:
                logger.debug("This is not a QualCoder database")
                self.close_project()
                return
        except Exception as err:
            logger.debug("This in not a QualCoder database " + str(err))
            self.close_project()
            return

        # Potential design flaw to have the current coders name in the config.ini file
        # as it would change to this coder when opening different projects
        # Check that the coder name from setting ini file is in the project
        # If not then replace with a name in the project
        # Database version 5 (QualCoder 2.8 and newer) stores the current coder in the project table
        names = self.app.get_coder_names_in_project()
        if self.app.settings['codername'] not in names and len(names) > 0:
            self.app.settings['codername'] = names[0]
            self.app.write_config_ini(self.app.settings, self.app.ai_models)
            self.ui.textEdit.append(_("Default coder name changed to: ") + names[0])
        # Display some project details
        self.app.append_recent_project(self.app.project_path)
        self.fill_recent_projects_menu_actions()
        self.setWindowTitle("QualCoder " + self.app.project_name)

        # Check avid column in code_text table, Database version v2
        cur = self.app.conn.cursor()
        try:
            cur.execute("select avid from code_text")
        except sqlite3.OperationalError:
            try:
                cur.execute("ALTER TABLE code_text ADD avid integer")
                self.app.conn.commit()
            except Exception as err:
                logger.debug(str(err))
        try:
            cur.execute("select bookmarkfile from project")
        except sqlite3.OperationalError:
            try:
                cur.execute("ALTER TABLE project ADD bookmarkfile integer")
                self.app.conn.commit()
                cur.execute("ALTER TABLE project ADD bookmarkpos integer")
                self.app.conn.commit()
                self.ui.textEdit.append(_("Updating database to version") + " v2")
            except Exception as err:
                logger.debug(str(err))
        # Database version v3
        cur = self.app.conn.cursor()
        try:
            cur.execute("select important from code_text")
        except sqlite3.OperationalError:
            try:
                cur.execute("ALTER TABLE code_text ADD important integer")
                self.app.conn.commit()
            except Exception as err:
                logger.debug(str(err))
                cur = self.app.conn.cursor()
        try:
            cur.execute("select important from code_av")
        except sqlite3.OperationalError:
            try:
                cur.execute("ALTER TABLE code_av ADD important integer")
                self.app.conn.commit()
            except Exception as err:
                logger.debug(str(err))
        cur = self.app.conn.cursor()
        try:
            cur.execute("select important from code_image")
        except sqlite3.OperationalError:
            try:
                cur.execute("ALTER TABLE code_image ADD important integer")
                self.app.conn.commit()
                self.ui.textEdit.append(_("Updating database to version") + " v3")
            except Exception as err:
                logger.debug(str(err))
        # Database version v4
        try:
            cur.execute("select ctid from code_text")
        except sqlite3.OperationalError:
            cur.execute(
                "CREATE TABLE code_text2 (ctid integer primary key, cid integer, fid integer,seltext text, "
                "pos0 integer, pos1 integer, owner text, date text, memo text, avid integer, important integer, "
                "unique(cid,fid,pos0,pos1, owner))")
            self.app.conn.commit()
            sql = "insert into code_text2 (cid, fid, seltext, pos0, pos1, owner, date, memo, avid, important) "
            sql += "select cid, fid, seltext, pos0, pos1, owner, date, memo, avid, important from code_text"
            cur.execute(sql)
            self.app.conn.commit()
            cur.execute("drop table code_text")
            cur.execute("alter table code_text2 rename to code_text")
            cur.execute('update project set databaseversion="v4", about=?', [qualcoder_version])
            self.app.conn.commit()
            self.ui.textEdit.append(_("Updating database to version") + " v4")
        # Database version v5
        # Add codername to project, add av_text_id to source, add stored sql table
        try:
            cur.execute("select codername from project")
        except sqlite3.OperationalError:
            print(self.app.settings['codername'])
            cur.execute("ALTER TABLE project ADD codername text")
            self.app.conn.commit()
            cur.execute('update project set databaseversion="v5", about=?, codername=?',
                        [qualcoder_version, self.app.settings['codername']])
            self.app.conn.commit()
        try:
            cur.execute("select av_text_id from source")
        except sqlite3.OperationalError:
            cur.execute('ALTER TABLE source ADD av_text_id integer')
            self.app.conn.commit()
            # Add id link from AV file to text file.
            av_files = self.app.get_av_filenames()  # id, name, memo
            text_files = self.app.get_text_filenames()  # id, name, memo
            for av in av_files:
                for t in text_files:
                    if av['name'] + ".transcribed" == t['name']:
                        cur.execute('update source set av_text_id =? where id=?', [t['id'], av['id']])
                        self.app.conn.commit()
            self.ui.textEdit.append(_("Updating database to version") + " v5")
        try:
            cur.execute("select title from stored_sql")
        except sqlite3.OperationalError:
            cur.execute(
                "CREATE TABLE stored_sql (title text, description text, grouper text, ssql text, unique(title));")
            self.app.conn.commit()
        # Database version 6
        try:
            cur.execute("select name, description, date from graph")
        except sqlite3.OperationalError:
            # Tables to store graph. sqlite 0 is False 1 is True
            cur.execute("CREATE TABLE graph (grid integer primary key, name text, description text, "
                        "date text, scene_width integer, scene_height integer, unique(name));")
            cur.execute(
                "CREATE TABLE gr_cdct_text_item (gtextid integer primary key, grid integer, x integer, y integer, "
                "supercatid integer, catid integer, cid integer, font_size integer, bold integer, "
                "isvisible integer, displaytext text);")
            cur.execute("CREATE TABLE gr_case_text_item (gcaseid integer primary key, grid integer, x integer, "
                        "y integer, caseid integer, font_size integer, bold integer, color text, displaytext text);")
            cur.execute("CREATE TABLE gr_file_text_item (gfileid integer primary key, grid integer, x integer, "
                        "y integer, fid integer, font_size integer, bold integer, color text, displaytext text);")
            cur.execute("CREATE TABLE gr_free_text_item (gfreeid integer primary key, grid integer, freetextid integer,"
                        "x integer, y integer, free_text text, font_size integer, bold integer, color text,"
                        "tooltip text, ctid integer);")
            cur.execute("CREATE TABLE gr_cdct_line_item (glineid integer primary key, grid integer, "
                        "fromcatid integer, fromcid integer, tocatid integer, tocid integer, color text, "
                        "linewidth real, linetype text, isvisible integer);")
            cur.execute("CREATE TABLE gr_free_line_item (gflineid integer primary key, grid integer, "
                        "fromfreetextid integer, fromcatid integer, fromcid integer, fromcaseid integer,"
                        "fromfileid integer, fromimid integer, fromavid integer, tofreetextid integer, tocatid integer,"
                        "tocid integer, tocaseid integer, tofileid integer, toimid integer, toavid integer, color text,"
                        " linewidth real, linetype text);")
            cur.execute("CREATE TABLE gr_pix_item (grpixid integer primary key, grid integer, imid integer,"
                        "x integer, y integer, px integer, py integer, w integer, h integer, filepath text,"
                        "tooltip text);")
            cur.execute("CREATE TABLE gr_av_item (gr_avid integer primary key, grid integer, avid integer,"
                        "x integer, y integer, pos0 integer, pos1 integer, filepath text, tooltip text, color text);")
            self.app.conn.commit()
            cur.execute('update project set databaseversion="v6", about=?', [qualcoder_version])
            self.ui.textEdit.append(_("Updating database to version") + " v6")
        # Database v7
        db7_update = False
        try:
            cur.execute("select memo_ctid from gr_free_text_item")
        except sqlite3.OperationalError:
            cur.execute('ALTER TABLE gr_free_text_item ADD memo_ctid integer')
            self.app.conn.commit()
            db7_update = True
        try:
            cur.execute("select memo_imid from gr_free_text_item")
        except sqlite3.OperationalError:
            cur.execute('ALTER TABLE gr_free_text_item ADD memo_imid integer')
            self.app.conn.commit()
            db7_update = True
        try:
            cur.execute("select memo_avid from gr_free_text_item")
        except sqlite3.OperationalError:
            cur.execute('ALTER TABLE gr_free_text_item ADD memo_avid integer')
            self.app.conn.commit()
            db7_update = True
        if db7_update:
            cur.execute('update project set databaseversion="v7", about=?', [qualcoder_version])
            self.app.conn.commit()
            self.ui.textEdit.append(_("Updating database to version") + " v7")
        # Database version v8
        try:
            cur.execute("select risid from ris")
        except sqlite3.OperationalError:
            cur.execute("CREATE TABLE ris (risid integer, tag text, longtag text, value text);")
            cur.execute('update project set databaseversion="v8", about=?', [qualcoder_version])
            self.app.conn.commit()
            self.ui.textEdit.append(_("Updating database to version") + " v8")
        try:
            cur.execute("select risid from source")
        except sqlite3.OperationalError:
            cur.execute('ALTER TABLE source ADD risid integer')

        # Save a date and 24 hour stamped backup
        if self.app.settings['backup_on_open'] == 'True' and newproject == "no":
            msg, backup_name = self.app.save_backup()
            self.ui.textEdit.append(msg)
        msg = f"\n{_('Project Opened: ')}{self.app.project_name}"
        self.ui.textEdit.append(msg)
        self.project_summary_report()
        self.show_menu_options()

        # Delete codings (fid, id) that do not have a matching source id
        sql = "select fid from code_text where fid not in (select source.id from source)"
        cur.execute(sql)
        res = cur.fetchall()
        if res:
            self.ui.textEdit.append(_("Deleting code_text coding to deleted files: ") + str(res))
        for r in res:
            cur.execute("delete from code_text where fid=?", [r[0]])
        sql = "select code_image.id from code_image where code_image.id not in (select source.id from source)"
        cur.execute(sql)
        res = cur.fetchall()
        if res:
            self.ui.textEdit.append(_("Deleting code_image coding to deleted files: ") + str(res))
        for r in res:
            cur.execute("delete from code_image where id=?", [r[0]])
        sql = "select code_av.id from code_av where code_av.id not in (select source.id from source)"
        cur.execute(sql)
        res = cur.fetchall()
        if res:
            self.ui.textEdit.append(_("Deleting code_av coding to deleted files: ") + str(res))
        for r in res:
            cur.execute("delete from code_av where id=?", [r[0]])
        self.app.conn.commit()

        # Fix 'lost' categories if present.
        sql = "update code_cat set supercatid=null where supercatid is not null and supercatid not in "
        sql += "(select catid from code_cat)"
        cur.execute(sql)
        self.app.conn.commit()
        # Vacuum database
        cur.execute("vacuum")
        self.app.conn.commit()
        
        # AI: init llm and update vectorstore
        self.app.ai.init_llm(self)
        self.ai_chat_window.init_ai_chat(self.app)
        
        # Fix missing folders within QualCoder project. Will cause import errors.
        span = '<span style="color:red">'
        end_span = "</span>"
        missing_folders = False
        if not os.path.exists(os.path.join(self.app.project_path, "documents")):
            os.makedirs(os.path.join(self.app.project_path, "documents"))
            self.ui.textEdit.append(f"{span}No documents folder. Created empty folder{end_span}")
            missing_folders = True
        if not os.path.exists(os.path.join(self.app.project_path, "audio")):
            os.makedirs(os.path.join(self.app.project_path, "audio"))
            self.ui.textEdit.append(f"{span}No audio folder. Created empty folder{end_span}")
            missing_folders = True
        if not os.path.exists(os.path.join(self.app.project_path, "images")):
            os.makedirs(os.path.join(self.app.project_path, "images"))
            self.ui.textEdit.append(f"{span}No images folder. Created empty folder{end_span}")
            missing_folders = True
        if not os.path.exists(os.path.join(self.app.project_path, "video")):
            os.makedirs(os.path.join(self.app.project_path, "video"))
            self.ui.textEdit.append(f"{span}No video folder. Created empty folder{end_span}")
            missing_folders = True
        if missing_folders:
            Message(self.app, _("Information"), _("QualCoder project missing folders. Created empty folders")).exec()

    def project_summary_report(self):
        """ Add a summary of the project to the text edit.
         Display project memo, and code, attribute, journal, files frequencies.
         Also detect and display bad links to linked files. """

        if self.app.conn is None:
            return
        cur = self.app.conn.cursor()
        cur.execute("select databaseversion, date, memo, about, bookmarkfile,bookmarkpos from project")
        result = cur.fetchall()[-1]
        self.project['databaseversion'] = result[0]
        self.project['date'] = result[1]
        self.project['memo'] = result[2]
        self.ui.textEdit.append("\n")
        self.ui.textEdit.append("<h1>" + _("Project summary") + "</h1>")
        msg = _("Date time now: ") + datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M") + "\n"
        msg += self.app.project_name + "\n"
        msg += f'{_("Project path: ")}{self.app.project_path}\n'
        msg += f"{_('Project date: ')}{self.project['date']}\n"
        sql = "select memo from project"
        cur.execute(sql)
        memo_res = cur.fetchone()
        if memo_res[0] != "":
            msg += _("Project memo: ") + f"\n---------------------\n{memo_res[0]}\n---------------------\n"
        sql = "select count(id) from source"
        cur.execute(sql)
        files_res = cur.fetchone()
        text_res = self.app.get_text_filenames()
        image_res = self.app.get_image_filenames()
        av_res = self.app.get_av_filenames()
        msg += _("Files: ") + f"{files_res[0]}. Text files: {len(text_res)}. Image files: {len(image_res)}. AV files: {len(av_res)}\n"
        sql = "select count(caseid) from cases"
        cur.execute(sql)
        res = cur.fetchone()
        msg += _("Cases: ") + f"{res[0]}\n"
        sql = "select count(catid) from code_cat"
        cur.execute(sql)
        res = cur.fetchone()
        msg += f'{_("Code categories: ")}{res[0]}\n'
        sql = "select count(cid) from code_name"
        cur.execute(sql)
        res = cur.fetchone()
        msg += f'{_("Codes: ")}{res[0]}\n'
        sql = "select count(name) from attribute_type"
        cur.execute(sql)
        res = cur.fetchone()
        msg += f'{_("Attributes: ")}{res[0]}\n'
        sql = "select count(jid) from journal"
        cur.execute(sql)
        res = cur.fetchone()
        msg += f'{_("Journals: ")}{res[0]}\n'
        cur.execute("select name from source where id=?", [result[4]])
        bookmark_filename = cur.fetchone()
        if bookmark_filename is not None and result[5] is not None:
            msg += f"\nText Bookmark: {bookmark_filename[0]}"
            msg += f", position: {result[5]}\n"
        if platform.system() == "Windows":
            msg += "\n" + _("Directory (folder) paths / represents \\")
        self.ui.textEdit.append(msg)
        bad_links = self.app.check_bad_file_links()
        if bad_links:
            span = '<span style="color:red">'
            self.ui.textEdit.append(span + _("Bad links to files") + "</span>")
            for lnk in bad_links:
                self.ui.textEdit.append(span + lnk['name'] + "   " + lnk['mediapath'] + '</span>')
            self.ui.actionManage_bad_links_to_files.setEnabled(True)
        else:
            self.ui.actionManage_bad_links_to_files.setEnabled(False)
        self.ui.textEdit.append("\n")
        self.ui.tabWidget.setCurrentWidget(self.ui.tab_action_log)
        self.ui.textEdit.verticalScrollBar().setValue(self.ui.textEdit.verticalScrollBar().maximum())

    def close_project(self):
        """ Close an open project.
        Remove widgets from tabs, clear dialog list. Close app connection.
        Delete old backups. Hide menu options. """

        self.journal_display = None
        # Remove widgets from each tab
        contents = self.ui.tab_reports.layout()
        if contents:
            for i in reversed(range(contents.count())):
                contents.itemAt(i).widget().close()
                contents.itemAt(i).widget().setParent(None)
        contents = self.ui.tab_coding.layout()
        if contents:
            for i in reversed(range(contents.count())):
                contents.itemAt(i).widget().close()
                contents.itemAt(i).widget().setParent(None)
        contents = self.ui.tab_manage.layout()
        if contents:
            for i in reversed(range(contents.count())):
                contents.itemAt(i).widget().close()
                contents.itemAt(i).widget().setParent(None)
        # Added if statement for the first opening of QualCoder. Looks odd closing a project that is not there.
        if self.app.project_name != "":
            self.ui.textEdit.append(_("Closing project: ") + self.app.project_name)
            self.ui.textEdit.append("========\n")
            self.app.append_recent_project(self.app.project_path)
        # AI
        self.ai_chat_window.close()
        self.app.ai.close()
        
        if self.app.conn is not None:
            try:
                self.app.conn.commit()
                self.app.conn.close()
            except Exception as e_:  # TODO add specific exception
                print(e_)
                logger.warning(e_)
                self.app.conn = None
        self.stop_heartbeat(wait=True)
        self.delete_backup_folders()
        self.fill_recent_projects_menu_actions()
        self.app.conn = None
        self.app.project_path = ""
        self.app.project_name = ""
        self.app.delete_backup_path_name = ""
        self.app.delete_backup = True
        self.project = {"databaseversion": "", "date": "", "memo": "", "about": ""}
        self.hide_menu_options()
        self.setWindowTitle("QualCoder")
        self.app.write_config_ini(self.app.settings, self.app.ai_models)
        self.ui.tabWidget.setCurrentWidget(self.ui.tab_action_log)
        self.ui.textEdit.verticalScrollBar().setValue(self.ui.textEdit.verticalScrollBar().maximum())

    def delete_backup_folders(self):
        """ Delete the most current backup created on opening a project,
        providing the project was not changed in any way.
        Delete the oldest backups if more than BACKUP_NUM are created.
        Backup name format: directories/projectname_BKUP_yyyymmdd_hh.qda
        Requires: self.settings['backup_num'] """

        if self.app.project_path == "" or not os.path.exists(self.app.project_path):
            return
        if self.app.delete_backup_path_name != "" and self.app.delete_backup:
            try:
                shutil.rmtree(self.app.delete_backup_path_name)
            except Exception as err:
                print(str(err))
                logger.warning(str(err))
        # Get a list of backup folders for current project
        parts = self.app.project_path.split('/')
        project_name_and_suffix = parts[-1]
        directory = self.app.project_path[0:-len(project_name_and_suffix)]
        project_name = project_name_and_suffix[:-4]
        project_name_and_bkup = project_name + "_BKUP_"
        lenname = len(project_name_and_bkup)
        files_folders = os.listdir(directory)
        backups = []
        for f_ in files_folders:
            if f_[0:lenname] == project_name_and_bkup and f_[-4:] == ".qda":
                backups.append(f_)
        # Sort newest to oldest, and remove any that are more than BACKUP_NUM position in the list
        backups.sort(reverse=True)
        to_remove = []
        if len(backups) > self.app.settings['backup_num']:
            to_remove = backups[self.app.settings['backup_num']:]
        if not to_remove:
            return
        for f_ in to_remove:
            try:
                shutil.rmtree(directory + f_)
                self.ui.textEdit.append(_("Deleting: ") + directory + f_)
            except Exception as err:
                print(str(err))
                logger.warning(str(err))

    # AI Menu Actions
    def ai_setup_wizard(self):
        """Action triggered by AI Setup Wizard menu item or at the first start of QualCoder."""
        if self.app.settings['ai_enable'] == 'True':
            msg = _('The AI is setup and enabled, so there is nothing to do here. '
                    'Go to AI > settings to change the current model or other settings.')
            Message(self.app, _('AI Setup Wizard'), msg).exec() 
            return
        self.ui.textEdit.append(_('AI: Setup Wizard'))
        QtWidgets.QApplication.processEvents()  # update ui
        self.app.ai.init_llm(self, rebuild_vectorstore=True, enable_ai=True)
        self.ui.textEdit.append(_('AI: Setup Wizard finished'))
        
    def ai_settings(self):
        """Action triggered by AI Settings menu item."""
        self.change_settings(section='AI')

    def ai_rebuild_memory(self):
        """Action triggered by AI Rebuild Internal Memory menu item."""
        if self.app.settings['ai_enable'] != 'True':
            msg = _('Please enable the AI first and set it in Settings.')
            Message(self.app, _('Rebuild AI Memory'), msg).exec() 
            return
        if not self.app.ai.is_ready():
            msg = _('The AI is busy or not set up correctly.')
            Message(self.app, _('Rebuild AI Memory'), msg).exec()
            return 
        
        msg = _('This will re-read all of your empirical documents, which may take some time. Do you want to continue?')
        mb = QtWidgets.QMessageBox(self)
        mb.setWindowTitle(_('Rebuild AI Memory'))
        mb.setText(msg)
        mb.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok |
                            QtWidgets.QMessageBox.StandardButton.Abort)
        mb.setStyleSheet(f'* {{font-size: {self.app.settings["fontsize"]}pt}}')
        if mb.exec() == QtWidgets.QMessageBox.StandardButton.Ok: 
            self.ui.tabWidget.setCurrentIndex(0)  # Show action log
            self.app.ai.sources_vectorstore.init_vectorstore(rebuild=True)
    
    def ai_prompts(self):
        """Action triggered by AI Prompts menu item."""
        DialogAiEditPrompts(self.app).exec()

    def ai_go_chat(self):
        """Action triggered by AI Chat menu item."""
        if self.app.settings['ai_enable'] != 'True':
            msg = _('Please enable the AI first and set it up in Settings.')
            Message(self.app, _('Ai Chat'), msg).exec() 
            return
        self.ui.tabWidget.setCurrentWidget(self.ui.tab_ai_chat) 

    def ai_go_search(self):
        """Action triggered by AI Search and Coding menu item."""
        if self.app.settings['ai_enable'] != 'True':
            msg = _('Please enable the AI first and set it up in Settings.')
            Message(self.app, _('Rebuild AI Memory'), msg).exec() 
            return
        self.text_coding(task='ai_search')

    def get_latest_github_release(self):
        """ Get latest github release.
        https://stackoverflow.com/questions/24987542/is-there-a-link-to-github-for-downloading-a-file-in-the-latest-release-of-a-repo
        Dated May 2018

        Some issues on some platforms, so all in try except clause
        """

        self.ui.textEdit.append(_("This version: ") + qualcoder_version)
        try:
            _json = json.loads(urllib.request.urlopen(urllib.request.Request(
                'https://api.github.com/repos/ccbogel/QualCoder/releases/latest',
                headers={'Accept': 'application/vnd.github.v3+json'},
            )).read())
            if _json['name'] > qualcoder_version:
                html = '<span style="color:red">' + _("Newer release available: ") + _json['name'] + '</span>'
                self.ui.textEdit.append(html)
                html = f'<span style="color:red">{_json["html_url"]}</span><br />'
                self.ui.textEdit.append(html)
            else:
                self.ui.textEdit.append(_("Latest Release: ") + _json['name'])
                self.ui.textEdit.append(_json['html_url'] + "\n")
        except Exception as err:
            print(err)
            logger.warning(str(err))


def gui():
    app = QtWidgets.QApplication(sys.argv)    
    qual_app = App()
    settings, ai_models = qual_app.load_settings()
    project_path = qual_app.get_most_recent_projectpath()
    #QtGui.QFontDatabase.addApplicationFont("GUI/NotoSans-hinted/NotoSans-Regular.ttf")  # OLD
    #QtGui.QFontDatabase.addApplicationFont("GUI/NotoSans-hinted/NotoSans-Bold.ttf")  # OLD
    stylesheet = qual_app.merge_settings_with_default_stylesheet(settings)
    app.setStyleSheet(stylesheet)
    if sys.platform != 'darwin':
        qualcoder32_icon = b'iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAHlHpUWHRSYXcgcHJvZmlsZSB0eXBlIGV4aWYAAHja7ZdZkuS2DkX/uQovQRzAYTkkQUZ4B2/5PqAys7Kq2u52vP50KlKiOIDgvZjk1v/+3O4PfkHy5ZKUmlvOF7/UUgudRr3uXzt3f6VzP7/wGOL9U797DQS6Is94v5b+mN/pl48Fzz38+Nzv6mMk1Iegx8BTYLSdbTd9V5L+cPf79BDU1t3IrZZ3VcdD1fmYeFR5/GO5T/gUYu/uvSMVUFJhVgxhRR+vc6+3BtH+Pnb+dr9iZh5zTrs5HgGJtyYA8ul4z+d1vQP0CeRny31F/9X6An7oj/74Bcv8wIjGDwe8/Bj8A/HbxvGlUfg8MNuL4W8g761173WfrqcMovlhUZd7omNrmDiAPJ5lmavwF9rlXO2yTfo1IUeveQ2u6ZsPIL6dT15999uv85x+omIKKxSeIUyIsr4aS2hhRuMp2eV3KLFFjRWyZlguRrrDSxd/9m1nv+krO6tnavAI8yz528v90+C/udze0yDyV31hhV7BLBc1jDm7MwtC/H7wJgfg5/Wg/3qzH0wVBuXAXDlgv8YtYoj/sK14eI7ME563V3hX9CEAiNhbUAYXSP7KPorP/iohFO/BsUJQR/MQUxgw4EWComRIEW9xJdRge7Om+DM3SMjBuolNECExxwI3LXbISkmwn5IqNtQlShKRLEWqkyY9x5yy5JxLtiDXSyypSMmllFpa6TXWVKXmWmqtrfYWWiQGSsuttNpa6z24zkYdWZ35nZ4RRhxpyMijjDra6BPzmWnKzLPMOtvsGjQqYUKzFq3atC/vFpFipSUrr7LqaqtvbG3HnbbsvMuuu+3+Yu3B6rfrX7DmH6yFw5TNKy/W6HWlPEV4CydinMFYSB7GizGAQQfj7Ko+pWDMGWdXCziFBJQU48apN8agMC0fZPsXdx/M/RJvTuov8RZ+xpwz6n4Hcw7qvvP2A9bU8tw8jN1eaJheEe9jTg/V8b8ubv/v8z9Bv1MQpNbL7ITGmISkmaxjdS7e3KQO6cYhS8b0637BKAaXRJMTl/a+WhiLnL5zshk9r9ZkFZVZNI+rO5lb02o91rIxUsV8pE8WxIzkLtkvZcKu61q689hotTo+ERrOsQcmFzE4wkjGFWREpJckoaSOYMGQZfe2ppexZZlj9hFxF5a1Varfa5d1FZT2MqOW7IbMESqpOPZy0b2TeNyyUetY4/r0xPpjsoPtFtZnGAF7DOHkVjvuZt27z96yQZMmo2CBzwjD6zqLaIWhAcSVFyXugGV2XaQQLHeKukLLo2rfKfe1JY62lKbu7hvHpqoUEGx75E0i311L86t4GwlCFlER3wf+ymHJzEp9kI7CA9LYvKxhqjRKj5WIWnOWoSqDmAyg2XhZXZzpNaVrMr0GmUoOGK3NddCZdiYsh6riUL/9sLO9zrj61YfKIoskOFl9foEWYWlYq7ShZTYvhAstfjB9+3a2A3dwqRDstyMMqo3lpKTO3qd+SCtxyBL+q0nqg8AnkXDpVRKhfM0FeuvCWnITl4lwpZcStae1PBEPWzOLaokQCjRpt8mCbk6ChXLACKQISD3mqy+hE7ycbz2lZub5UnY0+6xQAw1dtVqK/2pR357uoBBAYWDwBSunRjNxt1iPWYsdpnAO2elHcjiMrOhYTqGAJ8C1TpztWqN7zJIjatglrtLMLKu5ntzGQw2iPW7VPQu1qV9g6dYUo7umVTAQw3ssMgTGx7vtstDmMnuo9Y2qVWRfttds6D0KRyttSz4qmgnIwqezxQ6VDL4RIBsGM74BIzsGBEUkRozYXaWGt502SJyG2k69/BO+n8S6/VjPY4d5oI/6FPx3T2xPJoZ32FDzQnUAQKTbxfpSMHsmGuqtOlOUQoSK+mxQ9UNzvGmz8FbButzPNn+trQMLS1rC0cOXD6lUEbM7xZXZL1cpyXzu4V8EPW+c5Vt/k4iZQRPkMz51P60I/REqDg3n09/kgmpjjgi7yP4fdrkWR4HP0lQt+nyH246Gv5Y2NTdfS/RD+Rac+6QBi5CzElSxz7hyxlKADm0tkMZACNQ+ic+EIncdt8QCKy4thnagSprDLMrqEZCZ8tlpKkqZLxkhVDEcb3h1IEE0fXed1iz+tDv+tHkgqfrNcBRELtsq2Qwhi+T8Ja12DpDHpOCivovNjoa2jehDQJ/hJIhE1CaW6MxxdpPuSGlJxyC6gEgpTdR2J3KUllUnVVabo9U7tiaqVfqxwPbOph3WTQs6LwDUwhHdpIBzTCWPPbPYSdRoWvqo5Vtp4E4DTE9OOImeNEeu33VaeCd0rkkNGU+uGAVoOsUgOZivxJFXv0HD+4mAJ21Qa2TcRy00Dr4ww7DdSduEaQQTc3IIY1Oj5novtvr5w/JfLlKiiIb75BEUKtxZLJiH35ksQ1LDCgTa+8Y8y5i3tV68OOoAJaTY+sBa8yYDKVnamcfF9NimP/KuYfKwjXkgnOQTA1UKrHEjx2r2aVAHNyI+SVQvy9RrUenkSIWRlaObv0KYeSWFOoWWWFBOw5PDh4u7NlzrZCvzCMjlRiQlkVE6PXIqH9o/Kevcbykg/xP0i4IiXz6NCPcXkG3wBnlTA/kAAAGFaUNDUElDQyBwcm9maWxlAAB4nH2RPUjDQBzFX1Nr/ag4WFDEIUN1siAq4qhVKEKFUCu06mBy6YfQpCFJcXEUXAsOfixWHVycdXVwFQTBDxA3NydFFynxf0mhRawHx/14d+9x9w4QqkWmWW1jgKbbZjIeE9OZFTH4im4E0I9OtMvMMmYlKYGW4+sePr7eRXlW63N/jh41azHAJxLPMMO0ideJpzZtg/M+cZgVZJX4nHjUpAsSP3Jd8fiNc95lgWeGzVRyjjhMLOabWGliVjA14kniiKrplC+kPVY5b3HWimVWvyd/YSirLy9xneYQ4ljAIiSIUFDGBoqwEaVVJ8VCkvZjLfyDrl8il0KuDTByzKMEDbLrB/+D391auYlxLykUAwIvjvMxDAR3gVrFcb6PHad2AvifgSu94S9VgelP0isNLXIE9G4DF9cNTdkDLneAgSdDNmVX8tMUcjng/Yy+KQP03QJdq15v9X2cPgAp6ipxAxwcAiN5yl5r8e6O5t7+PVPv7wfz2XJ065JIMgAAF41pVFh0WE1MOmNvbS5hZG9iZS54bXAAAAAAADw/eHBhY2tldCBiZWdpbj0i77u/IiBpZD0iVzVNME1wQ2VoaUh6cmVTek5UY3prYzlkIj8+Cjx4OnhtcG1ldGEgeG1sbnM6eD0iYWRvYmU6bnM6bWV0YS8iIHg6eG1wdGs9IlhNUCBDb3JlIDQuNC4wLUV4aXYyIj4KIDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+CiAgPHJkZjpEZXNjcmlwdGlvbiByZGY6YWJvdXQ9IiIKICAgIHhtbG5zOmlwdGNFeHQ9Imh0dHA6Ly9pcHRjLm9yZy9zdGQvSXB0YzR4bXBFeHQvMjAwOC0wMi0yOS8iCiAgICB4bWxuczp4bXBNTT0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL21tLyIKICAgIHhtbG5zOnN0RXZ0PSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VFdmVudCMiCiAgICB4bWxuczpzdFJlZj0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wL3NUeXBlL1Jlc291cmNlUmVmIyIKICAgIHhtbG5zOnBsdXM9Imh0dHA6Ly9ucy51c2VwbHVzLm9yZy9sZGYveG1wLzEuMC8iCiAgICB4bWxuczpHSU1QPSJodHRwOi8vd3d3LmdpbXAub3JnL3htcC8iCiAgICB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iCiAgICB4bWxuczpleGlmPSJodHRwOi8vbnMuYWRvYmUuY29tL2V4aWYvMS4wLyIKICAgIHhtbG5zOnBob3Rvc2hvcD0iaHR0cDovL25zLmFkb2JlLmNvbS9waG90b3Nob3AvMS4wLyIKICAgIHhtbG5zOnRpZmY9Imh0dHA6Ly9ucy5hZG9iZS5jb20vdGlmZi8xLjAvIgogICAgeG1sbnM6eG1wPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvIgogICB4bXBNTTpEb2N1bWVudElEPSJhZG9iZTpkb2NpZDpwaG90b3Nob3A6ZWU1YjRlNWUtNGU1MS02NzRkLTk1ZDItNTIwMzA3YWQ0MWFhIgogICB4bXBNTTpJbnN0YW5jZUlEPSJ4bXAuaWlkOmJjMTRjZDA2LTQzYzItNDBhOS1iOGExLWY3NjZjMGI0NzVkMSIKICAgeG1wTU06T3JpZ2luYWxEb2N1bWVudElEPSJ4bXAuZGlkOmE1ZTMzYzY4LTAyNGEtNzk0MS05N2VmLWZhN2NjODExODdlOSIKICAgR0lNUDpBUEk9IjIuMCIKICAgR0lNUDpQbGF0Zm9ybT0iTGludXgiCiAgIEdJTVA6VGltZVN0YW1wPSIxNjM2MTUzNzY5NTY3OTIyIgogICBHSU1QOlZlcnNpb249IjIuMTAuMTgiCiAgIGRjOkZvcm1hdD0iaW1hZ2UvcG5nIgogICBleGlmOlBpeGVsWERpbWVuc2lvbj0iNTEyIgogICBleGlmOlBpeGVsWURpbWVuc2lvbj0iNTEyIgogICBwaG90b3Nob3A6Q29sb3JNb2RlPSIzIgogICB0aWZmOk9yaWVudGF0aW9uPSIxIgogICB0aWZmOlJlc29sdXRpb25Vbml0PSIyIgogICB0aWZmOlhSZXNvbHV0aW9uPSI3MjAwMDAvMTAwMDAiCiAgIHRpZmY6WVJlc29sdXRpb249IjcyMDAwMC8xMDAwMCIKICAgeG1wOkNyZWF0ZURhdGU9IjIwMjEtMTEtMDVUMTE6MzU6NDkrMDE6MDAiCiAgIHhtcDpDcmVhdG9yVG9vbD0iR0lNUCAyLjEwIgogICB4bXA6TWV0YWRhdGFEYXRlPSIyMDIxLTExLTA1VDEyOjM0OjMxKzAxOjAwIgogICB4bXA6TW9kaWZ5RGF0ZT0iMjAyMS0xMS0wNVQxMjozNDozMSswMTowMCI+CiAgIDxpcHRjRXh0OkxvY2F0aW9uQ3JlYXRlZD4KICAgIDxyZGY6QmFnLz4KICAgPC9pcHRjRXh0OkxvY2F0aW9uQ3JlYXRlZD4KICAgPGlwdGNFeHQ6TG9jYXRpb25TaG93bj4KICAgIDxyZGY6QmFnLz4KICAgPC9pcHRjRXh0OkxvY2F0aW9uU2hvd24+CiAgIDxpcHRjRXh0OkFydHdvcmtPck9iamVjdD4KICAgIDxyZGY6QmFnLz4KICAgPC9pcHRjRXh0OkFydHdvcmtPck9iamVjdD4KICAgPGlwdGNFeHQ6UmVnaXN0cnlJZD4KICAgIDxyZGY6QmFnLz4KICAgPC9pcHRjRXh0OlJlZ2lzdHJ5SWQ+CiAgIDx4bXBNTTpIaXN0b3J5PgogICAgPHJkZjpTZXE+CiAgICAgPHJkZjpsaQogICAgICBzdEV2dDphY3Rpb249ImNyZWF0ZWQiCiAgICAgIHN0RXZ0Omluc3RhbmNlSUQ9InhtcC5paWQ6YTVlMzNjNjgtMDI0YS03OTQxLTk3ZWYtZmE3Y2M4MTE4N2U5IgogICAgICBzdEV2dDpzb2Z0d2FyZUFnZW50PSJBZG9iZSBQaG90b3Nob3AgQ0MgKFdpbmRvd3MpIgogICAgICBzdEV2dDp3aGVuPSIyMDIxLTExLTA1VDExOjM1OjQ5KzAxOjAwIi8+CiAgICAgPHJkZjpsaQogICAgICBzdEV2dDphY3Rpb249ImNvbnZlcnRlZCIKICAgICAgc3RFdnQ6cGFyYW1ldGVycz0iZnJvbSBpbWFnZS9wbmcgdG8gYXBwbGljYXRpb24vdm5kLmFkb2JlLnBob3Rvc2hvcCIvPgogICAgIDxyZGY6bGkKICAgICAgc3RFdnQ6YWN0aW9uPSJzYXZlZCIKICAgICAgc3RFdnQ6Y2hhbmdlZD0iLyIKICAgICAgc3RFdnQ6aW5zdGFuY2VJRD0ieG1wLmlpZDo0NTJhODhhNi1iYWVjLTgzNDktODZjNy0xMWM0NWVmY2IyNDEiCiAgICAgIHN0RXZ0OnNvZnR3YXJlQWdlbnQ9IkFkb2JlIFBob3Rvc2hvcCBDQyAoV2luZG93cykiCiAgICAgIHN0RXZ0OndoZW49IjIwMjEtMTEtMDVUMTI6MjQ6MTMrMDE6MDAiLz4KICAgICA8cmRmOmxpCiAgICAgIHN0RXZ0OmFjdGlvbj0ic2F2ZWQiCiAgICAgIHN0RXZ0OmNoYW5nZWQ9Ii8iCiAgICAgIHN0RXZ0Omluc3RhbmNlSUQ9InhtcC5paWQ6MDU3OGM4ZTMtYjllNC03ZjRiLWEyOGMtYWExNmYzOGJmZjA5IgogICAgICBzdEV2dDpzb2Z0d2FyZUFnZW50PSJBZG9iZSBQaG90b3Nob3AgQ0MgKFdpbmRvd3MpIgogICAgICBzdEV2dDp3aGVuPSIyMDIxLTExLTA1VDEyOjM0OjMxKzAxOjAwIi8+CiAgICAgPHJkZjpsaQogICAgICBzdEV2dDphY3Rpb249ImNvbnZlcnRlZCIKICAgICAgc3RFdnQ6cGFyYW1ldGVycz0iZnJvbSBhcHBsaWNhdGlvbi92bmQuYWRvYmUucGhvdG9zaG9wIHRvIGltYWdlL3BuZyIvPgogICAgIDxyZGY6bGkKICAgICAgc3RFdnQ6YWN0aW9uPSJkZXJpdmVkIgogICAgICBzdEV2dDpwYXJhbWV0ZXJzPSJjb252ZXJ0ZWQgZnJvbSBhcHBsaWNhdGlvbi92bmQuYWRvYmUucGhvdG9zaG9wIHRvIGltYWdlL3BuZyIvPgogICAgIDxyZGY6bGkKICAgICAgc3RFdnQ6YWN0aW9uPSJzYXZlZCIKICAgICAgc3RFdnQ6Y2hhbmdlZD0iLyIKICAgICAgc3RFdnQ6aW5zdGFuY2VJRD0ieG1wLmlpZDo1ZGM3ZDg0Ny1kNGRhLTk1NGUtYTQ0NC00NzhmOGVhZjY3MDEiCiAgICAgIHN0RXZ0OnNvZnR3YXJlQWdlbnQ9IkFkb2JlIFBob3Rvc2hvcCBDQyAoV2luZG93cykiCiAgICAgIHN0RXZ0OndoZW49IjIwMjEtMTEtMDVUMTI6MzQ6MzErMDE6MDAiLz4KICAgICA8cmRmOmxpCiAgICAgIHN0RXZ0OmFjdGlvbj0ic2F2ZWQiCiAgICAgIHN0RXZ0OmNoYW5nZWQ9Ii8iCiAgICAgIHN0RXZ0Omluc3RhbmNlSUQ9InhtcC5paWQ6YzJlMmQyMmEtZWUyNy00MTEzLTg0OTQtYTRhZDYzMjhkOTBmIgogICAgICBzdEV2dDpzb2Z0d2FyZUFnZW50PSJHaW1wIDIuMTAgKExpbnV4KSIKICAgICAgc3RFdnQ6d2hlbj0iKzExOjAwIi8+CiAgICA8L3JkZjpTZXE+CiAgIDwveG1wTU06SGlzdG9yeT4KICAgPHhtcE1NOkRlcml2ZWRGcm9tCiAgICBzdFJlZjpkb2N1bWVudElEPSJhZG9iZTpkb2NpZDpwaG90b3Nob3A6N2YxMDM5N2ItZTBmZi05NzRlLThkMjktY2VmZDU3MGFiNDFiIgogICAgc3RSZWY6aW5zdGFuY2VJRD0ieG1wLmlpZDowNTc4YzhlMy1iOWU0LTdmNGItYTI4Yy1hYTE2ZjM4YmZmMDkiCiAgICBzdFJlZjpvcmlnaW5hbERvY3VtZW50SUQ9InhtcC5kaWQ6YTVlMzNjNjgtMDI0YS03OTQxLTk3ZWYtZmE3Y2M4MTE4N2U5Ii8+CiAgIDxwbHVzOkltYWdlU3VwcGxpZXI+CiAgICA8cmRmOlNlcS8+CiAgIDwvcGx1czpJbWFnZVN1cHBsaWVyPgogICA8cGx1czpJbWFnZUNyZWF0b3I+CiAgICA8cmRmOlNlcS8+CiAgIDwvcGx1czpJbWFnZUNyZWF0b3I+CiAgIDxwbHVzOkNvcHlyaWdodE93bmVyPgogICAgPHJkZjpTZXEvPgogICA8L3BsdXM6Q29weXJpZ2h0T3duZXI+CiAgIDxwbHVzOkxpY2Vuc29yPgogICAgPHJkZjpTZXEvPgogICA8L3BsdXM6TGljZW5zb3I+CiAgPC9yZGY6RGVzY3JpcHRpb24+CiA8L3JkZjpSREY+CjwveDp4bXBtZXRhPgogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIAogICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgCiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgICAgICAgICAgICAgICAgCjw/eHBhY2tldCBlbmQ9InciPz7mcyShAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAB3RJTUUH5QsFFwkdYf6D1wAAA2NJREFUSMftVl9IU1EYP7fd1VX8y8r/yMAtcoWDwGES5EAoTGeUkFGSrD0k+rKRCQ7qRV+ESkEMQXQPqSAo+K8xZuGQ8s9Q9CpqugkhUyduNtfm5p07PUyOh+t0+iC9+OM83Hu+7/f9zvnu+b5zCQghOE9cAueMC4H/L0AGnTWZTLOzszMzM16vFwDA5XLFYnFGRoZAICAIwu/bt61s2pY3HSvbft8+ACCKHxubdvXa9UQuxWWFIljH1GQyNTQ0NDY2BhVWKBQvH7/wfLV71z1HrZwoMu2ZKE164xLJCS4wODiYn58fctfK269z+Hc5RPD0Rt6MkbzJoSLD2AJ9fX2FhYXILzMzUy6XJycnEwSxtrbW0dFhMBiQtUL86lFOQVx2EhnG9fv8mxNr7mUnsoYLI7PVuVciKAAAgBBCCBcXF/FVaDSa3d1diGFvb0+r1eI+BoMBd9iYt+jLewaedATG6KdvgXkAIfT5fAqFAjF7enrgMZicnERuEonE7XbjVve2C9ewTP8+EJibm0M0lUrl9/vh8Whvb0fOQ0NDLKt1wYIERmp1BwLNzc2IMzU1BU+E3W5HzlVVVTAUAIRQLpcjjtPpDMnB8xnSmQQAtLa2IoLD4TAajVarlWEYiqIEAkF6ejpFUfjnjY+PR882m43H452hklNSUlgzEomkpqZGKpWSJIlWfVhHBBGiaiCExcXFIYtLrVbv7OwEdi2TyU6fIgAhbGpqQgSRSFRXV9fV1dXZ2alSqXCNkpKS9fX1hYUFNFNZWXkqgenpacSprq7GzVtbW/X19Xi6SktL0ater2eF+2Ox//wwFBhTmh8HAgzD4Fnq7e1l0fr7+48mLSsri1VoXpdnWD2A6mBl5NeBAIRwfn4eJ7e0tLhcLpys0+lYAuPj47iDc9NheDeIon9/2+fzMhDCw2bX3d1dVFSE+Hw+X6lU8vl8DodjsVja2trGxsZwgfLyctmDgoSkhPC/lx3Ltg3t6mHfjiTv1OZGJ8Wy2zWroZ4SXx5+jqGiDw9+NFfyXhqbygtyZcpksqWlpYqKiuNilZWVDQ8Pn3CsE/NS733MQ9GD3GgBmM1mmqZpmvZ4PPiVKRQKAQAMw9A0bRydMC+ZV/Xm5/efxgkSeKL4hFvJEXFRIa7Mi9+WC4Gz4x8imSOgwBMa1AAAAABJRU5ErkJggg=='
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(qualcoder32_icon), "png")
        app.setWindowIcon(QtGui.QIcon(pm))

    # Use two character language setting
    lang = settings.get('language', 'en')
    # Test for pyinstall data files
    locale_dir = os.path.join(path, 'locale')
    # Need to get the external data directory for PyInstaller
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        ext_data_dir = sys._MEIPASS
        locale_dir = os.path.join(ext_data_dir, 'qualcoder')
        locale_dir = os.path.join(locale_dir, 'locale')
        # locale_dir = os.path.join(locale_dir, lang)
        # locale_dir = os.path.join(locale_dir, 'LC_MESSAGES')
    # print("LISTDIR: ", os.listdir(locale_dir))
    install_language(lang)  # Install language files on every start, so updates are reflected
    # getlang = gettext.translation('en', localedir=locale_dir, languages=['en'])
    translator = gettext.translation(domain='default', localedir=locale_dir, fallback=True)
    if lang in ["de", "es", "fr", "it", "pt"]:
        # qt translator applies to ui designed GUI widgets only
        # qt_locale_dir = os.path.join(locale_dir, lang)
        # qt_locale_file = os.path.join(qt_locale_dir, "app_" + lang + ".qm")
        # print("qt qm translation file: ", qt_locale_file)
        qt_translator = QtCore.QTranslator()
        # qt_translator.load(qt_locale_file)
        ''' Below for pyinstaller and obtaining app_lang.qm data file from .qualcoder folder
        A solution to this error [Errno 13] Permission denied:
        Replace 'lang' with the short language name, e.g. app_de.qm '''
        if qt_translator.isEmpty():
            print("trying to load translation qm file from .qualcoder folder")
            qm = os.path.join(home, '.qualcoder')
            qm = os.path.join(qm, f"app_{lang}.qm")
            print("qm file located at: ", qm)
            qt_translator.load(qm)
            '''if qt_translator.isEmpty():
                print(f"Installing app_{lang}.qm to .qualcoder folder")
                install_language(lang)
                qt_translator.load(qm)'''
        app.installTranslator(qt_translator)
        '''Below for pyinstaller and obtaining mo data file from .qualcoder folder
        A solution to this [Errno 13] Permission denied:
        Must have the folder lang/LC_MESSAGES/lang.mo  in the .qualcoder folder
        Replace 'lang' with the language short name e.g. de, el, es ...
        '''
        try:
            translator = gettext.translation(lang, localedir=locale_dir, languages=[lang])
            print("locale directory for python translations: ", locale_dir)
        except Exception as err:
            print("Error accessing python translations mo file\n", err)
            print("Locale directory for python translations: ", locale_dir)
            try:
                print(f"Trying folder: home/.qualcoder/{lang}/LC_MESSAGES/{lang}.mo")
                mo_dir = os.path.join(home, '.qualcoder')
                translator = gettext.translation(lang, localedir=mo_dir, languages=[lang])
            except Exception as err2:
                print(f"No {lang}.mo translation file loaded", err2)
    translator.install()
    # Check DroidSandMono installed  - for wordcloud
    install_droid_sans_mono()
    ex = MainWindow(qual_app)
    if project_path:
        split_ = project_path.split("|")
        proj_path = ""
        # Only the path - older and rarer format - legacy
        if len(split_) == 1:
            proj_path = split_[0]
        # Newer datetime | path
        if len(split_) == 2:
            proj_path = split_[1]
        ex.open_project(path_=proj_path)

    sys.exit(app.exec())


def install_language(lang):
    """ Mainly for pyinstaller on Windows, as cannot access language data files.
    So, recreate them from base64 data into home/.qualcoder folder.
    Install Qt translation file into folder .qualcoder/app_lang.qm
    Install poedit.mo file into folder .qualcoder/lang/LC_MESSAGES/lang.mo
    """

    qm = os.path.join(home, '.qualcoder')
    qm = os.path.join(qm, 'app_' + lang + '.qm')
    qm_data = None
    mo_data = None
    if lang == "de":
        qm_data = de_qm
        mo_data = de_mo
    if lang == "es":
        qm_data = es_qm
        mo_data = es_mo
    if lang == "fr":
        qm_data = fr_qm
        mo_data = fr_mo
    if lang == "it":
        qm_data = it_qm
        mo_data = it_mo
    if lang == "pt":
        qm_data = pt_qm
        mo_data = pt_mo
    if qm_data is None or mo_data is None:
        return
    with open(qm, 'wb') as file_:
        decoded_data = base64.decodebytes(qm_data)
        file_.write(decoded_data)
    mo_path = os.path.join(home, '.qualcoder')
    mo_path = os.path.join(mo_path, lang)
    if not os.path.exists(mo_path):
        os.mkdir(mo_path)
    mo_path = os.path.join(mo_path, "LC_MESSAGES")
    if not os.path.exists(mo_path):
        os.mkdir(mo_path)
    mo = os.path.join(mo_path, lang + ".mo")
    with open(mo, 'wb') as file_:
        decoded_data = base64.decodebytes(mo_data)
        file_.write(decoded_data)


def install_droid_sans_mono():
    """ Install DroidSandMono ttf font for wordclouds into .qualcoder folder """

    qc_folder = os.path.join(home, '.qualcoder', 'DroidSansMono.ttf')
    with open(qc_folder, 'wb') as file_:
        decoded_data = base64.decodebytes(DroidSansMono)
        file_.write(decoded_data)


if __name__ == "__main__":
     # Pyinstaller fix
    multiprocessing.freeze_support()
    gui()
