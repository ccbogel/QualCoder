from contextlib import closing
import datetime
import os
import sqlite3
import tempfile
from types import MethodType, SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from PyQt6 import QtCore, QtWidgets

from qualcoder.__main__ import MainWindow
from qualcoder.ai_chat import DialogAIChat


LEGACY_MESSAGES_SCHEMA = (
    "CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, chat_id INTEGER, "
    "msg_type TEXT, msg_author TEXT, msg_content TEXT, "
    "FOREIGN KEY (chat_id) REFERENCES chats(id))"
)


def make_chat_history(project_path: str) -> SimpleNamespace:
    """Initialize real chat storage with UI and event dependencies replaced."""

    dialog = SimpleNamespace(
        app=SimpleNamespace(project_path=project_path, project_events=MagicMock()),
        chat_history_conn=None,
        chat_list=[],
        chat_msg_list=[],
        fill_chat_list=MagicMock(),
        _update_undo_button_state=MagicMock(),
        _normalize_ai_profile_author=MagicMock(return_value="test-model"),
        replace_references=MagicMock(side_effect=lambda content, chat_idx: content),
        update_chat_window=MagicMock(),
        _clear_chat_ai_profile_snapshot=MagicMock(),
        current_streaming_chat_idx=0,
    )
    for name in (
        "init_ai_chat", "_close_chat_history_connection", "_emit_project_table_changes",
        "history_add_message", "history_add_or_append_agent_status", "history_update_message_list",
        "process_message", "ai_mcp_message_callback",
    ):
        setattr(dialog, name, MethodType(getattr(DialogAIChat, name), dialog))
    dialog.init_ai_chat()
    dialog.chat_history_conn.executemany(
        "INSERT INTO chats (id, name, analysis_type, date) VALUES (?, ?, ?, ?)",
        [(1, "First chat", "agent chat", "2026-10-01 10:00:00"),
         (2, "Second chat", "agent chat", "2026-10-02 10:00:00")],
    )
    dialog.chat_history_conn.commit()
    dialog.chat_list = dialog.chat_history_conn.execute(
        "SELECT id, name, analysis_type, summary, date, analysis_prompt FROM chats ORDER BY id"
    ).fetchall()
    dialog.current_chat_idx = 0
    return dialog


