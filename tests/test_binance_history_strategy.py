from __future__ import annotations

import asyncio
import pandas as pd
import httpx
from qmtl.io import QuestDBLoader, QuestDBRecorder

from strategies.config import load_config
from strategies.binance_history_strategy import BinanceHistoryStrategy
from qmtl.io import BinanceFetcher
from qmtl.sdk.runner import Runner
from qmtl.sdk import StreamInput
from qmtl.io import binance_fetcher as bf_mod


def test_stream_binding() -> None:
    cfg = load_config()
    strat = BinanceHistoryStrategy()
    strat.setup()
    stream_count = len(cfg.get("streams", []))
    assert len(strat.nodes) == stream_count * 2
    price_nodes = strat.nodes[::2]
    for node in price_nodes:
        assert isinstance(node.history_provider, QuestDBLoader)
        assert isinstance(node.event_recorder, QuestDBRecorder)
        assert node.history_provider.dsn == cfg["questdb_dsn"]
        assert node.event_recorder.dsn == cfg["questdb_dsn"]
        assert isinstance(node.history_provider.fetcher, BinanceFetcher)


def test_fetcher_returns_dataframe(monkeypatch) -> None:
    class DummyResponse:
        def json(self):
            return [[0, "1", "1", "1", "1", "1", 60, "0", 0, "0", "0", "0"]]

        def raise_for_status(self) -> None:
            return None

    class DummyClient:
        async def get(self, url, params=None, timeout=None):
            return DummyResponse()

        async def aclose(self):
            return None

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)
    bf_mod._close_client_sync()
    fetcher = BinanceFetcher()
    df = asyncio.run(fetcher.fetch(0, 60, node_id="n", interval="1m"))
    assert not df.empty
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]


def test_backtest_records_and_loads(monkeypatch) -> None:
    memory_db: dict[str, dict[int, dict[str, float]]] = {}

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
            self, node_id: str, interval: int, timestamp: int, payload: dict[str, float]
        ) -> None:
            table = memory_db.setdefault(self.table, {})
            table[timestamp] = {
                "node_id": node_id,
                "interval": interval,
                "ts": timestamp,
                **payload,
            }

    class DummyLoader:
        def __init__(self, dsn: str, *, table: str | None = None, fetcher=None) -> None:
            self.dsn = dsn
            self._table = table
            self.fetcher = fetcher

        def bind_stream(self, stream) -> None:  # pragma: no cover - simple binder
            self._stream_id = stream.node_id

        @property
        def table(self) -> str:
            return self._table or getattr(self, "_stream_id")

        async def coverage(self, *, node_id: str, interval: int):
            rows = memory_db.get(self.table, {})
            ts = sorted(rows)
            if not ts:
                return []
            ranges: list[tuple[int, int]] = []
            start = prev = ts[0]
            for t in ts[1:]:
                if t == prev + interval:
                    prev = t
                else:
                    ranges.append((start, prev))
                    start = prev = t
            ranges.append((start, prev))
            return ranges

        async def fill_missing(self, start: int, end: int, *, node_id: str, interval: int) -> None:
            df = await self.fetcher.fetch(start, end, node_id=node_id, interval=interval)
            table = memory_db.setdefault(self.table, {})
            for _, row in df.iterrows():
                ts = int(row["ts"])
                table[ts] = {
                    "node_id": node_id,
                    "interval": interval,
                    "ts": ts,
                    **{k: row[k] for k in row.index if k != "ts"},
                }

        async def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
            rows = [
                r
                for ts, r in sorted(memory_db.get(self.table, {}).items())
                if start <= ts < end and r["node_id"] == node_id and r["interval"] == interval
            ]
            return pd.DataFrame(rows)

    class DummyFetcher:
        def __init__(self) -> None:
            self.calls: list[tuple[int, int, str, int]] = []

        async def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
            self.calls.append((start, end, node_id, interval))
            rows = []
            for ts in range(start, end + interval, interval):
                rows.append({
                    "ts": ts,
                    "open": 1.0,
                    "high": 1.0,
                    "low": 1.0,
                    "close": 1.0,
                    "volume": 1.0,
                })
            return pd.DataFrame(rows)

    cfg = {"questdb_dsn": "questdb://", "streams": [{"symbol": "BTCUSDT", "interval": "60s"}]}
    fetcher = DummyFetcher()
    monkeypatch.setattr("strategies.dags.binance_history_dag.load_config", lambda: cfg)
    monkeypatch.setattr("strategies.dags.binance_history_dag.QuestDBRecorder", DummyRecorder)
    monkeypatch.setattr("strategies.dags.binance_history_dag.QuestDBLoader", DummyLoader)
    monkeypatch.setattr("strategies.dags.binance_history_dag.BinanceFetcher", lambda: fetcher)

    async def fake_gateway(**kwargs):
        return {}

    class DummyManager:
        async def resolve_tags(self, offline: bool = False) -> None:
            return None

    monkeypatch.setattr("qmtl.sdk.runner.Runner._post_gateway_async", staticmethod(fake_gateway))
    monkeypatch.setattr("qmtl.sdk.runner.Runner._init_tag_manager", lambda s, u: DummyManager())

    strategy = Runner.backtest(
        BinanceHistoryStrategy,
        start_time=0,
        end_time=120,
        gateway_url="http://gw",
    )
    node = strategy.nodes[0]

    df = asyncio.run(
        node.history_provider.fetch(
            0, 180, node_id=node.node_id, interval=node.interval
        )
    )
    assert not df.empty
    assert set(df["ts"]) == {0, 60, 120}


def test_load_history_invokes_fetcher(monkeypatch) -> None:
    called: dict[str, tuple[int, int, str, int]] = {}

    async def dummy_fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
        called["args"] = (start, end, node_id, interval)
        return pd.DataFrame([
            {"ts": start, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}
        ])

    monkeypatch.setattr(BinanceFetcher, "fetch", dummy_fetch)
    fetcher = BinanceFetcher()

    class DummyLoader:
        def __init__(self, dsn: str, *, fetcher=None) -> None:
            self.dsn = dsn
            self.fetcher = fetcher

        def bind_stream(self, stream) -> None:  # pragma: no cover - simple binder
            self._stream_id = stream.node_id

        async def fetch(self, start: int, end: int, *, node_id: str, interval: int) -> pd.DataFrame:
            return await self.fetcher.fetch(start, end, node_id=node_id, interval=interval)

    stream = StreamInput(
        interval=60,
        period=1,
        history_provider=DummyLoader("dsn", fetcher=fetcher),
    )
    asyncio.run(stream.load_history(0, 60))
    assert "args" in called
