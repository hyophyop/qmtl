import httpx
import pytest

from qmtl.sdk.runner import Runner
from qmtl.common import AsyncCircuitBreaker


class DummyClient:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def post(self, url, json=None):
        raise httpx.RequestError("fail", request=httpx.Request("POST", url))


@pytest.mark.asyncio
async def test_post_gateway_circuit_breaker(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)
    cb = AsyncCircuitBreaker(max_failures=1, reset_timeout=60)

    with pytest.raises(httpx.RequestError):
        await Runner._post_gateway_async(
            gateway_url="http://gw",
            dag={},
            meta=None,
            run_type="x",
            circuit_breaker=cb,
        )

    with pytest.raises(RuntimeError):
        await Runner._post_gateway_async(
            gateway_url="http://gw",
            dag={},
            meta=None,
            run_type="x",
            circuit_breaker=cb,
        )



@pytest.mark.asyncio
async def test_env_config(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", DummyClient)
    monkeypatch.setenv("QMTL_GW_CB_MAX_FAILURES", "1")
    monkeypatch.setenv("QMTL_GW_CB_RESET_TIMEOUT", "60")
    Runner.set_gateway_circuit_breaker(None)

    with pytest.raises(httpx.RequestError):
        await Runner._post_gateway_async(
            gateway_url="http://gw",
            dag={},
            meta=None,
            run_type="x",
        )

    with pytest.raises(RuntimeError):
        await Runner._post_gateway_async(
            gateway_url="http://gw",
            dag={},
            meta=None,
            run_type="x",
        )
    Runner.set_gateway_circuit_breaker(None)

