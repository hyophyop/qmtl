from __future__ import annotations

from datetime import datetime, timezone

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.runner import Runner
from qmtl.runtime.sdk.timing_controls import TimingController

from qmtl.runtime.pipeline.execution_nodes.timing import TimingGateNode


def test_timing_gate_node_blocks_closed_market() -> None:
    src = Node(name="src", interval=1, period=1)
    controller = TimingController(require_regular_hours=True)
    node = TimingGateNode(src, controller=controller)
    order = {"symbol": "AAPL", "price": 10.0, "quantity": 1.0}
    saturday = int(datetime(2024, 1, 6, 15, 0, tzinfo=timezone.utc).timestamp())
    out = Runner.feed_queue_data(node, src.node_id, 1, saturday, order)
    assert out["rejected"]
