import dataclasses
import logging
from enum import Enum
from typing import Any

from .events import BaseEvent
from .listeners import EventListener

log = logging.getLogger(__name__)


@dataclasses.dataclass
class EventDispatcher:
    _listeners: dict[str, dict[int, list[EventListener[Any]]]] = dataclasses.field(default_factory=dict)
    _sorted: dict[str, list[EventListener[Any]]] = dataclasses.field(default_factory=dict)

    def dispatch(self, name: Enum, event: BaseEvent) -> None:
        log.debug("Dispatching event: %s", name)
        listeners = self.get_listeners(str(name))

        for listener in listeners:
            log.debug("Calling listener: %s", str(listener))
            if event.is_propagation_stopped():
                log.debug('Stopped event propagation: event="%s"', name)
                break
            listener.on_event(event)

    def register(self, name: Enum, listener: EventListener[Any], priority: int = 0) -> None:
        named_listeners = self._listeners.setdefault(str(name), {})
        named_listeners.setdefault(priority, []).append(listener)

        self._sorted.pop(str(name), None)

    def get_listeners(self, name: str) -> list[EventListener[Any]]:
        if name not in self._listeners:
            return []

        if name not in self._sorted:
            self._sort_listeners(name)

        return self._sorted[name]

    def _sort_listeners(self, name: str) -> None:
        d = sorted(self._listeners[name].items(), reverse=True)

        self._sorted[name] = [x for t in d for x in t[1]]
