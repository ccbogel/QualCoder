import sqlite3
import threading
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import httpx

from qualcoder.ai_llm import AiLLM


class _Chunk:
    def __init__(self, content):
        self.content = content


class _StreamLLM:
    def __init__(self, err):
        self.err = err

    def stream(self, messages):
        yield _Chunk("partial")
        raise self.err


class _FakeListView:
    def setStyleSheet(self, value):
        pass

    def setSelectionMode(self, value):
        pass

    def clearSelection(self):
        pass

    def setCurrentIndex(self, value):
        pass


class _FakeSelectDialog:
    def __init__(self, app, options, title, selection_mode):
        self.options = options
        self.ui = SimpleNamespace(listView=_FakeListView())

    def exec(self):
        return True

    def get_selected(self):
        return [self.options[0]]


class _FakeConfirmDialog:
    def __init__(self, app, text, title):
        self.text = text
        self.title = title

    def exec(self):
        return True


class _FakeMessage:
    calls = []

    def __init__(self, app, title, text, icon=None):
        self.title = title
        self.text = text
        self.icon = icon
        _FakeMessage.calls.append(self)

    def exec(self):
        return True


class TestAiLLMStreamErrors(TestCase):

    def setUp(self):
        self.ai = AiLLM.__new__(AiLLM)
        self.ai._runs_lock = threading.RLock()
        self.ai._runs_by_id = {}
        self.ai._last_streaming_output_by_run = {}
        self.ai._set_current_run_context = lambda run_context: None
        self.ai._clear_current_run_context = lambda: None
        self.ai.log_llm_request = lambda llm, messages, context='': 1
        self.ai.log_llm_error = lambda req_id, llm, err, context='': None
        self.ai.log_llm_response = lambda req_id, llm, response_text, context='': None
        self.ai._safe_to_text = lambda value: str(value)
        self.ai._finalize_run_context = lambda run_context, terminal_status='': None

        def update_run_status(run_id, status, error_text=''):
            self.run_statuses.append((status, error_text))
            self.run_context.status = status
            if error_text != '':
                self.run_context.error_text = error_text

        self.run_statuses = []
        self.ai._update_run_status = update_run_status

    def make_run_context(self, err):
        self.run_context = SimpleNamespace(
            run_id="run-1",
            llm=_StreamLLM(err),
            cancel_event=threading.Event(),
            stream_iter=None,
            streaming_output="",
            error_text="",
            status="queued",
        )
        self.ai._runs_by_id[self.run_context.run_id] = self.run_context
        return self.run_context

    def test_timeout_errors_do_not_allow_partial_stream_result(self):
        self.assertFalse(
            self.ai._allow_partial_stream_result_after_error(httpx.ReadTimeout("stream timed out"))
        )
        self.assertFalse(
            self.ai._allow_partial_stream_result_after_error(TimeoutError("stream timed out"))
        )

    def test_transport_errors_do_not_allow_partial_stream_result(self):
        self.assertFalse(
            self.ai._allow_partial_stream_result_after_error(httpx.ReadError("stream disconnected"))
        )
        self.assertFalse(
            self.ai._allow_partial_stream_result_after_error(httpx.ConnectError("network unreachable"))
        )

    def test_wrapped_transport_errors_do_not_allow_partial_stream_result(self):
        try:
            try:
                raise httpx.ReadError("stream disconnected")
            except httpx.ReadError as err:
                raise RuntimeError("provider connection failed") from err
        except RuntimeError as err:
            self.assertFalse(self.ai._allow_partial_stream_result_after_error(err))

    def test_wrapped_timeout_errors_do_not_allow_partial_stream_result(self):
        try:
            try:
                raise httpx.ReadTimeout("stream timed out")
            except httpx.ReadTimeout as err:
                raise RuntimeError("provider stream failed") from err
        except RuntimeError as err:
            self.assertFalse(self.ai._allow_partial_stream_result_after_error(err))

    def test_non_timeout_errors_still_allow_partial_stream_result(self):
        self.assertTrue(
            self.ai._allow_partial_stream_result_after_error(ValueError("malformed trailing event"))
        )

    def test_stream_timeout_with_partial_output_raises_error(self):
        run_context = self.make_run_context(httpx.ReadTimeout("stream timed out"))

        with self.assertRaises(httpx.ReadTimeout):
            self.ai._run_stream_worker(None, run_context, [])

        self.assertIn(("errored", "stream timed out"), self.run_statuses)

    def test_stream_transport_error_with_partial_output_raises_error(self):
        run_context = self.make_run_context(httpx.ReadError("stream disconnected"))

        with self.assertRaises(httpx.ReadError):
            self.ai._run_stream_worker(None, run_context, [])

        self.assertIn(("errored", "stream disconnected"), self.run_statuses)

    def test_non_timeout_stream_error_with_partial_output_returns_partial(self):
        run_context = self.make_run_context(ValueError("malformed trailing event"))

        result = self.ai._run_stream_worker(None, run_context, [])

        self.assertEqual("partial", result)
        self.assertIn(("errored", "malformed trailing event"), self.run_statuses)

    def test_finalized_run_keeps_stream_snapshot_until_cleared(self):
        run_context = SimpleNamespace(
            run_id="run-2",
            cancel_event=threading.Event(),
            stream_iter=None,
            http_client=None,
            streaming_output="partial",
            status="errored",
            finished_at=0.0,
            scope_type="",
            scope_id=None,
        )
        self.ai._runs_by_id[run_context.run_id] = run_context

        AiLLM._finalize_run_context(self.ai, run_context, "errored")

        self.assertEqual("partial", self.ai.get_streaming_output("run-2"))
        self.ai.clear_streaming_output("run-2")
        self.assertEqual("", self.ai.get_streaming_output("run-2"))


