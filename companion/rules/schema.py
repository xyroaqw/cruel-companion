"""Trigger/Condition/Action schema and the config/rules.yaml loader."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import yaml


class AlertLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Condition:
    zone_equals: str | None = None
    boss_name: str | None = None
    hp_pct_below: float | None = None
    # A single fragment, or a tuple of fragments meaning "any of these matches" (YAML: either
    # a plain string or a list of strings).
    message_contains: str | tuple[str, ...] | None = None
    # Matches while a vision-layer color cue is active (see companion/vision). In boss packs,
    # bare cue names are namespaced to "<pack>:<cue>" at load time.
    visual_cue: str | None = None


@dataclass(frozen=True)
class Action:
    alert: str
    level: AlertLevel = AlertLevel.INFO


@dataclass(frozen=True)
class Trigger:
    id: str
    when: Condition
    then: Action
    cooldown_seconds: float = 0.0
    fire_once_per_threshold_crossing: bool = False
    # Timer mode (for rotational reminders like "taunt every N seconds"): once `when` first
    # becomes true (e.g. boss present = fight start), fire after initial_delay_seconds, then
    # repeat every repeat_every_seconds while `when` stays true. Leaving/ending the fight
    # resets the timer so the next pull starts fresh. A trigger is a timer if either is > 0.
    initial_delay_seconds: float = 0.0
    repeat_every_seconds: float = 0.0

    @property
    def is_timer(self) -> bool:
        return self.initial_delay_seconds > 0 or self.repeat_every_seconds > 0


VALID_RULE_KEYS = {
    "id", "when", "then", "cooldown_seconds", "fire_once_per_threshold_crossing",
    "initial_delay_seconds", "repeat_every_seconds",
}
VALID_WHEN_KEYS = {"zone_equals", "boss_name", "hp_pct_below", "message_contains", "visual_cue"}
VALID_THEN_KEYS = {"alert", "level"}


def _require_str(value, field: str, where: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError(f"{where}: '{field}' must be a single text string, got {type(value).__name__}")


def _parse_message_contains(value, where: str) -> str | tuple[str, ...] | None:
    """Accepts a string OR a list of strings ("any of these matches")."""
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, list):
        if not value or not all(isinstance(item, str) for item in value):
            raise ValueError(
                f"{where}: 'message_contains' list must contain only text strings"
            )
        return tuple(value)
    raise ValueError(
        f"{where}: 'message_contains' must be a text string or a list of strings, "
        f"got {type(value).__name__}"
    )


def parse_rule_dict(raw: dict, context: str) -> Trigger:
    """Parses one raw rule mapping into a Trigger, validating types and rejecting unknown
    keys so a typo produces a named error instead of a silently dead (or crashing) rule.
    Shared by load_rules (config/rules.yaml) and the boss-pack loader
    (companion/rules/packs.py). context names the source for error messages.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"{context}: each rule must be a mapping, got {type(raw).__name__}")

    rule_id = raw.get("id")
    if not rule_id:
        raise ValueError(f"{context} is missing required field 'id'")
    where = f"rule '{rule_id}' ({context})"

    unknown = set(raw) - VALID_RULE_KEYS
    if unknown:
        raise ValueError(f"{where}: unknown field(s) {sorted(unknown)}; valid: {sorted(VALID_RULE_KEYS)}")

    when_raw = raw.get("when")
    if when_raw is None:
        raise ValueError(f"{where} is missing required field 'when'")
    if not isinstance(when_raw, dict) or not when_raw:
        raise ValueError(f"{where}: 'when' must be a mapping of condition fields")
    unknown = set(when_raw) - VALID_WHEN_KEYS
    if unknown:
        raise ValueError(
            f"{where}: unknown condition(s) {sorted(unknown)}; valid: {sorted(VALID_WHEN_KEYS)}"
        )

    then_raw = raw.get("then")
    if not isinstance(then_raw, dict) or not then_raw.get("alert"):
        raise ValueError(f"{where} is missing required field 'then.alert'")
    unknown = set(then_raw) - VALID_THEN_KEYS
    if unknown:
        raise ValueError(f"{where}: unknown 'then' field(s) {sorted(unknown)}; valid: {sorted(VALID_THEN_KEYS)}")

    hp_raw = when_raw.get("hp_pct_below")
    hp_pct_below = None
    if hp_raw is not None:
        try:
            hp_pct_below = float(hp_raw)
        except (TypeError, ValueError):
            raise ValueError(f"{where}: 'hp_pct_below' must be a number, got {hp_raw!r}") from None

    condition = Condition(
        zone_equals=_require_str(when_raw.get("zone_equals"), "zone_equals", where),
        boss_name=_require_str(when_raw.get("boss_name"), "boss_name", where),
        hp_pct_below=hp_pct_below,
        message_contains=_parse_message_contains(when_raw.get("message_contains"), where),
        visual_cue=_require_str(when_raw.get("visual_cue"), "visual_cue", where),
    )

    try:
        level = AlertLevel(then_raw.get("level", "info"))
    except ValueError as exc:
        valid = ", ".join(level.value for level in AlertLevel)
        raise ValueError(f"{where} has invalid 'then.level' (must be one of: {valid})") from exc

    def _num(field: str) -> float:
        try:
            return float(raw.get(field, 0.0))
        except (TypeError, ValueError):
            raise ValueError(f"{where}: '{field}' must be a number, got {raw.get(field)!r}") from None

    return Trigger(
        id=rule_id,
        when=condition,
        then=Action(alert=then_raw["alert"], level=level),
        cooldown_seconds=_num("cooldown_seconds"),
        fire_once_per_threshold_crossing=bool(
            raw.get("fire_once_per_threshold_crossing", False)
        ),
        initial_delay_seconds=_num("initial_delay_seconds"),
        repeat_every_seconds=_num("repeat_every_seconds"),
    )


