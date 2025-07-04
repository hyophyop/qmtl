import pytest
from qmtl.sdk import ProcessingNode, StreamInput, TagQueryNode


def test_multi_input_serialization_list():
    s1 = StreamInput(interval="60s", period=1)
    s2 = StreamInput(interval="60s", period=1)
    node = ProcessingNode(input=[s1, s2], compute_fn=lambda x: x, name="out", interval="60s", period=1)
    d = node.to_dict()
    assert set(d["inputs"]) == {s1.node_id, s2.node_id}


def test_multi_input_serialization_dict():
    s1 = StreamInput(interval="60s", period=1)
    s2 = StreamInput(interval="60s", period=1)
    with pytest.raises(TypeError):
        ProcessingNode(input={"a": s1, "b": s2}, compute_fn=lambda x: x, name="out", interval="60s", period=1)


def test_multi_input_with_tag_query():
    tq = TagQueryNode(["t"], interval="60s", period=1)
    s = StreamInput(interval="60s", period=1)
    node = ProcessingNode(input=[tq, s], compute_fn=lambda x: x, name="out", interval="60s", period=1)
    d = node.to_dict()
    assert set(d["inputs"]) == {tq.node_id, s.node_id}
