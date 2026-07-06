"""Builds the public release zip: PyInstaller one-folder bundle + loose editable config/
+ QUICKSTART.txt, zipped as dist/Companion-v<version>-win64.zip.

Usage (from the project root, inside the venv):
    python tools/make_release.py            # build + assemble + zip
    python tools/make_release.py --no-zip   # stop after assembling dist/Companion/
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist" / "Companion"

QUICKSTART = """\
Companion — AQW ultra-boss overlay (passive: it watches, you play)
===================================================================

GETTING STARTED
1. Unzip this folder anywhere (keep the files together).
2. Start AQW in the Artix Games Launcher, windowed.
3. Double-click Companion.exe.
   - A transparent alert HUD appears top-left; a Rule Editor window opens too.
   - Windows SmartScreen may warn on first run (unsigned app): More info -> Run anyway.

ALERT SOURCES
- Packets (main source — boss text, HP%, room changes): install Npcap
  (https://npcap.com, check "WinPcap API-compatible mode") and run Companion.exe
  as Administrator. Reads only your own AQW traffic.
- Vision (works without any setup): watches the game window for glowing telegraph
  zones, per the boss packs in config\\bosses\\.

CUSTOMIZING / ADDING BOSSES
- Each boss is one file in config\\bosses\\. Copy _TEMPLATE.yaml, follow the
  comments, restart Companion.
- Glow colors vary by screen setup: run VisionProbe.exe while in the fight to tune
  a pack ("VisionProbe.exe --watch" shows live per-cue readings; "--save shot.png"
  saves a screenshot to color-pick from).
- General rules (any boss) live in config\\rules.yaml, editable in-app via the
  Rule Editor window.

WHAT THIS TOOL NEVER DOES
- No key presses, no mouse movement, no packet injection, no automation.
  It only observes and displays suggestions - like WeakAuras/DBM for WoW.

Troubleshooting: keep the game window unminimized; if the HUD shows nothing,
check the console window Companion opened for status messages.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-zip", action="store_true", help="skip the final zip step")
    args = parser.parse_args()

    version = _read_version()
    print(f"Building Companion v{version}")

    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "Companion.spec", "--noconfirm"],
        cwd=ROOT,
        check=True,
    )

    print("Adding editable config/ and QUICKSTART.txt")
    config_dst = DIST / "config"
    if config_dst.exists():
        shutil.rmtree(config_dst)
    shutil.copytree(ROOT / "config", config_dst)
    (DIST / "QUICKSTART.txt").write_text(QUICKSTART, encoding="utf-8")

    if args.no_zip:
        print(f"Done (unzipped): {DIST}")
        return

    zip_base = ROOT / "dist" / f"Companion-v{version}-win64"
    zip_path = shutil.make_archive(str(zip_base), "zip", root_dir=DIST.parent, base_dir="Companion")
    size_mb = Path(zip_path).stat().st_size / (1024 * 1024)
    print(f"Done: {zip_path} ({size_mb:.0f} MB)")


def _read_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else "0.0.0"


if __name__ == "__main__":
    main()
