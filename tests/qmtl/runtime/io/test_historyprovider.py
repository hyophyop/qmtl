from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from qmtl.runtime.io import historyprovider


class _FakeConnection:
    def __init__(self) -> None:
        self.commands: list[tuple[str, tuple]] = []
        self.closed = False

    async def execute(self, sql: str, *args) -> None:
        self.commands.append((sql, args))

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_write_rows_builds_single_insert_statement(monkeypatch):
    backend = historyprovider.QuestDBBackend("postgresql://qdb", table="candles")
    fake_conn = _FakeConnection()

    async def fake_connect(dsn: str):
        return fake_conn

    monkeypatch.setattr(historyprovider.asyncpg, "connect", fake_connect)

    rows = pd.DataFrame(
        [
            {"ts": np.int64(10), "open": np.float64(1.1), "close": np.float64(1.2)},
            {"ts": np.int64(20), "open": np.float64(1.3), "close": np.float64(1.4)},
        ]
    )

    await backend.write_rows(rows, node_id="node-1", interval=60)

    assert len(fake_conn.commands) == 2
    sql, args = fake_conn.commands[0]
    assert sql == "INSERT INTO candles(node_id, interval, ts, open, close) VALUES($1, $2, $3, $4, $5)"
    assert args == ("node-1", 60, 10, 1.1, 1.2)
    assert fake_conn.closed is True


@pytest.mark.asyncio
async def test_write_rows_raises_on_missing_ts_and_closes(monkeypatch):
    backend = historyprovider.QuestDBBackend("postgresql://qdb", table="candles")
    fake_conn = _FakeConnection()

    async def fake_connect(dsn: str):
        return fake_conn

    monkeypatch.setattr(historyprovider.asyncpg, "connect", fake_connect)

    rows = pd.DataFrame([{"open": 1.0, "close": 1.1}])

    with pytest.raises(KeyError):
        await backend.write_rows(rows, node_id="node-1", interval=60)

    assert fake_conn.closed is True
    assert fake_conn.commands == []
