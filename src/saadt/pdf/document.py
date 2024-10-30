import logging
import pathlib
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

import gi
import requests
from urllib3.util import parse_url

from .page import Page
from .parser import Parser

gi.require_version("Poppler", "0.18")
from gi.repository import GLib, Poppler  # noqa: E402

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Document:
    _doc: Poppler.Document
    _parser: Parser

    @classmethod
    def new(cls, source: Sequence[int] | str | pathlib.Path, parser: Parser) -> "Document":
        if isinstance(source, str):
            url = parse_url(source)
            if url.scheme in ["http", "https"]:
                url_str = url.url
                log.debug(f"Creating document from url: {url_str}")
                return cls(cls._from_url(url_str), parser)
            else:
                log.debug(f"Creating document from path: {source}")
                return cls(Poppler.Document.new_from_file(f"file://{source}"), parser)
        elif isinstance(source, pathlib.Path):
            log.debug(f"Creating document from path: {source}")
            return cls(Poppler.Document.new_from_file(f"file://{source}"), parser)
        else:
            log.debug("Creating document from bytes")
            return cls(cls._from_bytes(source), parser)

    @staticmethod
    def _from_bytes(b: Sequence[int]) -> Poppler.Document:
        return Poppler.Document.new_from_bytes(GLib.Bytes.new(b))

    @staticmethod
    def _from_url(url: str) -> Poppler.Document:
        r = requests.get(url)
        r.raise_for_status()

        return Document._from_bytes(r.content)

    def page(self, i: int) -> Page:
        return Page(self._doc.get_page(i), self._parser)

    @property
    def pages(self) -> int:
        return self._doc.get_n_pages()

    def iter_pages(self) -> Iterator[Page]:
        for i in range(self.pages):
            yield self.page(i)

    def text(self) -> str:
        result = ""
        for page in self.iter_pages():
            result += page.text()
        return result

    def uris(self) -> list[str]:
        result = []
        for page in self.iter_pages():
            result.extend(page.uris())

        return result
