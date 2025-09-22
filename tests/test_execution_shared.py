from __future__ import annotations

from qmtl.sdk.cache_view import CacheView
from qmtl.sdk.node import Node
from qmtl.sdk.order_gate import Activation
from qmtl.brokerage import BrokerageModel, CashBuyingPowerModel
from qmtl.brokerage.fees import PercentFeeModel
from qmtl.brokerage.fill_models import MarketFillModel
from qmtl.brokerage.order import Account
from qmtl.brokerage.slippage import NullSlippageModel
from qmtl.pipeline.execution_nodes import PreTradeGateNode as PipelinePreTradeGate
from qmtl.pipeline.execution_nodes import SizingNode as PipelineSizing
from qmtl.sdk.portfolio import Portfolio
from qmtl.transforms.execution_nodes import PreTradeGateNode as TransformPreTradeGate
from qmtl.transforms.execution_nodes import SizingNode as TransformSizing


def _make_brokerage() -> BrokerageModel:
    return BrokerageModel(
        buying_power_model=CashBuyingPowerModel(),
        fee_model=PercentFeeModel(),
        slippage_model=NullSlippageModel(),
        fill_model=MarketFillModel(),
    )


def _make_view(node: Node, payload) -> CacheView:
    return CacheView({node.node_id: {node.interval: [(0, payload)]}})


def test_pretrade_nodes_allow_consistently():
    order_node = Node(name="order", interval=1, period=1)
    activation = {"AAPL": Activation(enabled=True)}
    brokerage = _make_brokerage()
    account = Account(cash=10000.0)
    pipeline_gate = PipelinePreTradeGate(
        order_node,
        activation_map=activation,
        brokerage=brokerage,
        account=account,
    )
    transform_gate = TransformPreTradeGate(
        order_node,
        activation_map=activation,
        brokerage=brokerage,
        account=account,
    )
    payload = {"symbol": "AAPL", "quantity": 5, "price": 100.0}
    pipeline_out = pipeline_gate._compute(_make_view(order_node, payload))
    transform_out = transform_gate.compute_fn(_make_view(order_node, payload))
    assert pipeline_out == transform_out


def test_pretrade_nodes_reject_consistently():
    order_node = Node(name="order", interval=1, period=1)
    activation = {"AAPL": Activation(enabled=False, reason="disabled")}
    brokerage = _make_brokerage()
    account = Account(cash=10000.0)
    pipeline_gate = PipelinePreTradeGate(
        order_node,
        activation_map=activation,
        brokerage=brokerage,
        account=account,
    )
    transform_gate = TransformPreTradeGate(
        order_node,
        activation_map=activation,
        brokerage=brokerage,
        account=account,
    )
    payload = {"symbol": "AAPL", "quantity": 5, "price": 100.0}
    pipeline_out = pipeline_gate._compute(_make_view(order_node, payload))
    transform_out = transform_gate.compute_fn(_make_view(order_node, payload))
    assert pipeline_out == transform_out
    assert pipeline_out == {"rejected": True, "reason": "activation_disabled"}


def test_sizing_nodes_value_consistently():
    intent_node = Node(name="intent", interval=1, period=1, config={"role": "intent"})
    portfolio_node = Node(name="portfolio", interval=1, period=1, config={"role": "portfolio"})
    portfolio = Portfolio(cash=1000.0)
    pipeline_sizing = PipelineSizing(intent_node, portfolio=portfolio)
    transform_sizing = TransformSizing(intent_node, portfolio_node)
    payload = {"symbol": "AAPL", "price": 100.0, "value": 500.0}
    pipeline_out = pipeline_sizing._compute(_make_view(intent_node, payload))
    transform_out = transform_sizing.compute_fn(
        CacheView({
            intent_node.node_id: {intent_node.interval: [(0, payload)]},
            portfolio_node.node_id: {portfolio_node.interval: [(0, portfolio)]},
        })
    )
    assert pipeline_out == transform_out
    assert pipeline_out["quantity"] == 5


def test_sizing_nodes_percent_consistently():
    intent_node = Node(name="intent", interval=1, period=1, config={"role": "intent"})
    portfolio_node = Node(name="portfolio", interval=1, period=1, config={"role": "portfolio"})
    portfolio = Portfolio(cash=1000.0)
    pipeline_sizing = PipelineSizing(intent_node, portfolio=portfolio)
    transform_sizing = TransformSizing(intent_node, portfolio_node)
    payload = {"symbol": "AAPL", "price": 50.0, "percent": 0.1}
    pipeline_out = pipeline_sizing._compute(_make_view(intent_node, payload))
    transform_out = transform_sizing.compute_fn(
        CacheView({
            intent_node.node_id: {intent_node.interval: [(0, payload)]},
            portfolio_node.node_id: {portfolio_node.interval: [(0, portfolio)]},
        })
    )
    assert pipeline_out == transform_out
    assert round(pipeline_out["quantity"], 6) == 2
