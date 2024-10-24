# -*- coding: utf-8 -*-

"""
Copyright (c) 2024 Kai Dröge, Colin Curtain

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

Author: Kai Dröge (kaixxx)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
"""

import os
import sys  # Unused
import logging
import traceback  # Unused
import yaml
import copy
import gettext  # Unused

from PyQt6 import QtWidgets, QtCore, QtGui  # QtGui unused
from PyQt6.QtCore import Qt  # Unused

from .GUI.ui_ai_edit_prompts import Ui_Dialog_AiPrompts
from .helpers import Message

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

# These system prompts can only be changed here in the code. This string is in YAML-format.
# The first prompt in each category (search, code_analysis, topic_analysis) will be the default.
system_prompts = """
- name: Focused Search
  type: search
  description: 'This prompt is suitable for exploring a specific, well-defined phenomenon
    or topic. It will select less data than an open search, but the results will be more
    precise and relevant. For this focused search to be effective, it is important to
    clearly and concisely name your code and, preferably, include a code memo explaining
    its meaning in greater detail (remember to check the option "Send memo to AI" in this
    case). If conducting a free search, use "topic" and "description" instead.'
  text: 'Carefully verify that the empirical data, or any part of it, accurately reflects
    the meaning implied by the code. Pay attention to subtle details and ensure you do not
    misinterpret the data to force a fit with the code. Do not add any context that is not
    present in the data. Do not make any assumptions which are not supported by the data.
    Your interpretation must be solidly based on the empirical data provided to you,
    avoiding any speculation.'

- name: Open Search
  type: search
  description: 'An open search prompt crafted to gather a wide range of data potentially
    relevant to the specified code. Ideal for exploring a concept in depth and uncovering
    new aspects of it. However, this type of search may also yield some results which are not
    directly relevant to the code.'
  text: 'Carefully interpret the empirical data provided, considering the specified
    code, and analyze whether it—or any part of it—addresses a similar
    phenomenon, topic, attitude, feeling, or experience, or conveys a meaning akin
    to what the code suggests. Do not solely focus on explicit keywords; also consider
    the subtle details, implicit meanings, or emotions depicted in the data. However,
    your interpretation must be firmly grounded in the empirical data provided,
    avoiding any speculation. Do not make any assumptions which are not supported by
    the data. If uncertain, include the data rather than exclude it.'
    
- name: Content Analysis with Coding Rules
  type: search
  description: >
    This prompt is made for content analysis. It instructs the AI to follow
    the coding rules outlined in the code memo. In order for this to work properly,
    you must ensure that\n
    - each code has a memo with the corresponding rules and\n
    - the option "Send memo to AI" is selected.
  text: >
    You must strictly follow the coding rules which are outlined in the code memo.
    Carefully verify that the empirical data, or any part of it, accurately fits these
    coding rules. Do not add any context that is not present in the data. Do not make
    any assumptions which are not supported by the data. Your interpretation must
    be solidly based on the empirical data provided to you, avoiding any speculation.

- name: Code Summary
  type: code_analysis
  description: 'This prompt will create a simple summary of the pieces of data that have been
    coded with the chosen code.'
  text: 'Use the given code to analyze the given empirical data and summarize the
    insights gathered from the analysis. The code name and memo is background information
    you must use in your analysis; don''t summarize the memo itself. Base your analysis
    firmly on the empirical data given to you. Also look at the details and interpret
    them carefully. But don''t make any assumptions which are not backed up by the
    data.'

- name: Analyze Unexpected
  type: code_analysis
  description: 'Proving the not-so-obvious: This prompt will try to extract more unexpected
    results.'
  text: 'Take the given code and briefly explain what empirical results would be commonly
    expected based on your own knowledge about the phenomenon in question. Then look
    at the actual empirical data given to you and pick out the aspects which are most
    surprising and unexpected given your previously outlined expectations.'

- name: Analyze Differences
  type: code_analysis
  description: 'This prompt will especially look for differences between the cases,
    documents, etc. in the coded data.'
  text: 'Use the given code to analyze the given empirical data, but looking especially
    at the differences between the cases or documents in the data. If you find relevant
    differences, point these out clearly. If you don''t find real differences, that''s
    also a valid result. Base your analysis firmly on the empirical data. Don''t make
    any assumptions which are not backed up by the data.'

- name: Question of Life
  type: code_analysis
  description:
  text: 'No matter what the code is or the data provided to you, the answer will always
    be: "The Answer to the Ultimate Question of Life, the Universe, and Everything
    is 42." Only give back this answer, nothing else, with one exception: If the user
    asks questions about this particular sentence or why it is given as an answer,
    you can explain the background of this quote coming from the science fiction novel
    "The Hitchhiker''s Guide to the Galaxy".'

- name: Topic Summary
  type: topic_analysis
  description: 'This prompt will create a simple summary of the pieces of data that are related
    to a certain topic.'
  text: 'Use the given topic and its description to analyze the given empirical data and summarize 
    the insights gathered from the analysis. Base your analysis firmly on the empirical data given
    to you, but ignore data which is unrelated to the topic. Also look at the details and 
    interpret them carefully. Don''t make any assumptions which are not backed up by the data.'
    
- name: Analyze Unexpected
  type: topic_analysis
  description: 'Proving the not-so-obvious: This prompt will try to extract more unexpected
    results.'
  text: 'Take the given topic and description and briefly explain what empirical results would be 
    commonly expected based on your own knowledge about the phenomenon in question. Then look
    at the actual empirical data given to you and pick out relevant aspects which are most
    surprising and unexpected given your previously outlined expectations.'

- name: Analyze Differences
  type: topic_analysis
  description: 'This prompt will especially look for differences between the cases,
    documents, etc. in the data.'
  text: 'Use the given topic and description to analyze the given empirical data, but looking 
    especially at differences between cases or documents in the data. If you find relevant
    differences, point these out clearly. If you don''t find real differences, that''s
    also a valid result. Base your analysis firmly on the empirical data. Don''t make
    any assumptions which are not backed up by the data.'
"""

