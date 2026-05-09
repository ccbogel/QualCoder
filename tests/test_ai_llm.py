import httpx
import threading
from types import SimpleNamespace
from unittest import TestCase

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


class TestAiLLMStreamErrors(TestCase):

    def setUp(self):
        self.ai = AiLLM.__new__(AiLLM)
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
            error_text="",
            status="queued",
        )
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
