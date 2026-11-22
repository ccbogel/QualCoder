"""Strict API schemas and local validation for MCP controller responses."""

from copy import deepcopy
import json
from typing import Any

from jsonschema import Draft202012Validator


MCP_CONTROL_SCHEMA_NAMES = frozenset({
    'mcp_planner_control', 'mcp_replanner_control', 'mcp_reflection_control',
})
MCP_CONTROL_FORMAT_INSTRUCTIONS = (
    'For MCP calls in this response, encode tools/call params.arguments as a JSON '
    'string containing an object, for example "{\\"name\\": \\"value\\"}". '
    'Use null for unused cursor, start, or length fields required by the response schema. '
    'Keep params itself an object. All other controller fields follow the phase instructions.'
)


def mcp_call_json_schema() -> dict[str, Any]:
    """Return closed MCP call variants supported by strict Structured Outputs."""
    empty_params = {'type': 'object', 'properties': {}, 'required': [], 'additionalProperties': False}
    list_params = {
        'type': 'object',
        'properties': {'cursor': {'type': ['string', 'null']}},
        'required': ['cursor'],
        'additionalProperties': False,
    }
    read_params = {
        'type': 'object',
        'properties': {
            'uri': {'type': 'string'},
            'start': {'type': ['number', 'string', 'null']},
            'length': {'type': ['number', 'string', 'null']},
        },
        'required': ['uri', 'start', 'length'],
        'additionalProperties': False,
    }
    tool_params = {
        'type': 'object',
        'properties': {
            'name': {'type': 'string'},
            'arguments': {
                'type': 'string',
                'description': 'A JSON-encoded object with the arguments from the discovered tool schema.',
            },
        },
        'required': ['name', 'arguments'],
        'additionalProperties': False,
    }
    variants = []
    for method_name, params_schema in (
        ('initialize', empty_params),
        ('resources/list', list_params),
        ('resources/templates/list', list_params),
        ('resources/read', read_params),
        ('tools/list', list_params),
        ('tools/call', tool_params),
    ):
        variants.append({
            'type': 'object',
            'properties': {
                'method': {'type': 'string', 'enum': [method_name]},
                'params': params_schema,
            },
            'required': ['method', 'params'],
            'additionalProperties': False,
        })
    return {'anyOf': variants}


def mcp_control_json_schema(reflection: bool = False) -> dict[str, Any]:
    """Return the API schema; action-dependent rules are validated locally.

    Args:
        reflection: Whether to build a reflection rather than a planning response.
    """
    properties = {
        'action': {'type': 'string', 'enum': ['call_mcp', 'final_answer', 'ask_user']},
    }
    if reflection:
        properties.update({
            'reflection_summary': {'type': 'string'},
            'next_step_note': {'type': 'string'},
        })
    else:
        properties['plan_summary'] = {'type': 'string'}
    properties.update({
        'methodology_decision': {
            'type': 'string',
            'enum': ['allow', 'allow_with_caveat', 'reframe_and_ask', 'refuse'],
        },
        'methodology_note': {'type': 'string'},
    })
    if reflection:
        properties['continue_deferred_calls'] = {'type': 'boolean'}
    properties.update({
        'user_decision_required': {'type': 'boolean'},
        'decision_question': {'type': 'string'},
        'decision_context': {'type': 'string'},
        'proposed_next_calls': {'type': 'array', 'items': mcp_call_json_schema()},
        'revised_calls' if reflection else 'calls': {'type': 'array', 'items': mcp_call_json_schema()},
        'answer_brief': {'type': 'string'},
    })
    return {
        'type': 'object',
        'properties': properties,
        'required': list(properties),
        'additionalProperties': False,
    }


def parse_mcp_control_response(payload: Any, reflection: bool = False) -> dict[str, Any]:
    """Validate one controller response and decode calls before they can execute.

    Args:
        payload: Parsed model output, including responses without API format enforcement.
        reflection: Whether the payload belongs to the reflection phase.

    Raises:
        ValueError: If the structure, tool arguments, or controller decisions are invalid.
    """
    if not isinstance(payload, dict):
        raise ValueError('The MCP controller response must be an object.')
    data = deepcopy(payload)
    calls_key = 'revised_calls' if reflection else 'calls'
    # Also accept native argument objects and omitted optional parameters from
    # providers using the existing fallback without response_format.
    for field_name in (calls_key, 'proposed_next_calls'):
        raw_calls = data.get(field_name)
        if not isinstance(raw_calls, list):
            continue
        for call in raw_calls:
            if not isinstance(call, dict) or not isinstance(call.get('params'), dict):
                continue
            method_name = call.get('method')
            params = call['params']
            if method_name in ('resources/list', 'resources/templates/list', 'tools/list'):
                params.setdefault('cursor', None)
            elif method_name == 'resources/read':
                params.setdefault('start', None)
                params.setdefault('length', None)
            elif method_name == 'tools/call' and isinstance(params.get('arguments'), dict):
                params['arguments'] = json.dumps(params['arguments'], ensure_ascii=False, allow_nan=False)

    error = next(Draft202012Validator(mcp_control_json_schema(reflection)).iter_errors(data), None)
    if error is not None:
        location = '.'.join(str(part) for part in error.absolute_path) or 'response'
        raise ValueError(f'Invalid MCP controller field {location}: {error.message}')

    for field_name in (calls_key, 'proposed_next_calls'):
        for call in data[field_name]:
            method_name = call['method']
            params = call['params']
            if method_name == 'tools/call':
                try:
                    arguments = json.loads(params['arguments'])
                    json.dumps(arguments, allow_nan=False)
                except (ValueError, TypeError) as err:
                    raise ValueError('Tool arguments must contain a JSON-encoded object.') from err
                if not isinstance(arguments, dict):
                    raise ValueError('Tool arguments must decode to an object.')
                params['arguments'] = arguments
                if not params['name'].strip():
                    raise ValueError('tools/call requires a nonempty tool name.')
            elif method_name == 'resources/read' and not params['uri'].strip():
                raise ValueError('resources/read requires a nonempty URI.')
            # Remove only optional transport fields, preserving nulls inside tool arguments.
            for optional_name in ('cursor', 'start', 'length'):
                if optional_name in params and params[optional_name] is None:
                    del params[optional_name]

    action = data['action']
    calls = data[calls_key]
    continue_deferred = data.get('continue_deferred_calls', False)
    if data['methodology_decision'] in ('reframe_and_ask', 'refuse') and action != 'final_answer':
        raise ValueError('A blocking methodology decision requires action=final_answer.')
    if action == 'call_mcp':
        if not calls and not continue_deferred:
            raise ValueError('action=call_mcp requires executable calls or continued deferred calls.')
    elif action == 'ask_user':
        if not data['user_decision_required'] or not data['decision_question'].strip():
            raise ValueError('action=ask_user requires a user decision and a nonempty question.')
        if calls or continue_deferred:
            raise ValueError('action=ask_user must not execute or continue calls.')
    elif calls or continue_deferred or data['proposed_next_calls']:
        raise ValueError('action=final_answer must not execute, continue, or propose calls.')
    if action != 'ask_user' and (
        data['user_decision_required'] or data['decision_question'] or data['decision_context']
    ):
        raise ValueError('Only action=ask_user may request a user decision or include question/context fields.')
    return data
