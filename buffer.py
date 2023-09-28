from typing import Optional
from sublime import Edit, Region, View
# from sublime_types import Point
from sublime_plugin import TextCommand
from .assistant_settings import PromptMode

class SublimeBuffer():
    def __init__(self, view: View) -> None:
        self.view = view
        self.offset = 0

    def update_completion(self, prompt_mode: PromptMode, completion: str, placeholder: Optional[str] = None):
        region = self.view.sel()[0]
        completion = completion.replace("$", "\$")
        print(f'prompt_mode: {prompt_mode}')
        if prompt_mode == PromptMode.insert.name:
            # print('xxx13')
            result = self.view.find(placeholder, 0, 1)
            if result:
                self.view.sel().clear()
                self.view.sel().add(result)
                # Replace the placeholder with the specified replacement text
                self.view.run_command("insert", {"characters": completion})
            return

        elif prompt_mode == PromptMode.append.name:
            end_of_selection = region.end() + self.offset

            self.offset += len(completion)

            # Replace the placeholder with the specified replacement text
            self.view.run_command("text_stream_at", {"position": end_of_selection, "text": completion})
            return

        elif prompt_mode == PromptMode.replace.name: # it's just replacing all given text for now.
            json_reg = {'a': region.begin(), 'b': region.end()}
            self.view.run_command('replace_region', {'region': json_reg, "text": completion})
            return

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