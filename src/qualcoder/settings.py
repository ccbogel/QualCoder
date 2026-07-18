# -*- coding: utf-8 -*-

"""
This file is part of QualCoder.

QualCoder is free software: you can redistribute it and/or modify it under the
terms of the GNU Lesser General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version.

QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with QualCoder.
If not, see <https://www.gnu.org/licenses/>.

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.org/

"""

import logging
import os
from PyQt6 import QtGui, QtWidgets, QtCore
import qtawesome as qta
import copy
import re
import unicodedata  # <- L normalize localized numerals when reading numeric combos

from .GUI.ui_dialog_settings import Ui_Dialog_settings
from .coder_names import DialogCoderNames
from .helpers import get_default_user_directory, Message
from .ai_llm import (
    add_new_ai_model,
    ensure_chatgpt_oauth_profile_defaults,
    get_available_models,
    get_chatgpt_oauth_status,
    is_chatgpt_oauth_profile,
    renew_chatgpt_oauth,
)

home = os.path.expanduser('~')
path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

USER_I18N_README = """QualCoder additional translations

This folder can contain additional compiled translation files for QualCoder.
It can also contain a zip package for one language.

How to add a language
1. Download additional language files from here:
   https://github.com/ccbogel/QualCoder/tree/master/other_languages/
   If you want to add your own language, follow the instructions here on 
   how to translate the software: https://qualcoder.org/doc/en/7.6.-How-to-contribute/   
2. Put either the zip package or the .qm and .mo files into this folder.
3. Use the same language code for all filenames, for example:
   sv.qm
   sv.mo
   sv.txt (optional)
   sv.zip
4. A zip package should contain both files for the same language.
   It may also contain an optional text file with extra information.
5. Restart QualCoder after selecting the language in Settings.

Notes
- A language is only listed in Settings when a zip package or both the .qm and .mo files are present.
- The zip package will be unpacked automatically when that language is used.
- If a language exists both here and inside QualCoder, the newer file is used.
"""


# Canonical values of the numeric combos in Settings, in the SAME order as the items defined in the .ui. The logic uses these values by INDEX, so
# the translated label (e.g. '۱۰', '十' or even a corrupt label) is presentation only and never alters the stored value.
FONT_SIZES = [8, 10, 12, 14, 16, 18]        # comboBox_fontsize / codetree / docfontsize  
BACKUP_COUNTS = [0, 1, 2, 3, 4, 5]          # comboBox_backups  
CONTEXT_CHARS = [100, 200, 300]             # comboBox_surrounding_chars  
CHUNK_SIZES = [50000, 30000]                # comboBox_text_chunk_size  
STYLE_OPTIONS = ["native", "original", "dark", "blue", "green", "orange", "purple", "yellow", "rainbow"]


def _combo_value(combobox, values, default):  
    """
    Return the canonical value of the selected item, by index.

    The combo's visible text goes through the translation function and may be localized
    (fa: '50،000'; zh: '十') or corrupt (eo: '12 12 12 12'), so the text is NEVER parsed:
    the item index identifies the value. As a safety net (invalid index), the text is
    interpreted with _combo_int bounded to the range of 'values' and, ultimately,
    'default' (the previous valid value) is returned.
    """
    idx = combobox.currentIndex()
    if 0 <= idx < len(values):
        return values[idx]
    return _combo_int(combobox.currentText(), default=default,
                      minimum=min(values), maximum=max(values))


def _set_combo_by_value(combobox, values, value):  
    """
    Select in the combo the item whose canonical value matches, by index.

    Replaces findText(str(value)): with translated or corrupt labels, findText cannot
    match the text and the dialog always showed the first item instead of the user's
    stored selection. By index, the selection is always honoured.
    """
    try:
        combobox.setCurrentIndex(values.index(value))
    except ValueError:
        combobox.setCurrentIndex(0)


def _combo_int(text, default=0, minimum=None, maximum=None):  # <- L
    """
    Convert a numeric combo's text to int, tolerating localization and guarding
    against corrupt translations. Safety net for _combo_value.

    Covers two real problems seen in the translation files:
    1) Localized numerals: some translations (e.g. fa) use non-ASCII digits or
       thousands separators (Arabic comma U+060C), so 'currentText()' returns
       '50،000' and int() fails. We keep only the decimal digits, mapped to ASCII.
    2) Duplicated or exorbitant numerals: other translations (e.g. eo) duplicate the
       literal ('12' -> '12 12 12 12'), which would yield 12121212 and break the UI
       (giant fonts). If 'minimum'/'maximum' are given and the value is out of range,
       a warning is logged and 'default' (the previous valid value) is returned
       instead of applying the corrupt number.
    """
    
    digits = ''.join(
        str(unicodedata.decimal(ch)) for ch in text
        if unicodedata.decimal(ch, None) is not None
    )
    value = int(digits) if digits else default
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        logger.warning(
            "Numeric combo value out of range after translation: %r -> %s "
            "(allowed %s..%s). Falling back to %s.", text, value, minimum, maximum, default)  # <- L
        return default
    return value


class StrictDoubleRangeValidator(QtGui.QDoubleValidator):
    """Treat fully-parseable out-of-range numbers as invalid while typing."""

    def validate(self, text: str, pos: int):
        state, text, pos = super().validate(text, pos)
        normalized = text.strip().replace(',', '.')
        if normalized in ('', '.', '-', '-.', '+', '+.'):
            return QtGui.QValidator.State.Intermediate, text, pos
        try:
            value = float(normalized)
        except ValueError:
            return state, text, pos
        if value < self.bottom() or value > self.top():
            return QtGui.QValidator.State.Invalid, text, pos
        return state, text, pos


