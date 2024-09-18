import sublime
import sublime_plugin
import logging

logger = logging.getLogger(__name__)


class ReloadSettingsListener(sublime_plugin.EventListener):
    def on_post_save_async(self, view: sublime.View):
        logger.debug('Settings relodaer triggered')
        # This method is triggered whenever any file is saved. Check if the saved file is our settings.
        filepath = view.file_name()
        if filepath and 'openAI.sublime-settings' in filepath:
            logger.debug('openAI.sublime-settings relodaer triggered')
            # Reload the plugin settings by calling the plugin_loaded function directly.
            from .openai_base import plugin_loaded

            plugin_loaded()
