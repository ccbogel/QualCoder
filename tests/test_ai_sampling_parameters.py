from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

from PyQt6 import QtCore, QtGui, QtWidgets

from qualcoder.ai_llm import AiLLM, CHATGPT_OAUTH_API_BASE
from qualcoder.settings import DialogSettings, StrictDoubleRangeValidator


class TestAiSamplingParameters(TestCase):
    """Check optional sampling values in settings and API setup."""

    @classmethod
    def setUpClass(cls):
        cls.qt_app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_blank_fields_pass_validation(self):
        for field_name, validate_method, maximum in (
            ('lineEdit_ai_temperature', DialogSettings.validate_ai_temperature, 2.0),
            ('lineEdit_top_p', DialogSettings.validate_ai_top_p, 1.0),
        ):
            with self.subTest(field_name=field_name):
                line_edit = QtWidgets.QLineEdit()
                validator = StrictDoubleRangeValidator(0.0, maximum, 6, line_edit)
                validator.setLocale(QtCore.QLocale.c())
                line_edit.setValidator(validator)
                dialog = SimpleNamespace(
                    ui=SimpleNamespace(**{field_name: line_edit}),
                    parse_bounded_float=DialogSettings.parse_bounded_float,
                )
                dialog.validate_ai_float_field = lambda *args: DialogSettings.validate_ai_float_field(dialog, *args)
                for blank_value in ('', '   '):
                    line_edit.setText(blank_value)
                    self.assertTrue(line_edit.hasAcceptableInput())
                    with patch('qualcoder.settings._', side_effect=lambda text: text, create=True):
                        self.assertTrue(validate_method(dialog))
                    self.assertEqual('', line_edit.text())
                self.assertEqual(QtGui.QValidator.State.Invalid, validator.validate(str(maximum + 1), 1)[0])

    def test_numeric_values_keep_range_checks(self):
        self.assertEqual('0.0', DialogSettings.parse_bounded_float('0', 0.0, 2.0))
        self.assertEqual('0.5', DialogSettings.parse_bounded_float(' 0,5 ', 0.0, 1.0))
        for invalid_value in ('bad', '-0.1', '1.1', 'nan', 'inf'):
            with self.subTest(invalid_value=invalid_value), self.assertRaises(ValueError):
                DialogSettings.parse_bounded_float(invalid_value, 0.0, 1.0)

    def test_api_setup_omits_blank_values_for_both_models(self):
        for api_base in ('https://example.invalid/v1', 'https://example.azure.com', CHATGPT_OAUTH_API_BASE):
            for temperature_value, top_p_value in (('', ''), (' ', '0.7'), ('0', ''), ('0.5', '1.0'), (None, None)):
                with self.subTest(api_base=api_base, temperature=temperature_value, top_p=top_p_value):
                    settings_data = {'ai_enable': 'True', 'ai_model_index': 0}
                    if temperature_value is not None:
                        settings_data['ai_temperature'] = temperature_value
                    if top_p_value is not None:
                        settings_data['ai_top_p'] = top_p_value
                    service = AiLLM.__new__(AiLLM)
                    service.app = SimpleNamespace(settings=settings_data, ai_models=[{
                        'large_model': 'test-large', 'large_model_context_window': '4096',
                        'fast_model': 'test-fast', 'fast_model_context_window': '4096',
                        'api_base': api_base, 'api_key': 'test-key', 'reasoning_effort': 'default',
                    }])
                    service.parent_text_edit = MagicMock()
                    service.sources_vectorstore = MagicMock()
                    service.sources_vectorstore.is_open.return_value = True
                    service.sources_vectorstore.ai_worker_running.return_value = False
                    service._migrate_legacy_prompts_for_current_scope = MagicMock()
                    with patch('qualcoder.ai_llm._', side_effect=lambda text: text, create=True):
                        service.init_llm(SimpleNamespace())
                    self.assertEqual('True', service.app.settings['ai_enable'])
                    for model_params in (service._large_llm_params, service._fast_llm_params):
                        for param_name, input_value in (('temperature', temperature_value), ('top_p', top_p_value)):
                            if input_value is None:
                                input_value = '1.0'
                            if input_value.strip() == '' or (param_name == 'top_p' and api_base == CHATGPT_OAUTH_API_BASE):
                                self.assertNotIn(param_name, model_params)
                            else:
                                self.assertEqual(float(input_value), model_params[param_name])
