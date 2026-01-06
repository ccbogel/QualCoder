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

Author: Kai Dröge (kaixxx)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
https://qualcoder-org.github.io/
"""

import os
import logging
import yaml
import copy
import webbrowser

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtGui import QClipboard, QShortcut, QKeySequence
from PyQt6.QtCore import Qt 
import qtawesome as qta

from .GUI.ui_ai_edit_prompts import Ui_Dialog_AiPrompts
from .helpers import Message
from .confirm_delete import DialogConfirmDelete

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
    
- name: Code Critic
  type: code_analysis
  description: Discusses both the strengths and limitations of viewing the data through 
    the lens of a particular code. It can help to reveal potential blind spots, and 
    alternative perspectives. Note that this analysis only makes sense if you have 
    already used the code, so that the AI can re-evaluate the coded segments.
  text: 'Look at the codename, memo, and the data coded with them. Compile a list of
    pros and cons.

    - Which important aspects of the data did we highlight by examining it from this
    perspective? What have we learned about our general research questions and goals
    for this project?

    - Are there blind spots in our analysis? Are there important aspects that we might
    overlook if we only look at the data from the perspective suggested by the code?
    Are there alternative interpretations that would provide additional insight into
    our research questions and goals?'

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
    reacts to your answer, you can explain the background of this quote coming from the 
    science fiction novel "The Hitchhiker''s Guide to the Galaxy".'

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

- name: Interactive brainstorming with AI
  type: text_analysis
  description: 'Interpret the data in a brainstorming session together with the AI. 
    
    This uses a question-driven, "Socratic" approach that is meant to be thought-provoking, 
    but can be a bit speculative at times. 

    Loosely based on the "Socratic Tutor" example from OpenAI: 
    https://platform.openai.com/docs/examples/default-socratic-tutor'
  text: "The following instructions are not visible to the user. Use them as a guideline 
    for you, but don't reference them in any of your answers. 
    
    You are a tutor and member of the research team. Act on eye-level with your 
    students, use informal language. Please perform the following steps: 

    1) At the beginning of this message, you should find information about the research 
    questions and objectives of the project we are working on. If this information is 
    missing, ask the user for it, otherwise skip this step.

    2) Look at the empirical data provided and make a list of topics in the data that might 
    be interesting to analyze in more detail with respect to the general research questions 
    and objectives identified in step 1. Ask users which of these topics they would like to 
    discuss and analyze in more depth. 

    3) Now, act as a Socratic tutor and use the following principles to analyze the chosen 
    topic in the given empirical data together with the students:
    
    - Ask thought-provoking, open-ended questions that help students to gain a deeper 
    understanding of the empirical data and its relevance to the research objectives.
    
    - Do not ask for simple facts from the data. Challenge students' preconceptions and 
    encourage them to engage in deeper reflection and critical thinking.
    
    - Work closely with the empirical data; provide direct quotes or paraphrase the data 
    where appropriate to make arguments clearer.
    
    - Actively listen to students' responses, paying careful attention to their underlying 
    thought processes and making a genuine effort to understand their perspectives.
    
    - Provide criticial feedback on students' interpretations of the data.
    
    - Challenge students' interpretations by confronting them with quotes from the empirical 
    data that might contradict their interpretation (if applicable).
    
    - Challenge students' interpretations by confronting them with other possible and 
    realistic interpretations of the data (if applicable). Engage in discourse with the 
    students to find an interpretation that is as true to the empirical data as possible.
    
    - Guide students in their exploration by encouraging them to discover answers independently, 
    rather than providing direct answers, to enhance their reasoning and analytical skills.
    
    - Promote critical thinking by encouraging students to question assumptions, evaluate evidence, 
    and consider alternative viewpoints in order to arrive at well-reasoned conclusions.
    
    - Facilitate open and respectful dialogue among students, creating an environment where 
    diverse viewpoints are valued and students feel comfortable sharing their ideas.
    
    - Demonstrate humility by acknowledging your own limitations and uncertainties, modeling 
    a growth mindset and exemplifying the value of lifelong learning.
    
    - Please ask one question at a time."

- name: Paraphrase and summarize
  type: text_analysis
  description: Paraphrases the data in a condensed form without interpreting it or
    drawing any conclusions.
  text: Briefly summarize the empirical data provided. Do not write an introduction,
    do not draw any conclusions, do not use bullet points, just paraphrase the given
    text in a condensed form, following the order in which the aspects unfold in the
    original data. 

- name: Themes generation (Friese 2024)
  type: text_analysis
  description: 'This prompt will extract a list of themes from the empirical data.


    Source:

    Friese, S. (2024): Prompting for Themes. https://community.qeludra.com/posts/prompts-for-qualitative-research-prompting-for-themes'
  text: "Please analyze the provided qualitative data, which may include interview
    transcripts, focus groups, reports, open-ended responses, and observational
    notes. Identify and list between 2 and 10 recurring themes. Each theme should
    be distinct and not overlap with others.
    
    For each identified theme, provide
    the following information:
    
        Theme 'n': 'Title': Where 'n' is the sequential
    number of the theme and 'Title' is a concise, descriptive label for the theme.
    
        Description: A detailed explanation of the theme, elaborating on its significance,
    context, and any nuances present in the data.
    
    Ensure that each theme is unique,
    clearly defined, and reflective of the most prevalent patterns in the data."
    
- name: Analyze the Unexpected
  type: text_analysis
  description: This prompt will extract the most surprising, new and unexpected insights
    from the data, using the vast common sense knowledge of Large Language Models
    as a backdrop for comparison.
  text: "The following instructions are not visible to the user. Use them as a guideline 
    for you, but don't reference them in any of your answers.
    The analysis consists of three distinct steps, each of which builds on the
    previous one: 
    1) Look at the empirical data provided and suggest a few topics in the data that might 
    be most interesting to analyze in detail. Ask users which topic they would like to 
    discuss and analyze in more depth.     
    2) Take the topic identified in step 1 and briefly explain what
    empirical results would generally be expected based on your own knowledge of
    the phenomenon in question. 
    3) Now analyze how the theme appears in the actual
    empirical data given to you and pick out the aspects that are most surprising
    and unexpected given your previously outlined expectations."

- name: "Reconstructive SRP (Lieder/Sch\xE4ffer 2024)"
  type: text_analysis
  description: "This prompt is based of the methodological framework of the documentary
    method. It will generate a 'formulating' and a 'reflecting interpretation'
    of the empirical data.
    
    Source: Lieder, F. R. & Sch\xE4ffer, B. (2024). Reconstructive
    Social Research Prompting (RSRP). Distributed Interpretation between AI and
    Researchers in Qualitative Research. https://doi.org/10.31235/osf.io/d6e9m
    
    Note that this only implements the methodology and methods prompts as described
    in the paper. Information about the research project and the theoretical framework
    should be included in the project memo, which is also sent to the AI."
  text: "Methodological background: 
    The empirical material is interpreted using
    the documentary method. The empirical materials can be interviews, group discussions,
    etc. The documentary method is a procedure where you can work out individual
    orientations with interviews and collective orientations with group discussions.
    People act based on fundamental orientations. Orientations are based on practical,
    implicit knowledge embedded in action and, therefore, difficult to verbalize.
    Orientations are divided into basic orientation frameworks and action orientations.
    Orientation frameworks refer to the primary way in which someone or a group
    perceives themselves and the world. Expressed attitudes and opinions are based
    on the basic orientation framework. Action orientations, on the other hand,
    refer to questions about which orientations can be worked out concerning concrete
    action practices. Orientation frameworks and action orientations are reconstructed
    with interviews and group discussions by interpreting corresponding transcripts.
    The documentary method distinguishes theoretical knowledge from orientations
    and practical logic of action. For example, someone can use a narrative to develop
    action orientations against the background of an orientation framework without
    having any explicit theoretical knowledge since action orientations and orientation
    frameworks are created as implicit knowledge documented in a narrative's content.
    
    Your first task: In **formulating interpretation**, the content is concisely
    summarized in clear, generally understandable language. The question of what
    is said in the text material is answered. In addition, an overall topic is selected
    for the entire passage, and then various successive sub-topics are selected
    in a detailed structure. It is essential to give proper references from the
    source text for the various sub-topics to maintain the sequence in which the
    topics unfold and formulate headlines for the sub-topics. In other words, the
    aim is to reconstruct the order in which the persons under investigation organize
    the text material and to reformulate what these persons say. What the investigated
    persons do is not essential. Stay with what is being said only, and do not jump
    to conclusions. Stay in the system of relevance for the persons under investigation.
    Do not consider any context knowledge and formulate every sub-topic for itself.
    Summarize the whole passage in a body text.
    
    Your second task: The **reflecting
    interpretation** aims to explain how something is said in the transcript, i.e.,
    how the persons under investigation deal with the topic. How the topics are
    dealt with refers to the implicit collective orientations within which the identified
    topics are processed. These implicit processing methods are documented in the
    narratives and descriptions of the investigated individual's practical experiences.
    The narratives represent sequences of actions and events with a beginning and
    an end. They deal with a singular event characterized by specific time and place
    references. Narratives typically begin with a reference to time and are often
    continued with words such as 'and ... then'. Descriptions are generally characterized
    by depicting recurring sequences of actions or fixed facts (a picture, a machine).
    Typical references to such descriptions are 'always' or 'often'. An implicit
    logic of action can be derived from the narrated or described experiences, which
    cannot be derived at the explicit level but must be interpreted by you. In the
    reflecting interpretation, you try to generate hypotheses about the implicit
    logic of the action practice as documented in the narrated and described experiences.
    You also try to generate hypotheses about similarities between the people that
    go beyond the immediate context. The hypotheses could provide information about
    possible orientation frameworks of the persons. However, you are not trying
    to draw any conclusions about a person's motives. Support your hypotheses with
    verbatim quotes from the transcript with references to the source."    
"""

