import importlib
import sys
import types
import unittest
from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch


class FakeRegion:
    def __init__(self, a, b=None):
        self.a = a
        self.b = a if b is None else b

    def begin(self):
        return min(self.a, self.b)

    def end(self):
        return max(self.a, self.b)

    def empty(self):
        return self.a == self.b


class FakeSettings:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value

    def erase(self, key):
        self.values.pop(key, None)


class FakeSelection(list):
    def add(self, region):
        self.append(region)


class FakeWindow:
    def __init__(self, window_id=1):
        self.window_id = window_id
        self.window_settings = FakeSettings()
        self.panel = None
        self.commands = []
        self.opened = []

    def id(self):
        return self.window_id

    def settings(self):
        return self.window_settings

    def find_output_panel(self, name):
        return self.panel

    def active_panel(self):
        return 'output.openai_input' if self.panel is not None else None

    def run_command(self, command, args=None):
        self.commands.append((command, args))

    def get_view_index(self, _view):
        return 1, 0

    def open_file(self, target, flags, group):
        self.opened.append((target, flags, group))


class FakePanel:
    def __init__(self, window, text='', caret=0, panel_id=7):
        self._window = window
        self.text = text
        self.caret = caret
        self.panel_id = panel_id
        self.selection = FakeSelection([FakeRegion(caret)])
        window.panel = self

    def id(self):
        return self.panel_id

    def window(self):
        return self._window

    def size(self):
        return len(self.text)

    def substr(self, region):
        return self.text[region.begin() : region.end()]

    def sel(self):
        return self.selection

    def rowcol(self, point):
        prefix = self.text[:point]
        row = prefix.count('\n')
        column = len(prefix.rsplit('\n', 1)[-1])
        return row, column


class FakeChatView:
    def __init__(self, window, text='[source](/workspace/source.py:12)'):
        self._window = window
        self.text = text
        self.view_settings = FakeSettings()
        self.view_settings.set('openai_is_chat_transcript', True)

    def id(self):
        return 8

    def settings(self):
        return self.view_settings

    def window_to_text(self, _coordinates):
        return 3

    def score_selector(self, _point, _selector):
        return 1

    def line(self, _point):
        return FakeRegion(0, len(self.text))

    def substr(self, region):
        return self.text[region.begin() : region.end()]

    def window(self):
        return self._window


def load_input_panel_module():
    module_names = ('sublime', 'sublime_plugin', 'llm_runner')
    original_modules = {name: sys.modules.get(name) for name in module_names}

    sublime = types.ModuleType('sublime')
    sublime.Region = FakeRegion
    sublime.View = object
    sublime.Window = object
    sublime.status_message = lambda message: None
    sublime.get_clipboard = lambda: ''
    sublime.ENCODED_POSITION = 1
    sublime.ADD_TO_SELECTION = 32

    sublime_plugin = types.ModuleType('sublime_plugin')
    sublime_plugin.EventListener = object
    sublime_plugin.TextCommand = object
    sublime_plugin.WindowCommand = object

    llm_runner = types.ModuleType('llm_runner')
    llm_runner.AssistantSettings = object
    llm_runner.SublimeInputContent = object

    try:
        sys.modules['sublime'] = sublime
        sys.modules['sublime_plugin'] = sublime_plugin
        sys.modules['llm_runner'] = llm_runner
        sys.modules.pop('plugins.input_panel', None)
        return importlib.import_module('plugins.input_panel')
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


input_panel = load_input_panel_module()


class PromptHistorySessionTests(unittest.TestCase):
    def test_previous_starts_at_latest_and_preserves_draft(self):
        session = input_panel.PromptHistorySession()

        self.assertEqual(session.previous(['one', 'two'], 'draft'), 'two')
        self.assertEqual(session.previous(['one', 'two'], 'ignored'), 'one')
        self.assertEqual(session.previous(['one', 'two'], 'ignored'), 'one')
        self.assertTrue(session.browsing)

    def test_next_returns_to_draft_and_leaves_history_mode(self):
        session = input_panel.PromptHistorySession()
        session.previous(['one', 'two'], 'draft')
        session.previous(['one', 'two'], 'ignored')

        self.assertEqual(session.next(['one', 'two']), 'two')
        self.assertEqual(session.next(['one', 'two']), 'draft')
        self.assertFalse(session.browsing)
        self.assertIsNone(session.next(['one', 'two']))

    def test_empty_history_does_not_enter_history_mode(self):
        session = input_panel.PromptHistorySession()

        self.assertIsNone(session.previous([], 'draft'))
        self.assertFalse(session.browsing)


