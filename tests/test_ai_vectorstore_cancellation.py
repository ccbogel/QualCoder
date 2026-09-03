import sqlite3
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase

import numpy as np
from PyQt6 import QtCore

from qualcoder.ai_vectorstore import AiVectorstore, SearchChunkDocument


class BlockingEmbeddings:
    """Embedding stub that lets a test cancel work during the first batch."""

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.batches = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.batches.append(list(texts))
        self.started.set()
        if not self.release.wait(3.0):
            raise TimeoutError("Test did not release the embedding batch")
        return [[1.0, 0.0, 0.0] for _text in texts]


class TestVectorstoreCancellation(TestCase):
    """Regression tests for source deletion and application shutdown."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.qt_app = QtCore.QCoreApplication.instance()
        if cls.qt_app is None:
            cls.qt_app = QtCore.QCoreApplication([])

    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        project_path = Path(self.temp_dir.name)
        self.project_db_path = project_path / "data.qda"
        conn = sqlite3.connect(self.project_db_path)
        conn.execute("CREATE TABLE source (id INTEGER PRIMARY KEY, name TEXT, fulltext TEXT)")
        conn.execute(
            "INSERT INTO source(id, name, fulltext) VALUES (1, 'source.txt', 'project text')"
        )
        conn.commit()
        conn.close()

        self.embeddings = BlockingEmbeddings()
        self.messages = []
        ai_service = SimpleNamespace(_status='')
        self.app = SimpleNamespace(
            project_path=str(project_path),
            project_name="test.qda",
            settings={'ai_enable': 'True'},
            ai_embedding_function=self.embeddings,
            ai=ai_service,
        )
        self.store = AiVectorstore(
            self.app,
            SimpleNamespace(append=self.messages.append),
            "documents",
        )
        self.store.embedding_batch_size = 1
        self.store._split_source_text = self._split_source_text

    def tearDown(self) -> None:
        self.embeddings.release.set()
        self.store.close()
        self.temp_dir.cleanup()

    @staticmethod
    def _split_source_text(_source_id: int, _source_name: str,
                           _text: str) -> list[SearchChunkDocument]:
        documents = []
        for index, text in enumerate(("first", "second", "third")):
            documents.append(
                SearchChunkDocument(
                    page_content=text,
                    metadata={
                        "chunk_index": index,
                        "start_index": index * 10,
                        "text_hash": text,
                        "hash_ordinal": 0,
                    },
                    id="",
                )
            )
        return documents

    def _delete_project_source(self) -> None:
        conn = sqlite3.connect(self.project_db_path)
        conn.execute("DELETE FROM source WHERE id=1")
        conn.commit()
        conn.close()

    def _seed_indexed_source(self) -> None:
        self.store._set_project_paths()
        conn = self.store._connect_search_db()
        try:
            self.store._ensure_search_schema(conn)
            conn.execute(
                "INSERT INTO search_source_state "
                "(source_id, source_name, text_hash, text_len, last_indexed_at) "
                "VALUES (1, 'old.txt', 'old-hash', 3, 'now')"
            )
            cursor = conn.execute(
                "INSERT INTO search_chunks "
                "(source_id, source_name, chunk_index, start_index, length, text, text_hash, hash_ordinal) "
                "VALUES (1, 'old.txt', 0, 0, 3, 'old', 'old-hash', 0)"
            )
            chunk_id = int(cursor.lastrowid)
            conn.execute(
                "INSERT INTO search_embeddings(chunk_id, dim, vector_blob) VALUES (?, ?, ?)",
                (
                    chunk_id,
                    3,
                    self.store._vector_to_blob(np.asarray([1.0, 0.0, 0.0], dtype=np.float32)),
                ),
            )
            conn.execute(
                "INSERT INTO search_chunk_fts "
                "(chunk_id, source_id, source_name, start_index, length, text) "
                "VALUES (?, 1, 'old.txt', 0, 3, 'old')",
                (chunk_id,),
            )
            conn.commit()
        finally:
            conn.close()

    def _indexed_row_counts(self) -> tuple[int, int, int, int]:
        conn = sqlite3.connect(Path(self.temp_dir.name) / "ai_data" / "search.sqlite")
        try:
            return (
                conn.execute("SELECT count(*) FROM search_source_state").fetchone()[0],
                conn.execute("SELECT count(*) FROM search_chunks").fetchone()[0],
                conn.execute("SELECT count(*) FROM search_embeddings").fetchone()[0],
                conn.execute("SELECT count(*) FROM search_chunk_fts").fetchone()[0],
            )
        finally:
            conn.close()

    def test_deleting_source_cancels_embedding_and_removes_all_rows(self):
        self._seed_indexed_source()
        self.assertEqual((1, 1, 1, 1), self._indexed_row_counts())
        self.store.import_document(1, "source.txt", "project text")
        self.assertTrue(self.embeddings.started.wait(2.0))

        self._delete_project_source()
        self.store.delete_document(1)
        self.embeddings.release.set()

        self.assertTrue(self.store.threadpool.waitForDone(3000))
        self.assertEqual([["first"]], self.embeddings.batches)
        self.assertEqual((0, 0, 0, 0), self._indexed_row_counts())

    def test_close_cancels_remaining_embedding_batches(self):
        self.store.import_document(1, "source.txt", "project text")
        self.assertTrue(self.embeddings.started.wait(2.0))
        old_generation = self.store._worker_generation_snapshot()
        release_timer = threading.Timer(0.05, self.embeddings.release.set)
        release_timer.start()

        started_at = time.monotonic()
        self.store.close()
        release_timer.join()

        self.assertLess(time.monotonic() - started_at, 2.0)
        self.assertEqual(0, self.store.threadpool.activeThreadCount())
        self.assertEqual([["first"]], self.embeddings.batches)
        self.assertTrue(self.store.cancelled(old_generation))
        self.assertEqual((0, 0, 0, 0), self._indexed_row_counts())

    def test_unchanged_source_is_committed_after_all_batches(self):
        self.embeddings.release.set()

        self.store.import_document(1, "source.txt", "project text")

        self.assertTrue(self.store.threadpool.waitForDone(3000))
        self.assertEqual([["first"], ["second"], ["third"]], self.embeddings.batches)
        self.assertEqual((1, 3, 3, 3), self._indexed_row_counts())
