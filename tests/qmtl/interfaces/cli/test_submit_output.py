from __future__ import annotations

from qmtl.interfaces.cli import submit as cli_submit
from qmtl.runtime.sdk import Mode
from qmtl.runtime.sdk.submit import PrecheckResult, StrategyMetrics, SubmitResult


def test_cli_prints_ws_and_precheck_sections(capsys):
    result = SubmitResult(
        strategy_id="s-1",
        status="active",
        world="w-1",
        mode=Mode.PAPER,
        contribution=0.08,
        weight=0.12,
        rank=3,
        threshold_violations=[{"metric": "sharpe", "threshold_type": "min", "threshold_value": 1.0}],
        metrics=StrategyMetrics(sharpe=1.8, max_drawdown=0.12, correlation_avg=0.4),
        precheck=PrecheckResult(
            status="passed",
            weight=0.05,
            rank=9,
            contribution=0.01,
            metrics=StrategyMetrics(sharpe=1.2, max_drawdown=0.2, correlation_avg=0.1),
            violations=[{"metric": "sharpe", "threshold_type": "min", "threshold_value": 1.0, "message": "ok"}],
            improvement_hints=["raise sharpe"],
            correlation_avg=0.1,
        ),
    )

    cli_submit._print_submission_result(result)
    output = capsys.readouterr().out

    assert "WorldService decision (SSOT)" in output
    assert "✅ Strategy activated successfully" in output
    assert "Local pre-check (ValidationPipeline)" in output
    assert "Threshold violations (WS)" in output
    assert "Threshold violations (pre-check)" in output


def test_cli_prints_ws_rejection_and_precheck(capsys):
    result = SubmitResult(
        strategy_id="s-2",
        status="rejected",
        world="w-2",
        mode=Mode.BACKTEST,
        rejection_reason="WorldService evaluation rejected strategy",
        threshold_violations=[{"metric": "corr", "threshold_type": "max", "threshold_value": 0.8, "value": 0.9}],
        improvement_hints=["ws hint"],
        precheck=PrecheckResult(
            status="failed",
            metrics=StrategyMetrics(sharpe=0.5, max_drawdown=0.3),
            violations=[{"metric": "sharpe", "threshold_type": "min", "threshold_value": 1.0, "value": 0.5}],
            improvement_hints=["local hint"],
        ),
    )

    cli_submit._print_submission_result(result)
    output = capsys.readouterr().out

    assert "WorldService decision (SSOT)" in output
    assert "Strategy rejected" in output
    assert "Threshold violations (WS)" in output
    assert "Local pre-check (ValidationPipeline)" in output
    assert "Threshold violations (pre-check)" in output
