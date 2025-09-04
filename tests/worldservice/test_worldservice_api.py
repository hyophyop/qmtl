import httpx
import pytest

from qmtl.worldservice.api import create_app, ApplyRequest
from qmtl.worldservice.controlbus_producer import ControlBusProducer


class DummyBus(ControlBusProducer):
    def __init__(self):
        self.published: list[tuple[str, list[str]]] = []

    async def publish_policy_update(self, world_id: str, strategies: list[str]) -> None:  # type: ignore[override]
        self.published.append((world_id, strategies))


@pytest.mark.asyncio
async def test_apply_endpoint_broadcasts():
    bus = DummyBus()
    app = create_app(bus=bus)
    payload = ApplyRequest(
        policy={"top_k": {"metric": "sharpe", "k": 1}},
        metrics={"s1": {"sharpe": 1.0}, "s2": {"sharpe": 0.5}},
    )
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            r = await client.post("/worlds/w1/apply", json=payload.model_dump())
            assert r.json() == {"active": ["s1"]}
            r2 = await client.get("/worlds/w1/apply")
            assert r2.json() == {"active": ["s1"]}
    assert bus.published == [("w1", ["s1"])]
