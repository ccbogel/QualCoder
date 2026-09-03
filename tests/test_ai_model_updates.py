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

    def test_obsolete_history_is_unique_and_excludes_current_defaults(self):
        """Historical snapshots contain no duplicate or current profile definitions."""

        obsolete_snapshots = {tuple(sorted(model.items())) for model in self.obsolete_models}
        current_snapshots = {tuple(sorted(model.items())) for model in self.default_models}

        self.assertEqual(44, len(self.obsolete_models))
        self.assertEqual(len(self.obsolete_models), len(obsolete_snapshots))
        self.assertTrue(obsolete_snapshots.isdisjoint(current_snapshots))

    def test_gpt_35_era_profiles_are_in_obsolete_history(self):
        """The earliest configurable profiles using GPT-3.5 are retained as snapshots."""

        gpt_35_profiles = [
            model for model in self.obsolete_models
            if model['fast_model'] == 'gpt-3.5-turbo'
        ]

        self.assertEqual(4, len(gpt_35_profiles))
        self.assertEqual(
            {'OpenAI_GPT4', 'OpenAI_GPT4-turbo', 'OpenAI_GPT4o'},
            {model['name'] for model in gpt_35_profiles},
        )

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

    def test_unseen_upgrade_offer_survives_model_list_reload(self):
        """An unseen offer remains available after newly added profiles were persisted."""

        selected_model = copy.deepcopy(_find_model(self.obsolete_models, 'OpenAI GPT5.5 reasoning'))
        settings = {}

        models, current_index, first_offer = update_ai_models([selected_model], 0, settings)
        _, _, reloaded_offer = update_ai_models(copy.deepcopy(models), current_index, settings)

        expected_offer = {
            'current_model_name': 'OpenAI GPT5.5 reasoning',
            'suggested_model_name': 'OpenAI GPT5.6 reasoning',
        }
        self.assertEqual(expected_offer, first_offer)
        self.assertEqual(expected_offer, reloaded_offer)

    def test_obsolete_profile_with_same_name_is_replaced(self):
        """An obsolete definition is replaced when the current default uses the same name."""

        obsolete_model = copy.deepcopy(_find_model(self.obsolete_models, 'Anthropic Claude Sonnet 5'))
        selected_model = copy.deepcopy(_find_model(self.default_models, 'Mistral'))
        expected_model = _find_model(self.default_models, 'Anthropic Claude Sonnet 5')

        models, current_index, _ = update_ai_models([obsolete_model, selected_model], 1)

        matching_models = [model for model in models if model['name'] == 'Anthropic Claude Sonnet 5']
        self.assertEqual([expected_model], matching_models)
        self.assertEqual('Mistral', models[current_index]['name'])

    def test_earlier_historical_profile_is_removed(self):
        """An unchanged profile from an earlier model generation is removed."""

        obsolete_model = copy.deepcopy(_find_model(self.obsolete_models, 'OpenAI GPT5.2 reasoning'))
        selected_model = copy.deepcopy(_find_model(self.default_models, 'Mistral'))

        models, current_index, _ = update_ai_models([obsolete_model, selected_model], 1)

        self.assertIsNone(_find_model(models, 'OpenAI GPT5.2 reasoning'))
        self.assertEqual('Mistral', models[current_index]['name'])
