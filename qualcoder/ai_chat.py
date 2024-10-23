# -*- coding: utf-8 -*-

"""
Copyright (c) 2024 Kai Droege, Colin Curtain

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

Author: Kai Droege (kaixxx)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
"""

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QCursor, QGuiApplication, QTextCursor, QPalette  # Kai: QTextCurosr, QPalette - Unused
from PyQt6.QtWidgets import QTextEdit
from PyQt6.QtGui import QKeySequence, QPixmap, QIcon  # Kai Unused
import qtawesome as qta

from langchain_core.messages.human import HumanMessage
from langchain_core.messages.ai import AIMessage
from langchain_core.messages.system import SystemMessage
from langchain_core.callbacks.base import BaseCallbackHandler

from datetime import datetime
import json
import logging
import os
import sqlite3

from .ai_search_dialog import DialogAiSearch
from .GUI.ui_ai_chat import Ui_Dialog_ai_chat
from .GUI.base64_helper import *  # Kai Unused
from .helpers import Message

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


class DialogAIChat(QtWidgets.QDialog):
    """ AI chat window
    """    
    app = None
    parent_textEdit = None
    chat_history_conn = None
    current_chat_idx = -1
    current_streaming_chat_idx = -1
    chat_msg_list = [] 
    is_updating_chat_window = False
    ai_semantic_search_chunks = []
    # filenames = []

    def __init__(self, app, parent_text_edit: QTextEdit, main_window: QtWidgets.QMainWindow):

        self.app = app
        self.parent_textEdit = parent_text_edit
        self.main_window = main_window
        # Set up the user interface from Designer.
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_ai_chat()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        self.ui.plainTextEdit_question.installEventFilter(self)
        self.ui.pushButton_question.pressed.connect(self.button_question_clicked)
        self.ui.progressBar_ai.setMaximum(100)
        self.ui.plainTextEdit_question.setPlaceholderText(_('<your question>'))
        self.ui.pushButton_new_analysis.clicked.connect(self.button_new_clicked)
        self.ui.pushButton_delete.clicked.connect(self.delete_chat)
        self.ui.listWidget_chat_list.itemSelectionChanged.connect(self.chat_list_selection_changed)
        # Enable editing of items on double click and when pressing F2
        self.ui.listWidget_chat_list.setEditTriggers(QtWidgets.QListWidget.EditTrigger.DoubleClicked | QtWidgets.QListWidget.EditTrigger.EditKeyPressed)
        self.ui.listWidget_chat_list.itemChanged.connect(self.chat_list_item_changed)
        self.ui.ai_output.linkHovered.connect(self.on_linkHovered)
        self.ui.ai_output.linkActivated.connect(self.on_linkActivated)
        self.init_styles()
        self.ai_busy_timer = QtCore.QTimer(self)
        self.ai_busy_timer.timeout.connect(self.update_ai_busy)
        self.ai_busy_timer.start(100)

    def init_styles(self):
        """Set up the stylesheets for the ui and the chat entries
        """
        self.font = f'font: {self.app.settings["fontsize"]}pt "{self.app.settings["font"]}";'
        self.setStyleSheet(self.font)
        # Set progressBar color to default highlight color
        self.ui.progressBar_ai.setStyleSheet(f"""
            QProgressBar::chunk {{
                background-color: {self.app.highlight_color()};
            }}
        """)
        doc_font = f'font: {self.app.settings["docfontsize"]}pt \'{self.app.settings["font"]}\';'
        self.ai_response_style = f'"{doc_font} color: #356399;"'
        self.ai_user_style = f'"{doc_font} color: #287368;"'
        self.ai_info_style = f'"{doc_font}"'
        if self.app.settings['stylesheet'] in ['dark', 'rainbow']:
            self.ai_response_style = f'"{doc_font} color: #8FB1D8;"'
            self.ai_user_style = f'"{doc_font} color: #35998A;"'
            self.ai_info_style = f'"{doc_font}"'
        elif self.app.settings['stylesheet'] == 'native':
            # Determine whether dark or light native style is active:
            style_hints = QGuiApplication.styleHints()
            # Older versions fot PyQt6 may not have QGuiApplication.styleHints().colorScheme() e.g. PtQ66 vers 6.2.3
            try:
                if style_hints.colorScheme() == QtCore.Qt.ColorScheme.Dark:
                    self.ai_response_style = f'"{doc_font} color: #8FB1D8;"'
                    self.ai_user_style = f'"{doc_font} color: #35998A;"'
                    self.ai_info_style = f'"{doc_font}"'
                else:
                    self.ai_response_style = f'"{doc_font} color: #356399;"'
                    self.ai_user_style = f'"{doc_font} color: #287368;"'
                    self.ai_info_style = f'"{doc_font}"'
            except AttributeError as e_:
                print(f"Using older version of PyQT6? {e_}")
                logger.debug(f"Using older version of PyQT6? {e_}")
                pass
        else:
            self.ai_response_style = f'"{doc_font} color: #356399;"'
            self.ai_user_style = f'"{doc_font} color: #287368;"'
            self.ai_info_style = f'"{doc_font}"'
        self.ui.plainTextEdit_question.setStyleSheet(self.ai_user_style[1:-1])
        default_bg_color = self.ui.plainTextEdit_question.palette().color(self.ui.plainTextEdit_question.viewport().backgroundRole())
        self.ui.ai_output.setStyleSheet(doc_font)
        self.ui.ai_output.setAutoFillBackground(True)
        self.ui.ai_output.setStyleSheet('QWidget:focus {border: none;}')
        self.ui.ai_output.setStyleSheet(f'background-color: {default_bg_color.name()};')
        self.ui.scrollArea_ai_output.setStyleSheet(f'background-color: {default_bg_color.name()};')
        self.update_chat_window()
        
    def init_ai_chat(self, app=None):
        if app is not None:
            self.app = app
        # init chat history
        self.chat_history_folder = self.app.project_path + '/ai_data'
        if not os.path.exists(self.chat_history_folder):
            os.makedirs(self.chat_history_folder)
        self.chat_history_path = self.chat_history_folder + '/chat_history.sqlite'            
        self.chat_history_conn = sqlite3.connect(self.chat_history_path)
        cursor = self.chat_history_conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS chats (
                                id INTEGER PRIMARY KEY,
                                name TEXT,
                                analysis_type TEXT,
                                summary TEXT,
                                date TEXT,
                                analysis_prompt TEXT)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS chat_messages (
                                id INTEGER PRIMARY KEY,
                                chat_id INTEGER,
                                msg_type TEXT,
                                msg_author TEXT,
                                msg_content TEXT,
                                FOREIGN KEY (chat_id) REFERENCES chats(id))''')
        self.chat_history_conn.commit()
        self.current_chat_idx = -1
        self.fill_chat_list()
    
    def close(self):
        if self.chat_history_conn is not None:
            self.chat_history_conn.close()

    def get_chat_list(self):
        """Load the current chat list from the database into self.chat_list
        """
        cursor = self.chat_history_conn.cursor()
        cursor.execute('SELECT id, name, analysis_type, summary, date, analysis_prompt FROM chats ORDER BY date DESC')
        self.chat_list = cursor.fetchall()
        if self.current_chat_idx >= len(self.chat_list):
            self.current_chat_idx = len(self.chat_list) - 1    
            
    def fill_chat_list(self):
        self.ui.listWidget_chat_list.clear()
        self.get_chat_list()
        for i in range(len(self.chat_list)):
            chat = self.chat_list[i]
            id_, name, analysis_type, summary, date, analysis_prompt = chat
            tooltip_text = f"{name}\nType: {analysis_type}\nSummary: {summary}\nDate: {date}\nPrompt: {analysis_prompt}"

            # Creating a new QListWidgetItem
            if analysis_type == 'general chat':
                icon = self.app.ai.general_chat_icon()
            elif analysis_type == 'topic chat':
                icon = self.app.ai.topic_analysis_icon()
            else:  # code chat
                icon = self.app.ai.code_analysis_icon()

            item = QtWidgets.QListWidgetItem(icon, name)
            item.setToolTip(tooltip_text)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
            
            # Adding the item to the QListWidget
            self.ui.listWidget_chat_list.addItem(item)
            #if i == self.current_chat_idx:
            #    item.setSelected(True)
        if self.current_chat_idx >= len(self.chat_list):
            self.current_chat_idx = len(self.chat_list) - 1
        self.ui.listWidget_chat_list.setCurrentRow(self.current_chat_idx)
        self.chat_list_selection_changed(force_update=True)

    def new_chat(self, name, analysis_type, summary, analysis_prompt):
        date = datetime.now()
        date_text = date.strftime('%Y-%m-%d %H:%M:%S')
        cursor = self.chat_history_conn.cursor()
        cursor.execute('''INSERT INTO chats (name, analysis_type, summary, date, analysis_prompt)
                            VALUES (?, ?, ?, ?, ?)''', (name, analysis_type, summary, date_text, analysis_prompt))
        self.chat_history_conn.commit()
        self.current_chat_idx = -1
        self.fill_chat_list()
        # select new chat
        self.current_chat_idx = self.find_chat_idx(cursor.lastrowid)
        self.ui.listWidget_chat_list.setCurrentRow(self.current_chat_idx)
        self.chat_list_selection_changed()

    def new_general_chat(self, name, summary):
        if self.app.project_name == "":
            msg = _('No project open.')
            Message(self.app, _('AI not enabled'), msg, "warning").exec()
            return
        if self.app.settings['ai_enable'] != 'True':
            msg = _('The AI is disabled. Go to "AI > Setup Wizard" first.')
            Message(self.app, _('AI not enabled'), msg, "warning").exec()
            return

        self.new_chat(name, 'general chat', summary, '')
        self.process_message('system', self.app.ai.get_default_system_prompt())
        self.update_chat_window()  
             
    def new_code_chat(self):
        """chat about codings"""
        if self.app.project_name == "":
            msg = _('No project open.')
            Message(self.app, _('AI not enabled'), msg, "warning").exec()
            return
        if self.app.settings['ai_enable'] != 'True':
            msg = _('The AI is disabled. Go to "AI > Setup Wizard" first.')
            Message(self.app, _('AI not enabled'), msg, "warning").exec()
            return
       
        ui = DialogAiSearch(self.app, 'code_analysis')
        ret = ui.exec()
        if ret == QtWidgets.QDialog.DialogCode.Accepted:
            self.ai_search_code_name = ui.selected_code_name
            self.ai_search_code_memo = ui.selected_code_memo
            #self.ai_include_coded_segments = ui.include_coded_segments
            self.ai_search_file_ids = ui.selected_file_ids
            self.ai_search_code_ids = ui.selected_code_ids
            self.ai_prompt = ui.current_prompt
            
            file_ids_str = str(self.ai_search_file_ids).replace('[', '(').replace(']', ')')
            code_ids_str = str(self.ai_search_code_ids).replace('[', '(').replace(']', ')')
                        
            # fetch data
            #sql = f'SELECT * FROM code_text WHERE cid IN {code_ids_str} AND fid IN {file_ids_str}'
            
            # This SQL sorts the results by file id, but not like 1, 1, 1, 2, 2, 3... 
            # Instead, the results are mixed up in this order: file id = 1, 2, 3, 1, 2, 1...
            # This tries to ensure that even if the data send to the AI must be cut off at some point 
            # because of the token limit, there will at least be data from as many different files as 
            # possible included in the analysis.
            # The JOIN also adds the source.name so that the AI can refer to a certain document
            # by its name.     
            sql = f"""
                SELECT ordered.*, source.name
                FROM (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY fid ORDER BY ctid) as rn
                FROM code_text
                WHERE cid IN {code_ids_str} AND fid IN {file_ids_str}
                ) AS ordered
                JOIN source ON ordered.fid = source.id
                ORDER BY ordered.rn, ordered.fid;
                """
            cursor = self.app.conn.cursor()
            cursor.execute(sql)
            self.curr_codings = cursor.fetchall()
            
            ai_data = []
            # Limit the amount of data (characters) send to the ai, so the maximum context window is not exceeded.
            # As a rough estimation, one token is about 4 characters long (in english). 
            # We want to fill not more than half the context window with our data, so that there is enough
            # room for the answer and further chats.
            max_ai_data_length = round(0.5 * (self.app.ai.large_llm_context_window * 4)) 
            max_ai_data_length_reached = False
            ai_data_length = 0
            for row in self.curr_codings:
                if ai_data_length >= max_ai_data_length:
                    max_ai_data_length_reached = True
                    break
                ai_data.append({
                    'source_id': row[0],
                    'source_name': row[12],
                    'quote': row[3]
                })
                ai_data_length = ai_data_length + len(row[3])
            ai_data_json = json.dumps(ai_data)
            
            ai_instruction = (
                f'You are discussing the code named "{self.ai_search_code_name}" with the following code memo: "{self.ai_search_code_memo}". \n'
                f'Here is a list of quotes from the empirical data that have been coded with the given code:\n'
                f'{ai_data_json}\n'
                f'Your task is to analyze the given empirical data following these instructions: {self.ai_prompt.text}\n'
                f'The whole discussion should be based upon the the empirical data provided and its proper interpretation. '
                f'Do not make any assumptions which are not supported by the data. '
                f'Please mention the sources that your refer to from the given empirical data, using an html anchor tag of the following form: '
                '<a href="coding:{source_id}">{source_name}</a>\n' 
                f'Always answer in the following language: "{self.app.ai.get_curr_language()}".'
            )    
            
            summary = f'Analyzing the data coded as "{self.ai_search_code_name}" ({len(ai_data)} pieces of data sent to the AI.)'
            if max_ai_data_length_reached:
                summary += f'\nATTENTION: There was more coded data found, but it had to be truncated because of the limited context window of the AI.'
            logger.debug(f'New code chat. Prompt:\n{ai_instruction}')
            self.new_chat(f'Code "{self.ai_search_code_name}"', 'code chat', summary, self.ai_prompt.name_and_scope())
            self.process_message('system', self.app.ai.get_default_system_prompt())
            self.process_message('instruct', ai_instruction)
            self.update_chat_window()  
 
    def new_topic_chat(self):
        """chat about a free topic in the data"""
        if self.app.project_name == "":
            msg = _('No project open.')
            Message(self.app, _('AI not enabled'), msg, "warning").exec()
            return
        if self.app.settings['ai_enable'] != 'True':
            msg = _('The AI is disabled. Go to "AI > Setup Wizard" first.')
            Message(self.app, _('AI not enabled'), msg, "warning").exec()
            return
       
        ui = DialogAiSearch(self.app, 'topic_analysis')
        ret = ui.exec()
        if ret == QtWidgets.QDialog.DialogCode.Accepted:
            self.ai_search_code_name = ui.selected_code_name
            self.ai_search_code_memo = ui.selected_code_memo
            
            self.ai_search_file_ids = ui.selected_file_ids
            self.ai_prompt = ui.current_prompt
            # self.filenames = self.app.get_filenames()
            
            summary = f'Analyzing the free topic "{self.ai_search_code_name}" in the data.\nDescription: {self.ai_search_code_memo}'
            logger.debug(f'New topic chat.')
            self.new_chat(f'Topic "{self.ai_search_code_name}"', 'topic chat', summary, self.ai_prompt.name_and_scope())
            self.process_message('system', self.app.ai.get_default_system_prompt())
            self.process_message('info', _('Searching for related data...'))
            self.update_chat_window()  

            self.app.ai.retrieve_similar_data(self.new_topic_chat_callback,  
                                            self.ai_search_code_name, self.ai_search_code_memo,
                                            self.ai_search_file_ids)

    def get_filename(self, id_) -> str:
        """Return the filename for a source id
        Args:
            id_: source id
        Returns:
            str: name | '' if nothing found
        """
        # This might be called from a different thread (ai asynch operations), so have to create a new database connection
        conn = sqlite3.connect(os.path.join(self.app.project_path, 'data.qda'))
        cur = conn.cursor()
        cur.execute(f'select name from source where id = {id_}')
        res = cur.fetchone()[0]
        if res is not None:
            return res
        else:
            return ''

    def new_topic_chat_callback(self, chunks):
        # Analyze the data found
        if self.app.ai.ai_async_is_canceled:
            self.process_message('info', _('Chat has been canceled by the user.'))
            self.update_chat_window()  
            return
        if chunks is None or len(chunks) == 0:
            msg = _('Sorry, the AI could could not find any data related to "') + self.ai_search_code_name + '".'
            self.process_message('info', msg)
            self.update_chat_window()  
            return
        
        self.ai_semantic_search_chunks = chunks                
        topic_analysis_max_chunks = 30
        msg = _('Found ') + str(len(chunks)) + _(' chunks of data which might be related to the topic. Analyzing the first ') + str(topic_analysis_max_chunks) + _(' chunks closer.')
        self.process_message('info', msg)
        self.update_chat_window()

        ai_data = []
        max_ai_data_length = round(0.5 * (self.app.ai.large_llm_context_window * 4)) 
        max_ai_data_length_reached = False
        ai_data_length = 0
        for i in range(0, topic_analysis_max_chunks):
            if i >= len(chunks): 
                break
            if ai_data_length >= max_ai_data_length:
                max_ai_data_length_reached = True
                break
            chunk = chunks[i]
            ai_data.append({
                'source_id': f'{chunk.metadata["id"]}_{chunk.metadata["start_index"]}_{len(chunk.page_content)}',
                'source_name': self.get_filename(int(chunk.metadata['id'])),
                'quote': chunk.page_content
            })
            ai_data_length += len(chunk.page_content)
        
        ai_data_json = json.dumps(ai_data)
            
        ai_instruction = (
            f'You are analyzing the topic "{self.ai_search_code_name}" with the following description: "{self.ai_search_code_memo}". \n'
            f'A semantic search in the empirical data resulted in the the following list of chunks of empirical data which might be relevant '
            f'for the analysis of the given topic:\n'   
            f'{ai_data_json}\n'
            f'Your task is to analyze the given empirical data following these instructions: {self.ai_prompt.text}\n'
            f'The whole discussion should be based updon the the empirical data provided and its proper interpretation. '
            f'Do not make any assumptions which are not supported by the data. '
            f'Please mention the sources that your refer to from the given empirical data, using an html anchor tag of the following form: '
            '<a href="chunk:{source_id}">{source_name}</a>\n' 
            f'Always answer in the following language: "{self.app.ai.get_curr_language()}".'
        )    
        logger.debug(f'Topic chat prompt:\n{ai_instruction}')
        self.process_message('instruct', ai_instruction)
        self.update_chat_window()   
        
    def delete_chat(self):
        """Deletes the currently selected chat, connected to the button
           'pushButton_delete'
        """
        if self.current_chat_idx <= -1:
            return
        chat_id = int(self.chat_list[self.current_chat_idx][0])
        cursor = self.chat_history_conn.cursor()
        try:
            cursor.execute('DELETE from chat_messages WHERE chat_id = ?', (chat_id,))
            cursor.execute('DELETE from chats WHERE id = ?', (chat_id,))
            self.chat_history_conn.commit()
        except Exception as e_:
            print(e_)
            self.chat_history_conn.rollback()
            raise
        self.fill_chat_list()

    def find_chat_idx(self, chat_id) -> int | None:
        """Returns the index of the chat with the id 'chat_id' in self.chat_list
        """
        if chat_id is None:
            return None 
        for i in range(len(self.chat_list)):
            if self.chat_list[i][0] == chat_id:
                return i
        return None    
    
    def update_ai_busy(self):
        """update question button + progress bar"""
        if self.app.ai is None or not self.app.ai.is_busy():
            self.ui.pushButton_question.setIcon(qta.icon('mdi6.message-fast-outline', color=self.app.highlight_color()))
            self.ui.pushButton_question.setToolTip(_('Send your question to the AI'))
            self.ui.progressBar_ai.setRange(0, 100)  # Stops the animation
        else:
            if self.ui.progressBar_ai.maximum() > 0: 
                spin_icon = qta.icon("mdi.loading", color=self.app.highlight_color(), animation=qta.Spin(self.ui.pushButton_question))
                self.ui.pushButton_question.setIcon(spin_icon)
                self.ui.pushButton_question.setToolTip(_('Cancel AI generation'))
                self.ui.progressBar_ai.setRange(0, 0)  # Starts the animation
        # update ai status in the statusBar of the main window
        if self.app.ai is not None:
            self.main_window.statusBar().showMessage(_('AI: ') + _(self.app.ai.get_status()))
        else: 
            self.main_window.statusBar().showMessage('')

    def update_chat_window(self, scroll_to_bottom=True):
        """load current chat into self.ai_output"""
        if self.current_chat_idx > -1:
            self.is_updating_chat_window = True
            try:
                html = ''
                self.ui.plainTextEdit_question.setEnabled(True)
                self.ui.pushButton_question.setEnabled(True)
                chat = self.chat_list[self.current_chat_idx]
                id_, name, analysis_type, summary, date, analysis_prompt = chat
                self.ui.ai_output.setText('')  # Clear chat window
                # Show title
                html += (f'<h1 style={self.ai_info_style}>{name}</h1>')
                summary_br = summary.replace('\n', '<br />')
                html += (f"<p style={self.ai_info_style}><b>{_('Type:')}</b> {analysis_type}<br /><b>{_('Summary:')}</b> {summary_br}<br /><b>{_('Date:')}</b> {date}<br /><b>{_('Prompt:')}</b> {analysis_prompt}<br /></p>")
                # Show chat messages:
                for msg in self.chat_msg_list:
                    if msg[2] == 'user':
                        txt = msg[4].replace('\n', '<br />')
                        author = msg[3]
                        if author is None or author == '':
                            author = 'unkown'
                        txt = f'<b>{_("User")} ({author}):</b><br />{txt}'
                        html += f'<p style={self.ai_user_style}>{txt}</p>'
                    elif msg[2] == 'ai':
                        txt = msg[4].replace('\n', '<br />')
                        author = msg[3]
                        if author is None or author == '':
                            author = 'unkown'
                        txt = f'<b>{_("AI")} ({author}):</b><br />{txt}'                        
                        html += f'<p style={self.ai_response_style}>{txt}</p>'
                    elif msg[2] == 'info':
                        txt = msg[4].replace('\n', '<br />')
                        txt = '<b>' + _('Info:') + '</b><br />' + txt
                        html += f'<p style={self.ai_info_style}>{txt}</p>'
                # add partially streamed ai response if needed
                if len(self.app.ai.ai_streaming_output) > 0:
                    txt = self.app.ai.ai_streaming_output.replace('\n', '<br />')
                    author = self.app.ai_models[int(self.app.settings['ai_model_index'])]['name']
                    if author is None or author == '':
                        author = 'unkown'
                    txt = f'<b>AI ({author}):</b><br />{txt}'                        
                    html += f'<p style={self.ai_response_style}>{txt}</p>'
                self.ui.ai_output.setText(html)
            finally:
                if scroll_to_bottom:
                    self.ai_output_scroll_to_bottom()
                self.is_updating_chat_window = False
        else:
            self.ui.ai_output.setText('')
            self.ui.plainTextEdit_question.setEnabled(False)
            self.ui.pushButton_question.setEnabled(False)
            
    def chat_list_selection_changed(self, force_update=False):
        self.ui.pushButton_delete.setEnabled(self.current_chat_idx > -1)
        if (not force_update) and (self.current_chat_idx == self.ui.listWidget_chat_list.currentRow()):
            return
        if self.app.ai.cancel(True):
            # AI generation is either finished or canceled, we can change to another chat
            self.current_chat_idx = self.ui.listWidget_chat_list.currentRow()
            self.ui.pushButton_delete.setEnabled(self.current_chat_idx > -1)
            self.history_update_message_list()
            self.update_chat_window(scroll_to_bottom=False)
        else:  # return to previous chat
            self.ui.listWidget_chat_list.setCurrentRow(self.current_chat_idx)
        
    def chat_list_item_changed(self, item: QtWidgets.QListWidgetItem):
        """This method is called whenever the name of a chat is edited in the list"""
        chat_id = self.chat_list[self.current_chat_idx][0]
        curr_name = item.text()
        cursor = self.chat_history_conn.cursor()
        cursor.execute('UPDATE chats SET name = ? WHERE id = ?', (curr_name, chat_id))
        self.chat_history_conn.commit()
        self.get_chat_list()
        self.update_chat_window()

    def button_new_clicked(self):
        # Create QMenu
        menu = QtWidgets.QMenu()
        menu.setStyleSheet(self.font)

        # Add actions
        action_codings_analysis = menu.addAction(_('New code chat'))
        action_codings_analysis.setIcon(self.app.ai.code_analysis_icon())
        action_codings_analysis.setToolTip(_('Start chatting about the data in the codings for a particular code.'))
        action_topic_analysis = menu.addAction(_('New topic chat'))
        action_topic_analysis.setIcon(self.app.ai.topic_analysis_icon())
        action_topic_analysis.setToolTip(_('Start chatting about data related to a free-search topic.'))
        action_general_chat = menu.addAction(_('New general chat'))
        action_general_chat.setIcon(self.app.ai.general_chat_icon())
        action_general_chat.setToolTip(_('Ask the AI anything, not related to your data.'))

        # Obtain the bottom-left point of the button in global coordinates
        buttonRect = self.ui.pushButton_new_analysis.rect()  # Get the button's rect
        bottomLeftPoint = buttonRect.bottomLeft()  # Bottom-left point
        globalBottomLeftPoint = self.ui.pushButton_new_analysis.mapToGlobal(bottomLeftPoint)  # Map to global

        # Execute the menu at the calculated position
        action = menu.exec(globalBottomLeftPoint)

        # Check which action was selected and do something
        if action == action_codings_analysis:
            self.new_code_chat()
        elif action == action_topic_analysis:
            self.new_topic_chat()
        elif action == action_general_chat:
            self.new_general_chat('New general chat', '')

    def ai_output_scroll_to_bottom(self, minVal=None, maxVal=None):
        # Delay the scrolling a little to make sure that the updated text is fully rendered before scrolling to the bottom: 
        QtCore.QTimer.singleShot(0, self._ai_output_scroll_to_bottom)
        
    def _ai_output_scroll_to_bottom(self):
        self.ui.scrollArea_ai_output.ensureVisible(0, self.ui.scrollArea_ai_output.widget().height())
                                
    def history_update_message_list(self, db_conn=None):
        """Update sel.chat_msg_list from the database

        Args:
            db_conn: database conncetion, if None, use defaults to self.chat:history_conn
        """
        if self.current_chat_idx > -1:
            curr_chat_id = self.chat_list[self.current_chat_idx][0]
            if db_conn is None:
                db_conn = self.chat_history_conn 
            cursor = db_conn.cursor()
            cursor.execute('SELECT * FROM chat_messages WHERE chat_id=? ORDER BY id', (curr_chat_id,))
            self.chat_msg_list = cursor.fetchall()
            self.ai_streaming_output = ''
        else:
            self.chat_msg_list.clear()
            self.ai_streaming_output = ''
    
    def history_get_ai_messages(self):
        messages = []
        for msg in self.chat_msg_list:
            if msg[2] == 'system':
                messages.append(SystemMessage(content=msg[4]))
            elif msg[2] == 'instruct' or msg[2] == 'user':
                messages.append(HumanMessage(content=msg[4]))
            elif msg[2] == 'ai':
                messages.append(AIMessage(content=msg[4]))
        return messages
    
    def history_add_message(self, msg_type, msg_author, msg_content, chat_idx=None, db_conn=None):
        self.ai_streaming_output = ''
        if chat_idx is None:
            chat_idx = self.current_chat_idx
        if chat_idx > -1:
            curr_chat_id = self.chat_list[chat_idx][0]
            if db_conn is None:
                db_conn = self.chat_history_conn
            cursor = db_conn.cursor()
            # insert new message
            cursor.execute('''INSERT INTO chat_messages (chat_id, msg_type, msg_author, msg_content)
                            VALUES (?, ?, ?, ?)''', (curr_chat_id, msg_type, msg_author, msg_content))
            db_conn.commit()
            self.history_update_message_list()
    
    def button_question_clicked(self):
        if self.app.ai.is_busy():
            self.app.ai.cancel(True)
        else:
            self.send_user_question()
                    
    def send_user_question(self):
        if self.app.settings['ai_enable'] != 'True':
            msg = _('The AI is disabled. Go to "AI > Setup Wizard" first.')
            Message(self.app, _('AI not enabled'), msg, "warning").exec()
            return
        elif self.app.ai.is_busy():
            msg = _('The AI is busy generating a response. Click on the button on the right to stop.')
            Message(self.app, _('AI busy'), msg, "warning").exec()
            return
        elif not self.app.ai.is_ready():
            msg = _('The AI not yet fully loaded. Please wait and retry.')
            Message(self.app, _('AI not ready'), msg, "warning").exec()
            return
        q = self.ui.plainTextEdit_question.toPlainText()
        if q != '':
            if self.process_message('user', q):
                self.ui.plainTextEdit_question.clear()
                QtWidgets.QApplication.processEvents()
                        
    def process_message(self, msg_type, msg_content, chat_idx=None) -> bool:
        #if not self.app.ai.is_ready():
        #    msg = _('The AI is busy or not yet fully loaded. Please wait a moment and retry.')
        #    Message(self.app, _('AI not ready'), msg, "warning").exec()
        #    return False
        if chat_idx is None:
            chat_idx = self.current_chat_idx
        if chat_idx <= -1:
            self.ai_streaming_output = ''
            self.chat_msg_list.clear()
            msg = _('Please select a chat or create a new one.')
            Message(self.app, _('Chat selection'), msg, "warning").exec()
            return False
             
        if msg_type == 'info':
            # info messages are only shown on screen, not send to the AI
            self.history_add_message(msg_type, '', msg_content, chat_idx)
            self.update_chat_window()
        elif msg_type == 'system':
            # system messages are only added to the chat history. They are never shown on screen. 
            # The system message will be not be send to the AI immediately, but together with the next user message (as part of the chat history).
            self.history_add_message(msg_type, '', msg_content, chat_idx)
        elif msg_type == 'instruct':
            # instruct messages are only send to the AI, but not shown on screen
            # Other than system messages, instruct messages are send immediatly and will produce an answer that is shown on screen
            if chat_idx == self.current_chat_idx:
                self.history_add_message(msg_type, '', msg_content, chat_idx)
                messages = self.history_get_ai_messages()
                self.current_streaming_chat_idx = self.current_chat_idx
                self.app.ai.ai_async_stream(self.app.ai.large_llm, 
                                            messages, 
                                            result_callback=self.ai_message_callback, 
                                            progress_callback=None, 
                                            streaming_callback=self.ai_streaming_callback, 
                                            error_callback=None)
        elif msg_type == 'user':
            # user question, shown on screen and send to the AI
            if chat_idx == self.current_chat_idx:
                self.history_add_message(msg_type, self.app.settings['codername'], msg_content, chat_idx)
                messages = self.history_get_ai_messages()
                self.current_streaming_chat_idx = self.current_chat_idx
                self.app.ai.ai_async_stream(self.app.ai.large_llm, 
                                            messages, 
                                            result_callback=self.ai_message_callback, 
                                            progress_callback=None, 
                                            streaming_callback=self.ai_streaming_callback, 
                                            error_callback=self.ai_error_callback)
                self.update_chat_window()
        elif msg_type == 'ai':
            # ai responses.
            # create temporary db connection to make it thread safe
            db_conn = sqlite3.connect(self.chat_history_path)
            try: 
                ai_model_name = self.app.ai_models[int(self.app.settings['ai_model_index'])]['name']
                self.history_add_message(msg_type, ai_model_name, msg_content, chat_idx, db_conn)
                self.ai_streaming_output = ''
                self.update_chat_window()
            finally:
                db_conn.close()
        return True    
    
    def ai_streaming_callback(self, streamed_text):
        self.update_chat_window()

    def _send_message(self, messages, progress_callback=None):  
        # callback for async call    
        self.ai_streaming_output = ''
        self.current_streaming_chat_idx = self.current_chat_idx
        for chunk in self.app.ai.large_llm.stream(messages):
            if self.app.ai.ai_async_is_canceled:
                break # cancel the streaming
            elif self.current_chat_idx != self.current_streaming_chat_idx:
                # switched to another chat, cancel also
                break
            else:
                self.ai_streaming_output += str(chunk.content)
                if not self.is_updating_chat_window:
                    self.update_chat_window()
        return self.ai_streaming_output
    
    def ai_message_callback(self, ai_result):
        """Called if the AI has finished sending its response.
        The streamed resonse is now replaced with the final one.
        """
        self.ai_streaming_output = ''
        if ai_result != '':
            self.process_message('ai', ai_result, self.current_streaming_chat_idx)
        else:
            self.process_message('info', _('Error: The AI returned an empty result. This may indicate that the AI model is not available at the moment. Try again later or choose a different model.'), self.current_streaming_chat_idx)
            
    def ai_error_callback(self, exception_type, value, tb_obj):
        """Called if the AI returns an error"""
        self.ai_streaming_output = ''
        self.process_message('info', _('The AI returned an error: ') + str(value), self.current_streaming_chat_idx)    
        raise exception_type(value).with_traceback(tb_obj)  # Re-raise a new exception with the original traceback
    
    def eventFilter(self, source, event):
        # Check if the event is a KeyPress, source is the lineEdit, and the key is Enter
        if (event.type() == QEvent.Type.KeyPress and source is self.ui.plainTextEdit_question and
            (event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter)):
            # Shift + Return/Enter creates a new line. Just pressing Return/Enter sends the question to the AI:
            if not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.send_user_question()
                return True  # Event handled
        # For all other cases, return super's eventFilter result
        return super().eventFilter(source, event)
    
    def on_linkHovered(self, link: str):

        if link:
            # Show tooltip when hovering over a link
            if link.startswith('coding:'):
                try:
                    coding_id = link[len('coding:'):]
                    cursor = self.app.conn.cursor()
                    sql = (f'SELECT code_text.ctid, source.name, code_text.seltext '
                            f'FROM code_text JOIN source ON code_text.fid = source.id '
                            f'WHERE code_text.ctid = {coding_id}')
                    cursor.execute(sql)
                    coding = cursor.fetchone()
                except Exception as e:
                    logger.debug(f'Link: "{link}" - Error: {e}')
                    coding = None                
                if coding is not None:
                    tooltip_txt = f'{coding[1]}:\n'  # file name
                    tooltip_txt += f'"{coding[2]}"'  # seltext
                else:
                    tooltip_txt = _('Invalid source reference.')
                QtWidgets.QToolTip.showText(QCursor.pos(), tooltip_txt, self.ui.ai_output)
            elif link.startswith('chunk:'):
                try:
                    chunk_id = link[len('chunk:'):]
                    source_id, start, length = chunk_id.split('_')
                    cursor = self.app.conn.cursor()
                    sql = f'SELECT name, fulltext FROM source WHERE id = {source_id}'
                    cursor.execute(sql)
                    source = cursor.fetchone()
                except Exception as e:
                    logger.debug(f'Link: "{link}" - Error: {e}')
                    source = None
                if source is not None:
                    tooltip_txt = f'{source[0]}:\n'  # File name
                    # Kai - varriables start and length - referenced before asignment
                    tooltip_txt += f'"{source[1][int(start):int(start) + int(length)]}"'  # Chunk extracted from fulltext
                else:
                    tooltip_txt = _('Invalid source reference.')
                QtWidgets.QToolTip.showText(QCursor.pos(), tooltip_txt, self.ui.ai_output)
        else:
            QtWidgets.QToolTip.hideText()
            
    def on_linkActivated(self, link: str):

        if link:
            # Open doc in coding window 
            if link.startswith('coding:'):
                try:
                    coding_id = link[len('coding:'):]
                    cursor = self.app.conn.cursor()
                    sql = (f'SELECT fid, pos0, pos1 '
                            f'FROM code_text '
                            f'WHERE code_text.ctid = {coding_id}')
                    cursor.execute(sql)
                    coding = cursor.fetchone()
                except Exception as e:
                    logger.debug(f'Link: "{link}" - Error: {e}')
                    coding = None
                if coding is not None:
                    # Kai - Unresolved attribute reference: text_coding - ? identfied by PyCharm
                    self.main_window.text_coding(task='documents', 
                                                 doc_id=int(coding[0]), 
                                                 doc_sel_start=int(coding[1]), 
                                                 doc_sel_end=int(coding[2]))
                else:
                    msg = _('Invalid source reference.')
                    Message(self.app, _('AI Chat'), msg, icon='critical').exec()
            elif link.startswith('chunk:'):
                try:
                    chunk_id = link[len('chunk:'):]
                    source_id, start, length = chunk_id.split('_')
                    end = int(start) + int(length)
                except Exception as e:
                    logger.debug(f'Link: "{link}" - Error: {e}')
                    source_id = None
                if source_id is not None:
                    # Kai - Unresolved attribute refernce text_coding. Identifiied by PyCharm
                    # Kai - start and end refernfed before assignment. Idnetified by PyCharm
                    self.main_window.text_coding(task='documents', 
                                                 doc_id=int(source_id), 
                                                 doc_sel_start=int(start), 
                                                 doc_sel_end=end)
                else:
                    msg = _('Invalid source reference.')
                    Message(self.app, _('AI Chat'), msg, icon='critical').exec()                    

###### Helper:


class LlmCallbackHandler(BaseCallbackHandler):
    def __init__(self, dialog_ai_chat: DialogAIChat):
        self.dialog = dialog_ai_chat
        
    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.dialog.ai_streaming_output += token
        if not self.dialog.is_updating_chat_window:
            self.dialog.update_chat_window()        

