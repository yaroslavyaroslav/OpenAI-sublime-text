import sys

# clear modules cache if package is reloaded (after update?)
prefix = __package__ + '.plugins'  # type: ignore # don't clear the base package
for module_name in [module_name for module_name in sys.modules if module_name.startswith(prefix)]:
    del sys.modules[module_name]
del prefix

from .plugins.active_view_event import ActiveViewEventListener  # noqa: E402, F401
from .plugins.buffer import (  # noqa: E402, F401
    EraseRegionCommand,
    ReplaceRegionCommand,
    TextStreamAtCommand,
)
from .plugins.sheet_toggle import ToggleViewAiContextIncludedCommand, SelectSheetsWithAiContextIncludedCommand  # noqa: E402, F401
from .plugins.openai import Openai  # noqa: E402, F401
from .plugins.openai_panel import OpenaiPanelCommand  # noqa: E402, F401
from .plugins.output_panel import SharedOutputPanelListener  # noqa: E402, F401
from .plugins.phantom_streamer import PhantomStreamer  # noqa: E402, F401
from .plugins.settings_reloader import ReloadSettingsListener  # noqa: E402, F401
from .plugins.stop_worker_execution import (  # noqa: E402
    StopOpenaiExecutionCommand,  # noqa: F401
)
from .plugins.worker_running_context import (  # noqa: E402,
    OpenaiWorkerRunningContext,  # noqa: F401
)
