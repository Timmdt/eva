#!/usr/bin/env python3

import logging
import os
from pathlib import Path

log_level_name = os.getenv("EVA_LOG_LEVEL", "INFO").strip().upper()
log_level = getattr(logging, log_level_name, logging.INFO)
logging.basicConfig(
    level=log_level,
    format='[%(name)s] %(levelname)s: %(message)s'
)

# Bibliotheks-Transportdetails dürfen nicht zwischen EVAs Stream-Chunks landen.
if os.getenv("EVA_HTTP_DEBUG", "false").lower() not in {"1", "true", "yes", "on"}:
    for noisy_logger in ("httpcore", "httpx", "urllib3"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

ROOT = Path(__file__).resolve().parent

from core.eva import EVA


def main() -> None:
    eva = EVA()

    if os.getenv("EVA_HEALTH_ENABLED", "false").lower() in {"1", "true", "yes", "on"}:
        from interfaces.health_server import start_in_thread
        start_in_thread(
            eva,
            os.getenv("EVA_HEALTH_HOST", "127.0.0.1"),
            int(os.getenv("EVA_HEALTH_PORT", "8765")),
        )

    print(
        f"--- {eva.name} initialisiert ---"
    )

    startup_text = eva.startup()

    if startup_text:
        eva.speak(
            startup_text
        )

    try:
        while True:

            user_input = input(
                "Du: "
            ).strip()

            if user_input.lower() in {
                "exit",
                "shutdown",
                "bye",
            }:
                print(
                    "Auf Wiedersehen!"
                )
                eva.shutdown()
                break

            if not user_input:
                continue

            print(f"{eva.name}: ", end="", flush=True)
            wrote = False
            for chunk in eva.receive_stream(user_input):
                print(chunk, end="", flush=True)
                wrote = True
            if wrote:
                print()

    except KeyboardInterrupt:

        print(
            "\nBeendet."
        )

        eva.shutdown()

        try:
            from memory.memory_engine import (
                run_reflection_and_save
            )
        except ImportError:
            run_reflection_and_save = None

        if run_reflection_and_save:
            try:
                run_reflection_and_save()
            except Exception as exc:
                logging.exception(
                    "Reflection konnte nicht ausgeführt werden: %s",
                    exc,
                )


if __name__ == "__main__":
    main()
