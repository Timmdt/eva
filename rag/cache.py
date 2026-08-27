from __future__ import annotations

import copy
import threading
import time
from collections import OrderedDict
from typing import Any


class TTLCache:
    """Small thread-safe TTL/LRU cache used for retrieval results."""

    def __init__(self, max_size: int = 256, ttl_seconds: float = 60.0) -> None:
        self.max_size = max(1, int(max_size))
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self._items: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: str) -> Any | None:
        now = time.monotonic()
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at <= now:
                self._items.pop(key, None)
                return None
            self._items.move_to_end(key)
            return copy.deepcopy(value)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._items[key] = (time.monotonic() + self.ttl_seconds, copy.deepcopy(value))
            self._items.move_to_end(key)
            while len(self._items) > self.max_size:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
