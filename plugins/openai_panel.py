from __future__ import annotations

import logging
from typing import Any, Dict, List

from .load_model import get_cache_path
import sublime
from rust_helper import AssistantSettings, write_model  # type: ignore
from sublime import Settings, Window
from sublime_plugin import WindowCommand

from .openai_base import CommonMethods

logger = logging.getLogger(__name__)


class OpenaiPanelCommand(WindowCommand):
    def __init__(self, window: Window):
        super().__init__(window)
        self.settings: Settings = sublime.load_settings('openAI.sublime-settings')
        self.project_settings: Dict[str, str] | None = (
            sublime.active_window().active_view().settings().get('ai_assistant')
        )  # type: ignore

        self.load_assistants()
        self.window = window

        self.settings.add_on_change('reload_assistants', self.load_assistants)

    def load_assistants(self):
        assistants: List[Dict[str, Any]] = self.settings.get('assistants', [])  # type: ignore
        self.assistants: List[AssistantSettings] = [AssistantSettings(assistant) for assistant in assistants]

    def run(self, **kwargs):
        self.kwargs = kwargs
        logger.debug('Running')
        self.window.show_quick_panel(
            [
                f'{assistant.name} | {assistant.output_mode} | {assistant.chat_model}'
                for assistant in self.assistants
            ],
            self.on_done,
        )

    def on_done(self, index: int):
        if index == -1:
            return

        assistant = self.assistants[index]

        assistant.token = assistant.token if assistant.token else self.settings.get('token', None)

        path = get_cache_path(self.window.active_view())

        logger.debug('path: %s', path)

        write_model(path, assistant)

        CommonMethods.process_openai_command(
            self.window.active_view(),  # type: ignore
            assistant,
            self.kwargs,
        )

    def __del__(self):
        # Make sure to remove the settings change callback when the object is deleted
        if self.settings:
            self.settings.clear_on_change('reload_assistants')
