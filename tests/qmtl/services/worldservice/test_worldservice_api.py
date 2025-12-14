from pathlib import Path
from typing import Any

import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from qmtl.services.worldservice import api as worldservice_api
from qmtl.foundation.config import (
    DeploymentProfile,
    RiskHubBlobStoreConfig,
    RiskHubConfig,
)
from qmtl.services.worldservice.api import StorageHandle, create_app
from qmtl.services.worldservice.controlbus_producer import ControlBusProducer
from qmtl.services.worldservice.config import WorldServiceServerConfig
from qmtl.services.worldservice.schemas import AllocationUpsertRequest, EvaluateRequest
from qmtl.services.worldservice.services import WorldService
from qmtl.services.worldservice.storage import PersistentStorage, Storage
from qmtl.services.worldservice.policy_engine import ValidationConfig, Policy
from qmtl.services.worldservice.decision import DecisionEvaluator
from qmtl.services.worldservice.risk_hub import PortfolioSnapshot, RiskSignalHub
from qmtl.services.worldservice.blob_store import JsonBlobStore


def _iso_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


async def _post_risk_snapshot(
    client: httpx.AsyncClient,
    *,
    world_id: str,
    actor: str = "risk",
    stage: str = "paper",
    version: str = "v1",
) -> None:
    resp = await client.post(
        f"/risk-hub/worlds/{world_id}/snapshots",
        headers={"X-Actor": actor, "X-Stage": stage},
        json={
            "world_id": world_id,
            "as_of": _iso_now(),
            "version": version,
            "weights": {"s1": 1.0},
        },
    )
    assert resp.status_code == 200


class _PersistentStoreStub:
    async def close(self) -> None:  # pragma: no cover - interface stub
        return None


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

    async def publish_risk_snapshot_updated(  # type: ignore[override]
        self,
        world_id: str,
        snapshot: dict,
        *,
        version: int = 1,
    ) -> None:
        payload = dict(snapshot)
        payload.setdefault("event_version", version)
        self.events.append(("risk_snapshot_updated", world_id, payload))

    async def publish_evaluation_run_created(  # type: ignore[override]
        self,
        world_id: str,
        *,
        strategy_id: str,
        run_id: str,
        stage: str,
        risk_tier: str | None = None,
        status: str | None = None,
        recommended_stage: str | None = None,
        version: int = 1,
    ) -> None:
        payload: dict[str, Any] = {
            "strategy_id": strategy_id,
            "run_id": run_id,
            "stage": stage,
            "version": version,
        }
        if risk_tier is not None:
            payload["risk_tier"] = risk_tier
        if status is not None:
            payload["status"] = status
        if recommended_stage is not None:
            payload["recommended_stage"] = recommended_stage
        self.events.append(("evaluation_run_created", world_id, payload))

    async def publish_evaluation_run_updated(  # type: ignore[override]
        self,
        world_id: str,
        *,
        strategy_id: str,
        run_id: str,
        stage: str,
        change_type: str,
        risk_tier: str | None = None,
        status: str | None = None,
        recommended_stage: str | None = None,
        version: int = 1,
    ) -> None:
        payload: dict[str, Any] = {
            "strategy_id": strategy_id,
            "run_id": run_id,
            "stage": stage,
            "change_type": change_type,
            "version": version,
        }
        if risk_tier is not None:
            payload["risk_tier"] = risk_tier
        if status is not None:
            payload["status"] = status
        if recommended_stage is not None:
            payload["recommended_stage"] = recommended_stage
        self.events.append(("evaluation_run_updated", world_id, payload))

    async def publish_validation_profile_changed(  # type: ignore[override]
        self,
        world_id: str,
        *,
        policy_version: int,
        version: int = 1,
    ) -> None:
        self.events.append(
            (
                "validation_profile_changed",
                world_id,
                {"policy_version": policy_version, "version": version},
            )
        )


class DummyExecutor:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def execute(self, payload: dict) -> dict:
        self.calls.append(dict(payload))
        return {"ok": True}
class _StubProducer:
    async def start(self) -> None:  # pragma: no cover - trivial stub
        return None

    async def stop(self) -> None:  # pragma: no cover - trivial stub
        return None

    async def send_and_wait(self, *args, **kwargs) -> None:  # pragma: no cover - stub
        return None


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
            worlds = r.json()
            assert worlds[0]["id"] == "w1"
            assert worlds[0]["name"] == "World"
            assert worlds[0]["allow_live"] is False
            assert worlds[0]["state"] == "ACTIVE"
            assert worlds[0]["circuit_breaker"] is False
            assert "created_at" in worlds[0]
            assert "updated_at" in worlds[0]

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


class _CapturingProducer:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict, bytes | None]] = []

    async def start(self) -> None:  # pragma: no cover - trivial stub
        return None

    async def stop(self) -> None:  # pragma: no cover - trivial stub
        return None

    async def send_and_wait(self, topic: str, data: bytes, key: bytes | None = None) -> None:
        import json

        self.sent.append((topic, json.loads(data.decode()), key))


@pytest.mark.asyncio
async def test_evaluation_and_overrides_emit_controlbus_events():
    producer = _CapturingProducer()
    bus = ControlBusProducer(producer=producer, topic="events")
    app = create_app(bus=bus, storage=Storage())

    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "w-events", "name": "Events"})
            await client.post("/worlds/w-events/policies", json={"policy": {}})
            await client.post("/worlds/w-events/set-default", json={"version": 1})

            eval_payload = {
                "strategy_id": "s1",
                "metrics": {"s1": {"sharpe": 1.0}},
                "policy": {},
                "run_id": "run-1",
                "stage": "backtest",
                "risk_tier": "low",
            }
            eval_resp = await client.post("/worlds/w-events/evaluate", json=eval_payload)
            assert eval_resp.status_code == 200

            override_resp = await client.post(
                "/worlds/w-events/strategies/s1/runs/run-1/override",
                json={
                    "status": "approved",
                    "reason": "risk sign-off",
                    "actor": "risk_team",
                    "timestamp": "2025-01-01T00:00:00Z",
                },
            )
            assert override_resp.status_code == 200

            override_resp_2 = await client.post(
                "/worlds/w-events/strategies/s1/runs/run-1/override",
                json={
                    "status": "rejected",
                    "reason": "manual reversal",
                    "actor": "risk_team",
                    "timestamp": "2025-01-02T00:00:00Z",
                },
            )
            assert override_resp_2.status_code == 200

            ex_post_resp = await client.post(
                "/worlds/w-events/strategies/s1/runs/run-1/ex-post-failures",
                json={
                    "status": "confirmed",
                    "category": "risk_breach",
                    "reason_code": "live_drawdown_breach",
                    "severity": "high",
                    "actor": "risk_team",
                    "recorded_at": "2025-01-03T00:00:00Z",
                    "evidence_url": "https://example.com/evidence",
                    "source": "manual",
                },
            )
            assert ex_post_resp.status_code == 200

    types = [evt.get("type") for _, evt, _ in producer.sent]
    assert "validation_profile_changed" in types
    assert "evaluation_run_created" in types
    assert "evaluation_run_updated" in types

    override_updates = [
        evt.get("data", {})
        for _, evt, _ in producer.sent
        if evt.get("type") == "evaluation_run_updated" and evt.get("data", {}).get("change_type") == "override"
    ]
    assert len(override_updates) == 2
    idempotency_keys = [entry.get("idempotency_key") for entry in override_updates]
    assert len(set(idempotency_keys)) == 2

    ex_post_updates = [
        evt.get("data", {})
        for _, evt, _ in producer.sent
        if evt.get("type") == "evaluation_run_updated" and evt.get("data", {}).get("change_type") == "ex_post_failure"
    ]
    assert len(ex_post_updates) == 1


@pytest.mark.asyncio
async def test_evaluation_run_creation_and_fetch():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "weval", "name": "Eval"})
            policy_resp = await client.post(
                "/worlds/weval/policies",
                json={"policy": {"thresholds": {"sharpe": {"metric": "sharpe", "min": 0.0}}}},
            )
            assert policy_resp.status_code == 200
            default_resp = await client.post("/worlds/weval/set-default", json={"version": 1})
            assert default_resp.status_code == 200
            payload = {
                "strategy_id": "s-eval",
                "metrics": {
                    "s-eval": {
                        "returns": {"sharpe": 1.5},
                        "risk": {
                            "adv_utilization_p95": 0.2,
                            "participation_rate_p95": 0.15,
                        },
                    }
                },
                "run_id": "run-eval-1",
                "stage": "backtest",
                "risk_tier": "medium",
            }
            resp = await client.post("/worlds/weval/evaluate", json=payload)
            assert resp.status_code == 200
            body = resp.json()
            assert body["evaluation_run_id"] == "run-eval-1"
            assert body["evaluation_run_url"].startswith("/worlds/weval/strategies/s-eval/runs/")

            run_resp = await client.get(body["evaluation_run_url"])
            assert run_resp.status_code == 200
            record = run_resp.json()
            assert record["run_id"] == "run-eval-1"
            assert record["strategy_id"] == "s-eval"
            assert record["status"] == "evaluated"
            assert record["stage"] == "backtest"
            assert record["model_card_version"] == "v1.0"
            assert record["links"]["metrics"].endswith("/worlds/weval/strategies/s-eval/runs/run-eval-1/metrics")
            assert record["links"]["history"].endswith("/worlds/weval/strategies/s-eval/runs/run-eval-1/history")
            assert record["metrics"]["returns"]["sharpe"] == 1.5
            assert record["metrics"]["risk"]["adv_utilization_p95"] == 0.2
            assert record["metrics"]["risk"]["participation_rate_p95"] == 0.15
            assert record["summary"]["status"] == "warn"
            assert record["summary"]["recommended_stage"] == "backtest_only"
            assert record["validation"]["results"]
            assert record["validation"]["policy_version"] == "1"
            assert record["validation"]["ruleset_hash"].startswith("blake3:")
            assert set(record["validation"]["results"].keys()) >= {
                "data_currency",
                "sample",
                "performance",
                "risk_constraint",
            }


