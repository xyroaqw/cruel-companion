"""Live game-state tracking: GameState is the single mutable source of truth, built by
applying normalized events (companion/protocol/events.py) -- it never sees raw packets, so it
doesn't depend on protocol/parser.py being finished.
"""

from collections import deque
from dataclasses import dataclass

from companion.identity.resolver import IdentityResolver
from companion.protocol.events import (
    IdentityHintEvent,
    MessageEvent,
    NormalizedEvent,
    VisualCueEvent,
    VitalsEvent,
    ZoneChangeEvent,
)


@dataclass(frozen=True)
class ActorState:
    actor_id: str
    display_name: str
    hp: int | None = None
    hp_max: int | None = None
    mp: int | None = None
    mp_max: int | None = None
    shield: int | None = None

    @property
    def hp_pct(self) -> float | None:
        if self.hp is None or not self.hp_max:
            return None
        return 100.0 * self.hp / self.hp_max

    @property
    def is_monster(self) -> bool:
        return self.actor_id.startswith("m:")


@dataclass(frozen=True)
class GameStateSnapshot:
    zone: str | None
    actors: dict[str, ActorState]
    recent_messages: tuple[str, ...]
    visual_cues: frozenset[str] = frozenset()

    def find_actor_by_name(self, name: str) -> ActorState | None:
        for actor in self.actors.values():
            if actor.display_name == name:
                return actor
        return None

    def monsters(self) -> list[ActorState]:
        return [a for a in self.actors.values() if a.is_monster]


def _coalesce(new_value, old_value):
    return new_value if new_value is not None else old_value


class GameState:
    """Only ever mutated from the GUI-thread side of the queue bridge -- not thread-safe by
    itself, by design (see ui/queue_bridge.py: capture threads only ever push to a queue)."""

    def __init__(self, identity: IdentityResolver, max_recent_messages: int = 20):
        self.zone: str | None = None
        self._actors: dict[str, ActorState] = {}
        self._recent_messages: deque[str] = deque(maxlen=max_recent_messages)
        self._visual_cues: set[str] = set()
        self._identity = identity

    def apply(self, event: NormalizedEvent) -> None:
        if isinstance(event, VitalsEvent):
            self._apply_vitals(event)
        elif isinstance(event, MessageEvent):
            self._apply_message(event)
        elif isinstance(event, ZoneChangeEvent):
            self._apply_zone_change(event)
        elif isinstance(event, IdentityHintEvent):
            self._apply_identity_hint(event)
        elif isinstance(event, VisualCueEvent):
            self._apply_visual_cue(event)

    def get_actor(self, actor_id: str) -> ActorState | None:
        return self._actors.get(actor_id)

    def snapshot(self) -> GameStateSnapshot:
        return GameStateSnapshot(
            zone=self.zone,
            actors=dict(self._actors),
            recent_messages=tuple(self._recent_messages),
            visual_cues=frozenset(self._visual_cues),
        )

    def _apply_vitals(self, event: VitalsEvent) -> None:
        for vitals in event.actors:
            existing = self._actors.get(vitals.actor_id)
            self._actors[vitals.actor_id] = ActorState(
                actor_id=vitals.actor_id,
                display_name=self._identity.resolve(vitals.actor_id),
                hp=_coalesce(vitals.hp, existing.hp if existing else None),
                hp_max=_coalesce(vitals.hp_max, existing.hp_max if existing else None),
                mp=_coalesce(vitals.mp, existing.mp if existing else None),
                mp_max=_coalesce(vitals.mp_max, existing.mp_max if existing else None),
                shield=_coalesce(vitals.shield, existing.shield if existing else None),
            )

    def _apply_message(self, event: MessageEvent) -> None:
        self._recent_messages.append(event.text)

    def _apply_zone_change(self, event: ZoneChangeEvent) -> None:
        self.zone = event.zone_name
        # Monsters don't carry over between rooms; a stale low-HP reading from the last fight
        # could otherwise spuriously match an hp_pct_below rule in the new zone. Players persist.
        self._actors = {aid: a for aid, a in self._actors.items() if not a.is_monster}
        # Telegraph glows don't carry over either -- a cue left "on" at the moment of a zone
        # change would otherwise stay latched until the same cue fired and cleared again.
        self._visual_cues.clear()

    def _apply_visual_cue(self, event: VisualCueEvent) -> None:
        if event.active:
            self._visual_cues.add(event.cue_id)
        else:
            self._visual_cues.discard(event.cue_id)

    def _apply_identity_hint(self, event: IdentityHintEvent) -> None:
        self._identity.observe(event)
        self._identity.maybe_save()
