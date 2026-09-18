import threading
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from qualcoder import ai_llm
from qualcoder.ai_vectorstore import AiVectorstore
from qualcoder.vectorstore_runtime import VECTORSTORE_INDEXING


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
