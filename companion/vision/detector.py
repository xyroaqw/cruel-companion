"""Pure frame -> cue-reading logic: HSV color masking for glow/telegraph detection, plus
on/off edge tracking with hysteresis. No capture or threading here so it stays unit-testable
with synthetic numpy frames.
"""

from dataclasses import dataclass

import cv2
import numpy as np

from companion.vision.cues import CueProfile


@dataclass(frozen=True)
class CueReading:
    cue_id: str
    coverage_pct: float
    threshold_pct: float

    @property
    def over_threshold(self) -> bool:
        return self.coverage_pct >= self.threshold_pct


class ZoneDetector:
    def __init__(self, profiles: list[CueProfile]):
        self._profiles = list(profiles)

    def read(self, frame_bgr: np.ndarray) -> list[CueReading]:
        if not self._profiles:
            return []
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        height, width = hsv.shape[:2]

        readings = []
        for profile in self._profiles:
            left, top, right, bottom = profile.region
            x0, x1 = int(left * width), max(int(right * width), int(left * width) + 1)
            y0, y1 = int(top * height), max(int(bottom * height), int(top * height) + 1)
            crop = hsv[y0:y1, x0:x1]

            mask = _hsv_mask(crop, profile.hsv_lower, profile.hsv_upper)
            coverage = 100.0 * int(np.count_nonzero(mask)) / mask.size
            readings.append(
                CueReading(
                    cue_id=profile.id,
                    coverage_pct=coverage,
                    threshold_pct=profile.min_coverage_pct,
                )
            )
        return readings


def _hsv_mask(
    hsv: np.ndarray, lower: tuple[int, int, int], upper: tuple[int, int, int]
) -> np.ndarray:
    lh, ls, lv = lower
    uh, us, uv = upper
    if lh <= uh:
        return cv2.inRange(hsv, np.array([lh, ls, lv]), np.array([uh, us, uv]))
    # Hue wraparound (reds): union of [lh..179] and [0..uh] at the same S/V bounds.
    high = cv2.inRange(hsv, np.array([lh, ls, lv]), np.array([179, us, uv]))
    low = cv2.inRange(hsv, np.array([0, ls, lv]), np.array([uh, us, uv]))
    return cv2.bitwise_or(high, low)


class CueEdgeTracker:
    """Turns per-frame coverage readings into on/off transitions. A cue activates at its
    configured threshold but only deactivates below release_ratio * threshold, so coverage
    hovering right at the threshold doesn't strobe alerts.
    """

    def __init__(self, release_ratio: float = 0.6):
        self._release_ratio = release_ratio
        self._active: set[str] = set()

    def update(self, readings: list[CueReading]) -> list[tuple[str, bool, float]]:
        """Returns only the cues whose on/off state changed this frame."""
        changes = []
        for reading in readings:
            was_active = reading.cue_id in self._active
            if not was_active and reading.over_threshold:
                self._active.add(reading.cue_id)
                changes.append((reading.cue_id, True, reading.coverage_pct))
            elif was_active and reading.coverage_pct < self._release_ratio * reading.threshold_pct:
                self._active.discard(reading.cue_id)
                changes.append((reading.cue_id, False, reading.coverage_pct))
        return changes
