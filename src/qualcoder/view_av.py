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

from copy import copy
import datetime
# import difflib  # Use diff_match_patch as it is 20x faster. Keep this in case its needed later.
import diff_match_patch
import logging
import os
import platform
import qtawesome as qta  # see: https://pictogrammers.com/library/mdi/
import re
import subprocess
import time

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from .GUI.ui_dialog_view_av import Ui_Dialog_view_av
from .helpers import msecs_to_hours_mins_secs, Message, ExportDirectoryPathDialog
from .select_items import DialogSelectItems

# If VLC not installed, it will not crash
vlc = None
try:
    import vlc
except Exception as e:
    print(e)

path = os.path.abspath(os.path.dirname(__file__))
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
        tt = _("It is best to edit text before ANY coding has been applied.")
        tt += "\n" + _(
            "Avoid selecting sections of text with a combination of not underlined (not coded) and underlined (coded).")
        tt += "\n" + _(
            "Positions of the underlying codes / annotations / case-assigned may be incorrect if text is typed over or deleted.")
        tt += "\n" + _("Auto-save: Text changes are automatically saved every 20 seconds.")
        self.ui.label_note.setToolTip(tt)
        self.ui.label_transcription.setToolTip(tt)
        self.ui.textEdit.installEventFilter(self)
        self.installEventFilter(self)  # for rewind, play/stop, etc
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
        # Fedora 39 NameError: no function 'libvlc_new'
        try:
            self.instance = vlc.Instance()
        except NameError as name_err:
            logger.error(f"{name_err}")
            msg = f"{name_err}"
            Message(self.app, _("QualCoder will crash") + " " * 20, msg).exec()
        # Create an empty vlc media player
        self.mediaplayer = self.instance.media_player_new()
        self.mediaplayer.video_set_mouse_input(False)
        self.mediaplayer.video_set_key_input(False)
        self.ui.pushButton_play.clicked.connect(self.play_pause)
        self.ui.horizontalSlider_vol.valueChanged.connect(self.set_volume)
        self.ui.horizontalSlider_vol.setValue(99)
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
        # self.mediaplayer.audio_set_volume(0)
        self.ui.horizontalSlider_vol.setValue(100)
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
        self.mediaplayer.audio_set_volume(100)

        self.ui.textEdit.textChanged.connect(self.update_positions)
        self.textchanged_timer = QtCore.QTimer(self)
        self.textchanged_timer.setInterval(20000)  # 20 seconds
        self.textchanged_timer.start()
        self.textchanged_timer.timeout.connect(self.update_database_text)

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
        self.ui.horizontalSlider.setValue(int(result[1] / self.media.get_duration() * 1000))
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
        """ Insert speaker name using a settings format [name] {name} name:
        Up to 8 speakers can be selected from, 1 - 8.
        args:
            key: """

        list_pos = key - 49
        try:
            speaker = self.speaker_list[list_pos]
        except IndexError:
            return False
        if self.app.settings['speakernameformat'] == ":":
            self.ui.textEdit.insertPlainText(f"\n{speaker}: ")
        if self.app.settings['speakernameformat'] == "[]":
            self.ui.textEdit.insertPlainText(f"\n[{speaker}] ")
        if self.app.settings['speakernameformat'] == "{}":
            self.ui.textEdit.insertPlainText(f"\n{{{speaker}}} ")

    def insert_timestamp(self):
        """ Insert timestamp using settings format.
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
        self.ui.textEdit.insertPlainText(f"{ts}\n")
        # Code here makes the current text location visible on the textEdit pane
        text_cursor = self.ui.textEdit.textCursor()
        pos = text_cursor.position()
        text_cursor.setPosition(pos)
        self.ui.textEdit.setTextCursor(text_cursor)

    def add_speaker_names_to_label(self):
        """ Add speaker names to label, four on each line.
        Called by init, delete_speakernames, add_speakernames """

        txt = "Ctrl "
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
        self.textchanged_timer.stop()
        self.timer.stop()
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
                    if not changed and c['newpos0'] >= preceding_pos and c[
                        'newpos1'] < preceding_pos - pre_chars_len + post_chars_len:
                        c['newpos0'] -= chars_len
                        c['newpos1'] -= chars_len
                        changed = True
                        self.code_deletions.append(f"delete from annotations where anid={c['anid']}")
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
