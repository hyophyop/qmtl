from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import pytest

from qmtl.gateway.dagmanager_client import DagManagerClient
from qmtl.sdk.activation_manager import ActivationManager
from qmtl.worldservice.api import create_app
from qmtl.worldservice.controlbus_producer import ControlBusProducer
from qmtl.worldservice.storage import Storage


class _RecordingBus(ControlBusProducer):
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict]] = []

    async def publish_activation_update(  # type: ignore[override]
        self,
        world_id: str,
        *,
        etag: str,
        run_id: str,
        ts: str,
        state_hash: str,
        payload: dict | None = None,
        version: int = 1,
    ) -> None:
        body = {**(payload or {}), "etag": etag, "run_id": run_id, "ts": ts, "state_hash": state_hash, "version": version}
        self.events.append(("activation", world_id, body))

    async def publish_policy_update(  # type: ignore[override]
        self,
        world_id: str,
        policy_version: int,
        checksum: str,
        status: str,
        ts: str,
        *,
        version: int = 1,
    ) -> None:
        self.events.append(
            (
                "policy",
                world_id,
                {"policy_version": policy_version, "checksum": checksum, "status": status, "ts": ts, "version": version},
            )
        )


async def _activation_events(bus: _RecordingBus) -> list[dict]:
    return [evt for topic, _, evt in bus.events if topic == "activation"]


@pytest.mark.asyncio
async def test_domain_promotion_freeze_switch_unfreeze_and_rollback():
    bus = _RecordingBus()
    store = Storage()
    app = create_app(bus=bus, storage=store)

    async with httpx.ASGITransport(app=app) as asgi:
        async with httpx.AsyncClient(transport=asgi, base_url="http://test") as client:
            await client.post("/worlds", json={"id": "w-domain"})
            await client.post("/worlds/w-domain/decisions", json={"strategies": ["strat-a"]})
            await client.put(
                "/worlds/w-domain/activation",
                json={"strategy_id": "strat-a", "side": "long", "active": True, "weight": 1.0, "effective_mode": "compute-only"},
            )

            activation_history = list(await _activation_events(bus))
            bus.events.clear()

            # Freeze to begin dryrun promotion
            freeze_payload = {"transition": {"run_id": "run-1", "target": "dryrun", "phase": "freeze"}}
            resp = await client.post("/worlds/w-domain/apply", json=freeze_payload)
            data = resp.json()
            assert data["domain"]["phase"] == "freeze"
            assert data["domain"]["pending"] == "dryrun"
            assert data["domain"]["freeze"] is True
            activation_history.extend(await _activation_events(bus))
            freeze_evt = activation_history[-1]
            assert freeze_evt["freeze"] is True and freeze_evt["drain"] is True
            assert freeze_evt["effective_mode"] == "compute-only"
            bus.events.clear()

            # Switch into dryrun domain while remaining frozen
            switch_payload = {"transition": {"run_id": "run-1", "phase": "switch"}}
            resp = await client.post("/worlds/w-domain/apply", json=switch_payload)
            data = resp.json()
            assert data["domain"]["current"] == "dryrun"
            assert data["domain"]["freeze"] is True
            activation_history.extend(await _activation_events(bus))
            bus.events.clear()

            # Unfreeze to resume in dryrun domain
            unfreeze_payload = {"transition": {"run_id": "run-1", "phase": "unfreeze"}}
            resp = await client.post("/worlds/w-domain/apply", json=unfreeze_payload)
            data = resp.json()
            assert data["domain"]["current"] == "dryrun"
            assert data["domain"]["freeze"] is False
            activation_history.extend(await _activation_events(bus))
            dryrun_evt = activation_history[-1]
            assert dryrun_evt["freeze"] is False and dryrun_evt["effective_mode"] == "paper"
            bus.events.clear()

            # Promote from dryrun to live
            await client.post("/worlds/w-domain/apply", json={"transition": {"run_id": "run-2", "target": "live", "phase": "freeze"}})
            activation_history.extend(await _activation_events(bus))
            bus.events.clear()
            await client.post("/worlds/w-domain/apply", json={"transition": {"run_id": "run-2", "phase": "switch"}})
            activation_history.extend(await _activation_events(bus))
            bus.events.clear()
            resp = await client.post("/worlds/w-domain/apply", json={"transition": {"run_id": "run-2", "phase": "unfreeze"}})
            data = resp.json()
            assert data["domain"]["current"] == "live"
            assert data["domain"]["freeze"] is False
            activation_history.extend(await _activation_events(bus))
            live_evt = activation_history[-1]
            assert live_evt["effective_mode"] == "live"
            bus.events.clear()

            # Roll back to dryrun domain
            resp = await client.post(
                "/worlds/w-domain/apply",
                json={"transition": {"run_id": "rollback-1", "phase": "rollback", "target": "dryrun"}},
            )
            data = resp.json()
            assert data["domain"]["current"] == "dryrun"
            assert data["domain"]["freeze"] is False
            activation_history.extend(await _activation_events(bus))
            rollback_evt = activation_history[-1]
            assert rollback_evt["effective_mode"] == "paper"

            # Activation manager observes freeze/unfreeze phases
            am = ActivationManager(world_id="w-domain", strategy_id="strat-a")
            for evt in activation_history:
                await am._on_message({"event": "activation_updated", "data": evt})
            assert am.allow_side("long") is True
            await am.stop()

            audit = await store.get_audit("w-domain")
            domain_events = [entry for entry in audit if entry.get("event") == "domain_transition"]
            phases = [entry["phase"] for entry in domain_events]
            assert phases.count("freeze") >= 2
            assert phases[-1] == "rollback"


@pytest.mark.asyncio
async def test_domain_queue_isolation(monkeypatch):
    client = DagManagerClient("dummy")

    class _StubDiff:
        async def Diff(self, request):
            yield SimpleNamespace(queue_map={"node:0": "base"}, sentinel_id="sent", buffer_nodes=[], version="v1")

        async def AckChunk(self, _):
            return None

    class _StubTag:
        async def GetQueues(self, request):
            return SimpleNamespace(queues=[SimpleNamespace(**{"queue": "base", "global": False})])

    def fake_ensure(self):
        self._diff_stub = _StubDiff()
        self._tag_stub = _StubTag()

    monkeypatch.setattr(DagManagerClient, "_ensure_channel", fake_ensure, raising=False)

    chunk_bt = await client.diff("sid", json.dumps({}), world_id="w", execution_domain="backtest")
    chunk_live = await client.diff("sid", json.dumps({}), world_id="w", execution_domain="live")

    assert chunk_bt is not None and chunk_live is not None
    assert chunk_bt.queue_map["node:0"] == "w/w/backtest/base"
    assert chunk_live.queue_map["node:0"] == "w/w/live/base"

    queues_bt = await client.get_queues_by_tag(["t"], 60, world_id="w", execution_domain="backtest")
    queues_live = await client.get_queues_by_tag(["t"], 60, world_id="w", execution_domain="live")

    assert queues_bt[0]["queue"] == "w/w/backtest/base"
    assert queues_live[0]["queue"] == "w/w/live/base"
    assert queues_bt[0]["queue"] != queues_live[0]["queue"]

    await client.close()
