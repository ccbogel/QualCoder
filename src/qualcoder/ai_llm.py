# -*- coding: utf-8 -*-

"""
This file is part of QualCoder.

QualCoder is free software: you can redistribute it and/or modify it under the
terms of the GNU Lesser General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later version.

QualCoder is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public License along with QualCoder.
If not, see <https://www.gnu.org/licenses/>.

Author: Kai Droege (kaixxx)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
https://qualcoder.org/
"""

import asyncio
import configparser
import logging
from dataclasses import dataclass, field
from datetime import datetime
from logging.handlers import RotatingFileHandler
import os
import re
import threading
import time
import traceback
import uuid

from Bio.Align import PairwiseAligner
import httpx
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_community.cache import InMemoryCache  # Unused
from langchain_core.documents.base import Document  # Unused
from langchain_core.globals import set_llm_cache  # Unused
from langchain_core.messages.ai import AIMessage  # Unused
from langchain_core.messages.human import HumanMessage
from langchain_core.messages.system import SystemMessage
from langchain_core.runnables.config import RunnableConfig
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_openai.chat_models.codex import _ChatOpenAICodex
from langchain_openai.chatgpt_oauth import (
    _ChatGPTOAuthRefreshError,
    _FileChatGPTOAuthTokenProvider,
    login_chatgpt,
)
import json_repair
from openai import OpenAI, BadRequestError
from pydantic import ValidationError
from PyQt6 import QtCore
from PyQt6 import QtGui
from PyQt6 import QtWidgets
import qtawesome as qta

from .ai_agent_prompts import AiAgentPromptsCatalog, AgentPromptRecord
from .ai_async_worker import Worker
from .ai_vectorstore import AiVectorstore
from .confirm_delete import DialogConfirmDelete
from .error_dlg import qt_exception_hook
from .helpers import Message
from .html_parser import html_to_text
from .select_items import DialogSelectItems

max_memo_length = 1500  # Maximum length of the memo send to the AI

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

CHATGPT_OAUTH_API_BASE = 'ChatGPT_OAuth'
NO_API_KEY_NEEDED = '<no API key needed>'


class AICancelled(Exception):
    """Raised when one AI run was canceled cooperatively."""

    def __init__(self, run_id: str = ''):
        self.run_id = str(run_id).strip()
        super().__init__(self.run_id if self.run_id != '' else 'AI run canceled')


@dataclass
class AiRunContext:
    """Execution context for one AI run with isolated transport state."""

    run_id: str
    model_kind: str
    purpose: str
    scope_type: str = ''
    scope_id: object = None
    group_id: str = ''
    parent_run_id: str = ''
    cancel_result: object = None
    cancel_event: threading.Event = field(default_factory=threading.Event)
    http_client: object = None
    llm: object = None
    stream_iter: object = None
    streaming_output: str = ''
    status: str = 'queued'
    created_at: float = field(default_factory=time.time)
    finished_at: float = 0.0
    error_text: str = ''
    worker_type: str = ''
    provider: str = ''
        

class MyCustomSyncHandler(BaseCallbackHandler):
    def __init__(self, ai_llm):
        self.ai_llm = ai_llm
        
    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.ai_llm.run_progress_count += 1
    

def extract_ai_memo(memo: str) -> str:
    """In any memo, any text after the mark '#####' are considered as personal notes that will not be send to the AI.
    This function extracts the text before this mark (or all text if no marking is found) 

    Args:
        memo (str): memo text

    Returns:
        str: shortened memo for AI
    """
    mark = memo.find('#####')
    if mark > -1:
        return memo[0:mark]
    else:
        return memo


def is_chatgpt_oauth_api_base(api_base: str) -> bool:
    """Return whether the api_base marker selects ChatGPT OAuth auth."""

    return str(api_base).strip() == CHATGPT_OAUTH_API_BASE


def is_chatgpt_oauth_profile(model: dict | None) -> bool:
    """Return whether the AI profile uses ChatGPT OAuth authentication."""

    if model is None:
        return False
    return is_chatgpt_oauth_api_base(model.get('api_base', ''))


def ensure_chatgpt_oauth_profile_defaults(model: dict | None) -> None:
    """Normalize a ChatGPT OAuth profile in-place."""

    if not is_chatgpt_oauth_profile(model):
        return
    model['api_key'] = NO_API_KEY_NEEDED


def _chatgpt_oauth_provider(timeout: float = 5.0) -> _FileChatGPTOAuthTokenProvider:
    """Return the default ChatGPT OAuth token provider."""

    return _FileChatGPTOAuthTokenProvider(timeout=timeout)


def _format_chatgpt_oauth_token_status(token) -> str:
    """Format one human-readable ChatGPT OAuth status line."""

    details = []
    plan_type = str(getattr(token, 'plan_type', '')).strip()
    if plan_type != '':
        details.append(plan_type)
    expires_at = getattr(token, 'expires_at', None)
    if expires_at is not None:
        try:
            expires_text = expires_at.astimezone().strftime('%Y-%m-%d %H:%M')
        except Exception:
            expires_text = str(expires_at)
        details.append(_('expires ') + expires_text)
    if len(details) == 0:
        return _('Authenticated')
    return _('Authenticated') + ' (' + ', '.join(details) + ')'


def get_chatgpt_oauth_status(timeout: float = 5.0) -> tuple[bool, str]:
    """Return current ChatGPT OAuth status for the default token store."""

    try:
        token = _chatgpt_oauth_provider(timeout=timeout).get_token()
        return True, _format_chatgpt_oauth_token_status(token)
    except FileNotFoundError:
        return False, _('Not authenticated')
    except _ChatGPTOAuthRefreshError:
        return False, _('Authentication expired. Please renew it.')
    except Exception as err:
        return False, _('Authentication error') + ': ' + str(err)


def renew_chatgpt_oauth(timeout: float = 300.0) -> tuple[bool, str]:
    """Start or renew ChatGPT OAuth authentication."""

    try:
        login_chatgpt(timeout=timeout)
    except Exception as err:
        return False, _('Authentication error') + ': ' + str(err)
    return get_chatgpt_oauth_status()


def _chatgpt_oauth_reauth_message() -> str:
    """Return a user-facing re-authentication instruction."""

    return _('ChatGPT authentication expired or could not be renewed. '
             'Open the settings dialog and click "Renew" to authenticate again.')


def get_available_models(app, api_base: str, api_key: str) -> list:
    """Queries the API and returns a list of all AI models available from this provider."""
    if is_chatgpt_oauth_api_base(api_base):
        return []
    msg = None
    if app is not None:
        msg = Message(app, _('AI Models'), _('Loading list of available AI models...'))
        msg.setStandardButtons(QtWidgets.QMessageBox.StandardButton.NoButton)
        msg.show()
        QtWidgets.QApplication.processEvents()
    try:        
        if api_base == '':
            api_base = None
        client = OpenAI(api_key=api_key, base_url=api_base)
        response = client.models.list(timeout=4.0)
        model_dict = response.model_dump().get('data', [])
        model_list = sorted([model['id'] for model in model_dict])
    finally:
        if msg is not None:
            msg.deleteLater()
    return model_list

def get_default_ai_models():
    ini_string = """
[ai_model_OpenAI GPT5.5 reasoning]
desc = Powerful model from OpenAI, with internal reasoning, for complex tasks.
	You need an API-key from OpenAI and have paid for credits in your account.
	OpenAI will charge a small amount for every use.
access_info_url = https://platform.openai.com/api-keys
large_model = gpt-5.5
large_model_context_window = 272000
fast_model = gpt-5.4-mini
fast_model_context_window = 400000
reasoning_effort = medium
api_base = 
api_key = 

[ai_model_OpenAI GPT5.5 no reasoning]
desc = Powerful model from OpenAI, no reasoning, faster and cheaper.
	You need an API-key from OpenAI and have paid for credits in your account.
	OpenAI will charge a small amount for every use.
access_info_url = https://platform.openai.com/api-keys
large_model = gpt-5.5
large_model_context_window = 272000
fast_model = gpt-5.4-mini
fast_model_context_window = 400000
reasoning_effort = low
api_base = 
api_key = 

[ai_model_OpenAI ChatGPT Login]
desc = Lets you use your ChatGPT Plus, Pro, or Team account with QualCoder.
	No API key is needed, so no extra cost. Use the authentication controls 
    in the settings dialog. Note that this is experimental, availability 
    may vary. 
access_info_url = https://chatgpt.com/
large_model = gpt-5.5
large_model_context_window = 272000
fast_model = gpt-5.5
fast_model_context_window = 272000
reasoning_effort = medium
api_base = ChatGPT_OAuth
api_key = <no API key needed>

[ai_model_Blablador]
desc = Free and open source models, excellent privacy, but not as powerful 
	as the commercial offerings. Blablador runs on a server of the Helmholtz 
	Society, a large non-profit research organization in Germany. To gain 
	access and get an API-key, you have to identify yourself once with your
	university, ORCID, GitHub, or Google account.
access_info_url = https://sdlaml.pages.jsc.fz-juelich.de/ai/guides/blablador_api_access/
large_model = alias-large
large_model_context_window = 128000
fast_model = alias-fast
fast_model_context_window = 32000
reasoning_effort = default
api_base = https://api.helmholtz-blablador.fz-juelich.de/v1/
api_key = 

[ai_model_Blablador Huge]
desc = The largest and most powerful model currently running on Blablador. 
    Availability might change.
	Blablador is free to use and runs on a server of the Helmholtz Society,
	a large non-profit research organization in Germany. To gain
	access and get an API-key, you have to identify yourself once with your
	university, ORCID, GitHub, or Google account.
access_info_url = https://sdlaml.pages.jsc.fz-juelich.de/ai/guides/blablador_api_access/
large_model = alias-huge
large_model_context_window = 128000
fast_model = alias-fast
fast_model_context_window = 128000
reasoning_effort = default
api_base = https://api.helmholtz-blablador.fz-juelich.de/v1/
api_key = 

[ai_model_Anthropic Claude Opus 4.8]
desc = Claude is a family of high quality models from Anthropic.
	You need an API-key from Anthropic and credits in your account.
	Anthropic will charge a small amount for every use.
access_info_url = https://console.anthropic.com/settings/keys
large_model = claude-opus-4-8
large_model_context_window = 1000000
fast_model = claude-sonnet-5
fast_model_context_window = 1000000
reasoning_effort = medium
api_base = https://api.anthropic.com/v1/
api_key = 

[ai_model_Anthropic Claude Sonnet 5]
desc = Claude is a family of high quality models from Anthropic.
	You need an API-key from Anthropic and credits in your account.
	Anthropic will charge a small amount for every use.
access_info_url = https://console.anthropic.com/settings/keys
large_model = claude-sonnet-5
large_model_context_window = 1000000
fast_model = claude-sonnet-5
fast_model_context_window = 1000000
reasoning_effort = medium
api_base = https://api.anthropic.com/v1/
api_key = 

[ai_model_Google Gemini 3.5 Flash]
desc = Google offers several free and paid models on their servers.
	Select one in the Advanced AI options below.
	You need an API-key from Google.
access_info_url = https://ai.google.dev/gemini-api/docs
large_model = gemini-3.5-flash
large_model_context_window = 1000000
fast_model = gemini-3.1-flash-lite
fast_model_context_window = 1000000
reasoning_effort = default
api_base = https://generativelanguage.googleapis.com/v1beta/openai/
api_key = 

[ai_model_Deepseek Chat V3]
desc = Deepseek is a high quality Chinese chat model.
	You will need an an API-key from Deepseek and have payed credits in your account.
	Deepseek will charge a small amount for every use.
access_info_url = https://platform.deepseek.com/api_keys
large_model = deepseek-chat
large_model_context_window = 64000
fast_model = deepseek-chat
fast_model_context_window = 64000
reasoning_effort = default
api_base = https://api.deepseek.com
api_key = 

[ai_model_Mistral]
desc = Mistral AI offers high-performance, open-source and proprietary language models, 
    prioritizing transparency, privacy, and ethical AI for researchers and developers.
access_info_url = https://mistral.ai
large_model = mistral-large-latest
large_model_context_window = 128000
fast_model = mistral-small-latest
fast_model_context_window = 128000
reasoning_effort = default
api_base = https://api.mistral.ai/v1
api_key =

[ai_model_OpenRouter]
desc = OpenRouter is a unified interface to access many different AI language
	models, both free and paid. You need an API-key from OpenRouter.
	Select a model in the Advanced AI Options below.
access_info_url = https://openrouter.ai/
large_model = deepseek/deepseek-chat:free
large_model_context_window = 64000
fast_model = deepseek/deepseek-chat:free
fast_model_context_window = 64000
reasoning_effort = default
api_base = https://openrouter.ai/api/v1
api_key = 

[ai_model_Ollama local AI]
desc = Ollama is an open source server that lets you run LLMs locally on
	your computer. To use it in QualCoder, you must have Ollama set up and
	running first. Use the Advanced AI Options below to select between your
	locally installed models.
access_info_url = https://ollama.com
large_model = 
large_model_context_window = 32000
fast_model = 
fast_model_context_window = 32000
reasoning_effort = default
api_base = http://localhost:11434/v1/
api_key = <no API key needed>

    """
    
    config = configparser.ConfigParser()
    config.read_string(ini_string)
    ai_models = []
    for section in config.sections():
        if section.startswith('ai_model_'):
            model = {
                'name': section[9:],
                'desc': config[section].get('desc', ''),
                'access_info_url': config[section].get('access_info_url', ''),
                'large_model': config[section].get('large_model', ''),
                'large_model_context_window': config[section].get('large_model_context_window', '32768'),
                'fast_model': config[section].get('fast_model', ''),
                'fast_model_context_window': config[section].get('fast_model_context_window', '32768'),
                'reasoning_effort': config[section].get('reasoning_effort', ''),
                'api_base': config[section].get('api_base', ''),
                'api_key': config[section].get('api_key', '')
            }
            ai_models.append(model)
    return ai_models

def add_new_ai_model(current_models: list, new_name: str) -> tuple[list, int]:
    """Adds a new AI profile to the list, sets some default values,
    and returns the extended list as well as the index of the new model 

    Args:
        current_models (list): AI profiles
        new_name (str): the name for the new profile

    Returns:
        tuple[list, int]: extended list, index of new profile
    """
    new_model = {
        'name': new_name,
        'desc': '',
        'access_info_url': '',
        'large_model': '',
        'large_model_context_window': '32768',
        'fast_model': '',
        'fast_model_context_window': '32768',
        'reasoning_effort': 'default',
        'api_base': '',
        'api_key': ''
    }
    current_models.append(new_model)
    return current_models, len(current_models) - 1

def get_ai_profile_group_key(model: dict) -> str:
    """Return the group key for an AI profile based on the first word of its name."""

    name = str(model.get('name', '')).strip()
    if name == '':
        return ''
    return re.split(r'\s+', name, maxsplit=1)[0].lower()


def _find_first_ai_group_index(models: list, group_key: str) -> int:
    """Return the first list index that belongs to the requested profile group."""

    if group_key == '':
        return -1
    for idx, model in enumerate(models):
        if get_ai_profile_group_key(model) == group_key:
            return idx
    return -1


def _find_ai_model_index_by_name(models: list, model_name: str) -> int:
    """Return the list index for a named AI profile, or -1 if it is not found."""

    for idx, model in enumerate(models):
        if str(model.get('name', '')).strip() == model_name:
            return idx
    return -1


def _parse_seen_ai_model_upgrade_offers(settings: dict | None) -> set[str]:
    """Return the set of one-time model-upgrade prompts that were already shown."""

    if settings is None:
        return set()
    raw_value = str(settings.get('ai_model_upgrade_offers_seen', '')).strip()
    if raw_value == '':
        return set()
    return {item for item in raw_value.split('||') if item != ''}


def _store_seen_ai_model_upgrade_offers(settings: dict | None, seen_offers: set[str]) -> None:
    """Persist the set of one-time model-upgrade prompts in the settings dictionary."""

    if settings is None:
        return
    settings['ai_model_upgrade_offers_seen'] = '||'.join(sorted(seen_offers))


def _queue_ai_profile_upgrade_offer(current_models: list, current_model_name: str,
                                    suggested_model_name: str,
                                    settings: dict | None) -> dict | None:
    """Prepare one deferred upgrade offer for a newly added provider profile."""

    current_index = _find_ai_model_index_by_name(current_models, current_model_name)
    suggested_index = _find_ai_model_index_by_name(current_models, suggested_model_name)
    if current_index < 0 or suggested_index < 0 or current_index == suggested_index:
        return None

    seen_offers = _parse_seen_ai_model_upgrade_offers(settings)
    offer_key = str(suggested_model_name).strip()
    if offer_key == '' or offer_key in seen_offers:
        return None

    return {
        'current_model_name': str(current_model_name).strip(),
        'suggested_model_name': offer_key,
    }


def update_ai_models(current_models: list, current_model_index: int,
                     settings: dict | None = None) -> tuple[list, int, dict | None]:
    """Update the AI model definitions, and add new models from the default set

    Args:
        current_models (list): the current list from config.ini
        current_model_index (int): the index of the currently selected model
        settings (dict | None): config settings used for one-time upgrade prompts

    Returns:
        tuple[list, int, dict | None]: updated list, current model index, queued upgrade offer
    """
    if current_model_index < 0 or current_model_index > (len(current_models) - 1):
        current_model_index = 0

    current_model_name = str(current_models[current_model_index].get('name', '')).strip()
    current_group_key = get_ai_profile_group_key(current_models[current_model_index])

    # add new models from the default model list, keeping provider groups together
    default_models = get_default_ai_models()
    current_models_names = {model['name'] for model in current_models}
    missing_models_by_group = {}
    missing_group_order = []
    for model in default_models:
        if model['name'] not in current_models_names:
            group_key = get_ai_profile_group_key(model)
            if group_key not in missing_models_by_group:
                missing_models_by_group[group_key] = []
                missing_group_order.append(group_key)
            missing_models_by_group[group_key].append(model)
            current_models_names.add(model['name'])

    newest_inserted_by_group = {}
    for group_key in missing_group_order:
        group_models = missing_models_by_group.get(group_key, [])
        if len(group_models) == 0:
            continue
        insertion_index = _find_first_ai_group_index(current_models, group_key)
        if insertion_index < 0:
            insertion_index = len(current_models)
        for offset, model in enumerate(group_models):
            insert_at = insertion_index + offset
            current_models.insert(insert_at, model)
            if current_model_index >= insert_at:
                current_model_index += 1
        newest_inserted_by_group[group_key] = str(group_models[0].get('name', '')).strip()
                
    # Blablador: update config (api base, model alias)
    curr_model = current_models[current_model_index]
    if curr_model['api_base'] == 'https://helmholtz-blablador.fz-juelich.de:8000/v1' and curr_model['large_model'] != 'alias-large':
        msg = _('You are using the "Blablador" service on an old server that will soon be disabled. '
                'Your configuration will be updated automatically. Please test if the AI access still works as expected. '
                'You might need to change to a different AI model in the settings dialog under "Advanced AI Settings".')
        msg_box = QtWidgets.QMessageBox()
        msg_box.setWindowTitle(_('AI Setup'))
        msg_box.setText(msg)
        msg_box.exec()
    for model in current_models:
        if model['api_base'] == 'https://helmholtz-blablador.fz-juelich.de:8000/v1':
            model['api_base'] = 'https://api.helmholtz-blablador.fz-juelich.de/v1/'
        if model['large_model'] == 'alias-llama3-huge': # this alias is no longer available
            model['large_model'] = 'alias-huge'
        if model['fast_model'] == 'alias-llama3-huge':
            model['fast_model'] = 'alias-huge'
    
    # add parameter "reasoning_effort"    
    for model in current_models:
        if model['reasoning_effort'] == '':
            if model['large_model'].lower().find('gpt-5') > -1 or \
                    model['large_model'].lower().find('o4') > -1 or \
                    model['large_model'].lower().find('o3') > -1 or \
                    model['large_model'].lower().find('o1') > -1 or \
                    model['large_model'].lower().find('gpt-oss') > -1 or \
                    model['large_model'].lower().find('qwen3') > -1 or \
                    model['large_model'].lower().find('opus') > -1 or \
                    model['large_model'].lower().find('sonnet') > -1 or \
                    model['large_model'].lower().find('grok-4') > -1:
                model['reasoning_effort'] = 'medium'
            else:
                model['reasoning_effort'] = 'default'
    
        # Correct an error in the QualCoder 3.8 release, where reasoning effort was set to medium for GPT-4.1:            
        if model['large_model'].lower().find('gpt-4.1') > -1: 
            model['reasoning_effort'] = 'default'

    pending_upgrade_offer = None
    suggested_model_name = newest_inserted_by_group.get(current_group_key, '')
    if current_model_name != '' and suggested_model_name != '':
        pending_upgrade_offer = _queue_ai_profile_upgrade_offer(
            current_models, current_model_name, suggested_model_name, settings
        )
    
    return current_models, current_model_index, pending_upgrade_offer

