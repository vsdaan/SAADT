import re
import socket
from abc import ABC, abstractmethod
from typing import Any, TypeVar, override

import requests
from urllib3.util import Url, parse_url


class BaseConstraint(ABC):
    def __str__(self) -> str:
        cls = self.__class__.__name__
        return f"{cls}"

    @abstractmethod
    def validate(self, *args: Any, **kwargs: Any) -> tuple[bool, str]:
        pass


ConstraintType = TypeVar("ConstraintType", bound=BaseConstraint)


class Constraint(BaseConstraint, ABC):
    @abstractmethod
    def validate(self, url: Url, resp: requests.Response | None = None) -> tuple[bool, str]:
        raise NotImplementedError()


class RawURLConstraint(BaseConstraint, ABC):
    @abstractmethod
    def validate(self, url: str) -> tuple[bool, str]:
        raise NotImplementedError()


class NotHost(Constraint):
    """
    Fails if the given host matches the host of the url to validate.
    """

    def __init__(self, host: str):
        super().__init__()
        self.host = host

    def __str__(self) -> str:
        cls = self.__class__.__name__
        return f"{cls}<{self.host}>"

    def validate(self, url: Url, resp: requests.Response | None = None) -> tuple[bool, str]:
        host = url.host
        if resp is not None:
            host = parse_url(resp.url).host

        return host != self.host, str(self)


class NotDomain(Constraint):
    def __init__(self, domain: str):
        super().__init__()
        self.domain = domain

    def __str__(self) -> str:
        cls = self.__class__.__name__
        return f"{cls}<{self.domain}>"

    @override
    def validate(self, url: Url, resp: requests.Response | None = None) -> tuple[bool, str]:
        host = url.host
        if resp is not None:
            host = parse_url(resp.url).host

        assert host is not None

        return not host.endswith(self.domain), str(self)


class HostExists(Constraint):
    @override
    def validate(self, url: Url, resp: requests.Response | None = None) -> tuple[bool, str]:
        host = url.host
        if resp is not None:
            # Checking with response is pointless...
            return True, ""

        assert host is not None

        try:
            addr = socket.gethostbyname(host)
            if addr == "127.0.0.1":
                return False, f"HostExists<'{host}'=127.0.0.1>"
        except socket.gaierror:
            return False, f"HostExists<'{host}'=False>"

        return True, ""


class HasHost(Constraint):
    @override
    def validate(self, url: Url, resp: requests.Response | None = None) -> tuple[bool, str]:
        return url.host is not None, str(self)


class StatusCode(Constraint):
    @override
    def validate(self, url: Url, resp: requests.Response | None = None) -> tuple[bool, str]:
        if resp is None:
            return True, ""

        return resp.ok, f"StatusCode<{resp.status_code}: {resp.reason}>"


class SigninPage(Constraint):
    login_paths = {"login", "sign-in", "sign_in", "signin"}

    @override
    def validate(self, url: Url, resp: requests.Response | None = None) -> tuple[bool, str]:
        if resp is None:
            return True, ""

        url = parse_url(resp.url)
        if url.path is not None:
            path = url.path.strip("/").split("/")
            if len(path) > 0:
                if path[-1] in self.login_paths:
                    return False, f"SigninPage<{url.url}>"

        return True, ""


class ProbablyJoinedSentence(RawURLConstraint):
    regex = re.compile(r"""[a-zA-Z0-9]+\.[A-Z][a-zA-Z]+""")

    def validate(self, url: str) -> tuple[bool, str]:
        return self.regex.fullmatch(url) is None, str(self)


class Duplicate(Constraint):
    links: set[str] = set()

    @override
    def validate(self, url: Url, resp: requests.Response | None = None) -> tuple[bool, str]:
        url_string = url.url
        if resp is not None:
            url_string = resp.url

        if url_string in self.links:
            return False, f"Duplicate<{url_string}>"

        self.links.add(url_string)
        return True, ""
