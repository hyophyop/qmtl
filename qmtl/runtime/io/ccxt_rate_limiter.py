from __future__ import annotations

"""Process-wide shared rate limiter for CCXT calls.

This module provides a per-exchange limiter to coordinate requests across
multiple fetchers within a single Python process. For distributed (multi-host)
coordination, consider extending this with a Redis-backed token bucket.
"""

from dataclasses import dataclass
import asyncio
import time
from typing import Dict, Any

from qmtl.runtime.sdk import metrics as sdk_metrics

try:  # Optional at runtime; required for cluster scope
    from redis import asyncio as aioredis  # type: ignore
except Exception:  # pragma: no cover - import guarded for environments without redis
    aioredis = None  # type: ignore


@dataclass(slots=True)
class _LimiterShape:
    max_concurrency: int
    min_interval_s: float


class _SharedLimiter:
    def __init__(self, *, max_concurrency: int, min_interval_s: float) -> None:
        self._sem = asyncio.Semaphore(max(1, int(max_concurrency)))
        self._min_interval_s = max(0.0, float(min_interval_s))
        self._last_call_at: float = 0.0
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "_SharedLimiter":
        await self._sem.acquire()
        # Enforce minimum gap between request starts
        if self._min_interval_s > 0:
            async with self._lock:
                now = time.perf_counter()
                elapsed = now - self._last_call_at
                if elapsed < self._min_interval_s:
                    await asyncio.sleep(self._min_interval_s - elapsed)
                # mark start time to space subsequent calls
                self._last_call_at = time.perf_counter()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._sem.release()


_REGISTRY: Dict[str, _SharedLimiter] = {}
_SHAPES: Dict[str, _LimiterShape] = {}
_REGISTRY_LOCK = asyncio.Lock()


async def get_shared_limiter(
    key: str, *, max_concurrency: int, min_interval_s: float
) -> _SharedLimiter:
    """Return a process-wide limiter identified by ``key``.

    First configuration applied for a ``key`` wins. Subsequent calls with
    different shapes are ignored to avoid runtime surprises.
    """
    # Include shape in the registry key to avoid cross-test/process-wide
    # collisions where an earlier configuration for the same logical key
    # (e.g., exchange id) would dictate the shape for the entire process.
    # This mirrors the cluster-scope cache behavior below.
    reg_key = f"{key}|{int(max_concurrency)}|{float(min_interval_s)}"
    if reg_key in _REGISTRY:
        return _REGISTRY[reg_key]
    async with _REGISTRY_LOCK:
        if reg_key in _REGISTRY:
            return _REGISTRY[reg_key]
        limiter = _SharedLimiter(
            max_concurrency=max_concurrency, min_interval_s=min_interval_s
        )
        _REGISTRY[reg_key] = limiter
        _SHAPES[reg_key] = _LimiterShape(max_concurrency, min_interval_s)
        return limiter


class _LocalLimiter(_SharedLimiter):
    """Local (per-instance) limiter using the same mechanics."""

    pass


