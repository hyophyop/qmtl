import httpx
import pytest

from qmtl.worldservice.api import create_app
from qmtl.worldservice.controlbus_producer import ControlBusProducer


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
