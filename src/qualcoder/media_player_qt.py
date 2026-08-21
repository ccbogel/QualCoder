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

Author: Colin Curtain C, Kai Dröge, Justin Missaghieh--Poncet, Lorenzo Salomón
https://github.com/ccbogel/QualCoder
https://qualcoder-org.github.io
https://qualcoder.wordpress.com/
https://qualcoder.org/
"""

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
import logging

logger = logging.getLogger(__name__)


class MediaInstance:
    """
    Mirrors vlc.Instance(): a factory for players and media.
    """

    def __init__(self, *args):
        pass

    def media_player_new(self):
        return MediaPlayer()

    def media_new(self, path):
        return Media(path)


class Media:
    """
    Mirrors vlc.Media for the calls the dialogs make.
    """

    def __init__(self, path):
        self.path = path
        self._duration = 0
        self._parsed = False

    def parse(self):
        """
        Synchronous duration probe; dialogs expect parse() to block.
        """
        if self._parsed:
            return
        probe = QMediaPlayer()
        out = QAudioOutput()
        probe.setAudioOutput(out)
        loop = QtCore.QEventLoop()
        done = {}

        def on_status(status):
            if status in (QMediaPlayer.MediaStatus.LoadedMedia,
                          QMediaPlayer.MediaStatus.InvalidMedia,
                          QMediaPlayer.MediaStatus.NoMedia):
                done['x'] = True
                loop.quit()
        probe.mediaStatusChanged.connect(on_status)
        probe.setSource(QtCore.QUrl.fromLocalFile(self.path))
        if not done:
            QtCore.QTimer.singleShot(4000, loop.quit)  # never hang on odd files
            loop.exec()
        self._duration = int(probe.duration() or 0)
        probe.setSource(QtCore.QUrl())
        self._parsed = True

    def get_duration(self):
        return self._duration


class MediaPlayer:
    """
    Mirrors the vlc.MediaPlayer surface used by code_av / view_av.
    """

    def __init__(self):
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.video_widget = None
        self._media = None
        self._host = None
        self._pending_ms = None
        self._want_playing = False  # play() intent while the media is still loading
        # Seek target + retry loop: setPosition is async and can be dropped;
        # get_time reports the target while converging.
        self._target_ms = None
        self._target_started = 0.0
        self._target_tries = 0
        # Pre-load seeks are queued; status/position signals and a timed
        # fallback apply or clear them.
        self.player.mediaStatusChanged.connect(self._apply_pending_seek)
        self.player.positionChanged.connect(self._position_moved)

    def _seek_ready(self):
        """
        Seek allowed with any media present; playing reports BufferingMedia
        and a stricter whitelist queued every seek forever.
        """
        return self.player.mediaStatus() not in (
            QMediaPlayer.MediaStatus.NoMedia,
            QMediaPlayer.MediaStatus.LoadingMedia,
            QMediaPlayer.MediaStatus.InvalidMedia)

    def _apply_pending_seek(self, status):
        logger.debug(f"QtMP status: {status}")
        if self._pending_ms is not None and status in (
                QMediaPlayer.MediaStatus.LoadedMedia,
                QMediaPlayer.MediaStatus.BufferedMedia,
                QMediaPlayer.MediaStatus.BufferingMedia):
            self.player.setPosition(self._pending_ms)
            self._pending_ms = None

    def _position_moved(self, pos):
        if self._target_ms is not None and abs(pos - self._target_ms) <= 400:
            self._target_ms = None  # seek reached
        if self._pending_ms is not None and self._target_ms is None and pos > 250:
            self._pending_ms = None

    def _force_pending(self):
        if self._pending_ms is not None:
            self.player.setPosition(self._pending_ms)
            self._pending_ms = None

    def _verify_seek(self):
        """
        Re-issue the seek until the player lands near the target: some
        platforms drop paused/stopped seeks.
        """
        import time as _time
        if self._target_ms is None:
            return
        pos = self.player.position()
        if abs(pos - self._target_ms) <= 400:
            self._target_ms = None
            return
        if self._target_tries >= 5 or (_time.monotonic() - self._target_started) > 2.5:
            logger.warning(f"seek to {self._target_ms} not confirmed (pos={pos}); releasing")
            self._target_ms = None
            return
        self._target_tries += 1
        loaded = self._seek_ready()
        if loaded and self._target_tries >= 3 \
                and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            # Stubborn backend while playing: classic pause-seek-resume sandwich
            self.player.pause()
            self.player.setPosition(self._target_ms)
            self.player.play()
        elif loaded:
            self.player.setPosition(self._target_ms)
        QtCore.QTimer.singleShot(300, self._verify_seek)

    # video embedding: the dialogs pass a winId; we instead fill the same
    # frame with a QVideoWidget, resolved from the widget registry.
    def set_video_host(self, frame_widget):
        """
        Extra to the vlc API: host frame for the video; reparents on
        detach/dock.
        """
        if self.video_widget is not None and self._host is frame_widget:
            return
        self._host = frame_widget
        if self.video_widget is None:
            self.video_widget = QVideoWidget(frame_widget)
            # If its window container goes native, keep ancestors alien
            self.video_widget.setAttribute(
                QtCore.Qt.WidgetAttribute.WA_DontCreateNativeAncestors, True)
            self.player.setVideoOutput(self.video_widget)
        else:
            old_lay = self.video_widget.parent().layout() if self.video_widget.parent() else None
            if old_lay is not None:
                old_lay.removeWidget(self.video_widget)
            self.video_widget.setParent(frame_widget)
        lay = frame_widget.layout()
        if lay is None:
            lay = QtWidgets.QVBoxLayout(frame_widget)
            lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.video_widget)
        self.video_widget.show()

    def set_hwnd(self, _winid):
        pass  # video goes through set_video_host; kept for call compatibility

    def set_xwindow(self, _winid):
        pass

    def set_nsobject(self, _winid):
        pass

    def video_set_mouse_input(self, _flag):
        pass

    def video_set_key_input(self, _flag):
        pass

    # media
    def set_media(self, media):
        self._media = media
        self.player.setSource(QtCore.QUrl.fromLocalFile(media.path))

    def get_media(self):
        return self._media

    # transport
    def play(self):
        self._want_playing = True
        if self.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia \
                and self._pending_ms is None:
            # Normalise the Windows restart-after-end path
            self.player.setPosition(0)
        self.player.play()
        if self._target_ms is not None:
            QtCore.QTimer.singleShot(300, self._verify_seek)
        if self._pending_ms is not None:
            # Timed fallback: apply the queued seek even if load signals are missed
            QtCore.QTimer.singleShot(400, self._force_pending)
        return 0

    def pause(self):
        self._want_playing = False
        self.player.pause()

    def stop(self):
        self._want_playing = False
        self._target_ms = None
        self.player.stop()

    def release(self):
        """ Free the file handle (stop() alone keeps it open on Windows) and
        tear down the video widget so no stale surface is left. """
        self.stop()
        self._pending_ms = None
        self._media = None
        self.player.setSource(QtCore.QUrl())
        try:
            self.player.setVideoOutput(None)
        except Exception:
            pass
        if self.video_widget is not None:
            self.video_widget.hide()
            self.video_widget.setParent(None)
            self.video_widget.deleteLater()
            self.video_widget = None
        self._host = None
        QtCore.QCoreApplication.processEvents()

    def is_playing(self):
        """
        Report playing while the play() intent holds during async startup;
        otherwise the update timer stops everything on its first tick.
        """
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            return 1
        if self._want_playing and self.player.mediaStatus() in (
                QMediaPlayer.MediaStatus.LoadingMedia,
                QMediaPlayer.MediaStatus.BufferingMedia,
                QMediaPlayer.MediaStatus.StalledMedia,
                QMediaPlayer.MediaStatus.LoadedMedia,
                QMediaPlayer.MediaStatus.BufferedMedia):
            return 1
        return 0

    def get_time(self):
        import time as _time
        if self._target_ms is not None:
            if (_time.monotonic() - self._target_started) < 2.5:
                # Converging: report the target so the UI cannot snap back to the
                # pre-seek position while the backend catches up.
                return self._target_ms
            self._target_ms = None
        if self._pending_ms is not None:
            return self._pending_ms
        return int(self.player.position())

    def set_time(self, msecs):
        import time as _time
        msecs = max(0, int(msecs))
        self._target_ms = msecs
        self._target_started = _time.monotonic()
        self._target_tries = 0
        if self._seek_ready():
            self.player.setPosition(msecs)
        else:
            self._pending_ms = msecs
        QtCore.QTimer.singleShot(250, self._verify_seek)

    def get_position(self):
        dur = self.player.duration()
        return (self.player.position() / dur) if dur else 0.0

    def set_position(self, fraction):
        dur = self.player.duration() or (self._media.get_duration() if self._media else 0)
        if dur:
            self.set_time(int(max(0.0, min(1.0, fraction)) * dur))

    def get_rate(self):
        return float(self.player.playbackRate() or 1.0)

    def set_rate(self, rate):
        self.player.setPlaybackRate(float(rate))

    # audio
    def audio_set_volume(self, vol):
        self.audio_output.setVolume(max(0, min(100, int(vol))) / 100.0)
        return 0

    def audio_get_track_count(self):
        try:
            n = len(self.player.audioTracks())
        except Exception:
            n = 1
        # vlc counts a "disable" pseudo-track, dialogs subtract accordingly
        return n + 1 if n else 0

    def audio_get_track_description(self):
        out = [(-1, b'Disable')]
        try:
            for i, tr in enumerate(self.player.audioTracks()):
                title = tr.stringValue(tr.Key.Title) or f"Track {i + 1}"
                out.append((i + 1, title.encode('utf-8')))
        except Exception:
            out.append((1, b'Track 1'))
        return out

    def audio_set_track(self, track_1based):
        try:
            self.player.setActiveAudioTrack(int(track_1based) - 1)
        except Exception:
            pass
        return 0

    def video_take_snapshot(self, _num, out_path, _w, _h):
        """
        Current frame to PNG; 0 on success as vlc.
        """
        try:
            sink = self.player.videoSink()
            frame = sink.videoFrame() if sink else None
            if frame is None or not frame.isValid():
                return -1
            img = frame.toImage()
            if img.isNull():
                return -1
            return 0 if img.save(out_path, "PNG") else -1
        except Exception as err:
            logger.warning(f"Qt snapshot failed: {err}")
            return -1


def make_vlc_instance(vlc_module):
    """ VLC instance for embedded playback: quiet console and no title
    overlay. Decoder and video output are left to VLC. """
    if vlc_module is None:
        return None
    flags = ["--quiet", "--no-video-title-show"]
    try:
        inst = vlc_module.Instance(flags)
        if inst is not None:
            logger.debug(f"vlc instance: {flags}")
            return inst
    except Exception as err:
        logger.debug(f"vlc arguments rejected ({err}); bare instance")
    logger.debug("vlc bare instance")
    return vlc_module.Instance()

_metadata_instance = None


def metadata_vlc_instance(vlc_module):
    """ Lightweight cached instance for reading media metadata: no video
    output is ever attached, so one per session is enough. """
    global _metadata_instance
    if _metadata_instance is None and vlc_module is not None:
        try:
            _metadata_instance = vlc_module.Instance(["--quiet", "--no-video"])
        except Exception:
            _metadata_instance = vlc_module.Instance()
    return _metadata_instance
