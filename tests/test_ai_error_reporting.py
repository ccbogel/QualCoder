from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from qualcoder.ai_chat import DialogAIChat
from qualcoder.ai_llm import AICancelled, AiLLM


class TestAiErrorReporting(TestCase):
    """Preserve transport causes when providers wrap connection errors."""

    def setUp(self):
        self.ai = AiLLM.__new__(AiLLM)

    def _connection_error(self) -> RuntimeError:
        try:
            try:
                raise OSError('certificate verify failed')
            except OSError as cause:
                raise RuntimeError('Connection error.') from cause
        except RuntimeError as error:
            return error

    def test_dialog_and_traceback_include_transport_cause(self):
        error = self._connection_error()
        with patch('qualcoder.ai_llm.qt_exception_hook') as hook, \
                patch.object(self.ai, '_chatgpt_oauth_user_error', return_value=''), \
                patch('qualcoder.ai_llm.logger'), \
                patch('qualcoder.ai_llm._', side_effect=lambda text: text, create=True):
            self.ai._handle_run_error(type(error), error, error.__traceback__)

        message, details = hook._exception_caught.emit.call_args.args
        self.assertIn('RuntimeError: Connection error.', message)
        self.assertIn('OSError: certificate verify failed', message)
        self.assertIn('OSError: certificate verify failed', details)
        self.assertIn('raise OSError', details)

    def test_ai_log_includes_transport_cause(self):
        self.ai._write_ai_log = MagicMock()
        self.ai._llm_name_for_log = MagicMock(return_value='test-model')
        self.ai.log_llm_error(7, object(), self._connection_error(), 'metadata')
        logged = self.ai._write_ai_log.call_args.args[0]
        self.assertIn('[#7] ERROR model="test-model" context="metadata"', logged)
        self.assertIn('RuntimeError: Connection error.', logged)
        self.assertIn('OSError: certificate verify failed', logged)

    def test_normal_chat_includes_cause_and_preserves_partial_response(self):
        error = self._connection_error()
        self.ai.get_streaming_output = MagicMock(return_value='Partial answer')
        self.ai.clear_streaming_output = MagicMock()
        self.ai._is_stream_interruption_exception = MagicMock(return_value=True)
        dialog = SimpleNamespace(
            app=SimpleNamespace(ai=self.ai),
            current_streaming_run_id='test-run',
            current_streaming_chat_idx=0,
            _cancel_pending_stream_render=MagicMock(),
            _normalize_ai_profile_author=MagicMock(return_value='test-model'),
            process_message=MagicMock(),
            _clear_chat_ai_profile_snapshot=MagicMock(),
        )
        with patch('qualcoder.ai_chat._', side_effect=lambda text: text, create=True), \
                patch('qualcoder.ai_chat.logger') as chat_logger, \
                patch('qualcoder.ai_chat.qt_exception_hook') as hook:
            DialogAIChat.ai_error_callback(dialog, type(error), error, error.__traceback__)

        dialog.process_message.assert_any_call('ai', 'Partial answer', 0)
        message = dialog.process_message.call_args.args[1]
        self.assertIn('RuntimeError: Connection error.', message)
        self.assertIn('OSError: certificate verify failed', message)
        self.assertIn('raise OSError', chat_logger.error.call_args.args[0])
        hook._exception_caught.emit.assert_not_called()
        dialog._clear_chat_ai_profile_snapshot.assert_called_once_with(0)

    def test_suppressed_context_is_not_displayed(self):
        error = RuntimeError('Public error')
        error.__context__ = ValueError('Hidden context')
        error.__suppress_context__ = True
        self.assertEqual('RuntimeError: Public error', self.ai._exception_summary(error))

    def test_agent_planning_error_reaches_chat_with_underlying_cause(self):
        error = RuntimeError('Connection error.')
        error.__cause__ = ValueError(
            "Request URL is missing an 'http://' or 'https://' protocol."
        )
        dialog = MagicMock()
        dialog.app.ai = self.ai
        self.ai.is_current_run_canceled = MagicMock(return_value=False)
        self.ai.start_stream = MagicMock()
        dialog._begin_ai_change_set.return_value = ''
        dialog._mcp_base_system_prompt.return_value = ''
        dialog._build_mcp_combined_system_prompt.return_value = 'Plan the next step.'
        dialog._run_mcp_request.return_value = ({}, {'result': {}})
        dialog._compact_mcp_result_content.return_value = '{}'
        dialog._invoke_json_llm_with_step_timeout.side_effect = error
        dialog.current_streaming_chat_idx = 0
        dialog.chat_list = [('test-chat',)]

        with patch('qualcoder.ai_chat._', side_effect=lambda text: text, create=True), \
                patch('qualcoder.ai_chat.AIMessage', SimpleNamespace), \
                patch('qualcoder.ai_chat.HumanMessage', SimpleNamespace):
            result = DialogAIChat._mcp_general_chat_worker(dialog, [], 0)
            DialogAIChat.ai_mcp_message_callback(dialog, result)

        dialog._invoke_json_llm_with_step_timeout.assert_called_once()
        message_type, message, chat_idx = dialog.process_message.call_args.args
        self.assertEqual(('info', 0), (message_type, chat_idx))
        self.assertIn('RuntimeError: Connection error.', message)
        self.assertIn("Request URL is missing an 'http://' or 'https://' protocol.", message)
        self.ai.start_stream.assert_not_called()

    def test_implicit_context_and_cycles(self):
        error = RuntimeError('Outer error')
        cause = OSError('Transport error')
        error.__context__ = cause
        cause.__cause__ = error
        self.assertEqual(
            'RuntimeError: Outer error\nOSError: Transport error',
            self.ai._exception_summary(error),
        )

    def test_cancellation_does_not_show_error_dialog(self):
        with patch('qualcoder.ai_llm.qt_exception_hook') as hook:
            self.ai._handle_run_error(AICancelled, AICancelled('test-run'), None)
        hook._exception_caught.emit.assert_not_called()