@pytest.mark.asyncio
async def test_validation_invariants_endpoint_reports_live_failures():
    store = Storage()
    app = create_app(storage=store)
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "winv", "name": "Invariant World"})
            await store.record_evaluation_run(
                "winv",
                "s-live",
                "run-live-fail",
                stage="live",
                risk_tier="low",
                metrics={"returns": {"sharpe": 0.1}},
                summary={"status": "fail"},
            )

            inv_resp = await client.get("/worlds/winv/validations/invariants")
            assert inv_resp.status_code == 200
            body = inv_resp.json()
            assert body["ok"] is False
            assert body["live_status_failures"]


@pytest.mark.asyncio
async def test_evaluation_run_override_flow():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wover", "name": "Override World"})
            payload = {
                "strategy_id": "s-eval",
                "metrics": {"s-eval": {"sharpe": 1.2}},
                "policy": {},
                "run_id": "override-1",
                "stage": "paper",
                "risk_tier": "high",
            }
            resp = await client.post("/worlds/wover/evaluate", json=payload)
            assert resp.status_code == 200

            override_payload = {
                "status": "approved",
                "reason": "risk sign-off",
                "actor": "risk_team",
                "timestamp": "2025-01-01T00:00:00Z",
            }
            override_resp = await client.post(
                "/worlds/wover/strategies/s-eval/runs/override-1/override",
                json=override_payload,
            )
            assert override_resp.status_code == 200
            override_body = override_resp.json()
            summary = override_body["summary"]
            assert summary["override_status"] == "approved"
            assert summary["override_reason"] == "risk sign-off"
            assert summary["override_actor"] == "risk_team"
            assert summary["override_timestamp"]
            assert override_body["model_card_version"] == "v1.0"

            # A rejection should update the override fields
            reject_resp = await client.post(
                "/worlds/wover/strategies/s-eval/runs/override-1/override",
                json={"status": "rejected", "reason": "policy change", "actor": "risk_team"},
            )
            assert reject_resp.status_code == 200
            latest = reject_resp.json()["summary"]
            assert latest["override_status"] == "rejected"
            assert latest["override_reason"] == "policy change"


@pytest.mark.asyncio
async def test_evaluation_run_metrics_endpoint_requires_metrics():
    store = Storage()
    app = create_app(storage=store)
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wmet", "name": "Metrics World"})
            await store.record_evaluation_run(
                "wmet",
                "s1",
                "run-empty",
                stage="backtest",
                risk_tier="low",
                metrics=None,
                summary={"status": "warn"},
            )

            resp = await client.get("/worlds/wmet/strategies/s1/runs/run-empty/metrics")
            assert resp.status_code == 409
            detail = resp.json()["detail"]
            assert detail["code"] == "E_RUN_NOT_EVALUATED"

            await store.record_evaluation_run(
                "wmet",
                "s1",
                "run-full",
                stage="paper",
                risk_tier="low",
                metrics={"returns": {"sharpe": 1.1, "max_drawdown": -0.2}, "sample": {"n_trades_total": 12}},
                summary={"status": "pass"},
            )
            ok = await client.get("/worlds/wmet/strategies/s1/runs/run-full/metrics")
            assert ok.status_code == 200
            body = ok.json()
            assert body["world_id"] == "wmet"
            assert body["strategy_id"] == "s1"
            assert body["run_id"] == "run-full"
            assert body["metrics"]["returns"]["sharpe"] == 1.1
            assert body["metrics"]["returns"]["max_drawdown"] == -0.2
            assert body["metrics"]["sample"]["n_trades_total"] == 12


@pytest.mark.asyncio
async def test_world_decisions_get_endpoint_returns_active_strategies():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wdec", "name": "Decision World"})
            set_resp = await client.post("/worlds/wdec/decisions", json={"strategies": ["s1", "s2"]})
            assert set_resp.status_code == 200

            get_resp = await client.get("/worlds/wdec/decisions")
            assert get_resp.status_code == 200
            assert get_resp.json()["strategies"] == ["s1", "s2"]


@pytest.mark.asyncio
async def test_live_promotion_approve_endpoint_records_override():
    store = Storage()
    app = create_app(storage=store)
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wpro", "name": "Promo World"})
            await store.record_evaluation_run(
                "wpro",
                "s1",
                "run-1",
                stage="paper",
                risk_tier="low",
                metrics={"returns": {"sharpe": 1.0}},
                summary={"active_set": ["s1"]},
            )

            approve_resp = await client.post(
                "/worlds/wpro/promotions/live/approve",
                json={"strategy_id": "s1", "run_id": "run-1", "reason": "risk sign-off", "actor": "risk"},
            )
            assert approve_resp.status_code == 200
            assert approve_resp.json()["summary"]["override_status"] == "approved"


@pytest.mark.asyncio
async def test_live_promotion_apply_requires_manual_approval_by_policy():
    store = Storage()
    app = create_app(storage=store)
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wgov", "name": "Governed World"})
            policy_resp = await client.post(
                "/worlds/wgov/policies",
                json={
                    "policy": {
                        "governance": {"live_promotion": {"mode": "manual_approval"}},
                        "thresholds": {"sharpe": {"metric": "sharpe", "min": 0.0}},
                    }
                },
            )
            assert policy_resp.status_code == 200
            default_resp = await client.post("/worlds/wgov/set-default", json={"version": 1})
            assert default_resp.status_code == 200
            await _post_risk_snapshot(client, world_id="wgov")

            await client.post("/worlds/wgov/decisions", json={"strategies": ["s-old"]})
            await store.record_evaluation_run(
                "wgov",
                "s1",
                "run-1",
                stage="paper",
                risk_tier="low",
                metrics={"returns": {"sharpe": 1.0}},
                summary={"active_set": ["s1"], "override_status": "none", "status": "pass"},
            )

            apply_resp = await client.post(
                "/worlds/wgov/promotions/live/apply",
                json={"strategy_id": "s1", "run_id": "run-1", "apply_run_id": "apply-1"},
            )
            assert apply_resp.status_code == 409

            approve_resp = await client.post(
                "/worlds/wgov/promotions/live/approve",
                json={"strategy_id": "s1", "run_id": "run-1", "reason": "ok", "actor": "risk"},
            )
            assert approve_resp.status_code == 200

            apply_resp_2 = await client.post(
                "/worlds/wgov/promotions/live/apply",
                json={"strategy_id": "s1", "run_id": "run-1", "apply_run_id": "apply-2"},
            )
            assert apply_resp_2.status_code == 200


@pytest.mark.asyncio
async def test_live_promotion_plan_endpoint_derives_apply_plan():
    store = Storage()
    app = create_app(storage=store)
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wplan", "name": "Plan World"})
            set_resp = await client.post("/worlds/wplan/decisions", json={"strategies": ["s2", "s3"]})
            assert set_resp.status_code == 200
            await _post_risk_snapshot(client, world_id="wplan")

            await store.record_evaluation_run(
                "wplan",
                "s1",
                "run-1",
                stage="paper",
                risk_tier="low",
                metrics={"returns": {"sharpe": 1.0}},
                summary={"active_set": ["s1", "s2"], "override_status": "approved", "status": "pass"},
            )

            plan_resp = await client.get(
                "/worlds/wplan/promotions/live/plan",
                params={"strategy_id": "s1", "run_id": "run-1"},
            )
            assert plan_resp.status_code == 200
            body = plan_resp.json()
            assert body["plan"]["activate"] == ["s1"]
            assert body["plan"]["deactivate"] == ["s3"]


@pytest.mark.asyncio
async def test_live_promotion_auto_apply_endpoint_applies_latest_paper_run():
    store = Storage()
    app = create_app(storage=store)
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wauto", "name": "Auto World"})
            policy_resp = await client.post(
                "/worlds/wauto/policies",
                json={
                    "policy": {
                        "governance": {"live_promotion": {"mode": "auto_apply"}},
                        "thresholds": {"sharpe": {"metric": "sharpe", "min": 0.0}},
                    }
                },
            )
            assert policy_resp.status_code == 200
            default_resp = await client.post("/worlds/wauto/set-default", json={"version": 1})
            assert default_resp.status_code == 200
            await _post_risk_snapshot(client, world_id="wauto")

            await client.post("/worlds/wauto/decisions", json={"strategies": ["s3"]})
            await store.record_evaluation_run(
                "wauto",
                "s1",
                "run-paper-1",
                stage="paper",
                risk_tier="low",
                metrics={"returns": {"sharpe": 1.0}},
                summary={"active_set": ["s1", "s2"], "status": "pass"},
            )

            resp = await client.post("/worlds/wauto/promotions/live/auto-apply", json={})
            assert resp.status_code == 200
            body = resp.json()
            assert body["applied"] is True
            assert body["source_run_id"] == "run-paper-1"
            assert body["plan"]["activate"] == ["s1", "s2"]
            assert body["plan"]["deactivate"] == ["s3"]

            decisions = await client.get("/worlds/wauto/decisions")
            assert decisions.status_code == 200
            assert decisions.json()["strategies"] == ["s1", "s2"]


