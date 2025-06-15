import pandas as pd
import pytest

from qmtl.io import QuestDBLoader, QuestDBRecorder
from tests.dummy_fetcher import DummyDataFetcher


class DummyConn:
    def __init__(self, rows):
        self.rows = rows
        self.closed = False

    async def fetch(self, query, *args):
        return self.rows

    async def close(self):
        self.closed = True


async def dummy_connect(_):
    rows = [
        {"ts": 1, "value": 10},
        {"ts": 2, "value": 20},
    ]
    return DummyConn(rows)


@pytest.mark.asyncio
async def test_questdb_fetch(monkeypatch):
    monkeypatch.setattr("qmtl.io.historyprovider.asyncpg.connect", dummy_connect)
    src = QuestDBLoader("db")
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

    async def _connect(_):
        return DummyConn()

    monkeypatch.setattr("qmtl.io.historyprovider.asyncpg.connect", _connect)
    src = QuestDBLoader("db")
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

    async def _connect(_):
        return DummyConn()

    monkeypatch.setattr("qmtl.io.historyprovider.asyncpg.connect", _connect)
    src = QuestDBLoader("db")
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

    async def _connect(_):
        return DummyConn()

    monkeypatch.setattr("qmtl.io.historyprovider.asyncpg.connect", _connect)
    loader = QuestDBLoader("db")
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

    async def _connect(_):
        return DummyConn()

    monkeypatch.setattr("qmtl.io.historyprovider.asyncpg.connect", _connect)
    src = QuestDBLoader("db", fetcher=fetcher)
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

    async def _connect(dsn):
        record["dsn"] = dsn
        return DummyConn()

    monkeypatch.setattr("qmtl.io.eventrecorder.asyncpg.connect", _connect)
    recorder = QuestDBRecorder("db", table="t")
    await recorder.persist("n", 60, 1, {"v": 99})

    assert record["dsn"] == "db"
    assert record["closed"] is True
    assert "INSERT INTO t" in record["query"]
    assert record["args"] == ("n", 60, 1, 99)


def test_stream_input_records_on_feed():
    from qmtl.sdk.node import StreamInput

    events = []

    class DummyRecorder:
        async def persist(self, node_id, interval, timestamp, payload):
            events.append((node_id, interval, timestamp, payload))

    s = StreamInput(interval=60, period=1, event_recorder=DummyRecorder())

    s.feed("s", 60, 1, {"v": 1})
    assert events == [(s.node_id, 60, 1, {"v": 1})]

