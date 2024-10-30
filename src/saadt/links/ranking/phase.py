import logging
import threading
from abc import ABC, abstractmethod
from collections.abc import Iterator, Sequence
from typing import Any, override

import requests
import urllib3.util.url

from saadt.links import parsing
from saadt.links.util import safe_parse_url
from saadt.util.cache import LRUCache

from .rules import LinkType, LocationRuleContext, RequestRuleContext, RootContext, SessionRuleContext, UrlRuleContext
from .rules.base import AbstractRule, RuleContext

log = logging.getLogger(__package__)


class RankPhase(ABC):
    """Represents a Phase of ranking."""

    _rules: list[AbstractRule[Any]]

    def __init__(self, rules: Sequence[AbstractRule[Any]]) -> None:
        self._rules = list(rules)

    def rules(self) -> Iterator[AbstractRule[RuleContext]]:
        yield from self._rules

    @abstractmethod
    def prepare(self, ctx: RootContext, link: LinkType) -> RuleContext:
        pass


class RawPhase(RankPhase):
    @override
    def prepare(self, ctx: RootContext, link: LinkType) -> RuleContext:
        log.debug(f"{self.__class__.__name__}: preparing {str(link)}")
        return RuleContext(ctx, link)


class UrlPhase(RankPhase):
    @override
    def prepare(self, ctx: RootContext, link: LinkType) -> UrlRuleContext:
        log.debug(f"{self.__class__.__name__}: preparing {str(link)}")
        return UrlRuleContext(ctx, link, safe_parse_url(str(link)))


class LocationPhase(RankPhase):
    @override
    def prepare(self, ctx: RootContext, link: LinkType) -> LocationRuleContext:
        log.debug(f"{self.__class__.__name__}: preparing {str(link)}")
        if ctx.paper is None or ctx.path is None:
            raise ValueError("No paper or path specified")

        if not isinstance(link, parsing.ParsedLink):
            raise ValueError("Link must be an instance of ParsedLink")

        return LocationRuleContext(ctx, link)


class SessionPhase(RankPhase):
    def __init__(self, rules: Sequence[AbstractRule[Any]], session: requests.Session) -> None:
        super().__init__(rules)
        self._session = session

    @override
    def prepare(self, ctx: RootContext, link: LinkType) -> SessionRuleContext:
        log.debug(f"{self.__class__.__name__}: preparing {str(link)}")
        return SessionRuleContext(ctx, link, safe_parse_url(str(link)), self._session)


class RequestPhase(RankPhase):
    def __init__(self, rules: Sequence[AbstractRule[Any]], session: requests.Session) -> None:
        super().__init__(rules)
        self._session = session
        self._domain_locks = LRUCache[str, threading.Lock]()
        self._lock = threading.RLock()

    def _get_lock(self, url: urllib3.util.Url) -> threading.Lock:
        assert url.host is not None
        with self._lock:
            return self._domain_locks.setdefault(url.host, threading.Lock())

    def _request(self, url: urllib3.util.Url) -> requests.Response | None:
        if url.host is None:
            return None

        lock = self._get_lock(url)
        with lock:
            r: requests.Response | None = None
            try:
                r = self._session.get(url.url, stream=True, timeout=(3.05, 10))
                if (
                    r.encoding is not None
                    and r.ok
                    and (ct := r.headers.get("content-type")) is not None
                    and "text/html" in ct
                ):
                    r.content  # noqa
                r.close()
            except requests.exceptions.RequestException as exc:
                log.debug('"Request for url="%s" failed: %r"', url, exc)

            return r

    @override
    def prepare(self, ctx: RootContext, link: LinkType) -> RequestRuleContext:
        log.debug(f"{self.__class__.__name__}: preparing {str(link)}")
        url = safe_parse_url(str(link))
        if url.host is None:
            raise ValueError("Link is not a url")

        r = self._request(url)

        return RequestRuleContext(ctx, link, safe_parse_url(str(link)), self._session, r)
