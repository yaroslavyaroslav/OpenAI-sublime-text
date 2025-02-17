import logging

from sublime import QueryOperator, View
from sublime_plugin import EventListener

from .ass_base import CommonMethods

logger = logging.getLogger(__name__)


class AssWorkerRunningContext(EventListener):
    def on_query_context(
        self,
        view: View,
        key: str,
        operator: QueryOperator,
        operand: str,
        match_all: bool,
    ):
        if key == 'ass_worker_running':
            logger.debug('key == ass_worker_running')
            logger.debug(
                'CommonMethods.worker_thread is alive: %s',
                CommonMethods.is_worker_alive() if CommonMethods.worker else False,
            )
            return CommonMethods.worker and CommonMethods.is_worker_alive()
        return None
