import httpx
import pytest

from qmtl.sdk import TagQueryNode
from qmtl.sdk.tagquery_manager import TagQueryManager


@pytest.mark.asyncio
async def test_tagquery_manager_reuses_http_client(monkeypatch):
    node = TagQueryNode(["t1"], interval="60s", period=1)
    created = 0
    closed = False

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"queues": ["q1"]})

    transport = httpx.MockTransport(handler)

    class DummyClient:
        def __init__(self, *args, **kwargs):
            nonlocal created
            created += 1
            self._client = httpx.Client(transport=transport)

        async def get(self, url, params=None):
            request = httpx.Request("GET", url, params=params)
            resp = handler(request)
            resp.request = request
            return resp

        async def aclose(self):
            nonlocal closed
            closed = True
            self._client.close()

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    manager = TagQueryManager("http://gw")
    manager.register(node)

    await manager.resolve_tags()
    await manager.resolve_tags()

    assert created == 1

    await manager.stop()
    assert closed
