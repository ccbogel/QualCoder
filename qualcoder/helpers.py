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
import platform
import sys
import traceback

from PyQt6 import QtCore, QtGui, QtWidgets

import qualcoder.vlc as vlc
from .color_selector import TextColor
from .GUI.ui_dialog_code_context_image import Ui_Dialog_code_context_image
from .GUI.ui_dialog_start_and_end_marks import Ui_Dialog_StartAndEndMarks


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


def msecs_to_mins_and_secs(msecs):
    """ Convert milliseconds to minutes and seconds.
    msecs is an integer. Minutes and seconds output is a string."""

    secs = int(msecs / 1000)
    mins = int(secs / 60)
    remainder_secs = str(secs - mins * 60)
    if len(remainder_secs) == 1:
        remainder_secs = "0" + remainder_secs
    return str(mins) + "." + remainder_secs


def msecs_to_hours_mins_secs(msecs):
    """ Convert milliseconds to hours, minutes and seconds.
    msecs is an integer. Hours, minutes and seconds output is a string."""

    secs = int(msecs / 1000)
    mins = int(secs / 60)
    remainder_secs = str(secs - mins * 60)
    if len(remainder_secs) == 1:
        remainder_secs = "0" + remainder_secs
    hours = int(mins / 60)
    remainder_mins = str(mins - hours * 60)
    if len(remainder_mins) == 1:
        remainder_mins = "0" + remainder_mins
    hours = str(hours)
    if len(hours) == 1:
        hours = "0" + hours
    res = hours + "." + remainder_mins + "." + remainder_secs
    return res


def file_typer(mediapath):
    """ Take the source mediapath and return type as: text, audio, video, image
    Required function as this is a historical quirk of development
    param:
        mediapath: String containing the mediapath
    """

    if mediapath is None:
        return "text"
    if len(mediapath) < 3:
        return "text"
    mediapath = mediapath.lower()
    if mediapath[-3:] in ('jpg', 'png'):
        return "image"
    if len(mediapath) > 4 and mediapath[-4:] == 'jpeg':
        return "image"
    if mediapath[-3:] in ('mp3', 'wav', 'm4a'):
        return "audio"
    if mediapath[-3:] in ('mkv', 'mov', 'mp4', 'ogg', 'wmv'):
        return "video"
    return "text"


class Message(QtWidgets.QMessageBox):
    """ This is called a lot , but is styled to font size """

    def __init__(self, app, title, text, icon=None):
        QtWidgets.QMessageBox.__init__(self)

        self.setStyleSheet("* {font-size:" + str(app.settings['fontsize']) + "pt} ")
        self.setWindowTitle(title)
        self.setText(text)
        if icon == "warning":
            self.setIcon(QtWidgets.QMessageBox.Icon.Warning)
        if icon == "Information":
            self.setIcon(QtWidgets.QMessageBox.Icon.Information)
        if icon == "critical":
            self.setIcon(QtWidgets.QMessageBox.Icon.Critical)


class ExportDirectoryPathDialog:
    """ Dialog to get export directory path, but also to check for existing file.
    If an existing file found, add a counter to the file name until a new file name is made.
     Counter in format _1, _2, etc. """

    filepath = None

    def __init__(self, app, filename):
        """ params:
                    app : App class
                    filename: String of filename with extension only"""

        extension = filename.split('.')[-1]
        filename_only = filename[0:-len(extension) - 1]
        options = QtWidgets.QFileDialog.Option.DontResolveSymlinks | QtWidgets.QFileDialog.Option.ShowDirsOnly
        directory = QtWidgets.QFileDialog.getExistingDirectory(None,
                                                               _("Select directory to save file"),
                                                               app.last_export_directory, options)
        if directory:
            if directory != app.last_export_directory:
                app.last_export_directory = directory
            self.filepath = directory + "/" + filename_only + "." + extension
            counter = 0
            while os.path.exists(self.filepath):
                self.filepath = directory + "/" + filename_only + "_" + str(counter) + "." + extension
                counter += 1
        else:
            self.filepath = None


