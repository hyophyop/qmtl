from __future__ import annotations

from datetime import datetime, timezone
import asyncio

import qmtl.sdk.runner as runner_module
from qmtl.sdk.node import Node
from qmtl.pipeline.execution_nodes import (
    PreTradeGateNode,
    SizingNode,
    ExecutionNode,
    OrderPublishNode,
    PortfolioNode,
    RiskControlNode,
    TimingGateNode,
)
from qmtl.sdk.order_gate import Activation
from qmtl.sdk.watermark import (
    WatermarkGate,
    clear_watermarks,
    get_watermark,
    set_watermark,
)
from qmtl.brokerage.order import Account
from qmtl.sdk.portfolio import Portfolio
from qmtl.sdk.execution_modeling import ExecutionFill
from qmtl.sdk.risk_management import RiskManager
from qmtl.sdk.timing_controls import TimingController
from qmtl.sdk.activation_manager import ActivationManager


class DummyBrokerage:
    def can_submit_order(self, account, order):  # noqa: D401 - simple stub
        return True


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


def test_pretrade_gate_allows_when_gating_disabled():
    clear_watermarks()
    src = Node(name="src", interval=60, period=1)
    src.world_id = "sim-world"
    node = PreTradeGateNode(
        src,
        activation_map={"AAPL": Activation(True)},
        brokerage=DummyBrokerage(),
        account=Account(),
        watermark_gate=WatermarkGate.for_mode("simulate"),
    )
    order = {"symbol": "AAPL", "quantity": 1, "price": 10.0}
    out = runner_module.Runner.feed_queue_data(node, src.node_id, 60, 120, order)
    assert out == order


def test_pretrade_gate_blocks_until_watermark_ready():
    clear_watermarks()
    src = Node(name="src", interval=60, period=1)
    src.world_id = "live-world"
    node = PreTradeGateNode(
        src,
        activation_map={"AAPL": Activation(True)},
        brokerage=DummyBrokerage(),
        account=Account(),
        watermark_gate=WatermarkGate.for_mode("live"),
    )
    order = {"symbol": "AAPL", "quantity": 1, "price": 10.0}
    rejected = runner_module.Runner.feed_queue_data(node, src.node_id, 60, 180, order.copy())
    assert rejected == {"rejected": True, "reason": "watermark"}

    set_watermark("trade.portfolio", "live-world", 179)
    rejected_again = runner_module.Runner.feed_queue_data(
        node, src.node_id, 60, 240, {"symbol": "AAPL", "quantity": 1, "price": 10.5}
    )
    assert rejected_again == {"rejected": True, "reason": "watermark"}

    set_watermark("trade.portfolio", "live-world", 240)
    allowed = runner_module.Runner.feed_queue_data(
        node, src.node_id, 60, 300, {"symbol": "AAPL", "quantity": 1, "price": 10.5}
    )
    assert allowed["symbol"] == "AAPL"


def test_pretrade_gate_respects_configured_lag():
    clear_watermarks()
    src = Node(name="src", interval=60, period=1)
    src.world_id = "lag-world"
    node = PreTradeGateNode(
        src,
        activation_map={"AAPL": Activation(True)},
        brokerage=DummyBrokerage(),
        account=Account(),
        watermark_gate=WatermarkGate(enabled=True, lag=2),
    )
    rejected = runner_module.Runner.feed_queue_data(node, src.node_id, 60, 180, {"symbol": "AAPL", "quantity": 1, "price": 11.0})
    assert rejected == {"rejected": True, "reason": "watermark"}

    set_watermark("trade.portfolio", "lag-world", 119)
    still_blocked = runner_module.Runner.feed_queue_data(
        node, src.node_id, 60, 240, {"symbol": "AAPL", "quantity": 1, "price": 11.5}
    )
    assert still_blocked == {"rejected": True, "reason": "watermark"}

    set_watermark("trade.portfolio", "lag-world", 180)
    allowed = runner_module.Runner.feed_queue_data(
        node, src.node_id, 60, 300, {"symbol": "AAPL", "quantity": 1, "price": 11.5}
    )
    assert allowed["price"] == 11.5


