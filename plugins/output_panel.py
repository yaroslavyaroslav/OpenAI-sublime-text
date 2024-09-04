from sublime import Settings, Window, View, load_settings
from sublime_plugin import EventListener, ViewEventListener
from .cacher import Cacher
from typing import Dict, Optional


class SharedOutputPanelListener(EventListener):
    OUTPUT_PANEL_NAME = 'AI Chat'

    def __init__(self, markdown: bool = True, cacher: Cacher = Cacher()) -> None:
        self.markdown: bool = markdown
        self.cacher = cacher
        self.settings: Settings = load_settings('openAI.sublime-settings')
        self.panel_settings: Dict[str, bool] = self.settings.get(
            'chat_presentation', None
        )

        self.gutter_enabled: bool = self.panel_settings.get('gutter_enabled', True)
        self.line_numbers_enabled: bool = self.panel_settings.get(
            'line_numbers_enabled', True
        )
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

    def get_output_panel_(self, window: Window) -> View:
        output_panel = window.find_output_panel(
            self.OUTPUT_PANEL_NAME
        ) or window.create_output_panel(self.OUTPUT_PANEL_NAME)
        self.setup_common_presentation_style_(output_panel)
        return output_panel

    def setup_common_presentation_style_(self, view: View, reversed: bool = False):
        if self.markdown:
            view.assign_syntax('Packages/Markdown/MultiMarkdown.sublime-syntax')
        scroll_past_end = not self.scroll_past_end if reversed else self.scroll_past_end
        gutter_enabled = not self.gutter_enabled if reversed else self.gutter_enabled
        line_numbers_enabled = (
            not self.line_numbers_enabled if reversed else self.line_numbers_enabled
        )

        view.settings().set('scroll_past_end', scroll_past_end)
        view.settings().set('gutter', gutter_enabled)
        view.settings().set('line_numbers', line_numbers_enabled)
        view.settings().set('set_unsaved_view_name', False)

    def toggle_overscroll(self, window: Window, enabled: bool):
        view = self.get_output_view_(window=window)
        view.settings().set('scroll_past_end', enabled)

    def update_output_view(self, text: str, window: Window):
        view = self.get_output_view_(window=window)
        view.set_read_only(False)
        view.run_command('append', {'characters': text})
        view.set_read_only(True)
        view.set_name(self.OUTPUT_PANEL_NAME)

    def get_output_view_(self, window: Window, reversed: bool = False) -> View:
        view = self.get_active_tab_(window=window) or self.get_output_panel_(
            window=window
        )
        return view

    def refresh_output_panel(self, window: Window):
        output_panel = self.get_output_view_(window=window)
        output_panel.set_read_only(False)
        self.clear_output_panel(window)

        for line in self.cacher.read_all():
            ## TODO: Make me enumerated, e.g. Question 1, Question 2 etc.
            ## (it's not that easy, since question and answer are the different lines)
            ## FIXME: This logic conflicts with multifile/multimessage request behaviour
            ## it presents ## Question above each message, while has to do it once for a pack.
            if line['role'] == 'user':
                output_panel.run_command(
                    'append', {'characters': f'\n\n## Question\n\n'}
                )
            elif line['role'] == 'assistant':
                output_panel.run_command('append', {'characters': '\n\n## Answer\n\n'})

            output_panel.run_command('append', {'characters': line['content']})

        output_panel.set_read_only(True)
        output_panel.set_name(self.OUTPUT_PANEL_NAME)
        self.scroll_to_botton(window=window)

    def clear_output_panel(self, window: Window):
        output_panel = self.get_output_view_(window=window)
        output_panel.run_command('select_all')
        output_panel.run_command('right_delete')

    ## FIXME: This command doesn't work as expected at first run
    ## despite that textpoint provides correct value.
    def scroll_to_botton(self, window: Window):
        output_panel = self.get_output_view_(window=window)
        point = output_panel.text_point(__get_number_of_lines__(view=output_panel), 0)
        output_panel.show_at_center(point)

    def get_active_tab_(self, window) -> Optional[View]:
        for view in window.views():
            if view.name() == self.OUTPUT_PANEL_NAME:
                return view

    def show_panel(self, window: Window):
        # Attempt to activate the view with streaming_view_id if it exists
        view = self.get_active_tab_(window) or None
        if view:
            view.set_name(self.OUTPUT_PANEL_NAME)
            window.focus_view(self.get_active_tab_(window))
            return

        window.run_command('show_panel', {'panel': f'output.{self.OUTPUT_PANEL_NAME}'})


class AIChatViewEventListener(ViewEventListener):
    @classmethod
    def is_applicable(cls, settings) -> bool:
        return (
            settings.get('syntax') == 'Packages/Markdown/MultiMarkdown.sublime-syntax'
            or settings.get('syntax') == 'Packages/Markdown/PlainText.sublime-syntax'
        )

    def on_activated(self) -> None:
        self.update_status_message(self.view.window())

    def update_status_message(self, window: Window) -> None:
        project_settings = window.active_view().settings().get('ai_assistant', None)
        cacher = (
            Cacher(name=project_settings['cache_prefix'])
            if project_settings
            else Cacher()
        )
        if self.is_ai_chat_tab_active(window):
            status_message = self.get_status_message(cacher=cacher)
            active_view = window.active_view()
            if active_view and active_view.name() == 'AI Chat':
                active_view.set_status('ai_chat_status', status_message)

    def is_ai_chat_tab_active(self, window: Window) -> bool:
        active_view = window.active_view()
        return active_view and active_view.name() == 'AI Chat'

    def get_status_message(self, cacher: Cacher) -> str:
        tokens = cacher.read_tokens_count()
        prompt = tokens['prompt_tokens'] if tokens else 0
        completion = tokens['completion_tokens'] if tokens else 0
        total = prompt + completion

        return f'[⬆️: {prompt:,} + ⬇️: {completion:,} = {total:,}]'


def __get_number_of_lines__(view: View) -> int:
    last_line_num = view.rowcol(view.size())[0]
    return last_line_num
