from __future__ import annotations

import pytest

from qmtl.gateway.submission.node_identity import NodeIdentityValidator
from tests.factories import node_ids_crc32, tag_query_node_payload


def test_validate_accepts_matching_ids() -> None:
    validator = NodeIdentityValidator()
    node = tag_query_node_payload(
        tags=["t"],
        code_hash="code",
        config_hash="config",
        schema_hash="schema",
        schema_compat_id="compat",
    )
    dag = {"nodes": [node]}
    validator.validate(dag, node_ids_crc32([node]))


def test_validate_missing_fields_raises() -> None:
    validator = NodeIdentityValidator()
    node = tag_query_node_payload(
        tags=["t"],
        code_hash="code",
        config_hash="config",
        schema_hash="",
        schema_compat_id="",
        include_node_id=False,
    )
    node["node_id"] = "abc"
    dag = {"nodes": [node]}

    with pytest.raises(Exception) as exc:
        validator.validate(dag, 0)

    detail = exc.value.detail  # type: ignore[attr-defined]
    assert detail["code"] == "E_NODE_ID_FIELDS"


def test_validate_crc_mismatch_raises() -> None:
    validator = NodeIdentityValidator()
    node = tag_query_node_payload(
        tags=["t"],
        code_hash="code",
        config_hash="config",
        schema_hash="schema",
        schema_compat_id="compat",
    )
    dag = {"nodes": [node]}

    with pytest.raises(Exception) as exc:
        validator.validate(dag, 0)

    detail = exc.value.detail  # type: ignore[attr-defined]
    assert detail["code"] == "E_CHECKSUM_MISMATCH"


def test_validate_detects_mismatch() -> None:
    validator = NodeIdentityValidator()
    node = tag_query_node_payload(
        tags=["t"],
        code_hash="code",
        config_hash="config",
        schema_hash="schema",
        schema_compat_id="compat",
        node_id="not-matching",
    )
    dag = {"nodes": [node]}
    with pytest.raises(Exception) as exc:
        validator.validate(dag, node_ids_crc32([node]))

    detail = exc.value.detail  # type: ignore[attr-defined]
    assert detail["code"] == "E_NODE_ID_MISMATCH"
