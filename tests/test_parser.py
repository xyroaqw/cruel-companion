"""Parser tests using real frame shapes captured from a live Escherion fight (Grimoire
client, 2026-07-06). If AQW's protocol drifts, re-capture with tools/capture_spike.py and
update these samples."""

from companion.protocol.events import (
    IdentityHintEvent,
    MessageEvent,
    VitalsEvent,
    ZoneChangeEvent,
)
from companion.protocol.parser import parse_frame

# --- real captured frames (trimmed) ---

CT_MONSTER_AND_PLAYER = {
    "t": "xt",
    "b": {"r": -1, "o": {
        "cmd": "ct",
        "m": {"3": {"intState": 2, "intHP": 3873}},
        "p": {"xyronius": {"intState": 2, "intMP": 100}},
    }},
}

CT_PLAYER_HP = {
    "t": "xt",
    "b": {"r": -1, "o": {"cmd": "ct", "p": {"xyronius": {"intHP": 2240}}}},
}

MTLS_ESCHERION = {
    "t": "xt",
    "b": {"r": -1, "o": {"cmd": "mtls", "id": 3, "o": {"intState": 1, "intHP": 6000, "intMP": 100}}},
}

ADD_GOLD_EXP = {
    "t": "xt",
    "b": {"r": -1, "o": {"cmd": "addGoldExp", "intGold": 59, "typ": "m", "id": 3}},
}

# Real ct aura shape from the Escherion capture (isNew toggled for the test cases).
CT_WITH_AURAS = {
    "t": "xt",
    "b": {"r": -1, "o": {
        "cmd": "ct",
        "a": [
            {"cmd": "aura+", "tInf": "m:3", "cInf": "m:3",
             "auras": [{"nam": "Empowered", "dur": 10, "t": "s", "isNew": True}]},
            {"cmd": "aura+", "tInf": "p:24686", "cInf": "p:24686",
             "auras": [{"nam": "Dricken +20% Damage Done", "dur": 20, "isNew": False}]},
            {"cmd": "aura-", "tInf": "m:3", "aura": {"nam": "Empowered"}},
        ],
    }},
}

# Real Nulgath telegraph frame: boss text rides in a ct anims[].msg field.
CT_ANIM_MSG = {
    "t": "xt",
    "b": {"r": -1, "o": {
        "cmd": "ct",
        "m": {"1": {}},
        "p": {"xyronius": {}},
        "anims": [{"cInf": "m:2", "tInf": "p:25152", "animStr": "Charge",
                   "strFrame": "Boss", "fx": "m", "msg": "Behold the power of the Abyss!"}],
    }},
}

UOTLS_PLAYER = {
    "t": "xt",
    "b": {"r": -1, "o": {"cmd": "uotls", "unm": "xyronius",
                         "o": {"intHP": 2000, "intHPMax": 2835, "intMP": 100, "intMPMax": 100}}},
}

# Real escherion room-load frame (roster trimmed to the two monsters + the player).
MOVE_TO_ESCHERION = {
    "t": "xt",
    "b": {"r": -1, "o": {
        "cmd": "moveToArea",
        "strMapName": "escherion",
        "areaName": "escherion-1022",
        "monmap": [
            {"MonMapID": 2, "MonID": 203},
            {"MonMapID": 3, "MonID": 187},
        ],
        "mondef": [
            {"MonID": 187, "strMonName": "Escherion"},
            {"MonID": 203, "strMonName": "Staff of Inversion"},
        ],
        "monBranch": [
            {"MonMapID": 2, "intState": 1, "intHP": 1000, "intHPMax": 1000},
            {"MonMapID": 3, "intState": 1, "intHP": 6000, "intHPMax": 6000},
        ],
        "uoBranch": [
            {"uoName": "xyronius", "intHP": 2155, "intHPMax": 2155, "intMP": 100},
        ],
    }},
}


def test_ct_yields_monster_and_player_vitals():
    (event,) = parse_frame(CT_MONSTER_AND_PLAYER)
    assert isinstance(event, VitalsEvent)
    by_id = {a.actor_id: a for a in event.actors}
    assert by_id["m:3"].hp == 3873
    assert by_id["m:3"].state == 2
    assert by_id["p:xyronius"].mp == 100
    assert by_id["p:xyronius"].hp is None  # not present in this frame


def test_ct_player_hp_only():
    (event,) = parse_frame(CT_PLAYER_HP)
    (actor,) = event.actors
    assert actor.actor_id == "p:xyronius"
    assert actor.hp == 2240


def test_mtls_provides_max_hp():
    (event,) = parse_frame(MTLS_ESCHERION)
    (actor,) = event.actors
    assert actor.actor_id == "m:3"
    assert actor.hp_max == 6000
    assert actor.hp is None  # mtls is the MAX source; current HP comes from ct


def test_mtls_then_ct_gives_hp_pct():
    """The whole point: max from mtls + current from ct = a usable HP percentage."""
    from companion.identity.resolver import IdentityResolver
    from companion.state.game_state import GameState

    state = GameState(identity=IdentityResolver.__new__(IdentityResolver))
    state._identity = _StubIdentity()
    for ev in parse_frame(MTLS_ESCHERION):
        state.apply(ev)
    for ev in parse_frame({"t": "xt", "b": {"o": {"cmd": "ct", "m": {"3": {"intHP": 1500}}}}}):
        state.apply(ev)
    actor = state.snapshot().actors["m:3"]
    assert actor.hp == 1500 and actor.hp_max == 6000
    assert actor.hp_pct == 25.0


