from qmtl.sdk.node import Node
from qmtl.sdk.cache_view import CacheView
from qmtl.brokerage import BrokerageModel, CashBuyingPowerModel
from qmtl.brokerage.fees import PercentFeeModel
from qmtl.brokerage.slippage import NullSlippageModel
from qmtl.brokerage.fill_models import MarketFillModel
from qmtl.brokerage.order import Account
from qmtl.transforms.execution_nodes import PreTradeGateNode, SizingNode
from qmtl.sdk.pretrade import Activation
from qmtl.sdk.portfolio import Portfolio


def _make_brokerage() -> BrokerageModel:
    return BrokerageModel(
        buying_power_model=CashBuyingPowerModel(),
        fee_model=PercentFeeModel(),
        slippage_model=NullSlippageModel(),
        fill_model=MarketFillModel(),
    )


def test_pretrade_gate_node_allows():
    order_src = Node(name="order", interval="1s", period=1)
    activation = {"AAPL": Activation(enabled=True)}
    node = PreTradeGateNode(
        order_src,
        activation_map=activation,
        brokerage=_make_brokerage(),
        account=Account(cash=10000.0),
    )
    view = CacheView({
        order_src.node_id: {order_src.interval: [(0, {"symbol": "AAPL", "quantity": 1, "price": 100.0})]}
    })
    assert node.compute_fn(view)["symbol"] == "AAPL"


def test_pretrade_gate_node_rejects():
    order_src = Node(name="order", interval="1s", period=1)
    activation = {"AAPL": Activation(enabled=False, reason="disabled")}
    node = PreTradeGateNode(
        order_src,
        activation_map=activation,
        brokerage=_make_brokerage(),
        account=Account(cash=10000.0),
    )
    view = CacheView({
        order_src.node_id: {order_src.interval: [(0, {"symbol": "AAPL", "quantity": 1, "price": 100.0})]}
    })
    res = node.compute_fn(view)
    assert res["rejected"]
    assert res["reason"] == "activation_disabled"


def test_sizing_node_value():
    intent_src = Node(name="intent", interval="1s", period=1, config={"role": "intent"})
    portfolio_src = Node(name="portfolio", interval="1s", period=1, config={"role": "portfolio"})
    node = SizingNode(intent_src, portfolio_src)
    portfolio = Portfolio(cash=1000.0)
    view = CacheView({
        intent_src.node_id: {intent_src.interval: [(0, {"symbol": "AAPL", "value": 500.0, "price": 100.0})]},
        portfolio_src.node_id: {portfolio_src.interval: [(0, portfolio)]},
    })
    sized = node.compute_fn(view)
    assert sized["quantity"] == 5


def test_sizing_node_percent():
    intent_src = Node(name="intent", interval="1s", period=1, config={"role": "intent"})
    portfolio_src = Node(name="portfolio", interval="1s", period=1, config={"role": "portfolio"})
    node = SizingNode(intent_src, portfolio_src)
    portfolio = Portfolio(cash=1000.0)
    view = CacheView({
        intent_src.node_id: {intent_src.interval: [(0, {"symbol": "AAPL", "percent": 0.1, "price": 50.0})]},
        portfolio_src.node_id: {portfolio_src.interval: [(0, portfolio)]},
    })
    sized = node.compute_fn(view)
    assert sized["quantity"] == 2
