from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Dict, List

import sublime
from llm_runner import AssistantSettings, SublimeInputContent  # type: ignore
from sublime import Region, View, Window
from sublime_plugin import EventListener, TextCommand, WindowCommand

from .section_folding import is_chat_view
from .vendor.sublime_chat_ui.history import PromptHistorySession
from .vendor.sublime_chat_ui.links import local_file_target, markdown_link_at
from .vendor.sublime_chat_ui.markdown import fenced_code
from .vendor.sublime_chat_ui.presentation import prepare_input_panel, replace_content, view_text

logger = logging.getLogger(__name__)


@dataclass
class PendingInputRequest:
    source_view: View
    assistant: AssistantSettings | None
    inputs: List[SublimeInputContent]


class OpenAIInputPanelController:
    PANEL_NAME = 'openai_input'
    DRAFT_STORAGE_KEY = 'OPENAI_INPUT_DRAFT_STORAGE'
    HISTORY_STORAGE_KEY = 'OPENAI_INPUT_HISTORY_STORAGE'
    _pending_requests: Dict[int, PendingInputRequest] = {}
    _history_sessions: Dict[int, PromptHistorySession] = {}
    _hiding_windows: set[int] = set()

    @classmethod
    def is_input_panel_view(cls, view: View | None) -> bool:
        if view is None:
            return False
        window = view.window()
        if window is None:
            return False
        panel = window.find_output_panel(cls.PANEL_NAME)
        return panel is not None and panel.id() == view.id()

    @staticmethod
    def _replace_panel_content(panel: View, text: str) -> None:
        replace_content(panel, text)

    @staticmethod
    def panel_text(panel: View) -> str:
        return view_text(panel)

    @classmethod
    def get_draft(cls, window: Window) -> str:
        draft = window.settings().get(cls.DRAFT_STORAGE_KEY, '')
        return draft if isinstance(draft, str) else ''

    @classmethod
    def save_draft(cls, window: Window, draft: str) -> None:
        window.settings().set(cls.DRAFT_STORAGE_KEY, draft)

    @classmethod
    def clear_draft(cls, window: Window) -> None:
        window.settings().erase(cls.DRAFT_STORAGE_KEY)

    @classmethod
    def get_history(cls, window: Window) -> List[str]:
        history = window.settings().get(cls.HISTORY_STORAGE_KEY, [])
        if not isinstance(history, list):
            return []
        return [item for item in history if isinstance(item, str) and item]

    @classmethod
    def record_history(cls, window: Window, prompt: str) -> None:
        history = cls.get_history(window)
        history.append(prompt)
        window.settings().set(cls.HISTORY_STORAGE_KEY, history)

    @classmethod
    def history_session(cls, window: Window) -> PromptHistorySession:
        return cls._history_sessions.setdefault(window.id(), PromptHistorySession())

    @classmethod
    def reset_history_session(cls, window: Window) -> None:
        cls._history_sessions.pop(window.id(), None)

    @classmethod
    def is_caret_at_history_boundary(cls, panel: View) -> bool:
        selections = list(panel.sel())
        if len(selections) != 1 or not selections[0].empty():
            return False
        return panel.rowcol(selections[0].begin()) == (0, 0)

    @classmethod
    def should_navigate_previous(cls, panel: View) -> bool:
        window = panel.window()
        return bool(
            window
            and cls.is_caret_at_history_boundary(panel)
            and cls.get_history(window)
        )

    @classmethod
    def should_navigate_next(cls, panel: View) -> bool:
        window = panel.window()
        return bool(
            window
            and cls.is_caret_at_history_boundary(panel)
            and cls.history_session(window).browsing
        )

    @classmethod
    def show(
        cls,
        window: Window,
        source_view: View,
        assistant: AssistantSettings | None,
        inputs: List[SublimeInputContent],
    ) -> None:
        cls._pending_requests[window.id()] = PendingInputRequest(
            source_view=source_view,
            assistant=assistant,
            inputs=inputs,
        )

        cls.reset_history_session(window)
        prepare_input_panel(window, cls.PANEL_NAME, cls.get_draft(window))

    @classmethod
    def get_pending_request(cls, window: Window) -> PendingInputRequest | None:
        return cls._pending_requests.get(window.id())

    @classmethod
    def clear_pending_request(cls, window: Window) -> None:
        cls._pending_requests.pop(window.id(), None)

    @classmethod
    def cancel(cls, window: Window) -> None:
        panel = window.find_output_panel(cls.PANEL_NAME)
        if panel is not None:
            cls.save_draft(window, cls.panel_text(panel))
        cls.reset_history_session(window)
        cls.clear_pending_request(window)
        cls._hiding_windows.add(window.id())
        try:
            window.run_command('hide_panel')
        finally:
            cls._hiding_windows.discard(window.id())


