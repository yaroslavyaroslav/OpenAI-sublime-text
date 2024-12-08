GET_REGION_FOR_TEXT = {
    'type': 'function',
    'function': {
        'name': 'get_region_for_text',
        'description': 'Get the Sublime Text Region bounds that is matching the content provided',
        'parameters': {
            'type': 'object',
            'properties': {
                'file_path': {
                    'type': 'string',
                    'description': 'The path of the file where content to search is stored',
                },
                'content': {
                    'type': 'string',
                    'description': 'Content bounds of which to search for',
                },
            },
            'required': ['file_path', 'content'],
            'additionalProperties': False,
        },
    },
}

REPLACE_TEXT_FOR_REGION = {
    'type': 'function',
    'function': {
        'name': 'replace_text_for_region',
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
                'region': {
                    'type': 'object',
                    'description': 'The region in the file to replace text',
                    'properties': {
                        'a': {
                            'type': 'integer',
                            'description': 'The beginning point of the region to be replaced',
                        },
                        'b': {
                            'type': 'integer',
                            'description': 'The ending point of the region to be replaced',
                        },
                    },
                    'required': ['a', 'b'],
                    'additionalProperties': False,
                },
                'content': {
                    'type': 'string',
                    'description': 'The content to replace in the specified region',
                },
            },
            'required': ['file_path', 'region', 'content'],
            'additionalProperties': False,
        },
    },
}

REPLACE_TEXT_FOR_WHOLE_FILE = {
    'type': 'function',
    'function': {
        'name': 'replace_text_for_whole_file',
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
        'name': 'read_region_content',
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
        'name': 'get_working_directory_content',
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
    GET_REGION_FOR_TEXT,
    REPLACE_TEXT_FOR_REGION,
    READ_REGION_CONTENT,
    GET_WORKING_DIRECTORY_CONTENT,
    REPLACE_TEXT_FOR_WHOLE_FILE,
]
