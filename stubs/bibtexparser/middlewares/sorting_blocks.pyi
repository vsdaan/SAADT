from dataclasses import dataclass

from _typeshed import Incomplete
from bibtexparser.library import Library as Library
from bibtexparser.model import Block as Block

from .middleware import LibraryMiddleware as LibraryMiddleware

DEFAULT_BLOCK_TYPE_ORDER: Incomplete

@dataclass
class _BlockJunk:
    sort_key: str = ...
    blocks: list[Block] = ...

    @property
    def main_block_type(self) -> type: ...

class SortBlocksByTypeAndKeyMiddleware(LibraryMiddleware):
    def __init__(
        self, block_type_order: tuple[type[Block], ...] = ..., preserve_comments_on_top: bool = True
    ) -> None: ...
    def transform(self, library: Library) -> Library: ...
