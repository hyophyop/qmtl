import pytest

from qmtl.sdk import Node, StreamInput
from qmtl.nodesets.recipes import make_ccxt_spot_nodeset


def test_attach_nodeset_simulate():
    price = StreamInput(interval="60s", period=1)
    signal = Node(input=price, compute_fn=lambda view: {"action": "BUY", "size": 1, "symbol": "BTC/USDT"})
    ns = make_ccxt_spot_nodeset(signal, "world", exchange_id="binance")
    assert ns.execution is not None and ns.pretrade is not None


def test_attach_nodeset_sandbox_requires_credentials():
    price = StreamInput(interval="60s", period=1)
    signal = Node(input=price, compute_fn=lambda view: {"action": "BUY", "size": 1, "symbol": "BTC/USDT"})
    with pytest.raises(RuntimeError):
        make_ccxt_spot_nodeset(signal, "world", exchange_id="binance", sandbox=True)
