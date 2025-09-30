from qmtl.runtime.sdk import Node, StreamInput
from qmtl.runtime.nodesets.adapters import CcxtSpotAdapter, CcxtFuturesAdapter
from qmtl.runtime.nodesets.options import NodeSetOptions
from qmtl.runtime.nodesets.resources import clear_shared_portfolios


def test_ccxt_adapter_populates_ports_and_capabilities_in_describe():
    clear_shared_portfolios()
    price = StreamInput(interval="60s", period=1)
    signal = Node(input=price, compute_fn=lambda v: {"action": "HOLD"})

    adapter = CcxtSpotAdapter(exchange_id="binance")
    ns = adapter.build({"signal": signal}, world_id="w1")

    info = ns.describe()
    ports = info.get("ports")
    assert isinstance(ports, dict)

    in_ports = ports.get("inputs") or []
    out_ports = ports.get("outputs") or []

    assert any(p.get("name") == "signal" and p.get("required") is True for p in in_ports)
    assert any(p.get("name") == "orders" for p in out_ports)

    caps = ns.capabilities()
    assert "modes" in caps and "simulate" in caps["modes"]
    assert caps.get("portfolio_scope") == "strategy"
    assert info.get("name") == "ccxt_spot"


def test_ccxt_adapter_respects_options():
    clear_shared_portfolios()
    price = StreamInput(interval="60s", period=1)
    signal = Node(input=price, compute_fn=lambda v: {"action": "HOLD"})
    adapter = CcxtSpotAdapter(exchange_id="binance")
    options = NodeSetOptions(portfolio_scope="world")
    ns = adapter.build({"signal": signal}, world_id="w1", options=options)
    caps = ns.capabilities()
    assert caps.get("portfolio_scope") == "world"


def test_ccxt_futures_adapter_descriptor():
    clear_shared_portfolios()
    price = StreamInput(interval="60s", period=1)
    signal = Node(input=price, compute_fn=lambda v: {"action": "HOLD"})

    adapter = CcxtFuturesAdapter()
    ns = adapter.build({"signal": signal}, world_id="w1")

    info = ns.describe()
    assert info.get("name") == "ccxt_futures"
    caps = ns.capabilities()
    assert "simulate" in caps.get("modes", ())
