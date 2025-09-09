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
    nodes = list(ns)
    # pretrade
    out = Runner.feed_queue_data(nodes[0], signal.node_id, 1, 0, order)
    assert out == order
    # sizing
    out = Runner.feed_queue_data(nodes[1], nodes[0].node_id, 1, 0, out)
    assert out == order
    # execution
    out = Runner.feed_queue_data(nodes[2], nodes[1].node_id, 1, 0, out)
    assert out == order
    # fills
    out = Runner.feed_queue_data(nodes[3], nodes[2].node_id, 1, 0, out)
    assert out == order
    # portfolio
    out = Runner.feed_queue_data(nodes[4], nodes[3].node_id, 1, 0, out)
    assert out == order
    # risk
    out = Runner.feed_queue_data(nodes[5], nodes[4].node_id, 1, 0, out)
    assert out == order
    # timing
    out = Runner.feed_queue_data(nodes[6], nodes[5].node_id, 1, 0, out)
    assert out == order
