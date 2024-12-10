from enum import Enum


class Function(str, Enum):
    replace_text_with_another_text = 'replace_text_with_another_text'
    replace_text_for_whole_file = 'replace_text_for_whole_file'
    read_region_content = 'read_region_content'
    get_working_directory_content = 'get_working_directory_content'


REPLACE_TEXT_WITH_ANOTHER_TEXT = {
    'type': 'function',
    'function': {
        'name': Function.replace_text_with_another_text.value,
        'description': 'Replace the existed text in the file with the new one',
        'parameters': {
            'type': 'object',
            'properties': {
                'file_path': {
                    'type': 'string',
                    'description': 'The path of the file where content to search is stored',
                },
                'old_content': {
                    'type': 'string',
                    'description': 'The existing old content to be replaced with new content',
                },
                'new_content': {
                    'type': 'string',
                    'description': 'The content to replace the old one',
                },
            },
            'required': ['file_path', 'old_content', 'new_content'],
            'additionalProperties': False,
        },
    },
}


REPLACE_TEXT_FOR_WHOLE_FILE = {
    'type': 'function',
    'function': {
        'name': Function.replace_text_for_whole_file.value,
        'description': 'Replace the content of a region with the content provided',
        'parameters': {
            'type': 'object',
            'properties': {
                'file_path': {
                    'type': 'string',
                    'description': 'The path of the file where content to search is stored',
                },
                'create': {
                    'type': 'boolean',
                    'description': "To create a new pane and file for it under a given path and with a given content. File created that way won't be visible by `get_working_directory_content` function call until user manually saves it",
                },
                'content': {
                    'type': 'string',
                    'description': 'The New content of the file',
                },
            },
            'required': ['file_path', 'content'],
            'additionalProperties': False,
        },
    },
}

READ_REGION_CONTENT = {
    'type': 'function',
    'function': {
        'name': Function.read_region_content.value,
        'description': 'Read the content of the particular region',
        'parameters': {
            'type': 'object',
            'properties': {
                'file_path': {
                    'type': 'string',
                    'description': 'The path of the file where content to search is stored',
                },
                'region': {
                    'type': 'object',
                    'description': 'The region in the file to read',
                    'properties': {
                        'a': {
                            'type': 'integer',
                            'description': 'The beginning point of the region to read, set -1 to read the file till the start',
                        },
                        'b': {
                            'type': 'integer',
                            'description': 'The ending point of the region to read, set -1 to read the file till the end',
                        },
                    },
                    'required': ['a', 'b'],
                    'additionalProperties': False,
                },
            },
            'required': ['file_path', 'region'],
            'additionalProperties': False,
        },
    },
}

GET_WORKING_DIRECTORY_CONTENT = {
    'type': 'function',
    'function': {
        'name': Function.get_working_directory_content.value,
        'description': 'Get complete structure of directories and files within the working directory, current dir is a working dir, i.e. `.` is the roor project',
        'parameters': {
            'type': 'object',
            'properties': {
                'directory_path': {
                    'type': 'string',
                    'description': 'The path of the directory where content to search is stored',
                },
            },
            'required': ['directory_path'],
            'additionalProperties': False,
        },
    },
}


FUNCTION_DATA = [
    REPLACE_TEXT_WITH_ANOTHER_TEXT,
    READ_REGION_CONTENT,
    GET_WORKING_DIRECTORY_CONTENT,
    REPLACE_TEXT_FOR_WHOLE_FILE,
]
