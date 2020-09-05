import logging
from multiprocessing import Queue

from turntable.application import Application
from turntable.events import Event


def main() -> None:
    events: "Queue[Event]" = Queue()
    app = Application(events)
    app.run()
    try:
        while event := events.get():
            logging.info("Event: %s", event)
    except:
        app.shutdown()
