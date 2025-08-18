from strategies.nodes.transforms.alpha_performance import alpha_performance_node
import pytest


def test_alpha_performance_metrics():
    returns = [0.1, -0.05, 0.2, -0.1]
    metrics = alpha_performance_node(returns)
    assert metrics["max_drawdown"] == -0.1
    assert metrics["win_ratio"] == 0.5
    assert metrics["profit_factor"] == 2.0
    assert metrics["sharpe"] == pytest.approx(0.31448545, rel=1e-6)
