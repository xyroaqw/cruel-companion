"""Boss packs: one YAML file per boss in config/bosses/, bundling that fight's visual cue
profiles (what to look for on screen) with its alert rules (what to say when seen). Adding
support for a new ultra means dropping in a new file -- no code changes.

Namespacing: every cue id and rule id is prefixed with the pack's filename stem
("ultra_darkon.yaml" -> "ultra_darkon:red_telegraph"), so two packs can both call a cue
"red_telegraph" without colliding. Inside a pack, rules may reference their own cues by bare
name; a cue from another pack must be referenced by its full "pack:cue" form.

Files whose name starts with "_" (e.g. _TEMPLATE.yaml) are skipped.
"""

from dataclasses import dataclass, replace
from pathlib import Path

import yaml

from companion.rules.schema import Trigger, parse_rule_dict
from companion.vision.cues import CueProfile


@dataclass(frozen=True)
class BossPack:
    name: str
    source: Path
    cues: list[CueProfile]
    triggers: list[Trigger]


def load_boss_packs(bosses_dir: Path, strict: bool = True) -> list[BossPack]:
    """strict=True (tests, tooling): first bad pack raises. strict=False (the running app):
    a broken pack is skipped with a console message naming the file and the problem, so one
    user's YAML typo can't take down every other boss's alerts."""
    if not bosses_dir.is_dir():
        return []

    packs = []
    seen_rule_ids: set[str] = set()
    for path in sorted(bosses_dir.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        try:
            pack = _load_pack(path)
            for trigger in pack.triggers:
                if trigger.id in seen_rule_ids:
                    raise ValueError(f"duplicate rule id '{trigger.id}' across boss packs")
        except (ValueError, yaml.YAMLError) as exc:
            if strict:
                raise
            print(f"[packs] SKIPPED {path.name}: {exc}")
            continue
        seen_rule_ids.update(t.id for t in pack.triggers)
        packs.append(pack)
    return packs


def _load_pack(path: Path) -> BossPack:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    namespace = path.stem
    context = f"bosses/{path.name}"

    valid_cue_keys = {"id", "hsv_lower", "hsv_upper", "min_coverage_pct", "region"}
    cues = []
    cue_ids: set[str] = set()
    for i, raw in enumerate(data.get("cues", [])):
        if not isinstance(raw, dict):
            raise ValueError(f"{context} cue #{i} must be a mapping")
        cue_id = raw.get("id")
        if not cue_id:
            raise ValueError(f"{context} cue #{i} is missing required field 'id'")
        unknown = set(raw) - valid_cue_keys
        if unknown:
            raise ValueError(
                f"{context} cue '{cue_id}': unknown field(s) {sorted(unknown)}; "
                f"valid: {sorted(valid_cue_keys)}"
            )
        if cue_id in cue_ids:
            raise ValueError(f"{context} has duplicate cue id '{cue_id}'")
        cue_ids.add(cue_id)

        for field in ("hsv_lower", "hsv_upper"):
            value = raw.get(field)
            if not isinstance(value, list) or len(value) != 3:
                raise ValueError(
                    f"{context} cue '{cue_id}': '{field}' must be a 3-item list [h, s, v]"
                )

        kwargs = {}
        if "min_coverage_pct" in raw:
            kwargs["min_coverage_pct"] = float(raw["min_coverage_pct"])
        if "region" in raw:
            region = raw["region"]
            if not isinstance(region, list) or len(region) != 4:
                raise ValueError(
                    f"{context} cue '{cue_id}': 'region' must be a 4-item list "
                    "[left, top, right, bottom] of window fractions"
                )
            kwargs["region"] = tuple(float(v) for v in region)

        cues.append(
            CueProfile(
                id=f"{namespace}:{cue_id}",
                hsv_lower=tuple(int(v) for v in raw["hsv_lower"]),
                hsv_upper=tuple(int(v) for v in raw["hsv_upper"]),
                **kwargs,
            )
        )

    triggers = []
    for raw in data.get("rules", []):
        trigger = parse_rule_dict(raw, context=context)
        when = trigger.when
        if when.visual_cue is not None and ":" not in when.visual_cue:
            if when.visual_cue not in cue_ids:
                raise ValueError(
                    f"{context} rule '{trigger.id}' references unknown cue "
                    f"'{when.visual_cue}' (not defined in this pack; use 'pack:cue' to "
                    "reference another pack's cue)"
                )
            when = replace(when, visual_cue=f"{namespace}:{when.visual_cue}")
        triggers.append(replace(trigger, id=f"{namespace}:{trigger.id}", when=when))

    return BossPack(
        name=str(data.get("boss", namespace)),
        source=path,
        cues=cues,
        triggers=triggers,
    )
