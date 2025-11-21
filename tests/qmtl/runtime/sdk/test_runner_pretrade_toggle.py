from __future__ import annotations

import importlib

import qmtl.runtime.sdk.runner as runner_module
from qmtl.foundation.common.compute_key import ComputeContext, compute_compute_key
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


def test_runner_blocks_trade_submission_in_shadow_domain() -> None:
    importlib.reload(runner_module)
    from qmtl.runtime.sdk.runner import Runner  # re-import after reload

    Runner.set_enable_trade_submission(True)
    service = DummyService()
    Runner.set_trade_execution_service(service)

    src = Node(name="sig", interval=1, period=1)
    pub = TradeOrderPublisherNode(src)
    context = ComputeContext(world_id="w", execution_domain="shadow")
    src.apply_compute_context(context)
    pub.apply_compute_context(context)

    result = Runner.feed_queue_data(
        pub, src.node_id, 1, 0, {"action": "BUY", "size": 1.0}
    )

    assert result is not None and result.get("side") == "BUY"
    assert service.orders == []

    active_context = pub.cache.active_context
    assert active_context is not None
    assert active_context.execution_domain == "shadow"

    shadow_key = compute_compute_key(pub.node_hash, context)
    backtest_key = compute_compute_key(
        pub.node_hash, ComputeContext(world_id="w", execution_domain="backtest")
    )
    assert shadow_key == pub.compute_key
    assert shadow_key != backtest_key

