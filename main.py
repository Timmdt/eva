#!/usr/bin/env python3
import sys
import logging
from pathlib import Path

# Enable debug logging
logging.basicConfig(
    level=logging.DEBUG,
    format='[%(name)s] %(levelname)s: %(message)s'
)

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'core'))

from eva import EVA


def main() -> None:
    eva = EVA()
    print(f"--- {eva.name} initialisiert ---")

    startup_text = eva.startup()
    if startup_text:
        eva.speak(startup_text)

    try:
        while True:
            user_input = input("Du: ")
            if user_input.lower() in {"exit", "shutdown", "bye"}:
                print("Auf Wiedersehen!")
                eva.shutdown()
                break

            reply = eva.receive(user_input)
            eva.speak(reply)
    except KeyboardInterrupt:
        print("\nBeendet.")
        eva.shutdown()
        try:
            from memory.memory_engine import run_reflection_and_save
        except ImportError:
            run_reflection_and_save = None
        if run_reflection_and_save:
            run_reflection_and_save()


if __name__ == '__main__':
    main()
