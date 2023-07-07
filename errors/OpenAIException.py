from sublime import error_message
from logging import exception

class OpenAIException(Exception):
    """Exception raised for errors in the input.

    Attributes:
        message -- explanation of the error
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)

class ContextLengthExceededException(OpenAIException): ...

class UnknownException(OpenAIException): ...


def present_error(title: str, error: OpenAIException):
    exception(f"{title}: {error.message}")
    error_message(f"{title}\n{error.message}")