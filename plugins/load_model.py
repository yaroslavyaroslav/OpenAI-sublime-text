import logging

from llm_runner import AssistantSettings, read_model  # type: ignore
from sublime import View, cache_path, load_settings

import traceback

logger = logging.getLogger(__name__)


def get_cache_path(view: View) -> str:
    path = cache_path() + '/ass/'

    logger.debug('view %s', view)
    ai_assistant = view.settings().get(
        'ai_assistant',
        None,
    )
    logger.debug('ai_assistant %s', ai_assistant)
    if ai_assistant:
        path = ai_assistant.get(  # type: ignore
            'cache_prefix',
            cache_path(),
        )
    logger.debug('path: %s', path)
    return path


def get_model_or_default(view: View) -> AssistantSettings:
    settings = load_settings('ass.sublime-settings')

    path = get_cache_path(view)

    try:
        # print(f'# read model path = {path}')
        assistant = read_model(path)
        logger.debug('assistant: %s', assistant)
    except RuntimeError as error:
        # traceback.print_exc()
        first_assistant = settings.get('assistants', None)[0]  # type: ignore
        # logger.error('Error reading: %s', error)
        # logger.error(traceback.format_exc())
        assistant = AssistantSettings(first_assistant)

    return assistant
