"""Normalized event types: the shared vocabulary between the capture layers (packet sniffer
in companion/capture + screen watcher in companion/vision) and everything downstream (state
tracking, rules, overlay). Nothing outside companion/protocol/ should need to know what a raw
AQW packet looks like, and nothing outside companion/vision/ should need to know what a pixel
looks like.
"""

from dataclasses import dataclass, field
from typing import Literal, Union

ActorKind = Literal["player_state", "combat_tick", "monster_spawn"]


@dataclass(frozen=True)
class ActorVitals:
    actor_id: str
    hp: int | None = None
    hp_max: int | None = None
    mp: int | None = None
    mp_max: int | None = None
    shield: int | None = None
    state: int | None = None  # 0=Dead, 1=Alive, 2=InCombat (player-side only)

    @property
    def hp_pct(self) -> float | None:
        if self.hp is None or not self.hp_max:
            return None
        return 100.0 * self.hp / self.hp_max


@dataclass(frozen=True)
class VitalsEvent:
    ts: float
    actors: list[ActorVitals] = field(default_factory=list)
    kind: ActorKind = "combat_tick"


@dataclass(frozen=True)
class MessageEvent:
    ts: float
    text: str
    caster_id: str | None = None
    target_id: str | None = None
    raw_kind: str = ""


@dataclass(frozen=True)
class ZoneChangeEvent:
    ts: float
    zone_name: str


@dataclass(frozen=True)
class IdentityHintEvent:
    ts: float
    actor_id: str
    display_name: str


@dataclass(frozen=True)
class VisualCueEvent:
    """Emitted by the vision layer when a configured color cue (e.g. a glowing floor
    telegraph) turns on or off. cue_id is namespaced by boss pack: "<pack>:<cue>".
    """

    ts: float
    cue_id: str
    active: bool
    coverage_pct: float = 0.0


NormalizedEvent = Union[
    VitalsEvent, MessageEvent, ZoneChangeEvent, IdentityHintEvent, VisualCueEvent
]
