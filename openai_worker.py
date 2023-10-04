import sublime
from sublime import View, Region
import threading
from .cacher import Cacher
from typing import Dict, List, Optional, Any
from .openai_network_client import NetworkClient
from .buffer import TextStramer
from .errors.OpenAIException import ContextLengthExceededException, UnknownException, WrongUserInputException, present_error, present_unknown_error
from .assistant_settings import AssistantSettings, DEFAULT_ASSISTANT_SETTINGS, PromptMode
import json
from json import JSONDecoder
import logging
import re


class OpenAIWorker(threading.Thread):
    def __init__(self, region: Optional[Region], text: Optional[str], view: View, mode: str, command: Optional[str], assistant: Optional[AssistantSettings] = None):
        self.region = region
        # Selected text within editor (as `user`)
        self.text = text
        # Text from input panel (as `user`)
        self.command = command # optional
        self.view = view
        self.mode = mode
        # Text input from input panel
        self.settings = sublime.load_settings("openAI.sublime-settings")

        opt_assistant_dict = Cacher().read_model()
        ## loading assistant dict
        assistant_dict = opt_assistant_dict if opt_assistant_dict else self.settings.get('assistants')[0]
        ## merging dicts with a default one and initializing AssitantSettings
        self.assistant = assistant if assistant is not None else AssistantSettings(**{**DEFAULT_ASSISTANT_SETTINGS, **assistant_dict})
        self.provider = NetworkClient(settings=self.settings)
        self.window = sublime.active_window()

        markdown_setting = self.settings.get('markdown')
        if not isinstance(markdown_setting, bool):
            markdown_setting = True

        from .outputpanel import SharedOutputPanelListener # https://stackoverflow.com/a/52927102
        self.listner = SharedOutputPanelListener(markdown=markdown_setting)

        self.buffer_manager = TextStramer(self.view)
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

    def delete_selection(self, region):
        self.buffer_manager.delete_selected_region(region=region)

    def update_completion(self, completion):
        self.buffer_manager.update_completion(completion=completion)

    def handle_sse_delta(self, delta: Dict[str, Any], full_response_content:Dict[str, str]):
        if self.assistant.prompt_mode == PromptMode.panel.name:
            if 'role' in delta:
                full_response_content['role'] = delta['role']
            elif 'content' in delta:
                full_response_content['content'] += delta['content']
                self.update_output_panel(delta['content'])
        else:
            if 'content' in delta:
                self.update_completion(delta['content'])

    def prepare_to_response(self):
        if self.assistant.prompt_mode == PromptMode.panel.name:
            self.update_output_panel("\n\n## Answer\n\n")
            self.listner.show_panel(window=self.window)
            self.listner.toggle_overscroll(window=self.window, enabled=False)

        elif self.assistant.prompt_mode == PromptMode.append.name:
            cursor_pos = self.view.sel()[0].end()
            # clear selections
            self.view.sel().clear()
            # restore cursor position
            self.view.sel().add(Region(cursor_pos, cursor_pos))
            self.update_completion("\n")

        elif self.assistant.prompt_mode == PromptMode.replace.name:
            self.delete_selection(region=self.view.sel()[0])
            cursor_pos = self.view.sel()[0].begin()
            # clear selections
            self.view.sel().clear()
            # restore cursor position
            self.view.sel().add(Region(cursor_pos, cursor_pos))

        elif self.assistant.prompt_mode == PromptMode.insert.name:
            # FIXME: Broken code,
            # Execution continues after error thrown.
            selection_region = self.view.sel()[0]
            try:
                if self.assistant.placeholder:
                    placeholder_region = self.view.find(self.assistant.placeholder, selection_region.begin(), sublime.LITERAL)
                    if len(placeholder_region) > 0:
                        placeholder_begin = placeholder_region.begin()
                        self.delete_selection(region=placeholder_region)
                        self.view.sel().clear()
                        self.view.sel().add(Region(placeholder_begin, placeholder_begin))
                    else:
                        raise WrongUserInputException("There is no placeholder '" + self.assistant.placeholder + "' within the selected text. There should be exactly one.")
                elif not self.assistant.placeholder:
                    raise WrongUserInputException("There is no placeholder value set for this assistant. Please add `placeholder` property in a given assistant setting.")
            except Exception:
                raise

    def handle_chat_response(self):
        response = self.provider.execute_response()

        if response is None or response.status != 200: return

        try:
            self.prepare_to_response()
        except Exception:
            raise

        # without key declaration it would failt to append there later in code.
        full_response_content = {'role': '', 'content': ''}

        for chunk in response:
            chunk_str = chunk.decode('utf-8')

            # Check for SSE data
            if chunk_str.startswith("data:") and not re.search(r"\[DONE\]$", chunk_str):
                chunk_str = chunk_str[len("data:"):].strip()

                try:
                    response = JSONDecoder().decode(chunk_str)
                    if 'delta' in response['choices'][0]:
                        delta = response['choices'][0]['delta']
                        self.handle_sse_delta(delta=delta, full_response_content=full_response_content)
                except: raise

        self.provider.connection.close()
        if self.assistant.prompt_mode == PromptMode.panel.name:
            Cacher().append_to_cache([full_response_content])

    def handle_deprecated_response(self):
        response = self.provider.execute_response()
        if response is None or response.status != 200:
            return
        data = response.read()
        data_decoded = data.decode('utf-8')
        self.provider.connection.close()
        completion = json.loads(data_decoded)['choices'][0]['text']
        completion = completion.strip()  # Removing leading and trailing spaces
        self.prompt_completion(completion)

    def handle_response(self):
        try:
            if self.mode == "chat_completion": self.handle_chat_response()
            else: self.handle_deprecated_response()
        except ContextLengthExceededException as error:
            if self.mode == 'chat_completion':
                # Ask user if it's ok to delete first dialog pair?
                do_delete = sublime.ok_cancel_dialog(msg=f'Delete the two farthest pairs?\n\n{error.message}', ok_title="Delete")
                if do_delete:
                    Cacher().drop_first(2)
                    messages = self.create_message(selected_text=self.text, command=self.command)
                    payload = self.provider.prepare_payload(assitant_setting=self.assistant, messages=messages)
                    self.provider.prepare_request(json_payload=payload)
                    self.handle_response()
            else:
                present_error(title="OpenAI error", error=error)
        except WrongUserInputException as error:
            present_error(title="OpenAI error", error=error)
            return
        except UnknownException as error:
            present_error(title="OpenAI error", error=error)
            return

    def manage_chat_completion(self):
        messages = self.create_message(selected_text=self.text, command=self.command, placeholder=self.assistant.placeholder)
        if self.assistant.prompt_mode == PromptMode.panel.name:
            cacher = Cacher()
            cacher.append_to_cache(messages)
            self.update_output_panel("\n\n## Question\n\n")

            # MARK: Read only last few messages from cache with a len of a messages list
            questions = [value['content'] for value in cacher.read_all()[-len(messages):]]

            # MARK: \n\n for splitting command from selected text
            # FIXME: This logic adds redundant line breaks on a single message.
            [self.update_output_panel(question + "\n\n") for question in questions]

            # Clearing selection area, coz it's easy to forget that there's something selected during a chat conversation.
            # And it designed be a one shot action rather then persistant one.
            #
            # We're doing it here just in sake of more clear user flow, because text got captured at the very beginning of a command evaluation,
            # convenience is in being able see current selection while writting additional input to an assistant by input panel.
            self.view.sel().clear()

        payload = self.provider.prepare_payload(assitant_setting=self.assistant, messages=messages)
        try:
            self.provider.prepare_request(json_payload=payload)
        except Exception as error:
            present_unknown_error(title="OpenAI error", error=error)
            return
        self.handle_response()

    def create_message(self, selected_text: Optional[str], command: Optional[str], placeholder: Optional[str] = None) -> List[Dict[str, str]]:
        messages = []
        if placeholder: messages.append({"role": "system", "content": f'placeholder: {placeholder}', 'name': 'OpenAI_completion'})
        if selected_text: messages.append({"role": "user", "content": selected_text, 'name': 'OpenAI_completion'})
        if command: messages.append({"role": "user", "content": command, 'name': 'OpenAI_completion'})
        return messages

    def run(self):
        try:
            # FIXME: It's better to have such check locally, but it's pretty complicated with all those different modes and models
            # if (self.settings.get("max_tokens") + len(self.text)) > 4000:
            #     raise AssertionError("OpenAI accepts max. 4000 tokens, so the selected text and the max_tokens setting must be lower than 4000.")
            api_token = self.settings.get('token')
            if not isinstance(api_token, str):
                raise WrongUserInputException("The token must be a string.")
            if len(api_token) < 10:
                raise WrongUserInputException("No API token provided, you have to set the OpenAI token into the settings to make things work.")
        except WrongUserInputException as error:
            present_error(title="OpenAI error", error=error)
            return

        ### ---------- DEPRECATED CODE ---------- ###
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
            payload = self.provider.prepare_payload_deprecated(mode=self.mode, parts=parts)
            self.provider.prepare_request_deprecated(gateway="/v1/completions", json_payload=payload)
            self.handle_response()

        elif self.mode == 'edition':
            payload = self.provider.prepare_payload_deprecated(mode=self.mode, text=self.text, command=self.command)
            self.provider.prepare_request_deprecated(gateway="/v1/edits", json_payload=payload)
            self.handle_response()
        elif self.mode == 'completion':
            payload = self.provider.prepare_payload_deprecated(mode=self.mode, text=self.text)
            self.provider.prepare_request_deprecated(gateway="/v1/completions", json_payload=payload)
            self.handle_response()
        ### ---------- DEPRECATED CODE ---------- ###

        elif self.mode == 'chat_completion':
            self.manage_chat_completion()
