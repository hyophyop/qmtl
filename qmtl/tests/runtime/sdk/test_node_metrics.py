import pytest

from qmtl.runtime.sdk import metrics as sdk_metrics
from qmtl.runtime.sdk.node import StreamInput, ProcessingNode
from qmtl.runtime.sdk.runner import Runner


def test_node_metrics_increment():
    sdk_metrics.reset_metrics()
    src = StreamInput(interval="60s", period=1)
    node = ProcessingNode(
        input=src, compute_fn=lambda view: None, name="n", interval="60s", period=1
    )
    Runner.feed_queue_data(node, src.node_id, 60, 60, {"v": 1})
    assert sdk_metrics.node_processed_total._vals[node.node_id] == 1
    assert len(sdk_metrics.node_process_duration_ms._vals[node.node_id]) == 1
    assert node.node_id not in sdk_metrics.node_process_failure_total._vals


def test_node_metrics_failure():
    sdk_metrics.reset_metrics()
    src = StreamInput(interval="60s", period=1)

    def boom(_):
        raise RuntimeError("boom")

    node = ProcessingNode(input=src, compute_fn=boom, name="n", interval="60s", period=1)
    with pytest.raises(RuntimeError):
        Runner.feed_queue_data(node, src.node_id, 60, 60, {"v": 1})
    assert sdk_metrics.node_processed_total._vals[node.node_id] == 1
    assert sdk_metrics.node_process_failure_total._vals[node.node_id] == 1


def test_cross_context_cache_hit_counter_normalises_missing_labels():
    sdk_metrics.reset_metrics()
    node_id = "node-a"
    sdk_metrics.observe_cross_context_cache_hit(
        node_id,
        world_id="world-a",
        execution_domain="live",
        as_of=None,
        partition=None,
    )
    key = ("node-a", "world-a", "live", "__unset__", "__unset__")
    assert sdk_metrics.cross_context_cache_hit_total._vals[key] == 1  # type: ignore[attr-defined]

    sdk_metrics.observe_cross_context_cache_hit(
        node_id,
        world_id="world-a",
        execution_domain="backtest",
        as_of="2024-01-01",
        partition="tenant-1",
    )
    key_bt = ("node-a", "world-a", "backtest", "2024-01-01", "tenant-1")
    assert sdk_metrics.cross_context_cache_hit_total._vals[key_bt] == 1  # type: ignore[attr-defined]
