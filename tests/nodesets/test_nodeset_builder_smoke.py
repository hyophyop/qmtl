from __future__ import annotations

from qmtl.sdk.node import Node
from qmtl.sdk.runner import Runner
from qmtl.nodesets.base import NodeSetBuilder


def test_nodeset_attach_passes_through():
    # Minimal signal node emitting an order intent
    signal = Node(name="signal", interval=1, period=1)
    builder = NodeSetBuilder()
    ns = builder.attach(signal, world_id="w1")
    # Feed through the chain; each stub passes the payload as-is
    order = {"symbol": "AAPL", "price": 10.0, "quantity": 2.0}
    out = Runner.feed_queue_data(ns.pretrade, signal.node_id, 1, 0, order)
    assert out == order
    out = Runner.feed_queue_data(ns.sizing, ns.pretrade.node_id, 1, 0, out)
    assert out == order
    out = Runner.feed_queue_data(ns.execution, ns.sizing.node_id, 1, 0, out)
    assert out == order
    out = Runner.feed_queue_data(ns.fills, ns.execution.node_id, 1, 0, out)
    assert out == order
    out = Runner.feed_queue_data(ns.portfolio, ns.fills.node_id, 1, 0, out)
    assert out == order
    out = Runner.feed_queue_data(ns.risk, ns.portfolio.node_id, 1, 0, out)
    assert out == order
    out = Runner.feed_queue_data(ns.timing, ns.risk.node_id, 1, 0, out)
    assert out == order
