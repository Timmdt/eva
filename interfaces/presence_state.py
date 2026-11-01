from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class FusedPresence:
    room_presence: bool = False
    desk_presence: bool = False
    identity: str | None = None
    confidence: float = 0.0
    desk_identity_confirmed: bool = False
    updated_at: str = ""

    @property
    def personal_context_allowed(self) -> bool:
        return bool(self.desk_presence and self.identity and self.desk_identity_confirmed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "room_presence": self.room_presence,
            "desk_presence": self.desk_presence,
            "identity": self.identity,
            "confidence": self.confidence,
            "personal_context_allowed": self.personal_context_allowed,
            "updated_at": self.updated_at,
        }


class PresenceFusion:
    def __init__(self, ttl_seconds: float | None = None, clock: Any = time.monotonic) -> None:
        self._reports: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self.ttl_seconds = float(
            os.getenv("EVA_PRESENCE_REPORT_TTL", "30") if ttl_seconds is None else ttl_seconds
        )
        self.clock = clock

    def update(self, report: dict[str, Any]) -> FusedPresence:
        sensor = str(report.get("sensor", "")).strip().lower()
        if sensor not in {"room", "desk"}:
            raise ValueError("sensor muss room oder desk sein.")
        clean = {
            "presence": bool(report.get("presence")),
            "identity": str(report.get("identity") or "").strip() or None,
            "confidence": max(0.0, min(1.0, float(report.get("confidence", 0.0)))),
            "received_at": self.clock(),
            "received_iso": datetime.now(UTC).isoformat(),
        }
        with self._lock:
            self._reports[sensor] = clean
            return self.current()

    def current(self) -> FusedPresence:
        with self._lock:
            room = self._reports.get("room", {})
            desk = self._reports.get("desk", {})
            now = self.clock()
            if room and now - float(room.get("received_at", 0.0)) > self.ttl_seconds:
                room = {}
            if desk and now - float(desk.get("received_at", 0.0)) > self.ttl_seconds:
                desk = {}
            desk_identity = desk.get("identity") if desk.get("presence") else None
            room_identity = room.get("identity") if room.get("presence") else None
            identity = desk_identity or room_identity
            confidence = float(
                desk.get("confidence", 0.0) if desk_identity else room.get("confidence", 0.0)
            )
            return FusedPresence(
                room_presence=bool(room.get("presence")),
                desk_presence=bool(desk.get("presence")),
                identity=identity,
                confidence=confidence,
                desk_identity_confirmed=bool(desk_identity),
                updated_at=str(desk.get("received_iso") or room.get("received_iso") or ""),
            )


presence_fusion = PresenceFusion()
