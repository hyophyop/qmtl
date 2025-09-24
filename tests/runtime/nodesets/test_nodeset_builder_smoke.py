from __future__ import annotations

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.runner import Runner
from qmtl.runtime.nodesets.base import NodeSetBuilder
from qmtl.runtime.nodesets.options import NodeSetOptions
from qmtl.runtime.nodesets.resources import clear_shared_portfolios


def test_nodeset_attach_passes_through():
    # Minimal signal node emitting an order intent
    signal = Node(name="signal", interval=1, period=1)
    builder = NodeSetBuilder()
    ns = builder.attach(signal, world_id="w1")
    # Feed through the chain; each stub passes the payload as-is
    order = {"symbol": "AAPL", "price": 10.0, "quantity": 2.0}
    nodes = list(ns)
    assert len(nodes) == 8
    # pretrade
    out = Runner.feed_queue_data(nodes[0], signal.node_id, 1, 0, order)
    assert out == order
    # sizing
    out = Runner.feed_queue_data(nodes[1], nodes[0].node_id, 1, 0, out)
    assert out == order
    # execution
    out = Runner.feed_queue_data(nodes[2], nodes[1].node_id, 1, 0, out)
    assert out == order
    # order publish
    out = Runner.feed_queue_data(nodes[3], nodes[2].node_id, 1, 0, out)
    assert out == order
    # fills
    out = Runner.feed_queue_data(nodes[4], nodes[3].node_id, 1, 0, out)
    assert out == order
    # portfolio
    out = Runner.feed_queue_data(nodes[5], nodes[4].node_id, 1, 0, out)
    assert out == order
    # risk
    out = Runner.feed_queue_data(nodes[6], nodes[5].node_id, 1, 0, out)
    assert out == order
    # timing
    out = Runner.feed_queue_data(nodes[7], nodes[6].node_id, 1, 0, out)
    assert out == order


def test_nodeset_builder_world_scope_shares_portfolio():
    clear_shared_portfolios()
    signal1 = Node(name="sig1", interval=1, period=1)
    signal2 = Node(name="sig2", interval=1, period=1)
    builder = NodeSetBuilder(options=NodeSetOptions(portfolio_scope="world"))
    ns1 = builder.attach(signal1, world_id="world", scope="world")
    ns2 = builder.attach(signal2, world_id="world", scope="world")

    sizing1 = list(ns1)[1]
    sizing2 = list(ns2)[1]
    portfolio1 = getattr(sizing1, "portfolio", None)
    portfolio2 = getattr(sizing2, "portfolio", None)

    assert portfolio1 is not None
    assert portfolio1 is portfolio2
    assert getattr(list(ns1)[5], "portfolio", None) is portfolio1
    assert getattr(sizing1, "weight_fn", None) is not None
