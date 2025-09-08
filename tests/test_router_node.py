from qmtl.sdk.node import Node
from qmtl.sdk.runner import Runner
from qmtl.pipeline.execution_nodes import RouterNode


def test_router_node_assigns_target():
    src = Node(name="src", interval=1, period=1)

    def route_fn(order: dict) -> str:
        sym = order.get("symbol", "")
        return "binance" if sym.endswith("USDT") else "ibkr"

    router = RouterNode(src, route_fn=route_fn)
    order = {"symbol": "BTCUSDT", "price": 10.0, "quantity": 1.0}
    out = Runner.feed_queue_data(router, src.node_id, 1, 0, order)
    assert out["route"] == "binance"

