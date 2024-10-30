import logging

import yaml
from bs4.dammit import UnicodeDammit

from saadt.model import ArtifactBadge, Paper, WOOTArtifactBadge
from saadt.model.paper import PaperTitle
from saadt.scraper import Scraper

log = logging.getLogger(__name__)


class JekyllParser:
    def parse_front_matter(self, data: bytes) -> dict[str, list[dict[str, str]]] | None:
        parsed = UnicodeDammit(data).unicode_markup
        fm = self._get_front_matter(parsed)
        if fm is None:
            return None

        return yaml.load(fm, yaml.CLoader)  # type: ignore[no-any-return]

    def _get_front_matter(self, data: str) -> str | None:
        lines = data.splitlines()
        if lines.pop(0) != "---":
            return None
        end = lines.index("---")
        if end != -1:
            return "\n".join(lines[0:end])

        return None


class WootScraper(Scraper):
    url: str

    def __init__(self, edition: str, proxies: dict[str, str] | None = None):
        super().__init__(edition, proxies=proxies)
        self.url = f"https://raw.githubusercontent.com/secartifacts/secartifacts.github.io/main/_conferences/woot20{edition}/results.md"

    def run(self) -> list[Paper]:
        return self._get_artifacts()

    def _get_artifacts(self) -> list[Paper]:
        sec_papers = self._get_results()

        result = []
        for p in sec_papers:
            log.debug(f'Processing "{p["title"]}"')
            badges = self._get_badges(p)
            artifacts = self._get_artifacts_links(p)
            result.append(
                Paper(
                    PaperTitle(p["title"]),
                    pdf_link=p["paper_url"],
                    badges=badges,
                    artifact_links=artifacts,
                )
            )

        return result

    def _get_badges(self, artifact: dict[str, str]) -> list[ArtifactBadge]:
        if int(self.edition) < 23:
            return [WOOTArtifactBadge.EVALUATED]

        badges: list[ArtifactBadge] = []
        for badge in artifact["badges"].split(","):
            try:
                badges.append(WOOTArtifactBadge(badge.strip()))
            except ValueError as exc:
                log.error('Failed to add badges title="%s": %s', artifact["title"], exc)

        return badges

    def _get_artifacts_links(self, paper: dict[str, str]) -> list[str]:
        if "artifact_url" not in paper:
            return []

        result = []
        urls = paper["artifact_url"].split(",")
        for url in urls:
            url = url.strip()
            result.append(url)

        if len(result) == 0:
            return []
        return result

    def _get_results(self) -> list[dict[str, str]]:
        r = self.session.get(self.url)
        if not r.ok:
            log.error("Failed to fetch results")
            r.raise_for_status()

        fm = JekyllParser().parse_front_matter(r.content)
        assert fm is not None
        if "artifacts" not in fm:
            raise Exception(f"Failed to find artifacts in results, url={self.url}")

        result = list(map(lambda x: {k: v.strip() for k, v in x.items()}, fm["artifacts"]))
        return result
