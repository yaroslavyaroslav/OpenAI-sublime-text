from __future__ import annotations

import logging
from typing import Any, Dict, List

import sublime
from rust_helper import (
    AssistantSettings,  # type: ignore
    InputKind,  # type: ignore
    PromptMode,  # type: ignore
    SublimeInputContent,  # type: ignore
    Worker,  # type: ignore
)
from sublime import Region, Settings, Sheet, View, Window, active_window

from .assistant_settings import (
    CommandMode,
)

from .buffer import BufferContentManager
from .errors.OpenAIException import WrongUserInputException, present_error
from .image_handler import ImageValidator
from .output_panel import SharedOutputPanelListener
from .phantom_streamer import PhantomStreamer
from .response_manager import ResponseManager

logger = logging.getLogger(__name__)


class CommonMethods:
    worker: Worker | None = None

    @classmethod
    def process_openai_command(cls, view: View, assistant: AssistantSettings | None, kwargs: Dict[str, Any]):
        logger.debug('Openai started')
        plugin_loaded()
        mode = kwargs.pop('mode', 'chat_completion')
        files_included = kwargs.get('files_included', False)

        region: Region | None = None

        items = []

        logger.debug('mode: %s', mode)
        logger.debug('Region: %s', region)
        build_input = kwargs.pop('build_output', False)
        lsp_diagnostics = kwargs.pop('lsp_diagnostics', False)
        logger.debug(f'build_input {build_input}')
        logger.debug(f'lsp_diagnostics {lsp_diagnostics}')
        if lsp_diagnostics:
            output_limit: int = settings.get('build_output_limit', 100)  # type: ignore
            lsp_text = CommonMethods.get_output_lines('diagnostics', output_limit)
            items.append(InputCompositor.compose_input(InputKind.LspOutputPanel, lsp_text))
        if build_input and settings:
            output_limit: int = settings.get('build_output_limit', 100)  # type: ignore
            build_text = CommonMethods.get_output_lines('exec', output_limit)
            items.append(InputCompositor.compose_input(InputKind.BuildOutputPanel, build_text))

        some_text = ''
        for region in view.sel():
            if not region.empty():
                some_text += view.substr(region) + '\n'

        items.append(InputCompositor.compose_input(InputKind.ViewSelection, some_text, view))

        try:
            minimum_selection_length: int | None = settings.get('minimum_selection_length')  # type: ignore
            if region and minimum_selection_length and len(region) < minimum_selection_length:
                raise WrongUserInputException(
                    'Not enough text selected to complete the request, please expand the selection.'
                )
        except WrongUserInputException as error:
            present_error(title='OpenAI error', error=error)
            return

        logger.debug('AssistantSettings: %s', assistant)
        logger.debug('view: %s', view)
        logger.debug('view.window(): %s', view.window())

        first_assistant: Dict[str, Any] = settings.get('assistants', None)[0]

        default_assistant = AssistantSettings(first_assistant)
        if default_assistant.url is None:
            default_assistant.url = settings.get('url', None)
        if default_assistant.token is None:
            default_assistant.token = settings.get('token', None)

        if mode == CommandMode.handle_image_input.value:
            cls.handle_image_input(
                view,
                assistant or default_assistant,
                items,
            )
        else:
            cls.handle_chat_completion(
                view,
                assistant or default_assistant,
                items,
            )

    @classmethod
    def get_output_lines(cls, view_name: str, limit: int) -> str:
        output_view = sublime.active_window().find_output_panel(view_name)
        if output_view:
            content = output_view.substr(sublime.Region(0, output_view.size()))
            lines = content.splitlines()
            if limit == -1:
                return '\n'.join(lines)
            return '\n'.join(lines[-limit:])
        return ''

    @classmethod
    def handle_image_input(
        cls,
        view: View,
        assistant: AssistantSettings | None,
        inputs: List[SublimeInputContent],
    ):
        # FIXME: Image don't work in the new flow
        valid_input = ImageValidator.get_valid_image_input('text')
        window = view.window() or sublime.active_window()
        logger.debug('handle_image_input hit')
        sublime.active_window().show_input_panel(
            'Command for Image: ',
            window.settings().get('OPENAI_INPUT_TMP_STORAGE') or '',  # type: ignore
            lambda user_input: cls.handle_input(
                user_input,
                view,
                assistant,
                inputs,
            ),
            lambda user_input: cls.save_input(user_input, window),
            lambda: cls.save_input('', window),
        )

    @classmethod
    def handle_chat_completion(
        cls,
        view: View,
        assistant: AssistantSettings | None,
        inputs: List[SublimeInputContent],
    ):
        window = view.window() or sublime.active_window()
        logger.debug('handle_chat_completion hit')
        sublime.active_window().show_input_panel(
            'Question:',
            window.settings().get('OPENAI_INPUT_TMP_STORAGE') or '',  # type: ignore
            lambda user_input: cls.handle_input(
                user_input,
                view,
                assistant,
                inputs,
            ),
            lambda user_input: cls.save_input(user_input, window),
            lambda: cls.save_input('', window),
        )

    @classmethod
    def save_input(cls, user_input: str, window: Window):
        logger.debug(f'user_input: {user_input}')
        window.settings().set('OPENAI_INPUT_TMP_STORAGE', user_input)

    @classmethod
    def handle_input(
        cls, input: str, view: View, assistant: AssistantSettings, user_input: List[SublimeInputContent]
    ):
        logger.debug('selections received: %s', user_input)
        logger.debug('user input received: %s', input)
        user_input.append(InputCompositor.compose_input(InputKind.Command, input))
        CommonMethods.on_input(view, assistant, user_input)

    @classmethod
    def on_input(
        cls,
        view: View,
        assistant: AssistantSettings,
        inputs: List[SublimeInputContent],
    ):
        path = sublime.cache_path()

        ai_assistant = view.settings().get(
            'ai_assistant',
            None,
        )
        if ai_assistant:
            path = ai_assistant.get(  # type: ignore
                'cache_prefix',
                sublime.cache_path(),
            )

        proxy = ''

        proxy_obj = settings.get('proxy', None)
        if proxy_obj:
            proxy = f'{proxy_obj.get("address")}:{proxy_obj.get("port")}'

        window = view.window() or active_window()
        cls.worker = Worker(
            window_id=window.id(),
            path=path,
            proxy=proxy if proxy else None,
        )

        handler = (
            PhantomCapture(view, inputs).phantom_handler
            if assistant.output_mode == PromptMode.Phantom
            else tab_handler
        )

        cls.worker.run(
            view.id(),
            assistant.output_mode,
            inputs,
            assistant,
            handler,
        )

        if assistant.output_mode == PromptMode.View:
            ResponseManager.print_requests(
                SharedOutputPanelListener(),
                window,
                inputs,
            )
            ResponseManager.prepare_to_response(
                SharedOutputPanelListener(),
                window,
            )

        logger.debug('spawned successfully')

    @classmethod
    def stop_worker(cls):
        logger.debug('Stopping worker...')
        cls.worker.cancel()


settings: Settings | None = None


class InputCompositor:
    @staticmethod
    def compose_input(
        kind: InputKind,
        content: str,
        view: View | None = None,
    ) -> SublimeInputContent:
        if kind == InputKind.ViewSelection:
            scope_region = view.scope_name(0)  # Assuming you want the scope at the start of the document
            scope_name = scope_region.split(' ')[0].split('.')[-1]
            content = BufferContentManager.wrap_content_with_scope(scope_name, content)
            return SublimeInputContent(kind, content=content, path=view.file_name(), scope=scope_name)
        else:
            return SublimeInputContent(kind, content=content)


def plugin_loaded():
    global settings
    settings = sublime.load_settings('openAI.sublime-settings')


def tab_handler(content: str) -> None:
    window = sublime.active_window()

    listner = SharedOutputPanelListener()

    ResponseManager.update_output_panel_(listner, window, content)

    print(f'Received data: {content}')


class PhantomCapture:
    def __init__(self, view: View, user_input: List[SublimeInputContent]) -> None:
        self.phantom = PhantomStreamer(view, user_input)

    def phantom_handler(self, content: str) -> None:
        self.phantom.update_completion(content)

        print(f'Received data: {content}')
