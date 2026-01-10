"""Activation event orchestration for apply flows."""

from __future__ import annotations

import json
from datetime import datetime, timezone
import logging
from typing import Any, Dict, Sequence

from qmtl.foundation.common.hashutils import hash_bytes
from qmtl.services.observability import add_span_attributes, build_observability_fields

from .controlbus_producer import ControlBusProducer
from .run_state import ApplyRunState
from .storage import Storage
from .risk_hub import PortfolioSnapshot, RiskSignalHub

logger = logging.getLogger(__name__)


class ActivationEventPublisher:
    """Publish activation mutations to storage and the control bus."""

    def __init__(
        self,
        store: Storage,
        bus: ControlBusProducer | None,
        *,
        risk_hub: RiskSignalHub | None = None,
    ) -> None:
        self.store = store
        self.bus = bus
        self.risk_hub = risk_hub

    async def upsert_activation(
        self, world_id: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        version, data = await self.store.update_activation(
            world_id, payload
        )
        if self.bus:
            full_state = await self.store.get_activation(world_id)
            state_payload = json.dumps(full_state, sort_keys=True).encode()
            state_hash = hash_bytes(state_payload)
            event_payload = {
                key: val
                for key, val in {
                    **data,
                    "strategy_id": payload.get("strategy_id")
                    or data.get("strategy_id"),
                    "side": payload.get("side") or data.get("side"),
                }.items()
                if key not in {"etag", "run_id", "ts"} and val is not None
            }
            await self.bus.publish_activation_update(
                world_id,
                etag=data.get("etag", str(version)),
                run_id=str(data.get("run_id") or ""),
                ts=str(data.get("ts")),
                state_hash=state_hash,
                payload=event_payload,
                version=version,
            )
            fields = build_observability_fields(
                world_id=world_id,
                strategy_id=event_payload.get("strategy_id"),
                run_id=data.get("run_id"),
                etag=data.get("etag", str(version)),
            )
            add_span_attributes(fields)
            if fields:
                logger.info("activation_update_published", extra=fields)
        ts = str(data.get("ts") or "")
        await self._publish_snapshot(world_id, version_hint=f"{ts}-{version}" if ts else str(version))
        return data

    async def update_activation_state(
        self,
        world_id: str,
        payload: Dict[str, Any],
        *,
        phase: str | None = None,
        requires_ack: bool = False,
        sequence: int | None = None,
    ) -> Dict[str, Any]:
        version, data = await self.store.update_activation(world_id, payload)
        if self.bus:
            full_state = await self.store.get_activation(world_id)
            state_payload = json.dumps(full_state, sort_keys=True).encode()
            state_hash = hash_bytes(state_payload)
            event_payload = {
                key: val
                for key, val in {
                    **data,
                    "strategy_id": payload["strategy_id"],
                    "side": payload["side"],
                    "phase": phase,
                }.items()
                if key not in {"etag", "run_id", "ts"} and val is not None
            }
            await self.bus.publish_activation_update(
                world_id,
                etag=data.get("etag", str(version)),
                run_id=str(data.get("run_id") or ""),
                ts=str(data.get("ts")),
                state_hash=state_hash,
                payload=event_payload,
                version=version,
                requires_ack=requires_ack,
                sequence=sequence,
            )
            fields = build_observability_fields(
                world_id=world_id,
                strategy_id=event_payload.get("strategy_id"),
                run_id=data.get("run_id"),
                etag=data.get("etag", str(version)),
            )
            add_span_attributes(fields)
            if fields:
                logger.info("activation_state_update_published", extra=fields)
        ts = str(data.get("ts") or "")
        await self._publish_snapshot(world_id, version_hint=f"{ts}-{version}" if ts else str(version))
        return data

    async def freeze_world(
        self,
        world_id: str,
        run_id: str,
        snapshot: Dict[str, Any],
        run_state: ApplyRunState,
    ) -> None:
        state = snapshot.get("state", {})
        if not state:
            return
        for strategy_id, sides in state.items():
            for side, entry in sides.items():
                payload = {
                    "strategy_id": strategy_id,
                    "side": side,
                    "active": False,
                    "weight": entry.get("weight", 0.0),
                    "freeze": True,
                    "drain": True,
                    "effective_mode": entry.get("effective_mode"),
                    "run_id": run_id,
                }
                sequence = run_state.next_sequence()
                await self.update_activation_state(
                    world_id,
                    payload,
                    phase="freeze",
                    requires_ack=True,
                    sequence=sequence,
                )

    async def unfreeze_world(
        self,
        world_id: str,
        run_id: str,
        snapshot: Dict[str, Any],
        run_state: ApplyRunState,
        target_active: Sequence[str],
    ) -> None:
        state = snapshot.get("state", {})
        active_set = set(target_active)
        seen: set[tuple[str, str]] = set()
        for strategy_id, sides in state.items():
            for side, entry in sides.items():
                seen.add((strategy_id, side))
                active_flag = strategy_id in active_set
                payload = {
                    "strategy_id": strategy_id,
                    "side": side,
                    "active": active_flag,
                    "weight": entry.get("weight", 1.0 if active_flag else 0.0),
                    "freeze": False,
                    "drain": False,
                    "effective_mode": entry.get("effective_mode"),
                    "run_id": run_id,
                }
                sequence = run_state.next_sequence()
                await self.update_activation_state(
                    world_id,
                    payload,
                    phase="unfreeze",
                    requires_ack=True,
                    sequence=sequence,
                )

        for strategy_id in active_set:
            if all(strategy_id != sid for sid, _ in seen):
                sequence = run_state.next_sequence()
                await self.update_activation_state(
                    world_id,
                    {
                        "strategy_id": strategy_id,
                        "side": "long",
                        "active": True,
                        "weight": 1.0,
                        "freeze": False,
                        "drain": False,
                        "run_id": run_id,
                    },
                    phase="unfreeze",
                    requires_ack=True,
                    sequence=sequence,
                )

    async def _publish_snapshot(self, world_id: str, version_hint: str | None = None) -> None:
        if self.risk_hub is None:
            return
        try:
            decisions = await self.store.get_decisions(world_id)
        except Exception:
            decisions = []
        if not decisions:
            return
        try:
            snapshot = await self.store.snapshot_activation(world_id)
        except Exception:
            return
        weights: Dict[str, float] = {}
        for sid, sides in (snapshot.state or {}).items():
            for entry in sides.values():
                if entry.get("active"):
                    weights[sid] = weights.get(sid, 0.0) + float(entry.get("weight", 1.0))
        total = sum(weights.values())
        if total <= 0:
            return
        normalized = {sid: val / total for sid, val in weights.items()}
        ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        snap = PortfolioSnapshot(
            world_id=world_id,
            as_of=ts,
            version=str(version_hint or ts),
            weights=normalized,
            provenance={
                "source": "worldservice",
                "reason": "activation_update",
                "actor": "worldservice",
                "stage": "live",
            },
        )
        await self.risk_hub.upsert_snapshot(snap)
        if self.bus:
            try:
                await self.bus.publish_risk_snapshot_updated(world_id, snap.to_dict())
            except Exception:
                pass


__all__ = ["ActivationEventPublisher"]
