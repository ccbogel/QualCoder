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

import csv
import datetime
import ebooklib
from ebooklib import epub
import logging
import os
import PIL
from PIL import Image
import platform
import sys
from shutil import copyfile, move
import subprocess
import traceback
import webbrowser
import zipfile

from PyQt6 import QtCore, QtGui, QtWidgets

from .add_attribute import DialogAddAttribute
from .add_item_name import DialogAddItemName
from .GUI.base64_helper import *
from .code_text import DialogCodeText  # for isinstance()
from .confirm_delete import DialogConfirmDelete
from .docx import opendocx, getdocumenttext
from .GUI.ui_dialog_manage_files import Ui_Dialog_manage_files
from .edit_textfile import DialogEditTextFile
from .helpers import Message, ExportDirectoryPathDialog, msecs_to_hours_mins_secs
from .html_parser import *
from .memo import DialogMemo
from .select_items import DialogSelectItems
from .view_image import DialogViewImage, DialogCodeImage  # DialogCodeImage for isinstance()
from .view_av import DialogViewAV, DialogCodeAV  # DialogCodeAV for isinstance()
from .report_codes import DialogReportCodes  # for isInstance()

import qualcoder.vlc as vlc

from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams, LTTextBox, LTTextLine


path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text_ = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text_)
    logger.error(_("Uncaught exception: ") + text_)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 12pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(text_)
    mb.exec()


