from __future__ import annotations

import copy
import logging
import re
from http.client import HTTPResponse
from json import JSONDecodeError, JSONDecoder, loads
from threading import Event, Thread
from typing import Any, Dict, List

import sublime
from sublime import Region, Settings, Sheet, View

from .assistant_settings import (
    DEFAULT_ASSISTANT_SETTINGS,
    AssistantSettings,
    CommandMode,
    Function,
    PromptMode,
    ToolCall,
)
from .cacher import Cacher
from .errors.OpenAIException import (
    ContextLengthExceededException,
    FunctionCallFailedException,
    UnknownException,
    WrongUserInputException,
    present_error,
    present_unknown_error,
)
from .messages import MessageCreator
from .openai_network_client import NetworkClient
from .phantom_streamer import PhantomStreamer
from .response_manager import ResponseManager
from .function_handler import FunctionHandler
from .buffer import BufferContentManager

logger = logging.getLogger(__name__)


class OpenAIWorker(Thread):
    current_request: List[Dict[str, Any]] | List[Dict[str, str]]

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
        self.selected_text = text  # Selected text within editor (as `user`)
        logger.debug('selected_text in worker %s:', text)
        self.command = command  # Text from input panel (as `user`)
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

        self.phantom_manager = PhantomStreamer(self.view, self.cacher)
        super(OpenAIWorker, self).__init__()

    def handle_function_call(self, tool_calls: List[ToolCall]):
        for tool in tool_calls:
            logger.debug(f'{tool.function.name} function called')
            messages = []
            try:
                messages = FunctionHandler.perform_function(cacher=self.cacher, window=self.window, tool=tool)
            except FunctionCallFailedException as error:  # we have to notify assistant about error occured
                messages = MessageCreator.create_message(
                    self.cacher, command=error.message, tool_call_id=tool.id
                )
            except:
                raise
            payload = self.provider.prepare_payload(assitant_setting=self.assistant, messages=messages)
            new_messages = messages[-1:]
            self.cacher.append_to_cache(new_messages)
            self.provider.prepare_request(json_payload=payload)
            if self.assistant.prompt_mode == PromptMode.panel.value:
                ResponseManager.prepare_to_response(self.listner, self.window)

            self.handle_response()

    def handle_streaming_response(self, response: HTTPResponse):
        # without key declaration it would failt to append there later in code.
        full_response_content = {'role': '', 'content': ''}
        full_function_call: Dict[str, Any] = {}

        logger.debug('OpenAIWorker execution self.stop_event id: %s', id(self.stop_event))
        listner = (
            self.phantom_manager if self.assistant.prompt_mode == PromptMode.phantom.value else self.listner
        )

        for chunk in response:
            # FIXME: With this implementation few last tokens get missed on cacnel action.
            # (e.g. they're seen within a proxy, but not in the code)
            if self.stop_event.is_set():
                ResponseManager.handle_sse_delta(
                    listner,
                    self.current_request,
                    self.window,
                    self.assistant.prompt_mode,
                    delta={'role': 'assistant'},
                    full_response_content=full_response_content,
                )
                ResponseManager.handle_sse_delta(
                    listner,
                    self.current_request,
                    self.window,
                    self.assistant.prompt_mode,
                    delta={'content': '\n\n[Aborted]'},
                    full_response_content=full_response_content,
                )

                self.provider.close_connection()
                break
            chunk_str = chunk.decode()

            # Check for SSE data
            if chunk_str.startswith('data:') and not re.search(r'\[DONE\]$', chunk_str):
                chunk_str = chunk_str[len('data:') :].strip()

                try:
                    response_dict: Dict[str, Any] = JSONDecoder().decode(chunk_str)
                    if 'delta' in response_dict['choices'][0]:
                        delta: Dict[str, Any] = response_dict['choices'][0]['delta']
                        if delta.get('content'):
                            ResponseManager.handle_sse_delta(
                                listner,
                                self.current_request,
                                self.window,
                                self.assistant.prompt_mode,
                                delta=delta,
                                full_response_content=full_response_content,
                            )
                        elif delta.get('tool_calls'):
                            FunctionHandler.append_non_null(full_function_call, delta)

                except:
                    self.provider.close_connection()
                    raise

        logger.debug(f'function_call {full_function_call}')
        self.provider.close_connection()

        if full_function_call:
            tool_calls = [
                ToolCall(
                    index=call['index'],
                    id=call['id'],
                    type=call['type'],
                    function=Function(
                        name=call['function']['name'], arguments=loads(call['function']['arguments'])
                    ),
                )
                for call in full_function_call['tool_calls']
            ]
            ResponseManager.update_output_panel_(
                self.listner, self.window, f'Function calling: `{tool_calls[0].function.name}`'
            )
            self.cacher.append_to_cache([full_function_call])
            self.handle_function_call(tool_calls)

        if self.assistant.prompt_mode == PromptMode.panel.name:
            if full_response_content['role'] == '':
                # together.ai never returns role value, so we have to set it manually
                full_response_content['role'] = 'assistant'
            self.cacher.append_to_cache([full_response_content])
            completion_tokens_amount = MessageCreator.calculate_completion_tokens([full_response_content])
            self.cacher.append_tokens_count({'completion_tokens': completion_tokens_amount})

    def handle_plain_response(self, response: HTTPResponse):
        # Prepare the full response content structure
        full_response_content = {'role': '', 'content': ''}

        logger.debug('Handling plain (non-streaming) response for OpenAIWorker.')

        listner = self.phantom_manager if self.assistant.prompt_mode == PromptMode.phantom else self.listner
        # Read the complete response directly
        response_data = response.read().decode()
        logger.debug(f'raw response: {response_data}')

        try:
            # Parse the JSON response
            response_dict: Dict[str, Any] = JSONDecoder().decode(response_data)
            logger.debug(f'raw dict: {response_dict}')

            # Ensure there's at least one choice
            if 'choices' in response_dict and len(response_dict['choices']) > 0:
                choice = response_dict['choices'][0]
                logger.debug(f'choise: {choice}')

                if 'message' in choice:
                    message = choice['message']
                    logger.debug(f'message: {message}')
                    # Directly populate the full response content
                    if 'role' in message:
                        full_response_content['role'] = message['role']
                    if 'content' in message:
                        full_response_content['content'] = message['content']

            # If role is not set, default it
            if full_response_content['role'] == '':
                full_response_content['role'] = 'assistant'

            ResponseManager.handle_whole_response(
                listner,
                self.current_request,
                self.window,
                self.assistant.prompt_mode,
                content=full_response_content,
            )
            # Store the response in the cache
            self.cacher.append_to_cache([full_response_content])

            # Calculate and store the token count
            completion_tokens_amount = MessageCreator.calculate_completion_tokens([full_response_content])
            self.cacher.append_tokens_count({'completion_tokens': completion_tokens_amount})

        except JSONDecodeError as e:
            logger.error('Failed to decode JSON response: %s', e)
            self.provider.close_connection()
            raise
        except Exception as e:
            logger.error('An error occurred while handling the plain response: %s', e)
            self.provider.close_connection()
            raise

        # Close the connection
        self.provider.close_connection()

    def handle_response(self):
        try:
            ## Step 1: Prepare and get the chat response
            response = self.provider.execute_response()

            if response is None or response.status != 200:
                return  # Exit if there's no valid response

            # Step 2: Handle the response based on whether it's streaming
            if self.assistant.stream:
                self.handle_streaming_response(response)
            else:
                self.handle_plain_response(response)

        # Step 3: Exception Handling
        except ContextLengthExceededException as error:
            do_delete = sublime.ok_cancel_dialog(
                msg=f'Delete the two farthest pairs?\n\n{error.message}',
                ok_title='Delete',
            )
            if do_delete:
                self.cacher.drop_first(2)  # Drop old requests from the cache
                messages = MessageCreator.create_message(self.cacher)
                payload = self.provider.prepare_payload(assitant_setting=self.assistant, messages=messages)
                self.provider.prepare_request(json_payload=payload)

                # Retry after dropping extra cache loads
                self.handle_response()

        except WrongUserInputException as error:
            logger.debug('on WrongUserInputException event status: %s', self.stop_event.is_set())
            present_error(title='OpenAI error', error=error)

        except UnknownException as error:
            logger.debug('on UnknownException event status: %s', self.stop_event.is_set())
            present_error(title='OpenAI error', error=error)

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

        wrapped_selection = None
        if self.sheets:
            wrapped_selection = BufferContentManager.wrap_sheet_contents_with_scope(self.sheets)
        elif self.region:
            scope_region = self.window.active_view().scope_name(self.region.begin())
            scope_name = scope_region.split('.')[-1]  # in case of precise selection take the last scope
            wrapped_selection = [
                (
                    scope_name,
                    None,
                    BufferContentManager.wrap_content_with_scope(scope_name, self.selected_text),
                )
            ]
        elif self.selected_text:  # build_input
            wrapped_selection = [
                (
                    'log',
                    None,
                    BufferContentManager.wrap_content_with_scope('log', self.selected_text),
                )
            ]

        if self.mode == CommandMode.handle_image_input.value:
            messages = MessageCreator.create_image_message(
                self.cacher, image_url=self.selected_text, command=self.command
            )
            ## MARK: This should be here, otherwise it would duplicates the messages.
            image_assistant = copy.deepcopy(self.assistant)
            image_assistant.assistant_role = (
                "Follow user's request on an image provided."
                '\nIf none provided do either:'
                '\n1. Describe this image that it be possible to drop it from the chat history without any context lost.'
                "\n2. It it's just a text screenshot prompt its literally with markdown formatting (don't wrapp the text into markdown scope)."
                "\n3. If it's a figma/sketch mock, provide the exact code of the exact following layout with the tools of user's choise."
                '\nPay attention between text screnshot and a mock of the design in figma or sketch'
            )
            payload = self.provider.prepare_payload(assitant_setting=image_assistant, messages=messages)
        else:
            messages = MessageCreator.create_message(
                self.cacher,
                selected_text=wrapped_selection,  # type: ignore
                command=self.command,
            )
            payload = self.provider.prepare_payload(assitant_setting=self.assistant, messages=messages)

        new_messages_len = (
            len(wrapped_selection) + 1 if wrapped_selection else 1  # 1 stands for user input
        )
        new_messages = messages[-new_messages_len:]

        self.current_request = new_messages
        if self.assistant.prompt_mode == PromptMode.panel.name:
            # MARK: Read only last few messages from cache with a len of a messages list
            # questions = [value['content'] for value in self.cacher.read_all()[-len(messages) :]]
            fake_messages = None
            if self.mode == CommandMode.handle_image_input.value:
                fake_messages = MessageCreator.create_image_fake_message(
                    self.cacher, self.selected_text, self.command
                )
                self.cacher.append_to_cache(fake_messages)
                new_messages = fake_messages
            else:
                self.cacher.append_to_cache(new_messages)

            ResponseManager.update_output_panel_(self.listner, self.window, '\n\n## Question\n\n')
            # MARK: \n\n for splitting command from selected text
            # FIXME: This logic adds redundant line breaks on a single message.
            [
                ResponseManager.update_output_panel_(self.listner, self.window, question['content'] + '\n\n')
                for question in new_messages
            ]

            # Clearing selection area, coz it's easy to forget that there's something selected during a chat conversation.
            # And it designed be a one shot action rather then persistant one.
            self.view.sel().clear()
        try:
            self.provider.prepare_request(json_payload=payload)
        except Exception as error:
            present_unknown_error(title='OpenAI error', error=error)
            return
        if self.assistant.prompt_mode == PromptMode.panel.value:
            ResponseManager.prepare_to_response(self.listner, self.window)

        self.handle_response()