class DialogGetStartAndEndMarks(QtWidgets.QDialog):
    """ This dialog gets the start and end mark text to allow text to be
    automatically assigned to the currently selected case or a code to be assigned when coding text.
    It requires the name of the selected case and filename(s) - for display purposes only.
    Methods return the user's choices for the startmark text and the endmark text.
    Called by:
        case_file_manager, code_text.
    """

    title = ""

    def __init__(self, title, filenames):
        """ title is a String. Filenames is a String """

        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_StartAndEndMarks()
        self.ui.setupUi(self)
        self.ui.label_title.setText(title)
        self.ui.label_files.setText(filenames)

    def get_start_mark(self):
        return str(self.ui.lineEdit_startmark.text())

    def get_end_mark(self):
        return str(self.ui.lineEdit_endmark.text())


class DialogCodeInText(QtWidgets.QDialog):
    """ View the coded text in context of the original text file in a modal dialog.
    Called by: reports.DialogReportCodes after results are produced
    """

    app = None
    data = None
    te = None

    def __init__(self, app, data, parent=None):
        """ Prepare QDialog window.
        param:
            data : dictionary: codename, color, file_or_casename, pos0, pos1, text, coder, fid, file_or_case,
                textedit_start, textedit_end
            app : class containing app details such as database connection
        """

        sys.excepthook = exception_handler
        self.app = app
        self.data = data
        QtWidgets.QDialog.__init__(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['docfontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.resize(400, 300)
        file_list = self.app.get_file_texts([data['fid'], ])
        file_text = file_list[0]
        title = ""
        if data['file_or_case'] == "File":
            title = _("File: ") + data['file_or_casename']
        if data['file_or_case'] == "Case":
            title = _("Case: ") + data['file_or_casename'] + ", " + file_text['name']
        self.setWindowTitle(title)
        self.te = QtWidgets.QTextEdit()
        self.te.setStyleSheet(font)
        self.te.setPlainText(file_text['fulltext'])
        self.te.ensureCursorVisible()
        grid_layout = QtWidgets.QGridLayout(self)
        grid_layout.addWidget(self.te, 1, 0)
        self.resize(400, 300)
        cursor = self.te.textCursor()
        cursor.setPosition(data['pos0'], QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(data['pos1'], QtGui.QTextCursor.MoveMode.KeepAnchor)
        fmt = QtGui.QTextCharFormat()
        brush = QtGui.QBrush(QtGui.QColor(data['color']))
        fmt.setBackground(brush)
        text_brush = QtGui.QBrush(QtGui.QColor(TextColor(data['color']).recommendation))
        fmt.setForeground(text_brush)
        fmt.setFontUnderline(True)
        fmt.setUnderlineColor(QtGui.QColor(data['color']))
        cursor.setCharFormat(fmt)
        # Make marked text visible in view.
        text_cursor = self.te.textCursor()
        cur_pos = data['pos1']
        text_cursor.setPosition(cur_pos)
        self.te.setTextCursor(text_cursor)
        self.te.setReadOnly(True)

    def add_coded_text(self, data):
        """ Add a second coded segment to the text.
        Merge with the original. The original has an underline which is merged into this new format.
        Called in report_relations.show_context """

        cursor = self.te.textCursor()
        cursor.setPosition(data['pos0'], QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(data['pos1'], QtGui.QTextCursor.MoveMode.KeepAnchor)
        fmt = QtGui.QTextCharFormat()
        brush = QtGui.QBrush(QtGui.QColor(data['color']))
        fmt.setBackground(brush)
        text_brush = QtGui.QBrush(QtGui.QColor(TextColor(data['color']).recommendation))
        fmt.setForeground(text_brush)
        cursor.mergeCharFormat(fmt)
        # Make marked text visible, in view.
        text_cursor = self.te.textCursor()
        cur_pos = data['pos1']
        text_cursor.setPosition(cur_pos)


class DialogCodeInAllFiles(QtWidgets.QDialog):
    """ Display all coded media for this code, in a modal dialog.
    Coded media comes from ALL files for this coder.
    Need to store textedit start and end positions so that code in context can be used.
    Called from code_text, code_av, code_image.
    """

    app = None
    code_dict = None
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
        msg = _("Click on heading for coding in context") + "\n\n"
        self.te.append(msg)

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


class DialogCodeInAV(QtWidgets.QDialog):
    """ View coded section in original image.
    Scalable and scrollable image. The slider values range from 10 to 99.

    Called by: reports.DialogReportCodes after results are produced
    """

    app = None
    data = None
    frame = None

    def __init__(self, app, data, parent=None):
        """ View audio/video segment in a dialog window.
        mediapath may be a link as: 'video:path'
        param:
            app : class containing app details such as database connection
            data : dictionary {codename, color, file_or_casename, pos0, pos1, coder, text,
                    mediapath, fid, memo, file_or_case}
        """

        sys.excepthook = exception_handler
        self.app = app
        self.data = data
        QtWidgets.QDialog.__init__(self)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.resize(400, 300)
        # Enable custom window hint to enable customizing window controls
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowType.CustomizeWindowHint)
        self.setWindowTitle(self.data['file_or_casename'])
        self.gridLayout = QtWidgets.QGridLayout(self)
        self.frame = QtWidgets.QFrame(self)
        if platform.system() == "Darwin":  # for MacOS
            self.frame = QtWidgets.QMacCocoaViewContainer(0)
        self.gridLayout.addWidget(self.frame, 0, 0, 0, 0)
        # Create a vlc instance with an empty vlc media player
        # https://stackoverflow.com/questions/55339786/how-to-turn-off-vlcpulse-audio-from-python-program
        self.instance = vlc.Instance()
        self.mediaplayer = self.instance.media_player_new()
        self.mediaplayer.video_set_mouse_input(False)
        self.mediaplayer.video_set_key_input(False)
        # Load media
        try:
            if self.data['mediapath'][0:6] in ('/audio', '/video'):
                self.media = self.instance.media_new(self.app.project_path + self.data['mediapath'])
            if self.data['mediapath'][0:6] in ('audio:', 'video:'):
                self.media = self.instance.media_new(self.data['mediapath'][6:])
        except Exception as e:
            Message(self.app, _('Media not found'), str(e) + "\n" + self.app.project_path + self.data['mediapath'],
                    "warning").exec()
            self.close()
            return
        self.mediaplayer.set_media(self.media)
        # Parse the metadata of the file
        self.media.parse()
        self.mediaplayer.video_set_mouse_input(False)
        self.mediaplayer.video_set_key_input(False)
        # The media player has to be connected to the QFrame (otherwise the
        # video would be displayed in it's own window). This is platform
        # specific, so we must give the ID of the QFrame (or similar object) to
        # vlc. Different platforms have different functions for this
        if platform.system() == "Linux":  # for Linux using the X Server
            # self.mediaplayer.set_xwindow(int(self.ui.frame.winId()))
            self.mediaplayer.set_xwindow(int(self.frame.winId()))
        elif platform.system() == "Windows":  # for Windows
            self.mediaplayer.set_hwnd(int(self.winId()))
        elif platform.system() == "Darwin":  # for MacOS
            self.mediaplayer.set_nsobject(int(self.winId()))

        # The vlc MediaPlayer needs a float value between 0 and 1 for AV position,
        pos = self.data['pos0'] / self.mediaplayer.get_media().get_duration()
        self.mediaplayer.play()  # Need to start play first
        self.mediaplayer.set_position(pos)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_ui)
        self.timer.start()

    def update_ui(self):
        """ Checks for end of playing segment. """

        msecs = self.mediaplayer.get_time()
        msg = msecs_to_mins_and_secs(msecs)
        try:
            msg += "\n" + _("Memo: ") + self.data['memo']
        except KeyError:
            pass
        self.setToolTip(msg)
        if self.data['pos1'] < msecs:
            self.mediaplayer.stop()

    def closeEvent(self, event):
        self.mediaplayer.stop()


class DialogCodeInImage(QtWidgets.QDialog):
    """ View coded section in original image.

    Called by: reports.DialogReportCodes qhn results are produced
    """

    app = None
    data = None
    pixmap = None
    label = None
    scale = None
    scene = None

    def __init__(self, app, data, parent=None):
        """ Image_data contains: {name, mediapath, owner, id, date, memo, fulltext}
        mediapath may be a link as: 'images:path'
        param:
            app : class containing app details such as database connection
            data : dictionary {codename, color, file_or_casename, x1, y1, width, height, coder,
                    mediapath, fid, memo, file_or_case}
        """

        sys.excepthook = exception_handler
        self.app = app
        self.data = data
        self.scale = 1
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_code_context_image()
        self.ui.setupUi(self)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        abs_path = ""
        if "images:" in self.data['mediapath']:
            abs_path = self.data['mediapath'].split(':')[1]
        else:
            abs_path = self.app.project_path + self.data['mediapath']
        self.setWindowTitle(abs_path)
        image = QtGui.QImage(abs_path)
        if image.isNull():
            Message(self.app, _('Image error'), _("Cannot open: ") + abs_path, "warning").exec()
            self.close()
            return
        self.scene = QtWidgets.QGraphicsScene()
        self.ui.graphicsView.setScene(self.scene)
        self.ui.graphicsView.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.installEventFilter(self)

        self.pixmap = QtGui.QPixmap.fromImage(image)
        self.pixmap = QtGui.QPixmap.fromImage(image)
        pixmap_item = QtWidgets.QGraphicsPixmapItem(QtGui.QPixmap.fromImage(image))
        pixmap_item.setPos(0, 0)
        self.scene.setSceneRect(QtCore.QRectF(0, 0, self.pixmap.width(), self.pixmap.height()))
        self.scene.addItem(pixmap_item)
        self.ui.horizontalSlider.setValue(99)

        self.ui.scrollArea.setWidget(self.label)
        self.ui.scrollArea.resize(self.pixmap.width(), self.pixmap.height())
        self.ui.horizontalSlider.valueChanged[int].connect(self.change_scale)
        # Scale initial picture by height to mostly fit inside scroll area
        # Tried other methods e.g. sizes of components, but nothing was correct.
        if self.pixmap.height() > self.height() - 30 - 80:  # slider 30 and textedit 80 heights
            self.scale = (self.height() - 30 - 80) / self.pixmap.height()
            slider_value = int(self.scale * 100)
            if slider_value > 100:
                slider_value = 100
            self.ui.horizontalSlider.setValue(slider_value)
        self.draw_coded_area()

    def draw_coded_area(self):
        """ Draw the coded rectangle in the scene.
         The coded memo can be in the data as ['memo'] if data from DialogCodeText, DialogCodeImage, DialogCodeAV
         It is in the data as ['coded memo'] if data from DialogReportCodes
         DialogReportCodes can produce various memos on output: source memo, coded memo, codename memo
         """

        tooltip = self.data['codename']
        try:
            tooltip += "\nMemo: " + self.data['memo']
        except KeyError:
            pass
        try:
            tooltip += "\nMemo: " + self.data['coded memo']
        except KeyError:
            pass
        x = self.data['x1'] * self.scale
        y = self.data['y1'] * self.scale
        width = self.data['width'] * self.scale
        height = self.data['height'] * self.scale
        rect_item = QtWidgets.QGraphicsRectItem(x, y, width, height)
        rect_item.setPen(QtGui.QPen(QtGui.QColor(self.data['color']), 2, QtCore.Qt.PenStyle.DashLine))
        rect_item.setToolTip(tooltip)
        self.scene.addItem(rect_item)

    def change_scale(self):
        """ Resize image. Triggered by user change in slider.
        Also called by unmark, as all items need to be redrawn. """

        if self.pixmap is None:
            return
        self.scale = (self.ui.horizontalSlider.value() + 1) / 100
        height = self.scale * self.pixmap.height()
        pixmap = self.pixmap.scaledToHeight(height, QtCore.Qt.TransformationMode.FastTransformation)
        pixmap_item = QtWidgets.QGraphicsPixmapItem(pixmap)
        pixmap_item.setPos(0, 0)
        self.scene.clear()
        self.scene.addItem(pixmap_item)
        self.draw_coded_area()
        self.ui.horizontalSlider.setToolTip(_("Scale: ") + str(int(self.scale * 100)) + "%")

    def eventFilter(self, object, event):
        """ Using this event filter to identify treeWidgetItem drop events.
        http://doc.qt.io/qt-5/qevent.html#Type-enum
        QEvent::Drop	63	A drag and drop operation is completed (QDropEvent).
        https://stackoverflow.com/questions/28994494/why-does-qtreeview-not-fire-a-drop-or-move-event-during-drag-and-drop
        Also use eventFilter for QGraphicsView.

        Key events on scene
        minus reduce the scale
        plus increase the scale
        """

        if type(event) == QtGui.QKeyEvent:
            key = event.key()
            mod = event.modifiers()
            if key == QtCore.Qt.Key.Key_Minus:
                v = self.ui.horizontalSlider.value()
                v -= 3
                if v < self.ui.horizontalSlider.minimum():
                    return True
                self.ui.horizontalSlider.setValue(v)
                return True
            if key == QtCore.Qt.Key.Key_Plus:
                v = self.ui.horizontalSlider.value()
                v += 3
                if v > self.ui.horizontalSlider.maximum():
                    return True
                self.ui.horizontalSlider.setValue(v)
                return True
        return False
