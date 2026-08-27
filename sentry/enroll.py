from __future__ import annotations

import argparse
import os
from pathlib import Path

from visual_cortex.camera import DesktopCamera
from visual_cortex.identity import IdentityStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Register one local EVA user")
    parser.add_argument("name")
    parser.add_argument("--camera", type=int, default=0)
    args = parser.parse_args()
    store = IdentityStore(Path(os.getenv("EVA_FACE_STORE", "data/faces.json")))
    camera = DesktopCamera(args.camera)
    try:
        frame = camera.read()
        store.enroll(args.name, frame)
    finally:
        camera.close()
    print(f"Benutzer '{args.name}' wurde lokal registriert; kein Kameraframe gespeichert.")


if __name__ == "__main__":
    main()
