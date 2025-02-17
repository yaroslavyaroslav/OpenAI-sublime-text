import logging

from sublime import Edit
from sublime_plugin import TextCommand

from .ass_base import CommonMethods

logger = logging.getLogger(__name__)


class StopAssExecutionCommand(TextCommand):
    def run(self, edit: Edit):
        logger.debug('Stop execution call')
        if CommonMethods.worker and CommonMethods.is_worker_alive():
            logger.debug('working_thread and is_alive == true')
            CommonMethods.stop_worker()
