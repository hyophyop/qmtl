import pytest

from qmtl.sdk import Node, StreamInput
from qmtl.brokerage.ccxt_spot_nodeset import CcxtSpotNodeSet


def test_attach_simulate_uses_fake_client():
    price = StreamInput(interval="60s", period=1)
    signal = Node(input=price, compute_fn=lambda view: {"action": "BUY", "size": 1, "symbol": "BTC/USDT"})
    nodes = CcxtSpotNodeSet.attach(signal, "world", exchange_id="binance")
    assert len(nodes) == 3


def test_attach_sandbox_requires_credentials():
    price = StreamInput(interval="60s", period=1)
    signal = Node(input=price, compute_fn=lambda view: {"action": "BUY", "size": 1, "symbol": "BTC/USDT"})
    with pytest.raises(RuntimeError):
        CcxtSpotNodeSet.attach(signal, "world", exchange_id="binance", sandbox=True)
