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
from typing import Any, AsyncIterator, Iterable, Literal, Optional
import logging
import time

import polars as pl

from qmtl.runtime.sdk.ohlcv_nodeid import parse as _parse_ohlcv_node_id
from qmtl.runtime.sdk.seamless_data_provider import LiveDataFeed
from .ccxt_fetcher import CcxtWatchExchange, _try_parse_timeframe_s as _tf_to_seconds


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


@dataclass(slots=True)
class _SubscriptionParams:
    node_id: str
    symbol: str
    timeframe: str | None
    mode: str
    interval: int
    key: str


@dataclass(slots=True)
class _BackoffController:
    schedule: list[float]
    base_backoff: float
    max_backoff: float
    schedule_index: int = 0

    def next_delay(self) -> float:
        if self.schedule:
            idx = min(self.schedule_index, len(self.schedule) - 1)
            delay = self.schedule[idx]
            self.schedule_index += 1
            return delay
        delay = self.base_backoff
        self.base_backoff = min(self.max_backoff, self.base_backoff * 2.0)
        return delay


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
        self._exchange: CcxtWatchExchange | None = exchange  # optionally injected (tests)
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

    async def subscribe(self, *, node_id: str, interval: int) -> AsyncIterator[tuple[int, pl.DataFrame]]:  # type: ignore[override]
        params = self._build_subscription_params(node_id=node_id, interval=interval)
        backoff = self._build_backoff_controller()
        self._subs[params.key] = True
        try:
            async for ts, df in self._run_subscribe_loop(params=params, backoff=backoff):
                yield ts, df
        finally:
            self._subs.pop(params.key, None)

    async def _stream_ohlcv(
        self,
        exchange: Any,
        symbol: str,
        timeframe: str,
        interval: int,
        key: str,
    ) -> AsyncIterator[tuple[int, pl.DataFrame]]:
        interval_s = int(interval if interval > 0 else _tf_to_seconds(timeframe))
        # resolve method name once
        watch = getattr(exchange, "watch_ohlcv", None) or getattr(exchange, "watchOHLCV", None)
        if watch is None:
            raise RuntimeError("exchange does not support watch_ohlcv/watchOHLCV")
        while self._subs.get(key, False):
            rows = await watch(symbol, timeframe)
            # rows is a list of candles [[ms, o, h, l, c, v], ...]
            now_s = int(time.time())

            def _iter_records() -> Iterable[dict[str, Any]]:
                for r in (rows or []):
                    try:
                        ts = int(r[0]) // 1000
                    except Exception:
                        continue
                    if not self.config.emit_building_candle and ts + interval_s > now_s:
                        continue
                    record: dict[str, Any] = {
                        "ts": ts,
                        "open": float(r[1]),
                        "high": float(r[2]),
                        "low": float(r[3]),
                        "close": float(r[4]),
                        "volume": float(r[5]),
                    }
                    if self._uses_symbol_dedupe():
                        record["symbol"] = symbol
                    yield record

            normalized = self._normalize_records(key=key, symbol=symbol, records=_iter_records())
            if not normalized:
                # yield nothing; let outer loop iterate again
                await asyncio.sleep(0)
                continue

            yield normalized

    async def _stream_trades(
        self,
        exchange: Any,
        symbol: str,
        interval: int,
        key: str,
    ) -> AsyncIterator[tuple[int, pl.DataFrame]]:
        watch = getattr(exchange, "watch_trades", None) or getattr(exchange, "watchTrades", None)
        if watch is None:
            raise RuntimeError("exchange does not support watch_trades/watchTrades")
        while self._subs.get(key, False):
            trades = await watch(symbol)
            if not trades:
                await asyncio.sleep(0)
                continue
            normalized = self._normalize_records(
                key=key,
                symbol=symbol,
                records=self._trade_records(trades, symbol),
            )
            if not normalized:
                await asyncio.sleep(0)
                continue

            yield normalized

    def _build_subscription_params(self, *, node_id: str, interval: int) -> _SubscriptionParams:
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
        return _SubscriptionParams(
            node_id=node_id,
            symbol=symbol,
            timeframe=timeframe,
            mode=mode,
            interval=int(interval),
            key=key,
        )

    def _build_backoff_controller(self) -> _BackoffController:
        schedule = self._build_backoff_schedule()
        base_backoff = max(0.1, float(self.config.reconnect_backoff_s))
        max_backoff = max(base_backoff, float(self.config.max_backoff_s))
        return _BackoffController(
            schedule=schedule,
            base_backoff=base_backoff,
            max_backoff=max_backoff,
        )

    async def _run_subscribe_loop(
        self,
        *,
        params: _SubscriptionParams,
        backoff: _BackoffController,
    ) -> AsyncIterator[tuple[int, pl.DataFrame]]:
        key = params.key
        while self._subs.get(key, False):
            try:
                ex = await self._get_or_create_exchange()
                async for ts, df in self._stream_by_mode(
                    exchange=ex,
                    symbol=params.symbol,
                    timeframe=params.timeframe,
                    interval=params.interval,
                    mode=params.mode,
                    key=key,
                ):
                    yield ts, df
                # Normal termination (unsubscribe)
                break
            except asyncio.CancelledError:  # pragma: no cover - cooperative cancel
                raise
            except Exception as exc:
                if not self._subs.get(key, False):
                    break
                self._log_subscribe_error(params=params, error=exc)
                await asyncio.sleep(backoff.next_delay())

    async def _stream_by_mode(
        self,
        *,
        exchange: Any,
        symbol: str,
        timeframe: str | None,
        interval: int,
        mode: str,
        key: str,
    ) -> AsyncIterator[tuple[int, pl.DataFrame]]:
        if mode == "ohlcv":
            effective_timeframe = timeframe or self.config.timeframe or "1m"
            async for ts, df in self._stream_ohlcv(
                exchange, symbol, effective_timeframe, interval, key
            ):
                yield ts, df
        else:
            async for ts, df in self._stream_trades(exchange, symbol, interval, key):
                yield ts, df

    def _log_subscribe_error(self, *, params: _SubscriptionParams, error: Exception) -> None:
        log.warning(
            "ccxtpro.live_feed.error; will reconnect",
            extra={
                "node_id": params.node_id,
                "symbol": params.symbol,
                "timeframe": params.timeframe,
                "mode": params.mode,
                "error": str(error),
            },
        )

    def _trade_records(self, trades: Iterable[dict[str, Any]], symbol: str) -> Iterable[dict[str, Any]]:
        for t in trades:
            try:
                ts = int(t.get("timestamp")) // 1000
            except Exception:
                continue
            record: dict[str, Any] = {"ts": ts}
            if "price" in t:
                record["price"] = float(t["price"])  # type: ignore[arg-type]
            if "amount" in t:
                record["amount"] = float(t["amount"])  # type: ignore[arg-type]
            if "side" in t:
                record["side"] = t["side"]
            if self._uses_symbol_dedupe():
                record["symbol"] = symbol
            yield record

    def _normalize_records(
        self,
        *,
        key: str,
        symbol: str | None,
        records: Iterable[dict[str, Any]],
    ) -> tuple[int, pl.DataFrame] | None:
        last_token = self._last_emitted_token.get(key)
        ready_records: list[dict[str, Any]] = []
        for raw in records:
            record, last_token = self._normalize_single_record(
                raw,
                symbol=symbol,
                last_token=last_token,
            )
            if record is not None:
                ready_records.append(record)

        if not ready_records:
            return None

        df = pl.DataFrame(ready_records)
        if df.is_empty():
            return None
        df = df.unique(subset=self._dedupe_subset()).sort("ts")
        last_ts = int(df.get_column("ts")[-1])
        if self._uses_symbol_dedupe():
            symbol_value = None
            if "symbol" in df.columns:
                symbol_value = df.get_column("symbol")[-1]
            if symbol_value is None and symbol is not None:
                symbol_value = symbol
            last_token = (last_ts, str(symbol_value) if symbol_value is not None else "")
        else:
            last_token = last_ts
        self._last_emitted_token[key] = last_token
        return last_ts, df

    def _normalize_single_record(
        self,
        raw: dict[str, Any],
        *,
        symbol: str | None,
        last_token: int | tuple[int, str] | None,
    ) -> tuple[dict[str, Any] | None, int | tuple[int, str] | None]:
        if "ts" not in raw:
            return None, last_token
        try:
            ts = int(raw["ts"])
        except (TypeError, ValueError):
            return None, last_token
        record = dict(raw)
        record["ts"] = ts
        symbol_for_token: str | None
        if self._uses_symbol_dedupe():
            symbol_for_token = record.get("symbol")
            if symbol_for_token is None:
                symbol_for_token = symbol
                if symbol is not None:
                    record.setdefault("symbol", symbol)
        else:
            symbol_for_token = symbol
        token = self._dedupe_token(ts, symbol_for_token)
        if self.config.dedupe and not self._should_emit(last_token, token):
            return None, last_token
        if self.config.dedupe:
            last_token = token
        return record, last_token

    def _mode_for_node(self, node_id: str) -> str:
        if node_id.startswith("ohlcv:"):
            return "ohlcv"
        if node_id.startswith("trades:"):
            return "trades"
        # fallback to config
        return (self.config.mode or "ohlcv").lower()

    async def _get_or_create_exchange(self) -> CcxtWatchExchange:
        if self._exchange is not None:
            return self._exchange
        klass = self._resolve_ccxt_exchange_class()
        exchange: CcxtWatchExchange = klass({"enableRateLimit": True, "newUpdates": True})
        await self._configure_exchange(exchange)
        self._exchange = exchange
        return exchange

    def _resolve_ccxt_exchange_class(self) -> Any:
        ccxtpro = self._import_ccxtpro_module()
        eid = self.config.exchange_id.lower()
        if not hasattr(ccxtpro, eid):
            raise ValueError(f"Unknown ccxt.pro exchange id: {eid}")
        return getattr(ccxtpro, eid)

    def _import_ccxtpro_module(self) -> Any:
        # Lazy, guarded import of ccxt.pro
        ccxtpro: Optional[Any] = None
        try:  # pragma: no cover - optional dependency
            import ccxt.pro as ccxtpro  # type: ignore
        except Exception:
            try:  # pragma: no cover - alternative name
                import ccxtpro  # type: ignore
            except Exception as exc:  # noqa: F841
                raise RuntimeError(
                    "ccxt.pro is required for CcxtProLiveFeed; install ccxtpro or ccxt.pro"
                ) from exc
        return ccxtpro

    async def _configure_exchange(self, ex: CcxtWatchExchange) -> None:
        self._apply_sandbox_mode_if_needed(ex)
        await self._load_markets_if_available(ex)

    def _apply_sandbox_mode_if_needed(self, ex: Any) -> None:
        if not self.config.sandbox:
            return
        try:
            if hasattr(ex, "set_sandbox_mode"):
                ex.set_sandbox_mode(True)  # type: ignore[attr-defined]
                return
        except Exception:
            pass
        try:
            if hasattr(ex, "setSandboxMode"):
                getattr(ex, "setSandboxMode")(True)
        except Exception:
            pass

    async def _load_markets_if_available(self, ex: Any) -> None:
        try:
            if hasattr(ex, "load_markets"):
                await ex.load_markets()
        except Exception:
            pass

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
        try:
            await ex.close()
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