def test_pretrade_gate_isolated_per_world():
    clear_watermarks()
    src_a = Node(name="src_a", interval=60, period=1)
    src_a.world_id = "world-a"
    src_b = Node(name="src_b", interval=60, period=1)
    src_b.world_id = "world-b"
    gate_a = PreTradeGateNode(
        src_a,
        activation_map={"AAPL": Activation(True)},
        brokerage=DummyBrokerage(),
        account=Account(),
        watermark_gate=WatermarkGate(enabled=True),
    )
    gate_b = PreTradeGateNode(
        src_b,
        activation_map={"AAPL": Activation(True)},
        brokerage=DummyBrokerage(),
        account=Account(),
        watermark_gate=WatermarkGate(enabled=True),
    )

    set_watermark("trade.portfolio", "world-a", 10**9)
    allowed = runner_module.Runner.feed_queue_data(
        gate_a, src_a.node_id, 60, 180, {"symbol": "AAPL", "quantity": 1, "price": 12.0}
    )
    assert allowed["price"] == 12.0

    rejected = runner_module.Runner.feed_queue_data(
        gate_b, src_b.node_id, 60, 180, {"symbol": "AAPL", "quantity": 1, "price": 12.0}
    )
    assert rejected == {"rejected": True, "reason": "watermark"}


def test_sizing_node_value_to_quantity():
    src = Node(name="src", interval=1, period=1)
    portfolio = Portfolio(cash=1000)
    node = SizingNode(src, portfolio=portfolio)
    order = {"symbol": "AAPL", "price": 10.0, "value": 100.0}
    out = runner_module.Runner.feed_queue_data(node, src.node_id, 1, 0, order)
    assert out["quantity"] == 10


def test_execution_node_simulates_fill():
    src = Node(name="src", interval=1, period=1)
    exec_model = DummyExecModel()
    node = ExecutionNode(src, execution_model=exec_model)
    order = {"symbol": "AAPL", "price": 10.0, "quantity": 5.0}
    out = runner_module.Runner.feed_queue_data(node, src.node_id, 1, 0, order)
    assert out["fill_price"] == 10.0 and out["quantity"] == 5.0


def test_portfolio_node_applies_fill():
    src = Node(name="fill", interval=1, period=1)
    portfolio = Portfolio(cash=100.0)
    node = PortfolioNode(src, portfolio=portfolio)
    fill = {"symbol": "AAPL", "quantity": 5.0, "fill_price": 10.0}
    out = runner_module.Runner.feed_queue_data(node, src.node_id, 1, 0, fill)
    assert portfolio.cash == 50.0
    assert out["positions"]["AAPL"]["qty"] == 5.0


def test_portfolio_node_updates_custom_watermark_topic():
    clear_watermarks()
    src = Node(name="fill", interval=1, period=1)
    src.world_id = "topic-world"
    portfolio = Portfolio(cash=100.0)
    node = PortfolioNode(src, portfolio=portfolio, watermark_topic="custom.topic")
    fill = {"symbol": "AAPL", "quantity": 1.0, "fill_price": 10.0, "timestamp": 200}
    runner_module.Runner.feed_queue_data(node, src.node_id, 1, 0, fill)
    assert get_watermark("custom.topic", "topic-world") == 200


def test_portfolio_node_watermark_ignores_out_of_order_fill():
    clear_watermarks()
    src = Node(name="fill", interval=1, period=1)
    src.world_id = "wm-world"
    portfolio = Portfolio(cash=100.0)
    node = PortfolioNode(src, portfolio=portfolio)
    newest = {"symbol": "AAPL", "quantity": 1.0, "fill_price": 10.0, "timestamp": 220}
    runner_module.Runner.feed_queue_data(node, src.node_id, 1, 0, newest)
    older = {"symbol": "AAPL", "quantity": 1.0, "fill_price": 10.0, "timestamp": 200}
    runner_module.Runner.feed_queue_data(node, src.node_id, 1, 0, older)
    assert get_watermark("trade.portfolio", "wm-world") == 220


def test_risk_control_node_rejects_large_position():
    src = Node(name="src", interval=1, period=1)
    portfolio = Portfolio(cash=1000.0)
    risk = RiskManager(max_position_size=50.0)
    node = RiskControlNode(src, portfolio=portfolio, risk_manager=risk)
    order = {"symbol": "AAPL", "price": 10.0, "quantity": 10.0}
    out = runner_module.Runner.feed_queue_data(node, src.node_id, 1, 0, order)
    assert out["rejected"]


