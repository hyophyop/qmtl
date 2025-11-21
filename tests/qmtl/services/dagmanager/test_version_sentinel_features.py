import pytest

from qmtl.foundation.common.metrics_factory import get_mapping_store
from qmtl.services.dagmanager.models import DiffRequest
from qmtl.services.dagmanager import metrics

from .diff_helpers import build_dag, dag_node


def _queue_key(node_id: str) -> str:
    """Helper to build the queue partition key used in diff responses."""

    # ``DiffService`` uses ``partition_key`` with default interval/bucket values
    # when no explicit overrides are present on the node definition.
    from qmtl.services.dagmanager.kafka_admin import partition_key, compute_key

    ck = compute_key(node_id)
    return partition_key(node_id, None, None, compute_key=ck)


def test_canary_weight_inferred_from_meta(diff_service, diff_metrics):
    """Traffic weights embedded in DAG meta should emit sentinel events."""

    dag_json = build_dag(
        [dag_node("alpha", code_hash="c1", schema_hash="s1")],
        meta={
            "version": "release-2025.10",
            "traffic_weight": 0.25,
        },
    )

    request = DiffRequest(
        strategy_id="strategy",
        dag_json=dag_json,
        world_id="world-main",
    )

    chunk = diff_service.diff(request)
    events = diff_service.consume_weight_events()

    assert chunk.version == "release-2025.10"
    assert len(events) == 1
    event = events[0]
    assert event.sentinel_id == "strategy-sentinel"
    assert event.sentinel_version == "release-2025.10"
    assert event.weight == pytest.approx(0.25)
    assert event.world_id == "world-main"
    weight_store = get_mapping_store(metrics.dagmanager_active_version_weight, dict)
    assert weight_store["release-2025.10"] == pytest.approx(0.25)


def test_sentinel_weight_cache_is_world_scoped(diff_service):
    """Weights are cached per world so canary cohorts remain deterministic."""

    dag_json = build_dag(
        [
            dag_node("alpha", code_hash="c1", schema_hash="s1"),
            {
                "node_id": "sentinel",
                "node_type": "VersionSentinel",
                "version": "release-2025.10",
                "weight": 0.6,
            },
        ]
    )

    main_request = DiffRequest(
        strategy_id="strategy",
        dag_json=dag_json,
        world_id="world-main",
    )
    shadow_request = DiffRequest(
        strategy_id="strategy",
        dag_json=dag_json,
        world_id="world-shadow",
    )

    diff_service.diff(main_request)
    events_main = diff_service.consume_weight_events()
    assert len(events_main) == 1
    assert events_main[0].world_id == "world-main"

    diff_service.diff(shadow_request)
    events_shadow = diff_service.consume_weight_events()
    assert len(events_shadow) == 1
    assert events_shadow[0].world_id == "world-shadow"

    diff_service.diff(shadow_request)
    assert diff_service.consume_weight_events() == []


def test_queue_topics_reuse_across_version_bumps(diff_service, fake_queue):
    """Existing queues are reused when only the sentinel version changes."""

    dag_v1 = build_dag(
        [dag_node("alpha", code_hash="c1", schema_hash="s1")],
        meta={"version": "release-2025.10"},
    )
    dag_v2 = build_dag(
        [dag_node("alpha", code_hash="c1", schema_hash="s1")],
        meta={"version": "release-2025.11"},
    )

    first_chunk = diff_service.diff(
        DiffRequest(strategy_id="strategy", dag_json=dag_v1)
    )
    first_queue = first_chunk.queue_map[_queue_key("alpha")]
    assert fake_queue.calls[-1][3] == "release-2025.10"

    second_chunk = diff_service.diff(
        DiffRequest(strategy_id="strategy", dag_json=dag_v2)
    )
    second_queue = second_chunk.queue_map[_queue_key("alpha")]

    assert second_queue == first_queue
    assert len(fake_queue.calls) == 1
