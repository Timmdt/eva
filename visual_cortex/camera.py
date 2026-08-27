from __future__ import annotations

from typing import Any, Callable


class DesktopCamera:
    def __init__(self, device: int = 0, *, capture_factory: Callable[[int], Any] | None = None) -> None:
        if capture_factory:
            self.capture = capture_factory(device)
        else:
            try:
                import cv2
            except ImportError as exc:
                raise RuntimeError("Desktop-Kamera benötigt optional OpenCV.") from exc
            self.capture = cv2.VideoCapture(device)
        if not self.capture.isOpened():
            raise RuntimeError(f"Kamera {device} konnte nicht geöffnet werden.")

    def read(self) -> Any:
        ok, frame = self.capture.read()
        if not ok:
            raise RuntimeError("Kameraframe konnte nicht gelesen werden.")
        return frame

    def close(self) -> None:
        self.capture.release()

    def __enter__(self) -> "DesktopCamera":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()
