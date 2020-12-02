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

from copy import deepcopy
import datetime
import logging
import os
import platform
from random import randint
import re
import sys
import time
import traceback

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.Qt import QHelpEvent
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush

# https://stackoverflow.com/questions/59014318/filenotfounderror-could-not-find-module-libvlc-dll
if sys.platform.startswith("win"):
    try:
        # Older x86 32 bit location
        os.add_dll_directory(r'C:\Program Files (x86)\VideoLAN\VLC')
    except Exception as e:
        logger.debug(str(e))
        # Commented below out, as this would be less common location.
        # Uncomment if desired
        # QtWidgets.QMessageBox.critical(None, _('Add DLL Exception'), str(e))
    try:
        os.add_dll_directory(r'C:\Program Files\VideoLAN\VLC')
    except Exception as e:
        # Commented below out, uncomment if desired
        # QtWidgets.QMessageBox.critical(None, _('Add DLL Exception'), str(e))
        logger.debug(str(e))
vlc_msg = ""
try:
    import vlc
except Exception as e:
    vlc_msg = str(e) + "\n"
    if sys.platform.startswith("win"):
        imp = False
    if not imp:
        msg = str(e) + "\n"
        msg = "view_av. Cannot import vlc\n"
        msg += "Ensure you have 64 bit python AND 64 bit VLC installed OR\n"
        msg += "32 bit python AND 32 bit VLC installed."
        print(msg)
        vlc_msg = msg
    QtWidgets.QMessageBox.critical(None, _('Cannot import vlc'), vlc_msg)

from add_item_name import DialogAddItemName
from color_selector import DialogColorSelect
from color_selector import colors
from confirm_delete import DialogConfirmDelete
from GUI.ui_dialog_code_av import Ui_Dialog_code_av
from GUI.ui_dialog_view_av import Ui_Dialog_view_av
from helpers import msecs_to_mins_and_secs, Message
from memo import DialogMemo
from select_items import DialogSelectItems


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception: ") + text)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 12pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(text)
    mb.exec_()