def test_anim_msg_becomes_message():
    (msg,) = [e for e in parse_frame(CT_ANIM_MSG) if isinstance(e, MessageEvent)]
    assert msg.text == "Behold the power of the Abyss!"
    assert msg.caster_id == "m:2"
    assert msg.raw_kind == "anim_msg"


def test_anim_msg_matches_user_rule():
    """The reported bug: a message_contains rule keyed on boss telegraph text now fires."""
    from companion.rules.engine import RulesEngine
    from companion.rules.schema import Action, AlertLevel, Condition, Trigger
    from companion.state.game_state import GameStateSnapshot

    (msg,) = [e for e in parse_frame(CT_ANIM_MSG) if isinstance(e, MessageEvent)]
    snap = GameStateSnapshot(zone=None, actors={}, recent_messages=(msg.text,))
    engine = RulesEngine([Trigger(
        id="taunt", when=Condition(message_contains="Behold the power of the Abyss!"),
        then=Action(alert="LoO - Taunt Nulgath", level=AlertLevel.CRITICAL),
    )])
    assert len(engine.evaluate(snap)) == 1


def test_new_auras_become_messages():
    events = parse_frame(CT_WITH_AURAS)
    messages = [e for e in events if isinstance(e, MessageEvent)]
    texts = [m.text for m in messages]
    assert "aura+ Empowered on m:3" in texts
    assert "aura- Empowered on m:3" in texts
    # Refresh ticks (isNew: false) are NOT surfaced -- they'd flood the buffer.
    assert not any("Dricken" in t for t in texts)


def test_aura_message_matches_rule():
    """The point of the feature: a message_contains rule keys off the aura name."""
    from companion.rules.engine import RulesEngine
    from companion.rules.schema import Action, AlertLevel, Condition, Trigger
    from companion.state.game_state import GameStateSnapshot

    (msg,) = [e for e in parse_frame(CT_WITH_AURAS) if isinstance(e, MessageEvent)][:1]
    snap = GameStateSnapshot(zone=None, actors={}, recent_messages=(msg.text,))
    engine = RulesEngine([Trigger(
        id="taunt", when=Condition(message_contains="aura+ Empowered"),
        then=Action(alert="Taunt now!", level=AlertLevel.CRITICAL),
    )])
    assert len(engine.evaluate(snap)) == 1


def test_uotls_player_max_hp():
    (event,) = parse_frame(UOTLS_PLAYER)
    (actor,) = event.actors
    assert actor.actor_id == "p:xyronius"
    assert actor.hp == 2000 and actor.hp_max == 2835


def test_move_to_area_emits_zone_change():
    events = parse_frame(MOVE_TO_ESCHERION)
    zones = [e for e in events if isinstance(e, ZoneChangeEvent)]
    assert len(zones) == 1 and zones[0].zone_name == "escherion"


def test_move_to_area_maps_monster_names():
    events = parse_frame(MOVE_TO_ESCHERION)
    hints = {e.actor_id: e.display_name for e in events if isinstance(e, IdentityHintEvent)}
    # MonMapID (ct key) -> MonID -> strMonName join
    assert hints == {"m:2": "Staff of Inversion", "m:3": "Escherion"}


def test_move_to_area_carries_max_hp():
    events = parse_frame(MOVE_TO_ESCHERION)
    (vitals,) = [e for e in events if isinstance(e, VitalsEvent)]
    by_id = {a.actor_id: a for a in vitals.actors}
    assert by_id["m:3"].hp_max == 6000  # Escherion
    assert by_id["m:2"].hp_max == 1000  # Staff
    assert by_id["p:xyronius"].hp_max == 2155


def test_move_to_area_end_to_end_resolves_named_boss(tmp_path):
    """Room load -> GameState -> a boss_name rule matches by resolved name."""
    from companion.identity.resolver import IdentityResolver
    from companion.rules.engine import RulesEngine
    from companion.rules.schema import Action, AlertLevel, Condition, Trigger
    from companion.state.game_state import GameState

    ident = IdentityResolver(tmp_path / "identities.json")
    state = GameState(identity=ident)
    for ev in parse_frame(MOVE_TO_ESCHERION):
        state.apply(ev)

    engine = RulesEngine([Trigger(
        id="staff_present",
        when=Condition(boss_name="Staff of Inversion", hp_pct_below=101),
        then=Action(alert="staff here", level=AlertLevel.INFO),
    )])
    assert len(engine.evaluate(state.snapshot())) == 1


def test_unrelated_cmd_ignored():
    assert parse_frame(ADD_GOLD_EXP) == []


def test_non_xt_frame_ignored():
    assert parse_frame({"t": "sys", "b": {}}) == []


def test_garbage_never_raises():
    for junk in [{}, {"t": "xt"}, {"t": "xt", "b": "nope"}, {"t": "xt", "b": {"o": None}},
                 {"t": "xt", "b": {"o": {"cmd": "ct", "m": "notadict"}}}, "string", 42, None]:
        assert parse_frame(junk) == []


class _StubIdentity:
    def resolve(self, actor_id):
        return actor_id
