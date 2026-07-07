from pathlib import Path

import pytest
import yaml

from companion.rules.schema import (
    Action,
    AlertLevel,
    Condition,
    Trigger,
    load_rules,
    save_rules,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def write_rules(tmp_path, data) -> Path:
    path = tmp_path / "rules.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_loads_real_config_rules_yaml():
    # The shipped rules.yaml must always parse cleanly and include the verified Nulgath rule.
    triggers = load_rules(REPO_ROOT / "config" / "rules.yaml")
    nulgie = next(t for t in triggers if t.id == "Nulgie")
    assert nulgie.when.message_contains == "Behold the power of the Abyss!"


def test_missing_id_raises(tmp_path):
    path = write_rules(tmp_path, {"rules": [{"when": {"zone_equals": "X"}, "then": {"alert": "go"}}]})
    with pytest.raises(ValueError, match="missing required field 'id'"):
        load_rules(path)


def test_duplicate_id_raises(tmp_path):
    rule = {"id": "dup", "when": {"zone_equals": "X"}, "then": {"alert": "go"}}
    path = write_rules(tmp_path, {"rules": [rule, dict(rule)]})
    with pytest.raises(ValueError, match="duplicate rule id 'dup'"):
        load_rules(path)


def test_missing_when_raises(tmp_path):
    path = write_rules(tmp_path, {"rules": [{"id": "r1", "then": {"alert": "go"}}]})
    with pytest.raises(ValueError, match="missing required field 'when'"):
        load_rules(path)


def test_missing_then_alert_raises(tmp_path):
    path = write_rules(tmp_path, {"rules": [{"id": "r1", "when": {"zone_equals": "X"}, "then": {}}]})
    with pytest.raises(ValueError, match="missing required field 'then.alert'"):
        load_rules(path)


def test_invalid_level_raises(tmp_path):
    rule = {"id": "r1", "when": {"zone_equals": "X"}, "then": {"alert": "go", "level": "nope"}}
    path = write_rules(tmp_path, {"rules": [rule]})
    with pytest.raises(ValueError, match="invalid 'then.level'"):
        load_rules(path)


def test_defaults_applied(tmp_path):
    rule = {"id": "r1", "when": {"zone_equals": "X"}, "then": {"alert": "go"}}
    path = write_rules(tmp_path, {"rules": [rule]})
    [trigger] = load_rules(path)
    assert trigger.then.level == AlertLevel.INFO
    assert trigger.cooldown_seconds == 0.0
    assert trigger.fire_once_per_threshold_crossing is False


# ── save_rules round-trip ─────────────────────────────────────────────────────

def make_trigger(
    rule_id="t1",
    zone_equals=None,
    boss_name=None,
    hp_pct_below=None,
    message_contains=None,
    alert="do thing",
    level=AlertLevel.INFO,
    cooldown_seconds=0.0,
    fire_once=False,
):
    return Trigger(
        id=rule_id,
        when=Condition(
            zone_equals=zone_equals,
            boss_name=boss_name,
            hp_pct_below=hp_pct_below,
            message_contains=message_contains,
        ),
        then=Action(alert=alert, level=level),
        cooldown_seconds=cooldown_seconds,
        fire_once_per_threshold_crossing=fire_once,
    )


def test_save_rules_round_trip_minimal(tmp_path):
    trigger = make_trigger(zone_equals="Lair")
    path = tmp_path / "rules.yaml"
    save_rules([trigger], path)
    [loaded] = load_rules(path)
    assert loaded.id == trigger.id
    assert loaded.when.zone_equals == "Lair"
    assert loaded.then.alert == "do thing"
    assert loaded.then.level == AlertLevel.INFO
    assert loaded.cooldown_seconds == 0.0
    assert loaded.fire_once_per_threshold_crossing is False


def test_save_rules_round_trip_full(tmp_path):
    trigger = make_trigger(
        rule_id="burn",
        boss_name="Tercess",
        hp_pct_below=30.0,
        alert="Burn!",
        level=AlertLevel.WARNING,
        fire_once=True,
    )
    path = tmp_path / "rules.yaml"
    save_rules([trigger], path)
    [loaded] = load_rules(path)
    assert loaded.when.boss_name == "Tercess"
    assert loaded.when.hp_pct_below == 30.0
    assert loaded.then.level == AlertLevel.WARNING
    assert loaded.fire_once_per_threshold_crossing is True


def test_save_rules_round_trip_multiple(tmp_path):
    triggers = [
        make_trigger("r1", zone_equals="Zone A"),
        make_trigger("r2", message_contains="fire", cooldown_seconds=5.0, alert="dodge"),
    ]
    path = tmp_path / "rules.yaml"
    save_rules(triggers, path)
    loaded = load_rules(path)
    assert [t.id for t in loaded] == ["r1", "r2"]
    assert loaded[1].cooldown_seconds == 5.0


def test_save_rules_overwrites_existing(tmp_path):
    path = tmp_path / "rules.yaml"
    save_rules([make_trigger("v1", zone_equals="A")], path)
    save_rules([make_trigger("v2", zone_equals="B")], path)
    loaded = load_rules(path)
    assert len(loaded) == 1
    assert loaded[0].id == "v2"
