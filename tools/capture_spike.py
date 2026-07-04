"""Step 0: live-capture verification spike.

Run this from an Administrator terminal while actually playing AQW, to confirm: which
port(s) currently carry traffic, that NUL-delimited JSON framing holds, real field names for
player/monster vitals, the monster max-HP source packet (the most important open question --
see README.md), the message/telegraph field, the zone-change shape, and identity-hint packets.

Deliberately standalone: does NOT import the companion package, so it stays disposable and
dependency-free (only scapy) and can never accidentally couple the real pipeline to guesses
made before the protocol is confirmed. Prints to console only -- never writes to disk.
"""

import json
import sys
from datetime import datetime

from scapy.all import IP, TCP, sniff

CANDIDATE_PORTS = [5588, 5594]

_buffers: dict[tuple, bytearray] = {}


def bpf_filter() -> str:
    port_clause = " or ".join(f"port {p}" for p in CANDIDATE_PORTS)
    return f"tcp and ({port_clause})"


def timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def handle_packet(pkt) -> None:
    if not (pkt.haslayer(IP) and pkt.haslayer(TCP)):
        return
    tcp = pkt[TCP]
    payload = bytes(tcp.payload)
    if not payload:
        return

    key = (pkt[IP].src, tcp.sport, pkt[IP].dst, tcp.dport)
    buf = _buffers.setdefault(key, bytearray())
    buf.extend(payload)

    parts = bytes(buf).split(b"\x00")
    complete, remainder = parts[:-1], parts[-1]
    _buffers[key] = bytearray(remainder)

    for part in complete:
        text = part.decode("utf-8", errors="replace").strip()
        if not (text.startswith("{") and text.endswith("}")):
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            print(f"[{timestamp()}] {key} -- non-JSON frame after NUL-split: {text[:200]!r}")
            continue
        print(f"[{timestamp()}] {key}")
        print(json.dumps(obj, indent=2))
        print("-" * 60)


def main() -> None:
    print(f"Listening on BPF filter: {bpf_filter()!r}")
    print("Play AQW now: enter a room with a monster, fight until a mechanic telegraphs,")
    print("then change zones once. Press Ctrl+C to stop.\n")
    try:
        sniff(filter=bpf_filter(), prn=handle_packet, store=False)
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
