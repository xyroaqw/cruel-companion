from companion.capture.frame_tap import FrameTap
from companion.ui.inspector import _is_vitals_noise, _summarize


def test_tap_records_and_drains_in_order():
    tap = FrameTap()
    tap.record("inbound", '{"a":1}')
    tap.record("outbound", "%xt%zm%")
    drained = tap.drain()
    assert [d[1] for d in drained] == ["inbound", "outbound"]
    assert [d[2] for d in drained] == ['{"a":1}', "%xt%zm%"]
    assert tap.drain() == []  # queue emptied


def test_tap_bounded_drops_oldest_when_full():
    tap = FrameTap(maxsize=3)
    for i in range(5):
        tap.record("inbound", str(i))
    kept = [d[2] for d in tap.drain()]
    assert len(kept) == 3
    assert "4" in kept and "0" not in kept  # newest survived, oldest dropped


def test_vitals_noise_detection():
    assert _is_vitals_noise('{"t":"xt","b":{"o":{"cmd":"ct","m":{"3":{"intHP":10}}}}}')
    # A ct frame carrying an aura is NOT noise -- that's the interesting case.
    assert not _is_vitals_noise('{"b":{"o":{"cmd":"ct","a":[{"cmd":"aura+"}]}}}')
    assert not _is_vitals_noise('{"b":{"o":{"cmd":"moveToArea"}}}')


def test_summarize_extracts_cmd_and_auras():
    assert "moveToArea" in _summarize('{"t":"xt","b":{"o":{"cmd":"moveToArea"}}}')
    s = _summarize('{"b":{"o":{"cmd":"ct","a":[{"cmd":"aura+","auras":[{"nam":"Empowered"}]}]}}}')
    assert "ct" in s and "Empowered" in s


def test_summarize_handles_percent_and_garbage():
    assert _summarize("%xt%zm%gar%1%").startswith("pkt %")
    assert _summarize("not json at all")  # does not raise
