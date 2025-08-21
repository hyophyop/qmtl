import httpx
import pytest

from qmtl.gateway.api import create_app
from qmtl.gateway import metrics
from qmtl.common.cloudevents import format_event


class DummyDagManagerClient:
    async def status(self) -> bool:
        return True

    async def get_queues_by_tag(self, *args, **kwargs):
        return []

    async def close(self) -> None:  # pragma: no cover - nothing to clean up
        pass


@pytest.mark.asyncio
async def test_dag_event_route(fake_redis):
    dag_client = DummyDagManagerClient()
    app = create_app(
        redis_client=fake_redis, dag_client=dag_client, database_backend="memory"
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        event = format_event("test", "diff", {})
        resp = await client.post("/callbacks/dag-event", json=event)
        assert resp.status_code == 202
        assert resp.json()["ok"] is True
    await transport.aclose()


@pytest.mark.asyncio
async def test_dag_event_sentinel_weight(fake_redis):
    class DummyHub:
        def __init__(self):
            self.weights = []

        async def send_sentinel_weight(self, sid: str, weight: float) -> None:
            self.weights.append((sid, weight))

    hub = DummyHub()
    dag_client = DummyDagManagerClient()
    app = create_app(
        redis_client=fake_redis,
        ws_hub=hub,
        dag_client=dag_client,
        database_backend="memory",
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        metrics.reset_metrics()
        event = format_event(
            "qmtl.dagmanager",
            "sentinel_weight",
            {"sentinel_id": "v1", "weight": 0.7},
        )
        resp = await client.post("/callbacks/dag-event", json=event)
        assert resp.status_code == 202
        assert hub.weights == [("v1", 0.7)]
        assert metrics.gateway_sentinel_traffic_ratio._vals["v1"] == 0.7

        # Re-sending the same weight should not trigger another call
        resp = await client.post("/callbacks/dag-event", json=event)
        assert resp.status_code == 202
        assert hub.weights == [("v1", 0.7)]

        # Sending a different weight should trigger an update
        event2 = format_event(
            "qmtl.dagmanager",
            "sentinel_weight",
            {"sentinel_id": "v1", "weight": 0.3},
        )
        resp = await client.post("/callbacks/dag-event", json=event2)
        assert resp.status_code == 202
        assert hub.weights == [("v1", 0.7), ("v1", 0.3)]
        assert metrics.gateway_sentinel_traffic_ratio._vals["v1"] == 0.3
    await transport.aclose()


@pytest.mark.asyncio
async def test_dag_event_sentinel_weight_metric(fake_redis):
    class DummyHub:
        def __init__(self):
            self.weights = []

        async def send_sentinel_weight(self, sid: str, weight: float) -> None:
            self.weights.append((sid, weight))

    metrics.reset_metrics()
    hub = DummyHub()
    dag_client = DummyDagManagerClient()
    app = create_app(
        redis_client=fake_redis,
        ws_hub=hub,
        dag_client=dag_client,
        database_backend="memory",
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        event = format_event(
            "qmtl.dagmanager",
            "sentinel_weight",
            {"sentinel_id": "v2", "weight": 0.5},
        )
        resp = await client.post("/callbacks/dag-event", json=event)
        assert resp.status_code == 202
        assert hub.weights == [("v2", 0.5)]
        assert (
            metrics.gateway_sentinel_traffic_ratio.labels(sentinel_id="v2")._value.get() == 0.5
        )
    await transport.aclose()


@pytest.mark.asyncio
async def test_dag_event_sentinel_weight_invalid(fake_redis):
    class DummyHub:
        def __init__(self):
            self.weights = []

        async def send_sentinel_weight(self, sid: str, weight: float) -> None:
            self.weights.append((sid, weight))

    metrics.reset_metrics()
    hub = DummyHub()
    dag_client = DummyDagManagerClient()
    app = create_app(
        redis_client=fake_redis,
        ws_hub=hub,
        dag_client=dag_client,
        database_backend="memory",
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        event = format_event(
            "qmtl.dagmanager",
            "sentinel_weight",
            {"sentinel_id": "v3", "weight": 1.2},
        )
        resp = await client.post("/callbacks/dag-event", json=event)
        assert resp.status_code == 202
        # Invalid weights should be ignored entirely
        assert hub.weights == []
        assert "v3" not in metrics.gateway_sentinel_traffic_ratio._vals
    await transport.aclose()
