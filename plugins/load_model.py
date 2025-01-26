from rust_helper import AssistantSettings, read_model  # type: ignore
from sublime import View, cache_path, load_settings


def get_cache_path(view: View) -> str:
    path = cache_path()

    ai_assistant = view.settings().get(
        'ai_assistant',
        None,
    )
    if ai_assistant:
        path = ai_assistant.get(  # type: ignore
            'cache_prefix',
            cache_path(),
        )
    return path


def get_model_or_default(view: View) -> AssistantSettings:
    settings = load_settings('openAI.sublime-settings')

    path = get_cache_path(view)

    try:
        assistant = read_model(path)
    except RuntimeError as error:
        first_assistant = settings.get('assistants', None)[0]  # type: ignore
        print(f'Error reading: model {error}')
        assistant = AssistantSettings(first_assistant)

    return assistant
