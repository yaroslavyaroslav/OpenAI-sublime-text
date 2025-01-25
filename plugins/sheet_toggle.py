import sublime
import sublime_plugin

VIEW_TOGGLE_KEY = 'VIEW_AI_CONTEXT_INCLUDED'


class ToggleViewAiContextIncludedCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        window = self.window
        for sheet in window.selected_sheets():
            view = sheet.view()
            if view:
                current_value = view.settings().get(VIEW_TOGGLE_KEY, False)
                view.settings().set(VIEW_TOGGLE_KEY, not current_value)

        sublime.status_message(f'{len(window.selected_sheets())} sheets toggled for context')


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
