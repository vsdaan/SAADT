import logging
import multiprocessing as mp
import multiprocessing.queues  # noqa
import multiprocessing.synchronize
from collections.abc import Iterable, Iterator
from enum import Enum
from typing import NamedTuple, override

import requests
import urllib3.util

from saadt.model import Conference
from saadt.util.log import LoggerInterface, MultiProcessingLogger
from saadt.util.mputils import BaseWorker
from saadt.util.session import create_session

from .crawlers import BaseContender, BaseCrawler, CrawlerError, CrawlerFactory, LinkContext
from .rules import RuleEvalContext, RulePack, RulePackContext, RuleSet, get_ruleset

log = logging.getLogger(__name__)


class LinkState(Enum):
    ERROR = "error"
    NO = "no"
    PARTIAL = "partial"
    FULL = "full"


class MatchedLink(NamedTuple):
    link: str
    # state: LinkState
    score: int
    metadata: str = ""


class MatchedPaper(NamedTuple):
    title: str
    links: list[MatchedLink]


class UnmatchedPaper(NamedTuple):
    title: str
    conference: Conference
    links: Iterable[urllib3.util.Url]

    @property
    def combination_title(self) -> bool:
        return ":" in self.title

    @property
    def popular_title(self) -> str:
        return self.title.split(":", 1)[0]

    @property
    def descriptive_title(self) -> str:
        if self.combination_title:
            return self.title.split(":", 1)[1]

        return ""


class MatchingResult:
    papers: list[MatchedPaper] = []

    def add(self, title: str, links: list[MatchedLink]) -> None:
        self.papers.append(MatchedPaper(title, links))


class MatchingSet(Iterable[UnmatchedPaper]):
    papers: list[UnmatchedPaper] = []

    def add(self, title: str, conference: Conference, links: list[str]) -> None:
        parsed_links: list[urllib3.util.Url] = []
        for link in links:
            parsed = urllib3.util.parse_url(link)
            if parsed.host is None or parsed.scheme is None:
                raise Exception("Invalid URL")

            parsed_links.append(parsed)

        self.papers.append(UnmatchedPaper(title, conference, parsed_links))

    @override
    def __iter__(self) -> Iterator[UnmatchedPaper]:
        yield from self.papers


class Matcher:
    session: requests.Session
    work_path: str

    def __init__(
        self,
        work_path: str,
        session: requests.Session | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
    ):
        self.session = session or create_session()
        self.session.headers.update(headers or {})
        self.session.cookies.update(cookies or {})

        self.work_path = work_path

    def run(self, papers: MatchingSet) -> MatchingResult:
        log.debug("Started link matching")

        result = MatchingResult()
        matcher = MatcherWorker(self.work_path, self.session)
        for paper in papers:
            log.debug(f"Processing paper: {paper.title}")
            links = matcher.process_paper(paper)

            if links is not None:
                result.add(paper.title, links)

        return result


class MatchTask(NamedTuple):
    id: int
    conference: Conference
    paper: str
    links: tuple[urllib3.util.Url, ...]


class MatchTaskResult(NamedTuple):
    task_id: int
    links: tuple[MatchedLink, ...]


class MatcherWorker:
    factory: CrawlerFactory
    logger: LoggerInterface
    rule_set: RuleSet
    session: requests.Session

    def __init__(self, work_path: str, session: requests.Session, logger: LoggerInterface = log):
        self.logger = logger
        self.rule_set = get_ruleset()
        self.session = session
        self.factory = CrawlerFactory(self.session, work_path)

    def process_paper(self, paper: UnmatchedPaper) -> list[MatchedLink] | None:
        rule_pack = self.rule_set.get_rulepack(RulePackContext(paper.conference, paper.title))

        try:
            matched_links = self.process_links(paper.links, rule_pack)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            self.logger.error(f'Failed to match links for paper="{paper.title}": {exc}')
        else:
            return matched_links

        return None

    def process_links(self, links: Iterable[urllib3.util.Url], rule_pack: RulePack) -> list[MatchedLink]:
        result = []
        for link in links:
            try:
                c = self.factory.create(LinkContext(link))
                if c is None:
                    continue
                m = self.match(c, rule_pack)
                result.append(m)
            except CrawlerError as exc:
                self.logger.error(f'Failed matching for link="{link}": {exc}')
                self.logger.debug("Traceback:", exc_info=exc)
                result.append(MatchedLink(link.url, -1, str(exc)))

        return result

    def match(self, crawler: BaseCrawler, rule_pack: RulePack) -> MatchedLink:
        ranked_contenders: list[BaseContender] = []

        for contender in crawler.crawl():
            ctx = RuleEvalContext(contender.content)
            for rule in rule_pack.rules():
                if rule.eval(ctx):
                    contender.score += rule.score

                if contender.score >= 100:
                    # This should be enough
                    break

            ranked_contenders.append(contender)

        best = max(ranked_contenders, key=lambda x: x.score)
        # TODO: gather metadata

        return MatchedLink(crawler.context.url.url, best.score)


class MatcherProcessWorker(MatcherWorker, BaseWorker[MatchTask, MatchTaskResult]):
    factory: CrawlerFactory
    logger: MultiProcessingLogger

    def __init__(
        self,
        work_path: str,
        session: requests.Session,
        threads: int,
        stop_event: mp.synchronize.Event,
        dispatch_queue: mp.queues.Queue[MatchTask | None],
        finished_queue: mp.queues.Queue[MatchTaskResult | None],
        logger: MultiProcessingLogger,
    ):
        csession = create_session(self._threads + 10, stop_event)
        csession.headers.update(session.headers or {})
        csession.cookies.update(session.cookies or dict[str, str]())

        MatcherWorker.__init__(self, work_path, csession)
        BaseWorker.__init__(self, threads, stop_event, dispatch_queue, finished_queue, logger)
        self.session = create_session(self._threads + 10, stop_event)
        self.factory = CrawlerFactory(self.session, work_path)

    @override
    def process_item(self, item: MatchTask) -> MatchTaskResult | None:
        rule_pack = self.rule_set.get_rulepack(RulePackContext(item.conference, item.paper))

        try:
            matched_links = self.process_links(item.links, rule_pack)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            self.logger.error(f'Failed to match links for paper="{item.paper.title}": {exc}')
        else:
            return MatchTaskResult(item.id, tuple(matched_links))

        return None
