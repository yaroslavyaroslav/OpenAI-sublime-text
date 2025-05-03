import json
import os
import subprocess
from typing import List, Set


def get_ignored_files(relative_paths: List[str], base_path: str) -> Set[str]:
    """
    Runs git check-ignore in batch for the given relative paths.
    Returns a set of relative paths that are ignored.
    """
    if not relative_paths:
        return set()

    # Run git check-ignore on all files in one call.
    cmd = ['git', 'check-ignore'] + relative_paths
    try:
        result = subprocess.run(
            cmd,
            cwd=base_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except Exception:
        return set()

    ignored = set()
    if result.stdout:
        # Each line corresponds to a file that is ignored.
        for line in result.stdout.splitlines():
            ignored.add(line.strip())
    return ignored


def build_folder_structure_(path: str, base_path: str) -> dict:
    """
    Recursively builds a folder structure starting at 'path',
    skipping files or folders that Git ignores and excluding the .git folder.
    base_path: the root folder of the git repository.
    """
    folder_structure = {'name': os.path.basename(path), 'children': []}
    try:
        items = os.listdir(path)
        if not items:
            return folder_structure

        # Explicitly exclude the '.git' folder.
        if '.git' in items:
            items.remove('.git')

        # Create a mapping from item to its relative path from base_path.
        rel_paths = {item: os.path.relpath(os.path.join(path, item), base_path) for item in items}

        # Get the set of ignored relative paths for the current directory.
        ignored = get_ignored_files(list(rel_paths.values()), base_path)

        for item in items:
            if rel_paths[item] in ignored:
                continue

            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                folder_structure['children'].append(build_folder_structure_(item_path, base_path))
            else:
                folder_structure['children'].append({'name': item, 'children': []})
    except PermissionError:
        folder_structure['children'].append({'name': 'Access Denied', 'children': []})
    return folder_structure


def build_folder_structure(path: str) -> str:
    """
    Build and return a JSON representation of the folder structure.
    'path' should be the root of a Git repository.
    """
    folder_structure = build_folder_structure_(path, path)
    return json.dumps(folder_structure, indent=4)


# Example usage:
if __name__ == '__main__':
    root_path = input('Enter the path to the root folder: ')
    print(build_folder_structure(root_path))
