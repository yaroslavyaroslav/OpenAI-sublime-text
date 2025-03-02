from __future__ import annotations

from typing import List

from llm_runner import InputKind, SublimeInputContent  # type: ignore
from sublime import Window

from .output_panel import SharedOutputPanelListener


class ResponseManager:
    @staticmethod
    def print_requests(
        listner: SharedOutputPanelListener,
        window: Window,
        content: List[SublimeInputContent],
    ):
        for item in content:
            if item.path:
                if item.input_kind == InputKind.ViewSelection:
                    ResponseManager.update_output_panel_(listner, window, '\n\n## Selection\n\n')
                    ResponseManager.update_output_panel_(listner, window, f'Path: `{item.path}`')
                    ResponseManager.update_output_panel_(listner, window, '\n')
                elif item.input_kind == InputKind.Sheet:
                    continue
            else:
                ResponseManager.update_output_panel_(listner, window, '\n\n## Question\n\n')

            ResponseManager.update_output_panel_(listner, window, item.content)

    @staticmethod
    def prepare_to_response(
        listner: SharedOutputPanelListener,
        window: Window,
    ):
        ResponseManager.update_output_panel_(listner, window, '\n\n## Answer\n\n')
        listner.show_panel(window=window)
        listner.scroll_to_botton(window=window)

    @staticmethod
    def update_output_panel_(listner: SharedOutputPanelListener, window: Window, text_chunk: str):
        listner.update_output_view(text=text_chunk, window=window)
