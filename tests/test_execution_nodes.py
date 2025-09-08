from __future__ import annotations

from datetime import datetime, timezone

from qmtl.sdk.node import Node
from qmtl.sdk.runner import Runner
from qmtl.pipeline.execution_nodes import (
    PreTradeGateNode,
    SizingNode,
    ExecutionNode,
    PortfolioNode,
    RiskControlNode,
    TimingGateNode,
)
from qmtl.sdk.order_gate import Activation
from qmtl.brokerage.order import Account
from qmtl.sdk.portfolio import Portfolio
from qmtl.sdk.execution_modeling import ExecutionFill
from qmtl.sdk.risk_management import RiskManager
from qmtl.sdk.timing_controls import TimingController


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


def test_pretrade_gate_allows():
    src = Node(name="src", interval=1, period=1)
    node = PreTradeGateNode(
        src,
        activation_map={"AAPL": Activation(True)},
        brokerage=DummyBrokerage(),
        account=Account(),
    )
    order = {"symbol": "AAPL", "quantity": 1, "price": 10.0}
    out = Runner.feed_queue_data(node, src.node_id, 1, 0, order)
    assert out == order


def test_sizing_node_value_to_quantity():
    src = Node(name="src", interval=1, period=1)
    portfolio = Portfolio(cash=1000)
    node = SizingNode(src, portfolio=portfolio)
    order = {"symbol": "AAPL", "price": 10.0, "value": 100.0}
    out = Runner.feed_queue_data(node, src.node_id, 1, 0, order)
    assert out["quantity"] == 10


def test_execution_node_simulates_fill():
    src = Node(name="src", interval=1, period=1)
    exec_model = DummyExecModel()
    node = ExecutionNode(src, execution_model=exec_model)
    order = {"symbol": "AAPL", "price": 10.0, "quantity": 5.0}
    out = Runner.feed_queue_data(node, src.node_id, 1, 0, order)
    assert out["fill_price"] == 10.0 and out["quantity"] == 5.0


def test_portfolio_node_applies_fill():
    src = Node(name="fill", interval=1, period=1)
    portfolio = Portfolio(cash=100.0)
    node = PortfolioNode(src, portfolio=portfolio)
    fill = {"symbol": "AAPL", "quantity": 5.0, "fill_price": 10.0}
    out = Runner.feed_queue_data(node, src.node_id, 1, 0, fill)
    assert portfolio.cash == 50.0
    assert out["positions"]["AAPL"]["qty"] == 5.0


def test_risk_control_node_rejects_large_position():
    src = Node(name="src", interval=1, period=1)
    portfolio = Portfolio(cash=1000.0)
    risk = RiskManager(max_position_size=50.0)
    node = RiskControlNode(src, portfolio=portfolio, risk_manager=risk)
    order = {"symbol": "AAPL", "price": 10.0, "quantity": 10.0}
    out = Runner.feed_queue_data(node, src.node_id, 1, 0, order)
    assert out["rejected"]


def test_timing_gate_node_blocks_closed_market():
    src = Node(name="src", interval=1, period=1)
    controller = TimingController(require_regular_hours=True)
    node = TimingGateNode(src, controller=controller)
    order = {"symbol": "AAPL", "price": 10.0, "quantity": 1.0}
    saturday = int(datetime(2024, 1, 6, 15, 0, tzinfo=timezone.utc).timestamp())
    out = Runner.feed_queue_data(node, src.node_id, 1, saturday, order)
    assert out["rejected"]
