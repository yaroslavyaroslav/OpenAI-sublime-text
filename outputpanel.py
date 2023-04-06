import sublime
import sublime_plugin
from .cacher import Cacher

class SharedOutputPanelListener(sublime_plugin.EventListener):
    OUTPUT_PANEL_NAME = "OpenAI Chat"

    def get_output_panel(self, window):
        return window.find_output_panel(self.OUTPUT_PANEL_NAME) if window.find_output_panel(self.OUTPUT_PANEL_NAME) != None else window.create_output_panel(self.OUTPUT_PANEL_NAME)

    def rewrite_output_panel(self, window, markdown: bool, syntax_path: str):
        output_panel = self.get_output_panel(window=window)
        output_panel.set_read_only(False)
        self.clear_output_panel(window)

        if markdown: output_panel.set_syntax_file(syntax_path)

        for line in Cacher().read_all():
            if line['role'] == 'user':
                output_panel.run_command('append', {'characters': f'\n\n## Question\n\n'})
            elif line['role'] == 'assistant':
                ## This one left here as there're could be loooong questions.
                output_panel.run_command('append', {'characters': '\n\n## Answer\n\n'})

            output_panel.run_command('append', {'characters': line['content']})

        output_panel.set_read_only(True)
        num_lines = get_number_of_lines(output_panel)
        print(f'num_lines: {num_lines}')

        ## FIXME: To calibrate scroll.
        point = output_panel.text_point(num_lines, 0) # +8 is that much from last line of a past answer and the first line of a next one.

        output_panel.show_at_center(point)

    def clear_output_panel(self, window):
        output_panel = self.get_output_panel(window=window)
        output_panel.run_command("select_all")
        output_panel.run_command("right_delete")

    # This works pretty well. It shows the same output panel within any view.
    def on_activated(self, view):
        window = view.window()
        settings = sublime.load_settings("openAI.sublime-settings")
        if window:
            self.rewrite_output_panel(
                window=window,
                markdown=settings.get('markdown'),
                syntax_path=settings.get('syntax_path')
            )

    def show_panel(self, window):
        window.run_command("show_panel", {"panel": f"output.{self.OUTPUT_PANEL_NAME}"})

def get_number_of_lines(view):
        last_line_num = view.rowcol(view.size())[0] + 1
        return last_line_num