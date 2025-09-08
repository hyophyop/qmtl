from __future__ import annotations

from qmtl.sdk.node import Node
from qmtl.sdk.runner import Runner
from qmtl.pipeline.micro_batch import MicroBatchNode


def test_micro_batch_aggregates_same_timestamp():
    src = Node(name="src", interval=1, period=4)
    mb = MicroBatchNode(src)
    # Feed three payloads in the same bucket (t=0), and one in next bucket
    # No flush until the next bucket arrives
    out = Runner.feed_queue_data(mb, src.node_id, 1, 0, {"id": 1})
    assert out is None
    out = Runner.feed_queue_data(mb, src.node_id, 1, 0, {"id": 2})
    assert out is None
    out = Runner.feed_queue_data(mb, src.node_id, 1, 0, {"id": 3})
    assert out is None
    # New bucket t=1 flushes batch for t=0
    out = Runner.feed_queue_data(mb, src.node_id, 1, 1, {"id": 4})
    assert out == [{"id": 1}, {"id": 2}, {"id": 3}]
    # Next bucket t=2 flushes t=1 batch
    out = Runner.feed_queue_data(mb, src.node_id, 1, 2, {"id": 5})
    assert out == [{"id": 4}]
