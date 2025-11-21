from pathlib import Path
from typing import Any

import asyncio

import httpx
import pytest

from qmtl.services.worldservice.api import StorageHandle, create_app
from qmtl.services.worldservice.controlbus_producer import ControlBusProducer
from qmtl.services.worldservice.config import WorldServiceServerConfig
from qmtl.services.worldservice.schemas import AllocationUpsertRequest
from qmtl.services.worldservice.services import WorldService
from qmtl.services.worldservice.storage import PersistentStorage, Storage


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


    async def publish_rebalancing_plan(  # type: ignore[override]
        self,
        world_id: str,
        plan: dict,
        *,
        version: int = 1,
        schema_version: int | None = None,
        alpha_metrics: dict | None = None,
        rebalance_intent: dict | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "plan": plan,
            "version": version,
        }
        if schema_version is not None:
            payload["schema_version"] = schema_version
        if alpha_metrics is not None:
            payload["alpha_metrics"] = alpha_metrics
        if rebalance_intent is not None:
            payload["rebalance_intent"] = rebalance_intent
        self.events.append(("rebalancing_planned", world_id, payload))


class DummyExecutor:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def execute(self, payload: dict) -> dict:
        self.calls.append(dict(payload))
        return {"ok": True}


@pytest.mark.asyncio
async def test_world_crud_policy_apply_and_events():
    bus = DummyBus()
    app = create_app(bus=bus, storage=Storage())
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
    app = create_app(bus=bus, storage=Storage())
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
async def test_rebalancing_apply_scaling_mode_success():
    app = create_app(storage=Storage())

    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            payload = {
                "total_equity": 1_000.0,
                "world_alloc_before": {"w1": 1.0},
                "world_alloc_after": {"w1": 1.0},
                "positions": [
                    {
                        "world_id": "w1",
                        "strategy_id": "s1",
                        "symbol": "BTC",
                        "qty": 1.0,
                        "mark": 100.0,
                        "venue": "spot",
                    }
                ],
                "mode": "scaling",
            }

            resp = await client.post("/rebalancing/apply", json=payload)
            assert resp.status_code == 200

            body = resp.json()
            assert set(body) >= {"schema_version", "per_world", "global_deltas"}
            assert body["schema_version"] == 1
            assert "w1" in body["per_world"]

            plan = body["per_world"]["w1"]
            assert plan["world_id"] == "w1"
            assert isinstance(plan["deltas"], list)
            assert plan["scale_world"] == pytest.approx(1.0)
            assert "s1" in plan["scale_by_strategy"]

            assert body["global_deltas"] == []
            assert "overlay_deltas" not in body or body["overlay_deltas"] is None
            assert body.get("alpha_metrics") is None


@pytest.mark.asyncio
async def test_rebalancing_plan_downgrades_when_v2_disabled():
    app = create_app(storage=Storage())

    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            payload = {
                "schema_version": 2,
                "total_equity": 1_000.0,
                "world_alloc_before": {"w1": 1.0},
                "world_alloc_after": {"w1": 1.0},
                "positions": [
                    {
                        "world_id": "w1",
                        "strategy_id": "s1",
                        "symbol": "BTC",
                        "qty": 1.0,
                        "mark": 100.0,
                        "venue": "spot",
                    }
                ],
            }

            resp = await client.post("/rebalancing/plan", json=payload)
            assert resp.status_code == 200
            body = resp.json()
            assert body["schema_version"] == 1
            assert body.get("alpha_metrics") is None


@pytest.mark.asyncio
async def test_rebalancing_plan_serves_v2_when_enabled():
    app = create_app(storage=Storage(), compat_rebalance_v2=True)

    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            payload = {
                "schema_version": 2,
                "total_equity": 1_000.0,
                "world_alloc_before": {"w1": 1.0},
                "world_alloc_after": {"w1": 1.0},
                "positions": [
                    {
                        "world_id": "w1",
                        "strategy_id": "s1",
                        "symbol": "BTC",
                        "qty": 1.0,
                        "mark": 100.0,
                        "venue": "spot",
                    }
                ],
            }

            resp = await client.post("/rebalancing/plan", json=payload)
            assert resp.status_code == 200
            body = resp.json()
            assert body["schema_version"] == 2
            alpha_metrics = body["alpha_metrics"]
            assert "per_world" in alpha_metrics
            assert "per_strategy" in alpha_metrics
            assert alpha_metrics["per_world"]["w1"]["alpha_performance.sharpe"] == 0.0
            assert "s1" in alpha_metrics["per_strategy"]
            assert alpha_metrics["per_strategy"]["s1"]["w1"]["alpha_performance.sharpe"] == 0.0


