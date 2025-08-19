from strategies.nodes.transforms.alpha_performance import alpha_performance_node
import pytest


def test_alpha_performance_metrics():
    returns = [0.1, -0.05, 0.2, -0.1]
    metrics = alpha_performance_node(returns)
    assert metrics["max_drawdown"] == -0.1
    assert metrics["win_ratio"] == 0.5
    assert metrics["profit_factor"] == 2.0
    assert metrics["sharpe"] == pytest.approx(0.31448545, rel=1e-6)
    assert metrics["car_mdd"] == pytest.approx(1.286, rel=1e-6)
    assert metrics["rar_mdd"] == pytest.approx(3.14485451, rel=1e-6)


def test_alpha_performance_with_transaction_cost():
    returns = [0.1, -0.05, 0.2, -0.1]
    metrics = alpha_performance_node(returns, transaction_cost=0.01)
    assert metrics["max_drawdown"] == -0.11
    assert metrics["win_ratio"] == 0.5
    assert metrics["profit_factor"] == pytest.approx(1.64705882, rel=1e-6)
    assert metrics["sharpe"] == pytest.approx(0.23062266, rel=1e-6)
    assert metrics["car_mdd"] == pytest.approx(0.774126, rel=1e-6)
    assert metrics["rar_mdd"] == pytest.approx(2.09656967, rel=1e-6)
