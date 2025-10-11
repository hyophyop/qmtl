import json
import logging

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


@pytest.mark.asyncio
async def test_distributed_coordinator_emits_success_logs(
    caplog: pytest.LogCaptureFixture,
    configure_sdk,
) -> None:
    sdk_metrics.reset_metrics()
    caplog.set_level(logging.INFO, logger="qmtl.runtime.sdk.backfill_coordinator")
    configure_sdk({"connectors": {"worker_id": "worker-42"}})

    claim_response = _make_response(
        200,
        {
            "lease": {"token": "abc", "lease_until_ms": 2000},
            "completion_ratio": 0.5,
        },
    )
    complete_response = _make_response(200, {"completion_ratio": 1.0})
    fail_response = _make_response(200, {"completion_ratio": 0.0})
    factory = _ClientFactory([claim_response, complete_response, fail_response])

    coordinator = DistributedBackfillCoordinator(
        "http://coordinator.local", client_factory=factory
    )

    key = "nodeA:60:1700:1760:world-1:2024-01-01T00:00:00Z"
    lease = await coordinator.claim(key, 60_000)
    assert lease is not None

    await coordinator.complete(lease)
    await coordinator.fail(lease, "synthetic_failure")

    records = [
        record
        for record in caplog.records
        if record.name == "qmtl.runtime.sdk.backfill_coordinator"
    ]
    messages = [record.getMessage() for record in records]
    assert messages == [
        "seamless.backfill.coordinator_claimed",
        "seamless.backfill.coordinator_completed",
        "seamless.backfill.coordinator_failed",
    ]

    claim_record = records[0]
    assert claim_record.coordinator_id == "coordinator.local"
    assert claim_record.worker == "worker-42"
    assert claim_record.lease_key == key
    assert claim_record.lease_token == "abc"
    assert claim_record.lease_until_ms == 2000
    assert claim_record.batch_start == 1700
    assert claim_record.batch_end == 1760
    assert claim_record.world == "world-1"
    assert claim_record.requested_as_of == "2024-01-01T00:00:00Z"
    assert claim_record.completion_ratio == pytest.approx(0.5)

    complete_record = records[1]
    assert complete_record.completion_ratio == pytest.approx(1.0)
    assert not hasattr(complete_record, "reason")

    fail_record = records[2]
    assert fail_record.completion_ratio == pytest.approx(0.0)
    assert fail_record.reason == "synthetic_failure"

    assert len(factory.calls) == 3
