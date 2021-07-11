#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Copyright (c) 2021 Colin Curtain

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


qc_icon = b"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"

import configparser
import datetime
import gettext
import json  # to get latest Github release information
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

from PyQt5 import QtCore, QtGui, QtWidgets

from qualcoder.attributes import DialogManageAttributes
from qualcoder.cases import DialogCases
from qualcoder.codebook import Codebook
from qualcoder.code_text import DialogCodeText
from qualcoder.GUI.base64_helper import qualcoder32
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
from qualcoder.report_codes import DialogReportCodes
from qualcoder.report_file_summary import DialogReportFileSummary
from qualcoder.report_relations import DialogReportRelations
from qualcoder.report_sql import DialogSQL
from qualcoder.rqda import Rqda_import
from qualcoder.settings import DialogSettings
from qualcoder.special_functions import DialogSpecialFunctions
#from qualcoder.text_mining import DialogTextMining
from qualcoder.view_av import DialogCodeAV
from qualcoder.view_graph_original import ViewGraphOriginal
from qualcoder.view_image import DialogCodeImage

qualcoder_version = "QualCoder 2.7"

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
    f = open(logfile, "r")
    data = f.read()
    f.close()
    if len(data) > 12000:
        os.remove(logfile)
        f.open(logfile, "w")
        f.write(data[10000:])
        f.close()
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
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    #logger.error(_("Uncaught exception : ") + text)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 10pt}")
    #mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(text)
    mb.exec_()


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
        except:
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
                f.write(line)
                f.write(os.linesep)
                if i > 8:
                    break
        return result

    def append_recent_project(self, path):
        """ Add project path as first entry to .qualcoder/recent_projects.txt
        """

        if path == "":
            return
        nowdate = datetime.datetime.now().astimezone().strftime("%Y-%m-%d_%H:%M:%S")
        result = self.read_previous_project_paths()
        dated_path = nowdate + "|" + path
        if result == []:
            with open(self.persist_path, 'w') as f:
                f.write(dated_path)
                f.write(os.linesep)
            return

        proj_path = ""
        splt = result[0].split("|") #open_menu
        if len(splt) == 1:
            proj_path = splt[0]
        if len(splt) == 2:
            proj_path = splt[1]
        #print("PATH:", path, "PPATH:", proj_path)  # tmp
        if path != proj_path:
            result.append(dated_path)
            result.sort()
            with open(self.persist_path, 'w') as f:
                for i, line in enumerate(result):
                    f.write(line)
                    f.write(os.linesep)
                    if i > 8:
                        break

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

    def get_text_filenames(self, ids=[]):
        """ Get filenames of text files.
        param:
            ids: list of Integer ids for a restricted list of files. """
        sql = "select id, name, memo from source where (mediapath is Null or mediapath like 'docs:%') "
        if ids != []:
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

    def get_image_filenames(self, ids=[]):
        """ Get filenames of image files only.
        param:
            ids: list of Integer ids for a restricted list of files. """

        sql = "select id, name, memo from source where mediapath like '/images/%' or mediapath like 'images:%'"
        if ids != []:
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

    def get_av_filenames(self, ids=[]):
        """ Get filenames of audio video files only.
        param:
            ids: list of Integer ids for a restricted list of files. """

        sql = "select id, name, memo from source where "
        sql += "(mediapath like '/audio/%' or mediapath like 'audio:%' or mediapath like '/video/%' or mediapath like 'video:%') "
        if ids != []:
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
                bad_links.append({'name': r[1], 'mediapath': r[2] , 'id': r[0]})
            if r[2][0:7] == "images:" and not os.path.exists(r[2][7:]):
                bad_links.append({'name': r[1], 'mediapath': r[2] , 'id': r[0]})
            if r[2][0:6] == "video:" and not os.path.exists(r[2][6:]):
                bad_links.append({'name': r[1], 'mediapath': r[2] , 'id': r[0]})
            if r[2][0:6] == "audio:" and not os.path.exists(r[2][6:]):
                bad_links.append({'name': r[1], 'mediapath': r[2] , 'id': r[0]})
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
        config = configparser.ConfigParser()
        config.read(self.configpath)
        default = config['DEFAULT']
        result = dict(default)
        # convert to int can be removed when all manual styles are removed
        if 'fontsize' in default:
            result['fontsize'] = default.getint('fontsize')
        if 'treefontsize' in default:
            result['treefontsize'] = default.getint('treefontsize')
        if 'docfontsize' in default:
            result['docfontsize'] = default.getint('docfontsize')
        return result

    def check_and_add_additional_settings(self, data):
        """ Newer features include width and height settings for many dialogs and main window.
        timestamp format.
        dialog_crossovers IS dialog relations
        :param data:  dictionary of most or all settings
        :return: dictionary of all settings
        """

        dict_len = len(data)
        keys = ['mainwindow_w', 'mainwindow_h',
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
        'dialogcases_splitter0', 'dialogcases_splitter1',
        'dialogcasefilemanager_splitter0', 'dialogcasefilemanager_splitter1',
        'timestampformat', 'speakernameformat',
        'video_w', 'video_h',
        'codeav_abs_pos_x', 'codeav_abs_pos_y',
        'viewav_abs_pos_x', 'viewav_abs_pos_y',
        'viewav_video_pos_x', 'viewav_video_pos_y',
        'codeav_video_pos_x', 'codeav_video_pos_y',
        'dialogcodeav_splitter_0','dialogcodeav_splitter_1',
        'dialogcodeav_splitter_h0','dialogcodeav_splitter_h1',
        'dialogcodecrossovers_w', 'dialogcodecrossovers_h',
        'dialogcodecrossovers_splitter0', 'dialogcodecrossovers_splitter1',
        'dialogmanagelinks_w', 'dialogmanagelinks_h',
        'docfontsize',
        'dialogreport_file_summary_splitter0', 'dialogreport_file_summary_splitter0',
        'dialogreport_code_summary_splitter0', 'dialogreport_code_summary_splitter0',
        'stylesheet'
        ]
        for key in keys:
            if key not in data:
                data[key] = 0
                if key == "timestampformat":
                    data[key] = "[hh.mm.ss]"
                if key == "speakernameformat":
                    data[key] = "[]"
        # write out new ini file, if needed
        if len(data) > dict_len:
            self.write_config_ini(data)
        return data

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
        QTreeWidget::branch:selected {border-left: 2px solid red; color: #eeeeee;}\n\
        QTreeWidget {font-size: 12px;}"
        style_dark = style_dark.replace("* {font-size: 12", "* {font-size:" + str(settings.get('fontsize')))
        style_dark = style_dark.replace("QTreeWidget {font-size: 12", "QTreeWidget {font-size: " + str(settings.get('treefontsize')))

        style = "* {font-size: 12px; color: #000000;}\n\
        QWidget:focus {border: 2px solid #f89407;}\n\
        QComboBox:hover,QPushButton:hover {border: 2px solid #ffaa00;}\n\
        QGroupBox {border: None;}\n\
        QGroupBox:focus {border: 3px solid #ffaa00;}\n\
        QTextEdit:focus {border: 2px solid #ffaa00;}\n\
        QListWidget::item:selected {border-left: 2px solid red; color: #000000;}\n\
        QTableWidget:focus {border: 3px solid #ffaa00;}\n\
        QTreeWidget::branch:selected {border-left: 2px solid red; color: #000000;}\n\
        QTreeWidget {font-size: 12px;}"
        style = style.replace("* {font-size: 12", "* {font-size:" + str(settings.get('fontsize')))
        style = style.replace("QTreeWidget {font-size: 12", "QTreeWidget {font-size: " + str(settings.get('treefontsize')))

        if self.settings['stylesheet'] == 'dark':
            return style_dark
        return style

    def load_settings(self):
        result = self._load_config_ini()
        if not len(result):
            self.write_config_ini(self.default_settings)
            logger.info('Initialized config.ini')
            result = self._load_config_ini()
        if result['codername'] == "":
            result['codername'] = "default"
        result = self.check_and_add_additional_settings(result)
        #TODO TEMPORARY delete in 2022
        if result['speakernameformat'] == 0:
            result['speakernameformat'] = "[]"
        if result['stylesheet'] == 0:
            result['stylesheet'] = "original"
        return result

    @property
    def default_settings(self):
        """ Standard Settings for config.ini file. """
        return {
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
            cur.execute("select name, id, fulltext, memo, owner, date from source where fulltext is not null order by name")
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
            cur.execute("select name, jid, jentry, owner, date from journal")
        keys = 'name', 'jid', 'jentry', 'owner', 'date'
        result = []
        for row in cur.fetchall():
            result.append(dict(zip(keys, row)))
        return result

    def get_coder_names_in_project(self):
        """ Get all coder names from all tables and from the config.ini file
        Possible design flaw is that codernames are not stored in a specific table in the database.
        """

        # The coder name may be stored in the config.ini file, so need to add it here as it may not be obtained from the sql
        coder_names = [self.settings['codername']]
        # Try except, as there may not be an open project
        try:
            cur = self.conn.cursor()
            sql = "select owner from code_image union select owner from code_text union select owner from code_av "
            sql += "union select owner from cases union select owner from source union select owner from code_name"
            cur.execute(sql)
            res = cur.fetchall()
            for r in res:
                if r[0] not in coder_names:
                    coder_names.append(r[0])
        except:
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
    #dialog_list = []  # keeps active and track of non-modal windows
    recent_projects = []  # a list of recent projects for the qmenu

    def __init__(self, app, force_quit=False):
        """ Set up user interface from ui_main.py file. """
        self.app = app
        self.force_quit = force_quit
        sys.excepthook = exception_handler
        QtWidgets.QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.get_latest_github_release()
        try:
            w = int(self.app.settings['mainwindow_w'])
            h = int(self.app.settings['mainwindow_h'])
            if h > 40 and w > 50:
                self.resize(w, h)
        except:
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
        self.ui.actionProject_Exchange_Export.triggered.connect(self.REFI_project_export)
        self.ui.actionREFI_Codebook_export.triggered.connect(self.REFI_codebook_export)
        self.ui.actionREFI_Codebook_import.triggered.connect(self.REFI_codebook_import)
        self.ui.actionREFI_QDA_Project_import.triggered.connect(self.REFI_project_import)
        self.ui.actionRQDA_Project_import.triggered.connect(self.rqda_project_import)
        self.ui.actionExit.triggered.connect(self.closeEvent)
        self.ui.actionExit.setShortcut('Ctrl+Q')

        # file cases and journals menu
        self.ui.actionManage_files.triggered.connect(self.manage_files)
        #self.ui.actionManage_files.setShortcut('Alt+F') Affects code AV function
        self.ui.actionManage_journals.triggered.connect(self.journals)
        self.ui.actionManage_journals.setShortcut('Alt+J')
        self.ui.actionManage_cases.triggered.connect(self.manage_cases)
        self.ui.actionManage_cases.setShortcut('Alt+C')
        self.ui.actionManage_attributes.triggered.connect(self.manage_attributes)
        self.ui.actionManage_attributes.setShortcut('Alt+A')
        self.ui.actionImport_survey.triggered.connect(self.import_survey)
        self.ui.actionImport_survey.setShortcut('Alt+I')
        self.ui.actionManage_bad_links_to_files.triggered.connect(self.manage_bad_file_links)

        # codes menu
        self.ui.actionCodes.triggered.connect(self.text_coding)
        self.ui.actionCodes.setShortcut('Alt+T')
        self.ui.actionCode_image.triggered.connect(self.image_coding)
        self.ui.actionCode_image.setShortcut('Alt+I')
        self.ui.actionCode_audio_video.triggered.connect(self.av_coding)
        self.ui.actionCode_audio_video.setShortcut('Alt+V')
        self.ui.actionExport_codebook.triggered.connect(self.codebook)

        # reports menu
        self.ui.actionCoding_reports.triggered.connect(self.report_coding)
        #self.ui.actionCoding_reports.setShortcut('Ctrl+R') Affects code AV function
        self.ui.actionCoding_comparison.triggered.connect(self.report_coding_comparison)
        self.ui.actionCode_frequencies.triggered.connect(self.report_code_frequencies)
        self.ui.actionView_Graph.triggered.connect(self.view_graph_original)
        self.ui.actionView_Graph.setShortcut('Ctrl+G')
        self.ui.actionCode_relations.triggered.connect(self.report_code_relations)
        self.ui.actionFile_summary.triggered.connect(self.report_file_summary)
        self.ui.actionCode_summary.triggered.connect(self.report_code_summary)
        #TODO self.ui.actionText_mining.triggered.connect(self.text_mining)
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
        # removes the qtdesigner default action. Also clears the section when a proect is closed
        # so that the options for recent projects can be updated
        self.ui.menuOpen_Recent_Project.clear()
        #TODO must be a better way to do this
        for i, r in enumerate(self.recent_projects):
            display_name = r
            if len(r.split("|")) == 2:
                display_name = r.split("|")[1]
            if i == 0:
                action0 = QtWidgets.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action0)
                action0.triggered.connect(self.project0)
            if i == 1:
                action1 = QtWidgets.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action1)
                action1.triggered.connect(self.project1)
            if i == 2:
                action2 = QtWidgets.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action2)
                action2.triggered.connect(self.project2)
            if i == 3:
                action3 = QtWidgets.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action3)
                action3.triggered.connect(self.project3)
            if i == 4:
                action4 = QtWidgets.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action4)
                action4.triggered.connect(self.project4)
            if i == 5:
                action5 = QtWidgets.QAction(display_name, self)
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
        self.ui.actionCategories.setEnabled(False)
        self.ui.actionView_Graph.setEnabled(False)
        # reports menu
        self.ui.actionCoding_reports.setEnabled(False)
        self.ui.actionCoding_comparison.setEnabled(False)
        self.ui.actionCode_frequencies.setEnabled(False)
        self.ui.actionCode_relations.setEnabled(False)
        self.ui.actionText_mining.setEnabled(False)
        self.ui.actionSQL_statements.setEnabled(False)
        self.ui.actionFile_summary.setEnabled(False)
        self.ui.actionCode_summary.setEnabled(False)
        # help menu
        self.ui.actionSpecial_functions.setEnabled(False)

    def show_menu_options(self):
        """ Project opened, show most menu options.
         Disable project import options. """

        # project menu
        self.ui.actionClose_Project.setEnabled(True)
        self.ui.actionProject_Memo.setEnabled(True)
        self.ui.actionProject_Exchange_Export.setEnabled(True)
        self.ui.actionREFI_Codebook_export.setEnabled(True)
        self.ui.actionREFI_Codebook_import.setEnabled(True)
        self.ui.actionREFI_QDA_Project_import.setEnabled(False)
        self.ui.actionRQDA_Project_import.setEnabled(False)
        self.ui.actionExport_codebook.setEnabled(True)
        # files cases journals menu
        self.ui.actionManage_files.setEnabled(True)
        self.ui.actionManage_journals.setEnabled(True)
        self.ui.actionManage_cases.setEnabled(True)
        self.ui.actionManage_attributes.setEnabled(True)
        self.ui.actionImport_survey.setEnabled(True)
        # codes menu
        self.ui.actionCodes.setEnabled(True)
        self.ui.actionCode_image.setEnabled(True)
        self.ui.actionCode_audio_video.setEnabled(True)
        self.ui.actionCategories.setEnabled(True)
        self.ui.actionView_Graph.setEnabled(True)
        # reports menu
        self.ui.actionCoding_reports.setEnabled(True)
        self.ui.actionCoding_comparison.setEnabled(True)
        self.ui.actionCode_frequencies.setEnabled(True)
        self.ui.actionCode_relations.setEnabled(True)
        self.ui.actionSQL_statements.setEnabled(True)
        self.ui.actionFile_summary.setEnabled(True)
        self.ui.actionCode_summary.setEnabled(True)
        # help menu
        self.ui.actionSpecial_functions.setEnabled(True)

        #TODO FOR FUTURE EXPANSION text mining
        self.ui.actionText_mining.setEnabled(False)
        self.ui.actionText_mining.setVisible(False)

    def settings_report(self):
        """ Display general settings and project summary """

        msg = _("Settings")
        msg += "\n========\n"
        msg += _("Coder") + ": " + self.app.settings['codername'] + "\n"
        msg += _("Font") + ": " + self.app.settings['font'] + " " + str(self.app.settings['fontsize']) + "\n"
        msg += _("Tree font size") + ": " + str(self.app.settings['treefontsize']) + "\n"
        msg += _("Working directory") + ": " +  self.app.settings['directory']
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
        self.ui.textEdit.textCursor().movePosition(QtGui.QTextCursor.End)
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
        """ Compare two or more coders using Cohens Kappa. """

        self.ui.label_reports.hide()
        ui = DialogReportCoderComparisons(self.app, self.ui.textEdit)
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
        ui = ViewGraphOriginal(self.app)
        ui.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.tab_layout_helper(self.ui.tab_reports, ui)

    def help(self):
        """ Display manual in browser. """

        webbrowser.open("https://github.com/ccbogel/QualCoder/wiki")

    def about(self):
        """ About dialog. """

        ui = DialogInformation(self.app, "About", "")
        ui.exec_()

    def special_functions(self):
        """ User requested special functions dialog. """

        ui = DialogSpecialFunctions(self.app, self.ui.textEdit, self.ui.tab_coding)
        ui.exec_()

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
        ui.exec_()
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
        ui = DialogManageLinks(self.app, self.ui.textEdit, self.ui.tab_coding, self.ui.tab_reports)
        self.tab_layout_helper(self.ui.tab_manage, ui)
        bad_links = self.app.check_bad_file_links()
        if bad_links == []:
            self.ui.actionManage_bad_links_to_files.setEnabled(False)

    def journals(self):
        """ Create and edit journals. """

        self.ui.label_manage.hide()
        ui = DialogJournals(self.app, self.ui.textEdit)
        ui.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.tab_layout_helper(self.ui.tab_manage, ui)

    def text_coding(self):
        """ Create edit and delete codes. Apply and remove codes and annotations to the
        text in imported text files. """

        files = self.app.get_text_filenames()
        if len(files) > 0:
            self.ui.label_coding.hide()
            ui = DialogCodeText(self.app, self.ui.textEdit, self.ui.tab_reports)
            ui.setAttribute(QtCore.Qt.WA_DeleteOnClose)
            self.tab_layout_helper(self.ui.tab_coding, ui)
        else:
            msg = _("This project contains no text files.")
            Message(self.app, _('No text files'), msg).exec_()

    def image_coding(self):
        """ Create edit and delete codes. Apply and remove codes to the image (or regions)
        """

        files = self.app.get_image_filenames()
        if len(files) > 0:
            self.ui.label_coding.hide()
            ui = DialogCodeImage(self.app, self.ui.textEdit, self.ui.tab_reports)
            ui.setAttribute(QtCore.Qt.WA_DeleteOnClose)
            self.tab_layout_helper(self.ui.tab_coding, ui)
        else:
            msg = _("This project contains no image files.")
            Message(self.app, _('No image files'), msg).exec_()

    def av_coding(self):
        """ Create edit and delete codes. Apply and remove codes to segments of the
        audio or video file. Added try block in case VLC bindings do not work. """

        files = self.app.get_av_filenames()
        if len(files) == 0:
            msg = _("This project contains no audio/video files.")
            Message(self.app, _('No a/v files'), msg).exec_()
            return

        self.ui.label_coding.hide()
        try:
            ui = DialogCodeAV(self.app, self.ui.textEdit, self.ui.tab_reports)
            ui.setAttribute(QtCore.Qt.WA_DeleteOnClose)
            self.tab_layout_helper(self.ui.tab_coding, ui)
        except Exception as e:
            logger.debug(str(e))
            print(e)
            QtWidgets.QMessageBox.warning(None, "A/V Coding", str(e), QtWidgets.QMessageBox.Ok)

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
            layout.addWidget(ui)
            tab_widget.setLayout(layout)
        else:
            # Remove widgets from layout
            for i in reversed(range(contents.count())):
                contents.itemAt(i).widget().close()
                contents.itemAt(i).widget().setParent(None)
            contents.addWidget(ui)

    def codebook(self):
        """ Export a text file code book of categories and codes.
        """

        Codebook(self.app, self.ui.textEdit)

    def REFI_project_export(self):
        """ Export the project as a qpdx zipped folder.
         Follows the REFI Project Exchange standards.
         CURRENTLY IN TESTING AND NOT COMPLETE NOR VALIDATED.
         NEED TO TEST RELATIVE EXPORTS, TIMESTAMPS AND TRANSCRIPTION
        """

        RefiExport(self.app, self.ui.textEdit, "project")

    def REFI_codebook_export(self):
        """ Export the codebook as .qdc
        Follows the REFI standard version 1.0. https://www.qdasoftware.org/
        """
        #
        RefiExport(self.app, self.ui.textEdit, "codebook")

    def REFI_codebook_import(self):
        """ Import a codebook .qdc into an opened project.
        Follows the REFI-QDA standard version 1.0. https://www.qdasoftware.org/
         """

        RefiImport(self.app, self.ui.textEdit, "qdc")

    def REFI_project_import(self):
        """ Import a qpdx QDA project into a new project space.
        Follows the REFI standard.
        CURRENTLY IN TESTING AND NOT COMPLETE NOR VALIDATED.
         NEED TO TEST RELATIVE EXPORTS, TIMESTAMPS AND TRANSCRIPTION
         """

        self.close_project()
        self.ui.textEdit.append(_("IMPORTING REFI-QDA PROJECT"))
        msg = _(
            "Step 1: You will be asked for a new QualCoder project name.\nStep 2: You will be asked for the QDPX file.")
        Message(self.app, _('REFI-QDA import steps'), msg).exec_()
        self.new_project()
        # check project created successfully
        if self.app.project_name == "":
            Message(self.app, _("Project creation"), _("REFI-QDA Project not successfully created"), "warning").exec_()
            return

        RefiImport(self.app, self.ui.textEdit, "qdpx")
        self.project_summary_report()

    def rqda_project_import(self):
        """ Import an RQDA format project into a new project space. """

        self.close_project()
        self.ui.textEdit.append(_("IMPORTING RQDA PROJECT"))
        msg = _("Step 1: You will be asked for a new QualCoder project name.\nStep 2: You will be asked for the RQDA file.")
        Message(self.app, _('RQDA import steps'), msg).exec_()
        self.new_project()
        # check project created successfully
        if self.app.project_name == "":
            Message(self.app, _('Project creation'), _("Project not successfully created"), "critical").exec_()
            return
        Rqda_import(self.app, self.ui.textEdit)
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
            QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No)
            if reply == QtWidgets.QMessageBox.Yes:
                # close project before the dialog list, as close project clean the dialogs
                self.close_project()
                #self.dialog_list = None
                if self.app.conn is not None:
                    try:
                        self.app.conn.commit()
                        self.app.conn.close()
                    except:
                        pass
                QtWidgets.qApp.quit()
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
        v2 ha added column in code_text table to link to avid in code_av table.
        v3 has added columns in code_text, code_image, code_av for important - to mark particular important codings.
        """

        self.app = App()
        if self.app.settings['directory'] == "":
            self.app.settings['directory'] = os.path.expanduser('~')
        project_path = QtWidgets.QFileDialog.getSaveFileName(self,
            _("Enter project name"), self.app.settings['directory'], ".qda")[0]
        if project_path == "":
            Message(self.app, _("Project"), _("No project created."), "critical").exec_()
            return

        # Add suffix to project name if it already exists
        counter = 0
        extension = ""
        while os.path.exists(project_path + extension + ".qda"):
            print("C", counter, project_path + extension + ".qda")
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
        except Exception as e:
            logger.critical(_("Project creation error ") + str(e))
            Message(self.app, _("Project"), self.app.project_path + _(" not successfully created"), "critical").exec_()
            self.app = App()
            return
        self.app.project_name = self.app.project_path.rpartition('/')[2]
        self.app.settings['directory'] = self.app.project_path.rpartition('/')[0]
        self.app.create_connection(self.app.project_path)
        cur = self.app.conn.cursor()
        cur.execute("CREATE TABLE project (databaseversion text, date text, memo text,about text, bookmarkfile integer, bookmarkpos integer);")
        cur.execute("CREATE TABLE source (id integer primary key, name text, fulltext text, mediapath text, memo text, owner text, date text, unique(name));")
        cur.execute("CREATE TABLE code_image (imid integer primary key,id integer,x1 integer, y1 integer, width integer, height integer, cid integer, memo text, date text, owner text, important integer);")
        cur.execute("CREATE TABLE code_av (avid integer primary key,id integer,pos0 integer, pos1 integer, cid integer, memo text, date text, owner text, important integer);")
        cur.execute("CREATE TABLE annotation (anid integer primary key, fid integer,pos0 integer, pos1 integer, memo text, owner text, date text, unique(fid,pos0,pos1,owner));")
        cur.execute("CREATE TABLE attribute_type (name text primary key, date text, owner text, memo text, caseOrFile text, valuetype text);")
        cur.execute("CREATE TABLE attribute (attrid integer primary key, name text, attr_type text, value text, id integer, date text, owner text);")
        cur.execute("CREATE TABLE case_text (id integer primary key, caseid integer, fid integer, pos0 integer, pos1 integer, owner text, date text, memo text);")
        cur.execute("CREATE TABLE cases (caseid integer primary key, name text, memo text, owner text,date text, constraint ucm unique(name));")
        cur.execute("CREATE TABLE code_cat (catid integer primary key, name text, owner text, date text, memo text, supercatid integer, unique(name));")
        cur.execute("CREATE TABLE code_text (ctid integer primary key, cid integer, fid integer,seltext text, pos0 integer, pos1 integer, owner text, date text, memo text, avid integer, important integer, unique(cid,fid,pos0,pos1, owner));")
        cur.execute("CREATE TABLE code_name (cid integer primary key, name text, memo text, catid integer, owner text,date text, color text, unique(name));")
        cur.execute("CREATE TABLE journal (jid integer primary key, name text, jentry text, date text, owner text);")
        cur.execute("INSERT INTO project VALUES(?,?,?,?,?,?)", ('v4', datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), '', qualcoder_version, 0, 0))
        self.app.conn.commit()
        try:
            # get and display some project details
            self.ui.textEdit.append("\n" + _("New project: ") + self.app.project_path + _(" created."))
            #self.settings['projectName'] = self.path.rpartition('/')[2]
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
        except Exception as e:
            msg = _("Problem creating database ")
            logger.warning(msg + self.app.project_path + " Exception:" + str(e))
            self.ui.textEdit.append("\n" + msg + "\n" + self.app.project_path)
            self.ui.textEdit.append(str(e))
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
        ui.exec_()
        #ss = self.app.merge_settings_with_default_stylesheet(self.app.settings)
        #self.setStyleSheet(ss)
        self.settings_report()
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        if current_coder != self.app.settings['codername']:
            self.ui.textEdit.append(_("Coder name changed to: ") + self.app.settings['codername'])
            # Close all opened dialogs as coder name needs to change everywhere
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
        ui.exec_()
        if memo != ui.memo:
            cur.execute('update project set memo=?', (ui.memo,))
            self.app.conn.commit()
            self.ui.textEdit.append(_("Project memo entered."))
            self.app.delete_backup = False

    def open_project(self, path="", newproject="no"):
        """ Open an existing project.
        if set, also save a backup datetime stamped copy at the same time.
        Do not backup on a newly created project, as it wont contain data.
        A backup is created if settings backuop is True.
        The backup is deleted, if no changes occured.
        Backups are created using the date and 24 hour suffix: _BKUP_yyyymmdd_hh
        Backups are not replaced within the same hour.
        param:
            path: if path is "" then get the path from a dialog, otherwise use the supplied path
            newproject: yes or no  if yes then do not make an initial backup
        """

        default_directory = self.app.settings['directory']
        if path == "" or path is False:
            if default_directory == "":
                default_directory = os.path.expanduser('~')
            path = QtWidgets.QFileDialog.getExistingDirectory(self,
                _('Open project directory'), default_directory)
        if path == "" or path is False:
            return
        self.close_project()
        msg = ""
        # New path variable from recent_projects.txt contains time | path
        # Older variable only listed the project path
        splt = path.split("|")
        proj_path = ""
        if len(splt) == 1:
            proj_path = splt[0]
        if len(splt) == 2:
            proj_path = splt[1]
        if len(path) > 3 and proj_path[-4:] == ".qda":
            try:
                self.app.create_connection(proj_path)
            except Exception as e:
                self.app.conn = None
                msg += " " + str(e)
                logger.debug(msg)
        if self.app.conn is None:
            msg += "\n" + proj_path
            Message(self.app, _("Cannot open file"), msg, "critical").exec_()
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
        except Exception as e:
            logger.debug("This in not a QualCoder database " + str(e))
            self.close_project()
            return

        #TODO Potential design flaw to have the current coders name in the config.ini file
        #TODO as is would change when opening different projects
        # Check that the coder name from setting ini file is in the project
        # If not then replace with a name in the project
        names = self.app.get_coder_names_in_project()
        if self.app.settings['codername'] not in names and len(names) > 0:
            self.app.settings['codername'] = names[0]
            self.app.write_config_ini(self.app.settings)
            self.ui.textEdit.append(_("Default coder name changed to: ") + names[0])
        # get and display some project details
        self.app.append_recent_project(self.app.project_path)
        self.fill_recent_projects_menu_actions()
        self.setWindowTitle("QualCoder " + self.app.project_name)

        # Check avid column in code_text table, v2
        cur = self.app.conn.cursor()
        try:
            cur.execute("select avid from code_text")
        except:
            try:
                cur.execute("ALTER TABLE code_text ADD avid integer")
                self.app.conn.commit()
            except Exception as e:
                logger.debug(str(e))
        try:
            cur.execute("select bookmarkfile from project")
        except:
            try:
                cur.execute("ALTER TABLE project ADD bookmarkfile integer")
                self.app.conn.commit()
                cur.execute("ALTER TABLE project ADD bookmarkpos integer")
                self.app.conn.commit()
            except Exception as e:
                logger.debug(str(e))
        # Check important column in code_text, code_image, code_av v3
        cur = self.app.conn.cursor()
        try:
            cur.execute("select important from code_text")
        except:
            try:
                cur.execute("ALTER TABLE code_text ADD important integer")
                self.app.conn.commit()
            except Exception as e:
                logger.debug(str(e))
                cur = self.app.conn.cursor()
        try:
            cur.execute("select important from code_av")
        except:
            try:
                cur.execute("ALTER TABLE code_av ADD important integer")
                self.app.conn.commit()
            except Exception as e:
                logger.debug(str(e))
        cur = self.app.conn.cursor()
        try:
            cur.execute("select important from code_image")
        except:
            try:
                cur.execute("ALTER TABLE code_image ADD important integer")
                self.app.conn.commit()
            except Exception as e:
                logger.debug(str(e))
        # database version v4
        try:
            cur.execute("select ctid from code_text")
        except:  # sqlite3.OperationalError as e:
            cur.execute(
                "CREATE TABLE code_text2 (ctid integer primary key, cid integer, fid integer,seltext text, pos0 integer, pos1 integer, owner text, date text, memo text, avid integer, important integer, unique(cid,fid,pos0,pos1, owner))")
            self.app.conn.commit()
            sql = "insert into code_text2 (cid, fid, seltext, pos0, pos1, owner, date, memo, avid, important) "
            sql += "select cid, fid, seltext, pos0, pos1, owner, date, memo, avid, important from code_text"
            cur.execute(sql)
            self.app.conn.commit()
            cur.execute("drop table code_text")
            cur.execute("alter table code_text2 rename to code_text")
            cur.execute('update project set databaseversion="v4", about=?', [qualcoder_version])
            self.app.conn.commit()

        # Save a date and 24hour stamped backup
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
        if res != []:
            self.ui.textEdit.append(_("Deleting code_text coding to deleted files: ") + str(res))
        for r in res:
            cur.execute("delete from code_text where fid=?", [r[0]])
        sql = "select code_image.id from code_image where code_image.id not in (select source.id from source)"
        cur.execute(sql)
        res = cur.fetchall()
        if res != []:
            self.ui.textEdit.append(_("Deleting code_image coding to deleted files: ") + str(res))
        for r in res:
            cur.execute("delete from code_image where id=?", [r[0]])
        sql = "select code_av.id from code_av where code_av.id not in (select source.id from source)"
        cur.execute(sql)
        res = cur.fetchall()
        if res != []:
            self.ui.textEdit.append(_("Deleting code_av coding to deleted files: ") + str(res))
        for r in res:
            cur.execute("delete from code_av where id=?", [r[0]])
        self.app.conn.commit()
        # Vacuum database
        cur.execute("vacuum")
        self.app.conn.commit()

    def save_backup(self):
        """ Save a date and hours stamped backup.
        Do not backup if the name already exists.
        A back up can be generated in the subsequent hour."""

        nowdate = datetime.datetime.now().astimezone().strftime("%Y%m%d_%H")  # -%M-%S")
        backup = self.app.project_path[0:-4] + "_BKUP_" + nowdate + ".qda"
        # Do not try and create another backup with same date and hour
        result = os.path.exists(backup)
        if result:
            return
        if self.app.settings['backup_av_files'] == 'True':
            try:
                shutil.copytree(self.app.project_path, backup)
            except FileExistsError as e:
                msg = _("There is already a backup with this name")
                print(str(e) + "\n" + msg)
                logger.warning(_(msg) + "\n" + str(e))
        else:
            shutil.copytree(self.app.project_path, backup,
            ignore=shutil.ignore_patterns('*.mp3', '*.wav', '*.mp4', '*.mov', '*.ogg', '*.wmv', '*.MP3',
                '*.WAV', '*.MP4', '*.MOV', '*.OGG', '*.WMV'))
            self.ui.textEdit.append(_("WARNING: audio and video files NOT backed up. See settings."))
        self.ui.textEdit.append(_("Project backup created: ") + backup)
        # delete backup path - delete the backup if no changes occurred in the project during the session
        self.app.delete_backup_path_name = backup

    def project_summary_report(self):
        """ Add a summary of the project to the text edit.
         Display project memo, and code, attribute, journal, files frequencies.
         Also detect and display bad links to linked files. """

        os_type = platform.system()
        if self.app.conn is None:
            return
        cur = self.app.conn.cursor()
        cur.execute("select databaseversion, date, memo, about, bookmarkfile,bookmarkpos from project")
        result = cur.fetchall()[-1]
        self.project['databaseversion'] = result[0]
        self.project['date'] = result[1]
        self.project['memo'] = result[2]
        #self.project['about'] = result[3]
        msg = "\n" + _("PROJECT SUMMARY")
        msg += "\n========\n"
        msg += _("Date time now: ") + datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M") + "\n"
        msg += self.app.project_name + "\n"
        msg += _("Project path: ") + self.app.project_path + "\n"
        #msg += _("Database version: ") + self.project['databaseversion'] + ". "
        msg+= _("Project date: ") + str(self.project['date']) + "\n"
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
        cur.execute("select name from source where id=?", [result[4],])
        bookmark_filename = cur.fetchone()
        if bookmark_filename is not None and result[5] is not None:
            msg += "\nText Bookmark: " + str(bookmark_filename[0])
            msg += ", position: " + str(result[5])

        if platform.system() == "Windows":
            msg += "\n" + _("Directory (folder) paths / represents \\")
        self.ui.textEdit.append(msg)

        bad_links = self.app.check_bad_file_links()
        if bad_links:
            self.ui.textEdit.append('<span style="color:red">' + _("Bad links to files") + "</span>")
            for l in bad_links:
                self.ui.textEdit.append('<span style="color:red">' + l['name'] + "   " + l['mediapath'] + '</span>')
            self.ui.actionManage_bad_links_to_files.setEnabled(True)
        else:
            self.ui.actionManage_bad_links_to_files.setEnabled(False)
        self.ui.textEdit.append("\n========\n")
        self.ui.textEdit.textCursor().movePosition(QtGui.QTextCursor.End)
        self.ui.tabWidget.setCurrentWidget(self.ui.tab_action_log)

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
        try:
            self.app.conn.commit()
            self.app.conn.close()
        except:
            pass
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

    def delete_backup_folders(self):
        """ Delete the most current backup created on opening a project,
        providing the project was not changed in any way.
        Delete oldest backups if more than 5 are created.
        Backup name format:
        directories/projectname_BKUP_yyyymmdd_hh.qda
        Keep up to FIVE backups only. """

        if self.app.project_path == "":
            return
        if self.app.delete_backup_path_name != "" and self.app.delete_backup:
            try:
                shutil.rmtree(self.app.delete_backup_path_name)
            except Exception as e:
                print(str(e))

        # Get a list of backup folders for current project
        parts = self.app.project_path.split('/')
        projectname_and_suffix = parts[-1]
        directory = self.app.project_path[0:-len(projectname_and_suffix)]
        projectname = projectname_and_suffix[:-4]
        projectname_and_bkup = projectname + "_BKUP_"
        lenname = len(projectname_and_bkup)
        files_folders = os.listdir(directory)
        backups = []
        for f in files_folders:
            if f[0:lenname] == projectname_and_bkup and f[-4:] == ".qda":
                backups.append(f)
        # Sort newest to oldest, and remove any that are more than fifth position in the list
        backups.sort(reverse=True)
        to_remove = []
        if len(backups) > 5:
            to_remove = backups[5:]
        if to_remove == []:
            return
        for f in to_remove:
            try:
                shutil.rmtree(directory + f)
                self.ui.textEdit.append(_("Deleting: ") + directory + f)
            except Exception as e:
                print(str(e))

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
                #asset = _json['assets'][0]
                #urllib.request.urlretrieve(asset['browser_download_url'], asset['name'])
        except Exception as e:
            print(e)
            logger.debug(str(e))
            #self.ui.textEdit.append(_("Could not detect latest release from Github\n") + str(e))

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
        #print("ext data dir: ", ext_data_dir)
        locale_dir = os.path.join(ext_data_dir, 'qualcoder')
        locale_dir = os.path.join(locale_dir, 'locale')
        #locale_dir = os.path.join(locale_dir, lang)
        #locale_dir = os.path.join(locale_dir, 'LC_MESSAGES')
    #print("locale dir: ", locale_dir)
    #print("LISTDIR: ", os.listdir(locale_dir))
    #getlang = gettext.translation('en', localedir=locale_dir, languages=['en'])
    translator = gettext.translation(domain='default', localedir=locale_dir, fallback=True)
    if lang in ["de", "el", "es", "fr", "it", "jp", "pt"]:
        # qt translator applies to ui designed GUI widgets only
        qt_locale_dir = os.path.join(locale_dir, lang)
        qt_locale_file = os.path.join(qt_locale_dir, "app_" + lang + ".qm")
        #print("qt qm translation file: ", qt_locale_file)
        qt_translator = QtCore.QTranslator()
        qt_translator.load(qt_locale_file)
        ''' Below for pyinstaller and obtaining app_lang.qm data file from .qualcoder folder
        A solution to this error [Errno 13] Permission denied:
        Replace 'lang' with the short language name, e.g. app_de.qm '''
        if qt_translator.isEmpty():
            print("trying to load translation qm file from .qualcoder folder")
            qm = os.path.join(home, '.qualcoder')
            qm = os.path.join(qm, 'app_' + lang + '.qm')
            print("qm file located at: ", qm)
            qt_translator.load(qm)
            print("Success")
            if qt_translator.isEmpty():
                print("No .qm translation file loaded")
                msg = "Copy app_" + lang + ".qm file from downloaded QualCoder-Master/qualcoder/locale folder into the home/.qualcoder folder"
                Message(qual_app,"No .qm file", msg).exec_()
                install_language(lang, "qm")

        app.installTranslator(qt_translator)
        '''Below for pyinstaller and obtaining mo data file from .qualcoder folder
        A solution to this [Errno 13] Permission denied:
        Must have the folder lang/LC_MESSAGES/lang.mo  in the .qualcoder folder
        Replace 'lang' with the language short name e.g. de, el, es ...
        '''
        try:
            translator = gettext.translation(lang, localedir=locale_dir, languages=[lang])
            print("locale directory for python translations: ", locale_dir)
        except Exception as e:
            print("Error accessing python translations mo file")
            print(e)
            print("locale directory for python translations: ", locale_dir)
            try:
                print("trying folder: home/.qualcoder/" + lang + "/LC_MESSAGES/" + lang + ".mo")
                mo_dir = os.path.join(home, '.qualcoder')
                translator = gettext.translation(lang, localedir=mo_dir, languages=[lang])
                print("Success")
            except:
                print("No .mo translation file loaded")
                msg = "Copy folder path with " + lang + ".mo file from downloaded QualCoder-Master/qualcoder/locale folder into home/.qualcoder/" + lang + "/LC_MESSAGES/" + lang + ".mo"
                Message(qual_app,"No .qm file", msg).exec_()
                install_language(lang, "mo")

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
        ex.open_project(path=proj_path)
    sys.exit(app.exec_())

def install_language(lang, type):
    """ Mainly for pyinstaller on Windows. Cannot access language ddta files.
     So, recreate them from base64 data into home/.qualcoder folder. """

    # Install Qt translation file into folder .qualcoder
    if type == "qm":
        qm = os.path.join(home, '.qualcoder')
        qm = os.path.join(qm, 'app_' + lang + '.qm')
        data = None
        if lang == "de":
            data = de_qm
        if lang == "el":
            data = el_qm
        if lang == "es":
            data = es_qm
        if lang == "fr":
            data = fr_qm
        if lang == "it":
            data = it_qm
        if lang == "jp":
            data = jp_qm
        if lang == "pt":
            data = pt_qm
        if data is None:
            return
        with open(qm, 'wb') as file_:
            decoded_data = base64.decodebytes(data)
            file_.write(decoded_data)



if __name__ == "__main__":
    gui()
