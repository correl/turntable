from bisect import bisect
from collections import deque
import logging
from multiprocessing import Queue
import os
import queue
from statistics import fmean
from typing import Deque, Iterable, List, Optional, Tuple, Union

import numpy as np  # type: ignore
import pygame  # type: ignore
from pygame.locals import *  # type: ignore
import scipy.signal  # type: ignore

from turntable import application, events, models, turntable

logger = logging.getLogger(__name__)


class Plot:
    def __init__(
        self,
        screen,
        x: int,
        y: int,
        width: int,
        height: int,
        bars: int = 20,
        bar_colors: List[Tuple[int, Tuple[int, int, int]]] = [
            (0, (255, 255, 255)),
        ],
        lines_color: Tuple[int, int, int] = (128, 128, 128),
        smoothing: int = 5,
    ) -> None:
        self.screen = screen
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.bars = bars
        self.bar_colors = bar_colors
        self.lines_color = lines_color
        self.audio = models.PCM(44100, 2)
        self.spectrums: Deque[np.array] = deque(maxlen=smoothing)

    def spectrum(self) -> np.array:
        data = np.fromstring(self.audio.raw, dtype=np.int16)
        if len(data) == 0:
            return data
        merged = np.mean(np.reshape(data, (-1, self.audio.channels)), axis=1)
        fft = np.abs(np.fft.fft(merged))
        fft = fft[: len(fft) // 2]
        dbfs = 20 * np.log10(fft * 2 / (len(fft) * 2 ** 15))
        dbfs = np.maximum(-100, dbfs) + 100
        self.spectrums.append(dbfs)
        return np.mean(np.column_stack(self.spectrums), axis=1)

    def draw_lines(self) -> None:
        data = self.spectrum()
        if len(data) == 0:
            return

        nlines = self.width // 4
        data = np.mean(
            np.reshape(data[: len(data) // nlines * nlines], (-1, len(data) // nlines)),
            axis=1,
        )
        lines = self.height * (data / 100)
        for i, line in enumerate(lines):
            pygame.draw.line(
                self.screen,
                self.lines_color,
                (self.x + i * 4, self.height),
                (self.x + i * 4, self.height - int(line)),
            )

    def draw_bars(self) -> None:
        data = self.spectrum()
        if len(data) == 0:
            return
        fft = np.max(
            np.reshape(
                data[: len(data) // self.bars * self.bars], (-1, len(data) // self.bars)
            ),
            axis=1,
        )

        light_width = self.width // (2 * self.bars - 1)
        light_height = self.height // 2 // light_width
        light_steps = self.height // light_height // 2
        lights = fft * light_steps / 100

        color_keys = [k for k, v in self.bar_colors]
        color_values = [v for k, v in self.bar_colors]
        for i, steps in enumerate(lights):
            for step in range(int(steps)):
                color = color_values[bisect(color_keys, step / light_steps * 100) - 1]
                pygame.draw.rect(
                    self.screen,
                    color,
                    (
                        self.x + i * light_width * 2,
                        self.height - step * light_height * 2,
                        light_width,
                        -light_height,
                    ),
                )


def main():
    event_queue: "Queue[events.Event]" = Queue()
    pcm_in: "Queue[models.PCM]" = Queue()
    app = application.Application(event_queue, pcm_in)
    config = app.config.get("gui", dict())
    disp_no = os.getenv("DISPLAY")
    if disp_no:
        logger.info("I'm running under X display = {0}".format(disp_no))

    # Check which frame buffer drivers are available
    # Start with fbcon since directfb hangs with composite output
    drivers = ["x11", "fbcon", "directfb", "svgalib"]
    found = False
    for driver in drivers:
        # Make sure that SDL_VIDEODRIVER is set
        if not os.getenv("SDL_VIDEODRIVER"):
            os.putenv("SDL_VIDEODRIVER", driver)
        try:
            pygame.display.init()
        except pygame.error:
            logger.warn("Driver: {0} failed.".format(driver))
            continue
        found = True
        break

    if not found:
        raise Exception("No suitable video driver found!")

    size = (pygame.display.Info().current_w, pygame.display.Info().current_h)
    logger.info("Maximum size: %d x %d" % (size[0], size[1]))
    WIDTH = int(config.get("width", size[0]))
    HEIGHT = int(config.get("height", size[1]))
    FPS = int(config.get("fps", 60))
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.mouse.set_visible(False)
    # Clear the screen to start
    screen.fill((0, 0, 0))
    # Initialise font support
    pygame.font.init()
    font = pygame.font.Font(pygame.font.get_default_font(), int(20 * HEIGHT / 720))
    # Render the screen
    pygame.display.update()

    plot = Plot(
        screen=screen,
        x=0,
        y=0,
        width=screen.get_width(),
        height=screen.get_height() - 50,
        bars=15,
        bar_colors=config.get(
            "bars",
            [
                (0, (0, 255, 0)),
                (50, (255, 255, 0)),
                (75, (255, 0, 0)),
            ],
        ),
        lines_color=config.get("lines", (128, 128, 128)),
        smoothing=config.get("smoothing", 5),
    )

    try:
        app.run()
        clock = pygame.time.Clock()
        title = "<Idle>"
        while True:
            for event in pygame.event.get():
                if event.type == QUIT or (
                    event.type == KEYDOWN and event.key == K_ESCAPE
                ):
                    app.shutdown()
                    pygame.quit()
                    return
            try:
                while event := event_queue.get(False):
                    ...
                    if isinstance(event, events.StartedPlaying):
                        title = "<Starting...>"
                    elif isinstance(event, events.StoppedPlaying):
                        title = "<Idle>"
                    elif isinstance(event, events.NewMetadata):
                        title = event.title

            except queue.Empty:
                ...
            try:
                while sample := pcm_in.get(False):
                    plot.audio = sample
            except queue.Empty:
                ...
            screen.fill((0, 0, 0))
            plot.draw_lines()
            plot.draw_bars()
            title_text = font.render(title, True, (255, 255, 255))
            title_rect = title_text.get_rect()
            title_rect.left = 25
            title_rect.centery = screen.get_height() - 25
            screen.blit(title_text, title_rect)
            pygame.display.update()
            clock.tick(FPS)
    except:
        logger.exception("Shutting down")
    finally:
        app.shutdown()
