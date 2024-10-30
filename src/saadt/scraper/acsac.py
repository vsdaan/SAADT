import logging
import re
from concurrent.futures import ThreadPoolExecutor
from typing import NamedTuple, Protocol
from urllib.parse import urljoin

import bs4
from bs4 import BeautifulSoup
from requests import HTTPError
from unidecode import unidecode
from urllib3.util import parse_url

from saadt.model import ACMArtifactBadge, ArtifactBadge, Paper
from saadt.model.paper import PaperTitle
from saadt.scraper import Scraper
from saadt.scraper.util import TitleMatcher

log = logging.getLogger(__name__)


class _Artifact(NamedTuple):
    title: str
    github: str
    web: str
    badge: ArtifactBadge


class _HasTitle(Protocol):
    title: str


class AcsacScraper(Scraper):
    base_url: str
    _num_threads: int

    def __init__(self, edition: str, max_threads: int = 10, proxies: dict[str, str] | None = None):
        self.base_url = f"https://www.acsac.org/20{edition}/"
        self._num_threads = max_threads
        super().__init__(edition, proxies=proxies)

    def run(self) -> list[Paper]:
        try:
            papers = self._get_all_papers()
        except (RuntimeError, HTTPError) as exc:
            raise RuntimeError("Error fetching papers from ACSAC website") from exc

        if len(papers) == 0:
            log.error("No papers found")

        try:
            artifacts = self._get_artifacts()
        except HTTPError as exc:
            log.error("Failed fetching artifacts: %s", exc)
            log.debug("Traceback:", exc_info=exc)
        else:
            matcher = TitleMatcher(papers, key=lambda x: str(x.title))
            for artifact in artifacts:
                self._process_artifact(matcher, artifact)

        self._fix_badges(papers)

        return papers

    def _fix_badges(self, papers: list[Paper]) -> None:
        for paper in papers:
            badges = set(paper.badges)
            if ACMArtifactBadge.REUSABLE in badges:
                badges.add(ACMArtifactBadge.FUNCTIONAL)
            paper.badges = sorted(badges, key=list(ACMArtifactBadge).index)  # type: ignore[arg-type]

    def _process_artifact(self, matcher: TitleMatcher[Paper], artifact: _Artifact) -> None:
        # Paper/artifact titles don't always match completely...
        match = matcher.match(artifact.title)
        if match is None and ":" in artifact.title:
            match = matcher.match(artifact.title.split(":", 1)[0])
        if match is None:
            unsafe_match = matcher.unsafe_match(artifact.title)
            if unsafe_match is not None:
                log.warning('Found unsafe match for artifacts "%s": %s', artifact.title, str(unsafe_match.title))
                match = (unsafe_match, None)  # type: ignore[assignment]

        if match is None:
            log.error("Couldn't find paper for artifact=%s", artifact.title)
            return

        paper = match[0]
        paper.badges.append(artifact.badge)
        log.debug('Matched artifact "%s" with paper "%s"', artifact.title, str(paper.title))

        links: set[str] = set(paper.artifact_links)
        new_links: set[str] = set()
        if artifact.github != "":
            new_links.add(artifact.github)
        if artifact.web != "":
            new_links.add(artifact.web)

        for link in new_links:
            link = link.strip()
            if link not in links:
                paper.artifact_links.append(link)

    def _get_all_papers(self) -> list[Paper]:
        log.info("Fetching conference papers")
        r = self.session.get(self._get_accepted_papers_url())
        r.raise_for_status()

        log.debug("Parsing conference site")
        soup = BeautifulSoup(r.content, "lxml")
        content = self._get_papers_content_node(soup)
        if content is None:
            raise RuntimeError("Couldn't find papers on website. Did the website change?")

        log.debug("Parsing content node")
        nodes = self._process_papers_content_node(content)

        result: list[Paper] = []
        e = ThreadPoolExecutor(self._num_threads, thread_name_prefix="worker")
        for paper in e.map(lambda node: self._process_paper_node(node), nodes):
            result.append(paper)

        return result

    def _process_paper_node(self, node: bs4.Tag) -> Paper:
        assert node.string is not None
        title = unidecode(" ".join(map(lambda line: line.strip(), node.string.splitlines())))

        log.debug(f"Processing node: {title}")
        link = node.attrs.get("href")
        if link is not None:
            link = urljoin(self._get_accepted_papers_url(), link)

        pdf_link = None
        if int(self.edition) > 18 and link is not None and "dl.acm.org/" in link:
            p = parse_url(link)
            assert p.path is not None

            if "authorize" in p.path:
                resp = self.session.head(p.url)
                if "Location" in resp.headers and "/doi" in resp.headers["Location"]:
                    p = parse_url(resp.headers["Location"])

            assert p.path is not None
            path = "/doi/pdf/" + "/".join(p.path.split("/")[2:])
            pdf_link = urljoin(link, path)

        return Paper(PaperTitle(title), link, pdf_link)

    def _get_artifacts(self) -> list[_Artifact]:
        log.info("Fetching conference artifacts")
        r = self.session.get(self._get_artifacts_url())
        r.raise_for_status()

        result = []
        soup = BeautifulSoup(r.content, "lxml")
        node_dict = self._get_artifacts_nodes(soup)
        nodes: list[bs4.Tag]
        for badge, nodes in node_dict.items():
            for node in nodes:
                result.append(
                    _Artifact._make(
                        [
                            self._artifact_node_title(node),
                            self._artifact_node_github(node),
                            self._artifact_node_web(node),
                            badge,
                        ]
                    )
                )

        return result

    def _artifact_node_title(self, node: bs4.Tag) -> str:
        return unidecode(node.text.strip())

    def _artifact_node_github(self, node: bs4.Tag) -> str:
        gn = node.find("img", alt="github")
        if gn is not None:
            assert gn.parent is not None and isinstance(gn.parent["href"], str)
            return gn.parent["href"]
        return ""

    def _artifact_node_web(self, node: bs4.Tag) -> str:
        gn = node.find("img", alt="web")
        if gn is not None:
            assert gn.parent is not None and isinstance(gn.parent["href"], str)
            return gn.parent["href"]
        return ""

    def _get_artifacts_nodes(self, soup: BeautifulSoup) -> dict[ACMArtifactBadge, list[bs4.Tag]]:
        nodes = {}
        if int(self.edition) < 19:
            nodes[ACMArtifactBadge.FUNCTIONAL] = soup.find("div", id="content").find("ul").find_all("li")  # type: ignore[union-attr]
        else:
            nodes = {
                ACMArtifactBadge.FUNCTIONAL: self._get_artifact_by_badge_node(soup, "artifacts_evaluated_functional"),
                ACMArtifactBadge.REUSABLE: self._get_artifact_by_badge_node(soup, "artifacts_evaluated_reusable"),
                ACMArtifactBadge.REPRODUCED: self._get_artifact_by_badge_node(soup, "results_reproduced"),
            }

        return nodes

    def _get_artifact_by_badge_node(self, soup: BeautifulSoup, img_link: str) -> list[bs4.Tag]:
        node = soup.find("img", src=re.compile(rf"{img_link}\.[a-z]{{3}}", re.I))
        if node is None:
            return []
        return node.parent.find_next_sibling("ul").find_all("li")  # type: ignore[union-attr]

    def _get_accepted_papers_url(self) -> str:
        if int(self.edition) < 19:
            return urljoin(self.base_url, "program-files/")
        return urljoin(self.base_url, "program/papers/")

    def _get_artifacts_url(self) -> str:
        if int(self.edition) < 19:
            return urljoin(self.base_url, "artifacts/")
        return urljoin(self.base_url, "program/artifacts/")

    def _get_papers_content_node(self, soup: BeautifulSoup) -> bs4.Tag | None:
        if int(self.edition) < 19:
            return soup.find("div", id="oc_program_matrix")  # type: ignore[return-value]
        return soup.find("main", id="main-content")  # type: ignore[return-value]

    def _process_papers_content_node(self, content: bs4.Tag) -> list[bs4.Tag]:
        if int(self.edition) < 19:
            nodes = content.find_all("span", class_="oc_program_concurrentSessionPaperTitle")
            return list(map(lambda node: node.a, nodes))
        nodes = content.find_all("a", href=re.compile(r"https://dl.acm.org/.*"))
        if len(nodes) == 0:
            nodes = content.find_all("b")
        return nodes
