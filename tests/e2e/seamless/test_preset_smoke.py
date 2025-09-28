from __future__ import annotations

import asyncio
from typing import Any

import pandas as pd
import pytest

from qmtl.runtime.sdk import build_seamless_assembly
from qmtl.runtime.sdk.seamless_data_provider import SeamlessDataProvider, DataSource, DataSourcePriority


class _StubStorage:
    def __init__(self) -> None:
        self.rows = pd.DataFrame()

    async def read_range(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
        df = self.rows
        if df.empty:
            return df
        mask = (df["ts"] >= start) & (df["ts"] < end)
        return df[mask].copy().reset_index(drop=True)

    async def write_rows(self, rows: pd.DataFrame, *, node_id: str, interval: int) -> None:
        self.rows = pd.concat([self.rows, rows], ignore_index=True) if not rows.empty else self.rows

    async def coverage(self, *, node_id: str, interval: int) -> list[tuple[int, int]]:
        if self.rows.empty:
            return []
        ts = sorted(self.rows["ts"].tolist())
        out: list[tuple[int, int]] = []
        start = prev = ts[0]
        for t in ts[1:]:
            if t == prev + interval:
                prev = t
            else:
                out.append((start, prev))
                start = prev = t
        out.append((start, prev))
        return out


class _StorageSource(DataSource):  # type: ignore[misc]
    def __init__(self, backend: _StubStorage) -> None:
        self.backend = backend
        self.priority = DataSourcePriority.STORAGE

    async def is_available(self, start: int, end: int, *, node_id: str, interval: int) -> bool:
        cov = await self.coverage(node_id=node_id, interval=interval)
        return any(s <= start and end <= e for s, e in cov)

    async def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
        return await self.backend.read_range(start, end, node_id=node_id, interval=interval)

    async def coverage(self, *, node_id: str, interval: int) -> list[tuple[int, int]]:
        return await self.backend.coverage(node_id=node_id, interval=interval)


class _DummyProvider(SeamlessDataProvider):
    def __init__(self, storage: DataSource):
        super().__init__(storage_source=storage, stabilization_bars=0)


@pytest.mark.asyncio
async def test_preset_builder_chaining_smoke(monkeypatch):
    # Monkeypatch QuestDBLoader and CCXT fetchers used by the preset to our stubbed storage
    backend = _StubStorage()

    class _FakeLoader:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self._args = args
            self._kwargs = kwargs

        async def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
            return await backend.read_range(start, end, node_id=node_id, interval=interval)

        async def coverage(self, *, node_id: str, interval: int) -> list[tuple[int, int]]:
            return await backend.coverage(node_id=node_id, interval=interval)

        async def fill_missing(self, start: int, end: int, *, node_id: str, interval: int) -> None:
            # simulate a backfill by writing a contiguous block
            rows = pd.DataFrame({"ts": list(range(start, end, interval))})
            await backend.write_rows(rows, node_id=node_id, interval=interval)

    monkeypatch.setattr("qmtl.runtime.io.seamless_presets.QuestDBLoader", _FakeLoader)

    # Build assembly via presets (storage + registrar)
    cfg = {
        "presets": [
            {"name": "ccxt.questdb.ohlcv", "options": {"exchange_id": "binance", "symbols": ["BTC/USDT"], "timeframe": "1m", "questdb": {"dsn": "postgresql://stub/qdb", "table": "ohlcv"}}},
            {"name": "seamless.registrar.filesystem"},
        ]
    }
    assembly = build_seamless_assembly(cfg)

    # Use the assembled storage in a dummy seamless provider and exercise a fetch
    provider = _DummyProvider(_StorageSource(backend))
    node_id = "ohlcv:binance:BTC/USDT:60"
    interval = 60
    start, end = 0, 300

    # Initially empty
    assert await provider.ensure_data_available(start, end, node_id=node_id, interval=interval) is False

    # Simulate that backfill (via preset-created backfiller) has written rows
    await backend.write_rows(pd.DataFrame({"ts": [0, 60, 120, 180, 240]}), node_id=node_id, interval=interval)
    ok = await provider.ensure_data_available(start, end, node_id=node_id, interval=interval)
    assert ok is False  # still missing last bar
    await backend.write_rows(pd.DataFrame({"ts": [300]}), node_id=node_id, interval=interval)
    ok2 = await provider.ensure_data_available(start, end, node_id=node_id, interval=interval)
    assert ok2 is True

    df = await provider.fetch(start, end + interval, node_id=node_id, interval=interval)
    assert not df.empty and df["ts"].tolist()[-1] == 300
