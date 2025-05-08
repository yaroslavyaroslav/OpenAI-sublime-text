from __future__ import annotations
import logging
import subprocess
import os
from enum import Enum
from json import dumps, loads
from typing import Dict, List, Tuple

from sublime import Region, Window
from .project_structure import build_folder_structure

logger = logging.getLogger(__name__)


class Function(str, Enum):
    apply_patch = 'apply_patch'
    replace_text_for_whole_file = 'replace_text_for_whole_file'
    read_region_content = 'read_region_content'
    get_working_directory_content = 'get_working_directory_content'


def _normalize_patch(patch_text: str) -> Tuple[str, str]:
    """
    Strip the Begin/End markers, rewrite Update File into ---/+++ headers,
    return (normalized_diff, file_path).
    """
    in_patch = False
    diff_lines: List[str] = []
    file_path: str | None = None

    for line in patch_text.splitlines():
        if line.startswith('*** Begin Patch'):
            in_patch = True
            continue
        if line.startswith('*** End Patch'):
            break
        if not in_patch:
            continue

        if line.startswith('*** Update File:'):
            file_path = line[len('*** Update File:') :].strip()
            diff_lines.append(f'--- a/{file_path}')
            diff_lines.append(f'+++ b/{file_path}')
        else:
            diff_lines.append(line)

    if not file_path:
        raise ValueError('No "*** Update File:" line found in patch.')
    return '\n'.join(diff_lines) + '\n', file_path


def _parse_simple_patch(diff: str) -> List[Tuple[str, str]]:
    """
    Extract contiguous - / + blocks as (old_block, new_block) pairs.
    This version preserves indentation by removing only the first character.
    """
    lines = diff.splitlines()
    i = 0
    hunks: List[Tuple[str, str]] = []

    while i < len(lines):
        # old-hunk lines start with '-' but not '---' (the file-header)
        if lines[i].startswith('-') and not lines[i].startswith('---'):
            old_block_lines: List[str] = []
            # collect all consecutive '-' lines
            while i < len(lines) and lines[i].startswith('-') and not lines[i].startswith('---'):
                old_block_lines.append(lines[i][1:])  # strip only the '-' marker
                i += 1

            new_block_lines: List[str] = []
            # collect all consecutive '+' lines
            while i < len(lines) and lines[i].startswith('+') and not lines[i].startswith('+++'):
                new_block_lines.append(lines[i][1:])  # strip only the '+' marker
                i += 1

            old_text = '\n'.join(old_block_lines)
            new_text = '\n'.join(new_block_lines)
            old_hunk = old_text + '\n'
            new_hunk = (new_text + '\n') if new_block_lines else ''
            hunks.append((old_hunk, new_hunk))
        else:
            i += 1

    return hunks


class FunctionHandler:
    @staticmethod
    def perform_function(func_name: str, args: str, window: Window) -> str:
        args_json = loads(args)
        logger.debug(f'executing: {func_name}')

        # -------------------------------------------------------------------
        # apply_patch
        if func_name == Function.apply_patch.value:
            patch_text = args_json.get('patch')
            if not isinstance(patch_text, str):
                return 'Wrong attributes passed: patch must be a string'

            # normalize + extract path
            try:
                normalized_diff, path = _normalize_patch(patch_text)
                # If path is not absolute, treat it as relative to project root
                if not os.path.isabs(path):
                    folders = window.folders()
                    project_root = folders[0] if folders else os.getcwd()
                    path = os.path.join(project_root, path)
            except Exception as e:
                return (
                    "Failed to parse patch header. Make sure your patch includes the markers and file path: \n"
                    "*** Begin Patch\n"
                    "*** Update File: /path/to/your/file\n"
                    "*** End Patch\n"
                    f"Parsing error: {e}"
                )

            # simple find/replace fallback (always use this)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    original = f.read()
                new_content = original

                hunks = _parse_simple_patch(normalized_diff)
                if not hunks:
                    return (
                        'Invalid patch format. Expected patch syntax:\n'
                        '*** Begin Patch\n'
                        '*** Update File: /path/to/file\n'
                        '@@ -start,count +start,count @@\n'
                        '-old line\n'
                        '+new line\n'
                        '*** End Patch'
                    )

                for old_hunk, new_hunk in hunks:
                    new_content = new_content.replace(old_hunk, new_hunk)

                if new_content == original:
                    return (
                        'Patch format recognized, but no changes were applied. '
                        "The diff syntax is correct; verify that the '-' lines exactly match "
                        'current file content (including whitespace/indentation) and '
                        "'+' lines reflect intended additions."
                    )

                with open(path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
            except Exception as e:
                return f'Patch failed: {e}'

            return 'Done!'

        # -------------------------------------------------------------------
        # replace_text_for_whole_file
        elif func_name == Function.replace_text_for_whole_file.value:
            path = args_json.get('file_path')
            create = args_json.get('create')
            content = args_json.get('content')
            if not (isinstance(path, str) and isinstance(content, str)):
                return f'Wrong attributes passed: file_path={path}, content={content}'
            # resolve non-absolute path against project root
            if not os.path.isabs(path):
                folders = window.folders()
                project_root = folders[0] if folders else os.getcwd()
                path = os.path.join(project_root, path)
            # open or find the file view
            if create:
                view = window.open_file(path)
            else:
                view = window.find_open_file(path) or window.open_file(path)
            if not view:
                return f'File under path not found: {path}'
            # replace entire content
            region = Region(0, view.size())
            view.run_command(
                'replace_region',
                {'region': {'a': region.begin(), 'b': region.end()}, 'text': content},
            )
            text = view.substr(region)
            return dumps({'result': text})

        elif func_name == Function.read_region_content.value:
            path = args_json.get('file_path')
            region = args_json.get('region')
            if not (isinstance(path, str) and isinstance(region, Dict)):
                return f'Wrong attributes passed: file_path={path}, region={region}'
            # resolve non-absolute path against project root
            if not os.path.isabs(path):
                folders = window.folders()
                project_root = folders[0] if folders else os.getcwd()
                path = os.path.join(project_root, path)
            # open or find view
            view = window.find_open_file(path) or window.open_file(path)
            if not view:
                return f'File under path not found: {path}'
            # extract region
            a_reg = region.get('a') if region.get('a') != -1 else 0
            b_reg = region.get('b') if region.get('b') != -1 else view.size()
            region_ = Region(a=a_reg, b=b_reg)
            text = view.substr(region_)
            return dumps({'content': text})

        elif func_name == Function.get_working_directory_content.value:
            path = args_json.get('directory_path')
            logger.debug('initial directory_path: %s', path)
            # Determine base directory: use provided path, project root, or active view
            if not path or path in ('.', './'):
                folders = window.folders()
                if folders:
                    path = folders[0]
                else:
                    view = window.active_view()
                    filename = view.file_name() if view else None
                    if filename:
                        path = os.path.dirname(filename)
                    else:
                        path = os.getcwd()
            if path and isinstance(path, str):
                folder_structure = build_folder_structure(path)
                return dumps({'content': f'{folder_structure}'})
            return f'Wrong attributes passed: {path}'
        else:
            return f"Called function doen't exists: {func_name}"
