"""Thread-safe hand-off of raw captured frames from the sniffer thread to the Frame Inspector
window (Tk main thread) -- same put()/drain() pattern as ui/queue_bridge.py. Bounded so that
if the inspector is never opened (nobody drains fast enough) it drops the oldest frames rather
than growing without limit.
"""

import queue
import time


class FrameTap:
    def __init__(self, maxsize: int = 8000):
        self._q: queue.Queue = queue.Queue(maxsize=maxsize)

    def record(self, direction: str, frame_text: str) -> None:
        """Called on the sniffer thread for every complete frame (JSON or not)."""
        try:
            self._q.put_nowait((time.time(), direction, frame_text))
        except queue.Full:
            # Drop one oldest to make room -- a live debug view, not an audit log.
            try:
                self._q.get_nowait()
                self._q.put_nowait((time.time(), direction, frame_text))
            except queue.Empty:
                pass

    def drain(self) -> list[tuple[float, str, str]]:
        items = []
        while True:
            try:
                items.append(self._q.get_nowait())
            except queue.Empty:
                break
        return items