@pytest.mark.asyncio
async def test_live_promotion_candidates_endpoint_lists_latest_per_strategy():
    store = Storage()
    app = create_app(storage=store)
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wcand", "name": "Candidates World"})
            policy_resp = await client.post(
                "/worlds/wcand/policies",
                json={
                    "policy": {
                        "governance": {"live_promotion": {"mode": "manual_approval"}},
                        "thresholds": {"sharpe": {"metric": "sharpe", "min": 0.0}},
                    }
                },
            )
            assert policy_resp.status_code == 200
            default_resp = await client.post("/worlds/wcand/set-default", json={"version": 1})
            assert default_resp.status_code == 200
            await _post_risk_snapshot(client, world_id="wcand")

            await client.post("/worlds/wcand/decisions", json={"strategies": ["s-old"]})
            await store.record_evaluation_run(
                "wcand",
                "s1",
                "run-older",
                stage="paper",
                risk_tier="low",
                metrics={"returns": {"sharpe": 1.0}},
                summary={"active_set": ["s1"], "status": "pass", "override_status": "none"},
                created_at="2025-01-01T00:00:00Z",
                updated_at="2025-01-01T00:00:00Z",
            )
            await store.record_evaluation_run(
                "wcand",
                "s1",
                "run-latest",
                stage="paper",
                risk_tier="low",
                metrics={"returns": {"sharpe": 1.1}},
                summary={"active_set": ["s1", "s2"], "status": "pass", "override_status": "none"},
                created_at="2025-01-02T00:00:00Z",
                updated_at="2025-01-02T00:00:00Z",
            )
            await store.record_evaluation_run(
                "wcand",
                "s2",
                "run-fail",
                stage="paper",
                risk_tier="low",
                metrics={"returns": {"sharpe": -1.0}},
                summary={"active_set": ["s2"], "status": "fail", "override_status": "none"},
            )

            resp = await client.get(
                "/worlds/wcand/promotions/live/candidates",
                params={"limit": 10, "include_plan": "true"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["world_id"] == "wcand"
            assert body["promotion_mode"] == "manual_approval"
            candidates = body["candidates"]
            assert isinstance(candidates, list)
            # s1 should be present (latest run only); s2 is filtered out due to fail status.
            assert len(candidates) == 1
            assert candidates[0]["strategy_id"] == "s1"
            assert candidates[0]["run_id"] == "run-latest"
            assert candidates[0]["pending_manual_approval"] is True
            assert candidates[0]["eligible"] is True
            assert candidates[0]["blocked_reasons"] == ["manual_approval_required"]
            assert candidates[0]["plan"]["activate"] == ["s1", "s2"]
            assert candidates[0]["plan"]["deactivate"] == ["s-old"]


@pytest.mark.asyncio
async def test_campaign_status_endpoint_reports_phase_and_progress():
    store = Storage()
    app = create_app(storage=store)
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wcamp", "name": "Campaign World"})
            policy_resp = await client.post(
                "/worlds/wcamp/policies",
                json={
                    "policy": {
                        "campaign": {
                            "backtest": {"window": "2d"},
                            "paper": {"window": "1d"},
                            "common": {"min_sample_days": 1, "min_trades_total": 1},
                        },
                        "thresholds": {"sharpe": {"metric": "sharpe", "min": 0.0}},
                    }
                },
            )
            assert policy_resp.status_code == 200
            default_resp = await client.post("/worlds/wcamp/set-default", json={"version": 1})
            assert default_resp.status_code == 200

            await store.record_evaluation_run(
                "wcamp",
                "s1",
                "bt-1",
                stage="backtest",
                risk_tier="low",
                metrics={"returns": {"sharpe": 1.0}, "sample": {"effective_history_years": 0.01, "n_trades_total": 10}},
                summary={"status": "pass", "active_set": ["s1"]},
                created_at="2025-01-01T00:00:00Z",
                updated_at="2025-01-01T00:00:00Z",
            )
            await store.record_evaluation_run(
                "wcamp",
                "s1",
                "bt-2",
                stage="backtest",
                risk_tier="low",
                metrics={"returns": {"sharpe": 1.0}, "sample": {"effective_history_years": 0.01, "n_trades_total": 10}},
                summary={"status": "pass", "active_set": ["s1"]},
                created_at="2025-01-03T00:00:00Z",
                updated_at="2025-01-03T00:00:00Z",
            )
            await store.record_evaluation_run(
                "wcamp",
                "s1",
                "paper-1",
                stage="paper",
                risk_tier="low",
                metrics={"returns": {"sharpe": 1.2}, "sample": {"effective_history_years": 0.01, "n_trades_total": 10}},
                summary={"status": "pass", "active_set": ["s1"]},
                created_at="2025-01-04T00:00:00Z",
                updated_at="2025-01-05T00:00:00Z",
            )

            resp = await client.get("/worlds/wcamp/campaign/status", params={"strategy_id": "s1"})
            assert resp.status_code == 200
            body = resp.json()
            assert body["world_id"] == "wcamp"
            assert body["config"]["backtest_window"] == "2d"
            assert body["config"]["paper_window"] == "1d"
            assert len(body["strategies"]) == 1
            status = body["strategies"][0]
            assert status["strategy_id"] == "s1"
            assert status["phase"] == "paper_campaign"
            assert status["backtest"]["satisfied"] is True
            assert status["paper"]["satisfied"] is True
            assert status["promotable_to_paper"] is True
            assert status["promotable_to_live"] is True


@pytest.mark.asyncio
async def test_campaign_tick_emits_recommended_actions():
    store = Storage()
    app = create_app(storage=store)
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wtick", "name": "Tick World"})
            policy_resp = await client.post(
                "/worlds/wtick/policies",
                json={
                    "policy": {
                        "campaign": {"backtest": {"window": "0d"}, "paper": {"window": "0d"}},
                        "governance": {"live_promotion": {"mode": "auto_apply"}},
                        "thresholds": {"sharpe": {"metric": "sharpe", "min": 0.0}},
                    }
                },
            )
            assert policy_resp.status_code == 200
            default_resp = await client.post("/worlds/wtick/set-default", json={"version": 1})
            assert default_resp.status_code == 200

            await store.record_evaluation_run(
                "wtick",
                "s1",
                "bt-1",
                stage="backtest",
                risk_tier="low",
                metrics={"returns": {"sharpe": 1.0}, "sample": {"effective_history_years": 0.01, "n_trades_total": 10}},
                summary={"status": "pass", "active_set": ["s1"]},
                created_at="2025-01-01T00:00:00Z",
                updated_at="2025-01-01T00:00:00Z",
            )
            await store.record_evaluation_run(
                "wtick",
                "s2",
                "paper-1",
                stage="paper",
                risk_tier="low",
                metrics={"returns": {"sharpe": 1.0}, "sample": {"effective_history_years": 0.01, "n_trades_total": 10}},
                summary={"status": "pass", "active_set": ["s2"]},
                created_at="2025-01-02T00:00:00Z",
                updated_at="2025-01-02T00:00:00Z",
            )

            resp = await client.post("/worlds/wtick/campaign/tick", params={})
            assert resp.status_code == 200
            body = resp.json()
            assert body["schema_version"] == 1
            assert body["world_id"] == "wtick"
            actions = body["actions"]
            assert isinstance(actions, list)
            action_names = {a.get("action") for a in actions if isinstance(a, dict)}
            assert "evaluate" in action_names
            assert "auto_apply_live" in action_names

            evaluate_action = next(a for a in actions if isinstance(a, dict) and a.get("action") == "evaluate")
            assert evaluate_action.get("idempotency_key")
            assert evaluate_action.get("requires") == ["metrics"]
            assert isinstance(evaluate_action.get("suggested_run_id"), str)
            assert str(evaluate_action["suggested_run_id"]).startswith("camp-wtick-s1-")
            suggested_body = evaluate_action.get("suggested_body")
            assert isinstance(suggested_body, dict)
            assert "metrics" not in suggested_body
            assert suggested_body.get("run_id") == evaluate_action.get("suggested_run_id")

            auto_apply_action = next(a for a in actions if isinstance(a, dict) and a.get("action") == "auto_apply_live")
            assert auto_apply_action.get("idempotency_key")
            assert auto_apply_action.get("strategy_id") == "s2"
            assert auto_apply_action.get("stage") == "live"
            assert auto_apply_action.get("suggested_run_id") == "paper-1"


@pytest.mark.asyncio
async def test_live_promotion_apply_enforces_max_live_slots():
    store = Storage()
    app = create_app(storage=store)
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wslots", "name": "Slots World"})
            policy_resp = await client.post(
                "/worlds/wslots/policies",
                json={
                    "policy": {
                        "governance": {"live_promotion": {"mode": "manual_approval", "max_live_slots": 1}},
                        "thresholds": {"sharpe": {"metric": "sharpe", "min": 0.0}},
                    }
                },
            )
            assert policy_resp.status_code == 200
            default_resp = await client.post("/worlds/wslots/set-default", json={"version": 1})
            assert default_resp.status_code == 200
            await _post_risk_snapshot(client, world_id="wslots")

            await client.post("/worlds/wslots/decisions", json={"strategies": ["s-old"]})
            await store.record_evaluation_run(
                "wslots",
                "s1",
                "run-1",
                stage="paper",
                risk_tier="low",
                metrics={"returns": {"sharpe": 1.0}},
                summary={"active_set": ["s1", "s2"], "override_status": "approved", "status": "pass"},
            )

            apply_resp = await client.post(
                "/worlds/wslots/promotions/live/apply",
                json={"strategy_id": "s1", "run_id": "run-1", "apply_run_id": "apply-1"},
            )
            assert apply_resp.status_code == 409


@pytest.mark.asyncio
async def test_live_promotion_auto_apply_respects_cooldown():
    store = Storage()
    app = create_app(storage=store)
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wcool", "name": "Cooldown World"})
            policy_resp = await client.post(
                "/worlds/wcool/policies",
                json={
                    "policy": {
                        "governance": {"live_promotion": {"mode": "auto_apply", "cooldown": "10m"}},
                        "thresholds": {"sharpe": {"metric": "sharpe", "min": 0.0}},
                    }
                },
            )
            assert policy_resp.status_code == 200
            default_resp = await client.post("/worlds/wcool/set-default", json={"version": 1})
            assert default_resp.status_code == 200
            await _post_risk_snapshot(client, world_id="wcool")

            await client.post("/worlds/wcool/decisions", json={"strategies": ["s3"]})
            await store.record_evaluation_run(
                "wcool",
                "s1",
                "run-paper-1",
                stage="paper",
                risk_tier="low",
                metrics={"returns": {"sharpe": 1.0}},
                summary={"active_set": ["s1", "s2"], "status": "pass"},
            )
            await store.record_apply_stage("wcool", "prev-apply", "completed")

            resp = await client.post("/worlds/wcool/promotions/live/auto-apply", json={})
            assert resp.status_code == 200
            body = resp.json()
            assert body["applied"] is False
            assert body["reason"] == "cooldown_active"
            assert 0 < body["cooldown_remaining_sec"] <= 600

            decisions = await client.get("/worlds/wcool/decisions")
            assert decisions.status_code == 200
            assert decisions.json()["strategies"] == ["s3"]


@pytest.mark.asyncio
async def test_live_promotion_auto_apply_respects_canary_fraction():
    store = Storage()
    app = create_app(storage=store)
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wcanary", "name": "Canary World"})
            policy_resp = await client.post(
                "/worlds/wcanary/policies",
                json={
                    "policy": {
                        "governance": {"live_promotion": {"mode": "auto_apply", "canary_fraction": 0.0}},
                        "thresholds": {"sharpe": {"metric": "sharpe", "min": 0.0}},
                    }
                },
            )
            assert policy_resp.status_code == 200
            default_resp = await client.post("/worlds/wcanary/set-default", json={"version": 1})
            assert default_resp.status_code == 200
            await _post_risk_snapshot(client, world_id="wcanary")

            await client.post("/worlds/wcanary/decisions", json={"strategies": ["s3"]})
            await store.record_evaluation_run(
                "wcanary",
                "s1",
                "run-paper-1",
                stage="paper",
                risk_tier="low",
                metrics={"returns": {"sharpe": 1.0}},
                summary={"active_set": ["s1", "s2"], "status": "pass"},
            )

            resp = await client.post("/worlds/wcanary/promotions/live/auto-apply", json={})
            assert resp.status_code == 200
            body = resp.json()
            assert body["applied"] is False
            assert body["reason"] == "canary_skipped"

            decisions = await client.get("/worlds/wcanary/decisions")
            assert decisions.status_code == 200
            assert decisions.json()["strategies"] == ["s3"]


@pytest.mark.asyncio
async def test_live_promotion_approve_respects_policy_approvers():
    store = Storage()
    app = create_app(storage=store)
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wapp", "name": "Approvers World"})
            policy_resp = await client.post(
                "/worlds/wapp/policies",
                json={
                    "policy": {
                        "governance": {
                            "live_promotion": {
                                "mode": "manual_approval",
                                "approvers": ["risk"],
                            }
                        },
                        "thresholds": {"sharpe": {"metric": "sharpe", "min": 0.0}},
                    }
                },
            )
            assert policy_resp.status_code == 200
            default_resp = await client.post("/worlds/wapp/set-default", json={"version": 1})
            assert default_resp.status_code == 200

            await store.record_evaluation_run(
                "wapp",
                "s1",
                "run-1",
                stage="paper",
                risk_tier="low",
                metrics={"returns": {"sharpe": 1.0}},
                summary={"active_set": ["s1"], "override_status": "none", "status": "pass"},
            )

            deny_resp = await client.post(
                "/worlds/wapp/promotions/live/approve",
                json={"strategy_id": "s1", "run_id": "run-1", "reason": "ok", "actor": "someone"},
            )
            assert deny_resp.status_code == 403

            allow_resp = await client.post(
                "/worlds/wapp/promotions/live/approve",
                json={"strategy_id": "s1", "run_id": "run-1", "reason": "ok", "actor": "risk"},
            )
            assert allow_resp.status_code == 200
            assert allow_resp.json()["summary"]["override_status"] == "approved"


@pytest.mark.asyncio
async def test_live_promotion_approve_is_idempotent():
    store = Storage()
    app = create_app(storage=store)
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "widem", "name": "Idempotent World"})
            policy_resp = await client.post(
                "/worlds/widem/policies",
                json={
                    "policy": {
                        "governance": {"live_promotion": {"mode": "manual_approval"}},
                        "thresholds": {"sharpe": {"metric": "sharpe", "min": 0.0}},
                    }
                },
            )
            assert policy_resp.status_code == 200
            default_resp = await client.post("/worlds/widem/set-default", json={"version": 1})
            assert default_resp.status_code == 200

            await store.record_evaluation_run(
                "widem",
                "s1",
                "run-1",
                stage="paper",
                risk_tier="low",
                metrics={"returns": {"sharpe": 1.0}},
                summary={"active_set": ["s1"], "override_status": "none", "status": "pass"},
            )
            history_before = await store.list_evaluation_run_history("widem", "s1", "run-1")
            assert len(history_before) == 1

            approve_1 = await client.post(
                "/worlds/widem/promotions/live/approve",
                json={"strategy_id": "s1", "run_id": "run-1", "reason": "ok", "actor": "risk"},
            )
            assert approve_1.status_code == 200
            history_after_1 = await store.list_evaluation_run_history("widem", "s1", "run-1")
            assert len(history_after_1) == 2

            approve_2 = await client.post(
                "/worlds/widem/promotions/live/approve",
                json={"strategy_id": "s1", "run_id": "run-1", "reason": "ok", "actor": "risk"},
            )
            assert approve_2.status_code == 200
            history_after_2 = await store.list_evaluation_run_history("widem", "s1", "run-1")
            assert len(history_after_2) == 2


