import audioop
import logging
from multiprocessing import Process, Queue
import os
import queue
import time
from typing import Any, Optional

import requests

from turntable.events import *
from turntable.models import PCM

logger = logging.getLogger(__name__)


class HueError(Exception):
    ...


def hue_response(response: requests.Response) -> Any:
    try:
        response.raise_for_status()
        result = response.json()
        try:
            raise HueError(response.json()[0]["error"]["description"])
        except (IndexError, KeyError, TypeError):
            return result
    except requests.HTTPError as e:
        raise HueError(f"http error: {e}") from e
    except ValueError:
        raise HueError("invalid response")


def hue_error(response: Any) -> Optional[str]:
    try:
        return response.json()[0]["error"]["description"]
    except ValueError:
        return "invalid response"
    except (IndexError, KeyError, TypeError):
        return None


class Hue(Process):
    def __init__(
        self,
        pcm_in: "Queue[PCM]",
        events: "Queue[Event]",
        host: str,
        username: str,
        light: str,
    ):
        super().__init__()
        self.pcm_in = pcm_in
        self.events = events
        self.host = host
        self.username = username
        self.light = light
        self.light_id = None

        try:
            lights = hue_response(
                requests.get(f"http://{self.host}/api/{self.username}/lights")
            )
        except HueError as error:
            logger.warn(f"Error fetching lights: {error}")
            return
        try:
            self.light_id = next(
                filter(
                    lambda i: i[1]["name"].lower() == self.light.lower(), lights.items()
                )
            )[0]
        except StopIteration:
            logger.warn(f"Could not find a light named '{light}")
            return
        logger.info("Hue ready")

    def run(self) -> None:
        if not self.light_id:
            logger.warn("No light identified, not starting Hue")
            return
        logger.debug("Starting Hue")
        max_peak = 3000
        audio = None
        while True:
            try:
                while event := self.events.get(False):
                    ...
            except queue.Empty:
                ...
            try:
                while sample := self.pcm_in.get(False):
                    audio = sample
            except queue.Empty:
                ...
            if not audio:
                continue
            rms = audioop.rms(audio.raw, audio.channels)
            peak = audioop.max(audio.raw, audio.channels)
            max_peak = max(peak, max_peak)
            brightness = int(peak / max_peak * 255)
            logger.debug(f"Brightness: {brightness}")

            requests.put(
                "http://192.168.1.199/api/bx1YKf6IQmU-W1MLHrsZ79Wz4bRWiBShb4ewBpfm/lights/7/state",
                json={"bri": brightness, "transitiontime": 1},
            )

            # requests.put(
            #     "http://192.168.1.199/api/bx1YKf6IQmU-W1MLHrsZ79Wz4bRWiBShb4ewBpfm/groups/2/action",
            #     json={"bri": brightness, "transitiontime": 1},
            # )

            time.sleep(0.1)
