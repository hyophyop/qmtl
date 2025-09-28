from __future__ import annotations

"""Preset registrations for Seamless builder integrations."""

from typing import Any, Callable, Mapping, MutableMapping, Sequence

from qmtl.runtime.sdk.seamless import SeamlessPresetRegistry
from qmtl.runtime.io.historyprovider import QuestDBLoader
from qmtl.runtime.io.seamless_provider import (
    CacheDataSource,
    DataFetcherAutoBackfiller,
    LiveDataFeedImpl,
    StorageDataSource,
)
from qmtl.runtime.io.ccxt_fetcher import (
    CcxtBackfillConfig,
    CcxtOHLCVFetcher,
    RateLimiterConfig,
    CcxtTradesConfig,
    CcxtTradesFetcher,
)
from qmtl.runtime.io.ccxt_live_feed import CcxtProConfig, CcxtProLiveFeed
from qmtl.runtime.sdk.artifacts import FileSystemArtifactRegistrar


def _ensure_str(value: Any, *, field: str) -> str:
    if value is None:
        raise KeyError(f"ccxt.questdb.ohlcv preset requires '{field}'")
    return str(value)


def _ensure_int(value: Any, default: int) -> int:
    if value is None:
        return default
    return int(value)


def _ensure_float(value: Any, default: float) -> float:
    if value is None:
        return default
    return float(value)


