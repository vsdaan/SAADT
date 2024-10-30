#!/usr/bin/env python3
import argparse
import dataclasses
import json
import logging
import os
import pathlib
import sys
from collections.abc import Iterable, Sequence
from typing import Any, Unpack, override

import requests
from _model import parse_links_file

from saadt.links import ranking
from saadt.links.parsing import ParsedLink, ParsedPaper
from saadt.links.ranking import RankedLink, rules
from saadt.util import mputils
from saadt.util.log import get_logger
from saadt.util.session import create_session

ignore_domains = [
    "dl.acm.org",
    "springer.com",
    "arxiv.org",
    "usenix.org",
    "ieee.org",
    "crossmark.crossref.org",
    "wikipedia.org",
    "archive.org",
]
"""
These domains won't host artifacts at this moment.
Papers are assumed to not be an artifact.
"""

session_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.3"
}


def get_rules(session: requests.Session) -> Iterable[ranking.RankPhase]:
    session.headers.update(session_headers)

    trash_phase = ranking.RawPhase((rules.base.Parseable(),))
    filter_phase = ranking.UrlPhase(
        (
            rules.url.JoinedSentence(),
            *(rules.url.NotDomain(domain) for domain in ignore_domains),
        )
    )
    resolve_phase = ranking.UrlPhase((rules.url.HostExists(),))
    offline_phase_1 = ranking.UrlPhase(
        (
            rules.url.MaybeJoinedSentence(),
            rules.url.GithubRepo(),
            rules.url.GithubStable(),
            rules.url.DoiZenodo(),
            rules.url.ZenodoArchive(),
            rules.url.Domain("gitlab.com", 10, True),
            rules.url.Domain("github.io", 10),
        )
    )
    offline_phase_2 = ranking.LocationPhase(
        (
            rules.location.TitleInUrl(),
            rules.location.LocationInPaper(),
            rules.location.LinkParagraphContext(),
        )
    )
    request_phase = ranking.RequestPhase(
        (
            rules.request.FailedRequest(),
            rules.request.TitleInContent(),
            rules.request.PartialTitleInContent(),
            rules.request.Citation(),
            rules.url.Domain("eprint.iacr.org", -50, True),
            rules.url.Domain("ia.cr", -50, True),
        ),
        session,
    )

    return (
        trash_phase,
        filter_phase,
        resolve_phase,
        offline_phase_1,
        offline_phase_2,
        request_phase,
    )


class RankWorker(mputils.BaseWorker[ParsedPaper, tuple[str, Sequence[RankedLink]]]):
    def __init__(
        self, paper_dir: str, **kwargs: Unpack[mputils.WorkerParams[ParsedPaper, tuple[str, Sequence[RankedLink]]]]
    ):
        super().__init__(**kwargs)
        self.session = create_session(10, self.stop_event)
        self.paper_dir = paper_dir
        self.ranker = ranking.Ranker()
        for rule in get_rules(self.session):
            self.ranker.register_phase(rule)

    @override
    def process_item(self, paper: ParsedPaper) -> tuple[str, Sequence[RankedLink]] | None:
        self.logger.info("Processing paper %s", paper.title.popular_title)
        path = pathlib.Path(os.path.join(os.path.abspath(self.paper_dir), f"{paper.id()}.pdf"))
        # Filter duplicates
        link_dict: dict[str, ParsedLink] = {}
        for link in paper.links:
            if link.link not in link_dict:
                link_dict[link.link] = link

        return paper.id(), self.ranker.rank_links(link_dict.values(), paper, path)


class RankManager(mputils.ProcessExecutor[ParsedPaper, tuple[str, Sequence[RankedLink]]]):
    def __init__(self, paper_dir: str, papers: list[ParsedPaper]) -> None:
        super().__init__(max_workers=8, max_threads=1)

        self.papers = papers
        self.paper_dir = paper_dir

    def _prepare_items(self) -> Iterable[ParsedPaper]:
        yield from self.papers

    def _get_worker_args(self, i: int) -> Iterable[Any]:
        return (self.paper_dir,)

    @classmethod
    def _worker(cls, *args: Any, **kwargs: Any) -> RankWorker:
        return RankWorker(*args, **kwargs)


def process_papers(papers: list[ParsedPaper], paper_dir: str) -> dict[str, Sequence[RankedLink]]:
    manager = RankManager(paper_dir, papers)
    result = manager.run()

    return {pid: links for pid, links in result}


def main() -> None:
    parser = argparse.ArgumentParser(description="Conference paper link ranker")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose operation")
    parser.add_argument("-q", "--quiet", action="store_true", default=0, help="Disable all logging")
    parser.add_argument("--debug", metavar="[debug file]", help="path to file for debug logging")
    parser.add_argument("links_file_path", metavar="[list.json file]", help="path to output of find_links.py")
    parser.add_argument("paper_dir", help="path to directory containing the pdfs to process")
    args = parser.parse_args()

    level = logging.INFO
    if args.verbose:
        level = logging.DEBUG
    if args.quiet:
        level = logging.ERROR
    log = get_logger(level, args.debug)

    papers = parse_links_file(args.links_file_path)

    ranked = process_papers(papers, args.paper_dir)

    d = []
    for pid, links in ranked.items():
        d.append({pid: [dataclasses.asdict(link) for link in links]})
    json.dump(d, sys.stdout, indent=2)

    log.info("Finished")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt as e:
        logging.info(f'{type(e).__name__}: {"Terminated."}')
        sys.exit(1)
