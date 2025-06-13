import pytest
from qmtl.sdk.node import Node

@pytest.mark.parametrize(
    "interval,period",
    [
        (None, 1),
        (1, None),
        (0, 1),
        (1, 0),
        (-1, 1),
        (1, -1),
    ],
)
def test_invalid_node_parameters(interval, period):
    with pytest.raises(ValueError):
        Node(interval=interval, period=period)


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
        Node(compute_fn=fn, interval=1, period=1)
