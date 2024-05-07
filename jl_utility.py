import json
from typing import Iterator, Generator

def reader(fname: str) -> Iterator[dict]:
    with open(fname) as file:
        for line in file:
            obj = json.loads(line.strip())
            yield obj


def writer(fname: str, mode: str = 'a') -> Generator[None, dict, None]:
    with open(fname, mode) as file:
        while True:
            obj = yield
            line = json.dumps(obj, ensure_ascii=False)
            file.write(f"{line}\n")
