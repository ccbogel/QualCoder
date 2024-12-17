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

import csv
import datetime
import logging
import os
import platform
from random import randint
import sqlite3

from PyQt6 import QtCore, QtGui, QtWidgets

from .color_selector import TextColor, colors
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


def msecs_to_mins_and_secs(msecs):
    """ Convert milliseconds to minutes and seconds.
    msecs is an integer. Minutes and seconds output is a string."""

    secs = int(msecs / 1000)
    mins = int(secs / 60)
    remainder_secs = str(secs - mins * 60)
    if len(remainder_secs) == 1:
        remainder_secs = f"0{remainder_secs}"
    return f"{mins}.{remainder_secs}"


def msecs_to_hours_mins_secs(msecs):
    """ Convert milliseconds to hours, minutes and seconds.
    msecs is an integer. Hours, minutes and seconds output is a string."""

    secs = int(msecs / 1000)
    mins = int(secs / 60)
    remainder_secs = str(secs - mins * 60)
    if len(remainder_secs) == 1:
        remainder_secs = f"0{remainder_secs}"
    hours = int(mins / 60)
    remainder_mins = str(mins - hours * 60)
    if len(remainder_mins) == 1:
        remainder_mins = f"0{remainder_mins}"
    hours = str(hours)
    if len(hours) == 1:
        hours = f"0{hours}"
    res = hours + f".{remainder_mins}.{remainder_secs}"
    return res


def file_typer(mediapath):
    """ Take the source mediapath and return type as: text, audio, video, image
    Required function as this is a historical quirk of development
    param:
        mediapath: String containing the mediapath
    """

    if mediapath is None:
        return "text"
    if len(mediapath) < 6:
        return "text"
    if len(mediapath) > 5 and mediapath[:6] == "/docs/" or mediapath[:5] == "docs:":
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

        self.setStyleSheet(f"* {{font-size:{app.settings['fontsize']}pt}} ")
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
                self.filepath = directory + f"/{filename_only}_{counter}.{extension}"
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

    def __init__(self, app, data):
        """ Prepare QDialog window.
        param:
            data : dictionary: codename, color, file_or_casename, pos0, pos1, text, coder, fid, file_or_case,
                textedit_start, textedit_end
            app : class containing app details such as database connection
        """

        self.app = app
        self.data = data
        self.code_resize_timer = datetime.datetime.now()
        QtWidgets.QDialog.__init__(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f"font: {self.app.settings['docfontsize']}pt "
        font += f'"{self.app.settings["font"]}";'
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
            return False
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

    def __init__(self, app, data):
        """ View audio/video segment in a dialog window.
        mediapath may be a link as: 'video:path'
        param:
            app : class containing app details such as database connection
            data : dictionary {codename, color, file_or_casename, pos0, pos1, coder, text,
                    mediapath, fid, memo, file_or_case}
        """

        self.app = app
        self.data = data
        QtWidgets.QDialog.__init__(self)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.resize(400, 300)
        # Enable custom window hint to enable customising window controls
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.WindowType.CustomizeWindowHint)
        self.setWindowTitle(self.data['file_or_casename'])
        self.gridLayout = QtWidgets.QGridLayout(self)
        self.frame = QtWidgets.QFrame(self)
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
            msg = f"{err}\n{self.app.project_path}{self.data['mediapath']}"
            logger.warning(msg)
            print(msg)
            Message(self.app, _('Media not found'), msg,
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
            msg += f"\nMemo: {self.data['memo']}"
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

    def __init__(self, app, data):
        """ Image_data contains details to show the image and the coded section.
        mediapath may be a link as: 'images:path'
        param:
            app : class containing app details such as database connection
            data : dictionary {codename, color, file_or_casename, x1, y1, width, height, coder,
                    mediapath, fid, memo, file_or_case}
        """

        self.app = app
        self.data = data
        self.scale = 1
        self.export_key_timer = datetime.datetime.now()
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_code_context_image()
        self.ui.setupUi(self)
        font = f"font: {self.app.settings['fontsize']}pt "
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
        msg += f'{_("Scale:")} {int(self.scale * 100)}%'
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


class ImportPlainTextCodes:
    """ Import a list of plain text codes codebook.
        The codebook is a plain text file or csv file.
        In plain text file, Tab separates the codename from the code description.
        The >> symbol is used to assign code to category:
        category>>code
        category>>category>>code
        code
            """

    def __init__(self, app, text_edit):
        self.app = app
        self.text_edit = text_edit
        response = QtWidgets.QFileDialog.getOpenFileNames(None, _('Select plain text codes file'),
                                                          self.app.settings['directory'], "Text (*.txt *.csv)",
                                                          options=QtWidgets.QFileDialog.Option.DontUseNativeDialog
                                                          )
        filepath = response[0]
        if not filepath:
            self.text_edit.append(_("Codes list text file not imported"))
            return
        filepath = filepath[0]  # List to string of file path
        self.text_edit.append("\n" + _("Importing codes from: ") + filepath)
        self.text_edit.append(_("Refresh codes trees via menu options for coding, reports"))
        with open(filepath, 'r', encoding='UTF-8-sig') as file_:
            rows = []
            if filepath[-4:].lower() == ".csv":
                reader = csv.reader(file_, delimiter=",", quoting=csv.QUOTE_MINIMAL)
                for row in reader:
                    rows.append(row)
            else:
                reader = csv.reader(file_, delimiter="\t", quoting=csv.QUOTE_MINIMAL)
                for row in reader:
                    if row:
                        rows.append(row)
        cur = self.app.conn.cursor()
        # Insert categories
        for row in rows:
            categories = row[0].split(">>")
            if len(categories) < 2 or categories[0] == "":
                continue
            categories.pop()  # Remove code name
            for i, category in enumerate(categories):
                supercatid = None
                if i >= 1:
                    cur.execute("select catid from code_cat where name=?", [categories[i - 1].strip()])
                    res = cur.fetchone()
                    if res:
                        supercatid = res[0]
                try:
                    cur.execute("insert into code_cat (name,memo,owner,date,supercatid) values(?,?,?,?,?)",
                                (category.strip(), "", self.app.settings['codername'],
                                 datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), supercatid))
                    self.app.conn.commit()
                    self.text_edit.append(_("Imported category: ") + category)
                except sqlite3.IntegrityError:
                    pass
        # Insert codes
        for row in rows:
            memo = ""
            if len(row) > 1:
                memo = row[1]
            code_name = row[0].strip()  # only code name
            category_name = None
            if ">>" in code_name:
                code_name = row[0].split(">>")[-1].strip()
                category_name = row[0].split(">>")[-2].strip()
            if code_name == "":
                continue
            catid = None
            if category_name:
                cur.execute("select catid from code_cat where name=?", [category_name])
                res = cur.fetchone()
                if res:
                    catid = res[0]
            date_ = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
            color = colors[randint(0, len(colors) - 1)]
            try:
                cur.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,?,?,?,?)",
                            (code_name, memo, self.app.settings['codername'], date_, catid, color))
                self.app.conn.commit()
                self.text_edit.append(_("Imported code: ") + code_name)
            except sqlite3.IntegrityError:
                self.text_edit.append(_("Duplicate code not imported: ") + code_name)


