from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .camera import DesktopCamera
from .identity import IdentityStore
from .presence import FacePresenceDetector, VisualCortex
from .state import VisualConfig


def main() -> None:
    config = VisualConfig.from_env()
    if not config.enabled:
        print("Visual Cortex is disabled (EVA_VISUAL_CORTEX_ENABLED=false).")
        return
    store = IdentityStore(
        Path(os.getenv("EVA_FACE_STORE", "data/faces.json")), threshold=config.recognition_threshold
    )
    cortex = VisualCortex(FacePresenceDetector(), store)
    interval = 1.0 / max(0.1, min(5.0, float(os.getenv("EVA_VISUAL_FPS", "2"))))
    with DesktopCamera(config.camera_device) as camera:
        last_state = None
        while True:
            started = time.monotonic()
            state = cortex.process(camera.read())
            if state != last_state:
                print(json.dumps(state.to_dict(), ensure_ascii=False), flush=True)
                last_state = state
            time.sleep(max(0.0, interval - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
