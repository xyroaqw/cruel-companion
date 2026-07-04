"""Owns the full pipeline lifecycle: capture (packets + vision) -> bridge -> overlay.
State mutation and rule evaluation happen inside the overlay's poll loop (see ui/overlay.py)
so they only ever run on the Tk main thread.
"""

import json
import sys
from pathlib import Path

import tkinter as tk
import yaml

from companion.capture.reassembler import FlowReassembler
from companion.capture.sniffer import PacketSniffer, RawSegment
from companion.identity.resolver import IdentityResolver
from companion.protocol.parser import parse_frame
from companion.rules.engine import RulesEngine
from companion.rules.packs import load_boss_packs
from companion.rules.schema import load_rules
from companion.state.game_state import GameState
from companion.ui.overlay import OverlayHUD
from companion.ui.queue_bridge import EventBridge
from companion.ui.settings_window import SettingsWindow
from companion.ui.sounds import SoundPlayer
from companion.ui.theme import Theme
from companion.vision.ocr import OcrRegion
from companion.vision.worker import VisionWorker


class Companion:
    def __init__(self, settings_path: Path, rules_path: Path, project_root: Path):
        settings = yaml.safe_load(settings_path.read_text(encoding="utf-8"))

        self._rules_path = rules_path
        self.bridge = EventBridge()
        self.reassembler = FlowReassembler()

        identity_cache = project_root / settings["identity"]["cache_path"]
        self.identity = IdentityResolver(identity_cache)
        self.state = GameState(identity=self.identity)

        bosses_dir = project_root / settings.get("bosses_dir", "config/bosses")
        self.packs = load_boss_packs(bosses_dir)
        pack_triggers = [t for pack in self.packs for t in pack.triggers]
        self.engine = RulesEngine(load_rules(rules_path), pack_triggers=pack_triggers)

        capture_cfg = settings["capture"]
        self.sniffer = PacketSniffer(
            ports=capture_cfg["ports"],
            iface=capture_cfg.get("interface"),
            on_segment=self._on_segment,
        )

        self.vision = self._build_vision_worker(settings.get("vision", {}))

        # Single shared Tk root: the overlay lives ON the root window (not a Toplevel), and
        # the settings editor opens as a Toplevel on the same root.
        self._root = tk.Tk()

        overlay_cfg = settings["overlay"]
        theme = Theme.from_settings(overlay_cfg)
        self.overlay = OverlayHUD(
            bridge=self.bridge,
            state=self.state,
            engine=self.engine,
            x=overlay_cfg["x"],
            y=overlay_cfg["y"],
            poll_ms=overlay_cfg["poll_ms"],
            max_alert_feed=overlay_cfg["max_alert_feed"],
            root=self._root,
            sound_player=SoundPlayer(enabled=settings.get("sounds", {}).get("enabled", True)),
            theme=theme,
            alert_ttl_seconds=float(overlay_cfg.get("alert_ttl_seconds", 8)),
        )

        self.settings_win = SettingsWindow(
            root=self._root,
            rules_path=rules_path,
            engine=self.engine,
            theme=theme,
        )

        _print_banner(rules_path, self.packs, vision_on=self.vision is not None)

    def _build_vision_worker(self, vision_cfg: dict) -> VisionWorker | None:
        if not vision_cfg.get("enabled", True):
            return None
        cue_profiles = [cue for pack in self.packs for cue in pack.cues]

        ocr_cfg = vision_cfg.get("ocr", {})
        ocr_regions = [
            OcrRegion(
                name=raw["name"],
                left=float(raw["left"]),
                top=float(raw["top"]),
                right=float(raw["right"]),
                bottom=float(raw["bottom"]),
            )
            for raw in ocr_cfg.get("regions", [])
        ]

        return VisionWorker(
            bridge=self.bridge,
            profiles=cue_profiles,
            title_substrings=vision_cfg.get(
                "window_title_contains", ["AdventureQuest Worlds", "Artix Game Launcher"]
            ),
            fps=float(vision_cfg.get("fps", 5)),
            ocr_enabled=ocr_cfg.get("enabled", True),
            ocr_interval_ms=int(ocr_cfg.get("interval_ms", 600)),
            ocr_regions=ocr_regions,
        )

    def _on_segment(self, seg: RawSegment) -> None:
        key = (seg.src_ip, seg.src_port, seg.dst_ip, seg.dst_port)
        for frame_text in self.reassembler.feed(key, seg.payload):
            try:
                raw = json.loads(frame_text)
            except json.JSONDecodeError:
                continue
            for event in parse_frame(raw):
                self.bridge.put(event)

    def run(self) -> None:
        # Packet capture needs admin + Npcap; the vision layer needs neither. If sniffing
        # can't start, keep going -- screen-based alerts still work.
        try:
            self.sniffer.start()
        except Exception as exc:
            print(f"  WARNING: packet capture disabled ({exc}); vision layer still active")
        if self.vision is not None:
            self.vision.start()
        self.overlay.start()
        self._root.mainloop()


def _print_banner(rules_path: Path, packs, vision_on: bool) -> None:
    print("=" * 60)
    print("  Companion — AQW passive overlay")
    print("=" * 60)
    print(f"  Python {sys.version.split()[0]}")
    print(f"  Rules:    {rules_path}")
    if packs:
        names = ", ".join(pack.name for pack in packs)
        print(f"  Bosses:   {names}")
    else:
        print("  Bosses:   none loaded (add packs under config/bosses/)")
    print(f"  Vision:   {'watching for game window' if vision_on else 'disabled in settings'}")
    print()
    print("  Overlay:  transparent HUD (top-left of screen)")
    print("  Settings: Rule Editor window just opened")
    print()
    print("  NOTE: packet parser stub is active — packet-based alerts")
    print("  need Step 0 (capture_spike.py); vision alerts work now.")
    print("=" * 60)
