from __future__ import annotations

import asyncio
import sys
import types
import pandas as pd
import pytest

from qmtl.runtime.io.ccxt_fetcher import (
    CcxtTradesConfig,
    CcxtTradesFetcher,
    RateLimiterConfig,
)


class _StubTradesExchange:
    def __init__(self, batches):
        self._batches = list(batches)
        self.calls = []

    async def fetch_trades(self, symbol, since=None, limit=None):
        self.calls.append((symbol, since, limit))
        if not self._batches:
            return []
        batch = self._batches.pop(0)
        await asyncio.sleep(0)
        return batch

    async def close(self):  # pragma: no cover - best effort
        await asyncio.sleep(0)


class _DummyLimiter:
    async def __aenter__(self):  # pragma: no cover - trivial context
        return self

    async def __aexit__(self, exc_type, exc, tb):  # pragma: no cover - trivial context
        return False


@pytest.mark.asyncio
async def test_trades_fetcher_normalizes_and_sorts():
    rows = [
        {"timestamp": 60_000, "price": 10.0, "amount": 0.1, "side": "buy"},
        {"timestamp": 120_000, "price": 11.0, "amount": 0.2, "side": "sell"},
        {"timestamp": 30_000, "price": 9.5, "amount": 0.05},  # filtered out
    ]
    ex = _StubTradesExchange([rows])
    cfg = CcxtTradesConfig(
        exchange_id="binance",
        symbols=["BTC/USDT"],
        rate_limiter=RateLimiterConfig(),
    )
    fetcher = CcxtTradesFetcher(cfg, exchange=ex)
    df = await fetcher.fetch(60, 120, node_id="trades:binance:BTC/USDT", interval=60)
    assert list(df.columns)[:1] == ["ts"]
    assert df["ts"].tolist() == [60, 120]
    assert df.iloc[0]["price"] == 10.0


@pytest.mark.asyncio
async def test_trades_fetcher_chunks_by_window_size():
    batch1 = [
        {"timestamp": 60_000, "price": 10.0, "amount": 0.1},
        {"timestamp": 61_000, "price": 10.1, "amount": 0.1},
    ]
    batch2 = [
        {"timestamp": 120_000, "price": 11.0, "amount": 0.2},
        {"timestamp": 121_000, "price": 11.2, "amount": 0.2},
    ]
    ex = _StubTradesExchange([batch1, batch2])
    cfg = CcxtTradesConfig(exchange_id="binance", symbols=["BTC/USDT"], window_size=2)
    fetcher = CcxtTradesFetcher(cfg, exchange=ex)
    df = await fetcher.fetch(60, 121, node_id="trades:binance:BTC/USDT", interval=60)
    assert len(df) == 4
    assert len(ex.calls) >= 2


@pytest.mark.asyncio
async def test_trades_fetcher_retries_then_succeeds():
    class _Flaky(_StubTradesExchange):
        def __init__(self):
            super().__init__([[{"timestamp": 60_000, "price": 10.0, "amount": 0.1}]])
            self._fail = True

        async def fetch_trades(self, symbol, since=None, limit=None):
            if self._fail:
                self._fail = False
                raise RuntimeError("rate limit")
            return await super().fetch_trades(symbol, since=since, limit=limit)

    ex = _Flaky()
    cfg = CcxtTradesConfig(exchange_id="binance", symbols=["BTC/USDT"], max_retries=2, retry_backoff_s=0.01)
    fetcher = CcxtTradesFetcher(cfg, exchange=ex)
    df = await fetcher.fetch(60, 60, node_id="trades:binance:BTC/USDT", interval=60)
    assert df["ts"].tolist() == [60]


