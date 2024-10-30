import logging
import multiprocessing as mp
import multiprocessing.queues  # noqa
import multiprocessing.synchronize
import threading
from abc import abstractmethod
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Generic, TypedDict, TypeVar, Unpack, final

from saadt.util.log import MultiProcessingLogger

_TD = TypeVar("_TD", bound=Any)
_TF = TypeVar("_TF", bound=Any)
log = logging.getLogger(__name__)


class WorkerParams(Generic[_TD, _TF], TypedDict):
    threads: int
    stop_event: mp.synchronize.Event
    dispatch_queue: mp.queues.Queue[_TD | None]
    finished_queue: mp.queues.Queue[_TF | None]
    logger: MultiProcessingLogger


def logger_thread(queue: multiprocessing.queues.Queue[logging.LogRecord | None]) -> None:
    while True:
        record = queue.get()
        if record is None:
            break
        logger = logging.getLogger(record.name)
        logger.handle(record)


class BaseWorker(Generic[_TD, _TF]):
    _threads: int

    dispatch_queue: mp.queues.Queue[_TD | None]
    executor: ThreadPoolExecutor
    finished_queue: mp.queues.Queue[_TF | None]
    processing_queue: mp.queues.Queue[int]
    stop_event: mp.synchronize.Event

    def __init__(
        self,
        threads: int,
        stop_event: mp.synchronize.Event,
        dispatch_queue: mp.queues.Queue[_TD | None],
        finished_queue: mp.queues.Queue[_TF | None],
        logger: MultiProcessingLogger,
    ):
        self._threads = threads
        self.stop_event = stop_event
        self.dispatch_queue = dispatch_queue
        self.finished_queue = finished_queue
        self.logger = logger

        self.processing_queue = mp.Queue(self._threads)
        for i in range(self._threads):
            self.processing_queue.put(i)

        self.executor = ThreadPoolExecutor(max_workers=self._threads, thread_name_prefix=f"{mp.current_process().name}")

    def run(self) -> None:
        self.logger.debug("Worker started")

        while not self.stop_event.is_set():
            # Blocks until the thread is free
            self.processing_queue.get()

            item = self.dispatch_queue.get()
            if item is None:
                break

            self.executor.submit(self._dispatch_item, item)

        self.shutdown()

    def _dispatch_item(self, item: _TD) -> None:
        try:
            processed = self.process_item(item)
            if processed is not None:
                self.finished_queue.put(processed)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            self.logger.error("Exception while processing item", exc_info=e)

        self.processing_queue.put(threading.get_ident())

    @abstractmethod
    def process_item(self, item: _TD) -> _TF | None:
        pass

    def shutdown(self) -> None:
        self.executor.shutdown(False)
        self.processing_queue.close()
        self.processing_queue.join_thread()
        self.executor.shutdown(True)
        self.finished_queue.put(None)
        self.logger.debug("worker finished")


class ProcessExecutor(Generic[_TD, _TF]):
    _workers: list[mp.process.BaseProcess]

    max_workers: int
    max_threads: int

    _dispatch_queue: mp.queues.Queue[_TD | None]
    _finished_queue: mp.queues.Queue[_TF | None]

    _stop_event: mp.synchronize.Event

    _log_queue: mp.queues.Queue[logging.LogRecord | None]
    _log_thread: threading.Thread

    _ctx: mp.context.SpawnContext

    def __init__(self, max_workers: int = 2, max_threads: int = 10):
        self._workers = []
        self.max_workers = max_workers
        self.max_threads = max_threads

        self._ctx = mp.get_context("spawn")
        self._dispatch_queue = self._ctx.Queue()
        self._finished_queue = self._ctx.Queue()
        self._log_queue = self._ctx.Queue()
        self._stop_event = self._ctx.Event()

        self._log_thread = threading.Thread(target=logger_thread, args=(self._log_queue,))

    @abstractmethod
    def _prepare_items(self) -> Iterable[_TD]:
        pass

    def __do_run(self) -> list[_TF]:
        for item in self._prepare_items():
            self._dispatch_queue.put(item)

        # Make sure workers shutdown
        for _ in self._workers:
            self._dispatch_queue.put(None)

        result = []
        running = len(self._workers)
        while running != 0:
            finished_item = self._finished_queue.get()
            if finished_item is None:
                running -= 1
            else:
                result.append(finished_item)
        return result

    @abstractmethod
    def _get_worker_args(self, i: int) -> Iterable[Any]:
        pass

    @classmethod
    @abstractmethod
    def _worker(cls, *args: Any, **kwargs: Unpack[WorkerParams[_TD, _TF]]) -> BaseWorker[_TD, _TF]:
        pass

    @classmethod
    @final
    def _init_worker(cls, *args: Any, **kwargs: Unpack[WorkerParams[_TD, _TF]]) -> None:
        # Set MainThread to worker name
        threading.current_thread().name = mp.current_process().name

        logger: MultiProcessingLogger = kwargs["logger"]
        finished_queue: mp.queues.Queue[_TF | None] = kwargs["finished_queue"]

        logger.start()
        try:
            worker = cls._worker(*args, **kwargs)
        except Exception as exc:
            finished_queue.put(None)
            logger.critical("Error creating worker: %s", exc)
            logger.debug("Traceback:", exc_info=exc)
            exit(1)

        try:
            worker.run()
        except KeyboardInterrupt:
            worker.shutdown()

    def _create_workers(self) -> None:
        logger = MultiProcessingLogger(__name__, log.getEffectiveLevel(), self._log_queue)

        for i in range(self.max_workers):
            log.debug("Creating worker: %d", i)
            p = self._ctx.Process(
                target=self._init_worker,
                name=f"worker-{i}",
                args=self._get_worker_args(i),
                kwargs={
                    "logger": logger,
                    "threads": self.max_threads,
                    "stop_event": self._stop_event,
                    "dispatch_queue": self._dispatch_queue,
                    "finished_queue": self._finished_queue,
                },
            )
            self._workers.append(p)
            p.start()

    @final
    def run(self) -> list[_TF]:
        try:
            self._log_thread.start()
            self._create_workers()
            result = self.__do_run()
            self.shutdown()
            return result
        except KeyboardInterrupt as exc:
            log.debug("Cancellation requested, stopping futures")
            self.shutdown()
            raise exc
        except Exception as exc:
            log.debug("Exception occurred, shutting down. Traceback:", exc_info=exc)
            self.shutdown()
            raise exc

    def shutdown(self) -> None:
        self._stop_event.set()

        # Stop workers from waiting, needed if an exception is raised
        for _ in self._workers:
            self._dispatch_queue.put(None)

        log.debug("Waiting for workers to shutdown")
        for p in self._workers:
            p.join()
            log.debug(f"{p.name} exited with code: {p.exitcode}")
            if p.exitcode != 0:
                log.error(f"Exception occurred in {p.name}")
            p.close()

        # shutdown logger
        log.debug("Shutting down logger")

        self._log_queue.put(None)
        self._log_thread.join()

        log.debug("Closing queues")
        self._dispatch_queue.close()
        self._finished_queue.close()
        self._finished_queue.cancel_join_thread()
        self._dispatch_queue.cancel_join_thread()

        self._log_queue.close()
        self._log_queue.join_thread()

        log.debug("Shutdown completed")
