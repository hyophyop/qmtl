from __future__ import annotations

import polars as pl

from qmtl.runtime.io.seamless_provider import (
    CacheDataSource,
    HistoryProviderDataSource,
    StorageDataSource,
)
from qmtl.runtime.sdk.data_io import HistoryProvider
from qmtl.runtime.sdk.seamless_data_provider import DataSourcePriority


class _DummyHistoryProvider(HistoryProvider):
    async def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pl.DataFrame:
        return pl.DataFrame()

    async def coverage(self, *, node_id: str, interval: int) -> list[tuple[int, int]]:
        return []

    async def fill_missing(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> None:
        return None

    async def ensure_range(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> None:
        await self.fill_missing(start, end, node_id=node_id, interval=interval)


def test_cache_data_source_wrapper_sets_cache_priority() -> None:
    provider = _DummyHistoryProvider()

    wrapper = CacheDataSource(provider)

    assert isinstance(wrapper, HistoryProviderDataSource)
    assert wrapper.priority is DataSourcePriority.CACHE
    assert wrapper.provider is provider


def test_storage_data_source_wrapper_sets_storage_priority() -> None:
    provider = _DummyHistoryProvider()

    wrapper = StorageDataSource(provider)

    assert isinstance(wrapper, HistoryProviderDataSource)
    assert wrapper.priority is DataSourcePriority.STORAGE
    assert wrapper.provider is provider