def test_timing_gate_node_blocks_closed_market():
    src = Node(name="src", interval=1, period=1)
    controller = TimingController(require_regular_hours=True)
    node = TimingGateNode(src, controller=controller)
    order = {"symbol": "AAPL", "price": 10.0, "quantity": 1.0}
    saturday = int(datetime(2024, 1, 6, 15, 0, tzinfo=timezone.utc).timestamp())
    out = runner_module.Runner.feed_queue_data(node, src.node_id, 1, saturday, order)
    assert out["rejected"]


def test_order_publish_node_calls_publisher():
    src = Node(name="src", interval=1, period=1)
    calls: list[dict] = []

    def _pub(o):
        calls.append(o)

    prev_am = runner_module.Runner._activation_manager
    runner_module.Runner.set_activation_manager(None)
    try:
        node = OrderPublishNode(src, submit_order=_pub)
        order = {"symbol": "AAPL", "price": 10.0, "quantity": 1.0}
        out = runner_module.Runner.feed_queue_data(node, src.node_id, 1, 0, order)
        assert out == order and calls == [order]
    finally:
        runner_module.Runner.set_activation_manager(prev_am)


def test_order_publish_node_blocks_during_freeze_and_drain():
    src = Node(name="src", interval=1, period=1)

    class DummyWriter:
        def __init__(self) -> None:
            self.calls: list[tuple[int, int, list[tuple[str, str, dict]]]] = []

        async def publish_bucket(self, ts, interval, entries):
            self.calls.append((ts, interval, list(entries)))

    class DummySubmit:
        def __init__(self) -> None:
            self.orders: list[dict] = []

        def __call__(self, order):
            self.orders.append(order)

    writer = DummyWriter()
    submit = DummySubmit()
    node = OrderPublishNode(src, commit_log_writer=writer, submit_order=submit)

    am = ActivationManager()

    prev_am = runner_module.Runner._activation_manager
    prev_service = runner_module.Runner._trade_execution_service
    prev_http = runner_module.Runner._trade_order_http_url
    prev_topic = runner_module.Runner._trade_order_kafka_topic
    prev_producer = runner_module.Runner._kafka_producer

    runner_module.Runner.set_trade_execution_service(None)
    runner_module.Runner.set_trade_order_http_url(None)
    runner_module.Runner.set_trade_order_kafka_topic(None)
    runner_module.Runner.set_kafka_producer(None)
    runner_module.Runner.set_activation_manager(am)

    try:
        def _feed(ts: int, payload: dict) -> None:
            runner_module.Runner.feed_queue_data(node, src.node_id, 1, ts, payload.copy())

        asyncio.run(
            am._on_message({
                "event": "activation_updated",
                "data": {"side": "long", "active": True, "weight": 1.0},
            })
        )
        asyncio.run(
            am._on_message({
                "event": "activation_updated",
                "data": {"side": "short", "active": True, "weight": 1.0},
            })
        )

        buy = {"symbol": "AAPL", "price": 10.0, "quantity": 1.0, "side": "BUY"}
        sell = {"symbol": "AAPL", "price": 10.0, "quantity": -1.0, "side": "SELL"}

        _feed(1, buy)
        assert len(writer.calls) == 1
        assert len(submit.orders) == 1

        asyncio.run(
            am._on_message({
                "event": "activation_updated",
                "data": {"side": "long", "active": True, "freeze": True},
            })
        )

        _feed(2, sell)
        assert len(writer.calls) == 1
        assert len(submit.orders) == 1

        asyncio.run(
            am._on_message({
                "event": "activation_updated",
                "data": {"side": "long", "active": True, "freeze": False},
            })
        )

        _feed(3, sell)
        assert len(writer.calls) == 2
        assert len(submit.orders) == 2

        asyncio.run(
            am._on_message({
                "event": "activation_updated",
                "data": {"side": "short", "active": True, "drain": True},
            })
        )

        _feed(4, buy)
        assert len(writer.calls) == 2
        assert len(submit.orders) == 2

        asyncio.run(
            am._on_message({
                "event": "activation_updated",
                "data": {"side": "short", "active": True, "drain": False},
            })
        )

        _feed(5, buy)
        assert len(writer.calls) == 3
        assert len(submit.orders) == 3
    finally:
        runner_module.Runner.set_activation_manager(prev_am)
        runner_module.Runner.set_trade_execution_service(prev_service)
        runner_module.Runner.set_trade_order_http_url(prev_http)
        runner_module.Runner.set_trade_order_kafka_topic(prev_topic)
        runner_module.Runner.set_kafka_producer(prev_producer)
