import httpx
import pytest

from qmtl.sdk.runner import Runner
from tests.sample_strategy import SampleStrategy


@pytest.fixture
def gateway_mock(monkeypatch):
    """Patch ``httpx.AsyncClient`` with a handler-driven mock."""

    def install(handler):
        transport = httpx.MockTransport(handler)

        class DummyClient:
            def __init__(self, *args, **kwargs):
                self._client = httpx.Client(transport=transport)

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                self._client.close()

            async def post(self, url, json=None):
                request = httpx.Request("POST", url, json=json)
                return handler(request)

        monkeypatch.setattr(httpx, "AsyncClient", DummyClient)
        return handler

    return install


@pytest.fixture
def gateway_response(gateway_mock):
    """Provide a default 202 gateway response and patch the client."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(202, json={"strategy_id": "s"})

    gateway_mock(handler)
    return handler


@pytest.fixture
def runner_with_gateway(gateway_response):
    """Run ``SampleStrategy`` against the gateway with default parameters."""

    def run(strategy_cls=SampleStrategy, **kwargs):
        params = {"world_id": "w", "gateway_url": "http://gw"}
        params.update(kwargs)
        return Runner.run(strategy_cls, **params)

    return run
