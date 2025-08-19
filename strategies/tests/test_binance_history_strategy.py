from __future__ import annotations

import asyncio
from typing import Any

import pandas as pd

from qmtl.pipeline import Pipeline

from strategies.dags.binance_history_dag import BinanceHistoryStrategy


def test_strategy_records_and_loads(monkeypatch) -> None:
    """Running BinanceHistoryStrategy writes and loads records."""

    memory_db: dict[str, list[dict[str, Any]]] = {}

    class DummyRecorder:
        def __init__(self, dsn: str, *, table: str | None = None) -> None:
            self.dsn = dsn
            self._table = table

        def bind_stream(self, stream) -> None:  # pragma: no cover - simple binder
            self._stream_id = stream.node_id

        @property
        def table(self) -> str:
            return self._table or getattr(self, "_stream_id")

        async def persist(
            self, node_id: str, interval: int, timestamp: int, payload: dict[str, Any]
        ) -> None:
            rows = memory_db.setdefault(self.table, [])
            rows.append({"node_id": node_id, "interval": interval, "ts": timestamp, **payload})

    class DummyLoader:
        def __init__(self, dsn: str, *, table: str | None = None, fetcher: Any | None = None) -> None:
            self.dsn = dsn
            self._table = table
            self.fetcher = fetcher

        def bind_stream(self, stream) -> None:  # pragma: no cover - simple binder
            self._stream_id = stream.node_id

        @property
        def table(self) -> str:
            return self._table or getattr(self, "_stream_id")

        async def fetch(
            self, start: int, end: int, *, node_id: str, interval: int
        ) -> pd.DataFrame:
            rows = [
                r
                for r in memory_db.get(self.table, [])
                if r["node_id"] == node_id and r["interval"] == interval and start <= r["ts"] < end
            ]
            return pd.DataFrame(rows)

    cfg = {"questdb_dsn": "questdb://", "streams": [{"symbol": "BTCUSDT", "interval": "60s"}]}
    monkeypatch.setattr(
        "strategies.dags.binance_history_dag.load_config", lambda: cfg
    )
    monkeypatch.setattr(
        "strategies.dags.binance_history_dag.QuestDBRecorder", DummyRecorder
    )
    monkeypatch.setattr(
        "strategies.dags.binance_history_dag.QuestDBLoader", DummyLoader
    )

    strat = BinanceHistoryStrategy()
    strat.setup()
    node = strat.nodes[0]
    pipe = Pipeline(strat.nodes)

    ts = 0
    payload = {"open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}
    pipe.feed(node, ts, payload)

    table = node.event_recorder.table
    assert memory_db[table]

    df = asyncio.run(
        node.history_provider.fetch(
            ts, ts + node.interval, node_id=node.node_id, interval=node.interval
        )
    )
    assert not df.empty
    assert df.iloc[0]["close"] == 1.5
