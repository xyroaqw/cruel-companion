from companion.identity.resolver import IdentityResolver
from companion.protocol.events import (
    ActorVitals,
    IdentityHintEvent,
    MessageEvent,
    VitalsEvent,
    ZoneChangeEvent,
)
from companion.state.game_state import GameState


def make_game_state(tmp_path):
    return GameState(identity=IdentityResolver(tmp_path / "identities.json"))


def test_apply_vitals_creates_actor(tmp_path):
    state = make_game_state(tmp_path)
    state.apply(VitalsEvent(ts=0.0, actors=[ActorVitals(actor_id="m:1", hp=50, hp_max=100)]))

    actor = state.get_actor("m:1")
    assert actor is not None
    assert actor.hp == 50
    assert actor.hp_max == 100
    assert actor.hp_pct == 50.0


def test_apply_vitals_merges_partial_update_preserves_previous_fields(tmp_path):
    state = make_game_state(tmp_path)
    state.apply(VitalsEvent(ts=0.0, actors=[ActorVitals(actor_id="m:1", hp=100, hp_max=100)]))
    state.apply(VitalsEvent(ts=1.0, actors=[ActorVitals(actor_id="m:1", hp=40)]))  # no hp_max

    actor = state.get_actor("m:1")
    assert actor.hp == 40
    assert actor.hp_max == 100  # preserved from the earlier packet
    assert actor.hp_pct == 40.0


def test_apply_message_appends_to_recent_messages(tmp_path):
    state = make_game_state(tmp_path)
    state.apply(MessageEvent(ts=0.0, text="incoming fire"))
    assert state.snapshot().recent_messages == ("incoming fire",)


def test_recent_messages_capped(tmp_path):
    state = GameState(identity=IdentityResolver(tmp_path / "identities.json"), max_recent_messages=2)
    state.apply(MessageEvent(ts=0.0, text="a"))
    state.apply(MessageEvent(ts=1.0, text="b"))
    state.apply(MessageEvent(ts=2.0, text="c"))
    assert state.snapshot().recent_messages == ("b", "c")


def test_apply_zone_change_updates_zone(tmp_path):
    state = make_game_state(tmp_path)
    state.apply(ZoneChangeEvent(ts=0.0, zone_name="Lair"))
    assert state.zone == "Lair"
    assert state.snapshot().zone == "Lair"


def test_zone_change_clears_monsters_but_keeps_players(tmp_path):
    state = make_game_state(tmp_path)
    state.apply(
        VitalsEvent(
            ts=0.0,
            actors=[
                ActorVitals(actor_id="m:1", hp=50, hp_max=100),
                ActorVitals(actor_id="p:1", hp=80, hp_max=100),
            ],
        )
    )
    state.apply(ZoneChangeEvent(ts=1.0, zone_name="NewRoom"))

    assert state.get_actor("m:1") is None
    assert state.get_actor("p:1") is not None


def test_identity_hint_updates_display_name_on_next_vitals(tmp_path):
    state = make_game_state(tmp_path)
    state.apply(VitalsEvent(ts=0.0, actors=[ActorVitals(actor_id="m:1", hp=50, hp_max=100)]))
    assert state.get_actor("m:1").display_name == "m:1"  # not yet known

    state.apply(IdentityHintEvent(ts=1.0, actor_id="m:1", display_name="Sepulchure"))
    state.apply(VitalsEvent(ts=2.0, actors=[ActorVitals(actor_id="m:1", hp=40, hp_max=100)]))
    assert state.get_actor("m:1").display_name == "Sepulchure"


def test_snapshot_supports_rules_lookups(tmp_path):
    state = make_game_state(tmp_path)
    state.apply(IdentityHintEvent(ts=0.0, actor_id="m:1", display_name="Boss"))
    state.apply(VitalsEvent(ts=1.0, actors=[ActorVitals(actor_id="m:1", hp=20, hp_max=100)]))

    snap = state.snapshot()
    assert snap.find_actor_by_name("Boss").hp_pct == 20.0
    assert [a.actor_id for a in snap.monsters()] == ["m:1"]
