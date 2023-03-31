import sublime, sublime_plugin
import functools
from .cacher import Cacher
import logging
from .openai_worker import OpenAIWorker


class Openai(sublime_plugin.TextCommand):
    def on_input(self, edit, region, text, view, mode, input):
        from .openai_worker import OpenAIWorker # https://stackoverflow.com/a/52927102

        worker_thread = OpenAIWorker(region, text, view, mode=mode, command=input)
        worker_thread.start()

    """
    asyncroniously send request to https://api.openai.com/v1/completions
    with the selcted text of the view
    and inserts suggestion from within response at place of `[insert]` placeholder
    """
    def run(self, edit, **kwargs):
        settings = sublime.load_settings("openAI.sublime-settings")
        mode = kwargs.get('mode', 'chat_completion')

        # get selected text
        region = ''
        text = ''
        for region in self.view.sel():
            if not region.empty():
                text = self.view.substr(region)


        # Cheching that user select some text
        try:
            if region.__len__() < settings.get("minimum_selection_length"):
                if mode != 'chat_completion' and mode != 'reset_char_history':
                    raise AssertionError("Not enough text selected to complete the request, please expand the selection.")
        except Exception as ex:
            sublime.error_message("Exception\n" + str(ex))
            logging.exception("Exception: " + str(ex))
            return

        if mode == 'edition':
            sublime.active_window().show_input_panel("Request: ", "Comment the given code line by line", functools.partial(self.on_input, edit, region, text, self.view, mode), None, None)
        elif mode == 'insertion':
            worker_thread = OpenAIWorker(edit, region, text, self.view, mode, "")
            worker_thread.start()
        elif mode == 'completion': # mode == `completion`
            worker_thread = OpenAIWorker(edit, region, text, self.view, mode, "")
            worker_thread.start()
        elif mode == 'reset_char_history':
            Cacher().drop_all()
            output_panel = sublime.active_window().find_output_panel("OpenAI Chat")
            output_panel.set_read_only(False)
            region = sublime.Region(0, output_panel.size())
            output_panel.erase(edit, region)
            output_panel.set_read_only(True)
        else: # mode 'chat_completion', always in panel
            sublime.active_window().show_input_panel("Question: ", "", functools.partial(self.on_input, edit, "region", "text", self.view, mode), None, None)

