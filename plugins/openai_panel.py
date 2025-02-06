from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

import sublime
from llm_runner import AssistantSettings, write_model  # type: ignore
from sublime import Settings, Window
from sublime_plugin import WindowCommand, ListInputHandler
from sublime_types import Value

from .load_model import get_cache_path
from .openai_base import CommonMethods, get_marked_sheets

logger = logging.getLogger(__name__)


class OpenaiPanelCommand(WindowCommand):
    def __init__(self, window: Window):
        super().__init__(window)
        self.settings: Settings = sublime.load_settings('openAI.sublime-settings')

        self.load_assistants()
        self.window = window

        self.settings.add_on_change('reload_assistants', self.load_assistants)

    def load_assistants(self):
        assistants: List[Dict[str, Any]] = self.settings.get('assistants', [])  # type: ignore
        self.assistants: List[AssistantSettings] = [AssistantSettings(assistant) for assistant in assistants]

    def run(self, model: Dict[str, Any] | None = None, output_mode: str | None = None, **kwargs):
        self.kwargs = kwargs
        logger.debug('Running')
        logger.debug('active_view: %s', self.window.active_view())
        logger.debug('active_sheet: %s', self.window.active_sheet().view())
        if model and output_mode:
            view = self.window.active_view()
            model['output_mode'] = output_mode
            assistant = AssistantSettings(model)
            path = get_cache_path(self.window.active_view())
            write_model(path, assistant)

            CommonMethods.process_openai_command(
                view,
                assistant,
                self.kwargs,
            )
        else:
            self.window.show_quick_panel(
                [
                    f'{assistant.name} | {assistant.output_mode} | {assistant.chat_model}'
                    for assistant in self.assistants
                ],
                self.on_done,
            )

    def input(self, args):
        return AIWholeInputHandler(self.window, ['model', 'output_mode'])

    def on_done(self, index: int):
        if index == -1:
            return

        assistant = self.assistants[index]

        assistant.token = assistant.token if assistant.token else self.settings.get('token', None)
        logger.debug('Openai window: %s', self.window)

        view = self.window.active_view()

        logger.debug('Openai window.active_view(): %s', view)
        path = get_cache_path(view)

        logger.debug('path: %s', path)

        write_model(path, assistant)

        CommonMethods.process_openai_command(
            view,  # type: ignore
            assistant,
            self.kwargs,
        )

    def __del__(self):
        # Make sure to remove the settings change callback when the object is deleted
        if self.settings:
            self.settings.clear_on_change('reload_assistants')


class AIWholeInputHandler(ListInputHandler):
    def __init__(self, window: Window, names: List[str]) -> None:
        self._name, *self.next_names = names
        self.window = window
        self.settings: Settings = sublime.load_settings('openAI.sublime-settings')
        self.assistants: List[Dict[str, Any]] = self.settings.get('assistants', [])  # type: ignore
        self.output_modes = ['view', 'phantom']

    def name(self):
        return self._name

    def placeholder(self):
        return self._name

    def description(self, v, text: str) -> str:
        return text

    def preview(self, text: str) -> str | sublime.Html:
        sheets = get_marked_sheets(self.window)

        return f'{len(sheets)} file(s) added: {str([sheet.view().file_name() for sheet in sheets])}'

    def list_items(self) -> List[Tuple[str, Value]]:
        logger.debug('list_items _name: %s', self._name)
        if self._name == 'model':
            return [(assistant['name'], assistant) for assistant in self.assistants]
        elif self._name == 'output_mode':
            return [(value, value) for value in self.output_modes]

        return [('', None)]

    def next_input(self, args):
        if self.next_names:
            return AIWholeInputHandler(self.window, self.next_names)
