from __future__ import annotations

"""CCXT-based DataFetcher implementations for OHLCV (and future Trades).

This module is optional and only imported when used. It provides a thin
asynchronous wrapper around ``ccxt.async_support`` to return DataFrames in the
SDK's standard schema with a ``ts`` (seconds) column.
"""

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence
import asyncio
import time

import pandas as pd

from qmtl.runtime.sdk.data_io import DataFetcher


@dataclass(slots=True)
class RateLimiterConfig:
    """Simple rate limiter configuration.

    Attributes
    ----------
    max_concurrency:
        Maximum number of in-flight CCXT requests.
    min_interval_s:
        Minimum seconds between consecutive requests (best-effort).
    """

    max_concurrency: int = 1
    min_interval_s: float = 0.0
    # scope: "local" → per-fetcher only; "process" → share across fetchers in-process;
    # "cluster" → Redis-backed shared limiter across processes
    scope: str = "process"
    # Cluster options (when scope="cluster"): if not provided, sensible defaults are derived
    redis_dsn: str | None = None
    tokens_per_sec: float | None = None  # if None, 1/min_interval_s
    burst: int | None = None  # capacity; default=1
    key_suffix: str | None = None  # e.g., account id


@dataclass(slots=True)
class CcxtBackfillConfig:
    exchange_id: str
    symbols: list[str] | None
    timeframe: str
    window_size: int = 1000  # max candles per request
    max_retries: int = 3
    retry_backoff_s: float = 0.5
    rate_limiter: RateLimiterConfig = field(default_factory=RateLimiterConfig)


def _try_parse_timeframe_s(timeframe: str) -> int:
    """Return seconds for a CCXT timeframe string.

    Tries ``ccxt.parse_timeframe`` when available; falls back to a static map.
    """
    try:  # pragma: no cover - optional dependency path
        import ccxt  # type: ignore

        seconds = int(getattr(ccxt, "parse_timeframe")(timeframe))
        if seconds > 0:
            return seconds
    except Exception:
        pass

    table = {
        "1s": 1,
        "5s": 5,
        "10s": 10,
        "15s": 15,
        "30s": 30,
        "1m": 60,
        "3m": 180,
        "5m": 300,
        "15m": 900,
        "30m": 1800,
        "1h": 3600,
        "2h": 7200,
        "4h": 14400,
        "6h": 21600,
        "8h": 28800,
        "12h": 43200,
        "1d": 86400,
        "3d": 259200,
        "1w": 604800,
    }
    if timeframe not in table:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return table[timeframe]


def _parse_symbol_from_node_id(node_id: str) -> tuple[str | None, str | None]:
    """Extract ``(symbol, timeframe)`` from a conventional node_id if present.

    Expected patterns (best-effort):
      - "ohlcv:{exchange}:{symbol}:{timeframe}"
      - "{symbol}:{timeframe}"
    Returns (None, None) when not parseable.
    """
    parts = node_id.split(":")
    if len(parts) >= 4 and parts[0] == "ohlcv":
        return parts[2], parts[3]
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return None, None


from .ccxt_rate_limiter import get_limiter


