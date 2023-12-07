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
from langchain.chat_models import ChatOpenAI
from langchain.globals import set_llm_cache
from langchain.cache import InMemoryCache
from langchain.pydantic_v1 import BaseModel, Field
from langchain.chains.openai_functions import (
    create_openai_fn_chain,
    create_structured_output_chain,
    create_openai_fn_runnable,
    create_structured_output_runnable,
)
from langchain.prompts import ChatPromptTemplate
from langchain.callbacks.base import BaseCallbackHandler
from langchain.schema.runnable import RunnableConfig
from .ai_async_worker import Worker, AiException
from .ai_vectorstore import AiVectorstore
from .GUI.base64_helper import *
import fuzzysearch

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text_ = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text_)
    logger.error(_("Uncaught exception: ") + text_)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 12pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(text_)
    mb.exec()
    
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
    
class AiLLM():
    """ This manages the communication between qualcoder, the vectorstore 
    and the LLM (large language model, GPT-4 in this case)."""

    app = None
    parent_text_edit = None
    threadpool: QtCore.QThreadPool = None
    ai_async_is_canceled = False
    ai_async_is_finished = False
    ai_async_progress_msgbox = None
    ai_async_progress_msg = ''
    ai_async_progress_count = -1
    ai_async_progress_max = -1
    busy = False   
    gpt4 = None
    default_system_prompt = (
        'You are a member of a team of qualitative social researchers.'
    )

    def __init__(self, app, parent_text_edit):
        self.app = app
        self.parent_text_edit = parent_text_edit
        self.threadpool = QtCore.QThreadPool()
        self.threadpool.setMaxThreadCount(1)
    
    def init_llm(self):
        set_llm_cache(InMemoryCache())
        self.gpt4 = ChatOpenAI(model='gpt-4-1106-preview', 
                               openai_api_key=self.app.settings['open_ai_api_key'], 
                               cache=True,
                               temperature=0.0,
                               streaming=True
                               )
        
    def is_ready(self):
        return (self.app.sources_vectorstore is not None) and \
                    (self.app.sources_vectorstore.is_ready()) and \
                    (self.gpt4 is not None) and \
                    (self.threadpool.activeThreadCount() == 0)
    
    def _ai_async_progress(self, msg):
        # print(msg)
        self.ai_async_progress_msg = self.ai_async_progress_msg + '\n' + msg

    def _ai_async_finished(self):
        self.ai_async_progress_msgbox.close()
        self.ai_async_is_finished = True
    
    def ai_async_query(self, parent_window, func, result_callback, *args, **kwargs):
        # show MessageBox while waiting
        self.ai_async_progress_msgbox = QtWidgets.QMessageBox(parent_window)
        self.ai_async_progress_msgbox.setStandardButtons((QtWidgets.QMessageBox.StandardButton.Abort))
        self.ai_async_progress_msgbox.setWindowTitle('AI query running')
        # create Label
        pm = QtGui.QPixmap()
        pm.loadFromData(QtCore.QByteArray.fromBase64(ai_search), "gif")
        self.ai_async_progress_msgbox.setIconPixmap(pm.scaledToWidth(128))
        icon_label = self.ai_async_progress_msgbox.findChild(QtWidgets.QLabel, "qt_msgboxex_icon_label")
        # load gif
        bArray = QtCore.QByteArray.fromBase64(ai_search)
        bBuffer = QtCore.QBuffer(bArray)
        bBuffer.open(QtCore.QIODeviceBase.OpenModeFlag.ReadWrite)
        movie = QtGui.QMovie()
        movie.setDevice(bBuffer)
        movie.setFormat(b'GIF')
        size = QtCore.QSize(128, 128)
        movie.setScaledSize(size)
        # avoid garbage collector
        setattr(self.ai_async_progress_msgbox, 'icon_label_bArray', bArray)
        setattr(self.ai_async_progress_msgbox, 'icon_label_bBuffer', bBuffer)
        setattr(self.ai_async_progress_msgbox, 'icon_label', movie)
        # start animation
        icon_label.setMovie(movie)
        movie.start()
        self.ai_async_progress_msgbox.setModal(True)
        self.ai_async_progress_msgbox.show()
        self.ai_async_is_canceled = False
        
        # start async worker
        self.ai_async_is_finished = False
        self.ai_async_progress_msg = ''
        self.ai_async_progress_count = -1
        worker = Worker(func, *args, **kwargs) # Any other args, kwargs are passed to the run function
        worker.signals.result.connect(result_callback)
        worker.signals.finished.connect(self._ai_async_finished)
        worker.signals.progress.connect(self._ai_async_progress)
        worker.signals.error.connect(exception_handler)
        self.threadpool.start(worker)
        
        while not self.ai_async_is_finished:
            if (self.ai_async_progress_count > -1) and (self.ai_async_progress_max > -1):
                progress_percent = round((self.ai_async_progress_count / self.ai_async_progress_max) * 100)
                self.ai_async_progress_msgbox.setText(f'{self.ai_async_progress_msg} (~{progress_percent}%)')
            else:
                self.ai_async_progress_msgbox.setText(self.ai_async_progress_msg)
            QtWidgets.QApplication.processEvents() # update the progress dialog
            time.sleep(0.01)
    
    def generate_code_descriptions(self, code_name, code_memo='') -> list:
        """Prompts GPT-4 to create a list of 10 short descriptions of the given code.
        This is used to get a better basis for the semantic search in the vectorstore. 

        Args:
            code_name (str): the name of the code
            code_memo (str): a memo, optional

        Returns:
            list: list of strings
        """

        if self.busy:
            raise AiException('AI is busy (generate_code_descriptions)')
        
        # define the format for the output
        class CodeDescription(BaseModel):
            description: str = Field(..., description="A short description of the meaning of the code")
        class CodeDescriptions(BaseModel):
            """A list of code-descriptions"""
            descriptions: List[CodeDescription]

        # create the prompt         
        if code_memo != '':
            memo_prompt = f' with the following code memo: "{code_memo[:300]}".'
        else:
            memo_prompt = '.'

        code_descriptions_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    'system',
                    self.default_system_prompt,
                ),
                (
                    'human',
                    ('You are discussing the code named "{code_name}"{memo_prompt}\n'
                    'Your task: Give back a list of 10 short descriptions of the meaning of this code using the given format. '
                    'Try to give a variety of diverse code-descriptions. Use simple language.'),
                )
            ]
        )

        # query the llm
        runnable = create_structured_output_runnable(
            output_schema = CodeDescriptions, 
            llm = self.gpt4, 
            prompt = code_descriptions_prompt)

        code_descriptions = runnable.invoke({
            'code_name': code_name,
            'memo_prompt': memo_prompt
        })

        # return the result as a list
        res = []
        for desc in code_descriptions.descriptions:
            self.parent_text_edit.append(desc.description)
            res.append(desc.description)
        return res
    
    def retrieve_similar_data(self, parent_window, result_callback, code_name, code_memo='', doc_ids=[]):
        self.ai_async_query(parent_window, self._retrieve_similar_data, result_callback, code_name, code_memo, doc_ids)

    def _retrieve_similar_data(self, code_name, code_memo='', doc_ids=[], progress_callback=None) -> list:
        # 1) Get a list of code descriptions from the llm
        if progress_callback != None:
            progress_callback.emit(_('Searching data related to "') + code_name + '"') 
        descriptions = self.generate_code_descriptions(code_name, code_memo)
        if self.ai_async_is_canceled:
            return
        
        # 2) Use the list of code descriptions to retrieve related data from the vectorstore
        search_kwargs = {'score_threshold': 0.5, 'k': 50}
        if len(doc_ids) > 0:
            # add document filter
            search_kwargs['filter'] = {'id': {'$in':doc_ids}}
        
        retriever = self.app.sources_vectorstore.chroma_db.as_retriever(
            search_type="similarity_score_threshold",
            search_kwargs=search_kwargs
        )

        chunks_meta_list = []
        for desc in descriptions:
            chunks_meta_list.append(retriever.get_relevant_documents(desc))

        #for chunk_list in chunks_meta_list:
        #    print(chunk_list)
            
        # 3) Consolidate results
        # Flatten the lists of chunks in chunks_lists and collect all the chunks in a master list.
        # Duplicate chunks are collected only once. The list is sorted by the frequency 
        # of a chunk counted over all lists. 
        
        # TODO: try to improve ranking with "Reciprocal Rank Fusion" (https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)
        # as implemented here: https://python.langchain.com/docs/modules/data_connection/retrievers/ensemble 

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
                chunk_str = chunk_unique_str(chunk)
                chunk_in_count_list = chunk_count_list.get(chunk_str, None)
                if chunk_in_count_list: 
                    chunk_count_list[chunk_str] += 1
                else:
                    chunk_count_list[chunk_str] = 1
                    chunk_master_list.append(chunk)
                        
        # Sort the common items by their frequency in descending order
        chunk_master_list.sort(key=lambda chunk: chunk_count_list[chunk_unique_str(chunk)], reverse=True)
        
        return chunk_master_list
    
    def analyze_similarity(self, parent_window, result_callback, chunk_list, code_name, code_memo=''):
        # Analyze the chunks of data with GPT-4
        self.ai_async_query(parent_window, self._analyze_similarity, result_callback, chunk_list, code_name, code_memo)
    
    def _analyze_similarity(self, chunk_list, code_name, code_memo='', progress_callback=None) -> list:        
        # the async function
        if progress_callback != None:
            progress_callback.emit(_("We've found related data.\nGive me some time to inspect it more closely..."))        
        
        # create json:
        chunks_json = '{\n  "chunks_of_empirical_data":[\n'
        for chunk in chunk_list:
            chunks_json += f'    {chunk.json()},\n'
        chunks_json = chunks_json[:-2] + '\n' # delete the last comma
        chunks_json += '  ]\n}'
        
        if code_memo != '':
            memo_str = f'The code has the following memo attached: "{code_memo[:300]}".\n'
        else:
            memo_str = ''
        
        analyze_chunks_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    'system',
                    self.default_system_prompt + '\nYou are an expert in analyzing the empirical data that was collected during the research.',
                ),
                (
                    'human',
                    str('We are analyzing the code named "{code_name}".\n'
                     '{memo_str}'
                     'Here is a list of larger chunks of empirical data, formatted as a JSON object. The field "page_content" contains the actual data: \n'
                     '{chunks_json}\n'
                     'Your tasks: Go through this list one by one and fulfill the following tasks:\n'
                     '1. Estimate the relevance of the chunk of empirical data in "page_content" for the analysis of the given code and give it a score '
                     'between 0 and 10. A chunk of empirical data will be relevant if it addresses a similar topic, attitude, feeling '
                     'or experience or conveys a similar meaning as the given code. Return the score in the field "relevance" of the output. \n'
                     '2. In the field "interpretation" of the output, give a short a short explanation how the empirical data in "page_content" '
                     'relates to the given code code or not \n'
                     '3. Select a short quote from the empirical data in "page_content" that contains the part which is most relevant for the analysis '
                     'of the given code. Give back the quote in the field "quote" of the output, following the the original exactly, including errors. '
                     'Do not change the text in any way. \n'
                     'Do these 3 steps for every chunk of empirical data in the list, then close the JSON object for the output. Make sure to return '
                     'a valid JSON object that follows the given schema exactly.',
                    )
                )
            ]
        )
        
        self.ai_async_progress_max = round(len(chunks_json) / 4)
      
        # my_analyze_chunk_prompt = analyze_chunk_prompt.format(code_name=code_name, memo_str=memo_str, chunks_json=chunks_json)

        runnable = create_structured_output_runnable(
            output_schema=LlmAnalyzedDataList, 
            llm=self.gpt4, 
            prompt=analyze_chunks_prompt)
        
        config = RunnableConfig()
        config['callbacks'] = [MyCustomSyncHandler(self)]

        selected_quotes: AnalyzedDataList = runnable.invoke({
            'code_name': code_name, 
            'memo_str': memo_str, 
            'chunks_json': chunks_json
        }, config=config)
                
        # Adjust quote_start
        i = 0
        for doc in selected_quotes.data:
            doc.metadata = chunk_list[i].metadata
            
            # doc.quote_start = doc.metadata['start_index'] + doc.quote_start 
            # quote_found = str(chunk_list[i].page_content).find(doc.quote)
            
            # search with not more than 20% mismatch (Levenshtein Distance)
            if doc.quote != '':
                quote_found = fuzzysearch.find_near_matches(doc.quote, chunk_list[i].page_content, 
                                                        max_l_dist=round(len(doc.quote) * 0.2)) # result: list [Match(start=x, end=x, dist=x, matched='txt')]
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
   

    
    
