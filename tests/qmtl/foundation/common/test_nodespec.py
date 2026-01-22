from __future__ import annotations

import copy

import pytest

from qmtl.foundation.common import CanonicalNodeSpec, compute_node_id
from qmtl.foundation.common.nodespec import serialize_nodespec


_NONDETERMINISTIC_ENV_SAMPLE = {
    "AS": "arm64-apple-darwin20.0.0-as",
    "RUST_LOG": "warn",
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "MallocNanoZone": "0",
    "APPLICATIONINSIGHTS_CONFIGURATION_CONTENT": "{}",
    "SDKROOT": "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk",
    "_": "/usr/bin/env",
}


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


def test_serialize_nodespec_rejects_conflicting_schema_ids() -> None:
    payload = {
        "node_type": "LegacyNode",
        "interval": 0,
        "period": 0,
        "config": {"beta": 2},
        "inputs": [],
        "schema_compat_id": "compat",
        "schema_id": "legacy",
        "code_hash": "code",
    }

    with pytest.raises(ValueError, match="must match if both are provided"):
        serialize_nodespec(payload)


def test_compute_node_id_ignores_nondeterministic_params() -> None:
    def _make_payload(extra_params: dict[str, object] | None = None) -> dict[str, object]:
        payload: dict[str, object] = {
            "node_type": "EnvSensitiveNode",
            "interval": 30,
            "period": 5,
            "params": {"alpha": 1},
            "dependencies": ["dep-a"],
            "schema_compat_id": "compat-1",
            "code_hash": "hash-xyz",
        }
        if extra_params:
            merged = dict(payload["params"])
            merged.update(extra_params)
            payload["params"] = merged
        return payload

    base_payload = _make_payload()
    base_node_id = compute_node_id(base_payload)

    nondeterministic_params = {
        "timestamp": "2024-05-01T00:00:00Z",
        "seed": 1234,
        "random_state": {"numpy": 99},
        "ENV": dict(_NONDETERMINISTIC_ENV_SAMPLE),
        "env_extra": "ignored",
        "Env_Path": "/tmp/path",
    }

    payload_with_env = _make_payload(nondeterministic_params)

    assert compute_node_id(payload_with_env) == base_node_id


def test_compute_node_id_ignores_nondeterministic_config() -> None:
    base_payload = {
        "node_type": "ConfigDrivenNode",
        "interval": 10,
        "period": 0,
        "config": {"alpha": 0.2, "beta": [1, 2, 3]},
        "dependencies": ["dep-1"],
        "schema_compat_id": "compat-2",
        "code_hash": "hash-cfg",
    }

    base_id = compute_node_id(base_payload)

    mutated = copy.deepcopy(base_payload)
    mutated_config = dict(mutated["config"])
    mutated_config.update(
        {
            "Seed": 99,
            "TIMESTAMP": "2024-05-01T12:00:00Z",
            "ENV": dict(_NONDETERMINISTIC_ENV_SAMPLE),
            "env_runtime": "ignored",
            "random_state": {"numpy": 123},
        }
    )
    mutated["config"] = mutated_config

    assert compute_node_id(mutated) == base_id


def test_tagquery_node_id_normalizes_query_spec() -> None:
    base_payload = {
        "node_type": "TagQueryNode",
        "interval": 60,
        "period": 0,
        "params": {"tags": ["b", "a"], "match_mode": "any"},
        "dependencies": [],
        "schema_compat_id": "tag-compat",
        "code_hash": "tag-code",
    }
    reordered = copy.deepcopy(base_payload)
    reordered["params"] = {"match_mode": "any", "tags": ["a", "b"]}

    assert compute_node_id(base_payload) == compute_node_id(reordered)

    stricter = copy.deepcopy(base_payload)
    stricter["params"] = {"tags": ["a", "b"], "match_mode": "all"}

    assert compute_node_id(base_payload) != compute_node_id(stricter)


def test_tagquery_node_id_falls_back_to_node_fields() -> None:
    base = {
        "node_type": "TagQueryNode",
        "interval": 60,
        "period": 0,
        "tags": ["x", "y"],
        "match_mode": "all",
        "dependencies": [],
        "schema_compat_id": "tag-compat",
        "code_hash": "tag-code",
    }
    with_params = {
        **base,
        "params": {"tags": ["y", "x"], "match_mode": "all"},
    }

    assert compute_node_id(base) == compute_node_id(with_params)
