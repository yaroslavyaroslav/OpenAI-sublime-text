from __future__ import annotations

from typing import Dict

from llm_runner import Roles, read_all_cache  # type: ignore
from sublime import Settings, View, Window, load_settings
from sublime_plugin import EventListener

from .load_model import get_cache_path


class SharedOutputPanelListener(EventListener):
    OUTPUT_PANEL_NAME = 'AI Chat'

    def __init__(
        self,
        markdown: bool = True,
    ) -> None:
        self.markdown: bool = markdown
        # self.cacher = cacher
        self.settings: Settings = load_settings('openAI.sublime-settings')
        self.panel_settings: Dict[str, bool] | None = self.settings.get('chat_presentation')  # type: ignore

        self.gutter_enabled: bool = self.panel_settings.get('gutter_enabled', True)
        self.line_numbers_enabled: bool = self.panel_settings.get('line_numbers_enabled', True)
        self.scroll_past_end: bool = self.panel_settings.get('scroll_past_end', False)
        self.reverse_for_tab: bool = self.panel_settings.get('reverse_for_tab', True)
        super().__init__()

    def create_new_tab(self, window: Window):
        if self.get_active_tab_(window=window):
            self.refresh_output_panel(window=window)
            self.show_panel(window=window)
            return

        new_view = window.new_file()
        new_view.set_scratch(True)
        self.setup_common_presentation_style_(new_view, reversed=self.reverse_for_tab)
        ## FIXME: This is temporary, should be moved to plugin settings
        new_view.set_name(self.OUTPUT_PANEL_NAME)
        new_view.settings().set('sheet_view', self.OUTPUT_PANEL_NAME)

    def get_output_panel_(self, window: Window) -> View:
        output_panel = window.find_output_panel(self.OUTPUT_PANEL_NAME) or window.create_output_panel(
            self.OUTPUT_PANEL_NAME
        )
        self.setup_common_presentation_style_(output_panel)
        return output_panel

    def setup_common_presentation_style_(self, view: View, reversed: bool = False):
        if self.markdown:
            view.assign_syntax('Packages/Markdown/MultiMarkdown.sublime-syntax')
        scroll_past_end = not self.scroll_past_end if reversed else self.scroll_past_end
        gutter_enabled = not self.gutter_enabled if reversed else self.gutter_enabled
        line_numbers_enabled = not self.line_numbers_enabled if reversed else self.line_numbers_enabled

        view.settings().set('scroll_past_end', scroll_past_end)
        view.settings().set('gutter', gutter_enabled)
        view.settings().set('line_numbers', line_numbers_enabled)
        view.settings().set('set_unsaved_view_name', False)

    def toggle_overscroll(self, window: Window, enabled: bool):
        view = self.get_output_view_(window=window)
        view.settings().set('scroll_past_end', enabled)

    def update_output_view(self, text: str, window: Window):
        view = self.get_output_view_(window=window)
        view.run_command('append', {'characters': text, 'force': True})

    def get_output_view_(self, window: Window, reversed: bool = False) -> View:
        view = self.get_active_tab_(window=window) or self.get_output_panel_(window=window)
        view.set_name(self.OUTPUT_PANEL_NAME)
        return view

    def refresh_output_panel(self, window: Window):
        output_panel = self.get_output_view_(window=window)
        self.clear_output_panel(window)

        path = get_cache_path(window.active_view())  # type: ignore

        for item in read_all_cache(path):
            ## TODO: Make me enumerated, e.g. Question 1, Question 2 etc.
            if item.role == Roles.User:
                output_panel.run_command('append', {'characters': '\n\n## Question\n\n', 'force': True})
            # elif item.role == Roles.Assistant and 'tool_calls' in item:
            #     output_panel.run_command('append', {'characters': '\n\n## Tool Call\n\n', 'force': True})
            #     function_name = item['tool_calls'][0]['function']['name']
            #     function_name = f'`{function_name}`'
            #     output_panel.run_command('append', {'characters': function_name, 'force': True})
            #     continue
            # elif item['role'] == 'tool':
            #     output_panel.run_command('append', {'characters': '\n\n## Tool Result\n\n', 'force': True})
            #     if len(item['content']) > 50:
            #         output_panel.run_command(
            #             'append', {'characters': 'Function response is too long', 'force': True}
            #         )
            #     else:
            #         output_panel.run_command('append', {'characters': item['content'], 'force': True})

            #     continue
            elif item.role == Roles.Assistant:
                output_panel.run_command('append', {'characters': '\n\n## Answer\n\n', 'force': True})

            output_panel.run_command('append', {'characters': item.content, 'force': True})

        self.scroll_to_botton(window=window)

    def clear_output_panel(self, window: Window):
        output_panel = self.get_output_view_(window=window)
        output_panel.set_read_only(False)
        output_panel.run_command('select_all')
        output_panel.run_command('right_delete')
        output_panel.set_read_only(True)

    ## FIXME: This command doesn't work as expected at first run
    ## despite that textpoint provides correct value.
    def scroll_to_botton(self, window: Window):
        output_panel = self.get_output_view_(window=window)
        point = output_panel.text_point(__get_number_of_lines__(view=output_panel), 0)
        output_panel.show_at_center(point)

    def get_active_tab_(self, window) -> View | None:
        for view in window.views():
            if view.name() == self.OUTPUT_PANEL_NAME:
                return view

    def show_panel(self, window: Window):
        # Attempt to activate the view with streaming_view_id if it exists
        view = self.get_active_tab_(window) or None
        if view:
            view.set_name(self.OUTPUT_PANEL_NAME)
            return

        window.run_command('show_panel', {'panel': f'output.{self.OUTPUT_PANEL_NAME}'})


def __get_number_of_lines__(view: View) -> int:
    last_line_num = view.rowcol(view.size())[0]
    return last_line_num
