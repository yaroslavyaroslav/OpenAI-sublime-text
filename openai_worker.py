from re import fullmatch
import sublime, sublime_plugin
import http.client
import threading
from .cacher import Cacher
from .outputpanel import get_number_of_lines, SharedOutputPanelListener
import json
import logging
import re


class OpenAIWorker(threading.Thread):
    message = {}

    def __init__(self, region, text, view, mode, command):
        self.region = region
        self.text = text
        self.view = view
        self.mode = mode
        self.command = command # optional
        self.message = {"role": "user", "content": self.command, 'name': 'OpenAI_completion'}
        settings = sublime.load_settings("openAI.sublime-settings")
        self.settings = settings
        self.proxy = settings.get('proxy')['address']
        self.port = settings.get('proxy')['port']
        super(OpenAIWorker, self).__init__()

    def update_output_panel(self, text_chunk: str, shot_panel: bool = False):
        from .outputpanel import SharedOutputPanelListener
        window = sublime.active_window()
        listner = SharedOutputPanelListener()
        listner.show_panel(window=window)
        listner.update_output_panel(
            text=text_chunk,
            window=window
        )

    def prompt_completion(self, completion):
        completion = completion.replace("$", "\$")
        if self.mode == 'insertion':
            result = self.view.find(self.settings.get('placeholder'), 0, 1)
            if result:
                self.view.sel().clear()
                self.view.sel().add(result)
                # Replace the placeholder with the specified replacement text
                self.view.run_command("insert_snippet", {"contents": completion})
            return

        if self.mode == 'completion':
            region = self.view.sel()[0]
            if region.a <= region.b:
                region.a = region.b
            else:
                region.b = region.a

            self.view.sel().clear()
            self.view.sel().add(region)
            # Replace the placeholder with the specified replacement text
            self.view.run_command("insert_snippet", {"contents": completion})
            return

        if self.mode == 'edition': # it's just replacing all given text for now.
            region = self.view.sel()[0]
            self.view.run_command("insert_snippet", {"contents": completion})
            return

    def exec_net_request(self, connect: http.client.HTTPSConnection):
        try:
            res = connect.getresponse()

            if res.status != 200:
                raise Exception(f"Server Error: {res.status}")

            decoder = json.JSONDecoder()

            full_response_content = {"role": "", "content": ""}

            self.update_output_panel("\n\n## Answer\n\n")

            for chunk in res:
                chunk_str = chunk.decode('utf-8')

                # Check for SSE data
                if chunk_str.startswith("data:") and not re.search(r"\[DONE\]$", chunk_str):
                    print(chunk_str)
                    print(re.search(r"\[DONE\]$", chunk_str))
                    chunk_str = chunk_str[len("data:"):].strip()

                    try:
                        response = decoder.decode(chunk_str)
                    except ValueError as ex:
                        sublime.error_message(f"Server Error: {str(ex)}")
                        logging.exception("Exception: " + str(ex))

                    if 'delta' in response['choices'][0]:
                        delta = response['choices'][0]['delta']
                        if 'role' in delta:
                            full_response_content['role'] = delta['role']
                        elif 'content' in delta:
                            full_response_content['content'] += delta['content']
                            self.update_output_panel(delta['content'])

            connect.close()
            Cacher().append_to_cache([full_response_content])
            # self.prompt_completion(completion)

        except KeyError:
            # TODO: Add status bar user notification for this action.
            if self.mode == 'chat_completion' and response['error']['code'] == 'context_length_exceeded':
                Cacher().drop_first(4)
                self.chat_complete()
            else:
                sublime.error_message("Exception\n" + "The OpenAI response could not be decoded. There could be a problem on their side. Please look in the console for additional error info.")
                logging.exception("Exception: " + str(response))
            return
        except Exception as ex:
            sublime.error_message(f"Server Error: {str(ex)}")
            logging.exception("Exception: " + str(ex))
            return

    def create_connection(self) -> http.client.HTTPSConnection:
        if len(self.proxy) > 0:
            connection = http.client.HTTPSConnection(host=self.proxy, port=self.port)
            connection.set_tunnel("api.openai.com")
            return connection
        else:
            return http.client.HTTPSConnection("api.openai.com")

    def chat_complete(self):
        cacher = Cacher()

        conn = self.create_connection()
        role = self.settings.get('assistant_role')

        self.update_output_panel("\n\n## Question\n\n")
        self.update_output_panel(cacher.read_all()[-1]["content"])

        payload = {
            # Todo add uniq name for each output panel (e.g. each window)
            "messages": [
                {"role": "system", "content": role},
                *cacher.read_all()
            ],
            "model": self.settings.get('chat_model'),
            "temperature": self.settings.get("temperature"),
            "max_tokens": self.settings.get("max_tokens"),
            "top_p": self.settings.get("top_p"),
            "stream": True
        }

        json_payload = json.dumps(payload)
        token = self.settings.get('token')

        headers = {
            'Content-Type': "application/json",
            'Authorization': f'Bearer {token}',
            'cache-control': "no-cache",
        }
        conn.request("POST", "/v1/chat/completions", json_payload, headers)
        self.exec_net_request(connect=conn)

    def complete(self):
        conn = self.create_connection()

        payload = {
            "prompt": self.text,
            "model": self.settings.get("model"),
            "temperature": self.settings.get("temperature"),
            "max_tokens": self.settings.get("max_tokens"),
            "top_p": self.settings.get("top_p"),
            "frequency_penalty": self.settings.get("frequency_penalty"),
            "presence_penalty": self.settings.get("presence_penalty")
        }
        json_payload = json.dumps(payload)

        token = self.settings.get('token')

        headers = {
            'Content-Type': "application/json",
            'Authorization': 'Bearer {}'.format(token),
            'cache-control': "no-cache",
        }
        conn.request("POST", "/v1/completions", json_payload, headers)
        self.exec_net_request(connect=conn)

    def insert(self):
        conn = self.create_connection()
        parts = self.text.split(self.settings.get('placeholder'))
        try:
            if not len(parts) == 2:
                raise AssertionError("There is no placeholder '" + self.settings.get('placeholder') + "' within the selected text. There should be exactly one.")
        except Exception as ex:
            sublime.error_message("Exception\n" + str(ex))
            logging.exception("Exception: " + str(ex))
            return

        payload = {
            "model": self.settings.get("model"),
            "prompt": parts[0],
            "suffix": parts[1],
            "temperature": self.settings.get("temperature"),
            "max_tokens": self.settings.get("max_tokens"),
            "top_p": self.settings.get("top_p"),
            "frequency_penalty": self.settings.get("frequency_penalty"),
            "presence_penalty": self.settings.get("presence_penalty")
        }
        json_payload = json.dumps(payload)

        token = self.settings.get('token')

        headers = {
            'Content-Type': "application/json",
            'Authorization': 'Bearer {}'.format(token),
            'cache-control': "no-cache",
        }
        conn.request("POST", "/v1/completions", json_payload, headers)
        self.exec_net_request(connect=conn)

    def edit_f(self):
        conn = self.create_connection()
        payload = {
            "model": self.settings.get('edit_model'),
            "input": self.text,
            "instruction": self.command,
            "temperature": self.settings.get("temperature"),
            "top_p": self.settings.get("top_p"),
        }
        json_payload = json.dumps(payload)

        token = self.settings.get('token')

        headers = {
            'Content-Type': "application/json",
            'Authorization': 'Bearer {}'.format(token),
            'cache-control': "no-cache",
        }
        conn.request("POST", "/v1/edits", json_payload, headers)
        self.exec_net_request(connect=conn)

    def run(self):
        try:
            # FIXME: It's better to have such check locally, but it's pretty complicated with all those different modes and models
            # if (self.settings.get("max_tokens") + len(self.text)) > 4000:
            #     raise AssertionError("OpenAI accepts max. 4000 tokens, so the selected text and the max_tokens setting must be lower than 4000.")
            if not self.settings.has("token"):
                raise AssertionError("No token provided, you have to set the OpenAI token into the settings to make things work.")
            token = self.settings.get('token')
            if len(token) < 10:
                raise AssertionError("No token provided, you have to set the OpenAI token into the settings to make things work.")
        except Exception as ex:
            sublime.error_message("Exception\n" + str(ex))
            logging.exception("Exception: " + str(ex))
            return

        if self.mode == 'insertion': self.insert()
        if self.mode == 'edition': self.edit_f()
        if self.mode == 'completion': self.complete()
        if self.mode == 'chat_completion':
            Cacher().append_to_cache([self.message])
            self.chat_complete()
