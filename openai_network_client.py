import json
from base64 import b64encode
from http.client import HTTPConnection, HTTPResponse, HTTPSConnection, responses
from typing import Dict, List, Optional

import sublime

from .assistant_settings import AssistantSettings, PromptMode
from .cacher import Cacher
from .errors.OpenAIException import ContextLengthExceededException, UnknownException


class NetworkClient():
    response: Optional[HTTPResponse] = None

    # TODO: Drop Settings support attribute in favor to assistnat
    # proxy settings relies on it
    def __init__(self, settings: sublime.Settings, assistant: AssistantSettings, cacher: Cacher = Cacher()) -> None:
        self.cacher = cacher
        self.settings = settings
        self.assistant = assistant
        token = self.assistant.token if self.assistant.token else self.settings.get("token")
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}',
            'cache-control': 'no-cache',
        }

        url_string = self.assistant.url if self.assistant.url else self.settings.get('url')

        url_parts = url_string.split('://')
        url = '://'.join(url_parts[1:])
        connection = HTTPSConnection if url_parts[0] == 'https' else HTTPConnection

        proxy_settings = self.settings.get('proxy')
        if isinstance(proxy_settings, dict):
            address = proxy_settings.get('address')
            port = proxy_settings.get('port')
            proxy_username = proxy_settings.get('username')
            proxy_password = proxy_settings.get('password')
            proxy_auth = b64encode(bytes(f'{proxy_username}:{proxy_password}', 'utf-8')).strip().decode('ascii')
            headers = {'Proxy-Authorization': f'Basic {proxy_auth}'} if len(proxy_auth) > 0 else {}
            if address and len(address) > 0 and port:
                self.connection = connection(
                    host=address,
                    port=port,
                )
                self.connection.set_tunnel(
                    url,
                    headers=headers
                )
            else:
                self.connection = connection(url)

    def prepare_payload(self, assitant_setting: AssistantSettings, messages: List[Dict[str, str]]) -> str:
        internal_messages = []
        internal_messages.insert(0, {'role': 'system', 'content': assitant_setting.assistant_role})
        if assitant_setting.prompt_mode == PromptMode.panel.value:
            ## FIXME: This is error prone and should be rewritten
            #  Messages shouldn't be written in cache and passing as an attribute, should use either one.
            internal_messages += self.cacher.read_all()
        internal_messages += messages

        prompt_tokens_amount = self.calculate_prompt_tokens(internal_messages)
        self.cacher.append_tokens_count(data={'prompt_tokens': prompt_tokens_amount})

        return json.dumps({
            # Todo add uniq name for each output panel (e.g. each window)
            'messages': internal_messages,
            'model': assitant_setting.chat_model,
            'temperature': assitant_setting.temperature,
            'max_tokens': assitant_setting.max_tokens,
            'top_p': assitant_setting.top_p,
            'stream': True
        })

    def prepare_request(self, json_payload):
        self.connection.request(method='POST', url='/v1/chat/completions', body=json_payload, headers=self.headers)

    def execute_response(self) -> Optional[HTTPResponse]:
        return self._execute_network_request()

    def close_connection(self):
        self.response.close()
        self.connection.close()

    def _execute_network_request(self) -> Optional[HTTPResponse]:
        self.response = self.connection.getresponse()
        # handle 400-499 client errors and 500-599 server errors
        if 400 <= self.response.status < 600:
            error_object = self.response.read().decode('utf-8')
            error_data = json.loads(error_object)
            if error_data.get('error', {}).get('code') == 'context_length_exceeded':
                raise ContextLengthExceededException(error_data['error']['message'])
            raise UnknownException(error_data.get('error').get('message'))
        return self.response

    def calculate_prompt_tokens(self, responses: List[Dict[str, str]]) -> int:
        total_tokens = 0
        for response in responses:
            if 'content' in response:
                total_tokens += len(response['content']) / 4
        return int(total_tokens)