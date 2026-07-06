"""Calibration tool for the vision layer -- the "Step 0" for glow-zone detection, like
capture_spike.py is for packets. Run it while AQW is open (no admin needed):

    python tools/vision_probe.py                 # one snapshot: cue coverage readout
    python tools/vision_probe.py --save shot.png # also write the captured frame to disk
    python tools/vision_probe.py --watch         # live readout ~2x/sec until Ctrl+C

Use it to answer, per boss pack: is my HSV range catching the telegraph glow (coverage%
jumps when it appears), and what's the idle noise floor (set min_coverage_pct above it)?
"""

import argparse
import sys
import time
from pathlib import Path

# Frozen (PyInstaller): config/ and boss packs live next to the .exe, same as __main__.py.
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from companion.rules.packs import load_boss_packs  # noqa: E402
from companion.vision.capture import ScreenGrabber  # noqa: E402
from companion.vision.detector import ZoneDetector  # noqa: E402
from companion.vision.window import ensure_dpi_aware, find_game_window  # noqa: E402


def load_config():
    settings = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
    vision_cfg = settings.get("vision", {})
    titles = vision_cfg.get(
        "window_title_contains", ["AdventureQuest Worlds", "Artix Game Launcher"]
    )
    packs = load_boss_packs(ROOT / settings.get("bosses_dir", "config/bosses"))
    profiles = [cue for pack in packs for cue in pack.cues]
    return titles, packs, profiles


def probe_once(grabber, detector, titles, save_path=None) -> bool:
    rect = find_game_window(titles)
    if rect is None:
        print(f"Game window NOT found (looking for titles containing {titles}).")
        print("Is AQW running and not minimized?")
        return False

    frame = grabber.grab(rect)
    print(f"Window: {rect.width}x{rect.height} at ({rect.left},{rect.top})")

    if save_path:
        import cv2

        cv2.imwrite(str(save_path), frame)
        print(f"Frame saved to {save_path}")

    readings = detector.read(frame)
    if readings:
        print("Cue coverage:")
        for r in readings:
            marker = "ON " if r.over_threshold else "off"
            print(
                f"  [{marker}] {r.cue_id:<40} {r.coverage_pct:6.2f}%"
                f"  (threshold {r.threshold_pct}%)"
            )
    else:
        print("No cues configured -- add boss packs under config/bosses/")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", type=Path, help="write the captured frame to this PNG path")
    parser.add_argument("--watch", action="store_true", help="repeat ~2x/sec until Ctrl+C")
    args = parser.parse_args()

    ensure_dpi_aware()
    titles, packs, profiles = load_config()
    print(f"Loaded {len(packs)} boss pack(s): {[p.name for p in packs]}")

    detector = ZoneDetector(profiles)
    grabber = ScreenGrabber()

    try:
        if args.watch:
            while True:
                print("-" * 70)
                probe_once(grabber, detector, titles)
                time.sleep(0.5)
        else:
            probe_once(grabber, detector, titles, save_path=args.save)
    except KeyboardInterrupt:
        pass
    finally:
        grabber.close()


if __name__ == "__main__":
    main()
