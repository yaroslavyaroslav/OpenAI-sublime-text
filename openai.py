import sublime, sublime_plugin
import functools
import http.client
import threading
import json
import logging


class OpenAIWorker(threading.Thread):
    def __init__(self, edit, region, text, view, mode, command):
        self.edit = edit
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

        if self.mode == 'completion':
            if self.settings.get('output_panel'):
                window = sublime.active_window()

                output_view = window.find_output_panel("OpenAI") if window.find_output_panel("OpenAI") != None else window.create_output_panel("OpenAI")
                output_view.run_command('append', {'characters': f'## {self.text}'})
                output_view.run_command('append', {'characters': '\n------------'})
                output_view.run_command('append', {'characters': completion})
                output_view.run_command('append', {'characters': '\n============\n\n'})
                window.run_command("show_panel", {"panel": "output.OpenAI"})
            else:
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
            data_decoded = data.decode('utf-8')
            connect.close()
            completion = json.loads(data_decoded)['choices'][0]['text']
            self.prompt_completion(completion)
        except KeyError:
            sublime.error_message("Exception\n" + "The OpenAI response could not be decoded. There could be a problem on their side. Please look in the console for additional error info.")
            logging.exception("Exception: " + str(data_decoded))
            return

        except Exception as ex:
            sublime.error_message("Error\n" + str(ex))
            logging.exception("Exception: " + str(ex))
            return

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
                raise AssertionError("There is no placeholder within the selected text, there should be exactly one.")
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
            if (self.settings.get("max_tokens") + len(self.text)) > 4000:
                raise AssertionError("OpenAI accepts max. 4000 tokens, so the selected text and the max_tokens setting must be lower than 4000.")
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
        if self.mode == 'completion':
            if self.settings.get('output_panel'):
                self.text = self.command
            if self.settings.get('multimarkdown'):
                self.text += ' format the answer with multimarkdown markup'
            self.complete()


class Openai(sublime_plugin.TextCommand):
    def on_input(self, edit, region, text, view, mode, input):
        worker_thread = OpenAIWorker(edit, region, text, view, mode=mode, command=input)
        worker_thread.start()

    """
    asyncroniously send request to https://api.openai.com/v1/completions
    with the selcted text of the view
    and inserts suggestion from within response at place of `[insert]` placeholder
    """
    def run(self, edit, **kwargs):
        settings = sublime.load_settings("openAI.sublime-settings")
        mode = kwargs.get('mode', 'completion')

        # get selected text
        region = ''
        text = ''
        for region in self.view.sel():
            if not region.empty():
                text = self.view.substr(region)


        try:
            if region.__len__() < settings.get("minimum_selection_length"):
                if mode == 'completion':
                    if not settings.get('output_panel'):
                        raise AssertionError("Not enough text selected to complete the request, please expand the selection.")
                else:
                    raise AssertionError("Not enough text selected to complete the request, please expand the selection.")
        except Exception as ex:
            sublime.error_message("Exception\n" + str(ex))
            logging.exception("Exception: " + str(ex))
            return

        if mode == 'edition':
            sublime.active_window().show_input_panel("Request: ", "Comment the given code line by line", functools.partial(self.on_input, edit, region, text, self.view, mode), None, None)

        elif mode == 'insertion':
            worker_thread = OpenAIWorker(edit, region, text, self.view, mode, "")
            worker_thread.start()
        else: # mode == `completion`
            if settings.get('output_panel'):
                sublime.active_window().show_input_panel("Question: ", "", functools.partial(self.on_input, edit, region, text, self.view, mode), None, None)
            else:
                worker_thread = OpenAIWorker(edit, region, text, self.view, mode, "")
                worker_thread.start()

