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
https://qualcoder.org/
https://qualcoder-org.github.io
"""

import sqlite3
from copy import copy, deepcopy
import datetime
# import difflib  # Use diff_match_patch as it is 20x faster. Keep this in case its needed later.
import logging
import os
import platform
import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/
from random import randint
import re
import subprocess
import time

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor

from .add_item_name import DialogAddItemName
from .code_in_all_files import DialogCodeInAllFiles
from .color_selector import DialogColorSelect, colors, TextColor, colour_ranges, show_codes_of_colour_range
from .confirm_delete import DialogConfirmDelete
from .GUI.ui_dialog_code_av import Ui_Dialog_code_av
from .helpers import msecs_to_hours_mins_secs, Message, ToolTipEventFilter, CodeResizeHandle, \
    init_persistent_tree_header, restore_persistent_tree_widths, ExportDirectoryPathDialog
from .memo import DialogMemo
from .report_attributes import DialogSelectAttributeParameters
from .select_items import DialogSelectItems

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

    def __init__(self, app, parent_text_edit, tab_reports):
        """ Show list of audio and video files.
        Can code a transcribed text file for the audio / video. """

        super(DialogCodeAV, self).__init__()
        self.app = app
        self.parent_textEdit = parent_text_edit
        self.tab_reports = tab_reports
        self.tree_sort_option = "all asc"  # Options: all desc, cat then code asc
        self.files = []
        self.attributes = []  # Show selected files in list widget
        self.file_ = None  # Current file
        self.show_codes_like_filter = ""  # gets filled when text strings are used to show specific code names
        self.show_codes_colour_filter = ""  # gets filled when a code colur is selected

        # For transcribed text
        self.annotations = []
        self.code_text = []
        self.transcription = None  # A tuple of id, fulltext, name
        # For Code Resize Handles Experimental- for resizing coded text
        self.active_handles = []
        # Transcribed time positions as list of [text_pos0, text_pos1, milliseconds]
        self.time_positions = []
        self.important = False  # Flag to show or hide important coded text and segments
        self.code_resize_timer = datetime.datetime.now()
        self.overlap_timer = datetime.datetime.now()
        self.overlap_code_index = 0  # Overlapping codes in text index

        # Segment variables
        self.segments = []
        self.segment = {'start': None, 'end': None, 'start_msecs': None, 'end_msecs': None, 'memo': "", 'important': 0,
                        'seltext': ""}
        self.play_segment_end = None  # End msecs of a segment that is played
        self.media_duration_text = ""
        self.segment_for_text = None  # When linking segment to text
        self.text_for_segment = {}  # When linking text to segment

        # Variables for codes and categories
        self.undo_deleted_codes = []  # Undo last deleted segment code, or text code(s).
        self.codes = []
        self.categories = []
        self.get_codes_and_categories()
        self.recent_codes = []  # list of recent codes (up to 5) for textedit context menu
        self.get_recent_codes()  # After codes obtained!

        # Variables for media and vlc player
        self.ddialog = None  # Contains video media
        self.instance = None  # vlc instance
        self.mediaplayer = None
        self.media = None
        self.metadata = None
        self.is_paused = False
        self.timer = QtCore.QTimer()

        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_code_av()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        try:
            s0 = int(self.app.settings['dialogcodeav_splitter0'])
            s1 = int(self.app.settings['dialogcodeav_splitter1'])
            if s0 > 10 and s1 > 10:
                self.ui.splitter.setSizes([s0, 30, s1, 30])
            h0 = int(self.app.settings['dialogcodeav_splitter_h0'])
            h1 = int(self.app.settings['dialogcodeav_splitter_h1'])
            if h0 > 10 and h1 > 10:
                self.ui.splitter_2.setSizes([h0, h1])
        except KeyError:
            pass
        # Header section
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
        self.ui.pushButton_important.setIcon(qta.icon('mdi6.star-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_important.pressed.connect(self.show_important_coded)
        self.ui.pushButton_add_image_to_project.setIcon(
            qta.icon('mdi6.image-plus-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_add_image_to_project.pressed.connect(self.import_screenshot_into_project)
        self.ui.pushButton_add_image_to_project.setEnabled(False)
        self.ui.pushButton_screensshot.setIcon(qta.icon('mdi6.image-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_screensshot.pressed.connect(self.save_screenshot)
        self.ui.pushButton_screensshot.setEnabled(False)
        self.ui.pushButton_find_code.setIcon(qta.icon('mdi6.card-search-outline', options=[{'scale-factor': 1.2}]))
        self.ui.pushButton_find_code.pressed.connect(self.find_code_in_tree)

        # The buttons under the files list
        self.ui.pushButton_latest.setIcon(qta.icon('mdi6.arrow-collapse-right', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_latest.pressed.connect(self.go_to_latest_coded_file)
        self.ui.pushButton_next_file.setIcon(qta.icon('mdi6.arrow-right', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_next_file.pressed.connect(self.go_to_next_file)
        self.ui.pushButton_document_memo.setIcon(qta.icon('mdi6.text-box-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_document_memo.pressed.connect(self.active_file_memo)
        self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_file_attributes.pressed.connect(self.get_files_from_attributes)
        self.ui.pushButton_clear_filter_file.setIcon(qta.icon('mdi6.filter-off-outline', options=[{'scale_factor': 1.3}]))  # for clear filter file <- L
        self.ui.pushButton_clear_filter_file.pressed.connect(self.clear_file_filter)
        self.ui.pushButton_clear_filter_file.setToolTip(_("Clear file filter"))
        self.ui.pushButton_clear_filter_file.setVisible(False)
        self.ui.pushButton_goto_bookmark.setIcon(qta.icon('mdi6.bookmark', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_goto_bookmark.pressed.connect(self.go_to_bookmark)

        # Widgets under codes tree
        self.ui.pushButton_clear_filter_code.setIcon(
            qta.icon('mdi6.filter-off-outline', options=[{'scale_factor': 1.3}]))  # for clear filter code <- L
        self.ui.pushButton_clear_filter_code.pressed.connect(self.clear_code_filter)
        self.ui.pushButton_clear_filter_code.setToolTip(_("Clear code filter"))
        self.ui.pushButton_clear_filter_code.setVisible(False)
        self.ui.lineEdit_code_filter.textChanged.connect(
            lambda textchanged: self.show_codes_like(self.ui.lineEdit_code_filter.text()))

        # Until any media is selected disable some widgets
        self.ui.pushButton_play.setEnabled(False)
        self.ui.pushButton_coding.setEnabled(False)
        self.ui.horizontalSlider.setEnabled(False)
        self.installEventFilter(self)  # for rewind, play/stop

        # Prepare textEdit for coding transcribed text
        self.ui.plainTextEdit.setPlainText("")
        self.ui.plainTextEdit.setAutoFillBackground(True)
        self.ui.plainTextEdit.setToolTip("")
        self.ui.plainTextEdit.setMouseTracking(True)
        self.ui.plainTextEdit.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse |
            Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.eventFilterTT = ToolTipEventFilter()
        self.ui.plainTextEdit.installEventFilter(self.eventFilterTT)
        self.ui.plainTextEdit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.plainTextEdit.customContextMenuRequested.connect(self.textedit_menu)
        self.ui.plainTextEdit.verticalScrollBar().valueChanged.connect(self.hide_resize_handles)
        self.ui.pushButton_segment_menu.pressed.connect(self.label_segment_menu)

        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        tree_font = f'font: {self.app.settings["treefontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.treeWidget.setStyleSheet(tree_font)
        doc_font = f'font: {self.app.settings["docfontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.plainTextEdit.setStyleSheet(doc_font)
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
        self.ui.treeWidget.itemClicked.connect(self.tree_item_clicked)  # open memo, or assign text to code
        init_persistent_tree_header(self.ui.treeWidget, self.app, 'dialogcodeav_tree_widths')
        self.get_files()
        self.app.project_events.project_data_changed.connect(self._on_project_data_changed)
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

    def help(self):
        """ Open help for transcribe section in browser. """
        self.app.help_wiki("4.5.-Coding-Audio-and-Video")

    def find_code_in_tree(self):
        """ Find a code by name in the codes tree and select it.
        """

        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
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
        matches = []
        while iterator.value():
            item = iterator.value()
            if "cid" in item.text(1):
                cid = int(item.text(1)[4:])
                code_ = next((code_ for code_ in self.codes if code_['cid'] == cid), None)
                if search_text in code_['name']:
                    matches.append(code_)
            iterator += 1
        if not matches:
            Message(self.app, _("Match not found"), _("No code with matching text found.")).exec()
            return
        # Get one selected code from one or more codes.
        selected = None
        if len(matches) > 1:
            ui = DialogSelectItems(self.app, matches, _("Select code"), "single")
            ok = ui.exec()
            if not ok:
                return
            selected = ui.get_selected()
            if not selected:
                return
        else:
            selected = matches[0]
        # Set selected in tree
        item = None
        iterator = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        while iterator.value():
            item = iterator.value()
            if "cid" in item.text(1):
                cid = int(item.text(1)[4:])
                if cid == selected['cid']:
                    self.ui.treeWidget.setCurrentItem(item)
                    break
            iterator += 1
        # Expand parents
        parent = item.parent()
        while parent is not None:
            parent.setExpanded(True)
            parent = parent.parent()

    def ddialog_menu(self, position):
        """ Context menu to export a screenshot, to resize dialog. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}}")
        action_screenshot = menu.addAction(_("Screenshot"))
        action_resize = menu.addAction(_("Resize"))
        action = menu.exec(self.ddialog.mapToGlobal(position))
        if action == action_screenshot:
            filename = f'Frame_{datetime.datetime.now().astimezone().strftime("%Y%m%d_%H_%M_%S")}.jpg'
            hms = msecs_to_hours_mins_secs(self.mediaplayer.get_time())
            image_name = f"{self.file_['name']}_{hms}.png"
            exp_directory = ExportDirectoryPathDialog(self.app, image_name)
            filepath = exp_directory.filepath
            if filepath is None:
                return
            image = self.mediaplayer.video_take_snapshot(0, filepath, 1280, 720)
            if image == 0:
                Message(self.app, _("Frame saved"), filepath).exec()
                self.parent_textEdit.append(_("Screenshot saved: ") + filepath)
            else:
                Message(self.app, _("Screenshot"), _("Not saved")).exec()
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

    def get_files(self, ids=None, sort="name asc"):
        """ Get AV files and exclude those with bad links.
        Fill list widget with file names.
        Args:
            ids : list of Integer ids to restrict files
            sort : String Sort options, name asc, name, desc, case asc, case desc
        """

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
        selection_model = self.ui.listWidget.selectionModel()
        selection_blocker = QtCore.QSignalBlocker(selection_model) if selection_model is not None else None
        self.ui.listWidget.clear()
        sql_case = "SELECT group_concat(cases.name) from cases join case_text on case_text.caseid=cases.caseid " \
                   "where case_text.fid=?"
        for file_ in self.files:
            tt = _("Date: ") + file_['date'].split()[0]
            cur.execute(sql_case, [file_['id']])
            file_['case'] = ""
            res_cases = cur.fetchone()
            if res_cases and res_cases[0] is not None:
                tt += "\n" + _("Case: ") + f"{res_cases[0]}"
                file_['case'] = f"{res_cases[0]}"
            tt += f"\n{file_['memo']}"
            file_['tooltip'] = tt
        # Sorting the file list
        if sort == "name asc":
            self.files = sorted(self.files, key=lambda x: x['name'])
        if sort == "name desc":
            self.files = sorted(self.files, key=lambda x: x['name'], reverse=True)
        if sort == "case asc":
            self.files = sorted(self.files, key=lambda x: x['case'])
        if sort == "case desc":
            self.files = sorted(self.files, key=lambda x: x['case'], reverse=True)
        if sort == "date asc":
            self.files = sorted(self.files, key=lambda x: x['date'])
        if sort == "date desc":
            self.files = sorted(self.files, key=lambda x: x['date'], reverse=True)
        # Fill list widget
        for file_ in self.files:
            item = QtWidgets.QListWidgetItem(file_['name'])
            item.setToolTip(file_['tooltip'])
            self.ui.listWidget.addItem(item)
        self.clear_file()
        del selection_blocker

    def get_files_from_attributes(self, refresh_only: bool = False):
        """ Select files based on attribute selections.
        Attribute results are a dictionary of:
        first item is a Boolean AND or OR list item
        Followed by each attribute list item

        Args:
            refresh_only: Recompute an already active attribute filter without reopening
                the selection dialog.
        """

        if refresh_only and len(self.attributes) <= 1:
            return

        # Clear ui
        self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
        ui = DialogSelectAttributeParameters(self.app)
        previous_attributes = deepcopy(self.attributes)
        ui.fill_parameters(deepcopy(self.attributes))
        temp_attributes = deepcopy(self.attributes)
        if refresh_only:
            ui.make_parameter_list()
            ui.get_results_case_ids()
            ui.get_results_file_ids()
            ui.get_results_message()
        else:
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
            if refresh_only and len(previous_attributes) > 1:
                self.clear_file_filter()
                return
            self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable'))
            self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
            self.get_files()
            return
        if not ui.result_file_ids:
            if not refresh_only:
                Message(self.app, _("Nothing found") + " " * 20, _("No matching files found")).exec()
                self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable'))
                self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
                return
            selection_model = self.ui.listWidget.selectionModel()
            selection_blocker = QtCore.QSignalBlocker(selection_model) if selection_model is not None else None
            self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable-box'))
            self.ui.pushButton_file_attributes.setToolTip(ui.tooltip_msg)
            self.ui.listWidget.clear()
            self.files = []
            self.clear_file()
            self.ui.pushButton_clear_filter_file.setVisible(True)
            self.ui.pushButton_clear_filter_file.setStyleSheet("background-color: #1e90ff; color: white;")
            del selection_blocker
            return
        self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable-box'))
        self.ui.pushButton_file_attributes.setToolTip(ui.tooltip_msg)
        self.get_files(ui.result_file_ids)
        self.ui.pushButton_clear_filter_file.setVisible(True)  # for clear filter file <- L
        self.ui.pushButton_clear_filter_file.setStyleSheet("background-color: #1e90ff; color: white;")

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

    def fill_tree(self):
        """ Fill tree widget, top level items are main categories and unlinked codes. """

        cats = deepcopy(self.categories)
        codes = deepcopy(self.codes)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(4)
        self.ui.treeWidget.setHeaderLabels([_("Name"), _("Id"), _("Memo"), _("Count")])
        if not self.app.settings['showids']:
            self.ui.treeWidget.setColumnHidden(1, True)
        else:
            self.ui.treeWidget.setColumnHidden(1, False)

        # Add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                memo = ""
                if c['memo'] != "":
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], f"catid:{c['catid']}", memo])
                top_item.setToolTip(0, '')
                if len(c['name']) > 52:
                    top_item.setText(0, f"{c['name'][:25]}..{c['name'][-25:]}")
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
                        child.setToolTip(0, '')
                        if len(c['name']) > 52:
                            child.setText(0, f"{c['name'][:25]}..{c['name'][-25:]}")
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
            if not remove_list:
                break  # cycle or dangling parent: leftovers placed at top level below
            for item in remove_list:
                cats.remove(item)
            count += 1
        # Fallback: never lose a category. Any with a missing/cyclic parent goes to top level. <- L
        for c in cats:
            memo = _("Memo") if c['memo'] != "" else ""
            top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
            top_item.setToolTip(2, c['memo'])
            top_item.setToolTip(0, '')
            if len(c['name']) > 52:
                top_item.setText(0, f"{c['name'][:25]}..{c['name'][-25:]}")
                top_item.setToolTip(0, c['name'])
            self.ui.treeWidget.addTopLevelItem(top_item)

        # Add codes, with sub-code nesting. A code is top level only when it has neither a
        # parent category (catid) nor a parent code (supercid). The rest are nested under
        # their category (catid:) or under their parent code (cid:). <- L

        def _make_code_item(code_dict):
            """ Build a styled tree item for a code. Sub-codes share this styling. <- L """
            memo_ = _("Memo") if code_dict['memo'] != "" else ""
            code_item = QtWidgets.QTreeWidgetItem([code_dict['name'], f"cid:{code_dict['cid']}", memo_])
            code_item.setToolTip(2, code_dict['memo'])
            code_item.setToolTip(0, '')
            if len(code_dict['name']) > 52:
                code_item.setText(0, f"{code_dict['name'][:25]}..{code_dict['name'][-25:]}")
                code_item.setToolTip(0, code_dict['name'])
            code_item.setBackground(0, QBrush(QColor(code_dict['color']), Qt.BrushStyle.SolidPattern))
            code_item.setForeground(0, QBrush(QColor(TextColor(code_dict['color']).recommendation)))
            code_item.setFlags(
                Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable |
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled)
            return code_item

        # Index every node already in the tree (categories) by its id text for O(1) lookup. <- L
        node_index = {}
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        while it.value():
            node_index[it.value().text(1)] = it.value()
            it += 1
        # Top level codes: no category and no parent code.
        remove_items = []
        for c in codes:
            if c['catid'] is None and c.get('supercid') is None:
                node = _make_code_item(c)
                self.ui.treeWidget.addTopLevelItem(node)
                node_index[f"cid:{c['cid']}"] = node
                remove_items.append(c)
        for c in remove_items:
            codes.remove(c)
        # Remaining codes: nest under category or parent code. Iterate because a parent code
        # may itself be a not-yet-placed sub-code. Each pass places every code whose parent
        # already exists; the loop ends when all are placed or no further progress is possible.
        count = 0
        while codes and count < 10000:
            remove_items = []
            for c in codes:
                if c.get('supercid') is not None:
                    parent_key = f"cid:{c['supercid']}"
                else:
                    parent_key = f"catid:{c['catid']}"
                parent_node = node_index.get(parent_key)
                if parent_node is not None:
                    node = _make_code_item(c)
                    parent_node.addChild(node)
                    node_index[f"cid:{c['cid']}"] = node
                    remove_items.append(c)
            if not remove_items:
                break  # remaining codes have a missing/cyclic parent: placed at top level below
            for c in remove_items:
                codes.remove(c)
            count += 1
        # Fallback: never lose a code. Any code with a dangling parent goes to top level. <- L
        for c in codes:
            node = _make_code_item(c)
            self.ui.treeWidget.addTopLevelItem(node)
            node_index[f"cid:{c['cid']}"] = node

        if self.tree_sort_option == "all asc":
            self.ui.treeWidget.sortByColumn(0, QtCore.Qt.SortOrder.AscendingOrder)
        if self.tree_sort_option == "all desc":
            self.ui.treeWidget.sortByColumn(0, QtCore.Qt.SortOrder.DescendingOrder)
        # Show the code tree expanded from the start: sub-code branches are visible by default;
        # categories the user had collapsed are restored to their collapsed state. <- L
        self.ui.treeWidget.expandAll()
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        while it.value():
            node = it.value()
            if node.text(1) in self.app.collapsed_categories:
                node.setExpanded(False)
            it += 1
        self.fill_code_counts_in_tree()
        restore_persistent_tree_widths(
            self.ui.treeWidget,
            default_width_factors={0: 0.70, 2: 0.15, 3: 0.15}
        )

    def fill_code_counts_in_tree(self):
        """ Calculate the frequency of each code and category for this coder and the selected file.
        Add a list item to each code that can be used to display in treeWidget.
        If the tab 'AI assisted coding' is active, the codings will be counted
        across all files, not only the currently selected one, because the AI assisted
        coding is not working on a per-file basis.
        """

        if self.file_ is None:
            return
        cur = self.app.conn.cursor()
        code_counts = []
        for c in self.codes:
            parameters = [c['cid'], self.app.settings['codername'], self.file_['id']]
            sql = "select code_name.catid, count(code_av.cid) from code_av join code_name " \
                "on code_name.cid=code_av.cid where code_av.cid=? and code_av.owner=? " \
                "and code_av.id=?"
            cur.execute(sql, parameters)
            result = cur.fetchone()
            sql_text = "select count(cid) from code_text where cid=? and owner=? and fid=?"
            text_parameters = [c['cid'], self.app.settings['codername'],self.transcription[0]]
            cur.execute(sql_text, text_parameters)
            result_text = cur.fetchone()
            code_counts.append([c['cid'], result[0], result[1] + result_text[0]])

        # Sub-code roll-up. Build own counts, the parent/children maps and an effective
        # category for each code (a sub-code is attributed to its top ancestor's category). <- L
        own_count = {cc[0]: cc[2] for cc in code_counts}
        code_by_cid = {c['cid']: c for c in self.codes}
        children_of = {}
        for c in self.codes:
            sup = c.get('supercid')
            if sup is not None:
                children_of.setdefault(sup, []).append(c['cid'])

        def _effective_catid(cid):
            """ Resolve a (possibly nested) code to the catid of its top ancestor code. <- L """
            seen = set()
            cur_c = code_by_cid.get(cid)
            while cur_c is not None and cur_c['cid'] not in seen:
                seen.add(cur_c['cid'])
                if cur_c['catid'] is not None:
                    return cur_c['catid']
                sup_ = cur_c.get('supercid')
                if sup_ is None:
                    return None
                cur_c = code_by_cid.get(sup_)
            return None

        eff_catid = {cc[0]: _effective_catid(cc[0]) for cc in code_counts}

        total_cache = {}

        def _code_total(cid):
            """ Code count rolled up with all descendant sub-codes. Memoized, cycle-safe. <- L """
            if cid in total_cache:
                return total_cache[cid]
            total_cache[cid] = own_count.get(cid, 0)  # seed guards against cycles
            t = own_count.get(cid, 0)
            for child_cid in children_of.get(cid, []):
                t += _code_total(child_cid)
            total_cache[cid] = t
            return t

        categories = deepcopy(self.categories)
        # Set up category counts
        for category in categories:
            category['count'] = 0
        # Add each code's own count to its effective category (sub-codes roll up to the
        # category of their top ancestor code, not to a raw catid that is None). <- L
        for category in categories:
            for code in code_counts:
                if eff_catid.get(code[0]) == category['catid']:
                    category['count'] += code[2]
        # Find leaf categories, add to above categories, and gradually remove leaves
        # until only top categories are left
        sub_categories = copy(categories)
        counter = 0
        while len(sub_categories) > 0 or counter < 10000:
            leaf_list = []
            branch_list = []
            for cat in sub_categories:
                for cat2 in sub_categories:
                    if cat['catid'] == cat2['supercatid']:
                        branch_list.append(cat)
            for category in sub_categories:
                if category not in branch_list:
                    leaf_list.append(category)
            # Add totals higher category
            for leaf_category in leaf_list:
                for category in categories:
                    if category['catid'] == leaf_category['supercatid']:
                        category['count'] += leaf_category['count']
                sub_categories.remove(leaf_category)
            counter += 1
        # Fill tree item counts
        iterator = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        while iterator.value():
            item = iterator.value()
            if item.text(1).startswith("catid"):
                catid = int(item.text(1)[6:])
                for category in categories:
                    if catid == category['catid']:
                        item.setText(3, str(category['count']))
            else:
                cid = int(item.text(1)[4:])
                own_n = own_count.get(cid, 0)
                if cid in children_of:
                    total_n = _code_total(cid)
                    item.setText(3, f"{own_n} ({total_n})" if total_n != own_n else str(own_n))
                else:
                    item.setText(3, str(own_n))
            iterator += 1  # Move to the next item

    def tree_item_clicked(self, item, column):
        """ Use to quicky open memo. Or,
        Assign selected text on left-click on code in tree. """

        if column == 2:
            self.add_edit_code_memo(item)
            return
        if item.text(1)[0:3] == 'cat':
            return
        selected_text = self.ui.plainTextEdit.textCursor().selectedText()
        if len(selected_text) > 0:
            self.mark()

    def get_collapsed(self, item):
        """ On category collapse or expansion signal, find the collapsed parent category items.
        This will fill the self.app.collapsed_categories and is the expanded/collapsed tree is then replicated across
        other areas of the app. """

        if item.text(1)[:3] == "cid":
            return
        if not item.isExpanded() and item.text(1) not in self.app.collapsed_categories:
            self.app.collapsed_categories.append(item.text(1))
        if item.isExpanded() and item.text(1) in self.app.collapsed_categories:
            self.app.collapsed_categories.remove(item.text(1))

    def file_menu(self, position):
        """ Context menu to select the next image alphabetically, or
         to select the image that was most recently coded """

        selected = self.ui.listWidget.currentItem()
        if not selected:
            return
        file_ = next((f for f in self.files if f['name'] == selected.text()), None)
        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        memo_action = menu.addAction(_("Open memo"))
        action_next = menu.addAction(_("Next file"))
        action_latest = menu.addAction(_("File with latest coding"))
        action_show_files_like = menu.addAction(_("Show files like"))
        action_show_case_files = menu.addAction(_("Show case files"))
        action_show_by_attribute = menu.addAction(_("Show files by attributes"))
        sort_menu = QtWidgets.QMenu(_("Sort"))
        sort_menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        action_sort_name_asc = sort_menu.addAction(_("Sort by name ascending"))
        action_sort_name_desc = sort_menu.addAction(_("Sort by name descending"))
        action_sort_case_asc = sort_menu.addAction(_("Sort by case ascending"))
        action_sort_case_desc = sort_menu.addAction(_("Sort by case descending"))
        action_sort_date_asc = sort_menu.addAction(_("Sort by date ascending"))
        action_sort_date_desc = sort_menu.addAction(_("Sort by date descending"))
        menu.addMenu(sort_menu)
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
            sql = "select id from code_av where owner=? order by date desc limit 1"
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
        if action == action_sort_name_asc:
            self.get_files(None, "name asc")
        if action == action_sort_name_desc:
            self.get_files(None, "name desc")
        if action == action_sort_case_asc:
            self.get_files(None, "case asc")
        if action == action_sort_case_desc:
            self.get_files(None, "case desc")
        if action == action_sort_date_asc:
            self.get_files(None, "date asc")
        if action == action_sort_date_desc:
            self.get_files(None, "date desc")

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
            self.ui.pushButton_clear_filter_file.setVisible(False)  # reset filter button when showing all
            self.ui.pushButton_clear_filter_file.setStyleSheet("")
            return
        cur = self.app.conn.cursor()
        cur.execute('select fid from case_text where caseid=?', [selection['id']])
        res = cur.fetchall()
        file_ids = [r[0] for r in res]
        self.get_files(file_ids)
        self.ui.pushButton_clear_filter_file.setVisible(True)  # for clear filter file <- L
        self.ui.pushButton_clear_filter_file.setStyleSheet("background-color: #1e90ff; color: white;")

    def show_files_like(self):
        """ Show files that contain specified filename text.
        If blank, show all files. """

        dialog = QtWidgets.QInputDialog(None) # correct: dialog embedded in workspace instead of floating
        dialog.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}}")
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
            self.ui.pushButton_clear_filter_file.setVisible(False)  # hide filter button when showing all <- L
            self.ui.pushButton_clear_filter_file.setStyleSheet("")
            return
        cur = self.app.conn.cursor()
        cur.execute("select id from source where name like ? and "  # restrict to AV files only <- L
                    "substr(mediapath,1,6) in ('/audio','/video', 'audio:', 'video:')",
                    ['%' + text_ + '%'])
        res = cur.fetchall()
        file_ids = [r[0] for r in res]
        self.get_files(file_ids)
        self.ui.pushButton_clear_filter_file.setVisible(True)  # for clear filter file <- L
        self.ui.pushButton_clear_filter_file.setStyleSheet("background-color: #1e90ff; color: white;")

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

        sql = "select id from code_av where owner=? order by date desc limit 1"
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
        current_item = self.ui.listWidget.currentItem()
        if current_item is None:
            return
        itemname = current_item.text()
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
        self.ui.plainTextEdit.clear()
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
        # It always plays at full volume when loading, even if half-way, se make it full vol visually
        self.ui.horizontalSlider_vol.setValue(100)
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
        self.ui.plainTextEdit.setPlainText(self.transcription[1])
        self.ui.plainTextEdit.ensureCursorVisible()
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
        transcript_id_and_offset = {"id": self.transcription[0], "start":0}
        if self.important:
            imp_coded = []
            for c in self.code_text:
                if c['important'] == 1:
                    imp_coded.append(c)
            self.eventFilterTT.set_codes_and_annotations(self.app, imp_coded, self.codes, self.annotations, transcript_id_and_offset)
        else:
            self.eventFilterTT.set_codes_and_annotations(self.app, self.code_text, self.codes, self.annotations, transcript_id_and_offset)
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
            # Adjust msecs to 1000's for 1 or 2 digit strings
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
                self.ui.plainTextEdit.toPlainText() != "":
            for i in range(1, len(self.time_positions)):
                if self.time_positions[i - 1][2] < msecs < self.time_positions[i][2]:
                    text_pos = self.time_positions[i][0]
                    text_cursor = self.ui.plainTextEdit.textCursor()
                    text_cursor.setPosition(text_pos)
                    self.ui.plainTextEdit.setTextCursor(text_cursor)

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

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        selected = self.ui.treeWidget.currentItem()
        action_color = None
        action_assign_segment = None
        action_show_coded_media = None
        action_move_code = None
        if self.segment['end_msecs'] is not None and self.segment['start_msecs'] is not None:
            action_assign_segment = menu.addAction("Assign segment to code")
        action_add_code_to_category = None
        action_add_category_to_category = None
        if selected is not None and selected.text(1)[0:3] == 'cat':
            action_add_code_to_category = menu.addAction(_("Add new code to category"))
            action_add_category_to_category = menu.addAction(_("Add a new category to category"))
        action_add_code = menu.addAction(_("Add a new code"))
        action_add_category = menu.addAction(_("Add a new category"))
        action_add_subcode = None
        if selected is not None and selected.text(1)[0:3] == 'cid':
            action_add_subcode = menu.addAction(_("Add a new sub-code to code"))  # <- L
        action_expand_collapse = None
        action_cat_show_coded_files = None
        if selected is not None and selected.text(1)[0:3] == 'cat':
            action_expand_collapse = menu.addAction(_("Expand or collapse branch"))
            action_cat_show_coded_files = menu.addAction(_("Show coded files"))
        if selected is not None and selected.text(1)[0:3] == 'cid' and selected.childCount() > 0:
            action_expand_collapse = menu.addAction(_("Expand or collapse branch"))  # <- L
        modify_menu = menu.addMenu(_("Modify"))
        action_rename = modify_menu.addAction(_("Rename F2"))
        action_edit_memo = modify_menu.addAction(_("View or edit memo"))
        action_merge_category = None
        action_move_category = None
        if selected is not None and selected.text(1)[0:3] == 'cat':
            action_merge_category = modify_menu.addAction(_("Merge category into category"))
            action_move_category = modify_menu.addAction(_("Move category under category"))
        action_delete = modify_menu.addAction(_("Delete"))
        action_move_multi_codes = None
        action_merge_code_into_code = None
        if selected is not None and selected.text(1)[0:3] == 'cid':
            action_color = modify_menu.addAction(_("Change code color"))
            action_move_code = modify_menu.addAction(_("Move code to"))
            action_move_multi_codes = modify_menu.addAction(_("Move multiple codes"))
            action_merge_code_into_code = modify_menu.addAction(_("Merge code into code"))  # <- L
            action_show_coded_media = menu.addAction(_("Show coded files"))
        action_find_code = menu.addAction(_("Find code"))
        filter_menu = menu.addMenu(_("Filter"))
        action_show_codes_like = filter_menu.addAction(_("Show codes like") + ": " + self.show_codes_like_filter)
        action_show_codes_of_colour = filter_menu.addAction(_("Show codes of colour") + ": " + self.show_codes_colour_filter)
        sort_menu = menu.addMenu(_("Sort"))
        action_all_asc = sort_menu.addAction(_("Sort ascending"))
        action_all_desc = sort_menu.addAction(_("Sort descending"))
        action_cat_then_code_asc = sort_menu.addAction(_("Sort category then code ascending"))
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
        if action == action_find_code:
            self.find_code_in_tree()
            return
        if selected is not None and selected.text(1)[0:3] == 'cid' and action == action_color:
            self.change_code_color(selected)
            return
        if selected is not None and action == action_move_code:
            self.move_code(selected)
            return
        if action == action_move_multi_codes:
            self.move_multiple_codes()
            return
        if action == action_merge_code_into_code and selected is not None:
            self.merge_code_into_code(selected)  # <- L
            return
        if action == action_add_category_to_category:
            catid = int(selected.text(1).split(":")[1])
            self.add_category(catid)
            return
        if action == action_add_category:
            self.add_category()
            return
        if action == action_add_code:
            self.add_code()
            return
        if action == action_move_category:
            catid = int(selected.text(1).split(":")[1])
            self.move_category(catid)
            return
        if action == action_merge_category:
            catid = int(selected.text(1).split(":")[1])
            self.merge_category(catid)
            return
        if action == action_add_code_to_category:
            catid = int(selected.text(1).split(":")[1])
            self.add_code(catid)
            return
        if action == action_add_subcode and selected is not None:
            supercid = int(selected.text(1).split(":")[1])  # <- L
            self.add_code(supercid=supercid)
            return
        if action == action_expand_collapse:
            expand_toggle = not selected.isExpanded()
            self.recursive_expand_collapse_branch(selected, expand_toggle)
            return
        if selected is not None and action == action_rename:
            self.rename_category_or_code(selected)
        if selected is not None and action == action_edit_memo:
            self.add_edit_code_memo(selected)
        if selected is not None and action == action_delete:
            self.delete_category_or_code(selected)
        if action == action_assign_segment:
            self.assign_segment_to_code(selected)
        if action == action_cat_show_coded_files:
            branch_codes = self.recursive_get_branch_codes(selected, [])
            self.coded_media_dialog(branch_codes, selected.text(0))
            return
        if selected is not None and action == action_show_coded_media:
            to_find = int(selected.text(1)[4:])
            found = next((code for code in self.codes if code['cid'] == to_find), None)
            if found:
                self.coded_media_dialog(found)

    def recursive_get_branch_codes(self, item, branch_codes):
        """ Set all children of this item to be expanded or collapsed.
        Recurse through all child categories. """

        child_count = item.childCount()
        for i in range(child_count):
            if item.child(i).text(1)[0:3] == "cid":
                cid = int(item.child(i).text(1)[4:])
                for code_ in self.codes:
                    if cid == code_['cid']:
                        branch_codes.append(code_)
                        break
                self.recursive_get_branch_codes(item.child(i), branch_codes)  # also gather sub-codes nested under this code (supercid) <- L
            if item.child(i).text(1)[0:3] == "cat":
                self.recursive_get_branch_codes(item.child(i), branch_codes)
        return branch_codes

    def recursive_expand_collapse_branch(self, item, expand_toggle):
        """ Set all children of this item to be expanded or collapsed.
        Recurse through all child categories. """

        child_count = item.childCount()
        for i in range(child_count):
            item.setExpanded(expand_toggle)
            self.recursive_expand_collapse_branch(item.child(i), expand_toggle)

    def coded_media_dialog(self, code_dict, category_name:str = ""):
        """ Display all coded media for this code, in a separate modal dialog.
        Coded media comes from ALL files for this coder.
        Need to store textedit start and end positions so that code in 000000000000 can be used.
        Called from tree_menu.
        Re-load the codings may have changed.
        Args:
            code_dict : code dictionary
            category_name : if a category selected, the category name
        """

        DialogCodeInAllFiles(self.app, code_dict, "File", category_name)
        self.update_dialog_codes_and_categories(["code_name", "code_cat", "code_text", "code_av", "code_image"])

    def move_multiple_codes(self):
        """ Move multiple codes to another category. """

        cur = self.app.conn.cursor()
        cur.execute("select code_name.name, code_cat.name, cid from code_name left join code_cat on "
                    "code_cat.catid=code_name.catid order by upper(code_cat.name) asc, upper(code_name.name) asc")
        res = cur.fetchall()
        code_list = []
        for r in res:
            name = r[0]
            if r[1] is not None:
                name = r[1] + " ← " + r[0]
            code_list.append({'name': name, 'cid': r[2]})
        ui = DialogSelectItems(self.app, code_list, _("Select codes"), "multi")
        ok = ui.exec()
        if not ok:
            return
        selected_codes = ui.get_selected()
        cur.execute("select name, catid from code_cat order by upper(name)")
        res = cur.fetchall()
        category_list = [{'name': "", 'catid': None}]
        for r in res:
            category_list.append({'name': r[0], 'catid': r[1]})
        ui = DialogSelectItems(self.app, category_list, _("Select blank or category"), "single")
        ok = ui.exec()
        if not ok:
            return
        category = ui.get_selected()
        for s in selected_codes:
            # Moving to a category (or to blank) removes any sub-code nesting. <- L
            cur.execute("update code_name set catid=?, supercid=null where cid=?", [category['catid'], s['cid']])
            self.app.conn.commit()
            self.parent_textEdit.append(_("Code moved.") + s['name'].replace(" ← ", "/") + " → " + category['name'])
        self.update_dialog_codes_and_categories(["code_name"])

    def move_code(self, selected):
        """ Move code to another category or to no category.
        Uses a list selection.
        param:
            selected : QTreeWidgetItem
         """

        items_list = [{'name': " ", 'catid': -1, 'cid': -1}]  # Default blank item
        iterator = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        while iterator.value():
            can_append = True
            item = iterator.value()
            depth = 0
            current = item
            # Get depth and if circular reference present
            while current.parent() is not None:
                if current.text(1) == selected.text(1):
                    can_append = False
                current = current.parent()
                depth += 1
            prefix = ""
            if depth > 0:
                prefix = "  " * (depth - 1) * 2 + "└─"  # U2514 U2500
            name = prefix + item.text(0)
            cid = -1
            catid = -1
            if "cid" in item.text(1):
                cid = int(item.text(1)[4:])
            else:
                catid = int(item.text(1)[6:])
                name += " " + _("[CATEGORY]")
            # Check the same item is not the same selected item
            if item.text(1) == selected.text(1) and item.text(2) == selected.text(2):
                can_append = False
            memo = item.toolTip(2)
            if can_append:
                items_list.append({'name': name, 'catid': catid, 'cid': cid, 'memo': memo})
            iterator += 1
        ui = DialogSelectItems(self.app, items_list, _("Select blank or category or code"), "single")
        ok = ui.exec()
        if not ok:
            return
        destination = ui.get_selected()
        # print(destination)
        selected_cid = int(selected.text(1)[4:])
        cur = self.app.conn.cursor()
        if destination['catid'] == -1 and destination['cid'] == -1:  # move to top level
            cur.execute("update code_name set catid=null, supercid=null where cid=?", [selected_cid])
        elif destination['cid'] > 0:  # Move under another code
            cur.execute("update code_name set catid=null, supercid=? where cid=?", [destination['cid'], selected_cid])
        else:  # Move under a category
            cur.execute("update code_name set catid=?, supercid=null where cid=?", [destination['catid'], selected_cid])
        self.app.conn.commit()
        self.update_dialog_codes_and_categories(["code_name"])

        '''cid = int(selected.text(1)[4:])
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
        # Moving to a category (or to blank) removes any sub-code nesting. <- L
        cur.execute("update code_name set catid=?, supercid=null where cid=?", [category['catid'], cid])
        self.update_dialog_codes_and_categories(["code_name"])'''

    def move_category(self, catid: int):
        """ Select another category to move this category underneath.
        Args:
            catid : Integer category identifier
        """

        do_not_merge_list = []
        do_not_merge_list = self.recursive_non_merge_item(self.ui.treeWidget.currentItem(), do_not_merge_list)
        do_not_merge_list.append(str(catid))
        do_not_merge_ids_string = f"({','.join(do_not_merge_list)})"
        sql = "select name, catid, supercatid from code_cat where catid not in "
        sql += do_not_merge_ids_string + " order by name"
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
        current_cat_name = self.ui.treeWidget.currentItem().text(0)
        if category['name'] == '':
            cur.execute("update code_cat set supercatid=Null where catid=?", [catid])
            self.app.conn.commit()
            self.parent_textEdit.append(_("Moved category: ") + current_cat_name + " → Top level")
        else:
            cur.execute("update code_cat set supercatid=? where catid=?", [category['catid'], catid])
            self.app.conn.commit()
            self.parent_textEdit.append(_("Moved category: ") + current_cat_name + " → " + category['name'])
        self.update_dialog_codes_and_categories()

    def show_codes_like(self, preset=None):
        """ Show all codes if text is empty.
        Show selected codes that contain entered text.
        The input dialog is too narrow, so it is re-created.
        Args:
            preset: None of called from tree_menu, or a string value if called from filer_code_text line edit
        """

        case_sensitive = True
        if preset is None:
            dialog = QtWidgets.QDialog(None)
            dialog.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
            dialog.setWindowTitle(_("Show some codes"))
            dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
            dlg_text = _("Show codes containing the text. (Blank for all)") + "\n"
            if self.show_codes_like_filter:
                dlg_text += _("Filter: ") + self.show_codes_like_filter
            lbl = QtWidgets.QLabel(dlg_text)
            line = QtWidgets.QLineEdit()
            chkbox = QtWidgets.QCheckBox(_("Case sensitive"))
            btnBox = QtWidgets.QDialogButtonBox()
            btnBox.setStandardButtons(QtWidgets.QDialogButtonBox.StandardButton.Ok|QtWidgets.QDialogButtonBox.StandardButton.Cancel)
            layout = QtWidgets.QVBoxLayout()
            layout.addWidget(lbl)
            layout.addWidget(chkbox)
            layout.addWidget(line)
            layout.addWidget(btnBox)
            dialog.setLayout(layout)
            btnBox.rejected.connect(dialog.reject)
            btnBox.accepted.connect(dialog.accept)
            dialog.resize(200, 60)
            ok = dialog.exec()
            if not ok:
                return
            self.show_codes_colour_filter = ""
            case_sensitive = chkbox.isChecked()
            self.show_codes_like_filter = line.text()
        else:
            self.show_codes_like_filter = preset
        root = self.ui.treeWidget.invisibleRootItem()
        self.recursive_traverse(root, "")  # Show all codes in tree
        root = self.ui.treeWidget.invisibleRootItem()
        self.recursive_traverse(root, self.show_codes_like_filter, case_sensitive)
        if self.show_codes_like_filter == "":  # <- L
            self.ui.pushButton_clear_filter_code.setVisible(False)  # for clear filter code <- L
            self.ui.pushButton_clear_filter_code.setStyleSheet("")
        else:
            self.ui.pushButton_clear_filter_code.setVisible(True)
            self.ui.pushButton_clear_filter_code.setStyleSheet("background-color: #1e90ff; color: white;")
            
    def show_codes_of_color(self):
        """ Show all codes in colour range in code tree., ir all codes if no selection.
        Show selected codes that are of a selected colour.
        """

        ui = DialogSelectItems(self.app, colour_ranges, _("Select code colors"), "single")
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        self.show_codes_colour_filter = selected['name']  # colour range name
        if self.show_codes_colour_filter == "all":
            self.show_codes_colour_filter = ""
        show_codes_of_colour_range(self.app, self.ui.treeWidget, self.codes, selected)
        self.show_codes_like_filter = ""
        if self.show_codes_colour_filter == "":  # <- L
            self.ui.pushButton_clear_filter_code.setVisible(False)
            self.ui.pushButton_clear_filter_code.setStyleSheet("")
        else:
            self.ui.pushButton_clear_filter_code.setVisible(True)
            self.ui.pushButton_clear_filter_code.setStyleSheet("background-color: #1e90ff; color: white;")
            
    def clear_code_filter(self):
        """ Clear any active code filter and restore all codes in the tree. """
        self.show_codes_like_filter = ""
        self.show_codes_colour_filter = ""
        self.ui.lineEdit_code_filter.setText("")
        root = self.ui.treeWidget.invisibleRootItem()
        self.recursive_traverse(root, "")
        self.ui.pushButton_clear_filter_code.setVisible(False)
        self.ui.pushButton_clear_filter_code.setStyleSheet("")

    def clear_file_filter(self):
        """ Clear any active file filter and reload all files. """
        self.attributes = []
        self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_file_attributes.setToolTip(_("Attributes"))
        self.get_files()
        self.ui.pushButton_clear_filter_file.setVisible(False)
        self.ui.pushButton_clear_filter_file.setStyleSheet("")

    def recursive_traverse(self, item, text_="", case_sensitive=False):
        """ Find all children codes of this item that match or not and hide or unhide based on 'text'.
        Recurse through all child categories and sub-codes. A code stays visible if it matches or
        if any of its descendant sub-codes matches, so a match is never hidden under a
        non-matching parent code. Returns True if this item or any descendant matches. <- L
        Called by: show_codes_like
        Args:
            item: a QTreeWidgetItem
            text_:  Text string for matching with code names
            case_sensitive:  Bool
        """

        child_count = item.childCount()
        any_visible_descendant = False
        for i in range(child_count):
            child = item.child(i)
            is_code = "cid:" in child.text(1)
            # Recurse first so we know whether any descendant matches. <- L
            descendant_match = self.recursive_traverse(child, text_, case_sensitive)
            if text_ == "":
                if is_code:
                    child.setHidden(False)
                any_visible_descendant = True
                continue
            self_match = False
            if is_code:
                cid = int(child.text(1)[4:])
                c = next((cc for cc in self.codes if cc['cid'] == cid), None)
                if c is not None:
                    if case_sensitive:
                        self_match = text_ in c['name']
                    else:
                        self_match = text_.lower() in c['name'].lower()
            visible = self_match or descendant_match
            if is_code:
                child.setHidden(not visible)
            if visible:
                any_visible_descendant = True
        return any_visible_descendant

    def update_dialog_codes_and_categories(self, tables: list[str]|None = None):
        """Refresh the local dialog after code/category changes and optionally notify other dialogs.

        Args:
            tables: Optional list of changed database table names to emit to the project event bus.
                Use an empty list for a local-only refresh without notifying other dialogs.
        """

        self.get_codes_and_categories()
        self.fill_tree()
        self.load_segments()
        self.unlight()
        self.highlight()
        self.get_coded_text_update_eventfilter_tooltips()

        if self.app.project_events is not None:
            self.app.project_events.emit_table_changes(tables, source=self)

    def _on_project_data_changed(self, tables, source):
        """Handle project change events from other dialogs.

        Args:
            tables: Changed database table names.
            source: Event emitter, ignored when it is this dialog.
        """

        if source is self or not isinstance(tables, list):
            return
        tables = set(tables)
        if ("attribute" in tables or "attribute_type" in tables) and len(self.attributes) > 1:
            self.get_files_from_attributes(refresh_only=True)

        code_tree_changed = "code_cat" in tables or "code_name" in tables

        refresh_segments = "code_av" in tables or "code_text" in tables or ("code_name" in tables and bool(self.segments))
        refresh_transcript = "code_text" in tables or ("code_name" in tables and bool(self.code_text))
        refresh_counts = "code_av" in tables or "code_text" in tables

        if code_tree_changed:
            self.get_codes_and_categories()
            self.fill_tree()
        elif not refresh_counts and not refresh_segments and not refresh_transcript:
            return

        if refresh_transcript:
            self.get_coded_text_update_eventfilter_tooltips()
        if refresh_segments and self.file_ is not None and self.media is not None:
            self.load_segments()
        if refresh_counts and not code_tree_changed:
            self.fill_code_counts_in_tree()

    def keyPressEvent(self, event):
        """ This works best without the modifiers.
         As pressing Ctrl + E give the Ctrl but not the E.
         These key presses are not used in edi mode.

        A annotate - for current selection
        Shift B Go to bookmark
        B set bookmark
        C New category
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

        F2 Rename code or category
        """

        key = event.key()
        mods = QtGui.QGuiApplication.keyboardModifiers()

        # Esc hides any active resize handles <- L
        if key == QtCore.Qt.Key.Key_Escape:
            if hasattr(self, 'active_handles') and self.active_handles:
                self.hide_resize_handles()
                return
        # Go to bookmark
        if key == QtCore.Qt.Key.Key_B and mods & QtCore.Qt.KeyboardModifier.ShiftModifier:
            self.go_to_bookmark()
            return
        # Set bookmark
        if key == QtCore.Qt.Key.Key_B:
            if self.file_ is None:
                return
            cur = self.app.conn.cursor()
            cursor_pos = self.ui.plainTextEdit.textCursor().position()
            cur.execute("update project set avbookmarkfile=?, avbookmarkmsec=?, avbookmarktextpos=?", [self.file_['id'], self.mediaplayer.get_time(), cursor_pos])
            self.app.conn.commit()
            return
        # New category
        if key == QtCore.Qt.Key.Key_C:
            # if category already selected, add new category to that
            supercatid = None
            selected = self.ui.treeWidget.currentItem()
            if selected is not None and selected.text(1)[0:3] == 'cat':
                supercatid = int(selected.text(1)[6:])
            self.add_category(supercatid)
            return
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
        # Rename code or category
        if self.ui.treeWidget.hasFocus() and key == QtCore.Qt.Key.Key_F2:
            selected = self.ui.treeWidget.currentItem()
            self.rename_category_or_code(selected)
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
        if not self.ui.plainTextEdit.hasFocus():
            return
        '''# Ignore all other key events if edit mode is active  # Edit mode not used here yet
        if self.edit_mode:
            return'''
        cursor_pos = self.ui.plainTextEdit.textCursor().position()
        selected_text = self.ui.plainTextEdit.textCursor().selectedText()
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
        if key == QtCore.Qt.Key.Key_R and self.file_ is not None and self.ui.plainTextEdit.textCursor().selectedText() != "":
            self.textedit_recent_codes_menu(self.ui.plainTextEdit.cursorRect().topLeft())
            return

    def go_to_bookmark(self):
        """ B or button. """

        cur = self.app.conn.cursor()
        cur.execute("select avbookmarkfile, avbookmarkmsec, avbookmarktextpos from project")
        result = cur.fetchone()
        self.file_ = None
        for i, f in enumerate(self.files):
            if f['id'] == result[0]:
                self.file_ = f
                self.ui.listWidget.setCurrentItem(
                    self.ui.listWidget.findItems(self.file_['name'], QtCore.Qt.MatchFlag.MatchExactly)[0])
                self.load_media()
                self.load_segments()
                self.fill_code_counts_in_tree()
                break
        if self.file_ is None:
            return
        self.mediaplayer.set_time(result[1])
        self.mediaplayer.play()
        # Playback must be active to set_time(). Also add a small sleep to give vlc time to load the media.
        time.sleep(0.2)
        self.mediaplayer.set_time(result[1])
        self.ui.horizontalSlider.setValue(int(result[1] / self.media.get_duration() * 1000))
        self.mediaplayer.pause()
        cursor = self.ui.plainTextEdit.textCursor()
        cursor.setPosition(result[2])
        endpos = result[2] - 1
        if endpos < 0:
            endpos = 0
        cursor.setPosition(endpos, QtGui.QTextCursor.MoveMode.KeepAnchor)
        self.ui.plainTextEdit.setTextCursor(cursor)

    def save_screenshot(self):
        filename = f'Frame_{datetime.datetime.now().astimezone().strftime("%Y%m%d_%H_%M_%S")}.jpg'
        hms = msecs_to_hours_mins_secs(self.mediaplayer.get_time())
        image_name = f"{self.file_['name']}_{hms}.png"
        exp_directory = ExportDirectoryPathDialog(self.app, image_name)
        filepath = exp_directory.filepath
        if filepath is None:
            return
        image = self.mediaplayer.video_take_snapshot(0, filepath, 1280, 720)
        if image == 0:
            Message(self.app, _("Frame saved"), filepath).exec()
            self.parent_textEdit.append(_("Screenshot saved: ") + filepath)
        else:
            Message(self.app, _("Screenshot"), _("Not saved")).exec()

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
        try:
            cur = self.app.conn.cursor()
            cur.execute("insert into source(name,memo,owner,date, mediapath, fulltext) values(?,?,?,?,?,?)",
                        (
                            entry['name'], entry['memo'], entry['owner'], entry['date'], entry['mediapath'],
                            entry['fulltext']))
            self.app.conn.commit()
        except sqlite3.IntegrityError as e_:
            print(e_)
            msg = f"{e_}\n"
            msg += _("This source name already exists:")
            msg += f"\n{entry['name']}"
            Message(self.app, _("Name exists"), msg, "warning").exec()
            return
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
                return True
            # Scroll the tree when dragged item it as top or bottom edges
            if event.type() == QtCore.QEvent.Type.DragMove:
                vsb = self.ui.treeWidget.verticalScrollBar()
                item = self.ui.treeWidget.currentItem()
                top = self.ui.treeWidget.visualRect(
                    self.ui.treeWidget.indexAt(self.ui.treeWidget.rect().topLeft())).bottom()
                bottom = self.ui.treeWidget.viewport().height()
                y = event.position().toPoint().y()
                if y < top + 8:  # Margin 0f 8
                    vsb.setValue(vsb.value() - 1)
                if y > bottom - 8:  # Margin of 8
                    vsb.setValue(vsb.value() + 1)
                return True
        if event.type() != 7 or self.media is None:
            return False

        key = event.key()
        mod = event.modifiers()
        # Change start and end code positions using alt arrow left and alt arrow right
        # and shift arrow left, shift arrow right
        if self.ui.plainTextEdit.hasFocus():
            cursor_pos = self.ui.plainTextEdit.textCursor().position()
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

        if self.ui.plainTextEdit.toPlainText() == "":
            return
        selected_text = self.ui.plainTextEdit.textCursor().selectedText()
        if selected_text == "":
            return
        if len(self.recent_codes) == 0:
            return
        menu = QtWidgets.QMenu()
        for item in self.recent_codes:
            menu.addAction(item['name'])
        action = menu.exec(self.ui.plainTextEdit.mapToGlobal(position))
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

        pos = self.ui.plainTextEdit.textCursor().position()
        codes_here = [c for c in self.code_text if c['pos0'] <= pos <= c['pos1']]
        self.overlap_code_index += 1
        if self.overlap_code_index >= len(codes_here):
            self.overlap_code_index = 0
        item = codes_here[self.overlap_code_index]
        for c in self.codes:
            if item['cid'] == c['cid']:
                item['color'] = c['color']
                break
        # Remove formatting
        cursor = self.ui.plainTextEdit.textCursor()
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

        if code_['pos1'] + 1 >= len(self.ui.plainTextEdit.toPlainText()):
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

    def _category_is_descendant(self, candidate_catid, ancestor_catid):
        """ Return True if candidate_catid is ancestor_catid or one of its descendant
        sub-categories. Used to prevent cycles when moving a category under another. <- L """
        if candidate_catid == ancestor_catid:
            return True
        children = {}
        for c in self.categories:
            sup = c.get('supercatid')
            if sup is not None:
                children.setdefault(sup, []).append(c['catid'])
        stack = list(children.get(ancestor_catid, []))
        seen = set()
        while stack:
            catid = stack.pop()
            if catid == candidate_catid:
                return True
            if catid in seen:
                continue
            seen.add(catid)
            stack.extend(children.get(catid, []))
        return False

    def item_moved_update_data(self, item, parent):
        """ Called from drop event in treeWidget view port.
        identify code or category to move.
        Also merge codes if one code is dropped on another code.
        param:
            item: QTreeWidgetItem
            parent: QTreeWidgetItem """

        # Find the category in the list
        if item.text(1)[0:3] == 'cat':
            found = -1  # use -1 sentinel, not None <- L
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(item.text(1)[6:]):
                    found = i
            if found == -1:  # check against sentinel, not falsy
                return
            if parent is None:
                self.categories[found]['supercatid'] = None
            else:
                if parent.text(1).split(':')[0] == 'cid':
                    # parent is code (leaf) cannot add child
                    return
                supercatid = int(parent.text(1).split(':')[1])
                if supercatid == self.categories[found]['catid']:
                    # Cannot be its own parent.
                    return
                # Guard against cycles: moving a category under one of its own sub-categories
                # would make the branch disappear and corrupt the tree. <- L
                if self._category_is_descendant(supercatid, self.categories[found]['catid']):
                    Message(self.app, _("Cannot move category"),
                            _("Cannot move a category under one of its own sub-categories.")).exec()
                    return
                self.categories[found]['supercatid'] = supercatid
            cur = self.app.conn.cursor()
            cur.execute("update code_cat set supercatid=? where catid=?",
                        [self.categories[found]['supercatid'], self.categories[found]['catid']])
            self.app.conn.commit()
            self.update_dialog_codes_and_categories(["code_cat"])
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
                # Move code to top level: clear both parents. <- L
                self.codes[found]['catid'] = None
                self.codes[found]['supercid'] = None
            else:
                if parent.text(1).split(':')[0] == 'cid':
                    parent_cid = int(parent.text(1).split(':')[1])
                    # Ctrl held while dropping a code on a code merges (previous behaviour);
                    # otherwise the code is nested as a sub-code. <- L
                    ctrl = bool(QtWidgets.QApplication.keyboardModifiers() &
                                QtCore.Qt.KeyboardModifier.ControlModifier)
                    if ctrl:
                        self.merge_codes(self.codes[found], parent)
                        return
                    if parent_cid == self.codes[found]['cid']:
                        return  # cannot nest under itself
                    if self._code_is_descendant(parent_cid, self.codes[found]['cid']):
                        Message(self.app, _("Cannot nest code"),
                                _("Cannot move a code under one of its own sub-codes.")).exec()
                        return
                    # Nest as a sub-code (mutually exclusive with category). <- L
                    self.codes[found]['supercid'] = parent_cid
                    self.codes[found]['catid'] = None
                else:
                    # Dropped onto a category. <- L
                    catid = int(parent.text(1).split(':')[1])
                    self.codes[found]['catid'] = catid
                    self.codes[found]['supercid'] = None
            cur = self.app.conn.cursor()
            cur.execute("update code_name set catid=?, supercid=? where cid=?",
                        [self.codes[found]['catid'], self.codes[found].get('supercid'),
                         self.codes[found]['cid']])
            self.app.conn.commit()
            self.update_dialog_codes_and_categories(["code_name"])
            self.app.delete_backup = False

    def _code_is_descendant(self, candidate_cid, ancestor_cid):
        """ Return True if candidate_cid is ancestor_cid or one of its descendant sub-codes.
        Used to prevent cycles when nesting a code under another code. <- L """
        if candidate_cid == ancestor_cid:
            return True
        children = {}
        for c in self.codes:
            sup = c.get('supercid')
            if sup is not None:
                children.setdefault(sup, []).append(c['cid'])
        stack = list(children.get(ancestor_cid, []))
        seen = set()
        while stack:
            cid = stack.pop()
            if cid == candidate_cid:
                return True
            if cid in seen:
                continue
            seen.add(cid)
            stack.extend(children.get(cid, []))
        return False

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
            # Always record merge info in target category memo  # <- L
            source_cat = None
            for c in self.categories:
                if c['catid'] == catid:
                    source_cat = c
                    break
            if source_cat is not None and category['catid'] is not None:
                target_cat = None
                for c in self.categories:
                    if c['catid'] == category['catid']:
                        target_cat = c
                        break
                if target_cat is not None:
                    merge_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
                    source_memo = (source_cat.get('memo', '') or '').strip()
                    source_owner = source_cat.get('owner', self.app.settings['codername'])
                    merged_block = f"\n\n[{_('Merged from category:')} {source_cat['name']}, {_('Coder:')} {source_owner}, {_('Merger date:')} {merge_date}]"
                    if source_memo:
                        merged_block += f"\n{source_memo}"
                    target_memo = target_cat.get('memo', '') or ''
                    new_memo = (target_memo + merged_block).strip()
                    cur.execute("update code_cat set memo=? where catid=?", [new_memo, category['catid']])
                    target_cat['memo'] = new_memo
            for code in self.codes:
                if code['catid'] == catid:
                    cur.execute("update code_name set catid=? where catid=?", [category['catid'], catid])
            cur.execute("delete from code_cat where catid=?", [catid])
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
        except Exception as e_:
            print(e_)
            logger.warning(e_)
            self.app.conn.rollback()  # revert all changes
            self.update_dialog_codes_and_categories()
            raise            
        self.update_dialog_codes_and_categories(["code_cat", "code_name"])

    def merge_code_into_code(self, selected):
        """ Merge the selected code into another code chosen from a list.
        Reuses merge_codes (the same logic used by drag-and-drop with Ctrl). The source code
        and all of its descendant sub-codes are excluded from the candidate targets to avoid
        creating a supercid cycle when merging a code into one of its own sub-codes. <- L
        param:
            selected: QTreeWidgetItem
        """

        if selected is None or selected.text(1)[0:3] != 'cid':
            return
        src_cid = int(selected.text(1)[4:])
        source_code = next((c for c in self.codes if c['cid'] == src_cid), None)
        if source_code is None:
            return
        # Candidate targets: every code that is not the source nor a descendant of the source.
        target_list = []
        for c in self.codes:
            if not self._code_is_descendant(c['cid'], src_cid):
                target_list.append({'name': c['name'], 'cid': c['cid']})
        if not target_list:
            Message(self.app, _("Merge code into code"),
                    _("There is no other code to merge into.")).exec()
            return
        target_list = sorted(target_list, key=lambda x: x['name'].lower())
        ui = DialogSelectItems(self.app, target_list, _("Select code to merge into"), "single")
        ok = ui.exec()
        if not ok:
            return
        target = ui.get_selected()
        if not target:
            return
        # merge_codes expects the target as a QTreeWidgetItem, so find it in the tree.
        target_item = None
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        while it.value():
            node = it.value()
            if node.text(1) == f"cid:{target['cid']}":
                target_item = node
                break
            it += 1
        if target_item is None:
            return
        self.merge_codes(source_code, target_item)

    def merge_codes(self, item, parent):
        """ Merge code with another code .
        Called by item_moved_update_data when a code is moved onto another code.
        param:
            item: QTreeWidgetItem
            parent: QTreeWidgetItem """

        # Check item dropped on itself. Error can occur on Ubuntu 22.04.
        if item['name'] == parent.text(0):
            return
        # Prevent a supercid cycle <- L
        target_cid = int(parent.text(1).split(':')[1])
        if self._code_is_descendant(target_cid, item['cid']):
            Message(self.app, _("Cannot merge code"),
                    _("Cannot merge a code into itself or one of its own sub-codes.")).exec()
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
        # Always record merge info in target code memo <- L
        target_code = None
        for c in self.codes:
            if c['cid'] == new_cid:
                target_code = c
                break
        if target_code is not None:
            merge_date = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
            source_memo = item.get('memo', '').strip()
            source_owner = item.get('owner', self.app.settings['codername'])
            merged_block = f"\n\n[{_('Merged from code:')} {item['name']}, {_('Coder:')} {source_owner}, {_('Merger date:')} {merge_date}]"
            if source_memo:
                merged_block += f"\n{source_memo}"
            target_memo = target_code.get('memo', '') or ''
            new_memo = (target_memo + merged_block).strip()
            cur.execute("update code_name set memo=? where cid=?", [new_memo, new_cid])
            target_code['memo'] = new_memo
        # Update cid for each coded segment in text, av, image. Delete where there is an Integrity error
        ct_sql = "select ctid from code_text where cid=?"
        cur.execute(ct_sql, [old_cid])
        ct_res = cur.fetchall()
        try:
            for ct in ct_res:
                try:
                    cur.execute("update code_text set cid=? where ctid=?", [new_cid, ct[0]])
                except sqlite3.IntegrityError:
                    cur.execute("delete from code_text where ctid=?", [ct[0]])
            av_sql = "select avid from code_av where cid=?"
            cur.execute(av_sql, [old_cid])
            av_res = cur.fetchall()
            for av in av_res:
                try:
                    cur.execute("update code_av set cid=? where avid=?", [new_cid, av[0]])
                except sqlite3.IntegrityError:
                    cur.execute("delete from code_av where avid=?", [av[0]])
            img_sql = "select imid from code_image where cid=?"
            cur.execute(img_sql, [old_cid])
            img_res = cur.fetchall()
            for img in img_res:
                try:
                    cur.execute("update code_image set cid=? where imid=?", [new_cid, img[0]])
                except sqlite3.IntegrityError:
                    cur.execute("delete from code_image where imid=?", [img[0]])
            # Re-parent the merged code's sub-codes onto the target code (no orphans). <- L
            cur.execute("update code_name set supercid=?, catid=null where supercid=?", [new_cid, old_cid])
            cur.execute("delete from code_name where cid=?", [old_cid, ])
            self.app.conn.commit()
        except Exception as e_:
            print(e_)
            logger.warning(e_)
            self.app.conn.rollback()  # revert all changes
            raise                
        self.update_dialog_codes_and_categories(["code_name", "code_text", "code_av", "code_image"])
        self.parent_textEdit.append(msg_)
        self.load_segments()

    def add_code(self, catid=None, supercid=None):
        """  Use add_item dialog to get new code text. Add_code_name dialog checks for
        duplicate code name. A random color is selected for the code.
        New code is added to data and database.
        param:
            catid : None to add to without category, catid to add to to category.
            supercid : None, or Integer to add the code as a sub-code of another code. <- L """

        # Mutual exclusivity: a sub-code never belongs to a category as well. <- L
        if supercid is not None:
            catid = None
        ui = DialogAddItemName(self.app, self.codes, _("Add new code"), _("New code name"))
        ui.exec()
        new_name = ui.get_new_name()
        if new_name is None:
            return
        code_color = colors[randint(0, len(colors) - 1)]
        item = {'name': new_name, 'memo': "", 'owner': self.app.settings['codername'],
                'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), 'catid': catid,
                'color': code_color, 'supercid': supercid}
        cur = self.app.conn.cursor()
        cur.execute("insert into code_name (name,memo,owner,date,catid,color,supercid) values(?,?,?,?,?,?,?)",
                    (item['name'], item['memo'], item['owner'], item['date'], item['catid'], item['color'],
                     item['supercid']))
        self.app.conn.commit()
        self.parent_textEdit.append(_("Code added: ") + item['name'])
        self.update_dialog_codes_and_categories(["code_name"])
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
        self.update_dialog_codes_and_categories(["code_cat"])
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
        # Re-parent this code's sub-codes so they are not orphaned by the deletion. <- L
        if code_.get('supercid') is not None:
            # Was itself a sub-code: lift its children to the grandparent code.
            cur.execute("update code_name set supercid=? where supercid=?", [code_['supercid'], code_['cid']])
        else:
            # Was top level (possibly under a category): move children into that category (or top level).
            cur.execute("update code_name set supercid=null, catid=? where supercid=?",
                        [code_['catid'], code_['cid']])
        cur.execute("delete from code_name where cid=?", [code_['cid'], ])
        cur.execute("delete from code_av where cid=?", [code_['cid'], ])
        cur.execute("delete from code_image where cid=?", [code_['cid'], ])
        cur.execute("delete from code_text where cid=?", [code_['cid'], ])
        self.app.conn.commit()
        self.parent_textEdit.append(_("Code deleted: ") + code_['name'])
        self.update_dialog_codes_and_categories(["code_name", "code_text", "code_av", "code_image"])
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
        # An extra check. Fix 'lost' categories if present.
        sql = "update code_cat set supercatid=null where supercatid is not null and supercatid not in " \
              "(select catid from code_cat)"
        cur.execute(sql)
        self.app.conn.commit()
        self.parent_textEdit.append(_("Category deleted: ") + category['name'])
        self.update_dialog_codes_and_categories(["code_cat", "code_name"])
        self.app.delete_backup = False

    def add_edit_code_memo(self, selected):
        """ View and edit a memo to a code.
        param:
            selected: QTreeWidgetItem """

        changed_tables = []

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
            # Update codes list and database
            if memo != self.codes[found]['memo']:
                self.codes[found]['memo'] = memo
                cur = self.app.conn.cursor()
                cur.execute("update code_name set memo=? where cid=?", (memo, self.codes[found]['cid']))
                self.app.conn.commit()
                self.app.delete_backup = False
                changed_tables = ["code_name"]

        if selected.text(1)[0:3] == 'cat':
            # Find the category in the list
            found = -1  # use -1 sentinel <- L
            for i in range(0, len(self.categories)):
                if self.categories[i]['catid'] == int(selected.text(1)[6:]):
                    found = i
            if found == -1:  # check against sentinel
                return
            ui = DialogMemo(self.app, _("Memo for Category ") + self.categories[found]['name'],
                            self.categories[found]['memo'])
            ui.exec()
            memo = ui.memo
            if memo == "":
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, "")
            else:
                selected.setData(2, QtCore.Qt.ItemDataRole.DisplayRole, _("Memo"))
            # Update codes list and database
            if memo != self.categories[found]['memo']:
                self.categories[found]['memo'] = memo
                cur = self.app.conn.cursor()
                cur.execute("update code_cat set memo=? where catid=?", (memo, self.categories[found]['catid']))
                self.app.conn.commit()
                self.app.delete_backup = False
                changed_tables = ["code_cat"]
        self.update_dialog_codes_and_categories(changed_tables)

    def rename_category_or_code(self, selected):
        """ Rename a code or category. Checks that the proposed code or category name is
        not currently in use.
        param:
            selected: QTreeWidgetItem """

        if selected.text(1)[0:3] == 'cid':
            found_code = None
            check_codes = []
            for code_ in self.codes:
                if code_['cid'] == int(selected.text(1)[4:]):
                    found_code = code_
                else:
                    check_codes.append(code_)
            ui = DialogAddItemName(self.app, check_codes, _("Rename code"), _("Code name"))
            ui.ui.lineEdit.setText(found_code['name'])
            ui.exec()
            new_name = ui.get_new_name()
            if new_name is None or new_name == found_code['name']:
                return
            # Find the code in the list
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
            self.update_dialog_codes_and_categories(["code_name"])
            self.app.delete_backup = False
            return

        if selected.text(1)[0:3] == 'cat':
            found_cat = None
            check_categories = []
            for category in self.categories:
                if category['catid'] == int(selected.text(1)[6:]):
                    found_cat = category
                else:
                    check_categories.append(category)
            ui = DialogAddItemName(self.app, check_categories, _("Rename category"), _("Category name"))
            ui.ui.lineEdit.setText(found_cat['name'])
            ui.exec()
            new_name = ui.get_new_name()
            if new_name is None or new_name == found_cat['name']:
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
            self.update_dialog_codes_and_categories(["code_cat"])
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
        self.update_dialog_codes_and_categories(["code_name"])
        self.app.delete_backup = False

    # Methods used with the textEdit transcribed text
    def unlight(self):
        """ Remove all text highlighting from current file. """

        if self.transcription is None or self.ui.plainTextEdit.toPlainText() == "":
            return
        cursor = self.ui.plainTextEdit.textCursor()
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
            cursor = self.ui.plainTextEdit.textCursor()
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
                cursor = self.ui.plainTextEdit.textCursor()
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
        cursor = self.ui.plainTextEdit.textCursor()
        for overlap in overlaps:
            fmt = QtGui.QTextCharFormat()
            fmt.setFontUnderline(True)
            if self.app.settings['stylesheet'] == 'dark':
                fmt.setUnderlineColor(QColor("#000000"))
            else:
                fmt.setUnderlineColor(QColor("#FFFFFF"))
            cursor.setPosition(overlap[0], QtGui.QTextCursor.MoveMode.MoveAnchor)
            cursor.setPosition(overlap[1], QtGui.QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(fmt)

    def textedit_menu(self, position):
        """ Context menu for textEdit. Mark, unmark, annotate, copy. """

        if self.ui.checkBox_scroll_transcript.isChecked():
            return
        cursor = self.ui.plainTextEdit.cursorForPosition(position)
        selected_text = self.ui.plainTextEdit.textCursor().selectedText()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
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
        action_show_handles = None

        for item in self.code_text:
            if item['pos0'] <= cursor.position() <= item['pos1']:
                if item['avid'] is not None:
                    action_play_text = QtGui.QAction(_("Play text"))
                    # TODO select which avid if multiple coded here
                    play_text_avid = item['avid']
                action_unmark = QtGui.QAction(_("Unmark"))
                action_code_memo = QtGui.QAction(_("Memo coded text M"))
                action_change_code = QtGui.QAction(_("Change code"))
                action_show_handles = QtGui.QAction(_("Resize"))
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
        if action_show_handles:
            menu.addAction(action_show_handles)
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
        action = menu.exec(self.ui.plainTextEdit.mapToGlobal(position))
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
        if action == action_change_code:
            self.change_code_to_another_code(cursor.position())
            return
        # ---  handles experimental
        if action == action_show_handles:
            self.display_handles_for_code(cursor.position())
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
        to_remove = next((code_ for code_ in codes_list if code_['cid'] == text_item['cid']), None)
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
            position = self.ui.plainTextEdit.textCursor().position()
        if self.file_ is None:
            return
        coded_text_list = []
        for item in self.code_text:
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
        msg_ = f"{text_item['name']} [{text_item['pos0']}-{text_item['pos1']}]"
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

    def play_text(self, avid):
        """ Play the audio/video for this coded text selection that is mapped to an a/v segment. """

        segment = next((item for item in self.segments if item['avid'] == avid), None)
        if not segment:
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

        timestamp = next((ts for ts in self.time_positions if ts[0] <= position <= ts[1]), None)
        if not timestamp:
            return
        self.timer.stop()
        self.mediaplayer.set_position(timestamp[2] / self.media.get_duration())
        self.timer.start()

    def copy_selected_text_to_clipboard(self):
        """ Copy text to clipboard for external use.
        For example adding text to another document. """

        selected_text = self.ui.plainTextEdit.textCursor().selectedText()
        cb = QtWidgets.QApplication.clipboard()
        cb.setText(selected_text)

    def mark(self):
        """ Mark selected text in file with currently selected code.
       Need to check for multiple same codes at same pos0 and pos1.
       """

        if self.transcription is None or self.ui.plainTextEdit.toPlainText() == "":
            Message(self.app, _('Warning'), _('No transcription'), "warning").exec()
            return
        item = self.ui.treeWidget.currentItem()
        if item is None:
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec()
            return
        if item.text(1).split(':')[0] == 'catid':  # must be a code
            return
        cid = int(item.text(1).split(':')[1])
        selected_text = self.ui.plainTextEdit.textCursor().selectedText()
        pos0 = self.ui.plainTextEdit.textCursor().selectionStart()
        pos1 = self.ui.plainTextEdit.textCursor().selectionEnd()
        if pos0 == pos1:  # Something quirky happened
            return
        # Add the coded section to code text, add to database and update GUI
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
        tmp_code = next((item for item in self.codes if item['cid'] == cid), None)
        if not tmp_code:
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

        if self.transcription is None or self.ui.plainTextEdit.toPlainText() == "":
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

        if self.transcription is None or self.ui.plainTextEdit.toPlainText() == "":
            Message(self.app, _('Warning'), _("No media transcription selected"), "warning").exec()
            return
        pos0 = self.ui.plainTextEdit.textCursor().selectionStart()
        pos1 = self.ui.plainTextEdit.textCursor().selectionEnd()
        text_length = len(self.ui.plainTextEdit.toPlainText())
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
                                            + f"{item['pos0']}-{item['pos1']}" + _(" for: ") +
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
                                        + f"{item['pos0']}" + _(" for: ") + self.transcription[2])
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

    # --- handles
    def display_handles_for_code(self, position):
        """ Display interactive drag handles to resize a code's boundaries. """

        if self.file_ is None:
            return
        self.file_['start'] = 0  # Needed for helpers class CodeResizeHandle
        self.text = self.ui.plainTextEdit.toPlainText()  # Needed for helpers class CodeResizeHandle
        coded_text_list = []
        for item in self.code_text:
            if item['pos0'] <= position <= item['pos1']:
                coded_text_list.append(item)
        if not coded_text_list:
            return
        code_to_handle = coded_text_list[-1]
        if len(coded_text_list) > 1:
            ui = DialogSelectItems(self.app, coded_text_list, _("Select code to resize"), "single")
            if ui.exec():
                code_to_handle = ui.get_selected()
            else:
                return
        self.hide_resize_handles()

        # Create start handle
        cursor_start = self.ui.plainTextEdit.textCursor()
        cursor_start.setPosition(max(0, code_to_handle['pos0']))
        rect_start = self.ui.plainTextEdit.cursorRect(cursor_start)
        h_start = CodeResizeHandle(self.ui.plainTextEdit, True, code_to_handle, self)
        # start teardrop tip is at its top-right corner -> shift left by full width <- L
        h_start.move(rect_start.x() - h_start.width(), rect_start.y())
        self.active_handles.append(h_start)

        # Create end handle
        cursor_end = self.ui.plainTextEdit.textCursor()
        cursor_end.setPosition(min(len(self.ui.plainTextEdit.toPlainText()), code_to_handle['pos1']))
        rect_end = self.ui.plainTextEdit.cursorRect(cursor_end)
        h_end = CodeResizeHandle(self.ui.plainTextEdit, False, code_to_handle, self)
        # end teardrop tip is at its top-left corner -> align directly to the cursor x <- L
        h_end.move(rect_end.x(), rect_end.y())
        self.active_handles.append(h_end)

    def hide_resize_handles(self):
        """ Remove all active resize handles from the screen. """
        for h in getattr(self, 'active_handles', []):
            h.hide()
            h.deleteLater()
        self.active_handles = []

    # Reposition active handles to their code's current pos0/pos1 without recreating them.
    # Keeps the handles on screen so start and end can be adjusted repeatedly <- L
    def reposition_resize_handles(self):
        """ Re-anchor active handles after a resize so they stay usable. """
        if not getattr(self, 'active_handles', []):
            return
        for h in self.active_handles:
            fresh = next((c for c in self.code_text if c.get('ctid') == h.code_item.get('ctid')), None)
            if fresh is not None:
                h.code_item = fresh
                h.orig_pos0 = fresh['pos0']
                h.orig_pos1 = fresh['pos1']
            anchor = h.code_item['pos0'] if h.is_start else h.code_item['pos1']
            cursor = self.ui.plainTextEdit.textCursor()
            cursor.setPosition(max(0, min(len(self.ui.plainTextEdit.toPlainText()), anchor)))
            rect = self.ui.plainTextEdit.cursorRect(cursor)
            if h.is_start:
                h.move(rect.x() - h.width(), rect.y())  # start tip at top-right
            else:
                h.move(rect.x(), rect.y())  # end tip at top-left
            h.raise_()

    def update_code_position_from_handle(self, code_item, new_pos, is_start, orig_pos0, orig_pos1):
        """ Receive final drop coordinates from a handle and update the database. """
        if is_start:
            if new_pos >= code_item['pos1']:
                code_item['pos0'] = orig_pos0  # Revert visually
                self.hide_resize_handles()
                self.unlight()
                self.highlight()
                return
            code_item['pos0'] = new_pos
        else:
            if new_pos <= code_item['pos0']:
                code_item['pos1'] = orig_pos1  # Revert visually
                self.hide_resize_handles()
                self.unlight()
                self.highlight()
                return
            code_item['pos1'] = new_pos

        cur = self.app.conn.cursor()
        cur.execute("select substr(fulltext,?,?) from source where id=?",
                    [code_item['pos0'] + 1, code_item['pos1'] - code_item['pos0'], code_item['fid']])
        res = cur.fetchone()

        if not res:
            # Revert on extraction error
            code_item['pos0'] = orig_pos0
            code_item['pos1'] = orig_pos1
            self.hide_resize_handles()
            self.unlight()
            self.highlight()
            return
        seltext = res[0]

        try:
            sql = "update code_text set pos0=?, pos1=?, seltext=? where ctid=?"
            cur.execute(sql, [code_item['pos0'], code_item['pos1'], seltext, code_item['ctid']])
            self.app.conn.commit()
            self.app.delete_backup = False
        except sqlite3.IntegrityError:
            self.app.conn.rollback()
            # Revert in-memory positions to undo temporary highlight
            code_item['pos0'] = orig_pos0
            code_item['pos1'] = orig_pos1
            Message(self.app, _("Duplicate Error"),
                    _("This code already exists at this exact location."), "warning").exec()
        # Keep handles active after a successful resize so the user can
        # adjust the other end without re-triggering the action <- L
        self.get_coded_text_update_eventfilter_tooltips()
        self.reposition_resize_handles()


