import importlib
from unittest.mock import MagicMock

import qmtl.runtime.sdk.runner as runner_module
from qmtl.runtime.sdk.node import Node


class TradeOrderPublisherNode(Node):
    pass


def test_runner_trade_execution_service_invoked():
    runner_mod = importlib.reload(runner_module)
    service = MagicMock()
    runner_mod.Runner.set_trade_execution_service(service)
    try:
        src = Node(name="src", interval=1, period=1)
        trade = TradeOrderPublisherNode(
            src,
            compute_fn=lambda view: {"side": "BUY"},
            interval=1,
            period=1,
        )
        runner_mod.Runner.feed_queue_data(trade, src.node_id, 1, 0, {})
        service.post_order.assert_called_once_with({"side": "BUY"})
    finally:
        runner_mod.Runner.set_trade_execution_service(None)


def test_runner_trade_execution_service_survives_reload():
    service = MagicMock()
    runner_module.Runner.set_trade_execution_service(service)
    try:
        runner_module.Runner._handle_trade_order({"side": "BUY"})
        service.post_order.assert_called_once_with({"side": "BUY"})
        service.post_order.reset_mock()
        importlib.reload(runner_module)
        runner_module.Runner._handle_trade_order({"side": "SELL"})
        service.post_order.assert_called_once_with({"side": "SELL"})
    finally:
        runner_module.Runner.set_trade_execution_service(None)
