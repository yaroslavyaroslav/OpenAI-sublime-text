from __future__ import annotations

import logging
import re

import sublime
import sublime_plugin

logger = logging.getLogger(__name__)


code_pattern = r'^```(?:\w+)?\s*\n(.*?)```'


class AiFrameViewEventListenerCommand(sublime_plugin.ViewEventListener):
    @classmethod
    def is_applicable(cls, settings: sublime.Settings) -> bool:
        is_available = settings.get('sheet_name') == 'AI Chat'
        logger.debug(f'is_available: {is_available}')
        return is_available

    def on_hover(self, hover_point, hover_zone):
        window = self.view.window()
        logger.debug('on_hover triggered')
        if not window:
            return
        line_region = self.view.line(hover_point)
        almoust_full_content = self.view.substr(sublime.Region(line_region.end(), self.view.size()))
        code_match = re.search(code_pattern, almoust_full_content, re.DOTALL | re.MULTILINE)
        logger.debug('code_match: %s', code_match)
        if code_match:
            code = code_match.group(1)
            logger.debug('code: %s', code)
            self.code = code
            self.view.show_popup(
                content="""
                <a href="{fuck}">   Copy   </a>
                """,
                flags=sublime.PopupFlags.HIDE_ON_MOUSE_MOVE_AWAY,
                location=hover_point,
                on_navigate=self.test_func,
                # max_width=800,
            )

    def test_func(self, content: str):
        logger.debug('running')
        sublime.set_clipboard(self.code)
