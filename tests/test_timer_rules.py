"""Timer-mode triggers: initial_delay_seconds + repeat_every_seconds, anchored to when the
condition first becomes true (fight start). Uses a fake clock so the tests are instant."""

import companion.rules.engine as engine_mod
from companion.rules.engine import RulesEngine
from companion.rules.schema import Action, AlertLevel, Condition, Trigger
from companion.state.game_state import GameStateSnapshot


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def lr_timer(delay=5.0, repeat=12.0) -> Trigger:
    return Trigger(
        id="lr", when=Condition(boss_name="Nulgath"),
        then=Action(alert="Taunt!", level=AlertLevel.WARNING),
        initial_delay_seconds=delay, repeat_every_seconds=repeat,
    )


def boss_present() -> GameStateSnapshot:
    from companion.state.game_state import ActorState
    boss = ActorState(actor_id="m:2", display_name="Nulgath", hp=100, hp_max=100)
    return GameStateSnapshot(zone="x", actors={"m:2": boss}, recent_messages=())


def no_boss() -> GameStateSnapshot:
    return GameStateSnapshot(zone="x", actors={}, recent_messages=())


def setup_engine(monkeypatch, trigger):
    clock = Clock()
    monkeypatch.setattr(engine_mod.time, "monotonic", clock)
    return RulesEngine([trigger]), clock


def test_is_timer_flag():
    assert lr_timer().is_timer
    assert not Trigger(id="x", when=Condition(boss_name="N"),
                       then=Action(alert="a")).is_timer


def test_fires_after_initial_delay_not_before(monkeypatch):
    eng, clock = setup_engine(monkeypatch, lr_timer(delay=5, repeat=12))
    present = boss_present()

    # Pull: boss appears at t=1000. Nothing yet.
    assert eng.evaluate(present) == []
    clock.t = 1004  # 4s in -- still before the 5s delay
    assert eng.evaluate(present) == []
    clock.t = 1005.1  # past 5s -- first taunt reminder
    assert [a.message for a in eng.evaluate(present)] == ["Taunt!"]


def test_repeats_on_interval(monkeypatch):
    eng, clock = setup_engine(monkeypatch, lr_timer(delay=5, repeat=12))
    present = boss_present()
    eng.evaluate(present)          # anchor at 1000
    clock.t = 1005.1
    assert len(eng.evaluate(present)) == 1   # first at +5s
    clock.t = 1010
    assert eng.evaluate(present) == []       # not yet 12s since last
    clock.t = 1017.2
    assert len(eng.evaluate(present)) == 1   # +12s -> repeat
    clock.t = 1029.3
    assert len(eng.evaluate(present)) == 1   # +12s -> repeat again


def test_leaving_fight_resets_timer(monkeypatch):
    eng, clock = setup_engine(monkeypatch, lr_timer(delay=5, repeat=12))
    eng.evaluate(boss_present())   # anchor at 1000
    clock.t = 1006
    assert len(eng.evaluate(boss_present())) == 1  # fired once

    clock.t = 1030                 # leave the room -> condition false, timer resets
    assert eng.evaluate(no_boss()) == []

    clock.t = 1100                 # re-pull; must wait the full 5s again, not fire instantly
    assert eng.evaluate(boss_present()) == []
    clock.t = 1104
    assert eng.evaluate(boss_present()) == []
    clock.t = 1106
    assert len(eng.evaluate(boss_present())) == 1


def test_delay_only_fires_once(monkeypatch):
    # repeat_every=0 -> a one-shot pull timer (fire once at delay, never again).
    eng, clock = setup_engine(monkeypatch, lr_timer(delay=5, repeat=0))
    present = boss_present()
    eng.evaluate(present)
    clock.t = 1006
    assert len(eng.evaluate(present)) == 1
    clock.t = 1100
    assert eng.evaluate(present) == []  # no repeat


def test_repeat_only_fires_immediately_then_repeats(monkeypatch):
    # delay=0, repeat>0 -> fire at pull, then every interval.
    eng, clock = setup_engine(monkeypatch, lr_timer(delay=0, repeat=10))
    present = boss_present()
    assert len(eng.evaluate(present)) == 1  # immediate at pull
    clock.t = 1005
    assert eng.evaluate(present) == []
    clock.t = 1010.1
    assert len(eng.evaluate(present)) == 1
