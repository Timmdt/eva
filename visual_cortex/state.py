from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class PresenceState(str, Enum):
    ABSENT = "ABSENT"
    PRESENT_UNKNOWN = "PRESENT_UNKNOWN"
    PRESENT_USER = "PRESENT_USER"


@dataclass(frozen=True)
class VisualState:
    state: PresenceState = PresenceState.ABSENT
    presence: bool = False
    identity: str | None = None
    confidence: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {"state": self.state.value, "presence": self.presence,
                "identity": self.identity, "confidence": self.confidence}


@dataclass(frozen=True)
class VisualConfig:
    enabled: bool = False
    camera_device: int = 0
    save_frames: bool = False
    recognition_threshold: float = 0.82

    @classmethod
    def from_env(cls) -> "VisualConfig":
        truthy = {"1", "true", "yes", "on"}
        return cls(
            enabled=os.getenv("EVA_VISUAL_CORTEX_ENABLED", "false").lower() in truthy,
            camera_device=int(os.getenv("EVA_VISUAL_CAMERA", "0")),
            save_frames=os.getenv("EVA_VISUAL_SAVE_FRAMES", "false").lower() in truthy,
            recognition_threshold=float(os.getenv("EVA_FACE_THRESHOLD", "0.82")),
        )
