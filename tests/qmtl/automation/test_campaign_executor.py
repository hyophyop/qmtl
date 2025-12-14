from __future__ import annotations

from typing import Any

from qmtl.automation.campaign_executor import CampaignExecutor, CampaignRunConfig


class FakeCampaignExecutor(CampaignExecutor):
    def __init__(self) -> None:
        super().__init__(base_url="http://example.invalid")
        self.calls: list[tuple[str, str, dict[str, Any] | None, dict[str, Any] | None]] = []

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int | float | bool] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> tuple[int, Any]:
        self.calls.append((method, path, params, dict(json_body) if json_body is not None else None))

        if path == "/worlds/w/campaign/tick":
            return (
                200,
                {
                    "actions": [
                        {
                            "action": "evaluate",
                            "strategy_id": "s1",
                            "stage": "backtest",
                            "suggested_method": "POST",
                            "suggested_endpoint": "/worlds/w/evaluate",
                            "suggested_body": {
                                "strategy_id": "s1",
                                "stage": "backtest",
                                "risk_tier": "low",
                                "run_id": "camp-w-s1-backtest-20250101",
                            },
                        }
                    ]
                },
            )

        if path == "/worlds/w/strategies/s1/runs":
            return (
                200,
                [
                    {
                        "world_id": "w",
                        "strategy_id": "s1",
                        "run_id": "eval-prev",
                        "stage": "backtest",
                        "status": "evaluated",
                        "created_at": "2025-01-01T00:00:00Z",
                        "updated_at": "2025-01-01T00:00:10Z",
                    }
                ],
            )

        if path == "/worlds/w/strategies/s1/runs/eval-prev/metrics":
            return (
                200,
                {
                    "metrics": {
                        "returns": {"sharpe": 1.2, "max_drawdown": 0.1},
                        "sample": {"effective_history_years": 0.5},
                    }
                },
            )

        if path == "/worlds/w/evaluate":
            return 200, {"active": ["s1"], "evaluation_run_id": "camp-w-s1-backtest-20250101"}

        raise AssertionError(f"unexpected request: {method} {path} params={params} json={json_body}")


def test_campaign_executor_executes_evaluate_with_sourced_metrics() -> None:
    exe = FakeCampaignExecutor()
    cfg = CampaignRunConfig(world_id="w", strategy_id="s1", execute=True, execute_evaluate=True)

    tick, results = exe.execute_tick(cfg)

    assert tick["actions"][0]["action"] == "evaluate"
    assert results and results[0].ok is True
    assert results[0].skipped is False

    # Ensure the evaluate call includes metrics keyed by strategy_id.
    evaluate_calls = [c for c in exe.calls if c[0] == "POST" and c[1] == "/worlds/w/evaluate"]
    assert len(evaluate_calls) == 1
    _, _, _, body = evaluate_calls[0]
    assert body is not None
    metrics = body.get("metrics")
    assert isinstance(metrics, dict)
    assert metrics.get("s1", {}).get("returns", {}).get("sharpe") == 1.2


def test_campaign_executor_skips_evaluate_when_no_metrics_source() -> None:
    class NoMetricsExecutor(FakeCampaignExecutor):
        def _request(self, method: str, path: str, *, params=None, json_body=None):
            if path == "/worlds/w/strategies/s1/runs":
                return 200, []
            return super()._request(method, path, params=params, json_body=json_body)

    exe = NoMetricsExecutor()
    cfg = CampaignRunConfig(world_id="w", strategy_id="s1", execute=True, execute_evaluate=True)

    _, results = exe.execute_tick(cfg)

    assert results and results[0].skipped is True
    assert results[0].reason == "missing_metrics_source"
