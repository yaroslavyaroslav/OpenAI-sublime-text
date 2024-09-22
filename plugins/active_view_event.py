from __future__ import annotations

import logging
from typing import Any, Dict, List

import sublime
from sublime import View
from sublime_plugin import EventListener

from .cacher import Cacher
from .status_bar import StatusBarMode

logger = logging.getLogger(__name__)


class ActiveViewEventListener(EventListener):
    cacher = None

    def on_activated(self, view: View):
        ## FIXME: This is might be wrong, settings of view should be get not for an active view, but for a given window project view.
        ## It could be correct btw, as if a window with a specific settings gets active — it updated exact it status bar.
        self.project_settings: Dict[str, str] | None = (
            sublime.active_window().active_view().settings().get('ai_assistant')
        )  # type: ignore

        # Logging disabled becuase it's too spammy. Uncomment in case of necessity.
        # logger.debug(
        #     "project_settings exists: %s", "YES" if self.project_settings else "NO"
        # )

        cache_prefix = self.project_settings.get('cache_prefix') if self.project_settings else None

        # Initialize Cacher with proper default handling for missing cache_prefix
        self.cacher = Cacher(name=cache_prefix)

        # logger.debug("cacher.history_file: %s", self.cacher.history_file)
        # logger.debug("cacher.current_model_file: %s", self.cacher.current_model_file)
        # logger.debug("cacher.tokens_count_file: %s", self.cacher.tokens_count_file)

        # Reading the assistant model from cache
        assistant = self.cacher.read_model()

        # logger.debug("assistant: %s", assistant)

        settings = sublime.load_settings('openAI.sublime-settings')

        status_hint_options: List[str] = settings.get('status_hint', []) if settings else []  # type: ignore

        # logger.debug("status_hint_options: %s", status_hint_options)

        # Update status bar with potentially retrieved model
        self.update_status_bar(view, assistant, status_hint_options)

    def update_status_bar(
        self,
        view: View,
        assistant: Dict[str, Any] | None,
        status_hint_options: List[str],
    ):
        if not assistant:
            return

        if not status_hint_options:
            return

        # Check necessary keys in assistant
        if {'name', 'prompt_mode', 'chat_model'} <= assistant.keys():
            statuses: List[str] = []
            for key in ['name', 'prompt_mode', 'chat_model']:
                lookup_key = key if key != 'name' else 'name_'  # name is a reserved keyword
                if StatusBarMode[lookup_key].value in status_hint_options:
                    if key == 'chat_model':
                        statuses.append(assistant[key].upper())
                    else:
                        statuses.append(assistant[key].title())

            if statuses:
                status = f'[{" | ".join(statuses)}]'
                view.set_status('openai_assistant_settings', status)
