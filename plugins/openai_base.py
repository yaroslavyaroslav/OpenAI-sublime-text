from __future__ import annotations

import logging
from typing import Any, Dict, List

import sublime
from llm_runner import (
    AssistantSettings,  # type: ignore
    InputKind,  # type: ignore
    PromptMode,  # type: ignore
    SublimeInputContent,  # type: ignore
    Worker,  # type: ignore
)
from sublime import Region, Settings, View, Window, active_window

from .assistant_settings import (
    CommandMode,
)
from .buffer import BufferContentManager
from .errors.OpenAIException import WrongUserInputException, present_error, present_error_str
from .image_handler import ImageValidator
from .load_model import get_cache_path, get_model_or_default
from .output_panel import SharedOutputPanelListener
from .phantom_streamer import PhantomStreamer
from .response_manager import ResponseManager
from .sheet_toggle import VIEW_TOGGLE_KEY

logger = logging.getLogger(__name__)


class CommonMethods:
    worker: Worker | None = None

    @classmethod
    def process_openai_command(cls, view: View, assistant: AssistantSettings | None, kwargs: Dict[str, Any]):
        logger.debug('Openai started')
        plugin_loaded()
        mode = kwargs.pop('mode', 'chat_completion')

        region: Region | None = None

        items = get_sheets_context(window=view.window() or active_window())

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

        if some_text:
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

        logger.debug('assistant: %s', assistant)
        logger.debug('view: %s', view)
        logger.debug('view.window(): %s', view.window())

        combined_assistant = assistant or get_model_or_default(view)
        logger.debug('combined_assistant: %s', combined_assistant)

        if combined_assistant.url is None:
            combined_assistant.url = settings.get('url', None)
        if combined_assistant.token is None:
            combined_assistant.token = settings.get('token', None)

        if mode == CommandMode.handle_image_input.value:
            cls.handle_image_input(
                view,
                combined_assistant,
                items,
            )
        else:
            cls.handle_chat_completion(
                view,
                combined_assistant,
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
        path = get_cache_path(view)

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
            else ViewCapture(view).tab_handler
        )

        cls.worker.run(
            view.id(),
            assistant.output_mode,
            inputs,
            assistant,
            handler,
            ErrorCapture.error_handler,
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

    @classmethod
    def is_worker_alive(cls) -> bool:
        logger.debug('Stopping worker...')
        return cls.worker.is_alive()


settings: Settings | None = None


def get_sheets_context(window: Window) -> List[SublimeInputContent]:
    sheets = []
    for view in window.views():
        if view and view.settings().get(VIEW_TOGGLE_KEY, False):
            sheets.append(view.sheet())
    return BufferContentManager.wrap_sheet_contents_with_scope(sheets)


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


class ErrorCapture:
    @staticmethod
    def error_handler(content: str) -> None:
        present_error_str('OpenAI Error', content)


class ViewCapture:
    def __init__(self, view: View) -> None:
        self.view = view

    def tab_handler(self, content: str) -> None:
        window: Window = self.view.window()  # type: ignore

        listner = SharedOutputPanelListener()

        ResponseManager.update_output_panel_(listner, window, content)

        logger.debug('Received data: %s', content)


class PhantomCapture:
    def __init__(self, view: View, user_input: List[SublimeInputContent]) -> None:
        self.phantom = PhantomStreamer(view, user_input)

    def phantom_handler(self, content: str) -> None:
        self.phantom.update_completion(content)

        logger.debug('Received data: %s', content)
