from collections import deque
from dataclasses import dataclass
from typing import Deque, Iterable, Optional, Union


class PCM:
    """16-bit raw PCM audio."""

    def __init__(
        self,
        framerate: int,
        channels: int,
        data: bytes = b"",
        maxlen: Optional[int] = None,
    ):
        self.framerate = framerate
        self.channels = channels
        self._data: Deque[int] = deque(data, maxlen)

    @property
    def raw(self):
        return bytes(self._data)

    @property
    def framesize(self):
        # Two bytes for each channel
        return self.channels * 2

    def __getitem__(self, key: Union[int, slice]) -> "PCM":
        """Address raw data by frame."""
        if isinstance(key, int):
            start = key * self.framesize
            stop = start + self.framesize
            return PCM(self.framerate, self.channels, self.raw[start:stop])
        else:
            start = key.start * self.framesize if key.start is not None else None
            stop = key.stop * self.framesize if key.stop is not None else None
            step = key.step * self.framesize if key.step is not None else None
            return PCM(self.framerate, self.channels, self.raw[start:stop:step])

    def __iter__(self) -> "Iterable[PCM]":
        """Iterate over raw data by frame."""
        for i in range(0, len(self._data), self.framesize):
            yield PCM(self.framerate, self.channels, self.raw[i : i + self.framesize])

    def __len__(self) -> int:
        return len(self._data) // self.framesize

    def append(self, other: "PCM") -> None:
        if other.framerate != self.framerate or other.channels != self.channels:
            raise ValueError("Cannot append incompatible PCM audio")
        self._data.extend(other._data)
