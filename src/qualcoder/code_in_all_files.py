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

import datetime
import fitz
import logging
import os
import sqlite3

from PyQt6 import QtCore, QtGui, QtWidgets

from .color_selector import TextColor
from .helpers import msecs_to_mins_and_secs, DialogCodeInAV, DialogCodeInImage, DialogCodeInText, \
    ExportDirectoryPathDialog, Message
from .memo import DialogMemo
from .select_items import DialogSelectItems

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogCodeInAllFiles(QtWidgets.QDialog):
    """ Display all coded media for this code, in a modal dialog.
    Coded media comes from ALL files for this coder.
    Need to store textedit start and end positions so that code in context can be used.
    Called from:
        DialogCodeText, DialogCodeImage, DialogCodePdf
        DialogCodeAV, DialogReportCodeFrequencies,
        DialogReportCoderComparisons, DialogReportCodeSummary,
        DialogReportExactTextMatches, DialogCodesBySegments
    """

    def __init__(self, app, codes_list, case_or_file:str = "File", category_name:str = ""):
        """ Create dialog with textEdit widget to show all codings of this code.
        Called: code_text.coded_media_dialog , code_av.coded_media_dialog , code_image.coded_media_dialog
        param:
            app : class containing app details such as database connection
            codes_list : dictionary of this one code {name, color, cid, catid, date, owner, memo}, OR
                list of dictionaries of {name,color, cid, catid,date,owner,memo}
            case_or_file: default to "File", but view_graph has a "Case" option
            category_name: String
        """

        self.app = app
        self.codes_list = []
        if isinstance(codes_list, list):
            self.codes_list = codes_list
        if isinstance(codes_list, dict):
            self.codes_list = [codes_list]
        self.case_or_file = case_or_file
        self.category_name = category_name
        QtWidgets.QDialog.__init__(self)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.resize(620, 580)
        # Enable custom window hint to enable customizing window controls
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowType.CustomizeWindowHint)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        title = _("Coded files ")
        if case_or_file == "Case":
            title = _("Coded cases ")
        if self.category_name != "":
            title += _(" of category: ") + self.category_name
        self.setWindowTitle(title)
        self.gridLayout = QtWidgets.QGridLayout(self)
        self.te = QtWidgets.QTextEdit()
        self.gridLayout.addWidget(self.te, 1, 0)
        self.te.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.te.customContextMenuRequested.connect(self.text_edit_menu)
        self.text_results = []
        self.image_results = []
        self.av_results = []
        self.codes = []
        self.categories = []
        self.codes, self.categories = self.app.get_codes_categories()
        self.get_coded_segments_all_files()
        self.te.cursorPositionChanged.connect(self.show_context_of_clicked_heading)
        self.exec()

    def get_coded_segments_all_files(self):
        """ Get coded segments by file for this code. """

        self.te.blockSignals(True)
        self.te.clear()
        if self.category_name != "":
            hmsg = "<h2>" + _("Codes under category: ") + f"{self.category_name}</h2><br />"
            self.te.insertHtml(hmsg)
        msg = _("Left click on heading for coding in context") + "\n"
        msg += _("Right click on heading to unmark or to add codes") + "\n\n"
        self.te.append(msg)
        cur = self.app.conn.cursor()
        sql = "select code_name.name, color, source.name, pos0, pos1, seltext, source.name, source.id,ctid," \
              "important, code_text_visible.memo, code_text_visible.owner from "
        sql += "code_text_visible "
        sql += " join code_name on code_name.cid = code_text_visible.cid join source on fid = source.id "
        sql += " where code_name.cid=? "
        sql += " order by source.name, pos0"
        if self.case_or_file == "Case":
            sql = "select code_name.name, color, cases.name, "
            sql += "code_text_visible.pos0, code_text_visible.pos1, seltext, source.name, source.id, ctid, important," \
                   "code_text_visible.memo, code_text_visible.owner from code_text_visible "
            sql += " join code_name on code_name.cid = code_text_visible.cid "
            sql += " join (case_text join cases on cases.caseid = case_text.caseid) on "
            sql += " code_text_visible.fid = case_text.fid "
            sql += "and (code_text_visible.pos0 between case_text.pos0 and case_text.pos1) "
            sql += "and (code_text_visible.pos1 between case_text.pos0 and case_text.pos1) "
            sql += " join source on source.id = code_text_visible.fid "
            sql += " where code_name.cid=? "
            sql += " order by cases.name, code_text_visible.pos0, code_text_visible.owner"
        keys = 'codename', 'color', 'file_or_casename', 'pos0', 'pos1', 'text', 'source_name', 'fid', 'ctid', \
            'important', 'memo', 'owner'
        self.text_results = []
        for code in self.codes_list:
            cur.execute(sql, [code['cid']])
            results = cur.fetchall()
            for row in results:
                res_dict = dict(zip(keys, row))
                res_dict['codename'] = code['name']
                res_dict['cid'] = code['cid']
                self.text_results.append(res_dict)

        # Text insertion into textEdit
        if self.text_results:
            hmsg = "<h3>" + _("Coded text") + "<h3><br />"
            self.te.insertHtml(hmsg)
        for row in self.text_results:
            row['file_or_case'] = self.case_or_file
            row['textedit_start'] = len(self.te.toPlainText())
            self.insert_title(row)
            row['textedit_end'] = len(self.te.toPlainText())
            self.te.append(f"{row['text']}\n")
            if row['memo']:
                self.te.append(_("Memo: ") + row['memo'] + "\n")

        # Get coded image by file for this coder data
        sql = "select code_name.name, color, source.name, x1, y1, width, height,source.mediapath, source.id, "
        sql += "pdf_page, code_image_visible.memo, imid, important, code_image_visible.owner, pdf_page "
        sql += "from code_image_visible join code_name "
        sql += "on code_name.cid = code_image_visible.cid join source on code_image_visible.id = source.id "
        sql += "where code_name.cid =? "
        sql += "order by source.name"
        if self.case_or_file == "Case":
            sql = "select code_name.name, color, cases.name, x1, y1, width, height, source.mediapath,"
            sql += "source.id, code_image_visible.memo,imid, important, code_image_visible.owner, pdf_page "
            sql += "from code_image_visible join code_name on code_name.cid = code_image_visible.cid "
            sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
            sql += "code_image_visible.id = case_text.fid "
            sql += "join source on case_text.fid = source.id "
            sql += "where code_name.cid=? "
            sql += "order by cases.name, code_image_visible.owner "
        keys = 'codename', 'color', 'file_or_casename', 'x1', 'y1', 'width', 'height', 'mediapath', 'fid', 'pdf_page', \
            'memo', 'imid', 'important', 'owner', 'pdf_page'
        self.image_results = []
        for code in self.codes_list:
            cur.execute(sql, [code['cid']])
            results = cur.fetchall()
            for row in results:
                res_dict = dict(zip(keys, row))
                res_dict['codename'] = code['name']
                res_dict['cid'] = code['cid']
                self.image_results.append(res_dict)

        # Image - textEdit insertion
        if self.image_results:
            hmsg = "<h3>" + _("Coded images") + "<h3><br />"
            self.te.insertHtml(hmsg)
        for counter, row in enumerate(self.image_results):
            row['file_or_case'] = self.case_or_file
            row['textedit_start'] = len(self.te.toPlainText())
            self.insert_title(row)
            row['textedit_end'] = len(self.te.toPlainText())
            img = {'mediapath': row['mediapath'], 'x1': row['x1'], 'y1': row['y1'], 'width': row['width'],
                   'height': row['height'], 'pdf_page': row['pdf_page']}
            self.put_image_into_textedit(img, counter, self.te)
            if row['memo'] != "":
                self.te.append(_("Memo: ") + row['memo'] + "\n")
            else:
                self.te.append("\n")

        # Get coded A/V by file for this coder data
        sql = "select code_name.name, color, source.name, pos0, pos1, code_av_visible.memo, source.mediapath, "
        sql += "source.id, avid, important, code_av_visible.owner from code_av_visible join code_name "
        sql += "on code_name.cid = code_av_visible.cid join source on code_av_visible.id = source.id "
        sql += "where code_name.cid =? "
        sql += " order by source.name"
        if self.case_or_file == "Case":
            sql = "select code_name.name, color, cases.name, code_av_visible.pos0, code_av_visible.pos1, "
            sql += "code_av_visible.memo, source.mediapath, source.id, avid, important, code_av_visible.owner from "
            sql += "code_av_visible join code_name on code_name.cid = code_av_visible.cid "
            sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
            sql += "code_av_visible.id = case_text.fid "
            sql += " join source on case_text.fid = source.id "
            sql += "where code_name.cid=? "
            sql += " order by source.name, code_av_visible.owner "
        keys = 'codename', 'color', 'file_or_casename', 'pos0', 'pos1', 'memo', 'mediapath', 'fid', 'avid', \
            'important', 'owner'
        self.av_results = []
        for code in self.codes_list:
            cur.execute(sql, [code['cid']])
            results = cur.fetchall()
            for row in results:
                res_dict = dict(zip(keys, row))
                res_dict['codename'] = code['name']
                res_dict['cid'] = code['cid']
                self.av_results.append(res_dict)
        # A/V - textEdit insertion
        if self.av_results:
            hmsg = "<h3>" + _("Coded audio / video") + "<h3><br />"
            self.te.insertHtml(hmsg)
        for row in self.av_results:
            row['file_or_case'] = self.case_or_file
            row['textedit_start'] = len(self.te.toPlainText())
            self.insert_title(row)
            start = msecs_to_mins_and_secs(row['pos0'])
            end = msecs_to_mins_and_secs(row['pos1'])
            self.te.insertHtml(f'<br />Time: [{start} - {end}] ')
            row['textedit_end'] = len(self.te.toPlainText())
            if row['memo'] != "":
                self.te.append(_("Memo: ") + row['memo'] + "\n")
            else:
                self.te.append("\n")

        self.te.moveCursor(QtGui.QTextCursor.MoveOperation.Start)
        self.te.blockSignals(False)

    def insert_title(self, row):
        """ Convenience method for a/v, image, text title insertion.
        Args:
            row : Dictionary
        """

        foregroundcolor = f"color:{TextColor(row['color']).recommendation};"
        title = f'<span style="background-color:{row["color"]}; {foregroundcolor}\">'
        if self.case_or_file == "File":
            title += _(" File: ") + row['file_or_casename']
        else:
            title += _("Case: ") + row['file_or_casename'] + _(" File: ") + row['source_name']
        if 'pos0' in row.keys():
            title += f", [{row['pos0']} - {row['pos1']}]"
        title += "  " + _("Code:") + f" {row['codename']} ({row['owner']})"
        if row['important']:
            title += " [!]"
        title += "</span><br />"
        self.te.insertHtml(title)

    def put_image_into_textedit(self, img, counter:int, text_edit):
        """ Scale image, add resource to document, insert image.
        A counter is important as each image slice needs a unique name, counter adds
        the uniqueness to the name.
        Called by: coded_media_dialog
        Args:
            img: image data dictionary with file location and width, height, position data
            counter: a changing counter is needed to make discrete different images
            text_edit:  the widget that shows the data
        """

        abs_path = ""
        image = None
        if "images:" in img['mediapath']:
            abs_path = img['mediapath'].split(':')[1]
        else:
            abs_path = self.app.project_path + img['mediapath']
        if not img['mediapath'].lower().endswith(".pdf"):
            image = QtGui.QImage(abs_path)
        else:  # A pdf, must create the image
            source_path = ""
            if img['mediapath'][:6] == "/docs/":
                source_path = f"{self.app.project_path}/documents/{img['mediapath'][6:]}"
            if img['mediapath'][:5] == "docs:":
                source_path = img['mediapath'][5:]
            # In-memory render of only the needed page, document always closed
            # (the old tmp_pdf_page.png pattern leaked the handle and went stale).
            image = QtGui.QImage()
            # Areas from older imports may have pdf_page NULL: they belong to page 0
            # (same normalization as the image coding view).
            pdf_page_ = img['pdf_page'] if img['pdf_page'] is not None else 0
            try:
                fitz_pdf = fitz.open(source_path)
                try:
                    if 0 <= pdf_page_ < len(fitz_pdf):
                        page = fitz_pdf.load_page(pdf_page_)
                        pix = page.get_pixmap(alpha=False, annots=False)  # PDF highlights/notes not painted
                        image = QtGui.QImage(pix.samples, pix.width, pix.height, pix.stride,
                                             QtGui.QImage.Format.Format_RGB888).copy()
                finally:
                    fitz_pdf.close()
            except Exception as err:
                logger.warning(f"Pdf area image: {source_path} {err}")
            if image.isNull():
                return
        image = image.copy(int(img['x1']), int(img['y1']), int(img['width']), int(img['height']))
        # scale to max 300 wide or high. perhaps add option to change maximum limit?
        scaler_w = 1.0
        scaler_h = 1.0
        if image.width() > 300:
            scaler_w = 300 / image.width()
        if image.height() > 300:
            scaler_h = 300 / image.height()
        if scaler_w < scaler_h:
            scaler = scaler_w
        else:
            scaler = scaler_h
        # Need unique image names or the same image from the same path is reproduced
        imagename = os.path.join(self.app.project_path, "images", f"{counter}-{img['mediapath']}")
        url = QtCore.QUrl(imagename)
        document = text_edit.document()
        document.addResource(QtGui.QTextDocument.ResourceType.ImageResource.value, url, image)
        # See https://doc.qt.io/qt-6/qtextdocument.html#addResource
        # The image can be inserted into the document using the QTextCursor API:
        cursor = text_edit.textCursor()
        image_format = QtGui.QTextImageFormat()
        image_format.setWidth(image.width() * scaler)
        image_format.setHeight(image.height() * scaler)
        image_format.setName(url.toString())
        cursor.insertImage(image_format)
        text_edit.insertHtml("<br />")

    def show_context_of_clicked_heading(self):
        """ Heading (code, file, etc) in textEdit clicked so show context of coding in dialog.
        Called by: textEdit.cursorPositionChanged, after results are filled.
        text/image/AV results contain textedit_start and textedit_end which map the cursor position to the
        specific result.
        """

        pos = self.te.textCursor().position()
        # Check the clicked position for a text result
        for row in self.text_results:
            if row['textedit_start'] <= pos < row['textedit_end']:
                ui = DialogCodeInText(self.app, row)
                ui.exec()
                return
        # Check the position for an image result
        for row in self.image_results:
            if row['textedit_start'] <= pos < row['textedit_end']:
                ui = DialogCodeInImage(self.app, row)
                ui.exec()
                return
        # Check the position for an a/v result
        for row in self.av_results:
            if row['textedit_start'] <= pos < row['textedit_end']:
                ui = DialogCodeInAV(self.app, row)
                ui.exec()
                break

    def text_edit_menu(self, position):
        """ Context menu for textEdit.
        Mark, unmark, annotate, important mark, memo.
        """

        cursor = self.te.cursorForPosition(position)
        pos = cursor.position()
        # Check the clicked position for a text result
        item = None
        for row in self.text_results:
            if row['textedit_start'] <= pos < row['textedit_end']:
                item = {'type': 'text', 'res': row}
                break
        # Check the position for an image result
        for row in self.image_results:
            if row['textedit_start'] <= pos < row['textedit_end']:
                item = {'type': 'image', 'res': row}
                break
        # Check the position for an a/v result
        for row in self.av_results:
            if row['textedit_start'] <= pos < row['textedit_end']:
                item = {'type': 'av', 'res': row}
                break
        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        action_mark = None
        action_unmark = None
        action_memo = None
        action_add_important = None
        action_remove_important = None
        if item:
            action_mark = menu.addAction(_("Apply more codes to this segment"))
            action_unmark = menu.addAction(_("Remove code"))
            action_memo = menu.addAction(_("Memo"))
            if item['res']['important']:
                action_remove_important = menu.addAction(_("Remove important flag"))
            else:
                action_add_important = menu.addAction(_("Add important flag"))
        action_export_odt = menu.addAction((_("Export to ODT file")))
        action = menu.exec(self.te.mapToGlobal(position))
        if action is None:
            return
        if action == action_export_odt:
            self.export_odt()
        if action == action_mark:
            self.mark_with_more_codes(item)
            return
        if action == action_unmark:
            cur = self.app.conn.cursor()
            if item['type'] == "text":
                cur.execute("delete from code_text where ctid=?", [item['res']['ctid']])
                self.app.conn.commit()
            if item['type'] == "image":
                cur.execute("delete from code_image where imid=?", [item['res']['imid']])
                self.app.conn.commit()
            if item['type'] == "av":
                cur.execute("delete from code_av where avid=?", [item['res']['avid']])
                self.app.conn.commit()
            self.get_coded_segments_all_files()
            self.app.delete_backup = False
            return
        if action == action_memo:
            self.edit_memo(item)
        if action == action_add_important:
            self.add_important_flag(item)
        if action == action_remove_important:
            self.remove_important_flag(item)

    def add_important_flag(self, item):
        """ Add flag to item
        Args:
            item : Dictionary
        """

        cur = self.app.conn.cursor()
        if item['type'] == 'text':
            cur.execute("update code_text set important=1 where ctid=?", (item['res']['ctid'],))
        if item['type'] == 'image':
            cur.execute("update code_image set important=1 where imid=?", (item['res']['imid'],))
        if item['type'] == 'av':
            cur.execute("update code_av set important=1 where avid=?", (item['res']['avid'],))
        self.app.conn.commit()
        self.get_coded_segments_all_files()
        self.app.delete_backup = False

    def remove_important_flag(self, item):

        cur = self.app.conn.cursor()
        if item['type'] == 'text':
            cur.execute("update code_text set important=null where ctid=?", (item['res']['ctid'],))
        if item['type'] == 'image':
            cur.execute("update code_image set important=null where imid=?", (item['res']['imid'],))
        if item['type'] == 'av':
            cur.execute("update code_av set important=null where avid=?", (item['res']['avid'],))
        self.app.conn.commit()
        self.get_coded_segments_all_files()
        self.app.delete_backup = False

    def edit_memo(self, item):
        """ Edit item memo.
        Args:
            item : Dictionary
        """

        ui = DialogMemo(self.app, _("Memo for Coded: ") + item['type'], item['res']['memo'], "show")
        ui.exec()
        memo = ui.memo
        if memo == item['res']['memo']:
            return
        cur = self.app.conn.cursor()
        if item['type'] == 'text':
            cur.execute("update code_text set memo=? where ctid=?", (memo, item['res']['ctid']))
        if item['type'] == 'image':
            cur.execute("update code_image set memo=? where imid=?", (memo, item['res']['imid']))
        if item['type'] == 'av':
            cur.execute("update code_av set memo=? where avid=?", (memo, item['res']['avid']))
        self.app.conn.commit()
        self.get_coded_segments_all_files()
        self.app.delete_backup = False

    def export_odt(self):
        """ Export all contents to ODT file. """

        filename = "Coded_media.odt"
        exp_dir = ExportDirectoryPathDialog(self.app, filename)
        filepath = exp_dir.filepath
        if filepath is None:
            return
        tw = QtGui.QTextDocumentWriter()
        tw.setFileName(filepath)
        tw.setFormat(b'ODF')  # byte array needed for Windows 10
        tw.write(self.te.document())
        msg = _("Coded text file exported: ") + filepath
        Message(self.app, _('Coded text file exported'), msg, "information").exec()

    def mark_with_more_codes(self, item):
        """ Select and apply more codes to this coded segment.
        Args:
            item : Dictionary
        """

        codes = [c for c in self.codes if c['cid'] != item['res']['cid']]
        ui = DialogSelectItems(self.app, codes, _("Select codes"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selection = ui.get_selected()
        if not selection:
            return
        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        cur = self.app.conn.cursor()
        for i, s in enumerate(selection):
            if item['type'] == "text":
                try:
                    cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,\
                        memo,date, important) values(?,?,?,?,?,?,?,?,?)", (s['cid'], item['res']['fid'],
                                                                           item['res']['text'], item['res']['pos0'],
                                                                           item['res']['pos1'],
                                                                           self.app.settings['codername'],
                                                                           "", now_date, None))
                    self.app.conn.commit()
                except sqlite3.IntegrityError:
                    pass
            if item['type'] == "image":
                try:
                    cur.execute(
                        "insert into code_image (id,x1,y1,width,height,cid,memo,date,owner, important) "
                        "values(?,?,?,?,?,?,?,?,?,?)",
                        (item['res']['fid'], item['res']['x1'] + (i + 1) * 3, item['res']['y1'] + (1 + i) * 3,
                         item['res']['width'] + (1 + i) * 3, item['res']['height'] + (1 + i) * 3,
                         s['cid'], "", now_date, self.app.settings['codername'], None))
                    self.app.conn.commit()
                except sqlite3.IntegrityError:
                    pass
            if item['type'] == "av":
                try:
                    sql = "insert into code_av (id, pos0, pos1, cid, memo, date, owner, important) " \
                          "values(?,?,?,?,?,?,?, null)"
                    values = [item['res']['fid'], item['res']['pos0'], item['res']['pos1'],
                              s['cid'], "", now_date, self.app.settings['codername']]
                    cur.execute(sql, values)
                    self.app.conn.commit()
                except sqlite3.IntegrityError:
                    pass


