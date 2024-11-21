import os
import json
import fnmatch
import sublime


def parse_gitignore(path):
    """Parse the .gitignore file to create a list of ignore patterns."""
    gitignore_paths = [os.path.join(path, '.gitignore'), os.path.join('~', '.gitignore_global')]
    ignore_patterns = []

    for gitignore_path in gitignore_paths:
        if os.path.isfile(gitignore_path):
            with open(gitignore_path, 'r') as file:
                ignore_patterns = [
                    line.strip() for line in file.readlines() if line.strip() and not line.startswith('#')
                ]

    ignore_patterns.append('.git')
    return ignore_patterns


def is_ignored(item, ignore_patterns):
    """Check if an item matches any pattern in the ignore list."""
    for pattern in ignore_patterns:
        if fnmatch.fnmatch(item, pattern):
            return True
    return False


def build_folder_structure_(path, ignore_patterns):
    """Recursively build a folder structure, ignoring files in .gitignore."""
    folder_structure = {'name': os.path.basename(path), 'children': []}

    try:
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            if is_ignored(item, ignore_patterns):
                continue  # Skip ignored items

            if os.path.isdir(item_path):
                # If the item is a directory, call the function recursively
                folder_structure['children'].append(build_folder_structure_(item_path, ignore_patterns))
            else:
                # If the item is a file, append it to children as well
                folder_structure['children'].append({'name': item, 'children': []})
    except PermissionError:
        # Handle situation where we do not have permission to access a folder
        folder_structure['children'].append({'name': 'Access Denied', 'children': []})

    return folder_structure


def build_folder_structure(path: str) -> str:
    """Convert a folder structure to JSON format."""
    ignore_patterns = parse_gitignore(path)
    if path == '.':
        window = sublime.active_window()

        project_data = window.project_data()

        if project_data:
            path = window.folders()[0]

    folder_structure = build_folder_structure_(path, ignore_patterns)
    return json.dumps(folder_structure, indent=4)


# Example usage
if __name__ == '__main__':
    root_path = input('Enter the path to the root folder: ')
    folder_json = build_folder_structure(root_path)
    print(folder_json)
