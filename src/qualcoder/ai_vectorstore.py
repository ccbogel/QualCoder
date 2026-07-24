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
https://qualcoder.org/
"""

import hashlib
import logging
import math
import os
import re
import sqlite3
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple, Union

os.environ['FAISS_NO_AVX2'] = '1'
# Setting the env 'FAISS_OPT_LEVEL' to '' will create a 'generic' index. It is a poorly documented 
# feature introduced here: https://github.com/facebookresearch/faiss/commit/eefa39105eda498ab5fcd82ea0e11b18fd3fc0d7
# Must be set before importing faiss. This tells faiss not to use AVX2, which makes the resulting
# index also compatible with older machines and non-intel platforms.    
os.environ['FAISS_OPT_LEVEL'] = '' 
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

from huggingface_hub import hf_hub_url
import faiss
import numpy as np
import requests
import sentence_transformers  # Keep a reference so it is not garbage collected in subthreads.
from langchain_community.embeddings import SentenceTransformerEmbeddings
from langchain_community.vectorstores import FAISS as LegacyFAISS
from PyQt6 import QtCore, QtWidgets

from qualcoder.ai_async_worker import AIException
from qualcoder.ai_async_worker import Worker
from qualcoder.error_dlg import show_error_dlg
from qualcoder.helpers import Message

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)


def ai_exception_handler(exception_type, value, tb_obj):
    """Show error message."""

    msg = exception_type.__name__ + ': ' + str(value)
    tb = '\n'.join(traceback.format_tb(tb_obj))
    logger.error(_("Uncaught exception: ") + msg + '\n' + tb)
    show_error_dlg(msg, tb)


@dataclass
class SearchChunkDocument:
    """Lightweight replacement for the LangChain Document used by the AI workflow."""

    page_content: str
    metadata: Dict[str, Union[str, int, float]]
    id: str


class E5SentenceTransformerEmbeddings(SentenceTransformerEmbeddings):

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        emb_texts = []
        for text in texts:
            emb_texts.append('passage: ' + text)
        return super().embed_documents(texts=emb_texts)

    def embed_query(self, text: str) -> List[float]:
        return super().embed_documents([f'query: {text}'])[0]


class _RecursiveTextChunker:
    """Adapted from LangChain's RecursiveCharacterTextSplitter."""

    def __init__(self, separators: Optional[List[str]] = None, chunk_size: int = 500,
                 chunk_overlap: int = 100, keep_separator: Union[bool, str] = "end",
                 strip_whitespace: bool = True):
        if chunk_overlap > chunk_size:
            raise ValueError("chunk_overlap must be <= chunk_size")
        self._separators = separators or ["\n\n", "\n", " ", ""]
        self._chunk_size = int(chunk_size)
        self._chunk_overlap = int(chunk_overlap)
        self._keep_separator = keep_separator
        self._strip_whitespace = strip_whitespace

    def _split_text_with_regex(self, text: str, separator: str) -> List[str]:
        if separator:
            if self._keep_separator:
                raw_splits = re.split(f"({re.escape(separator)})", text)
                if self._keep_separator == "end":
                    splits = [raw_splits[i] + raw_splits[i + 1] for i in range(0, len(raw_splits) - 1, 2)]
                else:
                    splits = [raw_splits[i] + raw_splits[i + 1] for i in range(1, len(raw_splits), 2)]
                if len(raw_splits) % 2 == 0:
                    splits += raw_splits[-1:]
                if self._keep_separator == "end":
                    splits = splits + raw_splits[-1:]
                else:
                    splits = raw_splits[:1] + splits
            else:
                splits = re.split(re.escape(separator), text)
        else:
            splits = list(text)
        return [split for split in splits if split != ""]

    def _join_docs(self, docs: List[str], separator: str) -> Optional[str]:
        text = separator.join(docs)
        if self._strip_whitespace:
            text = text.strip()
        return None if text == "" else text

    def _merge_splits(self, splits: Iterable[str], separator: str) -> List[str]:
        separator_len = len(separator)
        docs: List[str] = []
        current_doc: List[str] = []
        total = 0
        for item in splits:
            item_len = len(item)
            if total + item_len + (separator_len if current_doc else 0) > self._chunk_size:
                if total > self._chunk_size:
                    logger.warning(
                        "Created a chunk of size %s, larger than the configured chunk_size %s",
                        total,
                        self._chunk_size,
                    )
                if current_doc:
                    merged = self._join_docs(current_doc, separator)
                    if merged is not None:
                        docs.append(merged)
                    while total > self._chunk_overlap or (
                        total + item_len + (separator_len if current_doc else 0) > self._chunk_size and total > 0
                    ):
                        total -= len(current_doc[0]) + (separator_len if len(current_doc) > 1 else 0)
                        current_doc = current_doc[1:]
            current_doc.append(item)
            total += item_len + (separator_len if len(current_doc) > 1 else 0)

        merged = self._join_docs(current_doc, separator)
        if merged is not None:
            docs.append(merged)
        return docs

    def _split_text(self, text: str, separators: List[str]) -> List[str]:
        final_chunks: List[str] = []
        separator = separators[-1]
        new_separators: List[str] = []
        for idx, candidate in enumerate(separators):
            if candidate == "":
                separator = candidate
                break
            if re.search(re.escape(candidate), text):
                separator = candidate
                new_separators = separators[idx + 1:]
                break

        splits = self._split_text_with_regex(text, separator)
        good_splits: List[str] = []
        merge_separator = "" if self._keep_separator else separator
        for split in splits:
            if len(split) < self._chunk_size:
                good_splits.append(split)
                continue
            if good_splits:
                final_chunks.extend(self._merge_splits(good_splits, merge_separator))
                good_splits = []
            if not new_separators:
                final_chunks.append(split)
            else:
                final_chunks.extend(self._split_text(split, new_separators))

        if good_splits:
            final_chunks.extend(self._merge_splits(good_splits, merge_separator))
        return final_chunks

    def split_text(self, text: str) -> List[str]:
        return self._split_text(text, self._separators)

    def create_documents(self, text: str, metadata: Dict[str, Union[str, int]]) -> List[SearchChunkDocument]:
        documents: List[SearchChunkDocument] = []
        index = 0
        previous_chunk_len = 0
        for chunk_idx, chunk in enumerate(self.split_text(text)):
            chunk_meta = dict(metadata)
            offset = index + previous_chunk_len - self._chunk_overlap
            index = text.find(chunk, max(0, offset))
            chunk_meta["start_index"] = index
            chunk_meta["chunk_index"] = chunk_idx
            previous_chunk_len = len(chunk)
            documents.append(SearchChunkDocument(page_content=chunk, metadata=chunk_meta, id=""))
        return documents


