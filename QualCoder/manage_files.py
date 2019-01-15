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
https://pypi.org/project/QualCoder

pip install PyPDF2
'''

from PyQt5 import QtCore, QtGui, QtWidgets
from memo import DialogMemo
from confirm_delete import DialogConfirmDelete
from GUI.ui_dialog_manage_files import Ui_Dialog_manage_files
from add_item_name import DialogAddItemName
from GUI.ui_dialog_attribute_type import Ui_Dialog_attribute_type
from GUI.ui_dialog_memo import Ui_Dialog_memo  # for manually creating a new file
from view_image import DialogViewImage
import datetime
import os
from shutil import copyfile
import logging

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

# for file extraction
from docx import opendocx, getdocumenttext
import zipfile
from html_parser import *

try:
    import PyPDF2  # use this module only if it is installed
except:
    logger.debug("For importing PDF text, PyPDF2 not installled. From command line, try either: \
    pip install PyPDF2 or if this still fails \
    pip3 install PyPDF2\n On Linux add sudo to the start of the command \
    e.g. sudo pip3 install PyPDF2")


class DialogManageFiles(QtWidgets.QDialog):
    ''' View, import, export, rename and delete text files.  '''

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

    def __init__(self, settings, parent_textEdit):

        self.settings = settings
        self.parent_textEdit = parent_textEdit
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
        ''' Documents images and audio contain the filetype suffix.
        No suffix imples the 'file' was imported from a survey question.
        This also fills out the table header lables with file attribute names.
         '''

        self.source = []
        cur = self.settings['conn'].cursor()
        cur.execute("select name, id, fulltext, imagepath, memo, owner, date from source order by name")
        result = cur.fetchall()
        for row in result:
            self.source.append({'name': row[0], 'id': row[1], 'fulltext': row[2],
            'imagepath': row[3], 'memo': row[4], 'owner': row[5], 'date': row[6]})
        # attributes
        self.headerLabels = ["Name", "Memo", "Date", "Id"]
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
        print

    def add_attribute(self):
        ''' When add button pressed, opens the addItem dialog to get new attribute text.
        Then get the attribute type through a dialog.
        AddItem dialog checks for duplicate attribute name.
        New attribute is added to the model and database '''

        check_names = self.attribute_names + [{'name': 'name'}, {'name':'memo'}, {'name':'id'}, {'name':'date'}]
        ui = DialogAddItemName(check_names, "New attribute name")
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
        self.parent_textEdit.append("Attribute added to files: " + name + ", type: " + valuetype)

    def cell_selected(self):
        ''' When the table widget memo cell is selected display the memo.
        Update memo text, or delete memo by clearing text.
        If a new memo also show in table widget by displaying YES in the memo column '''

        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()

        if y == self.MEMO_COLUMN:
            name =self.source[x]['name'].lower()
            if name[-5:] == ".jpeg" or name[-4:] in ('.jpg', '.png', '.gif'):
                ui = DialogMemo(self.settings, "Memo for file " + self.source[x]['name'],
                self.source[x]['memo'])
                ui.exec_()
                self.source[x]['memo'] = ui.memo
                cur = self.settings['conn'].cursor()
                cur.execute('update source set memo=? where id=?', (ui.memo, self.source[x]['id']))
                self.settings['conn'].commit()
            else:
                ui = DialogMemo(self.settings, "Memo for file " + self.source[x]['name'],
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
        ''' If the filename has been changed in the table widget update the database '''

        x = self.ui.tableWidget.currentRow()
        y = self.ui.tableWidget.currentColumn()
        if y == self.NAME_COLUMN:
            newText = str(self.ui.tableWidget.item(x, y).text()).strip()

            # check that no other source file has this text and this is is not empty
            update = True
            if newText == "":
                update = False
            for c in self.source:
                if c['name'] == newText:
                    update = False
            if update:
                # update source list and database
                self.source[x]['name'] = newText
                cur = self.settings['conn'].cursor()
                cur.execute("update source set name=? where id=?", (newText, self.source[x]['id']))
                self.settings['conn'].commit()
            else:  # put the original text in the cell
                self.ui.tableWidget.item(x, y).setText(self.source[x]['name'])
        if y > self.ID_COLUMN:  # update attribute value
            value = str(self.ui.tableWidget.item(x, y).text()).strip()
            attribute_name = self.headerLabels[y]
            cur = self.settings['conn'].cursor()
            cur.execute("update attribute set value=? where id=? and name=? and attr_type='file'",
            (value, self.source[x]['id'], attribute_name))
            self.settings['conn'].commit()
            logger.debug("updating: " + attribute_name + " , " + value)
            self.ui.tableWidget.resizeColumnsToContents()

    def view(self):
        ''' View and edit text file contents.
        Alternatively view an image '''

        x = self.ui.tableWidget.currentRow()
        if self.source[x]['imagepath'] is not None:
            self.view_image(x)
            return

        Dialog = QtWidgets.QDialog()
        ui = Ui_Dialog_memo()
        ui.setupUi(Dialog)
        ui.textEdit.setFontPointSize(self.settings['fontsize'])
        ui.textEdit.setPlainText(self.source[x]['fulltext'])
        Dialog.setWindowTitle("View file: " + self.source[x]['name'] + " (ID:" + str(self.source[x]['id']) + ") ")
        Dialog.exec_()
        text = ui.textEdit.toPlainText()
        if text == self.source[x]['fulltext']:
            return
        cur = self.settings['conn'].cursor()
        # cannot edit file text of there are linked cases, codes or annotations
        sql = "select * from case_text where fid=?"
        cur.execute(sql, [self.source[x]['id'], ])
        c_linked = cur.fetchall()
        sql = "select * from annotation where id=?"
        cur.execute(sql, [self.source[x]['id'], ])
        a_linked = cur.fetchall()
        sql = "select * from code_text where fid=?"
        cur.execute(sql, [self.source[x]['id'], ])
        c_linked = cur.fetchall()
        if c_linked != [] or a_linked != [] or c_linked != []:
            msg = "Cannot edit file text, there  are codes, cases or annotations linked to this file"
            QtWidgets.QMessageBox.warning(None, 'Warning', msg, QtWidgets.QMessageBox.Ok)
            return
        self.source[x]['fulltext'] = text
        cur.execute("update source set fulltext=? where id=?", (text, self.source[x]['id']))
        self.settings['conn'].commit()

    def view_image(self, x):
        ''' View an image file and edit the image memo. '''

        ui = DialogViewImage(self.settings, self.source[x])
        ui.exec_()
        self.source[x]['memo'] = ui.ui.textEdit.toPlainText()
        cur = self.settings['conn'].cursor()
        cur.execute('update source set memo=? where id=?', (self.source[x]['memo'], self.source[x]['id']))
        self.settings['conn'].commit()
        if self.source[x]['memo'] == "":
            self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem())
        else:
            self.ui.tableWidget.setItem(x, self.MEMO_COLUMN, QtWidgets.QTableWidgetItem("Yes"))

    def create(self):
        ''' Create a new text file by entering text into the dialog.
        Implements the QtDesigner memo dialog '''

        name, ok = QtWidgets.QInputDialog.getText(self, 'New File', 'Enter the file name:')
        if not ok:
            return
        if name is None or name == "":
            QtWidgets.QMessageBox.warning(None, 'Warning',"No filename was selected", QtWidgets.QMessageBox.Ok)
            return
        # check for non-unique filename
        if any(d['name'] == name for d in self.source):
            QtWidgets.QMessageBox.warning(None, 'Warning',"Filename in use", QtWidgets.QMessageBox.Ok)
            return

        ui = DialogMemo(self.settings, "Creating a new file: " + name)
        ui.exec_()
        filetext = ui.memo
        # update database
        entry = {'name': name, 'id': -1, 'fulltext': filetext, 'memo': "",
        'owner': self.settings['codername'], 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'imagepath': None}
        cur = self.settings['conn'].cursor()
        cur.execute("insert into source(name,fulltext,imagepath,memo,owner,date) values(?,?,?,?,?,?)",
            (entry['name'], entry['fulltext'], entry['imagepath'], entry['memo'], entry['owner'], entry['date']))
        self.settings['conn'].commit()
        self.parent_textEdit.append("File created: " + entry['name'])
        self.source.append(entry)
        self.fill_table()

    def import_files(self):
        ''' Import files and store into relevant directories (documents, images, ?audio?).
        Convert documents to plain text and store this in data.qda
        Can import from plain text files, also import from html, odt and docx
        Note importing from html, odt and docx all formatting is lost.
        Also 'imports' images as jpg, jpeg, png, gif which are stored in an images directory '''

        imports, ok = QtWidgets.QFileDialog.getOpenFileNames(None, 'Open file', self.default_import_directory)
        if not ok or imports == []:
            return
        nameSplit = imports[0].split("/")
        temp_filename = nameSplit[-1]
        self.default_import_directory = imports[0][0:-len(temp_filename)]
        for f in imports:
            filename = f.split("/")[-1]
            destination = self.settings['path']
            if f.split('.')[-1].lower() in ('docx', 'odt', 'txt', 'pdf', 'htm', 'html'):
                destination += "/documents/" + filename
                copyfile(f, destination)
                self.load_file_text(f)
            if f.split('.')[-1].lower() in ('jpg', 'jpeg', 'png', 'gif'):
                destination += "/images/" + filename
                copyfile(f, destination)
                self.load_image_reference(f)
            #TODO audio
            '''if f.split('.')[-1].lower() in ('wav', 'mp3'):
                destination += "/audio/" + filename
                copyfile(f, destination)'''
        self.fill_table()

    def load_image_reference(self, import_file):
        ''' Load image reference data. '''

        # check for duplicated filename and update model, widget and database
        name_split = import_file.split("/")
        filename = name_split[-1]
        if any(d['name'] == filename for d in self.source):
            QtWidgets.QMessageBox.warning(None, 'Duplicate file', "Duplicate filename.\nFile not imported")
            return
        entry = {'name': filename, 'id': -1, 'fulltext': None, 'memo': "", 'imagepath': filename,
        'owner': self.settings['codername'], 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        cur = self.settings['conn'].cursor()
        cur.execute("insert into source(name,memo,owner,date, imagepath, fulltext) values(?,?,?,?,?,?)",
            (entry['name'], entry['memo'], entry['owner'], entry['date'], entry['imagepath'], entry['fulltext']))
        self.settings['conn'].commit()
        cur.execute("select last_insert_rowid()")
        id_ = cur.fetchone()[0]
        entry['id'] = id_
        self.parent_textEdit.append(entry['name'] + " imported.")

        # clear and refill table widget
        for r in self.source:
            self.ui.tableWidget.removeRow(0)
        self.source.append(entry)
        self.fill_table()

    def load_file_text(self, import_file):
        ''' Import individual file types of .odt, .docx .txt, PDF, .html, .htm'''

        text = ""

        # Import from odt
        if import_file[-4:].lower() == ".odt":
            text = self.convert_odt_to_text(import_file)
        # Import from docx
        if import_file[-5:].lower() == ".docx":
            #text = convert(importFile)  # uses docx_to_html
            document = opendocx(import_file)
            list_ = getdocumenttext(document)
            text = " ".join(list_)
        # import PDF
        if import_file[-4:].lower() == ".pdf":
            try:
                content = ""
                pdf_obj = open(import_file,'rb')  # read binary mode
                pdfReader = PyPDF2.PdfFileReader(pdf_obj)
                pages = pdfReader.numPages
                for p in range(0, pages):
                    page_obj = pdfReader.getPage(p)
                    page_obj.extractText()
                    content += page_obj.extractText() + "\n"
                text = content
            except Exception as e:
                QtWidgets.QMessageBox.warning(None, "Problem importing PDF",
                str(e) + "\nPyPDF2 module may not be installed.")
                logger.warning("Importing PDF: PyPDF2 not installled. In Terminal try: sudo pip3 install PyPDF2")
                return
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
                QtWidgets.QMessageBox.warning(None, 'Warning', str(importErrors) + " lines not imported")
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
                QtWidgets.QMessageBox.warning(None, 'Warning', "Cannot import " + str(import_file) + "\n" + str(e))
                return
            if import_errors > 0:
                QtWidgets.QMessageBox.warning(None, 'Warning', str(import_errors) + " lines not imported")
                logger.warning(import_file + ": " + str(import_errors) + " lines not imported")
        # Final checks: check for duplicated filename and update model, widget and database
        nameSplit = import_file.split("/")
        filename = nameSplit[-1]
        if any(d['name'] == filename for d in self.source):
            QtWidgets.QMessageBox.warning(None, 'Duplicate file', "Duplicate filename.\nFile not imported")
            return
        entry = {'name': filename, 'id': -1, 'fulltext': text, 'imagepath': None, 'memo': "",
        'owner': self.settings['codername'], 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        cur = self.settings['conn'].cursor()
        #logger.debug("type fulltext: " + str(type(entry['fulltext'])))
        cur.execute("insert into source(name,fulltext,imagepath,memo,owner,date) values(?,?,?,?,?,?)",
            (entry['name'],  entry['fulltext'], entry['imagepath'], entry['memo'], entry['owner'], entry['date']))
        self.settings['conn'].commit()
        cur.execute("select last_insert_rowid()")
        id_ = cur.fetchone()[0]
        entry['id'] = id_
        self.parent_textEdit.append(entry['name'] + " imported.")
        self.source.append(entry)

    def convert_odt_to_text(self, import_file):
        ''' convert odt to very rough equivalent with headings, list items and tables for
        html display in qTextEdits '''

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

    def convert_odt_to_html(self, import_file):
        ''' convert odt to very rough equivalent with headings, list items and tables for
        html display in qTextEdits.
        Not currently used '''

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
        return text

    def export(self):
        ''' Export fulltext to a plain text file, filename will have .txt ending '''

        x = self.ui.tableWidget.currentRow()
        if self.source[x]['imagepath'] is not None:
            return
        filename = self.source[x]['name']
        if len(filename) > 5 and (filename[-5:] == ".html" or filename[-5:] == ".docx"):
            filename = filename[0:len(filename) - 5]
        if len(filename) > 4 and (filename[-4:] == ".htm" or filename[-4:] == ".odt" or filename[-4] == ".txt"):
            filename = filename[0:len(filename) - 4]
        filename += ".txt"
        options = QtWidgets.QFileDialog.DontResolveSymlinks | QtWidgets.QFileDialog.ShowDirsOnly
        directory = QtWidgets.QFileDialog.getExistingDirectory(None, "Select directory to save file", os.getenv('HOME'), options)
        if directory !="":
            filename = directory + "/" + filename
            logger.info("Exporting:  to " + filename)
            filedata = self.source[x]['fulltext']
            f = open(filename, 'w')
            f.write(filedata)
            f.close()
        QtWidgets.QMessageBox.information(None, "File Export", str(filename) + " exported")
        self.parent_textEdit.append(filename + " exported to " + directory)

    def delete(self):
        ''' Delete file from database and update model and widget.
        Also, delete files from /images directory '''

        x = self.ui.tableWidget.currentRow()
        fileId = self.source[x]['id']
        ui = DialogConfirmDelete(self.source[x]['name'])
        ok = ui.exec_()

        if not ok:
            return
        cur = self.settings['conn'].cursor()
        # delete text source
        if self.source[x]['imagepath'] is None:
            cur.execute("delete from source where id = ?", [fileId])
            cur.execute("delete from code_text where fid = ?", [fileId])
            cur.execute("delete from annotation where fid = ?", [fileId])
            cur.execute("delete from case_text where fid = ?", [fileId])
            sql = "delete from attribute where attr_type in (select attribute_type.name from attribute_type where id=? and attribute_type.caseOrFile='file')"
            cur.execute(sql, [fileId])
            self.settings['conn'].commit()
        # delete image source
        if self.source[x]['imagepath'] is not None:
            filepath = self.settings['path'] + "/images/" + self.source[x]['name']
            try:
                os.remove(filepath)
            except Exception as e:
                logger.warning("Deleting image error: " + str(e))
            cur.execute("delete from source where id = ?", [fileId])
            cur.execute("delete from code_image where id = ?", [fileId])
            sql = "delete from attribute where attr_type in (select attribute_type.name from attribute_type where id=? and attribute_type.caseOrFile='file')"
            cur.execute(sql, [fileId])

        self.parent_textEdit.append("Deleted source: " + self.source[x]['name'])
        for item in self.source:
            if item['id'] == fileId:
                self.source.remove(item)
        self.fill_table()

    def fill_table(self):
        ''' Fill the table widget with file data. '''

        self.ui.tableWidget.setColumnCount(len(self.headerLabels))
        self.ui.tableWidget.setHorizontalHeaderLabels(self.headerLabels)
        self.ui.tableWidget.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)

        rows = self.ui.tableWidget.rowCount()
        for r in range(0, rows):
            self.ui.tableWidget.removeRow(0)

        for row, data in enumerate(self.source):
            self.ui.tableWidget.insertRow(row)
            self.ui.tableWidget.setItem(row, self.NAME_COLUMN, QtWidgets.QTableWidgetItem(data['name']))
            dateitem = QtWidgets.QTableWidgetItem(data['date'])
            dateitem.setFlags(dateitem.flags() ^ QtCore.Qt.ItemIsEditable)
            self.ui.tableWidget.setItem(row, self.DATE_COLUMN, dateitem)
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
                        #TODO id in image and file matches - get overlap
                        self.ui.tableWidget.setItem(row, col, QtWidgets.QTableWidgetItem(str(a[1])))
        self.ui.tableWidget.resizeColumnsToContents()
        self.ui.tableWidget.resizeRowsToContents()
        self.ui.tableWidget.hideColumn(self.ID_COLUMN)
        if self.settings['showIDs']:
            self.ui.tableWidget.showColumn(self.ID_COLUMN)
        self.ui.tableWidget.verticalHeader().setVisible(False)


if __name__ == "__main__":
    import sys
    app = QtWidgets.QApplication(sys.argv)
    ui = Ui_dialog_manage_files()
    ui.show()
    sys.exit(app.exec_())

