from __future__ import annotations

import json
import logging
import os
from json.decoder import JSONDecodeError
from typing import Any, Dict, Iterator, List, Tuple

import sublime

from . import jl_utility as jl

logger = logging.getLogger(__name__)


class Cacher:
    def __init__(self, name: str | None = None) -> None:
        cache_dir = sublime.cache_path()
        plugin_cache_dir = os.path.join(cache_dir, 'OpenAI completion')
        if not os.path.exists(plugin_cache_dir):
            os.makedirs(plugin_cache_dir)

        # Create the file path to store the data
        self.history_file = os.path.join(
            plugin_cache_dir,
            '{file_name}chat_history.jl'.format(file_name=name + '_' if name else ''),
        )
        self.current_model_file = os.path.join(
            plugin_cache_dir,
            '{file_name}current_assistant.json'.format(file_name=name + '_' if name else ''),
        )
        self.tokens_count_file = os.path.join(
            plugin_cache_dir,
            '{file_name}tokens_count.json'.format(file_name=name + '_' if name else ''),
        )

    def check_and_create(self, path: str):
        if not os.path.isfile(path):
            open(path, 'w').close()

    def len(self) -> int:
        length = len(self.read_all()) // 2
        logger.debug(f'history length: {length}')
        return length

    def append_tokens_count(self, data: Dict[str, int]):
        try:
            with open(self.tokens_count_file, 'r') as file:
                existing_data: Dict[str, int] = json.load(file)
        except (FileNotFoundError, JSONDecodeError):
            existing_data = {
                'prompt_tokens': 0,
                'completion_tokens': 0,
            }

        for key, value in data.items():
            if key in existing_data:
                existing_data[key] += value
            else:
                existing_data[key] = value

        with open(self.tokens_count_file, 'w') as file:
            json.dump(existing_data, file)

    def reset_tokens_count(self):
        with open(self.tokens_count_file, 'w') as _:
            pass  # Truncate the file by opening it in 'w' mode and doing nothing

    @staticmethod
    def read_file_from_project(file_path: str) -> str:
        with open(file_path, 'r') as data:
            content = data.read()
            return content

    def read_tokens_count(self) -> Tuple[int, int]:
        self.check_and_create(self.tokens_count_file)
        with open(self.tokens_count_file, 'r') as file:
            try:
                data: Dict[str, int] | None = json.load(file)
                tokens = (data['prompt_tokens'], data['completion_tokens'])
            except JSONDecodeError:
                return (0, 0)
        return tokens

    def save_model(self, data: Dict[str, Any]):
        with open(self.current_model_file, 'w') as file:
            json.dump(data, file)

    def read_model(self) -> Dict[str, Any] | None:
        self.check_and_create(self.current_model_file)
        with open(self.current_model_file, 'r') as file:
            try:
                data: Dict[str, Any] | None = json.load(file)
            except JSONDecodeError:
                # TODO: Handle this state, but keep in mind
                # that it's completely legal to being a file empty for some (yet unspecified) state
                print('Empty file I belive')
                return None
        return data

    @staticmethod
    def expand_placeholders(line: Dict[str, str]) -> Dict[str, str]:
        if {'file_path', 'scope_name'}.issubset(line.keys()):
            file_path = line['file_path']
            scope = line['scope_name']
            file_content = Cacher.read_file_from_project(file_path)
            content = f'Path: `{file_path}`\n\n'
            content += f'```{scope}\n'
            content += f'{file_content}\n'
            content += '```'
            line['content'] = content
        return line

    def read_all(self) -> List[Dict[str, str]]:
        self.check_and_create(self.history_file)
        json_objects: List[Dict[str, str]] = []
        reader: Iterator[Dict[str, str]] = jl.reader(self.history_file)
        for json_object in reader:
            expanded_json = Cacher.expand_placeholders(json_object)
            json_objects.append(expanded_json)

        return json_objects

    def append_to_cache(self, cache_lines: List[Dict[str, str]]):
        # Create a new JSON Lines writer for output.jl
        writer = jl.writer(self.history_file)
        next(writer)
        for line in cache_lines:
            if {'content', 'file_path', 'scope_name'}.issubset(line.keys()):
                if line['file_path'] is not None:
                    copy_of_line = line.copy()
                    del copy_of_line['content']
                    writer.send(copy_of_line)
                    continue
            writer.send(line)

    def drop_first(self, number=4):
        self.check_and_create(self.history_file)
        # Read all lines from the JSON Lines file
        with open(self.history_file, 'r') as file:
            lines = file.readlines()

        # Remove the specified number of lines from the beginning
        lines = lines[number:]

        # Write the remaining lines back to the cache file
        with open(self.history_file, 'w') as file:
            file.writelines(lines)

    def drop_all(self):
        with open(self.history_file, 'w') as _:
            pass  # Truncate the file by opening it in 'w' mode and doing nothing
