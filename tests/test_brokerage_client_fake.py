from __future__ import annotations

from qmtl.runtime.sdk.brokerage_client import FakeBrokerageClient


def test_fake_brokerage_post_returns_completed_and_id():
    client = FakeBrokerageClient()
    resp = client.post_order({"symbol": "AAPL", "side": "BUY", "quantity": 1})
    assert isinstance(resp, dict)
    assert resp.get("status") == "completed"
    assert resp.get("id") == "1"
    assert resp.get("echo", {}).get("symbol") == "AAPL"


def test_fake_brokerage_poll_by_id_returns_record():
    client = FakeBrokerageClient()
    rec = client.post_order({"symbol": "AAPL", "side": "BUY", "quantity": 1})
    order = {"id": rec.get("id"), "symbol": "AAPL"}
    status = client.poll_order_status(order)
    assert isinstance(status, dict)
    assert status.get("id") == rec.get("id")
    assert status.get("status") == "completed"


def test_fake_brokerage_cancel_sets_status_canceled():
    client = FakeBrokerageClient()
    rec = client.post_order({"symbol": "AAPL", "side": "BUY", "quantity": 1})
    oid = rec.get("id")
    canceled = client.cancel_order(str(oid))
    assert isinstance(canceled, dict)
    assert canceled.get("status") == "canceled"
    # Poll reflects canceled status
    status = client.poll_order_status({"id": oid, "symbol": "AAPL"})
    assert isinstance(status, dict)
    assert status.get("status") == "canceled"


def test_fake_brokerage_poll_without_id_returns_completed_echo():
    client = FakeBrokerageClient()
    status = client.poll_order_status({"symbol": "AAPL", "side": "BUY", "quantity": 1})
    assert isinstance(status, dict)
    assert status.get("status") == "completed"
    assert status.get("echo", {}).get("symbol") == "AAPL"

