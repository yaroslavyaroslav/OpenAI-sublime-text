from .assistant_settings import AssistantSettings, DEFAULT_ASSISTANT_SETTINGS, CommandMode
import sublime
from sublime import View, Region
from sublime_plugin import WindowCommand
from .errors.OpenAIException import WrongUserInputException, present_error
import functools
from typing import Optional, List
from .cacher import Cacher
from .openai_worker import OpenAIWorker
from threading import Event

class OpenaiPanelCommand(WindowCommand):
    stop_event: Event = Event()
    worker_thread: Optional[OpenAIWorker] = None

    def __init__(self, window):
        super().__init__(window)
        self.settings = sublime.load_settings("openAI.sublime-settings")
        # Load assistants from settings
        self.load_assistants()

        # Register a callback to reload assistants when settings change
        self.settings.add_on_change("reload_assistants", self.load_assistants)

    def load_assistants(self):
        self.assistants: List[AssistantSettings] = [
            AssistantSettings(**{**DEFAULT_ASSISTANT_SETTINGS, **assistant})
            for assistant in self.settings.get('assistants', [])
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
        text: Optional[str] = ""
        min_selection = self.settings.get("minimum_selection_length")
        for region in self.window.active_view().sel():
            if not region.empty():
                text += self.window.active_view().substr(region)
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
                text,
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

    def __del__(self):
        # Make sure to remove the settings change callback when the object is deleted
        if self.settings:
            self.settings.clear_on_change("reload_assistants")