class GraphicsScene(QtWidgets.QGraphicsScene):
    """ set the scene for the graphics objects and re-draw events. """

    def __init__(self, width, height, parent=None):
        super(GraphicsScene, self).__init__(parent)
        self.scene_width = width
        self.scene_height = height
        self.setSceneRect(QtCore.QRectF(0, 0, self.scene_width, self.scene_height))

    def mousePressEvent(self, event):
        """ I have implemented this, as the Segment context menu does not work when right-clicked
        once the QualCoder code is packaged by pyinstaller. (It does work outside of this).
        So a mouse click on a segment will open the 'alternative_context_menu' within the SegmentGraphicsItem
        """

        super(GraphicsScene, self).mousePressEvent(event)
        position = QtCore.QPointF(event.scenePos())
        #print("pos:", position.x(), position.y())
        for item in self.items(): # item is QGraphicsProxyWidget
            # print("X", int(item.scene_from_x), int(item.scene_to_x))
            # print("Y", item.scene_from_y, item.scene_to_y)
            if isinstance(item, SegmentGraphicsItem) and item.scene_from_x <= position.x() <= item.scene_to_x and \
                item.scene_from_y <= position.y() <= item.scene_to_y:
                # print("Found", item.segment)
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

        seltext = self.code_av_dialog.ui.plainTextEdit.textCursor().selectedText()
        items = [{'name': 'Memo for segment'},
                 {'name': 'Delete segment'},
                 {'name': 'Play segment'},
                 {'name': 'Edit start position'},
                 {'name': 'Edit end position'},
                 {'name': 'Change code to selected code'},
                 {'name': 'Add selected code to segment'},
                 {'name': 'Export segment'}]
        if self.code_av_dialog.ui.plainTextEdit.toPlainText() != "" and seltext != "":
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
        if action['name'] == 'Change code to selected code':
            self.replace_code()
            return
        if action['name'] == 'Add selected code to segment':
            self.add_code()
            return

    def contextMenuEvent(self, event):
        """
        # https://riverbankcomputing.com/pipermail/pyqt/2010-July/027094.html
        I was not able to mapToGlobal position so, the menu maps to scene position plus
        the Dialog screen position.
        Makes use of current segment: self.segment
        ThisMenu now does not work when packed with pyinstaller. So alternative menu method above.
        """

        seltext = self.code_av_dialog.ui.plainTextEdit.textCursor().selectedText()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet("QMenu {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        action_memo = menu.addAction(_('Memo for segment'))
        action_delete = menu.addAction(_('Delete segment'))
        action_play = menu.addAction(_('Play segment'))
        action_edit_start = menu.addAction(_('Edit segment start position'))
        action_edit_end = menu.addAction(_('Edit segment end position'))
        action_change_code = menu.addAction(_('Change code to selected code'))
        action_add_code = menu.addAction(_('Add selected code to segment'))
        action_export = None
        try:
            result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True).stdout
            action_export = menu.addAction(_('Export segment to file'))
        except Exception as e_:
            print(f"Cannot find ffmpeg {e_}")
        action_important = None
        action_not_important = None
        action_link_segment_to_text = None
        if self.code_av_dialog.ui.plainTextEdit.toPlainText() != "" and seltext != "":
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
            return
        if action == action_add_code:
            self.add_code()
            return
        if action== action_change_code:
            self.replace_code()
            return

    def add_code(self):
        """ Add another code to the segment. """
        selected = self.code_av_dialog.ui.treeWidget.currentItem()
        if selected is None:
            Message(self.app, _("No selection"), _("No code selected in tree")).exec()
            return
        item = selected.text(1)
        if 'catid' in item:
            Message(self.app, _("No selection"), _("No code selected in tree")).exec()
            return
        cid = int(item.split(":")[1])
        sql = "insert into code_av (id, pos0, pos1, cid, memo, date, owner, important) values(?,?,?,?,?,?,?, null)"
        values = [self.segment['id'], self.segment['pos0'], self.segment['pos1'], cid, "",
                  datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), self.app.settings['codername']]
        cur = self.app.conn.cursor()
        cur.execute(sql, values)
        self.app.conn.commit()
        self.code_av_dialog.load_segments()
        self.app.delete_backup = False
        self.code_av_dialog.fill_code_counts_in_tree()

    def replace_code(self):
        """ Replace code with another code. """
        selected = self.code_av_dialog.ui.treeWidget.currentItem()
        if selected is None:
            Message(self.app, _("No selection"), _("No code selected in tree")).exec()
            return
        item = selected.text(1)
        if 'catid' in item:
            Message(self.app, _("No selection"), _("No code selected in tree")).exec()
            return
        sql = "update code_av set cid=?, date=? where avid=?"
        values = [int(item.split(":")[1]), datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                  self.segment['avid']]
        cur = self.app.conn.cursor()
        cur.execute(sql, values)
        self.app.conn.commit()
        self.code_av_dialog.load_segments()
        self.app.delete_backup = False
        self.code_av_dialog.fill_code_counts_in_tree()

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
        ffmpeg_command = f'ffmpeg -i "{mediapath}" -ss {self.segment["pos0"] / 1000}'
        ffmpeg_command += f' -to {self.segment["pos1"] / 1000}'
        ffmpeg_command += f' -c copy "{filepath}"'
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
        cursor = self.code_av_dialog.ui.plainTextEdit.textCursor()
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
