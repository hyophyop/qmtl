import pytest

from qmtl.services.risk_hub_contract import (
    normalize_and_validate_snapshot,
    stable_snapshot_hash,
)


def test_stable_snapshot_hash_excludes_volatile_fields():
    payload = {
        "world_id": "w",
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"s1": 1.0},
        "created_at": "2025-01-02T00:00:00Z",
        "hash": "old",
    }
    h1 = stable_snapshot_hash(payload)
    payload["created_at"] = "2025-01-03T00:00:00Z"
    payload["hash"] = "new"
    h2 = stable_snapshot_hash(payload)
    assert h1 == h2


def test_normalize_and_validate_snapshot_sets_provenance_and_hash():
    payload = {
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"s1": 1.0},
    }
    out = normalize_and_validate_snapshot(
        "w",
        payload,
        actor="gateway",
        stage="live",
        ttl_sec_default=900,
    )
    assert out["world_id"] == "w"
    assert out["provenance"]["actor"] == "gateway"
    assert out["provenance"]["stage"] == "live"
    assert out["ttl_sec"] == 900
    assert isinstance(out.get("hash"), str) and out["hash"]


def test_normalize_and_validate_snapshot_rejects_bad_weights():
    payload = {
        "world_id": "w",
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"s1": 0.5, "s2": 0.4},
    }
    with pytest.raises(ValueError, match="sum"):
        normalize_and_validate_snapshot("w", payload, actor="gateway", stage="paper")


def test_normalize_and_validate_snapshot_enforces_allowlist():
    payload = {
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"s1": 1.0},
    }
    with pytest.raises(ValueError, match="not allowed"):
        normalize_and_validate_snapshot(
            "w",
            payload,
            actor="evil",
            stage="paper",
            allowed_actors=["gateway"],
        )


def test_normalize_and_validate_snapshot_enforces_payload_actor_allowlist():
    payload = {
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"s1": 1.0},
        "provenance": {"actor": "evil"},
    }
    with pytest.raises(ValueError, match="not allowed"):
        normalize_and_validate_snapshot(
            "w",
            payload,
            stage="paper",
            allowed_actors=["gateway"],
        )


def test_normalize_and_validate_snapshot_requires_actor():
    payload = {
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"s1": 1.0},
        "provenance": {"stage": "paper"},
    }
    with pytest.raises(ValueError, match="actor is required"):
        normalize_and_validate_snapshot("w", payload)


def test_normalize_and_validate_snapshot_requires_stage():
    payload = {
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"s1": 1.0},
        "provenance": {"actor": "gateway"},
    }
    with pytest.raises(ValueError, match="stage is required"):
        normalize_and_validate_snapshot("w", payload)


def test_normalize_and_validate_snapshot_enforces_stage_allowlist():
    payload = {
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"s1": 1.0},
        "provenance": {"actor": "gateway", "stage": "prod"},
    }
    with pytest.raises(ValueError, match="not allowed"):
        normalize_and_validate_snapshot(
            "w",
            payload,
            allowed_stages=["staging"],
        )


def test_normalize_and_validate_snapshot_rejects_header_actor_mismatch():
    payload = {
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"s1": 1.0},
        "provenance": {"actor": "gateway", "stage": "paper"},
    }
    with pytest.raises(ValueError, match="actor mismatch"):
        normalize_and_validate_snapshot(
            "w",
            payload,
            actor="risk-engine",
            stage="paper",
        )


def test_normalize_and_validate_snapshot_rejects_header_stage_mismatch():
    payload = {
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"s1": 1.0},
        "provenance": {"actor": "gateway", "stage": "paper"},
    }
    with pytest.raises(ValueError, match="stage mismatch"):
        normalize_and_validate_snapshot(
            "w",
            payload,
            actor="gateway",
            stage="live",
        )


def test_normalize_and_validate_snapshot_rejects_non_positive_ttl():
    payload = {
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"s1": 1.0},
        "ttl_sec": 0,
        "provenance": {"actor": "gateway", "stage": "paper"},
    }
    with pytest.raises(ValueError, match="ttl_sec must be positive"):
        normalize_and_validate_snapshot("w", payload)


def test_normalize_and_validate_snapshot_rejects_ttl_above_max():
    payload = {
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"s1": 1.0},
        "ttl_sec": 90001,
        "provenance": {"actor": "gateway", "stage": "paper"},
    }
    with pytest.raises(ValueError, match="ttl_sec must be <="):
        normalize_and_validate_snapshot("w", payload, ttl_sec_max=86400)


def test_normalize_and_validate_snapshot_rejects_hash_mismatch():
    payload = {
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"s1": 1.0},
        "hash": "not-a-real-hash",
        "provenance": {"actor": "gateway", "stage": "paper"},
    }
    with pytest.raises(ValueError, match="hash mismatch"):
        normalize_and_validate_snapshot("w", payload)
