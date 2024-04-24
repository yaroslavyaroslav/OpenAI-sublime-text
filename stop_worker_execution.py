from .openai import Openai
from .openai_panel import OpenaiPanelCommand
from sublime_plugin import TextCommand
from sublime import Edit

class StopOpenaiExecutionCommand(TextCommand):
    def run(self, edit: Edit):
        # Check if Openai's worker_thread is active and stop it
        if Openai.worker_thread and Openai.worker_thread.is_alive():
            Openai.stop_event.set()

        # Similar check and stop mechanism for OpenaiPanelCommand's worker_thread
        if OpenaiPanelCommand.worker_thread and OpenaiPanelCommand.worker_thread.is_alive():
            OpenaiPanelCommand.stop_event.set()
