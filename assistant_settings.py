from dataclasses import dataclass
from enum import Enum
from typing import Optional

class PromptMode(Enum):
    panel = "panel"
    append = "append"
    insert = "insert"
    replace = "replace"

@dataclass
class AssistantSettings():
    name: str
    prompt_mode: PromptMode
    url: Optional[str]
    token: Optional[str]
    chat_model: str
    assistant_role: str
    temperature: int
    max_tokens: int
    top_p: int
    frequency_penalty: int
    presence_penalty: int
    placeholder: Optional[str]

DEFAULT_ASSISTANT_SETTINGS = {
    "placeholder": None,
    "url": None,
    "token": None,
    "temperature": 1,
    "max_tokens": 2048,
    "top_p": 1,
    "frequency_penalty": 0,
    "presence_penalty": 0,
}

class CommandMode(Enum):
    handle_image_input = "handle_image_input"
    refresh_output_panel = "refresh_output_panel"
    create_new_tab = "create_new_tab"
    reset_chat_history = "reset_chat_history"
    chat_completion = "chat_completion"
