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

from copy import copy
import datetime
# import difflib  # Use diff_match_patch as it is 20x faster. Keep this in case its needed later.
import diff_match_patch
import json
import logging
import os
import platform
import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/
import re
import threading
import time

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from .GUI.ui_dialog_view_av import Ui_Dialog_view_av
from .helpers import NumberBar, msecs_to_hours_mins_secs, Message, ExportDirectoryPathDialog
from .html_parser import html_to_text  # Homologate transcript formats with Manage files
from .select_items import DialogSelectItems
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


class DialogViewAV(QtWidgets.QDialog):
    """ View Audio and Video using VLC. View and edit displayed memo.
    Mouse events did not work when the vlc play is in this dialog.
    Mouse events do work with the vlc player in a separate modal dialog.
    Transcribing the text file can be done here also.

    Linked a/v have 'audio:' or 'video:' at start of mediapath
    """

    def __init__(self, app, file_, parent=None):

        """ file_ contains: {name, mediapath, owner, id, date, memo, fulltext}
        A separate modal dialog is created to display the video.
        """

        self.app = app
        self.file_ = file_
        # Search variables
        self.search_indices = []  # A list of tuples of (text name, match.start, match length)
        self.search_index = 0
        # Media variables
        self.label = None
        self.media_duration_text = ""
        self.displayframe = None
        self.ddialog = None
        self.instance = None
        self.mediaplayer = None
        self.media = None
        self.abs_path = ""
        if self.file_['mediapath'][0:6] in ('/audio', '/video'):
            self.abs_path = self.app.project_path + self.file_['mediapath']
        if self.file_['mediapath'][0:6] in ('audio:', 'video:'):
            self.abs_path = self.file_['mediapath'][6:]
        self.is_paused = True
        # Variables used for editing the transcribed text file
        self.transcription = None # Will be a tuple of id, fulltext
        self.codetext = []
        self.annotations = []
        self.casetext = []
        self.prev_text = ""
        self.no_codes_annotes_cases = True
        self.code_deletions = []
        self.time_positions = []
        self.speaker_list = []  # loaded from / persisted to speakers.json
        self.speaker_formats = {}  # per-speaker identifier

        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_view_av()
        self.ui.setupUi(self)
        # Main splitter is horizontal: video/speakers/snippets left, writing + waveform right.
        self.ui.splitter_v.setStretchFactor(0, 0)
        self.ui.splitter_v.setStretchFactor(1, 1)
        try:
            t0 = int(self.app.settings['viewav_splitter0'])
            t1 = int(self.app.settings['viewav_splitter1'])
            if t0 > 10 and t1 > 10:
                self.ui.splitter_v.setSizes([t0, t1])
        except (KeyError, ValueError):
            self.ui.splitter_v.setSizes([420, 900])
        self.ui.splitter_v.splitterMoved.connect(self._save_splitter_sizes)
        # All section layouts persist, as in code_text.
        try:
            l0 = int(self.app.settings['viewav_splitl0'])
            l1 = int(self.app.settings['viewav_splitl1'])
            # l0 can legitimately be 0 (video hidden for audio-only files)
            if l0 >= 0 and l1 > 10:
                self.ui.splitter_left.setSizes([l0, l1])
        except (KeyError, ValueError):
            pass
        try:
            w0 = int(self.app.settings['viewav_splitw0'])
            w1 = int(self.app.settings['viewav_splitw1'])
            if w0 > 10 and w1 > 10:
                self.ui.splitter_write.setSizes([w0, w1])
        except (KeyError, ValueError):
            pass
        self.ui.splitter_left.splitterMoved.connect(self._save_splitter_sizes)
        self.ui.splitter_write.splitterMoved.connect(self._save_splitter_sizes)
        self.setWindowTitle(self.abs_path.split('/')[-1])
        try:
            x = int(self.app.settings['viewav_abs_pos_x'])
            y = int(self.app.settings['viewav_abs_pos_y'])
            self.move(self.mapToGlobal(QtCore.QPoint(x, y)))
        except KeyError:
            pass
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        # Upstream aborted init without python-vlc; Qt backend covers it now
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        font = f'font: {self.app.settings["treefontsize"]}pt "{self.app.settings["font"]}";'
        # Speakers persist in speakers.json in the project folder, like pseudonyms.json.
        # Migrates once from the old config.ini key.
        self._speakers_file_key = "project"
        self.speaker_list = self._load_speakers_json()
        if not self.speaker_list:
            legacy_key = f"viewav_speakers::{self.app.project_name}::{self._speakers_file_key}"
            legacy = self.app.settings.get(legacy_key, "")
            if legacy:
                self.speaker_list = [s for s in str(legacy).split("|") if s.strip()][:8]
                self._save_speakers_json()
        self.ui.listWidget_snippets.itemDoubleClicked.connect(self.insert_snippet)
        self.ui.listWidget_snippets.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.listWidget_snippets.customContextMenuRequested.connect(self.snippets_menu)
        self.refresh_snippets_list()
        doc_font = f'font: {self.app.settings["docfontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.textEdit.setStyleSheet(doc_font)
        self.ui.label_note.setText(
            _("F4 play/pause  F3 rewind 5s  F5 forward 5s | Ctrl+T timestamp  Ctrl+N new speaker  Ctrl+1-8 speaker  Alt+Enter next speaker"))
        tt = _("It is best to edit text before ANY coding has been applied.")
        tt += "\n" + _(
            "Avoid selecting sections of text with a combination of not underlined (not coded) and underlined (coded).")
        tt += "\n" + _(
            "Positions of the underlying codes / annotations / case-assigned may be incorrect if text is typed over or deleted.")
        tt += "\n" + _("Auto-save: Text changes are automatically saved every 20 seconds.")
        self.ui.label_note.setToolTip(tt)
        self.ui.label_transcription.setToolTip(tt)
        self.ui.textEdit.installEventFilter(self)
        # Line numbers in the transcription area.
        # Paragraph numbers via NumberBar in the .ui lineNumbers container
        self.number_bar = NumberBar(self.ui.textEdit)
        _ln_layout = QtWidgets.QVBoxLayout(self.ui.lineNumbers)
        _ln_layout.setContentsMargins(0, 0, 0, 0)
        _ln_layout.addWidget(self.number_bar)
        self.ui.textEdit.viewport().installEventFilter(self)  # click on a timestamp -> seek
        self.installEventFilter(self)  # for rewind, play/stop, etc
        if platform.system() in ("Windows", "Darwin"):
            self.get_waveform()  # Crashes on Fedora 40, segmentation fault with ffmpeg
        # Get the transcription text and fill textedit
        self.transcription = None
        cur = self.app.conn.cursor()
        if self.file_['av_text_id'] is not None:
            cur.execute("select id, fulltext, name from source where id=?", [file_['av_text_id']])
            self.transcription = cur.fetchone()
            if self.transcription is not None and \
                    not (self.transcription[2].endswith(".txt")
                         or self.transcription[2].endswith(".transcribed")):
                # Stale link after id reuse pointed at a non-transcript file
                self.transcription = None
                self.file_['av_text_id'] = None
            if self.transcription is not None and self.transcription[1] is None:
                # Old projects can hold NULL fulltext; normalise so setText/regex do not crash
                self.transcription = (self.transcription[0], "", self.transcription[2])
        if self.transcription is not None:
            self.ui.textEdit.setText(self.transcription[1])
            self.get_timestamps_from_transcription()
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
                self.app.conn.commit()  # was a 'conmmit' typo silently swallowed; the
                # av_text_id link could be lost, recreating duplicate .txt transcripts
            self._emit_project_table_changes(['source'])
            cur.execute("select id, fulltext, name from source where id=?", [tr_id])
            self.transcription = cur.fetchone()
            if self.transcription is not None and self.transcription[1] is None:
                # Old projects can hold NULL fulltext; normalise so setText/regex do not crash
                self.transcription = (self.transcription[0], "", self.transcription[2])
        self.get_cases_codings_annotations()
        self.text = self.transcription[1]
        self.ui.textEdit.setPlainText(self.text)
        self.prev_text = copy(self.text)
        self.text_has_changed = False
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
        self.ui.label_case_sensitive.setPixmap(qta.icon('mdi6.format-letter-case').pixmap(22, 22))
        self.ui.pushButton_previous.setIcon(qta.icon('mdi6.arrow-left'))
        self.ui.pushButton_previous.setEnabled(False)
        self.ui.pushButton_previous.pressed.connect(self.move_to_previous_search_text)
        self.ui.pushButton_help.setIcon(qta.icon('mdi6.help'))
        self.ui.pushButton_help.pressed.connect(self.help)
        self.ui.pushButton_next.setIcon(qta.icon('mdi6.arrow-right'))
        self.ui.pushButton_next.pressed.connect(self.move_to_next_search_text)
        self.ui.pushButton_next.setEnabled(False)
        self.ui.lineEdit_search.textEdited.connect(self.search_for_text)
        self.ui.checkBox_case_sensitive.stateChanged.connect(self.search_for_text)
        # Transcription buttons
        self.ui.pushButton_new_speaker.setIcon(qta.icon('mdi6.account-plus-outline'))
        self.ui.pushButton_new_speaker.pressed.connect(self.add_speakername)
        self.ui.pushButton_new_speaker.setText("")
        self.ui.pushButton_new_speaker.setIcon(qta.icon('mdi6.account-plus'))
        self.ui.pushButton_new_speaker.setToolTip(_("Add speaker (Ctrl+N)"))
        self.ui.pushButton_remove_speaker.setText("")
        self.ui.pushButton_remove_speaker.setIcon(qta.icon('mdi6.account-minus'))
        self.ui.pushButton_remove_speaker.setToolTip(_("Remove speaker (Ctrl+D)"))
        self.ui.pushButton_remove_speaker.setIcon(qta.icon('mdi6.account-minus-outline'))
        self.ui.pushButton_remove_speaker.pressed.connect(self.delete_speakernames)
        self.ui.pushButton_insert_timestamp.setIcon(qta.icon('mdi6.clock-outline'))
        self.ui.pushButton_insert_timestamp.pressed.connect(self.insert_timestamp)
        # Bookmark buttons
        self.ui.pushButton_goto_bookmark.setIcon(qta.icon('mdi6.bookmark-off'))
        self.ui.pushButton_goto_bookmark.setEnabled(False)
        cur = self.app.conn.cursor()
        cur.execute("select avbookmarkfile from project")
        result = cur.fetchone()
        if self.file_['id'] == result[0]:
            self.ui.pushButton_goto_bookmark.setIcon(qta.icon('mdi6.bookmark-check'))
            self.ui.pushButton_goto_bookmark.setEnabled(True)
        self.ui.pushButton_goto_bookmark.pressed.connect(self.go_to_bookmark)
        self.ui.pushButton_set_bookmark.setIcon(qta.icon('mdi6.bookmark'))
        self.ui.pushButton_set_bookmark.pressed.connect(self.set_bookmark)
        self.ui.pushButton_load_transcription.setIcon(qta.icon('mdi6.file-import-outline'))
        self.ui.pushButton_load_transcription.pressed.connect(self.load_transcription)

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
        # Add context menu for ddialog
        self.ddialog.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.ddialog.customContextMenuRequested.connect(self.ddialog_menu)
        # Esc reject() hides the window while detached, leaving no video target: dock it back.
        self.ddialog.rejected.connect(self._on_ddialog_closed)
        # Set video dialog position, with a default initial position
        self.ddialog.move(self.mapToGlobal(QtCore.QPoint(40, 20)))
        # ddialog is relative to self global position
        try:
            x = int(self.app.settings['viewav_video_pos_x']) - int(self.app.settings['viewav_abs_pos_x'])
            y = int(self.app.settings['viewav_video_pos_y']) - int(self.app.settings['viewav_abs_pos_y'])
            self.ddialog.move(self.mapToGlobal(QtCore.QPoint(x, y)))
        except KeyError:
            pass
        # Video is embedded in the main window by default; ddialog is shown only when detached
        self.ddialog.hide()
        # Create a vlc instance
        # Fedora 39 NameError: no function 'libvlc_new'
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
        # Create an empty vlc media player
        self.mediaplayer = self.instance.media_player_new()
        self.mediaplayer.video_set_mouse_input(False)
        self.mediaplayer.video_set_key_input(False)
        self.ui.pushButton_play.clicked.connect(self.play_pause)
        self.ui.horizontalSlider_vol.valueChanged.connect(self.set_volume)
        try:
            self.ui.horizontalSlider_vol.setValue(int(self.app.settings.get('viewav_volume', 100)))
        except (TypeError, ValueError):
            self.ui.horizontalSlider_vol.setValue(100)
        # Player backend combo (VLC / Qt)
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
        self.ui.comboBox_tracks.currentIndexChanged.connect(self.audio_track_changed)
        # Wave navigation + embedded video / detach
        self.is_audio = self.file_['mediapath'][0:6] in ("/audio", "audio:")
        self.video_detached = False
        # Segment / loop playback driven from the transcript selection
        self.segment_play_start = None
        self.segment_play_end = None
        self.segment_loop = False
        self.ui.textEdit.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        self.ui.textEdit.customContextMenuRequested.connect(self.transcript_menu)
        self.ui.widget_seekbar.positionClicked.connect(self._seek_to_ms)
        # Classic position slider above the waveform, as in the original design.
        self.ui.horizontalSlider.setTickPosition(QtWidgets.QSlider.TickPosition.NoTicks)
        self.ui.horizontalSlider.setMouseTracking(True)
        self.ui.horizontalSlider.sliderMoved.connect(self.slider_seek)
        self.ui.widget_seekbar.segmentContextRequested.connect(self.wave_menu)
        self.ui.pushButton_play_segment.setIcon(qta.icon('mdi6.play-box-outline'))
        self.ui.pushButton_play_segment.clicked.connect(lambda: self.play_selection(False))
        self.ui.pushButton_loop_segment.setIcon(qta.icon('mdi6.repeat'))
        self.ui.pushButton_loop_segment.clicked.connect(lambda: self.play_selection(True))
        self.ui.pushButton_stop_segment.setIcon(qta.icon('mdi6.stop'))
        self.ui.pushButton_stop_segment.clicked.connect(lambda: self.stop_segment_play())
        self.ui.pushButton_clear_selection.setIcon(qta.icon('mdi6.selection-remove'))
        self.ui.pushButton_clear_selection.clicked.connect(lambda: self.ui.widget_seekbar.clear_selection())
        self.ui.frame_video.setVisible(not self.is_audio)
        if not self.is_audio:
            # Restore a collapsed video pane, else the preview never shows
            sizes = self.ui.splitter_left.sizes()
            if len(sizes) >= 2 and sizes[0] < 80:
                total = max(sum(sizes), 400)
                self.ui.splitter_left.setSizes([max(280, total // 2), total - max(280, total // 2)])
        # Embed VLC into frame_video without forcing sibling/ancestor widgets (e.g. the
        # transcript) to become native windows -> silences "must be a top level window" warnings
        self.ui.frame_video.setAttribute(QtCore.Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
        self.ui.frame_video.setAttribute(QtCore.Qt.WidgetAttribute.WA_NativeWindow, True)
        self.ui.pushButton_detach.setIcon(qta.icon('mdi6.open-in-new'))
        self.ui.pushButton_detach.setToolTip(_("Detach video to a window"))
        self.ui.pushButton_detach.pressed.connect(self.toggle_detach_video)
        if self.is_audio:
            self.ui.pushButton_detach.hide()
        try:
            self.media = self.instance.media_new(self.abs_path)
        except Exception as e_:
            Message(self.app, _('Media not found'), f"{e_}\n{self.abs_path}").exec()
            self.closeEvent()
            return
        # ddialog is now only the detached video window; size it but keep it hidden initially
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
        self.ddialog.hide()
        # Put the media in the media player
        self.mediaplayer.set_media(self.media)
        # Parse the metadata of the file
        self.media.parse()
        self._check_seek_friendliness(self.abs_path)
        self.mediaplayer.video_set_mouse_input(False)
        self.mediaplayer.video_set_key_input(False)
        # Bind VLC video output to the embedded frame (or the detached window)
        self._set_video_output()
        msecs = self.media.get_duration()
        self.media_duration_text = " / " + msecs_to_hours_mins_secs(msecs)
        self.ui.label_time.setText("0.00" + self.media_duration_text)
        self.ui.widget_seekbar.set_duration(msecs)
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
        self.ui.checkBox_scroll_transcript.stateChanged.connect(self.scroll_transcribed_checkbox_changed)
        # Need this for helping set the slider if user sliding before play begins
        # Detect number of audio tracks in media
        self.mediaplayer.play()
        time.sleep(0.2)
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
        # Apply the user's level rather than a hardcoded 100
        self.mediaplayer.audio_set_volume(self.ui.horizontalSlider_vol.value())

        self.ui.textEdit.textChanged.connect(self.update_positions)
        self.textchanged_timer = QtCore.QTimer(self)
        self.textchanged_timer.setInterval(20000)  # 20 seconds
        self.textchanged_timer.start()
        self.textchanged_timer.timeout.connect(self.update_database_text)

    def _save_splitter_sizes(self):
        """ Persist the vertical splitter sizes (video/controls vs transcript). """
        sizes = self.ui.splitter_v.sizes()
        if len(sizes) >= 2:
            self.app.settings['viewav_splitter0'] = sizes[0]
            self.app.settings['viewav_splitter1'] = sizes[1]
        lsizes = self.ui.splitter_left.sizes()
        if len(lsizes) >= 2:
            self.app.settings['viewav_splitl0'] = lsizes[0]
            self.app.settings['viewav_splitl1'] = lsizes[1]
        wsizes = self.ui.splitter_write.sizes()
        if len(wsizes) >= 2:
            self.app.settings['viewav_splitw0'] = wsizes[0]
            self.app.settings['viewav_splitw1'] = wsizes[1]

    def _set_video_output(self):
        """ Point VLC's video output at the embedded frame, or the detached ddialog. """
        if self.mediaplayer is None:
            return
        target = self.ddialog.dframe if getattr(self, 'video_detached', False) else self.ui.frame_video
        if hasattr(self.mediaplayer, 'set_video_host'):
            self.mediaplayer.set_video_host(target)  # Qt backend
            return
        if getattr(self, 'video_detached', False):
            winid = int(self.ddialog.dframe.winId())
        else:
            winid = int(self.ui.frame_video.winId())
        system = platform.system()
        if system == "Linux":
            self.mediaplayer.set_xwindow(winid)
        elif system == "Windows":
            self.mediaplayer.set_hwnd(winid)
        elif system == "Darwin":
            self.mediaplayer.set_nsobject(winid)


    def change_player_backend(self, index):
        """ Rebuild the player with the chosen backend keeping the position;
        without python-vlc it reverts to Qt with a message. """

        wanted = 'qt' if index == 1 else 'vlc'
        pos = 0
        try:
            pos = self.mediaplayer.get_time()
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
        self.app.settings['av_player'] = wanted
        self.app.write_config_ini(self.app.settings, self.app.ai_models)
        self.media = self.instance.media_new(self.abs_path)
        self.media.parse()
        self.mediaplayer.set_media(self.media)
        self._retarget_video_output()
        host = self.ddialog.dframe if getattr(self, 'video_detached', False) else self.ui.frame_video
        host.repaint()  # clear leftovers from the previous backend surface
        self.mediaplayer.audio_set_volume(int(self.ui.horizontalSlider_vol.value()))
        if pos:
            self.mediaplayer.set_time(pos)

    def _retarget_video_output(self):
        """ Move VLC's video to the current target window. VLC binds the output when the video
        output is created, so we briefly restart playback at the same position to recreate it
        on the new window. """
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

    def _on_ddialog_closed(self):
        """ The floating window was dismissed (Esc): dock the video back. """
        if getattr(self, 'video_detached', False):
            self.toggle_detach_video()

    def toggle_detach_video(self):
        """ Detach the video into the floating window (ddialog), or dock it back. """
        if getattr(self, 'video_detached', False):
            self.video_detached = False
            self.ddialog.hide()
            self.ui.frame_video.setVisible(not self.is_audio)
            self._retarget_video_output()
            self.ui.pushButton_detach.setIcon(qta.icon('mdi6.open-in-new'))
            self.ui.pushButton_detach.setToolTip(_("Detach video to a window"))
        else:
            self.video_detached = True
            self.ui.frame_video.setVisible(False)
            self.ddialog.show()
            self._retarget_video_output()
            self.ui.pushButton_detach.setIcon(qta.icon('mdi6.dock-window'))
            self.ui.pushButton_detach.setToolTip(_("Dock video back"))

    def get_waveform(self):
        """ Show the waveform image on the seek bar. Reuses the per-file cached image
        (audio/waveform_<id>.png) built on import; if missing, generates it once (blue) when
        ffmpeg is available, else shows a hint. Requires ffmpeg only for generation; playback
        and seeking work regardless. Skipped on Linux in __init__. """

        if self.file_ is None:
            return
        sb = self.ui.widget_seekbar
        waveform_path = os.path.join(self.app.project_path, "audio", f"waveform_{self.file_['id']}.png")
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
            sb.set_waveform_pixmap(None)
            sb.set_no_waveform_message("")  # silent: bar still works for seeking
            return
        # Worker thread build; a QTimer polls for completion in the GUI thread.
        sb.set_waveform_pixmap(None)
        sb.set_no_waveform_message(_("Generating waveform..."))
        thread = generate_waveform_png_async(self.abs_path, waveform_path,
                                             waveform_colour(self.app.settings['stylesheet']))
        timer = QtCore.QTimer(self)
        timer.setInterval(300)

        def _check_waveform_done():
            if thread.is_alive():
                return
            timer.stop()
            timer.deleteLater()
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
        timer.start()

    def load_transcription(self):
        """ Import transcript text from a .txt/.srt/.vtt file into the linked transcription
        and save it. Timestamps in the file are reused for transcript sync. """

        if self.transcription is None:
            return
        filename, _ok = QtWidgets.QFileDialog.getOpenFileName(
            self, _("Load transcription"), self.app.project_path,
            _("Transcript files") + " (*.txt *.srt *.vtt *.md *.html *.htm);;" + _("All files") + " (*)")
        if not filename:
            return
        try:
            # Same formats and reading as Manage files > Import transcription from file.
            if filename.lower().endswith((".html", ".htm")):
                with open(filename, "r", encoding="utf-8", errors="surrogateescape") as f:
                    text = html_to_text(f.read())
            else:
                with open(filename, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read()
        except Exception as e_:
            Message(self.app, _("Load transcription"), str(e_), "warning").exec()
            return
        if text is None:
            text = ""
        # Normalise line endings and strip BOM so stored positions match the editor.
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        if text and text[0] == "\ufeff":
            text = text[1:]
        if text.strip() == "":
            Message(self.app, _("Load transcription"),
                    _("The selected file has no readable text."), "warning").exec()
            return
        # Apply pseudonyms, consistent with the Manage files transcript import.
        for pseudonym in self._load_pseudonyms():
            text = re.sub(rf"(?<!\w){re.escape(pseudonym['original'])}(?!\w)", pseudonym['pseudonym'], text)
        cur = self.app.conn.cursor()
        if self.ui.textEdit.toPlainText().strip():
            # Warn with concrete counts, same as the Manage files import
            cur.execute("select count(*) from code_text where fid=?", [self.transcription[0]])
            codings = cur.fetchone()[0]
            cur.execute("select count(*) from annotation where fid=?", [self.transcription[0]])
            annotations = cur.fetchone()[0]
            warn = _("Replace the current transcription with the loaded file?") + "\n"
            warn += _("Codings: ") + str(codings) + "    " + _("Annotations: ") + str(annotations) + "\n"
            warn += _("Replacing it may shift or remove existing codings and annotations.")
            resp = QtWidgets.QMessageBox.question(self, _("Load transcription"), warn)
            if resp != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        # Block textChanged while replacing programmatically: update_positions would diff
        # old against new text and shift every coding/annotation.
        self.ui.textEdit.blockSignals(True)
        self.ui.textEdit.setPlainText(text)
        self.ui.textEdit.blockSignals(False)
        self.text = text
        self.prev_text = copy(text)
        self.text_has_changed = False  # already persisted below, nothing pending for autosave
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("update source set fulltext=?, date=? where id=?", [text, now, self.transcription[0]])
        self.app.conn.commit()
        self.app.delete_backup = False
        # Only source.fulltext is rewritten here; subscribers reload the file on 'source'
        self._emit_project_table_changes(['source'])
        cur.execute("select id, fulltext, name from source where id=?", [self.transcription[0]])
        self.transcription = cur.fetchone()
        if self.transcription is not None and self.transcription[1] is None:
            self.transcription = (self.transcription[0], "", self.transcription[2])  #
        self.get_timestamps_from_transcription()
        # Refresh coded text, annotations, cases and repaint over the new text
        self.get_cases_codings_annotations()
        self.highlight()

    def _load_pseudonyms(self):
        """ Pseudonyms stored in pseudonyms.json in the project folder.
        Same source as ManageFiles.load_pseudonyms, duplicated here to avoid a
        circular import (manage_files already imports view_av).
        Returns a list of dicts with 'original' and 'pseudonym' keys. """

        pseudonyms_filepath = os.path.join(self.app.project_path, "pseudonyms.json")
        try:
            with open(pseudonyms_filepath, "r") as f:
                pseudonyms = json.load(f)
        except FileNotFoundError:
            return []
        except Exception as e_:
            logger.warning(f"Cannot read pseudonyms.json: {e_}")
            return []
        # Defensive: keep only well-formed entries
        return [p for p in pseudonyms
                if isinstance(p, dict) and p.get('original') and p.get('pseudonym')]

    def get_cases_codings_annotations(self):
        """ Get all linked cases, coded text and annotations for this file """

        cur = self.app.conn.cursor()
        sql = "select ctid, cid, pos0, pos1, seltext, owner from code_text where fid=?"
        cur.execute(sql, [self.transcription[0]])
        res = cur.fetchall()
        self.codetext = []
        for r in res:
            self.codetext.append({'ctid': r[0], 'cid': r[1], 'pos0': r[2], 'pos1': r[3], 'seltext': r[4],
                                  'owner': r[5], 'newpos0': r[2], 'newpos1': r[3]})
        sql = "select anid, pos0, pos1 from annotation where fid=?"
        cur.execute(sql, [self.transcription[0]])
        res = cur.fetchall()
        self.annotations = []
        for r in res:
            self.annotations.append({'anid': r[0], 'pos0': r[1], 'pos1': r[2],
                                     'newpos0': r[1], 'newpos1': r[2]})
        sql = "select id, pos0, pos1 from case_text where fid=?"
        cur.execute(sql, [self.transcription[0]])
        res = cur.fetchall()
        self.casetext = []
        for r in res:
            self.casetext.append({'id': r[0], 'pos0': r[1], 'pos1': r[2],
                                  'newpos0': r[1], 'newpos1': r[2]})
        self.no_codes_annotes_cases = True
        if len(self.codetext) > 0 or len(self.annotations) > 0 or len(self.casetext) > 0:
            self.no_codes_annotes_cases = False

    def help(self):
        """ Open help for transcribe section in browser. """

        self.app.help_wiki("3.2.-Files")

    def ddialog_menu(self, position):
        """ Context menu to export a screenshot, to resize dialog """

        menu = QtWidgets.QMenu()
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
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

    def wave_menu(self, seg, global_pos):
        """ Right-click menu on the waveform (viewer). Offers playback helpers at the clicked
        position and, if a region was drag-selected on the wave, play/loop that region. """

        sb = self.ui.widget_seekbar
        duration = self.media.get_duration() if self.media is not None else 0
        local = sb.mapFromGlobal(global_pos)
        w = sb.width()
        click_ms = int(local.x() / w * duration) if w > 0 and duration > 0 else 0
        click_ms = max(0, min(click_ms, duration))
        menu = QtWidgets.QMenu()
        sel = sb.get_selection()
        act_play_sel = act_loop_sel = act_clear_sel = None
        if sel is not None:
            act_play_sel = menu.addAction(_("Play selection"))
            act_loop_sel = menu.addAction(_("Loop selection"))
            act_clear_sel = menu.addAction(_("Clear selection"))
            menu.addSeparator()
        act_play_here = menu.addAction(_("Play from here"))
        act_ts_here = menu.addAction(_("Insert timestamp here"))
        act_stop = None
        if self.segment_play_end is not None:
            act_stop = menu.addAction(_("Stop segment playback"))
        action = menu.exec(global_pos)
        if action is None:
            return
        if action == act_play_sel:
            self._play_range(sel[0], sel[1], loop=False)
        elif action == act_loop_sel:
            self._play_range(sel[0], sel[1], loop=True)
        elif action == act_clear_sel:
            sb.clear_selection()
        elif action == act_play_here:
            self._start_playing()
            self._seek_to_ms(click_ms)
        elif action == act_ts_here:
            self._insert_timestamp_at_ms(click_ms)
        elif action == act_stop:
            self.stop_segment_play()

    def transcript_menu(self, position):
        """ Context menu in the transcript area to aid transcribing: insert timestamp,
        play / loop the selected segment (bounded by surrounding timestamps). """

        menu = self.ui.textEdit.createStandardContextMenu()
        menu.addSeparator()
        act_ts = menu.addAction(_("Insert timestamp (Ctrl+T)"))
        # Re-parse timestamps from the current text so freshly inserted ones are recognised
        self.get_timestamps_from_transcription()
        has_sel = self.ui.textEdit.textCursor().hasSelection()
        act_play = act_loop = act_stop = None
        if has_sel and self.time_positions:
            act_play = menu.addAction(_("Play selected segment"))
            act_loop = menu.addAction(_("Loop selected segment"))
        if self.segment_play_end is not None:
            act_stop = menu.addAction(_("Stop segment playback"))
        action = menu.exec(self.ui.textEdit.mapToGlobal(position))
        if action is None:
            return
        if action == act_ts:
            self.insert_timestamp()
        elif action == act_play:
            self.play_text_segment(loop=False)
        elif action == act_loop:
            self.play_text_segment(loop=True)
        elif action == act_stop:
            self.stop_segment_play()

    def _text_selection_to_ms(self):
        """ Map the current transcript selection to a media time range using the timestamps
        surrounding it: start = last timestamp at/before the selection start; end = first
        timestamp at/after the selection end (or media end). Returns (ms0, ms1) or (None, None). """
        cursor = self.ui.textEdit.textCursor()
        if not cursor.hasSelection() or not self.time_positions:
            return None, None
        sel0 = cursor.selectionStart()
        sel1 = cursor.selectionEnd()
        stamps = sorted(self.time_positions, key=lambda x: x[0])
        ms0 = None
        for c0, c1, ms in stamps:
            if c0 <= sel0:
                ms0 = ms
        if ms0 is None:
            ms0 = stamps[0][2]
        ms1 = None
        for c0, c1, ms in stamps:
            if c0 >= sel1:
                ms1 = ms
                break
        if ms1 is None and self.media is not None:
            ms1 = self.media.get_duration()
        return ms0, ms1

    def _start_playing(self):
        """ Ensure the media is playing (without toggling pause). """
        if not self.mediaplayer.is_playing():
            if self.mediaplayer.play() == -1:
                return
            self.ui.pushButton_play.setIcon(qta.icon('mdi6.pause'))
            self.is_paused = False
            if not self.timer.isActive():
                self.timer.start()

    def play_text_segment(self, loop=False):
        """ Play (or loop) the media between the timestamps surrounding the transcript selection. """
        ms0, ms1 = self._text_selection_to_ms()
        self._play_range(ms0, ms1, loop)

    def _current_selection_range(self):
        """ Prefer a range selected by dragging on the wave; otherwise use the transcript
        text selection. Returns (ms0, ms1) or (None, None). """
        sel = self.ui.widget_seekbar.get_selection()
        if sel is not None:
            return sel[0], sel[1]
        return self._text_selection_to_ms()

    def play_selection(self, loop=False):
        """ Play (or loop) the current selection (wave selection or transcript selection). """
        ms0, ms1 = self._current_selection_range()
        self._play_range(ms0, ms1, loop)

    def _play_range(self, ms0, ms1, loop=False):
        """ Play (or loop) the media between two absolute millisecond positions. """
        if ms0 is None or ms1 is None or ms1 <= ms0:
            return
        self.segment_play_start = int(ms0)
        self.segment_play_end = int(ms1)
        self.segment_loop = bool(loop)
        self._start_playing()
        self._seek_to_ms(int(ms0))

    def stop_segment_play(self):
        """ Stop segment / loop playback. """
        self.segment_play_start = None
        self.segment_play_end = None
        self.segment_loop = False
        self.pause()

    def _seek_to_clicked_timestamp(self, event):
        """ If the click landed on a transcript timestamp, seek the media to that time. """
        if self.mediaplayer is None or not self.time_positions:
            return
        cursor = self.ui.textEdit.cursorForPosition(event.position().toPoint())
        char = cursor.position()
        for c0, c1, ms in self.time_positions:
            if c0 <= char <= c1:
                self._seek_to_ms(ms)
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

    def _seek_to_ms(self, ms):
        """ Seek the media player to an absolute millisecond position. """
        if self.mediaplayer is None or self.mediaplayer.get_media() is None:
            return
        duration = self.mediaplayer.get_media().get_duration()
        if duration <= 0:
            return
        ms = max(0, min(int(ms), duration - 1))
        if type(self.mediaplayer).__module__.endswith('media_player_qt'):
            self.mediaplayer.set_position(ms / duration)
        else:
            self._vlc_apply_seek(ms, duration)
        self.ui.label_time.setText(msecs_to_hours_mins_secs(ms))
        self.sync_position_slider(ms, duration)
        self.update_ui()

    def slider_seek(self, value):
        """ Seek from the classic position slider (0-1000) above the waveform.
        Routed through _seek_to_ms so slider, playhead and time label stay in sync. """

        if self.mediaplayer is None or self.mediaplayer.get_media() is None:
            return
        duration = self.mediaplayer.get_media().get_duration()
        if duration <= 0:
            return
        self._seek_to_ms(int(value / 1000 * duration))

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

    def eventFilter(self, object_, event):
        """ Add key options to improve manual transcribing.
        Options are:
            Crtl B Set Bookmark
            Ctrl Shift B Go to Bookmart
            Ctrl D Delete speaker names from shortcuts
            Ctrl N Enter a new speakers name into shortcuts
            Ctrl R Rewind 5 seconds
            Ctrl S OR ctrl + P Start/pause On start rewind slightly
            Ctrl T Insert timestamp in format [hh.mm.ss]
            Ctrl +1 .. 8 Insert speaker in format [speaker name]
            Ctrl Shift > Increase play rate
            Ctrl Shift < Decrease play rate
            Alt plus Forward 30 seconds
            Alt minus Rewind 30 seconds.
        """

        # Left-click on a transcript timestamp -> seek the media to that time
        if event.type() == QtCore.QEvent.Type.MouseButtonRelease and object_ == self.ui.textEdit.viewport() \
                and event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._seek_to_clicked_timestamp(event)
            return False  # let the textEdit also place the caret normally
        # Alternate speakers: Enter is caught on PRESS (consumes the default newline).
        # Alt+Enter always inserts the next speaker; the checkbox makes every Enter do it.
        if event.type() == QtCore.QEvent.Type.KeyPress and \
                event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter) and \
                object_ is self.ui.textEdit and self.speaker_list:
            alt = bool(event.modifiers() & QtCore.Qt.KeyboardModifier.AltModifier)
            if alt or self.ui.checkBox_alternate_speakers.isChecked():
                self._insert_next_speaker()
                return True
        if event.type() != 7:  # QtGui.QKeyEvent
            return False
        key = event.key()
        mods = event.modifiers()
        # print("KEY ", key, "MODS ", mods)
        #  ctrl S or ctrl P pause/play toggle
        if (key == QtCore.Qt.Key.Key_S or key == QtCore.Qt.Key.Key_P) and \
                mods == QtCore.Qt.KeyboardModifier.ControlModifier:
            self.play_pause()
        # Transport keys as in transcription software: F3 -5s, F4 play/pause, F5 +5s.
        if key == QtCore.Qt.Key.Key_F4:
            self.play_pause()
            return True
        if key == QtCore.Qt.Key.Key_F3:
            self.rewind_5_seconds()
            return True
        if key == QtCore.Qt.Key.Key_F5:
            self.forward_5_seconds()
            return True
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
        # Increase play rate  Ctrl Shift >
        if key == QtCore.Qt.Key.Key_Greater and (mods and QtCore.Qt.KeyboardModifier.ShiftModifier) and \
                (mods and QtCore.Qt.KeyboardModifier.ControlModifier):
            self.increase_play_rate()
        # Decrease play rate  Ctrl Shift <
        if key == QtCore.Qt.Key.Key_Less and (mods and QtCore.Qt.KeyboardModifier.ShiftModifier) and \
                (mods and QtCore.Qt.KeyboardModifier.ControlModifier):
            self.decrease_play_rate()
        # Go to bookmark, if this is the correct a/v file
        if key == QtCore.Qt.Key.Key_B and mods & QtCore.Qt.KeyboardModifier.ShiftModifier and \
                mods & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.go_to_bookmark()
            return True  # Without this, the set-bookmark branch below also fires and
            # overwrites the bookmark just visited (Ctrl is still held).
        # Set bookmark
        if key == QtCore.Qt.Key.Key_B and mods & QtCore.Qt.KeyboardModifier.ControlModifier:
            self.set_bookmark()
        return True

    def go_to_bookmark(self):
        """ Only if this file is bookmarked. Ctrl Shift B or button. """

        cur = self.app.conn.cursor()
        cur.execute("select avbookmarkfile, avbookmarkmsec, avbookmarktextpos from project")
        result = cur.fetchone()
        if self.file_['id'] != result[0]:
            return True
        self.mediaplayer.play()
        # Playback must be active to set_time().
        time.sleep(0.1)
        self.mediaplayer.set_time(result[1])
        self.ui.widget_seekbar.set_position(result[1])  # the bar works in absolute msecs
        if self.media is not None:
            self.sync_position_slider(result[1], self.media.get_duration())
        self.mediaplayer.pause()
        cursor = self.ui.textEdit.textCursor()
        cursor.setPosition(result[2])
        endpos = result[2] - 1
        if endpos < 0:
            endpos = 0
        cursor.setPosition(endpos, QtGui.QTextCursor.MoveMode.KeepAnchor)
        self.ui.textEdit.setTextCursor(cursor)

    def set_bookmark(self):
        """ Ctrl B or button. """

        cur = self.app.conn.cursor()
        cursor_pos = self.ui.textEdit.textCursor().position()
        cur.execute("update project set avbookmarkfile=?, avbookmarkmsec=?, avbookmarktextpos=?",
                    [self.file_['id'], self.mediaplayer.get_time(), cursor_pos])
        self.app.conn.commit()
        self.ui.pushButton_goto_bookmark.setIcon(qta.icon('mdi6.bookmark-check'))
        self.ui.pushButton_goto_bookmark.setEnabled(True)

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

    def _speaker_snippet_text(self, speaker):
        """ Insert text for a speaker, using the identifier chosen at creation. """
        fmt = self.speaker_formats.get(speaker) or self.app.settings.get('speakernameformat', ':')
        if fmt == "[]":
            return f"\n[{speaker}] "
        if fmt == "{}":
            return f"\n{{{speaker}}} "
        if fmt == "#":
            return f"\n#{speaker}: "
        if fmt == "@":
            return f"\n@{speaker}: "
        return f"\n{speaker}: "

    def _speakers_json_path(self):
        return os.path.join(self.app.project_path, "speakers.json")

    def _load_speakers_json(self):
        """ Read the project speakers from speakers.json. """
        try:
            with open(self._speakers_json_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            speakers = data.get(self._speakers_file_key, [])
            if not speakers and isinstance(data, dict):
                # Migration: merge old per-file lists into the shared one.
                merged = []
                for value in data.values():
                    if isinstance(value, list):
                        for s in value:
                            if s not in merged:
                                merged.append(s)
                speakers = merged
            names = []
            for s in speakers[:8]:
                if isinstance(s, dict):
                    name = str(s.get('name', '')).strip()
                    if name:
                        names.append(name)
                        if s.get('fmt'):
                            self.speaker_formats[name] = s['fmt']
                elif str(s).strip():
                    names.append(str(s))
            return names
        except (FileNotFoundError, ValueError, OSError):
            return []

    def _save_speakers_json(self):
        """ Save the speakers to speakers.json, keeping other keys intact. """
        path = self._speakers_json_path()
        data = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        except (FileNotFoundError, ValueError, OSError):
            data = {}
        data[self._speakers_file_key] = [
            {'name': n, 'fmt': self.speaker_formats.get(n)} for n in self.speaker_list]
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=1)
        except OSError as err:
            logger.warning(f"speakers.json write failed: {err}")

    def refresh_snippets_list(self):
        """ Rebuild the speakers list with a header row. Predefined symbols
        removed after review. """
        lw = self.ui.listWidget_snippets
        lw.clear()
        bold = QtGui.QFont()
        bold.setBold(True)
        header = QtWidgets.QListWidgetItem(_("Speakers"))
        hfont = QtGui.QFont()
        hfont.setBold(True)
        hfont.setPointSize(max(lw.font().pointSize() - 1, 7))
        header.setFont(hfont)
        header.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)  # header row: not interactive
        fg = header.foreground().color()
        fg.setAlpha(150)
        header.setForeground(fg)
        lw.addItem(header)

        for i, speaker in enumerate(self.speaker_list):
            # Show the speaker as it will be inserted; shortcut in the tooltip.
            shown = self._speaker_snippet_text(speaker).strip()
            item = QtWidgets.QListWidgetItem(shown)
            item.setFont(bold)
            tip = _("Double click inserts the speaker at the cursor.")
            if i < 8:
                tip += "\n" + _("Shortcut:") + f" Ctrl+{i + 1}"
            tip += "\n" + _("Right click to edit.")
            item.setToolTip(tip)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, speaker)
            item.setData(QtCore.Qt.ItemDataRole.UserRole + 1, True)  # speaker flag
            lw.addItem(item)

    def snippets_menu(self, position):
        """ Snippets list context menu: edit speaker."""

        item = self.ui.listWidget_snippets.itemAt(position)
        if item is None or not item.data(QtCore.Qt.ItemDataRole.UserRole + 1):
            return
        speaker = str(item.data(QtCore.Qt.ItemDataRole.UserRole))
        menu = QtWidgets.QMenu(self)
        menu.setStyleSheet(f"QMenu {{font-size:{self.app.settings['fontsize']}pt}} ")
        action_edit = menu.addAction(_("Edit speaker"))
        action = menu.exec(self.ui.listWidget_snippets.mapToGlobal(position))
        if action == action_edit:
            self.edit_speaker(speaker)

    def insert_snippet(self, item):
        """ Insert at the cursor; speakers use the identifier chosen at creation."""

        data = item.data(QtCore.Qt.ItemDataRole.UserRole)
        if not data:
            return
        if item.data(QtCore.Qt.ItemDataRole.UserRole + 1):
            data = self._speaker_snippet_text(str(data))
        cursor = self.ui.textEdit.textCursor()
        cursor.insertText(data)
        self.ui.textEdit.ensureCursorVisible()  # scroll to the insertion point
        self.ui.textEdit.setFocus()

    def _insert_next_speaker(self):
        """ Insert the next speaker in the list (cyclic), in its own format. """
        if not self.speaker_list:
            return
        self._alternate_idx = (getattr(self, '_alternate_idx', -1) + 1) % len(self.speaker_list)
        speaker = self.speaker_list[self._alternate_idx]
        self.ui.textEdit.textCursor().insertText(self._speaker_snippet_text(speaker))
        self.ui.textEdit.ensureCursorVisible()  # scroll to the insertion point
        self.ui.textEdit.setFocus()

    def _speaker_dialog(self, initial_name="", initial_fmt=None, title=None):
        """ Name + identifier dialog, for adding and editing speakers.
        Returns (name, format), or None if cancelled or the name is invalid. """

        d = QtWidgets.QDialog(self)
        d.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        d.setWindowFlags(d.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        d.setWindowTitle(title or _("Speaker name"))
        form = QtWidgets.QFormLayout(d)
        name_edit = QtWidgets.QLineEdit()
        name_edit.setText(initial_name)
        form.addRow(_("Name:"), name_edit)
        fmt_combo = QtWidgets.QComboBox()
        variants = [(":", _("Name") + ":"), ("#", "#" + _("Name") + ":"), ("@", "@" + _("Name") + ":"),
                    ("[]", "[" + _("Name") + "]"), ("{}", "{" + _("Name") + "}")]
        for fmt_code, label in variants:
            fmt_combo.addItem(label, fmt_code)
        preselect = initial_fmt or self.app.settings.get('speakernameformat', ':')
        idx = next((i for i, v in enumerate(variants) if v[0] == preselect), 0)
        fmt_combo.setCurrentIndex(idx)
        form.addRow(_("Identifier:"), fmt_combo)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok |
                                             QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(d.accept)
        buttons.rejected.connect(d.reject)
        form.addRow(buttons)
        name_edit.setFocus()
        if d.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return None
        name = name_edit.text().strip()
        if name == "" or name.find('.') == 0 or name.find(':') == 0 or name.find('[') == 0 or name.find(
                ']') == 0 or name.find('{') == 0 or name.find('}') == 0:
            return None
        return name, fmt_combo.currentData()

    def add_speakername(self):
        """ Add a speaker: one dialog with name + identifier. Maximum of 8. """

        if len(self.speaker_list) == 8:
            return
        result = self._speaker_dialog()
        if result is None:
            return
        name, fmt = result
        self.speaker_formats[name] = fmt
        self.speaker_list.append(name)
        self.add_speaker_names_to_label()

    def edit_speaker(self, old_name):
        """ Right-click edit: rename and/or change the identifier, keeping the
        position (and so the Ctrl+n shortcut). """

        if old_name not in self.speaker_list:
            return
        result = self._speaker_dialog(initial_name=old_name,
                                      initial_fmt=self.speaker_formats.get(old_name),
                                      title=_("Edit speaker"))
        if result is None:
            return
        new_name, fmt = result
        pos = self.speaker_list.index(old_name)
        self.speaker_list[pos] = new_name
        self.speaker_formats.pop(old_name, None)
        self.speaker_formats[new_name] = fmt
        self.add_speaker_names_to_label()

    def insert_speakername(self, key):
        """ Insert speaker name using a settings format [name] {name} name:
        Up to 8 speakers can be selected from, 1 - 8.
        args:
            key: """

        list_pos = key - 49
        try:
            speaker = self.speaker_list[list_pos]
        except IndexError:
            return False
        # Uses the identifier chosen when the speaker was created.
        self.ui.textEdit.insertPlainText(self._speaker_snippet_text(speaker))
        self.ui.textEdit.ensureCursorVisible()  # scroll to the insertion point

    def insert_timestamp(self):
        """ Insert a timestamp for the current playback position. """
        self._insert_timestamp_at_ms(self.mediaplayer.get_time())

    def _insert_timestamp_at_ms(self, time_msecs):
        """ Insert a timestamp for the given media position at the text cursor.
        Format options:
        [mm.ss], [mm:ss], [hh.mm.ss], [hh:mm:ss],
        {hh:mm:ss}, #hh:mm:ss.sss#
        """

        fmt = self.app.settings['timestampformat']
        time_msecs = int(time_msecs)
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
        self.ui.textEdit.insertPlainText(f"{ts}\n")
        self.ui.textEdit.ensureCursorVisible()  # scroll to the insertion point
        # Code here makes the current text location visible on the textEdit pane
        text_cursor = self.ui.textEdit.textCursor()
        pos = text_cursor.position()
        text_cursor.setPosition(pos)
        self.ui.textEdit.setTextCursor(text_cursor)
        # Refresh parsed timestamps so click-to-seek and segment playback see the new mark
        self.get_timestamps_from_transcription()

    def add_speaker_names_to_label(self):
        """ Add speaker names to label, four on each line.
        Called by init, delete_speakernames, add_speakernames """

        # Persist the list and mirror it in the snippets.
        self._save_speakers_json()
        self.refresh_snippets_list()

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

        mmss1 = r"\[[0-9]{1,3}:[0-9][0-9]\]"  # up to 999 mins: the inserted [mm:ss] uses total minutes
        hhmmss1 = r"\[[0-9][0-9]:[0-9][0-9]:[0-9][0-9]\]"
        mmss2 = r"\[[0-9]{1,3}\.[0-9][0-9]\]"  #
        hhmmss2 = r"\[[0-9][0-9]\.[0-9][0-9]\.[0-9][0-9]\]"
        hhmmss3 = r"\{[0-9][0-9]\:[0-9][0-9]\:[0-9][0-9]\}"
        hhmmss_sss = r"#[0-9][0-9]:[0-9][0-9]:[0-9][0-9]\.[0-9]{1,3}#"  # 1-3 msec digits, same as the coder
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
            # Format {00:34:20} is colon separated; splitting by '.' crashed on load.
            stamp = match.group()[1:-1]
            s = stamp.split(':')
            try:
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s[2])) * 1000
                self.time_positions.append([match.span()[0], match.span()[1], msecs])
            except (IndexError, ValueError):
                pass
        for match in re.finditer(hhmmss_sss, transcription):
            # Format #00:12:34.567#  (also .5 / .56: pad to milliseconds, as the coder does)
            stamp = match.group()[1:-1]
            s = stamp.split(':')
            s2 = s[2].split('.')
            try:
                text_msecs = s2[1]
                if len(text_msecs) == 1:
                    text_msecs += "00"
                if len(text_msecs) == 2:
                    text_msecs += "0"
                msecs = (int(s[0]) * 3600 + int(s[1]) * 60 + int(s2[0])) * 1000 + int(text_msecs)
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
        # Consumers (transcript scroll, click-to-seek) assume ascending text positions
        self.time_positions.sort(key=lambda tp: tp[0])

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
        self.ui.widget_seekbar.set_position(0)
        self.ui.horizontalSlider.blockSignals(True)
        self.ui.horizontalSlider.setValue(0)
        self.ui.horizontalSlider.blockSignals(False)
        # Clear segment / loop playback state, otherwise the old loop resumes on next play
        self.segment_play_start = None
        self.segment_play_end = None
        self.segment_loop = False
        # Set combobox display of audio track to the first one, or leave it blank if it contains no items
        if self.ui.comboBox_tracks.count() > 0:
            self.ui.comboBox_tracks.setCurrentIndex(0)

    def set_volume(self, volume):
        """ Set the volume (slider 0-100), update the icon and remember it. """

        if self.mediaplayer is not None:
            self.mediaplayer.audio_set_volume(volume)
        self.app.settings['viewav_volume'] = volume
        if volume == 0:
            icon = 'mdi6.volume-off'
        elif volume < 34:
            icon = 'mdi6.volume-low'
        elif volume < 67:
            icon = 'mdi6.volume-medium'
        else:
            icon = 'mdi6.volume-high'
        self.ui.label_volume.setPixmap(qta.icon(icon).pixmap(22, 22))
        self.ui.horizontalSlider_vol.setToolTip(_("Volume") + f": {volume}%")

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
        """ Updates the user interface: wave playhead, audio tracks, media time and
        optional transcript scrolling. """

        # update audio track list, only works if media is playing
        if self.mediaplayer.audio_get_track_count() > 0 and self.ui.comboBox_tracks.count() == 0:
            tracks = self.mediaplayer.audio_get_track_description()
            for t in tracks:
                if t[0] > 0:
                    self.ui.comboBox_tracks.addItem(str(t[0]))

        if getattr(self, '_keyframe_gap', None):
            self._apply_keyframe_hint()
        msecs = self._vlc_display_ms(self.mediaplayer.get_time())
        self.ui.widget_seekbar.set_position(msecs)
        media = self.mediaplayer.get_media()
        if media is not None:
            self.sync_position_slider(msecs, media.get_duration())
        self.ui.label_time.setText(msecs_to_hours_mins_secs(msecs) + self.media_duration_text)

        # Segment / loop playback bounds (from the transcript "Play selected segment")
        if self.segment_play_end is not None and msecs >= self.segment_play_end:
            if self.segment_loop and self.segment_play_start is not None:
                media = self.mediaplayer.get_media()
                if media is None:  # released between timer ticks (e.g. while closing)
                    return
                dur = media.get_duration()
                if dur and dur > 0:
                    self.mediaplayer.set_position(self.segment_play_start / dur)
            else:
                self.segment_play_start = None
                self.segment_play_end = None
                self.pause()

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

    def reject(self):
        """ Esc must NOT close the dialog: an accidental Escape while transcribing
        silently closed the window. Closing goes through the window button, whose
        closeEvent stops playback and saves the transcript. """
        return

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
        If case sensitive is checked then text searched is matched for case sensitivity.
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
        if not self.ui.checkBox_case_sensitive.isChecked():
            flags |= re.IGNORECASE
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

    def closeEvent(self, event):
        """ Stop the vlc player and timers on close.
        Record the dialog and video dialog0 size and positions. """

        self.update_sizes()
        self.ddialog.close()
        self.stop()
        if type(self.mediaplayer).__module__.endswith('media_player_qt'):
            self.mediaplayer.release()  # free the file handle (WinError 32 on delete)
        self.textchanged_timer.stop()
        self.timer.stop()
        self.app.write_config_ini(self.app.settings, self.app.ai_models)  # persist volume/sizes
        self.update_database_text()
        
    def update_database_text(self):
        """ Called every 10 seconds via textchanged_timer """

        if not self.text_has_changed:
            return
        self.text_has_changed = False
        current_text = self.ui.textEdit.toPlainText()
        try:
            cur = self.app.conn.cursor()
            # self.transcription[0] is file id, [1] is the original text
            date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("update source set fulltext=?, date=? where id=?", [current_text, date, self.transcription[0]])
            for item in self.code_deletions:
                cur.execute(item)
            self.code_deletions = []
            self.update_codings()
            self.codetext = []
            self.update_annotations()
            self.annotations = []
            self.update_casetext()
            self.casetext = []
            self.app.conn.commit()  # Commit all changes in one go to prevent database inconsistencies
            # Update transcript in vectorstore
            if self.app.settings['ai_enable'] == 'True':
                name = self.transcription[2]
                self.app.ai.sources_vectorstore.import_document(self.transcription[0], name, current_text)
        except Exception as e_:
            print(e_)
            self.app.conn.rollback()
            raise
        self.text = current_text
        self.prev_text = copy(self.text)
        self.app.delete_backup = False
        self._emit_project_table_changes(['source', 'code_text', 'annotation', 'case_text'])

    def _emit_project_table_changes(self, tables):
        """Notify other open dialogs about changed project tables."""

        if getattr(self.app, "project_events", None) is not None:
            self.app.project_events.emit_table_changes(tables, source=self)

    def update_positions(self):
        """ Update positions for code text, annotations and case text as each character changes
        via adding or deleting.
        Called by text changed in textEdit.

        uses diff-match-patch module much faster than difflib with large text files that are
        annotated, coded, cased.
        consider diff_match_patch 20x faster

        diff_match_patch.diff_main() Output:
        Adding X at pos 0
            [(1, 'X'), (0, "I rea...")]
        Adding X at pos 4
            [(0, 'I re'), (1, 'X'), (0, "ally...")]
        Adding X at end of file
            [(0, "...appy to pay €200."), (1, 'X')]
        Removing 'really'
            [(0, 'I '), (-1, 'really'), (0, " like ...")]

        """
        self.text_has_changed = True

        if self.no_codes_annotes_cases:
            return
        self.text = self.ui.textEdit.toPlainText()
        diff = diff_match_patch.diff_match_patch()
        diff_list = diff.diff_main(self.prev_text, self.text)
        # print(diff_list)
        extending = True
        preceding_pos = 0
        chars_len = 0
        pre_chars_len = 0
        post_chars_len = 0
        if len(diff_list) == 2 and diff_list[0][0] == 1:
            # print("Add at start")
            chars_len = len(diff_list[0][1])
            pre_chars_len = 0
            preceding_pos = 0
        if len(diff_list) == 2 and diff_list[0][0] == -1:
            # print("Remove from start")
            extending = False
            chars_len = len(diff_list[0][1])
            pre_chars_len = 0
            preceding_pos = 0
            post_chars_len = len(diff_list[1][1])
        if len(diff_list) == 2 and diff_list[1][0] == 1:
            # print("Add at end")
            chars_len = len(diff_list[1][1])
            pre_chars_len = len(diff_list[0][1])
            preceding_pos = pre_chars_len - 1
        if len(diff_list) == 2 and diff_list[1][0] == -1:
            # print("Remove from end")
            extending = False
            chars_len = len(diff_list[1][1])
            post_chars_len = 0
            pre_chars_len = len(diff_list[0][1])
            preceding_pos = pre_chars_len - 1
        if len(diff_list) == 3 and diff_list[1][0] == 1:
            # print("Add in middle")
            chars_len = len(diff_list[1][1])
            pre_chars_len = len(diff_list[0][1])
            preceding_pos = pre_chars_len - 1
        if len(diff_list) == 3 and diff_list[1][0] == -1:
            # print("Delete from middle")
            extending = False
            chars_len = len(diff_list[1][1])
            pre_chars_len = len(diff_list[0][1])
            preceding_pos = pre_chars_len - 1
            post_chars_len = len(diff_list[2][1])
        # Adding characters
        if extending:
            for c in self.codetext:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= preceding_pos and c[
                    'newpos0'] >= preceding_pos - pre_chars_len:
                    c['newpos0'] += chars_len
                    c['newpos1'] += chars_len
                    changed = True
                if not changed and c['newpos0'] is not None and c['newpos0'] < preceding_pos < c['newpos1']:
                    c['newpos1'] += chars_len
            for c in self.annotations:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= preceding_pos and c[
                    'newpos0'] >= preceding_pos - pre_chars_len:
                    c['newpos0'] += chars_len
                    c['newpos1'] += chars_len
                    changed = True
                if c['newpos0'] is not None and not changed and c['newpos0'] < preceding_pos < c['newpos1']:
                    c['newpos1'] += chars_len
            for c in self.casetext:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= preceding_pos and c[
                    'newpos0'] >= preceding_pos - pre_chars_len:
                    c['newpos0'] += chars_len
                    c['newpos1'] += chars_len
                    changed = True
                if c['newpos0'] is not None and not changed and c['newpos0'] < preceding_pos < c['newpos1']:
                    c['newpos1'] += chars_len
            self.highlight()
            self.prev_text = copy(self.text)
            return
        # Removing characters
        if not extending:
            for c in self.codetext:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= preceding_pos and c[
                    'newpos0'] >= preceding_pos - pre_chars_len:
                    c['newpos0'] -= chars_len
                    c['newpos1'] -= chars_len
                    changed = True
                # Remove, as entire text is being removed (e.g. copy replace)
                if c['newpos0'] is not None and not changed and c['newpos0'] >= preceding_pos and \
                        c['newpos1'] < preceding_pos - pre_chars_len + post_chars_len:
                    c['newpos0'] -= chars_len
                    c['newpos1'] -= chars_len
                    changed = True
                    self.code_deletions.append(f"delete from code_text where ctid={c['ctid']}")
                    c['newpos0'] = None
                if c['newpos0'] is not None and not changed and c['newpos0'] < preceding_pos <= c['newpos1']:
                    c['newpos1'] -= chars_len
                    if c['newpos1'] < c['newpos0']:
                        self.code_deletions.append(f"delete from code_text where ctid={c['ctid']}")
                        c['newpos0'] = None
            for c in self.annotations:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= preceding_pos and c[
                    'newpos0'] >= preceding_pos - pre_chars_len:
                    c['newpos0'] -= chars_len
                    c['newpos1'] -= chars_len
                    changed = True
                # Remove, as entire text is being removed (e.g. copy replace)
                # De-nested to loop level (it sat inside the if that had just set changed=True) and
                # table name fixed: 'annotation', not 'annotations'.
                if c['newpos0'] is not None and not changed and c['newpos0'] >= preceding_pos and c[
                        'newpos1'] < preceding_pos - pre_chars_len + post_chars_len:
                    c['newpos0'] -= chars_len
                    c['newpos1'] -= chars_len
                    changed = True
                    self.code_deletions.append(f"delete from annotation where anid={c['anid']}")
                    c['newpos0'] = None
                if c['newpos0'] is not None and not changed and c['newpos0'] < preceding_pos <= c['newpos1']:
                    c['newpos1'] -= chars_len
                    if c['newpos1'] < c['newpos0']:
                        self.code_deletions.append(f"delete from annotation where anid={c['anid']}")
                        c['newpos0'] = None
            for c in self.casetext:
                changed = False
                if c['newpos0'] is not None and c['newpos0'] >= preceding_pos and c[
                    'newpos0'] >= preceding_pos - pre_chars_len:
                    c['newpos0'] -= chars_len
                    c['newpos1'] -= chars_len
                    changed = True
                # Remove, as entire text is being removed (e.g. copy replace)
                if c['newpos0'] is not None and not changed and c['newpos0'] >= preceding_pos and \
                        c['newpos1'] < preceding_pos - pre_chars_len + post_chars_len:
                    c['newpos0'] -= chars_len
                    c['newpos1'] -= chars_len
                    changed = True
                    self.code_deletions.append(f"delete from case_text where id={c['id']}")
                    c['newpos0'] = None
                if c['newpos0'] is not None and not changed and c['newpos0'] < preceding_pos <= c['newpos1']:
                    c['newpos1'] -= chars_len
                    if c['newpos1'] < c['newpos0']:
                        self.code_deletions.append(f"delete from case_text where id={c['id']}")
                        c['newpos0'] = None
        self.highlight()
        self.prev_text = copy(self.text)

    def update_casetext(self):
        """ Update linked case text positions. """

        sql = "update case_text set pos0=?, pos1=? where id=? and (pos0 !=? or pos1 !=?)"
        cur = self.app.conn.cursor()
        for c in self.casetext:
            if c['newpos0'] is not None:
                cur.execute(sql, [c['newpos0'], c['newpos1'], c['id'], c['newpos0'], c['newpos1']])
            if c['newpos1'] >= len(self.text):
                cur.execute("delete from case_text where id=?", [c['id']])

    def update_annotations(self):
        """ Update annotation positions. """

        sql = "update annotation set pos0=?, pos1=? where anid=? and (pos0 !=? or pos1 !=?)"
        cur = self.app.conn.cursor()
        for a in self.annotations:
            if a['newpos0'] is not None and a['newpos0'] >= 0:
                cur.execute(sql, [a['newpos0'], a['newpos1'], a['anid'], a['newpos0'], a['newpos1']])
            if a['newpos1'] >= len(self.text):
                cur.execute("delete from annotation where anid=?", [a['anid']])

    def update_codings(self):
        """ Update coding positions and seltext. """

        cur = self.app.conn.cursor()
        sql = "update code_text set pos0=?, pos1=?, seltext=? where ctid=?"
        for c in self.codetext:
            if c['newpos0'] is not None and c['newpos0'] >= 0:
                seltext = self.text[c['newpos0']:c['newpos1']]
                cur.execute(sql, [c['newpos0'], c['newpos1'], seltext, c['ctid']])
            if c['newpos1'] >= len(self.text):
                cur.execute("delete from code_text where ctid=?", [c['ctid']])

    def highlight(self):
        """ Add coding and annotation highlights. """

        self.remove_formatting()
        format_ = QtGui.QTextCharFormat()
        format_.setFontFamily(self.app.settings['font'])
        format_.setFontPointSize(self.app.settings['docfontsize'])

        self.ui.textEdit.blockSignals(True)
        cursor = self.ui.textEdit.textCursor()
        for item in self.casetext:
            if item['newpos0'] is not None:
                cursor.setPosition(int(item['newpos0']), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(int(item['newpos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
                format_.setFontUnderline(True)
                format_.setUnderlineColor(QtCore.Qt.GlobalColor.green)
                cursor.setCharFormat(format_)
        for item in self.annotations:
            if item['newpos0'] is not None:
                cursor.setPosition(int(item['newpos0']), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(int(item['newpos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
                format_.setFontUnderline(True)
                format_.setUnderlineColor(QtCore.Qt.GlobalColor.red)
                cursor.setCharFormat(format_)
        for item in self.codetext:
            if item['newpos0'] is not None:
                cursor.setPosition(int(item['newpos0']), QtGui.QTextCursor.MoveMode.MoveAnchor)
                cursor.setPosition(int(item['newpos1']), QtGui.QTextCursor.MoveMode.KeepAnchor)
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