class DialogCodeAV(QtWidgets.QDialog):
    """ View and code audio and video segments.
    Create codes and categories.  """

    app = None
    dialog_list = None
    parent_textEdit = None
    filename = None
    files = []
    codes = []
    categories = []
    code_text = []
    ddialog = None
    media_data = None
    instance = None
    mediaplayer = None
    media = None
    metadata = None
    is_paused = False
    segment = {}
    segments = []
    text_for_segment = {}  # when linking text to segment
    segment_for_text = None  # when linking segment to text
    timer = QtCore.QTimer()
    play_segment_end = None

    # for transcribed text
    annotations = []
    code_text = []
    transcription = None  # A tuple of id, fulltext, name
    # transcribed time positions as list of [text_pos0, text_pos1, milliseconds]
    time_positions = []

    def __init__(self, app, parent_textEdit, dialog_list):
        """ Show list of audio and video files.
        Can code a transcribed text file for the audio / video.
        """

        super(DialogCodeAV, self).__init__()
        sys.excepthook = exception_handler
        self.app = app
        self.dialog_list = dialog_list
        self.parent_textEdit = parent_textEdit
        if vlc_msg != "":
            self.parent_textEdit.append(vlc_msg)
        self.codes = []
        self.categories = []
        self.annotations = []
        self.code_text = []
        self.time_positions = []
        self.transcription = None
        self.media_data = None
        self.segment['start'] = None
        self.segment['end'] = None
        self.segment['start_msecs'] = None
        self.segment['end_msecs'] = None
        self.play_segment_end = None
        self.segments = []
        self.text_for_segment = {'cid': None, 'fid': None, 'seltext': None, 'pos0': None, 'pos1': None,
                'owner': None, 'memo': None, 'date': None, 'avid': None}
        self.segment_for_text = None
        self.get_codes_and_categories()
        self.get_list_of_media()
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_code_av()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        try:
            w = int(self.app.settings['dialogcodeav_w'])
            h = int(self.app.settings['dialogcodeav_h'])
            if h > 50 and w > 50:
                self.resize(w, h)
            x = int(self.app.settings['codeav_abs_pos_x'])
            y = int(self.app.settings['codeav_abs_pos_y'])
            self.move(self.mapToGlobal(QtCore.QPoint(x, y)))
        except:
            pass
        try:
            s0 = int(self.app.settings['dialogcodeav_splitter0'])
            s1 = int(self.app.settings['dialogcodeav_splitter1'])
            if s0 > 10 and s1 > 10:
                self.ui.splitter.setSizes([s0, s1])
            h0 = int(self.app.settings['dialogcodeav_splitter_h0'])
            h1 = int(self.app.settings['dialogcodeav_splitter_h1'])
            if h0 > 10 and h1 > 10:
                self.ui.splitter_2.setSizes([h0, h1])
        except:
            pass

        # until any media is selected disable some widgets
        self.ui.pushButton_play.setEnabled(False)
        self.ui.pushButton_coding.setEnabled(False)
        self.ui.horizontalSlider.setEnabled(False)
        self.installEventFilter(self)  # for rewind, play/stop

        # Prepare textEdit for coding transcribed text
        self.ui.textEdit.setPlainText("")
        self.ui.textEdit.setAutoFillBackground(True)
        self.ui.textEdit.setToolTip("")
        self.ui.textEdit.setMouseTracking(True)
        self.ui.textEdit.setReadOnly(True)
        self.eventFilterTT = ToolTip_EventFilter()
        self.ui.textEdit.installEventFilter(self.eventFilterTT)
        self.ui.textEdit.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.textEdit.customContextMenuRequested.connect(self.textEdit_menu)

        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        tree_font = 'font: ' + str(self.app.settings['treefontsize']) + 'pt '
        tree_font += '"' + self.app.settings['font'] + '";'
        self.ui.treeWidget.setStyleSheet(tree_font)
        self.ui.label_coder.setText(_("Coder: ") + self.app.settings['codername'])
        self.setWindowTitle(_("Media coding"))
        self.ui.listWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.listWidget.customContextMenuRequested.connect(self.select_media_menu)
        self.ui.listWidget.setStyleSheet(tree_font)
        for f in self.files:
            item = QtWidgets.QListWidgetItem(f['name'])
            item.setToolTip(f['memo'])
            self.ui.listWidget.addItem(item)
        self.ui.listWidget.itemClicked.connect(self.listwidgetitem_view_file)
        self.ui.treeWidget.setDragEnabled(True)
        self.ui.treeWidget.setAcceptDrops(True)
        self.ui.treeWidget.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.ui.treeWidget.viewport().installEventFilter(self)
        self.ui.treeWidget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ui.treeWidget.customContextMenuRequested.connect(self.tree_menu)
        self.ui.treeWidget.itemClicked.connect(self.assign_selected_text_to_code)
        self.fill_tree()

        # My solution to getting gui mouse events by putting vlc video in another dialog
        # A display-dialog named ddialog
        # Otherwise, the vlc player hogs all the mouse events
        self.ddialog = QtWidgets.QDialog()
        # Enable custom window hint
        self.ddialog.setWindowFlags(self.ddialog.windowFlags() | QtCore.Qt.CustomizeWindowHint)
        # Disable close button, only close through closing the Ui_Dialog_code_av
        self.ddialog.setWindowFlags(self.ddialog.windowFlags() & ~QtCore.Qt.WindowCloseButtonHint)
        self.ddialog.gridLayout = QtWidgets.QGridLayout(self.ddialog)
        self.ddialog.dframe = QtWidgets.QFrame(self.ddialog)
        self.ddialog.dframe.setObjectName("frame")
        if platform.system() == "Darwin":  # For MacOS
            self.ddialog.dframe = QtWidgets.QMacCocoaViewContainer(0)
        self.palette = self.ddialog.dframe.palette()
        self.palette.setColor(QtGui.QPalette.Window, QtGui.QColor(30, 30, 30))
        self.ddialog.dframe.setPalette(self.palette)
        self.ddialog.dframe.setAutoFillBackground(True)
        self.ddialog.gridLayout.addWidget(self.ddialog.dframe, 0, 0, 0, 0)
        # enable custom window hint - must be set to enable customizing window controls
        self.ddialog.setWindowFlags(self.ddialog.windowFlags() | QtCore.Qt.CustomizeWindowHint)
        # disable close button, only close through closing the Ui_Dialog_view_av
        self.ddialog.setWindowFlags(self.ddialog.windowFlags() & ~QtCore.Qt.WindowCloseButtonHint)
        self.ddialog.setWindowFlags(self.ddialog.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        # add context menu for ddialog
        self.ddialog.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ddialog.customContextMenuRequested.connect(self.ddialog_menu)

        # Create a vlc instance with an empty vlc media player
        # https://stackoverflow.com/questions/55339786/how-to-turn-off-vlcpulse-audio-from-python-program
        self.instance = vlc.Instance()
        self.mediaplayer = self.instance.media_player_new()
        self.mediaplayer.video_set_mouse_input(False)
        self.mediaplayer.video_set_key_input(False)
        self.ui.horizontalSlider.setTickPosition(QtWidgets.QSlider.NoTicks)
        self.ui.horizontalSlider.setMouseTracking(True)
        self.ui.horizontalSlider.installEventFilter(self)
        self.ui.horizontalSlider.sliderMoved.connect(self.set_position)
        self.ui.pushButton_play.clicked.connect(self.play_pause)
        self.ui.horizontalSlider_vol.valueChanged.connect(self.set_volume)
        self.ui.pushButton_coding.pressed.connect(self.create_or_clear_segment)
        self.ui.comboBox_tracks.currentIndexChanged.connect(self.audio_track_changed)

        # Set the scene for coding stripes
        # Matches the designer file graphics view size
        self.scene_width = 990
        self.scene_height = 110
        self.scene = GraphicsScene(self.scene_width, self.scene_height)
        self.ui.graphicsView.setScene(self.scene)
        self.ui.graphicsView.setContextMenuPolicy(QtCore.Qt.DefaultContextMenu)

    def ddialog_menu(self, position):
        """ Context menu to export a screenshot, to resize dialog. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        ActionScreenshot = menu.addAction(_("Screenshot"))
        ActionResize = menu.addAction(_("Resize"))

        action = menu.exec_(self.ddialog.mapToGlobal(position))
        if action == ActionScreenshot:
            time.sleep(0.5)
            screen = QtWidgets.QApplication.primaryScreen()
            screenshot = screen.grabWindow(self.ddialog.winId())
            screenshot.save(self.app.settings['directory'] + '/Frame_' + datetime.datetime.now().astimezone().strftime(
                "%Y%m%d_%H_%M_%S") + '.jpg', 'jpg')
        if action == ActionResize:
            w = self.ddialog.size().width()
            h = self.ddialog.size().height()
            res_w = QtWidgets.QInputDialog.getInt(None, _("Width"), _("Width:"), w, 100, 2000, 5)
            if res_w[1]:
                w = res_w[0]
            res_h = QtWidgets.QInputDialog.getInt(None, _("Height"), _("Height:"), h, 80, 2000, 5)
            if res_h[1]:
                h = res_h[0]
            self.ddialog.resize(w, h)

    def get_codes_and_categories(self):
        """ Called from init, delete category/code, event_filter. """

        self.codes, self.categories = self.app.get_data()

    def get_list_of_media(self):
        """ Get AV media and exclude those with bad links. """

        bad_links = self.app.check_bad_file_links()
        bl_sql = ""
        for bl in bad_links:
            bl_sql += "," + str(bl['id'])
        if len(bl_sql) > 0:
            bl_sql = " and id not in (" + bl_sql[1:] + ") "

        self.files = []
        cur = self.app.conn.cursor()
        cur.execute("select name, id, memo, owner, date, mediapath from source where \
            substr(mediapath,1,6) in ('/audio','/video', 'audio:', 'video:') " + bl_sql + " order by name")
        result = cur.fetchall()
        self.files = []
        keys = 'name', 'id', 'memo', 'owner', 'date', 'mediapath'
        for row in result:
            self.files.append(dict(zip(keys, row)))

    def assign_selected_text_to_code(self):
        """ Assign selected text on left-click on code in tree. """

        current = self.ui.treeWidget.currentItem()
        if current.text(1)[0:3] == 'cat':
            return
        code_for_underlining = None
        for c in self.codes:
            if current.text(0) == c['name']:
                code_for_underlining = c
                break
        selected_text = self.ui.textEdit.textCursor().selectedText()
        if len(selected_text) > 0:
            self.mark()
        self.underline_text_of_this_code(code_for_underlining)

    def underline_text_of_this_code(self, code_for_underlining):
        """ User interface, highlight coded text selections for the currently selected code.
        Qt underline options: # NoUnderline, SingleUnderline, DashUnderline, DotLine, DashDotLine, WaveUnderline
        param:
            code_for_underlining: dictionary of the code to be underlined """

        # Remove all underlining
        selstart = 0
        selend = len(self.ui.textEdit.toPlainText())
        format = QtGui.QTextCharFormat()
        format.setUnderlineStyle(QtGui.QTextCharFormat.NoUnderline)
        cursor = self.ui.textEdit.textCursor()
        cursor.setPosition(selstart)
        cursor.setPosition(selend, QtGui.QTextCursor.KeepAnchor)
        cursor.mergeCharFormat(format)
        # Apply underlining in for selected coded text
        format = QtGui.QTextCharFormat()
        format.setUnderlineStyle(QtGui.QTextCharFormat.DashUnderline)
        cursor = self.ui.textEdit.textCursor()
        for coded_text in self.code_text:
            if coded_text['cid'] == code_for_underlining['cid']:
                cursor.setPosition(int(coded_text['pos0']), QtGui.QTextCursor.MoveAnchor)
                cursor.setPosition(int(coded_text['pos1']), QtGui.QTextCursor.KeepAnchor)
                cursor.mergeCharFormat(format)

    def fill_tree(self):
        """ Fill tree widget, tope level items are main categories and unlinked codes. """

        cats = deepcopy(self.categories)
        codes = deepcopy(self.codes)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(4)
        self.ui.treeWidget.setHeaderLabels([_("Name"), _("Id"), _("Memo"), _("Count")])
        if self.app.settings['showids'] == 'False':
            self.ui.treeWidget.setColumnHidden(1, True)
        else:
            self.ui.treeWidget.setColumnHidden(1, False)
        self.ui.treeWidget.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.ui.treeWidget.header().setStretchLastSection(False)
        # add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                memo = ""
                if c['memo'] != "" and c['memo'] is not None:
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                top_item.setToolTip(2, c['memo'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_list.append(c)
        for item in remove_list:
            # try:
            cats.remove(item)
            # except Exception as e:
            #    print(e, item)

        ''' Add child categories. Look at each unmatched category, iterate through tree
        to add as child, then remove matched categories from the list. '''
        count = 0
        while len(cats) > 0 and count < 10000:
            remove_list = []
            # logger.debug("cats:" + str(cats))
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
                item = it.value()
                count2 = 0
                while item and count2 < 10000:  # while there is an item in the list
                    if item.text(1) == 'catid:' + str(c['supercatid']):
                        memo = ""
                        if c['memo'] != "":
                            memo = "Memo"
                        child = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                        child.setToolTip(2, c['memo'])
                        item.addChild(child)
                        remove_list.append(c)
                    it += 1
                    item = it.value()
                    count2 += 1
            for item in remove_list:
                cats.remove(item)
            count += 1

        # add unlinked codes as top level items
        remove_items = []
        for c in codes:
            if c['catid'] is None:
                memo = ""
                if c['memo'] != "" and c['memo'] is not None:
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                top_item.setToolTip(2, c['memo'])
                top_item.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.SolidPattern))
                top_item.setFlags(
                    Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)

        # add codes as children
        for c in codes:
            it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
            item = it.value()
            count = 0
            while item and count < 10000:
                if item.text(1) == 'catid:' + str(c['catid']):
                    memo = ""
                    if c['memo'] != "" and c['memo'] is not None:
                        memo = _("Memo")
                    child = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                    child.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.SolidPattern))
                    child.setToolTip(2, c['memo'])
                    child.setFlags(
                        Qt.ItemIsSelectable | Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
                    item.addChild(child)
                    c['catid'] = -1  # make unmatchable
                it += 1
                item = it.value()
                count += 1
        self.ui.treeWidget.expandAll()

    def fill_code_counts_in_tree(self):
        """ Count instances of each code for current coder and in the selected file. """

        if self.media_data is None:
            return
        cur = self.app.conn.cursor()
        sql = "select count(cid) from code_av where cid=? and id=? and owner=?"
        sql_txt = "select count(cid) from code_text where cid=? and fid=? and owner=?"
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        count = 0
        while item and count < 10000:
            if item.text(1)[0:4] == "cid:":
                cid = str(item.text(1)[4:])
                cur.execute(sql, [cid, self.media_data['id'], self.app.settings['codername']])
                result_av = cur.fetchone()
                result_txt = [0]
                try:  # may not have a text file
                    cur.execute(sql_txt, [cid, self.transcription[0], self.app.settings['codername']])
                    result_txt = cur.fetchone()
                except:
                    pass
                result = result_av[0] + result_txt[0]
                if result > 0:
                    item.setText(3, str(result))
                else:
                    item.setText(3, "")
            it += 1
            item = it.value()
            count += 1

    def select_media_menu(self, position):
        """ Context menu to select the next image alphabetically, or
         to select the image that was most recently coded """

        if len(self.files) < 2:
            return
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_next = menu.addAction(_("Next file"))
        action_latest = menu.addAction(_("File with latest coding"))
        action = menu.exec_(self.ui.listWidget.mapToGlobal(position))
        if action == action_next:
            if self.media_data is None:
                self.media_data = self.files[0]
                self.load_media()
                self.load_segments()
                self.fill_code_counts_in_tree()
                return
            for i in range(0, len(self.files) - 1):
                if self.media_data == self.files[i]:
                    found = self.files[i + 1]
                    self.media_data = found
                    self.load_media()
                    self.load_segments()
                    self.fill_code_counts_in_tree()
                    return
        if action == action_latest:
            sql = "SELECT id FROM code_av where owner=? order by date desc limit 1"
            cur = self.app.conn.cursor()
            cur.execute(sql, [self.app.settings['codername'], ])
            result = cur.fetchone()
            if result is None:
                return
            for f in self.files:
                if f['id'] == result[0]:
                    self.media_data = f
                    self.load_media()
                    self.load_segments()
                    self.fill_code_counts_in_tree()
                    return

    def listwidgetitem_view_file(self):
        """ Item selcted so fill current file variable and load. """

        if len(self.files) == 0:
            return
        itemname = self.ui.listWidget.currentItem().text()
        for f in self.files:
            if f['name'] == itemname:
                self.media_data = f
                self.load_media()
                self.load_segments()
                self.fill_code_counts_in_tree()
                break

    def load_segments(self):
        """ Get coded segments for this file and for this coder.
        Called from select_media. """

        if self.media_data is None:
            return
        self.segments = []
        sql = "select avid, id, pos0, pos1, code_av.cid, code_av.memo, code_av.date, "
        sql += " code_av.owner, code_name.name, code_name.color from code_av"
        sql += " join code_name on code_name.cid=code_av.cid"
        sql += " where id=? "
        sql += " and code_av.owner=? "
        values = [self.media_data['id']]
        values.append(self.app.settings['codername'])
        cur = self.app.conn.cursor()
        cur.execute(sql, values)
        code_results = cur.fetchall()
        for row in code_results:
            self.segments.append({'avid': row[0], 'id': row[1], 'pos0': row[2],
                                  'pos1': row[3], 'cid': row[4], 'memo': row[5], 'date': row[6],
                                  'owner': row[7], 'codename': row[8], 'color': row[9], 'y': 10})
        # Fix overlapping segments by incrementing y values so segment is shown on a different line
        for i in range(0, len(self.segments) - 1):
            for j in range(i + 1, len(self.segments)):
                if (self.segments[j]['pos0'] >= self.segments[i]['pos0'] and \
                    self.segments[j]['pos0'] <= self.segments[i]['pos1'] and \
                    self.segments[i]['y'] == self.segments[j]['y']) or \
                        (self.segments[j]['pos0'] <= self.segments[i]['pos0'] and \
                         self.segments[j]['pos1'] >= self.segments[i]['pos0'] and \
                         self.segments[i]['y'] == self.segments[j]['y']):
                    # print("\nOVERLAP i:", self.segments[i]['pos0'], self.segments[i]['pos1'], self.segments[i]['y'], self.segments[i]['codename'])
                    # print("OVERLAP j:", self.segments[j]['pos0'], self.segments[j]['pos1'], self.segments[j]['y'], self.segments[j]['codename'])
                    # to overcome the overlap, add to the y value of the i segment
                    self.segments[j]['y'] += 10
        # Draw coded segments in scene
        scaler = self.scene_width / self.media.get_duration()
        self.scene.clear()
        for s in self.segments:
            self.scene.addItem(SegmentGraphicsItem(self.app, s, scaler, self.text_for_segment, self))

    def load_media(self):
        """ Add media to media dialog. """

        try:
            if self.media_data['mediapath'][0:6] in ('/audio', '/video'):
                self.media = self.instance.media_new(self.app.project_path + self.media_data['mediapath'])
            if self.media_data['mediapath'][0:6] in ('audio:', 'video:'):
                self.media = self.instance.media_new(self.media_data['mediapath'][6:])
        except Exception as e:
            mb = QtWidgets.QMessageBox()
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            mb.setWindowTitle(_('Media not found'))
            mb.setText(str(e) + "\n" + self.app.project_path + self.media_data['mediapath'])
            mb.exec_()
            self.media = None
            self.media_data = None
            self.setWindowTitle(_("Media coding"))
            return

        title = self.media_data['name'].split('/')[-1]
        self.ddialog.setWindowTitle(title)
        self.setWindowTitle(_("Media coding: ") + title)
        self.ui.pushButton_play.setEnabled(True)
        self.ui.horizontalSlider.setEnabled(True)
        self.ui.pushButton_coding.setEnabled(True)
        if self.media_data['mediapath'][0:6] not in ("/audio", "audio:"):
            self.ddialog.show()
            try:
                w = int(self.app.settings['video_w'])
                h = int(self.app.settings['video_h'])
                if w < 100 or h < 80:
                    w = 100
                    h = 80
                self.ddialog.resize(w, h)
                x = int(self.app.settings['codeav_video_pos_x']) - int(self.app.settings['codeav_abs_pos_x'])
                y = int(self.app.settings['codeav_video_pos_y']) - int(self.app.settings['codeav_abs_pos_y'])
                self.ddialog.move(self.mapToGlobal(QtCore.QPoint(x, y)))
            except:
                self.ddialog.resize(500, 400)
        else:
            self.ddialog.hide()

        # clear comboBox tracks options and reload when playing/pausing
        self.ui.comboBox_tracks.clear()
        # Put the media in the media player
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
            self.mediaplayer.set_xwindow(int(self.ddialog.dframe.winId()))
        elif platform.system() == "Windows":  # for Windows
            self.mediaplayer.set_hwnd(int(self.ddialog.winId()))
        elif platform.system() == "Darwin":  # for MacOS
            self.mediaplayer.set_nsobject(int(self.ddialog.winId()))
        msecs = self.media.get_duration()
        self.media_duration_text = "Duration: " + msecs_to_mins_and_secs(msecs)
        self.ui.label_time_2.setText(self.media_duration_text)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.update_ui)
        # Get the transcribed text and fill textedit
        cur = self.app.conn.cursor()
        cur.execute("select id, fulltext, name from source where name = ?", [self.media_data['name'] + ".transcribed"])
        self.transcription = cur.fetchone()
        if self.transcription is None:
            return
        self.ui.textEdit.setText(self.transcription[1])
        self.ui.textEdit.ensureCursorVisible()
        self.get_timestamps_from_transcription()

        # get text annotations
        cur = self.app.conn.cursor()
        cur.execute("select anid, fid, pos0, pos1, memo, owner, date from annotation where owner=? and fid=?",
                    [self.app.settings['codername'], self.transcription[0]])
        result = cur.fetchall()
        for row in result:
            self.annotations.append({'anid': row[0], 'fid': row[1], 'pos0': row[2],
                                     'pos1': row[3], 'memo': row[4], 'owner': row[5], 'date': row[6]})
        self.get_coded_text_update_eventfilter_tooltips()

    def get_coded_text_update_eventfilter_tooltips(self):
        """ Called by load_media, update_dialog_codes_and_categories,
        Segment_Graphics_Item.link_text_to_segment.
        link_segment_to_text"""

        if self.transcription is None:
            return
        # Get code text for this file and for this coder
        values = [self.transcription[0], self.app.settings['codername']]
        cur = self.app.conn.cursor()
        self.code_text = []
        # seltext length, longest first, so overlapping shorter text is superimposed.
        sql = "select code_text.cid, code_text.fid, seltext, code_text.pos0, code_text.pos1, "
        sql += "code_text.owner, code_text.date, code_text.memo, code_text.avid,code_av.pos0, code_av.pos1 "
        sql += "from code_text left join code_av on code_text.avid = code_av.avid "
        sql += " where code_text.fid=? and code_text.owner=? order by length(seltext) desc"
        cur.execute(sql, values)
        code_results = cur.fetchall()
        for row in code_results:
            self.code_text.append({'cid': row[0], 'fid': row[1], 'seltext': row[2],
                                   'pos0': row[3], 'pos1': row[4], 'owner': row[5], 'date': row[6],
                                   'memo': row[7], 'avid': row[8], 'av_pos0': row[9], 'av_pos1': row[10]})

        # Update filter for tooltip and redo formatting
        self.eventFilterTT.setCodes(self.code_text, self.codes)
        self.unlight()
        self.highlight()

    def get_timestamps_from_transcription(self):
        """ Get a list of starting/ending characterpositions and time in milliseconds
        from transcribed text file.

        Example formats:  [00:34:12] [45:33] [01.23.45] [02.34] {00.34.20}
        #00:12:34.567#
        09:33:04,100 --> 09:33:09,600

        Converts hh mm ss to milliseconds with text positions stored in a list
        The list contains lists of [text_pos0, text_pos1, milliseconds] """

        mmss1 = "\[[0-9]?[0-9]:[0-9][0-9]\]"
        hhmmss1 = "\[[0-9][0-9]:[0-9][0-9]:[0-9][0-9]\]"
        mmss2 = "\[[0-9]?[0-9]\.[0-9][0-9]\]"
        hhmmss2 = "\[[0-9][0-9]\.[0-9][0-9]\.[0-9][0-9]\]"
        hhmmss3 = "\{[0-9][0-9]\:[0-9][0-9]\:[0-9][0-9]\}"
        hhmmss_sss = "#[0-9][0-9]:[0-9][0-9]:[0-9][0-9]\.[0-9]{1,3}#"  # allow for 1 to 3 msecs digits
        srt = "[0-9][0-9]:[0-9][0-9]:[0-9][0-9],[0-9][0-9][0-9]\s-->\s[0-9][0-9]:[0-9][0-9]:[0-9][0-9],[0-9][0-9][0-9]"

        self.time_positions = []
        for match in re.finditer(mmss1, self.transcription[1]):
            stamp = match.group()[1:-1]
            s = stamp.split(':')
            try:
                msecs = (int(s[0]) * 60 + int(s[1])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except:
                pass
        for match in re.finditer(hhmmss1, self.transcription[1]):
            stamp = match.group()[1:-1]
            s = stamp.split(':')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s[2])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except:
                pass
        for match in re.finditer(mmss2, self.transcription[1]):
            stamp = match.group()[1:-1]
            s = stamp.split('.')
            try:
                msecs = (int(s[0]) * 60 + int(s[1])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except:
                pass
        for match in re.finditer(hhmmss2, self.transcription[1]):
            stamp = match.group()[1:-1]
            s = stamp.split('.')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s[2])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except:
                pass
        for match in re.finditer(hhmmss3, self.transcription[1]):
            stamp = match.group()[1:-1]
            s = stamp.split('.')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s[2])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except:
                pass
        for match in re.finditer(hhmmss_sss, self.transcription[1]):
            # Format #00:12:34.567#
            stamp = match.group()[1:-1]
            text_hms = stamp.split(':')
            text_secs = text_hms[2].split('.')[0]
            text_msecs = text_hms[2].split('.')[1]
            # adjust msecs to 1000's for 1 or 2 digit strings
            if len(text_msecs) == 1:
                text_msecs += "00"
            if len(text_msecs) == 2:
                text_msecs += "0"
            try:
                msecs = (int(text_hms[0]) * 3600 + int(text_hms[1]) * 60 + int(text_secs)) * 1000 + int(text_msecs)
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except:
                pass
        for match in re.finditer(srt, self.transcription[1]):
            # Format 09:33:04,100 --> 09:33:09,600  skip the arrow and second time position
            stamp = match.group()[0:12]
            s = stamp.split(':')
            s2 = s[2].split(',')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s2[0])) * 1000 + int(s2[1])
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except:
                pass
        # print(self.time_positions)

    def set_position(self):
        """ Set the movie position according to the position slider.
        The vlc MediaPlayer needs a float value between 0 and 1, Qt uses
        integer variables, so you need a factor; the higher the factor, the
        more precise are the results (1000 should suffice).
        """

        self.timer.stop()
        pos = self.ui.horizontalSlider.value()
        self.mediaplayer.set_position(pos / 1000.0)
        self.timer.start()

    def audio_track_changed(self):
        """ Audio track changed.
        The video needs to be playing/paused before the combobox is filled with track options.
        The combobox only has positive integers."""

        text = self.ui.comboBox_tracks.currentText()
        if text == "":
            text = 1
        # print("text: ", text)
        success = self.mediaplayer.audio_set_track(int(text))
        # print("changed audio ", success)

    def play_pause(self):
        """ Toggle play or pause status. """

        if self.mediaplayer.is_playing():
            self.mediaplayer.pause()
            self.ui.pushButton_play.setText(_("Play"))
            self.is_paused = True
            self.timer.stop()
        else:
            if self.mediaplayer.play() == -1:
                return

            # On play rewind one second
            time_msecs = self.mediaplayer.get_time() - 2000
            if time_msecs < 0:
                time_msecs = 0
            pos = time_msecs / self.mediaplayer.get_media().get_duration()
            self.mediaplayer.set_position(pos)
            # Update timer display
            msecs = self.mediaplayer.get_time()
            self.ui.label_time.setText(_("Time: ") + msecs_to_mins_and_secs(msecs))

            self.mediaplayer.play()
            self.ui.pushButton_play.setText(_("Pause"))
            self.timer.start()
            self.is_paused = False
            self.play_segment_end = None

    def stop(self):
        """ Stop vlc player. Set position slider to the start.
         If multiple audio tracks are shown in the combobox, set the audio track to the first index.
         This is because when beginning play again, the audio track reverts to the first track.
         Programatically setting the audio track to other values does not work."""

        self.mediaplayer.stop()
        self.ui.pushButton_play.setText(_("Play"))
        self.timer.stop()
        self.ui.horizontalSlider.setProperty("value", 0)
        self.play_segment_end = None

        # set combobox display of audio track to the first one, or leave it blank if it contains no items
        if self.ui.comboBox_tracks.count() > 0:
            self.ui.comboBox_tracks.setCurrentIndex(0)

    def set_volume(self, volume):
        """ Set the volume. """

        self.mediaplayer.audio_set_volume(volume)

    def update_ui(self):
        """ Updates the user interface. Update the slider position to match media.
         Adds audio track options to combobox.
         Updates the current displayed media time. """

        # update audio track list, only works if media is playing
        if self.mediaplayer.audio_get_track_count() > 0 and self.ui.comboBox_tracks.count() == 0:
            tracks = self.mediaplayer.audio_get_track_description()
            for t in tracks:
                if t[0] > 0:
                    # print(t[0], t[1])  # track number and track name
                    self.ui.comboBox_tracks.addItem(str(t[0]))

        # Set the slider's position to its corresponding media position
        # Note that the setValue function only takes values of type int,
        # so we must first convert the corresponding media position.
        media_pos = int(self.mediaplayer.get_position() * 1000)
        self.ui.horizontalSlider.setValue(media_pos)

        # update label_time
        msecs = self.mediaplayer.get_time()
        self.ui.label_time.setText(_("Time: ") + msecs_to_mins_and_secs(msecs))

        # Check if segments need to be reloaded
        # This only updates if the media is playing, not ideal, but works
        for i in self.scene.items():
            if isinstance(i, SegmentGraphicsItem) and i.reload_segment is True:
                self.load_segments()

        """ For long transcripts, update the relevant text position in the textEdit to match the
        video's current position.
        time_postion list item: [text_pos0, text_pos1, milliseconds]
        """
        if self.ui.checkBox_scroll_transcript.isChecked() and self.transcription is not None and self.ui.textEdit.toPlainText() != "":
            for i in range(1, len(self.time_positions)):
                if msecs > self.time_positions[i - 1][2] and msecs < self.time_positions[i][2]:
                    text_pos = self.time_positions[i][0]
                    textCursor = self.ui.textEdit.textCursor()
                    textCursor.setPosition(text_pos)
                    self.ui.textEdit.setTextCursor(textCursor)

        # No need to call this function if nothing is played
        if not self.mediaplayer.is_playing():
            self.timer.stop()
            # After the video finished, the play button stills shows "Pause",
            # which is not the desired behavior of a media player.
            # This fixes that "bug".
            if not self.is_paused:
                self.stop()

        # If only playing a segment, need to pause at end of segment
        if self.play_segment_end is not None:
            if self.play_segment_end < msecs:
                self.play_segment_end = None
                self.play_pause()

    def closeEvent(self, event):
        """ Stop the vlc player on close.
        Capture the video window size. """

        self.app.settings['dialogcodeav_w'] = self.size().width()
        self.app.settings['dialogcodeav_h'] = self.size().height()
        if self.media_data is not None and self.media_data['mediapath'] is not None and self.media_data['mediapath'][
                                                                                        0:7] != "/audio/":
            size = self.ddialog.size()
            if size.width() > 100:
                self.app.settings['video_w'] = size.width()
            else:
                self.app.settings['video_w'] = 100
            if size.height() > 80:
                self.app.settings['video_h'] = size.height()
            else:
                self.app.settings['video_h'] = 80
        # Get absolute video dialog position
        self.app.settings['codeav_video_pos_x'] = self.ddialog.pos().x()
        self.app.settings['codeav_video_pos_y'] = self.ddialog.pos().y()
        self.app.settings['codeav_abs_pos_x'] = self.pos().x()
        self.app.settings['codeav_abs_pos_y'] = self.pos().y()
        self.app.settings['dialogcodeav_splitter0'] = self.ui.splitter.sizes()[0]
        self.app.settings['dialogcodeav_splitter1'] = self.ui.splitter.sizes()[1]
        self.app.settings['dialogcodeav_splitter_h0'] = self.ui.splitter_2.sizes()[0]
        self.app.settings['dialogcodeav_splitter_h1'] = self.ui.splitter_2.sizes()[1]
        self.ddialog.close()
        self.stop()

    def create_or_clear_segment(self):
        """ Make the start end end points of the segment of time.
        Use minutes and seconds, and milliseconds formats for the time.
        Can also clear the segment by pressing the button when it says Clear segment.
        clear segment text is changed to Start segment once a segment is assigned to a code.
        """

        if self.ui.pushButton_coding.text() == _("Clear segment"):
            self.clear_segment()
            self.fill_code_counts_in_tree()
            return
        time = self.ui.label_time.text()
        time = time[6:]
        time_msecs = self.mediaplayer.get_time()
        if self.segment['start'] is None:
            self.segment['start'] = time
            self.segment['start_msecs'] = time_msecs
            self.segment['memo'] = ""
            self.ui.pushButton_coding.setText(_("End segment"))
            self.ui.label_segment.setText(_("Segment: ") + str(self.segment['start']) + " - ")
            return
        if self.segment['start'] is not None and self.segment['end'] is None:
            self.segment['end'] = time
            self.segment['end_msecs'] = time_msecs
            self.ui.pushButton_coding.setText(_("Clear segment"))

            # check and reverse start and end times if start is greater than the end
            # print("start", self.segment['start'], "end", self.segment['end'])
            if float(self.segment['start'].replace(":", ".")) > float(self.segment['end'].replace(":", ".")):
                tmp = self.segment['start']
                tmp_msecs = self.segment['start_msecs']
                self.segment['start'] = self.segment['end']
                self.segment['start_msecs'] = self.segment['end_msecs']
                self.segment['end'] = tmp
                self.segment['end_msecs'] = tmp_msecs
            text = _("Segment: ") + str(self.segment['start']) + " - " + self.segment['end']
            self.ui.label_segment.setText(text)

    def tree_menu(self, position):
        """ Context menu for treeWidget items.
        Add, rename, memo, move or delete code or category. Change code color. """

        selected_text = self.ui.textEdit.textCursor().selectedText()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        selected = self.ui.treeWidget.currentItem()
        # logger.debug("selected paremt: " + str(selected.parent()))
        # logger.debug("index: " + str(self.ui.treeWidget.currentIndex()))
        '''ActionAssignSelectedText = None
        if selected_text != "" and selected is not None and selected.text(1)[0:3] == 'cid':
            ActionAssignSelectedText = menu.addAction("Assign selected text")'''
        ActionItemAssignSegment = None
        if self.segment['end_msecs'] is not None and self.segment['start_msecs'] is not None:
            ActionItemAssignSegment = menu.addAction("Assign segment to code")
        ActionItemAddCode = menu.addAction(_("Add a new code"))
        ActionItemAddCategory = menu.addAction(_("Add a new category"))
        ActionItemRename = menu.addAction(_("Rename"))
        ActionItemEditMemo = menu.addAction(_("View or edit memo"))
        ActionItemDelete = menu.addAction(_("Delete"))
        if selected is not None and selected.text(1)[0:3] == 'cid':
            ActionItemChangeColor = menu.addAction(_("Change code color"))
        ActionShowCodesLike = menu.addAction(_("Show codes like"))

        action = menu.exec_(self.ui.treeWidget.mapToGlobal(position))
        if action == ActionShowCodesLike:
            self.show_codes_like()
            return
        if selected is not None and selected.text(1)[0:3] == 'cid' and action == ActionItemChangeColor:
            self.change_code_color(selected)
        if action == ActionItemAddCategory:
            self.add_category()
        if action == ActionItemAddCode:
            self.add_code()
        if selected is not None and action == ActionItemRename:
            self.rename_category_or_code(selected)
        if selected is not None and action == ActionItemEditMemo:
            self.add_edit_code_memo(selected)
        if selected is not None and action == ActionItemDelete:
            self.delete_category_or_code(selected)
        if action == ActionItemAssignSegment:
            self.assign_segment_to_code(selected)

    def show_codes_like(self):
        """ Show all codes if text is empty.
         Show selected codes that contain entered text. """

        # Input dialog narrow, so code below
        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        dialog.setWindowTitle(_("Show codes containing"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.TextInput)
        dialog.setLabelText(_("Show codes containing text.\n(Blank for all)"))
        dialog.resize(200, 20)
        ok = dialog.exec_()
        if not ok:
            return
        text = str(dialog.textValue())
        root = self.ui.treeWidget.invisibleRootItem()
        self.recursive_traverse(root, text)

    def recursive_traverse(self, item, text):
        """ Find all children codes of this item that match or not and hide or unhide based on 'text'.
        Recurse through all child categories.
        Called by: show_codes_like
        param:
            item: a QTreeWidgetItem
            text:  Text string for matching with code names
        """

        #logger.debug("recurse this item:" + item.text(0) + "|" item.text(1))
        child_count = item.childCount()
        for i in range(child_count):
            #print(item.child(i).text(0) + "|" + item.child(i).text(1))
            if "cid:" in item.child(i).text(1) and len(text) > 0 and text not in item.child(i).text(0):
                item.child(i).setHidden(True)
            if "cid:" in item.child(i).text(1) and text == "":
                item.child(i).setHidden(False)
            self.recursive_traverse(item.child(i), text)

    def update_dialog_codes_and_categories(self):
        """ Update code and category tree in DialogCodeImage, DialogCodeAV,
        DialogCodeText, DialogReportCodes.
        Not using isinstance for other classes, as could not import. There was an import error.
        Using try except blocks for each instance, as instance may have been deleted. """

        for d in self.dialog_list:
            if str(type(d)) == "<class 'code_text.DialogCodeText'>":
                try:
                    d.get_codes_and_categories()
                    d.fill_tree()
                    d.unlight()
                    d.highlight()
                    d.get_coded_text_update_eventfilter_tooltips()
                except RuntimeError as e:
                    pass
            if isinstance(d, DialogCodeAV):
                try:
                    d.get_codes_and_categories()
                    d.fill_tree()
                    d.load_segments()
                    d.unlight()
                    d.highlight()
                    d.get_coded_text_update_eventfilter_tooltips()
                except RuntimeError as e:
                    pass
            if str(type(d)) == "<class 'view_image.DialogCodeImage'>":
                try:
                    d.get_codes_and_categories()
                    d.fill_tree()
                    d.get_coded_areas()
                    d.draw_coded_areas()
                except RuntimeError as e:
                    pass
            if str(type(d)) == "<class 'reports.DialogReportCodes'>":
                try:
                    d.get_data()
                    d.fill_tree()
                except RuntimeError as e:
                    pass

    def eventFilter(self, object, event):
        """ Using this event filter to identify treeWidgetItem drop events.
        http://doc.qt.io/qt-5/qevent.html#Type-enum
        QEvent::Drop 63 A drag and drop operation is completed (QDropEvent).
        https://stackoverflow.com/questions/28994494/why-does-qtreeview-not-fire-a-drop-or-move-event-during-drag-and-drop
        Also use eventFilter for QGraphicsView.

        Options are:
            Ctrl + R to rewind 3 seconds.
            Alt + R rewind 30 seconds
            Alt +F forward 30 seconds
            Ctrl + S OR Ctrl + p to start/pause On start rewind 1 second

            Ctrl + Shift + > to increase play rate
            Ctrl + Shift + < to decrease play rate

        Also detect key events in the textedit. These are used to extend or shrink a text coding.
        Only works if clicked on a code (text cursor is in the coded text).
        Shrink start and end code positions using alt arrow left and alt arrow right
        Extend start and end code positions using shift arrow left, shift arrow right
        """

        if object is self.ui.treeWidget.viewport():
            if event.type() == QtCore.QEvent.Drop:
                item = self.ui.treeWidget.currentItem()
                parent = self.ui.treeWidget.itemAt(event.pos())
                self.item_moved_update_data(item, parent)

        if object == self.ui.horizontalSlider and event.type() == QtCore.QEvent.MouseMove and self.media is not None:
            maxx = self.ui.horizontalSlider.size().width()
            proportion = event.pos().x() / maxx
            msecs = self.media.get_duration() * proportion
            time = msecs_to_mins_and_secs(msecs)
            self.ui.horizontalSlider.setToolTip(time)

        if event.type() != 7 or self.media is None:  # QtGui.QKeyEvent = 7
            return False
        key = event.key()
        mods = event.modifiers()
        # print("KEY ", key, "MODS ", mods)

        # change start and end code positions using alt arrow left and alt arrow right
        # and shift arrow left, shift arrow right
        if self.ui.textEdit.hasFocus():
            key = event.key()
            mod = event.modifiers()
            cursor_pos = self.ui.textEdit.textCursor().position()
            codes_here = []
            for item in self.code_text:
                if cursor_pos >= item['pos0'] and cursor_pos <= item['pos1'] and item['owner'] == self.app.settings['codername']:
                    codes_here.append(item)
            if len(codes_here) == 1:
                if key == QtCore.Qt.Key_Left and mod == QtCore.Qt.AltModifier:
                    self.shrink_to_left(codes_here[0])
                    return False
                if key == QtCore.Qt.Key_Right and mod == QtCore.Qt.AltModifier:
                    self.shrink_to_right(codes_here[0])
                    return False
                if key == QtCore.Qt.Key_Left and mod == QtCore.Qt.ShiftModifier:
                    self.extend_left(codes_here[0])
                    return False
                if key == QtCore.Qt.Key_Right and mod == QtCore.Qt.ShiftModifier:
                    self.extend_right(codes_here[0])
                    return False

        #  Ctrl S or Ctrl + P pause/play toggle
        if (key == QtCore.Qt.Key_S or key == QtCore.Qt.Key_P) and mods == QtCore.Qt.ControlModifier:
            self.play_pause()
        # Advance 30 seconds Alt F
        if key == QtCore.Qt.Key_F and mods == QtCore.Qt.AltModifier:
            time_msecs = self.mediaplayer.get_time() + 30000
            if time_msecs > self.media.get_duration():
                time_msecs = self.media.get_duration() - 1
            pos = time_msecs / self.mediaplayer.get_media().get_duration()
            self.mediaplayer.set_position(pos)
            # Update timer display
            msecs = self.mediaplayer.get_time()
            self.ui.label_time.setText(_("Time: ") + msecs_to_mins_and_secs(msecs))
            self.update_ui()
        # Rewind 30 seconds Alt R
        if key == QtCore.Qt.Key_R and mods == QtCore.Qt.AltModifier:
            time_msecs = self.mediaplayer.get_time() - 30000
            if time_msecs < 0:
                time_msecs = 0
            pos = time_msecs / self.mediaplayer.get_media().get_duration()
            self.mediaplayer.set_position(pos)
            # Update timer display
            msecs = self.mediaplayer.get_time()
            self.ui.label_time.setText(_("Time: ") + msecs_to_mins_and_secs(msecs))
            self.update_ui()
        # Rewind 5 seconds Ctrl R
        if key == QtCore.Qt.Key_R and mods == QtCore.Qt.ControlModifier:
            time_msecs = self.mediaplayer.get_time() - 5000
            if time_msecs < 0:
                time_msecs = 0
            pos = time_msecs / self.mediaplayer.get_media().get_duration()
            self.mediaplayer.set_position(pos)
            # Update timer display
            msecs = self.mediaplayer.get_time()
            self.ui.label_time.setText(_("Time: ") + msecs_to_mins_and_secs(msecs))
            self.update_ui()
        # Increase play rate  Ctrl + Shift + >
        if key == QtCore.Qt.Key_Greater and (mods and QtCore.Qt.ShiftModifier) and (mods and QtCore.Qt.ControlModifier):
            self.increase_play_rate()
        # Decrease play rate  Ctrl + Shift + <
        if key == QtCore.Qt.Key_Less and (mods and QtCore.Qt.ShiftModifier) and (mods and QtCore.Qt.ControlModifier):
            self.decrease_play_rate()
        return False

    def extend_left(self, code_):
        """ Shift left arrow """

        if code_['pos0'] < 1:
            return
        code_['pos0'] -= 1
        cur = self.app.conn.cursor()
        sql = "update code_text set pos0=? where cid=? and fid=? and pos0=? and pos1=? and owner=?"
        cur.execute(sql,
            (code_['pos0'], code_['cid'], code_['fid'], code_['pos0'] + 1, code_['pos1'], self.app.settings['codername']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def extend_right(self, code_):
        """ Shift right arrow """

        if code_['pos1'] +1 >= len(self.ui.textEdit.toPlainText()):
            return
        code_['pos1'] += 1
        cur = self.app.conn.cursor()
        sql = "update code_text set pos1=? where cid=? and fid=? and pos0=? and pos1=? and owner=?"
        cur.execute(sql,
            (code_['pos1'], code_['cid'], code_['fid'], code_['pos0'], code_['pos1'] - 1, self.app.settings['codername']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def shrink_to_left(self, code_):
        """ Alt left arrow, shrinks code from the right end of the code """

        if code_['pos1'] <= code_['pos0'] + 1:
            return
        code_['pos1'] -= 1
        cur = self.app.conn.cursor()
        sql = "update code_text set pos1=? where cid=? and fid=? and pos0=? and pos1=? and owner=?"
        cur.execute(sql,
            (code_['pos1'], code_['cid'], code_['fid'], code_['pos0'], code_['pos1'] + 1, self.app.settings['codername']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def shrink_to_right(self, code_):
        """ Alt right arrow shrinks code from the left end of the code """

        if code_['pos0'] >= code_['pos1'] - 1:
            return
        code_['pos0'] += 1
        cur = self.app.conn.cursor()
        sql = "update code_text set pos0=? where cid=? and fid=? and pos0=? and pos1=? and owner=?"
        cur.execute(sql,
            (code_['pos0'], code_['cid'], code_['fid'], code_['pos0'] - 1, code_['pos1'], self.app.settings['codername']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def increase_play_rate(self):
        """ Several increased rate options """

        rate = self.mediaplayer.get_rate()
        rate += 0.1
        if rate > 2:
            rate = 2
        self.mediaplayer.set_rate(rate)
        self.ui.label_rate.setText(_("Rate: ") + str(round(rate, 1)))

    def decrease_play_rate(self):
        """ Several decreased rate options """

        rate = self.mediaplayer.get_rate()
        rate -= 0.1
        if rate < 0.1:
            rate = 0.1
        self.mediaplayer.set_rate(rate)
        self.ui.label_rate.setText(_("Rate: ") + str(round(rate, 1)))

    def assign_segment_to_code(self, selected):
        """ Assign time segment to selected code. Insert an entry into the database.
        Then clear the segment for re-use."""

        if self.media_data is None or self.segment['start_msecs'] is None or self.segment['end_msecs'] is None:
            self.clear_segment()
            return
        sql = "insert into code_av (id, pos0, pos1, cid, memo, date, owner) values(?,?,?,?,?,?,?)"
        cid = int(selected.text(1).split(':')[1])
        values = [self.media_data['id'], self.segment['start_msecs'],
                  self.segment['end_msecs'], cid, self.segment['memo'],
                  datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                  self.app.settings['codername']]
        cur = self.app.conn.cursor()
        cur.execute(sql, values)
        self.app.conn.commit()
        self.load_segments()
        self.clear_segment()
        self.app.delete_backup = False
        self.fill_code_counts_in_tree()

    def clear_segment(self):
        """ Called by assign_segment_to code. """

        self.segment['start'] = None
        self.segment['start_msecs'] = None
        self.segment['end'] = None
        self.segment['end_msecs'] = None
        self.segment['memo'] = ""
        self.ui.label_segment.setText(_("Segment:"))
        self.ui.pushButton_coding.setText(_("Start segment"))

    def item_moved_update_data(self, item, parent):
        """ Called from drop event in treeWidget view port.
        identify code or category to move.
        Also merge codes if one code is dropped on another code. """

        # find the category in the list
        if item.text(1)[0:3] == 'cat':
            found = -1
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(item.text(1)[6:]):
                    found = i
            if found == -1:
                return
            if parent is None:
                self.categories[found]['supercatid'] = None
            else:
                if parent.text(1).split(':')[0] == 'cid':
                    # parent is code (leaf) cannot add child
                    return
                supercatid = int(parent.text(1).split(':')[1])
                if supercatid == self.categories[found]['catid']:
                    # something went wrong
                    logger.debug("supercatid== self.categories[found][catid]")
                    return
                self.categories[found]['supercatid'] = supercatid
            cur = self.app.conn.cursor()
            cur.execute("update code_cat set supercatid=? where catid=?",
                        [self.categories[found]['supercatid'], self.categories[found]['catid']])
            self.app.conn.commit()
            self.update_dialog_codes_and_categories()
            return

        # find the code in the list
        if item.text(1)[0:3] == 'cid':
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(item.text(1)[4:]):
                    found = i
            if found == -1:
                return
            if parent is None:
                self.codes[found]['catid'] = None
            else:
                if parent.text(1).split(':')[0] == 'cid':
                    # parent is code (leaf) cannot add child, but can merge
                    self.merge_codes(self.codes[found], parent)
                    return
                catid = int(parent.text(1).split(':')[1])
                self.codes[found]['catid'] = catid
            cur = self.app.conn.cursor()
            cur.execute("update code_name set catid=? where cid=?",
                        [self.codes[found]['catid'], self.codes[found]['cid']])
            self.app.conn.commit()
            self.update_dialog_codes_and_categories()
            self.app.delete_backup = False

    def merge_codes(self, item, parent):
        """ Merge code or category with another code or category.
        Called by item_moved_update_data when a code is moved onto another code. """

        msg = _("Merge code: ") + item['name'] + " ==> " + parent.text(0)
        # TODO font size in message box
        reply = QtWidgets.QMessageBox.question(None, _('Merge codes'),
                                               msg, QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No)
        if reply == QtWidgets.QMessageBox.No:
            return
        cur = self.app.conn.cursor()
        old_cid = item['cid']
        new_cid = int(parent.text(1).split(':')[1])
        try:
            cur.execute("update code_av set cid=? where cid=?", [new_cid, old_cid])
            cur.execute("update code_image set cid=? where cid=?", [new_cid, old_cid])
            cur.execute("update code_text set cid=? where cid=?", [new_cid, old_cid])
            self.app.conn.commit()
            self.app.delete_backup = False
        except Exception as e:
            e = str(e)
            msg = _("Cannot merge codes, unmark overlapping text.") + "\n" + e
            QtWidgets.QInformationDialog(None, _("Cannot merge"), msg)
            return
        cur.execute("delete from code_name where cid=?", [old_cid, ])
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        self.parent_textEdit.append(msg)
        self.load_segments()

    def add_code(self):
        """ Use add_item dialog to get new code text.
        Add_code_name dialog checks for duplicate code name.
        New code is added to data and database. """

        ui = DialogAddItemName(self.app, self.codes, _("Add new code"), _("New code name"))
        ui.exec_()
        new_name = ui.get_new_name()
        if new_name is None:
            return
        code_color = colors[randint(0, len(colors) - 1)]
        item = {'name': new_name, 'memo': "", 'owner': self.app.settings['codername'],
                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'catid': None, 'color': code_color}
        cur = self.app.conn.cursor()
        cur.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,?,?,?,?)"
                    , (item['name'], item['memo'], item['owner'], item['date'], item['catid'], item['color']))
        self.app.conn.commit()
        self.parent_textEdit.append(_("Code added: ") + item['name'])
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False

    def add_category(self):
        """ Add a new category.
        Note: the addItem dialog does the checking for duplicate category names
        Add the new category as a top level item. """

        ui = DialogAddItemName(self.app, self.categories, _("Category"), _("Category name"))
        ui.exec_()
        new_name = ui.get_new_name()
        if new_name is None:
            return
        # add to database
        item = {'name': new_name, 'cid': None, 'memo': "",
                'owner': self.app.settings['codername'],
                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
        cur = self.app.conn.cursor()
        cur.execute("insert into code_cat (name, memo, owner, date, supercatid) values(?,?,?,?,?)"
                    , (item['name'], item['memo'], item['owner'], item['date'], None))
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False

    def delete_category_or_code(self, selected):
        """ Determine if category or code is to be deleted. """

        if selected.text(1)[0:3] == 'cat':
            self.delete_category(selected)
            return  # avoid error as selected is now None
        if selected.text(1)[0:3] == 'cid':
            self.delete_code(selected)

    def delete_code(self, selected):
        """ Find code, remove from database, refresh and code_name data and fill
        treeWidget. """

        # find the code_in the list, check to delete
        found = -1
        for i in range(0, len(self.codes)):
            if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                found = i
        if found == -1:
            return
        code_ = self.codes[found]
        ui = DialogConfirmDelete(self.app, _("Code: ") + selected.text(0))
        ok = ui.exec_()
        if not ok:
            return
        cur = self.app.conn.cursor()
        cur.execute("delete from code_name where cid=?", [code_['cid'], ])
        cur.execute("delete from code_av where cid=?", [code_['cid'], ])
        cur.execute("delete from code_image where cid=?", [code_['cid'], ])
        cur.execute("delete from code_text where cid=?", [code_['cid'], ])
        self.app.conn.commit()
        self.parent_textEdit.append(_("Code deleted: ") + code_['name'])
        selected = None
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False

    def delete_category(self, selected):
        """ Find category, remove from database, refresh categories and code data
        and fill treeWidget. """

        found = -1
        for i in range(0, len(self.categories)):
            if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                found = i
        if found == -1:
            return
        category = self.categories[found]
        ui = DialogConfirmDelete(self.app, _("Category: ") + selected.text(0))
        ok = ui.exec_()
        if not ok:
            return
        cur = self.app.conn.cursor()
        cur.execute("update code_name set catid=null where catid=?", [category['catid'], ])
        cur.execute("update code_cat set supercatid=null where catid = ?", [category['catid'], ])
        cur.execute("delete from code_cat where catid = ?", [category['catid'], ])
        self.app.conn.commit()
        self.parent_textEdit.append(_("Category deleted: ") + category['name'])
        selected = None
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False

    def add_edit_code_memo(self, selected):
        """ View and edit a memo. """

        if selected.text(1)[0:3] == 'cid':
            # find the code in the list
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                    found = i
            if found == -1:
                return
            ui = DialogMemo(self.app, _("Memo for Code ") + self.codes[found]['name'],
                            self.codes[found]['memo'])
            ui.exec_()
            memo = ui.memo
            if memo == "":
                selected.setData(2, QtCore.Qt.DisplayRole, "")
            else:
                selected.setData(2, QtCore.Qt.DisplayRole, _("Memo"))
            # update codes list and database
            if memo != self.codes[found]['memo']:
                self.codes[found]['memo'] = memo
                cur = self.app.conn.cursor()
                cur.execute("update code_name set memo=? where cid=?", (memo, self.codes[found]['cid']))
                self.app.conn.commit()
                self.app.delete_backup = False

        if selected.text(1)[0:3] == 'cat':
            # find the category in the list
            found = -1
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                    found = i
            if found == -1:
                return
            ui = DialogMemo(self.app, _("Memo for Category ") + self.categories[found]['name'],
                            self.categories[found]['memo'])
            ui.exec_()
            memo = ui.memo
            if memo == "":
                selected.setData(2, QtCore.Qt.DisplayRole, "")
            else:
                selected.setData(2, QtCore.Qt.DisplayRole, _("Memo"))
            # update codes list and database
            if memo != self.categories[found]['memo']:
                self.categories[found]['memo'] = memo
                cur = self.app.conn.cursor()
                cur.execute("update code_cat set memo=? where catid=?", (memo, self.categories[found]['catid']))
                self.app.conn.commit()
                self.app.delete_backup = False
        self.update_dialog_codes_and_categories()

    def rename_category_or_code(self, selected):
        """ Rename a code or category. Checks that the proposed code or category name is
        not currently in use. """

        if selected.text(1)[0:3] == 'cid':
            new_name, ok = QtWidgets.QInputDialog.getText(self, _("Rename code"), _("New code name:"),
                                                          QtWidgets.QLineEdit.Normal, selected.text(0))
            if not ok or new_name == '':
                return
            # check that no other code has this text
            for c in self.codes:
                if c['name'] == new_name:
                    mb = QtWidgets.QMessageBox()
                    mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
                    mb.setWindowTitle(_('Name in use'))
                    mb.setText(new_name + _(" Name already in use, choose another."))
                    mb.exec_()
                    return
            # find the code in the list
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                    found = i
            if found == -1:
                return
            # update codes list and database
            cur = self.app.conn.cursor()
            cur.execute("update code_name set name=? where cid=?", (new_name, self.codes[found]['cid']))
            self.app.conn.commit()
            self.parent_textEdit.append(_("Code renamed: ") + self.codes[found]['name'] + " ==> " + new_name)
            self.update_dialog_codes_and_categories()
            self.app.delete_backup = False
            return

        if selected.text(1)[0:3] == 'cat':
            new_name, ok = QtWidgets.QInputDialog.getText(self, _("Rename category"), _("New category name:"),
                                                          QtWidgets.QLineEdit.Normal, selected.text(0))
            if not ok or new_name == '':
                return
            # check that no other category has this text
            for c in self.categories:
                if c['name'] == new_name:
                    msg = _("This category name is already in use")
                    mb = QtWidgets.QMessageBox()
                    mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
                    mb.setWindowTitle(_('Duplicate category name'))
                    mb.setText(msg)
                    mb.exec_()
                    return
            # find the category in the list
            found = -1
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                    found = i
            if found == -1:
                return
            # update category list and database
            cur = self.app.conn.cursor()
            cur.execute("update code_cat set name=? where catid=?",
                        (new_name, self.categories[found]['catid']))
            self.app.conn.commit()
            self.parent_textEdit.append(_("Category renamed: ") + self.categories[found]['name'] + " ==> " + new_name)
            self.update_dialog_codes_and_categories()
            self.app.delete_backup = False

    def change_code_color(self, selected):
        """ Change the color of the currently selected code. """

        cid = int(selected.text(1)[4:])
        found = -1
        for i in range(0, len(self.codes)):
            if self.codes[i]['cid'] == cid:
                found = i
        if found == -1:
            return
        ui = DialogColorSelect(self.codes[found]['color'])
        ok = ui.exec_()
        if not ok:
            return
        new_color = ui.get_color()
        if new_color is None:
            return
        selected.setBackground(0, QBrush(QtGui.QColor(new_color), Qt.SolidPattern))
        # update codes list and database
        self.codes[found]['color'] = new_color
        cur = self.app.conn.cursor()
        cur.execute("update code_name set color=? where cid=?",
                    (self.codes[found]['color'], self.codes[found]['cid']))
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False

    # Methods used with the textEdit transcribed text
    def unlight(self):
        """ Remove all text highlighting from current file. """

        if self.transcription is None or self.ui.textEdit.toPlainText() == "":
            return
        cursor = self.ui.textEdit.textCursor()
        cursor.setPosition(0, QtGui.QTextCursor.MoveAnchor)
        cursor.setPosition(len(self.transcription[1]) - 1, QtGui.QTextCursor.KeepAnchor)
        cursor.setCharFormat(QtGui.QTextCharFormat())

    def highlight(self):
        """ Apply text highlighting to current file.
        If no colour has been assigned to a code, those coded text fragments are coloured gray.
        Each code text item contains: fid, date, pos0, pos1, seltext, cid, status, memo,
        name, owner. """

        fmt = QtGui.QTextCharFormat()
        cursor = self.ui.textEdit.textCursor()

        # add coding highlights
        for item in self.code_text:
            cursor.setPosition(int(item['pos0']), QtGui.QTextCursor.MoveAnchor)
            cursor.setPosition(int(item['pos1']), QtGui.QTextCursor.KeepAnchor)
            color = "#F8E0E0"  # default light red
            for fcode in self.codes:
                if fcode['cid'] == item['cid']:
                    color = fcode['color']
            fmt.setBackground(QtGui.QBrush(QtGui.QColor(color)))
            # highlight codes with memos - these are italicised
            if item['memo'] is not None and item['memo'] != "":
                fmt.setFontItalic(True)
            else:
                fmt.setFontItalic(False)
                fmt.setFontWeight(QtGui.QFont.Normal)
            cursor.setCharFormat(fmt)

        # add annotation marks - these are in bold
        for note in self.annotations:
            if note['fid'] == self.transcription[0]:
                cursor.setPosition(int(note['pos0']), QtGui.QTextCursor.MoveAnchor)
                cursor.setPosition(int(note['pos1']), QtGui.QTextCursor.KeepAnchor)
                formatB = QtGui.QTextCharFormat()
                formatB.setFontWeight(QtGui.QFont.Bold)
                cursor.mergeCharFormat(formatB)

    def textEdit_menu(self, position):
        """ Context menu for textEdit. Mark, unmark, annotate, copy. """

        if self.ui.checkBox_scroll_transcript.isChecked():
            return

        cursor = self.ui.textEdit.cursorForPosition(position)
        selectedText = self.ui.textEdit.textCursor().selectedText()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_unmark = None
        action_start_pos = None
        action_end_pos = None
        action_play_text = None
        play_text_avid = None
        for item in self.code_text:
            if cursor.position() >= item['pos0'] and cursor.position() <= item['pos1']:
                if item['avid'] is not None:
                    action_play_text = menu.addAction(_("Play text"))
                    play_text_avid = item['avid']
                action_unmark = menu.addAction(_("Unmark"))
                action_start_pos = menu.addAction(_("Change start position"))
                action_end_pos = menu.addAction(_("Change end position"))
                break
        if selectedText != "":
            if self.ui.treeWidget.currentItem() is not None:
                action_mark = menu.addAction(_("Mark"))
            action_annotate = menu.addAction(_("Annotate"))
            action_copy = menu.addAction(_("Copy to clipboard"))
            if self.segment_for_text is None:
                action_link_text_to_segment = menu.addAction(_("Prepare text_link to segment"))
            if self.segment_for_text is not None:
                action_link_segment_to_text = menu.addAction(_("Link to segment to text"))
        action_video_position_timestamp = -1
        for ts in self.time_positions:
            # print(ts, cursor.position())
            if cursor.position() >= ts[0] and cursor.position() <= ts[1]:
                action_video_position_timestamp = menu.addAction(_("Video position to timestamp"))
        action = menu.exec_(self.ui.textEdit.mapToGlobal(position))
        if action is None:
            return
        if selectedText != "" and action == action_copy:
            self.copy_selected_text_to_clipboard()
        if selectedText != "" and self.ui.treeWidget.currentItem() is not None and action == action_mark:
            self.mark()
        if action_unmark is not None and action == action_unmark:
            self.unmark(cursor.position())
        if action_play_text is not None and action == action_play_text:
            self.play_text(play_text_avid)
        if selectedText != "" and action == action_annotate:
            self.annotate(cursor.position())
        try:
            if action == action_video_position_timestamp:
                self.set_video_to_timestamp_position(cursor.position())
        except:
            pass
        if self.segment_for_text is None and selectedText != "" and action == action_link_text_to_segment:
            self.prepare_link_text_to_segment()
        if self.segment_for_text is not None and selectedText != "" and action == action_link_segment_to_text:
            self.link_segment_to_text()
        if action == action_start_pos:
            self.change_text_code_pos(cursor.position(), "start")
        if action == action_end_pos:
            self.change_text_code_pos(cursor.position(), "end")

    def change_text_code_pos(self, location, start_or_end):
        if self.filename == {}:
            return
        code_list = []
        for item in self.code_text:
            if location >= item['pos0'] and location <= item['pos1'] and item['owner'] == self.app.settings[
                'codername']:
                code_list.append(item)
        if code_list == []:
            return
        code_to_edit = None
        if len(code_list) == 1:
            code_to_edit = code_list[0]
        # multiple codes to selet from
        if len(code_list) > 1:
            ui = DialogSelectItems(self.app, code_list, _("Select code to unmark"), "single")
            ok = ui.exec_()
            if not ok:
                return
            code_to_edit = ui.get_selected()
        if code_to_edit is None:
            return
        txt_len = len(self.ui.textEdit.toPlainText())
        changed_start = 0
        changed_end = 0
        if start_or_end == "start":
            max = code_to_edit['pos1'] - code_to_edit['pos0'] - 1
            min = -1 * code_to_edit['pos0']
            print("start", min, max)
            changed_start, ok = QtWidgets.QInputDialog.getInt(self, _("Change start position"), _(
                "Change start character position.\nPositive or negative number:"), 0, min, max, 1)
            if not ok:
                return
        if start_or_end == "end":
            max = txt_len - code_to_edit['pos1']
            min = code_to_edit['pos0'] - code_to_edit['pos1'] + 1
            print("end", min, max)
            changed_end, ok = QtWidgets.QInputDialog.getInt(self, _("Change end position"), _(
                "Change end character position.\nPositive or negative number:"), 0, min, max, 1)
            if not ok:
                return
        if changed_start == 0 and changed_end == 0:
            return

        # Update db, reload code_text and highlights
        new_pos0 = code_to_edit['pos0'] + changed_start
        new_pos1 = code_to_edit['pos1'] + changed_end
        cur = self.app.conn.cursor()
        sql = "update code_text set pos0=?, pos1=? where cid=? and fid=? and pos0=? and pos1=? and owner=?"
        cur.execute(sql,
                    (new_pos0, new_pos1, code_to_edit['cid'], code_to_edit['fid'], code_to_edit['pos0'],
                     code_to_edit['pos1'], self.app.settings['codername']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def play_text(self, avid):
        """ Play the audio/video for this coded text selection that is mapped to an a/v segment. """

        segment = None
        for s in self.segments:
            if s['avid'] == avid:
                segment = s
                break
        if segment is None:
            return
        pos = segment['pos0'] / self.mediaplayer.get_media().get_duration()
        self.mediaplayer.play()
        self.mediaplayer.set_position(pos)
        self.is_paused = False
        self.ui.pushButton_play.setText(_("Pause"))
        self.play_segment_end = segment['pos1']
        self.timer.start()

    def link_segment_to_text(self):
        """ Link selected segment to selected text. """

        item = {}
        item['cid'] = self.segment_for_text['cid']
        item['fid'] = self.transcription[0]
        item['seltext'] = self.ui.textEdit.textCursor().selectedText()
        item['pos0'] = self.ui.textEdit.textCursor().selectionStart()
        item['pos1'] = self.ui.textEdit.textCursor().selectionEnd()
        item['owner'] = self.app.settings['codername']
        item['memo'] = ""
        item['date'] = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        item['avid'] = self.segment_for_text['avid']
        cur = self.app.conn.cursor()
        # check for an existing duplicated marking first
        cur.execute("select * from code_text where cid = ? and fid=? and pos0=? and pos1=? and owner=?",
                    (item['cid'], item['fid'], item['pos0'], item['pos1'], item['owner']))
        result = cur.fetchall()
        if len(result) > 0:
            mb = QtWidgets.QMessageBox()
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            mb.setWindowTitle(_('Already Coded'))
            mb.setText(_("This segment has already been coded with this code by ") + item['owner'])
            mb.exec_()
            return
        # Should not get sqlite3.IntegrityError:
        # UNIQUE constraint failed: code_text.cid, code_text.fid, code_text.pos0, code_text.pos1
        try:
            cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,\
            memo,date,avid) values(?,?,?,?,?,?,?,?,?)", (item['cid'], item['fid'],
                                                         item['seltext'], item['pos0'], item['pos1'], item['owner'],
                                                         item['memo'], item['date'], item['avid']))
            self.app.conn.commit()
            self.app.delete_backup = False
        except Exception as e:
            logger.debug(str(e))
        # update codes and filter for tooltip
        self.get_coded_text_update_eventfilter_tooltips()

    def prepare_link_text_to_segment(self):
        """ Select text in transcription and prepare variable to be linked to a/v segment. """

        selected_text = self.ui.textEdit.textCursor().selectedText()
        pos0 = self.ui.textEdit.textCursor().selectionStart()
        pos1 = self.ui.textEdit.textCursor().selectionEnd()
        if pos0 == pos1:
            return
        self.text_for_segment['cid'] = None
        self.text_for_segment['fid'] = self.transcription[0]
        self.text_for_segment['seltext'] = selected_text
        self.text_for_segment['pos0'] = pos0
        self.text_for_segment['pos1'] = pos1
        self.text_for_segment['owner'] = self.app.settings['codername']
        self.text_for_segment['memo'] = ""
        self.text_for_segment['date'] = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        self.text_for_segment['avid'] = None

    def set_video_to_timestamp_position(self, position):
        """ Set the video position to this time stamp.
        The horizontal slider will move to match the position of the video (in update_ui).
        """

        timestamp = None
        for ts in self.time_positions:
            if position >= ts[0] and position <= ts[1]:
                timestamp = ts
        if timestamp is None:
            return
        self.timer.stop()
        self.mediaplayer.set_position(timestamp[2] / self.media.get_duration())
        self.timer.start()

    def copy_selected_text_to_clipboard(self):
        """ Copy text to clipboard for external use.
        For example adding text to another document. """

        selectedText = self.ui.textEdit.textCursor().selectedText()
        cb = QtWidgets.QApplication.clipboard()
        cb.clear(mode=cb.Clipboard)
        cb.setText(selectedText, mode=cb.Clipboard)

    def mark(self):
        """ Mark selected text in file with currently selected code.
       Need to check for multiple same codes at same pos0 and pos1.
       """

        if self.transcription is None or self.ui.textEdit.toPlainText() == "":
            mb = QtWidgets.QMessageBox()
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            mb.setWindowTitle(_('Warning'))
            mb.setText(_('No transcription'))
            mb.exec_()
            return
        item = self.ui.treeWidget.currentItem()
        if item is None:
            mb = QtWidgets.QMessageBox()
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            mb.setWindowTitle(_('Warning'))
            mb.setText(_("No code was selected"))
            mb.exec_()
            return
        if item.text(1).split(':')[0] == 'catid':  # must be a code
            return
        cid = int(item.text(1).split(':')[1])
        selectedText = self.ui.textEdit.textCursor().selectedText()
        pos0 = self.ui.textEdit.textCursor().selectionStart()
        pos1 = self.ui.textEdit.textCursor().selectionEnd()
        if pos0 == pos1:  # Something quirky happened
            return
        # add the coded section to code text, add to database and update GUI
        coded = {'cid': cid, 'fid': self.transcription[0], 'seltext': selectedText,
                 'pos0': pos0, 'pos1': pos1, 'owner': self.app.settings['codername'], 'memo': "",
                 'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}

        cur = self.app.conn.cursor()
        # check for an existing duplicated marking first
        cur.execute("select * from code_text where cid = ? and fid=? and pos0=? and pos1=? and owner=?",
                    (coded['cid'], coded['fid'], coded['pos0'], coded['pos1'], coded['owner']))
        result = cur.fetchall()
        if len(result) > 0:
            mb = QtWidgets.QMessageBox()
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            mb.setWindowTitle(_('Already Coded'))
            mb.setText(_("This segment has already been coded with this code by ") + coded['owner'])
            mb.exec_()
            return

        self.code_text.append(coded)
        self.highlight()

        # Should not get sqlite3.IntegrityError:
        # UNIQUE constraint failed: code_text.cid, code_text.fid, code_text.pos0, code_text.pos1
        try:
            cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,\
                memo,date) values(?,?,?,?,?,?,?,?)", (coded['cid'], coded['fid'],
                                                      coded['seltext'], coded['pos0'], coded['pos1'], coded['owner'],
                                                      coded['memo'], coded['date']))
            self.app.conn.commit()
            self.app.delete_backup = False
        except Exception as e:
            logger.debug(str(e))
        # update coded, filter for tooltip
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()

    def unmark(self, location):
        """ Remove code marking by this coder from selected text in current file. """

        if self.transcription is None or self.ui.textEdit.toPlainText() == "":
            return
        to_unmark = None
        for item in self.code_text:
            if location >= item['pos0'] and location <= item['pos1'] and item['owner'] == self.app.settings[
                'codername']:
                to_unmark = item
        if to_unmark is None:
            return

        # delete from db, remove from coding and update highlights
        cur = self.app.conn.cursor()
        cur.execute("delete from code_text where cid=? and pos0=? and pos1=? and owner=? and fid=?",
                    (to_unmark['cid'], to_unmark['pos0'], to_unmark['pos1'], self.app.settings['codername'],
                     to_unmark['fid']))
        self.app.conn.commit()
        self.app.delete_backup = False
        # update filter for tooltip and update code colours
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()

    def annotate(self, location):
        """ Add view, or remove an annotation for selected text.
        Annotation positions are displayed as bold text.
        """

        if self.transcription is None or self.ui.textEdit.toPlainText() == "":
            mb = QtWidgets.QMessageBox()
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            mb.setWindowTitle(_('Warning'))
            mb.setText(_("No media transcription selected"))
            mb.exec_()
            return
        pos0 = self.ui.textEdit.textCursor().selectionStart()
        pos1 = self.ui.textEdit.textCursor().selectionEnd()
        text_length = len(self.ui.textEdit.toPlainText())
        if pos0 >= text_length or pos1 >= text_length:
            return
        item = None
        details = ""
        annotation = ""
        # find existing annotation at this position for this file
        for note in self.annotations:
            if location >= note['pos0'] and location <= note['pos1'] and note['fid'] == self.transcription[0]:
                item = note  # use existing annotation
                details = item['owner'] + " " + item['date']
        # exit method if no text selected and there is not annotation at this position
        if pos0 == pos1 and item is None:
            return
        # add new item to annotations, add to database and update GUI
        if item is None:
            item = {'fid': self.transcription[0], 'pos0': pos0, 'pos1': pos1,
                    'memo': str(annotation), 'owner': self.app.settings['codername'],
                    'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'anid': -1}
        ui = DialogMemo(self.app, _("Annotation: ") + details, item['memo'])
        ui.exec_()
        item['memo'] = ui.memo
        if item['memo'] != "":
            cur = self.app.conn.cursor()
            cur.execute("insert into annotation (fid,pos0, pos1,memo,owner,date) \
                values(?,?,?,?,?,?)", (item['fid'], item['pos0'], item['pos1'],
                                       item['memo'], item['owner'], item['date']))
            self.app.conn.commit()
            self.app.delete_backup = False
            cur.execute("select last_insert_rowid()")
            anid = cur.fetchone()[0]
            item['anid'] = anid
            self.annotations.append(item)
            self.highlight()
            self.parent_textEdit.append(_("Annotation added at position: ") \
                                        + str(item['pos0']) + "-" + str(item['pos1']) + _(" for: ") +
                                        self.transcription[2])
        # if blank delete the annotation
        if item['memo'] == "":
            cur = self.app.conn.cursor()
            cur.execute("delete from annotation where pos0 = ?", (item['pos0'],))
            self.app.conn.commit()
            for note in self.annotations:
                if note['pos0'] == item['pos0'] and note['fid'] == item['fid']:
                    self.annotations.remove(note)
            self.parent_textEdit.append(_("Annotation removed from position ") \
                                        + str(item['pos0']) + _(" for: ") + self.transcription[2])
        self.unlight()
        self.highlight()


class ToolTip_EventFilter(QtCore.QObject):
    """ Used to add a dynamic tooltip for the textEdit.
    The tool top text is changed according to its position in the text.
    If over a coded section the codename is displayed in the tooltip.
    Need to add av time segments to the code_text where relevant.
    """

    codes = None
    code_text = None

    def setCodes(self, code_text, codes):
        self.code_text = code_text
        self.codes = codes
        for item in self.code_text:
            for c in self.codes:
                if item['cid'] == c['cid']:
                    item['name'] = c['name']

    def eventFilter(self, receiver, event):
        # QtGui.QToolTip.showText(QtGui.QCursor.pos(), tip)
        if event.type() == QtCore.QEvent.ToolTip:
            helpEvent = QHelpEvent(event)
            cursor = QtGui.QTextCursor()
            cursor = receiver.cursorForPosition(helpEvent.pos())
            pos = cursor.position()
            receiver.setToolTip("")
            text = ""
            # occasional None type error
            if self.code_text is None:
                # Call Base Class Method to Continue Normal Event Processing
                return super(ToolTip_EventFilter, self).eventFilter(receiver, event)
            for item in self.code_text:
                if item['pos0'] <= pos and item['pos1'] >= pos:
                    # print(item)
                    try:
                        if text != "":
                            text = text + "\n"
                        text += item['name']  # += as can have multiple codes on same position
                        if item['avid'] is not None:
                            text += " [" + msecs_to_mins_and_secs(item['av_pos0'])
                            text += " - " + msecs_to_mins_and_secs(item['av_pos1']) + "]"
                    except Exception as e:
                        msg = "Codes ToolTipEventFilter " + str(e) + ". Possible key error: "
                        msg += str(item) + "\n" + str(self.code_text)
                        logger.error(msg)
            if text != "":
                receiver.setToolTip(text)
        # Call Base Class Method to Continue Normal Event Processing
        return super(ToolTip_EventFilter, self).eventFilter(receiver, event)


class GraphicsScene(QtWidgets.QGraphicsScene):
    """ set the scene for the graphics objects and re-draw events. """

    def __init__(self, width, height, parent=None):
        super(GraphicsScene, self).__init__(parent)
        self.scene_width = width
        self.scene_height = height
        self.setSceneRect(QtCore.QRectF(0, 0, self.scene_width, self.scene_height))

    '''def set_width(self, width):
        """ Resize scene width. Not currently used. """

        self.sceneWidth = width
        self.setSceneRect(QtCore.QRectF(0, 0, self.scene_width, self.scene_height))

    def set_height(self, height):
        """ Resize scene height. Not currently used. """

        self.sceneHeight = height
        self.setSceneRect(QtCore.QRectF(0, 0, self.scene_width, self.scene_height))

    def get_width(self):
        """ Return scene width. Not currently used. """

        return self.scene_width

    def get_height(self):
        """ Return scene height. Not currently used. """

        return self.scene_height

    def mouseMoveEvent(self, mouseEvent):
        super(GraphicsScene, self).mousePressEvent(mouseEvent)

        for i in self.scene.items():
            if isinstance(i, SegmentGraphicsItem) and i.reload_segment is True:
                self.load_segments()
        self.update()'''

    """def mousePressEvent(self, mouseEvent):
        super(GraphicsScene, self).mousePressEvent(mouseEvent)
        #position = QtCore.QPointF(event.scenePos())
        #logger.debug("pressed here: " + str(position.x()) + ", " + str(position.y()))
        for item in self.items(): # item is QGraphicsProxyWidget
            if isinstance(item, LinkItem):
                item.redraw()
        self.update(self.sceneRect())"""

    """def mouseReleaseEvent(self, mouseEvent):
        ''' On mouse release, an item might be repositioned so need to redraw all the
        link_items '''

        super(GraphicsScene, self).mouseReleaseEvent(mouseEvent)
        for item in self.items():
            if isinstance(item, LinkGraphicsItem):
                item.redraw()
        self.update(self.sceneRect())"""


class SegmentGraphicsItem(QtWidgets.QGraphicsLineItem):
    """ Draws coded segment line. The media duration determines the scaler for the line length and position.
    y values are pre-calculated and stored in the segment data.
    Refernces Dialog_code_av for variables and methods.
    """

    app = None
    segment = None
    scaler = None
    reload_segment = False
    code_av_dialog = None

    def __init__(self, app, segment, scaler, text_for_segment, code_av_dialog):
        super(SegmentGraphicsItem, self).__init__(None)

        self.app = app
        self.segment = segment
        self.scaler = scaler
        self.code_av_dialog = code_av_dialog
        self.reload_segment = False
        self.setFlag(self.ItemIsSelectable, True)
        tooltip = self.segment['codename'] + " "
        seg_time = "[" + msecs_to_mins_and_secs(self.segment['pos0']) + " - "
        seg_time += msecs_to_mins_and_secs(self.segment['pos1']) + "]"
        tooltip += seg_time
        if self.segment['memo'] != "":
            tooltip += "\n" + _("Memo: ") + self.segment['memo']
        self.setToolTip(tooltip)
        self.draw_segment()

    def contextMenuEvent(self, event):
        """
        # https://riverbankcomputing.com/pipermail/pyqt/2010-July/027094.html
        I was not able to mapToGlobal position so, the menu maps to scene position plus
        the Dialog screen position.
        """

        action_link_segment = 1
        action_link_text = 1
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_memo = menu.addAction(_('Memo for segment'))
        action_delete = menu.addAction(_('Delete segment'))
        action_play = menu.addAction(_('Play segment'))
        action_edit_start = menu.addAction(_('Edit segment start position'))
        action_edit_end = menu.addAction(_('Edit segment end position'))
        if self.code_av_dialog.text_for_segment['seltext'] is not None:
            action_link_text = menu.addAction(_('Link text to segment'))
        if self.code_av_dialog.text_for_segment[
            'seltext'] is None and self.code_av_dialog.ui.textEdit.toPlainText() != "":
            action_link_segment = menu.addAction(_("Select segment to link to text"))
        action = menu.exec_(QtGui.QCursor.pos())
        if action is None:
            return
        if action == action_memo:
            self.edit_memo()
        if action == action_delete:
            self.delete()
        if action == action_play:
            self.play_segment()
        if action == action_edit_start:
            self.edit_segment_start()
        if action == action_edit_end:
            self.edit_segment_end()
        if self.code_av_dialog.text_for_segment['seltext'] is not None and action == action_link_text:
            self.link_text_to_segment()
        if self.code_av_dialog.text_for_segment['seltext'] is None and action == action_link_segment:
            self.link_segment_to_text()

    def link_segment_to_text(self):
        """ Prepare Dialog_code_av to link segment to text """

        self.code_av_dialog.segment_for_text = self.segment

    def link_text_to_segment(self):
        """ Link text to this segment. this will add a code to the text and insert
        a code_text entry into database. """

        seg = self.code_av_dialog.text_for_segment
        seg['cid'] = self.segment['cid']
        seg['avid'] = self.segment['avid']
        # check for an existing duplicated marking first
        cur = self.code_av_dialog.app.conn.cursor()
        cur.execute("select * from code_text where cid = ? and fid=? and pos0=? and pos1=? and owner=?",
                    (seg['cid'], seg['fid'], seg['pos0'], seg['pos1'], seg['owner']))
        result = cur.fetchall()
        if len(result) > 0:
            mb = QtWidgets.QMessageBox()
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            mb.setWindowTitle(_('Already Coded'))
            mb.setText(_("This segment has already been coded with this code."))
            mb.exec_()
            return
        try:
            cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,\
            memo,date, avid) values(?,?,?,?,?,?,?,?,?)", (seg['cid'],
                                                          seg['fid'], seg['seltext'], seg['pos0'], seg['pos1'],
                                                          seg['owner'], seg['memo'], seg['date'], seg['avid']))
            self.code_av_dialog.app.conn.commit()
            self.app.delete_backup = False
        except Exception as e:
            print(e)
        # print(self.code_av_dialog.text_for_segment)  # tmp
        self.code_av_dialog.get_coded_text_update_eventfilter_tooltips()
        self.code_av_dialog.text_for_segment = {'cid': None, 'fid': None, 'seltext': None, 'pos0': None, 'pos1': None,
                                                'owner': None, 'memo': None, 'date': None, 'avid': None}

    def edit_segment_start(self):
        """ Edit segment start time. """

        i, ok_pressed = QtWidgets.QInputDialog.getInt(None, "Segment start in mseconds",
                                                      "Edit time in milliseconds\n1000 msecs = 1 second:",
                                                      self.segment['pos0'], 1,
                                                      self.segment['pos1'] - 1, 5)
        if not ok_pressed:
            return
        if i < 1:
            return
        self.segment['pos0'] = i
        sql = "update code_av set pos0=? where avid=?"
        cur = self.code_av_dialog.app.conn.cursor()
        cur.execute(sql, [i, self.segment['avid']])
        self.code_av_dialog.app.conn.commit()
        self.draw_segment()
        self.app.delete_backup = False

    def edit_segment_end(self):
        """ Edit segment end time """

        duration = self.code_av_dialog.media.get_duration()
        i, ok_pressed = QtWidgets.QInputDialog.getInt(None, "Segment end in mseconds",
                                                      "Edit time in milliseconds\n1000 msecs = 1 second:",
                                                      self.segment['pos1'],
                                                      self.segment['pos0'] + 1, duration - 1, 5)
        if not ok_pressed:
            return
        if i < 1:
            return
        self.segment['pos1'] = i
        sql = "update code_av set pos1=? where avid=?"
        cur = self.code_av_dialog.app.conn.cursor()
        cur.execute(sql, [i, self.segment['avid']])
        self.code_av_dialog.app.conn.commit()
        self.draw_segment()
        self.app.delete_backup = False

    def play_segment(self):
        """ Play segment section. Stop at end of segment. """

        pos = self.segment['pos0'] / self.code_av_dialog.mediaplayer.get_media().get_duration()
        self.code_av_dialog.mediaplayer.play()
        self.code_av_dialog.mediaplayer.set_position(pos)
        self.code_av_dialog.is_paused = False
        self.code_av_dialog.ui.pushButton_play.setText(_("Pause"))
        self.code_av_dialog.play_segment_end = self.segment['pos1']
        self.code_av_dialog.timer.start()

    def delete(self):
        """ Mark segment for deletion. Does not actually delete segment item, but hides
        it from the scene. Reload_segment is set to True, so on playing media, the update
        event will reload all segments. """

        # print(self.segment)
        ui = DialogConfirmDelete(self.app,
                                 _("Segment: ") + self.segment['codename'] + "\n" + _("Memo: ") + self.segment['memo'])
        ok = ui.exec_()
        if not ok:
            return

        self.setToolTip("")
        self.setLine(-100, -100, -100, -100)
        self.segment['memo'] = ""
        self.segment['pos0'] = -100
        self.segment['pos1'] = -100
        self.segment['y'] = -100
        self.reload_segment = True
        sql = "delete from code_av where avid=?"
        values = [self.segment['avid']]
        cur = self.code_av_dialog.app.conn.cursor()
        cur.execute(sql, values)
        sql = "update code_text set avid=null where avid=?"
        cur.execute(sql, values)
        self.code_av_dialog.app.conn.commit()
        self.code_av_dialog.get_coded_text_update_eventfilter_tooltips()
        self.app.delete_backup = False

    def edit_memo(self):
        """ View, edit or delete memo for this segment.
        Reload_segment is set to True, so on playing media, the update event will reload
        all segments. """

        ui = DialogMemo(self.code_av_dialog.app, _("Memo for segment"), self.segment["memo"])
        ui.exec_()
        if self.segment['memo'] == ui.memo:
            return
        self.reload_segment = True
        self.segment['memo'] = ui.memo
        sql = "update code_av set memo=?, date=? where avid=?"
        values = [self.segment['memo'],
                  datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), self.segment['avid']]
        cur = self.code_av_dialog.app.conn.cursor()
        cur.execute(sql, values)
        self.code_av_dialog.app.conn.commit()
        self.app.delete_backup = False
        tooltip = self.segment['codename'] + " "
        seg_time = "[" + msecs_to_mins_and_secs(self.segment['pos0']) + " - "
        seg_time += msecs_to_mins_and_secs(self.segment['pos1']) + "]"
        tooltip += seg_time
        if self.segment['memo'] != "":
            tooltip += "\nMemo: " + self.segment['memo']
        self.setToolTip(tooltip)

    def redraw(self):
        """ Called from mouse move and release events. Not currently used. """

        self.draw_segment()

    def draw_segment(self):
        """ Calculate the x values for the line. """

        from_x = self.segment['pos0'] * self.scaler
        to_x = self.segment['pos1'] * self.scaler
        line_width = 8
        color = QtGui.QColor(self.segment['color'])
        self.setPen(QtGui.QPen(color, line_width, QtCore.Qt.SolidLine))
        self.setLine(from_x, self.segment['y'], to_x, self.segment['y'])


class DialogViewAV(QtWidgets.QDialog):
    """ View Audio and Video using VLC. View and edit displayed memo.
    Mouse events did not work when the vlc play is in this dialog.
    Mouse events do work with the vlc player in a separate modal dialog.

    Linked a/v have 'audio:' or 'video:' at start of mediapath
    """

    app = None
    label = None
    media_data = None
    is_paused = False
    media_duration_text = ""
    displayframe = None
    ddialog = None
    instance = None
    mediaplayer = None
    media = None
    transcription = None
    time_positions = []
    speaker_list = []
    can_transcribe = True

    def __init__(self, app, media_data, parent=None):

        """ Media_data contains: {name, mediapath, owner, id, date, memo, fulltext}
        A separate modal dialog is created to display the video.
        """

        sys.excepthook = exception_handler
        self.app = app
        self.media_data = media_data
        abs_path = ""
        if self.media_data['mediapath'][0:6] in ('/audio', '/video'):
            abs_path = self.app.project_path + self.media_data['mediapath']
        if self.media_data['mediapath'][0:6] in ('audio:', 'video:'):
            abs_path = self.media_data['mediapath'][6:]
        self.is_paused = True
        self.time_positions = []
        self.speaker_list = []
        self.can_transcribe = True

        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_view_av()
        self.ui.setupUi(self)
        try:
            w = int(self.app.settings['dialogviewav_w'])
            h = int(self.app.settings['dialogviewav_h'])
            if h > 50 and w > 50:
                self.resize(w, h)
            x = int(self.app.settings['viewav_abs_pos_x'])
            y = int(self.app.settings['viewav_abs_pos_y'])
            self.move(self.mapToGlobal(QtCore.QPoint(x, y)))
        except:
            pass
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        font = 'font: ' + str(self.app.settings['treefontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.ui.label_speakers.setStyleSheet(font)
        self.setWindowTitle(abs_path.split('/')[-1])

        # Get the transcription text and fill textedit
        cur = self.app.conn.cursor()
        cur.execute("select id, fulltext from source where name=?", [media_data['name'] + ".transcribed"])
        self.transcription = cur.fetchone()
        if self.transcription is not None:
            self.ui.textEdit_transcription.installEventFilter(self)
            self.installEventFilter(self)  # for rewind, play/stop
            cur.execute("select cid from  code_text where fid=?", [self.transcription[0], ])
            coded = cur.fetchall()
            cur.execute("select anid from  annotation where fid=?", [self.transcription[0], ])
            annoted = cur.fetchall()
            if coded != [] or annoted != []:
                self.ui.textEdit_transcription.setReadOnly(True)
                self.can_transcribe = False
                self.ui.label_speakers.setVisible(False)
                self.ui.label_transcription.setToolTip("")
            else:
                self.ui.label_memo.setText(
                    _("Transcription area: ctrl+R alt+R alt+F ctrl+P/S ctrl+T ctrl+N ctrl+1-8 ctrl+D"))
            self.ui.textEdit_transcription.setText(self.transcription[1])
            self.get_timestamps_from_transcription()
            self.get_speaker_names_from_bracketed_text()
            self.add_speaker_names_to_label()

        # My solution to getting gui mouse events by putting vlc video in another dialog
        self.ddialog = QtWidgets.QDialog()
        # enable custom window hint - must be set to enable customizing window controls
        self.ddialog.setWindowFlags(self.ddialog.windowFlags() | QtCore.Qt.CustomizeWindowHint)
        # disable close button, only close through closing the Ui_Dialog_view_av
        self.ddialog.setWindowFlags(self.ddialog.windowFlags() & ~QtCore.Qt.WindowCloseButtonHint)
        self.ddialog.setWindowFlags(self.ddialog.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        title = abs_path.split('/')[-1]
        self.ddialog.setWindowTitle(title)
        self.ddialog.gridLayout = QtWidgets.QGridLayout(self.ddialog)
        self.ddialog.dframe = QtWidgets.QFrame(self.ddialog)
        self.ddialog.dframe.setObjectName("frame")
        if platform.system() == "Darwin":  # for MacOS
            self.ddialog.dframe = QtWidgets.QMacCocoaViewContainer(0)
        self.palette = self.ddialog.dframe.palette()
        self.palette.setColor(QtGui.QPalette.Window, QtGui.QColor(30, 30, 30))
        self.ddialog.dframe.setPalette(self.palette)
        self.ddialog.dframe.setAutoFillBackground(True)
        self.ddialog.gridLayout.addWidget(self.ddialog.dframe, 0, 0, 0, 0)
        # add context menu for ddialog
        self.ddialog.setContextMenuPolicy(Qt.CustomContextMenu)
        self.ddialog.customContextMenuRequested.connect(self.ddialog_menu)

        # Set video dialog position, with a default initial position
        self.ddialog.move(self.mapToGlobal(QtCore.QPoint(40, 20)))
        # ddialog is relative to self global position
        try:
            x = int(self.app.settings['viewav_video_pos_x']) - int(self.app.settings['viewav_abs_pos_x'])
            y = int(self.app.settings['viewav_video_pos_y']) - int(self.app.settings['viewav_abs_pos_y'])
            self.ddialog.move(self.mapToGlobal(QtCore.QPoint(x, y)))
        except:
            pass
        if self.media_data['mediapath'][0:6] not in ("/audio", "audio:"):
            self.ddialog.show()

        # Create a vlc instance
        self.instance = vlc.Instance()
        # Create an empty vlc media player
        self.mediaplayer = self.instance.media_player_new()
        self.mediaplayer.video_set_mouse_input(False)
        self.mediaplayer.video_set_key_input(False)
        self.ui.pushButton_play.clicked.connect(self.play_pause)
        self.ui.horizontalSlider_vol.valueChanged.connect(self.set_volume)
        self.ui.comboBox_tracks.currentIndexChanged.connect(self.audio_track_changed)
        self.ui.horizontalSlider.setTickPosition(QtWidgets.QSlider.NoTicks)
        self.ui.horizontalSlider.setMouseTracking(True)
        self.ui.horizontalSlider.installEventFilter(self)
        self.ui.horizontalSlider.sliderMoved.connect(self.set_position)

        try:
            self.media = self.instance.media_new(abs_path)
        except Exception as e:
            Message(self.app, _('Media not found'), str(e) + "\n" + abs_path).exec_()
            self.closeEvent()
            return
        if self.media_data['mediapath'][0:7] not in ("/audio", "audio:"):
            try:
                w = int(self.app.settings['video_w'])
                h = int(self.app.settings['video_h'])
                if w < 100 or h < 80:
                    w = 100
                    h = 80
                self.ddialog.resize(w, h)
            except:
                self.ddialog.resize(500, 400)
        else:
            self.ddialog.hide()
        # Put the media in the media player
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
            self.mediaplayer.set_xwindow(int(self.ddialog.dframe.winId()))
        elif platform.system() == "Windows":  # for Windows
            self.mediaplayer.set_hwnd(int(self.ddialog.winId()))
        elif platform.system() == "Darwin":  # for MacOS
            self.mediaplayer.set_nsobject(int(self.ddialog.winId()))
        msecs = self.media.get_duration()
        self.ui.label_time_2.setText("Duration: " + msecs_to_mins_and_secs(msecs))
        self.ui.textEdit.setText(self.media_data['memo'])
        self.ui.textEdit.ensureCursorVisible()
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.update_ui)
        self.ui.checkBox_scroll_transcript.stateChanged.connect(self.scroll_transcribed_checkbox_changed)
        # self.play_pause()

    def ddialog_menu(self, position):
        """ Context menu to export a screenshot, to resize dialog """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        ActionScreenshot = menu.addAction(_("Screenshot"))
        ActionResize = menu.addAction(_("Resize"))

        action = menu.exec_(self.ddialog.mapToGlobal(position))
        if action == ActionScreenshot:
            time.sleep(0.5)
            screen = QtWidgets.QApplication.primaryScreen()
            screenshot = screen.grabWindow(self.ddialog.winId())
            screenshot.save(self.app.settings['directory'] + '/Frame_' + datetime.datetime.now().astimezone().strftime(
                "%Y%m%d_%H_%M_%S") + '.jpg', 'jpg')
        if action == ActionResize:
            w = self.ddialog.size().width()
            h = self.ddialog.size().height()
            res_w = QtWidgets.QInputDialog.getInt(None, _("Width"), _("Width:"), w, 100, 2000, 5)
            if res_w[1]:
                w = res_w[0]
            res_h = QtWidgets.QInputDialog.getInt(None, _("Height"), _("Height:"), h, 80, 2000, 5)
            if res_h[1]:
                h = res_h[0]
            self.ddialog.resize(w, h)

    def set_position(self):
        """ Set the movie position according to the position slider.
        The vlc MediaPlayer needs a float value between 0 and 1, Qt uses
        integer variables, so you need a factor; the higher the factor, the
        more precise are the results (1000 should suffice).
        """

        # Set the media position to where the slider was dragged
        self.timer.stop()
        pos = self.ui.horizontalSlider.value()
        self.mediaplayer.set_position(pos / 1000.0)
        self.timer.start()

    def eventFilter(self, object, event):
        """ Add key options to improve manual transcribing.
        Options are:
            Ctrl + R to rewind 5 seconds.
            Alt + R rewind 30 seconds
            Alt + F forward 30 seconds
            Ctrl + S OR ctrl + P to start/pause On start rewind 1 second
        Can only use these options if the transcription is not coded:
            Ctrl + T to insert timestamp in format [hh.mm.ss]
            Ctrl + N to enter a new speakers name into shortcuts
            Ctrl + 1 .. 8 to insert speaker in format [speaker name]

            Ctrl + Shift + > to increase play rate
            Ctrl + Shift + < to decrease play rate
        """

        if object == self.ui.horizontalSlider and event.type() == QtCore.QEvent.MouseMove:
            maxx = self.ui.horizontalSlider.size().width()
            proportion = event.pos().x() / maxx
            msecs = self.media.get_duration() * proportion
            time = msecs_to_mins_and_secs(msecs)
            self.ui.horizontalSlider.setToolTip(time)

        if event.type() != 7:  # QtGui.QKeyEvent
            return False
        key = event.key()
        mods = event.modifiers()
        # print("KEY ", key, "MODS ", mods)
        #  ctrl S or ctrl P pause/play toggle
        if (key == QtCore.Qt.Key_S or key == QtCore.Qt.Key_P) and mods == QtCore.Qt.ControlModifier:
            self.play_pause()
        # Rewind 30 seconds Alt R
        if key == QtCore.Qt.Key_R and mods == QtCore.Qt.AltModifier:
            time_msecs = self.mediaplayer.get_time() - 30000
            if time_msecs < 0:
                time_msecs = 0
            pos = time_msecs / self.mediaplayer.get_media().get_duration()
            self.mediaplayer.set_position(pos)
            # Update timer display
            msecs = self.mediaplayer.get_time()
            self.ui.label_time.setText(_("Time: ") + msecs_to_mins_and_secs(msecs))
            self.update_ui()
        # Rewind 5 seconds   Ctrl R
        if key == QtCore.Qt.Key_R and mods == QtCore.Qt.ControlModifier:
            time_msecs = self.mediaplayer.get_time() - 5000
            if time_msecs < 0:
                time_msecs = 0
            pos = time_msecs / self.mediaplayer.get_media().get_duration()
            self.mediaplayer.set_position(pos)
            # Update timer display
            msecs = self.mediaplayer.get_time()
            self.ui.label_time.setText(_("Time: ") + msecs_to_mins_and_secs(msecs))
            self.update_ui()
        # Advance 30 seconds Alt F
        if key == QtCore.Qt.Key_F and mods == QtCore.Qt.AltModifier:
            time_msecs = self.mediaplayer.get_time() + 30000
            if time_msecs > self.media.get_duration():
                time_msecs = self.media.get_duration() - 1
            pos = time_msecs / self.mediaplayer.get_media().get_duration()
            self.mediaplayer.set_position(pos)
            # Update timer display
            msecs = self.mediaplayer.get_time()
            self.ui.label_time.setText(_("Time: ") + msecs_to_mins_and_secs(msecs))
            self.update_ui()
        #  Insert  timestamp Ctrl T
        if key == QtCore.Qt.Key_T and mods == QtCore.Qt.ControlModifier and self.can_transcribe:
            self.insert_timestamp()
        # Insert speaker  Ctrl 1 .. 8
        if key in range(49, 57) and mods == QtCore.Qt.ControlModifier and self.can_transcribe:
            self.insert_speakername(key)
        # Add new speaker to list  Ctrl n
        if key == QtCore.Qt.Key_N and mods == QtCore.Qt.ControlModifier and self.can_transcribe:
            self.pause()
            self.add_speakername()
        # Delete speaker name(s) from list
        if key == QtCore.Qt.Key_D and mods == QtCore.Qt.ControlModifier and self.can_transcribe:
            self.pause()
            self.delete_speakernames()
        # Increase play rate  Ctrl + Shift + >
        if key == QtCore.Qt.Key_Greater and (mods and QtCore.Qt.ShiftModifier) and (mods and QtCore.Qt.ControlModifier):
            self.increase_play_rate()
        # Decrease play rate  Ctrl + Shift + <
        if key == QtCore.Qt.Key_Less and (mods and QtCore.Qt.ShiftModifier) and (mods and QtCore.Qt.ControlModifier):
            self.decrease_play_rate()
        return True

    def increase_play_rate(self):
        """ Several increased rate options """

        rate = self.mediaplayer.get_rate()
        rate += 0.1
        if rate > 2:
            rate = 2
        self.mediaplayer.set_rate(rate)
        self.ui.label_rate.setText(_("Rate: ") + str(round(rate, 1)))

    def decrease_play_rate(self):
        """ Several decreased rate options """

        rate = self.mediaplayer.get_rate()
        rate -= 0.1
        if rate < 0.1:
            rate = 0.1
        self.mediaplayer.set_rate(rate)
        self.ui.label_rate.setText(_("Rate: ") + str(round(rate, 1)))

    def delete_speakernames(self):
        """ Delete speakername from list of shortcut names """

        if self.speaker_list == []:
            return
        # convert to list of dictionaries
        names = []
        for n in self.speaker_list:
            names.append({"name": n})
        if names == []:
            return
        ui = DialogSelectItems(self.app, names, _("Select name to delete"), "many")
        ok = ui.exec_()
        if not ok:
            return
        names = ui.get_selected()
        if names == []:
            return
        for name in names:
            self.speaker_list.remove(name['name'])
        self.add_speaker_names_to_label()

    def add_speakername(self):
        """ Add speaker name to list of shortcut names. Maximum of 8 entries. """

        if len(self.speaker_list) == 8:
            return
        d = QtWidgets.QInputDialog()
        d.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        d.setWindowFlags(d.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        d.setWindowTitle(_("Speaker name"))
        d.setLabelText(_("Name:"))
        d.setInputMode(QtWidgets.QInputDialog.TextInput)
        if d.exec() == QtWidgets.QDialog.Accepted:
            name = d.textValue()
            if name == "" or name.find('.') == 0 or name.find(':') == 0 or name.find('[') == 0 or name.find(
                    ']') == 0 or name.find('{') == 0 or name.find('}') == 0:
                return
            self.speaker_list.append(name)
            self.add_speaker_names_to_label()

    def insert_speakername(self, key):
        """ Insert speaker name using settings format of {} or [] """

        list_pos = key - 49
        speaker = ""
        try:
            speaker = self.speaker_list[list_pos]
        except:
            return False
        if self.app.settings['speakernameformat'] == "[]":
            speaker = '[' + speaker + ']'
        else:
            speaker = '{' + speaker + '}'
        self.ui.textEdit_transcription.insertPlainText(speaker)

    def insert_timestamp(self):
        """ Insert timestamp using current format.
        Format options:
        [mm.ss], [mm:ss], [hh.mm.ss], [hh:mm:ss],
        {hh.mm.ss}, #hh:mm:ss.sss#
        """

        fmt = self.app.settings['timestampformat']

        time_msecs = self.mediaplayer.get_time()
        mins_secs = msecs_to_mins_and_secs(time_msecs)  # String
        delimiter = ":"
        if "." in mins_secs:
            delimiter = "."
        mins = int(mins_secs.split(delimiter)[0])
        secs = mins_secs.split(delimiter)[1]
        hours = int(mins / 60)
        remainder_mins = str(mins - hours * 60)
        if len(remainder_mins) == 1:
            remainder_mins = "0" + remainder_mins
        hours = str(hours)
        if len(hours) == 1:
            hours = '0' + hours
        ts = "\n"
        if fmt == "[mm.ss]":
            ts += '[' + str(mins) + '.' + secs + ']'
        if fmt == "[mm:ss]":
            ts += '[' + str(mins) + ':' + secs + ']'
        if fmt == "[hh.mm.ss]":
            ts += '[' + str(hours) + '.' + remainder_mins + '.' + secs + ']'
        if fmt == "[hh:mm:ss]":
            ts += '[' + str(hours) + ':' + remainder_mins + ':' + secs + ']'
        if fmt == "{hh:mm:ss}":
            ts += '{' + str(hours) + ':' + remainder_mins + ':' + secs + '}'
        if fmt == "#hh:mm:ss.sss#":
            msecs = "000"
            tms_str = str(time_msecs)
            if len(tms_str) > 2:
                msecs = tms_str[-3:]
            ts += '#' + str(hours) + ':' + remainder_mins + ':' + secs + '.' + msecs + '#'
        self.ui.textEdit_transcription.insertPlainText("\n" + ts + " ")
        # Code here makes the current text location visible on the textEdit pane
        textCursor = self.ui.textEdit_transcription.textCursor()
        pos = textCursor.position()
        textCursor.setPosition(pos)
        self.ui.textEdit_transcription.setTextCursor(textCursor)

    def add_speaker_names_to_label(self):
        """ Add speaker names to label, four on each line. """

        text = ""
        for i, n in enumerate(self.speaker_list):
            if i == 4:
                text += "\n"
            text += str(i + 1) + ": " + n + "  "
        self.ui.label_speakers.setText(text)

    def get_speaker_names_from_bracketed_text(self):
        """ Parse text for format of [] or {} to find speaker names.
        If needed limit to 8 names. """

        if self.transcription is None:
            return
        text = self.transcription[1]
        start = False
        ts_and_names = ""
        sn_format = self.app.settings['speakernameformat']
        for c in text:
            if c == sn_format[0]:
                start = True
            if c == sn_format[1]:
                start = False
            if start:
                ts_and_names = ts_and_names + c
        ts_and_names = ts_and_names.split(sn_format[0])
        names = []
        for n in ts_and_names:
            if n.find('.') == -1 and n.find(':') == -1 and n != '':
                tidy_n = n.replace('\n', '')
                tidy_n = n.strip()
                names.append(tidy_n)
        names = list(set(names))
        if len(names) > 8:
            names = names[0:8]
        self.speaker_list = names

    def scroll_transcribed_checkbox_changed(self):
        """ If checked, then cannot edit the textEdit_transcribed. """

        if not self.can_transcribe:
            # occurs if there is coded or annotated text.
            return
        if self.ui.checkBox_scroll_transcript.isChecked():
            self.ui.textEdit_transcription.setReadOnly(True)
        else:
            # redo timestamps as text may have been changed by user
            self.get_timestamps_from_transcription()
            self.ui.textEdit_transcription.setReadOnly(False)

    def get_timestamps_from_transcription(self):
        """ Get a list of starting/ending characterpositions and time in milliseconds
        from transcribed text file.

        Example formats:  [00:34:12] [45:33] [01.23.45] [02.34] {00.34.20}
        #00:12:34.567#
        09:33:04,100 --> 09:33:09,600

        Converts hh mm ss to milliseconds with text positions stored in a list
        The list contains lists of [text_pos0, text_pos1, milliseconds] """

        mmss1 = "\[[0-9]?[0-9]:[0-9][0-9]\]"
        hhmmss1 = "\[[0-9][0-9]:[0-9][0-9]:[0-9][0-9]\]"
        mmss2 = "\[[0-9]?[0-9]\.[0-9][0-9]\]"
        hhmmss2 = "\[[0-9][0-9]\.[0-9][0-9]\.[0-9][0-9]\]"
        hhmmss3 = "\{[0-9][0-9]\:[0-9][0-9]\:[0-9][0-9]\}"
        hhmmss_sss = "#[0-9][0-9]:[0-9][0-9]:[0-9][0-9]\.[0-9][0-9][0-9]#"
        srt = "[0-9][0-9]:[0-9][0-9]:[0-9][0-9],[0-9][0-9][0-9]\s-->\s[0-9][0-9]:[0-9][0-9]:[0-9][0-9],[0-9][0-9][0-9]"

        transcription = self.ui.textEdit_transcription.toPlainText()
        self.time_positions = []
        for match in re.finditer(mmss1, transcription):
            stamp = match.group()[1:-1]
            s = stamp.split(':')
            try:
                msecs = (int(s[0]) * 60 + int(s[1])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except:
                pass
        for match in re.finditer(hhmmss1, transcription):
            stamp = match.group()[1:-1]
            s = stamp.split(':')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s[2])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except:
                pass
        for match in re.finditer(mmss2, transcription):
            stamp = match.group()[1:-1]
            s = stamp.split('.')
            try:
                msecs = (int(s[0]) * 60 + int(s[1])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except:
                pass
        for match in re.finditer(hhmmss2, transcription):
            stamp = match.group()[1:-1]
            s = stamp.split('.')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s[2])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except:
                pass
        for match in re.finditer(hhmmss3, transcription):
            stamp = match.group()[1:-1]
            s = stamp.split('.')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s[2])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except:
                pass
        for match in re.finditer(hhmmss_sss, transcription):
            # Format #00:12:34.567#
            stamp = match.group()[1:-1]
            s = stamp.split(':')
            s2 = s[2].split('.')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s2[0])) * 1000 + int(s2[1])
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except:
                pass
        for match in re.finditer(srt, transcription):
            # Format 09:33:04,100 --> 09:33:09,600  skip the arrow and second time position
            stamp = match.group()[0:12]
            s = stamp.split(':')
            s2 = s[2].split(',')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s2[0])) * 1000 + int(s2[1])
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except:
                pass
        # print(self.time_positions)

    def audio_track_changed(self):
        """ Audio track changed.
        The video needs to be playing/paused before the combobox is filled with track options.
        The combobox only has positive integers."""

        text = self.ui.comboBox_tracks.currentText()
        # print("text: ", text)
        if text == "":
            text = 1
        success = self.mediaplayer.audio_set_track(int(text))
        # print("changed audio ", success)

    def play_pause(self):
        """ Toggle play or pause status. """

        # check that QDialog containinv vlc is visible (i.e. has not been closed)

        if self.mediaplayer.is_playing():
            self.mediaplayer.pause()
            self.ui.pushButton_play.setText(_("Play"))
            self.is_paused = True
            self.timer.stop()
        else:
            if self.mediaplayer.play() == -1:
                return

            # On play rewind one second
            time_msecs = self.mediaplayer.get_time() - 2000
            if time_msecs < 0:
                time_msecs = 0
            pos = time_msecs / self.mediaplayer.get_media().get_duration()
            self.mediaplayer.set_position(pos)
            # Update timer display
            msecs = self.mediaplayer.get_time()
            self.ui.label_time.setText(_("Time: ") + msecs_to_mins_and_secs(msecs))

            self.mediaplayer.play()
            self.ui.pushButton_play.setText(_("Pause"))
            self.timer.start()
            self.is_paused = False

    def pause(self):
        """ Pause any playback. Called when entering a new speakers name
        during manual transcription. """

        if self.mediaplayer.is_playing():
            self.mediaplayer.pause()
            self.ui.pushButton_play.setText(_("Play"))
            self.is_paused = True
            self.timer.stop()

    def stop(self):
        """ Stop vlc player. Set position slider to the start.
         If multiple audio tracks are shown in the combobox, set the audio track to the first index.
         This is because when beginning play again, the audio track reverts to the first track.
         Programatically setting the audio track to other values does not work. """

        self.mediaplayer.stop()
        self.ui.pushButton_play.setText(_("Play"))
        self.ui.horizontalSlider.setProperty("value", 0)

        # set combobox display of audio track to the first one, or leave it blank if it contains no items
        if self.ui.comboBox_tracks.count() > 0:
            self.ui.comboBox_tracks.setCurrentIndex(0)

    def set_volume(self, volume):
        """ Set the volume. """

        self.mediaplayer.audio_set_volume(volume)

    def update_ui(self):
        """ Updates the user interface. Update the slider position to match media.
         Adds audio track options to combobox.
         Updates the current displayed media time. """

        self.ui.horizontalSlider.blockSignals(True)
        # update audio track list, only works if media is playing
        if self.mediaplayer.audio_get_track_count() > 0 and self.ui.comboBox_tracks.count() == 0:
            tracks = self.mediaplayer.audio_get_track_description()
            for t in tracks:
                if t[0] > 0:
                    # print(t[0], t[1])  # track number and track name
                    self.ui.comboBox_tracks.addItem(str(t[0]))

        # Set the slider's position to its corresponding media position
        # Note that the setValue function only takes values of type int,
        # so we must first convert the corresponding media position.
        media_pos = int(self.mediaplayer.get_position() * 1000)
        self.ui.horizontalSlider.setValue(media_pos)
        msecs = self.mediaplayer.get_time()
        self.ui.label_time.setText(_("Time: ") + msecs_to_mins_and_secs(msecs))

        """ For long transcripts, update the relevant text position in the textEdit to match the
        video's current position.
        time_postion list itme: [text_pos0, text_pos1, milliseconds]
        """
        if self.ui.checkBox_scroll_transcript.isChecked() and self.transcription is not None and self.ui.textEdit_transcription.toPlainText() != "":
            for i in range(1, len(self.time_positions)):
                if msecs > self.time_positions[i - 1][2] and msecs < self.time_positions[i][2]:
                    text_pos = self.time_positions[i][0]
                    textCursor = self.ui.textEdit_transcription.textCursor()
                    textCursor.setPosition(text_pos)
                    self.ui.textEdit_transcription.setTextCursor(textCursor)

        # No need to call this function if nothing is played
        if not self.mediaplayer.is_playing():
            self.timer.stop()
            # After the video finished, the play button stills shows "Pause",
            # which is not the desired behavior of a media player.
            # This fixes that "bug".
            if not self.is_paused:
                self.stop()
        self.ui.horizontalSlider.blockSignals(False)

    def closeEvent(self, event):
        """ Stop the vlc player on close.
        Record the dialog and video dialog0 size and positions.
        Update the memo. """

        self.app.settings['dialogviewav_w'] = self.size().width()
        self.app.settings['dialogviewav_h'] = self.size().height()
        if self.media_data['mediapath'][0:7] != "/audio/":
            size = self.ddialog.size()
            if size.width() > 100:
                self.app.settings['video_w'] = size.width()
            else:
                self.app.settings['video_w'] = 100
            if size.height() > 80:
                self.app.settings['video_h'] = size.height()
            else:
                self.app.settings['video_h'] = 80
        # Get absolute video dialog position
        self.app.settings['viewav_video_pos_x'] = self.ddialog.pos().x()
        self.app.settings['viewav_video_pos_y'] = self.ddialog.pos().y()
        self.ddialog.close()
        self.app.settings['viewav_abs_pos_x'] = self.pos().x()
        self.app.settings['viewav_abs_pos_y'] = self.pos().y()
        self.stop()
        memo = self.ui.textEdit.toPlainText()
        cur = self.app.conn.cursor()
        cur.execute('update source set memo=? where id=?', (memo, self.media_data['id']))
        self.app.conn.commit()
        if self.transcription is not None:
            text = self.ui.textEdit_transcription.toPlainText()
            cur.execute("update source set fulltext=? where id=?", [text, self.transcription[0]])
            self.app.conn.commit()
        # following will occur even if memo is not changed
        self.app.delete_backup = False
