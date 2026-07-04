"""Feeds tests/fixtures/sample_events.jsonl through the rules engine (and, by default, a live
OverlayHUD) without needing AQW running at all -- the fast iteration loop for tuning
config/rules.yaml or the HUD's look.

Usage:
    python tools/replay_canned_events.py            # drives the real overlay window
    python tools/replay_canned_events.py --no-gui    # just prints fired alerts to console
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from companion.identity.resolver import IdentityResolver  # noqa: E402
from companion.protocol.events import (  # noqa: E402
    ActorVitals,
    IdentityHintEvent,
    MessageEvent,
    NormalizedEvent,
    VisualCueEvent,
    VitalsEvent,
    ZoneChangeEvent,
)
from companion.rules.engine import RulesEngine  # noqa: E402
from companion.rules.schema import load_rules  # noqa: E402
from companion.state.game_state import GameState  # noqa: E402
from companion.ui.overlay import OverlayHUD  # noqa: E402
from companion.ui.queue_bridge import EventBridge  # noqa: E402

FIXTURES_PATH = ROOT / "tests" / "fixtures" / "sample_events.jsonl"

EVENT_BUILDERS = {
    "vitals": lambda d: VitalsEvent(
        ts=d["ts"],
        kind=d.get("kind", "combat_tick"),
        actors=[ActorVitals(**a) for a in d["actors"]],
    ),
    "message": lambda d: MessageEvent(
        ts=d["ts"], text=d["text"], caster_id=d.get("caster_id"), target_id=d.get("target_id")
    ),
    "zone_change": lambda d: ZoneChangeEvent(ts=d["ts"], zone_name=d["zone_name"]),
    "identity_hint": lambda d: IdentityHintEvent(
        ts=d["ts"], actor_id=d["actor_id"], display_name=d["display_name"]
    ),
    "visual_cue": lambda d: VisualCueEvent(
        ts=d["ts"], cue_id=d["cue_id"], active=d["active"], coverage_pct=d.get("coverage_pct", 0.0)
    ),
}


def load_fixture_events(path: Path) -> list[NormalizedEvent]:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        record = json.loads(line)
        events.append(EVENT_BUILDERS[record["type"]](record))
    return events


def run_headless(events: list[NormalizedEvent], rules_path: Path) -> None:
    identity = IdentityResolver(ROOT / "data" / "identities.json")
    state = GameState(identity=identity)
    engine = RulesEngine(load_rules(rules_path))

    for event in events:
        state.apply(event)
        for alert in engine.evaluate(state.snapshot()):
            print(f"[FIRED] {alert.level.value.upper()}: {alert.message}  (trigger={alert.trigger_id})")
    print("Done. (Use without --no-gui to see this drive the actual overlay window.)")


def run_with_overlay(events: list[NormalizedEvent], rules_path: Path, interval_s: float) -> None:
    identity = IdentityResolver(ROOT / "data" / "identities.json")
    state = GameState(identity=identity)
    engine = RulesEngine(load_rules(rules_path))
    bridge = EventBridge()

    overlay = OverlayHUD(bridge=bridge, state=state, engine=engine)
    overlay.start()

    remaining = list(events)

    def feed_next() -> None:
        if remaining:
            bridge.put(remaining.pop(0))
            overlay.root.after(int(interval_s * 1000), feed_next)
        else:
            print("Replay finished. Close the overlay window to exit.")

    overlay.root.after(int(interval_s * 1000), feed_next)
    overlay.root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-gui", action="store_true", help="skip the overlay, just print fired alerts")
    parser.add_argument("--interval", type=float, default=0.5, help="seconds between simulated events")
    parser.add_argument("--rules", type=Path, default=ROOT / "config" / "rules.yaml")
    parser.add_argument("--fixtures", type=Path, default=FIXTURES_PATH)
    args = parser.parse_args()

    events = load_fixture_events(args.fixtures)
    print(f"Loaded {len(events)} fixture events from {args.fixtures}")

    if args.no_gui:
        run_headless(events, args.rules)
    else:
        run_with_overlay(events, args.rules, args.interval)


if __name__ == "__main__":
    main()
