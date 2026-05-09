import httpx
from types import SimpleNamespace
from unittest import TestCase, skipIf

try:
    from qualcoder.ai_chat import DialogAIChat
    IMPORT_ERROR = None
except ModuleNotFoundError as err:
    DialogAIChat = None
    IMPORT_ERROR = err


class _AiService:
    def __init__(self):
        self.ai_streaming_output = "partial answer"

    def _is_stream_interruption_exception(self, err):
        return isinstance(err, httpx.TransportError)


@skipIf(IMPORT_ERROR is not None, f"Optional AI chat dependency is not installed: {IMPORT_ERROR}")
class TestDialogAIChatStreamErrors(TestCase):

    def test_interrupted_stream_keeps_partial_response_from_ai_service_buffer(self):
        dialog = DialogAIChat.__new__(DialogAIChat)
        dialog.app = SimpleNamespace(ai=_AiService())
        dialog.current_streaming_chat_idx = 2
        dialog.ai_streaming_output = ""
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
        self.assertEqual("", dialog.app.ai.ai_streaming_output)
