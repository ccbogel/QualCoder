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

import datetime
import ebooklib
from ebooklib import epub
import logging
import os
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams, LTTextBox, LTTextLine
from shutil import copyfile
import sys
import traceback
import zipfile

from PyQt6 import QtWidgets

from .docx import opendocx, getdocumenttext
from .helpers import Message
from .html_parser import *


path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class ReplaceTextFile:
    """  """

    app = None
    old_file = None
    annotations = []
    codings = []
    case_assign = []
    case_is_full_file = None
    new_file_path = None
    new_file = {}
    matching_filename = False

    def __init__(self, app, old_file, new_file_path):
        """ Update codings, annotations in new file
        param:
            app: App opject
            old_file: Dictionary of {name, id, fulltext}
            new_file: String filepath """

        self.app = app
        self.old_file = old_file
        self.new_file_path = new_file_path
        # Check for matching file name
        name_split = self.new_file_path.split("/")
        new_filename = name_split[-1]
        if self.old_file['name'] == new_filename:
            self.matching_filename = True
        filenames = self.app.get_filenames()
        for f in filenames:
            if f['name'] == new_filename and not self.matching_filename:
                msg = _(" New file name matches another existing file name")
                Message(self.app, _("Warning"), msg, "warning").exec()
                return
        self.get_codings_annotations_case()
        self.load_file_text()
        errs = self.update_annotation_positions()
        errs += self.update_code_positions()
        errs += self.update_case_positions()
        msg = _("Reload the other tabs.\nCheck accuracy of codings and annotations.\n")
        msg += _("Function works by identifying the first matching text segment for each coding and annotation.")
        msg += "\n" + errs
        Message(self.app, _("File replaced"), msg).exec()

    def update_case_positions(self):
        """ Update case if all file is assigned to case or portions assigned to case. """

        if len(self.case_assign) == 0:
            return ""
        # Entire file assigned to case
        if self.case_is_full_file is not None:
            cur = self.app.conn.cursor()
            cur.execute("update case_text set pos1=? where caseid=?", [len(self.new_file['fulltext']) - 1,
                                                                       self.case_is_full_file])
            self.app.conn.commit()
            return ""
        # Find matching text segments and assign to case
        to_delete = []
        err_msg = ""
        cur = self.app.conn.cursor()
        for c in self.case_assign:
            count = self.new_file['fulltext'].count(c['seltext'])
            if count == 0:
                to_delete.append(c['id'])
            if count > 1:
                err_msg += _("\nFound ") + str(count) + _(" of ") + c['seltext']
            pos = self.new_file['fulltext'].find(c['seltext'])
            c_len = c['pos1'] - c['pos0']
            if pos > -1:
                cur.execute("update case_text set pos0=?, pos1=? where id=?", [pos, pos + c_len, c['id']])
                self.app.conn.commit()
        for id_ in to_delete:
            cur.execute("delete from case_text where id=?", [id_])
            self.app.conn.commit()
        if err_msg != "":
            return "\n" + err_msg
        return err_msg

    def update_code_positions(self):
        """ Find matching text and update pos0 and pos1.
         codings are order from lowest to highest pos0 """

        to_delete = []
        err_msg = ""
        cur = self.app.conn.cursor()
        for c in self.codings:
            count = self.new_file['fulltext'].count(c['seltext'])
            if count == 0:
                to_delete.append(c['ctid'])
            if count > 1:
                err_msg += _("\nFound ") + str(count) + _(" of ") + c['seltext']
            pos = self.new_file['fulltext'].find(c['seltext'])
            c_len = c['pos1'] - c['pos0']
            if pos > -1:
                cur.execute("update code_text set pos0=?, pos1=? where ctid=?", [pos, pos + c_len, c['ctid']])
                self.app.conn.commit()
        for ctid in to_delete:
            cur.execute("delete from code_text where ctid=?", [ctid])
            self.app.conn.commit()
        if len(to_delete) > 0:
            err_msg += _("\nDeleted ") + str(len(to_delete)) + _(" unmatched codings")
        if err_msg != "":
            return err_msg
        return err_msg

    def update_annotation_positions(self):
        """ Find matching text and update pos0 and pos1.
        annotations are ordered from lowest to highest pos0"""

        to_delete = []
        err_msg = ""
        cur = self.app.conn.cursor()
        for an in self.annotations:
            count = self.new_file['fulltext'].count(an['seltext'])
            if count == 0:
                to_delete.append(an['anid'])
            if count > 1:
                err_msg += _("\nFound ") + str(count) + _(" of ") + an['seltext']
            pos = self.new_file['fulltext'].find(an['seltext'])
            a_len = an['pos1'] - an['pos0']
            if pos > -1:
                cur.execute("update annotation set pos0=?, pos1=? where anid=?", [pos, pos + a_len, an['anid']])
                self.app.conn.commit()
        for anid in to_delete:
            cur.execute("delete from annotation where anid=?", [anid])
            self.app.conn.commit()
        if len(to_delete) > 0:
            err_msg += _("\nDeleted ") + str(len(to_delete)) + _(" unmatched codings")
        if err_msg != "":
            return err_msg + "\n"
        return err_msg

    def get_codings_annotations_case(self):
        """ Get codings and annotations for old file. """

        cur = self.app.conn.cursor()
        cur.execute("select anid, pos0, pos1 from annotation where fid=? order by pos0",
                    [self.old_file['id'], ])
        a_result = cur.fetchall()
        self.annotations = []
        keys = 'anid', 'pos0', 'pos1'
        for row in a_result:
            self.annotations.append(dict(zip(keys, row)))
        for r in self.annotations:
            a_len = r['pos1'] - r['pos0']
            a_st = r['pos0'] + 1  # First str pos is 1 in sqlite
            cur.execute("select substr(fulltext,?,?) from source where id=?",
                        [a_st, a_len, self.old_file['id']])
            res = cur.fetchone()
            r['seltext'] = res[0]
        cur.execute("select ctid, pos0, pos1, seltext from code_text where fid=? order by pos0",
                    [self.old_file['id'], ])
        c_result = cur.fetchall()
        self.codings = []
        keys = 'ctid', 'pos0', 'pos1', 'seltext'
        for row in c_result:
            self.codings.append(dict(zip(keys, row)))
        cur.execute("select id, caseid,pos0,pos1 from case_text where fid=?", [self.old_file['id']])
        case_result = cur.fetchall()
        self.case_assign = []
        keys = 'id', 'caseid', 'pos0', 'pos1'
        for r in case_result:
            self.case_assign.append(dict(zip(keys, r)))
        for r in self.case_assign:
            ca_len = r['pos1'] - r['pos0']
            ca_st = r['pos0'] + 1  # First str pos is 1 in sqlite
            cur.execute("select substr(fulltext,?,?) from source where id=?",
                        [ca_st, ca_len, self.old_file['id']])
            res1 = cur.fetchone()
            r['seltext'] = res1[0]
        self.case_is_full_file = None
        if len(self.case_assign) == 1 and self.case_assign[0]['pos0'] == 0 and \
                self.case_assign[0]['pos1'] == len(self.old_file['fulltext']) - 1:
            self.case_is_full_file = self.case_assign[0]['caseid']

    # Copied from manage_files.DialogManageFiles

    def load_file_text(self):
        """ Import from file types of odt, docx pdf, epub, txt, html, htm.
        Implement character detection for txt imports.
        Do not link the new text, load it instead.
        Delete old project folder file, insert new file int project folder.
        Update database entry and keep same id.

        param:
            import_file: filepath of file to be imported, String
            link_path:  filepath of file to be linked, String
        """

        text = ""
        # Import from odt
        if self.new_file_path[-4:].lower() == ".odt":
            text = self.convert_odt_to_text(self.new_file_path)
            text = text.replace("\n", "\n\n")  # add line to paragraph spacing for visual format
        # Import from docx
        if self.new_file_path[-5:].lower() == ".docx":
            document = opendocx(self.new_file_path)
            list_ = getdocumenttext(document)
            text = "\n\n".join(list_)  # add line to paragraph spacing for visual format
        # Import from epub
        if self.new_file_path[-5:].lower() == ".epub":
            book = epub.read_epub(self.new_file_path)
            for d in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                try:
                    bytes_ = d.get_body_content()
                    string = bytes_.decode('utf-8')
                    text += html_to_text(string) + "\n\n"  # add line to paragraph spacing for visual format
                except TypeError as e:
                    logger.debug("ebooklib get_body_content error " + str(e))
        # Import PDF
        if self.new_file_path[-4:].lower() == '.pdf':
            fp = open(self.new_file_path, 'rb')  # read binary mode
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
                        text += lt_obj.get_text() + "\n"  # add line to paragraph spacing for visual format
            # Remove excess line endings, include those with one blank space on a line
            text = text.replace('\n \n', '\n')
            text = text.replace('\n\n\n', '\n\n')
        # Import from html
        if self.new_file_path[-5:].lower() == ".html" or self.new_file_path[-4:].lower() == ".htm":
            with open(self.new_file_path, "r") as sourcefile:
                file_text = ""
                while 1:
                    line_ = sourcefile.readline()
                    if not line_:
                        break
                    file_text += line_
                text = html_to_text(file_text)
        # Try importing as a plain text file.
        if text == "":
            import_errors = 0
            try:
                # Can get UnicodeDecode Error on Windows so using error handler
                with open(self.new_file_path, "r", encoding="utf-8", errors="backslashreplace") as sourcefile:
                    while 1:
                        line = sourcefile.readline()
                        if not line:
                            break
                        try:
                            text += line
                        except Exception as err:
                            import_errors += 1
                            print(err)
                    # Associated with notepad files
                    if text[0:6] == "\ufeff":
                        text = text[6:]
            except Exception as e:
                msg = _("Cannot import") + str(self.new_file_path) + "\n" + str(e)
                Message(self.app, _("Warning"), msg, "warning").exec()
                return
            if import_errors > 0:
                Message(self.app, _("Warning"), str(import_errors) + _(" lines not imported"), "warning").exec()
                logger.warning(self.new_file_path + ": " + str(import_errors) + _(" lines not imported"))
        # Import of text file did not work
        if text == "":
            msg = str(self.new_file_path) + _("\nPlease check if the file is empty.")
            Message(self.app, _("Warning"), _("Cannot import ") + msg, "warning").exec()
            return

        name_split = self.new_file_path.split("/")
        filename = name_split[-1]

        cur = self.app.conn.cursor()
        # Remove old file from project folder
        cur.execute("select mediapath from source where id=?", [self.old_file['id']])
        res = cur.fetchone()
        if res[0] is None:  # Internal file
            old_filepath = self.app.project_path + "/documents/" + self.old_file['name']
            try:
                os.remove(old_filepath)
            except FileNotFoundError as e:
                logger.warning(_("Deleting file error: ") + str(e))
        # Insert new file into project folder
        copyfile(self.new_file_path, self.app.project_path + "/documents/" + filename)
        # Update old file entry to new file
        mediapath = None
        '''if link_path != "":
            mediapath = link_path'''
        self.new_file = {'name': filename, 'id': self.old_file['id'], 'fulltext': text, 'mediapath': mediapath,
            'memo': self.old_file['memo'], 'owner': self.app.settings['codername'],
            'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        cur.execute("update source set name=?,fulltext=?,mediapath=?,owner=?,date=? where id=?",
            (self.new_file['name'],  self.new_file['fulltext'], self.new_file['mediapath'],
             self.new_file['owner'], self.new_file['date'],
             self.old_file['id']))
        self.app.conn.commit()
        # Update vectorstore
        if self.app.settings['ai_enable'] == 'True':
            self.app.ai.sources_vectorstore.import_document(self.old_file['id'], self.new_file['name'], self.new_file['fulltext'], update=True)  

    @staticmethod
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
