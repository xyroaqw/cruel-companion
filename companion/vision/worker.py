"""The vision capture thread: finds the AQW window, grabs frames, runs the zone detector and
OCR, and pushes normalized events into the EventBridge -- exactly the same seam the packet
sniffer uses, so GameState and the rules engine don't know or care which sensor an event
came from.

Like every capture-side component, this thread only ever calls bridge.put(); it never touches
GameState directly (see ui/queue_bridge.py).
"""

import threading
import time

from companion.protocol.events import MessageEvent, VisualCueEvent
from companion.ui.queue_bridge import EventBridge
from companion.vision.capture import ScreenGrabber
from companion.vision.cues import CueProfile
from companion.vision.detector import CueEdgeTracker, ZoneDetector
from companion.vision.ocr import OcrRegion, TextDeduper, create_ocr_engine
from companion.vision.window import find_game_window

# How long to idle between window-lookup retries while the game window can't be found.
WINDOW_RETRY_SECONDS = 1.5

OCR_MESSAGE_KIND = "screen_ocr"


class VisionWorker(threading.Thread):
    def __init__(
        self,
        bridge: EventBridge,
        profiles: list[CueProfile],
        title_substrings: list[str],
        fps: float = 5.0,
        ocr_enabled: bool = True,
        ocr_interval_ms: int = 600,
        ocr_regions: list[OcrRegion] | None = None,
    ):
        super().__init__(daemon=True, name="vision-worker")
        self._bridge = bridge
        self._detector = ZoneDetector(profiles)
        self._tracker = CueEdgeTracker()
        self._deduper = TextDeduper()
        self._title_substrings = title_substrings
        self._frame_period = 1.0 / max(fps, 0.5)
        self._ocr_enabled = ocr_enabled and bool(ocr_regions)
        self._ocr_interval = ocr_interval_ms / 1000.0
        self._ocr_regions = list(ocr_regions or [])
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        grabber = ScreenGrabber()
        ocr = create_ocr_engine() if self._ocr_enabled else None
        if self._ocr_enabled and ocr is None:
            print(
                "[vision] OCR disabled: rapidocr-onnxruntime is not installed "
                "(zone detection still active)"
            )

        window_was_lost = False
        next_ocr_at = 0.0
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

                if ocr is not None and started >= next_ocr_at:
                    self._run_ocr(ocr, frame)
                    next_ocr_at = started + self._ocr_interval

                elapsed = time.monotonic() - started
                self._stop_event.wait(max(self._frame_period - elapsed, 0.01))
        finally:
            grabber.close()

    def _run_ocr(self, ocr, frame) -> None:
        height, width = frame.shape[:2]
        for region in self._ocr_regions:
            x0, x1 = int(region.left * width), max(int(region.right * width), 1)
            y0, y1 = int(region.top * height), max(int(region.bottom * height), 1)
            crop = frame[y0:y1, x0:x1]
            if crop.size == 0:
                continue
            text = self._deduper.offer(region.name, ocr.read_text(crop))
            if text:
                self._bridge.put(MessageEvent(ts=time.time(), text=text, raw_kind=OCR_MESSAGE_KIND))
