"""Regression tests from tester feedback: lists in message_contains must WORK (any-of),
wrong types and typo'd keys must produce named errors at load time (never a runtime crash),
and one broken boss pack must not take down the others in non-strict mode."""

import pytest

from companion.rules.engine import RulesEngine
from companion.rules.packs import load_boss_packs
from companion.rules.schema import parse_rule_dict
from companion.state.game_state import GameStateSnapshot


def rule(when: dict, **extra) -> dict:
    return {"id": "r1", "when": when, "then": {"alert": "x"}, **extra}


def snapshot(*messages: str) -> GameStateSnapshot:
    return GameStateSnapshot(zone=None, actors={}, recent_messages=tuple(messages))


# ── message_contains list support ─────────────────────────────────────────

def test_message_list_parses_to_tuple():
    t = parse_rule_dict(rule({"message_contains": ["staff", "counter"]}), context="t")
    assert t.when.message_contains == ("staff", "counter")


def test_message_list_matches_any_fragment():
    t = parse_rule_dict(rule({"message_contains": ["staff is down", "counter attack"]}), context="t")
    engine = RulesEngine([t])
    assert len(engine.evaluate(snapshot("COUNTER ATTACK incoming!"))) == 1


def test_message_list_no_match_no_fire():
    t = parse_rule_dict(rule({"message_contains": ["staff", "counter"]}), context="t")
    assert RulesEngine([t]).evaluate(snapshot("something unrelated")) == []


def test_message_plain_string_still_works():
    t = parse_rule_dict(rule({"message_contains": "staff is down"}), context="t")
    assert len(RulesEngine([t]).evaluate(snapshot("The Staff is Down..."))) == 1


# ── type validation: named errors instead of runtime crashes ─────────────

def test_message_contains_dict_rejected_at_load():
    with pytest.raises(ValueError, match="message_contains"):
        parse_rule_dict(rule({"message_contains": {"oops": 1}}), context="t")


def test_message_list_of_numbers_rejected():
    with pytest.raises(ValueError, match="only text strings"):
        parse_rule_dict(rule({"message_contains": ["ok", 42]}), context="t")


def test_boss_name_list_rejected_with_field_name():
    with pytest.raises(ValueError, match="boss_name"):
        parse_rule_dict(rule({"boss_name": ["a", "b"]}), context="t")


def test_hp_pct_below_non_number_rejected():
    with pytest.raises(ValueError, match="hp_pct_below"):
        parse_rule_dict(rule({"hp_pct_below": "lots"}), context="t")


def test_unknown_condition_key_names_the_typo():
    with pytest.raises(ValueError, match="visual_cues"):
        parse_rule_dict(rule({"visual_cues": "x"}), context="t")


def test_unknown_rule_key_rejected():
    with pytest.raises(ValueError, match="cooldown"):
        parse_rule_dict(rule({"message_contains": "x"}, cooldown=5), context="t")


def test_error_message_names_the_source_file():
    with pytest.raises(ValueError, match="bosses/broken.yaml"):
        parse_rule_dict(rule({"hp_pct_below": "nan-sense"}), context="bosses/broken.yaml")


# ── non-strict pack loading: skip broken, keep the rest ──────────────────

GOOD_PACK = """
boss: Good Boss
rules:
  - id: ok
    when: {message_contains: "fine"}
    then: {alert: "fine"}
"""

BROKEN_PACK = """
rules:
  - id: broken
    when: {message_contains: {not: valid}}
    then: {alert: "x"}
"""


def test_non_strict_skips_broken_pack_keeps_good(tmp_path, capsys):
    (tmp_path / "a_broken.yaml").write_text(BROKEN_PACK, encoding="utf-8")
    (tmp_path / "b_good.yaml").write_text(GOOD_PACK, encoding="utf-8")

    packs = load_boss_packs(tmp_path, strict=False)
    assert [p.name for p in packs] == ["Good Boss"]
    out = capsys.readouterr().out
    assert "SKIPPED a_broken.yaml" in out


def test_non_strict_skips_unparseable_yaml(tmp_path, capsys):
    (tmp_path / "a_bad.yaml").write_text("rules:\n  - id: x\n   bad_indent: {", encoding="utf-8")
    (tmp_path / "b_good.yaml").write_text(GOOD_PACK, encoding="utf-8")

    packs = load_boss_packs(tmp_path, strict=False)
    assert [p.name for p in packs] == ["Good Boss"]
    assert "SKIPPED" in capsys.readouterr().out


def test_strict_mode_still_raises(tmp_path):
    (tmp_path / "a_broken.yaml").write_text(BROKEN_PACK, encoding="utf-8")
    with pytest.raises(ValueError):
        load_boss_packs(tmp_path)


def test_unknown_cue_key_names_typo(tmp_path):
    (tmp_path / "a.yaml").write_text(
        """
cues:
  - id: glow
    hsv_lower: [0, 0, 0]
    hsv_upper: [10, 255, 255]
    min_coverage_percent: 5
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="min_coverage_percent"):
        load_boss_packs(tmp_path)
