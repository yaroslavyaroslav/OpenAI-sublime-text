import logging

from sublime import Edit
from sublime_plugin import TextCommand

from .openai_base import CommonMethods

logger = logging.getLogger(__name__)


class StopOpenaiExecutionCommand(TextCommand):
    def run(self, edit: Edit):
        logger.debug('Stop execution call')
        if CommonMethods.worker_thread and CommonMethods.worker_thread.is_alive():
            logger.debug('working_thread and is_alive == true')
            CommonMethods.stop_worker()