@pytest.mark.asyncio
async def test_rebalancing_plan_includes_intent_metadata_when_v2_enabled():
    app = create_app(storage=Storage(), compat_rebalance_v2=True)

    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            payload = {
                "schema_version": 2,
                "total_equity": 1_000.0,
                "world_alloc_before": {"w1": 1.0},
                "world_alloc_after": {"w1": 1.0},
                "positions": [
                    {
                        "world_id": "w1",
                        "strategy_id": "s1",
                        "symbol": "BTC",
                        "qty": 1.0,
                        "mark": 100.0,
                        "venue": "spot",
                    }
                ],
                "rebalance_intent": {
                    "meta": {
                        "ticket": "1514",
                        "reason": "smoke-test",
                    }
                },
            }

            resp = await client.post("/rebalancing/plan", json=payload)
            assert resp.status_code == 200
            body = resp.json()
            assert body["schema_version"] == 2
            assert body["rebalance_intent"]["meta"]["ticket"] == "1514"
            assert body["rebalance_intent"]["meta"]["reason"] == "smoke-test"


@pytest.mark.asyncio
async def test_rebalancing_plan_strips_intent_for_v1_clients():
    app = create_app(storage=Storage())

    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            payload = {
                "total_equity": 1_000.0,
                "world_alloc_before": {"w1": 1.0},
                "world_alloc_after": {"w1": 1.0},
                "positions": [
                    {
                        "world_id": "w1",
                        "strategy_id": "s1",
                        "symbol": "BTC",
                        "qty": 1.0,
                        "mark": 100.0,
                        "venue": "spot",
                    }
                ],
                "rebalance_intent": {"meta": {"ticket": "legacy-client"}},
            }

            resp = await client.post("/rebalancing/plan", json=payload)
            assert resp.status_code == 200
            body = resp.json()
            assert body["schema_version"] == 1
            assert "rebalance_intent" not in body


@pytest.mark.asyncio
async def test_rebalancing_apply_emits_controlbus_metadata_for_v2():
    bus = DummyBus()
    app = create_app(bus=bus, storage=Storage(), compat_rebalance_v2=True)

    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            payload = {
                "schema_version": 2,
                "total_equity": 1_000.0,
                "world_alloc_before": {"w1": 1.0},
                "world_alloc_after": {"w1": 1.0},
                "positions": [
                    {
                        "world_id": "w1",
                        "strategy_id": "s1",
                        "symbol": "BTC",
                        "qty": 1.0,
                        "mark": 100.0,
                        "venue": "spot",
                    }
                ],
                "rebalance_intent": {"meta": {"ticket": "cb-v2"}},
            }

            resp = await client.post("/rebalancing/apply", json=payload)
            assert resp.status_code == 200

    events = [evt for evt in bus.events if evt[0] == "rebalancing_planned"]
    assert events
    per_world_event = next(evt for evt in events if evt[1] == "w1")
    event_payload = per_world_event[2]
    assert event_payload["version"] == 2
    assert event_payload["schema_version"] == 2
    assert event_payload["alpha_metrics"]["per_world"]["w1"]["alpha_performance.sharpe"] == 0.0
    assert event_payload["rebalance_intent"]["meta"]["ticket"] == "cb-v2"