@pytest.mark.asyncio
async def test_ex_post_failure_record_flow_appends_history():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wexp", "name": "Ex-post Failure World"})
            payload = {
                "strategy_id": "s-eval",
                "metrics": {"s-eval": {"sharpe": 1.2}},
                "policy": {},
                "run_id": "exp-1",
                "stage": "live",
                "risk_tier": "high",
            }
            resp = await client.post("/worlds/wexp/evaluate", json=payload)
            assert resp.status_code == 200

            candidate_resp = await client.post(
                "/worlds/wexp/strategies/s-eval/runs/exp-1/ex-post-failures",
                json={
                    "status": "candidate",
                    "category": "risk_breach",
                    "reason_code": "live_drawdown_breach",
                    "severity": "high",
                    "actor": "system",
                    "recorded_at": "2025-01-02T00:00:00Z",
                    "source": "auto",
                },
            )
            assert candidate_resp.status_code == 200
            candidate_body = candidate_resp.json()
            failures = candidate_body["summary"]["ex_post_failures"]
            assert len(failures) == 1
            case_id = failures[0]["case_id"]
            assert case_id
            assert candidate_body["updated_at"] == "2025-01-02T00:00:00Z"

            confirm_resp = await client.post(
                "/worlds/wexp/strategies/s-eval/runs/exp-1/ex-post-failures",
                json={
                    "case_id": case_id,
                    "status": "confirmed",
                    "category": "risk_breach",
                    "reason_code": "live_drawdown_breach",
                    "severity": "high",
                    "actor": "risk_team",
                    "recorded_at": "2025-01-03T00:00:00Z",
                    "evidence_url": "https://example.com/evidence",
                    "source": "manual",
                },
            )
            assert confirm_resp.status_code == 200
            confirm_body = confirm_resp.json()
            failures = confirm_body["summary"]["ex_post_failures"]
            assert len(failures) == 2
            assert failures[-1]["status"] == "confirmed"
            assert confirm_body["updated_at"] == "2025-01-03T00:00:00Z"

            history_resp = await client.get(
                "/worlds/wexp/strategies/s-eval/runs/exp-1/history"
            )
            assert history_resp.status_code == 200
            items = history_resp.json()
            assert len(items) == 3
            assert items[-1]["payload"]["summary"]["ex_post_failures"][-1]["status"] == "confirmed"


@pytest.mark.asyncio
async def test_override_approved_requires_timestamp():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wover2", "name": "Override World 2"})
            payload = {
                "strategy_id": "s-eval",
                "metrics": {"s-eval": {"sharpe": 1.2}},
                "policy": {},
                "run_id": "override-2",
                "stage": "paper",
                "risk_tier": "high",
            }
            resp = await client.post("/worlds/wover2/evaluate", json=payload)
            assert resp.status_code == 200

            override_resp = await client.post(
                "/worlds/wover2/strategies/s-eval/runs/override-2/override",
                json={"status": "approved", "reason": "risk", "actor": "risk_team"},
            )
            assert override_resp.status_code == 422


