from functools import partial
import os
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtTest import QTest

from qualcoder.__main__ import MainWindow
from qualcoder.main_tab_rail import MainTabRail
from qualcoder.recent_projects_delegate import PATH_ROLE


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

    def add_project_contents(self) -> None:
        """Add real summary tiles, text links and menu actions to the navigation fixture."""

        self.manage_page = QtWidgets.QWidget()
        manage_layout = QtWidgets.QVBoxLayout(self.manage_page)
        manage_layout.addWidget(QtWidgets.QPlainTextEdit(self.manage_page))
        self.tabs.addTab(self.manage_page, "Manage")
        frame = QtWidgets.QFrame(self.project_page)
        self.project_page.layout().addWidget(frame)
        summary_layout = QtWidgets.QVBoxLayout(frame)
        heading = QtWidgets.QLabel("Project contents", frame)
        summary_layout.addWidget(heading)
        grid = QtWidgets.QGridLayout()
        summary_layout.addLayout(grid)
        files_label = QtWidgets.QLabel(frame)
        warning_label = QtWidgets.QLabel(frame)
        for link_label in (files_label, warning_label):
            link_label.setTextFormat(QtCore.Qt.TextFormat.RichText)
            link_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.LinksAccessibleByMouse |
                                              QtCore.Qt.TextInteractionFlag.LinksAccessibleByKeyboard)
            summary_layout.addWidget(link_label)
        files_label.linkActivated.connect(self.window.open_coding_for_file_type)
        warning_label.linkActivated.connect(self.window.project_summary_warning_link)
        self.window.ui.frame_project_summary = frame
        self.window.ui.label_project_summary = heading
        self.window.ui.gridLayout_project_summary = grid
        self.window.ui.label_project_summary_files = files_label
        self.window.ui.label_project_summary_warning = warning_label
        self.summary_handlers = {}
        for action_name in ("actionManage_files", "actionManage_cases", "actionManage_journals",
                            "actionManage_bad_links_to_files", "actionCodes", "actionCode_pdf",
                            "actionCode_image", "actionCode_audio_video"):
            action = QtGui.QAction(self.window)
            if action_name == "actionManage_journals":
                handler = MagicMock(side_effect=lambda checked=False: self.window.journals())
            elif action_name.startswith("actionManage_"):
                handler = MagicMock(side_effect=lambda checked=False: self.tabs.setCurrentWidget(self.manage_page))
            else:
                handler = MagicMock(side_effect=lambda checked=False: self.tabs.setCurrentWidget(self.coding_page))
            action.triggered.connect(handler)
            setattr(self.window.ui, action_name, action)
            self.summary_handlers[action_name] = handler
        with patch("qualcoder.__main__._", side_effect=lambda text: text, create=True):
            self.window.build_project_summary_tiles()
        self.window.resize(900, 700)
        self.qt_app.processEvents()

    def assert_summary_outlines_cleared(self) -> None:
        self.assert_activity_outlines_cleared()
        self.assertFalse(any(entry["tile"].hasFocus() for entry in self.window.project_summary_tiles.values()))
        self.assertFalse(self.window.ui.label_project_summary_files.hasFocus())
        self.assertFalse(self.window.ui.label_project_summary_warning.hasFocus())

    def activate_summary_text_link(self, label: QtWidgets.QLabel, link: str, caption: str, activation: str) -> None:
        """Activate a real QLabel anchor using the mouse or Return key."""

        label.setText(f'<a href="{link}">{caption}</a>')
        self.qt_app.processEvents()
        if activation == "keyboard":
            label.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
            QTest.keyClick(label, QtCore.Qt.Key.Key_Tab)
            self.assertTrue(label.hasFocus())
            QTest.keyClick(label, QtCore.Qt.Key.Key_Return)
        else:
            self.tabs.tabBar().setFocus(QtCore.Qt.FocusReason.TabFocusReason)
            position = QtCore.QPoint(label.contentsRect().left() + label.fontMetrics().horizontalAdvance(caption) // 2,
                                    label.contentsRect().center().y())
            QTest.mouseClick(label, QtCore.Qt.MouseButton.LeftButton, pos=position)
        self.qt_app.processEvents()

    def add_recent_projects(self) -> None:
        """Add the real recent-projects selection and refresh handlers to the fixture."""

        heading = QtWidgets.QLabel("Recent projects", self.project_page)
        combo = QtWidgets.QComboBox(self.project_page)
        heading.setBuddy(combo)
        self.project_page.layout().insertWidget(0, heading)
        self.project_page.layout().insertWidget(1, combo)
        self.window.ui.label_recent_projects = heading
        self.window.ui.comboBox_recent_projects = combo
        self.window.app.project_path = "C:/projects/current.qda"
        self.window.recent_projects = [
            "2026-10-19_10:00:00|C:/projects/current.qda",
            "2026-10-18_10:00:00|C:/projects/other.qda",
        ]
        self.window.request_project_summary_update = MagicMock()
        self.window.open_project = MagicMock()
        combo.view()  # Production creates the popup view when installing its custom delegate.
        combo.installEventFilter(self.window)
        combo.activated.connect(self.window.open_recent_project_from_combo)
        translate = patch("qualcoder.__main__._", side_effect=lambda text: text, create=True)
        translate.start()
        self.addCleanup(translate.stop)
        self.window.fill_recent_projects_list()
        self.qt_app.processEvents()

    def open_recent_projects_popup(self, activation: str) -> None:
        """Open the popup by clicking or using the existing arrow-key navigation."""

        combo = self.window.ui.comboBox_recent_projects
        combo.setFocus(QtCore.Qt.FocusReason.TabFocusReason)
        if activation == "mouse":
            QTest.mouseMove(combo, combo.rect().center())
            QTest.mouseClick(combo, QtCore.Qt.MouseButton.LeftButton, pos=combo.rect().center())
        else:
            QTest.keyClick(combo, QtCore.Qt.Key.Key_Down)
        self.qt_app.processEvents()
        self.assertTrue(combo.view().isVisible())

    def choose_recent_project(self, index: int, activation: str) -> None:
        """Choose a real popup entry with a mouse click or keyboard confirmation."""

        self.open_recent_projects_popup(activation)
        view = self.window.ui.comboBox_recent_projects.view()
        if activation == "mouse":
            position = view.visualRect(view.model().index(index, 0)).center()
            QTest.mouseMove(view.viewport(), position)
            self.qt_app.processEvents()
            QTest.mouseClick(view.viewport(), QtCore.Qt.MouseButton.LeftButton, pos=position)
        else:
            difference = index - view.currentIndex().row()
            navigation_key = QtCore.Qt.Key.Key_Down if difference > 0 else QtCore.Qt.Key.Key_Up
            for step in range(abs(difference)):
                QTest.keyClick(view, navigation_key)
            QTest.keyClick(view, QtCore.Qt.Key.Key_Return)
        self.qt_app.processEvents()

    def assert_recent_projects_outline_cleared(self) -> None:
        combo = self.window.ui.comboBox_recent_projects
        self.assertFalse(combo.hasFocus())
        self.assertFalse(combo.view().isVisible())
        self.assert_activity_outlines_cleared()

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

    def test_project_contents_tiles_clear_outlines_after_activation_and_return(self):
        self.add_project_contents()
        for tile_key, destination, action_name in (
            ("files", self.manage_page, "actionManage_files"),
            ("cases", self.manage_page, "actionManage_cases"),
            ("journals", self.journal_dialog, "actionManage_journals"),
        ):
            for activation in ("mouse", QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter, QtCore.Qt.Key.Key_Space):
                with self.subTest(tile=tile_key, activation=activation):
                    self.tabs.setCurrentWidget(self.project_page)
                    self.window.activateWindow()
                    tile = self.window.project_summary_tiles[tile_key]["tile"]
                    tile.setFocus(QtCore.Qt.FocusReason.TabFocusReason)
                    previous_calls = self.summary_handlers[action_name].call_count
                    if activation == "mouse":
                        self.tabs.tabBar().setFocus(QtCore.Qt.FocusReason.TabFocusReason)
                        QTest.mouseClick(tile, QtCore.Qt.MouseButton.LeftButton, pos=tile.rect().center())
                    else:
                        QTest.keyClick(tile, activation)
                    if destination is self.journal_dialog:
                        self.journal_dialog.activateWindow()
                    self.qt_app.processEvents()
                    self.assertEqual(previous_calls + 1, self.summary_handlers[action_name].call_count)
                    self.assert_summary_outlines_cleared()
                    self.assert_focus_in(destination)

                    self.journal_dialog.hide()
                    self.tabs.setCurrentWidget(self.project_page)
                    self.window.activateWindow()
                    self.qt_app.processEvents()
                    self.assert_summary_outlines_cleared()

        codes_tile = self.window.project_summary_tiles["codes"]["tile"]
        self.assertNotIn(codes_tile, self.window.project_cards)

    def test_ai_chat_tile_opens_tab_or_focuses_sidebar_even_when_ai_is_disabled(self):
        self.add_project_contents()
        self.window.app.settings = {"ai_enable": "False"}
        self.window.ui.tab_ai_agent = self.ai_page
        self.window.ui.actionAI_Agent = QtGui.QAction(self.window)
        self.window.ui.actionAI_Agent.setEnabled(False)
        tile = self.window.project_summary_tiles["ai_chats"]["tile"]
        tile.show()

        def configure_sidebar(enabled: bool, persist: bool = True) -> None:
            current_layout = self.chat_view.parentWidget().layout()
            current_layout.removeWidget(self.chat_view)
            target_layout = self.sidebar_layout if enabled else self.ai_page.layout()
            target_layout.addWidget(self.chat_view)
            self.sidebar.setVisible(enabled)
            self.tabs.setTabVisible(self.tabs.indexOf(self.ai_page), not enabled)
            self.chat_view.show()

        self.window.set_ai_chat_sidebar_mode = MagicMock(side_effect=configure_sidebar)
        for sidebar_enabled in (False, True):
            self.window.ai_chat_sidebar_mode = sidebar_enabled
            for activation in ("mouse", QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter, QtCore.Qt.Key.Key_Space):
                with self.subTest(sidebar=sidebar_enabled, activation=activation):
                    self.tabs.setCurrentWidget(self.project_page)
                    self.window.set_ai_chat_sidebar_mode.reset_mock()
                    tile.setFocus(QtCore.Qt.FocusReason.TabFocusReason)
                    if activation == "mouse":
                        self.tabs.tabBar().setFocus(QtCore.Qt.FocusReason.TabFocusReason)
                        QTest.mouseClick(tile, QtCore.Qt.MouseButton.LeftButton, pos=tile.rect().center())
                    else:
                        QTest.keyClick(tile, activation)
                    self.qt_app.processEvents()

                    self.window.set_ai_chat_sidebar_mode.assert_called_once_with(sidebar_enabled, persist=False)
                    self.assertIs(self.project_page if sidebar_enabled else self.ai_page, self.tabs.currentWidget())
                    self.assert_focus_in(self.chat_view)
                    self.assert_summary_outlines_cleared()
                    self.assertFalse(self.window.ui.actionAI_Agent.isEnabled())
                    self.tabs.setCurrentWidget(self.project_page)
                    self.qt_app.processEvents()
                    self.assert_summary_outlines_cleared()

    def test_project_contents_file_type_links_clear_outlines_after_activation_and_return(self):
        self.add_project_contents()
        label = self.window.ui.label_project_summary_files
        for link, caption, action_name in (
            ("text", "Text", "actionCodes"), ("pdf", "PDF", "actionCode_pdf"),
            ("image", "Images", "actionCode_image"), ("av", "Audio/video", "actionCode_audio_video"),
        ):
            for activation in ("mouse", "keyboard"):
                with self.subTest(link=link, activation=activation):
                    self.tabs.setCurrentWidget(self.project_page)
                    previous_calls = self.summary_handlers[action_name].call_count
                    self.activate_summary_text_link(label, link, caption, activation)
                    self.assertEqual(previous_calls + 1, self.summary_handlers[action_name].call_count)
                    self.assert_summary_outlines_cleared()
                    self.assert_focus_in(self.coding_page)
                    self.tabs.setCurrentWidget(self.project_page)
                    self.qt_app.processEvents()
                    self.assert_summary_outlines_cleared()

    def test_project_contents_repair_links_clear_outlines_after_activation_and_return(self):
        self.add_project_contents()
        label = self.window.ui.label_project_summary_warning
        for link, caption, action_name in (
            ("bad_links", "Manage links", "actionManage_bad_links_to_files"),
            ("missing_files", "Manage files", "actionManage_files"),
        ):
            for activation in ("mouse", "keyboard"):
                with self.subTest(link=link, activation=activation):
                    self.tabs.setCurrentWidget(self.project_page)
                    previous_calls = self.summary_handlers[action_name].call_count
                    self.activate_summary_text_link(label, link, caption, activation)
                    self.assertEqual(previous_calls + 1, self.summary_handlers[action_name].call_count)
                    self.assert_summary_outlines_cleared()
                    self.assert_focus_in(self.manage_page)
                    self.tabs.setCurrentWidget(self.project_page)
                    self.qt_app.processEvents()
                    self.assert_summary_outlines_cleared()

    def test_new_and_open_project_panels_clear_outlines_after_accepting_or_cancelling(self):
        self.add_project_contents()
        heading = QtWidgets.QLabel("Project", self.project_page)
        self.project_page.layout().insertWidget(0, heading)
        self.window.ui.label_project_title = heading
        panels = {}
        for position, action_name in enumerate(("actionCreate_New_Project", "actionOpen_Project"), start=1):
            panel = QtWidgets.QFrame(self.project_page)
            panel.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
            panel.setFixedHeight(60)
            panel.installEventFilter(self.window)
            self.project_page.layout().insertWidget(position, panel)
            panels[action_name] = panel
        self.qt_app.processEvents()
        activations = []

        for action_name, panel in panels.items():
            for dialog_result in (QtWidgets.QDialog.DialogCode.Accepted, QtWidgets.QDialog.DialogCode.Rejected):
                for activation in ("mouse", QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter, QtCore.Qt.Key.Key_Space):
                    with self.subTest(action=action_name, result=dialog_result, activation=activation):
                        def open_dialog(checked: bool = False) -> None:
                            chooser = QtWidgets.QDialog(self.window)
                            chooser_layout = QtWidgets.QVBoxLayout(chooser)
                            chooser_layout.addWidget(QtWidgets.QLineEdit(chooser))
                            QtCore.QTimer.singleShot(10, lambda: chooser.done(dialog_result))
                            activations.append(chooser.exec())
                            chooser.deleteLater()

                        action = QtGui.QAction(self.window)
                        action.triggered.connect(open_dialog)
                        setattr(self.window.ui, action_name, action)
                        self.window.project_cards[panel] = partial(
                            self.window.activate_project_panel_action, action, heading,
                        )
                        previous_calls = len(activations)
                        panel.setFocus(QtCore.Qt.FocusReason.TabFocusReason)
                        self.assertTrue(panel.hasFocus())
                        if activation == "mouse":
                            self.tabs.tabBar().setFocus(QtCore.Qt.FocusReason.TabFocusReason)
                            QTest.mouseClick(panel, QtCore.Qt.MouseButton.LeftButton, pos=panel.rect().center())
                        else:
                            QTest.keyClick(panel, activation)
                        self.window.activateWindow()
                        self.qt_app.processEvents()
                        self.assertEqual(previous_calls + 1, len(activations))
                        self.assertEqual(dialog_result, activations[-1])
                        self.assertFalse(any(card.hasFocus() for card in panels.values()))
                        self.assert_summary_outlines_cleared()
                        self.assert_focus_in(self.project_page)

                        self.tabs.setCurrentWidget(self.coding_page)
                        self.tabs.setCurrentWidget(self.project_page)
                        self.qt_app.processEvents()
                        self.assertFalse(any(card.hasFocus() for card in panels.values()))
                        self.assert_summary_outlines_cleared()
                        QTest.keyClick(self.qt_app.focusWidget(), QtCore.Qt.Key.Key_Tab)
                        self.assertTrue(any(card.hasFocus() for card in panels.values()))

    def test_recent_projects_clear_outline_after_opening_or_cancelling_a_project(self):
        self.add_recent_projects()
        combo = self.window.ui.comboBox_recent_projects
        selected_entry = self.window.recent_projects[1]
        for dialog_result in (QtWidgets.QDialog.DialogCode.Accepted, QtWidgets.QDialog.DialogCode.Rejected):
            for activation in ("mouse", "keyboard"):
                with self.subTest(result=dialog_result, activation=activation):
                    self.window.app.project_path = "C:/projects/current.qda"
                    self.window.fill_recent_projects_list()
                    self.window.open_project.reset_mock()

                    def open_selected_project(entry: str) -> None:
                        chooser = QtWidgets.QDialog(self.window)
                        chooser_layout = QtWidgets.QVBoxLayout(chooser)
                        chooser_layout.addWidget(QtWidgets.QLineEdit(chooser))
                        QtCore.QTimer.singleShot(10, lambda: chooser.done(dialog_result))
                        if chooser.exec() == QtWidgets.QDialog.DialogCode.Accepted:
                            self.window.app.project_path = entry.split("|", maxsplit=1)[-1]
                        chooser.deleteLater()

                    self.window.open_project.side_effect = open_selected_project
                    self.choose_recent_project(1, activation)
                    self.window.activateWindow()
                    self.qt_app.processEvents()
                    self.window.open_project.assert_called_once_with(selected_entry)
                    self.assert_recent_projects_outline_cleared()
                    expected_path = ("C:/projects/other.qda" if dialog_result == QtWidgets.QDialog.DialogCode.Accepted
                                     else "C:/projects/current.qda")
                    self.assertEqual(expected_path, self.window.app.project_path)
                    self.assertEqual(expected_path, combo.itemData(combo.currentIndex(), PATH_ROLE))
                    self.tabs.setCurrentWidget(self.coding_page)
                    self.tabs.setCurrentWidget(self.project_page)
                    self.qt_app.processEvents()
                    self.assert_recent_projects_outline_cleared()

    def test_reselecting_the_current_project_clears_outline_without_reopening_it(self):
        self.add_recent_projects()
        for activation in ("mouse", "keyboard"):
            with self.subTest(activation=activation):
                self.choose_recent_project(0, activation)
                self.window.open_project.assert_not_called()
                self.assert_recent_projects_outline_cleared()
                combo = self.window.ui.comboBox_recent_projects
                self.assertEqual("C:/projects/current.qda", combo.itemData(combo.currentIndex(), PATH_ROLE))

    def test_dismissing_recent_projects_popup_clears_outline_and_preserves_keyboard_navigation(self):
        self.add_recent_projects()
        combo = self.window.ui.comboBox_recent_projects
        for activation in ("mouse", "keyboard"):
            with self.subTest(activation=activation):
                self.open_recent_projects_popup(activation)
                QTest.keyClick(combo.view(), QtCore.Qt.Key.Key_Escape)
                self.qt_app.processEvents()
                self.assert_recent_projects_outline_cleared()
                self.window.open_project.assert_not_called()
                self.assertEqual("C:/projects/current.qda", combo.itemData(combo.currentIndex(), PATH_ROLE))
                QTest.keyClick(self.qt_app.focusWidget(), QtCore.Qt.Key.Key_Tab)
                self.assertTrue(combo.hasFocus())
                QTest.keyClick(combo, QtCore.Qt.Key.Key_Down)
                self.qt_app.processEvents()
                self.assertTrue(combo.view().isVisible())
                QTest.keyClick(combo.view(), QtCore.Qt.Key.Key_Escape)
                self.qt_app.processEvents()

    def test_closing_recent_projects_popup_does_not_steal_focus_from_another_control(self):
        self.add_recent_projects()
        combo = self.window.ui.comboBox_recent_projects
        self.open_recent_projects_popup("keyboard")
        combo.hidePopup()
        heading = self.window.ui.label_recent_activity
        heading.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
        self.qt_app.processEvents()

        self.assertTrue(heading.hasFocus())
        self.assert_recent_projects_outline_cleared()
        self.window.open_project.assert_not_called()
