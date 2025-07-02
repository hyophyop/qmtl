import pytest
from qmtl.sdk.node import SourceNode, ProcessingNode

@pytest.mark.parametrize(
    "interval,period",
    [
        (0, 1),
        (1, 0),
        (-1, 1),
        (1, -1),
    ],
)
def test_invalid_node_parameters(interval, period):
    with pytest.raises(ValueError):
        SourceNode(interval=interval, period=period)


@pytest.mark.parametrize(
    "fn",
    [
        lambda: None,
        lambda a, b: None,
        lambda a, *args: None,
    ],
)
def test_invalid_compute_fn(fn):
    with pytest.raises(TypeError):
        SourceNode(compute_fn=fn, interval=1, period=1)


def test_processing_node_requires_input():
    with pytest.raises(ValueError):
        ProcessingNode(input=None, compute_fn=lambda v: v, interval=1, period=1)
