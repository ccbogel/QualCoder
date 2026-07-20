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
https://qualcoder-org.github.io
https://qualcoder.org/
"""

from charset_normalizer import from_bytes
import datetime
import ebooklib
from ebooklib import epub
import json
from pathlib import Path
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfinterp import PDFResourceManager, PDFPageInterpreter
from pdfminer.converter import PDFPageAggregator
from pdfminer.layout import LAParams, LTTextLine
from PyQt6 import QtCore
from shutil import copyfile
from striprtf.striprtf import rtf_to_text
from typing import Any, Iterable
import zipfile

from .docx import opendocx, getdocumenttext
from .helpers import Message
from .html_parser import *


path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class ReplaceTextFile:
    """ Replace an older text file with a new text file.
     Attempt to adjust case, annotation and code segment positions. """

    def __init__(self, app, old_file:dict[str,Any], new_file_path:str):
        """ Update codings, annotations in new file
        Args:
            app: App object
            old_file: Dictionary of {name, id, fulltext}
            new_file_path: String filepath """

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
        self.annotations = []
        self.codings = []
        self.get_codings_annotations_case()
        self.case_assign = []
        self.case_is_full_file = None
        self.new_file = {}
        self.matching_filename = False
        self.pdf_page_text = ""  # Used when loading pdf text
        self.load_file_text()
        errs = self.update_annotation_positions()
        errs += self.update_code_positions()
        errs += self.update_case_positions()
        msg = _("Reload the other tabs.\nCheck accuracy of codings and annotations.\n")
        msg += _("Function works by identifying the first matching text segment for each coding and annotation.")
        msg += f"\n{errs}"
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
            return f"\n{err_msg}"
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
            return f"{err_msg}\n"
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

    def load_file_text(self):
        """ Import from file types of odt, docx, rtf, pdf, epub, txt, html, htm, md.
        Implement character detection for txt imports.
        Do not link the new text, load it instead.
        Delete old project folder file, insert new file int project folder.
        Update database entry and keep same id.

        import_file: filepath of file to be imported, String
        link_path:  filepath of file to be linked, String
        """

        text = ""
        # Import from odt
        if Path(self.new_file_path).suffix.lower() == ".odt":
            text = self.convert_odt_to_text(self.new_file_path)
            text = text.replace("\n", "\n\n")  # Add line to paragraph spacing for visual format
        # Import from docx
        if Path(self.new_file_path).suffix.lower() == ".docx":
            document = opendocx(self.new_file_path)
            list_ = getdocumenttext(document)
            text = "\n\n".join(list_)  # Add line to paragraph spacing for visual format
        # Import from rtf
        if Path(self.new_file_path).suffix.lower() == ".rtf":
            # text_ = rtf_to_text(import_file, encoding="latin-1", errors="replace")
            with open(self.new_file_path, "r", encoding="latin-1") as sourcefile:
                text = ""
                try:
                    rtf = sourcefile.read()
                    text = rtf_to_text(rtf)
                except Exception as err:
                    msg = "Importing rtf. Expecting characters encoded as latin-1. Import failed."
                    logger.debug(f"rtf_to_text error Not Latin-1: {err}")
                    Message(self.app, "rtf to text error", msg).exec()
        # Import from epub
        if Path(self.new_file_path).suffix.lower() == ".epub":
            book = epub.read_epub(self.new_file_path)
            for d in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
                try:
                    bytes_ = d.get_body_content()
                    string = bytes_.decode('utf-8')
                    text += html_to_text(string) + "\n\n"  # add line to paragraph spacing for visual format
                except TypeError as e:
                    logger.debug("ebooklib get_body_content error " + str(e))
        # Import from html
        if Path(self.new_file_path).suffix.lower() in (".html", ".htm"):
            import_errors = 0
            with open(self.new_file_path, "r", encoding="utf-8", errors="surrogateescape") as sourcefile:
                html_text = ""
                while 1:
                    line = sourcefile.readline()
                    if not line:
                        break
                    html_text += line
                text = html_to_text(html_text)
                if import_errors > 0:
                    Message(self.app, _("Warning"), str(import_errors) + _(" lines not imported"), "warning").exec()
        # Import PDF
        if Path(self.new_file_path).suffix.lower() == '.pdf':
            pdf_file = open(self.new_file_path, 'rb')
            resource_manager = PDFResourceManager()
            laparams = LAParams()
            device = PDFPageAggregator(resource_manager, laparams=laparams)
            interpreter = PDFPageInterpreter(resource_manager, device)
            pages_generator = PDFPage.get_pages(pdf_file)  # Generator PDFpage objects
            text = ""
            # Can be very slow with large PDFs and older computers
            for i, page in enumerate(pages_generator):
                QtCore.QCoreApplication.processEvents()  # Trial this to see if it prevents 'App not responding'
                self.pdf_page_text = ""
                interpreter.process_page(page)
                layout = device.get_result()
                for lobj in layout:
                    self.get_item_and_hierarchy(page, lobj)
                text += self.pdf_page_text
        # Try importing as a plain text file.
        if text == "":
            try:
                text_, detected_encoding = self.decode_text_with_best_encoding(self.new_file_path)
                logger.debug(f"Importing plain text file: {self.new_file_path} decoded as {detected_encoding}")
                if text_ and text_[0] == "\ufeff":  # associated with notepad files
                    text = text_[1:]
            except Exception as err:
                logger.warning(str(err))
                Message(self.app, _("Warning"), _("Cannot import") + f"{self.new_file_path}\n{err}",
                        "warning").exec()
                return
        # Import of text file did not work
        if text == "":
            msg = str(self.new_file_path) + _("\nPlease check if the file is empty.")
            Message(self.app, _("Warning"), _("Cannot import ") + msg, "warning").exec()
            return
        # Normalise line endings and strip BOM so the stored fulltext matches
        # exactly what QPlainTextEdit will display. Qt converts \r\n and lone \r
        # into \n on setPlainText(), and a leftover BOM adds a char; either makes
        # stored positions drift past the editor length (setPosition out of range,
        # frozen highlight on resize).
        if Path(self.new_file_path).suffix.lower() != '.pdf':  # skip PDF
            text = text.replace("\r\n", "\n").replace("\r", "\n")
            if text and text[0] == "\ufeff":
                text = text[1:]
        # Final checks: check for duplicated filename and update model, widget and database
        name_split = self.new_file_path.split("/")
        filename = name_split[-1]

        # Apply pseudonym text replacement
        pseudonyms = self.load_pseudonyms()
        if Path(self.new_file_path).suffix.lower() != '.pdf':
            for pseudonym in pseudonyms:
                pseudonymised = re.sub(rf"\b{pseudonym['original']}\b", pseudonym['pseudonym'], text)
                text = pseudonymised

        cur = self.app.conn.cursor()
        # Remove old file from project folder
        cur.execute("select mediapath from source where id=?", [self.old_file['id']])
        res = cur.fetchone()
        if res[0] is None:  # Internal file
            old_filepath = f"{self.app.project_path}/documents/{self.old_file['name']}"
            try:
                os.remove(old_filepath)
            except FileNotFoundError as e:
                logger.warning(_("Deleting file error: ") + str(e))
        # Insert new file into project folder
        copyfile(self.new_file_path, f"{self.app.project_path}/documents/{filename}")
        # Update old file entry to new file
        mediapath = None
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
            self.app.ai.sources_vectorstore.import_document(self.old_file['id'], self.new_file['name'], self.new_file['fulltext'])

    def get_item_and_hierarchy(self, page, lobj: Any):
        """ Get text item details add to page_dict, with descendants.
        Use LTextLine as this object can be parsed in Code_pdf for font size and colour.
        """

        if isinstance(lobj, LTTextLine):  # Do not use LTTextBox
            obj_text = lobj.get_text()
            # Fix Pdfminer recognising invalid unicode characters.
            obj_text = obj_text.replace(u"\uE002", "Th")
            obj_text = obj_text.replace(u"\uFB01", "fi")
            self.pdf_page_text += obj_text
        if isinstance(lobj, Iterable):
            for obj in lobj:
                self.get_item_and_hierarchy(page, obj)

    def load_pseudonyms(self):
        """ Pseudonyms stored in pseudonyms.json in qda data folder.
        Loads into list of dictionaries of 'original', ;pseudonym' keys.
        """

        pseudonyms = []
        pseudonyms_filepath = os.path.join(self.app.project_path, "pseudonyms.json")
        try:
            with open(pseudonyms_filepath, "r") as f:
                pseudonyms = json.load(f)
        except FileNotFoundError:
            pass
        return pseudonyms

    @staticmethod
    def decode_text_with_best_encoding(import_file:str):
        """ Decode text file bytes using robust encoding detection and fallbacks. """

        with open(import_file, "rb") as sourcefile:
            raw_bytes = sourcefile.read()
        if not raw_bytes:
            return "", "empty"
        # Try Unicode first, with and without BOM
        decode_order = ("utf-8-sig", "utf-8")
        for encoding in decode_order:
            try:
                return raw_bytes.decode(encoding), encoding
            except UnicodeDecodeError:
                pass
        # no Unicode, try to detect charset with charset-normalizer, then fall back to common encodings
        best_match = from_bytes(raw_bytes).best()
        if best_match is not None:
            detected_encoding = best_match.encoding if best_match.encoding else "unknown"
            return str(best_match), detected_encoding
        for encoding in ("cp1252", "latin-1"):
            try:
                return raw_bytes.decode(encoding), encoding
            except UnicodeDecodeError:
                pass
        return raw_bytes.decode("utf-8", errors="backslashreplace"), "utf-8(backslashreplace)"

    @staticmethod
    def convert_odt_to_text(import_file:str) -> str:
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
