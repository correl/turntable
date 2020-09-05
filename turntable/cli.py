import logging

from turntable import application, turntable


def main() -> None:
    app = application.Application()
    with app.run() as events:
        while event := events.get():
            if not isinstance(event, turntable.Audio):
                logging.info("Event: %s", event)