@pytest.mark.asyncio
async def test_evaluation_run_history_endpoint_records_revisions():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "whist", "name": "History World"})
            payload = {
                "strategy_id": "s-hist",
                "metrics": {"s-hist": {"sharpe": 1.2}},
                "policy": {},
                "run_id": "hist-1",
                "stage": "paper",
                "risk_tier": "high",
            }
            resp = await client.post("/worlds/whist/evaluate", json=payload)
            assert resp.status_code == 200

            await client.post(
                "/worlds/whist/strategies/s-hist/runs/hist-1/override",
                json={
                    "status": "approved",
                    "reason": "manual",
                    "actor": "risk_team",
                    "timestamp": "2025-01-01T00:00:00Z",
                },
            )

            history_resp = await client.get(
                "/worlds/whist/strategies/s-hist/runs/hist-1/history"
            )
            assert history_resp.status_code == 200
            items = history_resp.json()
            assert len(items) == 2
            assert items[0]["revision"] == 1
            assert items[1]["revision"] == 2
            assert items[1]["payload"]["summary"]["override_status"] == "approved"


@pytest.mark.asyncio
async def test_live_monitoring_report_endpoint_lists_latest_live_runs():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wliverep", "name": "Live Report World"})
            policy = {"live_monitoring": {"sharpe_min": 0.0, "dd_max": 10.0, "severity": "soft"}}
            await client.post("/worlds/wliverep/policies", json={"policy": policy})
            await client.post("/worlds/wliverep/set-default", json={"version": 1})

            eval_payload = {
                "strategy_id": "s-live",
                "metrics": {
                    "s-live": {
                        "returns": {"sharpe": 1.0},
                        "diagnostics": {"live_returns": [0.01, -0.005, 0.02]},
                    }
                },
                "run_id": "run-live-1",
                "stage": "live",
                "risk_tier": "medium",
            }
            resp = await client.post("/worlds/wliverep/evaluate", json=eval_payload)
            assert resp.status_code == 200

            report_resp = await client.get("/worlds/wliverep/live-monitoring/report")
            assert report_resp.status_code == 200
            report = report_resp.json()
            assert report["world_id"] == "wliverep"
            assert report["summary"]["total"] == 1
            item = report["strategies"][0]
            assert item["strategy_id"] == "s-live"
            assert item["run_id"] == "run-live-1"
            assert item["live_monitoring"]["status"] in {"pass", "warn", "fail"}


@pytest.mark.asyncio
async def test_extended_validation_layers_are_persisted():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wcohort", "name": "Cohort World"})
            policy = {
                "cohort": {"top_k": 1, "sharpe_median_min": 0.9, "severity": "soft"},
                "portfolio": {"max_incremental_var_99": 0.5, "severity": "soft"},
                "stress": {"scenarios": {"crash": {"dd_max": 0.3}}},
                "live_monitoring": {"sharpe_min": 0.7, "dd_max": 0.3, "severity": "soft"},
            }
            await client.post("/worlds/wcohort/policies", json={"policy": policy})
            await client.post("/worlds/wcohort/set-default", json={"version": 1})

            payload1 = {
                "strategy_id": "s1",
                "metrics": {
                    "s1": {
                        "sharpe": 1.2,
                        "incremental_var_99": 0.3,
                        "stress.crash.max_drawdown": 0.2,
                        "live_sharpe": 1.0,
                        "live_max_drawdown": 0.1,
                    }
                },
                "run_id": "run-1",
                "stage": "backtest",
                "risk_tier": "medium",
            }
            payload2 = {
                "strategy_id": "s2",
                "metrics": {
                    "s2": {
                        "sharpe": 0.7,
                        "incremental_var_99": 0.6,
                        "stress.crash.max_drawdown": 0.4,
                        "live_sharpe": 0.5,
                        "live_max_drawdown": 0.35,
                    }
                },
                "run_id": "run-2",
                "stage": "backtest",
                "risk_tier": "medium",
            }

            await client.post("/worlds/wcohort/evaluate", json=payload1)
            await client.post("/worlds/wcohort/evaluate", json=payload2)

            run_resp = await client.get("/worlds/wcohort/strategies/s2/runs/run-2")
            record = run_resp.json()
            results = record["validation"]["results"]

            assert "cohort" in results
            assert "portfolio" in results
            assert "stress" in results
            assert "live_monitoring" in results
            assert results["cohort"]["reason_code"] in {"cohort_top_k_exceeded", "cohort_median_sharpe_below_min"}
            assert results["portfolio"]["reason_code"] in {"incremental_var_exceeds_max", "portfolio_ok", "incremental_var_missing"}
            assert results["stress"]["reason_code"] in {"crash_dd_exceeds_max", "stress_ok", "crash_dd_missing"}
            assert results["live_monitoring"]["reason_code"] in {"live_decay_missing", "live_sharpe_below_min", "live_monitoring_ok", "live_sharpe_missing"}


@pytest.mark.asyncio
async def test_evaluation_run_preserves_extra_metrics():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wextra"})
            await client.post("/worlds/wextra/policies", json={"policy": {}})
            await client.post("/worlds/wextra/set-default", json={"version": 1})

            payload = {
                "strategy_id": "s-extra",
                "run_id": "run-extra",
                "metrics": {
                    "s-extra": {
                        "returns": {"sharpe": 1.1},
                        "diagnostics": {"extra_metrics": {"foo": 1.23, "bar": -0.1}},
                    }
                },
                "stage": "backtest",
                "risk_tier": "low",
            }

            resp = await client.post("/worlds/wextra/evaluate", json=payload)
            assert resp.status_code == 200

            run_resp = await client.get("/worlds/wextra/strategies/s-extra/runs/run-extra")
            assert run_resp.status_code == 200
            body = run_resp.json()
            diagnostics = body["metrics"]["diagnostics"]
            assert diagnostics["extra_metrics"]["foo"] == pytest.approx(1.23)
            assert diagnostics["extra_metrics"]["bar"] == pytest.approx(-0.1)


@pytest.mark.asyncio
async def test_policy_enforced_via_ws_single_entry():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wssot"})
            policy = {"thresholds": {"sharpe": {"metric": "sharpe", "min": 1.0}}}
            await client.post("/worlds/wssot/policies", json={"policy": policy})
            await client.post("/worlds/wssot/set-default", json={"version": 1})

            payload = {
                "strategy_id": "s-weak",
                "run_id": "run-ssot",
                "metrics": {"s-weak": {"sharpe": 0.5}},
                "stage": "backtest",
                "risk_tier": "low",
            }
            resp = await client.post("/worlds/wssot/evaluate", json=payload)
            assert resp.status_code == 200
            eval_url = resp.json().get("evaluation_run_url")
            run_resp = await client.get(eval_url)
            assert run_resp.status_code == 200
            run = run_resp.json()
            assert run["summary"]["status"] != "pass"


@pytest.mark.asyncio
async def test_live_and_portfolio_metrics_are_derived():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wlive"})
            await client.post("/worlds/wlive/policies", json={"policy": {}})
            await client.post("/worlds/wlive/set-default", json={"version": 1})

            # 40 days of small positive/negative returns
            live_returns = [0.01 if i % 5 else -0.02 for i in range(40)]
            payload = {
                "strategy_id": "s-live",
                "run_id": "run-live",
                "metrics": {
                    "s-live": {
                        "returns": {"sharpe": 1.0, "max_drawdown": -0.15},
                        "diagnostics": {
                            "live_returns": live_returns,
                            "extra_metrics": {"portfolio_baseline_sharpe": 0.4},
                        },
                    }
                },
                "stage": "backtest",
                "risk_tier": "medium",
            }

            resp = await client.post("/worlds/wlive/evaluate", json=payload)
            assert resp.status_code == 200

            run_resp = await client.get("/worlds/wlive/strategies/s-live/runs/run-live")
            assert run_resp.status_code == 200
            body = run_resp.json()
            diagnostics = body["metrics"]["diagnostics"]
            assert diagnostics["live_sharpe_p30"] is not None
            assert diagnostics["live_max_drawdown_p30"] is not None
            assert diagnostics["live_vs_backtest_sharpe_ratio"] is not None

            risk = body["metrics"]["risk"]
            assert risk["incremental_var_99"] == pytest.approx(abs(-0.15))
            assert risk["incremental_es_99"] == pytest.approx(abs(-0.15) * 1.2)

            uplift = diagnostics["extra_metrics"]["portfolio_sharpe_uplift"]
            assert uplift == pytest.approx(1.0 - 0.4)


