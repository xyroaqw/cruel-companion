"""Raw SFS2X frame dict -> normalized events.

Field mappings verified 2026-07-06 against a live solo Escherion capture (Grimoire client,
port 5590). See tools/capture_spike.py to re-verify. Every frame is the SFS2X "extension"
shape {"t": "xt", "b": {"o": {"cmd": <str>, ...}}}; we dispatch on that inner o.cmd.

Verified frame types:
  ct          combat tick -- current vitals for monsters (o.m, keyed by MonMapID) and players
                        (o.p, keyed by player name). Values: intHP, intMP, intState. Also
                        carries aura+/aura- entries in o.a, surfaced as MessageEvents
                        ("aura+ <name> on <target>") so message_contains rules can key off
                        the server-side aura behind a client-side mechanic banner.
  mtls        monster full stats -- o.id + o.o.intHP is the monster's MAX HP (constant at
                        6000 for Escherion / 1000 for the Staff while ct shows HP draining).
  uotls       player full stats -- o.unm + o.o with intHP/intHPMax/intMP.
  moveToArea  room load / zone change -- carries strMapName (the zone), plus the monster
                        roster: monmap (MonMapID->MonID), mondef (MonID->strMonName), and
                        monBranch/uoBranch (per-entity intHP/intHPMax at load). This is where
                        monster NAMES and MAX HP come from at room entry, and the zone change.

Actor id convention (matches state/game_state.py: monsters start "m:"):
  monsters -> "m:<MonMapID>"      players -> "p:<name>"

NOT emitted from packets (confirmed absent, documented so nobody re-hunts): boss mechanic
TEXT (e.g. "The staff is down...") is rendered client-side, never sent as a packet -- the
packet-native signal is the Staff monster's HP hitting 0. Unrecognized shapes return [] --
never raise.
"""

from companion.protocol.events import (
    ActorVitals,
    IdentityHintEvent,
    MessageEvent,
    NormalizedEvent,
    VitalsEvent,
    ZoneChangeEvent,
)


def parse_frame(raw: dict) -> list[NormalizedEvent]:
    if not isinstance(raw, dict) or raw.get("t") != "xt":
        return []
    body = raw.get("b")
    if not isinstance(body, dict):
        return []
    o = body.get("o")
    if not isinstance(o, dict):
        return []

    cmd = o.get("cmd")
    try:
        if cmd == "ct":
            return _parse_combat_tick(o)
        if cmd == "mtls":
            return _parse_monster_stats(o)
        if cmd == "uotls":
            return _parse_player_stats(o)
        if cmd == "moveToArea":
            return _parse_move_to_area(o)
    except (TypeError, ValueError, AttributeError):
        # One malformed frame must never take down the capture pipeline.
        return []
    return []


def _parse_combat_tick(o: dict) -> list[NormalizedEvent]:
    events: list[NormalizedEvent] = []
    actors: list[ActorVitals] = []

    monsters = o.get("m")
    if isinstance(monsters, dict):
        for mid, vitals in monsters.items():
            if isinstance(vitals, dict):
                actors.append(_vitals(f"m:{mid}", vitals))

    players = o.get("p")
    if isinstance(players, dict):
        for name, vitals in players.items():
            if isinstance(vitals, dict):
                actors.append(_vitals(f"p:{name}", vitals))

    if actors:
        events.append(VitalsEvent(ts=0.0, actors=actors, kind="combat_tick"))

    events.extend(_parse_aura_entries(o.get("a")))
    return events


def _parse_aura_entries(entries) -> list[MessageEvent]:
    """ct frames carry aura applications in o.a: {"cmd": "aura+", "tInf": "m:3",
    "auras": [{"nam": ..., "isNew": bool}]} (and "aura-" removals with a single "aura").
    Boss mechanics are usually aura-driven -- the flashy on-screen text is client-side
    decoration for an aura the server DID send. Surfacing auras as messages gives
    message_contains rules a packet-native hook: match e.g. "aura+ Empowered".
    Only isNew auras are emitted for aura+ -- refresh ticks (isNew: false) would flood
    the message buffer.
    """
    messages: list[MessageEvent] = []
    for entry in _as_list(entries):
        if not isinstance(entry, dict):
            continue
        cmd = entry.get("cmd")
        target = entry.get("tInf", "?")
        if cmd == "aura+":
            for aura in _as_list(entry.get("auras")):
                if isinstance(aura, dict) and aura.get("nam") and aura.get("isNew"):
                    messages.append(
                        MessageEvent(
                            ts=0.0,
                            text=f"aura+ {aura['nam']} on {target}",
                            target_id=str(target),
                            raw_kind="aura",
                        )
                    )
        elif cmd == "aura-":
            aura = entry.get("aura")
            if isinstance(aura, dict) and aura.get("nam"):
                messages.append(
                    MessageEvent(
                        ts=0.0,
                        text=f"aura- {aura['nam']} on {target}",
                        target_id=str(target),
                        raw_kind="aura",
                    )
                )
    return messages


