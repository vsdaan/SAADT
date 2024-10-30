import json
from dataclasses import dataclass, field
from typing import Any

from saadt.links import parsing
from saadt.links.ranking import RankedLink


@dataclass(slots=True)
class ComparedPaper:
    title: str
    groundtruth_link: str | None
    links: tuple[RankedLink, ...]
    exact_match_index: int = field(default=-1)
    closest_partial_match_index: int = field(default=-1)
    best_match_index: int = field(default=-1)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ComparedPaper":
        for x in d["links"]:
            if "metadata" in x:
                del x["metadata"]

        return cls(
            title=d["title"],
            groundtruth_link=d["groundtruth_link"],
            links=tuple(RankedLink(**x) for x in d["links"]),
            exact_match_index=d["exact_match_index"],
            closest_partial_match_index=d["closest_partial_match_index"],
            best_match_index=d["best_match_index"],
        )


def parse_links_file(path: str) -> list[parsing.ParsedPaper]:
    with open(path) as f:
        raw: list[dict[str, str | list[str | dict[str, Any]] | dict[str, str]]] = json.load(f)

    result: list[parsing.ParsedPaper] = []
    for entry in raw:
        result.append(parsing.ParsedPaper.from_dict(entry))
    return result


def parse_ranked_file(path: str) -> dict[str, list[RankedLink]]:
    with open(path) as f:
        raw: list[dict[str, list[dict[str, Any]]]] = json.load(f)

    result: dict[str, list[RankedLink]] = {}
    for entry in raw:
        # Fix stupid output...
        pid, links = next(iter(entry.items()))
        result[pid] = [RankedLink(**x) for x in links]
    return result
