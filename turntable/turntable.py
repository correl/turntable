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


from turntable.models import PCM

logger = logging.getLogger(__name__)


FINGERPRINT_DELAY = 5
FINGERPRINT_IDENTIFY_DELAY = 5
FINGERPRINT_IDENTIFY_SECONDS = 5
FINGERPRINT_STORE_SECONDS = 30
SAMPLE_SECONDS = 30
SILENCE_THRESHOLD = 20
STOP_DELAY = 5


class State(enum.Enum):
    idle = "idle"
    playing = "playing"
    silent = "silent"


class Event:
    @property
    def type(self) -> str:
        return self.__class__.__name__

    def __repr__(self) -> str:
        return f"<{self.type}>"


class StartedPlaying(Event):
    ...


class StoppedPlaying(Event):
    ...


@dataclass
class NewMetadata(Event):
    title: str

@dataclass
class Audio(Event):
    pcm: PCM

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
        framerate: int,
        channels: int,
        dejavu: Dejavu,
        pcm_in: "Queue[PCM]",
        events_out: "Queue[Event]",
    ) -> None:
        super().__init__()
        maxlen = channels * 2 * framerate * SAMPLE_SECONDS
        self.buffer = PCM(framerate=framerate, channels=channels, maxlen=maxlen)
        self.recognizer = PCMRecognizer(dejavu)
        self.pcm_in = pcm_in
        self.events_out = events_out
        self.state: State = State.idle
        self.identified = False
        self.captured = False
        self.last_update: float = time.time()

    def run(self) -> None:
        logger.info("Initializing Turntable")
        while fragment := self.pcm_in.get():
            self.buffer.append(fragment)
            self.events_out.put(Audio(fragment))
            maximum = audioop.max(fragment.raw, 2)
            self.update_audiolevel(maximum)

    def update_audiolevel(self, level: int) -> None:
        newstate = self.state
        now = time.time()
        if self.state == State.idle:
            # Transition to playing if there's sufficient audio.
            if level > SILENCE_THRESHOLD:
                self.transition(State.playing, now)
        elif self.state == State.playing:
            # Transition to silent when the audio drops out.
            if level <= SILENCE_THRESHOLD:
                self.transition(State.silent, now)
            elif (
                now - self.last_update
                >= FINGERPRINT_DELAY + FINGERPRINT_IDENTIFY_SECONDS
                and self.identified == False
            ):
                startframe = - self.buffer.framerate * FINGERPRINT_IDENTIFY_SECONDS
                sample = self.buffer[startframe:]
                identification = self.recognizer.recognize(sample)
                logger.debug("Dejavu results: %s", identification)
                if results := identification[dejavu.config.settings.RESULTS]:
                    self.events_out.put(
                        NewMetadata(
                            results[0][dejavu.config.settings.SONG_NAME].decode("utf-8")
                        )
                    )
                else:
                    self.events_out.put(NewMetadata("Unknown Artist - Unknown Album"))
                self.identified = True
            elif (
                now - self.last_update >= FINGERPRINT_DELAY + FINGERPRINT_STORE_SECONDS
                and self.captured == False
            ):
                startframe = - self.buffer.framerate * FINGERPRINT_STORE_SECONDS
                sample = self.buffer[startframe:]
                with wave.open("/tmp/fingerprint.wav", "wb") as wavfile:
                    wavfile.setsampwidth(2)
                    wavfile.setnchannels(sample.channels)
                    wavfile.setframerate(sample.framerate)
                    wavfile.writeframesraw(sample.raw)
                logger.info("Captured waveform for fingerprinting")
                self.captured = True

        elif self.state == State.silent:
            # Transition back to playing if audio returns within STOP_DELAY
            # seconds, otherwise transition to idle.
            if level > SILENCE_THRESHOLD:
                self.transition(State.playing, now)
            elif now - self.last_update >= STOP_DELAY:
                self.transition(State.idle, now)

    def transition(self, to_state: State, updated_at: float) -> None:
        from_state = self.state
        logger.debug("Transition: %s => %s", from_state, to_state)
        self.state = to_state
        self.last_update = updated_at

        if to_state == State.idle:
            self.events_out.put(StoppedPlaying())
            self.identified = False
            self.captured = False
        elif from_state == State.idle and to_state == State.playing:
            self.events_out.put(StartedPlaying())
