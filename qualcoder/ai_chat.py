# -*- coding: utf-8 -*-

"""
Copyright (c) 2023 Colin Curtain

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

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
"""

from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor, QPalette

import datetime
import logging
import os
import re
import sqlite3
import sys
import traceback

from .GUI.ui_ai_chat import Ui_Dialog_ai_chat
from .helpers import Message

from langchain.llms import OpenAI
from langchain.chat_models import ChatOpenAI

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)

def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception: ") + text)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 12pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(text)
    mb.exec()


class DialogAIChat(QtWidgets.QDialog):
    """ AI chat window
    """

    app = None
    parent_textEdit = None
    filepath = ""
    header = []
    data = []

    def __init__(self, app, parent_text_edit):
        """ Need to comment out the connection accept signal line in ui_Dialog_Import.py.
         Otherwise, get a double-up of accept signals. """

        sys.excepthook = exception_handler
        self.app = app
        self.parent_textEdit = parent_text_edit
        self.filepath = ""
        # Set up the user interface from Designer.
        QtWidgets.QDialog.__init__(self)
        self.ui = Ui_Dialog_ai_chat()
        self.ui.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~QtCore.Qt.WindowType.WindowContextHelpButtonHint)
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.ui.plainTextEdit_question.installEventFilter(self)
        self.ui.pushButton_question.pressed.connect(self.send_question)
        self.ui.plainTextEdit_question.setPlaceholderText(_('<your question>'))
        self.ui.scrollArea_ai_output.verticalScrollBar().rangeChanged.connect(self.ai_output_bottom)
        # palette = self.ui.plainTextEdit_question.palette()
        # background_color = self.property("background-color")
        # bg_color = self.palette().base().color().name()
        # print(background_color)
        # self.ui.ai_output.setStyleSheet(f'background-color: {background_color}; ')
        doc_font = 'font: ' + str(self.app.settings['docfontsize']) + 'pt '
        doc_font += '"' + self.app.settings['font'] + '";'
        self.ai_response_style = "'" + doc_font + " color: #356399;'"     
        self.ai_user_style = "'" + doc_font + " color: #35998A; '"
        self.ui.plainTextEdit_question.setStyleSheet(self.ai_user_style[1:-1])
        
        #messages
        self.ai_welcome_message = f'<p style={self.ai_response_style}>Hi there, how can I help you with your research?</p>'
        self.ai_offline_messsage = f'<p style={self.ai_response_style}>The AI is sleeping (not connected).</p>'
        self.ai_api_key_missing = f"""<p style={self.ai_response_style}>API-Key misssing: In order to use the AI integration, you'll need an API-key from OpenAI 
                                and you have to enter this key in the settings-dialog of qualcoder.
                                Visit this page for more information on how to get an API-key: <a href=https://platform.openai.com/account/api-keys>https://platform.openai.com/account/api-keys</a></p>"""
        self.ai_disabled = f"<p style={self.ai_response_style}>In order to use the AI-integration in qualcoder, you have to enable it in the settings.</p>"
        
        self.alive = None # becomes True if the connection to the LLM api is established 
        self.init_llm()

    def ai_output_bottom(self, minVal=None, maxVal=None):
        self.ui.scrollArea_ai_output.verticalScrollBar().setValue(self.ui.scrollArea_ai_output.verticalScrollBar().maximum())
            
    def append_ai_output(self, html):
        self.ui.ai_output.setText(self.ui.ai_output.text() + html) #  .append(html)
        self.ui.ai_output.update()
        
        self.ui.scrollArea_ai_output.ensureVisible(0, 2147483647)
        #self.ui.scrollArea_ai_output.verticalScrollBar().setValue(self.ui.scrollArea_ai_output.verticalScrollBar().maximum())
        
    def init_llm(self):
        if self.app.settings['ai_enable'] == 'True':
            if self.app.settings['open_ai_api_key'] != '':
                self.llm = OpenAI(openai_api_key = self.app.settings['open_ai_api_key'])
                self.chat_model = ChatOpenAI(model='gpt-3.5-turbo')
                self.set_alive(True, True)
            else:
                self.llm = None
                self.chat_model = None
                self.set_alive(False, True)
                self.append_ai_output(self.ai_api_key_missing)
        else:
            self.llm = None
            self.chat_model = None
            self.set_alive(False, True)
            self.append_ai_output(self.ai_disabled)
            
    def set_alive(self, alive, force_ui_update=False):
        if alive != self.alive or force_ui_update:
            self.alive = alive
            self.ui.plainTextEdit_question.setEnabled(alive)
            self.ui.pushButton_question.setEnabled(alive)
            if alive:
                self.append_ai_output(self.ai_welcome_message)
            else:
                self.append_ai_output(self.ai_offline_messsage)
    
    def send_question(self):  
        if self.alive:
            q = self.ui.plainTextEdit_question.toPlainText()
            q_html = f'<p style={self.ai_user_style}>{q}</p>'          
            self.append_ai_output(q_html)
            self.ui.plainTextEdit_question.clear()
            r = self.chat_model.predict(q) # better make an asynch call, other wise the ui freezes until the response is ready
            rx = """Certainly! Here are some potential questions to ask yourself during the analysis of interviews for exploring the meaning of work for women in the post-war era:

1. What were the primary motivations for women to enter the workforce during the post-war era?
2. How did women perceive their roles and responsibilities at work compared to their roles in the household?
3. Did women feel that their work was valued and recognized by society during this time?
4. Were there any specific challenges or barriers that women faced in pursuing their careers during the post-war era?
5. How did women navigate and balance their work and family life during this time period?
6. Did women feel a sense of empowerment or liberation through their work, or did they experience any feelings of constraint or limitation?
7. What were the prevailing societal norms and expectations regarding women's work during the post-war era, and how did these influence individual experiences?
8. How did women perceive the impact of their work on their personal identity and self-worth?
9. Were there any notable differences in the meaning of work for women from different socio-economic backgrounds or geographic locations?
10. How did women's experiences and perspectives on work evolve and change throughout the post-war era?

Remember to tailor these questions based on the specific context and objectives of your research project. Additionally, adapt and refine your questions as you progress through the analysis of the interviews to ensure a comprehensive exploration of the topic.

            """
            r= r.replace('\n', '<br />')
            self.append_ai_output(f'<p style={self.ai_response_style}>{r}</p>')
            # self.append_ai_output(f'<table><tr><td style="padding: 6px; border-width: 3px; border-color: #F4F4F4; background-color: #F4F4F4">{r}</td></tr></table>')
       
    def keyReleaseEvent(self, event):
        if event.key() == QtCore.Qt.Key.Key_Return and self.ui.plainTextEdit_question.hasFocus():
            self.send_question()



