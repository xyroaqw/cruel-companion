import sys
from pathlib import Path

from companion.app import Companion

# When frozen by PyInstaller, __file__ points inside a temp extraction dir, not next to the
# .exe -- config/rules.yaml must stay editable next to the .exe, not get baked into the bundle.
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    from companion.vision.window import ensure_dpi_aware

    ensure_dpi_aware()
    app = Companion(
        settings_path=ROOT / "config" / "settings.yaml",
        rules_path=ROOT / "config" / "rules.yaml",
        project_root=ROOT,
    )
    app.run()


if __name__ == "__main__":
    main()
