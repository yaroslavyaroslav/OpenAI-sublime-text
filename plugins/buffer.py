from __future__ import annotations

from typing import Dict

from sublime import Edit, Region, View
from sublime_types import Point
from sublime_plugin import TextCommand


class TextStreamer:
    def __init__(self, view: View) -> None:
        self.view = view

    def update_completion(self, completion: str):
        ## Till this line selection has to be cleared and the carret should be placed in to a desired starting point.
        ## So begin() and end() sould be the very same carret offset.
        ## begin() because if we point an end there — it'll start to reverse prompting.
        start_of_selection = self.view.sel()[0].begin()
        self.view.run_command('text_stream_at', {'position': start_of_selection, 'text': completion})
        return

    def delete_selected_region(self, region: Region):
        json_reg = {'a': region.begin(), 'b': region.end()}
        self.view.run_command('erase_region', {'region': json_reg})


class TextStreamAtCommand(TextCommand):
    def run(self, edit: Edit, position: int, text: str):  # type: ignore
        _ = self.view.insert(edit=edit, pt=position, text=text)


class ReplaceRegionCommand(TextCommand):
    def run(self, edit: Edit, region: Dict[str, Point], text: str):  # type: ignore
        self.view.replace(edit=edit, region=Region(region['a'], region['b']), text=text)


class EraseRegionCommand(TextCommand):
    def run(self, edit: Edit, region: Dict[str, Point]):  # type: ignore
        self.view.erase(edit=edit, region=Region(region['a'], region['b']))
