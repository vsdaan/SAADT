from collections import OrderedDict
from typing import TypeVar, override

_KT = TypeVar("_KT")
_VT = TypeVar("_VT")


class LRUCache(OrderedDict[_KT, _VT]):
    def __init__(self, maxsize: int = 128):
        super().__init__()
        self.maxsize = maxsize

    @override
    def __getitem__(self, key: _KT) -> _VT:
        value = super().__getitem__(key)
        self.move_to_end(key)
        return value

    @override
    def __setitem__(self, key: _KT, value: _VT) -> None:
        size = len(self)
        if key in self:
            self.move_to_end(key)
        else:
            size += 1

        if size > self.maxsize:
            self.popitem(last=False)

        super().__setitem__(key, value)
