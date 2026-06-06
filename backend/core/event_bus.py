"""
backend.core.event_bus — synchronous in-process pub/sub bus.

Usage:
    from backend.core.event_bus import bus
    bus.subscribe("pipeline_completed", my_handler)
    bus.emit("pipeline_completed", task_id="x")
    bus.unsubscribe("pipeline_completed", my_handler)
"""
import threading
import logging

log = logging.getLogger(__name__)


class EventBus:
    def __init__(self) -> None:
        self._listeners: dict[str, list] = {}
        self._lock = threading.Lock()

    def subscribe(self, event: str, fn) -> None:
        with self._lock:
            self._listeners.setdefault(event, []).append(fn)
        log.debug("[EventBus] subscribed to '%s' (total=%d)", event, len(self._listeners[event]))

    def unsubscribe(self, event: str, fn) -> None:
        with self._lock:
            listeners = self._listeners.get(event, [])
            try:
                listeners.remove(fn)
            except ValueError:
                pass

    def emit(self, event: str, **payload) -> None:
        with self._lock:
            fns = list(self._listeners.get(event, []))
        log.debug("[EventBus] emit '%s' to %d subscriber(s)", event, len(fns))
        for fn in fns:
            try:
                fn(**payload)
            except Exception:
                log.exception("[EventBus] Subscriber error for event '%s'", event)


# Module-level singleton
bus = EventBus()
