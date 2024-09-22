from __future__ import annotations

import logging

import mdpopups
from sublime import Phantom, PhantomLayout, PhantomSet, View, set_clipboard

VIEW_SETTINGS_KEY_OPENAI_TEXT = 'VIEW_SETTINGS_KEY_OPENAI_TEXT'
OPENAI_COMPLETION_KEY = 'openai_completion'
PHANTOM_TEMPLATE = (
    '---\n'
    + 'allow_code_wrap: true\n'
    + '---\n\n'
    + '<a href="close">[x]</a> | <a href="copy">Copy</a>\n\n{streaming_content}'
)
CLASS_NAME = 'openai-completion-phantom'

logger = logging.getLogger(__name__)


class PhantomStreamer:
    def __init__(self, view: View) -> None:
        self.view = view
        self.phantom_set = PhantomSet(self.view, OPENAI_COMPLETION_KEY)
        self.completion: str = ''
        self.phantom: Phantom | None = None
        self.phantom_id: int | None = None
        self.global_state: int = 0

    def update_completion(self, completion: str):
        line_beginning = self.view.line(self.view.sel()[0])
        self.completion += completion
        self.global_state = self.global_state + 1 if self.global_state <= 100 else 0

        if self.global_state % 5 == 0:
            content = PHANTOM_TEMPLATE.format(streaming_content=self.completion)
            html = mdpopups._create_html(self.view, content, wrapper_class=CLASS_NAME)

            phantom = (
                self.phantom
                if self.phantom
                else Phantom(line_beginning, html, PhantomLayout.BLOCK, self.close_phantom)
            )

            self.phantom_set.update([phantom])

    def close_phantom(self, attribute):
        if attribute == 'copy':
            set_clipboard(self.completion)
        self.phantom_set.update([])
        self.view.settings().set(VIEW_SETTINGS_KEY_OPENAI_TEXT, False)