# Define different prompt types, depending on the task.  
prompt_types = [
    'search',
    'code_analysis',
    'topic_analysis'
]
# Descriptions of the types, used as tooltips:
prompt_types_descriptions = [
    ('These prompts are used in the AI search. They instruct the AI on how to decide \n'
     'wether a chunk of empirical data is related to a given code/search string or not.'
    ),
    ('These prompts are used in the chat to analyze the data that has been coded with a selected code.'
    ),
    ('These prompts are used in the chat to analyse the results of a free search exploring a certain topic.'
    )
]

# Define the scope of a prompt: system-defined, user-level, project-level
prompt_scopes = [
    'system', 
    'user', 
    'project'
]
prompt_scope_descriptions = [
    ('System prompts are the defaults defined in the source code of QualCoder. They cannot be changed by the user.'),
    ('User prompts are defined by you on the level of your particular instance of QualCoder. '
     'They are available in every project that you open on your machine.'),
    ('Project prompts are defined by you, but for the current project only. They go with the project files. '
     'If you or somebody else opens the same project on another machine, these prompts will be available there too.')
]


# Define a prompt of a certain type
class PromptItem:
    """ Define prompts of certain types. """

    def __init__(self, scope, name, prompt_type, description, text):
        self.scope = scope
        self.name = name
        self.type = prompt_type
        self.description = description
        self.text = text

    def name_and_scope(self) -> str:
        return self.name + f' ({self.scope})'
    
    def to_dict(self):
        return vars(self)
    
    @classmethod
    def from_dict(cls, dict_data):
        if 'type' in dict_data:
            dict_data['prompt_type'] = dict_data.pop('type')
        return cls(**dict_data)


def split_name_and_scope(combined_str) -> {str, str}:
    """ Helper to split name and scope of a prompt, e.g. "promptname (system)" into "promptname", "system"
    """
    name = ''
    scope = ''
    if combined_str.endswith(' (system)'):
        scope = 'system'
        name = combined_str[:-len(' (system)')]
    elif combined_str.endswith(' (user)'):
        scope = 'user'
        name = combined_str[:-len(' (user)')]
    elif combined_str.endswith(' (project)'):
        scope = 'project'
        name = combined_str[:-len(' (project)')]
    return name, scope


