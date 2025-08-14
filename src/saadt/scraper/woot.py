import logging
import re
from collections.abc import Iterable
from typing import Any, Unpack, override
from urllib.parse import urljoin

import bs4
import requests
from bs4 import BeautifulSoup
from unidecode import unidecode

from saadt.model import ArtifactBadge, Paper, PaperTitle, WOOTArtifactBadge
from saadt.scraper import ScraperWorker, ThreadedScraper
from saadt.util import mputils
from saadt.util.mputils import WorkerParams

WOOT_BASE_URL = "https://www.usenix.org/conference/woot{year}/"

log = logging.getLogger(__name__)


class WootScraperWorker(ScraperWorker[tuple[PaperTitle, str]]):
    _paper_href_re: re.Pattern[str]
    _appendix_href_re: re.Pattern[str]
    _appendix_string_re: re.Pattern[str] = re.compile(r"[a-z]+\s.*(?:Appendix|Abstract)\s.*PDF$", re.IGNORECASE)

    def __init__(
        self,
        edition: str,
        **kwargs: Unpack[WorkerParams[tuple[PaperTitle, str], Paper]],
    ):
        super().__init__(edition, **kwargs)

        self._paper_href_re = re.compile(rf"files/.*{self.edition}(?:-[a-z0-9]+)+(?:_[0-9])?\.pdf", re.IGNORECASE)
        self._appendix_href_re = re.compile(rf"files/.*{self.edition}-.*\.pdf")

    def _process_node(self, node: tuple[PaperTitle, str]) -> Paper:
        title, link = node
        self.logger.debug('Processing paper="%s", url="%s"', title, link)
        pdf_link, appendix_link, badges = self._parse_presentation_site(link)

        paper = Paper(title, link, pdf_link, appendix_link, badges)
        return paper

    def _parse_presentation_site(self, link: str) -> tuple[str, str | None, list[ArtifactBadge]]:
        name = link.rsplit("/", 1)[-1]

        try:
            r = self.session.get(link)
            r.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError(f'Error fetching presentation site="{link}"') from exc

        soup = BeautifulSoup(r.content, "lxml")
        pdf_link = self._get_paper_link(soup, name)
        if pdf_link is None:
            raise Exception(f'Failed to find PDF for presentation="{link}"')

        badges = []
        badge_nodes = soup.find_all("img", src=re.compile("artifact_evaluation_[a-z]+"))
        for node in badge_nodes:
            b = self._parse_artifact_badge_link(node.get("src"))
            if b is not None:
                badges.append(b)

        appendix_link = self._get_appendix_link(soup)

        if len(badges) > 0 and appendix_link is None:
            self.logger.error("Paper has badges but appendix not found. presentation=%s", link)

        return pdf_link, appendix_link, badges

    def _get_paper_link(self, soup: BeautifulSoup, name: str = "") -> str | None:
        node: bs4.Tag = soup.find("a", href=self._paper_href_re, string=self._not_appendix)  # type: ignore[assignment]
        if node is None:
            return None
        return node.get("href")  # type: ignore[return-value]

    def _get_appendix_link(self, soup: BeautifulSoup, name: str = "") -> str | None:
        node: bs4.Tag = soup.find("a", href=self._appendix_href_re, string=self._appendix_string_re)  # type: ignore[assignment]
        if node is None:
            return None
        return node.get("href")  # type: ignore[return-value]

    def _parse_artifact_badge_link(self, url: str) -> ArtifactBadge | None:
        if "available" in url:
            return WOOTArtifactBadge.AVAILABLE
        if "functional" in url:
            return WOOTArtifactBadge.FUNCTIONAL
        if "reproduced" in url:
            return WOOTArtifactBadge.REPRODUCED
        return None

    @staticmethod
    def _not_appendix(val: str) -> bool:
        return val is not None and not re.compile(r"\sAppendix\s").search(val)


class WootOldScraperWorker(WootScraperWorker):
    def __init__(
        self,
        edition: str,
        **kwargs: Unpack[WorkerParams[tuple[PaperTitle, str], Paper]],
    ):
        super().__init__(edition, **kwargs)
        self._paper_href_re = re.compile(
            rf"files/(?:conference/woot{self.edition}/)?woot{self.edition}(?!_slides_|_web_flyer)(?:[-_][a-z]+[0-9]*)+(?:_[0-9])?\.pdf",
            re.IGNORECASE,
        )

    def _parse_artifact_badge_link(self, url: str) -> ArtifactBadge | None:
        if "passed" in url:
            return WOOTArtifactBadge.PASSED
        return None

    def _get_appendix_link(self, soup: BeautifulSoup, name: str = "") -> str | None:
        return None



class WootScraper(ThreadedScraper[tuple[PaperTitle, str]]):
    @override
    def _get_papers(self) -> list[tuple[PaperTitle, str]]:
        log.info("Fetching conference papers")
        try:
            r = self.session.get(self._get_url("technical-sessions"))
            r.raise_for_status()
        except requests.HTTPError as exc:
            raise RuntimeError("Error fetching WOOT website") from exc

        log.debug("Parsing technical-session page")
        soup = BeautifulSoup(r.content, "lxml")
        # find all papers
        nodes = self._get_tags(soup.find_all(class_="node-paper"))

        result = []
        for node in nodes:
            if node.string is None:
                continue
            title = unidecode(node.string.strip())
            link = self._get_url(node.attrs["href"])
            result.append((PaperTitle(title), str(link)))

        log.debug("Found %d entries", len(result))

        return result

    def _get_url(self, url: str) -> str:
        return urljoin(WOOT_BASE_URL.format(year=self.edition), url)

    def _get_tags(self, nodes: bs4.ResultSet[bs4.Tag]) -> list[bs4.Tag]:
        result: list[bs4.Tag] = []
        for node in nodes:
            result.append(node.find("a"))  # type: ignore[arg-type]

        return result

    @override
    def _get_worker_args(self, i: int) -> Iterable[Any]:
        return (self.edition,)

    @classmethod
    @override
    def _worker(
        cls,
        *args: str,
        **kwargs: Unpack[mputils.WorkerParams[tuple[PaperTitle, str], Paper]],
    ) -> WootScraperWorker:
        if int(args[0]) >= 22:
            return WootScraperWorker(*args, **kwargs)
        else:
            return WootOldScraperWorker(*args, **kwargs)



