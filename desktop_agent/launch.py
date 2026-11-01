"""Absolute Windows-autostart entry point; independent of the login working directory."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from desktop_agent.app.controller import main

if __name__ == "__main__":
    main()
