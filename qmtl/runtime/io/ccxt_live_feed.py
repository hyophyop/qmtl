from __future__ import annotations

"""ccxt.pro-based WebSocket live feed (draft).

This module provides a LiveDataFeed implementation that streams OHLCV or Trades
via ccxt.pro when available. Imports are lazy and guarded so environments
without ccxt.pro can still import this module without error; functionality is
enabled only when subscribe() is called and ccxt.pro can be imported.

Scope
-----
- Draft-quality: focuses on correctness and resilience with simple backoff.
- Supports two modes: "ohlcv" (watch_ohlcv) and "trades" (watch_trades).
- Filters out building candle by default (emits closed candles only).
"""

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator, Literal, Optional
import logging
import time

import pandas as pd

from qmtl.runtime.sdk.ohlcv_nodeid import parse as _parse_ohlcv_node_id
from qmtl.runtime.sdk.seamless_data_provider import LiveDataFeed
from .ccxt_fetcher import _try_parse_timeframe_s as _tf_to_seconds


log = logging.getLogger(__name__)


@dataclass(slots=True)
class CcxtProConfig:
    exchange_id: str
    symbols: list[str] | None = None
    timeframe: str | None = None  # required for OHLCV mode
    mode: str = "ohlcv"  # or "trades"
    sandbox: bool = False
    reconnect_backoff_ms: list[int] | None = None
    reconnect_backoff_s: float = 1.0
    max_backoff_s: float = 30.0
    dedupe: bool = True  # drop duplicate candles/trades by ts
    dedupe_by: Literal["ts", "ts+symbol"] = "ts"
    emit_building_candle: bool = False  # if False, emit only fully closed bars


