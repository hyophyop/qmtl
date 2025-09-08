from __future__ import annotations

from qmtl.sdk.node import Node
from qmtl.sdk.runner import Runner
from qmtl.nodesets.base import NodeSetBuilder
from qmtl.nodesets.testkit import attach_minimal, fake_fill_webhook


def test_nodeset_testkit_attach():
    sig = Node(name="sig", interval=1, period=1)
    ns = attach_minimal(NodeSetBuilder(), sig, world_id="w1")
    order = {"symbol": "AAPL", "price": 10.0, "quantity": 1.0}
    out = Runner.feed_queue_data(ns.pretrade, sig.node_id, 1, 0, order)
    assert out == order


def test_fake_fill_webhook_shape():
    evt = fake_fill_webhook("AAPL", 1.0, 10.0)
    assert evt["specversion"] == "1.0" and evt["type"] == "trade.fill"
    assert evt["data"]["symbol"] == "AAPL" and evt["data"]["fill_price"] == 10.0

