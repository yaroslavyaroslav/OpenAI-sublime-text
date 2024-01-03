from typing import Optional
from main.assistant_settings import AssistantSettings, PromptMode, DEFAULT_ASSISTANT_SETTINGS
from network.openai_network_client import NetworkClient
from sublime import Settings


__settings_mock__ = {
    'token': '',
    'proxy': {
        'address': '',
        'port': '',
        'username': '',
        'password': ''
    }
}

__network_instance__: Optional[NetworkClient]

def _set_up():
    global __network_instance__
    __network_instance__ = NetworkClient(Settings(id=0))

def test_panel_mode_prepare_payload():
    global __network_instance__
    _set_up()

    # assistant_dict = {
    #     'name': 'str',
    #     'prompt_mode': PromptMode.panel,
    #     'chat_model': 'str',
    #     'assistant_role': 'str'
    # }
    # assistant_settings = AssistantSettings(**{**DEFAULT_ASSISTANT_SETTINGS, **assistant_dict})
    # messages = [
    #     {"role": "system", "content": f'some system instruction', 'name': 'OpenAI_completion'},
    #     {"role": "user", "content": f'some user input', 'name': 'OpenAI_completion'},
    # ]

    # payload = __network_instance__.prepare_payload(assitant_setting=assistant_settings, messages=messages)

    # assert payload == messages.__str__, "Wrong test "

    _tear_down()

def test_non_panel_mode_prepare_payload():
    global __network_instance__
    _set_up()

    assistant_dict = {
        'name': 'str',
        'prompt_mode': PromptMode.insert,
        'chat_model': 'str',
        'assistant_role': 'str'
    }
    assistant_settings = AssistantSettings(**{**DEFAULT_ASSISTANT_SETTINGS, **assistant_dict})
    messages = [
        {"role": "system", "content": f'some system instruction', 'name': 'OpenAI_completion'},
        {"role": "user", "content": f'some user input', 'name': 'OpenAI_completion'},
    ]

    payload = __network_instance__.prepare_payload(assitant_setting=assistant_settings, messages=messages)

    assert payload == messages.__str__, "Wrong test "

    _tear_down()

def _tear_down():
    global __network_instance__
    __network_instance__ = None