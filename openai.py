import sublime, sublime_plugin
import http.client
import threading
import json
import re

import logging

class OpenAIWorker(threading.Thread):
    def __init__(self, edit, region, text, view, mode):
        self.mode = mode
        self.edit = edit
        self.region = region
        self.text = text
        self.view = view
        self.settings = sublime.load_settings("openAI.sublime-settings")
        super(OpenAIWorker, self).__init__()

    def prompt_completion(self, completion):
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
                region.b -= 1
            else:
                region.a -= 1

            self.view.sel().subtract(region)
            # Replace the placeholder with the specified replacement text
            self.view.run_command("insert_snippet", {"contents": completion})
            return

    def exec_net_request(self, payload, headers):
        while True:
            try:
                conn = http.client.HTTPSConnection("api.openai.com")
                json_payload = json.dumps(payload)

                conn.request("POST", "/v1/completions", json_payload, headers)
                res = conn.getresponse()

                data = res.read()
                data_decoded = data.decode('utf-8')
                conn.close()

                completion = json.loads(data_decoded)['choices'][0]['text']
                self.prompt_completion(completion)
                return

            except Exception as ex:
                print("Exception")
                sublime.error_message("Exception: " + str(ex))
                logging.exception("Exception")
                return

    def complete(self):
        payload = {
            "prompt": self.text,
            "model": self.settings.get("model"),
            "temperature": self.settings.get("temperature"),
            "max_tokens": self.settings.get("max_tokens"),
            "top_p": self.settings.get("top_p"),
            "frequency_penalty": self.settings.get("frequency_penalty"),
            "presence_penalty": self.settings.get("presence_penalty")
        }

        headers = {
            'Content-Type': "application/json",
            'Authorization': f'Bearer {self.settings.get("token")}',
            'cache-control': "no-cache",
        }
        self.exec_net_request(payload=payload, headers=headers)

    def insert(self):
        parts = self.text.split(self.settings.get('placeholder'))
        if not len(parts) == 2: return

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

        headers = {
            'Content-Type': "application/json",
            'Authorization': f'Bearer {self.settings.get("token")}',
            'cache-control': "no-cache",
        }

        self.exec_net_request(payload=payload, headers=headers)


    def run(self):
        settings = sublime.load_settings("openAI.sublime-settings")
        if not settings.has("token"): return

        if self.mode == 'completion': self.complete()
        if self.mode == 'insertion': self.insert()


class Openai(sublime_plugin.TextCommand):
    """
    asyncroniously send request to https://api.openai.com/v1/completions
    with the selcted text of the view
    and inserts suggestion from within response at place of `[insert]` placeholder
    """
    def run(self, edit, **kwargs):

        mode = kwargs.get('mode', 'completion')

        # get selected text
        region = ''
        text = ''
        for region in self.view.sel():
            if not region.empty():
                text = self.view.substr(region)

            worker_thread = OpenAIWorker(edit, region, text, self.view, mode)
            worker_thread.start()