@pytest.mark.asyncio
async def test_advanced_metrics_are_derived_from_series():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wadv"})
            await client.post("/worlds/wadv/policies", json={"policy": {}})
            await client.post("/worlds/wadv/set-default", json={"version": 1})

            returns = [0.01 if i % 7 else -0.03 for i in range(120)]
            payload = {
                "strategy_id": "s-adv",
                "run_id": "run-adv-1",
                "metrics": {
                    "s-adv": {
                        "returns": {"sharpe": 1.0, "max_drawdown": -0.1},
                        "diagnostics": {"search_intensity": 10, "extra_metrics": {"n_features": 50}},
                    }
                },
                "series": {"s-adv": {"returns": returns}},
                "stage": "backtest",
                "risk_tier": "medium",
            }

            resp = await client.post("/worlds/wadv/evaluate", json=payload)
            assert resp.status_code == 200

            run_resp = await client.get("/worlds/wadv/strategies/s-adv/runs/run-adv-1")
            assert run_resp.status_code == 200
            body = run_resp.json()

            returns_block = body["metrics"]["returns"]
            assert returns_block["var_p01"] is not None
            assert returns_block["es_p01"] is not None
            assert returns_block["max_time_under_water_days"] is not None

            sample_block = body["metrics"]["sample"]
            coverage = sample_block["regime_coverage"]
            assert coverage["low_vol"] is not None
            assert coverage["mid_vol"] is not None
            assert coverage["high_vol"] is not None
            assert coverage["low_vol"] + coverage["mid_vol"] + coverage["high_vol"] == pytest.approx(1.0)

            robustness = body["metrics"]["robustness"]
            assert 0.0 <= robustness["probabilistic_sharpe_ratio"] <= 1.0
            assert robustness["cv_folds"] is not None
            assert robustness["cv_sharpe_mean"] is not None
            assert robustness["cv_sharpe_std"] is not None

            diagnostics = body["metrics"]["diagnostics"]
            assert diagnostics["strategy_complexity"] is not None


@pytest.mark.asyncio
async def test_paper_shadow_consistency_rule_detects_drift():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wps"})
            policy = {
                "paper_shadow_consistency": {
                    "stages": ["paper"],
                    "min_sharpe_ratio": 0.8,
                    "max_drawdown_ratio": 1.5,
                    "severity": "blocking",
                    "owner": "ops",
                }
            }
            await client.post("/worlds/wps/policies", json={"policy": policy})
            await client.post("/worlds/wps/set-default", json={"version": 1})

            backtest_returns = [0.01 if i % 5 else -0.02 for i in range(60)]
            await client.post(
                "/worlds/wps/evaluate",
                json={
                    "strategy_id": "s-drift",
                    "run_id": "run-backtest",
                    "stage": "backtest",
                    "risk_tier": "medium",
                    "metrics": {"s-drift": {"returns": {"sharpe": 1.0, "max_drawdown": -0.2}}},
                    "series": {"s-drift": {"returns": backtest_returns}},
                },
            )

            paper_returns = [0.005 if i % 5 else -0.04 for i in range(60)]
            paper_resp = await client.post(
                "/worlds/wps/evaluate",
                json={
                    "strategy_id": "s-drift",
                    "run_id": "run-paper",
                    "stage": "paper",
                    "risk_tier": "medium",
                    "metrics": {"s-drift": {"returns": {"sharpe": 0.5, "max_drawdown": -0.4}}},
                    "series": {"s-drift": {"returns": paper_returns}},
                },
            )
            assert paper_resp.status_code == 200

            run_resp = await client.get("/worlds/wps/strategies/s-drift/runs/run-paper")
            assert run_resp.status_code == 200
            record = run_resp.json()
            results = record["validation"]["results"]
            assert "paper_shadow_consistency" in results
            assert results["paper_shadow_consistency"]["status"] == "fail"
            assert results["paper_shadow_consistency"]["reason_code"].startswith("paper_shadow_")

            extra = record["metrics"]["diagnostics"]["extra_metrics"]
            assert extra["backtest_sharpe"] == pytest.approx(1.0)
            assert extra["paper_vs_backtest_sharpe_ratio"] == pytest.approx(0.5)
            assert extra["paper_vs_backtest_dd_ratio"] == pytest.approx(2.0)


@pytest.mark.asyncio
async def test_benchmark_metrics_and_relative_rule_are_recorded():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wbench"})
            policy = {
                "benchmark": {"min_vs_benchmark_sharpe": 0.0, "severity": "soft", "owner": "quant"},
            }
            await client.post("/worlds/wbench/policies", json={"policy": policy})
            await client.post("/worlds/wbench/set-default", json={"version": 1})

            resp = await client.post(
                "/worlds/wbench/evaluate",
                json={
                    "strategy_id": "s-bench",
                    "run_id": "run-bench-1",
                    "stage": "backtest",
                    "risk_tier": "low",
                    "metrics": {
                        "s-bench": {
                            "returns": {"sharpe": 0.3},
                            "benchmark": {"sharpe": 0.4, "max_drawdown": 0.1, "volatility": 0.2},
                        }
                    },
                },
            )
            assert resp.status_code == 200

            run_resp = await client.get("/worlds/wbench/strategies/s-bench/runs/run-bench-1")
            assert run_resp.status_code == 200
            record = run_resp.json()

            assert record["metrics"]["benchmark"]["sharpe"] == pytest.approx(0.4)
            results = record["validation"]["results"]
            assert "benchmark" in results
            assert results["benchmark"]["status"] == "fail"

            extra = record["metrics"]["diagnostics"]["extra_metrics"]
            assert extra["benchmark_sharpe"] == pytest.approx(0.4)
            assert extra["vs_benchmark_sharpe"] == pytest.approx(-0.1)


@pytest.mark.asyncio
async def test_cohort_campaign_evaluation_records_runs_for_all_candidates():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wcohort"})
            policy = {
                "selection": {"top_k": {"metric": "sharpe", "k": 1}},
                "cohort": {"top_k": 1, "severity": "soft", "owner": "risk"},
            }
            await client.post("/worlds/wcohort/policies", json={"policy": policy})
            await client.post("/worlds/wcohort/set-default", json={"version": 1})

            resp = await client.post(
                "/worlds/wcohort/evaluate-cohort",
                json={
                    "campaign_id": "camp-1",
                    "run_id": "run-camp-1",
                    "stage": "backtest",
                    "risk_tier": "low",
                    "metrics": {
                        "s-good": {"returns": {"sharpe": 1.0}},
                        "s-bad": {"returns": {"sharpe": 0.5}},
                    },
                },
            )
            assert resp.status_code == 200
            payload = resp.json()
            assert payload["campaign_id"] == "camp-1"
            assert payload["run_id"] == "run-camp-1"
            assert set(payload["candidates"]) == {"s-good", "s-bad"}
            assert "s-good" in payload["active"]
            assert "s-bad" not in payload["active"]

            assert set(payload["evaluation_runs"].keys()) == {"s-good", "s-bad"}
            for sid in ("s-good", "s-bad"):
                run_resp = await client.get(payload["evaluation_runs"][sid])
                assert run_resp.status_code == 200
                record = run_resp.json()
                assert record["run_id"] == "run-camp-1"
                assert record["summary"]["campaign_id"] == "camp-1"
                assert set(record["summary"]["campaign_candidates"]) == {"s-good", "s-bad"}
                assert set(record["summary"]["active_set"]) == {"s-good"}
                assert record["summary"]["active"] is (sid == "s-good")

                results = record["validation"]["results"]
                assert "cohort" in results
                if sid == "s-bad":
                    assert results["cohort"]["status"] == "fail"


@pytest.mark.asyncio
async def test_policy_missing_metrics_is_flagged():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wmissing"})
            policy = {"thresholds": {"sharpe": {"metric": "sharpe", "min": 1.0}}}
            await client.post("/worlds/wmissing/policies", json={"policy": policy})
            await client.post("/worlds/wmissing/set-default", json={"version": 1})

            payload = {
                "strategy_id": "s-miss",
                "run_id": "run-miss",
                "metrics": {"s-miss": {"max_drawdown": -0.1}},  # sharpe missing
                "stage": "backtest",
                "risk_tier": "low",
            }
            resp = await client.post("/worlds/wmissing/evaluate", json=payload)
            assert resp.status_code == 200
            eval_url = resp.json().get("evaluation_run_url")
            run_resp = await client.get(eval_url)
            assert run_resp.status_code == 200
            run = run_resp.json()
            assert run["summary"]["status"] != "pass"


@pytest.mark.asyncio
async def test_summary_status_reflects_warn_results():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wwarn"})
            policy = {
                "thresholds": {"sharpe": {"metric": "sharpe", "min": 1.0}},
                "validation": {"on_missing_metric": "warn"},
            }
            await client.post("/worlds/wwarn/policies", json={"policy": policy})
            await client.post("/worlds/wwarn/set-default", json={"version": 1})

            payload = {
                "strategy_id": "s-warn",
                "run_id": "run-warn",
                "metrics": {"s-warn": {"max_drawdown": -0.1}},  # sharpe missing -> warn
                "stage": "backtest",
                "risk_tier": "low",
            }
            resp = await client.post("/worlds/wwarn/evaluate", json=payload)
            assert resp.status_code == 200
            run_resp = await client.get(resp.json()["evaluation_run_url"])
            assert run_resp.status_code == 200
            run = run_resp.json()
            assert run["summary"]["status"] == "warn"


@pytest.mark.asyncio
async def test_risk_hub_rejects_missing_actor_header():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            snap = {
                "as_of": "2025-01-01T00:00:00Z",
                "version": "v1",
                "weights": {"s1": 1.0},
            }
            resp = await client.post("/risk-hub/worlds/wfail/snapshots", json=snap)
            assert resp.status_code == 400


@pytest.mark.asyncio
async def test_fail_closed_enforced_for_high_risk_world():
    storage = Storage()
    await storage.create_world({"id": "whigh", "risk_profile": {"tier": "high", "client_critical": True}})
    policy = Policy(validation=ValidationConfig(on_error="warn", on_missing_metric="warn"))
    version = await storage.add_policy("whigh", policy)
    await storage.set_default_policy("whigh", version=version)

    evaluator = DecisionEvaluator(storage)
    resolved, _ = await evaluator._resolve_policy("whigh", EvaluateRequest())  # type: ignore[arg-type]

    assert resolved.validation.on_error == "fail"
    assert resolved.validation.on_missing_metric == "fail"


