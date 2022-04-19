#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Copyright (c) 2022 Colin Curtain

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
"""

import base64
import configparser
import datetime
import gettext
import json  # To get latest Github release information
import logging
from logging.handlers import RotatingFileHandler
import os
import platform
import shutil
import sys
import sqlite3
import traceback
import urllib.request
import webbrowser
from copy import copy

from PyQt6 import QtCore, QtGui, QtWidgets

from qualcoder.attributes import DialogManageAttributes
from qualcoder.cases import DialogCases
from qualcoder.codebook import Codebook
from qualcoder.code_text import DialogCodeText
from qualcoder.code_by_case import DialogCodeByCase
from qualcoder.GUI.base64_helper import *
from qualcoder.GUI.ui_main import Ui_MainWindow
from qualcoder.helpers import Message
from qualcoder.import_survey import DialogImportSurvey
from qualcoder.information import DialogInformation
from qualcoder.locale.base64_lang_helper import *
from qualcoder.journals import DialogJournals
from qualcoder.manage_files import DialogManageFiles
from qualcoder.manage_links import DialogManageLinks
from qualcoder.memo import DialogMemo
from qualcoder.refi import RefiExport, RefiImport
from qualcoder.reports import DialogReportCoderComparisons, DialogReportCodeFrequencies
from qualcoder.report_code_summary import DialogReportCodeSummary
from qualcoder.report_compare_coder_file import DialogCompareCoderByFile
from qualcoder.report_codes import DialogReportCodes
from qualcoder.report_file_summary import DialogReportFileSummary
from qualcoder.report_relations import DialogReportRelations
from qualcoder.report_sql import DialogSQL
from qualcoder.rqda import RqdaImport
from qualcoder.settings import DialogSettings
from qualcoder.special_functions import DialogSpecialFunctions
# from qualcoder.text_mining import DialogTextMining
from qualcoder.view_av import DialogCodeAV
from qualcoder.view_charts import ViewCharts
from qualcoder.view_graph import ViewGraph
from qualcoder.view_image import DialogCodeImage

qualcoder_version = "QualCoder 3.0"

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


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    msg = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(msg)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 10pt}")
    mb.setText(msg)
    mb.exec()


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

    def __init__(self):
        sys.excepthook = exception_handler
        self.conn = None
        self.project_path = ""
        self.project_name = ""
        self.last_export_directory = ""
        self.delete_backup = True
        self.delete_backup_path_name = ""
        self.confighome = os.path.expanduser('~/.qualcoder')
        self.configpath = os.path.join(self.confighome, 'config.ini')
        self.persist_path = os.path.join(self.confighome, 'recent_projects.txt')
        self.settings = self.load_settings()
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
            with open(self.persist_path, 'r') as f:
                for line in f:
                    previous.append(line.strip())
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
        with open(self.persist_path, 'w') as f:
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
            with open(self.persist_path, 'w') as f:
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
        with open(self.persist_path, 'w') as f:
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

    def get_code_names(self):
        cur = self.conn.cursor()
        cur.execute("select name, memo, owner, date, cid, catid, color from code_name order by lower(name)")
        result = cur.fetchall()
        res = []
        keys = 'name', 'memo', 'owner', 'date', 'cid', 'catid', 'color'
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def get_filenames(self):
        """ Get all filenames. As id, name, memo """
        cur = self.conn.cursor()
        cur.execute("select id, name, memo from source order by lower(name)")
        result = cur.fetchall()
        res = []
        for row in result:
            res.append({'id': row[0], 'name': row[1], 'memo': row[2]})
        return res

    def get_casenames(self):
        """ Get all case names. As id, name, memo. """
        cur = self.conn.cursor()
        cur.execute("select caseid, name, memo from cases order by lower(name)")
        result = cur.fetchall()
        res = []
        for row in result:
            res.append({'id': row[0], 'name': row[1], 'memo': row[2]})
        return res

    def get_text_filenames(self, ids=None):
        """ Get filenames of text files.
        param:
            ids: list of Integer ids for a restricted list of files. """

        if ids is None:
            ids = []
        sql = "select id, name, memo from source where (mediapath is Null or mediapath like 'docs:%') "
        if ids:
            str_ids = list(map(str, ids))
            sql += " and id in (" + ",".join(str_ids) + ")"
        sql += "order by lower(name)"
        cur = self.conn.cursor()
        cur.execute(sql)
        result = cur.fetchall()
        res = []
        for row in result:
            res.append({'id': row[0], 'name': row[1], 'memo': row[2]})
        return res

    def get_image_filenames(self, ids=None):
        """ Get filenames of image files only.
        param:
            ids: list of Integer ids for a restricted list of files. """

        if ids is None:
            ids = []
        sql = "select id, name, memo from source where mediapath like '/images/%' or mediapath like 'images:%'"
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
        sql = "select id, name, memo from source where "
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
        cur.execute("select name, catid, owner, date, memo, supercatid from code_cat order by lower(name)")
        result = cur.fetchall()
        keys = 'name', 'catid', 'owner', 'date', 'memo', 'supercatid'
        for row in result:
            categories.append(dict(zip(keys, row)))
        codes = []
        cur = self.conn.cursor()
        cur.execute("select name, memo, owner, date, cid, catid, color from code_name order by lower(name)")
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

    def write_config_ini(self, settings):
        """ Stores settings for fonts, current coder, directory, and window sizes in .qualcoder folder
        Called by qualcoder.App.load_settings, qualcoder.MainWindow.open_project, settings.DialogSettings
        """

        config = configparser.ConfigParser()
        config['DEFAULT'] = settings
        with open(self.configpath, 'w') as configfile:
            config.write(configfile)

    def _load_config_ini(self):
        """ load config settings, and convert some to int. """

        config = configparser.ConfigParser()
        config.read(self.configpath)
        default = config['DEFAULT']
        result = dict(default)
        if 'fontsize' in default:
            result['fontsize'] = default.getint('fontsize')
        if 'docfontsize' in default:
            result['docfontsize'] = default.getint('docfontsize')
        if 'treefontsize' in default:
            result['treefontsize'] = default.getint('treefontsize')
        if 'backup_num' in default:
            result['backup_num'] = default.getint('backup_num')
        return result

    def check_and_add_additional_settings(self, settings_data):
        """ Newer features include width and height settings for many dialogs and main window.
        timestamp format.
        dialog_crossovers IS dialog relations
        :param settings_data:  dictionary of most or all settings
        :return: dictionary of all settings
        """

        dict_len = len(settings_data)
        keys = ['mainwindow_w', 'mainwindow_h',
                'dialogcasefilemanager_w', 'dialogcasefilemanager_h',
                'dialogcodetext_splitter0', 'dialogcodetext_splitter1',
                'dialogcodetext_splitter_v0', 'dialogcodetext_splitter_v1',
                'dialogcodebycase_splitter0', 'dialogcodebycase_splitter1',
                'dialogcodebycase_splitter_v0', 'dialogcodebycase_splitter_v1',
                'dialogcodeimage_splitter0', 'dialogcodeimage_splitter1',
                'dialogcodeimage_splitter_h0', 'dialogcodeimage_splitter_h1',
                'dialogreportcodes_splitter0', 'dialogreportcodes_splitter1',
                'dialogreportcodes_splitter_v0', 'dialogreportcodes_splitter_v1',
                'dialogreportcodes_splitter_v2',
                'dialogjournals_splitter0', 'dialogjournals_splitter1',
                'dialogsql_splitter_h0', 'dialogsql_splitter_h1',
                'dialogsql_splitter_v0', 'dialogsql_splitter_v1',
                'dialogcases_splitter0', 'dialogcases_splitter1',
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
                'docfontsize',
                'dialogreport_file_summary_splitter0', 'dialogreport_file_summary_splitter0',
                'dialogreport_code_summary_splitter0', 'dialogreport_code_summary_splitter0',
                'stylesheet', 'backup_num'
                ]
        for key in keys:
            if key not in settings_data:
                settings_data[key] = 0
                if key == "timestampformat":
                    settings_data[key] = "[hh.mm.ss]"
                if key == "speakernameformat":
                    settings_data[key] = "[]"
                if key == "backup_num":
                    settings_data[key] = 5
        # write out new ini file, if needed
        if len(settings_data) > dict_len:
            self.write_config_ini(settings_data)
        return settings_data

    def merge_settings_with_default_stylesheet(self, settings):
        """ Originally had separate stylesheet file. Now stylesheet is coded because
        avoids potential data file import errors with pyinstaller. """

        style_dark = "* {font-size: 12px; background-color: #2a2a2a; color:#eeeeee;}\n\
        QWidget:focus {border: 2px solid #f89407;}\n\
        QDialog {border: 1px solid #707070;}\n\
        QLabel#label_search_regex {background-color:#808080;}\n\
        QLabel#label_search_case_sensitive {background-color:#808080;}\n\
        QLabel#label_search_all_files {background-color:#808080;}\n\
        QLabel#label_font_size {background-color:#808080;}\n\
        QLabel#label_search_all_journals {background-color:#808080;}\n\
        QLabel#label_exports {background-color:#808080;}\n\
        QLabel#label_time_3 {background-color:#808080;}\n\
        QLabel#label_volume {background-color:#808080;}\n\
        QLabel:disabled {color: #808080;}\n\
        QSlider::handle:horizontal {background-color: #f89407;}\n\
        QCheckBox {border: None}\n\
        QCheckBox::indicator {border: 2px solid #808080; background-color: #2a2a2a;}\n\
        QCheckBox::indicator::checked {border: 2px solid #808080; background-color: orange;}\n\
        QRadioButton::indicator {border: 1px solid #808080; background-color: #2a2a2a;}\n\
        QRadioButton::indicator::checked {border: 2px solid #808080; background-color: orange;}\n\
        QLineEdit {border: 1px solid #808080;}\n\
        QMenuBar::item:selected {background-color: #3498db; }\n\
        QMenu {border: 1px solid #808080;}\n\
        QMenu::item:selected {background-color:  #3498db;}\n\
        QMenu::item:disabled {color: #777777;}\n\
        QToolTip {background-color: #2a2a2a; color:#eeeeee; border: 1px solid #f89407; }\n\
        QPushButton {background-color: #808080;}\n\
        QPushButton:hover {border: 2px solid #ffaa00;}\n\
        QComboBox {border: 1px solid #707070;}\n\
        QComboBox:hover {border: 2px solid #ffaa00;}\n\
        QGroupBox {border: None;}\n\
        QGroupBox:focus {border: 3px solid #ffaa00;}\n\
        QTabWidget::pane {border: 1px solid #808080;}\n\
        QTabBar {border: 2px solid #808080;}\n\
        QTabBar::tab {border: 1px solid #808080;}\n\
        QTabBar::tab:selected {border: 2px solid #f89407; background-color: #707070; margin-left: 3px;}\n\
        QTabBar::tab:!selected {border: 2px solid #707070; background-color: #2a2a2a; margin-left: 3px;}\n\
        QTextEdit {border: 1px solid #ffaa00;}\n\
        QTextEdit:focus {border: 2px solid #ffaa00;}\n\
        QTableWidget {border: 1px solid #ffaa00; gridline-color: #707070;}\n\
        QTableWidget:focus {border: 3px solid #ffaa00;}\n\
        QListWidget::item:selected {border-left: 3px solid red; color: #eeeeee;}\n\
        QHeaderView::section {background-color: #505050; color: #ffce42;}\n\
        QTreeWidget {font-size: 12px;}\n\
        QTreeWidget::branch:selected {border-left: 2px solid red; color: #eeeeee;}"
        style_dark = style_dark.replace("* {font-size: 12", "* {font-size:" + str(settings.get('fontsize')))
        style_dark = style_dark.replace("QTreeWidget {font-size: 12",
                                        "QTreeWidget {font-size: " + str(settings.get('treefontsize')))

        style = "* {font-size: 12px; color: #000000;}\n\
        QWidget:focus {border: 2px solid #f89407;}\n\
        QComboBox:hover,QPushButton:hover {border: 2px solid #ffaa00;}\n\
        QGroupBox {border: None;}\n\
        QGroupBox:focus {border: 3px solid #ffaa00;}\n\
        QTextEdit:focus {border: 2px solid #ffaa00;}\n\
        QToolTip {background-color: #fffacd; color:#000000; border: 1px solid #f89407; }\n\
        QListWidget::item:selected {border-left: 2px solid red; color: #000000;}\n\
        QTableWidget:focus {border: 3px solid #ffaa00;}\n\
        QTreeWidget {font-size: 12px;}\n\
        QTreeWidget::branch:selected {border-left: 2px solid red; color: #000000;}"
        style = style.replace("* {font-size: 12", "* {font-size:" + str(settings.get('fontsize')))
        style = style.replace("QTreeWidget {font-size: 12",
                              "QTreeWidget {font-size: " + str(settings.get('treefontsize')))

        if self.settings['stylesheet'] == 'dark':
            return style_dark
        return style

    def load_settings(self):
        result = self._load_config_ini()
        if not len(result):
            self.write_config_ini(self.default_settings)
            logger.info('Initialized config.ini')
            result = self._load_config_ini()
        # codername is also legacy, v2.8 plus keeps current coder name in database project table
        if result['codername'] == "":
            result['codername'] = "default"
        result = self.check_and_add_additional_settings(result)
        # TODO TEMPORARY delete, legacy
        if result['speakernameformat'] == 0:
            result['speakernameformat'] = "[]"
        if result['stylesheet'] == 0:
            result['stylesheet'] = "original"
        return result

    @property
    def default_settings(self):
        """ Standard Settings for config.ini file. """
        return {
            'backup_num': 5,
            'codername': 'default',
            'font': 'Noto Sans',
            'fontsize': 14,
            'docfontsize': 12,
            'treefontsize': 12,
            'directory': os.path.expanduser('~'),
            'showids': False,
            'language': 'en',
            'backup_on_open': True,
            'backup_av_files': True,
            'timestampformat': "[hh.mm.ss]",
            'speakernameformat': "[]",
            'mainwindow_w': 0,
            'mainwindow_h': 0,
            'dialogcodetext_splitter0': 1,
            'dialogcodetext_splitter1': 1,
            'dialogcodetext_splitter_v0': 1,
            'dialogcodetext_splitter_v1': 1,
            'dialogcodebycase_splitter0': 1,
            'dialogcodebycase_splitter1': 1,
            'dialogcodebycase_splitter_v0': 1,
            'dialogcodebycase_splitter_v1': 1,
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
            'dialogcases_splitter0': 1,
            'dialogcases_splitter1': 1,
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
            'stylesheet': 'original'
        }

    def get_file_texts(self, fileids=None):
        """ Get the texts of all text files as a list of dictionaries.
        Called by DialogCodeText.search_for_text
        param:
            fileids - a list of fileids or None
        """

        cur = self.conn.cursor()
        if fileids is not None:
            cur.execute(
                "select name, id, fulltext, memo, owner, date from source where id in (?) and fulltext is not null",
                fileids
            )
        else:
            cur.execute(
                "select name, id, fulltext, memo, owner, date from source where fulltext is not null order by name")
        keys = 'name', 'id', 'fulltext', 'memo', 'owner', 'date'
        result = []
        for row in cur.fetchall():
            result.append(dict(zip(keys, row)))
        return result

    def get_journal_texts(self, jids=None):
        """ Get the texts of all journals as a list of dictionaries.
        Called by DialogJournals.search_for_text
        param:
            jids - a list of jids or None
        """

        cur = self.conn.cursor()
        if jids is not None:
            cur.execute(
                "select name, jid, jentry, owner, date from journal where jid in (?)",
                jids
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
        sys.excepthook = exception_handler
        QtWidgets.QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        # Test of MacOS menu bar
        self.ui.menubar.setNativeMenuBar(False)
        self.get_latest_github_release()
        try:
            w = int(self.app.settings['mainwindow_w'])
            h = int(self.app.settings['mainwindow_h'])
            if h > 40 and w > 50:
                self.resize(w, h)
        except KeyError:
            pass
        self.hide_menu_options()
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.init_ui()
        self.show()

    def init_ui(self):
        """ Set up menu triggers """

        # project menu
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
        self.ui.actionExit.triggered.connect(self.closeEvent)
        self.ui.actionExit.setShortcut('Ctrl+Q')

        # File cases and journals menu
        self.ui.actionManage_files.triggered.connect(self.manage_files)
        self.ui.actionManage_journals.triggered.connect(self.journals)
        self.ui.actionManage_journals.setShortcut('Alt+J')
        self.ui.actionManage_cases.triggered.connect(self.manage_cases)
        self.ui.actionManage_cases.setShortcut('Alt+C')
        self.ui.actionManage_attributes.triggered.connect(self.manage_attributes)
        self.ui.actionManage_attributes.setShortcut('Alt+A')
        self.ui.actionImport_survey.triggered.connect(self.import_survey)
        self.ui.actionImport_survey.setShortcut('Alt+I')
        self.ui.actionManage_bad_links_to_files.triggered.connect(self.manage_bad_file_links)

        # Codes menu
        self.ui.actionCodes.triggered.connect(self.text_coding)
        self.ui.actionCodes.setShortcut('Alt+T')
        self.ui.actionCode_image.triggered.connect(self.image_coding)
        self.ui.actionCode_image.setShortcut('Alt+I')
        self.ui.actionCode_audio_video.triggered.connect(self.av_coding)
        self.ui.actionCode_audio_video.setShortcut('Alt+V')
        self.ui.actionCode_by_case.triggered.connect(self.code_by_case)
        self.ui.actionExport_codebook.triggered.connect(self.codebook)

        # Reports menu
        self.ui.actionCoding_reports.triggered.connect(self.report_coding)
        self.ui.actionCoding_comparison.triggered.connect(self.report_coding_comparison)
        self.ui.actionCoding_comparison_by_file.triggered.connect(self.report_compare_coders_by_file)
        self.ui.actionCode_frequencies.triggered.connect(self.report_code_frequencies)
        self.ui.actionView_Graph.triggered.connect(self.view_graph_original)
        self.ui.actionView_Graph.setShortcut('Ctrl+G')
        self.ui.actionCharts.triggered.connect(self.view_charts)
        self.ui.actionCode_relations.triggered.connect(self.report_code_relations)
        self.ui.actionFile_summary.triggered.connect(self.report_file_summary)
        self.ui.actionCode_summary.triggered.connect(self.report_code_summary)
        # TODO self.ui.actionText_mining.triggered.connect(self.text_mining)
        self.ui.actionSQL_statements.triggered.connect(self.report_sql)

        # help menu
        self.ui.actionContents.triggered.connect(self.help)
        self.ui.actionContents.setShortcut('Ctrl+H')
        self.ui.actionAbout.triggered.connect(self.about)
        self.ui.actionSpecial_functions.triggered.connect(self.special_functions)

        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.ui.textEdit.setReadOnly(True)
        self.settings_report()

    def resizeEvent(self, new_size):
        """ Update the widget size details in the app.settings variables """

        self.app.settings['mainwindow_w'] = new_size.size().width()
        self.app.settings['mainwindow_h'] = new_size.size().height()

    def fill_recent_projects_menu_actions(self):
        """ Get the recent projects from the .qualcoder txt file.
        Add up to 7 recent projects to the menu. """

        self.recent_projects = self.app.read_previous_project_paths()
        if len(self.recent_projects) == 0:
            return
        # Removes the qtdesigner default action. Also clears the section when a proect is closed
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

        # project menu
        self.ui.actionClose_Project.setEnabled(False)
        self.ui.actionProject_Memo.setEnabled(False)
        self.ui.actionProject_Exchange_Export.setEnabled(False)
        self.ui.actionREFI_Codebook_export.setEnabled(False)
        self.ui.actionREFI_Codebook_import.setEnabled(False)
        self.ui.actionREFI_QDA_Project_import.setEnabled(True)
        self.ui.actionRQDA_Project_import.setEnabled(True)
        self.ui.actionExport_codebook.setEnabled(False)
        # files cases journals menu
        self.ui.actionManage_files.setEnabled(False)
        self.ui.actionManage_journals.setEnabled(False)
        self.ui.actionManage_cases.setEnabled(False)
        self.ui.actionManage_attributes.setEnabled(False)
        self.ui.actionImport_survey.setEnabled(False)
        self.ui.actionManage_bad_links_to_files.setEnabled(False)
        # codes menu
        self.ui.actionCodes.setEnabled(False)
        self.ui.actionCode_image.setEnabled(False)
        self.ui.actionCode_audio_video.setEnabled(False)
        self.ui.actionCode_by_case.setEnabled(False)
        # reports menu
        self.ui.actionCoding_reports.setEnabled(False)
        self.ui.actionCoding_comparison.setEnabled(False)
        self.ui.actionCoding_comparison_by_file.setEnabled(False)
        self.ui.actionCode_frequencies.setEnabled(False)
        self.ui.actionCode_relations.setEnabled(False)
        self.ui.actionText_mining.setEnabled(False)
        self.ui.actionSQL_statements.setEnabled(False)
        self.ui.actionFile_summary.setEnabled(False)
        self.ui.actionCode_summary.setEnabled(False)
        self.ui.actionCategories.setEnabled(False)
        self.ui.actionView_Graph.setEnabled(False)
        self.ui.actionCharts.setEnabled(False)
        # help menu
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
        # Files cases journals menu
        self.ui.actionManage_files.setEnabled(True)
        self.ui.actionManage_journals.setEnabled(True)
        self.ui.actionManage_cases.setEnabled(True)
        self.ui.actionManage_attributes.setEnabled(True)
        self.ui.actionImport_survey.setEnabled(True)
        # Codes menu
        self.ui.actionCodes.setEnabled(True)
        self.ui.actionCode_image.setEnabled(True)
        self.ui.actionCode_audio_video.setEnabled(True)
        self.ui.actionCode_by_case.setEnabled(True)
        # Reports menu
        self.ui.actionCoding_reports.setEnabled(True)
        self.ui.actionCoding_comparison.setEnabled(True)
        self.ui.actionCoding_comparison_by_file.setEnabled(True)
        self.ui.actionCode_frequencies.setEnabled(True)
        self.ui.actionCode_relations.setEnabled(True)
        self.ui.actionSQL_statements.setEnabled(True)
        self.ui.actionFile_summary.setEnabled(True)
        self.ui.actionCode_summary.setEnabled(True)
        self.ui.actionCategories.setEnabled(True)
        self.ui.actionView_Graph.setEnabled(True)
        self.ui.actionCharts.setEnabled(True)
        # Help menu
        self.ui.actionSpecial_functions.setEnabled(True)

        # TODO FOR FUTURE EXPANSION text mining
        self.ui.actionText_mining.setEnabled(False)
        self.ui.actionText_mining.setVisible(False)

    def settings_report(self):
        """ Display general settings and project summary """

        msg = _("Settings")
        msg += "\n========\n"
        msg += _("Coder") + ": " + self.app.settings['codername'] + "\n"
        msg += _("Font") + ": " + self.app.settings['font'] + " " + str(self.app.settings['fontsize']) + "\n"
        msg += _("Tree font size") + ": " + str(self.app.settings['treefontsize']) + "\n"
        msg += _("Working directory") + ": " + self.app.settings['directory']
        msg += "\n" + _("Show IDs") + ": " + str(self.app.settings['showids']) + "\n"
        msg += _("Language") + ": " + self.app.settings['language'] + "\n"
        msg += _("Timestamp format") + ": " + self.app.settings['timestampformat'] + "\n"
        msg += _("Speaker name format") + ": " + str(self.app.settings['speakernameformat']) + "\n"
        msg += _("Backup on open") + ": " + str(self.app.settings['backup_on_open']) + "\n"
        msg += _("Backup AV files") + ": " + str(self.app.settings['backup_av_files'])
        if platform.system() == "Windows":
            msg += "\n" + _("Directory (folder) paths / represents \\")
        msg += "\n========"
        self.ui.textEdit.append(msg)
        self.ui.textEdit.textCursor().movePosition(QtGui.QTextCursor.MoveOperation.End)
        self.ui.tabWidget.setCurrentWidget(self.ui.tab_action_log)

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

    def report_coding(self):
        """ Report on coding and categories. """

        self.ui.label_reports.hide()
        ui = DialogReportCodes(self.app, self.ui.textEdit)
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

    def import_survey(self):
        """ Import survey flat sheet: csv file or xlsx.
        Create cases and assign attributes to cases.
        Identify qualitative questions and assign these data to the source table for
        coding and review. Modal dialog. """

        ui = DialogImportSurvey(self.app, self.ui.textEdit)
        ui.exec()
        self.ui.tabWidget.setCurrentWidget(self.ui.tab_action_log)

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
        """ Create and edit journals. """

        self.ui.label_manage.hide()
        ui = DialogJournals(self.app, self.ui.textEdit)
        ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.tab_layout_helper(self.ui.tab_manage, ui)

    def text_coding(self):
        """ Create edit and delete codes. Apply and remove codes and annotations to the
        text in imported text files. """

        files = self.app.get_text_filenames()
        if len(files) > 0:
            self.ui.label_coding.hide()
            ui = DialogCodeText(self.app, self.ui.textEdit, self.ui.tab_reports)
            ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
            self.tab_layout_helper(self.ui.tab_coding, ui)
        else:
            msg = _("This project contains no text files.")
            Message(self.app, _('No text files'), msg).exec()

    def code_by_case(self):
        """ Create edit and delete codes. Apply and remove codes and annotations to
         files. Organised by Case. Useful for an imported survey. """

        cases = self.app.get_casenames()
        files = self.app.get_text_filenames()
        if len(files) > 0 and len(cases) > 0:
            self.ui.label_coding.hide()
            ui = DialogCodeByCase(self.app, self.ui.textEdit, self.ui.tab_reports)
            ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
            self.tab_layout_helper(self.ui.tab_coding, ui)
        else:
            msg = _("This project contains no text files.")
            if len(cases) == 0:
                msg = _("This project contains no cases.")
            Message(self.app, _('No cases or files'), msg).exec()

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
        self.ui.label_coding.hide()
        try:
            ui = DialogCodeAV(self.app, self.ui.textEdit, self.ui.tab_reports)
            ui.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
            self.tab_layout_helper(self.ui.tab_coding, ui)
        except Exception as e_:
            logger.debug(str(e_))
            Message(self.app, _("A/V Coding"), str(e_), "warning").exec()

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

    def refi_project_export(self):
        """ Export the project as a qpdx zipped folder.
         Follows the REFI Project Exchange standards.
         CURRENTLY IN TESTING AND NOT COMPLETE NOR VALIDATED.
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
        Close project will also delete a backup if a backup was made and no changes occured.
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
                if self.app.conn is not None:
                    try:
                        self.app.conn.commit()
                        self.app.conn.close()
                    except Exception as e_:
                        print("closeEvent", e_)
                QtWidgets.QApplication.instance().quit()
                #QtWidgets.qApp.quit()
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
        """

        self.app = App()
        if self.app.settings['directory'] == "":
            self.app.settings['directory'] = os.path.expanduser('~')
        project_path = QtWidgets.QFileDialog.getSaveFileName(self,
                                                             _("Enter project name"), self.app.settings['directory'],
                                                             options=QtWidgets.QFileDialog.Option.DontUseNativeDialog)
        project_path = project_path[0]
        if project_path == "":
            Message(self.app, _("Project"), _("No project created."), "critical").exec()
            return
        # Add suffix to project name if it already exists
        counter = 0
        extension = ""
        while os.path.exists(project_path + extension + ".qda"):
            #print("C", counter, project_path + extension + ".qda")
            if counter > 0:
                extension = "_" + str(counter)
            counter += 1
        self.app.project_path = project_path + extension + ".qda"
        try:
            os.mkdir(self.app.project_path)
            os.mkdir(self.app.project_path + "/images")
            os.mkdir(self.app.project_path + "/audio")
            os.mkdir(self.app.project_path + "/video")
            os.mkdir(self.app.project_path + "/documents")
        except Exception as e_:
            logger.critical(_("Project creation error ") + str(e_))
            Message(self.app, _("Project"), self.app.project_path + _(" not successfully created"), "critical").exec()
            self.app = App()
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
            "owner text, date text, av_text_id integer, unique(name))")
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
        cur.execute("INSERT INTO project VALUES(?,?,?,?,?,?,?)",
                    ('v6', datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), '', qualcoder_version, 0,
                     0, self.app.settings['codername']))
        self.app.conn.commit()
        try:
            # Get and display some project details
            self.ui.textEdit.append("\n" + _("New project: ") + self.app.project_path + _(" created."))
            self.ui.textEdit.append(_("Opening: ") + self.app.project_path)
            self.setWindowTitle("QualCoder " + self.app.project_name)
            cur.execute('select sqlite_version()')
            self.ui.textEdit.append("SQLite version: " + str(cur.fetchone()))
            cur.execute("select databaseversion, date, memo, about from project")
            result = cur.fetchone()
            self.project['databaseversion'] = result[0]
            self.project['date'] = result[1]
            self.project['memo'] = result[2]
            self.project['about'] = result[3]
            self.ui.textEdit.append(_("New Project Created") + "\n========\n"
                                    + _("DB Version:") + str(self.project['databaseversion']) + "\n"
                                    + _("Date: ") + str(self.project['date']) + "\n"
                                    + _("About: ") + str(self.project['about']) + "\n"
                                    + _("Coder:") + str(self.app.settings['codername']) + "\n"
                                    + "========")
        except Exception as e_:
            msg = _("Problem creating database ")
            logger.warning(msg + self.app.project_path + " Exception:" + str(e_))
            self.ui.textEdit.append("\n" + msg + "\n" + self.app.project_path)
            self.ui.textEdit.append(str(e_))
            self.close_project()
            return
        # New project, so tell open project NOT to backup, as there will be nothing in there to backup
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

    def change_settings(self):
        """ Change default settings - the coder name, font, font size.
        Language, Backup options.
        As this dialog affects all others if the coder name changes, on exit of the dialog,
        all other opened dialogs are destroyed."""

        current_coder = self.app.settings['codername']
        ui = DialogSettings(self.app)
        ui.exec()
        self.settings_report()
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
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

        cur = self.app.conn.cursor()
        cur.execute("select memo from project")
        memo = cur.fetchone()[0]
        ui = DialogMemo(self.app, _("Memo for project ") + self.app.project_name,
                        memo)
        ui.exec()
        if memo != ui.memo:
            cur.execute('update project set memo=?', (ui.memo,))
            self.app.conn.commit()
            self.ui.textEdit.append(_("Project memo entered."))
            self.app.delete_backup = False

    def open_project(self, path_="", newproject="no"):
        """ Open an existing project.
        if set, also save a backup datetime stamped copy at the same time.
        Do not backup on a newly created project, as it wont contain data.
        A backup is created if settings backuop is True.
        The backup is deleted, if no changes occured.
        Backups are created using the date and 24 hour suffix: _BKUP_yyyymmdd_hh
        Backups are not replaced within the same hour.
        Update older databases to current version mainly by adding columns and tables.
        Table constraints are not updated (code_text dupliated codings).
        param:
            path: if path is "" then get the path from a dialog, otherwise use the supplied path
            newproject: yes or no  if yes then do not make an initial backup
        """

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
        splt = path_.split("|")
        proj_path = ""
        if len(splt) == 1:
            proj_path = splt[0]
        if len(splt) == 2:
            proj_path = splt[1]
        if len(path) > 3 and proj_path[-4:] == ".qda":
            try:
                self.app.create_connection(proj_path)
            except Exception as e_:
                self.app.conn = None
                msg += " " + str(e_)
                logger.debug(msg)
        if self.app.conn is None:
            msg += "\n" + proj_path
            Message(self.app, _("Cannot open file"), msg, "critical").exec()
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
        except Exception as e_:
            logger.debug("This in not a QualCoder database " + str(e_))
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
            self.app.write_config_ini(self.app.settings)
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
            except Exception as e_:
                logger.debug(str(e_))
        try:
            cur.execute("select bookmarkfile from project")
        except sqlite3.OperationalError:
            try:
                cur.execute("ALTER TABLE project ADD bookmarkfile integer")
                self.app.conn.commit()
                cur.execute("ALTER TABLE project ADD bookmarkpos integer")
                self.app.conn.commit()
                self.ui.textEdit.append(_("Updating database to version") + " v2")
            except Exception as e_:
                logger.debug(str(e_))
        # Database version v3
        cur = self.app.conn.cursor()
        try:
            cur.execute("select important from code_text")
        except sqlite3.OperationalError:
            try:
                cur.execute("ALTER TABLE code_text ADD important integer")
                self.app.conn.commit()
            except Exception as e_:
                logger.debug(str(e_))
                cur = self.app.conn.cursor()
        try:
            cur.execute("select important from code_av")
        except sqlite3.OperationalError:
            try:
                cur.execute("ALTER TABLE code_av ADD important integer")
                self.app.conn.commit()
            except Exception as e_:
                logger.debug(str(e_))
        cur = self.app.conn.cursor()
        try:
            cur.execute("select important from code_image")
        except sqlite3.OperationalError:
            try:
                cur.execute("ALTER TABLE code_image ADD important integer")
                self.app.conn.commit()
                self.ui.textEdit.append(_("Updating database to version") + " v3")
            except Exception as e_:
                logger.debug(str(e_))
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
        # Save a date and 24 hour stamped backup
        if self.app.settings['backup_on_open'] == 'True' and newproject == "no":
            self.save_backup()
        msg = "\n" + _("Project Opened: ") + self.app.project_name
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

    def save_backup(self):
        """ Save a date and hours stamped backup.
        Do not backup if the name already exists.
        A backup can be generated in the subsequent hour."""

        nowdate = datetime.datetime.now().astimezone().strftime("%Y%m%d_%H")  # -%M-%S")
        backup = self.app.project_path[0:-4] + "_BKUP_" + nowdate + ".qda"
        # Do not try and create another backup with same date and hour
        result = os.path.exists(backup)
        if result:
            return
        if self.app.settings['backup_av_files'] == 'True':
            try:
                shutil.copytree(self.app.project_path, backup)
            except FileExistsError as e_:
                msg = _("There is already a backup with this name")
                print(str(e_) + "\n" + msg)
                logger.warning(_(msg) + "\n" + str(e_))
        else:
            shutil.copytree(self.app.project_path, backup,
                            ignore=shutil.ignore_patterns('*.mp3', '*.wav', '*.mp4', '*.mov', '*.ogg', '*.wmv', '*.MP3',
                                                          '*.WAV', '*.MP4', '*.MOV', '*.OGG', '*.WMV'))
            self.ui.textEdit.append(_("WARNING: audio and video files NOT backed up. See settings."))
        self.ui.textEdit.append(_("Project backup created: ") + backup)
        # Delete backup path - delete the backup if no changes occurred in the project during the session
        self.app.delete_backup_path_name = backup

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
        msg = "\n" + _("PROJECT SUMMARY")
        msg += "\n========\n"
        msg += _("Date time now: ") + datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M") + "\n"
        msg += self.app.project_name + "\n"
        msg += _("Project path: ") + self.app.project_path + "\n"
        msg += _("Project date: ") + str(self.project['date']) + "\n"
        sql = "select memo from project"
        cur.execute(sql)
        res = cur.fetchone()
        msg += _("Project memo: ") + str(res[0]) + "\n"
        sql = "select count(id) from source"
        cur.execute(sql)
        res = cur.fetchone()
        msg += _("Files: ") + str(res[0]) + "\n"
        sql = "select count(caseid) from cases"
        cur.execute(sql)
        res = cur.fetchone()
        msg += _("Cases: ") + str(res[0]) + "\n"
        sql = "select count(catid) from code_cat"
        cur.execute(sql)
        res = cur.fetchone()
        msg += _("Code categories: ") + str(res[0]) + "\n"
        sql = "select count(cid) from code_name"
        cur.execute(sql)
        res = cur.fetchone()
        msg += _("Codes: ") + str(res[0]) + "\n"
        sql = "select count(name) from attribute_type"
        cur.execute(sql)
        res = cur.fetchone()
        msg += _("Attributes: ") + str(res[0]) + "\n"
        sql = "select count(jid) from journal"
        cur.execute(sql)
        res = cur.fetchone()
        msg += _("Journals: ") + str(res[0])
        cur.execute("select name from source where id=?", [result[4]])
        bookmark_filename = cur.fetchone()
        if bookmark_filename is not None and result[5] is not None:
            msg += "\nText Bookmark: " + str(bookmark_filename[0])
            msg += ", position: " + str(result[5])

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
        self.ui.textEdit.append("\n========\n")
        self.ui.tabWidget.setCurrentWidget(self.ui.tab_action_log)
        self.ui.textEdit.verticalScrollBar().setValue(self.ui.textEdit.verticalScrollBar().maximum())

    def close_project(self):
        """ Close an open project.
        Remove widgets from tabs, clear dialog list. Close app connection.
        Delete old backups. Hide menu options. """

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
        # Added if statement for the first opening of QualCoder. Otherwise looks odd.
        if self.app.project_name != "":
            self.ui.textEdit.append("Closing project: " + self.app.project_name)
            self.ui.textEdit.append("========\n")
        if self.app.conn is not None:
            self.app.conn.commit()
            self.app.conn.close()
        self.delete_backup_folders()
        self.app.append_recent_project(self.app.project_path)
        self.fill_recent_projects_menu_actions()
        self.app.conn = None
        self.app.project_path = ""
        self.app.project_name = ""
        self.app.delete_backup_path_name = ""
        self.app.delete_backup = True
        self.project = {"databaseversion": "", "date": "", "memo": "", "about": ""}
        self.hide_menu_options()
        self.setWindowTitle("QualCoder")
        self.app.write_config_ini(self.app.settings)
        self.ui.tabWidget.setCurrentWidget(self.ui.tab_action_log)
        self.ui.textEdit.verticalScrollBar().setValue(self.ui.textEdit.verticalScrollBar().maximum())

    def delete_backup_folders(self):
        """ Delete the most current backup created on opening a project,
        providing the project was not changed in any way.
        Delete oldest backups if more than BACKUP_NUM are created.
        Backup name format: directories/projectname_BKUP_yyyymmdd_hh.qda
        Requires: self.settings['backup_num'] """

        if self.app.project_path == "":
            return
        if self.app.delete_backup_path_name != "" and self.app.delete_backup:
            try:
                shutil.rmtree(self.app.delete_backup_path_name)
            except Exception as e_:
                print(str(e_))
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
            except Exception as e_:
                print(str(e_))

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
                html = '<span style="color:red">' + _json['html_url'] + '</span><br />'
                self.ui.textEdit.append(html)
            else:
                self.ui.textEdit.append(_("Latest Release: ") + _json['name'])
                self.ui.textEdit.append(_json['html_url'] + "\n")
        except Exception as e_:
            print(e_)
            logger.debug(str(e_))


def gui():
    qual_app = App()
    settings = qual_app.load_settings()
    project_path = qual_app.get_most_recent_projectpath()
    app = QtWidgets.QApplication(sys.argv)
    QtGui.QFontDatabase.addApplicationFont("GUI/NotoSans-hinted/NotoSans-Regular.ttf")
    QtGui.QFontDatabase.addApplicationFont("GUI/NotoSans-hinted/NotoSans-Bold.ttf")
    stylesheet = qual_app.merge_settings_with_default_stylesheet(settings)
    app.setStyleSheet(stylesheet)
    pm = QtGui.QPixmap()
    pm.loadFromData(QtCore.QByteArray.fromBase64(qualcoder32), "png")
    app.setWindowIcon(QtGui.QIcon(pm))

    # Use two character language setting
    lang = settings.get('language', 'en')
    # Test for pyinstall data files
    '''if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        print('Running in a PyInstaller bundle')
    else:
        print('Running in a normal Python process')'''
    locale_dir = os.path.join(path, 'locale')
    # Need to get the external data directory for PyInstaller
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        ext_data_dir = sys._MEIPASS
        # print("ext data dir: ", ext_data_dir)
        locale_dir = os.path.join(ext_data_dir, 'qualcoder')
        locale_dir = os.path.join(locale_dir, 'locale')
        # locale_dir = os.path.join(locale_dir, lang)
        # locale_dir = os.path.join(locale_dir, 'LC_MESSAGES')
    # print("locale dir: ", locale_dir)
    # print("LISTDIR: ", os.listdir(locale_dir))
    # getlang = gettext.translation('en', localedir=locale_dir, languages=['en'])
    translator = gettext.translation(domain='default', localedir=locale_dir, fallback=True)
    if lang in ["de", "el", "es", "fr", "it", "jp", "pt"]:
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
            qm = os.path.join(qm, 'app_' + lang + '.qm')
            print("qm file located at: ", qm)
            qt_translator.load(qm)
            if qt_translator.isEmpty():
                print("Installing app_" + lang + ".qm to .qualcoder folder")
                install_language(lang)
                qt_translator.load(qm)
        app.installTranslator(qt_translator)
        '''Below for pyinstaller and obtaining mo data file from .qualcoder folder
        A solution to this [Errno 13] Permission denied:
        Must have the folder lang/LC_MESSAGES/lang.mo  in the .qualcoder folder
        Replace 'lang' with the language short name e.g. de, el, es ...
        '''
        try:
            translator = gettext.translation(lang, localedir=locale_dir, languages=[lang])
            print("locale directory for python translations: ", locale_dir)
        except Exception as e_:
            print("Error accessing python translations mo file\n", e_)
            print("Locale directory for python translations: ", locale_dir)
            try:
                print("Trying folder: home/.qualcoder/" + lang + "/LC_MESSAGES/" + lang + ".mo")
                mo_dir = os.path.join(home, '.qualcoder')
                translator = gettext.translation(lang, localedir=mo_dir, languages=[lang])
            except Exception as e2_:
                print("No " + lang + ".mo translation file loaded", e2_)
    translator.install()
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
        os.mkdir(mo_path)
        mo = os.path.join(mo_path, lang + ".mo")
        with open(mo, 'wb') as file_:
            decoded_data = base64.decodebytes(mo_data)
            file_.write(decoded_data)


if __name__ == "__main__":
    gui()
