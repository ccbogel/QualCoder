# -*- coding: utf-8 -*-

"""
Copyright (c) 2020 Colin Curtain

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

import logging
import datetime
import os
from PIL import Image
from PIL.ExifTags import TAGS
import platform
import sys
from shutil import copyfile, move
import subprocess
import traceback
import zipfile

vlc_msg = ""
try:
    import vlc
except Exception as e:
    vlc_msg = str(e)

from PyQt5 import QtCore, QtGui, QtWidgets

pdfminer_installed = True
try:
    from pdfminer.pdfpage import PDFPage
    from pdfminer.pdfparser import PDFParser
    from pdfminer.pdfdocument import PDFDocument
    from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
    from pdfminer.converter import PDFPageAggregator
    from pdfminer.layout import LAParams, LTTextBox, LTTextLine
except:  # ModuleNotFoundError
    pdfminer_installed = False
    text = "For Linux run the following on the terminal: sudo pip install pdfminer.six\n"
    text += "For Windows run the following in the command prmpt: pip install pdfminer.six"
    QtWidgets.QMessageBox.critical(None, _('pdfminer is not installed.'), _(text))

import ebooklib
from ebooklib import epub

from add_attribute import DialogAddAttribute
from add_item_name import DialogAddItemName
from code_text import DialogCodeText  # for isinstance()
from confirm_delete import DialogConfirmDelete
from docx import opendocx, getdocumenttext
from GUI.ui_dialog_manage_files import Ui_Dialog_manage_files
from GUI.ui_dialog_memo import Ui_Dialog_memo  # for manually creating a new file
from helpers import Message
from html_parser import *
from memo import DialogMemo
from select_items import DialogSelectItems
from view_image import DialogViewImage, DialogCodeImage  # DialogCodeImage for isinstance()
from view_av import DialogViewAV, DialogCodeAV  # DialogCodeAV for isinstance()
from reports import DialogReportCodes  # for isInstance()


path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception: ") + text)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 12pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(text)
    mb.exec_()


class DialogManageFiles(QtWidgets.QDialog):
    """ View, import, export, rename and delete text files.
    Files are normally imported into the qda project folder.
    Option to link to external A/V files.
    Notes regards icons in buttons:
    The buttons are 36x36 pixels and the icons are 32x32 pixels.
    """

    source = []
    app = None
    parent_textEdit = None
    tab_coding = None  # Tab widget coding tab for updates
    tab_reports = None  # Tab widget reports for updates
    text_view = None
    header_labels = []
    NAME_COLUMN = 0
    MEMO_COLUMN = 1
    DATE_COLUMN = 2
    ID_COLUMN = 3
    rows_hidden = False
    default_import_directory = os.path.expanduser("~")
    attribute_names = []  # list of dictionary name:value for AddAtributewww.git dialog
    dialog_list = []  # Used for opened image , text and AV dialogs

    def __init__(self, app, parent_textEdit, tab_coding, tab_reports):

        sys.excepthook = exception_handler
        self.app = app
        self.default_import_directory = self.app.settings['directory']
        self.parent_textEdit = parent_textEdit
        self.tab_coding = tab_coding
        self.tab_reports = tab_reports
        self.attributes = []
        self.dialog_list = []
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_manage_files()
        self.ui.setupUi(self)
        try:
            w = int(self.app.settings['dialogmanagefiles_w'])
            h = int(self.app.settings['dialogmanagefiles_h'])
            if h > 50 and w > 50:
                self.resize(w, h)
        except:
            pass
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.ui.tableWidget.itemChanged.connect(self.cell_modified)
        icon = QtGui.QIcon(QtGui.QPixmap('GUI/pencil_icon.png'))
        self.ui.pushButton_create.setIcon(icon)
        self.ui.pushButton_create.clicked.connect(self.create)
        icon = QtGui.QIcon(QtGui.QPixmap('GUI/eye_icon.png'))
        self.ui.pushButton_view.setIcon(icon)
        self.ui.pushButton_view.clicked.connect(self.view)
        icon = QtGui.QIcon(QtGui.QPixmap('GUI/delete_icon.png'))
        self.ui.pushButton_delete.setIcon(icon)
        self.ui.pushButton_delete.clicked.connect(self.delete_button_multiple_files)
        icon = QtGui.QIcon(QtGui.QPixmap('GUI/doc_import_icon.png'))
        self.ui.pushButton_import.setIcon(icon)
        self.ui.pushButton_import.clicked.connect(self.import_files)
        icon = QtGui.QIcon(QtGui.QPixmap('GUI/link_icon.png'))
        self.ui.pushButton_link.setIcon(icon)
        self.ui.pushButton_link.clicked.connect(self.link_files)
        icon = QtGui.QIcon(QtGui.QPixmap('GUI/linked_import_icon.png'))
        self.ui.pushButton_import_from_linked.setIcon(icon)
        self.ui.pushButton_import_from_linked.clicked.connect(self.button_import_linked_file)
        icon = QtGui.QIcon(QtGui.QPixmap('GUI/to_link_icon.png'))
        self.ui.pushButton_export_to_linked.setIcon(icon)
        self.ui.pushButton_export_to_linked.clicked.connect(self.button_export_file_as_linked_file)
        icon = QtGui.QIcon(QtGui.QPixmap('GUI/doc_export_icon.png'))
        self.ui.pushButton_export.setIcon(icon)
        self.ui.pushButton_export.clicked.connect(self.export)
        icon = QtGui.QIcon(QtGui.QPixmap('GUI/plus_icon.png'))
        self.ui.pushButton_add_attribute.setIcon(icon)
        self.ui.pushButton_add_attribute.clicked.connect(self.add_attribute)
        self.ui.tableWidget.cellClicked.connect(self.cell_selected)
        self.ui.tableWidget.cellDoubleClicked.connect(self.cell_double_clicked)
        self.ui.tableWidget.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.ui.tableWidget.customContextMenuRequested.connect(self.table_menu)
        self.ui.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.load_file_data()

    def closeEvent(self, event):
        """ Save dialog and splitter dimensions. """

        self.app.settings['dialogmanagefiles_w'] = self.size().width()
        self.app.settings['dialogmanagefiles_h'] = self.size().height()

    def table_menu(self, position):
        """ Context menu for displaying table rows in differing order """

        row = self.ui.tableWidget.currentRow()
        col = self.ui.tableWidget.currentColumn()
        # Use these next few lines to use for mvoing a linked file into or an internal file out of the project folder
        id_ = None
        mediapath = None
        id_ = int(self.ui.tableWidget.item(row, self.ID_COLUMN).text())
        for s in self.source:
            if s['id'] == id_:
                mediapath = s['mediapath']

        text = None
        try:
            text = str(self.ui.tableWidget.item(row, col).text())
            # some blanks cells contain None and some contain blank strings
            if text == "":
                text = None
        except:
            pass
        # action cannot be None otherwise may default to one of the actions below depending on column clicked
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_view = menu.addAction(_("View"))
        action_alphabetic = None
        action_date = None
        action_type = None
        action_equals_value = None
        action_order_by_value = None
        action_show_all = None
        action_import_linked = None
        action_export_to_linked = None
        if col < 4:
            action_alphabetic = menu.addAction(_("Alphabetic order"))
            action_date = menu.addAction(_("Date order"))
            action_type = menu.addAction(_("File type order"))
        if col > 3:
            action_equals_value = menu.addAction(_("Show this value"))
            action_order_by_value = menu.addAction(_("Order by attribute"))
        action_export = menu.addAction(_("Export"))
        action_delete = menu.addAction(_("Delete"))
        if self.rows_hidden:
            action_show_all = menu.addAction(_("Show all rows"))
        if mediapath is None or (mediapath is not None and mediapath[0] == "/"):
            action_export_to_linked = menu.addAction(_("Move file to externally linked file"))
        else:
            action_import_linked = menu.addAction(_("Import linked file"))
        action = menu.exec_(self.ui.tableWidget.mapToGlobal(position))
        if action is None:
            return
        if action == action_import_linked:
            self.import_linked_file(id_, mediapath)
        if action == action_export_to_linked:
            self.export_file_as_linked_file(id_, mediapath)
        if action == action_view:
            self.view()
        if action == action_export:
            self.export()
        if action== action_delete:
            self.delete()
        if action == action_alphabetic:
            self.load_file_data()
        if action == action_date:
            self.load_file_data("date")
            self.fill_table()
        if action == action_type:
            self.load_file_data("filetype")
        if action == action_order_by_value:
            self.load_file_data("attribute:" + self.header_labels[col])

        if action == action_equals_value:
            # Hide rows that do not match this value, text can be None type
            # Cell items can be None or exist with ''
            for r in range(0, self.ui.tableWidget.rowCount()):
                item = self.ui.tableWidget.item(r, col)
                # items can be None or appear to be None when item text == ''
                if text is None and (item is not None and len(item.text()) > 0):
                    self.ui.tableWidget.setRowHidden(r, True)
                if text is not None and (item is None or item.text().find(text) == -1):
                    self.ui.tableWidget.setRowHidden(r, True)
            self.rows_hidden = True
        if action == action_show_all:
            for r in range(0, self.ui.tableWidget.rowCount()):
                self.ui.tableWidget.setRowHidden(r, False)
            self.rows_hidden = False

    def button_export_file_as_linked_file(self):
        """ User presses button to export current row's file.
         Only to work with an exportable file. """

        row = self.ui.tableWidget.currentRow()
        id_ = None
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

        params:
            id_ : the file id, Integer
            mediapath: stored path to media, will be None for text files, or String
        """

        options = QtWidgets.QFileDialog.DontResolveSymlinks | QtWidgets.QFileDialog.ShowDirsOnly
        directory = QtWidgets.QFileDialog.getExistingDirectory(None,
            _("Select directory to save file"), self.app.last_export_directory, options)
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
        except Exception as e:
            logger.debug(str(e))
            Message(self.app, _("Cannot export"), _("Cannot export as linked file\n") + str(e), "warning").exec_()
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
        self.parent_textEdit.append(msg)
        self.app.conn.commit()
        self.update_files_in_dialogs()
        self.load_file_data()
        self.app.delete_backup = False

    def button_import_linked_file(self):
        """ User presses button to import a linked file into the project folder.
        Only to work with an importable file. """

        row = self.ui.tableWidget.currentRow()
        id_ = None
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
                #print("file", s[0],"attr", a[0], " res", res, type(res))
                if res is None:
                    #print("No attr placeholder found")
                    placeholders = [a[0], s[0], datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.app.settings['codername']]
                    cur.execute(insert_sql, placeholders)
                    self.app.conn.commit()

        # Check and delete attribute values where file has been deleted
        att_to_del_sql = "SELECT distinct attribute.id FROM  attribute where \
        attribute.id not in (select source.id from source) order by attribute.id asc"
        cur.execute(att_to_del_sql)
        res = cur.fetchall()
        for r in res:
            cur.execute("delete from attribute where id=?", [r[0],])
            self.app.conn.commit()

    def load_file_data(self, order_by=""):
        """ Documents images and audio contain the filetype suffix.
        No suffix implies the 'file' was imported from a survey question or created internally.
        This also fills out the table header lables with file attribute names.
        Files with the '.transcribed' suffix mean they are associated with audio and
        video files.
        Obtain some file metadata to use in table tooltip.
        param:
            order_by: string ""= name, "date" = date, "filetype" = mediapath, "attribute:attribute name" selected atribute
        """

        # check a placeholder attribute is present for the file, add if missing
        self.check_attribute_placeholders()
        self.source = []
        cur = self.app.conn.cursor()
        placeholders = None
        # default alphabetic order
        sql = "select name, id, fulltext, mediapath, memo, owner, date from source order by upper(name)"
        if order_by == "date":
            sql = "select name, id, fulltext, mediapath, memo, owner, date from source order by date, upper(name)"
        if order_by == "filetype":
            sql = "select name, id, fulltext, mediapath, memo, owner, date from source order by mediapath"
        if order_by[:10] == "attribute:":
            attribute_name = order_by[10:]
            # two types of ordering character or numeric
            cur.execute("select valuetype from attribute_type where name=?", [attribute_name])
            attr_type = cur.fetchone()[0]
            sql = 'select source.name, source.id, fulltext, mediapath, source.memo, source.owner, source.date \
                from source  join attribute on attribute.id = source.id \
                where attribute.attr_type = "file" and attribute.name=? '
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
            icon, metadata = self.get_icon_and_metadata(row[0], row[2], row[3])
            self.source.append({'name': row[0], 'id': row[1], 'fulltext': row[2],
            'mediapath': row[3], 'memo': row[4], 'owner': row[5], 'date': row[6], 'metadata': metadata, 'icon': icon})
        # attributes
        self.header_labels = [_("Name"), _("Memo"), _("Date"), _("Id")]
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

    def get_icon_and_metadata(self, name, fulltext, mediapath):
        """ Get metadata used in table tooltip.
        Called by: create, load_file_data
        param:
            name: string
            fulltext: None or string
            mediapath: None or string
        """

        metadata = name + "\n"
        icon = QtGui.QIcon("GUI/text.png")
        if fulltext is not None and len(fulltext) > 0 and mediapath is None:
            metadata += "Characters: " + str(len(fulltext))
            return icon, metadata
        if mediapath is None:
            logger.debug("empty media path error")
            return icon, metadata
        if fulltext is not None and len(fulltext) > 0 and mediapath[0:5] == 'docs:':
            metadata += "Characters: " + str(len(fulltext))
            icon = QtGui.QIcon("GUI/text_link.png")
            return icon, metadata

        abs_path = ""
        if 'audio:' == mediapath[0:6]:
            abs_path = mediapath[6:]
        elif 'video:' == mediapath[0:6]:
            abs_path = mediapath[6:]
        elif 'images:' == mediapath[0:7]:
            abs_path = mediapath[7:]
        else:
            abs_path = self.app.project_path + mediapath

        if mediapath[:8] == "/images/":
            icon = QtGui.QIcon("GUI/picture.png")
            w = 0
            h = 0
            try:
                image = Image.open(abs_path)
                w, h = image.size
            except:
                metadata += _("Cannot locate media. " + abs_path)
                return icon, metadata
            metadata += "W: " + str(w) + " x H: " + str(h)
        if mediapath[:7] == "images:":
            icon = QtGui.QIcon("GUI/picture_link.png")
            w = 0
            h = 0
            try:
                image = Image.open(abs_path)
                w, h = image.size
            except:
                metadata += _("Cannot locate media. " + abs_path)
                return icon, metadata
            metadata += "W: " + str(w) + " x H: " + str(h)
        if mediapath[:7] == "/video/":
            icon = QtGui.QIcon("GUI/play.png")
        if mediapath[:6] == "video:":
            icon = QtGui.QIcon("GUI/play_link.png")
        if mediapath[:7] == "/audio/":
            icon = QtGui.QIcon("GUI/sound.png")
        if mediapath[:6] == "audio:":
            icon = QtGui.QIcon("GUI/sound_link.png")
        if mediapath[:6] in ("/audio", "audio:", "/video", "video:"):
            if not os.path.exists(abs_path):
                metadata += _("Cannot locate media. " + abs_path)
                return icon, metadata

            instance = vlc.Instance()
            mediaplayer = instance.media_player_new()
            try:
                media = instance.media_new(abs_path)
                media.parse()
                msecs = media.get_duration()
                secs = int(msecs / 1000)
                mins = int(secs / 60)
                remainder_secs = str(secs - mins * 60)
                if len(remainder_secs) == 1:
                    remainder_secs = "0" + remainder_secs
                metadata += "Duration: " + str(mins) + ":" + remainder_secs
            except Exception as e:
                logger.debug(str(e))
                metadata += _("Cannot locate media. " + abs_path)
                return icon, metadata
        bytes = 0
        try:
            bytes = os.path.getsize(abs_path)
        except:
            pass
        metadata += "\nBytes: " + str(bytes)
        if bytes > 1024 and bytes < 1024 * 1024:
            metadata += "  " + str(int(bytes / 1024)) + "KB"
        if bytes > 1024 * 1024:
            metadata += "  " + str(int(bytes / 1024 / 1024)) + "MB"
        return icon, metadata

    def add_attribute(self):
        """ When add button pressed, opens the AddAtribute dialog to get new attribute text.
        Then get the attribute type through a dialog.
        AddAttribute dialog checks for duplicate attribute name.
        New attribute is added to the model and database. """

        check_names = self.attribute_names + [{'name': 'name'}, {'name':'memo'}, {'name':'id'}, {'name':'date'}]
        ok = ui = DialogAddAttribute(self.app, check_names)
        if not ok:
            return
        ui.exec_()
        name = ui.new_name
        value_type = ui.value_type
        if name == "":
            return

        self.attribute_names.append({'name': name})
        # update attribute_type list and database
        now_date = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        cur = self.app.conn.cursor()
        cur.execute("insert into attribute_type (name,date,owner,memo,caseOrFile, valuetype) values(?,?,?,?,?,?)"
            ,(name, now_date, self.app.settings['codername'], "", 'file', value_type))
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
        self.parent_textEdit.append(_("Attribute added to files: ") + name + ", " + _("type") + ": " + value_type)

    def cell_double_clicked(self):
        """  """

        x = self.ui.tableWidget.currentRow()
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
            name =self.source[x]['name'].lower()
            if name[-5:] == ".jpeg" or name[-4:] in ('.jpg', '.png', '.gif'):
                ui = DialogMemo(self.app, _("Memo for file ") + self.source[x]['name'],
                self.source[x]['memo'])
                ui.exec_()
                self.source[x]['memo'] = ui.memo
                cur = self.app.conn.cursor()
                cur.execute('update source set memo=? where id=?', (ui.memo, self.source[x]['id']))
                self.app.conn.commit()
            else:
                ui = DialogMemo(self.app, _("Memo for file ") + self.source[x]['name'],
                self.source[x]['memo'])
                ui.exec_()
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

        # update attribute value
        if y > self.ID_COLUMN:
            value = str(self.ui.tableWidget.item(x, y).text()).strip()
            attribute_name = self.header_labels[y]
            cur = self.app.conn.cursor()
            cur.execute("update attribute set value=? where id=? and name=? and attr_type='file'",
            (value, self.source[x]['id'], attribute_name))
            self.app.conn.commit()
            self.app.delete_backup = False
            #logger.debug("updating: " + attribute_name + " , " + value)
            self.ui.tableWidget.resizeColumnsToContents()

    def is_caselinked_or_coded_or_annotated(self, fid):
        """ Check for text linked to case, coded or annotated text.
        param: fid   the text file id
        return: True or False
        """

        cur = self.app.conn.cursor()
        sql = "select pos0,pos1 from case_text where fid=?"
        cur.execute(sql, [fid, ])
        case_linked = cur.fetchall()
        sql = "select pos0,pos1 from annotation where fid=?"
        cur.execute(sql, [fid, ])
        annote_linked = cur.fetchall()
        sql = "select pos0,pos1 from code_text where fid=?"
        cur.execute(sql, [fid, ])
        code_linked = cur.fetchall()
        if case_linked != [] or annote_linked != [] or code_linked != []:
            return True
        return False

    def highlight(self, fid):
        """ Add coding and annotation highlights. """

        self.text_view_remove_formatting()
        # Get highlight data
        cur = self.app.conn.cursor()
        sql = "select pos0,pos1 from annotation where fid=? union all select pos0,pos1 from code_text where fid=?"
        cur.execute(sql, [fid, fid])
        annoted_coded = cur.fetchall()
        format_ = QtGui.QTextCharFormat()
        format_.setFontFamily(self.app.settings['font'])
        format_.setFontPointSize(self.app.settings['fontsize'])
        # add formatting
        cursor = self.text_view.ui.textEdit.textCursor()
        for item in annoted_coded:
            cursor.setPosition(int(item[0]), QtGui.QTextCursor.MoveAnchor)
            cursor.setPosition(int(item[1]), QtGui.QTextCursor.KeepAnchor)
            format_.setFontUnderline(True)
            format_.setUnderlineColor(QtCore.Qt.red)
            cursor.setCharFormat(format_)

    def view(self):
        """ View and edit text file contents.
        Alternatively view an image, audio or video media. """

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

        restricted = self.is_caselinked_or_coded_or_annotated(self.source[x]['id'])
        title = _("View file: ") + self.source[x]['name'] + " (ID:" + str(self.source[x]['id']) + ") "
        if restricted:
            title += "RESTRICTED EDIT"
        # cannot easily edit file text of there are linked cases, codes or annotations
        self.text_view = DialogMemo(self.app, title, self.source[x]['fulltext'], "hide")
        self.text_view.ui.textEdit.setReadOnly(restricted)
        if restricted:
            self.text_view.ui.textEdit.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            self.text_view.ui.textEdit.customContextMenuRequested.connect(self.textEdit_restricted_menu)
        else:
            self.text_view.ui.textEdit.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            self.text_view.ui.textEdit.customContextMenuRequested.connect(self.textEdit_unrestricted_menu)
            self.text_view.ui.textEdit.currentCharFormatChanged.connect(self.text_view_remove_formatting)
        self.highlight(self.source[x]['id'])
        self.text_view.exec_()
        text = self.text_view.ui.textEdit.toPlainText()
        if text == self.source[x]['fulltext']:
            return
        self.source[x]['fulltext'] = text
        cur = self.app.conn.cursor()
        cur.execute("update source set fulltext=? where id=?", (text, self.source[x]['id']))
        self.app.conn.commit()

    def text_view_remove_formatting(self):
        """ Remove formatting from text edit on changed text.
         Useful when pasting mime data (rich text or html) from clipboard. """

        format_ = QtGui.QTextCharFormat()
        format_.setFontFamily(self.app.settings['font'])
        format_.setFontPointSize(self.app.settings['fontsize'])
        cursor = self.text_view.ui.textEdit.textCursor()
        cursor.setPosition(0, QtGui.QTextCursor.MoveAnchor)
        cursor.setPosition(len(self.text_view.ui.textEdit.toPlainText()), QtGui.QTextCursor.KeepAnchor)
        cursor.setCharFormat(format_)

    def textEdit_unrestricted_menu(self, position):
        """ Context menu for select all and copy of text.
         Used in the 'unrestricted' i.e. no coded text file. """

        if self.text_view.ui.textEdit.toPlainText() == "":
            return
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_select_all = menu.addAction(_("Select all"))
        action_copy = menu.addAction(_("Copy"))
        action = menu.exec_(self.text_view.ui.textEdit.mapToGlobal(position))
        if action == action_copy:
            selected_text = self.text_view.ui.textEdit.textCursor().selectedText()
            cb = QtWidgets.QApplication.clipboard()
            cb.clear(mode=cb.Clipboard)
            cb.setText(selected_text, mode=cb.Clipboard)
        if action == action_select_all:
            self.text_view.ui.textEdit.selectAll()

    def textEdit_restricted_menu(self, position):
        """ Context menu for selection of small sections of text to be edited.
        The section of text must be only non-annotated and non-coded or
        only annotated or coded.
        For use with a text file that has codes/annotations/casses linked to it."""

        if self.text_view.ui.textEdit.toPlainText() == "":
            return
        selected_text = self.text_view.ui.textEdit.textCursor().selectedText()
        text_cursor = self.text_view.ui.textEdit.textCursor()
        x = self.ui.tableWidget.currentRow()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_item_edit = menu.addAction(_("Edit text maximum 20 characters"))
        action_select_all = menu.addAction(_("Select all"))
        action_copy = menu.addAction(_("Copy"))
        action = menu.exec_(self.text_view.ui.textEdit.mapToGlobal(position))
        if action == action_item_edit and len(selected_text) > 0 and len(selected_text) < 21:
            result = self.crossover_check(x, text_cursor)
            if result['crossover']:
                return
            self.restricted_edit_text(x, text_cursor)
            # reload text
            self.text_view.ui.textEdit.setPlainText(self.source[x]['fulltext'])
            self.highlight(self.source[x]['id'])
        if action == action_copy:
            selected_text = self.text_view.ui.textEdit.textCursor().selectedText()
            cb = QtWidgets.QApplication.clipboard()
            cb.clear(mode=cb.Clipboard)
            cb.setText(selected_text, mode=cb.Clipboard)
        if action == action_select_all:
            self.text_view.ui.textEdit.selectAll()

    def crossover_check(self, x, text_cursor):
        """ Check text selection for codes and annotations that cross over with non-coded
        and non-annotated sections. User can only select coded or non-coded text, this makes
        updating changes much simpler.

        param: x the current table row
        param: text_cursor  - the document cursor
        return: dictionary of crossover indication and of whether selection is entirely coded annotated or neither """

        response = {"crossover": True, "coded_section":[], "annoted_section":[], "cased_section":[]}
        msg = _("Please select text that does not have a combination of coded and uncoded text.")
        msg += _(" Nor a combination of annotated and un-annotated text.\n")
        selstart = text_cursor.selectionStart()
        selend = text_cursor.selectionEnd()
        msg += _("Selection start: ") + str(selstart) + _(" Selection end: ") + str(selend) + "\n"
        cur = self.app.conn.cursor()
        sql = "select pos0,pos1 from code_text where fid=? and "
        sql += "((pos0>? and pos0<?)  or (pos1>? and pos1<?)) "
        cur.execute(sql, [self.source[x]['id'], selstart, selend, selstart, selend])
        code_crossover = cur.fetchall()
        if code_crossover != []:
            msg += _("Code crossover: ") + str(code_crossover)
            Message(self.app, _('Codes cross over text'), msg, "warning").exec_()
            return response
        # find if the selected text is coded
        sql = "select pos0,pos1 from code_text where fid=? and ?>=pos0 and ?<=pos1"
        cur.execute(sql, [self.source[x]['id'], selstart, selend])
        response['coded_section'] = cur.fetchall()
        sql = "select pos0,pos1 from annotation where fid=? and "
        sql += "((pos0>? and pos0<?) or (pos1>? and pos1<?))"
        cur.execute(sql, [self.source[x]['id'], selstart, selend, selstart, selend])
        annote_crossover = cur.fetchall()
        if annote_crossover != []:
            msg += _("Annotation crossover: ") + str(annote_crossover)
            Message(self.app, _('Annotations cross over text'), msg, "warning").exec_()
            return response
        # find if the selected text is annotated
        sql = "select pos0,pos1 from annotation where fid=? and ?>=pos0 and ?<=pos1"
        cur.execute(sql, [self.source[x]['id'], selstart, selend])
        response['annoted_section'] = cur.fetchall()
        response['crossover'] = False
        # find if the selected text is assigned to case
        sql = "select pos0,pos1, id from case_text where fid=? and ?>=pos0 and ?<=pos1"
        cur.execute(sql, [self.source[x]['id'], selstart, selend])
        response['cased_section'] = cur.fetchall()
        response['crossover'] = False
        return response

    def restricted_edit_text(self, x, text_cursor):
        """ Restricted edit of small sections of text. selected text can be replaced.
        Mainly used for fixing spelling mistakes.
        original text is here: self.source[x]['fulltext']

        param: x the current table row
        param: text_cursor  - the document cursor
        """

        txt = text_cursor.selectedText()
        selstart = text_cursor.selectionStart()
        selend = text_cursor.selectionEnd()

        if len(txt) > 20:
            msg = _("Can only edit small selections of text, up to 20 characters in length.") + "\n"
            msg += _("You selected " + str(len(txt)) + _(" characters"))
            Message(self.app, _('Too much text selected'), msg, "warning").exec_()
            return

        #TODO maybe use DialogMemo again
        edit_dialog = QtWidgets.QDialog()
        edit_ui = Ui_Dialog_memo()
        edit_ui.setupUi(edit_dialog)
        edit_dialog.resize(400, 60)
        edit_dialog.setWindowTitle(_("Edit text: start") +str(selstart) + _(" end:") + str(selend))
        edit_ui.textEdit.setFontPointSize(self.app.settings['fontsize'])
        edit_ui.textEdit.setPlainText(txt)
        ok = edit_dialog.exec_()
        if not ok:
            return
        new_text = edit_ui.textEdit.toPlainText()

        # split original text and fix
        #original_text = self.source[x]['fulltext']
        before = self.source[x]['fulltext'][0:text_cursor.selectionStart()]
        after = self.source[x]['fulltext'][text_cursor.selectionEnd():len(self.source[x]['fulltext'])]
        fulltext = before + new_text + after

        # update database with the new fulltext
        self.source[x]['fulltext'] = fulltext
        cur = self.app.conn.cursor()
        sql = "update source set fulltext=? where id=?"
        cur.execute(sql, [fulltext, self.source[x]['id']])
        self.app.conn.commit()
        length_diff = len(new_text) - len(txt)
        if length_diff == 0:
            return
        """ UPDATE CODES//CASES/ANNOTATIONS located after the selected text
        Update database for codings, annotations and case linkages.
        Find affected codings annotations and case linkages.
        All codes, annotations and case linkages that occur after this text selection can be easily updated
        by adding the length diff to the pos0 and pos1 fields. """
        cur = self.app.conn.cursor()
        # find cases after this text section
        sql = "select id, pos0,pos1 from case_text where fid=? and pos1>? "
        sql += "and not(?>=pos0 and ?<=pos1)"
        cur.execute(sql, [self.source[x]['id'], selend, selstart, selend])
        post_case_linked = cur.fetchall()
        # find annotations after this text selection
        sql = "select anid,pos0,pos1 from annotation where fid=? and pos1>? "
        sql += "and not(?>=pos0 and ?<=pos1)"
        cur.execute(sql, [self.source[x]['id'], selend, selstart, selend])
        post_annote_linked = cur.fetchall()
        # find codes after this text selection section
        sql = "select pos0,pos1 from code_text where fid=? and pos1>? "
        sql += "and not(?>=pos0 and ?<=pos1)"
        cur.execute(sql, [self.source[x]['id'], selend, selstart, selend])
        post_code_linked = cur.fetchall()
        txt = text_cursor.selectedText()
        #print("cursor selstart", text_cursor.selectionStart())
        #print("cursor selend", text_cursor.selectionEnd())
        #print("length_diff", length_diff, "\n")

        for i in post_case_linked:
            #print(i)
            #print(i[0], i[1] + length_diff, i[2] + length_diff)
            #print("lengths ", len(original_text), i[2] - i[1])
            sql = "update case_text set pos0=?, pos1=? where id=?"
            cur.execute(sql, [i[1] + length_diff, i[2] + length_diff, i[0]])
        for i in post_annote_linked:
            sql = "update annotation set pos0=?, pos1=? where anid=?"
            cur.execute(sql, [i[1] + length_diff, i[2] + length_diff, i[0]])
        for i in post_code_linked:
            sql = "update code_text set pos0=?,pos1=? where fid=? and pos0=? and pos1=?"
            cur.execute(sql, [i[0] + length_diff, i[1] + length_diff, self.source[x]['id'], i[0], i[1]])
        self.app.conn.commit()

        # UPDATE THE CODED AND/OR ANNOTATED SECTION
        # The crossover dictionary contains annotations and codes for this section
        # need to extend or reduce the code or annotation length
        # the coded text stored in code_text also need to be updated
        crossovers = self.crossover_check(x, text_cursor)
        # Codes in this selection
        for i in crossovers['coded_section']:
            #print("selected text coded: ", i)
            sql = "update code_text set seltext=?,pos1=? where fid=? and pos0=? and pos1=?"
            newtext = fulltext[i[0]:i[1] + length_diff]
            cur.execute(sql, [newtext, i[1] + length_diff, self.source[x]['id'], i[0], i[1]])
        # Annotations in this selection
        for i in crossovers['annoted_section']:
            #print("selected text annoted: ", i)
            sql = "update annotation set pos1=? where fid=? and pos0=? and pos1=?"
            cur.execute(sql, [i[1] + length_diff, self.source[x]['id'], i[0], i[1]])
        for i in crossovers['cased_section']:
            #print("selected text as case: ", i)
            sql = "update case_text set pos1=? where fid=? and pos0=? and pos1=?"
            cur.execute(sql, [i[1] + length_diff, self.source[x]['id'], i[0], i[1]])
        self.app.conn.commit()

        self.app.delete_backup = False

    def view_av(self, x):
        """ View an audio or video file. Edit the memo. Edit the transcribed file.
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
            #TODO update bad links
            self.parent_textEdit.append(_("Bad link or non-existent file ") + abs_path)
            return

        try:
            ui = DialogViewAV(self.app, self.source[x])
            ui.exec_()  # this dialog does not display well on Windows 10 so trying .show()
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
        except Exception as e:
            logger.debug(e)
            print(e)
            Message(self.app, _('view AV error'), str(e), "warning").exec_()
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
            #TODO update bad links
            self.parent_textEdit.append(_("Bad link or non-existent file ") + abs_path)
            return

        ui = DialogViewImage(self.app, self.source[x])
        self.dialog_list.append(ui)
        ui.exec_()
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

    def create(self):
        """ Create a new text file by entering text into the dialog.
        Implements the QtDesigner memo dialog. """

        ui = DialogAddItemName(self.app, self.source,_('New File'), _('Enter file name'))
        ui.exec_()
        name = ui.get_new_name()
        if name is None:
            return
        ui = DialogMemo(self.app, _("Creating a new file: ") + name)
        ui.exec_()
        filetext = ui.memo

        # Create entry details to add to self.source and to database
        icon, metadata = self.get_icon_and_metadata(name, filetext, None)
        entry = {'name': name, 'id': -1, 'fulltext': filetext, 'memo': "",
        'owner': self.app.settings['codername'], 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'mediapath': None, 'icon': icon, 'metadata': metadata}

        # Update database
        cur = self.app.conn.cursor()
        cur.execute("insert into source(name,fulltext,mediapath,memo,owner,date) values(?,?,?,?,?,?)",
            (entry['name'], entry['fulltext'], entry['mediapath'], entry['memo'], entry['owner'], entry['date']))
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
            placeholders = [a[0], id_, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.app.settings['codername']]
            cur.execute(insert_sql, placeholders)
            self.app.conn.commit()
        self.update_files_in_dialogs()
        self.parent_textEdit.append(_("File created: ") + entry['name'])
        self.source.append(entry)
        self.fill_table()
        self.app.delete_backup = False

    def link_files(self):
        """ Trigger to link to file location. """

        self.import_files(True)

    def import_files(self, link=False):
        """ Import files and store into relevant directories (documents, images, audio, video).
        Convert documents to plain text and store this in data.qda
        Can import from plain text files, also import from html, odt, docx and md
        md is text markdown format.
        Note importing from html, odt, docx all formatting is lost.
        Imports images as jpg, jpeg, png which are stored in an images directory.
        Imports audio as mp3, wav, m4a which are stored in an audio directory.
        Imports video as mp4, mov, ogg, wmv which are stored in a video directory.

        param:
            link:   False - files are imported into project folder,
                    True- files are linked and not imported
        """

        imports, ok = QtWidgets.QFileDialog.getOpenFileNames(None, _('Open file'),
            self.default_import_directory)
        if not ok or imports == []:
            return
        known_file_type = False
        name_split = imports[0].split("/")
        temp_filename = name_split[-1]
        self.default_import_directory = imports[0][0:-len(temp_filename)]
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
            if f.split('.')[-1].lower() in ('pdf'):
                if pdfminer_installed is False:
                    text = "For Linux run the following on the terminal: sudo pip install pdfminer.six\n"
                    text += "For Windows run the following in the command prompt: pip install pdfminer.six"
                    Message(self.app, _("pdf miner is not installed"), _(text) + str(e),"critical").exec_()
                    return
                destination += "/documents/" + filename
                # remove encryption from pdf if possible, for Linux
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
                        except Exception as e:
                            logger.debug("Remove decrypted pdf linked file from /documents\n" + destination + "\n" + str(e))
                else:
                    # qpdf decrypt not implemented for windows, OSX.  Warn user of encrypted PDF
                    msg = _("Sometimes pdfs are encrypted, download and decrypt using qpdf before trying to load the pdf") + ":\n" + f
                    Message(self.app, _('If import error occurs'), msg, "warning").exec_()
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
                    _("Trying to import as text") + ":\n" + f
                    , "warning")
                destination += "/documents/" + filename
                if link_path == "":
                    try:
                        self.load_file_text(f)
                        copyfile(f, destination)
                    except Exception as e:
                        Message(self.app, _('Unknown file type'), _("Cannot import file") + ":\n" + f, "warning")
                else:
                    try:
                        self.load_file_text(f, "docs:" + link_path)
                    except Exception as e:
                        Message(self.app, _('Unknown file type'),  _("Cannot import file") + ":\n" + f, "warning")
        self.load_file_data()
        self.fill_table()
        self.app.delete_backup = False
        self.update_files_in_dialogs()

    def update_files_in_dialogs(self):
        """ Update files list in any opened dialogs:
         DialogReportCodes, DialogCodeText, DialogCodeAV, DialogCodeImage """

        contents = self.tab_coding.layout()
        if contents:
            for i in reversed(range(contents.count())):
                c = contents.itemAt(i).widget()
                if isinstance(c, DialogCodeImage):
                    c.get_files()
                if isinstance(c, DialogCodeAV):
                    c.get_files()
                if isinstance(c, DialogCodeText):
                    c.get_files()
        contents = self.tab_reports.layout()
        if contents:
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
        'owner': self.app.settings['codername'], 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        cur = self.app.conn.cursor()
        cur.execute("insert into source(name,memo,owner,date, mediapath, fulltext) values(?,?,?,?,?,?)",
            (entry['name'], entry['memo'], entry['owner'], entry['date'], entry['mediapath'], entry['fulltext']))
        self.app.conn.commit()
        cur.execute("select last_insert_rowid()")
        id_ = cur.fetchone()[0]
        entry['id'] = id_
        msg = entry['name']
        if ':' in mediapath:
            msg += _(" linked")
        else:
            msg += _(" imported.")
        self.parent_textEdit.append(msg)
        self.source.append(entry)

        # Create an empty transcription file for audio and video
        if mediapath[:6] in("/audio", "audio:", "/video", "video:"):
            entry = {'name': filename + ".transcribed", 'id': -1, 'fulltext': "", 'mediapath': None, 'memo': "",
            'owner': self.app.settings['codername'], 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            cur = self.app.conn.cursor()
            cur.execute("insert into source(name,fulltext,mediapath,memo,owner,date) values(?,?,?,?,?,?)",
                (entry['name'],  entry['fulltext'], entry['mediapath'], entry['memo'], entry['owner'], entry['date']))
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

            self.parent_textEdit.append(entry['name'] + _(" created."))
            self.source.append(entry)

    def load_file_text(self, import_file, link_path=""):
        """ Import from file types of odt, docx pdf, epub, txt, html, htm.
        Implement character detection for txt imports.

        param:
            import_file: filepath of file to be imported, String
            link_path:  filepath of file to be linked, String
        """

        text = ""

        # Import from odt
        if import_file[-4:].lower() == ".odt":
            text = self.convert_odt_to_text(import_file)
            text = text.replace("\n", "\n\n")  # add line to paragraph spacing for visual format
        # Import from docx
        if import_file[-5:].lower() == ".docx":
            #text = convert(importFile)  # uses docx_to_html
            document = opendocx(import_file)
            list_ = getdocumenttext(document)
            text = "\n\n".join(list_)  # add line to paragraph spacing for visual format
        # Import from epub
        if import_file[-5:].lower() == ".epub":
            book = epub.read_epub(import_file)
            for d in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                try:
                    #print(d.get_content())
                    bytes_ = d.get_body_content()
                    string = bytes_.decode('utf-8')
                    text += html_to_text(string) + "\n\n"  # add line to paragraph spacing for visual format
                except TypeError as e:
                    logger.debug("ebooklib get_body_content error " + str(e))
        # import PDF
        if import_file[-4:].lower() == '.pdf':
            fp = open(import_file, 'rb')  # read binary mode
            parser = PDFParser(fp)
            doc = PDFDocument(parser=parser)
            parser.set_document(doc)
            # potential error with encrypted PDF
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
                        text += lt_obj.get_text() + "\n"  # add line to paragraph spacing for visual format
            # remove excess line endings, include those with one blank space on a line
            text = text.replace('\n \n', '\n')
            text = text.replace('\n\n\n', '\n\n')

        # import from html
        if import_file[-5:].lower() == ".html" or import_file[-4:].lower() == ".htm":
            importErrors = 0
            with open(import_file, "r") as sourcefile:
                fileText = ""
                while 1:
                    line = sourcefile.readline()
                    if not line:
                        break
                    fileText += line
                text = html_to_text(fileText)
                QtWidgets.QMessageBox.warning(None, _('Warning'), str(importErrors) + _(" lines not imported"))
        # Try importing as a plain text file.
        #TODO https://stackoverflow.com/questions/436220/how-to-determine-the-encoding-of-text
        #coding = chardet.detect(file.content).get('encoding')
        #text = file.content[:10000].decode(coding)
        if text == "":
            import_errors = 0
            try:
                # can get UnicodeDecode Error on Windows so using error handler
                with open(import_file, "r", encoding="utf-8", errors="backslashreplace") as sourcefile:
                    while 1:
                        line = sourcefile.readline()
                        if not line:
                            break
                        try:
                            text += line
                        except Exception as e:
                            #logger.debug("Importing plain text file, line ignored: " + str(e))
                            import_errors += 1
                    if text[0:6] == "\ufeff":  # associated with notepad files
                        text = text[6:]
            except Exception as e:
                Message(self.app, _("Warning"), _("Cannot import") + str(import_file) + "\n" + str(e), "warning").exec_()
                return
            if import_errors > 0:
                Message(self.app, _("Warning"), str(import_errors) + _(" lines not imported"), "warning").exec_()
                logger.warning(import_file + ": " + str(import_errors) + _(" lines not imported"))
        # import of text file did not work
        if text == "":
            Message(self.app, _("Warning"), _("Cannot import ") + str(import_file) + "\n" + str(e), "warning").exec_()
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
        entry = {'name': filename, 'id': -1, 'fulltext': text, 'mediapath': mediapath, 'memo': "",
        'owner': self.app.settings['codername'], 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        cur = self.app.conn.cursor()
        #logger.debug("type fulltext: " + str(type(entry['fulltext'])))
        cur.execute("insert into source(name,fulltext,mediapath,memo,owner,date) values(?,?,?,?,?,?)",
            (entry['name'],  entry['fulltext'], entry['mediapath'], entry['memo'], entry['owner'], entry['date']))
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
            placeholders = [a[0], id_, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), self.app.settings['codername']]
            cur.execute(insert_sql, placeholders)
            self.app.conn.commit()

        msg = entry['name']
        if link_path == "":
            msg += _(" imported")
        else:
            msg += _(" linked")
        self.parent_textEdit.append(msg)
        self.source.append(entry)

    def convert_odt_to_text(self, import_file):
        """ Convert odt to very rough equivalent with headings, list items and tables for
        html display in qTextEdits. """

        odt_file = zipfile.ZipFile(import_file)
        data = str(odt_file.read('content.xml'))  # bytes class to string
        #https://stackoverflow.com/questions/18488734/python3-unescaping-non-ascii-characters
        data = str(bytes([ord(char) for char in data.encode("utf_8").decode("unicode_escape")]), "utf_8")
        data_start = data.find("</text:sequence-decls>")
        data_end = data.find("</office:text>")
        if data_start == -1 or data_end == -1:
            logger.warning("ODT IMPORT ERROR")
            return ""
        data = data[data_start + 22: data_end]
        #print(data)
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

        text = ""
        tagged = False
        for i in range(0, len(data)):
            if data[i: i + 6] == "<text:" or data[i: i + 7] == "<table:" or data[i: i + 6] == "<draw:":
                tagged = True
            if not tagged:
                text += data[i]
            if data[i] == ">":
                tagged = False
        return text

    def export(self):
        """ Export files to selected directory.
        If an imported file was from a docx, odt, pdf, html, epub then export the original file
        If the file was created within QualCoder (so only in the database), export as plain text.

        Currently can only export ONE file at time, due to tableWidget single selection mode

        Can only export files that were imported into the project folder.
        Need to check for this condition.
        """

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
            Message(self.app, _('Cannot export'), msg, "warning").exec_()
            return
        # Warn of export of text representation of linked files (e.g. odt, docx, txt, md, pdf)
        text_rep = False
        if self.source[rows[0]]['mediapath'] is not None and ':' in self.source[rows[0]]['mediapath'] \
                and self.source[rows[0]]['fulltext'] != "":
            msg = _("This is a linked file. Will export text representation.") + "\n"
            msg += self.source[rows[0]]['mediapath'].split(':')[1]
            Message(self.app, _("Can export text"), msg, "warning").exec_()
            text_rep = True

        options = QtWidgets.QFileDialog.DontResolveSymlinks | QtWidgets.QFileDialog.ShowDirsOnly
        directory = QtWidgets.QFileDialog.getExistingDirectory(None,
            _("Select directory to save file"), self.app.last_export_directory, options)
        if directory == "":
            return
        if directory != self.app.last_export_directory:
            self.app.last_export_directory = directory
        names = _("Export to ") + directory + "\n"
        #for row in rows:
        # Currently single selection mode in tableWidget
        names = names + self.source[rows[0]]['name'] + "\n"
        ui = DialogConfirmDelete(self.app, names, _("Export files"))
        ok = ui.exec_()
        if not ok:
            return
        msg = _("Export to ") + directory + "\n"
        # Currently can only export ONE file at time, due to tableWidget single selection mode
        #for row in rows:
        row = rows[0]
        filename = self.source[row]['name']

        # export audio, video, picture files
        if self.source[row]['mediapath'] is not None and text_rep is False:
            file_path = self.app.project_path + self.source[row]['mediapath']
            destination = directory + "/" + filename
            try:
                copyfile(file_path, destination)
                msg += destination + "\n"
            except FileNotFoundError:
                pass

        # export pdf, docx, odt, epub, html files if located in documents directory
        document_stored = os.path.exists(self.app.project_path + "/documents/" + self.source[row]['name'])
        if document_stored and self.source[row]['mediapath'] is None:
            destination = directory + "/" + self.source[row]['name']
            try:
                copyfile(self.app.project_path + "/documents/" + self.source[row]['name'], destination)
                msg += destination + "\n"
            except FileNotFoundError as e:
                logger.warning(str(e))
                document_stored = False

        # Export transcribed files, user created text files, text representations of linked files
        if (self.source[row]['mediapath'] is None or self.source[row]['mediapath'][0:5] == 'docs:') and not document_stored:
            filename_txt = filename + ".txt"
            filename_txt = directory + "/" + filename_txt
            filedata = self.source[row]['fulltext']
            f = open(filename_txt, 'w', encoding='utf-8-sig')
            f.write(filedata)
            f.close()
            msg += filename_txt + "\n"
        Message(self.app, _("Files exported"), msg).exec_()
        self.parent_textEdit.append(filename + _(" exported to ") + msg)

    def delete_button_multiple_files(self):
        """ Delete files from database and update model and widget.
        Also, delete files from sub-directories, if not externally linked.

        Called by: delete button.
        """

        ui = DialogSelectItems(self.app, self.source, _("Delete files"), "multi")
        ok = ui.exec_()
        if not ok:
            return
        selection = ui.get_selected()
        if selection == []:
            return
        names = ""
        for s in selection:
            names = names + s['name'] + "\n"
        ui = DialogConfirmDelete(self.app, names)
        ok = ui.exec_()
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
                except Exception as e:
                    logger.warning(_("Deleting file error: ") + str(e))
                # Delete stored coded sections and source details
                cur.execute("delete from source where id = ?", [s['id']])
                cur.execute("delete from code_text where fid = ?", [s['id']])
                cur.execute("delete from annotation where fid = ?", [s['id']])
                cur.execute("delete from case_text where fid = ?", [s['id']])
                cur.execute("delete from attribute where attr_type ='file' and id=?", [s['id']])
                self.app.conn.commit()
            # Delete image, audio or video source
            if s['mediapath'] is not None and 'docs:' not in s['mediapath']:
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
                    except Exception as e:
                        logger.warning(_("Deleting file error: ") + str(e))
                # Delete stored coded sections and source details
                cur.execute("delete from source where id = ?", [s['id']])
                cur.execute("delete from code_image where id = ?", [s['id']])
                cur.execute("delete from code_av where id = ?", [s['id']])
                cur.execute("delete from attribute where attr_type='file' and id=?", [s['id']])
                self.app.conn.commit()

                # Delete the .transcribed text file
                transcribed = s['name'] + ".transcribed"
                print("transcribed ", transcribed)
                cur.execute("select id from source where name=?", [transcribed])
                res = cur.fetchone()
                if res is not None:
                    cur.execute("delete from source where id = ?", [res[0]])
                    cur.execute("delete from code_text where fid = ?", [res[0]])
                    cur.execute("delete from annotation where fid = ?", [res[0]])
                    cur.execute("delete from case_text where fid = ?", [res[0]])
                    cur.execute("delete from attribute where attr_type ='file' and id=?", [res[0]])
                    self.app.conn.commit()

        self.update_files_in_dialogs()
        self.check_attribute_placeholders()
        self.parent_textEdit.append(msg)
        self.load_file_data()
        self.fill_table()
        self.app.delete_backup = False

    def delete(self):
        """ Delete one file from database and update model and widget.
        Deletes only one file due to table single selection mode
        Also, delete the file from sub-directories, if not externally linked.
        Called by: right-click table context menu.
        """

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
        ok = ui.exec_()
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
            except Exception as e:
                logger.warning(_("Deleting file error: ") + str(e))
            # Delete stored coded sections and source details
            cur.execute("delete from source where id = ?", [file_id])
            cur.execute("delete from code_text where fid = ?", [file_id])
            cur.execute("delete from annotation where fid = ?", [file_id])
            cur.execute("delete from case_text where fid = ?", [file_id])
            cur.execute("delete from attribute where attr_type ='file' and id=?", [file_id])
            self.app.conn.commit()

        # Delete image, audio or video source
        if self.source[row]['mediapath'] is not None and 'docs:' not in self.source[row]['mediapath']:
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
                except Exception as e:
                    logger.warning(_("Deleting file error: ") + str(e))
            # Delete stored coded sections and source details
            cur.execute("delete from source where id = ?", [file_id])
            cur.execute("delete from code_image where id = ?", [file_id])
            cur.execute("delete from code_av where id = ?", [file_id])
            cur.execute("delete from attribute where attr_type='file' and id=?", [file_id])
            self.app.conn.commit()

            # Delete the .transcribed text file
            transcribed = self.source[row]['name'] + ".transcribed"
            print("transcribed ", transcribed)
            cur.execute("select id from source where name=?", [transcribed])
            res = cur.fetchone()
            if res is not None:
                cur.execute("delete from source where id = ?", [res[0]])
                cur.execute("delete from code_text where fid = ?", [res[0]])
                cur.execute("delete from annotation where fid = ?", [res[0]])
                cur.execute("delete from case_text where fid = ?", [res[0]])
                cur.execute("delete from attribute where attr_type ='file' and id=?", [res[0]])
                self.app.conn.commit()

        self.update_files_in_dialogs()
        self.check_attribute_placeholders()
        self.parent_textEdit.append(_("Deleted file: ") + self.source[row]['name'])
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
            # having un-editable file names helps with assigning icons
            name_item.setFlags(name_item.flags() ^ QtCore.Qt.ItemIsEditable)
            # if externally linked add link details to tooltip
            name_tt = data['metadata']
            if data['mediapath'] is not None and ':' in data['mediapath']:
                name_tt += _("\nExternally linked file:\n")
                name_tt += data['mediapath']
            name_item.setToolTip((name_tt))
            self.ui.tableWidget.setItem(row, self.NAME_COLUMN, name_item)
            date_item = QtWidgets.QTableWidgetItem(data['date'])
            date_item.setFlags(date_item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.DATE_COLUMN, date_item)
            memo_string = ""
            if data['memo'] is not None and data['memo'] != "":
                memo_string = _("Memo")
            memo_item = QtWidgets.QTableWidgetItem(memo_string)
            if data['memo'] is not None and data['memo'] != "":
                memo_item.setToolTip(data['memo'])
            memo_item.setFlags(date_item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.MEMO_COLUMN, memo_item)
            fid = data['id']
            if fid is None:
                fid = ""
            iditem = QtWidgets.QTableWidgetItem(str(fid))
            iditem.setFlags(iditem.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.ID_COLUMN, iditem)
            # Add the attribute values
            for a in self.attributes:
                for col, header in enumerate(self.header_labels):
                    #print(fid, a[2], a[0], header)
                    #print(type(fid), type(a[2]), type(a[0]), type(header))
                    if fid == a[2] and a[0] == header:
                        #print("found", a)
                        self.ui.tableWidget.setItem(row, col, QtWidgets.QTableWidgetItem(str(a[1])))
        self.ui.tableWidget.resizeColumnsToContents()
        table_w = 0
        for i in range(self.ui.tableWidget.columnCount()):
            table_w += self.ui.tableWidget.columnWidth(i)
        #print("t", table_w)
        #print("d", self.size().width() - 20)  # 20 for L and R margins
        dialog_w = self.size().width() - 20
        if self.ui.tableWidget.columnWidth(self.NAME_COLUMN) > 450 and table_w > dialog_w:
            self.ui.tableWidget.setColumnWidth(self.NAME_COLUMN, 450)
        self.ui.tableWidget.resizeRowsToContents()
        self.ui.tableWidget.hideColumn(self.ID_COLUMN)
        if self.app.settings['showids'] == 'True':
            self.ui.tableWidget.showColumn(self.ID_COLUMN)
        self.ui.tableWidget.verticalHeader().setVisible(False)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    ui = Ui_Dialog_manage_files()
    ui.show()
    sys.exit(app.exec_())

