from __future__ import annotations

import asyncio
import httpx
from qmtl.io import QuestDBLoader, QuestDBRecorder

from strategies.config import load_config
from strategies.binance_history_strategy import BinanceHistoryStrategy
from qmtl.io import BinanceFetcher
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
    bf_mod._close_client_sync()
