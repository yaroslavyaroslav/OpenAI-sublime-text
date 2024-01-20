import json
from typing import Optional, Any
from sublime import Settings
import sys
from unittest import TestCase


network_client_module = sys.modules['OpenAI completion.openai_network_client']
assistant_module = sys.modules['OpenAI completion.assistant_settings']


class TestNetworkClient(TestCase):
    __network_instance__ = Optional[Any]

    def _set_up(self):
        self.__network_instance__ = network_client_module.NetworkClient(Settings(id=0))

    def test_panel_mode_prepare_payload(self):
        self._set_up()

        assistant_dict = {
            'name': 'str',
            'prompt_mode': assistant_module.PromptMode.panel,
            'chat_model': 'str',
            'assistant_role': 'str'
        }
        assistant_settings = assistant_module.AssistantSettings(**{**assistant_module.DEFAULT_ASSISTANT_SETTINGS, **assistant_dict})
        messages = [
            {'role': 'system', 'content': f'some system instruction', 'name': 'OpenAI_completion'},
            {'role': 'user', 'content': f'some user input', 'name': 'OpenAI_completion'},
        ]

        # payload = __network_instance__.prepare_payload(assitant_setting=assistant_settings, messages=messages)

        self._tear_down()

    def test_non_panel_mode_prepare_payload(self):
        self._set_up()

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

        payload_json = json.loads(payload)
        payload_messages = json.dumps(payload_json['messages'])
        messages_string = json.dumps(messages_to_test)

        self.assertEqual(payload_messages, messages_string, f'\npayload: {payload_messages}\nmessage: {messages_string}')

        self._tear_down()

    def _tear_down(self):
        self.__network_instance__ = None