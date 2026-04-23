from __future__ import annotations

import pytest
from fastapi import FastAPI
import httpx

from qmtl.services.worldservice.core_loop_hub import (
    CoreLoopHub,
    deep_merge_mappings,
    derive_metrics_from_risk_snapshot,
)
from qmtl.services.worldservice.risk_hub import RiskSignalHub
from qmtl.services.worldservice.routers.risk_hub import create_risk_hub_router


def test_derive_metrics_from_risk_snapshot_builds_live_metrics_and_risk_context() -> None:
    snapshot = {
        "version": "v1",
        "provenance": {"stage": "paper"},
        "weights": {"s2": 1.0},
        "covariance": {"s1,s1": 0.04, "s2,s2": 0.01, "s1,s2": 0.005},
        "realized_returns": {"s1": [0.01, -0.005, 0.003, 0.0]},
        "stress": {"s1": {"max_loss": -0.2}},
    }

    derived = derive_metrics_from_risk_snapshot(
        snapshot,
        strategy_id="s1",
        stage="paper",
    )

    assert derived is not None
    assert derived["returns"]["sharpe"] is not None
    assert derived["sample"]["effective_history_years"] == pytest.approx(4 / 252.0)
    assert derived["stress"]["max_loss"] == -0.2
    assert derived["risk"]["incremental_var_99"] is not None
    diagnostics = derived["diagnostics"]
    assert diagnostics["live_returns"] == [0.01, -0.005, 0.003, 0.0]
    assert diagnostics["extra_metrics"]["risk_hub_snapshot_version"] == "v1"


def test_derive_metrics_from_risk_snapshot_keeps_backtest_to_diagnostics_only() -> None:
    derived = derive_metrics_from_risk_snapshot(
        {
            "version": "v1",
            "provenance": {"stage": "backtest"},
            "realized_returns": {"s1": [0.01, -0.005]},
        },
        strategy_id="s1",
        stage="backtest",
    )

    assert derived is not None
    assert "returns" not in derived
    assert derived["diagnostics"]["live_returns_source"] == "risk_hub"
    assert derived["diagnostics"]["extra_metrics"]["risk_hub_snapshot_version"] == "v1"


def test_deep_merge_mappings_merges_nested_metrics() -> None:
    merged = deep_merge_mappings(
        {"returns": {"sharpe": 1.0}, "diagnostics": {"source": "runs"}},
        {"returns": {"max_drawdown": 0.2}, "diagnostics": {"live_returns_source": "risk_hub"}},
    )

    assert merged == {
        "returns": {"sharpe": 1.0, "max_drawdown": 0.2},
        "diagnostics": {"source": "runs", "live_returns_source": "risk_hub"},
    }


@pytest.mark.asyncio
async def test_core_loop_hub_dispatches_snapshot_update_to_bus_and_scheduler() -> None:
    events: list[tuple[str, str, dict[str, object]]] = []
    scheduled: list[str] = []

    class _Bus:
        async def publish_risk_snapshot_updated(self, world_id: str, payload: dict[str, object]) -> None:
            events.append(("risk_snapshot_updated", world_id, payload))

    async def _schedule(world_id: str) -> None:
        scheduled.append(world_id)

    hub = CoreLoopHub(bus=_Bus(), schedule_extended_validation=_schedule)
    snapshot = {"world_id": "w1", "version": "v1", "weights": {"s1": 1.0}}

    await hub.handle_risk_snapshot_update("w1", snapshot)

    assert events == [("risk_snapshot_updated", "w1", snapshot)]
    assert scheduled == ["w1"]


@pytest.mark.asyncio
async def test_risk_hub_router_dedupes_without_retriggering_core_loop_hub() -> None:
    events: list[tuple[str, str, dict[str, object]]] = []
    scheduled: list[str] = []

    class _Bus:
        async def publish_risk_snapshot_updated(self, world_id: str, payload: dict[str, object]) -> None:
            events.append(("risk_snapshot_updated", world_id, payload))

    async def _schedule(world_id: str) -> None:
        scheduled.append(world_id)

    app = FastAPI()
    app.include_router(
        create_risk_hub_router(
            RiskSignalHub(),
            core_loop_hub=CoreLoopHub(bus=_Bus(), schedule_extended_validation=_schedule),
        )
    )

    payload = {
        "as_of": "2025-01-01T00:00:00Z",
        "version": "v1",
        "weights": {"s1": 1.0},
    }
    headers = {"X-Actor": "risk", "X-Stage": "paper"}

    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            first = await client.post("/risk-hub/worlds/w1/snapshots", json=payload, headers=headers)
            second = await client.post("/risk-hub/worlds/w1/snapshots", json=payload, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(events) == 1
    assert scheduled == ["w1"]
