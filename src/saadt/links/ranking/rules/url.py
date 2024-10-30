import ipaddress
import logging
import re
from abc import ABC
from dataclasses import InitVar, dataclass, field

import dns.nameserver
import dns.resolver
from urllib3.util import Url

from .base import AbstractRule, RuleContext

log = logging.getLogger(__package__)


@dataclass(slots=True)
class UrlRuleContext(RuleContext):
    url: Url


class UrlBaseRule(AbstractRule[UrlRuleContext], ABC):
    pass


@dataclass
class NotHost(UrlBaseRule):
    host: str
    score: int = -100

    def eval(self, ctx: UrlRuleContext) -> bool:
        if ctx.url.host is None:
            return False

        return ctx.url.host == self.host


@dataclass
class Domain(UrlBaseRule):
    host: str
    score: int
    check_path: bool = False

    def eval(self, ctx: UrlRuleContext) -> bool:
        if ctx.url.host is None:
            return False
        pos = ctx.url.host.rfind(self.host)
        if pos == -1 or ctx.url.host[pos:] != self.host:
            return False

        if self.check_path and (ctx.url.path is None or ctx.url.path.strip("/") == ""):
            return False

        return pos == 0 or ctx.url.host[pos - 1] == "."

    def __str__(self) -> str:
        cls = self.__class__.__name__
        return f"{cls}<{self.host}>"


@dataclass
class NotDomain(Domain):
    score: int = -100
    check_path: bool = False

    def eval(self, ctx: UrlRuleContext) -> bool:
        return super().eval(ctx)


@dataclass
class Regex(UrlBaseRule):
    pattern: re.Pattern[str] = field(init=False)
    pattern_str: InitVar[str | tuple[str, int]]
    score: int

    def __post_init__(self, pattern_str: str | tuple[str, int]) -> None:
        flags = 0
        if isinstance(pattern_str, tuple):
            pattern, flags = pattern_str
        else:
            pattern = pattern_str
        self.pattern = re.compile(pattern, flags)

    def eval(self, ctx: RuleContext) -> bool:
        return self.pattern.fullmatch(str(ctx.link)) is not None

    def __str__(self) -> str:
        cls = self.__class__.__name__
        if cls == "Regex":
            return f"{cls}<{self.pattern.pattern}>"
        return f"{cls}"


@dataclass
class JoinedSentence(Regex):
    pattern_str: InitVar[str] = r"""[a-zA-Z0-9-_]+\.[A-Z][a-zA-Z]+"""
    score: int = -100


@dataclass
class MaybeJoinedSentence(Regex):
    """
    Slightly decreases the score of a URL that could be a joined sentence.
    Mostly to make sure that the actual URL has a higher score.
    """

    pattern_str: InitVar[str] = (
        r""".*\/(?:(?:[0-9]{3,}(?:\.?[A-Z][a-z]|[A-Z](?=\.)|\.[0-9])|(?:[a-zA-Z0-9_-]+(?:\.[A-Z])))(?:\.?[a-zA-Z]+|\.[0-9]+)*|[\w-]+\.)"""
    )
    score: int = -1


@dataclass
class GithubRepo(Regex):
    pattern_str: InitVar[tuple[str, int]] = (
        r"""(?:https?://)?github\.com/[a-z0-9-]+/[a-z0-9._-]+(?:/.+|/?)""",
        re.I,
    )
    score: int = 10


@dataclass
class GithubStable(Regex):
    """
    Extension of GithubRepo, so low score
    """

    pattern_str: InitVar[tuple[str, int]] = (
        r"""(?:https?://)?github\.com/[a-z0-9-]+/[a-z0-9._-]+/(?:(?:tree|releases/tag)/[a-z0-9_\-\.]+|(?:commit|tree)/[a-f0-9]{40})/?""",
        re.I,
    )
    score: int = 2


