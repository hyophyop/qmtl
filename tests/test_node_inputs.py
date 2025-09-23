import pytest
from qmtl.runtime.sdk import ProcessingNode, StreamInput


def test_processing_node_accepts_list_or_node():
    s1 = StreamInput(interval="60s", period=1)
    node = ProcessingNode(input=s1, compute_fn=lambda v: None, name="n", interval="60s", period=1)
    assert node.inputs == [s1]
    s2 = StreamInput(interval="60s", period=1)
    node2 = ProcessingNode(input=[s1, s2], compute_fn=lambda v: None, name="n2", interval="60s", period=1)
    assert node2.inputs == [s1, s2]


def test_processing_node_rejects_dict():
    s1 = StreamInput(interval="60s", period=1)
    s2 = StreamInput(interval="60s", period=1)
    with pytest.raises(TypeError):
        ProcessingNode(input={"a": s1, "b": s2}, compute_fn=lambda v: None, name="n", interval="60s", period=1)
