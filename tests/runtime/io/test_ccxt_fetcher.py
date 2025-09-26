from __future__ import annotations

import asyncio
import pandas as pd
import pytest

from qmtl.runtime.io.ccxt_fetcher import (
    CcxtBackfillConfig,
    CcxtOHLCVFetcher,
    RateLimiterConfig,
)


class _StubExchange:
    def __init__(self, batches):
        self._batches = list(batches)
        self.calls = []

    async def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        self.calls.append((symbol, timeframe, since, limit))
        # Pop next batch or return empty
        if not self._batches:
            return []
        batch = self._batches.pop(0)
        # Simulate async
        await asyncio.sleep(0)
        return batch

    async def close(self):  # pragma: no cover - best-effort close in tests
        await asyncio.sleep(0)


class _RateLimitOnceExchange(_StubExchange):
    def __init__(self, batches, *, status_code: int = 429):
        super().__init__(batches)
        self._status_code = status_code
        self._fail = True

    async def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        if self._fail:
            self._fail = False
            exc = RuntimeError("too many requests")
            setattr(exc, "status_code", self._status_code)
            raise exc
        return await super().fetch_ohlcv(symbol, timeframe, since, limit)


@pytest.mark.asyncio
async def test_ccxt_fetcher_normalizes_rows_and_filters_range():
    # Frames across 60..180 seconds; include an out-of-range row (30s) and duplicate
    rows = [
        [30_000, 1, 1, 1, 1, 1],
        [60_000, 1, 2, 0.5, 1.5, 10],
        [120_000, 2, 3, 1, 2.5, 11],
        [120_000, 2, 3, 1, 2.5, 11],  # duplicate ts
        [180_000, 3, 4, 2, 3.5, 12],
    ]
    ex = _StubExchange([rows])
    cfg = CcxtBackfillConfig(
        exchange_id="binance",
        symbols=["BTC/USDT"],
        timeframe="1m",
        rate_limiter=RateLimiterConfig(),
    )
    fetcher = CcxtOHLCVFetcher(cfg, exchange=ex)
    df = await fetcher.fetch(60, 180, node_id="ohlcv:binance:BTC/USDT:1m", interval=60)
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]
    assert df["ts"].tolist() == [60, 120, 180]
    assert df.iloc[0]["open"] == 1


@pytest.mark.asyncio
async def test_ccxt_fetcher_chunks_requests_with_window_size():
    # Simulate two batches of 2 rows each (limit=2)
    batch1 = [[60_000, 1, 1, 1, 1, 1], [120_000, 1, 1, 1, 1, 1]]
    batch2 = [[180_000, 1, 1, 1, 1, 1], [240_000, 1, 1, 1, 1, 1]]
    ex = _StubExchange([batch1, batch2])
    cfg = CcxtBackfillConfig(
        exchange_id="binance",
        symbols=["BTC/USDT"],
        timeframe="1m",
        window_size=2,
    )
    fetcher = CcxtOHLCVFetcher(cfg, exchange=ex)
    df = await fetcher.fetch(60, 240, node_id="ohlcv:binance:BTC/USDT:1m", interval=60)
    assert df["ts"].tolist() == [60, 120, 180, 240]
    # Two calls due to window_size
    assert len(ex.calls) >= 2


@pytest.mark.asyncio
async def test_ccxt_fetcher_retries_on_error_then_succeeds():
    class _FlakyExchange(_StubExchange):
        def __init__(self):
            super().__init__([[[60_000, 1, 1, 1, 1, 1]]])
            self._fail = True

        async def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
            if self._fail:
                self._fail = False
                raise RuntimeError("rate limit")
            return await super().fetch_ohlcv(symbol, timeframe, since, limit)

    ex = _FlakyExchange()
    cfg = CcxtBackfillConfig(
        exchange_id="binance",
        symbols=["BTC/USDT"],
        timeframe="1m",
        max_retries=2,
        retry_backoff_s=0.01,
    )
    fetcher = CcxtOHLCVFetcher(cfg, exchange=ex)
    df = await fetcher.fetch(60, 60, node_id="ohlcv:binance:BTC/USDT:1m", interval=60)
    assert df["ts"].tolist() == [60]


@pytest.mark.asyncio
async def test_ccxt_fetcher_penalty_backoff_on_429(monkeypatch):
    orig_sleep = asyncio.sleep
    delays: list[float] = []

    async def _fake_sleep(duration, *args, **kwargs):
        delays.append(duration)
        await orig_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)

    rows = [[[60_000, 1, 1, 1, 1, 1]]]
    ex = _RateLimitOnceExchange(rows)
    cfg = CcxtBackfillConfig(
        exchange_id="binance",
        symbols=["BTC/USDT"],
        timeframe="1m",
        max_retries=2,
        retry_backoff_s=0.1,
        rate_limiter=RateLimiterConfig(penalty_backoff_ms=500),
    )
    fetcher = CcxtOHLCVFetcher(cfg, exchange=ex)

    df = await fetcher.fetch(60, 60, node_id="ohlcv:binance:BTC/USDT:1m", interval=60)
    assert df["ts"].tolist() == [60]
    assert any(pytest.approx(0.5, rel=0.1) == d for d in delays)

