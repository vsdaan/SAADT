import abc

from bibtexparser.library import Library as Library
from bibtexparser.model import Block as Block
from bibtexparser.model import Entry as Entry
from bibtexparser.model import String as String
from pylatexenc.latex2text import LatexNodes2Text  # type: ignore[import-untyped]
from pylatexenc.latexencode import UnicodeToLatexEncoder  # type: ignore[import-untyped]

from .middleware import BlockMiddleware as BlockMiddleware

class _PyStringTransformerMiddleware(BlockMiddleware, abc.ABC, metaclass=abc.ABCMeta):
    def transform_entry(self, entry: Entry, library: Library) -> Block: ...
    def transform_string(self, string: String, library: Library) -> Block: ...

class LatexEncodingMiddleware(_PyStringTransformerMiddleware):
    def __init__(
        self,
        keep_math: bool | None = None,
        enclose_urls: bool | None = None,
        encoder: UnicodeToLatexEncoder | None = None,
        allow_inplace_modification: bool = True,
    ) -> None: ...
    @classmethod
    def metadata_key(cls) -> str: ...

class LatexDecodingMiddleware(_PyStringTransformerMiddleware):
    def __init__(
        self,
        allow_inplace_modification: bool = True,
        keep_braced_groups: bool | None = None,
        keep_math_mode: bool | None = None,
        decoder: LatexNodes2Text | None = None,
    ) -> None: ...
    @classmethod
    def metadata_key(cls) -> str: ...
