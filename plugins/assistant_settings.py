from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class PromptMode(Enum):
    panel = 'panel'
    append = 'append'
    insert = 'insert'
    replace = 'replace'
    phantom = 'phantom'


@dataclass
class Function:
    name: str
    arguments: Dict[str, Union[str, int, bool, Dict[str, int]]]


@dataclass
class ToolCall:
    index: int
    id: str
    type: str
    function: Function


@dataclass
class AssistantResponse:
    role: str
    content: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)
    refusal: Optional[str] = None
    logprobs: Optional[str] = None
    finish_reason: Optional[str] = None


@dataclass
class AssistantSettings:
    name: str
    prompt_mode: PromptMode
    url: str | None
    token: str | None
    chat_model: str
    assistant_role: str | None
    temperature: int | None
    max_tokens: int | None
    max_completion_tokens: int | None
    top_p: int | None
    frequency_penalty: int | None
    presence_penalty: int | None
    placeholder: str | None
    tools: bool
    parallel_tool_calls: bool
    stream: bool
    advertisement: bool


DEFAULT_ASSISTANT_SETTINGS: Dict[str, Any] = {
    'placeholder': None,
    'assistant_role': None,
    'url': None,
    'token': None,
    'temperature': None,
    'max_tokens': None,
    'max_completion_tokens': None,
    'top_p': None,
    'frequency_penalty': None,
    'presence_penalty': None,
    'tools': False,
    'parallel_tool_calls': False,
    'stream': True,
    'advertisement': True,
}


class CommandMode(Enum):
    handle_image_input = 'handle_image_input'
    refresh_output_panel = 'refresh_output_panel'
    create_new_tab = 'create_new_tab'
    reset_chat_history = 'reset_chat_history'
