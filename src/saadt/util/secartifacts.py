# mypy: ignore-errors

import dataclasses
from typing import Any

import requests
import yaml

from saadt.model import ArtifactBadge, badge
from saadt.util import text_encoding

BASE_URL = "https://raw.githubusercontent.com/secartifacts/secartifacts.github.io/main/_conferences/"


class JekyllParser:
    def parse_front_matter(self, data: bytes, encoding: str | None = None) -> dict[str, list[dict[str, str]]] | None:
        fm = self._get_front_matter(text_encoding.unicode(data, encoding))

        if fm is None:
            return None

        return yaml.load(fm, yaml.CLoader)  # type: ignore[no-any-return]

    def filter_line(self, line: str) -> str | None:
        if line.strip().startswith("#"):
            return None

        return line

    def _get_front_matter(self, data: str) -> str | None:
        lines = data.splitlines()
        if lines.pop(0) != "---":
            return None
        end = lines.index("---")
        if end != -1:
            return "\n".join([line for line in lines[0:end] if self.filter_line(line) is not None])

        return None


@dataclasses.dataclass
class SecartifactsArtifact:
    title: str
    artifact_urls: list[str] | None
    appendix_url: str | None
    paper_url: str | None
    badges: list[ArtifactBadge] | None


class SecartifactsScraper:
    conference: str
    edition: str

    data: dict[str, list[dict[str, str]]]
    artifacts: list[SecartifactsArtifact]

    def __init__(self, conference: str, edition: str) -> None:
        self.conference = self.fix_conference_name(conference)
        self.edition = edition

        data = self._get_conference_data()
        if data is None:
            raise RuntimeError(f"Couldn't find data for {self.conference} {self.edition}")
        self.data = data

        self.artifacts = self._get_artifacts(data)

    def _get_conference_data(self) -> dict[str, list[dict[str, str]]] | None:
        url = f"{BASE_URL}{self.conference}20{self.edition}/results.md"

        r = requests.get(url)
        r.raise_for_status()

        parser = JekyllParser()
        return parser.parse_front_matter(r.content, r.encoding)

    def _find_artifacts(self, d: dict[str, Any]) -> list[dict[str, Any]] | None:
        if "artifacts" in d:
            return d["artifacts"]

        result = []

        for _, val in d.items():
            if isinstance(val, dict):
                a = self._find_artifacts(val)
                if a is not None:
                    result.extend(a)
            elif isinstance(val, list):
                for el in val:
                    a = self._find_artifacts(el)
                    if a is not None:
                        result.extend(a)

        if len(result) == 0:
            return None

        return result

    def _parse_badge(self, bs: str) -> ArtifactBadge | None:
        try:
            match self.conference:
                case "acsac":
                    return badge.ACMArtifactBadge.parse_string(bs)
                case "ches":
                    return badge.CHESArtifactBadge(bs)
                case "usenixsec":
                    if self.edition < "22":
                        if "Evaluated" in bs:
                            return badge.UsenixArtifactBadge.PASSED
                    else:
                        return badge.UsenixArtifactBadge(bs)
                case "woot":
                    return badge.WOOTArtifactBadge(bs)
        except ValueError:
            return None

    def _parse_badges(self, raw: str | None) -> list[badge.ArtifactBadge] | None:
        if raw is None:
            return None
        result = []

        if ":" in raw:
            raw = raw.split(":", maxsplit=1)[1]

        for s in raw.split(","):
            b = self._parse_badge(s.strip())
            if b is not None:
                result.append(b)

        return result

    def _parse_artifacts(self, raw: list[dict[str, Any]]):
        result = []

        for entry in raw:
            urls = None
            if "artifact_url" in entry:
                if " " in entry["artifact_url"]:
                    urls = entry["artifact_url"].split(" ")
                else:
                    urls = entry["artifact_url"].split(",")
            result.append(
                SecartifactsArtifact(
                    title=text_encoding.sanitize(entry.get("title")),
                    artifact_urls=urls,
                    appendix_url=entry.get("appendix_url"),
                    paper_url=entry.get("paper_url"),
                    badges=self._parse_badges(entry.get("badges")),
                )
            )

        return result

    def _get_artifacts(self, data: dict[str, list[dict[str, str]]]):
        artifacts_dict = self._find_artifacts(data)
        if artifacts_dict is None:
            raise ValueError(f"No artifacts found for conference {self.conference} and edition {self.edition}")

        return self._parse_artifacts(artifacts_dict)

    @staticmethod
    def fix_conference_name(conference: str) -> str:
        if conference == "usenix":
            return "usenixsec"

        return conference
