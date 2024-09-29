from __future__ import annotations

import base64
import copy
import logging
import re
from json import JSONDecoder
from threading import Event, Thread
from typing import Any, Dict, List

import sublime
from sublime import Region, Settings, Sheet, View

from .assistant_settings import (
    DEFAULT_ASSISTANT_SETTINGS,
    AssistantSettings,
    CommandMode,
    PromptMode,
)
from .buffer import TextStreamer
from .cacher import Cacher
from .errors.OpenAIException import (
    ContextLengthExceededException,
    UnknownException,
    WrongUserInputException,
    present_error,
    present_unknown_error,
)
from .openai_network_client import NetworkClient

logger = logging.getLogger(__name__)


class OpenAIWorker(Thread):
    def __init__(
        self,
        stop_event: Event,
        region: Region | None,
        text: str,
        view: View,
        mode: str,
        command: str | None,
        assistant: AssistantSettings | None = None,
        sheets: List[Sheet] | None = None,
    ):
        self.region = region
        # Selected text within editor (as `user`)
        self.text = text
        # Text from input panel (as `user`)
        self.command = command
        self.view = view
        self.mode = mode
        # Text input from input panel
        self.settings: Settings = sublime.load_settings('openAI.sublime-settings')

        logger.debug('OpenAIWorker stop_event id: %s', id(stop_event))
        self.stop_event: Event = stop_event
        logger.debug('OpenAIWorker self.stop_event id: %s', id(self.stop_event))
        self.sheets = sheets

        self.project_settings: Dict[str, str] | None = (
            sublime.active_window().active_view().settings().get('ai_assistant')
        )  # type: ignore

        cache_prefix = self.project_settings.get('cache_prefix') if self.project_settings else None

        self.cacher = Cacher(name=cache_prefix)

        opt_assistant_dict = self.cacher.read_model()
        ## loading assistant dict
        assistant_dict: Dict[str, Any] = (
            opt_assistant_dict if opt_assistant_dict else self.settings.get('assistants')[0]  # type: ignore
        )

        ## merging dicts with a default one and initializing AssitantSettings
        self.assistant = (
            assistant if assistant else AssistantSettings(**{**DEFAULT_ASSISTANT_SETTINGS, **assistant_dict})
        )
        self.provider = NetworkClient(settings=self.settings, assistant=self.assistant, cacher=self.cacher)
        self.window = sublime.active_window()

        markdown_setting = self.settings.get('markdown')
        if not isinstance(markdown_setting, bool):
            markdown_setting = True

        from .output_panel import (
            SharedOutputPanelListener,
        )  # https://stackoverflow.com/a/52927102

        self.listner = SharedOutputPanelListener(markdown=markdown_setting, cacher=self.cacher)

        self.buffer_manager = TextStreamer(self.view)
        super(OpenAIWorker, self).__init__()

    # This method appears redundant.
    def update_output_panel(self, text_chunk: str):
        self.listner.update_output_view(text=text_chunk, window=self.window)

    def delete_selection(self, region: Region):
        self.buffer_manager.delete_selected_region(region=region)

    def update_completion(self, completion: str):
        self.buffer_manager.update_completion(completion=completion)

    def handle_sse_delta(self, delta: Dict[str, Any], full_response_content: Dict[str, str]):
        if self.assistant.prompt_mode == PromptMode.panel.name:
            if 'role' in delta:
                full_response_content['role'] = delta['role']
            if 'content' in delta:
                full_response_content['content'] += delta['content']
                self.update_output_panel(delta['content'])
        else:
            if 'content' in delta:
                self.update_completion(delta['content'])

    def prepare_to_response(self):
        if self.assistant.prompt_mode == PromptMode.panel.name:
            self.update_output_panel('\n\n## Answer\n\n')
            self.listner.show_panel(window=self.window)
            self.listner.scroll_to_botton(window=self.window)

        elif self.assistant.prompt_mode == PromptMode.append.name:
            cursor_pos = self.view.sel()[0].end()
            # clear selections
            self.view.sel().clear()
            # restore cursor position
            self.view.sel().add(Region(cursor_pos, cursor_pos))
            self.update_completion('\n')

        elif self.assistant.prompt_mode == PromptMode.replace.name:
            self.delete_selection(region=self.view.sel()[0])
            cursor_pos = self.view.sel()[0].begin()
            # clear selections
            self.view.sel().clear()
            # restore cursor position
            self.view.sel().add(Region(cursor_pos, cursor_pos))

        elif self.assistant.prompt_mode == PromptMode.insert.name:
            selection_region = self.view.sel()[0]
            try:
                if self.assistant.placeholder:
                    placeholder_region = self.view.find(
                        self.assistant.placeholder,
                        selection_region.begin(),
                        sublime.LITERAL,
                    )
                    if len(placeholder_region) > 0:
                        placeholder_begin = placeholder_region.begin()
                        self.delete_selection(region=placeholder_region)
                        self.view.sel().clear()
                        self.view.sel().add(Region(placeholder_begin, placeholder_begin))
                    else:
                        raise WrongUserInputException(
                            "There is no placeholder '"
                            + self.assistant.placeholder
                            + "' within the selected text. There should be exactly one."
                        )
                elif not self.assistant.placeholder:
                    raise WrongUserInputException(
                        'There is no placeholder value set for this assistant. Please add `placeholder` property in a given assistant setting.'
                    )
            except Exception:
                raise

    def handle_chat_response(self):
        response = self.provider.execute_response()

        if response is None or response.status != 200:
            return

        try:
            self.prepare_to_response()
        except Exception:
            logger.error('prepare_to_response failed')
            self.provider.close_connection()
            raise

        # without key declaration it would failt to append there later in code.
        full_response_content = {'role': '', 'content': ''}

        logger.debug('OpenAIWorker execution self.stop_event id: %s', id(self.stop_event))

        full_text = ''

        for chunk in response:
            # FIXME: With this implementation few last tokens get missed on cacnel action. (e.g. the're seen within a proxy, but not in the code)
            if self.stop_event.is_set():
                self.handle_sse_delta(
                    delta={'role': 'assistant'},
                    full_response_content=full_response_content,
                )
                self.handle_sse_delta(
                    delta={'content': '\n\n[Aborted]'},
                    full_response_content=full_response_content,
                )

                self.provider.close_connection()
                break
            chunk_str = chunk.decode('utf-8')
            full_text = full_text + chunk_str

            # Check for SSE data
            if chunk_str.startswith('data:') and not re.search(r'\[DONE\]$', chunk_str):
                chunk_str = chunk_str[len('data:') :].strip()

                try:
                    response_str: Dict[str, Any] = JSONDecoder().decode(chunk_str)
                    if 'delta' in response_str['choices'][0]:
                        delta: Dict[str, Any] = response_str['choices'][0]['delta']
                        self.handle_sse_delta(delta=delta, full_response_content=full_response_content)
                except:
                    self.provider.close_connection()
                    raise

        json_text = JSONDecoder().decode(full_text)
        self.handle_sse_delta(delta=json_text['choices'][0]['message'], full_response_content=full_response_content)

        self.provider.close_connection()
        if self.assistant.prompt_mode == PromptMode.panel.name:
            if full_response_content['role'] == '':
                full_response_content['role'] = (
                    'assistant'  # together.ai never returns role value, so we have to set it manually
                )
            self.cacher.append_to_cache([full_response_content])
            completion_tokens_amount = self.calculate_completion_tokens([full_response_content])
            self.cacher.append_tokens_count({'completion_tokens': completion_tokens_amount})

    def handle_response(self):
        try:
            self.handle_chat_response()
        except ContextLengthExceededException as error:
            do_delete = sublime.ok_cancel_dialog(
                msg=f'Delete the two farthest pairs?\n\n{error.message}',
                ok_title='Delete',
            )
            if do_delete:
                self.cacher.drop_first(2)
                messages = self.create_message(selected_text=[self.text], command=self.command)
                payload = self.provider.prepare_payload(assitant_setting=self.assistant, messages=messages)
                self.provider.prepare_request(json_payload=payload)
                self.handle_response()
        except WrongUserInputException as error:
            logger.debug('on WrongUserInputException event status: %s', self.stop_event.is_set())
            present_error(title='OpenAI error', error=error)
        except UnknownException as error:
            logger.debug('on UnknownException event status: %s', self.stop_event.is_set())
            present_error(title='OpenAI error', error=error)

    def wrap_sheet_contents_with_scope(self) -> List[str]:
        wrapped_selection: List[str] = []

        if self.sheets:
            for sheet in self.sheets:
                # Convert the sheet to a view
                view = sheet.view() if sheet else None
                if not view:
                    continue  # If for some reason the sheet cannot be converted to a view, skip.

                # Deriving the scope from the beginning of the view's content
                scope_region = view.scope_name(0)  # Assuming you want the scope at the start of the document
                scope_name = scope_region.split(' ')[0].split('.')[-1]

                # Extracting the text from the view
                content = view.substr(sublime.Region(0, view.size()))

                # Wrapping the content with the derived scope name
                wrapped_content = f'```{scope_name}\n{content}\n```'
                wrapped_selection.append(wrapped_content)

        return wrapped_selection

    def manage_chat_completion(self):
        wrapped_selection = None
        if self.region:
            scope_region = self.window.active_view().scope_name(self.region.begin())
            scope_name = scope_region.split('.')[-1]  # in case of precise selection take the last scope
            wrapped_selection = [f'```{scope_name}\n' + self.text + '\n```']
        if self.sheets:  # no sheets should be passed unintentionaly
            wrapped_selection = (
                self.wrap_sheet_contents_with_scope()
            )  # in case of unprecise selection take the last scope

        if self.mode == CommandMode.handle_image_input.value:
            messages = self.create_image_message(image_url=self.text, command=self.command)
            ## MARK: This should be here, otherwise it would duplicates the messages.
            image_assistant = copy.deepcopy(self.assistant)
            image_assistant.assistant_role = (
                "Follow user's request on an image provided. "
                'If none provided do either: '
                '1. Describe this image that it be possible to drop it from the chat history without any context lost. '
                "2. It it's just a text screenshot prompt its literally with markdown formatting (don't wrapp the text into markdown scope). "
                "3. If it's a figma/sketch mock, provide the exact code of the exact following layout with the tools of user's choise. "
                'Pay attention between text screnshot and a mock of the design in figma or sketch'
            )
            payload = self.provider.prepare_payload(assitant_setting=image_assistant, messages=messages)
        else:
            messages = self.create_message(
                selected_text=wrapped_selection,
                command=self.command,
                placeholder=self.assistant.placeholder,
            )
            ## MARK: This should be here, otherwise it would duplicates the messages.
            payload = self.provider.prepare_payload(assitant_setting=self.assistant, messages=messages)

        if self.assistant.prompt_mode == PromptMode.panel.name:
            if self.mode == CommandMode.handle_image_input.value:
                fake_messages = self.create_image_fake_message(self.text, self.command)
                self.cacher.append_to_cache(fake_messages)
            else:
                self.cacher.append_to_cache(messages)
            self.update_output_panel('\n\n## Question\n\n')

            # MARK: Read only last few messages from cache with a len of a messages list
            questions = [value['content'] for value in self.cacher.read_all()[-len(messages) :]]

            # MARK: \n\n for splitting command from selected text
            # FIXME: This logic adds redundant line breaks on a single message.
            [self.update_output_panel(question + '\n\n') for question in questions]

            # Clearing selection area, coz it's easy to forget that there's something selected during a chat conversation.
            # And it designed be a one shot action rather then persistant one.
            #
            # We're doing it here just in sake of more clear user flow, because text got captured at the very beginning of a command evaluation,
            # convenience is in being able see current selection while writting additional input to an assistant by input panel.
            self.view.sel().clear()
        try:
            self.provider.prepare_request(json_payload=payload)
        except Exception as error:
            present_unknown_error(title='OpenAI error', error=error)
            return
        self.handle_response()

    def create_message(
        self,
        selected_text: List[str] | None,
        command: str | None,
        placeholder: str | None = None,
    ) -> List[Dict[str, str]]:
        messages = []
        if placeholder:
            messages.append(
                {
                    'role': 'system',
                    'content': f'placeholder: {placeholder}',
                    'name': 'OpenAI_completion',
                }
            )
        if selected_text:
            messages.extend(
                [{'role': 'user', 'content': text, 'name': 'OpenAI_completion'} for text in selected_text]
            )
        if command:
            messages.append({'role': 'user', 'content': command, 'name': 'OpenAI_completion'})
        return messages

    def create_image_fake_message(self, image_url: str | None, command: str | None) -> List[Dict[str, str]]:
        messages = []
        if image_url:
            messages.append({'role': 'user', 'content': command, 'name': 'OpenAI_completion'})
        if image_url:
            messages.append({'role': 'user', 'content': image_url, 'name': 'OpenAI_completion'})
        return messages

    def encode_image(self, image_path: str) -> str:
        with open(image_path, 'rb') as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def create_image_message(self, image_url: str | None, command: str | None) -> List[Dict[str, Any]]:
        """Create a message with a list of image URLs (in base64) and a command."""
        messages = []

        # Split single image_urls_string by newline into multiple paths
        if image_url:
            image_urls = image_url.split('\n')
            image_data_list = []

            for image_url in image_urls:
                image_url = image_url.strip()
                if image_url:  # Only handle non-empty lines
                    base64_image = self.encode_image(image_url)
                    image_data_list.append(
                        {
                            'type': 'image_url',
                            'image_url': {'url': f'data:image/jpeg;base64,{base64_image}'},
                        }
                    )

            # Add to the message with the command and all the base64 images
            messages.append(
                {
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': command},
                        *image_data_list,  # Add all the image data
                    ],
                    'name': 'OpenAI_completion',
                }
            )

        return messages

    def run(self):
        try:
            # FIXME: It's better to have such check locally, but it's pretty complicated with all those different modes and models
            # if (self.settings.get("max_tokens") + len(self.text)) > 4000:
            #     raise AssertionError("OpenAI accepts max. 4000 tokens, so the selected text and the max_tokens setting must be lower than 4000.")
            api_token = self.settings.get('token')
            if not isinstance(api_token, str):
                raise WrongUserInputException('The token must be a string.')
            if len(api_token) < 10:
                raise WrongUserInputException(
                    'No API token provided, you have to set the OpenAI token into the settings to make things work.'
                )
        except WrongUserInputException as error:
            present_error(title='OpenAI error', error=error)
            return

        self.manage_chat_completion()

    def calculate_completion_tokens(self, responses: List[Dict[str, str]]) -> int:
        total_tokens = 0
        for response in responses:
            if response['content'] and response['role'] == 'assistant':
                total_tokens += int(len(response['content']) / 4)
        return total_tokens
