from qmtl.runtime.sdk.cache_view import CacheView
from qmtl.runtime.sdk.node import Node

from qmtl.runtime.transforms.equity_linearity import (
    equity_linearity_from_history_node,
    equity_linearity_v2_from_history_node,
)
from qmtl.runtime.transforms.linearity_metrics import (
    equity_linearity_metrics,
    equity_linearity_metrics_v2,
)


def _history_node(name: str = "history", interval: int = 60) -> Node:
    return Node(
        compute_fn=lambda view: view,
        name=name,
        interval=interval,
        period=interval,
    )


def _cache_view_for(node: Node, series):
    data = {node.node_id: {node.interval: [(0, series)]}}
    return CacheView(data)


def test_equity_linearity_from_history_node_wraps_metrics():
    history = _history_node()
    wrapper = equity_linearity_from_history_node(history, eps=0.0)
    view = _cache_view_for(history, [0.0, 1.0, 2.0])

    result = wrapper.compute_fn(view)
    assert result == equity_linearity_metrics([0.0, 1.0, 2.0], eps=0.0)
    assert wrapper.interval == history.interval
    assert wrapper.period == history.period


def test_equity_linearity_node_returns_none_for_empty_history():
    history = _history_node()
    wrapper = equity_linearity_from_history_node(history)
    empty_view = CacheView({history.node_id: {history.interval: None}})

    assert wrapper.compute_fn(empty_view) is None


def test_equity_linearity_v2_wrapper_passes_orientation():
    history = _history_node("down_history")
    wrapper = equity_linearity_v2_from_history_node(
        history,
        orientation="down",
        eps=1e-9,
    )
    downward = [5.0, 4.0, 3.0, 2.0]
    view = _cache_view_for(history, downward)

    result = wrapper.compute_fn(view)
    expected = equity_linearity_metrics_v2(downward, orientation="down", eps=1e-9)
    assert result == expected
    assert result["score"] > 0.5