@pytest.mark.asyncio
async def test_rebalancing_apply_controlbus_v1_skips_optional_metadata():
    bus = DummyBus()
    app = create_app(bus=bus, storage=Storage())

    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            payload = {
                "total_equity": 1_000.0,
                "world_alloc_before": {"w1": 1.0},
                "world_alloc_after": {"w1": 1.0},
                "positions": [
                    {
                        "world_id": "w1",
                        "strategy_id": "s1",
                        "symbol": "BTC",
                        "qty": 1.0,
                        "mark": 100.0,
                        "venue": "spot",
                    }
                ],
                "rebalance_intent": {"meta": {"ticket": "legacy"}},
            }

            resp = await client.post("/rebalancing/apply", json=payload)
            assert resp.status_code == 200

    events = [evt for evt in bus.events if evt[0] == "rebalancing_planned"]
    assert events
    per_world_event = next(evt for evt in events if evt[1] == "w1")
    event_payload = per_world_event[2]
    assert event_payload["version"] == 1
    assert event_payload.get("schema_version") == 1
    assert "alpha_metrics" not in event_payload
    assert "rebalance_intent" not in event_payload


@pytest.mark.asyncio
async def test_rebalancing_plan_requires_v2_when_alpha_metrics_required():
    app = create_app(
        storage=Storage(),
        compat_rebalance_v2=True,
        alpha_metrics_required=True,
    )

    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            base_payload = {
                "total_equity": 1_000.0,
                "world_alloc_before": {"w1": 1.0},
                "world_alloc_after": {"w1": 1.0},
                "positions": [
                    {
                        "world_id": "w1",
                        "strategy_id": "s1",
                        "symbol": "BTC",
                        "qty": 1.0,
                        "mark": 100.0,
                        "venue": "spot",
                    }
                ],
            }

            resp = await client.post("/rebalancing/plan", json=base_payload)
            assert resp.status_code == 400
            assert "schema_version>=2" in resp.json()["detail"]

            payload_v2 = dict(base_payload, schema_version=2)
            ok = await client.post("/rebalancing/plan", json=payload_v2)
            assert ok.status_code == 200
            assert ok.json()["schema_version"] == 2


@pytest.mark.asyncio
async def test_rebalancing_apply_overlay_mode_rejected():
    app = create_app(storage=Storage())

    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            payload = {
                "total_equity": 1_000.0,
                "world_alloc_before": {"w1": 1.0},
                "world_alloc_after": {"w1": 1.0},
                "positions": [
                    {
                        "world_id": "w1",
                        "strategy_id": "s1",
                        "symbol": "BTC",
                        "qty": 1.0,
                        "mark": 100.0,
                        "venue": "spot",
                    }
                ],
                "mode": "overlay",
            }

            resp = await client.post("/rebalancing/apply", json=payload)
            assert resp.status_code == 501
            assert resp.json() == {
                "detail": "Overlay mode is not implemented yet. Use mode='scaling'."
            }


@pytest.mark.asyncio
async def test_allocations_endpoint_execute_and_idempotency():
    bus = DummyBus()
    executor = DummyExecutor()
    app = create_app(bus=bus, storage=Storage(), rebalance_executor=executor)

    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "w1"})
            await client.post("/worlds", json={"id": "w2"})

            payload = {
                "run_id": "alloc-run-1",
                "total_equity": 1000.0,
                "world_allocations": {"w1": 0.6, "w2": 0.4},
                "positions": [
                    {
                        "world_id": "w1",
                        "strategy_id": "s1",
                        "symbol": "BTC",
                        "qty": 1.0,
                        "mark": 100.0,
                    },
                    {
                        "world_id": "w1",
                        "strategy_id": "s2",
                        "symbol": "ETH",
                        "qty": 2.0,
                        "mark": 50.0,
                    },
                    {
                        "world_id": "w2",
                        "strategy_id": "s3",
                        "symbol": "BTC",
                        "qty": 0.5,
                        "mark": 100.0,
                    },
                ],
                "strategy_alloc_after_total": {
                    "w1": {"s1": 0.36, "s2": 0.24},
                    "w2": {"s3": 0.4},
                },
                "execute": True,
            }

            resp = await client.post("/allocations", json=payload)
            assert resp.status_code == 200
            body = resp.json()
            assert body["run_id"] == "alloc-run-1"
            assert body["executed"] is True
            assert executor.calls and executor.calls[0]["world_alloc_after"]["w1"] == 0.6

            conflict = dict(payload)
            conflict["world_allocations"] = {"w1": 0.7, "w2": 0.3}
            r_conflict = await client.post("/allocations", json=conflict)
            assert r_conflict.status_code == 409

            repeat = dict(payload)
            repeat["execute"] = False
            r_repeat = await client.post("/allocations", json=repeat)
            assert r_repeat.status_code == 200
            assert r_repeat.json()["executed"] is True
            assert len(executor.calls) == 1

            followup = {
                "run_id": "alloc-run-2",
                "total_equity": 1000.0,
                "world_allocations": {"w1": 0.7, "w2": 0.3},
                "positions": payload["positions"],
            }
            r_follow = await client.post("/allocations", json=followup)
            assert r_follow.status_code == 200
            follow_body = r_follow.json()
            scale = follow_body["per_world"]["w1"]["scale_by_strategy"]
            assert scale["s1"] == pytest.approx(scale["s2"], rel=1e-3)
            assert scale["s1"] == pytest.approx(0.7 / 0.6, rel=1e-3)


