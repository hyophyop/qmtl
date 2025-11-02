"""Tests for :mod:`qmtl.services.worldservice.activation`."""

from __future__ import annotations

import copy
import json
from typing import Any, Dict

import pytest

from qmtl.foundation.common.hashutils import hash_bytes
from qmtl.services.worldservice.activation import ActivationEventPublisher
from qmtl.services.worldservice.run_state import ApplyRunState


class _StubStore:
    def __init__(self, *, initial_state: Dict[str, Any] | None = None) -> None:
        self.full_state: Dict[str, Any] = (
            copy.deepcopy(initial_state) if initial_state is not None else {"state": {}}
        )
        self.updates: list[tuple[str, Dict[str, Any]]] = []
        self._version = 0

    async def update_activation(self, world_id: str, payload: Dict[str, Any]) -> tuple[int, Dict[str, Any]]:
        self.updates.append((world_id, copy.deepcopy(payload)))
        self._version += 1

        strategy_id = payload.get("strategy_id")
        side = payload.get("side")
        if strategy_id and side:
            state = self.full_state.setdefault("state", {})
            entry = state.setdefault(strategy_id, {}).setdefault(side, {})
            entry.update({k: v for k, v in payload.items() if k not in {"strategy_id", "side"}})

        data = {
            **payload,
            "etag": f"etag-{self._version}",
            "ts": f"2024-01-01T00:00:0{self._version}Z",
        }
        return self._version, data

    async def get_activation(self, world_id: str) -> Dict[str, Any]:
        return copy.deepcopy(self.full_state)


class _StubBus:
    def __init__(self) -> None:
        self.activation_updates: list[Dict[str, Any]] = []

    async def publish_activation_update(
        self,
        world_id: str,
        *,
        etag: str,
        run_id: str,
        ts: str,
        state_hash: str,
        payload: Dict[str, Any] | None = None,
        version: int = 1,
        requires_ack: bool = False,
        sequence: int | None = None,
    ) -> None:
        self.activation_updates.append(
            {
                "world_id": world_id,
                "etag": etag,
                "run_id": run_id,
                "ts": ts,
                "state_hash": state_hash,
                "payload": copy.deepcopy(payload) if payload is not None else None,
                "version": version,
                "requires_ack": requires_ack,
                "sequence": sequence,
            }
        )


@pytest.mark.asyncio
async def test_upsert_activation_emits_filtered_payload() -> None:
    store = _StubStore(
        initial_state={
            "state": {
                "alpha": {
                    "long": {"weight": 0.75, "effective_mode": "paper", "active": True}
                }
            }
        }
    )
    bus = _StubBus()
    publisher = ActivationEventPublisher(store, bus)

    payload = {"strategy_id": "alpha", "side": "long", "active": True, "run_id": "r1"}
    data = await publisher.upsert_activation("world-1", payload)

    assert data["etag"] == "etag-1"
    assert data["run_id"] == "r1"

    assert len(bus.activation_updates) == 1
    event = bus.activation_updates[0]
    assert event["world_id"] == "world-1"
    assert event["run_id"] == "r1"
    assert event["requires_ack"] is False
    assert event["sequence"] is None

    # Keys that are mirrored in structured parameters should not leak into the payload.
    assert event["payload"] == {"strategy_id": "alpha", "side": "long", "active": True}

    expected_hash = hash_bytes(json.dumps(store.full_state, sort_keys=True).encode())
    assert event["state_hash"] == expected_hash


@pytest.mark.asyncio
async def test_freeze_and_unfreeze_sequence_ack_flow() -> None:
    snapshot = {
        "state": {
            "alpha": {
                "long": {
                    "weight": 0.5,
                    "effective_mode": "live",
                    "active": True,
                }
            }
        }
    }
    store = _StubStore(initial_state=copy.deepcopy(snapshot))
    bus = _StubBus()
    publisher = ActivationEventPublisher(store, bus)
    run_state = ApplyRunState(run_id="run-42", active=["alpha"])

    await publisher.freeze_world("world-2", "run-42", snapshot, run_state)
    await publisher.unfreeze_world("world-2", "run-42", snapshot, run_state, ["alpha", "beta"])

    assert len(bus.activation_updates) == 3

    freeze_event = bus.activation_updates[0]
    assert freeze_event["requires_ack"] is True
    assert freeze_event["run_id"] == "run-42"
    assert freeze_event["sequence"] == 1
    assert freeze_event["payload"] == {
        "strategy_id": "alpha",
        "side": "long",
        "active": False,
        "weight": 0.5,
        "freeze": True,
        "drain": True,
        "effective_mode": "live",
        "phase": "freeze",
    }

    first_unfreeze = bus.activation_updates[1]
    assert first_unfreeze["run_id"] == "run-42"
    assert first_unfreeze["sequence"] == 2
    assert first_unfreeze["payload"] == {
        "strategy_id": "alpha",
        "side": "long",
        "active": True,
        "weight": 0.5,
        "freeze": False,
        "drain": False,
        "effective_mode": "live",
        "phase": "unfreeze",
    }

    second_unfreeze = bus.activation_updates[2]
    assert second_unfreeze["run_id"] == "run-42"
    assert second_unfreeze["sequence"] == 3
    assert second_unfreeze["payload"] == {
        "strategy_id": "beta",
        "side": "long",
        "active": True,
        "weight": 1.0,
        "freeze": False,
        "drain": False,
        "phase": "unfreeze",
    }

