import dataclasses
from typing import Any, override

from saadt import model


@dataclasses.dataclass(slots=True)
class ParsedLink:
    link: str
    locations: list[int]
    occurrences: int
    page: int
    page_length: int
    annotation: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ParsedLink":
        return cls(**d)

    def __str__(self) -> str:
        return self.link


@dataclasses.dataclass
class ParsedPaper(model.Paper):
    links: list[ParsedLink] = dataclasses.field(default_factory=list)
    pages: int | None = dataclasses.field(default=None)

    @classmethod
    def from_paper(cls, paper: model.Paper, links: list[ParsedLink], pages: int) -> "ParsedPaper":
        return cls(
            title=paper.title,
            page_link=paper.page_link,
            pdf_link=paper.pdf_link,
            appendix_link=paper.appendix_link,
            badges=paper.badges.copy(),
            artifact_links=paper.artifact_links.copy(),
            links=links,
            pages=pages,
        )

    @override
    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()

        d["links"] = [link.to_dict() for link in self.links]
        d["pages"] = self.pages
        return d

    @classmethod
    def from_dict(cls, d: dict[str, str | list[str | dict[str, Any]] | dict[str, str]]) -> "ParsedPaper":
        p = super().from_dict(d)
        assert isinstance(p, ParsedPaper)

        p.pages = d.get("pages")  # type: ignore[assignment]
        if "links" in d:
            p.links = [ParsedLink.from_dict(pl) for pl in d["links"]]  # type: ignore[arg-type]

        return p
