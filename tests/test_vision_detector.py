"""ZoneDetector + CueEdgeTracker against synthetic frames -- no screen capture involved."""

import numpy as np

from companion.vision.cues import CueProfile
from companion.vision.detector import CueEdgeTracker, ZoneDetector


def solid_bgr(width: int, height: int, bgr: tuple[int, int, int]) -> np.ndarray:
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :] = bgr
    return frame


GREEN_CUE = CueProfile(
    id="t:green", hsv_lower=(50, 100, 100), hsv_upper=(70, 255, 255), min_coverage_pct=5.0
)
# Wraparound red range: hue 170..179 plus 0..10.
RED_CUE = CueProfile(
    id="t:red", hsv_lower=(170, 100, 100), hsv_upper=(10, 255, 255), min_coverage_pct=5.0
)


def test_coverage_matches_painted_fraction():
    frame = solid_bgr(100, 100, (0, 0, 0))
    frame[0:20, :] = (0, 255, 0)  # pure green rows: 20% of the frame

    (reading,) = ZoneDetector([GREEN_CUE]).read(frame)
    assert abs(reading.coverage_pct - 20.0) < 1.0
    assert reading.over_threshold


def test_black_frame_matches_nothing():
    (reading,) = ZoneDetector([GREEN_CUE]).read(solid_bgr(50, 50, (0, 0, 0)))
    assert reading.coverage_pct == 0.0
    assert not reading.over_threshold


def test_red_wraparound_catches_both_sides_of_hue_zero():
    pure_red = solid_bgr(20, 20, (0, 0, 255))       # hue 0
    magenta_red = solid_bgr(20, 20, (60, 0, 255))   # hue slightly below 180

    detector = ZoneDetector([RED_CUE])
    assert detector.read(pure_red)[0].coverage_pct > 90.0
    assert detector.read(magenta_red)[0].coverage_pct > 90.0


def test_green_not_caught_by_red_cue():
    (reading,) = ZoneDetector([RED_CUE]).read(solid_bgr(20, 20, (0, 255, 0)))
    assert reading.coverage_pct == 0.0


def test_region_limits_detection_area():
    top_half_cue = CueProfile(
        id="t:top",
        hsv_lower=(50, 100, 100),
        hsv_upper=(70, 255, 255),
        min_coverage_pct=5.0,
        region=(0.0, 0.0, 1.0, 0.5),
    )
    frame = solid_bgr(100, 100, (0, 0, 0))
    frame[50:, :] = (0, 255, 0)  # green only in the BOTTOM half

    (reading,) = ZoneDetector([top_half_cue]).read(frame)
    assert reading.coverage_pct == 0.0


def make_reading(coverage: float):
    frame = solid_bgr(100, 100, (0, 0, 0))
    rows = int(coverage)
    if rows:
        frame[0:rows, :] = (0, 255, 0)
    return ZoneDetector([GREEN_CUE]).read(frame)


def test_edge_tracker_reports_only_transitions():
    tracker = CueEdgeTracker()

    assert tracker.update(make_reading(0)) == []

    changes = tracker.update(make_reading(20))
    assert len(changes) == 1
    cue_id, active, coverage = changes[0]
    assert (cue_id, active) == ("t:green", True)
    assert coverage > 5.0

    # Still on: no new events while the glow persists.
    assert tracker.update(make_reading(20)) == []

    changes = tracker.update(make_reading(0))
    assert [(c[0], c[1]) for c in changes] == [("t:green", False)]


def test_edge_tracker_hysteresis_holds_near_threshold():
    tracker = CueEdgeTracker(release_ratio=0.6)
    tracker.update(make_reading(20))  # ON (threshold 5%)

    # Dipping to 4% is below threshold but above the 3% release point: stays on, no event.
    assert tracker.update(make_reading(4)) == []
    # 2% is below the release point: turns off.
    changes = tracker.update(make_reading(2))
    assert [(c[0], c[1]) for c in changes] == [("t:green", False)]