class TestChatMessageTimestamps(TestCase):
    """Exercise schema upgrades, all message writers and commit notifications."""

    def setUp(self):
        temporary_project = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_project.cleanup)
        self.dialog = make_chat_history(temporary_project.name)
        self.addCleanup(self.dialog._close_chat_history_connection)
        translate = patch("qualcoder.ai_chat._", side_effect=lambda text: text, create=True)
        translate.start()
        self.addCleanup(translate.stop)

    def test_upgrade_preserves_legacy_messages_and_existing_timestamps(self):
        connection = self.dialog.chat_history_conn
        connection.execute("DROP TABLE chat_messages")
        connection.execute(LEGACY_MESSAGES_SCHEMA)
        connection.execute("INSERT INTO chat_messages VALUES (1, 1, 'user', 'coder', 'Old question')")
        connection.commit()

        self.dialog.init_ai_chat()
        self.dialog.current_chat_idx = 0
        self.assertEqual(
            [(1, "Old question", None)],
            self.dialog.chat_history_conn.execute("SELECT id, msg_content, date FROM chat_messages").fetchall(),
        )
        self.dialog.history_add_message("user", "coder", "New question")
        saved_messages = self.dialog.chat_history_conn.execute("SELECT * FROM chat_messages ORDER BY id").fetchall()
        self.assertIsNotNone(saved_messages[1][5])

        self.dialog.init_ai_chat()
        self.assertEqual(
            saved_messages,
            self.dialog.chat_history_conn.execute("SELECT * FROM chat_messages ORDER BY id").fetchall(),
        )
        self.assertEqual(
            "2026-10-01 10:00:00",
            self.dialog.chat_history_conn.execute("SELECT date FROM chats WHERE id=1").fetchone()[0],
        )

    def test_user_and_ai_messages_are_dated_and_keep_the_five_column_history(self):
        observed_counts = []

        def observe_commit(tables: list[str], source: object) -> None:
            self.assertEqual(["chat_messages"], tables)
            self.assertIs(self.dialog, source)
            with closing(sqlite3.connect(self.dialog.chat_history_path)) as reader:
                observed_counts.append(reader.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0])

        self.dialog.app.project_events.emit_table_changes.side_effect = observe_commit
        with patch("qualcoder.ai_chat.datetime") as clock:
            clock.now.side_effect = [datetime.datetime(2026, 10, 19, 10, 0), datetime.datetime(2026, 10, 19, 10, 1)]
            self.dialog.history_add_message("user", "coder", "Question")
            self.dialog.history_add_message("ai", "test-model", "Answer")

        self.assertEqual(
            [("user", "2026-10-19 10:00:00"), ("ai", "2026-10-19 10:01:00")],
            self.dialog.chat_history_conn.execute("SELECT msg_type, date FROM chat_messages ORDER BY id").fetchall(),
        )
        self.assertEqual([1, 2], observed_counts)
        self.assertEqual(
            [(1, 1, "user", "coder", "Question"), (2, 1, "ai", "test-model", "Answer")],
            self.dialog.chat_msg_list,
        )
        self.dialog.history_update_message_list()
        self.assertEqual(
            ["2026-10-19 10:00:00", "2026-10-19 10:01:00"],
            [row[0] for row in self.dialog.chat_history_conn.execute("SELECT date FROM chat_messages ORDER BY id")],
        )

    def test_status_messages_are_dated_without_rewriting_duplicate_statuses(self):
        with patch("qualcoder.ai_chat.datetime") as clock:
            clock.now.side_effect = [datetime.datetime(2026, 10, 19, 10, 0), datetime.datetime(2026, 10, 19, 10, 1)]
            self.dialog.history_add_or_append_agent_status("Working")
            self.dialog.history_add_or_append_agent_status("Working")
            self.dialog.history_add_or_append_agent_status("Preparing response")

        self.assertEqual(
            [("Working", "2026-10-19 10:00:00"), ("Preparing response", "2026-10-19 10:01:00")],
            self.dialog.chat_history_conn.execute("SELECT msg_content, date FROM chat_messages ORDER BY id").fetchall(),
        )
        self.assertEqual(2, self.dialog.app.project_events.emit_table_changes.call_count)

    def test_uncommitted_messages_do_not_notify_or_leak_to_other_readers(self):
        with closing(sqlite3.connect(self.dialog.chat_history_path)) as writer:
            self.dialog.history_add_message("env_update", "system_event", "Internal update",
                                            db_conn=writer, refresh=False, commit=False)
            self.assertIsNotNone(writer.execute("SELECT date FROM chat_messages").fetchone()[0])
            self.assertEqual(0, self.dialog.chat_history_conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0])
            self.dialog.app.project_events.emit_table_changes.assert_not_called()
            writer.rollback()

    def test_batched_agent_messages_notify_after_commit(self):
        observed_messages = []

        def observe_commit(tables: list[str], source: object) -> None:
            with closing(sqlite3.connect(self.dialog.chat_history_path)) as reader:
                observed_messages.append(reader.execute("SELECT msg_type, date FROM chat_messages ORDER BY id").fetchall())

        self.dialog.app.project_events.emit_table_changes.side_effect = observe_commit
        self.dialog.ai_mcp_message_callback({
            "chat_idx": 0,
            "tool_messages": [{"msg_type": "env_update", "msg_content": "Internal update"}],
            "direct_info_message": "Finished",
        })

        self.assertEqual([["env_update"], ["env_update", "info"]],
                         [[row[0] for row in rows] for rows in observed_messages])
        self.assertTrue(all(row[1] for rows in observed_messages for row in rows))

    def test_deleting_a_chat_notifies_after_its_messages_are_removed(self):
        self.dialog.history_add_message("user", "coder", "Question")
        self.dialog.app.project_events.reset_mock()
        self.dialog._selected_chat_rows = MagicMock(return_value=[0])
        self.dialog._display_chat_name = MagicMock(return_value="First chat")

        with patch("qualcoder.ai_chat.DialogConfirmDelete") as confirm:
            confirm.return_value.exec.return_value = True
            DialogAIChat.delete_chat(self.dialog)

        self.assertEqual([], self.dialog.chat_history_conn.execute("SELECT * FROM chat_messages").fetchall())
        self.assertEqual([(2,)], self.dialog.chat_history_conn.execute("SELECT id FROM chats").fetchall())
        self.dialog.app.project_events.emit_table_changes.assert_called_once_with(
            ["chats", "chat_messages"], source=self.dialog,
        )


