"""
backend.core.task_runner — lightweight in-process background task queue.

Complements (does not replace) TaskManager's subprocess model.
Use for fast, lightweight in-process tasks: thumbnail generation,
file hashing, metadata extraction. NOT for long-running CLI scripts.

Usage:
    from backend.core.task_runner import task_runner
    task_runner.enqueue("thumbnail", generate_thumbnail, item_id=1, path="/data/img.jpg")
    # On completion, bus.emit("thumbnail_completed", result=...)
"""
import collections
import threading
import logging
from typing import Callable
from .event_bus import bus

log = logging.getLogger(__name__)

_MAX_QUEUE = 500


class TaskRunner:
    def __init__(self) -> None:
        self._queue: collections.deque = collections.deque(maxlen=_MAX_QUEUE)
        self._cond = threading.Condition()
        self._thread: threading.Thread | None = None
        self._running = False

    def enqueue(self, task_type: str, fn: Callable, **kwargs) -> bool:
        """
        Enqueue a task. Returns False if queue is full.
        task_type is used as the event name suffix on completion:
        bus.emit(f"{task_type}_completed", result=...)
        """
        with self._cond:
            if len(self._queue) >= _MAX_QUEUE:
                log.warning("[TaskRunner] Queue full (%d), dropping task '%s'", _MAX_QUEUE, task_type)
                return False
            self._queue.append((task_type, fn, kwargs))
            self._cond.notify()
        return True

    def queue_size(self) -> int:
        return len(self._queue)

    def _worker(self) -> None:
        log.info("[TaskRunner] Worker thread started")
        while self._running:
            with self._cond:
                while not self._queue and self._running:
                    self._cond.wait(timeout=1.0)
                if not self._queue:
                    continue
                task_type, fn, kwargs = self._queue.popleft()
            try:
                result = fn(**kwargs)
                bus.emit(f"{task_type}_completed", result=result)
            except Exception:
                log.exception("[TaskRunner] Task '%s' raised an exception", task_type)
        log.info("[TaskRunner] Worker thread stopped")

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="TaskRunner-worker"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        with self._cond:
            self._cond.notify_all()
        if self._thread:
            self._thread.join(timeout=3.0)


# Module-level singleton — started by the app factory
task_runner = TaskRunner()
