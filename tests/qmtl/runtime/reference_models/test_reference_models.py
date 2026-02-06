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


def test_activation_updated_accepts_shadow_and_augmented_fields():
    evt = ActivationUpdated(
        type="activation_updated",
        version=2,
        world_id="w-shadow",
        effective_mode="shadow",
        execution_domain="shadow",
        compute_context={"world_id": "w-shadow", "execution_domain": "shadow"},
        phase="frozen",
        requires_ack=True,
        sequence=7,
    )

    assert evt.type == "activation_updated"
    assert evt.effective_mode == "shadow"
    assert evt.execution_domain == "shadow"
    assert evt.compute_context == {
        "world_id": "w-shadow",
        "execution_domain": "shadow",
    }
    assert evt.phase == "frozen"
    assert evt.requires_ack is True
    assert evt.sequence == 7
