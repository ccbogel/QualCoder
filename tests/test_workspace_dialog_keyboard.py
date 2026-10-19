from contextlib import contextmanager
from importlib import import_module
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtTest import QSignalSpy, QTest


WORKSPACE_DIALOGS = (
    ("attributes", "DialogManageAttributes", "Ui_Dialog_manage_attributes"),
    ("code_color_scheme", "DialogCodeColorScheme", "Ui_Dialog_code_colors"),
    ("import_survey", "DialogImportSurvey", "Ui_Dialog_Import"),
    ("manage_links", "DialogManageLinks", "Ui_Dialog_manage_links"),
    ("reports", "DialogReportCodeFrequencies", "Ui_Dialog_reportCodeFrequencies"),
    ("reports", "DialogReportCoderComparisons", "Ui_Dialog_reportComparisons"),
    ("report_codes", "DialogReportCodes", "Ui_Dialog_reportCodings"),
    ("report_codes_by_segments", "DialogCodesBySegments", "Ui_DialogSegmentCodings"),
    ("report_code_summary", "DialogReportCodeSummary", "Ui_Dialog_code_summary"),
    ("report_compare_coder_file", "DialogCompareCoderByFile", "Ui_Dialog_reportCompareCoderFile"),
    ("report_comparison_table", "DialogReportComparisonTable", "Ui_Dialog_Comparisons"),
    ("report_cooccurrence", "DialogReportCooccurrence", "Ui_Dialog_Coocurrence"),
    ("report_exact_matches", "DialogReportExactTextMatches", "Ui_DialogMatchingTextSegments"),
    ("report_file_summary", "DialogReportFileSummary", "Ui_Dialog_file_summary"),
    ("report_relations", "DialogReportRelations", "Ui_Dialog_CodeRelations"),
    ("view_charts", "ViewCharts", "Ui_DialogCharts"),
)


class TestWorkspaceDialogKeyboard(TestCase):
    """Check Escape propagation and existing dialog actions in embedded views."""

    @classmethod
    def setUpClass(cls):
        cls.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    @contextmanager
    def _workspace(self, module_name: str, class_name: str, ui_name: str):
        """Build a real form without opening a project or running database queries.

        Args:
            module_name: QualCoder module containing the workspace class.
            class_name: Workspace dialog class to exercise.
            ui_name: Generated form class used by that workspace.
        """

        module = import_module("qualcoder." + module_name)
        dialog_type = getattr(module, class_name)
        host = QtWidgets.QWidget()
        dialog = dialog_type.__new__(dialog_type)
        QtWidgets.QDialog.__init__(dialog)
        dialog.app = SimpleNamespace(settings={})
        dialog.ui = getattr(module, ui_name)()
        dialog.ui.setupUi(dialog)
        layout = QtWidgets.QVBoxLayout(host)
        layout.addWidget(dialog)
        host.show()
        self.qt_app.processEvents()
        try:
            yield dialog
        finally:
            host.hide()
            dialog.deleteLater()
            host.deleteLater()
            self.qt_app.processEvents()

    def test_escape_keeps_each_workspace_and_draft_visible(self):
        for workspace in WORKSPACE_DIALOGS:
            with self.subTest(dialog=workspace[1]), self._workspace(*workspace) as dialog:
                editor = QtWidgets.QLineEdit("Unsent input", dialog)
                editor.show()
                rejected = QSignalSpy(dialog.rejected)

                for target in (editor, dialog):
                    QTest.keyClick(target, QtCore.Qt.Key.Key_Escape)
                    QTest.keyClick(target, QtCore.Qt.Key.Key_Escape)

                    self.assertTrue(dialog.isVisible())
                    self.assertEqual("Unsent input", editor.text())
                    self.assertEqual(0, len(rejected))

    def test_enter_still_activates_default_button(self):
        for workspace in WORKSPACE_DIALOGS:
            with self.subTest(dialog=workspace[1]), self._workspace(*workspace) as dialog:
                editor = QtWidgets.QLineEdit(dialog)
                for candidate in dialog.findChildren(QtWidgets.QPushButton):
                    candidate.setAutoDefault(False)
                    candidate.setDefault(False)
                button = QtWidgets.QPushButton("Run", dialog)
                clicked = QSignalSpy(button.clicked)
                editor.show()
                button.show()
                editor.setFocus()
                self.qt_app.processEvents()
                button.setDefault(True)

                QTest.keyClick(editor, QtCore.Qt.Key.Key_Return)

                self.assertEqual(1, len(clicked))

    def test_escape_still_closes_child_dialog(self):
        for workspace in WORKSPACE_DIALOGS:
            with self.subTest(dialog=workspace[1]), self._workspace(*workspace) as dialog:
                child = QtWidgets.QDialog(dialog)
                editor = QtWidgets.QLineEdit(child)
                rejected = QSignalSpy(child.rejected)
                child.show()

                QTest.keyClick(editor, QtCore.Qt.Key.Key_Escape)

                self.assertFalse(child.isVisible())
                self.assertEqual(1, len(rejected))
                self.assertTrue(dialog.isVisible())

    def test_escape_still_closes_combo_popup(self):
        for workspace in WORKSPACE_DIALOGS:
            with self.subTest(dialog=workspace[1]), self._workspace(*workspace) as dialog:
                combo = QtWidgets.QComboBox(dialog)
                combo.addItems(["First", "Second"])
                combo.show()
                combo.showPopup()
                self.assertTrue(combo.view().isVisible())

                QTest.keyClick(combo.view(), QtCore.Qt.Key.Key_Escape)

                self.assertFalse(combo.view().isVisible())
                self.assertEqual("First", combo.currentText())
                self.assertTrue(dialog.isVisible())

    def test_escape_still_cancels_table_edit(self):
        for workspace in WORKSPACE_DIALOGS:
            with self.subTest(dialog=workspace[1]), self._workspace(*workspace) as dialog:
                table = QtWidgets.QTableWidget(1, 1, dialog)
                item = QtWidgets.QTableWidgetItem("Original value")
                table.setItem(0, 0, item)
                table.show()
                table.editItem(item)
                editor = table.findChild(QtWidgets.QLineEdit)
                self.assertIsNotNone(editor)
                editor.setText("Uncommitted edit")

                QTest.keyClick(editor, QtCore.Qt.Key.Key_Escape)
                self.qt_app.processEvents()

                self.assertEqual("Original value", item.text())
                self.assertNotEqual(QtWidgets.QAbstractItemView.State.EditingState, table.state())
                self.assertTrue(dialog.isVisible())

    def test_survey_cancel_button_still_rejects(self):
        with self._workspace(*WORKSPACE_DIALOGS[2]) as dialog:
            rejected = QSignalSpy(dialog.rejected)
            cancel_button = dialog.ui.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel)

            QTest.mouseClick(cancel_button, QtCore.Qt.MouseButton.LeftButton)

            self.assertEqual(1, len(rejected))
            self.assertFalse(dialog.isVisible())

    def test_survey_ok_button_still_imports_and_accepts(self):
        with self._workspace(*WORKSPACE_DIALOGS[2]) as dialog:
            dialog.success = True
            dialog.fields = ["Name"]
            dialog.data = [["Participant"]]
            accepted = QSignalSpy(dialog.accepted)
            ok_button = dialog.ui.buttonBox.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)

            with patch.object(dialog, "insert_data") as insert_data:
                QTest.mouseClick(ok_button, QtCore.Qt.MouseButton.LeftButton)

            insert_data.assert_called_once_with()
            self.assertEqual(1, len(accepted))
            self.assertFalse(dialog.isVisible())
