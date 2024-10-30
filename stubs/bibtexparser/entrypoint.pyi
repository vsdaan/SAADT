from .library import Library as Library
from .middlewares.middleware import Middleware as Middleware
from .middlewares.parsestack import (
    default_parse_stack as default_parse_stack,
    default_unparse_stack as default_unparse_stack,
)
from .splitter import Splitter as Splitter
from .writer import BibtexFormat as BibtexFormat, write as write
from typing import Iterable, TextIO

def parse_string(
    bibtex_str: str,
    parse_stack: Iterable[Middleware] | None = None,
    append_middleware: Iterable[Middleware] | None = None,
    library: Library | None = None,
) -> Library: ...
def parse_file(
    path: str,
    parse_stack: Iterable[Middleware] | None = None,
    append_middleware: Iterable[Middleware] | None = None,
    encoding: str = "UTF-8",
) -> Library: ...
def write_file(
    file: str | TextIO,
    library: Library,
    parse_stack: Iterable[Middleware] | None = None,
    append_middleware: Iterable[Middleware] | None = None,
    bibtex_format: BibtexFormat | None = None,
) -> None: ...
def write_string(
    library: Library,
    unparse_stack: Iterable[Middleware] | None = None,
    prepend_middleware: Iterable[Middleware] | None = None,
    bibtex_format: BibtexFormat | None = None,
) -> str: ...
