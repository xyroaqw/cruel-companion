"""Cue-profile config types. Deliberately free of cv2/numpy imports so the rules layer
(companion/rules/packs.py) can load boss packs without pulling in the vision stack.

HSV values use OpenCV conventions: H in [0, 179], S and V in [0, 255]. A profile whose
hsv_lower hue is GREATER than its hsv_upper hue means "wrap around the red end of the hue
circle" (e.g. lower h=170, upper h=10 matches both magenta-reds and orange-reds).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CueProfile:
    id: str
    hsv_lower: tuple[int, int, int]
    hsv_upper: tuple[int, int, int]
    # Percentage of the watched region that must match before the cue counts as "on".
    min_coverage_pct: float = 1.0
    # (left, top, right, bottom) as fractions of the game window, so profiles keep working
    # when the player resizes the client.
    region: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)

    def __post_init__(self) -> None:
        for name, (h, s, v) in (("hsv_lower", self.hsv_lower), ("hsv_upper", self.hsv_upper)):
            if not (0 <= h <= 179 and 0 <= s <= 255 and 0 <= v <= 255):
                raise ValueError(
                    f"cue '{self.id}': {name} out of range (H 0-179, S/V 0-255): {(h, s, v)}"
                )
        left, top, right, bottom = self.region
        if not (0.0 <= left < right <= 1.0 and 0.0 <= top < bottom <= 1.0):
            raise ValueError(
                f"cue '{self.id}': region must be fractions with left<right and top<bottom, "
                f"got {self.region}"
            )
        if self.min_coverage_pct <= 0:
            raise ValueError(f"cue '{self.id}': min_coverage_pct must be > 0")
