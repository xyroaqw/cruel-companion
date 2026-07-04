"""Calibration tool for the vision layer -- the "Step 0" for screen detection, like
capture_spike.py is for packets. Run it while AQW is open (no admin needed):

    python tools/vision_probe.py                 # one snapshot: cue coverage + OCR text
    python tools/vision_probe.py --save shot.png # also write the captured frame to disk
    python tools/vision_probe.py --watch         # live readout ~2x/sec until Ctrl+C

Use it to answer, per boss pack: is my HSV range catching the telegraph glow (coverage%
jumps when it appears), what's the idle noise floor (set min_coverage_pct above it), and
does OCR actually read the warning banner text?
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
from companion.vision.ocr import OcrRegion, create_ocr_engine  # noqa: E402
from companion.vision.window import ensure_dpi_aware, find_game_window  # noqa: E402


def load_config():
    settings = yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
    vision_cfg = settings.get("vision", {})
    titles = vision_cfg.get(
        "window_title_contains", ["AdventureQuest Worlds", "Artix Game Launcher"]
    )
    regions = [
        OcrRegion(
            name=raw["name"],
            left=float(raw["left"]),
            top=float(raw["top"]),
            right=float(raw["right"]),
            bottom=float(raw["bottom"]),
        )
        for raw in vision_cfg.get("ocr", {}).get("regions", [])
    ]
    packs = load_boss_packs(ROOT / settings.get("bosses_dir", "config/bosses"))
    profiles = [cue for pack in packs for cue in pack.cues]
    return titles, regions, packs, profiles


def probe_once(grabber, detector, ocr, regions, titles, save_path=None) -> bool:
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

    if ocr is not None and regions:
        height, width = frame.shape[:2]
        for region in regions:
            crop = frame[
                int(region.top * height) : int(region.bottom * height),
                int(region.left * width) : int(region.right * width),
            ]
            text = ocr.read_text(crop) if crop.size else ""
            print(f"OCR [{region.name}]: {text!r}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", type=Path, help="write the captured frame to this PNG path")
    parser.add_argument("--watch", action="store_true", help="repeat ~2x/sec until Ctrl+C")
    parser.add_argument("--no-ocr", action="store_true", help="skip OCR (faster)")
    args = parser.parse_args()

    ensure_dpi_aware()
    titles, regions, packs, profiles = load_config()
    print(f"Loaded {len(packs)} boss pack(s): {[p.name for p in packs]}")

    detector = ZoneDetector(profiles)
    ocr = None if args.no_ocr else create_ocr_engine()
    if not args.no_ocr and ocr is None:
        print("OCR unavailable (rapidocr-onnxruntime not installed); zone readout only.")
    grabber = ScreenGrabber()

    try:
        if args.watch:
            while True:
                print("-" * 70)
                probe_once(grabber, detector, ocr, regions, titles)
                time.sleep(0.5)
        else:
            probe_once(grabber, detector, ocr, regions, titles, save_path=args.save)
    except KeyboardInterrupt:
        pass
    finally:
        grabber.close()


if __name__ == "__main__":
    main()
