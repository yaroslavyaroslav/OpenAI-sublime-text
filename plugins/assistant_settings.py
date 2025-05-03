from __future__ import annotations

from enum import Enum


class CommandMode(Enum):
    handle_image_input = 'handle_image_input'
    refresh_output_panel = 'refresh_output_panel'
    create_new_tab = 'create_new_tab'
    reset_chat_history = 'reset_chat_history'
