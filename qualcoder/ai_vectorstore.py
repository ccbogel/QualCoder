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

from langchain.embeddings.sentence_transformer import SentenceTransformerEmbeddings
from langchain.text_splitter import CharacterTextSplitter, RecursiveCharacterTextSplitter
from langchain.vectorstores import Chroma
from langchain.docstore.document import Document
from typing import (Any, Iterable, Optional, List)
import os
import logging
import traceback
from PyQt6 import QtWidgets
from PyQt6.QtCore import QThreadPool
import qualcoder.ai_async_worker

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

class E5SentenceTransformerEmbeddings(SentenceTransformerEmbeddings):
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Compute doc embeddings using a HuggingFace transformer model.
        This is a special version for E5 embedding models which need 'passage: ' 
        in front of every chunk of embedded text and 'query: ' in front of 
        every query.

        Args:
            texts: The list of texts to embed.

        Returns:
            List of embeddings, one for each text.
        """
        for text in texts:
            text = 'passage: ' + text
        return super().embed_documents(texts=texts)
    
    def embed_query(self, text: str) -> List[float]:
        """Compute query embeddings using a HuggingFace transformer model.
        This is a special version for E5 embedding models which need 'passage: ' 
        in front of every chunk of embedded text and 'query: ' in front of 
        every query. 

        Args:
            text: The text to embed.

        Returns:
            Embeddings for the text.
        """
        return super().embed_documents([f'query: {text}'])[0]
   
    
class AiVectorstore():
    """ This is the memory of AI research mate. 
    It manages a chromadb vectorstore with embeddings for all text based 
    source data in the project. This allows for semantic search and retrieval 
    of chunks of data which can then be further processed with a large 
    language model like GPT-4. 
    Embeddings are created locally using a multilingual model based on E5 
    from Microsoft Research."""

    app = None
    parent_text_edit = None
    ready = False # If the chroma_db is busy ingesting documents, ready will be "False" since we cannot make any queries yet.   
    import_workers_count = 0
    # Setup the database 
    model_name = "intfloat/multilingual-e5-small" # or intfloat/multilingual-e5-base
    embedding_function = E5SentenceTransformerEmbeddings(model_name=model_name) 
    chroma_db = None
    _is_closing = False
    collection_name = ''
    
    def __init__(self, app, parent_text_edit, collection_name):
        self.app = app
        self.parent_text_edit = parent_text_edit
        self.collection_name = collection_name
        self.threadpool = QThreadPool()
        self.threadpool.setMaxThreadCount(1)
    
    def _open_db(self, progress_callback=None):
        if self._is_closing:
            return # abort when closing db
        if self.app.project_path != '' and os.path.exists(self.app.project_path):
            db_path = self.app.project_path + '/vectorstore'
            self.chroma_db = Chroma(embedding_function=self.embedding_function, 
                                    persist_directory=db_path,
                                    collection_name=self.collection_name)
        else:
            self.chroma_db = None
            raise FileNotFoundError(f'AI Vectorstore: project path "{self.app.project_path}" not found.')
    
    def _open_and_empty_db(self, progress_callback=None):
        logger.debug('AI research mate: rebuilding vectorstore')
        self._open_db()
        # delete all the contents from the vectorstore
        ids = self.chroma_db.get(include=[])['ids']
        self.chroma_db.delete(ids)
        
    def init_vectorstore(self, rebuild=False):
        """Initializes the vectorstore and checks if all text sources are stored.
        If rebuild is True, the contents of the vectorstore will be deleted
        and rebuild from the ground up.  

        Args:
            rebuild (bool, optional): Rebuild the vectorstore from the ground up. Defaults to False.
        """
        self._is_closing = False
        self.ready = False

        # start background thread opening/rebuilding the chroma db. This avoids blocking the ui.
        if rebuild:
            worker = qualcoder.ai_async_worker.Worker(self._open_and_empty_db)
        else:    
            worker = qualcoder.ai_async_worker.Worker(self._open_db)
        # once finished opening, check if all source documents are in the vectorstore  
        worker.signals.finished.connect(self.update_vectorstore)
        worker.signals.error.connect(exception_handler)
        self.threadpool.start(worker)
        
    def progress_import(self, msg):
        self.parent_text_edit.append(msg)
        
    def finished_import(self):
        msg = _('AI research mate: Finished updating memory.')
        self.import_workers_count -= 1
        if self.import_workers_count <= 0:
            self.import_workers_count = 0
            self.ready = True
            self.parent_text_edit.append(msg)
            logger.debug(msg)
        # else:
            # logger.debug(f'Updating vectorstore, {self.import_workers_count} documents to go.')
    
    def _import_document(self, id, name, text, update=False, progress_callback=None):
        if self._is_closing:
            return # abort when closing db
                       
        # Check if the document is already in the store:
        embeddings_list = self.chroma_db.get(where={"id" : id}, include=['metadatas'])
        if len(embeddings_list['ids']) > 0: # found it
            if update or embeddings_list['metadatas'][0]['name'] != name:
                # delete old embeddings
                self.chroma_db.delete(embeddings_list['ids']) 
            else:
                # skip the doc
                return 
        
        # add to chroma_db
        if self._is_closing:
            return # abort when closing db
        
        # split fulltext in smaller chunks 
        if text != '': # can only add embeddings if text is not empty
            if progress_callback != None:
                progress_callback.emit(_('AI research mate: Memorizing document ') + f'"{name}"')

            metadata = {'id': id, 'name': name}
            document = Document(page_content=text, metadata=metadata)
            text_splitter = RecursiveCharacterTextSplitter(separators=[".", "!", "?", "\n\n", "\n", " ", ""], 
                                                        keep_separator=False, chunk_size=500, chunk_overlap=100, 
                                                        add_start_index=True)
            chunks = text_splitter.split_documents([document])
            
            # create embeddings for these chunks and store them in the chroma_db (with metadata)
            chunk_texts = [chunk.page_content for chunk in chunks]
            chunk_metadatas = [chunk.metadata for chunk in chunks]
            self.chroma_db.add_texts(chunk_texts, chunk_metadatas)    

    def import_document(self, id, name, text, update=False):
        """Imports a document into the chroma_db. 
        If a document with the same id is already in 
        the chroma_db, it can be updated (update=True) 
        or skipped (update=False).
        This is an async process running in a background
        thread. AiVectorstore.ready will be False
        until the import is finished.

        Args:
            id (integer): the database id
            update (bool, optional): defaults to False.
        """
        worker = qualcoder.ai_async_worker.Worker(self._import_document, id, name, text, update) # Any other args, kwargs are passed to the run function
        # worker.signals.result.connect()
        worker.signals.finished.connect(self.finished_import)
        worker.signals.progress.connect(self.progress_import)
        worker.signals.error.connect(exception_handler)
        self.import_workers_count += 1
        self.threadpool.start(worker)

    def update_vectorstore(self):
        """Collects all text sources from the database and adds them to the chroma_db if 
        not already in there.  
        """   
        docs = self.app.get_file_texts()
        for doc in docs:
            self.import_document(doc['id'], doc['name'], doc['fulltext'], False)
            
    def delete_document(self, id):
        """Deletes all the embeddings from related to this doc 
        from the vectorstore"""
        embeddings_list = self.chroma_db.get(where={"id" : id}, include=[])
        if len(embeddings_list['ids']) > 0: # found it
            self.chroma_db.delete(embeddings_list['ids']) 
               
    def close(self):
        """Cancels the update process if running"""
        self._is_closing = True
        # cancel all waiting threads:
        self.threadpool.clear()
        self.threadpool.waitForDone(5000)
        self.chroma_db = None
        self.ready = False
            
    def is_ready(self) -> bool:
        """If the vectorstore is initiated and done importing data, 
        it is ready for queries."""
        return self.chroma_db != None and self._is_closing == False and self.threadpool.activeThreadCount == 0
        
    
        