def strip_think_blocks(text: str) -> str:
    """
    Removes <think>...</think> blocks from an LLM response.
    If the closing </think> is missing (e.g., during streaming),
    removes everything from <think> to the end of the text.
    """
    # Case 1: Remove complete <think>...</think> blocks
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    # Case 2: Remove unfinished <think> blocks (no closing tag yet)
    text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL)

    return text.strip()


def llm_content_to_text(content) -> str:
    """Convert LLM content payloads into plain text.

    LangChain providers usually return a string in `AIMessage.content`, but
    Responses-API based models can return a list of content blocks instead.
    This helper flattens the common text-bearing block shapes that QualCoder
    needs for logging and JSON parsing.
    """

    if content is None:
        return ''
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            text = llm_content_to_text(item)
            if text != '':
                parts.append(text)
        return "\n".join(parts)
    if isinstance(content, dict):
        for key in ('text', 'output_text'):
            value = content.get(key, None)
            if isinstance(value, str):
                return value
        value = content.get('content', None)
        if value is not None:
            return llm_content_to_text(value)
        return ''
    return str(content)

def ai_quote_search(quote: str, original: str) -> tuple[int, int]:
    """Searches the quote in the original text using the Smith-Waterman algorithm.
    This also tolerates gaps up to complete sentences in the cited text or other 
    minor differences in the exact wording.
    The "PairwiseAligner" is normally used to find partial overlaps in DNA-strings.
    Returns -1, -1 if no match is found.
    """
    
    # try finding an exact match first
    start_idx = original.find(quote)
    if start_idx > -1:
        return start_idx, start_idx + len(quote)
    
    # no exact match found, use the PairwiseAligner to find also partial matches
    aligner = PairwiseAligner()
    aligner.mode = 'local'
    aligner.match_score = 2         # score for each matched char
    aligner.mismatch_score = -1     # penalty for mismatched chars (errors)
    aligner.open_gap_score = -0.5   # penalty for opening a gap (left out chars)
    aligner.extend_gap_score = -0.1 # penalty for gap continuation

    alignments = aligner.align(original.lower(), quote.lower())
    try:
        best = next(alignments)
    except StopIteration: 
        # No alignments were found
        return -1, -1
    except Exception as e:
        # any other error (could be a memory issue)
        logger.error(e)
        return -1, -1

    orig_spans = best.aligned[0]
    if not len(orig_spans):
        return -1, -1

    # combine all matched blocks from the first start to the last end:
    start_idx = int(orig_spans[0][0])
    end_idx = int(orig_spans[-1][1])
        
    # only accept a match if it reaches 80% of the max score -> prevents false positives
    max_score = len(quote) * aligner.match_score
    score_fraction = best.score / max_score
    if score_fraction > 0.8:
        return start_idx, end_idx
    else:
        return -1, -1

