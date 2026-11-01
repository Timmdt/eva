"""Windows desktop entry point; implementation lives in desktop_agent.app."""

from .app.capture import exclude_from_capture, screenshot
from .app.controller import Companion, main

__all__ = ["Companion", "exclude_from_capture", "screenshot", "main"]

if __name__ == "__main__":
    main()
