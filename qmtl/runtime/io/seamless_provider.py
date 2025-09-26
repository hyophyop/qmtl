from __future__ import annotations

from typing import Any, Callable, Optional
import pandas as pd
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
from qmtl.runtime.sdk.conformance import ConformancePipeline
from qmtl.runtime.io.artifact import ArtifactRegistrar as IOArtifactRegistrar
from qmtl.runtime.sdk.artifacts import ArtifactRegistrar, FileSystemArtifactRegistrar

logger = logging.getLogger(__name__)


class CacheDataSource:
    """In-memory cache data source implementation."""
    
    def __init__(self, cache_provider: HistoryProvider):
        self.cache_provider = cache_provider
        self.priority = DataSourcePriority.CACHE
    
    async def is_available(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> bool:
        try:
            coverage = await self.cache_provider.coverage(node_id=node_id, interval=interval)
            # Check if requested range is fully covered
            for range_start, range_end in coverage:
                if range_start <= start and end <= range_end:
                    return True
            return False
        except Exception:
            return False
    
    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        return await self.cache_provider.fetch(start, end, node_id=node_id, interval=interval)
    
    async def coverage(
        self, *, node_id: str, interval: int
    ) -> list[tuple[int, int]]:
        return await self.cache_provider.coverage(node_id=node_id, interval=interval)


class StorageDataSource:
    """Historical storage data source implementation."""
    
    def __init__(self, storage_provider: HistoryProvider):
        self.storage_provider = storage_provider
        self.priority = DataSourcePriority.STORAGE
    
    async def is_available(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> bool:
        try:
            coverage = await self.storage_provider.coverage(node_id=node_id, interval=interval)
            # Check if requested range is fully covered
            for range_start, range_end in coverage:
                if range_start <= start and end <= range_end:
                    return True
            return False
        except Exception:
            return False
    
    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        return await self.storage_provider.fetch(start, end, node_id=node_id, interval=interval)
    
    async def coverage(
        self, *, node_id: str, interval: int
    ) -> list[tuple[int, int]]:
        return await self.storage_provider.coverage(node_id=node_id, interval=interval)


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
        planned_source = (
            "storage"
            if target_storage and hasattr(target_storage, "storage_provider")
            else "fetcher"
        )
        logger.info(
            "seamless.backfill.attempt",
            extra=self._build_log_extra(
                batch_id=batch_identifier,
                attempt=attempt,
                node_id=node_id,
                interval=interval,
                start=start,
                end=end,
                source=planned_source,
            ),
        )

        # Prefer materializing directly into storage to avoid double-fetch
        if target_storage and hasattr(target_storage, "storage_provider"):
            storage_provider = target_storage.storage_provider
            if hasattr(storage_provider, "fill_missing") and hasattr(storage_provider, "fetch"):
                try:
                    await storage_provider.fill_missing(
                        start, end, node_id=node_id, interval=interval
                    )
                    frame = await storage_provider.fetch(
                        start, end, node_id=node_id, interval=interval
                    )
                    logger.info(
                        "seamless.backfill.succeeded",
                        extra=self._build_log_extra(
                            batch_id=batch_identifier,
                            attempt=attempt,
                            node_id=node_id,
                            interval=interval,
                            start=start,
                            end=end,
                            source="storage",
                        ),
                    )
                    return frame
                except Exception as exc:
                    logger.warning(
                        "seamless.backfill.storage_fallback",
                        extra=self._build_log_extra(
                            batch_id=batch_identifier,
                            attempt=attempt,
                            node_id=node_id,
                            interval=interval,
                            start=start,
                            end=end,
                            source="storage",
                            error=str(exc),
                        ),
                        exc_info=True,
                    )

        # Fallback: fetch directly from external source and return
        try:
            frame = await self.fetcher.fetch(start, end, node_id=node_id, interval=interval)
        except Exception as exc:
            logger.error(
                "seamless.backfill.failed",
                extra=self._build_log_extra(
                    batch_id=batch_identifier,
                    attempt=attempt,
                    node_id=node_id,
                    interval=interval,
                    start=start,
                    end=end,
                    source="fetcher",
                    error=str(exc),
                ),
                exc_info=True,
            )
            raise

        logger.info(
            "seamless.backfill.succeeded",
            extra=self._build_log_extra(
                batch_id=batch_identifier,
                attempt=attempt,
                node_id=node_id,
                interval=interval,
                start=start,
                end=end,
                source="fetcher",
            ),
        )
        return frame
    
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


class EnhancedQuestDBProvider(SeamlessDataProvider):
    """
    Enhanced QuestDB provider with seamless data access capabilities.
    
    This extends the existing QuestDBLoader with auto-backfill and live data support.
    """
    
    def __init__(
        self,
        dsn: str,
        *,
        table: str | None = None,
        fetcher: DataFetcher | None = None,
        live_fetcher: DataFetcher | None = None,
        live_feed: LiveDataFeed | None = None,
        cache_provider: HistoryProvider | None = None,
        strategy: DataAvailabilityStrategy = DataAvailabilityStrategy.SEAMLESS,
        conformance: ConformancePipeline | None = None,
        partial_ok: bool = False,
        registrar: ArtifactRegistrar | None = None,
        node_id_format: str | None = None,
        **kwargs
    ):
        # Import here to avoid circular imports
        from qmtl.runtime.io.historyprovider import QuestDBLoader
        
        # Create the underlying storage provider
        self.storage_provider = QuestDBLoader(dsn, table=table, fetcher=fetcher)
        
        # Create data sources
        storage_source = StorageDataSource(self.storage_provider)
        cache_source = CacheDataSource(cache_provider) if cache_provider else None
        
        # Create backfiller if fetcher is available
        backfiller = DataFetcherAutoBackfiller(fetcher) if fetcher else None
        
        # Create live feed if available (prefer explicit LiveDataFeed)
        live_feed_obj = live_feed or (LiveDataFeedImpl(live_fetcher) if live_fetcher else None)
        
        registrar_obj: ArtifactRegistrar | None = registrar
        if registrar_obj is None:
            registrar_obj = FileSystemArtifactRegistrar.from_env()
        if registrar_obj is None:
            registrar_obj = IOArtifactRegistrar(stabilization_bars=0)

        fmt = node_id_format.strip() if node_id_format else None
        self._node_id_format = fmt
        self._node_id_validator: Callable[[str], None] | None = None
        if fmt:
            if fmt == "ohlcv:{exchange}:{symbol}:{timeframe}":
                self._node_id_validator = _validate_ohlcv_node_id
            else:
                logger.warning(
                    "enhanced_provider.node_id_validation.unsupported_format",
                    extra={"format": fmt},
                )

        super().__init__(
            strategy=strategy,
            cache_source=cache_source,
            storage_source=storage_source,
            backfiller=backfiller,
            live_feed=live_feed_obj,
            conformance=conformance or ConformancePipeline(),
            partial_ok=partial_ok,
            registrar=registrar_obj,
            **kwargs
        )

    def bind_stream(self, stream) -> None:
        """Bind to a stream like the original HistoryProvider."""
        self.storage_provider.bind_stream(stream)

        # Also bind cache if available
        if self.cache_source and hasattr(self.cache_source.cache_provider, 'bind_stream'):
            self.cache_source.cache_provider.bind_stream(stream)

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


__all__ = [
    "CacheDataSource",
    "StorageDataSource", 
    "DataFetcherAutoBackfiller",
    "LiveDataFeedImpl",
    "EnhancedQuestDBProvider",
]
