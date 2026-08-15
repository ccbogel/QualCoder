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

Authors: Colin Curtain C, Kai Dröge, Justin Missaghieh--Poncet, Lorenzo Salomón
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
https://qualcoder-org.github.io
https://qualcoder.org/
"""

import sqlite3
from copy import copy, deepcopy
import datetime
import emoji
import logging
import os
from pathlib import Path
import platform
import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/
import re
import subprocess
import threading
import time

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor

from .code_in_all_files import DialogCodeInAllFiles
from .code_tree import CodeTreeController
from .coder_names import DialogCoderNames
from .color_selector import TextColor, colour_ranges, show_codes_of_colour_range
from .confirm_delete import DialogConfirmDelete
from .GUI.ui_dialog_code_av import Ui_Dialog_code_av
from .helpers import NumberBar, msecs_to_hours_mins_secs, Message, ToolTipEventFilter, CodeResizeHandle, \
    init_persistent_tree_header, ExportDirectoryPathDialog
from .memo import DialogMemo
from .report_attributes import DialogSelectAttributeParameters
from .select_items import DialogSelectItems
from .speakers import DialogSpeakers, speaker_coder_name
from .ris import Ris
from .ai_agent_prompts import AiAgentPromptsCatalog
from .ai_chat import ai_chat_signal_emitter
from .ai_prompt_library import DialogAiEditPrompts
from .view_av_waveform import waveform_backend_available, waveform_png_is_current, generate_waveform_png_async, \
    waveform_colour, keyframe_interval_seconds  # noqa: F401  (WaveformSeekBar used via the promoted .ui widget)

# If VLC not installed, it will not crash
vlc = None
from .media_player_qt import MediaInstance as QtMediaInstance, make_vlc_instance
try:
    import vlc
except Exception as e:  # python-vlc missing: Qt backend takes over, no console noise
    logging.getLogger(__name__).debug(f"python-vlc unavailable: {e}")

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
        self.undo_deleted_av_mirrors = []  # Wave segments removed as text-coding mirrors, for symmetric undo.
        self.undo_deleted_text_mirrors = []  # Text codings removed when deleting a segment in mirror mode.
        self.codes = []
        self.categories = []
        self.get_codes_and_categories()
        self.recent_codes = []  # list of recent codes (up to 5) for textedit context menu
        self.get_recent_codes()  # After codes obtained!

        # Variables for media and vlc player
        self.instance = None  # vlc instance
        self.mediaplayer = None
        self.video_window = None  # ventana flotante opcional para el video desacoplado
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
        # All splitters persist their layout, as in code_text.
        self.ui.splitter_right.splitterMoved.connect(self.update_sizes)
        self.ui.splitter_media.splitterMoved.connect(self.update_sizes)
        # Volume popup: icon button opening a vertical slider.
        self.ui.pushButton_volume.setIcon(qta.icon('mdi6.volume-high'))
        self.volume_menu = QtWidgets.QMenu(self)
        volume_action = QtWidgets.QWidgetAction(self.volume_menu)
        volume_holder = QtWidgets.QWidget()
        volume_layout = QtWidgets.QVBoxLayout(volume_holder)
        volume_layout.setContentsMargins(10, 8, 10, 8)
        self.volume_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Vertical)
        self.volume_slider.setRange(0, 100)
        try:
            self.volume_slider.setValue(int(self.app.settings.get('dialogcodeav_volume', 100)))
        except (TypeError, ValueError):
            self.volume_slider.setValue(100)
        self.volume_slider.setFixedHeight(110)
        volume_layout.addWidget(self.volume_slider, alignment=QtCore.Qt.AlignmentFlag.AlignHCenter)
        volume_action.setDefaultWidget(volume_holder)
        self.volume_menu.addAction(volume_action)
        self.volume_slider.valueChanged.connect(self.set_volume)
        self.ui.pushButton_volume.clicked.connect(self.show_volume_popup)
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
        self.ui.pushButton_mark_speakers.setIcon(qta.icon('mdi6.pin-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_mark_speakers.pressed.connect(self.mark_speakers)
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
        self.ui.label_coder_icon.setPixmap(qta.icon('mdi6.account').pixmap(26, 26))
        # The coder icon replaces the "Coder:" text label.
        self.ui.label_coder.hide()
        icon_geo = self.ui.label_coder.geometry()
        self.ui.label_coder_icon.setParent(self.ui.widget_coder)
        self.ui.label_coder_icon.setGeometry(icon_geo.x(), icon_geo.y(), 26, 26)
        self.ui.label_coder_icon.show()

        # The buttons under the files list
        self.ui.pushButton_latest.setIcon(qta.icon('mdi6.arrow-collapse-right', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_latest.pressed.connect(self.go_to_latest_coded_file)
        self.ui.pushButton_next_file.setIcon(qta.icon('mdi6.arrow-right', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_next_file.pressed.connect(self.go_to_next_file)
        self.ui.pushButton_document_memo.setIcon(qta.icon('mdi6.text-box-outline', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_document_memo.pressed.connect(self.active_file_memo)
        self.ui.pushButton_file_attributes.setIcon(qta.icon('mdi6.variable', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_file_attributes.pressed.connect(self.get_files_from_attributes)
        self.ui.pushButton_clear_filter_file.setIcon(qta.icon('mdi6.filter-off-outline', options=[{'scale_factor': 1.3}]))  # for clear filter file
        self.ui.pushButton_clear_filter_file.pressed.connect(self.clear_file_filter)
        self.ui.pushButton_clear_filter_file.setToolTip(_("Clear file filter"))
        self.ui.pushButton_clear_filter_file.setVisible(False)
        self.ui.pushButton_goto_bookmark.setIcon(qta.icon('mdi6.bookmark', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_goto_bookmark.pressed.connect(self.go_to_bookmark)
        self.ui.pushButton_segment_menu.setIcon(qta.icon('mdi6.format-list-bulleted', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_segment_menu.setToolTip(_("Segment menu"))
        self.ui.pushButton_segment_menu.pressed.connect(self.label_segment_menu)

        # Widgets under codes tree
        self.ui.pushButton_clear_filter_code.setIcon(
            qta.icon('mdi6.filter-off-outline', options=[{'scale_factor': 1.3}]))  # for clear filter code
        self.ui.pushButton_clear_filter_code.pressed.connect(self.clear_code_filter)
        self.ui.pushButton_clear_filter_code.setToolTip(_("Clear code filter"))
        self.ui.pushButton_clear_filter_code.setVisible(False)
        self.ui.lineEdit_code_filter.textChanged.connect(
            lambda textchanged: self.show_codes_like(self.ui.lineEdit_code_filter.text()))

        # Until any media is selected disable some widgets
        self.ui.pushButton_play.setEnabled(False)
        self.ui.pushButton_coding.setEnabled(False)
        self.ui.widget_seekbar.setEnabled(False)
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
        self.ui.plainTextEdit.viewport().installEventFilter(self)  # click on a timestamp -> seek
        self.ui.plainTextEdit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        # Line numbers in the transcript, as in the transcription area.
        # NumberBar in the .ui lineNumbers container, as code_text does
        self.number_bar = NumberBar(self.ui.plainTextEdit)
        _ln_layout = QtWidgets.QVBoxLayout(self.ui.lineNumbers)
        _ln_layout.setContentsMargins(0, 0, 0, 0)
        _ln_layout.addWidget(self.number_bar)
        self.ui.plainTextEdit.customContextMenuRequested.connect(self.textedit_menu)
        self.ui.plainTextEdit.verticalScrollBar().valueChanged.connect(self.hide_resize_handles)
        self.ui.plainTextEdit.cursorPositionChanged.connect(self.hide_handles_if_cursor_outside)

        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        tree_font = f'font: {self.app.settings["treefontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.treeWidget.setStyleSheet(tree_font)
        doc_font = f'font: {self.app.settings["docfontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.plainTextEdit.setStyleSheet(doc_font)
        # Top coder group as in code_text: label, name lineEdit and edit-coders button.
        self.ui.lineEdit_coder.setText(self.app.settings['codername'])
        self.ui.pushButton_coder.clicked.connect(self.edit_coder_names)
        # Autocode, show annotations and show memos next to the coder; search row below.
        self.autocode_history = []
        self.search_indices = []
        self.search_index = -1
        self.ui.pushButton_show_annotations.setIcon(
            qta.icon('mdi6.text-search-variant', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_show_annotations.pressed.connect(self.show_annotations)
        self.ui.pushButton_show_memos.setIcon(qta.icon('mdi6.text-search', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_show_memos.pressed.connect(self.show_memos)
        self.ui.pushButton_auto_code.setIcon(qta.icon('mdi6.mace'))
        self.ui.pushButton_auto_code.clicked.connect(self.auto_code)
        self.ui.pushButton_auto_code_undo.setIcon(qta.icon('mdi6.undo'))
        self.ui.pushButton_auto_code_undo.pressed.connect(self.undo_autocoding)
        self.ui.label_search.setPixmap(qta.icon('mdi6.magnify').pixmap(22, 22))
        self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
        self.ui.pushButton_previous.setIcon(qta.icon('mdi6.arrow-left', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_previous.setEnabled(False)
        self.ui.pushButton_previous.pressed.connect(self.move_to_previous_search_text)
        self.ui.pushButton_next.setIcon(qta.icon('mdi6.arrow-right', options=[{'scale_factor': 1.3}]))
        self.ui.pushButton_next.setEnabled(False)
        self.ui.pushButton_next.pressed.connect(self.move_to_next_search_text)
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
        # Shared code tree controller (code_tree.py): loading, context menu, drag and drop,
        # F2-F6 shortcuts and category branch deletion.
        self.code_tree = CodeTreeController(self.app, self.ui.treeWidget, self)
        self.ui.treeWidget.customContextMenuRequested.connect(self.code_tree.tree_menu)
        self.code_tree.fill_counts_callback = self.fill_code_counts_in_tree
        self.code_tree.coded_files_callback = self.coded_media_dialog
        self.code_tree.find_code_callback = self.find_code_in_tree
        self.code_tree.show_codes_like_callback = self.show_codes_like
        self.code_tree.show_codes_of_colour_callback = self.show_codes_of_color
        self.code_tree.codes_changed.connect(self.update_dialog_codes_and_categories)
        # Restore the page-specific entry lost in the tree migration.
        self.code_tree.menu_requested.connect(self.add_av_tree_menu_actions)

        self.ui.treeWidget.itemClicked.connect(self.tree_item_clicked)  # open memo, or assign text to code
        init_persistent_tree_header(self.ui.treeWidget, self.app, 'dialogcodeav_tree_widths')
        self.get_files()
        self.app.project_events.project_data_changed.connect(self._on_project_data_changed)
        self.code_tree.fill_tree()
        # These signals after the tree is filled the first time
        self.ui.treeWidget.itemCollapsed.connect(self.get_collapsed)
        self.ui.treeWidget.itemExpanded.connect(self.get_collapsed)

        # Video incrustado en el propio diálogo (sin ventana separada)
        self.ui.frame_video.setAutoFillBackground(True)
        _pal = self.ui.frame_video.palette()
        _pal.setColor(QtGui.QPalette.ColorRole.Window, QColor(30, 30, 30))
        self.ui.frame_video.setPalette(_pal)
        self.ui.frame_video.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.frame_video.customContextMenuRequested.connect(self.video_frame_menu)
        # Player backend combo (VLC / Qt), takes effect on the next media load
        self.ui.comboBox_player.addItems(["VLC", "Qt"])
        if vlc is None:
            # python-vlc not installed: the VLC entry cannot be selected at all
            self.ui.comboBox_player.model().item(0).setEnabled(False)
            self.ui.comboBox_player.setItemData(
                0, _("python-vlc is not installed"), QtCore.Qt.ItemDataRole.ToolTipRole)
            self.ui.comboBox_player.setCurrentIndex(1)
        else:
            self.ui.comboBox_player.setCurrentIndex(
                1 if self.app.settings.get('av_player', 'vlc') == 'qt' else 0)
        self.ui.comboBox_player.currentIndexChanged.connect(self.change_player_backend)
        # Designer-only minimums from the .ui, released for a shrinkable window
        for widget_ in (self.ui.topPanel, self.ui.frame_video, self.ui.widget_media,
                        self.ui.plainTextEdit):
            widget_.setMinimumSize(0, 0)
        # Botón para desacoplar el video a una ventana flotante
        self.ui.pushButton_detach.setIcon(qta.icon('mdi6.open-in-new'))
        self.ui.pushButton_detach.setToolTip(_("Detach video to a window"))
        self.ui.pushButton_detach.clicked.connect(self.toggle_detach_video)
        # Splitter entre el video y los controles (redimensionable)
        try:
            v0 = int(self.app.settings['dialogcodeav_splitter_v0'])
            v1 = int(self.app.settings['dialogcodeav_splitter_v1'])
            # Keys once stored heights; only restore plausible AV-pane widths
            if v0 > 450 and v1 > 10:
                self.ui.splitter_right.setSizes([v0, v1])
            else:
                raise ValueError("legacy heights, use defaults")
            m0 = int(self.app.settings['dialogcodeav_splitter_m0'])
            m1 = int(self.app.settings['dialogcodeav_splitter_m1'])
            if m0 > 10 and m1 > 10:
                self.ui.splitter_media.setSizes([m0, m1])
        except (KeyError, ValueError):
            # Default: wide AV panel so the media buttons show without stretching;
            # the default sizeHint left it ~300 px.
            self.ui.splitter_right.setSizes([620, 420])
        # Default split: two thirds AV area, one third transcript.
        self.ui.splitter_right.setStretchFactor(0, 2)
        self.ui.splitter_right.setStretchFactor(1, 1)
        # Transcript highlight style: 'marker' or 'underline', shared with code_text via the
        # same settings key.
        saved_style = self.app.settings.get('codetext_highlight_style', None)
        self.highlight_style = saved_style if saved_style in ('marker', 'underline') else 'marker'
        # Coding bands live in the scrollable widget_tracks; the seekbar shows only the
        # tinted waveform, full width like the slider.
        self.ui.widget_seekbar.set_lanes_visible(False)
        # Constant scrollbar gutter in the tracks list and the same right inset in the
        # waveform: the playhead lands on the same x in both.
        self.ui.scrollArea_tracks.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.ui.scrollArea_tracks.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.ui.widget_seekbar.set_right_inset(
            self.ui.scrollArea_tracks.verticalScrollBar().sizeHint().width())
        self.ui.widget_tracks.segmentClicked.connect(self.track_bar_clicked)
        self.ui.widget_tracks.segmentContextRequested.connect(self.seekbar_context_menu)
        try:
            self.text_to_av_coding = self.app.settings['dialogcodeav_text_to_av'] != 'False'
        except (KeyError, AttributeError):
            self.text_to_av_coding = True
        self.ui.checkBox_text_to_av.setChecked(self.text_to_av_coding)
        self.ui.checkBox_text_to_av.stateChanged.connect(self.text_to_av_toggled)
        # Warn (once) if the user starts coding with Sync on but no transcript timestamps
        self.sync_no_timestamps_warned = False

        # Create a vlc instance with an empty vlc media player
        # Fix an Ubuntu error but, makes no difference self.instance = vlc.Instance("--no-xlib")
        # Fedora 39: NameError: no function 'libvlc_new'
        try:
            if self.app.settings.get('av_player', 'vlc') == 'qt' or vlc is None:
                # vlc stays None when python-vlc is missing: use the Qt player
                self.instance = QtMediaInstance()
            else:
                self.instance = make_vlc_instance(vlc)
                if self.instance is None:
                    raise NameError("libvlc not available")
        except (NameError, AttributeError) as name_err:
            # VLC missing: fall back to the Qt player instead of crashing
            self.instance = QtMediaInstance()
            logger.warning(f"python-vlc unavailable, using Qt player: {name_err}")

        # Ubuntu 22.04: vlc renders into the embedded frame_video
        self.mediaplayer = self.instance.media_player_new()
        self.mediaplayer.video_set_mouse_input(False)
        self.mediaplayer.video_set_key_input(False)

        # Barra interactiva (reemplaza al QSlider): clic = saltar, arrastre = seleccionar segmento
        self.ui.widget_seekbar.positionClicked.connect(self.seek_to_ms)
        self.ui.widget_seekbar.selectionChanged.connect(self.on_selection_changed)
        self.ui.widget_seekbar.segmentContextRequested.connect(self.seekbar_context_menu)
        self.ui.widget_seekbar.segmentResized.connect(self.on_segment_resized)
        # Classic position slider above the waveform, as in the original design.
        self.ui.horizontalSlider.setEnabled(False)
        self.ui.horizontalSlider.setTickPosition(QtWidgets.QSlider.TickPosition.NoTicks)
        self.ui.horizontalSlider.setMouseTracking(True)
        self.ui.horizontalSlider.sliderMoved.connect(self.slider_seek)
        # The segment status label changes from "Segment:" to a long string on the first
        # selection. Stop its width hint from forcing the controls (and the side splitter) to
        # relayout/jump: ignore its horizontal size hint so its text never resizes the panel.
        self.ui.label_segment.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            self.ui.label_segment.sizePolicy().verticalPolicy())
        self.ui.label_segment.setMinimumWidth(0)
        self.ui.pushButton_play.clicked.connect(self.play_pause)
        self.ui.pushButton_coding.pressed.connect(self.create_or_clear_segment)
        self.ui.comboBox_tracks.currentIndexChanged.connect(self.audio_track_changed)

    def show_memos(self):
        """
        Show all memos for coded transcript text in a dialog, as in code_text.
        """

        if self.transcription is None:
            return
        text_ = ""
        cur = self.app.conn.cursor()
        sql = "select code_name.name, pos0,pos1, seltext, code_text_visible.memo, code_text_visible.owner "
        sql += "from code_text_visible join code_name on code_text_visible.cid = code_name.cid "
        sql += "where length(code_text_visible.memo)>0 and fid=? order by pos0"
        cur.execute(sql, [self.transcription[0]])
        res = cur.fetchall()
        if not res:
            return
        for r in res:
            text_ += f'[{r[1]}-{r[2]}] ' + _("Code: ") + f'{r[0]}'
            text_ += " (" + r[5] + ")\n"  # coder/owner
            text_ += _("Text: ") + f"{r[3]}\n"
            text_ += _("Memo: ") + f"{r[4]}\n\n"
        ui = DialogMemo(self.app, _("Memos for transcript: ") + self.transcription[2], text_)
        ui.ui.pushButton_clear.hide()
        ui.ui.textEdit.setReadOnly(True)
        ui.exec()

    def show_annotations(self):
        """ Show all annotations for the transcript text in a dialog, as in code_text."""

        if self.transcription is None:
            return
        text_ = ""
        cur = self.app.conn.cursor()
        sql = "select substr(source.fulltext,pos0+1 ,pos1-pos0), pos0, pos1, annotation_visible.memo "
        sql += "from annotation_visible join source on annotation_visible.fid = source.id "
        sql += "where fid=? order by pos0"
        cur.execute(sql, [self.transcription[0]])
        res = cur.fetchall()
        if not res:
            return
        for r in res:
            text_ += f"[{r[1]}-{r[2]}] \n"
            text_ += _("Text: ") + f"{r[0]}\n"
            text_ += _("Annotation: ") + r[3] + "\n\n"
        ui = DialogMemo(self.app, _("Annotations for transcript: ") + self.transcription[2], text_)
        ui.ui.pushButton_clear.hide()
        ui.ui.textEdit.setReadOnly(True)
        ui.exec()

    def auto_code(self):
        """ Autocode the current transcript with the selected code, exact matches,
        pipe | splits multiple find texts. Port of the code_text auto_code. """

        if self.transcription is None or self.ui.plainTextEdit.toPlainText() == "":
            Message(self.app, _('Warning'), _("No media transcription selected"), "warning").exec()
            return
        code_item = self.ui.treeWidget.currentItem()
        if code_item is None or code_item.text(1)[0:3] == 'cat':
            Message(self.app, _('Warning'), _("No code was selected"), "warning").exec()
            return
        cid = int(code_item.text(1).split(':')[1])
        dialog = QtWidgets.QInputDialog(None)
        dialog.setStyleSheet(f"* {{font-size:{self.app.settings['fontsize']}pt}} ")
        dialog.setWindowTitle(_("Automatic coding"))
        dialog.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        dialog.setInputMode(QtWidgets.QInputDialog.InputMode.TextInput)
        dialog.setToolTip(_("Use | to code multiple texts"))
        dialog.setLabelText(_("Auto code the transcript with the current code for this text:") + "\n" + code_item.text(0))
        dialog.resize(200, 20)
        ok = dialog.exec()
        if not ok:
            return
        find_text = str(dialog.textValue())
        if find_text == "" or find_text is None:
            return
        find_texts = [t for t in dict.fromkeys(find_text.split('|')) if t != ""]
        fid = self.transcription[0]
        cur = self.app.conn.cursor()
        cur.execute("select fulltext from source where id=?", [fid])
        res = cur.fetchone()
        file_text = res[0] if res is not None and res[0] is not None else ""
        if file_text == "":
            return
        emojis = emoji.emoji_list(file_text)
        found_instances = 0
        undo_list = []
        msg = _("Autocode transcript") + f": {find_texts}\n"
        try:
            for find_txt in find_texts:
                text_starts = [m.start() for m in re.finditer(re.escape(find_txt), file_text)]
                text_ends = [m.end() for m in re.finditer(re.escape(find_txt), file_text)]
                msg += f"{self.transcription[2]}: {len(text_starts)}. "
                for index in range(len(text_starts)):
                    pos0 = text_starts[index]
                    pos1 = text_ends[index]
                    # Adjust for emoji length, as in code_text auto_code
                    for emo in emojis:
                        if emo['match_end'] < pos0:
                            pos0 += emo['match_end'] - emo['match_start']
                            pos1 += emo['match_end'] - emo['match_start']
                    item = {'cid': cid, 'fid': fid, 'seltext': str(find_txt), 'pos0': pos0, 'pos1': pos1,
                            'owner': self.app.settings['codername'], 'memo': "",
                            'date': datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")}
                    try:
                        found_instances += 1
                        cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,memo,date) "
                                    "values(?,?,?,?,?,?,?,?)",
                                    [item['cid'], item['fid'], item['seltext'], item['pos0'],
                                     item['pos1'], item['owner'], item['memo'], item['date']])
                        undo_list.append({
                            "sql": "delete from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?",
                            "cid": item['cid'], "fid": item['fid'], "pos0": item['pos0'], "pos1": item['pos1'],
                            "owner": item['owner']})
                    except sqlite3.IntegrityError as err:
                        logger.debug(_("Autocode insert error ") + str(err))
                    self.app.delete_backup = False
            self.app.conn.commit()
        except Exception as err:
            self.app.conn.rollback()
            logger.error(f"auto_code rollback. {err}")
            self.parent_textEdit.append(_("Autocoding error: ") + str(err))
            raise
        if undo_list:
            name = _("Transcript coding: ") + _("\nCode: ") + code_item.text(0)
            name += _("\nWith: ") + find_text
            self.autocode_history.insert(0, {"name": name, "sql_list": undo_list})
        self.parent_textEdit.append(msg)
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        if undo_list:
            self._emit_project_table_changes(['code_text'])

    def _record_speakers_undo(self, ctids_before):
        """ Register the Mark speakers run in the autocode undo history: deletes the
        new code_text rows and their mirrored wave segments."""

        cur = self.app.conn.cursor()
        cur.execute("select ctid, cid, fid, pos0, pos1, owner, avid from code_text "
                    "where fid=? and owner=?", [self.transcription[0], speaker_coder_name])
        new_rows = [r for r in cur.fetchall() if r[0] not in ctids_before]
        if not new_rows:
            return
        undo_list = []
        for ctid, cid, fid, pos0, pos1, owner, avid in new_rows:
            undo_list.append({'sql': "delete from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?",
                              'cid': cid, 'fid': fid, 'pos0': pos0, 'pos1': pos1, 'owner': owner})
            if avid:
                cur.execute("select id, pos0, pos1, owner from code_av where avid=?", [avid])
                seg = cur.fetchone()
                if seg:
                    undo_list.append({'sql': "delete from code_av where cid=? and id=? and pos0=? and pos1=? and owner=?",
                                      'cid': cid, 'fid': seg[0], 'pos0': seg[1], 'pos1': seg[2], 'owner': seg[3]})
        now = datetime.datetime.now().astimezone().strftime("%H:%M:%S")
        name = _("Mark speakers") + f" {now} ({len(new_rows)} " + _("codings") + ")"
        self.autocode_history.insert(0, {"name": name, "sql_list": undo_list})

    def undo_autocoding(self):
        """ Present a list of choices for the undo operation, as in code_text."""

        if not self.autocode_history:
            return
        ui = DialogSelectItems(self.app, self.autocode_history, _("Select auto-codings to undo"), "single")
        ok = ui.exec()
        if not ok:
            return
        undo = ui.get_selected()
        cur = self.app.conn.cursor()
        try:
            for i in undo['sql_list']:
                cur.execute(i['sql'], [i['cid'], i['fid'], i['pos0'], i['pos1'], i['owner']])
            self.app.conn.commit()
        except Exception:
            self.app.conn.rollback()
            raise
        self.autocode_history.remove(undo)
        self.parent_textEdit.append(_("Undo autocoding: ") + f"{undo['name']}\n")
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        # Refresh the wave: undo may have deleted mirrored speaker segments.
        if self.file_ is not None and self.media is not None:
            self.load_segments()

    def reset_search_state(self):
        """ Clear search matches when the transcript changes; stale indices would
        point into the previous text. """

        self.search_indices = []
        self.search_index = -1
        self.ui.label_search_totals.setText("0 / 0")
        self.ui.pushButton_next.setEnabled(False)
        self.ui.pushButton_previous.setEnabled(False)
        if self.ui.lineEdit_search.text() != "":
            # Re-run against the new transcript so an active term keeps working
            self.search_for_text()

    def search_for_text(self):
        """ On text changed in lineEdit_search, find matching transcript positions.
        Three or more characters. Ported from view_av. """

        if not self.search_indices:
            self.ui.pushButton_next.setEnabled(False)
            self.ui.pushButton_previous.setEnabled(False)
        self.search_indices = []
        self.search_index = -1
        search_term = self.ui.lineEdit_search.text()
        self.ui.label_search_totals.setText("0 / 0")
        if len(search_term) < 3:
            return
        flags = 0
        if not self.ui.checkBox_search_case.isChecked():
            flags |= re.IGNORECASE
        try:
            pattern = re.compile(re.escape(search_term), flags)
        except re.error as e_:
            logger.warning('Bad escape\n' + str(e_))
            return
        txt = self.ui.plainTextEdit.toPlainText()
        for match in pattern.finditer(txt):
            self.search_indices.append((match.start(), len(match.group(0))))
        if self.search_indices:
            self.ui.pushButton_next.setEnabled(True)
            self.ui.pushButton_previous.setEnabled(True)
        self.ui.label_search_totals.setText("0 / " + str(len(self.search_indices)))

    def move_to_previous_search_text(self):
        """ Move to previous search match in the transcript."""

        if not self.search_indices:
            return
        self.search_index -= 1
        if self.search_index < 0:
            self.search_index = len(self.search_indices) - 1
        self._select_search_result()

    def move_to_next_search_text(self):
        """ Move to next search match in the transcript. """

        if not self.search_indices:
            return
        self.search_index += 1
        if self.search_index == len(self.search_indices):
            self.search_index = 0
        self._select_search_result()

    def _select_search_result(self):
        """ Select the current search match in the transcript and update the totals label. """

        result = self.search_indices[self.search_index]
        cursor = self.ui.plainTextEdit.textCursor()
        cursor.setPosition(result[0])
        cursor.setPosition(cursor.position() + result[1], QtGui.QTextCursor.MoveMode.KeepAnchor)
        self.ui.plainTextEdit.setTextCursor(cursor)
        self.ui.label_search_totals.setText(str(self.search_index + 1) + " / " + str(len(self.search_indices)))

    def edit_coder_names(self):
        """ Open the coder names dialog, as in code_text. """

        ui_coder_names = DialogCoderNames(self.app, extended_options=False)
        if (ui_coder_names.exec() == QtWidgets.QDialog.DialogCode.Accepted and
                ui_coder_names.coder_names_changed):
            self.update_coder_names()

    def update_coder_names(self):
        """ Refresh coder-dependent data after a coder change: wave segments,
        transcript codings and tree counts are all filtered by codername."""

        self.ui.lineEdit_coder.setText(self.app.settings['codername'])
        if self.file_ is not None:
            self.load_segments()
            self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()

    def mark_speakers(self):
        """ Open the Mark speakers dialog on the current transcript, as code_text does;
        on accept, refresh codes and codings and offer to show the speaker coder."""

        if self.transcription is None:
            Message(self.app, _('Mark speakers'), _('No transcript for this file.'), 'critical').exec()
            return
        files_ = [{'id': self.transcription[0], 'name': self.transcription[2]}]
        ui_speaker = DialogSpeakers(self.app, files_)
        # Snapshot to make this run undoable via autocode undo.
        cur_before = self.app.conn.cursor()
        cur_before.execute("select ctid from code_text where fid=? and owner=?",
                           [self.transcription[0], speaker_coder_name])
        ctids_before = {row[0] for row in cur_before.fetchall()}
        if ui_speaker.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.update_dialog_codes_and_categories(["code_name", "code_text"])
            # With sync on, mirror the new speaker codings onto the wave (transcript timestamps).
            if getattr(self, 'text_to_av_coding', True) and self.time_positions and \
                    self.file_ is not None and self.media is not None:
                cur = self.app.conn.cursor()
                cur.execute("select cid, pos0, pos1, ifnull(seltext,'') from code_text "
                            "where fid=? and owner=? and avid is null",
                            [self.transcription[0], speaker_coder_name])
                mirrored = False
                for s_cid, s_p0, s_p1, s_text in cur.fetchall():
                    if self._create_av_segment_from_text_code(s_cid, s_p0, s_p1, s_text,
                                                              owner=speaker_coder_name):
                        mirrored = True
                self.load_segments()
                self.fill_code_counts_in_tree()
                self.get_coded_text_update_eventfilter_tooltips()
                if mirrored:
                    # One event for the whole speaker run, not one per turn
                    self._emit_project_table_changes(['code_av', 'code_text'])
            self._record_speakers_undo(ctids_before)
            if self.app.conn is not None and speaker_coder_name not in self.app.get_coder_names_in_project(
                    only_visible=True):
                msg = _(
                    'Coder "{}" is currently hidden. Do you want to make it visible, to see the speaker codings?').format(
                    speaker_coder_name)
                msg_box = Message(self.app, _('Speaker coding'), msg, 'Information')
                msg_box.setStandardButtons(
                    QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
                msg_box.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Yes)
                reply = msg_box.exec()
                if reply == QtWidgets.QMessageBox.StandardButton.Yes:
                    cur = self.app.conn
                    cur.execute('update coder_names set visibility=1 where name=?', (speaker_coder_name,))
                    cur.commit()
                    self.update_coder_names()

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

    def video_frame_menu(self, position):
        """ Context menu on the embedded video frame: screenshot. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}}")
        # Primary action saves the frame into the project; export to file is secondary.
        action_screenshot = menu.addAction(_("Save frame to project"))
        action_export_frame = menu.addAction(_("Export frame to file"))
        action = menu.exec(self.ui.frame_video.mapToGlobal(position))
        if action == action_screenshot:
            # Use VLC's own frame capture (grabbing the window gives a black strip)
            self.import_screenshot_into_project()
        elif action == action_export_frame:
            self.save_screenshot()

    def _set_video_output(self):
        """ Point VLC's video output at the current target: the floating window if
        detached, otherwise the embedded frame. """

        if self.mediaplayer is None:
            return
        target = self.video_window.dframe if self.video_window is not None else self.ui.frame_video
        if hasattr(self.mediaplayer, 'set_video_host'):
            # Qt backend: a QVideoWidget fills the same frame
            self.mediaplayer.set_video_host(target)
            return
        winid = int(target.winId())
        system = platform.system()
        if system == "Linux":
            self.mediaplayer.set_xwindow(winid)
        elif system == "Windows":
            self.mediaplayer.set_hwnd(winid)
        elif system == "Darwin":
            self.mediaplayer.set_nsobject(winid)

    def _retarget_video_output(self):
        """ Move VLC's video to the current target window. VLC binds the output to a window
        when the video output is created, so changing the handle mid-playback won't move the
        picture. We briefly restart playback at the same position to recreate the output on
        the new window. """
        mp = self.mediaplayer
        if mp is None or mp.get_media() is None:
            self._set_video_output()
            return
        was_playing = mp.is_playing()
        t = mp.get_time()
        mp.stop()
        self._set_video_output()
        mp.play()

        def _restore():
            try:
                if t and t > 0:
                    mp.set_time(int(t))
                if not was_playing:
                    mp.pause()
            except Exception:
                pass
        QtCore.QTimer.singleShot(300, _restore)

    def toggle_detach_video(self):
        """ Detach the video into a floating window, or dock it back. """

        if self.video_window is not None:
            self.reattach_video()
            return
        # Create the floating video window (with a working close button)
        self.video_window = QtWidgets.QDialog(self)
        self.video_window.setWindowTitle(_("Video"))
        self.video_window.setWindowFlags(self.video_window.windowFlags() | QtCore.Qt.WindowType.Window)
        lay = QtWidgets.QGridLayout(self.video_window)
        lay.setContentsMargins(0, 0, 0, 0)
        self.video_window.dframe = QtWidgets.QFrame(self.video_window)
        pal = self.video_window.dframe.palette()
        pal.setColor(QtGui.QPalette.ColorRole.Window, QColor(30, 30, 30))
        self.video_window.dframe.setPalette(pal)
        self.video_window.dframe.setAutoFillBackground(True)
        lay.addWidget(self.video_window.dframe, 0, 0)
        self.video_window.resize(500, 400)
        # Closing the window (X) docks the video back
        self.video_window.finished.connect(self.reattach_video)
        self.video_window.show()
        self.ui.frame_video.setVisible(False)
        self._retarget_video_output()
        self.ui.pushButton_detach.setIcon(qta.icon('mdi6.dock-window'))
        self.ui.pushButton_detach.setToolTip(_("Dock video back"))

    def reattach_video(self):
        """ Dock the floating video back into the embedded frame. """

        if self.video_window is None:
            return
        win = self.video_window
        self.video_window = None  # set first so output retargets the embedded frame
        try:
            win.finished.disconnect()
        except Exception:
            pass
        self.ui.frame_video.setVisible(not getattr(self, 'is_audio', False))
        self._retarget_video_output()
        try:
            win.close()
            win.deleteLater()
        except Exception:
            pass
        self.ui.pushButton_detach.setIcon(qta.icon('mdi6.open-in-new'))
        self.ui.pushButton_detach.setToolTip(_("Detach video to a window"))

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
        self.ui.pushButton_clear_filter_file.setVisible(True)  # for clear filter file
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

        # Resaltar segmentos en la barra (filtrando por 'importante' si procede)
        if self.important:
            self.ui.widget_seekbar.set_segments([s for s in self.segments if s['important'] == 1])
            self.ui.widget_tracks.set_code_structure(self.codes, self.categories)
            self.ui.widget_tracks.set_segments([s for s in self.segments if s['important'] == 1])
        else:
            self.ui.widget_seekbar.set_segments(self.segments)
            self.ui.widget_tracks.set_code_structure(self.codes, self.categories)
            self.ui.widget_tracks.set_segments(self.segments)

    def _strip_tree_color_icons(self):
        """ No colour chips before code names in this dialog's tree. """
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        while it.value():
            item = it.value()
            if item.text(1)[0:3] == 'cid':
                item.setIcon(0, QtGui.QIcon())
            it += 1

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
        # Counts for all VISIBLE coders (segments and text), matching wave and transcript.
        visible = self._visible_coders()
        owner_marks = ",".join("?" * len(visible))
        for c in self.codes:
            parameters = [c['cid']] + visible + [self.file_['id']]
            sql = "select code_name.catid, count(code_av.cid) from code_av join code_name " \
                "on code_name.cid=code_av.cid where code_av.cid=? and code_av.owner in (" + owner_marks + ") " \
                "and code_av.id=?"
            cur.execute(sql, parameters)
            result = cur.fetchone()
            sql_text = "select count(cid) from code_text_visible where cid=? and fid=?"
            # Media without a transcript: transcription is None, count no text codings
            tid = self.transcription[0] if self.transcription else -1
            text_parameters = [c['cid'], tid]
            cur.execute(sql_text, text_parameters)
            result_text = cur.fetchone()
            code_counts.append([c['cid'], result[0], result[1] + result_text[0]])

        # Sub-code roll-up: own counts, parent/child maps and an effective category per code
        # (a sub-code is attributed to its top ancestor's category).
        own_count = {cc[0]: cc[2] for cc in code_counts}
        code_by_cid = {c['cid']: c for c in self.codes}
        children_of = {}
        for c in self.codes:
            sup = c.get('supercid')
            if sup is not None:
                children_of.setdefault(sup, []).append(c['cid'])

        def _effective_catid(cid):
            """ Resolve a (possibly nested) code to the catid of its top ancestor code. """
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
            """ Code count rolled up with all descendant sub-codes. Memoized, cycle-safe. """
            if cid in total_cache:
                return total_cache[cid]
            total_cache[cid] = own_count.get(cid, 0)  # seed guards against cycles
            t = own_count.get(cid, 0)
            for child_cid in children_of.get(cid, []):
                t += _code_total(child_cid)
            total_cache[cid] = t
            return t

        categories = deepcopy(self.categories)
        for category in categories:
            category['count'] = 0
        # Add each code's own count to its effective category (sub-codes roll up to the
        # category of their top ancestor code, not to a raw catid that is None).
        for category in categories:
            for code in code_counts:
                if eff_catid.get(code[0]) == category['catid']:
                    category['count'] += code[2]
        # Find leaf categories, add to above categories, and gradually remove leaves
        # until only top categories are left
        sub_categories = copy(categories)
        counter = 0
        # 'and', not 'or': with 'or' the 10,000 guard never fires (cycle in code_cat =
        # infinite loop) and healthy data still spins 10,000 empty passes.
        while len(sub_categories) > 0 and counter < 10000:
            leaf_list = []
            branch_list = []
            for cat in sub_categories:
                for cat2 in sub_categories:
                    if cat['catid'] == cat2['supercatid']:
                        branch_list.append(cat)
            for category in sub_categories:
                if category not in branch_list:
                    leaf_list.append(category)
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
        self._strip_tree_color_icons()


    def tree_item_clicked(self, item, column):
        """ Use to quicky open memo. Or,
        Assign selected text on left-click on code in tree. """

        if column == 2:
            self.code_tree.add_edit_cat_or_code_memo(item)
            return
        if item.text(1)[0:3] == 'cat':
            return
        # Arrastraste una selección en la barra -> clic en el código la codifica (sin start/end)
        if self.segment.get('start_msecs') is not None and self.segment.get('end_msecs') is not None:
            self.assign_segment_to_code(item)
            self.ui.widget_seekbar.clear_selection()
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
        self.ui.pushButton_clear_filter_file.setVisible(True)  # for clear filter file
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
            self.ui.pushButton_clear_filter_file.setVisible(False)  # hide filter button when showing all
            self.ui.pushButton_clear_filter_file.setStyleSheet("")
            return
        cur = self.app.conn.cursor()
        cur.execute("select id from source where name like ? and "  # restrict to AV files only
                    "substr(mediapath,1,6) in ('/audio','/video', 'audio:', 'video:')",
                    ['%' + text_ + '%'])
        res = cur.fetchall()
        file_ids = [r[0] for r in res]
        self.get_files(file_ids)
        self.ui.pushButton_clear_filter_file.setVisible(True)  # for clear filter file
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
        ui = DialogMemo(self.app, _("Memo for file: ") + file_['name'], file_['memo'],
                        entity_type="file", entity_id=file_['id'])
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
        self._emit_project_table_changes(['source'])

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
        visible = self._visible_coders()
        sql += " where id=? "
        sql += " and code_av.owner in (" + ",".join("?" * len(visible)) + ") "
        sql += " order by pos0, pos1"
        values = [self.file_['id']] + visible
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
        # Resaltar los segmentos codificados como bandas de color sobre la barra
        self.ui.widget_seekbar.set_duration(self.media.get_duration())
        self.ui.widget_tracks.set_duration(self.media.get_duration())
        self.ui.widget_seekbar.set_segments(self.segments)
        self.ui.widget_tracks.set_code_structure(self.codes, self.categories)
        self.ui.widget_tracks.set_segments(self.segments)

    def _reset_segment_state(self):
        """ Drop any marked segment: the dict, not the drawn selection, is what
        'assign to code' uses, so a leftover from another file could code the
        wrong span. """
        self.segment = {'start': None, 'end': None, 'start_msecs': None, 'end_msecs': None,
                        'memo': "", 'important': 0, 'seltext': ""}
        self.play_segment_end = None
        self.segment_play_start = None
        self.segment_play_end = None
        self.ui.widget_seekbar.clear_selection()
        self.ui.label_segment.setText(_("Segment:"))

    def clear_file(self):
        """ When AV file removed clear all details.
        Called by null file with load_media, ManageFiles.delete, get_files """

        self.stop()
        self.media = None
        self.file_ = None
        self._reset_segment_state()
        self.setWindowTitle(_("Media coding"))
        self.ui.pushButton_play.setEnabled(False)
        self.ui.widget_seekbar.setEnabled(False)
        self.ui.horizontalSlider.setEnabled(False)
        self.ui.pushButton_coding.setEnabled(False)
        self.ui.plainTextEdit.clear()
        self.reset_search_state()
        self.transcription = None
        self.ui.pushButton_add_image_to_project.setEnabled(False)
        self.ui.pushButton_screensshot.setEnabled(False)
        self.ui.frame_video.setVisible(False)


    def change_player_backend(self, index):
        """ Rebuild the player with the chosen backend and reload the media;
        without python-vlc it reverts to Qt with a message."""

        wanted = 'qt' if index == 1 else 'vlc'
        try:
            self.mediaplayer.stop()
        except Exception:
            pass
        # Full teardown of the outgoing backend so video surfaces never stack:
        # a lingering QVideoWidget over the frame splits the screen, and a vout
        # still attached to the hwnd leaves black or frozen pixels.
        old_mp = getattr(self, 'mediaplayer', None)
        try:
            if old_mp is not None:
                if type(old_mp).__module__.endswith('media_player_qt'):
                    old_mp.release()
                else:
                    old_mp.set_media(None)
                    system = platform.system()
                    if system == "Windows":
                        old_mp.set_hwnd(0)
                    elif system == "Darwin":
                        old_mp.set_nsobject(0)
                    else:
                        old_mp.set_xwindow(0)
        except Exception:
            pass
        try:
            if wanted == 'qt':
                new_instance = QtMediaInstance()
            else:
                if vlc is None:
                    raise NameError("python-vlc not installed")
                new_instance = make_vlc_instance(vlc)
                if new_instance is None:
                    raise NameError("libvlc not available")
        except (NameError, AttributeError):
            Message(self.app, _("VLC not available"),
                    _("python-vlc is not installed. Keeping the Qt player.")).exec()
            wanted = 'qt'
            new_instance = QtMediaInstance()

            def _revert_combo():
                # Deferred: setting the index inside its own changed-handler is
                # overridden by Qt when the handler returns.
                self.ui.comboBox_player.blockSignals(True)
                self.ui.comboBox_player.setCurrentIndex(1)
                self.ui.comboBox_player.blockSignals(False)
            QtCore.QTimer.singleShot(0, _revert_combo)
        self.instance = new_instance
        self.mediaplayer = self.instance.media_player_new()
        self.mediaplayer.video_set_mouse_input(False)
        self.mediaplayer.video_set_key_input(False)
        self.mediaplayer.audio_set_volume(self.volume_slider.value())  # keep level across backends
        self.app.settings['av_player'] = wanted
        self.app.write_config_ini(self.app.settings, self.app.ai_models)
        if self.file_ is not None:
            self.load_media()

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

        self._reset_segment_state()  # nothing from the previous file survives

        title = self.file_['name'].split('/')[-1]
        self.setWindowTitle(_("Media coding: ") + title)
        self.ui.pushButton_play.setEnabled(True)
        self.ui.widget_seekbar.setEnabled(True)
        self.ui.horizontalSlider.setEnabled(True)
        # It always plays at full volume when loading, even if half-way, se make it full vol visually
        try:
            self.volume_slider.setValue(int(self.app.settings.get('dialogcodeav_volume', 100)))
        except (TypeError, ValueError):
            self.volume_slider.setValue(100)
        self.ui.pushButton_coding.setEnabled(True)
        is_audio = self.file_['mediapath'][0:6] in ("/audio", "audio:")
        self.ui.frame_video.setVisible(not is_audio)
        self.ui.pushButton_add_image_to_project.setEnabled(not is_audio)
        self.ui.pushButton_screensshot.setEnabled(not is_audio)

        # Clear comboBox tracks options and reload when playing/pausing
        self.ui.comboBox_tracks.clear()
        # Put the media in the media player
        self.mediaplayer.set_media(self.media)
        # Parse the metadata of the file
        self.media.parse()
        self._check_seek_friendliness(self.app.project_path + self.file_['mediapath']
                                      if ':' not in self.file_['mediapath'][:6]
                                      else self.file_['mediapath'][6:])
        self.mediaplayer.video_set_mouse_input(False)
        self.mediaplayer.video_set_key_input(False)
        # The media player has to be connected to the QFrame (otherwise the
        # video would be displayed in it's own window). This is platform
        # specific, so we must give the ID of the QFrame (or similar object) to
        # vlc. Different platforms have different functions for this
        self._set_video_output()
        msecs = self.media.get_duration()
        self.media_duration_text = " / " + msecs_to_hours_mins_secs(msecs)
        self.ui.label_time.setText("0.00" + self.media_duration_text)
        self.ui.widget_seekbar.set_duration(msecs)
        self.ui.widget_tracks.set_duration(msecs)
        # Onda opcional (solo Windows/macOS; ffmpeg puede fallar en algunas distros Linux)
        if platform.system() in ("Windows", "Darwin"):
            self.get_waveform()
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._update_ui_safe)
        # Watchdog: whatever kills the main timer, playback must never leave a
        # frozen bar; while media plays, restart the update timer.
        if getattr(self, '_ui_watchdog', None) is None:
            self._ui_watchdog = QtCore.QTimer(self)
            self._ui_watchdog.setInterval(1000)
            self._ui_watchdog.timeout.connect(self._revive_update_timer)
            self._ui_watchdog.start()

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
        # Track probing muted then restored the volume: apply the user's level,
        # not a hardcoded 100 (setValue alone will not fire when unchanged)
        self.mediaplayer.audio_set_volume(self.volume_slider.value())
        # Get the transcription text
        self.transcription = None
        cur = self.app.conn.cursor()
        if self.file_['av_text_id'] is not None:
            cur.execute("select id, fulltext, name from source where id=?", [self.file_['av_text_id']])
            self.transcription = cur.fetchone()
            if self.transcription is not None and \
                    not (self.transcription[2].endswith(".txt")
                         or self.transcription[2].endswith(".transcribed")):
                # Stale link after id reuse pointed at a non-transcript file
                self.transcription = None
                self.file_['av_text_id'] = None
            if self.transcription is not None and self.transcription[1] is None:
                # Old projects can hold NULL fulltext; normalise so setPlainText/regex do not crash
                self.transcription = (self.transcription[0], "", self.transcription[2])
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
            self._emit_project_table_changes(['source'])
            cur.execute("select id, fulltext, name from source where id=?", [tr_id])
            self.transcription = cur.fetchone()
            if self.transcription is not None and self.transcription[1] is None:
                # Old projects can hold NULL fulltext; normalise so setPlainText/regex do not crash
                self.transcription = (self.transcription[0], "", self.transcription[2])
        self.ui.plainTextEdit.setPlainText(self.transcription[1])
        self.reset_search_state()
        self.ui.plainTextEdit.ensureCursorVisible()
        self.get_timestamps_from_transcription()
        self.sync_no_timestamps_warned = False  # each loaded file may warn once

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

    def _visible_coders(self):
        """ Visible coders (always including the current one), as in code_text."""
        try:
            names = list(self.app.get_coder_names_in_project(only_visible=True))
        except (AttributeError, Exception):
            names = []
        me = self.app.settings['codername']
        if me not in names:
            names.append(me)
        return names

    def get_coded_text_update_eventfilter_tooltips(self):
        """ Called by load_media, update_dialog_codes_and_categories,
        Segment_Graphics_Item.link_text_to_segment.
        """

        if self.transcription is None:
            return
        # Coded text for all VISIBLE coders (code_text_visible view), as in code_text.
        values = [self.transcription[0]]
        cur = self.app.conn.cursor()
        self.code_text = []
        # seltext length, longest first, so overlapping shorter text is superimposed.
        sql = "select ct.cid, ct.fid, seltext, ct.pos0, ct.pos1, "
        sql += "ct.owner, ct.date, ifnull(ct.memo,''), ct.avid, code_av.pos0, code_av.pos1, "
        sql += "ct.important, ct.ctid "
        sql += "from code_text_visible ct left join code_av on ct.avid = code_av.avid "
        sql += " where ct.fid=? order by length(seltext) desc"
        cur.execute(sql, values)
        code_results = cur.fetchall()
        keys = 'cid', 'fid', 'seltext', 'pos0', 'pos1', 'owner', 'date', 'memo', 'avid', 'av_pos0', 'av_pos1', \
            'important', 'ctid'
        code_names = {c['cid']: (c['name'], c['color']) for c in self.codes}
        for row in code_results:
            item = dict(zip(keys, row))
            item['name'], item['color'] = code_names.get(item['cid'], (str(item['cid']), '#777777'))
            self.code_text.append(item)
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

        mmss1 = r"\[[0-9]{1,3}:[0-9][0-9]\]"  # up to 999 mins: the inserted [mm:ss] uses total minutes
        hhmmss1 = r"\[[0-9][0-9]:[0-9][0-9]:[0-9][0-9]\]"
        mmss2 = r"\[[0-9]{1,3}\.[0-9][0-9]\]"  # 
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
            # Format {00:34:20} -> colon separated
            stamp = match.group()[1:-1]
            s = stamp.split(':')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s[2])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except (IndexError, ValueError):
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
        # Consumers (transcript scroll, text<->AV sync) assume ascending text positions;
        # with mixed timestamp formats the per-pattern passes are appended out of order
        self.time_positions.sort(key=lambda tp: tp[0])

    def text_to_av_toggled(self):
        """ Checkbox: enable/disable mirroring text codings onto the wave. """
        self.text_to_av_coding = self.ui.checkBox_text_to_av.isChecked()
        self.app.settings['dialogcodeav_text_to_av'] = str(self.text_to_av_coding)
        self.sync_no_timestamps_warned = False

    def _warn_sync_without_timestamps(self):
        """ Warn once that Sync coding cannot mirror codings while the transcript has no
        timestamps. Re-warned after toggling the Sync checkbox or loading another file. """
        if self.sync_no_timestamps_warned:
            return
        self.sync_no_timestamps_warned = True
        Message(self.app, _("Sync coding") + " " * 20,
                _("Sync coding is enabled, but the transcript has no timestamps.\n"
                  "Without timestamps the coding cannot be mirrored between the text and "
                  "the wave (there is no way to map text positions to media time).\n"
                  "The coding was saved normally, without its mirror.\n"
                  "Add timestamps to the transcript, or untick Sync coding.")).exec()

    def _text_range_to_segment_ms(self, pos0_char, pos1_char):
        """ Snap a coded text range to the surrounding timestamps. The segment spans from
        the timestamp at/just before the selection start to the timestamp at/just after the
        selection end (i.e. it covers the whole block(s) the selection touches). Deliberately
        not precise to the word; the user fine-tunes it with the wave resize handles. """
        if not self.time_positions:
            return None, None
        stamps = sorted(((tp[0], tp[2]) for tp in self.time_positions), key=lambda a: a[0])
        # start = ms of the last timestamp at or before the selection start
        start_ms = stamps[0][1]
        for c, ms in stamps:
            if c <= pos0_char:
                start_ms = ms
            else:
                break
        # end = ms of the first timestamp at or after the selection end
        end_ms = None
        for c, ms in stamps:
            if c >= pos1_char:
                end_ms = ms
                break
        if end_ms is None or end_ms <= start_ms:
            dur = self.media.get_duration() if self.media is not None else 0
            end_ms = dur if dur and dur > start_ms else start_ms + 1000
        return int(start_ms), int(end_ms)

    def _create_av_segment_from_text_code(self, cid, pos0_char, pos1_char, seltext="", owner=None):
        """ EXPERIMENTAL: mirror a text coding onto the wave.
        - The wave segment memo gets [file, code name, coder] followed by the selected text.
        - The text coding memo gets the audio segment location/extent (ms, as in the db).
        If a matching wave segment already exists, the block is appended (not replaced).
        Only runs when the transcript has timestamps and media is loaded. """
        if not getattr(self, 'text_to_av_coding', True):
            return
        if not self.time_positions:
            self._warn_sync_without_timestamps()
            return
        if self.file_ is None or self.media is None:
            return
        ms0, ms1 = self._text_range_to_segment_ms(pos0_char, pos1_char)
        if ms0 is None or ms1 is None:
            return
        if ms1 <= ms0:
            ms1 = ms0 + 1
        dur = self.media.get_duration()
        if dur and dur > 0:
            ms0 = max(0, min(ms0, dur - 1))
            ms1 = max(ms0 + 1, min(ms1, dur))
        ms0, ms1 = int(ms0), int(ms1)
        owner = owner or self.app.settings['codername']
        fname = self.file_['name'] if self.file_ else ""
        codename = next((c['name'] for c in self.codes if c['cid'] == cid), str(cid))
        new_text = (seltext or "").strip()
        header = f"[{fname}, {codename}, {owner}]"
        entry = header + ("\n" + new_text if new_text else "")
        cur = self.app.conn.cursor()
        # --- Wave segment (code_av): memo = [file, code, coder] + selected text ---
        cur.execute("select avid, memo from code_av where id=? and cid=? and pos0=? and pos1=? and owner=?",
                    [self.file_['id'], cid, ms0, ms1, owner])
        existing = cur.fetchone()
        written = False
        if existing:
            avid, old_memo = existing[0], existing[1] or ""
            if entry not in old_memo:
                memo = (old_memo.rstrip() + "\n\n" + entry) if old_memo.strip() else entry
                cur.execute("update code_av set memo=? where avid=?", [memo, avid])
                self.app.conn.commit()
                self.app.delete_backup = False
                written = True
        else:
            cur.execute("insert into code_av (id, pos0, pos1, cid, memo, date, owner, important) "
                        "values(?,?,?,?,?,?,?, null)",
                        [self.file_['id'], ms0, ms1, cid, entry,
                         datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"), owner])
            avid = cur.lastrowid
            self.app.conn.commit()
            self.app.delete_backup = False
            written = True
            self.load_segments()
            self.fill_code_counts_in_tree()
        # --- Text coding (code_text): link it to the wave segment (native code_text.avid)
        #     and add the audio location/extent to its memo ---
        if self.transcription is not None:
            audio_info = (f"[Audio: {ms0}-{ms1} ms "
                          f"({msecs_to_hours_mins_secs(ms0)} - {msecs_to_hours_mins_secs(ms1)})]")
            cur.execute("select memo from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?",
                        [cid, self.transcription[0], pos0_char, pos1_char, owner])
            row = cur.fetchone()
            old_t = (row[0] if row and row[0] else "")
            tmemo = old_t
            if audio_info not in old_t:
                tmemo = (old_t.rstrip() + "\n" + audio_info) if old_t.strip() else audio_info
            cur.execute("update code_text set memo=?, avid=? where cid=? and fid=? and pos0=? and pos1=? and owner=?",
                        [tmemo, avid, cid, self.transcription[0], pos0_char, pos1_char, owner])
            self.app.conn.commit()
            self.app.delete_backup = False
            written = True
            self.get_coded_text_update_eventfilter_tooltips()
        # The caller emits one event for the whole action, so no event is sent here
        return written

    def _delete_linked_av_segment(self, item):
        """ Remove the wave segment linked to a text coding. Uses the native code_text.avid
        link so it works even after the wave band was resized. Falls back to recomputing the
        timestamp range for legacy codings that have no link. Returns True if one was removed. """
        if not getattr(self, 'text_to_av_coding', True):
            return False
        text_key = (item['cid'], item['fid'], item['pos0'], item['pos1'])
        avid = item.get('avid')
        if avid:
            cur = self.app.conn.cursor()
            # Capture the row first so Ctrl+Z can restore the band together with the text code
            cur.execute("select id, pos0, pos1, cid, memo, date, owner, important "
                        "from code_av where avid=?", [avid])
            row = cur.fetchone()
            if row is not None:
                self.undo_deleted_av_mirrors.append({'text_key': text_key, 'row': row})
            cur.execute("delete from code_av where avid=?", [avid])
            deleted = cur.rowcount
            self.app.conn.commit()
            if deleted:
                self.app.delete_backup = False
            return deleted > 0
        # Legacy fallback: no stored link, match by recomputed timestamp range
        return self._delete_av_segment_from_text_code(item['cid'], item['pos0'], item['pos1'],
                                                      text_key=text_key)

    def _delete_av_segment_from_text_code(self, cid, pos0_char, pos1_char, text_key=None):
        """ EXPERIMENTAL: remove the wave segment that mirrors a text coding, by
        recomputing the same ms range from the timestamps. Returns True if one was removed. """
        if not getattr(self, 'text_to_av_coding', True):
            return False
        if not self.time_positions or self.file_ is None or self.media is None:
            return False
        ms0, ms1 = self._text_range_to_segment_ms(pos0_char, pos1_char)
        if ms0 is None or ms1 is None:
            return False
        if ms1 <= ms0:
            ms1 = ms0 + 1
        dur = self.media.get_duration()
        if dur and dur > 0:
            ms0 = max(0, min(ms0, dur - 1))
            ms1 = max(ms0 + 1, min(ms1, dur))
        owner = self.app.settings['codername']
        cur = self.app.conn.cursor()

        def _capture(where_sql, params):
            """ Stash the rows about to be deleted, for symmetric Ctrl+Z restore. """
            if text_key is None:
                return
            cur.execute("select id, pos0, pos1, cid, memo, date, owner, important "
                        "from code_av where " + where_sql, params)
            for row_ in cur.fetchall():
                self.undo_deleted_av_mirrors.append({'text_key': text_key, 'row': row_})

        # First try exact range match (un-resized mirror segment)
        exact_where = "id=? and cid=? and pos0=? and pos1=? and owner=?"
        exact_params = [self.file_['id'], cid, int(ms0), int(ms1), owner]
        _capture(exact_where, exact_params)
        cur.execute("delete from code_av where " + exact_where, exact_params)
        deleted = cur.rowcount
        if not deleted:
            # The band may have been resized: remove the segment of this code that overlaps
            # the timestamp range of the text coding.
            overlap_where = "id=? and cid=? and owner=? and pos0 < ? and pos1 > ?"
            overlap_params = [self.file_['id'], cid, owner, int(ms1), int(ms0)]
            _capture(overlap_where, overlap_params)
            cur.execute("delete from code_av where " + overlap_where, overlap_params)
            deleted = cur.rowcount
        self.app.conn.commit()
        if deleted:
            self.app.delete_backup = False
        return deleted > 0

    def _av_ms_to_text_range(self, ms0, ms1):
        """ Map an audio ms range to a transcript char range, snapped to timestamps:
        from the end of the timestamp at/just before ms0 to the start of the timestamp
        at/just after ms1. Whitespace at the edges is trimmed. """
        if not self.time_positions:
            return None, None
        stamps = sorted(self.time_positions, key=lambda t: t[0])  # [char0, char1, ms]
        full = self.ui.plainTextEdit.toPlainText()
        start_char = stamps[0][1]
        for c0, c1, ms in stamps:
            if ms <= ms0:
                start_char = c1
            else:
                break
        end_char = None
        for c0, c1, ms in stamps:
            if ms >= ms1:
                end_char = c0
                break
        if end_char is None:
            end_char = len(full)
        while start_char < end_char and full[start_char] in ' \t\r\n':
            start_char += 1
        while end_char > start_char and full[end_char - 1] in ' \t\r\n':
            end_char -= 1
        return start_char, end_char

    def _create_text_code_from_av_segment(self, cid, ms0, ms1):
        """ EXPERIMENTAL (reverse): when a wave segment is coded, also code the transcript
        text spanning those times (snapped to timestamps). The text coding memo gets the
        audio location/extent. Only runs with the checkbox on. """
        if not getattr(self, 'text_to_av_coding', True):
            return
        if not self.time_positions:
            self._warn_sync_without_timestamps()
            return
        if self.transcription is None or ms0 is None or ms1 is None:
            return
        ms0, ms1 = int(ms0), int(ms1)
        pos0, pos1 = self._av_ms_to_text_range(ms0, ms1)
        if pos0 is None or pos1 is None or pos1 <= pos0:
            return
        full = self.ui.plainTextEdit.toPlainText()
        seltext = full[pos0:pos1]
        owner = self.app.settings['codername']
        fid = self.transcription[0]
        cur = self.app.conn.cursor()
        # Enrich the wave segment memo with [file, code, coder] + text (same as the forward direction)
        fname = self.file_['name'] if self.file_ else ""
        codename = next((c['name'] for c in self.codes if c['cid'] == cid), str(cid))
        header = f"[{fname}, {codename}, {owner}]"
        new_text = seltext.strip()
        entry = header + ("\n" + new_text if new_text else "")
        cur.execute("select avid, memo from code_av where id=? and cid=? and pos0=? and pos1=? and owner=?",
                    [self.file_['id'], cid, ms0, ms1, owner])
        row = cur.fetchone()
        avid = row[0] if row else None
        if row:
            old_memo = row[1] or ""
            if entry not in old_memo:
                memo = (old_memo.rstrip() + "\n\n" + entry) if old_memo.strip() else entry
                cur.execute("update code_av set memo=? where avid=?", [memo, avid])
                self.app.conn.commit()
                self.app.delete_backup = False
        # Create the text coding (with the audio location in its memo), linked by code_text.avid.
        cur.execute("select ctid from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?",
                    [cid, fid, pos0, pos1, owner])
        already = cur.fetchone()
        if already:
            # Already coded there: just (re)link it to this wave segment
            cur.execute("update code_text set avid=? where ctid=?", [avid, already[0]])
            self.app.conn.commit()
            self.app.delete_backup = False
            return True
        audio_info = (f"[Audio: {ms0}-{ms1} ms "
                      f"({msecs_to_hours_mins_secs(ms0)} - {msecs_to_hours_mins_secs(ms1)})]")
        now = datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        try:
            cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,memo,date,important,avid) "
                        "values(?,?,?,?,?,?,?,?,?,?)",
                        (cid, fid, seltext, pos0, pos1, owner, audio_info, now, None, avid))
            self.app.conn.commit()
            self.app.delete_backup = False
        except Exception as e_:
            logger.debug(str(e_))
            print(e_)
            return
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        # The caller emits one event for the whole action, so no event is sent here
        return True

    def _seek_to_clicked_timestamp(self, event):
        """ If a left click landed on a transcript timestamp, seek the media to that time.
        Releases that finish a text selection (for coding) are ignored. """
        if self.mediaplayer is None or not self.time_positions:
            return
        if self.ui.plainTextEdit.textCursor().hasSelection():
            return
        cursor = self.ui.plainTextEdit.cursorForPosition(event.position().toPoint())
        char = cursor.position()
        for c0, c1, ms in self.time_positions:
            if c0 <= char <= c1:
                self.seek_to_ms(ms)
                break

    def _check_seek_friendliness(self, media_path):
        """ Widely spaced keyframes make every seek rebuild seconds of frames
        in any player. Warn in the seek bar tooltip and widen coalescing. """
        self._seek_coalesce_ms = 120
        self._keyframe_gap = None
        self.ui.widget_seekbar.setToolTip("")

        def measure():
            # Reading keyframes decodes part of the file: off the UI thread so
            # loading a file never blocks playback controls
            self._keyframe_gap = keyframe_interval_seconds(media_path) or 0.0

        threading.Thread(target=measure, daemon=True).start()

    def _apply_keyframe_hint(self):
        """ Pick up the background keyframe measurement (once) and warn when
        seeking on this file will be imprecise. """
        gap = self._keyframe_gap
        if not gap:
            return
        self._keyframe_gap = None
        logger.debug(f"keyframe interval {gap:.2f}s")
        if gap < 2.0:
            return
        self._seek_coalesce_ms = 400
        hint = _("Keyframes in this file are about %s seconds apart, so seeking "
                 "may stall or repeat frames. Re-encoding it with denser "
                 "keyframes gives precise navigation.") % f"{gap:.1f}"
        self.ui.widget_seekbar.setToolTip(hint)
        logger.info(hint)

    def _vlc_apply_seek(self, ms, duration):
        """ First request seeks at once; further rapid ones (a drag) coalesce
        into a single seek. """
        self._vlc_seek_pending = (ms, duration)
        timer = getattr(self, '_vlc_seek_timer', None)
        if timer is None:
            timer = QtCore.QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(self._vlc_fire_seek)
            self._vlc_seek_timer = timer
        if not timer.isActive():
            self._vlc_fire_seek()  # first request goes straight through
        timer.setInterval(getattr(self, '_seek_coalesce_ms', 120))
        timer.start()

    def _vlc_fire_seek(self):
        pending = getattr(self, '_vlc_seek_pending', None)
        if pending is None:
            return
        ms, duration = pending
        self._vlc_seek_pending = None
        mp = self.mediaplayer
        if mp is None or type(mp).__module__.endswith('media_player_qt'):
            return
        self._vlc_target_ms = ms
        self._vlc_last_seek_at = time.monotonic()
        try:
            mp.set_position(ms / duration)
            if mp.is_playing() == 0:
                try:
                    mp.next_frame()  # paused vlc keeps the stale frame
                except Exception:
                    pass
        except Exception:
            pass

    def seek_to_ms(self, ms):
        """ Seek to an absolute position in milliseconds (from the seek bar).
        Fixes the time-label lag of the original slider set_position. """

        if self.mediaplayer is None or self.mediaplayer.get_media() is None:
            return
        duration = self.mediaplayer.get_media().get_duration()
        if duration <= 0:
            return
        ms = max(0, min(int(ms), duration))
        if type(self.mediaplayer).__module__.endswith('media_player_qt'):
            self.mediaplayer.set_position(ms / duration)
        else:
            self._vlc_apply_seek(ms, duration)
        self.ui.label_time.setText(msecs_to_hours_mins_secs(ms) + self.media_duration_text)
        self.ui.widget_seekbar.set_position(ms)
        self.ui.widget_tracks.set_position(ms)
        self.sync_position_slider(ms, duration)

    def slider_seek(self, value):
        """ Seek from the classic position slider (0-1000) above the waveform.
        Routed through seek_to_ms so slider, playhead and time label stay in sync. """

        if self.mediaplayer is None or self.mediaplayer.get_media() is None:
            return
        duration = self.mediaplayer.get_media().get_duration()
        if duration <= 0:
            return
        self.seek_to_ms(int(value / 1000 * duration))

    def sync_position_slider(self, msecs, duration):
        """ Reflect the playhead on the classic slider without re-triggering a seek. """

        if duration <= 0:
            return
        self.ui.horizontalSlider.blockSignals(True)
        if duration is None or duration <= 0:
            return
        # Clamp: VLC/bookmarks can briefly report out-of-range msecs (int32 overflow)
        value = max(0, min(1000, int(msecs / duration * 1000)))
        self.ui.horizontalSlider.setValue(value)
        self.ui.horizontalSlider.blockSignals(False)

    def track_bar_clicked(self, seg):
        """ A bar in the tracks list selects its time span (same path as a drag on the
        waveform) and moves the playhead to its start. """

        pos0 = int(seg.get('pos0', 0))
        pos1 = int(seg.get('pos1', 0))
        if pos1 <= pos0:
            return
        self.ui.widget_seekbar.clear_resize()
        self.seek_to_ms(pos0)
        self.ui.widget_seekbar.set_selection(pos0, pos1)
        self.on_selection_changed(pos0, pos1)

    def on_selection_changed(self, start_ms, end_ms):
        """ The seek bar reported a dragged selection (or its clearing with 0,0).
        Feeds the existing self.segment so the normal 'assign to code' flow (right
        click a code in the tree) works. """

        if end_ms - start_ms < 50:  # clic / selección nula
            self.segment['start'] = None
            self.segment['start_msecs'] = None
            self.segment['end'] = None
            self.segment['end_msecs'] = None
            self.ui.label_segment.setText(_("Segment:"))
            self.ui.pushButton_coding.setText(_("Start segment"))
            return
        start_ms, end_ms = int(start_ms), int(end_ms)
        self.segment['start'] = msecs_to_hours_mins_secs(start_ms)
        self.segment['start_msecs'] = start_ms
        self.segment['end'] = msecs_to_hours_mins_secs(end_ms)
        self.segment['end_msecs'] = end_ms
        self.segment['memo'] = ""
        self.segment['important'] = None
        self.segment['seltext'] = ""
        self.ui.pushButton_coding.setText(_("Clear segment"))
        self.ui.label_segment.setText(
            _("Segment: ") + self.segment['start'] + " - " + self.segment['end'] + "  " +
            _("(click a code to assign)"))

    def seekbar_context_menu(self, segment, global_pos):
        """ Right click on the seek bar. 'segment' is the coded segment (colour band)
        under the cursor, or None. Offers playing the current selection and full
        management of the coded segment under the cursor. """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}}")
        act_play_sel = act_clear = act_mark = None
        recent_actions = {}  # QAction -> cid, for the "recent code" submenu
        act_play_seg = act_memo = act_important = act_start = act_end = act_delete = act_resize = None
        act_add_code = act_replace_code = act_new_code = act_add_additional = None
        if self.segment['start_msecs'] is not None and self.segment['end_msecs'] is not None:
            act_play_sel = menu.addAction(_("Play selection"))
            act_mark = menu.addAction(_("Mark (Q)"))
            if self.recent_codes:
                recent_menu = menu.addMenu(_("Mark with recent code (R)"))
                for rc in self.recent_codes:
                    a = recent_menu.addAction(rc['name'])
                    recent_actions[a] = rc['cid']
            act_new_code = menu.addAction(_("Mark with new code"))
            act_clear = menu.addAction(_("Clear selection"))
        if segment is not None:
            if not menu.isEmpty():
                menu.addSeparator()
            act_play_seg = menu.addAction(_("Play segment"))
            act_memo = menu.addAction(_("Memo for segment"))
            act_important = menu.addAction(_("Important mark"))
            act_add_code = menu.addAction(_("Add code to segment"))
            act_add_additional = menu.addAction(_("Add additional code"))
            act_replace_code = menu.addAction(_("Change code"))
            act_resize = menu.addAction(_("Resize"))
            act_start = menu.addAction(_("Edit start position"))
            act_end = menu.addAction(_("Edit end position"))
            act_delete = menu.addAction(_("Delete segment"))
        if menu.isEmpty():
            return
        action = menu.exec(global_pos)
        if action is None:
            return
        if action == act_play_sel:
            self._play_range(self.segment['start_msecs'], self.segment['end_msecs'])
        elif action == act_mark:
            self._mark_wave_selection()
        elif action == act_new_code:
            self._mark_wave_selection_with_new_code()
        elif action in recent_actions:
            self._assign_selection_to_cid(recent_actions[action])
            self.ui.widget_seekbar.clear_selection()
        elif action == act_clear:
            self.clear_segment()
            self.ui.widget_seekbar.clear_selection()
        elif action == act_play_seg:
            self.play_segment(segment)
        elif action == act_memo:
            self.edit_segment_memo(segment)
        elif action == act_important:
            self.set_segment_importance(segment)
        elif action == act_add_code:
            self.segment_add_code_from_tree(segment)
        elif action == act_add_additional:
            self.segment_add_additional_code(segment)
        elif action == act_replace_code:
            self.change_segment_code(segment)
        elif action == act_resize:
            self.ui.widget_seekbar.activate_resize(segment)
        elif action == act_start:
            self.edit_segment_start(segment)
        elif action == act_end:
            self.edit_segment_end(segment)
        elif action == act_delete:
            self.delete_segment(segment)

    def _mark_wave_selection(self):
        """ Mark the current wave selection with the code selected in the tree (the 'Mark (Q)'
        action). Mirrors the text 'Mark' behaviour. """
        if self.segment['start_msecs'] is None or self.segment['end_msecs'] is None:
            return
        item = self.ui.treeWidget.currentItem()
        if item is not None and item.text(1)[0:3] == 'cid':
            self._assign_selection_to_cid(int(item.text(1).split(':')[1]))
            self.ui.widget_seekbar.clear_selection()
        else:
            QtWidgets.QMessageBox.information(self, _("Mark"), _("Select a code in the tree first."))

    def _mark_wave_selection_with_new_code(self):
        """ Create a new code and assign the current wave selection to it, as the
        transcript 'Mark with new code' does (no keyboard shortcut). """

        if self.segment['start_msecs'] is None or self.segment['end_msecs'] is None:
            return
        tree_item = self.ui.treeWidget.currentItem()
        catid = None
        if tree_item is not None and tree_item.text(1)[0:3] == 'cat':
            catid = int(tree_item.text(1)[6:])
        codes_copy = deepcopy(self.codes)
        self.code_tree.add_code(catid)
        new_code = None
        for c in self.codes:
            if c not in codes_copy:
                new_code = c
        if new_code is None:
            return  # not a new code
        self._assign_selection_to_cid(new_code['cid'])
        self.ui.widget_seekbar.clear_selection()

    def segment_add_additional_code(self, segment):
        """ Add another code to this segment's span, chosen from a selection dialog
        (codes already on the exact span are excluded)."""

        cur = self.app.conn.cursor()
        cur.execute("select cid from code_av where id=? and pos0=? and pos1=? and owner=?",
                    [segment['id'], segment['pos0'], segment['pos1'], self.app.settings['codername']])
        present = {row[0] for row in cur.fetchall()}
        choices = [{'id': c['cid'], 'name': c['name']} for c in
                   sorted(self.codes, key=lambda x: x['name'].lower()) if c['cid'] not in present]
        if not choices:
            Message(self.app, _("Add additional code"), _("No other codes available.")).exec()
            return
        ui_dsi = DialogSelectItems(self.app, choices, _("Select additional code"), "single")
        ok = ui_dsi.exec()
        if not ok:
            return
        selection = ui_dsi.get_selected()
        if not selection:
            return
        sql = "insert into code_av (id, pos0, pos1, cid, memo, date, owner, important) values(?,?,?,?,?,?,?, null)"
        cur.execute(sql, [segment['id'], segment['pos0'], segment['pos1'], selection['id'], "",
                          datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                          self.app.settings['codername']])
        self.app.conn.commit()
        self.app.delete_backup = False
        self.load_segments()
        self.fill_code_counts_in_tree()
        self._emit_project_table_changes(['code_av'])

    def _wave_recent_codes_menu(self, global_pos):
        """ Popup of recent codes to assign to the current wave selection (the 'Mark with
        recent code (R)' action). """
        if self.segment['start_msecs'] is None or self.segment['end_msecs'] is None:
            return
        if not self.recent_codes:
            return
        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}}")
        actions = {}
        for rc in self.recent_codes:
            a = menu.addAction(rc['name'])
            actions[a] = rc['cid']
        action = menu.exec(global_pos)
        if action in actions:
            self._assign_selection_to_cid(actions[action])
            self.ui.widget_seekbar.clear_selection()

    def _play_range(self, start_ms, end_ms):
        """ Play media from start_ms, pausing at end_ms (reuses play_segment_end). """

        if self.mediaplayer is None or self.mediaplayer.get_media() is None:
            return
        duration = self.mediaplayer.get_media().get_duration()
        if duration <= 0:
            return
        self.play_segment_end = int(end_ms)
        if self.mediaplayer.play() == -1:
            self.play_segment_end = None
            return
        self.mediaplayer.set_position(int(start_ms) / duration)
        self.ui.pushButton_play.setIcon(qta.icon('mdi6.pause'))
        self.is_paused = False
        self.timer.start()

    def _waveform_png_path(self):
        """ Per-file cached waveform image path: audio/waveform_<fileid>.png """
        return os.path.join(self.app.project_path, "audio", f"waveform_{self.file_['id']}.png")

    def _waveform_media_abs_path(self):
        """ Absolute path of the current media file, for waveform generation. """
        abs_path = ""
        if self.file_['mediapath'][0:6] in ('/audio', '/video'):
            abs_path = self.app.project_path + self.file_['mediapath']
        elif self.file_['mediapath'][0:6] in ('audio:', 'video:'):
            abs_path = self.file_['mediapath'][6:]
        return abs_path

    def get_waveform(self):
        """ Show the waveform image in the seek bar. Uses a per-file cached image
        (audio/waveform_<id>.png), pre-built on import; if missing (e.g. older files or
        video), it is generated once and cached. If ffmpeg is unavailable or generation
        fails, the seek bar shows a hint and stays fully usable (playback/seeking/coding
        work via VLC). Skipped on Linux in load_media. """

        sb = self.ui.widget_seekbar
        waveform_path = self._waveform_png_path()
        # Cancel a pending generation poll from a previously loaded file
        old_timer = getattr(self, '_wf_timer', None)
        if old_timer is not None:
            old_timer.stop()
            old_timer.deleteLater()
            self._wf_timer = None
        if waveform_png_is_current(waveform_path):
            pm = QtGui.QPixmap()
            pm.load(waveform_path)
            if pm.isNull():  # unreadable/corrupt image
                sb.set_waveform_pixmap(None)
                sb.set_no_waveform_message(_("Waveform could not be generated"))
                return
            sb.set_no_waveform_message("")
            sb.set_waveform_pixmap(pm)
            return
        if not waveform_backend_available():
            # ffmpeg not installed: cannot build the image. Everything else still works.
            sb.set_waveform_pixmap(None)
            sb.set_no_waveform_message("")  # silent: bar still works for seeking
            if not getattr(self.app, '_ffmpeg_warned', False):
                logger.warning("ffmpeg not found: waveform images disabled. "
                               "Playback, seeking and coding still work.")
                self.app._ffmpeg_warned = True
            return
        # Worker thread build; a QTimer polls for completion in the GUI thread.
        sb.set_waveform_pixmap(None)
        sb.set_no_waveform_message(_("Generating waveform..."))
        thread = generate_waveform_png_async(self._waveform_media_abs_path(), waveform_path,
                                             waveform_colour(self.app.settings['stylesheet']))
        file_id = self.file_['id']
        timer = QtCore.QTimer(self)
        timer.setInterval(300)

        def _check_waveform_done():
            if thread.is_alive():
                return
            timer.stop()
            timer.deleteLater()
            if getattr(self, '_wf_timer', None) is timer:
                self._wf_timer = None
            if self.file_ is None or self.file_['id'] != file_id:
                return  # the user switched files while generating
            if os.path.exists(waveform_path):
                pm = QtGui.QPixmap()
                pm.load(waveform_path)
                if pm.isNull():  #
                    sb.set_waveform_pixmap(None)
                    sb.set_no_waveform_message(_("Waveform could not be generated"))
                    return
                sb.set_no_waveform_message("")
                sb.set_waveform_pixmap(pm)
            else:
                sb.set_waveform_pixmap(None)
                sb.set_no_waveform_message(_("Waveform could not be generated"))

        timer.timeout.connect(_check_waveform_done)
        self._wf_timer = timer
        timer.start()

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
        self.ui.widget_seekbar.set_position(0)
        self.ui.widget_tracks.set_position(0)
        self.ui.horizontalSlider.blockSignals(True)
        self.ui.horizontalSlider.setValue(0)
        self.ui.horizontalSlider.blockSignals(False)
        self.play_segment_end = None

        # set combobox display of audio track to the first one, or leave it blank if it contains no items
        if self.ui.comboBox_tracks.count() > 0:
            self.ui.comboBox_tracks.setCurrentIndex(0)

    def show_volume_popup(self):
        """ Show the vertical volume slider above the volume button. """

        hint = self.volume_menu.sizeHint()
        button = self.ui.pushButton_volume
        pos = button.mapToGlobal(QtCore.QPoint(0, -hint.height()))
        self.volume_menu.exec(pos)

    def set_volume(self, volume):
        """ Set the volume, update the button icon and remember the level. """

        if self.mediaplayer is not None:
            self.mediaplayer.audio_set_volume(volume)
        self.app.settings['dialogcodeav_volume'] = volume
        if volume == 0:
            icon = 'mdi6.volume-off'
        elif volume < 34:
            icon = 'mdi6.volume-low'
        elif volume < 67:
            icon = 'mdi6.volume-medium'
        else:
            icon = 'mdi6.volume-high'
        self.ui.pushButton_volume.setIcon(qta.icon(icon))
        self.ui.pushButton_volume.setToolTip(_("Volume") + f": {volume}%")

    def audio_track_changed(self):
        """ Audio track changed.
        The video needs to be playing/paused before the combobox is filled with track options.
        The combobox only has positive integers."""

        txt = self.ui.comboBox_tracks.currentText()
        if txt == "":
            txt = 1
        success = self.mediaplayer.audio_set_track(int(txt))

    def _revive_update_timer(self):
        """ Watchdog: revive a dead update timer while media plays. """
        try:
            if self.mediaplayer is not None and self.mediaplayer.is_playing() \
                    and not self.timer.isActive():
                logger.warning("update timer found dead while playing: revived")
                self.timer.start()
        except Exception:
            pass

    def _update_ui_safe(self):
        """ Armoured tick: an exception is logged once, the bar keeps alive. """
        try:
            self.update_ui()
        except Exception as err:
            if not getattr(self, '_update_ui_error_logged', False):
                self._update_ui_error_logged = True
                logger.exception(f"update_ui tick failed (bar kept alive): {err}")

    def _vlc_display_ms(self, msecs):
        """ vlc reports the previous position for a few ticks after a seek:
        show the requested one until playback converges. """
        target = getattr(self, '_vlc_target_ms', None)
        if target is None:
            return msecs
        if abs(msecs - target) <= 400 or \
                time.monotonic() - getattr(self, '_vlc_last_seek_at', 0) > 3.0:
            self._vlc_target_ms = None
            return msecs
        return target

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

        # Set the seek-bar playhead to the current media position
        if getattr(self, '_keyframe_gap', None):
            self._apply_keyframe_hint()
        msecs = self._vlc_display_ms(self.mediaplayer.get_time())
        self.ui.widget_seekbar.set_position(msecs)
        self.ui.widget_tracks.set_position(msecs)
        media = self.mediaplayer.get_media()
        if media is not None:
            self.sync_position_slider(msecs, media.get_duration())

        # While marking a segment with the buttons (Start pressed, End not yet), grow the
        # drawn selection to the current playhead so it is visible as it plays.
        if self.segment['start_msecs'] is not None and self.segment['end_msecs'] is None:
            self.ui.widget_seekbar.set_selection(self.segment['start_msecs'], msecs)

        # update label_time
        self.ui.label_time.setText(msecs_to_hours_mins_secs(msecs) + self.media_duration_text)

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
        """ Stop the vlc player on close. """

        self.update_sizes()
        if self.video_window is not None:
            self.reattach_video()
        self.stop()
        self.app.write_config_ini(self.app.settings, self.app.ai_models)  # persist volume/sizes

    def changeEvent(self, event):
        """ When this window regains focus (e.g. returning from another program), clear any
        drag/resize that was left mid-action so mouse input isn't stuck. """
        try:
            if event.type() == QtCore.QEvent.Type.ActivationChange and self.isActiveWindow() \
                    and QtWidgets.QApplication.mouseButtons() == QtCore.Qt.MouseButton.NoButton:
                self.ui.widget_seekbar.cancel_interaction()
        except Exception:
            pass
        super().changeEvent(event)

    def update_sizes(self):
        """ Called by splitter resizes and play/pause """

        sizes = self.ui.splitter.sizes()
        self.app.settings['dialogcodeav_splitter0'] = sizes[0]
        self.app.settings['dialogcodeav_splitter1'] = sizes[2]  # as 30 is for size[1] for the buttons
        sizes = self.ui.splitter_2.sizes()
        self.app.settings['dialogcodeav_splitter_h0'] = sizes[0]
        self.app.settings['dialogcodeav_splitter_h1'] = sizes[1]
        vsizes = self.ui.splitter_right.sizes()
        if len(vsizes) >= 2:
            self.app.settings['dialogcodeav_splitter_v0'] = vsizes[0]
            self.app.settings['dialogcodeav_splitter_v1'] = vsizes[1]
        msizes = self.ui.splitter_media.sizes()
        if len(msizes) >= 2:
            self.app.settings['dialogcodeav_splitter_m0'] = msizes[0]
            self.app.settings['dialogcodeav_splitter_m1'] = msizes[1]

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
            # Start drawing the selection on the wave (grows with playback until End is set)
            self.ui.widget_seekbar.set_selection(time_msecs, time_msecs)
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
            txt = (_("Segment: ") + str(self.segment['start']) + " - " + self.segment['end'] +
                   "  " + _("(click a code to assign)"))
            self.ui.label_segment.setText(txt)
            # Draw the final selection on the wave
            self.ui.widget_seekbar.set_selection(self.segment['start_msecs'], self.segment['end_msecs'])

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
        if self.show_codes_like_filter == "":  #
            self.ui.pushButton_clear_filter_code.setVisible(False)  # for clear filter code
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
        if self.show_codes_colour_filter == "":  #
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
        non-matching parent code. Returns True if this item or any descendant matches.
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
            # Recurse first so we know whether any descendant matches.
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

    def _emit_project_table_changes(self, tables):
        """Notify other open dialogs about changed project tables."""

        if getattr(self.app, "project_events", None) is not None:
            self.app.project_events.emit_table_changes(tables, source=self)

    def update_dialog_codes_and_categories(self, tables: list[str]|None = None):
        """Refresh the local dialog after code/category changes and optionally notify other dialogs.

        Args:
            tables: Optional list of changed database table names to emit to the project event bus.
                Use an empty list for a local-only refresh without notifying other dialogs.
        """

        self.get_codes_and_categories()
        self.code_tree.fill_tree()
        self.load_segments()
        self.unlight()
        self.highlight()
        self.get_coded_text_update_eventfilter_tooltips()

        self._emit_project_table_changes(tables)

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
            self.code_tree.fill_tree()
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

        # Esc hides any active resize handles
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
            self.code_tree.add_category(supercatid)
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
        # Tree widget menu item keys F2 - F6, handled by the shared controller.
        if self.ui.treeWidget.hasFocus():
            if self.code_tree.handle_key_press(event):
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
                if self.undo_deleted_codes[0].get('is_segment'):
                    self.restore_unmarked_segment()
                else:
                    self.restore_unmarked_text_codes()
                return
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
        # Quick mark selected text
        if key == QtCore.Qt.Key.Key_Q and selected_text != "":
            self.mark()
            return
        # Quick mark the wave selection (when no transcript text is selected)
        if key == QtCore.Qt.Key.Key_Q and self.segment.get('start_msecs') is not None \
                and self.segment.get('end_msecs') is not None:
            self._mark_wave_selection()
            return
        # Recent codes context menu
        if key == QtCore.Qt.Key.Key_R and self.file_ is not None and self.ui.plainTextEdit.textCursor().selectedText() != "":
            self.textedit_recent_codes_menu(self.ui.plainTextEdit.cursorRect().topLeft())
            return
        # Recent codes for the wave selection (when no transcript text is selected)
        if key == QtCore.Qt.Key.Key_R and self.segment.get('start_msecs') is not None \
                and self.segment.get('end_msecs') is not None:
            sb = self.ui.widget_seekbar
            self._wave_recent_codes_menu(sb.mapToGlobal(sb.rect().center()))
            return

    def _unique_screenshot_name(self, in_project_images=False):
        """ Build a unique screenshot file name based on file name + media time (incl. ms).
        Avoids 'name already exists' clashes when capturing within the same second.
        Returns (name, full_path). """

        base = self.file_['name'] if self.file_ else "frame"
        time_msecs = self.mediaplayer.get_time()
        hms = msecs_to_hours_mins_secs(time_msecs)
        ms = int(time_msecs) % 1000
        stem = f"{base}_{hms}-{ms:03d}"
        name = f"{stem}.png"
        n = 1
        while True:
            if in_project_images:
                path = os.path.join(self.app.project_path, "images", name)
                cur = self.app.conn.cursor()
                cur.execute("select 1 from source where name=?", [name])
                clash = cur.fetchone() is not None or os.path.exists(path)
            else:
                path = os.path.join(self.app.settings['directory'], name)
                clash = os.path.exists(path)
            if not clash:
                return name, path
            n += 1
            name = f"{stem}_{n}.png"

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
        self.ui.widget_seekbar.set_position(result[1])  # the bar works in absolute msecs
        self.ui.widget_tracks.set_position(result[1])
        if self.media is not None:
            self.sync_position_slider(result[1], self.media.get_duration())
        self.mediaplayer.pause()
        cursor = self.ui.plainTextEdit.textCursor()
        cursor.setPosition(result[2])
        endpos = result[2] - 1
        if endpos < 0:
            endpos = 0
        cursor.setPosition(endpos, QtGui.QTextCursor.MoveMode.KeepAnchor)
        self.ui.plainTextEdit.setTextCursor(cursor)

    def save_screenshot(self):
        """ Save a snapshot of the current video frame. The user picks the export path;
        the suggested name is unique (file name + media time incl. ms). """

        if self.mediaplayer is None or self.mediaplayer.get_media() is None:
            return
        image_name, _default_path = self._unique_screenshot_name()
        exp_directory = ExportDirectoryPathDialog(self.app, image_name)
        filepath = exp_directory.filepath
        if filepath is None:
            return
        # width=0, height=0 -> native video resolution (no stretching / black bars)
        ok = self.mediaplayer.video_take_snapshot(0, filepath, 0, 0)
        if ok != 0 or not os.path.exists(filepath):
            Message(self.app, _("Screenshot"),
                    _("Could not capture the video frame. Try while the video is playing."),
                    "warning").exec()
            return
        Message(self.app, _("Frame saved"), filepath).exec()
        self.parent_textEdit.append(_("Screenshot saved: ") + filepath)

    def import_screenshot_into_project(self):
        """ Capture the current video frame and add it as an image source. """

        if self.mediaplayer is None or self.mediaplayer.get_media() is None:
            return
        image_name, file_path = self._unique_screenshot_name(in_project_images=True)
        ok = self.mediaplayer.video_take_snapshot(0, file_path, 0, 0)
        if ok != 0 or not os.path.exists(file_path):
            Message(self.app, _("Screenshot"),
                    _("Could not capture the video frame. Try while the video is playing."),
                    "warning").exec()
            return
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
        self._emit_project_table_changes(['source'])

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

        # Left-click on a transcript timestamp -> seek the media to that time
        if object_ is self.ui.plainTextEdit.viewport() and \
                event.type() == QtCore.QEvent.Type.MouseButtonRelease and \
                event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._seek_to_clicked_timestamp(event)
            return False  # let the text edit also handle the click normally

        if object_ is self.ui.treeWidget.viewport():
            if event.type() == QtCore.QEvent.Type.Drop:
                item = self.ui.treeWidget.currentItem()
                # event position is QPointF, itemAt requires toPoint
                parent = self.ui.treeWidget.itemAt(event.position().toPoint())
                self.code_tree.item_moved_update_data(item, parent)
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
        self._emit_project_table_changes(['code_text'])

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
        self._emit_project_table_changes(['code_text'])

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
        self._emit_project_table_changes(['code_text'])

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
        self._emit_project_table_changes(['code_text'])

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

    def add_av_tree_menu_actions(self, menu, selected):
        """ Append A/V page-specific entries to the shared tree context menu.
        Assign segment to code: only on a code item; on a category this inserted
        the catid as a cid. """

        if self.segment['end_msecs'] is not None and self.segment['start_msecs'] is not None \
                and selected is not None and selected.text(1)[0:3] == 'cid':
            action = QtGui.QAction(_("Assign segment to code"), menu)
            action.triggered.connect(lambda checked=False, sel=selected: self.assign_segment_to_code(sel))
            first = menu.actions()[0] if menu.actions() else None
            if first is not None:
                menu.insertAction(first, action)
            else:
                menu.addAction(action)

    def assign_segment_to_code(self, selected):
        """ Assign time segment to the code of the selected tree item. """

        if self.file_ is None or self.segment['start_msecs'] is None or self.segment['end_msecs'] is None:
            self.clear_segment()
            return
        if selected is None or selected.text(1)[0:3] != 'cid':
            # Defence in depth: never insert a catid (or nothing) as a code id
            Message(self.app, _("No selection"), _("No code selected in tree")).exec()
            return
        cid = int(selected.text(1).split(':')[1])
        self._assign_selection_to_cid(cid)

    def _assign_selection_to_cid(self, cid):
        """ Assign the current wave selection (self.segment) to a code id. Inserts an entry
        into code_av, mirrors it to the transcript, then clears the segment for re-use. """

        if self.file_ is None or self.segment['start_msecs'] is None or self.segment['end_msecs'] is None:
            self.clear_segment()
            return
        sql = "insert into code_av (id, pos0, pos1, cid, memo, date, owner, important) values(?,?,?,?,?,?,?, null)"
        values = [self.file_['id'], self.segment['start_msecs'],
                  self.segment['end_msecs'], cid, self.segment['memo'],
                  datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                  self.app.settings['codername']]
        cur = self.app.conn.cursor()
        cur.execute(sql, values)
        self.app.conn.commit()
        self.load_segments()
        # Reverse mirror: also code the transcript text spanning this segment's times
        mirrored = self._create_text_code_from_av_segment(cid, self.segment['start_msecs'],
                                                          self.segment['end_msecs'])
        self.clear_segment()
        self.app.delete_backup = False
        self.fill_code_counts_in_tree()
        self._emit_project_table_changes(['code_av', 'code_text'] if mirrored else ['code_av'])

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
        self.ui.widget_seekbar.set_selection(None, None)

    def unlight(self):
        """ Remove all text highlighting from current file. """

        if self.transcription is None or self.ui.plainTextEdit.toPlainText() == "":
            return
        cursor = self.ui.plainTextEdit.textCursor()
        cursor.setPosition(0, QtGui.QTextCursor.MoveMode.MoveAnchor)
        cursor.setPosition(len(self.transcription[1]) - 1, QtGui.QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(QtGui.QTextCharFormat())

    def _underline_contrast_color(self, color):
        """ Code colour adjusted so the underline contrasts with the transcript
        background (lightened or darkened, keeping the hue). """
        base = self.ui.plainTextEdit.viewport().palette().color(QtGui.QPalette.ColorRole.Base)
        col = QtGui.QColor(color)
        if not col.isValid():
            col = QtGui.QColor('#888888')
        # background claro -> oscurecer; oscuro -> aclarar
        if base.lightness() >= 128:
            while col.lightness() > 110 and col.lightness() > 0:
                col = col.darker(115)
        else:
            while col.lightness() < 150 and col.lightness() < 255:
                col = col.lighter(115)
        return col

    def set_highlight_style(self, style):
        """ Set the transcript highlight style ('marker'/'underline') and persist it
        in the key shared with code_text. """
        if style not in ('marker', 'underline') or style == self.highlight_style:
            return
        self.highlight_style = style
        self.app.settings['codetext_highlight_style'] = style
        if self.transcription is not None and self.ui.plainTextEdit.toPlainText() != "":
            self.unlight()
            self.highlight()

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
            if self.highlight_style == 'underline':
                # Dashed underline in the code colour, contrast adjusted.
                fmt.setUnderlineStyle(QtGui.QTextCharFormat.UnderlineStyle.DashUnderline)
                fmt.setUnderlineColor(self._underline_contrast_color(color))
            else:
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

        cursor = self.ui.plainTextEdit.cursorForPosition(position)
        selected_text = self.ui.plainTextEdit.textCursor().selectedText()
        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        menu.setToolTipsVisible(True)
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
        action_new_code = None
        action_new_invivo_code = None
        action_copy_metadata = None

        for item in self.code_text:
            if item['pos0'] <= cursor.position() <= item['pos1']:
                if item['avid'] is not None:
                    action_play_text = QtGui.QAction(_("Play text"))
                    # TODO select which avid if multiple coded here
                    play_text_avid = item['avid']
                action_unmark = QtGui.QAction(_("Unmark (U)"))
                action_code_memo = QtGui.QAction(_("Memo coded text (M)"))
                action_change_code = QtGui.QAction(_("Change code"))
                action_show_handles = QtGui.QAction(_("Resize"))
            if item['pos0'] <= cursor.position() <= item['pos1']:
                if item['important'] is None or item['important'] > 1:
                    action_important = QtGui.QAction(_("Add important mark (I)"))
                if item['important'] == 1:
                    action_not_important = QtGui.QAction(_("Remove important mark"))
        # Menu order as in code_text: mark, then actions on existing codings, then
        # annotate/copy/AI, with the A/V specific items last.
        if selected_text != "":
            if self.ui.treeWidget.currentItem() is not None:
                action_mark = menu.addAction(_("Mark (Q)"))
            # Use up to 5 recent codes
            if len(self.recent_codes) > 0:
                submenu = menu.addMenu(_("Mark with recent code (R)"))
                for item in self.recent_codes:
                    submenu.addAction(item['name'])
            action_new_code = menu.addAction(_("Mark with new code (N)"))
            action_new_invivo_code = menu.addAction(_("in vivo code (V)"))
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
            action_annotate = menu.addAction(_("Annotate (A)"))
            action_copy = menu.addAction(_("Copy to clipboard"))
            action_copy_metadata = menu.addAction(_("Copy with metadata"))
            # AI text analysis submenu, as in code_text.
            submenu_ai_text_analysis = menu.addMenu(_("AI Text Analysis"))
            submenu_ai_text_analysis.setToolTipsVisible(True)
            if self._ai_menu_options_enabled():
                submenu_ai_text_analysis.setEnabled(True)
                prompts_catalog = AiAgentPromptsCatalog(self.app)
                prompt_records = prompts_catalog.list_visible_prompt_variants(prompt_type='text_analysis')
                self._populate_text_analysis_prompt_menu(submenu_ai_text_analysis, prompts_catalog, prompt_records)
                if len(prompt_records) > 0:
                    submenu_ai_text_analysis.addSeparator()
                ac = submenu_ai_text_analysis.addAction(_('Edit text analysis prompts'))
                ac.setProperty('submenu', 'ai_text_analysis_prompts')
            else:
                submenu_ai_text_analysis.setEnabled(False)
        if selected_text == "" and self.is_annotated(cursor.position()):
            action_edit_annotate = menu.addAction(_("Edit annotation"))
        action_set_bookmark = None
        if self.transcription is not None:
            action_set_bookmark = menu.addAction(_("Set bookmark (B)"))
        # Highlight style: offer the one NOT active, as in code_text.
        style_menu = menu.addMenu(_("Highlight style"))
        action_style_marker = None
        action_style_underline = None
        if self.highlight_style != 'marker':
            action_style_marker = style_menu.addAction(_("Marker"))
        if self.highlight_style != 'underline':
            action_style_underline = style_menu.addAction(_("Underline"))
        if action_play_text:
            menu.addSeparator()
            menu.addAction(action_play_text)
        action_video_position_timestamp = -1
        for ts in self.time_positions:
            if ts[0] <= cursor.position() <= ts[1]:
                action_video_position_timestamp = menu.addAction(_("Video position to timestamp"))
        action_mark_speakers = None
        if self.transcription is not None:
            if not menu.isEmpty():
                menu.addSeparator()
            action_mark_speakers = menu.addAction(_("Mark speakers"))
        action = menu.exec(self.ui.plainTextEdit.mapToGlobal(position))
        if action is None:
            return
        if action_mark_speakers is not None and action == action_mark_speakers:
            self.mark_speakers()
            return
        if selected_text != "" and action == action_copy:
            self.copy_selected_text_to_clipboard()
            return
        if selected_text != "" and action == action_copy_metadata:
            self.copy_selected_text_to_clipboard(True)
            return
        if action_new_code is not None and action == action_new_code:
            self.mark_with_new_code()
            return
        if action_new_invivo_code is not None and action == action_new_invivo_code:
            self.mark_with_new_code(in_vivo=True)
            return
        if action_style_marker is not None and action == action_style_marker:
            self.set_highlight_style('marker')
            return
        if action_style_underline is not None and action == action_style_underline:
            self.set_highlight_style('underline')
            return
        if action_set_bookmark is not None and action == action_set_bookmark:
            cur = self.app.conn.cursor()
            cur.execute("update project set bookmarkfile=?, bookmarkpos=?",
                        [self.transcription[0], cursor.position()])
            self.app.conn.commit()
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
        if action.property('submenu') == 'ai_text_analysis':
            if self.transcription is None:
                Message(self.app, _('Warning'), _("No transcript for this file."), "warning").exec()
                return
            selected_text = self.ui.plainTextEdit.textCursor().selectedText()
            start_pos = self.ui.plainTextEdit.textCursor().selectionStart()
            ai_chat_signal_emitter.newTextChatSignal.emit(int(self.transcription[0]),
                                                          self.transcription[2],
                                                          selected_text,
                                                          start_pos,
                                                          action.data())
            return
        if action.property('submenu') == 'ai_text_analysis_prompts':
            DialogAiEditPrompts(self.app, 'text_analysis').exec()
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
            if item['pos0'] <= position <= item['pos1']:
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
        replacement_code = ui.get_selected()
        if not replacement_code:
            return
        cur = self.app.conn.cursor()
        sql = "update code_text set cid=? where ctid=?"
        try:
            cur.execute(sql, [replacement_code['cid'], text_item['ctid']])
            # Keep the mirrored wave segment consistent with the new code.
            if text_item.get('avid'):
                cur.execute("update code_av set cid=?, date=? where avid=?",
                            [replacement_code['cid'],
                             datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                             text_item['avid']])
            self.app.conn.commit()
        except sqlite3.IntegrityError:
            # A coding with the replacement code already exists at this exact position.
            # Do not fail silently: it made "Replace code" look broken.
            self.app.conn.rollback()
            Message(self.app, _("Replace code"),
                    _("Cannot replace: this text is already coded with the selected code."),
                    "warning").exec()
            return
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()
        self.load_segments()
        self.fill_code_counts_in_tree()
        self._emit_project_table_changes(['code_av', 'code_text'])

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
        self._emit_project_table_changes(['code_text'])

    def coded_text_memo(self, position=None):
        """ Add or edit a memo for this coded text.
        Called by: textEdit context menu option
        param:
            position : textEdit cursor position """

        if self.transcription is None:
            return
        coded_text_list = []
        for item in self.code_text:
            if item['pos0'] <= position <= item['pos1']:
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
                    and text_item['pos1'] == i['pos1'] and text_item['owner'] == i['owner']:
                i['memo'] = memo
        self.app.delete_backup = False
        self.get_coded_text_update_eventfilter_tooltips()
        self._emit_project_table_changes(['code_text'])

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

    def copy_selected_text_to_clipboard(self, metadata=False):
        """ Copy text to clipboard, optionally with metadata (file, positions, codes
        and reference), as code_text does; the file here is the transcript."""

        text = self.ui.plainTextEdit.textCursor().selectedText()
        if metadata and self.transcription is not None:
            start_pos = self.ui.plainTextEdit.textCursor().selectionStart()
            end_pos = self.ui.plainTextEdit.textCursor().selectionEnd()
            text += f"\nFile: {self.transcription[2]} [{start_pos} - {end_pos}] "
            code_names = {c['cid']: c['name'] for c in self.codes}
            codes = ""
            for coded in self.code_text:
                if coded['pos0'] <= start_pos <= coded['pos1'] or coded['pos0'] <= end_pos <= coded['pos1'] or \
                        (start_pos <= coded['pos0'] and coded['pos1'] <= end_pos):
                    codes += f"{code_names.get(coded['cid'], '')}; "
            if codes:
                text += f"\nCodes: {codes}"
            cur = self.app.conn.cursor()
            cur.execute("select risid from source where source.id=?", [self.transcription[0]])
            ris_res = cur.fetchone()
            if ris_res and ris_res[0]:
                ris = Ris(self.app)
                ris.get_references(ris_res[0])
                if ris.refs:
                    text += "\n" + _("Reference: ") + ris.refs[0]['apa']
        cb = QtWidgets.QApplication.clipboard()
        cb.setText(text)

    @staticmethod
    def _text_analysis_prompt_menu_leaf(relative_path: str) -> str:
        """Return the leaf label for one text-analysis prompt menu item."""

        normalized = str(relative_path if relative_path is not None else "").replace("\\", "/").strip("/")
        if normalized == "":
            return ""
        return normalized.rsplit("/", 1)[-1]

    def _text_analysis_prompt_folder_icon(self):
        """Return the same folder icon used by the prompt library."""

        return qta.icon("mdi.folder-outline", color=self.app.highlight_color())

    def _text_analysis_prompt_file_icon(self, menu):
        """Return the same prompt file icon used by the prompt library."""

        text_color = menu.palette().color(QtGui.QPalette.ColorRole.Text).name()
        return qta.icon("mdi6.script-text-outline", color=text_color)

    def _populate_text_analysis_prompt_menu(self, menu, prompts_catalog, prompt_records) -> None:
        """Populate one prompt menu, mirroring the prompt library folder structure."""

        menu_tree = {"prompts": [], "folders": {}}
        for prompt in prompt_records:
            relative_path = prompts_catalog.prompt_name_within_type(prompt.name)
            parts = [part for part in relative_path.split("/") if part != ""]
            if len(parts) == 0:
                continue
            current_branch = menu_tree
            for part in parts[:-1]:
                current_branch = current_branch["folders"].setdefault(part, {"prompts": [], "folders": {}})
            current_branch["prompts"].append((relative_path, prompt))

        def populate_branch(parent_menu, branch) -> None:
            for branch_relative_path, prompt_record in branch["prompts"]:
                action = parent_menu.addAction(self._text_analysis_prompt_menu_leaf(branch_relative_path))
                action.setToolTip(prompt_record.description)
                action.setIcon(self._text_analysis_prompt_file_icon(parent_menu))
                action.setProperty('submenu', 'ai_text_analysis')
                action.setData(prompt_record)
            for folder_name, child_branch in branch["folders"].items():
                submenu = parent_menu.addMenu(folder_name)
                submenu.setToolTipsVisible(True)
                submenu.setIcon(self._text_analysis_prompt_folder_icon())
                populate_branch(submenu, child_branch)

        populate_branch(menu, menu_tree)

    def _ai_menu_options_enabled(self) -> bool:
        """Return whether AI-specific text-coding actions should be enabled."""

        return self.app.settings.get('ai_enable', 'False') == 'True'

    def mark_with_new_code(self, in_vivo=False):
        """ Create a new code and mark the selected transcript text with it; with
        in_vivo the selection itself is the code name (code_text port). """

        tree_item = self.ui.treeWidget.currentItem()
        catid = None
        if tree_item is not None and tree_item.text(1)[0:3] == 'cat':
            catid = int(tree_item.text(1)[6:])
        codes_copy = deepcopy(self.codes)
        if not in_vivo:
            self.code_tree.add_code(catid)
        else:
            self.code_tree.add_code(catid, code_name=self.ui.plainTextEdit.textCursor().selectedText())
        new_code = None
        for c in self.codes:
            if c not in codes_copy:
                new_code = c
        if new_code is None and not in_vivo:
            return  # not a new code
        if new_code is None and in_vivo:
            for c in self.codes:
                if c['name'] == self.ui.plainTextEdit.textCursor().selectedText():
                    new_code = c
        if new_code is None:
            return
        self.recursive_set_current_item(self.ui.treeWidget.invisibleRootItem(), new_code['name'])
        self.mark()

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
            coded_written = True
        except Exception as e_:
            logger.debug(str(e_))
            print(e_)
            coded_written = False
        # update coded, filter for tooltip
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        # EXPERIMENTAL: mirror this text coding onto the wave via bracketing timestamps
        mirrored = self._create_av_segment_from_text_code(cid, coded['pos0'], coded['pos1'], coded['seltext'])
        if coded_written or mirrored:
            # One event for the whole mark, covering the wave mirror when it wrote
            self._emit_project_table_changes(['code_text', 'code_av'] if mirrored else ['code_text'])

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
        cur = self.app.conn.cursor()
        try:
            # Skip if an identical segment already exists (repeated Ctrl+Z or re-marked
            # segment). Prevents silent duplicates in code_av.
            cur.execute("select 1 from code_av where id=? and cid=? and pos0=? and pos1=? and owner=?",
                        [item['id'], item['cid'], item['pos0'], item['pos1'], item['owner']])
            if cur.fetchone() is None:
                sql = "insert into code_av (id, pos0, pos1, cid, memo, date, owner, important) " \
                      "values(?,?,?,?,?,?,?,?)"
                values = [item['id'], item['pos0'], item['pos1'], item['cid'], item['memo'],
                          item['date'], item['owner'], item['important']]
                cur.execute(sql, values)
                cur.execute("select last_insert_rowid()")
                new_avid = cur.fetchone()[0]
                # Restore the text codings that delete_segment removed in mirror mode,
                # re-linked to the new avid.
                for tr in getattr(self, 'undo_deleted_text_mirrors', []):
                    # tr: cid, fid, seltext, pos0, pos1, owner, memo, date, important
                    cur.execute("select 1 from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?",
                                (tr[0], tr[1], tr[3], tr[4], tr[5]))
                    if cur.fetchone() is not None:
                        continue
                    cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,memo,date,important,avid) "
                                "values(?,?,?,?,?,?,?,?,?,?)", list(tr) + [new_avid])
            self.app.conn.commit()
        except Exception as e_:
            self.app.conn.rollback()
            logger.warning(f"restore_unmarked_segment: {e_}")
        finally:
            self.undo_deleted_codes = []
            self.undo_deleted_text_mirrors = []
        self.load_segments()
        self.clear_segment()
        self.get_coded_text_update_eventfilter_tooltips()
        self.app.delete_backup = False
        self.fill_code_counts_in_tree()
        self._emit_project_table_changes(['code_av', 'code_text'])

    def restore_unmarked_text_codes(self):
        """ Restore the last deleted code(s).
        One code or multiple, depends on what was selected when the unmark method was used.
        The event filer method checks for text or segment coding.
        Requires self.undo_deleted_codes """

        if not self.undo_deleted_codes:
            return
        cur = self.app.conn.cursor()
        # Mirror wave segments captured by the unmark helpers, grouped per text coding
        mirrors_by_key = {}
        for m in getattr(self, 'undo_deleted_av_mirrors', []):
            mirrors_by_key.setdefault(m['text_key'], []).append(m['row'])
        av_restored = False
        try:
            for item in self.undo_deleted_codes:
                # Skip if an identical coding exists (re-mark, stale undo buffer, repeated Ctrl+Z).
                # Prevents IntegrityError on the code_text UNIQUE constraint.
                cur.execute("select 1 from code_text where cid=? and fid=? and pos0=? and pos1=? and owner=?",
                            (item['cid'], item['fid'], item['pos0'], item['pos1'], item['owner']))
                if cur.fetchone() is not None:
                    continue
                key = (item['cid'], item['fid'], item['pos0'], item['pos1'])
                new_avid = None
                for row in mirrors_by_key.pop(key, []):
                    # row: id, pos0, pos1, cid, memo, date, owner, important
                    cur.execute("select 1 from code_av where id=? and pos0=? and pos1=? and cid=? and owner=?",
                                (row[0], row[1], row[2], row[3], row[6]))
                    if cur.fetchone() is not None:
                        continue  # mirror segment already present, avoid duplicating it
                    cur.execute("insert into code_av (id, pos0, pos1, cid, memo, date, owner, important) "
                                "values(?,?,?,?,?,?,?,?)", list(row))
                    cur.execute("select last_insert_rowid()")
                    new_avid = cur.fetchone()[0]
                    av_restored = True
                cur.execute("insert into code_text (cid,fid,seltext,pos0,pos1,owner,\
                    memo,date, important, avid) values(?,?,?,?,?,?,?,?,?,?)", (item['cid'], item['fid'],
                                                                       item['seltext'], item['pos0'], item['pos1'],
                                                                       item['owner'],
                                                                       item['memo'], item['date'], item['important'],
                                                                       new_avid))
            self.app.conn.commit()
        except Exception as e_:
            self.app.conn.rollback()
            logger.warning(f"restore_unmarked_text_codes: {e_}")
        finally:
            # Always clear the undo buffers, so a failed restore cannot be retried
            # against a partially applied transaction.
            self.undo_deleted_codes = []
            self.undo_deleted_av_mirrors = []
        if av_restored:
            self.load_segments()
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        self._emit_project_table_changes(['code_av', 'code_text'] if av_restored else ['code_text'])

    def unmark(self, location):
        """ Remove code marking by this coder from selected text in current file.
        Keep a record for ctrl Z restore.
        param:
            location: integer """

        if self.transcription is None or self.ui.plainTextEdit.toPlainText() == "":
            return
        unmarked_list = []
        # All visible codings (e.g. Mark speakers), as in code_text.
        for item in self.code_text:
            if item['pos0'] <= location <= item['pos1']:
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
        self.undo_deleted_av_mirrors = []  # will be filled by the mirror-delete helpers

        # Delete from db, remove from coding and update highlights
        cur = self.app.conn.cursor()
        av_removed = False
        for item in to_unmark:
            cur.execute("delete from code_text where cid=? and pos0=? and pos1=? and owner=? and fid=?",
                        (item['cid'], item['pos0'], item['pos1'], item['owner'], item['fid']))
            self.app.conn.commit()
            # Mirror removal: drop the wave segment linked to this text coding
            if self._delete_linked_av_segment(item):
                av_removed = True
        self.app.conn.commit()
        if av_removed:
            self.load_segments()

        # Update filter for tooltip and update code colours
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        self.app.delete_backup = False
        self._emit_project_table_changes(['code_av', 'code_text'] if av_removed else ['code_text'])

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
                self._emit_project_table_changes(['annotation'])
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
            self._emit_project_table_changes(['annotation'])
            return

        # If blank delete the annotation
        if item['memo'] == "":
            cur = self.app.conn.cursor()
            cur.execute("delete from annotation where pos0 = ?", (item['pos0'],))
            self.app.conn.commit()
            self.annotations = self.app.get_annotations()
            self.parent_textEdit.append(_("Annotation removed from position ")
                                        + f"{item['pos0']}" + _(" for: ") + self.transcription[2])
            self._emit_project_table_changes(['annotation'])
        self.get_coded_text_update_eventfilter_tooltips()

    # Segment menu. A hack to fix when pyinstaller Segment.contextMenu does not work.
    def label_segment_menu(self):
        """ Menu on the Label segment. This is in place because the segment context menu
        does not work when packed with pyinstaller """

        if self.file_ is None or not self.segments:
            return
        for s in self.segments:
            s['name'] = f"{msecs_to_hours_mins_secs(s['pos0'])}-{msecs_to_hours_mins_secs(s['pos1'])}: {s['codename']}"
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
        action_add_code = menu.addAction(_('Add code to segment'))
        action_replace_code = menu.addAction(_('Change code'))
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
        if action == action_add_code:
            self.segment_add_code_from_tree(segment)
            return
        if action == action_replace_code:
            self.segment_replace_code_from_tree(segment)
            return
        if action == action_change_start_pos:
            self.edit_segment_start(segment)
            return
        if action == action_change_end_pos:
            self.edit_segment_end(segment)
            return

    def segment_add_code_from_tree(self, segment):
        """ Add another code (the one selected in the tree) to this segment's time span.
        Mirrors SegmentGraphicsItem.add_code so the wave bands offer the same options."""

        selected = self.ui.treeWidget.currentItem()
        if selected is None or 'catid' in selected.text(1):
            Message(self.app, _("No selection"), _("No code selected in tree")).exec()
            return
        cid = int(selected.text(1).split(":")[1])
        cur = self.app.conn.cursor()
        # Avoid an exact duplicate coding (same code, file, span, coder)
        cur.execute("select 1 from code_av where id=? and pos0=? and pos1=? and cid=? and owner=?",
                    [segment['id'], segment['pos0'], segment['pos1'], cid,
                     self.app.settings['codername']])
        if cur.fetchone() is not None:
            Message(self.app, _("Duplicate"), _("This segment is already coded with this code.")).exec()
            return
        sql = "insert into code_av (id, pos0, pos1, cid, memo, date, owner, important) values(?,?,?,?,?,?,?, null)"
        values = [segment['id'], segment['pos0'], segment['pos1'], cid, "",
                  datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                  self.app.settings['codername']]
        cur.execute(sql, values)
        self.app.conn.commit()
        self.app.delete_backup = False
        self.load_segments()
        self.fill_code_counts_in_tree()
        self._emit_project_table_changes(['code_av'])

    def change_segment_code(self, segment):
        """ Change this segment's code to another one chosen from a selection dialog,
        as code_text does (it used to require selecting the code in the tree). """

        codes_list = [c for c in deepcopy(self.codes) if c['cid'] != segment.get('cid')]
        if not codes_list:
            return
        ui = DialogSelectItems(self.app, codes_list, _("Select replacement code"), "single")
        ok = ui.exec()
        if not ok:
            return
        replacement_code = ui.get_selected()
        if not replacement_code:
            return
        cid = replacement_code['cid']
        cur = self.app.conn.cursor()
        cur.execute("update code_av set cid=?, date=? where avid=?",
                    [cid, datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                     segment['avid']])
        # Keep the mirrored text coding(s) consistent with the new code.
        try:
            cur.execute("update code_text set cid=? where avid=?", [cid, segment['avid']])
        except sqlite3.IntegrityError:
            # Same text span already coded with the new code by this coder: unlink instead.
            cur.execute("update code_text set avid=null where avid=?", [segment['avid']])
        self.app.conn.commit()
        self.app.delete_backup = False
        self.load_segments()
        self.get_coded_text_update_eventfilter_tooltips()
        self.fill_code_counts_in_tree()
        self._emit_project_table_changes(['code_av', 'code_text'])

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
        self._emit_project_table_changes(['code_av'])

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
        self._emit_project_table_changes(['code_av'])

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
        tmp_seg = deepcopy(segment)  # the deleted segment, not the selection dict
        tmp_seg['is_segment'] = True  # Need to distinguish from text coding
        self.undo_deleted_codes = [tmp_seg]
        self.undo_deleted_text_mirrors = []
        sql = "delete from code_av where avid=?"
        values = [segment['avid']]
        cur = self.app.conn.cursor()
        cur.execute(sql, values)
        # Mirror (consistent both ways): if Text<->wave is on, also remove the linked text
        # coding; otherwise keep QualCoder's native behaviour of just unlinking it.
        if getattr(self, 'text_to_av_coding', True):
            # Capture the linked text codings first so Ctrl+Z restores them too.
            cur.execute("select cid, fid, seltext, pos0, pos1, owner, ifnull(memo,''), date, important "
                        "from code_text where avid=?", values)
            self.undo_deleted_text_mirrors = cur.fetchall()
            cur.execute("delete from code_text where avid=?", values)
        else:
            cur.execute("update code_text set avid=null where avid=?", values)
        self.app.conn.commit()
        self.get_coded_text_update_eventfilter_tooltips()
        self.app.delete_backup = False
        self.load_segments()
        self._emit_project_table_changes(['code_av', 'code_text'])

    def edit_segment_start(self, segment):
        """ Edit segment start time. """

        i, ok_pressed = QtWidgets.QInputDialog.getInt(self, _("Segment start in mseconds"),
                                                      _("Edit time in milliseconds\n1000 msecs = 1 second:"),
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
        self._emit_project_table_changes(['code_av'])

    def edit_segment_end(self, segment):
        """ Edit segment end time """

        duration = self.media.get_duration()
        i, ok_pressed = QtWidgets.QInputDialog.getInt(None, _("Segment end in mseconds"),
                                                      _("Edit time in milliseconds\n1000 msecs = 1 second:"),
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
        self._emit_project_table_changes(['code_av'])

    def on_segment_resized(self, segment, new_pos0, new_pos1):
        """ A coded band was resized by dragging an edge on the wave. Persist and reload. """

        if self.file_ is None or segment is None:
            return
        avid = segment.get('avid')
        if avid is None or new_pos1 <= new_pos0:
            return
        cur = self.app.conn.cursor()
        cur.execute("update code_av set pos0=?, pos1=? where avid=?",
                    [int(new_pos0), int(new_pos1), avid])
        self.app.conn.commit()
        self.app.delete_backup = False
        self.load_segments()
        self._emit_project_table_changes(['code_av'])

    # --- handles experimental
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
        # start teardrop tip is at its top-right corner -> shift left by full width
        h_start.move(rect_start.x() - h_start.width(), rect_start.y())
        self.active_handles.append(h_start)

        # Create end handle
        cursor_end = self.ui.plainTextEdit.textCursor()
        cursor_end.setPosition(min(len(self.ui.plainTextEdit.toPlainText()), code_to_handle['pos1']))
        rect_end = self.ui.plainTextEdit.cursorRect(cursor_end)
        h_end = CodeResizeHandle(self.ui.plainTextEdit, False, code_to_handle, self)
        # end teardrop tip is at its top-left corner -> align directly to the cursor x
        h_end.move(rect_end.x(), rect_end.y())
        self.active_handles.append(h_end)

    def hide_resize_handles(self):
        """ Remove all active resize handles from the screen. """
        for h in getattr(self, 'active_handles', []):
            h.hide()
            h.deleteLater()
        self.active_handles = []

    def hide_handles_if_cursor_outside(self):
        """ Hide the text resize handles when the caret moves outside the coded segment
        they belong to (i.e. when the user clicks elsewhere in the transcript). """
        if not getattr(self, 'active_handles', []):
            return
        pos = self.ui.plainTextEdit.textCursor().position()
        for h in self.active_handles:
            item = getattr(h, 'code_item', None)
            if item and item['pos0'] <= pos <= item['pos1']:
                return  # caret still inside the coded segment -> keep handles
        self.hide_resize_handles()

    # Reposition active handles to the code's current pos0/pos1 without recreating them.
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
            self._emit_project_table_changes(['code_text'])
        except sqlite3.IntegrityError:
            self.app.conn.rollback()
            # Revert in-memory positions to undo temporary highlight
            code_item['pos0'] = orig_pos0
            code_item['pos1'] = orig_pos1
            Message(self.app, _("Duplicate Error"),
                    _("This code already exists at this exact location."), "warning").exec()
        # Keep handles active after a successful resize so the user can
        # adjust the other end without re-triggering the action
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
        self.code_av_dialog._emit_project_table_changes(['code_av'])

    def replace_code(self):
        """ Change code via the selection dialog (code_text style). """
        self.code_av_dialog.change_segment_code(self.segment)

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
        filename = str(Path(self.app.settings['directory']) / filename)
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
        # Argument list, no shell: paths with quotes or shell metacharacters are safe.
        # -y avoids ffmpeg hanging on its overwrite prompt (stdin is not attached).
        ffmpeg_command = ['ffmpeg', '-y', '-i', mediapath,
                          '-ss', str(self.segment["pos0"] / 1000),
                          '-to', str(self.segment["pos1"] / 1000),
                          '-c', 'copy', filepath]
        try:
            subprocess.run(ffmpeg_command, timeout=60,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if not os.path.exists(filepath):
                Message(self.app, _("Segment export"), _("Export failed"), "warning").exec()
                return
            self.code_av_dialog.parent_textEdit.append(_("A/V segment exported: ") + filepath)
            Message(self.app, _("Segment exported"), filepath).exec()
        except Exception as e_:
            logger.error(str(e_))
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
        self.code_av_dialog._emit_project_table_changes(['code_av'])
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
            self.code_av_dialog._emit_project_table_changes(['code_text'])
        except Exception as e_:
            print(e_)
        self.code_av_dialog.text_for_segment = {'cid': None, 'fid': None, 'seltext': None, 'pos0': None, 'pos1': None,
                                                'owner': None, 'memo': None, 'date': None, 'avid': None}
        # Update codes and filter for tooltip
        self.code_av_dialog.get_coded_text_update_eventfilter_tooltips()
        self.set_segment_tooltip()

    def edit_segment_start(self):
        """ Edit segment start time. """

        i, ok_pressed = QtWidgets.QInputDialog.getInt(None, _("Segment start in mseconds"),
                                                      _("Edit time in milliseconds\n1000 msecs = 1 second:"),
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
        self.code_av_dialog._emit_project_table_changes(['code_av'])

    def edit_segment_end(self):
        """ Edit segment end time """

        duration = self.code_av_dialog.media.get_duration()
        i, ok_pressed = QtWidgets.QInputDialog.getInt(None, _("Segment end in mseconds"),
                                                      _("Edit time in milliseconds\n1000 msecs = 1 second:"),
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
        self.code_av_dialog._emit_project_table_changes(['code_av'])

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
        self.code_av_dialog.undo_deleted_text_mirrors = []  # This path only unlinks text codings

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
        self.code_av_dialog._emit_project_table_changes(['code_av', 'code_text'])

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
        self.code_av_dialog._emit_project_table_changes(['code_av'])
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


