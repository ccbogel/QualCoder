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
"""

import os
import logging
import traceback
from PyQt6 import QtWidgets
from PyQt6 import QtCore
import qtawesome as qta

from openai import OpenAI
from .ai_prompts import PromptItem
from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langchain_core.globals import set_llm_cache  # Unused
from langchain_community.cache import InMemoryCache  # Unused
from langchain_core.callbacks.base import BaseCallbackHandler
from langchain_core.runnables.config import RunnableConfig
from langchain_core.messages.human import HumanMessage
from langchain_core.messages.ai import AIMessage  # Unused
from langchain_core.messages.system import SystemMessage
from langchain_core.documents.base import Document  # Unused
from .ai_async_worker import Worker
from .ai_vectorstore import AiVectorstore
from .helpers import Message
from .error_dlg import qt_exception_hook
from .html_parser import html_to_text
import json_repair
import asyncio
import configparser
from Bio.Align import PairwiseAligner
from pydantic import ValidationError
import re

max_memo_length = 1500  # Maximum length of the memo send to the AI

path = os.path.abspath(os.path.dirname(__file__))
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
        

class MyCustomSyncHandler(BaseCallbackHandler):
    def __init__(self, ai_llm):
        self.ai_llm = ai_llm
        
    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.ai_llm.ai_async_progress_count += 1
    

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
    
def get_available_models(app, api_base: str, api_key: str) -> list:
    """Queries the API and returns a list of all AI models available from this provider."""
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
[ai_model_OpenAI GPT5.1 reasoning]
desc = Powerful model from OpenAI, with internal reasoning, for complex tasks.
	You need an API-key from OpenAI and have paid for credits in your account.
	OpenAI will charge a small amount for every use.
access_info_url = https://platform.openai.com/api-keys
large_model = gpt-5.1
large_model_context_window = 1000000
fast_model = gpt-5-mini
fast_model_context_window = 128000
reasoning_effort = medium
api_base = 
api_key = 

[ai_model_OpenAI GPT5.1 no reasoning]
desc = Powerful model from OpenAI, no reasoning, faster and cheaper.
	You need an API-key from OpenAI and have paid for credits in your account.
	OpenAI will charge a small amount for every use.
access_info_url = https://platform.openai.com/api-keys
large_model = gpt-5.1
large_model_context_window = 1000000
fast_model = gpt-5-mini
fast_model_context_window = 128000
reasoning_effort = low
api_base = 
api_key = 

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

[ai_model_Anthropic Claude Sonnet 4.5]
desc = Claude is a family of high quality models from Anthropic.
	You need an API-key from Anthropic and credits in your account.
	Anthropic will charge a small amount for every use.
access_info_url = https://console.anthropic.com/settings/keys
large_model = claude-sonnet-4-5
large_model_context_window = 200000
fast_model = claude-sonnet-4-5
fast_model_context_window = 200000
reasoning_effort = medium
api_base = https://api.anthropic.com/v1/
api_key = 

[ai_model_Google Gemini]
desc = Google offers several free and paid models on their servers.
	Select one in the Advanced AI options below.
	You need an API-key from Google.
access_info_url = https://ai.google.dev/gemini-api/docs
large_model = gemini-2.5-flash
large_model_context_window = 1000000
fast_model = gemini-2.5-flash
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

def update_ai_models(current_models: list, current_model_index: int) -> tuple[list, int]:
    """Update the AI model definitions, and add new models from the default set

    Args:
        current_models (list): the current list from config.ini
        current_model_index (int): the index of the currently selected model

    Returns:
        tuple[list, int]: updated list and current model index 
    """
    if current_model_index < 0 or current_model_index > (len(current_models) - 1):
        current_model_index = 0

    # add new models from the default model list
    default_models = get_default_ai_models()
    current_models_names = {model['name'] for model in current_models}
    for model in default_models:
        if not model['name'] in current_models_names:
            if model['name'] == 'OpenAI GPT5.1 reasoning': # insert this at the top, because it is the current default model
                current_models.insert(0, model)
                if current_model_index >= 0:
                    current_model_index += 1
            elif model['name'] == 'OpenAI GPT5.1 no reasoning' and len(current_models) > 1: # insert this at the second position
                current_models.insert(1, model)
                if current_model_index >= 1:
                    current_model_index += 1        
            else:
                current_models.append(model)
                
    # Blablador: update config (api base, model alias)
    curr_model = current_models[current_model_index]
    if curr_model['api_base'] == 'https://helmholtz-blablador.fz-juelich.de:8000/v1' and curr_model['large_model'] != 'alias-large':
        msg = _('You are using the "Blablador" service on an old server that will soon be disabled. '
                'Your configuration will be updated automatically. Please test if the AI access still works as expected. '
                'You might need to change to a different AI model in the settings dialog under "Advanced AI Settings".')
        QtWidgets.QMessageBox(parent=None, title=_('AI Setup'), text=msg).exec()
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
                    model['large_model'].lower().find('gpt-4.1') > -1 or \
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
    
    return current_models, current_model_index

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
    start_idx = orig_spans[0][0]
    end_idx = orig_spans[-1][1]
        
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
    ai_async_is_canceled = False
    ai_async_is_finished = False
    ai_async_is_errored = False
    ai_async_progress_msg = ''
    ai_async_progress_count = -1
    ai_async_progress_max = -1
    _status = ''   
    large_llm = None
    fast_llm = None
    large_llm_context_window = 128000
    fast_llm_context_window = 16385
    ai_streaming_output = ''
    sources_collection = 'qualcoder'  # name of the vectorstore collection for source documents
    
    def __init__(self, app, parent_text_edit):
        self.app = app
        self.parent_text_edit = parent_text_edit
        self.threadpool = QtCore.QThreadPool()
        self.threadpool.setMaxThreadCount(1)
        self.sources_vectorstore = AiVectorstore(self.app, self.parent_text_edit, self.sources_collection)

    # Icons (https://pictogrammers.com/library/mdi/)
    def code_analysis_icon(self):
        return qta.icon('mdi6.tag-text-outline', color=self.app.highlight_color())

    def topic_analysis_icon(self):
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
        
    def init_llm(self, main_window, rebuild_vectorstore=False, enable_ai=False):  
        try:
            self.main_window = main_window      
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
                api_base = curr_model['api_base']
                api_key = curr_model['api_key']
                if api_key == '':
                    msg = _('Please enter an API-key for the AI in the following dialog.')
                    Message(self.app, _('AI API-key'), msg).exec()
                    main_window.change_settings(section='AI', enable_ai=True)
                    curr_model = self.app.ai_models[int(self.app.settings['ai_model_index'])]
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
                    # raise the timeout for reasoning models
                    large_llm_params['timeout'] = (['low', 'medium', 'high'].index(curr_model['reasoning_effort']) + 1) * timeout
                
                if large_model.lower().find('claude') != -1:  # Anthropic
                    # omitting top_p, since Antrhopic does not accept temperature and top_p at the same time
                    try:
                        large_llm_params.pop('top_p')
                        fast_llm_params.pop('top_p')
                    except:
                        pass
                
                if is_azure:
                    self.large_llm = AzureChatOpenAI(**large_llm_params)
                    self.fast_llm = AzureChatOpenAI(**fast_llm_params)
                else:    
                    self.large_llm = ChatOpenAI(**large_llm_params)
                    self.fast_llm = ChatOpenAI(**fast_llm_params)

                self.ai_streaming_output = ''
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
        self.cancel(False)
        self.sources_vectorstore.close()
        self.large_llm = None
        self.fast_llm = None
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
        # cancel all waiting threads:
        self.threadpool.clear()
        self.ai_async_is_canceled = True
        self.threadpool.waitForDone(5000)
        if ask and self.is_busy():
            msg = _('The AI operation could not be aborted immediately. It may take a moment for the AI to be ready again.')
            msg_box = Message(self.app, 'AI Cancel', msg)
            msg_box.exec()            
        return True

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
        elif self.sources_vectorstore is None or not self.sources_vectorstore.is_open():
            return 'no data'
        elif self.sources_vectorstore.ai_worker_running():
            return 'reading data'
        elif self.large_llm is None or self.fast_llm is None:
            return 'closed'
        elif self.threadpool.activeThreadCount() > 0:
            return 'busy'
        else:
            return 'ready'
    
    def is_busy(self) -> bool:
        return self.get_status() == 'busy'
        # return self.threadpool.activeThreadCount() > 0

    def is_ready(self):
        return self.get_status() == 'ready'
        #return (self.sources_vectorstore is not None) and \
        #            (self.sources_vectorstore.is_ready()) and \
        #            (self.large_llm is not None) and \
        #            (self.fast_llm is not None) and \
        #            (not self.is_busy())
    
    def get_default_system_prompt(self) -> str:
        p = 'You are assisting a team of qualitative social researchers.'
        project_memo = extract_ai_memo(self.app.get_project_memo())
        if self.app.settings.get('ai_send_project_memo', 'True') == 'True' and len(project_memo) > 0:
            p += f' Here is some background information about the research project the team is working on:\n{project_memo}'
        return p
        
    def _ai_async_progress(self, msg):
        self.ai_async_progress_msg = self.ai_async_progress_msg + '\n' + msg
        
    def _ai_async_error(self, exception_type, value, tb_obj):
        self.ai_async_is_errored = True
        value = html_to_text(str(value))
        msg = _('AI Error:\n')
        msg += exception_type.__name__ + ': ' + str(value)
        tb = '\n'.join(traceback.format_tb(tb_obj))
        logger.error(_("Uncaught exception: ") + msg + '\n' + tb)
        # Trigger message box show
        qt_exception_hook._exception_caught.emit(msg, tb)        

    def _ai_async_finished(self):
        self.ai_async_is_finished = True
    
    def _ai_async_abort_button_clicked(self):
        self.ai_async_is_canceled = True
    
    def ai_async_stream(self, llm, messages, result_callback=None, progress_callback=None, streaming_callback=None, error_callback=None):       
        """Calls the LLM in a background thread and streams back the results 

        Args:
            llm: can be either self.fast_llm or self.large_llm
            messages: list of AI messages (e.g. a conversation)
            result_callback (optional): Defaults to None.
            progress_callback (optional): Defaults to None.
            streaming_callback (optional): Defaults to None.
            error_callback (optional): Defaults to None.
        """
        # start async worker 
        self.ai_async_is_finished = False
        self.ai_async_is_errored = False
        self.ai_async_progress_msg = ''
        self.ai_async_progress_count = -1
        worker = Worker(self._ai_async_stream, llm=llm, messages=messages)
        if result_callback is not None: 
            worker.signals.result.connect(result_callback)
        if progress_callback is not None:
            worker.signals.progress.connect(progress_callback)
        if streaming_callback is not None:
            worker.signals.streaming.connect(streaming_callback)
        if error_callback is not None:
            worker.signals.error.connect(error_callback)
        else:
            worker.signals.error.connect(self._ai_async_error)
        self.threadpool.start(worker)

    def _ai_async_stream(self, signals, llm, messages):
        self.ai_async_is_canceled = False
        self.ai_streaming_output = ''
        for chunk in llm.stream(messages):
            if self.ai_async_is_canceled:
                break  # cancel the streaming
            else:
                self.ai_streaming_output += chunk.content
                if signals is not None:
                    if signals.streaming is not None:
                        signals.streaming.emit(str(chunk.content))
                    if signals.progress is not None:
                        self.ai_async_progress_count += len(chunk.content)
                        signals.progress.emit(str(self.ai_async_progress_count))
        res = self.ai_streaming_output
        self.ai_streaming_output = ''
        return res

    def ai_async_query(self, func, result_callback, *args, **kwargs):        
        """Calls an AI related function in a background thread

        Args:
            func: the function to be called.  *args, **kwargs are handed over to this function. 
            result_callback: callback function
        """
        self.ai_async_is_canceled = False
        
        # start async worker
        self.ai_async_is_finished = False
        self.ai_async_is_errored = False
        self.ai_async_progress_msg = ''
        self.ai_async_progress_count = -1
        worker = Worker(func, *args, **kwargs)  # Any other args, kwargs are passed to the run function
        if result_callback is not None: 
            worker.signals.result.connect(result_callback)
        worker.signals.finished.connect(self._ai_async_finished)
        worker.signals.progress.connect(self._ai_async_progress)
        worker.signals.error.connect(self._ai_async_error)
        self.threadpool.start(worker)
                        
    def get_curr_language(self):
        """Determine the current language of the UI and/or the project. 
        Used to instruct the AI answering in the correct language. 
        """ 
        if self.app.settings.get('ai_language_ui', 'True') == 'True':
            # get ui language
            lang_long = {"de": "Deutsch", "en": "English", "es": "Español", "fr": "Français", "it": "Italiano", "pt": "Português"}
            lang = lang_long[self.app.settings['language']] 
            if lang is None:
                lang = 'English'
        else:
            lang = self.app.settings.get('ai_language', 'English')
        return lang
    
    def generate_code_descriptions(self, code_name, code_memo='') -> list:
        """Prompts the AI to create a list of 10 short descriptions of the given code.
        This is used to get a better basis for the semantic search in the vectorstore. 

        Args:
            code_name (str): the name of the code
            code_memo (str): a memo, optional

        Returns:
            list: list of strings
        """

        json_result = {
            "descriptions": [
                "first description",
                "second description",
                ...
            ]
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
        self.ai_async_progress_max = round(1000 / 4)  # estimated token count of the result (1000 chars)

        try:
            res = self.large_llm.invoke(code_descriptions_prompt, response_format={"type": "json_object"}, config=config)
        except ValidationError as e:
            # The returned JSON was malformed. Try it without validation and hope that "json_repair" will fix it below 
            logger.debug(e)
            res = self.large_llm.invoke(code_descriptions_prompt, config=config)            
        logger.debug(str(res.content))
        res.content = strip_think_blocks(res.content)
        code_descriptions = list(json_repair.loads(str(res.content))['descriptions'])
        code_descriptions.insert(0, code_name) # insert the original as well
        return code_descriptions

    def retrieve_similar_data(self, result_callback, code_name, code_memo='', doc_ids=None):
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
        self.ai_async_query(self._retrieve_similar_data, result_callback, code_name, code_memo, doc_ids)

    def _retrieve_similar_data(self, code_name, code_memo='', doc_ids=None, progress_callback=None, signals=None) -> list:
        # 1) Get a list of code descriptions from the llm
        if progress_callback is not None:
            progress_callback.emit(_('Stage 1:\nSearching data related to "') + code_name + '"') 
        descriptions = self.generate_code_descriptions(code_name, code_memo)
        if self.ai_async_is_canceled:
            return []
        
        # 2) Use the list of code descriptions to retrieve related data from the vectorstore
        search_kwargs = {'score_threshold': 0.5, 'k': 50}       
        chunks_meta_list = []
        for desc in descriptions:
            res = self.sources_vectorstore.faiss_db.similarity_search_with_relevance_scores(desc, **search_kwargs)
            if doc_ids is not None and len(doc_ids) > 0:
                # filter results by document ids
                res_filtered = []
                for chunk in res:
                    if chunk[0].metadata['id'] in doc_ids:
                        res_filtered.append(chunk)
                chunks_meta_list.append(res_filtered)
            else: 
                chunks_meta_list.append(res)

        # 3) Consolidate and rank results:
        # Flatten the lists of chunks in chunks_lists and collect all the chunks in a master list.
        # Duplicate chunks are collected only once. The list is sorted by the frequency 
        # of a chunk counted over all lists + the similarity score that chromadb returns.
        # This way, frequent and relevant chunks should be sorted to the top
        # (see: "Reciprocal Rank Fusion" (https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf))

        def chunk_unique_str(chunk):
            # helper
            chunk_str = str(chunk.metadata['id']) + ", "
            chunk_str += str(chunk.metadata['start_index']) + ", "
            return chunk_str
            
        # Flatten the lists and count the frequency of each chunk
        chunk_count_list = {}  # contains the chunk count
        chunk_master_list = []  # contains all chunks from all lists but no doubles
        for lst in chunks_meta_list:
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
    
    def search_analyze_chunk(self, result_callback, chunk, code_name, code_memo, search_prompt: PromptItem):
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
            search_prompt (PromptItem): the prompt used for the analysis
        """
        self.ai_async_query(self._search_analyze_chunk, result_callback, chunk, code_name, code_memo, search_prompt)
        
    def _search_analyze_chunk(self, chunk, code_name, code_memo, search_prompt: PromptItem, progress_callback=None, signals=None):                
        if progress_callback is not None:
            progress_callback.emit(_("Stage 2:\nInspecting the data more closely..."))        

        # build up the prompt
        json_result = """
{
    "interpretation": your reasoning,
    "related": your conclusion, true or false
    "quote": the selected quote or an empty string,
}
"""
        prompt = [
            SystemMessage(
                content=self.get_default_system_prompt()
            ),
            HumanMessage(
                content= (f'You are discussing the code named "{code_name}" with the following code memo: "{extract_ai_memo(code_memo)}". \n'
                    'At the end of this message, you will find a chunk of empirical data. \n'
                    'Your task is to use the following instructions to analyze the chunk of empirical data and decide wether it relates to the given code or not. '
                    f'Instructions: "{search_prompt.text}". \n'
                    'Summarize your reasoning briefly in the field "interpretation" of the result. '
                    f'In this particular field, always answer in the language "{self.get_curr_language()}".\n'
                    'If you came to the conclusion that the chunk of data '
                    'is not related to the code, give back \'False\' in the field "related", otherwise \'True\'.\n'
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
        self.ai_async_progress_max = 130  # estimated average token count of the result
        
        # send the query to the llm 
        try:
            res = self.large_llm.invoke(f'{prompt}', response_format={"type": "json_object"}, config=config)
        except ValidationError as e:
            # The returned JSON was malformed. Try it without validation and hope that "json_repair" will fix it below 
            logger.debug(e)
            res = self.large_llm.invoke(f'{prompt}', config=config)                  
        res.content = strip_think_blocks(res.content)
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

    
    
