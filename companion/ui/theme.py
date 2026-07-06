"""Shared HUD/editor palette and user-customizable HUD text. Colors and labels are all
overridable from settings.yaml (overlay.theme / overlay.labels); every piece of static text
the HUD shows lives here, so users can rename or blank out ("" hides the row) any of it.
"""

from dataclasses import dataclass, fields

from companion.rules.schema import AlertLevel


@dataclass(frozen=True)
class Theme:
    # Colors
    panel_bg: str = "#15161c"
    border: str = "#2d2f3a"
    accent: str = "#7c5cff"
    text: str = "#e8e8f0"
    muted: str = "#9aa0b0"
    info: str = "#8ab4f8"
    warning: str = "#fbbc04"
    critical: str = "#f28b82"
    hp_high: str = "#6fcf97"
    hp_mid: str = "#fbbc04"
    hp_low: str = "#f28b82"
    font_family: str = "Segoe UI"
    # Labels (empty string hides the row)
    title: str = "Ultras Companion"
    # The current game ROOM (from packets; what zone_equals rules match) -- deliberately not
    # called "Zone" on screen, since AQW players read "zone" as the glowing boss mechanic.
    zone_prefix: str = "Room"
    hp_unknown: str = "?"

    @classmethod
    def from_settings(cls, overlay_cfg: dict) -> "Theme":
        overrides = {}
        merged = {**overlay_cfg.get("theme", {}), **overlay_cfg.get("labels", {})}
        known = {f.name for f in fields(cls)}
        for key, value in merged.items():
            if key in known:
                overrides[key] = str(value)
            else:
                print(f"[theme] ignoring unknown overlay theme/label key '{key}'")
        return cls(**overrides)

    def level_color(self, level: AlertLevel) -> str:
        return {
            AlertLevel.INFO: self.info,
            AlertLevel.WARNING: self.warning,
            AlertLevel.CRITICAL: self.critical,
        }[level]

    def hp_color(self, pct: float) -> str:
        if pct > 50:
            return self.hp_high
        if pct > 25:
            return self.hp_mid
        return self.hp_low
