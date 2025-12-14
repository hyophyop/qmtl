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

        if path == "/worlds/w/evaluate":
            assert json_body is not None
            assert "metrics" not in json_body
            return 200, {"active": ["s1"], "evaluation_run_id": "camp-w-s1-backtest-20250101"}

        raise AssertionError(f"unexpected request: {method} {path} params={params} json={json_body}")


def test_campaign_executor_executes_evaluate_without_client_metrics() -> None:
    exe = FakeCampaignExecutor()
    cfg = CampaignRunConfig(world_id="w", strategy_id="s1", execute=True, execute_evaluate=True)

    tick, results = exe.execute_tick(cfg)

    assert tick["actions"][0]["action"] == "evaluate"
    assert results and results[0].ok is True
    assert results[0].skipped is False

    # Ensure the executor does not attempt to build metrics client-side.
    evaluate_calls = [c for c in exe.calls if c[0] == "POST" and c[1] == "/worlds/w/evaluate"]
    assert len(evaluate_calls) == 1
    _, _, _, body = evaluate_calls[0]
    assert body is not None
    assert "metrics" not in body
    assert body.get("strategy_id") == "s1"
    assert body.get("stage") == "backtest"
    assert body.get("risk_tier") == "low"
    assert body.get("run_id") == "camp-w-s1-backtest-20250101"


def test_campaign_executor_skips_evaluate_when_execute_evaluate_disabled() -> None:
    exe = FakeCampaignExecutor()
    cfg = CampaignRunConfig(world_id="w", strategy_id="s1", execute=True, execute_evaluate=False)

    _, results = exe.execute_tick(cfg)

    assert results and results[0].skipped is True
    assert results[0].reason == "execute_evaluate_disabled"
    assert not [c for c in exe.calls if c[0] == "POST" and c[1] == "/worlds/w/evaluate"]


def test_campaign_executor_gates_evaluate_cohort_when_execute_evaluate_disabled() -> None:
    class CohortTickExecutor(FakeCampaignExecutor):
        def _request(self, method: str, path: str, *, params=None, json_body=None):
            if path == "/worlds/w/campaign/tick":
                return (
                    200,
                    {
                        "actions": [
                            {
                                "action": "evaluate_cohort",
                                "stage": "backtest",
                                "suggested_method": "POST",
                                "suggested_endpoint": "/worlds/w/evaluate-cohort",
                                "suggested_body": {
                                    "campaign_id": "c1",
                                    "run_id": "cohort-run",
                                    "candidates": ["s1"],
                                    "stage": "backtest",
                                    "risk_tier": "low",
                                },
                            }
                        ]
                    },
                )
            if path == "/worlds/w/evaluate-cohort":
                raise AssertionError("evaluate-cohort should be gated when execute_evaluate is disabled")
            return super()._request(method, path, params=params, json_body=json_body)

    exe = CohortTickExecutor()
    cfg = CampaignRunConfig(world_id="w", execute=True, execute_evaluate=False)

    _, results = exe.execute_tick(cfg)

    assert results and results[0].skipped is True
    assert results[0].reason == "execute_evaluate_disabled"
