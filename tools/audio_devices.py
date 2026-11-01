from __future__ import annotations

import shutil
import subprocess


def main() -> int:
    aplay = shutil.which("aplay")
    if aplay is None:
        print(
            "aplay wurde nicht gefunden. Installiere unter Debian/Ubuntu: sudo apt install alsa-utils"
        )
        return 1
    result = subprocess.run([aplay, "-L"], check=False, text=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
