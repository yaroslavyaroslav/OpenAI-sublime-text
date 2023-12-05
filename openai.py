from enum import Enum
from typing import List, Optional
import sublime
from sublime_plugin import TextCommand, EventListener
from sublime import Settings, View, Region, Edit
import functools
from .cacher import Cacher
from .errors.OpenAIException import WrongUserInputException, present_error
from .openai_panel import CommandMode

class Openai(TextCommand):
    def on_input_deprecated(self, region: Optional[Region], text: Optional[str], view: View, mode: str, input: str):
        from .openai_worker import OpenAIWorker # https://stackoverflow.com/a/52927102

        worker_thread = OpenAIWorker(region, text, view, mode=mode, command=input)
        worker_thread.start()

    def on_input(self, region: Optional[Region], text: Optional[str], view: View, mode: str, input: str):
        from .openai_worker import OpenAIWorker # https://stackoverflow.com/a/52927102

        worker_thread = OpenAIWorker(region=region, text=text, view=view, mode=mode, command=input)
        worker_thread.start()

    """
    asyncroniously send request to https://api.openai.com/v1/completions
    with the selcted text of the view
    and inserts suggestion from within response at place of `[insert]` placeholder
    """
    def run(self, edit: Edit, **kwargs):
        global settings
        plugin_loaded()
        mode = kwargs.get('mode', 'chat_completion')

        # get selected text
        region: Optional[Region] = None
        text: Optional[str] = None
        for region in self.view.sel():
            if not region.empty():
                text = self.view.substr(region)

        # Checking that user select some text
        try:
            if region and region.__len__() < settings.get("minimum_selection_length"):
                if mode != 'reset_chat_history' and mode != 'refresh_output_panel':
                    raise WrongUserInputException("Not enough text selected to complete the request, please expand the selection.")
        except WrongUserInputException as error:
            present_error(title="OpenAI error", error=error)
            return

        from .openai_worker import OpenAIWorker # https://stackoverflow.com/a/52927102

        if mode == CommandMode.reset_chat_history.value:
            Cacher().drop_all()
            output_panel = sublime.active_window().find_output_panel("OpenAI Chat")
            output_panel.set_read_only(False)
            region = Region(0, output_panel.size())
            output_panel.erase(edit, region)
            output_panel.set_read_only(True)
        elif mode == CommandMode.refresh_output_panel.value:
            from .outputpanel import SharedOutputPanelListener # https://stackoverflow.com/a/52927102
            window = sublime.active_window()
            listner = SharedOutputPanelListener(markdown=settings.get('markdown'))
            listner.toggle_overscroll(window=window, enabled=False)
            listner.refresh_output_panel(window=window)
            listner.show_panel(window=window)
        else: # mode 'chat_completion', always in panel
            sublime.active_window().show_input_panel(
                "Question: ",
                "",
                functools.partial(
                    self.on_input,
                    region if region else None,
                    text if text else None,
                    self.view,
                    mode
                ),
                None,
                None
            )

class ActiveViewEventListener(EventListener):
    def on_activated(self, view: View):
        global settings
        plugin_loaded()
        assistant = Cacher().read_model()
        status_hint_options: Optional[List[str]] = settings.get('status_hint', [])

        if assistant and 'name' in assistant and 'prompt_mode' in assistant and 'chat_model' in assistant:
            if status_hint_options:
                if len(status_hint_options) > 1:
                    if StatusBarMode._name.value in status_hint_options and StatusBarMode.prompt_mode.value in status_hint_options and StatusBarMode.chat_model.value in status_hint_options:
                        view.set_status('openai_assistant_settings', f'[{assistant["name"].title()} | {assistant["prompt_mode"].title()} | {assistant["chat_model"].upper()}]')
                    elif StatusBarMode._name.value in status_hint_options and StatusBarMode.prompt_mode.value in status_hint_options:
                        view.set_status('openai_assistant_settings', f'[{assistant["name"].title()} | {assistant["prompt_mode"].title()}]')
                    elif StatusBarMode._name.value in status_hint_options and StatusBarMode.chat_model.value in status_hint_options:
                        view.set_status('openai_assistant_settings', f'[{assistant["name"].title()} | {assistant["chat_model"].upper()}]')
                    elif StatusBarMode.prompt_mode.value in status_hint_options and StatusBarMode.chat_model.value in status_hint_options:
                        view.set_status('openai_assistant_settings', f'[{assistant["prompt_mode"].title()} | {assistant["chat_model"].upper()}]')
                elif len(status_hint_options) == 1:
                    if StatusBarMode._name.value in status_hint_options:
                        view.set_status('openai_assistant_settings', f'{assistant["name"].title}')
                    if StatusBarMode.prompt_mode.value in status_hint_options:
                        view.set_status('openai_assistant_settings', f'{assistant["prompt_mode"].title}')
                    if StatusBarMode.chat_model.value in status_hint_options:
                        view.set_status('openai_assistant_settings', f'{assistant["chat_model"].upper}')
                else: # status_hint_options is None or len(status_hint_options) == 0
                    pass

settings: Optional[Settings] = None

def plugin_loaded():
    global settings
    settings = sublime.load_settings("openAI.sublime-settings")

class StatusBarMode(Enum):
    _name = "name"
    prompt_mode = "prompt_mode"
    chat_model = "chat_model"
