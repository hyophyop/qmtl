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
        requires_ack: bool = False,
        sequence: int | None = None,
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
                    "requires_ack": requires_ack,
                    "sequence": sequence,
                },
            )
        )


@pytest.mark.asyncio
async def test_world_crud_policy_apply_and_events():
    bus = DummyBus()
    app = create_app(bus=bus)
    gating_policy = {
        "dataset_fingerprint": "ohlcv:ASOF=2025-09-30T23:59:59Z",
        "share_policy": "feature-artifacts-only",
        "snapshot": {"strategy_plane": "cow", "feature_plane": "readonly"},
        "edges": {
            "pre_promotion": {"disable_edges_to": "live"},
            "post_promotion": {"enable_edges_to": "live"},
        },
        "observability": {"slo": {"cross_context_cache_hit": 0}},
    }

    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            # Create world
            await client.post("/worlds", json={"id": "w1", "name": "World"})
            r = await client.get("/worlds")
            assert r.json() == [{"id": "w1", "name": "World"}]

            overrides_resp = await client.get("/worlds/w1/edges/overrides")
            assert overrides_resp.status_code == 200
            overrides = overrides_resp.json()
            assert overrides
            default_edge = next(
                o
                for o in overrides
                if o["src_node_id"] == "domain:backtest" and o["dst_node_id"] == "domain:live"
            )
            assert default_edge["active"] is False
            assert default_edge["reason"] == "auto:cross-domain-block"

            # Add policy and set default
            await client.post("/worlds/w1/policies", json={"policy": {"top_k": {"metric": "m", "k": 1}}})
            await client.post("/worlds/w1/set-default", json={"version": 1})

            # Seed activation so freeze/unfreeze emits events
            payload_act = {"strategy_id": "s1", "side": "long", "active": True, "weight": 1.0}
            r = await client.put("/worlds/w1/activation", json=payload_act)
            assert r.json()["active"] is True
            bus.events.clear()

            # Apply metrics via 2-phase apply
            run_id = "run-1"
            payload = {
                "run_id": run_id,
                "metrics": {"s1": {"m": 1.0}, "s2": {"m": 0.5}},
                "gating_policy": gating_policy,
            }
            r = await client.post("/worlds/w1/apply", json=payload)
            body = r.json()
            assert body == {"ok": True, "run_id": run_id, "active": ["s1"], "phase": "completed"}

            overrides_after = await client.get("/worlds/w1/edges/overrides")
            assert overrides_after.status_code == 200
            edge_after = next(
                o
                for o in overrides_after.json()
                if o["src_node_id"] == "domain:backtest" and o["dst_node_id"] == "domain:live"
            )
            assert edge_after["active"] is True
            assert edge_after["reason"] == f"post_promotion_enable:{run_id}"

            # Idempotent acknowledgement for same run
            r = await client.post("/worlds/w1/apply", json=payload)
            assert r.json()["phase"] == "completed"

            # Decision envelope
            d = await client.get("/worlds/w1/decide")
            assert d.json()["ttl"] == "300s"

            # Read back activation
            r = await client.get("/worlds/w1/activation", params={"strategy_id": "s1", "side": "long"})
            assert r.json()["active"] is True

            # Audit log contains entries
            audit = await client.get("/worlds/w1/audit")
            stages = [e for e in audit.json() if e["event"] == "apply_stage"]
            assert [s["stage"] for s in stages] == ["requested", "freeze", "switch", "unfreeze", "completed"]

    policy_evt = next(e for e in bus.events if e[0] == "policy")
    assert policy_evt[1] == "w1"
    assert policy_evt[2]["policy_version"] == 1

    activation_events = [e for e in bus.events if e[0] == "activation"]
    assert len(activation_events) >= 2
    freeze_evt = activation_events[0][2]
    unfreeze_evt = activation_events[1][2]
    assert freeze_evt["phase"] == "freeze"
    assert freeze_evt["freeze"] is True
    assert freeze_evt["requires_ack"] is True
    assert freeze_evt["sequence"] == 1
    assert unfreeze_evt["phase"] == "unfreeze"
    assert unfreeze_evt["freeze"] is False
    assert unfreeze_evt["requires_ack"] is True
    final_payload = activation_events[-1][2]
    assert final_payload.get("side") == "long"
    assert final_payload.get("active") is True


@pytest.mark.asyncio
async def test_apply_rejects_invalid_gating_policy():
    bus = DummyBus()
    app = create_app(bus=bus)
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "w2"})
            await client.post("/worlds/w2/policies", json={"policy": {"top_k": {"metric": "m", "k": 1}}})
            await client.post("/worlds/w2/set-default", json={"version": 1})

            payload = {
                "run_id": "run-err",
                "metrics": {"s1": {"m": 1.0}},
                "gating_policy": {
                    "dataset_fingerprint": "ohlcv:ASOF=2025-09-30T23:59:59Z",
                    "share_policy": "invalid",
                    "snapshot": {"strategy_plane": "cow", "feature_plane": "readonly"},
                    "edges": {
                        "pre_promotion": {"disable_edges_to": "live"},
                        "post_promotion": {"enable_edges_to": "live"},
                    },
                    "observability": {"slo": {"cross_context_cache_hit": 0}},
                },
            }

            r = await client.post("/worlds/w2/apply", json=payload)
            assert r.status_code == 422


@pytest.mark.asyncio
async def test_edge_overrides_upsert_and_reason_preservation():
    app = create_app()
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "edge-world", "name": "Edges"})

            resp = await client.get("/worlds/edge-world/edges/overrides")
            assert resp.status_code == 200
            overrides = resp.json()
            assert overrides
            base = next(
                o
                for o in overrides
                if o["src_node_id"] == "domain:backtest" and o["dst_node_id"] == "domain:live"
            )
            assert base["active"] is False
            assert base["reason"] == "auto:cross-domain-block"
            assert base["updated_at"]

            put_resp = await client.put(
                "/worlds/edge-world/edges/domain:backtest/domain:live",
                json={"active": True, "reason": "manual enable"},
            )
            assert put_resp.status_code == 200
            override = put_resp.json()
            assert override["active"] is True
            assert override["reason"] == "manual enable"

            put_again = await client.put(
                "/worlds/edge-world/edges/domain:backtest/domain:live",
                json={"active": False},
            )
            assert put_again.status_code == 200
            updated = put_again.json()
            assert updated["active"] is False
            assert updated["reason"] == "manual enable"

            latest = await client.get("/worlds/edge-world/edges/overrides")
            assert latest.status_code == 200
            latest_edge = next(
                o
                for o in latest.json()
                if o["src_node_id"] == "domain:backtest" and o["dst_node_id"] == "domain:live"
            )
            assert latest_edge["active"] is False
            assert latest_edge["reason"] == "manual enable"


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
