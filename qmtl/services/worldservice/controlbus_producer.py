from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from typing import Any, Dict, Iterable

from qmtl.foundation.common.cloudevents import format_event
from qmtl.services.kafka import KafkaProducerLike, create_kafka_producer

from .controlbus_defaults import DEFAULT_CONTROLBUS_TOPIC


class ControlBusProducer:
    """Publish updates to the internal ControlBus."""

    def __init__(
        self,
        *,
        brokers: Iterable[str] | None = None,
        topic: str = DEFAULT_CONTROLBUS_TOPIC,
        producer: KafkaProducerLike | None = None,
        required: bool = False,
        retries: int = 2,
        backoff: float = 0.5,
        logger: logging.Logger | None = None,
    ) -> None:
        self.brokers = list(brokers or [])
        self.topic = topic
        self._producer: KafkaProducerLike | None = producer
        self._required = required
        self._retries = int(retries)
        self._backoff = float(backoff)
        self._logger = logger or logging.getLogger(__name__)

    async def start(self) -> None:
        if self._producer is not None:
            return
        if not self.brokers or not self.topic:
            self._handle_disabled("brokers/topics not configured")
            return
        producer = create_kafka_producer(self.brokers)
        if producer is None:
            self._handle_disabled("Kafka client not available for ControlBus")
            return
        self._producer = producer
        await producer.start()

    async def stop(self) -> None:
        producer = self._producer
        if producer is None:
            return
        with contextlib.suppress(Exception):  # pragma: no cover - best effort
            await producer.stop()
        self._producer = None

    async def _publish(
        self,
        event_type: str,
        world_id: str,
        payload: Dict[str, Any],
        *,
        correlation_id: str | None = None,
    ) -> None:
        producer = getattr(self, "_producer", None)
        if producer is None:
            return
        topic = getattr(self, "topic", "")
        if not topic:
            return
        event = format_event(
            "qmtl.services.worldservice",
            event_type,
            payload,
            correlation_id=correlation_id,
        )
        data = json.dumps(event).encode()
        key = world_id.encode()
        last_exc: Exception | None = None
        retries = int(getattr(self, "_retries", 0))
        backoff = float(getattr(self, "_backoff", 0.0))
        for attempt in range(retries + 1):
            try:
                await producer.send_and_wait(topic, data, key=key)
                return
            except Exception as exc:  # pragma: no cover - best-effort reliability
                last_exc = exc
                if attempt >= retries:
                    break
                await asyncio.sleep(backoff * (attempt + 1))
        if last_exc:
            raise last_exc

    def _handle_disabled(self, reason: str) -> None:
        if self._required:
            raise RuntimeError(f"ControlBus unavailable: {reason}")
        self._logger.warning("ControlBus disabled: %s", reason)

    async def publish_policy_update(
        self,
        world_id: str,
        policy_version: int,
        checksum: str,
        status: str,
        ts: str,
        *,
        version: int = 1,
    ) -> None:
        payload: Dict[str, Any] = {
            "world_id": world_id,
            "policy_version": policy_version,
            "checksum": checksum,
            "status": status,
            "ts": ts,
            "version": version,
        }
        await self._publish("policy_updated", world_id, payload)

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
        body: Dict[str, Any] = {
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
        await self._publish("activation_updated", world_id, body)

    async def publish_rebalancing_plan(
        self,
        world_id: str,
        plan: Dict[str, Any],
        *,
        version: int = 1,
        schema_version: int | None = None,
        alpha_metrics: Dict[str, Any] | None = None,
        rebalance_intent: Dict[str, Any] | None = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "world_id": world_id,
            "plan": plan,
            "version": version,
        }
        if schema_version is not None:
            payload["schema_version"] = schema_version
        if alpha_metrics is not None:
            payload["alpha_metrics"] = alpha_metrics
        if rebalance_intent is not None:
            payload["rebalance_intent"] = rebalance_intent
        await self._publish("rebalancing_planned", world_id, payload)

    async def publish_risk_snapshot_updated(
        self,
        world_id: str,
        snapshot: Dict[str, Any],
        *,
        version: int = 1,
    ) -> None:
        payload: Dict[str, Any] = dict(snapshot)
        payload["world_id"] = world_id
        payload.setdefault("event_version", version)
        await self._publish("risk_snapshot_updated", world_id, payload)

    async def publish_evaluation_run_created(
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
        payload: Dict[str, Any] = {
            "world_id": world_id,
            "strategy_id": strategy_id,
            "run_id": run_id,
            "stage": stage,
            "version": version,
            "idempotency_key": f"evaluation_run_created:{world_id}:{strategy_id}:{run_id}:{version}",
        }
        if risk_tier is not None:
            payload["risk_tier"] = risk_tier
        if status is not None:
            payload["status"] = status
        if recommended_stage is not None:
            payload["recommended_stage"] = recommended_stage
        correlation_id = f"evaluation_run:{world_id}:{strategy_id}:{run_id}"
        await self._publish(
            "evaluation_run_created",
            world_id,
            payload,
            correlation_id=correlation_id,
        )

    async def publish_evaluation_run_updated(
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
        payload: Dict[str, Any] = {
            "world_id": world_id,
            "strategy_id": strategy_id,
            "run_id": run_id,
            "stage": stage,
            "change_type": change_type,
            "version": version,
            "idempotency_key": f"evaluation_run_updated:{world_id}:{strategy_id}:{run_id}:{change_type}:{version}",
        }
        if risk_tier is not None:
            payload["risk_tier"] = risk_tier
        if status is not None:
            payload["status"] = status
        if recommended_stage is not None:
            payload["recommended_stage"] = recommended_stage
        correlation_id = f"evaluation_run:{world_id}:{strategy_id}:{run_id}"
        await self._publish(
            "evaluation_run_updated",
            world_id,
            payload,
            correlation_id=correlation_id,
        )

    async def publish_validation_profile_changed(
        self,
        world_id: str,
        *,
        policy_version: int,
        version: int = 1,
    ) -> None:
        payload: Dict[str, Any] = {
            "world_id": world_id,
            "policy_version": policy_version,
            "version": version,
            "idempotency_key": f"validation_profile_changed:{world_id}:{policy_version}:{version}",
        }
        correlation_id = f"validation_profile:{world_id}:{policy_version}"
        await self._publish(
            "validation_profile_changed",
            world_id,
            payload,
            correlation_id=correlation_id,
        )


__all__ = ["ControlBusProducer"]
