from __future__ import annotations

from typing import Dict

from sublime import Window
from sublime_plugin import ViewEventListener


# class AIChatViewEventListener(ViewEventListener):
#     @classmethod
#     def is_applicable(cls, settings) -> bool:
#         return (
#             settings.get('syntax') == 'Packages/Markdown/MultiMarkdown.sublime-syntax'
#             or settings.get('syntax') == 'Packages/Markdown/PlainText.sublime-syntax'
#         )

#     def on_activated(self) -> None:
#         self.update_status_message(self.view.window())  # type: ignore

#     def update_status_message(self, window: Window) -> None:

#         # cache_prefix = get_cache_path(window.active_view())

#         # cacher = Cacher(name=cache_prefix)
#         # if self.is_ai_chat_tab_active(window):
#         #     status_message = self.get_status_message(cacher=cacher)
#         #     active_view = window.active_view()
#         #     if active_view and active_view.name() == 'AI Chat':
#         #         active_view.set_status('ai_chat_status', status_message)

#     def is_ai_chat_tab_active(self, window: Window) -> bool:
#         active_view = window.active_view()
#         return active_view.name() == 'AI Chat' if active_view else False

#     def get_status_message(self, cacher: Cacher) -> str:
#         prompt, completion = cacher.read_tokens_count()
#         return f'[⬆️: {prompt:,} + ⬇️: {completion:,} = {prompt + completion:,}]'
