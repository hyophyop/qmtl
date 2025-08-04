import httpx
import pytest

from qmtl.common import AsyncCircuitBreaker
from qmtl.sdk.runner import Runner


class FailingClient:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def post(self, url, json=None):
        raise httpx.RequestError("fail", request=httpx.Request("POST", url))


class FlakyClient:
    calls = 0

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def post(self, url, json=None):
        type(self).calls += 1
        if type(self).calls == 1:
            raise httpx.RequestError("fail", request=httpx.Request("POST", url))
        return httpx.Response(202, json={"queue_map": {"n": "t"}})


class TrackingCircuitBreaker(AsyncCircuitBreaker):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.reset_calls = 0

    def reset(self) -> None:  # type: ignore[override]
        self.reset_calls += 1
        super().reset()


@pytest.mark.asyncio
async def test_post_gateway_circuit_breaker(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", FailingClient)
    cb = AsyncCircuitBreaker(max_failures=1)

    res = await Runner._post_gateway_async(
        gateway_url="http://gw",
        dag={},
        meta=None,
        run_type="x",
        circuit_breaker=cb,
    )
    assert "error" in res and "fail" in res["error"]
    assert cb.is_open

    res = await Runner._post_gateway_async(
        gateway_url="http://gw",
        dag={},
        meta=None,
        run_type="x",
        circuit_breaker=cb,
    )
    assert res["error"] == "circuit open"


@pytest.mark.asyncio
async def test_default_circuit_breaker(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", FailingClient)
    Runner.set_gateway_circuit_breaker(None)

    for _ in range(3):
        res = await Runner._post_gateway_async(
            gateway_url="http://gw",
            dag={},
            meta=None,
            run_type="x",
        )
        assert "error" in res

    res = await Runner._post_gateway_async(
        gateway_url="http://gw",
        dag={},
        meta=None,
        run_type="x",
    )
    assert res["error"] == "circuit open"
    Runner.set_gateway_circuit_breaker(None)


@pytest.mark.asyncio
async def test_breaker_resets_on_success(monkeypatch):
    monkeypatch.setattr(httpx, "AsyncClient", FlakyClient)
    cb = TrackingCircuitBreaker(max_failures=2)

    first = await Runner._post_gateway_async(
        gateway_url="http://gw",
        dag={},
        meta=None,
        run_type="x",
        circuit_breaker=cb,
    )
    assert "error" in first
    assert cb.failures == 1

    second = await Runner._post_gateway_async(
        gateway_url="http://gw",
        dag={},
        meta=None,
        run_type="x",
        circuit_breaker=cb,
    )
    assert second == {"n": "t"}
    assert cb.reset_calls == 1
    assert cb.failures == 0
    assert not cb.is_open

