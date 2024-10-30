import logging
import random
import time
from multiprocessing.synchronize import Event
from typing import overload, override

import requests
import urllib3
from requests.adapters import HTTPAdapter

from .exceptions import CancelledError

log = logging.getLogger(__name__)


class RetryableSession(requests.Session):
    fallback_user_agent = "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0"

    def send(self, request: requests.PreparedRequest, **kwargs):  # type: ignore[no-untyped-def]
        resp = super().send(request, **kwargs)

        if resp.status_code == 403:
            log.debug("Retrying request, changing User-Agent (status=403): %s", request.url)
            resp.close()
            request.headers.update({"User-Agent": self.fallback_user_agent})
            resp = super().send(request, **kwargs)

        for i in range(4):
            if resp.status_code != 429:
                break

            log.debug("Retrying request (status=429, %d/4): %s", i + 1, request.url)
            resp.close()
            time.sleep(random.randint(3, 7))
            super().send(request, **kwargs)

        return resp


class CancellableSession(RetryableSession):
    def __init__(self, stop_event: Event):
        super().__init__()
        self._stop_event = stop_event

    @override
    def request(  # type: ignore[no-untyped-def]
        self,
        method,
        url,
        params=None,
        data=None,
        headers=None,
        cookies=None,
        files=None,
        auth=None,
        timeout=None,
        allow_redirects=True,
        proxies=None,
        hooks=None,
        stream=None,
        verify=None,
        cert=None,
        json=None,
    ) -> requests.Response:
        if self._stop_event.is_set():
            raise CancelledError("session is cancelled.")
        return super().request(
            method,
            url,
            params,
            data,
            headers,
            cookies,
            files,
            auth,
            timeout,
            allow_redirects,
            proxies,
            hooks,
            stream,
            verify,
            cert,
            json,
        )


@overload
def create_session(
    pool_size: int = 10,
    stop_event: None = None,
    respect_retry_after_header: bool = False,
    proxies: dict[str, str] | None = None,
) -> requests.Session: ...


@overload
def create_session(
    pool_size: int, stop_event: Event, respect_retry_after_header: bool = False, proxies: dict[str, str] | None = None
) -> CancellableSession: ...


def create_session(
    pool_size: int = 10,
    stop_event: Event | None = None,
    respect_retry_after_header: bool = False,
    proxies: dict[str, str] | None = None,
) -> requests.Session:
    if stop_event is None:
        s = RetryableSession()
    else:
        s = CancellableSession(stop_event)
    if proxies is not None:
        s.proxies.update(proxies)

    retry = urllib3.Retry(respect_retry_after_header=respect_retry_after_header, total=3)
    s.mount("http://", HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size, max_retries=retry))
    s.mount("https://", HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size, max_retries=retry))

    return s
