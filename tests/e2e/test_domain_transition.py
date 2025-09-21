from types import SimpleNamespace

import httpx
import pytest

from qmtl.common import ComputeContext, compute_compute_key
from qmtl.gateway.dagmanager_client import DagManagerClient
from qmtl.sdk.activation_manager import ActivationManager
from qmtl.sdk import metrics as sdk_metrics
from qmtl.sdk.node import ProcessingNode, StreamInput
from qmtl.sdk.runner import Runner
from qmtl.worldservice.api import create_app
from qmtl.worldservice.controlbus_producer import ControlBusProducer
from qmtl.worldservice.storage import Storage


class RecordingBus(ControlBusProducer):
    def __init__(self) -> None:
        super().__init__()
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
        payload = {
            "policy_version": policy_version,
            "checksum": checksum,
            "status": status,
            "ts": ts,
            "version": version,
        }
        self.events.append(("policy", world_id, payload))

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
        body = {
            "etag": etag,
            "run_id": run_id,
            "ts": ts,
            "state_hash": state_hash,
            "version": version,
        }
        if payload:
            body.update(payload)
        if requires_ack:
            body["requires_ack"] = True
        if sequence is not None:
            body["sequence"] = sequence
        self.events.append(("activation", world_id, body))


def _activation_events(bus: RecordingBus, *, world_id: str) -> list[dict]:
    return [
        payload
        for event, wid, payload in bus.events
        if event == "activation" and wid == world_id
    ]


@pytest.mark.asyncio
async def test_domain_promotion_flow_respects_freeze_and_isolation(monkeypatch):
    bus = RecordingBus()
    storage = Storage()
    app = create_app(bus=bus, storage=storage)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/worlds", json={"id": "w-domain", "name": "Domain"})
        await client.post(
            "/worlds/w-domain/policies",
            json={"policy": {"top_k": {"metric": "sharpe", "k": 1}}},
        )
        await client.post("/worlds/w-domain/set-default", json={"version": 1})

        activation_payload = {
            "strategy_id": "alpha",
            "side": "long",
            "active": True,
            "weight": 1.0,
            "effective_mode": "validate",
        }
        await client.put("/worlds/w-domain/activation", json=activation_payload)

        initial_evt = _activation_events(bus, world_id="w-domain")[-1]
        am = ActivationManager(world_id="w-domain", strategy_id="alpha")
        await am._on_message({"event": "activation_updated", "data": initial_evt})
        assert am.allow_side("long") is True
        assert am.state.effective_mode == "validate"

        sdk_metrics.reset_metrics()
        monkeypatch.setattr(Runner, "_ray_available", False)
        stream = StreamInput(interval="60s", period=1)
        node = ProcessingNode(
            input=stream,
            compute_fn=lambda _: None,
            name="node-alpha",
            interval="60s",
            period=1,
        )

        contexts: list[ComputeContext] = []
        keys: list[str] = []

        bt_context = ComputeContext(
            world_id="w-domain",
            execution_domain="backtest",
            as_of="ohlcv-2025-09-30",
        )
        contexts.append(bt_context)
        node.apply_compute_context(bt_context)
        Runner.feed_queue_data(node, "source", 60, 60, {"p": 1})
        assert node.cache.get_slice("source", 60, count=1) == [(60, {"p": 1})]
        keys.append(compute_compute_key(node.node_hash, bt_context))

        class _StubTagStub:
            async def GetQueues(self, request):  # type: ignore[override]
                return SimpleNamespace(
                    queues=[SimpleNamespace(**{"queue": "base", "global": False})]
                )

        monkeypatch.setenv("QMTL_ENABLE_TOPIC_NAMESPACE", "1")
        monkeypatch.setattr(
            DagManagerClient,
            "_ensure_channel",
            lambda self: setattr(self, "_tag_stub", _StubTagStub()),
        )

        dag_client = DagManagerClient("dummy")
        queues_bt = await dag_client.get_queues_by_tag(
            ["alpha"],
            60,
            world_id="w-domain",
            execution_domain="backtest",
        )
        assert queues_bt[0]["queue"] == "w-domain.backtest.base"

        bus.events.clear()
        payload = {
            "run_id": "promote-dryrun",
            "metrics": {"alpha": {"sharpe": 2.0}},
        }
        apply_resp = await client.post("/worlds/w-domain/apply", json=payload)
        assert apply_resp.status_code == 200
        stage_events = _activation_events(bus, world_id="w-domain")
        freeze_evt = next(evt for evt in stage_events if evt.get("phase") == "freeze")
        assert freeze_evt["freeze"] is True
        await am._on_message({"event": "activation_updated", "data": freeze_evt})
        assert am.allow_side("long") is False
        unfreeze_evt = next(
            evt for evt in stage_events if evt.get("phase") == "unfreeze"
        )
        assert unfreeze_evt["freeze"] is False
        await am._on_message({"event": "activation_updated", "data": unfreeze_evt})
        assert am.allow_side("long") is True

        dryrun_evt = {**unfreeze_evt, "effective_mode": "paper", "active": True}
        await am._on_message({"event": "activation_updated", "data": dryrun_evt})
        assert am.state.effective_mode == "paper"
        assert am.allow_side("long") is True

        dr_context = ComputeContext(
            world_id="w-domain",
            execution_domain="dryrun",
            as_of="ohlcv-2025-10-01",
        )
        contexts.append(dr_context)
        node.apply_compute_context(dr_context)
        assert node.cache.get_slice("source", 60, count=1) == []
        keys.append(compute_compute_key(node.node_hash, dr_context))

        queues_dr = await dag_client.get_queues_by_tag(
            ["alpha"],
            60,
            world_id="w-domain",
            execution_domain="dryrun",
        )
        assert queues_dr[0]["queue"] == "w-domain.dryrun.base"

        bus.events.clear()
        payload_live = {
            "run_id": "promote-live",
            "metrics": {"alpha": {"sharpe": 2.5}},
        }
        live_resp = await client.post("/worlds/w-domain/apply", json=payload_live)
        assert live_resp.status_code == 200
        live_events = _activation_events(bus, world_id="w-domain")
        freeze_live = next(evt for evt in live_events if evt.get("phase") == "freeze")
        await am._on_message({"event": "activation_updated", "data": freeze_live})
        assert am.allow_side("long") is False
        unfreeze_live = next(
            evt for evt in live_events if evt.get("phase") == "unfreeze"
        )
        await am._on_message({"event": "activation_updated", "data": unfreeze_live})
        assert am.allow_side("long") is True

        live_evt = {**unfreeze_live, "effective_mode": "live", "active": True}
        await am._on_message({"event": "activation_updated", "data": live_evt})
        assert am.state.effective_mode == "live"
        assert am.allow_side("long") is True

        live_context = ComputeContext(
            world_id="w-domain",
            execution_domain="live",
            as_of=None,
        )
        contexts.append(live_context)
        node.apply_compute_context(live_context)
        assert node.cache.get_slice("source", 60, count=1) == []
        keys.append(compute_compute_key(node.node_hash, live_context))

        queues_live = await dag_client.get_queues_by_tag(
            ["alpha"],
            60,
            world_id="w-domain",
            execution_domain="live",
        )
        assert queues_live[0]["queue"] == "w-domain.live.base"

        assert len({ctx.execution_domain for ctx in contexts}) == 3
        assert len(set(keys)) == 3

        await dag_client.close()

    await transport.aclose()


