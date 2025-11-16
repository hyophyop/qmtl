import asyncio

import httpx
import pytest

from qmtl.runtime.sdk.activation_manager import ActivationManager


class FakeWebSocketClient:
    def __init__(self, *_, **__):
        self.started = False
        self.stopped = False

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True


class SubscribeClient:
    def __init__(self, *_, **__):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json=None):
        return httpx.Response(200, json={"stream_url": "ws://stream", "token": "tok"})


class ErroringSubscribeClient:
    def __init__(self, *_, **__):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json=None):
        return httpx.Response(500, json={"error": "boom"})


@pytest.mark.asyncio
async def test_activation_start_success(monkeypatch):
    am = ActivationManager(gateway_url="http://gw", world_id="w1", strategy_id="s1")
    monkeypatch.setattr("qmtl.runtime.sdk.activation_manager.WebSocketClient", FakeWebSocketClient)
    monkeypatch.setattr(httpx, "AsyncClient", SubscribeClient)
    monkeypatch.setattr(am, "_reconcile_activation", lambda: asyncio.sleep(0))

    await am.start()

    assert am._started
    assert isinstance(am.client, FakeWebSocketClient)
    assert am._poll_task is not None
    assert am._stop_event is not None

    await am.stop()


@pytest.mark.asyncio
async def test_activation_start_handles_errors(monkeypatch):
    am = ActivationManager(gateway_url="http://gw", world_id="w1", strategy_id="s1")
    monkeypatch.setattr(httpx, "AsyncClient", ErroringSubscribeClient)
    monkeypatch.setattr(am, "_reconcile_activation", lambda: asyncio.sleep(0))

    await am.start()

    assert not am._started
    assert am.client is None
