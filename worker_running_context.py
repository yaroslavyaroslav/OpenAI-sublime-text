from .openai import Openai
from .openai_panel import OpenaiPanelCommand
from sublime_plugin import EventListener
from sublime import View, QueryOperator

class OpenaiWorkerRunningContext(EventListener):
    def on_query_context(self, view: View, key: str, operator: QueryOperator, operand: str, match_all: bool):
        if key == "openai_worker_running":
            return Openai.worker_thread is not None and Openai.worker_thread.is_alive() or OpenaiPanelCommand.worker_thread is not None and OpenaiPanelCommand.worker_thread.is_alive()
        return None
