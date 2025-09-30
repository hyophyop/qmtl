"""Sanity tests for Runner.run integration (validation features removed)."""

import pytest
import httpx
from qmtl.runtime.sdk import Runner, Strategy, StreamInput


def test_run_offline_minimal(monkeypatch):
    """Runner.run executes strategy setup and returns instance (offline)."""
    
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"strategy_id": "s"})

    transport = httpx.MockTransport(handler)

    class DummyClient:
        def __init__(self, *a, **k):
            self._client = httpx.Client(transport=transport)
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            self._client.close()
        async def post(self, url, json=None):
            request = httpx.Request("POST", url, json=json)
            return handler(request)

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    class TestStrategy(Strategy):
        def setup(self):
            stream = StreamInput(interval="60s", period=2)
            self.add_nodes([stream])

    strategy = Runner.offline(TestStrategy)
    assert isinstance(strategy, TestStrategy)


def test_run_offline_with_cached_data(monkeypatch):
    """Runner.run can operate with pre-cached data offline."""
    
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"strategy_id": "s"})

    transport = httpx.MockTransport(handler)

    class DummyClient:
        def __init__(self, *a, **k):
            self._client = httpx.Client(transport=transport)
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            self._client.close()
        async def post(self, url, json=None):
            request = httpx.Request("POST", url, json=json)
            return handler(request)

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    class TestStrategy(Strategy):
        def setup(self):
            stream = StreamInput(interval="60s", period=2)
            # Add some clean test data
            stream.cache.append("test_queue", 60, 60, {"close": 10.0})
            stream.cache.append("test_queue", 60, 120, {"close": 10.1})
            self.add_nodes([stream])

    strategy = Runner.offline(TestStrategy)
    assert isinstance(strategy, TestStrategy)


def test_run_offline_with_larger_moves(monkeypatch):
    """Runner.run supports arbitrary cached data without validation."""
    
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"strategy_id": "s"})

    transport = httpx.MockTransport(handler)

    class DummyClient:
        def __init__(self, *a, **k):
            self._client = httpx.Client(transport=transport)
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            self._client.close()
        async def post(self, url, json=None):
            request = httpx.Request("POST", url, json=json)
            return handler(request)

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    class TestStrategy(Strategy):
        def setup(self):
            stream = StreamInput(interval="60s", period=2)
            # Add data with larger price movement (but within custom limit)
            stream.cache.append("test_queue", 60, 60, {"close": 10.0})
            stream.cache.append("test_queue", 60, 120, {"close": 12.0})  # 20% change
            self.add_nodes([stream])

    strategy = Runner.offline(TestStrategy)
    assert isinstance(strategy, TestStrategy)
