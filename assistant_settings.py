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
    chat_model: str
    assistant_role: str
    temperature: int
    max_tokens: int
    top_p: int
    frequency_penalty: int
    presence_penalty: int
    placeholder: Optional[str] = None

DEFAULT_ASSISTANT_SETTINGS = {
    "placeholder": None,
    "temperature": 1,
    "max_tokens": 2048,
    "top_p": 1,
    "frequency_penalty": 0,
    "presence_penalty": 0,
}
