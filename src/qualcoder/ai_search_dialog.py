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
https://qualcoder.org/
"""

from copy import deepcopy
import logging
import os

from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush
from .ai_agent_prompts import AiAgentPromptsCatalog, AgentPromptRecord, prompt_name_and_scope
from .color_selector import TextColor
from .report_attributes import DialogSelectAttributeParameters
from .GUI.ui_ai_search import Ui_Dialog_AiSearch
from .helpers import Message
from .select_items import DialogSelectItems


path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogAiSearch(QtWidgets.QDialog):
    """ Dialog to select the options for the AI based search
    Called from code_text.py
    """
    
    attributes = []
    attribute_file_ids = []
    selected_code_name = ''
    selected_code_ids = -1
    selected_code_memo = ''
    selected_code_scope = []
    include_coded_segments = False
    selected_file_ids = []
    selected_case_ids = []
    selected_case_names = []
    selected_filter_info = {}
    current_prompt = None
    prompt_records = []

    def _default_prompt_record(self):
        """Return the legacy-default prompt for this dialog context when available."""

        default_names = {
            "search": "search/focused-search",
            "code_analysis": "code-analysis/code-summary",
            "topic_exploration": "topic-exploration/topic-summary",
        }
        default_name = default_names.get(self.context, "")
        if default_name == "":
            return self.prompt_records[0] if len(self.prompt_records) > 0 else None
        prompt = self.prompts_catalog.find_prompt_variant(
            default_name,
            "system",
            prompt_type=self.context,
            include_internal=(self.context == "search"),
            apply_init=False,
        )
        if prompt is not None:
            return prompt
        return self.prompt_records[0] if len(self.prompt_records) > 0 else None

    def _context_setting_keys(self, suffix: str) -> list[str]:
        keys = [f'ai_dlg_{self.context}_{suffix}']
        if self.context == 'topic_exploration':
            keys.append(f'ai_dlg_topic_analysis_{suffix}')
        return keys

    def _get_context_setting(self, suffix: str, default=None):
        for key in self._context_setting_keys(suffix):
            if key in self.app.settings:
                return self.app.settings[key]
        return default

    def _set_context_setting(self, suffix: str, value) -> None:
        self.app.settings[f'ai_dlg_{self.context}_{suffix}'] = value

    def _prompt_display_name_and_scope(self, prompt: AgentPromptRecord) -> str:
        """Return the prompt label for this dialog context."""

        prompt_label = prompt_name_and_scope(prompt)
        prefixes = {
            "code_analysis": "code-analysis/",
            "topic_exploration": "topic-exploration/",
        }
        prefix = prefixes.get(self.context, "")
        if prefix != "" and prompt_label.startswith(prefix):
            return prompt_label[len(prefix):]
        return prompt_label

    def __init__(self, app_, context, selected_id=-1, selected_is_code=True, tree_sort_option="all asc"):
        """Initializes the dialog

        Args:
            app_ (qualcoder App)
            context: the calling context, can be:
                'search': called from 'Code Text > AI Search', 
                'code_analysis': called from 'AI Chat > New Code Chat', 
                'topic_exploration': called from 'AI Chat > New Topic Exploration Chat'.
            selected_id (int): the id of the selected item in the codes and categories tree. -1 if no item is selected.
            selected_is_code (bool): True if the selected item is a code, False if it is a category
        """
        self.app = app_
        self.code_names, self.categories = self.app.get_codes_categories()
        self.context = context
        self.file_ids = ""
        self.case_ids = ""
        self.files = []
        self.cases = []
        self.selected_code_scope = []
        self.coder_selection_is_custom = False
        self.tree_sort_option = tree_sort_option
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_AiSearch()
        self.ui.setupUi(self)
        # adapt UI to context
        if context == 'search':
            self.setWindowTitle('AI Search')
            self.ui.label_what.setText(_('1) What do you want to search for?'))
            self.ui.tabWidget.setTabVisible(0, True)  # code search
            self.ui.tabWidget.setTabVisible(1, True)  # free search
            self.ui.checkBox_coded_segments.setVisible(True)
            self.ui.widget_coder.setVisible(False)
        elif context == 'code_analysis':
            self.setWindowTitle('AI Code Analysis')
            self.ui.label_what.setText(_('1) Which codes or categories do you want to analyze?'))
            self.ui.tabWidget.setCurrentIndex(0)
            self.ui.tabWidget.setTabVisible(0, True)  # code search
            self.ui.tabWidget.setTabVisible(1, False)  # free search
            self.ui.checkBox_coded_segments.setVisible(False) 
            self.ui.widget_coder.setVisible(True)
        elif context == 'topic_exploration':
            self.setWindowTitle('AI Topic Exploration')
            self.ui.label_what.setText(_('1) Which topic do you want to explore?'))
            self.ui.tabWidget.setCurrentIndex(1)
            self.ui.tabWidget.setTabVisible(0, False)  # code search
            self.ui.tabWidget.setTabVisible(1, True)  # free search
            self.ui.checkBox_coded_segments.setVisible(False)
            self.ui.widget_coder.setVisible(False)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = f'font: {app_.settings["fontsize"]}pt "{app_.settings["font"]}";'
        self.setStyleSheet(font)
        font_bold = f'{font}\nfont-weight: bold;\n color: {self.app.highlight_color()}'  # 'font: bold ' + font[6:]
        self.ui.label_what.setStyleSheet(font_bold)
        self.ui.label_how.setStyleSheet(font_bold)
        self.ui.label_filter.setStyleSheet(font_bold)
        # coder
        self.coder_names = []
        if context == 'code_analysis':
            self.coder_names = self.app.get_coder_names_in_project(only_visible=True)
            coder_names_str = ', '.join(self.coder_names)
            self.ui.label_coder.setText(_('Coders: ') + coder_names_str)
            self.ui.pushButton_coder.clicked.connect(self.select_coders)  
        # code tree
        treefont = f'font: {self.app.settings["treefontsize"]}pt "{self.app.settings["font"]}";'
        self.ui.treeWidget.setStyleSheet(treefont)
        self.ui.listWidget_files.setStyleSheet(treefont)
        self.ui.listWidget_files.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.ui.listWidget_cases.setStyleSheet(treefont)
        self.ui.listWidget_cases.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        if context == 'code_analysis':
            self.ui.treeWidget.setSelectionMode(QtWidgets.QTreeWidget.SelectionMode.ExtendedSelection)
        else:
            self.ui.treeWidget.setSelectionMode(QtWidgets.QTreeWidget.SelectionMode.SingleSelection)
        if self.ui.tabWidget.isTabVisible(0):  # code
            self.fill_tree(selected_id, selected_is_code) 
        # prompts
        self.prompts_catalog = AiAgentPromptsCatalog(app_)
        self.prompt_records = self.prompts_catalog.list_prompt_variants(
            prompt_type=self.context,
            include_internal=(self.context == "search"),
            apply_init=False,
        )
        if len(self.prompt_records) == 0:
            msg = _('No prompts available for this analysis type.')
            Message(self.app, _('AI prompts'), msg, "warning").exec()
            self.reject()
            return
        # load last settings
        default_prompt = self._default_prompt_record()
        last_prompt_name = self._get_context_setting('last_prompt_name', default_prompt.name)
        last_prompt_scope = self._get_context_setting('last_prompt_scope', default_prompt.scope)
        self.current_prompt = self.prompts_catalog.find_prompt_variant(
            last_prompt_name,
            last_prompt_scope,
            prompt_type=self.context,
            include_internal=(self.context == "search"),
            apply_init=False,
        )
        if self.current_prompt is None:
            self.current_prompt = default_prompt
            msg = _('The last used prompt') + \
                f' "{last_prompt_name} ({last_prompt_scope})" ' + \
                _('could not be found. The prompt will be reset to the default.')
            Message(self.app, _('No codes'), msg, "warning").exec()
        for prompt in self.prompt_records:
            self.ui.comboBox_prompts.addItem(self._prompt_display_name_and_scope(prompt))
            item_idx = self.ui.comboBox_prompts.count() - 1
            self.ui.comboBox_prompts.setItemData(item_idx, prompt.description, Qt.ItemDataRole.ToolTipRole)
        self.ui.comboBox_prompts.setCurrentText(self._prompt_display_name_and_scope(self.current_prompt))
        self.ui.comboBox_prompts.setToolTip(self.current_prompt.description)
        self.ui.comboBox_prompts.currentIndexChanged.connect(self.on_prompt_selected)
        if context == 'search':
            self.ui.tabWidget.setCurrentIndex(int(self._get_context_setting('last_tab_index', 0)))
        self.ui.lineEdit_free_topic.setText(self._get_context_setting('free_topic', ''))
        self.ui.textEdit_free_description.setText(self._get_context_setting('free_description', '').replace('\\n', '\n'))        
        self.ui.checkBox_send_memos.setChecked((self._get_context_setting('send_memos', 'True') == 'True'))
        self.ui.checkBox_coded_segments.setChecked((self._get_context_setting('coded_segments', 'False') == 'True'))
        # buttons
        self.ui.pushButton_change_prompt.clicked.connect(self.change_prompt)
        self.ui.buttonBox.accepted.connect(self.ok)
        self.ui.buttonBox.rejected.connect(self.cancel) 
        # attributes        
        cur = self.app.conn.cursor()
        sql = "select count(name) from attribute_type"
        cur.execute(sql)
        res = cur.fetchone()
        if res[0] == 0:
            self.ui.pushButton_attributeselect.setEnabled(False)
        self.ui.pushButton_attributeselect.clicked.connect(self.select_attributes)
        self.get_files_and_cases()
        
    def showEvent(self, event):
        super().showEvent(event)
        # restore position splitter_code_tree:
        splitter_pos = int(self._get_context_setting('last_splitter_code_tree', 500))
        splitter_width = self.ui.splitter_code_tree.size().width()
        splitter_handle = self.ui.splitter_code_tree.handleWidth()
        self.ui.splitter_code_tree.setSizes([splitter_pos, splitter_width - splitter_pos - splitter_handle])
        # restore position splitter_case_files:
        splitter_pos = int(self._get_context_setting('last_splitter_case_files', 220))
        splitter_height = self.ui.splitter_case_files.size().height()
        splitter_handle = self.ui.splitter_case_files.handleWidth()
        self.ui.splitter_case_files.setSizes([splitter_pos, splitter_height - splitter_pos - splitter_handle])
        
    def fill_tree(self, selected_id, selected_is_code):
        """ Fill tree widget, top level items are main categories and unlinked codes. """

        cats = deepcopy(self.categories)
        codes = deepcopy(self.code_names)
        self.ui.treeWidget.clear()
        self.ui.treeWidget.setColumnCount(4)
        self.ui.treeWidget.setHeaderLabels([_("Name"), "Id", _("Memo"), _("Count")])
        self.ui.treeWidget.header().setToolTip(_("Codes and categories"))
        if not self.app.settings['showids']:
            self.ui.treeWidget.setColumnHidden(1, True)
        else:
            self.ui.treeWidget.setColumnHidden(1, False)
        self.ui.treeWidget.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.ui.treeWidget.header().setStretchLastSection(False)
        # Add top level categories
        remove_list = []
        for c in cats:
            if c['supercatid'] is None:
                memo = ""
                if c['memo'] != "":
                    memo = _("Memo")
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                top_item.setToolTip(0, '')
                if len(c['name']) > 52:
                    top_item.setText(0, c['name'][:25] + '..' + c['name'][-25:])
                    top_item.setToolTip(0, c['name'])
                top_item.setToolTip(2, c['memo'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                if not selected_is_code and c['catid'] == selected_id:
                    top_item.setSelected(True)
                remove_list.append(c)
        for item in remove_list:
            cats.remove(item)

        ''' Add child categories. Look at each unmatched category, iterate through tree
        to add as child then remove matched categories from the list. '''
        count = 0
        while len(cats) > 0 and count < 10000:
            remove_list = []
            for c in cats:
                it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
                item = it.value()
                count2 = 0
                while item and count2 < 10000:  # while there is an item in the list
                    if item.text(1) == 'catid:' + str(c['supercatid']):
                        memo = ""
                        if c['memo'] != "":
                            memo = "Memo"
                        child = QtWidgets.QTreeWidgetItem([c['name'], 'catid:' + str(c['catid']), memo])
                        child.setToolTip(0, '')
                        if len(c['name']) > 52:
                            child.setText(0, c['name'][:25] + '..' + c['name'][-25:])
                            child.setToolTip(0, c['name'])
                        child.setToolTip(2, c['memo'])
                        item.addChild(child)
                        if not selected_is_code and c['catid'] == selected_id:
                            child.setSelected(True)
                        remove_list.append(c)
                    it += 1
                    item = it.value()
                    count2 += 1
            for item in remove_list:
                cats.remove(item)
            count += 1

        # Add unlinked codes as top level items
        remove_items = []
        for c in codes:
            if c['catid'] is None:
                memo = ""
                if c['memo'] != "":
                    memo = "Memo"
                top_item = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                top_item.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.BrushStyle.SolidPattern))
                color = TextColor(c['color']).recommendation
                top_item.setForeground(0, QBrush(QtGui.QColor(color)))
                top_item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                top_item.setToolTip(0, '')
                if len(c['name']) > 52:
                    top_item.setText(0, c['name'][:25] + '..' + c['name'][-25:])
                    top_item.setToolTip(0, c['name'])
                top_item.setToolTip(2, c['memo'])
                self.ui.treeWidget.addTopLevelItem(top_item)
                if selected_is_code and c['cid'] == selected_id:
                    top_item.setSelected(True)
                remove_items.append(c)
        for item in remove_items:
            codes.remove(item)

        # Add codes as children
        for c in codes:
            it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
            item = it.value()
            count = 0
            while item and count < 10000:
                if item.text(1) == 'catid:' + str(c['catid']):
                    memo = ""
                    if c['memo'] != "":
                        memo = _("Memo")
                    child = QtWidgets.QTreeWidgetItem([c['name'], 'cid:' + str(c['cid']), memo])
                    child.setBackground(0, QBrush(QtGui.QColor(c['color']), Qt.BrushStyle.SolidPattern))
                    color = TextColor(c['color']).recommendation
                    child.setForeground(0, QBrush(QtGui.QColor(color)))
                    child.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
                    child.setToolTip(0, '')
                    if len(c['name']) > 52:
                        child.setText(0, c['name'][:25] + '..' + c['name'][-25:])
                        child.setToolTip(0, c['name'])
                    child.setToolTip(2, c['memo'])
                    item.addChild(child)
                    if selected_is_code and c['cid'] == selected_id:
                        child.setSelected(True)
                    c['catid'] = -1  # make unmatchable
                it += 1
                item = it.value()
                count += 1
        if self.tree_sort_option == "all asc":
            self.ui.treeWidget.sortByColumn(0, QtCore.Qt.SortOrder.AscendingOrder)
        if self.tree_sort_option == "all desc":
            self.ui.treeWidget.sortByColumn(0, QtCore.Qt.SortOrder.DescendingOrder)
        self.fill_code_counts_in_tree()
        self.ui.treeWidget.expandAll()    

    def fill_code_counts_in_tree(self):
        """ Count instances of each code from all visible or selected coders and all files. """

        cur = self.app.conn.cursor()
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        count = 0
        while item and count < 10000:
            if item.text(1)[0:4] == "cid:":
                cid = str(item.text(1)[4:])
                if self.context == 'code_analysis':
                    # use selected coders
                    placeholders = ", ".join(["?" for _ in self.coder_names])
                    sql = f"select count(cid) from code_text_visible where cid=? and owner in ({placeholders}) union "
                    sql += f"select count(cid) from code_av_visible where cid=? and owner in ({placeholders}) union "
                    sql += f"select count(cid) from code_image_visible where cid=? and owner in ({placeholders})"        
                    params = []
                    for _ in range(3):
                        params.append(cid)
                        params.extend(self.coder_names)
                else: 
                    # use all visible coders
                    sql = "select count(cid) from code_text_visible where cid=? union "
                    sql += "select count(cid) from code_av_visible where cid=? union "
                    sql += "select count(cid) from code_image_visible where cid=?"
                    params = [cid, cid, cid]
                cur.execute(sql, params)
                result = cur.fetchall()
                total = 0
                for row in result:
                    total = total + row[0]
                if total > 0:
                    item.setText(3, str(total))
                else:
                    item.setText(3, "")
            it += 1
            item = it.value()
            count += 1
            
    def select_coders(self):
        self.coder_names = self.app.get_coder_names_in_project(only_visible=False)
        coder_names_dicts = [{"name": name} for name in self.coder_names]
        ui = DialogSelectItems(self.app, coder_names_dicts, _('Coder selection'), 'multiple')
        ok = ui.exec()
        if not ok:
            return
        selection = ui.get_selected()
        if not selection:
            return
        self.coder_names = []
        for coder_name in selection:
            self.coder_names.append(coder_name['name'])
        self.coder_selection_is_custom = True
        coder_names_str = ', '.join(self.coder_names)
        self.ui.label_coder.setText(_('Coders: ') + coder_names_str)
        self.fill_code_counts_in_tree()
            
    def on_prompt_selected(self, index):
        """ This function will be called whenever the user selects a new item in the combobox. """
        del index
        if 0 <= self.ui.comboBox_prompts.currentIndex() < len(self.prompt_records):
            self.current_prompt = self.prompt_records[self.ui.comboBox_prompts.currentIndex()]
        self.ui.comboBox_prompts.setToolTip(self.current_prompt.description)
            
    def change_prompt(self):
        """ Select and edit the prompt for the search. """
        msg = _('These prompts are now loaded from Markdown files in the new prompt system. Editing them from this dialog is not available yet.')
        Message(self.app, _('AI prompts'), msg, "information").exec()

    def select_attributes(self):
        """ Select files based on attribute selections.
        Attribute results are a dictionary of:
        first item is a Boolean AND or OR list item
        Followed by each attribute list item
        """
        
        ui = DialogSelectAttributeParameters(self.app)
        ui.fill_parameters(self.attributes)
        temp_attributes = deepcopy(self.attributes)
        self.attributes = []
        ok = ui.exec()
        if not ok:
            self.attributes = temp_attributes
            self.ui.label_attributes.setText('')
            #if self.attributes:
            #    pm = QtGui.QPixmap()
            #    pm.loadFromData(QtCore.QByteArray.fromBase64(attributes_selected_icon), "png")
            #    self.ui.pushButton_attributeselect.setIcon(QtGui.QIcon(pm))
            return
        
        # Clear ui
        self.attribute_file_ids = []
        self.ui.label_attributes.setText('')
        # self.ui.splitter.setSizes([300, 300, 0])  # Unresolved attribute refernce: splitter
        # Remove any selected case or file ids
        self.file_ids = ""
        for i in range(self.ui.listWidget_files.count()):
            if i == 0:  # all files
                self.ui.listWidget_files.item(i).setSelected(True)
            else:    
                self.ui.listWidget_files.item(i).setSelected(False)
        self.case_ids = ""
        for i in range(self.ui.listWidget_cases.count()):
            if i == 0:  # all cases
                self.ui.listWidget_cases.item(i).setSelected(True)
            else:
                self.ui.listWidget_cases.item(i).setSelected(False)

        self.attributes = ui.parameters
        if len(self.attributes) == 1:
            self.ui.label_attributes.setText('')
            return
        self.ui.label_attributes.setText(ui.tooltip_msg[len(_("Show files:")):])
        self.attribute_file_ids = ui.result_file_ids

    def get_files_and_cases(self):
        """ Get source files with additional details and fill files list widget.
        Get cases and fill case list widget
        Called from : init
        """

        self.ui.listWidget_files.clear()
        self.files = self.app.get_text_filenames()
        # Fill additional details about each file in the memo
        cur = self.app.conn.cursor()
        sql = "select length(fulltext), mediapath from source where id=?"
        sql_text_codings = "select count(cid) from code_text_visible where fid=?"
        sql_av_codings = "select count(cid) from code_av_visible where id=?"  # Not used
        sql_image_codings = "select count(cid) from code_image_visible where id=?"  # Not used
        item = QtWidgets.QListWidgetItem(_("<no file filter>"))
        item.setToolTip(_("Search in all textfiles"))
        item.setData(Qt.ItemDataRole.UserRole, -1)
        self.ui.listWidget_files.addItem(item)
        item.setSelected(True)
        for f in self.files:
            cur.execute(sql, [f['id'], ])
            res = cur.fetchone()
            if res is None:  # safety catch
                res = [0]
            tt = ""
            cur.execute(sql_text_codings, [f['id']])
            txt_res = cur.fetchone()
            tt += _("Codings: ")
            tt += str(txt_res[0])
            item = QtWidgets.QListWidgetItem(f['name'])
            if f['memo'] != "":
                tt += _("\nMEMO: ") + f['memo']
            item.setToolTip(tt)
            item.setData(Qt.ItemDataRole.UserRole, f['id'])
            self.ui.listWidget_files.addItem(item)

        self.ui.listWidget_cases.clear()
        self.cases = self.app.get_casenames()
        item = QtWidgets.QListWidgetItem("<no case filter>")
        item.setToolTip(_("Search in all cases"))
        item.setData(Qt.ItemDataRole.UserRole, -1)
        self.ui.listWidget_cases.addItem(item)
        item.setSelected(True)
        for c in self.cases:
            tt = ""
            item = QtWidgets.QListWidgetItem(c['name'])
            if c['memo'] != "":
                tt = _("MEMO: ") + c['memo']
            item.setToolTip(tt)
            item.setData(Qt.ItemDataRole.UserRole, c['id'])
            self.ui.listWidget_cases.addItem(item)
            
    def _get_codes_from_tree(self, item: QtWidgets.QTreeWidgetItem) -> list:
        res = []
        if item.text(1)[0:3] == 'cid':  # is a code
            id_ = int(item.text(1).split(':')[1])
            res.append(id_)
        for i in range(item.childCount()):
            child = item.child(i)
            res.extend(self._get_codes_from_tree(child))
        return res

    def _tree_item_full_name(self, item: QtWidgets.QTreeWidgetItem) -> str:
        """Return the unabridged code/category name stored in the tree item."""

        full_name = str(item.toolTip(0) if item.toolTip(0) is not None else '').strip()
        if full_name != '':
            return full_name
        return str(item.text(0) if item.text(0) is not None else '').strip()

    def _tree_item_path(self, item: QtWidgets.QTreeWidgetItem) -> str:
        """Return the full tree path for a code or category item."""

        path = [self._tree_item_full_name(item)]
        parent = item.parent()
        while parent is not None and not isinstance(parent, QtWidgets.QTreeWidget):
            path.insert(0, self._tree_item_full_name(parent))
            parent = parent.parent()
        return " > ".join([part for part in path if part != ""])

    def _tree_item_scope_type(self, item: QtWidgets.QTreeWidgetItem) -> str:
        """Return the tree item scope type: code, category, or unknown."""

        item_id = str(item.text(1) if item.text(1) is not None else '')
        if item_id.startswith('cid:'):
            return 'code'
        if item_id.startswith('catid:'):
            return 'category'
        return 'unknown'

    def _tree_item_numeric_id(self, item: QtWidgets.QTreeWidgetItem) -> int:
        """Return the numeric id stored in the tree item id column."""

        item_id = str(item.text(1) if item.text(1) is not None else '')
        try:
            return int(item_id.split(':', 1)[1])
        except Exception:
            return -1

    def _iter_code_items_from_tree(self, item: QtWidgets.QTreeWidgetItem) -> list:
        """Return all code items below item, including item if it is a code."""

        res = []
        if self._tree_item_scope_type(item) == 'code':
            res.append(item)
        for i in range(item.childCount()):
            res.extend(self._iter_code_items_from_tree(item.child(i)))
        return res

    def _selected_tree_items_without_selected_ancestors(self) -> list:
        """Return selected tree items, excluding items already covered by a selected ancestor."""

        selected = list(self.ui.treeWidget.selectedItems())
        selected_ids = {id(item) for item in selected}
        result = []
        for item in selected:
            parent = item.parent()
            covered_by_parent = False
            while parent is not None and not isinstance(parent, QtWidgets.QTreeWidget):
                if id(parent) in selected_ids:
                    covered_by_parent = True
                    break
                parent = parent.parent()
            if not covered_by_parent:
                result.append(item)
        return result

    def _code_scope_from_tree_item(self, item: QtWidgets.QTreeWidgetItem, include_memos: bool) -> dict:
        """Build a structured code-analysis scope entry for one selected item."""

        code_items = self._iter_code_items_from_tree(item)
        included_codes = []
        code_ids = []
        for code_item in code_items:
            code_id = self._tree_item_numeric_id(code_item)
            if code_id < 0 or code_id in code_ids:
                continue
            code_ids.append(code_id)
            code_scope = {
                "id": code_id,
                "path": self._tree_item_path(code_item),
                "name": self._tree_item_full_name(code_item),
            }
            if include_memos:
                code_scope["memo"] = str(code_item.toolTip(2) if code_item.toolTip(2) is not None else '').strip()
            included_codes.append(code_scope)
        scope = {
            "type": self._tree_item_scope_type(item),
            "id": self._tree_item_numeric_id(item),
            "path": self._tree_item_path(item),
            "name": self._tree_item_full_name(item),
            "code_ids": code_ids,
            "included_codes": included_codes,
        }
        if include_memos:
            scope["memo"] = str(item.toolTip(2) if item.toolTip(2) is not None else '').strip()
        return scope

    def _format_selected_code_name(self, code_scope: list) -> str:
        """Build a compact display name for the selected code-analysis scope."""

        if len(code_scope) == 0:
            return ''
        paths = [str(scope.get("path", "")).strip() for scope in code_scope if str(scope.get("path", "")).strip() != ""]
        if len(paths) == 1:
            return paths[0]
        preview = "; ".join(paths[:3])
        if len(paths) > 3:
            preview += "; ..."
        return preview

    def _format_selected_code_memos(self, code_scope: list) -> str:
        """Build a compact memo text for the selected top-level code-analysis scope."""

        lines = []
        for idx, scope in enumerate(code_scope, start=1):
            memo = str(scope.get("memo", "")).strip()
            if memo == "":
                continue
            scope_type = _("Category") if scope.get("type") == "category" else _("Code")
            path = str(scope.get("path", "")).strip()
            if len(code_scope) == 1:
                lines.append(memo)
            else:
                lines.append(f"{idx}. {scope_type}: {path}")
                lines.append(_("Memo: ") + memo)
        return "\n".join(lines).strip()
           
    def ok(self):
        """Collect the infos needed for the ai based search and the filters applied 
        (selected files, cases, attributes), then close the dialog. 
        """    
        ai_status = self.app.ai.get_status()
        if ai_status != 'ready':
            msg = _('The AI ist not ready to fulfill your request (status: ') + ai_status + _(').')
            Message(self.app, _('AI not ready'), msg, "warning").exec()
            return

        if self.ui.tabWidget.currentIndex() == 0:  # code search selected
            if len(self.ui.treeWidget.selectedItems()) == 0:
                msg = _('Please select a code or category (or use "free search" instead).')
                Message(self.app, _('No codes'), msg, "warning").exec()
                return
            else:
                include_memos = self.ui.checkBox_send_memos.isChecked()
                if self.context == 'code_analysis':
                    selected_items = self._selected_tree_items_without_selected_ancestors()
                    self.selected_code_scope = [
                        self._code_scope_from_tree_item(item, include_memos) for item in selected_items
                    ]
                    self.selected_code_ids = []
                    for scope in self.selected_code_scope:
                        for code_id in list(scope.get("code_ids", []) or []):
                            if code_id not in self.selected_code_ids:
                                self.selected_code_ids.append(code_id)
                    self.selected_code_name = self._format_selected_code_name(self.selected_code_scope)
                    if include_memos:
                        self.selected_code_memo = self._format_selected_code_memos(self.selected_code_scope)
                    else:
                        self.selected_code_memo = ''
                else:
                    item = self.ui.treeWidget.selectedItems()[0]
                    self.selected_code_ids = self._get_codes_from_tree(item)
                    self.selected_code_scope = []
                    self.selected_code_name = self._tree_item_path(item)
                    if include_memos:
                        self.selected_code_memo = item.toolTip(2)
                    else:
                        self.selected_code_memo = ''
                self.include_coded_segments = self.ui.checkBox_coded_segments.isChecked()
        else:  # free search selected
            self.selected_code_ids = None
            self.selected_code_scope = []
            self.selected_code_name = self.ui.lineEdit_free_topic.text()
            if self.selected_code_name == '':
                msg = _('Please enter text in the "topic" field.')
                Message(self.app, _('No codes'), msg, "warning").exec()
                return
            self.selected_code_memo = self.ui.textEdit_free_description.toPlainText()
        
        # File selection
        self.selected_file_ids = []
        self.selected_case_ids = []
        self.selected_case_names = []
        self.selected_filter_info = {}
        if self.ui.listWidget_files.item(0).isSelected():  # first item selected = add all files
            for i in range(self.ui.listWidget_files.count()):
                id_ = self.ui.listWidget_files.item(i).data(Qt.ItemDataRole.UserRole)
                if id_ > -1:
                    self.selected_file_ids.append(id_)
        else:  # Add only selected
            for item in self.ui.listWidget_files.selectedItems():
                id_ = item.data(Qt.ItemDataRole.UserRole)
                if id_ > -1:
                    self.selected_file_ids.append(id_)
        
        no_file_filter = self.ui.listWidget_files.item(0).isSelected()

        # case filter
        no_case_filter = self.ui.listWidget_cases.item(0).isSelected()
        if not no_case_filter: 
            # Only apply case filter if the first item (<no case filter>)  
            # is not selected.
            # The case filter will delete all files from self.selected_file_ids that 
            # do not belong to the selected cases. 
            selected_cases = []
            for item in self.ui.listWidget_cases.selectedItems():
                id_ = item.data(Qt.ItemDataRole.UserRole)
                if id_ > -1:
                    selected_cases.append(id_)
                    self.selected_case_ids.append(id_)
                    self.selected_case_names.append(item.text())
            if len(selected_cases) > 0:
                selected_cases_str = "(" + ", ".join(map(str, selected_cases)) + ")"
                files_cases_sql = str('select distinct case_text.fid from case_text '
                                    'join source on case_text.fid=source.id '
                                    'where caseid in ') + selected_cases_str
                cur = self.app.conn.cursor()
                cur.execute(files_cases_sql)
                res = cur.fetchall()
                selected_cases_files = []
                for row in res:
                    selected_cases_files.append(row[0])
                # To filter out all items in self.selected_file_ids that are not also in selected_cases_files,
                # use a list comprehension to create a new list containing only elements present in both lists
                self.selected_file_ids = [x for x in self.selected_file_ids if x in selected_cases_files]
        
        # Combine ids with the attributes filter
        if len(self.attribute_file_ids) > 0:
            self.selected_file_ids = [x for x in self.selected_file_ids if x in self.attribute_file_ids]

        self.selected_filter_info = {
            "no_file_filter": no_file_filter,
            "no_case_filter": no_case_filter,
            "has_attribute_filter": (len(self.attribute_file_ids) > 0),
            "selected_case_ids": list(self.selected_case_ids),
            "selected_case_names": list(self.selected_case_names),
            "custom_coder_filter": bool(self.coder_selection_is_custom),
        }

        if len(self.selected_file_ids) == 0:
            msg = _('After combining all filters, there are not files left for the search. Please check your settings.')
            Message(self.app, _('No files'), msg, "warning").exec()
            return
        
        # Save the settings for the next search
        self._set_context_setting('last_prompt_name', self.current_prompt.name)
        self._set_context_setting('last_prompt_scope', self.current_prompt.scope)
        if self.context == 'search':
            self._set_context_setting('last_tab_index', self.ui.tabWidget.currentIndex())
        self._set_context_setting('free_topic', self.ui.lineEdit_free_topic.text())
        self._set_context_setting('free_description', self.ui.textEdit_free_description.toPlainText().replace('\n', '\\n'))
        self._set_context_setting('last_splitter_code_tree', self.ui.splitter_code_tree.sizes()[0])
        self._set_context_setting('last_splitter_case_files', self.ui.splitter_case_files.sizes()[0])
        self._set_context_setting('send_memos', 'True' if self.ui.checkBox_send_memos.isChecked() else 'False')
        self._set_context_setting('coded_segments', 'True' if self.ui.checkBox_coded_segments.isChecked() else 'False')
        self.accept()
        
    def cancel(self):
        self.selected_code_name = ''
        self.selected_code_memo = ''
        self.selected_code_scope = []
        self.selected_file_ids = []
        self.selected_case_ids = []
        self.selected_case_names = []
        self.selected_filter_info = {}
        self.reject()

