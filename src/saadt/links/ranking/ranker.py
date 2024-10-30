import concurrent
import logging
import multiprocessing as mp
import pathlib
import random
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor

from saadt.links.parsing import ParsedPaper

from . import BreakDownEntry, RankedLink
from .phase import RankPhase
from .rules import LinkType, RootContext

log = logging.getLogger(__package__)


class Ranker:
    phases: list[RankPhase]
    executor: ThreadPoolExecutor

    def __init__(self, phases: Iterable[RankPhase] | None = None):
        if phases is None:
            phases = []
        self.phases = list(phases)
        self.executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix=f"{mp.current_process().name}")

    def register_phase(self, phase: RankPhase) -> None:
        self.phases.append(phase)

    def _prepare_links(self, links: Iterable[LinkType]) -> list[tuple[RankedLink, LinkType]]:
        return [(RankedLink(str(link), 0, []), link) for link in links]

    def _rank_link(self, phase: RankPhase, root_ctx: RootContext, rlink: RankedLink, link: LinkType) -> None:
        # Links with score < 0 don't continue to next phase.
        if rlink.score < 0:
            return

        ctx = phase.prepare(root_ctx, link)
        for rule in phase.rules():
            log.debug(f"Eval {rule.__class__.__name__}: {str(ctx.link)}")
            ctx.score_modifier = 0

            if rule.eval(ctx):
                rlink.score += rule.score + ctx.score_modifier
                rlink.breakdown.append(BreakDownEntry(str(rule), rule.score + ctx.score_modifier))

    def rank_link(
        self, link: LinkType, paper: ParsedPaper | None = None, path: pathlib.Path | None = None
    ) -> RankedLink:
        rlink = RankedLink(str(link), 0, [])

        root_ctx = RootContext(paper, path)
        for phase in self.phases:
            self._rank_link(phase, root_ctx, rlink, link)

        return rlink

    def rank_links(
        self,
        links: Iterable[LinkType],
        paper: ParsedPaper | None = None,
        path: pathlib.Path | None = None,
    ) -> Sequence[RankedLink]:
        prepared: list[tuple[RankedLink, LinkType]] = self._prepare_links(links)
        # Shuffle the links to distribute domains that are frequently clustered together.
        random.shuffle(prepared)

        root_ctx = RootContext(paper, path)

        for phase in self.phases:
            log.info(f"Starting phase {phase.__class__.__name__}")
            futures = [self.executor.submit(self._rank_link, phase, root_ctx, rlink, link) for rlink, link in prepared]
            concurrent.futures.wait(futures)
            for fut in futures:
                fut.result()

        return tuple(sorted((x[0] for x in prepared), key=lambda x: x.score, reverse=True))

    def rank_papers(self, papers: Iterable[tuple[ParsedPaper, pathlib.Path]]) -> dict[str, Sequence[RankedLink]]:
        result: dict[str, Sequence[RankedLink]] = {}

        for paper, path in papers:
            if paper.appendix_link is None:
                continue
            result[paper.id()] = self.rank_links(paper.links, paper, path)

        return result
