from qmtl.services.worldservice import schemas
from qmtl.services.worldservice import shared_schemas


def test_shared_envelopes_reused():
    assert schemas.DecisionEnvelope is shared_schemas.DecisionEnvelope
    assert schemas.ActivationEnvelope is shared_schemas.ActivationEnvelope
    assert schemas.SeamlessArtifactPayload is shared_schemas.SeamlessArtifactPayload


def test_activation_envelope_fields_cover_state_hash():
    fields = set(shared_schemas.ActivationEnvelope.model_fields)
    assert "state_hash" in fields
    assert set(schemas.ActivationEnvelope.model_fields) == fields
