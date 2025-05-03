from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from sublime import Edit, Region, Sheet, View
from sublime_plugin import TextCommand
from sublime_types import Point
from llm_runner import SublimeInputContent, InputKind  # type: ignore

logger = logging.getLogger(__name__)


class BufferContentManager:
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

    @classmethod
    def wrap_content_with_scope(cls, scope_name: str, content: str) -> str:
        logger.debug(f'scope_name {scope_name}')
        if scope_name.strip().lower() in ['markdown', 'multimarkdown', 'plain']:
            wrapped_content = content
        else:
            wrapped_content = f'```{scope_name}\n{content}\n```'
        logger.debug(f'wrapped_content {wrapped_content}')
        return wrapped_content

    @staticmethod
    def wrap_sheet_contents_with_scope(sheets: List[Sheet]) -> List[SublimeInputContent]:
        items = []

        if sheets:
            for sheet in sheets:
                view = sheet.view()
                if not view:
                    continue  # If for some reason the sheet cannot be converted to a view, skip.

                scope_region = view.scope_name(0)  # Assuming you want the scope at the start of the document
                scope_name = scope_region.split(' ')[0].split('.')[-1]

                file_path = view.file_name()
                content = view.substr(Region(0, view.size()))
                content = BufferContentManager.wrap_content_with_scope(scope_name, content)

                wrapped_content = f'Path: `{file_path}`\n\n' + content
                items.append(SublimeInputContent(InputKind.Sheet, wrapped_content, file_path, scope_name))

        return items


class TextStreamAtCommand(TextCommand):
    def run(self, edit: Edit, position: int, text: str):  # type: ignore
        _ = self.view.insert(edit=edit, pt=position, text=text)


class ReplaceRegionCommand(TextCommand):
    def run(self, edit: Edit, region: Dict[str, Point], text: str):  # type: ignore
        self.view.replace(edit=edit, region=Region(region['a'], region['b']), text=text)


class EraseRegionCommand(TextCommand):
    def run(self, edit: Edit, region: Dict[str, Point]):  # type: ignore
        self.view.erase(edit=edit, region=Region(region['a'], region['b']))
