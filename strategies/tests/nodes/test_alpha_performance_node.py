from qmtl.transforms import alpha_performance_node
import math
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


def test_alpha_performance_ignores_nan_returns():
    returns = [0.1, float("nan"), -0.05, 0.2]
    metrics = alpha_performance_node(returns)
    assert metrics["max_drawdown"] == -0.05
    assert metrics["win_ratio"] == pytest.approx(2 / 3, rel=1e-6)
    assert metrics["profit_factor"] == pytest.approx(6.0, rel=1e-6)
    assert metrics["sharpe"] == pytest.approx(0.8111071056538126, rel=1e-6)
    assert metrics["car_mdd"] == pytest.approx(5.08, rel=1e-6)
    assert metrics["rar_mdd"] == pytest.approx(16.222142113076252, rel=1e-6)


def test_alpha_performance_all_nan_returns():
    returns = [float("nan"), float("nan")]
    metrics = alpha_performance_node(returns)
    assert metrics == {
        "sharpe": 0.0,
        "max_drawdown": 0.0,
        "win_ratio": 0.0,
        "profit_factor": 0.0,
        "car_mdd": 0.0,
        "rar_mdd": 0.0,
    }


def test_alpha_performance_constant_returns():
    returns = [0.01, 0.01, 0.01]
    metrics = alpha_performance_node(returns)
    assert metrics["sharpe"] == 0.0
    assert metrics["max_drawdown"] == 0.0
    assert metrics["win_ratio"] == 1.0
    assert math.isinf(metrics["profit_factor"])
    assert math.isinf(metrics["car_mdd"])
    assert math.isinf(metrics["rar_mdd"])
