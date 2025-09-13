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
https://qualcoder.wordpress.com/
"""

import logging
import os
from PyQt6 import QtGui, QtWidgets, QtCore
import copy
import re

from .GUI.ui_dialog_settings import Ui_Dialog_settings
from .helpers import Message
from .ai_llm import get_available_models

home = os.path.expanduser('~')
path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogSettings(QtWidgets.QDialog):
    """ Settings for the coder name, coder table and to display ids. """

    settings = {}
    current_coder = "default"

    def __init__(self, app, parent=None, section=None, enable_ai=False):

        self.app = app
        self.settings = app.settings
        self.ai_models = copy.deepcopy(self.app.ai_models)
        self.current_coder = self.app.settings['codername']
        super(QtWidgets.QDialog, self).__init__(parent)  # overrride accept method
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_settings()
        self.ui.setupUi(self)
        font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(font)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        new_font = QtGui.QFont(self.settings['font'], self.settings['fontsize'], QtGui.QFont.Weight.Normal)
        self.ui.label_current_coder.setText(_("Current coder: ") + self.app.settings['codername'])
        self.ui.fontComboBox.setCurrentFont(new_font)
        # Get coder names from all tables
        sql = "select owner from code_image union select owner from code_text union select owner from code_av "
        sql += "union select owner from code_name union select owner from code_cat "
        sql += "union select owner from cases union select owner from case_text "
        sql += "union select owner from attribute union select owner from attribute_type "
        sql += "union select owner from source union select owner from annotation union select owner from journal "
        sql += "union select owner from manage_files_display union select owner from files_filter"
        coders = [""]
        if self.app.conn is not None:
            cur = self.app.conn.cursor()
            cur.execute(sql)
            results = cur.fetchall()
            for row in results:
                if row[0] != "":
                    coders.append(row[0])
        self.ui.comboBox_coders.addItems(coders)
        languages = ["Deutsch de", "English en", "Español es", "Français fr",
                     "Italiano it", "日本語 ja", "Português pt", "Svenska sv", "中国人 zh"]
        self.ui.comboBox_language.addItems(languages)
        for index, lang in enumerate(languages):
            if lang[-2:] == self.settings['language']:
                self.ui.comboBox_language.setCurrentIndex(index)
        timestampformats = ["[mm.ss]", "[mm:ss]", "[hh.mm.ss]", "[hh:mm:ss]",
                            "{hh:mm:ss}", "#hh:mm:ss.sss#"]
        self.ui.comboBox_timestamp.addItems(timestampformats)
        for index, ts in enumerate(timestampformats):
            if ts == self.settings['timestampformat']:
                self.ui.comboBox_timestamp.setCurrentIndex(index)
        speakernameformats = ["[]", "{}"]
        self.ui.comboBox_speaker.addItems(speakernameformats)
        for index, snf in enumerate(speakernameformats):
            if snf == self.settings['speakernameformat']:
                self.ui.comboBox_speaker.setCurrentIndex(index)
        index = self.ui.comboBox_fontsize.findText(str(self.settings['fontsize']),
                                                          QtCore.Qt.MatchFlag.MatchFixedString)
        if index == -1:
            index = 0
        self.ui.comboBox_fontsize.setCurrentIndex(index)
        index = self.ui.comboBox_codetreefontsize.findText(str(self.settings['treefontsize']),
                                                          QtCore.Qt.MatchFlag.MatchFixedString)
        if index == -1:
            index = 0
        self.ui.comboBox_codetreefontsize.setCurrentIndex(index)

        index = self.ui.comboBox_docfontsize.findText(str(self.settings['docfontsize']),
                                                          QtCore.Qt.MatchFlag.MatchFixedString)
        if index == -1:
            index = 0
        self.ui.comboBox_docfontsize.setCurrentIndex(index)

        self.ui.comboBox_coders.currentIndexChanged.connect(self.combobox_coder_changed)
        index = self.ui.comboBox_text_chunk_size.findText(str(self.settings['codetext_chunksize']),
                                                          QtCore.Qt.MatchFlag.MatchFixedString)
        if index == -1:
            index = 0
        self.ui.comboBox_text_chunk_size.setCurrentIndex(index)
        self.ui.checkBox_auto_backup.stateChanged.connect(self.backup_state_changed)
        if self.settings['showids'] == 'True':
            self.ui.checkBox.setChecked(True)
        else:
            self.ui.checkBox.setChecked(False)
        styles = ["original", "dark", "blue", "green", "orange", "purple", "yellow", "rainbow", "native"]
        styles_translated = [_("original"), _("dark"), _("blue"), _("green"), _("orange"), _("purple"), _("yellow"), _("rainbow"), _("native")]
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

        index = self.ui.comboBox_backups.findText(str(self.settings['backup_num']),
                                                      QtCore.Qt.MatchFlag.MatchFixedString)
        if index == -1:
            index = 0
        self.ui.comboBox_backups.setCurrentIndex(index)

        if self.settings['directory'] == "":
            self.settings['directory'] = os.path.expanduser("~")
        self.ui.label_directory.setText(self.settings['directory'])
        text_styles = [_('Bold'), _('Italic'), _('Bigger')]
        self.ui.comboBox_text_style.addItems(text_styles)
        for index, text_style in enumerate(text_styles):
            if text_style == self.settings['report_text_context_style']:
                self.ui.comboBox_text_style.setCurrentIndex(index)

        index = self.ui.comboBox_surrounding_chars.findText(str(self.settings['report_text_context_characters']),
                                                      QtCore.Qt.MatchFlag.MatchFixedString)
        if index == -1:
            index = 0
        self.ui.comboBox_surrounding_chars.setCurrentIndex(index)
        msg = _("Default folder for storing automatic backups and for file outputs.")
        self.ui.pushButton_choose_directory.setToolTip(msg)
        self.ui.pushButton_choose_directory.clicked.connect(self.choose_directory)
        self.ui.pushButton_set_coder.pressed.connect(self.new_coder_entered)

        # AI options
        if enable_ai or self.settings['ai_enable'] == 'True':
            self.ui.checkBox_AI_enable.setChecked(True)
        else:
            self.ui.checkBox_AI_enable.setChecked(False)
        self.ui.checkBox_AI_enable.stateChanged.connect(self.ai_enable_state_changed)
        self.ui.comboBox_ai_profile.clear()
        if len(self.ai_models) > 0:
            for i in range(len(self.ai_models)):
                model = self.ai_models[i]
                self.ui.comboBox_ai_profile.addItem(model['name'])
                self.ui.comboBox_ai_profile.setItemData(i, model['desc'], QtCore.Qt.ItemDataRole.ToolTipRole)
            if 0 <= int(self.settings['ai_model_index']) <= (len(self.ai_models) - 1): 
                self.ui.comboBox_ai_profile.setCurrentIndex(int(self.settings['ai_model_index']))
            else: # ai_model_index out of range
                self.settings['ai_model_index'] = 0
                self.ui.comboBox_ai_profile.setCurrentIndex(0)
        else: # no ai profiles defined
            self.settings['ai_model_index'] = -1
        self.ui.comboBox_ai_profile.currentIndexChanged.connect(self.ai_profile_changed)
        self.ai_profile_changed()
        self.ai_enable_state_changed()
        self.ui.pushButton_ai_profile_edit.clicked.connect(self.ai_profile_name_edit)
        self.ui.lineEdit_ai_api_key.textChanged.connect(self.ai_api_key_changed)
        # advanced AI options:
        self.ui.pushButton_advanced_AI_options.clicked.connect(self.toggle_ai_advanced_options)
        self.toggle_ai_advanced_options() # hide the advanced AI options panel
        int_validator = QtGui.QIntValidator(self)
        int_validator.setBottom(0)
        self.ui.lineEdit_ai_large_context_window.setValidator(int_validator)
        self.ui.lineEdit_ai_fast_context_window.setValidator(int_validator)
        self.ui.lineEdit_ai_large_context_window.textChanged.connect(self.ai_model_parameters_changed)
        self.ui.lineEdit_ai_fast_context_window.textChanged.connect(self.ai_model_parameters_changed)
        self.ui.comboBox_AI_model_large.currentTextChanged.connect(self.ai_model_parameters_changed)
        self.ui.comboBox_AI_model_fast.currentTextChanged.connect(self.ai_model_parameters_changed)
        self.ui.comboBox_AI_model_large.view().setMinimumWidth(500)  # Set a minimum width for the dropdown list
        self.ui.comboBox_AI_model_fast.view().setMinimumWidth(500)
        self.ui.checkBox_ai_project_memo.setChecked(self.settings.get('ai_send_project_memo', 'True') == 'True')
        self.ui.checkBox_AI_language_ui.setChecked(self.settings.get('ai_language_ui', 'True') == 'True')
        self.ui.checkBox_AI_language_ui.stateChanged.connect(self.ai_language_ui_changed)
        self.ui.lineEdit_AI_language.setText(self.settings.get('ai_language', ''))
        self.ui.lineEdit_AI_language.setEnabled(not self.ui.checkBox_AI_language_ui.isChecked())
        self.ui.lineEdit_ai_temperature.setText(self.settings.get('ai_temperature', '1.0'))
        self.ui.lineEdit_ai_temperature.editingFinished.connect(self.validate_ai_temperature)
        self.ui.lineEdit_top_p.setText(self.settings.get('ai_top_p', '1.0'))
        self.ui.lineEdit_top_p.editingFinished.connect(self.validate_ai_top_p)
        
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

    def backup_state_changed(self):
        """ Enable and disable av backup checkbox. Only enable when checkBox_auto_backup is checked. """

        if self.ui.checkBox_auto_backup.isChecked():
            self.ui.checkBox_backup_AV_files.setEnabled(True)
        else:
            self.ui.checkBox_backup_AV_files.setEnabled(False)
    
    def ai_enable_state_changed(self):
        self.ui.comboBox_ai_profile.setEnabled(self.ui.checkBox_AI_enable.isChecked())
        self.ui.label_ai_model_desc.setEnabled(self.ui.checkBox_AI_enable.isChecked())
        self.ui.label_ai_access_info_url.setEnabled(self.ui.checkBox_AI_enable.isChecked())
        self.ui.lineEdit_ai_api_key.setEnabled(self.ui.checkBox_AI_enable.isChecked())
        self.ui.checkBox_ai_project_memo.setEnabled(self.ui.checkBox_AI_enable.isChecked())
        self.ui.lineEdit_ai_temperature.setEnabled(self.ui.checkBox_AI_enable.isChecked())
        self.ui.lineEdit_top_p.setEnabled(self.ui.checkBox_AI_enable.isChecked())
        self.ui.checkBox_AI_language_ui.setEnabled(self.ui.checkBox_AI_enable.isChecked())
        self.ui.lineEdit_AI_language.setEnabled(self.ui.checkBox_AI_enable.isChecked() and (not self.ui.checkBox_AI_language_ui.isChecked()))
    
    def ai_profile_changed(self):
        self.settings['ai_model_index'] = self.ui.comboBox_ai_profile.currentIndex()
        if int(self.settings['ai_model_index']) >= 0:
            curr_ai_model = self.ai_models[int(self.settings['ai_model_index'])]
            self.ui.label_ai_model_desc.setText(curr_ai_model['desc'])
            self.ui.label_ai_access_info_url.setText(f'<a href="{curr_ai_model["access_info_url"]}">{curr_ai_model["access_info_url"]}</a>')
            with QtCore.QSignalBlocker(self.ui.lineEdit_ai_api_key): # prevents ai_update_avaliable_models() to trigger
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
        else:
            self.ui.label_ai_model_desc.setText('')
            self.ui.label_ai_access_info_url.setText('')
            with QtCore.QSignalBlocker(self.ui.lineEdit_ai_api_key): # prevents ai_update_avaliable_models() to trigger
                self.ui.lineEdit_ai_api_key.setText('')
            self.ui.comboBox_AI_model_large.setCurrentText('')
            self.ui.comboBox_AI_model_fast.setCurrentText('')
            self.ui.lineEdit_ai_large_context_window.setText('')
            self.ui.lineEdit_ai_fast_context_window.setText('')            
        self.ai_update_avaliable_models()     
        
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

    def ai_api_key_changed(self):
        if int(self.settings['ai_model_index']) >= 0:
            self.ai_models[int(self.settings['ai_model_index'])]['api_key'] = self.ui.lineEdit_ai_api_key.text()   
        self.ai_update_avaliable_models()     

    def ai_update_avaliable_models(self):
        if not self.ui.widget_AI_advanced_options.isVisible():
            return
        model_list = []
        if int(self.settings['ai_model_index']) >= 0:
            try:
                model_list = get_available_models(self.ai_models[int(self.settings['ai_model_index'])]['api_base'], 
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
                
    def validate_ai_temperature(self):
        text = self.ui.lineEdit_ai_temperature.text()
        # Check if the input text is numeric
        if not text:
            return
        value = float(text)
        if not (0.0 <= value <= 2.0):
            Message.warning(self, "Invalid input", "AI temperature parameter must be between 0.0 and 2.0.")
            self.ui.lineEdit_ai_temperature.setFocus()
            self.ui.lineEdit_ai_temperature.selectAll()
            
    def validate_ai_top_p(self):
        text = self.ui.lineEdit_top_p.text()
        # Check if the input text is numeric
        if not text:
            return
        value = float(text)
        if not (0.0 <= value <= 1.0):
            Message.warning(self, "Invalid input", "AI top_p parameter must be between 0.0 and 1.0.")
            self.ui.lineEdit_top_p.setFocus()
            self.ui.lineEdit_top_p.selectAll()
            
    def new_coder_entered(self):
        """ New coder name entered.
        Tried to disable Enter key or catch the event. Failed. So new coder name assigned
        when the pushButton_set_coder is activated. """

        new_coder = self.ui.lineEdit_coderName.text()
        if new_coder == "":
            return
        self.ui.lineEdit_coderName.setEnabled(False)
        self.current_coder = new_coder
        self.ui.label_current_coder.setText(_("Current coder: ") + self.current_coder)

    def combobox_coder_changed(self):
        """ Set the coder name to the current selection. """

        current_selection = self.ui.comboBox_coders.currentText()
        if current_selection == "":
            return
        self.current_coder = current_selection
        self.ui.label_current_coder.setText(_("Current coder: ") + self.current_coder)

    def choose_directory(self):
        """ Choose default project directory. """

        directory = QtWidgets.QFileDialog.getExistingDirectory(self,
            _('Choose project directory'), self.settings['directory'])
        if directory == "":
            return
        self.ui.label_directory.setText(directory)
        
    def toggle_ai_advanced_options(self):
        if self.ui.pushButton_advanced_AI_options.isChecked():
            self.ui.widget_AI_advanced_options.show()
            self.ai_update_avaliable_models()
            QtCore.QTimer.singleShot(100, lambda: self.ui.scrollArea.verticalScrollBar().setValue(self.ui.scrollArea.verticalScrollBar().maximum()))
        else:
            self.ui.widget_AI_advanced_options.hide()

    def accept(self):
        restart_qualcoder = False
        self.settings['codername'] = self.current_coder
        if self.settings['codername'] == "":
            self.settings['codername'] = "default"
        if self.app.conn is not None:
            # None if no project opened
            cur = self.app.conn.cursor()
            cur.execute('update project set codername=?', [self.settings['codername']])
            self.app.conn.commit()
        self.settings['font'] = self.ui.fontComboBox.currentText()
        self.settings['fontsize'] = int(self.ui.comboBox_fontsize.currentText())
        self.settings['treefontsize'] = int(self.ui.comboBox_codetreefontsize.currentText())
        self.settings['docfontsize'] = int(self.ui.comboBox_docfontsize.currentText())
        self.settings['directory'] = self.ui.label_directory.text()
        if self.ui.checkBox.isChecked():
            self.settings['showids'] = 'True'
        else:
            self.settings['showids'] = 'False'
        index = self.ui.comboBox_style.currentIndex()
        styles = ["original", "dark", "blue", "green", "orange", "purple", "yellow", "rainbow", "native"]
        if self.settings['stylesheet'] != styles[index]:
            restart_qualcoder = True
        self.settings['stylesheet'] = styles[index]
        if self.settings['language'] != self.ui.comboBox_language.currentText()[-2:]:
            restart_qualcoder = True
        self.settings['language'] = self.ui.comboBox_language.currentText()[-2:]
        self.settings['codetext_chunksize'] = int(self.ui.comboBox_text_chunk_size.currentText())
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
        self.settings['backup_num'] = int(self.ui.comboBox_backups.currentText())
        self.settings['report_text_context_characters'] = int(self.ui.comboBox_surrounding_chars.currentText())
        ts_index = self.ui.comboBox_text_style.currentIndex()
        self.settings['report_text_context_style'] = ['Bold', 'Italic', 'Bigger'][ts_index]
        # AI settings
        if self.ui.checkBox_AI_enable.isChecked():
            self.settings['ai_enable'] = 'True'
        else:
            self.settings['ai_enable'] = 'False'
        ai_model_index = self.ui.comboBox_ai_profile.currentIndex() 
        self.settings['ai_model_index'] = ai_model_index
        if self.settings['ai_enable'] == 'True' and ai_model_index < 0:
            msg = _('Please select an AI profile or disable the AI altogether.')
            Message(self.app, _('AI profile'), msg).exec()
            return
        if self.settings['ai_enable'] == 'True' and self.ai_models[ai_model_index]['api_key'] == '':
            msg = _('Please enter a valid API-key for the AI model.')
            Message(self.app, _('AI model'), msg).exec()
            return
        if self.settings['ai_enable'] == 'True' and (self.ui.comboBox_AI_model_large.currentText() == '' or self.ui.comboBox_AI_model_fast.currentText() == ''):
            self.ui.pushButton_advanced_AI_options.setChecked(True)
            self.toggle_ai_advanced_options()
            msg = _('Please select a "large" and a "fast" AI model.')
            Message(self.app, _('AI model'), msg).exec()
            return
        if self.ui.checkBox_ai_project_memo.isChecked():
            self.settings['ai_send_project_memo'] = 'True'
        else: 
            self.settings['ai_send_project_memo'] = 'False'
        self.settings['ai_language_ui'] = 'True' if self.ui.checkBox_AI_language_ui.isChecked() else 'False'
        self.settings['ai_language'] =  self.ui.lineEdit_AI_language.text()
        self.settings['ai_temperature'] = self.ui.lineEdit_ai_temperature.text()
        self.settings['ai_top_p'] = self.ui.lineEdit_top_p.text()
        self.save_settings()
        if restart_qualcoder:
            Message(self.app, _("Restart QualCoder"), _("Restart QualCoder to enact some changes")).exec()
        super().accept()

    def save_settings(self):
        """ Save settings to text file in user's home directory.
        Each setting has a variable identifier then a colon
        followed by the value. """

        self.app.write_config_ini(self.settings, self.ai_models)