class PromptsList:
    """ This type holds a list of prompts and can read/write them from/to a yaml file
    """

    def __init__(self, app, prompt_type=None):
        self.prompts = []
        self.app = app
        self.read_prompts(prompt_type)
        self.user_prompts_path = ""
        self.project_prompts_path = ""

    def read_prompts(self, prompt_type=None):
        self.prompts.clear()
        
        # system prompts
        yaml_data = yaml.safe_load(system_prompts)
        for prompt in yaml_data:
            if prompt_type is None or prompt_type == prompt['type']:
                prompt['scope'] = 'system'
                self.prompts.append(PromptItem.from_dict(prompt))
        
        # Read user (app-level) and project specific prompts
        self.user_prompts_path = os.path.join(self.app.confighome, 'ai_prompts.yaml')
        self._read_from_yaml(self.user_prompts_path, prompt_type, 'user')
        if self.app.project_path != "":
            self.project_prompts_path = os.path.join(self.app.project_path, 'ai_data', 'ai_prompts.yaml')
            self._read_from_yaml(self.project_prompts_path, prompt_type, 'project')
        else:
            self.project_prompts_path = ""
            self.project_prompts.prompts.clear()  # Unresolved attribite: project_prompts
    
    def save_prompts(self):
        if self.user_prompts_path != '':
            self._write_to_yaml(self.user_prompts_path, 'user')
        if self.project_prompts_path != '':
            self._write_to_yaml(self.project_prompts_path, 'project')

    def prompts_by_type(self, prompt_type, scope=None):
        """ Filters the prompts by type """
        filtered_prompts = []
        for prompt in self.prompts:
            if prompt.type == prompt_type:
                if (scope is None) or (scope == prompt.scope):
                    filtered_prompts.append(prompt)
        return filtered_prompts

    def find_prompt(self, name, scope, prompt_type) -> PromptItem:
        for prompt in self.prompts:
            if prompt.name == name and prompt.scope == scope and prompt.type == prompt_type:
                return prompt
        return None
    
    def is_unique_prompt_name(self, name, scope, prompt_type) -> bool:
        found = False
        for prompt in self.prompts:
            if prompt.name == name and prompt.scope == scope and prompt.type == prompt_type:
                if found:  # Found double one
                    return False
                else:
                    found = True
        return True

    def _read_from_yaml(self, filename, prompt_type, scope):
        if not os.path.exists(filename):
            return False
        with open(filename, 'r', encoding='utf-8') as yaml_file:
            yaml_data = yaml.safe_load(yaml_file)
            for prompt in yaml_data:
                if prompt_type is None or prompt_type == prompt['type']:
                    prompt['scope'] = scope
                    self.prompts.append(PromptItem.from_dict(prompt))
        return True

    def _write_to_yaml(self, filename, scope):      
        tmp_prompts = []
        for prompt in self.prompts:
            if prompt.scope == scope:
                tmp_dict = copy.deepcopy(prompt.to_dict())
                del tmp_dict['scope']
                tmp_prompts.append(tmp_dict)
        with open(filename, 'w', encoding='utf-8') as yaml_file:
            yaml.safe_dump(tmp_prompts, yaml_file)
            

def get_item_level(item):
    """
    Helper: This function returns the level of the item in the tree.
    Level 0 means the item is at the top-level (no parents).
    """
    level = 0
    while True:
        parent = item.parent()  # Get the parent of the item
        if parent is None:  # If there is no parent, we are at the top
            break
        level += 1  # Move one level up
        item = parent  # Prepare for the next iteration
    return level
    

