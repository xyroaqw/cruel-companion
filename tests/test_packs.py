import pytest

from companion.rules.packs import load_boss_packs

VALID_PACK = """
boss: Ultra Testboss
cues:
  - id: red_glow
    hsv_lower: [170, 130, 160]
    hsv_upper: [10, 255, 255]
    min_coverage_pct: 2.0
    region: [0.1, 0.2, 0.9, 0.95]
rules:
  - id: dodge
    when:
      visual_cue: red_glow
    then:
      alert: "Move!"
      level: critical
    fire_once_per_threshold_crossing: true
"""


def write_pack(bosses_dir, name, text):
    bosses_dir.mkdir(parents=True, exist_ok=True)
    (bosses_dir / name).write_text(text, encoding="utf-8")


def test_missing_dir_yields_no_packs(tmp_path):
    assert load_boss_packs(tmp_path / "nope") == []


def test_pack_ids_are_namespaced_by_filename(tmp_path):
    write_pack(tmp_path, "ultra_testboss.yaml", VALID_PACK)

    (pack,) = load_boss_packs(tmp_path)
    assert pack.name == "Ultra Testboss"
    assert [c.id for c in pack.cues] == ["ultra_testboss:red_glow"]
    (trigger,) = pack.triggers
    assert trigger.id == "ultra_testboss:dodge"
    # Bare cue reference inside the pack is rewritten to the namespaced id.
    assert trigger.when.visual_cue == "ultra_testboss:red_glow"


def test_cue_profile_fields_parsed(tmp_path):
    write_pack(tmp_path, "ultra_testboss.yaml", VALID_PACK)
    (pack,) = load_boss_packs(tmp_path)
    (cue,) = pack.cues
    assert cue.hsv_lower == (170, 130, 160)
    assert cue.hsv_upper == (10, 255, 255)
    assert cue.min_coverage_pct == 2.0
    assert cue.region == (0.1, 0.2, 0.9, 0.95)


def test_template_files_are_skipped(tmp_path):
    write_pack(tmp_path, "_TEMPLATE.yaml", VALID_PACK)
    assert load_boss_packs(tmp_path) == []


def test_same_ids_in_two_packs_do_not_collide(tmp_path):
    write_pack(tmp_path, "boss_a.yaml", VALID_PACK)
    write_pack(tmp_path, "boss_b.yaml", VALID_PACK)

    packs = load_boss_packs(tmp_path)
    assert {p.triggers[0].id for p in packs} == {"boss_a:dodge", "boss_b:dodge"}


def test_cross_pack_cue_reference_is_left_untouched(tmp_path):
    other = """
rules:
  - id: borrow
    when:
      visual_cue: "boss_a:red_glow"
    then:
      alert: "Shared cue"
"""
    write_pack(tmp_path, "boss_a.yaml", VALID_PACK)
    write_pack(tmp_path, "boss_b.yaml", other)

    packs = load_boss_packs(tmp_path)
    borrow = next(t for p in packs for t in p.triggers if t.id == "boss_b:borrow")
    assert borrow.when.visual_cue == "boss_a:red_glow"


def test_unknown_bare_cue_reference_fails(tmp_path):
    bad = """
rules:
  - id: dangling
    when:
      visual_cue: not_defined_here
    then:
      alert: "?"
"""
    write_pack(tmp_path, "boss_a.yaml", bad)
    with pytest.raises(ValueError, match="unknown cue"):
        load_boss_packs(tmp_path)


def test_bad_hsv_shape_fails(tmp_path):
    bad = """
cues:
  - id: broken
    hsv_lower: [170, 130]
    hsv_upper: [10, 255, 255]
"""
    write_pack(tmp_path, "boss_a.yaml", bad)
    with pytest.raises(ValueError, match="3-item list"):
        load_boss_packs(tmp_path)


def test_out_of_range_hsv_fails(tmp_path):
    bad = """
cues:
  - id: broken
    hsv_lower: [200, 130, 160]
    hsv_upper: [10, 255, 255]
"""
    write_pack(tmp_path, "boss_a.yaml", bad)
    with pytest.raises(ValueError, match="out of range"):
        load_boss_packs(tmp_path)
