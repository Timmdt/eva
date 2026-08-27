from __future__ import annotations

from typing import Any, Callable

from core.events import EventBus, EventType, event_bus
from .state import PresenceState, VisualState


class FacePresenceDetector:
    """Face detection is deliberately separate from identity recognition."""

    def __init__(self, detector: Callable[[Any], bool] | None = None) -> None:
        self.detector = detector
        self._cascade = None

    def detect(self, frame: Any) -> bool:
        if self.detector:
            return bool(self.detector(frame))
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("Face Detection benötigt OpenCV.") from exc
        if self._cascade is None:
            self._cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return len(self._cascade.detectMultiScale(gray, 1.1, 5)) > 0


class VisualCortex:
    def __init__(self, detector: FacePresenceDetector, identity_store: Any | None = None,
                 bus: EventBus = event_bus) -> None:
        self.detector, self.identity_store, self.bus = detector, identity_store, bus
        self.state = VisualState()

    def process(self, frame: Any) -> VisualState:
        old = self.state
        if not self.detector.detect(frame):
            new = VisualState()
        elif self.identity_store is None:
            new = VisualState(PresenceState.PRESENT_UNKNOWN, True)
        else:
            result = self.identity_store.recognize(frame)
            identity = result.get("identity")
            new = VisualState(
                PresenceState.PRESENT_USER if identity else PresenceState.PRESENT_UNKNOWN,
                True, identity, float(result.get("confidence", 0.0)))
        self.state = new
        if old.presence != new.presence:
            self.bus.publish(EventType.PRESENCE_DETECTED if new.presence
                             else EventType.PRESENCE_LOST, **new.to_dict())
        if old.identity != new.identity:
            self.bus.publish(EventType.IDENTITY_CHANGED, **new.to_dict())
        return new
