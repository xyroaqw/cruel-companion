"""The vision capture thread: finds the AQW window, grabs frames, runs the glow-zone
detector, and pushes VisualCueEvents into the EventBridge -- the same seam the packet
sniffer uses, so GameState and the rules engine don't know or care which sensor an event
came from.

Vision handles ONLY color-cue (glow/telegraph) detection: that's client-rendered and
invisible to packet capture. All text/HP/zone data comes from the packet layer.

Like every capture-side component, this thread only ever calls bridge.put(); it never touches
GameState directly (see ui/queue_bridge.py).
"""

import threading
import time

from companion.protocol.events import VisualCueEvent
from companion.ui.queue_bridge import EventBridge
from companion.vision.capture import ScreenGrabber
from companion.vision.cues import CueProfile
from companion.vision.detector import CueEdgeTracker, ZoneDetector
from companion.vision.window import find_game_window

# How long to idle between window-lookup retries while the game window can't be found.
WINDOW_RETRY_SECONDS = 1.5


class VisionWorker(threading.Thread):
    def __init__(
        self,
        bridge: EventBridge,
        profiles: list[CueProfile],
        title_substrings: list[str],
        fps: float = 5.0,
    ):
        super().__init__(daemon=True, name="vision-worker")
        self._bridge = bridge
        self._detector = ZoneDetector(profiles)
        self._tracker = CueEdgeTracker()
        self._title_substrings = title_substrings
        self._frame_period = 1.0 / max(fps, 0.5)
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        grabber = ScreenGrabber()
        window_was_lost = False
        try:
            while not self._stop_event.is_set():
                rect = find_game_window(self._title_substrings)
                if rect is None:
                    if not window_was_lost:
                        print(
                            "[vision] game window not found (looking for titles containing "
                            f"{self._title_substrings}); retrying..."
                        )
                        window_was_lost = True
                    self._stop_event.wait(WINDOW_RETRY_SECONDS)
                    continue
                if window_was_lost:
                    print(f"[vision] game window found: {rect.width}x{rect.height}")
                    window_was_lost = False

                started = time.monotonic()
                frame = grabber.grab(rect)

                for cue_id, active, coverage in self._tracker.update(self._detector.read(frame)):
                    self._bridge.put(
                        VisualCueEvent(
                            ts=time.time(), cue_id=cue_id, active=active, coverage_pct=coverage
                        )
                    )

                elapsed = time.monotonic() - started
                self._stop_event.wait(max(self._frame_period - elapsed, 0.01))
        finally:
            grabber.close()
