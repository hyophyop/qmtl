from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Callable, Optional
from pathlib import Path
import pandas as pd
import numpy as np
import asyncio
import logging

from qmtl.runtime.sdk.data_io import HistoryProvider, DataFetcher
from qmtl.runtime.sdk.ohlcv_nodeid import validate as _validate_ohlcv_node_id
from qmtl.runtime.sdk.seamless_data_provider import (
    SeamlessDataProvider,
    DataSource,
    DataSourcePriority,
    DataAvailabilityStrategy,
    LiveDataFeed,
)
from qmtl.runtime.sdk.seamless.builder import SeamlessAssembly, SeamlessBuilder
from qmtl.runtime.sdk.conformance import ConformancePipeline
from qmtl.runtime.io.artifact import ArtifactRegistrar as IOArtifactRegistrar
from qmtl.runtime.sdk.sla import SLAPolicy
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from qmtl.runtime.sdk.artifacts import ArtifactRegistrar, FileSystemArtifactRegistrar

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FingerprintPolicy:
    """Fingerprint publication policy for Seamless providers."""

    publish: bool | None = None
    early: bool | None = None

    def to_kwargs(self) -> dict[str, bool | None]:
        """Return keyword arguments understood by :class:`SeamlessDataProvider`."""

        payload: dict[str, bool | None] = {}
        if self.publish is not None:
            payload["publish_fingerprint"] = self.publish
        if self.early is not None:
            payload["early_fingerprint"] = self.early
        return payload


@dataclass(slots=True)
class EnhancedQuestDBProviderSettings:
    """Encapsulate optional knobs for :class:`EnhancedQuestDBProvider`.

    The settings object provides a single place to aggregate strategy, SLA,
    conformance and fingerprint configuration while keeping backwards
    compatibility with legacy keyword arguments. Call sites can migrate in two
    phases:

    1. Instantiate :class:`EnhancedQuestDBProviderSettings` with the
       configuration currently supplied through keyword arguments.
    2. Pass the instance via the ``settings`` parameter. Once all call sites
       adopt the object we can deprecate the legacy keyword arguments.
    """

    table: str | None = None
    fetcher: DataFetcher | None = None
    live_fetcher: DataFetcher | None = None
    live_feed: LiveDataFeed | None = None
    cache_provider: HistoryProvider | None = None
    strategy: DataAvailabilityStrategy = DataAvailabilityStrategy.SEAMLESS
    conformance: ConformancePipeline | None = None
    partial_ok: bool = False
    registrar: ArtifactRegistrar | None = None
    node_id_format: str | None = None
    sla: SLAPolicy | None = None
    fingerprint: FingerprintPolicy = field(default_factory=FingerprintPolicy)


@dataclass(slots=True)
class _EnhancedProviderComponents:
    storage_provider: "QuestDBLoader"
    assembly: SeamlessAssembly
    node_id_format: str | None
    node_id_validator: Callable[[str], None] | None


