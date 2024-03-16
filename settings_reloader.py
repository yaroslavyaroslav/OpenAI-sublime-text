import sublime
import sublime_plugin

class ReloadSettingsListener(sublime_plugin.EventListener):
    def on_post_save_async(self, view: sublime.View):
        # This method is triggered whenever any file is saved. Check if the saved file is our settings.
        filepath = view.file_name()
        if filepath and "openAI.sublime-settings" in filepath:
            # Reload the plugin settings by calling the plugin_loaded function directly.
            from .openai import plugin_loaded
            plugin_loaded()