class MarkdownHighlighter(QtGui.QSyntaxHighlighter):
    """ Text markdown highlighter. """

    highlighting_rules = []
    app = None

    def __init__(self, parent, app):
        """
        param:
            parent : QTextEdit
            app : App object
        """
        QtGui.QSyntaxHighlighter.__init__(self, parent)
        self.parent = parent
        self.app = app
        self.highlighting_rules = []
        self.rules()

    def rules(self):
        """ Sets formatting rules for markdown text.
        H1 H2 H3 bold and italic
        """

        # Heading 1
        h1_format = QtGui.QTextCharFormat()
        h1_format.setFontPointSize(self.app.settings['docfontsize'] + 6)
        h1_format.setFontWeight(QtGui.QFont.Weight.Bold)
        self.highlighting_rules += [(QtCore.QRegularExpression("# [^\n]*"), h1_format)]
        # Heading 2
        h2_format = QtGui.QTextCharFormat()
        h2_format.setFontPointSize(self.app.settings['docfontsize'] + 4)
        h2_format.setFontWeight(QtGui.QFont.Weight.Bold)
        self.highlighting_rules += [(QtCore.QRegularExpression("## [^\n]*"), h2_format)]
        # Heading 3
        h3_format = QtGui.QTextCharFormat()
        h3_format.setFontPointSize(self.app.settings['docfontsize'] + 2)
        h3_format.setFontWeight(QtGui.QFont.Weight.Bold)
        self.highlighting_rules += [(QtCore.QRegularExpression("### [^\n]*"), h3_format)]
        # Italic
        italic_format = QtGui.QTextCharFormat()
        italic_format.setFontItalic(True)
        self.highlighting_rules += [(QtCore.QRegularExpression(r"\*.*\*"), italic_format)]
        # Bold
        bold_format = QtGui.QTextCharFormat()
        bold_format.setFontWeight(QtGui.QFont.Weight.Bold)
        self.highlighting_rules += [(QtCore.QRegularExpression(r"\*\*.*\*\*"), bold_format)]

    def highlightBlock(self, text):
        for pattern, format_ in self.highlighting_rules:
            reg_exp = QtCore.QRegularExpression(pattern)
            i = reg_exp.globalMatch(text)
            while i.hasNext():
                match = i.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format_)


