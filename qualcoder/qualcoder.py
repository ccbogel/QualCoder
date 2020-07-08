#!/usr/bin/python
# -*- coding: utf-8 -*-

'''
Copyright (c) 2019 Colin Curtain

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
'''

import configparser
import datetime
import gettext
import logging
from logging.handlers import RotatingFileHandler
import os
import re
import shutil
import sys
import sqlite3
import traceback
import webbrowser
from PyQt5 import QtCore, QtGui, QtWidgets
from settings import DialogSettings
from attributes import DialogManageAttributes
from cases import DialogCases
from codebook import Codebook
from code_text import DialogCodeText
from dialog_sql import DialogSQL
from GUI.ui_main import Ui_MainWindow
from import_survey import DialogImportSurvey
from information import DialogInformation
from journals import DialogJournals
from manage_files import DialogManageFiles
from memo import DialogMemo
from refi import Refi_export, Refi_import
from reports import DialogReportCodes, DialogReportCoderComparisons, DialogReportCodeFrequencies
from rqda import Rqda_import
#from text_mining import DialogTextMining
from view_av import DialogCodeAV
from view_graph_original import ViewGraphOriginal
from view_image import DialogCodeImage

path = os.path.abspath(os.path.dirname(__file__))
home = os.path.expanduser('~')
if not os.path.exists(home + '/.qualcoder'):
    try:
        os.mkdir(home + '/.qualcoder')
    except Exception as e:
        print("Cannot add .qualcoder folder to home directory\n" + str(e))
        raise
logfile = home + '/.qualcoder/QualCoder.log'
# Delete log file on first opening so that file sizes are more managable
try:
    os.remove(logfile)
except OSError:
    pass

logging.basicConfig(format='%(asctime)s %(levelname)s %(name)s.%(funcName)s %(message)s',
     datefmt='%Y/%m/%d %H:%M:%S', filename=logfile)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = RotatingFileHandler(logfile, maxBytes=4000, backupCount=2)
logger.addHandler(handler)

def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception : ") + text)
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), text)