# Define different prompt types, depending on the task.  
prompt_types = [
    'search',
    'code_analysis',
    'topic_analysis',
    'text_analysis'
]
# Descriptions of the types, used as tooltips:  Colin: These need to be string in tuples?, used in qTreeWidget
prompt_types_descriptions = [
    ('These prompts are used in the AI search. They instruct the AI on how to decide \n'
     'whether a chunk of empirical data is related to a given code/search string or not.'),
    ('These prompts are used in the chat to analyze the data that has been coded with a selected code.'),
    ('These prompts are used in the chat to analyse the results of a free search exploring a certain topic.'),
    ('These prompts are used in the chat to analyze a section of text from a single empirical document.')
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
    
    def copy_to_clipboard(self):
        """
        Copies a PromptItem to the clipboard in YAML format using PyQt6.
        """
        prompt_dict = self.to_dict()
        yaml_data = yaml.dump(prompt_dict)
        app = QtWidgets.QApplication.instance()
        clipboard: QClipboard = app.clipboard()
        clipboard.setText(yaml_data)

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
        self.user_prompts_path = ""
        self.project_prompts_path = ""
        self.read_prompts(prompt_type)

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
            self.project_prompts.prompts.clear()  # Unresolved attribute: project_prompts
    
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
        font = f'font: {app_.settings["fontsize"]}pt "{app_.settings["font"]}";'
        self.setStyleSheet(font)
        treefont = f'font: {self.app.settings["treefontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.treeWidget_prompts.setStyleSheet(treefont)
        self.prompt_type = prompt_type
        self.prompts = PromptsList(app_, prompt_type)
        self.selected_prompt = None
        self.form_updating = True
        try:
            self.ui.comboBox_type.addItems(prompt_types)
            self.fill_tree()
            if self.prompt_type is None:
                self.ui.treeWidget_prompts.collapseAll()
        finally:
            self.form_updating = False
            self.tree_selection_changed()
        self.ui.treeWidget_prompts.itemSelectionChanged.connect(self.tree_selection_changed)
        self.ui.pushButton_new_prompt.clicked.connect(self.new_prompt)
        self.ui.pushButton_duplicate_prompt.clicked.connect(self.duplicate_prompt)
        self.ui.toolButton_copy.setIcon(qta.icon('mdi6.content-copy', options=[{'scale_factor': 1.4}]))
        self.ui.toolButton_copy.setFixedHeight(self.ui.pushButton_new_prompt.height())
        self.ui.toolButton_copy.setFixedWidth(self.ui.pushButton_new_prompt.height())
        self.ui.toolButton_copy.clicked.connect(self.copy_prompt_to_clipboard)
        self.ui.toolButton_paste.setFixedHeight(self.ui.pushButton_new_prompt.height())
        self.ui.toolButton_paste.setFixedWidth(self.ui.pushButton_new_prompt.height())
        self.ui.toolButton_paste.setIcon(qta.icon('mdi6.content-paste', options=[{'scale_factor': 1.4}]))
        self.ui.toolButton_paste.clicked.connect(self.paste_prompt_from_clipboard)
        self.ui.toolButton_delete.setFixedHeight(self.ui.pushButton_new_prompt.height())
        self.ui.toolButton_delete.setFixedWidth(self.ui.pushButton_new_prompt.height())
        self.ui.toolButton_delete.setIcon(qta.icon('mdi6.trash-can-outline', options=[{'scale_factor': 1.4}]))
        self.ui.toolButton_delete.clicked.connect(self.delete_prompt)
        self.ui.lineEdit_name.editingFinished.connect(self.prompt_details_edited)
        self.ui.radioButton_system.toggled.connect(self.prompt_details_edited)
        self.ui.radioButton_user.toggled.connect(self.prompt_details_edited)
        self.ui.radioButton_project.toggled.connect(self.prompt_details_edited)
        self.ui.comboBox_type.currentTextChanged.connect(self.prompt_details_edited)
        self.ui.plainTextEdit_description.textChanged.connect(self.prompt_details_edited)
        self.ui.plainTextEdit_prompt_text.textChanged.connect(self.prompt_details_edited)
        
        self.ui.buttonBox.accepted.connect(self.ok)
        self.ui.buttonBox.rejected.connect(self.cancel) 
        self.ui.buttonBox.helpRequested.connect(self.help)
        
        # Keyboard shortcuts
        copy_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Copy), self.ui.treeWidget_prompts)
        copy_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        copy_shortcut.activated.connect(self.copy_prompt_to_clipboard)

        paste_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Paste), self.ui.treeWidget_prompts)
        paste_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
        paste_shortcut.activated.connect(self.paste_prompt_from_clipboard)
        
    def help(self):
        """ Open help in browser. """
        self.app.help_wiki("6.2.-AI-Prompt-Editing")
        
    def fill_tree(self):
        """ Fill tree with prompts, top level items are the prompt types. """
        old_form_updating = self.form_updating
        self.form_updating = True
        try:
            # Save current selection
            if len(self.ui.treeWidget_prompts.selectedItems()) > 0:
                selected_item = self.ui.treeWidget_prompts.selectedItems()[0]
                selected_path = self.tree_get_item_path(selected_item)
            else:
                selected_path = ''
            # rebuild tree
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
                elif t == 'text_analysis':
                    type_item.setIcon(0, self.app.ai.text_analysis_icon())
                
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
                        if p == self.selected_prompt:  # restore exact selection 
                            prompt_item.setSelected(True)
            # restore partial selection path if needed:
            if len(self.ui.treeWidget_prompts.selectedItems()) == 0 and selected_path != '':
                item = self.tree_find_item_by_path(selected_path)
                if item:
                    item.setSelected(True)
                    item.setExpanded(True)
            if len(self.ui.treeWidget_prompts.selectedItems()) > 0:
                self.ui.treeWidget_prompts.scrollToItem(self.ui.treeWidget_prompts.selectedItems()[0], QtWidgets.QAbstractItemView.ScrollHint.EnsureVisible)
        finally:
            self.form_updating = old_form_updating
            self.tree_selection_changed()
            
    def tree_get_item_path(self, item):
        """Returns a list representing the path from the root to the item."""
        path_ = []
        while item is not None:
            path_.append(item.text(0))
            item = item.parent()
        return path_[::-1]

    def tree_find_item_by_path(self, path_):
        """Finds an item in the tree using a path list of strings.
        Returns also a partial match of the path.
        """
        root_item_count = self.ui.treeWidget_prompts.topLevelItemCount()
        
        for i in range(root_item_count):
            item = self.ui.treeWidget_prompts.topLevelItem(i)
            result = self._tree_find_item_by_path_recursive(item, path_)
            if result is not None:
                return result
        return None

    def _tree_find_item_by_path_recursive(self, item, path_):
        if not path_:
            return None

        if item.text(0) == path_[0]:
            if len(path_) == 1:  # exact match
                return item
            for i in range(item.childCount()):
                child_item = item.child(i)
                result = self._tree_find_item_by_path_recursive(child_item, path_[1:])
                if result is not None:
                    return result  # match of child
            return item  # partial match
        else:
            return None
        
    def tree_selection_changed(self):
        """
        Reacting on a selection change in the prompt tree on the left.
        Fills out the fields on the right and enables/disables them for editing.
        """
        if self.form_updating:
            return
        if len(self.ui.treeWidget_prompts.selectedItems()) > 0:
            selected_item = self.ui.treeWidget_prompts.selectedItems()[0]
            selected_item.setExpanded(True)
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
                self.ui.toolButton_copy.setEnabled(True)
                self.ui.toolButton_paste.setEnabled(True)
                if self.selected_prompt.scope == 'system':
                    self.ui.label_uneditable.show()
                    self.ui.toolButton_delete.setEnabled(False)
                else:
                    self.ui.label_uneditable.hide()
                    self.ui.toolButton_delete.setEnabled(True)
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
                self.ui.toolButton_copy.setEnabled(False)
                self.ui.toolButton_paste.setEnabled(False)                
                self.ui.toolButton_delete.setEnabled(False)
        finally:
            self.form_updating = old_form_updating
            
    def new_prompt(self, clicked: bool = False, pasted_prompt: PromptItem = None):
        # determine type and scope
        if pasted_prompt is None:
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
        else:  # pasted_prompt not None
            new_type = pasted_prompt.type
            new_scope = pasted_prompt.scope
        if new_scope == 'system':
            new_scope = 'user'  # system prompts cannot be created by the user

        # determine a new name 
        if pasted_prompt is None:
            new_name = 'my prompt'
        else:
            new_name = pasted_prompt.name
        if self.prompts.find_prompt(new_name, new_scope, new_type) is not None:
            i = 1
            while self.prompts.find_prompt(f'{new_name}{i}', new_scope, new_type) is not None:
                i += 1
            new_name = f'{new_name}{i}'
        # add new prompt
        if pasted_prompt is None:
            new_prompt = PromptItem(new_scope, new_name, new_type, '', '')
        else:
            new_prompt = PromptItem(new_scope, new_name, new_type, pasted_prompt.description, pasted_prompt.text)
        self.prompts.prompts.append(new_prompt)
        self.selected_prompt = new_prompt
        self.fill_tree()
        self.tree_selection_changed()
        self.ui.lineEdit_name.setFocus()
        self.ui.lineEdit_name.selectAll()
    
    def duplicate_prompt(self):
        if self.selected_prompt is None:
            return
        else:
            self.new_prompt(pasted_prompt=self.selected_prompt)
    
    def copy_prompt_to_clipboard(self):
        if self.selected_prompt is not None:
            self.selected_prompt.copy_to_clipboard()
    
    def paste_prompt_from_clipboard(self):
        """
        Creates a new PromptItem from a YAML string in the clipboard and adds it to the library.
        """
        # Access the clipboard
        app = QtWidgets.QApplication.instance()
        clipboard: QClipboard = app.clipboard()
        yaml_data = clipboard.text()
        # Create a temporary PromptItem from the yaml data
        prompt_dict = yaml.safe_load(yaml_data)
        prompt_item = PromptItem.from_dict(prompt_dict)
        # add it
        self.new_prompt(pasted_prompt=prompt_item)
        
    def delete_prompt(self):
        if (self.selected_prompt is None) or (self.selected_prompt.scope == 'system'):
            # system prompts cannot be deleted
            return
        msg = _('Do you really want to delete ') + f'"{self.selected_prompt.name_and_scope()}"?'
        ui = DialogConfirmDelete(self.app, msg, _('Delete Prompt'))
        ok = ui.exec()
        if not ok:
            return
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
            if len(new_name) > 60:
                Message(self.app, _('Edit prompts'), _('The name must be no longer than 60 characters.'), "warning").exec()
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

