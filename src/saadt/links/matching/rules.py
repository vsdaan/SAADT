import re
from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import NamedTuple

import bibtexparser
import regex

from saadt.model import Conference

Pattern = re.Pattern[str] | regex.Pattern[str]


def title_regex(title: str) -> str:
    # 5% error rate
    errs = max(round(len(title) * 0.05), 1)

    return f"({regex.escape(title)}){{e<={errs}}}"


class RuleEvalContext(NamedTuple):
    content: str


class BaseRule(ABC):
    score: int

    conference: Conference
    paper: str

    def __init__(self, conference: Conference, paper: str) -> None:
        self.conference = conference
        self.paper = paper

    @abstractmethod
    def eval(self, context: RuleEvalContext) -> bool:
        pass


class RulePack:
    _rules: tuple[BaseRule, ...]
    """Instantiated rules. This is a tuple to enforce immutability."""

    def __init__(self, rules: Iterable[BaseRule]):
        self._rules = tuple(sorted(rules, key=lambda r: r.score, reverse=True))

    def rules(self) -> Iterator[BaseRule]:
        yield from self._rules


@dataclass
class RulePackContext:
    conference: Conference
    paper: str


class RuleSet:
    _rule_classes: list[type[BaseRule]] = []

    def register(self, rule: type[BaseRule]) -> None:
        self._rule_classes.append(rule)

    def get_rulepack(self, context: RulePackContext) -> RulePack:
        rules = [rule_class(context.conference, context.paper) for rule_class in self._rule_classes]

        return RulePack(rules)


class RuleFullTitleMatch(BaseRule):
    score = 90
    rex: Pattern

    def __init__(self, conference: Conference, paper: str):
        super().__init__(conference, paper)

        self.rex = regex.compile(rf"(?:^|\s|\W){title_regex(paper)}(?:$|\s|\W)", re.I)

    def eval(self, context: RuleEvalContext) -> bool:
        return self.rex.search(context.content) is not None


class RuleCitation(BaseRule):
    """
    Searches for bibtex citations and checks if the entry matches the paper.

    The score is changed according to the kind of match.
    - Full title match: 100
    """

    score = 100  # Set to 100 to make sure it's run before FullTitleMatch
    cite_rex: Pattern
    title_rex: Pattern

    def __init__(self, conference: Conference, paper: str):
        super().__init__(conference, paper)

        self.cite_rex = re.compile(
            r"""@[a-zA-Z]+{[^~\\"#'(),={}%\s]+,\s*$(?:\s^\s*[^~\\"#'(),={}%\s]+\s*=(?:[^{}\n]+|(?:\s*{[\s\S]*})+),?\s*$)+$\s}""",
            re.MULTILINE,
        )

        self.title_rex = regex.compile(rf"(?:^|\s|\W){title_regex(paper)}(?:$|\s|\W)", re.I)

    def eval(self, context: RuleEvalContext) -> bool:
        # reset score
        self.score = 0

        for m in self.cite_rex.finditer(context.content):
            db = bibtexparser.parse_string(m.group(0))
            for entry in db.entries:
                title_entry = entry.get("title")
                if title_entry is None:
                    continue

                if self.title_rex.search(title_entry.value) is not None:
                    self.score = 100
                    return True

        return False


def get_rules() -> list[type[BaseRule]]:
    return [RuleFullTitleMatch, RuleCitation]


def get_ruleset() -> RuleSet:
    rule_set = RuleSet()
    for rule in get_rules():
        rule_set.register(rule)

    return rule_set
