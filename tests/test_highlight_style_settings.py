"""Regression tests for highlight styles shared by coding views and Settings."""

from collections.abc import Iterator
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from PyQt6 import QtCore, QtGui, QtWidgets, sip

from qualcoder.app import App
from qualcoder.code_pdf import DialogCodePdf, PdfPageItem
from qualcoder.code_text import DialogCodeText
from qualcoder.settings import DialogSettings


class TestHighlightStyleSettings(TestCase):
    styles = ('marker', 'marker light', 'underline')

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        cls.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.translation = patch('builtins._', side_effect=lambda text: text, create=True)
        self.translation.start()
        self.addCleanup(self.translation.stop)
        # Repeated headless dialogs need no QtAwesome icon engines.
        icons = patch('qualcoder.settings.qta.icon', return_value=QtGui.QIcon())
        icons.start()
        self.addCleanup(icons.stop)
        self.application = App.__new__(App)
        self.application.confighome = temporary_directory.name
        self.application.configpath = str(Path(temporary_directory.name) / 'config.ini')
        self.application.conn = None
        self.application.ai_models = []
        self.application.settings = self.application.default_settings
        self.application.settings.update({
            'language': 'en',
            'report_text_context_style': 'Bold',
            'report_text_context_characters': 100,
        })
        self.application.settings, _ = self.application.check_and_add_additional_settings(
            self.application.settings, [])

    def coding_view(self) -> SimpleNamespace:
        """Create a minimal text view using the production style setter."""
        view = SimpleNamespace(
            app=self.application,
            highlight_style='marker',
            file_=None,
        )
        view._set_highlight_style = DialogCodeText._set_highlight_style.__get__(view)
        return view

    @contextmanager
    def settings_dialog(self) -> Iterator[DialogSettings]:
        """Close each settings dialog before opening the next one."""
        dialog = DialogSettings(self.application)
        try:
            yield dialog
        finally:
            sip.delete(dialog)

    def test_context_menu_selection_survives_settings_accept_and_config_reload(self):
        view = self.coding_view()
        for style in self.styles:
            with self.subTest(style=style):
                view._set_highlight_style(style)
                self.assertEqual(self.application.settings['codetext_highlight_style'], style)
                with self.settings_dialog() as dialog:
                    self.assertEqual(dialog.ui.comboBox_code_highlight_style.currentText(), style)
                    dialog.accept()
                    self.assertEqual(dialog.result(), QtWidgets.QDialog.DialogCode.Accepted)
                loaded_settings, _ = self.application._load_config_ini()
                self.assertEqual(loaded_settings['codetext_highlight_style'], style)
                self.application.settings = loaded_settings
                view.highlight_style = 'unset'
                DialogCodeText.apply_highlight_style_setting(view)
                self.assertEqual(view.highlight_style, style)

    def test_every_settings_choice_persists_independently_of_translated_labels(self):
        for index, style in enumerate(self.styles):
            with self.subTest(style=style):
                with self.settings_dialog() as dialog:
                    combo = dialog.ui.comboBox_code_highlight_style
                    self.assertEqual(combo.count(), len(self.styles))
                    for item_index in range(combo.count()):
                        combo.setItemText(item_index, f'Translated label {item_index}')
                    combo.setCurrentIndex(index)
                    dialog.accept()
                    self.assertEqual(dialog.result(), QtWidgets.QDialog.DialogCode.Accepted)
                self.assertEqual(self.application.settings['codetext_highlight_style'], style)
                loaded_settings, _ = self.application._load_config_ini()
                self.assertEqual(loaded_settings['codetext_highlight_style'], style)

    def test_pdf_applies_shared_marker_light_preference(self):
        self.application.settings['codetext_highlight_style'] = 'marker light'
        view = SimpleNamespace(
            app=self.application,
            highlight_style='underline',
            rebuild_marks=Mock(),
        )
        view._set_highlight_style = DialogCodePdf._set_highlight_style.__get__(view)
        DialogCodePdf.apply_highlight_style_setting(view)
        self.assertEqual(view.highlight_style, 'marker light')
        view.rebuild_marks.assert_called_once_with()
        self.assertEqual(self.application.settings['codetext_highlight_style'], 'marker light')

    def test_pdf_user_selections_update_the_shared_preference(self):
        view = SimpleNamespace(
            app=self.application,
            highlight_style='marker',
            rebuild_marks=Mock(),
        )
        for style in ('marker light', 'underline', 'marker'):
            with self.subTest(style=style):
                DialogCodePdf._set_highlight_style(view, style)
                self.assertEqual(view.highlight_style, style)
                self.assertEqual(self.application.settings['codetext_highlight_style'], style)
                self.application.write_config_ini(self.application.settings, self.application.ai_models)
                loaded_settings, _ = self.application._load_config_ini()
                self.assertEqual(loaded_settings['codetext_highlight_style'], style)

    def test_highlight_context_menus_show_all_styles_and_check_current_choice(self):
        source_widget = SimpleNamespace(mapToGlobal=lambda position: position)
        view = SimpleNamespace(
            app=self.application,
            file_=None,
            show_margin_stripes=True,
            margin_side='left',
            selection=None,
            undo_deleted_codes=[],
            undo_deleted_areas=[],
            rebuild_marks=Mock(),
            view=SimpleNamespace(
                mapToScene=lambda position: position,
                page_at=lambda position: None,
                single_page_mode=False,
            ),
        )
        menu_methods = (
            (DialogCodeText.coding_margin_context_menu, DialogCodeText._set_highlight_style),
            (DialogCodePdf.view_menu, DialogCodePdf._set_highlight_style),
            (DialogCodePdf.coding_margin_context_menu, DialogCodePdf._set_highlight_style),
        )
        for menu_method, set_highlight_style in menu_methods:
            view._set_highlight_style = set_highlight_style.__get__(view)
            for current_style in self.styles:
                for selected_style in self.styles:
                    with self.subTest(menu=menu_method.__name__, current=current_style, selected=selected_style):
                        view.highlight_style = current_style
                        self.application.settings['codetext_highlight_style'] = current_style

                        def select_style(menu: QtWidgets.QMenu, *args):
                            style_menu = next(action.menu() for action in menu.actions()
                                              if action.text() == 'Highlight style')
                            actions = style_menu.actions()
                            self.assertEqual([action.text().lower() for action in actions], list(self.styles))
                            self.assertTrue(all(action.isCheckable() for action in actions))
                            self.assertEqual([action.text().lower() for action in actions if action.isChecked()],
                                             [current_style])
                            selected_action = next(action for action in actions
                                                   if action.text().lower() == selected_style)
                            selected_action.trigger()
                            self.assertEqual([action.text().lower() for action in actions if action.isChecked()],
                                             [selected_style])
                            return selected_action

                        with patch.object(QtWidgets.QMenu, 'exec', select_style):
                            if menu_method == DialogCodePdf.view_menu:
                                menu_method(view, QtCore.QPoint(), QtCore.QPoint())
                            else:
                                menu_method(view, QtCore.QPoint(), source_widget)
                        self.assertEqual(view.highlight_style, selected_style)
                        self.assertEqual(self.application.settings['codetext_highlight_style'], selected_style)

    def test_pdf_marker_light_is_lighter_and_preserves_overlap_and_document_text(self):
        document_image = QtGui.QImage(60, 40, QtGui.QImage.Format.Format_RGB32)
        document_image.fill(QtGui.QColor('white'))
        document_painter = QtGui.QPainter(document_image)
        document_painter.fillRect(12, 18, 36, 3, QtGui.QColor('black'))
        document_painter.end()
        view = SimpleNamespace(
            dialog=SimpleNamespace(highlight_style='marker'),
            pixmap_cache={0: {'pixmap': QtGui.QPixmap.fromImage(document_image)}},
        )
        page = PdfPageItem(view, 0, 60, 40)
        page.text_marks = [
            (QtCore.QRectF(10, 10, 30, 20), QtGui.QColor('blue'),
             {'color': '#0000ff', 'date': '2026-11-01', 'ctid': 1}),
            (QtCore.QRectF(20, 10, 30, 20), QtGui.QColor('red'),
             {'color': '#ff0000', 'date': '2026-11-02', 'ctid': 2}),
        ]
        for style, alpha in (('marker', 110), ('marker light', 40), ('underline', 0)):
            with self.subTest(style=style):
                view.dialog.highlight_style = style
                rendered = QtGui.QImage(60, 40, QtGui.QImage.Format.Format_RGB32)
                painter = QtGui.QPainter(rendered)
                try:
                    page.paint(painter, None)
                finally:
                    painter.end()
                self.assertEqual(rendered.pixelColor(15, 15), QtGui.QColor(255 - alpha, 255 - alpha, 255))
                # The newer red coding wins in the overlap without mixing with blue.
                self.assertEqual(rendered.pixelColor(25, 15), QtGui.QColor(255, 255 - alpha, 255 - alpha))
                self.assertEqual(rendered.pixelColor(25, 15), rendered.pixelColor(45, 15))
                # The document's black text remains visible beneath the translucent fill.
                self.assertEqual(rendered.pixelColor(25, 19), QtGui.QColor(alpha, 0, 0))
