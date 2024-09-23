from __future__ import annotations

import logging
from threading import Event
from typing import Any, Dict, List

import sublime
from sublime import Settings, Window
from sublime_plugin import WindowCommand

from .assistant_settings import DEFAULT_ASSISTANT_SETTINGS, AssistantSettings
from .cacher import Cacher
from .openai_base import CommonMethods
from .openai_worker import OpenAIWorker

logger = logging.getLogger(__name__)


class OpenaiPanelCommand(WindowCommand):
    stop_event: Event = Event()
    worker_thread: OpenAIWorker | None = None
    cache_prefix = None
    files_included = False

    def __init__(self, window: Window):
        super().__init__(window)
        self.settings: Settings = sublime.load_settings('openAI.sublime-settings')
        self.project_settings: Dict[str, str] | None = (
            sublime.active_window().active_view().settings().get('ai_assistant')
        )  # type: ignore

        cache_prefix = self.project_settings.get('cache_prefix') if self.project_settings else None

        self.cacher = Cacher(name=cache_prefix)

        # Load assistants from settings
        self.load_assistants()

        # Register a callback to reload assistants when settings change
        self.settings.add_on_change('reload_assistants', self.load_assistants)

    def load_assistants(self):
        assistants: List[Dict[str, Any]] = self.settings.get('assistants', [])  # type: ignore
        self.assistants: List[AssistantSettings] = [
            AssistantSettings(**{**DEFAULT_ASSISTANT_SETTINGS, **assistant}) for assistant in assistants
        ]

    def run(self, **kwargs):
        self.kwargs = kwargs
        logger.debug('Running')
        self.window.show_quick_panel(
            [
                f'{assistant.name} | {assistant.prompt_mode} | {assistant.chat_model}'
                for assistant in self.assistants
            ],
            self.on_done,
        )
        settings: Dict[str, str] = self.window.active_view().settings().get('ai_assistant')  # type: ignore

        if settings and settings.get('cache_prefix'):
            prefix = settings.get('cache_prefix')
            if prefix:
                self.cacher = Cacher(prefix)  # noqa: E701

    def on_done(self, index: int):
        if index == -1:
            return

        assistant = self.assistants[index]

        self.cacher.save_model(assistant.__dict__)

        CommonMethods.process_openai_command(
            self.window.active_view(),  # type: ignore
            assistant,
            self.kwargs,
        )

    def __del__(self):
        # Make sure to remove the settings change callback when the object is deleted
        if self.settings:
            self.settings.clear_on_change('reload_assistants')
