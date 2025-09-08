from qmtl.sdk.node import Node
from qmtl.sdk.runner import Runner
from qmtl.pipeline.execution_nodes import PreTradeGateNode
from qmtl.sdk.order_gate import Activation
from qmtl.brokerage.order import Account


def test_pretrade_backpressure_blocks():
    src = Node(name="src", interval=1, period=1)
    overloaded = True

    def guard() -> bool:
        return overloaded

    node = PreTradeGateNode(
        src,
        activation_map={"AAPL": Activation(True)},
        brokerage=type("B", (), {"can_submit_order": lambda *_: True})(),
        account=Account(),
        backpressure_guard=guard,
    )
    out = Runner.feed_queue_data(
        node, src.node_id, 1, 0, {"symbol": "AAPL", "quantity": 1, "price": 10.0}
    )
    assert out["rejected"] and out["reason"] == "backpressure"