class DialogManageFiles(QtWidgets.QDialog):
    """ View, import, export, rename and delete text files.
    Files are normally imported into the qda project folder.
    Option to link to external files.
    """

    source = []
    app = None
    parent_text_edit = None
    tab_coding = None  # Tab widget coding tab for updates
    tab_reports = None  # Tab widget reports for updates
    text_view = None
    header_labels = []
    NAME_COLUMN = 0
    MEMO_COLUMN = 1
    DATE_COLUMN = 2
    ID_COLUMN = 3
    CASE_COLUMN = 4
    rows_hidden = False
    default_import_directory = os.path.expanduser("~")
    attribute_names = []  # list of dictionary name:value for AddAtribute dialog
    av_dialog_open = None  # Used for opened AV dialog

    def __init__(self, app, parent_text_edit, tab_coding, tab_reports):

        sys.excepthook = exception_handler
        self.app = app
        self.parent_text_edit = parent_text_edit
        self.tab_coding = tab_coding
        self.tab_reports = tab_reports
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_manage_files()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)

        self.default_import_directory = self.app.settings['directory']
        self.attributes = []
        self.av_dialog_open = None
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(pencil_icon), "png")
        self.ui.pushButton_create.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_create.clicked.connect(self.create_text_file)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(eye_icon), "png")
        self.ui.pushButton_view.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_view.clicked.connect(self.view)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(delete_icon), "png")
        self.ui.pushButton_delete.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_delete.clicked.connect(self.delete_button_multiple_files)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(doc_import_icon), "png")
        self.ui.pushButton_import.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_import.clicked.connect(self.import_files)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(link_icon), "png")
        self.ui.pushButton_link.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_link.clicked.connect(self.link_files)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(linked_import_icon), "png")
        self.ui.pushButton_import_from_linked.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_import_from_linked.clicked.connect(self.button_import_linked_file)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(to_link_icon), "png")
        self.ui.pushButton_export_to_linked.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_export_to_linked.clicked.connect(self.button_export_file_as_linked_file)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(doc_export_icon), "png")
        self.ui.pushButton_export.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_export.clicked.connect(self.export)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(plus_icon), "png")
        self.ui.pushButton_add_attribute.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_add_attribute.clicked.connect(self.add_attribute)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(doc_export_csv_icon), "png")
        self.ui.pushButton_export_attributes.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_export_attributes.clicked.connect(self.export_attributes)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(question_icon), "png")
        self.ui.pushButton_help.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_help.pressed.connect(self.help)
        self.ui.tableWidget.itemChanged.connect(self.cell_modified)
        self.ui.tableWidget.cellClicked.connect(self.cell_selected)
        self.ui.tableWidget.cellDoubleClicked.connect(self.cell_double_clicked)
        self.ui.tableWidget.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.tableWidget.customContextMenuRequested.connect(self.table_menu)
        self.ui.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.load_file_data()
        # Initial resize of table columns
        self.ui.tableWidget.resizeColumnsToContents()
        self.ui.tableWidget.resizeRowsToContents()

    # @staticmethod
    def help():
        """ Open help for transcribe section in browser. """

        url = "https://github.com/ccbogel/QualCoder/wiki/05-Files"
        webbrowser.open(url)

    def table_menu(self, position):
        """ Context menu for displaying table rows in differing order """

        row = self.ui.tableWidget.currentRow()
        col = self.ui.tableWidget.currentColumn()
        # Use these next few lines to use for moving a linked file into or an internal file out of the project folder
        mediapath = None
        try:
            id_ = int(self.ui.tableWidget.item(row, self.ID_COLUMN).text())
        except AttributeError:
            # Occurs if a table cell is not clicked, but click occurs elsewhere in container
            return
        for s in self.source:
            if s['id'] == id_:
                mediapath = s['mediapath']
        # Action cannot be None otherwise may default to one of the actions below depending on column clicked
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_view = menu.addAction(_("View"))
        action_alphabetic = None
        action_date = None
        action_type = None
        action_casename = None
        action_equals_value = None
        action_order_by_value = None
        action_show_all = None
        action_import_linked = None
        action_export_to_linked = None
        if col <= self.CASE_COLUMN:
            action_alphabetic = menu.addAction(_("Alphabetic order"))
            action_date = menu.addAction(_("Date order"))
            action_type = menu.addAction(_("File type order"))
            action_casename = menu.addAction(_("Case order"))
        if col > self.CASE_COLUMN:
            action_equals_value = menu.addAction(_("Show this value"))
            action_order_by_value = menu.addAction(_("Order by attribute"))
        action_rename = menu.addAction(_("Rename database entry"))
        action_export = menu.addAction(_("Export"))
        action_delete = menu.addAction(_("Delete"))
        if self.rows_hidden:
            action_show_all = menu.addAction(_("Show all rows"))
        if mediapath is None or (mediapath is not None and mediapath[0] == "/"):
            action_export_to_linked = menu.addAction(_("Move file to externally linked file"))
        else:
            action_import_linked = menu.addAction(_("Import linked file"))
        action = menu.exec(self.ui.tableWidget.mapToGlobal(position))
        if action is None:
            return
        if action == action_view:
            self.view()
            return
        if self.av_dialog_open is not None:
            self.av_dialog_open.mediaplayer.stop()
            self.av_dialog_open = None
        if action == action_import_linked:
            self.import_linked_file(id_, mediapath)
        if action == action_export_to_linked:
            self.export_file_as_linked_file(id_, mediapath)
        if action == action_export:
            self.export()
        if action == action_delete:
            self.delete()
        if action == action_rename:
            self.rename_database_entry()
        if action == action_alphabetic:
            self.load_file_data()
        if action == action_date:
            self.load_file_data("date")
            self.fill_table()
        if action == action_type:
            self.load_file_data("filetype")
        if action == action_casename:
            self.load_file_data("casename")
        if action == action_order_by_value:
            self.load_file_data("attribute:" + self.header_labels[col])
        if action == action_equals_value:
            # Hide rows that do not match this value
            item_to_compare = self.ui.tableWidget.item(row, col)
            compare_text = item_to_compare.text()
            for r in range(0, self.ui.tableWidget.rowCount()):
                item = self.ui.tableWidget.item(r, col)
                text_ = item.text()
                if compare_text != text_:
                    print(compare_text, text_)
                    self.ui.tableWidget.setRowHidden(r, True)
            self.rows_hidden = True
        if action == action_show_all:
            for r in range(0, self.ui.tableWidget.rowCount()):
                self.ui.tableWidget.setRowHidden(r, False)
            self.rows_hidden = False

    def rename_database_entry(self):
        """ Rename the database entry of the file. """

        row = self.ui.tableWidget.currentRow()
        if row == -1:
            return
        existing_name = self.ui.tableWidget.item(row, self.NAME_COLUMN).text()
        filenames = []
        for s in self.source:
            filenames.append({'name': s['name']})
        ui = DialogAddItemName(self.app, filenames, _("Rename database entry"), existing_name)
        ui.exec()
        new_name = ui.get_new_name()
        if new_name is None:
            return
        cur = self.app.conn.cursor()
        cur.execute("update source set name=? where name=?", [new_name, existing_name])
        self.app.conn.commit()
        self.parent_text_edit.append(_("Renamed database file entry: ") + existing_name + " -> " + new_name)
        self.load_file_data()
        self.fill_table()
        self.app.delete_backup = False
        self.update_files_in_dialogs()

    def button_export_file_as_linked_file(self):
        """ User presses button to export current row's file.
         Only to work with an exportable file. """

        if self.av_dialog_open is not None:
            self.av_dialog_open.mediaplayer.stop()
            self.av_dialog_open = None
        row = self.ui.tableWidget.currentRow()
        if row == -1:
            return
        mediapath = None
        id_ = int(self.ui.tableWidget.item(row, self.ID_COLUMN).text())
        for s in self.source:
            if s['id'] == id_:
                mediapath = s['mediapath']
        if id_ is None or mediapath is None:
            return
        if mediapath is None or (mediapath is not None and mediapath[0] == "/"):
            self.export_file_as_linked_file(id_, mediapath)

    def export_file_as_linked_file(self, id_, mediapath):
        """ Move an internal project file into an external location as a linked file.
        #TODO Do not export text files as linked files. e.g. internally created in database, or
        docx, txt, md, odt files.

        params:
            id_ : the file id, Integer
            mediapath: stored path to media, will be None for text files, or String
        """

        if self.av_dialog_open is not None:
            self.av_dialog_open.mediaplayer.stop()
            self.av_dialog_open = None
        options = QtWidgets.QFileDialog.Option.DontResolveSymlinks | QtWidgets.QFileDialog.Option.ShowDirsOnly
        directory = QtWidgets.QFileDialog.getExistingDirectory(None,
                                                               _("Select directory to save file"),
                                                               self.app.last_export_directory, options)
        if directory == "":
            return
        if directory != self.app.last_export_directory:
            self.app.last_export_directory = directory
        file_directory = ""
        if mediapath is not None:
            file_directory = mediapath.split('/')[1]  # as [0] will be blank
            destination = directory + "/" + mediapath.split('/')[-1]
        else:
            # Text files have None as mediapath
            cur = self.app.conn.cursor()
            cur.execute("select name from source where id=?", [id_, ])
            name = cur.fetchone()[0]
            file_directory = "documents"
            mediapath = "/documents/" + name
            destination = directory + "/" + name
        msg = _("Export to ") + destination + "\n"
        try:
            move(self.app.project_path + mediapath, destination)
        except Exception as e_:
            logger.debug(str(e_))
            Message(self.app, _("Cannot export"), _("Cannot export as linked file\n") + str(e_), "warning").exec()
            return
        new_mediapath = ""
        if file_directory == "documents":
            new_mediapath = "docs:" + destination
        if file_directory == "images":
            new_mediapath = "images:" + destination
        if file_directory == "audio":
            new_mediapath = "audio:" + destination
        if file_directory == "video":
            new_mediapath = "video:" + destination
        cur = self.app.conn.cursor()
        cur.execute("update source set mediapath=? where id=?", [new_mediapath, id_])
        self.parent_text_edit.append(msg)
        self.app.conn.commit()
        self.update_files_in_dialogs()
        self.load_file_data()
        self.app.delete_backup = False

    def button_import_linked_file(self):
        """ User presses button to import a linked file into the project folder.
        Only to work with an importable file. """

        if self.av_dialog_open is not None:
            self.av_dialog_open.mediaplayer.stop()
            self.av_dialog_open = None
        row = self.ui.tableWidget.currentRow()
        if row == -1:
            return
        mediapath = None
        id_ = int(self.ui.tableWidget.item(row, self.ID_COLUMN).text())
        for s in self.source:
            if s['id'] == id_:
                mediapath = s['mediapath']
        if id_ is None or mediapath is None:
            return
        if mediapath is not None and mediapath[0] != "/":
            self.import_linked_file(id_, mediapath)

    def import_linked_file(self, id_, mediapath):
        """ Import a linked file into the project folder, and change mediapath details. """

        if self.av_dialog_open is not None:
            self.av_dialog_open.mediaplayer.stop()
            self.av_dialog_open = None
        name_split1 = mediapath.split(":")[1]
        filename = name_split1.split('/')[-1]
        if mediapath[0:6] == "audio:":
            copyfile(mediapath[6:], self.app.project_path + "/audio/" + filename)
            mediapath = '/audio/' + filename
        if mediapath[0:6] == "video:":
            copyfile(mediapath[6:], self.app.project_path + "/video/" + filename)
            mediapath = '/video/' + filename
        if mediapath[0:7] == "images:":
            copyfile(mediapath[7:], self.app.project_path + "/images/" + filename)
            mediapath = '/images/' + filename
        # This must be the last if statement as mediapath can be None
        if mediapath[0:5] == "docs:":
            copyfile(mediapath[5:], self.app.project_path + "/documents/" + filename)
            mediapath = None
        cur = self.app.conn.cursor()
        cur.execute("update source set mediapath=? where id=?", [mediapath, id_])
        self.app.conn.commit()
        self.update_files_in_dialogs()
        self.load_file_data()
        self.app.delete_backup = False

    def check_attribute_placeholders(self):
        """ Files can be added after attributes are in the project.
         Need to add placeholder attribute values for these, if missing.
         Also,if a file is deleted, check and remove any isolated attribute values. """

        cur = self.app.conn.cursor()
        sql = "select id from source "
        cur.execute(sql)
        sources = cur.fetchall()
        sql = 'select name from attribute_type where caseOrFile ="file"'
        cur.execute(sql)
        attr_types = cur.fetchall()
        insert_sql = "insert into attribute (name, attr_type, value, id, date, owner) values(?,'file','',?,?,?)"
        for s in sources:
            for a in attr_types:
                sql = "select value from attribute where id=? and name=?"
                cur.execute(sql, (s[0], a[0]))
                res = cur.fetchone()
                # print("file", s[0],"attr", a[0], " res", res, type(res))
                if res is None:
                    # print("No attr placeholder found")
                    placeholders = [a[0], s[0], datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                    self.app.settings['codername']]
                    cur.execute(insert_sql, placeholders)
                    self.app.conn.commit()

        # Check and delete attribute values where file has been deleted
        att_to_del_sql = "SELECT distinct attribute.id FROM  attribute where \
        attribute.id not in (select source.id from source) order by attribute.id asc"
        cur.execute(att_to_del_sql)
        res = cur.fetchall()
        for r in res:
            cur.execute("delete from attribute where attr_type='file' and id=?", [r[0], ])
            self.app.conn.commit()

    def export_attributes(self):
        """ Export attributes from table as a csv file. """

        if self.av_dialog_open is not None:
            self.av_dialog_open.mediaplayer.stop()
            self.av_dialog_open = None
        shortname = self.app.project_name.split(".qda")[0]
        filename = shortname + "_file_attributes.csv"
        exp_dlg = ExportDirectoryPathDialog(self.app, filename)
        filepath = exp_dlg.filepath
        if filepath is None:
            return
        cols = self.ui.tableWidget.columnCount()
        rows = self.ui.tableWidget.rowCount()
        header = []
        for i in range(0, cols):
            header.append(self.ui.tableWidget.horizontalHeaderItem(i).text())
        with open(filepath, mode='w') as f:
            writer = csv.writer(f, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(header)
            for r in range(0, rows):
                data = []
                for c in range(0, cols):
                    # Table cell may be a None type
                    cell = ""
                    try:
                        cell = self.ui.tableWidget.item(r, c).text()
                    except AttributeError:
                        pass
                    data.append(cell)
                writer.writerow(data)
        msg = _("File attributes csv file exported to: ") + filepath
        Message(self.app, _('Csv file Export'), msg).exec()
        self.parent_text_edit.append(msg)

    def load_file_data(self, order_by=""):
        """ Documents images and audio contain the filetype suffix.
        No suffix implies the 'file' was imported from a survey question or created internally.
        This also fills out the table header labels with file attribute names.
        Db versions < 5: Files with the '.transcribed' suffix mean they are associated with audio and
        video files.
        Db version 5+: av_text_id links the text file to the audio/video
        Obtain some file metadata to use in table tooltip.
        param:
            order_by: string ""= name, "date" = date, "filetype" = mediapath,
                "casename" = by alphabetic casename
                "attribute:attribute name" selected atribute
        """

        # check a placeholder attribute is present for the file, add if missing
        self.check_attribute_placeholders()
        self.source = []
        cur = self.app.conn.cursor()
        placeholders = None
        # default alphabetic order
        sql = "select name, id, fulltext, mediapath, memo, owner, date, av_text_id from source order by upper(name)"
        if order_by == "date":
            sql = "select name, id, fulltext, mediapath, memo, owner, date, av_text_id from source order by date, upper(name)"
        if order_by == "filetype":
            sql = "select name, id, fulltext, mediapath, memo, owner, date, av_text_id from source order by mediapath"
        if order_by == "casename":
            sql = 'select distinct source.name, source.id, source.fulltext, source.mediapath, source.memo, '
            sql += 'source.owner, source.date, av_text_id '
            sql += 'from source left join case_text on source.id=case_text.fid '
            sql += 'left join cases on cases.caseid=case_text.caseid '
            sql += 'order by cases.name, source.name '

        if order_by[:10] == "attribute:":
            attribute_name = order_by[10:]
            # two types of ordering character or numeric
            cur.execute("select valuetype from attribute_type where name=?", [attribute_name])
            attr_type = cur.fetchone()[0]
            sql = 'select source.name, source.id, fulltext, mediapath, source.memo, source.owner, source.date,'
            sql += 'av_text_id from source join attribute on attribute.id = source.id '
            sql += ' where attribute.attr_type = "file" and attribute.name=? '
            if attr_type == "character":
                sql += 'order by lower(attribute.value) asc '
            else:
                sql += 'order by cast(attribute.value as numeric) asc'
            placeholders = [attribute_name]
        if placeholders is not None:
            cur.execute(sql, placeholders)
        else:
            cur.execute(sql)
        result = cur.fetchall()
        for row in result:
            icon, metadata = self.get_icon_and_metadata(row[1])
            self.source.append({'name': row[0], 'id': row[1], 'fulltext': row[2],
                                'mediapath': row[3], 'memo': row[4], 'owner': row[5], 'date': row[6],
                                'av_text_id': row[7], 'metadata': metadata, 'icon': icon,
                                'case': self.get_cases_by_filename(row[0])})
        # Attributes
        self.header_labels = [_("Name"), _("Memo"), _("Date"), _("Id"), _("Case")]
        sql = "select name from attribute_type where caseOrFile='file'"
        cur.execute(sql)
        result = cur.fetchall()
        self.attribute_names = []
        for n in result:
            self.header_labels.append(n[0])
            self.attribute_names.append({'name': n[0]})
        sql = "select attribute.name, value, id from attribute join attribute_type on \
        attribute_type.name=attribute.name where attribute_type.caseOrFile='file'"
        cur.execute(sql)
        result = cur.fetchall()
        self.attributes = []
        for row in result:
            self.attributes.append(row)
        self.fill_table()

    def get_icon_and_metadata(self, id_):
        """ Get metadata used in table tooltip.
        Called by: create_text_file, load_file_data
        param:
            id_  : integer source.id
        """

        cur = self.app.conn.cursor()
        cur.execute("select name, fulltext, mediapath from source where id=?", [id_])
        res = cur.fetchone()
        metadata = res[0] + "\n"
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(text), "png")
        icon = QtGui.QIcon(pm)
        # Check if text file is a transcription and add details
        cur.execute("select name from source where av_text_id=?", [id_])
        tr_res = cur.fetchone()
        if tr_res is not None:
            metadata += _("Transcript for: ") + tr_res[0] + "\n"
            pm.loadFromData(QtCore.QByteArray.fromBase64(transcribed_text_icon), "png")
            icon = QtGui.QIcon(pm)
        if res[1] is not None and len(res[1]) > 0 and res[2] is None:
            metadata += _("Characters: ") + str(len(res[1]))
            return icon, metadata
        if res[2] is None:
            logger.debug("empty media path error")
            return icon, metadata
        if res[1] is not None and len(res[1]) > 0 and res[2][0:5] == 'docs:':
            metadata += _("Characters: ") + str(len([res[1]]))
            pm = QtGui.QPixmap()
            pm.loadFromData(QtCore.QByteArray.fromBase64(text_link), "png")
            icon = QtGui.QIcon(pm)
            return icon, metadata

        abs_path = ""
        if 'audio:' == res[2][0:6]:
            abs_path = res[2][6:]
        elif 'video:' == res[2][0:6]:
            abs_path = res[2][6:]
        elif 'images:' == res[2][0:7]:
            abs_path = res[2][7:]
        else:
            abs_path = self.app.project_path + res[2]

        if res[2][:8] == "/images/":
            pm = QtGui.QPixmap()
            pm.loadFromData(QtCore.QByteArray.fromBase64(picture), "png")
            icon = QtGui.QIcon(pm)
            # w = 0
            # h = 0
            try:
                image = Image.open(abs_path)
                w, h = image.size
            except (FileNotFoundError, PIL.UnidentifiedImageError):
                metadata += _("Cannot locate media. ") + abs_path
                return icon, metadata
            metadata += "W: " + str(w) + " x H: " + str(h)
        if res[2][:7] == "images:":
            pm = QtGui.QPixmap()
            pm.loadFromData(QtCore.QByteArray.fromBase64(picture_link), "png")
            icon = QtGui.QIcon(pm)
            # w = 0
            # h = 0
            try:
                image = Image.open(abs_path)
                w, h = image.size
            except (FileNotFoundError, PIL.UnidentifiedImageError):
                metadata += _("Cannot locate media. ") + abs_path
                return icon, metadata
            metadata += "W: " + str(w) + " x H: " + str(h)
        if res[2][:7] == "/video/":
            pm = QtGui.QPixmap()
            pm.loadFromData(QtCore.QByteArray.fromBase64(play), "png")
            icon = QtGui.QIcon(pm)
        if res[2][:6] == "video:":
            pm = QtGui.QPixmap()
            pm.loadFromData(QtCore.QByteArray.fromBase64(play_link), "png")
            icon = QtGui.QIcon(pm)
        if res[2][:7] == "/audio/":
            pm = QtGui.QPixmap()
            pm.loadFromData(QtCore.QByteArray.fromBase64(sound), "png")
            icon = QtGui.QIcon(pm)
        if res[2][:6] == "audio:":
            pm = QtGui.QPixmap()
            pm.loadFromData(QtCore.QByteArray.fromBase64(sound_link), "png")
            icon = QtGui.QIcon(pm)
        if res[2][:6] in ("/audio", "audio:", "/video", "video:"):
            if not os.path.exists(abs_path):
                metadata += _("Cannot locate media. ") + abs_path
                return icon, metadata

            instance = vlc.Instance()
            # mediaplayer = instance.media_player_new()
            try:
                media = instance.media_new(abs_path)
                media.parse()
                msecs = media.get_duration()
                duration_txt = msecs_to_hours_mins_secs(msecs)
                metadata += _("Duration: ") + duration_txt
            except AttributeError as e_:
                logger.debug(str(e_))
                metadata += _("Cannot locate media. ") + abs_path + "\n" + str(e_)
                return icon, metadata
        bytes_ = 0
        try:
            bytes_ = os.path.getsize(abs_path)
        except OSError:
            pass
        metadata += "\nBytes: " + str(bytes_)
        if bytes_ > 1024 and bytes_ < 1024 * 1024:
            metadata += "  " + str(int(bytes_ / 1024)) + "KB"
        if bytes_ > 1024 * 1024:
            metadata += "  " + str(int(bytes_ / 1024 / 1024)) + "MB"
        # Get case names linked to the file
        txt = self.get_cases_by_filename(res[0])
        if txt != "":
            metadata += "\n" + _("Case linked:") + "\n" + txt
        return icon, metadata

    def get_cases_by_filename(self, name):
        """ Called by get_icon_and_metadata, get_file_data
        param: name String of filename """

        cur = self.app.conn.cursor()
        # Case_text is the table, but this also links av and images
        sql = "select distinct cases.name from cases join case_text on case_text.caseid=cases.caseid "
        sql += "join source on source.id=case_text.fid where source.name=? "
        text_ = ""
        cur.execute(sql, [name, ])
        res = cur.fetchall()
        if res:
            for r in res:
                text_ += r[0] + " "
        return text_

    def add_attribute(self):
        """ When add button pressed, opens the AddAtribute dialog to get new attribute text.
        Then get the attribute type through a dialog.
        AddAttribute dialog checks for duplicate attribute name.
        New attribute is added to the model and database. """

        if self.av_dialog_open is not None:
            self.av_dialog_open.mediaplayer.stop()
            self.av_dialog_open = None
        check_names = self.attribute_names + [{'name': 'name'}, {'name': 'memo'}, {'name': 'id'}, {'name': 'date'}]
        ui = DialogAddAttribute(self.app, check_names)
        ok = ui.exec()
        if not ok:
            return
        name = ui.new_name
        value_type = ui.value_type
        if name == "":
            return
        self.attribute_names.append({'name': name})
        # update attribute_type list and database
        now_date = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        cur = self.app.conn.cursor()
        cur.execute("insert into attribute_type (name,date,owner,memo,caseOrFile, valuetype) values(?,?,?,?,?,?)",
                    (name, now_date, self.app.settings['codername'], "", 'file', value_type))
        self.app.conn.commit()
        self.app.delete_backup = False
        sql = "select id from source"
        cur.execute(sql)
        ids = cur.fetchall()
        for id_ in ids:
            sql = "insert into attribute (name, value, id, attr_type, date, owner) values (?,?,?,?,?,?)"
            cur.execute(sql, (name, "", id_[0], 'file', now_date, self.app.settings['codername']))
        self.app.conn.commit()
        self.load_file_data()
        self.fill_table()
        self.parent_text_edit.append(_("Attribute added to files: ") + name + ", " + _("type") + ": " + value_type)

    def cell_double_clicked(self):
        """ View file """

        y = self.ui.tableWidget.currentColumn()
        if y == self.NAME_COLUMN:
            self.view()

    def cell_selected(self):
        """ When the table widget memo cell is selected display the memo.
        Update memo text, or delete memo by clearing text.
        If a new memo, also show in table widget by displaying MEMO in the memo column. """

        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        if y == self.MEMO_COLUMN:
            name = self.source[x]['name'].lower()
            if name[-5:] == ".jpeg" or name[-4:] in ('.jpg', '.png', '.gif'):
                ui = DialogMemo(self.app, _("Memo for file ") + self.source[x]['name'],
                                self.source[x]['memo'])
                ui.exec()
                self.source[x]['memo'] = ui.memo
                cur = self.app.conn.cursor()
                cur.execute('update source set memo=? where id=?', (ui.memo, self.source[x]['id']))
                self.app.conn.commit()
            else:
                ui = DialogMemo(self.app, _("Memo for file ") + self.source[x]['name'],
                                self.source[x]['memo'])
                ui.exec()
                self.source[x]['memo'] = ui.memo
                cur = self.app.conn.cursor()
                cur.execute('update source set memo=? where id=?', (ui.memo, self.source[x]['id']))
                self.app.conn.commit()
            if self.source[x]['memo'] == "":
                self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem())
            else:
                self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem("Memo"))

    def cell_modified(self):
        """ Attribute values can be changed.
        Filenames cannot be changed. """

        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()

        # Update attribute value
        if y > self.CASE_COLUMN:
            value = str(self.ui.tableWidget.item(x, y).text()).strip()
            attribute_name = self.header_labels[y]
            cur = self.app.conn.cursor()

            # Check numeric for numeric attributes, clear "" if cannot be cast
            cur.execute("select valuetype from attribute_type where caseOrFile='file' and name=?", (attribute_name,))
            result = cur.fetchone()
            if result is None:
                return
            if result[0] == "numeric":
                try:
                    float(value)
                except ValueError:
                    self.ui.tableWidget.item(x, y).setText("")
                    value = ""
                    msg = _("This attribute is numeric")
                    Message(self.app, _("Warning"), msg, "warning").exec()

            cur.execute("update attribute set value=? where id=? and name=? and attr_type='file'",
                        (value, self.source[x]['id'], attribute_name))
            self.app.conn.commit()
            self.app.delete_backup = False
            self.ui.tableWidget.resizeColumnsToContents()

    def view(self):
        """ View and edit text file contents.
        Alternatively view an image, audio or video media. """

        if self.av_dialog_open is not None:
            self.av_dialog_open.mediaplayer.stop()
            self.av_dialog_open = None
        x = self.ui.tableWidget.currentRow()
        self.ui.tableWidget.selectRow(x)
        if self.source[x]['mediapath'] is not None and 'docs:' != self.source[x]['mediapath'][0:5]:
            if len(self.source[x]['mediapath']) > 6 and self.source[x]['mediapath'][:7] in ("/images", "images:"):
                self.view_image(x)
                return
            if len(self.source[x]['mediapath']) > 5 and self.source[x]['mediapath'][:6] in ("/video", "video:"):
                self.view_av(x)
                return
            if len(self.source[x]['mediapath']) > 5 and self.source[x]['mediapath'][:6] in ("/audio", "audio:"):
                self.view_av(x)
                return
        ui = DialogEditTextFile(self.app, self.source[x]['id'])
        ui.exec()
        # Get fulltext if changed (for metadata)
        cur = self.app.conn.cursor()
        cur.execute("select fulltext from source where id=?", [self.source[x]['id']])
        res = cur.fetchone()
        fulltext = ""
        if res is not None:
            fulltext = res[0]
        self.source[x]['fulltext'] = fulltext

    def view_av(self, x):
        """ View an audio or video file. Edit the memo. Edit the transcript file.
        Added try block in case VLC bindings do not work.
        Uses a non-modal dialog.

        param:
            x  :  row number Integer
        """

        # Check media exists
        abs_path = ""
        if self.source[x]['mediapath'][0:6] in ('/audio', '/video'):
            abs_path = self.app.project_path + self.source[x]['mediapath']
        if self.source[x]['mediapath'][0:6] in ('audio:', 'video:'):
            abs_path = self.source[x]['mediapath'][6:]
        if not os.path.exists(abs_path):
            self.parent_text_edit.append(_("Bad link or non-existent file ") + abs_path)
            return
        try:
            ui = DialogViewAV(self.app, self.source[x])
            # ui.exec()  # this dialog does not display well on Windows 10 so trying .show()
            # The vlc window becomes unmovable and not resizable
            self.av_dialog_open = ui
            ui.show()
            if self.source[x]['memo'] == "":
                self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem())
            else:
                self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem(_("Memo")))
        except Exception as e_:
            logger.debug(e_)
            print(e_)
            Message(self.app, _('view AV error'), str(e_), "warning").exec()
            self.av_dialog_open = None
            return

    def view_image(self, x):
        """ View an image file and edit the image memo.

        param:
            x  :  row number Integer
        """

        # Check image exists
        abs_path = ""
        if "images:" in self.source[x]['mediapath']:
            abs_path = self.source[x]['mediapath'].split(':')[1]
        else:
            abs_path = self.app.project_path + self.source[x]['mediapath']
        if not os.path.exists(abs_path):
            self.parent_text_edit.append(_("Bad link or non-existent file ") + abs_path)
            return
        ui = DialogViewImage(self.app, self.source[x])
        ui.exec()
        memo = ui.ui.textEdit.toPlainText()
        if self.source[x]['memo'] != memo:
            self.source[x]['memo'] = memo
            cur = self.app.conn.cursor()
            cur.execute('update source set memo=? where id=?', (self.source[x]['memo'],
                                                                self.source[x]['id']))
            self.app.conn.commit()
        if self.source[x]['memo'] == "":
            self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem())
        else:
            self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem(_("Memo")))

    def create_text_file(self):
        """ Create a new text file by entering text into the dialog.
        Implements the QtDesigner memo dialog. """

        if self.av_dialog_open is not None:
            self.av_dialog_open.mediaplayer.stop()
            self.av_dialog_open = None
        ui = DialogAddItemName(self.app, self.source, _('New File'), _('Enter file name'))
        ui.exec()
        name = ui.get_new_name()
        if name is None:
            return

        # Create entry details to add to self.source and to database
        entry = {'name': name, 'id': -1, 'fulltext': '', 'memo': "",
                 'owner': self.app.settings['codername'], 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 'mediapath': None, 'icon': None, 'metadata': '', 'case': ""}
        # Update database
        cur = self.app.conn.cursor()
        cur.execute("insert into source(name,fulltext,mediapath,memo,owner,date) values(?,?,?,?,?,?)",
                    (
                        entry['name'], entry['fulltext'], entry['mediapath'], entry['memo'], entry['owner'],
                        entry['date']))
        self.app.conn.commit()
        cur.execute("select last_insert_rowid()")
        id_ = cur.fetchone()[0]
        entry['id'] = id_
        ui = DialogEditTextFile(self.app, id_)
        ui.exec()
        icon, metadata = self.get_icon_and_metadata(id_)
        entry['icon'] = icon
        entry['metadata'] = metadata

        # Add file attribute placeholders
        att_sql = 'select name from attribute_type where caseOrFile ="file"'
        cur.execute(att_sql)
        attr_types = cur.fetchall()
        insert_sql = "insert into attribute (name, attr_type, value, id, date, owner) values(?,'file','',?,?,?)"
        for a in attr_types:
            placeholders = [a[0], id_, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            self.app.settings['codername']]
            cur.execute(insert_sql, placeholders)
            self.app.conn.commit()
        self.update_files_in_dialogs()
        self.parent_text_edit.append(_("File created: ") + entry['name'])
        self.source.append(entry)
        self.fill_table()
        self.app.delete_backup = False

    def link_files(self):
        """ Trigger to link to file location. """

        if self.av_dialog_open is not None:
            self.av_dialog_open.mediaplayer.stop()
            self.av_dialog_open = None
        self.import_files(True)

    def import_files(self, link=False):
        """ Import files and store into relevant directories (documents, images, audio, video).
        Convert documents to plain text and store this in data.qda
        Can import from plain text files, also import from html, odt, docx and md.
        md is text markdown format.
        Note importing from html, odt, docx all formatting is lost.
        Imports images as jpg, jpeg, png which are stored in an images directory.
        Imports audio as mp3, wav, m4a which are stored in an audio directory.
        Imports video as mp4, mov, ogg, wmv which are stored in a video directory.

        param:
            link:   False - files are imported into project folder,
                    True- files are linked and not imported
        """

        if self.av_dialog_open is not None:
            self.av_dialog_open.mediaplayer.stop()
            self.av_dialog_open = None
        response = QtWidgets.QFileDialog.getOpenFileNames(None, _('Open file'),
                                                           self.default_import_directory,
                                                          options=QtWidgets.QFileDialog.Option.DontUseNativeDialog
                                                          )
        imports = response[0]
        if not imports:
            return
        known_file_type = False
        name_split = imports[0].split("/")
        temp_filename = name_split[-1]
        self.default_import_directory = imports[0][0:-len(temp_filename)]
        pdf_msg = ""
        for f in imports:
            link_path = ""
            if link:
                link_path = f
            # Check file size, any files over 2Gb are linked and not imported internally
            fileinfo = os.stat(f)
            if fileinfo.st_size >= 2147483647:
                link_path = f
            # Need process events, if many large files are imported, which leaves the FileDialog open and covering the screen.
            QtWidgets.QApplication.processEvents()
            filename = f.split("/")[-1]
            destination = self.app.project_path
            if f.split('.')[-1].lower() in ('docx', 'odt', 'txt', 'htm', 'html', 'epub', 'md'):
                destination += "/documents/" + filename
                if link_path == "":
                    copyfile(f, destination)
                    self.load_file_text(f)
                else:
                    self.load_file_text(f, "docs:" + link_path)
                known_file_type = True
            if f.split('.')[-1].lower() == 'pdf':
                '''if pdfminer_installed is False:
                    text_ = "For Linux run the following on the terminal: sudo pip install pdfminer.six\n"
                    text_ += "For Windows run the following in the command prompt: pip install pdfminer.six"
                    Message(self.app, _("pdf miner is not installed"), _(text_), "critical").exec()
                    return'''
                destination += "/documents/" + filename
                # Try and remove encryption from pdf if a simple encryption, for Linux
                if platform.system() == "Linux":
                    process = subprocess.Popen(["qpdf", "--decrypt", f, destination],
                                               stdout=subprocess.PIPE)
                    process.wait()
                    if link_path == "":
                        self.load_file_text(destination)
                    else:
                        self.load_file_text(destination, "docs:" + link_path)
                        try:
                            os.remove(destination)
                        except OSError as e_:
                            logger.debug(
                                "Remove decrypted pdf linked file from /documents\n" + destination + "\n" + str(e_))
                else:
                    # qpdf decrypt not implemented for windows, OSX.  Warn user of encrypted PDF
                    pdf_msg = _(
                        "Sometimes pdfs are encrypted, download and decrypt using qpdf before trying to load the pdf")
                    # Message(self.app, _('If import error occurs'), msg, "warning").exec()
                    if link_path == "":
                        copyfile(f, destination)
                        self.load_file_text(f)
                    else:
                        self.load_file_text(f, "docs:" + link_path)
                known_file_type = True

            # Media files
            if f.split('.')[-1].lower() in ('jpg', 'jpeg', 'png'):
                if link_path == "":
                    destination += "/images/" + filename
                    copyfile(f, destination)
                    self.load_media_reference("/images/" + filename)
                else:
                    self.load_media_reference("images:" + link_path)
                known_file_type = True
            if f.split('.')[-1].lower() in ('wav', 'mp3', 'm4a'):
                if link_path == "":
                    destination += "/audio/" + filename
                    copyfile(f, destination)
                    self.load_media_reference("/audio/" + filename)
                else:
                    self.load_media_reference("audio:" + link_path)
                known_file_type = True
            if f.split('.')[-1].lower() in ('mkv', 'mov', 'mp4', 'ogg', 'wmv'):
                if link_path == "":
                    destination += "/video/" + filename
                    copyfile(f, destination)
                    self.load_media_reference("/video/" + filename)
                else:
                    self.load_media_reference("video:" + link_path)
                known_file_type = True
            if not known_file_type:
                Message(self.app, _('Unknown file type'),
                        _("Trying to import as text") + ":\n" + f,
                        "warning")
                destination += "/documents/" + filename
                if link_path == "":
                    try:
                        self.load_file_text(f)
                    except Exception as e_:
                        print(e_)
                        logger.warning(str(e_))
                    try:
                        copyfile(f, destination)
                    except OSError as e_:
                        logger.warning(str(e_))
                        Message(self.app, _('Unknown file type'), _("Cannot import file") + ":\n" + f, "warning")
                else:
                    try:
                        self.load_file_text(f, "docs:" + link_path)
                    except Exception as e_:
                        print(e_)
                        logger.warning(str(e_))
                        Message(self.app, _('Unknown file type'), _("Cannot import file") + ":\n" + f, "warning")
        if pdf_msg != "":
            self.parent_text_edit.append(pdf_msg)
        self.load_file_data()
        self.fill_table()
        self.app.delete_backup = False
        self.update_files_in_dialogs()

    def update_files_in_dialogs(self):
        """ Update files list in any opened dialogs:
         DialogReportCodes, DialogCodeText, DialogCodeAV, DialogCodeImage """

        contents = self.tab_coding.layout()
        if contents is not None:
            for i in reversed(range(contents.count())):
                c = contents.itemAt(i).widget()
                if isinstance(c, DialogCodeImage):
                    c.get_files()
                if isinstance(c, DialogCodeAV):
                    c.get_files()
                if isinstance(c, DialogCodeText):
                    c.get_files()
        contents = self.tab_reports.layout()
        if contents is not None:
            # Examine widgets in layout
            for i in reversed(range(contents.count())):
                c = contents.itemAt(i).widget()
                if isinstance(c, DialogReportCodes):
                    c.get_files_and_cases()

    def load_media_reference(self, mediapath):
        """ Load media reference information for audio, video, images.

        param:
            mediapath: QualCoder project folder path OR external link path to file
                       External link path contains prefix 'docs:', 'images:, 'audio:', 'video:'
        """

        # check for duplicated filename and update model, widget and database
        name_split = mediapath.split("/")
        filename = name_split[-1]
        if any(d['name'] == filename for d in self.source):
            QtWidgets.QMessageBox.warning(None, _('Duplicate file'), _("Duplicate filename.\nFile not imported"))
            return
        entry = {'name': filename, 'id': -1, 'fulltext': None, 'memo': "", 'mediapath': mediapath,
                 'owner': self.app.settings['codername'], 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 'av_text_id': None}
        cur = self.app.conn.cursor()
        cur.execute("insert into source(name,memo,owner,date, mediapath, fulltext) values(?,?,?,?,?,?)",
                    (
                        entry['name'], entry['memo'], entry['owner'], entry['date'], entry['mediapath'],
                        entry['fulltext']))
        self.app.conn.commit()
        cur.execute("select last_insert_rowid()")
        id_ = cur.fetchone()[0]
        entry['id'] = id_
        msg = entry['name']
        if ':' in mediapath:
            msg += _(" linked")
        else:
            msg += _(" imported.")
        self.parent_text_edit.append(msg)
        self.source.append(entry)

        # Create an empty transcription file for audio and video
        if mediapath[:6] in ("/audio", "audio:", "/video", "video:"):
            entry = {'name': filename + ".txt", 'id': -1, 'fulltext': "", 'mediapath': None, 'memo': "",
                     'owner': self.app.settings['codername'],
                     'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     'av_text_id': None}
            cur = self.app.conn.cursor()
            cur.execute("insert into source(name,fulltext,mediapath,memo,owner,date) values(?,?,?,?,?,?)",
                        (entry['name'], entry['fulltext'], entry['mediapath'], entry['memo'], entry['owner'],
                         entry['date']))
            self.app.conn.commit()
            cur.execute("select last_insert_rowid()")
            tr_id = cur.fetchone()[0]
            entry['id'] = tr_id
            # Update av file entry with av_text_id link to this text file
            cur.execute("update source set av_text_id=? where id=?", [tr_id, id_])
            self.app.conn.commit()

            # Add file attribute placeholders
            att_sql = 'select name from attribute_type where caseOrFile ="file"'
            cur.execute(att_sql)
            attr_types = cur.fetchall()
            insert_sql = "insert into attribute (name, attr_type, value, id, date, owner) values(?,'file','',?,?,?)"
            for a in attr_types:
                placeholders = [a[0], tr_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                self.app.settings['codername']]
                cur.execute(insert_sql, placeholders)
                self.app.conn.commit()

            self.parent_text_edit.append(entry['name'] + _(" created."))
            self.source.append(entry)

    def load_file_text(self, import_file, link_path=""):
        """ Import from file types of odt, docx pdf, epub, txt, html, htm.
        Implement character detection for txt imports.

        param:
            import_file: filepath of file to be imported, String
            link_path:  filepath of file to be linked, String
        """

        if self.av_dialog_open is not None:
            self.av_dialog_open.mediaplayer.stop()
            self.av_dialog_open = None
        text_ = ""
        # Import from odt
        if import_file[-4:].lower() == ".odt":
            text_ = self.convert_odt_to_text(import_file)
            text_ = text_.replace("\n", "\n\n")  # add line to paragraph spacing for visual format
        # Import from docx
        if import_file[-5:].lower() == ".docx":
            document = opendocx(import_file)
            list_ = getdocumenttext(document)
            text_ = "\n\n".join(list_)  # add line to paragraph spacing for visual format
        # Import from epub
        if import_file[-5:].lower() == ".epub":
            book = epub.read_epub(import_file)
            for d in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                try:
                    # print(d.get_content())
                    bytes_ = d.get_body_content()
                    string = bytes_.decode('utf-8')
                    text_ += html_to_text(string) + "\n\n"  # add line to paragraph spacing for visual format
                except TypeError as e_:
                    logger.debug("ebooklib get_body_content error " + str(e_))
        # Import PDF
        if import_file[-4:].lower() == '.pdf':
            fp = open(import_file, 'rb')  # read binary mode
            parser = PDFParser(fp)
            doc = PDFDocument(parser=parser)
            parser.set_document(doc)
            # Potential error with encrypted PDF
            rsrcmgr = PDFResourceManager()
            laparams = LAParams()
            laparams.char_margin = 1.0
            laparams.word_margin = 1.0
            device = PDFPageAggregator(rsrcmgr, laparams=laparams)
            interpreter = PDFPageInterpreter(rsrcmgr, device)
            for page in PDFPage.create_pages(doc):
                interpreter.process_page(page)
                layout = device.get_result()
                for lt_obj in layout:
                    if isinstance(lt_obj, LTTextBox) or isinstance(lt_obj, LTTextLine):
                        text_ += lt_obj.get_text() + "\n"  # add line to paragraph spacing for visual format
            # Remove excess line endings, include those with one blank space on a line
            text_ = text_.replace('\n \n', '\n')
            text_ = text_.replace('\n\n\n', '\n\n')
            # Fix Pdfminer recognising invalid unicode characters.
            text_ = text_.replace(u"\uE002", "Th")
            text_ = text_.replace(u"\uFB01", "fi")

        # Import from html
        if import_file[-5:].lower() == ".html" or import_file[-4:].lower() == ".htm":
            import_errors = 0
            with open(import_file, "r") as sourcefile:
                html_text = ""
                while 1:
                    line = sourcefile.readline()
                    if not line:
                        break
                    html_text += line
                text_ = html_to_text(html_text)
                QtWidgets.QMessageBox.warning(None, _('Warning'), str(import_errors) + _(" lines not imported"))
        # Try importing as a plain text file.
        # TODO https://stackoverflow.com/questions/436220/how-to-determine-the-encoding-of-text
        # coding = chardet.detect(file.content).get('encoding')
        # text = file.content[:10000].decode(coding)
        if text_ == "":
            import_errors = 0
            try:
                # can get UnicodeDecode Error on Windows so using error handler
                with open(import_file, "r", encoding="utf-8", errors="backslashreplace") as sourcefile:
                    while 1:
                        line = sourcefile.readline()
                        if not line:
                            break
                        try:
                            text_ += line
                        except Exception as e_:
                            logger.debug("Importing plain text file, line ignored: " + str(e_))
                            import_errors += 1
                    if text_[0:6] == "\ufeff":  # associated with notepad files
                        text_ = text_[6:]
            except Exception as e_:
                Message(self.app, _("Warning"), _("Cannot import") + str(import_file) + "\n" + str(e_),
                        "warning").exec()
                return
            if import_errors > 0:
                Message(self.app, _("Warning"), str(import_errors) + _(" lines not imported"), "warning").exec()
                logger.warning(import_file + ": " + str(import_errors) + _(" lines not imported"))
        # Import of text file did not work
        if text_ == "":
            Message(self.app, _("Warning"),
                    _("Cannot import ") + str(import_file) + "\nPlease check if the file is empty.", "warning").exec()
            return
        # Final checks: check for duplicated filename and update model, widget and database
        name_split = import_file.split("/")
        filename = name_split[-1]
        if any(d['name'] == filename for d in self.source):
            QtWidgets.QMessageBox.warning(None, _('Duplicate file'),
                                          _("Duplicate filename.\nFile not imported"))
            return

        mediapath = None
        if link_path != "":
            mediapath = link_path
        entry = {'name': filename, 'id': -1, 'fulltext': text_, 'mediapath': mediapath, 'memo': "",
                 'owner': self.app.settings['codername'], 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        cur = self.app.conn.cursor()
        # logger.debug("type fulltext: " + str(type(entry['fulltext'])))
        cur.execute("insert into source(name,fulltext,mediapath,memo,owner,date) values(?,?,?,?,?,?)",
                    (
                        entry['name'], entry['fulltext'], entry['mediapath'], entry['memo'], entry['owner'],
                        entry['date']))
        self.app.conn.commit()
        cur.execute("select last_insert_rowid()")
        id_ = cur.fetchone()[0]
        entry['id'] = id_

        # Add file attribute placeholders
        att_sql = 'select name from attribute_type where caseOrFile ="file"'
        cur.execute(att_sql)
        attr_types = cur.fetchall()
        insert_sql = "insert into attribute (name, attr_type, value, id, date, owner) values(?,'file','',?,?,?)"
        for a in attr_types:
            placeholders = [a[0], id_, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            self.app.settings['codername']]
            cur.execute(insert_sql, placeholders)
            self.app.conn.commit()

        msg = entry['name']
        if link_path == "":
            msg += _(" imported")
        else:
            msg += _(" linked")
        self.parent_text_edit.append(msg)
        self.source.append(entry)

    # @staticmethod
    def convert_odt_to_text(import_file):
        """ Convert odt to very rough equivalent with headings, list items and tables for
        html display in qTextEdits. """

        odt_file = zipfile.ZipFile(import_file)
        data = str(odt_file.read('content.xml'))  # bytes class to string
        # https://stackoverflow.com/questions/18488734/python3-unescaping-non-ascii-characters
        data = str(bytes([ord(char) for char in data.encode("utf_8").decode("unicode_escape")]), "utf_8")
        data_start = data.find("</text:sequence-decls>")
        data_end = data.find("</office:text>")
        if data_start == -1 or data_end == -1:
            logger.warning("ODT IMPORT ERROR")
            return ""
        data = data[data_start + 22: data_end]
        # print(data)
        data = data.replace('<text:h', '\n<text:h')
        data = data.replace('</text:h>', '\n\n')
        data = data.replace('</text:list-item>', '\n')
        data = data.replace('</text:span>', '')
        data = data.replace('</text:p>', '\n')
        data = data.replace('</text:a>', ' ')
        data = data.replace('</text:list>', '')
        data = data.replace('<text:list-item>', '')
        data = data.replace('<table:table table:name=', '\n=== TABLE ===\n<table:table table:name=')
        data = data.replace('</table:table>', '=== END TABLE ===\n')
        data = data.replace('</table:table-cell>', '\n')
        data = data.replace('</table:table-row>', '')
        data = data.replace('<draw:image', '\n=== IMG ===<draw:image')
        data = data.replace('</draw:frame>', '\n')
        text_ = ""
        tagged = False
        for i in range(0, len(data)):
            if data[i: i + 6] == "<text:" or data[i: i + 7] == "<table:" or data[i: i + 6] == "<draw:":
                tagged = True
            if not tagged:
                text_ += data[i]
            if data[i] == ">":
                tagged = False
        return text_

    def export(self):
        """ Export selected file to selected directory.
        If an imported file was from a docx, odt, pdf, html, epub then export the original file
        If the file was created within QualCoder (so only in the database), export as plain text.
        Can only export ONE file at time, due to tableWidget single selection mode
        Can only export file that was imported into the project folder.
        Need to check for this condition.
        """

        if self.av_dialog_open is not None:
            self.av_dialog_open.mediaplayer.stop()
            self.av_dialog_open = None
        index_list = self.ui.tableWidget.selectionModel().selectedIndexes()
        rows = []
        for i in index_list:
            rows.append(i.row())
        rows = list(set(rows))  # duplicate rows due to multiple columns
        if len(rows) == 0:
            return
        # Currently single selection mode in tableWidget, 1 row only, so rows[0]
        if self.source[rows[0]]['mediapath'] is not None and ':' in self.source[rows[0]]['mediapath'] \
                and (self.source[rows[0]]['fulltext'] is None or self.source[rows[0]]['fulltext'] == ""):
            msg = _("This is an external linked file") + "\n"
            msg += self.source[rows[0]]['mediapath'].split(':')[1]
            Message(self.app, _('Cannot export'), msg, "warning").exec()
            return
        # Warn of export of text representation of linked files (e.g. odt, docx, txt, md, pdf)
        text_rep = False
        if self.source[rows[0]]['mediapath'] is not None and ':' in self.source[rows[0]]['mediapath'] \
                and self.source[rows[0]]['fulltext'] != "":
            msg = _("This is a linked file. Will export text representation.") + "\n"
            msg += self.source[rows[0]]['mediapath'].split(':')[1]
            Message(self.app, _("Can export text"), msg, "warning").exec()
            text_rep = True
        # Currently can only export ONE file at time, due to tableWidget single selection mode
        row = rows[0]
        filename = self.source[row]['name']
        if self.source[row]['mediapath'] is None or self.source[row]['mediapath'][0:5] == 'docs:':
            filename = filename + ".txt"
        exp_dialog = ExportDirectoryPathDialog(self.app, filename)
        destination = exp_dialog.filepath
        if destination is None:
            return
        msg = _("Export to ") + destination + "\n"

        # export audio, video, picture files
        if self.source[row]['mediapath'] is not None and text_rep is False:
            file_path = self.app.project_path + self.source[row]['mediapath']
            # destination = directory + "/" + filename
            try:
                copyfile(file_path, destination)
                msg += destination + "\n"
            except FileNotFoundError:
                pass

        # export pdf, docx, odt, epub, html files if located in documents directory
        document_stored = os.path.exists(self.app.project_path + "/documents/" + self.source[row]['name'])
        if document_stored and self.source[row]['mediapath'] is None:
            # destination = directory + "/" + self.source[row]['name']
            try:
                copyfile(self.app.project_path + "/documents/" + self.source[row]['name'], destination)
                msg += destination + "\n"
            except FileNotFoundError as e_:
                logger.warning(str(e_))
                document_stored = False

        # Export transcribed files, user created text files, text representations of linked files
        if (self.source[row]['mediapath'] is None or self.source[row]['mediapath'][
                                                     0:5] == 'docs:') and not document_stored:
            filedata = self.source[row]['fulltext']
            f = open(destination, 'w', encoding='utf-8-sig')
            f.write(filedata)
            f.close()
            msg += destination + "\n"
        Message(self.app, _("Files exported"), msg).exec()
        self.parent_text_edit.append(filename + _(" exported to ") + msg)

    def delete_button_multiple_files(self):
        """ Delete files from database and update model and widget.
        Also, delete files from sub-directories, if not externally linked.

        Called by: delete button.
        """

        if self.av_dialog_open is not None:
            self.av_dialog_open.mediaplayer.stop()
            self.av_dialog_open = None
        ui = DialogSelectItems(self.app, self.source, _("Delete files"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selection = ui.get_selected()
        if not selection:
            return
        names = ""
        for s in selection:
            names = names + s['name'] + "\n"
        ui = DialogConfirmDelete(self.app, names)
        ok = ui.exec()
        if not ok:
            return

        msg = ""
        cur = self.app.conn.cursor()
        for s in selection:
            msg += _("Deleted file: ") + s['name'] + "\n"
            # Delete text source
            if s['mediapath'] is None or 'docs:' in s['mediapath']:
                try:
                    if s['mediapath'] is None:
                        os.remove(self.app.project_path + "/documents/" + s['name'])
                except OSError as e_:
                    logger.warning(_("Deleting file error: ") + str(e_))
                # Delete stored coded sections and source details
                cur.execute("delete from source where id = ?", [s['id']])
                cur.execute("delete from code_text where fid = ?", [s['id']])
                cur.execute("delete from annotation where fid = ?", [s['id']])
                cur.execute("delete from case_text where fid = ?", [s['id']])
                cur.execute("delete from attribute where attr_type ='file' and id=?", [s['id']])
                self.app.conn.commit()
            # Delete image, audio or video source
            if s['mediapath'] is not None and 'docs:' not in s['mediapath']:
                # Get linked transcript file id
                cur.execute("select av_text_id from source where id=?", [s['id']])
                res = cur.fetchone()
                av_text_id = res[0]
                # Remove avid links in code_text
                sql = "select avid from code_av where id=?"
                cur.execute(sql, [s['id']])
                avids = cur.fetchall()
                sql = "update code_text set avid=null where avid=?"
                for avid in avids:
                    cur.execute(sql, [avid[0]])
                self.app.conn.commit()
                # Remove project folder file, if internally stored
                if ':' not in s['mediapath']:
                    filepath = self.app.project_path + s['mediapath']
                    try:
                        os.remove(filepath)
                    except OSError as e_:
                        logger.warning(_("Deleting file error: ") + str(e_))
                # Delete stored coded sections and source details
                cur.execute("delete from source where id = ?", [s['id']])
                cur.execute("delete from code_image where id = ?", [s['id']])
                cur.execute("delete from code_av where id = ?", [s['id']])
                cur.execute("delete from attribute where attr_type='file' and id=?", [s['id']])
                # Just in case, added this line
                cur.execute("delete from case_text where fid = ?", [s['id']])
                self.app.conn.commit()

                # Delete linked transcription text file
                if av_text_id is not None:
                    cur.execute("delete from source where id = ?", [res[0]])
                    cur.execute("delete from code_text where fid = ?", [res[0]])
                    cur.execute("delete from annotation where fid = ?", [res[0]])
                    cur.execute("delete from case_text where fid = ?", [res[0]])
                    cur.execute("delete from attribute where attr_type ='file' and id=?", [res[0]])
                    self.app.conn.commit()

        self.update_files_in_dialogs()
        self.check_attribute_placeholders()
        self.parent_text_edit.append(msg)
        self.load_file_data()
        self.fill_table()
        self.app.delete_backup = False

    def delete(self):
        """ Delete one file from database and update model and widget.
        Deletes only one file due to table single selection mode
        Also, delete the file from sub-directories, if not externally linked.
        Called by: right-click table context menu.
        """

        if self.av_dialog_open is not None:
            self.av_dialog_open.mediaplayer.stop()
            self.av_dialog_open = None
        index_list = self.ui.tableWidget.selectionModel().selectedIndexes()
        rows = []
        for i in index_list:
            rows.append(i.row())
        rows = list(set(rows))  # duplicate rows due to multiple columns
        if len(rows) == 0:
            return
        names = ""
        names = names + self.source[rows[0]]['name'] + "\n"
        ui = DialogConfirmDelete(self.app, names)
        ok = ui.exec()
        if not ok:
            return

        cur = self.app.conn.cursor()
        row = rows[0]
        file_id = self.source[row]['id']
        # Delete text source
        if self.source[row]['mediapath'] is None or 'docs:' in self.source[row]['mediapath']:
            try:
                if self.source[row]['mediapath'] is None:
                    os.remove(self.app.project_path + "/documents/" + self.source[row]['name'])
            except OSError as e_:
                logger.warning(_("Deleting file error: ") + str(e_))
            # Delete stored coded sections and source details
            cur.execute("delete from source where id = ?", [file_id])
            cur.execute("delete from code_text where fid = ?", [file_id])
            cur.execute("delete from annotation where fid = ?", [file_id])
            cur.execute("delete from case_text where fid = ?", [file_id])
            cur.execute("delete from attribute where attr_type ='file' and id=?", [file_id])
            self.app.conn.commit()

        # Delete image, audio or video source
        if self.source[row]['mediapath'] is not None and 'docs:' not in self.source[row]['mediapath']:
            # Get linked transcript file id
            cur.execute("select av_text_id from source where id=?", [file_id])
            res = cur.fetchone()
            av_text_id = res[0]
            # Remove avid links in code_text
            sql = "select avid from code_av where id=?"
            cur.execute(sql, [file_id])
            avids = cur.fetchall()
            sql = "update code_text set avid=null where avid=?"
            for avid in avids:
                cur.execute(sql, [avid[0]])
            self.app.conn.commit()
            # Remove folder file, if internally stored
            if ':' not in self.source[row]['mediapath']:
                filepath = self.app.project_path + self.source[row]['mediapath']
                try:
                    os.remove(filepath)
                except OSError as e_:
                    logger.warning(_("Deleting file error: ") + str(e_))
            # Delete stored coded sections and source details
            cur.execute("delete from source where id = ?", [file_id])
            cur.execute("delete from code_image where id = ?", [file_id])
            cur.execute("delete from code_av where id = ?", [file_id])
            cur.execute("delete from attribute where attr_type='file' and id=?", [file_id])
            self.app.conn.commit()

            # Delete transcription text file
            if av_text_id is not None:
                cur.execute("delete from source where id = ?", [res[0]])
                cur.execute("delete from code_text where fid = ?", [res[0]])
                cur.execute("delete from annotation where fid = ?", [res[0]])
                cur.execute("delete from case_text where fid = ?", [res[0]])
                cur.execute("delete from attribute where attr_type ='file' and id=?", [res[0]])
                self.app.conn.commit()

        self.update_files_in_dialogs()
        self.check_attribute_placeholders()
        self.parent_text_edit.append(_("Deleted file: ") + self.source[row]['name'])
        self.load_file_data()
        self.fill_table()
        self.app.delete_backup = False

    def fill_table(self):
        """ Fill the table widget with file details. """

        self.ui.label_fcount.setText(_("Files: ") + str(len(self.source)))
        self.ui.tableWidget.setColumnCount(len(self.header_labels))
        self.ui.tableWidget.setHorizontalHeaderLabels(self.header_labels)
        rows = self.ui.tableWidget.rowCount()
        for r in range(0, rows):
            self.ui.tableWidget.removeRow(0)
        for row, data in enumerate(self.source):
            self.ui.tableWidget.insertRow(row)
            icon = data['icon']
            name_item = QtWidgets.QTableWidgetItem(data['name'])
            name_item.setIcon(icon)
            # Having un-editable file names helps with assigning icons
            name_item.setFlags(name_item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            # Externally linked - add link details to tooltip
            name_tt = data['metadata']
            if data['mediapath'] is not None and ':' in data['mediapath']:
                name_tt += _("\nExternally linked file:\n")
                name_tt += data['mediapath']
            name_item.setToolTip(name_tt)
            self.ui.tableWidget.setItem(row, self.NAME_COLUMN, name_item)
            date_item = QtWidgets.QTableWidgetItem(data['date'])
            date_item.setFlags(date_item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.DATE_COLUMN, date_item)
            memo_string = ""
            if data['memo'] is not None and data['memo'] != "":
                memo_string = _("Memo")
            memo_item = QtWidgets.QTableWidgetItem(memo_string)
            if data['memo'] is not None and data['memo'] != "":
                memo_item.setToolTip(data['memo'])
            memo_item.setFlags(date_item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.MEMO_COLUMN, memo_item)
            fid = data['id']
            if fid is None:
                fid = ""
            iditem = QtWidgets.QTableWidgetItem(str(fid))
            iditem.setFlags(iditem.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.ID_COLUMN, iditem)
            case_item = QtWidgets.QTableWidgetItem(data['case'])
            case_item.setFlags(case_item.flags() ^ QtCore.Qt.ItemFlag.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.CASE_COLUMN, case_item)

            # Add the attribute values
            for a in self.attributes:
                for col, header in enumerate(self.header_labels):
                    # print(fid, a[2], a[0], header)
                    # print(type(fid), type(a[2]), type(a[0]), type(header))
                    if fid == a[2] and a[0] == header:
                        # print("found", a)
                        self.ui.tableWidget.setItem(row, col, QtWidgets.QTableWidgetItem(str(a[1])))
        dialog_w = self.size().width() - 20
        table_w = 0
        for i in range(self.ui.tableWidget.columnCount()):
            table_w += self.ui.tableWidget.columnWidth(i)
        if self.ui.tableWidget.columnWidth(self.NAME_COLUMN) > 450 and table_w > dialog_w:
            self.ui.tableWidget.setColumnWidth(self.NAME_COLUMN, 450)
        self.ui.tableWidget.resizeRowsToContents()
        self.ui.tableWidget.hideColumn(self.ID_COLUMN)
        if self.app.settings['showids'] == 'True':
            self.ui.tableWidget.showColumn(self.ID_COLUMN)
        self.ui.tableWidget.verticalHeader().setVisible(False)
