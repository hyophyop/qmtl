from __future__ import annotations

import pytest

from qmtl.services.gateway.submission.node_identity import NodeIdentityValidator
from tests.qmtl.runtime.sdk.factories import NodeFactory, node_ids_crc32


_GATEWAY_ENV_SAMPLE = {
    "AS": "arm64-apple-darwin20.0.0-as",
    "RUST_LOG": "warn",
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "MallocNanoZone": "0",
    "APPLICATIONINSIGHTS_CONFIGURATION_CONTENT": "{}",
    "SDKROOT": "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk",
    "_": "/usr/bin/env",
}


@pytest.fixture()
def node_factory() -> NodeFactory:
    return NodeFactory()


def test_validate_accepts_matching_ids(node_factory: NodeFactory) -> None:
    validator = NodeIdentityValidator()
    node = node_factory.build()
    dag = {"nodes": [node]}
    validator.validate(dag, node_ids_crc32([node]))


def test_validate_missing_fields_raises(node_factory: NodeFactory) -> None:
    validator = NodeIdentityValidator()
    node = node_factory.build(assign_id=False, schema_hash="", schema_compat_id="")
    node["node_id"] = "abc"
    dag = {"nodes": [node]}

    with pytest.raises(Exception) as exc:
        validator.validate(dag, node_ids_crc32([node]))

    detail = exc.value.detail  # type: ignore[attr-defined]
    assert detail["code"] == "E_NODE_ID_FIELDS"


def test_validate_crc_mismatch_raises(node_factory: NodeFactory) -> None:
    validator = NodeIdentityValidator()
    node = node_factory.build()
    dag = {"nodes": [node]}

    with pytest.raises(Exception) as exc:
        validator.validate(dag, 0)

    detail = exc.value.detail  # type: ignore[attr-defined]
    assert detail["code"] == "E_CHECKSUM_MISMATCH"


def test_validate_detects_mismatch(node_factory: NodeFactory) -> None:
    validator = NodeIdentityValidator()
    node = node_factory.build(assign_id=False)
    node["node_id"] = "not-matching"
    dag = {"nodes": [node]}
    with pytest.raises(Exception) as exc:
        validator.validate(dag, node_ids_crc32([node]))

    detail = exc.value.detail  # type: ignore[attr-defined]
    assert detail["code"] == "E_NODE_ID_MISMATCH"


def test_validate_ignores_nondeterministic_params(node_factory: NodeFactory) -> None:
    validator = NodeIdentityValidator()
    node = node_factory.build()

    mutated = {**node}
    mutated_params = dict(node["params"])
    mutated_params.update(
        {
            "timestamp": "2024-05-01T00:00:00Z",
            "seed": 1234,
            "random_state": {"numpy": 99},
            "ENV": dict(_GATEWAY_ENV_SAMPLE),
            "env_extra": "ignored",
        }
    )
    mutated["params"] = mutated_params

    dag = {"nodes": [mutated]}

    # The CRC is computed from ``node_id`` values and remains unchanged because
    # canonicalisation ignores the injected non-deterministic fields.
    report = validator.validate(dag, node_ids_crc32([mutated]))

    assert report.is_valid
