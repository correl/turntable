from dataclasses import dataclass

from turntable.models import PCM


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
