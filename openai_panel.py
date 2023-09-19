from .assistant_settings import AssistantSettings, DEFAULT_ASSISTANT_SETTINGS
import sublime
import logging
from sublime import View, Region
from sublime_plugin import WindowCommand
import functools
from enum import Enum
from typing import Optional

class OpenaiPanelCommand(WindowCommand):
    def __init__(self, window):
        super().__init__(window)
        self.settings = sublime.load_settings("openAI.sublime-settings")
        self.assistants = [
            # Unpacking both dictionaries, combine them while overwriting default values with user setup and then initialize
            # with a complete dict AssistantSettings struct.
            AssistantSettings(**{**DEFAULT_ASSISTANT_SETTINGS, **assistant}) for assistant in self.settings.get('assistants')
        ]

    def on_input(self, region: Optional[Region], text: Optional[str], view: View, mode: str, assistant: AssistantSettings, input: str):
        from .openai_worker import OpenAIWorker # https://stackoverflow.com/a/52927102

        worker_thread = OpenAIWorker(region, text, view, mode=mode, command=input, assistant=assistant)
        worker_thread.start()

    def run(self):
        self.window.show_quick_panel([f"{assistant.name} | {assistant.prompt_mode}" for assistant in self.assistants], self.on_done)

    def on_done(self, index: int):
        if index == -1: return

        region: Optional[Region] = None
        text: Optional[str] = None
        for region in self.window.active_view().sel():
            if not region.empty():
                text = self.window.active_view().substr(region)
        try:
            if region and len(region) <= self.settings.get("minimum_selection_length"):
                raise AssertionError("Not enough text selected to complete the request, please expand the selection.")
        except Exception as ex:
            sublime.error_message("Exception\n" + str(ex))
            logging.exception("Exception: " + str(ex))
            return

        sublime.active_window().show_input_panel(
            "Question: ",
             "",
             functools.partial(
                self.on_input,
                region if region is not None else None,
                text if text is not None else None,
                self.window.active_view(),
                CommandMode.chat_completion.value,
                self.assistants[index]
            ),
            None,
            None
       )

class CommandMode(Enum):
    refresh_output_panel = "refresh_output_panel"
    reset_chat_history = "reset_chat_history"
    chat_completion = "chat_completion"