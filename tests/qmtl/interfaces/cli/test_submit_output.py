from __future__ import annotations

import json

from qmtl.interfaces.cli import submit as cli_submit
from qmtl.runtime.sdk import Mode
from qmtl.runtime.sdk.submit import PrecheckResult, StrategyMetrics, SubmitResult
from qmtl.services.worldservice.shared_schemas import ActivationEnvelope, DecisionEnvelope


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


def test_cli_emits_json_with_ws_and_precheck_sections(capsys):
    decision = DecisionEnvelope(
        world_id="w-json",
        policy_version=1,
        effective_mode="validate",
        reason="stub",
        as_of="2025-01-01T00:00:00Z",
        ttl="60s",
        etag="etag-1",
    )
    activation = ActivationEnvelope(
        world_id="w-json",
        strategy_id="s-json",
        side="long",
        active=True,
        weight=0.25,
        etag="etag-2",
        run_id="run-1",
        ts="2025-01-01T00:00:01Z",
    )
    result = SubmitResult(
        strategy_id="s-json",
        status="active",
        world="w-json",
        mode=Mode.BACKTEST,
        contribution=0.05,
        weight=0.25,
        rank=1,
        metrics=StrategyMetrics(sharpe=2.0, max_drawdown=0.05),
        decision=decision,
        activation=activation,
        threshold_violations=[{"metric": "sharpe", "threshold_type": "min", "threshold_value": 1.0}],
        precheck=PrecheckResult(
            status="passed",
            metrics=StrategyMetrics(sharpe=1.5, max_drawdown=0.1),
            violations=[],
        ),
    )

    cli_submit._emit_submission_result(result, output_format="json")
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert payload["ws"]["decision"]["world_id"] == "w-json"
    assert payload["ws"]["decision"]["ttl"] == "60s"
    assert payload["ws"]["decision"]["reason"] == "stub"
    assert payload["ws"]["activation"]["strategy_id"] == "s-json"
    assert payload["ws"]["threshold_violations"][0]["metric"] == "sharpe"
    assert payload["precheck"]["status"] == "passed"


def test_allocation_guidance_uses_plan_file_hint(capsys):
    cli_submit._print_allocation_guidance("demo-world")

    output = capsys.readouterr().out

    assert "qmtl world apply demo-world --run-id <id> [--plan-file plan.json]" in output
