import base64
import dataclasses
import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from saadt.model import ArtifactBadge


@dataclass(frozen=True, slots=True)
class PaperTitle:
    popular_title: str
    descriptive_title: str | None = field(default=None)
    subtitle: str | None = field(default=None)
    _cached_str: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.descriptive_title is not None:
            return

        i = self.popular_title.find(":")
        if 2 < i < len(self.popular_title) - 1:
            object.__setattr__(self, "descriptive_title", self.popular_title[i + 1 :].strip())
            object.__setattr__(self, "popular_title", self.popular_title[:i])

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        if "_cached_str" in d:
            del d["_cached_str"]
        return d

    def __str__(self) -> str:
        if self._cached_str:
            return self._cached_str
        result = self.popular_title
        if self.descriptive_title:
            result += ": "
            result += self.descriptive_title
        if self.subtitle:
            result += " " if result[-1] == ":" else " - "
            result += self.subtitle

        object.__setattr__(self, "_cached_str", result)

        return result

    def __lt__(self, other: "PaperTitle") -> bool:
        return str(self) < str(other)

    def __contains__(self, other: str) -> bool:
        return other in str(self)

    def __getitem__(self, index: int) -> str:
        return str(self)[index]

    def __len__(self) -> int:
        return len(str(self))


@dataclass
class Paper:
    title: PaperTitle
    page_link: str | None = field(default=None)
    pdf_link: str | None = field(default=None)
    appendix_link: str | None = field(default=None)
    badges: list[ArtifactBadge] = field(default_factory=list)
    artifact_links: list[str] = field(default_factory=list)

    _re_unsafe_chars = re.compile(r"[\W]")

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title.to_dict() if isinstance(self.title, PaperTitle) else str(self.title),
            "page_link": self.page_link,
            "pdf_link": self.pdf_link,
            "appendix_link": self.appendix_link,
            "badges": list(map(lambda x: str(x), self.badges)),
            "artifact_links": self.artifact_links,
        }

    @classmethod
    def from_dict(cls, d: dict[str, str | list[str | dict[str, Any]] | dict[str, str]]) -> "Paper":
        if isinstance(d["title"], str):
            title = PaperTitle(d["title"])
        else:
            assert isinstance(d["title"], dict)
            title = PaperTitle(**d["title"])

        badges = []
        bs = d.get("badges")
        if bs is not None:
            for b in bs:
                badges.append(ArtifactBadge.from_string(b))

        return cls(
            title=title,
            page_link=d.get("page_link"),  # type: ignore[arg-type]
            pdf_link=d.get("pdf_link"),  # type: ignore[arg-type]
            appendix_link=d.get("appendix_link"),  # type: ignore[arg-type]
            badges=badges,
            artifact_links=d.get("artifact_links") or [],  # type: ignore[arg-type]
        )

    def combination_title(self) -> bool:
        if isinstance(self.title, PaperTitle):
            return (self.title.descriptive_title or self.title.subtitle) is not None
        return ":" in self.title

    @property
    def popular_title(self) -> str:
        if isinstance(self.title, PaperTitle):
            return self.title.popular_title
        return self.title.split(":", 1)[0]

    @property
    def descriptive_title(self) -> str:
        if isinstance(self.title, PaperTitle):
            return self.title.descriptive_title or ""

        if self.combination_title():
            return self.title.split(":", 1)[1]

        return ""

    def id(self) -> str:
        h = hashlib.md5(usedforsecurity=False)
        h.update(str(self.title).encode("utf-8"))
        if self.pdf_link is not None:
            h.update(self.pdf_link.encode("utf-8"))

        safe_title = self._re_unsafe_chars.sub("", str(self.title).replace(" ", "_"))[:48]
        return safe_title + "_" + self._re_unsafe_chars.sub("", str(base64.b64encode(h.digest())))[:8]