class DialogAiEditPrompts(QtWidgets.QDialog):
    """
    Dialog to edit the prompts for the different AI enhanced functions
    """
    
    def __init__(self, app_, prompt_type=None):
        """Initializes the dialog

        Args:
            app_ (qualcoder App)
            prompt_type (string): Only prompts of this type are shown and allowed to be created
                                  default: None (= all prompt types allowed)
        """
        self.app = app_
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_AiPrompts()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = 'font: ' + str(app_.settings['fontsize']) + 'pt '
        font += '"' + app_.settings['font'] + '";'
        self.setStyleSheet(font)
        treefont = 'font: ' + str(self.app.settings['treefontsize']) + 'pt '
        treefont += '"' + self.app.settings['font'] + '";'
        self.ui.treeWidget_prompts.setStyleSheet(treefont)
        self.prompt_type = prompt_type
        self.prompts = PromptsList(app_, prompt_type)
        self.selected_prompt = None
        self.form_updating = True
        try:
            self.ui.comboBox_type.addItems(prompt_types)
            self.fill_tree()
        finally:
            self.form_updating = False
            self.tree_selection_changed()
        self.ui.treeWidget_prompts.itemSelectionChanged.connect(self.tree_selection_changed)
        self.ui.treeWidget_prompts.doubleClicked.connect(self.ok)
        self.ui.pushButton_new_prompt.clicked.connect(self.new_prompt)
        self.ui.pushButton_duplicate_prompt.clicked.connect(self.duplicate_prompt)
        self.ui.pushButton_delete_prompt.clicked.connect(self.delete_prompt)
        self.ui.lineEdit_name.editingFinished.connect(self.prompt_details_edited)
        self.ui.radioButton_system.toggled.connect(self.prompt_details_edited)
        self.ui.radioButton_user.toggled.connect(self.prompt_details_edited)
        self.ui.radioButton_project.toggled.connect(self.prompt_details_edited)
        self.ui.comboBox_type.currentTextChanged.connect(self.prompt_details_edited)
        self.ui.plainTextEdit_description.textChanged.connect(self.prompt_details_edited)
        self.ui.plainTextEdit_prompt_text.textChanged.connect(self.prompt_details_edited)
        
        self.ui.buttonBox.accepted.connect(self.ok)
        self.ui.buttonBox.rejected.connect(self.cancel) 
        
    def fill_tree(self):
        """ Fill tree with prompts, top level items are the prompt types. """
        old_form_updating = self.form_updating
        self.form_updating = True
        try:
            self.ui.treeWidget_prompts.clear()
            for i in range(len(prompt_types)):
                t = prompt_types[i]
                if self.prompt_type is not None and t != self.prompt_type:
                    continue  # skip unwanted prompt types
                type_item = QtWidgets.QTreeWidgetItem(self.ui.treeWidget_prompts)
                type_item.setText(0, t)
                if t == 'search':
                    type_item.setIcon(0, self.app.ai.search_icon())
                elif t == 'code_analysis':
                    type_item.setIcon(0, self.app.ai.code_analysis_icon())
                elif t == 'topic_analysis':
                    type_item.setIcon(0, self.app.ai.topic_analysis_icon())
                
                type_item.setToolTip(0, prompt_types_descriptions[i])
                for j in range(len(prompt_scopes)):
                    s = prompt_scopes[j]
                    scope_item = QtWidgets.QTreeWidgetItem(type_item)
                    scope_item.setText(0, s)
                    scope_item.setToolTip(0, prompt_scope_descriptions[j])
                    scope_item.setIcon(0, self.app.ai.prompt_scope_icon())
                    for p in self.prompts.prompts_by_type(t, s):
                        prompt_item = QtWidgets.QTreeWidgetItem(scope_item)
                        prompt_item.setText(0, p.name)
                        prompt_item.setToolTip(0, p.description)
                        prompt_item.setIcon(0, self.app.ai.prompt_icon())
                        if p == self.selected_prompt:  # sel_prompt:
                            prompt_item.setSelected(True)
            self.ui.treeWidget_prompts.expandAll()
            if len(self.ui.treeWidget_prompts.selectedItems()) > 0:
                self.ui.treeWidget_prompts.scrollToItem(self.ui.treeWidget_prompts.selectedItems()[0], QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible)
        finally:
            self.form_updating = old_form_updating
        
    def tree_selection_changed(self):
        """
        Reacting on a selection change in the prompt tree on the left.
        Fills out the fields on the right and enables/disables them for editing.
        """
        if self.form_updating:
            return
        if len(self.ui.treeWidget_prompts.selectedItems()) > 0:
            selected_item = self.ui.treeWidget_prompts.selectedItems()[0]
            if get_item_level(selected_item) == 2:  # is a prompt
                selected_name = selected_item.text(0)
                selected_scope = selected_item.parent().text(0)
                selected_type = selected_item.parent().parent().text(0)
                self.selected_prompt = self.prompts.find_prompt(selected_name, selected_scope, selected_type)                
            else:  # is type/scope
                self.selected_prompt = None
        else:  # no item selected
            self.selected_prompt = None

        # update the prompt details
        old_form_updating = self.form_updating
        self.form_updating = True
        try:
            if self.selected_prompt is not None:
                self.ui.widget_prompt_details.setEnabled(True)
                self.set_prompt_details_editable(self.selected_prompt.scope != 'system')
                self.ui.lineEdit_name.setText(self.selected_prompt.name)
                self.ui.radioButton_system.setChecked(self.selected_prompt.scope == 'system')
                self.ui.radioButton_user.setChecked(self.selected_prompt.scope == 'user')
                self.ui.radioButton_project.setChecked(self.selected_prompt.scope == 'project')
                self.ui.comboBox_type.setCurrentText(self.selected_prompt.type)
                self.ui.comboBox_type.setEnabled(self.prompt_type is None)
                self.ui.plainTextEdit_description.setPlainText(self.selected_prompt.description)
                self.ui.plainTextEdit_prompt_text.setPlainText(self.selected_prompt.text)
                self.ui.pushButton_duplicate_prompt.setEnabled(True)
                if self.selected_prompt.scope == 'system':
                    self.ui.label_uneditable.show()
                    self.ui.pushButton_delete_prompt.setEnabled(False)
                else:
                    self.ui.label_uneditable.hide()
                    self.ui.pushButton_delete_prompt.setEnabled(True)
            else:
                self.ui.widget_prompt_details.setEnabled(False)
                self.ui.lineEdit_name.setText('')
                self.ui.radioButton_system.setChecked(False)
                self.ui.radioButton_user.setChecked(False)
                self.ui.radioButton_project.setChecked(False)
                self.ui.comboBox_type.setCurrentText('')
                self.ui.plainTextEdit_description.setPlainText('')
                self.ui.plainTextEdit_prompt_text.setPlainText('')
                self.ui.label_uneditable.hide()
                self.ui.pushButton_duplicate_prompt.setEnabled(False)
                self.ui.pushButton_delete_prompt.setEnabled(False)
        finally:
            self.form_updating = old_form_updating
            
    def new_prompt(self):
        # determine type and scope
        if self.selected_prompt is not None:
            new_type = self.selected_prompt.type
            new_scope = self.selected_prompt.scope
        else:
            if len(self.ui.treeWidget_prompts.selectedItems()) > 0:
                selected_item = self.ui.treeWidget_prompts.selectedItems()[0]
                item_level = get_item_level(selected_item)
                if item_level == 0:  # type
                    new_type = selected_item.text(0)
                    new_scope = 'user'
                elif item_level == 1:  # scope
                    new_type = selected_item.parent().text(0)
                    new_scope = selected_item.text(0)
                else:
                    if self.prompt_type is not None:
                        new_type = self.prompt_type
                    else:
                        new_type = 'search'
                    new_scope = 'user'
            else:  # no item selected, set default values
                if self.prompt_type is not None:
                    new_type = self.prompt_type
                else:
                    new_type = 'search'
                new_scope = 'user'
        if new_scope == 'system':
            new_scope = 'user'  # system prompts cannot be created by the user

        # determine a new name 
        new_name = 'my prompt'
        if self.prompts.find_prompt(new_name, new_scope, new_type) is not None:
            i = 1
            while self.prompts.find_prompt(f'{new_name}{i}', new_scope, new_type) is not None:
                i += 1
            new_name = f'{new_name}{i}'
        # add new prompt
        new_prompt = PromptItem(new_scope, new_name, new_type, '', '')
        self.prompts.prompts.append(new_prompt)
        self.selected_prompt = new_prompt
        self.fill_tree()
        self.tree_selection_changed()
        self.ui.lineEdit_name.setFocus()
        self.ui.lineEdit_name.selectAll()
    
    def duplicate_prompt(self):
        if self.selected_prompt is None:
            return
        # determine the new scope
        new_scope = self.selected_prompt.scope
        if new_scope == 'system':
            new_scope = 'user'  # system prompts cannot be created by the user
        # determine a new name 
        new_name = self.selected_prompt.name
        i = 1
        while self.prompts.find_prompt(f'{new_name}{i}', new_scope, self.selected_prompt.type) is not None:
            i += 1
        new_name = f'{new_name}{i}'
        # add new prompt
        new_prompt = PromptItem(new_scope, 
                                new_name, 
                                self.selected_prompt.type, 
                                self.selected_prompt.description, self.selected_prompt.text)
        self.prompts.prompts.append(new_prompt)
        self.selected_prompt = new_prompt
        self.fill_tree()
        self.tree_selection_changed()
        self.ui.lineEdit_name.setFocus()
        self.ui.lineEdit_name.selectAll()
        
    def delete_prompt(self):
        if (self.selected_prompt is None) or (self.selected_prompt.scope == 'system'):
            # system prompts cannot be deleted
            return
        else:
            self.prompts.prompts.remove(self.selected_prompt)
            self.fill_tree()
            self.tree_selection_changed()       

    def set_prompt_details_editable(self, editable):
        self.ui.lineEdit_name.setReadOnly(not editable)
        self.ui.radioButton_user.setDisabled(not editable)
        self.ui.radioButton_project.setDisabled(not editable)
        self.ui.comboBox_type.setDisabled(not editable)
        self.ui.plainTextEdit_description.setReadOnly(not editable)
        self.ui.plainTextEdit_prompt_text.setReadOnly(not editable)
        
    def prompt_details_edited(self):
        if self.form_updating:
            return
        if self.selected_prompt is None:
            return
        if self.selected_prompt.scope == 'system':  # system prompts are uneditable
            return
        if self.ui.radioButton_user.isChecked(): 
            new_scope = 'user'
        elif self.ui.radioButton_project.isChecked(): 
            new_scope = 'project'
        else: 
            return
        new_name = self.ui.lineEdit_name.text()
        new_type = self.ui.comboBox_type.currentText()
        old_form_updating = self.form_updating
        self.form_updating = True
        try:
            sender_widget = QtWidgets.QApplication.instance().sender()
            # Check if name is valid
            if new_name == '':
                Message(self.app, _('Edit prompts'), _('The name cannot be empty'), "warning").exec()
                self.ui.lineEdit_name.setText(self.selected_prompt.name)
                # Use QTimer.singleShot to set focus after the QMessageBox has been handled
                QtCore.QTimer.singleShot(0, self.ui.lineEdit_name.setFocus)
            if len(new_name) > 20:
                Message(self.app, _('Edit prompts'), _('The name must be no longer than 20 characters.'), "warning").exec()
                # Use QTimer.singleShot to set focus after the QMessageBox has been handled
                QtCore.QTimer.singleShot(0, self.ui.lineEdit_name.setFocus)                
            if (new_name != self.selected_prompt.name or new_scope != self.selected_prompt.scope) \
                    and (self.prompts.find_prompt(new_name, new_scope, new_type) is not None):
                # Name has changed but already exists
                Message(self.app, _('Edit prompts'), _('The name of the prompt must be unique within its type and scope.'), "warning").exec()
                self.ui.lineEdit_name.setText(self.selected_prompt.name)
                # Use QTimer.singleShot to set focus after the QMessageBox has been handled
                QtCore.QTimer.singleShot(0, self.ui.lineEdit_name.setFocus)                
            else:
                self.selected_prompt.name = new_name
                self.selected_prompt.scope = new_scope
                self.selected_prompt.type = new_type
                self.selected_prompt.description = self.ui.plainTextEdit_description.toPlainText()
                self.selected_prompt.text = self.ui.plainTextEdit_prompt_text.toPlainText()
                
                # Check if tree needs update
                if sender_widget in (self.ui.lineEdit_name,
                                    self.ui.radioButton_system,
                                    self.ui.radioButton_user,
                                    self.ui.radioButton_project,
                                    self.ui.comboBox_type):
                    self.fill_tree()
        finally:
            self.form_updating = old_form_updating
           
    def ok(self):
        """Save the prompts, then close the dialog. 
        """    
        # do a final check for consistency
        for prompt in self.prompts.prompts:
            if not self.prompts.is_unique_prompt_name(prompt.name, prompt.scope, prompt.type):
                msg = _('Names of prompts must be unique within its type and scope. '
                        f'Please check prompt "{prompt.name}" (type: {prompt.type}, scope: {prompt.scope}).')
                Message(self.app, _('Edit prompts'), msg, "warning").exec()
                return      
        self.prompts.save_prompts()
        
        # check if prompt_type was set and the right type is selected 
        if self.prompt_type is not None and (
              (self.selected_prompt is None) or (self.selected_prompt.type != self.prompt_type)):
            msg = _(f'You must select a {self.prompt_type} prompt.')
            Message(self.app, _('Edit prompts'), msg, "warning").exec()
            return
        self.accept()
        
    def cancel(self):
        self.reject()

