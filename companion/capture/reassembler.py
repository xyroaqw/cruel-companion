"""Per-TCP-flow buffering and NUL-delimited frame extraction for AQW's SFS2X traffic."""

FlowKey = tuple[str, int, str, int]

MAX_BUFFER_BYTES = 256 * 1024


class FlowReassembler:
    def __init__(self) -> None:
        self._buffers: dict[FlowKey, bytearray] = {}

    def feed(self, key: FlowKey, payload: bytes) -> list[str]:
        """Complete frames that look like JSON objects -- what the parser consumes."""
        return [t for t in self.feed_all(key, payload) if t.startswith("{") and t.endswith("}")]

    def feed_all(self, key: FlowKey, payload: bytes) -> list[str]:
        """Every complete NUL-delimited frame, JSON or not (e.g. AQW's %xt%...% percent
        frames). The Frame Inspector uses this so nothing the client sent is hidden."""
        buf = self._buffers.setdefault(key, bytearray())
        buf.extend(payload)

        parts = bytes(buf).split(b"\x00")
        complete, remainder = parts[:-1], parts[-1]

        if len(remainder) > MAX_BUFFER_BYTES:
            self.reset_flow(key)
        else:
            self._buffers[key] = bytearray(remainder)

        frames = []
        for part in complete:
            text = part.decode("utf-8", errors="replace").strip()
            if text:
                frames.append(text)
        return frames

    def reset_flow(self, key: FlowKey) -> None:
        self._buffers.pop(key, None)