class TestAiLLMUndoHistory(TestCase):

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        cur = self.conn.cursor()
        cur.execute("CREATE TABLE cases (caseid INTEGER PRIMARY KEY, name TEXT, memo TEXT, owner TEXT)")
        cur.execute(
            "CREATE TABLE attribute_type (name TEXT PRIMARY KEY, date TEXT, owner TEXT, memo TEXT, caseOrFile TEXT, valuetype TEXT)"
        )
        cur.execute(
            "CREATE TABLE attribute (attrid INTEGER PRIMARY KEY, name TEXT, attr_type TEXT, value TEXT, id INTEGER, owner TEXT, date TEXT)"
        )
        self.conn.commit()

        self.app = SimpleNamespace(
            conn=self.conn,
            delete_backup=True,
            project_events=None,
        )
        self.ai = AiLLM.__new__(AiLLM)
        self.ai.app = self.app
        self.ai.parent_text_edit = None
        self.ai.ai_change_history = []
        self.ai._ai_change_list_stylesheet = lambda list_view: ""

        _FakeMessage.calls = []

    def tearDown(self):
        self.conn.close()

    def _insert_blocked_attribute_state(self):
        cur = self.conn.cursor()
        cur.execute("INSERT INTO cases (caseid, name, memo, owner) VALUES (1, 'Case A', '', 'AI Agent')")
        cur.execute(
            "INSERT INTO attribute_type (name, date, owner, memo, caseOrFile, valuetype) VALUES (?, '', 'AI Agent', '', 'case', 'character')",
            ("Age",),
        )
        cur.execute(
            "INSERT INTO attribute (attrid, name, attr_type, value, id, owner, date) VALUES (1, 'Age', 'case', '23', 1, 'AI Agent', '')"
        )
        self.conn.commit()

    def _set_change_history(self):
        self.ai.ai_change_history = [{
            "id": "set-1",
            "name": "[12:00:00]",
            "created_at": "2026-06-04 12:00:00",
            "operations": [
                {"type": "create_case", "caseid": 1, "name": "Case A"},
                {"type": "create_case_attribute", "name": "Age", "target_type": "case", "value_type": "character"},
            ],
        }]

    def _run_undo_dialog(self):
        with patch("qualcoder.ai_llm.DialogSelectItems", _FakeSelectDialog), \
                patch("qualcoder.ai_llm.DialogConfirmDelete", _FakeConfirmDialog), \
                patch("qualcoder.ai_llm.Message", _FakeMessage):
            self.ai.undo_ai_agent_changes()

    def test_undo_keeps_blocked_operations_for_retry(self):
        self._insert_blocked_attribute_state()
        self._set_change_history()

        self._run_undo_dialog()

        self.assertEqual(0, self.conn.execute("SELECT COUNT(*) FROM cases").fetchone()[0])
        self.assertEqual(1, len(self.ai.ai_change_history))
        remaining_ops = self.ai.ai_change_history[0]["operations"]
        self.assertEqual(["create_case_attribute"], [op["type"] for op in remaining_ops])

        last_message = _FakeMessage.calls[-1].text
        self.assertIn("Blocked operations kept for retry: 1", last_message)
        self.assertIn("Created case attribute: Age", last_message)
        self.assertIn("dependent data", last_message)
        self.assertIn("remains in the list", last_message)

    def test_undo_removes_change_set_after_retry_succeeds(self):
        self._insert_blocked_attribute_state()
        self._set_change_history()

        self._run_undo_dialog()
        self.conn.execute("DELETE FROM attribute WHERE name='Age' AND attr_type='case'")
        self.conn.commit()

        self._run_undo_dialog()

        self.assertEqual(0, len(self.ai.ai_change_history))
        self.assertEqual(0, self.conn.execute("SELECT COUNT(*) FROM attribute_type").fetchone()[0])

    def test_change_set_tooltip_lists_more_actions_than_preview(self):
        change_set = {
            "id": "set-2",
            "created_at": "2026-06-04 12:00:00",
            "operations": [
                {"type": "create_code", "name": f"Code {i}"}
                for i in range(1, 26)
            ],
        }

        self.ai._refresh_ai_change_set_name(change_set)

        self.assertIn("Created code: Code 1", change_set["name"])
        self.assertIn("Created code: Code 4", change_set["name"])
        self.assertIn("Additional actions: 21", change_set["name"])
        self.assertNotIn("Created code: Code 5", change_set["name"])

        self.assertIn("Created code: Code 20", change_set["tooltip"])
        self.assertNotIn("Created code: Code 21", change_set["tooltip"])
        self.assertIn("Additional actions: 5", change_set["tooltip"])
