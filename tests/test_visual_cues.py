"""The visual-cue path end to end (minus pixels): VisualCueEvent -> GameState -> rules
engine, plus schema round-tripping and pack-trigger survival across engine reloads."""

from pathlib import Path

from companion.identity.resolver import IdentityResolver
from companion.protocol.events import VisualCueEvent, ZoneChangeEvent
from companion.rules.engine import RulesEngine
from companion.rules.schema import Action, AlertLevel, Condition, Trigger, load_rules, save_rules
from companion.state.game_state import GameState


def make_state(tmp_path) -> GameState:
    return GameState(identity=IdentityResolver(tmp_path / "identities.json"))


def cue_trigger(rule_id="pack:dodge", cue="pack:red_glow", fire_once=True) -> Trigger:
    return Trigger(
        id=rule_id,
        when=Condition(visual_cue=cue),
        then=Action(alert="Move!", level=AlertLevel.CRITICAL),
        fire_once_per_threshold_crossing=fire_once,
    )


def test_cue_events_toggle_snapshot_membership(tmp_path):
    state = make_state(tmp_path)
    state.apply(VisualCueEvent(ts=1.0, cue_id="pack:red_glow", active=True, coverage_pct=3.0))
    assert "pack:red_glow" in state.snapshot().visual_cues

    state.apply(VisualCueEvent(ts=2.0, cue_id="pack:red_glow", active=False))
    assert "pack:red_glow" not in state.snapshot().visual_cues


def test_zone_change_clears_latched_cues(tmp_path):
    state = make_state(tmp_path)
    state.apply(VisualCueEvent(ts=1.0, cue_id="pack:red_glow", active=True))
    state.apply(ZoneChangeEvent(ts=2.0, zone_name="somewhere-else"))
    assert state.snapshot().visual_cues == frozenset()


def test_engine_fires_on_cue_and_rearms_when_it_clears(tmp_path):
    state = make_state(tmp_path)
    engine = RulesEngine([cue_trigger()])

    assert engine.evaluate(state.snapshot()) == []

    state.apply(VisualCueEvent(ts=1.0, cue_id="pack:red_glow", active=True))
    (alert,) = engine.evaluate(state.snapshot())
    assert alert.trigger_id == "pack:dodge"
    # Cue still on: fire_once means no repeat.
    assert engine.evaluate(state.snapshot()) == []

    state.apply(VisualCueEvent(ts=2.0, cue_id="pack:red_glow", active=False))
    engine.evaluate(state.snapshot())  # re-arms
    state.apply(VisualCueEvent(ts=3.0, cue_id="pack:red_glow", active=True))
    assert len(engine.evaluate(state.snapshot())) == 1


def test_pack_triggers_survive_engine_reload(tmp_path):
    state = make_state(tmp_path)
    base = Trigger(id="base", when=Condition(zone_equals="x"), then=Action(alert="in x"))
    engine = RulesEngine([base], pack_triggers=[cue_trigger()])

    engine.reload([])  # GUI save with all base rules deleted

    state.apply(VisualCueEvent(ts=1.0, cue_id="pack:red_glow", active=True))
    (alert,) = engine.evaluate(state.snapshot())
    assert alert.trigger_id == "pack:dodge"


def test_visual_cue_round_trips_through_yaml(tmp_path):
    path = Path(tmp_path) / "rules.yaml"
    save_rules([cue_trigger(rule_id="dodge", fire_once=False)], path)

    (loaded,) = load_rules(path)
    assert loaded.when.visual_cue == "pack:red_glow"
