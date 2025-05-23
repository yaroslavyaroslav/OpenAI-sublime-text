from __future__ import annotations

import logging
import os
from enum import Enum
from json import dumps, loads
from typing import Dict, List, Tuple

from sublime import Region, Window

from .project_structure import get_ignored_files

logger = logging.getLogger(__name__)


class Function(str, Enum):
    apply_patch = 'apply_patch'
    replace_text_for_whole_file = 'replace_text_for_whole_file'
    read_region_content = 'read_region_content'
    get_working_directory_content = 'get_working_directory_content'


def _extract_patch_blocks(patch_text: str) -> List[Tuple[str, str]]:
    """Return list of (normalized_diff, file_path) for each *** Begin Patch block"""
    lines = patch_text.splitlines()
    i = 0
    blocks: List[Tuple[str, str]] = []

    while i < len(lines):
        # look for a new block
        if not lines[i].startswith('*** Begin Patch'):
            i += 1
            continue

        i += 1  # skip Begin Patch
        diff_lines: List[str] = []
        file_path: str | None = None

        while i < len(lines) and not lines[i].startswith('*** End Patch'):
            line = lines[i]
            if line.startswith('*** Update File:'):
                file_path = line[len('*** Update File:') :].strip()
                diff_lines.append(f'--- a/{file_path}')
                diff_lines.append(f'+++ b/{file_path}')
            else:
                diff_lines.append(line)
            i += 1

        # skip the End Patch line
        while i < len(lines) and not lines[i].startswith('*** End Patch'):
            i += 1
        if i < len(lines):
            i += 1  # move past End Patch

        if not file_path:
            raise ValueError('No "*** Update File:" line found between markers.')

        blocks.append(('\n'.join(diff_lines) + '\n', file_path))

    if not blocks:
        raise ValueError('No patch blocks found.')

    return blocks


# ---------------------------------------------------------------------------
# New robust (model-style) diff parser & applier
# ---------------------------------------------------------------------------


def _parse_model_patch(diff: str) -> List[Tuple[str, str]]:
    """Parse a *very* restricted patch produced by the model.

    Rules:
        • No @@/index/Hunk headers – only raw -/+ lines.
        • Each hunk starts with ≥1 lines beginning with '-'. These lines form
          the *context* to locate in the file.
        • Optional consecutive '+' lines that immediately follow the '-' block
          make the replacement. If there are no '+', it is pure deletion.
        • Hunks are separated by at least one non-prefixed line (blank or any
          other text) **or** by a change of prefix (e.g., previous hunk’s +
          block ended and we encounter the next '-').
    Returns
        List of tuples: [(old_block, new_block), ...]
    """

    lines = diff.splitlines()
    i = 0
    hunks: List[Tuple[str, str]] = []

    while i < len(lines):
        # Locate the first '-' line which is NOT a file header ('--- a/file')
        if lines[i].startswith('-') and not lines[i].startswith('---'):
            old_block_lines: List[str] = []
            new_block_lines: List[str] = []

            # 1. Gather all consecutive '-' lines
            while i < len(lines) and lines[i].startswith('-') and not lines[i].startswith('---'):
                old_block_lines.append(lines[i][1:])  # strip prefix, preserve indentation
                i += 1

            # 2. Gather all consecutive '+' lines right after the '-'-block
            while i < len(lines) and lines[i].startswith('+') and not lines[i].startswith('+++'):
                new_block_lines.append(lines[i][1:])
                i += 1

            old_hunk = '\n'.join(old_block_lines) + '\n'
            new_hunk = ('\n'.join(new_block_lines) + '\n') if new_block_lines else ''

            if not old_block_lines:
                raise ValueError('Hunk without context (no "-" lines) encountered')

            hunks.append((old_hunk, new_hunk))
        else:
            i += 1

    if not hunks:
        raise ValueError('No hunks found – patch body is empty or mis-formatted')

    return hunks


