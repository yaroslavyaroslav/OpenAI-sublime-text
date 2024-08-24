from enum import Enum
from threading import Event
from typing import Any, Dict, List, Optional

import sublime
from sublime import Edit, Region, Settings, Sheet, View
from sublime_plugin import EventListener, TextCommand

from .assistant_settings import CommandMode
from .cacher import Cacher
from .errors.OpenAIException import WrongUserInputException, present_error
from .openai_worker import OpenAIWorker


class Openai(TextCommand):
    stop_event: Event = Event()
    worker_thread: Optional[OpenAIWorker] = None
    cacher = None

    def on_input(self, region: Optional[Region], text: str, view: View, mode: str, input: str, selected_sheets: Optional[List[Sheet]]):
        from .openai_worker import OpenAIWorker  # https://stackoverflow.com/a/52927102

        Openai.stop_worker()  # Stop any existing worker before starting a new one
        Openai.stop_event.clear()

        Openai.worker_thread = OpenAIWorker(stop_event=self.stop_event, region=region, text=text, view=view, mode=mode, command=input, assistant=None, sheets=selected_sheets)
        Openai.worker_thread.start()

    def run(self, edit: Edit, **kwargs):
        from .output_panel import (
            SharedOutputPanelListener,  # https://stackoverflow.com/a/52927102
        )

        if not settings:
            # Abort if settings are not loaded yet
            return

        mode = kwargs.get('mode', 'chat_completion')
        files_included = kwargs.get('files_included', False)
        self.project_settings = self.view.settings().get('ai_assistant', None)
        self.cacher = Cacher(name=self.project_settings['cache_prefix']) if self.project_settings else Cacher()

        listener = SharedOutputPanelListener(markdown=settings.get('markdown'), cacher=self.cacher)
        # get selected text
        region: Optional[Region] = None
        text: Optional[str] = ""
        for region in self.view.sel():
            if not region.empty():
                text += self.view.substr(region) + "\n\n"

        # Checking that user select some text
        try:
            if region and len(region) < settings.get("minimum_selection_length"):
                if mode == CommandMode.chat_completion:
                    raise WrongUserInputException("Not enough text selected to complete the request, please expand the selection.")
        except WrongUserInputException as error:
            present_error(title="OpenAI error", error=error)
            return

        if mode == CommandMode.reset_chat_history.value:
            self.cacher.drop_all()
            self.cacher.reset_tokens_count()
            # FIXME: This is broken, beacuse it specified on panel
            window = sublime.active_window()

            view = listener.get_output_view_(window=window)
            view.set_read_only(False)
            region = Region(0, view.size())
            view.erase(edit, region)
            view.set_read_only(True)

        elif mode == CommandMode.create_new_tab.value:
            window = sublime.active_window()

            listener.create_new_tab(window)
            # listner.toggle_overscroll(window=window, enabled=True)
            listener.refresh_output_panel(window=window)

        elif mode == CommandMode.refresh_output_panel.value:
            window = sublime.active_window()
            
            # listner.toggle_overscroll(window=window, enabled=False)
            listener.refresh_output_panel(window=window)
            listener.show_panel(window=window)


        elif mode == CommandMode.handle_image_input.value:
            _ = sublime.active_window().show_input_panel(
                "Command for Image: ",
                "",
                lambda user_input: self.on_input(
                    region=region if region else None,
                    text=text,
                    view=self.view,
                    mode=mode,
                    input=user_input,
                    selected_sheets=None
                ),
                None,
                None,
            )

        elif mode == CommandMode.chat_completion.value:
            if files_included:
                sheets = sublime.active_window().selected_sheets()
                _ = sublime.active_window().show_input_panel(
                    "Question: ",
                    "",
                    lambda user_input: self.on_input(
                        region=region if region else None,
                        text=text,
                        view=self.view,
                        mode=mode,
                        input=user_input,
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
                        view=self.view,
                        mode=mode,
                        input=user_input,
                        selected_sheets=None
                    ),
                    None,
                    None,
                )

    # TODO: To chech if this is even necessary
    @classmethod
    def stop_worker(cls):
        if cls.worker_thread and cls.worker_thread.is_alive():
            cls.stop_event.set()  # Signal the thread to stop
            cls.worker_thread = None

class ActiveViewEventListener(EventListener):

    cacher = None

    def on_activated(self, view: View):
        ## FIXME: This is might be wrong, settings of view should be get not for an active view, but for a given window project view.
        ## It could be correct btw, as if a window with a specific settings gets active — it updated exact it status bar.
        self.project_settings = sublime.active_window().active_view().settings().get('ai_assistant', None)

        # Initialize Cacher with proper default handling for missing cache_prefix
        self.cacher = Cacher(name=self.project_settings['cache_prefix']) if self.project_settings else Cacher()

        # Reading the assistant model from cache
        assistant = self.cacher.read_model()

        status_hint_options: List[str] = settings.get('status_hint', []) if settings else []

        # Update status bar with potentially retrieved model
        self.update_status_bar(view, assistant, status_hint_options)

    def update_status_bar(self, view: View, assistant: Optional[Dict[str, Any]], status_hint_options: List[str]):
        if not assistant:
            return

        if not status_hint_options:
            return

        # Check necessary keys in assistant
        if {'name', 'prompt_mode', 'chat_model'} <= assistant.keys():
            statuses: List[str] = []
            for key in ['name', 'prompt_mode', 'chat_model']:
                lookup_key = key if key != 'name' else 'name_' # name is a reserved keyword
                if StatusBarMode[lookup_key].value in status_hint_options:
                    if key == 'chat_model':
                        statuses.append(assistant[key].upper())
                    else:
                        statuses.append(assistant[key].title())

            if statuses:
                status = f'[ {" | ".join(statuses)} ]'
                view.set_status('openai_assistant_settings', status)


class StatusBarMode(Enum):
    name_ = "name"
    prompt_mode = "prompt_mode"
    chat_model = "chat_model"


settings: Optional[Settings] = None

def plugin_loaded():
    global settings
    settings = sublime.load_settings("openAI.sublime-settings")
