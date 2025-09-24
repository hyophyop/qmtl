from __future__ import annotations

import asyncio
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

