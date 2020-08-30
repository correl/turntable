import argparse
import importlib.metadata
import json
import logging
from multiprocessing import Queue
import os
from typing import Any, Dict

from dejavu import Dejavu  # type: ignore

from turntable.audio import Listener
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


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    print(f"Turntable {VERSION}")

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default=os.path.expanduser("~/.config/turntable.json")
    )
    args = parser.parse_args()
    with open(args.config, "r") as config_file:
        config: Dict[str, Any] = json.load(config_file)

    pcm_in: "Queue[PCM]" = Queue()
    events: "Queue[Event]" = Queue()

    audio_config = config.get("audio", dict())
    listener = Listener(
        pcm_in,
        audio_config.get("device", "default"),
        framerate=audio_config.get("framerate", 44100),
        channels=audio_config.get("channels", 2),
        period_size=audio_config.get("period_size", 4096),
    )

    dejavu = Dejavu(config.get("dejavu", dict()))

    player = Turntable(listener.framerate, listener.channels, dejavu, pcm_in, events)

    icecast_config = config.get("icecast", dict())
    icecast = Icecast(
        host=icecast_config.get("host", "localhost"),
        port=icecast_config.get("port", 8000),
        mountpoint=icecast_config.get("mountpoint", "stream.mp3"),
        user=icecast_config.get("admin_user", "admin"),
        password=icecast_config.get("admin_password", "hackme"),
    )

    processes = [listener, player]
    for process in processes:
        process.daemon = True
        process.start()
    try:
        icecast.set_title("<Idle>")
        while event := events.get():
            logging.info("Event: %s", event)
            if isinstance(event, StartedPlaying):
                icecast.set_title("<Record starting...>")
            elif isinstance(event, StoppedPlaying):
                icecast.set_title("<Idle>")
            elif isinstance(event, NewMetadata):
                icecast.set_title(event.title)
    except KeyboardInterrupt:
        for process in processes:
            if process.is_alive():
                process.terminate()
