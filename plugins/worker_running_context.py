import logging

from sublime import QueryOperator, View
from sublime_plugin import EventListener

from .openai_base import CommonMethods

logger = logging.getLogger(__name__)


class OpenaiWorkerRunningContext(EventListener):
    def on_query_context(
        self,
        view: View,
        key: str,
        operator: QueryOperator,
        operand: str,
        match_all: bool,
    ):
        if key == 'openai_worker_running':
            logger.debug('key == openai_worker_running')
            logger.debug(
                'CommonMethods.worker_thread is alive: %s',
                CommonMethods.worker.is_alive() if CommonMethods.worker else False,
            )
            return CommonMethods.worker and CommonMethods.worker.is_alive()
        return None
