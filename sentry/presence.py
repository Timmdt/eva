from __future__ import annotations

import time
from typing import Any, Callable


class PresenceDetector:
    """OpenCV HOG person detector; no frames are persisted."""

    def __init__(self, detector: Callable[[Any], bool] | None = None) -> None:
        self._detector = detector
        self._hog = None

    def detect(self, frame: Any) -> bool:
        if self._detector:
            return bool(self._detector(frame))
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("Presence Detection benötigt OpenCV.") from exc
        if self._hog is None:
            self._hog = cv2.HOGDescriptor()
            self._hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        boxes, _weights = self._hog.detectMultiScale(frame, winStride=(8, 8), scale=1.05)
        return len(boxes) > 0


class PresenceTracker:
    def __init__(self, timeout: float = 900.0, clock: Callable[[], float] = time.monotonic) -> None:
        self.timeout = timeout
        self.clock = clock
        self.last_seen: float | None = None

    def update(self, present: bool) -> bool:
        if present:
            self.last_seen = self.clock()
        return self.is_present()

    def is_present(self) -> bool:
        return self.last_seen is not None and self.clock() - self.last_seen < self.timeout

    def timed_out(self) -> bool:
        return self.last_seen is not None and not self.is_present()
