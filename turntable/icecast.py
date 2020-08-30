import logging
import os

import requests

logger = logging.getLogger(__name__)


class Icecast:
    def __init__(self, host: str, port: int, mountpoint: str, user: str, password: str):
        self.host = host
        self.port = port
        self.mountpoint = mountpoint
        self.credentials = (user, password)

    def set_title(self, title: str):
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
