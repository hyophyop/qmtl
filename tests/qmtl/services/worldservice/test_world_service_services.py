from __future__ import annotations

import pytest

from qmtl.services.worldservice.policy_engine import Policy, ThresholdRule
from qmtl.services.worldservice.schemas import EvaluateRequest, StrategySeries
from qmtl.services.worldservice.services import WorldService


class _StubStore:
    async def get_decisions(self, world_id: str):  # pragma: no cover - interface placeholder
        return []

    async def get_default_policy(self, world_id: str):  # pragma: no cover - interface placeholder
        return None


def test_augment_metrics_with_linearity_enriches_strategy_metrics():
    metrics = {'alpha': {'baseline': 1.0}}
    series = {'alpha': StrategySeries(equity=[0.0, 1.0, 2.0])}

    enriched = WorldService.augment_metrics_with_linearity(metrics, series)

    assert metrics['alpha'] == {'baseline': 1.0}
    assert 'el_v1_score' in enriched['alpha']
    assert 'el_v2_score' in enriched['alpha']


def test_augment_metrics_with_linearity_adds_portfolio_metrics():
    series = {
        'one': StrategySeries(equity=[0.0, 1.0, 2.0]),
        'two': StrategySeries(equity=[0.0, 0.5, 1.0]),
    }

    enriched = WorldService.augment_metrics_with_linearity({}, series)

    for slot in enriched.values():
        assert 'portfolio_el_v1_score' in slot
        assert 'portfolio_el_v2_score' in slot


def test_augment_metrics_with_linearity_records_alpha_performance():
    series = {'alpha': StrategySeries(equity=[0.0, 1.0, 1.5, 2.0])}

    enriched = WorldService.augment_metrics_with_linearity({}, series)

    assert 'alpha_performance.sharpe' in enriched['alpha']
    assert 'alpha_performance.max_drawdown' in enriched['alpha']


@pytest.mark.asyncio
async def test_world_service_evaluate_uses_augmented_metrics():
    service = WorldService(store=_StubStore())
    policy = Policy(
        thresholds={'equity': ThresholdRule(metric='el_v1_score', min=0.5)}
    )
    request = EvaluateRequest(
        metrics={},
        policy=policy,
        series={
            'good': StrategySeries(equity=[0.0, 1.0, 2.0]),
            'bad': StrategySeries(equity=[0.0, -1.0, -2.0]),
        },
    )

    response = await service.evaluate('world', request)

    assert response.active == ['good']
