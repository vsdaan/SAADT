from _typeshed import Incomplete

class ParsingException(Exception): ...

class BlockAbortedException(ParsingException):
    abort_reason: Incomplete
    end_index: Incomplete

    def __init__(self, abort_reason: str, end_index: int | None = None) -> None: ...

class ParserStateException(ParsingException):
    message: Incomplete

    def __init__(self, message: str) -> None: ...

class RegexMismatchException(ParserStateException):
    first_match: str
    expected_match: str
    second_match: str

    def __init__(self, first_match: str, expected_match: str, second_match: str) -> None: ...

class PartialMiddlewareException(ParsingException):
    def __init__(self, reasons: list[str]) -> None: ...
