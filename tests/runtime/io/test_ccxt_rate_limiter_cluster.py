from __future__ import annotations

import asyncio
import os
import time
import uuid
import pytest

from qmtl.runtime.io.ccxt_fetcher import (
    CcxtBackfillConfig,
    CcxtOHLCVFetcher,
    RateLimiterConfig,
)
from qmtl.runtime.io.ccxt_rate_limiter import _RedisTokenBucketLimiter
from qmtl.runtime.sdk import metrics as sdk_metrics


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


def _redis_available(url: str) -> bool:
    try:
        from redis import asyncio as aioredis  # type: ignore

        async def _ping() -> bool:
            try:
                client = aioredis.from_url(url)
                await client.ping()
                await client.close()
                return True
            except Exception:
                return False

        return asyncio.get_event_loop().run_until_complete(_ping())
    except Exception:
        return False


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _redis_available(os.getenv("QMTL_CCXT_RATE_LIMITER_REDIS", "redis://localhost:6379/0")),
    reason="Redis not available for cluster rate limiter test",
)
async def test_cluster_rate_limit_spreads_calls_across_fetchers():
    redis_url = os.getenv("QMTL_CCXT_RATE_LIMITER_REDIS", "redis://localhost:6379/0")
    ex1 = _TimedExchange(60_000)
    ex2 = _TimedExchange(60_000)
    # Use unique suffix to avoid collisions across parallel runs
    suffix = uuid.uuid4().hex
    rl = RateLimiterConfig(
        max_concurrency=1,
        min_interval_s=0.05,
        scope="cluster",
        redis_dsn=redis_url,
        burst=1,
        key_suffix=suffix,
    )
    cfg = CcxtBackfillConfig(exchange_id="binance", symbols=["BTC/USDT"], timeframe="1m", rate_limiter=rl)
    f1 = CcxtOHLCVFetcher(cfg, exchange=ex1)
    f2 = CcxtOHLCVFetcher(cfg, exchange=ex2)

    async def _call(fetcher):
        return await fetcher.fetch(60, 60, node_id="ohlcv:binance:BTC/USDT:1m", interval=60)

    await asyncio.gather(_call(f1), _call(f2))
    times = sorted(ex1.call_times + ex2.call_times)
    assert len(times) == 2
    assert (times[1] - times[0]) >= 0.04


class _StubPipeline:
    def __init__(self, redis: "_StubRedis") -> None:
        self._redis = redis
        self._calls: list[tuple[str, str]] = []

    def hget(self, key: str, field: str) -> None:
        self._calls.append((key, field))

    async def execute(self) -> tuple[float | None, float | None]:
        return tuple(self._redis.hget(key, field) for key, field in self._calls)


class _StubRedis:
    def __init__(self, tokens: float) -> None:
        self.store: dict[str, float] = {"tokens": tokens, "ts": 0.0}
        self.expire_calls: list[tuple[str, int]] = []

    async def time(self) -> tuple[int, int]:
        return (0, 0)

    def pipeline(self) -> _StubPipeline:
        return _StubPipeline(self)

    async def hset(self, key: str, mapping: dict[str, float]) -> None:
        self.store.update(mapping)

    async def expire(self, key: str, ttl: int) -> None:
        self.expire_calls.append((key, ttl))

    def hget(self, key: str, field: str) -> float | None:
        return self.store.get(field)


@pytest.mark.asyncio
async def test_cluster_rate_limiter_records_metrics() -> None:
    sdk_metrics.reset_metrics()
    redis = _StubRedis(tokens=0.5)
    limiter = _RedisTokenBucketLimiter(
        redis=redis,
        bucket_key="rl:test",
        tokens_per_sec=1.0,
        capacity=2,
        local_concurrency=1,
    )

    allowed = await limiter._reserve_token()
    assert allowed is False
    metric_key = ("rl:test", "default")
    assert (
        sdk_metrics.seamless_rl_dropped_total._vals[metric_key] == 1  # type: ignore[attr-defined]
    )
    assert sdk_metrics.seamless_rl_tokens_available._vals[metric_key] == 0.5  # type: ignore[attr-defined]

    redis.store["tokens"] = 1.5
    allowed = await limiter._reserve_token()
    assert allowed is True
    assert pytest.approx(0.5) == sdk_metrics.seamless_rl_tokens_available._vals[metric_key]  # type: ignore[attr-defined]

