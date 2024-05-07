from .assistant_settings import AssistantSettings, DEFAULT_ASSISTANT_SETTINGS, CommandMode
import sublime
from sublime import Settings, View, Region, Sheet, Window
from sublime_plugin import WindowCommand
from .errors.OpenAIException import WrongUserInputException, present_error
from typing import Optional, List
from .cacher import Cacher
from .openai_worker import OpenAIWorker
from threading import Event

class OpenaiPanelCommand(WindowCommand):
    stop_event: Event = Event()
    worker_thread: Optional[OpenAIWorker] = None
    cache_prefix = None
    files_included = False

    def __init__(self, window: Window):
        super().__init__(window)
        self.settings: Settings = sublime.load_settings("openAI.sublime-settings")
        self.project_settings = self.window.active_view().settings().get('ai_assistant', None)

        self.cacher = Cacher(name=self.project_settings['cache_prefix']) if self.project_settings else Cacher()
        # Load assistants from settings
        self.load_assistants()

        # Register a callback to reload assistants when settings change
        self.settings.add_on_change("reload_assistants", self.load_assistants)

    def load_assistants(self):
        self.assistants: List[AssistantSettings] = [
            AssistantSettings(**{**DEFAULT_ASSISTANT_SETTINGS, **assistant})
            for assistant in self.settings.get('assistants', [])
        ]

    def on_input(self, region: Optional[Region], text: Optional[str], view: View, mode: str, assistant: AssistantSettings, input: str, selected_sheets: Optional[List[Sheet]]):
        from .openai_worker import OpenAIWorker # https://stackoverflow.com/a/52927102

        OpenaiPanelCommand.stop_worker()  # Stop any existing worker before starting a new one
        OpenaiPanelCommand.stop_event.clear()

        OpenaiPanelCommand.worker_thread = OpenAIWorker(stop_event=self.stop_event, region=region, text=text, view=view, mode=mode, command=input, assistant=assistant, sheets=selected_sheets)
        OpenaiPanelCommand.worker_thread.start()

    def run(self, **kwargs):
        self.window.show_quick_panel([f"{assistant.name} | {assistant.prompt_mode} | {assistant.chat_model}" for assistant in self.assistants], self.on_done)
        self.files_included = kwargs.get('files_included', False)

    def on_done(self, index: int):
        if index == -1: return

        assistant = self.assistants[index]

        self.cacher.save_model(assistant.__dict__)

        region: Optional[Region] = None
        text: Optional[str] = ""

        min_selection: int = self.settings.get("minimum_selection_length", 10)
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

        if self.files_included:
            sheets = sublime.active_window().selected_sheets()
            _ = sublime.active_window().show_input_panel(
                "Question: ",
                "",
                lambda user_input: self.on_input(
                    region=region if region else None,
                    text=text,
                    view=self.window.active_view(),
                    mode=CommandMode.chat_completion.value,
                    input=user_input,
                    assistant=assistant,
                    selected_sheets=sheets
                ),
                None,
                None,
            )
        else:
            _ = sublime.active_window().show_input_panel(
                "Question: ",
                "",
                lambda user_input: self.on_input(
                    region=region if region else None,
                    text=text,
                    view=self.window.active_view(),
                    mode=CommandMode.chat_completion.value,
                    input=user_input,
                    assistant=assistant,
                    selected_sheets=None
                ),
                None,
                None,
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
