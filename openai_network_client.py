from http.client import HTTPSConnection, HTTPResponse
from typing import Optional, List, Dict
from .cacher import Cacher
import sublime
import json
from .errors.OpenAIException import ContextLengthExceededException, UnknownException, present_error
from .assistant_settings import AssistantSettings, PromptMode

class NetworkClient():
    mode = "" ## DEPRECATED
    def __init__(self, settings: sublime.Settings) -> None:
        self.settings = settings
        self.headers = {
            'Content-Type': "application/json",
            'Authorization': f'Bearer {self.settings.get("token")}',
            'cache-control': "no-cache",
        }

        proxy_settings = self.settings.get('proxy')
        if isinstance(proxy_settings, dict):
            address = proxy_settings.get('address')
            port = proxy_settings.get('port')
            if address and len(address) > 0 and port:

                # ctx = ssl.create_default_context()
                # ctx.check_hostname = False
                # ctx.verify_mode = ssl.CERT_NONE
                self.connection = HTTPSConnection(
                    host=address,
                    port=port,
                    # context=ctx
                )
                self.connection.set_tunnel("api.openai.com")
            else:
                self.connection = HTTPSConnection("api.openai.com")

    def prepare_payload(self, assitant_setting: AssistantSettings, messages: List[Dict[str, str]]):
        if assitant_setting.prompt_mode == PromptMode.panel.value:
            messages = Cacher().read_all() + messages
        messages.append({"role": "system", "content": assitant_setting.assistant_role})

        return json.dumps({
            # Todo add uniq name for each output panel (e.g. each window)
            "messages": messages,
            "model": assitant_setting.chat_model,
            "temperature": assitant_setting.temperature,
            "max_tokens": assitant_setting.max_tokens,
            "top_p": assitant_setting.top_p,
            "stream": True
        })

    ## DEPRECATED CODE
    def prepare_payload_deprecated(self, mode: str, text: Optional[str] = None, command: Optional[str] = None, role: Optional[str] = None, parts: Optional[List[str]] = None) -> str:
        self.mode = mode
        if mode == 'insertion':
            prompt, suffix = (parts[0], parts[1]) if parts and len(parts) >= 2 else ("Print out that input text is wrong", "Print out that input text is wrong")
            return json.dumps({
                "model": self.settings.get("model"),
                "prompt": prompt,
                "suffix": suffix,
                "temperature": self.settings.get("temperature"),
                "max_tokens": self.settings.get("max_tokens"),
                "top_p": self.settings.get("top_p"),
                "frequency_penalty": self.settings.get("frequency_penalty"),
                "presence_penalty": self.settings.get("presence_penalty")
            })

        elif mode == 'edition':
            return json.dumps({
                "model": self.settings.get('edit_model'),
                "input": text,
                "instruction": command,
                "temperature": self.settings.get("temperature"),
                "top_p": self.settings.get("top_p"),
            })

        elif mode == 'completion':
            return json.dumps({
                "prompt": text,
                "model": self.settings.get("model"),
                "temperature": self.settings.get("temperature"),
                "max_tokens": self.settings.get("max_tokens"),
                "top_p": self.settings.get("top_p"),
                "frequency_penalty": self.settings.get("frequency_penalty"),
                "presence_penalty": self.settings.get("presence_penalty")
            })

        else: raise Exception("Undefined mode")
    ## DEPRECATED CODE

    def prepare_request(self, json_payload):
        self.connection.request(method="POST", url="/v1/chat/completions", body=json_payload, headers=self.headers)

    def prepare_request_deprecated(self, gateway, json_payload):
        self.connection.request(method="POST", url=gateway, body=json_payload, headers=self.headers)

    def execute_response(self) -> Optional[HTTPResponse]:
        return self._execute_network_request()

    def _execute_network_request(self) -> Optional[HTTPResponse]:
        response = self.connection.getresponse()
        # handle 400-499 client errors and 500-599 server errors
        if 400 <= response.status < 600:
            error_object = response.read().decode('utf-8')
            error_data = json.loads(error_object)
            if error_data.get('error', {}).get('code') == 'context_length_exceeded':
                raise ContextLengthExceededException(error_data['error']['message'])
            code = error_data.get('error', {}).get('code') or error_data.get('error', {}).get('type')
            unknown_error = UnknownException(error_data.get('error', {}).get('message'))
            present_error(title=code, error=unknown_error)
        return response
