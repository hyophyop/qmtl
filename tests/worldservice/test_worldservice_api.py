import httpx
import pytest

from qmtl.worldservice.api import create_app
from qmtl.worldservice.controlbus_producer import ControlBusProducer


class DummyBus(ControlBusProducer):
    def __init__(self):
        self.events: list[tuple[str, str, int | None, object]] = []

    async def publish_policy_update(self, world_id: str, strategies: list[str], *, version: int = 1) -> None:  # type: ignore[override]
        self.events.append(("policy", world_id, version, list(strategies)))

    async def publish_activation_update(self, world_id: str, payload: dict, *, version: int = 1) -> None:  # type: ignore[override]
        self.events.append(("activation", world_id, version, payload))


@pytest.mark.asyncio
async def test_world_crud_policy_apply_and_events():
    bus = DummyBus()
    app = create_app(bus=bus)
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            # Create world
            await client.post("/worlds", json={"id": "w1", "name": "World"})
            r = await client.get("/worlds")
            assert r.json() == [{"id": "w1", "name": "World"}]

            # Add policy and set default
            await client.post("/worlds/w1/policies", json={"policy": {"top_k": {"metric": "m", "k": 1}}})
            await client.post("/worlds/w1/set-default", json={"version": 1})

            # Apply metrics
            payload = {"metrics": {"s1": {"m": 1.0}, "s2": {"m": 0.5}}}
            r = await client.post("/worlds/w1/apply", json=payload)
            assert r.json() == {"active": ["s1"]}

            # Activation update
            r = await client.put("/worlds/w1/activation", json={"side": "long", "active": True})
            assert r.json()["version"] == 1

            # Audit log contains entries
            audit = await client.get("/worlds/w1/audit")
            assert any(e["event"] == "activation_updated" for e in audit.json())

    assert ("policy", "w1", 1, ["s1"]) in bus.events
    assert ("activation", "w1", 1, {"side": "long", "active": True}) in bus.events
