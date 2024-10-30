#!/usr/bin/env python3
import argparse
import json
import logging
import sys
from collections.abc import Iterable
from typing import Any, Unpack

from _model import parse_links_file

from saadt.links.validation.eventdispatcher import EventDispatcher
from saadt.links.validation.events import ValidatorEvents
from saadt.links.parsing import ParsedPaper
from saadt.links.validation import constraints, validator, listeners
from saadt.util import mputils
from saadt.util.log import LoggerInterface, get_logger
from saadt.util.mputils import WorkerParams
from saadt.util.session import create_session

_TD = ParsedPaper
_TF = tuple[str, dict[str, list[tuple[str, str | None]]]]


def register_listeners(disp: EventDispatcher, logger: LoggerInterface) -> None:
    disp.register(ValidatorEvents.PARSE, listeners.ResolveDOI(), 0)
    disp.register(ValidatorEvents.PARSE, listeners.TransformGithub(), -10)
    disp.register(ValidatorEvents.VALIDATE, listeners.ConstraintListener(constraints.HostExists()), 10)
    disp.register(
        ValidatorEvents.VALIDATE, listeners.RawURLConstraintListener(constraints.ProbablyJoinedSentence()), 100
    )

    # Filter listeners
    disp.register(ValidatorEvents.FILTER, listeners.ConstraintListener(constraints.Duplicate()))
    disp.register(ValidatorEvents.FILTER, listeners.ConstraintListener(constraints.NotDomain("dl.acm.org")))
    disp.register(ValidatorEvents.FILTER, listeners.ConstraintListener(constraints.NotDomain("springer.com")))
    disp.register(ValidatorEvents.FILTER, listeners.ConstraintListener(constraints.NotDomain("arxiv.org")))
    disp.register(ValidatorEvents.FILTER, listeners.ConstraintListener(constraints.NotDomain("usenix.org")))
    disp.register(ValidatorEvents.FILTER, listeners.ConstraintListener(constraints.NotDomain("ieee.org")))
    disp.register(ValidatorEvents.RESPONSE, listeners.ConstraintListener(constraints.SigninPage()), 100)
    disp.register(ValidatorEvents.EXCEPTION, listeners.TracebackListener(logger))


class LinkValidatorWorker(mputils.BaseWorker[_TD, _TF]):
    def __init__(self, **kwargs: Unpack[WorkerParams[_TD, _TF]]):
        super().__init__(**kwargs)
        self.session = create_session(10, self.stop_event)
        headers = {"User-Agent": "ArtifactCrawler/1.0 (Crawling for academic research)"}
        self.urlvalidator = validator.UrlValidator(session=self.session, headers=headers)
        register_listeners(self.urlvalidator.dispatcher, self.logger)

    def process_item(self, item: _TD) -> _TF:
        paper = item
        self.logger.info("Processing paper %s", paper.title)
        links = [link.link for link in paper.links]
        validated_links = self.urlvalidator.run(links)
        self.logger.info(
            "Validated links: [functional=%d, errors=%d, invalid=%d], paper=%s",
            len(validated_links[validator.LinkState.FUNCTIONAL.value]),
            len(validated_links[validator.LinkState.INVALID.value]),
            len(validated_links[validator.LinkState.ERROR.value]),
            paper.title,
        )

        return paper.id(), validated_links


class LinkValidatorManager(mputils.ProcessExecutor[_TD, _TF]):
    def __init__(self, papers: list[_TD]) -> None:
        super().__init__(max_workers=2, max_threads=10)

        self.papers = papers

    def _prepare_items(self) -> Iterable[_TD]:
        yield from self.papers

    def _get_worker_args(self, i: int) -> Iterable[Any]:
        return ()

    @classmethod
    def _worker(cls, *args: Any, **kwargs: Any) -> LinkValidatorWorker:
        return LinkValidatorWorker(*args, **kwargs)


def process_papers(papers: list[ParsedPaper]) -> list[_TF]:
    manager = LinkValidatorManager(papers)
    result = manager.run()

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Conference paper link validator")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose operation")
    parser.add_argument("-q", "--quiet", action="store_true", default=0, help="Disable all logging")
    parser.add_argument("--debug", metavar="[debug file]", help="path to file for debug logging")
    parser.add_argument("links_file_path", metavar="[list.json file]", help="path to output of find_links.py")
    args = parser.parse_args()

    level = logging.INFO
    if args.verbose:
        level = logging.DEBUG
    if args.quiet:
        level = logging.ERROR
    log = get_logger(level, args.debug)

    links = parse_links_file(args.links_file_path)

    log.info(f"Processing {len(links)} papers")

    result = process_papers(links)
    d = []
    for paper_id, link_sets in result:
        result_links = []
        for status, link_set in link_sets.items():
            result_links.extend([{"link": link[0], "status": status, "reason": link[1]} for link in link_set])
        d.append({"id": paper_id, "links": result_links})
    json.dump(d, sys.stdout, indent=4)

    log.info("Finished")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt as e:
        logging.info(f'{type(e).__name__}: {"Terminated."}')
        sys.exit(1)
