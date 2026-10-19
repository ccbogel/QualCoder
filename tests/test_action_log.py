import os
from unittest import TestCase

from PyQt6 import QtCore, QtGui, QtWidgets

from qualcoder.GUI.ui_main import Ui_MainWindow


class TestActionLog(TestCase):
    """Check formatting when background messages arrive while reading the log."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.window = QtWidgets.QMainWindow()
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self.window)
        self.log = self.ui.textEdit
        self.log.append('<p>Project backup created: '
                        '<a href="file:///C:/backup.qda">backup.qda</a></p>')

    def tearDown(self):
        self.window.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)

    def test_ai_messages_stay_plain_when_cursor_is_in_a_link(self):
        cursor = self.log.document().find("backup.qda")
        cursor.setPosition(cursor.selectionStart() + 2)
        self.log.setTextCursor(cursor)
        self.log.append('<p><b>Project Opened:</b><br />project.qda</p>')
        messages = ("AI: Starting up...", "AI: Components loaded.", "AI: Checking for new documents",
                    "AI: Checked all documents, memory is up to date.")
        for message in messages:
            self.log.append(message)

        for message in messages:
            with self.subTest(message=message):
                character_format = self.log.document().find(message).charFormat()
                self.assertFalse(character_format.isAnchor())
                self.assertEqual("", character_format.anchorHref())
                self.assertFalse(character_format.fontUnderline())
                self.assertEqual(QtGui.QFont.Weight.Normal, character_format.fontWeight())
        self.assertEqual("file:///C:/backup.qda",
                         self.log.document().find("backup.qda").charFormat().anchorHref())

    def test_new_entries_preserve_selected_text(self):
        cursor = self.log.document().find("backup.qda")
        self.log.setTextCursor(cursor)
        self.log.append("AI: Starting up...")
        self.log.append("AI: Components loaded.")

        self.assertEqual("backup.qda", self.log.textCursor().selectedText())
        self.assertEqual(cursor.selectionStart(), self.log.textCursor().selectionStart())
        self.assertFalse(self.log.document().find("AI: Starting up...").charFormat().isAnchor())

    def test_explicit_links_and_headings_keep_their_formatting(self):
        self.log.setTextCursor(self.log.document().find("backup.qda"))
        self.log.append('<p><b>QualCoder 4.1</b> '
                        '<a href="qualcoder://action/about">About</a></p>')

        self.assertEqual("qualcoder://action/about",
                         self.log.document().find("About").charFormat().anchorHref())
        self.assertEqual(QtGui.QFont.Weight.Bold,
                         self.log.document().find("QualCoder 4.1").charFormat().fontWeight())
