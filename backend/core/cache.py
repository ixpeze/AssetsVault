"""
backend.core.cache — generic TTL key/value cache.

Usage:
    from backend.core.cache import response_cache
    response_cache.set("items:page1", data, ttl=30)
    result = response_cache.get("items:page1")  # None if expired
    response_cache.invalidate("items:page1")
    response_cache.invalidate_prefix("items:")
"""
import threading
import time
import logging

log = logging.getLogger(__name__)


class TTLCache:
    def __init__(self) -> None:
        self._values: dict[str, object] = {}
        self._expiry: dict[str, float] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> object | None:
        with self._lock:
            if key not in self._values:
                return None
            if time.monotonic() > self._expiry[key]:
                del self._values[key]
                del self._expiry[key]
                return None
            return self._values[key]

    def set(self, key: str, value: object, ttl: int = 60) -> None:
        with self._lock:
            self._values[key] = value
            self._expiry[key] = time.monotonic() + ttl

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._values.pop(key, None)
            self._expiry.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> int:
        """Remove all keys that start with *prefix*. Returns number removed."""
        with self._lock:
            to_remove = [k for k in self._values if k.startswith(prefix)]
            for k in to_remove:
                del self._values[k]
                del self._expiry[k]
        if to_remove:
            log.debug("[TTLCache] Invalidated %d key(s) with prefix '%s'", len(to_remove), prefix)
        return len(to_remove)

    def size(self) -> int:
        with self._lock:
            return len(self._values)


# Module-level singleton
response_cache = TTLCache()
