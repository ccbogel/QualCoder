"""Regression tests for selecting a project to merge."""

from contextlib import ExitStack
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, call, patch

from qualcoder.special_functions import DialogSpecialFunctions


class TestMergeProjectSelection(TestCase):

    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.directory = Path(temporary_directory.name)
        self.current_project = self.directory / "current.qda"
        self.current_project.mkdir()
        self.dialog = SimpleNamespace(
            app=SimpleNamespace(
                settings={"directory": ""},
                project_path=self.current_project.as_posix(),
            ),
            merge_project_path="previous.qda",
            ui=SimpleNamespace(pushButton_merge=MagicMock()),
        )
        stack = self.enterContext(ExitStack())
        stack.enter_context(patch("builtins._", side_effect=lambda text: text, create=True))
        self.picker = stack.enter_context(patch(
            "qualcoder.special_functions.QtWidgets.QFileDialog.getExistingDirectory"
        ))
        self.message = stack.enter_context(patch("qualcoder.special_functions.Message"))

    def create_project(self, name: str = "source.qda", about: str = "QualCoder test") -> Path:
        """Create a minimal project with the requested folder name and identity."""
        project_directory = self.directory / name
        project_directory.mkdir()
        with sqlite3.connect(project_directory / "data.qda") as connection:
            connection.execute(
                "create table project (databaseversion text, date text, memo text, about text)"
            )
            connection.execute("insert into project values ('v17', '', '', ?)", (about,))
        connection.close()
        return project_directory

    def select(self, selected_path: str) -> None:
        """Simulate selecting a folder in the merge dialog."""
        self.picker.return_value = selected_path
        DialogSpecialFunctions.select_project_folder(self.dialog)

    def assert_rejected(self, expected_message: str) -> None:
        """Check that a rejected selection cannot run a stale merge."""
        self.assertEqual("", self.dialog.merge_project_path)
        self.dialog.ui.pushButton_merge.setEnabled.assert_called_once_with(False)
        self.message.assert_called_once()
        self.assertIn(expected_message, self.message.call_args.args[2])

    def test_trailing_separator_and_uppercase_suffix_are_accepted(self):
        project_directory = self.create_project("source.QDA")
        self.select(project_directory.as_posix() + "/")
        self.assertEqual(project_directory.as_posix(), self.dialog.merge_project_path)
        self.assertEqual(
            [call(False), call(True)],
            self.dialog.ui.pushButton_merge.setEnabled.call_args_list,
        )

    def test_cancel_clears_previous_selection_without_error(self):
        self.select("")
        self.assertEqual("", self.dialog.merge_project_path)
        self.dialog.ui.pushButton_merge.setEnabled.assert_called_once_with(False)
        self.message.assert_not_called()

    def test_wrong_suffix_is_rejected(self):
        self.select(self.directory.as_posix())
        self.assert_rejected("name must end with .qda")

    def test_missing_folder_is_rejected(self):
        self.select((self.directory / "missing.qda").as_posix())
        self.assert_rejected("could not be found or accessed")

    def test_same_project_with_trailing_separator_is_rejected(self):
        self.select(self.current_project.as_posix() + "/")
        self.assert_rejected("The same project")

    def test_same_project_with_relative_components_is_rejected(self):
        alias_path = self.current_project / ".." / self.current_project.name
        self.select(alias_path.as_posix())
        self.assert_rejected("The same project")

    def test_missing_database_is_not_created(self):
        project_directory = self.directory / "empty.qda"
        project_directory.mkdir()
        self.select(project_directory.as_posix())
        self.assert_rejected("No data.qda database found")
        self.assertFalse((project_directory / "data.qda").exists())

    def test_corrupt_database_is_rejected_without_changes(self):
        project_directory = self.directory / "corrupt.qda"
        project_directory.mkdir()
        database_path = project_directory / "data.qda"
        database_path.write_bytes(b"not a database")
        self.select(project_directory.as_posix())
        self.assert_rejected("database could not be opened")
        self.assertEqual(b"not a database", database_path.read_bytes())

    def test_unrelated_database_is_rejected(self):
        self.select(self.create_project(about="Another application").as_posix())
        self.assert_rejected("Not a QualCoder project")

    def test_empty_project_table_is_rejected(self):
        project_directory = self.create_project()
        with sqlite3.connect(project_directory / "data.qda") as connection:
            connection.execute("delete from project")
        connection.close()
        self.select(project_directory.as_posix())
        self.assert_rejected("Not a QualCoder project")

    def test_database_access_error_is_reported(self):
        project_directory = self.create_project()
        with patch("qualcoder.special_functions.sqlite3.connect",
                   side_effect=sqlite3.OperationalError("unable to open database file")):
            self.select(project_directory.as_posix())
        self.assert_rejected("unable to open database file")

    def test_validation_opens_database_read_only_and_closes_connection(self):
        project_directory = self.create_project("source #1.qda")
        with patch("qualcoder.special_functions.sqlite3.connect") as connect:
            connection = connect.return_value
            connection.execute.return_value.fetchone.return_value = ("v17", "", "", "QualCoder")
            self.select(project_directory.as_posix())
        connect.assert_called_once_with(
            (project_directory / "data.qda").resolve().as_uri() + "?mode=ro", uri=True
        )
        connection.close.assert_called_once()
        self.assertEqual(project_directory.as_posix(), self.dialog.merge_project_path)
