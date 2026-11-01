from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from .camera import DesktopCamera
from .eva_client import EVAClient
from .identity import DesktopIdentity
from .presence import DeskPresenceDetector


def _enabled(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.lower() in {"1", "true", "yes", "on"}


def main() -> None:
    logging.basicConfig(
        level=getattr(logging, os.getenv("EVA_LOG_LEVEL", "INFO").upper(), logging.INFO)
    )
    if not _enabled("EVA_DESKTOP_AGENT_ENABLED"):
        print("Desktop Agent ist deaktiviert (EVA_DESKTOP_AGENT_ENABLED=false).")
        return
    fps = max(0.1, min(5.0, float(os.getenv("EVA_DESKTOP_FPS", "2"))))
    store = Path(os.getenv("EVA_DESKTOP_FACE_STORE", "data/faces.json"))
    detector = DeskPresenceDetector()
    identity = DesktopIdentity(store, threshold=float(os.getenv("EVA_FACE_THRESHOLD", "0.82")))
    client = EVAClient(os.getenv("EVA_DESKTOP_EVA_URL", ""), os.getenv("EVA_PRESENCE_TOKEN", ""))
    last_payload: dict[str, object] | None = None
    last_sent = 0.0
    with DesktopCamera(int(os.getenv("EVA_DESKTOP_CAMERA", "0"))) as camera:
        while True:
            started = time.monotonic()
            frame = camera.read()
            detected = detector.detect(frame)
            result = identity.recognize(frame) if detected else {}
            payload: dict[str, object] = {
                "presence": detected,
                "identity": result.get("identity"),
                "confidence": float(result.get("confidence", 0.0)),
            }
            now = time.monotonic()
            if payload != last_payload or now - last_sent >= 15.0:
                client.report_desk_presence(**payload)
                print(json.dumps(payload, ensure_ascii=False), flush=True)
                last_payload, last_sent = payload, now
            time.sleep(max(0.0, 1.0 / fps - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
