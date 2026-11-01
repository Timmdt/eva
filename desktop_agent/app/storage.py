from __future__ import annotations

import json
import math
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

DEFAULTS = {
    "monitor": "",
    "position": 0.84,
    "size": 220,
    "opacity": 1.0,
    "always_on_top": True,
    "animations": True,
    "animation_speed": 1.0,
    "auto_tired": True,
    "tired_after": 600,
    "sleep_after": 1200,
    "pose": "idle",
    "outfit": "",
    "autostart": False,
    "language": "de",
    "backend": "none",
    "url": "http://192.168.2.15:8766",
    "model": "qwen3-vl:4b-instruct",
    "remember_token": False,
    "observe_interval": 60,
    "include_eva_in_screenshots": True,
    "taskbar_offset": 0,
}


def data_directory() -> Path:
    explicit = os.getenv("EVA_DESKTOP_DATA_DIR")
    if explicit:
        return Path(explicit)
    root = Path(os.getenv("APPDATA", str(Path.home() / ".local/share")))
    return root / "EVA Desktop Agent"


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


class Preferences:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or data_directory()
        self.path = self.directory / "settings.json"
        loaded = read_json(self.path, {})
        self.values = dict(DEFAULTS)
        if isinstance(loaded, dict):
            self.values.update({key: value for key, value in loaded.items() if key in DEFAULTS})
        for key in (
            "size",
            "opacity",
            "position",
            "animation_speed",
            "tired_after",
            "sleep_after",
            "observe_interval",
            "taskbar_offset",
        ):
            try:
                number = float(self.values[key])
                if not math.isfinite(number):
                    raise ValueError()
                self.values[key] = number
            except (ValueError, TypeError):
                self.values[key] = DEFAULTS[key]
        self.values["size"] = max(100, min(480, int(self.values["size"])))
        self.values["opacity"] = max(0.3, min(1.0, self.values["opacity"]))
        self.values["position"] = max(0.05, min(0.95, self.values["position"]))
        self.values["animation_speed"] = max(0.25, min(2.0, self.values["animation_speed"]))
        self.values["taskbar_offset"] = max(-24, min(24, int(self.values["taskbar_offset"])))
        for key in (
            "always_on_top",
            "animations",
            "auto_tired",
            "autostart",
            "remember_token",
            "include_eva_in_screenshots",
        ):
            if not isinstance(self.values[key], bool):
                self.values[key] = DEFAULTS[key]
        for key in ("monitor", "outfit", "pose", "language", "backend", "url", "model"):
            if not isinstance(self.values[key], str):
                self.values[key] = DEFAULTS[key]
        if self.values["backend"] not in {"none", "ollama", "bridge"}:
            self.values["backend"] = "none"

    def get(self, key):
        return self.values[key]

    def update(self, values):
        self.values.update({key: value for key, value in values.items() if key in DEFAULTS})
        write_json(self.path, self.values)


class Conversations:
    def __init__(self, directory: Path):
        self.path = directory / "conversations.json"
        loaded = read_json(self.path, {})
        self.items = []
        if isinstance(loaded, dict) and isinstance(loaded.get("items"), list):
            for item in loaded["items"][-30:]:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                    continue
                raw = item.get("messages", [])
                if not isinstance(raw, list):
                    raw = []
                messages = [
                    {"role": row["role"], "content": row["content"][:12000]}
                    for row in raw[-200:]
                    if isinstance(row, dict)
                    and row.get("role") in ("user", "assistant")
                    and isinstance(row.get("content"), str)
                ]
                self.items.append(
                    {
                        "id": item["id"],
                        "title": str(item.get("title", "Unterhaltung"))[:80],
                        "messages": messages,
                    }
                )
        selected = loaded.get("current") if isinstance(loaded, dict) else None
        self.current = selected if any(row["id"] == selected for row in self.items) else None
        if not self.items:
            self.new()
        elif self.current is None:
            self.current = self.items[-1]["id"]

    @property
    def active(self):
        return next(item for item in self.items if item["id"] == self.current)

    def new(self):
        self.current = uuid.uuid4().hex
        self.items.append(
            {
                "id": self.current,
                "title": datetime.now().strftime("Gespräch %d.%m. %H:%M"),
                "messages": [],
            }
        )
        self.items = self.items[-30:]
        self.save()

    def append(self, role, content):
        item = self.active
        if role == "user" and not item["messages"]:
            item["title"] = content[:55]
        item["messages"].append({"role": role, "content": content[:12000]})
        item["messages"] = item["messages"][-200:]
        self.save()

    def save(self):
        write_json(self.path, {"current": self.current, "items": self.items})


def credential_token(url: str, value: str | None = None, *, delete=False) -> str:
    if sys.platform != "win32":
        return ""
    from keyring.backends.Windows import WinVaultKeyring

    vault = WinVaultKeyring()
    service = "EVA.DesktopAgent"
    if delete:
        if vault.get_password(service, url):
            vault.delete_password(service, url)
        return ""
    if value is not None:
        vault.set_password(service, url, value)
        return value
    return vault.get_password(service, url) or ""