@pytest.mark.asyncio
async def test_allocation_lock_prevents_overlap():
    service = WorldService(store=Storage())

    base_payload = {
        "total_equity": 100.0,
        "world_allocations": {"w1": 0.5},
        "positions": [
            {
                "world_id": "w1",
                "strategy_id": "s1",
                "symbol": "BTC",
                "qty": 1.0,
                "mark": 100.0,
            }
        ],
        "strategy_alloc_after_total": {"w1": {"s1": 0.5}},
    }

    payload1 = AllocationUpsertRequest(run_id="lock-1", **base_payload)
    payload2 = AllocationUpsertRequest(
        run_id="lock-2",
        total_equity=100.0,
        world_allocations={"w1": 0.6},
        positions=base_payload["positions"],
    )

    event_ready = asyncio.Event()
    release = asyncio.Event()

    original_set = service.store.set_world_allocations

    async def blocking_set(*args, **kwargs):
        event_ready.set()
        await release.wait()
        return await original_set(*args, **kwargs)

    service.store.set_world_allocations = blocking_set  # type: ignore[assignment]

    task1 = asyncio.create_task(service.upsert_allocations(payload1))
    await event_ready.wait()
    task2 = asyncio.create_task(service.upsert_allocations(payload2))
    await asyncio.sleep(0.05)
    assert not task2.done()
    release.set()
    result1 = await task1
    result2 = await task2
    assert result1.run_id == "lock-1"
    assert result2.run_id == "lock-2"


@pytest.mark.asyncio
async def test_decide_effective_mode_canonicalised():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "mode-test"})

            resp = await client.get("/worlds/mode-test/decide")
            assert resp.status_code == 200
            body = resp.json()
            assert body["effective_mode"] == "validate"

            await client.post(
                "/worlds/mode-test/decisions", json={"strategies": ["s-live"]}
            )

            live_resp = await client.get("/worlds/mode-test/decide")
            assert live_resp.status_code == 200
            live_body = live_resp.json()
            assert live_body["effective_mode"] == "live"


@pytest.mark.asyncio
async def test_post_decisions_normalizes_payload_and_validates():
    bus = DummyBus()
    app = create_app(bus=bus, storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "w3"})

            resp = await client.post(
                "/worlds/w3/decisions",
                json={"strategies": ["alpha", "alpha", "beta"]},
            )
            assert resp.status_code == 200
            assert resp.json() == {"strategies": ["alpha", "beta"]}

            stored = await app.state.world_service.store.get_decisions("w3")
            assert stored == ["alpha", "beta"]

            invalid = await client.post(
                "/worlds/w3/decisions",
                json={"strategies": ["alpha", " "]},
            )
            assert invalid.status_code == 422


