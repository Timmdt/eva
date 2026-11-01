from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any


def _normalize(values: list[float]) -> list[float]:
    length = math.sqrt(sum(value * value for value in values))
    if not values or length == 0:
        raise ValueError("Gesichtsmerkmal ist leer.")
    return [value / length for value in values]


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return -1.0
    return sum(a * b for a, b in zip(left, right, strict=True))


def local_face_embedding(frame: Any) -> list[float]:
    """Lightweight local descriptor. It stores descriptors, never source frames."""
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError("Lokale Gesichtserkennung benötigt OpenCV.") from exc
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
    if len(faces) == 0:
        raise ValueError("Kein Gesicht erkannt.")
    x, y, width, height = max(faces, key=lambda item: item[2] * item[3])
    face = cv2.resize(gray[y : y + height, x : x + width], (32, 32))
    equalized = cv2.equalizeHist(face)
    return _normalize([float(value) / 255.0 for row in equalized.tolist() for value in row])


class IdentityStore:
    def __init__(
        self,
        path: Path = Path("data/faces.json"),
        *,
        threshold: float = 0.82,
        extractor: Callable[[Any], list[float]] = local_face_embedding,
    ) -> None:
        self.path, self.threshold, self.extractor = path, threshold, extractor
        self.identities: dict[str, list[list[float]]] = {}
        self.load()

    def load(self) -> None:
        if not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            self.identities = {
                str(name): [[float(v) for v in vector] for vector in vectors]
                for name, vectors in data.items()
                if isinstance(vectors, list)
            }

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.identities, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)

    def enroll(self, name: str, frame: Any) -> None:
        name = name.strip()
        if not re.fullmatch(r"[\w .-]{1,80}", name, re.UNICODE):
            raise ValueError("Ungültiger Benutzername.")
        self.identities.setdefault(name, []).append(_normalize(self.extractor(frame)))
        self.save()

    def recognize(self, frame: Any) -> dict[str, Any]:
        candidate = _normalize(self.extractor(frame))
        best_name: str | None = None
        best_score = -1.0
        for name, vectors in self.identities.items():
            for vector in vectors:
                score = _cosine(candidate, vector)
                if score > best_score:
                    best_name, best_score = name, score
        if best_name is None or best_score < self.threshold:
            return {"identity": None, "confidence": max(0.0, best_score), "registered": False}
        return {"identity": best_name, "confidence": min(1.0, best_score), "registered": True}
