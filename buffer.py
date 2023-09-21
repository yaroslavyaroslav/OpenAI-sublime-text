from typing import Optional
from sublime import View
from .assistant_settings import PromptMode

class SublimeBuffer():

    def __init__(self, view: View) -> None:
        self.view = view

    def update_completion(self, prompt_mode: PromptMode, completion: str, placeholder: Optional[str] = None):
        # print(f'prompt_mode: {prompt_mode}')
        completion = completion.replace("$", "\$")
        if prompt_mode == PromptMode.insert.name:
            print('xxx13')
            result = self.view.find(placeholder, 0, 1)
            if result:
                self.view.sel().clear()
                self.view.sel().add(result)
                # Replace the placeholder with the specified replacement text
                self.view.run_command("insert_snippet", {"contents": completion})
            return

        elif prompt_mode == PromptMode.append.name:
            print('xxx14')
            # Replace the placeholder with the specified replacement text
            self.view.run_command("insert_snippet", {"contents": completion})
            # self.view.run_command("append", {"characters": completion})

            return

        elif prompt_mode == PromptMode.replace.name: # it's just replacing all given text for now.
            region = self.view.sel()[0]
            self.view.run_command("insert_snippet", {"contents": completion})
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
