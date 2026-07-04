"""OCR of on-screen text regions (boss warnings, "Focus!" banners, countdowns).

Backend is RapidOCR (pip-installable ONNX models, no external Tesseract install). It is
imported lazily and treated as optional: if unavailable, create_ocr_engine() returns None and
the vision worker runs zone detection only.
"""

from dataclasses import dataclass

import numpy as np

MIN_CONFIDENCE = 0.5


@dataclass(frozen=True)
class OcrRegion:
    name: str
    # Fractions of the game window, same convention as CueProfile.region.
    left: float
    top: float
    right: float
    bottom: float


class RapidOcrEngine:
    def __init__(self, rapid_ocr) -> None:
        self._ocr = rapid_ocr

    def read_text(self, img_bgr: np.ndarray) -> str:
        result, _elapse = self._ocr(img_bgr)
        if not result:
            return ""
        return " ".join(text for _box, text, score in result if float(score) >= MIN_CONFIDENCE)


def create_ocr_engine():
    """Returns an engine with a read_text(img_bgr) -> str method, or None if the optional
    OCR dependency isn't installed."""
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return None
    return RapidOcrEngine(RapidOCR())


class TextDeduper:
    """The same banner text sits on screen for many frames; rules only care that it appeared.
    Tracks the last text emitted per region and passes through only changes. Very short
    fragments are treated as blank -- OCR noise on particle effects loves 1-2 char garbage.
    """

    def __init__(self, min_len: int = 4):
        self._min_len = min_len
        self._last: dict[str, str] = {}

    def offer(self, region_name: str, text: str) -> str | None:
        normalized = " ".join(text.split())
        if len(normalized) < self._min_len:
            normalized = ""
        if normalized == self._last.get(region_name, ""):
            return None
        self._last[region_name] = normalized
        return normalized or None
