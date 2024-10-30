import logging
from enum import Enum
from typing import Any, TypeVar

import requests
from urllib3.util import Url

log = logging.getLogger(__name__)


class ValidatorEvents(Enum):
    PARSE = "parse"
    VALIDATE = "validate"
    FILTER = "filter"
    REQUEST = "request"
    RESPONSE = "response"
    EXCEPTION = "exception"


class BaseEvent:
    _link: str
    _propagation_stopped: bool

    def __init__(self, link: str):
        self._link = link
        self._propagation_stopped = False

    @property
    def link(self) -> str:
        return self._link

    def is_propagation_stopped(self) -> bool:
        return self._propagation_stopped

    def stop_propagation(self) -> None:
        self._propagation_stopped = True


EventType = TypeVar("EventType", bound=BaseEvent)


class _EventWithURL(BaseEvent):
    _url: Url

    def __init__(self, link: str, url: Url):
        super().__init__(link)
        self._url = url

    @property
    def url(self) -> Url:
        return self._url

    @url.setter
    def url(self, value: Url) -> None:
        log.debug(f'Setting url from="{self._url}" to="{value}"')
        self._url = value


class ParseEvent(_EventWithURL):
    pass


class EventWithValidation(_EventWithURL):
    _valid = True
    _reason: str | None = None

    def set_valid(self, success: bool, reason: str | None) -> None:
        if self._valid:
            self._valid = success
            self._reason = reason

    def is_valid(self) -> bool:
        return self._valid

    def reason(self) -> str | None:
        return self._reason


EventWithValidationType = TypeVar("EventWithValidationType", bound=EventWithValidation)


class ValidateEvent(EventWithValidation):
    pass


class FilterEvent(EventWithValidation):
    pass


class RequestEvent(_EventWithURL):
    _request: requests.PreparedRequest
    _settings: dict[str, Any]

    def __init__(self, link: str, url: Url, request: requests.PreparedRequest, settings: dict[str, Any]):
        super().__init__(link, url)
        self._request = request
        self._settings = settings

    def request(self) -> requests.PreparedRequest:
        return self._request

    def settings(self) -> dict[str, Any]:
        return self._settings


class ResponseEvent(EventWithValidation):
    _response: requests.Response

    def __init__(self, link: str, url: Url, response: requests.Response):
        super().__init__(link, url)
        self._response = response

    def response(self) -> requests.Response:
        return self._response


class ExceptionEvent(BaseEvent):
    _exception: Exception

    def __init__(self, link: str, exception: Exception):
        super().__init__(link)
        self._exception = exception

    def exception(self) -> Exception:
        return self._exception
