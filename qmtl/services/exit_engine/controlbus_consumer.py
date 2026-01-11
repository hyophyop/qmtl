"""Consume risk snapshot events and apply exit engine decisions."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from qmtl.services.kafka import KafkaConsumerLike, create_kafka_consumer
from qmtl.services.risk_hub_contract import normalize_and_validate_snapshot

from .activation_client import WorldServiceActivationClient
from .config import ExitEngineConfig
from .models import ExitAction
from .rules import determine_exit_action

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


def _expired_snapshot(payload: Mapping[str, Any], *, now: datetime | None = None) -> bool:
    ttl = payload.get("ttl_sec")
    if ttl is None:
        return False
    ttl_value = int(ttl)
    if ttl_value <= 0:
        return True
    created = _parse_iso(payload.get("created_at"))
    if created is None:
        return False
    return (now or datetime.now(timezone.utc)) > created + timedelta(seconds=ttl_value)


class ExitEngineControlBusConsumer:
    """Listen to risk_snapshot_updated events and trigger activation updates."""

    def __init__(
        self,
        *,
        config: ExitEngineConfig,
        activation_client: WorldServiceActivationClient,
        brokers: Iterable[str] | None = None,
        topic: str | None = None,
        group_id: str | None = None,
        consumer: KafkaConsumerLike | None = None,
    ) -> None:
        self._config = config
        self._activation_client = activation_client
        self._brokers = list(brokers or config.controlbus_brokers)
        self._topic = topic or config.controlbus_topic
        self._group_id = group_id or config.controlbus_group_id
        self._consumer: KafkaConsumerLike | None = consumer
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        if self._consumer is None:
            if not self._brokers or not self._topic:
                logger.warning("ExitEngine consumer disabled: brokers/topics not configured")
                return
            consumer = create_kafka_consumer(
                self._brokers,
                group_id=self._group_id,
                auto_offset_reset="latest",
                enable_auto_commit=True,
            )
            if consumer is None:
                logger.warning("ExitEngine consumer disabled: Kafka client unavailable")
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
        self._stopped.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopped.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        if self._consumer:
            with contextlib.suppress(Exception):
                await self._consumer.stop()
            self._consumer = None

    async def _run(self) -> None:
        consumer = self._consumer
        if consumer is None:
            return
        async for msg in consumer:
            if self._stopped.is_set():
                break
            try:
                await self._handle_message(msg)
            except Exception:
                logger.exception("ExitEngine failed to process message")

    def _extract_event(self, msg: Any) -> tuple[str | None, Mapping[str, Any] | None, str | None]:
        try:
            payload: Any = msg.value
            if isinstance(payload, (bytes, bytearray)):
                payload = payload.decode()
            if isinstance(payload, str):
                payload = json.loads(payload)
        except Exception:
            logger.warning("ExitEngine consumer received malformed message")
            return None, None, None
        if not isinstance(payload, Mapping):
            return None, None, None
        event_type = payload.get("type")
        data = payload.get("data")
        corr = payload.get("correlation_id")
        request_id = None
        if isinstance(corr, str) and corr:
            request_id = corr
        elif isinstance(payload.get("id"), str):
            request_id = payload.get("id")
        return str(event_type) if event_type else None, data if isinstance(data, Mapping) else None, request_id

    async def _handle_message(self, msg: Any) -> None:
        event_type, data, request_id = self._extract_event(msg)
        if event_type != "risk_snapshot_updated" or data is None:
            return
        world_id = str(data.get("world_id") or "").strip()
        if not world_id:
            return
        try:
            validated = normalize_and_validate_snapshot(
                world_id,
                data,
                ttl_sec_default=self._config.ttl_sec_default,
                ttl_sec_max=self._config.ttl_sec_max,
            )
        except Exception:
            logger.exception("ExitEngine received invalid risk snapshot payload")
            return
        if _expired_snapshot(validated):
            logger.warning("Skipping expired risk snapshot for %s", world_id)
            return
        action = determine_exit_action(validated, self._config, request_id=request_id)
        if action is None:
            return
        await self._apply_action(action)

    async def _apply_action(self, action: ExitAction) -> None:
        fields = {
            "world_id": action.world_id,
            "run_id": action.run_id,
            "request_id": action.request_id,
            "strategy_id": action.strategy_id,
            "side": action.side,
            "action": action.action,
            "reason": action.reason,
        }
        logger.info("exit_engine_action", extra=fields)
        try:
            await self._activation_client.apply_action(action)
        except Exception:
            logger.exception("ExitEngine activation update failed", extra=fields)


__all__ = ["ExitEngineControlBusConsumer"]
