from copy import deepcopy
import json
from types import MethodType, SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock

from jsonschema import Draft202012Validator

from qualcoder.ai_chat import DialogAIChat
from qualcoder.ai_mcp_schema import mcp_control_json_schema, parse_mcp_control_response


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
            {'method': 'resources/templates/list', 'params': {'cursor': None}},
            {
                'method': 'resources/read',
                'params': {'uri': 'qualcoder://documents', 'start': None, 'length': None},
            },
            {'method': 'tools/list', 'params': {'cursor': None}},
            {
                'method': 'tools/call',
                'params': {'name': 'example_tool', 'arguments': '{"example": 1}'},
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

    def test_entire_control_schemas_use_strict_output_subset(self):
        def check_schema(schema: dict):
            forbidden = {'allOf', 'oneOf', 'if', 'then', 'else', 'not', 'minLength', 'minItems', 'maxItems'}
            self.assertFalse(forbidden.intersection(schema))
            if schema.get('type') == 'object':
                self.assertIs(schema['additionalProperties'], False)
                self.assertEqual(set(schema['properties']), set(schema['required']))
            for child in schema.get('properties', {}).values():
                check_schema(child)
            if 'items' in schema:
                check_schema(schema['items'])
            for child in schema.get('anyOf', []):
                check_schema(child)

        for schema in (DialogAIChat._mcp_planner_json_schema(None),
                       DialogAIChat._mcp_reflection_json_schema(None)):
            Draft202012Validator.check_schema(schema)
            check_schema(schema)
            self.assertEqual('object', schema['type'])


def controller_payload(reflection: bool = False, **changes) -> dict:
    """Build a complete controller response for validation tests."""
    payload = {
        'action': 'final_answer',
        'methodology_decision': 'allow',
        'methodology_note': '',
        'user_decision_required': False,
        'decision_question': '',
        'decision_context': '',
        'proposed_next_calls': [],
        'answer_brief': '',
    }
    if reflection:
        payload.update(reflection_summary='', next_step_note='', continue_deferred_calls=False, revised_calls=[])
    else:
        payload.update(plan_summary='', calls=[])
    payload.update(changes)
    return payload


class TestMcpControlValidation(TestCase):
    """Check transport decoding and action rules before any MCP dispatch."""

    def test_valid_actions_for_both_phases(self):
        for reflection in (False, True):
            calls_key = 'revised_calls' if reflection else 'calls'
            payloads = [
                controller_payload(reflection),
                controller_payload(reflection, methodology_decision='refuse'),
                controller_payload(reflection, action='ask_user', user_decision_required=True,
                                   decision_question='Continue?', proposed_next_calls=[
                                       {'method': 'tools/list', 'params': {}},
                                   ]),
                controller_payload(reflection, action='call_mcp', **{
                    calls_key: [{'method': 'initialize', 'params': {}}],
                }),
            ]
            for payload in payloads:
                with self.subTest(reflection=reflection, action=payload['action']):
                    self.assertEqual(payload, parse_mcp_control_response(payload, reflection))
        deferred = controller_payload(True, action='call_mcp', continue_deferred_calls=True)
        self.assertEqual(deferred, parse_mcp_control_response(deferred, True))

    def test_contradictory_actions_are_rejected_in_both_phases(self):
        for reflection in (False, True):
            calls_key = 'revised_calls' if reflection else 'calls'
            call = {'method': 'initialize', 'params': {}}
            changes = [
                {'action': 'call_mcp'},
                {calls_key: [call]},
                {'proposed_next_calls': [call]},
                {'user_decision_required': True},
                {'decision_question': 'Continue?'},
                {'decision_context': 'Pending approval'},
                {'action': 'ask_user', 'decision_question': 'Continue?'},
                {'action': 'ask_user', 'user_decision_required': True, 'decision_question': '  '},
                {'action': 'ask_user', 'user_decision_required': True,
                 'decision_question': 'Continue?', calls_key: [call]},
                {'action': 'call_mcp', calls_key: [call], 'methodology_decision': 'refuse'},
                {'action': 'ask_user', 'user_decision_required': True,
                 'decision_question': 'Continue?', 'methodology_decision': 'reframe_and_ask'},
                {'action': 'call_mcp', calls_key: [call], 'user_decision_required': True},
            ]
            if reflection:
                changes.extend([
                    {'continue_deferred_calls': True},
                    {'action': 'ask_user', 'user_decision_required': True,
                     'decision_question': 'Continue?', 'continue_deferred_calls': True},
                ])
            for fields in changes:
                with self.subTest(reflection=reflection, fields=fields), self.assertRaises(ValueError):
                    parse_mcp_control_response(controller_payload(reflection, **fields), reflection)

    def test_tool_arguments_round_trip_without_changing_nested_values(self):
        arguments = {'text': 'Grüße "quoted"\nline', 'nested': {'value': None}, 'items': [1, True]}
        for encoded_arguments in (arguments, json.dumps(arguments, ensure_ascii=False)):
            with self.subTest(encoded=isinstance(encoded_arguments, str)):
                payload = controller_payload(action='call_mcp', calls=[{
                    'method': 'tools/call', 'params': {'name': 'example', 'arguments': encoded_arguments},
                }])
                original = deepcopy(payload)
                decoded = parse_mcp_control_response(payload)
                self.assertEqual(arguments, decoded['calls'][0]['params']['arguments'])
                self.assertEqual(original, payload)

    def test_optional_transport_nulls_are_removed(self):
        payload = controller_payload(action='call_mcp', calls=[
            {'method': 'resources/read', 'params': {'uri': 'qualcoder://documents', 'start': None, 'length': 10}},
            {'method': 'tools/list', 'params': {'cursor': None}},
            {'method': 'resources/list', 'params': {'cursor': 'next'}},
        ])
        decoded = parse_mcp_control_response(payload)
        self.assertEqual({'uri': 'qualcoder://documents', 'length': 10}, decoded['calls'][0]['params'])
        self.assertEqual({}, decoded['calls'][1]['params'])
        self.assertEqual({'cursor': 'next'}, decoded['calls'][2]['params'])

    def test_invalid_calls_in_executable_and_proposed_lists_are_rejected(self):
        bad_calls = [
            {'method': 'unknown', 'params': {}},
            {'method': 'initialize', 'params': {'extra': True}},
            {'method': 'resources/read', 'params': {}},
            {'method': 'resources/read', 'params': {'uri': '   '}},
            {'method': 'resources/read', 'params': {'uri': 'qualcoder://documents', 'start': False}},
            {'method': 'tools/call', 'params': {'name': 'tool'}},
            {'method': 'tools/call', 'params': {'name': ' ', 'arguments': '{}'}},
        ]
        for arguments in ('invalid JSON', '[]', 'null', '"string"', '{"value": NaN}', 1, None):
            bad_calls.append({'method': 'tools/call', 'params': {'name': 'tool', 'arguments': arguments}})
        for call in bad_calls:
            for field_name in ('calls', 'proposed_next_calls'):
                payload = controller_payload(action='call_mcp', calls=[{'method': 'initialize', 'params': {}}])
                payload[field_name] = [call]
                with self.subTest(call=call, field=field_name), self.assertRaises(ValueError):
                    parse_mcp_control_response(payload)

    def test_missing_unknown_and_wrongly_typed_fields_are_rejected(self):
        for field_name, value in (('action', 'unknown'), ('user_decision_required', 'false'),
                                  ('calls', {}), ('unexpected', True)):
            with self.subTest(field=field_name), self.assertRaises(ValueError):
                parse_mcp_control_response(controller_payload(**{field_name: value}))
        payload = controller_payload()
        del payload['action']
        with self.assertRaises(ValueError):
            parse_mcp_control_response(payload)


class TestMcpControlInvocation(TestCase):
    """Exercise correction and fallback decoding at the model invocation boundary."""

    def setUp(self):
        self.ai = SimpleNamespace(
            get_response_format_json_schema=MagicMock(return_value={'type': 'json_schema'}),
            invoke_with_logging=MagicMock(),
        )
        self.dialog = SimpleNamespace(app=SimpleNamespace(ai=self.ai))
        self.dialog._extract_first_json_object = MethodType(DialogAIChat._extract_first_json_object, self.dialog)

    def invoke(self, schema_name: str = 'mcp_planner_control') -> dict:
        return DialogAIChat._invoke_json_llm(
            self.dialog, [], schema_name=schema_name,
            response_schema=mcp_control_json_schema(schema_name == 'mcp_reflection_control'),
        )

    def test_bad_response_is_corrected_once_before_returning(self):
        for schema_name in ('mcp_planner_control', 'mcp_replanner_control', 'mcp_reflection_control'):
            reflection = schema_name == 'mcp_reflection_control'
            valid = controller_payload(reflection)
            self.ai.invoke_with_logging.reset_mock()
            self.ai.invoke_with_logging.side_effect = [
                SimpleNamespace(content=json.dumps(controller_payload(reflection, action='call_mcp'))),
                SimpleNamespace(content=json.dumps(valid)),
            ]
            with self.subTest(schema_name=schema_name):
                self.assertEqual(valid, self.invoke(schema_name))
                self.assertEqual(2, self.ai.invoke_with_logging.call_count)
                correction = self.ai.invoke_with_logging.call_args.args[0][-1].content
                self.assertIn('requires executable calls', correction)

    def test_persistently_invalid_response_stops_after_one_correction(self):
        self.ai.invoke_with_logging.return_value = SimpleNamespace(content='{}')
        with self.assertRaisesRegex(ValueError, 'after correction'):
            self.invoke()
        self.assertEqual(2, self.ai.invoke_with_logging.call_count)

    def test_transport_error_is_not_retried_as_invalid_model_output(self):
        self.ai.invoke_with_logging.side_effect = RuntimeError('Server overloaded')
        with self.assertRaisesRegex(RuntimeError, 'Server overloaded'):
            self.invoke()
        self.ai.invoke_with_logging.assert_called_once()

    def test_non_controller_json_behavior_is_preserved(self):
        self.ai.invoke_with_logging.return_value = SimpleNamespace(content='{"metadata": 1}')
        self.assertEqual({'metadata': 1}, self.invoke('agent_chat_metadata'))
        self.assertEqual([], self.ai.invoke_with_logging.call_args.args[0])

    def test_native_fallback_arguments_are_validated_and_returned_as_objects(self):
        payload = controller_payload(action='call_mcp', calls=[{
            'method': 'tools/call', 'params': {'name': 'tool', 'arguments': {'value': 1}},
        }])
        self.ai.invoke_with_logging.return_value = SimpleNamespace(content=json.dumps(payload))
        self.assertEqual(payload, self.invoke())
        self.ai.invoke_with_logging.assert_called_once()
        self.assertTrue(self.ai.invoke_with_logging.call_args.kwargs['fallback_without_response_format'])
