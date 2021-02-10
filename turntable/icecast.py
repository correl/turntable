import logging
from multiprocessing import Process, Queue
import os

import requests

from turntable.events import *

logger = logging.getLogger(__name__)


class Icecast(Process):
    def __init__(
        self,
        events: "Queue[Event]",
        host: str,
        port: int,
        mountpoint: str,
        user: str,
        password: str,
    ) -> None:
        super().__init__()
        self.events = events
        self.host = host
        self.port = port
        self.mountpoint = mountpoint
        self.credentials = (user, password)
        logger.info("Icecast Updater ready for '%s:%d/%s'", host, port, mountpoint)

    def set_title(self, title: str) -> None:
        logger.info("Updating icecast title to '%s'", title)
        try:
            requests.get(
                f"http://{self.host}:{self.port}/admin/metadata",
                params={
                    "mount": os.path.join("/", self.mountpoint),
                    "mode": "updinfo",
                    "song": title,
                },
                auth=self.credentials,
            )
        except requests.RequestException as e:
            logger.warning("Failed to update icecast metadata: %s", e)

    def run(self) -> None:
        logger.debug("Starting Icecast Updater")
        self.set_title("<Idle>")
        while event := self.events.get():
            if isinstance(event, StartedPlaying):
                self.set_title("<Starting...>")
            elif isinstance(event, StoppedPlaying):
                self.set_title("<Idle>")
            elif isinstance(event, NewMetadata):
                self.set_title(event.title)
            elif isinstance(event, Exit):
                break
        logger.info("Icecast Updater stopped")
