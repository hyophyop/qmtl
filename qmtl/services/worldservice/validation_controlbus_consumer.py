"""ControlBus consumer for EvaluationRun-driven validation pipelines."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import logging
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Awaitable, Callable, Iterable, Sequence

from qmtl.foundation.common.cloudevents import format_event
from qmtl.services.kafka import KafkaConsumerLike, KafkaProducerLike, create_kafka_consumer, create_kafka_producer

from . import metrics as ws_metrics
from .controlbus_defaults import (
    DEFAULT_CONTROLBUS_TOPIC,
    DEFAULT_VALIDATION_CONSUMER_GROUP_ID,
    DEFAULT_VALIDATION_DEDUPE_TTL_SEC,
    DEFAULT_VALIDATION_DLQ_TOPIC,
    DEFAULT_VALIDATION_EVENT_TTL_SEC,
    DEFAULT_VALIDATION_MAX_ATTEMPTS,
    DEFAULT_VALIDATION_RETRY_BACKOFF_SEC,
    default_dlq_topic,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidationEvent:
    event_type: str
    world_id: str
    stage: str | None
    strategy_id: str | None
    run_id: str | None
    policy_version: int | None
    change_type: str | None
    idempotency_key: str
    emitted_at: datetime | None
    correlation_id: str | None
    raw_event: Mapping[str, Any]
    data: Mapping[str, Any]


def _parse_event_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return ws_metrics.parse_timestamp(str(value))


class ValidationControlBusConsumer:
    """Consume validation-related events and trigger async extended validations."""

    def __init__(
        self,
        *,
        on_event: Callable[[ValidationEvent], Awaitable[Any]] | None = None,
        allowed_event_types: Sequence[str] | None = None,
        dedupe_cache: Any | None = None,
        dedupe_ttl_sec: int | None = DEFAULT_VALIDATION_DEDUPE_TTL_SEC,
        event_ttl_sec: int | None = DEFAULT_VALIDATION_EVENT_TTL_SEC,
        max_attempts: int = DEFAULT_VALIDATION_MAX_ATTEMPTS,
        retry_backoff_sec: float = DEFAULT_VALIDATION_RETRY_BACKOFF_SEC,
        dlq_topic: str | None = DEFAULT_VALIDATION_DLQ_TOPIC,
        dlq_producer: KafkaProducerLike | None = None,
        brokers: Iterable[str] | None = None,
        topic: str | None = DEFAULT_CONTROLBUS_TOPIC,
        consumer: KafkaConsumerLike | None = None,
        group_id: str = DEFAULT_VALIDATION_CONSUMER_GROUP_ID,
    ) -> None:
        self._on_event = on_event
        self._allowed_event_types = set(allowed_event_types) if allowed_event_types is not None else {
            "evaluation_run_created",
            "evaluation_run_updated",
            "validation_profile_changed",
        }
        self._brokers = list(brokers or [])
        self._topic = topic
        self._consumer: KafkaConsumerLike | None = consumer
        self._group_id = group_id
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

        self._dedupe_cache = dedupe_cache
        self._dedupe_ttl_sec = dedupe_ttl_sec
        self._dedupe_keys: deque[str] | None = deque(maxlen=2000)

        self._event_ttl_sec = event_ttl_sec
        self._max_attempts = max(1, int(max_attempts))
        self._retry_backoff_sec = max(0.0, float(retry_backoff_sec))

        resolved_dlq = dlq_topic
        if resolved_dlq is None and topic:
            resolved_dlq = default_dlq_topic(str(topic))
        self._dlq_topic = resolved_dlq
        self._dlq_producer: KafkaProducerLike | None = dlq_producer
        self._dlq_started = False

    async def _dedupe_cached(self, key: str) -> bool:
        cache = self._dedupe_cache
        if cache is None:
            return False
        cache_key = f"world-validation:dedupe:{key}"
        getter = getattr(cache, "get", None)
        if getter is None:
            return False
        try:
            value = getter(cache_key)
            if inspect.isawaitable(value):
                value = await value
            return bool(value)
        except Exception:
            return False

    async def _mark_dedupe(self, key: str) -> None:
        cache = self._dedupe_cache
        if cache is None:
            return
        cache_key = f"world-validation:dedupe:{key}"
        setter = getattr(cache, "set", None)
        expire = getattr(cache, "expire", None)
        if setter is None:
            return
        try:
            res = setter(cache_key, "1")
            if inspect.isawaitable(res):
                await res
            ttl = self._dedupe_ttl_sec
            if ttl is not None and ttl > 0 and expire is not None:
                res2 = expire(cache_key, int(ttl))
                if inspect.isawaitable(res2):
                    await res2
        except Exception:
            return

    async def _start_dlq_producer(self) -> None:
        if self._dlq_producer is not None:
            starter = getattr(self._dlq_producer, "start", None)
            if starter is not None and not self._dlq_started:
                try:
                    await starter()
                    self._dlq_started = True
                except Exception:
                    logger.exception("Failed to start validation DLQ producer")
            return
        if not self._dlq_topic or not self._brokers:
            return
        producer = create_kafka_producer(self._brokers)
        if producer is None:
            logger.warning("Validation DLQ disabled: Kafka client unavailable")
            return
        self._dlq_producer = producer
        try:
            await producer.start()
            self._dlq_started = True
        except Exception:
            logger.exception("Failed to start validation DLQ producer")
            self._dlq_producer = None
            self._dlq_started = False

    async def _stop_dlq_producer(self) -> None:
        producer = self._dlq_producer
        if producer is None or not self._dlq_started:
            return
        with contextlib.suppress(Exception):  # pragma: no cover - best-effort shutdown
            await producer.stop()
        self._dlq_started = False

    async def _commit(self) -> None:
        consumer = self._consumer
        if consumer is None:
            return
        commit = getattr(consumer, "commit", None)
        if commit is None:
            return
        try:
            res = commit()
            if inspect.isawaitable(res):
                await res
        except Exception:  # pragma: no cover - best-effort
            return

    async def start(self) -> None:
        if self._task is not None:
            return
        if self._consumer is None:
            if not self._brokers or not self._topic:
                logger.warning("Validation consumer disabled: brokers/topics not configured")
                return
            consumer = create_kafka_consumer(
                self._brokers,
                group_id=self._group_id,
                auto_offset_reset="latest",
                enable_auto_commit=False,
            )
            if consumer is None:
                logger.warning("Validation consumer disabled: Kafka client unavailable")
                return
            self._consumer = consumer
            await consumer.start()
            await consumer.subscribe([self._topic])
        else:
            if hasattr(self._consumer, "start"):
                with contextlib.suppress(Exception):
                    await self._consumer.start()
            if self._topic and hasattr(self._consumer, "subscribe"):
                with contextlib.suppress(Exception):
                    await self._consumer.subscribe([self._topic])

        await self._start_dlq_producer()
        self._stopped.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopped.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(Exception):
                await self._task
            self._task = None
        if self._consumer:
            with contextlib.suppress(Exception):  # pragma: no cover - best-effort shutdown
                await self._consumer.stop()
            self._consumer = None
        await self._stop_dlq_producer()

    async def _publish_dlq(
        self,
        *,
        event: ValidationEvent,
        error: str,
        attempts: int,
    ) -> None:
        ws_metrics.record_validation_event_dlq(
            event.world_id,
            event_type=event.event_type,
            stage=event.stage,
        )
        if not self._dlq_topic or self._dlq_producer is None:
            return
        body = {
            "world_id": event.world_id,
            "stage": event.stage,
            "event_type": event.event_type,
            "attempts": int(attempts),
            "error": error,
            "event": dict(event.raw_event),
        }
        evt = format_event(
            "qmtl.services.worldservice",
            "validation_event_dlq",
            body,
            correlation_id=event.correlation_id,
        )
        data = json.dumps(evt).encode()
        key = event.world_id.encode() if event.world_id else None
        try:
            await self._dlq_producer.send_and_wait(self._dlq_topic, data, key=key)
        except Exception:  # pragma: no cover - best-effort
            logger.exception("Failed to publish validation DLQ event")

    def _is_expired(self, event: ValidationEvent) -> bool:
        ttl = self._event_ttl_sec
        if ttl is None or ttl <= 0:
            return False
        if event.emitted_at is None:
            return False
        return datetime.now(timezone.utc) > event.emitted_at + timedelta(seconds=int(ttl))

    async def _run(self) -> None:
        assert self._consumer is not None
        try:
            async for msg in self._consumer:
                if self._stopped.is_set():
                    break
                try:
                    await self._handle_message(msg)
                finally:
                    await self._commit()
        except asyncio.CancelledError:
            return
        except Exception:  # pragma: no cover - defensive
            logger.exception("Validation consumer loop failed")

    async def _handle_message(self, msg: Any) -> None:
        try:
            payload = msg.value
            if isinstance(payload, (bytes, bytearray)):
                payload = payload.decode()
            if isinstance(payload, str):
                payload = json.loads(payload)
        except Exception:
            logger.warning("Validation consumer received malformed message")
            return
        if not isinstance(payload, Mapping):
            return

        event_type = payload.get("type")
        if not isinstance(event_type, str) or event_type not in self._allowed_event_types:
            return
        data = payload.get("data")
        if not isinstance(data, Mapping):
            return

        world_id = str(data.get("world_id") or "")
        stage = str(data.get("stage")) if data.get("stage") is not None else None
        strategy_id = str(data.get("strategy_id")) if data.get("strategy_id") is not None else None
        run_id = str(data.get("run_id")) if data.get("run_id") is not None else None
        change_type = str(data.get("change_type")) if data.get("change_type") is not None else None
        policy_version: int | None = None
        if data.get("policy_version") is not None:
            try:
                policy_version = int(data.get("policy_version"))
            except Exception:
                policy_version = None

        idem = data.get("idempotency_key")
        if not isinstance(idem, str) or not idem:
            evt_id = payload.get("id")
            idem = str(evt_id) if isinstance(evt_id, str) and evt_id else f"{event_type}:{world_id}:{strategy_id}:{run_id}"

        event = ValidationEvent(
            event_type=event_type,
            world_id=world_id,
            stage=stage,
            strategy_id=strategy_id,
            run_id=run_id,
            policy_version=policy_version,
            change_type=change_type,
            idempotency_key=idem,
            emitted_at=_parse_event_time(payload.get("time")),
            correlation_id=str(payload.get("correlation_id")) if payload.get("correlation_id") else None,
            raw_event=payload,
            data=data,
        )

        if self._dedupe_keys is not None and event.idempotency_key in self._dedupe_keys:
            ws_metrics.record_validation_event_dedupe(world_id or "unknown", event_type=event_type, stage=stage)
            return
        if await self._dedupe_cached(event.idempotency_key):
            ws_metrics.record_validation_event_dedupe(world_id or "unknown", event_type=event_type, stage=stage)
            if self._dedupe_keys is not None:
                self._dedupe_keys.append(event.idempotency_key)
            return

        if self._event_ttl_sec is not None and self._is_expired(event):
            ws_metrics.record_validation_event_expired(world_id or "unknown", event_type=event_type, stage=stage)
            return

        for attempt in range(1, self._max_attempts + 1):
            try:
                if self._on_event is not None:
                    await self._on_event(event)
                latency = None
                if event.emitted_at is not None:
                    latency = (datetime.now(timezone.utc) - event.emitted_at).total_seconds()
                ws_metrics.record_validation_event_processed(
                    world_id or "unknown",
                    event_type=event_type,
                    stage=stage,
                    latency_seconds=latency,
                )
                await self._mark_dedupe(event.idempotency_key)
                if self._dedupe_keys is not None:
                    self._dedupe_keys.append(event.idempotency_key)
                return
            except Exception as exc:
                if attempt >= self._max_attempts:
                    ws_metrics.record_validation_event_failed(world_id or "unknown", event_type=event_type, stage=stage)
                    await self._publish_dlq(event=event, error=str(exc), attempts=self._max_attempts)
                    logger.exception("Failed to process validation event %s", event_type)
                    return
                ws_metrics.record_validation_event_retry(world_id or "unknown", event_type=event_type, stage=stage)
                if self._retry_backoff_sec > 0:
                    await asyncio.sleep(self._retry_backoff_sec * attempt)


__all__ = ["ValidationControlBusConsumer", "ValidationEvent"]
