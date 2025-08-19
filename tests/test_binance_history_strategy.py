from __future__ import annotations

import asyncio
import httpx
from qmtl.io import QuestDBLoader, QuestDBRecorder

from strategies.config import load_config
from strategies.dags.binance_history_dag import BinanceHistoryStrategy
from strategies.utils.binance_fetcher import BinanceFetcher


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
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, url, params=None, timeout=None):
            return DummyResponse()

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)
    fetcher = BinanceFetcher()
    df = asyncio.run(fetcher.fetch(0, 60, node_id="n", interval=60))
    assert not df.empty
    assert list(df.columns) == ["ts", "open", "high", "low", "close", "volume"]
