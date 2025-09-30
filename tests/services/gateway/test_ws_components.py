from __future__ import annotations

import json

import pytest

from qmtl.services.gateway.ws.connections import ConnectionRegistry
from qmtl.services.gateway.ws.duplicate import DuplicateTracker
from qmtl.services.gateway.ws.filters import FilterEvaluator
from qmtl.services.gateway.ws.rate_limit import TokenBucketRateLimiter


class DummyWebSocket:
    def __init__(self, name: str) -> None:
        self.name = name
        self.sent: list[str] = []

    async def send_text(self, payload: str) -> None:
        self.sent.append(payload)


class ManualClock:
    def __init__(self, start: float = 0.0) -> None:
        self.current = start

    def now(self) -> float:
        return self.current

    def advance(self, delta: float) -> None:
        self.current += delta


@pytest.mark.asyncio
async def test_filtering_respects_world_id() -> None:
    registry = ConnectionRegistry()
    evaluator = FilterEvaluator()
    client_all = DummyWebSocket("all")
    client_earth = DummyWebSocket("earth")
    client_mars = DummyWebSocket("mars")

    await registry.add(client_all)
    await registry.add(client_earth, topics={"queue"})
    await registry.update_filters(client_earth, world_id="earth")
    await registry.add(client_mars, topics={"queue"})
    await registry.update_filters(client_mars, world_id="mars")

    clients = await registry.clients_for_topic("queue")
    event = evaluator.decode(json.dumps({"data": {"world_id": "earth"}}))
    filtered = evaluator.filter_clients(clients, event)

    assert {client.websocket for client in filtered} == {client_all, client_earth}


def test_duplicate_tracker_window() -> None:
    tracker = DuplicateTracker(window=3)
    event_a = {"id": "a"}
    event_b = {"id": "b"}
    assert not tracker.seen(event_a)
    assert tracker.seen(event_a)
    assert not tracker.seen(event_b)
    assert not tracker.seen({"id": "c"})
    assert not tracker.seen({"id": "d"})  # old "a" should have rotated out
    assert not tracker.seen(event_a)


def test_rate_limiter_allows_burst_and_recovers() -> None:
    clock = ManualClock()
    limiter = TokenBucketRateLimiter(rate_per_sec=2, time_source=clock.now)
    client = object()

    assert limiter.allow(client)
    assert limiter.allow(client)
    assert not limiter.allow(client)

    clock.advance(0.4)
    assert not limiter.allow(client)

    clock.advance(0.1)
    assert limiter.allow(client)

    limiter.reset(client)
    assert limiter.allow(client)