def _normalize_symbols(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [str(item) for item in value]
    raise TypeError("symbols must be string or sequence of strings")


def _pull_questdb_config(config: Mapping[str, Any]) -> tuple[str, str | None]:
    questdb_cfg = config.get("questdb")
    if isinstance(questdb_cfg, Mapping):
        dsn = questdb_cfg.get("dsn")
        table = questdb_cfg.get("table")
    else:
        dsn = config.get("dsn")
        table = config.get("table")
    return _ensure_str(dsn, field="questdb.dsn"), str(table) if table else None


def _pull_rate_limiter(config: Mapping[str, Any]) -> RateLimiterConfig:
    raw = config.get("rate_limiter")
    if not isinstance(raw, MutableMapping):
        raw = {}
    return RateLimiterConfig(
        max_concurrency=_ensure_int(raw.get("max_concurrency"), 1),
        min_interval_s=_ensure_float(raw.get("min_interval_s"), 0.0),
        scope=str(raw.get("scope", "process")),
        redis_dsn=raw.get("redis_dsn"),
        tokens_per_interval=(
            float(raw["tokens_per_interval"])
            if raw.get("tokens_per_interval") is not None
            else None
        ),
        interval_ms=(
            int(raw["interval_ms"])
            if raw.get("interval_ms") is not None
            else None
        ),
        burst_tokens=(
            int(raw["burst_tokens"])
            if raw.get("burst_tokens") is not None
            else None
        ),
        local_semaphore=(
            int(raw["local_semaphore"])
            if raw.get("local_semaphore") is not None
            else None
        ),
        key_suffix=raw.get("key_suffix"),
        penalty_backoff_ms=(
            int(raw["penalty_backoff_ms"])
            if raw.get("penalty_backoff_ms") is not None
            else None
        ),
    )


def _resolve_callable(value: Any) -> Callable[[], Any] | None:
    if value is None:
        return None
    if callable(value):
        return value
    return lambda value=value: value


def _register_ccxt_questdb_preset() -> None:
    def _apply(builder, config: Mapping[str, Any]):
        dsn, table = _pull_questdb_config(config)
        exchange_id = _ensure_str(
            config.get("exchange_id") or config.get("exchange"),
            field="exchange_id",
        )
        symbols = _normalize_symbols(config.get("symbols"))
        timeframe = str(config.get("timeframe", "1m"))
        window_size = _ensure_int(config.get("window_size"), 1000)
        max_retries = _ensure_int(config.get("max_retries"), 3)
        retry_backoff_s = _ensure_float(config.get("retry_backoff_s"), 0.5)
        rate_limiter = _pull_rate_limiter(config)

        def make_fetcher() -> CcxtOHLCVFetcher:
            backfill_cfg = CcxtBackfillConfig(
                exchange_id=exchange_id,
                symbols=symbols,
                timeframe=timeframe,
                window_size=window_size,
                max_retries=max_retries,
                retry_backoff_s=retry_backoff_s,
                rate_limiter=rate_limiter,
            )
            return CcxtOHLCVFetcher(backfill_cfg)

        cache_provider_factory = _resolve_callable(config.get("cache_provider"))
        registrar_factory = _resolve_callable(config.get("registrar"))
        live_fetcher_factory = _resolve_callable(config.get("live_fetcher"))

        def storage_factory():
            fetcher = make_fetcher()
            provider = QuestDBLoader(dsn, table=table, fetcher=fetcher)
            return StorageDataSource(provider)

        def backfill_factory():
            return DataFetcherAutoBackfiller(make_fetcher())

        builder.with_storage(storage_factory)
        if cache_provider_factory is not None:
            def cache_factory():
                provider = cache_provider_factory()
                if provider is None:
                    raise RuntimeError("cache_provider factory returned None")
                return CacheDataSource(provider)

            builder.with_cache(cache_factory)
        builder.with_backfill(backfill_factory)
        if live_fetcher_factory is not None:
            def live_factory():
                fetcher = live_fetcher_factory()
                if fetcher is None:
                    raise RuntimeError("live_fetcher factory returned None")
                return LiveDataFeedImpl(fetcher)

            builder.with_live(live_factory)
        if registrar_factory is not None:
            builder.with_registrar(registrar_factory)
        return builder

    SeamlessPresetRegistry.register("ccxt.questdb.ohlcv", _apply)


_register_ccxt_questdb_preset()


def _register_ccxt_trades_preset() -> None:
    def _apply(builder, config: Mapping[str, Any]):
        dsn, table = _pull_questdb_config(config)
        exchange_id = _ensure_str(
            config.get("exchange_id") or config.get("exchange"),
            field="exchange_id",
        )
        symbols = _normalize_symbols(config.get("symbols"))
        window_size = _ensure_int(config.get("window_size"), 1000)
        max_retries = _ensure_int(config.get("max_retries"), 3)
        retry_backoff_s = _ensure_float(config.get("retry_backoff_s"), 0.5)
        rate_limiter = _pull_rate_limiter(config)

        def make_fetcher() -> CcxtTradesFetcher:
            backfill_cfg = CcxtTradesConfig(
                exchange_id=exchange_id,
                symbols=symbols,
                window_size=window_size,
                max_retries=max_retries,
                retry_backoff_s=retry_backoff_s,
                rate_limiter=rate_limiter,
            )
            return CcxtTradesFetcher(backfill_cfg)

        registrar_factory = _resolve_callable(config.get("registrar"))

        def storage_factory():
            fetcher = make_fetcher()
            provider = QuestDBLoader(dsn, table=table, fetcher=fetcher)
            return StorageDataSource(provider)

        builder.with_storage(storage_factory)
        builder.with_backfill(lambda: DataFetcherAutoBackfiller(make_fetcher()))
        if registrar_factory is not None:
            builder.with_registrar(registrar_factory)
        return builder

    SeamlessPresetRegistry.register("ccxt.questdb.trades", _apply)


_register_ccxt_trades_preset()


def _register_ccxt_live_pro_preset() -> None:
    def _apply(builder, config: Mapping[str, Any]):
        exchange_id = _ensure_str(
            config.get("exchange_id") or config.get("exchange"),
            field="exchange_id",
        )
        symbols = _normalize_symbols(config.get("symbols"))
        timeframe = str(config.get("timeframe") or "1m")
        mode = str(config.get("mode") or "ohlcv").lower()
        sandbox = bool(config.get("sandbox", False))
        backoff_ms = list(config.get("reconnect_backoff_ms", []) or [])
        dedupe_by = str(config.get("dedupe_by") or "ts").lower()
        emit_building = bool(config.get("emit_building_candle", False))

        def live_factory():
            cfg = CcxtProConfig(
                exchange_id=exchange_id,
                symbols=symbols,
                timeframe=timeframe,
                mode=mode,
                sandbox=sandbox,
                reconnect_backoff_ms=backoff_ms,
                dedupe_by=dedupe_by,  # type: ignore[arg-type]
                emit_building_candle=emit_building,
            )
            return CcxtProLiveFeed(cfg)

        builder.with_live(live_factory)
        return builder

    SeamlessPresetRegistry.register("ccxt.live.pro", _apply)


_register_ccxt_live_pro_preset()


def _register_filesystem_registrar_preset() -> None:
    def _apply(builder, config: Mapping[str, Any]):
        def registrar_factory():
            reg = FileSystemArtifactRegistrar.from_env()
            if reg is None:
                # fall back to IO registrar with default path
                from qmtl.runtime.io.artifact import ArtifactRegistrar as IORegistrar

                return IORegistrar(stabilization_bars=int(config.get("stabilization_bars", 2)))
            return reg

        builder.with_registrar(registrar_factory)
        return builder

    SeamlessPresetRegistry.register("seamless.registrar.filesystem", _apply)


_register_filesystem_registrar_preset()


__all__ = ["_register_ccxt_questdb_preset"]
