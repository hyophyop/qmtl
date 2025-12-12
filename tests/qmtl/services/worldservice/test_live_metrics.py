from qmtl.services.worldservice.live_metrics import aggregate_live_metrics


def test_aggregate_live_metrics_computes_basic_stats():
    returns = [0.01, -0.005, 0.02, 0.0, -0.01]

    metrics = aggregate_live_metrics(returns, windows=(3, 5), backtest_sharpe=1.0)

    assert "live_sharpe_p3" in metrics
    assert "live_max_drawdown_p3" in metrics
    assert metrics.get("live_sharpe") == metrics.get("live_sharpe_p3")
    assert metrics.get("live_max_drawdown") == metrics.get("live_max_drawdown_p3")
    assert metrics["live_sharpe_p3"] is not None
    assert metrics["live_max_drawdown_p5"] is not None
    # decay is optional when sharpe is missing or zero
    assert "live_vs_backtest_sharpe_ratio" not in metrics or metrics["live_vs_backtest_sharpe_ratio"] is not None
