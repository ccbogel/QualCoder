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

Author: Kai Droege (kaixxx)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
"""

import os
import logging
import traceback
from typing import List
import time
from PyQt6 import QtWidgets
from PyQt6 import QtGui
from PyQt6 import QtCore 
import qtawesome as qta

import sqlite3
from .ai_prompts import PromptItem
from langchain_openai import ChatOpenAI
from langchain_core.globals import set_llm_cache
from langchain_community.cache import InMemoryCache
from langchain.pydantic_v1 import BaseModel, Field
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.runnables.config import RunnableConfig
from langchain_core.messages.human import HumanMessage
from langchain_core.messages.ai import AIMessage
from langchain_core.messages.system import SystemMessage
from langchain_core.documents.base import Document
from .ai_async_worker import Worker
from .ai_vectorstore import AiVectorstore
from .GUI.base64_helper import *
from .helpers import Message
import fuzzysearch
import json
import json_repair

max_memo_length = 1500 # maximum length of the memo send to the AI

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
        
class MyCustomSyncHandler(BaseCallbackHandler):
    def __init__(self, ai_llm):
        self.ai_llm = ai_llm
        
    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.ai_llm.ai_async_progress_count += 1
    
# Type for returned list of documents
class LlmAnalyzedData(BaseModel):
    relevance: int = Field(..., 
        description='A score between 0 and 10 indicating how relevant the empirical data in "page_content" is for the analysis of the given code.')
    interpretation: str = Field(..., 
        description='A short explanation how the empirical data in "page_content" relates to the given code code or not.')
    quote: str = Field(..., 
        description=str('A selected quote from the empirical data in "page_content" that contains the part which is most '
                        'relevant for the analysis of the given code. Give back the quote exactly like in the original, including errors. '
                        'Do not change the text in any way.')
    )

class AnalyzedData(LlmAnalyzedData):
    quote_start: int = Field(..., 
        description='The position of the first character of the selected quote within "page_content".')
    metadata: dict = Field(default_factory=dict, 
        description='The metadata of the chunk of empirical data, excactly like in the original JSON.')

# metadata: {'id':xx, 'name':xx, 'start_index':xx}

class LlmAnalyzedDataList(BaseModel):
    """A list of analyzed chunks of empircal data"""
    data: List[AnalyzedData]

class AnalyzedDataList(BaseModel):
    """A list of analyzed chunks of empircal data"""
    data: List[AnalyzedData]

def extract_ai_memo(memo: str) -> str:
    """In any memo, any text after the mark '#####' are considered as personal notes that will not be send to the AI.
    This function extracts the text before this mark (or all text if no marking is found) 

    Args:
        memo (str): memo text

    Returns:
        str: shortened memo for AI
    """
    mark = memo.find('#####')
    if mark > -1:
        return memo[0:mark]
    else:
        return memo
    
class AiLLM():
    """ This manages the communication between qualcoder, the vectorstore 
    and the LLM (large language model, e.g. GPT-4)."""
    app = None
    parent_text_edit = None
    main_window = None
    threadpool: QtCore.QThreadPool = None
    ai_async_is_canceled = False
    ai_async_is_finished = False
    ai_async_is_errored = False
    ai_async_progress_msg = ''
    ai_async_progress_count = -1
    ai_async_progress_max = -1
    _status = ''   
    large_llm = None
    fast_llm = None
    large_llm_context_window = 128000
    fast_llm_context_window = 16385
    ai_streaming_output = ''
    sources_collection = 'qualcoder' # name of the vectorstore collection for source documents
        
    def get_default_system_prompt(self) -> str:
        p =  'You are assisting a team of qualitative social researchers.'
        project_memo = extract_ai_memo(self.app.get_project_memo())
        if self.app.settings.get('ai_send_project_memo', 'True') == 'True' and len(project_memo) > 0:
            p +=  f' Here is some background information about the research project the team is working on:\n{project_memo}'
        return p

    def __init__(self, app, parent_text_edit):
        self.app = app
        self.parent_text_edit = parent_text_edit
        self.threadpool = QtCore.QThreadPool()
        self.threadpool.setMaxThreadCount(1)
        self.sources_vectorstore = None
        # Icons (https://pictogrammers.com/library/mdi/)
        self.code_analysis_icon = qta.icon('mdi6.tag-text-outline', color=self.app.highlight_color)
        self.topic_analysis_icon = qta.icon('mdi6.star-outline', color=self.app.highlight_color)
        self.search_icon = qta.icon('mdi6.magnify', color=self.app.highlight_color)
        self.general_chat_icon = qta.icon('mdi6.chat-question-outline', color=self.app.highlight_color)
        self.prompt_scope_icon = qta.icon('mdi6.folder-open-outline', color=self.app.highlight_color)
        self.prompt_icon = qta.icon('mdi6.script-text-outline', color=self.app.highlight_color)
    
    def init_llm(self, main_window, rebuild_vectorstore=False, enable_ai=False):  
        self.main_window = main_window      
        if enable_ai or self.app.settings['ai_enable'] == 'True':
            self.parent_text_edit.append(_('AI: Starting up...'))
            QtWidgets.QApplication.processEvents() # update ui
            self._status = 'starting'

            # init LLMs
            # set_llm_cache(InMemoryCache())
            if int(self.app.settings['ai_model_index']) < 0:
                self.parent_text_edit.append(_('AI: Please set up the AI model'))

                main_window.change_settings(section='AI', enable_ai=True)
                if int(self.app.settings['ai_model_index']) < 0:
                    # still no model selected, disable AI:
                    self.app.settings['ai_enable'] = 'False'
                    self.parent_text_edit.append(_('AI: No model selected, AI is disabled.'))
                    self._status = ''
                    return
                else: 
                    # Success, model was selected. But since the "change_settings" function will start 
                    # a new "init_llm" anyways, we are going to quit here
                    self.app.settings['ai_enable'] = 'True'
                    return    
            curr_model = self.app.ai_models[int(self.app.settings['ai_model_index'])]
            
            large_model = curr_model['large_model']
            self.large_llm_context_window = int(curr_model['large_model_context_window'])
            fast_model = curr_model['fast_model']
            self.fast_llm_context_window = int(curr_model['fast_model_context_window'])
            api_base = curr_model['api_base']
            api_key = curr_model['api_key']
            if api_key == '':
                msg = "Cannot start the AI, the API-key for the AI model is empty. The AI will be disabled."
                Message(self.app, _('AI API key'), msg).exec()
                self._status = ''
                self.app.settings['ai_enable'] = 'False'
                self.parent_text_edit.append(_('AI: No API key available, AI is disabled.'))
                return
            elif api_key == 'None':
                api_key = ''
            self.large_llm = ChatOpenAI(model=large_model, 
                                openai_api_key=api_key, 
                                openai_api_base=api_base, 
                                cache=False,
                                temperature=0.0,
                                streaming=True
                                )
            self.fast_llm = ChatOpenAI(model=fast_model, 
                                openai_api_key=api_key, 
                                openai_api_base=api_base, 
                                cache=False,
                                temperature=0.0,
                                streaming=True
                                )
            self.ai_streaming_output = ''
            self.app.settings['ai_enable'] = 'True'
            
            # init vectorstore
            if self.sources_vectorstore is None:
                self.sources_vectorstore = AiVectorstore(self.app, self.parent_text_edit, self.sources_collection)
                self.sources_vectorstore.init_vectorstore(rebuild_vectorstore)
            else:
                self._status = ''
                self.parent_text_edit.append(_('AI: Ready'))
        else:
            self.close()
        
    def close(self):
        self._status = 'closing'
        self.cancel(False)
        if self.sources_vectorstore is not None: 
            self.sources_vectorstore.close()
            self.sources_vectorstore = None
        self.large_llm = None
        self.fast_llm = None
        self._status = ''
        
    def cancel(self, ask: bool) -> bool:
        if not self.is_busy():
            return True
        if ask:
            msg = _('Do you really want to cancel the AI operation?')
            msg_box = Message(self.app, 'AI Cancel', msg)
            msg_box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
            reply = msg_box.exec()
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                return False
        # cancel all waiting threads:
        self.threadpool.clear()
        self.ai_async_is_canceled = True
        self.threadpool.waitForDone(5000)
        return True

    def get_status(self) -> str:
        """Return the status of the AI system:
        - 'disabled'
        - 'starting' (in the process of loading all its modules)
        - 'no data' (the vectorstore is not available, propably because no project is open)
        - 'reading data' (in the process of adding empirical douments to its internal memory)
        - 'busy' (in the process of sending a prompt to the LLM and streaming the response)
        - 'ready' (fully loaded and idle, ready for a task)
        - 'closing' (in the process of shutting down)
        """
        if self._status != '':
            return self._status # 'starting' and 'closing' are set by the corresponding procedures
        elif self.app.settings['ai_enable'] != 'True':
            return 'disabled'
        elif self.sources_vectorstore is None:
            return 'no data'
        elif self.sources_vectorstore.ai_worker_running():
            return 'reading data'
        elif self.large_llm is None or self.fast_llm is None:
            return 'starting'
        elif self.threadpool.activeThreadCount() > 0:
            return 'busy'
        else:
            return 'ready'
    
    def is_busy(self) -> bool:
        return self.get_status() == 'busy'
        # return self.threadpool.activeThreadCount() > 0

    def is_ready(self):
        return self.get_status() == 'ready'
        #return (self.sources_vectorstore is not None) and \
        #            (self.sources_vectorstore.is_ready()) and \
        #            (self.large_llm is not None) and \
        #            (self.fast_llm is not None) and \
        #            (not self.is_busy())
    
    def _ai_async_progress(self, msg):
        self.ai_async_progress_msg = self.ai_async_progress_msg + '\n' + msg
        
    def _ai_async_error(self, exception_type, value, tb_obj):
        self.ai_async_is_errored = True
        raise exception_type(value).with_traceback(tb_obj)  # Re-raise
        # exception_handler(exception_type, value, tb_obj)

    def _ai_async_finished(self):
        self.ai_async_is_finished = True
    
    def _ai_async_abort_button_clicked(self):
        self.ai_async_is_canceled = True
    
    def ai_async_stream(self, llm, messages, result_callback=None, progress_callback=None, streaming_callback=None, error_callback=None):       
        """Calls the LLM in a background thread and streams back the results 

        Args:
            llm (_type_): _description_
            messages (_type_): _description_
            result_callback (_type_, optional): _description_. Defaults to None.
            progress_callback (_type_, optional): _description_. Defaults to None.
            streaming_callback (_type_, optional): _description_. Defaults to None.
            error_callback (_type_, optional): _description_. Defaults to None.
        """
        # start async worker
        self.ai_async_is_finished = False
        self.ai_async_is_errored = False
        self.ai_async_progress_msg = ''
        self.ai_async_progress_count = -1
        worker = Worker(self._ai_async_stream, llm=llm, messages=messages)
        if result_callback is not None: 
            worker.signals.result.connect(result_callback)
        if progress_callback is not None:
            worker.signals.progress.connect(progress_callback)
        if streaming_callback is not None:
            worker.signals.streaming.connect(streaming_callback)
        if error_callback is not None:
            worker.signals.error.connect(error_callback)
        else:
            worker.signals.error.connect(self._ai_async_error)
        self.threadpool.start(worker)

    def _ai_async_stream(self, signals, llm, messages):
        self.ai_async_is_canceled = False
        self.ai_streaming_output = ''
        for chunk in llm.stream(messages):
            if self.ai_async_is_canceled:
                break # cancel the streaming
            else:
                self.ai_streaming_output += chunk.content
                if signals is not None:
                    if signals.streaming is not None:
                        signals.streaming.emit(str(chunk.content))
                    if signals.progress is not None:
                        self.ai_async_progress_count += len(chunk.content)
                        signals.progress.emit(str(self.ai_async_progress_count))
        res = self.ai_streaming_output
        self.ai_streaming_output = ''
        return res

    def ai_async_query(self, func, result_callback, *args, **kwargs):        
        """_summary_

        Args:
            parent_window (_type_): _description_
            func (_type_): _description_
            result_callback (_type_): _description_
        """
        self.ai_async_is_canceled = False
        
        # start async worker
        self.ai_async_is_finished = False
        self.ai_async_is_errored = False
        self.ai_async_progress_msg = ''
        self.ai_async_progress_count = -1
        worker = Worker(func, *args, **kwargs) # Any other args, kwargs are passed to the run function
        if result_callback is not None: 
            worker.signals.result.connect(result_callback)
        worker.signals.finished.connect(self._ai_async_finished)
        worker.signals.progress.connect(self._ai_async_progress)
        worker.signals.error.connect(self._ai_async_error)
        self.threadpool.start(worker)
                        
    def get_curr_language(self):
        """Determine the current language of the UI and/or the project. 
        Used to instruct the AI answering in the correct language. 
        """ 
        lang_long = {"de": "Deutsch", "en": "English", "es": "Español", "fr": "Français", "it": "Italiano", "pt": "Português"}
        lang = lang_long[self.app.settings['language']] 
        if lang is None:
            lang = 'English'
        return lang
    
    def generate_code_descriptions(self, code_name, code_memo='') -> list:
        """Prompts the AI to create a list of 10 short descriptions of the given code.
        This is used to get a better basis for the semantic search in the vectorstore. 

        Args:
            code_name (str): the name of the code
            code_memo (str): a memo, optional

        Returns:
            list: list of strings
        """

        #if self.is_busy():
        #    raise AiException('AI is busy (generate_code_descriptions)')
                
        code_descriptions_prompt = [
            SystemMessage(
                content = self.get_default_system_prompt()
            ),
            HumanMessage(
                content= (f'You are discussing the code named "{code_name}" with the following code memo: "{code_memo}". \n'
                    'Your task: Give back a list of 10 short descriptions of the meaning of this code. '
                    'Try to give a variety of diverse code-descriptions. Use simple language. '
                    f'Always answer in the following language: "{self.get_curr_language()}". Do not use numbers or bullet points. '
                    'Do not explain anything or repeat the code name, just give back the descriptive text. '
                    'Return the list as a valid JSON object in the following form: '
                    '{\n  "descriptions": [\n    "first description",\n    "second description",\n   ]\n}.')
            )
        ]

        json_result = {
            "descriptions": [
                "first description",
                "second description",
                ...
            ]
        }

        code_descriptions_prompt = [
            SystemMessage(
                content = self.get_default_system_prompt()
            ),
            HumanMessage(
                content= (f'We are searching for empirical data that fits a code named "{code_name}" '
                    f'with the following code memo: "{extract_ai_memo(code_memo)}". \n'
                    'Your task: Give back a list of 10 short descriptions of the meaning of this code. '
                    'Try to give a variety of diverse code-descriptions. Use simple language. '
                    f'Always answer in the following language: "{self.get_curr_language()}". Do not use numbers or bullet points. '
                    'Do not explain anything or repeat the code name, just give back the descriptive text. '
                    'Return the list as a valid JSON object in the following form:\n'
                    f'{json_result}')
            )
        ]

        logger.debug(_('AI generate_code_descriptions\n'))
        logger.debug(_('Prompt:\n') + str(code_descriptions_prompt))
        
        # callback to show percentage done    
        config = RunnableConfig()
        config['callbacks'] = [MyCustomSyncHandler(self)]
        self.ai_async_progress_max = round(1000 / 4) # estimated token count of the result (1000 chars)

        res = self.large_llm.invoke(code_descriptions_prompt, response_format={"type": "json_object"}, config=config)
        logger.debug(str(res.content))
        code_descriptions = json_repair.loads(str(res.content))['descriptions']

        return code_descriptions
        
        """
        # define the format for the output
        class CodeDescription(BaseModel):
            description: str = Field(..., description="A short description of the meaning of the code")
        class CodeDescriptions(BaseModel):
            "A list of code-descriptions"
            descriptions: List[CodeDescription]

        # create the prompt         
        if code_memo != '':
            memo_prompt = f' with the following code memo: "{code_memo[:max_memo_length]}".'
        else:
            memo_prompt = '.'

        code_descriptions_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    'system',
                    self.get_default_system_prompt(),
                ),
                (
                    'human',
                    ('You are discussing the code named "{code_name}"{memo_prompt}\n'
                    'Your task: Give back a list of 10 short descriptions of the meaning of this code using the given format. '
                    'Try to give a variety of diverse code-descriptions. Use the same language as the code name and simple, everyday terms.'),
                )
            ]
        )
        
        logger.debug(_('AI generate_code_descriptions prompt:\n') + code_descriptions_prompt.format(code_name=code_name, memo_prompt=memo_prompt))

        self.ai_async_progress_max = round(1000 / 4) # estimated token count of the result (1000 chars)
        config = RunnableConfig()
        config['callbacks'] = [MyCustomSyncHandler(self)]

        # query the llm
        runnable = create_structured_output_runnable(
            output_schema = CodeDescriptions, 
            llm = self.llm, 
            prompt = code_descriptions_prompt)

        code_descriptions: CodeDescriptions = runnable.invoke({
            'code_name': code_name,
            'memo_prompt': memo_prompt
        }, config=config)
        
        logger.debug(_('AI generate_code_descriptions result:\n') + code_descriptions.json())

        # return the result as a list
        res = []
        for desc in code_descriptions.descriptions:
            res.append(desc.description)
        return res
        """
    
    def retrieve_similar_data(self, result_callback, code_name, code_memo='', doc_ids=[]):
        self.ai_async_query(self._retrieve_similar_data, result_callback, code_name, code_memo, doc_ids)

    def _retrieve_similar_data(self, code_name, code_memo='', doc_ids=[], progress_callback=None, signals=None) -> list:
        # 1) Get a list of code descriptions from the llm
        if progress_callback != None:
            progress_callback.emit(_('Stage 1:\nSearching data related to "') + code_name + '"') 
        descriptions = self.generate_code_descriptions(code_name, code_memo)
        if self.ai_async_is_canceled:
            return
        
        # 2) Use the list of code descriptions to retrieve related data from the vectorstore
        search_kwargs = {'score_threshold': 0.5, 'k': 50}
        if len(doc_ids) > 0:
            # add document filter
            search_kwargs['filter'] = {'id': {'$in':doc_ids}}
        
        #retriever = self.sources_vectorstore.chroma_db.as_retriever(
        #    search_type="similarity_score_threshold",
        #    search_kwargs=search_kwargs
        #)

        chunks_meta_list = []
        for desc in descriptions:
            #chunks_meta_list.append(retriever.get_relevant_documents(desc))
            chunks_meta_list.append(self.sources_vectorstore.chroma_db.similarity_search_with_relevance_scores(desc, **search_kwargs))


        #for chunk_list in chunks_meta_list:
        #    print(chunk_list)
            
        # 3) Consolidate results
        # Flatten the lists of chunks in chunks_lists and collect all the chunks in a master list.
        # Duplicate chunks are collected only once. The list is sorted by the frequency 
        # of a chunk counted over all lists + the similarity score that chromadb returns.
        # This way, frequent and relevant chunks should be sorted to the top
        # (see: "Reciprocal Rank Fusion" (https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf))

        def chunk_unique_str(chunk):
            # helper
            chunk_str = str(chunk.metadata['id']) + ", "
            chunk_str += str(chunk.metadata['start_index']) + ", "
            return chunk_str
            
        # Flatten the lists and count the frequency of each chunk
        chunk_count_list = {} # contains the chunk count
        chunk_master_list = [] # contains all chunks from all lists but no doubles
        for lst in chunks_meta_list:
            for chunk in lst:            
                chunk_doc = chunk[0]
                chunk_score = chunk[1]
                chunk_str = chunk_unique_str(chunk_doc)
                chunk_in_count_list = chunk_count_list.get(chunk_str, None)
                if chunk_in_count_list: 
                    chunk_count_list[chunk_str] += 1 + chunk_score
                else:
                    chunk_count_list[chunk_str] = 1 + chunk_score
                    chunk_master_list.append(chunk_doc)
                    
        # add scores
        for chunk_doc in chunk_master_list:
            chunk_doc.metadata['score'] = chunk_count_list[chunk_unique_str(chunk_doc)]
        
        # Sort the common items by their score in descending order
        chunk_master_list.sort(key=lambda chunk: chunk.metadata['score'], reverse=True)
                                
        logger.debug('First 10 chunks of retrieved data:\n' + str(chunk_master_list[:10]))
        
        return chunk_master_list
    
    def search_analyze_chunk(self, parent_window, result_callback, chunk, code_name, code_memo, search_prompt: PromptItem):
        # Analyze a chunk of data with the AI
        # if self.ai_async_is_canceled:
        #    return
        self.ai_async_query(self._search_analyze_chunk, result_callback, chunk, code_name, code_memo, search_prompt)
        
    def _search_analyze_chunk(self, chunk, code_name, code_memo, search_prompt: PromptItem, progress_callback=None, signals=None):
        # the async function
                
        if progress_callback != None:
            progress_callback.emit(_("Stage 2:\nInspecting the data more closely..."))        

        # build up the prompt
        
        json_result = """
{
    "interpretation": your reasoning,
    "related": your conclusion, true or false
    "quote": the selected quote or an empty string,
}
"""
        prompt = [
            SystemMessage(
                content=self.get_default_system_prompt()
            ),
            HumanMessage(
                content= (f'You are discussing the code named "{code_name}" with the following code memo: "{extract_ai_memo(code_memo)}". \n'
                    'At the end of this message, you will find a chunk of empircal data. \n'
                    'Your task is to inspect this chunk of empirical data and decide wether it relates to the given code or not. '
                    f'In order to decide this, you must adher to the folowing instructions: "{search_prompt.text}". \n'
                    'The result of your analysis must consist out of two parts:\n'
                    '1. In the field "interpretation", present a short summary of your reasoning behind the decision wether the '
                    'data relates to the given code or not. Avoid repeating the codes name '
                    'or memo or phrases like "The empirical data relates to the code because...". Get directly to the point. '
                    f'In this particular field, always answer in the language "{self.get_curr_language()}".\n'
                    '2a. If the previous step came to the conclusion that the data relates to the code, '
                    'identify a quote from the chunk of empirical data that contains the part which is '
                    'relevant for the analysis of the given code. Include enough context so that the quote is comprehensable. '
                    'Give back this quote in the field "quote" exactly like in the original, '
                    'including errors. Do not leave anything out, do not translate the text or change it in any other way. '
                    'If you cannot identify a particular quote, return the whole chunk of empirical data in the field "quote".\n'
                    '2b. If step 1 came to the conclusion that the data is not relevant, '
                    'return an empty quote ("") in the field "quote".\n'
                    'Make sure to return nothing else but a valid JSON object in the following form: \n{\n  "interpretation": your explanation,\n  "quote": the selected quote or an empty string,\n}.'
                    f'\n\nThe chunk of empirical data for you to analyze: \n"{chunk.page_content}"')
                )
            ]  

        prompt = [
            SystemMessage(
                content=self.get_default_system_prompt()
            ),
            HumanMessage(
                content= (f'You are discussing the code named "{code_name}" with the following code memo: "{extract_ai_memo(code_memo)}". \n'
                    'At the end of this message, you will find a chunk of empirical data. \n'
                    'Your task is to inspect this chunk of empirical data and decide wether it relates to the given code or not. '
                    f'In order to decide this, you must adher to the following instructions: "{search_prompt.text}". \n'
                    'Summarize your reasoning briefly in the field "interpretation" of the result. '
                    f'In this particular field, always answer in the language "{self.get_curr_language()}".\n'
                    'If you came to the conclusion that the data relates to the code, '
                    'identify a quote from the chunk of empirical data that contains the part which is '
                    'relevant for the analysis of the given code. Include enough context so that the quote is comprehensable. '
                    'Give back this quote in the field "quote" exactly like in the original, '
                    'including errors. Do not leave anything out, do not translate the text or change it in any other way. '
                    'If you cannot identify a particular quote, return the whole chunk of empirical data in the field "quote".\n'
                    'If you came the conclusion that the data is not relevant, '
                    'return an empty quote ("") in the field "quote".\n'
                    'Make sure to return nothing else but a valid JSON object in the following form: \n{\n  "interpretation": your explanation,\n  "quote": the selected quote or an empty string,\n}.'
                    f'\n\nThe chunk of empirical data for you to analyze: \n"{chunk.page_content}"')
                )
            ]

        prompt = [
            SystemMessage(
                content=self.get_default_system_prompt()
            ),
            HumanMessage(
                content= (f'You are discussing the code named "{code_name}" with the following code memo: "{extract_ai_memo(code_memo)}". \n'
                    'At the end of this message, you will find a chunk of empirical data. \n'
                    'Your task is to inspect this chunk of empirical data and decide wether it (or parts of it) relates to the given code or not. '
                    f'In order to decide this, you must adher to the following instructions: "{search_prompt.text}". \n'
                    'The result consists of three parts:\n'
                    '1) Briefly summarize your reasoning regarding the question wether this data relates to the code in the field "interpretation" of the result. '
                    f'In this particular field, always answer in the language "{self.get_curr_language()}".\n'
                    '2) Analyze your reasoning from the previous step. If you come to the conclusion that the chunk of data '
                    'is not related to the code, give back \'false\' in the field "related", otherwise \'true\'.\n'
                    '3) - If step 2 resulted in \'true\', identify a quote from the chunk of empirical data that contains the part which is '
                    'relevant for the analysis of the given code. Include enough context so that the quote is comprehensable. '
                    'Give back this quote in the field "quote" exactly like in the original, '
                    'including errors. Do not leave anything out, do not translate the text or change it in any other way. '
                    'If you cannot identify a particular quote, return the whole chunk of empirical data in the field "quote".\n'
                    '- If step 2 resulted in \'false\', return an empty quote ("") in the field "quote".\n'
                    f'Make sure to return nothing else but a valid JSON object in the following form: \n{json_result}.'
                    f'\n\nThe chunk of empirical data for you to analyze: \n"{chunk.page_content}"')
                )
            ]

        prompt = [
            SystemMessage(
                content=self.get_default_system_prompt()
            ),
            HumanMessage(
                content= (f'You are discussing the code named "{code_name}" with the following code memo: "{extract_ai_memo(code_memo)}". \n'
                    'At the end of this message, you will find a chunk of empirical data. \n'
                    'Your task is to inspect this chunk of empirical data and decide wether it relates to the given code or not. '
                    f'In order to decide this, you must adher to the following instructions: "{search_prompt.text}". \n'
                    'Summarize your reasoning briefly in the field "interpretation" of the result. '
                    f'In this particular field, always answer in the language "{self.get_curr_language()}".\n'
                    'If you came to the conclusion that the chunk of data '
                    'is not related to the code, give back \'false\' in the field "related", otherwise \'true\'.\n'
                    'If the previous step resulted in \'true\', identify a quote from the chunk of empirical data that contains the part which is '
                    'relevant for the analysis of the given code. Include enough context so that the quote is comprehensable. '
                    'Give back this quote in the field "quote" exactly like in the original, '
                    'including errors. Do not leave anything out, do not translate the text or change it in any other way. '
                    'If you cannot identify a particular quote, return the whole chunk of empirical data in the field "quote".\n'
                    'If the previous step resulted in \'false\', return an empty quote ("") in the field "quote".\n'
                    f'Make sure to return nothing else but a valid JSON object in the following form: \n{json_result}.'
                    f'\n\nThe chunk of empirical data for you to analyze: \n"{chunk.page_content}"')
                )
            ]

        prompt = [
            SystemMessage(
                content=self.get_default_system_prompt()
            ),
            HumanMessage(
                content= (f'You are discussing the code named "{code_name}" with the following code memo: "{extract_ai_memo(code_memo)}". \n'
                    'At the end of this message, you will find a chunk of empirical data. \n'
                    'Your task is to use the following instructions to analyze the chunk of empirical data and decide wether it relates to the given code or not. '
                    f'Instructions: "{search_prompt.text}". \n'
                    'Summarize your reasoning briefly in the field "interpretation" of the result. '
                    f'In this particular field, always answer in the language "{self.get_curr_language()}".\n'
                    'If you came to the conclusion that the chunk of data '
                    'is not related to the code, give back \'false\' in the field "related", otherwise \'true\'.\n'
                    'If the previous step resulted in \'true\', identify a quote from the chunk of empirical data that contains the part which is '
                    'relevant for the analysis of the given code. Include enough context so that the quote is comprehensable. '
                    'Give back this quote in the field "quote" exactly like in the original, '
                    'including errors. Do not leave anything out, do not translate the text or change it in any other way. '
                    'If you cannot identify a particular quote, return the whole chunk of empirical data in the field "quote".\n'
                    'If the previous step resulted in \'false\', return an empty quote ("") in the field "quote".\n'
                    f'Make sure to return nothing else but a valid JSON object in the following form: \n{json_result}.'
                    f'\n\nThe chunk of empirical data for you to analyze: \n"{chunk.page_content}"')
                )
            ]

        # callback to show percentage done    
        config = RunnableConfig()
        config['callbacks'] = [MyCustomSyncHandler(self)]
        self.ai_async_progress_max = 130 # estimated average token count of the result
        
        # send the query to the llm 
        res = self.large_llm.invoke(f'{prompt}', response_format={"type": "json_object"}, config=config)
        res_json = json_repair.loads(str(res.content))
        
        # analyse and format the answer
        # if res_json['quote'] != '': # found something
        if 'related' in res_json and res_json['related'] == True and \
           'quote' in res_json and res_json['quote'] != '': # found something
            # Adjust quote_start
            i = 0
            doc = {}
            doc['metadata'] = chunk.metadata
                       
            # search quote with not more than 30% mismatch (Levenshtein Distance). This is done because the AI sometimes alters the text a little bit.
            quote_found = fuzzysearch.find_near_matches(res_json['quote'], chunk.page_content, 
                             max_l_dist=round(len(res_json['quote']) * 0.3)) # result: list [Match(start=x, end=x, dist=x, matched='txt')]
            if len(quote_found) > 0:
                doc['quote_start'] = quote_found[0].start + doc['metadata']['start_index']
                doc['quote'] = quote_found[0].matched
            else: # quote not found, make the whole chunk the quote
                doc['quote_start'] = doc['metadata']['start_index']
                doc['quote'] = chunk.page_content
        
            doc['interpretation'] = res_json['interpretation']
        else: # No quote means the AI discarded this chunk as not relevant
            doc = None
        return doc
    
    """ old:
    def analyze_similarity(self, parent_window, result_callback, chunk_list, code_name, code_memo=''):
        # Analyze the chunks of data with GPT-4
        self.ai_async_query(parent_window, self._analyze_similarity, True, result_callback, chunk_list, code_name, code_memo)
    
    def _analyze_similarity(self, chunk_list, code_name, code_memo='', progress_callback=None) -> list:        
        # the async function
        if progress_callback != None:
            progress_callback.emit(_("We've found potentially related data.\nGive me some time to inspect it more closely..."))        
        
        # create json:
        chunks_json = '{\n  "chunks_of_empirical_data":[\n'
        for chunk in chunk_list:
            chunks_json += f'    {json.dumps(chunk.page_content)},\n'
        chunks_json = chunks_json[:-2] + '\n' # delete the last comma
        chunks_json += '  ]\n}'
        
        if code_memo != '':
            memo_str = f'The code has the following memo attached: "{code_memo[:max_memo_length]}".\n'
        else:
            memo_str = ''
        
        analyze_chunks_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    'system',
                    self.get_default_system_prompt() + '\nYou are an expert in analyzing the empirical data that was collected during the research.',
                ),
                (
                    'human',
                    str('We are analyzing the code named "{code_name}".\n'
                     '{memo_str}'
                     'Please answer in the language of the code name.\n'
                     'Here is a list of larger chunks of empirical data, formatted as a JSON object: \n'
                     '{chunks_json}\n'
                     'Your tasks: Go through this list one by one and fulfill the following tasks:\n'
                     '1. Estimate the relevance of the chunk of empirical data for the analysis of the given code and give it a score '
                     'between 0 and 10. A chunk of empirical data will be relevant if it addresses a similar topic, attitude, feeling '
                     'or experience or conveys a similar meaning as the given code. Return the score in the field "relevance" of the output. \n'
                     '2. In the field "interpretation" of the output, give a short a short explanation how the chunk of empirical data '
                     'relates to the given code code or not.\n'
                     '3. Select a quote from the chunk of empirical data that contains the part which is most relevant for the analysis '
                     'of the given code. Give back the quote in the field "quote" of the output, following the the original exactly, including errors. '
                     'Do not change the text in any way. \n'
                     'Do these 3 steps for every chunk of empirical data in the list, then close the JSON object for the output. Make sure to return '
                     'a valid JSON object that follows the given schema exactly.',
                    )
                )
            ]
        )
        
        self.ai_async_progress_max = round((len(chunks_json) / 4) * 0.75) # estimated token count of the result
      
        logger.debug(_("AI analyze_similarity prompt:\n") + analyze_chunks_prompt.format(code_name=code_name, memo_str=memo_str, chunks_json=chunks_json))

        runnable = create_structured_output_runnable(
            output_schema=LlmAnalyzedDataList, 
            llm=self.llm, 
            prompt=analyze_chunks_prompt)
        
        config = RunnableConfig()
        config['callbacks'] = [MyCustomSyncHandler(self)]

        selected_quotes: AnalyzedDataList = runnable.invoke({
            'code_name': code_name, 
            'memo_str': memo_str, 
            'chunks_json': chunks_json
        }, config=config)
        
        logger.debug(_("AI analyze_similarity result:\n") + selected_quotes.json())
                
        # Adjust quote_start
        i = 0
        for doc in selected_quotes.data:
            doc.metadata = chunk_list[i].metadata
                       
            # search with not more than 30% mismatch (Levenshtein Distance)
            if doc.quote != '':
                quote_found = fuzzysearch.find_near_matches(doc.quote, chunk_list[i].page_content, 
                                                        max_l_dist=round(len(doc.quote) * 0.3)) # result: list [Match(start=x, end=x, dist=x, matched='txt')]
            else: 
                quote_found = []
            if len(quote_found) > 0:
                doc.quote_start = quote_found[0].start + doc.metadata['start_index']
                doc.quote = quote_found[0].matched
            else:
                doc.quote_start = doc.metadata['start_index']
                doc.quote = chunk_list[i].page_content
            i += 1
            
        # filter out chunks with a relevance score <= 3:
        filtered_docs = []
        for doc in selected_quotes.data:
            if doc.relevance > 3:
                filtered_docs.append(doc)
        selected_quotes.data = filtered_docs        
        
        # Sort the selected quotes by their relevance in descending order
        selected_quotes.data.sort(key=lambda chunk: chunk.relevance, reverse=True)
         
        return selected_quotes 
        
        """       
   

    
    
