import json
from typing import Optional, Any
from sublime import Settings
import sys
from unittest import TestCase


network_client_module = sys.modules['OpenAI completion.openai_network_client']
assistant_module = sys.modules['OpenAI completion.assistant_settings']
cacher_module = sys.modules['OpenAI completion.cacher']


class TestNetworkClient(TestCase):
    __network_instance__ = Optional[Any]
    __cacher__ = cacher_module.Cacher(name='test')
    __fake_history__ = [
        {'role': 'user', 'content': 'some user instruction 1', 'name': 'OpenAI_completion'},
        {'role': 'assistant', 'content': 'some assitant output 1'},
        {'role': 'user', 'content': 'some user selection 2', 'name': 'OpenAI_completion'},
        {'role': 'user', 'content': 'some user instruction 2', 'name': 'OpenAI_completion'},
        {'role': 'assistant', 'content': 'some assitant output 2'},
        {'role': 'user', 'content': 'some user instruction 3', 'name': 'OpenAI_completion'},
        {'role': 'assistant', 'content': 'some assitant output 3'},
    ]

    def setUp(self):
        self.__network_instance__ = network_client_module.NetworkClient(Settings(id=0), cacher=self.__cacher__)
        self.__cacher__.append_to_cache(self.__fake_history__)

    def test_panel_mode_prepare_payload(self):

        # FIXME: This should be moved to a separate function
        assistant_dict = {
            'name': 'test_string',
            'prompt_mode': assistant_module.PromptMode.panel,
            'chat_model': 'test_string',
            'assistant_role': 'test_string'
        }
        assistant_settings = assistant_module.AssistantSettings(**{**assistant_module.DEFAULT_ASSISTANT_SETTINGS, **assistant_dict})
        messages_to_pass = [
            {"role": "user", "content": "some user selection 4", "name": "OpenAI_completion"},
            {"role": "user", "content": "some user input 4", "name": "OpenAI_completion"},
        ]

        messages_to_test = messages_to_pass[:]
        messages_to_test = self.__fake_history__ + messages_to_test
        messages_to_test.insert(0, {"role": "system", "content": "test_string"})

        payload = self.__network_instance__.prepare_payload(assitant_setting=assistant_settings, messages=messages_to_pass)

        # FIXME: This should be moved to a separate function
        payload_json = json.loads(payload)
        payload_messages = json.dumps(payload_json['messages'])
        messages_string = json.dumps(messages_to_test)

        self.assertEqual(payload_messages, messages_string, f'\npayload: {payload_messages}\nmessage: {messages_string}')

    def test_non_panel_mode_prepare_payload(self):
        assistant_dict = {
            'name': 'test_string',
            'prompt_mode': assistant_module.PromptMode.insert,
            'chat_model': 'test_string',
            'assistant_role': 'test_string'
        }
        assistant_settings = assistant_module.AssistantSettings(**{**assistant_module.DEFAULT_ASSISTANT_SETTINGS, **assistant_dict})
        messages_to_pass = [
            {"role": "user", "content": "some user selected text", "name": "OpenAI_completion"},
            {"role": "user", "content": "some user input", "name": "OpenAI_completion"},
        ]

        messages_to_test = messages_to_pass[:]
        messages_to_test.insert(0, {"role": "system", "content": "test_string"})

        payload = self.__network_instance__.prepare_payload(assitant_setting=assistant_settings, messages=messages_to_pass)

        # FIXME: This should be moved to a separate function
        payload_json = json.loads(payload)
        payload_messages = json.dumps(payload_json['messages'])
        messages_string = json.dumps(messages_to_test)

        self.assertEqual(payload_messages, messages_string, f'\npayload: {payload_messages}\nmessage: {messages_string}')

    def tearDown(self):
        self.__network_instance__ = None
        self.__cacher__.drop_all()