class InputPanelControllerTests(unittest.TestCase):
    def setUp(self):
        input_panel.OpenAIInputPanelController._pending_requests.clear()
        input_panel.OpenAIInputPanelController._history_sessions.clear()
        self.window = FakeWindow()

    def test_draft_round_trip_and_clear(self):
        controller = input_panel.OpenAIInputPanelController

        controller.save_draft(self.window, 'unfinished')
        self.assertEqual(controller.get_draft(self.window), 'unfinished')
        controller.clear_draft(self.window)
        self.assertEqual(controller.get_draft(self.window), '')

    def test_history_keeps_all_submitted_prompts_in_order(self):
        controller = input_panel.OpenAIInputPanelController

        for prompt in ['one', 'one', 'two']:
            controller.record_history(self.window, prompt)

        self.assertEqual(controller.get_history(self.window), ['one', 'one', 'two'])

    def test_history_ignores_malformed_storage(self):
        controller = input_panel.OpenAIInputPanelController
        self.window.settings().set(controller.HISTORY_STORAGE_KEY, ['ok', 3, '', None])

        self.assertEqual(controller.get_history(self.window), ['ok'])

    def test_navigation_requires_first_row_first_column(self):
        controller = input_panel.OpenAIInputPanelController
        controller.record_history(self.window, 'old prompt')

        panel = FakePanel(self.window, 'draft', caret=0)
        self.assertTrue(controller.should_navigate_previous(panel))

        panel.selection[:] = [FakeRegion(1)]
        self.assertFalse(controller.should_navigate_previous(panel))

        panel.selection[:] = [FakeRegion(0, 1)]
        self.assertFalse(controller.should_navigate_previous(panel))

    def test_cancel_saves_draft_clears_pending_and_hides_panel(self):
        controller = input_panel.OpenAIInputPanelController
        FakePanel(self.window, 'unfinished', caret=10)
        controller._pending_requests[self.window.id()] = object()

        controller.cancel(self.window)

        self.assertEqual(controller.get_draft(self.window), 'unfinished')
        self.assertIsNone(controller.get_pending_request(self.window))
        self.assertEqual(self.window.commands[-1], ('hide_panel', None))


class InputPanelEventListenerTests(unittest.TestCase):
    def setUp(self):
        input_panel.OpenAIInputPanelController._history_sessions.clear()
        input_panel.OpenAIInputPanelController._pending_requests.clear()
        input_panel.OpenAIInputPanelController._hiding_windows.clear()
        self.window = FakeWindow()
        self.panel = FakePanel(self.window, 'draft', caret=0)
        self.listener = input_panel.OpenaiInputPanelEventListener()

    def test_paste_is_replaced_with_code_block_command(self):
        self.assertEqual(
            self.listener.on_text_command(self.panel, 'paste_and_indent', None),
            ('openai_paste_as_code_block', None),
        )

    def test_generic_hide_panel_is_redirected_to_draft_saving_cancel(self):
        input_panel.OpenAIInputPanelController._pending_requests[self.window.id()] = object()

        self.assertEqual(
            self.listener.on_window_command(self.window, 'hide_panel', None),
            ('openai_cancel_input_panel', None),
        )

        input_panel.OpenAIInputPanelController._hiding_windows.add(self.window.id())
        self.assertIsNone(self.listener.on_window_command(self.window, 'hide_panel', None))

    def test_up_enters_history_and_down_only_intercepts_while_browsing(self):
        controller = input_panel.OpenAIInputPanelController
        controller.record_history(self.window, 'old prompt')

        self.assertEqual(
            self.listener.on_text_command(
                self.panel,
                'move',
                {'by': 'lines', 'forward': False},
            ),
            ('openai_input_history_previous', None),
        )
        self.assertIsNone(
            self.listener.on_text_command(
                self.panel,
                'move',
                {'by': 'lines', 'forward': True},
            )
        )

        controller.history_session(self.window).previous(['old prompt'], 'draft')
        self.assertEqual(
            self.listener.on_text_command(
                self.panel,
                'move',
                {'by': 'lines', 'forward': True},
            ),
            ('openai_input_history_next', None),
        )

    def test_chat_markdown_link_opens_existing_file_target(self):
        chat_view = FakeChatView(self.window)

        with (
            patch(
                'plugins.input_panel.markdown_link_at',
                return_value=types.SimpleNamespace(destination='/workspace/source.py:12'),
            ),
            patch(
                'plugins.input_panel.local_file_target',
                return_value='/workspace/source.py:12',
            ),
        ):
            result = self.listener.on_text_command(
                chat_view,
                'drag_select',
                {'event': {'x': 1, 'y': 2}},
            )

        self.assertEqual(result, ('noop', None))
        self.assertEqual(
            self.window.opened,
            [('/workspace/source.py:12', input_panel.sublime.ENCODED_POSITION, 1)],
        )

    def test_modified_chat_selection_is_not_intercepted_as_link(self):
        chat_view = FakeChatView(self.window)

        result = self.listener.on_text_command(
            chat_view,
            'drag_select',
            {'event': {'x': 1, 'y': 2}, 'extend': True},
        )

        self.assertIsNone(result)
        self.assertEqual(self.window.opened, [])


class FileContextTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(input_panel.OpenAIInputPanelController._pending_requests.clear)
        self.window = FakeWindow()
        self.first = self.make_view('/workspace/first.txt', 'first-file-marker')
        self.second = self.make_view('/workspace/second.txt', 'second-file-marker')
        self.source = self.make_view('/workspace/source.txt', 'unattached')
        views = [self.first, self.second, self.source]
        self.window.views = lambda: views
        self.window.find_open_file = {view.file_name(): view for view in views}.get
        self.window.selected_sheets = Mock(return_value=[self.source])
        self.window.promote_sheet = Mock()

        sublime = input_panel.sublime
        self.enterContext(patch.multiple(
            sublime, create=True, active_window=lambda: self.window, Edit=object,
            Settings=object, Sheet=object, load_settings=lambda _: {}, set_timeout=Mock(),
        ))
        runner = types.ModuleType('llm_runner')
        self.kinds = runner.InputKind = Enum('InputKind', 'Sheet ViewSelection Command')
        runner.PromptMode = Enum('PromptMode', 'View Phantom')
        runner.AssistantSettings = object
        runner.SublimeInputContent = lambda kind, content, path=None, scope=None: (
            types.SimpleNamespace(input_kind=kind, content=content, path=path, scope=scope)
        )
        runner.Worker = self.worker = Mock()
        self.assistant = types.SimpleNamespace(url='http://localhost', output_mode=runner.PromptMode.View)

        modules = {
            'sublime': sublime,
            'sublime_plugin': types.SimpleNamespace(TextCommand=object, WindowCommand=object),
            'sublime_types': types.SimpleNamespace(Point=int),
            'llm_runner': runner,
            'plugins.errors.OpenAIException': types.SimpleNamespace(
                WrongUserInputException=RuntimeError, present_error=Mock(), present_error_str=Mock(),
            ),
            'plugins.function_handler': types.SimpleNamespace(FunctionHandler=Mock()),
            'plugins.image_handler': types.SimpleNamespace(ImageValidator=Mock()),
            'plugins.load_model': types.SimpleNamespace(ensure_cache_path=lambda _: 'same-chat-cache'),
            'plugins.output_panel': types.SimpleNamespace(SharedOutputPanelListener=Mock()),
            'plugins.phantom_streamer': types.SimpleNamespace(PhantomStreamer=Mock()),
            'plugins.response_manager': types.SimpleNamespace(ResponseManager=Mock()),
        }
        self.enterContext(patch.dict(sys.modules, modules))
        for name in ('plugins.openai_base', 'plugins.buffer', 'plugins.sheet_toggle'):
            sys.modules.pop(name, None)
        self.base = importlib.import_module('plugins.openai_base')
        self.sheet_toggle = importlib.import_module('plugins.sheet_toggle')
        self.enterContext(patch.object(input_panel, 'prepare_input_panel'))

    def make_view(self, path, text):
        view = Mock()
        view.window.return_value = self.window
        view.id.return_value = 42
        view.sheet.return_value = view
        view.view.return_value = view
        view.settings.return_value = FakeSettings()
        view.file_name.return_value = path
        view.sel.return_value = []
        view.scope_name.return_value = 'text.plain'
        view.size.return_value = len(text)
        view.substr.side_effect = lambda region: text[region.begin():region.end()]
        view.is_valid.return_value = True
        view.is_loading.return_value = False
        return view

    def toggle(self, **kwargs):
        command = self.sheet_toggle.ToggleViewAiContextIncludedCommand()
        command.window = self.window
        command.run(**kwargs)

    def compose(self, prompt):
        self.base.CommonMethods.process_openai_command(self.source, self.assistant, {})
        FakePanel(self.window, prompt)

    def submit(self):
        command = input_panel.OpenaiSubmitInputPanelCommand()
        command.window = self.window
        command.run()
        return self.worker.return_value.run.call_args.args[2]

    def attachments(self, inputs):
        return {item.path: item.content for item in inputs if item.input_kind == self.kinds.Sheet}

    def test_sidebar_adds_file_to_next_turn_with_another_tab_selected(self):
        self.first.settings().set(self.sheet_toggle.VIEW_TOGGLE_KEY, True)
        self.compose('First turn')
        self.assertEqual(set(self.attachments(self.submit())), {self.first.file_name()})

        self.toggle(paths=[self.second.file_name()])
        self.compose('Second turn')
        inputs = self.submit()

        files = self.attachments(inputs)
        self.assertEqual(set(files), {self.first.file_name(), self.second.file_name()})
        self.assertIn('second-file-marker', files[self.second.file_name()])
        self.assertEqual(inputs[-1].content, 'Second turn')
        self.assertEqual(
            [call.kwargs['path'] for call in self.worker.call_args_list],
            ['same-chat-cache', 'same-chat-cache'],
        )

    def test_submit_reads_current_marks_and_current_buffer_contents(self):
        self.first.settings().set(self.sheet_toggle.VIEW_TOGGLE_KEY, True)
        self.compose('Draft before attachment changes')

        self.window.selected_sheets.return_value = [self.first]
        self.toggle()
        self.window.selected_sheets.return_value = [self.second]
        self.toggle()
        self.second.substr.side_effect = None
        self.second.substr.return_value = 'edited-in-buffer-marker'
        inputs = self.submit()

        files = self.attachments(inputs)
        self.assertEqual(set(files), {self.second.file_name()})
        self.assertIn('edited-in-buffer-marker', files[self.second.file_name()])
        self.assertEqual(inputs[-1].content, 'Draft before attachment changes')

    def test_submit_saves_draft_if_source_tab_moves_to_another_window(self):
        self.compose('Draft from the first window')
        other_window = FakeWindow(window_id=2)
        other_file = self.make_view('/other-project/private.txt', 'other-window-marker')
        other_file.settings().set(self.sheet_toggle.VIEW_TOGGLE_KEY, True)
        other_window.views = lambda: [other_file]
        self.source.window.return_value = other_window

        submit = input_panel.OpenaiSubmitInputPanelCommand()
        submit.window = self.window
        submit.run()

        self.worker.assert_not_called()
        controller = input_panel.OpenAIInputPanelController
        self.assertEqual(controller.get_draft(self.window), 'Draft from the first window')
        self.assertEqual(controller.get_history(self.window), [])
        self.assertIsNone(controller.get_pending_request(self.window))

    def test_pending_context_toggle_skips_tab_moved_to_another_window(self):
        self.second.is_loading.return_value = True
        self.toggle(paths=[self.second.file_name()])

        self.second.window.return_value = FakeWindow(window_id=2)
        self.second.is_loading.return_value = False
        input_panel.sublime.set_timeout.call_args.args[0]()

        self.assertFalse(self.second.settings().get(self.sheet_toggle.VIEW_TOGGLE_KEY, False))
        self.assertFalse(
            self.sheet_toggle.ToggleViewAiContextIncludedCommand.has_pending_changes(self.window)
        )

    def test_sidebar_opens_closed_file_and_waits_for_buffer_load(self):
        with TemporaryDirectory() as directory:
            path = str(Path(directory) / 'closed.txt')
            Path(path).write_text('saved-file-marker', encoding='utf-8')
            closed = self.make_view(path, 'saved-file-marker')
            closed.is_loading.return_value = True
            original_views = self.window.views()
            self.window.open_file = Mock(return_value=closed)

            self.toggle(paths=[path])
            self.window.open_file.assert_called_once_with(path)
            self.assertFalse(closed.settings().get(self.sheet_toggle.VIEW_TOGGLE_KEY, False))

            self.compose('Read the file')
            submit = input_panel.OpenaiSubmitInputPanelCommand()
            submit.window = self.window
            submit.run()
            self.worker.assert_not_called()
            self.assertIsNotNone(input_panel.OpenAIInputPanelController.get_pending_request(self.window))

            closed.is_loading.return_value = False
            self.window.views = lambda: [*original_views, closed]
            input_panel.sublime.set_timeout.call_args.args[0]()
            self.assertIn('saved-file-marker', self.attachments(self.submit())[path])


if __name__ == '__main__':
    unittest.main()
