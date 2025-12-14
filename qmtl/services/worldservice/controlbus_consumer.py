"""ControlBus consumer that hydrates the risk hub and triggers validations."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import logging
from collections import deque
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone, timedelta
from typing import Any, Awaitable, Callable, Iterable

from qmtl.foundation.common.cloudevents import format_event
from qmtl.services.kafka import KafkaConsumerLike, create_kafka_consumer
from qmtl.services.kafka import KafkaProducerLike, create_kafka_producer
from qmtl.services.risk_hub_contract import normalize_and_validate_snapshot, risk_snapshot_dedupe_key

from . import metrics as ws_metrics
from .controlbus_defaults import (
    DEFAULT_RISK_HUB_CONSUMER_GROUP_ID,
    DEFAULT_RISK_HUB_DEDUPE_TTL_SEC,
    DEFAULT_RISK_HUB_DLQ_TOPIC,
    DEFAULT_RISK_HUB_MAX_ATTEMPTS,
    DEFAULT_RISK_HUB_RETRY_BACKOFF_SEC,
    default_dlq_topic,
)
from .risk_hub import PortfolioSnapshot, RiskSignalHub


logger = logging.getLogger(__name__)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _expired(snapshot: PortfolioSnapshot, *, now: datetime | None = None) -> bool:
    ttl = snapshot.ttl_sec if snapshot.ttl_sec is not None else 10
    if ttl is None or ttl <= 0:
        return True
    created = _parse_iso(snapshot.created_at)
    if created is None:
        return False
    return (now or datetime.now(timezone.utc)) > created + timedelta(seconds=int(ttl))


class RiskHubControlBusConsumer:
    """Consume risk_snapshot_updated events and apply them to the local hub."""

    def __init__(
        self,
        *,
        hub: RiskSignalHub,
        on_snapshot: Callable[[PortfolioSnapshot], Awaitable[Any]] | None = None,
        dedupe_cache: Any | None = None,
        dedupe_ttl_sec: int | None = DEFAULT_RISK_HUB_DEDUPE_TTL_SEC,
        max_attempts: int = DEFAULT_RISK_HUB_MAX_ATTEMPTS,
        retry_backoff_sec: float = DEFAULT_RISK_HUB_RETRY_BACKOFF_SEC,
        dlq_topic: str | None = DEFAULT_RISK_HUB_DLQ_TOPIC,
        dlq_producer: KafkaProducerLike | None = None,
        ttl_sec_default: int = 900,
        ttl_sec_max: int = 86400,
        allowed_actors: Sequence[str] | None = None,
        allowed_stages: Sequence[str] | None = None,
        brokers: Iterable[str] | None = None,
        topic: str | None = None,
        consumer: KafkaConsumerLike | None = None,
        group_id: str = DEFAULT_RISK_HUB_CONSUMER_GROUP_ID,
    ) -> None:
        self._hub = hub
        self._on_snapshot = on_snapshot
        self._brokers = list(brokers or [])
        resolved_topic = topic
        self._topic = resolved_topic
        self._consumer: KafkaConsumerLike | None = consumer
        self._task: asyncio.Task | None = None
        self._group_id = group_id
        self._stopped = asyncio.Event()
        self._dedupe_cache = dedupe_cache or getattr(hub, "cache", None) or getattr(hub, "_cache", None)
        self._dedupe_ttl_sec = dedupe_ttl_sec
        self._dedupe_keys: deque[str] | None = deque(maxlen=1000)
        self._max_attempts = max(1, int(max_attempts))
        self._retry_backoff_sec = max(0.0, float(retry_backoff_sec))
        resolved_dlq_topic = dlq_topic
        if resolved_dlq_topic is None and resolved_topic:
            resolved_dlq_topic = default_dlq_topic(str(resolved_topic))
        self._dlq_topic = resolved_dlq_topic
        self._dlq_producer: KafkaProducerLike | None = dlq_producer
        self._dlq_started = False
        self._ttl_sec_default = int(ttl_sec_default)
        self._ttl_sec_max = int(ttl_sec_max)
        self._allowed_actors = list(allowed_actors) if allowed_actors is not None else None
        self._allowed_stages = list(allowed_stages) if allowed_stages is not None else None

    async def _dedupe_cached(self, key: str) -> bool:
        cache = self._dedupe_cache
        if cache is None:
            return False
        cache_key = f"risk-hub:dedupe:{key}"
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

    async def _mark_dedupe(self, key: str, *, ttl_sec: int | None = None) -> None:
        cache = self._dedupe_cache
        if cache is None:
            return
        cache_key = f"risk-hub:dedupe:{key}"
        setter = getattr(cache, "set", None)
        expire = getattr(cache, "expire", None)
        if setter is None:
            return
        ttl_final = ttl_sec if ttl_sec is not None else self._dedupe_ttl_sec
        try:
            res = setter(cache_key, "1")
            if inspect.isawaitable(res):
                await res
            if ttl_final is not None and ttl_final > 0 and expire is not None:
                res2 = expire(cache_key, int(ttl_final))
                if inspect.isawaitable(res2):
                    await res2
        except Exception:
            return

    async def start(self) -> None:
        if self._task is not None:
            return
        if self._consumer is None:
            if not self._brokers or not self._topic:
                logger.warning("RiskHub consumer disabled: brokers/topics not configured")
                return
            consumer = create_kafka_consumer(
                self._brokers,
                group_id=self._group_id,
                auto_offset_reset="latest",
                enable_auto_commit=False,
            )
            if consumer is None:
                logger.warning("RiskHub consumer disabled: Kafka client unavailable")
                return
            self._consumer = consumer
            await consumer.start()
            await consumer.subscribe([self._topic])
        else:
            # Ensure externally provided consumer is started/subscribed if possible
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

    async def _start_dlq_producer(self) -> None:
        if self._dlq_producer is not None:
            starter = getattr(self._dlq_producer, "start", None)
            if starter is not None and not self._dlq_started:
                try:
                    await starter()
                    self._dlq_started = True
                except Exception:
                    logger.exception("Failed to start RiskHub DLQ producer")
            return
        if not self._dlq_topic or not self._brokers:
            return
        producer = create_kafka_producer(self._brokers)
        if producer is None:
            logger.warning("RiskHub DLQ disabled: Kafka client unavailable")
            return
        self._dlq_producer = producer
        try:
            await producer.start()
            self._dlq_started = True
        except Exception:
            logger.exception("Failed to start RiskHub DLQ producer")
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
            logger.exception("RiskHub consumer loop failed")

    @staticmethod
    def _extract_stage(payload: Mapping[str, Any]) -> str:
        provenance = payload.get("provenance")
        if isinstance(provenance, Mapping):
            stage = provenance.get("stage")
            if stage:
                return str(stage)
        return "unknown"

    async def _publish_dlq(
        self,
        *,
        world_id: str,
        stage: str,
        original_event: Mapping[str, Any],
        error: str,
        attempts: int,
    ) -> None:
        ws_metrics.record_risk_snapshot_dlq(world_id, stage=stage)
        if not self._dlq_topic or self._dlq_producer is None:
            return
        correlation_id = original_event.get("correlation_id")
        corr = str(correlation_id) if isinstance(correlation_id, str) else None
        body = {
            "world_id": world_id,
            "stage": stage,
            "attempts": int(attempts),
            "error": error,
            "event": dict(original_event),
        }
        evt = format_event(
            "qmtl.services.worldservice",
            "risk_snapshot_updated_dlq",
            body,
            correlation_id=corr,
        )
        data = json.dumps(evt).encode()
        key = world_id.encode() if world_id else None
        try:
            await self._dlq_producer.send_and_wait(self._dlq_topic, data, key=key)
        except Exception:  # pragma: no cover - best-effort
            logger.exception("Failed to publish RiskHub DLQ event")

    async def _handle_message(self, msg: Any) -> None:
        try:
            payload = msg.value
            if isinstance(payload, (bytes, bytearray)):
                payload = payload.decode()
            if isinstance(payload, str):
                payload = json.loads(payload)
            event_type = payload.get("type")
            data = payload.get("data") if isinstance(payload, dict) else None
        except Exception:
            logger.warning("RiskHub consumer received malformed message")
            return
        if event_type != "risk_snapshot_updated" or not isinstance(data, dict):
            return
        world_id = str(data.get("world_id") or "")
        stage_label = self._extract_stage(data)
        try:
            validated = normalize_and_validate_snapshot(
                world_id,
                data,
                ttl_sec_default=self._ttl_sec_default,
                ttl_sec_max=self._ttl_sec_max,
                allowed_actors=self._allowed_actors,
                allowed_stages=self._allowed_stages,
            )
            snapshot = PortfolioSnapshot.from_payload(validated)
        except Exception as exc:
            ws_metrics.record_risk_snapshot_failed(world_id or "unknown", stage=stage_label)
            await self._publish_dlq(
                world_id=world_id or "unknown",
                stage=stage_label,
                original_event=payload if isinstance(payload, Mapping) else {"event": payload},
                error=f"invalid snapshot payload: {exc}",
                attempts=1,
            )
            logger.exception("Invalid risk snapshot event payload")
            return

        stage_label = str((snapshot.provenance or {}).get("stage") or stage_label or "unknown")
        if _expired(snapshot):
            ws_metrics.record_risk_snapshot_expired(snapshot.world_id, stage=stage_label)
            logger.warning("Skipping expired risk snapshot for %s", snapshot.world_id)
            return

        dedupe_key = risk_snapshot_dedupe_key(snapshot.to_dict())
        if self._dedupe_keys is not None and dedupe_key in self._dedupe_keys:
            ws_metrics.record_risk_snapshot_dedupe(snapshot.world_id, stage=stage_label)
            return
        if await self._dedupe_cached(dedupe_key):
            ws_metrics.record_risk_snapshot_dedupe(snapshot.world_id, stage=stage_label)
            if self._dedupe_keys is not None:
                self._dedupe_keys.append(dedupe_key)
            return

        for attempt in range(1, self._max_attempts + 1):
            try:
                await self._hub.upsert_snapshot(snapshot)
                if self._on_snapshot is not None:
                    await self._on_snapshot(snapshot)
                latency = None
                created = _parse_iso(snapshot.created_at)
                if created is not None:
                    latency = (datetime.now(timezone.utc) - created).total_seconds()
                ws_metrics.record_risk_snapshot_processed(
                    snapshot.world_id,
                    stage=stage_label,
                    latency_seconds=latency,
                )
                await self._mark_dedupe(dedupe_key, ttl_sec=snapshot.ttl_sec)
                if self._dedupe_keys is not None:
                    self._dedupe_keys.append(dedupe_key)
                return
            except Exception as exc:
                if attempt >= self._max_attempts:
                    ws_metrics.record_risk_snapshot_failed(snapshot.world_id, stage=stage_label)
                    await self._publish_dlq(
                        world_id=snapshot.world_id,
                        stage=stage_label,
                        original_event=payload if isinstance(payload, Mapping) else {"event": payload},
                        error=str(exc),
                        attempts=self._max_attempts,
                    )
                    logger.exception("Failed to process risk_snapshot_updated event")
                    return
                ws_metrics.record_risk_snapshot_retry(snapshot.world_id, stage=stage_label)
                if self._retry_backoff_sec > 0:
                    await asyncio.sleep(self._retry_backoff_sec * attempt)


__all__ = ["RiskHubControlBusConsumer"]
