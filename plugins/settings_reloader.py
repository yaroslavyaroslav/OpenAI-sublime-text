import logging

import sublime
import sublime_plugin

logger = logging.getLogger(__name__)


class ReloadSettingsListener(sublime_plugin.EventListener):
    def on_post_save_async(self, view: sublime.View):
        logger.debug('Settings relodaer triggered')
        # This method is triggered whenever any file is saved. Check if the saved file is our settings.
        filepath = view.file_name()
        if filepath and 'ass.sublime-settings' in filepath:
            logger.debug('ass.sublime-settings relodaer triggered')
            # Reload the plugin settings by calling the plugin_loaded function directly.
            from .ass_base import plugin_loaded

            plugin_loaded()
