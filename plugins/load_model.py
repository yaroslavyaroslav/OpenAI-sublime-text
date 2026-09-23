import logging
import os

from llm_runner import AssistantSettings, read_model  # type: ignore
from sublime import View, cache_path, error_message, load_settings, ok_cancel_dialog

logger = logging.getLogger(__name__)


def get_cache_path(view: View) -> str:
    path = os.path.join(cache_path(), 'OpenAI completion')

    logger.debug('view %s', view)
    ai_assistant = view.settings().get('ai_assistant', None)
    logger.debug('ai_assistant %s', ai_assistant)
    if ai_assistant:
        path = ai_assistant.get(  # type: ignore
            'cache_prefix',
            path,
        )
    logger.debug('Resolved cache path: %s', path)

    return path


def ensure_cache_path(view: View) -> str | None:
    path = get_cache_path(view)
    if os.path.isdir(path):
        return path

    if os.path.exists(path):
        error_message(f"Cache path '{path}' is not a folder.")
        return None

    if not ok_cancel_dialog(f"Folder '{path}' does not exist. Create it?", 'Create'):
        logger.debug('User chose not to create folder at %s', path)
        return None

    try:
        os.makedirs(path, exist_ok=True)
    except OSError as error:
        logger.error('Failed to create folder at %s: %s', path, error)
        error_message(f"Failed to create cache folder '{path}': {error}")
        return None

    logger.debug('Created folder at %s', path)
    return path


def get_model_or_default(view: View) -> AssistantSettings | None:
    settings = load_settings('openAI.sublime-settings')

    path = get_cache_path(view)

    try:
        assistant = read_model(path)
        logger.debug('assistant: %s', assistant)
    except RuntimeError as error:
        logger.error('Error reading: %s', error)
        assistants = settings.get('assistants', [])  # type: ignore
        if not assistants:
            logger.error('No assistants are configured')
            return None
        assistant = AssistantSettings(assistants[0])

    return assistant
