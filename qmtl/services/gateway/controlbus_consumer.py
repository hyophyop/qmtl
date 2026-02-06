from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import typing
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from pydantic import ValidationError
from qmtl.foundation.common.tagquery import MatchMode

from qmtl.services.observability import add_span_attributes, build_observability_fields
from .ws import WebSocketHub
from . import metrics as gw_metrics
from .controlbus_codec import decode as decode_cb, PROTO_CONTENT_TYPE
from .event_models import RebalancingPlannedData, SentinelWeightData
from .controlbus_ack import ActivationAckProducer

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


@dataclass
class _ActivationSequenceState:
    next_sequence: int
    buffered: dict[int, ControlBusMessage]
    gap_timeout_task: asyncio.Task[None] | None = None
    gap_timeout_token: int = 0


@dataclass(frozen=True)
class _ActivationGapTimeout:
    sequence_key: tuple[str, str]
    token: int


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
        ack_producer: ActivationAckProducer | None = None,
        activation_gap_timeout_ms: int = 3000,
    ) -> None:
        self.brokers = brokers or []
        self.topics = topics
        self.group = group
        self.ws_hub = ws_hub
        self._rebalancing_policy = rebalancing_policy
        self._ack_producer = ack_producer
        self._queue: asyncio.Queue[ControlBusMessage | _ActivationGapTimeout | None] = (
            asyncio.Queue()
        )
        self._task: asyncio.Task | None = None
        self._broker_task: asyncio.Task | None = None
        self._consumer: Any | None = None
        self._last_seen: dict[tuple[str, str], tuple[Any, ...]] = {}
        self._activation_sequence_states: dict[tuple[str, str], _ActivationSequenceState] = {}
        self._activation_gap_timeout_seconds = max(
            float(activation_gap_timeout_ms) / 1000.0, 0.001
        )
        # Track discovered tag+interval combinations to emit upsert events
        self._known_tag_intervals: set[tuple[tuple[str, ...], int, str]] = set()

    async def start(self) -> None:
        """Start the background consumer task."""
        if self._ack_producer is not None:
            await self._ack_producer.start()
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
        self._cancel_all_activation_gap_timeouts()
        if self._ack_producer is not None:
            with contextlib.suppress(Exception):
                await self._ack_producer.stop()
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
                if isinstance(msg, _ActivationGapTimeout):
                    await self._handle_activation_gap_timeout(msg)
                    continue
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
        headers = self._decode_headers(message.headers)
        event = self._decode_event(message.value, headers.get("content_type"))
        data = self._extract_data(event, headers.get("content_type"))
        etag = (data.get("etag") or headers.get("etag") or "")
        run_id = (data.get("run_id") or headers.get("run_id") or "")
        timestamp_ms = getattr(message, "timestamp", None)
        return ControlBusMessage(
            topic=message.topic,
            key=self._decode_key(message.key),
            etag=etag,
            run_id=run_id,
            data=data,
            timestamp_ms=timestamp_ms,
        )

    @staticmethod
    def _decode_key(raw_key: Any) -> str:
        if not raw_key:
            return ""
        return raw_key.decode() if isinstance(raw_key, (bytes, bytearray)) else str(raw_key)

    @staticmethod
    def _decode_headers(raw_headers: Any) -> dict[str, Any]:
        return {
            key: (value.decode() if isinstance(value, (bytes, bytearray)) else value)
            for key, value in (raw_headers or [])
        }

    @staticmethod
    def _decode_event(raw_value: Any, content_type: str | None) -> dict[str, Any]:
        if content_type == PROTO_CONTENT_TYPE:
            payload = raw_value if isinstance(raw_value, (bytes, bytearray)) else str(raw_value).encode()
            return decode_cb(payload)

        try:
            if isinstance(raw_value, (bytes, bytearray)):
                return typing.cast(dict[str, Any], json.loads(raw_value.decode()))
            return typing.cast(dict[str, Any], json.loads(raw_value))
        except Exception:  # pragma: no cover - malformed message
            return {}

    @staticmethod
    def _extract_data(event: dict[str, Any], content_type: str | None) -> dict[str, Any]:
        if content_type == PROTO_CONTENT_TYPE:
            return event
        nested = event.get("data", event)
        return nested if isinstance(nested, dict) else event

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
        if msg.topic == "rebalancing_planned":
            await self._process_rebalancing_planned(msg)
            return

        if msg.topic == "sentinel_weight":
            await self._process_sentinel_weight(msg)
            return

        await self._process_generic_message(msg)

    async def _process_rebalancing_planned(self, msg: ControlBusMessage) -> None:
        key = (msg.topic, msg.key)
        try:
            payload = RebalancingPlannedData.model_validate(msg.data)
        except ValidationError as exc:
            logger.warning("invalid rebalancing_planned payload: %s", exc)
            return

        marker = self._marker_for_plan(payload)
        if not self._track_delivery(key, marker, msg.topic):
            return

        fields = build_observability_fields(
            world_id=payload.world_id,
            run_id=payload.run_id,
        )
        add_span_attributes(fields)
        if fields:
            logger.info("rebalancing_planned_received", extra=fields)

        gw_metrics.record_controlbus_message(msg.topic, msg.timestamp_ms)
        gw_metrics.record_rebalance_plan(
            payload.world_id, len(payload.plan.deltas)
        )

        await self._notify_rebalancing(payload)
        await self._maybe_execute_rebalance(payload)

    async def _notify_rebalancing(self, payload: RebalancingPlannedData) -> None:
        if not self.ws_hub:
            return
        await self.ws_hub.send_rebalancing_planned(
            world_id=payload.world_id,
            plan=payload.plan.model_dump(mode="json"),
            version=payload.version,
            policy=payload.policy,
            run_id=payload.run_id,
            schema_version=payload.schema_version,
            alpha_metrics=payload.alpha_metrics,
            rebalance_intent=payload.rebalance_intent,
        )

    async def _maybe_execute_rebalance(
        self, payload: RebalancingPlannedData
    ) -> None:
        if self._rebalancing_policy is None:
            return
        try:
            should_execute = await self._rebalancing_policy.should_execute(payload)
        except Exception:
            logger.exception(
                "Failed to evaluate rebalancing execution policy",
                extra={"world_id": payload.world_id},
            )
            return

        if not should_execute:
            return

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

    async def _process_sentinel_weight(self, msg: ControlBusMessage) -> None:
        key = (msg.topic, msg.key)
        try:
            payload = SentinelWeightData.model_validate(msg.data)
        except ValidationError as exc:
            logger.warning("invalid sentinel_weight payload: %s", exc)
            return

        marker = (payload.sentinel_id, payload.weight, payload.version)
        if not self._track_delivery(key, marker, msg.topic):
            return

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

    async def _process_generic_message(self, msg: ControlBusMessage) -> None:
        if self._should_drop_invalid_ack_sequence(msg):
            logger.warning(
                "dropping activation message with requires_ack=true due to missing or invalid sequence: %r",
                msg.data.get("sequence"),
            )
            gw_metrics.record_event_dropped(msg.topic)
            return

        sequenced_activation = self._sequenced_activation_context(msg)
        if sequenced_activation is not None:
            sequence_key, sequence = sequenced_activation
            await self._process_sequenced_activation_message(msg, sequence_key, sequence)
            return

        await self._process_generic_message_now(msg)

    def _should_drop_invalid_ack_sequence(self, msg: ControlBusMessage) -> bool:
        if msg.topic != "activation" or not msg.data.get("requires_ack"):
            return False
        sequence = msg.data.get("sequence")
        return isinstance(sequence, bool) or not isinstance(sequence, int)

    def _sequenced_activation_context(
        self, msg: ControlBusMessage
    ) -> tuple[tuple[str, str], int] | None:
        if msg.topic != "activation" or not msg.data.get("requires_ack"):
            return None

        sequence = msg.data.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int):
            return None

        world_id = str(msg.data.get("world_id") or msg.key or "")
        run_id = str(msg.data.get("run_id") or msg.run_id or "")
        return (world_id, run_id), sequence

    async def _process_sequenced_activation_message(
        self,
        msg: ControlBusMessage,
        sequence_key: tuple[str, str],
        sequence: int,
    ) -> None:
        state = self._activation_sequence_states.get(sequence_key)
        if state is None:
            state = _ActivationSequenceState(
                next_sequence=sequence,
                buffered={},
            )
            self._activation_sequence_states[sequence_key] = state

        if sequence < state.next_sequence:
            gw_metrics.record_event_dropped(msg.topic)
            return

        if sequence > state.next_sequence:
            state.buffered.setdefault(sequence, msg)
            self._schedule_activation_gap_timeout(sequence_key, state)
            return

        self._clear_activation_gap_timeout(state)
        await self._drain_sequenced_activation_messages(
            sequence_key=sequence_key,
            state=state,
            current_message=msg,
            current_sequence=sequence,
        )

    async def _drain_sequenced_activation_messages(
        self,
        *,
        sequence_key: tuple[str, str],
        state: _ActivationSequenceState,
        current_message: ControlBusMessage,
        current_sequence: int,
    ) -> None:
        while True:
            await self._process_generic_message_now(
                current_message,
                await_activation_ack=True,
                activation_sequence=current_sequence,
            )
            state.next_sequence = current_sequence + 1
            buffered_next = state.buffered.pop(state.next_sequence, None)
            if buffered_next is None:
                if state.buffered:
                    self._schedule_activation_gap_timeout(sequence_key, state)
                else:
                    self._clear_activation_gap_timeout(state)
                return
            current_message = buffered_next
            current_sequence = state.next_sequence

    def _schedule_activation_gap_timeout(
        self,
        sequence_key: tuple[str, str],
        state: _ActivationSequenceState,
    ) -> None:
        task = state.gap_timeout_task
        if task is not None and not task.done():
            return
        state.gap_timeout_token += 1
        token = state.gap_timeout_token
        state.gap_timeout_task = asyncio.create_task(
            self._activation_gap_timeout_after(sequence_key, token)
        )

    def _clear_activation_gap_timeout(self, state: _ActivationSequenceState) -> None:
        task = state.gap_timeout_task
        if task is not None:
            task.cancel()
            state.gap_timeout_task = None
        state.gap_timeout_token += 1

    def _cancel_all_activation_gap_timeouts(self) -> None:
        for state in self._activation_sequence_states.values():
            self._clear_activation_gap_timeout(state)

    async def _activation_gap_timeout_after(
        self,
        sequence_key: tuple[str, str],
        token: int,
    ) -> None:
        try:
            await asyncio.sleep(self._activation_gap_timeout_seconds)
            await self._queue.put(_ActivationGapTimeout(sequence_key=sequence_key, token=token))
        except asyncio.CancelledError:
            return

    async def _handle_activation_gap_timeout(self, timeout: _ActivationGapTimeout) -> None:
        state = self._activation_sequence_states.get(timeout.sequence_key)
        if state is None:
            return
        if timeout.token != state.gap_timeout_token:
            return
        state.gap_timeout_task = None
        if not state.buffered:
            return

        next_available = min(state.buffered)
        if next_available > state.next_sequence:
            world_id, run_id = timeout.sequence_key
            skipped_count = next_available - state.next_sequence
            logger.warning(
                "activation sequence gap timeout exceeded; forcing resync (world_id=%s run_id=%s expected=%s available=%s skipped=%s)",
                world_id,
                run_id,
                state.next_sequence,
                next_available,
                skipped_count,
            )
            gw_metrics.record_event_dropped("activation")
            state.next_sequence = next_available

        next_message = state.buffered.pop(state.next_sequence, None)
        if next_message is None:
            if state.buffered:
                self._schedule_activation_gap_timeout(timeout.sequence_key, state)
            return

        await self._drain_sequenced_activation_messages(
            sequence_key=timeout.sequence_key,
            state=state,
            current_message=next_message,
            current_sequence=state.next_sequence,
        )

    async def _process_generic_message_now(
        self,
        msg: ControlBusMessage,
        *,
        await_activation_ack: bool = False,
        activation_sequence: int | None = None,
    ) -> None:
        key = (msg.topic, msg.key)
        marker = self._marker_for_generic_message(
            msg, activation_sequence=activation_sequence
        )
        if not self._track_delivery(key, marker, msg.topic):
            return

        gw_metrics.record_controlbus_message(msg.topic, msg.timestamp_ms)

        if msg.topic == "activation":
            await self._record_apply_ack_metrics(
                msg, await_publish=await_activation_ack
            )
            fields = build_observability_fields(
                world_id=msg.data.get("world_id"),
                run_id=msg.data.get("run_id"),
                etag=msg.data.get("etag") or msg.etag,
                strategy_id=msg.data.get("strategy_id"),
            )
            add_span_attributes(fields)
            if fields:
                logger.info("activation_update_received", extra=fields)

        ws_hub = self.ws_hub
        if ws_hub is None:
            return

        await self._dispatch_generic_message(msg, ws_hub)

    def _marker_for_generic_message(
        self,
        msg: ControlBusMessage,
        *,
        activation_sequence: int | None = None,
    ) -> tuple[Any, ...]:
        if msg.topic == "policy":
            return (
                msg.data.get("checksum"),
                msg.data.get("policy_version"),
            )
        if msg.topic == "activation" and activation_sequence is not None:
            return (
                msg.data.get("run_id") or msg.run_id,
                activation_sequence,
            )
        return (msg.etag, msg.run_id)

    async def _dispatch_generic_message(self, msg: ControlBusMessage, ws_hub: WebSocketHub) -> None:
        version = msg.data.get("version")
        if version != 1:
            logger.warning("unsupported controlbus message version: %s", version)
            return

        if msg.topic == "activation":
            await ws_hub.send_activation_updated(msg.data)
            return
        if msg.topic == "policy":
            await ws_hub.send_policy_updated(msg.data)
            return
        if msg.topic == "queue":
            await self._handle_queue_update(msg, ws_hub)
            return

        logger.warning("Unhandled ControlBus topic %s", msg.topic)

    async def _record_apply_ack_metrics(
        self,
        msg: ControlBusMessage,
        *,
        await_publish: bool = False,
    ) -> None:
        if not msg.data.get("requires_ack"):
            return
        world_id = str(msg.data.get("world_id") or msg.key or "")
        run_id = str(msg.data.get("run_id") or msg.run_id or "")
        phase = str(msg.data.get("phase") or "unknown")
        gw_metrics.record_controlbus_apply_ack(
            world_id=world_id,
            run_id=run_id,
            phase=phase,
            sent_timestamp=msg.data.get("ts"),
            broker_timestamp_ms=msg.timestamp_ms,
        )
        if await_publish:
            await self._publish_activation_ack(
                world_id=world_id,
                run_id=run_id,
                sequence=msg.data.get("sequence"),
                phase=phase,
                etag=msg.etag,
            )
            return

        asyncio.create_task(
            self._publish_activation_ack(
                world_id=world_id,
                run_id=run_id,
                sequence=msg.data.get("sequence"),
                phase=phase,
                etag=msg.etag,
            )
        )

    async def _publish_activation_ack(
        self,
        *,
        world_id: str,
        run_id: str,
        sequence: Any,
        phase: str,
        etag: str | None,
    ) -> None:
        if self._ack_producer is None:
            return
        try:
            await self._ack_producer.publish_ack(
                world_id=world_id,
                run_id=run_id,
                sequence=int(sequence) if sequence is not None else None,
                phase=phase,
                etag=etag,
            )
        except Exception:
            logger.exception(
                "Failed to publish activation ack",
                extra={
                    "world_id": world_id,
                    "run_id": run_id,
                    "phase": phase,
                    "sequence": sequence,
                },
            )

    async def _handle_queue_update(self, msg: ControlBusMessage, ws_hub: WebSocketHub) -> None:
        tags = msg.data.get("tags", [])
        interval = msg.data.get("interval", 0)
        queues = msg.data.get("queues", [])
        match_mode = msg.data.get("match_mode", MatchMode.ANY.value)
        etag = msg.data.get("etag", msg.etag)
        ts = msg.data.get("ts")
        world_id = msg.data.get("world_id")
        execution_domain = msg.data.get("execution_domain")

        try:
            mode = MatchMode(match_mode)
        except ValueError:
            mode = MatchMode.ANY

        await ws_hub.send_queue_update(
            tags,
            interval,
            queues,
            mode,
            world_id=world_id,
            execution_domain=execution_domain,
            etag=etag,
            ts=ts,
        )
        fields = build_observability_fields(
            world_id=world_id,
            execution_domain=execution_domain,
            etag=etag,
        )
        add_span_attributes(fields)
        if fields:
            logger.info("queue_update_received", extra=fields)
        await self._maybe_emit_tagquery_upsert(ws_hub, tags, interval, queues, execution_domain)

    async def _maybe_emit_tagquery_upsert(
        self, ws_hub: WebSocketHub, tags: list[str], interval: int, queues: list[Any], execution_domain: str | None
    ) -> None:
        key = (tuple(sorted(tags)), int(interval), execution_domain or "")
        if key in self._known_tag_intervals:
            return

        self._known_tag_intervals.add(key)
        await ws_hub.send_tagquery_upsert(tags, interval, queues)

    def _track_delivery(
        self,
        key: tuple[str, str],
        marker: tuple[Any, ...],
        topic: str,
    ) -> bool:
        if self._last_seen.get(key) == marker:
            gw_metrics.record_event_dropped(topic)
            return False

        self._last_seen[key] = marker
        return True


__all__ = [
    "ControlBusConsumer",
    "ControlBusMessage",
    "RebalancingExecutionPolicy",
]
