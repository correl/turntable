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
        self.light_state = dict()
        self.active = False

        try:
            lights = hue_response(
                requests.get(f"http://{self.host}/api/{self.username}/lights")
            )
        except HueError as error:
            logger.warn(f"Error fetching lights: %s", error)
            return
        try:
            self.light_id, self.light_state = next(
                filter(
                    lambda i: i[1]["name"].lower() == self.light.lower(), lights.items()
                )
            )
        except StopIteration:
            logger.warn(f"Could not find a light named '%s'", light)
            return
        logger.info("Hue ready")

    def run(self) -> None:
        if not self.light_id:
            logger.warn("No light identified, not starting Hue")
            return
        logger.debug("Starting Hue")
        max_peak = 3000
        audio = None
        stopping = False
        while not stopping:
            try:
                while event := self.events.get(False):
                    if isinstance(event, StartedPlaying):
                        try:
                            self.light_state = hue_response(
                                requests.get(
                                    f"http://{self.host}/api/{self.username}/lights/{self.light_id}"
                                )
                            )
                            logger.debug("Stored light state")
                        except HueError as e:
                            logger.warn(f"Error loading current light state: %s", e)
                        self.active = True
                    elif isinstance(event, StoppedPlaying):
                        self.active = False
                        original_brightness = self.light_state.get("state", {}).get(
                            "bri"
                        )
                        if original_brightness is not None:
                            try:
                                hue_response(
                                    requests.put(
                                        f"http://{self.host}/api/{self.username}/lights/{self.light_id}/state",
                                        json={"bri": original_brightness},
                                    )
                                )
                                logger.info(
                                    "Restored %s to previous brightness", self.light
                                )
                            except HueError as e:
                                logger.warn(f"Error restoring light brightness: %s", e)
                    elif isinstance(event, Exit):
                        stopping = True
            except queue.Empty:
                ...
            if stopping:
                break
            try:
                while sample := self.pcm_in.get(False):
                    audio = sample
            except queue.Empty:
                ...
            if audio and self.active:
                rms = audioop.rms(audio.raw, audio.channels)
                peak = audioop.max(audio.raw, audio.channels)
                max_peak = max(peak, max_peak)
                brightness = int(peak / max_peak * 255)
                logger.debug(f"Brightness: {brightness}")

                requests.put(
                    f"http://{self.host}/api/{self.username}/lights/{self.light_id}/state",
                    json={"bri": brightness, "transitiontime": 1},
                )

            time.sleep(0.1)
        logger.info("Hue stopped")