@pytest.mark.asyncio
async def test_trades_fetcher_penalty_backoff_on_429(monkeypatch):
    orig_sleep = asyncio.sleep
    delays: list[float] = []

    async def _fake_sleep(duration, *args, **kwargs):
        delays.append(duration)
        await orig_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    class _RateLimitOnce(_StubTradesExchange):
        def __init__(self, batches, *, status_code: int = 429):
            super().__init__(batches)
            self._status_code = status_code
            self._fail = True

        async def fetch_trades(self, symbol, since=None, limit=None):
            if self._fail:
                self._fail = False
                exc = RuntimeError("too many requests")
                setattr(exc, "status_code", self._status_code)
                raise exc
            return await super().fetch_trades(symbol, since=since, limit=limit)

    rows = [[{"timestamp": 60_000, "price": 10.0, "amount": 0.1}]]
    ex = _RateLimitOnce(rows)
    cfg = CcxtTradesConfig(
        exchange_id="binance",
        symbols=["BTC/USDT"],
        max_retries=2,
        retry_backoff_s=0.1,
        rate_limiter=RateLimiterConfig(penalty_backoff_ms=500),
    )
    fetcher = CcxtTradesFetcher(cfg, exchange=ex)

    df = await fetcher.fetch(60, 60, node_id="trades:binance:BTC/USDT", interval=60)
    assert df["ts"].tolist() == [60]
    assert any(pytest.approx(0.5, rel=0.1) == d for d in delays)


@pytest.mark.asyncio
async def test_trades_fetcher_reuses_limiter(monkeypatch):
    limiter_calls = 0
    limiter = _DummyLimiter()

    async def _fake_get_limiter(key: str, **kwargs):
        nonlocal limiter_calls
        limiter_calls += 1
        return limiter

    monkeypatch.setattr(
        "qmtl.runtime.io.ccxt_fetcher.get_limiter", _fake_get_limiter
    )

    cfg = CcxtTradesConfig(
        exchange_id="binance",
        symbols=["BTC/USDT"],
        rate_limiter=RateLimiterConfig(),
    )
    ex = _StubTradesExchange([[{"timestamp": 60_000, "price": 10.0, "amount": 0.1}]])
    fetcher = CcxtTradesFetcher(cfg, exchange=ex)

    await fetcher.fetch(60, 60, node_id="trades:binance:BTC/USDT", interval=60)
    await fetcher.fetch(60, 60, node_id="trades:binance:BTC/USDT", interval=60)

    assert limiter_calls == 1


@pytest.mark.asyncio
async def test_trades_fetcher_reuses_cached_exchange(monkeypatch):
    class _FakeTradesExchange:
        instances: list["_FakeTradesExchange"] = []

        def __init__(self, options):
            self.options = options
            self.fetch_calls = 0
            self.close_calls = 0
            type(self).instances.append(self)

        async def fetch_trades(self, symbol, since=None, limit=None):
            self.fetch_calls += 1
            await asyncio.sleep(0)
            return []

        async def close(self):
            self.close_calls += 1
            await asyncio.sleep(0)

    module = types.ModuleType("ccxt.async_support")
    module.binance = _FakeTradesExchange
    parent = types.ModuleType("ccxt")
    parent.async_support = module
    monkeypatch.setitem(sys.modules, "ccxt", parent)
    monkeypatch.setitem(sys.modules, "ccxt.async_support", module)

    limiter = _DummyLimiter()

    async def _fake_get_limiter(key: str, **kwargs):
        return limiter

    monkeypatch.setattr(
        "qmtl.runtime.io.ccxt_fetcher.get_limiter", _fake_get_limiter
    )

    _FakeTradesExchange.instances.clear()

    cfg = CcxtTradesConfig(
        exchange_id="binance",
        symbols=["BTC/USDT"],
    )
    fetcher = CcxtTradesFetcher(cfg)

    await fetcher.fetch(60, 60, node_id="trades:binance:BTC/USDT", interval=60)
    await fetcher.fetch(60, 60, node_id="trades:binance:BTC/USDT", interval=60)

    assert len(_FakeTradesExchange.instances) == 1
    instance = _FakeTradesExchange.instances[0]
    assert instance.fetch_calls >= 1
    assert instance.close_calls == 2

