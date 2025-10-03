import pytest

from qmtl.runtime.sdk import Node, StreamInput
from qmtl.runtime.nodesets.options import NodeSetOptions
from qmtl.runtime.nodesets.recipes import make_ccxt_futures_nodeset
from qmtl.runtime.nodesets.resources import clear_shared_portfolios


def test_attach_futures_nodeset_simulate():
    clear_shared_portfolios()
    price = StreamInput(interval="60s", period=1)
    signal = Node(
        input=price,
        compute_fn=lambda view: {"action": "BUY", "size": 1, "symbol": "BTC/USDT"},
    )
    ns = make_ccxt_futures_nodeset(signal, "world")
    nodes = list(ns)
    assert len(nodes) == 8 and ns.head is nodes[0]


def test_futures_nodeset_sandbox_requires_credentials():
    price = StreamInput(interval="60s", period=1)
    signal = Node(
        input=price,
        compute_fn=lambda view: {"action": "BUY", "size": 1, "symbol": "BTC/USDT"},
    )
    with pytest.raises(RuntimeError):
        make_ccxt_futures_nodeset(signal, "world", sandbox=True)


def test_futures_nodeset_exec_applies_defaults():
    clear_shared_portfolios()
    price = StreamInput(interval="60s", period=1)

    def make_signal(view):
        return {
            "action": "BUY",
            "size": 1,
            "symbol": "BTC/USDT",
            "type": "limit",
            "price": 100.0,
        }

    signal = Node(input=price, compute_fn=make_signal, name="sig", interval="60s", period=1)
    ns = make_ccxt_futures_nodeset(
        signal,
        "world",
        sandbox=False,
        reduce_only=True,
        leverage=5,
    )

    price.feed(price.node_id, price.interval, 60, {"close": 1})
    signal.feed(price.node_id, price.interval, 60, {"close": 1})

    nodes = list(ns)
    pre = nodes[0]
    siz = nodes[1]
    exe = nodes[2]

    pre.feed(signal.node_id, signal.interval, 60, make_signal(None))
    pre_out = pre.compute_fn(pre.cache.view())
    assert pre_out is not None

    siz.feed(pre.node_id, pre.interval, 60, pre_out)
    siz_out = siz.compute_fn(siz.cache.view())
    assert siz_out is not None

    exe.feed(siz.node_id, siz.interval, 60, siz_out)
    out = exe.compute_fn(exe.cache.view())

    assert out is not None
    assert out["symbol"] == "BTC/USDT"
    assert out["time_in_force"] == "GTC"
    assert out["reduce_only"] is True
    assert out["leverage"] == 5
    assert out["type"] == "limit"
    assert out.get("limit_price", out.get("price")) == 100.0


def test_futures_nodeset_world_portfolio_shared():
    clear_shared_portfolios()
    price = StreamInput(interval=1, period=1)
    sig1 = Node(input=price, compute_fn=lambda view: {})
    sig2 = Node(input=price, compute_fn=lambda view: {})
    options = NodeSetOptions(portfolio_scope="world")
    ns1 = make_ccxt_futures_nodeset(sig1, "world", options=options)
    ns2 = make_ccxt_futures_nodeset(sig2, "world", options=options)
    sizing1 = list(ns1)[1]
    sizing2 = list(ns2)[1]
    portfolio1 = getattr(sizing1, "portfolio", None)
    portfolio2 = getattr(sizing2, "portfolio", None)
    assert portfolio1 is not None
    assert portfolio1 is portfolio2
    assert getattr(list(ns1)[5], "portfolio", None) is portfolio1
