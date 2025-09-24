from __future__ import annotations

import asyncio
import time
import pandas as pd
import pytest

from qmtl.runtime.io.ccxt_fetcher import (
    CcxtBackfillConfig,
    CcxtOHLCVFetcher,
    RateLimiterConfig,
)


class _TimedExchange:
    def __init__(self, ts_ms: int):
        self._ts_ms = ts_ms
        self.call_times: list[float] = []

    async def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None):
        self.call_times.append(time.perf_counter())
        await asyncio.sleep(0)
        return [[self._ts_ms, 1, 1, 1, 1, 1]]

    async def close(self):  # pragma: no cover
        pass


@pytest.mark.asyncio
async def test_process_wide_rate_limit_serializes_calls_across_fetchers():
    # Two fetchers share the same exchange_id → process-wide limiter should serialize starts
    ex1 = _TimedExchange(60_000)
    ex2 = _TimedExchange(60_000)
    rl = RateLimiterConfig(max_concurrency=1, min_interval_s=0.05, scope="process")
    cfg = CcxtBackfillConfig(exchange_id="binance", symbols=["BTC/USDT"], timeframe="1m", rate_limiter=rl)
    f1 = CcxtOHLCVFetcher(cfg, exchange=ex1)
    f2 = CcxtOHLCVFetcher(cfg, exchange=ex2)

    async def _call(fetcher):
        return await fetcher.fetch(60, 60, node_id="ohlcv:binance:BTC/USDT:1m", interval=60)

    await asyncio.gather(_call(f1), _call(f2))
    times = sorted(ex1.call_times + ex2.call_times)
    assert len(times) == 2
    # Ensure ~50ms spacing with a small tolerance
    assert (times[1] - times[0]) >= 0.04

