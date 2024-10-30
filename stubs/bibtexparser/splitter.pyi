from .exceptions import (
    BlockAbortedException as BlockAbortedException,
    ParserStateException as ParserStateException,
    RegexMismatchException as RegexMismatchException,
)
from .library import Library as Library
from .model import (
    DuplicateFieldKeyBlock as DuplicateFieldKeyBlock,
    Entry as Entry,
    ExplicitComment as ExplicitComment,
    Field as Field,
    ImplicitComment as ImplicitComment,
    ParsingFailedBlock as ParsingFailedBlock,
    Preamble as Preamble,
    String as String,
)
from _typeshed import Incomplete

class Splitter:
    bibstr: Incomplete
    def __init__(self, bibstr: str) -> None: ...
    def split(self, library: Library | None = None) -> Library: ...
