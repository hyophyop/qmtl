import pandas as pd
import pytest

from qmtl.sdk.data_io import QuestDBLoader, QuestDBSink


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
    monkeypatch.setattr("qmtl.sdk.data_io.asyncpg.connect", dummy_connect)
    src = QuestDBLoader("db")
    df = await src.fetch(1, 3, node_id="n1", interval=60)
    expected = pd.DataFrame([{"ts": 1, "value": 10}, {"ts": 2, "value": 20}])
    pd.testing.assert_frame_equal(df.reset_index(drop=True), expected)


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

    monkeypatch.setattr("qmtl.sdk.data_io.asyncpg.connect", _connect)
    sink = QuestDBSink("db", table="t")
    await sink.persist("n", 60, 1, {"v": 99})

    assert record["dsn"] == "db"
    assert record["closed"] is True
    assert "INSERT INTO t" in record["query"]
    assert record["args"] == ("n", 60, 1, 99)

