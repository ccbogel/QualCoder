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
"""

from copy import deepcopy
import logging
import os

from PyQt6 import QtWidgets, QtCore, QtGui
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush
from .ai_prompts import PromptsList, DialogAiEditPrompts
from .color_selector import TextColor
from .report_attributes import DialogSelectAttributeParameters
from .GUI.ui_ai_search import Ui_Dialog_AiSearch
from .helpers import Message


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
    include_coded_segments = False
    selected_file_ids = []
    current_prompt = None

    def __init__(self, app_, context, selected_id=-1, selected_is_code=True):
        """Initializes the dialog

        Args:
            app_ (qualcoder App)
            context: the calling context, can be:
                'search': called from 'Code Text > AI Search', 
                'code_analysis': called from 'AI Chat > New Code Chat', 
                'topic_analysis': called from 'AI Chat > New Topic Chat'.
            selected_id (int): the id of the selected item in the codes and categories tree. -1 if no item is selected.
            selected_is_code (bool): True if the selected item is a code, False if it is a category
        """
        self.app = app_
        self.code_names, self.categories = self.app.get_codes_categories()
        self.context = context
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
        elif context == 'code_analysis':
            self.setWindowTitle('AI Code Analysis')
            self.ui.label_what.setText(_('1) Which code do you want to analyze?'))
            self.ui.tabWidget.setCurrentIndex(0)
            self.ui.tabWidget.setTabVisible(0, True)  # code search
            self.ui.tabWidget.setTabVisible(1, False)  # free search
            self.ui.checkBox_coded_segments.setVisible(False) 
        elif context == 'topic_analysis':
            self.setWindowTitle('AI Topic Analysis')
            self.ui.label_what.setText(_('1) Which topic do you want to analyze?'))
            self.ui.tabWidget.setCurrentIndex(1)
            self.ui.tabWidget.setTabVisible(0, False)  # code search
            self.ui.tabWidget.setTabVisible(1, True)  # free search
            self.ui.checkBox_coded_segments.setVisible(False)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = 'font: ' + str(app_.settings['fontsize']) + 'pt '
        font += '"' + app_.settings['font'] + '";'
        self.setStyleSheet(font)
        font_bold = font + '\n' + f'font-weight: bold;\n color: {self.app.highlight_color()}'# 'font: bold ' + font[6:]
        self.ui.label_what.setStyleSheet(font_bold)
        self.ui.label_how.setStyleSheet(font_bold)
        self.ui.label_filter.setStyleSheet(font_bold)
        treefont = 'font: ' + str(self.app.settings['treefontsize']) + 'pt '
        treefont += '"' + self.app.settings['font'] + '";'
        self.ui.treeWidget.setStyleSheet(treefont)
        self.ui.listWidget_files.setStyleSheet(treefont)
        self.ui.listWidget_files.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.ui.listWidget_cases.setStyleSheet(treefont)
        self.ui.listWidget_cases.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.ui.treeWidget.setSelectionMode(QtWidgets.QTreeWidget.SelectionMode.SingleSelection)
        if self.ui.tabWidget.isTabVisible(0):  # code
            self.fill_tree(selected_id, selected_is_code)   
        # prompts
        self.prompts_list = PromptsList(app_, context)
        # load last settings
        last_prompt_name = self.app.settings.get(f'ai_dlg_{self.context}_last_prompt_name', self.prompts_list.prompts[0].name)
        last_prompt_scope = self.app.settings.get(f'ai_dlg_{self.context}_last_prompt_scope', self.prompts_list.prompts[0].scope)
        self.current_prompt = self.prompts_list.find_prompt(last_prompt_name, last_prompt_scope, self.context)
        if self.current_prompt is None:
            self.current_prompt = self.prompts_list.prompts[0]
            msg = _('The last used prompt') + \
                f' "{last_prompt_name} ({last_prompt_scope})" ' + \
                _('could not be found. The prompt will be reset to the default.')
            Message(self.app, _('No codes'), msg, "warning").exec()
        for prompt in self.prompts_list.prompts:
            self.ui.comboBox_prompts.addItem(prompt.name_and_scope())
            item_idx = self.ui.comboBox_prompts.count() - 1
            self.ui.comboBox_prompts.setItemData(item_idx, prompt.description, Qt.ItemDataRole.ToolTipRole)
        self.ui.comboBox_prompts.setCurrentText(self.current_prompt.name_and_scope())
        self.ui.comboBox_prompts.setToolTip(self.current_prompt.description)
        self.ui.comboBox_prompts.currentIndexChanged.connect(self.on_prompt_selected)
        if context == 'search':
            self.ui.tabWidget.setCurrentIndex(int(self.app.settings.get(f'ai_dlg_{self.context}_last_tab_index', 0)))
        self.ui.lineEdit_free_topic.setText(self.app.settings.get(f'ai_dlg_{self.context}_free_topic', ''))
        self.ui.textEdit_free_description.setText(self.app.settings.get(f'ai_dlg_{self.context}_free_description', '').replace('\\n', '\n'))        
        self.ui.checkBox_send_memos.setChecked((self.app.settings.get(f'ai_dlg_{self.context}_send_memos', 'True') == 'True'))
        self.ui.checkBox_coded_segments.setChecked((self.app.settings.get(f'ai_dlg_{self.context}_coded_segments', 'False') == 'True'))
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
        splitter_pos = int(self.app.settings.get(f'ai_dlg_{self.context}_last_splitter_code_tree', 500))
        splitter_width = self.ui.splitter_code_tree.size().width()
        splitter_handle = self.ui.splitter_code_tree.handleWidth()
        self.ui.splitter_code_tree.setSizes([splitter_pos, splitter_width - splitter_pos - splitter_handle])
        # restore position splitter_case_files:
        splitter_pos = int(self.app.settings.get(f'ai_dlg_{self.context}_last_splitter_case_files', 220))
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
        self.fill_code_counts_in_tree()
        self.ui.treeWidget.expandAll()    

    def fill_code_counts_in_tree(self):
        """ Count instances of each code from all coders and all files. """

        cur = self.app.conn.cursor()
        sql = "select count(cid) from code_text where cid=? union "
        sql += "select count(cid) from code_av where cid=? union "
        sql += "select count(cid) from code_image where cid=?"
        it = QtWidgets.QTreeWidgetItemIterator(self.ui.treeWidget)
        item = it.value()
        count = 0
        while item and count < 10000:
            if item.text(1)[0:4] == "cid:":
                cid = str(item.text(1)[4:])
                cur.execute(sql, [cid, cid, cid])  # , self.app.settings['codername']])
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
            
    def on_prompt_selected(self, index):  # Kai, index not used | @Colin - 'index' is a parameter of the self.ui.comboBox_prompts.currentIndexChanged action/signal. I don't think I can omit it. 
        """ This function will be called whenever the user selects a new item in the combobox. """
        self.current_prompt = self.prompts_list.prompts[self.ui.comboBox_prompts.currentIndex()]
        self.ui.comboBox_prompts.setToolTip(self.current_prompt.description)
            
    def change_prompt(self):
        """ Select and edit the prompt for the search. """
        ui = DialogAiEditPrompts(self.app, self.context)
        if ui.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            # Update prompts list and display current prompt:
            self.prompts_list.read_prompts(self.context)
            self.ui.comboBox_prompts.clear()
            for prompt in self.prompts_list.prompts:
                self.ui.comboBox_prompts.addItem(prompt.name_and_scope())
            if ui.selected_prompt is not None:
                self.current_prompt = self.prompts_list.find_prompt(ui.selected_prompt.name, ui.selected_prompt.scope, ui.selected_prompt.type)
            if self.current_prompt is None:
                self.current_prompt = self.prompts_list.prompts[0]  # default
            self.ui.comboBox_prompts.setCurrentText(self.current_prompt.name_and_scope())
            self.ui.comboBox_prompts.setToolTip(self.current_prompt.description)

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
        self.ui.splitter.setSizes([300, 300, 0])  # Unresolved attribute refernce: splitter
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
        sql_text_codings = "select count(cid) from code_text where fid=?"
        sql_av_codings = "select count(cid) from code_av where id=?"  # Not used
        sql_image_codings = "select count(cid) from code_image where id=?"  # Not used
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
                item = self.ui.treeWidget.selectedItems()[0]
                self.selected_code_ids = self._get_codes_from_tree(item)
                self.selected_code_name = item.text(0)
                if self.ui.checkBox_send_memos.isChecked():
                    self.selected_code_memo = item.toolTip(2)
                else:
                    self.selected_code_memo = ''
                self.include_coded_segments = self.ui.checkBox_coded_segments.isChecked()
                item = item.parent()
                while item is not None and not isinstance(item, QtWidgets.QTreeWidget):
                    self.selected_code_name = f'{item.text(0)} > {self.selected_code_name}'
                    item = item.parent()               
        else:  # free search selected
            self.selected_code_ids = None
            self.selected_code_name = self.ui.lineEdit_free_topic.text()
            if self.selected_code_name == '':
                msg = _('Please enter text in the "topic" field.')
                Message(self.app, _('No codes'), msg, "warning").exec()
                return
            self.selected_code_memo = self.ui.textEdit_free_description.toPlainText()
        
        # File selection
        self.selected_file_ids = []
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
        
        # case filter
        if not self.ui.listWidget_cases.item(0).isSelected(): 
            # Only apply case filter if the first item (<no case filter>)  
            # is not selected.
            # The case filter will delete all files from self.selected_file_ids that 
            # do not belong to the selected cases. 
            selected_cases = []
            for item in self.ui.listWidget_cases.selectedItems():
                id_ = item.data(Qt.ItemDataRole.UserRole)
                if id_ > -1:
                    selected_cases.append(id_)
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

        if len(self.selected_file_ids) == 0:
            msg = _('After combining all filters, there are not files left for the search. Please check your settings.')
            Message(self.app, _('No files'), msg, "warning").exec()
            return
        
        # Save the settings for the next search
        self.app.settings[f'ai_dlg_{self.context}_last_prompt_name'] = self.current_prompt.name
        self.app.settings[f'ai_dlg_{self.context}_last_prompt_scope'] = self.current_prompt.scope
        if self.context == 'search':
            self.app.settings[f'ai_dlg_{self.context}_last_tab_index'] = self.ui.tabWidget.currentIndex()
        self.app.settings[f'ai_dlg_{self.context}_free_topic'] = self.ui.lineEdit_free_topic.text()
        self.app.settings[f'ai_dlg_{self.context}_free_description'] = self.ui.textEdit_free_description.toPlainText().replace('\n', '\\n')
        self.app.settings[f'ai_dlg_{self.context}_last_splitter_code_tree'] = self.ui.splitter_code_tree.sizes()[0]
        self.app.settings[f'ai_dlg_{self.context}_last_splitter_case_files'] = self.ui.splitter_case_files.sizes()[0]
        self.app.settings[f'ai_dlg_{self.context}_send_memos'] = 'True' if self.ui.checkBox_send_memos.isChecked() else 'False'
        self.app.settings[f'ai_dlg_{self.context}_coded_segments'] = 'True' if self.ui.checkBox_coded_segments.isChecked() else 'False'
        self.accept()
        
    def cancel(self):
        self.selected_code_name = ''
        self.selected_code_memo = ''
        self.selected_file_ids = []
        self.reject()

