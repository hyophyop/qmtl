import pytest

from qmtl.services.worldservice import schemas, shared_schemas


def test_shared_envelopes_reused():
    assert schemas.DecisionEnvelope is shared_schemas.DecisionEnvelope
    assert schemas.ActivationEnvelope is shared_schemas.ActivationEnvelope
    assert schemas.SeamlessArtifactPayload is shared_schemas.SeamlessArtifactPayload


def test_activation_envelope_fields_cover_state_hash():
    fields = set(shared_schemas.ActivationEnvelope.model_fields)
    assert "state_hash" in fields
    assert set(schemas.ActivationEnvelope.model_fields) == fields


def test_evaluate_request_and_series_shared():
    assert schemas.EvaluateRequest is shared_schemas.EvaluateRequest
    assert schemas.StrategySeries is shared_schemas.StrategySeries
    payload = shared_schemas.EvaluateRequest()
    assert payload.metrics == {}


def test_override_schema_requires_metadata_for_approved():
    with pytest.raises(ValueError):
        shared_schemas.EvaluationOverride(status="approved", reason="ok", actor="risk", timestamp=None)

    payload = shared_schemas.EvaluationOverride(
        status="approved",
        reason="ok",
        actor="risk",
        timestamp="2025-01-01T00:00:00Z",
    )
    assert payload.status == "approved"