@pytest.mark.asyncio
async def test_extended_validation_scheduler_invoked():
    scheduled: list[Any] = []

    def scheduler(coro):
        scheduled.append(coro)

    app = create_app(storage=Storage(), extended_validation_scheduler=scheduler)
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wsched"})
            await client.post("/worlds/wsched/policies", json={"policy": {"cohort": {"top_k": 1}}})
            await client.post("/worlds/wsched/set-default", json={"version": 1})

            payload = {
                "strategy_id": "s1",
                "run_id": "run-1",
                "metrics": {"s1": {"sharpe": 1.0, "max_drawdown": 0.1}},
                "stage": "backtest",
                "risk_tier": "low",
            }
            resp = await client.post("/worlds/wsched/evaluate", json=payload)
            assert resp.status_code == 200

    assert scheduled, "scheduler should be invoked"
    # run the queued coroutine to avoid warnings and ensure it succeeds
    coro = scheduled.pop()
    result = await coro
    assert result >= 0


@pytest.mark.asyncio
async def test_risk_hub_snapshot_consumed_by_extended_worker():
    storage = Storage()
    bus = DummyBus()
    app = create_app(storage=storage, bus=bus, risk_hub_token="t0k")
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            # write snapshot
            snap = {
                "as_of": "2025-01-01T00:00:00Z",
                "version": "v1",
                "weights": {"s1": 0.6, "s2": 0.4},
                "covariance": {"s1,s1": 0.01, "s2,s2": 0.04, "s1,s2": 0.015},
            }
            resp = await client.post(
                "/risk-hub/worlds/whub/snapshots",
                json=snap,
                headers={"Authorization": "Bearer t0k", "X-Actor": "test-suite", "X-Stage": "paper"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["provenance"].get("actor") == "test-suite"
            assert body["provenance"].get("stage") == "paper"

            await client.post("/worlds", json={"id": "whub"})
            await client.post("/worlds/whub/policies", json={"policy": {"cohort": {"top_k": 1}}})
            await client.post("/worlds/whub/set-default", json={"version": 1})

            payload = {
                "strategy_id": "s1",
                "run_id": "run-hub",
                "metrics": {"s1": {"sharpe": 1.0}},
                "stage": "backtest",
                "risk_tier": "low",
            }
            resp_eval = await client.post("/worlds/whub/evaluate", json=payload)
            assert resp_eval.status_code == 200

            run_resp = await client.get("/worlds/whub/strategies/s1/runs/run-hub")
            body = run_resp.json()
            diagnostics = body["metrics"]["diagnostics"]
            extra = diagnostics.get("extra_metrics", {})
            # hub 기반 포트폴리오 변동성 파생치가 계산되었는지 확인
            assert extra.get("portfolio_var_99_with_candidate") is not None or extra.get("portfolio_es_99_with_candidate") is not None
            assert any(evt[0] == "risk_snapshot_updated" for evt in bus.events)


@pytest.mark.asyncio
async def test_risk_hub_persists_snapshots_with_persistent_storage(tmp_path, fake_redis):
    db_path = tmp_path / "risk_hub.db"

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

    app = create_app(storage_factory=_factory_builder())
    async with app.router.lifespan_context(app):
        async with httpx.ASGITransport(app=app) as asgi:
            async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
                snap = {
                    "as_of": "2025-01-01T00:00:00Z",
                    "version": "v1",
                    "weights": {"s1": 1.0},
                    "covariance": {"s1,s1": 0.02},
                    "realized_returns": {"s1": [0.01, -0.005]},
                }
                resp = await client.post(
                    "/risk-hub/worlds/persist-hub/snapshots",
                    json=snap,
                    headers={"X-Actor": "test-suite", "X-Stage": "paper"},
                )
                assert resp.status_code == 200

    storage_inspect = await PersistentStorage.create(
        db_dsn=str(db_path),
        redis_client=fake_redis,
    )
    try:
        latest = await storage_inspect.latest_risk_snapshot("persist-hub")
        assert latest is not None
        assert latest["version"] == "v1"
        assert latest["weights"] == {"s1": 1.0}
        assert latest["realized_returns"] == {"s1": [0.01, -0.005]}
    finally:
        await storage_inspect.close()


@pytest.mark.asyncio
async def test_risk_hub_latest_supports_expand_and_stage_filter(tmp_path):
    risk_hub = RiskSignalHub(blob_store=JsonBlobStore(tmp_path), inline_cov_threshold=0)
    app = create_app(storage=Storage(), risk_hub=risk_hub)

    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            snap_backtest = {
                "as_of": "2025-01-01T00:00:00Z",
                "version": "v-backtest",
                "weights": {"s1": 1.0},
                "realized_returns": {"s1": [0.01, -0.005]},
            }
            resp = await client.post(
                "/risk-hub/worlds/wexp/snapshots",
                json=snap_backtest,
                headers={"X-Actor": "test-suite", "X-Stage": "backtest"},
            )
            assert resp.status_code == 200

            snap_paper = {
                "as_of": "2025-01-02T00:00:00Z",
                "version": "v-paper",
                "weights": {"s1": 1.0},
            }
            resp2 = await client.post(
                "/risk-hub/worlds/wexp/snapshots",
                json=snap_paper,
                headers={"X-Actor": "test-suite", "X-Stage": "paper"},
            )
            assert resp2.status_code == 200

            latest_plain = await client.get("/risk-hub/worlds/wexp/snapshots/latest", params={"stage": "backtest"})
            assert latest_plain.status_code == 200
            plain_payload = latest_plain.json()
            assert plain_payload.get("version") == "v-backtest"
            assert plain_payload.get("realized_returns") is None
            assert plain_payload.get("realized_returns_ref")

            latest_expanded = await client.get(
                "/risk-hub/worlds/wexp/snapshots/latest",
                params={"stage": "backtest", "expand": "true"},
            )
            assert latest_expanded.status_code == 200
            payload = latest_expanded.json()
            assert payload.get("version") == "v-backtest"
            assert payload.get("realized_returns") == {"s1": [0.01, -0.005]}


@pytest.mark.asyncio
async def test_evaluate_sources_metrics_from_latest_run_when_missing():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wsrc"})
            await client.post("/worlds/wsrc/policies", json={"policy": {}})
            await client.post("/worlds/wsrc/set-default", json={"version": 1})

            payload = {
                "strategy_id": "s1",
                "run_id": "run-prev",
                "metrics": {
                    "s1": {
                        "returns": {"sharpe": 1.0, "max_drawdown": 0.1},
                        "sample": {"effective_history_years": 0.5},
                    }
                },
                "stage": "backtest",
                "risk_tier": "low",
            }
            resp = await client.post("/worlds/wsrc/evaluate", json=payload)
            assert resp.status_code == 200

            resp2 = await client.post(
                "/worlds/wsrc/evaluate",
                json={
                    "strategy_id": "s1",
                    "run_id": "run-missing",
                    "metrics": {},
                    "stage": "backtest",
                    "risk_tier": "low",
                },
            )
            assert resp2.status_code == 200
            run_url = resp2.json().get("evaluation_run_url")
            assert run_url
            run_resp = await client.get(run_url)
            assert run_resp.status_code == 200
            recorded = run_resp.json()
            assert recorded.get("metrics", {}).get("returns", {}).get("sharpe") == 1.0


@pytest.mark.asyncio
async def test_evaluate_sources_metrics_from_risk_hub_when_run_metrics_missing():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "wrisk"})
            await client.post("/worlds/wrisk/policies", json={"policy": {}})
            await client.post("/worlds/wrisk/set-default", json={"version": 1})

            snapshot = {
                "as_of": "2025-01-01T00:00:00Z",
                "version": "v1",
                "weights": {"s2": 1.0},
                "covariance": {"s1,s1": 0.04, "s2,s2": 0.01, "s1,s2": 0.005},
            }
            snap_resp = await client.post(
                "/risk-hub/worlds/wrisk/snapshots",
                json=snapshot,
                headers={"X-Actor": "test-suite", "X-Stage": "backtest"},
            )
            assert snap_resp.status_code == 200

            resp = await client.post(
                "/worlds/wrisk/evaluate",
                json={
                    "strategy_id": "s1",
                    "run_id": "run-risk",
                    "metrics": {},
                    "stage": "backtest",
                    "risk_tier": "low",
                },
            )
            assert resp.status_code == 200
            run_url = resp.json().get("evaluation_run_url")
            assert run_url
            run_resp = await client.get(run_url)
            assert run_resp.status_code == 200
            recorded = run_resp.json()
            risk = recorded.get("metrics", {}).get("risk", {})
            assert risk.get("incremental_var_99") is not None
            extra = recorded.get("metrics", {}).get("diagnostics", {}).get("extra_metrics", {})
            assert extra.get("risk_hub_snapshot_version") == "v1"


@pytest.mark.asyncio
async def test_allocations_missing_snapshot_returns_empty_payload():
    bus = DummyBus()
    app = create_app(bus=bus, storage=Storage())

    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            response = await client.get("/allocations", params={"world_id": "absent"})

    assert response.status_code == 404
    detail = response.json().get("detail")
    assert "allocation snapshot" in str(detail)


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
async def test_rebalancing_apply_overlay_mode_success():
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
                "overlay": {
                    "instrument_by_world": {"w1": "BTC_PERP"},
                    "price_by_symbol": {"BTC_PERP": 100.0},
                    "min_order_notional": 1.0,
                },
            }

            resp = await client.post("/rebalancing/apply", json=payload)
            assert resp.status_code == 200
            body = resp.json()
            assert body["overlay_deltas"] == []


