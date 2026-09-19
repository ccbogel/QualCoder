import threading
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from qualcoder import ai_llm
from qualcoder.app import App
from qualcoder.ai_runtime import VECTORSTORE_INDEXING
from qualcoder.ai_vectorstore import AiVectorstore, SearchChunkDocument


class TestVectorstoreOwnership(TestCase):
    """The application owns one vectorstore shared by its consumers."""

    def test_ai_llm_stores_new_vectorstore_on_application(self):
        vectorstore = SimpleNamespace()
        app = SimpleNamespace(vectorstore=None)
        text_edit = SimpleNamespace(append=MagicMock())

        with patch.object(ai_llm, "load_ai_runtime_dependencies"), \
                patch.object(ai_llm, "AiVectorstore", return_value=vectorstore) as constructor:
            service = ai_llm.AiLLM(app, text_edit)

        constructor.assert_called_once_with(app, text_edit, service.sources_collection)
        self.assertIs(vectorstore, app.vectorstore)
        self.assertIs(vectorstore, service.sources_vectorstore)

    def test_ai_llm_reuses_application_vectorstore(self):
        vectorstore = SimpleNamespace(close=MagicMock())
        app = SimpleNamespace(vectorstore=vectorstore)
        text_edit = SimpleNamespace(append=MagicMock())

        with patch.object(ai_llm, "load_ai_runtime_dependencies"):
            service = ai_llm.AiLLM(app, text_edit)

        self.assertIs(vectorstore, service.sources_vectorstore)
        service.close()
        vectorstore.close.assert_not_called()

    def test_vectorstore_initialization_does_not_require_enabled_ai(self):
        store = object.__new__(AiVectorstore)
        store.app = SimpleNamespace(
            project_name="project.qda",
            settings={"ai_enable": "False"},
        )
        store._state_lock = threading.Lock()
        store._is_closing = False
        store.prepare_embedding_model = MagicMock(return_value=True)
        store.open_db = MagicMock()

        started = store.init_vectorstore(rebuild=True)

        self.assertTrue(started)
        self.assertEqual(VECTORSTORE_INDEXING, store.app.vectorstore_runtime_state)
        store.open_db.assert_called_once_with(True)

    def test_mcp_only_document_changes_use_shared_vectorstore(self):
        app = object.__new__(App)
        app.settings = {
            "ai_enable": "False",
            "mcp_external_enabled": "True",
        }
        app.ai = None
        app.vectorstore = MagicMock()

        app.vectorstore_import_document(7, "Interview", "Updated text")
        app.vectorstore_update()
        app.vectorstore_delete_document(7)

        app.vectorstore.import_document.assert_called_once_with(
            7, "Interview", "Updated text"
        )
        app.vectorstore.update_vectorstore.assert_called_once_with()
        app.vectorstore.delete_document.assert_called_once_with(7)

    def test_document_changes_skip_vectorstore_without_a_consumer(self):
        app = object.__new__(App)
        app.settings = {
            "ai_enable": "False",
            "mcp_external_enabled": "False",
        }
        app.vectorstore = MagicMock()

        app.vectorstore_import_document(7, "Interview", "Updated text")
        app.vectorstore_update()
        app.vectorstore_delete_document(7)

        app.vectorstore.import_document.assert_not_called()
        app.vectorstore.update_vectorstore.assert_not_called()
        app.vectorstore.delete_document.assert_not_called()

    def test_shared_vectorstore_performs_ranked_retrieval(self):
        first = SearchChunkDocument(
            page_content="first",
            metadata={"id": 1, "start_index": 0},
            id="first",
        )
        second = SearchChunkDocument(
            page_content="second",
            metadata={"id": 2, "start_index": 10},
            id="second",
        )
        store = object.__new__(AiVectorstore)
        store.faiss_db = SimpleNamespace(
            similarity_search_with_relevance_scores=MagicMock(
                side_effect=[
                    [(first, 0.8), (second, 0.7)],
                    [(first, 0.6)],
                ]
            )
        )

        result = store.retrieve_similar_documents(["query one", "query two"])

        self.assertEqual([first, second], result)
        self.assertAlmostEqual(3.4, first.metadata["score"])
        self.assertAlmostEqual(1.7, second.metadata["score"])
