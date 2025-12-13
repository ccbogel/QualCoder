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

import sqlite3
from copy import copy, deepcopy
import datetime
import difflib
import logging
import os
import platform
import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/
from random import randint
import re
import subprocess
import time
import webbrowser

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor

from .add_item_name import DialogAddItemName
from .code_in_all_files import DialogCodeInAllFiles
from .color_selector import DialogColorSelect, colors, TextColor, colour_ranges, show_codes_of_colour_range
from .confirm_delete import DialogConfirmDelete
from .GUI.ui_dialog_code_av import Ui_Dialog_code_av
from .GUI.ui_dialog_view_av import Ui_Dialog_view_av
from .helpers import msecs_to_hours_mins_secs, Message, ExportDirectoryPathDialog
from .memo import DialogMemo
from .report_attributes import DialogSelectAttributeParameters
from .reports import DialogReportCoderComparisons, DialogReportCodeFrequencies  # for isinstance()
from .report_codes import DialogReportCodes
from .select_items import DialogSelectItems
# from .speech_to_text import SpeechToText  # Removed as pydub module has error re pyaudioop

# If VLC not installed, it will not crash
vlc = None
try:
    import vlc
except Exception as e:
    print(e)

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogCodeAV(QtWidgets.QDialog):
    """ View and code audio and video segments.
    Create codes and categories.  """

    app = None
    parent_textEdit = None
    tab_reports = None  # Tab widget reports, used for updates to codes
    files = []
    file_ = None
    codes = []
    recent_codes = []  # list of recent codes (up to 5) for textedit context menu
    categories = []
    tree_sort_option = "all asc"  # all desc, cat then code asc
    ddialog = None
    instance = None
    mediaplayer = None
    media = None
    metadata = None
    is_paused = False
    segment = {}  # start, end, start_msecs, end_msecs, memo, important, seltext
    segments = []
    text_for_segment = {}  # when linking text to segment
    segment_for_text = None  # when linking segment to text
    timer = QtCore.QTimer()
    play_segment_end = None
    undo_deleted_codes = []  # Undo last deleted segment code, or text code(s).

    # For transcribed text
    annotations = []
    code_text = []
    transcription = None  # A tuple of id, fulltext, name
    # transcribed time positions as list of [text_pos0, text_pos1, milliseconds]
    time_positions = []
    important = False  # Flag to show or hide important coded text and segments
    attributes = []  # Show selected files in list widget

    # Overlapping codes in text index
    overlap_code_index = 0
    # Timers to reduce overly sensitive key events: overlap, re-size oversteps by multiple characters
    code_resize_timer = 0
    overlap_timer = 0

    def __init__(self, app, parent_text_edit, tab_reports):
        """ Show list of audio and video files.
        Can code a transcribed text file for the audio / video.
        """

        super(DialogCodeAV, self).__init__()
        self.app = app
        self.tab_reports = tab_reports
        self.parent_textEdit = parent_text_edit
        self.codes = []
        self.categories = []
        self.tree_sort_option = "all asc"
        self.annotations = []
        self.code_text = []
        self.time_positions = []
        self.important = False
        self.attributes = []
        self.code_resize_timer = datetime.datetime.now()
        self.overlap_timer = datetime.datetime.now()
        self.transcription = None
        self.file_ = None
        self.segment['start'] = None
        self.segment['end'] = None
        self.segment['start_msecs'] = None
        self.segment['end_msecs'] = None
        self.play_segment_end = None
        self.segments = []
        self.media_duration_text = ""
        self.segment_for_text = None
        self.undo_deleted_codes = []
        self.get_codes_and_categories()
        self.get_recent_codes()  # After codes obtained!
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_code_av()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        try:
            s0 = int(self.app.settings['dialogcodeav_splitter0'])
            s1 = int(self.app.settings['dialogcodeav_splitter1'])
            if s0 > 10 and s1 > 10:
                self.ui.splitter.setSizes([s0, 30, s1])
            h0 = int(self.app.settings['dialogcodeav_splitter_h0'])
            h1 = int(self.app.settings['dialogcodeav_splitter_h1'])
            if h0 > 10 and h1 > 10:
                self.ui.splitter_2.setSizes([h0, h1])
        except KeyError:
            pass
        self.ui.splitter.splitterMoved.connect(self.update_sizes)
        self.ui.splitter_2.splitterMoved.connect(self.update_sizes)
        self.ui.label_volume.setPixmap(qta.icon('mdi6.volume-high').pixmap(22, 22))
        self.ui.pushButton_play.setIcon(qta.icon('mdi6.play', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_rewind_30.setIcon(qta.icon('mdi6.rewind-30', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_rewind_30.pressed.connect(self.rewind_30_seconds)
        self.ui.pushButton_rewind_5.setIcon(qta.icon('mdi6.rewind-5', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_rewind_5.pressed.connect(self.rewind_5_seconds)
        self.ui.pushButton_forward_30.setIcon(qta.icon('mdi6.fast-forward-30', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_forward_30.pressed.connect(self.forward_30_seconds)
        self.ui.pushButton_rate_down.setIcon(qta.icon('mdi6.speedometer-slow', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_rate_down.pressed.connect(self.decrease_play_rate)
        self.ui.pushButton_rate_up.setIcon(qta.icon('mdi6.speedometer', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_rate_up.pressed.connect(self.increase_play_rate)
        self.ui.pushButton_help.setIcon(qta.icon('mdi6.help'))
        self.ui.pushButton_help.pressed.connect(self.help)
        self.ui.pushButton_find_code.setIcon(qta.icon('mdi6.card-search-outline', options=[{'scale-factor': 1.2}]))
        self.ui.pushButton_find_code.pressed.connect(self.find_code_in_tree)

        # The buttons in the splitter are smaller 24x24 pixels
        self.ui.pushButton_latest.setIcon(qta.icon('mdi6.arrow-collapse-right', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_latest.pressed.connect(self.go_to_latest_coded_file)
        self.ui.pushButton_next_file.setIcon(qta.icon('mdi6.arrow-right', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_next_file.pressed.connect(self.go_to_next_file)
        self.ui.pushButton_document_memo.setIcon(qta.icon('mdi6.text-box-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_document_memo.pressed.connect(self.active_file_memo)
        self.ui.pushButton_important.setIcon(qta.icon('mdi6.star-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_important.pressed.connect(self.show_important_coded)
        self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_file_attributes.pressed.connect(self.get_files_from_attributes)

        self.ui.pushButton_add_image_to_project.setIcon(qta.icon('mdi6.image-plus-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_add_image_to_project.pressed.connect(self.import_screenshot_into_project)
        self.ui.pushButton_add_image_to_project.setEnabled(False)
        self.ui.pushButton_screensshot.setIcon(qta.icon('mdi6.image-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_screensshot.pressed.connect(self.save_screenshot)
        self.ui.pushButton_screensshot.setEnabled(False)

        # Until any media is selected disable some widgets
        self.ui.pushButton_play.setEnabled(False)
        self.ui.pushButton_coding.setEnabled(False)
        self.ui.horizontalSlider.setEnabled(False)
        self.installEventFilter(self)  # for rewind, play/stop

        # Prepare textEdit for coding transcribed text
        self.ui.textEdit.setPlainText("")
        self.ui.textEdit.setAutoFillBackground(True)
        self.ui.textEdit.setToolTip("")
        self.ui.textEdit.setMouseTracking(True)
        #self.ui.textEdit.setReadOnly(True)
        self.ui.textEdit.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.eventFilterTT = ToolTipEventFilter()
        self.ui.textEdit.installEventFilter(self.eventFilterTT)
        self.ui.textEdit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.textEdit.customContextMenuRequested.connect(self.textedit_menu)
        self.ui.pushButton_segment_menu.pressed.connect(self.label_segment_menu)

        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        tree_font = f'font: {self.app.settings["treefontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.treeWidget.setStyleSheet(tree_font)
        doc_font = f'font: {self.app.settings["docfontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.textEdit.setStyleSheet(doc_font)
        self.ui.label_coder.setText(_("Coder: ") + self.app.settings['codername'])
        self.setWindowTitle(_("Media coding"))
        self.ui.listWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.listWidget.customContextMenuRequested.connect(self.file_menu)
        self.ui.listWidget.setStyleSheet(tree_font)
        self.ui.listWidget.selectionModel().selectionChanged.connect(self.file_selection_changed)

        self.ui.treeWidget.setDragEnabled(True)
        self.ui.treeWidget.setAcceptDrops(True)
        self.ui.treeWidget.setDragDropMode(QtWidgets.QAbstractItemView.DragDropMode.InternalMove)
        self.ui.treeWidget.viewport().installEventFilter(self)
        self.ui.treeWidget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.treeWidget.customContextMenuRequested.connect(self.tree_menu)
        self.ui.treeWidget.itemClicked.connect(self.assign_selected_text_to_code)
        self.get_files()
        self.fill_tree()
        # These signals after the tree is filled the first time
        self.ui.treeWidget.itemCollapsed.connect(self.get_collapsed)
        self.ui.treeWidget.itemExpanded.connect(self.get_collapsed)

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
        self.palette = self.ddialog.dframe.palette()
        self.palette.setColor(QtGui.QPalette.ColorRole.Window, QColor(30, 30, 30))
        self.ddialog.dframe.setPalette(self.palette)
        self.ddialog.dframe.setAutoFillBackground(True)
        self.ddialog.gridLayout.addWidget(self.ddialog.dframe, 0, 0, 0, 0)
        # Enable custom window hint - must be set to enable customizing window controls
        self.ddialog.setWindowFlags(self.ddialog.windowFlags() | QtCore.Qt.WindowType.CustomizeWindowHint)
        # Disable close button, only close through closing the Ui_Dialog_view_av
        self.ddialog.setWindowFlags(self.ddialog.windowFlags() & ~QtCore.Qt.WindowType.WindowCloseButtonHint)
        self.ddialog.setWindowFlags(self.ddialog.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        # Add context menu for ddialog
        self.ddialog.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ddialog.customContextMenuRequested.connect(self.ddialog_menu)

        # Create a vlc instance with an empty vlc media player
        # Fix an Ubuntu error but, makes no difference self.instance = vlc.Instance("--no-xlib")
        # Fedora 39: NameError: no function 'libvlc_new'
        try:
            self.instance = vlc.Instance()
        except NameError as name_err:
            logger.error(f"{name_err}")
            msg = f"{name_err}"
            Message(self.app, _("QualCoder will crash") + " " * 20, msg).exec()

        # Ubuntu 22.04 hide - self.ddialog.hide() as vlc is not inside dialog
        self.mediaplayer = self.instance.media_player_new()
        self.mediaplayer.video_set_mouse_input(False)
        self.mediaplayer.video_set_key_input(False)

        self.ui.horizontalSlider.setTickPosition(QtWidgets.QSlider.TickPosition.NoTicks)
        self.ui.horizontalSlider.setMouseTracking(True)
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
        self.ui.graphicsView.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.DefaultContextMenu)

    @staticmethod
    def help():
        """ Open help for transcribe section in browser. """

        url = "https://github.com/ccbogel/QualCoder/wiki/4.5.-Coding-Audio-and-Video"
        webbrowser.open(url)

    def find_code_in_tree(self):
        """ Find a code by name in the codes tree and select it.
        """

        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        dialog.setWindowTitle(_("Search for code"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        msg = _("Find and select first code that matches text.") + "\n"
        msg += _("Enter text to match all or partial code:")
        dialog.setLabelText(msg)
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        search_text = dialog.textValue()

        # Remove selections and search for matching item text
        self.ui.treeWidget.setCurrentItem(None)
        self.ui.treeWidget.clearSelection()
        item = None
        iterator = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        while iterator.value():
            item = iterator.value()
            if "cid" in item.text(1):
                cid = int(item.text(1)[4:])
                code_ = next((code_ for code_ in self.codes if code_['cid'] == cid), None)
                if search_text in code_['name']:
                    self.ui.treeWidget.setCurrentItem(item)
                    break
            iterator += 1
        if item is None:
            Message(self.app, _("Match not found"), _("No code with matching text found.")).exec()
            return
        # Expand parents
        parent = item.parent()
        while parent is not None:
            parent.setExpanded(True)
            parent = parent.parent()

    def ddialog_menu(self, position):
        """ Context menu to export a screenshot, to resize dialog. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_screenshot = menu.addAction(_("Screenshot"))
        action_resize = menu.addAction(_("Resize"))

        action = menu.exec(self.ddialog.mapToGlobal(position))
        if action == action_screenshot:
            time.sleep(0.5)
            screen = QtWidgets.QApplication.primaryScreen()
            screenshot = screen.grabWindow(self.ddialog.winId())
            screenshot.save(self.app.settings['directory'] + '/Frame_' + datetime.datetime.now().astimezone().strftime(
                "%Y%m%d_%H_%M_%S") + '.jpg', 'jpg')
        if action == action_resize:
            w = self.ddialog.size().width()
            h = self.ddialog.size().height()
            res_w = QtWidgets.QInputDialog.getInt(self, _("Width"), _("Width:"), w, 100, 2000, 5)
            if res_w[1]:
                w = res_w[0]
            res_h = QtWidgets.QInputDialog.getInt(self, _("Height"), _("Height:"), h, 80, 2000, 5)
            if res_h[1]:
                h = res_h[0]
            self.ddialog.resize(w, h)

    def get_codes_and_categories(self):
        """ Called from init, delete category/code, event_filter. """

        self.codes, self.categories = self.app.get_codes_categories()

    def get_recent_codes(self):
        """ Get recently used codes. Must have loaded all codes first.
        recent codes are stored as space delimited text in project table.
        Add code id to recent codes list, if code is present. """

        self.recent_codes = []
        cur = self.app.conn.cursor()
        cur.execute("select recently_used_codes from project")
        res = cur.fetchone()
        if not res:
            return
        if res[0] == "" or res[0] is None:
            return
        recent_codes_text = res[0].split()
        for code_id in recent_codes_text:
            try:
                cid = int(code_id)
                for code_ in self.codes:
                    if cid == code_['cid']:
                        self.recent_codes.append(code_)
            except ValueError:
                pass

    def get_files(self, ids=None):
        """ Get AV files and exclude those with bad links.
        Fill list widget with file names.
        param:
            ids : list of Integer ids to restrict files """

        if ids is None:
            ids = []
        bad_links = self.app.check_bad_file_links()
        bl_sql = ""
        for bl in bad_links:
            bl_sql += f",{bl['id']}"
        if len(bl_sql) > 0:
            bl_sql = f" and id not in ({bl_sql[1:]}) "
        self.files = []
        cur = self.app.conn.cursor()
        sql = "select name, id, ifnull(memo,''), owner, date, mediapath, av_text_id from source where "
        sql += "substr(mediapath,1,6) in ('/audio','/video', 'audio:', 'video:') " + bl_sql + " "
        if ids:
            str_ids = list(map(str, ids))
            sql += " and id in (" + ",".join(str_ids) + ")"
        sql += " order by name"
        cur.execute(sql)
        result = cur.fetchall()
        self.files = []
        keys = 'name', 'id', 'memo', 'owner', 'date', 'mediapath', 'av_text_id'
        for row in result:
            self.files.append(dict(zip(keys, row)))

        self.ui.listWidget.clear()
        for f in self.files:
            item = QtWidgets.QListWidgetItem(f['name'])
            item.setToolTip(f['memo'])
            self.ui.listWidget.addItem(item)
        self.clear_file()

    def get_files_from_attributes(self):
        """ Select files based on attribute selections.
        Attribute results are a dictionary of:
        first item is a Boolean AND or OR list item
        Followed by each attribute list item
        """

        # Clear ui
        self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
        ui = DialogSelectAttributeParameters(self.app)
        ui.fill_parameters(self.attributes)
        temp_attributes = deepcopy(self.attributes)
        self.attributes = []
        ok = ui.exec()
        if not ok:
            self.attributes = temp_attributes
            self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable'))
            self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
            if self.attributes:
                self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable-box'))
            return
        self.attributes = ui.parameters
        if len(self.attributes) == 1:
            self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable'))
            self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
            self.get_files()
            return
        if not ui.result_file_ids:
            Message(self.app, _("Nothing found") + " " * 20, _("No matching files found")).exec()
            self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable'))
            self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
            return
        self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable-box'))
        self.ui.pushButton_file_attributes.setToolTip(ui.tooltip_msg)
        self.get_files(ui.result_file_ids)

    def show_important_coded(self):
        """ Show codes flagged as important.
         Hide the remaining coded text and segments. """

        if self.media is None:
            return
        self.important = not self.important
        if self.important:
            self.ui.pushButton_important.setToolTip(_("Showing important codings"))
            self.ui.pushButton_important.setIcon(qta.icon('mdi6.star'))
        else:
            self.ui.pushButton_important.setToolTip(_("Show codings flagged important"))
            self.ui.pushButton_important.setIcon(qta.icon('mdi6.star-outline'))
        self.get_coded_text_update_eventfilter_tooltips()

        # Draw coded segments in scene
        scaler = self.scene_width / self.media.get_duration()
        self.scene.clear()
        for s in self.segments:
            if not self.important:
                self.scene.addItem(SegmentGraphicsItem(self.app, s, scaler, self))
            if self.important and s['important'] == 1:
                self.scene.addItem(SegmentGraphicsItem(self.app, s, scaler, self))
        # Set the scene to the top
        self.ui.graphicsView.verticalScrollBar().setValue(0)

    def assign_selected_text_to_code(self):
        """ Assign selected text on left-click on code in tree. """

        current = self.ui.treeWidget.currentItem()
        if current.text(1)[0:3] == 'cat':
            return
        selected_text = self.ui.textEdit.textCursor().selectedText()
        if len(selected_text) > 0:
            self.mark()

    def fill_tree(self):
        """ Fill tree widget, tope level items are main categories and unlinked codes. """

        cats = deepcopy(self.categories)
        codes = deepcopy(self.codes)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(4)
        self.ui.treeWidget.setHeaderLabels([_("Name"), _("Id"), _("Memo"), _("Count")])
        if not self.app.settings['showids']:
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
                if c['memo'] != "":
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], f"catid:{c['catid']}", memo])
                top_item.setToolTip(0, c['name'])
                if len(c['name']) > 52:
                    top_item.setText(0, c['name'][:25] + '..' + c['name'][-25:])
                    top_item.setToolTip(0, c['name'])
                top_item.setToolTip(2, c['memo'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                if f"catid:{c['catid']}" in self.app.collapsed_categories:
                    top_item.setExpanded(False)
                else:
                    top_item.setExpanded(True)
                remove_list.append(c)
        for item in remove_list:
            cats.remove(item)

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
                    if item.text(1) == f"catid:{c['supercatid']}":
                        memo = ""
                        if c['memo'] != "":
                            memo = "Memo"
                        child = QtWidgets.QTreeWidgetItem([c['name'], f"catid:{c['catid']}", memo])
                        child.setToolTip(0, c['name'])
                        if len(c['name']) > 52:
                            child.setText(0, c['name'][:25] + '..' + c['name'][-25:])
                            child.setToolTip(0, c['name'])
                        child.setToolTip(2, c['memo'])
                        item.addChild(child)
                        if f"catid:{c['catid']}" in self.app.collapsed_categories:
                            child.setExpanded(False)
                        else:
                            child.setExpanded(True)
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
                if c['memo'] != "":
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], f"cid:{c['cid']}", memo])
                top_item.setToolTip(0, c['name'])
                if len(c['name']) > 52:
                    top_item.setText(0, c['name'][:25] + '..' + c['name'][-25:])
                    top_item.setToolTip(0, c['name'])
                top_item.setToolTip(2, c['memo'])
                top_item.setBackground(0, QBrush(QColor(c['color']), Qt.BrushStyle.SolidPattern))
                color = TextColor(c['color']).recommendation
                top_item.setForeground(0, QBrush(QColor(color)))
                top_item.setFlags(
                    Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable |
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
                if item.text(1) == f"catid:{c['catid']}":
                    memo = ""
                    if c['memo'] != "":
                        memo = _("Memo")
                    child = QtWidgets.QTreeWidgetItem([c['name'], f"cid:{c['cid']}", memo])
                    child.setBackground(0, QBrush(QColor(c['color']), Qt.BrushStyle.SolidPattern))
                    color = TextColor(c['color']).recommendation
                    child.setForeground(0, QBrush(QColor(color)))
                    child.setToolTip(0, c['name'])
                    if len(c['name']) > 52:
                        child.setText(0, c['name'][:25] + '..' + c['name'][-25:])
                        child.setToolTip(0, c['name'])
                    child.setToolTip(2, c['memo'])
                    child.setFlags(
                        Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable |
                        Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled)
                    item.addChild(child)
                    c['catid'] = -1  # Make unmatchable
                it += 1
                item = it.value()
                count += 1
        # self.ui.treeWidget.expandAll()
        if self.tree_sort_option == "all asc":
            self.ui.treeWidget.sortByColumn(0, QtCore.Qt.SortOrder.AscendingOrder)
        if self.tree_sort_option == "all desc":
            self.ui.treeWidget.sortByColumn(0, QtCore.Qt.SortOrder.DescendingOrder)
        self.fill_code_counts_in_tree()

    def fill_code_counts_in_tree(self):
        """ Count instances of each code for current coder and in the selected file.
        Called by fill_tree """

        if self.file_ is None:
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
                cur.execute(sql, [cid, self.file_['id'], self.app.settings['codername']])
                result_av = cur.fetchone()
                result_txt = [0]
                try:  # May not have a text file
                    cur.execute(sql_txt, [cid, self.transcription[0], self.app.settings['codername']])
                    result_txt = cur.fetchone()
                except Exception as e_:
                    print(e_)
                    logger.warning(str(e_))
                result = result_av[0] + result_txt[0]
                if result > 0:
                    item.setText(3, str(result))
                else:
                    item.setText(3, "")
            it += 1
            item = it.value()
            count += 1

    def get_collapsed(self, item):
        """ On category collapse or expansion signal, find the collapsed parent category items.
        This will fill the self.app.collapsed_categories and is the expanded/collapsed tree is then replicated across
        other areas of the app. """

        #print(item.text(0), item.text(1), "Expanded:", item.isExpanded())
        if item.text(1)[:3] == "cid":
            return
        if not item.isExpanded() and item.text(1) not in self.app.collapsed_categories:
            self.app.collapsed_categories.append(item.text(1))
        if item.isExpanded() and item.text(1) in self.app.collapsed_categories:
            self.app.collapsed_categories.remove(item.text(1))

    def file_menu(self, position):
        """ Context menu to select the next image alphabetically, or
         to select the image that was most recently coded """

        if len(self.files) == 0:
            return
        selected = self.ui.listWidget.currentItem()
        file_ = None
        for f in self.files:
            if selected.text() == f['name']:
                file_ = f
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        memo_action = menu.addAction(_("Open memo"))
        action_next = menu.addAction(_("Next file"))
        action_latest = menu.addAction(_("File with latest coding"))
        action_show_files_like = menu.addAction(_("Show files like"))
        action_show_case_files = menu.addAction(_("Show case files"))
        action_show_by_attribute = menu.addAction(_("Show files by attributes"))
        action = menu.exec(self.ui.listWidget.mapToGlobal(position))
        if action is None:
            return
        if action == memo_action:
            self.file_memo(file_)
        if action == action_next:
            if self.file_ is None:
                self.file_ = self.files[0]
                self.load_media()
                self.load_segments()
                self.fill_code_counts_in_tree()
                return
            for i in range(0, len(self.files) - 1):
                if self.file_ == self.files[i]:
                    found = self.files[i + 1]
                    self.file_ = found
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
                    self.file_ = f
                    self.load_media()
                    self.load_segments()
                    self.fill_code_counts_in_tree()
                    return
        if action == action_show_files_like:
            self.show_files_like()
        if action == action_show_case_files:
            self.show_case_files()
        if action == action_show_by_attribute:
            self.get_files_from_attributes()

    def show_case_files(self):
        """ Show files of specified case.
        Or show all files. """

        cases = self.app.get_casenames()
        cases.insert(0, {"name": _("Show all files"), "id": -1})
        ui = DialogSelectItems(self.app, cases, _("Select case"), "single")
        ok = ui.exec()
        if not ok:
            return
        selection = ui.get_selected()
        if not selection:
            return
        if selection['id'] == -1:
            self.get_files()
            return
        cur = self.app.conn.cursor()
        cur.execute('select fid from case_text where caseid=?', [selection['id']])
        res = cur.fetchall()
        file_ids = [r[0] for r in res]
        '''for r in res:
            file_ids.append(r[0])'''
        self.get_files(file_ids)

    def show_files_like(self):
        """ Show files that contain specified filename text.
        If blank, show all files. """

        dialog = QtWidgets.QInputDialog(self)
        dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        dialog.setWindowTitle(_("Show files like"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog.setLabelText(_("Show files containing the text. (Blank for all)"))
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        text_ = str(dialog.textValue())
        if text_ == "":
            self.get_files()
            return
        cur = self.app.conn.cursor()
        cur.execute('select id from source where name like ?', ['%' + text_ + '%'])
        res = cur.fetchall()
        file_ids = [r[0] for r in res]
        self.get_files(file_ids)

    def active_file_memo(self):
        """ Send active file to file_memo method.
        Called by pushButton_document_memo for loaded text.
        """

        self.file_memo(self.file_)

    def file_memo(self, file_):
        """ Open file memo to view or edit.
        Called by pushButton_document_memo for loaded text, via active_file_memo
        and through file_menu for any file.
        param: file_ : Dictionary of file values
        """

        if file_ is None:
            return
        ui = DialogMemo(self.app, _("Memo for file: ") + file_['name'], file_['memo'])
        ui.exec()
        memo = ui.memo
        if memo == file_['memo']:
            return
        file_['memo'] = memo
        cur = self.app.conn.cursor()
        cur.execute("update source set memo=? where id=?", (memo, file_['id']))
        self.app.conn.commit()
        self.get_files()
        self.app.delete_backup = False

    def go_to_latest_coded_file(self):
        """ Vertical splitter button activates this """

        sql = "SELECT id FROM code_av where owner=? order by date desc limit 1"
        cur = self.app.conn.cursor()
        cur.execute(sql, [self.app.settings['codername'], ])
        result = cur.fetchone()
        if result is None:
            return
        for i, f in enumerate(self.files):
            if f['id'] == result[0]:
                self.file_ = f
                self.ui.listWidget.setCurrentRow(i)
                self.load_media()
                break

    def go_to_next_file(self):
        """ Vertical splitter button activates this.
         Assumes one or more items in the list widget.
         As the coding dialog will not open with no AV files. """

        if self.file_ is None:
            self.file_ = self.files[0]
            self.load_media()
            self.ui.listWidget.setCurrentRow(0)
            return
        for i in range(0, len(self.files) - 1):
            if self.file_ == self.files[i]:
                found = self.files[i + 1]
                self.file_ = found
                self.ui.listWidget.setCurrentRow(i + 1)
                self.load_media()
                return

    def file_selection_changed(self):
        """ Listwidget file name selected so fill current file variable and load. """

        if len(self.files) == 0:
            return
        itemname = self.ui.listWidget.currentItem().text()
        for f in self.files:
            if f['name'] == itemname:
                self.file_ = f
                self.load_media()
                self.load_segments()
                self.fill_code_counts_in_tree()
                break

    def load_segments(self):
        """ Get coded segments for this file and for this coder.
        Called from select_media. """

        if self.file_ is None:
            return
        # 10 is assigned as an initial default for y values for segments
        sql = "select avid, id, pos0, pos1, code_av.cid, ifnull(code_av.memo,''), code_av.date, "
        sql += " code_av.owner, code_name.name, code_name.color, 10, code_av.important from code_av"
        sql += " join code_name on code_name.cid=code_av.cid"
        sql += " where id=? "
        sql += " and code_av.owner=? "
        sql += " order by pos0, pos1"
        values = [self.file_['id'], self.app.settings['codername']]
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
                if (self.segments[i]['pos0'] <= self.segments[j]['pos0'] <= self.segments[i]['pos1'] and
                    self.segments[i]['y'] == self.segments[j]['y']) or \
                        (self.segments[j]['pos0'] <= self.segments[i]['pos0'] <= self.segments[j]['pos1'] and
                         self.segments[i]['y'] == self.segments[j]['y']):
                    # to overcome the overlap, add to the y value of the i segment
                    self.segments[j]['y'] += 10
        # Add seltext, the text link to the segment
        sql = "select seltext from code_text where avid=?"
        for s in self.segments:
            # Use this name with label_segment context menu
            s['name'] = f"{msecs_to_hours_mins_secs(s['pos0'])}-{msecs_to_hours_mins_secs(s['pos1'])}: {s['codename']}"
            cur.execute(sql, [s['avid']])
            res = cur.fetchall()
            txt = ""
            for r in res:
                txt += str(r[0]) + "\n"
            s['seltext'] = txt
        # Draw coded segments in scene
        scaler = self.scene_width / self.media.get_duration()
        self.scene.clear()
        for s in self.segments:
            self.scene.addItem(SegmentGraphicsItem(self.app, s, scaler, self))
        # Set te scene to the top
        self.ui.graphicsView.verticalScrollBar().setValue(0)

    def clear_file(self):
        """ When AV file removed clear all details.
        Called by null file with load_media, ManageFiles.delete, get_files """

        self.stop()
        self.media = None
        self.file_ = None
        self.setWindowTitle(_("Media coding"))
        self.ui.pushButton_play.setEnabled(False)
        self.ui.horizontalSlider.setEnabled(False)
        self.ui.pushButton_coding.setEnabled(False)
        self.ui.textEdit.clear()
        self.transcription = None
        # None on init
        if self.ddialog is not None:
            self.ui.pushButton_add_image_to_project.setEnabled(False)
            self.ui.pushButton_screensshot.setEnabled(False)
            self.ddialog.hide()

    def load_media(self):
        """ Add media to media dialog. """

        try:
            if self.file_['mediapath'][0:6] in ('/audio', '/video'):
                self.media = self.instance.media_new(self.app.project_path + self.file_['mediapath'])
            if self.file_['mediapath'][0:6] in ('audio:', 'video:'):
                self.media = self.instance.media_new(self.file_['mediapath'][6:])
        except Exception as e_:
            Message(self.app, _('Media not found'), str(e_) + "\n" + self.app.project_path + self.file_['mediapath'],
                    "warning").exec()
            self.clear_file()
            return

        title = self.file_['name'].split('/')[-1]
        self.ddialog.setWindowTitle(title)
        self.setWindowTitle(_("Media coding: ") + title)
        self.ui.pushButton_play.setEnabled(True)
        self.ui.horizontalSlider.setEnabled(True)
        self.ui.pushButton_coding.setEnabled(True)
        if self.file_['mediapath'][0:6] not in ("/audio", "audio:"):
            self.ddialog.show()
            self.ui.pushButton_add_image_to_project.setEnabled(True)
            self.ui.pushButton_screensshot.setEnabled(True)
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
            self.ui.pushButton_add_image_to_project.setEnabled(False)
            self.ui.pushButton_screensshot.setEnabled(False)

        # Clear comboBox tracks options and reload when playing/pausing
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
        # Get the transcription text
        self.transcription = None
        cur = self.app.conn.cursor()
        if self.file_['av_text_id'] is not None:
            cur.execute("select id, fulltext, name from source where id=?", [self.file_['av_text_id']])
            self.transcription = cur.fetchone()
        if self.transcription is None:
            # Create or re-link to the transcription text
            # Check if an existing matching text entry name is present, despite no linkage to the av source
            name = self.file_['name'] + ".txt"
            name2 = self.file_['name'] + ".transcribed"
            cur.execute("select id from source where name=? or name=?", [name, name2])
            existing_name_res = cur.fetchone()
            tr_id = None
            if existing_name_res is not None:
                cur.execute("update source set av_text_id=? where id=?", [existing_name_res[0], self.file_['id']])
                self.app.conn.commit()
                tr_id = existing_name_res[0]
            if existing_name_res is None:
                # Create a blank transcription file
                entry = {'name': self.file_['name'] + ".txt", 'id': -1, 'fulltext': "", 'mediapath': None, 'memo': "",
                         'owner': self.app.settings['codername'],
                         'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                cur.execute("insert into source(name,fulltext,mediapath,memo,owner,date) values(?,?,?,?,?,?)",
                            (entry['name'], entry['fulltext'], entry['mediapath'], entry['memo'], entry['owner'],
                             entry['date']))
                self.app.conn.commit()
                cur.execute("select last_insert_rowid()")
                tr_id = cur.fetchone()[0]
            # Create link from av entry to existing or new text entry
            self.file_['av_text_id'] = tr_id
            cur.execute("update source set av_text_id=? where id=?", [tr_id, self.file_['id']])
            self.app.conn.commit()
            cur.execute("select id, fulltext, name from source where id=?", [tr_id])
            self.transcription = cur.fetchone()
            '''print("transcription", self.transcription)
            if self.transcription is None:
                print("tr_id", tr_id)'''
        self.ui.textEdit.setText(self.transcription[1])
        self.ui.textEdit.ensureCursorVisible()
        self.get_timestamps_from_transcription()

        # Get text annotations
        cur = self.app.conn.cursor()
        cur.execute(
            "select anid, fid, pos0, pos1, ifnull(memo,''), owner, date from annotation where owner=? and fid=?",
            [self.app.settings['codername'], self.transcription[0]])
        result = cur.fetchall()
        keys = 'anid', 'fid', 'pos0', 'pos1', 'memo', 'owner', 'date'
        for row in result:
            self.annotations.append(dict(zip(keys, row)))
        self.get_coded_text_update_eventfilter_tooltips()

    def get_coded_text_update_eventfilter_tooltips(self):
        """ Called by load_media, update_dialog_codes_and_categories,
        Segment_Graphics_Item.link_text_to_segment.
        """

        if self.transcription is None:
            return
        # Get code text for this file and for this coder
        values = [self.transcription[0], self.app.settings['codername']]
        cur = self.app.conn.cursor()
        self.code_text = []
        # seltext length, longest first, so overlapping shorter text is superimposed.
        sql = "select code_text.cid, code_text.fid, seltext, code_text.pos0, code_text.pos1, "
        sql += "code_text.owner, code_text.date, ifnull(code_text.memo,''), code_text.avid,code_av.pos0, code_av.pos1, "
        sql += "code_text.important, code_text.ctid "
        sql += "from code_text left join code_av on code_text.avid = code_av.avid "
        sql += " where code_text.fid=? and code_text.owner=? order by length(seltext) desc"
        cur.execute(sql, values)
        code_results = cur.fetchall()
        keys = 'cid', 'fid', 'seltext', 'pos0', 'pos1', 'owner', 'date', 'memo', 'avid', 'av_pos0', 'av_pos1', \
            'important', 'ctid'
        for row in code_results:
            self.code_text.append(dict(zip(keys, row)))
        # Update filter for tooltip and redo formatting
        if self.important:
            imp_coded = []
            for c in self.code_text:
                if c['important'] == 1:
                    imp_coded.append(c)
            self.eventFilterTT.set_codes_and_annotations(self.app, imp_coded, self.codes, self.annotations)
        else:
            self.eventFilterTT.set_codes_and_annotations(self.app, self.code_text, self.codes, self.annotations)
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

        mmss1 = r"\[[0-9]?[0-9]:[0-9][0-9]\]"
        hhmmss1 = r"\[[0-9][0-9]:[0-9][0-9]:[0-9][0-9]\]"
        mmss2 = r"\[[0-9]?[0-9]\.[0-9][0-9]\]"
        hhmmss2 = r"\[[0-9][0-9]\.[0-9][0-9]\.[0-9][0-9]\]"
        hhmmss3 = r"\{[0-9][0-9]\:[0-9][0-9]\:[0-9][0-9]\}"
        hhmmss_sss = r"#[0-9][0-9]:[0-9][0-9]:[0-9][0-9]\.[0-9]{1,3}#"  # allow for 1 to 3 msecs digits
        srt = r"[0-9][0-9]:[0-9][0-9]:[0-9][0-9],[0-9][0-9][0-9]\s-->\s[0-9][0-9]:[0-9][0-9]:[0-9][0-9],[0-9][0-9][0-9]"

        self.time_positions = []
        for match in re.finditer(mmss1, self.transcription[1]):
            stamp = match.group()[1:-1]
            s = stamp.split(':')
            try:
                msecs = (int(s[0]) * 60 + int(s[1])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except IndexError:
                pass
        for match in re.finditer(hhmmss1, self.transcription[1]):
            stamp = match.group()[1:-1]
            s = stamp.split(':')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s[2])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except IndexError:
                pass
        for match in re.finditer(mmss2, self.transcription[1]):
            stamp = match.group()[1:-1]
            s = stamp.split('.')
            try:
                msecs = (int(s[0]) * 60 + int(s[1])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except IndexError:
                pass
        for match in re.finditer(hhmmss2, self.transcription[1]):
            stamp = match.group()[1:-1]
            s = stamp.split('.')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s[2])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except IndexError:
                pass
        for match in re.finditer(hhmmss3, self.transcription[1]):
            stamp = match.group()[1:-1]
            s = stamp.split('.')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s[2])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except IndexError:
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
            except IndexError:
                pass
        for match in re.finditer(srt, self.transcription[1]):
            # Format 09:33:04,100 --> 09:33:09,600  skip the arrow and second time position
            stamp = match.group()[0:12]
            s = stamp.split(':')
            s2 = s[2].split(',')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s2[0])) * 1000 + int(s2[1])
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except IndexError:
                pass

    def set_position(self):
        """ Set the movie position according to the position slider.
        The vlc MediaPlayer needs a float value between 0 and 1, Qt uses
        integer variables, so you need a factor; the higher the factor, the
        more precise are the results (1000 should suffice).
        """

        self.ui.horizontalSlider.blockSignals(True)
        pos = self.ui.horizontalSlider.value()
        msecs = self.mediaplayer.get_time()
        self.mediaplayer.set_position(pos / 1000.0)

        '''  # This code may not be needed - blockSignals seems to fix a problem where msecs returns -1
        counter = 0
        while pos > 0 and msecs == -1 and counter < 10000:
            self.mediaplayer.set_position(pos / 1000.0)
            msecs = self.mediaplayer.get_time()
            counter += 1
            #print("slider pos", pos, pos/1000.0 , "msecs", msecs, "counter", counter)'''

        self.ui.label_time.setText(msecs_to_hours_mins_secs(msecs) + self.media_duration_text)
        self.ui.horizontalSlider.blockSignals(False)

    def play_pause(self):
        """ Toggle play or pause status. """

        # user might update window positions and sizes, need to detect it
        self.update_sizes()
        if self.mediaplayer.is_playing():
            self.mediaplayer.pause()
            self.ui.pushButton_play.setIcon(qta.icon('mdi6.play', options=[{'scale_factor': 1.4}]))
            self.is_paused = True
            self.timer.stop()
        else:
            if self.mediaplayer.play() == -1:
                return

            # On play rewind 100 msecs
            time_msecs = self.mediaplayer.get_time() - 100
            if time_msecs < 0:
                time_msecs = 0
            pos = time_msecs / self.mediaplayer.get_media().get_duration()
            self.mediaplayer.set_position(pos)
            # Update timer display
            msecs = self.mediaplayer.get_time()
            self.ui.label_time.setText(msecs_to_hours_mins_secs(msecs) + self.media_duration_text)
            self.mediaplayer.play()
            self.ui.pushButton_play.setIcon(qta.icon('mdi6.pause'))
            self.timer.start()
            self.is_paused = False
            self.play_segment_end = None

    def stop(self):
        """ Stop vlc player. Set position slider to the start.
         If multiple audio tracks are shown in the combobox, set the audio track to the first index.
         This is because when beginning play again, the audio track reverts to the first track.
         Programming setting the audio track to other values does not work."""

        # Occurs on init , get_files
        if self.mediaplayer is None:
            return
        self.mediaplayer.stop()
        self.ui.pushButton_play.setIcon(qta.icon('mdi6.play', options=[{'scale_factor': 1.4}]))
        self.timer.stop()
        self.ui.horizontalSlider.setProperty("value", 0)
        self.play_segment_end = None

        # set combobox display of audio track to the first one, or leave it blank if it contains no items
        if self.ui.comboBox_tracks.count() > 0:
            self.ui.comboBox_tracks.setCurrentIndex(0)

    def set_volume(self, volume):
        """ Set the volume. """

        self.mediaplayer.audio_set_volume(volume)

    def audio_track_changed(self):
        """ Audio track changed.
        The video needs to be playing/paused before the combobox is filled with track options.
        The combobox only has positive integers."""

        txt = self.ui.comboBox_tracks.currentText()
        if txt == "":
            txt = 1
        success = self.mediaplayer.audio_set_track(int(txt))

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
        self.ui.label_time.setText(msecs_to_hours_mins_secs(msecs) + self.media_duration_text)

        # Check if segments need to be reloaded
        # This only updates if the media is playing, not ideal, but works
        for i in self.scene.items():
            if isinstance(i, SegmentGraphicsItem) and i.reload_segment is True:
                self.load_segments()

        """ For long transcripts, update the relevant text position in the textEdit to match the
        video's current position.
        time_position list item: [text_pos0, text_pos1, milliseconds]
        """
        if self.ui.checkBox_scroll_transcript.isChecked() and self.transcription is not None and \
                self.ui.textEdit.toPlainText() != "":
            for i in range(1, len(self.time_positions)):
                if self.time_positions[i - 1][2] < msecs < self.time_positions[i][2]:
                    text_pos = self.time_positions[i][0]
                    text_cursor = self.ui.textEdit.textCursor()
                    text_cursor.setPosition(text_pos)
                    self.ui.textEdit.setTextCursor(text_cursor)

        # No need to call this function if nothing is played
        if not self.mediaplayer.is_playing():
            self.timer.stop()
            self.ui.pushButton_play.setIcon(qta.icon('mdi6.play', options=[{'scale_factor': 1.4}]))
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

        self.update_sizes()
        self.ddialog.close()
        self.stop()

    def update_sizes(self):
        """ Called by splitter resizes and play/pause """

        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogcodeav_splitter0'] = sizes[0]
        self.app.settings['dialogcodeav_splitter1'] = sizes[2]  # as 30 is for size[1] for the buttons
        sizes = self.ui.splitter_2.sizes()
        self.app.settings['dialogcodeav_splitter_h0'] = sizes[0]
        self.app.settings['dialogcodeav_splitter_h1'] = sizes[1]
        if self.file_ is not None and self.file_['mediapath'] is not None \
                and self.file_['mediapath'][0:7] != "/audio/" \
                and self.file_['mediapath'][0:6] != "audio:":
            size = self.ddialog.size()
            if size.width() > 100:
                self.app.settings['video_w'] = size.width()
            else:
                self.app.settings['video_w'] = 100
            if size.height() > 80:
                self.app.settings['video_h'] = size.height()
            else:
                self.app.settings['video_h'] = 80

    def create_or_clear_segment(self):
        """ Make the start and end points of the segment duration.
        Use milliseconds formats for the times.
        Can also clear the segment by pressing the button when it says Clear segment.
        QButton text is changed to Start segment once a segment is assigned to a code.
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
            if self.segment['start_msecs'] > self.segment['end_msecs']:
                tmp = self.segment['start']
                tmp_msecs = self.segment['start_msecs']
                self.segment['start'] = self.segment['end']
                self.segment['start_msecs'] = self.segment['end_msecs']
                self.segment['end'] = tmp
                self.segment['end_msecs'] = tmp_msecs
            txt = _("Segment: ") + str(self.segment['start']) + " - " + self.segment['end']
            self.ui.label_segment.setText(txt)

    def tree_menu(self, position):
        """ Context menu for treeWidget items.
        Add, rename, memo, move or delete code or category. Change code color. """

        # selected_text = self.ui.textEdit.textCursor().selectedText()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        selected = self.ui.treeWidget.currentItem()
        action_color = None
        action_assign_segment = None
        action_show_coded_media = None
        action_move_code = None
        if self.segment['end_msecs'] is not None and self.segment['start_msecs'] is not None:
            action_assign_segment = menu.addAction("Assign segment to code")
        action_add_code_to_category = None
        action_add_category_to_category = None
        action_merge_category = None
        if selected is not None and selected.text(1)[0:3] == 'cat':
            action_add_code_to_category = menu.addAction(_("Add new code to category"))
            action_add_category_to_category = menu.addAction(_("Add a new category to category"))
            action_merge_category = menu.addAction(_("Merge category into category"))
        action_add_code = menu.addAction(_("Add a new code"))
        action_add_category = menu.addAction(_("Add a new category"))
        action_rename = menu.addAction(_("Rename"))
        action_edit_memo = menu.addAction(_("View or edit memo"))
        action_delete = menu.addAction(_("Delete"))
        if selected is not None and selected.text(1)[0:3] == 'cid':
            action_color = menu.addAction(_("Change code color"))
            action_move_code = menu.addAction(_("Move code to"))
            action_show_coded_media = menu.addAction(_("Show coded text and media"))
        action_show_codes_like = menu.addAction(_("Show codes like"))
        action_show_codes_of_colour = menu.addAction(_("Show codes of colour"))
        action_all_asc = menu.addAction(_("Sort ascending"))
        action_all_desc = menu.addAction(_("Sort descending"))
        action_cat_then_code_asc = menu.addAction(_("Sort category then code ascending"))
        action = menu.exec(self.ui.treeWidget.mapToGlobal(position))
        if action is None:
            return
        if action == action_show_codes_of_colour:
            self.show_codes_of_color()
            return
        if action == action_all_asc:
            self.tree_sort_option = "all asc"
            self.fill_tree()
            return
        if action == action_all_desc:
            self.tree_sort_option = "all desc"
            self.fill_tree()
            return
        if action == action_cat_then_code_asc:
            self.tree_sort_option = "cat and code asc"
            self.fill_tree()
            return
        if action == action_show_codes_like:
            self.show_codes_like()
            return
        if selected is not None and selected.text(1)[0:3] == 'cid' and action == action_color:
            self.change_code_color(selected)
        if selected is not None and action == action_move_code:
            self.move_code(selected)
        if action == action_add_category_to_category:
            catid = int(selected.text(1).split(":")[1])
            self.add_category(catid)
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
        if selected is not None and action == action_rename:
            self.rename_category_or_code(selected)
        if selected is not None and action == action_edit_memo:
            self.add_edit_code_memo(selected)
        if selected is not None and action == action_delete:
            self.delete_category_or_code(selected)
        if action == action_assign_segment:
            self.assign_segment_to_code(selected)
        if selected is not None and action == action_show_coded_media:
            found = None
            to_find = int(selected.text(1)[4:])
            for code in self.codes:
                if code['cid'] == to_find:
                    found = code
                    break
            if found:
                self.coded_media_dialog(found)

    def coded_media_dialog(self, code_dict):
        """ Display all coded media for this code, in a separate modal dialog.
        Coded media comes from ALL files for this coder.
        Need to store textedit start and end positions so that code in 000000000000 can be used.
        Called from tree_menu.
        Re-load the codings may have changed.
        param:
            code_dict : code dictionary
        """

        DialogCodeInAllFiles(self.app, code_dict)
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
        self.update_dialog_codes_and_categories()

    def show_codes_like(self):
        """ Show all codes if text is empty.
         Show selected codes that contain entered text. """

        # Input dialog narrow, so code below
        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        dialog.setWindowTitle(_("Show codes containing"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog.setLabelText(_("Show codes containing text.\n(Blank for all)"))
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        txt = str(dialog.textValue())
        root = self.ui.treeWidget.invisibleRootItem()
        self.recursive_traverse(root, txt)

    def show_codes_of_color(self):
        """ Show all codes in colour range in code tree., ir all codes if no selection.
        Show selected codes that are of a selected colour.
        """

        ui = DialogSelectItems(self.app, colour_ranges, _("Select code colors"), "single")
        ok = ui.exec()
        if not ok:
            return
        selected_color = ui.get_selected()
        show_codes_of_colour_range(self.app, self.ui.treeWidget, self.codes, selected_color)

    def recursive_traverse(self, item, txt):
        """ Find all children codes of this item that match or not and hide or unhide based on 'text'.
        Recurse through all child categories.
        Called by: show_codes_like
        param:
            item: a QTreeWidgetItem
            text:  Text string for matching with code names
        """

        child_count = item.childCount()
        for i in range(child_count):
            if "cid:" in item.child(i).text(1) and len(txt) > 0 and txt not in item.child(i).text(0):
                item.child(i).setHidden(True)
            if "cid:" in item.child(i).text(1) and txt == "":
                item.child(i).setHidden(False)
            self.recursive_traverse(item.child(i), txt)

    def update_dialog_codes_and_categories(self):
        """ Update code and category tree in DialogCodeImage, DialogCodeAV,
        DialogCodeText, DialogReportCodes.
        Not using isinstance for other classes as could not import the classes to test
        against. There was an import error.
        Using try except blocks for each instance, as instance may have been deleted. """

        self.get_codes_and_categories()
        self.fill_tree()
        self.load_segments()
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

    def keyPressEvent(self, event):
        """ This works best without the modifiers.
         As pressing Ctrl + E give the Ctrl but not the E.
         These key presses are not used in edi mode.

        A annotate - for current selection
        ON HOLD C - Save screenshot as png
        ON HOLD D - Save screenshot in project for image coding
        G Glue selected segment to selected code, and open segment memo
        Q Quick Mark with code - for current selection
        I Tag important
        L Show codes like
        M memo code - at clicked position
        O Shortcut to cycle through overlapping codes - at clicked position
        S search text - may include current selection
        R opens a context menu for recently used codes for marking text
        ! Shows cursor position in textEdit
        5 Jump forward 5 seconds

        Ctrl 0 to 9 Button presses
        Ctrl + Z restore last unmarked code(s) - text code(s) or segment code.
        Alt + minus rewind 30 seconds
        Ctrl + R to rewind 5 seconds.
        Alt + plus forward 30 seconds
        Ctrl + P to play/pause On start rewind 1 second
        Ctrl + D to play/pause On start rewind 1 second
        Ctrl + S to start and stop av segment creation
        Ctrl + Shift + > to increase play rate
        Ctrl + Shift + < to decrease play rate
        """

        key = event.key()
        mods = QtGui.QGuiApplication.keyboardModifiers()
        '''# Get screenshot and load in project for coding - D
        if key == QtCore.Qt.Key.Key_D and not self.ddialog.isHidden():
            self.import_screenshot_into_project()
            return
        # Save screenshot png - C
        if key == QtCore.Qt.Key.Key_C and not (self.ddialog.isHidden() or self.mediaplayer.get_media() is None):
            self.save_screenshot()
            return'''
        # Glue segment to currently selected code and open segment memo
        if key == QtCore.Qt.Key.Key_G and self.segment['start_msecs'] is not None and \
            self.segment['end_msecs'] is not None and self.ui.treeWidget.currentItem() is not None \
                and self.ui.treeWidget.currentItem().text(1)[0:3] == 'cid':
            ui = DialogMemo(self.app, _("Memo for Segment"), "")
            ui.exec()
            self.segment['memo'] = ui.memo
            self.assign_segment_to_code(self.ui.treeWidget.currentItem())
            return
        # Forward 5 seconds
        if key == QtCore.Qt.Key.Key_5:
            self.forward_5_seconds()
            return
        # Increase play rate  Ctrl + Shift + >
        if key == QtCore.Qt.Key.Key_Greater and (mods and QtCore.Qt.KeyboardModifier.ShiftModifier) and \
                (mods and QtCore.Qt.KeyboardModifier.ControlModifier):
            self.increase_play_rate()
            return
        # Decrease play rate  Ctrl + Shift + <
        if key == QtCore.Qt.Key.Key_Less and (mods and QtCore.Qt.KeyboardModifier.ShiftModifier) and \
                (mods and QtCore.Qt.KeyboardModifier.ControlModifier):
            self.decrease_play_rate()
            return
        # Advance 30 seconds Alt F
        if key == QtCore.Qt.Key.Key_Plus and mods & QtCore.Qt.KeyboardModifier.AltModifier:
            self.forward_30_seconds()
            return
        # Rewind 30 seconds Alt R
        if key == QtCore.Qt.Key.Key_Minus and mods == QtCore.Qt.KeyboardModifier.AltModifier:
            self.rewind_30_seconds()
            return
        # Ctrl 0 to 9
        if mods & QtCore.Qt.KeyboardModifier.ControlModifier:
            #  Ctrl + P pause/play toggle
            if key == QtCore.Qt.Key.Key_P or key == QtCore.Qt.Key.Key_D:
                self.play_pause()
                return
            #  Ctrl S to start and end A/V segment recording
            if key == QtCore.Qt.Key.Key_S:
                self.create_or_clear_segment()
                return
            # Rewind 5 seconds Ctrl R
            if key == QtCore.Qt.Key.Key_R:
                self.rewind_5_seconds()
                return
            if key == QtCore.Qt.Key.Key_1:
                self.go_to_next_file()
                return
            if key == QtCore.Qt.Key.Key_2:
                self.go_to_latest_coded_file()
                return
            if key == QtCore.Qt.Key.Key_3:
                self.file_memo(self.file_)
                return
            if key == QtCore.Qt.Key.Key_4:
                self.get_files_from_attributes()
                return
            if key == QtCore.Qt.Key.Key_5:
                self.show_important_coded()
                return
            if key == QtCore.Qt.Key.Key_9:
                self.show_important_coded()
                return
            if key == QtCore.Qt.Key.Key_0:
                self.help()
                return
            # Restore unmarked code(s) if undo code is present
            if key == QtCore.Qt.Key.Key_Z:
                if not self.undo_deleted_codes:
                    return
                try:
                    if self.undo_deleted_codes[0]['is_segment']:
                        self.restore_unmarked_segment()
                except KeyError:
                    self.restore_unmarked_text_codes()
        if not self.ui.textEdit.hasFocus():
            return
        '''# Ignore all other key events if edit mode is active  # Edit mode not used here yet
        if self.edit_mode:
            return'''
        cursor_pos = self.ui.textEdit.textCursor().position()
        selected_text = self.ui.textEdit.textCursor().selectedText()
        codes_here = []
        for item in self.code_text:
            if item['pos0'] <= cursor_pos <= item['pos1'] and \
                    item['owner'] == self.app.settings['codername']:
                codes_here.append(item)
        # Annotate selected
        if key == QtCore.Qt.Key.Key_A and selected_text != "":
            self.annotate(cursor_pos)
            return
        # Exclamation mark - show cursor position in textEdit
        if key == QtCore.Qt.Key.Key_Exclam:
            Message(self.app, _("Text position") + " " * 20, _("Character position: ") + str(cursor_pos)).exec()
            return
        # Important  for coded text
        if key == QtCore.Qt.Key.Key_I:
            self.set_important(cursor_pos)
            return
        # Show codes like
        if key == QtCore.Qt.Key.Key_L:
            self.show_codes_like()
        # Memo for current code
        if key == QtCore.Qt.Key.Key_M:
            self.coded_text_memo(cursor_pos)
            return
        # Overlapping codes cycle
        now = datetime.datetime.now()
        overlap_diff = now - self.overlap_timer
        if key == QtCore.Qt.Key.Key_O and overlap_diff.microseconds > 150000:
            self.overlap_timer = datetime.datetime.now()
            self.cycle_overlap()
            return
        # Quick mark selected
        if key == QtCore.Qt.Key.Key_Q and selected_text != "":
            self.mark()
            return
        # Recent codes context menu
        if key == QtCore.Qt.Key.Key_R and self.file_ is not None and self.ui.textEdit.textCursor().selectedText() != "":
            self.textedit_recent_codes_menu(self.ui.textEdit.cursorRect().topLeft())
            return

    def save_screenshot(self):
        hms = msecs_to_hours_mins_secs(self.mediaplayer.get_time())
        image_name = f"{self.file_['name']}_{hms}.png"
        filename = os.path.join(self.app.settings['directory'], image_name)
        self.mediaplayer.video_take_snapshot(0, filename, 1280, 720)
        Message(self.app, _("Screenshot saved"), filename).exec()
        self.parent_textEdit.append(_("Screenshot saved: ") + filename)

    def import_screenshot_into_project(self):

        hms = msecs_to_hours_mins_secs(self.mediaplayer.get_time())
        image_name = f"{self.file_['name']}_{hms}.png"
        file_path = os.path.join(self.app.project_path, "images", image_name)
        self.mediaplayer.video_take_snapshot(0, file_path, 1280, 720)
        entry = {'name': image_name, 'id': -1, 'fulltext': None,
                 'memo': self.file_['memo'], 'mediapath': f"/images/{image_name}",
                 'owner': self.app.settings['codername'],
                 'date': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 'av_text_id': None}
        cur = self.app.conn.cursor()
        cur.execute("insert into source(name,memo,owner,date, mediapath, fulltext) values(?,?,?,?,?,?)",
                    (
                        entry['name'], entry['memo'], entry['owner'], entry['date'], entry['mediapath'],
                        entry['fulltext']))
        self.app.conn.commit()
        Message(self.app, _("Screenshot imported"), file_path).exec()
        self.parent_textEdit.append(_("Screenshot imports: ") + image_name)

    def eventFilter(self, object_, event):
        """ Using this event filter to identify treeWidgetItem drop events.
        http://doc.qt.io/qt-5/qevent.html#Type-enum
        QEvent::Drop 63 A drag and drop operation is completed (QDropEvent).
        https://stackoverflow.com/questions/28994494/why-does-qtreeview-not-fire-a-drop-or-move-event-during-drag-and-drop

        Also use eventFilter for QGraphicsView.

        Also detect key events in the textedit. These are used to extend or shrink a text coding.
        Only works if clicked on a code (text cursor is in the coded text).
        Shrink start and end code positions using alt arrow left and alt arrow right
        Extend start and end code positions using shift arrow left, shift arrow right
        """

        '''if object == self.ui.graphicsView.viewport() and event.type() == event.Type.MousePress:  # event.Type.ContextMenu:
            #self.ui.graphicsView.contextMenuEvent(event)
            item = self.ui.graphicsView.itemAt(event.scenePos())
            if item is not None:
                print("HERE context menuy event")
                item.contextMenuEvent(event)
                #self.scene.sendEvent(item)
            return event.isAccepted()'''

        if object_ is self.ui.treeWidget.viewport():
            if event.type() == QtCore.QEvent.Type.Drop:
                item = self.ui.treeWidget.currentItem()
                # event position is QPointF, itemAt requires toPoint
                parent = self.ui.treeWidget.itemAt(event.position().toPoint())
                self.item_moved_update_data(item, parent)
        if event.type() != 7 or self.media is None:
            return False

        key = event.key()
        mod = event.modifiers()
        # Change start and end code positions using alt arrow left and alt arrow right
        # and shift arrow left, shift arrow right
        if self.ui.textEdit.hasFocus():
            cursor_pos = self.ui.textEdit.textCursor().position()
            codes_here = []
            for item in self.code_text:
                if item['pos0'] <= cursor_pos <= item['pos1'] and \
                        item['owner'] == self.app.settings['codername']:
                    codes_here.append(item)
            if len(codes_here) == 1:
                # Key event can be too sensitive, adjusted  for 100 millisecond gap
                msec_gap = 100000
                now = datetime.datetime.now()
                diff = now - self.code_resize_timer
                self.code_resize_timer = datetime.datetime.now()
                if key == QtCore.Qt.Key.Key_Left and mod == QtCore.Qt.KeyboardModifier.AltModifier \
                        and diff.microseconds > msec_gap:
                    self.shrink_to_left(codes_here[0])
                    return True
                if key == QtCore.Qt.Key.Key_Right and mod == QtCore.Qt.KeyboardModifier.AltModifier \
                        and diff.microseconds > msec_gap:
                    self.shrink_to_right(codes_here[0])
                    return True
                if key == QtCore.Qt.Key.Key_Left and mod == QtCore.Qt.KeyboardModifier.ShiftModifier \
                        and diff.microseconds > msec_gap:
                    self.extend_left(codes_here[0])
                    return True
                if key == QtCore.Qt.Key.Key_Right and mod == QtCore.Qt.KeyboardModifier.ShiftModifier \
                        and diff.microseconds > msec_gap:
                    self.extend_right(codes_here[0])
                    return True
        return False

    def textedit_recent_codes_menu(self, position):
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

    def recursive_set_current_item(self, item, text_):
        """ Set matching item to be the current selected item.
        Recurse through any child categories.
        Tried to use QTreeWidget.finditems - but this did not find matching item text
        Called by: textEdit recent codes menu option
        Required for: mark()
        """

        child_count = item.childCount()
        for i in range(child_count):
            if item.child(i).text(1)[0:3] == "cid" and (item.child(i).text(0) == text_ or
                                                        item.child(i).toolTip(0) == text_):
                self.ui.treeWidget.setCurrentItem(item.child(i))
            self.recursive_set_current_item(item.child(i), text_)

    def cycle_overlap(self):
        """ Cycle through coded text items located at current cursor position.
        Highlight the coded text. """

        pos = self.ui.textEdit.textCursor().position()
        codes_here = [c for c in self.code_text if c['pos0'] <= pos <= c['pos1']]
        '''for i in self.code_text:
            if i['pos0'] <= pos <= i['pos1']:
                codes_here.append(i)'''
        self.overlap_code_index += 1
        if self.overlap_code_index >= len(codes_here):
            self.overlap_code_index = 0
        item = codes_here[self.overlap_code_index]
        for c in self.codes:
            if item['cid'] == c['cid']:
                item['color'] = c['color']
                break
        # Remove formatting
        cursor = self.ui.textEdit.textCursor()
        cursor.setPosition(int(item['pos0']), QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(int(item['pos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(QtGui.QTextCharFormat())
        # Reapply formatting
        fmt = QtGui.QTextCharFormat()
        brush = QBrush(QColor(item['color']))
        fmt.setBackground(brush)
        fmt.setForeground(QBrush(QColor(TextColor(item['color']).recommendation)))
        cursor.setCharFormat(fmt)
        self.apply_underline_to_overlaps()

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

    def forward_5_seconds(self):
        """ Forward AV 5 seconds. Key 5. """

        if self.mediaplayer.get_media() is None:
            return
        time_msecs = self.mediaplayer.get_time() + 5000
        if time_msecs > self.media.get_duration():
            time_msecs = self.media.get_duration() - 1
        pos = time_msecs / self.mediaplayer.get_media().get_duration()
        self.mediaplayer.set_position(pos)
        # Update timer display
        msecs = self.mediaplayer.get_time()
        self.ui.label_time.setText(msecs_to_hours_mins_secs(msecs) + self.media_duration_text)
        self.update_ui()

    def extend_left(self, code_):
        """ Extend left to coded text. Shift left arrow """

        if code_['pos0'] < 1:
            return
        code_['pos0'] -= 1
        cur = self.app.conn.cursor()
        text_sql = "select substr(fulltext,?,?) from source where id=?"
        cur.execute(text_sql, [code_['pos0'] + 1, code_['pos1'] - code_['pos0'], code_['fid']])
        seltext = cur.fetchone()[0]
        sql = "update code_text set pos0=?, seltext=? where cid=? and fid=? and pos0=? and pos1=? and owner=?"
        cur.execute(sql,
                    (code_['pos0'], seltext, code_['cid'], code_['fid'], code_['pos0'] + 1, code_['pos1'],
                     self.app.settings['codername']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def extend_right(self, code_):
        """ Extend to right coded text. Shift right arrow """

        if code_['pos1'] + 1 >= len(self.ui.textEdit.toPlainText()):
            return
        code_['pos1'] += 1
        cur = self.app.conn.cursor()
        text_sql = "select substr(fulltext,?,?) from source where id=?"
        cur.execute(text_sql, [code_['pos0'] + 1, code_['pos1'] - code_['pos0'], code_['fid']])
        seltext = cur.fetchone()[0]
        sql = "update code_text set pos1=?, seltext=? where cid=? and fid=? and pos0=? and pos1=? and owner=?"
        cur.execute(sql,
                    (code_['pos1'], seltext, code_['cid'], code_['fid'], code_['pos0'], code_['pos1'] - 1,
                     self.app.settings['codername']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def shrink_to_left(self, code_):
        """ Alt left arrow, shrinks coded text from the right end of the coded text. """

        if code_['pos1'] <= code_['pos0'] + 1:
            return
        code_['pos1'] -= 1
        cur = self.app.conn.cursor()
        text_sql = "select substr(fulltext,?,?) from source where id=?"
        cur.execute(text_sql, [code_['pos0'] + 1, code_['pos1'] - code_['pos0'], code_['fid']])
        seltext = cur.fetchone()[0]
        sql = "update code_text set pos1=?, seltext=? where cid=? and fid=? and pos0=? and pos1=? and owner=?"
        cur.execute(sql,
                    (code_['pos1'], seltext, code_['cid'], code_['fid'], code_['pos0'], code_['pos1'] + 1,
                     self.app.settings['codername']))
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def shrink_to_right(self, code_):
        """ Alt right arrow shrinks coded text from the left end of the coded text. """

        if code_['pos0'] >= code_['pos1'] - 1:
            return
        code_['pos0'] += 1
        cur = self.app.conn.cursor()
        text_sql = "select substr(fulltext,?,?) from source where id=?"
        cur.execute(text_sql, [code_['pos0'] + 1, code_['pos1'] - code_['pos0'], code_['fid']])
        seltext = cur.fetchone()[0]
        sql = "update code_text set pos0=?, seltext=? where cid=? and fid=? and pos0=? and pos1=? and owner=?"
        cur.execute(sql,
                    (code_['pos0'], seltext, code_['cid'], code_['fid'], code_['pos0'] - 1, code_['pos1'],
                     self.app.settings['codername']))
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
        self.ui.label_rate.setText(str(round(rate, 1)) + "x")

    def decrease_play_rate(self):
        """ Several decreased rate options """

        rate = self.mediaplayer.get_rate()
        rate -= 0.1
        if rate < 0.1:
            rate = 0.1
        self.mediaplayer.set_rate(rate)
        self.ui.label_rate.setText(str(round(rate, 1)) + "x")

    def assign_segment_to_code(self, selected):
        """ Assign time segment to selected code. Insert an entry into the database.
        Then clear the segment for re-use."""

        if self.file_ is None or self.segment['start_msecs'] is None or self.segment['end_msecs'] is None:
            self.clear_segment()
            return
        sql = "insert into code_av (id, pos0, pos1, cid, memo, date, owner, important) values(?,?,?,?,?,?,?, null)"
        cid = int(selected.text(1).split(':')[1])
        values = [self.file_['id'], self.segment['start_msecs'],
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
        self.segment['important'] = None
        self.segment['seltext'] = ""
        self.ui.label_segment.setText(_("Segment:"))
        self.ui.pushButton_coding.setText(_("Start segment"))

    def item_moved_update_data(self, item, parent):
        """ Called from drop event in treeWidget view port.
        identify code or category to move.
        Also merge codes if one code is dropped on another code.
        param:
            item: QTreeWidgetItem
            parent: QTreeWidgetItem """

        # Find the category in the list
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

        # Find the code in the list
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

    def recursive_non_merge_item(self, item, no_merge_list):
        """ Find matching item to be the current selected item.
        Recurse through any child categories.
        Tried to use QTreeWidget.finditems - but this did not find matching item text
        Called by: textEdit recent codes menu option
        Required for: merge_category()
        param:
            item: QTreeWidgetItem
            no_merge_list: list of ?
        """

        child_count = item.childCount()
        for i in range(child_count):
            if item.child(i).text(1)[0:3] == "cat":
                no_merge_list.append(item.child(i).text(1)[6:])
            self.recursive_non_merge_item(item.child(i), no_merge_list)
        return no_merge_list

    def merge_category(self, catid):
        """ Select another category to merge this category into.
        param:
            catid: Integer  category identifier """

        do_not_merge_list = []
        do_not_merge_list = self.recursive_non_merge_item(self.ui.treeWidget.currentItem(), do_not_merge_list)
        do_not_merge_list.append(str(catid))
        do_not_merge_ids_str = "(" + ",".join(do_not_merge_list) + ")"
        sql = "select name, catid, supercatid from code_cat where catid not in "
        sql += do_not_merge_ids_str + " order by name"
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
        try:
            for code in self.codes:
                if code['catid'] == catid:
                    cur.execute("update code_name set catid=? where catid=?", [category['catid'], catid])
            cur.execute("delete from code_cat where catid=?", [catid])
            self.update_dialog_codes_and_categories()
            for cat in self.categories:
                if cat['supercatid'] == catid:
                    cur.execute("update code_cat set supercatid=? where supercatid=?", [category['catid'], catid])
            # Clear any orphan supercatids
            sql = "select supercatid from code_cat where supercatid not in (select catid from code_cat)"
            cur.execute(sql)
            orphans = cur.fetchall()
            sql = "update code_cat set supercatid=Null where supercatid=?"
            for orphan in orphans:
                cur.execute(sql, [orphan[0]])
            self.app.conn.commit()
        except:
            self.app.conn.rollback() # revert all changes 
            self.update_dialog_codes_and_categories()
            raise            
        self.update_dialog_codes_and_categories()

    def merge_codes(self, item, parent):
        """ Merge code with another code .
        Called by item_moved_update_data when a code is moved onto another code.
        param:
            item: QTreeWidgetItem
            parent: QTreeWidgetItem """

        # Check item dropped on itself. Error can occur on Ubuntu 22.04.
        if item['name'] == parent.text(0):
            return

        msg_ = _("Merge code: ") + item['name'] + " ==> " + parent.text(0)
        reply = QtWidgets.QMessageBox.question(self, _('Merge codes'),
                                               msg_, QtWidgets.QMessageBox.StandardButton.Yes,
                                               QtWidgets.QMessageBox.StandardButton.No)
        if reply == QtWidgets.QMessageBox.StandardButton.No:
            return
        cur = self.app.conn.cursor()
        old_cid = item['cid']
        new_cid = int(parent.text(1).split(':')[1])
        # Update cid for each coded segment in text, av, image. Delete where there is an Integrity error
        ct_sql = "select ctid from code_text where cid=?"
        cur.execute(ct_sql, [old_cid])
        ct_res = cur.fetchall()
        try:
            for ct in ct_res:
                try:
                    cur.execute("update code_text set cid=? where ctid=?", [new_cid, ct[0]])
                except sqlite3.IntegrityError as e_:
                    # print(ct, e_)
                    cur.execute("delete from code_text where ctid=?", [ct[0]])
            av_sql = "select avid from code_av where cid=?"
            cur.execute(av_sql, [old_cid])
            av_res = cur.fetchall()
            for av in av_res:
                try:
                    cur.execute("update code_av set cid=? where avid=?", [new_cid, av[0]])
                except sqlite3.IntegrityError as e_:
                    # print(e_)
                    cur.execute("delete from code_av where avid=?", [av[0]])
            img_sql = "select imid from code_image where cid=?"
            cur.execute(img_sql, [old_cid])
            img_res = cur.fetchall()
            for img in img_res:
                try:
                    cur.execute("update code_image set cid=? where imid=?", [new_cid, img[0]])
                except sqlite3.IntegrityError as e_:
                    # print(e_)
                    cur.execute("delete from code_image where imid=?", [img[0]])
            cur.execute("delete from code_name where cid=?", [old_cid, ])
            self.app.conn.commit()
        except:
            self.app.conn.rollback() # revert all changes 
            raise                
        self.update_dialog_codes_and_categories()
        self.parent_textEdit.append(msg_)
        self.load_segments()

    def add_code(self, catid=None):
        """  Use add_item dialog to get new code text. Add_code_name dialog checks for
        duplicate code name. A random color is selected for the code.
        New code is added to data and database.
        param:
            catid : None to add to without category, catid to add to to category. """

        ui = DialogAddItemName(self.app, self.codes, _("Add new code"), _("New code name"))
        ui.exec()
        new_name = ui.get_new_name()
        if new_name is None:
            return
        code_color = colors[randint(0, len(colors) - 1)]
        item = {'name': new_name, 'memo': "", 'owner': self.app.settings['codername'],
                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'catid': catid,
                'color': code_color}
        cur = self.app.conn.cursor()
        cur.execute("insert into code_name (name,memo,owner,date,catid,color) values(?,?,?,?,?,?)",
                    (item['name'], item['memo'], item['owner'], item['date'], item['catid'], item['color']))
        self.app.conn.commit()
        self.parent_textEdit.append(_("Code added: ") + item['name'])
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False

    def add_category(self, supercatid=None):
        """ Add a new category.
        Note: the addItem dialog does the checking for duplicate category names
        param:
            supercatid : None to add without category, supercatid to add to category. """

        ui = DialogAddItemName(self.app, self.categories, _("Category"), _("Category name"))
        ui.exec()
        new_name = ui.get_new_name()
        if new_name is None:
            return
        item = {'name': new_name, 'cid': None, 'memo': "",
                'owner': self.app.settings['codername'],
                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
        cur = self.app.conn.cursor()
        cur.execute("insert into code_cat (name, memo, owner, date, supercatid) values(?,?,?,?,?)",
                    (item['name'], item['memo'], item['owner'], item['date'], supercatid))
        self.app.conn.commit()
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False

    def delete_category_or_code(self, selected):
        """ Determine if category or code is to be deleted.
        param:
            selected: QTreeWidgetItem """

        if selected.text(1)[0:3] == 'cat':
            self.delete_category(selected)
            return  # avoid error as selected is now None
        if selected.text(1)[0:3] == 'cid':
            self.delete_code(selected)

    def delete_code(self, selected):
        """ Find code, remove from database, refresh and code_name data and fill
        treeWidget.
        param:
            selected: QTreeWidgetItem """

        # find the code_in the list, check to delete
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
        cur.execute("delete from code_av where cid=?", [code_['cid'], ])
        cur.execute("delete from code_image where cid=?", [code_['cid'], ])
        cur.execute("delete from code_text where cid=?", [code_['cid'], ])
        self.app.conn.commit()
        self.parent_textEdit.append(_("Code deleted: ") + code_['name'])
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False

    def delete_category(self, selected):
        """ Find category, remove from database, refresh categories and code data
        and fill treeWidget.
        param:
            selected: QTreeWidgetItem """

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
        self.parent_textEdit.append(_("Category deleted: ") + category['name'])
        self.update_dialog_codes_and_categories()
        self.app.delete_backup = False

    def add_edit_code_memo(self, selected):
        """ View and edit a memo to a code.
        param:
            selected: QTreeWidgetItem """

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
            ui.exec()
            memo = ui.memo
            if memo == "":
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, "")
            else:
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, _("Memo"))
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
            ui.exec()
            memo = ui.memo
            if memo == "":
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, "")
            else:
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, _("Memo"))
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
        not currently in use.
        param:
            selected: QTreeWidgetItem """

        if selected.text(1)[0:3] == 'cid':
            new_name, ok = QtWidgets.QInputDialog.getText(self, _("Rename code"), _("New code name:") + " " * 30,
                                                          QtWidgets.QLineEdit.EchoMode.Normal, selected.text(0))
            if not ok or new_name == '':
                return
            # check that no other code has this text
            for c in self.codes:
                if c['name'] == new_name:
                    Message(self.app, _('Name in use'), new_name + _(" Name already in use, choose another."),
                            "warning").exec()
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
            self.parent_textEdit.append(_("Code renamed: ") + f"{self.codes[found]['name']} ==> {new_name}")
            self.update_dialog_codes_and_categories()
            self.app.delete_backup = False
            return

        if selected.text(1)[0:3] == 'cat':
            new_name, ok = QtWidgets.QInputDialog.getText(self, _("Rename category"), _("New category name:"),
                                                          QtWidgets.QLineEdit.EchoMode.Normal, selected.text(0))
            if not ok or new_name == '':
                return
            # Check that no other category has this text
            for c in self.categories:
                if c['name'] == new_name:
                    msg_ = _("This category name is already in use")
                    Message(self.app, _('Duplicate category name'), msg_, "warning").exec()
                    return
            # Find the category in the list
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
        """ Change the color of the currently selected code.
        param:
            selected: QTreeWidgetItem """

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
        cursor.setPosition(0, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(len(self.transcription[1]) - 1, QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(QtGui.QTextCharFormat())

    def highlight(self):
        """ Apply text highlighting to current file.
        If no colour has been assigned to a code, those coded text fragments are coloured gray.
        Each code text item contains: fid, date, pos0, pos1, seltext, cid, status, memo,
        name, owner. """

        for item in self.code_text:
            fmt = QtGui.QTextCharFormat()
            cursor = self.ui.textEdit.textCursor()
            cursor.setPosition(int(item['pos0']), QtGui.QTextCursor.MoveMode.MoveAnchor)
            cursor.setPosition(int(item['pos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
            color = "#F8E0E0"  # default light red
            for fcode in self.codes:
                if fcode['cid'] == item['cid']:
                    color = fcode['color']
            fmt.setBackground(QBrush(QColor(color)))
            # Foreground depends on the defined need_white_text color in color_selector
            text_brush = QBrush(QColor(TextColor(color).recommendation))
            fmt.setForeground(text_brush)
            # Highlight codes with memos - these are italicised
            # Italics also used for overlapping codes
            if item['memo'] != "":
                fmt.setFontItalic(True)
            else:
                fmt.setFontItalic(False)
                fmt.setFontWeight(QtGui.QFont.Weight.Normal)
            # Bold important codes
            if item['important']:
                fmt.setFontWeight(QtGui.QFont.Weight.Bold)
            # Use important flag for ONLY showing important codes (button selected)
            if self.important and item['important'] == 1:
                cursor.setCharFormat(fmt)
            # Show all codes, as important button not selected
            if not self.important:
                cursor.setCharFormat(fmt)
        # Add annotation marks - these are in bold
        for note in self.annotations:
            if note['fid'] == self.transcription[0]:
                cursor = self.ui.textEdit.textCursor()
                cursor.setPosition(int(note['pos0']), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(int(note['pos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
                fmt_bold = QtGui.QTextCharFormat()
                fmt_bold.setFontWeight(QtGui.QFont.Weight.Bold)
                cursor.mergeCharFormat(fmt_bold)
        self.apply_underline_to_overlaps()

    def apply_underline_to_overlaps(self):
        """ Apply underline format to coded text sections which are overlapping. """

        overlaps = []
        for i in self.code_text:
            for j in self.code_text:
                if j != i:
                    if j['pos0'] <= i['pos0'] <= j['pos1']:
                        if j['pos0'] >= i['pos0'] and j['pos1'] <= i['pos1']:
                            overlaps.append([j['pos0'], j['pos1']])
                        elif i['pos0'] >= j['pos0'] and i['pos1'] <= j['pos1']:
                            overlaps.append([i['pos0'], i['pos1']])
                        elif j['pos0'] > i['pos0']:
                            overlaps.append([j['pos0'], i['pos1']])
                        else:  # j['pos0'] < i['pos0']:
                            overlaps.append([j['pos1'], i['pos0']])
        cursor = self.ui.textEdit.textCursor()
        for o in overlaps:
            fmt = QtGui.QTextCharFormat()
            fmt.setFontUnderline(True)
            if self.app.settings['stylesheet'] == 'dark':
                fmt.setUnderlineColor(QColor("#000000"))
            else:
                fmt.setUnderlineColor(QColor("#FFFFFF"))
            cursor.setPosition(o[0], QtGui.QTextCursor.MoveMode.MoveAnchor)
            cursor.setPosition(o[1], QtGui.QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(fmt)

    def textedit_menu(self, position):
        """ Context menu for textEdit. Mark, unmark, annotate, copy. """

        if self.ui.checkBox_scroll_transcript.isChecked():
            return
        cursor = self.ui.textEdit.cursorForPosition(position)
        selected_text = self.ui.textEdit.textCursor().selectedText()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_copy = None
        action_mark = None
        action_unmark = None
        action_code_memo = None
        action_start_pos = None
        action_end_pos = None
        action_play_text = None
        play_text_avid = None
        action_important = None
        action_not_important = None
        action_change_code = None
        action_annotate = None
        action_edit_annotate = None
        for item in self.code_text:
            if item['pos0'] <= cursor.position() <= item['pos1']:
                if item['avid'] is not None:
                    action_play_text = QtGui.QAction(_("Play text"))
                    # TODO select which avid if multiple coded here
                    play_text_avid = item['avid']
                action_unmark = QtGui.QAction(_("Unmark"))
                action_code_memo = QtGui.QAction(_("Memo coded text M"))
                action_start_pos = QtGui.QAction(_("Change start position (SHIFT LEFT/ALT RIGHT)"))
                action_end_pos = QtGui.QAction(_("Change end position (SHIFT RIGHT/ALT LEFT)"))
                action_change_code = QtGui.QAction(_("Change code"))
            if item['pos0'] <= cursor.position() <= item['pos1']:
                if item['important'] is None or item['important'] > 1:
                    action_important = QtGui.QAction(_("Add important mark (I)"))
                if item['important'] == 1:
                    action_not_important = QtGui.QAction(_("Remove important mark"))
        if action_play_text:
            menu.addAction(action_play_text)
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
        if action_change_code:
            menu.addAction(action_change_code)
        if selected_text != "":
            if self.ui.treeWidget.currentItem() is not None:
                action_mark = menu.addAction(_("Mark (Q)"))
            # Use up to 5 recent codes
            if len(self.recent_codes) > 0:
                submenu = menu.addMenu(_("Mark with recent code (R)"))
                for item in self.recent_codes:
                    submenu.addAction(item['name'])
            action_annotate = menu.addAction(_("Annotate (A)"))
            action_copy = menu.addAction(_("Copy to clipboard"))
        if selected_text == "" and self.is_annotated(cursor.position()):
            action_edit_annotate = menu.addAction(_("Edit annotation"))
        action_video_position_timestamp = -1
        for ts in self.time_positions:
            if ts[0] <= cursor.position() <= ts[1]:
                action_video_position_timestamp = menu.addAction(_("Video position to timestamp"))
        action = menu.exec(self.ui.textEdit.mapToGlobal(position))
        if action is None:
            return
        if selected_text != "" and action == action_copy:
            self.copy_selected_text_to_clipboard()
            return
        if selected_text != "" and self.ui.treeWidget.currentItem() is not None and action == action_mark:
            self.mark()
            return
        if action == action_important:
            self.set_important(cursor.position())
            return
        if action == action_not_important:
            self.set_important(cursor.position(), False)
            return
        if action == action_code_memo:
            self.coded_text_memo(cursor.position())
            return
        if action_unmark is not None and action == action_unmark:
            self.unmark(cursor.position())
            return
        if action_play_text is not None and action == action_play_text:
            self.play_text(play_text_avid)
            return
        if selected_text != "" and action == action_annotate:
            self.annotate(cursor.position())
            return
        if action == action_edit_annotate:
            # Used fora point text press rather than a selected text
            self.annotate(cursor.position())
            return
        try:
            if action == action_video_position_timestamp:
                self.set_video_to_timestamp_position(cursor.position())
                return
        except Exception as e_:
            print("action_video_position_timestamp ", str(e_))
            logger.warning(str(e_))
            return
        if action == action_start_pos:
            self.change_text_code_pos(cursor.position(), "start")
            return
        if action == action_end_pos:
            self.change_text_code_pos(cursor.position(), "end")
            return
        if action == action_change_code:
            self.change_code_to_another_code(cursor.position())
            return
        # Remaining actions will be the submenu codes
        self.recursive_set_current_item(self.ui.treeWidget.invisibleRootItem(), action.text())
        self.mark()

    def change_code_to_another_code(self, position):
        """ Change code to another code """

        # Get coded segments at this position
        if self.transcription is None:
            return
        coded_text_list = []
        for item in self.code_text:
            if item['pos0'] <= position <= item['pos1'] and \
                    item['owner'] == self.app.settings['codername']:
                coded_text_list.append(item)
        if not coded_text_list:
            return
        text_item = []
        if len(coded_text_list) == 1:
            text_item = coded_text_list[0]
        # Multiple codes at this position to select from
        if len(coded_text_list) > 1:
            ui = DialogSelectItems(self.app, coded_text_list, _("Select codes"), "single")
            ok = ui.exec()
            if not ok:
                return
            text_item = ui.get_selected()
        if not text_item:
            return
        # Get replacement code
        codes_list = deepcopy(self.codes)
        to_remove = None
        for code_ in codes_list:
            if code_['cid'] == text_item['cid']:
                to_remove = code_
        if to_remove:
            codes_list.remove(to_remove)
        ui = DialogSelectItems(self.app, codes_list, _("Select replacement code"), "single")
        ok = ui.exec()
        if not ok:
            return
        replacememt_code = ui.get_selected()
        if not replacememt_code:
            return
        cur = self.app.conn.cursor()
        sql = "update code_text set cid=? where ctid=?"
        try:
            cur.execute(sql, [replacememt_code['cid'], text_item['ctid']])
            self.app.conn.commit()
        except sqlite3.IntegrityError:
            pass
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def is_annotated(self, position):
        """ Check if position is annotated to provide annotation menu option.
        Returns True or False """

        for note in self.annotations:
            if (note['pos0'] <= position <= note['pos1']) \
                    and note['fid'] == self.transcription[0]:
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
        if self.file_ is None:
            return
        coded_text_list = []
        for item in self.code_text:
            # if position + self.file_['start'] >= item['pos0'] and position + self.file_['start'] <= item['pos1'] and \
            if item['pos0'] <= position <= item['pos1'] and \
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
        for item in text_items:
            cur.execute(
                "update code_text set important=? where cid=? and fid=? and seltext=? and pos0=? and pos1=? and owner=?",
                (importance, item['cid'], item['fid'], item['seltext'], item['pos0'], item['pos1'], item['owner']))
            self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def coded_text_memo(self, position=None):
        """ Add or edit a memo for this coded text.
        Called by: textEdit context menu option
        param:
            position : textEdit cursor position """

        if self.transcription is None:
            return
        coded_text_list = []
        for item in self.code_text:
            if item['pos0'] <= position <= item['pos1'] and item['owner'] == \
                    self.app.settings['codername']:
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
                    (memo, text_item['cid'], text_item['fid'], text_item['seltext'], text_item['pos0'],
                     text_item['pos1'], text_item['owner']))
        self.app.conn.commit()
        for i in self.code_text:
            if text_item['cid'] == i['cid'] and text_item['seltext'] == i['seltext'] and text_item['pos0'] == i['pos0'] \
                    and text_item['pos1'] == i['pos1'] and text_item['owner'] == self.app.settings['codername']:
                i['memo'] = memo
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()

    def change_text_code_pos(self, location, start_or_end):
        """ Change code start or end character position in text.
        param:
            location: integer
            start_or_end: 'start' or 'end' """

        if self.file_ is None:
            return
        code_list = []
        for item in self.code_text:
            if item['pos0'] <= location <= item['pos1'] and item['owner'] == \
                    self.app.settings['codername']:
                code_list.append(item)
        if not code_list:
            return
        code_to_edit = None
        if len(code_list) == 1:
            code_to_edit = code_list[0]
        # multiple codes to select from
        if len(code_list) > 1:
            ui = DialogSelectItems(self.app, code_list, _("Select code to unmark"), "single")
            ok = ui.exec()
            if not ok:
                return
            code_to_edit = ui.get_selected()
        if code_to_edit is None:
            return
        txt_len = len(self.ui.textEdit.toPlainText())
        changed_start = 0
        changed_end = 0
        if start_or_end == "start":
            max_ = code_to_edit['pos1'] - code_to_edit['pos0'] - 1
            min_ = -1 * code_to_edit['pos0']
            changed_start, ok = QtWidgets.QInputDialog.getInt(self, _("Change start position"), _(
                "Change start character position.\nPositive or negative number:"), 0, min_, max_, 1)
            if not ok:
                return
        if start_or_end == "end":
            max_ = txt_len - code_to_edit['pos1']
            min_ = code_to_edit['pos0'] - code_to_edit['pos1'] + 1
            changed_end, ok = QtWidgets.QInputDialog.getInt(self, _("Change end position"), _(
                "Change end character position.\nPositive or negative number:"), 0, min_, max_, 1)
            if not ok:
                return
        if changed_start == 0 and changed_end == 0:
            return
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
        self.ui.pushButton_play.setIcon(qta.icon('mdi6.pause'))
        self.play_segment_end = segment['pos1']
        self.timer.start()

    def set_video_to_timestamp_position(self, position):
        """ Set the video position to this time stamp.
        The horizontal slider will move to match the position of the video (in update_ui).
        """

        timestamp = None
        for ts in self.time_positions:
            if ts[0] <= position <= ts[1]:
                timestamp = ts
        if timestamp is None:
            return
        self.timer.stop()
        self.mediaplayer.set_position(timestamp[2] / self.media.get_duration())
        self.timer.start()

    def copy_selected_text_to_clipboard(self):
        """ Copy text to clipboard for external use.
        For example adding text to another document. """

        selected_text = self.ui.textEdit.textCursor().selectedText()
        cb = QtWidgets.QApplication.clipboard()
        cb.setText(selected_text)

    def mark(self):
        """ Mark selected text in file with currently selected code.
       Need to check for multiple same codes at same pos0 and pos1.
       """

        if self.transcription is None or self.ui.textEdit.toPlainText() == "":
            Message(self.app, _('Warning'), _('No transcription'), "warning").exec()
            return
        item = self.ui.treeWidget.currentItem()
        if item is None:
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec()
            return
        if item.text(1).split(':')[0] == 'catid':  # must be a code
            return
        cid = int(item.text(1).split(':')[1])
        selected_text = self.ui.textEdit.textCursor().selectedText()
        pos0 = self.ui.textEdit.textCursor().selectionStart()
        pos1 = self.ui.textEdit.textCursor().selectionEnd()
        if pos0 == pos1:  # Something quirky happened
            return
        # add the coded section to code text, add to database and update GUI
        coded = {'cid': cid, 'fid': self.transcription[0], 'seltext': selected_text,
                 'pos0': pos0, 'pos1': pos1, 'owner': self.app.settings['codername'], 'memo': "",
                 'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'important': None}

        cur = self.app.conn.cursor()
        # check for an existing duplicated marking first
        cur.execute("select * from code_text where cid = ? and fid=? and pos0=? and pos1=? and owner=?",
                    (coded['cid'], coded['fid'], coded['pos0'], coded['pos1'], coded['owner']))
        result = cur.fetchall()
        if len(result) > 0:
            Message(self.app, _('Already Coded'),
                    _("This segment has already been coded with this code by ") + coded['owner'], "warning").exec()
            return
        self.code_text.append(coded)
        self.highlight()

        # Should not get sqlite3.IntegrityError:
        # UNIQUE constraint failed: code_text.cid, code_text.fid, code_text.pos0, code_text.pos1
        try:
            cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,\
                memo,date, important) values(?,?,?,?,?,?,?,?,?)", (coded['cid'], coded['fid'],
                                                                   coded['seltext'], coded['pos0'], coded['pos1'],
                                                                   coded['owner'],
                                                                   coded['memo'], coded['date'], coded['important']))
            self.app.conn.commit()
            self.app.delete_backup = False
        except Exception as e_:
            logger.debug(str(e_))
            print(e_)
        # update coded, filter for tooltip
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()

        # Update recent_codes
        tmp_code = None
        for c in self.codes:
            if c['cid'] == cid:
                tmp_code = c
        if tmp_code is None:
            return
        for item in self.recent_codes:
            if item == tmp_code:
                self.recent_codes.remove(item)
                break
        self.recent_codes.insert(0, tmp_code)
        if len(self.recent_codes) > 10:
            self.recent_codes = self.recent_codes[:10]
        recent_codes_string = ""
        for r in self.recent_codes:
            recent_codes_string += f" {r['cid']}"
        recent_codes_string = recent_codes_string[1:]
        cur.execute("update project set recently_used_codes=?", [recent_codes_string])
        self.app.conn.commit()

    def restore_unmarked_segment(self):
        """ Restore the last deleted coded segment.
        The event filer method checks for text or segment coding.
        Requires self.undo_deleted_codes """

        item = self.undo_deleted_codes[0]
        sql = "insert into code_av (id, pos0, pos1, cid, memo, date, owner, important) values(?,?,?,?,?,?,?,?)"
        values = [item['id'], item['pos0'], item['pos1'], item['cid'], item['memo'],
                  item['date'], item['owner'], item['important']]
        cur = self.app.conn.cursor()
        cur.execute(sql, values)
        self.app.conn.commit()
        self.load_segments()
        self.clear_segment()
        self.app.delete_backup = False
        self.fill_code_counts_in_tree()

    def restore_unmarked_text_codes(self):
        """ Restore the last deleted code(s).
        One code or multiple, depends on what was selected when the unmark method was used.
        The event filer method checks for text or segment coding.
        Requires self.undo_deleted_codes """

        if not self.undo_deleted_codes:
            return
        cur = self.app.conn.cursor()
        for item in self.undo_deleted_codes:
            cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,\
                memo,date, important) values(?,?,?,?,?,?,?,?,?)", (item['cid'], item['fid'],
                                                                   item['seltext'], item['pos0'], item['pos1'],
                                                                   item['owner'],
                                                                   item['memo'], item['date'], item['important']))
        self.app.conn.commit()
        self.undo_deleted_codes = []
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()

    def unmark(self, location):
        """ Remove code marking by this coder from selected text in current file.
        Keep a record for ctrl Z restore.
        param:
            location: integer """

        if self.transcription is None or self.ui.textEdit.toPlainText() == "":
            return
        unmarked_list = []
        for item in self.code_text:
            if item['pos0'] <= location <= item['pos1'] and \
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
        if not to_unmark:
            return
        self.undo_deleted_codes = deepcopy(to_unmark)

        # Delete from db, remove from coding and update highlights
        cur = self.app.conn.cursor()
        for item in to_unmark:
            cur.execute("delete from code_text where cid=? and pos0=? and pos1=? and owner=? and fid=?",
                        (item['cid'], item['pos0'], item['pos1'], self.app.settings['codername'], item['fid']))
            self.app.conn.commit()
        self.app.conn.commit()

        # Update filter for tooltip and update code colours
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        self.app.delete_backup = False

    def annotate(self, cursor_pos):
        """ Add view, or remove an annotation for selected text.
        Annotation positions are displayed as bold text.
        params:
            cursor_pos : textCursor current position
        """

        if self.transcription is None or self.ui.textEdit.toPlainText() == "":
            Message(self.app, _('Warning'), _("No media transcription selected"), "warning").exec()
            return
        pos0 = self.ui.textEdit.textCursor().selectionStart()
        pos1 = self.ui.textEdit.textCursor().selectionEnd()
        text_length = len(self.ui.textEdit.toPlainText())
        if pos0 >= text_length or pos1 > text_length:
            return
        item = None
        details = ""
        annotation = ""
        # Find existing annotation at this position for this file
        for note in self.annotations:
            if note['pos0'] <= cursor_pos <= note['pos1'] and note['fid'] == self.transcription[0]:
                item = note  # use existing annotation
                details = item['owner'] + " " + item['date']
                break
        # Exit if no text selected and there is no annotation at this position
        if pos0 == pos1 and item is None:
            return
        # Add new item to annotations, add to database and update GUI
        if item is None:
            item = {'fid': self.transcription[0], 'pos0': pos0, 'pos1': pos1,
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
                self.annotations = self.app.get_annotations()
                self.parent_textEdit.append(_("Annotation added at position: ")
                                            + str(item['pos0']) + "-" + str(item['pos1']) + _(" for: ") +
                                            self.transcription[2])
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
            cur.execute("delete from annotation where pos0 = ?", (item['pos0'],))
            self.app.conn.commit()
            self.annotations = self.app.get_annotations()
            self.parent_textEdit.append(_("Annotation removed from position ")
                                        + str(item['pos0']) + _(" for: ") + self.transcription[2])
        self.get_coded_text_update_eventfilter_tooltips()

    # Segment menu. A hack to fix when pyinstaller Segment.contextMenu does not work.
    def label_segment_menu(self):
        """ Menu on the Label segment. This is in place because the segment context menu
        does not work when packed with pyinstaller """

        if self.file_ is None or not self.segments:
            return
        for s in self.segments:
            s['name'] = f"{msecs_to_hours_mins_secs(s['pos0'])}-{msecs_to_hours_mins_secs(s['pos1'])}: {s['codename']}"
            print(f"{msecs_to_hours_mins_secs(s['pos0'])}-{msecs_to_hours_mins_secs(s['pos1'])}: {s['codename']}")
        ui = DialogSelectItems(self.app, self.segments, ("Select a segment"), "single")
        ok = ui.exec()
        if not ok:
            return
        segment = ui.get_selected()
        if not segment:
            return
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_memo = menu.addAction(_('Memo for segment'))
        action_delete = menu.addAction(_('Delete segment'))
        action_play = menu.addAction(_('Play segment'))
        action_important = menu.addAction(_('Important mark'))
        action_change_start_pos = menu.addAction(_('Edit start position'))
        action_change_end_pos = menu.addAction(_('Edit end position'))
        action = menu.exec(QtGui.QCursor.pos())
        if action is None:
            return
        if action == action_play:
            self.play_segment(segment)
            return
        if action == action_memo:
            self.edit_segment_memo(segment)
            return
        if action == action_delete:
            self.delete_segment(segment)
            return
        if action == action_important:
            self.set_segment_importance(segment)
            return
        if action == action_change_start_pos:
            self.edit_segment_start(segment)
            return
        if action == action_change_end_pos:
            self.edit_segment_end(segment)
            return

    def set_segment_importance(self, segment):
        """ Set or unset importance to self.segment.
        Importance is denoted using '1'
        params:
            important: boolean, default True """

        importance = None
        if segment['important'] != 1:
            importance = 1
        segment['important'] = importance
        cur = self.app.conn.cursor()
        sql = "update code_av set important=?, date=? where avid=?"
        values = [importance, datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), segment['avid']]
        cur.execute(sql, values)
        self.app.conn.commit()
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()
        self.load_segments()

    def edit_segment_memo(self, segment):
        """ View, edit or delete memo for this segment.
        Reload_segment is set to True, so on playing media, the update event will reload
        all segments. """

        ui = DialogMemo(self.app, _("Memo for segment"), segment["memo"])
        ui.exec()
        if segment['memo'] == ui.memo:
            return
        segment['memo'] = ui.memo
        sql = "update code_av set memo=?, date=? where avid=?"
        values = [segment['memo'],
                  datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), segment['avid']]
        cur = self.app.conn.cursor()
        cur.execute(sql, values)
        self.app.conn.commit()
        self.app.delete_backup = False
        self.load_segments()

    def play_segment(self, segment):
        """ Play segment section. Stop at end of segment. """

        pos = segment['pos0'] / self.mediaplayer.get_media().get_duration()
        self.mediaplayer.play()
        self.mediaplayer.set_position(pos)
        self.is_paused = False
        self.ui.pushButton_play.setIcon(qta.icon('mdi6.pause'))
        self.play_segment_end = segment['pos1']
        self.timer.start()

    def delete_segment(self, segment):
        """ Mark the segment for deletion. Does not actually delete segment item, but hides
        it from the scene. Reload_segment is set to True, so on playing media, the update
        event will reload all segments. """

        # print(self.segment)
        ui = DialogConfirmDelete(self.app,
                                 _("Segment: ") + segment['codename'] + "\n" + _("Memo: ") + segment['memo'])
        ok = ui.exec()
        if not ok:
            return
        tmp_seg = deepcopy(self.segment)
        tmp_seg['is_segment'] = True  # Need to distinguish from text coding
        self.undo_deleted_codes = [tmp_seg]
        sql = "delete from code_av where avid=?"
        values = [segment['avid']]
        cur = self.app.conn.cursor()
        cur.execute(sql, values)
        sql = "update code_text set avid=null where avid=?"
        cur.execute(sql, values)
        self.app.conn.commit()
        self.get_coded_text_update_eventfilter_tooltips()
        self.app.delete_backup = False
        self.load_segments()

    def edit_segment_start(self, segment):
        """ Edit segment start time. """

        i, ok_pressed = QtWidgets.QInputDialog.getInt(self, "Segment start in mseconds",
                                                      "Edit time in milliseconds\n1000 msecs = 1 second:",
                                                      segment['pos0'], 1,
                                                      segment['pos1'] - 1, 5)
        if not ok_pressed:
            return
        if i < 1:
            return
        segment['pos0'] = i
        sql = "update code_av set pos0=? where avid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql, [i, segment['avid']])
        self.app.conn.commit()
        self.app.delete_backup = False
        self.load_segments()

    def edit_segment_end(self, segment):
        """ Edit segment end time """

        duration = self.media.get_duration()
        i, ok_pressed = QtWidgets.QInputDialog.getInt(None, "Segment end in mseconds",
                                                      "Edit time in milliseconds\n1000 msecs = 1 second:",
                                                      segment['pos1'],
                                                      segment['pos0'] + 1, duration - 1, 5)
        if not ok_pressed:
            return
        if i < 1:
            return
        segment['pos1'] = i
        sql = "update code_av set pos1=? where avid=?"
        cur = self.app.conn.cursor()
        cur.execute(sql, [i, segment['avid']])
        self.app.conn.commit()
        self.app.delete_backup = False
        self.load_segments()


class ToolTipEventFilter(QtCore.QObject):
    """ Used to add a dynamic tooltip for the textEdit.
    The tool top text is changed according to its position in the text.
    If over a coded section the codename is displayed in the tooltip.
    Need to add av time segments to the code_text where relevant.
    """

    codes = None
    code_text = None
    annotations = None
    app = None

    def set_codes_and_annotations(self, app, code_text, codes, annotations):
        """ Update codes and coded text and annotations for tooltips. """

        self.app = app
        self.code_text = code_text
        self.codes = codes
        self.annotations = annotations
        for item in self.code_text:
            for c in self.codes:
                if item['cid'] == c['cid']:
                    item['name'] = c['name']
                    item['color'] = c['color']

    def eventFilter(self, receiver, event):
        """ Tool tip event filter for textEdit """

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
                if item['pos0'] <= pos <= item['pos1']:
                    try:
                        text_ += '<p style="background-color:' + item['color']
                        text_ += '; color:' + TextColor(item['color']).recommendation + '">' + item['name']
                        if self.app.settings['showids']:
                            text_ += " [ctid:" + str(item['ctid']) + "] "
                        if item['avid'] is not None:
                            text_ += " [" + msecs_to_hours_mins_secs(item['av_pos0'])
                            text_ += " - " + msecs_to_hours_mins_secs(item['av_pos1']) + "]"
                        if item['memo'] != "":
                            text_ += "<br /><em>" + _("MEMO: ") + item['memo'] + "</em>"
                        if item['important'] == 1:
                            text_ += "<br /><em>IMPORTANT</em>"
                        text_ += "</p>"
                        multiple += 1
                    except KeyError as e_:
                        msg_ = f"Codes ToolTipEventFilter {e_}. Key error: "
                        msg_ += f"{item}\n{self.code_text}"
                        logger.error(msg_)
            if multiple > 1:
                text_ = multiple_msg + text_
            # Check annotations
            for ann in self.annotations:
                # if item['pos0'] - self.offset <= pos and item['pos1'] - self.offset >= pos:
                if ann['pos0'] <= pos <= ann['pos1']:
                    text_ += "<p>" + _("ANNOTATED:") + ann['memo'] + "</p>"
                    break
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

    def mousePressEvent(self, event):
        """ I have implemented this, as the Segment context menu does not work when right-clicked
        once the QualCoder code is packaged by pyinstaller. (It does work outside of this).
        So a mouse click on a segment will open the 'alternative_context_menu' within the SegmentGraphicsItem
        """

        super(GraphicsScene, self).mousePressEvent(event)
        position = QtCore.QPointF(event.scenePos())
        #print("pos:", position.x(), position.y())
        for item in self.items(): # item is QGraphicsProxyWidget
            #print("X", int(item.scene_from_x), int(item.scene_to_x))
            #print("Y", item.scene_from_y, item.scene_to_y)
            if isinstance(item, SegmentGraphicsItem) and item.scene_from_x <= position.x() <= item.scene_to_x and \
                item.scene_from_y <= position.y() <= item.scene_to_y:
                #print("Found", item.segment)
                item.alternative_context_menu()
                break

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

        # Using these for when packaged with pyinstaller, to find the item on mouse click in the scene
        self.scene_from_x = 0
        self.scene_to_x = 0
        self.scene_from_y = 0
        self.scene_to_y = 8

        self.app = app
        self.segment = segment
        self.scaler = scaler
        self.code_av_dialog = code_av_dialog
        self.reload_segment = False
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        self.set_segment_tooltip()
        self.draw_segment()

    def alternative_context_menu(self):
        """ Using alternative menu to the standard context menu.
        As the standard context menu does not work with pyinstaller. """

        seltext = self.code_av_dialog.ui.textEdit.textCursor().selectedText()
        items = [{'name': 'Memo for segment'},
                 {'name': 'Delete segment'},
                 {'name': 'Play segment'},
                 {'name': 'Edit start position'},
                 {'name': 'Edit end position'},
                 {'name': 'Export segment'}]
        if self.code_av_dialog.ui.textEdit.toPlainText() != "" and seltext != "":
            items.append({'name': 'Link segment to selected text'})
        if self.segment['important'] is None or self.segment['important'] > 1:
            items.append({'name': 'Add important mark'})
        if self.segment['important'] == 1:
            items.append({'name': 'Remove important mark'})
        menu_ui = DialogSelectItems(self.app, items, _("Segment menu"), "single")
        ok = menu_ui.exec()
        if not ok:
            return
        action = menu_ui.get_selected()
        if action['name'] == 'Memo for segment':
            self.edit_memo()
            return
        if action['name'] == 'Export segment':
            self.export_segment()
            return
        if action['name'] == 'Delete segment':
            self.delete()
            return
        if action['name'] == 'Play segment':
            self.play_segment()
            return
        if action['name'] == 'Edit start position':
            self.edit_segment_start()
            return
        if action['name'] == 'Edit end position':
            self.edit_segment_end()
            return
        if seltext != "" and action['name'] == 'Link segment to selected text':
            self.link_segment_to_text()
            return
        if action['name'] == 'Add important mark':
            self.set_coded_importance()
            return
        if action['name'] == 'Remove important mark':
            self.set_coded_importance(False)
            return

    def contextMenuEvent(self, event):
        """
        # https://riverbankcomputing.com/pipermail/pyqt/2010-July/027094.html
        I was not able to mapToGlobal position so, the menu maps to scene position plus
        the Dialog screen position.
        Makes use of current segment: self.segment

        Menu now does not work when packed with pyinstaller.
        """

        seltext = self.code_av_dialog.ui.textEdit.textCursor().selectedText()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_memo = menu.addAction(_('Memo for segment'))
        action_delete = menu.addAction(_('Delete segment'))
        action_play = menu.addAction(_('Play segment'))
        action_edit_start = menu.addAction(_('Edit segment start position'))
        action_edit_end = menu.addAction(_('Edit segment end position'))
        action_export = None
        try:
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True).stdout
            # print(f"RESULT: {result}")
            action_export = menu.addAction(_('Export segment to file'))
        except Exception as e_:
            print(f"Cannot find ffmpeg {e_}")
        action_important = None
        action_not_important = None
        action_link_segment_to_text = None
        if self.code_av_dialog.ui.textEdit.toPlainText() != "" and seltext != "":
            action_link_segment_to_text = menu.addAction(_("Link segment to selected text"))
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
        if seltext != "" and action == action_link_segment_to_text:
            self.link_segment_to_text()
            return
        if action == action_important:
            self.set_coded_importance()
            return
        if action == action_not_important:
            self.set_coded_importance(False)
            return
        if action == action_export:
            self.export_segment()

    def export_segment(self):
        """ Export segment as audio/video file.
        If a video file has multiple tracks only the first one is used for this method.
        https://ffmpeg.org/ffmpeg-filters.html
        Requires installed ffmpeg
        ffmpeg -i input.ogg -ss '100ms' -to '600ms' -c copy output.ogg
        presumes file ending of .xxx (ogg, mp4, mp3, mov...)
        """

        msecs_from = msecs_to_hours_mins_secs(self.segment['pos0'])
        msecs_from = msecs_from.replace('.', "H", 1)
        msecs_from = msecs_from.replace('.', "M", 1) + "S"
        msecs_to = msecs_to_hours_mins_secs(self.segment['pos1'])
        msecs_to = msecs_to.replace('.', "H", 1)
        msecs_to = msecs_to.replace('.', "M", 1) + "S"
        filename = self.code_av_dialog.file_['name'][:-4] + "_"
        filename += msecs_from + "_to_" + msecs_to + "_"
        filename += self.code_av_dialog.file_['name'][-4:]
        filename = os.path.join(self.app.settings['directory'], filename)
        file_suffix = self.code_av_dialog.file_['mediapath'][-4:]
        filepath, ok = QtWidgets.QFileDialog.getSaveFileName(None,
                                                            _("Export segment"), filename, file_suffix)
        if filepath == "" or not ok:
            return
        if filepath[-4:].lower() != file_suffix.lower():
            filepath += file_suffix
        mediapath = ""
        try:
            if self.code_av_dialog.file_['mediapath'][0:6] in ('/audio', '/video'):
                mediapath = self.app.project_path + self.code_av_dialog.file_['mediapath']
            if self.code_av_dialog.file_['mediapath'][0:6] in ('audio:', 'video:'):
                mediapath = self.code_av_dialog.file_['mediapath'][6:]
        except Exception as e_:
            Message(self.app, _('Media not found'),
                    f"{e_}\n{self.app.project_path}{self.code_av_dialog.file_['mediapath']}",
                    "warning").exec()
            return
        ffmpeg_command = 'ffmpeg -i "' + mediapath + '" -ss '
        ffmpeg_command += str(self.segment['pos0'] / 1000)
        ffmpeg_command += ' -to '
        ffmpeg_command += str(self.segment['pos1'] / 1000)
        ffmpeg_command += ' -c copy "' + filepath + '"'
        print(f"FFMPEG COMMAND\n {ffmpeg_command}")
        try:
            subprocess.run(ffmpeg_command, timeout=15, shell=True)
            self.code_av_dialog.parent_textEdit.append(_("A/V segment exported: ") + filepath)
            Message(self.app, _("Segment exported"), filepath).exec()
        except Exception as e_:
            logger.error(str(e_))
            print(str(e_))
            Message(self.app, "ffmpeg error", str(e_)).exec()

    def set_coded_importance(self, important=True):
        """ Set or unset importance to self.segment.
        Importance is denoted using '1'
        params:
            important: boolean, default True """

        importance = None
        if important:
            importance = 1
        self.segment['important'] = importance
        cur = self.app.conn.cursor()
        sql = "update code_av set important=?, date=? where avid=?"
        values = [importance, datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), self.segment['avid']]
        cur.execute(sql, values)
        self.app.conn.commit()
        self.app.delete_backup = False
        self.code_av_dialog.get_coded_text_update_eventfilter_tooltips()
        self.set_segment_tooltip()

    def link_segment_to_text(self):
        """ Link segment to selected text """

        seg = {}
        cursor = self.code_av_dialog.ui.textEdit.textCursor()
        seg['pos0'] = cursor.selectionStart()
        seg['pos1'] = cursor.selectionEnd()
        seg['seltext'] = cursor.selectedText()
        self.segment['seltext'] = seg['seltext']
        seg['cid'] = self.segment['cid']
        seg['fid'] = self.code_av_dialog.transcription[0]
        seg['avid'] = self.segment['avid']
        seg['owner'] = self.app.settings['codername']
        seg['memo'] = ""
        seg['date'] = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        # Check for an existing duplicated text entry first
        cur = self.code_av_dialog.app.conn.cursor()
        cur.execute("select * from code_text where cid = ? and fid=? and pos0=? and pos1=? and owner=?",
                    (seg['cid'], seg['fid'], seg['pos0'], seg['pos1'], seg['owner']))
        result = cur.fetchall()
        if len(result) > 0:
            Message(self.app, _('Already Coded'), _("This segment has already been coded with this code."),
                    "warning").exec()
            return
        try:
            cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,\
            memo,date, avid) values(?,?,?,?,?,?,?,?,?)", (seg['cid'],
                                                          seg['fid'], seg['seltext'], seg['pos0'], seg['pos1'],
                                                          seg['owner'], seg['memo'], seg['date'], seg['avid']))
            self.code_av_dialog.app.conn.commit()
            self.app.delete_backup = False
        except Exception as e_:
            print(e_)
        self.code_av_dialog.text_for_segment = {'cid': None, 'fid': None, 'seltext': None, 'pos0': None, 'pos1': None,
                                                'owner': None, 'memo': None, 'date': None, 'avid': None}
        # Update codes and filter for tooltip
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
        self.code_av_dialog.ui.pushButton_play.setIcon(qta.icon('mdi6.pause'))
        self.code_av_dialog.play_segment_end = self.segment['pos1']
        self.code_av_dialog.timer.start()

    def delete(self):
        """ Mark the segment for deletion. Does not actually delete segment item, but hides
        it from the scene. Reload_segment is set to True, so on playing media, the update
        event will reload all segments. """

        # print(self.segment)
        ui = DialogConfirmDelete(self.app,
                                 _("Segment: ") + self.segment['codename'] + "\n" + _("Memo: ") + self.segment['memo'])
        ok = ui.exec()
        if not ok:
            return
        tmp_seg = deepcopy(self.segment)
        tmp_seg['is_segment'] = True  # Need to distinguish from text coding
        self.code_av_dialog.undo_deleted_codes = [tmp_seg]

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
        if self.app.settings['showids']:
            tooltip += f" [avid:{self.segment['avid']}]"
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

        self.scene_from_x = self.segment['pos0'] * self.scaler
        self.scene_to_x = self.segment['pos1'] * self.scaler
        self.scene_from_y = self.segment['y']
        self.scene_to_y = self.segment['y'] + 8
        line_width = 8
        color = QColor(self.segment['color'])
        self.setPen(QtGui.QPen(color, line_width, QtCore.Qt.PenStyle.SolidLine))
        self.setLine(self.scene_from_x, self.segment['y'], self.scene_to_x, self.segment['y'])


class DialogViewAV(QtWidgets.QDialog):
    """ View Audio and Video using VLC. View and edit displayed memo.
    Mouse events did not work when the vlc play is in this dialog.
    Mouse events do work with the vlc player in a separate modal dialog.
    Transcribing the text file can be done here also.

    Linked a/v have 'audio:' or 'video:' at start of mediapath
    """

    app = None
    label = None
    file_ = None
    abs_path = ""
    is_paused = False
    media_duration_text = ""
    displayframe = None
    ddialog = None
    instance = None
    mediaplayer = None
    media = None

    # Variables for searching through text
    search_indices = []  # A list of tuples of (text name, match.start, match length)
    search_index = 0

    # Variables used for editing the transcribed text file
    transcription = None
    time_positions = []
    speaker_list = []
    codetext = []
    annotations = []
    casetext = []
    prev_text = ""
    no_codes_annotes_cases = True
    code_deletions = []

    def __init__(self, app, file_, parent=None):

        """ file_ contains: {name, mediapath, owner, id, date, memo, fulltext}
        A separate modal dialog is created to display the video.
        """

        self.app = app
        self.file_ = file_
        self.search_indices = []
        self.search_index = 0
        self.abs_path = ""
        if self.file_['mediapath'][0:6] in ('/audio', '/video'):
            self.abs_path = self.app.project_path + self.file_['mediapath']
        if self.file_['mediapath'][0:6] in ('audio:', 'video:'):
            self.abs_path = self.file_['mediapath'][6:]
        self.is_paused = True
        self.time_positions = []
        self.speaker_list = []

        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_view_av()
        self.ui.setupUi(self)
        self.setWindowTitle(self.abs_path.split('/')[-1])
        try:
            x = int(self.app.settings['viewav_abs_pos_x'])
            y = int(self.app.settings['viewav_abs_pos_y'])
            self.move(self.mapToGlobal(QtCore.QPoint(x, y)))
        except KeyError:
            pass
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        if not vlc:
            return
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        font = f'font: {self.app.settings["treefontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.label_speakers.setStyleSheet(font)
        doc_font = f'font: {self.app.settings["docfontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.textEdit.setStyleSheet(doc_font)
        self.ui.label_note.setText(
            _("Transcription area: Ctrl+T (insert timestamp) Ctrl+N (new speaker) Ctrl+1-8 (select speaker) Ctrl+D (delete speaker)"))
        tt = _(
            "Avoid selecting sections of text with a combination of not underlined (not coded / annotated / case-assigned) and underlined (coded, annotated, case-assigned).")
        tt += _(
            "Positions of the underlying codes / annotations / case-assigned may not correctly adjust if text is typed over or deleted.")
        self.ui.label_note.setToolTip(tt)
        self.ui.textEdit.installEventFilter(self)
        self.installEventFilter(self)  # for rewind, play/stop
        if platform.system() in ("Windows", "Darwin"):
            self.get_waveform()  # Crashes on Fedora 40, segmentation fault with ffmpeg
        # Get the transcription text and fill textedit
        self.transcription = None
        cur = self.app.conn.cursor()
        if self.file_['av_text_id'] is not None:
            cur.execute("select id, fulltext, name from source where id=?", [file_['av_text_id']])
            self.transcription = cur.fetchone()
        if self.transcription is not None:
            self.ui.textEdit.setText(self.transcription[1])
            self.get_timestamps_from_transcription()
            # Commented out as auto-filling speaker names annoys users
            # self.get_speaker_names_from_bracketed_text()
            # self.add_speaker_names_to_label()
        if self.transcription is None:
            # Check if an existing matching text entry name is present, despite no linkage to av source
            name = file_['name'] + ".txt"
            name2 = file_['name'] + ".transcribed"
            cur.execute("select id from source where name=? or name=?", [name, name2])
            res = cur.fetchone()
            tr_id = None
            if res is not None:
                # Recreate link from av entry to existing text entry
                cur.execute("update source set av_text_id=? where id=?", [res[0], self.file_['id']])
                self.app.conn.commit()
                tr_id = res[0]
            if res is None:
                cur.execute("insert into source(name,fulltext,mediapath,memo,owner,date) values(?,?,?,?,?,?)",
                            (file_['name'] + ".txt", "", None, "", self.app.settings['codername'],
                             datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                self.app.conn.commit()
                cur.execute("select last_insert_rowid()")
                tr_id = cur.fetchone()[0]
                self.file_['av_text_id'] = tr_id
                # print("tr_id", tr_id, "file id", self.file_['id'])
                cur.execute("update source set av_text_id=? where id=?", [tr_id, self.file_['id']])
                try:
                    # Called twice, and raises and error: 'sqlite3.Connection' object has no attribute 'commit'
                    self.app.conn.conmmit()
                except Exception as e_:
                    print(e_)
            cur.execute("select id, fulltext, name from source where id=?", [tr_id])
            self.transcription = cur.fetchone()
        self.get_cases_codings_annotations()
        self.text = self.transcription[1]
        self.ui.textEdit.setPlainText(self.text)
        self.prev_text = copy(self.text)
        self.highlight()

        self.ui.label_time_3.setPixmap(qta.icon('mdi6.clock-outline').pixmap(22, 22))
        self.ui.label_volume.setPixmap(qta.icon('mdi6.volume-high').pixmap(22, 22))
        self.ui.pushButton_play.setIcon(qta.icon('mdi6.play', options=[{'scale_factor': 1.4}]))
        self.ui.pushButton_rewind_30.setIcon(qta.icon('mdi6.rewind-30'))
        self.ui.pushButton_rewind_30.pressed.connect(self.rewind_30_seconds)
        self.ui.pushButton_rewind_5.setIcon(qta.icon('mdi6.rewind-5'))
        self.ui.pushButton_rewind_5.pressed.connect(self.rewind_5_seconds)
        self.ui.pushButton_forward_30.setIcon(qta.icon('mdi6.fast-forward-30'))
        self.ui.pushButton_forward_30.pressed.connect(self.forward_30_seconds)
        self.ui.pushButton_rate_down.setIcon(qta.icon('mdi6.speedometer-slow'))
        self.ui.pushButton_rate_down.pressed.connect(self.decrease_play_rate)
        self.ui.pushButton_rate_up.setIcon(qta.icon('mdi6.speedometer'))
        self.ui.pushButton_rate_up.pressed.connect(self.increase_play_rate)
        # Search text in transcription
        self.ui.label_search_regex.setPixmap(qta.icon('mdi6.text-search').pixmap(22, 22))
        self.ui.pushButton_previous.setIcon(qta.icon('mdi6.arrow-left'))
        self.ui.pushButton_previous.setEnabled(False)
        self.ui.pushButton_previous.pressed.connect(self.move_to_previous_search_text)
        self.ui.pushButton_help.setIcon(qta.icon('mdi6.help'))
        self.ui.pushButton_help.pressed.connect(self.help)
        self.ui.pushButton_next.setIcon(qta.icon('mdi6.arrow-right'))
        self.ui.pushButton_next.pressed.connect(self.move_to_next_search_text)
        self.ui.pushButton_next.setEnabled(False)
        self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
        # Transcription buttons
        self.ui.pushButton_new_speaker.setIcon(qta.icon('mdi6.account-plus-outline'))
        self.ui.pushButton_new_speaker.setToolTip("Ctrl+N")
        self.ui.pushButton_new_speaker.pressed.connect(self.add_speakername)
        self.ui.pushButton_remove_speaker.setIcon(qta.icon('mdi6.account-minus-outline'))
        self.ui.pushButton_remove_speaker.setToolTip("Ctrl+D")
        self.ui.pushButton_remove_speaker.pressed.connect(self.delete_speakernames)
        self.ui.pushButton_insert_timestamp.setIcon(qta.icon('mdi6.clock-outline'))
        self.ui.pushButton_insert_timestamp.setToolTip("Ctrl+T")
        self.ui.pushButton_insert_timestamp.pressed.connect(self.insert_timestamp)

        # My solution to getting gui mouse events by putting vlc video in another dialog
        self.ddialog = QtWidgets.QDialog()
        # Enable custom window hint - must be set to enable customizing window controls
        self.ddialog.setWindowFlags(self.ddialog.windowFlags() | QtCore.Qt.WindowType.CustomizeWindowHint)
        # Disable close button, only close through closing the Ui_Dialog_view_av
        self.ddialog.setWindowFlags(self.ddialog.windowFlags() & ~QtCore.Qt.WindowType.WindowCloseButtonHint)
        self.ddialog.setWindowFlags(self.ddialog.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        title = self.abs_path.split('/')[-1]
        self.ddialog.setWindowTitle(title)
        self.ddialog.gridLayout = QtWidgets.QGridLayout(self.ddialog)
        # NOT using QVideoWidget - too difficult to use
        self.ddialog.dframe = QtWidgets.QFrame(self.ddialog)
        self.ddialog.dframe.setObjectName("frame")
        self.palette = self.ddialog.dframe.palette()
        self.palette.setColor(QtGui.QPalette.ColorRole.Window, QColor(30, 30, 30))
        self.ddialog.dframe.setPalette(self.palette)
        self.ddialog.dframe.setAutoFillBackground(True)
        self.ddialog.gridLayout.addWidget(self.ddialog.dframe, 0, 0, 0, 0)
        # add context menu for ddialog
        self.ddialog.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ddialog.customContextMenuRequested.connect(self.ddialog_menu)
        # Set video dialog position, with a default initial position
        self.ddialog.move(self.mapToGlobal(QtCore.QPoint(40, 20)))
        # ddialog is relative to self global position
        try:
            x = int(self.app.settings['viewav_video_pos_x']) - int(self.app.settings['viewav_abs_pos_x'])
            y = int(self.app.settings['viewav_video_pos_y']) - int(self.app.settings['viewav_abs_pos_y'])
            self.ddialog.move(self.mapToGlobal(QtCore.QPoint(x, y)))
        except KeyError:
            pass
        if self.file_['mediapath'][0:6] not in ("/audio", "audio:"):
            self.ddialog.show()
        # Create a vlc instance
        # Fix an Ubuntu error but, makes no difference self.instance = vlc.Instance("--no-xlib")
        # Fedora 39 NameError: no function 'libvlc_new'
        try:
            self.instance = vlc.Instance()
        except NameError as name_err:
            logger.error(f"{name_err}")
            msg = f"{name_err}"
            Message(self.app, _("QualCoder will crash") + " " * 20, msg).exec()
        # Ubuntu 22.04 hide - self.ddialog.hide() as vlc is not inside dialog
        # Create an empty vlc media player
        self.mediaplayer = self.instance.media_player_new()
        self.mediaplayer.video_set_mouse_input(False)
        self.mediaplayer.video_set_key_input(False)
        # self.mediaplayer.set_hwnd(int(self.ddialog.dframe.winId())) # Does not work as is, but above code works without anyway
        self.ui.pushButton_play.clicked.connect(self.play_pause)
        self.ui.horizontalSlider_vol.valueChanged.connect(self.set_volume)
        self.ui.comboBox_tracks.currentIndexChanged.connect(self.audio_track_changed)
        self.ui.horizontalSlider.setTickPosition(QtWidgets.QSlider.TickPosition.NoTicks)
        self.ui.horizontalSlider.setMouseTracking(True)
        self.ui.horizontalSlider.sliderMoved.connect(self.set_position)
        try:
            self.media = self.instance.media_new(self.abs_path)
        except Exception as e_:
            Message(self.app, _('Media not found'), f"{e_}\n{self.abs_path}").exec()
            self.closeEvent()
            return
        if self.file_['mediapath'][0:7] not in ("/audio", "audio:"):
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
        # Put the media in the media player
        self.mediaplayer.set_media(self.media)
        # Parse the metadata of the file
        self.media.parse()
        self.mediaplayer.video_set_mouse_input(False)
        self.mediaplayer.video_set_key_input(False)
        # Did not use QVideoWidget - tried and did not work well
        # The media player has to be connected to the QFrame (otherwise the
        # video would be displayed in it's own window). This is platform
        # specific, so we must give the ID of the QFrame (or similar object) to
        # vlc. Different platforms have different functions for this
        if platform.system() == "Linux":  # for Linux using the X Server
            self.mediaplayer.set_xwindow(int(self.ddialog.dframe.winId()))
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
        self.ui.checkBox_scroll_transcript.stateChanged.connect(self.scroll_transcribed_checkbox_changed)
        # Need this for helping set the slider if user sliding before play begins
        # Detect number of audio tracks in media
        self.mediaplayer.play()
        self.mediaplayer.audio_set_volume(0)
        time.sleep(0.2)
        # print( self.mediaplayer.audio_get_track_count()) # > 0
        tracks = self.mediaplayer.audio_get_track_description()
        good_tracks = []  # note where track [0] == -1 is a disabled track
        for track in tracks:
            if track[0] >= 0:
                good_tracks.append(track)
            # print(track[0], track[1])  # track number and track name
        if len(good_tracks) < 2:
            self.ui.label_audio.setEnabled(False)
            self.ui.comboBox_tracks.setEnabled(False)
        self.mediaplayer.stop()
        self.mediaplayer.audio_set_volume(100)

    def get_waveform(self):
        """ Create waveform image in the audio folder. Apply image to label_waveform.
        If a video file has multiple tracks only the first one is used for this method.
        https://ffmpeg.org/ffmpeg-filters.html
        Requires installed ffmpeg
        ffmpeg is much slower on Windows han Ubuntu """

        waveform_path = os.path.join(self.app.project_path, "audio", "waveform.png")
        if os.path.exists(waveform_path):
            os.remove(waveform_path)
        wf_command = f'ffmpeg -i "{self.abs_path}" -filter_complex'
        wf_command += ' "aformat=channel_layouts=mono,showwavespic=s=1020x100'
        if self.app.settings['stylesheet'] in ("dark", "rainbow"):
            wf_command += ':colors=#f89407"'
        else:
            wf_command += ':colors=#0A0A0A"'
        wf_command += ' -frames:v 1'
        wf_command += f' "{waveform_path}"'
        try:
            subprocess.run(wf_command, timeout=15, shell=True)
        except Exception as e_:
            logger.error(str(e_))
            print(str(e_))
            Message(self.app, "ffmpeg error", str(e_))
        '''# https://www.cloudacm.com/?p=3105
        spectrogram_path = self.app.project_path + "/audio/spectrogram.png"
        if os.path.exists(spectrogram_path):
            os.remove(spectrogram_path)
        sp_command = 'ffmpeg -i "' + self.abs_path + '"'
        sp_command += ' -lavfi showspectrumpic=s=1020x200:legend=disabled'
        sp_command += ' "' + spectrogram_path + '"'
        try:
            subprocess.run(sp_command, timeout=15, shell=True)
        except Exception as e_:
            logger.error(str(e_))
            Message(self.app, "ffmpeg error", str(e_))
            print(str(e_))
            #return'''
        if not os.path.exists(waveform_path):
            self.ui.label_waveform.hide()
            return
        pm = QtGui.QPixmap()
        pm.load(waveform_path)
        self.ui.label_waveform.setPixmap(QtGui.QPixmap(pm).scaled(1020, 60))

    def get_cases_codings_annotations(self):
        """ Get all linked cases, coded text and annotations for this file """

        cur = self.app.conn.cursor()
        sql = "select ctid, cid, pos0, pos1, seltext, owner from code_text where fid=?"
        cur.execute(sql, [self.transcription[0]])
        res = cur.fetchall()
        self.codetext = []
        for r in res:
            self.codetext.append({'ctid': r[0], 'cid': r[1], 'pos0': r[2], 'pos1': r[3], 'seltext': r[4],
                                  'owner': r[5], 'npos0': r[2], 'npos1': r[3]})
        sql = "select anid, pos0, pos1 from annotation where fid=?"
        cur.execute(sql, [self.transcription[0]])
        res = cur.fetchall()
        self.annotations = []
        for r in res:
            self.annotations.append({'anid': r[0], 'pos0': r[1], 'pos1': r[2],
                                     'npos0': r[1], 'npos1': r[2]})
        sql = "select id, pos0, pos1 from case_text where fid=?"
        cur.execute(sql, [self.transcription[0]])
        res = cur.fetchall()
        self.casetext = []
        for r in res:
            self.casetext.append({'id': r[0], 'pos0': r[1], 'pos1': r[2],
                                  'npos0': r[1], 'npos1': r[2]})
        self.no_codes_annotes_cases = True
        if len(self.codetext) > 0 or len(self.annotations) > 0 or len(self.casetext) > 0:
            self.no_codes_annotes_cases = False

    ''' Problem with pydub pyaudioop module
    def speech_to_text(self):
        """ Convert speech to text using online service. """

        ui = SpeechToText(self.app, self.abs_path)
        ok = ui.exec()
        if not ok:
            return
        txt = ui.text
        self.ui.textEdit.setText(txt)'''

    @staticmethod
    def help():
        """ Open help for transcribe section in browser. """

        url = "https://github.com/ccbogel/QualCoder/wiki/3.2.-Files"
        webbrowser.open(url)

    def ddialog_menu(self, position):
        """ Context menu to export a screenshot, to resize dialog """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_screenshot = menu.addAction(_("Screenshot"))
        action_resize = menu.addAction(_("Resize"))

        action = menu.exec(self.ddialog.mapToGlobal(position))
        if action == action_screenshot:
            time.sleep(0.5)
            screen = QtWidgets.QApplication.primaryScreen()
            screenshot = screen.grabWindow(self.ddialog.winId())
            screenshot.save(self.app.settings['directory'] + '/Frame_' + datetime.datetime.now().astimezone().strftime(
                "%Y%m%d_%H_%M_%S") + '.jpg', 'jpg')
        if action == action_resize:
            w = self.ddialog.size().width()
            h = self.ddialog.size().height()
            res_w = QtWidgets.QInputDialog.getInt(self, _("Width"), _("Width:"), w, 100, 2000, 5)
            if res_w[1]:
                w = res_w[0]
            res_h = QtWidgets.QInputDialog.getInt(self, _("Height"), _("Height:"), h, 80, 2000, 5)
            if res_h[1]:
                h = res_h[0]
            self.ddialog.resize(w, h)

    def set_position(self):
        """ Set the a/v position according to the slider position.
        The vlc MediaPlayer needs a float value between 0 and 1, Qt uses
        integer variables, so you need a factor; the higher the factor, the
        more precise are the results (1000 should suffice).
        """

        self.ui.horizontalSlider.blockSignals(True)
        pos = self.ui.horizontalSlider.value()
        msecs = self.mediaplayer.get_time()
        self.mediaplayer.set_position(pos / 1000.0)
        self.ui.label_time.setText(msecs_to_hours_mins_secs(msecs) + self.media_duration_text)
        self.ui.horizontalSlider.blockSignals(False)

    def eventFilter(self, object_, event):
        """ Add key options to improve manual transcribing.
        Options are:
            Alt + minus to rewind 30 seconds.
            Ctrl + R rewind 5 seconds
            Alt + plus forward 30 seconds
            Ctrl + S OR ctrl + P to start/pause On start rewind 1 second
            Ctrl + T to insert timestamp in format [hh.mm.ss]
            Ctrl + N to enter a new speakers name into shortcuts
            Ctrl + D to delete speaker names from shortcuts
            Ctrl + 1 .. 8 to insert speaker in format [speaker name]
            Ctrl + Shift + > to increase play rate
            Ctrl + Shift + < to decrease play rate
        """

        if event.type() != 7:  # QtGui.QKeyEvent
            return False
        key = event.key()
        mods = event.modifiers()
        # print("KEY ", key, "MODS ", mods)
        #  ctrl S or ctrl P pause/play toggle
        if (key == QtCore.Qt.Key.Key_S or key == QtCore.Qt.Key.Key_P) and \
                mods == QtCore.Qt.KeyboardModifier.ControlModifier:
            self.play_pause()
        # Rewind 5 seconds   Ctrl + R
        if key == QtCore.Qt.Key.Key_R and mods == QtCore.Qt.KeyboardModifier.ControlModifier:
            self.rewind_5_seconds()
        # Forward 5 seconds   5
        if key == QtCore.Qt.Key.Key_5 and not self.ui.textEdit.hasFocus():
            self.forward_5_seconds()
        # Rewind 30 seconds Alt minus
        if key == QtCore.Qt.Key.Key_Minus and mods == QtCore.Qt.KeyboardModifier.AltModifier:
            self.rewind_30_seconds()
        # Advance 30 seconds Alt plus
        if key == QtCore.Qt.Key.Key_Plus and mods & QtCore.Qt.KeyboardModifier.AltModifier:
            self.forward_30_seconds()
        #  Insert  timestamp Ctrl T
        if key == QtCore.Qt.Key.Key_T and mods == QtCore.Qt.KeyboardModifier.ControlModifier:
            self.insert_timestamp()
        # Insert speaker  Ctrl 1 .. 8
        if key in range(49, 57) and mods == QtCore.Qt.KeyboardModifier.ControlModifier:
            self.insert_speakername(key)
        # Add new speaker to list  Ctrl n
        if key == QtCore.Qt.Key.Key_N and mods == QtCore.Qt.KeyboardModifier.ControlModifier:
            self.pause()
            self.add_speakername()
        # Delete speaker name(s) from list
        if key == QtCore.Qt.Key.Key_D and mods == QtCore.Qt.KeyboardModifier.ControlModifier:
            self.pause()
            self.delete_speakernames()
        # Increase play rate  Ctrl + Shift + >
        if key == QtCore.Qt.Key.Key_Greater and (mods and QtCore.Qt.KeyboardModifier.ShiftModifier) and \
                (mods and QtCore.Qt.KeyboardModifier.ControlModifier):
            self.increase_play_rate()
        # Decrease play rate  Ctrl + Shift + <
        if key == QtCore.Qt.Key.Key_Less and (mods and QtCore.Qt.KeyboardModifier.ShiftModifier) and \
                (mods and QtCore.Qt.KeyboardModifier.ControlModifier):
            self.decrease_play_rate()
        return True

    def rewind_30_seconds(self):
        """ Rewind 30 seconds. Alt + R """

        time_msecs = self.mediaplayer.get_time() - 30000
        if time_msecs < 0:
            time_msecs = 0
        pos = time_msecs / self.mediaplayer.get_media().get_duration()
        self.mediaplayer.set_position(pos)
        # Update timer display
        msecs = self.mediaplayer.get_time()
        self.ui.label_time.setText(msecs_to_hours_mins_secs(msecs))
        self.update_ui()

    def rewind_5_seconds(self):
        """ Rewind 5 seconds. Ctrl + R """

        time_msecs = self.mediaplayer.get_time() - 5000
        if time_msecs < 0:
            time_msecs = 0
        pos = time_msecs / self.mediaplayer.get_media().get_duration()
        self.mediaplayer.set_position(pos)
        # Update timer display
        msecs = self.mediaplayer.get_time()
        self.ui.label_time.setText(msecs_to_hours_mins_secs(msecs))
        self.update_ui()

    def forward_30_seconds(self):
        """ Forward 30 seconds. Alt + F """

        time_msecs = self.mediaplayer.get_time() + 30000
        if time_msecs > self.media.get_duration():
            time_msecs = self.media.get_duration() - 1
        pos = time_msecs / self.mediaplayer.get_media().get_duration()
        self.mediaplayer.set_position(pos)
        # Update timer display
        msecs = self.mediaplayer.get_time()
        self.ui.label_time.setText(msecs_to_hours_mins_secs(msecs))
        self.update_ui()

    def forward_5_seconds(self):
        """ Forward 5 seconds. 5 """

        time_msecs = self.mediaplayer.get_time() + 5000
        if time_msecs > self.media.get_duration():
            time_msecs = self.media.get_duration() - 1
        pos = time_msecs / self.mediaplayer.get_media().get_duration()
        self.mediaplayer.set_position(pos)
        # Update timer display
        msecs = self.mediaplayer.get_time()
        self.ui.label_time.setText(msecs_to_hours_mins_secs(msecs))
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

    def delete_speakernames(self):
        """ Delete speakername from list of shortcut names """

        if not self.speaker_list:
            return
        # convert to list of dictionaries
        names = []
        for n in self.speaker_list:
            names.append({"name": n})
        if not names:
            return
        ui = DialogSelectItems(self.app, names, _("Select name to delete"), "many")
        ok = ui.exec()
        if not ok:
            return
        names = ui.get_selected()
        if not names:
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
        d.setWindowFlags(d.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        d.setWindowTitle(_("Speaker name"))
        d.setLabelText(_("Name:"))
        d.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        if d.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            name = d.textValue()
            if name == "" or name.find('.') == 0 or name.find(':') == 0 or name.find('[') == 0 or name.find(
                    ']') == 0 or name.find('{') == 0 or name.find('}') == 0:
                return
            self.speaker_list.append(name)
            self.add_speaker_names_to_label()

    def insert_speakername(self, key):
        """ Insert speaker name using settings format of {} or []
        param:
            key: """

        list_pos = key - 49
        speaker = ""
        try:
            speaker = self.speaker_list[list_pos]
        except IndexError:
            return False
        if self.app.settings['speakernameformat'] == "[]":
            speaker = '[' + speaker + ']'
        else:
            speaker = '{' + speaker + '}'
        self.ui.textEdit.insertPlainText(speaker)

    def insert_timestamp(self):
        """ Insert timestamp using current format.
        Format options:
        [mm.ss], [mm:ss], [hh.mm.ss], [hh:mm:ss],
        {hh.mm.ss}, #hh:mm:ss.sss#
        """

        fmt = self.app.settings['timestampformat']
        time_msecs = self.mediaplayer.get_time()
        hours_mins_secs = msecs_to_hours_mins_secs(time_msecs)  # Returns a String  hh.mm.ss
        hours, mins, secs = hours_mins_secs.split('.')
        total_mins = int(hours) * 60 + int(mins)
        ts = "\n"
        if fmt == "[mm.ss]":
            ts += f'[{total_mins}.{secs}]'
        if fmt == "[mm:ss]":
            ts += f'[{total_mins}:{secs}]'
        if fmt == "[hh.mm.ss]":
            ts += f'[{hours}.{mins}.{secs}]'
        if fmt == "[hh:mm:ss]":
            ts += f'[{hours}:{mins}:{secs}]'
        if fmt == "{hh:mm:ss}":
            ts += f'{{{hours}:{mins}:{secs}}}'
        if fmt == "#hh:mm:ss.sss#":
            msecs = "000"
            tms_str = str(time_msecs)
            if len(tms_str) > 2:
                msecs = tms_str[-3:]
            ts += f'#{hours}:{mins}:{secs}.{msecs}#'
        self.ui.textEdit.insertPlainText(f"\n{ts} ")
        # Code here makes the current text location visible on the textEdit pane
        text_cursor = self.ui.textEdit.textCursor()
        pos = text_cursor.position()
        text_cursor.setPosition(pos)
        self.ui.textEdit.setTextCursor(text_cursor)

    def add_speaker_names_to_label(self):
        """ Add speaker names to label, four on each line.
        Called by init, delete_speakernames, add_speakernames """

        txt = ""
        for i, n in enumerate(self.speaker_list):
            if i == 4:
                txt += "\n"
            txt += f"{i + 1}: {n}  "
        self.ui.label_speakers.setText(txt)

    def scroll_transcribed_checkbox_changed(self):
        """ If checked, then cannot edit the textEdit_transcribed. """

        if self.ui.checkBox_scroll_transcript.isChecked():
            self.ui.textEdit.setReadOnly(True)
        else:
            # Redo timestamps as text may have been changed by user
            self.get_timestamps_from_transcription()
            self.ui.textEdit.setReadOnly(False)

    def get_timestamps_from_transcription(self):
        """ Get a list of starting/ending characterpositions and time in milliseconds
        from transcribed text file.

        Example formats:  [00:34:12] [45:33] [01.23.45] [02.34] {00.34.20}
        #00:12:34.567#
        09:33:04,100 --> 09:33:09,600

        Converts hh mm ss to milliseconds with text positions stored in a list
        The list contains lists of [text_pos0, text_pos1, milliseconds] """

        mmss1 = r"\[[0-9]?[0-9]:[0-9][0-9]\]"
        hhmmss1 = r"\[[0-9][0-9]:[0-9][0-9]:[0-9][0-9]\]"
        mmss2 = r"\[[0-9]?[0-9]\.[0-9][0-9]\]"
        hhmmss2 = r"\[[0-9][0-9]\.[0-9][0-9]\.[0-9][0-9]\]"
        hhmmss3 = r"\{[0-9][0-9]\:[0-9][0-9]\:[0-9][0-9]\}"
        hhmmss_sss = r"#[0-9][0-9]:[0-9][0-9]:[0-9][0-9]\.[0-9][0-9][0-9]#"
        srt = r"[0-9][0-9]:[0-9][0-9]:[0-9][0-9],[0-9][0-9][0-9]\s-->\s[0-9][0-9]:[0-9][0-9]:[0-9][0-9],[0-9][0-9][0-9]"

        transcription = self.ui.textEdit.toPlainText()
        self.time_positions = []
        for match in re.finditer(mmss1, transcription):
            stamp = match.group()[1:-1]
            s = stamp.split(':')
            try:
                msecs = (int(s[0]) * 60 + int(s[1])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except IndexError:
                pass
        for match in re.finditer(hhmmss1, transcription):
            stamp = match.group()[1:-1]
            s = stamp.split(':')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s[2])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except IndexError:
                pass
        for match in re.finditer(mmss2, transcription):
            stamp = match.group()[1:-1]
            s = stamp.split('.')
            try:
                msecs = (int(s[0]) * 60 + int(s[1])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except IndexError:
                pass
        for match in re.finditer(hhmmss2, transcription):
            stamp = match.group()[1:-1]
            s = stamp.split('.')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s[2])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except IndexError:
                pass
        for match in re.finditer(hhmmss3, transcription):
            stamp = match.group()[1:-1]
            s = stamp.split('.')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s[2])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except IndexError:
                pass
        for match in re.finditer(hhmmss_sss, transcription):
            # Format #00:12:34.567#
            stamp = match.group()[1:-1]
            s = stamp.split(':')
            s2 = s[2].split('.')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s2[0])) * 1000 + int(s2[1])
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except IndexError:
                pass
        for match in re.finditer(srt, transcription):
            # Format 09:33:04,100 --> 09:33:09,600  skip the arrow and second time position
            stamp = match.group()[0:12]
            s = stamp.split(':')
            s2 = s[2].split(',')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s2[0])) * 1000 + int(s2[1])
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except IndexError:
                pass

    def audio_track_changed(self):
        """ Audio track changed.
        The video needs to be playing/paused before the combobox is filled with track options.
        The combobox only has positive integers."""

        txt = self.ui.comboBox_tracks.currentText()
        if txt == "":
            txt = 1
        success = self.mediaplayer.audio_set_track(int(txt))

    def play_pause(self):
        """ Toggle play or pause status. """

        # user might update window positions and sizes, need to detect it
        self.update_sizes()
        if self.mediaplayer.is_playing():
            self.mediaplayer.pause()
            self.ui.pushButton_play.setIcon(qta.icon('mdi6.play', options=[{'scale_factor': 1.4}]))
            self.is_paused = True
            self.timer.stop()
        else:
            if self.mediaplayer.play() == -1:
                return

            # On play rewind slightly
            time_msecs = self.mediaplayer.get_time() - 100
            if time_msecs < 0:
                time_msecs = 0
            pos = time_msecs / self.mediaplayer.get_media().get_duration()
            self.mediaplayer.set_position(pos)
            # Update timer display
            msecs = self.mediaplayer.get_time()
            self.ui.label_time.setText(msecs_to_hours_mins_secs(msecs) + self.media_duration_text)
            self.mediaplayer.play()
            self.ui.pushButton_play.setIcon(qta.icon('mdi6.pause'))
            self.timer.start()
            self.is_paused = False

    def pause(self):
        """ Pause any playback. Called when entering a new speakers name
        during manual transcription. """

        if self.mediaplayer.is_playing():
            self.mediaplayer.pause()
            self.ui.pushButton_play.setIcon(qta.icon('mdi6.play', options=[{'scale_factor': 1.4}]))
            self.is_paused = True
            self.timer.stop()

    def stop(self):
        """ Stop vlc player. Set position slider to the start.
         If multiple audio tracks are shown in the combobox, set the audio track to the first index.
         This is because when beginning play again, the audio track reverts to the first track.
         Programmatically setting the audio track to other values does not work. """

        self.mediaplayer.stop()
        self.ui.pushButton_play.setIcon(qta.icon('mdi6.play', options=[{'scale_factor': 1.4}]))
        self.ui.horizontalSlider.setProperty("value", 0)
        # Set combobox display of audio track to the first one, or leave it blank if it contains no items
        if self.ui.comboBox_tracks.count() > 0:
            self.ui.comboBox_tracks.setCurrentIndex(0)

    def set_volume(self, volume):
        """ Set the volume. The slider ranges from 0 to 100."""

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
        self.ui.label_time.setText(msecs_to_hours_mins_secs(msecs) + self.media_duration_text)

        """ For long transcripts, update the relevant text position in the textEdit to match the
        video's current position.
        time_position list itme: [text_pos0, text_pos1, milliseconds]
        """
        if self.ui.checkBox_scroll_transcript.isChecked() and self.transcription is not None and \
                self.ui.textEdit.toPlainText() != "":
            for i in range(1, len(self.time_positions)):
                if self.time_positions[i - 1][2] < msecs < self.time_positions[i][2]:
                    text_pos = self.time_positions[i][0]
                    text_cursor = self.ui.textEdit.textCursor()
                    text_cursor.setPosition(text_pos)
                    self.ui.textEdit.setTextCursor(text_cursor)
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
        Record the dialog and video dialog0 size and positions. """

        self.update_sizes()
        self.ddialog.close()
        self.stop()
        cur = self.app.conn.cursor()
        if self.transcription is not None:
            txt = self.ui.textEdit.toPlainText()
            # self.transcription[0] is file id, [1] is the original text
            if txt != self.transcription[1]:
                date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cur.execute("update source set fulltext=?, date=? where id=?", [txt, date, self.transcription[0]])
                self.app.conn.commit()
                # update transcript in vectorstore
                if self.app.settings['ai_enable'] == 'True': 
                    name = self.transcription[2]
                    self.app.ai.sources_vectorstore.import_document(self.transcription[0], name, txt)
        self.app.delete_backup = False

    def update_sizes(self):
        """ Called by play/pause and close event """

        if self.file_['mediapath'][0:7] != "/audio/" and self.file_['mediapath'][0:6] != "audio:":
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
        self.app.settings['viewav_abs_pos_x'] = self.pos().x()
        self.app.settings['viewav_abs_pos_y'] = self.pos().y()

    # Functions to search though the transcription text
    def search_for_text(self):
        """ On text changed in lineEdit_search, find indices of matching text.
        Only where text is three or more characters long.
        Resets current search_index.
        NOT IMPLEMENTED If case sensitive is checked then text searched is matched for case sensitivity.
        """

        if not self.search_indices:
            self.ui.pushButton_next.setEnabled(False)
            self.ui.pushButton_previous.setEnabled(False)
        self.search_indices = []
        self.search_index = -1
        search_term = self.ui.lineEdit_search.text()
        self.ui.label_search_totals.setText("0 / 0")
        if len(search_term) < 3:
            return
        pattern = None
        flags = 0
        '''if not self.ui.checkBox_search_case.isChecked():
            flags |= re.IGNORECASE'''
        try:
            pattern = re.compile(search_term, flags)
        except Exception as e_:
            logger.warning('Bad escape\n' + str(e_))
        if pattern is None:
            return
        self.search_indices = []

        txt = self.ui.textEdit.toPlainText()
        try:
            for match in pattern.finditer(txt):
                # Get result as first dictionary item
                self.search_indices.append((match.start(), len(match.group(0))))
        except Exception as e_:
            print(e_)
            logger.exception('Failed searching transcription text for %s', search_term)

        if len(self.search_indices) > 0:
            self.ui.pushButton_next.setEnabled(True)
            self.ui.pushButton_previous.setEnabled(True)
        self.ui.label_search_totals.setText("0 / " + str(len(self.search_indices)))

    def move_to_previous_search_text(self):
        """ Push button pressed to move to previous search text position. """

        if not self.search_indices:
            return
        self.search_index -= 1
        if self.search_index < 0:
            self.search_index = len(self.search_indices) - 1
        cursor = self.ui.textEdit.textCursor()
        prev_result = self.search_indices[self.search_index]
        # prev_result is a tuple containing: char position and search string length
        cursor.setPosition(prev_result[0])
        cursor.setPosition(cursor.position() + prev_result[1], QtGui.QTextCursor.MoveMode.KeepAnchor)
        self.ui.textEdit.setTextCursor(cursor)
        self.ui.label_search_totals.setText(str(self.search_index + 1) + " / " + str(len(self.search_indices)))

    def move_to_next_search_text(self):
        """ Push button pressed to move to next search text position. """

        if not self.search_indices:
            return
        self.search_index += 1
        if self.search_index == len(self.search_indices):
            self.search_index = 0
        cursor = self.ui.textEdit.textCursor()
        next_result = self.search_indices[self.search_index]
        # next_result is a tuple containing: char position and search string length
        cursor.setPosition(next_result[0])
        cursor.setPosition(cursor.position() + next_result[1], QtGui.QTextCursor.MoveMode.KeepAnchor)
        self.ui.textEdit.setTextCursor(cursor)
        self.ui.label_search_totals.setText(str(self.search_index + 1) + " / " + str(len(self.search_indices)))

    # Text edit editing and formatting functions
    def update_positions(self):
        """ Update positions for code text, annotations and case text as each character changes
        via adding or deleting.

        Output: adding an e at pos 4:
        ---

        +++

        @@ -4,0 +5 @@

        +e
        """

        # No need to update positions (unless entire file is a case)
        if self.no_codes_annotes_cases:
            return
        # cursor = self.ui.textEdit.textCursor()
        self.text = self.ui.textEdit.toPlainText()
        # print("cursor", cursor.position())
        # for d in difflib.unified_diff(self.prev_text, self.text):
        # n is how many context lines to show
        d = list(difflib.unified_diff(self.prev_text, self.text, n=0))
        if len(d) < 4:
            return
        char = d[3]
        position = d[2][4:]  # Removes prefix @@ -
        position = position[:-4]  # Removes suffix space@@\n
        previous = position.split(" ")[0]
        pre_start = int(previous.split(",")[0])
        pre_chars = None
        try:
            pre_chars = previous.split(",")[1]
        except IndexError:
            pass
        post = position.split(" ")[1]
        post_start = int(post.split(",")[0])
        post_chars = None
        try:
            post_chars = post.split(",")[1]
        except IndexError:
            pass
        # print(char, " previous", pre_start, pre_chars, " post", post_start, post_chars)
        """
        Replacing 'way' with 'the' start position 13
        -w  previous 13 3  post 13 3

        Replacing 's' with 'T'  (highlight s and replace with T
        -s  previous 4 None  post 4 None
        """
        # No additions or deletions
        if pre_start == post_start and pre_chars == post_chars:
            self.highlight()
            self.prev_text = copy(self.text)
            return
        """
        Adding 'X' at inserted position 5, note: None as no number is provided from difflib
        +X  previous 4 0  post 5 None

        Adding 'qda' at inserted position 5 (After 'This')
        +q  previous 4 0  post 5 3

        Removing 'X' from position 5, note None
        -X  previous 5 None  post 4 0

        Removing 'the' from position 13
        -t  previous 13 3  post 12 0
        """
        if pre_chars is None:
            pre_chars = 1
        pre_chars = -1 * int(pre_chars)  # String if not None
        if post_chars is None:
            post_chars = 1
        post_chars = int(post_chars)  # String if not None
        # print("XXX", char, " previous", pre_start, pre_chars, " post", post_start, post_chars)
        # Adding characters
        if char[0] == "+":
            for c in self.codetext:
                changed = False
                if c['npos0'] is not None and c['npos0'] >= pre_start and c['npos0'] >= pre_start + -1 * pre_chars:
                    c['npos0'] += pre_chars + post_chars
                    c['npos1'] += pre_chars + post_chars
                    changed = True
                if c['npos0'] is not None and not changed and c['npos0'] < pre_start < c['npos1']:
                    c['npos1'] += pre_chars + post_chars
            for c in self.annotations:
                changed = False
                if c['npos0'] is not None and c['npos0'] >= pre_start and c['npos0'] >= pre_start + -1 * pre_chars:
                    c['npos0'] += pre_chars + post_chars
                    c['npos1'] += pre_chars + post_chars
                    changed = True
                if not changed and c['npos0'] < pre_start < c['npos1']:
                    c['npos1'] += pre_chars + post_chars
            for c in self.casetext:
                changed = False
                if c['npos0'] is not None and c['npos0'] >= pre_start and c['npos0'] >= pre_start + -1 * pre_chars:
                    c['npos0'] += pre_chars + post_chars
                    c['npos1'] += pre_chars + post_chars
                    changed = True
                if c['npos0'] is not None and not changed and c['npos0'] < pre_start < c['npos1']:
                    c['npos1'] += pre_chars + post_chars
            self.highlight()
            self.prev_text = copy(self.text)
            return

        # Removing characters
        if char[0] == "-":
            for c in self.codetext:
                changed = False
                # print("CODE npos0", c['npos0'], "pre start", pre_start, pre_chars, post_chars)
                if c['npos0'] is not None and c['npos0'] >= pre_start and c['npos0'] >= pre_start + -1 * pre_chars:
                    c['npos0'] += pre_chars + post_chars
                    c['npos1'] += pre_chars + post_chars
                    changed = True
                # Remove, as entire text is being removed (e.g. copy replace)
                # print(changed, c['npos0'],  pre_start, c['npos1'], pre_chars, post_chars)
                # print(c['npos0'], ">",  pre_start, "and", c['npos1'], "<", pre_start + -1*pre_chars + post_chars)
                if c['npos0'] is not None and not changed and c['npos0'] >= pre_start and \
                        c['npos1'] < pre_start + -1 * pre_chars + post_chars:
                    c['npos0'] += pre_chars + post_chars
                    c['npos1'] += pre_chars + post_chars
                    changed = True
                    self.code_deletions.append("delete from code_text where ctid=" + str(c['ctid']))
                    c['npos0'] = None
                if c['npos0'] is not None and not changed and c['npos0'] < pre_start <= c['npos1']:
                    c['npos1'] += pre_chars + post_chars
                    if c['npos1'] < c['npos0']:
                        self.code_deletions.append("delete from code_text where ctid=" + str(c['ctid']))
                        c['npos0'] = None
            for c in self.annotations:
                changed = False
                if c['npos0'] is not None and c['npos0'] >= pre_start and c['npos0'] >= pre_start + -1 * pre_chars:
                    c['npos0'] += pre_chars + post_chars
                    c['npos1'] += pre_chars + post_chars
                    changed = True
                    # Remove, as entire text is being removed (e.g. copy replace)
                    # print(changed, c['npos0'],  pre_start, c['npos1'], pre_chars, post_chars)
                    # print(c['npos0'], ">",  pre_start, "and", c['npos1'], "<", pre_start + -1*pre_chars + post_chars)
                    if c['npos0'] is not None and not changed and c['npos0'] >= pre_start and \
                            c['npos1'] < pre_start + -1 * pre_chars + post_chars:
                        c['npos0'] += pre_chars + post_chars
                        c['npos1'] += pre_chars + post_chars
                        changed = True
                        self.code_deletions.append("delete from annotations where anid=" + str(c['anid']))
                        c['npos0'] = None
                if c['npos0'] is not None and not changed and c['npos0'] < pre_start <= c['npos1']:
                    c['npos1'] += pre_chars + post_chars
                    if c['npos1'] < c['npos0']:
                        self.code_deletions.append("delete from annotation where anid=" + str(c['anid']))
                        c['npos0'] = None
            for c in self.casetext:
                changed = False
                if c['npos0'] is not None and c['npos0'] >= pre_start and c['npos0'] >= pre_start + -1 * pre_chars:
                    c['npos0'] += pre_chars + post_chars
                    c['npos1'] += pre_chars + post_chars
                    changed = True
                # Remove, as entire text is being removed (e.g. copy replace)
                # print(changed, c['npos0'],  pre_start, c['npos1'], pre_chars, post_chars)
                # print(c['npos0'], ">",  pre_start, "and", c['npos1'], "<", pre_start + -1*pre_chars + post_chars)
                if c['npos0'] is not None and not changed and c['npos0'] >= pre_start and \
                        c['npos1'] < pre_start + -1 * pre_chars + post_chars:
                    c['npos0'] += pre_chars + post_chars
                    c['npos1'] += pre_chars + post_chars
                    changed = True
                    self.code_deletions.append("delete from case_text where id=" + str(c['id']))
                    c['npos0'] = None
                if c['npos0'] is not None and not changed and c['npos0'] < pre_start <= c['npos1']:
                    c['npos1'] += pre_chars + post_chars
                    if c['npos1'] < c['npos0']:
                        self.code_deletions.append("delete from case_text where id=" + str(c['id']))
                        c['npos0'] = None
        self.highlight()
        self.prev_text = copy(self.text)
        cur = self.app.conn.cursor()
        cur.execute("update source set fulltext=? where id=?", (self.text, self.transcription[0]))
        self.app.conn.commit()
        for item in self.code_deletions:
            cur.execute(item)
        self.code_deletions = []
        self.update_codings()
        self.update_annotations()
        self.update_casetext()

    def highlight(self):
        """ Add coding and annotation highlights. """

        self.remove_formatting()
        format_ = QtGui.QTextCharFormat()
        format_.setFontFamily(self.app.settings['font'])
        format_.setFontPointSize(self.app.settings['docfontsize'])

        self.ui.textEdit.blockSignals(True)
        cursor = self.ui.textEdit.textCursor()
        for item in self.casetext:
            if item['npos0'] is not None:
                cursor.setPosition(int(item['npos0']), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(int(item['npos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
                format_.setFontUnderline(True)
                format_.setUnderlineColor(QtCore.Qt.GlobalColor.green)
                cursor.setCharFormat(format_)
        for item in self.annotations:
            if item['npos0'] is not None:
                cursor.setPosition(int(item['npos0']), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(int(item['npos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
                format_.setFontUnderline(True)
                format_.setUnderlineColor(QtCore.Qt.GlobalColor.yellow)
                cursor.setCharFormat(format_)
        for item in self.codetext:
            if item['npos0'] is not None:
                cursor.setPosition(int(item['npos0']), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(int(item['npos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
                format_.setFontUnderline(True)
                format_.setUnderlineColor(QtCore.Qt.GlobalColor.red)
                cursor.setCharFormat(format_)
        self.ui.textEdit.blockSignals(False)

    def remove_formatting(self):
        """ Remove formatting from text edit on changed text.
         Useful when pasting mime data (rich text or html) from clipboard. """

        self.ui.textEdit.blockSignals(True)
        format_ = QtGui.QTextCharFormat()
        format_.setFontFamily(self.app.settings['font'])
        format_.setFontPointSize(self.app.settings['docfontsize'])
        cursor = self.ui.textEdit.textCursor()
        cursor.setPosition(0, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(len(self.ui.textEdit.toPlainText()), QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(format_)
        self.ui.textEdit.blockSignals(False)

    def update_casetext(self):
        """ Update linked case text positions. """

        sql = "update case_text set pos0=?, pos1=? where id=? and (pos0 !=? or pos1 !=?)"
        cur = self.app.conn.cursor()
        for c in self.casetext:
            if c['npos0'] is not None:
                cur.execute(sql, [c['npos0'], c['npos1'], c['id'], c['npos0'], c['npos1']])
            if c['npos1'] >= len(self.text):
                cur.execute("delete from case_text where id=?", [c['id']])
        self.app.conn.commit()

    def update_annotations(self):
        """ Update annotation positions. """

        sql = "update annotation set pos0=?, pos1=? where anid=? and (pos0 !=? or pos1 !=?)"
        cur = self.app.conn.cursor()
        for a in self.annotations:
            if a['npos0'] is not None:
                cur.execute(sql, [a['npos0'], a['npos1'], a['anid'], a['npos0'], a['npos1']])
            if a['npos1'] >= len(self.text):
                cur.execute("delete from annotation where anid=?", [a['anid']])
        self.app.conn.commit()

    def update_codings(self):
        """ Update coding positions and seltext. """

        cur = self.app.conn.cursor()
        sql = "update code_text set pos0=?, pos1=?, seltext=? where ctid=?"
        for c in self.codetext:
            if c['npos0'] is not None:
                seltext = self.text[c['npos0']:c['npos1']]
                cur.execute(sql, [c['npos0'], c['npos1'], seltext, c['ctid']])
            if c['npos1'] >= len(self.text):
                cur.execute("delete from code_text where ctid=?", [c['ctid']])
        self.app.conn.commit()
