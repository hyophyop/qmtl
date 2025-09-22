from __future__ import annotations

from qmtl.sdk.execution_modeling import ExecutionFill
from qmtl.sdk.node import Node
from qmtl.sdk.runner import Runner

from qmtl.pipeline.execution_nodes.execution import ExecutionNode


class DummyExecModel:
    def simulate_execution(self, **kwargs):
        return ExecutionFill(
            order_id=kwargs.get("order_id", "1"),
            symbol=kwargs["symbol"],
            side=kwargs["side"],
            quantity=kwargs["quantity"],
            requested_price=kwargs["requested_price"],
            fill_price=kwargs["requested_price"],
            fill_time=kwargs["timestamp"],
            commission=0.0,
            slippage=0.0,
            market_impact=0.0,
        )


def test_execution_node_simulates_fill() -> None:
    src = Node(name="src", interval=1, period=1)
    exec_model = DummyExecModel()
    node = ExecutionNode(src, execution_model=exec_model)
    order = {"symbol": "AAPL", "price": 10.0, "quantity": 5.0}
    out = Runner.feed_queue_data(node, src.node_id, 1, 0, order)
    assert out["fill_price"] == 10.0 and out["quantity"] == 5.0
