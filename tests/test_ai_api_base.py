import os
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from langchain_openai import ChatOpenAI

from qualcoder.ai_llm import AiLLM


class TestAiApiBase(TestCase):
    """Verify profile URLs reach the real SDK with the intended defaults."""

    def test_profile_api_base_resolution(self):
        for profile_base, expected_url in (
            ('', 'https://api.openai.com/v1/'),
            ('  \t', 'https://api.openai.com/v1/'),
            (None, 'https://api.openai.com/v1/'),
            (' http://localhost:11434/v1/ ', 'http://localhost:11434/v1/'),
        ):
            with self.subTest(api_base=profile_base):
                service = AiLLM.__new__(AiLLM)
                service.app = SimpleNamespace(
                    settings={'ai_enable': 'True', 'ai_model_index': 0},
                    ai_models=[{
                        'large_model': 'gpt-4.1',
                        'large_model_context_window': 4096,
                        'fast_model': 'gpt-4.1-mini',
                        'fast_model_context_window': 4096,
                        'api_base': profile_base,
                        'api_key': 'test-key',
                    }],
                )
                service.parent_text_edit = MagicMock()
                service.sources_vectorstore = MagicMock()
                service._migrate_legacy_prompts_for_current_scope = MagicMock()
                with patch('qualcoder.ai_llm.QtWidgets.QApplication.processEvents'), \
                        patch('qualcoder.ai_llm._', side_effect=lambda text: text, create=True), \
                        patch.dict(os.environ, {}, clear=True):
                    service.init_llm(SimpleNamespace())
                    for model_params in (service._large_llm_params, service._fast_llm_params):
                        model = ChatOpenAI(**model_params)
                        try:
                            self.assertEqual(expected_url, str(model.root_client.base_url))
                        finally:
                            model.root_client.close()
