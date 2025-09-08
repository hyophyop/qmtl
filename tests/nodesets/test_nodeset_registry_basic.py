from qmtl.sdk import Node, StreamInput
from qmtl.nodesets.registry import make, list_registered


def test_nodeset_registry_has_ccxt_spot():
    assert "ccxt_spot" in list_registered()


def test_nodeset_registry_make_ccxt_spot_simulate():
    price = StreamInput(interval="60s", period=1)
    signal = Node(input=price, compute_fn=lambda v: {"action": "BUY", "size": 1, "symbol": "BTC/USDT"})
    ns = make("ccxt_spot", signal, "world", exchange_id="binance")
    assert ns.head is ns.pretrade and ns.tail is ns.timing
    assert len(list(ns)) == 7

