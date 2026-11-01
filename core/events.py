from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class EventType(str, Enum):
    PRESENCE_DETECTED = "PRESENCE_DETECTED"
    IDENTITY_CHANGED = "IDENTITY_CHANGED"
    SERVER_WAKE_REQUESTED = "SERVER_WAKE_REQUESTED"
    SERVER_READY = "SERVER_READY"
    PRESENCE_LOST = "PRESENCE_LOST"
    SERVER_SLEEP_REQUESTED = "SERVER_SLEEP_REQUESTED"


@dataclass(frozen=True)
class Event:
    type: EventType
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class EventBus:
    """Small in-process queue with optional synchronous subscribers."""

    def __init__(self) -> None:
        self.queue: queue.Queue[Event] = queue.Queue()
        self._subscribers: dict[EventType, list[Callable[[Event], None]]] = {}
        self._lock = threading.RLock()

    def subscribe(self, event_type: EventType, callback: Callable[[Event], None]) -> None:
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(callback)

    def publish(self, event_type: EventType, **payload: Any) -> Event:
        event = Event(event_type, payload)
        self.queue.put(event)
        with self._lock:
            callbacks = list(self._subscribers.get(event_type, []))
        for callback in callbacks:
            callback(event)
        return event


event_bus = EventBus()
