"""Small thread-safe TTL cache for analysis results and derived API data."""

from __future__ import annotations

import time
from collections import OrderedDict
from threading import RLock
from typing import Any

from .config import settings


class TTLCache:
    """Thread-safe in-memory TTL cache with simple LRU eviction."""

    def __init__(self, maxsize: int = 128, ttl_seconds: int = 900) -> None:
        self.maxsize = max(1, int(maxsize))
        self.ttl_seconds = max(1, int(ttl_seconds))
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = RLock()
        self.hits = 0
        self.misses = 0

    def _expired(self, created_at: float) -> bool:
        return time.time() - created_at > self.ttl_seconds

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                self.misses += 1
                return default

            created_at, value = item
            if self._expired(created_at):
                self._items.pop(key, None)
                self.misses += 1
                return default

            self._items.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._items[key] = (time.time(), value)
            self._items.move_to_end(key)
            while len(self._items) > self.maxsize:
                self._items.popitem(last=False)

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._items.pop(key, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self.hits = 0
            self.misses = 0

    def prune(self) -> int:
        with self._lock:
            expired = [key for key, (created_at, _) in self._items.items() if self._expired(created_at)]
            for key in expired:
                self._items.pop(key, None)
            return len(expired)

    def stats(self) -> dict[str, int | float]:
        with self._lock:
            self.prune()
            return {
                "items": len(self._items),
                "maxsize": self.maxsize,
                "ttl_seconds": self.ttl_seconds,
                "hits": self.hits,
                "misses": self.misses,
            }


analysis_cache = TTLCache(maxsize=256, ttl_seconds=settings.CACHE_TTL)
