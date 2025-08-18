import pytest

from qmtl.sdk import metrics as sdk_metrics
from qmtl.sdk.node import StreamInput, ProcessingNode
from qmtl.sdk.runner import Runner


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
