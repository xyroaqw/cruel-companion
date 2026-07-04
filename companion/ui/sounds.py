"""Per-alert-level sound cues via stdlib winsound -- no audio files to ship, no extra
dependency. Beeps run on a throwaway daemon thread because winsound.Beep blocks, and a
non-blocking lock drops overlapping requests: during an alert burst you hear one pattern,
not a queued-up siren concert.
"""

import sys
import threading

from companion.rules.schema import AlertLevel

# (frequency_hz, duration_ms) sequences -- distinct enough to tell apart without looking.
PATTERNS: dict[AlertLevel, list[tuple[int, int]]] = {
    AlertLevel.INFO: [(880, 90)],
    AlertLevel.WARNING: [(660, 110), (880, 110)],
    AlertLevel.CRITICAL: [(1245, 120), (1245, 120), (1245, 120)],
}


class SoundPlayer:
    def __init__(self, enabled: bool = True):
        self._enabled = enabled and sys.platform == "win32"
        self._playing = threading.Lock()

    def play(self, level: AlertLevel) -> None:
        if not self._enabled:
            return
        if not self._playing.acquire(blocking=False):
            return  # a pattern is already sounding; don't stack beeps
        threading.Thread(
            target=self._beep, args=(PATTERNS[level],), daemon=True, name="alert-sound"
        ).start()

    def _beep(self, pattern: list[tuple[int, int]]) -> None:
        try:
            import winsound

            for freq, dur in pattern:
                winsound.Beep(freq, dur)
        finally:
            self._playing.release()
