from __future__ import annotations

import httpx
import pytest

import importlib

import qmtl.sdk.trade_execution_service as tes
from qmtl.sdk import TradeExecutionService
import qmtl.sdk.runner as runner_module


class DummyResponse:
    status_code = 200

    def raise_for_status(self) -> None:
        return None


def test_service_retries_on_failure(monkeypatch):
    calls = {"count": 0}

    def fake_post(url: str, json: dict, timeout: float):
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.HTTPError("boom")
        return DummyResponse()

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(tes.time, "sleep", lambda s: None)
    service = TradeExecutionService("http://broker", max_retries=2)
    service.post_order({"id": 1})
    assert calls["count"] == 2


def test_service_raises_after_retries(monkeypatch):
    def fake_post(url: str, json: dict, timeout: float):
        raise httpx.HTTPError("boom")

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(tes.time, "sleep", lambda s: None)
    service = TradeExecutionService("http://broker", max_retries=1)
    with pytest.raises(httpx.HTTPError):
        service.post_order({"id": 1})


def test_runner_delegates_to_service(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("should not be called")

    class DummyService:
        def __init__(self) -> None:
            self.orders: list[dict] = []

        def post_order(self, order):
            self.orders.append(order)

    monkeypatch.setattr(httpx, "post", boom)
    service = DummyService()
    importlib.reload(runner_module)
    runner_module.Runner.set_trade_execution_service(service)
    runner_module.Runner._handle_trade_order({"id": 2})
    runner_module.Runner.set_trade_execution_service(None)
    assert service.orders == [{"id": 2}]
