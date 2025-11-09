from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from pydantic import ValidationError
from qmtl.foundation.common.tagquery import MatchMode

from .ws import WebSocketHub
from . import metrics as gw_metrics
from .controlbus_codec import decode as decode_cb, PROTO_CONTENT_TYPE
from .event_models import RebalancingPlannedData, SentinelWeightData

logger = logging.getLogger(__name__)


class RebalancingExecutionPolicy(Protocol):
    async def should_execute(self, event: RebalancingPlannedData) -> bool:
        ...

    async def execute(self, event: RebalancingPlannedData) -> None:
        ...


@dataclass
class ControlBusMessage:
    """Represents a message delivered from the ControlBus."""

    topic: str
    key: str
    etag: str
    run_id: str
    data: dict[str, Any]
    timestamp_ms: Optional[float] = None


class ControlBusConsumer:
    """Consume ControlBus events and relay them to WebSocket clients."""

    def __init__(
        self,
        brokers: list[str] | None,
        topics: list[str],
        group: str,
        *,
        ws_hub: WebSocketHub | None = None,
        rebalancing_policy: RebalancingExecutionPolicy | None = None,
    ) -> None:
        self.brokers = brokers or []
        self.topics = topics
        self.group = group
        self.ws_hub = ws_hub
        self._rebalancing_policy = rebalancing_policy
        self._queue: asyncio.Queue[ControlBusMessage | None] = asyncio.Queue()
        self._task: asyncio.Task | None = None
        self._broker_task: asyncio.Task | None = None
        self._consumer: Any | None = None
        self._last_seen: dict[tuple[str, str], tuple[Any, ...]] = {}
        # Track discovered tag+interval combinations to emit upsert events
        self._known_tag_intervals: set[tuple[tuple[str, ...], int]] = set()

    async def start(self) -> None:
        """Start the background consumer task."""
        if self._task is None:
            self._task = asyncio.create_task(self._worker())
        if self.brokers and self.topics and self._broker_task is None:
            self._broker_task = asyncio.create_task(self._broker_loop())

    async def stop(self) -> None:
        """Stop the background consumer task."""
        if self._broker_task is not None:
            self._broker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._broker_task
            self._broker_task = None
        if self._consumer is not None:
            with contextlib.suppress(Exception):
                await self._consumer.stop()
            self._consumer = None
        await self._queue.put(None)
        if self._task is not None:
            await self._task
            self._task = None

    async def publish(self, message: ControlBusMessage) -> None:
        """Submit a ControlBus message for processing."""
        await self._queue.put(message)

    async def _worker(self) -> None:
        while True:
            msg = await self._queue.get()
            if msg is None:
                break
            try:
                await self._handle_message(msg)
            finally:
                self._queue.task_done()

    async def _broker_ready(self) -> bool:
        """Return ``True`` if brokers are reachable."""
        try:  # pragma: no cover - aiokafka optional
            from aiokafka import AIOKafkaConsumer

            consumer = AIOKafkaConsumer(
                bootstrap_servers=self.brokers,
                group_id=self.group,
                enable_auto_commit=False,
            )
            await consumer.start()
            await consumer.stop()
            return True
        except Exception:
            return False

    async def _wait_for_broker(self, timeout: float = 60.0) -> None:
        """Poll brokers until they become reachable or ``timeout`` expires."""
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            if await self._broker_ready():
                return
            if asyncio.get_running_loop().time() > deadline:
                raise RuntimeError("brokers unavailable")
            await asyncio.sleep(1.0)

    async def _broker_loop(self) -> None:
        try:
            from aiokafka import AIOKafkaConsumer
        except Exception:  # pragma: no cover - dependency optional
            logger.error("aiokafka is required for broker consumption")
            return

        while True:
            try:
                self._consumer = AIOKafkaConsumer(
                    *self.topics,
                    bootstrap_servers=self.brokers,
                    group_id=self.group,
                    enable_auto_commit=False,
                )
                await self._consumer.start()
                while True:
                    msg = await self._consumer.getone()
                    try:
                        cb_msg = self._parse_kafka_message(msg)
                        await self._handle_message(cb_msg)
                        await self._consumer.commit()
                    except Exception as exc:  # pragma: no cover - robustness
                        logger.exception("Error handling ControlBus message: %s", exc)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # pragma: no cover - connection issues
                logger.warning("ControlBus consumer error: %s", exc)
                with contextlib.suppress(Exception):
                    if self._consumer:
                        await self._consumer.stop()
                self._consumer = None
                try:
                    await self._wait_for_broker()
                except Exception:
                    break
            finally:
                if self._consumer is not None:
                    with contextlib.suppress(Exception):
                        await self._consumer.stop()
                    self._consumer = None

    def _parse_kafka_message(self, message: Any) -> ControlBusMessage:
        key = message.key.decode() if message.key else ""
        headers = {k: (v.decode() if isinstance(v, bytes) else v) for k, v in (message.headers or [])}
        content_type = headers.get("content_type")
        data: dict[str, Any]
        if content_type == PROTO_CONTENT_TYPE:
            # Placeholder proto path: decode via helper (still JSON today)
            event = decode_cb(
                message.value if isinstance(message.value, (bytes, bytearray)) else str(message.value).encode()
            )
        else:
            try:
                event = (
                    json.loads(message.value.decode())
                    if isinstance(message.value, (bytes, bytearray))
                    else json.loads(message.value)
                )
            except Exception:  # pragma: no cover - malformed message
                event = {}
        if not isinstance(event, dict):
            data = {}
        elif content_type == PROTO_CONTENT_TYPE:
            # For proto placeholder, keep full event as data for downstream consumers
            data = event
        else:
            # For JSON, prefer nested payload when present; otherwise pass through
            data = event.get("data", event)
        etag = (data.get("etag") or headers.get("etag") or "")
        run_id = (data.get("run_id") or headers.get("run_id") or "")
        timestamp_ms = getattr(message, "timestamp", None)
        return ControlBusMessage(
            topic=message.topic,
            key=key,
            etag=etag,
            run_id=run_id,
            data=data,
            timestamp_ms=timestamp_ms,
        )

    def _marker_for_plan(self, payload: RebalancingPlannedData) -> tuple[Any, ...]:
        serialized = json.dumps(
            payload.plan.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(serialized.encode()).hexdigest()
        marker = payload.run_id or digest
        return (payload.version, marker, digest)

    async def _handle_message(self, msg: ControlBusMessage) -> None:
        key = (msg.topic, msg.key)
        if msg.topic == "rebalancing_planned":
            try:
                payload = RebalancingPlannedData.model_validate(msg.data)
            except ValidationError as exc:
                logger.warning("invalid rebalancing_planned payload: %s", exc)
                return

            marker = self._marker_for_plan(payload)
            if self._last_seen.get(key) == marker:
                gw_metrics.record_event_dropped(msg.topic)
                return
            self._last_seen[key] = marker

            gw_metrics.record_controlbus_message(msg.topic, msg.timestamp_ms)
            gw_metrics.record_rebalance_plan(
                payload.world_id, len(payload.plan.deltas)
            )

            if self.ws_hub:
                await self.ws_hub.send_rebalancing_planned(
                    world_id=payload.world_id,
                    plan=payload.plan.model_dump(mode="json"),
                    version=payload.version,
                    policy=payload.policy,
                    run_id=payload.run_id,
                )

            if self._rebalancing_policy is not None:
                try:
                    should_execute = await self._rebalancing_policy.should_execute(
                        payload
                    )
                except Exception:
                    logger.exception(
                        "Failed to evaluate rebalancing execution policy",
                        extra={"world_id": payload.world_id},
                    )
                else:
                    if should_execute:
                        try:
                            await self._rebalancing_policy.execute(payload)
                        except Exception:
                            gw_metrics.record_rebalance_plan_execution(
                                payload.world_id, success=False
                            )
                            logger.exception(
                                "Failed to execute rebalancing plan",
                                extra={"world_id": payload.world_id},
                            )
                        else:
                            gw_metrics.record_rebalance_plan_execution(
                                payload.world_id, success=True
                            )
            return

        if msg.topic == "sentinel_weight":
            try:
                payload = SentinelWeightData.model_validate(msg.data)
            except ValidationError as exc:
                logger.warning("invalid sentinel_weight payload: %s", exc)
                return
            marker = (payload.sentinel_id, payload.weight, payload.version)
            if self._last_seen.get(key) == marker:
                gw_metrics.record_event_dropped(msg.topic)
                return
            self._last_seen[key] = marker

            gw_metrics.record_controlbus_message(msg.topic, msg.timestamp_ms)

            sentinel_id = payload.sentinel_id
            weight = float(payload.weight)
            try:
                gw_metrics.record_sentinel_weight_update(sentinel_id)
                gw_metrics.set_sentinel_traffic_ratio(sentinel_id, weight)
            except Exception:
                logger.exception("failed to update sentinel weight metrics", exc_info=True)
            if self.ws_hub:
                await self.ws_hub.send_sentinel_weight(sentinel_id, weight)
            return

        if msg.topic == "policy":
            marker = (msg.data.get("checksum"), msg.data.get("policy_version"))
        else:
            marker = (msg.etag, msg.run_id)

        if self._last_seen.get(key) == marker:
            gw_metrics.record_event_dropped(msg.topic)
            return
        self._last_seen[key] = marker

        gw_metrics.record_controlbus_message(msg.topic, msg.timestamp_ms)

        if not self.ws_hub:
            return

        version = msg.data.get("version")
        if version != 1:
            logger.warning("unsupported controlbus message version: %s", version)
            return

        if msg.topic == "activation":
            await self.ws_hub.send_activation_updated(msg.data)
        elif msg.topic == "policy":
            await self.ws_hub.send_policy_updated(msg.data)
        elif msg.topic == "queue":
            tags = msg.data.get("tags", [])
            interval = msg.data.get("interval", 0)
            queues = msg.data.get("queues", [])
            match_mode = msg.data.get("match_mode", MatchMode.ANY.value)
            etag = msg.data.get("etag", msg.etag)
            ts = msg.data.get("ts")
            try:
                mode = MatchMode(match_mode)
            except ValueError:
                mode = MatchMode.ANY
            await self.ws_hub.send_queue_update(tags, interval, queues, mode, etag=etag, ts=ts)
            key = (tuple(sorted(tags)), int(interval))
            if key not in self._known_tag_intervals:
                self._known_tag_intervals.add(key)
                await self.ws_hub.send_tagquery_upsert(tags, interval, queues)
        else:
            logger.warning("Unhandled ControlBus topic %s", msg.topic)


__all__ = [
    "ControlBusConsumer",
    "ControlBusMessage",
    "RebalancingExecutionPolicy",
]
