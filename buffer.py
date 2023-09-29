from typing import Optional
from sublime import Edit, Region, View
# from sublime_types import Point
from sublime_plugin import TextCommand
from .assistant_settings import PromptMode

class TextStramer():
    def __init__(self, view: View) -> None:
        self.view = view

    def update_completion(self, completion: str):
        ## TODO: Check if this line is redundant w/o `insert_snipper` command.
        completion = completion.replace("$", "\$")
        ## Till this line selection has to be cleared and the carret should be placed in to a desired starting point.
        ## So begin() and end() sould be the very same carret offset.
        start_of_selection = self.view.sel()[0].begin() ## begin() because if we point an end there — it'll start to reverse prompting.
        self.view.run_command("text_stream_at", {"position": start_of_selection, "text": completion})
        return

    def delete_selected_region(self, region):
        json_reg = {'a': region.begin(), 'b': region.end()}
        self.view.run_command("erase_region", {"region": json_reg})

    ## DEPRECATED CODE
    def prompt_completion(self, mode: str, completion: str, placeholder: Optional[str] = None):
        completion = completion.replace("$", "\$")
        if mode == 'insertion':
            result = self.view.find(placeholder, 0, 1)
            if result:
                self.view.sel().clear()
                self.view.sel().add(result)
                # Replace the placeholder with the specified replacement text
                self.view.run_command("insert_snippet", {"contents": completion})
            return

        elif mode == 'completion':
            region = self.view.sel()[0]
            if region.a <= region.b:
                region.a = region.b
            else:
                region.b = region.a

            self.view.sel().clear()
            self.view.sel().add(region)
            # Replace the placeholder with the specified replacement text
            self.view.run_command("insert_snippet", {"contents": completion})
            return

        elif mode == 'edition': # it's just replacing all given text for now.
            region = self.view.sel()[0]
            self.view.run_command("insert_snippet", {"contents": completion})
            return
    ## DEPRECATED CODE

class TextStreamAtCommand(TextCommand):
    def run(self, edit: Edit, position: int, text: str):
        self.view.insert(edit=edit, pt=position, text=text)

    def append(self, point, text):
        self.view.run_command('text_stream_at', {'text': text, 'point': point})

class ReplaceRegionCommand(TextCommand):
    def run(self, edit: Edit, region, text: str):
        self.view.replace(edit=edit, region=Region(region['a'], region['b']), text=text)

class EraseRegionCommand(TextCommand):
    def run(self, edit: Edit, region):
        self.view.erase(edit=edit, region=Region(region['a'], region['b']))