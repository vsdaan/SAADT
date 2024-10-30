import abc
import dataclasses
import typing
from typing import Literal

from _typeshed import Incomplete
from bibtexparser.model import Block as Block
from bibtexparser.model import Entry as Entry

from .middleware import BlockMiddleware as BlockMiddleware

class InvalidNameError(ValueError):
    def __init__(self, name: str, reason: str) -> None: ...

class _NameTransformerMiddleware(BlockMiddleware, abc.ABC, metaclass=abc.ABCMeta):
    def __init__(
        self, allow_inplace_modification: bool = True, name_fields: tuple[str, ...] = ("author", "editor", "translator")
    ) -> None: ...
    @property
    def name_fields(self) -> tuple[str]: ...
    def transform_entry(self, entry: Entry, *_: typing.Any) -> Block: ...

class SeparateCoAuthors(_NameTransformerMiddleware):
    @classmethod
    def metadata_key(cls) -> str: ...

class MergeCoAuthors(_NameTransformerMiddleware):
    @classmethod
    def metadata_key(cls) -> str: ...

@dataclasses.dataclass
class NameParts:
    first: list[str] = ...
    von: list[str] = ...
    last: list[str] = ...
    jr: list[str] = ...

    @property
    def merge_first_name_first(self) -> str: ...
    @property
    def merge_last_name_first(self) -> str: ...

class SplitNameParts(_NameTransformerMiddleware):
    @classmethod
    def metadata_key(cls) -> str: ...

class MergeNameParts(_NameTransformerMiddleware):
    style: Incomplete

    def __init__(
        self,
        style: Literal["last", "first"] = "last",
        allow_inplace_modification: bool = True,
        name_fields: tuple[str, ...] = ("author", "editor", "translator"),
    ) -> None: ...
    @classmethod
    def metadata_key(cls) -> str: ...

def parse_single_name_into_parts(name: str, strict: bool = True) -> NameParts: ...
def split_multiple_persons_names(names: str) -> list[str]: ...
