from __future__ import annotations

import logging
from typing import List

import sublime
from rust_helper import AssistantSettings  # type: ignore
from sublime import View
from sublime_plugin import EventListener

from .load_model import get_model_or_default
from .status_bar import StatusBarMode

logger = logging.getLogger(__name__)


class ActiveViewEventListener(EventListener):
    def on_activated(self, view: View):
        settings = sublime.load_settings('openAI.sublime-settings')

        assistant = get_model_or_default(view)

        # logger.debug("assistant: %s", assistant)

        status_hint_options: List[str] = settings.get('status_hint', []) if settings else []  # type: ignore

        # logger.debug("status_hint_options: %s", status_hint_options)

        self.update_status_bar(view, assistant, status_hint_options)

    def update_status_bar(
        self,
        view: View,
        assistant: AssistantSettings | None,
        status_hint_options: List[str],
    ):
        if not assistant:
            return

        if not status_hint_options:
            return

        statuses: List[str] = []
        for key in ['name', 'prompt_mode', 'chat_model']:
            lookup_key = key if key != 'name' else 'name_'
            if StatusBarMode[lookup_key].value in status_hint_options:
                if key == 'chat_model':
                    statuses.append(assistant.chat_model.upper())
                # FIXME: Prompt_mode is not a string, so it's failing to print.
                # if key == 'prompt_mode':
                #     statuses.append(assistant.output_mode.title())
                if key == 'name':
                    statuses.append(assistant.name.title())

        if statuses:
            status = f'[{" | ".join(statuses)}]'
            view.set_status('openai_assistant_settings', status)
