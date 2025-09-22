from __future__ import annotations

import pytest

from qmtl.gateway.submission.node_identity import NodeIdentityValidator


def _build_node(**overrides):
    base = {
        "node_id": None,
        "node_type": "TagQueryNode",
        "code_hash": "code",
        "config_hash": "config",
        "schema_hash": "schema",
        "schema_compat_id": "compat",
    }
    base.update(overrides)
    return base


def test_validate_accepts_matching_ids() -> None:
    validator = NodeIdentityValidator()
    node = _build_node()
    dag = {"nodes": [node]}
    from qmtl.common import compute_node_id, crc32_of_list

    node_id = compute_node_id(node)
    node["node_id"] = node_id
    validator.validate(dag, crc32_of_list([node_id]))


def test_validate_missing_fields_raises() -> None:
    validator = NodeIdentityValidator()
    node = _build_node(schema_hash="")
    node_id = "abc"
    node["node_id"] = node_id
    dag = {"nodes": [node]}

    with pytest.raises(Exception) as exc:
        validator.validate(dag, 0)

    detail = exc.value.detail  # type: ignore[attr-defined]
    assert detail["code"] == "E_NODE_ID_FIELDS"


def test_validate_crc_mismatch_raises() -> None:
    validator = NodeIdentityValidator()
    node = _build_node()
    dag = {"nodes": [node]}
    from qmtl.common import compute_node_id

    node_id = compute_node_id(node)
    node["node_id"] = node_id

    with pytest.raises(Exception) as exc:
        validator.validate(dag, 0)

    detail = exc.value.detail  # type: ignore[attr-defined]
    assert detail["code"] == "E_CHECKSUM_MISMATCH"


def test_validate_detects_mismatch() -> None:
    validator = NodeIdentityValidator()
    node = _build_node(node_id="not-matching")
    dag = {"nodes": [node]}
    from qmtl.common import crc32_of_list

    with pytest.raises(Exception) as exc:
        validator.validate(dag, crc32_of_list(["not-matching"]))

    detail = exc.value.detail  # type: ignore[attr-defined]
    assert detail["code"] == "E_NODE_ID_MISMATCH"