class DialogSettings(QtWidgets.QDialog):
    """ Settings for the coder name, coder table and to display ids. """

    settings = {}

    def __init__(self, app, parent=None, section=None, enable_ai=False):

        self.app = app
        if self.app.conn is not None:
            self.initial_changes = self.app.conn.total_changes
        self.settings = copy.deepcopy(self.app.settings)
        self.ai_models = copy.deepcopy(self.app.ai_models)
        self.coder_names_changes = False 
        super(QtWidgets.QDialog, self).__init__(parent)  # overrride accept method
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_settings()
        self.ui.setupUi(self)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        new_font = QtGui.QFont(self.settings['font'], self.settings['fontsize'], QtGui.QFont.Weight.Normal)
        self.ui.lineEdit_coderName.setText(self.settings['codername'])
        self.ui.pushButton_set_coder.clicked.connect(self.set_coder)        
        self.ui.fontComboBox.setCurrentFont(new_font)
        self.selected_language_index = -1
        self.populate_language_combo()
        self.ui.comboBox_language.currentIndexChanged.connect(self.language_index_changed)
        self.ui.comboBox_language.activated.connect(self.language_activated)
        self.ui.comboBox_language.installEventFilter(self)

        timestampformats = ["[mm.ss]", "[mm:ss]", "[hh.mm.ss]", "[hh:mm:ss]",
                            "{hh:mm:ss}", "#hh:mm:ss.sss#"]
        self.ui.comboBox_timestamp.addItems(timestampformats)
        for index, ts in enumerate(timestampformats):
            if ts == self.settings['timestampformat']:
                self.ui.comboBox_timestamp.setCurrentIndex(index)
        speakernameformats = ["[]", "{}", ":"]
        self.ui.comboBox_speaker.addItems(speakernameformats)
        for index, snf in enumerate(speakernameformats):
            if snf == self.settings['speakernameformat']:
                self.ui.comboBox_speaker.setCurrentIndex(index)

        # Selection by canonical value (index), immune to translated or corrupt labels.
        _set_combo_by_value(self.ui.comboBox_fontsize, FONT_SIZES, self.settings['fontsize'])
        _set_combo_by_value(self.ui.comboBox_codetreefontsize, FONT_SIZES, self.settings['treefontsize'])
        _set_combo_by_value(self.ui.comboBox_docfontsize, FONT_SIZES, self.settings['docfontsize'])
        _set_combo_by_value(self.ui.comboBox_text_chunk_size, CHUNK_SIZES, self.settings['codetext_chunksize'])
        self.ui.checkBox_auto_backup.stateChanged.connect(self.backup_state_changed)
        if self.settings['showids'] == 'True':
            self.ui.checkBox.setChecked(True)
        else:
            self.ui.checkBox.setChecked(False)
        styles = STYLE_OPTIONS
        styles_translated = [_(style_name) for style_name in styles]
        self.ui.comboBox_style.addItems(styles_translated)
        for index, style in enumerate(styles):
            if style == self.settings['stylesheet']:
                self.ui.comboBox_style.setCurrentIndex(index)
        if self.settings['backup_on_open'] == 'True':
            self.ui.checkBox_auto_backup.setChecked(True)
        else:
            self.ui.checkBox_auto_backup.setChecked(False)
        if self.settings['backup_av_files'] == 'True':
            self.ui.checkBox_backup_AV_files.setChecked(True)
        else:
            self.ui.checkBox_backup_AV_files.setChecked(False)

        _set_combo_by_value(self.ui.comboBox_backups, BACKUP_COUNTS, self.settings['backup_num'])

        if self.settings['directory'] == "":
            self.settings['directory'] = get_default_user_directory()
        self.ui.label_directory.setText(self.settings['directory'])
        text_styles = [_('Bold'), _('Italic'), _('Bigger')]
        self.ui.comboBox_text_style.addItems(text_styles)
        for index, text_style in enumerate(text_styles):
            if text_style == self.settings['report_text_context_style']:
                self.ui.comboBox_text_style.setCurrentIndex(index)

        _set_combo_by_value(self.ui.comboBox_surrounding_chars, CONTEXT_CHARS,
                            self.settings['report_text_context_characters'])
        msg = _("Default folder for storing automatic backups and for file outputs.")
        self.ui.pushButton_choose_directory.setToolTip(msg)
        self.ui.pushButton_choose_directory.clicked.connect(self.choose_directory)

        # AI options
        if enable_ai or self.settings['ai_enable'] == 'True':
            self.ui.checkBox_AI_enable.setChecked(True)
        else:
            self.ui.checkBox_AI_enable.setChecked(False)
        self.ui.checkBox_AI_enable.stateChanged.connect(self.ai_enable_state_changed)
        self.ui.comboBox_reasoning.addItems(['default', 'low', 'medium', 'high'])
        self.ui.comboBox_ai_profile.clear()
        self.load_ai_profiles()
        self.ui.comboBox_ai_profile.currentIndexChanged.connect(self.ai_profile_changed)
        self.ai_enable_state_changed()
        self.ui.pushButton_ai_profile_edit.clicked.connect(self.ai_profile_name_edit)
        self.ui.lineEdit_ai_api_key.editingFinished.connect(self.ai_api_key_changed)
        self.ui.toolButtonShowApiKey.setIcon(qta.icon('mdi6.eye-outline'))
        self.ui.toolButtonShowApiKey.toggled.connect(self.ai_api_key_show)
        self.ui.pushButton_renew_auth.clicked.connect(self.renew_ai_authentication)
        # advanced AI options:
        self.ui.pushButton_advanced_AI_options.clicked.connect(self.toggle_ai_advanced_options)
        self.toggle_ai_advanced_options() # hide the advanced AI options panel
        int_validator = QtGui.QIntValidator(self)
        int_validator.setBottom(0)
        self.ui.lineEdit_ai_large_context_window.setValidator(int_validator)
        self.ui.lineEdit_ai_fast_context_window.setValidator(int_validator)
        self.ui.lineEdit_ai_large_context_window.editingFinished.connect(self.ai_model_parameters_changed)
        self.ui.lineEdit_ai_fast_context_window.editingFinished.connect(self.ai_model_parameters_changed)
        self.ui.comboBox_AI_model_large.currentTextChanged.connect(self.ai_model_parameters_changed)
        self.ui.comboBox_AI_model_fast.currentTextChanged.connect(self.ai_model_parameters_changed)
        self.ui.comboBox_AI_model_large.view().setMinimumWidth(500)  # Set a minimum width for the dropdown list
        self.ui.comboBox_AI_model_fast.view().setMinimumWidth(500)
        self.ui.checkBox_AI_language_ui.setChecked(self.settings.get('ai_language_ui', 'True') == 'True')
        self.ui.checkBox_AI_language_ui.stateChanged.connect(self.ai_language_ui_changed)
        self.ui.lineEdit_AI_language.setText(self.settings.get('ai_language', ''))
        self.ui.lineEdit_AI_language.setEnabled(not self.ui.checkBox_AI_language_ui.isChecked())
        self.ui.lineEdit_ai_temperature.setText(self.settings.get('ai_temperature', '1.0'))
        self.ui.lineEdit_ai_temperature.setValidator(self._create_ai_float_validator(0.0, 2.0))
        self.ui.lineEdit_ai_temperature.editingFinished.connect(self.validate_ai_temperature)
        self.ui.lineEdit_top_p.setText(self.settings.get('ai_top_p', '1.0'))
        self.ui.lineEdit_top_p.setValidator(self._create_ai_float_validator(0.0, 1.0))
        self.ui.lineEdit_top_p.editingFinished.connect(self.validate_ai_top_p)
        self.ui.comboBox_reasoning.currentIndexChanged.connect(self.ai_model_parameters_changed)
        self.ui.lineEdit_ai_api_base.editingFinished.connect(self.ai_api_base_changed)
        self.ui.pushButton_ai_new_profile.clicked.connect(self.new_ai_profile)
        
        # Move to AI settings if requested
        if section is not None and (section == 'AI' or section == 'advanced AI'):
            if section == 'advanced AI':
                self.ui.pushButton_advanced_AI_options.setChecked(True)
                self.toggle_ai_advanced_options()
            self.ui.scrollArea.verticalScrollBar().setValue(self.ui.scrollArea.verticalScrollBar().maximum())
            # Use QTimers to briefly flash a yellow border around the AI settings
            QtCore.QTimer.singleShot(200, lambda:self.ui.widget_ai.setStyleSheet('#widget_ai {\n'
                                                                                  '   border: 3px solid yellow; \n'
                                                                                  '   border-radius: 5px; \n'
                                                                                  '}'))
            QtCore.QTimer.singleShot(700, lambda: self.ui.widget_ai.setStyleSheet('#widget_ai { border: none; }'))
        else:
            self.ui.widget_ai.setStyleSheet('')

        self.load_ai_permissions()

    def load_ai_permissions(self):
        ai_permissions = self.settings.get('ai_permissions', 1)
        if ai_permissions not in (0, 1, 2):
            ai_permissions = 1
            self.settings['ai_permissions'] = ai_permissions
        self.ui.comboBox_ai_permissions.setCurrentIndex(ai_permissions)

    def current_ai_permissions(self):
        index = self.ui.comboBox_ai_permissions.currentIndex()
        if index not in (0, 1, 2):
            return 1
        return index

    def get_selected_language_code(self):
        """Return the currently selected language code, excluding the action item."""

        current_index = self.ui.comboBox_language.currentIndex()
        item_type = self.ui.comboBox_language.itemData(current_index, QtCore.Qt.ItemDataRole.UserRole + 1)
        if item_type == 'language':
            return self.ui.comboBox_language.itemData(current_index, QtCore.Qt.ItemDataRole.UserRole)
        if self.selected_language_index >= 0:
            return self.ui.comboBox_language.itemData(self.selected_language_index, QtCore.Qt.ItemDataRole.UserRole)
        return 'en'

    def set_language_combo_selection(self, lang_code):
        """Select a language entry in the combobox by code."""

        for index in range(self.ui.comboBox_language.count()):
            item_type = self.ui.comboBox_language.itemData(index, QtCore.Qt.ItemDataRole.UserRole + 1)
            if item_type != 'language':
                continue
            if self.ui.comboBox_language.itemData(index, QtCore.Qt.ItemDataRole.UserRole) == lang_code:
                self.ui.comboBox_language.setCurrentIndex(index)
                self.selected_language_index = index
                return True
        return False

    def populate_language_combo(self, preferred_language=None):
        """Populate built-in languages, user languages and the add-language action."""

        tooltip_lines = [
            _("Close and open the software for the change in language to occur."),
            _("Additional community supported languages can be installed by selecting \"Add more languages...\" in the dropdown."),
        ]
        self.ui.comboBox_language.clear()
        builtin_codes = set()
        for code, label in self.app.get_builtin_language_labels():
            builtin_codes.add(code)
            index = self.ui.comboBox_language.count()
            self.ui.comboBox_language.addItem(f"{label} {code}")
            self.ui.comboBox_language.setItemData(index, code, QtCore.Qt.ItemDataRole.UserRole)
            self.ui.comboBox_language.setItemData(index, 'language', QtCore.Qt.ItemDataRole.UserRole + 1)

        for code in self.app.get_complete_user_language_codes():
            if code in builtin_codes:
                continue
            index = self.ui.comboBox_language.count()
            self.ui.comboBox_language.addItem(f"other - {code}")
            self.ui.comboBox_language.setItemData(index, code, QtCore.Qt.ItemDataRole.UserRole)
            self.ui.comboBox_language.setItemData(index, 'language', QtCore.Qt.ItemDataRole.UserRole + 1)

        current_language = preferred_language if preferred_language is not None else self.settings['language']
        if not self.set_language_combo_selection(current_language):
            if not self.set_language_combo_selection('en'):
                for index in range(self.ui.comboBox_language.count()):
                    item_type = self.ui.comboBox_language.itemData(index, QtCore.Qt.ItemDataRole.UserRole + 1)
                    if item_type == 'language':
                        self.ui.comboBox_language.setCurrentIndex(index)
                        self.selected_language_index = index
                        break

        action_index = self.ui.comboBox_language.count()
        self.ui.comboBox_language.addItem(_("Add more languages..."))
        self.ui.comboBox_language.setItemData(action_index, 'add_other_language', QtCore.Qt.ItemDataRole.UserRole)
        self.ui.comboBox_language.setItemData(action_index, 'action', QtCore.Qt.ItemDataRole.UserRole + 1)
        self.ui.comboBox_language.setToolTip("\n".join(tooltip_lines))

    def language_index_changed(self, index):
        """Remember the last selected language entry."""

        item_type = self.ui.comboBox_language.itemData(index, QtCore.Qt.ItemDataRole.UserRole + 1)
        if item_type == 'language':
            self.selected_language_index = index

    def refresh_language_combo(self):
        """Reload user languages while preserving the current selection."""

        preferred_language = self.get_selected_language_code()
        with QtCore.QSignalBlocker(self.ui.comboBox_language):
            self.populate_language_combo(preferred_language)

    def eventFilter(self, obj, event):
        if obj == self.ui.comboBox_language:
            if event.type() == QtCore.QEvent.Type.MouseButtonPress:
                self.refresh_language_combo()
            if event.type() == QtCore.QEvent.Type.KeyPress:
                if event.key() in (QtCore.Qt.Key.Key_F4, QtCore.Qt.Key.Key_Down):
                    self.refresh_language_combo()
        return super().eventFilter(obj, event)

    def language_activated(self, index):
        """Handle the action item in the language combobox."""

        item_type = self.ui.comboBox_language.itemData(index, QtCore.Qt.ItemDataRole.UserRole + 1)
        if item_type != 'action':
            return
        self.open_user_language_folder()
        if self.selected_language_index >= 0:
            with QtCore.QSignalBlocker(self.ui.comboBox_language):
                self.ui.comboBox_language.setCurrentIndex(self.selected_language_index)

    def open_user_language_folder(self):
        """Create the user i18n folder and readme if needed, then open it."""

        user_i18n_dir = self.app.get_user_i18n_dir()
        try:
            os.makedirs(user_i18n_dir, exist_ok=True)
            readme_path = os.path.join(user_i18n_dir, "README.TXT")
            if not os.path.exists(readme_path):
                with open(readme_path, 'w', encoding='utf-8') as file_:
                    file_.write(USER_I18N_README)
        except Exception as err:
            logger.error(err)
            Message(self.app, _("Add more languages..."), str(err), "warning").exec()
            return
        opened = QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(user_i18n_dir))
        if not opened:
            Message(self.app, _("Add more languages..."),
                    _("Could not open the user translation folder.") + "\n" + user_i18n_dir,
                    "warning").exec()
        msg = _("Download additional language files from here:") + "\n"
        msg += "https://github.com/ccbogel/QualCoder/tree/master/other_languages/\n"
        msg += _("Put either the zip file or the .qm and .mo files into the folder") + " .qualcoder/i18n\n"
        msg += "For example: sv.zip, or both the sv.mo and sv.qm files." + "\n"
        msg += _("Then select that language in the dropdown box.") + "\n"
        msg += _("Additional languages may not be the most current translations, and they may contain inaccurate translations.")  + "\n"
        msg += _("Read the README.txt file in the i18n folder for more information.")
        Message(self.app, _("Add more languages"), msg, "information").exec()

    def backup_state_changed(self):
        """ Enable and disable av backup checkbox. Only enable when checkBox_auto_backup is checked. """

        if self.ui.checkBox_auto_backup.isChecked():
            self.ui.checkBox_backup_AV_files.setEnabled(True)
        else:
            self.ui.checkBox_backup_AV_files.setEnabled(False)

    def current_ai_model_index(self) -> int:
        """Return the currently selected AI profile index, or -1 if none is selected."""

        try:
            return int(self.settings.get('ai_model_index', -1))
        except (TypeError, ValueError):
            return -1

    def current_ai_profile(self):
        """Return the currently selected AI profile dictionary, or None."""

        ai_model_index = self.current_ai_model_index()
        if 0 <= ai_model_index < len(self.ai_models):
            return self.ai_models[ai_model_index]
        return None

    def current_ai_profile_uses_oauth(self) -> bool:
        """Return whether the current AI profile uses ChatGPT OAuth."""

        return is_chatgpt_oauth_profile(self.current_ai_profile())

    def refresh_ai_auth_status(self):
        """Refresh the authentication status label for OAuth profiles."""

        if not self.current_ai_profile_uses_oauth():
            self.ui.label_auth_result.setText('')
            return
        is_authenticated, status_text = get_chatgpt_oauth_status()
        self.ui.label_auth_result.setText(status_text)

    def update_ai_auth_widgets(self):
        """Toggle API-key and OAuth widgets according to the current profile type."""

        is_enabled = self.ui.checkBox_AI_enable.isChecked()
        uses_oauth = self.current_ai_profile_uses_oauth()
        self.ui.label_ai_api_key.setVisible(not uses_oauth)
        self.ui.lineEdit_ai_api_key.setVisible(not uses_oauth)
        self.ui.toolButtonShowApiKey.setVisible(not uses_oauth)
        self.ui.label_auth.setVisible(uses_oauth)
        self.ui.label_auth_result.setVisible(uses_oauth)
        self.ui.pushButton_renew_auth.setVisible(uses_oauth)
        self.ui.lineEdit_ai_api_key.setEnabled(is_enabled and (not uses_oauth))
        self.ui.toolButtonShowApiKey.setEnabled(is_enabled and (not uses_oauth))
        self.ui.label_auth.setEnabled(is_enabled and uses_oauth)
        self.ui.label_auth_result.setEnabled(is_enabled and uses_oauth)
        self.ui.pushButton_renew_auth.setEnabled(is_enabled and uses_oauth)
        if uses_oauth:
            self.refresh_ai_auth_status()
        else:
            self.ui.label_auth_result.setText('')

    def ai_enable_state_changed(self):
        self.ui.comboBox_ai_profile.setEnabled(self.ui.checkBox_AI_enable.isChecked())
        self.ui.label_ai_model_desc.setEnabled(self.ui.checkBox_AI_enable.isChecked())
        self.ui.label_ai_access_info_url.setEnabled(self.ui.checkBox_AI_enable.isChecked())
        self.ui.lineEdit_ai_temperature.setEnabled(self.ui.checkBox_AI_enable.isChecked())
        self.ui.lineEdit_top_p.setEnabled(self.ui.checkBox_AI_enable.isChecked())
        self.ui.checkBox_AI_language_ui.setEnabled(self.ui.checkBox_AI_enable.isChecked())
        self.ui.lineEdit_AI_language.setEnabled(self.ui.checkBox_AI_enable.isChecked() and (not self.ui.checkBox_AI_language_ui.isChecked()))
        self.update_ai_auth_widgets()
    
    def load_ai_profiles(self):
        with QtCore.QSignalBlocker(self.ui.comboBox_ai_profile):
            self.ui.comboBox_ai_profile.clear()
            if len(self.ai_models) > 0:
                for i in range(len(self.ai_models)):
                    model = self.ai_models[i]
                    self.ui.comboBox_ai_profile.addItem(model['name'])
                    self.ui.comboBox_ai_profile.setItemData(i, model['desc'], QtCore.Qt.ItemDataRole.ToolTipRole)
                if 0 <= int(self.settings['ai_model_index']) <= (len(self.ai_models) - 1): 
                    self.ui.comboBox_ai_profile.setCurrentIndex(int(self.settings['ai_model_index']))
                else:  # ai_model_index out of range
                    self.settings['ai_model_index'] = 0
                    self.ui.comboBox_ai_profile.setCurrentIndex(0)
            else:  # no ai profiles defined
                self.settings['ai_model_index'] = -1
        self.ai_profile_changed()
    
    def ai_profile_changed(self):
        self.settings['ai_model_index'] = self.ui.comboBox_ai_profile.currentIndex()
        if int(self.settings['ai_model_index']) >= 0:
            curr_ai_model = self.ai_models[int(self.settings['ai_model_index'])]
            ensure_chatgpt_oauth_profile_defaults(curr_ai_model)
            self.ui.label_ai_model_desc.setText(curr_ai_model['desc'])
            self.ui.label_ai_access_info_url.setText(f'<a href="{curr_ai_model["access_info_url"]}">{curr_ai_model["access_info_url"]}</a>')
            with QtCore.QSignalBlocker(self.ui.lineEdit_ai_api_key): # prevents ai_update_available_models() to trigger
                self.ui.lineEdit_ai_api_key.setText(curr_ai_model['api_key']) 
            with QtCore.QSignalBlocker(self.ui.comboBox_AI_model_large):
                self.ui.comboBox_AI_model_large.setCurrentText(curr_ai_model['large_model'])
                self.ui.comboBox_AI_model_large.lineEdit().setCursorPosition(0)
            with QtCore.QSignalBlocker(self.ui.comboBox_AI_model_fast):
                self.ui.comboBox_AI_model_fast.setCurrentText(curr_ai_model['fast_model'])
                self.ui.comboBox_AI_model_fast.lineEdit().setCursorPosition(0)
            with QtCore.QSignalBlocker(self.ui.lineEdit_ai_large_context_window):
                self.ui.lineEdit_ai_large_context_window.setText(curr_ai_model['large_model_context_window'])
            with QtCore.QSignalBlocker(self.ui.lineEdit_ai_fast_context_window):
                self.ui.lineEdit_ai_fast_context_window.setText(curr_ai_model['fast_model_context_window'])
            try:
                reasoning_effort = curr_ai_model['reasoning_effort']
                with QtCore.QSignalBlocker(self.ui.comboBox_reasoning):
                    self.ui.comboBox_reasoning.setCurrentText(reasoning_effort)
            except:
                self.ui.comboBox_reasoning.setCurrentText('default')
            with QtCore.QSignalBlocker(self.ui.lineEdit_ai_api_base):
                self.ui.lineEdit_ai_api_base.setText(curr_ai_model['api_base'])    
        else:
            self.ui.label_ai_model_desc.setText('')
            self.ui.label_ai_access_info_url.setText('')
            with QtCore.QSignalBlocker(self.ui.lineEdit_ai_api_key): # prevents ai_update_available_models() to trigger
                self.ui.lineEdit_ai_api_key.setText('')
            self.ui.comboBox_AI_model_large.setCurrentText('')
            self.ui.comboBox_AI_model_fast.setCurrentText('')
            self.ui.lineEdit_ai_large_context_window.setText('')
            self.ui.lineEdit_ai_fast_context_window.setText('') 
            self.ui.comboBox_reasoning.setCurrentText('default')
            with QtCore.QSignalBlocker(self.ui.lineEdit_ai_api_base):
                self.ui.lineEdit_ai_api_base.setText('')    
        self.update_ai_auth_widgets()
        self.ai_update_available_models()
        
    def ai_profile_name_edit(self):
        if int(self.settings['ai_model_index']) < 0:
            Message.warning(self, _('Edit AI profile name'), _('Select a profile first. \n'
                'You can only edit the name of an existing profile. ' 
                'To create a new profile from scratch, follow the instructions in the QualCoder '
                'wiki on GitHub.'))
            return
        curr_name = self.ai_models[int(self.settings['ai_model_index'])]['name']
        new_name, ok = QtWidgets.QInputDialog.getText(
            self,                                     # parent
            _('Edit AI profile name'),                # title
            _('Enter new profile name:'),             # label
            QtWidgets.QLineEdit.EchoMode.Normal,      # echo
            curr_name                                 # text
        )
        if ok and new_name != '':
            # clean up new name for use in ini file
            new_name = new_name.replace('[', '').replace(']', '') # Remove square brackets
            new_name = re.sub(r'[\r\n]+', ' ', new_name) # Replace line breaks with a space
            new_name = re.sub(r'\s+', ' ', new_name) # Remove repeated spaces
            new_name = new_name.strip() # Remove leading/trailing whitespace
            # if name not altered, return
            if new_name == curr_name:
                return
            # make the new name unique
            existing_names = {model['name'] for model in self.ai_models}
            i = 1
            candidate = new_name
            while candidate in existing_names: # Find next available unique name: new_name_1, new_name_2, etc.
                candidate = f"{new_name}_{i}"
                i += 1
            new_name = candidate            
            
            self.ai_models[int(self.settings['ai_model_index'])]['name'] = new_name
            with QtCore.QSignalBlocker(self.ui.comboBox_ai_profile): 
                self.ui.comboBox_ai_profile.setItemText(int(self.settings['ai_model_index']), new_name)
                self.ui.comboBox_ai_profile.setCurrentText = new_name
        
    def ai_model_parameters_changed(self):
        """Called if the selected large or fast model has changed or if one of the 
        context window numbers has been altered."""
        ai_model_index = int(self.settings['ai_model_index'])
        if 0 <= ai_model_index < len(self.ai_models):
            self.ai_models[ai_model_index]['large_model'] = self.ui.comboBox_AI_model_large.currentText()
            self.ai_models[ai_model_index]['fast_model'] = self.ui.comboBox_AI_model_fast.currentText()
            if self.ui.lineEdit_ai_large_context_window.text() != '':
                self.ai_models[ai_model_index]['large_model_context_window'] = self.ui.lineEdit_ai_large_context_window.text()
            else:
                self.ai_models[ai_model_index]['large_model_context_window'] = '32768' # default
            if self.ui.lineEdit_ai_fast_context_window.text() != '':
                self.ai_models[ai_model_index]['fast_model_context_window'] = self.ui.lineEdit_ai_fast_context_window.text()
            else:
                self.ai_models[ai_model_index]['fast_model_context_window'] = '32768' # default
            self.ai_models[ai_model_index]['reasoning_effort'] = self.ui.comboBox_reasoning.currentText()        

    def validate_ai_api_key(self, api_key: str, focus_field: bool = False) -> bool:
        """Reject API keys that contain non-ASCII characters.

        The current OpenAI-compatible client stack sends the key in an HTTP header,
        so visually similar Unicode characters break authentication before the request
        is sent.
        """
        invalid_chars = []
        for char in api_key:
            if ord(char) > 127:
                invalid_chars.append(f"{char} (U+{ord(char):04X})")
                if len(invalid_chars) == 5:
                    break
        if not invalid_chars:
            return True

        msg = _('The API key contains non-ASCII characters and cannot be used.\n'
                'Please paste the key again exactly as provided by your AI provider. \n\n'
                'Invalid character(s): ') + ', '.join(invalid_chars)
        Message.warning(self, _('Invalid API key'), msg)
        if focus_field:
            self.ui.lineEdit_ai_api_key.setFocus()
            self.ui.lineEdit_ai_api_key.selectAll()
        return False

    def ai_api_key_changed(self):
        if int(self.settings['ai_model_index']) >= 0:
            if self.current_ai_profile_uses_oauth():
                ensure_chatgpt_oauth_profile_defaults(self.current_ai_profile())
                with QtCore.QSignalBlocker(self.ui.lineEdit_ai_api_key):
                    self.ui.lineEdit_ai_api_key.setText(self.current_ai_profile()['api_key'])
                return
            api_key = self.ui.lineEdit_ai_api_key.text()
            if not self.validate_ai_api_key(api_key, focus_field=True):
                return
            self.ai_models[int(self.settings['ai_model_index'])]['api_key'] = api_key
        self.ai_update_available_models()
        
    def ai_api_key_show(self, checked):
        self.ui.lineEdit_ai_api_key.setEchoMode(QtWidgets.QLineEdit.EchoMode.Normal if checked else QtWidgets.QLineEdit.EchoMode.PasswordEchoOnEdit) 

    def ai_update_available_models(self):
        if not self.ui.widget_AI_advanced_options.isVisible():
            return
        model_list = []
        if int(self.settings['ai_model_index']) >= 0:
            try:
                model_list = get_available_models(self.app,
                                                  self.ai_models[int(self.settings['ai_model_index'])]['api_base'], 
                                                  self.ai_models[int(self.settings['ai_model_index'])]['api_key'])
            except Exception as e:
                msg = type(e).__name__ + ': ' + str(e)
                logger.error("Error getting AI model list: " + msg)
                model_list = ['<Error getting AI model list>']
        curr_model_large = self.ui.comboBox_AI_model_large.currentText()
        self.ui.comboBox_AI_model_large.clear()
        self.ui.comboBox_AI_model_large.addItems(model_list)
        self.ui.comboBox_AI_model_large.setCurrentText(curr_model_large)
        self.ui.comboBox_AI_model_large.lineEdit().setCursorPosition(0)
        curr_model_fast = self.ui.comboBox_AI_model_fast.currentText()
        self.ui.comboBox_AI_model_fast.clear()
        self.ui.comboBox_AI_model_fast.addItems(model_list)
        self.ui.comboBox_AI_model_fast.setCurrentText(curr_model_fast)
        self.ui.comboBox_AI_model_fast.lineEdit().setCursorPosition(0)

    def adjust_ai_models_comboboxes(self):
        # Adjust the width of the AI models ComboBox
        self.ui.comboBox_AI_model_large.setMaximumWidth(self.ui.label_ai_large_contex_window.width() + 6 + self.ui.lineEdit_ai_large_context_window.width())
        self.ui.comboBox_AI_model_fast.setMaximumWidth(self.ui.label_ai_fast_contex_window.width() + 6 + self.ui.lineEdit_ai_fast_context_window.width())        

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_ai_models_comboboxes()

    def showEvent(self, event):
        super().showEvent(event)
        self.adjust_ai_models_comboboxes()

    def ai_language_ui_changed(self):
        self.ui.lineEdit_AI_language.setEnabled(not self.ui.checkBox_AI_language_ui.isChecked())
        if not self.ui.checkBox_AI_language_ui.isChecked():
            self.ui.lineEdit_AI_language.setFocus()
            self.ui.lineEdit_AI_language.selectAll()

    def _create_ai_float_validator(self, minimum: float, maximum: float) -> QtGui.QDoubleValidator:
        validator = StrictDoubleRangeValidator(minimum, maximum, 6, self)
        validator.setNotation(QtGui.QDoubleValidator.Notation.StandardNotation)
        locale = QtCore.QLocale.c()
        locale.setNumberOptions(QtCore.QLocale.NumberOption.RejectGroupSeparator)
        validator.setLocale(locale)
        return validator

    @staticmethod
    def parse_bounded_float(text: str, minimum: float, maximum: float) -> str:
        """Normalize a user-entered float and ensure it stays within range."""

        normalized = text.strip().replace(',', '.')
        if normalized == '':
            raise ValueError("empty float value")
        value = float(normalized)
        if not (minimum <= value <= maximum):
            raise ValueError(f"float value {value} outside [{minimum}, {maximum}]")
        return str(value)

    def validate_ai_float_field(self, line_edit, minimum: float, maximum: float, message: str) -> bool:
        try:
            normalized = self.parse_bounded_float(line_edit.text(), minimum, maximum)
        except ValueError:
            Message.warning(self, _("Invalid input"), message)
            line_edit.setFocus()
            line_edit.selectAll()
            return False
        line_edit.setText(normalized)
        return True

    def validate_ai_temperature(self) -> bool:
        return self.validate_ai_float_field(
            self.ui.lineEdit_ai_temperature,
            0.0,
            2.0,
            _("AI temperature parameter must be between 0.0 and 2.0."),
        )

    def validate_ai_top_p(self) -> bool:
        return self.validate_ai_float_field(
            self.ui.lineEdit_top_p,
            0.0,
            1.0,
            _("AI top_p parameter must be between 0.0 and 1.0."),
        )

    def renew_ai_authentication(self):
        """Start or renew ChatGPT OAuth authentication for the current profile."""

        if not self.current_ai_profile_uses_oauth():
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        try:
            is_authenticated, status_text = renew_chatgpt_oauth()
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
        self.ui.label_auth_result.setText(status_text)
        if not is_authenticated:
            Message.warning(self, _('Authentication'), status_text)
            
    def ai_api_base_changed(self):
        if int(self.settings['ai_model_index']) >= 0:
            curr_ai_model = self.ai_models[int(self.settings['ai_model_index'])]
            curr_ai_model['api_base'] = self.ui.lineEdit_ai_api_base.text()
            ensure_chatgpt_oauth_profile_defaults(curr_ai_model)
            with QtCore.QSignalBlocker(self.ui.lineEdit_ai_api_key):
                self.ui.lineEdit_ai_api_key.setText(curr_ai_model['api_key'])
        self.update_ai_auth_widgets()
        self.ai_update_available_models()
            
    def set_coder(self):
        """ Edit the coder names and select the current one.
        Changes made to the database (e.g. renamed coders) will NOT be committed until the settings dialog 
        is closed with OK."""
        
        ui_coder_names = DialogCoderNames(self.app, self.settings, extended_options=True, do_commit=False)
        if ui_coder_names.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.ui.lineEdit_coderName.setText(self.settings['codername'])
            if ui_coder_names.coder_names_changed:
                self.coder_names_changes = True

    def choose_directory(self):
        """ Choose default project output folder. """

        directory = QtWidgets.QFileDialog.getExistingDirectory(self,
            _('Choose a default output folder'), self.settings['directory'])
        if directory == "":
            return
        if directory.endswith(".qualcoder"):
            Message(self.app, _("Choose another folder"), _("Do not use the QualCoder configuration folder."),"warning").exec()
            return
        if directory.endswith(".qda"):
            Message(self.app, _("Choose another folder"), _("Do not use the QualCoder data folder."),"warning").exec()
            return
        self.ui.label_directory.setText(directory)
        
    def toggle_ai_advanced_options(self):
        if self.ui.pushButton_advanced_AI_options.isChecked():
            self.ui.widget_AI_advanced_options.show()
            self.ai_update_available_models()
            QtCore.QTimer.singleShot(100, lambda: self.ui.scrollArea.verticalScrollBar().setValue(self.ui.scrollArea.verticalScrollBar().maximum()))
        else:
            self.ui.widget_AI_advanced_options.hide()
            
    def new_ai_profile(self):
        """Adds a new, empty AI profile and selects it.
        """
        new_name, ok = QtWidgets.QInputDialog.getText(
            self,                                     # parent
            _('New AI profile'),                      # title
            _('Enter new profile name:'),             # label
            QtWidgets.QLineEdit.EchoMode.Normal,      # echo
        )
        if ok and new_name != '':
            # clean up new name for use in ini file
            new_name = new_name.replace('[', '').replace(']', '') # Remove square brackets
            new_name = re.sub(r'[\r\n]+', ' ', new_name) # Replace line breaks with a space
            new_name = re.sub(r'\s+', ' ', new_name) # Remove repeated spaces
            new_name = new_name.strip() # Remove leading/trailing whitespace
            # ensure the new name is unique
            existing_names = {model['name'] for model in self.ai_models}
            if new_name in existing_names:
                Message(_('New AI profile'), _('An AI profile with this name already exists: ') + new_name, 'critical')
                return
            
            self.ai_models, self.settings['ai_model_index'] = add_new_ai_model(self.ai_models, new_name)
            self.load_ai_profiles()

    def accept(self):
        restart_qualcoder = False
        if self.settings['codername'] == "":
            self.settings['codername'] = "default"
            self.coder_names_changes = True
        if self.settings['codername'] != self.app.settings['codername']:
            self.coder_names_changes = True
            if self.app.conn is not None:
                # None if no project opened
                cur = self.app.conn.cursor()
                cur.execute('update project set codername=?', [self.settings['codername']])
        self.settings['font'] = self.ui.fontComboBox.currentText()

        # Read by index: the translated (or corrupt) label never alters the value
        self.settings['fontsize'] = _combo_value(self.ui.comboBox_fontsize, FONT_SIZES,
                                                 self.app.settings['fontsize'])
        self.settings['treefontsize'] = _combo_value(self.ui.comboBox_codetreefontsize, FONT_SIZES,
                                                     self.app.settings['treefontsize'])  
        self.settings['docfontsize'] = _combo_value(self.ui.comboBox_docfontsize, FONT_SIZES,
                                                    self.app.settings['docfontsize']) 
        self.settings['directory'] = self.ui.label_directory.text()
        if self.ui.checkBox.isChecked():
            self.settings['showids'] = 'True'
        else:
            self.settings['showids'] = 'False'
        index = self.ui.comboBox_style.currentIndex()
        styles = STYLE_OPTIONS
        if self.settings['stylesheet'] != styles[index]:
            restart_qualcoder = True
        self.settings['stylesheet'] = styles[index]
        selected_language = self.get_selected_language_code()
        if self.settings['language'] != selected_language:
            restart_qualcoder = True
        self.settings['language'] = selected_language
        self.settings['codetext_chunksize'] = _combo_value(self.ui.comboBox_text_chunk_size, CHUNK_SIZES,
                                                           self.app.settings['codetext_chunksize'])  # <- L
        self.settings['timestampformat'] = self.ui.comboBox_timestamp.currentText()
        self.settings['speakernameformat'] = self.ui.comboBox_speaker.currentText()
        if self.ui.checkBox_auto_backup.isChecked():
            self.settings['backup_on_open'] = 'True'
        else:
            self.settings['backup_on_open'] = 'False'
        if self.ui.checkBox_backup_AV_files.isChecked():
            self.settings['backup_av_files'] = 'True'
        else:
            self.settings['backup_av_files'] = 'False'
        self.settings['backup_num'] = _combo_value(self.ui.comboBox_backups, BACKUP_COUNTS,
                                                   self.app.settings['backup_num'])  # <- L
        self.settings['report_text_context_characters'] = _combo_value(
            self.ui.comboBox_surrounding_chars, CONTEXT_CHARS,
            self.app.settings['report_text_context_characters'])  # <- L
        ts_index = self.ui.comboBox_text_style.currentIndex()
        self.settings['report_text_context_style'] = ['Bold', 'Italic', 'Bigger'][ts_index]
        # AI settings
        if self.ui.checkBox_AI_enable.isChecked():
            self.settings['ai_enable'] = 'True'
        else:
            self.settings['ai_enable'] = 'False'
        ai_model_index = self.ui.comboBox_ai_profile.currentIndex() 
        self.settings['ai_model_index'] = ai_model_index
        self.settings['ai_permissions'] = self.current_ai_permissions()
        if self.settings['ai_enable'] == 'True' and ai_model_index < 0:
            msg = _('Please select an AI profile or disable the AI altogether.')
            Message(self.app, _('AI profile'), msg).exec()
            return
        uses_oauth = False
        if 0 <= ai_model_index < len(self.ai_models):
            ensure_chatgpt_oauth_profile_defaults(self.ai_models[ai_model_index])
            uses_oauth = is_chatgpt_oauth_profile(self.ai_models[ai_model_index])
        if self.settings['ai_enable'] == 'True' and (not uses_oauth) and \
                (not self.validate_ai_api_key(self.ui.lineEdit_ai_api_key.text(), focus_field=True)):
            return
        if self.settings['ai_enable'] == 'True' and (not uses_oauth) and self.ai_models[ai_model_index]['api_key'] == '':
            msg = _('Please enter a valid API-key for the AI model.')
            Message(self.app, _('AI model'), msg).exec()
            return
        if self.settings['ai_enable'] == 'True' and (self.ui.comboBox_AI_model_large.currentText() == '' or self.ui.comboBox_AI_model_fast.currentText() == ''):
            self.ui.pushButton_advanced_AI_options.setChecked(True)
            self.toggle_ai_advanced_options()
            msg = _('Please select a "large" and a "fast" AI model.')
            Message(self.app, _('AI model'), msg).exec()
            return
        if self.settings['ai_enable'] == 'True' and not self.validate_ai_temperature():
            return
        if self.settings['ai_enable'] == 'True' and not self.validate_ai_top_p():
            return
        self.settings['ai_language_ui'] = 'True' if self.ui.checkBox_AI_language_ui.isChecked() else 'False'
        self.settings['ai_language'] =  self.ui.lineEdit_AI_language.text()
        self.settings['ai_temperature'] = self.ui.lineEdit_ai_temperature.text()
        self.settings['ai_top_p'] = self.ui.lineEdit_top_p.text()
        
        # if any changes to the coder names have been made, write them to the disk:
        if self.app.conn is not None and self.app.conn.total_changes != self.initial_changes:
            self.coder_names_changes = True
        if self.app.conn is not None:
            self.app.conn.commit()
        self.save_settings()
        if restart_qualcoder:
            Message(self.app, _("Restart QualCoder"), _("Restart QualCoder to enact some changes")).exec()
        super().accept()
        
    def reject(self):
        if self.app.conn is not None and self.app.conn.total_changes != self.initial_changes:
            msg = _('It seems that you have made changes to the coder names. These changes will be lost as well. Do you really want to cancel?')
            msg_box = Message(self.app, _('Settings'), msg, "Information")
            msg_box.setStandardButtons(
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
            msg_box.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Yes)
            reply = msg_box.exec()
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            else: 
                self.app.conn.rollback()
        self.coder_names_changes = False
        super().reject()


    def save_settings(self):
        """ Updates the apps setting with the contents of self.Settings and save 
        it to a text file in user's home directory.
        Each setting has a variable identifier then a colon
        followed by the value. """
        self.app.settings.clear()
        self.app.settings.update(self.settings)
        self.app.write_config_ini(self.settings, self.ai_models)