class CcxtOHLCVFetcher(DataFetcher):
    """Asynchronous OHLCV fetcher backed by ccxt.async_support.

    Notes
    -----
    - ``ccxt`` is imported lazily. Tests may inject a fake ``exchange`` object to
      avoid the dependency.
    - Returns a DataFrame with columns: ``ts, open, high, low, close, volume``.
    """

    def __init__(
        self,
        config: CcxtBackfillConfig,
        *,
        exchange: Any | None = None,
    ) -> None:
        self.config = config
        self._exchange = exchange
        self._limiter = None  # created lazily

    # ------------------------------------------------------------------
    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        symbol, tf_from_node = _parse_symbol_from_node_id(node_id)
        symbol = symbol or (self.config.symbols[0] if self.config.symbols else None)
        timeframe = tf_from_node or self.config.timeframe
        if not symbol:
            raise ValueError("symbol not provided in config and not parseable from node_id")

        step_s = _try_parse_timeframe_s(timeframe)
        # Trust caller-supplied interval alignment, but guard gross mismatches
        if interval and step_s and interval % step_s != 0:
            # Allow submultiples; primary alignment responsibility remains with caller
            pass

        rows: list[list[Any]] = []
        ex = await self._get_or_create_exchange()
        try:
            start_ms = max(0, int(start) * 1000)
            end_ms = max(0, int(end) * 1000)
            step_ms = step_s * 1000

            cursor = start_ms
            hard_cap = 500_000  # safety valve against infinite loops
            while cursor <= end_ms and hard_cap > 0:
                hard_cap -= 1
                remaining = end_ms - cursor
                if remaining < 0:
                    break
                max_points = remaining // step_ms + 1
                limit = int(min(self.config.window_size, max(1, max_points)))
                batch = await self._fetch_ohlcv_with_retry(ex, symbol, timeframe, cursor, limit)
                if not batch:
                    break
                rows.extend(batch)
                last_ms = int(batch[-1][0])
                next_cursor = last_ms + step_ms
                if next_cursor <= cursor:
                    break
                cursor = next_cursor
        finally:
            await self._maybe_close_exchange(ex)

        # Normalize
        normalized = self._normalize_ohlcv(rows, start, end)
        return normalized

    # ------------------------------------------------------------------
    async def _fetch_ohlcv_with_retry(
        self,
        exchange: Any,
        symbol: str,
        timeframe: str,
        since_ms: int,
        limit: int,
    ) -> Sequence[Sequence[Any]]:
        attempt = 0
        backoff = self.config.retry_backoff_s
        while True:
            attempt += 1
            try:
                limiter = await self._ensure_limiter()
                async with limiter:
                    data = await exchange.fetch_ohlcv(
                        symbol, timeframe, since=since_ms, limit=limit
                    )
                    return data or []
            except Exception:  # pragma: no cover - error path exercised in tests via stub
                if attempt >= max(1, self.config.max_retries):
                    raise
                await asyncio.sleep(backoff)
                backoff *= 2.0

    async def _ensure_limiter(self):
        if self._limiter is not None:
            return self._limiter
        key = f"ccxt:{self.config.exchange_id.lower()}"
        rl = self.config.rate_limiter
        self._limiter = await get_limiter(
            key,
            max_concurrency=rl.max_concurrency,
            min_interval_s=rl.min_interval_s,
            scope=str(getattr(rl, "scope", "process")),
            redis_dsn=getattr(rl, "redis_dsn", None),
            tokens_per_sec=getattr(rl, "tokens_per_sec", None),
            burst=getattr(rl, "burst", None),
            key_suffix=getattr(rl, "key_suffix", None),
        )
        return self._limiter

    # ------------------------------------------------------------------
    async def _get_or_create_exchange(self) -> Any:
        if self._exchange is not None:
            return self._exchange
        # Lazy import to keep ccxt optional
        try:  # pragma: no cover - import path
            import ccxt.async_support as ccxt_async  # type: ignore
        except Exception as e:  # pragma: no cover - exercised when ccxt missing
            raise RuntimeError("ccxt is required for CcxtOHLCVFetcher; install with [ccxt]") from e

        eid = self.config.exchange_id.lower()
        if not hasattr(ccxt_async, eid):
            raise ValueError(f"Unknown ccxt exchange id: {eid}")
        klass = getattr(ccxt_async, eid)
        self._exchange = klass({"enableRateLimit": True})
        return self._exchange

    async def _maybe_close_exchange(self, exchange: Any) -> None:
        if exchange is not self._exchange:
            # external exchange injected by tests; don't close
            return
        close = getattr(exchange, "close", None)
        if asyncio.iscoroutinefunction(close):  # type: ignore[arg-type]
            try:
                await close()  # type: ignore[misc]
            except Exception:  # pragma: no cover - best-effort close
                pass

    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_ohlcv(rows: Iterable[Sequence[Any]], start: int, end: int) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame()
        records = []
        for r in rows:
            if not r:
                continue
            # CCXT OHLCV: [ timestamp(ms), open, high, low, close, volume, ... ]
            ts = int(r[0]) // 1000
            if ts < start or ts > end:
                continue
            rec = {
                "ts": ts,
                "open": float(r[1]),
                "high": float(r[2]),
                "low": float(r[3]),
                "close": float(r[4]),
                "volume": float(r[5]),
            }
            records.append(rec)
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame.from_records(records)
        # Deduplicate on ts and sort
        df = df.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
        return df


@dataclass(slots=True)
class CcxtTradesConfig:
    exchange_id: str
    symbols: list[str] | None
    window_size: int = 1000  # max trades per request
    max_retries: int = 3
    retry_backoff_s: float = 0.5
    rate_limiter: RateLimiterConfig = field(default_factory=RateLimiterConfig)


