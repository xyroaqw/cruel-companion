"""Resolves actor tokens (e.g. "m:8421", "p:1103") to display names, with a disk cache that
persists across sessions so most actors are already known from prior play.
"""

import json
import os
import time
from pathlib import Path

from companion.protocol.events import IdentityHintEvent


class IdentityResolver:
    def __init__(self, cache_path: Path, min_save_interval: float = 5.0):
        self._cache_path = Path(cache_path)
        self._map: dict[str, str] = {}
        self._dirty = False
        self._last_save = 0.0
        self._min_save_interval = min_save_interval
        self.load()

    def load(self) -> None:
        if not self._cache_path.exists():
            return
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        if isinstance(data, dict):
            self._map = {str(k): str(v) for k, v in data.items()}

    def save(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._cache_path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(self._map, indent=2), encoding="utf-8")
        os.replace(tmp_path, self._cache_path)
        self._dirty = False
        self._last_save = time.monotonic()

    def maybe_save(self) -> None:
        if self._dirty and (time.monotonic() - self._last_save) >= self._min_save_interval:
            self.save()

    def observe(self, hint: IdentityHintEvent) -> None:
        if self._map.get(hint.actor_id) != hint.display_name:
            self._map[hint.actor_id] = hint.display_name
            self._dirty = True

    def resolve(self, actor_id: str) -> str:
        return self._map.get(actor_id, actor_id)
