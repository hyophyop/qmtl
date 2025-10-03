from __future__ import annotations

import pytest

from qmtl.services.gateway.submission.node_identity import NodeIdentityValidator
from tests.qmtl.runtime.sdk.factories import NodeFactory, node_ids_crc32


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
