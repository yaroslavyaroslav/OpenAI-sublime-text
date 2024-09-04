from .openai_base import CommonMethods
from sublime_plugin import TextCommand
from sublime import Edit
import logging

logger = logging.getLogger(__name__)


class StopOpenaiExecutionCommand(TextCommand):
    def run(self, edit: Edit):
        logger.debug('Stop execution call')
        if CommonMethods.worker_thread and CommonMethods.worker_thread.is_alive():
            logger.debug('working_thread and is_alive == true')
            CommonMethods.stop_worker()
