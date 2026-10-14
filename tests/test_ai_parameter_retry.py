import threading
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import httpx
from openai import BadRequestError

from qualcoder.ai_llm import AiLLM


class TestAiParameterRetry(TestCase):
    """Regression tests for unsupported parameters without an API param field."""

    def setUp(self):
        self.ai_service = AiLLM.__new__(AiLLM)

    def make_error(self, error_body: dict) -> BadRequestError:
        """Build an API error without making a network request.

        Args:
            error_body: JSON body returned by the API.
        """
        response = httpx.Response(
            400, request=httpx.Request('POST', 'https://example.invalid/v1/chat/completions')
        )
        return BadRequestError(str(error_body), response=response, body=error_body)

    def test_detects_parameter_from_detail_with_missing_param(self):
        error = self.make_error({'detail': 'Unsupported parameter: temperature'})
        self.assertIsNone(error.param)
        self.assertEqual('temperature', self.ai_service._unsupported_param_from_error(error))

    def test_detects_parameter_from_message_with_null_param(self):
        error = self.make_error({
            'error': {'param': None, 'message': "Unsupported parameter: 'top_p'"}
        })
        self.assertEqual('top_p', self.ai_service._unsupported_param_from_error(error))

    def test_preserves_explicit_param_and_ignores_unrelated_errors(self):
        for error_body, expected in (
            ({'error': {'param': 'temperature', 'message': 'Invalid request'}}, 'temperature'),
            ({'detail': 'Invalid request', 'param': None}, ''),
        ):
            with self.subTest(error_body=error_body):
                self.assertEqual(
                    expected, self.ai_service._unsupported_param_from_error(self.make_error(error_body))
                )

    def test_retries_after_removing_both_sampling_parameters(self):
        self.ai_service._unsupported_llm_params_lock = threading.Lock()
        self.ai_service._unsupported_llm_params_by_key = {}
        self.ai_service._large_llm_params = {
            'model': 'gpt-6.1-sol', 'temperature': 1.0, 'top_p': 1.0,
        }
        self.ai_service.log_llm_retry = MagicMock()
        model_instances = []

        def build_model(**model_params: object) -> MagicMock:
            model_instance = MagicMock()
            for sampling_param in ('temperature', 'top_p'):
                if sampling_param in model_params:
                    model_instance.invoke.side_effect = self.make_error({
                        'detail': f'Unsupported parameter: {sampling_param}'
                    })
                    break
            else:
                model_instance.invoke.return_value = 'success'
            model_instances.append(model_instance)
            return model_instance

        self.ai_service._large_llm_factory = MagicMock(side_effect=build_model)
        run_context = SimpleNamespace(
            model_kind='large', purpose='invoke',
            llm=build_model(**self.ai_service._large_llm_params), http_client=None,
            cancel_event=threading.Event(),
        )
        with (
            patch('qualcoder.ai_llm.httpx', httpx),
            patch.object(self.ai_service, '_run_timeout', return_value=30.0),
        ):
            result = self.ai_service._invoke_with_unsupported_parameter_retry(
                run_context, ['Hello'], {}, 1, context='mcp_json_planner'
            )
        run_context.http_client.close()

        self.assertEqual('success', result)
        self.assertEqual(3, len(model_instances))
        self.assertEqual(2, self.ai_service.log_llm_retry.call_count)
        filtered_params = self.ai_service._filtered_llm_base_params(
            self.ai_service._large_llm_factory, self.ai_service._large_llm_params
        )
        self.assertEqual({'model': 'gpt-6.1-sol'}, filtered_params)
