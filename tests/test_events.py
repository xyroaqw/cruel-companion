from companion.protocol.events import ActorVitals


def test_hp_pct_normal():
    assert ActorVitals(actor_id="m:1", hp=25, hp_max=100).hp_pct == 25.0


def test_hp_pct_none_when_hp_missing():
    assert ActorVitals(actor_id="m:1", hp_max=100).hp_pct is None


def test_hp_pct_none_when_max_missing():
    assert ActorVitals(actor_id="m:1", hp=25).hp_pct is None


def test_hp_pct_none_when_max_zero():
    assert ActorVitals(actor_id="m:1", hp=25, hp_max=0).hp_pct is None
