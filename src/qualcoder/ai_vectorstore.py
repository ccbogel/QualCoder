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

Author: Kai Droege (kaixxx)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
"""

import os
os.environ['FAISS_NO_AVX2'] = '1'  # This is suggested by Langchain, but will in fact NOT WORK
os.environ['FAISS_OPT_LEVEL'] = ''  # This will atually create a 'generic' index. It is a poorly documented feature introduced here: https://github.com/facebookresearch/faiss/commit/eefa39105eda498ab5fcd82ea0e11b18fd3fc0d7
# Must be set before importing faiss. This tells faiss not to use AVX2, which makes the resulting
# index also compatible with older machines and non-intel platforms.    

from huggingface_hub import hf_hub_url
import sentence_transformers  # This is used in a subthread. But we must keep a reference here so that it is not garbage collected.
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_text_splitters.character import RecursiveCharacterTextSplitter
import faiss
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_community.vectorstores import FAISS
from langchain_core.documents.base import Document
import logging
import os
from PyQt6 import QtCore, QtWidgets
import requests
import time
import traceback
from typing import List
from uuid import uuid4
import inspect

from qualcoder.ai_async_worker import Worker
from qualcoder.ai_async_worker import AIException
from qualcoder.error_dlg import show_error_dlg
from qualcoder.helpers import Message

# Turn off telemetry
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"  # for huggingface hub

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def ai_exception_handler(exception_type, value, tb_obj):
    """ Show error message 
    """
    msg = exception_type.__name__ + ': ' + str(value)
    tb = '\n'.join(traceback.format_tb(tb_obj))
    logger.error(_("Uncaught exception: ") + msg + '\n' + tb)
    show_error_dlg(msg, tb)


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
        
        emb_texts = []
        
        for text in texts:
            emb_texts.append('passage: ' + text)
  
        return super().embed_documents(texts=emb_texts)
    
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
    """ This is the memory of the AI. 
    It manages a FAISS vectorstore with embeddings for all text based 
    source data in the project. This allows for semantic search and retrieval 
    of chunks of data which can then be further processed with a large 
    language model like GPT-4. 
    Embeddings are created locally using a multilingual model based on E5 
    from Microsoft Research."""

    app = None
    parent_text_edit = None
    ready = False  # If FAISS is busy indexing documents, ready will be "False" since we cannot make any queries yet.
    import_workers_count = 0
    # Setup the database 
    model_name = "intfloat/multilingual-e5-large"
    cache_folder = os.path.join(os.path.expanduser('~'), '.cache', 'torch', 'sentence_transformers')
    model_folder = os.path.join(cache_folder, model_name.replace("/", "_"))
    model_files = [
        '1_Pooling/config.json',
        '.gitattributes',
        'config.json',
        'modules.json',
        'pytorch_model.bin',
        'README.md',
        'sentence_bert_config.json',
        'sentencepiece.bpe.model',
        'special_tokens_map.json',
        'tokenizer.json',
        'tokenizer_config.json'
    ]
    download_model_running = False
    download_model_cancel = False
    download_model_msg = ''
    faiss_db = None
    faiss_db_path = None
    _is_closing = False
    collection_name = ''
    reading_doc = ''
    
    def __init__(self, app, parent_text_edit, collection_name):
        self.app = app
        self.parent_text_edit = parent_text_edit
        self.collection_name = collection_name
        self.threadpool = QtCore.QThreadPool()
        self.threadpool.setMaxThreadCount(1)
        
    def prepare_embedding_model(self, parent_window=None) -> bool:
        """Downloads the embeddings model if needed.    
        """
        if not self.embedding_model_is_cached():
            model_download_msg = _('\
Since you are using the AI integration for the first time, \
QualCoder needs to download and install some \
additional components. \n\
\n\
This will download about 2.5 GB of data. Do you \n\
want to continue?\
')
            mb = QtWidgets.QMessageBox(parent=parent_window)
            mb.setWindowTitle(_('Download AI components'))
            mb.setText(model_download_msg)
            mb.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok |
                                QtWidgets.QMessageBox.StandardButton.Abort)
            mb.setStyleSheet('* {font-size: ' + str(self.app.settings['fontsize']) + 'pt}')            
            if mb.exec() == QtWidgets.QMessageBox.StandardButton.Ok: 
                pd = QtWidgets.QProgressDialog(
                    labelText='                              ', 
                    minimum=0, maximum=100, 
                    parent=parent_window)
                pd.setStyleSheet('* {font-size: ' + str(self.app.settings['fontsize']) + 'pt}')
                pd.setWindowTitle(_('Download AI components'))
                pd.setAutoClose(False)
                pd.setModal(True)
                pd.show()
                self.download_embedding_model()
                while self.download_model_running:
                    if pd.wasCanceled():
                        self.download_model_cancel = True
                        self.app.settings['ai_enable'] = 'False'
                        return False
                    else:
                        # update progress bar
                        msg = self.download_model_msg
                        msgs = msg.split(':')
                        if len(msgs) > 1:
                            pd.setValue(int(''.join(filter(str.isdigit, msgs[1]))))
                            msg = msgs[0]
                        else:
                            pd.setValue(0)                            
                        pd.setLabelText(_('Downloading ') + msg)
                        QtWidgets.QApplication.processEvents()  # update the progress dialog
                        time.sleep(0.01)
                pd.close()
            else:
                self.app.settings['ai_enable'] = 'False'
                return False
        return True
        
    def embedding_model_is_cached(self) -> bool:
        """Checks if the embeddings model from huggingface is already downloaded 
        and in the local cache."""
        for model_file in self.model_files:
            if not os.path.exists(os.path.join(self.model_folder, model_file)):
                return False 
        return True
    
    def _download_embedding_model(self, signals=None):
        """Background thread to download the embedding model to the local cache if necessary.

        Args:
            progress_callback (function(msg), optional): called regularly with an update
                                                         message containing the file which
                                                         is downloaded and the percent finished. 
        """
        if not self.embedding_model_is_cached():
            self.download_model_running = True
            self.download_model_cancel = False
            for file_name in self.model_files:
                local_path = os.path.join(self.model_folder, file_name)
                if os.path.exists(local_path):
                    continue  # skip this file, already downloaded
                url = hf_hub_url(self.model_name, file_name)
                
                # create local dir if necessary
                local_folder = os.path.dirname(local_path)  # (may contain subdir to model_folder)
                os.makedirs(local_folder, exist_ok=True)
                tmp_filename = local_path + ".tmp"
                
                # download
                r = requests.get(url, stream=True, timeout=20)
                r.raise_for_status()  # raise error on 404 etc.
                with open(tmp_filename, "wb") as f:
                    total_length = r.headers.get('content-length')
                    if total_length is not None:
                        total_length = int(total_length)
                        expected_size = (total_length / 1024) + 1
                    else:
                        expected_size = 0
                    i = 0
                    for chunk in r.iter_content(chunk_size=1024):
                        if self.download_model_cancel:
                            return  # cancel the download
                        if chunk:
                            f.write(chunk)
                            i += 1
                            if expected_size > 0:
                                msg = f'{os.path.basename(local_path)}: {round(i/expected_size * 100)}%'
                            else:
                                msg = f'{os.path.basename(local_path)}: 50%'
                            if signals is not None and signals.progress is not None:
                                signals.progress.emit(msg)
                            print(msg, '                           ', end='\r', flush=True)
                msg = f'{os.path.basename(local_path)}: 100%'
                if signals is not None and signals.progress is not None:
                    signals.progress.emit(msg)
                print(msg, '                           ', end='\r', flush=True)
                if os.path.exists(local_path):
                    os.remove(local_path)
                os.rename(tmp_filename, local_path) 
                
    def _download_embedding_model_callback(self, msg):
        self.download_model_msg = msg
    
    def _download_embedding_model_finished(self):
        if not self.ai_worker_running():
            self.download_model_running = False
            if self.download_model_cancel:
                msg = _("AI: Could not download all the necessary components, the AI integration will be disabled.")
            else:
                msg = _('AI: Success, components downloaded and installed.')
            self.parent_text_edit.append(msg)
            logger.debug(msg)

    def download_embedding_model(self):
        """Downloads the embedding model to the local cache if necessary.
        self.download_model_running will be True until all files have finished downloading.
        """
        self.download_model_running = True
        worker = Worker(self._download_embedding_model)
        worker.signals.finished.connect(self._download_embedding_model_finished)
        worker.signals.progress.connect(self._download_embedding_model_callback)
        worker.signals.error.connect(ai_exception_handler)
        self.threadpool.start(worker)
    
    def _open_db(self, signals):
        # "signals" is when this is called by the Worker in ai_async_worker. Cannot omit it.
        if self._is_closing:
            return  # abort when closing db
        self.faiss_db = None
        if self.app.project_path != '' and os.path.exists(self.app.project_path):
            if self.app.ai_embedding_function is None:
                self.app.ai_embedding_function = E5SentenceTransformerEmbeddings(model_name=self.model_folder)
            self.faiss_db_path = os.path.join(self.app.project_path, 'ai_data', 'vectorstore', 'faiss_store.bin')
            if os.path.exists(self.faiss_db_path): 
                # load existing faiss db
                try:
                    self.faiss_db = self.faiss_load(self.faiss_db_path)
                    # Signature of 'self.faiss_db.index.search' for
                    # generic index: (x, k, *, params=None, D=None, I=None)
                    # AVX2-index:    (n, x, k, distances, labels, params=None)
                    # Check based on that if the index is AVX2 and need rebuilding in generic format
                    if str(inspect.signature(self.faiss_db.index.search)).find('n, x, k') != -1:
                        # print(inspect.signature(self.faiss_db.index.search))
                        raise ValueError('faiss: AVX2 index cannot be used')
                except (ModuleNotFoundError, ValueError):  # This happens if an index with AVX2-optimization is loaded. We turned AVX2-optimization off because it is not cross-compatible with newer macs.
                    self.faiss_db = None
                    if signals is not None and signals.progress is not None:
                        msg = _('It appears that you have already used the AI features with this project before. '
                                'Meanwhile, we had to change the internal implementation of the local AI memory '
                                'to make it more robust. As a result, the AI has to read through all your '
                                'empirical documents again to rebuild the local memory. This may take a while. '
                                'Sorry for the inconvenience.')                        
                        signals.progress.emit(msg)
            if self.faiss_db is None:  # create new faiss db
                embedding_size = 1024  # embedding size of the used model: https://huggingface.co/intfloat/multilingual-e5-large
                faiss_index = faiss.IndexFlatL2(embedding_size) 
                self.faiss_db = FAISS(
                    embedding_function=self.app.ai_embedding_function,
                    index=faiss_index,
                    docstore=InMemoryDocstore(),
                    index_to_docstore_id={},
                )
                self.faiss_save()
        else:
            self.faiss_db = None
            logger.debug(f'Project path "{self.app.project_path}" not found.')
            raise FileNotFoundError(f'AI Vectorstore: project path "{self.app.project_path}" not found.')
        self.app.ai._status = ''
    
    def faiss_load(self, file_path) -> FAISS:
        """ load and return existing faiss db """
        with open(file_path, 'rb') as f:
            serialized_bytes_loaded = f.read()
        # Deserialize to reconstruct the FAISS vector store
        return FAISS.deserialize_from_bytes(
            serialized=serialized_bytes_loaded,
            embeddings=self.app.ai_embedding_function,
            allow_dangerous_deserialization=True
        )

    def faiss_save(self, faiss_db=None, faiss_db_path=None):
        """ Save faiss index and docstore to a binary file."""
        if faiss_db is None:
            faiss_db = self.faiss_db
        if faiss_db is None:
            return
        if faiss_db_path is None:
            faiss_db_path = self.faiss_db_path
        if faiss_db_path is None:
            raise FileNotFoundError(f'AI Vectorstore: faiss path not found.') 
        serialized_bytes = faiss_db.serialize_to_bytes()
        os.makedirs(os.path.dirname(faiss_db_path), exist_ok=True)
        with open(faiss_db_path, 'wb') as f:
            f.write(serialized_bytes)    

    def init_vectorstore(self, rebuild=False):
        """Initializes the vectorstore and checks if all text sources are stored.
        If rebuild is True, the contents of the vectorstore will be deleted
        and rebuild from the ground up.  

        Args:
            rebuild (bool, optional): Rebuild the vectorstore from the ground up. Defaults to False.
        """
        self._is_closing = False        
        self.prepare_embedding_model()
        if self.app.settings['ai_enable'] == 'False':
            self.close()
            self.app.ai._status = ''
            return
        
        if self.app.project_name == '':  # no project open
            self.close()
            self.parent_text_edit.append(_('AI: Finished loading (no project open).'))
            self.app.ai._status = ''
        else: 
            self.open_db(rebuild)
            
    def open_db(self, rebuild=False):
        """ Opens an existing vectorstore. 
        If rebuild is True, all documents will be read in again. """
         
        # Check if conversion chromadb to faiss vectorstore is necessary
        vectorstore_path = os.path.join(self.app.project_path, 'ai_data', 'vectorstore')
        faiss_path = os.path.join(vectorstore_path, 'faiss_store.bin') 
        if os.path.exists(vectorstore_path) and (not os.path.exists(faiss_path)):
            msg = _('It appears that you have already used the AI features with this project before. '
                    'Meanwhile, we had to change the internal implementation of the local AI memory '
                    'to make it more robust. As a result, the AI has to read through all your '
                    'empirical documents again to rebuild the local memory. This may take a while. '
                    'Sorry for the inconvenience.')
            Message(self.app, _('AI memory'), msg).exec()
        
        worker = Worker(self._open_db)  
        if rebuild:
            worker.signals.finished.connect(self.rebuild_vectorstore)
        else:
            worker.signals.finished.connect(self.update_vectorstore)
        worker.signals.error.connect(ai_exception_handler)
        worker.signals.progress.connect(self.open_progress)
        self.threadpool.start(worker)
    
    def open_progress(self, msg):
        Message(self.app, _('AI memory'), msg).exec()    
 
    def progress_import(self, msg):
        self.parent_text_edit.append(msg)
        
    def finished_import(self):
        self.import_workers_count -= 1
        if self.import_workers_count <= 0:
            self.import_workers_count = 0
            msg = _("AI: Checked all documents, memory is up to date.")
            self.parent_text_edit.append(msg)
            logger.debug(msg)
            
    def faiss_db_search_file_id(self, file_id, faiss_db=None):
        """Returns a list of embedded chunk ids (doc_id) for a certain file id 
        or an empty list if nothing is found."""
        if faiss_db is None:
            faiss_db = self.faiss_db
        if faiss_db is None:
            return []
        res = []
        for doc_id in faiss_db.index_to_docstore_id.values():
            doc = faiss_db.docstore.search(doc_id)
            if isinstance(doc, Document):
                if doc.metadata['id'] == file_id:
                    res.append(str(doc_id))
        return res

    def faiss_db_retrieve_documents(self, docstore_ids: List[str], faiss_db=None):
        """Returns a list of langchain_core.Documents corresponding to the list of 
        faiss docstore_ids. """
        if faiss_db is None:
            faiss_db = self.faiss_db
        if faiss_db is None:
            return []
        res = []
        for doc_id in faiss_db.index_to_docstore_id.values():
            if doc_id in docstore_ids:
                doc = faiss_db.docstore.search(doc_id)
                if isinstance(doc, Document):
                    res.append(doc)
        return res
    
    def _import_document(self, id_, name, text, update=False, signals=None):
        if self._is_closing:
            return  # abort when closing db
        if self.faiss_db is None:
            raise AIException(_('Vectorstore: Document import failed, faiss_db not present.'))
        # Check if the document is already in the store and delete if needed:        
        embeddings_list = self.faiss_db_search_file_id(id_)
        if len(embeddings_list) > 0:
            # check name of first embedded chunk 
            doc = self.faiss_db.docstore.search(embeddings_list[0])
            if update or doc.metadata['name'] != name:
                # delete old embeddings
                try:
                    self.faiss_db.delete(embeddings_list)
                except ValueError as e:
                    logger.debug(f'Error deleting document from faiss vector store: {e}')
                self.faiss_save()
            else:
                # skip the doc
                return 
        # add to faiss_db
        if self._is_closing:
            return  # abort when closing db
        
        # split fulltext into smaller chunks 
        if text != '':  # Can only add embeddings if text is not empty
            metadata = {'id': id_, 'name': name}
            document = Document(page_content=text, metadata=metadata)
            text_splitter = RecursiveCharacterTextSplitter(separators=[".", "!", "?", "\n\n", "\n", " ", ""], 
                                                        keep_separator='end', chunk_size=500, chunk_overlap=100, 
                                                        add_start_index=True)
            chunks = text_splitter.split_documents([document])
            
            if len(chunks) > 0:  # doc not empty 
                if signals is not None and signals.progress is not None:
                    self.reading_doc = name
                    signals.progress.emit(_('AI: Adding document to internal memory: ') + f'"{name}"')

                # create embeddings for these chunks and store them in the faiss_db (with metadata)
                for chunk in chunks:
                    if not self._is_closing:
                        uid = str(uuid4())
                        self.faiss_db.add_documents([chunk], ids=[uid])
                    else:  # Canceled, delete the unfinished document from the vectorstore:
                        embeddings_list = self.faiss_db_search_file_id(id_)
                        if len(embeddings_list) > 0:
                            try:
                                self.faiss_db.delete(embeddings_list)
                            except ValueError as e:
                                logger.debug(f'Error deleting document from faiss vector store: {e}')
                        break
                self.faiss_save()
        self.reading_doc = ''

    def import_document(self, id_, name, text, update=False):
        """Imports a document into the faiss_db. 
        If a document with the same id is already in 
        the faiss_db, it can be updated (update=True) 
        or skipped (update=False).
        This is an async process running in a background
        thread. AiVectorstore.is_ready() will return False
        until the import is finished.

        Args:
            id_ (integer): the database id
            name (String): document name
            text (String): document text
            update (bool, optional): defaults to False.
        """   
        
        worker = Worker(self._import_document, id_, name, text, update)  # Any other args, kwargs are passed to the run function
        # worker.signals.result.connect()
        worker.signals.finished.connect(self.finished_import)
        worker.signals.progress.connect(self.progress_import)
        worker.signals.error.connect(ai_exception_handler)
        self.import_workers_count += 1
        self.threadpool.start(worker)

    def update_vectorstore(self):
        """Collects all text sources from the database and adds them to the faiss_db if 
        not already in there.  
        """
        self.app.ai._status = ''
        if self.faiss_db is None:
            logger.debug('faiss_db is None')
            return
        docs = self.app.get_file_texts()
        
        # Check if any docs in the vectorstore have been deleted or renamed in the project
        def search_name(docs_, name):
            for document in docs_:
                if document['name'] == name:
                    return True
            return False

        for idx, doc_id in self.faiss_db.index_to_docstore_id.items():
            doc = self.faiss_db.docstore.search(doc_id)
            if isinstance(doc, Document):
                if not search_name(docs, doc.metadata['name']):
                    try:
                        self.faiss_db.delete([idx])
                    except ValueError as e:
                        logger.debug(f'Error deleting document from faiss vector store: {e}')

        # Add new docs
        if len(docs) == 0:
            msg = _("AI: No documents, AI is ready.")
            self.parent_text_edit.append(msg)
            logger.debug(msg)
        else:
            msg = _("AI: Checking for new documents")
            self.parent_text_edit.append(msg)
            logger.debug(msg)
            for doc in docs:
                self.import_document(doc['id'], doc['name'], doc['fulltext'], False)
            
    def rebuild_vectorstore(self):
        """Deletes all contents from faiss_db and rebuilds the vectorstore from the ground up.  
        """
        self.app.ai._status = ''
        if self.faiss_db is None:
            logger.debug('faiss_db is None')
            return
        msg = _('AI: Rebuilding memory. The local AI will read through all your documents, please be patient.')
        self.parent_text_edit.append(msg)
        logger.debug(msg)
        # create a new, empty database:
        embedding_size = 1024  # embedding size of the used model: https://huggingface.co/intfloat/multilingual-e5-large
        faiss_index = faiss.IndexFlatL2(embedding_size) 
        self.faiss_db = FAISS(
            embedding_function=self.app.ai_embedding_function,
            index=faiss_index,
            docstore=InMemoryDocstore(),
            index_to_docstore_id={},
        )
        self.faiss_save()
        # rebuild vectorstore
        self.update_vectorstore()
    
    def delete_document(self, id_):
        """Deletes all the embeddings from related to this doc 
        from the vectorstore"""

        faiss_db = self.faiss_db
        faiss_db_path = self.faiss_db_path
        if faiss_db is None:
            # Try to create a temporary access
            faiss_db_path = os.path.join(self.app.project_path, 'ai_data', 'vectorstore', 'faiss_store.bin')
            if os.path.exists(faiss_db_path): 
                try:
                    faiss_db = self.faiss_load(faiss_db_path)
                except ModuleNotFoundError:
                    faiss_db = None
        if faiss_db is not None:
            embeddings_list = self.faiss_db_search_file_id(id_, faiss_db=faiss_db)
            if len(embeddings_list) > 0:
                try:
                    faiss_db.delete(embeddings_list)
                except ValueError as e:
                    logger.debug(f'Error deleting document from faiss vector store: {e}')
                self.faiss_save(faiss_db=faiss_db, faiss_db_path=faiss_db_path)
               
    def close(self):
        """Cancels the update process if running"""
        self._is_closing = True
        self.download_model_cancel = True
        # cancel all waiting threads:
        self.threadpool.clear()
        self.threadpool.waitForDone(5000)
        self.import_workers_count = 0
        self.faiss_db = None
        self._is_closing = False
        
    def ai_worker_running(self):
        return self.import_workers_count
        #return self.threadpool.activeThreadCount() > 0
            
    def is_open(self) -> bool:
        """Returnes True if the vectorstore is initiated"""
        return self.faiss_db is not None and self._is_closing is False
    
    def is_ready(self) -> bool:
        """If the vectorstore is initiated and done importing data, 
        it is ready for queries."""
        return self.is_open() and not self.ai_worker_running()
        
    
        
