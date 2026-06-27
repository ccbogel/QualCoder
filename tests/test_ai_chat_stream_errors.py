from types import SimpleNamespace
from unittest import TestCase, skipIf

import httpx

try:
    from qualcoder.ai_chat import DialogAIChat
    IMPORT_ERROR = None
except ModuleNotFoundError as err:
    DialogAIChat = None
    IMPORT_ERROR = err


class _AiService:
    def __init__(self):
        self.outputs = {"run-1": "partial answer"}

    def _is_stream_interruption_exception(self, err):
        return isinstance(err, httpx.TransportError)

    def get_streaming_output(self, run_id):
        return self.outputs.get(run_id, "")

    def clear_streaming_output(self, run_id):
        self.outputs.pop(run_id, None)


@skipIf(IMPORT_ERROR is not None, f"Optional AI chat dependency is not installed: {IMPORT_ERROR}")
class TestDialogAIChatStreamErrors(TestCase):

    def test_interrupted_stream_keeps_partial_response_from_ai_service_buffer(self):
        dialog = DialogAIChat.__new__(DialogAIChat)
        dialog.app = SimpleNamespace(ai=_AiService())
        dialog.current_streaming_chat_idx = 2
        dialog.current_streaming_run_id = "run-1"
        dialog.messages = []
        dialog._cancel_pending_stream_render = lambda: None
        dialog._clear_chat_ai_profile_snapshot = lambda chat_idx: None
        dialog._normalize_ai_profile_author = lambda chat_idx=None, fallback_to_current=False: "AI"

        def process_message(msg_type, msg_content, chat_idx):
            dialog.messages.append((msg_type, msg_content, chat_idx))

        dialog.process_message = process_message

        dialog.ai_error_callback(httpx.ReadError, httpx.ReadError("stream disconnected"), None)

        self.assertIn(("ai", "partial answer", 2), dialog.messages)
        self.assertTrue(
            any(
                msg_type == "info" and "partial response was kept" in msg_content
                for msg_type, msg_content, _chat_idx in dialog.messages
            )
        )
        self.assertEqual("", dialog.app.ai.get_streaming_output("run-1"))

    def test_replace_references_uses_general_mcp_candidates_for_new_text_analysis_chats(self):
        dialog = DialogAIChat.__new__(DialogAIChat)
        dialog.ai_text_doc_id = 7
        dialog._chat_analysis_type = lambda chat_idx=None: "text_analysis"
        dialog._collect_ref_candidates = lambda chat_idx=None: [{"source_id": 1, "start": 0, "text": "alpha"}]
        dialog._replace_text_references = lambda text, streaming=False: "legacy-path"
        dialog._replace_references_from_candidates = (
            lambda text, candidates, streaming=False, streaming_placeholder=None:
            f"general:{len(candidates)}:{text}"
        )

        result = dialog.replace_references('{REF: "alpha"}', chat_idx=0)

        self.assertEqual('general:1:{REF: "alpha"}', result)

    def test_replace_references_keeps_legacy_text_chat_fallback(self):
        dialog = DialogAIChat.__new__(DialogAIChat)
        dialog.ai_text_doc_id = 7
        dialog._chat_analysis_type = lambda chat_idx=None: "text chat"
        dialog._collect_ref_candidates = lambda chat_idx=None: [{"source_id": 1, "start": 0, "text": "alpha"}]
        dialog._replace_text_references = lambda text, streaming=False: "legacy-path"
        dialog._replace_references_from_candidates = (
            lambda text, candidates, streaming=False, streaming_placeholder=None:
            f"general:{len(candidates)}:{text}"
        )

        result = dialog.replace_references('{REF: "alpha"}', chat_idx=0)

        self.assertEqual("legacy-path", result)

    def test_render_plain_text_with_prompt_refs_keeps_html_and_replaces_prompt_placeholders(self):
        dialog = DialogAIChat.__new__(DialogAIChat)
        dialog._prompt_completion_enabled = lambda: True
        dialog._refresh_prompt_completion_records = lambda: None
        dialog._prompt_reference_placeholders_for_text = (
            lambda text, include_prompt_labels=False, require_enabled=False, style_role="user":
            (
                'Analyzing text from <a href="quote:1_2_3">Clare</a>\nQUALCODER_PROMPT_REF_0_TOKEN (project)',
                {"QUALCODER_PROMPT_REF_0_TOKEN": '<a href="promptref:ethnographic-brainstorming">/ethnographic-brainstorming</a>'},
            )
        )

        result = dialog._render_plain_text_with_prompt_refs("ignored", style_role="info")

        self.assertIn('<a href="quote:1_2_3">Clare</a>', result)
        self.assertIn('<a href="promptref:ethnographic-brainstorming">/ethnographic-brainstorming</a>', result)
        self.assertIn('<br />', result)

    def test_resolve_prompt_reference_name_restores_topic_exploration_prefix_for_nested_header_paths(self):
        dialog = DialogAIChat.__new__(DialogAIChat)
        nested_prompt = SimpleNamespace(name="topic-exploration/test/test", scope="project")
        dialog._prompt_reference_records_by_name = lambda: {
            "topic-exploration/test/test": nested_prompt,
        }
        dialog.current_chat_idx = 0
        dialog.chat_list = [(1, "Chat", "topic_exploration", "", "", "")]

        result = dialog._resolve_prompt_reference_name("test/test")

        self.assertIs(result, nested_prompt)

    def test_resolve_prompt_reference_name_restores_code_analysis_prefix_for_nested_header_paths(self):
        dialog = DialogAIChat.__new__(DialogAIChat)
        nested_prompt = SimpleNamespace(name="code-analysis/test/test", scope="project")
        dialog._prompt_reference_records_by_name = lambda: {
            "code-analysis/test/test": nested_prompt,
        }
        dialog.current_chat_idx = 0
        dialog.chat_list = [(1, "Chat", "code_analysis", "", "", "")]

        result = dialog._resolve_prompt_reference_name("test/test")

        self.assertIs(result, nested_prompt)
