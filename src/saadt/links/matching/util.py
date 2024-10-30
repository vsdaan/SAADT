import pathlib
import re
from collections.abc import Iterator
from typing import override

_RE_README = re.compile(r"""README(?:\.[a-z]+)?""", re.I)
"""
Regex to detect README by path.
 
Case insensitive because people are people...
"""


def find_readme(paths: list[str]) -> Iterator[pathlib.PurePath]:
    path_list = [_SortablePath(p) for p in paths]
    path_list.sort()

    for path in path_list:
        if _RE_README.fullmatch(path.name) is not None:
            yield path


class _SortablePath(pathlib.PurePath):
    @override
    def __lt__(self, other: pathlib.PurePath) -> bool:
        # Use _tail for performance reasons
        if len(self._tail) != len(other._tail):  # type: ignore[attr-defined]
            return len(self._tail) < len(other._tail)  # type: ignore[attr-defined]

        if self.suffix == "" or other.suffix == "":
            return self.suffix != ""

        return super().__lt__(other)


def find_paper_reference(paper: str, content: str) -> None:
    # Find reference to title?
    title: str = paper
    subtitle: str | None = None
    if ":" in paper:
        title, subtitle = paper.split(":", 1)

    title = title.strip()
    subtitle = subtitle.strip() if subtitle else None

    print(subtitle)
