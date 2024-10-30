from .middleware import Middleware as Middleware
from bibtexparser.middlewares import ResolveStringReferencesMiddleware as ResolveStringReferencesMiddleware
from bibtexparser.middlewares.enclosing import (
    AddEnclosingMiddleware as AddEnclosingMiddleware,
    RemoveEnclosingMiddleware as RemoveEnclosingMiddleware,
)
from typing import List

def default_parse_stack(allow_inplace_modification: bool = True) -> List[Middleware]: ...
def default_unparse_stack(allow_inplace_modification: bool = False) -> List[Middleware]: ...
