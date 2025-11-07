from __future__ import annotations

from qmtl.runtime.sdk.intent import PositionTarget, to_order_payloads


def test_to_order_payloads_percent_and_qty():
    intents = [
        PositionTarget(symbol="BTCUSDT", target_percent=0.1),
        PositionTarget(symbol="ETHUSDT", target_qty=-2.0, reason="risk_cut"),
    ]
    out = to_order_payloads(intents, price_by_symbol={"BTCUSDT": 60000.0})
    assert out[0]["symbol"] == "BTCUSDT"
    assert out[0]["target_percent"] == 0.1
    assert out[0]["price"] == 60000.0
    assert out[1]["symbol"] == "ETHUSDT"
    assert out[1]["quantity"] == -2.0
    assert out[1]["reason"] == "risk_cut"

