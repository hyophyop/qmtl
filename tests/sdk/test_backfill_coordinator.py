import json

import httpx
import pytest

from qmtl.runtime.sdk import metrics as sdk_metrics
from qmtl.runtime.sdk.backfill_coordinator import DistributedBackfillCoordinator


class _FakeClient:
    def __init__(self, response: httpx.Response, calls: list[tuple[str, dict]]):
        self._response = response
        self._calls = calls

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def post(self, url: str, json: dict) -> httpx.Response:
        self._calls.append((url, json))
        return self._response


class _ClientFactory:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, dict]] = []

    def __call__(self) -> _FakeClient:
        response = self._responses.pop(0)
        return _FakeClient(response, self.calls)


def _make_response(status_code: int, payload: dict) -> httpx.Response:
    content = json.dumps(payload).encode("utf-8")
    request = httpx.Request("POST", "http://coordinator.local/mock")
    return httpx.Response(
        status_code=status_code,
        content=content,
        headers={"Content-Type": "application/json"},
        request=request,
    )


@pytest.mark.asyncio
async def test_distributed_coordinator_updates_metrics() -> None:
    sdk_metrics.reset_metrics()
    claim_response = _make_response(
        200,
        {
            "lease": {"token": "abc", "lease_until_ms": 1700},
            "completion_ratio": 0.25,
        },
    )
    complete_response = _make_response(200, {"completion_ratio": 1.0})
    factory = _ClientFactory([claim_response, complete_response])

    coordinator = DistributedBackfillCoordinator(
        "http://coordinator.local", client_factory=factory
    )

    lease = await coordinator.claim("nodeA:60:0:600", 60_000)
    assert lease is not None
    assert lease.token == "abc"

    await coordinator.complete(lease)

    key = ("nodeA", "60", "nodeA:60:0:600")
    assert sdk_metrics.backfill_completion_ratio._vals[key] == 1.0  # type: ignore[attr-defined]
    assert len(factory.calls) == 2


@pytest.mark.asyncio
async def test_distributed_coordinator_gracefully_handles_conflict() -> None:
    sdk_metrics.reset_metrics()
    conflict_response = _make_response(409, {})
    factory = _ClientFactory([conflict_response])

    coordinator = DistributedBackfillCoordinator(
        "http://coordinator.local", client_factory=factory
    )

    lease = await coordinator.claim("nodeA:60:0:600", 60_000)
    assert lease is None
    assert len(factory.calls) == 1
