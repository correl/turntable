import logging
import queue
from statistics import fmean
from typing import Iterable, List, Optional, Tuple, Union

import numpy as np  # type: ignore
import pyglet  # type: ignore
import pyglet.clock  # type: ignore
import scipy.signal  # type: ignore

from turntable import application, models, turntable


class Plot:
    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        bars: int = 20,
        bar_width: int = 40,
        color: Tuple[int, int, int] = (255, 255, 255),
        batch: Optional[pyglet.graphics.Batch] = None,
    ) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.bars = bars
        self.bar_width = bar_width
        self.color = color
        self.batch = batch or pyglet.graphics.Batch()
        self.lines: List[pyglet.shapes.Line] = []
        self.audio = b""

    def update(self):
        data = np.fromstring(self.audio, dtype=np.int16)
        fft = abs(np.fft.fft(data).real)
        fft = fft[: len(fft) // 2]
        heights = scipy.signal.resample(fft, self.bars) * self.height / 2 ** 16
        self.lines = [
            pyglet.shapes.Line(
                self.x + x / self.bars * self.width,
                0,
                self.x + x / self.bars * self.width,
                y,
                width=self.bar_width,
                color=self.color,
                batch=self.batch,
            )
            for x, y in enumerate(heights)
        ]

    def draw(self) -> None:
        self.batch.draw()


def main():
    window = pyglet.window.Window(fullscreen=True)
    with application.run() as events:
        audio = b""
        label = pyglet.text.Label(
            "<Idle>",
            font_name="Noto Sans",
            font_size=36,
            x=window.width // 2,
            y=window.height // 2,
            anchor_x="center",
            anchor_y="center",
        )
        batch = pyglet.graphics.Batch()
        plot = Plot(
            x=0,
            y=0,
            width=window.width,
            height=window.height,
            bars=40,
            bar_width=window.width // 45,
            color=(139, 0, 139),
            batch=batch,
        )

        @window.event
        def on_draw():
            window.clear()
            batch.draw()
            label.draw()

        def check_events(dt):
            try:
                event = events.get(False)
                if isinstance(event, turntable.StartedPlaying):
                    label.text = "<Record starting...>"
                elif isinstance(event, turntable.StoppedPlaying):
                    label.text = "<Idle>"
                elif isinstance(event, turntable.NewMetadata):
                    label.text = event.title
                elif isinstance(event, turntable.Audio):
                    plot.audio = event.pcm.raw
            except queue.Empty:
                ...

        def update_vis(dt):
            plot.update()

        pyglet.clock.schedule(check_events)
        pyglet.clock.schedule_interval(update_vis, 0.03)
        pyglet.app.run()