def load_rules(path: Path) -> list[Trigger]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    triggers: list[Trigger] = []
    seen_ids: set[str] = set()

    for i, raw in enumerate(data.get("rules", [])):
        trigger = parse_rule_dict(raw, context=f"rules.yaml entry #{i}")
        if trigger.id in seen_ids:
            raise ValueError(f"rules.yaml has duplicate rule id '{trigger.id}'")
        seen_ids.add(trigger.id)
        triggers.append(trigger)

    return triggers


def save_rules(triggers: list[Trigger], path: Path) -> None:
    """Inverse of load_rules -- used by the Settings window. Rewrites the whole file, so any
    hand-written comments/formatting beyond the header below don't survive a GUI-driven save.
    """
    rules = []
    for t in triggers:
        when = {}
        if t.when.zone_equals is not None:
            when["zone_equals"] = t.when.zone_equals
        if t.when.boss_name is not None:
            when["boss_name"] = t.when.boss_name
        if t.when.hp_pct_below is not None:
            when["hp_pct_below"] = t.when.hp_pct_below
        if t.when.message_contains is not None:
            mc = t.when.message_contains
            when["message_contains"] = list(mc) if isinstance(mc, tuple) else mc
        if t.when.visual_cue is not None:
            when["visual_cue"] = t.when.visual_cue

        rule = {
            "id": t.id,
            "when": when,
            "then": {"alert": t.then.alert, "level": t.then.level.value},
        }
        if t.cooldown_seconds:
            rule["cooldown_seconds"] = t.cooldown_seconds
        if t.fire_once_per_threshold_crossing:
            rule["fire_once_per_threshold_crossing"] = True
        if t.initial_delay_seconds:
            rule["initial_delay_seconds"] = t.initial_delay_seconds
        if t.repeat_every_seconds:
            rule["repeat_every_seconds"] = t.repeat_every_seconds
        rules.append(rule)

    header = (
        "# Edited via the in-app Settings window -- hand-written comments/formatting beyond\n"
        "# this header are not preserved across GUI saves.\n\n"
    )
    path.write_text(header + yaml.safe_dump({"rules": rules}, sort_keys=False), encoding="utf-8")
