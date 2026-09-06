import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from qualcoder.__main__ import MainWindow, ProjectOpenError


class TestProjectOpening(TestCase):
    """Regression tests for selecting and validating QualCoder projects."""

    @staticmethod
    def _create_project(project_directory: Path, about: str = "QualCoder test") -> None:
        project_directory.mkdir()
        connection = sqlite3.connect(project_directory / "data.qda")
        connection.execute(
            "create table project (databaseversion text, date text, memo text, about text)"
        )
        connection.execute(
            "insert into project values (?, ?, ?, ?)",
            ("v17", "2026-09-06 12:00:00", "", about),
        )
        connection.commit()
        connection.close()

    @staticmethod
    def _window_with_open_project() -> tuple[SimpleNamespace, object, object]:
        existing_connection = object()
        journal_display = object()
        app = SimpleNamespace(
            settings={"directory": ""},
            project_path="current.qda",
            project_name="current.qda",
            conn=existing_connection,
        )
        window = SimpleNamespace(
            app=app,
            journal_display=journal_display,
            close_project=MagicMock(),
            _open_project_connection=MainWindow._open_project_connection,
        )
        return window, existing_connection, journal_display

    def test_trailing_separator_is_normalized_before_validation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_directory = Path(temporary_directory) / "example.qda"
            self._create_project(project_directory)

            selected_path = f"{project_directory}{os.sep}"
            normalized_path, connection = MainWindow._open_project_connection(selected_path)

            self.assertEqual(project_directory.as_posix(), normalized_path)
            self.assertEqual("v17", connection.execute(
                "select databaseversion from project"
            ).fetchone()[0])
            connection.close()

    def test_folder_without_qda_suffix_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            with self.assertRaises(ProjectOpenError) as context:
                MainWindow._open_project_connection(temporary_directory)

        self.assertEqual("wrong_suffix", context.exception.reason)

    def test_project_folder_without_database_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_directory = Path(temporary_directory) / "empty.qda"
            project_directory.mkdir()

            with self.assertRaises(ProjectOpenError) as context:
                MainWindow._open_project_connection(str(project_directory))

        self.assertEqual("missing_database", context.exception.reason)

    def test_invalid_database_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_directory = Path(temporary_directory) / "invalid.qda"
            project_directory.mkdir()
            (project_directory / "data.qda").write_text("not a database", encoding="utf-8")

            with self.assertRaises(ProjectOpenError) as context:
                MainWindow._open_project_connection(str(project_directory))

        self.assertEqual("invalid_database", context.exception.reason)

    def test_cancel_keeps_the_current_project_untouched(self):
        window, existing_connection, journal_display = self._window_with_open_project()

        with patch("builtins._", side_effect=lambda text: text, create=True), \
                patch.object(
                    MainWindow,
                    "_open_project_connection",
                    wraps=MainWindow._open_project_connection,
                ) as open_connection, \
                patch("qualcoder.__main__.QtWidgets.QFileDialog.getExistingDirectory", return_value=""), \
                patch("qualcoder.__main__.Message") as message_class:
            MainWindow.open_project(window)

        open_connection.assert_not_called()
        window.close_project.assert_not_called()
        message_class.assert_not_called()
        self.assertIs(existing_connection, window.app.conn)
        self.assertEqual("current.qda", window.app.project_path)
        self.assertEqual("current.qda", window.app.project_name)
        self.assertIs(journal_display, window.journal_display)

    def test_database_open_error_keeps_the_current_project_untouched(self):
        window, existing_connection, journal_display = self._window_with_open_project()
        with tempfile.TemporaryDirectory() as temporary_directory:
            project_directory = Path(temporary_directory) / "unavailable.qda"
            project_directory.mkdir()
            (project_directory / "data.qda").touch()

            with patch("builtins._", side_effect=lambda text: text, create=True), \
                    patch(
                        "qualcoder.__main__.sqlite3.connect",
                        side_effect=sqlite3.OperationalError("database is locked"),
                    ), patch("qualcoder.__main__.Message") as message_class:
                MainWindow.open_project(window, str(project_directory))

        window.close_project.assert_not_called()
        self.assertIs(existing_connection, window.app.conn)
        self.assertEqual("current.qda", window.app.project_path)
        self.assertEqual("current.qda", window.app.project_name)
        self.assertIs(journal_display, window.journal_display)
        message_class.assert_called_once()
        self.assertEqual("Cannot open project", message_class.call_args.args[1])
        self.assertIn("The project database could not be opened.", message_class.call_args.args[2])
        self.assertIn("database is locked", message_class.call_args.args[2])

    def test_wrong_folder_shows_clear_error_and_keeps_current_project(self):
        window, existing_connection, journal_display = self._window_with_open_project()
        with tempfile.TemporaryDirectory() as temporary_directory:
            with patch("builtins._", side_effect=lambda text: text, create=True), \
                    patch("qualcoder.__main__.Message") as message_class:
                MainWindow.open_project(window, temporary_directory)

        window.close_project.assert_not_called()
        self.assertIs(existing_connection, window.app.conn)
        self.assertIs(journal_display, window.journal_display)
        message_class.assert_called_once()
        self.assertEqual("Cannot open project", message_class.call_args.args[1])
        self.assertIn("name must end with .qda", message_class.call_args.args[2])

    def test_backup_cleanup_is_separator_independent(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent_directory = Path(temporary_directory)
            project_directory = parent_directory / "current.qda"
            project_directory.mkdir()
            backup_names = [
                "current_BKUP_20260906_10.qda",
                "current_BKUP_20260906_11.qda",
                "current_BKUP_20260906_12.qda",
            ]
            for backup_name in backup_names:
                (parent_directory / backup_name).mkdir()
            app = SimpleNamespace(
                project_path=str(project_directory),
                delete_backup_path_name="",
                delete_backup=False,
                settings={"backup_num": 2},
            )
            window = SimpleNamespace(
                app=app,
                ui=SimpleNamespace(textEdit=SimpleNamespace(append=MagicMock())),
            )

            MainWindow.delete_backup_folders(window)

            self.assertFalse((parent_directory / backup_names[0]).exists())
            self.assertTrue((parent_directory / backup_names[1]).exists())
            self.assertTrue((parent_directory / backup_names[2]).exists())
