import pytest
from qmtl.sdk.node import SourceNode


def test_add_tag():
    n = SourceNode(interval="1s", period=1)
    original = n.node_id
    assert n.tags == []

    n.add_tag("a")
    assert n.tags == ["a"]
    assert n.node_id == original

    n.add_tag("b")
    n.add_tag("a")
    assert n.tags == ["a", "b"]
    assert n.node_id == original
    assert n.to_dict()["tags"] == ["a", "b"]
