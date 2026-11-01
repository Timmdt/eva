from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPixmap

ROOT = Path(__file__).resolve().parents[2] / "assets"
DEFAULT_OUTFIT = ROOT / "character/outfits/gothic.json"
STATE_LABELS = {
    "idle": "Sitzen · Idle",
    "listening": "Zuhören",
    "thinking": "Nachdenken",
    "talking": "Antworten",
    "happy": "Freuen",
    "annoyed": "Genervt",
    "tired": "Müde",
    "sleeping": "Schlafen",
    "standing": "Stehen",
    "waving": "Winken",
    "typing": "Tippen / Arbeiten",
    "reading": "Lesen",
    "falling_asleep": "Einschlafen",
    "rising": "Aufstehen",
    "stretching": "Strecken",
    "sitting_down": "Hinsetzen",
    "alert": "Aufmerksam",
}


@dataclass
class Pose:
    name: str
    label: str
    frames: list[Path]
    scale: float
    anchor: tuple[float, float]
    duration_ms: int
    note: str


class Outfit:
    def __init__(self, manifest: Path = DEFAULT_OUTFIT):
        self.manifest = manifest.resolve()
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        if data.get("version") != 1 or not isinstance(data.get("poses"), dict):
            raise ValueError("Outfit benötigt version=1 und poses.")
        self.name = str(data.get("name", "Gothic"))
        self.description = str(data.get("description", ""))
        self.poses = {}
        self.pixmaps = {}
        root = self.manifest.parent.parent.resolve()

        def asset(relative):
            path = (self.manifest.parent / relative).resolve()
            if not path.is_relative_to(root) or path.suffix.lower() != ".png" or not path.is_file():
                raise ValueError(f"Ungültiger PNG-Assetpfad: {relative}")
            return path

        for name, row in data["poses"].items():
            if name not in STATE_LABELS or not isinstance(row, dict):
                continue
            frames = [asset(value) for value in row.get("frames", [])]
            if not frames:
                raise ValueError(f"Pose {name}: PNG-Frames fehlen.")
            anchor = row.get("anchor", [0.5, 1.0])
            if len(anchor) != 2 or not all(0 <= float(v) <= 1 for v in anchor):
                raise ValueError("Pose-Anker müssen zwischen 0 und 1 liegen.")
            self.poses[name] = Pose(
                name,
                str(row.get("label", STATE_LABELS[name])),
                frames,
                max(0.25, min(3.0, float(row.get("scale", 1)))),
                tuple(map(float, anchor)),
                max(50, int(row.get("frame_ms", 180))),
                str(row.get("note", "")),
            )
        if "idle" not in self.poses:
            raise ValueError("Das Outfit benötigt die Pose idle.")
        self.expressions = {
            str(key): asset(value) for key, value in data.get("expressions", {}).items()
        }
        self.default_expression = next(iter(self.expressions), None)

    def pose(self, name):
        return self.poses.get(name, self.poses["idle"])

    def pixmap(self, path: Path):
        if path not in self.pixmaps:
            image = QPixmap(str(path))
            if image.isNull() or image.width() > 8192 or image.height() > 8192:
                raise ValueError(f"PNG kann nicht geladen werden: {path.name}")
            self.pixmaps[path] = image
        return self.pixmaps[path]


class CharacterState(QObject):
    changed = Signal(str)

    def __init__(self, initial="idle", clock=time.monotonic):
        super().__init__()
        self.clock = clock
        self.last_activity = clock()
        self.current = initial
        self.manual = initial
        self.busy = False
        self.return_at = None

    def set(self, name, *, manual=False, seconds=None):
        if name not in STATE_LABELS:
            return
        if manual:
            self.manual = name
        self.return_at = self.clock() + seconds if seconds else None
        if self.current != name:
            self.current = name
            self.changed.emit(name)

    def activity(self):
        self.last_activity = self.clock()
        if not self.busy and self.current in {"sleeping", "tired", "falling_asleep"}:
            self.set("listening", seconds=5)

    def tick(self, *, auto_tired, tired_after, sleep_after, chat_visible=False):
        now = self.clock()
        if self.busy:
            return
        if self.return_at is not None:
            if now >= self.return_at:
                self.return_at = None
                self.set(self.manual)
            return
        idle = now - self.last_activity
        if chat_visible:
            return
        if auto_tired and idle >= max(tired_after + 30, sleep_after):
            self.set("sleeping")
        elif auto_tired and idle >= tired_after:
            self.set("tired")
