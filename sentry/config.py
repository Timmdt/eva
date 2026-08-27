from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class SentryConfig:
    enabled: bool = False
    rtsp_url: str = ""
    server_mac: str = ""
    server_ip: str = ""
    wol_broadcast: str = "255.255.255.255"
    presence_timeout: float = 900.0
    mode: str = "presence_only"
    face_recognition_enabled: bool = False
    detection_fps: float = 2.0
    frame_scale: float = 0.5
    camera_timeout: float = 10.0
    reconnect_delay: float = 2.0
    wol_cooldown: float = 120.0
    health_url: str = ""
    health_timeout: float = 2.0
    allow_shutdown: bool = False
    boot_grace: float = 600.0
    keep_awake_file: Path = Path("/tmp/eva_keep_awake")
    inhibit_file: Path = Path("/tmp/eva_shutdown_inhibit")

    @classmethod
    def from_env(cls) -> "SentryConfig":
        mode = os.getenv("EVA_SENTRY_MODE", "presence_only").strip().lower()
        if mode not in {"presence_only", "recognized_user"}:
            raise ValueError("EVA_SENTRY_MODE muss presence_only oder recognized_user sein.")
        return cls(
            enabled=env_bool("EVA_SENTRY_ENABLED"),
            rtsp_url=os.getenv("EVA_TAPO_RTSP_URL", ""),
            server_mac=os.getenv("EVA_SERVER_MAC", ""),
            server_ip=os.getenv("EVA_SERVER_IP", ""),
            wol_broadcast=os.getenv("EVA_WOL_BROADCAST", "255.255.255.255"),
            presence_timeout=env_float("EVA_PRESENCE_TIMEOUT", 900.0),
            mode=mode,
            face_recognition_enabled=env_bool("EVA_FACE_RECOGNITION_ENABLED"),
            detection_fps=max(0.1, min(5.0, env_float("EVA_SENTRY_DETECTION_FPS", 2.0))),
            frame_scale=max(0.1, min(1.0, env_float("EVA_SENTRY_FRAME_SCALE", 0.5))),
            camera_timeout=env_float("EVA_SENTRY_CAMERA_TIMEOUT", 10.0),
            reconnect_delay=env_float("EVA_SENTRY_RECONNECT_DELAY", 2.0),
            wol_cooldown=env_float("EVA_WOL_COOLDOWN", 120.0),
            health_url=os.getenv("EVA_HEALTH_URL", ""),
            health_timeout=env_float("EVA_HEALTH_TIMEOUT", 2.0),
            allow_shutdown=env_bool("EVA_SENTRY_ALLOW_SHUTDOWN"),
            boot_grace=env_float("EVA_SENTRY_BOOT_GRACE", 600.0),
            keep_awake_file=Path(os.getenv("EVA_KEEP_AWAKE_FILE", "/tmp/eva_keep_awake")),
            inhibit_file=Path(os.getenv("EVA_SHUTDOWN_INHIBIT_FILE", "/tmp/eva_shutdown_inhibit")),
        )
