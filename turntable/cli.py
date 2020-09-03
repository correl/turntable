import logging

from turntable import application, turntable


def main() -> None:
    with application.run() as events:
        while event := events.get():
            if not isinstance(event, turntable.Audio):
                logging.info("Event: %s", event)
