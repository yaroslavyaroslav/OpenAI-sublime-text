import sublime
import threading
from .cacher import Cacher
from typing import List
from .openai_network_client import NetworkClient
from .buffer import SublimeBuffer
from .errors.OpenAIException import ContextLengthExceededException, UnknownException, present_error
import json
import logging
import re


class OpenAIWorker(threading.Thread):
    def __init__(self, region, text, view, mode, command):
        self.region = region
        self.text = text
        self.view = view
        self.mode = mode
        self.command = command # optional
        self.message = {"role": "user", "content": self.command, 'name': 'OpenAI_completion'}
        self.settings = sublime.load_settings("openAI.sublime-settings")
        self.provider = NetworkClient(settings=self.settings)
        self.window = sublime.active_window()

        markdown_setting = self.settings.get('markdown')
        if not isinstance(markdown_setting, bool):
            markdown_setting = True

        from .outputpanel import SharedOutputPanelListener
        self.listner = SharedOutputPanelListener(markdown=markdown_setting)

        self.buffer_manager = SublimeBuffer(self.view)
        super(OpenAIWorker, self).__init__()

    # This method appears redundant.
    def update_output_panel(self, text_chunk: str):
        self.listner.update_output_panel(
            text=text_chunk,
            window=self.window
        )

    def prompt_completion(self, completion):
        placeholder = self.settings.get('placeholder')
        if not isinstance(placeholder, str):
            placeholder = "[insert]"
        self.buffer_manager.prompt_completion(
            mode=self.mode,
            completion=completion,
            placeholder=placeholder
        )

    def handle_chat_completion_response(self):
        response = self.provider.execute_response()

        if response is None or response.status != 200:
            print("xxxx5")
            return

        decoder = json.JSONDecoder()

        full_response_content = {"role": "", "content": ""}

        self.update_output_panel("\n\n## Answer\n\n")

        # TODO: This is temporary solution and should be implemented in a better way.
        self.listner.show_panel(window=self.window)

        for chunk in response:
            chunk_str = chunk.decode('utf-8')

            # Check for SSE data
            if chunk_str.startswith("data:") and not re.search(r"\[DONE\]$", chunk_str):
                # print(chunk_str)
                # print(re.search(r"\[DONE\]$", chunk_str))
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

        self.provider.connection.close()
        Cacher().append_to_cache([full_response_content])

    def handle_ordinary_response(self):
        response = self.provider.execute_response()
        if response is None or response.status != 200:
            return
        data = response.read()
        data_decoded = data.decode('utf-8')
        self.provider.connection.close()
        completion = json.loads(data_decoded)['choices'][0]['text']
        completion = completion.strip()  # Remove leading and trailing spaces
        self.prompt_completion(completion)


    def handle_response(self):
        try:
            if self.mode == "chat_completion": self.handle_chat_completion_response()
            else: self.handle_ordinary_response()
        except ContextLengthExceededException as error:
            print("xxxx8")
            if self.mode == 'chat_completion':
                # As user to delete first dialog pair,
                do_delete = sublime.ok_cancel_dialog(msg=f'Delete the two farthest pairs?\n\n{error.message}', ok_title="Delete")
                if do_delete:
                    Cacher().drop_first(2)
                    assistant_role = self.settings.get('assistant_role')
                    if not isinstance(assistant_role, str):
                        raise ValueError("The assistant_role setting must be a string.")
                    payload = self.provider.prepare_payload(mode=self.mode, role=assistant_role)
                    self.provider.prepare_request(gateway="/v1/chat/completions", json_payload=payload)
                    self.handle_response()
            else:
                present_error(title="OpenAI error", error=error)
        except KeyError:
            if self.mode == 'chat_completion' and response['error']['code'] == 'context_length_exceeded':
                Cacher().drop_first(2)
            else:
                sublime.error_message("Exception\n" + "The OpenAI response could not be decoded. There could be a problem on their side. Please look in the console for additional error info.")
                logging.exception("Exception: " + str(response))
            return
        except Exception as ex:
            sublime.error_message(f"Server Error: {str(response.status)}\n{ex}")
            logging.exception("Exception: " + str(data_decoded))
            return

    def run(self):
        try:
            # FIXME: It's better to have such check locally, but it's pretty complicated with all those different modes and models
            # if (self.settings.get("max_tokens") + len(self.text)) > 4000:
            #     raise AssertionError("OpenAI accepts max. 4000 tokens, so the selected text and the max_tokens setting must be lower than 4000.")
            token = self.settings.get('token')
            if not isinstance(token, str):
                raise AssertionError("The token must be a string.")
            if len(token) < 10:
                raise AssertionError("No token provided, you have to set the OpenAI token into the settings to make things work.")
        except Exception as ex:
            sublime.error_message("Exception\n" + str(ex))
            logging.exception("Exception: " + str(ex))
            return

        if self.mode == 'insertion':
            placeholder = self.settings.get('placeholder')
            if not isinstance(placeholder, str):
                raise AssertionError("The placeholder must be a string.")
            parts: List[str] = self.text.split(self.settings.get('placeholder'))
            try:
                if not len(parts) == 2:
                    raise AssertionError("There is no placeholder '" + placeholder + "' within the selected text. There should be exactly one.")
            except Exception as ex:
                sublime.error_message("Exception\n" + str(ex))
                logging.exception("Exception: " + str(ex))
                return
            payload = self.provider.prepare_payload(mode=self.mode, parts=parts)
            self.provider.prepare_request(gateway="/v1/completions", json_payload=payload)
            self.handle_response()

        elif self.mode == 'edition':
            payload = self.provider.prepare_payload(mode=self.mode, text=self.text, command=self.command)
            self.provider.prepare_request(gateway="/v1/edits", json_payload=payload)
            self.handle_response()
        elif self.mode == 'completion':
            payload = self.provider.prepare_payload(mode=self.mode, text=self.text)
            self.provider.prepare_request(gateway="/v1/completions", json_payload=payload)
            self.handle_response()

        elif self.mode == 'chat_completion':
            cacher = Cacher()
            cacher.append_to_cache([self.message])
            self.update_output_panel("\n\n## Question\n\n")
            self.update_output_panel(cacher.read_all()[-1]["content"])

            assistant_role = self.settings.get('assistant_role')
            if not isinstance(assistant_role, str):
                raise ValueError("The assistant_role setting must be a string.")

            payload = self.provider.prepare_payload(mode=self.mode, role=assistant_role)
            self.provider.prepare_request(gateway="/v1/chat/completions", json_payload=payload)
            self.handle_response()
