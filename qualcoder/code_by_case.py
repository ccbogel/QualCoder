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
"""
import sqlite3
from copy import deepcopy
import datetime
import logging
from operator import itemgetter
import os
import platform
from random import randint
import re
import sys
import time
import traceback
import webbrowser

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtGui import QHelpEvent
from PyQt6.QtCore import Qt  # for context menu
from PyQt6.QtGui import QBrush, QColor

from .add_item_name import DialogAddItemName
from .color_selector import DialogColorSelect
from .color_selector import colors, TextColor
from .confirm_delete import DialogConfirmDelete
from .helpers import msecs_to_hours_mins_secs, file_typer, Message, DialogCodeInAllFiles
from .GUI.base64_helper import *
from .GUI.ui_dialog_code_by_case import Ui_Dialog_code_by_case
from .memo import DialogMemo
from .report_attributes import DialogSelectAttributeParameters
from .reports import DialogReportCoderComparisons, DialogReportCodeFrequencies  # for isinstance()
from .report_codes import DialogReportCodes
from .report_code_summary import DialogReportCodeSummary  # for isinstance()
from .select_items import DialogSelectItems  # for isinstance()

# https://stackoverflow.com/questions/59014318/filenotfounderror-could-not-find-module-libvlc-dll
vlc_msg = ""
imp = True
try:
    import qualcoder.vlc as vlc
except Exception as e:
    vlc_msg = str(e) + "\n"
    if sys.platform.startswith("win"):
        imp = False
    if not imp:
        msg = str(e) + "\n"
        msg += "view_av. Cannot import vlc\n"
        msg += "Ensure you have 64 bit python AND 64 bit VLC installed OR\n"
        msg += "32 bit python AND 32 bit VLC installed."
        print(msg)
        vlc_msg = msg
    QtWidgets.QMessageBox.critical(None, _('Cannot import vlc'), vlc_msg)

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text_ = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text_)
    logger.error(_("Uncaught exception:") + "\n" + text_)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 12pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(text_)
    mb.exec()


class DialogCodeByCase(QtWidgets.QWidget):
    """ Code management. Add, delete codes. Mark and unmark text.
    Add memos and colors to codes.
    Can load a Case and assigned segments of text (and later images) can be coded. """

    NAME_COLUMN = 0
    ID_COLUMN = 1
    MEMO_COLUMN = 2
    app = None
    parent_textEdit = None
    tab_reports = None  # Tab widget reports, used for updates to codes
    help_url = "https://github.com/ccbogel/QualCoder/wiki/07-Coding-Text"
    codes = []
    recent_codes = []  # list of recent codes (up to 5) for textedit context menu
    categories = []
    cases = []  # List of cases
    case_ = None  # Current selected case
    code_text = []  # List of coded texts
    annotations = []
    # Overlapping coded text details
    overlaps_at_pos = []
    overlaps_at_pos_idx = 0
    # Search text variables
    search_indices = []
    search_index = 0
    search_term = ""
    search_type = "3"  # 3 or 5 or 1 for Enter

    selected_code_index = 0
    eventFilter = None
    important = False  # Show/hide important codes
    attributes = []  # Show selected cases using these attributes in list widget

    # Image variables
    code_areas = []
    img_selection = None
    img_scale = 1.0
    scene = None
    pixmap = None
    selection = None  # mouse point 0
    scale = 1

    # A/V variables
    ddialog = None
    instance = None
    mediaplayer = None
    media = None
    metadata = None
    is_paused = False
    segment = {}
    segments = []
    timer = QtCore.QTimer()
    play_segment_end = None
    media_duration_text = ""
    av_scene = None
    av_scene_width = 600
    av_scene_height = 90

    # A list of dictionaries of autcode history {title, list of dictionary of sql commands}
    # Timers to reduce overly sensitive key events: overlap, re-size oversteps by multiple characters
    code_resize_timer = 0
    overlap_timer = 0

    def __init__(self, app, parent_textEdit, tab_reports):

        super(DialogCodeByCase, self).__init__()
        self.app = app
        self.tab_reports = tab_reports
        sys.excepthook = exception_handler
        self.parent_textEdit = parent_textEdit
        self.search_indices = []
        self.search_index = 0
        self.recent_codes = []
        self.important = False
        self.attributes = []
        self.scale = 1
        self.code_resize_timer = datetime.datetime.now()
        self.overlap_timer = datetime.datetime.now()
        self.ui = Ui_Dialog_code_by_case()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        tree_font = 'font: ' + str(self.app.settings['treefontsize']) + 'pt '
        tree_font += '"' + self.app.settings['font'] + '";'
        self.ui.treeWidget.setStyleSheet(tree_font)
        doc_font = 'font: ' + str(self.app.settings['docfontsize']) + 'pt '
        doc_font += '"' + self.app.settings['font'] + '";'
        self.ui.textEdit.setStyleSheet(doc_font)
        self.ui.label_coder.setText("Coder: " + self.app.settings['codername'])
        self.ui.textEdit.setPlainText("")
        self.ui.textEdit.setAutoFillBackground(True)
        self.ui.textEdit.setToolTip("")
        self.ui.textEdit.setMouseTracking(True)
        self.ui.textEdit.setReadOnly(True)
        self.ui.textEdit.installEventFilter(self)
        self.eventFilterTT = ToolTipEventFilter()
        self.ui.textEdit.installEventFilter(self.eventFilterTT)
        self.ui.textEdit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.textEdit.customContextMenuRequested.connect(self.textEdit_menu)
        self.ui.textEdit.cursorPositionChanged.connect(self.overlapping_codes_in_text)
        self.ui.listWidget.setStyleSheet(tree_font)
        self.ui.listWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.listWidget.customContextMenuRequested.connect(self.cases_menu)
        self.ui.listWidget.currentItemChanged.connect(self.listwidgetitem_view_case)
        self.ui.listWidget_vars.setStyleSheet(tree_font)
        self.ui.lineEdit_search.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.lineEdit_search.customContextMenuRequested.connect(self.lineedit_search_menu)
        # Default to showing text edit
        self.ui.scrollArea.hide()
        self.ui.horizontalSlider.hide()
        self.ui.horizontalSlider_av.hide()
        self.ui.graphicsView_av.hide()
        self.ui.groupBox_av.hide()

        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(tag_icon32), "png")
        self.ui.pushButton_attributes.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_attributes.pressed.connect(self.get_cases_from_attributes)
        self.ui.pushButton_latest.hide()  # too hard to implement
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(playback_play_icon_24), "png")
        self.ui.pushButton_next_case.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_next_case.pressed.connect(self.go_to_next_case)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_right_icon_24), "png")
        self.ui.pushButton_next_file_portion.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_next_file_portion.pressed.connect(self.next_file_portion)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_left_icon_24), "png")
        self.ui.pushButton_previous_file_portion.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_previous_file_portion.pressed.connect(self.previous_file_portion)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_right_icon_24), "png")
        self.ui.pushButton_show_codings_next.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_show_codings_next.pressed.connect(self.show_selected_code_in_text_next)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_left_icon_24), "png")
        self.ui.pushButton_show_codings_prev.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_show_codings_prev.pressed.connect(self.show_selected_code_in_text_previous)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(a2x2_grid_icon_24), "png")
        self.ui.pushButton_show_all_codings.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_show_all_codings.pressed.connect(self.show_all_codes_in_text)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(notepad_pencil_icon), "png")
        self.ui.pushButton_annotate.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_annotate.pressed.connect(self.annotate)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(notepad_pencil_red_icon), "png")
        self.ui.pushButton_coding_memo.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_coding_memo.pressed.connect(self.coded_text_memo)
        self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
        self.ui.lineEdit_search.setEnabled(False)
        self.ui.checkBox_search_case.stateChanged.connect(self.search_for_text)
        self.ui.checkBox_search_case.setEnabled(False)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(question_icon), "png")
        self.ui.label_search_regex.setPixmap(QtGui.QPixmap(pm).scaled(22, 22))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(text_letter_t_icon), "png")
        self.ui.label_search_case_sensitive.setPixmap(QtGui.QPixmap(pm).scaled(22, 22))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(playback_back_icon), "png")
        self.ui.pushButton_previous.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_previous.setEnabled(False)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(playback_play_icon), "png")
        self.ui.pushButton_next.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_next.setEnabled(False)
        self.ui.pushButton_next.pressed.connect(self.move_to_next_search_text)
        self.ui.pushButton_previous.pressed.connect(self.move_to_previous_search_text)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(question_icon), "png")
        self.ui.pushButton_help.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_help.pressed.connect(self.help)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(star_icon32), "png")
        self.ui.pushButton_important.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_important.pressed.connect(self.show_important_coded)
        # Tree widget and splitter
        self.ui.label_codes_count.setEnabled(False)
        self.ui.treeWidget.setDragEnabled(True)
        self.ui.treeWidget.setAcceptDrops(True)
        self.ui.treeWidget.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.ui.treeWidget.viewport().installEventFilter(self)
        self.ui.treeWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.treeWidget.customContextMenuRequested.connect(self.tree_menu)
        self.ui.treeWidget.itemClicked.connect(self.fill_code_label_undo_show_selected_code)
        self.ui.splitter.setSizes([150, 400])
        try:
            s0 = int(self.app.settings['dialogcodebycase_splitter0'])
            s1 = int(self.app.settings['dialogcodebycase_splitter1'])
            if s0 > 5 and s1 > 5:
                self.ui.splitter.setSizes([s0, s1])
            v0 = int(self.app.settings['dialogcodebycase_splitter_v0'])
            v1 = int(self.app.settings['dialogcodebycase_splitter_v1'])
            if v0 > 5 and v1 > 5:
                # 30s are for the groupboxes containing buttons
                # The last 30 is for the variables list widget
                self.ui.leftsplitter.setSizes([v1, 30, v0, 30, 30])
        except KeyError:
            pass
        self.ui.splitter.splitterMoved.connect(self.update_sizes)
        self.ui.leftsplitter.splitterMoved.connect(self.update_sizes)
        #self.setAttribute(Qt.WA_QuitOnClose, False)

        # Image related
        self.scene = QtWidgets.QGraphicsScene()
        self.ui.graphicsView.setScene(self.scene)
        self.ui.graphicsView.setDragMode(QtWidgets.QGraphicsView.DragMode.RubberBandDrag)
        # Need this otherwise small images are centred on screen, and affect context menu position points
        self.ui.graphicsView.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.scene.installEventFilter(self)
        self.ui.horizontalSlider.valueChanged[int].connect(self.redraw_scene)
        # AV buttons and labels
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(clock_icon), "png")
        self.ui.label_time_3.setPixmap(QtGui.QPixmap(pm).scaled(22, 22))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(sound_high_icon), "png")
        self.ui.label_volume.setPixmap(QtGui.QPixmap(pm).scaled(22, 22))
        # Buttons need to be 36x36 pixels for 32x32 icons
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(play_icon), "png")
        self.ui.pushButton_play.setIcon(QtGui.QIcon(pm))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(rewind_30_icon), "png")
        self.ui.pushButton_rewind_30.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_rewind_30.pressed.connect(self.rewind_30_seconds)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(rewind_5_icon), "png")
        self.ui.pushButton_rewind_5.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_rewind_5.pressed.connect(self.rewind_5_seconds)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(forward_30_icon), "png")
        self.ui.pushButton_forward_30.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_forward_30.pressed.connect(self.forward_30_seconds)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(rate_down_icon), "png")
        self.ui.pushButton_rate_down.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_rate_down.pressed.connect(self.decrease_play_rate)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(rate_up_icon), "png")
        # Mediaplayer setup
        self.ui.pushButton_rate_up.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_rate_up.pressed.connect(self.increase_play_rate)
        # AV variables
        self.segment['start'] = None
        self.segment['end'] = None
        self.segment['start_msecs'] = None
        self.segment['end_msecs'] = None
        self.play_segment_end = None
        self.segments = []
        # My solution to getting gui mouse events by putting vlc video in another dialog
        # A display-dialog named ddialog
        # Otherwise, the vlc player hogs all the mouse events
        self.ddialog = QtWidgets.QDialog()
        # Enable custom window hint
        self.ddialog.setWindowFlags(self.ddialog.windowFlags() | QtCore.Qt.WindowType.CustomizeWindowHint)
        # Disable close button, only close through closing the Ui_Dialog_code_av
        self.ddialog.setWindowFlags(self.ddialog.windowFlags() & ~QtCore.Qt.WindowType.WindowCloseButtonHint)
        self.ddialog.gridLayout = QtWidgets.QGridLayout(self.ddialog)
        self.ddialog.dframe = QtWidgets.QFrame(self.ddialog)
        self.ddialog.dframe.setObjectName("frame")
        if platform.system() == "Darwin":  # For MacOS
            self.ddialog.dframe = QtWidgets.QMacCocoaViewContainer(0)
        self.palette = self.ddialog.dframe.palette()
        self.palette.setColor(QtGui.QPalette.ColorRole.Window, QColor(30, 30, 30))
        self.ddialog.dframe.setPalette(self.palette)
        self.ddialog.dframe.setAutoFillBackground(True)
        self.ddialog.gridLayout.addWidget(self.ddialog.dframe, 0, 0, 0, 0)
        # enable custom window hint - must be set to enable customizing window controls
        self.ddialog.setWindowFlags(self.ddialog.windowFlags() | QtCore.Qt.WindowType.CustomizeWindowHint)
        # disable close button, only close through closing the Ui_Dialog_view_av
        self.ddialog.setWindowFlags(self.ddialog.windowFlags() & ~QtCore.Qt.WindowType.WindowCloseButtonHint)
        self.ddialog.setWindowFlags(self.ddialog.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        # Create a vlc instance with an empty vlc media player
        # https://stackoverflow.com/questions/55339786/how-to-turn-off-vlcpulse-audio-from-python-program
        self.instance = vlc.Instance()
        self.mediaplayer = self.instance.media_player_new()
        self.mediaplayer.video_set_mouse_input(False)
        self.mediaplayer.video_set_key_input(False)
        self.ui.horizontalSlider.setTickPosition(QtWidgets.QSlider.TickPosition.NoTicks)
        self.ui.horizontalSlider_av.setMouseTracking(True)
        self.ui.horizontalSlider_av.sliderMoved.connect(self.set_position)
        self.ui.pushButton_play.clicked.connect(self.play_pause)
        self.ui.horizontalSlider_vol.valueChanged.connect(self.set_volume)
        self.ui.pushButton_coding.pressed.connect(self.create_or_clear_segment)
        self.ui.comboBox_tracks.currentIndexChanged.connect(self.audio_track_changed)
        # Set the scene for coding stripes
        self.av_scene_width = self.ui.graphicsView_av.viewport().size().width()
        # Height matches the designer file graphics view size
        self.av_scene_height = 90
        self.av_scene = GraphicsScene(self.av_scene_width, self.av_scene_height)
        self.ui.graphicsView_av.setScene(self.av_scene)
        self.ui.graphicsView_av.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.DefaultContextMenu)

        # Data
        self.get_cases()
        self.codes, self.categories = self.app.get_codes_categories()
        self.get_coded_areas()
        self.annotations = self.app.get_annotations()
        self.fill_tree()

    def help(self):
        """ Open help for transcribe section in browser.
        Can be text, or image help. """

        webbrowser.open(self.help_url)

    def get_cases(self, ids=None):
        """ Get cases with additional details (file texts and case attributes) and fill list widget.
         Called by: init, get_cases_from_attributes
         param:
         ids: list Integers of case ids. To limit case selection.

         Example case data:
         {'caseid': 1, 'name': 'ID1', 'memo': '',
         'files': [{'fid': 25, 'pos0': 0, 'pos1': 629, 'text': "Some text.", 'filename': 'id1.docx', 'mediapath': None,
         'memo': '', 'filetype': 'text'},
         {'fid': 20, 'pos0': 0, 'pos1': 0, 'text': None, 'filename': 'DSC_0005.JPG',
         'mediapath': '/images/DSC_0005.JPG', 'memo': '', 'filetype': 'image'}],
         'vars': [{'varname': 'Age', 'value': '45', 'valuetype': 'numeric'}], 'file_index': 0}
         """

        if ids is None:
            ids = []
        self.ui.listWidget.clear()
        cur = self.app.conn.cursor()
        cur.execute("select caseid, name, memo from cases order by lower(name)")
        result = cur.fetchall()
        self.cases = []
        keys = 'caseid', 'name', 'memo'
        for row in result:
            self.cases.append(dict(zip(keys, row)))
        # Fill additional data
        for c in self.cases:
            sql_sources = "select fid, pos0, pos1, substr(source.fulltext, pos0 + 1, pos1-pos0), " \
                  "source.name, source.mediapath, source.memo " \
                  "from case_text join source on source.id=case_text.fid " \
                  "where caseid=?"
            cur.execute(sql_sources, [c['caseid']])
            result_sources = cur.fetchall()
            sources = []
            for s_res in result_sources:
                keys_ = "fid", "pos0", "pos1", "text", "filename", "mediapath", "memo"
                res = dict(zip(keys_, s_res))
                res['filetype'] = file_typer(res['mediapath'])
                sources.append(res)
            c['files'] = sources
            sql_vars = "select attribute.name, value, valuetype from attribute " \
                "join attribute_type on attribute_type.name=attribute.name " \
                "where attr_type='case' and id=? order by attribute.name"
            cur.execute(sql_vars, [c['caseid']])
            result_vars = cur.fetchall()
            case_vars = []
            keys = "varname", "value", "valuetype"
            for v in result_vars:
                case_vars.append(dict(zip(keys, v)))
            c['vars'] = case_vars
            c['file_index'] = 0  # Showing this file segment for this case

        # Limited selection of cases
        if ids:
            tmp_cases = []
            for c in self.cases:
                for i in ids:
                    if c['caseid'] == i:
                        tmp_cases.append(c)
            self.cases = tmp_cases

        # Fill cases listWidget
        for c in self.cases:
            item = QtWidgets.QListWidgetItem(c['name'])
            tt = _("Text segments for case: ") + str(len(c['files']))
            if c['memo'] is not None and c['memo'] != "":
                tt += "\nMemo: " + c['memo']
            item.setToolTip(tt)
            self.ui.listWidget.addItem(item)

    def cases_menu(self, position):
        """ Cases menu to show cases like ... """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_show_like = QtGui.QAction(_("show cases like"))
        action_show_all = QtGui.QAction(_("Show all cases"))
        menu.addAction(action_show_like)
        menu.addAction(action_show_all)
        action = menu.exec(self.ui.listWidget.mapToGlobal(position))
        if action is None:
            return
        if action == action_show_all:
            self.attributes = []
            pm = QtGui.QPixmap()
            pm.loadFromData(QtCore.QByteArray.fromBase64(tag_icon32), "png")
            self.ui.pushButton_attributes.setIcon(QtGui.QIcon(pm))
            self.ui.pushButton_attributes.setToolTip(_("Show cases with selected attributes"))
            self.get_cases()
        if action == action_show_like:
            self.attributes = []
            pm = QtGui.QPixmap()
            pm.loadFromData(QtCore.QByteArray.fromBase64(tag_icon32), "png")
            self.ui.pushButton_attributes.setIcon(QtGui.QIcon(pm))
            self.ui.pushButton_attributes.setToolTip(_("Show cases with selected attributes"))
            dialog = QtWidgets.QInputDialog(None)
            dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            dialog.setWindowTitle(_("Show cases like"))
            #dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
            dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
            dialog.setLabelText(_("Show cases containing the text. (Blank for all)"))
            dialog.resize(200, 20)
            ok = dialog.exec()
            if not ok:
                return
            text_ = str(dialog.textValue())
            if text_ == "":
                self.get_cases()
                return
            cur = self.app.conn.cursor()
            sql = "select caseid, name from cases where name like ? order by cases.name"
            cur.execute(sql, ["%" + text_ + "%"])
            res = cur.fetchall()
            ids = []
            for r in res:
                ids.append(r[0])
            if len(ids) == 0:
                self.get_cases()
                return
            self.get_cases(ids)

    def fill_file_tooltip(self):
        """ Create tooltip for file containing characters, codings.
        Called by fill_segment
        Requires self.case_ """

        if self.case_ is None:
            return
        fid = self.case_['files'][self.case_['file_index']]['fid']
        ftype = self.case_['files'][self.case_['file_index']]['filetype']
        fmemo = self.case_['files'][self.case_['file_index']]['memo']
        tt = ""
        cur = self.app.conn.cursor()
        if ftype == 'text':
            sql = "select length(fulltext), memo from source where id=?"
            cur.execute(sql, [fid])
            res = cur.fetchone()
            if res is not None and res[0] > 0:
                tt += _("Characters: ") + str(res[0])
            sql_tx_codings = "select count(cid) from code_text where fid=? and owner=?"
            cur.execute(sql_tx_codings, [fid, self.app.settings['codername']])
            res_txt = cur.fetchone()
            if res_txt is not None and res_txt[0] > 0:
                tt += "\n" + _("Text codings: ") + str(res_txt[0])
        if ftype == 'image':
            sql_img_codings = "select count(cid) from code_image where id=? and owner=?"
            cur.execute(sql_img_codings, [fid, self.app.settings['codername']])
            res = cur.fetchone()
            if res is not None and res[0] > 0:
                tt += "\n" + _("Image codings: ") + str(res[0])

        if fmemo is not None and fmemo != "":
            tt += "\nMemo: " + fmemo
        # Find item to update tooltip
        self.ui.label_segment.setToolTip(tt)

    def get_cases_from_attributes(self):
        """ Trim the files list to files identified by attributes.
        Attribute dialing results are a dictionary of:
        [0] attribute name
        [1] attribute type: character, numeric
        [2] modifier: > < == != like between
        [3] comparison value as list, one item or two items for between

        DialogSelectAttributeParameters returns lists for each parameter selected of:
        attribute name, file or case, character or numeric, operator, list of one or two comparator values
        two comparator values are used with the 'between' operator
        ['source', 'file', 'character', '==', ["'interview'"]]
        ['case name', 'case', 'character', '==', ["'ID1'"]]

        Note, sqls are NOT parameterised.
        results from multiple parameters are intersected, an AND boolean function.
        """

        pm = QtGui.QPixmap()
        if self.attributes:
            self.attributes = []
            pm.loadFromData(QtCore.QByteArray.fromBase64(tag_icon32), "png")
            self.ui.pushButton_attributes.setIcon(QtGui.QIcon(pm))
            self.ui.pushButton_attributes.setToolTip(_("Show cases with selected attributes"))
            self.get_cases()
            return
        ui = DialogSelectAttributeParameters(self.app, "case")
        ok = ui.exec()
        if not ok:
            self.attributes = []
            return
        self.attributes = ui.parameters
        if not self.attributes:
            pm.loadFromData(QtCore.QByteArray.fromBase64(tag_icon32), "png")
            self.ui.pushButton_attributes.setIcon(QtGui.QIcon(pm))
            self.ui.pushButton_attributes.setToolTip(_("Show cases with selected attributes"))
            self.get_cases()
            return
        case_ids = []
        cur = self.app.conn.cursor()
        # Run a series of sql based on each selected attribute
        # Apply a set to the resulting ids to determine the final list of ids
        for a in self.attributes:
            sql = "select id from attribute where "
            sql += "attribute.name = '" + a[0] + "' "
            sql += " and attribute.value " + a[3] + " "
            if a[3] == 'between':
                sql += a[4][0] + " and " + a[4][1] + " "
            if a[3] in ('in', 'not in'):
                sql += "(" + ','.join(a[4]) + ") "  # One item the comma is skipped
            if a[3] not in ('between', 'in', 'not in'):
                sql += a[4][0]
            if a[2] == 'numeric':
                sql = sql.replace(' attribute.value ', ' cast(attribute.value as real) ')
            sql += " and attribute.attr_type='case'"
            cur.execute(sql)
            result = cur.fetchall()
            for i in result:
                case_ids.append(i[0])
        if not case_ids:
            Message(self.app, "Nothing found", "Nothing found").exec()
            return
        set_case_ids = set(case_ids)
        self.get_cases(list(set_case_ids))
        # Set message for label tooltip
        msg_ = ""
        for a in self.attributes:
            if a[1] == 'file':
                msg_ += " or" + "\n" + a[0] + " " + a[3] + " " + ",".join(a[4])
        if len(msg_) > 3:
            msg_ = msg_[3:]
        for a in self.attributes:
            if a[1] == 'case':
                msg_ += " and" + "\n" + a[0] + " " + a[3] + " " + ",".join(a[4])
        self.ui.pushButton_attributes.setToolTip(_("Show cases:") + msg_)
        pm.loadFromData(QtCore.QByteArray.fromBase64(tag_iconyellow32), "png")
        self.ui.pushButton_attributes.setIcon(QtGui.QIcon(pm))

    def update_sizes(self):
        """ Called by changed splitter size """

        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogcodebycase_splitter0'] = sizes[0]
        self.app.settings['dialogcodebycase_splitter1'] = sizes[1]
        v_sizes = self.ui.leftsplitter.sizes()
        self.app.settings['dialogcodebycase_splitter_v0'] = v_sizes[0]
        self.app.settings['dialogcodebycase_splitter_v1'] = v_sizes[1]

    def show_important_coded(self):
        """ Show codes flagged as important. """

        self.important = not self.important
        pm = QtGui.QPixmap()
        if self.important:
            pm.loadFromData(QtCore.QByteArray.fromBase64(star_icon_yellow32), "png")
            self.ui.pushButton_important.setToolTip(_("Showing important codings"))
        else:
            pm.loadFromData(QtCore.QByteArray.fromBase64(star_icon32), "png")
            self.ui.pushButton_important.setToolTip(_("Show codings flagged important"))
        self.ui.pushButton_important.setIcon(QtGui.QIcon(pm))
        self.get_coded_text_update_eventfilter_tooltips()

    def fill_code_label_undo_show_selected_code(self):
        """ Fill code label with currently selected item's code name and colour.
         Also, if text is highlighted, assign the text to this code.

         Called by: treewidgetitem_clicked, select_tree_item_by_code_name """

        current = self.ui.treeWidget.currentItem()
        if current.text(1)[0:3] == 'cat':
            self.ui.label_code.hide()
            self.ui.label_code.setToolTip("")
            return
        self.ui.label_code.show()
        # Set background colour of label to code color, and store current code for underlining
        for c in self.codes:
            if current.text(0) == c['name']:
                fg_color = TextColor(c['color']).recommendation
                style = "QLabel {background-color :" + c['color'] + "; color : " + fg_color + ";}"
                self.ui.label_code.setStyleSheet(style)
                self.ui.label_code.setAutoFillBackground(True)
                tt = c['name'] + "\n"
                if c['memo'] is not None and c['memo'] != "":
                    tt += _("Memo: ") + c['memo']
                self.ui.label_code.setToolTip(tt)
                break
        selected_text = self.ui.textEdit.textCursor().selectedText()
        if len(selected_text) > 0:
            self.mark()
        # When a code is selected undo the show selected code features
        self.highlight()
        # Reload button icons as they disappear on Windows
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_left_icon_24), "png")
        self.ui.pushButton_show_codings_prev.setIcon(QtGui.QIcon(pm))
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_right_icon_24), "png")
        self.ui.pushButton_show_codings_next.setIcon(QtGui.QIcon(pm))

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes.
        The Count column counts the number of times that code has been used by selected coder in selected file. """

        cats = deepcopy(self.categories)
        codes = deepcopy(self.codes)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(4)
        self.ui.treeWidget.setHeaderLabels([_("Name"), _("Id"), _("Memo"), _("Count")])
        if self.app.settings['showids'] == 'False':
            self.ui.treeWidget.setColumnHidden(1, True)
        else:
            self.ui.treeWidget.setColumnHidden(1, False)
        self.ui.treeWidget.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.ui.treeWidget.header().setStretchLastSection(False)
        # Add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                memo = ""
                if c['memo'] != "" and c['memo'] is not None:
                    memo = _("Memo")
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                top_item.setToolTip(2, c['memo'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_list.append(c)
        for item in remove_list:
            cats.remove(item)

        ''' Add child categories. look at each unmatched category, iterate through tree
         to add as child, then remove matched categories from the list '''
        count = 0
        while len(cats) > 0 and count < 10000:
            remove_list = []
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
                item = it.value()
                count2 = 0
                while item and count2 < 10000:  # while there is an item in the list
                    if item.text(1) == 'catid:' + str(c['supercatid']):
                        memo = ""
                        if c['memo'] != "" and c['memo'] is not None:
                            memo = _("Memo")
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
        # Add unlinked codes as top level items
        remove_items = []
        for c in codes:
            if c['catid'] is None:
                memo = ""
                if c['memo'] != "" and c['memo'] is not None:
                    memo = _("Memo")
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                top_item.setToolTip(2, c['memo'])
                top_item.setBackground(0, QBrush(QColor(c['color']), Qt.BrushStyle.SolidPattern))
                color = TextColor(c['color']).recommendation
                top_item.setForeground(0, QBrush(QColor(color)))
                top_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable |
                                  Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled)
                self.ui.treeWidget.addTopLevelItem(top_item)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)
        # Add codes as children
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
                    child.setBackground(0, QBrush(QColor(c['color']), Qt.BrushStyle.SolidPattern))
                    color = TextColor(c['color']).recommendation
                    child.setForeground(0, QBrush(QColor(color)))
                    child.setToolTip(2, c['memo'])
                    child.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable |
                                   Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled)
                    item.addChild(child)
                    c['catid'] = -1  # Make unmatchable
                it += 1
                item = it.value()
                count += 1
        self.ui.treeWidget.expandAll()
        self.fill_code_counts_in_tree()

    def fill_code_counts_in_tree(self):
        """ Count instances of each code for current coder and in the selected file or file segment.
        Called by: fill_tree
        """

        if self.case_ is None:
            return
        cur = self.app.conn.cursor()
        fid = self.case_['files'][self.case_['file_index']]['fid']
        text_pos0 = self.case_['files'][self.case_['file_index']]['pos0']
        end_pos = len(self.ui.textEdit.toPlainText()) + text_pos0
        ftype = self.case_['files'][self.case_['file_index']]['filetype']
        sql_txt = "select count(cid) from code_text where cid=? and fid=? and owner=? and pos0>=? and pos1<=?"
        sql_img = "select count(cid) from code_image where cid=? and id=? and owner=?"
        sql_av = "select count(cid) from code_av where cid=? and id=? and owner=?"
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        count = 0
        while item and count < 10000:
            if item.text(1)[0:4] == "cid:":
                cid = str(item.text(1)[4:])
                try:
                    if ftype == 'text':
                        cur.execute(sql_txt, [cid, fid, self.app.settings['codername'], text_pos0, end_pos])
                    if ftype == 'image':
                        cur.execute(sql_img, [cid, fid, self.app.settings['codername']])
                    if ftype in ('audio', 'video'):
                        cur.execute(sql_av, [cid, fid, self.app.settings['codername']])
                    result = cur.fetchone()
                    if result[0] > 0:
                        item.setText(3, str(result[0]))
                        item.setToolTip(3, self.app.settings['codername'])
                    else:
                        item.setText(3, "")
                except Exception as e_:
                    msg_ = "Fill code counts error\n" + str(e_) + "\n"
                    msg_ += "cid " + str(cid) + "\n"
                    msg_ += "self.file_['id'] " + str(fid) + "\n"
                    logger.debug(msg_)
                    item.setText(3, "")
            it += 1
            item = it.value()
            count += 1

    def get_codes_and_categories(self):
        """ Called from init, delete category/code.
        Also called on other coding dialogs in the dialog_list. """

        self.codes, self.categories = self.app.get_codes_categories()

    def search_for_text(self):
        """ On text changed in lineEdit_search OR Enter pressed, find indices of matching text.
        Only where text is >=3 OR 5 characters long. Or Enter is pressed (search_type==1).
        Resets current search_index.
        If all files is checked then searches for all matching text across all text files
        and displays the file text and current position to user.
        If case sensitive is checked then text searched is matched for case sensitivity.
        """

        if self.case_ is None:
            return
        if not self.search_indices:
            self.ui.pushButton_next.setEnabled(False)
            self.ui.pushButton_previous.setEnabled(False)
        self.search_indices = []
        self.search_index = -1
        self.search_term = self.ui.lineEdit_search.text()
        self.ui.label_search_totals.setText("0 / 0")
        if len(self.search_term) < int(self.search_type):
            return
        pattern = None
        flags = 0
        if not self.ui.checkBox_search_case.isChecked():
            flags |= re.IGNORECASE
        try:
            pattern = re.compile(self.search_term, flags)
        except re.error:
            logger.warning('Bad escape')
        if pattern is None:
            return
        self.search_indices = []
        for match in pattern.finditer(self.ui.textEdit.toPlainText()):
            # Get result as first dictionary item
            self.search_indices.append({'match_start': match.start(), 'match_len': len(match.group(0))})
        if len(self.search_indices) > 0:
            self.ui.pushButton_next.setEnabled(True)
            self.ui.pushButton_previous.setEnabled(True)
        self.ui.label_search_totals.setText("0 / " + str(len(self.search_indices)))

    def move_to_previous_search_text(self):
        """ Push button pressed to move to previous search text position. """

        if self.case_ is None or self.search_indices == []:
            return
        self.search_index -= 1
        if self.search_index < 0:
            self.search_index = len(self.search_indices) - 1
        cursor = self.ui.textEdit.textCursor()
        prev_result = self.search_indices[self.search_index]
        cursor.setPosition(prev_result['match_start'])
        cursor.setPosition(cursor.position() + prev_result['match_len'], QtGui.QTextCursor.MoveMode.KeepAnchor)
        self.ui.textEdit.setTextCursor(cursor)
        self.ui.label_search_totals.setText(str(self.search_index + 1) + " / " + str(len(self.search_indices)))

    def move_to_next_search_text(self):
        """ Push button pressed to move to next search text position. """

        if self.case_ is None or self.search_indices == []:
            return
        self.search_index += 1
        if self.search_index == len(self.search_indices):
            self.search_index = 0
        cursor = self.ui.textEdit.textCursor()
        next_result = self.search_indices[self.search_index]
        cursor.setPosition(cursor.position() + next_result['match_len'])
        self.ui.textEdit.setTextCursor(cursor)
        # Highlight selected text
        cursor.setPosition(next_result['match_start'])
        cursor.setPosition(cursor.position() + next_result['match_len'], QtGui.QTextCursor.MoveMode.KeepAnchor)
        self.ui.textEdit.setTextCursor(cursor)
        self.ui.label_search_totals.setText(str(self.search_index + 1) + " / " + str(len(self.search_indices)))

    def lineedit_search_menu(self, position):
        """ Option to change from automatic search on 3 characters or more to press Enter to search """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_char3 = QtGui.QAction(_("Automatic search 3 or more characters"))
        action_char5 = QtGui.QAction(_("Automatic search 5 or more characters"))
        action_enter = QtGui.QAction(_("Press Enter to search"))
        if self.search_type != "3":
            menu.addAction(action_char3)
        if self.search_type != "5":
            menu.addAction(action_char5)
        if self.search_type != "Enter":
            menu.addAction(action_enter)
        action = menu.exec(self.ui.lineEdit_search.mapToGlobal(position))
        if action is None:
            return
        if action == action_char3:
            self.search_type = 3
            self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
            self.ui.lineEdit_search.returnPressed.disconnect(self.search_for_text)
            return
        if action == action_char5:
            self.search_type = 5
            self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
            self.ui.lineEdit_search.returnPressed.disconnect(self.search_for_text)
            return
        if action == action_enter:
            self.search_type = 1
            self.ui.lineEdit_search.textEdited.disconnect(self.search_for_text)
            self.ui.lineEdit_search.returnPressed.connect(self.search_for_text)
            return

    def textEdit_recent_codes_menu(self, position):
        """ Alternative context menu.
        Shows a list of recent codes to select from.
        Called by R key press in the text edit pane, only if there is some selected text. """

        if self.ui.textEdit.toPlainText() == "":
            return
        selected_text = self.ui.textEdit.textCursor().selectedText()
        if selected_text == "":
            return
        if len(self.recent_codes) == 0:
            return
        menu = QtWidgets.QMenu()
        for item in self.recent_codes:
            menu.addAction(item['name'])
        action = menu.exec(self.ui.textEdit.mapToGlobal(position))
        if action is None:
            return
        # Remaining actions will be the submenu codes
        self.recursive_set_current_item(self.ui.treeWidget.invisibleRootItem(), action.text())
        self.mark()

    def textEdit_menu(self, position):
        """ Context menu for textEdit.
        Mark, unmark, annotate, copy, memo coded, coded importance. """

        if self.case_ is None:
            return
        text_pos0 = self.case_['files'][self.case_['file_index']]['pos0']
        cursor = self.ui.textEdit.cursorForPosition(position)
        selected_text = self.ui.textEdit.textCursor().selectedText()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_mark = None
        action_unmark = None
        action_copy = None
        action_code_memo = None
        action_start_pos = None
        action_end_pos = None
        action_important = None
        action_not_important = None
        action_annotate = None
        action_edit_annotate = None

        # Can have multiple coded text at this position
        for item in self.code_text:
            if cursor.position() + text_pos0 >= item['pos0'] and cursor.position() <= item['pos1']:
                action_unmark = QtGui.QAction(_("Unmark"))
                action_code_memo = QtGui.QAction(_("Memo coded text (M)"))
                action_start_pos = QtGui.QAction(_("Change start position (SHIFT LEFT/ALT RIGHT)"))
                action_end_pos = QtGui.QAction(_("Change end position (SHIFT RIGHT/ALT LEFT)"))
                if item['important'] is None or item['important'] > 1:
                    action_important = QtGui.QAction(_("Add important mark (I)"))
                if item['important'] == 1:
                    action_not_important = QtGui.QAction(_("Remove important mark"))
        if action_unmark:
            menu.addAction(action_unmark)
        if action_code_memo:
            menu.addAction(action_code_memo)
        if action_start_pos:
            menu.addAction(action_start_pos)
        if action_end_pos:
            menu.addAction(action_end_pos)
        if action_important:
            menu.addAction(action_important)
        if action_not_important:
            menu.addAction(action_not_important)

        if selected_text != "":
            if self.ui.treeWidget.currentItem() is not None:
                action_mark = menu.addAction(_("Mark (Q)"))
            # Use up to 10 recent codes
            if len(self.recent_codes) > 0:
                submenu = menu.addMenu(_("Mark with recent code (R)"))
                for item in self.recent_codes:
                    submenu.addAction(item['name'])
            action_annotate = menu.addAction(_("Annotate (A)"))
            action_copy = menu.addAction(_("Copy to clipboard"))
        if selected_text == "" and self.is_annotated(cursor.position()):
            action_edit_annotate = menu.addAction(_("Edit annotation"))
        action = menu.exec(self.ui.textEdit.mapToGlobal(position))
        if action is None:
            return
        if action == action_important:
            self.set_important(cursor.position())
            return
        if action == action_not_important:
            self.set_important(cursor.position(), False)
            return
        if selected_text != "" and action == action_copy:
            self.copy_selected_text_to_clipboard()
            return
        if selected_text != "" and self.ui.treeWidget.currentItem() is not None and action == action_mark:
            self.mark()
            return
        if action == action_annotate:
            self.annotate()
            return
        if action == action_edit_annotate:
            # Used fora point text press rather than a selected text
            self.annotate(cursor.position())
            return
        if action == action_unmark:
            self.unmark(cursor.position())
            return
        if action == action_code_memo:
            self.coded_text_memo(cursor.position())
            return
        if action == action_start_pos:
            self.change_code_pos(cursor.position(), "start")
            return
        if action == action_end_pos:
            self.change_code_pos(cursor.position(), "end")
            return
        # Remaining actions will be the submenu codes
        self.recursive_set_current_item(self.ui.treeWidget.invisibleRootItem(), action.text())
        self.mark()

    def recursive_set_current_item(self, item, text_):
        """ Set matching item to be the current selected item.
        Recurse through any child categories.
        Tried to use QTreeWidget.finditems - but this did not find matching item text
        Called by: textEdit recent codes menu option
        Required for: mark()
        """

        child_count = item.childCount()
        for i in range(child_count):
            if item.child(i).text(0) == text and item.child(i).text(1)[0:3] == "cid":
                self.ui.treeWidget.setCurrentItem(item.child(i))
            self.recursive_set_current_item(item.child(i), text_)

    def is_annotated(self, position):
        """ Check if position is annotated to provide annotation menu option.
        Returns True or False """

        if self.case_ is None or not self.case_['files']:
            return
        text_pos0 = self.case_['files'][self.case_['file_index']]['pos0']
        fid = self.case_['files'][self.case_['file_index']]['fid']
        for note in self.annotations:
            if (position + text_pos0 >= note['pos0'] and position + text_pos0 <= note['pos1']) \
                    and note['fid'] == fid:
                return True
        return False

    def set_important(self, position, important=True):
        """ Set or unset importance to coded text.
        Importance is denoted using '1'
        params:
            position: textEdit character cursor position
            important: boolean, default True """

        # Need to get coded segments at this position
        if position is None:
            # Called via button
            position = self.ui.textEdit.textCursor().position()
        if self.case_ is None or not self.case_['files']:
            return
        text_pos0 = self.case_['files'][self.case_['file_index']]['pos0']
        coded_text_list = []
        for item in self.code_text:
            if position + text_pos0 >= item['pos0'] and position + text_pos0 <= item['pos1'] and \
                    item['owner'] == self.app.settings['codername'] and \
                    ((not important and item['important'] == 1) or (important and item['important'] != 1)):
                coded_text_list.append(item)
        if not coded_text_list:
            return
        text_items = []
        if len(coded_text_list) == 1:
            text_items = [coded_text_list[0]]
        # Multiple codes at this position to select from
        if len(coded_text_list) > 1:
            ui = DialogSelectItems(self.app, coded_text_list, _("Select codes"), "multi")
            ok = ui.exec()
            if not ok:
                return
            text_items = ui.get_selected()
        if not text_items:
            return
        importance = None
        if important:
            importance = 1
        cur = self.app.conn.cursor()
        sql = "update code_text set important=? where cid=? and fid=? and seltext=? and pos0=? and pos1=? and owner=?"
        for item in text_items:
            cur.execute(sql,
                (importance, item['cid'], item['fid'], item['seltext'], item['pos0'], item['pos1'], item['owner']))
            self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def coded_text_memo(self, position=None):
        """ Add or edit a memo for this coded text. """

        if position is None:
            # Called via button
            position = self.ui.textEdit.textCursor().position()
        if self.case_ is None or not self.case_['files']:
            return
        text_pos0 = self.case_['files'][self.case_['file_index']]['pos0']
        coded_text_list = []
        for item in self.code_text:
            if position + text_pos0 >= item['pos0'] and position + text_pos0 <= item['pos1'] and \
                    item['owner'] == self.app.settings['codername']:
                coded_text_list.append(item)
        if not coded_text_list:
            return
        text_item = None
        if len(coded_text_list) == 1:
            text_item = coded_text_list[0]
        # Multiple codes at this position to select from
        if len(coded_text_list) > 1:
            ui = DialogSelectItems(self.app, coded_text_list, _("Select code to memo"), "single")
            ok = ui.exec()
            if not ok:
                return
            text_item = ui.get_selected()
        if text_item is None:
            return
        # Dictionary with cid fid seltext owner date name color memo
        msg_ = text_item['name'] + " [" + str(text_item['pos0']) + "-" + str(text_item['pos1']) + "]"
        ui = DialogMemo(self.app, _("Memo for Coded text: ") + msg_, text_item['memo'], "show", text_item['seltext'])
        ui.exec()
        memo = ui.memo
        if memo == text_item['memo']:
            return
        cur = self.app.conn.cursor()
        cur.execute("update code_text set memo=? where cid=? and fid=? and seltext=? and pos0=? and pos1=? and owner=?",
            (memo, text_item['cid'], text_item['fid'], text_item['seltext'], text_item['pos0'], text_item['pos1'], text_item['owner']))
        self.app.conn.commit()
        for i in self.code_text:
            if text_item['cid'] == i['cid'] and text_item['seltext'] == i['seltext'] and text_item['pos0'] == i['pos0'] \
                and text_item['pos1'] == i['pos1'] and text_item['owner'] == self.app.settings['codername']:
                i['memo'] = memo
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def change_code_pos(self, location, start_or_end):
        """  Called via textedit_menu. """

        if self.case_ is None:
            return
        text_pos0 = self.case_['files'][self.case_['file_index']]['pos0']
        code_list = []
        for item in self.code_text:
            if location + text_pos0 >= item['pos0'] and location + text_pos0 <= item['pos1'] and \
                    item['owner'] == self.app.settings['codername']:
                code_list.append(item)
        if not code_list:
            return
        code_to_edit = None
        if len(code_list) == 1:
            code_to_edit = code_list[0]
        # Multiple codes to select from
        if len(code_list) > 1:
            ui = DialogSelectItems(self.app, code_list, _("Select code for change"), "single")
            ok = ui.exec()
            if not ok:
                return
            code_to_edit = ui.get_selected()
        if code_to_edit is None:
            return
        txt_len = len(self.ui.textEdit.toPlainText())
        changed_start = 0
        changed_end = 0
        int_dialog = QtWidgets.QInputDialog()
        int_dialog.setMinimumSize(60, 150)
        # Remove context flag does not work here
        int_dialog.setWindowFlags(int_dialog.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        msg_ = _("Key shortcuts\nShift left Arrow\nShift Right Arrow\nAlt Left Arrow\nAlt Right Arrow")
        int_dialog.setToolTip(msg_)
        if start_or_end == "start":
            max_ = code_to_edit['pos1'] - code_to_edit['pos0'] - 1
            min_ = -1 * code_to_edit['pos0']
            changed_start, ok = int_dialog.getInt(self, _("Change start position"),
                _("Change start character position. Positive or negative number:"), 0, min_, max_, 1)
            if not ok:
                return
        if start_or_end == "end":
            max_ = txt_len - code_to_edit['pos1']
            min_ = code_to_edit['pos0'] - code_to_edit['pos1'] + 1
            changed_end, ok = int_dialog.getInt(self, _("Change end position"),
                _("Change end character position. Positive or negative number:"), 0, min_, max_, 1)
            if not ok:
                return
        if changed_start == 0 and changed_end == 0:
            return
        int_dialog.done(1)  # Need this, as reactiveated when called again with same int value.

        # Update database, reload code_text and highlights
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

    def copy_selected_text_to_clipboard(self):
        """ Copy text to clipboard for external use.
        For example adding text to another document. """

        selected_text = self.ui.textEdit.textCursor().selectedText()
        cb = QtWidgets.QApplication.clipboard()
        cb.setText(selected_text)

    def tree_menu(self, position):
        """ Context menu for treewidget code/category items.
        Add, rename, memo, move or delete code or category. Change code color.
        Assign selected text to current hovered code. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        selected = self.ui.treeWidget.currentItem()
        action_add_code_to_category = None
        action_add_category_to_category = None
        action_merge_category = None
        action_assign_segment = None
        if self.segment['end_msecs'] is not None and self.segment['start_msecs'] is not None:
            action_assign_segment = menu.addAction("Assign segment to code")
        if selected is not None and selected.text(1)[0:3] == 'cat':
            action_add_code_to_category = menu.addAction(_("Add new code to category"))
            action_add_category_to_category = menu.addAction(_("Add a new category to category"))
            action_merge_category = menu.addAction(_("Merge category into category"))
        action_add_code = menu.addAction(_("Add a new code"))
        action_add_category = menu.addAction(_("Add a new category"))
        action_rename = menu.addAction(_("Rename"))
        action_edit_memo = menu.addAction(_("View or edit memo"))
        action_delete = menu.addAction(_("Delete"))
        action_color = None
        action_show_coded_media = None
        action_move_code = None
        if selected is not None and selected.text(1)[0:3] == 'cid':
            action_color = menu.addAction(_("Change code color"))
            action_show_coded_media = menu.addAction(_("Show coded files"))
            action_move_code = menu.addAction(_("Move code to"))
        action_show_codes_like = menu.addAction(_("Show codes like"))
        action = menu.exec(self.ui.treeWidget.mapToGlobal(position))
        if action is not None:
            if action == action_show_codes_like:
                self.show_codes_like()
            if selected is not None and action == action_color:
                self.change_code_color(selected)
            if action == action_add_category:
                self.add_category()
            if action == action_add_code:
                self.add_code()
            if action == action_merge_category:
                catid = int(selected.text(1).split(":")[1])
                self.merge_category(catid)
            if action == action_add_code_to_category:
                catid = int(selected.text(1).split(":")[1])
                self.add_code(catid)
            if action == action_add_category_to_category:
                catid = int(selected.text(1).split(":")[1])
                self.add_category(catid)
            if action == action_assign_segment:
                self.assign_segment_to_code(selected)
            if selected is not None and action == action_move_code:
                self.move_code(selected)
            if selected is not None and action == action_rename:
                self.rename_category_or_code(selected)
            if selected is not None and action == action_edit_memo:
                self.add_edit_cat_or_code_memo(selected)
            if selected is not None and action == action_delete:
                self.delete_category_or_code(selected)
            if selected is not None and action == action_show_coded_media:
                found_code = None
                tofind = int(selected.text(1)[4:])
                for code in self.codes:
                    if code['cid'] == tofind:
                        found_code = code
                        break
                if found_code:
                    self.coded_media_dialog(found_code)

    def recursive_non_merge_item(self, item, no_merge_list):
        """ Find matching item to be the current selected item.
        Recurse through any child categories.
        Tried to use QTreeWidget.finditems - but this did not find matching item text
        Called by: textEdit recent codes menu option
        Required for: merge_category()
        """

        child_count = item.childCount()
        for i in range(child_count):
            if item.child(i).text(1)[0:3] == "cat":
                no_merge_list.append(item.child(i).text(1)[6:])
            self.recursive_non_merge_item(item.child(i), no_merge_list)
        return no_merge_list

    def assign_segment_to_code(self, selected):
        """ Assign time segment to selected code. Insert an entry into the database.
        Then clear the segment for re-use."""

        if self.case_ is None or self.segment['start_msecs'] is None or self.segment['end_msecs'] is None:
            self.clear_segment()
            return
        fid = self.case_['files'][self.case_['file_index']]['fid']
        sql = "insert into code_av (id, pos0, pos1, cid, memo, date, owner, important) values(?,?,?,?,?,?,?, null)"
        cid = int(selected.text(1).split(':')[1])
        values = [fid, self.segment['start_msecs'],
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

    def merge_category(self, catid):
        """ Select another category to merge this category into. """

        nons = []
        nons = self.recursive_non_merge_item(self.ui.treeWidget.currentItem(), nons)
        nons.append(str(catid))
        non_str = "(" + ",".join(nons) + ")"
        sql = "select name, catid, supercatid from code_cat where catid not in "
        sql += non_str + " order by name"
        cur = self.app.conn.cursor()
        cur.execute(sql)
        res = cur.fetchall()
        category_list = [{'name': "", 'catid': None, 'supercatid': None}]
        for r in res:
            category_list.append({'name': r[0], 'catid': r[1], "supercatid": r[2]})
        ui = DialogSelectItems(self.app, category_list, _("Select blank or category"), "single")
        ok = ui.exec()
        if not ok:
            return
        category = ui.get_selected()
        for c in self.codes:
            if c['catid'] == catid:
                cur.execute("update code_name set catid=? where catid=?", [category['catid'], catid])
        cur.execute("delete from code_cat where catid=?", [catid])
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        for cat in self.categories:
            if cat['supercatid'] == catid:
                cur.execute("update code_cat set supercatid=? where supercatid=?", [category['catid'], catid])
        self.app.conn.commit()
        # Clear any orphan supercatids
        sql = "select supercatid from code_cat where supercatid not in (select catid from code_cat)"
        cur.execute(sql)
        orphans = cur.fetchall()
        sql = "update code_cat set supercatid=Null where supercatid=?"
        for i in orphans:
            cur.execute(sql, [i[0]])
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()

    def move_code(self, selected):
        """ Move code to another category or to no category.
        Uses a list selection.
        param:
            selected : QTreeWidgetItem
         """

        cid = int(selected.text(1)[4:])
        cur = self.app.conn.cursor()
        cur.execute("select name, catid from code_cat order by name")
        res = cur.fetchall()
        category_list = [{'name': "", 'catid': None}]
        for r in res:
            category_list.append({'name': r[0], 'catid': r[1]})
        ui = DialogSelectItems(self.app, category_list, _("Select blank or category"), "single")
        ok = ui.exec()
        if not ok:
            return
        category = ui.get_selected()
        cur.execute("update code_name set catid=? where cid=?", [category['catid'], cid])
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()

    def show_codes_like(self):
        """ Show all codes if text is empty.
         Show selected codes that contain entered text.
         The input dialog is too narrow, so it is re-created. """

        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        dialog.setWindowTitle(_("Show some codes"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog.setLabelText(_("Show codes containing the text. (Blank for all)"))
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        text_ = str(dialog.textValue())
        root = self.ui.treeWidget.invisibleRootItem()
        self.recursive_traverse(root, text_)

    def recursive_traverse(self, item, text_):
        """ Find all children codes of this item that match or not and hide or unhide based on 'text'.
        Recurse through all child categories.
        Called by: show_codes_like
        param:
            item: a QTreeWidgetItem
            text:  Text string for matching with code names
        """

        child_count = item.childCount()
        for i in range(child_count):
            if "cid:" in item.child(i).text(1) and len(text_) > 0 and text_ not in item.child(i).text(0):
                item.child(i).setHidden(True)
            if "cid:" in item.child(i).text(1) and text_ == "":
                item.child(i).setHidden(False)
            self.recursive_traverse(item.child(i), text_)

    def keyPressEvent(self, event):
        """ This works best without the modifiers.
         As pressing Ctrl + E give the Ctrl but not the E.
         These key presses are not used in edi mode.

        A annotate - for current selection
        Q Quick Mark with code - for current selection
        H Hide / Unhide top groupbox
        I Tag important
        M memo code - at clicked position
        O Shortcut to cycle through overlapping codes - at clicked position
        S search text - may include current selection
        R opens a context menu for recently used codes for marking text
        """

        if not self.ui.textEdit.hasFocus():
            return
        if self.case_ is None:
            return
        text_pos0 = self.case_['files'][self.case_['file_index']]['pos0']
        key = event.key()
        # mod = QtGui.QGuiApplication.keyboardModifiers()
        cursor_pos = self.ui.textEdit.textCursor().position()
        selected_text = self.ui.textEdit.textCursor().selectedText()
        codes_here = []
        for item in self.code_text:
            if cursor_pos + text_pos0 >= item['pos0'] and \
                    cursor_pos + text_pos0 <= item['pos1'] and \
                    item['owner'] == self.app.settings['codername']:
                codes_here.append(item)
        # Annotate selected
        if key == QtCore.Qt.Key.Key_A and selected_text != "":
            self.annotate()
            return
        # Hide unHide top groupbox
        if key == QtCore.Qt.Key.Key_H:
            self.ui.groupBox.setHidden(not (self.ui.groupBox.isHidden()))
            return
        # Important  for coded text
        if key == QtCore.Qt.Key.Key_I:
            self.set_important(cursor_pos)
            return
        # Memo for current code
        if key == QtCore.Qt.Key.Key_M:
            self.coded_text_memo(cursor_pos)
            return
        # Overlapping codes cycle
        now = datetime.datetime.now()
        overlap_diff = now - self.overlap_timer
        if key == QtCore.Qt.Key.Key_O and len(self.overlaps_at_pos) > 0 and overlap_diff.microseconds > 150000:
            self.overlap_timer = datetime.datetime.now()
            self.highlight_selected_overlap()
            return
        # Quick mark selected
        if key == QtCore.Qt.Key.Key_Q and selected_text != "":
            self.mark()
            return
        # Recent codes context menu
        if key == QtCore.Qt.Key.Key_R and self.ui.textEdit.textCursor().selectedText() != "":
            self.textEdit_recent_codes_menu(self.ui.textEdit.cursorRect().topLeft())
            return
        # Search, with or without selected
        if key == QtCore.Qt.Key.Key_S and len(self.ui.textEdit.toPlainText()) > 0:
            if selected_text == "":
                self.ui.lineEdit_search.setFocus()
            else:
                self.ui.lineEdit_search.setText(selected_text)
                self.search_for_text()
                self.ui.pushButton_next.setFocus()

    def highlight_selected_overlap(self):
        """ Highlight the current overlapping text code, by placing formatting on top. """

        self.overlaps_at_pos_idx += 1
        if self.overlaps_at_pos_idx >= len(self.overlaps_at_pos):
            self.overlaps_at_pos_idx = 0
        item = self.overlaps_at_pos[self.overlaps_at_pos_idx]
        # Remove formatting
        text_pos0 = self.case_['files'][self.case_['file_index']]['pos0']
        cursor = self.ui.textEdit.textCursor()
        cursor.setPosition(int(item['pos0']) - text_pos0, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(int(item['pos1']) - text_pos0, QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(QtGui.QTextCharFormat())
        # Reapply formatting
        color = ""
        for code in self.codes:
            if code['cid'] == item['cid']:
                color = code['color']
        fmt = QtGui.QTextCharFormat()
        brush = QBrush(QColor(color))
        fmt.setBackground(brush)
        if item['important']:
            fmt.setFontWeight(QtGui.QFont.Weight.Bold)
        fmt.setForeground(QBrush(QColor(TextColor(color).recommendation)))
        cursor.setCharFormat(fmt)
        self.apply_italic_to_overlaps()

    def overlapping_codes_in_text(self):
        """ When coded text is clicked on find overlapping codes at this character position.
        Only enabled if two or more codes are here.
        Adjust for when portion of full text file loaded.
        Called by: textEdit cursor position changed. """

        self.overlaps_at_pos = []
        self.overlaps_at_pos_idx = 0
        pos = self.ui.textEdit.textCursor().position()
        text_pos0 = self.case_['files'][self.case_['file_index']]['pos0']
        for item in self.code_text:
            if item['pos0'] <= pos + text_pos0 and item['pos1'] >= pos + text_pos0:
                # logger.debug("Code name for selected pos0:" + str(item['pos0'])+" pos1:"+str(item['pos1'])
                self.overlaps_at_pos.append(item)
        if len(self.overlaps_at_pos) < 2:
            self.overlaps_at_pos = []
            self.overlaps_at_pos_idx = 0

    #TODO redeclared event filter
    def eventFilter(self, object, event):
        """ Using this event filter to identify treeWidgetItem drop events.
        http://doc.qt.io/qt-5/qevent.html#Type-enum
        QEvent::Drop 63 A drag and drop operation is completed (QDropEvent).
        https://stackoverflow.com/questions/28994494/why-does-qtreeview-not-fire-a-drop-or-move-event-during-drag-and-drop

        Also use it to detect key events in the textedit.
        These are used to extend or shrink a text coding.
        Only works if clicked on a code (text cursor is in the coded text).
        Shrink start and end code positions using alt arrow left and alt arrow right
        Extend start and end code positions using shift arrow left, shift arrow right
        """

        if object is self.ui.treeWidget.viewport():
            if event.type() == QtCore.QEvent.Type.Drop:
                item = self.ui.treeWidget.currentItem()
                # event position is QPointF, itemAt requires toPoint
                parent = self.ui.treeWidget.itemAt(event.position().toPoint())
                self.item_moved_update_data(item, parent)
                return True
        # Change start and end code positions using alt arrow left and alt arrow right
        # and shift arrow left, shift arrow right
        # QtGui.QKeyEvent = 7
        if type(event) == QtGui.QKeyEvent and self.ui.textEdit.hasFocus():
            key = event.key()
            mod = event.modifiers()
            # Using timer for a lot of things
            now = datetime.datetime.now()
            diff = now - self.code_resize_timer
            if diff.microseconds < 180000:
                return False
            cursor_pos = self.ui.textEdit.textCursor().position()
            codes_here = []
            if self.case_ is not None:
                text_pos0 = self.case_['files'][self.case_['file_index']]['pos0']
                for item in self.code_text:
                    if cursor_pos + text_pos0 >= item['pos0'] and \
                            cursor_pos + text_pos0 <= item['pos1'] and \
                            item['owner'] == self.app.settings['codername']:
                        codes_here.append(item)
            if len(codes_here) == 1:
                # Key event can be too sensitive, adjusted  for 150 millisecond gap
                self.code_resize_timer = datetime.datetime.now()
                if key == QtCore.Qt.Key.Key_Left and mod == QtCore.Qt.KeyboardModifier.AltModifier:
                    self.shrink_to_left(codes_here[0])
                    return True
                if key == QtCore.Qt.Key.Key_Right and mod == QtCore.Qt.KeyboardModifier.AltModifier:
                    self.shrink_to_right(codes_here[0])
                    return True
                if key == QtCore.Qt.Key.Key_Left and mod == QtCore.Qt.KeyboardModifier.ShiftModifier:
                    self.extend_left(codes_here[0])
                    return True
                if key == QtCore.Qt.Key.Key_Right and mod == QtCore.Qt.KeyboardModifier.ShiftModifier:
                    self.extend_right(codes_here[0])
                    return True
        if object is self.scene:
            if type(event) == QtWidgets.QGraphicsSceneMouseEvent and event.button() == Qt.MouseButton.LeftButton:
                if event.type() == QtCore.QEvent.Type.GraphicsSceneMousePress:
                    p0 = event.buttonDownScenePos(Qt.MouseButton.LeftButton)
                    # logger.debug("rectangle press:" + str(p0.x()) + ", " + str(p0.y()))
                    self.selection = p0
                    return True
                if event.type() == QtCore.QEvent.Type.GraphicsSceneMouseRelease:
                    p1 = event.lastScenePos()
                    # logger.debug("rectangle release: " + str(p1.x()) +", " + str(p1.y()))
                    self.img_create_coded_area(p1)
                    return True
            if type(event) == QtWidgets.QGraphicsSceneMouseEvent and event.button() == Qt.MouseButton.RightButton:
                if event.type() == QtCore.QEvent.Type.GraphicsSceneMousePress:
                    p = event.buttonDownScenePos(Qt.MouseButton.RightButton)
                    self.scene_context_menu(p)
                    return True
        return False

    def extend_left(self, code_):
        """ Shift left arrow. """

        if code_['pos0'] < 1:
            return
        code_['pos0'] -= 1
        cur = self.app.conn.cursor()
        text_sql = "select substr(fulltext,?,?) from source where id=?"
        cur.execute(text_sql, [code_['pos0'] + 1, code_['pos1'] - code_['pos0'], code_['fid']])
        seltext = cur.fetchone()[0]
        sql = "update code_text set pos0=?, seltext=? where cid=? and fid=? and pos0=? and pos1=? and owner=?"
        cur.execute(sql,
            (code_['pos0'], seltext, code_['cid'], code_['fid'], code_['pos0'] + 1, code_['pos1'], self.app.settings['codername']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def extend_right(self, code_):
        """ Shift right arrow. """

        if code_['pos1'] + 1 >= len(self.ui.textEdit.toPlainText()):
            return
        code_['pos1'] += 1
        cur = self.app.conn.cursor()
        text_sql = "select substr(fulltext,?,?) from source where id=?"
        cur.execute(text_sql, [code_['pos0'] + 1, code_['pos1'] - code_['pos0'], code_['fid']])
        seltext = cur.fetchone()[0]
        sql = "update code_text set pos1=?, seltext=? where cid=? and fid=? and pos0=? and pos1=? and owner=?"
        cur.execute(sql,
            (code_['pos1'], seltext, code_['cid'], code_['fid'], code_['pos0'], code_['pos1'] - 1, self.app.settings['codername']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def shrink_to_left(self, code_):
        """ Alt left arrow, shrinks code from the right end of the code. """

        if code_['pos1'] <= code_['pos0'] + 1:
            return
        code_['pos1'] -= 1
        cur = self.app.conn.cursor()
        text_sql = "select substr(fulltext,?,?) from source where id=?"
        cur.execute(text_sql, [code_['pos0'] + 1, code_['pos1'] - code_['pos0'], code_['fid']])
        seltext = cur.fetchone()[0]
        sql = "update code_text set pos1=?, seltext=? where cid=? and fid=? and pos0=? and pos1=? and owner=?"
        cur.execute(sql,
            (code_['pos1'], seltext, code_['cid'], code_['fid'], code_['pos0'], code_['pos1'] + 1, self.app.settings['codername']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def shrink_to_right(self, code_):
        """ Alt right arrow shrinks code from the left end of the code. """

        if code_['pos0'] >= code_['pos1'] - 1:
            return
        code_['pos0'] += 1
        cur = self.app.conn.cursor()
        text_sql = "select substr(fulltext,?,?) from source where id=?"
        cur.execute(text_sql, [code_['pos0'] + 1, code_['pos1'] - code_['pos0'], code_['fid']])
        seltext = cur.fetchone()[0]
        sql = "update code_text set pos0=?, seltext=? where cid=? and fid=? and pos0=? and pos1=? and owner=?"
        cur.execute(sql,
            (code_['pos0'], seltext, code_['cid'], code_['fid'], code_['pos0'] - 1, code_['pos1'], self.app.settings['codername']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def show_selected_code_in_text_next(self):
        """ Highlight only the selected code in the text. Move to next instance in text
        from the current textEdit cursor position.
        Adjust for a portion of text loaded.
        Called by: pushButton_show_codings_next
        """

        if self.case_ is None:
            return
        item = self.ui.treeWidget.currentItem()
        if item is None or item.text(1)[0:3] == 'cat':
            return
        cid = int(item.text(1)[4:])
        # Index list has to be dynamic, as a new code_text item could be created before this method is called again
        # Develop indexes and tooltip coded text list
        indexes = []
        tt_code_text = []
        for ct in self.code_text:
            if ct['cid'] == cid:
                indexes.append(ct)
                tt_code_text.append(ct)
        text_pos0 = self.case_['files'][self.case_['file_index']]['pos0']
        indexes = sorted(indexes, key=itemgetter('pos0'))
        cursor = self.ui.textEdit.textCursor()
        cur_pos = cursor.position()
        end_pos = 0
        found_larger = False
        msg_ = "/" + str(len(indexes))
        for i, index in enumerate(indexes):
            if index['pos0'] - text_pos0 > cur_pos:
                cur_pos = index['pos0'] - text_pos0
                end_pos = index['pos1'] - text_pos0
                found_larger = True
                msg_ = str(i + 1) + msg_
                break
        if not found_larger and indexes == []:
            return
        # Loop around to highest index
        if not found_larger and indexes != []:
            cur_pos = indexes[0]['pos0'] - text_pos0
            end_pos = indexes[0]['pos1'] - text_pos0
            msg_ = "1" + msg_
        if not found_larger:
            cursor = self.ui.textEdit.textCursor()
            cursor.setPosition(0)
            self.ui.textEdit.setTextCursor(cursor)
        self.unlight()
        msg_ = " " + _("Code:") + " " + msg_
        # Highlight the code in the text
        color = ""
        for c in self.codes:
            if c['cid'] == cid:
                color = c['color']
        cursor.setPosition(cur_pos)
        self.ui.textEdit.setTextCursor(cursor)
        cursor.setPosition(cur_pos, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(end_pos, QtGui.QTextCursor.MoveMode.KeepAnchor)
        brush = QBrush(QColor(color))
        fmt = QtGui.QTextCharFormat()
        fmt.setBackground(brush)
        foregroundcol = TextColor(color).recommendation
        fmt.setForeground(QBrush(QColor(foregroundcol)))
        cursor.mergeCharFormat(fmt)
        # Update tooltips to show only this code
        self.eventFilterTT.set_codes_and_annotations(tt_code_text, self.codes, self.annotations, text_pos0)
        # Need to reload arrow iconsas they dissapear on Windows
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(a2x2_color_grid_icon_24), "png")
        self.ui.pushButton_show_all_codings.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_show_codings_prev.setStyleSheet("background-color : " + color + ";color:" + foregroundcol)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_left_icon_24), "png")
        self.ui.pushButton_show_codings_prev.setIcon(QtGui.QIcon(pm))
        tt = _("Show previous coding of selected code") + msg_
        self.ui.pushButton_show_codings_prev.setToolTip(tt)
        self.ui.pushButton_show_codings_next.setStyleSheet("background-color : " + color + ";color:" + foregroundcol)
        tt = _("Show next coding of selected code") + msg_
        self.ui.pushButton_show_codings_next.setToolTip(tt)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_right_icon_24), "png")
        self.ui.pushButton_show_codings_next.setIcon(QtGui.QIcon(pm))

    def show_selected_code_in_text_previous(self):
        """ Highlight only the selected code in the text. Move to previous instance in text from
        the current textEdit cursor position.
        Called by: pushButton_show_codings_previous
        """

        if self.case_ is None:
            return
        item = self.ui.treeWidget.currentItem()
        if item is None or item.text(1)[0:3] == 'cat':
            return
        cid = int(item.text(1)[4:])
        # Index list has to be dynamic, as a new code_text item could be created before this method is called again
        # Develop indexs and tooltip coded text list
        text_pos0 = self.case_['files'][self.case_['file_index']]['pos0']
        indexes = []
        tt_code_text = []
        for ct in self.code_text:
            if ct['cid'] == cid:
                indexes.append(ct)
                tt_code_text.append(ct)
        indexes = sorted(indexes, key=itemgetter('pos0'), reverse=True)
        cursor = self.ui.textEdit.textCursor()
        cur_pos = cursor.position()
        end_pos = 0
        found_smaller = False
        msg_ = "/" + str(len(indexes))
        for i, index in enumerate(indexes):
            if index['pos0'] - text_pos0 < cur_pos - 1:
                cur_pos = index['pos0'] - text_pos0
                end_pos = index['pos1'] - text_pos0
                found_smaller = True
                msg_ = str(len(indexes) - i) + msg_
                break
        if not found_smaller and indexes == []:
            return
        # Loop around to highest index
        if not found_smaller and indexes != []:
            cur_pos = indexes[0]['pos0'] - text_pos0
            end_pos = indexes[0]['pos1'] - text_pos0
            msg_ = str(len(indexes)) + msg_
        msg_ += " " + _("Code:") + " " + msg_
        self.unlight()
        # Highlight the code in the text
        color = ""
        for c in self.codes:
            if c['cid'] == cid:
                color = c['color']
        cursor.setPosition(cur_pos)
        self.ui.textEdit.setTextCursor(cursor)
        cursor.setPosition(cur_pos, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(end_pos, QtGui.QTextCursor.MoveMode.KeepAnchor)
        brush = QBrush(QColor(color))
        fmt = QtGui.QTextCharFormat()
        fmt.setBackground(brush)
        foregroundcol = TextColor(color).recommendation
        fmt.setForeground(QBrush(QColor(foregroundcol)))
        cursor.mergeCharFormat(fmt)
        # Update tooltips to show only this code
        self.eventFilterTT.set_codes_and_annotations(tt_code_text, self.codes, self.annotations, text_pos0)
        # Need to reload arrow icons as they disappear on Windows
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(a2x2_color_grid_icon_24), "png")
        self.ui.pushButton_show_all_codings.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_show_codings_prev.setStyleSheet("background-color : " + color + ";color:" + foregroundcol)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_left_icon_24), "png")
        self.ui.pushButton_show_codings_prev.setIcon(QtGui.QIcon(pm))
        tt = _("Show previous coding of selected code") + msg_
        self.ui.pushButton_show_codings_prev.setToolTip(tt)
        self.ui.pushButton_show_codings_next.setStyleSheet("background-color : " + color + ";color:" + foregroundcol)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_right_icon_24), "png")
        self.ui.pushButton_show_codings_next.setIcon(QtGui.QIcon(pm))
        tt = _("Show next coding of selected code") + msg_
        self.ui.pushButton_show_codings_next.setToolTip(tt)

    def show_all_codes_in_text(self):
        """ Opposes show selected code methods.
        Highlights all the codes in the text. """

        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(a2x2_grid_icon_24), "png")
        self.ui.pushButton_show_all_codings.setIcon(QtGui.QIcon(pm))
        self.ui.pushButton_show_codings_prev.setStyleSheet("")
        self.ui.pushButton_show_codings_next.setStyleSheet("")
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_left_icon_24), "png")
        self.ui.pushButton_show_codings_prev.setIcon(QtGui.QIcon(pm))
        tt = _("Show previous coding of selected code")
        self.ui.pushButton_show_codings_prev.setToolTip(tt)
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(round_arrow_right_icon_24), "png")
        self.ui.pushButton_show_codings_next.setIcon(QtGui.QIcon(pm))
        tt = _("Show next coding of selected code")
        self.ui.pushButton_show_codings_next.setToolTip(tt)
        self.unlight()
        self.highlight()
        self.get_coded_text_update_eventfilter_tooltips()

    def coded_media_dialog(self, code_dict):
        """ Display all coded media for this code, in a separate modal dialog.
        Coded media comes from ALL files for this coder.
        Need to store textedit start and end positions so that code in context can be used.
        Called from tree_menu.
        param:
            code_dict : code dictionary
        """

        DialogCodeInAllFiles(self.app, code_dict)

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
                    return
                self.categories[found]['supercatid'] = supercatid
            cur = self.app.conn.cursor()
            cur.execute("update code_cat set supercatid=? where catid=?",
            [self.categories[found]['supercatid'], self.categories[found]['catid']])
            self.app.conn.commit()
            self.update_dialog_codes_and_categories()
            self.app.delete_backup = False
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
            self.app.delete_backup = False
            self.update_dialog_codes_and_categories()

    def merge_codes(self, item, parent):
        """ Merge code or category with another code or category.
        Called by item_moved_update_data when a code is moved onto another code. """

        msg_ = '<p style="font-size:' + str(self.app.settings['fontsize']) + 'px">'
        msg_ += _("Merge code: ") + item['name'] + _(" into code: ") + parent.text(0) + '</p>'
        reply = QtWidgets.QMessageBox.question(None, _('Merge codes'),
        msg_, QtWidgets.QMessageBox.StandardButton.Yes, QtWidgets.QMessageBox.StandardButton.No)
        if reply == QtWidgets.QMessageBox.StandardButton.No:
            return
        cur = self.app.conn.cursor()
        old_cid = item['cid']
        new_cid = int(parent.text(1).split(':')[1])
        try:
            cur.execute("update code_text set cid=? where cid=?", [new_cid, old_cid])
            cur.execute("update code_av set cid=? where cid=?", [new_cid, old_cid])
            cur.execute("update code_image set cid=? where cid=?", [new_cid, old_cid])
            self.app.conn.commit()
        except sqlite3.Error:
            '''e = str(e)
            msg = _("Cannot merge codes, unmark overlapping text first. ") + "\n" + str(e)
            Message(self.app, _("Cannot merge"), msg, "warning").exec_()
            return'''
            ''' Instead of a confusing warning, delete the duplicate coded text. '''
            pass
        cur.execute("delete from code_name where cid=?", [old_cid, ])
        self.app.conn.commit()
        self.app.delete_backup = False
        msg_ = msg_.replace("\n", " ")
        self.parent_textEdit.append(msg_)
        self.update_dialog_codes_and_categories()

    def add_code(self, catid=None):
        """ Use add_item dialog to get new code text. Add_code_name dialog checks for
        duplicate code name. A random color is selected for the code.
        New code is added to data and database.
        param:
            catid : None to add to without category, catid to add to to category. """

        ui = DialogAddItemName(self.app, self.codes, _("Add new code"), _("Code name"))
        ui.exec()
        code_name = ui.get_new_name()
        if code_name is None:
            return
        code_color = colors[randint(0, len(colors) - 1)]
        item = {'name': code_name, 'memo': "", 'owner': self.app.settings['codername'],
        'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'catid': catid,
        'color': code_color}
        cur = self.app.conn.cursor()
        cur.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,?,?,?,?)"
            , (item['name'], item['memo'], item['owner'], item['date'], item['catid'], item['color']))
        self.app.conn.commit()
        self.app.delete_backup = False
        cur.execute("select last_insert_rowid()")
        cid = cur.fetchone()[0]
        item['cid'] = cid
        self.parent_textEdit.append(_("New code: ") + item['name'])
        self.update_dialog_codes_and_categories()
        self.get_coded_text_update_eventfilter_tooltips()

    def update_dialog_codes_and_categories(self):
        """ Update code and category tree here and in DialogReportCodes, ReportCoderComparisons, ReportCodeFrequencies
        Using try except blocks for each instance, as instance may have been deleted. """

        self.get_codes_and_categories()
        self.fill_tree()
        self.unlight()
        self.highlight()
        self.get_coded_text_update_eventfilter_tooltips()

        contents = self.tab_reports.layout()
        if contents:
            for i in reversed(range(contents.count())):
                c = contents.itemAt(i).widget()
                if isinstance(c, DialogReportCodes):
                    c.get_codes_categories_coders()
                    c.fill_tree()
                if isinstance(c, DialogReportCoderComparisons):
                    c.get_data()
                    c.fill_tree()
                if isinstance(c, DialogReportCodeFrequencies):
                    c.get_data()
                    c.fill_tree()
                if isinstance(c, DialogReportCodeSummary):
                    c.get_codes_and_categories()
                    c.fill_tree()

    def add_category(self, supercatid=None):
        """ When button pressed, add a new category.
        Note: the addItem dialog does the checking for duplicate category names
        param:
            suoercatid : None to add without category, supercatid to add to category. """

        ui = DialogAddItemName(self.app, self.categories, _("Category"), _("Category name"))
        ui.exec()
        new_cat_text = ui.get_new_name()
        if new_cat_text is None:
            return
        item = {'name': new_cat_text, 'cid': None, 'memo': "",
        'owner': self.app.settings['codername'],
        'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
        cur = self.app.conn.cursor()
        cur.execute("insert into code_cat (name, memo, owner, date, supercatid) values(?,?,?,?,?)"
            , (item['name'], item['memo'], item['owner'], item['date'], supercatid))
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False
        self.parent_textEdit.append(_("New category: ") + item['name'])

    def delete_category_or_code(self, selected):
        """ Determine if selected item is a code or category before deletion. """

        if selected.text(1)[0:3] == 'cat':
            self.delete_category(selected)
            return  # Avoid error as selected is now None
        if selected.text(1)[0:3] == 'cid':
            self.delete_code(selected)

    def delete_code(self, selected):
        """ Find code, remove from database, refresh and code data and fill treeWidget.
        """

        # Find the code in the list, check to delete
        found = -1
        for i in range(0, len(self.codes)):
            if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                found = i
        if found == -1:
            return
        code_ = self.codes[found]
        ui = DialogConfirmDelete(self.app, _("Code: ") + selected.text(0))
        ok = ui.exec()
        if not ok:
            return
        cur = self.app.conn.cursor()
        cur.execute("delete from code_name where cid=?", [code_['cid'], ])
        cur.execute("delete from code_text where cid=?", [code_['cid'], ])
        cur.execute("delete from code_av where cid=?", [code_['cid'], ])
        cur.execute("delete from code_image where cid=?", [code_['cid'], ])
        self.app.conn.commit()
        self.app.delete_backup = False
        self.update_dialog_codes_and_categories()
        self.parent_textEdit.append(_("Code deleted: ") + code_['name'] + "\n")
        # Remove from recent codes
        for item in self.recent_codes:
            if item['name'] == code_['name']:
                self.recent_codes.remove(item)
                break

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
        ok = ui.exec()
        if not ok:
            return
        cur = self.app.conn.cursor()
        cur.execute("update code_name set catid=null where catid=?", [category['catid'], ])
        cur.execute("update code_cat set supercatid=null where catid = ?", [category['catid'], ])
        cur.execute("delete from code_cat where catid = ?", [category['catid'], ])
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False
        self.parent_textEdit.append(_("Category deleted: ") + category['name'])

    def add_edit_cat_or_code_memo(self, selected):
        """ View and edit a memo for a category or code. """

        if selected.text(1)[0:3] == 'cid':
            # Find the code in the list
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                    found = i
            if found == -1:
                return
            ui = DialogMemo(self.app, _("Memo for Code: ") + self.codes[found]['name'], self.codes[found]['memo'])
            ui.exec()
            memo = ui.memo
            if memo != self.codes[found]['memo']:
                self.codes[found]['memo'] = memo
                cur = self.app.conn.cursor()
                cur.execute("update code_name set memo=? where cid=?", (memo, self.codes[found]['cid']))
                self.app.conn.commit()
                self.app.delete_backup = False
            if memo == "":
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, "")
            else:
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, _("Memo"))
                self.parent_textEdit.append(_("Memo for code: ") + self.codes[found]['name'])

        if selected.text(1)[0:3] == 'cat':
            # Find the category in the list
            found = -1
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                    found = i
            if found == -1:
                return
            ui = DialogMemo(self.app, _("Memo for Category: ") + self.categories[found]['name'], self.categories[found]['memo'])
            ui.exec()
            memo = ui.memo
            if memo != self.categories[found]['memo']:
                self.categories[found]['memo'] = memo
                cur = self.app.conn.cursor()
                cur.execute("update code_cat set memo=? where catid=?", (memo, self.categories[found]['catid']))
                self.app.conn.commit()
                self.app.delete_backup = False
            if memo == "":
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, "")
            else:
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, _("Memo"))
                self.parent_textEdit.append(_("Memo for category: ") + self.categories[found]['name'])
        self.update_dialog_codes_and_categories()

    def rename_category_or_code(self, selected):
        """ Rename a code or category.
        Check that the code or category name is not currently in use.
        param:
            selected : QTreeWidgetItem """

        if selected.text(1)[0:3] == 'cid':
            new_name, ok = QtWidgets.QInputDialog.getText(self, _("Rename code"),
                _("New code name:"), QtWidgets.QLineEdit.EchoMode.Normal, selected.text(0))
            if not ok or new_name == '':
                return
            # Check that no other code has this name
            for c in self.codes:
                if c['name'] == new_name:
                    Message(self.app, _("Name in use"),
                    new_name + _(" is already in use, choose another name."), "warning").exec()
                    return
            # Find the code in the list
            found = -1
            for i in range(0, len(self.codes)):
                if self.codes[i]['cid'] == int(selected.text(1)[4:]):
                    found = i
            if found == -1:
                return
            # Rename in recent codes
            for item in self.recent_codes:
                if item['name'] == self.codes[found]['name']:
                    item['name'] = new_name
                    break
            # Update codes list and database
            cur = self.app.conn.cursor()
            cur.execute("update code_name set name=? where cid=?", (new_name, self.codes[found]['cid']))
            self.app.conn.commit()
            self.app.delete_backup = False
            old_name = self.codes[found]['name']
            self.parent_textEdit.append(_("Code renamed from: ") + old_name + _(" to: ") + new_name)
            self.update_dialog_codes_and_categories()
            return

        if selected.text(1)[0:3] == 'cat':
            new_name, ok = QtWidgets.QInputDialog.getText(self, _("Rename category"), _("New category name:"),
            QtWidgets.QLineEdit.EchoMode.Normal, selected.text(0))
            if not ok or new_name == '':
                return
            # Check that no other category has this name
            for c in self.categories:
                if c['name'] == new_name:
                    msg_ = _("This code name is already in use.")
                    Message(self.app, _("Duplicate code name"), msg_, "warning").exec()
                    return
            # Find the category in the list
            found = -1
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                    found = i
            if found == -1:
                return
            # Update category list and database
            cur = self.app.conn.cursor()
            cur.execute("update code_cat set name=? where catid=?",
            (new_name, self.categories[found]['catid']))
            self.app.conn.commit()
            self.app.delete_backup = False
            old_name = self.categories[found]['name']
            self.update_dialog_codes_and_categories()
            self.parent_textEdit.append(_("Category renamed from: ") + old_name + _(" to: ") + new_name)

    def change_code_color(self, selected):
        """ Change the colour of the currently selected code.
        param:
            selected : QTreeWidgetItem """

        cid = int(selected.text(1)[4:])
        found = -1
        for i in range(0, len(self.codes)):
            if self.codes[i]['cid'] == cid:
                found = i
        if found == -1:
            return
        ui = DialogColorSelect(self.app, self.codes[found])
        ok = ui.exec()
        if not ok:
            return
        new_color = ui.get_color()
        if new_color is None:
            return
        selected.setBackground(0, QBrush(QColor(new_color), Qt.BrushStyle.SolidPattern))
        # Update codes list, database and color markings
        self.codes[found]['color'] = new_color
        cur = self.app.conn.cursor()
        cur.execute("update code_name set color=? where cid=?",
        (self.codes[found]['color'], self.codes[found]['cid']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.update_dialog_codes_and_categories()

    def go_to_next_case(self):
        """ Go to next case in list. Button: pushButton_next_file. """

        if self.case_ is None:
            self.case_ = self.cases[0]
            self.load_case()
            self.ui.listWidget.setCurrentRow(0)
            return
        for i in range(0, len(self.cases) - 1):
            if self.case_ == self.cases[i]:
                self.case_ = self.cases[i + 1]
                self.ui.listWidget.setCurrentRow(i + 1)
                self.load_case()
                self.search_term = ""
                return

    def load_case(self):
        """ Load the first file segment.
        The first file segment is then displayed for coding.
        Get and display coding highlights.
        Fill variables list from: vars': [{'varname': 'Age', 'value': '45', 'valuetype': 'numeric'}, ...]
        Called from: listwidgetitem_view_case
        param: self.case_
        """

        self.ui.listWidget_vars.clear()
        for v in self.case_['vars']:
            var_text = v['varname'] + ": " + v['value']
            item = QtWidgets.QListWidgetItem(var_text)
            self.ui.listWidget_vars.addItem(item)
        # Fill text edit with initial (or current indexed file-segment)
        self.fill_file_details()

    def fill_file_details(self):
        """ Fill widgets (text_edit / graphics/ av) with current file_index file portion.
        Fill label_file_totals.
        Get and display coding highlights.
        Called from: listwidgetitem_view_case
        """

        self.ui.lineEdit_search.setText("")
        self.search_indices = []
        self.search_index = 0
        if not self.case_['files']:
            return
        ftype = self.case_['files'][self.case_['file_index']]['filetype']
        files_msg = str(self.case_['file_index'] + 1) + " / " + str(len(self.case_['files'])) + " "
        files_msg += self.case_['files'][self.case_['file_index']]['filename']
        if ftype == 'text':
            files_msg += " [" + str(self.case_['files'][self.case_['file_index']]['pos0']) + " - "
            files_msg += str(self.case_['files'][self.case_['file_index']]['pos1']) + "]"
        self.ui.label_segment.setText(files_msg)
        if ftype == 'text':
            self.ui.textEdit.show()
            self.stop()
            self.media = None
            self.ddialog.hide()
            self.ui.scrollArea.hide()
            self.ui.horizontalSlider.hide()
            self.ui.groupBox_av.hide()
            self.ui.horizontalSlider_av.hide()
            self.ui.graphicsView_av.hide()
            self.ui.textEdit.setPlainText(self.case_['files'][self.case_['file_index']]['text'])
            self.ui.lineEdit_search.show()
            self.ui.checkBox_search_case.show()
            self.ui.pushButton_annotate.show()
            self.ui.pushButton_coding_memo.show()
            self.ui.label_search_regex.show()
            self.ui.label_search_totals.show()
            self.ui.label_search_case_sensitive.show()
            self.ui.pushButton_next.show()
            self.ui.pushButton_previous.show()
            self.img_selection = None
            self.img_scale = 1.0
            self.pixmap = None
            self.help_url = "https://github.com/ccbogel/QualCoder/wiki/07-Coding-Text"
        if ftype == 'image':
            self.ui.textEdit.hide()
            self.stop()
            self.media = None
            self.ddialog.hide()
            self.ui.groupBox_av.hide()
            self.ui.horizontalSlider_av.hide()
            self.ui.graphicsView_av.hide()
            self.ui.scrollArea.show()
            self.ui.horizontalSlider.show()
            self.ui.lineEdit_search.hide()
            self.ui.checkBox_search_case.hide()
            self.ui.pushButton_annotate.hide()
            self.ui.pushButton_coding_memo.hide()
            self.ui.label_search_regex.hide()
            self.ui.label_search_totals.hide()
            self.ui.label_search_case_sensitive.hide()
            self.ui.pushButton_next.hide()
            self.ui.pushButton_previous.hide()
            self.help_url = "https://github.com/ccbogel/QualCoder/wiki/08-Coding-Images"
            self.load_image()
        if ftype in ('audio', 'video'):
            self.ui.scrollArea.hide()
            self.ui.horizontalSlider.hide()
            self.ui.textEdit.hide()
            self.ui.lineEdit_search.hide()
            self.ui.checkBox_search_case.hide()
            self.ui.pushButton_annotate.hide()
            self.ui.pushButton_coding_memo.hide()
            self.ui.label_search_regex.hide()
            self.ui.label_search_totals.hide()
            self.ui.label_search_case_sensitive.hide()
            self.ui.pushButton_next.hide()
            self.ui.pushButton_previous.hide()
            self.help_url = "https://github.com/ccbogel/QualCoder/wiki/09-Coding-audio-and-video"
            self.ui.horizontalSlider_av.show()
            self.ui.groupBox_av.show()
            self.ui.graphicsView_av.show()
            print(self.case_['files'][self.case_['file_index']])
            self.load_av_media()
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_file_tooltip()
        self.fill_code_counts_in_tree()

    def next_file_portion(self):
        """ Move to next file portion for this case. """

        if self.case_ is None:
            return
        self.case_['file_index'] += 1
        if self.case_['file_index'] >= len(self.case_['files']):
            self.case_['file_index'] = len(self.case_['files']) - 1
        self.fill_file_details()

    def previous_file_portion(self):
        """ Move to previous file portion for this case. """

        if self.case_ is None:
            return
        self.case_['file_index'] -= 1
        if self.case_['file_index'] < 0:
            self.case_['file_index'] = 0
        self.fill_file_details()

    def listwidgetitem_view_case(self):
        """ When listwidget item is pressed, find and load the case.
        """

        if self.ui.listWidget.currentItem() is None:
            return
        itemname = self.ui.listWidget.currentItem().text()
        for c in self.cases:
            if c['name'] == itemname:
                self.case_ = c
                self.load_case()
                self.search_term = ""
                break

    # Text edit methods
    def get_coded_text_update_eventfilter_tooltips(self):
        """ Called by load_file, and from other dialogs on update.
        Tooltips are for all coded_text or only for important if important is flagged.
        """

        if self.case_ is None:
            return
        fid = self.case_['files'][self.case_['file_index']]['fid']
        text_pos0 = self.case_['files'][self.case_['file_index']]['pos0']
        text_pos1 = self.case_['files'][self.case_['file_index']]['pos1']
        sql_values = [fid, self.app.settings['codername'], text_pos0, text_pos1]
        # Get code text for this file and for this coder
        self.code_text = []
        # seltext length, longest first, so overlapping shorter text is superimposed.
        sql = "select code_text.ctid, code_text.cid, fid, seltext, pos0, pos1, code_text.owner, code_text.date, "
        sql += "code_text.memo, important, name"
        sql += " from code_text join code_name on code_text.cid = code_name.cid"
        sql += " where fid=? and code_text.owner=? "
        # For file text which is currently loaded
        sql += " and pos0 >=? and pos1 <=? "
        sql += "order by length(seltext) desc, important asc"
        cur = self.app.conn.cursor()
        cur.execute(sql, sql_values)
        code_results = cur.fetchall()
        keys = 'ctid', 'cid', 'fid', 'seltext', 'pos0', 'pos1', 'owner', 'date', 'memo', 'important', 'name'
        for row in code_results:
            self.code_text.append(dict(zip(keys, row)))
        # Update filter for tooltip and redo formatting
        if self.important:
            imp_coded = []
            for c in self.code_text:
                if c['important'] == 1:
                    imp_coded.append(c)
            self.eventFilterTT.set_codes_and_annotations(imp_coded, self.codes, self.annotations, text_pos0)
        else:
            self.eventFilterTT.set_codes_and_annotations(self.code_text, self.codes, self.annotations, text_pos0)
        self.unlight()
        self.highlight()

    def unlight(self):
        """ Remove all text highlighting from current file. """

        text_len = len(self.ui.textEdit.toPlainText())
        if text_len == 0:
            return
        cursor = self.ui.textEdit.textCursor()
        cursor.setPosition(0, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(text_len - 1, QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(QtGui.QTextCharFormat())

    def highlight(self):
        """ Apply text highlighting to current file.
        If no colour has been assigned to a code, those coded text fragments are coloured gray.
        Each code text item contains: fid, date, pos0, pos1, seltext, cid, status, memo,
        name, owner.
        For defined colours in color_selector, make text light on dark, and conversely dark on light
        """

        if self.case_ is None:
            return
        fid = self.case_['files'][self.case_['file_index']]['fid']
        text_pos0 = self.case_['files'][self.case_['file_index']]['pos0']
        if len(self.ui.textEdit.toPlainText()) > 0:
            # Add coding highlights
            codes = {x['cid']: x for x in self.codes}
            for item in self.code_text:
                fmt = QtGui.QTextCharFormat()
                cursor = self.ui.textEdit.textCursor()
                cursor.setPosition(int(item['pos0'] - text_pos0), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(int(item['pos1'] - text_pos0), QtGui.QTextCursor.MoveMode.KeepAnchor)
                color = codes.get(item['cid'], {}).get('color', "#777777")  # default gray
                brush = QBrush(QColor(color))
                fmt.setBackground(brush)
                # Foreground depends on the defined need_white_text color in color_selector
                text_brush = QBrush(QColor(TextColor(color).recommendation))
                fmt.setForeground(text_brush)
                # Highlight codes with memos - these are italicised
                # Italics also used for overlapping codes
                if item['memo'] is not None and item['memo'] != "":
                    fmt.setFontItalic(True)
                else:
                    fmt.setFontItalic(False)
                # Bold important codes
                if item['important']:
                    fmt.setFontWeight(QtGui.QFont.Weight.Bold)
                # Use important flag for ONLY showing important codes (button selected)
                if self.important and item['important'] == 1:
                    cursor.setCharFormat(fmt)
                # Show all codes, as important button not selected
                if not self.important:
                    cursor.setCharFormat(fmt)

            # Add annotation marks - these are in bold, important codings are also bold
            for note in self.annotations:
                # Cursor pos could be negative if annotation was for an earlier text portion
                cursor = self.ui.textEdit.textCursor()
                if note['fid'] == fid and \
                        int(note['pos0']) - text_pos0 >= 0 and \
                        int(note['pos1']) - text_pos0 > 0 and \
                        int(note['pos1']) - text_pos0 <= len(self.ui.textEdit.toPlainText()):
                    cursor.setPosition(int(note['pos0']) - text_pos0, QtGui.QTextCursor.MoveMode.MoveAnchor)
                    cursor.setPosition(int(note['pos1']) - text_pos0, QtGui.QTextCursor.MoveMode.KeepAnchor)
                    format_bold = QtGui.QTextCharFormat()
                    format_bold.setFontWeight(QtGui.QFont.Weight.Bold)
                    cursor.mergeCharFormat(format_bold)
        self.apply_italic_to_overlaps()

    def apply_italic_to_overlaps(self):
        """ Apply italic format to coded text sections which are overlapping.
        Adjust for start of text file, as this may be a smaller portion of the full text file.
        Do not appyply overline when showing only important codes, as this causes user confusion.
        """

        if self.important:
            return
        overlaps = []
        for i in self.code_text:
            # print(item['pos0'], type(item['pos0']), item['pos1'], type(item['pos1']))
            for j in self.code_text:
                if j != i:
                    if j['pos0'] <= i['pos0'] and j['pos1'] >= i['pos0']:
                        # print("overlapping: j0", j['pos0'], j['pos1'],"- i0", i['pos0'], i['pos1'])
                        if j['pos0'] >= i['pos0'] and j['pos1'] <= i['pos1']:
                            overlaps.append([j['pos0'], j['pos1']])
                        elif i['pos0'] >= j['pos0'] and i['pos1'] <= j['pos1']:
                            overlaps.append([i['pos0'], i['pos1']])
                        elif j['pos0'] > i['pos0']:
                            overlaps.append([j['pos0'], i['pos1']])
                        else:  # j['pos0'] < i['pos0']:
                            overlaps.append([j['pos1'], i['pos0']])
        # print(overlaps)
        text_pos0 = self.case_['files'][self.case_['file_index']]['pos0']
        cursor = self.ui.textEdit.textCursor()
        for o in overlaps:
            fmt = QtGui.QTextCharFormat()
            fmt.setFontItalic(True)
            cursor.setPosition(o[0] - text_pos0, QtGui.QTextCursor.MoveMode.MoveAnchor)
            cursor.setPosition(o[1] - text_pos0, QtGui.QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(fmt)

    def select_tree_item_by_code_name(self, codename):
        """ Set a tree item code. This still call fill_code_label and
         put the selected code in the top left code label and
         param:
            codename: a string of the codename
         """

        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        while item:
            if item.text(0) == codename:
                self.ui.treeWidget.setCurrentItem(item)
            it += 1
            item = it.value()
        self.fill_code_label_undo_show_selected_code()

    def mark(self):
        """ Mark selected text in file with currently selected code.
       Need to check for multiple same codes at same pos0 and pos1.
       Update recent_codes list.
       Adjust for start of text file, as this may be a smaller portion of the full text file.
       """

        if self.case_ is None:
            return
        item = self.ui.treeWidget.currentItem()
        if item is None:
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec()
            return
        if item.text(1).split(':')[0] == 'catid':  # must be a code
            return
        text_pos0 = self.case_['files'][self.case_['file_index']]['pos0']
        fid = self.case_['files'][self.case_['file_index']]['fid']
        cid = int(item.text(1).split(':')[1])
        selected_text = self.ui.textEdit.textCursor().selectedText()
        pos0 = self.ui.textEdit.textCursor().selectionStart() + text_pos0
        pos1 = self.ui.textEdit.textCursor().selectionEnd() + text_pos0
        if pos0 == pos1:
            return
        # Add the coded section to code text, add to database and update GUI
        coded = {'cid': cid, 'fid': fid, 'seltext': selected_text,
        'pos0': pos0, 'pos1': pos1, 'owner': self.app.settings['codername'], 'memo': "",
        'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        'important': None}
        # Check for an existing duplicated marking first
        cur = self.app.conn.cursor()
        cur.execute("select * from code_text where cid = ? and fid=? and pos0=? and pos1=? and owner=?",
            (coded['cid'], coded['fid'], coded['pos0'], coded['pos1'], coded['owner']))
        result = cur.fetchall()
        if len(result) > 0:
            # The event can trigger multiple times, so dont present a warning to the user
            return
        self.code_text.append(coded)
        self.highlight()
        cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,\
            memo,date, important) values(?,?,?,?,?,?,?,?,?)", (coded['cid'], coded['fid'],
            coded['seltext'], coded['pos0'], coded['pos1'], coded['owner'],
            coded['memo'], coded['date'], coded['important']))
        self.app.conn.commit()
        self.app.delete_backup = False
        # Update filter for tooltip and update code colours
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        # Update recent_codes
        tmp_code = None
        for c in self.codes:
            if c['cid'] == cid:
                tmp_code = c
        if tmp_code is None:
            return
        # Need to remove as may not be in first position
        for item in self.recent_codes:
            if item == tmp_code:
                self.recent_codes.remove(item)
                break
        self.recent_codes.insert(0, tmp_code)
        if len(self.recent_codes) > 10:
            self.recent_codes = self.recent_codes[:10]

    def unmark(self, location):
        """ Remove code marking by this coder from selected text in current file.
        Called by text_edit_context_menu
        Adjust for start of text file, as this may be a smaller portion of the full text file.
        param:
            location: text cursor location, Integer
        """

        if self.case_ is None:
            return
        unmarked_list = []
        text_pos0 = self.case_['files'][self.case_['file_index']]['pos0']
        for item in self.code_text:
            if location + text_pos0 >= item['pos0'] and location + text_pos0 <= item['pos1'] and \
                    item['owner'] == self.app.settings['codername']:
                unmarked_list.append(item)
        if not unmarked_list:
            return
        to_unmark = []
        if len(unmarked_list) == 1:
            to_unmark = [unmarked_list[0]]
        # Multiple codes to select from
        if len(unmarked_list) > 1:
            ui = DialogSelectItems(self.app, unmarked_list, _("Select code to unmark"), "multi")
            ok = ui.exec()
            if not ok:
                return
            to_unmark = ui.get_selected()
        if to_unmark is None:
            return
        # Delete from db, remove from coding and update highlights
        cur = self.app.conn.cursor()
        for item in to_unmark:
            cur.execute("delete from code_text where cid=? and pos0=? and pos1=? and owner=? and fid=?",
                (item['cid'], item['pos0'], item['pos1'], self.app.settings['codername'], item['fid']))
            self.app.conn.commit()
        # Update filter for tooltip and update code colours
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        self.app.delete_backup = False

    def annotate(self, cursor_pos=None):
        """ Add view, or remove an annotation for selected text.
        Annotation positions are displayed as bold text.
        Adjust for start of text file, as this may be a smaller portion of the full text file.

        Called via context menu, button
        """

        if self.case_ is None:
            Message(self.app, _('Warning'), _("No file was selected"), "warning").exec()
            return
        pos0 = self.ui.textEdit.textCursor().selectionStart()
        pos1 = self.ui.textEdit.textCursor().selectionEnd()
        text_length = len(self.ui.textEdit.toPlainText())
        if pos0 >= text_length or pos1 > text_length:
            return
        item = None
        details = ""
        annotation = ""
        text_pos0 = self.case_['files'][self.case_['file_index']]['pos0']
        fid = self.case_['files'][self.case_['file_index']]['fid']
        filename = self.case_['files'][self.case_['file_index']]['filename']

        # Find annotation at this position for this file
        if cursor_pos is None:
            for note in self.annotations:
                if ((pos0 + text_pos0 >= note['pos0'] and pos0 + text_pos0 <= note['pos1']) or
                        (pos1 + text_pos0 >= note['pos0'] and pos1 + text_pos0 <= note['pos1'])) \
                        and note['fid'] == fid:
                    item = note  # use existing annotation
                    details = item['owner'] + " " + item['date']
                    break
        if cursor_pos is not None:  # Try point position, if cursor is on an annotation, but no text selected
            for note in self.annotations:
                if cursor_pos + text_pos0 >= note['pos0'] and cursor_pos <= note['pos1'] + text_pos0 \
                        and note['fid'] == fid:
                    item = note  # use existing annotation
                    details = item['owner'] + " " + item['date']
                    pos0 = cursor_pos
                    pos1 = cursor_pos
                    break
        # Exit this method if no text selected and there is no annotation at this position
        if pos0 == pos1 and item is None:
            return

        # Add new item to annotations, add to database and update GUI
        if item is None:
            item = {'fid': fid, 'pos0': pos0 + text_pos0, 'pos1': pos1 + text_pos0,
            'memo': str(annotation), 'owner': self.app.settings['codername'],
            'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'anid': -1}
            ui = DialogMemo(self.app, _("Annotation: ") + details, item['memo'])
            ui.exec()
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
                self.parent_textEdit.append(_("Annotation added at position: ") \
                    + str(item['pos0']) + "-" + str(item['pos1']) + _(" for: ") + filename)
                self.get_coded_text_update_eventfilter_tooltips()
            return

        # Edit existing annotation
        ui = DialogMemo(self.app, _("Annotation: ") + details, item['memo'])
        ui.exec()
        item['memo'] = ui.memo
        if item['memo'] != "":
            item['date'] = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
            cur = self.app.conn.cursor()
            sql = "update annotation set memo=?, date=? where anid=?"
            cur.execute(sql, (item['memo'], item['date'], item['anid']))
            self.app.conn.commit()
            self.app.delete_backup = False

            self.annotations = self.app.get_annotations()
            self.get_coded_text_update_eventfilter_tooltips()
            return

        # If blank delete the annotation
        if item['memo'] == "":
            cur = self.app.conn.cursor()
            cur.execute("delete from annotation where pos0 = ?", (item['pos0'], ))
            self.app.conn.commit()
            self.app.delete_backup = False
            self.annotations = self.app.get_annotations()
            self.parent_textEdit.append(_("Annotation removed from position ") \
                + str(item['pos0']) + _(" for: ") + filename)
        self.get_coded_text_update_eventfilter_tooltips()

    # Image related methods
    def get_coded_areas(self):
        """ Get the coded area details for the rectangles.
        Called by init and by unmark. """

        self.code_areas = []
        sql = "select imid,id,x1, y1, width, height, memo, date, owner, cid, important from code_image"
        cur = self.app.conn.cursor()
        cur.execute(sql)
        results = cur.fetchall()
        keys = 'imid', 'id', 'x1', 'y1', 'width', 'height', 'memo', 'date', 'owner', 'cid', 'important'
        for row in results:
            self.code_areas.append(dict(zip(keys, row)))

    def load_image(self):
        """ Add image to scene if image file exists. If not exists clear the GUI and variables.
        Called by: select_image_menu, listwidgetitem_view_file
        """

        source = self.app.project_path + self.case_['files'][self.case_['file_index']]['mediapath']
        if self.case_['files'][self.case_['file_index']]['mediapath'][0:7] == "images:":
            source = self.case_['files'][self.case_['file_index']]['mediapath'][7:]
        image = QtGui.QImage(source)
        if image.isNull():
            self.clear_image()
            Message(self.app, _("Image Error"), _("Cannot open: ", "warning") + source).exec()
            logger.warning("Cannot open image: " + source)
            return
        items = list(self.scene.items())
        for i in range(items.__len__()):
            self.scene.removeItem(items[i])
        self.pixmap = QtGui.QPixmap.fromImage(image)
        pixmap_item = QtWidgets.QGraphicsPixmapItem(QtGui.QPixmap.fromImage(image))
        pixmap_item.setPos(0, 0)
        self.scene.setSceneRect(QtCore.QRectF(0, 0, self.pixmap.width(), self.pixmap.height()))
        self.scene.addItem(pixmap_item)
        self.ui.horizontalSlider.setValue(99)

        # Scale initial picture by height to mostly fit inside scroll area
        # Tried other methods e.g. sizes of components, but nothing was correct.
        # slider and groupbox approx heights
        if self.pixmap.height() > self.height() - 30 - 100:
            scale = (self.height() - 30 - 100) / self.pixmap.height()
            slider_value = int(scale * 100)
            if slider_value > 100:
                slider_value = 100
            self.ui.horizontalSlider.setValue(slider_value)
        self.draw_coded_areas()
        self.fill_code_counts_in_tree()

    def clear_image(self):
        """ When image removed clear all details.
        Called by null file in load_file, and from ManageFiles.delete. """

        self.img_selection = None
        self.img_scale = 1.0
        items = list(self.scene.items())
        for i in range(items.__len__()):
            self.scene.removeItem(items[i])

    def redraw_scene(self):
        """ Resize image. Triggered by user change in slider.
        Also called by unmark, as all items need to be redrawn. """

        if self.pixmap is None:
            return
        self.scale = (self.ui.horizontalSlider.value() + 1) / 100
        height = int(self.scale * self.pixmap.height())
        pixmap = self.pixmap.scaledToHeight(height, QtCore.Qt.TransformationMode.FastTransformation)
        pixmap_item = QtWidgets.QGraphicsPixmapItem(pixmap)
        pixmap_item.setPos(0, 0)
        self.scene.clear()
        self.scene.addItem(pixmap_item)
        self.draw_coded_areas()
        self.ui.horizontalSlider.setToolTip(_("Scale: ") + str(int(self.scale * 100)) + "%")

    def draw_coded_areas(self):
        """ Draw coded areas with scaling. This coder is shown in dashed rectangles.
        Other coders are shown via dotline rectangles.
        Remove items first, as this is called after a coded area is unmarked. """

        if self.case_ is None:
            return
        fid = self.case_['files'][self.case_['file_index']]['fid']
        for item in self.code_areas:
            if item['id'] == fid:
                color = QtGui.QColor('#AA0000')  # Default color
                tooltip = ""
                for c in self.codes:
                    if c['cid'] == item['cid']:
                        tooltip = c['name'] + " (" + item['owner'] + ")"
                        if item['memo'] != "":
                            tooltip += "\nMemo: " + item['memo']
                        if item['important'] == 1:
                            tooltip += "\n" + _("IMPORTANT")
                        color = QtGui.QColor(c['color'])
                x = item['x1'] * self.scale
                y = item['y1'] * self.scale
                width = item['width'] * self.scale
                height = item['height'] * self.scale
                rect_item = QtWidgets.QGraphicsRectItem(x, y, width, height)
                rect_item.setPen(QtGui.QPen(color, 2, QtCore.Qt.PenStyle.DashLine))
                rect_item.setToolTip(tooltip)
                if item['owner'] == self.app.settings['codername']:
                    if self.important and item['important'] == 1:
                        self.scene.addItem(rect_item)
                    if not self.important:
                        self.scene.addItem(rect_item)

    def scene_context_menu(self, pos):
        """ Scene context menu for setting importance, unmarking coded areas and adding memos. """

        # Outside image area, no context menu
        for item in self.scene.items():
            if type(item) == QtWidgets.QGraphicsPixmapItem:
                if pos.x() > item.boundingRect().width() or pos.y() > item.boundingRect().height():
                    self.selection = None
                    return
        global_pos = QtGui.QCursor.pos()
        item = self.find_coded_areas_for_pos(pos)
        # No coded area item in this mouse position
        if item is None:
            return
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_memo = menu.addAction(_('Memo'))
        action_unmark = menu.addAction(_('Unmark'))
        action_important = None
        if item['important'] is None or item['important'] != 1:
            action_important = menu.addAction(_("Add important mark"))
        action_not_important = None
        if item['important'] == 1:
            action_not_important = menu.addAction(_("Remove important mark"))
        action = menu.exec(global_pos)
        if action is None:
            return
        if action == action_memo:
            self.img_coded_area_memo(item)
            self.app.delete_backup = False
            return
        if action == action_unmark:
            self.img_unmark(item)
            self.app.delete_backup = False
            return
        if action == action_important:
            self.img_set_importance(item)
            return
        if action == action_not_important:
            self.img_set_importance(item, False)
            return

    def find_coded_areas_for_pos(self, pos):
        """ Find any coded areas for this position AND for this coder.

        param: pos
        returns: None or coded item
        """

        if self.case_ is None:
            return
        fid = self.case_['files'][self.case_['file_index']]['fid']
        for item in self.code_areas:
            if item['id'] == fid and item['owner'] == self.app.settings['codername']:
                # print(pos, item['x1'], item['y1'], item['width'], item['height'])
                if pos.x() >= item['x1'] * self.scale and pos.x() <= (item['x1'] + item['width']) * self.scale \
                    and pos.y() >= item['y1'] * self.scale and pos.y() <= (item['y1'] + item['height']) * self.scale:
                    return item
        return None

    def img_set_importance(self, item, important=True):
        """ Set or unset importance to coded image item.
        Importance is denoted using '1'
        params:
            item: dictionary of coded area
            important: boolean, default True """

        importance = None
        if important:
            importance = 1
        item['important'] = importance
        cur = self.app.conn.cursor()
        cur.execute('update code_image set important=? where imid=?', (importance, item['imid']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.draw_coded_areas()

    def img_coded_area_memo(self, item):
        """ Add memo to this coded area.
        param:
            item : dictionary of coded area """

        filename = self.case_['files'][self.case_['file_index']]['filename']
        ui = DialogMemo(self.app, _("Memo for coded area of ") + filename,
            item['memo'])
        ui.exec()
        memo = ui.memo
        if memo != item['memo']:
            item['memo'] = memo
            cur = self.app.conn.cursor()
            cur.execute('update code_image set memo=? where imid=?', (ui.memo, item['imid']))
            self.app.conn.commit()
        # re-draw to update memos in tooltips
        self.draw_coded_areas()

    def img_unmark(self, item):
        """ Remove coded area.
        param:
            item : dictionary of coded area """

        cur = self.app.conn.cursor()
        cur.execute("delete from code_image where imid=?", [item['imid'], ])
        self.app.conn.commit()
        self.get_coded_areas()
        self.redraw_scene()
        self.fill_code_counts_in_tree()

    def img_create_coded_area(self, p1):
        """ Create coded area coordinates from mouse release.
        The point and width and height must be based on the original image size,
        so add in scale factor.
        param:
            p1 : QPoint of mouse release """

        code_ = self.ui.treeWidget.currentItem()
        if code_ is None:
            return
        if code_.text(1)[0:3] == 'cat':
            return
        fid = self.case_['files'][self.case_['file_index']]['fid']
        cid = int(code_.text(1)[4:])  # must be integer
        x = self.selection.x()
        y = self.selection.y()
        # print("x", x, "y", y, "scale", self.scale)
        width = p1.x() - x
        height = p1.y() - y
        if width < 0:
            x = x + width
            width = abs(width)
        if height < 0:
            y = y + height
            height = abs(height)
        # print("SCALED x", x, "y", y, "w", width, "h", height)
        # Outside image area, do not code
        for item in self.scene.items():
            if type(item) == QtWidgets.QGraphicsPixmapItem:
                if x + width > item.boundingRect().width() or y + height > item.boundingRect().height():
                    self.selection = None
                    return
        x_unscaled = x / self.scale
        y_unscaled = y / self.scale
        width_unscaled = width / self.scale
        height_unscaled = height / self.scale
        if width_unscaled == 0 or height_unscaled == 0:
            return
        #print("UNSCALED x", x, "y", y, "w", width, "h", height)
        item = {'imid': None, 'id': fid, 'x1': x_unscaled, 'y1': y_unscaled,
        'width': width_unscaled, 'height': height_unscaled, 'owner': self.app.settings['codername'],
         'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        'cid': cid, 'memo': '', 'important': None}
        cur = self.app.conn.cursor()
        cur.execute("insert into code_image (id,x1,y1,width,height,cid,memo,date,owner, important) values(?,?,?,?,?,?,?,?,?,null)"
            , (item['id'], item['x1'], item['y1'], item['width'], item['height'], cid, item['memo'],
            item['date'], item['owner']))
        self.app.conn.commit()
        cur.execute("select last_insert_rowid()")
        imid = cur.fetchone()[0]
        item['imid'] = imid
        self.code_areas.append(item)
        rect_item = QtWidgets.QGraphicsRectItem(x, y, width, height)
        color = None
        for i in range(0, len(self.codes)):
            if self.codes[i]['cid'] == int(cid):
                color = QtGui.QColor(self.codes[i]['color'])
        if color is None:
            print("img_create_coded_area CANNOT FIND COLOR ERROR")
            return
        rect_item.setPen(QtGui.QPen(color, 2, QtCore.Qt.PenStyle.DashLine))
        rect_item.setToolTip(code_.text(0))
        self.scene.addItem(rect_item)
        self.selection = None
        self.app.delete_backup = False
        self.fill_code_counts_in_tree()

    # Audio/video methods
    def load_av_media(self):
        """ Add av media to media dialog. """

        mediapath = self.case_['files'][self.case_['file_index']]['mediapath']
        filename = self.case_['files'][self.case_['file_index']]['filename']
        ftype = self.case_['files'][self.case_['file_index']]['filetype']
        try:
            if mediapath[0:6] in ('/audio', '/video'):
                self.media = self.instance.media_new(self.app.project_path + mediapath)
            if mediapath[0:6] in ('audio:', 'video:'):
                self.media = self.instance.media_new(mediapath[6:])
        except Exception as e_:
            Message(self.app, _('Media not found'), str(e_) + "\n" + self.app.project_path + mediapath, "warning").exec()
            return
        title = filename.split('/')[-1]
        self.ddialog.setWindowTitle(title)
        if ftype == "video":
            self.ddialog.show()
            try:
                w = int(self.app.settings['video_w'])
                h = int(self.app.settings['video_h'])
                if w < 100 or h < 80:
                    w = 100
                    h = 80
                self.ddialog.resize(w, h)
            except KeyError:
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
            self.mediaplayer.set_xwindow(int(self.ddialog.winId()))
        elif platform.system() == "Windows":  # for Windows
            self.mediaplayer.set_hwnd(int(self.ddialog.winId()))
        elif platform.system() == "Darwin":  # for MacOS
            self.mediaplayer.set_nsobject(int(self.ddialog.winId()))
        msecs = self.media.get_duration()
        self.media_duration_text = " / " + msecs_to_hours_mins_secs(msecs)
        self.ui.label_time.setText("0.00" + self.media_duration_text)
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.update_ui)

        # Need this for helping set the slider on user sliding before play begins
        # Also need to determine how many tracks available
        self.mediaplayer.play()
        self.mediaplayer.audio_set_volume(0)
        time.sleep(0.2)
        # print( self.mediaplayer.audio_get_track_count()) # > 0
        tracks = self.mediaplayer.audio_get_track_description()
        good_tracks = []  # note where track [0] == -1 is a disabled track
        for track in tracks:
            if track[0] >= 0:
                good_tracks.append(track)
        if len(good_tracks) < 2:
            self.ui.comboBox_tracks.setEnabled(False)
        self.mediaplayer.pause()
        self.mediaplayer.audio_set_volume(100)
        self.load_segments()

    def load_segments(self):
        """ Get coded segments for this file and for this coder.
        Called from load_av_media, update_ui. """

        if self.case_ is None:
            return
        fid = self.case_['files'][self.case_['file_index']]['fid']
        # 10 is assigned as an initial default for y values for segments
        sql = "select avid, id, pos0, pos1, code_av.cid, code_av.memo, code_av.date, "
        sql += " code_av.owner, code_name.name, code_name.color, 10, code_av.important from code_av"
        sql += " join code_name on code_name.cid=code_av.cid"
        sql += " where id=? "
        sql += " and code_av.owner=? "
        values = [fid]
        values.append(self.app.settings['codername'])
        cur = self.app.conn.cursor()
        cur.execute(sql, values)
        results = cur.fetchall()
        keys = 'avid', 'id', 'pos0', 'pos1', 'cid', 'memo', 'date', 'owner', 'codename', 'color', 'y', 'important'
        self.segments = []
        for row in results:
            self.segments.append(dict(zip(keys, row)))
        # Fix overlapping segments by incrementing y values so segment is shown on a different line
        for i in range(0, len(self.segments) - 1):
            for j in range(i + 1, len(self.segments)):
                if (self.segments[j]['pos0'] >= self.segments[i]['pos0'] and
                    self.segments[j]['pos0'] <= self.segments[i]['pos1'] and
                    self.segments[i]['y'] == self.segments[j]['y']) or \
                        (self.segments[j]['pos0'] <= self.segments[i]['pos0'] and
                         self.segments[j]['pos1'] >= self.segments[i]['pos0'] and
                         self.segments[i]['y'] == self.segments[j]['y']):
                    # print("\nOVERLAP i:", self.segments[i]['pos0'], self.segments[i]['pos1'], self.segments[i]['y'], self.segments[i]['codename'])
                    # print("OVERLAP j:", self.segments[j]['pos0'], self.segments[j]['pos1'], self.segments[j]['y'], self.segments[j]['codename'])
                    # to overcome the overlap, add to the y value of the i segment
                    self.segments[j]['y'] += 10
        # Add seltext, the text link to the segment, used in segment tooltip
        sql = "select seltext from code_text where avid=?"
        for s in self.segments:
            cur.execute(sql, [s['avid']])
            res = cur.fetchall()
            text_ = ""
            for r in res:
                text_ += str(r[0]) + "\n"
            s['seltext'] = text_

        # Draw coded segments in scene, scale segments to graphics view witdth
        self.av_scene_width = self.ui.graphicsView_av.viewport().size().width()
        self.av_scene = GraphicsScene(self.av_scene_width, self.av_scene_height)
        self.ui.graphicsView_av.setScene(self.av_scene)
        scaler = self.av_scene_width / self.media.get_duration()
        self.av_scene.clear()
        for s in self.segments:
            self.av_scene.addItem(SegmentGraphicsItem(self.app, s, scaler, self))
        # Set the scene to the top
        self.ui.graphicsView_av.verticalScrollBar().setValue(0)

    def rewind_30_seconds(self):
        """ Rewind AV by 30 seconds. Alt + R """

        if self.mediaplayer.get_media() is None:
            return
        time_msecs = self.mediaplayer.get_time() - 30000
        if time_msecs < 0:
            time_msecs = 0
        pos = time_msecs / self.mediaplayer.get_media().get_duration()
        self.mediaplayer.set_position(pos)
        # Update timer display
        msecs = self.mediaplayer.get_time()
        self.ui.label_time.setText(msecs_to_hours_mins_secs(msecs) + self.media_duration_text)
        self.update_ui()

    def rewind_5_seconds(self):
        """ Rewind AV by 30 seconds. Ctrl + R """

        if self.mediaplayer.get_media() is None:
            return
        time_msecs = self.mediaplayer.get_time() - 5000
        if time_msecs < 0:
            time_msecs = 0
        pos = time_msecs / self.mediaplayer.get_media().get_duration()
        self.mediaplayer.set_position(pos)
        # Update timer display
        msecs = self.mediaplayer.get_time()
        self.ui.label_time.setText(msecs_to_hours_mins_secs(msecs) + self.media_duration_text)
        self.update_ui()

    def forward_30_seconds(self):
        """ Forward AV 30 seconds. Alt + F """

        if self.mediaplayer.get_media() is None:
            return
        time_msecs = self.mediaplayer.get_time() + 30000
        if time_msecs > self.media.get_duration():
            time_msecs = self.media.get_duration() - 1
        pos = time_msecs / self.mediaplayer.get_media().get_duration()
        self.mediaplayer.set_position(pos)
        # Update timer display
        msecs = self.mediaplayer.get_time()
        self.ui.label_time.setText(msecs_to_hours_mins_secs(msecs) + self.media_duration_text)
        self.update_ui()

    def increase_play_rate(self):
        """ Several increased rate options """

        rate = self.mediaplayer.get_rate()
        rate += 0.1
        if rate > 2:
            rate = 2
        self.mediaplayer.set_rate(rate)
        self.ui.label_rate.setText(str(round(rate, 1)) + "x")

    def decrease_play_rate(self):
        """ Several decreased rate options """

        rate = self.mediaplayer.get_rate()
        rate -= 0.1
        if rate < 0.1:
            rate = 0.1
        self.mediaplayer.set_rate(rate)
        self.ui.label_rate.setText(str(round(rate, 1)) + "x")

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
        time_ = self.ui.label_time.text()
        time_ = time_.split(" / ")[0]
        time_msecs = self.mediaplayer.get_time()
        if self.segment['start'] is None:
            self.segment['start'] = time_
            self.segment['start_msecs'] = time_msecs
            self.segment['memo'] = ""
            self.segment['important'] = None
            self.segment['seltext'] = ""
            self.ui.pushButton_coding.setText(_("End segment"))
            self.ui.label_segment.setText(_("Segment: ") + str(self.segment['start']) + " - ")
            return
        if self.segment['start'] is not None and self.segment['end'] is None:
            self.segment['end'] = time_
            self.segment['end_msecs'] = time_msecs
            self.ui.pushButton_coding.setText(_("Clear segment"))
            # Check and reverse start and end times if start is greater than the end
            # print("start", self.segment['start'], "end", self.segment['end'])
            if self.segment['start_msecs'] > self.segment['end_msecs']:
                tmp = self.segment['start']
                tmp_msecs = self.segment['start_msecs']
                self.segment['start'] = self.segment['end']
                self.segment['start_msecs'] = self.segment['end_msecs']
                self.segment['end'] = tmp
                self.segment['end_msecs'] = tmp_msecs
            text_ = _("Segment: ") + str(self.segment['start']) + " - " + self.segment['end']
            self.ui.label_segment.setText(text_)

    def clear_segment(self):
        """ Called by assign_segment_to code. """

        self.segment['start'] = None
        self.segment['start_msecs'] = None
        self.segment['end'] = None
        self.segment['end_msecs'] = None
        self.segment['memo'] = ""
        self.segment['important'] = None
        self.segment['seltext'] = ""
        self.ui.label_segment.setText(_("Segment:"))
        self.ui.pushButton_coding.setText(_("Start segment"))

    def set_position(self):
        """ Set the movie position according to the position slider.
        The vlc MediaPlayer needs a float value between 0 and 1, Qt uses
        integer variables, so you need a factor; the higher the factor, the
        more precise are the results (1000 should suffice).
        """

        if self.mediaplayer.is_playing():
            self.mediaplayer.pause()
            pos = self.ui.horizontalSlider_av.value()
            self.mediaplayer.set_position(pos / 1000.0)
            self.mediaplayer.play()
            self.timer.start()
        else:
            pos = self.ui.horizontalSlider.value()
            self.mediaplayer.set_position(pos / 1000.0)

        # msecs is -1 if the video has not been played yet ?
        msecs = self.mediaplayer.get_time()
        self.ui.label_time.setText(msecs_to_hours_mins_secs(msecs) + self.media_duration_text)

    def audio_track_changed(self):
        """ Audio track changed.
        The video needs to be playing/paused before the combobox is filled with track options.
        The combobox only has positive integers."""

        text_ = self.ui.comboBox_tracks.currentText()
        if text_ == "":
            text_ = "1"
        success = self.mediaplayer.audio_set_track(int(text_))

    def play_pause(self):
        """ Toggle play or pause status. """

        # user might update window positions and sizes, need to detect it
        self.update_sizes()
        if self.mediaplayer.is_playing():
            self.mediaplayer.pause()
            pm = QtGui.QPixmap()
            pm.loadFromData(QtCore.QByteArray.fromBase64(play_icon), "png")
            self.ui.pushButton_play.setIcon(QtGui.QIcon(pm))
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
            self.ui.label_time.setText(msecs_to_hours_mins_secs(msecs) + self.media_duration_text)
            self.mediaplayer.play()
            pm = QtGui.QPixmap()
            pm.loadFromData(QtCore.QByteArray.fromBase64(playback_pause_icon), "png")
            self.ui.pushButton_play.setIcon(QtGui.QIcon(pm))
            self.timer.start()
            self.is_paused = False
            self.play_segment_end = None

    def stop(self):
        """ Stop vlc player. Set position slider to the start.
         If multiple audio tracks are shown in the combobox, set the audio track to the first index.
         This is because when beginning play again, the audio track reverts to the first track.
         Programming setting the audio track to other values does not work."""

        self.mediaplayer.stop()
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(play_icon), "png")
        self.ui.pushButton_play.setIcon(QtGui.QIcon(pm))
        self.timer.stop()
        self.ui.horizontalSlider_av.setProperty("value", 0)
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
        self.ui.horizontalSlider_av.setValue(media_pos)

        # update label_time
        msecs = self.mediaplayer.get_time()
        self.ui.label_time.setText(msecs_to_hours_mins_secs(msecs) + self.media_duration_text)

        # Check if segments need to be reloaded
        # This only updates if the media is playing, not ideal, but works
        for i in self.av_scene.items():
            if isinstance(i, SegmentGraphicsItem) and i.reload_segment is True:
                self.load_segments()

        """ For long transcripts, update the relevant text position in the textEdit to match the
        video's current position.
        time_postion list item: [text_pos0, text_pos1, milliseconds]
        """
        # No need to call this function if nothing is played
        if not self.mediaplayer.is_playing():
            self.timer.stop()
            pm = QtGui.QPixmap()
            pm.loadFromData(QtCore.QByteArray.fromBase64(play_icon), "png")
            self.ui.pushButton_play.setIcon(QtGui.QIcon(pm))
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

    #TODO remove commented out code - wait for feedback first
    '''def button_autocode_sentences_this_file(self):
        """ Flag to autocode sentences in one file """
        item = self.ui.treeWidget.currentItem()
        if item is None or item.text(1)[0:3] == 'cat':
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec_()
            return
        self.code_sentences("")

    def button_autocode_sentences_all_files(self):
        """ Flag to autocode sentences across all text files. """
        item = self.ui.treeWidget.currentItem()
        if item is None or item.text(1)[0:3] == 'cat':
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec_()
            return
        self.code_sentences("all")

    def button_autocode_surround(self):
        """ Autocode with selected code using start and end marks.
         Currently, only using the current selected file.
         Line ending text representation \\n is replaced with the actual line ending character. """

        item = self.ui.treeWidget.currentItem()
        if item is None or item.text(1)[0:3] == 'cat':
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec_()
            return
        if self.file_ is None:
            Message(self.app, _('Warning'), _("No file was selected"), "warning").exec_()
            return
        ui = DialogGetStartAndEndMarks(self.file_['name'], self.file_['name'])
        ok = ui.exec_()
        if not ok:
            return
        start_mark = ui.get_start_mark()
        if "\\n" in start_mark:
            start_mark = start_mark.replace("\\n", "\n")
        end_mark = ui.get_end_mark()
        if "\\n" in end_mark:
            end_mark = end_mark.replace("\\n", "\n")
        if start_mark == "" or end_mark == "":
            Message(self.app, _('Warning'), _("Cannot have blank text marks"), "warning").exec_()
            return

        #print("end mark: " + end_mark)
        msg = _("Code text using start and end marks: ") + self.file_['name']
        msg += _("\nUsing ") + start_mark + _(" and ") + end_mark + "\n"

        text_starts = [match.start() for match in re.finditer(re.escape(start_mark), self.file_['fulltext'])]
        text_ends = [match.start() for match in re.finditer(re.escape(end_mark), self.file_['fulltext'])]
        # Find and insert into database
        already_assigned = 0
        cid = int(item.text(1)[4:])
        cname = item.text(0)
        now_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        warning_msg = ""
        entries = 0
        undo_list = []
        cur = self.app.conn.cursor()
        for start_pos in text_starts:
            pos1 = -1  # default if not found
            text_end_iterator = 0
            try:
                while start_pos >= text_ends[text_end_iterator]:
                    text_end_iterator += 1
            except IndexError as e:
                text_end_iterator = -1
                #warning_msg += _("Could not find an end mark: ") + self.file_['name'] + "  " + end_mark + "\n"
                # logger.warning(warning_msg)
            if text_end_iterator >= 0:
                pos1 = text_ends[text_end_iterator]
                # Check if already coded in this file for this coder
                sql = "select cid from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?"
                cur.execute(sql, [cid, self.file_['id'], start_pos, pos1, self.app.settings['codername']])
                res = cur.fetchone()
                if res is None:
                    seltext = self.file_['fulltext'][start_pos : pos1]
                    sql = "insert into code_text (cid, fid, seltext, pos0, pos1, owner, date, memo) values(?,?,?,?,?,?,?,?)"
                    cur.execute(sql, (cid, self.file_['id'], seltext, start_pos, pos1,
                                   self.app.settings['codername'],now_date, ""))
                    # Add to undo auto-coding history
                    undo = {"sql": "delete from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?",
                            "cid": cid, "fid": self.file_['id'], "pos0": start_pos, "pos1": pos1, "owner": self.app.settings['codername']
                            }
                    undo_list.append(undo)
                    entries += 1
                    self.app.conn.commit()
                else:
                    already_assigned += 1
        # Add to undo auto-coding history
        if len(undo_list) > 0:
            name = _("Coding using start and end marks") + _("\nCode: ") + item.text(0)
            name += _("\nWith start mark: ") + start_mark + _("\nEnd mark: ") + end_mark
            undo_dict = {"name": name, "sql_list": undo_list}
            self.autocode_history.insert(0, undo_dict)

        # Update filter for tooltip and update code colours
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        msg += str(entries) + _(" new coded sections found.") + "\n"
        if already_assigned > 0:
            msg += str(already_assigned) + " " + _("previously coded.") + "\n"
        #msg += warning_msg
        self.parent_textEdit.append(msg)
        self.app.delete_backup = False

    def undo_autocoding(self):
        """ Present a list of choices for the undo operation.
         Use selects and undoes the chosen autocoding operation.
         The autocode_history is a list of dictionaries with 'name' and 'sql_list' """

        if self.autocode_history == []:
            return
        ui = DialogSelectItems(self.app, self.autocode_history, _("Select auto-codings to undo"), "single")
        ok = ui.exec_()
        if not ok:
            return
        undo = ui.get_selected()
        self.autocode_history.remove(undo)

        # Run all sqls
        cur = self.app.conn.cursor()
        for i in undo['sql_list']:
            cur.execute(i['sql'], [i['cid'], i['fid'], i['pos0'], i['pos1'], i['owner']])
        self.app.conn.commit()
        self.parent_textEdit.append(_("Undo autocoding: " + undo['name'] + "\n"))

        # Update filter for tooltip and update code colours
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()

    def code_sentences(self, all=""):
        """ Code full sentence based on text fragment.

        param:
            all = "" :  for this text file only.
            all = "all" :  for all text files.
        """

        item = self.ui.treeWidget.currentItem()
        if item is None or item.text(1)[0:3] == 'cat':
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec_()
            return
        cid = int(item.text(1).split(':')[1])
        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        dialog.setWindowTitle(_("Code sentence"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.TextInput)
        dialog.setLabelText(_("Auto code sentence using this text fragment:"))
        dialog.resize(200, 20)
        ok = dialog.exec_()
        if not ok:
            return
        text = dialog.textValue()
        if text == "":
            return
        dialog2 = QtWidgets.QInputDialog(None)
        dialog2.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        dialog2.setWindowTitle(_("Code sentence"))
        dialog2.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        dialog2.setInputMode(QtWidgets.QInputDialog.TextInput)
        dialog2.setToolTip("Use \\n for line ending")
        dialog2.setLabelText(_("Define sentence ending. Default is period space.\nUse \\n for line ending:"))
        dialog2.setTextValue(". ")
        dialog2.resize(200, 40)
        ok2 = dialog2.exec_()
        if not ok2:
            return
        ending = dialog2.textValue()
        if ending == "":
            return
        ending = ending.replace("\\n", "\n")
        files= []
        if all == "all":
            files = self.app.get_file_texts()
        else:
            files = self.app.get_file_texts([self.file_['id'], ])
        cur = self.app.conn.cursor()
        msg = ""
        undo_list = []
        for f in files:
            sentences = f['fulltext'].split(ending)
            pos0 = 0
            codes_added = 0
            for sentence in sentences:
                if text in sentence:
                    i = {'cid': cid, 'fid': int(f['id']), 'seltext': str(sentence),
                            'pos0': pos0, 'pos1': pos0 + len(sentence),
                            'owner': self.app.settings['codername'], 'memo': "",
                            'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
                    #TODO IntegrityError: UNIQUE constraint failed: code_text.cid, code_text.fid, code_text.pos0, code_text.pos1, code_text.owner
                    try:
                        codes_added += 1
                        cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,\
                            owner,memo,date) values(?,?,?,?,?,?,?,?)"
                            , (i['cid'], i['fid'], i['seltext'], i['pos0'],
                            i['pos1'], i['owner'], i['memo'], i['date']))
                        self.app.conn.commit()
                        # Record a list of undo sql
                        undo = {"sql": "delete from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?",
                            "cid": i['cid'], "fid": i['fid'], "pos0": i['pos0'], "pos1": i['pos1'], "owner": i['owner']
                            }
                        undo_list.append(undo)
                    except Exception as e:
                        logger.debug(_("Autocode insert error ") + str(e))
                pos0 += len(sentence) + len(ending)
            if codes_added > 0:
                msg += _("File: ") + f['name'] + " " + str(codes_added) + _(" added codes") + "\n"
        if len(undo_list) > 0:
            name = _("Sentence coding: ") + _("\nCode: ") + item.text(0)
            name += _("\nWith: ") + text + _("\nUsing line ending: ") + ending
            undo_dict = {"name": name, "sql_list": undo_list}
            self.autocode_history.insert(0, undo_dict)
        self.parent_textEdit.append(_("Automatic code sentence in files:") \
            + _("\nCode: ") + item.text(0)
            + _("\nWith text fragment: ") + text  + _("\nUsing line ending: ") + ending + "\n" + msg)
        self.app.delete_backup = False
        # Update tooltip filter and code tree code counts
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()

    def auto_code(self):
        """ Autocode text in one file or all files with currently selected code.
        """

        code_item = self.ui.treeWidget.currentItem()
        if code_item is None or code_item.text(1)[0:3] == 'cat':
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec_()
            return
        cid = int(code_item.text(1).split(':')[1])
        # Input dialog too narrow, so code below
        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        dialog.setWindowTitle(_("Automatic coding"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.TextInput)
        dialog.setToolTip(_("Use | to code multiple texts"))
        dialog.setLabelText(_("Auto code files with the current code for this text:") + "\n" + code_item.text(0))
        dialog.resize(200, 20)
        ok = dialog.exec_()
        if not ok:
            return
        find_text = str(dialog.textValue())
        if find_text == "" or find_text is None:
            return
        texts = find_text.split('|')
        tmp = list(set(texts))
        texts = []
        for t in tmp:
            if t != "":
                texts.append(t)
        if len(self.filenames) == 0:
            return
        ui = DialogSelectItems(self.app, self.filenames, _("Select files to code"), "many")
        ok = ui.exec_()
        if not ok:
            return
        files = ui.get_selected()
        if len(files) == 0:
            return

        undo_list = []
        cur = self.app.conn.cursor()
        for txt in texts:
            filenames = ""
            for f in files:
                filenames += f['name'] + " "
                cur = self.app.conn.cursor()
                cur.execute("select name, id, fulltext, memo, owner, date from source where id=? and mediapath is Null",
                    [f['id']])
                currentfile = cur.fetchone()
                text = currentfile[2]
                textStarts = [match.start() for match in re.finditer(re.escape(txt), text)]
                # Add new items to database
                for startPos in textStarts:
                    item = {'cid': cid, 'fid': int(f['id']), 'seltext': str(txt),
                    'pos0': startPos, 'pos1': startPos + len(txt),
                    'owner': self.app.settings['codername'], 'memo': "",
                    'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
                    #TODO IntegrityError: UNIQUE constraint failed: code_text.cid, code_text.fid, code_text.pos0, code_text.pos1, code_text.owner
                    try:
                        cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,\
                            owner,memo,date) values(?,?,?,?,?,?,?,?)"
                            , (item['cid'], item['fid'], item['seltext'], item['pos0'],
                            item['pos1'], item['owner'], item['memo'], item['date']))
                        self.app.conn.commit()
                        # Record a list of undo sql
                        undo = {"sql": "delete from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?",
                            "cid": item['cid'], "fid": item['fid'], "pos0": item['pos0'], "pos1": item['pos1'], "owner": item['owner']
                            }
                        undo_list.append(undo)
                    except Exception as e:
                        logger.debug(_("Autocode insert error ") + str(e))
                    self.app.delete_backup = False
                self.parent_textEdit.append(_("Automatic coding in files: ") + filenames \
                    + _(". with text: ") + txt)
        if len(undo_list) > 0:
            name = _("Text coding: ") + _("\nCode: ") + code_item.text(0)
            name += _("\nWith: ") + find_text
            undo_dict = {"name": name, "sql_list": undo_list}
            self.autocode_history.insert(0, undo_dict)
        # Update tooltip filter and code tree code counts
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()'''


class ToolTipEventFilter(QtCore.QObject):
    """ Used to add a dynamic tooltip for the textEdit.
    The tool top text is changed according to its position in the text.
    If over a coded section the codename(s) or Annotation note are displayed in the tooltip.
    """

    codes = None
    code_text = None
    annotations = None
    offset = 0

    def set_codes_and_annotations(self, code_text, codes, annotations, offset):
        """ Code_text contains the coded text to be displayed in a tooptip.
        Annotations - a mention is made if current position is annotated

        param:
            code_text: List of dictionaries of the coded text contains: pos0, pos1, seltext, cid, memo
            codes: List of dictionaries contains id, name, color
            annotations: List of dictionaries of
            offset: integer 0 if all the text is loaded, other numbers mean a portion of the text is loaded, beginning at the offset
        """

        self.code_text = code_text
        self.codes = codes
        self.annotations = annotations
        self.offset = offset
        for item in self.code_text:
            for c in self.codes:
                if item['cid'] == c['cid']:
                    item['name'] = c['name']
                    item['color'] = c['color']

    def eventFilter(self, receiver, event):
        if event.type() == QtCore.QEvent.Type.ToolTip:
            cursor = receiver.cursorForPosition(event.pos())
            pos = cursor.position()
            receiver.setToolTip("")
            text_ = ""
            multiple_msg = '<p style="color:#f89407">' + _("Press O to cycle overlapping codes") + "</p>"
            multiple = 0
            # Occasional None type error
            if self.code_text is None:
                # Call Base Class Method to Continue Normal Event Processing
                return super(ToolTipEventFilter, self).eventFilter(receiver, event)
            for item in self.code_text:
                if item['pos0'] - self.offset <= pos and item['pos1'] - self.offset >= pos and item['seltext'] is not None:
                    seltext = item['seltext']
                    seltext = seltext.replace("\n", "")
                    seltext = seltext.replace("\r", "")
                    # Selected text is long show start end snippets with a readable cut off (ie not cut off halfway through a word)
                    if len(seltext) > 90:
                        pre = seltext[0:40].split(' ')
                        post = seltext[len(seltext) - 40:].split(' ')
                        try:
                            pre = pre[:-1]
                        except:
                            pass
                        try:
                            post = post[1:]
                        except:
                            pass
                        seltext = " ".join(pre) + " ... " + " ".join(post)
                    try:
                        color = TextColor(item['color']).recommendation
                        text_ += '<p style="background-color:' + item['color'] + "; color:" + color + '"><em>'
                        text_ += item['name'] + "</em><br />" + seltext
                        if item['memo'] is not None and item['memo'] != "":
                            text_ += "<br /><em>" + _("Memo: ") + item['memo'] + "</em>"
                        if item['important'] == 1:
                            text_ += "<br /><em>IMPORTANT</em>"
                        text_ += "</p>"
                        multiple += 1
                    except Exception as e_:
                        msg_ = "Codes ToolTipEventFilter Exception\n" + str(e_) + ". Possible key error: \n"
                        msg_ += str(item)
                        logger.error(msg_)
            if multiple > 1:
                text_ = multiple_msg + text_

            # Check annotations
            for item in self.annotations:
                if item['pos0'] - self.offset <= pos and item['pos1'] - self.offset >= pos:
                    text_ += "<p>" + _("ANNOTATED") + "</p>"
            if text_ != "":
                receiver.setToolTip(text_)
        # Call Base Class Method to Continue Normal Event Processing
        return super(ToolTipEventFilter, self).eventFilter(receiver, event)


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
    References Dialog_code_av for variables and methods.
    """

    app = None
    segment = None
    scaler = None
    reload_segment = False
    code_av_dialog = None

    def __init__(self, app, segment, scaler, code_av_dialog):  # text_for_segment, code_av_dialog):
        super(SegmentGraphicsItem, self).__init__(None)

        self.app = app
        self.segment = segment
        self.scaler = scaler
        self.code_av_dialog = code_av_dialog
        self.reload_segment = False
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.set_segment_tooltip()
        self.draw_segment()

    def contextMenuEvent(self, event):
        """
        # https://riverbankcomputing.com/pipermail/pyqt/2010-July/027094.html
        I was not able to mapToGlobal position so, the menu maps to scene position plus
        the Dialog screen position.
        Makes use of current segment: self.segment
        """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_memo = menu.addAction(_('Memo for segment'))
        action_delete = menu.addAction(_('Delete segment'))
        action_play = menu.addAction(_('Play segment'))
        action_edit_start = menu.addAction(_('Edit segment start position'))
        action_edit_end = menu.addAction(_('Edit segment end position'))
        action_important = None
        action_not_important = None
        if self.segment['important'] is None or self.segment['important'] > 1:
            action_important = menu.addAction(_("Add important mark"))
        if self.segment['important'] == 1:
            action_not_important = menu.addAction(_("Remove important mark"))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == action_memo:
            self.edit_memo()
            return
        if action == action_delete:
            self.delete()
            return
        if action == action_play:
            self.play_segment()
            return
        if action == action_edit_start:
            self.edit_segment_start()
            return
        if action == action_edit_end:
            self.edit_segment_end()
            return
        if action == action_important:
            self.set_coded_importance()
            return
        if action == action_not_important:
            self.set_coded_importance(False)
            return

    def set_coded_importance(self, important=True):
        """ Set or unset importance to self.segment.
        Importance is denoted using '1'
        params:
            important: boolean, default True """

        importance = None
        if important:
            importance = 1
        self.segment['important'] = important
        cur = self.app.conn.cursor()
        sql = "update code_av set important=?, date=? where avid=?"
        values = [importance, datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), self.segment['avid']]
        cur.execute(sql, values)
        self.app.conn.commit()
        self.app.delete_backup = False
        self.code_av_dialog.get_coded_text_update_eventfilter_tooltips()
        self.set_segment_tooltip()

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
        icon = QtGui.QIcon(QtGui.QPixmap('GUI/playback_pause_icon.png'))
        self.code_av_dialog.ui.pushButton_play.setIcon(icon)
        self.code_av_dialog.play_segment_end = self.segment['pos1']
        self.code_av_dialog.timer.start()

    def delete(self):
        """ Mark segment for deletion. Does not actually delete segment item, but hides
        it from the scene. Reload_segment is set to True, so on playing media, the update
        event will reload all segments. """

        # print(self.segment)
        ui = DialogConfirmDelete(self.app,
                                 _("Segment: ") + self.segment['codename'] + "\n" + _("Memo: ") + self.segment['memo'])
        ok = ui.exec()
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
        ui.exec()
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
        self.set_segment_tooltip()

    def set_segment_tooltip(self):
        """ Set segment tooltip from self.segment data """

        tooltip = self.segment['codename'] + "\n"
        seg_time = "[" + msecs_to_hours_mins_secs(self.segment['pos0']) + " - "
        seg_time += msecs_to_hours_mins_secs(self.segment['pos1']) + "]"
        tooltip += seg_time
        if self.segment['memo'] != "":
            tooltip += "\n" + _("MEMO: ") + self.segment['memo']
        if self.segment['seltext'] is not None and self.segment['seltext'] != "":
            tooltip += "\n" + _("LINKED TEXT: ") + self.segment['seltext']
        if self.segment['important'] == 1:
            tooltip += "\n" + _("IMPORTANT")
        self.setToolTip(tooltip)

    def redraw(self):
        """ Called from mouse move and release events. Not currently used. """

        self.draw_segment()

    def draw_segment(self):
        """ Calculate the x values for the line. """

        from_x = self.segment['pos0'] * self.scaler
        to_x = self.segment['pos1'] * self.scaler
        line_width = 8
        color = QColor(self.segment['color'])
        self.setPen(QtGui.QPen(color, line_width, QtCore.Qt.PenStyle.SolidLine))
        self.setLine(from_x, self.segment['y'], to_x, self.segment['y'])
