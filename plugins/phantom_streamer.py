from __future__ import annotations

import logging
from enum import Enum
from typing import List
import re

import mdpopups
from llm_runner import InputKind, SublimeInputContent, write_to_cache  # type: ignore
from sublime import (
    NewFileFlags,
    Phantom,
    PhantomLayout,
    PhantomSet,
    View,
    active_window,
    load_settings,
    set_clipboard,
    set_timeout,
)

from .load_model import get_cache_path
from .output_panel import SharedOutputPanelListener
from .response_manager import ResponseManager
from .utils import extract_code_blocks

OPENAI_COMPLETION_KEY = 'openai_completion'
PHANTOM_TEMPLATE = (
    '---'
    + '\nallow_code_wrap: true'
    + '\n---'
    + '\n\n<a href="close">[x]</a> \
    | <a href="copy">Copy</a> \
    | <a href="append">Append</a> \
    | <a href="replace">Replace</a> \
    | <a href="new_file">In New Tab</a> \
    | <a href="history">Add to History</a>'
    + '\n\n{streaming_content}'
)
CLASS_NAME = 'openai-completion-phantom'

logger = logging.getLogger(__name__)


class PhantomStreamer:
    user_input: List[SublimeInputContent]

    def __init__(
        self,
        view: View,
        user_input: List[SublimeInputContent],
    ) -> None:
        self.view = view
        self.phantom_set = PhantomSet(self.view, OPENAI_COMPLETION_KEY)
        self.completion: str = ''
        self.phantom: Phantom | None = None
        self.phantom_id: int | None = None
        self.user_input = user_input
        self.is_discardable: bool = (
            load_settings('openAI.sublime-settings')
            .get('chat_presentation', {})
            .get('is_tabs_discardable', False)
        )
        self.should_extract_code: bool = (
            load_settings('openAI.sublime-settings')
            .get('chat_presentation', {})
            .get('phantom_integrate_code_only', False)
        )

        if len(view.sel()) > 0:
            logger.debug(f'view selection: {view.sel()[0]}')
            self.selected_region = view.sel()[0]  # saving only first selection to ease buffer logic
        else:
            self.selected_region = None

        self.init_phantom()

    @property
    def completion_code(self) -> str:
        """Returns the completion text according to the settings (either only the generated code or all the completion)"""
        if self.should_extract_code:
            return extract_code_blocks(self.completion)
        else:
            return self.completion

    def init_phantom(self):
        """Show a loading element to indicate that the model is processing the prompt"""
        self.update_phantom('Loading...')

    def update_completion(self, completion: str):
        """Update the completion and the phantom"""
        self.completion += completion
        self.update_phantom(self.completion)

    def update_phantom(self, content: str, hide_thoughts: bool = True):
        """Update and show the phantom"""
        line_beginning = self.view.line(self.view.sel()[0].end() if self.selected_region is None else self.selected_region.end())

        content = PHANTOM_TEMPLATE.format(streaming_content=content)
        html = mdpopups._create_html(self.view, self._preprocess_content(content, hide_thoughts=hide_thoughts), wrapper_class=CLASS_NAME)

        phantom = (
            self.phantom
            if self.phantom
            else Phantom(line_beginning, html, PhantomLayout.BLOCK, self.close_phantom)
        )

        def update_main_thread():
            # Updating on the main thread
            self.phantom_set.update([phantom])

        # Switch to the main thread to update phantoms
        set_timeout(update_main_thread)

    def close_phantom(self, attribute):
        logger.debug(f'attribure: `{attribute}`')
        if attribute in [action.value for action in PhantomActions]:
            if attribute == PhantomActions.copy.value:
                set_clipboard(self.completion_code)
            if attribute == PhantomActions.append.value:
                self.view.run_command(
                    'text_stream_at',
                    {'position': self.selected_region.end(),'text': self.completion_code},
                )
            elif attribute == PhantomActions.replace.value:
                region_object = {
                    'a': self.selected_region.begin(),
                    'b': self.selected_region.end(),
                }
                self.view.run_command('replace_region', {'region': region_object, 'text': self.completion_code})
            elif attribute == PhantomActions.new_file.value:
                new_tab = (self.view.window() or active_window()).new_file(
                    flags=NewFileFlags.ADD_TO_SELECTION | NewFileFlags.CLEAR_TO_RIGHT,
                    syntax='Packages/Markdown/MultiMarkdown.sublime-syntax',
                )
                logger.debug(f'self.is_discardable: {self.is_discardable}')
                new_tab.set_scratch(self.is_discardable)
                new_tab.run_command('text_stream_at', {'position': 0, 'text': self.completion_code})
            elif attribute == PhantomActions.history.value:
                assitant_content = SublimeInputContent(InputKind.AssistantResponse, self.completion)

                window = self.view.window() or active_window()

                path = get_cache_path(self.view)

                listner = SharedOutputPanelListener()

                ResponseManager.print_requests(listner, window, self.user_input)

                ResponseManager.prepare_to_response(listner, window)
                ResponseManager.update_output_panel_(listner, window, assitant_content.content)

                self.user_input.append(assitant_content)

                [write_to_cache(path, item) for item in self.user_input if item.input_kind != InputKind.Sheet]

            elif attribute == PhantomActions.close.value:
                pass

            # Handle showing/hidding thoughts for models that can think
            if attribute == PhantomActions.show_thoughts.value:
                set_timeout(self.update_phantom(self.completion, hide_thoughts=False))
            elif attribute == PhantomActions.hide_thoughts.value:
                set_timeout(self.update_phantom(self.completion, hide_thoughts=True))
            else:
                self.phantom_set.update([])


        else:  # for handling all the rest URLs
            (self.view.window() or active_window()).run_command('open_url', {'url': attribute})

    def _preprocess_content(self, content, hide_thoughts=True) -> str:
        """Pre-compile the content to show in the phantom
        
        Args:
            content (str): Content generated by the AI 
            close_thoughts (bool, optional): Indicate if we need to remove the thoughts or not
        
        Returns:
            str: preprocessed html
        """
        preprocessed_content = content

        openning_think = '<think>'
        closing_think = '</think>'

        # Check if there is a <think> token
        if openning_think in content:

            if closing_think in content:
                closed = True
                if hide_thoughts:
                    preprocessed_content = re.sub(r'<think>([\s\S]*?)<\/think>', '<think><a href="show_thoughts">Show thoughts</a></div>', preprocessed_content)
                else:
                    preprocessed_content = preprocessed_content.replace(closing_think, '\n\n\n<a href="hide_thoughts">Hide thoughts</a></div>')


            else:
                closed = False
                preprocessed_content += '</div>'

            # Build a nice opening <think>
            opening = '<div style="background-color: #303030; padding: 30px;">'

            # Replace the <think> token by a <div> for nicer display
            preprocessed_content = preprocessed_content.replace(openning_think, opening)

        return preprocessed_content


class PhantomActions(Enum):
    close = 'close'
    copy = 'copy'
    append = 'append'
    replace = 'replace'
    new_file = 'new_file'
    history = 'history'
    show_thoughts = 'show_thoughts'
    hide_thoughts = 'hide_thoughts'
