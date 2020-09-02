import logging

from turntable import application


def main() -> None:
    with application.run() as events:
        while event := events.get():
            logging.info("Event: %s", event)
