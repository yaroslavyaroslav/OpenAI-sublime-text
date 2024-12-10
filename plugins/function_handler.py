from __future__ import annotations

import logging
from json import dumps
from typing import Dict, List

from sublime import Region, Window

from .assistant_settings import ToolCall
from .cacher import Cacher
from .errors.OpenAIException import FunctionCallFailedException
from .messages import MessageCreator
from .project_structure import build_folder_structure
from .support_types import JSONType
from .ai_functions import Function

logger = logging.getLogger(__name__)


class FunctionHandler:
    @staticmethod
    def perform_function(cacher: Cacher, window: Window, tool: ToolCall) -> List[Dict[str, str]]:
        logger.debug(f'executing: {tool.function.name}')
        if tool.function.name == Function.replace_text_with_another_text.value:
            path = tool.function.arguments.get('file_path')
            old_content = tool.function.arguments.get('old_content')
            new_content = tool.function.arguments.get('new_content')

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
                        raise FunctionCallFailedException(f'Text not found: {old_content}')
                    else:
                        view.run_command(
                            'replace_region',
                            {'region': serializable_region, 'text': new_content},
                        )
                        return MessageCreator.create_message(
                            cacher, command=dumps(serializable_region), tool_call_id=tool.id
                        )
                else:
                    raise FunctionCallFailedException(f'File under path not found: {path}')
            else:
                raise FunctionCallFailedException(
                    f'Wrong attributes passed: {path}, {old_content}, {new_content}'
                )
        elif tool.function.name == Function.replace_text_for_whole_file.value:
            path = tool.function.arguments.get('file_path')
            create = tool.function.arguments.get('create')
            content = tool.function.arguments.get('content')
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
                    return MessageCreator.create_message(
                        cacher, command=dumps({'result': text}), tool_call_id=tool.id
                    )
                else:
                    raise FunctionCallFailedException(f'File under path not found: {path}')
            else:
                raise FunctionCallFailedException(f'Wrong attributes passed: {path}, {content}')

        elif tool.function.name == Function.read_region_content.value:
            path = tool.function.arguments.get('file_path')
            region = tool.function.arguments.get('region')
            if path and isinstance(path, str) and region and isinstance(region, Dict):
                view = window.find_open_file(path)
                if view:
                    a_reg: int = region.get('a') if region.get('a') != -1 else 0  # type: ignore
                    b_reg = region.get('b') if region.get('b') != -1 else len(view)
                    region_ = Region(a=a_reg, b=b_reg)
                    text = view.substr(region_)
                    return MessageCreator.create_message(
                        cacher, command=dumps({'content': f'{text}'}), tool_call_id=tool.id
                    )
                else:
                    raise FunctionCallFailedException(f'File under path not found: {path}')
            else:
                raise FunctionCallFailedException(f'Wrong attributes passed: {path}, {region}')
        elif tool.function.name == Function.get_working_directory_content.value:
            path = tool.function.arguments.get('directory_path')
            if path and isinstance(path, str):
                folder_structure = build_folder_structure(path)

                return MessageCreator.create_message(
                    cacher, command=dumps({'content': f'{folder_structure}'}), tool_call_id=tool.id
                )
            else:
                raise FunctionCallFailedException(f'Wrong attributes passed: {path}')
        else:
            raise FunctionCallFailedException(f"Called function doen't exists: {tool.function.name}")

    @staticmethod
    def append_non_null(original: JSONType, append: JSONType) -> JSONType:
        """
        Recursively processes the object, returning only non-null fields.
        """
        if isinstance(original, int) and isinstance(append, int):
            # logger.debug(f'original: int `{original}`, append: int `{append}`')
            original += append
            return original

        elif isinstance(original, str) and isinstance(append, str):
            # logger.debug(f'original: str `{original}`, append: str `{append}`')
            original += append
            return original

        elif isinstance(original, dict) and isinstance(append, dict):
            # logger.debug(f'original: dict `{original}`, append: dict `{append}`')
            for key, value in append.items():
                if value is not None:
                    if key in original:
                        original[key] = FunctionHandler.append_non_null(original[key], value)
                    else:
                        original[key] = value
            return original

        elif isinstance(append, list) and isinstance(original, list):
            # logger.debug(f'original: list `{original}`, append: list `{append}`')
            # Append non-null values from append to the original list
            for index, item in enumerate(append):
                if (
                    isinstance(original, list)
                    and isinstance(original[index], dict)
                    and isinstance(item, dict)
                ):
                    if original[index].get('index') == item['index']:
                        FunctionHandler.append_non_null(original[index], item)
                        return original
                if isinstance(item, dict):
                    original.append(item)
            return original

        # If the object is neither a dictionary nor a list, return it directly
        return original
