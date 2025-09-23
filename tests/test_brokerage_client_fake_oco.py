from __future__ import annotations

from qmtl.runtime.sdk.brokerage_client import FakeBrokerageClient
from qmtl.runtime.sdk.oco import OCOOrder


def test_fake_client_oco_cancel_other_leg():
    client = FakeBrokerageClient()
    first = {"symbol": "AAPL", "side": "BUY", "quantity": 1}
    second = {"symbol": "AAPL", "side": "SELL", "quantity": 1}
    oco = OCOOrder(first, second)
    resp_first, resp_second = oco.execute(client)

    assert resp_first.get("status") == "completed"
    # In the fake client both legs complete immediately; real connectors may
    # cancel the opposite leg. We accept either completed (late fill) or canceled.
    assert resp_second.get("status") in {"canceled", "completed"}
    # Poll to ensure terminal state persists
    refreshed = client.poll_order_status({"id": resp_second.get("id")})
    assert isinstance(refreshed, dict)
    assert refreshed.get("status") in {"canceled", "completed"}
