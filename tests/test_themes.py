"""Theme migration, palette contrast and preservation of Fusion controls."""

import configparser
import os
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

from PyQt6 import QtCore, QtGui, QtWidgets

from qualcoder.app import App
from qualcoder.themes import LEGACY_THEMES, STYLE_OPTIONS, palette_is_dark, theme_palette


def contrast_ratio(first: QtGui.QColor, second: QtGui.QColor) -> float:
    """Return the WCAG contrast ratio of two opaque colors."""
    luminances = []
    for color in (first, second):
        channels = [value / 255 for value in color.getRgb()[:3]]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
                  for value in channels]
        luminances.append(sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722))))
    return (max(luminances) + 0.05) / (min(luminances) + 0.05)


class TestThemeMigration(TestCase):
    def test_retired_themes_are_persisted_and_migration_is_idempotent(self):
        for previous, expected in {**LEGACY_THEMES, 0: 'native', 'unknown': 'native',
                                   **{name: name for name in STYLE_OPTIONS}}.items():
            with self.subTest(theme=previous), tempfile.TemporaryDirectory() as directory:
                application = App.__new__(App)
                application.configpath = str(Path(directory) / 'config.ini')
                settings = {'stylesheet': previous}
                model_keys = ('name', 'desc', 'access_info_url', 'large_model', 'large_model_context_window',
                              'fast_model', 'fast_model_context_window', 'reasoning_effort', 'api_base', 'api_key')
                models = [{key: 'test' for key in model_keys}]
                migrated, _ = application.check_and_add_additional_settings(settings, models)
                self.assertEqual(migrated['stylesheet'], expected)
                config = configparser.ConfigParser()
                config.read(application.configpath, encoding='utf-8')
                self.assertEqual(config['DEFAULT']['stylesheet'], expected)
                with patch.object(application, 'write_config_ini') as write_config:
                    application.check_and_add_additional_settings(migrated, models)
                    write_config.assert_not_called()

    def test_settings_offer_only_supported_themes(self):
        from qualcoder.settings import STYLE_OPTIONS as settings_options

        self.assertEqual(settings_options, ['native', 'original', 'dark'])


class TestFusionThemes(TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        cls.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.original_palette = self.qt_app.palette()
        self.original_stylesheet = self.qt_app.styleSheet()
        self.qt_app.setStyleSheet('')
        self.qt_app.setStyle('Fusion')
        self.system_palette = self.qt_app.style().standardPalette()
        self.qt_app.setPalette(self.system_palette)
        self.application = App.__new__(App)
        self.application.settings = {'stylesheet': 'native', 'fontsize': 12, 'treefontsize': 14}

    def tearDown(self):
        self.qt_app.paletteChanged.disconnect(self.application._update_native_palette)
        self.qt_app.setStyleSheet(self.original_stylesheet)
        self.qt_app.setPalette(self.original_palette)
        QtWidgets.QToolTip.setPalette(self.original_palette)

    def apply_theme(self, theme_name: str) -> None:
        self.application.settings['stylesheet'] = theme_name
        self.application.apply_theme(self.application.settings)

    def test_fixed_palettes_have_readable_text_in_all_enabled_states(self):
        roles = QtGui.QPalette.ColorRole
        pairs = ((roles.Text, roles.Base), (roles.WindowText, roles.Window),
                 (roles.ButtonText, roles.Button), (roles.HighlightedText, roles.Highlight),
                 (roles.Link, roles.Base), (roles.LinkVisited, roles.Base),
                 (roles.ToolTipText, roles.ToolTipBase), (roles.PlaceholderText, roles.Base))
        for theme_name in ('original', 'dark'):
            self.apply_theme(theme_name)
            palette = self.qt_app.palette()
            self.assertEqual(palette_is_dark(palette), theme_name == 'dark')
            for group in (QtGui.QPalette.ColorGroup.Active, QtGui.QPalette.ColorGroup.Inactive):
                for foreground, background in pairs:
                    with self.subTest(theme=theme_name, group=group, foreground=foreground):
                        self.assertGreaterEqual(contrast_ratio(palette.color(group, foreground),
                                                              palette.color(group, background)), 4.5)
            self.assertEqual(self.application.qtawesome_icon_color(), palette.color(roles.ButtonText))
            self.assertEqual(self.application.qtawesome_icon_color_disabled(),
                             palette.color(QtGui.QPalette.ColorGroup.Disabled, roles.ButtonText))
            self.assertEqual(self.application.highlight_color(), '#f89407')
            self.assertNotEqual(palette.color(roles.Base), palette.color(roles.AlternateBase))
            disabled = QtGui.QPalette.ColorGroup.Disabled
            for foreground, background in ((roles.Text, roles.Base), (roles.ButtonText, roles.Button)):
                self.assertNotEqual(palette.color(disabled, foreground), palette.color(foreground))
                self.assertGreaterEqual(contrast_ratio(palette.color(disabled, foreground),
                                                      palette.color(disabled, background)), 2.5)
            self.assertEqual(QtWidgets.QToolTip.palette().color(roles.ToolTipText),
                             palette.color(roles.ToolTipText))

    def test_fixed_themes_do_not_inherit_system_dark_or_accent_colors(self):
        self.apply_theme('native')  # Also initializes the signal connection for cleanup.
        dark_system = theme_palette('dark', self.system_palette)
        dark_system.setColor(QtGui.QPalette.ColorRole.Highlight, QtGui.QColor('magenta'))
        for theme_name in ('original', 'dark'):
            self.assertEqual(theme_palette(theme_name, self.system_palette), theme_palette(theme_name, dark_system))

    def test_native_restores_system_colors_after_a_fixed_theme(self):
        self.apply_theme('dark')
        self.apply_theme('native')
        roles = QtGui.QPalette.ColorRole
        for role in (roles.Base, roles.Text, roles.Button, roles.ButtonText, roles.Highlight, roles.HighlightedText):
            self.assertEqual(self.qt_app.palette().color(role), self.system_palette.color(role))
        # A later system appearance change also updates native row stripes.
        dark_system = theme_palette('dark', self.system_palette)
        self.qt_app.setPalette(dark_system)
        self.assertTrue(palette_is_dark())
        self.assertNotEqual(self.qt_app.palette().color(roles.Base),
                            self.qt_app.palette().color(roles.AlternateBase))

    def test_controls_keep_fusion_geometry_for_every_theme(self):
        fusion_style = QtWidgets.QStyleFactory.create('Fusion')
        for theme_name in STYLE_OPTIONS:
            self.apply_theme(theme_name)
            for control in (QtWidgets.QPushButton('OK'), QtWidgets.QCheckBox('Checked'),
                            QtWidgets.QRadioButton('Selected'), QtWidgets.QComboBox(),
                            QtWidgets.QSpinBox(), QtWidgets.QSlider()):
                with self.subTest(theme=theme_name, control=type(control).__name__):
                    control.ensurePolished()
                    self.assertEqual(control.styleSheet(), '')
                    option = QtWidgets.QStyleOption()
                    option.initFrom(control)
                    for metric in (QtWidgets.QStyle.PixelMetric.PM_ButtonMargin,
                                   QtWidgets.QStyle.PixelMetric.PM_DefaultFrameWidth,
                                   QtWidgets.QStyle.PixelMetric.PM_IndicatorWidth,
                                   QtWidgets.QStyle.PixelMetric.PM_SliderThickness):
                        self.assertEqual(control.style().pixelMetric(metric, option, control),
                                         fusion_style.pixelMetric(metric, option, control))
                    control.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)
