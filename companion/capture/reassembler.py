"""Per-TCP-flow buffering and NUL-delimited frame extraction for AQW's SFS2X traffic."""

FlowKey = tuple[str, int, str, int]

MAX_BUFFER_BYTES = 256 * 1024


class FlowReassembler:
    def __init__(self) -> None:
        self._buffers: dict[FlowKey, bytearray] = {}

    def feed(self, key: FlowKey, payload: bytes) -> list[str]:
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
            if text.startswith("{") and text.endswith("}"):
                frames.append(text)
        return frames

    def reset_flow(self, key: FlowKey) -> None:
        self._buffers.pop(key, None)