@pytest.mark.asyncio
async def test_history_metadata_in_decision_envelope():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wx"})
            history_payload = {
                "strategy_id": "strat-1",
                "node_id": "node-x",
                "interval": 60,
                "rows": 5,
                "coverage_bounds": [10, 70],
                "dataset_fingerprint": "fp-history",
                "as_of": "2025-03-15T12:00:00Z",
                "execution_domain": "live",
                "conformance_flags": {"gap": 1},
                "conformance_warnings": ["late"],
                "artifact": {
                    "dataset_fingerprint": "fp-history",
                    "as_of": "2025-03-15T12:00:00Z",
                    "rows": 5,
                    "uri": "local://artifact",
                },
            }
            resp = await client.post(
                "/worlds/wx/history",
                json=history_payload,
            )
            assert resp.status_code == 204

            history_resp = await client.get("/worlds/wx/history")
            history_body = history_resp.json()
            assert history_body["latest"]["dataset_fingerprint"] == "fp-history"
            assert history_body["entries"][0]["node_id"] == "node-x"
            assert history_body["entries"][0]["strategy_id"] == "strat-1"

            decide = await client.get("/worlds/wx/decide")
            decide_body = decide.json()
            assert decide_body["dataset_fingerprint"] == "fp-history"
            assert decide_body["as_of"] == "2025-03-15T12:00:00Z"
            assert decide_body["coverage_bounds"] == [10, 70]
            assert decide_body["conformance_flags"] == {"gap": 1}
            assert decide_body["conformance_warnings"] == ["late"]
            assert decide_body["rows"] == 5
            assert decide_body["artifact"]["uri"] == "local://artifact"


@pytest.mark.asyncio
async def test_edge_overrides_upsert_and_reason_preservation():
    app = create_app(storage=Storage())
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
            assert data["execution_domain"] == "backtest"
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
            # Default domain is backtest unless explicitly requested
            assert resp.json()["execution_domain"] == "backtest"

            resp = await client.get(
                f"/worlds/w1/nodes/{node_id}", params={"execution_domain": "backtest"}
            )
            assert resp.status_code == 200
            assert resp.json()["execution_domain"] == "backtest"

            resp = await client.get("/worlds/w1/nodes")
            assert resp.status_code == 200
            default_nodes = resp.json()
            assert all(n["execution_domain"] == "backtest" for n in default_nodes)
            assert {n["node_id"] for n in default_nodes} == {node_id, "legacy"}

            resp = await client.get("/worlds/w1/nodes", params={"execution_domain": "all"})
            assert resp.status_code == 200
            nodes = resp.json()
            assert {n["execution_domain"] for n in nodes} == {"backtest"}
            assert any(n["node_id"] == "legacy" for n in nodes)

            legacy_resp = await client.get("/worlds/w1/nodes/legacy")
            assert legacy_resp.status_code == 200
            legacy = legacy_resp.json()
            assert legacy["execution_domain"] == "backtest"
            assert legacy["status"] == "paused"
            assert legacy["annotations"] == {"source": "legacy"}

            delete_resp = await client.delete(
                f"/worlds/w1/nodes/{node_id}", params={"execution_domain": "backtest"}
            )
            assert delete_resp.status_code == 204

            resp = await client.get("/worlds/w1/nodes", params={"execution_domain": "all"})
            remaining = [n for n in resp.json() if n["node_id"] == node_id]
            assert remaining == []

            audit_resp = await client.get("/worlds/w1/audit")
            assert audit_resp.status_code == 200
        migrations = [
            entry
            for entry in audit_resp.json()
            if entry["event"] == "world_node_bucket_normalized" and entry.get("node_id") == "legacy"
        ]
        assert migrations
        legacy_event = migrations[-1]
        assert legacy_event.get("domains") == ["backtest"]
        assert legacy_event.get("source") == "legacy-single"

        bad_resp = await client.get("/worlds/w1/nodes", params={"execution_domain": "invalid"})
        assert bad_resp.status_code == 400


