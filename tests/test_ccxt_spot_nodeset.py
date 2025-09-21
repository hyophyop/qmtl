import pytest

from qmtl.sdk import Node, StreamInput
from qmtl.sdk.cache_view import CacheView
from qmtl.nodesets.options import NodeSetOptions
from qmtl.nodesets.recipes import make_ccxt_spot_nodeset
from qmtl.nodesets.resources import clear_shared_portfolios


def test_attach_nodeset_simulate():
    clear_shared_portfolios()
    price = StreamInput(interval="60s", period=1)
    signal = Node(input=price, compute_fn=lambda view: {"action": "BUY", "size": 1, "symbol": "BTC/USDT"})
    ns = make_ccxt_spot_nodeset(signal, "world", exchange_id="binance")
    nodes = list(ns)
    assert len(nodes) == 8 and ns.head is nodes[0]


def test_attach_nodeset_sandbox_requires_credentials():
    price = StreamInput(interval="60s", period=1)
    signal = Node(input=price, compute_fn=lambda view: {"action": "BUY", "size": 1, "symbol": "BTC/USDT"})
    with pytest.raises(RuntimeError):
        make_ccxt_spot_nodeset(signal, "world", exchange_id="binance", sandbox=True)


def test_ccxt_nodeset_applies_activation_weight():
    clear_shared_portfolios()
    price = StreamInput(interval=1, period=1)
    signal = Node(input=price, compute_fn=lambda view: {})
    ns = make_ccxt_spot_nodeset(signal, "world", exchange_id="binance")
    nodes = list(ns)
    sizing = nodes[1]
    order = {"symbol": "BTC/USDT", "price": 10.0, "value": 100.0, "side": "BUY"}
    assert sizing.weight_fn is not None
    sizing.weight_fn = lambda payload: 0.5
    upstream = sizing.order
    view = CacheView({upstream.node_id: {upstream.interval: [(0, order)]}})
    sized = sizing.compute_fn(view)
    assert sized["quantity"] == pytest.approx(5.0)


def test_ccxt_nodeset_world_portfolio_shared():
    clear_shared_portfolios()
    price = StreamInput(interval=1, period=1)
    sig1 = Node(input=price, compute_fn=lambda view: {})
    sig2 = Node(input=price, compute_fn=lambda view: {})
    options = NodeSetOptions(portfolio_scope="world")
    ns1 = make_ccxt_spot_nodeset(sig1, "world", exchange_id="binance", options=options)
    ns2 = make_ccxt_spot_nodeset(sig2, "world", exchange_id="binance", options=options)
    sizing1 = list(ns1)[1]
    sizing2 = list(ns2)[1]
    portfolio1 = getattr(sizing1, "portfolio", None)
    portfolio2 = getattr(sizing2, "portfolio", None)
    assert portfolio1 is not None
    assert portfolio1 is portfolio2
    assert getattr(list(ns1)[5], "portfolio", None) is portfolio1
