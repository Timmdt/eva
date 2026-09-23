from __future__ import annotations

import os
import re
from pathlib import Path


ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_env_file(path: str | Path, *, override: bool = False) -> set[str]:
    """Load plain KEY=value entries without executing the file as shell code.

    Existing process variables win unless ``override`` is explicitly enabled.
    Values stay literal: no command, variable or tilde expansion is performed.
    """
    env_path = Path(path)
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return set()

    loaded: set[str] = set()
    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ValueError(
                f"Ungültige .env-Zeile {line_number}: KEY=value erwartet."
            )

        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not ENV_NAME_RE.fullmatch(name):
            raise ValueError(
                f"Ungültiger Variablenname in .env-Zeile {line_number}."
            )
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if override or name not in os.environ:
            os.environ[name] = value
            loaded.add(name)

    return loaded
