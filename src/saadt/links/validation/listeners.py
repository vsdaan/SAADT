from abc import ABC, abstractmethod
from typing import Generic, override

from urllib3.util import Url, parse_url

from saadt.links.validation.constraints import Constraint, ConstraintType, RawURLConstraint
from saadt.util.log import LoggerInterface
from saadt.util.session import create_session

from .events import (
    EventType,
    EventWithValidationType,
    ExceptionEvent,
    ParseEvent,
    ResponseEvent,
    ValidateEvent,
)


class EventListener(ABC, Generic[EventType]):
    @abstractmethod
    def on_event(self, event: EventType) -> None:
        raise NotImplementedError()

    def __str__(self) -> str:
        cls = self.__class__.__name__
        return f"{cls}"


class AbstractConstraintListener(
    Generic[ConstraintType, EventWithValidationType], EventListener[EventWithValidationType], ABC
):
    constraint: ConstraintType

    def __init__(self, constraint: ConstraintType):
        self.constraint = constraint

    @override
    def __str__(self) -> str:
        cls = self.__class__.__name__
        return f"{cls}<{self.constraint}>"

    def _process_constraint_result(self, event: EventWithValidationType, ok: bool, reason: str) -> None:
        event.set_valid(ok, reason)
        if not ok:
            event.stop_propagation()


class ConstraintListener(AbstractConstraintListener[Constraint, ValidateEvent | ResponseEvent]):
    def on_event(self, event: ValidateEvent | ResponseEvent) -> None:
        resp = None
        if isinstance(event, ResponseEvent):
            resp = event.response()

        ok, reason = self.constraint.validate(event.url, resp)
        self._process_constraint_result(event, ok, reason)


class RawURLConstraintListener(AbstractConstraintListener[RawURLConstraint, ValidateEvent]):
    def on_event(self, event: ValidateEvent) -> None:
        ok, reason = self.constraint.validate(event.link)
        self._process_constraint_result(event, ok, reason)


class MissingScheme(EventListener[ParseEvent]):
    @override
    def on_event(self, event: ParseEvent) -> None:
        url = event.url
        if not url.scheme:
            event.url = Url("http", url.auth, url.host, url.port, url.path, url.query, url.fragment)


class ResolveDOI(EventListener[ParseEvent]):
    def __init__(self) -> None:
        self.session = create_session()

    def on_event(self, event: ParseEvent) -> None:
        url = event.url
        assert url.host is not None

        # TODO: try except?
        if url.host.endswith("doi.org"):
            resp = self.session.head(url.url)
            if "Location" in resp.headers:
                url = parse_url(resp.headers["Location"])

            event.url = url


class TransformGithub(EventListener[ParseEvent]):
    @override
    def on_event(self, event: ParseEvent) -> None:
        url = event.url
        assert url.host is not None
        if url.path is None:
            return

        if url.host.endswith("github.com"):
            path = url.path.strip("/").split("/")
            if "tree" in path:
                return

            i = -1
            if "releases" in path:
                i = path.index("releases")
            elif "commit" in path:
                i = path.index("commit")
            if i != -1:
                path[i] = "tree"
                if len(path) == i + 1:
                    path = path[:i]
                if "tag" in path:
                    path.remove("tag")

                event.url = Url(url.scheme, url.auth, url.host, url.port, f"/{'/'.join(path)}", None, None)


class TracebackListener(EventListener[ExceptionEvent]):
    def __init__(self, logger: LoggerInterface) -> None:
        self._logger = logger

    @override
    def on_event(self, event: ExceptionEvent) -> None:
        self._logger.error("An error occurred for link %s: %s", event.link, event.exception())
        self._logger.debug("Traceback:", exc_info=event.exception())
