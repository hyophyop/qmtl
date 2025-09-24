from __future__ import annotations

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.portfolio import Portfolio
from qmtl.runtime.sdk.runner import Runner

from qmtl.runtime.pipeline.execution_nodes.sizing import SizingNode


def test_sizing_node_converts_value_to_quantity() -> None:
    src = Node(name="src", interval=1, period=1)
    portfolio = Portfolio(cash=1000)
    node = SizingNode(src, portfolio=portfolio)
    order = {"symbol": "AAPL", "price": 10.0, "value": 100.0}
    out = Runner.feed_queue_data(node, src.node_id, 1, 0, order)
    assert out["quantity"] == 10
