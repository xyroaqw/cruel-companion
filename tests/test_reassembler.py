from companion.capture.reassembler import MAX_BUFFER_BYTES, FlowReassembler

KEY = ("1.2.3.4", 1234, "5.6.7.8", 5588)
OTHER_KEY = ("9.9.9.9", 9999, "5.6.7.8", 5588)


def test_single_complete_frame():
    r = FlowReassembler()
    frames = r.feed(KEY, b'{"a":1}\x00')
    assert frames == ['{"a":1}']


def test_frame_split_across_two_feeds():
    r = FlowReassembler()
    assert r.feed(KEY, b'{"a":1') == []
    assert r.feed(KEY, b'}\x00') == ['{"a":1}']


def test_multiple_frames_in_one_feed():
    r = FlowReassembler()
    frames = r.feed(KEY, b'{"a":1}\x00{"b":2}\x00')
    assert frames == ['{"a":1}', '{"b":2}']


def test_non_json_chunk_is_dropped():
    r = FlowReassembler()
    frames = r.feed(KEY, b'garbage\x00{"a":1}\x00')
    assert frames == ['{"a":1}']


def test_buffer_cap_resets_flow():
    r = FlowReassembler()
    r.feed(KEY, b"x" * (MAX_BUFFER_BYTES + 1))
    assert KEY not in r._buffers
    assert r.feed(KEY, b'{"a":1}\x00') == ['{"a":1}']


def test_flows_are_independent():
    r = FlowReassembler()
    assert r.feed(KEY, b'{"a":1') == []
    assert r.feed(OTHER_KEY, b'{"b":2}\x00') == ['{"b":2}']
    assert r.feed(KEY, b'}\x00') == ['{"a":1}']


def test_reset_flow_drops_buffer():
    r = FlowReassembler()
    r.feed(KEY, b'{"a":1')
    r.reset_flow(KEY)
    assert r.feed(KEY, b'}\x00') == []


def test_feed_all_keeps_non_json_frames():
    r = FlowReassembler()
    frames = r.feed_all(KEY, b'%xt%zm%gar%1%2%\x00{"a":1}\x00')
    assert frames == ["%xt%zm%gar%1%2%", '{"a":1}']


def test_feed_all_and_feed_agree_on_json():
    r1, r2 = FlowReassembler(), FlowReassembler()
    payload = b'garbage\x00{"a":1}\x00'
    assert r1.feed(KEY, payload) == ['{"a":1}']
    assert r2.feed_all(KEY, payload) == ["garbage", '{"a":1}']
