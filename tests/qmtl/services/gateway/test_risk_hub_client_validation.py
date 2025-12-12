import pytest

from qmtl.services.gateway.risk_hub_client import RiskHubClient
from qmtl.services.worldservice.blob_store import JsonBlobStore


def test_risk_hub_client_validates_weights_and_sets_hash():
    client = RiskHubClient(base_url="http://ws", actor="gateway", stage="paper")
    payload = {
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"s1": 0.6, "s2": 0.4},
    }

    normalized = client._normalize_and_validate("w", payload)  # type: ignore[attr-defined]

    assert normalized["world_id"] == "w"
    assert normalized["ttl_sec"] == client.ttl_sec
    assert normalized["hash"]
    assert normalized["provenance"]["actor"] == "gateway"
    assert normalized["provenance"]["stage"] == "paper"


def test_risk_hub_client_rejects_bad_weights():
    client = RiskHubClient(base_url="http://ws")
    payload = {
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"s1": 0.2, "s2": 0.2},
    }

    with pytest.raises(ValueError):
        client._normalize_and_validate("w", payload)  # type: ignore[attr-defined]


def test_risk_hub_client_offloads_realized_returns_and_stress(tmp_path):
    store = JsonBlobStore(tmp_path / "blobs")
    client = RiskHubClient(
        base_url="http://ws",
        blob_store=store,
        inline_cov_threshold=1,
    )
    payload = {
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"s1": 1.0},
        "realized_returns": {"s1": [0.01, 0.02]},
        "stress": {"crash": {"max_drawdown": 0.2}, "slowdown": {"max_drawdown": 0.1}},
    }

    normalized = client._normalize_and_validate("w", payload)  # type: ignore[attr-defined]
    offloaded = client._maybe_offload_auxiliary(normalized)  # type: ignore[attr-defined]

    assert offloaded.get("realized_returns_ref")
    assert "realized_returns" not in offloaded
    assert offloaded.get("stress_ref")
    assert "stress" not in offloaded
