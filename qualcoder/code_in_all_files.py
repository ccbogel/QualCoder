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

import logging
import os
import sys
import traceback

from PyQt6 import QtCore, QtGui, QtWidgets

from .color_selector import TextColor
from .helpers import msecs_to_mins_and_secs, DialogCodeInAV, DialogCodeInImage, DialogCodeInText

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


class DialogCodeInAllFiles(QtWidgets.QDialog):
    """ Display all coded media for this code, in a modal dialog.
    Coded media comes from ALL files for this coder.
    Need to store textedit start and end positions so that code in context can be used.
    Called from code_text, code_av, code_image.

    """

    app = None
    code_dict = None
    codes = []
    categories = []
    text_results = []
    image_results = []
    av_results = []
    te = None

    def __init__(self, app, code_dict, case_or_file="File", parent=None):
        """ Create dialog with textEdit widget.
        param:
            app : class containing app details such as database connection
            code_dict : dictionary of this code {name, color, cid, catid, date, owner, memo}
            case_or_file: default to "File", but view_graph has a "Case" option
        """

        sys.excepthook = exception_handler
        self.app = app
        self.code_dict = code_dict
        QtWidgets.QDialog.__init__(self)

        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
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
        msg = _("Click on heading for coding in context") + "\n\n"
        self.te.append(msg)

        self.codes, self.categories = self.app.get_codes_categories()

        # Get coded text by file for this coder data
        cur = self.app.conn.cursor()
        sql = "select code_name.name, color, source.name, pos0, pos1, seltext, source.name, source.id from "
        sql += "code_text "
        sql += " join code_name on code_name.cid = code_text.cid join source on fid = source.id "
        sql += " where code_name.cid=? and code_text.owner=?"
        sql += " order by source.name, pos0"
        if case_or_file == "Case":
            sql = "select code_name.name, color, cases.name, "
            sql += "code_text.pos0, code_text.pos1, seltext, source.name, source.id from code_text "
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
        keys = 'codename', 'color', 'file_or_casename', 'pos0', 'pos1', 'text', 'source_name', 'fid'
        for row in results:
            self.text_results.append(dict(zip(keys, row)))

        # Text insertion into textEdit
        for row in self.text_results:
            row['file_or_case'] = case_or_file
            row['textedit_start'] = len(self.te.toPlainText())
            fgc = "; color:" + TextColor(row['color']).recommendation + ";"
            title = '<span style=\"background-color:' + row['color'] + fgc + '\">'
            if case_or_file == "File":
                title += _(" File: ") + row['file_or_casename']
            else:
                title += _("Case: ") + row['file_or_casename'] + _(" File: ") + row['source_name']
            title += "</span>"
            title += ", " + str(row['pos0']) + " - " + str(row['pos1'])
            self.te.insertHtml(title)
            row['textedit_end'] = len(self.te.toPlainText())
            self.te.append(row['text'] + "\n\n")

        # Get coded image by file for this coder data
        sql = "select code_name.name, color, source.name, x1, y1, width, height,"
        sql += " source.mediapath, source.id, code_image.memo "
        sql += " from code_image join code_name "
        sql += "on code_name.cid = code_image.cid join source on code_image.id = source.id "
        sql += "where code_name.cid =? and code_image.owner=? "
        sql += " order by source.name"
        if case_or_file == "Case":
            sql = "select code_name.name, color, cases.name, "
            sql += "x1, y1, width, height, source.mediapath, source.id, code_image.memo  "
            sql += "from code_image join code_name on code_name.cid = code_image.cid "
            sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
            sql += "code_image.id = case_text.fid "
            sql += " join source on case_text.fid = source.id "
            sql += "where code_name.cid=? and code_image.owner=? "
            sql += " order by cases.name, code_image.owner "
        cur.execute(sql, [self.code_dict['cid'], self.app.settings['codername']])
        results = cur.fetchall()
        self.image_results = []
        keys = 'codename', 'color', 'file_or_casename', 'x1', 'y1', 'width', 'height', 'mediapath', 'fid', 'memo'
        for row in results:
            self.image_results.append(dict(zip(keys, row)))
        # Image - textEdit insertion
        for counter, row in enumerate(self.image_results):
            row['file_or_case'] = case_or_file
            row['textedit_start'] = len(self.te.toPlainText())
            fgc = "; color:" + TextColor(row['color']).recommendation + ";"
            title = '<p><span style=\"background-color:' + row['color'] + fgc + '\">'
            if case_or_file == "Case":
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
        sql += "source.mediapath, source.id from code_av join code_name "
        sql += "on code_name.cid = code_av.cid join source on code_av.id = source.id "
        sql += "where code_name.cid =? and code_av.owner=? "
        sql += " order by source.name"
        if case_or_file == "Case":
            sql = "select code_name.name, color, cases.name, code_av.pos0, code_av.pos1, code_av.memo, "
            sql += "source.mediapath, source.id from "
            sql += "code_av join code_name on code_name.cid = code_av.cid "
            sql += "join (case_text join cases on cases.caseid = case_text.caseid) on "
            sql += "code_av.id = case_text.fid "
            sql += " join source on case_text.fid = source.id "
            sql += "where code_name.cid=? and code_av.owner=? "
            sql += " order by source.name, code_av.owner "
        cur.execute(sql, [self.code_dict['cid'], self.app.settings['codername']])
        results = cur.fetchall()
        self.av_results = []
        keys = 'codename', 'color', 'file_or_casename', 'pos0', 'pos1', 'memo', 'mediapath', 'fid'
        for row in results:
            self.av_results.append(dict(zip(keys, row)))
        # A/V - textEdit insertion
        for row in self.av_results:
            row['file_or_case'] = case_or_file
            row['textedit_start'] = len(self.te.toPlainText())
            fgc = "; color:" + TextColor(row['color']).recommendation + ";"
            title = '<span style=\"background-color:' + row['color'] + fgc + '\">'
            if case_or_file == "Case":
                title += _("Case: ") + row['file_or_casename'] + _(" File: ") + row['mediapath']
            else:
                title += _("File: ") + row['mediapath']
            title += '</span>'
            self.te.insertHtml(title)
            start = msecs_to_mins_and_secs(row['pos0'])
            end = msecs_to_mins_and_secs(row['pos1'])
            self.te.insertHtml('<br />[' + start + ' - ' + end + '] ')
            row['textedit_end'] = len(self.te.toPlainText())
            self.te.append("Memo: " + row['memo'] + "\n\n")
        self.te.cursorPositionChanged.connect(self.show_context_of_clicked_heading)
        self.exec()

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
            if pos >= row['textedit_start'] and pos < row['textedit_end']:
                ui = DialogCodeInText(self.app, row)
                ui.exec()
                return
        # Check the position for an image result
        for row in self.image_results:
            if pos >= row['textedit_start'] and pos < row['textedit_end']:
                ui = DialogCodeInImage(self.app, row)
                ui.exec()
                return
        # Check the position for an a/v result
        for row in self.av_results:
            if pos >= row['textedit_start'] and pos < row['textedit_end']:
                ui = DialogCodeInAV(self.app, row)
                ui.exec()
                break

    def text_edit_menu(self, position):
        """ Context menu for textEdit.
        Mark, unmark, annotate. """

        cursor = self.te.cursorForPosition(position)
        pos = cursor.position()
        # Check the clicked position for a text result
        item = None
        for row in self.text_results:
            if pos >= row['textedit_start'] and pos < row['textedit_end']:
                item = {'type': 'text', 'res': row}
                break
        # Check the position for an image result
        for row in self.image_results:
            if pos >= row['textedit_start'] and pos < row['textedit_end']:
                item = {'type': 'image', 'res': row}
                break
        # Check the position for an a/v result
        for row in self.av_results:
            if pos >= row['textedit_start'] and pos < row['textedit_end']:
                item = {'type': 'av', 'res': row}
                break
        if not item:
            return
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_annotate = None
        action_code_memo = None
        action_end_pos = None
        action_start_pos = None
        action_mark = menu.addAction(_("Add another code"))
        action_change_code = None
        action_unmark = menu.addAction(_("Remove code"))
        action = menu.exec(self.te.mapToGlobal(position))
        if action is None:
            return
        print(item)
        if action == action_mark:
            pass
        if action == action_unmark:
            pass