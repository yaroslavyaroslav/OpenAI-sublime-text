import sublime, sublime_plugin
import http.client
import threading
from .cacher import Cacher
import json
import logging


class OpenAIWorker(threading.Thread):
    def __init__(self, region, text, view, mode, command):
        self.region = region
        self.text = text
        self.view = view
        self.mode = mode
        self.command = command # optional
        self.settings = sublime.load_settings("openAI.sublime-settings")
        super(OpenAIWorker, self).__init__()

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

        if self.mode == 'chat_completion':
            window = sublime.active_window()

            ## TODO: Make this costumizable.
            syntax_file = "Packages/MarkdownEditing/syntaxes/MultiMarkdown.sublime-syntax"

            ## FIXME: It opens new panel if the response came when user switched to new window.
            ## It should be the same window where it started.
            ## Guess needed to be cached.
            output_panel = window.find_output_panel("OpenAI Chat") if window.find_output_panel("OpenAI Chat") != None else window.create_output_panel("OpenAI Chat")
            output_panel.set_read_only(False)
            output_panel.set_syntax_file(syntax_file)

            ## This one left here as there're could be loooong questions.
            output_panel.run_command('append', {'characters': f'\n\n## Question\n\n'})
            output_panel.run_command('append', {'characters': self.command})
            output_panel.run_command('append', {'characters': '\n\n## Answer\n\n'})
            output_panel.run_command('append', {'characters': completion})
            window.run_command("show_panel", {"panel": "output.OpenAI Chat"})
            output_panel.set_read_only(True)

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
            data = res.read()
            status = res.status
            data_decoded = data.decode('utf-8')
            connect.close()
            response = json.loads(data_decoded)

            if self.mode == 'chat_completion':
                Cacher().append_to_cache([response['choices'][0]['message']])
                completion = response['choices'][0]['message']['content']
            else:
                completion = json.loads(data_decoded)['choices'][0]['text']

            completion = completion.strip()  # Remove leading and trailing spaces
            self.prompt_completion(completion)
        except KeyError:
            sublime.error_message("Exception\n" + "The OpenAI response could not be decoded. There could be a problem on their side. Please look in the console for additional error info.")
            logging.exception("Exception: " + str(data_decoded))
            return
        except Exception as ex:
            sublime.error_message(f"Server Error: {str(status)}\n{ex}")
            return

    def chat_complete(self):
        cacher = Cacher()
        conn = http.client.HTTPSConnection("api.openai.com")

        message = {"role": "user", "content": self.command, 'name': 'OpenAI_completion'}
        cacher.append_to_cache([message])

        print(f'cache: {cacher.read_all()}')

        payload = {
            # Todo add uniq name for each output panel (e.g. each window)
            "messages": [
                {"role": "system", "content": "You are a code assistant."},
                *cacher.read_all()
            ],
            "model": self.settings.get('chat_model'),
            "temperature": self.settings.get("temperature"),
            "max_tokens": self.settings.get("max_tokens"),
            "top_p": self.settings.get("top_p"),
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
        conn = http.client.HTTPSConnection("api.openai.com")
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
        conn = http.client.HTTPSConnection("api.openai.com")
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
        conn = http.client.HTTPSConnection("api.openai.com")
        payload = {
            "model": "code-davinci-edit-001", # could be text-davinci-edit-001
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
        if self.mode == 'chat_completion': self.chat_complete()

