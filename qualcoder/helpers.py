# -*- coding: utf-8 -*-

"""
Copyright (c) 2020 Colin Curtain

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
import vlc

from PyQt5 import QtCore, QtGui, QtWidgets
# from PyQt5.QtCore import Qt

from GUI.ui_dialog_code_context_image import Ui_Dialog_code_context_image

# from information import DialogInformation


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


class Message(QtWidgets.QMessageBox):
    """ This is called a lot , but is styled to font size """

    def __init__(self, app, title, text, icon=None):
        QtWidgets.QMessageBox.__init__(self)

        self.setStyleSheet("* {font-size:" + str(app.settings['fontsize']) + "pt} ")
        self.setWindowTitle(title)
        self.setText(text)
        if icon == "warning":
            self.setIcon(QtWidgets.QMessageBox.Warning)
        if icon == "Information":
            self.setIcon(QtWidgets.QMessageBox.Information)
        if icon == "critical":
            self.setIcon(QtWidgets.QMessageBox.Critical)


    class DialogCodeInText(QtWidgets.QDialog):
        """ View the coded text in context of the original text file in a modal dialog.
        Called by: reports.DialogReportCodes after results are produced
        """

        app = None
        data = None

        def __init__(self, app, data, parent=None):
            """ Prepare QDialog window.
            param:
                data : dictionary: codename, color, file_or_casename, pos0, pos1, text, coder, fid, file_or_case, textedit_start, textedit_end
                app : class containing app details such as database connection
            """

            sys.excepthook = exception_handler
            self.app = app
            self.data = data
            QtWidgets.QDialog.__init__(self)
            font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
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
            te = QtWidgets.QTextEdit()
            te.setPlainText(file_text['fulltext'])
            cursor = te.textCursor()
            cursor.setPosition(data['pos0'], QtGui.QTextCursor.MoveAnchor)
            cursor.setPosition(data['pos1'], QtGui.QTextCursor.KeepAnchor)
            fmt = QtGui.QTextCharFormat()
            brush = QtGui.QBrush(QtGui.QColor(data['color']))
            fmt.setBackground(brush)
            cursor.setCharFormat(fmt)
            #ui = QtWidgets.QDialog()
            self.setWindowTitle(title)
            font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
            font += '"' + self.app.settings['font'] + '";'
            self.setStyleSheet(font)
            gridLayout = QtWidgets.QGridLayout(self)
            gridLayout.addWidget(te, 1, 0)
            self.resize(400, 300)
            # Make marked text visible in the textEdit and not ned to scroll to it
            text_cursor = te.textCursor()
            text_cursor.setPosition(data['pos0'])
            te.setTextCursor(text_cursor)
            te.setReadOnly(True)
            #ui.exec_()


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

        # enable custom window hint - must be set to enable customizing window controls
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.CustomizeWindowHint)
        self.setWindowTitle(self.data['text'])
        self.gridLayout = QtWidgets.QGridLayout(self)
        self.frame = QtWidgets.QFrame(self)
        if platform.system() == "Darwin":  # for MacOS
            self.frame = QtWidgets.QMacCocoaViewContainer(0)
        '''self.palette = self.frame.palette()
        self.palette.setColor(QtGui.QPalette.Window, QtGui.QColor(30, 30, 30))
        self.frame.setPalette(self.palette)
        self.frame.setAutoFillBackground(True)'''
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
                self.media = self.instance.media_new(self.file_['mediapath'][6:])
        except Exception as e:
            Message(self.app, _('Media not found'), str(e) + "\n" + self.app.project_path + self.data['mediapath'],
                    "warning").exec_()
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
        # print("dur", self.mediaplayer.get_media().get_duration())
        # print("pos as float", pos)
        self.mediaplayer.play()  # Need to start play forst
        self.mediaplayer.set_position(pos)
        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.update_ui)
        self.timer.start()

    def update_ui(self):
        """ Checks for end of playing segment. """

        msecs = self.mediaplayer.get_time()
        msg = msecs_to_mins_and_secs(msecs)
        msg += "\n" + _("Memo: ") + self.data['memo']
        self.setToolTip(msg)
        if self.data['pos1'] < msecs:
            self.mediaplayer.stop()

    def closeEvent(self, event):
        self.mediaplayer.stop()


class DialogCodeInText(QtWidgets.QDialog):
    """View the coded text in context of the original text file in a modal dialog.
    """

    app = None
    data = None

    def __init__(self, app, data, parent=None):
        """ Set up QDialog
        param:
            app : class containing app details such as database connection
            data : dictionary {codename, color, file_or_casename, pos0, pos1, text, coder,
                    fid, memo, file_or_case, textedit_start, textedit_end}
        """

        sys.excepthook = exception_handler
        self.app = app
        self.data = data
        QtWidgets.QDialog.__init__(self)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.resize(400, 300)
        # enable custom window hint - must be set to enable customizing window controls
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.CustomizeWindowHint)
        file_list = self.app.get_file_texts([data['fid'], ])
        file_text = file_list[0]
        title = ""
        if data['file_or_case'] == "File":
            title = _("File: ") + data['file_or_casename']
        if data['file_or_case'] == "Case":
            title = _("Case: ") + data['file_or_casename'] + ", " + file_text['name']
        self.setWindowTitle(title)
        self.gridLayout = QtWidgets.QGridLayout(self)

        te = QtWidgets.QTextEdit()
        te.setPlainText(file_text['fulltext'])
        cursor = te.textCursor()
        cursor.setPosition(data['pos0'], QtGui.QTextCursor.MoveAnchor)
        cursor.setPosition(data['pos1'], QtGui.QTextCursor.KeepAnchor)
        fmt = QtGui.QTextCharFormat()
        brush = QtGui.QBrush(QtGui.QColor(data['color']))
        fmt.setBackground(brush)
        cursor.setCharFormat(fmt)
        '''font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        ui.setStyleSheet(font)'''
        self.gridLayout.addWidget(te, 1, 0)
        # Make marked text visible in the textEdit and not ned to scroll to it
        text_cursor = te.textCursor()
        text_cursor.setPosition(data['pos0'])
        te.setTextCursor(text_cursor)
        te.setReadOnly(True)


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
            Message(self.app, _('Image error'), _("Cannot open: ") + abs_path, "warning").exec_()
            self.close()
            return
        self.scene = QtWidgets.QGraphicsScene()
        self.ui.graphicsView.setScene(self.scene)
        self.ui.graphicsView.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)

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
        self_h = self.height() - 30 - 80  # slider and textedit heights
        s_w = self.width()
        if self.pixmap.height() > self.height() - 30 - 80:
            self.scale = (self.height() - 30 - 80) / self.pixmap.height()
            slider_value = int(self.scale * 100)
            if slider_value > 100:
                slider_value = 100
            self.ui.horizontalSlider.setValue(slider_value)
        self.draw_coded_area()

    def draw_coded_area(self):
        """ Draw the coded rectangle in the scene """

        tooltip = self.data['codename'] + " (" + self.data['coder'] + ")"
        tooltip += "\nMemo: " + self.data['memo']
        x = self.data['x1'] * self.scale
        y = self.data['y1'] * self.scale
        width = self.data['width'] * self.scale
        height = self.data['height'] * self.scale
        rect_item = QtWidgets.QGraphicsRectItem(x, y, width, height)
        rect_item.setPen(QtGui.QPen(QtGui.QColor(self.data['color']), 2, QtCore.Qt.DashLine))
        rect_item.setToolTip(tooltip)
        self.scene.addItem(rect_item)

    def change_scale(self):
        """ Resize image. Triggered by user change in slider.
        Also called by unmark, as all items need to be redrawn. """

        if self.pixmap is None:
            return
        self.scale = (self.ui.horizontalSlider.value() + 1) / 100
        height = self.scale * self.pixmap.height()
        pixmap = self.pixmap.scaledToHeight(height, QtCore.Qt.FastTransformation)
        pixmap_item = QtWidgets.QGraphicsPixmapItem(pixmap)
        pixmap_item.setPos(0, 0)
        self.scene.clear()
        self.scene.addItem(pixmap_item)
        self.draw_coded_area()
        self.ui.horizontalSlider.setToolTip(_("Scale: ") + str(int(self.scale * 100)) + "%")
