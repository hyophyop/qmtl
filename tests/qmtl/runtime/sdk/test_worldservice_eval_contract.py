import pytest

from qmtl.runtime.sdk.submit import StrategyMetrics, _evaluate_with_worldservice


class _DummyGatewayClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.response: dict[str, object] = {"active": []}

    async def evaluate_strategy(
        self,
        *,
        gateway_url: str,
        world_id: str,
        strategy_id: str,
        metrics: dict,
        returns: list[float],
        policy_payload: dict | None,
        evaluation_run_id: str | None,
        stage: str | None,
        risk_tier: str | None,
    ) -> dict:
        self.calls.append(
            {
                "gateway_url": gateway_url,
                "world_id": world_id,
                "strategy_id": strategy_id,
                "metrics": metrics,
                "returns": returns,
                "policy_payload": policy_payload,
                "evaluation_run_id": evaluation_run_id,
                "stage": stage,
                "risk_tier": risk_tier,
            }
        )
        return dict(self.response)


@pytest.mark.asyncio
async def test_evaluate_with_worldservice_uses_gateway_client_and_includes_risk_metrics():
    client = _DummyGatewayClient()
    client.response = {"active": ["s1"], "evaluation_run_id": "run-1"}
    metrics = StrategyMetrics(adv_utilization_p95=0.12, participation_rate_p95=0.34)

    result = await _evaluate_with_worldservice(
        gateway_url="http://gw",
        world_id="w",
        strategy_id="s1",
        metrics=metrics,
        returns=[0.01, -0.02, 0.03],
        preset=None,
        client=client,  # type: ignore[arg-type]
        evaluation_run_id="run-1",
        stage="paper",
        risk_tier="high",
    )

    assert result.error is None
    assert result.evaluation_run_id == "run-1"
    assert client.calls
    call = client.calls[0]
    payload_metrics = call["metrics"]
    assert payload_metrics["risk"]["adv_utilization_p95"] == 0.12
    assert payload_metrics["risk"]["participation_rate_p95"] == 0.34
    assert call["stage"] == "paper"
    assert call["risk_tier"] == "high"


@pytest.mark.asyncio
async def test_evaluate_with_worldservice_maps_gateway_error_to_ws_eval_error():
    client = _DummyGatewayClient()
    client.response = {"error": "boom"}

    result = await _evaluate_with_worldservice(
        gateway_url="http://gw",
        world_id="w",
        strategy_id="s1",
        metrics=StrategyMetrics(),
        returns=[0.01, 0.02],
        preset=None,
        client=client,  # type: ignore[arg-type]
        evaluation_run_id="run-err",
        stage=None,
        risk_tier=None,
    )

    assert result.error == "boom"
    assert result.evaluation_run_id == "run-err"
