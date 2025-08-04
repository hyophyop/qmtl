import httpx
import pytest

from qmtl.sdk.runner import Runner


@pytest.mark.asyncio
async def test_runner_reuses_http_client(monkeypatch):
    created = 0
    closed = False

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"queue_map": {}})

    transport = httpx.MockTransport(handler)

    class DummyClient:
        def __init__(self, *a, **k):
            nonlocal created
            created += 1
            self._client = httpx.Client(transport=transport)

        async def post(self, url, json=None):
            request = httpx.Request("POST", url, json=json)
            resp = handler(request)
            resp.request = request
            return resp

        async def aclose(self):
            nonlocal closed
            closed = True
            self._client.close()

    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)

    await Runner._post_gateway_async(
        gateway_url="http://gw", dag={}, meta=None, run_type="test"
    )
    await Runner._post_gateway_async(
        gateway_url="http://gw", dag={}, meta=None, run_type="test"
    )

    assert created == 1

    await Runner.aclose_http_client()
    assert closed
