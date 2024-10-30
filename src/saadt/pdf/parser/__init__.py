from abc import ABC, abstractmethod

import gi

gi.require_version("Poppler", "0.18")
from gi.repository import Poppler  # noqa: E402


class Parser(ABC):
    @abstractmethod
    def parse_page(self, page: Poppler.Page) -> str:
        raise NotImplementedError()


class SimpleParser(Parser):
    def parse_page(self, page: Poppler.Page) -> str:
        return page.get_text()


class CoordinateParser(Parser):
    def __init__(self, escape_sub_superscript: bool = True):
        self.escape_sub_superscript = escape_sub_superscript

    def parse_page(self, page: Poppler.Page) -> str:
        from ._coordinate import CoordinatePageParser

        parser = CoordinatePageParser(page, self.escape_sub_superscript)
        return parser.run()