class CcxtProLiveFeed(LiveDataFeed):
    """LiveDataFeed powered by ccxt.pro websockets (draft).

    Notes
    -----
    - Uses `watch_ohlcv` / `watch_trades` when supported by the exchange.
    - Reconnects with exponential backoff on failures.
    - For OHLCV, by default emits only closed candles based on `interval`.
    """

    def __init__(self, config: CcxtProConfig, *, exchange: Any | None = None) -> None:
        self.config = config
        self._exchange = exchange  # optionally injected (tests)
        self._subs: dict[str, bool] = {}
        self._last_emitted_token: dict[str, int | tuple[int, str]] = {}

    async def is_live_available(self, *, node_id: str, interval: int) -> bool:  # type: ignore[override]
        try:
            ex = await self._get_or_create_exchange()
        except Exception:
            return False
        mode = self._mode_for_node(node_id)
        if mode == "ohlcv":
            return hasattr(ex, "watch_ohlcv")
        return hasattr(ex, "watch_trades")

    async def subscribe(self, *, node_id: str, interval: int) -> AsyncIterator[tuple[int, pd.DataFrame]]:  # type: ignore[override]
        parsed = _parse_ohlcv_node_id(node_id)
        symbol = parsed[1] if parsed else None
        tf = parsed[2] if parsed else None
        mode = self._mode_for_node(node_id)
        symbol = symbol or (self.config.symbols[0] if self.config.symbols else None)
        if not symbol:
            raise ValueError("CcxtProLiveFeed requires symbol in node_id or config.symbols")
        timeframe = tf or self.config.timeframe
        if mode == "ohlcv" and not timeframe:
            raise ValueError("OHLCV mode requires timeframe (from node_id or config)")
        key = f"{node_id}:{symbol}:{timeframe or ''}:{mode}:{int(interval)}"
        self._subs[key] = True

        schedule = self._build_backoff_schedule()
        backoff = max(0.1, float(self.config.reconnect_backoff_s))
        max_backoff = max(backoff, float(self.config.max_backoff_s))
        schedule_index = 0

        while self._subs.get(key, False):
            ex = None
            try:
                ex = await self._get_or_create_exchange()
                if mode == "ohlcv":
                    async for ts, df in self._stream_ohlcv(ex, symbol, timeframe or "1m", interval, key):
                        yield ts, df
                else:
                    async for ts, df in self._stream_trades(ex, symbol, interval, key):
                        yield ts, df
                # Normal termination (unsubscribe)
                break
            except asyncio.CancelledError:  # pragma: no cover - cooperative cancel
                raise
            except Exception as exc:
                if not self._subs.get(key, False):
                    break
                log.warning("ccxtpro.live_feed.error; will reconnect", extra={
                    "node_id": node_id,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "mode": mode,
                    "error": str(exc),
                })
                delay = None
                if schedule:
                    idx = min(schedule_index, len(schedule) - 1)
                    delay = schedule[idx]
                    schedule_index += 1
                else:
                    delay = backoff
                    backoff = min(max_backoff, backoff * 2.0)
                await asyncio.sleep(delay)
            finally:
                # no explicit close; ccxt.pro manages WS per instance; users may call .close()
                pass

        # cleanup
        self._subs.pop(key, None)

    async def _stream_ohlcv(
        self,
        exchange: Any,
        symbol: str,
        timeframe: str,
        interval: int,
        key: str,
    ) -> AsyncIterator[tuple[int, pd.DataFrame]]:
        last_token = self._last_emitted_token.get(key)
        interval_s = int(interval if interval > 0 else _tf_to_seconds(timeframe))
        # resolve method name once
        watch = getattr(exchange, "watch_ohlcv", None) or getattr(exchange, "watchOHLCV", None)
        if watch is None:
            raise RuntimeError("exchange does not support watch_ohlcv/watchOHLCV")
        while self._subs.get(key, False):
            rows = await watch(symbol, timeframe)
            # rows is a list of candles [[ms, o, h, l, c, v], ...]
            now_s = int(time.time())
            ready_records: list[dict] = []
            for r in (rows or []):
                try:
                    ts = int(r[0]) // 1000
                except Exception:
                    continue
                token = self._dedupe_token(ts, symbol)
                if self.config.dedupe and not self._should_emit(last_token, token):
                    continue
                if not self.config.emit_building_candle:
                    # Only emit when we are past the close boundary of the bar
                    if ts + interval_s > now_s:
                        continue
                rec = {
                    "ts": ts,
                    "open": float(r[1]),
                    "high": float(r[2]),
                    "low": float(r[3]),
                    "close": float(r[4]),
                    "volume": float(r[5]),
                }
                if self._uses_symbol_dedupe():
                    rec["symbol"] = symbol
                ready_records.append(rec)
                if self.config.dedupe:
                    last_token = token

            if not ready_records:
                # yield nothing; let outer loop iterate again
                await asyncio.sleep(0)
                continue

            df = pd.DataFrame.from_records(ready_records)
            df = df.drop_duplicates(subset=self._dedupe_subset())
            df = df.sort_values("ts")
            last_ts = int(df["ts"].iloc[-1])
            if self._uses_symbol_dedupe():
                symbol_value = str(df.iloc[-1]["symbol"])
                last_token = (last_ts, symbol_value)
            else:
                last_token = last_ts
            self._last_emitted_token[key] = last_token
            yield last_ts, df

    async def _stream_trades(
        self,
        exchange: Any,
        symbol: str,
        interval: int,
        key: str,
    ) -> AsyncIterator[tuple[int, pd.DataFrame]]:
        last_token = self._last_emitted_token.get(key)
        watch = getattr(exchange, "watch_trades", None) or getattr(exchange, "watchTrades", None)
        if watch is None:
            raise RuntimeError("exchange does not support watch_trades/watchTrades")
        while self._subs.get(key, False):
            trades = await watch(symbol)
            if not trades:
                await asyncio.sleep(0)
                continue
            records: list[dict] = []
            for t in trades:
                try:
                    ts = int(t.get("timestamp")) // 1000
                except Exception:
                    continue
                token = self._dedupe_token(ts, symbol)
                if self.config.dedupe and not self._should_emit(last_token, token):
                    continue
                rec = {"ts": ts}
                if "price" in t:
                    rec["price"] = float(t["price"])  # type: ignore[arg-type]
                if "amount" in t:
                    rec["amount"] = float(t["amount"])  # type: ignore[arg-type]
                if "side" in t:
                    rec["side"] = t["side"]
                if self._uses_symbol_dedupe():
                    rec["symbol"] = symbol
                records.append(rec)
                if self.config.dedupe:
                    last_token = token

            if not records:
                await asyncio.sleep(0)
                continue

            df = pd.DataFrame.from_records(records)
            df = df.drop_duplicates(subset=self._dedupe_subset())
            df = df.sort_values("ts")
            last_ts = int(df["ts"].iloc[-1])
            if self._uses_symbol_dedupe():
                symbol_value = str(df.iloc[-1]["symbol"])
                last_token = (last_ts, symbol_value)
            else:
                last_token = last_ts
            self._last_emitted_token[key] = last_token
            yield last_ts, df

    def _mode_for_node(self, node_id: str) -> str:
        if node_id.startswith("ohlcv:"):
            return "ohlcv"
        if node_id.startswith("trades:"):
            return "trades"
        # fallback to config
        return (self.config.mode or "ohlcv").lower()

    async def _get_or_create_exchange(self) -> Any:
        if self._exchange is not None:
            return self._exchange
        # Lazy, guarded import of ccxt.pro
        ccxtpro: Optional[Any] = None
        try:  # pragma: no cover - optional dependency
            import ccxt.pro as ccxtpro  # type: ignore
        except Exception:
            try:  # pragma: no cover - alternative name
                import ccxtpro  # type: ignore
            except Exception as e:  # noqa: F841
                raise RuntimeError(
                    "ccxt.pro is required for CcxtProLiveFeed; install ccxtpro or ccxt.pro"
                )
        eid = self.config.exchange_id.lower()
        if not hasattr(ccxtpro, eid):
            raise ValueError(f"Unknown ccxt.pro exchange id: {eid}")
        klass = getattr(ccxtpro, eid)
        ex = klass({"enableRateLimit": True, "newUpdates": True})
        # best-effort sandbox mode
        try:
            if self.config.sandbox and hasattr(ex, "set_sandbox_mode"):
                ex.set_sandbox_mode(True)  # type: ignore[attr-defined]
        except Exception:
            try:
                if self.config.sandbox and hasattr(ex, "setSandboxMode"):
                    getattr(ex, "setSandboxMode")(True)
            except Exception:
                pass
        # best-effort market metadata
        try:
            if hasattr(ex, "load_markets"):
                await ex.load_markets()
        except Exception:
            pass
        self._exchange = ex
        return ex

    def _build_backoff_schedule(self) -> list[float]:
        values = self.config.reconnect_backoff_ms or []
        schedule: list[float] = []
        for raw in values:
            try:
                delay = max(0.0, float(raw) / 1000.0)
            except (TypeError, ValueError):
                continue
            schedule.append(delay)
        return schedule

    def _dedupe_mode(self) -> str:
        return (self.config.dedupe_by or "ts").lower()

    def _uses_symbol_dedupe(self) -> bool:
        return self._dedupe_mode() == "ts+symbol"

    def _dedupe_subset(self) -> list[str]:
        if self._uses_symbol_dedupe():
            return ["ts", "symbol"]
        return ["ts"]

    def _dedupe_token(self, ts: int, symbol: str | None) -> int | tuple[int, str]:
        if self._uses_symbol_dedupe():
            return ts, symbol or ""
        return ts

    @staticmethod
    def _should_emit(
        last_token: int | tuple[int, str] | None,
        current_token: int | tuple[int, str],
    ) -> bool:
        if last_token is None:
            return True
        last_ts = last_token[0] if isinstance(last_token, tuple) else last_token
        current_ts = current_token[0] if isinstance(current_token, tuple) else current_token
        if current_ts < last_ts:
            return False
        if current_ts > last_ts:
            return True
        if isinstance(last_token, tuple) and isinstance(current_token, tuple):
            return (current_token[1] or "") != (last_token[1] or "")
        return False

    async def close(self) -> None:
        ex = self._exchange
        self._exchange = None
        if not ex:
            return
        close = getattr(ex, "close", None)
        if asyncio.iscoroutinefunction(close):  # type: ignore[arg-type]
            try:
                await close()  # type: ignore[misc]
            except Exception:
                pass

    def unsubscribe(self, *, node_id: str, interval: int) -> None:
        """Signal the subscribe loop to stop for a given node/interval."""
        # We may not know the exact key (symbol/timeframe). Use prefix match.
        prefix = f"{node_id}:"
        for k in list(self._subs.keys()):
            if k.startswith(prefix):
                self._subs[k] = False


__all__ = ["CcxtProLiveFeed", "CcxtProConfig"]
