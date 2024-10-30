import dataclasses
import pathlib
import threading
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar, no_type_check

import urllib3.util

from saadt.links import parsing


@dataclasses.dataclass(slots=True)
class RootContext:
    paper: parsing.ParsedPaper | None = None
    path: pathlib.Path | None = None
    cache: dict[str, Any] = dataclasses.field(init=False, default_factory=dict)
    lock: threading.RLock = dataclasses.field(init=False, default_factory=threading.RLock)


LinkType = str | parsing.ParsedLink


@dataclasses.dataclass(slots=True)
class RuleContext:
    root: RootContext
    link: LinkType
    score_modifier: float = dataclasses.field(init=False, default=0.0)


RuleContextType = TypeVar("RuleContextType", bound=RuleContext)


class AbstractRule(ABC, Generic[RuleContextType]):
    # noinspection all
    @no_type_check
    def __new__(cls, *args, **kwargs):
        # Hack for fixing dataclasses and abstract score property
        if hasattr(cls, "__dataclass_fields__") and "score" in cls.__dataclass_fields__:
            cls.__abstractmethods__ = frozenset(el for el in cls.__abstractmethods__ if el != "score")
            dataclasses._set_new_attribute(cls, "score", None)

        return super().__new__(cls)

    @abstractmethod
    def eval(self, ctx: RuleContextType) -> bool:
        """
        Evaluates the given context.

        If true, the score will be added to the link.
        A score can be negative.
        """

    @property
    @abstractmethod
    def score(self) -> float:
        pass

    def __str__(self) -> str:
        cls = self.__class__.__name__
        return f"{cls}"


@dataclasses.dataclass(slots=True)
class Not(AbstractRule[RuleContextType]):
    rule: AbstractRule[RuleContextType]

    def eval(self, ctx: RuleContextType) -> bool:
        return not self.rule.eval(ctx)

    @property
    def score(self) -> float:
        return self.rule.score * -1


class Parseable(AbstractRule[RuleContextType]):
    score: int = -100

    def eval(self, ctx: RuleContextType) -> bool:
        try:
            urllib3.util.parse_url(str(ctx.link))
        except ValueError:
            return True
        return False
