from unittest import TestCase

from jsonschema import Draft202012Validator

from qualcoder.ai_chat import DialogAIChat


class TestAiPlannerSchema(TestCase):
    """Validate executable MCP calls against the agent's response schema."""

    def setUp(self):
        schema = DialogAIChat._mcp_allowed_call_json_schema(None)
        Draft202012Validator.check_schema(schema)
        self.validator = Draft202012Validator(schema)

    def test_concrete_calls_are_valid(self):
        calls = [
            {'method': 'initialize', 'params': {}},
            {'method': 'resources/list', 'params': {'cursor': 'next-page'}},
            {'method': 'resources/templates/list', 'params': {}},
            {
                'method': 'resources/read',
                'params': {'uri': 'qualcoder://documents'},
            },
            {'method': 'tools/list', 'params': {}},
            {
                'method': 'tools/call',
                'params': {'name': 'example_tool', 'arguments': {'example': 1}},
            },
        ]
        for call in calls:
            with self.subTest(call=call):
                self.validator.validate(call)

    def test_incomplete_or_unexpected_calls_are_invalid(self):
        calls = [
            {},
            {'method': 'resources/read'},
            {'params': {}},
            {'method': 'unknown', 'params': {}},
            {'method': 'resources/read', 'params': {}},
            {'method': 'tools/call', 'params': {'name': 'example_tool'}},
            {'method': 'initialize', 'params': {}, 'unexpected': True},
            {'method': 'initialize', 'params': {'unexpected': True}},
            {
                'method': 'resources/read',
                'params': {'uri': 'qualcoder://documents', 'unexpected': True},
            },
        ]
        for call in calls:
            with self.subTest(call=call):
                self.assertFalse(self.validator.is_valid(call))
