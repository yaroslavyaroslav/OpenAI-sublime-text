import sublime
from sublime import Settings, View, Region, Sheet
from threading import Event
from typing import Optional, List, Dict, Any
import logging

from .assistant_settings import (
    AssistantSettings,
    CommandMode,
)
from .errors.OpenAIException import WrongUserInputException, present_error
from .openai_worker import OpenAIWorker
from .image_handler import ImageValidator

logger = logging.getLogger(__name__)


class CommonMethods:
    stop_event: Event = Event()
    worker_thread: Optional[OpenAIWorker] = None

    @classmethod
    def process_openai_command(
        cls, view: View, assistant: Optional[AssistantSettings], kwargs: Dict[str, Any]
    ):
        logger.debug('Openai started')
        plugin_loaded()
        mode = kwargs.pop('mode', 'chat_completion')
        files_included = kwargs.get('files_included', False)

        region: Optional[Region] = None
        text: Optional[str] = ''

        logger.debug('mode: %s', mode)
        logger.debug('Region: %s', region)
        for region in view.sel():
            if not region.empty():
                text += view.substr(region) + '\n'

        logger.debug('Selected text: %s', text)
        # Checking that user selected some text
        try:
            if region and len(region) < settings.get('minimum_selection_length'):
                if mode == CommandMode.chat_completion:
                    raise WrongUserInputException(
                        'Not enough text selected to complete the request, please expand the selection.'
                    )
        except WrongUserInputException as error:
            present_error(title='OpenAI error', error=error)
            return

        logger.debug('AssistantSettings: %s', assistant)
        logger.debug('files_included: %s', files_included)

        if mode == CommandMode.handle_image_input.value:
            cls.handle_image_input(region, text, view, mode)

        elif mode == CommandMode.chat_completion.value:
            cls.handle_chat_completion(
                view, region, text, mode, assistant, files_included
            )

    @classmethod
    def handle_image_input(
        cls, region: Optional[Region], text: str, view: View, mode: str
    ):
        valid_input = ImageValidator.get_valid_image_input(text)

        sublime.active_window().show_input_panel(
            'Command for Image: ',
            '',
            lambda user_input: cls.on_input(
                region, valid_input, view, mode, user_input, None, None
            ),
            None,
            None,
        )

    @classmethod
    def handle_chat_completion(
        cls,
        view: View,
        region: Optional[Region],
        text: str,
        mode: str,
        assistant: Optional[AssistantSettings],
        files_included: bool,
    ):
        sheets = sublime.active_window().selected_sheets() if files_included else None
        sublime.active_window().show_input_panel(
            'Question: ',
            '',
            lambda user_input: cls.handle_input(
                user_input, region, text, view, mode, assistant, sheets
            ),
            None,
            None,
        )

    @classmethod
    def handle_input(cls, user_input, region, text, view, mode, assistant, sheets):
        logger.debug('User input received: %s', user_input)
        cls.on_input(region, text, view, mode, user_input, assistant, sheets)

    @classmethod
    def on_input(
        cls,
        region: Optional[Region],
        text: str,
        view: View,
        mode: str,
        input: str,
        assistant: Optional[AssistantSettings],
        selected_sheets: Optional[List[Sheet]],
    ):
        # from .openai_worker import OpenAIWorker  # https://stackoverflow.com/a/52927102

        cls.stop_worker()  # Stop any existing worker before starting a new one
        cls.stop_event.clear()

        cls.worker_thread = OpenAIWorker(
            stop_event=cls.stop_event,
            region=region,
            text=text,
            view=view,
            mode=mode,
            command=input,
            assistant=assistant,
            sheets=selected_sheets,
        )
        cls.worker_thread.start()

    @classmethod
    def stop_worker(cls):
        # if cls.worker_thread and cls.worker_thread.is_alive():
        logger.debug('Stopping worker...')
        cls.stop_event.set()  # Signal the thread to stop
        # cls.worker_thread = None


settings: Optional[Settings] = None


def plugin_loaded():
    global settings
    settings = sublime.load_settings('openAI.sublime-settings')
