import json
from types import MethodType
from unittest import TestCase
from unittest.mock import MagicMock, patch

from qualcoder.ai_chat import DialogAIChat


class TestAiAgentCallLimits(TestCase):
    """Exercise bulk case linking and the remaining execution limits."""

    def setUp(self) -> None:
        translation = patch('qualcoder.ai_chat._', lambda text: text, create=True)
        translation.start()
        self.addCleanup(translation.stop)

        self.chat = MagicMock()
        self.chat.app.ai.is_current_run_canceled.return_value = False
        self.chat.app.ai._exception_summary.side_effect = str
        self.chat._begin_ai_change_set.return_value = ''
        self.chat._mcp_base_system_prompt.return_value = ''
        self.chat._build_mcp_combined_system_prompt.side_effect = lambda text: text
        self.chat._mcp_planner_system_prompt.return_value = 'Plan'
        self.chat._mcp_reflection_system_prompt.return_value = 'Reflect'
        self.chat._compact_mcp_result_content.return_value = '{}'
        self.chat._extract_methodology_gate.return_value = {}
        self.chat._empty_methodology_gate.return_value = {}
        self.chat._merge_methodology_gate.return_value = {}
        self.chat._snapshot_methodology_gate.return_value = {}
        self.chat._is_methodology_gate_blocking.return_value = False
        self.chat._normalize_progress_note.side_effect = lambda text, **kwargs: text
        self.chat._short_reflection_next_step_note.return_value = ''
        self.chat._mcp_final_answer_phase_prompts.return_value = ('Final', 'Answer now')
        for method_name in (
            '_parse_mcp_planner_response', '_parse_mcp_reflection_response',
            '_planner_output_missing_calls', '_normalize_mcp_calls',
            '_merge_mcp_call_lists', '_split_mcp_call_queue', '_mcp_call_key',
            '_json_bool', '_execute_validated_mcp_call', '_validate_mcp_call_params',
            '_summarize_mcp_failure',
        ):
            setattr(self.chat, method_name, MethodType(getattr(DialogAIChat, method_name), self.chat))
        self.executed_file_ids = []
        self.round_sizes = []
        self.chat._run_mcp_request.side_effect = self._run_request

    def _run_request(self, method: str, params: dict) -> tuple[dict, dict]:
        if method == 'tools/call':
            self.executed_file_ids.append(params['arguments']['fid'])
        return {}, {'result': {}}

    def _run_links(self, document_count: int) -> dict:
        """Run a planned queue against simulated successful tool responses.

        Args:
            document_count: Number of whole-document case links to request.
        """
        calls = [
            {
                'method': 'tools/call',
                'params': {
                    'name': 'cases_link_text_to_case',
                    'arguments': {'caseid': 1, 'fid': file_id, 'full_document': True},
                },
            }
            for file_id in range(1, document_count + 1)
        ]

        def invoke(messages: list, schema_name: str, **kwargs) -> dict:
            if schema_name == 'mcp_planner_control':
                return {'action': 'call_mcp', 'calls': calls}
            self.assertEqual('mcp_reflection_control', schema_name)
            self.round_sizes.append(len(self.executed_file_ids) - sum(self.round_sizes))
            if len(self.executed_file_ids) == document_count:
                return {'action': 'final_answer'}
            return {'action': 'call_mcp', 'continue_deferred_calls': True}

        self.chat._invoke_json_llm_with_step_timeout.side_effect = invoke
        result = DialogAIChat._mcp_general_chat_worker(self.chat, [], 0)
        self.assertNotIn('error', result)
        return result

    @staticmethod
    def _agent_state(result: dict) -> dict:
        return next(
            json.loads(message['msg_content'])
            for message in result['tool_messages']
            if message['msg_type'] == 'agent_state'
        )

    def test_seventy_case_links_finish_in_one_turn(self) -> None:
        result = self._run_links(70)

        self.assertEqual(list(range(1, 71)), self.executed_file_ids)
        self.assertEqual([12, 12, 12, 12, 12, 10], self.round_sizes)
        self.assertEqual(73, self.chat._run_mcp_request.call_count)
        state = self._agent_state(result)
        self.assertEqual('final_answer', state['stop_reason'])
        self.assertEqual([], state['pending_calls'])

    def test_eight_rounds_cap_execution_at_ninety_six_calls(self) -> None:
        result = self._run_links(100)

        self.assertEqual(list(range(1, 97)), self.executed_file_ids)
        self.assertEqual([12] * 8, self.round_sizes)
        self.assertEqual(99, self.chat._run_mcp_request.call_count)
        state = self._agent_state(result)
        self.assertEqual('max_reflection_rounds_reached', state['stop_reason'])
        self.assertEqual(
            [97, 98, 99, 100],
            [call['params']['arguments']['fid'] for call in state['pending_calls']],
        )

    def test_cancellation_still_stops_a_large_queue(self) -> None:
        self.chat.app.ai.is_current_run_canceled.side_effect = lambda: len(self.executed_file_ids) >= 45

        result = self._run_links(70)

        self.assertTrue(result['canceled'])
        self.assertEqual(list(range(1, 46)), self.executed_file_ids)
        self.assertEqual([], result['stream_messages'])
