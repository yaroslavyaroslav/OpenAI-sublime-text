from json import dumps, loads
from typing import Optional, Any
from sublime import Settings
import sys
from unittest import TestCase


network_client_module = sys.modules['OpenAI completion.plugins.openai_network_client']
assistant_module = sys.modules['OpenAI completion.plugins.assistant_settings']
cacher_module = sys.modules['OpenAI completion.plugins.cacher']


class TestNetworkClient(TestCase):
    network_instance_ = Optional[Any]
    settings = Settings(id=2)
    cacher_ = cacher_module.Cacher(name='test_')
    fake_history_ = [
        {'role': 'user', 'content': 'some user instruction 1', 'name': 'OpenAI_completion'},
        {'role': 'assistant', 'content': 'some assitant output 1'},
        {'role': 'user', 'content': 'some user selection 2', 'name': 'OpenAI_completion'},
        {'role': 'user', 'content': 'some user instruction 2', 'name': 'OpenAI_completion'},
        {'role': 'assistant', 'content': 'some assitant output 2'},
        {'role': 'user', 'content': 'some user instruction 3', 'name': 'OpenAI_completion'},
        {'role': 'assistant', 'content': 'some assitant output 3'},
    ]

    messages_to_append_ = [
        {'role': 'user', 'content': 'some user selection 4', 'name': 'OpenAI_completion'},
        {'role': 'user', 'content': 'some user input 4', 'name': 'OpenAI_completion'},
    ]

    system_instruction_ = {'role': 'system', 'content': 'test_string'}

    assistant_dict_ = {
        'name': 'test_string',
        'chat_model': 'test_string',
        'assistant_role': 'test_string',
        'advertisement': False,
        'prompt_mode': 'panel',
    }

    def setUp(self):
        self.settings.set('url', 'http://localhost:8080')
        assistant_dict = self.assistant_dict_.copy()
        assistant_dict['prompt_mode'] = assistant_module.PromptMode.panel.value

        assistant_settings = assistant_module.AssistantSettings(
            **{**assistant_module.DEFAULT_ASSISTANT_SETTINGS, **assistant_dict}
        )
        self.network_instance_ = network_client_module.NetworkClient(
            self.settings, assistant=assistant_settings, cacher=self.cacher_
        )
        self.cacher_.save_model(assistant_settings.__dict__)
        self.cacher_.append_to_cache(self.fake_history_)

    def test_system_prepare_payload(self):
        assistant_dict = self.assistant_dict_.copy()

        assistant_settings = assistant_module.AssistantSettings(
            **{**assistant_module.DEFAULT_ASSISTANT_SETTINGS, **assistant_dict}
        )
        messages_to_pass = self.messages_to_append_

        messages_to_test = messages_to_pass[:]
        messages_to_test.insert(0, self.system_instruction_)

        payload = self.network_instance_.prepare_payload(
            assitant_setting=assistant_settings, messages=messages_to_pass
        )
        payload_json = loads(payload)

        self.assertEqual(
            dumps(payload_json['messages']),
            dumps(messages_to_test),
            f'\npayload: {dumps(payload_json["messages"])}\nmessage: {dumps(messages_to_test)}',
        )

    def tearDown(self):
        self.network_instance_ = None
        self.cacher_.delete_all_caches_()
