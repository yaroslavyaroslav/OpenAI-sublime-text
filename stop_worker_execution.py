from .openai import Openai
from .openai_panel import OpenaiPanelCommand
from sublime_plugin import TextCommand

class StopOpenaiExecutionCommand(TextCommand):
    def run(self, edit):
        if Openai.worker_thread:
            Openai.stop_event.set()
        elif OpenaiPanelCommand.worker_thread:
            OpenaiPanelCommand.stop_event.set()
