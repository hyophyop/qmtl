import polars as pl
import pytest

from qmtl.runtime.sdk import SourceNode, NodeValidationError


def test_schema_violation_fail_mode():
    node = SourceNode(interval="1s", period=1, expected_schema={"a": "int64"})
    df = pl.DataFrame({"b": [1]})
    with pytest.raises(NodeValidationError) as exc:
        node.feed("u", 1, 1, df)
    assert "missing columns" in str(exc.value)
    assert node.node_id in str(exc.value)