class OpenaiSubmitInputPanelCommand(WindowCommand):
    def run(self) -> None:
        panel_view = self.window.find_output_panel(OpenAIInputPanelController.PANEL_NAME)
        if panel_view is None:
            sublime.status_message('OpenAI input panel is not open')
            return

        pending_request = OpenAIInputPanelController.get_pending_request(self.window)
        if pending_request is None:
            sublime.status_message('OpenAI input request is missing')
            return

        prompt = OpenAIInputPanelController.panel_text(panel_view).strip()
        if not prompt:
            sublime.status_message('Prompt is empty')
            return

        if pending_request.assistant is None:
            sublime.status_message('Assistant settings are unavailable')
            return

        from .openai_base import CommonMethods, get_sheets_context
        from .sheet_toggle import ToggleViewAiContextIncludedCommand

        if ToggleViewAiContextIncludedCommand.has_pending_changes(self.window):
            sublime.status_message('Files are still loading. Submit again when they are ready.')
            return

        source_view = pending_request.source_view
        source_window = source_view.window() if source_view.is_valid() else None
        if source_window is None or source_window.id() != self.window.id():
            OpenAIInputPanelController.cancel(self.window)
            sublime.status_message('The original tab left this window. Reopen the prompt to send.')
            return

        inputs = get_sheets_context(self.window) + pending_request.inputs
        OpenAIInputPanelController.record_history(self.window, prompt)
        OpenAIInputPanelController.clear_draft(self.window)
        OpenAIInputPanelController.reset_history_session(self.window)
        OpenAIInputPanelController.clear_pending_request(self.window)
        self.window.run_command('hide_panel')
        CommonMethods.handle_input(
            prompt,
            source_view,
            pending_request.assistant,
            inputs,
        )


class OpenaiSubmitInputPanelFromViewCommand(TextCommand):
    def run(self, edit) -> None:
        window = self.view.window()
        if window is None:
            sublime.status_message('OpenAI input panel window is unavailable')
            return
        window.run_command('openai_submit_input_panel')


class OpenaiCancelInputPanelCommand(WindowCommand):
    def run(self) -> None:
        OpenAIInputPanelController.cancel(self.window)


class OpenaiCancelInputPanelFromViewCommand(TextCommand):
    def run(self, edit) -> None:
        window = self.view.window()
        if window is None:
            return
        window.run_command('openai_cancel_input_panel')


class OpenaiInputHistoryPreviousCommand(TextCommand):
    def run(self, edit) -> None:
        window = self.view.window()
        if window is None:
            return

        session = OpenAIInputPanelController.history_session(window)
        text = session.previous(
            OpenAIInputPanelController.get_history(window),
            OpenAIInputPanelController.panel_text(self.view),
        )
        if text is not None:
            self._replace(edit, text)

    def _replace(self, edit, text: str) -> None:
        self.view.replace(edit, Region(0, self.view.size()), text)
        self.view.sel().clear()
        self.view.sel().add(Region(0))
        self.view.show(0)


