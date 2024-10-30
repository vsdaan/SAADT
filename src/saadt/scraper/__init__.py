import logging.handlers
import multiprocessing.queues  # noqa
from abc import ABC, abstractmethod
from collections.abc import Iterable, Sequence
from typing import Any, TypeVar, Unpack, override

import requests

from saadt.model import Paper
from saadt.util.mputils import BaseWorker, ProcessExecutor, WorkerParams
from saadt.util.session import CancellableSession, create_session

log = logging.getLogger(__name__)
_T = TypeVar("_T", bound=Sequence[Any])


class Scraper(ABC):
    edition: str
    session: requests.Session

    def __init__(self, edition: str, proxies: dict[str, str] | None = None):
        self.edition = edition
        self.session = create_session(proxies=proxies)

    @abstractmethod
    def run(self) -> list[Paper]:
        pass


class ThreadedScraper(ProcessExecutor[_T, Paper], Scraper, ABC):
    def __init__(
        self, edition: str, max_workers: int = 2, max_threads: int = 10, proxies: dict[str, str] | None = None
    ):
        Scraper.__init__(self, edition, proxies=proxies)
        ProcessExecutor.__init__(self, max_workers, max_threads)

    @abstractmethod
    def _get_papers(self) -> list[_T]:
        pass

    @override
    def _prepare_items(self) -> Iterable[_T]:
        return self._get_papers()


class ScraperWorker(BaseWorker[_T, Paper]):
    edition: str
    session: CancellableSession

    def __init__(self, edition: str, proxies: dict[str, str] | None = None, **kwargs: Unpack[WorkerParams[_T, Paper]]):
        super().__init__(**kwargs)
        self.edition = edition

        size = 5 * self._threads + 10
        self.session = create_session(pool_size=size, stop_event=kwargs["stop_event"], proxies=proxies)

    @override
    def process_item(self, item: _T) -> Paper | None:
        try:
            paper = self._process_node(item)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            self.logger.error(f'Failed to process paper="{str(item[0])}": {exc}')
        else:
            return paper

        return None

    @abstractmethod
    def _process_node(self, node: _T) -> Paper:
        pass
