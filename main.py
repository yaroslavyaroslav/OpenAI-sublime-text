import sys

# clear modules cache if package is reloaded (after update?)
prefix = __package__ + ".plugins"  # don't clear the base package
for module_name in [
    module_name
    for module_name in sys.modules
    if module_name.startswith(prefix)
]:
    del sys.modules[module_name]
del prefix

from .plugins.openai import Openai
from .plugins.active_view_event import ActiveViewEventListener
from .plugins.openai_panel import OpenaiPanelCommand
from .plugins.stop_worker_execution import StopOpenaiExecutionCommand
from .plugins.worker_running_context import OpenaiWorkerRunningContext
from .plugins.settings_reloader import ReloadSettingsListener
from .plugins.output_panel import SharedOutputPanelListener, AIChatViewEventListener
from .plugins.buffer import TextStreamAtCommand, ReplaceRegionCommand, EraseRegionCommand