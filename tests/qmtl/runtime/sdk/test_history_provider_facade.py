import pandas as pd
import pytest

from qmtl.runtime.sdk.history_provider_facade import AugmentedHistoryProvider


class InMemoryBackend:
    """Simple in-memory backend used for AugmentedHistoryProvider tests."""

    def __init__(self) -> None:
        self._rows: dict[tuple[str, int], dict[int, dict]] = {}

    async def read_range(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        table = self._rows.get((node_id, interval), {})
        data = []
        for ts in sorted(table):
            if start <= ts < end:
                row = {"ts": ts}
                row.update(table[ts])
                data.append(row)
        return pd.DataFrame(data)

    async def write_rows(
        self, rows: pd.DataFrame, *, node_id: str, interval: int
    ) -> None:
        if rows.empty:
            return
        table = self._rows.setdefault((node_id, interval), {})
        for record in rows.to_dict("records"):
            ts = int(record["ts"])
            if ts in table:
                raise RuntimeError(f"duplicate write for ts={ts}")
            payload = {k: v for k, v in record.items() if k != "ts"}
            table[ts] = payload

    async def coverage(self, *, node_id: str, interval: int) -> list[tuple[int, int]]:
        table = self._rows.get((node_id, interval), {})
        timestamps = sorted(table)
        if not timestamps:
            return []
        ranges: list[tuple[int, int]] = []
        start = prev = timestamps[0]
        for ts in timestamps[1:]:
            if ts == prev + interval:
                prev = ts
            else:
                ranges.append((start, prev))
                start = prev = ts
        ranges.append((start, prev))
        return ranges


class RecordingFetcher:
    def __init__(self, rows: dict[tuple[str, int], dict[int, dict]]) -> None:
        self._rows = rows
        self.requests: list[tuple[int, int, str, int]] = []

    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        self.requests.append((start, end, node_id, interval))
        table = self._rows.get((node_id, interval), {})
        data = []
        for ts, payload in table.items():
            if start <= ts <= end:
                row = {"ts": ts}
                row.update(payload)
                data.append(row)
        return pd.DataFrame(data)


class ConcurrentFetcher:
    """Fetcher that simulates concurrent writes while a backfill is running."""

    def __init__(self, backend: InMemoryBackend) -> None:
        self.backend = backend

    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        df = pd.DataFrame([{"ts": start, "value": 42}])
        await self.backend.write_rows(df, node_id=node_id, interval=interval)
        return df


@pytest.mark.asyncio
async def test_fill_missing_refreshes_cached_coverage() -> None:
    backend = InMemoryBackend()
    storage = {("node", 60): {60: {"value": 1}, 120: {"value": 2}}}
    fetcher = RecordingFetcher(storage)
    provider = AugmentedHistoryProvider(backend, fetcher=fetcher)

    await backend.write_rows(
        pd.DataFrame([{"ts": 60, "value": 1}]), node_id="node", interval=60
    )
    await provider.coverage(node_id="node", interval=60)

    await backend.write_rows(
        pd.DataFrame([{"ts": 120, "value": 2}]), node_id="node", interval=60
    )

    await provider.fill_missing(60, 120, node_id="node", interval=60)

    assert fetcher.requests == []
    coverage = await provider.coverage(node_id="node", interval=60)
    assert coverage == [(60, 120)]


@pytest.mark.asyncio
async def test_fill_missing_skips_rows_inserted_during_fetch() -> None:
    backend = InMemoryBackend()
    provider = AugmentedHistoryProvider(backend, fetcher=ConcurrentFetcher(backend))

    await provider.fill_missing(0, 0, node_id="node", interval=60)

    data = await backend.read_range(0, 60, node_id="node", interval=60)
    assert list(data["ts"]) == [0]
    coverage = await provider.coverage(node_id="node", interval=60)
    assert coverage == [(0, 0)]
