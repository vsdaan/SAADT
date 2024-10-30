from .enclosing import REMOVED_ENCLOSING_KEY as REMOVED_ENCLOSING_KEY
from .middleware import LibraryMiddleware as LibraryMiddleware
from bibtexparser.library import Library as Library
from bibtexparser.model import Entry as Entry, Field as Field

class ResolveStringReferencesMiddleware(LibraryMiddleware):
    def __init__(self, allow_inplace_modification: bool = True) -> None: ...
    @classmethod
    def metadata_key(cls) -> str: ...
    def transform(self, library: Library) -> Library: ...
