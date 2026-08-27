from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from typing import Any, Callable

logger = logging.getLogger(__name__)


class RTSPCamera:
    """Low-FPS RTSP reader with reconnect and downscaling."""

    def __init__(self, url: str, *, detection_fps: float = 2.0, scale: float = 0.5,
                 timeout: float = 10.0, reconnect_delay: float = 2.0,
                 capture_factory: Callable[[str], Any] | None = None) -> None:
        self.url = url
        self.detection_fps = max(0.1, min(5.0, detection_fps))
        self.scale = max(0.1, min(1.0, scale))
        self.timeout = timeout
        self.reconnect_delay = reconnect_delay
        self._capture_factory = capture_factory
        self._stopped = False

    def _open(self) -> Any:
        if self._capture_factory:
            return self._capture_factory(self.url)
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("RTSP-Kamera benötigt optional opencv-python-headless.") from exc
        capture = cv2.VideoCapture(self.url)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        capture.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(self.timeout * 1000))
        capture.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(self.timeout * 1000))
        return capture

    def frames(self) -> Iterator[Any]:
        interval = 1.0 / self.detection_fps
        while not self._stopped:
            capture = self._open()
            try:
                while not self._stopped and capture.isOpened():
                    started = time.monotonic()
                    ok, frame = capture.read()
                    if not ok:
                        break
                    if self.scale < 1.0:
                        import cv2
                        frame = cv2.resize(frame, None, fx=self.scale, fy=self.scale)
                    yield frame
                    time.sleep(max(0.0, interval - (time.monotonic() - started)))
            finally:
                capture.release()
            if not self._stopped:
                logger.warning("RTSP-Stream unterbrochen; verbinde neu.")
                time.sleep(self.reconnect_delay)

    def stop(self) -> None:
        self._stopped = True
