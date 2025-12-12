from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from pytest import approx

from qmtl.foundation.common.metrics_factory import get_metric_value
from qmtl.services.worldservice.api import create_app
from qmtl.services.worldservice import metrics
from qmtl.services.worldservice.storage import Storage


def test_allocation_snapshot_ratio_reflects_counter_values() -> None:
    metrics.reset_metrics()
    world_id = "world-1"

    metrics.record_allocation_snapshot(world_id, stale=False)

    assert get_metric_value(
        metrics.world_allocation_snapshot_total, {"world_id": world_id}
    ) == 1.0
    assert (
        get_metric_value(
            metrics.world_allocation_snapshot_stale_total, {"world_id": world_id}
        )
        == 0.0
    )
    assert get_metric_value(
        metrics.world_allocation_snapshot_stale_ratio, {"world_id": world_id}
    ) == approx(0.0)

    metrics.record_allocation_snapshot(world_id, stale=True)

    assert get_metric_value(
        metrics.world_allocation_snapshot_total, {"world_id": world_id}
    ) == 2.0
    assert (
        get_metric_value(
            metrics.world_allocation_snapshot_stale_total, {"world_id": world_id}
        )
        == 1.0
    )
    assert get_metric_value(
        metrics.world_allocation_snapshot_stale_ratio, {"world_id": world_id}
    ) == approx(0.5)


def test_parse_timestamp_supports_z_suffix() -> None:
    ts = metrics.parse_timestamp("2025-01-01T00:00:00Z")
    assert ts == datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


def test_parse_timestamp_normalizes_timezone_offsets() -> None:
    ts = metrics.parse_timestamp("2025-01-01T09:00:00+09:00")
    assert ts == datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_metrics_endpoint_exports_risk_hub_snapshot_metrics() -> None:
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            resp = await client.get("/metrics")
            assert resp.status_code == 200
            payload = resp.text

    assert "risk_hub_snapshot_lag_seconds" in payload
    assert "risk_hub_snapshot_missing_total" in payload
    assert "risk_hub_snapshot_dedupe_total" in payload
    assert "risk_hub_snapshot_expired_total" in payload
    assert "risk_hub_snapshot_retry_total" in payload
    assert "risk_hub_snapshot_dlq_total" in payload