class HistoryProviderDataSource:
    """HistoryProvider-backed :class:`DataSource` with configurable priority."""

    def __init__(self, provider: HistoryProvider, priority: DataSourcePriority):
        self.provider = provider
        self.priority = priority

        # Preserve legacy attribute names for downstream compatibility.
        if priority is DataSourcePriority.CACHE:
            self.cache_provider = provider
        elif priority is DataSourcePriority.STORAGE:
            self.storage_provider = provider

    async def is_available(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> bool:
        try:
            coverage = await self.provider.coverage(node_id=node_id, interval=interval)
            for range_start, range_end in coverage:
                if range_start <= start and end <= range_end:
                    return True
            return False
        except Exception:
            return False

    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        return await self.provider.fetch(start, end, node_id=node_id, interval=interval)

    async def coverage(
        self, *, node_id: str, interval: int
    ) -> list[tuple[int, int]]:
        return await self.provider.coverage(node_id=node_id, interval=interval)


class CacheDataSource(HistoryProviderDataSource):
    """Compatibility wrapper that configures cache priority for a provider."""

    def __init__(self, provider: HistoryProvider):
        super().__init__(provider, DataSourcePriority.CACHE)


class StorageDataSource(HistoryProviderDataSource):
    """Compatibility wrapper that configures storage priority for a provider."""

    def __init__(self, provider: HistoryProvider):
        super().__init__(provider, DataSourcePriority.STORAGE)


class DataFetcherAutoBackfiller:
    """AutoBackfiller implementation using DataFetcher."""
    
    def __init__(self, fetcher: DataFetcher, max_chunk_size: int = 1000):
        self.fetcher = fetcher
        self.max_chunk_size = max_chunk_size
    
    async def can_backfill(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> bool:
        """Check if we can backfill this range."""
        try:
            # Try fetching a small sample to see if the fetcher works
            sample_end = min(start + interval, end)
            sample = await self.fetcher.fetch(
                start, sample_end, node_id=node_id, interval=interval
            )
            return not sample.empty
        except Exception as e:
            logger.warning(f"Backfill check failed for {node_id}: {e}")
            return False
    
    def _build_batch_id(
        self, *, batch_id: Optional[str], node_id: str, interval: int, start: int, end: int
    ) -> str:
        return batch_id or f"{node_id}:{interval}:{start}:{end}"

    def _build_log_extra(
        self,
        *,
        batch_id: str,
        attempt: int,
        node_id: str,
        interval: int,
        start: int,
        end: int,
        source: Optional[str] = None,
        error: Optional[str] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "batch_id": batch_id,
            "attempt": attempt,
            "node_id": node_id,
            "interval": interval,
            "start": start,
            "end": end,
        }
        if source:
            payload["source"] = source
        if error is not None:
            payload["error"] = error
        return payload

    @staticmethod
    def _should_use_storage(target_storage: Optional[DataSource]) -> bool:
        return (
            target_storage is not None
            and getattr(target_storage, "priority", None) is DataSourcePriority.STORAGE
        )

    def _resolve_storage_provider(self, target_storage: Optional[DataSource]):
        if not self._should_use_storage(target_storage):
            return None
        storage_provider = getattr(target_storage, "provider", None) if target_storage else None
        if storage_provider is None and target_storage is not None:
            storage_provider = getattr(target_storage, "storage_provider", None)
        if storage_provider and hasattr(storage_provider, "fill_missing") and hasattr(
            storage_provider, "fetch"
        ):
            return storage_provider
        return None

    def _log_attempt(
        self,
        *,
        batch_id: str,
        attempt: int,
        node_id: str,
        interval: int,
        start: int,
        end: int,
        source: str,
    ) -> None:
        logger.info(
            "seamless.backfill.attempt",
            extra=self._build_log_extra(
                batch_id=batch_id,
                attempt=attempt,
                node_id=node_id,
                interval=interval,
                start=start,
                end=end,
                source=source,
            ),
        )

    def _log_success(
        self,
        *,
        batch_id: str,
        attempt: int,
        node_id: str,
        interval: int,
        start: int,
        end: int,
        source: str,
    ) -> None:
        logger.info(
            "seamless.backfill.succeeded",
            extra=self._build_log_extra(
                batch_id=batch_id,
                attempt=attempt,
                node_id=node_id,
                interval=interval,
                start=start,
                end=end,
                source=source,
            ),
        )

    def _log_storage_fallback(
        self,
        *,
        batch_id: str,
        attempt: int,
        node_id: str,
        interval: int,
        start: int,
        end: int,
        error: str,
    ) -> None:
        logger.warning(
            "seamless.backfill.storage_fallback",
            extra=self._build_log_extra(
                batch_id=batch_id,
                attempt=attempt,
                node_id=node_id,
                interval=interval,
                start=start,
                end=end,
                source="storage",
                error=error,
            ),
            exc_info=True,
        )

    def _log_failure(
        self,
        *,
        batch_id: str,
        attempt: int,
        node_id: str,
        interval: int,
        start: int,
        end: int,
        error: str,
    ) -> None:
        logger.error(
            "seamless.backfill.failed",
            extra=self._build_log_extra(
                batch_id=batch_id,
                attempt=attempt,
                node_id=node_id,
                interval=interval,
                start=start,
                end=end,
                source="fetcher",
                error=error,
            ),
            exc_info=True,
        )

    async def _try_storage_backfill(
        self,
        storage_provider: Any,
        *,
        start: int,
        end: int,
        node_id: str,
        interval: int,
        batch_id: str,
        attempt: int,
    ) -> pd.DataFrame | None:
        try:
            await storage_provider.fill_missing(start, end, node_id=node_id, interval=interval)
            frame = await storage_provider.fetch(start, end, node_id=node_id, interval=interval)
            self._log_success(
                batch_id=batch_id,
                attempt=attempt,
                node_id=node_id,
                interval=interval,
                start=start,
                end=end,
                source="storage",
            )
            return frame
        except Exception as exc:
            self._log_storage_fallback(
                batch_id=batch_id,
                attempt=attempt,
                node_id=node_id,
                interval=interval,
                start=start,
                end=end,
                error=str(exc),
            )
            return None

    async def _fetch_from_source(
        self,
        *,
        start: int,
        end: int,
        node_id: str,
        interval: int,
        batch_id: str,
        attempt: int,
    ) -> pd.DataFrame:
        try:
            frame = await self.fetcher.fetch(start, end, node_id=node_id, interval=interval)
        except Exception as exc:
            self._log_failure(
                batch_id=batch_id,
                attempt=attempt,
                node_id=node_id,
                interval=interval,
                start=start,
                end=end,
                error=str(exc),
            )
            raise

        self._log_success(
            batch_id=batch_id,
            attempt=attempt,
            node_id=node_id,
            interval=interval,
            start=start,
            end=end,
            source="fetcher",
        )
        return frame

    async def backfill(
        self,
        start: int,
        end: int,
        *,
        node_id: str,
        interval: int,
        target_storage: Optional[DataSource] = None,
        attempt: int = 1,
        batch_id: Optional[str] = None,
    ) -> pd.DataFrame:
        """Synchronously backfill data; materialize via storage when possible."""
        batch_identifier = self._build_batch_id(
            batch_id=batch_id, node_id=node_id, interval=interval, start=start, end=end
        )
        planned_source = "storage" if self._should_use_storage(target_storage) else "fetcher"
        self._log_attempt(
            batch_id=batch_identifier,
            attempt=attempt,
            node_id=node_id,
            interval=interval,
            start=start,
            end=end,
            source=planned_source,
        )

        storage_provider = self._resolve_storage_provider(target_storage)
        if storage_provider:
            stored_frame = await self._try_storage_backfill(
                storage_provider,
                start=start,
                end=end,
                node_id=node_id,
                interval=interval,
                batch_id=batch_identifier,
                attempt=attempt,
            )
            if stored_frame is not None:
                return stored_frame

        return await self._fetch_from_source(
            start=start,
            end=end,
            node_id=node_id,
            interval=interval,
            batch_id=batch_identifier,
            attempt=attempt,
        )
    
    async def backfill_async(
        self, start: int, end: int, *, node_id: str, interval: int,
        target_storage: Optional[DataSource] = None,
        progress_callback: Optional[callable] = None
    ):
        """Asynchronously backfill data in chunks."""
        current = start
        total_size = end - start
        
        while current < end:
            chunk_end = min(current + self.max_chunk_size * interval, end)
            
            try:
                chunk_data = await self.backfill(
                    current, chunk_end,
                    node_id=node_id, interval=interval,
                    target_storage=target_storage
                )
                
                if progress_callback:
                    progress = (current - start) / total_size
                    progress_callback(progress)
                
                yield chunk_data
                
            except Exception as e:
                logger.error(f"Failed to backfill chunk [{current}, {chunk_end}]: {e}")
            
            current = chunk_end
            
            # Allow other tasks to run
            await asyncio.sleep(0)


class LiveDataFeedImpl:
    """Basic live data feed implementation."""
    
    def __init__(self, live_fetcher: Optional[DataFetcher] = None):
        self.live_fetcher = live_fetcher
        self._subscriptions: dict[str, bool] = {}
    
    async def is_live_available(
        self, *, node_id: str, interval: int
    ) -> bool:
        return self.live_fetcher is not None
    
    async def subscribe(
        self, *, node_id: str, interval: int
    ):
        """Subscribe to live data stream (polling prototype)."""
        if not self.live_fetcher:
            return

        key = f"{node_id}_{interval}"
        self._subscriptions[key] = True

        try:
            # Poll on aligned bar boundaries
            while self._subscriptions.get(key, False):
                try:
                    now = int(pd.Timestamp.now().timestamp())
                    current_bucket = now - (now % interval)

                    data = await self.live_fetcher.fetch(
                        current_bucket,
                        current_bucket + interval,
                        node_id=node_id,
                        interval=interval,
                    )

                    if not data.empty:
                        yield (current_bucket, data)

                    # Sleep until next bucket boundary
                    next_bucket = current_bucket + interval
                    now2 = int(pd.Timestamp.now().timestamp())
                    sleep_s = max(0, next_bucket - now2)
                    await asyncio.sleep(sleep_s or 0.001)

                except Exception as e:
                    logger.warning(f"Live data fetch failed for {node_id}: {e}")
                    await asyncio.sleep(1)
        finally:
            self._subscriptions.pop(key, None)
    
    def unsubscribe(self, *, node_id: str, interval: int):
        """Unsubscribe from live data stream."""
        key = f"{node_id}_{interval}"
        self._subscriptions[key] = False


class _FrameMappingDataSource(DataSource):
    """In-memory :class:`DataSource` backed by per-stream DataFrames.

    Frames are indexed by ``(node_id, interval)`` and must contain a ``ts``
    column with epoch-second timestamps. This is intended for lightweight
    offline integrations and examples.
    """

    def __init__(self) -> None:
        self.priority = DataSourcePriority.STORAGE
        self._frames: dict[tuple[str, int], pd.DataFrame] = {}

    def register(self, *, node_id: str, interval: int, frame: pd.DataFrame) -> None:
        if "ts" not in frame.columns:
            raise KeyError("frame missing 'ts' column")
        normalized = frame.copy()
        ts = normalized["ts"]
        normalized_ts: pd.Series
        if pd.api.types.is_integer_dtype(ts):
            normalized_ts = ts.astype("int64")
        else:
            numeric = pd.to_numeric(ts, errors="coerce")
            if numeric.notna().all():
                # ``ts`` already encodes epoch seconds but may be stored as
                # floats/objects (e.g., CSV with missing values). Ensure the
                # representation is integral rather than interpreting it as
                # nanosecond timestamps.
                remainder = np.modf(numeric.to_numpy(dtype="float64"))[0]
                if not np.allclose(remainder, 0):
                    raise TypeError(
                        "ts column must be integer seconds or datetime-like"
                    )
                normalized_ts = numeric.astype("int64")
            else:
                # Best-effort coercion from datetime-like values to epoch seconds.
                try:
                    dt = pd.to_datetime(ts, utc=True)
                    normalized_ts = (dt.view("int64") // 1_000_000_000).astype("int64")
                except Exception as exc:  # pragma: no cover - defensive guard
                    raise TypeError(
                        "ts column must be integer seconds or datetime-like"
                    ) from exc

        normalized["ts"] = normalized_ts

        normalized = normalized.sort_values("ts").reset_index(drop=True)
        self._frames[(str(node_id), int(interval))] = normalized

    async def is_available(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> bool:
        frame = self._frames.get((str(node_id), int(interval)))
        if frame is None or frame.empty:
            return False
        ts_min = int(frame["ts"].iloc[0])
        ts_max = int(frame["ts"].iloc[-1])
        # Treat data as available when the requested window intersects the
        # stored range. Fail-fast semantics are enforced by the caller.
        return not (end <= ts_min or start > ts_max)

    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        frame = self._frames.get((str(node_id), int(interval)))
        if frame is None or frame.empty:
            return pd.DataFrame(columns=["ts"])
        mask = (frame["ts"] >= int(start)) & (frame["ts"] < int(end))
        result = frame.loc[mask]
        if result.empty:
            return pd.DataFrame(columns=frame.columns)
        return result.reset_index(drop=True)

    async def coverage(
        self, *, node_id: str, interval: int
    ) -> list[tuple[int, int]]:
        frame = self._frames.get((str(node_id), int(interval)))
        if frame is None or frame.empty:
            return []
        ts_min = int(frame["ts"].iloc[0])
        ts_max = int(frame["ts"].iloc[-1])
        return [(ts_min, ts_max)]


class EnhancedQuestDBProvider(SeamlessDataProvider):
    """
    Enhanced QuestDB provider with seamless data access capabilities.
    
    This extends the existing QuestDBLoader with auto-backfill and live data support.
    """
    
    def __init__(
        self,
        dsn: str,
        *,
        settings: EnhancedQuestDBProviderSettings | None = None,
        table: str | None = None,
        fetcher: DataFetcher | None = None,
        live_fetcher: DataFetcher | None = None,
        live_feed: LiveDataFeed | None = None,
        cache_provider: HistoryProvider | None = None,
        strategy: DataAvailabilityStrategy | None = None,
        conformance: ConformancePipeline | None = None,
        partial_ok: bool | None = None,
        registrar: ArtifactRegistrar | None = None,
        node_id_format: str | None = None,
        **kwargs
    ):
        config = self._resolve_config(
            settings,
            table=table,
            fetcher=fetcher,
            live_fetcher=live_fetcher,
            live_feed=live_feed,
            cache_provider=cache_provider,
            strategy=strategy,
            conformance=conformance,
            partial_ok=partial_ok,
            registrar=registrar,
            node_id_format=node_id_format,
        )

        self._apply_config_kwargs(config, kwargs)

        strategy_value = config.strategy or DataAvailabilityStrategy.SEAMLESS
        components = self._build_components(dsn, config)

        self.storage_provider = components.storage_provider
        self._node_id_format = components.node_id_format
        self._node_id_validator = components.node_id_validator

        assembly = components.assembly
        super().__init__(
            strategy=strategy_value,
            cache_source=assembly.cache_source,
            storage_source=assembly.storage_source,
            backfiller=assembly.backfiller,
            live_feed=assembly.live_feed,
            conformance=config.conformance or ConformancePipeline(),
            partial_ok=bool(config.partial_ok),
            registrar=assembly.registrar,
            **kwargs
        )

    def bind_stream(self, stream) -> None:
        """Bind to a stream like the original HistoryProvider."""
        self.storage_provider.bind_stream(stream)

        # Also bind cache if available
        if self.cache_source:
            cache_provider = getattr(self.cache_source, "provider", None)
            if cache_provider is None:
                cache_provider = getattr(self.cache_source, "cache_provider", None)
            if cache_provider and hasattr(cache_provider, "bind_stream"):
                cache_provider.bind_stream(stream)

    def _validate_node_id(self, node_id: str) -> None:
        super()._validate_node_id(node_id)
        validator = self._node_id_validator
        if not validator:
            return
        try:
            validator(node_id)
        except (TypeError, ValueError) as exc:
            fmt = self._node_id_format or "unknown"
            raise ValueError(
                f"Node ID '{node_id}' does not match configured format '{fmt}': {exc}"
            ) from exc
    
    async def fill_missing(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> None:
        """Fill missing data using auto-backfill."""
        if not await self.ensure_data_available(start, end, node_id=node_id, interval=interval):
            raise RuntimeError(f"Could not ensure data availability for range [{start}, {end}]")

    @staticmethod
    def _build_components(dsn: str, config: EnhancedQuestDBProviderSettings) -> _EnhancedProviderComponents:
        from qmtl.runtime.io.historyprovider import QuestDBLoader

        storage_provider = QuestDBLoader(dsn, table=config.table, fetcher=config.fetcher)
        storage_source = HistoryProviderDataSource(storage_provider, DataSourcePriority.STORAGE)
        cache_source = EnhancedQuestDBProvider._build_cache_source(config.cache_provider)
        backfiller = EnhancedQuestDBProvider._build_backfiller(config.fetcher)
        live_feed = EnhancedQuestDBProvider._build_live_feed(config.live_feed, config.live_fetcher)
        registrar = EnhancedQuestDBProvider._resolve_registrar(config.registrar)
        node_id_format, node_id_validator = EnhancedQuestDBProvider._build_node_id_validator(
            config.node_id_format
        )

        assembly = EnhancedQuestDBProvider._build_seamless_assembly(
            storage_source=storage_source,
            cache_source=cache_source,
            backfiller=backfiller,
            live_feed=live_feed,
            registrar=registrar,
        )

        return _EnhancedProviderComponents(
            storage_provider=storage_provider,
            assembly=assembly,
            node_id_format=node_id_format,
            node_id_validator=node_id_validator,
        )

    @staticmethod
    def _resolve_config(
        settings: EnhancedQuestDBProviderSettings | None,
        **overrides: Any,
    ) -> EnhancedQuestDBProviderSettings:
        base = settings or EnhancedQuestDBProviderSettings()
        replacements = {k: v for k, v in overrides.items() if v is not None}
        return replace(base, **replacements) if replacements else base

    @staticmethod
    def _apply_config_kwargs(
        config: EnhancedQuestDBProviderSettings, kwargs: dict[str, Any]
    ) -> None:
        if config.sla is not None and "sla" not in kwargs:
            kwargs["sla"] = config.sla

        for key, value in config.fingerprint.to_kwargs().items():
            kwargs.setdefault(key, value)

    @staticmethod
    def _build_cache_source(
        cache_provider: HistoryProvider | None,
    ) -> HistoryProviderDataSource | None:
        if not cache_provider:
            return None
        return HistoryProviderDataSource(
            cache_provider, DataSourcePriority.CACHE
        )

    @staticmethod
    def _build_backfiller(
        fetcher: DataFetcher | None,
    ) -> DataFetcherAutoBackfiller | None:
        if not fetcher:
            return None
        return DataFetcherAutoBackfiller(fetcher)

    @staticmethod
    def _build_live_feed(
        live_feed: LiveDataFeed | None, live_fetcher: DataFetcher | None
    ) -> LiveDataFeed | None:
        if live_feed:
            return live_feed
        if live_fetcher:
            return LiveDataFeedImpl(live_fetcher)
        return None

    @staticmethod
    def _resolve_registrar(
        registrar: ArtifactRegistrar | None,
    ) -> ArtifactRegistrar:
        if registrar is not None:
            return registrar
        from qmtl.runtime.sdk.artifacts import FileSystemArtifactRegistrar

        runtime_registrar = FileSystemArtifactRegistrar.from_runtime_config()
        if runtime_registrar is not None:
            return runtime_registrar
        return IOArtifactRegistrar(stabilization_bars=2)

    @staticmethod
    def _build_node_id_validator(
        node_id_format: str | None,
    ) -> tuple[str | None, Callable[[str], None] | None]:
        fmt = node_id_format.strip() if node_id_format else None
        if not fmt:
            return None, None
        if fmt == "ohlcv:{exchange}:{symbol}:{timeframe}":
            return fmt, _validate_ohlcv_node_id
        logger.warning(
            "enhanced_provider.node_id_validation.unsupported_format",
            extra={"format": fmt},
        )
        return fmt, None

    @staticmethod
    def _build_seamless_assembly(
        *,
        storage_source: HistoryProviderDataSource,
        cache_source: HistoryProviderDataSource | None,
        backfiller: DataFetcherAutoBackfiller | None,
        live_feed: LiveDataFeed | None,
        registrar: ArtifactRegistrar,
    ):
        builder = SeamlessBuilder()
        builder.with_storage(storage_source)
        builder.with_cache(cache_source)
        builder.with_backfill(backfiller)
        builder.with_live(live_feed)
        builder.with_registrar(registrar)
        return builder.build()


class InMemorySeamlessProvider(SeamlessDataProvider):
    """Seamless provider backed by in-memory DataFrames.

    This helper is intended for local development and examples where history
    lives in CSV/Parquet files or pre-loaded DataFrames rather than an
    external storage backend. It wires an internal :class:`DataSource`
    so that the existing Seamless orchestration, coverage, and history
    warm-up paths can be reused unchanged.
    """

    def __init__(
        self,
        *,
        strategy: DataAvailabilityStrategy = DataAvailabilityStrategy.FAIL_FAST,
    ) -> None:
        storage = _FrameMappingDataSource()
        super().__init__(
            strategy=strategy,
            cache_source=None,
            storage_source=storage,
            backfiller=None,
            live_feed=None,
            conformance=None,
            partial_ok=True,
            registrar=None,
            stabilization_bars=0,
        )
        self._storage = storage

    def register_frame(
        self,
        stream: Any,
        frame: pd.DataFrame,
        *,
        ts_col: str = "ts",
    ) -> None:
        """Register a DataFrame as history for ``stream``.

        The stream must expose ``node_id`` and ``interval`` attributes
        (e.g. a :class:`qmtl.runtime.sdk.StreamInput` instance). If
        ``ts_col`` differs from ``\"ts\"``, it is renamed before
        normalization.
        """

        node_id = getattr(stream, "node_id", None)
        interval = getattr(stream, "interval", None)
        if node_id is None or interval is None:
            raise ValueError("stream must provide node_id and interval")
        payload = frame
        if ts_col != "ts":
            if ts_col not in payload.columns:
                raise KeyError(f"timestamp column {ts_col!r} not found")
            payload = payload.rename(columns={ts_col: "ts"})
        self._storage.register(node_id=str(node_id), interval=int(interval), frame=payload)

    def register_csv(
        self,
        stream: Any,
        path: str | Path,
        *,
        ts_col: str = "ts",
        **read_csv_kwargs: Any,
    ) -> None:
        """Register a CSV file as history for ``stream``.

        The CSV is loaded via :func:`pandas.read_csv` and passed to
        :meth:`register_frame`.
        """

        frame = pd.read_csv(path, **read_csv_kwargs)
        self.register_frame(stream, frame, ts_col=ts_col)


__all__ = [
    "HistoryProviderDataSource",
    "CacheDataSource",
    "StorageDataSource",
    "DataFetcherAutoBackfiller",
    "LiveDataFeedImpl",
    "FingerprintPolicy",
    "EnhancedQuestDBProviderSettings",
    "EnhancedQuestDBProvider",
    "InMemorySeamlessProvider",
]
