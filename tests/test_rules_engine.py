import companion.rules.engine as engine_mod
from companion.rules.engine import FiredAlert, RulesEngine
from companion.rules.schema import Action, AlertLevel, Condition, Trigger
from companion.state.game_state import ActorState, GameStateSnapshot


def make_state(zone=None, actors=None, messages=()):
    return GameStateSnapshot(zone=zone, actors=actors or {}, recent_messages=tuple(messages))


def boss_state(hp_pct, name="Boss"):
    hp_max = 100
    hp = int(hp_max * hp_pct / 100)
    actor = ActorState(actor_id="m:1", display_name=name, hp=hp, hp_max=hp_max)
    return make_state(actors={"m:1": actor})


def test_no_match_does_not_fire():
    trigger = Trigger(
        id="t1",
        when=Condition(hp_pct_below=30),
        then=Action(alert="go"),
    )
    engine = RulesEngine([trigger])
    assert engine.evaluate(make_state()) == []


def test_edge_detect_fires_once_then_suppresses_while_still_matched():
    trigger = Trigger(
        id="t1",
        when=Condition(boss_name="Boss", hp_pct_below=30),
        then=Action(alert="burn phase"),
        fire_once_per_threshold_crossing=True,
    )
    engine = RulesEngine([trigger])

    fired = engine.evaluate(boss_state(20))
    assert [a.trigger_id for a in fired] == ["t1"]

    fired_again = engine.evaluate(boss_state(15))
    assert fired_again == []


def test_edge_detect_rearms_after_condition_clears():
    trigger = Trigger(
        id="t1",
        when=Condition(boss_name="Boss", hp_pct_below=30),
        then=Action(alert="burn phase"),
        fire_once_per_threshold_crossing=True,
    )
    engine = RulesEngine([trigger])

    assert len(engine.evaluate(boss_state(20))) == 1
    assert engine.evaluate(boss_state(50)) == []  # condition clears, re-arms
    assert len(engine.evaluate(boss_state(10))) == 1  # fires again on second crossing


def test_cooldown_throttles_then_allows_after_elapsed(monkeypatch):
    fake_time = [0.0]
    monkeypatch.setattr(engine_mod.time, "monotonic", lambda: fake_time[0])

    trigger = Trigger(
        id="t1",
        when=Condition(message_contains="incoming fire"),
        then=Action(alert="dodge", level=AlertLevel.CRITICAL),
        cooldown_seconds=5.0,
    )
    engine = RulesEngine([trigger])
    state = make_state(messages=["boss says incoming fire now"])

    fake_time[0] = 0.0
    assert len(engine.evaluate(state)) == 1

    fake_time[0] = 2.0  # within cooldown window
    assert engine.evaluate(state) == []

    fake_time[0] = 6.0  # cooldown elapsed
    fired = engine.evaluate(state)
    assert len(fired) == 1
    assert isinstance(fired[0], FiredAlert)
    assert fired[0].level == AlertLevel.CRITICAL


def test_boss_name_alone_matches_presence():
    trigger = Trigger(id="t1", when=Condition(boss_name="Boss"), then=Action(alert="hi"))
    engine = RulesEngine([trigger])
    assert len(engine.evaluate(boss_state(80))) == 1
    assert engine.evaluate(make_state()) == []  # boss not present


def test_zone_equals_matches_exact_zone():
    trigger = Trigger(id="t1", when=Condition(zone_equals="Lair"), then=Action(alert="hi"))
    engine = RulesEngine([trigger])
    assert engine.evaluate(make_state(zone="Town")) == []
    assert len(engine.evaluate(make_state(zone="Lair"))) == 1


# ── RulesEngine.reload ────────────────────────────────────────────────────────

def test_reload_swaps_triggers():
    t1 = Trigger(id="t1", when=Condition(zone_equals="Lair"), then=Action(alert="hi"))
    t2 = Trigger(id="t2", when=Condition(zone_equals="Town"), then=Action(alert="there"))
    engine = RulesEngine([t1])
    assert len(engine.evaluate(make_state(zone="Lair"))) == 1
    assert engine.evaluate(make_state(zone="Town")) == []

    engine.reload([t2])
    assert engine.evaluate(make_state(zone="Lair")) == []
    assert len(engine.evaluate(make_state(zone="Town"))) == 1


def test_reload_preserves_cooldown_state(monkeypatch):
    fake_time = [0.0]
    monkeypatch.setattr(engine_mod.time, "monotonic", lambda: fake_time[0])

    t = Trigger(id="t1", when=Condition(zone_equals="Lair"), then=Action(alert="hi"), cooldown_seconds=10.0)
    engine = RulesEngine([t])
    state = make_state(zone="Lair")

    fake_time[0] = 0.0
    assert len(engine.evaluate(state)) == 1  # first fire

    # reload with the same id — cooldown timer should be preserved
    engine.reload([t])
    fake_time[0] = 5.0
    assert engine.evaluate(state) == []  # still within cooldown


def test_reload_drops_armed_state_for_removed_rule():
    t1 = Trigger(id="t1", when=Condition(zone_equals="Lair"), then=Action(alert="hi"), fire_once_per_threshold_crossing=True)
    t2 = Trigger(id="t2", when=Condition(zone_equals="Town"), then=Action(alert="there"), fire_once_per_threshold_crossing=True)
    engine = RulesEngine([t1])
    engine.evaluate(make_state(zone="Lair"))  # disarms t1

    # reload with t2 only — t1 state is gone
    engine.reload([t2])
    assert len(engine.evaluate(make_state(zone="Town"))) == 1  # t2 fires (fresh)


def test_reload_preserves_armed_state_for_kept_rule():
    t1 = Trigger(id="t1", when=Condition(zone_equals="Lair"), then=Action(alert="hi"), fire_once_per_threshold_crossing=True)
    engine = RulesEngine([t1])
    engine.evaluate(make_state(zone="Lair"))  # disarms t1

    # reload keeping t1 — armed=False should be preserved so it doesn't re-fire immediately
    engine.reload([t1])
    assert engine.evaluate(make_state(zone="Lair")) == []
