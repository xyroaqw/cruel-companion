"""Evaluates triggers against the current GameStateSnapshot, with two independent
per-trigger anti-spam mechanisms: edge-detection (fire_once_per_threshold_crossing) and a
plain time-based cooldown (cooldown_seconds).
"""

import time
from dataclasses import dataclass

from companion.rules.schema import AlertLevel, Condition, Trigger
from companion.state.game_state import GameStateSnapshot


@dataclass(frozen=True)
class FiredAlert:
    trigger_id: str
    message: str
    level: AlertLevel
    ts: float


class RulesEngine:
    def __init__(self, triggers: list[Trigger], pack_triggers: list[Trigger] | None = None):
        """triggers come from config/rules.yaml and are replaceable via reload() (the GUI rule
        editor). pack_triggers come from config/bosses/*.yaml and survive reloads -- the editor
        only manages rules.yaml, so a GUI save must not clobber boss-pack rules."""
        self._base_triggers = list(triggers)
        self._pack_triggers = list(pack_triggers or [])
        self._triggers = self._base_triggers + self._pack_triggers
        self._last_fired_at: dict[str, float] = {}
        self._armed: dict[str, bool] = {t.id: True for t in self._triggers}

    def reload(self, triggers: list[Trigger]) -> None:
        """Swaps in an edited base rule set live (no restart needed); boss-pack triggers are
        kept as-is. Cooldown/armed state is kept for rule ids that still exist; new ids start
        fresh."""
        self._base_triggers = list(triggers)
        self._triggers = self._base_triggers + self._pack_triggers
        self._armed = {t.id: self._armed.get(t.id, True) for t in self._triggers}
        self._last_fired_at = {
            t.id: self._last_fired_at.get(t.id, float("-inf")) for t in self._triggers
        }

    def evaluate(self, state: GameStateSnapshot) -> list[FiredAlert]:
        now = time.monotonic()
        fired = []
        for trigger in self._triggers:
            matched = self._condition_holds(trigger.when, state)

            if trigger.fire_once_per_threshold_crossing:
                if matched and self._armed[trigger.id]:
                    fired.append(FiredAlert(trigger.id, trigger.then.alert, trigger.then.level, now))
                    self._armed[trigger.id] = False
                elif not matched:
                    self._armed[trigger.id] = True
            else:
                last = self._last_fired_at.get(trigger.id, float("-inf"))
                if matched and (now - last) >= trigger.cooldown_seconds:
                    fired.append(FiredAlert(trigger.id, trigger.then.alert, trigger.then.level, now))
                    self._last_fired_at[trigger.id] = now
        return fired

    def _condition_holds(self, cond: Condition, state: GameStateSnapshot) -> bool:
        if cond.zone_equals is not None and state.zone != cond.zone_equals:
            return False

        if cond.visual_cue is not None and cond.visual_cue not in state.visual_cues:
            return False

        if cond.message_contains is not None:
            needle = cond.message_contains.lower()
            if not any(needle in msg.lower() for msg in state.recent_messages):
                return False

        if cond.boss_name is not None or cond.hp_pct_below is not None:
            if cond.boss_name is not None:
                actor = state.find_actor_by_name(cond.boss_name)
                targets = [actor] if actor else []
            else:
                targets = state.monsters()

            if not targets:
                return False

            if cond.hp_pct_below is not None and not any(
                a.hp_pct is not None and a.hp_pct < cond.hp_pct_below for a in targets
            ):
                return False

        return True
