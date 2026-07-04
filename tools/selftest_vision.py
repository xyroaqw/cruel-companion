"""End-to-end vision self-test -- no AQW (and no boss) needed.

Spawns a fake "game window" (a Tk window showing a red telegraph patch and a warning banner
text), points the REAL pipeline at it -- window finding, screen capture, HSV zone detection,
OCR, game state, rules engine -- and reports which alerts fired.

    python tools/selftest_vision.py

Expected result: both checks PASS within ~20 seconds. A window will briefly appear on
screen; that's the fake game window being captured.
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
BANNER_TEXT = "COUNTER ATTACK INCOMING"
TIMEOUT_S = 25.0


def run_banner(duration_s: float) -> None:
    """The fake game window: dark arena, red telegraph patch, warning text."""
    import tkinter as tk

    root = tk.Tk()
    root.title(WINDOW_TITLE)
    root.geometry("800x400+120+120")
    root.attributes("-topmost", True)  # must stay visible: mss captures the screen region
    canvas = tk.Canvas(root, width=800, height=400, bg="#101018", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    canvas.create_rectangle(60, 160, 300, 380, fill="#e60000", outline="")
    canvas.create_text(
        400, 70, text=BANNER_TEXT, fill="white", font=("Segoe UI", 30, "bold")
    )
    root.after(int(duration_s * 1000), root.destroy)
    root.mainloop()


def main() -> int:
    from companion.identity.resolver import IdentityResolver
    from companion.rules.engine import RulesEngine
    from companion.rules.schema import Action, AlertLevel, Condition, Trigger
    from companion.state.game_state import GameState
    from companion.ui.queue_bridge import EventBridge
    from companion.vision.cues import CueProfile
    from companion.vision.ocr import OcrRegion
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
            ),
            Trigger(
                id="selftest:banner_text_read",
                when=Condition(message_contains="counter attack"),
                then=Action(alert="OCR text detection works", level=AlertLevel.WARNING),
                cooldown_seconds=9999,
            ),
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
        ocr_enabled=True,
        ocr_interval_ms=500,
        ocr_regions=[OcrRegion(name="full", left=0.0, top=0.0, right=1.0, bottom=1.0)],
    )
    worker.start()

    fired: set[str] = set()
    deadline = time.monotonic() + TIMEOUT_S
    try:
        while time.monotonic() < deadline and len(fired) < 2:
            for event in bridge.drain():
                print(f"  event: {event}")
                state.apply(event)
            for alert in engine.evaluate(state.snapshot()):
                fired.add(alert.trigger_id)
                print(f"  FIRED [{alert.level.value}] {alert.message}")
            time.sleep(0.2)
    finally:
        worker.stop()
        banner.terminate()

    print()
    checks = [
        ("zone detection (red telegraph patch)", "selftest:red_patch_seen"),
        ("OCR text (warning banner)", "selftest:banner_text_read"),
    ]
    all_ok = True
    for label, trigger_id in checks:
        ok = trigger_id in fired
        all_ok &= ok
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    print()
    print("Self-test PASSED" if all_ok else "Self-test FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--banner", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--banner-duration", type=float, default=TIMEOUT_S + 10)
    args = parser.parse_args()

    if args.banner:
        run_banner(args.banner_duration)
        sys.exit(0)
    sys.exit(main())
