#!/usr/bin/env python3
import argparse
import dataclasses
import logging
import os
import pathlib
import re
import sys
from collections.abc import Iterable
from typing import Any

from saadt import pdf
from saadt.util import mputils, text_encoding
from saadt.util.log import get_logger


@dataclasses.dataclass(slots=True)
class ParseResult:
    title: str


class ParserWorker(mputils.BaseWorker[str, ParseResult]):
    re_escape = re.compile(r"\[|\]")
    re_special = re.compile(r"[^\x00-\x7f\w]")

    def process_item(self, file: str) -> ParseResult | None:
        self.logger.info("Processing file %s", file)

        path = pathlib.Path(file)
        doc = pdf.Document.new(str(path.absolute()), pdf.parser.CoordinateParser())

        text = doc.page(0).text()
        # print(text)
        # return

        lines = text.splitlines()
        title = lines.pop(1).strip()
        for i in range(len(lines)):
            if i == 3:  # title of 4 lines is long enough...
                break
            line = lines.pop(0)
            if line == "":
                break
            title += f" {line.strip()}"

        # Remove special unicode stuff, but keep non-ascii word characters
        title = self.re_escape.sub("", text_encoding.sanitize(title))

        return ParseResult(title)


class ParserManager(mputils.ProcessExecutor[str, ParseResult]):
    def __init__(self, files: list[str]) -> None:
        # Heavily compute based, so few threads.
        # super().__init__(max_workers=max(1, (os.cpu_count() or 4) - 2), max_threads=2)
        super().__init__(max_workers=14, max_threads=1)

        self.files = files

    def _prepare_items(self) -> Iterable[str]:
        return self.files

    def _get_worker_args(self, i: int) -> Iterable[Any]:
        return ()

    @classmethod
    def _worker(cls, *args: Any, **kwargs: Any) -> ParserWorker:
        return ParserWorker(*args, **kwargs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paper_dir", help="directory containing the pdfs to process")
    args = parser.parse_args()

    log = get_logger(logging.INFO)

    paper_dir = os.path.abspath(args.paper_dir)

    files = [
        os.path.join(paper_dir, file)
        for file in os.listdir(paper_dir)
        if file.endswith(".pdf") and "_appendix" not in file
    ]

    manager = ParserManager(files)
    result = manager.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt as e:
        logging.info(f'{type(e).__name__}: {"Terminated."}')
        sys.exit(1)
