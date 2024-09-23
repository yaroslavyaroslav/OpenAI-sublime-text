from __future__ import annotations

import logging
from typing import Dict

import sublime
from sublime import Edit, Region, View
from sublime_plugin import TextCommand

from .assistant_settings import CommandMode
from .cacher import Cacher
from .openai_base import CommonMethods
from .output_panel import SharedOutputPanelListener

logger = logging.getLogger(__name__)


class Openai(TextCommand):
    cacher = None

    def run(self, edit: Edit, **kwargs):
        mode = kwargs.get('mode', 'chat_completion')

        self.project_settings: Dict[str, str] | None = (
            sublime.active_window().active_view().settings().get('ai_assistant')
        )  # type: ignore

        cache_prefix = self.project_settings.get('cache_prefix') if self.project_settings else None

        settings = sublime.load_settings('openAI.sublime-settings')

        listener = SharedOutputPanelListener(
            markdown=settings.get('markdown', False),  # type: ignore
            cacher=Cacher(name=cache_prefix),
        )

        if mode == CommandMode.reset_chat_history.value:
            Openai.reset_chat_history(self.view, listener, edit)
        elif mode == CommandMode.create_new_tab.value:
            Openai.create_new_tab(listener)
        elif mode == CommandMode.refresh_output_panel.value:
            Openai.refresh_output_panel(listener)
        else:
            CommonMethods.process_openai_command(self.view, None, kwargs)

    # TODO: This is temporary solution, this method should be moved to a more proper place
    @classmethod
    def reset_chat_history(cls, view: View, listener: SharedOutputPanelListener, edit: Edit):
        listener.cacher.drop_all()
        listener.cacher.reset_tokens_count()
        window = sublime.active_window()
        view = listener.get_output_view_(window=window)
        view.set_read_only(False)
        region = Region(0, view.size())
        view.erase(edit, region)
        view.set_read_only(True)

    @classmethod
    def create_new_tab(cls, listener: SharedOutputPanelListener):
        window = sublime.active_window()
        listener.create_new_tab(window)
        listener.refresh_output_panel(window=window)

    @classmethod
    def refresh_output_panel(cls, listener: SharedOutputPanelListener):
        window = sublime.active_window()
        listener.refresh_output_panel(window=window)
        listener.show_panel(window=window)