@pytest.mark.asyncio
async def test_persistent_storage_survives_restart(tmp_path, fake_redis):
    db_path = tmp_path / "worlds_api.db"

    def _factory_builder():
        async def _factory() -> StorageHandle:
            storage = await PersistentStorage.create(
                db_dsn=str(db_path),
                redis_client=fake_redis,
            )

            async def _shutdown() -> None:
                await storage.close()

            return StorageHandle(storage=storage, shutdown=_shutdown)

        return _factory

    db_path.parent.mkdir(parents=True, exist_ok=True)
    app = create_app(storage_factory=_factory_builder())
    async with app.router.lifespan_context(app):
        async with httpx.ASGITransport(app=app) as asgi:
            async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
                resp = await client.post("/worlds", json={"id": "persist", "name": "Persistent"})
                assert resp.status_code == 201
                policy_resp = await client.post(
                    "/worlds/persist/policies",
                    json={"policy": {"top_k": {"metric": "m", "k": 1}}},
                )
                assert policy_resp.status_code == 200
                default_resp = await client.post("/worlds/persist/set-default", json={"version": 1})
                assert default_resp.status_code == 200
                decisions_resp = await client.post(
                    "/worlds/persist/decisions",
                    json={"strategies": ["strategy-1"]},
                )
                assert decisions_resp.status_code == 200
                bindings_post = await client.post(
                    "/worlds/persist/bindings",
                    json={"strategies": ["strategy-1"]},
                )
                assert bindings_post.status_code == 200
                activation_resp = await client.put(
                    "/worlds/persist/activation",
                    json={
                        "strategy_id": "strategy-1",
                        "side": "long",
                        "active": True,
                        "weight": 0.75,
                    },
                )
                assert activation_resp.status_code == 200
                initial_lookup = await client.get("/worlds/persist")
                assert initial_lookup.status_code == 200
                worlds = await app.state.storage.list_worlds()
                assert any(w["id"] == "persist" for w in worlds)

        driver = getattr(app.state.storage, "_driver", None)
        sqlite_conn = getattr(driver, "_conn", None)
        conn_path = Path(getattr(sqlite_conn, "database", str(db_path)))

    assert conn_path.exists(), conn_path
    storage_inspect = await PersistentStorage.create(
        db_dsn=str(db_path),
        redis_client=fake_redis,
    )
    try:
        persisted = await storage_inspect.get_world("persist")
        assert persisted is not None
    finally:
        await storage_inspect.close()

    app_restart = create_app(storage_factory=_factory_builder())
    async with app_restart.router.lifespan_context(app_restart):
        async with httpx.ASGITransport(app=app_restart) as asgi:
            async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
                world_resp = await client.get("/worlds/persist")
                assert world_resp.status_code == 200
                assert world_resp.json()["name"] == "Persistent"

                policy_resp = await client.get("/worlds/persist/policies/1")
                assert policy_resp.status_code == 200
                assert policy_resp.json()["top_k"] == {"metric": "m", "k": 1}

                decide_resp = await client.get("/worlds/persist/decide")
                assert decide_resp.status_code == 200
                assert decide_resp.json()["policy_version"] == 1

                activation_resp = await client.get(
                    "/worlds/persist/activation",
                    params={"strategy_id": "strategy-1", "side": "long"},
                )
                assert activation_resp.status_code == 200
                activation = activation_resp.json()
                assert activation["active"] is True
                assert activation["weight"] == 0.75
                assert activation["strategy_id"] == "strategy-1"

                audit_resp = await client.get("/worlds/persist/audit")
                assert audit_resp.status_code == 200
                audit_events = audit_resp.json()
                assert any(event["event"] == "activation_updated" for event in audit_events)

                bindings_resp = await client.get("/worlds/persist/bindings")
                assert bindings_resp.status_code == 200
                assert bindings_resp.json() == {"strategies": ["strategy-1"]}

                decisions = await app_restart.state.world_service.store.get_decisions("persist")
                assert decisions == ["strategy-1"]


def test_create_app_without_storage_requires_config():
    with pytest.raises(RuntimeError, match="configuration file not found"):
        create_app()


@pytest.mark.asyncio
async def test_create_app_without_redis_uses_in_memory_storage():
    config = WorldServiceServerConfig(dsn="sqlite+aiosqlite:///worlds.db")

    app = create_app(config=config)

    assert isinstance(app.state.storage, Storage)
    assert not isinstance(app.state.storage, PersistentStorage)
    assert app.state.worldservice_config == config

    async with app.router.lifespan_context(app):
        assert isinstance(app.state.storage, Storage)
        assert app.state.storage is app.state.world_service.store


def test_create_app_loads_config_from_explicit_path(tmp_path):
    config_path = tmp_path / "worldservice.yml"
    config_path.write_text(
        """
worldservice:
  server:
    dsn: sqlite+aiosqlite:///worlds.db
""".strip()
    )

    app = create_app(config_path=config_path)

    assert isinstance(app.state.storage, Storage)
    assert app.state.worldservice_config is not None
    assert app.state.worldservice_config.dsn == "sqlite+aiosqlite:///worlds.db"
    assert app.state.worldservice_config.redis is None
