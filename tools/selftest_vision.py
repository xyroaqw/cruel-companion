"""End-to-end vision self-test -- no AQW (and no boss) needed.

Spawns a fake "game window" (a Tk window showing a red telegraph patch), points the REAL
pipeline at it -- window finding, screen capture, HSV zone detection, game state, rules
engine -- and reports whether the glow alert fired.

    python tools/selftest_vision.py

Expected result: PASS within ~15 seconds. A window will briefly appear on screen; that's
the fake game window being captured.
"""

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

WINDOW_TITLE = "Companion Vision Selftest"
TIMEOUT_S = 20.0


def run_banner(duration_s: float) -> None:
    """The fake game window: dark arena with a red telegraph patch."""
    import tkinter as tk

    root = tk.Tk()
    root.title(WINDOW_TITLE)
    root.geometry("800x400+120+120")
    root.attributes("-topmost", True)  # must stay visible: mss captures the screen region
    canvas = tk.Canvas(root, width=800, height=400, bg="#101018", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    canvas.create_rectangle(60, 160, 300, 380, fill="#e60000", outline="")
    root.after(int(duration_s * 1000), root.destroy)
    root.mainloop()


def main() -> int:
    from companion.identity.resolver import IdentityResolver
    from companion.rules.engine import RulesEngine
    from companion.rules.schema import Action, AlertLevel, Condition, Trigger
    from companion.state.game_state import GameState
    from companion.ui.queue_bridge import EventBridge
    from companion.vision.cues import CueProfile
    from companion.vision.window import ensure_dpi_aware
    from companion.vision.worker import VisionWorker

    ensure_dpi_aware()

    banner = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--banner"])
    print(f"Spawned fake game window ('{WINDOW_TITLE}')")

    bridge = EventBridge()
    state = GameState(
        identity=IdentityResolver(Path(tempfile.mkdtemp()) / "identities.json")
    )
    engine = RulesEngine(
        [
            Trigger(
                id="selftest:red_patch_seen",
                when=Condition(visual_cue="selftest:red_patch"),
                then=Action(alert="zone detection works", level=AlertLevel.CRITICAL),
                fire_once_per_threshold_crossing=True,
            )
        ]
    )
    worker = VisionWorker(
        bridge=bridge,
        profiles=[
            CueProfile(
                id="selftest:red_patch",
                hsv_lower=(170, 120, 120),
                hsv_upper=(10, 255, 255),
                min_coverage_pct=3.0,
            )
        ],
        title_substrings=[WINDOW_TITLE],
        fps=5,
    )
    worker.start()

    fired = False
    deadline = time.monotonic() + TIMEOUT_S
    try:
        while time.monotonic() < deadline and not fired:
            for event in bridge.drain():
                print(f"  event: {event}")
                state.apply(event)
            for alert in engine.evaluate(state.snapshot()):
                fired = True
                print(f"  FIRED [{alert.level.value}] {alert.message}")
            time.sleep(0.2)
    finally:
        worker.stop()
        banner.terminate()

    print()
    print(f"  {'PASS' if fired else 'FAIL'}  zone detection (red telegraph patch)")
    print()
    print("Self-test PASSED" if fired else "Self-test FAILED")
    return 0 if fired else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--banner", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--banner-duration", type=float, default=TIMEOUT_S + 10)
    args = parser.parse_args()

    if args.banner:
        run_banner(args.banner_duration)
        sys.exit(0)
    sys.exit(main())
