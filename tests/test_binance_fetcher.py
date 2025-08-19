import pandas as pd
import httpx
import pytest

from qmtl.examples import BinanceFetcher


class DummyClient:
    def __init__(self, transport):
        self._client = httpx.Client(transport=transport)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._client.close()

    async def get(self, url, params=None, timeout=None):
        request = httpx.Request("GET", url, params=params)
        resp = self._client.send(request)
        return resp


@pytest.mark.asyncio
async def test_binance_fetcher(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/klines"
        assert request.url.params["symbol"] == "BTCUSDT"
        assert request.url.params["interval"] == "1m"
        data = [[0, "1", "2", "0.5", "3", "4", 2000, 0, 0, 0, 0, 0]]
        return httpx.Response(200, json=data, request=request)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: DummyClient(transport))

    fetcher = BinanceFetcher()
    df = await fetcher.fetch(1, 2, node_id="BTCUSDT", interval="1m")
    expected = pd.DataFrame(
        [{"ts": 2, "open": 1.0, "high": 2.0, "low": 0.5, "close": 3.0, "volume": 4.0}]
    )
    pd.testing.assert_frame_equal(df, expected)


@pytest.mark.asyncio
async def test_binance_fetcher_http_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"msg": "error"}, request=request)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: DummyClient(transport))

    fetcher = BinanceFetcher()
    with pytest.raises(httpx.HTTPStatusError):
        await fetcher.fetch(1, 2, node_id="BTCUSDT", interval="1m")