def _apply_hunks_sequentially(original: str, hunks: List[Tuple[str, str]]) -> str:
    """
    Apply hunks **in order**; match each old-block by ignoring leading whitespace.
    Replace the first matching occurrence of each old block in the file.
    Raises RuntimeError if a hunk cannot be located.
    """
    # Split original text into lines with endings
    orig_lines = original.splitlines(keepends=True)

    for idx, (old, new) in enumerate(hunks, start=1):
        # Old/new blocks as lists of lines (with endings)
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True) if new else []

        # If old block is empty, append new lines at EOF
        if not old_lines or (len(old_lines) == 1 and old_lines[0] == '\n'):
            orig_lines.extend(new_lines)
            continue

        # Search for first position where stripped lines match
        found = False
        for i in range(len(orig_lines) - len(old_lines) + 1):
            match = True
            for j, old_line in enumerate(old_lines):
                # Compare ignoring leading whitespace
                if orig_lines[i + j].lstrip() != old_line.lstrip():
                    match = False
                    break
            if match:
                # Replace these lines
                orig_lines = orig_lines[:i] + new_lines + orig_lines[i + len(old_lines) :]
                found = True
                break

        if not found:
            snippet = old_lines[0].lstrip() or '<newline>'
            raise RuntimeError(
                f'Hunk {idx}: context not found – failed to locate "{snippet.strip()}..." in target file'
            )

    # Reconstruct updated text
    return ''.join(orig_lines)


# ---------------------------------------------------------------------------
# (Legacy) keep the old simple parser for backward-compatibility, use it as
# fallback when the strict parser fails.
# ---------------------------------------------------------------------------


