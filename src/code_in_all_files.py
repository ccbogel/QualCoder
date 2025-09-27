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
"""

import datetime
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
    Called from code_text, code_av, code_image.
    """

    app = None
    code_dict = None
    case_or_file = None
    codes = []
    categories = []
    text_results = []
    image_results = []
    av_results = []
    te = None

    def __init__(self, app, code_dict, case_or_file="File", parent=None):
        """ Create dialog with textEdit widget to show all codings of this code.
        Called: code_text.coded_media_dialog , code_av.coded_media_dialog , code_image.coded_media_dialog
        param:
            app : class containing app details such as database connection
            code_dict : dictionary of this code {name, color, cid, catid, date, owner, memo}
            case_or_file: default to "File", but view_graph has a "Case" option
        """

        self.app = app
        self.code_dict = code_dict
        self.case_or_file = case_or_file
        QtWidgets.QDialog.__init__(self)

        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.resize(550, 580)
        # Enable custom window hint to enable customizing window controls
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowType.CustomizeWindowHint)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)

        title = _("Coded files: ") + self.code_dict['name']
        if case_or_file == "Case":
            title = _("Coded cases: ") + self.code_dict['name']
        self.setWindowTitle(title)
        self.gridLayout = QtWidgets.QGridLayout(self)
        self.te = QtWidgets.QTextEdit()
        self.gridLayout.addWidget(self.te, 1, 0)
        self.te.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.te.customContextMenuRequested.connect(self.text_edit_menu)
        msg = _("Left click on heading for coding in context") + "\n"
        msg += _("Right click on heading to unmark or to add codes") + "\n\n"
        self.te.append(msg)

        self.codes, self.categories = self.app.get_codes_categories()
        self.get_coded_segments_all_files()
        self.te.cursorPositionChanged.connect(self.show_context_of_clicked_heading)
        self.exec()

    def get_coded_segments_all_files(self):
        """ Get coded text by file for this coder data """

        self.te.blockSignals(True)
        self.te.clear()
        msg = _("Left click on heading for coding in context") + "\n"
        msg += _("Right click on heading to unmark or to add codes") + "\n\n"
        self.te.append(msg)
        cur = self.app.conn.cursor()
        sql = "select code_name.name, color, source.name, pos0, pos1, seltext, source.name, source.id,ctid," \
              "important, code_text.memo from "
        sql += "code_text "
        sql += " join code_name on code_name.cid = code_text.cid join source on fid = source.id "
        sql += " where code_name.cid=? and code_text.owner=?"
        sql += " order by source.name, pos0"
        if self.case_or_file == "Case":
            sql = "select code_name.name, color, cases.name, "
            sql += "code_text.pos0, code_text.pos1, seltext, source.name, source.id, ctid, important," \
                   "code_text.memo from code_text "
            sql += " join code_name on code_name.cid = code_text.cid "
            sql += " join (case_text join cases on cases.caseid = case_text.caseid) on "
            sql += " code_text.fid = case_text.fid "
            sql += "and (code_text.pos0 between case_text.pos0 and case_text.pos1) "
            sql += "and (code_text.pos1 between case_text.pos0 and case_text.pos1) "
            sql += " join source on source.id = case_text.fid "
            sql += " where code_name.cid=? and code_text.owner=? "
            sql += " order by cases.name, code_text.pos0, code_text.owner"
        cur.execute(sql, [self.code_dict['cid'], self.app.settings['codername']])
        results = cur.fetchall()
        self.text_results = []
        keys = 'codename', 'color', 'file_or_casename', 'pos0', 'pos1', 'text', 'source_name', 'fid', 'ctid', \
            'important', 'memo'
        for row in results:
            self.text_results.append(dict(zip(keys, row)))

        # Text insertion into textEdit
        for row in self.text_results:
            row['file_or_case'] = self.case_or_file
            row['textedit_start'] = len(self.te.toPlainText())
            foregroundcolor = f"color:{TextColor(row['color']).recommendation};"
            title = f'<span style="background-color:{row["color"]}; {foregroundcolor}\">'
            if self.case_or_file == "File":
                title += _(" File: ") + row['file_or_casename']
            else:
                title += _("Case: ") + row['file_or_casename'] + _(" File: ") + row['source_name']
            title += "</span>"
            title += f", {row['pos0']} - {row['pos1']}"
            self.te.insertHtml(title)
            row['textedit_end'] = len(self.te.toPlainText())
            self.te.append(f"{row['text']}\n\n")

        # Get coded image by file for this coder data
        sql = "select code_name.name, color, source.name, x1, y1, width, height,"
        sql += " source.mediapath, source.id, code_image.memo, imid, important "
        sql += " from code_image join code_name "
        sql += "on code_name.cid = code_image.cid join source on code_image.id = source.id "
        sql += "where code_name.cid =? and code_image.owner=? "
        sql += " order by source.name"
        if self.case_or_file == "Case":
            sql = "select code_name.name, color, cases.name, "
            sql += "x1, y1, width, height, source.mediapath, source.id, code_image.memo,imid, important "
            sql += "from code_image join code_name on code_name.cid = code_image.cid "
            sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
            sql += "code_image.id = case_text.fid "
            sql += " join source on case_text.fid = source.id "
            sql += "where code_name.cid=? and code_image.owner=? "
            sql += " order by cases.name, code_image.owner "
        cur.execute(sql, [self.code_dict['cid'], self.app.settings['codername']])
        results = cur.fetchall()
        self.image_results = []
        keys = 'codename', 'color', 'file_or_casename', 'x1', 'y1', 'width', 'height', 'mediapath', 'fid', 'memo', \
               'imid', 'important'
        for row in results:
            self.image_results.append(dict(zip(keys, row)))
        # Image - textEdit insertion
        for counter, row in enumerate(self.image_results):
            row['file_or_case'] = self.case_or_file
            row['textedit_start'] = len(self.te.toPlainText())
            foregroundcolor = f"color:{TextColor(row['color']).recommendation};"
            title = f'<p><span style="background-color:{row["color"]}; {foregroundcolor}">'
            if self.case_or_file == "Case":
                title += _(" Case: ") + row['file_or_casename'] + _(" File: ") + row['mediapath']
            else:
                title += _(" File: ") + row['mediapath']
            title += '</span></p>'
            self.te.insertHtml(title)
            row['textedit_end'] = len(self.te.toPlainText())
            self.te.append("\n")
            img = {'mediapath': row['mediapath'], 'x1': row['x1'], 'y1': row['y1'], 'width': row['width'],
                   'height': row['height']}
            self.put_image_into_textedit(img, counter, self.te)
            self.te.append(_("Memo: ") + row['memo'] + "\n\n")

        # Get coded A/V by file for this coder data
        sql = "select code_name.name, color, source.name, pos0, pos1, code_av.memo, "
        sql += "source.mediapath, source.id, avid, important from code_av join code_name "
        sql += "on code_name.cid = code_av.cid join source on code_av.id = source.id "
        sql += "where code_name.cid =? and code_av.owner=? "
        sql += " order by source.name"
        if self.case_or_file == "Case":
            sql = "select code_name.name, color, cases.name, code_av.pos0, code_av.pos1, code_av.memo, "
            sql += "source.mediapath, source.id, avid, important from "
            sql += "code_av join code_name on code_name.cid = code_av.cid "
            sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
            sql += "code_av.id = case_text.fid "
            sql += " join source on case_text.fid = source.id "
            sql += "where code_name.cid=? and code_av.owner=? "
            sql += " order by source.name, code_av.owner "
        cur.execute(sql, [self.code_dict['cid'], self.app.settings['codername']])
        results = cur.fetchall()
        self.av_results = []
        keys = 'codename', 'color', 'file_or_casename', 'pos0', 'pos1', 'memo', 'mediapath', 'fid', 'avid', 'important'
        for row in results:
            self.av_results.append(dict(zip(keys, row)))
        # A/V - textEdit insertion
        for row in self.av_results:
            row['file_or_case'] = self.case_or_file
            row['textedit_start'] = len(self.te.toPlainText())
            foregroundcolor = f"color:{TextColor(row['color']).recommendation};"
            title = f'<span style="background-color:{row["color"]}; {foregroundcolor}">'
            if self.case_or_file == "Case":
                title += _("Case: ") + row['file_or_casename'] + _(" File: ") + row['mediapath']
            else:
                title += _("File: ") + row['mediapath']
            title += '</span>'
            self.te.insertHtml(title)
            start = msecs_to_mins_and_secs(row['pos0'])
            end = msecs_to_mins_and_secs(row['pos1'])
            self.te.insertHtml(f'<br />[{start} - {end}] ')
            row['textedit_end'] = len(self.te.toPlainText())
            self.te.append("Memo: " + row['memo'] + "\n\n")
        self.te.blockSignals(False)

    def put_image_into_textedit(self, img, counter, text_edit):
        """ Scale image, add resource to document, insert image.
        A counter is important as each image slice needs a unique name, counter adds
        the uniqueness to the name.
        Called by: coded_media_dialog
        param:
            img: image data dictionary with file location and width, height, position data
            counter: a changing counter is needed to make discrete different images
            text_edit:  the widget that shows the data
        """

        path_ = self.app.project_path
        if img['mediapath'][0] == "/":
            path_ = path_ + img['mediapath']
        else:
            path_ = img['mediapath'][7:]
        document = text_edit.document()
        image = QtGui.QImageReader(path_).read()
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
        imagename = self.app.project_path + '/images/' + str(counter) + '-' + img['mediapath']
        url = QtCore.QUrl(imagename)
        document.addResource(QtGui.QTextDocument.ResourceType.ImageResource.value, url, image)
        # https://doc.qt.io/qt-6/qtextdocument.html#addResource
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
        Mark, unmark, annotate.
        TODO important mark, memo
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
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_mark = None
        action_unmark = None
        action_memo = None
        action_add_important = None
        action_remove_important = None
        if item:
            action_mark = menu.addAction(_("Appy more codes to this segment"))
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
            print("MEMO")
            self.edit_memo(item)
        if action == action_add_important:
            self.add_important_flag(item)
        if action == action_remove_important:
            self.remove_important_flag(item)

    def add_important_flag(self, item):

        cur = self.app.conn.cursor()
        print(item)
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
        """ Edit item memo. """

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
        """ Select and apply more codes to this coded segment. """

        codes = [c for c in self.codes if c['cid'] != self.code_dict['cid']]
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
                    sql = "insert into code_av (id, pos0, pos1, cid, memo, date, owner, important) values(?,?,?,?,?,?,?, null)"
                    values = [item['res']['fid'], item['res']['pos0'], item['res']['pos1'],
                              s['cid'], "", now_date, self.app.settings['codername']]
                    cur.execute(sql, values)
                    self.app.conn.commit()
                except sqlite3.IntegrityError:
                    pass