class AiLLM():
    """ This manages the communication between qualcoder, the vectorstore 
    and the LLM (large language model, e.g. GPT-4)."""
    app = None
    parent_text_edit = None
    main_window = None
    threadpool: QtCore.QThreadPool = None
    run_progress_msg = ''
    run_progress_count = -1
    run_progress_max = -1
    _status = ''   
    large_llm_context_window = 128000
    fast_llm_context_window = 16385
    sources_collection = 'qualcoder'  # name of the vectorstore collection for source documents
    ai_log_logger = None
    ai_log_handler = None
    ai_log_path = ''
    ai_log_seq = 0
    ai_change_history = None
    
    def __init__(self, app, parent_text_edit):
        self.app = app
        self.parent_text_edit = parent_text_edit
        self.threadpool = QtCore.QThreadPool()
        self.threadpool.setMaxThreadCount(2)
        self.sources_vectorstore = AiVectorstore(self.app, self.parent_text_edit, self.sources_collection)
        self.ai_change_history = []  # Session-scoped AI write operations for undo
        self._runs_lock = threading.RLock()
        self._runs_by_id = {}
        self._latest_run_by_scope = {}
        self._last_status_by_scope = {}
        self._last_streaming_output_by_run = {}
        self._llm_run_local = threading.local()
        self._large_llm_params = None
        self._fast_llm_params = None
        self._large_llm_factory = None
        self._fast_llm_factory = None
        self._large_reasoning_effort = ''
        self._fast_reasoning_effort = ''
        self._unsupported_llm_params_lock = threading.RLock()
        self._unsupported_llm_params_by_key = {}

    def _ai_log_target_path(self) -> str:
        """Return the file path for the dedicated AI communication log."""

        confighome = str(getattr(self.app, 'confighome', '')).strip()
        if confighome != '':
            log_dir = confighome
        else:
            log_dir = os.path.expanduser('~')
        return os.path.join(log_dir, 'ai.log')

    def _is_ai_extended_logging_enabled(self) -> bool:
        """Return whether verbose AI request logging is enabled in config.ini."""

        value = self.app.settings.get('ai_extended_logging', 'False')
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() == 'true'

    def _close_ai_log_handler(self):
        """Detach and close the dedicated AI log handler, if any."""

        if self.ai_log_logger is None:
            self.ai_log_logger = logging.getLogger('qualcoder.ai_log')
            self.ai_log_logger.setLevel(logging.INFO)
            self.ai_log_logger.propagate = False
        for stale_handler in list(self.ai_log_logger.handlers):
            try:
                self.ai_log_logger.removeHandler(stale_handler)
            except Exception:
                pass
            try:
                stale_handler.close()
            except Exception:
                pass
        self.ai_log_handler = None
        self.ai_log_path = ''

    def _ensure_ai_log_logger(self):
        """Set up or refresh the dedicated rotating AI logger."""

        if not self._is_ai_extended_logging_enabled():
            self._close_ai_log_handler()
            return False

        if self.ai_log_logger is None:
            self.ai_log_logger = logging.getLogger('qualcoder.ai_log')
            self.ai_log_logger.setLevel(logging.INFO)
            self.ai_log_logger.propagate = False
        if self.ai_log_handler is None and len(self.ai_log_logger.handlers) > 0:
            # Cleanup stale handlers from previous AiLLM instances in the same process.
            for stale_handler in list(self.ai_log_logger.handlers):
                try:
                    self.ai_log_logger.removeHandler(stale_handler)
                except Exception:
                    pass
                try:
                    stale_handler.close()
                except Exception:
                    pass

        desired_path = self._ai_log_target_path()
        if self.ai_log_handler is not None and self.ai_log_path == desired_path:
            return

        if self.ai_log_handler is not None:
            try:
                self.ai_log_logger.removeHandler(self.ai_log_handler)
            except Exception:
                pass
            try:
                self.ai_log_handler.close()
            except Exception:
                pass
            self.ai_log_handler = None

        os.makedirs(os.path.dirname(desired_path), exist_ok=True)
        handler = RotatingFileHandler(
            desired_path,
            maxBytes=500000,
            backupCount=2,
            encoding='utf-8',
        )
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
        self.ai_log_logger.addHandler(handler)
        self.ai_log_handler = handler
        self.ai_log_path = desired_path
        return True

    def _next_ai_log_id(self) -> int:
        self.ai_log_seq += 1
        return self.ai_log_seq

    def _llm_name_for_log(self, llm) -> str:
        for attr in ('model_name', 'model', 'deployment_name', 'azure_deployment'):
            try:
                value = str(getattr(llm, attr, '')).strip()
            except Exception:
                value = ''
            if value != '':
                return value
        model_idx = int(self.app.settings.get('ai_model_index', '-1'))
        if 0 <= model_idx < len(self.app.ai_models):
            return str(self.app.ai_models[model_idx].get('name', '')).strip()
        return 'unknown'

    def _llm_provider_name(self, factory) -> str:
        if factory is AzureChatOpenAI:
            return 'azure'
        if factory is _ChatOpenAICodex:
            return 'chatgpt_oauth'
        return 'openai'

    def _llm_setup_for_kind(self, model_kind: str):
        normalized_kind = 'fast' if str(model_kind).strip().lower() == 'fast' else 'large'
        if normalized_kind == 'fast':
            return normalized_kind, self._fast_llm_params, self._fast_llm_factory
        return normalized_kind, self._large_llm_params, self._large_llm_factory

    def _llm_profile_key(self, factory, base_params: dict | None) -> tuple[str, str, str]:
        if base_params is None:
            return self._llm_provider_name(factory), '', ''
        model_name = str(
            base_params.get('model', '') or
            base_params.get('azure_deployment', '') or
            base_params.get('deployment_name', '')
        ).strip().lower()
        endpoint = str(
            base_params.get('openai_api_base', '') or
            base_params.get('azure_endpoint', '')
        ).strip().lower()
        return self._llm_provider_name(factory), endpoint, model_name

    def _filtered_llm_base_params(self, factory, base_params: dict | None) -> dict:
        if base_params is None:
            return {}
        filtered_params = dict(base_params)
        key = self._llm_profile_key(factory, base_params)
        with self._unsupported_llm_params_lock:
            unsupported_params = set(self._unsupported_llm_params_by_key.get(key, set()))
        for param_name in unsupported_params:
            filtered_params.pop(param_name, None)
        return filtered_params

    def _remember_unsupported_llm_param(self, factory, base_params: dict | None, param_name: str) -> bool:
        normalized_name = str(param_name).strip()
        if normalized_name == '' or base_params is None:
            return False
        key = self._llm_profile_key(factory, base_params)
        with self._unsupported_llm_params_lock:
            known_params = set(self._unsupported_llm_params_by_key.get(key, set()))
            was_new = normalized_name not in known_params
            known_params.add(normalized_name)
            self._unsupported_llm_params_by_key[key] = known_params
        return was_new

    def _close_http_client(self, client) -> None:
        if client is None:
            return
        try:
            client.close()
        except Exception:
            pass

    def _build_llm_for_run(self, factory, base_params: dict | None, model_kind: str, purpose: str):
        timeout_obj = self._run_timeout(model_kind, purpose)
        http_client = httpx.Client(timeout=timeout_obj)
        llm_params = self._filtered_llm_base_params(factory, base_params)
        llm_params['timeout'] = timeout_obj
        llm_params['http_client'] = http_client
        llm = factory(**llm_params)
        return llm, http_client

    def _unsupported_param_from_message(self, message_text: str) -> str:
        text = str(message_text).strip()
        if text == '':
            return ''
        patterns = (
            r"Unsupported parameter:\s*['\"]([^'\"]+)['\"]",
            r"Unsupported parameter:\s*([A-Za-z0-9_.-]+)",
            r"Parameter\s+['\"]([^'\"]+)['\"]\s+is\s+not\s+supported",
            r"['\"]([^'\"]+)['\"]\s+is\s+not\s+supported\s+with\s+this\s+model",
        )
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match is not None:
                return str(match.group(1)).strip()
        return ''

    def _unsupported_param_from_error(self, err: BaseException) -> str:
        for item in self._exception_chain(err):
            param_name = str(getattr(item, 'param', '')).strip()
            if param_name != '':
                return param_name
            body = getattr(item, 'body', None)
            if isinstance(body, dict):
                error_payload = body.get('error', body)
                if isinstance(error_payload, dict):
                    param_name = str(error_payload.get('param', '')).strip()
                    if param_name != '':
                        return param_name
                    for key in ('message', 'detail'):
                        message_text = self._safe_to_text(error_payload.get(key, ''))
                        param_name = self._unsupported_param_from_message(message_text)
                        if param_name != '':
                            return param_name
            elif body is not None:
                param_name = self._unsupported_param_from_message(self._safe_to_text(body))
                if param_name != '':
                    return param_name
            for attr_name in ('message', 'detail'):
                attr_value = getattr(item, attr_name, None)
                if attr_value is None:
                    continue
                param_name = self._unsupported_param_from_message(self._safe_to_text(attr_value))
                if param_name != '':
                    return param_name
            param_name = self._unsupported_param_from_message(self._safe_to_text(item))
            if param_name != '':
                return param_name
        return ''

    def log_llm_retry(self, req_id: int, llm, param_name: str, source: str, context: str = ''):
        """Log one automatic retry triggered by an unsupported parameter error."""

        model_name = self._llm_name_for_log(llm)
        line = f'[#{req_id}] RETRY model="{model_name}"'
        if context.strip() != '':
            line += f' context="{context.strip()}"'
        line += f' unsupported_parameter="{str(param_name).strip()}" source="{str(source).strip()}"'
        self._write_ai_log(line)

    def _message_role_and_text_for_log(self, msg) -> tuple[str, str]:
        if isinstance(msg, SystemMessage):
            return 'system', str(msg.content)
        if isinstance(msg, HumanMessage):
            return 'user', str(msg.content)
        if isinstance(msg, AIMessage):
            return 'assistant', str(msg.content)
        if isinstance(msg, dict):
            role = str(msg.get('role', 'message')).strip() or 'message'
            content = msg.get('content', '')
            return role, str(content)
        if hasattr(msg, 'content'):
            role = msg.__class__.__name__.replace('Message', '').lower() or 'message'
            return role, str(getattr(msg, 'content', ''))
        if isinstance(msg, str):
            return 'message', msg
        return 'message', str(msg)

    def _safe_to_text(self, value: object) -> str:
        """Best-effort conversion that never raises during error handling/logging."""

        try:
            return str(value)
        except Exception:
            try:
                return repr(value)
            except Exception:
                return '<unprintable>'

    def _chatgpt_oauth_user_error(self, err: BaseException) -> str:
        """Return a friendly ChatGPT OAuth re-auth message, if applicable."""

        for item in self._exception_chain(err):
            if isinstance(item, _ChatGPTOAuthRefreshError):
                return _chatgpt_oauth_reauth_message()
            if isinstance(item, FileNotFoundError):
                item_text = self._safe_to_text(item)
                if 'ChatGPT OAuth token' in item_text or 'login_chatgpt()' in item_text:
                    return _chatgpt_oauth_reauth_message()
        return ''

    def _write_ai_log(self, text: str):
        if not self._ensure_ai_log_logger():
            return
        self.ai_log_logger.info(text)

    def log_llm_request(self, llm, messages, context: str = '') -> int:
        """Log one outgoing LLM request with readable message contents."""

        req_id = self._next_ai_log_id()
        model_name = self._llm_name_for_log(llm)
        header = f'[#{req_id}] REQUEST model="{model_name}"'
        if context.strip() != '':
            header += f' context="{context.strip()}"'
        lines = [header]

        if isinstance(messages, (list, tuple)):
            msg_list = list(messages)
        else:
            msg_list = [messages]
        for idx, msg in enumerate(msg_list, start=1):
            role, content = self._message_role_and_text_for_log(msg)
            lines.append(f'[{idx}] {role}:')
            content_lines = str(content).splitlines()
            if len(content_lines) == 0:
                lines.append('  ')
            else:
                for line in content_lines:
                    lines.append('  ' + line)
        self._write_ai_log('\n'.join(lines))
        return req_id

    def log_llm_response(self, req_id: int, llm, response_text, context: str = ''):
        """Log one final incoming LLM response."""

        model_name = self._llm_name_for_log(llm)
        header = f'[#{req_id}] RESPONSE model="{model_name}"'
        if context.strip() != '':
            header += f' context="{context.strip()}"'
        lines = [header, 'assistant:']
        response_body = llm_content_to_text(response_text)
        for line in self._safe_to_text(response_body).splitlines():
            lines.append('  ' + line)
        if len(lines) == 2:
            lines.append('  ')
        self._write_ai_log('\n'.join(lines))

    def log_llm_error(self, req_id: int, llm, err: Exception, context: str = ''):
        """Log one LLM error for traceability."""

        model_name = self._llm_name_for_log(llm)
        error_text = self._safe_to_text(err)
        line = f'[#{req_id}] ERROR model="{model_name}"'
        if context.strip() != '':
            line += f' context="{context.strip()}"'
        line += f' {err.__class__.__name__}: {error_text}'
        self._write_ai_log(line)

    def _exception_chain(self, err: BaseException):
        seen = set()
        current = err
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            yield current
            current = getattr(current, '__cause__', None) or getattr(current, '__context__', None)

    def _is_timeout_exception(self, err: BaseException) -> bool:
        for item in self._exception_chain(err):
            if isinstance(item, (TimeoutError, httpx.TimeoutException)):
                return True
            class_name = item.__class__.__name__.lower()
            if 'timeout' in class_name or 'timedout' in class_name:
                return True
        return False

    def _is_stream_interruption_exception(self, err: BaseException) -> bool:
        for item in self._exception_chain(err):
            if isinstance(item, (TimeoutError, httpx.TransportError)):
                return True
            class_name = item.__class__.__name__.lower()
            if any(
                marker in class_name
                for marker in (
                    'timeout',
                    'timedout',
                    'connection',
                    'connect',
                    'network',
                    'readerror',
                    'remoteprotocol',
                    'protocolerror',
                    'transport',
                )
            ):
                return True
        return False

    def _allow_partial_stream_result_after_error(self, err: BaseException) -> bool:
        """Return whether a partial stream can be treated as usable despite an error."""

        # Transport interruptions mean the stream ended before the provider signaled completion.
        # Returning accumulated text as a normal result would persist a truncated
        # answer without showing the user that generation failed.
        if self._is_stream_interruption_exception(err):
            return False
        return True

    def _next_run_id(self) -> str:
        return "ai-run-" + uuid.uuid4().hex

    def _scope_key(self, scope_type: str, scope_id: object) -> tuple[str, str]:
        return str(scope_type).strip(), self._safe_to_text(scope_id)

    def _get_current_run_context(self):
        return getattr(self._llm_run_local, 'current_run_context', None)

    def _set_current_run_context(self, run_context):
        self._llm_run_local.current_run_context = run_context

    def _clear_current_run_context(self):
        if hasattr(self._llm_run_local, 'current_run_context'):
            self._llm_run_local.current_run_context = None

    def _reasoning_effort_for_kind(self, model_kind: str) -> str:
        if str(model_kind).strip().lower() == 'fast':
            return str(self._fast_reasoning_effort).strip().lower()
        return str(self._large_reasoning_effort).strip().lower()

    def _run_timeout(self, model_kind: str, purpose: str):
        base_timeout = float(self.app.settings.get('ai_timeout', '30.0'))
        reasoning = self._reasoning_effort_for_kind(model_kind)
        connect_timeout = min(10.0, max(3.0, base_timeout / 3.0))
        write_timeout = min(30.0, max(10.0, base_timeout))
        pool_timeout = min(15.0, max(5.0, base_timeout / 2.0))
        if str(purpose).strip() == 'stream':
            read_timeout = max(base_timeout, 60.0)
        else:
            read_timeout = max(base_timeout * 2.0, 90.0)
        reasoning_factors = {
            'low': 2.0,
            'medium': 3.0,
            'high': 4.0,
        }
        if reasoning in reasoning_factors:
            read_timeout = max(read_timeout, reasoning_factors[reasoning] * base_timeout)
        return httpx.Timeout(
            connect=connect_timeout,
            read=read_timeout,
            write=write_timeout,
            pool=pool_timeout,
        )

    def _rebuild_run_context_without_param(self, run_context: AiRunContext, param_name: str) -> bool:
        normalized_kind, base_params, factory = self._llm_setup_for_kind(run_context.model_kind)
        normalized_name = str(param_name).strip()
        if base_params is None or factory is None or normalized_name == '':
            return False
        if normalized_name not in base_params:
            return False
        self._remember_unsupported_llm_param(factory, base_params, normalized_name)
        old_client = getattr(run_context, 'http_client', None)
        llm, http_client = self._build_llm_for_run(
            factory,
            base_params,
            normalized_kind,
            str(getattr(run_context, 'purpose', '')).strip(),
        )
        run_context.llm = llm
        run_context.http_client = http_client
        run_context.provider = self._llm_provider_name(factory)
        self._close_http_client(old_client)
        return True

    def _retry_after_unsupported_parameter_error(self, run_context: AiRunContext, invoke_kwargs: dict | None,
                                                 err: BaseException, attempted_params: set[str],
                                                 req_id: int, context: str = '') -> tuple[bool, dict | None]:
        param_name = self._unsupported_param_from_error(err)
        if param_name == '' or param_name in attempted_params:
            return False, invoke_kwargs

        if invoke_kwargs is not None and param_name in invoke_kwargs:
            retry_kwargs = dict(invoke_kwargs)
            retry_kwargs.pop(param_name, None)
            attempted_params.add(param_name)
            self.log_llm_retry(req_id, run_context.llm, param_name, source='invoke', context=context)
            return True, retry_kwargs

        if not self._rebuild_run_context_without_param(run_context, param_name):
            return False, invoke_kwargs

        attempted_params.add(param_name)
        self.log_llm_retry(req_id, run_context.llm, param_name, source='model', context=context)
        return True, invoke_kwargs

    def _invoke_with_unsupported_parameter_retry(self, run_context: AiRunContext, messages,
                                                 invoke_kwargs: dict | None, req_id: int,
                                                 context: str = ''):
        current_kwargs = {} if invoke_kwargs is None else dict(invoke_kwargs)
        attempted_params = set()
        while True:
            self._raise_if_run_canceled(run_context)
            try:
                return run_context.llm.invoke(messages, **current_kwargs)
            except Exception as err:
                retried, current_kwargs = self._retry_after_unsupported_parameter_error(
                    run_context,
                    current_kwargs,
                    err,
                    attempted_params,
                    req_id,
                    context=context,
                )
                if retried:
                    continue
                raise

    def _create_run_context(self, model_kind: str = 'large', purpose: str = '',
                            scope_type: str = '', scope_id=None, group_id: str = '',
                            parent_run_id: str = '', cancel_result=None) -> AiRunContext:
        normalized_kind, base_params, factory = self._llm_setup_for_kind(model_kind)
        if base_params is None or factory is None:
            raise RuntimeError('AI model configuration is not initialized.')

        llm, http_client = self._build_llm_for_run(factory, base_params, normalized_kind, purpose)

        return AiRunContext(
            run_id=self._next_run_id(),
            model_kind=normalized_kind,
            purpose=str(purpose).strip(),
            scope_type=str(scope_type).strip(),
            scope_id=scope_id,
            group_id=str(group_id).strip(),
            parent_run_id=str(parent_run_id).strip(),
            cancel_result=cancel_result,
            http_client=http_client,
            llm=llm,
            provider=self._llm_provider_name(factory),
        )

    def _register_run_context(self, run_context: AiRunContext):
        with self._runs_lock:
            self._runs_by_id[run_context.run_id] = run_context
            scope_type = str(run_context.scope_type).strip()
            if scope_type != '':
                scope_key = self._scope_key(scope_type, run_context.scope_id)
                self._latest_run_by_scope[scope_key] = run_context.run_id
                self._last_status_by_scope[scope_key] = 'queued'
        return run_context.run_id

    def _update_run_status(self, run_id: str, status: str, error_text: str = ''):
        with self._runs_lock:
            run_context = self._runs_by_id.get(str(run_id).strip())
            if run_context is None:
                return
            run_context.status = str(status).strip()
            if error_text != '':
                run_context.error_text = str(error_text)
            scope_type = str(run_context.scope_type).strip()
            if scope_type != '':
                self._last_status_by_scope[self._scope_key(scope_type, run_context.scope_id)] = run_context.status

    def get_streaming_output(self, run_id: str = '') -> str:
        normalized = str(run_id).strip()
        if normalized == '':
            return ''
        with self._runs_lock:
            run_context = self._runs_by_id.get(normalized)
            if run_context is not None:
                return str(getattr(run_context, 'streaming_output', ''))
            return str(self._last_streaming_output_by_run.get(normalized, ''))

    def clear_streaming_output(self, run_id: str = ''):
        normalized = str(run_id).strip()
        with self._runs_lock:
            if normalized == '':
                for run_context in self._runs_by_id.values():
                    run_context.streaming_output = ''
                self._last_streaming_output_by_run.clear()
            else:
                run_context = self._runs_by_id.get(normalized)
                if run_context is not None:
                    run_context.streaming_output = ''
                self._last_streaming_output_by_run.pop(normalized, None)

    def _finalize_run_context(self, run_context: AiRunContext, terminal_status: str = ''):
        if run_context is None:
            return
        with self._runs_lock:
            current = self._runs_by_id.get(run_context.run_id)
            current = run_context if current is None else current
            streaming_output = str(getattr(current, 'streaming_output', ''))
            if streaming_output != '':
                self._last_streaming_output_by_run[current.run_id] = streaming_output
                while len(self._last_streaming_output_by_run) > 20:
                    self._last_streaming_output_by_run.pop(next(iter(self._last_streaming_output_by_run)), None)
            if terminal_status != '':
                current.status = terminal_status
            if current.status not in ('finished', 'errored', 'canceled'):
                current.status = 'canceled' if current.cancel_event.is_set() else 'finished'
            current.finished_at = time.time()
            if run_context.run_id in self._runs_by_id:
                scope_type = str(current.scope_type).strip()
                if scope_type != '':
                    scope_key = self._scope_key(scope_type, current.scope_id)
                    self._last_status_by_scope[scope_key] = current.status
                    if self._latest_run_by_scope.get(scope_key) == current.run_id:
                        self._latest_run_by_scope.pop(scope_key, None)
                self._runs_by_id.pop(current.run_id, None)

        stream_iter = getattr(run_context, 'stream_iter', None)
        if stream_iter is not None:
            close_fn = getattr(stream_iter, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    pass
        client = getattr(run_context, 'http_client', None)
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        run_context.stream_iter = None

    def _active_run_count(self) -> int:
        with self._runs_lock:
            return sum(
                1 for ctx in self._runs_by_id.values()
                if str(ctx.status).strip() not in ('finished', 'errored', 'canceled')
            )

    def _has_blocking_active_runs(self) -> bool:
        """Return whether any user-blocking AI run is still active."""

        non_blocking_scopes = {'chat_title'}
        with self._runs_lock:
            for ctx in self._runs_by_id.values():
                if str(ctx.status).strip() in ('finished', 'errored', 'canceled'):
                    continue
                if str(ctx.scope_type).strip() in non_blocking_scopes:
                    continue
                return True
        return False

    def _request_cancel_run(self, run_context: AiRunContext) -> bool:
        if run_context is None:
            return False
        was_queued = str(run_context.status).strip() == 'queued'
        run_context.cancel_event.set()
        self._update_run_status(run_context.run_id, 'cancel_requested')
        stream_iter = getattr(run_context, 'stream_iter', None)
        if stream_iter is not None:
            close_fn = getattr(stream_iter, 'close', None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    pass
        client = getattr(run_context, 'http_client', None)
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        if was_queued:
            self._finalize_run_context(run_context, 'canceled')
        return True

    def _request_cancel_all_runs(self) -> int:
        with self._runs_lock:
            run_contexts = list(self._runs_by_id.values())
        canceled_count = 0
        for run_context in run_contexts:
            if self._request_cancel_run(run_context):
                canceled_count += 1
        return canceled_count

    def cancel_run(self, run_id: str, wait_ms: int = 5000) -> bool:
        normalized = str(run_id).strip()
        if normalized == '':
            return True
        with self._runs_lock:
            run_context = self._runs_by_id.get(normalized)
        if run_context is None:
            return True
        self._request_cancel_run(run_context)
        deadline = time.time() + (max(0, int(wait_ms)) / 1000.0)
        while time.time() < deadline:
            with self._runs_lock:
                if normalized not in self._runs_by_id:
                    return True
            time.sleep(0.05)
        return False

    def cancel_scope(self, scope_type: str, scope_id=None, wait_ms: int = 5000) -> bool:
        scope_key = self._scope_key(scope_type, scope_id)
        with self._runs_lock:
            target_ids = [
                run_id for run_id, ctx in self._runs_by_id.items()
                if self._scope_key(ctx.scope_type, ctx.scope_id) == scope_key
            ]
        ok = True
        for run_id in target_ids:
            if not self.cancel_run(run_id, wait_ms=wait_ms):
                ok = False
        return ok

    def cancel_all_runs(self, wait_ms: int = 5000) -> bool:
        self.threadpool.clear()
        with self._runs_lock:
            target_ids = list(self._runs_by_id.keys())
        ok = True
        for run_id in target_ids:
            if not self.cancel_run(run_id, wait_ms=wait_ms):
                ok = False
        return ok

    def _raise_if_run_canceled(self, run_context=None):
        ctx = run_context if run_context is not None else self._get_current_run_context()
        if ctx is not None and ctx.cancel_event.is_set():
            raise AICancelled(ctx.run_id)

    def is_current_run_canceled(self) -> bool:
        ctx = self._get_current_run_context()
        return ctx is not None and ctx.cancel_event.is_set()

    def has_active_runs(self, scope_type: str = '', scope_id=None) -> bool:
        with self._runs_lock:
            if str(scope_type).strip() == '':
                return any(
                    str(ctx.status).strip() not in ('finished', 'errored', 'canceled')
                    for ctx in self._runs_by_id.values()
                )
            scope_key = self._scope_key(scope_type, scope_id)
            return any(
                self._scope_key(ctx.scope_type, ctx.scope_id) == scope_key and
                str(ctx.status).strip() not in ('finished', 'errored', 'canceled')
                for ctx in self._runs_by_id.values()
            )

    def get_scope_status(self, scope_type: str, scope_id=None) -> str:
        scope_key = self._scope_key(scope_type, scope_id)
        with self._runs_lock:
            for ctx in self._runs_by_id.values():
                if self._scope_key(ctx.scope_type, ctx.scope_id) != scope_key:
                    continue
                status = str(ctx.status).strip()
                if status != '':
                    return status
            return str(self._last_status_by_scope.get(scope_key, 'idle')).strip() or 'idle'

    def invoke_with_logging(self, messages, response_format=None, config=None, context: str = '',
                            fallback_without_response_format: bool = False,
                            fallback_exceptions=(Exception,), run_context=None,
                            model_kind: str = 'large'):
        """Invoke an LLM and log request/response in the dedicated AI log."""

        temp_context = None
        current_context = run_context if run_context is not None else self._get_current_run_context()
        if current_context is None:
            temp_context = self._create_run_context(
                model_kind=model_kind,
                purpose='invoke',
            )
            current_context = temp_context
        active_llm = current_context.llm

        req_id = self.log_llm_request(active_llm, messages, context=context)
        try:
            self._raise_if_run_canceled(current_context)
            invoke_kwargs = {}
            if response_format is not None:
                invoke_kwargs['response_format'] = response_format
            if config is not None:
                invoke_kwargs['config'] = config
            res = self._invoke_with_unsupported_parameter_retry(
                current_context,
                messages,
                invoke_kwargs,
                req_id,
                context=context,
            )
            active_llm = current_context.llm
            self._raise_if_run_canceled(current_context)
        except Exception as err:
            if isinstance(err, AICancelled):
                raise
            if current_context.cancel_event.is_set():
                raise AICancelled(current_context.run_id)
            active_llm = current_context.llm
            if str(current_context.model_kind).strip().lower() == 'fast':
                self.log_llm_error(req_id, active_llm, err, context=f'{context}_fast_primary_error')
            try:
                res = self._invoke_with_large_model_fallback(messages, invoke_kwargs, context, current_context)
                if res is not None:
                    return res
            except AICancelled:
                raise
            except Exception:
                pass
            may_fallback = (
                fallback_without_response_format
                and response_format is not None
                and isinstance(err, fallback_exceptions)
            )
            if not may_fallback:
                self.log_llm_error(req_id, active_llm, err, context=context)
                raise
            try:
                self._raise_if_run_canceled(current_context)
                fallback_kwargs = {}
                if config is not None:
                    fallback_kwargs['config'] = config
                res = self._invoke_with_unsupported_parameter_retry(
                    current_context,
                    messages,
                    fallback_kwargs,
                    req_id,
                    context=context,
                )
                active_llm = current_context.llm
                self._raise_if_run_canceled(current_context)
            except Exception as err2:
                if isinstance(err2, AICancelled):
                    raise
                if current_context.cancel_event.is_set():
                    raise AICancelled(current_context.run_id)
                self.log_llm_error(req_id, active_llm, err2, context=context)
                raise
        finally:
            if temp_context is not None:
                terminal_status = 'canceled' if temp_context.cancel_event.is_set() else (
                    'errored' if temp_context.error_text != '' else 'finished'
                )
                self._finalize_run_context(temp_context, terminal_status)
        self.log_llm_response(req_id, active_llm, getattr(res, 'content', ''), context=context)
        return res

    def _invoke_with_large_model_fallback(self, messages, invoke_kwargs, context: str, current_context):
        """Retry one failed fast-model invoke with the configured large model."""

        if current_context is None:
            return None
        if str(current_context.model_kind).strip().lower() != 'fast':
            return None
        if self._large_llm_params is None or self._large_llm_factory is None:
            return None

        fallback_context = None
        fallback_req_id = None
        fallback_llm = None
        fallback_context_label = f'{context}_fallback_large' if str(context).strip() != '' else 'fallback_large'
        try:
            self._raise_if_run_canceled(current_context)
            fallback_context = self._create_run_context(model_kind='large', purpose='invoke')
            fallback_llm = fallback_context.llm
            fallback_req_id = self.log_llm_request(fallback_llm, messages, context=fallback_context_label)
            res = self._invoke_with_unsupported_parameter_retry(
                fallback_context,
                messages,
                invoke_kwargs,
                fallback_req_id,
                context=fallback_context_label,
            )
            fallback_llm = fallback_context.llm
            self._raise_if_run_canceled(current_context)
            self.log_llm_response(fallback_req_id, fallback_llm, getattr(res, 'content', ''), context=fallback_context_label)
            return res
        except Exception as err:
            if isinstance(err, AICancelled):
                raise
            if current_context.cancel_event.is_set():
                raise AICancelled(current_context.run_id)
            if fallback_req_id is not None and fallback_llm is not None:
                self.log_llm_error(fallback_req_id, fallback_llm, err, context=fallback_context_label)
            raise
        finally:
            if fallback_context is not None:
                terminal_status = 'canceled' if fallback_context.cancel_event.is_set() else (
                    'errored' if fallback_context.error_text != '' else 'finished'
                )
                self._finalize_run_context(fallback_context, terminal_status)

    def _ensure_ai_change_history(self):
        if not isinstance(self.ai_change_history, list):
            self.ai_change_history = []
        return self.ai_change_history

    def has_undoable_ai_changes(self) -> bool:
        """Return whether the current session contains AI changes that can be undone."""

        history = self._ensure_ai_change_history()
        for item in history:
            if not isinstance(item, dict):
                continue
            operations = item.get("operations", None)
            if isinstance(operations, list) and len(operations) > 0:
                return True
        return False

    def _ensure_ai_change_set(self, history, set_id: str):
        for item in history:
            if not isinstance(item, dict):
                continue
            if str(item.get("id", "")).strip() == set_id:
                ops = item.get("operations", None)
                if not isinstance(ops, list):
                    item["operations"] = []
                if "name" not in item or str(item.get("name", "")).strip() == "":
                    item["name"] = "" # _("AI changes")
                if "created_at" not in item:
                    item["created_at"] = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
                return item
        new_set = {
            "id": set_id,
            "name": "",  # _("AI changes")
            "created_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            "operations": [],
        }
        history.insert(0, new_set)
        return new_set

    def begin_ai_change_set(self, messages, chat_idx: int) -> str:
        """Create one session-scoped AI change set for the current chat turn."""

        history = self._ensure_ai_change_history()
        now = datetime.now().astimezone()
        set_id = f'ai-run-{now.strftime("%Y%m%d%H%M%S%f")}-{chat_idx}'
        title = "" # _("AI changes")
        title += "[" + now.strftime("%H:%M:%S") + "]"

        change_set = {
            "id": set_id,
            "name": title,
            "created_at": now.strftime("%Y-%m-%d %H:%M:%S"),
            "operations": [],
        }
        history.insert(0, change_set)
        return set_id

    def _short_change_label(self, text: str, max_len: int = 36) -> str:
        txt = " ".join(str(text if text is not None else "").split()).strip()
        if len(txt) <= max_len:
            return txt
        return txt[: max_len - 3] + "..."

    def _lookup_code_name(self, cid: int) -> str:
        if cid <= 0:
            return ""
        try:
            cur = self.app.conn.cursor()
            cur.execute("SELECT name FROM code_name WHERE cid=?", (cid,))
            row = cur.fetchone()
            if row is None:
                return ""
            return str(row[0] if row[0] is not None else "").strip()
        except Exception:
            return ""

    def _lookup_category_name(self, catid: int) -> str:
        if catid <= 0:
            return ""
        try:
            cur = self.app.conn.cursor()
            cur.execute("SELECT name FROM code_cat WHERE catid=?", (catid,))
            row = cur.fetchone()
            if row is None:
                return ""
            return str(row[0] if row[0] is not None else "").strip()
        except Exception:
            return ""

    def _lookup_source_name(self, fid: int) -> str:
        if fid <= 0:
            return ""
        try:
            cur = self.app.conn.cursor()
            cur.execute("SELECT name FROM source WHERE id=?", (fid,))
            row = cur.fetchone()
            if row is None:
                return ""
            return str(row[0] if row[0] is not None else "").strip()
        except Exception:
            return ""

    def _lookup_case_name(self, caseid: int) -> str:
        if caseid <= 0:
            return ""
        try:
            cur = self.app.conn.cursor()
            cur.execute("SELECT name FROM cases WHERE caseid=?", (caseid,))
            row = cur.fetchone()
            if row is None:
                return ""
            return str(row[0] if row[0] is not None else "").strip()
        except Exception:
            return ""

    def _format_name_line(self, prefix: str, names: list, max_items: int = 5) -> str:
        if not isinstance(names, list) or len(names) == 0:
            return ""
        trimmed = [n for n in names if str(n).strip() != ""]
        if len(trimmed) == 0:
            return ""
        shown = trimmed[:max_items]
        line = prefix + ", ".join(shown)
        remaining = len(trimmed) - len(shown)
        if remaining > 0:
            line += _(" (+{0} more)").format(remaining)
        return line

    def _format_ai_change_scope(self, categories: int = 0, codes: int = 0, codings: int = 0) -> str:
        """Return one compact scope summary for AI change descriptions."""

        parts = []
        if int(categories) > 0:
            parts.append(str(int(categories)) + " " + _("category(ies)"))
        if int(codes) > 0:
            parts.append(str(int(codes)) + " " + _("code(s)"))
        if int(codings) > 0:
            parts.append(str(int(codings)) + " " + _("coding(s)"))
        return ", ".join(parts)

    def _ai_change_operation_summary(self, op: dict, allow_db_lookup: bool = False) -> str:
        """Build one user-facing summary line for an AI change operation."""

        if not isinstance(op, dict):
            return ""
        op_type = str(op.get("type", "")).strip()

        if op_type == "create_category":
            name = self._short_change_label(op.get("name", ""))
            return (_("Created category: ") + name) if name != "" else ""

        if op_type == "create_code":
            name = self._short_change_label(op.get("name", ""))
            return (_("Created code: ") + name) if name != "" else ""

        if op_type == "create_coding_text":
            cid = int(op.get("cid", -1))
            fid = int(op.get("fid", -1))
            code_name = self._short_change_label(op.get("code_name", ""))
            source_name = self._short_change_label(op.get("source_name", ""))
            if allow_db_lookup and code_name == "":
                code_name = self._short_change_label(self._lookup_code_name(cid))
            if allow_db_lookup and source_name == "":
                source_name = self._short_change_label(self._lookup_source_name(fid))
            label = " @ ".join([item for item in (code_name, source_name) if item != ""])
            if label == "":
                label = _("Text coding")
            return _("Created text coding: ") + label

        if op_type == "create_case":
            name = self._short_change_label(op.get("name", ""))
            return (_("Created case: ") + name) if name != "" else ""

        if op_type == "create_case_attribute":
            name = self._short_change_label(op.get("name", ""))
            return (_("Created case attribute: ") + name) if name != "" else ""

        if op_type == "create_document_attribute":
            name = self._short_change_label(op.get("name", ""))
            return (_("Created document attribute: ") + name) if name != "" else ""

        if op_type == "create_case_text":
            case_name = self._short_change_label(op.get("case_name", ""))
            source_name = self._short_change_label(op.get("source_name", ""))
            if allow_db_lookup:
                if case_name == "":
                    caseid = int(op.get("caseid", -1))
                    if caseid > 0:
                        cur = self.app.conn.cursor()
                        cur.execute("SELECT name FROM cases WHERE caseid=?", (caseid,))
                        row = cur.fetchone()
                        if row is not None:
                            case_name = self._short_change_label(row[0])
                if source_name == "":
                    source_name = self._short_change_label(self._lookup_source_name(int(op.get("fid", -1))))
            label = " @ ".join([item for item in (case_name, source_name) if item != ""])
            return (_("Linked text to case: ") + label) if label != "" else _("Linked text to case")

        if op_type == "update_case":
            before_name = self._short_change_label(op.get("before", {}).get("name", ""))
            after_name = self._short_change_label(op.get("after", {}).get("name", ""))
            if before_name != "" and after_name != "" and before_name != after_name:
                return _("Updated case: ") + before_name + " -> " + after_name
            if after_name != "":
                return _("Updated case: ") + after_name
            return _("Updated case")

        if op_type == "update_case_attributes":
            target_name = self._short_change_label(op.get("target_name", ""))
            if allow_db_lookup and target_name == "":
                target_name = self._short_change_label(self._lookup_case_name(int(op.get("caseid", -1))))
            change_count = len(op.get("changes", [])) if isinstance(op.get("changes", []), list) else 0
            if target_name != "" and change_count > 0:
                return _("Updated case attributes: ") + target_name + f" ({change_count})"
            if target_name != "":
                return _("Updated case attributes: ") + target_name
            return _("Updated case attributes")

        if op_type == "update_document_attributes":
            target_name = self._short_change_label(op.get("target_name", ""))
            if allow_db_lookup and target_name == "":
                target_name = self._short_change_label(self._lookup_source_name(int(op.get("fid", -1))))
            change_count = len(op.get("changes", [])) if isinstance(op.get("changes", []), list) else 0
            if target_name != "" and change_count > 0:
                return _("Updated document attributes: ") + target_name + f" ({change_count})"
            if target_name != "":
                return _("Updated document attributes: ") + target_name
            return _("Updated document attributes")

        if op_type == "rename_category":
            old_name = self._short_change_label(op.get("old_name", ""))
            new_name = self._short_change_label(op.get("new_name", ""))
            if old_name == "" and allow_db_lookup:
                old_name = self._short_change_label(self._lookup_category_name(int(op.get("catid", -1))))
            if old_name == "" or new_name == "":
                return ""
            return _("Renamed category: ") + old_name + " -> " + new_name

        if op_type == "rename_code":
            old_name = self._short_change_label(op.get("old_name", ""))
            new_name = self._short_change_label(op.get("new_name", ""))
            if old_name == "" and allow_db_lookup:
                old_name = self._short_change_label(self._lookup_code_name(int(op.get("cid", -1))))
            if old_name == "" or new_name == "":
                return ""
            return _("Renamed code: ") + old_name + " -> " + new_name

        if op_type == "move_category_tree":
            name = self._short_change_label(op.get("name", ""))
            if name == "" and allow_db_lookup:
                name = self._short_change_label(self._lookup_category_name(int(op.get("root_catid", -1))))
            impact = op.get("impact", {})
            counts = impact.get("counts", {}) if isinstance(impact, dict) else {}
            scope = self._format_ai_change_scope(
                categories=int(counts.get("categories", 0)),
                codes=int(counts.get("codes", 0)),
                codings=int(counts.get("total_codings", 0)),
            )
            if name == "":
                return ""
            if scope != "":
                return _("Moved category tree: ") + name + " (" + scope + ")"
            return _("Moved category tree: ") + name

        if op_type == "move_code":
            name = self._short_change_label(op.get("name", ""))
            if name == "" and allow_db_lookup:
                name = self._short_change_label(self._lookup_code_name(int(op.get("cid", -1))))
            if name == "":
                return ""
            impact = op.get("impact", {})
            counts = impact.get("counts", {}) if isinstance(impact, dict) else {}
            scope = self._format_ai_change_scope(
                codes=int(counts.get("codes", 0)),
                codings=int(counts.get("total_codings", 0)),
            )
            if int(counts.get("codes", 0)) > 1:
                if scope != "":
                    return _("Moved code tree: ") + name + " (" + scope + ")"
                return _("Moved code tree: ") + name
            return _("Moved code: ") + name

        if op_type == "move_coding_text":
            old_cid = int(op.get("before", {}).get("cid", -1))
            new_cid = int(op.get("after", {}).get("cid", -1))
            old_name = self._short_change_label(self._lookup_code_name(old_cid)) if allow_db_lookup else ""
            new_name = self._short_change_label(self._lookup_code_name(new_cid)) if allow_db_lookup else ""
            if old_name != "" and new_name != "":
                return _("Moved text coding: ") + old_name + " -> " + new_name
            return _("Moved text coding")

        if op_type == "delete_category_tree":
            name = self._short_change_label(op.get("name", ""))
            counts = self._snapshot_counts(op)
            scope = self._format_ai_change_scope(
                categories=int(counts.get("categories", 0)),
                codes=int(counts.get("codes", 0)),
                codings=(
                    int(counts.get("text_codings", 0)) +
                    int(counts.get("av_codings", 0)) +
                    int(counts.get("image_codings", 0))
                ),
            )
            if name == "":
                return ""
            if scope != "":
                return _("Deleted category tree: ") + name + " (" + scope + ")"
            return _("Deleted category tree: ") + name

        if op_type == "delete_code":
            name = self._short_change_label(op.get("name", ""))
            counts = self._snapshot_counts(op)
            scope = self._format_ai_change_scope(
                codes=int(counts.get("codes", 0)),
                codings=(
                    int(counts.get("text_codings", 0)) +
                    int(counts.get("av_codings", 0)) +
                    int(counts.get("image_codings", 0))
                ),
            )
            if name == "" and allow_db_lookup:
                name = self._short_change_label(self._lookup_code_name(int(op.get("cid", -1))))
            if name == "":
                return ""
            if int(counts.get("codes", 0)) > 1:
                if scope != "":
                    return _("Deleted code tree: ") + name + " (" + scope + ")"
                return _("Deleted code tree: ") + name
            if scope != "":
                return _("Deleted code: ") + name + " (" + scope + ")"
            return _("Deleted code: ") + name

        if op_type == "delete_coding_text":
            snapshot = self._snapshot_tables(op)
            code_rows = snapshot.get("code_text", [])
            if isinstance(code_rows, list) and len(code_rows) > 0 and isinstance(code_rows[0], dict):
                cid = int(code_rows[0].get("cid", -1))
                fid = int(code_rows[0].get("fid", -1))
                code_name = self._short_change_label(self._lookup_code_name(cid)) if allow_db_lookup else ""
                source_name = self._short_change_label(self._lookup_source_name(fid)) if allow_db_lookup else ""
                label = " @ ".join([item for item in (code_name, source_name) if item != ""])
                if label != "":
                    return _("Deleted text coding: ") + label
            return _("Deleted text coding")

        if op_type == "delete_case_text":
            snapshot = self._snapshot_tables(op)
            link_rows = snapshot.get("case_text", [])
            if isinstance(link_rows, list) and len(link_rows) > 0 and isinstance(link_rows[0], dict):
                caseid = int(link_rows[0].get("caseid", -1))
                fid = int(link_rows[0].get("fid", -1))
                case_name = ""
                source_name = ""
                if allow_db_lookup:
                    if caseid > 0:
                        cur = self.app.conn.cursor()
                        cur.execute("SELECT name FROM cases WHERE caseid=?", (caseid,))
                        row = cur.fetchone()
                        if row is not None:
                            case_name = self._short_change_label(row[0])
                    source_name = self._short_change_label(self._lookup_source_name(fid))
                label = " @ ".join([item for item in (case_name, source_name) if item != ""])
                if label != "":
                    return _("Removed case link: ") + label
            return _("Removed case link")

        return ""

    def _format_ai_change_age(self, created_at: str) -> str:
        """Return a relative age label for one stored AI change set."""

        created_text = str(created_at if created_at is not None else "").strip()
        if created_text == "":
            return ""

        try:
            now = datetime.now().astimezone()
            created_dt = datetime.strptime(created_text, "%Y-%m-%d %H:%M:%S")
            created_dt = created_dt.replace(tzinfo=now.tzinfo)
        except Exception:
            return ""

        if created_dt > now:
            created_dt = now

        day_diff = (now.date() - created_dt.date()).days
        if day_diff > 0:
            if day_diff == 1:
                return _("1 day ago")
            return _("{0} days ago").format(day_diff)

        seconds_diff = max(0, int((now - created_dt).total_seconds()))
        minute_count = seconds_diff // 60
        if minute_count < 60:
            if minute_count == 1:
                return _("1 minute ago")
            return _("{0} minutes ago").format(minute_count)

        hour_count = minute_count // 60
        if hour_count == 1:
            return _("1 hour ago")
        return _("{0} hours ago").format(hour_count)

    def _blend_color(self, base: QtGui.QColor, overlay: QtGui.QColor, amount: float) -> QtGui.QColor:
        """Blend palette colors to create readable separators in light and dark themes."""

        factor = max(0.0, min(1.0, float(amount)))
        red = int(round(base.red() * (1.0 - factor) + overlay.red() * factor))
        green = int(round(base.green() * (1.0 - factor) + overlay.green() * factor))
        blue = int(round(base.blue() * (1.0 - factor) + overlay.blue() * factor))
        return QtGui.QColor(red, green, blue)

    def _ai_change_list_stylesheet(self, list_view: QtWidgets.QListView) -> str:
        palette = list_view.palette()
        base_color = palette.color(QtGui.QPalette.ColorRole.Base)
        text_color = palette.color(QtGui.QPalette.ColorRole.Text)
        highlight_color = palette.color(QtGui.QPalette.ColorRole.Highlight)
        highlighted_text_color = palette.color(QtGui.QPalette.ColorRole.HighlightedText)
        blend_amount = 0.42 if base_color.lightness() < 128 else 0.28
        separator_color = self._blend_color(base_color, text_color, blend_amount)
        inactive_selection_color = self._blend_color(base_color, highlight_color, 0.8)
        return (
            "QListView::item {"
            f"border-bottom: 1px solid {separator_color.name()};"
            "}"
            "QListView::item:selected {"
            f"background: {highlight_color.name()};"
            f"color: {highlighted_text_color.name()};"
            "}"
            "QListView::item:selected:!active {"
            f"background: {inactive_selection_color.name()};"
            f"color: {highlighted_text_color.name()};"
            "}"
        )

    def _refresh_ai_change_set_name(
            self,
            change_set: dict,
            allow_db_lookup: bool = False,
            use_relative_time: bool = False) -> None:
        """Update one change-set title from recorded operations."""

        if not isinstance(change_set, dict):
            return
        operations = change_set.get("operations", None)
        if not isinstance(operations, list) or len(operations) == 0:
            return

        category_count = 0
        code_count = 0
        case_count = 0
        coding_count = 0
        case_link_count = 0
        attribute_count = 0
        operation_summaries = []
        seen_operation_summaries = set()

        for op in operations:
            if not isinstance(op, dict):
                continue
            op_type = str(op.get("type", "")).strip()
            if op_type in ("create_category", "rename_category", "move_category_tree", "delete_category_tree"):
                category_count += 1
            elif op_type in ("create_code", "rename_code", "move_code", "delete_code"):
                code_count += 1
            elif op_type in ("create_coding_text", "move_coding_text", "delete_coding_text"):
                coding_count += 1
            elif op_type in ("create_case", "update_case"):
                case_count += 1
            elif op_type in ("create_case_text", "delete_case_text"):
                case_link_count += 1
            elif op_type in (
                    "create_case_attribute",
                    "create_document_attribute",
                    "update_case_attributes",
                    "update_document_attributes"):
                attribute_count += 1
            summary = self._ai_change_operation_summary(op, allow_db_lookup=allow_db_lookup)
            if summary != "" and summary not in seen_operation_summaries:
                seen_operation_summaries.add(summary)
                operation_summaries.append(summary)

        parts = []
        if category_count > 0:
            parts.append(str(category_count) + " " + _("category(ies)"))
        if code_count > 0:
            parts.append(str(code_count) + " " + _("code(s)"))
        if case_count > 0:
            parts.append(str(case_count) + " " + _("case(s)"))
        if coding_count > 0:
            parts.append(str(coding_count) + " " + _("text coding(s)"))
        if case_link_count > 0:
            parts.append(str(case_link_count) + " " + _("case link(s)"))
        if attribute_count > 0:
            parts.append(str(attribute_count) + " " + _("attribute action(s)"))
        if len(parts) == 0:
            return

        created_at = str(change_set.get("created_at", "")).strip()
        time_label = created_at
        if use_relative_time:
            relative_time = self._format_ai_change_age(created_at)
            if relative_time != "":
                time_label = relative_time
        elif len(created_at) >= 19:
            time_label = created_at[11:19] # extract HH:MM:SS from timestamp

        title = "" # _("AI changes")
        if time_label != "":
            if use_relative_time:
                title += time_label
            else:
                title += "[" + time_label + "]"
        first_line = title if title != "" else ", ".join(parts)
        lines = [first_line]
        shown_summaries = operation_summaries[:4]
        for summary in shown_summaries:
            lines.append(summary)
        remaining = len(operation_summaries) - len(shown_summaries)
        if remaining > 0:
            lines.append(_("Additional actions: ") + str(remaining))
        change_set["name"] = "\n".join(lines)

        tooltip_lines = [first_line]
        tooltip_summaries = operation_summaries[:20]
        tooltip_lines.extend(tooltip_summaries)
        tooltip_remaining = len(operation_summaries) - len(tooltip_summaries)
        if tooltip_remaining > 0:
            tooltip_lines.append(_("Additional actions: ") + str(tooltip_remaining))
        change_set["tooltip"] = "\n".join(tooltip_lines)

    def discard_empty_ai_change_set(self, set_id: str) -> None:
        """Remove a pre-created AI change set if no write operation was recorded."""

        normalized_id = str(set_id).strip()
        if normalized_id == "":
            return
        history = self._ensure_ai_change_history()
        for idx, item in enumerate(history):
            if not isinstance(item, dict):
                continue
            if str(item.get("id", "")).strip() != normalized_id:
                continue
            operations = item.get("operations", None)
            if isinstance(operations, list) and len(operations) == 0:
                history.pop(idx)
            return

    def record_ai_change(self, change_set_id: str, operation: dict) -> None:
        """Append one operation to the session-scoped AI change history."""

        if not isinstance(operation, dict):
            return
        history = self._ensure_ai_change_history()
        normalized_set_id = str(change_set_id).strip()
        if normalized_set_id == "":
            normalized_set_id = "ai-run-" + datetime.now().astimezone().strftime("%Y%m%d%H%M%S%f")
        change_set = self._ensure_ai_change_set(history, normalized_set_id)
        op_copy = dict(operation)
        op_copy["change_set_id"] = normalized_set_id
        change_set["operations"].append(op_copy)
        self._refresh_ai_change_set_name(change_set)

    def _table_exists(self, table_name: str) -> bool:
        cur = self.app.conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        return cur.fetchone() is not None

    def _can_undo_create_category(self, cur, op):
        catid = int(op.get("catid", -1))
        if catid <= 0:
            return False, "invalid", None
        cur.execute("SELECT catid, name, owner FROM code_cat WHERE catid=?", (catid,))
        row = cur.fetchone()
        if row is None:
            return False, "missing", None
        expected_name = str(op.get("name", "")).strip()
        if expected_name != "" and row[1] != expected_name:
            return False, "changed", row
        if str(row[2]) != "AI Agent":
            return False, "changed", row
        return True, "ok", row

    def _can_undo_create_code(self, cur, op):
        cid = int(op.get("cid", -1))
        if cid <= 0:
            return False, "invalid", None
        cur.execute("SELECT cid, name, owner, catid, supercid FROM code_name WHERE cid=?", (cid,))
        row = cur.fetchone()
        if row is None:
            return False, "missing", None
        expected_name = str(op.get("name", "")).strip()
        if expected_name != "" and row[1] != expected_name:
            return False, "changed", row
        if str(row[2]) != "AI Agent":
            return False, "changed", row
        expected_catid = op.get("catid", None)
        expected_supercid = op.get("supercid", None)
        if row[3] != expected_catid or row[4] != expected_supercid:
            return False, "changed", row
        cur.execute("SELECT count(*) FROM code_name WHERE supercid=?", (cid,))
        if int((cur.fetchone() or [0])[0] or 0) > 0:
            return False, "changed", row
        return True, "ok", row

    def _can_undo_create_coding_text(self, cur, op):
        ctid = int(op.get("ctid", -1))
        if ctid <= 0:
            return False, "invalid", None
        cur.execute(
            "SELECT ctid, cid, fid, pos0, pos1, owner, ifnull(seltext,'') FROM code_text WHERE ctid=?",
            (ctid,),
        )
        row = cur.fetchone()
        if row is None:
            return False, "missing", None
        expected = {
            "cid": int(op.get("cid", -1)),
            "fid": int(op.get("fid", -1)),
            "pos0": int(op.get("pos0", -1)),
            "pos1": int(op.get("pos1", -1)),
            "owner": str(op.get("owner", "AI Agent")),
            "seltext": str(op.get("seltext", "")),
        }
        if expected["cid"] > 0 and row[1] != expected["cid"]:
            return False, "changed", row
        if expected["fid"] > 0 and row[2] != expected["fid"]:
            return False, "changed", row
        if expected["pos0"] >= 0 and row[3] != expected["pos0"]:
            return False, "changed", row
        if expected["pos1"] >= 0 and row[4] != expected["pos1"]:
            return False, "changed", row
        if expected["owner"] != "" and row[5] != expected["owner"]:
            return False, "changed", row
        if expected["seltext"] != "" and row[6] != expected["seltext"]:
            return False, "changed", row
        return True, "ok", row

    def _can_undo_create_case(self, cur, op):
        caseid = int(op.get("caseid", -1))
        if caseid <= 0:
            return False, "invalid", None
        cur.execute("SELECT caseid, name, owner FROM cases WHERE caseid=?", (caseid,))
        row = cur.fetchone()
        if row is None:
            return False, "missing", None
        expected_name = str(op.get("name", "")).strip()
        if expected_name != "" and str(row[1]) != expected_name:
            return False, "changed", row
        if str(row[2]) != "AI Agent":
            return False, "changed", row
        return True, "ok", row

    def _can_undo_create_case_text(self, cur, op):
        link_id = int(op.get("id", -1))
        if link_id <= 0:
            return False, "invalid", None
        cur.execute(
            "SELECT id, caseid, fid, pos0, pos1, owner FROM case_text WHERE id=?",
            (link_id,),
        )
        row = cur.fetchone()
        if row is None:
            return False, "missing", None
        expected = {
            "caseid": int(op.get("caseid", -1)),
            "fid": int(op.get("fid", -1)),
            "pos0": int(op.get("pos0", -1)),
            "pos1": int(op.get("pos1", -1)),
            "owner": str(op.get("owner", "AI Agent")),
        }
        if expected["caseid"] > 0 and row[1] != expected["caseid"]:
            return False, "changed", row
        if expected["fid"] > 0 and row[2] != expected["fid"]:
            return False, "changed", row
        if expected["pos0"] >= 0 and row[3] != expected["pos0"]:
            return False, "changed", row
        if expected["pos1"] >= 0 and row[4] != expected["pos1"]:
            return False, "changed", row
        if expected["owner"] != "" and row[5] != expected["owner"]:
            return False, "changed", row
        return True, "ok", row

    def _can_undo_update_case(self, cur, op):
        caseid = int(op.get("caseid", -1))
        if caseid <= 0:
            return False, "invalid", None
        cur.execute("SELECT caseid, name, ifnull(memo,''), owner FROM cases WHERE caseid=?", (caseid,))
        row = cur.fetchone()
        if row is None:
            return False, "missing", None
        after = op.get("after", {}) if isinstance(op.get("after", {}), dict) else {}
        expected_name = str(after.get("name", "")).strip()
        expected_memo = str(after.get("memo", ""))
        if expected_name != "" and str(row[1]) != expected_name:
            return False, "changed", row
        if str(row[2]) != expected_memo:
            return False, "changed", row
        return True, "ok", row

    def _fetch_attribute_row_by_key(self, cur, name: str, attr_type: str, target_id: int):
        cur.execute(
            "SELECT attrid, name, attr_type, ifnull(value,''), id, ifnull(owner,''), ifnull(date,'') "
            "FROM attribute WHERE name=? AND attr_type=? AND id=?",
            (name, attr_type, target_id),
        )
        return cur.fetchone()

    def _attribute_row_matches_state(self, row, state: dict) -> bool:
        if row is None or not isinstance(state, dict):
            return False
        expected_attrid = int(state.get("attrid", -1))
        if expected_attrid > 0 and int(row[0]) != expected_attrid:
            return False
        expected_value = str(state.get("value", ""))
        expected_owner = str(state.get("owner", ""))
        if str(row[3]) != expected_value:
            return False
        if expected_owner != "" and str(row[5]) != expected_owner:
            return False
        return True

    def _can_undo_create_attribute(self, cur, op):
        attr_name = str(op.get("name", "")).strip()
        target_type = str(op.get("target_type", "")).strip()
        if attr_name == "" or target_type not in ("case", "file"):
            return False, "invalid", None
        cur.execute(
            "SELECT name, ifnull(owner,''), ifnull(caseOrFile,''), ifnull(valuetype,'') "
            "FROM attribute_type WHERE name=?",
            (attr_name,),
        )
        row = cur.fetchone()
        if row is None:
            return False, "missing", None
        if str(row[1]) != "AI Agent":
            return False, "changed", row
        if str(row[2]) != target_type:
            return False, "changed", row
        expected_value_type = str(op.get("value_type", "character")).strip() or "character"
        if str(row[3]) != expected_value_type:
            return False, "changed", row
        cur.execute(
            "SELECT count(*), "
            "sum(case when length(ifnull(value,'')) > 0 then 1 else 0 end), "
            "sum(case when ifnull(owner,'') != 'AI Agent' then 1 else 0 end) "
            "FROM attribute WHERE name=? AND attr_type=?",
            (attr_name, target_type),
        )
        attr_row = cur.fetchone() or (0, 0, 0)
        if int(attr_row[1] or 0) > 0 or int(attr_row[2] or 0) > 0:
            return False, "changed", row
        return True, "ok", row

    def _can_undo_update_attributes(self, cur, op):
        if not isinstance(op, dict):
            return False, "invalid", None
        target_type = str(op.get("target_type", "")).strip()
        target_id = int(op.get("caseid", op.get("fid", -1)))
        changes = op.get("changes", [])
        if target_type not in ("case", "file") or target_id <= 0 or not isinstance(changes, list) or len(changes) == 0:
            return False, "invalid", None
        current_rows = []
        for change in changes:
            if not isinstance(change, dict):
                return False, "invalid", None
            attr_name = str(change.get("name", "")).strip()
            after = change.get("after", {}) if isinstance(change.get("after", {}), dict) else {}
            if attr_name == "" or not bool(after.get("exists", False)):
                return False, "invalid", None
            row = self._fetch_attribute_row_by_key(cur, attr_name, target_type, target_id)
            if row is None:
                return False, "missing", None
            if not self._attribute_row_matches_state(row, after):
                return False, "changed", row
            current_rows.append(row)
        return True, "ok", current_rows

    def _can_undo_rename_category(self, cur, op):
        catid = int(op.get("catid", -1))
        if catid <= 0:
            return False, "invalid", None
        cur.execute("SELECT catid, name FROM code_cat WHERE catid=?", (catid,))
        row = cur.fetchone()
        if row is None:
            return False, "missing", None
        expected_name = str(op.get("new_name", "")).strip()
        if expected_name != "" and str(row[1]) != expected_name:
            return False, "changed", row
        return True, "ok", row

    def _can_undo_rename_code(self, cur, op):
        cid = int(op.get("cid", -1))
        if cid <= 0:
            return False, "invalid", None
        cur.execute("SELECT cid, name FROM code_name WHERE cid=?", (cid,))
        row = cur.fetchone()
        if row is None:
            return False, "missing", None
        expected_name = str(op.get("new_name", "")).strip()
        if expected_name != "" and str(row[1]) != expected_name:
            return False, "changed", row
        return True, "ok", row

    def _can_undo_move_category_tree(self, cur, op):
        catid = int(op.get("root_catid", op.get("catid", -1)))
        if catid <= 0:
            return False, "invalid", None
        cur.execute("SELECT catid, supercatid FROM code_cat WHERE catid=?", (catid,))
        row = cur.fetchone()
        if row is None:
            return False, "missing", None
        expected_supercatid = op.get("after", {}).get("supercatid", None)
        if row[1] != expected_supercatid:
            return False, "changed", row
        return True, "ok", row

    def _can_undo_move_code(self, cur, op):
        cid = int(op.get("cid", -1))
        if cid <= 0:
            return False, "invalid", None
        cur.execute("SELECT cid, catid, supercid FROM code_name WHERE cid=?", (cid,))
        row = cur.fetchone()
        if row is None:
            return False, "missing", None
        expected_catid = op.get("after", {}).get("catid", None)
        expected_supercid = op.get("after", {}).get("supercid", None)
        if row[1] != expected_catid or row[2] != expected_supercid:
            return False, "changed", row
        return True, "ok", row

    def _can_undo_move_coding_text(self, cur, op):
        ctid = int(op.get("ctid", -1))
        if ctid <= 0:
            return False, "invalid", None
        cur.execute("SELECT ctid, cid FROM code_text WHERE ctid=?", (ctid,))
        row = cur.fetchone()
        if row is None:
            return False, "missing", None
        expected_cid = int(op.get("after", {}).get("cid", -1))
        if expected_cid > 0 and row[1] != expected_cid:
            return False, "changed", row
        return True, "ok", row

    def _snapshot_tables(self, op):
        snapshot = op.get("snapshot", {})
        if not isinstance(snapshot, dict):
            return {}
        tables = snapshot.get("tables", {})
        if not isinstance(tables, dict):
            return {}
        return tables

    def _can_restore_snapshot(self, cur, op):
        tables = self._snapshot_tables(op)
        if len(tables) == 0:
            return False, "invalid"
        primary_keys = {
            "code_cat": "catid",
            "code_name": "cid",
            "code_text": "ctid",
            "code_av": "avid",
            "code_image": "imid",
            "case_text": "id",
        }
        for table_name, pk_name in primary_keys.items():
            rows = tables.get(table_name, [])
            if not isinstance(rows, list):
                continue
            if len(rows) == 0:
                continue
            if not self._table_exists(table_name):
                return False, "invalid"
            for row in rows:
                if not isinstance(row, dict):
                    return False, "invalid"
                pk_value = row.get(pk_name, None)
                if pk_value is None:
                    return False, "invalid"
                cur.execute(f"SELECT 1 FROM {table_name} WHERE {pk_name}=?", (pk_value,))
                if cur.fetchone() is not None:
                    return False, "changed"
        return True, "ok"

    def _restore_snapshot(self, cur, op):
        tables = self._snapshot_tables(op)
        restore_order = ("code_cat", "code_name", "cases", "code_text", "case_text", "code_av", "code_image")
        for table_name in restore_order:
            rows = tables.get(table_name, [])
            if not isinstance(rows, list) or len(rows) == 0:
                continue
            for row in rows:
                if not isinstance(row, dict) or len(row) == 0:
                    continue
                columns = list(row.keys())
                placeholders = ",".join(["?"] * len(columns))
                sql = f"INSERT INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})"
                values = [row.get(column, None) for column in columns]
                cur.execute(sql, values)

    def _snapshot_counts(self, op):
        tables = self._snapshot_tables(op)
        return {
            "categories": len(tables.get("code_cat", [])) if isinstance(tables.get("code_cat", []), list) else 0,
            "codes": len(tables.get("code_name", [])) if isinstance(tables.get("code_name", []), list) else 0,
            "text_codings": len(tables.get("code_text", [])) if isinstance(tables.get("code_text", []), list) else 0,
            "av_codings": len(tables.get("code_av", [])) if isinstance(tables.get("code_av", []), list) else 0,
            "image_codings": len(tables.get("code_image", [])) if isinstance(tables.get("code_image", []), list) else 0,
        }

    def _emit_project_table_changes(self, tables: list[str], source="ai_agent_undo") -> None:
        """Emit one app-level project data change event if the event bus exists."""

        project_events = getattr(self.app, "project_events", None)
        if project_events is None or not hasattr(project_events, "emit_table_changes") or not isinstance(tables, list):
            return
        project_events.emit_table_changes(tables, source=source)

    def _add_project_table_changes(self, aggregated: set[str], *table_names: str) -> None:
        """Collect changed table names for one later event-bus update."""

        for table_name in table_names:
            name = str(table_name if table_name is not None else "").strip()
            if name != "":
                aggregated.add(name)

    def _snapshot_changed_table_names(self, op) -> list[str]:
        """Return non-empty table names from one snapshot payload."""

        changed_tables = []
        tables = self._snapshot_tables(op)
        for table_name, rows in tables.items():
            name = str(table_name if table_name is not None else "").strip()
            if name == "" or not isinstance(rows, list) or len(rows) == 0:
                continue
            changed_tables.append(name)
        return changed_tables

    def _count_code_codings(self, cur, cid: int) -> tuple[int, int]:
        total = 0
        non_ai = 0
        for table in ("code_text", "code_av", "code_image"):
            if not self._table_exists(table):
                continue
            cur.execute(
                f"SELECT count(*), sum(case when owner != 'AI Agent' then 1 else 0 end) FROM {table} WHERE cid=?",
                (cid,),
            )
            row = cur.fetchone()
            if row is None:
                continue
            total += int(row[0] or 0)
            non_ai += int(row[1] or 0)
        return total, non_ai

    def _should_keep_skipped_undo_operation(self, reason: str) -> bool:
        """Return whether one skipped undo operation should remain retryable."""

        return str(reason).strip() == "changed"

    def _format_undo_skip_detail(self, op: dict, reason: str, keep_for_retry: bool) -> str:
        """Build one user-facing explanation for a skipped undo operation."""

        label = self._ai_change_operation_summary(op, allow_db_lookup=True)
        if label == "":
            label = _("Stored AI change")

        if reason == "changed":
            detail = _(
                "Could not be undone because the affected item no longer matches the recorded state. "
                "It may have been edited afterwards or still be blocked by dependent data."
            )
        elif reason == "missing":
            detail = _(
                "Could not be undone because the affected item is already missing."
            )
        else:
            detail = _(
                "Could not be undone because the stored undo information is incomplete or inconsistent."
            )

        if keep_for_retry:
            detail += " " + _(
                "This undo step remains in the list so you can remove the blocking condition and try again later."
            )
        else:
            detail += " " + _(
                "This undo step was removed from the list."
            )

        return label + "\n" + _("Reason: ") + detail

    def _build_ai_change_impact_text(self, change_set):
        operations = change_set.get("operations", [])
        if not isinstance(operations, list) or len(operations) == 0:
            return ""
        cur = self.app.conn.cursor()

        code_ids = set()
        category_ids = set()
        case_ids = set()
        coding_ctids = set()
        case_link_ids = set()
        skipped_changed = 0
        skipped_missing = 0
        restore_categories = 0
        restore_codes = 0
        restore_codings = 0
        restore_case_links = 0
        revert_renamed_categories = 0
        revert_renamed_codes = 0
        revert_moved_categories = 0
        revert_moved_codes = 0
        revert_moved_codings = 0
        revert_updated_cases = 0
        remove_attributes = 0
        revert_updated_attributes = 0

        for op in operations:
            if not isinstance(op, dict):
                continue
            op_type = str(op.get("type", "")).strip()
            if op_type == "create_code":
                ok, reason, row_data = self._can_undo_create_code(cur, op)
                if ok:
                    code_ids.add(int(op.get("cid", -1)))
                elif reason == "changed":
                    skipped_changed += 1
                elif reason == "missing":
                    skipped_missing += 1
            elif op_type == "create_category":
                ok, reason, row_data = self._can_undo_create_category(cur, op)
                if ok:
                    category_ids.add(int(op.get("catid", -1)))
                elif reason == "changed":
                    skipped_changed += 1
                elif reason == "missing":
                    skipped_missing += 1
            elif op_type == "create_coding_text":
                ok, reason, row_data = self._can_undo_create_coding_text(cur, op)
                if ok:
                    ctid = int(op.get("ctid", -1))
                    cid = int(op.get("cid", -1))
                    if ctid > 0 and cid not in code_ids:
                        coding_ctids.add(ctid)
                elif reason == "changed":
                    skipped_changed += 1
                elif reason == "missing":
                    skipped_missing += 1
            elif op_type == "create_case":
                ok, reason, row_data = self._can_undo_create_case(cur, op)
                if ok:
                    case_ids.add(int(op.get("caseid", -1)))
                elif reason == "changed":
                    skipped_changed += 1
                elif reason == "missing":
                    skipped_missing += 1
            elif op_type in ("create_case_attribute", "create_document_attribute"):
                ok, reason, row_data = self._can_undo_create_attribute(cur, op)
                if ok:
                    remove_attributes += 1
                elif reason == "changed":
                    skipped_changed += 1
                elif reason == "missing":
                    skipped_missing += 1
            elif op_type == "create_case_text":
                ok, reason, row_data = self._can_undo_create_case_text(cur, op)
                if ok:
                    link_id = int(op.get("id", -1))
                    if link_id > 0:
                        case_link_ids.add(link_id)
                elif reason == "changed":
                    skipped_changed += 1
                elif reason == "missing":
                    skipped_missing += 1
            elif op_type == "update_case":
                ok, reason, row_data = self._can_undo_update_case(cur, op)
                if ok:
                    revert_updated_cases += 1
                elif reason == "changed":
                    skipped_changed += 1
                elif reason == "missing":
                    skipped_missing += 1
            elif op_type in ("update_case_attributes", "update_document_attributes"):
                ok, reason, row_data = self._can_undo_update_attributes(cur, op)
                if ok:
                    revert_updated_attributes += 1
                elif reason == "changed":
                    skipped_changed += 1
                elif reason == "missing":
                    skipped_missing += 1
            elif op_type == "rename_category":
                ok, reason, row_data = self._can_undo_rename_category(cur, op)
                if ok:
                    revert_renamed_categories += 1
                elif reason == "changed":
                    skipped_changed += 1
                elif reason == "missing":
                    skipped_missing += 1
            elif op_type == "rename_code":
                ok, reason, row_data = self._can_undo_rename_code(cur, op)
                if ok:
                    revert_renamed_codes += 1
                elif reason == "changed":
                    skipped_changed += 1
                elif reason == "missing":
                    skipped_missing += 1
            elif op_type == "move_category_tree":
                ok, reason, row_data = self._can_undo_move_category_tree(cur, op)
                if ok:
                    revert_moved_categories += 1
                elif reason == "changed":
                    skipped_changed += 1
                elif reason == "missing":
                    skipped_missing += 1
            elif op_type == "move_code":
                ok, reason, row_data = self._can_undo_move_code(cur, op)
                if ok:
                    revert_moved_codes += 1
                elif reason == "changed":
                    skipped_changed += 1
                elif reason == "missing":
                    skipped_missing += 1
            elif op_type == "move_coding_text":
                ok, reason, row_data = self._can_undo_move_coding_text(cur, op)
                if ok:
                    revert_moved_codings += 1
                elif reason == "changed":
                    skipped_changed += 1
                elif reason == "missing":
                    skipped_missing += 1
            elif op_type in ("delete_category_tree", "delete_code", "delete_coding_text"):
                ok, reason = self._can_restore_snapshot(cur, op)
                if ok:
                    counts = self._snapshot_counts(op)
                    restore_categories += int(counts.get("categories", 0))
                    restore_codes += int(counts.get("codes", 0))
                    restore_codings += (
                        int(counts.get("text_codings", 0)) +
                        int(counts.get("av_codings", 0)) +
                        int(counts.get("image_codings", 0))
                    )
                elif reason == "changed":
                    skipped_changed += 1
                elif reason == "missing":
                    skipped_missing += 1
            elif op_type == "delete_case_text":
                ok, reason = self._can_restore_snapshot(cur, op)
                if ok:
                    restore_case_links += len(self._snapshot_tables(op).get("case_text", []))
                elif reason == "changed":
                    skipped_changed += 1
                elif reason == "missing":
                    skipped_missing += 1

        code_codings_total = 0
        code_codings_non_ai = 0
        for cid in code_ids:
            ct_total, ct_non_ai = self._count_code_codings(cur, cid)
            code_codings_total += ct_total
            code_codings_non_ai += ct_non_ai

        detach_codes = 0
        detach_subcats = 0
        for catid in category_ids:
            cur.execute("SELECT count(*) FROM code_name WHERE catid=?", (catid,))
            detach_codes += int((cur.fetchone() or [0])[0] or 0)
            cur.execute("SELECT count(*) FROM code_cat WHERE supercatid=?", (catid,))
            detach_subcats += int((cur.fetchone() or [0])[0] or 0)

        standalone_codings_total = 0
        standalone_codings_non_ai = 0
        for ctid in coding_ctids:
            cur.execute("SELECT owner FROM code_text WHERE ctid=?", (ctid,))
            row = cur.fetchone()
            if row is None:
                continue
            standalone_codings_total += 1
            if str(row[0]) != "AI Agent":
                standalone_codings_non_ai += 1

        lines = []
        if len(code_ids) > 0:
            lines.append(
                _("Undo will remove ") + str(len(code_ids)) + _(" code(s) and ") +
                str(code_codings_total) + _(" related coding(s).")
            )
            if code_codings_non_ai > 0:
                lines.append(
                    _("Warning: ") + str(code_codings_non_ai) +
                    _(" of these codings are not owned by 'AI Agent'.")
                )
        if len(category_ids) > 0:
            lines.append(
                _("Undo will remove ") + str(len(category_ids)) + _(" category(ies). ") +
                str(detach_codes) + _(" code(s) and ") + str(detach_subcats) +
                _(" subcategory(ies) would be detached, not deleted.")
            )
        if standalone_codings_total > 0:
            lines.append(
                _("Undo will remove ") + str(standalone_codings_total) + _(" standalone text coding(s).")
            )
            if standalone_codings_non_ai > 0:
                lines.append(
                    _("Warning: ") + str(standalone_codings_non_ai) +
                    _(" standalone coding(s) are not owned by 'AI Agent'.")
                )
        if len(case_ids) > 0:
            lines.append(_("Undo will remove ") + str(len(case_ids)) + _(" case(s)."))
        if len(case_link_ids) > 0:
            lines.append(_("Undo will remove ") + str(len(case_link_ids)) + _(" case link(s)."))
        if remove_attributes > 0:
            lines.append(_("Undo will remove ") + str(remove_attributes) + _(" attribute definition(s)."))
        if restore_categories > 0 or restore_codes > 0 or restore_codings > 0:
            parts = []
            if restore_categories > 0:
                parts.append(str(restore_categories) + _(" category(ies)"))
            if restore_codes > 0:
                parts.append(str(restore_codes) + _(" code(s)"))
            if restore_codings > 0:
                parts.append(str(restore_codings) + _(" coding(s)"))
            lines.append(_("Undo will restore ") + ", ".join(parts) + ".")
        if restore_case_links > 0:
            lines.append(_("Undo will restore ") + str(restore_case_links) + _(" case link(s)."))
        if revert_renamed_categories > 0:
            lines.append(str(revert_renamed_categories) + _(" renamed category(ies) would be restored to their old names."))
        if revert_renamed_codes > 0:
            lines.append(str(revert_renamed_codes) + _(" renamed code(s) would be restored to their old names."))
        if revert_updated_cases > 0:
            lines.append(str(revert_updated_cases) + _(" updated case(s) would be restored to their previous values."))
        if revert_updated_attributes > 0:
            lines.append(str(revert_updated_attributes) + _(" attribute update(s) would be restored to their previous values."))
        if revert_moved_categories > 0:
            lines.append(str(revert_moved_categories) + _(" moved category tree(s) would be moved back to their previous parent."))
        if revert_moved_codes > 0:
            lines.append(str(revert_moved_codes) + _(" moved code(s) would be moved back to their previous parent."))
        if revert_moved_codings > 0:
            lines.append(str(revert_moved_codings) + _(" moved text coding(s) would be moved back to their previous code."))
        if skipped_changed > 0:
            lines.append(
                str(skipped_changed) + _(" operation(s) appear changed since creation and may be skipped.")
            )
        if skipped_missing > 0:
            lines.append(
                str(skipped_missing) + _(" operation(s) are already missing and may be skipped.")
            )
        return "\n".join(lines)

    def _undo_ai_change_set(self, change_set):
        operations = change_set.get("operations", [])
        if not isinstance(operations, list):
            return {
                "undone": 0,
                "skipped_changed": 0,
                "skipped_missing": 0,
                "skipped_invalid": 0,
                "blocked_retry": 0,
                "removed_skipped": 0,
                "deleted_code_codings": 0,
                "deleted_code_codings_non_ai": 0,
                "skip_details": [],
                "remaining_operations": [],
            }
        stats = {
            "undone": 0,
            "skipped_changed": 0,
            "skipped_missing": 0,
            "skipped_invalid": 0,
            "blocked_retry": 0,
            "removed_skipped": 0,
            "deleted_code_codings": 0,
            "deleted_code_codings_non_ai": 0,
            "skip_details": [],
            "remaining_operations": [],
        }
        remaining_operations = []
        project_table_changes = set()
        cur = self.app.conn.cursor()
        try:
            for op in reversed(operations):
                if not isinstance(op, dict):
                    stats["skipped_invalid"] += 1
                    stats["removed_skipped"] += 1
                    continue
                op_type = str(op.get("type", "")).strip()

                if op_type == "create_coding_text":
                    ok, reason, row = self._can_undo_create_coding_text(cur, op)
                    if not ok:
                        if reason == "changed":
                            stats["skipped_changed"] += 1
                        elif reason == "missing":
                            stats["skipped_missing"] += 1
                        else:
                            stats["skipped_invalid"] += 1
                        keep_for_retry = self._should_keep_skipped_undo_operation(reason)
                        stats["skip_details"].append(self._format_undo_skip_detail(op, reason, keep_for_retry))
                        if keep_for_retry:
                            stats["blocked_retry"] += 1
                            remaining_operations.append(op)
                        else:
                            stats["removed_skipped"] += 1
                        continue
                    cur.execute("DELETE FROM code_text WHERE ctid=?", (int(row[0]),))
                    if cur.rowcount > 0:
                        stats["undone"] += 1
                        self._add_project_table_changes(project_table_changes, "code_text")
                    continue

                if op_type == "create_case_text":
                    ok, reason, row = self._can_undo_create_case_text(cur, op)
                    if not ok:
                        if reason == "changed":
                            stats["skipped_changed"] += 1
                        elif reason == "missing":
                            stats["skipped_missing"] += 1
                        else:
                            stats["skipped_invalid"] += 1
                        keep_for_retry = self._should_keep_skipped_undo_operation(reason)
                        stats["skip_details"].append(self._format_undo_skip_detail(op, reason, keep_for_retry))
                        if keep_for_retry:
                            stats["blocked_retry"] += 1
                            remaining_operations.append(op)
                        else:
                            stats["removed_skipped"] += 1
                        continue
                    cur.execute("DELETE FROM case_text WHERE id=?", (int(row[0]),))
                    if cur.rowcount > 0:
                        stats["undone"] += 1
                        self._add_project_table_changes(project_table_changes, "case_text")
                    continue

                if op_type == "create_code":
                    ok, reason, row = self._can_undo_create_code(cur, op)
                    if not ok:
                        if reason == "changed":
                            stats["skipped_changed"] += 1
                        elif reason == "missing":
                            stats["skipped_missing"] += 1
                        else:
                            stats["skipped_invalid"] += 1
                        keep_for_retry = self._should_keep_skipped_undo_operation(reason)
                        stats["skip_details"].append(self._format_undo_skip_detail(op, reason, keep_for_retry))
                        if keep_for_retry:
                            stats["blocked_retry"] += 1
                            remaining_operations.append(op)
                        else:
                            stats["removed_skipped"] += 1
                        continue
                    cid = int(row[0])
                    coding_total, coding_non_ai = self._count_code_codings(cur, cid)
                    stats["deleted_code_codings"] += coding_total
                    stats["deleted_code_codings_non_ai"] += coding_non_ai
                    changed_tables = []
                    if self._table_exists("code_text"):
                        cur.execute("DELETE FROM code_text WHERE cid=?", (cid,))
                        if cur.rowcount > 0:
                            changed_tables.append("code_text")
                    if self._table_exists("code_av"):
                        cur.execute("DELETE FROM code_av WHERE cid=?", (cid,))
                        if cur.rowcount > 0:
                            changed_tables.append("code_av")
                    if self._table_exists("code_image"):
                        cur.execute("DELETE FROM code_image WHERE cid=?", (cid,))
                        if cur.rowcount > 0:
                            changed_tables.append("code_image")
                    cur.execute("DELETE FROM code_name WHERE cid=?", (cid,))
                    if cur.rowcount > 0:
                        stats["undone"] += 1
                        self._add_project_table_changes(project_table_changes, "code_name", *changed_tables)
                    continue

                if op_type == "create_case":
                    ok, reason, row = self._can_undo_create_case(cur, op)
                    if not ok:
                        if reason == "changed":
                            stats["skipped_changed"] += 1
                        elif reason == "missing":
                            stats["skipped_missing"] += 1
                        else:
                            stats["skipped_invalid"] += 1
                        keep_for_retry = self._should_keep_skipped_undo_operation(reason)
                        stats["skip_details"].append(self._format_undo_skip_detail(op, reason, keep_for_retry))
                        if keep_for_retry:
                            stats["blocked_retry"] += 1
                            remaining_operations.append(op)
                        else:
                            stats["removed_skipped"] += 1
                        continue
                    caseid = int(row[0])
                    cur.execute("DELETE FROM cases WHERE caseid=?", (caseid,))
                    if cur.rowcount > 0:
                        stats["undone"] += 1
                        self._add_project_table_changes(project_table_changes, "cases")
                    continue

                if op_type in ("create_case_attribute", "create_document_attribute"):
                    ok, reason, row = self._can_undo_create_attribute(cur, op)
                    if not ok:
                        if reason == "changed":
                            stats["skipped_changed"] += 1
                        elif reason == "missing":
                            stats["skipped_missing"] += 1
                        else:
                            stats["skipped_invalid"] += 1
                        keep_for_retry = self._should_keep_skipped_undo_operation(reason)
                        stats["skip_details"].append(self._format_undo_skip_detail(op, reason, keep_for_retry))
                        if keep_for_retry:
                            stats["blocked_retry"] += 1
                            remaining_operations.append(op)
                        else:
                            stats["removed_skipped"] += 1
                        continue
                    attr_name = str(op.get("name", "")).strip()
                    attr_type = str(op.get("target_type", "")).strip()
                    cur.execute("DELETE FROM attribute WHERE name=? AND attr_type=?", (attr_name, attr_type))
                    cur.execute("DELETE FROM attribute_type WHERE name=?", (attr_name,))
                    if cur.rowcount > 0:
                        stats["undone"] += 1
                        self._add_project_table_changes(project_table_changes, "attribute", "attribute_type")
                    continue

                if op_type == "create_category":
                    ok, reason, row = self._can_undo_create_category(cur, op)
                    if not ok:
                        if reason == "changed":
                            stats["skipped_changed"] += 1
                        elif reason == "missing":
                            stats["skipped_missing"] += 1
                        else:
                            stats["skipped_invalid"] += 1
                        keep_for_retry = self._should_keep_skipped_undo_operation(reason)
                        stats["skip_details"].append(self._format_undo_skip_detail(op, reason, keep_for_retry))
                        if keep_for_retry:
                            stats["blocked_retry"] += 1
                            remaining_operations.append(op)
                        else:
                            stats["removed_skipped"] += 1
                        continue
                    catid = int(row[0])
                    cur.execute("UPDATE code_name SET catid=NULL WHERE catid=?", (catid,))
                    code_name_changed = cur.rowcount > 0
                    cur.execute("UPDATE code_cat SET supercatid=NULL WHERE supercatid=?", (catid,))
                    cur.execute("DELETE FROM code_cat WHERE catid=?", (catid,))
                    if cur.rowcount > 0:
                        stats["undone"] += 1
                        self._add_project_table_changes(project_table_changes, "code_cat")
                        if code_name_changed:
                            self._add_project_table_changes(project_table_changes, "code_name")
                    continue

                if op_type == "rename_category":
                    ok, reason, row = self._can_undo_rename_category(cur, op)
                    if not ok:
                        if reason == "changed":
                            stats["skipped_changed"] += 1
                        elif reason == "missing":
                            stats["skipped_missing"] += 1
                        else:
                            stats["skipped_invalid"] += 1
                        keep_for_retry = self._should_keep_skipped_undo_operation(reason)
                        stats["skip_details"].append(self._format_undo_skip_detail(op, reason, keep_for_retry))
                        if keep_for_retry:
                            stats["blocked_retry"] += 1
                            remaining_operations.append(op)
                        else:
                            stats["removed_skipped"] += 1
                        continue
                    cur.execute(
                        "UPDATE code_cat SET name=? WHERE catid=?",
                        (str(op.get("old_name", "")), int(row[0])),
                    )
                    if cur.rowcount > 0:
                        stats["undone"] += 1
                        self._add_project_table_changes(project_table_changes, "code_cat")
                    continue

                if op_type == "rename_code":
                    ok, reason, row = self._can_undo_rename_code(cur, op)
                    if not ok:
                        if reason == "changed":
                            stats["skipped_changed"] += 1
                        elif reason == "missing":
                            stats["skipped_missing"] += 1
                        else:
                            stats["skipped_invalid"] += 1
                        keep_for_retry = self._should_keep_skipped_undo_operation(reason)
                        stats["skip_details"].append(self._format_undo_skip_detail(op, reason, keep_for_retry))
                        if keep_for_retry:
                            stats["blocked_retry"] += 1
                            remaining_operations.append(op)
                        else:
                            stats["removed_skipped"] += 1
                        continue
                    cur.execute(
                        "UPDATE code_name SET name=? WHERE cid=?",
                        (str(op.get("old_name", "")), int(row[0])),
                    )
                    if cur.rowcount > 0:
                        stats["undone"] += 1
                        self._add_project_table_changes(project_table_changes, "code_name")
                    continue

                if op_type == "update_case":
                    ok, reason, row = self._can_undo_update_case(cur, op)
                    if not ok:
                        if reason == "changed":
                            stats["skipped_changed"] += 1
                        elif reason == "missing":
                            stats["skipped_missing"] += 1
                        else:
                            stats["skipped_invalid"] += 1
                        keep_for_retry = self._should_keep_skipped_undo_operation(reason)
                        stats["skip_details"].append(self._format_undo_skip_detail(op, reason, keep_for_retry))
                        if keep_for_retry:
                            stats["blocked_retry"] += 1
                            remaining_operations.append(op)
                        else:
                            stats["removed_skipped"] += 1
                        continue
                    before = op.get("before", {}) if isinstance(op.get("before", {}), dict) else {}
                    cur.execute(
                        "UPDATE cases SET name=?, memo=?, owner=? WHERE caseid=?",
                        (
                            str(before.get("name", "")),
                            str(before.get("memo", "")),
                            str(before.get("owner", "")),
                            int(row[0]),
                        ),
                    )
                    if cur.rowcount > 0:
                        stats["undone"] += 1
                        self._add_project_table_changes(project_table_changes, "cases")
                    continue

                if op_type in ("update_case_attributes", "update_document_attributes"):
                    ok, reason, rows = self._can_undo_update_attributes(cur, op)
                    if not ok:
                        if reason == "changed":
                            stats["skipped_changed"] += 1
                        elif reason == "missing":
                            stats["skipped_missing"] += 1
                        else:
                            stats["skipped_invalid"] += 1
                        keep_for_retry = self._should_keep_skipped_undo_operation(reason)
                        stats["skip_details"].append(self._format_undo_skip_detail(op, reason, keep_for_retry))
                        if keep_for_retry:
                            stats["blocked_retry"] += 1
                            remaining_operations.append(op)
                        else:
                            stats["removed_skipped"] += 1
                        continue
                    row_changed = False
                    changes = op.get("changes", [])
                    for change in reversed(changes):
                        if not isinstance(change, dict):
                            continue
                        before = change.get("before", {}) if isinstance(change.get("before", {}), dict) else {}
                        after = change.get("after", {}) if isinstance(change.get("after", {}), dict) else {}
                        attrid = int(after.get("attrid", before.get("attrid", -1)))
                        if bool(before.get("exists", False)):
                            cur.execute(
                                "UPDATE attribute SET value=?, owner=?, date=? WHERE attrid=?",
                                (
                                    str(before.get("value", "")),
                                    str(before.get("owner", "")),
                                    str(before.get("date", "")),
                                    attrid,
                                ),
                            )
                        else:
                            cur.execute("DELETE FROM attribute WHERE attrid=?", (attrid,))
                        if cur.rowcount > 0:
                            row_changed = True
                    if row_changed:
                        stats["undone"] += 1
                        self._add_project_table_changes(project_table_changes, "attribute")
                    continue

                if op_type == "move_category_tree":
                    ok, reason, row = self._can_undo_move_category_tree(cur, op)
                    if not ok:
                        if reason == "changed":
                            stats["skipped_changed"] += 1
                        elif reason == "missing":
                            stats["skipped_missing"] += 1
                        else:
                            stats["skipped_invalid"] += 1
                        keep_for_retry = self._should_keep_skipped_undo_operation(reason)
                        stats["skip_details"].append(self._format_undo_skip_detail(op, reason, keep_for_retry))
                        if keep_for_retry:
                            stats["blocked_retry"] += 1
                            remaining_operations.append(op)
                        else:
                            stats["removed_skipped"] += 1
                        continue
                    cur.execute(
                        "UPDATE code_cat SET supercatid=? WHERE catid=?",
                        (op.get("before", {}).get("supercatid", None), int(row[0])),
                    )
                    if cur.rowcount > 0:
                        stats["undone"] += 1
                        self._add_project_table_changes(project_table_changes, "code_cat")
                    continue

                if op_type == "move_code":
                    ok, reason, row = self._can_undo_move_code(cur, op)
                    if not ok:
                        if reason == "changed":
                            stats["skipped_changed"] += 1
                        elif reason == "missing":
                            stats["skipped_missing"] += 1
                        else:
                            stats["skipped_invalid"] += 1
                        keep_for_retry = self._should_keep_skipped_undo_operation(reason)
                        stats["skip_details"].append(self._format_undo_skip_detail(op, reason, keep_for_retry))
                        if keep_for_retry:
                            stats["blocked_retry"] += 1
                            remaining_operations.append(op)
                        else:
                            stats["removed_skipped"] += 1
                        continue
                    cur.execute(
                        "UPDATE code_name SET catid=?, supercid=? WHERE cid=?",
                        (
                            op.get("before", {}).get("catid", None),
                            op.get("before", {}).get("supercid", None),
                            int(row[0]),
                        ),
                    )
                    if cur.rowcount > 0:
                        stats["undone"] += 1
                        self._add_project_table_changes(project_table_changes, "code_name")
                    continue

                if op_type == "move_coding_text":
                    ok, reason, row = self._can_undo_move_coding_text(cur, op)
                    if not ok:
                        if reason == "changed":
                            stats["skipped_changed"] += 1
                        elif reason == "missing":
                            stats["skipped_missing"] += 1
                        else:
                            stats["skipped_invalid"] += 1
                        keep_for_retry = self._should_keep_skipped_undo_operation(reason)
                        stats["skip_details"].append(self._format_undo_skip_detail(op, reason, keep_for_retry))
                        if keep_for_retry:
                            stats["blocked_retry"] += 1
                            remaining_operations.append(op)
                        else:
                            stats["removed_skipped"] += 1
                        continue
                    cur.execute(
                        "UPDATE code_text SET cid=? WHERE ctid=?",
                        (int(op.get("before", {}).get("cid", -1)), int(row[0])),
                    )
                    if cur.rowcount > 0:
                        stats["undone"] += 1
                        self._add_project_table_changes(project_table_changes, "code_text")
                    continue

                if op_type in ("delete_category_tree", "delete_code", "delete_coding_text", "delete_case_text"):
                    ok, reason = self._can_restore_snapshot(cur, op)
                    if not ok:
                        if reason == "changed":
                            stats["skipped_changed"] += 1
                        else:
                            stats["skipped_invalid"] += 1
                        keep_for_retry = self._should_keep_skipped_undo_operation(reason)
                        stats["skip_details"].append(self._format_undo_skip_detail(op, reason, keep_for_retry))
                        if keep_for_retry:
                            stats["blocked_retry"] += 1
                            remaining_operations.append(op)
                        else:
                            stats["removed_skipped"] += 1
                        continue
                    self._restore_snapshot(cur, op)
                    stats["undone"] += 1
                    self._add_project_table_changes(project_table_changes, *self._snapshot_changed_table_names(op))
                    continue

                stats["skipped_invalid"] += 1
                stats["skip_details"].append(self._format_undo_skip_detail(op, "invalid", False))
                stats["removed_skipped"] += 1

            self.app.conn.commit()
            self.app.delete_backup = False
            if len(project_table_changes) > 0:
                self._emit_project_table_changes(sorted(project_table_changes), source="ai_agent_undo")
        except Exception:
            self.app.conn.rollback()
            raise
        remaining_operations.reverse()
        stats["remaining_operations"] = remaining_operations
        return stats

    def undo_ai_agent_changes(self):
        """Undo one or more selected AI-agent change sets from the current app session."""

        history = self._ensure_ai_change_history()
        options = []
        for item in history:
            if not isinstance(item, dict):
                continue
            ops = item.get("operations", [])
            if isinstance(ops, list) and len(ops) > 0:
                self._refresh_ai_change_set_name(item, allow_db_lookup=True, use_relative_time=True)
                options.append(item)
        if len(options) == 0:
            Message(self.app, _("Undo AI changes"), _("No AI changes available to undo.")).exec()
            return

        ui = DialogSelectItems(self.app, options, _("Select AI changes to undo"), "multiple")
        ui.ui.listView.setStyleSheet(self._ai_change_list_stylesheet(ui.ui.listView))
        ui.ui.listView.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        ui.ui.listView.clearSelection()
        ui.ui.listView.setCurrentIndex(QtCore.QModelIndex())
        QtCore.QTimer.singleShot(0, lambda: ui.ui.listView.clearSelection())
        QtCore.QTimer.singleShot(0, lambda: ui.ui.listView.setCurrentIndex(QtCore.QModelIndex()))
        
        ok = ui.exec()
        if not ok:
            return
        selected = ui.get_selected()
        if not isinstance(selected, list) or len(selected) == 0:
            return
        selected_sets = [item for item in options if item in selected]
        if len(selected_sets) == 0:
            return

        confirm_text = _("Undo {count} AI change set(s)?").format(count=len(selected_sets))
        impact_lines = []
        for item in selected_sets:
            impact_text = self._build_ai_change_impact_text(item)
            if impact_text == "":
                continue
            item_name = str(item.get("name", "")).strip()
            if item_name != "":
                impact_lines.append(item_name)
            impact_lines.append(impact_text)
        if len(impact_lines) > 0:
            confirm_text += "\n\n" + "\n\n".join(impact_lines)
        confirm_text += "\n\n" + _("Do you want to continue?")
        confirm = DialogConfirmDelete(self.app, confirm_text, _("Undo AI changes"))
        if not confirm.exec():
            return

        stats = {
            "undone": 0,
            "skipped_changed": 0,
            "skipped_missing": 0,
            "skipped_invalid": 0,
            "blocked_retry": 0,
            "removed_skipped": 0,
            "deleted_code_codings": 0,
            "deleted_code_codings_non_ai": 0,
        }
        skip_details = []
        undone_count = 0
        for item in selected_sets:
            item_stats = self._undo_ai_change_set(item)
            for key in stats.keys():
                stats[key] += int(item_stats.get(key, 0))
            item_skip_details = item_stats.get("skip_details", [])
            if isinstance(item_skip_details, list):
                skip_details.extend([detail for detail in item_skip_details if str(detail).strip() != ""])
            remaining_operations = item_stats.get("remaining_operations", [])
            if item in history:
                if isinstance(remaining_operations, list) and len(remaining_operations) > 0:
                    item["operations"] = remaining_operations
                    self._refresh_ai_change_set_name(item, allow_db_lookup=True, use_relative_time=True)
                else:
                    history.remove(item)
            undone_count += 1

        msg = _("Undo AI changes") + "\n"
        msg += _("Selected change sets: ") + str(undone_count) + "\n"
        msg += _("Undone operations: ") + str(stats.get("undone", 0)) + "\n"
        skipped = int(stats.get("skipped_changed", 0)) + int(stats.get("skipped_missing", 0)) + int(stats.get("skipped_invalid", 0))
        if skipped > 0:
            msg += _("Skipped operations: ") + str(skipped) + "\n"
        blocked_retry = int(stats.get("blocked_retry", 0))
        if blocked_retry > 0:
            msg += _("Blocked operations kept for retry: ") + str(blocked_retry) + "\n"
        removed_skipped = int(stats.get("removed_skipped", 0))
        if removed_skipped > 0:
            msg += _("Skipped operations removed from the list: ") + str(removed_skipped) + "\n"
        non_ai_loss = int(stats.get("deleted_code_codings_non_ai", 0))
        if non_ai_loss > 0:
            msg += _("Warning: removed codings not owned by 'AI Agent': ") + str(non_ai_loss) + "\n"
        if len(skip_details) > 0:
            msg += "\n" + _("Undo details:") + "\n\n" + "\n\n".join(skip_details)
        if self.parent_text_edit is not None:
            try:
                self.parent_text_edit.append(msg)
            except Exception:
                pass
        Message(self.app, _("Undo AI changes"), msg).exec()

    # Icons (https://pictogrammers.com/library/mdi/)
    def code_analysis_icon(self):
        return qta.icon('mdi6.tag-text-outline', color=self.app.highlight_color())

    def topic_analysis_icon(self):
        return self.topic_exploration_icon()

    def topic_exploration_icon(self):
        return qta.icon('mdi6.star-outline', color=self.app.highlight_color())

    def search_icon(self):
        return qta.icon('mdi6.magnify', color=self.app.highlight_color())
    
    def text_analysis_icon(self):
        return qta.icon('mdi6.text-box-outline', color=self.app.highlight_color())

    def general_chat_icon(self):
        return qta.icon('mdi6.chat-question-outline', color=self.app.highlight_color())

    def prompt_scope_icon(self):
        return qta.icon('mdi6.folder-open-outline', color=self.app.highlight_color())

    def prompt_icon(self):
        return qta.icon('mdi6.script-text-outline', color=self.app.highlight_color())

    def _migrate_legacy_prompts_for_current_scope(self) -> None:
        """One-time import of legacy user/project prompts into Markdown files."""

        try:
            catalog = AiAgentPromptsCatalog(self.app)
            results = catalog.migrate_legacy_prompts_once()
        except Exception as err:
            logger.warning("Legacy AI prompt migration failed: %s", err)
            self.parent_text_edit.append(_('AI: Legacy prompt migration failed.'))
            return

        for scope in ("user", "project"):
            scope_result = results.get(scope, {})
            migrated = int(scope_result.get("migrated", 0) or 0)
            if migrated > 0:
                self.parent_text_edit.append(
                    _('AI: Migrated {count} {scope} prompts to Markdown format.').format(
                        count=migrated,
                        scope=scope,
                    )
                )
        
    def init_llm(self, main_window, rebuild_vectorstore=False, enable_ai=False):  
        try:
            self.main_window = main_window      
            self._migrate_legacy_prompts_for_current_scope()
            if enable_ai or self.app.settings['ai_enable'] == 'True':
                self.parent_text_edit.append(_('AI: Starting up...'))
                QtWidgets.QApplication.processEvents()  # update ui
                self._status = 'starting'

                # init LLMs
                # set_llm_cache(InMemoryCache())
                if int(self.app.settings['ai_model_index']) >= len(self.app.ai_models): # model index out of range
                    self.app.settings['ai_model_index'] = -1
                if int(self.app.settings['ai_model_index']) < 0:
                    msg = _('AI: In the follwoing window, please set up the AI model.')
                    Message(self.app, _('AI Setup'), msg).exec()

                    main_window.change_settings(section='AI', enable_ai=True)
                    if int(self.app.settings['ai_model_index']) < 0:
                        # Still no model selected, disable AI:
                        self.app.settings['ai_enable'] = 'False'
                        self.parent_text_edit.append(_('AI: No model selected, AI is disabled.'))
                        self._status = ''
                        return
                    else: 
                        # Success, model was selected. But since the "change_settings" function will start 
                        # a new "init_llm" anyway, we are going to quit here
                        return    
                
                curr_model = self.app.ai_models[int(self.app.settings['ai_model_index'])]
                                                    
                # OpenAI: Check for outdated models:            
                if curr_model['large_model'].find('gpt-4-turbo') > -1:
                    self.parent_text_edit.append(_('AI: You are still using the outdated GPT-4 turbo. Consider switching to a newer model, such as GPT 4.1. Go to Project > Settings to change the AI profile and model.'))
                
                # Anthropic: Check for outdated models
                if curr_model['large_model'] == 'claude-opus-4-20250514':
                    self.parent_text_edit.append(_('AI: You are using the outdated Claude Opus 4 model from Anthropic. Consider switching to a newer model, such as Opus 4.1. Go to Project > Settings to change the AI profile and model.'))
                
                large_model = curr_model['large_model']
                self.large_llm_context_window = int(curr_model['large_model_context_window'])
                fast_model = curr_model['fast_model']
                self.fast_llm_context_window = int(curr_model['fast_model_context_window'])
                ensure_chatgpt_oauth_profile_defaults(curr_model)
                api_base = curr_model['api_base']
                api_key = curr_model['api_key']
                is_chatgpt_oauth = is_chatgpt_oauth_api_base(api_base)
                if api_key == '' and not is_chatgpt_oauth:
                    msg = _('Please enter an API-key for the AI in the following dialog.')
                    Message(self.app, _('AI API-key'), msg).exec()
                    main_window.change_settings(section='AI', enable_ai=True)
                    curr_model = self.app.ai_models[int(self.app.settings['ai_model_index'])]
                    ensure_chatgpt_oauth_profile_defaults(curr_model)
                    if curr_model['api_key'] == '':
                        # still no API-key, disable AI:
                        self.app.settings['ai_enable'] = 'False'
                        self.parent_text_edit.append(_('AI: No API key set, AI is disabled.'))
                        self._status = ''
                        return
                    else: 
                        # Success, API-key was set. But since the "change_settings" function will start 
                        # a new "init_llm" anyways, we are going to quit here
                        return    
                if large_model == '' or fast_model == '':
                    msg = _('In the following dialog, go to "Advanced AI Options" and select a large and a fast AI model (both can be the same).')
                    Message(self.app, _('AI Model Selection'), msg).exec()
                    main_window.change_settings(section='advanced AI', enable_ai=True)
                    curr_model = self.app.ai_models[int(self.app.settings['ai_model_index'])]
                    if curr_model['large_model'] == '' or curr_model['fast_model'] == '':
                        # still no model chosen, disable AI:
                        self.app.settings['ai_enable'] = 'False'
                        self.parent_text_edit.append(_('AI: No large/fast model selected, AI is disabled.'))
                        self._status = ''
                        return
                    else: 
                        # Success, models were selected. But since the "change_settings" function will start 
                        # a new "init_llm" anyways, we are going to quit here
                        return
                temp = float(self.app.settings.get('ai_temperature', '1.0'))
                top_p = float(self.app.settings.get('ai_top_p', '1.0'))
                timeout = float(self.app.settings.get('ai_timeout', '30.0'))
                self.app.settings['ai_timeout'] = str(timeout)
                if api_base.find('azure.com') != -1:  # using Microsoft Azure
                    is_azure = True
                    large_llm_params = {
                        'azure_endpoint': api_base,
                        'azure_deployment': large_model,    
                        'api_version': '2024-12-01-preview',
                        'api_key': api_key,
                        'temperature': temp,
                        'top_p': top_p,
                        'max_tokens': None,
                        'timeout': timeout,
                        'max_retries': 2,
                        'cache': False,
                        'streaming': True
                    }        
                    fast_llm_params = large_llm_params.copy()
                    fast_llm_params['model'] = fast_model
                elif is_chatgpt_oauth:
                    is_azure = False
                    large_llm_params = {
                        'model': large_model,
                        'cache': False,
                        'temperature': temp,
                        'timeout': timeout,
                    }
                    fast_llm_params = large_llm_params.copy()
                    fast_llm_params['model'] = fast_model
                else: # OpenAI or compatible API
                    is_azure = False
                    large_llm_params = {
                        'model': large_model, 
                        'openai_api_key': api_key, 
                        'openai_api_base': api_base, 
                        'cache': False,
                        'temperature': temp,
                        'top_p': top_p,
                        'streaming': True,
                        'timeout': timeout,
                    }   
                    fast_llm_params = large_llm_params.copy()
                    fast_llm_params['model'] = fast_model
                    
                if 'reasoning_effort' in curr_model and curr_model['reasoning_effort'] in ['low', 'medium', 'high']:
                    large_llm_params['reasoning_effort'] = curr_model['reasoning_effort']
                
                if large_model.lower().find('claude') != -1:  # Anthropic
                    # omitting top_p, since Antrhopic does not accept temperature and top_p at the same time
                    try:
                        large_llm_params.pop('top_p')
                        fast_llm_params.pop('top_p')
                    except:
                        pass

                self._large_llm_params = dict(large_llm_params)
                self._fast_llm_params = dict(fast_llm_params)
                if is_azure:
                    self._large_llm_factory = AzureChatOpenAI
                    self._fast_llm_factory = AzureChatOpenAI
                elif is_chatgpt_oauth:
                    self._large_llm_factory = _ChatOpenAICodex
                    self._fast_llm_factory = _ChatOpenAICodex
                else:
                    self._large_llm_factory = ChatOpenAI
                    self._fast_llm_factory = ChatOpenAI
                self._large_reasoning_effort = str(curr_model.get('reasoning_effort', '')).strip().lower()
                self._fast_reasoning_effort = ''
                
                self.app.settings['ai_enable'] = 'True'
                
                # init vectorstore
                if not self.sources_vectorstore.is_open():
                    self.sources_vectorstore.init_vectorstore(rebuild_vectorstore)
                else:
                    self._status = ''
                    self.parent_text_edit.append(_('AI: Ready'))
            else:
                self.close()
        except Exception as e:
            type_e = type(e)
            value = e
            tb_obj = e.__traceback__
            # log the exception and show error msg
            qt_exception_hook.exception_hook(type_e, value, tb_obj)
            self.close()
            self.app.settings['ai_enable'] = 'False'
            msg = _('An error occured during AI initialization. The AI features will be disabled. Click on Project > Settings to reenable them.')
            Message(self.app, _('AI Initialization'), msg, 'Information').exec()
        
    def close(self):
        self._status = 'closing'
        self.cancel_all_runs(wait_ms=5000)
        self.sources_vectorstore.close()
        self._large_llm_params = None
        self._fast_llm_params = None
        self._large_llm_factory = None
        self._fast_llm_factory = None
        with self._runs_lock:
            self._runs_by_id.clear()
            self._latest_run_by_scope.clear()
            self._last_status_by_scope.clear()
            self._last_streaming_output_by_run.clear()
        with self._unsupported_llm_params_lock:
            self._unsupported_llm_params_by_key.clear()
        self._status = ''
        
    def cancel(self, ask: bool) -> bool:
        if not self.is_busy():
            return True
        if ask:
            msg = _('Do you really want to cancel the AI operation?')
            msg_box = Message(self.app, 'AI Cancel', msg)
            msg_box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
            reply = msg_box.exec()
            if reply == QtWidgets.QMessageBox.StandardButton.No:
                return False
        success = self.cancel_all_runs(wait_ms=5000)
        if ask and not success:
            msg = _('The AI operation could not be aborted immediately. It may take a moment for the AI to be ready again.')
            msg_box = Message(self.app, 'AI Cancel', msg)
            msg_box.exec()
        return success

    def get_status(self) -> str:
        """Return the status of the AI system:
        - 'disabled'
        - 'starting' (in the process of loading all its modules)
        - 'no data' (the vectorstore is not available, propably because no project is open)
        - 'reading data' (in the process of adding empirical douments to its internal memory)
        - 'busy' (in the process of sending a prompt to the LLM and streaming the response)
        - 'ready' (fully loaded and idle, ready for a task)
        - 'closing' (in the process of shutting down)
        - 'closed' 
        """
        if self._status != '':
            return self._status  # 'starting' and 'closing' are set by the corresponding procedures
        elif self.app.settings['ai_enable'] != 'True':
            return 'disabled'
        elif self.sources_vectorstore is not None and self.sources_vectorstore.ai_worker_running():
            return 'reading data'
        elif self.sources_vectorstore is None or not self.sources_vectorstore.is_open():
            return 'no data'
        elif self._large_llm_factory is None or self._fast_llm_factory is None or \
                self._large_llm_params is None or self._fast_llm_params is None:
            return 'closed'
        elif self._has_blocking_active_runs():
            return 'busy'
        else:
            return 'ready'
    
    def is_busy(self) -> bool:
        return self.get_status() == 'busy'

    def is_ready(self):
        return self.get_status() == 'ready'
    
    def get_default_system_prompt(self) -> str:
        p = 'You are assisting a team of qualitative social researchers.'
        project_memo = extract_ai_memo(self.app.get_project_memo())
        if self.app.settings.get('ai_send_project_memo', 'True') == 'True' and len(project_memo) > 0:
            p += f' Here is some background information about the research project the team is working on:\n{project_memo}'
        return p
        
    def _handle_run_progress(self, msg):
        self.run_progress_msg = self.run_progress_msg + '\n' + msg
        
    def _handle_run_error(self, exception_type, value, tb_obj):
        try:
            if exception_type is AICancelled or isinstance(value, AICancelled):
                return
            auth_message = ''
            if isinstance(value, BaseException):
                auth_message = self._chatgpt_oauth_user_error(value)
            if auth_message != '':
                msg = _('AI Error:\n') + auth_message
            else:
                value_text = html_to_text(self._safe_to_text(value))
                msg = _('AI Error:\n')
                msg += exception_type.__name__ + ': ' + str(value_text)
            tb = '\n'.join(traceback.format_tb(tb_obj))
            logger.error(_("Uncaught exception: ") + msg + '\n' + tb)
            # Trigger message box show
            qt_exception_hook._exception_caught.emit(msg, tb)
        except Exception as err:
            logger.error(_("Uncaught exception while handling AI error: ") + self._safe_to_text(err))
    
    def _abort_active_runs(self):
        self.cancel_all_runs(wait_ms=0)
    
    def start_stream(self, messages, result_callback=None, progress_callback=None,
                     streaming_callback=None, error_callback=None, model_kind: str = 'large',
                     scope_type: str = '', scope_id=None, group_id: str = '', parent_run_id: str = ''):
        """Calls the LLM in a background thread and streams back the results 

        Args:
            messages: list of AI messages (e.g. a conversation)
            result_callback (optional): Defaults to None.
            progress_callback (optional): Defaults to None.
            streaming_callback (optional): Defaults to None.
            error_callback (optional): Defaults to None.
        """
        self.run_progress_msg = ''
        self.run_progress_count = -1
        try:
            run_context = self._create_run_context(
                model_kind=model_kind,
                purpose='stream',
                scope_type=scope_type,
                scope_id=scope_id,
                group_id=group_id,
                parent_run_id=parent_run_id,
            )
        except Exception as err:
            auth_message = self._chatgpt_oauth_user_error(err)
            if auth_message != '':
                Message.warning(self.app, _('Authentication'), auth_message)
                return ''
            raise
        run_context.worker_type = 'stream'
        self._register_run_context(run_context)
        worker = Worker(self._run_stream_worker, run_context=run_context, messages=messages)
        if result_callback is not None: 
            worker.signals.result.connect(result_callback)
        if progress_callback is not None:
            worker.signals.progress.connect(progress_callback)
        if streaming_callback is not None:
            worker.signals.streaming.connect(streaming_callback)
        if error_callback is not None:
            worker.signals.error.connect(error_callback)
        else:
            worker.signals.error.connect(self._handle_run_error)
        self.threadpool.start(worker)
        return run_context.run_id

    def _run_stream_worker(self, signals, run_context: AiRunContext, messages):
        self._set_current_run_context(run_context)
        self._update_run_status(run_context.run_id, 'running')
        run_context.streaming_output = ''
        req_id = self.log_llm_request(run_context.llm, messages, context='run_stream')
        stream_iter = None
        attempted_params = set()
        try:
            while True:
                active_llm = run_context.llm
                try:
                    self._raise_if_run_canceled(run_context)
                    stream_iter = active_llm.stream(messages)
                    run_context.stream_iter = stream_iter
                    for chunk in stream_iter:
                        if run_context.cancel_event.is_set():
                            break  # cancel the streaming
                        chunk_text = llm_content_to_text(getattr(chunk, 'content', ''))
                        run_context.streaming_output += chunk_text
                        if signals is not None:
                            if signals.streaming is not None:
                                signals.streaming.emit(chunk_text)
                            if signals.progress is not None:
                                self.run_progress_count += len(chunk_text)
                                signals.progress.emit(str(self.run_progress_count))
                    if run_context.cancel_event.is_set():
                        self._update_run_status(run_context.run_id, 'canceled')
                    break
                except Exception as err:
                    if run_context.cancel_event.is_set():
                        self._update_run_status(run_context.run_id, 'canceled')
                        res = run_context.streaming_output
                        self.clear_streaming_output(run_context.run_id)
                        return res
                    if run_context.streaming_output == '':
                        retried, _ = self._retry_after_unsupported_parameter_error(
                            run_context,
                            None,
                            err,
                            attempted_params,
                            req_id,
                            context='run_stream',
                        )
                        if retried:
                            continue
                    self._update_run_status(run_context.run_id, 'errored', self._safe_to_text(err))
                    self.log_llm_error(req_id, run_context.llm, err, context='run_stream')
                    # Some providers emit malformed trailing streaming events after content is already complete.
                    # Prefer returning the accumulated text instead of failing the whole turn.
                    if run_context.streaming_output != '' and self._allow_partial_stream_result_after_error(err):
                        res = run_context.streaming_output
                        self.clear_streaming_output(run_context.run_id)
                        if not run_context.cancel_event.is_set():
                            self.log_llm_response(req_id, run_context.llm, res, context='run_stream_partial')
                        return res
                    raise
                finally:
                    if stream_iter is not None and not run_context.cancel_event.is_set():
                        close_fn = getattr(stream_iter, "close", None)
                        if callable(close_fn):
                            try:
                                close_fn()
                            except Exception as close_err:
                                self.log_llm_error(req_id, active_llm, close_err, context='run_stream_close')
                    run_context.stream_iter = None
                    stream_iter = None
        finally:
            terminal_status = 'canceled' if run_context.cancel_event.is_set() else (
                'errored' if run_context.error_text != '' else 'finished'
            )
            self._finalize_run_context(run_context, terminal_status)
            self._clear_current_run_context()
        res = run_context.streaming_output
        self.clear_streaming_output(run_context.run_id)
        if not run_context.cancel_event.is_set():
            self.log_llm_response(req_id, run_context.llm, res, context='run_stream')
        return res

    def start_query(self, func, result_callback, *args, progress_callback=None,
                    model_kind: str = 'large', scope_type: str = '', scope_id=None,
                    group_id: str = '', parent_run_id: str = '', cancel_result=None, **kwargs):
        """Calls an AI related function in a background thread

        Args:
            func: the function to be called.  *args, **kwargs are handed over to this function. 
            result_callback: callback function
            progress_callback: callback function for progress/status updates
        """
        self.run_progress_msg = ''
        self.run_progress_count = -1
        try:
            run_context = self._create_run_context(
                model_kind=model_kind,
                purpose='query',
                scope_type=scope_type,
                scope_id=scope_id,
                group_id=group_id,
                parent_run_id=parent_run_id,
                cancel_result=cancel_result,
            )
        except Exception as err:
            auth_message = self._chatgpt_oauth_user_error(err)
            if auth_message != '':
                Message.warning(self.app, _('Authentication'), auth_message)
                return ''
            raise
        run_context.worker_type = 'query'
        self._register_run_context(run_context)
        worker = Worker(
            self._run_query_worker,
            run_context=run_context,
            target_func=func,
            target_args=args,
            target_kwargs=kwargs,
        )
        if result_callback is not None: 
            worker.signals.result.connect(result_callback)
        if progress_callback is not None:
            worker.signals.progress.connect(progress_callback)
        else:
            worker.signals.progress.connect(self._handle_run_progress)
        worker.signals.error.connect(self._handle_run_error)
        self.threadpool.start(worker)
        return run_context.run_id

    def _run_query_worker(self, signals, run_context: AiRunContext, target_func, target_args, target_kwargs):
        self._set_current_run_context(run_context)
        self._update_run_status(run_context.run_id, 'running')
        try:
            self._raise_if_run_canceled(run_context)
            call_kwargs = dict(target_kwargs) if isinstance(target_kwargs, dict) else {}
            call_kwargs['signals'] = signals
            result = target_func(*target_args, **call_kwargs)
            self._raise_if_run_canceled(run_context)
            return result
        except AICancelled:
            self._update_run_status(run_context.run_id, 'canceled')
            return run_context.cancel_result
        except Exception as err:
            self._update_run_status(run_context.run_id, 'errored', self._safe_to_text(err))
            raise
        finally:
            terminal_status = 'canceled' if run_context.cancel_event.is_set() else (
                'errored' if run_context.error_text != '' else 'finished'
            )
            self._finalize_run_context(run_context, terminal_status)
            self._clear_current_run_context()
                        
    def get_curr_language(self):
        """Determine the current language of the UI and/or the project.
        Used to instruct the AI answering in the correct language.
        """
        if self.app.settings.get('ai_language_ui', 'True') != 'True':
            lang = str(self.app.settings.get('ai_language', 'English')).strip()
            if lang == '':
                lang = 'English'
            return lang
        lang_code = str(self.app.settings.get('language', 'en')).strip()
        if lang_code == '':
            return 'English'
        locale = QtCore.QLocale(lang_code)
        lang = str(locale.nativeLanguageName()).strip()
        if lang == '':
            lang = str(QtCore.QLocale.languageToString(locale.language())).strip()
        if lang in ('', 'C', 'Default'):
            lang = 'English'
        return lang
    
    def _get_response_format_json_schema(self, schema_name: str, schema: dict):
        """Build a valid OpenAI-compatible response_format payload for JSON Schema mode."""
        if not schema_name or not isinstance(schema, dict) or len(schema) == 0:
            return None
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema,
                "strict": True
            }
        }

    def get_response_format_json_schema(self, schema_name: str, schema: dict):
        """Public helper for building JSON Schema response_format payloads."""
        return self._get_response_format_json_schema(schema_name, schema)
    
    def generate_code_descriptions(self, code_name, code_memo='') -> list:
        """Prompts the AI to create a list of 10 short descriptions of the given code.
        This is used to get a better basis for the semantic search in the vectorstore. 

        Args:
            code_name (str): the name of the code
            code_memo (str): a memo, optional

        Returns:
            list: list of strings
        """

        # example result: 
        json_result = """
{
    "descriptions": [
        "first description",
        "second description"
    ]
}
"""
        # validation schema:
        response_schema = {
            "type": "object",
            "properties": {
                "descriptions": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["descriptions"],
            "additionalProperties": False
        }

        """
        code_descriptions_prompt = [
            SystemMessage(
                content=self.get_default_system_prompt()
            ),
            HumanMessage(
                content=(f'We are searching for empirical data that fits a code named "{code_name}" '
                    f'with the following code memo: "{extract_ai_memo(code_memo)}". \n'
                    'Your task: Give back a list of 10 short descriptions of the meaning of this code. '
                    'Try to give a variety of diverse code-descriptions. Use simple language. '
                    f'Always answer in the following language: "{self.get_curr_language()}". Do not use numbers or bullet points. '
                    'Do not explain anything or repeat the code name, just give back the descriptive text. '
                    'Return the list as a valid JSON object in the following form:\n'
                    f'{json_result}')
            )
        ]
        """

        # revised version 7/25:
        code_descriptions_prompt = [
            SystemMessage(
                content=self.get_default_system_prompt() + '\n /no_think'
            ),
            HumanMessage(
                content=(f'We are searching for empirical data that fits a code named "{code_name}" '
                    f'with the following code memo: "{extract_ai_memo(code_memo)}". \n'
                    'Your task: Give back a list of up to 10 reformulated variants of the code, using '
                    'synonyms or directly related concepts. Also consider the memo, if available. '
                    'Try to give a variety of diverse reformulations. Use simple language.'
                    f'Always answer in the following language: "{self.get_curr_language()}". Do not use numbers or bullet points. '
                    'Do not explain anything or repeat the code name, just give back the list of variants. '
                    'Return the list as a valid JSON object in the following form:\n'
                    f'{json_result}')
            )
        ]

        logger.debug(_('AI generate_code_descriptions\n'))
        logger.debug(_('Prompt:\n') + str(code_descriptions_prompt))
        
        # callback to show percentage done    
        config = RunnableConfig()
        config['callbacks'] = [MyCustomSyncHandler(self)]
        self.run_progress_max = round(1000 / 4)  # estimated token count of the result (1000 chars)

        response_format = self._get_response_format_json_schema("code_descriptions", response_schema)
        try:
            res = self.invoke_with_logging(
                code_descriptions_prompt,
                response_format=response_format,
                config=config,
                context='generate_code_descriptions',
                fallback_without_response_format=True,
                fallback_exceptions=(BadRequestError, ValidationError),
                model_kind='large',
            )
        except AICancelled:
            return []
        response_text = llm_content_to_text(getattr(res, 'content', ''))
        logger.debug(response_text)
        res.content = strip_think_blocks(response_text)
        code_descriptions = list(json_repair.loads(str(res.content))['descriptions'])
        code_descriptions.insert(0, code_name) # insert the original as well
        return code_descriptions

    def retrieve_similar_data(self, result_callback, code_name, code_memo='', doc_ids=None,
                              scope_type: str = '', scope_id=None, group_id: str = '',
                              parent_run_id: str = ''):
        """Retrieve pieces of data from the vectorstore that are related to the given code.
        This function will be performed in the background, following these steps:
        1) Semantic extension: Let the LLM generate a list of 10 desciptions of the code in simple language
        2) Semantic search: Search in the vectorstore for data that has a semantic similarity to these descriptions
        3) Ranking: Sort the results for relevance

        Args:
            result_callback: Callback funtion, recieved the results as a list of documents type langchain_core.documents.base.Document
            code_name: str
            code_memo (optional): Defaults to ''.
            doc_ids (list, optional): Filter. If not None, only results from these documents will be returned. Defaults to [].
        """
        self.start_query(
            self._retrieve_similar_data,
            result_callback,
            code_name,
            code_memo,
            doc_ids,
            scope_type=scope_type,
            scope_id=scope_id,
            group_id=group_id,
            parent_run_id=parent_run_id,
            cancel_result=[],
        )

    def _retrieve_similar_data(self, code_name, code_memo='', doc_ids=None, progress_callback=None, signals=None) -> list:
        # Get a list of code descriptions from the llm
        if progress_callback is not None:
            progress_callback.emit(_('Stage 1:\nSearching data related to "') + code_name + '"') 
        descriptions = self.generate_code_descriptions(code_name, code_memo)
        self._raise_if_run_canceled()
        return self._retrieve_from_vectorstore(descriptions, doc_ids, progress_callback, signals)
    
    def _retrieve_from_vectorstore(self, search_strings, doc_ids=None, progress_callback=None, signals=None,
                                   score_threshold=0.5, k=50) -> list:
        # Use the list of search_strings to retrieve related data from the vectorstore
        try:
            threshold = float(score_threshold)
        except (TypeError, ValueError):
            threshold = 0.5
        threshold = max(0.0, min(threshold, 1.0))

        try:
            top_k = int(k)
        except (TypeError, ValueError):
            top_k = 50
        top_k = max(1, min(top_k, 500))

        search_kwargs = {'score_threshold': threshold, 'k': top_k}
        chunks_meta_list = []
        for _str in search_strings:
            self._raise_if_run_canceled()
            res = self.sources_vectorstore.faiss_db.similarity_search_with_relevance_scores(_str, **search_kwargs)
            if doc_ids is not None and len(doc_ids) > 0:
                # filter results by document ids
                res_filtered = []
                for chunk in res:
                    if chunk[0].metadata['id'] in doc_ids:
                        res_filtered.append(chunk)
                chunks_meta_list.append(res_filtered)
            else: 
                chunks_meta_list.append(res)

        # Consolidate and rank results:
        # Flatten the lists of chunks in chunks_lists and collect all the chunks in a master list.
        # Duplicate chunks are collected only once. The list is sorted by the frequency 
        # of a chunk counted over all lists + the similarity score that faiss returns.
        # This way, frequent and relevant chunks should be sorted to the top
        # (see: "Reciprocal Rank Fusion" (https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf))

        def chunk_unique_str(chunk_item):
            # helper
            chunk_key = str(chunk_item.metadata['id']) + ", "
            chunk_key += str(chunk_item.metadata['start_index']) + ", "
            return chunk_key
            
        # Flatten the lists and count the frequency of each chunk
        chunk_count_list = {}  # contains the chunk count
        chunk_master_list = []  # contains all chunks from all lists but no doubles
        for lst in chunks_meta_list:
            self._raise_if_run_canceled()
            for chunk in lst:            
                chunk_doc = chunk[0]
                chunk_score = chunk[1]
                chunk_str = chunk_unique_str(chunk_doc)
                chunk_in_count_list = chunk_count_list.get(chunk_str, None)
                if chunk_in_count_list: 
                    chunk_count_list[chunk_str] += 1 + chunk_score
                else:
                    chunk_count_list[chunk_str] = 1 + chunk_score
                    chunk_master_list.append(chunk_doc)
                    
        # add scores
        for chunk_doc in chunk_master_list:
            chunk_doc.metadata['score'] = chunk_count_list[chunk_unique_str(chunk_doc)]
        
        # Sort the common items by their score in descending order
        chunk_master_list.sort(key=lambda chunk: chunk.metadata['score'], reverse=True)
                                
        logger.debug('First 10 chunks of retrieved data:\n' + str(chunk_master_list[:10]))
        
        return chunk_master_list
    
    def search_analyze_chunk(self, result_callback, chunk, code_name, code_memo, search_prompt: AgentPromptRecord,
                             scope_type: str = '', scope_id=None, group_id: str = '',
                             parent_run_id: str = ''):
        """Letting the AI analyze a chunk of data, using the given prompt

        Args:
            result_callback: Callback function. Revieves the result in as a langchain_core.documents.base.Document with the folowing added fields:
                             - 'quote_start': the start_index of the quote
                             - 'quote': the selected quote
                             - 'interpretation': the interpretation of the LLM
                             If the AI discarded this chunk as not relevant, the returned document will be None 
            chunk: piece of data, type langchain_core.documents.base.Document
            code_name: str
            code_memo: str
            search_prompt (AgentPromptRecord): the prompt used for the analysis
        """
        self.start_query(
            self._search_analyze_chunk,
            result_callback,
            chunk,
            code_name,
            code_memo,
            search_prompt,
            scope_type=scope_type,
            scope_id=scope_id,
            group_id=group_id,
            parent_run_id=parent_run_id,
            cancel_result=None,
        )
        
    def _search_analyze_chunk(self, chunk, code_name, code_memo, search_prompt: AgentPromptRecord, progress_callback=None, signals=None):                
        if progress_callback is not None:
            progress_callback.emit(_("Stage 2:\nInspecting the data more closely..."))        

        # build up the prompt
        # example result:
        json_result = """
{
    "interpretation": "your brief reasoning",
    "related": true,
    "quote": "selected quote"
}
"""
        # validation schema:
        response_schema = {
            "type": "object",
            "properties": {
                "interpretation": {"type": "string"},
                "related": {"type": "boolean"},
                "quote": {"type": "string"}
            },
            "required": ["interpretation", "related", "quote"],
            "additionalProperties": False
        }

        prompt = [
            SystemMessage(
                content=self.get_default_system_prompt()
            ),
            HumanMessage(
                content= (f'You are discussing the code named "{code_name}" with the following code memo: "{extract_ai_memo(code_memo)}". \n'
                    'At the end of this message, you will find a chunk of empirical data. \n'
                    'Your task is to use the following instructions to analyze the chunk of empirical data and decide wether it relates to the given code or not. '
                    f'Instructions: "{search_prompt.content}". \n'
                    'Summarize your reasoning briefly in the field "interpretation" of the result. '
                    f'In this particular field, always answer in the language "{self.get_curr_language()}".\n'
                    'If you came to the conclusion that the chunk of data '
                    'is not related to the code, give back false in the field "related", otherwise true. '
                    'Use JSON booleans, not strings.\n'
                    'If the previous step resulted in \'True\', identify a quote from the chunk of empirical data that contains the part which is '
                    'relevant for the analysis of the given code. Include enough context so that the quote is comprehensable. '
                    'Give back this quote in the field "quote" exactly like in the original, '
                    'including errors. Do not leave anything out, do not translate the text or change it in any other way. '
                    'If you cannot identify a particular quote, return the whole chunk of empirical data in the field "quote".\n'
                    'If the previous step resulted in \'False\', return an empty quote ("") in the field "quote".\n'
                    f'Make sure to return nothing else but a valid JSON object in the following form: \n{json_result}.'
                    f'\n\nThe chunk of empirical data for you to analyze: \n"{chunk.page_content}"')
                )
            ]

        # callback to show percentage done    
        config = RunnableConfig()
        config['callbacks'] = [MyCustomSyncHandler(self)]
        self.run_progress_max = 130  # estimated average token count of the result
        
        # send the query to the llm 
        response_format = self._get_response_format_json_schema("search_analyze_chunk", response_schema)
        try:
            res = self.invoke_with_logging(
                prompt,
                response_format=response_format,
                config=config,
                context='search_analyze_chunk',
                fallback_without_response_format=True,
                fallback_exceptions=(BadRequestError, ValidationError),
                model_kind='large',
            )
        except AICancelled:
            return None
        response_text = llm_content_to_text(getattr(res, 'content', ''))
        res.content = strip_think_blocks(response_text)
        res_json = json_repair.loads(str(res.content))
        
        # analyse and format the answer
        if 'related' in res_json and res_json['related'] in [True, 'True', 'true'] and \
           'quote' in res_json and res_json['quote'] != '':  # found something
            # Adjust quote_start
            doc = {}
            doc['metadata'] = chunk.metadata          
            quote_start, quote_end = ai_quote_search(res_json['quote'], chunk.page_content)
            if quote_start > -1 < quote_end:
                doc['quote_start'] = quote_start + doc['metadata']['start_index']
                doc['quote'] = chunk.page_content[quote_start:quote_end]
            else:  # quote not found, make the whole chunk the quote
                doc['quote_start'] = doc['metadata']['start_index']
                doc['quote'] = chunk.page_content        
            doc['interpretation'] = res_json['interpretation']
        else:  # No quote means the AI discarded this chunk as not relevant
            doc = None
        return doc   

    
    
