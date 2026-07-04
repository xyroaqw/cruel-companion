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
    message_contains: str | None = None
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


def parse_rule_dict(raw: dict, context: str) -> Trigger:
    """Parses one raw rule mapping into a Trigger. Shared by load_rules (config/rules.yaml)
    and the boss-pack loader (companion/rules/packs.py). context names the source for error
    messages, e.g. "rules.yaml entry #2" or "bosses/ultra_darkon.yaml".
    """
    rule_id = raw.get("id")
    if not rule_id:
        raise ValueError(f"{context} is missing required field 'id'")

    when_raw = raw.get("when")
    if not when_raw:
        raise ValueError(f"rule '{rule_id}' ({context}) is missing required field 'when'")

    then_raw = raw.get("then")
    if not then_raw or not then_raw.get("alert"):
        raise ValueError(f"rule '{rule_id}' ({context}) is missing required field 'then.alert'")

    condition = Condition(
        zone_equals=when_raw.get("zone_equals"),
        boss_name=when_raw.get("boss_name"),
        hp_pct_below=when_raw.get("hp_pct_below"),
        message_contains=when_raw.get("message_contains"),
        visual_cue=when_raw.get("visual_cue"),
    )

    try:
        level = AlertLevel(then_raw.get("level", "info"))
    except ValueError as exc:
        valid = ", ".join(level.value for level in AlertLevel)
        raise ValueError(
            f"rule '{rule_id}' ({context}) has invalid 'then.level' (must be one of: {valid})"
        ) from exc

    return Trigger(
        id=rule_id,
        when=condition,
        then=Action(alert=then_raw["alert"], level=level),
        cooldown_seconds=float(raw.get("cooldown_seconds", 0.0)),
        fire_once_per_threshold_crossing=bool(
            raw.get("fire_once_per_threshold_crossing", False)
        ),
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
            when["message_contains"] = t.when.message_contains
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
        rules.append(rule)

    header = (
        "# Edited via the in-app Settings window -- hand-written comments/formatting beyond\n"
        "# this header are not preserved across GUI saves.\n\n"
    )
    path.write_text(header + yaml.safe_dump({"rules": rules}, sort_keys=False), encoding="utf-8")
