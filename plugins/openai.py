from __future__ import annotations

import logging

from rust_helper import drop_all  # type: ignore
from sublime import Edit, Region, View, active_window, cache_path, load_settings
from sublime_plugin import TextCommand

from .assistant_settings import CommandMode
from .openai_base import CommonMethods
from .output_panel import SharedOutputPanelListener

logger = logging.getLogger(__name__)


class Openai(TextCommand):
    def run(self, edit: Edit, **kwargs):
        mode = kwargs.get('mode', 'chat_completion')

        settings = load_settings('openAI.sublime-settings')

        listener = SharedOutputPanelListener(
            markdown=settings.get('markdown', False),  # type: ignore
        )

        if mode == CommandMode.reset_chat_history.value:
            Openai.reset_chat_history(self.view, listener, edit)
        elif mode == CommandMode.create_new_tab.value:
            Openai.create_new_tab(listener)
        elif mode == CommandMode.refresh_output_panel.value:
            Openai.refresh_output_panel(listener)
        else:
            logger.debug('Openai view: %s', self.view)
            CommonMethods.process_openai_command(self.view, None, kwargs)

    @classmethod
    def reset_chat_history(cls, view: View, listener: SharedOutputPanelListener, edit: Edit):
        window = active_window()

        path = view.settings().get('ai_assistant', cache_path()).get('cache_prefix', cache_path())

        drop_all(path)
        view = listener.get_output_view_(window=window)
        view.set_read_only(False)
        region = Region(0, view.size())
        view.erase(edit, region)
        view.set_read_only(True)

    @classmethod
    def create_new_tab(cls, listener: SharedOutputPanelListener):
        window = active_window()
        listener.create_new_tab(window)
        listener.refresh_output_panel(window=window)

    @classmethod
    def refresh_output_panel(cls, listener: SharedOutputPanelListener):
        window = active_window()
        listener.refresh_output_panel(window=window)
        listener.show_panel(window=window)
