import pandas as pd
import httpx
import pytest

from qmtl.examples import BinanceFetcher


@pytest.mark.asyncio
async def test_binance_fetcher(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/klines"
        return httpx.Response(200, json=[[1000, "1", None, None, "2"]])

    transport = httpx.MockTransport(handler)

    class DummyClient:
        def __init__(self, *a, **k):
            self._client = httpx.Client(transport=transport)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            self._client.close()

        async def get(self, url):
            request = httpx.Request("GET", url)
            resp = handler(request)
            resp.request = request
            return resp

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    fetcher = BinanceFetcher()
    df = await fetcher.fetch(1, 2, node_id="BTCUSDT", interval="1m")
    expected = pd.DataFrame([{"ts": 1, "open": 1.0, "close": 2.0}])
    pd.testing.assert_frame_equal(df, expected)