class OpenaiInputHistoryNextCommand(OpenaiInputHistoryPreviousCommand):
    def run(self, edit) -> None:
        window = self.view.window()
        if window is None:
            return

        session = OpenAIInputPanelController.history_session(window)
        text = session.next(OpenAIInputPanelController.get_history(window))
        if text is not None:
            self._replace(edit, text)


class OpenaiPasteAsCodeBlockCommand(TextCommand):
    def run(self, edit) -> None:
        clipboard = sublime.get_clipboard()
        if not clipboard:
            return

        block = fenced_code(clipboard)
        selections = list(self.view.sel())

        if not selections:
            self.view.insert(edit, self.view.size(), block)
            return

        for region in reversed(selections):
            self.view.replace(edit, region, block)


class OpenaiInputPanelEventListener(EventListener):
    def on_window_command(
        self,
        window: Window,
        command_name: str,
        args: Dict[str, Any] | None,
    ):
        if (
            command_name == 'hide_panel'
            and window.id() not in OpenAIInputPanelController._hiding_windows
            and window.active_panel() == f'output.{OpenAIInputPanelController.PANEL_NAME}'
            and OpenAIInputPanelController.get_pending_request(window) is not None
        ):
            return ('openai_cancel_input_panel', None)
        return None

    def on_text_command(self, view: View, command_name: str, args: Dict[str, Any] | None):
        chat_link_result = self._open_chat_link(view, command_name, args)
        if chat_link_result is not None:
            return chat_link_result

        if not OpenAIInputPanelController.is_input_panel_view(view):
            return None

        if command_name in {'paste', 'paste_and_indent'}:
            return ('openai_paste_as_code_block', None)

        command_args = args or {}
        if command_name == 'move' and command_args.get('by') == 'lines':
            if command_args.get('forward'):
                if OpenAIInputPanelController.should_navigate_next(view):
                    return ('openai_input_history_next', None)
            elif OpenAIInputPanelController.should_navigate_previous(view):
                return ('openai_input_history_previous', None)

        window = view.window()
        if (
            window is not None
            and OpenAIInputPanelController.history_session(window).browsing
            and command_name not in {'openai_input_history_previous', 'openai_input_history_next'}
        ):
            OpenAIInputPanelController.reset_history_session(window)

        return None

    def _open_chat_link(
        self,
        view: View,
        command_name: str,
        args: Dict[str, Any] | None,
    ):
        command_args = args or {}
        event = command_args.get('event')
        if (
            command_name != 'drag_select'
            or not is_chat_view(view)
            or not isinstance(event, dict)
            or command_args.get('by')
            or command_args.get('extend')
            or command_args.get('subtractive')
        ):
            return None

        x = event.get('x')
        y = event.get('y')
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            return None

        point = view.window_to_text((x, y))
        if view.score_selector(point, 'meta.link.inline') <= 0:
            return None

        line = view.line(point)
        link = markdown_link_at(view.substr(line), point - line.begin())
        if link is None:
            return None

        target = local_file_target(link.destination)
        if target is None:
            return None

        window = view.window()
        if window is None:
            return None

        group, _ = window.get_view_index(view)
        flags = sublime.ENCODED_POSITION
        if command_args.get('additive'):
            flags |= sublime.ADD_TO_SELECTION
        window.open_file(target, flags, group)
        return ('noop', None)

    def on_pre_close_window(self, window: Window) -> None:
        if OpenAIInputPanelController.get_pending_request(window) is not None:
            panel = window.find_output_panel(OpenAIInputPanelController.PANEL_NAME)
            if panel is not None:
                OpenAIInputPanelController.save_draft(
                    window,
                    OpenAIInputPanelController.panel_text(panel),
                )
        OpenAIInputPanelController.reset_history_session(window)
        OpenAIInputPanelController.clear_pending_request(window)
