import os
from types import SimpleNamespace
from unittest import TestCase

from PyQt6 import QtGui, QtWidgets

from qualcoder.code_text import DialogCodeText
from qualcoder.code_text_coding_margin import CodingMargin
from qualcoder.color_selector import colors


class TestCodeTextMarkerColors(TestCase):
    """Check marker opacity and contrast with native and stylesheet colors."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_constant_opacity_and_contrast_with_effective_editor_colors(self):
        original_palette = self.qt_app.palette()
        original_stylesheet = self.qt_app.styleSheet()
        try:
            for dark_mode in (True, False):
                base = QtGui.QColor("#2a2a2a" if dark_mode else "#fcfcfc")
                text = QtGui.QColor("#eeeeee" if dark_mode else "#202020")
                for source in ("native", "application", "parent", "editor"):
                    with self.subTest(dark_mode=dark_mode, source=source):
                        self.qt_app.setStyleSheet("")
                        palette = QtGui.QPalette(original_palette)
                        # Stylesheets must override an opposing system theme.
                        palette.setColor(QtGui.QPalette.ColorRole.Base,
                                         base if source == "native" else text)
                        palette.setColor(QtGui.QPalette.ColorRole.Text,
                                         text if source == "native" else base)
                        self.qt_app.setPalette(palette)
                        dialog = DialogCodeText.__new__(DialogCodeText)
                        QtWidgets.QWidget.__init__(dialog)
                        editor = QtWidgets.QPlainTextEdit(dialog)
                        dialog.ui = SimpleNamespace(plainTextEdit=editor)
                        stylesheet = (
                            "QPlainTextEdit {background-color: " + base.name()
                            + "; color: " + text.name() + ";}")
                        if source == "application":
                            self.qt_app.setStyleSheet(stylesheet)
                        elif source == "parent":
                            dialog.setStyleSheet(stylesheet)
                        elif source == "editor":
                            editor.setStyleSheet(stylesheet)
                        try:
                            # Deliberately format before the first show/polish.
                            for color in colors:
                                fmt = QtGui.QTextCharFormat()
                                dialog._set_code_marker_format(fmt, color)
                                marker = fmt.background().color()
                                self.assertAlmostEqual(
                                    marker.alphaF(), 0.3, places=4)
                                opacity = marker.alphaF()
                                blended = QtGui.QColor(*(
                                    round(opacity * first + (1 - opacity) * second)
                                    for first, second in zip(
                                        marker.getRgb()[:3], base.getRgb()[:3])))
                                self.assertGreaterEqual(CodingMargin._contrast_ratio(
                                    fmt.foreground().color(), blended), 4.5)
                        finally:
                            dialog.deleteLater()
                            self.qt_app.processEvents()
        finally:
            self.qt_app.setStyleSheet(original_stylesheet)
            self.qt_app.setPalette(original_palette)

    def test_text_color_changes_only_when_blended_contrast_is_low(self):
        dialog = DialogCodeText.__new__(DialogCodeText)
        QtWidgets.QWidget.__init__(dialog)
        editor = QtWidgets.QPlainTextEdit(dialog)
        dialog.ui = SimpleNamespace(plainTextEdit=editor)
        try:
            for base, text, marker, expected_text in (
                    ("#2a2a2a", "#eeeeee", "#B71C1C", "#eeeeee"),
                    ("#fcfcfc", "#202020", "#B71C1C", "#202020"),
                    ("#404040", "#eeeeee", "#ffffff", "#000000"),
                    ("#eeeeee", "#666666", "#000000", "#000000")):
                with self.subTest(base=base, text=text, marker=marker):
                    editor.setStyleSheet(
                        f"QPlainTextEdit {{background-color: {base}; color: {text};}}")
                    fmt = QtGui.QTextCharFormat()
                    dialog._set_code_marker_format(fmt, marker)
                    self.assertEqual(fmt.foreground().color().name(), expected_text)
        finally:
            dialog.deleteLater()
            self.qt_app.processEvents()
