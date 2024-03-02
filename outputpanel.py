from sublime import Window, View
from sublime_plugin import EventListener
from .cacher import Cacher

class SharedOutputPanelListener(EventListener):
    OUTPUT_PANEL_NAME = "OpenAI Chat"

    def __init__(self, markdown: bool = True, cacher: Cacher = Cacher()) -> None:
        self.markdown: bool = markdown
        self.cacher = cacher
        super().__init__()

    def __get_output_panel__(self, window: Window) -> View:
        output_panel = window.find_output_panel(self.OUTPUT_PANEL_NAME) or window.create_output_panel(self.OUTPUT_PANEL_NAME)
        if self.markdown: output_panel.set_syntax_file("Packages/Markdown/MultiMarkdown.sublime-syntax")
        return output_panel

    def toggle_overscroll(self, window: Window, enabled: bool):
        output_panel = self.__get_output_panel__(window=window)
        output_panel.settings().set("scroll_past_end", enabled)

    def update_output_panel(self, text: str, window: Window):
        output_panel = self.__get_output_panel__(window=window)
        output_panel.set_read_only(False)
        output_panel.run_command('append', {'characters': text})
        output_panel.set_read_only(True)

    def refresh_output_panel(self, window):
        output_panel = self.__get_output_panel__(window=window)
        output_panel.set_read_only(False)
        self.clear_output_panel(window)

        for line in self.cacher.read_all():
            if line['role'] == 'user':
                output_panel.run_command('append', {'characters': f'\n\n## Question\n\n'})
            elif line['role'] == 'assistant':
                output_panel.run_command('append', {'characters': '\n\n## Answer\n\n'})

            output_panel.run_command('append', {'characters': line['content']})

        output_panel.set_read_only(True)
        self.scroll_to_botton(window=window)

    def clear_output_panel(self, window):
        output_panel = self.__get_output_panel__(window=window)
        output_panel.run_command("select_all")
        output_panel.run_command("right_delete")

    ## FIXME: This command doesn't work as expected at first run
    ## despite that textpoint provides correct value.
    def scroll_to_botton(self, window):
        output_panel = self.__get_output_panel__(window=window)
        point = output_panel.text_point(__get_number_of_lines__(view=output_panel), 0)
        print(f"point: {point}")
        output_panel.show_at_center(point)

    def show_panel(self, window):
        window.run_command("show_panel", {"panel": f"output.{self.OUTPUT_PANEL_NAME}"})

def __get_number_of_lines__(view: View) -> int:
        last_line_num = view.rowcol(view.size())[0]
        return last_line_num
