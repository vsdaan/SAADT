import logging
import re
from collections.abc import Iterable
from typing import Any, Unpack, override
from urllib.parse import urljoin

import bs4
import requests
from bs4 import BeautifulSoup
from requests import HTTPError
from unidecode import unidecode
from urllib3.util import parse_url

from saadt.model import CHESArtifactBadge, Paper
from saadt.model.paper import PaperTitle
from saadt.scraper import ScraperWorker, ThreadedScraper
from saadt.scraper.util import TitleMatcher
from saadt.util.mputils import WorkerParams

log = logging.getLogger(__name__)

ARTICLE_DOWNLOAD_URL = "https://tches.iacr.org/index.php/TCHES/article/download/"
ARTICLE_VIEW_URL = "https://tches.iacr.org/index.php/TCHES/article/view/"
ISSUE_VIEW_URL = "https://tches.iacr.org/index.php/TCHES/issue/view/"
ISSUE_ARCHIVE_URL = "https://tches.iacr.org/index.php/TCHES/issue/archive"


class ChesScraperWorker(ScraperWorker[tuple[PaperTitle, str]]):
    _archive_rex = re.compile(r"\s*(?:zip|tar\.[a-z]{2,3}|tgz)\s+.*", re.I)
    _paper_rex = re.compile(r"\s*Paper\s*")
    _view_on_rex = re.compile(r"\s*View on\s.*")
    _readme_rex = re.compile(r"\s*README\s*")

    _pdf_rex = re.compile(".*PDF.*")
    _badge_rex = re.compile(r"IACR CHES [a-zA-Z]+")

    @override
    def _process_node(self, node: tuple[PaperTitle, str]) -> Paper:
        title, link = node
        self.logger.debug('Processing paper="%s", url="%s"', title, link)

        try:
            if parse_url(link).host == "artifacts.iacr.org":
                pdf_link, appendix_link, artifacts, badge = self._parse_artifact_site(link)
                return Paper(title, link, pdf_link, appendix_link, [badge], artifacts)

            pdf_link = self._parse_article_site(link)
            return Paper(title, link, pdf_link)
        except RuntimeError as err:
            self.logger.error("Failed to parse site: %s", err)
            self.logger.debug("Traceback:", exc_info=err)

            return Paper(title, link)

    def _parse_article_site(self, link: str) -> str:
        r = self.session.get(link)
        try:
            r.raise_for_status()
        except requests.HTTPError as ex:
            raise RuntimeError(f"Failed to fetch article site: {ex}") from ex

        soup = BeautifulSoup(r.content, "lxml")
        pdf_node: bs4.Tag | None = soup.find(
            "a", class_="obj_galley_link pdf", href=re.compile(f"{r.url}/[0-9]+"), string=self._pdf_rex
        )  # type: ignore[assignment]
        if pdf_node is None:
            raise RuntimeError(f"Could not find pdf link for site: {link}")

        url = parse_url(pdf_node.attrs["href"])
        assert url.path is not None

        return urljoin(ARTICLE_DOWNLOAD_URL, "/".join(url.path.rsplit("/", 2)[1:]))

    def _parse_artifact_site(self, link: str) -> tuple[str | None, str | None, list[str], CHESArtifactBadge]:
        r = self.session.get(link)
        try:
            r.raise_for_status()
        except requests.HTTPError as ex:
            raise RuntimeError(f"Failed to fetch artifact site: {ex}") from ex

        soup = BeautifulSoup(r.content, "lxml")
        main_node = self._get_main_content_node(soup)
        assert main_node is not None

        node = self._get_publication_node(main_node)
        if node is None:
            raise RuntimeError("Failed to find publication node")

        paper_link, appendix_link, artifacts, badge = self._parse_publication_node(link, node)
        if paper_link is None:
            raise Exception(f"Failed to find paper for site: {link}")
        if appendix_link is None:
            raise RuntimeError(f"Failed to find README for site: {link}")
        if len(artifacts) == 0:
            raise RuntimeError(f"Failed to find artifacts for site: {link}")

        pdf_link = self._parse_article_site(paper_link)

        return pdf_link, appendix_link, artifacts, badge

    def _get_main_content_node(self, soup: BeautifulSoup) -> bs4.Tag | None:
        return soup.find("main", class_="container")  # type: ignore[return-value]

    def _get_publication_node(self, content: bs4.Tag) -> bs4.Tag | None:
        container = content.find("div", class_="container", recursive=False)
        assert container is not None
        row: bs4.Tag = container.find("div", class_="row", recursive=False)  # type: ignore[call-arg,assignment]
        for pub in row.find_all("b", string="Publication"):
            p: bs4.Tag | None = pub.find_parent("div", class_="col")
            if p is not None:
                return p

        return None

    def _parse_publication_node(
        self, base: str, node: bs4.Tag
    ) -> tuple[str | None, str | None, list[str], CHESArtifactBadge]:
        paper_link = None
        appendix_link = None
        artifacts = []
        badge: CHESArtifactBadge = CHESArtifactBadge.FUNCTIONAL

        for a in node.find_all("a"):
            if a.find(string=self._paper_rex) is not None:
                paper_link = urljoin(base, a["href"])
                continue
            if a.find(string=self._view_on_rex) is not None:
                link = urljoin(base, a["href"])
                artifacts.append(link)
                continue
            if a.find(string=self._readme_rex) is not None:
                appendix_link = urljoin(base, a["href"])
                continue
            if a.find(string=self._archive_rex) is not None:
                link = urljoin(base, a["href"])
                artifacts.append(link)
                continue

        if int(self.edition) > 23:
            # Badges are introduced
            badge_title = node.find("span", string="Badge")
            if badge_title is None:
                raise Exception("Failed to find badge title")

            assert badge_title.parent is not None
            badge_node: bs4.Tag | None = badge_title.parent.find("span", string=self._badge_rex)  # type: ignore[assignment]
            if badge_node is None:
                raise Exception("Failed to find badge")
            badge = self._parse_artifact_badge_string(str(badge_node.string))  # type: ignore[assignment]
            if badge is None:
                raise Exception(f"Failed to parse badge string: {badge_node.string}")

        return paper_link, appendix_link, artifacts, badge

    def _parse_artifact_badge_string(self, val: str) -> CHESArtifactBadge | None:
        if "Available" in val:
            return CHESArtifactBadge.AVAILABLE
        if "Functional" in val:
            return CHESArtifactBadge.FUNCTIONAL
        if "Reproduced" in val:
            return CHESArtifactBadge.REPRODUCED
        return None


