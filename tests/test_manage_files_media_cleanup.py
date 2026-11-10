from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock

from PyQt6 import QtCore, QtWidgets

from qualcoder.manage_files import DialogManageFiles
from qualcoder.view_av import DialogViewAV


class TestMediaCleanup(TestCase):
    """Check player teardown ordering when deleting an open media file."""

    @classmethod
    def setUpClass(cls):
        cls.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_close_stops_all_timers_before_player_teardown(self):
        host = QtWidgets.QWidget()
        # Include the playback/save timers, watchdog and waveform polling timer.
        timers = [QtCore.QTimer(host) for _index in range(4)]
        for timer in timers:
            timer.start(60000)
        player_type = type("Player", (), {"__module__": "qualcoder.media_player_qt"})
        player = player_type()

        def assert_timers_stopped():
            self.qt_app.processEvents()
            self.assertTrue(all(not timer.isActive() for timer in timers))

        player.release = Mock(side_effect=assert_timers_stopped)
        dialog = SimpleNamespace(
            findChildren=host.findChildren,
            update_sizes=Mock(),
            ddialog=SimpleNamespace(close=Mock(side_effect=assert_timers_stopped)),
            stop=Mock(side_effect=assert_timers_stopped),
            mediaplayer=player,
            app=SimpleNamespace(write_config_ini=Mock(), settings={}, ai_models=[]),
            update_database_text=Mock(),
        )

        DialogViewAV.closeEvent(dialog, None)

        player.release.assert_called_once_with()
        dialog.update_database_text.assert_called_once_with()

    def test_delete_closes_viewer_without_releasing_player_first(self):
        viewer = Mock()
        dialog = SimpleNamespace(av_dialog_open=viewer, visible_selected_rows=lambda: [])

        DialogManageFiles.delete(dialog)

        viewer.close.assert_called_once_with()
        viewer.mediaplayer.stop.assert_not_called()
        viewer.mediaplayer.release.assert_not_called()
        self.assertIsNone(dialog.av_dialog_open)

    def test_close_handles_missing_or_uninitialized_player(self):
        for player_attribute_present in (False, True):
            with self.subTest(player_attribute_present=player_attribute_present):
                dialog = DialogViewAV.__new__(DialogViewAV)
                QtWidgets.QDialog.__init__(dialog)
                if player_attribute_present:
                    dialog.mediaplayer = None
                timer = QtCore.QTimer(dialog)
                timer.start(60000)
                try:
                    # No UI, detached window or save state has been initialized.
                    DialogViewAV.closeEvent(dialog, None)

                    self.assertFalse(timer.isActive())
                finally:
                    dialog.deleteLater()

    def test_bulk_delete_closes_viewer_without_releasing_player_first(self):
        viewer = Mock()
        dialog = SimpleNamespace(av_dialog_open=viewer, source=[])

        DialogManageFiles.delete_button_multiple_files(dialog)

        viewer.close.assert_called_once_with()
        viewer.mediaplayer.stop.assert_not_called()
        viewer.mediaplayer.release.assert_not_called()
        self.assertIsNone(dialog.av_dialog_open)
