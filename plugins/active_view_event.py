from __future__ import annotations

import logging
from typing import List

import sublime
from llm_runner import AssistantSettings  # type: ignore
from sublime import View
from sublime_plugin import EventListener

from .load_model import get_model_or_default
from .ass_base import get_marked_sheets
from .status_bar import StatusBarMode

logger = logging.getLogger(__name__)


class ActiveViewEventListener(EventListener):
    def on_activated(self, view: View):
        if view.sheet().id() == 0:
            return

        settings = sublime.load_settings('ass.sublime-settings')

        logger.debug('view: %s', view)
        logger.debug('sheet: %s', view.sheet())
        assistant = get_model_or_default(view)

        status_hint_options: List[str] = settings.get('status_hint', []) if settings else []  # type: ignore

        logger.debug('status_hint_options: %s', status_hint_options)

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
        for key in ['name', 'output_mode', 'chat_model', 'sheets']:
            lookup_key = key if key != 'name' else 'name_'
            if StatusBarMode[lookup_key].value in status_hint_options:
                if key == 'chat_model':
                    statuses.append(assistant.chat_model.title())
                if key == 'output_mode':
                    statuses.append(str(assistant.output_mode).title().split('.')[1])
                if key == 'name':
                    statuses.append(assistant.name.title())
                if key == 'sheets':
                    sheets = get_marked_sheets(view.window() or sublime.active_window())
                    statuses.append(f'{len(sheets)}')

        if statuses:
            status = f'[{" | ".join(statuses)}]'
            view.set_status('ass_assistant_settings', status)
