import typing

from _typeshed import Incomplete
from bibtexparser.model import Entry as Entry
from bibtexparser.model import String as String

from .middleware import BlockMiddleware as BlockMiddleware

REMOVED_ENCLOSING_KEY: str
STRINGS_CAN_BE_UNESCAPED_INTS: bool
ENTRY_POTENTIALLY_INT_FIELDS: Incomplete

class RemoveEnclosingMiddleware(BlockMiddleware):
    def __init__(self, allow_inplace_modification: bool = True) -> None: ...
    @classmethod
    def metadata_key(cls) -> str: ...
    def transform_entry(self, entry: Entry, *_: typing.Any) -> Entry: ...
    def transform_string(self, string: String, *_: typing.Any) -> String: ...

class AddEnclosingMiddleware(BlockMiddleware):
    def __init__(
        self,
        reuse_previous_enclosing: bool,
        enclose_integers: bool,
        default_enclosing: str,
        allow_inplace_modification: bool = True,
    ) -> None: ...
    @classmethod
    def metadata_key(cls) -> str: ...
    def transform_entry(self, entry: Entry, *_: typing.Any) -> Entry: ...
    def transform_string(self, string: String, *_: typing.Any) -> String: ...
