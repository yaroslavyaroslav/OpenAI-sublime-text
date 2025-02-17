from logging import exception

from sublime import error_message


class AssException(Exception):
    """Exception raised for errors in the input.

    Attributes:
        message -- explanation of the error
    """

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class ContextLengthExceededException(AssException): ...


class UnknownException(AssException): ...


class WrongUserInputException(AssException): ...


class FunctionCallFailedException(AssException): ...


def present_error(title: str, error: AssException):
    exception(f'{title}: {error.message}')
    error_message(f'{title}\n{error.message}')


def present_error_str(title: str, error: str):
    exception(f'{title}: {error}')
    error_message(f'{title}\n{error}')


def present_unknown_error(title: str, error: Exception):
    exception(f'{title}: {error}')
    error_message(f'{title}\n{error}')
