import argparse
from contextlib import contextmanager
import importlib.metadata
import json
import logging
from multiprocessing import Process, Queue
import os
from typing import Any, Dict, Iterator, List, Optional

from dejavu import Dejavu  # type: ignore

from turntable.audio import Listener, Player
from turntable.events import Event
from turntable.hue import Hue
from turntable.icecast import Icecast
from turntable.models import PCM
from turntable.turntable import Turntable

VERSION = importlib.metadata.version("turntable")
logger = logging.getLogger(__name__)


class Application:
    def __init__(self, events: "Queue[Event]", pcm: "Optional[Queue[PCM]]" = None):
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

        self.processes: List[Process] = []
        event_queues: "List[Queue[Event]]" = [events]

        audio_config = self.config.get("audio", dict())
        pcm_in: "Queue[PCM]" = Queue()
        hue_pcm: "Queue[PCM]" = Queue()
        pcms: "List[Queue[PCM]]" = [pcm_in, hue_pcm]
        if pcm:
            pcms.append(pcm)
        if output_device := audio_config.get("output_device"):
            pcm_out: "Queue[PCM]" = Queue()
            player = Player(
                pcm_out,
                audio_config.get("output_device", "null"),
                framerate=audio_config.get("framerate", 44100),
                channels=audio_config.get("channels", 2),
                period_size=audio_config.get("period_size", 4096),
            )
            self.processes.append(player)
            pcms.append(pcm_out)
        listener = Listener(
            pcms,
            audio_config.get("device", "default"),
            framerate=audio_config.get("framerate", 44100),
            channels=audio_config.get("channels", 2),
            period_size=audio_config.get("period_size", 4096),
        )
        self.processes.append(listener)

        icecast_config = self.config.get("icecast", dict())
        icecast_enabled = icecast_config.get("enabled", False)
        if icecast_enabled:
            icecast_events: "Queue[Event]" = Queue()
            icecast = Icecast(
                events=icecast_events,
                host=icecast_config.get("host", "localhost"),
                port=icecast_config.get("port", 8000),
                mountpoint=icecast_config.get("mountpoint", "stream.mp3"),
                user=icecast_config.get("admin_user", "admin"),
                password=icecast_config.get("admin_password", "hackme"),
            )
            event_queues.append(icecast_events)
            self.processes.append(icecast)

        hue_config = self.config.get("hue", dict())
        hue_enabled = hue_config.get("enabled", False)
        if hue_enabled:
            hue_events: "Queue[Event]" = Queue()
            hue = Hue(
                pcm_in=hue_pcm,
                events=hue_events,
                host=hue_config.get("host", "localhost"),
                username=hue_config.get("username", "turntable"),
                light=hue_config.get("light", "Light"),
            )
            event_queues.append(hue_events)
            self.processes.append(hue)

        dejavu = Dejavu(self.config.get("dejavu", dict()))

        turntable_config = self.config.get("turntable", dict())
        turntable = Turntable(
            pcm_in,
            event_queues,
            listener.framerate,
            listener.channels,
            dejavu,
            fingerprint_delay=turntable_config.get("fingerprint_delay", 5),
            fingerprint_identify_delay=turntable_config.get(
                "fingerprint_identify_delay", 5
            ),
            fingerprint_identify_seconds=turntable_config.get(
                "fingerprint_identify_seconds", 5
            ),
            fingerprint_store_path=turntable_config.get(
                "fingerprint_store_path", "/tmp/fingerprint.wav"
            ),
            fingerprint_store_seconds=turntable_config.get(
                "fingerprint_store_seconds", 30
            ),
            sample_seconds=turntable_config.get("sample_seconds", 30),
            silence_threshold=turntable_config.get("silence_threshold", 20),
            stop_delay=turntable_config.get("stop_delay", 5),
        )
        self.processes.append(turntable)

    def run(self) -> None:
        for process in self.processes:
            logging.info("Starting %s", process)
            process.daemon = True
            process.start()

    def shutdown(self) -> None:
        logging.info("Terminating")
        for process in self.processes:
            if process.is_alive():
                process.kill()
