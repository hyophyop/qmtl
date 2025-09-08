from __future__ import annotations

from qmtl.sdk.brokerage_client import FakeBrokerageClient
from qmtl.sdk.oco import OCOOrder


def test_fake_client_oco_cancel_other_leg():
    client = FakeBrokerageClient()
    first = {"symbol": "AAPL", "side": "BUY", "quantity": 1}
    second = {"symbol": "AAPL", "side": "SELL", "quantity": 1}
    oco = OCOOrder(first, second)
    resp_first, resp_second = oco.execute(client)

    assert resp_first.get("status") == "completed"
    assert resp_second.get("status") == "canceled"
    # Poll to ensure canceled state persists
    refreshed = client.poll_order_status({"id": resp_second.get("id")})
    assert isinstance(refreshed, dict)
    assert refreshed.get("status") == "canceled"
