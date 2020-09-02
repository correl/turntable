import logging
import queue

import pyglet  # type: ignore
import pyglet.clock  # type: ignore

from turntable import application, turntable

def main():
    window = pyglet.window.Window(fullscreen=True)
    with application.run() as events:
        label = pyglet.text.Label(
            "<Idle>",
            font_name='Noto Sans',
            font_size=36,
            x = window.width // 2,
            y = window.height // 2,
            anchor_x = 'center',
            anchor_y = 'center')

        @window.event
        def on_draw():
            window.clear()
            label.draw()

        def check_events(dt):
            try:
                event = events.get(False)
                logging.info("Event: %s", event)
                logging.info("Label: %s", label)
                if isinstance(event, turntable.StartedPlaying):
                    label.text = "<Record starting...>"
                elif isinstance(event, turntable.StoppedPlaying):
                    label.text = "<Idle>"
                elif isinstance(event, turntable.NewMetadata):
                    label.text = event.title
            except queue.Empty:
                ...
            except:
                logging.exception("Oops")

        pyglet.clock.schedule_interval_soft(check_events, 0.5)
        pyglet.app.run()
        # icecast.set_title("<Idle>")
        # while event := events.get():
        #     logging.info("Event: %s", event)
            # if isinstance(event, StartedPlaying):
            #     icecast.set_title("<Record starting...>")
            # elif isinstance(event, StoppedPlaying):
            #     icecast.set_title("<Idle>")
            # elif isinstance(event, NewMetadata):
            #     icecast.set_title(event.title)
