from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class ActivityRegistry:
    """Process-local activity counters used by safe shutdown checks."""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._lock = threading.RLock()

    @contextmanager
    def track(self, name: str) -> Iterator[None]:
        with self._lock:
            self._counts[name] = self._counts.get(name, 0) + 1
        try:
            yield
        finally:
            with self._lock:
                self._counts[name] = max(0, self._counts.get(name, 1) - 1)

    def active(self, name: str | None = None) -> bool:
        with self._lock:
            if name is not None:
                return self._counts.get(name, 0) > 0
            return any(count > 0 for count in self._counts.values())


activity_registry = ActivityRegistry()
INGESTION_LOCK = Path("/tmp/eva_ingestion.lock")
KEEP_AWAKE_FILE = Path("/tmp/eva_keep_awake")
