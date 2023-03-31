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


# if __name__ == "__main__":
#     # Read employees from employees.jl
#     reader = jl_reader("employees.jl")

#     # Create a new JSON Lines writer for output.jl
#     writer = jl_writer("output.jl")
#     next(writer)

#     for employee in reader:
#         id = employee["id"]
#         name = employee["name"]
#         dept = employee["department"]
#         print(f"#{id} - {name} ({dept})")

#         # Write the employee data to output.jl
#         writer.send(employee)

#     # Close the writer
#     writer.close()