@pytest.mark.asyncio
async def test_apply_rollback_restores_state(monkeypatch):
    bus = RecordingBus()
    storage = Storage()
    app = create_app(bus=bus, storage=storage)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/worlds", json={"id": "w-rollback"})
        await client.post(
            "/worlds/w-rollback/policies",
            json={"policy": {"top_k": {"metric": "pnl", "k": 1}}},
        )
        await client.post("/worlds/w-rollback/set-default", json={"version": 1})

        base_activation = {
            "strategy_id": "beta",
            "side": "long",
            "active": True,
            "weight": 1.0,
        }
        await client.put("/worlds/w-rollback/activation", json=base_activation)

        original_set_decisions = storage.set_decisions
        calls = {"count": 0}

        async def fail_set_decisions(world_id: str, strategies: list[str]) -> None:
            if calls["count"] == 0:
                calls["count"] += 1
                raise RuntimeError("forced failure")
            await original_set_decisions(world_id, strategies)

        monkeypatch.setattr(storage, "set_decisions", fail_set_decisions)

        bus.events.clear()

        payload = {
            "run_id": "fail-run",
            "metrics": {"beta": {"pnl": 1.0}},
        }
        resp = await client.post("/worlds/w-rollback/apply", json=payload)
        assert resp.status_code == 500
        assert resp.json()["detail"] == "apply failed"

        audit = await client.get("/worlds/w-rollback/audit")
        stages = [
            entry["stage"]
            for entry in audit.json()
            if entry.get("event") == "apply_stage"
        ]
        assert stages == ["requested", "freeze", "rolled_back"]

        state = app.state.apply_runs["w-rollback"]
        assert state["stage"] == "rolled_back"
        assert state["completed"] is False

        activation_events = _activation_events(bus, world_id="w-rollback")
        assert activation_events
        assert any(evt.get("freeze") is True for evt in activation_events)

        reverted = await client.get(
            "/worlds/w-rollback/activation",
            params={"strategy_id": "beta", "side": "long"},
        )
        assert reverted.status_code == 200
        reverted_body = reverted.json()
        assert reverted_body["active"] is False
        assert reverted_body["freeze"] is True

        monkeypatch.setattr(storage, "set_decisions", original_set_decisions)

    await transport.aclose()
