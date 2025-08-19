from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.node import Node
import pytest

from strategies.nodes.transforms.alpha_performance import (
    alpha_performance_from_history_node,
)


def test_alpha_performance_from_history_node():
    history = Node(name="alpha_hist", interval="1s", period=4)
    perf = alpha_performance_from_history_node(history)

    returns = [0.1, -0.05, 0.2, -0.1]
    view = CacheView({history.node_id: {1: [(0, returns)]}})
    metrics = perf.compute_fn(view)

    assert metrics["max_drawdown"] == -0.1
    assert metrics["win_ratio"] == 0.5
    assert metrics["profit_factor"] == 2.0
    assert metrics["sharpe"] == pytest.approx(0.31448545, rel=1e-6)

