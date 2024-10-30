import logging
import logging.handlers
import multiprocessing.queues
import sys
from typing import Any, Protocol

import colorlog


def get_logger(level: int, debug_file: str | None = None) -> logging.Logger:
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    sys_handler = logging.StreamHandler(stream=sys.stderr)
    sys_handler.setLevel(level)
    sys_handler.setFormatter(
        colorlog.ColoredFormatter(
            "%(asctime)-24.24s | %(threadName)-12s | %(name)-24.24s | %(log_color)s%(levelname)-8.8s%(reset)s | %(message)s"
        )
    )

    sys_handler.addFilter(lambda record: record.name == "root" or record.name.startswith("saadt"))

    if debug_file:
        file_formatter = logging.Formatter(
            "%(asctime)-24.24s | %(threadName)-12s | %(name)-40s | %(levelname)-8.8s |  %(message)s"
        )
        file_handler = logging.FileHandler(debug_file)
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)

    logger.addHandler(sys_handler)

    return logger


class LoggerInterface(Protocol):
    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None: ...

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None: ...

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None: ...

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None: ...

    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None: ...


class MultiProcessingLogger(LoggerInterface):
    logger: logging.Logger | None = None

    def __init__(self, name: str, level: int, log_queue: multiprocessing.queues.Queue[logging.LogRecord | None]):
        self._name = name
        self._level = level
        self._log_queue = log_queue

    def start(self) -> None:
        if self.logger is not None:
            return

        self._prepare_root_logger()

        logger = logging.getLogger(self._name)
        logger.setLevel(self._level)

        self.logger = logger

    def _prepare_root_logger(self) -> None:
        # Don't touch the root logger if this is the main process
        if multiprocessing.parent_process() is None:
            return

        root = logging.getLogger()
        # Clear handlers for forked processes
        root.handlers = []
        # Level is handled by main process
        root.setLevel(logging.NOTSET)

        # Add handler to forward to main process
        qh = logging.handlers.QueueHandler(self._log_queue)
        root.addHandler(qh)

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        if self.logger is None:
            raise Exception("Logger not started")

        self.logger.debug(msg, *args, **kwargs)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        if self.logger is None:
            raise Exception("Logger not started")

        self.logger.info(msg, *args, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        if self.logger is None:
            raise Exception("Logger not started")

        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        if self.logger is None:
            raise Exception("Logger not started")

        self.logger.error(msg, *args, **kwargs)

    def critical(self, msg: str, *args: Any, **kwargs: Any) -> None:
        if self.logger is None:
            raise Exception("Logger not started")

        self.logger.critical(msg, *args, **kwargs)
