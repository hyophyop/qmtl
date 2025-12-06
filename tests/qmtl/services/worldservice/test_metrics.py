from __future__ import annotations

from pytest import approx

from qmtl.foundation.common.metrics_factory import get_metric_value
from qmtl.services.worldservice import metrics


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