class _RedisTokenBucketLimiter:
    """Redis-backed token bucket limiter (cluster scope).

    Simple cluster-wide limiter that enforces an average rate across processes
    by consuming tokens from a bucket stored in Redis. It also includes a local
    semaphore to limit per-process concurrency.
    """

    def __init__(
        self,
        *,
        redis: Any,
        bucket_key: str,
        tokens_per_sec: float,
        capacity: int,
        local_concurrency: int,
    ) -> None:
        self._redis = redis
        self._key = bucket_key
        self._rate = float(max(0.000001, tokens_per_sec))
        self._cap = int(max(1, capacity))
        self._sem = asyncio.Semaphore(max(1, local_concurrency))

    async def __aenter__(self) -> "_RedisTokenBucketLimiter":
        await self._sem.acquire()
        # Spin until a token is granted
        backoff = 0.001
        while True:
            allowed = await self._reserve_token()
            if allowed:
                return self
            await asyncio.sleep(backoff)
            # exponential backoff capped to 100ms
            backoff = min(0.1, backoff * 2)

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self._sem.release()

    async def _reserve_token(self) -> bool:
        # Use Redis TIME for a stable time source
        try:
            now_sec, now_usec = await self._redis.time()
        except Exception:
            # Fallback to local time (best effort)
            t = time.time()
            now_sec, now_usec = int(t), int((t - int(t)) * 1_000_000)
        now_ms = now_sec * 1000 + (now_usec // 1000)

        # Stored as hash fields: tokens (float), ts (ms)
        pipe = self._redis.pipeline()
        pipe.hget(self._key, "tokens")
        pipe.hget(self._key, "ts")
        tokens_raw, ts_raw = await pipe.execute()

        try:
            tokens = float(tokens_raw) if tokens_raw is not None else float(self._cap)
            last_ms = int(ts_raw) if ts_raw is not None else now_ms
        except Exception:
            tokens = float(self._cap)
            last_ms = now_ms

        # Refill based on elapsed time
        elapsed_ms = max(0, now_ms - last_ms)
        refill = (elapsed_ms / 1000.0) * self._rate
        tokens = min(self._cap, tokens + refill)
        allowed = tokens >= 1.0
        if allowed:
            tokens -= 1.0

        # Update back
        await self._redis.hset(self._key, mapping={"tokens": tokens, "ts": now_ms})
        # Set an expiry to avoid stale keys (10 minutes)
        await self._redis.expire(self._key, 600)
        sdk_metrics.observe_rate_limiter_tokens(
            limiter=self._key,
            tokens=tokens,
            capacity=self._cap,
        )
        if not allowed:
            sdk_metrics.observe_rate_limiter_drop(limiter=self._key)
        return allowed


_CLUSTER_CACHE: Dict[str, _RedisTokenBucketLimiter] = {}


async def get_limiter(
    key: str,
    *,
    max_concurrency: int,
    min_interval_s: float,
    scope: str,
    redis_dsn: str | None = None,
    tokens_per_interval: float | None = None,
    interval_ms: int | None = None,
    burst_tokens: int | None = None,
    local_semaphore: int | None = None,
    key_suffix: str | None = None,
) -> _SharedLimiter | _RedisTokenBucketLimiter:
    if scope == "local":
        return _LocalLimiter(
            max_concurrency=max_concurrency, min_interval_s=min_interval_s
        )
    if scope == "cluster":
        if aioredis is None:  # pragma: no cover - dependency missing
            raise RuntimeError(
                "redis is required for cluster scope rate limiting; install redis"
            )
        # Compose full bucket key; allow suffix to partition by account/scope
        bucket_key = f"rl:{key}"
        if key_suffix:
            bucket_key = f"{bucket_key}:{key_suffix}"
        interval_ms_val = int(interval_ms) if interval_ms is not None else None
        if interval_ms_val is not None:
            interval_ms_val = max(1, interval_ms_val)
        rate: float
        capacity: int
        if tokens_per_interval is not None and interval_ms_val is not None:
            window_s = interval_ms_val / 1000.0
            rate = float(tokens_per_interval) / max(0.001, window_s)
            capacity = int(
                max(
                    1,
                    int(burst_tokens)
                    if burst_tokens is not None
                    else int(tokens_per_interval),
                )
            )
        else:
            rate = float(
                tokens_per_interval
                if tokens_per_interval is not None
                else (1.0 / max(0.000001, min_interval_s))
            )
            capacity = int(
                max(1, int(burst_tokens) if burst_tokens is not None else 1)
            )
        local_limit = int(
            max(
                1,
                int(local_semaphore) if local_semaphore is not None else max_concurrency,
            )
        )

        # Cache a limiter per (bucket_key, rate, capacity, concurrency)
        cache_key = f"{bucket_key}|{rate}|{capacity}|{local_limit}"
        if cache_key in _CLUSTER_CACHE:
            return _CLUSTER_CACHE[cache_key]

        # Resolve Redis DSN from argument or environment
        import os  # local import to avoid global dependency at import time
        dsn = redis_dsn or os.getenv("QMTL_CCXT_RATE_LIMITER_REDIS") or "redis://localhost:6379/0"

        client = aioredis.from_url(dsn, encoding=None, decode_responses=False)
        limiter = _RedisTokenBucketLimiter(
            redis=client,
            bucket_key=bucket_key,
            tokens_per_sec=rate,
            capacity=capacity,
            local_concurrency=local_limit,
        )
        _CLUSTER_CACHE[cache_key] = limiter
        return limiter
    # Default: process-wide
    return await get_shared_limiter(
        key, max_concurrency=max_concurrency, min_interval_s=min_interval_s
    )


__all__ = [
    "get_limiter",
]