class NumberBar(QtWidgets.QFrame):
    """
    NumberBar is a QWidget subclass providing a sidebar with line numbers
    for a QTextEdit widget. It visually aligns with the text editor to
    display line numbers alongside text content, offering a useful guide
    for text navigation.
    Loosely based on https://nachtimwald.com/2009/08/15/qtextedit-with-line-numbers/

    Attributes:
        text_edit (QTextEdit): The text editor widget that this NumberBar
                               is associated with.
    """    
    
    def __init__(self, text_edit: QtWidgets.QTextEdit, *args):
        super().__init__(*args)
        self.text_edit = text_edit
        background_color = text_edit.palette().color(QtGui.QPalette.ColorRole.Base)
        self.setStyleSheet(f"background-color: {background_color.name()};")
        # The highest line that is currently visible, used to update the width of the control
        self.highest_line = 0
        self.digits = 0
        self.first_line = 1

        # Install event filter
        class EventFilter(QtCore.QObject):
            def eventFilter(filter_self, source: QtCore.QObject, event: QtCore.QEvent):
                if source == self.text_edit or source == self.text_edit.viewport():
                    if event.type() in (QtCore.QEvent.Type.UpdateRequest, 
                                        QtCore.QEvent.Type.Paint, 
                                        QtCore.QEvent.Type.Resize, 
                                        QtCore.QEvent.Type.KeyPress, 
                                        QtCore.QEvent.Type.Wheel):
                        self.update()
                return super(EventFilter, filter_self).eventFilter(source, event)

        self.event_filter = EventFilter(self)
        self.text_edit.installEventFilter(self.event_filter)
        self.text_edit.viewport().installEventFilter(self.event_filter)

    def adjustWidth(self):
        """ 
        Adjust the with of the NumberBar according to the length of the highest number. 
        The minimum width is 3 digits.
        Will try to adjust the scrolling position accordingly so that the visible text is 
        not jumping too much.
        """
        if self.first_line > self.highest_line:
            self. highest_line = self.first_line
        if self.highest_line < 1000:
            digits = 3  # minimum width 3 digits
        else:
            digits = len(str(self.highest_line)) 
        new_digits = digits - self.digits
        if new_digits <= 0:
            return  # no width adjustment needed
        self.digits = digits
        font = self.text_edit.font()
        font.setFamily('Monospace')
        font.setStyleHint(QtGui.QFont.StyleHint.TypeWriter)
        font_metrics = QtGui.QFontMetrics(font)
        width = font_metrics.boundingRect('0' * digits).width() + 16
        self.setFixedWidth(width)
        # adjust scroll position
        magic_number = 0.00947327480831203467051894654962
        new_pos = round(self.text_edit.verticalScrollBar().value() * (1 + new_digits * magic_number))
        if new_pos > 0:
            QtCore.QTimer.singleShot(100, lambda: self.text_edit.verticalScrollBar().setValue(new_pos))
        
    def showEvent(self, event):
        """Adjusts the width based on the current font size"""
        super().showEvent(event)
        self.adjustWidth()

    def update(self, *args):
        """
        Updates the number bar to display the current set of numbers.
        Also, adjusts the width of the number bar if necessary.
        """
        self.adjustWidth()
        QtWidgets.QWidget.update(self, *args)
           
    def paintEvent(self, event):
        """Custom painting logic for rendering the line numbers
        based on the currently visible text blocks in the QTextEdit."""
        
        contents_y = self.text_edit.verticalScrollBar().value()
        page_bottom = contents_y + self.text_edit.viewport().height()
        text_edit_font_metrics = self.text_edit.fontMetrics()

        painter = QtGui.QPainter(self)
        font = self.text_edit.font()
        font.setFamily('Monospace')
        font.setStyleHint(QtGui.QFont.StyleHint.TypeWriter)
        text_color = self.palette().color(QtGui.QPalette.ColorGroup.Disabled, QtGui.QPalette.ColorRole.Text)
        painter.setPen(text_color)
        painter.setFont(font)
        font_metrics = painter.fontMetrics()

        line_count = self.first_line - 1
        block = self.text_edit.document().begin()

        while block.isValid():
            line_count += 1
            position = self.text_edit.document().documentLayout().blockBoundingRect(block).topLeft()
            if position.y() > page_bottom:
                break

            line_number = str(line_count)
            painter.drawText(
                self.width() - font_metrics.boundingRect(line_number).width() - 8, 
                round(position.y()) - contents_y + text_edit_font_metrics.ascent(), 
                line_number
            )
                            
            block = block.next()
            if line_count > self.highest_line:
                self.highest_line = line_count

        painter.end()
        QtWidgets.QWidget.paintEvent(self, event)
    
    def set_first_line(self, line: int, do_update=True):
        """
        Defines the number of the first line. 
        Used when loading long texts in chunks.
        """
        self.first_line = line
        if do_update:
            self.update()
