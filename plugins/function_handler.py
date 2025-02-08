from __future__ import annotations

import logging
from enum import Enum
from json import dumps, loads
from typing import Dict

from sublime import Region, Window

from .project_structure import build_folder_structure

# FIXME: logger prints nothing from within rust context
logger = logging.getLogger(__name__)


# TODO: This should be deleted in favor to rust type
class Function(str, Enum):
    replace_text_with_another_text = 'replace_text_with_another_text'
    replace_text_for_whole_file = 'replace_text_for_whole_file'
    read_region_content = 'read_region_content'
    get_working_directory_content = 'get_working_directory_content'


class FunctionHandler:
    @staticmethod
    def perform_function(func_name: str, args: str, window: Window) -> str:
        args_json = loads(args)
        logger.debug(f'executing: {func_name}')
        if func_name == Function.replace_text_with_another_text.value:
            path = args_json.get('file_path')
            old_content = args_json.get('old_content')
            new_content = args_json.get('new_content')

            if (
                path
                and isinstance(path, str)
                and old_content
                and isinstance(old_content, str)
                and new_content
                and isinstance(new_content, str)
            ):
                view = window.find_open_file(path)
                if view:
                    escaped_string = (
                        old_content.replace('(', r'\(')
                        .replace(')', r'\)')
                        .replace('[', r'\[')
                        .replace(']', r'\]')
                        .replace('{', r'\{')
                        .replace('}', r'\}')
                        .replace('|', r'\|')
                        .replace('"', r'\"')
                        .replace('\\', r'\\\\')
                    )
                    region = view.find(pattern=escaped_string, start_pt=0)
                    logger.debug(f'region {region}')
                    serializable_region = {
                        'a': region.begin(),
                        'b': region.end(),
                    }
                    if (
                        region.begin() == region.end() == -1 or region.begin() == region.end() == 0
                    ):  # means search found nothing
                        return f'Text not found: {old_content}'
                    else:
                        view.run_command(
                            'replace_region',
                            {'region': serializable_region, 'text': new_content},
                        )
                        return dumps(serializable_region)
                else:
                    return f'File under path not found: {path}'
            else:
                return f'Wrong attributes passed: {path}, {old_content}, {new_content}'

        elif func_name == Function.replace_text_for_whole_file.value:
            path = args_json.get('file_path')
            create = args_json.get('create')
            content = args_json.get('content')
            if path and isinstance(path, str) and content and isinstance(content, str):
                if isinstance(create, bool):
                    window.open_file(path)
                view = window.find_open_file(path)
                if view:
                    region = Region(0, len(view))
                    view.run_command(
                        'replace_region',
                        {'region': {'a': region.begin(), 'b': region.end()}, 'text': content},
                    )
                    text = view.substr(region)
                    return dumps({'result': text})
                else:
                    return f'File under path not found: {path}'
            else:
                return f'Wrong attributes passed: {path}, {content}'

        elif func_name == Function.read_region_content.value:
            path = args_json.get('file_path')
            region = args_json.get('region')
            if path and isinstance(path, str) and region and isinstance(region, Dict):
                view = window.find_open_file(path)
                if view:
                    a_reg: int = region.get('a') if region.get('a') != -1 else 0  # type: ignore
                    b_reg = region.get('b') if region.get('b') != -1 else len(view)
                    region_ = Region(a=a_reg, b=b_reg)
                    text = view.substr(region_)
                    return dumps({'content': f'{text}'})
                else:
                    return f'File under path not found: {path}'
            else:
                return f'Wrong attributes passed: {path}, {region}'

        elif func_name == Function.get_working_directory_content.value:
            path = args_json.get('directory_path')
            if path and isinstance(path, str):
                folder_structure = build_folder_structure(path)

                return dumps({'content': f'{folder_structure}'})
            else:
                return f'Wrong attributes passed: {path}'
        else:
            return f"Called function doen't exists: {func_name}"
