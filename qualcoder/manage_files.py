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

import logging
import datetime
import os
import platform
import sys
from shutil import copyfile
import subprocess
import traceback
import zipfile

from PyQt5 import QtCore, QtGui, QtWidgets

from add_item_name import DialogAddItemName
from confirm_delete import DialogConfirmDelete
from docx import opendocx, getdocumenttext
import ebooklib
from ebooklib import epub
from GUI.ui_dialog_attribute_type import Ui_Dialog_attribute_type
from GUI.ui_dialog_manage_files import Ui_Dialog_manage_files
from GUI.ui_dialog_memo import Ui_Dialog_memo  # for manually creating a new file
from html_parser import *
from memo import DialogMemo
from pdfminer.pdfparser import PDFParser, PDFDocument
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams, LTTextBox, LTTextLine
from view_image import DialogViewImage
from view_av import DialogViewAV

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception: ") + text)
    QtWidgets.QMessageBox.critical(None, _('Uncaught Exception'), text)


class DialogManageFiles(QtWidgets.QDialog):
    """ View, import, export, rename and delete text files. """

    source = []
    settings = None
    textDialog = None
    headerLabels = ["Name", "Memo", "Date", "Id"]
    NAME_COLUMN = 0
    MEMO_COLUMN = 1
    DATE_COLUMN = 2
    ID_COLUMN = 3
    default_import_directory = os.path.expanduser("~")
    attribute_names = []  # list of dictionary name:value for additem dialog
    parent_textEdit = None
    dialogList = []

    def __init__(self, settings, parent_textEdit):

        sys.excepthook = exception_handler
        self.settings = settings
        self.parent_textEdit = parent_textEdit
        self.dialogList = []
        self.load_file_data()
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_manage_files()
        self.ui.setupUi(self)
        newfont = QtGui.QFont(settings['font'], settings['fontsize'], QtGui.QFont.Normal)
        self.setFont(newfont)
        self.ui.tableWidget.itemChanged.connect(self.cell_modified)
        self.ui.pushButton_create.clicked.connect(self.create)
        self.ui.pushButton_view.clicked.connect(self.view)
        self.ui.pushButton_delete.clicked.connect(self.delete)
        self.ui.pushButton_import.clicked.connect(self.import_files)
        self.ui.pushButton_export.clicked.connect(self.export)
        self.ui.pushButton_add_attribute.clicked.connect(self.add_attribute)
        self.ui.tableWidget.cellClicked.connect(self.cell_selected)
        self.fill_table()

    def load_file_data(self):
        """ Documents images and audio contain the filetype suffix.
        No suffix implies the 'file' was imported from a survey question.
        This also fills out the table header lables with file attribute names.
        Files with the '.transcribed' suffix mean they are associated with audio and
        video files.
        """

        self.source = []
        cur = self.settings['conn'].cursor()
        # very occassionally code_text.seltext can be empty, when codes are unmarked from text
        # so remove these rows
        cur.execute('delete from code_text where length(seltext)=0')
        self.settings['conn'].commit()

        cur.execute("select name, id, fulltext, mediapath, memo, owner, date from source order by name")
        result = cur.fetchall()
        for row in result:
            self.source.append({'name': row[0], 'id': row[1], 'fulltext': row[2],
            'mediapath': row[3], 'memo': row[4], 'owner': row[5], 'date': row[6]})
        # attributes
        self.headerLabels = [_("Name"), _("Memo"), _("Date"), _("Id")]
        sql = "select name from attribute_type where caseOrFile='file'"
        cur.execute(sql)
        result = cur.fetchall()
        self.attribute_names = []
        for n in result:
            self.headerLabels.append(n[0])
            self.attribute_names.append({'name': n[0]})
        sql = "select attribute.name, value, id from attribute join attribute_type on \
        attribute_type.name=attribute.name where attribute_type.caseOrFile='file'"
        cur.execute(sql)
        result = cur.fetchall()
        self.attributes = []
        for row in result:
            self.attributes.append(row)

    def add_attribute(self):
        """ When add button pressed, opens the addItem dialog to get new attribute text.
        Then get the attribute type through a dialog.
        AddItem dialog checks for duplicate attribute name.
        New attribute is added to the model and database. """

        check_names = self.attribute_names + [{'name': 'name'}, {'name':'memo'}, {'name':'id'}, {'name':'date'}]
        ui = DialogAddItemName(check_names, _("New attribute name"))
        ui.exec_()
        name = ui.get_new_name()
        if name is None or name == "":
            return
        Dialog_type = QtWidgets.QDialog()
        ui = Ui_Dialog_attribute_type()
        ui.setupUi(Dialog_type)
        ok = Dialog_type.exec_()
        valuetype = "character"
        if ok and ui.radioButton_numeric.isChecked():
            valuetype = "numeric"
        self.attribute_names.append({'name': name})
        # update attribute_type list and database
        now_date = str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        cur = self.settings['conn'].cursor()
        cur.execute("insert into attribute_type (name,date,owner,memo,caseOrFile, valuetype) values(?,?,?,?,?,?)"
            ,(name, now_date, self.settings['codername'], "", 'file', valuetype))
        self.settings['conn'].commit()
        sql = "select id from source"
        cur.execute(sql)
        ids = cur.fetchall()
        for id_ in ids:
            sql = "insert into attribute (name, value, id, attr_type, date, owner) values (?,?,?,?,?,?)"
            cur.execute(sql, (name, "", id_[0], 'file', now_date, self.settings['codername']))
        self.settings['conn'].commit()
        self.load_file_data()
        self.fill_table()
        self.parent_textEdit.append(_("Attribute added to files: ") + name + ", " + _("type") + ": " + valuetype)

    def cell_selected(self):
        """ When the table widget memo cell is selected display the memo.
        Update memo text, or delete memo by clearing text.
        If a new memo also show in table widget by displaying YES in the memo column. """

        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()

        if y == self.MEMO_COLUMN:
            name =self.source[x]['name'].lower()
            if name[-5:] == ".jpeg" or name[-4:] in ('.jpg', '.png', '.gif'):
                ui = DialogMemo(self.settings, _("Memo for file ") + self.source[x]['name'],
                self.source[x]['memo'])
                ui.exec_()
                self.source[x]['memo'] = ui.memo
                cur = self.settings['conn'].cursor()
                cur.execute('update source set memo=? where id=?', (ui.memo, self.source[x]['id']))
                self.settings['conn'].commit()
            else:
                ui = DialogMemo(self.settings, _("Memo for file ") + self.source[x]['name'],
                self.source[x]['memo'])
                ui.exec_()
                self.source[x]['memo'] = ui.memo
                cur = self.settings['conn'].cursor()
                cur.execute('update source set memo=? where id=?', (ui.memo, self.source[x]['id']))
                self.settings['conn'].commit()
            if self.source[x]['memo'] == "":
                self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem())
            else:
                self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem("Yes"))

    def cell_modified(self):
        """ If the filename has been changed in the table widget update the database.
        Need to preserve the relationship between an audio/video file and its related
        transcribed file. Attribute values can be changed. """

        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        if y == self.NAME_COLUMN:
            new_text = str(self.ui.tableWidget.item(x, y).text()).strip()

            # check that no other source file has this text and this is is not empty
            update = True
            if new_text == "":
                update = False
            for c in self.source:
                if c['name'] == new_text:
                    update = False
            # .transcribed suffix is not to be used on a media file
            if new_text[-12:] == ".transcribed" and self.source[x]['mediapath'] is not None:
                update = False
            # Need to preserve names of a/v files and their
            # dependent transcribed files: filename.type.transcribed
            if update:
                if self.source[x]['mediapath'] is not None and self.source[x]['mediapath'][:2] in ('/a', '/v'):
                    msg = _("If there is an associated '.transcribed' file please rename ")
                    msg += _("it to match the media file plus '.transcribed'")
                    QtWidgets.QMessageBox.warning(None, "Media name", msg)
                if self.source[x]['name'][-12:] == ".transcribed":
                    msg = _("If there is an associated media file please rename ")
                    msg += _("it to match the media file before the '.transcribed' suffix")
                    QtWidgets.QMessageBox.warning(None, _("Media name"), msg)
                # update source list and database
                self.source[x]['name'] = new_text
                cur = self.settings['conn'].cursor()
                cur.execute("update source set name=? where id=?", (new_text, self.source[x]['id']))
                self.settings['conn'].commit()
            else:  # put the original text in the cell
                self.ui.tableWidget.item(x, y).setText(self.source[x]['name'])
        # update attribute value
        if y > self.ID_COLUMN:
            value = str(self.ui.tableWidget.item(x, y).text()).strip()
            attribute_name = self.headerLabels[y]
            cur = self.settings['conn'].cursor()
            cur.execute("update attribute set value=? where id=? and name=? and attr_type='file'",
            (value, self.source[x]['id'], attribute_name))
            self.settings['conn'].commit()
            #logger.debug("updating: " + attribute_name + " , " + value)
            self.ui.tableWidget.resizeColumnsToContents()

    def view(self):
        """ View and edit text file contents.
        Alternatively view an image or other media. """

        # need to relaod this, as transcribed files can be changed via view_av, and are otherwise not
        # updated
        self.load_file_data()

        x = self.ui.tableWidget.currentRow()
        if self.source[x]['mediapath'] is not None:
            if self.source[x]['mediapath'][:8] == "/images/":
                self.view_image(x)
                return
            if self.source[x]['mediapath'][:7] == "/video/":
                self.view_av(x)
                return
            if self.source[x]['mediapath'][:7] == "/audio/":
                self.view_av(x)
                return

        Dialog = QtWidgets.QDialog()
        ui = Ui_Dialog_memo()
        ui.setupUi(Dialog)
        ui.textEdit.setFontPointSize(self.settings['fontsize'])
        ui.textEdit.setPlainText(self.source[x]['fulltext'])
        Dialog.setWindowTitle(_("View file: ") + self.source[x]['name'] + " (ID:" + str(self.source[x]['id']) + ") ")
        Dialog.exec_()
        text = ui.textEdit.toPlainText()
        if text == self.source[x]['fulltext']:
            return
        cur = self.settings['conn'].cursor()
        # cannot edit file text of there are linked cases, codes or annotations
        sql = "select * from case_text where fid=?"
        cur.execute(sql, [self.source[x]['id'], ])
        ca_linked = cur.fetchall()
        sql = "select * from annotation where fid=?"
        cur.execute(sql, [self.source[x]['id'], ])
        a_linked = cur.fetchall()
        sql = "select * from code_text where fid=?"
        cur.execute(sql, [self.source[x]['id'], ])
        c_linked = cur.fetchall()
        if ca_linked != [] or a_linked != [] or c_linked != []:
            msg = _("Cannot edit file text, there are codes, cases or annotations linked to this file")
            QtWidgets.QMessageBox.warning(None, _('Warning'), msg, QtWidgets.QMessageBox.Ok)
            return

        self.source[x]['fulltext'] = text
        cur.execute("update source set fulltext=? where id=?", (text, self.source[x]['id']))
        self.settings['conn'].commit()

    def view_av(self, x):
        """ View an audio or video file. Edit the memo. Edit the transcribed file.
        Added try block in case VLC bindings do not work.
        Uses a non-modal dialog.
        """

        try:
            ui = DialogViewAV(self.settings, self.source[x])
            #ui.exec_()  # this dialog does not display well on Windows 10 so trying .show()
            self.dialogList.append(ui)
            ui.show()
            # try and update file data here
            self.load_file_data()
            if self.source[x]['memo'] == "":
                self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem())
            else:
                self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem("Yes"))
        except Exception as e:
            logger.debug(e)
            print(e)
            QtWidgets.QMessageBox.warning(None, 'view av error', str(e), QtWidgets.QMessageBox.Ok)
            return

    def view_image(self, x):
        """ View an image file and edit the image memo. """

        ui = DialogViewImage(self.settings, self.source[x])
        ui.exec_()
        memo = ui.ui.textEdit.toPlainText()
        if self.source[x]['memo'] != memo:
            self.source[x]['memo'] = memo
            cur = self.settings['conn'].cursor()
            cur.execute('update source set memo=? where id=?', (self.source[x]['memo'],
                self.source[x]['id']))
            self.settings['conn'].commit()
        if self.source[x]['memo'] == "":
            self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem())
        else:
            self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem("Yes"))

    def create(self):
        ''' Create a new text file by entering text into the dialog.
        Implements the QtDesigner memo dialog '''

        name, ok = QtWidgets.QInputDialog.getText(self, _('New File'), _('Enter the file name:'))
        if not ok:
            return
        if name is None or name == "":
            QtWidgets.QMessageBox.warning(None, _('Warning'),
                _("No filename was selected"), QtWidgets.QMessageBox.Ok)
            return
        # check for non-unique filename
        if any(d['name'] == name for d in self.source):
            QtWidgets.QMessageBox.warning(None, _('Warning'),
                _("Filename in use"), QtWidgets.QMessageBox.Ok)
            return

        ui = DialogMemo(self.settings, _("Creating a new file: ") + name)
        ui.exec_()
        filetext = ui.memo
        # update database
        entry = {'name': name, 'id': -1, 'fulltext': filetext, 'memo': "",
        'owner': self.settings['codername'], 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'mediapath': None}
        cur = self.settings['conn'].cursor()
        cur.execute("insert into source(name,fulltext,mediapath,memo,owner,date) values(?,?,?,?,?,?)",
            (entry['name'], entry['fulltext'], entry['mediapath'], entry['memo'], entry['owner'], entry['date']))
        self.settings['conn'].commit()
        self.parent_textEdit.append(_("File created: ") + entry['name'])
        self.source.append(entry)
        self.fill_table()

    def import_files(self):
        """ Import files and store into relevant directories (documents, images, ?audio?).
        Convert documents to plain text and store this in data.qda
        Can import from plain text files, also import from html, odt and docx
        Note importing from html, odt and docx all formatting is lost.
        Imports images as jpg, jpeg, png which are stored in an images directory.
        Imports audio as mp3, wav which are stored in an audio directory
        Imports video as mp4, mov, ogg, wmv which are stored in a video directory
        """

        imports, ok = QtWidgets.QFileDialog.getOpenFileNames(None, _('Open file'),
            self.default_import_directory)
        if not ok or imports == []:
            return
        known_file_type = False
        nameSplit = imports[0].split("/")
        temp_filename = nameSplit[-1]
        self.default_import_directory = imports[0][0:-len(temp_filename)]
        for f in imports:
            # Added process events, in case many large files are imported, which leaves the FileDialog open and covering the screen.
            QtWidgets.QApplication.processEvents()
            filename = f.split("/")[-1]
            destination = self.settings['path']
            if f.split('.')[-1].lower() in ('docx', 'odt', 'txt', 'htm', 'html', 'epub'):
                destination += "/documents/" + filename
                copyfile(f, destination)
                self.load_file_text(f)
                known_file_type = True
            if f.split('.')[-1].lower() in ('pdf'):
                destination += "/documents/" + filename
                # remove encryption from pdf if possible, for Linux
                if platform.system() == "Linux":
                    process = subprocess.Popen(["qpdf", "--decrypt", f, destination],
                        stdout=subprocess.PIPE)
                    process.wait()
                    self.load_file_text(destination)
                else:
                    #TODO qpdf decrypt not implemented for windows, OSX
                    QtWidgets.QMessageBox.warning(None, _('If import error occurs'),
                    _("Sometimes pdfs are encrypted, download and decrypt using qpdf before trying to load the pdf") + ":\n" + f)
                    copyfile(f, destination)
                    self.load_file_text(destination)
                known_file_type = True
            if f.split('.')[-1].lower() in ('jpg', 'jpeg', 'png'):
                destination += "/images/" + filename
                copyfile(f, destination)
                self.load_media_reference("/images/" + filename)
                known_file_type = True
            if f.split('.')[-1].lower() in ('wav', 'mp3'):
                destination += "/audio/" + filename
                copyfile(f, destination)
                self.load_media_reference("/audio/" + filename)
                known_file_type = True
            if f.split('.')[-1].lower() in ('mkv', 'mov', 'mp4', 'ogg', 'wmv'):
                destination += "/video/" + filename
                copyfile(f, destination)
                self.load_media_reference("/video/" + filename)
                known_file_type = True
            if not known_file_type:
                QtWidgets.QMessageBox.warning(None, _('Unknown file type'),
                    _("Unknown file type for import") + ":\n" + f)
        self.load_file_data()
        self.fill_table()

    def load_media_reference(self, mediapath):
        """ Load media reference information for audio video images. """

        # check for duplicated filename and update model, widget and database
        name_split = mediapath.split("/")
        filename = name_split[-1]
        if any(d['name'] == filename for d in self.source):
            QtWidgets.QMessageBox.warning(None, _('Duplicate file'), _("Duplicate filename.\nFile not imported"))
            return
        entry = {'name': filename, 'id': -1, 'fulltext': None, 'memo': "", 'mediapath': mediapath,
        'owner': self.settings['codername'], 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        cur = self.settings['conn'].cursor()
        cur.execute("insert into source(name,memo,owner,date, mediapath, fulltext) values(?,?,?,?,?,?)",
            (entry['name'], entry['memo'], entry['owner'], entry['date'], entry['mediapath'], entry['fulltext']))
        self.settings['conn'].commit()
        cur.execute("select last_insert_rowid()")
        id_ = cur.fetchone()[0]
        entry['id'] = id_
        self.parent_textEdit.append(entry['name'] + _(" imported."))
        self.source.append(entry)

        # Create an empty transcription file for audio and video
        if mediapath[:6] in("/audio", "/video"):
            entry = {'name': filename + ".transcribed", 'id': -1, 'fulltext': "", 'mediapath': None, 'memo': "",
            'owner': self.settings['codername'], 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            cur = self.settings['conn'].cursor()
            cur.execute("insert into source(name,fulltext,mediapath,memo,owner,date) values(?,?,?,?,?,?)",
                (entry['name'],  entry['fulltext'], entry['mediapath'], entry['memo'], entry['owner'], entry['date']))
            self.settings['conn'].commit()
            cur.execute("select last_insert_rowid()")
            id_ = cur.fetchone()[0]
            entry['id'] = id_
            self.parent_textEdit.append(entry['name'] + _(" imported."))
            self.source.append(entry)

    def load_file_text(self, import_file):
        """ Import from file types of odt, docx pdf, epub, txt, html, htm.
        """

        text = ""

        # Import from odt
        if import_file[-4:].lower() == ".odt":
            text = self.convert_odt_to_text(import_file)
        # Import from docx
        if import_file[-5:].lower() == ".docx":
            #text = convert(importFile)  # uses docx_to_html
            document = opendocx(import_file)
            list_ = getdocumenttext(document)
            text = "\n".join(list_)
        # Import from epub
        if import_file[-5:].lower() == ".epub":
            book = epub.read_epub(import_file)
            for d in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                #print(d.get_content())
                bytes_ = d.get_body_content()
                string = bytes_.decode('utf-8')
                text += html_to_text(string) + "\n"
        # import PDF
        if import_file[-4:].lower() == '.pdf':
            fp = open(import_file, 'rb')  # read binary mode
            parser = PDFParser(fp)
            doc = PDFDocument()
            parser.set_document(doc)
            doc.set_parser(parser)
            # potential error with encrypted PDF
            doc.initialize('')
            rsrcmgr = PDFResourceManager()
            laparams = LAParams()
            laparams.char_margin = 1.0
            laparams.word_margin = 1.0
            device = PDFPageAggregator(rsrcmgr, laparams=laparams)
            interpreter = PDFPageInterpreter(rsrcmgr, device)
            for page in doc.get_pages():
                interpreter.process_page(page)
                layout = device.get_result()
                for lt_obj in layout:
                    if isinstance(lt_obj, LTTextBox) or isinstance(lt_obj, LTTextLine):
                        text += lt_obj.get_text()
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
        if text == "":
            import_errors = 0
            try:
                with open(import_file, "r") as sourcefile:
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
                QtWidgets.QMessageBox.warning(None, _('Warning'),
                    _("Cannot import ") + str(import_file) + "\n" + str(e))
                return
            if import_errors > 0:
                QtWidgets.QMessageBox.warning(None, _('Warning'),
                    str(import_errors) + _(" lines not imported"))
                logger.warning(import_file + ": " + str(import_errors) + _(" lines not imported"))
        # import of text file did not work
        if text == "":
            QtWidgets.QMessageBox.warning(None, _('Warning'),
                _("Cannot import ") + str(import_file) + "\n" + str(e))
            return
        # Final checks: check for duplicated filename and update model, widget and database
        nameSplit = import_file.split("/")
        filename = nameSplit[-1]
        if any(d['name'] == filename for d in self.source):
            QtWidgets.QMessageBox.warning(None, _('Duplicate file'),
                _("Duplicate filename.\nFile not imported"))
            return
        entry = {'name': filename, 'id': -1, 'fulltext': text, 'mediapath': None, 'memo': "",
        'owner': self.settings['codername'], 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        cur = self.settings['conn'].cursor()
        #logger.debug("type fulltext: " + str(type(entry['fulltext'])))
        cur.execute("insert into source(name,fulltext,mediapath,memo,owner,date) values(?,?,?,?,?,?)",
            (entry['name'],  entry['fulltext'], entry['mediapath'], entry['memo'], entry['owner'], entry['date']))
        self.settings['conn'].commit()
        cur.execute("select last_insert_rowid()")
        id_ = cur.fetchone()[0]
        entry['id'] = id_
        self.parent_textEdit.append(entry['name'] + _(" imported."))
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

    '''def convert_odt_to_html(self, import_file):
        """ Convert odt to very rough equivalent with headings, list items and tables for
        html display in qTextEdits.
        NOT CURRENTLY USED. """

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
        data = data.replace('text:outline-level="1">', 'text:outline-level="1"><h1>')
        data = data.replace('text:outline-level="2">', 'text:outline-level="2"><h1>')
        data = data.replace('text:outline-level="3">', 'text:outline-level="3"><h1>')
        data = data.replace('</text:h>', '</h1>')
        data = data.replace('<text:list-item>', '<li>')
        data = data.replace('</text:list-item>', '</li>')
        data = data.replace('</text:span>', '')
        data = data.replace('<text:p', '<p><text:p')
        data = data.replace('</text:p>', '</p>')
        data = data.replace('<table:table table:name=', '<table><table:table table:name=')
        data = data.replace('</table:table>', '</table>')
        data = data.replace('<table:table-row', '<tr><table:table-row')
        data = data.replace('</table:table-row>', '</tr></table:table-row>')
        data = data.replace('<table:table-cell', '<td style="border:1px solid black"><table:table-cell')
        data = data.replace('</table:table-cell>', '</td>')
        text = ""
        tagged = False
        for i in range(0, len(data)):
            if data[i: i + 6] == "<text:" or data[i: i + 7] == "<table:":
                tagged = True
            if not tagged:
                text += data[i]
            if data[i] == ">":
                tagged = False
        return text'''

    def export(self):
        """ Export fulltext to a plain text file, filename will have .txt ending. """

        x = self.ui.tableWidget.currentRow()
        if self.source[x]['mediapath'] is not None:
            return
        filename = self.source[x]['name']
        if len(filename) > 5 and (filename[-5:] == ".html" or filename[-5:] == ".docx"):
            filename = filename[0:len(filename) - 5]
        if len(filename) > 4 and (filename[-4:] == ".htm" or filename[-4:] == ".odt" or filename[-4] == ".txt"):
            filename = filename[0:len(filename) - 4]
        filename += ".txt"
        options = QtWidgets.QFileDialog.DontResolveSymlinks | QtWidgets.QFileDialog.ShowDirsOnly
        directory = QtWidgets.QFileDialog.getExistingDirectory(None,
            _("Select directory to save file"), os.getenv('HOME'), options)
        if directory !="":
            filename = directory + "/" + filename
            #logger.info(_("Exporting to ") + filename)
            filedata = self.source[x]['fulltext']
            f = open(filename, 'w')
            f.write(filedata)
            f.close()
        QtWidgets.QMessageBox.information(None, _("File Exported"), str(filename))
        self.parent_textEdit.append(filename + _(" exported to ") + directory)

    def delete(self):
        """ Delete file from database and update model and widget.
        Also, delete files from sub-directories. """

        x = self.ui.tableWidget.currentRow()
        fileId = self.source[x]['id']
        ui = DialogConfirmDelete(self.source[x]['name'])
        ok = ui.exec_()

        if not ok:
            return
        cur = self.settings['conn'].cursor()
        # delete text source
        if self.source[x]['mediapath'] is None:
            cur.execute("delete from source where id = ?", [fileId])
            cur.execute("delete from code_text where fid = ?", [fileId])
            cur.execute("delete from annotation where fid = ?", [fileId])
            cur.execute("delete from case_text where fid = ?", [fileId])
            sql = "delete from attribute where attr_type in (select attribute_type.name from "
            sql += "attribute_type where id=? and attribute_type.caseOrFile='file')"
            cur.execute(sql, [fileId])
            self.settings['conn'].commit()
        # delete image source
        if self.source[x]['mediapath'] is not None:
            filepath = self.settings['path'] + self.source[x]['mediapath']
            try:
                os.remove(filepath)
            except Exception as e:
                logger.warning(_("Deleting image error: ") + str(e))
            cur.execute("delete from source where id = ?", [fileId])
            cur.execute("delete from code_image where id = ?", [fileId])
            sql = "delete from attribute where attr_type in (select attribute_type.name from "
            sql += "attribute_type where id=? and attribute_type.caseOrFile='file')"
            cur.execute(sql, [fileId])

        self.parent_textEdit.append(_("Deleted: ") + self.source[x]['name'])
        for item in self.source:
            if item['id'] == fileId:
                self.source.remove(item)
        self.fill_table()

    def fill_table(self):
        """ Fill the table widget with file data. """

        self.ui.tableWidget.setColumnCount(len(self.headerLabels))
        self.ui.tableWidget.setHorizontalHeaderLabels(self.headerLabels)
        self.ui.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        rows = self.ui.tableWidget.rowCount()
        for r in range(0, rows):
            self.ui.tableWidget.removeRow(0)

        for row, data in enumerate(self.source):
            self.ui.tableWidget.insertRow(row)
            name_item = QtWidgets.QTableWidgetItem(data['name'])
            #name_item.setFlags(name_item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.NAME_COLUMN, name_item)
            date_item = QtWidgets.QTableWidgetItem(data['date'])
            date_item.setFlags(date_item.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.DATE_COLUMN, date_item)
            memoitem = data['memo']
            if memoitem != None and memoitem != "":
                self.ui.tableWidget.setItem(row, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem("Yes"))
            fid = data['id']
            if fid is None:
                fid = ""
            iditem = QtWidgets.QTableWidgetItem(str(fid))
            iditem.setFlags(iditem.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.ID_COLUMN, iditem)
            # add the attribute values
            for a in self.attributes:
                for col, header in enumerate(self.headerLabels):
                    #print(fid, a[2], a[0], header)
                    #print(type(fid), type(a[2]), type(a[0]), type(header))
                    if fid == a[2] and a[0] == header:
                        #print("found", a)
                        self.ui.tableWidget.setItem(row, col, QtWidgets.QTableWidgetItem(str(a[1])))
        self.ui.tableWidget.resizeColumnsToContents()
        self.ui.tableWidget.resizeRowsToContents()
        self.ui.tableWidget.hideColumn(self.ID_COLUMN)
        if self.settings['showIDs']:
            self.ui.tableWidget.showColumn(self.ID_COLUMN)
        self.ui.tableWidget.verticalHeader().setVisible(False)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    ui = Ui_dialog_manage_files()
    ui.show()
    sys.exit(app.exec_())

