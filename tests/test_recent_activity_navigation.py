import os
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtTest import QTest

from qualcoder.__main__ import MainWindow
from qualcoder.main_tab_rail import MainTabRail


class TestRecentActivityNavigation(TestCase):
    """Exercise focus across real activity rows, tab navigation, sidebars and dialogs."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.window = MainWindow.__new__(MainWindow)
        QtWidgets.QMainWindow.__init__(self.window)
        self.window.app = SimpleNamespace(conn=object())
        self.window.project_cards = {}
        container = QtWidgets.QWidget(self.window)
        self.window.setCentralWidget(container)
        outer_layout = QtWidgets.QHBoxLayout(container)
        self.tabs = QtWidgets.QTabWidget(container)
        outer_layout.addWidget(self.tabs)
        self.sidebar = QtWidgets.QWidget(container)
        self.sidebar_layout = QtWidgets.QVBoxLayout(self.sidebar)
        outer_layout.addWidget(self.sidebar)
        self.sidebar.hide()
        self.project_page = QtWidgets.QWidget()
        project_layout = QtWidgets.QVBoxLayout(self.project_page)
        activity_frame = QtWidgets.QFrame(self.project_page)
        project_layout.addWidget(activity_frame)
        activity_layout = QtWidgets.QVBoxLayout(activity_frame)
        heading = QtWidgets.QLabel("Recent activity", activity_frame)
        activity_layout.addWidget(heading)
        self.coding_page = QtWidgets.QWidget()
        coding_layout = QtWidgets.QVBoxLayout(self.coding_page)
        self.code_editor = QtWidgets.QPlainTextEdit(self.coding_page)
        coding_layout.addWidget(self.code_editor)
        self.ai_page = QtWidgets.QWidget()
        ai_layout = QtWidgets.QVBoxLayout(self.ai_page)
        self.chat_view = QtWidgets.QWidget(self.ai_page)
        chat_layout = QtWidgets.QVBoxLayout(self.chat_view)
        self.chat_editor = QtWidgets.QPlainTextEdit(self.chat_view)
        chat_layout.addWidget(self.chat_editor)
        ai_layout.addWidget(self.chat_view)
        self.tabs.addTab(self.project_page, "Project")
        self.tabs.addTab(self.coding_page, "Coding")
        self.tabs.addTab(self.ai_page, "AI Agent")
        self.rail = MainTabRail(self.tabs, lambda: "#009cff")
        self.rail.set_enabled(True)
        self.window.ui = SimpleNamespace(
            tabWidget=self.tabs, frame_recent_activity=activity_frame,
            label_recent_activity=heading, verticalLayout_recent_activity=activity_layout,
        )
        self.window.ai_chat_window = self.chat_view
        self.window.text_coding = MagicMock(side_effect=lambda **kwargs: self.tabs.setCurrentWidget(self.coding_page))
        self.window.open_ai_chat = MagicMock(side_effect=lambda chat_id: self.tabs.setCurrentWidget(self.ai_page))
        self.journal_dialog = QtWidgets.QDialog(self.window)
        journal_layout = QtWidgets.QVBoxLayout(self.journal_dialog)
        journal_layout.addWidget(QtWidgets.QPlainTextEdit(self.journal_dialog))
        self.window.journal_display = self.journal_dialog
        self.window.journals = MagicMock(side_effect=self.journal_dialog.show)
        self.window.select_journal = MagicMock()
        self.window.build_recent_activity_rows()
        self.window.recent_activity_targets = {
            "coded": ("text", 1, 10, 20, "2026-10-19 10:00:00"), "journal": 3, "ai_chat": 4,
        }
        for activity_key in self.window.recent_activity_targets:
            self.window.recent_activity_rows[activity_key]["row"].show()
        self.window.resize(700, 400)
        self.window.show()
        self.window.activateWindow()
        self.qt_app.processEvents()

    def tearDown(self):
        self.journal_dialog.hide()
        self.window.hide()
        self.window.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)

    def assert_activity_outlines_cleared(self) -> None:
        self.assertFalse(any(entry["row"].hasFocus() for entry in self.window.recent_activity_rows.values()))
        self.assertFalse(self.tabs.tabBar().hasFocus())
        self.assertFalse(self.rail.keyboard_focus)

    def assert_focus_in(self, destination: QtWidgets.QWidget) -> None:
        focused_widget = self.qt_app.focusWidget()
        self.assertIsNotNone(focused_widget)
        self.assertTrue(focused_widget is destination or destination.isAncestorOf(focused_widget))

    def test_mouse_and_keyboard_activation_clear_outlines_after_opening_and_returning(self):
        for activity_key, destination in (("coded", self.coding_page), ("ai_chat", self.chat_view)):
            for activation in ("mouse", QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter, QtCore.Qt.Key.Key_Space):
                with self.subTest(activity=activity_key, activation=activation):
                    self.tabs.setCurrentWidget(self.project_page)
                    row = self.window.recent_activity_rows[activity_key]["row"]
                    row.setFocus(QtCore.Qt.FocusReason.TabFocusReason)
                    if activation == "mouse":
                        self.tabs.tabBar().setFocus(QtCore.Qt.FocusReason.TabFocusReason)
                        self.assertTrue(self.rail.keyboard_focus)
                        QTest.mouseClick(row, QtCore.Qt.MouseButton.LeftButton, pos=row.rect().center())
                    else:
                        self.assertTrue(row.hasFocus())
                        QTest.keyClick(row, activation)
                    self.qt_app.processEvents()
                    self.assert_activity_outlines_cleared()
                    self.assert_focus_in(destination)

                    self.tabs.setCurrentWidget(self.project_page)
                    self.qt_app.processEvents()
                    self.assert_activity_outlines_cleared()
                    QTest.keyClick(self.qt_app.focusWidget(), QtCore.Qt.Key.Key_Tab)
                    self.qt_app.processEvents()
                    self.assertTrue(any(entry["row"].hasFocus() for entry in self.window.recent_activity_rows.values()))

        self.window.text_coding.assert_called_with(doc_id=1, doc_sel_start=10, doc_sel_end=20)
        self.window.open_ai_chat.assert_called_with(4)

    def test_sidebar_activation_moves_focus_into_chat_without_highlighting_a_row(self):
        def show_sidebar(chat_id: int) -> None:
            self.assertEqual(4, chat_id)
            self.ai_page.layout().removeWidget(self.chat_view)
            self.sidebar_layout.addWidget(self.chat_view)
            self.sidebar.show()
            self.chat_view.show()

        self.window.open_ai_chat.side_effect = show_sidebar
        row = self.window.recent_activity_rows["ai_chat"]["row"]
        row.setFocus(QtCore.Qt.FocusReason.TabFocusReason)
        QTest.keyClick(row, QtCore.Qt.Key.Key_Return)
        self.qt_app.processEvents()

        self.assertIs(self.project_page, self.tabs.currentWidget())
        self.assert_activity_outlines_cleared()
        self.assert_focus_in(self.chat_view)

    def test_modeless_journal_gets_focus_and_leaves_no_highlight_on_return(self):
        row = self.window.recent_activity_rows["journal"]["row"]
        row.setFocus(QtCore.Qt.FocusReason.TabFocusReason)
        QTest.keyClick(row, QtCore.Qt.Key.Key_Return)
        self.journal_dialog.activateWindow()
        self.qt_app.processEvents()

        self.window.select_journal.assert_called_once_with(3)
        self.assert_activity_outlines_cleared()
        self.assert_focus_in(self.journal_dialog)
        self.journal_dialog.hide()
        self.window.activateWindow()
        self.qt_app.processEvents()
        self.assert_activity_outlines_cleared()

    def test_standalone_keyboard_navigation_on_the_rail_keeps_its_indicator(self):
        row = self.window.recent_activity_rows["coded"]["row"]
        row.setFocus(QtCore.Qt.FocusReason.TabFocusReason)
        self.tabs.tabBar().setFocus(QtCore.Qt.FocusReason.TabFocusReason)
        self.qt_app.processEvents()

        self.assertTrue(self.tabs.tabBar().hasFocus())
        self.assertTrue(self.rail.keyboard_focus)
