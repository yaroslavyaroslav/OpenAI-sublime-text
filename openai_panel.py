from .assistant_settings import AssistantSettings, DEFAULT_ASSISTANT_SETTINGS
import sublime
from sublime import View, Region
from sublime_plugin import WindowCommand
from .errors.OpenAIException import WrongUserInputException, present_error
import functools
from enum import Enum
from typing import Optional
from .cacher import Cacher
from .openai_worker import OpenAIWorker
from threading import Event

class OpenaiPanelCommand(WindowCommand):
    stop_event: Event = Event()
    worker_thread: Optional[OpenAIWorker] = None

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

        OpenaiPanelCommand.stop_worker()  # Stop any existing worker before starting a new one
        OpenaiPanelCommand.stop_event.clear()

        OpenaiPanelCommand.worker_thread = OpenAIWorker(stop_event=self.stop_event, region=region, text=text, view=view, mode=mode, command=input, assistant=assistant)
        OpenaiPanelCommand.worker_thread.start()

    def run(self):
        self.window.show_quick_panel([f"{assistant.name} | {assistant.prompt_mode} | {assistant.chat_model}" for assistant in self.assistants], self.on_done)

    def on_done(self, index: int):
        if index == -1: return

        assistant = self.assistants[index]

        Cacher().save_model(assistant.__dict__)

        region: Optional[Region] = None
        text: Optional[str] = None
        min_selection = self.settings.get("minimum_selection_length")
        for region in self.window.active_view().sel():
            if not region.empty():
                text = self.window.active_view().substr(region)
        try:
            ## If none text selected — it's ok, pass that through.
            if region and len(region) <= min_selection:
                raise WrongUserInputException(f"You've selected just {len(region)} chars, while the minimal selection number is {min_selection}. Please expand the selection.")
        except WrongUserInputException as error:
            present_error(title="OpenAI error", error=error)
            return

        sublime.active_window().show_input_panel(
            "Question: ",
             "",
             functools.partial(
                self.on_input,
                region if region else None,
                text if text else None,
                self.window.active_view(),
                CommandMode.chat_completion.value,
                assistant
            ),
            None,
            None
       )

    @classmethod
    def stop_worker(cls):
        if cls.worker_thread and cls.worker_thread.is_alive():
            cls.stop_event.set()  # Signal the thread to stop
            cls.worker_thread = None

class CommandMode(Enum):
    refresh_output_panel = "refresh_output_panel"
    reset_chat_history = "reset_chat_history"
    chat_completion = "chat_completion"
