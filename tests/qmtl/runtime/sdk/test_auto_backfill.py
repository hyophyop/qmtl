import pandas as pd
import pytest

from qmtl.foundation.common.metrics_factory import get_mapping_store
from qmtl.runtime.sdk.auto_backfill import (
    FetcherBackfillStrategy,
    LiveReplayBackfillStrategy,
)
from qmtl.runtime.sdk.history_provider_facade import AugmentedHistoryProvider
from qmtl.runtime.sdk import metrics


class InMemoryBackend:
    """Simple backend storing rows in memory for strategy tests."""

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
            payload = {k: v for k, v in record.items() if k != "ts"}
            table.setdefault(ts, payload)

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


class StaticFetcher:
    def __init__(self, rows: list[dict]) -> None:
        self._frame = pd.DataFrame(rows)

    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        return self._frame.copy()


class ReplayBuffer:
    def __init__(self) -> None:
        self._events: list[tuple[int, dict]] = []

    def append(self, ts: int, payload: dict) -> None:
        self._events.append((ts, payload))

    async def replay(
        self, start: int, end: int, node_id: str, interval: int
    ) -> list[tuple[int, dict]]:
        return [event for event in self._events if start <= event[0] <= end]


@pytest.mark.asyncio
async def test_fetcher_backfill_strategy_records_metrics() -> None:
    metrics.reset_metrics()
    backend = InMemoryBackend()
    fetcher = StaticFetcher([
        {"ts": 120, "value": 1},
        {"ts": 180, "value": 2},
    ])
    provider = AugmentedHistoryProvider(
        backend, auto_backfill=FetcherBackfillStrategy(fetcher)
    )

    await provider.fill_missing(120, 180, node_id="node", interval=60)

    data = await backend.read_range(60, 240, node_id="node", interval=60)
    assert list(data["ts"]) == [120, 180]

    key = ("fetcher", "node", "60")
    requests_store = get_mapping_store(metrics.history_auto_backfill_requests_total, dict)
    missing_store = get_mapping_store(metrics.history_auto_backfill_missing_ranges_total, dict)
    rows_store = get_mapping_store(metrics.history_auto_backfill_rows_total, dict)
    duration_store = get_mapping_store(metrics.history_auto_backfill_duration_ms, dict)
    assert requests_store[key] == 1
    assert missing_store[key] == 1
    assert rows_store[key] == 2
    assert key[0] in duration_store


@pytest.mark.asyncio
async def test_live_replay_strategy_replays_from_buffer() -> None:
    metrics.reset_metrics()
    backend = InMemoryBackend()
    buffer = ReplayBuffer()
    buffer.append(60, {"value": 1})
    buffer.append(120, {"value": 2})

    provider = AugmentedHistoryProvider(
        backend, auto_backfill=LiveReplayBackfillStrategy(replay_source=buffer.replay)
    )

    await provider.fill_missing(60, 120, node_id="node", interval=60)

    data = await backend.read_range(0, 180, node_id="node", interval=60)
    assert list(data["ts"]) == [60, 120]

    coverage = await provider.coverage(node_id="node", interval=60)
    assert coverage == [(60, 120)]

    key = ("live_replay", "node", "60")
    rows_store = get_mapping_store(metrics.history_auto_backfill_rows_total, dict)
    requests_store = get_mapping_store(metrics.history_auto_backfill_requests_total, dict)
    assert rows_store[key] == 2
    assert requests_store[key] == 1
