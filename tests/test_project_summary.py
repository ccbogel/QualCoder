from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from PyQt6 import QtCore, QtWidgets

from qualcoder.__main__ import MainWindow
from qualcoder.GUI.ui_main import Ui_MainWindow


class TestProjectSummaryChats(TestCase):
    """Verify saved-chat counts and tile visibility using the real Project tab UI."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        temporary_project = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_project.cleanup)
        self.history_path = Path(temporary_project.name) / "ai_data" / "chat_history.sqlite"
        self.project_connection = sqlite3.connect(":memory:")
        self.addCleanup(self.project_connection.close)
        self.project_connection.executescript(
            "CREATE TABLE cases (caseid INTEGER); INSERT INTO cases VALUES (1), (2);"
            "CREATE TABLE code_name (cid INTEGER); INSERT INTO code_name VALUES (1), (2), (3);"
            "CREATE TABLE journal (jid INTEGER); INSERT INTO journal VALUES (1);"
        )
        translate = patch("qualcoder.__main__._", side_effect=lambda text: text, create=True)
        translate.start()
        self.addCleanup(translate.stop)
        self.window = MainWindow.__new__(MainWindow)
        QtWidgets.QMainWindow.__init__(self.window)
        self.window.ui = Ui_MainWindow()
        self.window.ui.setupUi(self.window)
        self.window.app = SimpleNamespace(
            conn=self.project_connection, project_path=temporary_project.name, settings={"ai_enable": "False"},
            get_pdf_filenames=MagicMock(return_value=["document.pdf"]),
            get_text_filenames=MagicMock(return_value=["interview.txt", "document.pdf"]),
            get_image_filenames=MagicMock(return_value=["photo.jpg"]),
            get_av_filenames=MagicMock(return_value=["recording.mp3"]),
        )
        self.window.project_cards = {}
        self.window.project_panel_colors = {"secondary": "#888888"}
        self.window.project_summary_check_links = False
        self.window.collect_recent_activity = MagicMock(return_value={})
        self.window.show_recent_activity = MagicMock()
        self.window.build_project_summary_tiles()

    def tearDown(self):
        self.window.hide()
        self.window.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)

    def write_chats(self, count: int) -> None:
        """Create current and legacy conversations without message storage."""

        self.history_path.parent.mkdir(exist_ok=True)
        with closing(sqlite3.connect(self.history_path)) as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY, analysis_type TEXT)")
            connection.execute("DELETE FROM chats")
            chat_types = ("agent chat", "general chat", "code chat")
            connection.executemany("INSERT INTO chats (analysis_type) VALUES (?)",
                                   [(chat_types[index % len(chat_types)],) for index in range(count)])
            connection.commit()

    def test_long_activity_text_does_not_change_panel_widths(self):
        self.window.build_recent_activity_rows()
        self.window.update_project_summary_panel()
        self.window.resize(1100, 800)
        self.window.show()
        short_title = "Interview"
        long_title = 'Topic exploration "Wandel der Rolle der Väter" ' * 20
        for window_width in (1100, 1400):
            self.window.resize(window_width, 800)
            for title_text in (short_title, long_title, short_title):
                MainWindow.show_recent_activity(self.window, {
                    "ai_chat": (title_text, "AI chat, last changed today 18:44", 1, "2026-10-19 18:44:00")})
                self.qt_app.processEvents()
                panel_widths = (self.window.ui.frame_recent_activity.width(),
                                self.window.ui.frame_project_summary.width())
                if title_text == short_title:
                    expected_widths = panel_widths
                else:
                    self.assertEqual(expected_widths, panel_widths)
                    title_label = self.window.recent_activity_rows["ai_chat"]["title"]
                    self.assertEqual(long_title, title_label.text())
                    self.assertEqual(long_title, title_label.toolTip())
                    self.assertIn(long_title, self.window.recent_activity_rows["ai_chat"]["row"].toolTip())
                    self.assertGreater(title_label.fontMetrics().horizontalAdvance(long_title), title_label.width())
                    # Render the custom paint path as well as exercising layout negotiation.
                    self.assertFalse(title_label.grab().isNull())

    def test_chat_tile_visibility_matches_count_and_ai_setting(self):
        tile = self.window.project_summary_tiles["ai_chats"]
        for count in (0, 3):
            self.write_chats(count)
            for ai_enabled in ("False", "True"):
                with self.subTest(chats=count, ai_enabled=ai_enabled):
                    self.window.app.settings["ai_enable"] = ai_enabled
                    self.window.update_project_summary_panel()

                    self.assertEqual(str(count), tile["value"].text())
                    self.assertEqual(count == 0 and ai_enabled == "False", tile["tile"].isHidden())
                    self.assertEqual(f"AI agent chats: {count}", tile["tile"].accessibleName())
                    for tile_key, expected in (("files", 4), ("cases", 2), ("codes", 3), ("journals", 1)):
                        self.assertEqual(str(expected), self.window.project_summary_tiles[tile_key]["value"].text())
                        self.assertFalse(self.window.project_summary_tiles[tile_key]["tile"].isHidden())

    def test_missing_chat_storage_counts_zero_without_creating_files(self):
        tile = self.window.project_summary_tiles["ai_chats"]
        for ai_enabled in ("False", "True"):
            with self.subTest(ai_enabled=ai_enabled):
                self.window.app.settings["ai_enable"] = ai_enabled
                self.window.update_project_summary_panel()
                self.assertEqual("0", tile["value"].text())
                self.assertEqual(ai_enabled == "False", tile["tile"].isHidden())
                self.assertFalse(self.history_path.parent.exists())

    def test_cache_only_database_counts_zero_without_creating_chat_tables(self):
        self.history_path.parent.mkdir()
        with closing(sqlite3.connect(self.history_path)) as connection:
            connection.execute("CREATE TABLE mcp_vector_search_cache (id INTEGER PRIMARY KEY)")
            connection.commit()

        self.window.app.settings["ai_enable"] = "True"
        self.window.update_project_summary_panel()
        self.assertEqual("0", self.window.project_summary_tiles["ai_chats"]["value"].text())
        with closing(sqlite3.connect(self.history_path)) as connection:
            self.assertEqual([("mcp_vector_search_cache",)], connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall())

    def test_count_refreshes_after_creation_deletion_and_project_close(self):
        tile = self.window.project_summary_tiles["ai_chats"]
        for count in (1, 2, 0):
            self.write_chats(count)
            self.window.update_project_summary_panel()
            self.assertEqual(str(count), tile["value"].text())
            self.assertEqual(count == 0, tile["tile"].isHidden())

        self.write_chats(2)
        self.window.app.settings["ai_enable"] = "True"
        self.window.app.conn = None
        self.window.update_project_summary_panel()
        self.assertTrue(all(entry["tile"].isHidden() for entry in self.window.project_summary_tiles.values()))
        self.assertTrue(self.window.ui.label_project_summary_files.isHidden())
