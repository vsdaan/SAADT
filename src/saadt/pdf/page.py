from dataclasses import dataclass
from typing import NamedTuple

import gi

from saadt.util.patterns import RE_WWW

from .parser import Parser

gi.require_version("Poppler", "0.18")
from gi.repository import Poppler  # noqa: E402


class _PageSize(NamedTuple):
    width: float
    height: float


@dataclass(frozen=True)
class Page:
    _page: Poppler.Page
    _parser: Parser

    @property
    def index(self) -> int:
        return self._page.get_index()

    @property
    def size(self) -> _PageSize:
        return _PageSize._make(self._page.get_size())

    def _invert_mapping_coords(self, mapping: Poppler.LinkMapping) -> Poppler.Rectangle:
        """
        Inverts the coordinates of the given LinkMapping.

        For some reason LinkMapping coordinates are PDF style instead of X style
        (like literally everything else in the Poppler GLib API).
        """
        area = mapping.area.copy()
        area.y1 = self.size.height - mapping.area.y2
        area.y2 = self.size.height - mapping.area.y1

        # Some margin to remove random bits of text
        height = area.y2 - area.y1
        area.x1 += height * 0.2
        area.x2 -= height * 0.2
        area.y1 += height * 0.2
        area.y2 -= height * 0.2

        return area

    def _get_uri_link_mapping(self) -> list[Poppler.LinkMapping]:
        result = []
        for mapping in self._page.get_link_mapping():
            if mapping.action.type == Poppler.ActionType.URI:
                result.append(mapping)

        return result

    def uris(self) -> list[str]:
        # dict to filter duplicates, but keep order
        result = dict[str, None]()

        for mapping in self._get_uri_link_mapping():
            # need this variable, otherwise the next line will crash
            action: Poppler.Action = mapping.action

            uri: str = action.uri.uri.strip()
            if RE_WWW.fullmatch(uri) is not None:
                result.setdefault(uri)

        return list(result.keys())

    def uris_with_text(self) -> dict[str, list[str]]:
        # dict to filter duplicates, but keep order
        result = dict[str, list[str]]()

        for mapping in self._get_uri_link_mapping():
            area = self._invert_mapping_coords(mapping)
            link_text = self._page.get_text_for_area(area)

            # need this variable, otherwise the next line will crash
            action: Poppler.Action = mapping.action
            uri: str = action.uri.uri.strip()
            if RE_WWW.fullmatch(uri) is not None:
                result.setdefault(uri, []).append(link_text)

        return result

    def text(self) -> str:
        return self._parser.parse_page(self._page)
