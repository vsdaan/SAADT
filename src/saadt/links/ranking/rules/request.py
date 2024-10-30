import itertools
import logging
import re
import warnings
from abc import ABC
from dataclasses import dataclass, field

import bibtexparser
import bibtexparser.middlewares.middleware
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from regex import regex
from urllib3.util import Url

from saadt.links.ranking.rules.base import AbstractRule, RuleContext
from saadt.scraper.util import TitleMatcher

PatternType = re.Pattern[str] | regex.Pattern[str]


@dataclass(slots=True)
class RequestRuleContext(RuleContext):
    url: Url
    session: requests.Session
    response: requests.Response | None

    _cached_content: BeautifulSoup | None = field(init=False, default=None)

    def content(self) -> BeautifulSoup | None:
        if self.response is None:
            return None
        if self._cached_content is not None:
            return self._cached_content
        if not self.response.content:
            return None

        warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
        self._cached_content = BeautifulSoup(self.response.content, "lxml")

        return self._cached_content


class RequestBaseRule(AbstractRule[RequestRuleContext], ABC):
    pass


@dataclass
class FailedRequest(RequestBaseRule):
    """
    Decreases score for failed requests.
    """

    score: int = -20

    def eval(self, ctx: RequestRuleContext) -> bool:
        if ctx.response is None:
            return False

        return not ctx.response.ok


@dataclass
class TitleInContent(RequestBaseRule):
    """
    Searches for a reference to the title on the website.
    """

    score: int = 20

    def eval(self, ctx: RequestRuleContext) -> bool:
        if ctx.root.paper is None or (content := ctx.content()) is None:
            return False

        pat = TitleMatcher.title_pattern(str(ctx.root.paper.title), False)

        return pat.search(content.get_text(separator=" ", strip=True)) is not None


@dataclass
class PartialTitleInContent(RequestBaseRule):
    """
    Searches for a reference to the title on the website.
    """

    score: float = 5.0

    def eval(self, ctx: RequestRuleContext) -> bool:
        if ctx.root.paper is None or (content := ctx.content()) is None:
            return False

        pat = re.compile(rf"({re.escape(ctx.root.paper.title.popular_title)})", re.I)

        count = sum(1 for _ in itertools.islice(pat.finditer(content.get_text(separator=" ", strip=True)), 19))
        ctx.score_modifier = count / 20.0

        return count > 0


@dataclass
class Citation(RequestBaseRule):
    """
    Searches for bibtex citations and checks if the entry matches the paper.
    """

    score: int = 50
    cite_rex: PatternType = field(init=False)

    parse_stack: list[bibtexparser.middlewares.middleware.Middleware] = field(init=False)

    def __post_init__(self) -> None:
        self.parse_stack = [
            self._restore_failed_blocks_middleware(),
            bibtexparser.middlewares.ResolveStringReferencesMiddleware(allow_inplace_modification=True),
            bibtexparser.middlewares.RemoveEnclosingMiddleware(allow_inplace_modification=True),
            # Entries are sometimes double enclosed
            bibtexparser.middlewares.RemoveEnclosingMiddleware(allow_inplace_modification=True),
        ]
        self.cite_rex = self._build_cite_rex()

    @staticmethod
    def _build_cite_rex() -> PatternType:
        ws = r"""[^\S\r\n]*"""
        entry = r"""@[a-zA-Z]+{[^~\\"#'(),={}%\s]+,"""
        field_key = r"""[^~\\"#'(),={}%\s]+"""
        field_val = (
            r"""(?:[^{}"\s][^{}\r\n]+|(?:{(?:"""
            + rf"(?!.*{entry})"
            + r""".+(?:$\s|(?=}\s*,?\s*}?\s*$)))+})+|"(?:"""
            + rf"(?!.*{entry})"
            + r"""[^"\r\n]+(?:$\s|(?="\s*,?\s*}?\s*$)))+")"""
        )
        fieldkv = rf"""^{ws}{field_key}{ws}={ws}{field_val}{ws}"""

        return re.compile(rf"""{ws}{entry}{ws}$\s(?:{fieldkv},{ws}$\s)*{fieldkv},?{ws}\s?{ws}}}""", re.M)

    def _restore_failed_blocks_middleware(self) -> bibtexparser.middlewares.LibraryMiddleware:
        def transform(library: bibtexparser.Library) -> bibtexparser.Library:
            block: bibtexparser.model.ParsingFailedBlock
            for block in library.failed_blocks:
                err_block = block.ignore_error_block
                if isinstance(err_block, bibtexparser.model.Entry):
                    library.add(err_block)
            return library

        m = bibtexparser.middlewares.LibraryMiddleware()
        m.transform = transform  # type: ignore[method-assign]

        return m

    def _parse(self, bibtex_str: str) -> bibtexparser.Library:
        _logger = logging.getLogger()
        saved_val = _logger.disabled
        try:
            _logger.disabled = True
            # bibtexparser uses the root logger...
            return bibtexparser.parse_string(bibtex_str, parse_stack=self.parse_stack)
        finally:
            _logger.disabled = saved_val

    def eval(self, ctx: RequestRuleContext) -> bool:
        if ctx.root.paper is None or (content := ctx.content()) is None:
            return False

        matcher: TitleMatcher[str] | None = None
        for m in self.cite_rex.finditer(str(content)):  # citation is sometimes in data attr or js
            for entry in self._parse(m.group(0)).entries:
                if (title_entry := entry.get("title")) is None:
                    continue

                matcher = matcher or TitleMatcher([str(ctx.root.paper.title)])

                val = " ".join([s.strip() for s in title_entry.value.splitlines() if s])
                if matcher.match(val) is not None:
                    return True

        return False
