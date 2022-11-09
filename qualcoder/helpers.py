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
import logging
import os
import platform
import sys
import traceback

from PyQt6 import QtCore, QtGui, QtWidgets

from .color_selector import TextColor
from .GUI.ui_dialog_code_context_image import Ui_Dialog_code_context_image
from .GUI.ui_dialog_start_and_end_marks import Ui_Dialog_StartAndEndMarks

# If VLC not installed, it will not crash
vlc = None
try:
    import vlc
except Exception as e:
    print(e)


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

    Called by: DialogCodeInAllFiles.show_context_of_clicked_heading,
    reports.DialogReportCodes, when results are produced
    """

    app = None
    data = None
    te = None
    code_resize_timer = 0
    event_filter_on = True

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
        self.code_resize_timer = datetime.datetime.now()
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
        self.te.installEventFilter(self)
        self.te.setReadOnly(True)
        grid_layout = QtWidgets.QGridLayout(self)
        grid_layout.addWidget(self.te, 1, 0)
        self.resize(400, 300)
        self.draw_initial_coded_text()
        # Make marked text visible in view.
        text_cursor = self.te.textCursor()
        cur_pos = self.data['pos1']
        text_cursor.setPosition(cur_pos)
        self.te.setTextCursor(text_cursor)
        if self.event_filter_on:
            tt = _("Resize coding\nAlt+Left Arrow, Alt+Right Arrow\nShift+LeftArrow, Shift+Right Arrow")
            self.te.setToolTip(tt)

    def draw_initial_coded_text(self):
        """ Can be called multiple times via keystrokes, so  initally set formatting to none. """

        cursor = self.te.textCursor()
        cursor.setPosition(0, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(len(self.te.toPlainText()) - 1, QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(QtGui.QTextCharFormat())

        cursor.setPosition(self.data['pos0'], QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(self.data['pos1'], QtGui.QTextCursor.MoveMode.KeepAnchor)
        fmt = QtGui.QTextCharFormat()
        brush = QtGui.QBrush(QtGui.QColor(self.data['color']))
        fmt.setBackground(brush)
        text_brush = QtGui.QBrush(QtGui.QColor(TextColor(self.data['color']).recommendation))
        fmt.setForeground(text_brush)
        fmt.setFontUnderline(True)
        fmt.setUnderlineColor(QtGui.QColor(self.data['color']))
        cursor.setCharFormat(fmt)

    def add_coded_text(self, data):
        """ Add a second coded segment to the text.
        Merge with the original. The original has an underline which is merged into this new format.
        Called in report_relations.show_context """

        self.event_filter_on = False
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

    def eventFilter(self, object_, event):
        """ To detect key events in the textedit.
        These are used to extend or shrink a text coding.
        Only works if clicked on a code (text cursor is in the coded text).
        Shrink start and end code positions using alt arrow left and alt arrow right
        Extend start and end code positions using shift arrow left, shift arrow right
        """

        if not self.event_filter_on:
            return
        # Change start and end code positions using alt arrow left and alt arrow right
        # and shift arrow left, shift arrow right
        # QtGui.QKeyEvent = 7
        if type(event) == QtGui.QKeyEvent and self.te.hasFocus():
            key = event.key()
            mod = event.modifiers()
            # using timer for a lot of things
            now = datetime.datetime.now()
            diff = now - self.code_resize_timer
            if diff.microseconds < 100000:
                return False
            # Key event can be too sensitive, adjusted  for 150 millisecond gap
            self.code_resize_timer = datetime.datetime.now()
            if key == QtCore.Qt.Key.Key_Left and mod == QtCore.Qt.KeyboardModifier.AltModifier:
                self.shrink_to_left()
                return True
            if key == QtCore.Qt.Key.Key_Right and mod == QtCore.Qt.KeyboardModifier.AltModifier:
                self.shrink_to_right()
                return True
            if key == QtCore.Qt.Key.Key_Left and mod == QtCore.Qt.KeyboardModifier.ShiftModifier:
                self.extend_left()
                return True
            if key == QtCore.Qt.Key.Key_Right and mod == QtCore.Qt.KeyboardModifier.ShiftModifier:
                self.extend_right()
                return True
        return False

    def extend_left(self):
        """ Shift left arrow. """

        if self.data['pos0'] < 1:
            return
        self.data['pos0'] -= 1
        cur = self.app.conn.cursor()
        text_sql = "select substr(fulltext,?,?) from source where id=?"
        cur.execute(text_sql, [self.data['pos0'] + 1, self.data['pos1'] - self.data['pos0'], self.data['fid']])
        seltext = cur.fetchone()[0]
        sql = "update code_text set pos0=?, seltext=? where ctid=?"
        cur.execute(sql, (self.data['pos0'], seltext, self.data['ctid']))
        self.app.conn.commit()
        self.draw_initial_coded_text()

    def extend_right(self):
        """ Shift right arrow. """

        if self.data['pos1'] + 1 >= len(self.te.toPlainText()):
            return
        self.data['pos1'] += 1
        cur = self.app.conn.cursor()
        text_sql = "select substr(fulltext,?,?) from source where id=?"
        cur.execute(text_sql, [self.data['pos0'] + 1, self.data['pos1'] - self.data['pos0'], self.data['fid']])
        seltext = cur.fetchone()[0]
        sql = "update code_text set pos1=?, seltext=? where ctid=?"
        cur.execute(sql,
                    (self.data['pos1'], seltext, self.data['ctid']))
        self.app.conn.commit()
        self.draw_initial_coded_text()

    def shrink_to_left(self):
        """ Alt left arrow, shrinks code from the right end of the code. """

        if self.data['pos1'] <= self.data['pos0'] + 1:
            return
        self.data['pos1'] -= 1
        cur = self.app.conn.cursor()
        text_sql = "select substr(fulltext,?,?) from source where id=?"
        cur.execute(text_sql, [self.data['pos0'] + 1, self.data['pos1'] - self.data['pos0'], self.data['fid']])
        seltext = cur.fetchone()[0]
        sql = "update code_text set pos1=?, seltext=? where ctid=?"
        cur.execute(sql, (self.data['pos1'], seltext, self.data['ctid']))
        self.app.conn.commit()
        self.draw_initial_coded_text()

    def shrink_to_right(self):
        """ Alt right arrow shrinks code from the left end of the code. """

        if self.data['pos0'] >= self.data['pos1'] - 1:
            return
        self.data['pos0'] += 1
        cur = self.app.conn.cursor()
        text_sql = "select substr(fulltext,?,?) from source where id=?"
        cur.execute(text_sql, [self.data['pos0'] + 1, self.data['pos1'] - self.data['pos0'], self.data['fid']])
        seltext = cur.fetchone()[0]
        sql = "update code_text set pos0=?, seltext=? where ctid=?"
        cur.execute(sql, (self.data['pos0'], seltext, self.data['ctid']))
        self.app.conn.commit()
        self.draw_initial_coded_text()


class DialogCodeInAV(QtWidgets.QDialog):
    """ View coded section in original image.
    Scalable and scrollable image. The slider values range from 10 to 99.

    Called by: DialogCodeInAllFiles.show_context_of_clicked_heading,
    reports.DialogReportCodes, when results are produced
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
        if platform.system() == "Darwin":  # for macOS
            self.frame = QtWidgets.QMacCocoaViewContainer(0)
        self.gridLayout.addWidget(self.frame, 0, 0, 0, 0)
        if not vlc:
            return
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
        except Exception as err:
            logger.warning((str(err)))
            print(err)
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
        elif platform.system() == "Darwin":  # for macOS
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

    Called by: DialogCodeInAllFiles.show_context_of_clicked_heading,
    reports.DialogReportCodes, when results are produced
    """

    app = None
    data = None
    pixmap = None
    label = None
    scale = None
    scene = None
    degrees = 0
    export_key_timer = 0

    def __init__(self, app, data, parent=None):
        """ Image_data contains details to show the image and the coded section.
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
        self.export_key_timer = datetime.datetime.now()
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
        tt = _("L rotate clockwise\nR rotate anti-clockwise\n+ - zoom in and out\nE Export Image")
        self.ui.graphicsView.setToolTip(tt)
        self.ui.graphicsView.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.installEventFilter(self)
        self.pixmap = QtGui.QPixmap.fromImage(image)
        self.ui.horizontalSlider.setValue(99)
        self.ui.horizontalSlider.setToolTip(_("Key + or W zoom in. Key - or Q zoom out"))
        self.ui.scrollArea.setWidget(self.label)
        self.ui.horizontalSlider.valueChanged[int].connect(self.draw_scene)
        # Scale initial picture by height to mostly fit inside scroll area
        # Tried other methods e.g. sizes of components, but nothing was correct.
        if self.pixmap.height() > self.height() - 30 - 80:  # slider 30 and textedit 80 heights
            self.scale = (self.height() - 30 - 80) / self.pixmap.height()
            slider_value = int(self.scale * 100)
            if slider_value > 100:
                slider_value = 100
            self.ui.horizontalSlider.setValue(slider_value)
        self.draw_scene()

    def draw_coded_area(self):
        """ Draw the coded rectangle in the scene.
         The coded memo can be in the data as ['memo'] if data from DialogCodeText, DialogCodeImage, DialogCodeAV
         It is in the data as ['coded memo'] if data from DialogReportCodes.
         DialogReportCodes can produce various memos on output: source memo, coded memo, codename memo.
         Called by: draw_scene
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

        # Degrees 0
        x = self.data['x1'] * self.scale
        y = self.data['y1'] * self.scale
        width = self.data['width'] * self.scale
        height = self.data['height'] * self.scale
        if self.degrees == 90:
            y = (self.data['x1']) * self.scale
            x = (self.pixmap.height() - self.data['y1'] - self.data['height']) * self.scale
            height = self.data['width'] * self.scale
            width = self.data['height'] * self.scale
        if self.degrees == 180:
            x = (self.pixmap.width() - self.data['x1'] - self.data['width']) * self.scale
            y = (self.pixmap.height() - self.data['y1'] - self.data['height']) * self.scale
            width = self.data['width'] * self.scale
            height = self.data['height'] * self.scale
        if self.degrees == 270:
            y = (self.pixmap.width() - self.data['x1'] - self.data['width']) * self.scale
            x = (self.data['y1']) * self.scale
            height = self.data['width'] * self.scale
            width = self.data['height'] * self.scale

        rect_item = QtWidgets.QGraphicsRectItem(x, y, width, height)
        rect_item.setPen(QtGui.QPen(QtGui.QColor(self.data['color']), 2, QtCore.Qt.PenStyle.DashLine))
        rect_item.setToolTip(tooltip)
        self.scene.addItem(rect_item)

    def draw_scene(self):
        """ Resize image. Triggered by user change in slider or + - keys
        Called by: draw_scene
        """

        if self.pixmap is None:
            return
        self.scale = (self.ui.horizontalSlider.value() + 1) / 100
        height = int(self.scale * self.pixmap.height())
        pixmap = self.pixmap.scaledToHeight(height, QtCore.Qt.TransformationMode.FastTransformation)
        transform = QtGui.QTransform().rotate(self.degrees)
        pixmap = pixmap.transformed(transform)
        pixmap_item = QtWidgets.QGraphicsPixmapItem(pixmap)
        pixmap_item.setPos(0, 0)
        self.scene.setSceneRect(QtCore.QRectF(0, 0, pixmap.width(), pixmap.height()))
        self.ui.scrollArea.resize(pixmap.width(), pixmap.height())
        self.scene.clear()
        self.scene.addItem(pixmap_item)
        self.draw_coded_area()
        self.ui.graphicsView.update()
        msg = _("Key + or W zoom in. Key - or Q zoom out") + "\n"
        msg += _("Scale: ") + str(int(self.scale * 100)) + "%"
        self.ui.horizontalSlider.setToolTip(msg)

    def eventFilter(self, object_, event):
        """ Using this event filter for QGraphicsView.

        Key events on scene
        - reduce the scale
        + increase the scale
        L rotate left
        R rotate right
        E Export image
        """

        if type(event) == QtGui.QKeyEvent:
            key = event.key()
            # mod = event.modifiers()
            if key == QtCore.Qt.Key.Key_Minus or key == QtCore.Qt.Key.Key_Q:
                v = self.ui.horizontalSlider.value()
                v -= 3
                if v < self.ui.horizontalSlider.minimum():
                    return True
                self.ui.horizontalSlider.setValue(v)
                return True
            if key == QtCore.Qt.Key.Key_Plus or key == QtCore.Qt.Key.Key_W:
                v = self.ui.horizontalSlider.value()
                v += 3
                if v > self.ui.horizontalSlider.maximum():
                    return True
                self.ui.horizontalSlider.setValue(v)
                return True
            if key == QtCore.Qt.Key.Key_R:
                self.degrees -= 90
                if self.degrees < 0:
                    self.degrees = 270
                self.draw_scene()
                return True
            if key == QtCore.Qt.Key.Key_L:
                self.degrees += 90
                if self.degrees > 270:
                    self.degrees = 0
                self.draw_scene()
                return True
            if key == QtCore.Qt.Key.Key_E:
                # Prevent E key event double-activating
                now = datetime.datetime.now()
                overlap_diff = now - self.export_key_timer
                if overlap_diff.total_seconds() > 2:
                    self.export_image()
                self.export_key_timer = datetime.datetime.now()
                return True
        return False

    def export_image(self):
        """ Export the QGraphicsScene as a png image with transparent background.
        Called by QButton_export.
        """

        filename = "Image_with_code.png"
        e_dir = ExportDirectoryPathDialog(self.app, filename)
        filepath = e_dir.filepath
        if filepath is None:
            return
        width = self.scene.sceneRect().width()
        height = self.scene.sceneRect().height()
        rect_area = QtCore.QRectF(0.0, 0.0, width, height)
        image = QtGui.QImage(int(width), int(height), QtGui.QImage.Format.Format_ARGB32_Premultiplied)
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        # Render method requires QRectF NOT QRect
        self.scene.render(painter, QtCore.QRectF(image.rect()), rect_area)
        painter.end()
        image.setText("Description", self.data['codename'])
        image.save(filepath)
        Message(self.app, _("Image exported"), filepath).exec()
