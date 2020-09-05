import audioop
from dataclasses import dataclass
import enum
import logging
from multiprocessing import Process, Queue
from multiprocessing.connection import Connection
import struct
import time
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple
import wave

from dejavu import Dejavu  # type: ignore
from dejavu.base_classes.base_recognizer import BaseRecognizer  # type: ignore
import dejavu.config.settings  # type: ignore


from turntable.events import *
from turntable.models import PCM

logger = logging.getLogger(__name__)


class State(enum.Enum):
    idle = "idle"
    playing = "playing"
    silent = "silent"


class PCMRecognizer(BaseRecognizer):
    @staticmethod
    def pcm_to_channel_data(pcm: PCM) -> List[List[int]]:
        def to_ints(data: bytes) -> List[int]:
            return list(struct.unpack("{}h".format(len(data) // 2), data))

        stream = to_ints(pcm.raw)
        return [stream[channel :: pcm.channels] for channel in range(pcm.channels)]

    def recognize(self, pcm: PCM) -> Dict[str, Any]:
        data = PCMRecognizer.pcm_to_channel_data(pcm)
        t = time.time()
        matches, fingerprint_time, query_time, align_time = self._recognize(*data)
        t = time.time() - t
        return {
            dejavu.config.settings.TOTAL_TIME: t,
            dejavu.config.settings.FINGERPRINT_TIME: fingerprint_time,
            dejavu.config.settings.QUERY_TIME: query_time,
            dejavu.config.settings.ALIGN_TIME: align_time,
            dejavu.config.settings.RESULTS: matches,
        }


class Turntable(Process):
    def __init__(
        self,
        pcm_in: "Queue[PCM]",
        events_out: "List[Queue[Event]]",
        framerate: int,
        channels: int,
        dejavu: Dejavu,
        fingerprint_delay: int = 5,
        fingerprint_identify_delay: int = 5,
        fingerprint_identify_seconds: int = 5,
        fingerprint_store_path: str = "/tmp/fingerprint.wav",
        fingerprint_store_seconds: int = 30,
        sample_seconds: int = 30,
        silence_threshold: int = 20,
        stop_delay: int = 5,
    ) -> None:
        super().__init__()
        maxlen = channels * 2 * framerate * sample_seconds
        self.buffer = PCM(framerate=framerate, channels=channels, maxlen=maxlen)
        self.recognizer = PCMRecognizer(dejavu)
        self.pcm_in = pcm_in
        self.events_out = events_out
        self.state: State = State.idle
        self.identified = False
        self.captured = False
        self.last_update: float = time.time()
        self.fingerprint_delay = fingerprint_delay
        self.fingerprint_identify_delay = fingerprint_identify_delay
        self.fingerprint_identify_seconds = fingerprint_identify_seconds
        self.fingerprint_store_path = fingerprint_store_path
        self.fingerprint_store_seconds = fingerprint_store_seconds
        self.silence_threshold = silence_threshold
        self.stop_delay = stop_delay
        logger.info("Turntable ready")

    def run(self) -> None:
        logger.debug("Starting Turntable")
        while fragment := self.pcm_in.get():
            self.buffer.append(fragment)
            maximum = audioop.max(fragment.raw, 2)
            self.update_audiolevel(maximum)

    def publish(self, event: Event) -> None:
        for queue in self.events_out:
            queue.put(event)

    def update_audiolevel(self, level: int) -> None:
        newstate = self.state
        now = time.time()
        if self.state == State.idle:
            # Transition to playing if there's sufficient audio.
            if level > self.silence_threshold:
                self.transition(State.playing, now)
        elif self.state == State.playing:
            # Transition to silent when the audio drops out.
            if level <= self.silence_threshold:
                self.transition(State.silent, now)
            elif (
                now - self.last_update
                >= self.fingerprint_delay + self.fingerprint_identify_seconds
                and self.identified == False
            ):
                startframe = -self.buffer.framerate * self.fingerprint_identify_seconds
                sample = self.buffer[startframe:]
                identification = self.recognizer.recognize(sample)
                logger.debug("Dejavu results: %s", identification)
                if results := identification[dejavu.config.settings.RESULTS]:
                    self.publish(
                        NewMetadata(
                            results[0][dejavu.config.settings.SONG_NAME].decode("utf-8")
                        )
                    )
                else:
                    self.publish(NewMetadata("Unknown Artist - Unknown Album"))
                self.identified = True
            elif (
                now - self.last_update
                >= self.fingerprint_delay + self.fingerprint_store_seconds
                and self.captured == False
            ):
                startframe = -self.buffer.framerate * self.fingerprint_store_seconds
                sample = self.buffer[startframe:]
                with wave.open(self.fingerprint_store_path, "wb") as wavfile:
                    wavfile.setsampwidth(2)
                    wavfile.setnchannels(sample.channels)
                    wavfile.setframerate(sample.framerate)
                    wavfile.writeframesraw(sample.raw)
                logger.info("Captured waveform for fingerprinting")
                self.captured = True

        elif self.state == State.silent:
            # Transition back to playing if audio returns within STOP_DELAY
            # seconds, otherwise transition to idle.
            if level > self.silence_threshold:
                self.transition(State.playing, now)
            elif now - self.last_update >= self.stop_delay:
                self.transition(State.idle, now)

    def transition(self, to_state: State, updated_at: float) -> None:
        from_state = self.state
        logger.debug("Transition: %s => %s", from_state, to_state)
        self.state = to_state
        self.last_update = updated_at

        if to_state == State.idle:
            self.publish(StoppedPlaying())
            self.identified = False
            self.captured = False
        elif from_state == State.idle and to_state == State.playing:
            self.publish(StartedPlaying())