def _parse_simple_patch(diff: str) -> List[Tuple[str, str]]:
    """Very loose parser kept as fallback for older patches."""

    lines = diff.splitlines()
    i = 0
    hunks: List[Tuple[str, str]] = []

    while i < len(lines):
        if lines[i].startswith('-') and not lines[i].startswith('---'):
            old_block_lines: List[str] = []
            while i < len(lines) and lines[i].startswith('-') and not lines[i].startswith('---'):
                old_block_lines.append(lines[i][1:])
                i += 1

            new_block_lines: List[str] = []
            while i < len(lines) and lines[i].startswith('+') and not lines[i].startswith('+++'):
                new_block_lines.append(lines[i][1:])
                i += 1

            old_text = '\n'.join(old_block_lines) + '\n'
            new_text = ('\n'.join(new_block_lines) + '\n') if new_block_lines else ''
            hunks.append((old_text, new_text))
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
                blocks = _extract_patch_blocks(patch_text)
            except Exception as e:
                return (
                    'Failed to parse patch header. Make sure your patch includes the markers and file path: \n'
                    '*** Begin Patch\n'
                    '*** Update File: /path/to/your/file\n'
                    '*** End Patch\n'
                    f'Parsing error: {e}'
                )

            for normalized_diff, path in blocks:
                # If path is not absolute, treat it as relative to project root
                if not os.path.isabs(path):
                    folders = window.folders()
                    project_root = folders[0] if folders else os.getcwd()
                    path = os.path.join(project_root, path)

                # ---------------------------------------------------------------
                # 1) Read original file content (fail early if file absent)
                # ---------------------------------------------------------------
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        original = f.read()
                except FileNotFoundError:
                    return f'File not found: {path}'
                except Exception as e:
                    return f'Unable to read {path}: {e}'

                # ---------------------------------------------------------------
                # 2) Parse & apply with strict model-style diff first
                # ---------------------------------------------------------------
                new_content: str | None = None
                strict_err: Exception | None = None

                try:
                    hunks = _parse_model_patch(normalized_diff)
                    new_content = _apply_hunks_sequentially(original, hunks)
                except Exception as e:
                    strict_err = e

                # Already-applied shortcut
                if strict_err:
                    try:
                        simple_hunks = _parse_simple_patch(normalized_diff)
                        applied_all = True
                        for old_hunk, new_hunk in simple_hunks:
                            old_str = old_hunk.strip('\n')
                            new_str = new_hunk.strip('\n')

                            if not new_str:
                                continue  # pure deletion, ignore

                            # New part is present and old part is gone?
                            if new_str in original and (not old_str or old_str not in original):
                                continue

                            applied_all = False
                            break

                        if applied_all:
                            continue  # block already applied, skip write
                    except Exception:
                        pass

                if new_content is None:
                    try:
                        hunks = _parse_simple_patch(normalized_diff)
                        if not hunks:
                            return (
                                'Patch parse failed – no hunks detected.\n'
                                'Ensure each change block starts with one or more "-" lines\n'
                                'and the patch is wrapped between *** Begin Patch / *** End Patch.'
                            )
                        new_content = _apply_hunks_sequentially(original, hunks)
                    except Exception as legacy_err:
                        return (
                            f'Strict parser error: {strict_err}.\nFallback parser also failed: {legacy_err}'
                        )

                # 3) Check no change
                if new_content == original:
                    continue  # nothing changed for this file

                # 4) Write back
                try:
                    with open(path, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                except PermissionError as e:
                    return f'Permission denied when writing to {path}: {e}'
                except Exception as e:
                    return f'Failed to write changes to {path}: {e}'

            return 'Done!'

        # -------------------------------------------------------------------
        # replace_text_for_whole_file – simple file write
        elif func_name == Function.replace_text_for_whole_file.value:
            path = args_json.get('file_path')
            create = args_json.get('create')
            content = args_json.get('content')

            if not (isinstance(path, str) and isinstance(content, str) and isinstance(create, bool)):
                return 'Wrong attributes passed: file_path(str), create(bool), content(str) required'

            # Resolve path relative to project root
            if not os.path.isabs(path):
                project_root = window.folders()[0] if window.folders() else os.getcwd()
                path = os.path.join(project_root, path)

            # Create parent dirs if needed
            if create:
                parent = os.path.dirname(path)
                if parent and not os.path.exists(parent):
                    try:
                        os.makedirs(parent, exist_ok=True)
                    except Exception as e:
                        return f'Failed to create directory: {e}'

            # Write file to disk
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(content)
            except Exception as e:
                return f'Failed to write file: {e}'

            return 'Done!'

        elif func_name == Function.read_region_content.value:
            path = args_json.get('file_path')
            region = args_json.get('region')
            if not (isinstance(path, str) and isinstance(region, Dict)):
                return f'Wrong attributes passed: file_path={path}, region={region}'

            # Resolve non-absolute path against project root
            if not os.path.isabs(path):
                folders = window.folders()
                project_root = folders[0] if folders else os.getcwd()
                path = os.path.join(project_root, path)

            # Open or find the view
            view = window.find_open_file(path) or window.open_file(path)
            if not view:
                return f'File under path not found: {path}'

            # Determine line indices (0-based; -1 means start/end)
            a_val = region.get('a')
            a_line = a_val if isinstance(a_val, int) and a_val != -1 else 0

            all_lines = view.lines(Region(0, view.size()))
            total = len(all_lines)

            b_val = region.get('b')
            b_line = b_val if isinstance(b_val, int) and b_val != -1 else total

            # Clamp to valid range, inclusive upper bound
            a_line = max(0, min(a_line, total))
            b_line = max(0, min(b_line, total - 1))

            if a_line > b_line:
                return dumps({'content': ''})

            # Slice is exclusive on end, so include b_line
            selected = all_lines[a_line : b_line + 1]

            # Join line contents with newline separators
            lines = [view.substr(r) for r in selected]
            text = '\n'.join(lines)

            return dumps(
                {
                    'content': text[:5000]
                    + (f'…[truncated] response is too long: {len(text)}' if len(text) > 5000 else '')
                }
            )

        elif func_name == Function.get_working_directory_content.value:
            path = args_json.get('directory_path')
            logger.debug('initial directory_path: %s', path)

            # 1. establish project root (first folder or cwd)
            folders = window.folders()
            project_root = folders[0] if folders else os.getcwd()

            # 2. resolve the directory_path argument
            if not path or path in ('.', './'):
                path = project_root
            elif not os.path.isabs(path):
                # treat as relative to project root
                path = os.path.join(project_root, path)

            if not isinstance(path, str):
                return f'Wrong attributes passed: directory_path={path}'

            if not os.path.exists(path):
                return f'Directory not found: {path}'

            # Recursively list like `ls -R`, respecting .gitignore
            output_lines: List[str] = []
            # Top-level directory: use "." as ls -R does
            items = os.listdir(path)
            if '.git' in items:
                items.remove('.git')
            ignored = get_ignored_files(items, path)
            visible = sorted([i for i in items if i not in ignored])
            output_lines.append('.:')
            if visible:
                output_lines.append(' '.join(visible))
            output_lines.append('')

            # Recurse into subdirectories
            for root, dirs, files in os.walk(path):
                # always skip `.git` directory from traversal
                if '.git' in dirs:
                    dirs.remove('.git')
                rel = os.path.relpath(root, path)
                if rel == '.':
                    continue

                # filter ignored entries
                rel_paths = [os.path.relpath(os.path.join(root, name), path) for name in dirs + files]
                ignored = get_ignored_files(rel_paths, path)

                entries: List[str] = []
                for name in sorted(dirs):
                    relp = os.path.relpath(os.path.join(root, name), path)
                    if relp in ignored:
                        continue
                    entries.append(name)
                for name in sorted(files):
                    relp = os.path.relpath(os.path.join(root, name), path)
                    if relp in ignored:
                        continue
                    entries.append(name)

                output_lines.append(f'./{rel}:')
                if entries:
                    output_lines.append(' '.join(entries))
                output_lines.append('')

            content_text = '\n'.join(output_lines).rstrip('\n')
            # apply same 5k char limit
            return dumps(
                {
                    'content': content_text[:5000]
                    + (
                        f'…[truncated] response is too long: {len(content_text)}'
                        if len(content_text) > 5000
                        else ''
                    )
                }
            )
        else:
            return f"Called function doen't exists: {func_name}"


# ---------------------------------------------------------------------------
# Command-line tester
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    """Run any plugin function from the terminal.

    Syntax:
        python -m plugins.function_handler <function_name> '<json-args>'

    Examples:
        # apply a two-hunk patch to this file
        python -m plugins.function_handler apply_patch '{"patch": "*** Begin Patch\\n*** Update File: plugins/function_handler.py\\n@@\\n+# injected hunk 1\\n@@\\n+# injected hunk 2\\n*** End Patch"}'

        # read first 5 lines of this file
        python -m plugins.function_handler read_region_content '{"file_path": "plugins/function_handler.py", "region": {"a": 0, "b": 4}}'

        # list working directory tree (honours .gitignore)
        python -m plugins.function_handler get_working_directory_content '{"directory_path": "."}'

        # overwrite /tmp/demo.txt
        echo hello > /tmp/demo.txt
        python -m plugins.function_handler replace_text_for_whole_file '{"file_path": "/tmp/demo.txt", "create": false, "content": "new text"}'
    """
    import sys
    import json
    from pathlib import Path

    if len(sys.argv) < 3:
        print('Usage: python -m plugins.function_handler <function_name> <json-args>')
        sys.exit(1)

    func = sys.argv[1]
    raw = ' '.join(sys.argv[2:])
    try:
        json.loads(raw)
        args_json = raw
    except json.JSONDecodeError:
        if func == Function.apply_patch.value:
            args_json = json.dumps({'patch': raw})
        else:
            print('arguments must be JSON')
            sys.exit(2)

    class _View:
        def size(self):
            return 0

    class _Window:
        def folders(self):
            return [str(Path.cwd())]

        def open_file(self, _p):
            return _View()

        def find_open_file(self, _p):
            return None

    result = FunctionHandler.perform_function(func, args_json, _Window())
    print(result)
