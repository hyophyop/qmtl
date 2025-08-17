import pytest

from qmtl.indicators import volatility_node
from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.node import SourceNode


@pytest.mark.parametrize(
    "window,expected",
    [
        (2, 1.0606601718),
        (3, 0.8660254038),
        (4, 0.8660254038),
    ],
)
def test_volatility_node(window: int, expected: float) -> None:
    src = SourceNode(interval="1s", period=5)
    node = volatility_node(src, window=window)
    values = [1, 2, 1, 2, 1]
    data = {src.node_id: {1: list(enumerate(values))}}
    view = CacheView(data)
    result = node.compute_fn(view)
    assert result == pytest.approx(expected, rel=1e-9)
