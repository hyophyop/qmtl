from __future__ import annotations

"""Convenience provider wiring CCXT fetcher with QuestDB backend.

This module exposes a small helper class that composes
``QuestDBHistoryProvider`` with ``FetcherBackfillStrategy`` using the
``CcxtOHLCVFetcher`` implementation.
"""

from dataclasses import dataclass
from typing import Any, Mapping

from qmtl.runtime.sdk.auto_backfill import FetcherBackfillStrategy
from qmtl.runtime.sdk.ohlcv_nodeid import build as _build_ohlcv_node_id
from qmtl.runtime.io.historyprovider import QuestDBHistoryProvider
from .ccxt_fetcher import (
    CcxtBackfillConfig,
    CcxtOHLCVFetcher,
    RateLimiterConfig,
    CcxtTradesConfig,
    CcxtTradesFetcher,
)


@dataclass(slots=True)
class QuestDBConn:
    dsn: str | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None
    table: str | None = None

    def resolve_dsn(self) -> str:
        if self.dsn:
            return self.dsn
        host = self.host or "localhost"
        port = int(self.port or 8812)
        db = self.database or "qdb"
        # asyncpg-compatible DSN
        return f"postgresql://{host}:{port}/{db}"


class CcxtQuestDBProvider(QuestDBHistoryProvider):
    """QuestDB provider pre-configured with a CCXT OHLCV backfiller.

    Typical usage:
        provider = CcxtQuestDBProvider.from_config({
            "exchange": "binance",
            "symbols": ["BTC/USDT"],
            "timeframe": "1m",
            "questdb": {"dsn": "postgresql://localhost:8812/qdb", "table": "crypto_ohlcv"},
        })
    """

    def __init__(
        self,
        dsn: str,
        *,
        table: str | None = None,
        fetcher: CcxtOHLCVFetcher | None = None,
    ) -> None:
        auto = FetcherBackfillStrategy(fetcher) if fetcher is not None else None
        super().__init__(dsn, table=table, fetcher=fetcher, auto_backfill=auto)

    # ------------------------------------------------------------------
    @classmethod
    def from_config(
        cls,
        cfg: Mapping[str, Any],
        *,
        exchange: Any | None = None,
    ) -> "CcxtQuestDBProvider":
        """Create a provider for OHLCV (default) or trades mode.

        cfg keys:
            - mode: "ohlcv" (default) or "trades"
            - exchange/exchange_id, symbols, timeframe (for ohlcv)
            - questdb: { dsn | host/port/database, table | table_prefix }
            - backoff/rate_limiter/window_size/etc.; see fetcher configs
        """
        mode = str(cfg.get("mode", "ohlcv")).lower()
        exchange_id = str(cfg.get("exchange") or cfg.get("exchange_id") or "binance")
        symbols = list(cfg.get("symbols") or []) or None
        rl_cfg = cfg.get("rate_limiter") or {}
        min_interval_s_cfg = rl_cfg.get("min_interval_s")
        min_interval_ms_cfg = rl_cfg.get("min_interval_ms")
        min_interval_value: float | None = None
        if min_interval_s_cfg is not None:
            min_interval_value = float(min_interval_s_cfg)
        if min_interval_ms_cfg is not None:
            min_interval_from_ms = float(min_interval_ms_cfg) / 1000.0
            if min_interval_value is not None:
                if abs(min_interval_value - min_interval_from_ms) > 1e-9:
                    raise ValueError(
                        "rate_limiter.min_interval_s and rate_limiter.min_interval_ms "
                        "conflict; provide matching values or only one option"
                    )
            min_interval_value = min_interval_from_ms
        effective_min_interval_s = float(min_interval_value or 0.0)
        rate_limiter = RateLimiterConfig(
            max_concurrency=int(rl_cfg.get("max_concurrency", 1)),
            min_interval_s=effective_min_interval_s,
            scope=str(rl_cfg.get("scope", "process")),
            redis_dsn=rl_cfg.get("redis_dsn"),
            tokens_per_interval=(
                float(rl_cfg["tokens_per_interval"])
                if rl_cfg.get("tokens_per_interval") is not None
                else None
            ),
            interval_ms=(
                int(rl_cfg["interval_ms"])
                if rl_cfg.get("interval_ms") is not None
                else None
            ),
            burst_tokens=(
                int(rl_cfg["burst_tokens"])
                if rl_cfg.get("burst_tokens") is not None
                else None
            ),
            local_semaphore=(
                int(rl_cfg["local_semaphore"])
                if rl_cfg.get("local_semaphore") is not None
                else None
            ),
            key_suffix=rl_cfg.get("key_suffix"),
            key_template=rl_cfg.get("key_template"),
            penalty_backoff_ms=(
                int(rl_cfg["penalty_backoff_ms"])
                if rl_cfg.get("penalty_backoff_ms") is not None
                else None
            ),
        )

        fetcher: CcxtOHLCVFetcher | CcxtTradesFetcher
        if mode == "trades":
            backfill_t = CcxtTradesConfig(
                exchange_id=exchange_id,
                symbols=symbols,
                window_size=int(cfg.get("window_size", 1000)),
                max_retries=int(cfg.get("max_retries", 3)),
                retry_backoff_s=float(cfg.get("retry_backoff_s", 0.5)),
                rate_limiter=rate_limiter,
            )
            fetcher = CcxtTradesFetcher(backfill_t, exchange=exchange)
        else:
            timeframe = str(cfg.get("timeframe") or "1m")
            backfill_o = CcxtBackfillConfig(
                exchange_id=exchange_id,
                symbols=symbols,
                timeframe=timeframe,
                window_size=int(cfg.get("window_size", 1000)),
                max_retries=int(cfg.get("max_retries", 3)),
                retry_backoff_s=float(cfg.get("retry_backoff_s", 0.5)),
                rate_limiter=rate_limiter,
            )
            fetcher = CcxtOHLCVFetcher(backfill_o, exchange=exchange)

        q = cfg.get("questdb") or {}
        table = q.get("table")
        table_prefix = q.get("table_prefix")
        if not table and table_prefix:
            # Derive a simple table name from prefix and mode
            table = f"{table_prefix}_{mode}"
        conn = QuestDBConn(
            dsn=q.get("dsn"),
            host=q.get("host"),
            port=q.get("port"),
            database=q.get("database") or q.get("db"),
            table=table,
        )
        dsn = conn.resolve_dsn()
        return cls(dsn, table=conn.table, fetcher=fetcher)

    # ------------------------------------------------------------------
    @staticmethod
    def make_node_id(
        *, exchange_id: str, symbol: str, timeframe: str | None = None, mode: str = "ohlcv"
    ) -> str:
        mode = (mode or "ohlcv").lower()
        if mode == "trades":
            return f"trades:{exchange_id}:{symbol}"
        tf = timeframe or "1m"
        return _build_ohlcv_node_id(exchange_id, symbol, tf)

    # ------------------------------------------------------------------
    @classmethod
    def from_config_multi(
        cls, cfg: Mapping[str, Any], *, exchange: Any | None = None
    ) -> dict[str, "CcxtQuestDBProvider"]:
        """Create multiple providers for combinations of symbols/timeframes.

        For mode=ohlcv, returns one per (symbol, timeframe). For trades, one per symbol.
        Keys are constructed via make_node_id.
        """
        mode = str(cfg.get("mode", "ohlcv")).lower()
        exchange_id = str(cfg.get("exchange") or cfg.get("exchange_id") or "binance")
        symbols = list(cfg.get("symbols") or [])
        timeframes = list(cfg.get("timeframes") or ([] if cfg.get("timeframe") is None else [cfg.get("timeframe")]))
        if mode == "trades":
            if not symbols:
                return {}
            out: dict[str, CcxtQuestDBProvider] = {}
            for sym in symbols:
                node_id = cls.make_node_id(exchange_id=exchange_id, symbol=sym, mode="trades")
                provider = cls.from_config(cfg, exchange=exchange)
                out[node_id] = provider
            return out

        # OHLCV
        if not timeframes:
            timeframes = ["1m"]
        out2: dict[str, CcxtQuestDBProvider] = {}
        for sym in symbols or []:
            for tf in timeframes:
                local_cfg = dict(cfg)
                local_cfg["timeframe"] = tf
                node_id = cls.make_node_id(exchange_id=exchange_id, symbol=sym, timeframe=tf, mode="ohlcv")
                provider = cls.from_config(local_cfg, exchange=exchange)
                out2[node_id] = provider
        return out2


__all__ = ["CcxtQuestDBProvider", "CcxtBackfillConfig", "RateLimiterConfig"]
