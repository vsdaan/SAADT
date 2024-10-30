import logging
from collections.abc import Iterable
from enum import Enum
from typing import Any

import requests
import urllib3
from urllib3.util import Url

from saadt.links.validation.eventdispatcher import EventDispatcher
from saadt.links.validation.events import (
    ExceptionEvent,
    FilterEvent,
    ParseEvent,
    RequestEvent,
    ResponseEvent,
    ValidateEvent,
    ValidatorEvents,
)
from saadt.util.session import create_session

from . import constraints, listeners

log = logging.getLogger(__name__)


class LinkState(Enum):
    ERROR = "error"
    INVALID = "invalid"
    FUNCTIONAL = "functional"


class UrlValidator:
    dispatcher: EventDispatcher
    session: requests.Session

    _result: dict[str, list[tuple[str, str | None]]]

    def __init__(
        self,
        register_default: bool = True,
        session: requests.Session | None = None,
        headers: dict[str, str] | None = None,
        cookies: dict[str, str] | None = None,
    ):
        self.dispatcher = EventDispatcher()
        self.session = session or create_session()
        self.session.headers.update(headers or {})
        self.session.cookies.update(cookies or {})
        self._result = {e.value: [] for e in LinkState}

        # Register default listeners
        if register_default:
            self.dispatcher.register(ValidatorEvents.PARSE, listeners.MissingScheme(), 100)
            self.dispatcher.register(
                ValidatorEvents.VALIDATE,
                listeners.ConstraintListener(constraints.HasHost()),
                100,
            )
            self.dispatcher.register(
                ValidatorEvents.RESPONSE,
                listeners.ConstraintListener(constraints.StatusCode()),
            )

    def _init_result(self) -> None:
        self._result = {e.value: [] for e in LinkState}

    def _parse_url(self, url_string: str) -> Url:
        parsed = urllib3.util.parse_url(url_string)

        event = ParseEvent(url_string, parsed)
        self.dispatcher.dispatch(ValidatorEvents.PARSE, event)

        return event.url

    def _validate_url(self, url_string: str, url: Url) -> tuple[bool, str | None]:
        event = ValidateEvent(url_string, url)
        self.dispatcher.dispatch(ValidatorEvents.VALIDATE, event)

        return event.is_valid(), event.reason()

    def _filter_url(self, link: str, url: Url) -> tuple[bool, str | None]:
        event = FilterEvent(link, url)
        self.dispatcher.dispatch(ValidatorEvents.FILTER, event)

        return event.is_valid(), event.reason()

    def _request(self, link: str, url: Url) -> requests.Response:
        req = requests.Request(method="GET", url=url)
        prepped = self.session.prepare_request(req)
        settings: dict[str, Any] = self.session.merge_environment_settings(prepped.url, {}, True, None, None)  # type: ignore[assignment]
        settings.setdefault("allow_redirects", True)
        settings.setdefault("timeout", (6.05, 27))

        self.dispatcher.dispatch(ValidatorEvents.REQUEST, RequestEvent(link, url, prepped, settings))

        return self.session.send(prepped, **settings)

    def _validate_response(self, link: str, url: Url, resp: requests.Response) -> tuple[bool, str | None]:
        event = ResponseEvent(link, url, resp)
        self.dispatcher.dispatch(ValidatorEvents.RESPONSE, event)

        return event.is_valid(), event.reason()

    def _process_link(self, link: str) -> None:
        url = self._parse_url(link)
        log.debug("Parsed link as: %s", url)

        # Validate url
        ok, reason = self._validate_url(link, url)
        if not ok:
            self._result[LinkState.INVALID.value].append((link, reason))
            return

        # Filter url
        ok, reason = self._filter_url(link, url)
        if not ok:
            self._result[LinkState.INVALID.value].append((link, reason))
            return

        resp = self._request(link, url)
        resp.close()
        ok, reason = self._validate_response(link, url, resp)
        if not ok:
            self._result[LinkState.INVALID.value].append((link, reason))
            return

        self._result[LinkState.FUNCTIONAL.value].append((link, ""))

    def _handle_exception(self, link: str, ex: Exception) -> None:
        event = ExceptionEvent(link, ex)
        self.dispatcher.dispatch(ValidatorEvents.EXCEPTION, event)

    def run(self, links: Iterable[str]) -> dict[str, list[tuple[str, str | None]]]:
        self._init_result()
        log.debug("Starting link validation")
        for link in links:
            log.info(f"Processing link: {link}")
            try:
                self._process_link(link)
            except KeyboardInterrupt:
                raise
            except Exception as ex:
                self._handle_exception(link, ex)
                self._result[LinkState.ERROR.value].append((link, str(ex)))
                continue

        log.debug("Validation finished")

        return self._result
