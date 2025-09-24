import pandas as pd
import pytest

from qmtl.runtime.sdk import (
    QuestDBHistoryProvider,
    QuestDBRecorder,
    HistoryProvider,
    EventRecorder,
    EventRecorderService,
    FetcherBackfillStrategy,
    StreamInput,
    AugmentedHistoryProvider,
)
from tests.dummy_fetcher import DummyDataFetcher


class DummyConn:
    def __init__(self, rows):
        self.rows = rows
        self.closed = False

    async def fetch(self, query, *args):
        return self.rows

    async def close(self):
        self.closed = True


async def dummy_connect(*_args, **_kwargs):
    rows = [
        {"ts": 1, "value": 10},
        {"ts": 2, "value": 20},
    ]
    return DummyConn(rows)


@pytest.mark.asyncio
async def test_questdb_fetch(monkeypatch):
    monkeypatch.setattr("qmtl.runtime.io.historyprovider.asyncpg.connect", dummy_connect)
    src = QuestDBHistoryProvider("db", table="node_data")
    assert isinstance(src, HistoryProvider)
    df = await src.fetch(1, 3, node_id="n1", interval=60)
    expected = pd.DataFrame([{"ts": 1, "value": 10}, {"ts": 2, "value": 20}])
    pd.testing.assert_frame_equal(df.reset_index(drop=True), expected)


@pytest.mark.asyncio
async def test_questdb_coverage(monkeypatch):
    class DummyConn:
        def __init__(self):
            self.closed = False

        async def fetch(self, query, *args):
            return [
                {"ts": 60},
                {"ts": 120},
                {"ts": 240},
                {"ts": 300},
            ]

        async def close(self):
            self.closed = True

    async def _connect(*_args, **_kwargs):
        return DummyConn()

    monkeypatch.setattr("qmtl.runtime.io.historyprovider.asyncpg.connect", _connect)
    src = QuestDBHistoryProvider("db", table="node_data")
    assert isinstance(src, HistoryProvider)
    ranges = await src.coverage(node_id="n", interval=60)
    assert ranges == [(60, 120), (240, 300)]


@pytest.mark.asyncio
async def test_questdb_fill_missing_no_fetcher(monkeypatch):
    executed: list[tuple[str, tuple]] = []

    class DummyConn:
        async def fetch(self, query, *args):
            return [{"ts": 60}, {"ts": 180}]

        async def execute(self, query, *args):
            executed.append((query, args))

        async def close(self):
            pass

    async def _connect(*_args, **_kwargs):
        return DummyConn()

    monkeypatch.setattr("qmtl.runtime.io.historyprovider.asyncpg.connect", _connect)
    src = QuestDBHistoryProvider("db", table="node_data")
    assert isinstance(src, HistoryProvider)
    with pytest.raises(RuntimeError):
        await src.fill_missing(60, 180, node_id="n", interval=60)


@pytest.mark.asyncio
async def test_fill_missing_without_fetcher_raises(monkeypatch):
    class DummyConn:
        async def fetch(self, query, *args):
            return []

        async def execute(self, query, *args):
            pass

        async def close(self):
            pass

    async def _connect(*_args, **_kwargs):
        return DummyConn()

    monkeypatch.setattr("qmtl.runtime.io.historyprovider.asyncpg.connect", _connect)
    loader = QuestDBHistoryProvider("db", table="node_data")
    assert isinstance(loader, HistoryProvider)
    with pytest.raises(RuntimeError):
        await loader.fill_missing(0, 0, node_id="n", interval=60)


@pytest.mark.asyncio
async def test_questdb_fill_missing(monkeypatch):
    executed: list[tuple[str, tuple]] = []
    fetcher = DummyDataFetcher()

    class DummyConn:
        async def fetch(self, query, *args):
            return [{"ts": 60}]

        async def execute(self, query, *args):
            executed.append((query, args))

        async def close(self):
            pass

    async def _connect(*_args, **_kwargs):
        return DummyConn()

    monkeypatch.setattr("qmtl.runtime.io.historyprovider.asyncpg.connect", _connect)
    src = QuestDBHistoryProvider(
        "db",
        table="node_data",
        fetcher=fetcher,
        auto_backfill=FetcherBackfillStrategy(fetcher),
    )
    assert isinstance(src, HistoryProvider)
    await src.fill_missing(60, 180, node_id="n", interval=60)

    inserted_args = [args for _, args in executed]
    assert inserted_args == [
        ("n", 60, 120, 1),
        ("n", 60, 180, 2),
    ]


@pytest.mark.asyncio
async def test_questdb_persist(monkeypatch):
    record: dict = {}

    class DummyConn:
        async def execute(self, query, *args):
            record["query"] = query
            record["args"] = args

        async def close(self):
            record["closed"] = True

    async def _connect(*args, **kwargs):
        record["dsn"] = kwargs.get("dsn") or (args[0] if args else None)
        return DummyConn()

    monkeypatch.setattr("qmtl.runtime.io.eventrecorder.asyncpg.connect", _connect)
    recorder = QuestDBRecorder("db", table="t")
    assert isinstance(recorder, EventRecorder)
    await recorder.persist("n", 60, 1, {"v": 99})

    assert record["dsn"] == "db"
    assert record["closed"] is True
    assert "INSERT INTO t" in record["query"]
    assert record["args"] == ("n", 60, 1, 99)


def test_stream_input_records_on_feed():
    from qmtl.runtime.sdk.node import StreamInput

    events = []

    class DummyRecorder:
        async def persist(self, node_id, interval, timestamp, payload):
            events.append((node_id, interval, timestamp, payload))

    s = StreamInput(interval="60s", period=1, event_service=EventRecorderService(DummyRecorder()))

    s.feed("s", 60, 1, {"v": 1})
    assert events == [(s.node_id, 60, 1, {"v": 1})]


class _InMemoryBackend:
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


class _RecordingFetcher:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int, str, int]] = []

    async def fetch(
        self, start: int, end: int, *, node_id: str, interval: int
    ) -> pd.DataFrame:
        self.calls.append((start, end, node_id, interval))
        rows = []
        ts = start
        while ts <= end:
            rows.append({"ts": ts, "value": ts})
            ts += interval
        return pd.DataFrame(rows)


@pytest.mark.asyncio
async def test_augmented_provider_ensure_range_auto_backfills() -> None:
    backend = _InMemoryBackend()
    fetcher = _RecordingFetcher()
    provider = AugmentedHistoryProvider(
        backend, auto_backfill=FetcherBackfillStrategy(fetcher)
    )

    await provider.ensure_range(60, 180, node_id="node", interval=60)

    assert fetcher.calls == [(60, 180, "node", 60)]
    coverage = await provider.coverage(node_id="node", interval=60)
    assert coverage == [(60, 180)]

    frame = await provider.fetch(60, 240, node_id="node", interval=60)
    assert list(frame["ts"]) == [60, 120, 180]


@pytest.mark.asyncio
async def test_stream_input_load_history_uses_auto_backfill() -> None:
    backend = _InMemoryBackend()
    fetcher = _RecordingFetcher()
    provider = AugmentedHistoryProvider(
        backend, auto_backfill=FetcherBackfillStrategy(fetcher)
    )
    stream = StreamInput(interval=60, period=3, history_provider=provider)

    await stream.load_history(60, 240)

    snapshot = stream.cache._snapshot()[stream.node_id][60]
    timestamps = [ts for ts, _ in snapshot]
    assert timestamps == [60, 120, 180]
    assert fetcher.calls == [(60, 180, stream.node_id, 60)]
