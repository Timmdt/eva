#!/usr/bin/env python3

import logging
from pathlib import Path

# Debug Logging
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(name)s] %(levelname)s: %(message)s'
)

ROOT = Path(__file__).resolve().parent

from core.eva import EVA


def main() -> None:
    eva = EVA()

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

            reply = eva.receive(
                user_input
            )

            if reply:
                eva.speak(
                    reply
                )

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