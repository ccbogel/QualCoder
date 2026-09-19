import subprocess
import sys
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from qualcoder.ai_runtime import (
    AI_DISABLED,
    AI_FAILED,
    AI_INITIALIZING,
    AI_LOADING,
    AI_READY,
    AI_UNLOADED,
    VECTORSTORE_LOADING,
    ai_runtime_ready,
    ensure_ai_ready,
    show_ai_runtime_not_ready,
    vectorstore_required,
)
from qualcoder.ai_llm import AiLLM
from qualcoder.app import App
from qualcoder.__main__ import MainWindow


class TestAiRuntime(TestCase):
    """Tests for the non-blocking AI startup boundary."""

    def test_ready_state(self):
        self.assertTrue(ai_runtime_ready(SimpleNamespace(ai_runtime_state=AI_READY)))
        self.assertFalse(ai_runtime_ready(SimpleNamespace(ai_runtime_state=AI_LOADING)))

    def test_app_status_covers_runtime_and_operational_state(self):
        app = App.__new__(App)
        app.ai_runtime_state = AI_UNLOADED
        app.ai = None
        self.assertEqual(AI_UNLOADED, app.get_ai_status())

        app.ai_runtime_state = AI_LOADING
        self.assertEqual(AI_LOADING, app.get_ai_status())

        app.ai_runtime_state = AI_READY
        self.assertEqual(AI_INITIALIZING, app.get_ai_status())

        app.ai = SimpleNamespace(get_status=lambda: "busy")
        self.assertEqual("busy", app.get_ai_status())

        app.ai = SimpleNamespace(get_status=lambda: AI_READY)
        self.assertEqual(AI_READY, app.get_ai_status())

    def test_llm_startup_clears_starting_state_while_index_opens(self):
        app = SimpleNamespace(
            settings={"ai_enable": "True", "ai_model_index": 0},
            ai_models=[{
                "large_model": "test-large",
                "large_model_context_window": 4096,
                "fast_model": "test-fast",
                "fast_model_context_window": 4096,
                "api_base": "http://localhost",
                "api_key": "test-key",
            }],
        )
        store = SimpleNamespace(
            is_open=MagicMock(return_value=False),
            ai_worker_running=MagicMock(return_value=False),
            init_vectorstore=MagicMock(),
        )
        service = object.__new__(AiLLM)
        service.app = app
        service.parent_text_edit = SimpleNamespace(append=MagicMock())
        service.sources_vectorstore = store
        service._migrate_legacy_prompts_for_current_scope = MagicMock()

        with patch("qualcoder.ai_llm.QtWidgets.QApplication.processEvents"):
            service.init_llm(SimpleNamespace())

        store.init_vectorstore.assert_called_once_with(False)
        self.assertEqual("", service._status)
        store.ai_worker_running.return_value = True
        self.assertEqual("reading data", service.get_status())

        store.init_vectorstore.reset_mock()
        with patch("qualcoder.ai_llm.QtWidgets.QApplication.processEvents"):
            service.init_llm(SimpleNamespace())

        store.init_vectorstore.assert_not_called()
        self.assertEqual("", service._status)

    def test_operational_guard_uses_combined_status(self):
        app = App.__new__(App)
        app.ai_runtime_state = AI_LOADING
        app.ai = None
        with patch("qualcoder.ai_runtime.Message") as message_class:
            self.assertFalse(ensure_ai_ready(app, "AI Search"))
        self.assertIn("retry", message_class.call_args.args[2].lower())

    def test_loading_message_asks_user_to_retry(self):
        app = SimpleNamespace(ai_runtime_state=AI_LOADING)
        with patch("qualcoder.ai_runtime.Message") as message_class:
            show_ai_runtime_not_ready(app, "AI Agent")
        self.assertIn("retry", message_class.call_args.args[2].lower())
        message_class.return_value.exec.assert_called_once_with()

    def test_new_chat_without_project_asks_to_open_one(self):
        app = SimpleNamespace(
            project_path="",
            get_ai_status=lambda: "no data",
        )

        with patch("qualcoder.ai_runtime.Message") as message_class:
            self.assertFalse(ensure_ai_ready(app, "AI Agent"))

        message = message_class.call_args.args[2]
        self.assertIn("Open or create a project", message)
        self.assertNotIn("preparing the project data", message)

    def test_new_chat_without_project_rejects_even_ready_ai(self):
        app = SimpleNamespace(
            project_path="",
            get_ai_status=lambda: AI_READY,
        )

        with patch("qualcoder.ai_runtime.Message") as message_class:
            self.assertFalse(ensure_ai_ready(app, "AI Agent"))

        self.assertIn("Open or create a project", message_class.call_args.args[2])

    def test_open_project_without_search_index_reports_index_status(self):
        app = SimpleNamespace(
            project_path="project.qda",
            get_ai_status=lambda: "no data",
        )

        with patch("qualcoder.ai_runtime.Message") as message_class:
            self.assertFalse(ensure_ai_ready(app, "AI Agent"))

        message = message_class.call_args.args[2]
        self.assertIn("search index", message)
        self.assertNotIn("Open or create a project", message)

    def test_failure_message_does_not_claim_loading(self):
        app = SimpleNamespace(ai_runtime_state=AI_FAILED)
        with patch("qualcoder.ai_runtime.Message") as message_class:
            show_ai_runtime_not_ready(app, "AI Agent")
        self.assertIn("could not be loaded", message_class.call_args.args[2].lower())

    def test_disabled_message_does_not_claim_loading(self):
        app = SimpleNamespace(ai_runtime_state=AI_DISABLED)
        with patch("qualcoder.ai_runtime.Message") as message_class:
            show_ai_runtime_not_ready(app, "AI Agent")
        self.assertIn("disabled", message_class.call_args.args[2].lower())

    def test_disabled_ai_skips_background_runtime_loading(self):
        app = SimpleNamespace(
            ai_runtime_state=AI_UNLOADED,
            settings={'ai_enable': 'False'},
        )
        window = SimpleNamespace(app=app, ai_import_thread=None)

        MainWindow.start_ai_background_loading(window)

        self.assertEqual(AI_DISABLED, app.ai_runtime_state)
        self.assertIsNone(window.ai_import_thread)

    def test_external_mcp_starts_vectorstore_only_loader(self):
        app = SimpleNamespace(
            settings={
                'ai_enable': 'False',
                'mcp_external_enabled': 'True',
            },
            vectorstore=None,
            vectorstore_runtime_state='unloaded',
            vectorstore_runtime_error='',
        )
        import_thread = MagicMock()
        import_thread.isRunning.return_value = False
        window = SimpleNamespace(
            app=app,
            vectorstore_import_thread=None,
            ui=SimpleNamespace(textEdit=SimpleNamespace(append=MagicMock())),
            _finish_vectorstore_runtime_initialization=MagicMock(),
            _vectorstore_runtime_loading_failed=MagicMock(),
        )

        with patch(
                'qualcoder.__main__.VectorstoreImportThread',
                return_value=import_thread,
        ) as thread_class:
            MainWindow.start_vectorstore_background_loading(window)

        thread_class.assert_called_once_with(window)
        self.assertEqual(VECTORSTORE_LOADING, app.vectorstore_runtime_state)
        import_thread.start.assert_called_once()

    def test_vectorstore_is_required_by_ai_or_external_mcp(self):
        app = SimpleNamespace(
            settings={"ai_enable": "False", "mcp_external_enabled": "False"}
        )
        self.assertFalse(vectorstore_required(app))

        app.settings["ai_enable"] = "True"
        self.assertTrue(vectorstore_required(app))

        app.settings["ai_enable"] = "False"
        app.settings["mcp_external_enabled"] = "True"
        self.assertTrue(vectorstore_required(app))

    def test_vectorstore_import_does_not_load_llm_provider_stack(self):
        code = (
            "import sys; import qualcoder.ai_vectorstore; "
            "assert 'qualcoder.ai_llm' not in sys.modules; "
            "assert 'langchain_openai' not in sys.modules; "
            "assert 'openai' not in sys.modules"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)

    def test_lightweight_ai_llm_import_excludes_model_stack(self):
        code = (
            "import sys; import qualcoder.ai_llm; "
            "assert 'torch' not in sys.modules; "
            "assert 'sentence_transformers' not in sys.modules; "
            "assert 'langchain_openai' not in sys.modules"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
