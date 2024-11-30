from __future__ import annotations

import base64
import copy
import logging
import re
from http.client import HTTPResponse
from json import JSONDecodeError, JSONDecoder, dumps, loads
from threading import Event, Thread
from typing import Any, Dict, List, Tuple, Union

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
from .openai_network_client import NetworkClient
from .phantom_streamer import PhantomStreamer
from .response_manager import ResponseManager
from .project_structure import build_folder_structure

logger = logging.getLogger(__name__)


JSONObject = Dict[str, Any]  # A JSON object is typically a dict with string keys
JSONArray = List[Any]  # A JSON array is typically a list of any types
JSONType = Union[JSONObject, JSONArray, str, int, float, bool, None]  # Any valid JSON type


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
        # Selected text within editor (as `user`)
        self.selected_text = text
        logger.debug('selected_text in worker %s:', text)
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

        self.phantom_manager = PhantomStreamer(self.view, self.cacher)
        super(OpenAIWorker, self).__init__()

    @staticmethod
    def append_non_null(original: JSONType, append: JSONType) -> JSONType:
        """
        Recursively processes the object, returning only non-null fields.
        """
        if isinstance(original, int) and isinstance(append, int):
            # logger.debug(f'original: int `{original}`, append: int `{append}`')
            original += append
            return original

        elif isinstance(original, str) and isinstance(append, str):
            # logger.debug(f'original: str `{original}`, append: str `{append}`')
            original += append
            return original

        elif isinstance(original, dict) and isinstance(append, dict):
            # logger.debug(f'original: dict `{original}`, append: dict `{append}`')
            for key, value in append.items():
                if value is not None:
                    if key in original:
                        original[key] = OpenAIWorker.append_non_null(original[key], value)
                    else:
                        original[key] = value
            return original

        elif isinstance(append, list) and isinstance(original, list):
            # logger.debug(f'original: list `{original}`, append: list `{append}`')
            # Append non-null values from append to the original list
            for index, item in enumerate(append):
                if (
                    isinstance(original, list)
                    and isinstance(original[index], dict)
                    and isinstance(item, dict)
                ):
                    if original[index].get('index') == item['index']:
                        OpenAIWorker.append_non_null(original[index], item)
                        return original
                if isinstance(item, dict):
                    original.append(item)
            return original

        # If the object is neither a dictionary nor a list, return it directly
        return original

    def prepare_to_response(self):
        ResponseManager.update_output_panel_(self.listner, self.window, '\n\n## Answer\n\n')
        self.listner.show_panel(window=self.window)
        self.listner.scroll_to_botton(window=self.window)

    def perform_function(self, tool: ToolCall) -> List[Dict[str, str]]:
        if tool.function.name == 'get_region_for_text':
            path = tool.function.arguments.get('file_path')
            content = tool.function.arguments.get('content')
            if path and isinstance(path, str) and content and isinstance(content, str):
                view = self.window.find_open_file(path)
                if view:
                    logger.debug(f'{tool.function.name} executing')
                    escaped_string = (
                        content.replace('(', r'\(')
                        .replace(')', r'\)')
                        .replace('[', r'\[')
                        .replace(']', r'\]')
                        .replace('{', r'\{')
                        .replace('}', r'\}')
                    )
                    region = view.find(pattern=escaped_string, start_pt=0)
                    logger.debug(f'region {region}')
                    serializable_region = {
                        'begin': region.begin(),
                        'end': region.end(),
                    }
                    if region.begin() == region.end() == -1:  # means search found nothing
                        raise FunctionCallFailedException(f'Text not found: {content}')
                    else:
                        return self.create_message(command=dumps(serializable_region), tool_call_id=tool.id)
                else:
                    raise FunctionCallFailedException(f'File under path not found: {path}')
            else:
                raise FunctionCallFailedException(f'Wrong attributes passed: {path}, {content}')

        elif tool.function.name == 'replace_text_for_region':
            path = tool.function.arguments.get('file_path')
            region = tool.function.arguments.get('region')
            content = tool.function.arguments.get('content')
            if (
                path
                and isinstance(path, str)
                and region
                and isinstance(region, Dict)
                and content
                and isinstance(content, str)
            ):
                view = self.window.find_open_file(path)
                if view:
                    logger.debug(f'{tool.function.name} executing')
                    view.run_command('replace_region', {'region': region, 'text': content})
                    region = Region(a=(region.get('a') - 30), b=(region.get('b') + 30))  # type: ignore
                    text = view.substr(region)
                    return self.create_message(
                        command=dumps({'result_with_vicinity_30': text}), tool_call_id=tool.id
                    )
                else:
                    raise FunctionCallFailedException(f'File under path not found: {path}')
            else:
                raise FunctionCallFailedException(f'Wrong attributes passed: {path}, {region} {content}')

        elif tool.function.name == 'read_region_content':
            path = tool.function.arguments.get('file_path')
            region = tool.function.arguments.get('region')
            if path and isinstance(path, str) and region and isinstance(region, Dict):
                view = self.window.find_open_file(path)
                if view:
                    logger.debug(f'{tool.function.name} executing')
                    region_ = Region(a=(region.get('a') - 30), b=(region.get('b') + 30))  # type: ignore
                    text = view.substr(region_)
                    return self.create_message(command=dumps({'content': f'{text}'}), tool_call_id=tool.id)
                else:
                    raise FunctionCallFailedException(f'File under path not found: {path}')
            else:
                raise FunctionCallFailedException(f'Wrong attributes passed: {path}, {region}')
        elif tool.function.name == 'get_working_directory_content':
            path = tool.function.arguments.get('directory_path')
            if path and isinstance(path, str):
                folder_structure = build_folder_structure(path)
                logger.debug(f'{tool.function.name} executing')

                return self.create_message(
                    command=dumps({'content': f'{folder_structure}'}), tool_call_id=tool.id
                )
            else:
                raise FunctionCallFailedException(f'Wrong attributes passed: {path}')
        else:
            raise FunctionCallFailedException(f"Called function don't exists: {tool.function.name}")

    def handle_function_call(self, tool_calls: List[ToolCall]):
        for tool in tool_calls:
            logger.debug(f'{tool.function.name} function called')
            messages = []
            try:
                messages = self.perform_function(tool=tool)
            except FunctionCallFailedException as error:  # we have to notify assistant about error occured
                messages = self.create_message(command=error.message, tool_call_id=tool.id)
            except:
                raise
            payload = self.provider.prepare_payload(assitant_setting=self.assistant, messages=messages)
            new_messages = messages[-1:]
            self.cacher.append_to_cache(new_messages)
            self.provider.prepare_request(json_payload=payload)
            if self.assistant.prompt_mode == PromptMode.panel.value:
                self.prepare_to_response()

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
                            self.append_non_null(full_function_call, delta)

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
            completion_tokens_amount = self.calculate_completion_tokens([full_response_content])
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
            completion_tokens_amount = self.calculate_completion_tokens([full_response_content])
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
                messages = self.create_message()
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

    @classmethod
    def wrap_content_with_scope(cls, scope_name: str, content: str) -> str:
        logger.debug(f'scope_name {scope_name}')
        if scope_name.strip().lower() in ['markdown', 'multimarkdown', 'plain']:
            wrapped_content = content
        else:
            wrapped_content = f'```{scope_name}\n{content}\n```'
        logger.debug(f'wrapped_content {wrapped_content}')
        return wrapped_content

    def wrap_sheet_contents_with_scope(self) -> List[Tuple[str, str | None, str]]:
        wrapped_selection: List[Tuple[str, str | None, str]] = []

        if self.sheets:
            for sheet in self.sheets:
                view = sheet.view()
                if not view:
                    continue  # If for some reason the sheet cannot be converted to a view, skip.

                scope_region = view.scope_name(0)  # Assuming you want the scope at the start of the document
                scope_name = scope_region.split(' ')[0].split('.')[-1]

                file_path = view.file_name()
                content = view.substr(sublime.Region(0, view.size()))
                content = OpenAIWorker.wrap_content_with_scope(scope_name, content)

                wrapped_content = f'Path: `{file_path}`\n\n' + content
                wrapped_selection.append((scope_name, file_path, wrapped_content))

        return wrapped_selection

    def manage_chat_completion(self):
        wrapped_selection = None
        if self.sheets:
            wrapped_selection = self.wrap_sheet_contents_with_scope()
        elif self.region:
            scope_region = self.window.active_view().scope_name(self.region.begin())
            scope_name = scope_region.split('.')[-1]  # in case of precise selection take the last scope
            wrapped_selection = [
                (
                    scope_name,
                    None,
                    OpenAIWorker.wrap_content_with_scope(scope_name, self.selected_text),
                )
            ]
        elif self.selected_text:  # build_input
            wrapped_selection = [
                (
                    'log',
                    'Build log',
                    OpenAIWorker.wrap_content_with_scope('log', self.selected_text),
                )
            ]

        if self.mode == CommandMode.handle_image_input.value:
            messages = self.create_image_message(image_url=self.selected_text, command=self.command)
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
            messages = self.create_message(
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
                fake_messages = self.create_image_fake_message(self.selected_text, self.command)
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
            self.prepare_to_response()

        self.handle_response()

    def create_message(
        self,
        selected_text: List[Tuple[str, str | None, str]] | None = None,
        command: str | None = None,
        tool_call_id: str | None = None,
    ) -> List[Dict[str, str]]:
        messages = self.cacher.read_all()
        logger.debug(len(selected_text) if selected_text else None)
        if selected_text:
            new_messages = [
                {
                    'role': 'user',
                    **({'file_path': file_path} if file_path is not None else {}),
                    **({'scope_name': scope} if scope is not None else {}),
                    'content': text,  # Content
                    'name': 'OpenAI_completion',
                }
                for scope, file_path, text in selected_text  # Iterates over provided non-None selected_text
            ]

            logger.debug(['content' in message for message in new_messages])
            messages.extend(new_messages)

        if command:
            if tool_call_id:
                messages.append(
                    {
                        'role': 'tool',
                        'content': command,
                        'tool_call_id': tool_call_id,
                        'name': 'OpenAI_completion',
                    }
                )
            else:
                messages.append({'role': 'user', 'content': command, 'name': 'OpenAI_completion'})

        logger.debug(['content' in message for message in messages])
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
        messages = self.cacher.read_all()

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

            messages.append(
                {
                    'role': 'user',
                    'content': [
                        {'type': 'text', 'text': command},  # type: ignore
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
