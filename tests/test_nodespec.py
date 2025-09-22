from __future__ import annotations

from qmtl.common import CanonicalNodeSpec, compute_node_id
from qmtl.common.nodespec import serialize_nodespec


def test_canonical_nodespec_serialization_matches_legacy() -> None:
    payload = {
        "node_type": "ExampleNode",
        "interval": 60,
        "period": 0,
        "params": {
            "alpha": 1,
            "nested": {"z": 2, "a": 1},
            "world_id": "ignored",
        },
        "dependencies": ["dep-b", "dep-a"],
        "schema_compat_id": "s-major",
        "code_hash": "code-123",
    }
    spec = (
        CanonicalNodeSpec()
        .with_node_type(payload["node_type"])
        .with_interval(payload["interval"])
        .with_period(payload["period"])
        .with_params(payload["params"])
        .with_dependencies(payload["dependencies"])
        .with_schema_compat_id(payload["schema_compat_id"])
        .with_code_hash(payload["code_hash"])
    )

    assert serialize_nodespec(spec) == serialize_nodespec(payload)


def test_canonical_nodespec_roundtrip_preserves_payload() -> None:
    payload = {
        "node_type": "ProcessingNode",
        "interval": None,
        "period": 5,
        "params": {"alpha": 1},
        "inputs": ["dep-2", "dep-1"],
        "schema_compat_id": "compat",
        "code_hash": "hash",
        "name": "node-name",
        "tags": ["a", "b"],
        "config_hash": "cfg",
        "schema_hash": "schema",
        "pre_warmup": False,
    }

    spec = CanonicalNodeSpec.from_payload(payload)
    roundtrip = spec.to_payload()

    for key in payload:
        assert roundtrip[key] == payload[key]
    assert set(roundtrip["dependencies"]) == {"dep-1", "dep-2"}
    assert roundtrip["interval"] is None
    assert roundtrip["inputs"] == payload["inputs"]


def test_compute_node_id_accepts_builder() -> None:
    payload = {
        "node_type": "LegacyNode",
        "interval": 0,
        "period": 0,
        "config": {"beta": 2},
        "inputs": [],
        "schema_id": "legacy",  # fallback when compat id missing
        "code_hash": "code",
    }

    spec = CanonicalNodeSpec.from_payload(payload)

    assert compute_node_id(spec) == compute_node_id(payload)
