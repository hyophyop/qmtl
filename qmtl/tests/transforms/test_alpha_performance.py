import math

from qmtl.transforms import (
    alpha_performance_node,
    alpha_performance_from_history_node,
    AlphaPerformanceNode,
)
from qmtl.sdk.node import SourceNode
from qmtl.sdk.cache_view import CacheView


def test_alpha_performance_metrics():
    returns = [0.1, -0.05, 0.2, -0.1, 0.05]
    metrics = alpha_performance_node(returns)
    assert math.isclose(metrics["sharpe"], 0.37463432463267754)
    assert math.isclose(metrics["max_drawdown"], -0.1)
    assert math.isclose(metrics["car_mdd"], 1.850299999999998)


def test_alpha_performance_node_wrappers():
    returns = [0.1, -0.05, 0.2]
    history = SourceNode(interval="1s", period=1)
    func_node = alpha_performance_from_history_node(history)
    class_node = AlphaPerformanceNode(history)
    view = CacheView({history.node_id: {1: [(0, returns)]}})
    expected = alpha_performance_node(returns)
    assert func_node.compute_fn(view) == expected
    assert class_node.compute_fn(view) == expected