@pytest.mark.asyncio
async def test_rebalancing_apply_overlay_requires_config():
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
            assert resp.status_code == 422
            assert resp.json() == {
                "detail": "overlay config is required when mode='overlay'"
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
async def test_allocations_snapshot_endpoint():
    app = create_app(storage=Storage())

    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "w1"})
            payload = {
                "run_id": "alloc-run-3",
                "total_equity": 1000.0,
                "world_allocations": {"w1": 1.0},
                "positions": [
                    {
                        "world_id": "w1",
                        "strategy_id": "s1",
                        "symbol": "BTC",
                        "qty": 1.0,
                        "mark": 100.0,
                    }
                ],
            }
            await client.post("/allocations", json=payload)

            resp = await client.get("/allocations", params={"world_id": "w1"})
            assert resp.status_code == 200
            body = resp.json()
            alloc = body["allocations"].get("w1")
            assert alloc is not None
            assert alloc["allocation"] == pytest.approx(1.0)
            assert alloc["world_id"] == "w1"
            assert alloc["run_id"] == "alloc-run-3"
            assert alloc["ttl"] == "300s"
            assert alloc["stale"] is False
            assert alloc.get("strategy_alloc_total") is None


@pytest.mark.asyncio
async def test_allocations_snapshot_missing_world_returns_404():
    app = create_app(storage=Storage())

    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            resp = await client.get("/allocations", params={"world_id": "absent"})
            assert resp.status_code == 404
            detail = resp.json().get("detail")
            assert "allocation snapshot" in str(detail)


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
            await client.post("/worlds", json={"id": "mode-test", "allow_live": True})

            resp = await client.get("/worlds/mode-test/decide")
            assert resp.status_code == 200
            body = resp.json()
            assert body["effective_mode"] == "validate"

            await client.post(
                "/worlds/mode-test/bindings", json={"strategies": ["s-live"]}
            )
            await client.post(
                "/worlds/mode-test/decisions", json={"strategies": ["s-live"]}
            )
            await client.post(
                "/worlds/mode-test/history",
                json={
                    "strategy_id": "s-live",
                    "node_id": "n-1",
                    "interval": 60,
                    "coverage_bounds": [1, 2],
                    "dataset_fingerprint": "fp-mode",
                },
            )

            live_resp = await client.get("/worlds/mode-test/decide")
            assert live_resp.status_code == 200
            live_body = live_resp.json()
            assert live_body["effective_mode"] == "live"


@pytest.mark.asyncio
async def test_decide_blocks_live_without_allow_flag():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "no-live"})
            await client.post(
                "/worlds/no-live/bindings", json={"strategies": ["s-1"]}
            )
            await client.post(
                "/worlds/no-live/decisions", json={"strategies": ["s-1"]}
            )
            await client.post(
                "/worlds/no-live/history",
                json={
                    "strategy_id": "s-1",
                    "node_id": "n-1",
                    "interval": 60,
                    "coverage_bounds": [1, 2],
                    "dataset_fingerprint": "fp-no-live",
                },
            )

            resp = await client.get("/worlds/no-live/decide")
            assert resp.status_code == 200
            body = resp.json()
            assert body["effective_mode"] == "compute-only"
            assert "allow_live_disabled" in body["reason"]
            assert body["ttl"] == "60s"


@pytest.mark.asyncio
async def test_decide_allows_live_when_policy_inputs_present():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "live-ok", "allow_live": True})
            await client.post(
                "/worlds/live-ok/bindings", json={"strategies": ["s-1"]}
            )
            await client.post(
                "/worlds/live-ok/decisions", json={"strategies": ["s-1"]}
            )
            await client.post(
                "/worlds/live-ok/history",
                json={
                    "strategy_id": "s-1",
                    "node_id": "n-1",
                    "interval": 60,
                    "coverage_bounds": [1, 2],
                    "dataset_fingerprint": "fp-live",
                    "rows": 10,
                },
            )

            resp = await client.get("/worlds/live-ok/decide")
            assert resp.status_code == 200
            body = resp.json()
            assert body["effective_mode"] == "live"
            assert "allow_live" in body["reason"]
            assert "metrics_ok" in body["reason"]
            assert body["ttl"] == "300s"


@pytest.mark.asyncio
async def test_decide_uses_hysteresis_when_metrics_missing():
    app = create_app(storage=Storage())
    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "hys", "allow_live": True})
            await client.post("/worlds/hys/bindings", json={"strategies": ["s-1"]})
            await client.post(
                "/worlds/hys/decisions", json={"strategies": ["s-1"]}
            )
            await client.post(
                "/worlds/hys/history",
                json={
                    "strategy_id": "s-1",
                    "node_id": "n-1",
                    "interval": 60,
                    "coverage_bounds": [5, 10],
                    "dataset_fingerprint": "fp-hys",
                },
            )

            first = await client.get("/worlds/hys/decide")
            assert first.status_code == 200
            assert first.json()["effective_mode"] == "live"

            await client.post(
                "/worlds/hys/history",
                json={
                    "strategy_id": "s-1",
                    "node_id": "n-1",
                    "interval": 60,
                    "dataset_fingerprint": "fp-hys",
                    "as_of": "2025-03-16T00:00:00Z",
                },
            )

            resp = await client.get("/worlds/hys/decide")
            assert resp.status_code == 200
            body = resp.json()
            assert body["effective_mode"] == "live"
            assert "hysteresis_hold" in body["reason"]
            assert body["ttl"] == "120s"

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
    storage._world_nodes.nodes.setdefault("w1", {})["legacy"] = {
        "backtest": {
            "status": "paused",
            "annotations": {"source": "legacy"},
        }
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
            assert "source" not in legacy_event


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
async def test_create_app_with_config_object_uses_redis_storage(
    monkeypatch, tmp_path, fake_redis
):
    config = WorldServiceServerConfig(
        dsn=f"sqlite+aiosqlite:///{tmp_path/'worlds.db'}",
        redis="redis://example",
    )

    calls: list[str] = []

    def _fake_from_url(url: str, decode_responses: bool = True):
        calls.append(url)
        assert decode_responses is True
        return fake_redis

    monkeypatch.setattr(worldservice_api.redis, "from_url", _fake_from_url)

    app = create_app(config=config)

    async with app.router.lifespan_context(app):
        assert isinstance(app.state.storage, PersistentStorage)
        assert app.state.world_service.store is app.state.storage
        assert app.state.storage._redis is fake_redis

    assert calls == [config.redis]


def test_build_hub_blob_store_falls_back_to_sync_redis_client(monkeypatch):
    cfg = RiskHubConfig(blob_store=RiskHubBlobStoreConfig(type="redis"))

    class _AsyncRedisStub:
        async def set(self, *args: Any, **kwargs: Any) -> None:
            return None

    class _SyncRedisStub:
        def __init__(self) -> None:
            self._values: dict[str, str] = {}

        def set(self, key: str, value: str) -> None:
            self._values[key] = value

        def get(self, key: str) -> str | None:
            return self._values.get(key)

        def expire(self, key: str, ttl: int) -> None:
            # ttl bookkeeping is not required for this unit test
            return None

    sync_stub = _SyncRedisStub()

    import redis as redis_sync

    monkeypatch.setattr(
        redis_sync,
        "from_url",
        lambda *args, **kwargs: sync_stub,
    )

    store = worldservice_api._build_hub_blob_store(
        cfg,
        redis_url="redis://example",
        redis_client=_AsyncRedisStub(),
        profile=DeploymentProfile.PROD,
    )
    assert store is not None
    assert getattr(store, "_client") is sync_stub

    ref = store.write("cov", {"a": 1})
    assert store.read(ref) == {"a": 1}


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


def test_create_app_requires_redis_in_prod_profile(tmp_path):
    config_path = tmp_path / "worldservice.yml"
    config_path.write_text(
        """
profile: prod
worldservice:
  server:
    dsn: sqlite+aiosqlite:///worlds.db
""".strip()
    )

    with pytest.raises(RuntimeError, match="worldservice.server.redis"):
        create_app(config_path=config_path)


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


def test_create_app_applies_config_profile_when_storage_injected(tmp_path):
    config_path = tmp_path / "worldservice.yml"
    config_path.write_text(
        """
profile: prod
worldservice:
  server:
    dsn: sqlite+aiosqlite:///worlds.db
""".strip()
    )

    with pytest.raises(RuntimeError, match="PersistentStorage"):
        create_app(config_path=config_path, storage=Storage())


def test_create_app_requires_controlbus_in_prod_profile():
    with pytest.raises(RuntimeError, match="ControlBus"):
        create_app(profile=DeploymentProfile.PROD, storage=_PersistentStoreStub())


def test_create_app_sets_controlbus_required_flag_in_prod():
    producer = ControlBusProducer(producer=_StubProducer(), required=False)

    app = create_app(
        bus=producer, profile=DeploymentProfile.PROD, storage=_PersistentStoreStub()
    )

    assert producer._required is True
    assert app.state.world_service.bus is producer


def test_create_app_warns_when_controlbus_missing_in_dev(caplog):
    config = WorldServiceServerConfig(dsn="sqlite:///worlds.db")

    with caplog.at_level("WARNING"):
        create_app(config=config, storage=Storage())

    assert any("ControlBus disabled" in message for message in caplog.messages)