class TestRecentChatActivity(TestCase):
    """Verify activity selection and labels against real project and chat databases."""

    def setUp(self):
        temporary_project = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_project.cleanup)
        self.dialog = make_chat_history(temporary_project.name)
        self.addCleanup(self.dialog._close_chat_history_connection)
        project_connection = sqlite3.connect(":memory:")
        self.addCleanup(project_connection.close)
        project_connection.executescript(
            "CREATE TABLE source (id INTEGER, name TEXT);"
            "CREATE TABLE code_text (fid INTEGER, pos0 INTEGER, pos1 INTEGER, date TEXT, owner TEXT);"
            "CREATE TABLE code_image (id INTEGER, date TEXT, owner TEXT);"
            "CREATE TABLE code_av (id INTEGER, date TEXT, owner TEXT);"
            "CREATE TABLE journal (jid INTEGER, name TEXT, date TEXT);"
            "CREATE TABLE project (bookmarkfile INTEGER, bookmarkpos INTEGER, avbookmarkfile INTEGER, avbookmarkmsec INTEGER);"
            "INSERT INTO source VALUES (1, 'Interview');"
            "INSERT INTO code_text VALUES (1, 10, 20, '2026-10-18 10:00:00', 'coder');"
            "INSERT INTO journal VALUES (1, 'Notes', '2026-10-18 11:00:00');"
            "INSERT INTO project VALUES (1, 10, 1, 65000);"
        )
        self.window = SimpleNamespace(
            app=SimpleNamespace(project_path=temporary_project.name, conn=project_connection,
                                settings={"ai_enable": "True", "codername": "coder"}),
            ai_chat_window=None,
            format_activity_date=MainWindow.format_activity_date,
        )
        self.window.last_ai_chat = MethodType(MainWindow.last_ai_chat, self.window)
        translate = patch("qualcoder.__main__._", side_effect=lambda text: text, create=True)
        translate.start()
        self.addCleanup(translate.stop)

    def insert_message(self, chat_id: int, msg_type: str, date_text: str | None) -> None:
        self.dialog.chat_history_conn.execute(
            "INSERT INTO chat_messages (chat_id, msg_type, msg_content, date) VALUES (?, ?, 'Message', ?)",
            (chat_id, msg_type, date_text),
        )
        self.dialog.chat_history_conn.commit()

    def test_latest_visible_timestamp_wins_over_message_id_and_internal_records(self):
        self.insert_message(1, "ai", "2026-10-19 16:00:00")
        self.insert_message(2, "user", "2026-10-19 15:00:00")
        self.insert_message(2, "user", None)
        for msg_type in ("system", "instruct", "tool_call", "tool_result", "single_instruct",
                         "prompt", "agent_state", "env_update"):
            self.insert_message(2, msg_type, "2026-10-19 18:00:00")

        self.assertEqual((1, "First chat", "2026-10-19 16:00:00"), self.window.last_ai_chat())
        self.insert_message(2, "agent_status", "2026-10-19 16:00:00")
        self.assertEqual((2, "Second chat", "2026-10-19 16:00:00"), self.window.last_ai_chat())

    def test_legacy_history_can_be_read_without_upgrading_it(self):
        connection = self.dialog.chat_history_conn
        connection.execute("DROP TABLE chat_messages")
        connection.execute(LEGACY_MESSAGES_SCHEMA)
        connection.executemany(
            "INSERT INTO chat_messages (chat_id, msg_type) VALUES (?, ?)",
            [(1, "ai"), (2, "user"), (1, "env_update")],
        )
        connection.commit()

        self.assertEqual((2, "Second chat", "2026-10-02 10:00:00"), self.window.last_ai_chat())
        self.assertNotIn("date", [row[1] for row in connection.execute("PRAGMA table_info(chat_messages)")])
        self.assertEqual(("Second chat", "AI chat, last changed 2026-10-02 10:00", 2, "2026-10-02 10:00:00"),
                         MainWindow.collect_recent_activity(self.window)["ai_chat"])

        self.dialog.init_ai_chat()
        self.assertEqual((2, "Second chat", "2026-10-02 10:00:00"), self.window.last_ai_chat())

    def test_missing_message_dates_use_chat_creation_dates_for_ordering(self):
        self.insert_message(2, "user", None)
        self.insert_message(1, "ai", None)
        self.insert_message(1, "info", "")
        self.assertEqual((2, "Second chat", "2026-10-02 10:00:00"), self.window.last_ai_chat())

        self.insert_message(1, "ai", "2026-10-03 12:00:00")
        self.insert_message(2, "user", None)
        self.assertEqual((1, "First chat", "2026-10-03 12:00:00"), self.window.last_ai_chat())
        self.assertEqual(
            [(None,), (None,), ("",), ("2026-10-03 12:00:00",), (None,)],
            self.dialog.chat_history_conn.execute("SELECT date FROM chat_messages ORDER BY id").fetchall(),
        )

    def test_empty_chats_and_empty_history_have_no_ai_activity(self):
        self.assertIsNone(self.window.last_ai_chat())
        self.assertNotIn("ai_chat", MainWindow.collect_recent_activity(self.window))

        self.dialog.chat_history_conn.execute("DELETE FROM chats")
        self.dialog.chat_history_conn.commit()
        self.assertIsNone(self.window.last_ai_chat())
        self.assertNotIn("ai_chat", MainWindow.collect_recent_activity(self.window))

    def test_project_without_a_chat_database_has_no_ai_activity(self):
        with tempfile.TemporaryDirectory() as empty_project:
            self.window.app.project_path = empty_project
            self.assertIsNone(self.window.last_ai_chat())
            self.assertNotIn("ai_chat", MainWindow.collect_recent_activity(self.window))
            self.assertFalse(os.path.exists(os.path.join(empty_project, "ai_data", "chat_history.sqlite")))

    def test_internal_messages_alone_have_no_ai_activity(self):
        self.insert_message(1, "prompt", "2026-10-19 10:00:00")
        self.insert_message(1, "env_update", "2026-10-19 10:01:00")
        self.assertIsNone(self.window.last_ai_chat())
        self.assertNotIn("ai_chat", MainWindow.collect_recent_activity(self.window))

    def test_activity_labels_and_sort_dates_use_the_latest_message(self):
        today_text = datetime.date.today().strftime("%Y-%m-%d")
        self.insert_message(1, "info", f"{today_text} 14:32:00")
        activity = MainWindow.collect_recent_activity(self.window)

        self.assertEqual(("First chat", "AI chat, last changed today 14:32", 1, f"{today_text} 14:32:00"),
                         activity["ai_chat"])
        self.assertEqual("2026-10-18 10:00:00", activity["coded"][3])
        self.assertEqual("2026-10-18 11:00:00", activity["journal"][3])
        self.assertIsNone(activity["text_bookmark"][3])
        self.assertIsNone(activity["av_bookmark"][3])

        self.dialog.chat_history_conn.execute("UPDATE chat_messages SET date=NULL")
        self.dialog.chat_history_conn.commit()
        self.assertEqual(("First chat", "AI chat, last changed 2026-10-01 10:00", 1, "2026-10-01 10:00:00"),
                         MainWindow.collect_recent_activity(self.window)["ai_chat"])

    def test_activity_date_labels_cover_today_yesterday_and_older_dates(self):
        today = datetime.date.today()
        self.assertEqual("today 14:32", MainWindow.format_activity_date(f"{today} 14:32:00"))
        self.assertEqual("yesterday 14:32", MainWindow.format_activity_date(f"{today - datetime.timedelta(days=1)} 14:32:00"))
        older_day = today - datetime.timedelta(days=2)
        self.assertEqual(f"{older_day} 14:32", MainWindow.format_activity_date(f"{older_day} 14:32:00"))
        self.assertEqual("", MainWindow.format_activity_date(None))

    def test_chat_changes_schedule_a_refresh_without_checking_file_links(self):
        self.window.request_project_summary_update = MagicMock()
        self.window.project_summary_check_links = False
        for table_name in ("chats", "chat_messages"):
            with self.subTest(table=table_name):
                self.window.request_project_summary_update.reset_mock()
                MainWindow.schedule_project_summary_update(self.window, [table_name], self.dialog)
                self.window.request_project_summary_update.assert_called_once_with(check_links=False)
                self.assertFalse(self.window.project_summary_check_links)


