import httpx
import polars as pl
from polars.testing import assert_frame_equal
import pytest

from qmtl.runtime.io import BinanceFetcher
from qmtl.runtime.io import binance_fetcher as bf_mod


class DummyClient:
    def __init__(self, transport):
        self._client = httpx.Client(transport=transport)

    async def get(self, url, params=None, timeout=None):
        request = httpx.Request("GET", url, params=params)
        return self._client.send(request)

    async def aclose(self):
        self._client.close()


@pytest.fixture(autouse=True)
def reset_client():
    bf_mod._close_client_sync()
    bf_mod._CLIENT = None
    yield
    bf_mod._close_client_sync()
    bf_mod._CLIENT = None


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
    expected = pl.DataFrame(
        [{"ts": 2, "open": 1.0, "high": 2.0, "low": 0.5, "close": 3.0, "volume": 4.0}]
    )
    assert_frame_equal(df, expected)


@pytest.mark.asyncio
async def test_binance_fetcher_http_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"msg": "error"}, request=request)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: DummyClient(transport))

    fetcher = BinanceFetcher()
    with pytest.raises(httpx.HTTPStatusError):
        await fetcher.fetch(1, 2, node_id="BTCUSDT", interval="1m")


@pytest.mark.asyncio
async def test_binance_fetcher_defaults(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["symbol"] == "ETHUSDT"
        assert request.url.params["interval"] == "5m"
        data = [[0, "1", "2", "0.5", "3", "4", 2000, 0, 0, 0, 0, 0]]
        return httpx.Response(200, json=data, request=request)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: DummyClient(transport))

    fetcher = BinanceFetcher(symbol="ETHUSDT", interval="5m")
    df = await fetcher.fetch(1, 2, node_id="BTCUSDT", interval="1m")
    expected = pl.DataFrame(
        [{"ts": 2, "open": 1.0, "high": 2.0, "low": 0.5, "close": 3.0, "volume": 4.0}]
    )
    assert_frame_equal(df, expected)


@pytest.mark.asyncio
async def test_reuses_client(monkeypatch):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[[0, "1", "1", "1", "1", "1", 0, 0, 0, 0, 0, 0]], request=request)

    transport = httpx.MockTransport(handler)

    def factory(*a, **k):
        nonlocal calls
        calls += 1
        return DummyClient(transport)

    monkeypatch.setattr(httpx, "AsyncClient", factory)

    fetcher = BinanceFetcher()
    await fetcher.fetch(1, 2, node_id="BTCUSDT", interval="1m")
    await fetcher.fetch(1, 2, node_id="BTCUSDT", interval="1m")
    assert calls == 1
