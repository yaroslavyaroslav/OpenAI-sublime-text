from http.client import HTTPSConnection, HTTPResponse
from typing import Optional, List
from sublime import Settings
import json
from .cacher import Cacher

class NetworkClient():
    def __init__(self, settings: Settings) -> None:
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
                self.connection = HTTPSConnection(
                    host=address,
                    port=port
                )
                self.connection.set_tunnel("api.openai.com")
            else:
                self.connection = HTTPSConnection("api.openai.com")

    def prepare_payload(self, mode: str, text: Optional[str] = None, command: Optional[str] = None, cacher: Optional[Cacher] = None, role: Optional[str] = None, parts: Optional[List[str]] = None) -> str:
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

        elif mode == 'chat_completion':
            return json.dumps({
                # Todo add uniq name for each output panel (e.g. each window)
                "messages": [
                    {"role": "system", "content": role},
                    *(cacher.read_all() if cacher is not None else [])
                ],
                "model": self.settings.get('chat_model'),
                "temperature": self.settings.get("temperature"),
                "max_tokens": self.settings.get("max_tokens"),
                "top_p": self.settings.get("top_p"),
                "stream": True
            })
        else: raise Exception("Undefined mode")

    def prepare_request(self, gateway, json_payload):
        self.connection.request(method="POST", url=gateway, body=json_payload, headers=self.headers)

    def execute_response(self) -> HTTPResponse:
        return self.connection.getresponse()
