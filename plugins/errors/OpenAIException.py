from logging import exception

from sublime import error_message


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


class WrongUserInputException(OpenAIException): ...


class FunctionCallFailedException(OpenAIException): ...


def present_error(title: str, error: OpenAIException):
    exception(f'{title}: {error.message}')
    error_message(f'{title}\n{error.message}')


def present_unknown_error(title: str, error: Exception):
    exception(f'{title}: {error}')
    error_message(f'{title}\n{error}')