def _parse_monster_stats(o: dict) -> list[NormalizedEvent]:
    """mtls = a monster's full/max stats snapshot. o.o.intHP is the MAX HP."""
    mid = o.get("id")
    stats = o.get("o")
    if mid is None or not isinstance(stats, dict):
        return []
    hp_max = stats.get("intHP")
    if hp_max is None:
        return []
    return [
        VitalsEvent(
            ts=0.0,
            kind="monster_spawn",
            actors=[
                ActorVitals(
                    actor_id=f"m:{mid}",
                    hp_max=int(hp_max),
                    mp_max=_maybe_int(stats.get("intMP")),
                    state=_maybe_int(stats.get("intState")),
                )
            ],
        )
    ]


def _parse_player_stats(o: dict) -> list[NormalizedEvent]:
    """uotls = a player's full stats. o.unm is the name; o.o carries intHP/intHPMax/intMP."""
    name = o.get("unm")
    stats = o.get("o")
    if not name or not isinstance(stats, dict):
        return []
    return [
        VitalsEvent(
            ts=0.0,
            kind="player_state",
            actors=[
                ActorVitals(
                    actor_id=f"p:{name}",
                    hp=_maybe_int(stats.get("intHP")),
                    hp_max=_maybe_int(stats.get("intHPMax")),
                    mp=_maybe_int(stats.get("intMP")),
                    mp_max=_maybe_int(stats.get("intMPMax")),
                    state=_maybe_int(stats.get("intState")),
                )
            ],
        )
    ]


def _parse_move_to_area(o: dict) -> list[NormalizedEvent]:
    """Room load: emit the zone change, the monster name mapping, and everyone's max HP."""
    events: list[NormalizedEvent] = []

    zone = o.get("strMapName")
    if isinstance(zone, str) and zone:
        events.append(ZoneChangeEvent(ts=0.0, zone_name=zone))

    # MonMapID (the id ct uses) -> MonID -> strMonName, joined across monmap + mondef.
    monid_to_name = {
        d.get("MonID"): d.get("strMonName")
        for d in _as_list(o.get("mondef"))
        if isinstance(d, dict) and d.get("strMonName")
    }
    for m in _as_list(o.get("monmap")):
        if not isinstance(m, dict):
            continue
        name = monid_to_name.get(m.get("MonID"))
        map_id = m.get("MonMapID")
        if name and map_id is not None:
            events.append(IdentityHintEvent(ts=0.0, actor_id=f"m:{map_id}", display_name=name))

    monster_vitals = [
        ActorVitals(
            actor_id=f"m:{m.get('MonMapID')}",
            hp=_maybe_int(m.get("intHP")),
            hp_max=_maybe_int(m.get("intHPMax")),
            mp=_maybe_int(m.get("intMP")),
            state=_maybe_int(m.get("intState")),
        )
        for m in _as_list(o.get("monBranch"))
        if isinstance(m, dict) and m.get("MonMapID") is not None
    ]
    player_vitals = [
        ActorVitals(
            actor_id=f"p:{u.get('uoName')}",
            hp=_maybe_int(u.get("intHP")),
            hp_max=_maybe_int(u.get("intHPMax")),
            mp=_maybe_int(u.get("intMP")),
            mp_max=_maybe_int(u.get("intMPMax")),
            state=_maybe_int(u.get("intState")),
        )
        for u in _as_list(o.get("uoBranch"))
        if isinstance(u, dict) and u.get("uoName")
    ]
    actors = monster_vitals + player_vitals
    if actors:
        events.append(VitalsEvent(ts=0.0, actors=actors, kind="monster_spawn"))

    return events


def _vitals(actor_id: str, v: dict) -> ActorVitals:
    return ActorVitals(
        actor_id=actor_id,
        hp=_maybe_int(v.get("intHP")),
        mp=_maybe_int(v.get("intMP")),
        state=_maybe_int(v.get("intState")),
    )


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _maybe_int(value) -> int | None:
    return int(value) if isinstance(value, (int, float)) else None
