from __future__ import annotations

import asyncio
import httpx
from qmtl.io import QuestDBLoader, QuestDBRecorder

from strategies.dags.binance_history_dag import BinanceHistoryStrategy
from strategies.utils.binance_fetcher import BinanceFetcher


def test_stream_binding() -> None:
    strat = BinanceHistoryStrategy()
    strat.setup()
    price = strat.nodes[0]
    assert isinstance(price.history_provider, QuestDBLoader)
    assert isinstance(price.event_recorder, QuestDBRecorder)
    assert isinstance(price.history_provider.fetcher, BinanceFetcher)


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
