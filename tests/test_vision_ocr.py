from companion.vision.ocr import TextDeduper


def test_first_text_passes_through():
    assert TextDeduper().offer("banner", "Counter Attack!") == "Counter Attack!"


def test_repeat_of_same_text_is_suppressed():
    dedupe = TextDeduper()
    dedupe.offer("banner", "Counter Attack!")
    assert dedupe.offer("banner", "Counter Attack!") is None
    # Whitespace jitter between OCR passes doesn't count as new text.
    assert dedupe.offer("banner", "  Counter   Attack! ") is None


def test_text_can_reappear_after_clearing():
    dedupe = TextDeduper()
    dedupe.offer("banner", "Counter Attack!")
    dedupe.offer("banner", "")  # banner disappeared
    assert dedupe.offer("banner", "Counter Attack!") == "Counter Attack!"


def test_short_noise_is_treated_as_blank():
    dedupe = TextDeduper(min_len=4)
    assert dedupe.offer("banner", "xy") is None
    # ...and doesn't overwrite the remembered text with garbage in between.
    dedupe.offer("banner", "Counter Attack!")
    assert dedupe.offer("banner", "zq") is None       # noise -> treated as blank (a change)
    assert dedupe.offer("banner", "Counter Attack!") == "Counter Attack!"


def test_regions_are_tracked_independently():
    dedupe = TextDeduper()
    assert dedupe.offer("top", "Focus!") == "Focus!"
    assert dedupe.offer("bottom", "Focus!") == "Focus!"
