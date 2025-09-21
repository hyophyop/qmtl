import httpx
import pytest

from qmtl.worldservice.api import create_app
from qmtl.worldservice.controlbus_producer import ControlBusProducer
from qmtl.worldservice.storage import Storage


class DummyBus(ControlBusProducer):
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []

    async def publish_policy_update(
        self,
        world_id: str,
        policy_version: int,
        checksum: str,
        status: str,
        ts: str,
        *,
        version: int = 1,
    ) -> None:  # type: ignore[override]
        self.events.append(
            (
                "policy",
                world_id,
                {
                    "policy_version": policy_version,
                    "checksum": checksum,
                    "status": status,
                    "ts": ts,
                    "version": version,
                },
            )
        )

    async def publish_activation_update(
        self,
        world_id: str,
        *,
        etag: str,
        run_id: str,
        ts: str,
        state_hash: str,
        payload: dict | None = None,
        version: int = 1,
    ) -> None:  # type: ignore[override]
        self.events.append(
            (
                "activation",
                world_id,
                {
                    **(payload or {}),
                    "etag": etag,
                    "run_id": run_id,
                    "ts": ts,
                    "state_hash": state_hash,
                    "version": version,
                },
            )
        )


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

            # Decision envelope
            d = await client.get("/worlds/w1/decide")
            assert d.json()["ttl"] == "300s"

            # Activation update
            payload_act = {"strategy_id": "s1", "side": "long", "active": True, "weight": 1.0}
            r = await client.put("/worlds/w1/activation", json=payload_act)
            assert r.json()["active"] is True

            # Read back activation
            r = await client.get("/worlds/w1/activation", params={"strategy_id": "s1", "side": "long"})
            assert r.json()["active"] is True

            # Audit log contains entries
            audit = await client.get("/worlds/w1/audit")
            assert any(e["event"] == "activation_updated" for e in audit.json())

    policy_evt = next(e for e in bus.events if e[0] == "policy")
    assert policy_evt[1] == "w1"
    assert policy_evt[2]["policy_version"] == 1

    activation_evt = next(e for e in bus.events if e[0] == "activation")
    assert activation_evt[1] == "w1"
    assert activation_evt[2]["side"] == "long"
    assert activation_evt[2]["active"] is True


@pytest.mark.asyncio
async def test_world_nodes_execution_domains_and_legacy_migration():
    storage = Storage()
    storage.world_nodes.setdefault("w1", {})["legacy"] = {
        "status": "paused",
        "annotations": {"source": "legacy"},
    }

    app = create_app(storage=storage)
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "w1", "name": "World"})

            live_payload = {
                "status": "valid",
                "annotations": {"note": "live"},
            }
            node_id = "blake3:node-live"
            resp = await client.put(f"/worlds/w1/nodes/{node_id}", json=live_payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["execution_domain"] == "live"
            assert data["status"] == "valid"

            backtest_payload = {
                "status": "validating",
                "execution_domain": "backtest",
                "last_eval_key": "blake3:eval",
            }
            resp = await client.put(f"/worlds/w1/nodes/{node_id}", json=backtest_payload)
            assert resp.status_code == 200
            backtest_data = resp.json()
            assert backtest_data["execution_domain"] == "backtest"
            assert backtest_data["last_eval_key"] == "blake3:eval"

            resp = await client.get(f"/worlds/w1/nodes/{node_id}")
            assert resp.status_code == 200
            assert resp.json()["execution_domain"] == "live"

            resp = await client.get(
                f"/worlds/w1/nodes/{node_id}", params={"execution_domain": "backtest"}
            )
            assert resp.status_code == 200
            assert resp.json()["execution_domain"] == "backtest"

            resp = await client.get("/worlds/w1/nodes")
            assert resp.status_code == 200
            default_nodes = resp.json()
            assert all(n["execution_domain"] == "live" for n in default_nodes)
            assert {n["node_id"] for n in default_nodes} == {node_id, "legacy"}

            resp = await client.get("/worlds/w1/nodes", params={"execution_domain": "all"})
            assert resp.status_code == 200
            nodes = resp.json()
            assert {n["execution_domain"] for n in nodes} == {"live", "backtest"}
            assert any(n["node_id"] == "legacy" for n in nodes)

            legacy_resp = await client.get("/worlds/w1/nodes/legacy")
            assert legacy_resp.status_code == 200
            legacy = legacy_resp.json()
            assert legacy["execution_domain"] == "live"
            assert legacy["status"] == "paused"
            assert legacy["annotations"] == {"source": "legacy"}

            delete_resp = await client.delete(
                f"/worlds/w1/nodes/{node_id}", params={"execution_domain": "backtest"}
            )
            assert delete_resp.status_code == 204

            resp = await client.get("/worlds/w1/nodes", params={"execution_domain": "all"})
            remaining = [n for n in resp.json() if n["node_id"] == node_id]
            assert {n["execution_domain"] for n in remaining} == {"live"}

            bad_resp = await client.get("/worlds/w1/nodes", params={"execution_domain": "invalid"})
            assert bad_resp.status_code == 400
