from .openai_base import CommonMethods
from .assistant_settings import AssistantSettings, DEFAULT_ASSISTANT_SETTINGS
import sublime
from sublime import Settings, Window
from sublime_plugin import WindowCommand
from typing import Optional, List
from .cacher import Cacher
from .openai_worker import OpenAIWorker
from threading import Event
import logging

logger = logging.getLogger(__name__)


class OpenaiPanelCommand(WindowCommand):
    stop_event: Event = Event()
    worker_thread: Optional[OpenAIWorker] = None
    cache_prefix = None
    files_included = False

    def __init__(self, window: Window):
        super().__init__(window)
        self.settings: Settings = sublime.load_settings('openAI.sublime-settings')
        self.project_settings = (
            self.window.active_view().settings().get('ai_assistant', None)
        )

        self.cacher = (
            Cacher(name=self.project_settings['cache_prefix'])
            if self.project_settings
            else Cacher()
        )
        # Load assistants from settings
        self.load_assistants()

        # Register a callback to reload assistants when settings change
        self.settings.add_on_change('reload_assistants', self.load_assistants)

    def load_assistants(self):
        self.assistants: List[AssistantSettings] = [
            AssistantSettings(**{**DEFAULT_ASSISTANT_SETTINGS, **assistant})
            for assistant in self.settings.get('assistants', [])
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
        settings = self.window.active_view().settings().get('ai_assistant', None)
        if settings and settings.get('cache_prefix', None):
            prefix = settings.get('cache_prefix', None)
            if prefix:
                self.cacher = Cacher(prefix)

    def on_done(self, index: int):
        if index == -1:
            return

        assistant = self.assistants[index]

        self.cacher.save_model(assistant.__dict__)

        CommonMethods.process_openai_command(
            self.window.active_view(), assistant, self.kwargs
        )

    def __del__(self):
        # Make sure to remove the settings change callback when the object is deleted
        if self.settings:
            self.settings.clear_on_change('reload_assistants')
