from collections import deque
import logging
import math
from multiprocessing import Process, Queue
from multiprocessing.connection import Connection
from typing import Deque, List, Tuple, Union

import alsaaudio  # type: ignore

from turntable.models import PCM

logger = logging.getLogger(__name__)


class Listener(Process):
    def __init__(
        self,
        pcm_in: "Queue[PCM]",
        device: str,
        sample_length: int = 30,
        framerate: int = 44100,
        channels: int = 2,
        period_size: int = 1024,
    ) -> None:
        super().__init__()
        logger.info("Initializing Listener")
        self.pcm_in = pcm_in
        self.framerate = framerate
        self.channels = channels
        self.capture = alsaaudio.PCM(
            device=device,
            type=alsaaudio.PCM_CAPTURE,
            format=alsaaudio.PCM_FORMAT_S16_LE,
            periodsize=period_size,
            rate=framerate,
            channels=channels,
        )
        available_channels: List[int] = self.capture.getchannels()
        available_rates: Union[int, Tuple[int, int]] = self.capture.getrates()
        if channels not in available_channels:
            raise ValueError(f"Unsupported channel count: {channels}")
        if isinstance(available_rates, int):
            framerate = available_rates
        elif framerate not in range(*available_rates):
            raise ValueError(f"Unsupported framerate: {framerate}")
        logger.info(
            "Listener started on '%s' [rate=%d, channels=%d, periodsize=%d]",
            device,
            framerate,
            channels,
            period_size,
        )

    def run(self) -> None:
        while True:
            length, data = self.capture.read()
            if length > 0:
                self.pcm_in.put(PCM(self.framerate, self.channels, data))
            else:
                logger.warning(
                    "Sampler error (length={}, bytes={})".format(length, len(data))
                )
