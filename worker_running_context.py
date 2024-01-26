from .openai import Openai
from .openai_panel import OpenaiPanelCommand
from sublime_plugin import EventListener

class OpenaiWorkerRunningContext(EventListener):
    def on_query_context(self, view, key, operator, operand, match_all):
        if key == "openai_worker_running":
            return Openai.worker_thread is not None and Openai.worker_thread.is_alive() or OpenaiPanelCommand.worker_thread is not None and OpenaiPanelCommand.worker_thread.is_alive()
        return None
