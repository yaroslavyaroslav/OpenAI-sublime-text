import sublime
import sublime_plugin

class SharedOutputPanelListener(sublime_plugin.EventListener):
    OUTPUT_PANEL_NAME = "shared_output_panel"

    def update_output_panel(self, window):
        output_panel = window.create_output_panel(SharedOutputPanelListener.OUTPUT_PANEL_NAME)
        output_panel.run_command("select_all")
        output_panel.run_command("right_delete")
        output_panel.run_command("insert", {"characters": "This is a shared output panel."})
        # window.run_command("show_panel", {"panel": "output." + SharedOutputPanelListener.OUTPUT_PANEL_NAME})
        # Set the desired offset here
        # desired_offset = 10

        # Scroll the output panel to the given offset
        # output_panel.show_at_center(desired_offset)

    # This works pretty well. It shows the same output panel within any view.
    # def on_activated(self, view):
    #     window = view.window()
    #     if window:
    #         self.update_output_panel(window)

def get_number_of_lines(view):
        last_line_num = view.rowcol(view.size())[0] + 1
        return last_line_num