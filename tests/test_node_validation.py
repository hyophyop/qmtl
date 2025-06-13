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
