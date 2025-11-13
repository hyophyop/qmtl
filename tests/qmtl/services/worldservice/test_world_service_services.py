from __future__ import annotations

import pytest

from qmtl.services.worldservice.policy_engine import Policy, ThresholdRule
from qmtl.services.worldservice.schemas import (
    AllocationUpsertRequest,
    PositionSliceModel,
    StrategySeries,
    EvaluateRequest,
)
from qmtl.services.worldservice.services import WorldService
from qmtl.services.worldservice.storage.facade import Storage


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


class _RecorderExecutor:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def execute(self, payload):  # pragma: no cover - interface contract exercised via tests
        self.calls.append(payload)
        return {"status": "ok"}


@pytest.mark.asyncio
async def test_upsert_allocations_executes_pending_existing_plan():
    store = Storage()
    executor = _RecorderExecutor()
    service = WorldService(store=store, rebalance_executor=executor)

    payload = AllocationUpsertRequest(
        run_id="alloc-existing",
        total_equity=1_000.0,
        world_allocations={"w1": 1.0},
        positions=[
            PositionSliceModel(
                world_id="w1",
                strategy_id="s1",
                symbol="BTCUSDT",
                qty=1.0,
                mark=50_000.0,
            )
        ],
        execute=True,
    )

    etag = service._hash_allocation_payload(payload)
    await store.record_allocation_run(
        payload.run_id,
        etag,
        {"plan": {"schema_version": 1, "per_world": {}, "global_deltas": []}},
        executed=False,
    )

    response = await service.upsert_allocations(payload)

    assert response.executed is True
    assert executor.calls and executor.calls[0]["world_allocations"] == {"w1": 1.0}
    assert store.allocation_runs[payload.run_id].executed is True
