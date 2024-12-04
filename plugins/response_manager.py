from __future__ import annotations

from typing import Any, Dict, List

from sublime import Window

from .assistant_settings import PromptMode
from .output_panel import SharedOutputPanelListener
from .phantom_streamer import PhantomStreamer


class ResponseManager:
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

    @staticmethod
    def handle_whole_response(
        listner: SharedOutputPanelListener | PhantomStreamer,
        user_input: List[Dict[str, Any]] | List[Dict[str, str]],
        window: Window,
        prompt_mode: PromptMode,
        content: Dict[str, Any],
    ):
        if prompt_mode == PromptMode.panel.name and type(listner) is SharedOutputPanelListener:
            if 'content' in content:
                ResponseManager.update_output_panel_(listner, window, content['content'])
        elif prompt_mode == PromptMode.phantom.name and type(listner) is PhantomStreamer:
            if 'content' in content:
                listner.update_completion(user_input, content['content'])

    @staticmethod
    def handle_sse_delta(
        listner: SharedOutputPanelListener | PhantomStreamer,
        user_input: List[Dict[str, Any]] | List[Dict[str, str]],
        window: Window,
        prompt_mode: PromptMode,
        delta: Dict[str, Any],
        full_response_content: Dict[str, str],
    ):
        if prompt_mode == PromptMode.panel.name and type(listner) is SharedOutputPanelListener:
            if 'role' in delta:
                full_response_content['role'] = delta['role']
            if 'content' in delta:
                full_response_content['content'] += delta['content']
                ResponseManager.update_output_panel_(listner, window, delta['content'])
        elif prompt_mode == PromptMode.phantom.name and type(listner) is PhantomStreamer:
            if 'content' in delta:
                listner.update_completion(user_input, delta['content'])
