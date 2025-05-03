import sublime
import sublime_plugin

VIEW_TOGGLE_KEY = 'VIEW_AI_CONTEXT_INCLUDED'


class ToggleViewAiContextIncludedCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        window = self.window
        sheets = window.selected_sheets()

        # Gather current values for the VIEW_TOGGLE_KEY
        current_values = [sheet.view().settings().get(VIEW_TOGGLE_KEY, False) for sheet in sheets]

        # Check if all current values are True
        if all(current_values):
            # If all values are True, set them all to False
            new_value = False
        else:
            # If some values are False, set all to True
            new_value = True

        # Set the new value for each sheet
        for sheet in sheets:
            view = sheet.view()
            if view:
                view.settings().set(VIEW_TOGGLE_KEY, new_value)

        sublime.status_message(f'{len(sheets)} sheets toggled for context')


class SelectSheetsWithAiContextIncludedCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        window = self.window
        sheets_with_ai_context = []

        for view in window.views():
            if view and view.settings().get(VIEW_TOGGLE_KEY, False):
                sheets_with_ai_context.append(view.sheet())

        # Select identified sheets
        window.select_sheets(sheets_with_ai_context)

        sublime.status_message(f'Selected {len(sheets_with_ai_context)} sheets with AI context included.')
