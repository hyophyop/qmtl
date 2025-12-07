from __future__ import annotations

from copy import deepcopy

import pytest
from blake3 import blake3

from qmtl.foundation.common import (
    CanonicalNodeSpec,
    NodeValidationError,
    crc32_of_list,
    compute_node_id,
    enforce_node_identity,
)
from qmtl.foundation.common.nodeid import hash_blake3


_DEF_BASE_NODE = {
    "node_type": "CanonicalNode",
    "interval": 60,
    "period": 0,
    "params": {
        "alpha": 1.0,
        "beta": 2.0,
        "nested": {"k1": "v1", "k2": [1, 2, 3]},
    },
    "dependencies": ["dep-a", "dep-b"],
    "schema_compat_id": "schema/v1",
    "code_hash": "code-abc",
}


@pytest.fixture(name="base_node")
def fixture_base_node() -> dict[str, object]:
    return deepcopy(_DEF_BASE_NODE)


def test_nodeid_param_canonicalization_invariance(base_node: dict[str, object]) -> None:
    reordered = deepcopy(base_node)
    reordered["params"] = {
        "nested": {"k2": [1, 2, 3], "k1": "v1"},
        "beta": 2.0,
        "alpha": 1.0,
    }

    base_id = compute_node_id(base_node)
    reordered_id = compute_node_id(reordered)

    assert reordered_id == base_id

    spec = (
        CanonicalNodeSpec()
        .with_node_type(base_node["node_type"])
        .with_interval(base_node["interval"])
        .with_period(base_node["period"])
        .with_params(base_node["params"])
        .with_dependencies(base_node["dependencies"])
        .with_schema_compat_id(base_node["schema_compat_id"])
        .with_code_hash(base_node["code_hash"])
    )

    payload_from_spec = spec.to_payload()
    payload_from_spec["params"] = {
        "beta": 2.0,
        "nested": {"k1": "v1", "k2": [1, 2, 3]},
        "alpha": 1.0,
    }

    assert compute_node_id(payload_from_spec) == base_id


def test_nodeid_dependency_sorting(base_node: dict[str, object]) -> None:
    reversed_deps = deepcopy(base_node)
    reversed_deps["dependencies"] = ["dep-b", "dep-a"]

    base_id = compute_node_id(base_node)
    reversed_id = compute_node_id(reversed_deps)

    assert reversed_id == base_id


def test_nodeid_schema_compat_boundary(base_node: dict[str, object]) -> None:
    minor_update = deepcopy(base_node)
    minor_update["schema_hash"] = "schema-hash-v1.1"

    major_update = deepcopy(base_node)
    major_update["schema_compat_id"] = "schema/v2"
    major_update["schema_hash"] = "schema-hash-v2"

    base_id = compute_node_id(base_node)
    minor_id = compute_node_id(minor_update)
    major_id = compute_node_id(major_update)

    assert minor_id == base_id
    assert major_id != base_id


def test_nodeid_excludes_non_deterministic_fields(base_node: dict[str, object]) -> None:
    with_metadata = deepcopy(base_node)
    with_metadata["metadata"] = {
        "created_at": "2025-10-09T12:00:00Z",
        "random_seed": 42,
    }
    with_metadata["params"] = deepcopy(base_node["params"])
    with_metadata["params"]["timestamp"] = "2025-10-09T12:00:00Z"
    with_metadata["params"]["env_MODE"] = "test"

    base_id = compute_node_id(base_node)
    metadata_id = compute_node_id(with_metadata)

    assert metadata_id == base_id


def test_nodeid_blake3_prefix_enforced() -> None:
    node = {
        **_DEF_BASE_NODE,
        "node_id": "sha256:abcdef",
        "config_hash": "cfg",
        "schema_hash": "schema",
    }

    with pytest.raises(NodeValidationError) as excinfo:
        enforce_node_identity([node], crc32_of_list([node["node_id"]]))

    detail = excinfo.value.detail
    assert detail["code"] == "E_NODE_ID_MISMATCH"
    expected = detail["node_id_mismatch"][0]["expected"]
    assert expected.startswith("blake3:")


def test_hash_blake3_collision_extension() -> None:
    payload = b"canonical-node-spec"
    base_id = hash_blake3(payload)

    existing = {base_id}

    def expected(counter: int) -> str:
        hasher = blake3()
        hasher.update(payload)
        hasher.update(b"|collision:")
        hasher.update(str(counter).encode())
        return f"blake3:{hasher.digest(length=64).hex()}"

    first = hash_blake3(payload, existing_ids=existing)
    assert first == expected(1)
    assert len(first) > len(base_id)

    existing.add(first)
    second = hash_blake3(payload, existing_ids=existing)

    assert second == expected(2)
    assert second not in existing
