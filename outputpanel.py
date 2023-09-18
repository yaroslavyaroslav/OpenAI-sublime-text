from sublime import Window, View
from sublime_plugin import EventListener
from .cacher import Cacher

class SharedOutputPanelListener(EventListener):
    OUTPUT_PANEL_NAME = "OpenAI Chat"

    def __init__(self, markdown: bool = True) -> None:
        self.markdown: bool = markdown
        super().__init__()

    def __get_output_panel__(self, window: Window) -> View:
        output_panel = window.find_output_panel(self.OUTPUT_PANEL_NAME) or window.create_output_panel(self.OUTPUT_PANEL_NAME)
        if self.markdown: output_panel.set_syntax_file("Packages/Markdown/MultiMarkdown.sublime-syntax")
        return output_panel

    def toggle_overscroll(self, window: Window, enabled: bool):
        output_panel = self.__get_output_panel__(window=window)
        # scroll_past_end = output_panel.settings().get("scroll_past_end")
        output_panel.settings().set("scroll_past_end", enabled)

    ## FIXME: This one should allow scroll while updating, yet it should follow the text if it's not
    def update_output_panel(self, text: str, window: Window):
        output_panel = self.__get_output_panel__(window=window)
        output_panel.set_read_only(False)
        output_panel.run_command('append', {'characters': text})
        output_panel.set_read_only(True)
        num_lines: int = get_number_of_lines(output_panel)

    def refresh_output_panel(self, window):
        output_panel = self.__get_output_panel__(window=window)
        output_panel.set_read_only(False)
        self.clear_output_panel(window)

        for line in Cacher().read_all():
            if line['role'] == 'user':
                output_panel.run_command('append', {'characters': f'\n\n## Question\n\n'})
            elif line['role'] == 'assistant':
                ## This one placed here as there're could be loooong questions.
                output_panel.run_command('append', {'characters': '\n\n## Answer\n\n'})

            output_panel.run_command('append', {'characters': line['content']})

        # scrolling panel to the bottom.
        point = output_panel.text_point(get_number_of_lines(view=output_panel), 0)
        output_panel.show_at_center(point)
        output_panel.set_read_only(True)

    def clear_output_panel(self, window):
        output_panel = self.__get_output_panel__(window=window)
        output_panel.run_command("select_all")
        output_panel.run_command("right_delete")

    def show_panel(self, window):
        window.run_command("show_panel", {"panel": f"output.{self.OUTPUT_PANEL_NAME}"})

def get_number_of_lines(view: View) -> int:
        last_line_num = view.rowcol(view.size())[0] + 1
        return last_line_num