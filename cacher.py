import sublime
import os
from . import jl_utility as jl


class Cacher():
    def __init__(self) -> None:
        cache_dir = sublime.cache_path()
        plugin_cache_dir = os.path.join(cache_dir, "OpenAI completion")
        if not os.path.exists(plugin_cache_dir):
            os.makedirs(plugin_cache_dir)

        # Create the file path to store the data
        self.cache_file = os.path.join(plugin_cache_dir, "chat_history.jl")


    def read_all(self):
        json_objects = []
        reader = jl.reader(self.cache_file)
        for json_object in reader:
            json_objects.append(json_object)

        return json_objects

    def append_to_cache(self, cache_lines):
        # Create a new JSON Lines writer for output.jl
        writer = jl.writer(self.cache_file)
        next(writer)
        writer.send(cache_lines[0])
        # for line in cache_lines:
        #     writer.send(line)

    def drop_first(self, number = 4):
        # Read all lines from the JSON Lines file
        with open(self.cache_file, "r") as file:
            lines = file.readlines()

        # Remove the specified number of lines from the beginning
        lines = lines[number:]

        # Write the remaining lines back to the cache file
        with open(self.cache_file, "w") as file:
            file.writelines(lines)

    def drop_all(self):
        with open(self.cache_file, "w") as file:
            pass # Truncate the file by opening it in 'w' mode and doing nothing
