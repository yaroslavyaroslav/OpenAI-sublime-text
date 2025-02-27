import logging

from llm_runner import AssistantSettings, read_model  # type: ignore
from sublime import View, cache_path, load_settings, ok_cancel_dialog, windows
import os

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

    # Check if the folder exists; if not, prompt the user to create it.
    if not os.path.exists(path):
        if ok_cancel_dialog(f"Folder '{path}' does not exist. Create it?", 'Create'):
            try:
                os.makedirs(path, exist_ok=True)
                logger.debug('Created folder at %s', path)
            except Exception as e:
                logger.error('Failed to create folder at %s: %s', path, e)
        else:
            view.window.set("")
            logger.debug('User chose not to create folder at %s', path)

    return path


def get_model_or_default(view: View) -> AssistantSettings:
    settings = load_settings('openAI.sublime-settings')

    path = get_cache_path(view)

    try:
        assistant = read_model(path)
        logger.debug('assistant: %s', assistant)
    except RuntimeError as error:
        first_assistant = settings.get('assistants', None)[0]  # type: ignore
        logger.error('Error reading: %s', error)
        assistant = AssistantSettings(first_assistant)

    return assistant