class TestRecentActivityRows(TestCase):
    """Check physical row ordering, undated fallbacks and refreshes with real Qt widgets."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_rows_reorder_by_date_and_keep_undated_entries_stable(self):
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        rows = {}
        for key in ("coded", "text_bookmark", "av_bookmark", "journal", "ai_chat"):
            row = QtWidgets.QFrame(panel)
            row.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
            layout.addWidget(row)
            rows[key] = {"row": row, "title": QtWidgets.QLabel(row), "detail": QtWidgets.QLabel(row)}
        window = SimpleNamespace(recent_activity_rows=rows, ui=SimpleNamespace(
            verticalLayout_recent_activity=layout, label_recent_activity_empty=QtWidgets.QLabel(panel),
        ))
        activity = {
            "coded": ("Interview", "Coding", ("text", 1), "2026-10-19 10:00:00"),
            "text_bookmark": ("Interview", "Bookmark", None, None),
            "av_bookmark": ("Recording", "Bookmark", None, None),
            "journal": ("Notes", "Journal", 3, "2026-10-19 11:00:00"),
            "ai_chat": ("First chat", "Chat", 1, "2026-10-19 12:00:00"),
        }

        MainWindow.show_recent_activity(window, activity)
        self.assertEqual(
            [rows[key]["row"] for key in ("ai_chat", "journal", "coded", "text_bookmark", "av_bookmark")],
            [layout.itemAt(index).widget() for index in range(layout.count())],
        )
        self.assertEqual(1, window.recent_activity_targets["ai_chat"])
        self.assertEqual("First chat, Chat", rows["ai_chat"]["row"].accessibleName())
        self.assertTrue(window.ui.label_recent_activity_empty.isHidden())

        activity["coded"] = ("Interview", "Coding", ("text", 1), "2026-10-19 13:00:00")
        activity["ai_chat"] = ("Old chat", "Last AI chat", 1, None)
        MainWindow.show_recent_activity(window, activity)
        self.assertEqual(
            [rows[key]["row"] for key in ("coded", "journal", "text_bookmark", "av_bookmark", "ai_chat")],
            [layout.itemAt(index).widget() for index in range(layout.count())],
        )
        self.assertEqual("Old chat", rows["ai_chat"]["title"].text())

        del activity["ai_chat"]
        MainWindow.show_recent_activity(window, activity)
        self.assertTrue(rows["ai_chat"]["row"].isHidden())
        self.assertNotIn("ai_chat", window.recent_activity_targets)
        self.assertFalse(rows["coded"]["row"].isHidden())
        self.assertTrue(window.ui.label_recent_activity_empty.isHidden())

        MainWindow.show_recent_activity(window, {})
        self.assertEqual({}, window.recent_activity_targets)
        self.assertTrue(all(row["row"].isHidden() for row in rows.values()))
        self.assertFalse(window.ui.label_recent_activity_empty.isHidden())
