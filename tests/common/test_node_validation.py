from __future__ import annotations

import pytest

from qmtl.foundation.common import crc32_of_list, enforce_node_identity, validate_node_identity
from qmtl.foundation.common.node_validation import NodeValidationError
from tests.factories import NodeFactory


def test_validate_node_identity_success() -> None:
    factory = NodeFactory()
    node = factory.build()
    checksum = crc32_of_list([node["node_id"]])

    report = validate_node_identity([node], checksum)

    assert report.is_valid
    assert report.checksum_valid
    assert report.node_ids == (node["node_id"],)
    report.raise_for_issues()  # does not raise


def test_validate_node_identity_missing_fields() -> None:
    factory = NodeFactory()
    node = factory.build(schema_hash="")

    report = validate_node_identity([node], 0)

    assert not report.is_valid
    assert report.missing_fields

    with pytest.raises(NodeValidationError) as exc:
        report.raise_for_issues()

    detail = exc.value.detail
    assert detail["code"] == "E_NODE_ID_FIELDS"


def test_enforce_node_identity_checksum_mismatch() -> None:
    factory = NodeFactory()
    node = factory.build()

    with pytest.raises(NodeValidationError) as exc:
        enforce_node_identity([node], 0)

    assert exc.value.code == "E_CHECKSUM_MISMATCH"


def test_enforce_node_identity_detects_mismatched_id() -> None:
    factory = NodeFactory()
    node = factory.build()
    node["node_id"] = "not-matching"

    checksum = crc32_of_list([node["node_id"]])

    with pytest.raises(NodeValidationError) as exc:
        enforce_node_identity([node], checksum)

    assert exc.value.code == "E_NODE_ID_MISMATCH"
