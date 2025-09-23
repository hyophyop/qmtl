from qmtl.runtime.reference_models import ActivationEnvelope, ActivationUpdated


def test_activation_models_validate_fields():
    env = ActivationEnvelope(
        world_id="w1",
        strategy_id="s1",
        side="long",
        active=True,
        weight=1.0,
        etag="e1",
        ts="2025-01-01T00:00:00Z",
    )
    assert env.active and env.weight == 1.0

    evt = ActivationUpdated(
        version=1,
        world_id="w1",
        side="long",
        active=True,
        weight=1.0,
        etag="e1",
        ts="2025-01-01T00:00:00Z",
    )
    assert evt.type == "ActivationUpdated"

