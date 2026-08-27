import logging

from .controller import SentryController


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    SentryController().run()


if __name__ == "__main__":
    main()
