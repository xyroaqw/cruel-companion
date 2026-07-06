import sys
from pathlib import Path

from companion.app import Companion

# When frozen by PyInstaller, __file__ points inside a temp extraction dir, not next to the
# .exe -- config/rules.yaml must stay editable next to the .exe, not get baked into the bundle.
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent


def _make_console_utf8_safe() -> None:
    # Alert text is user-authored and the HUD renders full Unicode, but the Windows console
    # defaults to cp1252 -- printing an em-dash or non-Latin1 glyph there would raise
    # UnicodeEncodeError. Reconfigure stdio to UTF-8 and never let output encoding crash.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def main() -> None:
    from companion.vision.window import ensure_dpi_aware

    _make_console_utf8_safe()
    ensure_dpi_aware()
    app = Companion(
        settings_path=ROOT / "config" / "settings.yaml",
        rules_path=ROOT / "config" / "rules.yaml",
        project_root=ROOT,
    )
    app.run()


if __name__ == "__main__":
    main()