class App(object):
    """ General methods for loading settings and recent project stored in .qualcoder folder.
    Savable settings does not contain project name, project path or db connection.
    """

    conn = None
    project_path = ""
    project_name = ""
    # Can delete the most current back up if the project has not been altered
    delete_backup_path_name = ""
    delete_backup = True

    def __init__(self):
        sys.excepthook = exception_handler
        self.conn = None
        self.project_path = ""
        self.project_name = ""
        self.delete_backup = True
        self.delete_backup_path_name = ""
        self.confighome = os.path.expanduser('~/.qualcoder')
        self.configpath = os.path.join(self.confighome, 'config.ini')
        self.persist_path = os.path.join(self.confighome, 'recent_projects.txt')
        self.settings = self.load_settings()

    def read_previous_project_paths(self):
        """ Recent project path is stored in .qualcoder/recent_projects.txt """

        res = []
        try:
            with open(self.persist_path, 'r') as f:
                for line in f:
                    res.append(line.strip())
        except:
            logger.debug('No previous projects found')
        return res

    def append_recent_project(self, path):
        """ Add project path as first entry to .qualcoder/recent_projects.txt """

        res = self.read_previous_project_paths()
        if not res or path != res[0]:
            res.append(path)
            with open(self.persist_path, 'w') as f:
                for i, line in enumerate(reversed(res)):
                    f.write(line)
                    f.write(os.linesep)
                    if i > 10:
                        break

    def get_most_recent_projectpath(self):
        """ Get most recent project path from .qualcoder/recent_projects.txt """

        res = self.read_previous_project_paths()
        if res:
            return res[0]

    def create_connection(self, project_path):
        """ Create connection to recent project and load codes, categories and model """

        self.project_path = project_path
        self.project_name = project_path.split('/')[-1]
        self.conn = sqlite3.connect(os.path.join(project_path, 'data.qda'))

    def get_code_names(self):
        cur = self.conn.cursor()
        cur.execute("select name, memo, owner, date, cid, catid, color from code_name")
        result = cur.fetchall()
        res = []
        for row in result:
            res.append({'name': row[0], 'memo': row[1], 'owner': row[2], 'date': row[3],
            'cid': row[4], 'catid': row[5], 'color': row[6]})
        return res

    def get_filenames(self):
        """ Get all filenames. """
        cur = self.conn.cursor()
        cur.execute("select id, name from source")
        result = cur.fetchall()
        res = []
        for row in result:
            res.append({'id': row[0], 'name': row[1]})
        return res

    def get_text_filenames(self):
        """ Get filenames of textfiles only. """
        cur = self.conn.cursor()
        cur.execute("select id, name from source where mediapath is Null")
        result = cur.fetchall()
        res = []
        for row in result:
            res.append({'id': row[0], 'name': row[1]})
        return res

    def get_annotations(self):
        """ Get annotations for text files. """

        cur = self.conn.cursor()
        cur.execute("select anid, fid, pos0, pos1, memo, owner, date from annotation where owner=?",
            [self.settings['codername'], ])
        result = cur.fetchall()
        res = []
        for row in result:
            res.append({'anid': row[0], 'fid': row[1], 'pos0': row[2],
            'pos1': row[3], 'memo': row[4], 'owner': row[5], 'date': row[6]})
        return res

    def get_data(self):
        """ Called from init and gets all the codes and categories.
        Called from ? """

        categories = []
        cur = self.conn.cursor()
        cur.execute("select name, catid, owner, date, memo, supercatid from code_cat order by name")
        result = cur.fetchall()
        for row in result:
            categories.append({'name': row[0], 'catid': row[1], 'owner': row[2],
            'date': row[3], 'memo': row[4], 'supercatid': row[5]})
        code_names = []
        cur = self.conn.cursor()
        cur.execute("select name, memo, owner, date, cid, catid, color from code_name")
        result = cur.fetchall()
        for row in result:
            code_names.append({'name': row[0], 'memo': row[1], 'owner': row[2], 'date': row[3],
            'cid': row[4], 'catid': row[5], 'color': row[6]})
        return code_names, categories

    def write_config_ini(self, settings):
        config = configparser.ConfigParser()
        config['DEFAULT'] = settings
        with open(self.configpath, 'w') as configfile:
            config.write(configfile)

    def _load_config_ini(self):
        config = configparser.ConfigParser()
        config.read(self.configpath)
        default =  config['DEFAULT']
        result = dict(default)
        # convert to int can be removed when all manual styles are removed
        if 'fontsize' in default:
            result['fontsize'] = default.getint('fontsize')
        if 'treefontsize' in default:
            result['treefontsize'] = default.getint('treefontsize')
        return result

    def merge_settings_with_default_stylesheet(self, settings):
        """ Originally had separate stylesheet file. Now stylesheet is coded because
        avoids potential data file import errors with pyinstaller. """

        stylesheet = "* {font-size: 16px;}\n\
        QWidget:focus {border: 2px solid #f89407;}\n\
        QComboBox:hover,QPushButton:hover {border: 2px solid #ffaa00;}\n\
        QGroupBox {border: None;}\n\
        QGroupBox:focus {border: 3px solid #ffaa00;}\n\
        QTextEdit:focus {border: 2px solid #ffaa00;}\n\
        QTableWidget:focus {border: 3px solid #ffaa00;}\n\
        QTreeWidget {font-size: 14px;}"
        stylesheet = stylesheet.replace("* {font-size: 16", "* {font-size:" + str(settings.get('fontsize')))
        stylesheet = stylesheet.replace("QTreeWidget {font-size: 14", "QTreeWidget {font-size: " + str(settings.get('treefontsize')))
        return stylesheet

    def load_settings(self):
        result = self._load_config_ini()
        if not len(result):
            self.write_config_ini(self.default_settings)
            logger.info('Initilaized config.ini')
            result = self._load_config_ini()
        return result

    @property
    def default_settings(self):
        return {
            'codername': 'default',
            'font': 'Noto Sans',
            'fontsize': 14,
            'treefontsize': 12,
            'directory': os.path.expanduser('~'),
            'showids': False,
            'language': 'en',
            'backup_on_open': True,
            'backup_av_files': True,
        }

    def get_file_texts(self, fileids=None):
        """ Get the texts of all text files as a list of dictionaries.
        param: fileids - a list of fileids or None """

        cur = self.conn.cursor()
        if fileids is not None:
            cur.execute(
                "select name, id, fulltext, memo, owner, date from source where id in (?) and fulltext is not null",
                fileids
            )
        else:
            cur.execute("select name, id, fulltext, memo, owner, date from source where fulltext is not null order by name")
        res = []
        for row in cur.fetchall():
            res.append({
            'name': row[0],
            'id': row[1],
            'fulltext': row[2],
            'memo': row[3],
            'owner': row[4],
            'date': row[5],
        })
        return res

    def get_code_texts(self, text):
        cur = self.conn.cursor()
        codingsql = "select cid, fid, seltext, pos0, pos1, owner, date, memo from code_text where seltext like ?"
        cur.execute(
            codingsql,
            [text],
        )
        keys = 'cid', 'fid', 'seltext', 'pos0', 'pos1', 'owner', 'date', 'memo'
        for res in cur.fetchall():
            yield dict(zip(keys, res))


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
    dialogList = []  # keeps active and track of non-modal windows

    def __init__(self, app, force_quit=False):
        """ Set up user interface from ui_main.py file. """
        self.app = app
        self.force_quit = force_quit
        sys.excepthook = exception_handler
        QtWidgets.QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        #self.setWindowIcon(QtGui.QIcon("GUI/qualcoder.png"))
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
        self.ui.actionOpen_Project.triggered.connect(self.open_project)
        self.ui.actionProject_Memo.triggered.connect(self.project_memo)
        self.ui.actionClose_Project.triggered.connect(self.close_project)
        self.ui.actionSettings.triggered.connect(self.change_settings)
        self.ui.actionProject_Exchange_Export.triggered.connect(self.REFI_project_export)
        self.ui.actionREFI_Codebook_export.triggered.connect(self.REFI_codebook_export)
        self.ui.actionREFI_Codebook_import.triggered.connect(self.REFI_codebook_import)
        self.ui.actionREFI_QDA_Project_import.triggered.connect(self.REFI_project_import)
        self.ui.actionRQDA_Project_import.triggered.connect(self.rqda_project_import)
        self.ui.actionExit.triggered.connect(self.closeEvent)

        # file cases and journals menu
        self.ui.actionManage_files.triggered.connect(self.manage_files)
        self.ui.actionManage_journals.triggered.connect(self.journals)
        self.ui.actionManage_cases.triggered.connect(self.manage_cases)
        self.ui.actionManage_attributes.triggered.connect(self.manage_attributes)
        self.ui.actionImport_survey.triggered.connect(self.import_survey)

        # codes menu
        self.ui.actionCodes.triggered.connect(self.text_coding)
        self.ui.actionCode_image.triggered.connect(self.image_coding)
        self.ui.actionCode_audio_video.triggered.connect(self.av_coding)
        self.ui.actionExport_codebook.triggered.connect(self.codebook)

        # reports menu
        self.ui.actionCoding_reports.triggered.connect(self.report_coding)
        self.ui.actionCoding_comparison.triggered.connect(self.report_coding_comparison)
        self.ui.actionCode_frequencies.triggered.connect(self.report_code_frequencies)
        self.ui.actionView_Graph.triggered.connect(self.view_graph_original)
        #TODO self.ui.actionText_mining.triggered.connect(self.text_mining)
        self.ui.actionSQL_statements.triggered.connect(self.report_sql)

        # help menu
        self.ui.actionContents.triggered.connect(self.help)
        self.ui.actionAbout.triggered.connect(self.about)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.settings_report()

    def hide_menu_options(self):
        """ No project opened, hide most menu options.
         Enable project import options."""

        # project menu
        self.ui.actionClose_Project.setEnabled(False)
        self.ui.actionProject_Memo.setEnabled(False)
        self.ui.actionProject_Exchange_Export.setEnabled(False)
        self.ui.actionREFI_Codebook_export.setEnabled(False)
        self.ui.actionREFI_Codebook_import.setEnabled(False)
        self.ui.actionREFI_QDA_Project_import.setEnabled(True)
        self.ui.actionRQDA_Project_import.setEnabled(True)
        # files cases journals menu
        self.ui.actionManage_files.setEnabled(False)
        self.ui.actionManage_journals.setEnabled(False)
        self.ui.actionManage_cases.setEnabled(False)
        self.ui.actionManage_attributes.setEnabled(False)
        self.ui.actionImport_survey.setEnabled(False)
        # codes menu
        self.ui.actionCodes.setEnabled(False)
        self.ui.actionCode_image.setEnabled(False)
        self.ui.actionCode_audio_video.setEnabled(False)
        self.ui.actionCategories.setEnabled(False)
        self.ui.actionView_Graph.setEnabled(False)
        self.ui.actionExport_codebook.setEnabled(False)
        # reports menu
        self.ui.actionCoding_reports.setEnabled(False)
        self.ui.actionCoding_comparison.setEnabled(False)
        self.ui.actionCode_frequencies.setEnabled(False)
        self.ui.actionText_mining.setEnabled(False)
        self.ui.actionSQL_statements.setEnabled(False)

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
        self.ui.actionExport_codebook.setEnabled(True)
        # reports menu
        self.ui.actionCoding_reports.setEnabled(True)
        self.ui.actionCoding_comparison.setEnabled(True)
        self.ui.actionCode_frequencies.setEnabled(True)
        self.ui.actionSQL_statements.setEnabled(True)
        #TODO FOR FUTURE EXPANSION text mining
        self.ui.actionText_mining.setEnabled(False)
        self.ui.actionText_mining.setVisible(False)

    def settings_report(self):
        msg = _("Settings")
        msg += "\n========\n"
        msg += _("Coder") + ": " + self.app.settings['codername'] + "\n"
        msg += _("Font") + ": " + self.app.settings['font'] + " " + str(self.app.settings['fontsize']) + "\n"
        msg += _("Tree font size") + ": " + str(self.app.settings['treefontsize']) + "\n"
        msg += _("Directory") + ": " + self.app.settings['directory'] + "\n"
        msg += _("Project_path:") + self.app.project_path + "\n"
        msg += _("Show IDs") + ": " + str(self.app.settings['showids']) + "\n"
        msg += _("Language") + ": " + self.app.settings['language'] + "\n"
        msg += _("Backup on open") + ": " + str(self.app.settings['backup_on_open']) + "\n"
        msg += _("Backup AV files") + ": " + str(self.app.settings['backup_av_files'])
        msg += "\n========"
        self.ui.textEdit.append(msg)

    def report_sql(self):
        """ Run SQL statements on database. """

        ui = DialogSQL(self.app, self.ui.textEdit)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    """def text_mining(self):
        ''' text analysis of files / cases / codings.
        NOT CURRENTLY IMPLEMENTED, FOR FUTURE EXPANSION.
        '''

        ui = DialogTextMining(self.app, self.ui.textEdit)
        ui.show()"""

    def report_coding_comparison(self):
        """ Compare two or more coders using Cohens Kappa. """

        for d in self.dialogList:
            if type(d).__name__ == "DialogCoderComparison":
                return
        ui = DialogReportCoderComparisons(self.app, self.ui.textEdit)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def report_code_frequencies(self):
        """ Show code frequencies overall and by coder. """

        for d in self.dialogList:
            if type(d).__name__ == "DialogCodeFrequencies":
                return
        ui = DialogReportCodeFrequencies(self.app, self.ui.textEdit, self.dialogList)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def report_coding(self):
        """ Report on coding and categories. """

        ui = DialogReportCodes(self.app, self.ui.textEdit, self.dialogList)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def view_graph_original(self):
        """ Show acyclic graph of codes and categories. """

        ui = ViewGraphOriginal(self.app)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def help(self):
        """ Display help information in browser. """

        webbrowser.open(path + "/GUI/QualCoder_Manual.pdf")
        self.clean_dialog_refs()

    def about(self):
        """ About dialog. """

        for d in self.dialogList:
            if type(d).__name__ == "DialogInformation" and d.windowTitle() == "About":
                return
        ui = DialogInformation("About", "")
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def manage_attributes(self):
        """ Create, edit, delete, rename attributes. """

        ui = DialogManageAttributes(self.app, self.ui.textEdit)
        ui.exec_()
        self.clean_dialog_refs()

    def import_survey(self):
        """ Import survey flat sheet: csv file.
        Create cases and assign attributes to cases.
        Identify qualitative questions and assign these data to the source table for
        coding and review. Modal dialog. """

        ui = DialogImportSurvey(self.app, self.ui.textEdit)
        ui.exec_()
        self.clean_dialog_refs()

    def manage_cases(self):
        """ Create, edit, delete, rename cases, add cases to files or parts of
        files, add memos to cases. """

        for d in self.dialogList:
            if type(d).__name__ == "DialogCases":
                return
        ui = DialogCases(self.app, self.ui.textEdit)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def manage_files(self):
        """ Create text files or import files from odt, docx, html and
        plain text. Rename, delete and add memos to files.
        """

        for d in self.dialogList:
            if type(d).__name__ == "DialogManageFiles":
                return
        ui = DialogManageFiles(self.app, self.ui.textEdit)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def journals(self):
        """ Create and edit journals. """

        for d in self.dialogList:
            if type(d).__name__ == "DialogJournals":
                return
        ui = DialogJournals(self.app, self.ui.textEdit)
        ui.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def text_coding(self):
        """ Create edit and delete codes. Apply and remove codes and annotations to the
        text in imported text files. """

        ui = DialogCodeText(self.app, self.ui.textEdit, self.dialogList)
        ui.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def image_coding(self):
        """ Create edit and delete codes. Apply and remove codes to the image (or regions)
        """

        ui = DialogCodeImage(self.app, self.ui.textEdit, self.dialogList)
        ui.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def av_coding(self):
        """ Create edit and delete codes. Apply and remove codes to segements of the
        audio or video file. Added try block in case VLC bindings do not work. """

        try:
            ui = DialogCodeAV(self.app, self.ui.textEdit, self.dialogList)
            ui.setAttribute(QtCore.Qt.WA_DeleteOnClose)
            self.dialogList.append(ui)
            ui.show()
        except Exception as e:
            logger.debug(str(e))
            print(e)
            QtWidgets.QMessageBox.warning(None, "A/V Coding", str(e), QtWidgets.QMessageBox.Ok)
        self.clean_dialog_refs()

    def codebook(self):
        """ Export a text file code book of categories and codes.
        """

        Codebook(self.app, self.ui.textEdit)

    def REFI_project_export(self):
        """ Export the project as a qpdx zipped folder.
         Follows the REFI Project Exchange standards.
         CURRENTLY IN TESTING AND NOT COMPLETE NOR VALIDATED.
        VARIABLES ARE NOT SUCCESSFULLY EXPORTED YET.
        CURRENTLY GIFS ARE EXPORTED UNCHANGED (NEED TO BE PNG OR JPG)"""

        Refi_export(self.app, self.ui.textEdit, "project")
        msg = "NOT FULLY TESTED - EXPERIMENTAL\n"
        QtWidgets.QMessageBox.warning(None, "REFI QDA Project export", msg)

    def REFI_codebook_export(self):
        """ Export the codebook as .qdc
        Follows the REFI standard version 1.0. https://www.qdasoftware.org/
        """
        #
        Refi_export(self.app, self.ui.textEdit, "codebook")

    def REFI_codebook_import(self):
        """ Import a codebook .qdc into an opened project.
        Follows the REFI-QDA standard version 1.0. https://www.qdasoftware.org/
         """

        Refi_import(self.app, self.ui.textEdit, "qdc")

    def REFI_project_import(self):
        """ Import a qpdx QDA project into a new project space.
        Follows the REFI standard. """

        self.close_project()
        self.ui.textEdit.append("IMPORTING REFI-QDA PROJECT")
        self.new_project()
        # check project created successfully
        if self.app.project_name == "":
            QtWidgets.QMessageBox.warning(None, "Project creation", "Project not successfully created")
            return

        Refi_import(self.app, self.ui.textEdit, "qdpx")
        msg = "EXPERIMENTAL - NOT FULLY TESTED\n"
        msg += "PDFs not imported\n"
        msg += "Audio, video, transcripts, transcript codings and synchpoints not tested.\n"
        msg += "Sets and Graphs not imported as QualCoders does not have this functionality.\n"
        msg += "External sources over 2GB not imported."
        QtWidgets.QMessageBox.warning(None, "REFI QDA Project import", msg)

    def rqda_project_import(self):
        """ Import an RQDA format project into a new poject space. """

        self.close_project()
        self.ui.textEdit.append("IMPORTING RQDA PROJECT")
        self.new_project()
        # check project created successfully
        if self.app.project_name == "":
            QtWidgets.QMessageBox.warning(None, "Project creation", "Project not successfully created")
            return
        Rqda_import(self.app, self.ui.textEdit)

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
                self.dialogList = None

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
        v2 had added column in code_text table to link to avid in code_av table.
        """

        self.app = App()
        if self.app.settings['directory'] == "":
            self.app.settings['directory'] = os.path.expanduser('~')
        self.app.project_path = QtWidgets.QFileDialog.getSaveFileName(self,
            _("Enter project name"), self.app.settings['directory'], ".qda")[0]
        if self.app.project_path == "":
            QtWidgets.QMessageBox.warning(None, _("Project"), _("No project created."))
            return
        if self.app.project_path.find(".qda") == -1:
            self.app.project_path = self.app.project_path + ".qda"
        try:
            os.mkdir(self.app.project_path)
            os.mkdir(self.app.project_path + "/images")
            os.mkdir(self.app.project_path + "/audio")
            os.mkdir(self.app.project_path + "/video")
            os.mkdir(self.app.project_path + "/documents")
        except Exception as e:
            logger.critical(_("Project creation error ") + str(e))
            QtWidgets.QMessageBox.warning(None, _("Project"), _("No project created. Exiting. ") + str(e))
            exit(0)
        self.app.project_name = self.app.project_path.rpartition('/')[2]
        self.app.settings['directory'] = self.app.project_path.rpartition('/')[0]
        self.app.create_connection(self.app.project_path)
        cur = self.app.conn.cursor()
        cur.execute("CREATE TABLE project (databaseversion text, date text, memo text,about text);")
        cur.execute("CREATE TABLE source (id integer primary key, name text, fulltext text, mediapath text, memo text, owner text, date text, unique(name));")
        cur.execute("CREATE TABLE code_image (imid integer primary key,id integer,x1 integer, y1 integer, width integer, height integer, cid integer, memo text, date text, owner text);")
        cur.execute("CREATE TABLE code_av (avid integer primary key,id integer,pos0 integer, pos1 integer, cid integer, memo text, date text, owner text);")
        cur.execute("CREATE TABLE annotation (anid integer primary key, fid integer,pos0 integer, pos1 integer, memo text, owner text, date text);")
        cur.execute("CREATE TABLE attribute_type (name text primary key, date text, owner text, memo text, caseOrFile text, valuetype text);")
        cur.execute("CREATE TABLE attribute (attrid integer primary key, name text, attr_type text, value text, id integer, date text, owner text);")
        cur.execute("CREATE TABLE case_text (id integer primary key, caseid integer, fid integer, pos0 integer, pos1 integer, owner text, date text, memo text);")
        cur.execute("CREATE TABLE cases (caseid integer primary key, name text, memo text, owner text,date text, constraint ucm unique(name));")
        cur.execute("CREATE TABLE code_cat (catid integer primary key, name text, owner text, date text, memo text, supercatid integer, unique(name));")
        cur.execute("CREATE TABLE code_text (cid integer, fid integer,seltext text, pos0 integer, pos1 integer, owner text, date text, memo text, avid integer, unique(cid,fid,pos0,pos1, owner));")
        cur.execute("CREATE TABLE code_name (cid integer primary key, name text, memo text, catid integer, owner text,date text, color text, unique(name));")
        cur.execute("CREATE TABLE journal (jid integer primary key, name text, jentry text, date text, owner text);")
        cur.execute("INSERT INTO project VALUES(?,?,?,?)", ('v2',datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),'','QualCoder'))
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
        self.open_project(self.app.project_path)

    def change_settings(self):
        """ Change default settings - the coder name, font, font size. Non-modal.
        Backup options """

        ui = DialogSettings(self.app)
        ui.exec_()
        self.settings_report()
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)

    def project_memo(self):
        """ Give the entire project a memo. Modal dialog. """

        cur = self.app.conn.cursor()
        cur.execute("select memo from project")
        memo = cur.fetchone()[0]
        ui = DialogMemo(self.app, _("Memo for project ") + self.app.project_name,
            memo)
        self.dialogList.append(ui)
        ui.exec_()
        if memo != ui.memo:
            cur.execute('update project set memo=?', (ui.memo,))
            self.app.conn.commit()
            self.ui.textEdit.append(_("Project memo entered."))
            self.app.delete_backup = False

    def open_project(self, path=""):
        """ Open an existing project.
        Also save a backup datetime stamped copy at the same time. """

        if self.app.project_name != "":
            self.close_project()
        self.setWindowTitle("QualCoder" + _("Open Project"))
        default_directory = self.app.settings['directory']
        if path == "" or path is False:
            if default_directory == "":
                default_directory = os.path.expanduser('~')
            path = QtWidgets.QFileDialog.getExistingDirectory(self,
                _('Open project directory'), default_directory)
        if path == "" or path is False:
            return
        msg = ""
        if len(path) > 3 and path[-4:] == ".qda":
            try:
                self.app.create_connection(path)
            except Exception as e:
                self.app.conn = None
                msg += " " + str(e)
                logger.debug(msg)
        if self.app.conn is None:
            msg += "\n" + path
            QtWidgets.QMessageBox.warning(None, _("Cannot open file"),
                msg)
            self.app.project_path = ""
            self.app.project_name = ""
            return

        # get and display some project details
        self.app.append_recent_project(self.app.project_path)
        self.setWindowTitle("QualCoder " + self.app.project_name)
        cur = self.app.conn.cursor()
        cur.execute("select databaseversion, date, memo, about from project")
        result = cur.fetchall()[-1]
        self.project['databaseversion'] = result[0]
        self.project['date'] = result[1]
        self.project['memo'] = result[2]
        self.project['about'] = result[3]

        # check avid column in code_text table
        # database version < 2
        try:
            cur.execute("select avid from code_text")
        except:
            cur.execute("ALTER TABLE code_text ADD avid integer;")
            self.app.conn.commit()

        # Save a datetime stamped backup
        if self.app.settings['backup_on_open'] == 'True':
            nowdate = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup = self.app.project_path[0:-4] + "_BACKUP_" + nowdate + ".qda"
            if self.app.settings['backup_av_files'] == 'True':
                shutil.copytree(self.app.project_path, backup)
            else:
                shutil.copytree(self.app.project_path, backup, ignore=shutil.ignore_patterns('*.mp3','*.wav','*.mp4', '*.mov','*.ogg','*.wmv','*.MP3','*.WAV','*.MP4', '*.MOV','*.OGG','*.WMV'))
                self.ui.textEdit.append(_("WARNING: audio and video files NOT backed up. See settings."))
            self.ui.textEdit.append(_("Project backup created: ") + backup)

            self.app.delete_backup_path_name = backup
            delete_backup = True

        self.ui.textEdit.append(_("Project Opened: ") + self.app.project_name
            + "\n========\n"
            + _("Path: ") + self.app.project_path + "\n"
            + _("Directory: ") + self.app.settings['directory'] + "\n"
            + _("Database version: ") + self.project['databaseversion'] + ". "
            + _("Date: ") + str(self.project['date']) + "\n"
            + _("About: ") + self.project['about']
            + "\n========\n")
        self.show_menu_options()

    def close_project(self):
        """ Close an open project. """

        self.ui.textEdit.append("Closing project: " + self.app.project_name + "\n========\n")
        try:
            self.app.conn.commit()
            self.app.conn.close()
        except:
            pass

        #print(self.app.delete_backup_path_name)
        #print(self.app.delete_backup)
        # delete the backup folder
        if self.app.delete_backup_path_name != "" and self.app.delete_backup:
            try:
                shutil.rmtree(self.app.delete_backup_path_name)
            except Exception as e:
                print(str(e))

        self.app.conn = None
        self.app.project_path = ""
        self.app.project_name = ""
        self.app.delete_backup_path_name = ""
        self.app.delete_backup = True
        self.project = {"databaseversion": "", "date": "", "memo": "", "about": ""}
        self.hide_menu_options()
        self.clean_dialog_refs()
        self.setWindowTitle("QualCoder")

    def clean_dialog_refs(self):
        """ Test the list of dialog refs to see if they have been cleared
        and create a new list of current dialogs.
        Also need to keep these dialog references to keep non-modal dialogs open.
        Non-modal example - having a journal open and a coding dialog. """

        tempList = []
        for d in self.dialogList:
            try:
                #logger.debug(str(d) + ", isVisible:" + str(d.isVisible()) + " Title:" + d.windowTitle())
                #d.windowTitle()
                if d.isVisible():
                    tempList.append(d)
            # RuntimeError: wrapped C/C++ object of type DialogSQL has been deleted
            except RuntimeError as e:
                logger.error(str(e))
        self.dialogList = tempList
        self.update_dialog_lists_in_modeless_dialogs()

    def update_dialog_lists_in_modeless_dialogs(self):
        ''' This is to assist: Update code and category tree in DialogCodeImage,
        DialogCodeAV, DialogCodeText, DialogReportCodes '''

        for d in self.dialogList:
            if isinstance(d, DialogCodeText):
                d.dialog_list = self.dialogList
            if isinstance(d, DialogCodeAV):
                d.dialog_list = self.dialogList
            if isinstance(d, DialogCodeImage):
                d.dialog_list = self.dialogList
            if isinstance(d, DialogReportCodes):
                d.dialog_list = self.dialogList


def gui():
    qual_app = App()
    settings = qual_app.load_settings()
    project_path = qual_app.get_most_recent_projectpath()
    app = QtWidgets.QApplication(sys.argv)
    QtGui.QFontDatabase.addApplicationFont("GUI/NotoSans-hinted/NotoSans-Regular.ttf")
    QtGui.QFontDatabase.addApplicationFont("GUI/NotoSans-hinted/NotoSans-Bold.ttf")
    stylesheet = qual_app.merge_settings_with_default_stylesheet(settings)
    app.setStyleSheet(stylesheet)
    # Try and load language settings from file stored in home/.qualcoder/
    # translator applies to ui designed GUI widgets only
    lang = settings.get('language','en')
    getlang = gettext.translation('en', localedir=path +'/locale', languages=['en'])
    if lang != "en":
        translator = QtCore.QTranslator()
        if lang == "fr":
            translator.load(path + "/locale/fr/app_fr.qm")
            getlang = gettext.translation('fr', localedir=path + '/locale', languages=['fr'])
        if lang == "de":
            translator.load(path + "/locale/de/app_de.qm")
            getlang = gettext.translation('de', localedir=path + '/locale', languages=['de'])
        if lang == "es":
            translator.load(path + "/locale/es/app_es.qm")
            getlang = gettext.translation('es', localedir=path + '/locale', languages=['es'])
        app.installTranslator(translator)
    getlang.install()
    ex = MainWindow(qual_app)
    if project_path:
        ex.open_project(path=project_path)
    sys.exit(app.exec_())


if __name__ == "__main__":
    gui()
