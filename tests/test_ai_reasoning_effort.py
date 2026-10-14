from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from PyQt6 import QtWidgets

from qualcoder.ai_llm import AiLLM
from qualcoder.app import App
from qualcoder.settings import DialogSettings


class TestAiReasoningEffort(TestCase):
    """Check custom reasoning values from dialog editing through API setup."""

    @classmethod
    def setUpClass(cls):
        cls.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def make_profile(self, reasoning_effort: str) -> dict:
        return {
            'name': 'Test profile', 'desc': '', 'access_info_url': '',
            'large_model': 'test-large', 'large_model_context_window': '4096',
            'fast_model': 'test-fast', 'fast_model_context_window': '4096',
            'api_base': 'https://example.invalid/v1', 'api_key': 'test-key',
            'reasoning_effort': reasoning_effort,
        }

    def test_typed_values_are_saved_and_restored_when_switching_profiles(self):
        app = App.__new__(App)
        with patch.object(app, 'get_initial_language_code', return_value='en'):
            settings_data = app.default_settings
        settings_data.update(
            ai_enable='False', ai_model_index=0, report_text_context_style='Bold',
            report_text_context_characters=100,
        )
        app.settings = settings_data
        app.conn = None
        app.ai_models = [self.make_profile('none'), self.make_profile('xhigh')]
        app.ai_models[1]['name'] = 'Second profile'

        with (
            patch('qualcoder.settings._', side_effect=lambda text: text, create=True),
            patch.object(DialogSettings, 'populate_language_combo'),
            patch.object(DialogSettings, 'ai_update_available_models'),
        ):
            dialog = DialogSettings(app)
            try:
                reasoning_combo = dialog.ui.comboBox_reasoning
                self.assertTrue(reasoning_combo.isEditable())
                self.assertEqual('none', reasoning_combo.currentText())
                for custom_value in ('xhigh', 'provider-custom', ' none '):
                    reasoning_combo.lineEdit().setText(custom_value)
                    self.assertEqual(custom_value.strip(), dialog.ai_models[0]['reasoning_effort'])
                dialog.ui.comboBox_ai_profile.setCurrentIndex(1)
                self.assertEqual('xhigh', reasoning_combo.currentText())
                dialog.ui.comboBox_ai_profile.setCurrentIndex(0)
                self.assertEqual('none', reasoning_combo.currentText())
                self.assertEqual('xhigh', dialog.ai_models[1]['reasoning_effort'])
            finally:
                dialog.close()

    def test_api_setup_forwards_custom_values_and_omits_defaults(self):
        for effort_value in ('none', 'xhigh', 'provider-custom', ' low ', '', 'default'):
            with self.subTest(effort_value=effort_value):
                service = AiLLM.__new__(AiLLM)
                service.app = SimpleNamespace(
                    settings={'ai_enable': 'True', 'ai_model_index': 0},
                    ai_models=[self.make_profile(effort_value)],
                )
                service.parent_text_edit = MagicMock()
                service.sources_vectorstore = MagicMock()
                service.sources_vectorstore.is_open.return_value = True
                service.sources_vectorstore.ai_worker_running.return_value = False
                service._migrate_legacy_prompts_for_current_scope = MagicMock()
                with patch('qualcoder.ai_llm._', side_effect=lambda text: text, create=True):
                    service.init_llm(SimpleNamespace())
                self.assertEqual('True', service.app.settings['ai_enable'])
                if effort_value.strip() in ('', 'default'):
                    self.assertNotIn('reasoning_effort', service._large_llm_params)
                else:
                    self.assertEqual(effort_value.strip(), service._large_llm_params['reasoning_effort'])
                self.assertNotIn('reasoning_effort', service._fast_llm_params)
