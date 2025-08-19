from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.node import Node
import pytest
import qmtl.sdk.runner as runner_module

from qmtl.transforms import AlphaPerformanceNode


def test_alpha_performance_node_triggers_postprocess(monkeypatch):
    history = Node(name="alpha_hist", interval="1s", period=4)
    perf_node = AlphaPerformanceNode(history)

    returns = [0.1, -0.05, 0.2, -0.1]
    view = CacheView({history.node_id: {1: [(0, returns)]}})
    metrics = perf_node.compute_fn(view)

    captured: dict[str, dict] = {}
    monkeypatch.setattr(
        runner_module.Runner,
        "_handle_alpha_performance",
        lambda result: captured.setdefault("result", result),
    )
    runner_module.Runner._postprocess_result(perf_node, metrics)

    assert metrics["max_drawdown"] == -0.1
    assert metrics["win_ratio"] == 0.5
    assert metrics["profit_factor"] == 2.0
    assert metrics["sharpe"] == pytest.approx(0.31448545, rel=1e-6)
    assert metrics["car_mdd"] == pytest.approx(1.286, rel=1e-6)
    assert metrics["rar_mdd"] == pytest.approx(3.14485451, rel=1e-6)
    assert captured["result"] == metrics

