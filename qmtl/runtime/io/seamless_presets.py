from __future__ import annotations

"""Preset registrations for Seamless builder integrations."""

import logging
import os
from typing import Any, Callable, Mapping, MutableMapping, Sequence

from qmtl.runtime.sdk.seamless import SeamlessPresetRegistry
from qmtl.runtime.sdk.seamless_data_provider import DataSourcePriority
from qmtl.runtime.io.historyprovider import QuestDBLoader
from qmtl.runtime.io.seamless_provider import (
    DataFetcherAutoBackfiller,
    LiveDataFeedImpl,
    HistoryProviderDataSource,
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

_logger = logging.getLogger(__name__)


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
            return HistoryProviderDataSource(provider, DataSourcePriority.STORAGE)

        def backfill_factory():
            return DataFetcherAutoBackfiller(make_fetcher())

        builder.with_storage(storage_factory)
        if cache_provider_factory is not None:
            def cache_factory():
                provider = cache_provider_factory()
                if provider is None:
                    raise RuntimeError("cache_provider factory returned None")
                return HistoryProviderDataSource(provider, DataSourcePriority.CACHE)

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
            return HistoryProviderDataSource(provider, DataSourcePriority.STORAGE)

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
            reg = FileSystemArtifactRegistrar.from_runtime_config()
            if reg is None:
                # fall back to IO registrar with default path
                from qmtl.runtime.io.artifact import ArtifactRegistrar as IORegistrar

                return IORegistrar(stabilization_bars=int(config.get("stabilization_bars", 2)))
            return reg

        builder.with_registrar(registrar_factory)
        return builder

    SeamlessPresetRegistry.register("seamless.registrar.filesystem", _apply)


_register_filesystem_registrar_preset()


def _register_ccxt_bundle_presets() -> None:
    """High-level convenience bundles that compose existing presets."""

    def _apply_ohlcv_live(builder, config: Mapping[str, Any]):
        # Apply OHLCV storage/backfill and then live feed
        core_opts = {
            "exchange_id": config.get("exchange_id") or config.get("exchange"),
            "symbols": config.get("symbols"),
            "timeframe": config.get("timeframe", "1m"),
            "questdb": _as_mapping(config.get("questdb"), "questdb"),
            "rate_limiter": _as_mapping(config.get("rate_limiter"), "rate_limiter"),
            "window_size": config.get("window_size"),
            "max_retries": config.get("max_retries"),
            "retry_backoff_s": config.get("retry_backoff_s"),
        }
        builder = SeamlessPresetRegistry.apply(
            "ccxt.questdb.ohlcv", builder=builder, config=core_opts
        )

        live_opts = {
            "exchange_id": core_opts["exchange_id"],
            "symbols": core_opts["symbols"],
            "timeframe": core_opts["timeframe"],
            "mode": "ohlcv",
            "sandbox": config.get("sandbox", False),
            "reconnect_backoff_ms": config.get("reconnect_backoff_ms", []),
            "dedupe_by": config.get("dedupe_by", "ts"),
            "emit_building_candle": config.get("emit_building_candle", False),
        }
        builder = SeamlessPresetRegistry.apply(
            "ccxt.live.pro", builder=builder, config=live_opts
        )
        return builder

    def _apply_trades_live(builder, config: Mapping[str, Any]):
        core_opts = {
            "exchange_id": config.get("exchange_id") or config.get("exchange"),
            "symbols": config.get("symbols"),
            "questdb": _as_mapping(config.get("questdb"), "questdb"),
            "rate_limiter": _as_mapping(config.get("rate_limiter"), "rate_limiter"),
            "window_size": config.get("window_size"),
            "max_retries": config.get("max_retries"),
            "retry_backoff_s": config.get("retry_backoff_s"),
        }
        builder = SeamlessPresetRegistry.apply(
            "ccxt.questdb.trades", builder=builder, config=core_opts
        )
        live_opts = {
            "exchange_id": core_opts["exchange_id"],
            "symbols": core_opts["symbols"],
            "mode": "trades",
            "sandbox": config.get("sandbox", False),
            "reconnect_backoff_ms": config.get("reconnect_backoff_ms", []),
            "dedupe_by": config.get("dedupe_by", "ts"),
        }
        builder = SeamlessPresetRegistry.apply(
            "ccxt.live.pro", builder=builder, config=live_opts
        )
        return builder

    SeamlessPresetRegistry.register("ccxt.bundle.ohlcv_live", _apply_ohlcv_live)
    SeamlessPresetRegistry.register("ccxt.bundle.trades_live", _apply_trades_live)


_register_ccxt_bundle_presets()


# ---------------------------------------------------------------------------
# Nautilus Trader Integration Presets
# ---------------------------------------------------------------------------


class NautilusPresetUnavailableError(ImportError):
    """Raised when nautilus.* preset is requested but nautilus_trader is not installed.
    
    This error follows QMTL's Default-safe principle: when the required dependency
    is missing, the system fails fast with a clear message rather than silently
    degrading to unexpected behavior.
    
    Alternative presets:
    - Use 'ccxt.questdb.ohlcv' for CCXT-based historical data
    - Use 'ccxt.bundle.ohlcv_live' for CCXT historical + live
    - Use 'demo.inmemory.ohlcv' for testing without external dependencies
    """
    
    def __init__(self, preset_name: str, original_error: Exception | None = None):
        self.preset_name = preset_name
        self.original_error = original_error
        super().__init__(
            f"Nautilus preset '{preset_name}' requires nautilus_trader which is not installed. "
            f"Install with: uv pip install qmtl[nautilus]\n"
            f"Alternative presets: 'ccxt.questdb.ohlcv', 'ccxt.bundle.ohlcv_live', 'demo.inmemory.ohlcv'"
        )


class NautilusCatalogNotFoundError(FileNotFoundError):
    """Raised when the Nautilus DataCatalog path does not exist.
    
    This follows Default-safe principle: fails fast when catalog is missing
    rather than returning empty data silently.
    """
    
    def __init__(self, catalog_path: str):
        self.catalog_path = catalog_path
        super().__init__(
            f"Nautilus DataCatalog not found at '{catalog_path}'. "
            f"Ensure the catalog exists and contains data, or use an alternative preset."
        )


def _register_nautilus_presets() -> None:
    """Register Nautilus Trader integration presets.
    
    Available presets:
    - nautilus.catalog: Historical data from Nautilus DataCatalog (storage only)
    - nautilus.full: Historical (Nautilus) + Live (CCXT Pro)
    
    Core Loop compliance:
    - These presets integrate with world.data.presets[] auto-wiring
    - Follows Default-safe principle: fails fast with clear messages
    - Single entry point via SeamlessPresetRegistry
    """
    
    def _apply_nautilus_catalog(builder, config: Mapping[str, Any]):
        """Nautilus DataCatalog as storage source.
        
        Config options:
            catalog_path: Path to Nautilus catalog (default: ~/.nautilus/catalog)
            priority: DataSourcePriority (default: STORAGE)
            
        Default-safe behavior:
            - Fails fast if nautilus_trader not installed
            - Logs warning if catalog path doesn't exist (allows lazy initialization)
        """
        try:
            from qmtl.runtime.io.nautilus_catalog_source import (
                NautilusCatalogDataSource,
                NAUTILUS_AVAILABLE,
            )
        except ImportError as e:
            raise NautilusPresetUnavailableError("nautilus.catalog", e) from e
        
        if not NAUTILUS_AVAILABLE:
            raise NautilusPresetUnavailableError("nautilus.catalog")
        
        try:
            from nautilus_trader.persistence.catalog import DataCatalog
        except ImportError as e:
            raise NautilusPresetUnavailableError("nautilus.catalog", e) from e
        
        catalog_path = config.get("catalog_path", "~/.nautilus/catalog")
        priority_raw = config.get("priority", "STORAGE")
        if isinstance(priority_raw, str):
            priority = DataSourcePriority[priority_raw.upper()]
        else:
            priority = priority_raw
        
        # Expand user path and check existence (warning, not error for lazy init)
        expanded_path = os.path.expanduser(catalog_path)
        if not os.path.exists(expanded_path):
            _logger.warning(
                "Nautilus catalog path '%s' does not exist yet. "
                "DataCatalog will be initialized on first use.",
                expanded_path,
            )
        
        catalog = DataCatalog(catalog_path)
        source = NautilusCatalogDataSource(catalog=catalog, priority=priority)
        
        return builder.with_storage(source)
    
    def _apply_nautilus_full(builder, config: Mapping[str, Any]):
        """Nautilus DataCatalog + CCXT Pro live feed.
        
        Config options:
            catalog_path: Path to Nautilus catalog (default: ~/.nautilus/catalog)
            exchange_id: Exchange for live data (e.g., "binance") - REQUIRED
            symbols: List of symbols (e.g., ["BTC/USDT"])
            timeframe: Timeframe for OHLCV (default: "1m")
            mode: "ohlcv" or "trades" (default: "ohlcv")
            sandbox: Use sandbox mode (default: False)
            
        Default-safe behavior:
            - Fails fast if nautilus_trader not installed
            - Fails fast if exchange_id not provided (required for live feed)
        """
        # Apply nautilus.catalog first (inherits Default-safe checks)
        builder = _apply_nautilus_catalog(builder, config)
        
        # Configure CCXT Pro live feed
        exchange_id = config.get("exchange_id") or config.get("exchange")
        if not exchange_id:
            raise KeyError(
                "nautilus.full preset requires 'exchange_id' for live data feed. "
                "Example: exchange_id='binance'"
            )
        
        symbols = _normalize_symbols(config.get("symbols"))
        timeframe = config.get("timeframe", "1m")
        mode = config.get("mode", "ohlcv")
        sandbox = config.get("sandbox", False)
        reconnect_backoff_ms = config.get("reconnect_backoff_ms")
        dedupe_by = config.get("dedupe_by", "ts")
        emit_building_candle = config.get("emit_building_candle", False)
        
        live_config = CcxtProConfig(
            exchange_id=exchange_id,
            symbols=symbols,
            timeframe=timeframe if mode == "ohlcv" else None,
            mode=mode,
            sandbox=sandbox,
            reconnect_backoff_ms=(
                list(reconnect_backoff_ms) if reconnect_backoff_ms else None
            ),
            dedupe_by=dedupe_by,  # type: ignore[arg-type]
            emit_building_candle=emit_building_candle,
        )
        live_feed = CcxtProLiveFeed(live_config)
        
        return builder.with_live(live_feed)
    
    SeamlessPresetRegistry.register("nautilus.catalog", _apply_nautilus_catalog)
    SeamlessPresetRegistry.register("nautilus.full", _apply_nautilus_full)


_register_nautilus_presets()


__all__ = [
    "_register_ccxt_questdb_preset",
    "NautilusPresetUnavailableError",
    "NautilusCatalogNotFoundError",
]
