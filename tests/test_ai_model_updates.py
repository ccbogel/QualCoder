import copy
from unittest import TestCase

from qualcoder.ai_llm import (
    get_default_ai_models,
    get_obsolete_ai_models,
    update_ai_models,
)


def _find_model(models: list[dict[str, str]], name: str) -> dict[str, str] | None:
    """Return a named AI profile from a model list.

    Args:
        models: AI profiles to search.
        name: Exact profile name.
    """

    return next((model for model in models if model['name'] == name), None)


class TestAiModelUpdates(TestCase):
    """Regression tests for default and obsolete AI profile updates."""

    def setUp(self):
        self.default_models = get_default_ai_models()
        self.obsolete_models = get_obsolete_ai_models()

    def test_unchanged_obsolete_profile_is_removed(self):
        """An unselected obsolete default is removed and the selection remains stable."""

        obsolete_model = copy.deepcopy(_find_model(self.obsolete_models, 'OpenAI GPT5.5 reasoning'))
        selected_model = copy.deepcopy(_find_model(self.default_models, 'Mistral'))

        models, current_index, _ = update_ai_models([obsolete_model, selected_model], 1)

        self.assertIsNone(_find_model(models, 'OpenAI GPT5.5 reasoning'))
        self.assertIsNotNone(_find_model(models, 'OpenAI GPT5.6 reasoning'))
        self.assertEqual('Mistral', models[current_index]['name'])

    def test_customized_obsolete_profile_is_preserved(self):
        """Changing any persisted field protects an obsolete profile from removal."""

        obsolete_model = copy.deepcopy(_find_model(self.obsolete_models, 'OpenAI GPT5.5 reasoning'))
        obsolete_model['api_key'] = 'user-api-key'
        selected_model = copy.deepcopy(_find_model(self.default_models, 'Mistral'))

        models, current_index, _ = update_ai_models([obsolete_model, selected_model], 1)

        preserved_model = _find_model(models, 'OpenAI GPT5.5 reasoning')
        self.assertIsNotNone(preserved_model)
        self.assertEqual('user-api-key', preserved_model['api_key'])
        self.assertEqual('Mistral', models[current_index]['name'])

    def test_selected_obsolete_profile_is_preserved(self):
        """The selected profile is retained even when it exactly matches an obsolete default."""

        selected_model = copy.deepcopy(_find_model(self.obsolete_models, 'OpenAI GPT5.5 reasoning'))
        other_model = copy.deepcopy(_find_model(self.default_models, 'Mistral'))

        models, current_index, _ = update_ai_models([other_model, selected_model], 1)

        self.assertEqual('OpenAI GPT5.5 reasoning', models[current_index]['name'])
        self.assertEqual(selected_model, models[current_index])

    def test_obsolete_profile_with_same_name_is_replaced(self):
        """An obsolete definition is replaced when the current default uses the same name."""

        obsolete_model = copy.deepcopy(_find_model(self.obsolete_models, 'Anthropic Claude Sonnet 5'))
        selected_model = copy.deepcopy(_find_model(self.default_models, 'Mistral'))
        expected_model = _find_model(self.default_models, 'Anthropic Claude Sonnet 5')

        models, current_index, _ = update_ai_models([obsolete_model, selected_model], 1)

        matching_models = [model for model in models if model['name'] == 'Anthropic Claude Sonnet 5']
        self.assertEqual([expected_model], matching_models)
        self.assertEqual('Mistral', models[current_index]['name'])