class ChesScraper(ThreadedScraper[tuple[PaperTitle, str]]):
    def __init__(
        self, edition: str, max_workers: int = 2, max_threads: int = 10, proxies: dict[str, str] | None = None
    ):
        super().__init__(edition, max_workers=max_workers, max_threads=max_threads)
        self.artifacts_url = f"https://artifacts.iacr.org/tches/20{self.edition}/"
        self.re_artifact_view = re.compile(f"{ARTICLE_VIEW_URL}[0-9]+")
        self.re_article_id = re.compile("^article-[0-9]+$")
        self.re_volume_name = re.compile(rf"Vol(?:\.|ume)\s+20{self.edition}[^0-9]+")
        self.re_issue_href = re.compile(rf"{ISSUE_VIEW_URL}[0-9]+")

    @override
    def _get_papers(self) -> list[tuple[PaperTitle, str]]:
        try:
            papers = self._get_all_papers()
        except HTTPError as exc:
            raise RuntimeError("Error fetching papers from CHES website") from exc

        try:
            artifacts = self._get_artifacts()
        except HTTPError as exc:
            raise RuntimeError("Error fetching artifacts from CHES website") from exc

        result: dict[str, tuple[PaperTitle, str]] = {}
        for paper in papers:
            result[str(paper[0])] = paper

        matcher = TitleMatcher(result.values(), lambda x: str(x[0]))
        for artifact in artifacts:
            match = matcher.match(artifact)
            if match:
                paper = match[0]
                result[str(paper[0])] = (paper[0], artifact[1])
            else:
                log.error("Couldn't find paper for artifact=%s", str(artifact[0]))

        return list(result.values())

    def _get_all_papers(self) -> list[tuple[PaperTitle, str]]:
        log.info("Fetching conference papers")
        log.debug("Fetching archive")
        r = self.session.get(ISSUE_ARCHIVE_URL)
        r.raise_for_status()

        soup = BeautifulSoup(r.content, "lxml")
        issues = self._get_issue_nodes(soup)

        result: list[tuple[PaperTitle, str]] = []
        for issue in issues:
            try:
                result.extend(self._process_issue(issue))
            except (HTTPError, RuntimeError) as e:
                log.error('Failed processing issue "%s": %s', issue.get("href", None), e)

        return result

    def _get_issue_article_list(self, soup: BeautifulSoup) -> bs4.Tag:
        sections = soup.find_all("div", class_="section")
        re_art_header = re.compile(r"^\s*Articles\s*$")

        for section in sections:
            h = section.find("h2", string=re_art_header)
            ul = section.find("ul", class_="articles")
            if h and ul:
                assert isinstance(ul, bs4.Tag)
                return ul

        raise RuntimeError("Failed to find article list")

    def _process_issue(self, issue: bs4.Tag) -> list[tuple[PaperTitle, str]]:
        r = self.session.get(issue.attrs["href"])
        r.raise_for_status()

        soup = BeautifulSoup(r.content, "lxml")
        article_list = self._get_issue_article_list(soup)
        nodes = article_list.find_all(
            "a",
            id=self.re_article_id,
            href=self.re_artifact_view,
        )

        log.debug("Found %d articles in %s", len(nodes), issue.text.strip())

        result = []
        title: str
        for node in nodes:
            title = unidecode(node.next.string.strip())
            subtitle: str | None = None

            subtitle_node = node.find("span", class_="subtitle")
            if subtitle_node is not None:
                subtitle = unidecode(subtitle_node.next.string.strip())
            link = str(node.attrs["href"])

            result.append((PaperTitle(title, None, subtitle), link))

        return result

    def _get_artifacts(self) -> list[tuple[PaperTitle, str]]:
        if int(self.edition) < 21:
            return []

        log.info("Fetching conference artifacts")
        r = self.session.get(self.artifacts_url)
        r.raise_for_status()

        result = []
        soup = BeautifulSoup(r.content, "lxml")
        nodes = soup.find_all("a", href=re.compile(rf"/tches/20{self.edition}/[a-z0-9]+/"))
        for node in nodes:
            link = str(urljoin(self.artifacts_url, node.attrs["href"]))
            title = unidecode(" ".join(map(lambda line: line.strip(), node.b.string.splitlines())), errors="replace")
            result.append((PaperTitle(title), link))

        return result

    def _get_issue_nodes(self, content: bs4.Tag) -> list[bs4.Tag]:
        nodes = content.find_all(
            "a",
            class_="title",
            href=self.re_issue_href,
            string=self.re_volume_name,
        )

        return list(nodes)

    @override
    def _get_worker_args(self, i: int) -> Iterable[Any]:
        return (self.edition,)

    @classmethod
    @override
    def _worker(
        cls,
        *args: Any,
        **kwargs: Unpack[WorkerParams[tuple[PaperTitle, str], Paper]],
    ) -> ChesScraperWorker:
        return ChesScraperWorker(*args, **kwargs)
