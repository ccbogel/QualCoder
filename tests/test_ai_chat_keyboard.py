from unittest import TestCase
from unittest.mock import patch

from PyQt6 import QtCore, QtWidgets
from PyQt6.QtTest import QSignalSpy, QTest

from qualcoder.ai_chat import DialogAIChat
from qualcoder.GUI.ui_ai_chat import Ui_Dialog_ai_chat


class TestAiChatKeyboard(TestCase):
    """Exercise chat keyboard handling through Qt's event propagation."""

    @classmethod
    def setUpClass(cls):
        cls.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.host = QtWidgets.QWidget()
        self.chat = DialogAIChat.__new__(DialogAIChat)
        QtWidgets.QDialog.__init__(self.chat)
        self.chat.ui = Ui_Dialog_ai_chat()
        self.chat.ui.setupUi(self.chat)
        self.editor = self.chat.ui.plainTextEdit_question
        self.editor.installEventFilter(self.chat)
        self.chat._prompt_completion_popup = QtWidgets.QListWidget(self.chat)
        self.chat._prompt_completion_popup.hide()
        self.chat._prompt_inline_completion = None
        self.chat._prompt_completion_guard = False
        self.rejected = QSignalSpy(self.chat.rejected)
        splitter_patch = patch.object(self.chat, "schedule_ai_output_splitter_restore")
        splitter_patch.start()
        self.addCleanup(splitter_patch.stop)

    def tearDown(self):
        self.chat.hide()
        self.host.close()
        self.chat.deleteLater()
        self.host.deleteLater()
        self.qt_app.processEvents()

    def test_escape_keeps_chat_and_draft_visible(self):
        self.editor.setPlainText("Unsent question")
        for embedded in (False, True):
            with self.subTest(embedded=embedded):
                self.rejected = QSignalSpy(self.chat.rejected)
                if embedded:
                    layout = QtWidgets.QVBoxLayout(self.host)
                    layout.addWidget(self.chat)
                    self.host.show()
                self.chat.show()
                self.qt_app.processEvents()
                self.editor.setFocus()

                QTest.keyClick(self.editor, QtCore.Qt.Key.Key_Escape)

                self.assertTrue(self.chat.isVisible())
                self.assertEqual("Unsent question", self.editor.toPlainText())
                self.assertEqual(0, len(self.rejected))

    def test_escape_from_chat_list_keeps_chat_visible(self):
        self.chat.show()
        QTest.keyClick(self.chat.ui.treeView_chat_list, QtCore.Qt.Key.Key_Escape)

        self.assertTrue(self.chat.isVisible())
        self.assertEqual(0, len(self.rejected))

    def test_escape_dismisses_completion_and_keeps_chat_visible_when_repeated(self):
        self.chat.show()
        self.editor.setPlainText("/Test")
        self.chat._prompt_inline_completion = {"start": 3, "end": 5, "suffix": "st"}
        self.chat._prompt_completion_popup.show()

        QTest.keyClick(self.editor, QtCore.Qt.Key.Key_Escape)

        self.assertFalse(self.chat._prompt_completion_popup.isVisible())
        self.assertIsNone(self.chat._prompt_inline_completion)
        self.assertEqual("/Te", self.editor.toPlainText())
        self.assertTrue(self.chat.isVisible())

        QTest.keyClick(self.editor, QtCore.Qt.Key.Key_Escape)

        self.assertTrue(self.chat.isVisible())
        self.assertEqual("/Te", self.editor.toPlainText())
        self.assertEqual(0, len(self.rejected))
