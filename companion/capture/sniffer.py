"""scapy-based packet capture. The BPF filter is built only from the configured game ports
(see bpf_filter) -- this is the single enforcement point for "never capture the whole NIC's
traffic", so it should remain the only call site that invokes scapy.sniff().
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass

from scapy.all import IP, TCP, sniff


@dataclass(frozen=True)
class RawSegment:
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    payload: bytes
    direction: str  # "inbound" | "outbound", relative to the configured game ports


class PacketSniffer:
    def __init__(
        self,
        ports: list[int],
        on_segment: Callable[[RawSegment], None],
        iface: str | None = None,
    ):
        self._ports = ports
        self._on_segment = on_segment
        self._iface = iface
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def bpf_filter(self) -> str:
        port_clause = " or ".join(f"port {p}" for p in self._ports)
        return f"tcp and ({port_clause})"

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _run(self) -> None:
        try:
            sniff(
                iface=self._iface,
                filter=self.bpf_filter(),
                prn=self._handle,
                stop_filter=lambda _pkt: self._stop_event.is_set(),
                store=False,
            )
        except Exception as exc:
            # Most commonly: not running as Administrator, or Npcap missing. The vision
            # layer doesn't need either, so the app keeps running without packet alerts.
            print(
                f"[capture] packet capture unavailable ({exc}). "
                "Run from an Administrator terminal with Npcap installed to enable it; "
                "vision-based alerts continue to work."
            )

    def _handle(self, pkt) -> None:
        if not (pkt.haslayer(IP) and pkt.haslayer(TCP)):
            return
        tcp = pkt[TCP]
        payload = bytes(tcp.payload)
        if not payload:
            return

        direction = "outbound" if tcp.dport in self._ports else "inbound"
        self._on_segment(
            RawSegment(
                src_ip=pkt[IP].src,
                src_port=tcp.sport,
                dst_ip=pkt[IP].dst,
                dst_port=tcp.dport,
                payload=payload,
                direction=direction,
            )
        )
