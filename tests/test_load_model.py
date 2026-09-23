import importlib.util
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


def load_module():
    sublime = types.ModuleType('sublime')
    sublime.View = object
    sublime.cache_path = lambda: ''
    sublime.error_message = Mock()
    sublime.load_settings = Mock()
    sublime.ok_cancel_dialog = Mock()

    llm_runner = types.ModuleType('llm_runner')
    llm_runner.AssistantSettings = lambda settings: settings
    llm_runner.read_model = Mock(side_effect=RuntimeError('no cached model'))

    path = Path(__file__).resolve().parents[1] / 'plugins' / 'load_model.py'
    spec = importlib.util.spec_from_file_location('cache_path_under_test', path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'sublime': sublime, 'llm_runner': llm_runner}):
        spec.loader.exec_module(module)
    return module


class FakeView:
    def settings(self):
        return {}


class CachePathTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.module = load_module()
        self.module.cache_path = lambda: self.temp_dir.name
        self.module.load_settings.return_value = {'assistants': [{'name': 'Example'}]}
        self.path = os.path.join(self.temp_dir.name, 'OpenAI completion')
        self.view = FakeView()

    def test_reading_path_does_not_prompt_or_create_folder(self):
        self.assertEqual(self.module.get_cache_path(self.view), self.path)
        self.assertEqual(self.module.get_model_or_default(self.view), {'name': 'Example'})
        self.module.ok_cancel_dialog.assert_not_called()
        self.assertFalse(os.path.exists(self.path))

    def test_cancel_leaves_folder_absent(self):
        self.module.ok_cancel_dialog.return_value = False

        self.assertIsNone(self.module.ensure_cache_path(self.view))
        self.assertFalse(os.path.exists(self.path))

    def test_create_makes_folder_and_existing_folder_does_not_prompt_again(self):
        self.module.ok_cancel_dialog.return_value = True

        self.assertEqual(self.module.ensure_cache_path(self.view), self.path)
        self.assertTrue(os.path.isdir(self.path))
        self.assertEqual(self.module.ensure_cache_path(self.view), self.path)
        self.module.ok_cancel_dialog.assert_called_once()

    def test_failed_creation_stops_and_reports_error(self):
        self.module.ok_cancel_dialog.return_value = True
        with patch.object(self.module.os, 'makedirs', side_effect=PermissionError('denied')):
            self.assertIsNone(self.module.ensure_cache_path(self.view))
        self.module.error_message.assert_called_once()

    def test_missing_assistants_has_no_fallback_model(self):
        self.module.load_settings.return_value = {}

        self.assertIsNone(self.module.get_model_or_default(self.view))
        self.module.ok_cancel_dialog.assert_not_called()


if __name__ == '__main__':
    unittest.main()
