from __future__ import annotations

import importlib

import qmtl.runtime.sdk.runner as runner_module
from qmtl.runtime.sdk.node import Node
from qmtl.runtime.sdk.runner import Runner
from qmtl.runtime.transforms.publisher import TradeOrderPublisherNode


class DummyService:
    def __init__(self) -> None:
        self.orders = []

    def post_order(self, order):
        self.orders.append(order)


def test_runner_can_disable_trade_submission():
    importlib.reload(runner_module)
    from qmtl.runtime.sdk.runner import Runner  # re-import after reload

    Runner.set_enable_trade_submission(False)
    service = DummyService()
    Runner.set_trade_execution_service(service)

    src = Node(name="sig", interval=1, period=1)
    pub = TradeOrderPublisherNode(src)
    Runner.feed_queue_data(pub, src.node_id, 1, 0, {"action": "BUY", "size": 1.0})
    assert service.orders == []

    Runner.set_enable_trade_submission(True)
    Runner.feed_queue_data(pub, src.node_id, 1, 1, {"action": "SELL", "size": 2.0})
    assert len(service.orders) == 1 and service.orders[0]["side"] == "SELL"

