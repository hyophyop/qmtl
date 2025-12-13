from __future__ import annotations

import math

import pytest

from qmtl.runtime.sdk.submit import StrategyMetrics, _evaluate_with_worldservice
from qmtl.runtime.sdk.world_validation_metrics import (
    build_v1_evaluation_metrics,
    deflated_sharpe_ratio,
    gain_to_pain_ratio,
    time_under_water_ratio,
)


GOOD_RETURNS = [0.01, 0.02, -0.005, 0.015, 0.012, 0.008, -0.003, 0.02, 0.01, 0.005]


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return False


def test_gain_to_pain_ratio_returns_none_without_losses():
    assert gain_to_pain_ratio([0.01, 0.02]) is None


def test_time_under_water_ratio_in_range():
    ratio = time_under_water_ratio(GOOD_RETURNS)
    assert ratio is not None
    assert 0.0 <= ratio <= 1.0


def test_deflated_sharpe_ratio_probability_range():
    metrics = build_v1_evaluation_metrics(GOOD_RETURNS)
    sharpe = metrics["returns"]["sharpe"]
    assert isinstance(sharpe, (int, float))
    prob = deflated_sharpe_ratio(GOOD_RETURNS, sharpe=float(sharpe), trials=1)
    assert prob is not None
    assert 0.0 <= prob <= 1.0


def test_build_v1_evaluation_metrics_no_nan_or_inf():
    metrics = build_v1_evaluation_metrics(GOOD_RETURNS)
    for section in ("returns", "sample", "robustness"):
        slot = metrics.get(section) or {}
        assert isinstance(slot, dict)
        for value in slot.values():
            if value is None:
                continue
            assert _is_finite_number(value)


class CapturingGatewayClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def evaluate_strategy(
        self,
        *,
        gateway_url: str,
        world_id: str,
        strategy_id: str,
        metrics: dict,
        returns: list[float],
        policy_payload=None,
        evaluation_run_id=None,
        stage=None,
        risk_tier=None,
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
        return {
            "active": [],
            "weights": {},
            "violations": [],
            "evaluation_run_id": evaluation_run_id,
            "evaluation_run_url": f"/worlds/{world_id}/strategies/{strategy_id}/runs/{evaluation_run_id}",
        }


@pytest.mark.asyncio
async def test_ws_evaluate_payload_includes_v1_core_metrics():
    client = CapturingGatewayClient()
    result = await _evaluate_with_worldservice(
        gateway_url="http://gw",
        world_id="world-1",
        strategy_id="strategy-1",
        metrics=StrategyMetrics(sharpe=1.0, max_drawdown=-0.1, win_rate=0.5),
        returns=GOOD_RETURNS,
        preset=None,
        client=client,
        evaluation_run_id="eval-1",
        stage="backtest",
        risk_tier="low",
    )
    assert result.error is None
    assert client.calls, "expected evaluate_strategy to be invoked"
    payload = client.calls[0]["metrics"]
    assert isinstance(payload, dict)

    def _path_value(section: str, name: str):
        slot = payload.get(section)
        assert isinstance(slot, dict)
        return slot.get(name)

    assert _path_value("returns", "sharpe") is not None
    assert _path_value("returns", "max_drawdown") is not None
    assert _path_value("returns", "gain_to_pain_ratio") is not None
    assert _path_value("returns", "time_under_water_ratio") is not None

    assert _path_value("sample", "effective_history_years") is not None
    assert _path_value("sample", "n_trades_total") is not None
    assert _path_value("sample", "n_trades_per_year") is not None

    assert _path_value("robustness", "deflated_sharpe_ratio") is not None
    assert _path_value("robustness", "sharpe_first_half") is not None
    assert _path_value("robustness", "sharpe_second_half") is not None

