import httpx
import pytest

from qmtl.runtime.sdk.activation_manager import ActivationManager
from qmtl.services.exit_engine.activation_client import WorldServiceActivationClient
from qmtl.services.exit_engine.config import ExitEngineConfig
from qmtl.services.exit_engine.controlbus_consumer import ExitEngineControlBusConsumer
from qmtl.services.worldservice.api import create_app
from qmtl.services.worldservice.controlbus_producer import ControlBusProducer
from qmtl.services.worldservice.storage import Storage


class RecordingBus(ControlBusProducer):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict] = []

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
            "world_id": world_id,
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
        self.events.append(body)


class _Message:
    def __init__(self, value: dict) -> None:
        self.value = value


@pytest.mark.asyncio
async def test_exit_engine_freeze_turns_off_order_gate():
    bus = RecordingBus()
    storage = Storage()
    app = create_app(bus=bus, storage=storage)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        world_id = "w-exit"
        await client.post("/worlds", json={"id": world_id, "name": "Exit World"})
        await client.put(
            f"/worlds/{world_id}/activation",
            json={
                "strategy_id": "alpha",
                "side": "long",
                "active": True,
                "weight": 1.0,
            },
        )
        bus.events.clear()

        activation_client = WorldServiceActivationClient("http://test", client=client)
        config = ExitEngineConfig(
            ws_base_url="http://test",
            freeze_world_ids={world_id},
            drain_world_ids=set(),
            strategy_id="alpha",
            side="long",
        )
        consumer = ExitEngineControlBusConsumer(
            config=config,
            activation_client=activation_client,
            brokers=[],
            topic="",
        )

        snapshot = {
            "world_id": world_id,
            "as_of": "2025-01-01T00:00:00Z",
            "version": "risk-1",
            "run_id": "exit-run",
            "weights": {"alpha": 1.0},
            "provenance": {"actor": "risk-hub", "stage": "exit"},
        }
        message = _Message(
            {
                "type": "risk_snapshot_updated",
                "data": snapshot,
                "correlation_id": "req-exit-1",
            }
        )

        await consumer._handle_message(message)

        assert bus.events, "exit engine should publish activation updates"
        event = bus.events[-1]
        assert event["world_id"] == world_id
        assert event["run_id"] == "exit-run"
        assert event["etag"]
        assert event["state_hash"]
        assert event["strategy_id"] == "alpha"
        assert event["side"] == "long"
        assert event["active"] is False
        assert event["freeze"] is True
        assert event["drain"] is True
        assert event["weight"] == 0.0

        manager = ActivationManager(world_id=world_id, strategy_id="alpha")
        await manager._on_message({"event": "activation_updated", "data": event})

        assert manager.allow_side("long") is False
        assert manager.allow_side("short") is False
        assert manager.state.run_id == "exit-run"
        assert manager.state.etag == event["etag"]
        assert manager.state.state_hash == event["state_hash"]

    await transport.aclose()
