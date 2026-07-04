import companion.identity.resolver as resolver_mod
from companion.identity.resolver import IdentityResolver
from companion.protocol.events import IdentityHintEvent


def test_resolve_unknown_falls_back_to_raw_token(tmp_path):
    resolver = IdentityResolver(tmp_path / "identities.json")
    assert resolver.resolve("m:999") == "m:999"


def test_observe_then_resolve_returns_display_name(tmp_path):
    resolver = IdentityResolver(tmp_path / "identities.json")
    resolver.observe(IdentityHintEvent(ts=0.0, actor_id="m:1", display_name="Sepulchure"))
    assert resolver.resolve("m:1") == "Sepulchure"


def test_load_missing_file_starts_empty(tmp_path):
    resolver = IdentityResolver(tmp_path / "does_not_exist.json")
    assert resolver.resolve("m:1") == "m:1"


def test_load_corrupt_file_starts_empty(tmp_path):
    path = tmp_path / "identities.json"
    path.write_text("not valid json{{{", encoding="utf-8")
    resolver = IdentityResolver(path)
    assert resolver.resolve("m:1") == "m:1"


def test_save_and_reload_round_trip(tmp_path):
    path = tmp_path / "identities.json"
    resolver = IdentityResolver(path)
    resolver.observe(IdentityHintEvent(ts=0.0, actor_id="p:1103", display_name="PlayerName"))
    resolver.save()

    reloaded = IdentityResolver(path)
    assert reloaded.resolve("p:1103") == "PlayerName"


def test_maybe_save_respects_min_interval(tmp_path, monkeypatch):
    fake_time = [0.0]
    monkeypatch.setattr(resolver_mod.time, "monotonic", lambda: fake_time[0])

    path = tmp_path / "identities.json"
    resolver = IdentityResolver(path, min_save_interval=5.0)
    resolver.observe(IdentityHintEvent(ts=0.0, actor_id="m:1", display_name="Boss"))

    fake_time[0] = 1.0
    resolver.maybe_save()
    assert not path.exists()  # too soon, should not have saved yet

    fake_time[0] = 6.0
    resolver.maybe_save()
    assert path.exists()


def test_observe_same_value_does_not_mark_dirty(tmp_path, monkeypatch):
    fake_time = [0.0]
    monkeypatch.setattr(resolver_mod.time, "monotonic", lambda: fake_time[0])

    path = tmp_path / "identities.json"
    resolver = IdentityResolver(path, min_save_interval=5.0)
    resolver.observe(IdentityHintEvent(ts=0.0, actor_id="m:1", display_name="Boss"))
    resolver.save()

    resolver.observe(IdentityHintEvent(ts=0.0, actor_id="m:1", display_name="Boss"))
    fake_time[0] = 100.0
    assert resolver._dirty is False
