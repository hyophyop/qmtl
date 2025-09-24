from __future__ import annotations

from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.portfolio import Portfolio
from qmtl.runtime.sdk.runner import Runner
from qmtl.runtime.sdk.risk_management import RiskManager

from qmtl.runtime.pipeline.execution_nodes.risk import RiskControlNode


def test_risk_control_node_rejects_large_position() -> None:
    src = Node(name="src", interval=1, period=1)
    portfolio = Portfolio(cash=1000.0)
    risk = RiskManager(max_position_size=50.0)
    node = RiskControlNode(src, portfolio=portfolio, risk_manager=risk)
    order = {"symbol": "AAPL", "price": 10.0, "quantity": 10.0}
    out = Runner.feed_queue_data(node, src.node_id, 1, 0, order)
    assert out["rejected"]
