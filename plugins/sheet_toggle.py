from collections import deque
from os.path import isfile

import sublime
import sublime_plugin

VIEW_TOGGLE_KEY = 'VIEW_AI_CONTEXT_INCLUDED'


class ToggleViewAiContextIncludedCommand(sublime_plugin.WindowCommand):
    _pending: dict[int, deque[list[sublime.View]]] = {}

    @classmethod
    def has_pending_changes(cls, window):
        return window.id() in cls._pending

    def run(self, paths=None):
        window = self.window
        if paths is None:
            views = [sheet.view() for sheet in window.selected_sheets()]
        else:
            views = []
            for path in dict.fromkeys(paths):
                view = window.find_open_file(path)
                if view:
                    window.promote_sheet(view.sheet())
                elif isfile(path):
                    view = window.open_file(path)
                if view:
                    views.append(view)

        window_id = window.id()
        queue = self._pending.setdefault(window_id, deque())
        queue.append(views)
        if len(queue) == 1:
            self._toggle_when_loaded(window_id)

    def _toggle_when_loaded(self, window_id):
        queue = self._pending[window_id]
        while queue:
            views = []
            for view in queue[0]:
                if view and view.is_valid():
                    window = view.window()
                    if window and window.id() == window_id:
                        views.append(view)
            if any(view.is_loading() for view in views):
                sublime.set_timeout(lambda: self._toggle_when_loaded(window_id), 25)
                return

            new_value = not all(view.settings().get(VIEW_TOGGLE_KEY, False) for view in views)
            for view in views:
                view.settings().set(VIEW_TOGGLE_KEY, new_value)

            queue.popleft()
            sublime.status_message(f'{len(views)} sheets toggled for context')
        del self._pending[window_id]


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
