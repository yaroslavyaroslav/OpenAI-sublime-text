from json import dumps, loads
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
    __cacher__ = cacher_module.Cacher(name='test_')
    __fake_history__ = [
        {'role': 'user', 'content': 'some user instruction 1', 'name': 'OpenAI_completion'},
        {'role': 'assistant', 'content': 'some assitant output 1'},
        {'role': 'user', 'content': 'some user selection 2', 'name': 'OpenAI_completion'},
        {'role': 'user', 'content': 'some user instruction 2', 'name': 'OpenAI_completion'},
        {'role': 'assistant', 'content': 'some assitant output 2'},
        {'role': 'user', 'content': 'some user instruction 3', 'name': 'OpenAI_completion'},
        {'role': 'assistant', 'content': 'some assitant output 3'},
    ]

    __messages_to_append__ = [
        {'role': 'user', 'content': 'some user selection 4', 'name': 'OpenAI_completion'},
        {'role': 'user', 'content': 'some user input 4', 'name': 'OpenAI_completion'},
    ]

    __system_instruction__ = {'role': 'system', 'content': 'test_string'}

    __assistant_dict__ = {
        'name': 'test_string',
        'chat_model': 'test_string',
        'assistant_role': 'test_string'
    }

    def setUp(self):
        self.__network_instance__ = network_client_module.NetworkClient(Settings(id=0), cacher=self.__cacher__)
        self.__cacher__.append_to_cache(self.__fake_history__)

    def test_panel_mode_prepare_payload(self):
        assistant_dict = self.__assistant_dict__.copy()
        assistant_dict['prompt_mode'] = assistant_module.PromptMode.panel.value

        assistant_settings = assistant_module.AssistantSettings(
            **{
                **assistant_module.DEFAULT_ASSISTANT_SETTINGS,
                **assistant_dict
            }
        )
        messages_to_pass = self.__messages_to_append__

        messages_to_test = messages_to_pass[:]
        messages_to_test = self.__fake_history__ + messages_to_test
        messages_to_test.insert(0, self.__system_instruction__)

        payload = self.__network_instance__.prepare_payload(assitant_setting=assistant_settings, messages=messages_to_pass)
        payload_json = loads(payload)

        self.assertEqual(
            dumps(payload_json['messages']),
            dumps(messages_to_test),
            f'\npayload: {dumps(payload_json["messages"])}\nmessage: {dumps(messages_to_test)}'
        )

    def test_non_panel_mode_prepare_payload(self):
        assistant_dict = self.__assistant_dict__.copy()
        assistant_dict['prompt_mode'] = assistant_module.PromptMode.insert.value

        assistant_settings = assistant_module.AssistantSettings(
            **{
                **assistant_module.DEFAULT_ASSISTANT_SETTINGS,
                **assistant_dict
            }
        )
        messages_to_pass = self.__messages_to_append__

        messages_to_test = messages_to_pass[:]
        messages_to_test.insert(0, self.__system_instruction__)

        payload = self.__network_instance__.prepare_payload(assitant_setting=assistant_settings, messages=messages_to_pass)
        payload_json = loads(payload)

        self.assertEqual(
            dumps(payload_json['messages']),
            dumps(messages_to_test),
            f'\npayload: {dumps(payload_json["messages"])}\nmessage: {dumps(messages_to_test)}'
        )

    def tearDown(self):
        self.__network_instance__ = None
        self.__cacher__.drop_all()
