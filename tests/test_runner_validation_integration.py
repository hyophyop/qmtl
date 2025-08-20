"""Test that validation integration works properly with Runner."""

import pytest
import httpx
from qmtl.sdk import Runner, Strategy, StreamInput


def test_backtest_with_validation_disabled(monkeypatch):
    """Test that backtest works when validation is disabled."""
    
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

    # Should work with validation disabled
    strategy = Runner.backtest(
        TestStrategy,
        start_time="s",
        end_time="e",
        gateway_url="http://gw",
        validate_data=False
    )
    assert isinstance(strategy, TestStrategy)


def test_backtest_with_validation_enabled_clean_data(monkeypatch):
    """Test that backtest works with validation enabled and clean data."""
    
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

    # Should work with validation enabled and clean data
    strategy = Runner.backtest(
        TestStrategy,
        start_time="s",
        end_time="e",
        gateway_url="http://gw",
        validate_data=True
    )
    assert isinstance(strategy, TestStrategy)


def test_backtest_with_validation_custom_config(monkeypatch):
    """Test that backtest works with custom validation configuration."""
    
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

    # Should work with custom validation config allowing larger price movements
    strategy = Runner.backtest(
        TestStrategy,
        start_time="s",
        end_time="e",
        gateway_url="http://gw",
        validate_data=True,
        validation_config={
            "max_price_change_pct": 0.25,  # Allow up to 25% change
        }
    )
    assert isinstance(strategy, TestStrategy)