class DialogCodedIds(QtWidgets.QDialog):
    """ Display all coded segments using imids, avdids, or ctids, in a modal dialog.
    Need to store textedit start and end positions so that code in context can be used.
    Called from:
        DialogReportCodes
    """

    def __init__(self, app, prime_item):
        """ Create dialog with textEdit widget to show all code ids.
        Used to show codes that overlaps with another base code.
        Called by: DialogReportCodes
        Args:
            app : class containing app details such as database connection
            prime_item : dictionary of the coded item, containing 'overlaps'
        """

        self.app = app
        self.prime_item = prime_item
        # item may not contain 'important'
        self.prime_item['memo'] = self.prime_item['coded_memo']
        self.prime_item['owner'] = prime_item['coder']  # needed for insert_title.
        QtWidgets.QDialog.__init__(self)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.resize(620, 580)
        # Enable custom window hint to enable customizing window controls
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowType.CustomizeWindowHint)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        title = _("Coded segments")
        self.setWindowTitle(title)
        self.gridLayout = QtWidgets.QGridLayout(self)
        self.te = QtWidgets.QTextEdit()
        self.gridLayout.addWidget(self.te, 1, 0)
        self.te.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.te.customContextMenuRequested.connect(self.text_edit_menu)
        self.text_results = []
        self.image_results = []
        self.av_results = []
        self.insert_prime_coded_item()
        self.get_and_insert_coded_segments()
        self.exec()

    def insert_prime_coded_item(self):
        """  For overlapping codes, show the primary one. """

        hmsg = "<p><i>Right click for export options</i></p><br />"
        self.te.insertHtml(hmsg)
        hmsg = "<h3>" + _("Coded item") + "<h3>"
        self.te.insertHtml(hmsg)
        self.insert_title(self.prime_item)
        if self.prime_item['result_type'] == 'text':
            self.te.append(self.prime_item['text'] + "\n")
        if self.prime_item['result_type'] == 'av':
            start = msecs_to_mins_and_secs(self.prime_item['pos0'])
            end = msecs_to_mins_and_secs(self.prime_item['pos1'])
            self.te.insertHtml(f'<br />Time: [{start} - {end}] ')
        if self.prime_item['result_type'] == 'image':
            img = {'mediapath': self.prime_item['mediapath'], 'x1': self.prime_item['x1'], 'y1': self.prime_item['y1'],
                   'width': self.prime_item['width'], 'height': self.prime_item['height'], ''
                    'pdf_page': self.prime_item['pdf_page']}
            self.put_image_into_textedit(img, 9999, self.te)
        if 'memo' in self.prime_item and self.prime_item['memo'] != "":
            self.te.append(_("Memo: ") + self.prime_item['memo'] + "\n")
        hmsg = "<br /><h3>" + _("Overlaps") + "<h3><br />"
        self.te.insertHtml(hmsg)

    def get_and_insert_coded_segments(self):
        """ Get coded text by file for this code. Insert into text edit. """

        self.te.blockSignals(True)
        cur = self.app.conn.cursor()

        # Get coded text by file for this coded data
        if self.prime_item['result_type'] == 'text':
            sql = "select code_name.name, color, source.name, pos0, pos1, seltext, source.name, source.id,ctid," \
                  "important, code_text_visible.memo, code_text_visible.owner from "
            sql += "code_text_visible "
            sql += " join code_name on code_name.cid = code_text_visible.cid join source on fid = source.id "
            sql += " where ctid=? "
            sql += " order by pos0"
            keys = 'codename', 'color', 'file_or_casename', 'pos0', 'pos1', 'text', 'source_name', 'fid', 'ctid', \
                'important', 'memo', 'owner'
            self.text_results = []
            for id_ in self.prime_item['overlaps']:
                cur.execute(sql, [id_])
                results = cur.fetchone()
                res_dict = dict(zip(keys, results))
                self.text_results.append(res_dict)
            # Text insertion into textEdit
            for row in self.text_results:
                row['textedit_start'] = len(self.te.toPlainText())
                self.insert_title(row)
                row['textedit_end'] = len(self.te.toPlainText())
                self.te.append(f"{row['text']}\n")
                if row['memo']:
                    self.te.append(_("Memo: ") + row['memo'] + "\n")
        if 'image' in self.prime_item['result_type']:
            sql = "select code_name.name, color, source.name, x1, y1, width, height,source.mediapath, source.id, "
            sql += "pdf_page, code_image_visible.memo, imid, important, code_image_visible.owner, pdf_page "
            sql += "from code_image_visible join code_name "
            sql += "on code_name.cid = code_image_visible.cid join source on code_image_visible.id = source.id "
            sql += "where imid =? "
            keys = 'codename', 'color', 'file_or_casename', 'x1', 'y1', 'width', 'height', 'mediapath', 'fid', 'pdf_page', \
                'memo', 'imid', 'important', 'owner', 'pdf_page'
            self.image_results = []
            for id_ in self.prime_item['overlaps']:
                cur.execute(sql, [id_])
                results = cur.fetchall()
                for row in results:
                    res_dict = dict(zip(keys, row))
                    self.image_results.append(res_dict)
            # Image - textEdit insertion
            for counter, row in enumerate(self.image_results):
                row['textedit_start'] = len(self.te.toPlainText())
                self.insert_title(row)
                row['textedit_end'] = len(self.te.toPlainText())
                img = {'mediapath': row['mediapath'], 'x1': row['x1'], 'y1': row['y1'], 'width': row['width'],
                       'height': row['height'], 'pdf_page': row['pdf_page']}
                self.put_image_into_textedit(img, counter, self.te)
                if row['memo'] != "":
                    self.te.append(_("Memo: ") + row['memo'] + "\n")
                else:
                    self.te.append("\n")

        if 'av' in self.prime_item['result_type']:
            sql = "select code_name.name, color, source.name, pos0, pos1, code_av_visible.memo, source.mediapath, "
            sql += "source.id, avid, important, code_av_visible.owner from code_av_visible join code_name "
            sql += "on code_name.cid = code_av_visible.cid join source on code_av_visible.id = source.id "
            sql += "where avid =? "
            sql += " order by pos0"
            keys = 'codename', 'color', 'file_or_casename', 'pos0', 'pos1', 'memo', 'mediapath', 'fid', 'avid', \
                'important', 'owner'
            self.av_results = []
            for id_ in self.prime_item['overlaps']:
                cur.execute(sql, [id_])
                results = cur.fetchall()
                for row in results:
                    res_dict = dict(zip(keys, row))
                    self.av_results.append(res_dict)
            # A/V - textEdit insertion
            for row in self.av_results:
                row['textedit_start'] = len(self.te.toPlainText())
                self.insert_title(row)
                start = msecs_to_mins_and_secs(row['pos0'])
                end = msecs_to_mins_and_secs(row['pos1'])
                self.te.insertHtml(f'<br />Time: [{start} - {end}] ')
                row['textedit_end'] = len(self.te.toPlainText())
                if row['memo'] != "":
                    self.te.append(_("Memo: ") + row['memo'] + "\n")
                else:
                    self.te.append("\n")

        self.te.moveCursor(QtGui.QTextCursor.MoveOperation.Start)
        self.te.blockSignals(False)

    def insert_title(self, row):
        """ Convenience method for a/v, image, text title insertion.
        Args:
            row : Dictionary
        """

        foregroundcolor = f"color:{TextColor(row['color']).recommendation};"
        title = f'<span style="background-color:{row["color"]}; {foregroundcolor}\">'
        title += _(" File: ") + row['file_or_casename']
        if 'pos0' in row.keys():
            title += f", [{row['pos0']} - {row['pos1']}]"
        title += "  " + _("Code:") + f" {row['codename']} ({row['owner']})"
        if 'important' in row and row['important']:
            title += " [!]"
        title += "</span><br />"
        self.te.insertHtml(title)

    def put_image_into_textedit(self, img, counter: int, text_edit):
        """ Scale image, add resource to document, insert image.
        A counter is important as each image slice needs a unique name, counter adds
        the uniqueness to the name.
        Called by: coded_media_dialog
        Args:
            img: image data dictionary with file location and width, height, position data
            counter: a changing counter is needed to make discrete different images
            text_edit:  the widget that shows the data
        """

        abs_path = ""
        image = None
        if "images:" in img['mediapath']:
            abs_path = img['mediapath'].split(':')[1]
        else:
            abs_path = self.app.project_path + img['mediapath']
        if not img['mediapath'].lower().endswith(".pdf"):
            image = QtGui.QImage(abs_path)
        else:  # A pdf, must create the image
            source_path = ""
            if img['mediapath'][:6] == "/docs/":
                source_path = f"{self.app.project_path}/documents/{img['mediapath'][6:]}"
            if img['mediapath'][:5] == "docs:":
                source_path = img['mediapath'][5:]
            # In-memory render of only the needed page, document always closed
            # (the old tmp_pdf_page.png pattern leaked the handle and went stale).
            image = QtGui.QImage()
            # Areas from older imports may have pdf_page NULL: they belong to page 0
            # (same normalization as the image coding view).
            pdf_page_ = img['pdf_page'] if img['pdf_page'] is not None else 0
            try:
                fitz_pdf = fitz.open(source_path)
                try:
                    if 0 <= pdf_page_ < len(fitz_pdf):
                        page = fitz_pdf.load_page(pdf_page_)
                        pix = page.get_pixmap(alpha=False, annots=False)  # PDF highlights/notes not painted
                        image = QtGui.QImage(pix.samples, pix.width, pix.height, pix.stride,
                                             QtGui.QImage.Format.Format_RGB888).copy()
                finally:
                    fitz_pdf.close()
            except Exception as err:
                logger.warning(f"Pdf area image: {source_path} {err}")
            if image.isNull():
                return
        image = image.copy(int(img['x1']), int(img['y1']), int(img['width']), int(img['height']))
        # scale to max 600 wide or high. Add option to change maximum limit?
        scaler_w = 1.0
        scaler_h = 1.0
        if image.width() > 600:
            scaler_w = 600 / image.width()
        if image.height() > 600:
            scaler_h = 600 / image.height()
        if scaler_w < scaler_h:
            scaler = scaler_w
        else:
            scaler = scaler_h
        # Need unique image names or the same image from the same path is reproduced
        imagename = os.path.join(self.app.project_path, "images", f"{counter}-{img['mediapath']}")
        url = QtCore.QUrl(imagename)
        document = text_edit.document()
        document.addResource(QtGui.QTextDocument.ResourceType.ImageResource.value, url, image)
        # See https://doc.qt.io/qt-6/qtextdocument.html#addResource
        # The image can be inserted into the document using the QTextCursor API:
        cursor = text_edit.textCursor()
        image_format = QtGui.QTextImageFormat()
        image_format.setWidth(image.width() * scaler)
        image_format.setHeight(image.height() * scaler)
        image_format.setName(url.toString())
        cursor.insertImage(image_format)
        text_edit.insertHtml("<br />")

    def text_edit_menu(self, position):
        """ Context menu for textEdit. To export text_edit. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"font-size:{self.app.settings['fontsize']}pt")
        menu.setToolTipsVisible(True)
        action_export_odt = menu.addAction(_("Export as ODT file"))
        # TODO action_export_html = menu.addAction(_("Export as HTML files"))
        action = menu.exec(self.te.mapToGlobal(position))
        if action == action_export_odt:
            filename = "Overlaps.odt"
            exp_dir = ExportDirectoryPathDialog(self.app, filename)
            filepath = exp_dir.filepath
            if filepath is None:
                return
            tw = QtGui.QTextDocumentWriter()
            tw.setFileName(filepath)
            tw.setFormat(b'ODF')  # byte array needed for Windows 10
            tw.write(self.te.document())
            msg = _("Overlaps exported: ") + filepath
            Message(self.app, _('Overlaps exported'), msg, "information").exec()
