from unittest.mock import MagicMock

from qmtl.sdk.node import Node


class TradeOrderPublisherNode(Node):
    pass


def test_runner_trade_execution_service_invoked():
    import importlib
    import qmtl.sdk.runner as runner_module

    runner_module = importlib.reload(runner_module)
    Runner = runner_module.Runner

    service = MagicMock()
    Runner.set_trade_execution_service(service)
    try:
        src = Node(name="src", interval=1, period=1)
        trade = TradeOrderPublisherNode(
            src,
            compute_fn=lambda view: {"side": "BUY"},
            interval=1,
            period=1,
        )
        Runner.feed_queue_data(trade, src.node_id, 1, 0, {})
        service.post_order.assert_called_once_with({"side": "BUY"})
    finally:
        Runner.set_trade_execution_service(None)