class _CompatFaissStore:
    """Compatibility shim for the old ai_llm lookup path."""

    def __init__(self, vectorstore: "AiVectorstore"):
        self._vectorstore = vectorstore

    def similarity_search_with_relevance_scores(self, query: str, k: int = 4,
                                                filter=None, fetch_k: int = 20, **kwargs):
        score_threshold = kwargs.get("score_threshold", 0.0)
        return self._vectorstore.similarity_search_with_relevance_scores(
            query,
            k=k,
            score_threshold=score_threshold,
            metadata_filter=filter,
            fetch_k=fetch_k,
        )


class AiVectorstore:
    """Persistent SQLite chunk store plus an in-memory FAISS index."""

    app = None
    parent_text_edit = None
    ready = False
    import_workers_count = 0
    vectorstore_workers_count = 0
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

    schema_version = 1
    embedding_dim = 1024
    chunk_size = 500
    chunk_overlap = 100
    chunker_version = "recursive_char_v1"
    chunk_separators = [".", "!", "?", "\n\n", "\n", " ", ""]

    def __init__(self, app, parent_text_edit, collection_name):
        self.app = app
        self.parent_text_edit = parent_text_edit
        self.collection_name = collection_name
        self.threadpool = QtCore.QThreadPool()
        self.threadpool.setMaxThreadCount(1)
        self._search_db_path = ""
        self._legacy_faiss_path = ""
        self._faiss_index = None
        self._chunk_ids_by_pos: List[int] = []
        self._compat_store = _CompatFaissStore(self)
        self._chunker = _RecursiveTextChunker(
            separators=list(self.chunk_separators),
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            keep_separator="end",
        )

    def prepare_embedding_model(self, parent_window=None) -> bool:
        if not self.embedding_model_is_cached():
            model_download_msg = _(
                'Since you are using the AI integration for the first time, '
                'QualCoder needs to download and install some '
                'additional components. \n\n'
                'This will download about 2.5 GB of data. Do you \n'
                'want to continue?'
            )
            mb = QtWidgets.QMessageBox(parent=parent_window)
            mb.setWindowTitle(_('Download AI components'))
            mb.setText(model_download_msg)
            mb.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok | QtWidgets.QMessageBox.StandardButton.Abort)
            mb.setStyleSheet('* {font-size: ' + str(self.app.settings['fontsize']) + 'pt}')
            if mb.exec() == QtWidgets.QMessageBox.StandardButton.Ok:
                pd = QtWidgets.QProgressDialog(
                    labelText='                              ',
                    minimum=0,
                    maximum=100,
                    parent=parent_window,
                )
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
                    msg = self.download_model_msg
                    msgs = msg.split(':')
                    if len(msgs) > 1:
                        pd.setValue(int(''.join(filter(str.isdigit, msgs[1]))))
                        msg = msgs[0]
                    else:
                        pd.setValue(0)
                    pd.setLabelText(_('Downloading ') + msg)
                    QtWidgets.QApplication.processEvents()
                    time.sleep(0.01)
                pd.close()
            else:
                self.app.settings['ai_enable'] = 'False'
                return False
        return True

    def embedding_model_is_cached(self) -> bool:
        for model_file in self.model_files:
            if not os.path.exists(os.path.join(self.model_folder, model_file)):
                return False
        return True

    def _download_embedding_model(self, signals=None):
        if not self.embedding_model_is_cached():
            self.download_model_running = True
            self.download_model_cancel = False
            for file_name in self.model_files:
                local_path = os.path.join(self.model_folder, file_name)
                if os.path.exists(local_path):
                    continue
                url = hf_hub_url(self.model_name, file_name)
                local_folder = os.path.dirname(local_path)
                os.makedirs(local_folder, exist_ok=True)
                tmp_filename = local_path + ".tmp"
                response = requests.get(url, stream=True, timeout=20)
                response.raise_for_status()
                with open(tmp_filename, "wb") as handle:
                    total_length = response.headers.get('content-length')
                    if total_length is not None:
                        total_length = int(total_length)
                        expected_size = (total_length / 1024) + 1
                    else:
                        expected_size = 0
                    count = 0
                    for chunk in response.iter_content(chunk_size=1024):
                        if self.download_model_cancel:
                            return
                        if not chunk:
                            continue
                        handle.write(chunk)
                        count += 1
                        if expected_size > 0:
                            msg = f'{os.path.basename(local_path)}: {round(count / expected_size * 100)}%'
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
        self.download_model_running = True
        worker = Worker(self._download_embedding_model)
        worker.signals.finished.connect(self._download_embedding_model_finished)
        worker.signals.progress.connect(self._download_embedding_model_callback)
        worker.signals.error.connect(ai_exception_handler)
        self.threadpool.start(worker)

    def _ensure_embedding_function(self):
        if self.app.ai_embedding_function is None:
            self.app.ai_embedding_function = E5SentenceTransformerEmbeddings(model_name=self.model_folder)

    def _project_ai_dir(self) -> str:
        if self.app.project_path == '' or not os.path.exists(self.app.project_path):
            raise FileNotFoundError(f'AI Vectorstore: project path "{self.app.project_path}" not found.')
        ai_dir = os.path.join(self.app.project_path, 'ai_data')
        os.makedirs(ai_dir, exist_ok=True)
        return ai_dir

    def _set_project_paths(self):
        ai_dir = self._project_ai_dir()
        self._search_db_path = os.path.join(ai_dir, 'search.sqlite')
        self._legacy_faiss_path = os.path.join(ai_dir, 'vectorstore', 'faiss_store.bin')
        self.faiss_db_path = self._search_db_path

    def _project_db_path(self) -> str:
        if self.app.project_path == '' or not os.path.exists(self.app.project_path):
            raise FileNotFoundError(f'AI Vectorstore: project path "{self.app.project_path}" not found.')
        return os.path.join(self.app.project_path, 'data.qda')

    def _connect_project_db(self) -> sqlite3.Connection:
        return sqlite3.connect(self._project_db_path(), timeout=30)

    def _fetch_project_text_sources(self) -> List[Dict[str, Union[str, int, None]]]:
        conn = self._connect_project_db()
        try:
            rows = conn.execute(
                "SELECT name, id, fulltext, ifnull(memo,''), owner, date, mediapath "
                "FROM source WHERE fulltext IS NOT NULL ORDER BY name"
            ).fetchall()
        finally:
            conn.close()
        keys = ('name', 'id', 'fulltext', 'memo', 'owner', 'date', 'mediapath')
        return [dict(zip(keys, row)) for row in rows]

    def _connect_search_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._search_db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA temp_store=MEMORY")
        return conn

    def _ensure_search_schema(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE IF NOT EXISTS search_meta ("
            "schema_version INTEGER NOT NULL, "
            "embedding_model TEXT NOT NULL, "
            "chunker_version TEXT NOT NULL, "
            "chunk_size INTEGER NOT NULL, "
            "chunk_overlap INTEGER NOT NULL, "
            "metric TEXT NOT NULL, "
            "build_state TEXT NOT NULL, "
            "last_build_at TEXT NOT NULL)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS search_source_state ("
            "source_id INTEGER PRIMARY KEY, "
            "source_name TEXT NOT NULL, "
            "text_hash TEXT NOT NULL, "
            "text_len INTEGER NOT NULL, "
            "last_indexed_at TEXT NOT NULL)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS search_chunks ("
            "chunk_id INTEGER PRIMARY KEY, "
            "source_id INTEGER NOT NULL, "
            "source_name TEXT NOT NULL, "
            "chunk_index INTEGER NOT NULL, "
            "start_index INTEGER NOT NULL, "
            "length INTEGER NOT NULL, "
            "text TEXT NOT NULL, "
            "text_hash TEXT NOT NULL, "
            "hash_ordinal INTEGER NOT NULL)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_search_chunks_source_chunk "
            "ON search_chunks(source_id, chunk_index)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_search_chunks_source_hash "
            "ON search_chunks(source_id, text_hash, hash_ordinal)"
        )
        cur.execute(
            "CREATE TABLE IF NOT EXISTS search_embeddings ("
            "chunk_id INTEGER PRIMARY KEY, "
            "dim INTEGER NOT NULL, "
            "vector_blob BLOB NOT NULL, "
            "FOREIGN KEY (chunk_id) REFERENCES search_chunks(chunk_id) ON DELETE CASCADE)"
        )
        cur.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS search_chunk_fts USING fts5("
            "chunk_id UNINDEXED, "
            "source_id UNINDEXED, "
            "source_name UNINDEXED, "
            "start_index UNINDEXED, "
            "length UNINDEXED, "
            "text)"
        )
        row = cur.execute("SELECT schema_version FROM search_meta LIMIT 1").fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO search_meta(schema_version, embedding_model, chunker_version, chunk_size, chunk_overlap, metric, build_state, last_build_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    self.schema_version,
                    self.model_name,
                    self.chunker_version,
                    self.chunk_size,
                    self.chunk_overlap,
                    "l2",
                    "ready",
                    datetime.utcnow().isoformat(timespec="seconds"),
                ),
            )
        conn.commit()

    def _meta_schema_version(self, conn: sqlite3.Connection) -> int:
        row = conn.execute("SELECT schema_version FROM search_meta LIMIT 1").fetchone()
        if row is None:
            return 0
        try:
            return int(row[0])
        except (TypeError, ValueError):
            return 0

    def _set_meta_build_state(self, conn: sqlite3.Connection, state: str) -> None:
        conn.execute(
            "UPDATE search_meta SET build_state=?, last_build_at=?",
            (str(state), datetime.utcnow().isoformat(timespec="seconds")),
        )
        conn.commit()

    def _reset_search_store(self, conn: sqlite3.Connection) -> None:
        conn.execute("DELETE FROM search_embeddings")
        conn.execute("DELETE FROM search_chunks")
        conn.execute("DELETE FROM search_source_state")
        conn.execute("DELETE FROM search_chunk_fts")
        conn.commit()

    def _hash_text(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _vector_to_blob(self, vector: np.ndarray):
        arr = np.asarray(vector, dtype=np.float32)
        return sqlite3.Binary(arr.tobytes())

    def _blob_to_vector(self, blob) -> np.ndarray:
        return np.frombuffer(blob, dtype=np.float32).copy()

    def _compute_hash_ordinals(self, docs: List[SearchChunkDocument]) -> None:
        seen: Dict[str, int] = defaultdict(int)
        for doc in docs:
            text_hash = self._hash_text(doc.page_content)
            doc.metadata["text_hash"] = text_hash
            doc.metadata["hash_ordinal"] = seen[text_hash]
            seen[text_hash] += 1

    def _split_source_text(self, source_id: int, source_name: str, text: str) -> List[SearchChunkDocument]:
        docs = self._chunker.create_documents(text, {"id": int(source_id), "name": str(source_name)})
        self._compute_hash_ordinals(docs)
        return docs

    def _load_existing_vectors_by_hash(self, conn: sqlite3.Connection, source_id: int) -> Dict[str, List[np.ndarray]]:
        rows = conn.execute(
            "SELECT c.text_hash, e.vector_blob "
            "FROM search_chunks c JOIN search_embeddings e ON e.chunk_id = c.chunk_id "
            "WHERE c.source_id=? ORDER BY c.chunk_index",
            (int(source_id),),
        ).fetchall()
        result: Dict[str, List[np.ndarray]] = defaultdict(list)
        for text_hash, vector_blob in rows:
            if text_hash is None or vector_blob is None:
                continue
            result[str(text_hash)].append(self._blob_to_vector(vector_blob))
        return result

    def _delete_source_rows(self, conn: sqlite3.Connection, source_id: int) -> None:
        conn.execute("DELETE FROM search_chunk_fts WHERE source_id=?", (int(source_id),))
        conn.execute(
            "DELETE FROM search_embeddings WHERE chunk_id IN (SELECT chunk_id FROM search_chunks WHERE source_id=?)",
            (int(source_id),),
        )
        conn.execute("DELETE FROM search_chunks WHERE source_id=?", (int(source_id),))
        conn.execute("DELETE FROM search_source_state WHERE source_id=?", (int(source_id),))

    def _index_source(self, conn: sqlite3.Connection, source_id: int, source_name: str, text: str,
                      candidate_vectors_by_hash: Optional[Dict[str, List[np.ndarray]]] = None,
                      signals=None) -> int:
        if self._is_closing:
            return 0

        docs = self._split_source_text(source_id, source_name, text)
        if candidate_vectors_by_hash is None:
            candidate_vectors_by_hash = self._load_existing_vectors_by_hash(conn, source_id)
        else:
            normalized: Dict[str, List[np.ndarray]] = defaultdict(list)
            for key, vectors in candidate_vectors_by_hash.items():
                normalized[str(key)] = [np.asarray(vec, dtype=np.float32) for vec in vectors]
            candidate_vectors_by_hash = normalized

        # NOTE: old rows are deleted AFTER the embedding (below). It used to happen
        # here, without commit, and the implicit write transaction stayed open for
        # the whole embed_documents (minutes with local models): any other writer of
        # search.sqlite (e.g. delete_document from the UI thread when deleting a
        # file) exhausted the 30 s busy_timeout and died with "database is locked".

        if signals is not None and signals.progress is not None and self.reading_doc != source_name:
            self.reading_doc = source_name
            signals.progress.emit(_('AI: Adding document to internal memory: ') + f'"{source_name}"')

        texts_to_embed: List[str] = []
        chunk_vectors: List[Optional[np.ndarray]] = []
        for doc in docs:
            text_hash = str(doc.metadata["text_hash"])
            vectors = candidate_vectors_by_hash.get(text_hash, [])
            if vectors:
                chunk_vectors.append(vectors.pop(0))
            else:
                chunk_vectors.append(None)
                texts_to_embed.append(doc.page_content)

        new_vectors: List[np.ndarray] = []
        if texts_to_embed:
            embedded = self.app.ai_embedding_function.embed_documents(texts_to_embed)
            new_vectors = [np.asarray(vec, dtype=np.float32) for vec in embedded]

        # Delete + reinsert in one short atomic transaction, with the vectors already
        # computed: the write-lock window is minimal.
        self._delete_source_rows(conn, source_id)

        embedded_idx = 0
        for doc in docs:
            vector = chunk_vectors.pop(0)
            if vector is None:
                vector = new_vectors[embedded_idx]
                embedded_idx += 1

            cur = conn.execute(
                "INSERT INTO search_chunks(source_id, source_name, chunk_index, start_index, length, text, text_hash, hash_ordinal) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    int(source_id),
                    str(source_name),
                    int(doc.metadata["chunk_index"]),
                    int(doc.metadata["start_index"]),
                    len(doc.page_content),
                    doc.page_content,
                    str(doc.metadata["text_hash"]),
                    int(doc.metadata["hash_ordinal"]),
                ),
            )
            chunk_id = int(cur.lastrowid)
            doc.id = str(chunk_id)
            conn.execute(
                "INSERT INTO search_embeddings(chunk_id, dim, vector_blob) VALUES (?, ?, ?)",
                (chunk_id, int(vector.shape[0]), self._vector_to_blob(vector)),
            )
            conn.execute(
                "INSERT INTO search_chunk_fts(chunk_id, source_id, source_name, start_index, length, text) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    chunk_id,
                    int(source_id),
                    str(source_name),
                    int(doc.metadata["start_index"]),
                    len(doc.page_content),
                    doc.page_content,
                ),
            )

        conn.execute(
            "INSERT OR REPLACE INTO search_source_state(source_id, source_name, text_hash, text_len, last_indexed_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                int(source_id),
                str(source_name),
                self._hash_text(text),
                len(text),
                datetime.utcnow().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()
        self.reading_doc = ''
        return len(docs)

    def _build_candidate_vectors_from_legacy(self, source_id: int, source_name: str, text: str,
                                             legacy_items: List[Tuple[int, str, np.ndarray]]) -> Dict[str, List[np.ndarray]]:
        result: Dict[str, List[np.ndarray]] = defaultdict(list)
        current_len = len(text)
        for start_index, chunk_text, vector in sorted(legacy_items, key=lambda item: item[0]):
            if start_index < 0 or chunk_text == "":
                continue
            end_index = start_index + len(chunk_text)
            if end_index > current_len:
                continue
            if text[start_index:end_index] != chunk_text:
                continue
            result[self._hash_text(chunk_text)].append(np.asarray(vector, dtype=np.float32))
        return result

    def _load_legacy_candidates(self) -> Dict[int, List[Tuple[int, str, np.ndarray]]]:
        result: Dict[int, List[Tuple[int, str, np.ndarray]]] = defaultdict(list)
        if not os.path.exists(self._legacy_faiss_path):
            return result
        with open(self._legacy_faiss_path, 'rb') as handle:
            serialized_bytes = handle.read()
        legacy_store = LegacyFAISS.deserialize_from_bytes(
            serialized=serialized_bytes,
            embeddings=self.app.ai_embedding_function,
            allow_dangerous_deserialization=True,
        )
        index = getattr(legacy_store, "index", None)
        docstore = getattr(legacy_store, "docstore", None)
        index_to_docstore_id = getattr(legacy_store, "index_to_docstore_id", {})
        if index is None or docstore is None:
            return result
        for pos, docstore_id in index_to_docstore_id.items():
            try:
                doc = docstore.search(docstore_id)
            except Exception:
                doc = None
            if doc is None or not hasattr(doc, "page_content") or not hasattr(doc, "metadata"):
                continue
            metadata = getattr(doc, "metadata", {})
            if not isinstance(metadata, dict):
                continue
            try:
                source_id = int(metadata.get("id", -1))
                start_index = int(metadata.get("start_index", -1))
            except (TypeError, ValueError):
                continue
            if source_id <= 0 or start_index < 0:
                continue
            chunk_text = str(getattr(doc, "page_content", ""))
            if chunk_text == "":
                continue
            try:
                vector = np.asarray(index.reconstruct(int(pos)), dtype=np.float32)
            except Exception:
                continue
            result[source_id].append((start_index, chunk_text, vector))
        return result

    def _rebuild_faiss_index_from_db(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            "SELECT c.chunk_id, e.dim, e.vector_blob "
            "FROM search_chunks c JOIN search_embeddings e ON e.chunk_id = c.chunk_id "
            "ORDER BY c.chunk_id"
        ).fetchall()
        dim = self.embedding_dim
        if rows:
            try:
                dim = int(rows[0][1])
            except (TypeError, ValueError):
                dim = self.embedding_dim
        self._faiss_index = faiss.IndexFlatL2(dim)
        self._chunk_ids_by_pos = []
        if not rows:
            self.faiss_db = self._compat_store
            return
        matrix = np.vstack([self._blob_to_vector(row[2]) for row in rows]).astype(np.float32)
        self._faiss_index.add(np.ascontiguousarray(matrix))
        self._chunk_ids_by_pos = [int(row[0]) for row in rows]
        self.faiss_db = self._compat_store

    def _refresh_sources(self, conn: sqlite3.Connection, signals=None,
                         legacy_candidates: Optional[Dict[int, List[Tuple[int, str, np.ndarray]]]] = None) -> None:
        docs = self._fetch_project_text_sources()
        current_source_ids = {int(doc['id']) for doc in docs}
        existing_ids = {int(row[0]) for row in conn.execute("SELECT source_id FROM search_source_state").fetchall()}
        for source_id in sorted(existing_ids.difference(current_source_ids)):
            self._delete_source_rows(conn, source_id)
        conn.commit()

        if len(docs) == 0:
            msg = _("AI: No documents, AI is ready.")
            self.parent_text_edit.append(msg)
            logger.debug(msg)
            return

        msg = _("AI: Checking for new documents")
        self.parent_text_edit.append(msg)
        logger.debug(msg)

        for doc in docs:
            source_id = int(doc['id'])
            source_name = str(doc['name'])
            text = "" if doc['fulltext'] is None else str(doc['fulltext'])
            current_hash = self._hash_text(text)
            row = conn.execute(
                "SELECT text_hash, source_name FROM search_source_state WHERE source_id=?",
                (source_id,),
            ).fetchone()
            if row is not None and str(row[0]) == current_hash and str(row[1]) == source_name:
                continue

            candidates = None
            if legacy_candidates is not None and source_id in legacy_candidates:
                candidates = self._build_candidate_vectors_from_legacy(
                    source_id,
                    source_name,
                    text,
                    legacy_candidates[source_id],
                )
            self._index_source(conn, source_id, source_name, text, candidate_vectors_by_hash=candidates, signals=signals)

    def _open_db(self, rebuild=False, signals=None):
        if self._is_closing:
            return
        if self.app.project_path != '' and os.path.exists(self.app.project_path):
            self._ensure_embedding_function()
            self._set_project_paths()
            os.makedirs(os.path.dirname(self._legacy_faiss_path), exist_ok=True)
            conn = self._connect_search_db()
            try:
                self._ensure_search_schema(conn)
                if self._meta_schema_version(conn) != self.schema_version:
                    self._reset_search_store(conn)
                    conn.execute(
                        "UPDATE search_meta SET schema_version=?, embedding_model=?, chunker_version=?, chunk_size=?, chunk_overlap=?, metric=?",
                        (
                            self.schema_version,
                            self.model_name,
                            self.chunker_version,
                            self.chunk_size,
                            self.chunk_overlap,
                            "l2",
                        ),
                    )
                    conn.commit()

                legacy_candidates = None
                self._set_meta_build_state(conn, "building")
                if rebuild:
                    msg = _('AI: Rebuilding memory. The local AI will read through all your documents, please be patient.')
                    self.parent_text_edit.append(msg)
                    logger.debug(msg)
                    self._reset_search_store(conn)
                else:
                    has_chunks = conn.execute("SELECT 1 FROM search_chunks LIMIT 1").fetchone() is not None
                    if not has_chunks and os.path.exists(self._legacy_faiss_path):
                        if signals is not None and signals.progress is not None:
                            signals.progress.emit(
                                _('Migrating the existing AI memory to the new internal search database...')
                            )
                        try:
                            legacy_candidates = self._load_legacy_candidates()
                        except Exception:
                            legacy_candidates = None
                            if signals is not None and signals.progress is not None:
                                signals.progress.emit(
                                    _('The old AI memory could not be migrated automatically. Rebuilding from the project texts instead.')
                                )
                self._refresh_sources(conn, signals=signals, legacy_candidates=legacy_candidates)
                self._rebuild_faiss_index_from_db(conn)
                self._set_meta_build_state(conn, "ready")
                msg = _("AI: Checked all documents, memory is up to date.")
                self.parent_text_edit.append(msg)
                logger.debug(msg)
            finally:
                conn.close()
        else:
            self.faiss_db = None
            self._faiss_index = None
            self._chunk_ids_by_pos = []
            logger.debug(f'Project path "{self.app.project_path}" not found.')
            raise FileNotFoundError(f'AI Vectorstore: project path "{self.app.project_path}" not found.')
        self.app.ai._status = ''

    def init_vectorstore(self, rebuild=False):
        self._is_closing = False
        self.prepare_embedding_model()
        if self.app.settings['ai_enable'] == 'False':
            self.close()
            self.app.ai._status = ''
            return
        if self.app.project_name == '':
            self.close()
            self.parent_text_edit.append(_('AI: Finished loading (no project open).'))
            self.app.ai._status = ''
        else:
            self.app.ai._status = ''
            self.open_db(rebuild)

    def open_db(self, rebuild=False):
        worker = Worker(self._open_db, rebuild)
        self.vectorstore_workers_count += 1
        worker.signals.finished.connect(self._finish_vectorstore_worker)
        worker.signals.error.connect(ai_exception_handler)
        worker.signals.progress.connect(self.open_progress)
        self.threadpool.start(worker)

    def open_progress(self, msg):
        self.parent_text_edit.append(msg)
        logger.debug(msg)

    def progress_import(self, msg):
        self.parent_text_edit.append(msg)

    def finished_import(self):
        self._finish_vectorstore_worker()
        self.import_workers_count -= 1
        if self.import_workers_count <= 0:
            self.import_workers_count = 0
            msg = _("AI: Checked all documents, memory is up to date.")
            self.parent_text_edit.append(msg)
            logger.debug(msg)

    def _finish_vectorstore_worker(self):
        if self.vectorstore_workers_count > 0:
            self.vectorstore_workers_count -= 1

    def _query_embedding(self, query: str) -> np.ndarray:
        vector = self.app.ai_embedding_function.embed_query(query)
        return np.asarray(vector, dtype=np.float32)

    def _fetch_documents_by_chunk_ids(self, chunk_ids: List[int]) -> Dict[int, SearchChunkDocument]:
        result: Dict[int, SearchChunkDocument] = {}
        if not chunk_ids:
            return result
        normalized_ids = []
        for chunk_id in chunk_ids:
            try:
                cid = int(chunk_id)
            except (TypeError, ValueError):
                continue
            if cid > 0 and cid not in normalized_ids:
                normalized_ids.append(cid)
        if not normalized_ids:
            return result
        placeholders = ",".join(["?"] * len(normalized_ids))
        conn = self._connect_search_db()
        try:
            rows = conn.execute(
                "SELECT chunk_id, source_id, source_name, start_index, text FROM search_chunks "
                f"WHERE chunk_id IN ({placeholders})",
                tuple(normalized_ids),
            ).fetchall()
        finally:
            conn.close()
        for row in rows:
            chunk_id = int(row[0])
            result[chunk_id] = SearchChunkDocument(
                page_content=str(row[4]),
                metadata={
                    "id": int(row[1]),
                    "name": str(row[2]),
                    "start_index": int(row[3]),
                },
                id=str(chunk_id),
            )
        return result

    def faiss_db_retrieve_documents(self, docstore_ids: List[str], faiss_db=None):
        chunk_ids: List[int] = []
        for docstore_id in docstore_ids:
            try:
                chunk_id = int(str(docstore_id).strip())
            except (TypeError, ValueError):
                continue
            if chunk_id > 0:
                chunk_ids.append(chunk_id)
        docs_map = self._fetch_documents_by_chunk_ids(chunk_ids)
        result: List[SearchChunkDocument] = []
        for chunk_id in chunk_ids:
            doc = docs_map.get(chunk_id)
            if doc is not None:
                result.append(doc)
        return result

    def faiss_db_search_file_id(self, file_id, faiss_db=None):
        conn = self._connect_search_db()
        try:
            rows = conn.execute(
                "SELECT chunk_id FROM search_chunks WHERE source_id=? ORDER BY chunk_index",
                (int(file_id),),
            ).fetchall()
        finally:
            conn.close()
        return self.faiss_db_retrieve_documents([str(row[0]) for row in rows])

    def _distance_to_relevance(self, distance: float) -> float:
        score = 1.0 - (float(distance) / math.sqrt(2.0))
        if score < 0.0:
            return 0.0
        if score > 1.0:
            return 1.0
        return score

    def similarity_search_with_relevance_scores(self, query: str, k: int = 4,
                                                score_threshold: float = 0.0,
                                                metadata_filter=None, fetch_k: int = 20):
        if self._faiss_index is None or self._faiss_index.ntotal == 0:
            return []
        query_vec = self._query_embedding(query)
        top_k = max(1, min(int(fetch_k if metadata_filter is not None else k), max(k, fetch_k, 1)))
        distances, indices = self._faiss_index.search(np.ascontiguousarray(query_vec.reshape(1, -1)), top_k)
        chunk_ids: List[int] = []
        for pos in indices[0]:
            pos_i = int(pos)
            if pos_i < 0 or pos_i >= len(self._chunk_ids_by_pos):
                continue
            chunk_ids.append(self._chunk_ids_by_pos[pos_i])
        docs_map = self._fetch_documents_by_chunk_ids(chunk_ids)
        results = []
        for raw_distance, pos in zip(distances[0], indices[0]):
            pos_i = int(pos)
            if pos_i < 0 or pos_i >= len(self._chunk_ids_by_pos):
                continue
            chunk_id = self._chunk_ids_by_pos[pos_i]
            doc = docs_map.get(chunk_id)
            if doc is None:
                continue
            if metadata_filter is not None:
                metadata = getattr(doc, "metadata", {})
                if callable(metadata_filter):
                    if not metadata_filter(metadata):
                        continue
                elif isinstance(metadata_filter, dict):
                    matched = True
                    for key, expected in metadata_filter.items():
                        if metadata.get(key) != expected:
                            matched = False
                            break
                    if not matched:
                        continue
            score = self._distance_to_relevance(float(raw_distance))
            if score < float(score_threshold):
                continue
            results.append((doc, score))
            if len(results) >= int(k):
                break
        return results

    def _import_document(self, id_, name, text, signals=None):
        if self._is_closing:
            return
        self._ensure_embedding_function()
        self._set_project_paths()
        conn = self._connect_search_db()
        try:
            self._ensure_search_schema(conn)
            self._set_meta_build_state(conn, "building")
            self._index_source(conn, int(id_), str(name), "" if text is None else str(text), signals=signals)
            self._rebuild_faiss_index_from_db(conn)
            self._set_meta_build_state(conn, "ready")
        finally:
            conn.close()
        self.reading_doc = ''

    def import_document(self, id_, name, text):
        worker = Worker(self._import_document, id_, name, text)
        worker.signals.finished.connect(self.finished_import)
        worker.signals.progress.connect(self.progress_import)
        worker.signals.error.connect(ai_exception_handler)
        self.import_workers_count += 1
        self.vectorstore_workers_count += 1
        self.threadpool.start(worker)

    def _update_vectorstore(self, signals=None):
        self.app.ai._status = ''
        self._ensure_embedding_function()
        self._set_project_paths()
        conn = self._connect_search_db()
        try:
            self._ensure_search_schema(conn)
            self._set_meta_build_state(conn, "building")
            self._refresh_sources(conn)
            self._rebuild_faiss_index_from_db(conn)
            self._set_meta_build_state(conn, "ready")
        finally:
            conn.close()

    def update_vectorstore(self):
        worker = Worker(self._update_vectorstore)
        self.vectorstore_workers_count += 1
        worker.signals.finished.connect(self._finish_vectorstore_worker)
        worker.signals.error.connect(ai_exception_handler)
        self.threadpool.start(worker)

    def rebuild_vectorstore(self):
        self.app.ai._status = ''
        self._ensure_embedding_function()
        self._set_project_paths()
        conn = self._connect_search_db()
        try:
            self._ensure_search_schema(conn)
            self._set_meta_build_state(conn, "building")
            self._reset_search_store(conn)
            self._refresh_sources(conn)
            self._rebuild_faiss_index_from_db(conn)
            self._set_meta_build_state(conn, "ready")
        finally:
            conn.close()

    def delete_document(self, id_):
        self._ensure_embedding_function()
        self._set_project_paths()
        conn = self._connect_search_db()
        try:
            self._ensure_search_schema(conn)
            self._set_meta_build_state(conn, "building")
            self._delete_source_rows(conn, int(id_))
            self._rebuild_faiss_index_from_db(conn)
            self._set_meta_build_state(conn, "ready")
        finally:
            conn.close()

    def close(self):
        self._is_closing = True
        self.download_model_cancel = True
        self.threadpool.clear()
        self.threadpool.waitForDone(5000)
        self.import_workers_count = 0
        self.vectorstore_workers_count = 0
        self._faiss_index = None
        self._chunk_ids_by_pos = []
        self.faiss_db = None
        self._is_closing = False

    def ai_worker_running(self):
        return self.vectorstore_workers_count

    def is_open(self) -> bool:
        return self.faiss_db is not None and self._is_closing is False

    def is_ready(self) -> bool:
        return self.is_open() and not self.ai_worker_running()