@dataclass
class GithubWiki(Regex):
    """
    Decrease the score of Github Wikis.
    """

    pattern_str: InitVar[tuple[str, int]] = (
        r"""(?:https?://)?github\.com/[a-z0-9-]+/[a-z0-9._-]+/wiki(?:/.+|/?)""",
        re.I,
    )
    score: int = -5


@dataclass
class ZenodoArchive(Regex):
    pattern_str: InitVar[tuple[str, int]] = (
        r"""(?:https?://)zenodo\.org/record/[0-9-]+(?:/.*)?(?:#.*)?""",
        re.I,
    )
    score: int = 10


@dataclass
class DoiZenodo(Regex):
    pattern_str: InitVar[tuple[str, int]] = (
        r"https?://(?:dx\.)?doi.org/[^/]+/zenodo.[0-9]+",
        re.I,
    )
    score: int = 10


@dataclass
class HostExists(UrlBaseRule):
    """
    Checks if the host exists.

    This rule uses preconfigured nameservers due to issues with many ISP provided nameservers.
    To disable this, set `use_default_nameservers` to True
    """

    use_default_nameservers: InitVar[bool] = False
    score: int = -100

    resolver: dns.resolver.Resolver = field(init=False)
    _cache: dns.resolver.CacheBase = field(init=False, default_factory=dns.resolver.LRUCache)
    _failed_cache: set[str] = field(init=False, default_factory=set)

    def __post_init__(self, use_default_nameservers: bool) -> None:
        # systemd-resolved doesn't resolve TLDs using DNS...
        if use_default_nameservers:
            self.resolver = dns.resolver.Resolver()
        else:
            self.resolver = dns.resolver.Resolver(configure=False)
            self.resolver.nameservers = ["1.1.1.1", "2606:4700:4700::1111", "8.8.8.8", "2001:4860:4860::8888"]

        self.resolver.cache = self._cache

    def get_authoritative_nameserver(self, domain: str) -> str | None:
        n = dns.name.from_text(domain)
        ns_resolver = dns.resolver.Resolver(configure=False)
        ns_resolver.cache = self._cache

        nameserver = self.resolver.nameservers[0]
        depth = 2

        last = False
        while not last:
            ns_resolver.nameservers = [nameserver]
            s = n.split(depth)

            last = s[0].to_text() == "@"
            sub = s[1]

            log.debug(f"HostExists<{domain}>: Looking up {sub}")
            try:
                response = ns_resolver.resolve(sub, dns.rdatatype.NS, raise_on_no_answer=False)
            except dns.exception.DNSException as exc:
                log.debug(f"HostExists<{domain}>: lookup error: {exc}")
                return None

            rrset: dns.rrset.RRset | None
            if len(response.response.authority) > 0:
                rrset = response.response.authority[0]
            else:
                rrset = response.response.answer[0]
            assert rrset is not None
            rr = rrset[0]
            if rr.rdtype != dns.rdatatype.SOA:
                authority = rr.target
                log.debug(f"{authority} is authoritative for {sub}")
                try:
                    rrset = self.resolver.resolve(authority).rrset
                    assert rrset is not None
                    nameserver = rrset[0].to_text()
                except dns.exception.DNSException as exc:
                    log.debug(f"HostExists<{domain}>: lookup error for authority: {exc}")
                    return None

            depth += 1

        return str(nameserver)

    def resolve(self, domain: str) -> str | None:
        s = ""
        if any(s for sub in reversed(domain.split(".")) if (s := ".".join((sub, s))).rstrip(".") in self._failed_cache):
            return None

        try:
            response = self.resolver.resolve(domain)
            assert response.rrset is not None
            return str(response.rrset[0])
        except dns.exception.DNSException as exc:
            log.debug(f"HostExists<{domain}>: resolve error: {exc}")
            self._failed_cache.add(domain)
        return None

    def eval(self, ctx: UrlRuleContext) -> bool:
        assert ctx.url.host is not None
        result = self.resolve(ctx.url.host)

        return result is None or ipaddress.ip_address(result).is_private