class CcxtTradesFetcher(DataFetcher):
    """Asynchronous Trades fetcher backed by ccxt.async_support.

    Returns a DataFrame with at least: ``ts, price, amount``. ``side`` is
    included when available. This is a stub suitable for unit testing and
    incremental integration; production-hardening (e.g., pagination nuances
    across exchanges) can be added iteratively.
    """

    def __init__(
        self,
        config: CcxtTradesConfig,
        *,
        exchange: Any | None = None,
    ) -> None:
        self.config = config
        self._exchange = exchange
        self._limiter = None

    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        symbol, _ = _parse_symbol_from_node_id(node_id)
        symbol = symbol or (self.config.symbols[0] if self.config.symbols else None)
        if not symbol:
            raise ValueError("symbol not provided in config and not parseable from node_id")

        ex = await self._get_or_create_exchange()
        rows: list[dict] = []
        try:
            start_ms = max(0, int(start) * 1000)
            end_ms = max(0, int(end) * 1000)
            cursor = start_ms
            hard_cap = 1_000_000  # generous safety valve
            while cursor <= end_ms and hard_cap > 0:
                hard_cap -= 1
                limit = int(max(1, min(self.config.window_size, 1000)))
                batch = await self._fetch_trades_with_retry(ex, symbol, cursor, limit)
                if not batch:
                    break
                # ccxt returns list of dict-like trade objects
                rows.extend(batch)
                last_ms = int(batch[-1].get("timestamp", cursor))
                next_cursor = last_ms + 1
                if next_cursor <= cursor:
                    break
                cursor = next_cursor
                if cursor > end_ms:
                    break
        finally:
            await self._maybe_close_exchange(ex)

        return self._normalize_trades(rows, start, end)

    async def _fetch_trades_with_retry(
        self, exchange: Any, symbol: str, since_ms: int, limit: int
    ) -> list[dict]:
        attempt = 0
        backoff = self.config.retry_backoff_s
        while True:
            attempt += 1
            try:
                limiter = await self._ensure_limiter()
                async with limiter:
                    data = await exchange.fetch_trades(
                        symbol, since=since_ms, limit=limit
                    )
                    return list(data or [])
            except Exception:  # pragma: no cover - error path in stub tests
                if attempt >= max(1, self.config.max_retries):
                    raise
                await asyncio.sleep(backoff)
                backoff *= 2.0

    async def _ensure_limiter(self):
        if self._limiter is not None:
            return self._limiter
        key = f"ccxt:{self.config.exchange_id.lower()}"
        rl = self.config.rate_limiter
        self._limiter = await get_limiter(
            key,
            max_concurrency=rl.max_concurrency,
            min_interval_s=rl.min_interval_s,
            scope=str(getattr(rl, "scope", "process")),
            redis_dsn=getattr(rl, "redis_dsn", None),
            tokens_per_sec=getattr(rl, "tokens_per_sec", None),
            burst=getattr(rl, "burst", None),
            key_suffix=getattr(rl, "key_suffix", None),
        )
        return self._limiter

    async def _get_or_create_exchange(self) -> Any:
        if self._exchange is not None:
            return self._exchange
        try:  # pragma: no cover - import path
            import ccxt.async_support as ccxt_async  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("ccxt is required for CcxtTradesFetcher; install with [ccxt]") from e
        eid = self.config.exchange_id.lower()
        if not hasattr(ccxt_async, eid):
            raise ValueError(f"Unknown ccxt exchange id: {eid}")
        klass = getattr(ccxt_async, eid)
        self._exchange = klass({"enableRateLimit": True})
        return self._exchange

    async def _maybe_close_exchange(self, exchange: Any) -> None:
        if exchange is not self._exchange:
            return
        close = getattr(exchange, "close", None)
        if asyncio.iscoroutinefunction(close):  # type: ignore[arg-type]
            try:
                await close()  # type: ignore[misc]
            except Exception:  # pragma: no cover
                pass

    @staticmethod
    def _normalize_trades(rows: Iterable[dict], start: int, end: int) -> pd.DataFrame:
        if not rows:
            return pd.DataFrame()
        records = []
        for tr in rows:
            try:
                ts = int(tr.get("timestamp")) // 1000
            except Exception:
                continue
            if ts < start or ts > end:
                continue
            rec = {"ts": ts}
            if "price" in tr:
                rec["price"] = float(tr["price"])  # type: ignore[arg-type]
            if "amount" in tr:
                rec["amount"] = float(tr["amount"])  # type: ignore[arg-type]
            if "side" in tr:
                rec["side"] = tr["side"]
            records.append(rec)
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame.from_records(records)
        df = df.sort_values(["ts"]).reset_index(drop=True)
        return df


__all__ = [
    "CcxtBackfillConfig",
    "RateLimiterConfig",
    "CcxtOHLCVFetcher",
    "CcxtTradesConfig",
    "CcxtTradesFetcher",
]
