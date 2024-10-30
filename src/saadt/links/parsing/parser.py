import logging
import os
import pathlib
from collections.abc import Iterable
from typing import Any

from regex import regex

from saadt import pdf
from saadt.links.parsing import ParsedLink, ParsedPaper
from saadt.model import Paper
from saadt.util import mputils


class LinkParserWorker(mputils.BaseWorker[tuple[pathlib.Path, Paper], ParsedPaper]):
    def _find_link_location(self, text: str, link: str, link_text: str) -> list[int]:
        """
        Tries to find the given link with link_text in the text.
        This will often produce incorrect/incomplete results.
        A better way would be to use the rectangle from Poppler.
        """

        # check if the link_text is actually just the link
        is_link = link_text in link or link in link_text
        if len(link_text) > 2 * len(link):
            # issues with whole paragraphs as link_text
            link_text = link

        if is_link:
            errs = max(round(len(link) * 0.03), 1)
            pattern = regex.compile(f"({regex.escape(link)}){{e<={errs}:\n}}")
            matches = list(m.start(1) for m in pattern.finditer(text))

            if len(matches) > 0:
                return matches

        errs = max(round(len(link_text) * 0.03), 1)
        pattern = regex.compile(f"({regex.escape(link_text)}){{e<={errs}:\n}}")

        # only search for a single match. Finding strings like "Google Drive" is a mess,
        # so this is likely to fail anyway
        match = pattern.search(text)

        if match is not None:
            if link.startswith(link_text):
                substr = text[match.start(1) :].split(maxsplit=1)[0]
                if not link.startswith(substr[: len(link)]):
                    return []

            return [match.start(1)]

        return []

    def _open_doc(self, path: str) -> pdf.Document:
        return pdf.Document.new(path, pdf.parser.CoordinateParser())

    def process_item(self, item: tuple[pathlib.Path, Paper]) -> ParsedPaper | None:
        path, paper = item
        self.logger.info("Processing paper %s from %s", paper.title, path)

        doc = self._open_doc(str(path.absolute()))

        links = list[ParsedLink]()
        for page in doc.iter_pages():
            if self.stop_event.is_set():
                break

            page_links = dict[str, ParsedLink]()

            logging.debug("Parsing text, paper=%s, page=%d", paper.title, page.index)
            try:
                text = page.text()
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                self.logger.error(f"Unexpected error while parsing text. page={page.index}, paper={paper.title}: {exc}")
                self.logger.debug("Traceback:", exc_info=exc)
                continue

            logging.debug("Parsing links: paper=%s, page=%d", paper.title, page.index)
            for uri, uri_texts in page.uris_with_text().items():
                locs = set()

                if uri not in page_links:
                    for uri_text in uri_texts:
                        locs.update(self._find_link_location(text, uri, uri_text))

                page_links.setdefault(
                    uri, ParsedLink(uri, sorted(locs), 0, page.index, len(text), True)
                ).occurrences += max(len(locs), 1)

            for link, locs in pdf.parse_links_from_text(text).items():
                sl = page_links.get(link)
                if sl is None:
                    sl = ParsedLink(link, sorted(locs), 0, page.index, len(text), False)

                locs.update(sl.locations)
                sl.locations = sorted(locs)
                sl.occurrences = 0
                sl.occurrences += len(locs)
                page_links[link] = sl

            links.extend(page_links.values())

        result = ParsedPaper.from_paper(paper, list(links), doc.pages)
        self.logger.debug("Finished processing %s", paper.title)
        return result


class LinkParser(mputils.ProcessExecutor[tuple[pathlib.Path, Paper], ParsedPaper]):
    def __init__(self, papers: list[tuple[pathlib.Path, Paper]], max_workers: int | None = None) -> None:
        # Heavily compute based, so few threads.
        super().__init__(max_workers=max_workers or max(1, (os.cpu_count() or 4) - 2), max_threads=1)

        self.papers = papers

    def _prepare_items(self) -> Iterable[tuple[pathlib.Path, Paper]]:
        yield from self.papers

    def _get_worker_args(self, i: int) -> Iterable[Any]:
        return ()

    @classmethod
    def _worker(cls, *args: Any, **kwargs: Any) -> LinkParserWorker:
        return LinkParserWorker(*args, **kwargs)
