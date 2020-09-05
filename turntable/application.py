import argparse
from contextlib import contextmanager
import importlib.metadata
import json
import logging
from multiprocessing import Queue
import os
from typing import Any, Dict, Iterator

from dejavu import Dejavu  # type: ignore

from turntable.audio import Listener, Player
from turntable.icecast import Icecast
from turntable.models import PCM
from turntable.turntable import (
    Event,
    NewMetadata,
    StartedPlaying,
    StoppedPlaying,
    Turntable,
)

VERSION = importlib.metadata.version("turntable")
logger = logging.getLogger(__name__)


class Application:
    def __init__(self):
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--config", default=os.path.expanduser("~/.config/turntable.json")
        )
        args = parser.parse_args()
        with open(args.config, "r") as config_file:
            self.config: Dict[str, Any] = json.load(config_file)

        logging.basicConfig(
            level=logging.DEBUG if self.config.get("debug") else logging.INFO
        )
        logger.info("Turntable version %s", VERSION)

        pcm_in: "Queue[PCM]" = Queue()
        pcm_out: "Queue[PCM]" = Queue()
        self.pcm_display: "Queue[PCM]" = Queue()
        self.events: "Queue[Event]" = Queue()

        audio_config = self.config.get("audio", dict())
        listener = Listener(
            [pcm_in, pcm_out, self.pcm_display],
            self.events,
            audio_config.get("device", "default"),
            framerate=audio_config.get("framerate", 44100),
            channels=audio_config.get("channels", 2),
            period_size=audio_config.get("period_size", 4096),
        )

        player = Player(
            pcm_out,
            audio_config.get("output_device", "null"),
            framerate=audio_config.get("framerate", 44100),
            channels=audio_config.get("channels", 2),
            period_size=audio_config.get("period_size", 4096),
        )

        dejavu = Dejavu(self.config.get("dejavu", dict()))

        turntable = Turntable(
            listener.framerate, listener.channels, dejavu, pcm_in, self.events
        )

        icecast_config = self.config.get("icecast", dict())
        icecast = Icecast(
            host=icecast_config.get("host", "localhost"),
            port=icecast_config.get("port", 8000),
            mountpoint=icecast_config.get("mountpoint", "stream.mp3"),
            user=icecast_config.get("admin_user", "admin"),
            password=icecast_config.get("admin_password", "hackme"),
        )

        self.processes = [listener, player, turntable]

    def run(self) -> "Iterator[Queue[Event]]":
        for process in self.processes:
            process.daemon = True
            process.start()

    def shutdown(self) -> None:
        logging.info("Terminating")
        for process in self.processes:
            if process.is_alive():
                process.kill()
