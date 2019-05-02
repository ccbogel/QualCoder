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

import datetime
import gettext
import logging
import os
import shutil
import sys
import sqlite3
import traceback

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
from refi import Refi
from reports import DialogReportCodes, DialogReportCoderComparisons, DialogReportCodeFrequencies
#from text_mining import DialogTextMining
from view_av import DialogCodeAV
from view_graph import ViewGraph
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
     datefmt='%Y/%m/%d %I:%M', filename=logfile,
     level=logging.DEBUG)
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception : ") + text)
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), text)


class MainWindow(QtWidgets.QMainWindow):
    """ Main GUI window.
    Project data is stored in a directory with .qda suffix
    core data is stored in data.qda sqlite file.
    Journal and coding dialogs can be shown non-modally - multiple dialogs open.
    There is a risk of a clash if two coding windows are open with the same file text or
    two journals open with the same journal entry. """

    settings = {"conn": None, "directory": home, "projectName": "", "showIDs": False,
    'path': home, "codername": "default", "font": "Noto Sans", "fontsize": 10,
    'treefontsize': 10, "language": "en"}
    project = {"databaseversion": "", "date": "", "memo": "", "about": ""}
    dialogList = []  # keeps active and track of non-modal windows

    def __init__(self):
        """ Set up user interface from ui_main.py file. """

        sys.excepthook = exception_handler
        QtWidgets.QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.hide_menu_options()
        self.init_ui()
        self.conn = None
        self.show()

    def init_ui(self):
        """ Set up menu triggers """

        # project menu
        self.ui.actionCreate_New_Project.triggered.connect(self.new_project)
        self.ui.actionOpen_Project.triggered.connect(self.open_project)
        self.ui.actionProject_Memo.triggered.connect(self.project_memo)
        self.ui.actionClose_Project.triggered.connect(self.close_project)
        self.ui.actionSettings.triggered.connect(self.change_settings)
        self.ui.actionProject_Exchange_Export.triggered.connect(self.project_exchange_export)
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
        self.ui.actionView_Graph.triggered.connect(self.view_graph)

        # reports menu
        self.ui.actionCoding_reports.triggered.connect(self.report_coding)
        self.ui.actionCoding_comparison.triggered.connect(self.report_coding_comparison)
        self.ui.actionCode_frequencies.triggered.connect(self.report_code_frequencies)
        #TODO self.ui.actionText_mining.triggered.connect(self.text_mining)
        self.ui.actionSQL_statements.triggered.connect(self.report_sql)

        # help menu
        self.ui.actionContents.triggered.connect(self.help)
        self.ui.actionAbout.triggered.connect(self.about)

        # load_settings from file stored in home/.qualcoder/
        try:
            with open(home + '/.qualcoder/QualCoder_settings.txt') as f:
                txt = f.read()
                txt = txt.split("\n")
                self.settings['codername'] = txt[0]
                self.settings['font'] = txt[1]
                self.settings['fontsize'] = int(txt[2])
                self.settings['treefontsize'] = int(txt[3])
                self.settings['directory'] = txt[4]
                self.settings['showIDs'] = False
                if txt[5] == "True":
                    self.settings['showIDs'] = True
                # With workarounds for an empty or non-existant language line
                try:
                    self.settings['language'] = txt[6]
                    if txt[6] == "":
                        self.settings['language'] = "en"
                except:
                    self.settings['language'] = "en"
        except:
            f = open(home + '/.qualcoder/QualCoder_settings.txt', 'w')
            f.write("default\nNoto Sans\n10\n10\n" + home + "\nFalse\nen")
            f.close()
        new_font = QtGui.QFont(self.settings['font'], self.settings['fontsize'], QtGui.QFont.Normal)
        self.setFont(new_font)
        self.settings_report()

    def hide_menu_options(self):
        """ No project opened, hide these menu options """

        self.ui.actionClose_Project.setEnabled(False)
        self.ui.actionProject_Memo.setEnabled(False)
        self.ui.actionProject_Exchange_Export.setEnabled(False)
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
        """ Project opened, show these menu options """

        self.ui.actionClose_Project.setEnabled(True)
        self.ui.actionProject_Memo.setEnabled(True)
        self.ui.actionProject_Exchange_Export.setEnabled(True)
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

    def settings_report(self):
        msg = _("Settings")
        msg += "\n========\n"
        msg += _("Coder") + ": " + self.settings['codername'] + "\n"
        msg += _("Font") + ": " + self.settings['font'] + " " + str(self.settings['fontsize'])
        msg += ". "
        msg += _("Code font size") + ": " + self.settings['font'] + " " + str(self.settings['treefontsize']) + "\n"
        msg += _("Directory") + ": " + self.settings['directory'] + "\n"
        msg += _("Show IDs") + ": " + str(self.settings['showIDs']) + "\n"
        msg += _("Language") + ": " + self.settings['language']
        msg += "\n========"
        self.ui.textEdit.append(msg)

    def report_sql(self):
        """ Run SQL statements on database. """

        ui = DialogSQL(self.settings, self.ui.textEdit)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    """def text_mining(self):
        ''' text analysis of files / cases / codings.
        NOT CURRENTLY IMPLEMENTED, FOR FUTURE EXPANSION.
        '''

        ui = DialogTextMining(self.settings, self.ui.textEdit)
        ui.show()"""

    def report_coding_comparison(self):
        """ Compare two or more coders using Cohens Kappa. """

        for d in self.dialogList:
            if type(d).__name__ == "DialogCoderComparison":
                return
        ui = DialogReportCoderComparisons(self.settings, self.ui.textEdit)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def report_code_frequencies(self):
        """ Show code frequencies overall and by coder. """

        for d in self.dialogList:
            if type(d).__name__ == "DialogCodeFrequencies":
                return
        ui = DialogReportCodeFrequencies(self.settings, self.ui.textEdit)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def report_coding(self):
        """ Report on coding and categories. """

        ui = DialogReportCodes(self.settings, self.ui.textEdit)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def view_graph(self):
        """ Show acyclic graph of codes and categories. """

        ui = ViewGraph(self.settings)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def help(self):
        """ Help dialog. """

        ui = DialogInformation("Help contents", "GUI/en_Help.html")
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def about(self):
        """ About dialog. """

        for d in self.dialogList:
            if type(d).__name__ == "DialogInformation" and d.windowTitle() == "About":
                return
        ui = DialogInformation("About", "GUI/About.html")
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def manage_attributes(self):
        """ Create, edit, delete, rename attributes. """

        ui = DialogManageAttributes(self.settings, self.ui.textEdit)
        ui.exec_()
        self.clean_dialog_refs()

    def import_survey(self):
        """ Import survey flat sheet: csv file.
        Create cases and assign attributes to cases.
        Identify qualitative questions and assign these data to the source table for
        coding and review. Modal dialog. """

        ui = DialogImportSurvey(self.settings, self.ui.textEdit)
        ui.exec_()
        self.clean_dialog_refs()

    def manage_cases(self):
        """ Create, edit, delete, rename cases, add cases to files or parts of
        files, add memos to cases. """

        for d in self.dialogList:
            if type(d).__name__ == "DialogCases":
                return
        ui = DialogCases(self.settings, self.ui.textEdit)
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
        ui = DialogManageFiles(self.settings, self.ui.textEdit)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def journals(self):
        """ Create and edit journals. """

        for d in self.dialogList:
            if type(d).__name__ == "DialogJournals":
                return
        ui = DialogJournals(self.settings, self.ui.textEdit)
        ui.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def text_coding(self):
        """ Create edit and delete codes. Apply and remove codes and annotations to the
        text in imported text files. """

        ui = DialogCodeText(self.settings, self.ui.textEdit)
        ui.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def image_coding(self):
        """ Create edit and delete codes. Apply and remove codes to the image (or regions)
        """

        ui = DialogCodeImage(self.settings, self.ui.textEdit)
        ui.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def av_coding(self):
        """ Create edit and delete codes. Apply and remove codes to segements of the
        audio or video file. Added try block in case VLC bindings do not work. """

        try:
            ui = DialogCodeAV(self.settings, self.ui.textEdit)
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

        Codebook(self.settings, self.ui.textEdit)

    def project_exchange_export(self):
        """ Export the project as a qpdx zipped folder.
         Follows the REFI Project Exchange standards.
         CURRENTLY IN TESTING AND NOT COMPLETE NOR VALIDATED.
        VARIABLES ARE NOT SUCCESSFULLY EXPORTED YET.
        CURRENTLY GIFS ARE EXPORTED UNCHANGED (NEED TO BE PNG OR JPG)"""

        Refi(self.settings, self.ui.textEdit)

    def closeEvent(self, event):
        """ Override the QWindow close event.
        Close all dialogs and database connection.
        If selected via menu option exit: event == False
        If selected via window x close: event == QtGui.QCloseEvent
        """

        quit_msg = _("Are you sure you want to quit?")
        reply = QtWidgets.QMessageBox.question(self, 'Message', quit_msg,
        QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.Yes:
            self.dialogList = None
            if self.settings['conn'] is not None:
                try:
                    self.settings['conn'].commit()
                    self.settings['conn'].close()
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
        images, audio and video. """

        #logger.debug("settings[directory]:" + self.settings['directory'])
        self.settings['path'] = QtWidgets.QFileDialog.getSaveFileName(self,
            _("Enter project name"), self.settings['directory'], ".qda")[0]
        if self.settings['path'] == "":
            QtWidgets.QMessageBox.warning(None, _("Project"), _("No project created."))
            return
        if self.settings['path'].find(".qda") == -1:
            self.settings['path'] = self.settings['path'] + ".qda"
        try:
            os.mkdir(self.settings['path'])
            os.mkdir(self.settings['path'] + "/images")
            os.mkdir(self.settings['path'] + "/audio")
            os.mkdir(self.settings['path'] + "/video")
            os.mkdir(self.settings['path'] + "/documents")
        except Exception as e:
            logger.critical(_("Project creation error ") + str(e))
            QtWidgets.QMessageBox.warning(None, _("Project"), _("No project created. Exiting. ") + str(e))
            exit(0)
        self.settings['projectName'] = self.settings['path'].rpartition('/')[2]
        self.settings['directory'] = self.settings['path'].rpartition('/')[0]
        #try:
        self.settings['conn'] = sqlite3.connect(self.settings['path'] + "/data.qda")
        cur = self.settings['conn'].cursor()
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
        cur.execute("CREATE TABLE code_text (cid integer, fid integer,seltext text, pos0 integer, pos1 integer, owner text, date text, memo text, unique(cid,fid,pos0,pos1, owner));")
        cur.execute("CREATE TABLE code_name (cid integer primary key, name text, memo text, catid integer, owner text,date text, color text, unique(name));")
        cur.execute("CREATE TABLE journal (jid integer primary key, name text, jentry text, date text, owner text);")
        cur.execute("INSERT INTO project VALUES(?,?,?,?)", ('v1',datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),'','QualCoder'))
        self.settings['conn'].commit()
        try:
            # get and display some project details
            self.ui.textEdit.append("\n" + _("New project: ") + self.settings['path'] + _(" created."))
            #self.settings['projectName'] = self.path.rpartition('/')[2]
            self.ui.textEdit.append(_("Opening: ") + self.settings['path'])
            self.setWindowTitle("QualCoder " + self.settings['projectName'])
            cur = self.settings['conn'].cursor()
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
                + _("Coder:") + str(self.settings['codername']) + "\n"
                + "========")
        except Exception as e:
            msg = _("Problem creating database ")
            logger.warning(msg + self.settings['path'] + " Exception:" + str(e))
            self.ui.textEdit.append("\n" + msg + "\n" + self.settings['path'])
            self.ui.textEdit.append(str(e))
            self.close_project()
            return
        self.open_project(self.settings['path'])

    def change_settings(self):
        """ Change default settings - the coder name, font, font size. Non-modal. """

        ui = DialogSettings(self.settings)
        ui.exec_()
        self.settings_report()
        newfont = QtGui.QFont(self.settings['font'], self.settings['fontsize'], QtGui.QFont.Normal)
        self.setFont(newfont)

    def project_memo(self):
        """ Give the entire project a memo. Modal dialog. """

        cur = self.settings['conn'].cursor()
        cur.execute("select memo from project")
        memo = cur.fetchone()[0]
        ui = DialogMemo(self.settings, _("Memo for project ") + self.settings['projectName'],
            memo)
        self.dialogList.append(ui)
        ui.exec_()
        if memo != ui.memo:
            cur.execute('update project set memo=?', (ui.memo,))
            self.settings['conn'].commit()
            self.ui.textEdit.append(_("Project memo entered."))

    def open_project(self, path=""):
        """ Open an existing project.
        Also save a backup datetime stamped copy at the same time. """

        if self.settings['projectName'] != "":
            self.close_project()
        self.setWindowTitle("QualCoder" + _("Open Project"))
        if path == "" or path is False:
            path = QtWidgets.QFileDialog.getExistingDirectory(self,
                _('Open project directory'), self.settings['directory'])
        if path == "" or path is False:
            return
        if len(path) > 3 and path[-4:] == ".qda":
            self.settings['path'] = path
            msg = ""
            try:
                self.settings['conn'] = sqlite3.connect(self.settings['path'] + "/data.qda")
            except Exception as e:
                self.settings['conn'] = None
                msg += str(e)
                logger.debug(str(e))
        if self.settings['conn'] is None:
            QtWidgets.QMessageBox.warning(None, _("Cannot open file"),
                self.settings['path'] + _(" is not a .qda file "))
            self.settings['path'] = ""
            return
        # get and display some project details
        self.settings['path'] = path
        self.settings['projectName'] = self.settings['path'].rpartition('/')[2]
        self.settings['directory'] = self.settings['path'].rpartition('/')[0]
        self.setWindowTitle("QualCoder " + self.settings['projectName'])
        cur = self.settings['conn'].cursor()
        cur.execute("select databaseversion, date, memo, about from project")
        result = cur.fetchone()
        self.project['databaseversion'] = result[0]
        self.project['date'] = result[1]
        self.project['memo'] = result[2]
        self.project['about'] = result[3]
        # Save a datetime stamped backup
        nowdate = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup = self.settings['path'][0:-4] + "_BACKUP_" + nowdate + ".qda"
        shutil.copytree(self.settings['path'], backup)
        self.ui.textEdit.append(_("Project Opened: ") + self.settings['projectName']
            + "\n========\n"
            + _("Path: ") + self.settings['path'] + "\n"
            + _("Directory: ") + self.settings['directory'] + "\n"
            + _("Database version: ") + self.project['databaseversion'] + ". "
            + _("Date: ") + str(self.project['date']) + "\n"
            + _("About: ") + self.project['about'] + "\n"
            + _("Language: ") + self.settings['language'] + "\n"
            + _("Project backup created: ") + backup
            + "\n========\n")
        self.show_menu_options()

    def close_project(self):
        """ Close an open project. """

        self.ui.textEdit.append("Closing project: " + self.settings['projectName'] + "\n========\n")
        try:
            self.settings['conn'].commit()
            self.settings['conn'].close()
        except:
            pass
        self.conn = None
        self.settings['conn'] = None
        self.settings['path'] = ""
        self.settings['projectName'] = ""
        self.settings['directory'] = ""
        self.project = {"databaseversion": "", "date": "", "memo": "", "about": ""}
        self.hide_menu_options()
        self.clean_dialog_refs()

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


def main():
    app = QtWidgets.QApplication(sys.argv)
    QtGui.QFontDatabase.addApplicationFont("GUI/NotoSans-hinted/NotoSans-Regular.ttf")
    QtGui.QFontDatabase.addApplicationFont("GUI/NotoSans-hinted/NotoSans-Bold.ttf")
    # uncomment below when used in deb package RemRmm44's suggestion
    #with open(path + "/QualCoder/GUI/default.stylesheet", "r") as fh:
    # comment below when used in deb package, RemRam44's suggestion
    with open(path + "/GUI/default.stylesheet", "r") as fh:
        app.setStyleSheet(fh.read())
    # Try and load language settings from file stored in home/.qualcoder/
    # translator applies to ui designed GUI widgets only
    lang = "en"
    try:
        with open(home + '/.qualcoder/QualCoder_settings.txt') as f:
            txt = f.read()
            txt = txt.split("\n")
            lang = txt[6]
            if lang == "":
                lang = "en"
    except:
        pass
    getlang = gettext.translation('en', localedir=path +'/locale', languages=['en'])
    if lang != "en":
        translator = QtCore.QTranslator()
        if lang == "fr":
            translator.load(path + "/locale/fr/app_fr.qm")
            getlang = gettext.translation('fr', localedir=path + '/locale', languages=['fr'])
        if lang == "de":
            translator.load(path + "/locale/de/app_de.qm")
            getlang = gettext.translation('de', localedir=path + '/locale', languages=['de'])
        app.installTranslator(translator)
    getlang.install()
    ex = MainWindow()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()

