from sublime import Window, View, load_settings
from sublime_plugin import EventListener
from .cacher import Cacher
from typing import Optional

class SharedOutputPanelListener(EventListener):
    OUTPUT_PANEL_NAME = "OpenAI Chat"

    def __init__(self, markdown: bool = True, cacher: Cacher = Cacher()) -> None:
        self.markdown: bool = markdown
        self.cacher = cacher
        self.settings = load_settings("openAI.sublime-settings")
        super().__init__()

    def create_new_tab(self, window: Window):
        print(f"self.streaming_view_id_1: {self.settings.get(f'streaming_view_id_for_window_{window.id()}', None)}")
        if self.settings.get(f"streaming_view_id_for_window_{window.id()}", None):
            if self.get_active_tab_(window=window):
                self.refresh_output_panel(window=window)
                self.show_panel(window=window)
                return

        new_view = window.new_file()
        new_view.set_scratch(True)
        new_view.settings().set("line_numbers", False)
        ## FIXME: This is temporary
        new_view.settings().set("scroll_past_end", True)
        self.settings.set(f'streaming_view_id_for_window_{window.id()}', new_view.id())

    def get_tab_(self, window: Window) -> Optional[View]:
        print(f"self.streaming_view_id_2: {self.settings.get(f'streaming_view_id_for_window_{window.id()}', None)}")
        if self.settings.get(f'streaming_view_id_for_window_{window.id()}', None) is not None:
            return self.get_active_tab_(window=window)

    def get_output_panel_(self, window: Window) -> View:
        output_panel = window.find_output_panel(self.OUTPUT_PANEL_NAME) or window.create_output_panel(self.OUTPUT_PANEL_NAME)
        self.setup_presentation_style_(output_panel)
        output_panel.settings().set("scroll_past_end", False)
        return output_panel

    def setup_presentation_style_(self, view: View):
        if self.markdown: view.set_syntax_file("Packages/Markdown/MultiMarkdown.sublime-syntax")

    def toggle_overscroll(self, window: Window, enabled: bool):
        view = self.get_output_view_(window=window)
        view.settings().set("scroll_past_end", enabled)

    def update_output_view(self, text: str, window: Window):
        view = self.get_output_view_(window=window)
        view.set_read_only(False)
        view.run_command('append', {'characters': text})
        view.set_read_only(True)

    def get_output_view_(self, window: Window) -> View:
        view = self.get_tab_(window=window) or self.get_output_panel_(window=window)
        self.setup_presentation_style_(view=view)
        return view

    def refresh_output_panel(self, window):
        output_panel = self.get_output_view_(window=window)
        output_panel.set_read_only(False)
        self.clear_output_panel(window)

        for line in self.cacher.read_all():
            ## TODO: Make me enumerated (it's not that easy, since question and answer are the different lines)
            if line['role'] == 'user':
                output_panel.run_command('append', {'characters': f'\n\n## Question\n\n'})
            elif line['role'] == 'assistant':
                output_panel.run_command('append', {'characters': '\n\n## Answer\n\n'})

            output_panel.run_command('append', {'characters': line['content']})

        output_panel.set_read_only(True)
        self.scroll_to_botton(window=window)

    def clear_output_panel(self, window):
        output_panel = self.get_output_view_(window=window)
        output_panel.run_command("select_all")
        output_panel.run_command("right_delete")

    ## FIXME: This command doesn't work as expected at first run
    ## despite that textpoint provides correct value.
    def scroll_to_botton(self, window):
        output_panel = self.get_output_view_(window=window)
        point = output_panel.text_point(__get_number_of_lines__(view=output_panel), 0)
        print(f"point: {point}")
        output_panel.show_at_center(point)

    def get_active_tab_(self, window) -> Optional[View]:
        if self.settings.get(f'streaming_view_id_for_window_{window.id()}', None) is not None:
            for view in window.views():
                if view.id() == self.settings.get(f'streaming_view_id_for_window_{window.id()}', None):
                    return view

    def show_panel(self, window):
        # Attempt to activate the view with streaming_view_id if it exists
        print(f"self.streaming_view_id_3: {self.settings.get(f'streaming_view_id_for_window_{window.id()}', None)}")
        if self.settings.get(f'streaming_view_id_for_window_{window.id()}', None) is not None:
            view = self.get_active_tab_(window)
            window.focus_view(view)
            return

        window.run_command("show_panel", {"panel": f"output.{self.OUTPUT_PANEL_NAME}"})

def __get_number_of_lines__(view: View) -> int:
        last_line_num = view.rowcol(view.size())[0]
        return last_line_num
