from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DispatchContext:
    """Shared state passed between dispatch pipeline steps."""

    order: Any
    state: dict[str, Any] = field(default_factory=dict)
    stopped: bool = False

    def stop(self) -> None:
        """Signal that the pipeline should halt after the current step."""

        self.stopped = True


class DispatchStep(Protocol):
    """Single unit of work in the trade dispatch pipeline."""

    def handle(self, context: DispatchContext) -> None:  # pragma: no cover - protocol
        ...


class ActivationGateStep:
    """Gate orders based on activation manager rules."""

    def __init__(self, activation_manager: Any | None) -> None:
        self._activation_manager = activation_manager

    def handle(self, context: DispatchContext) -> None:
        manager = self._activation_manager
        if manager is None:
            return

        order = context.order
        side = ""
        if isinstance(order, dict):
            side = (order.get("side") or "").lower()

        if not side:
            return

        try:
            allowed = manager.allow_side(side)
        except Exception:  # pragma: no cover - activation is user provided
            allowed = True

        if not allowed:
            logger.info("Order gated off by activation: side=%s", side)
            context.stop()


class CustomServiceDispatchStep:
    """Short-circuit dispatch when a custom execution service is configured."""

    def __init__(self, service: Any | None, sentinel: Any) -> None:
        self._service = service
        self._sentinel = sentinel

    def handle(self, context: DispatchContext) -> None:
        service = self._service
        if service is None or service is self._sentinel:
            return

        service.post_order(context.order)
        context.stop()


class PayloadValidationStep:
    """Ensure that the payload resembles a trade order before dispatch."""

    def handle(self, context: DispatchContext) -> None:
        order = context.order
        if not isinstance(order, dict) or not order.get("side"):
            logger.debug("ignoring non-order payload: %s", order)
            context.stop()


class DeduplicationStep:
    """Prevent duplicate orders based on a cache-backed key."""

    def __init__(self, cache: Any | None) -> None:
        self._cache = cache

    def handle(self, context: DispatchContext) -> None:
        cache = self._cache
        if cache is None:
            return

        order = context.order
        if not isinstance(order, dict):
            return

        key = self._dedup_key(order)
        if key is None:
            return

        if cache.get(key):
            logger.info("duplicate order suppressed (idempotent): %s", key)
            context.stop()
            return

        cache[key] = True

    @staticmethod
    def _dedup_key(order: dict[str, Any]) -> str | None:
        try:
            qty = order.get("quantity")
            ts = order.get("timestamp")
            sym = order.get("symbol") or ""
            side = order.get("side")
        except Exception:
            return None

        if side is None:
            return None

        return f"{side}|{qty}|{ts}|{sym}"


class HttpSubmitStep:
    """Submit orders via HTTP with retry semantics."""

    def __init__(
        self,
        http_poster: type,
        trade_order_http_url: str | None,
    ) -> None:
        self._http_poster = http_poster
        self._trade_order_http_url = trade_order_http_url

    def handle(self, context: DispatchContext) -> None:
        url = self._trade_order_http_url
        if url is None:
            return

        order = context.order
        for attempt in range(2):
            try:
                self._http_poster.post(url, json=order)
                break
            except Exception:  # pragma: no cover - network failures are non-deterministic
                if attempt == 1:
                    logger.warning("trade order HTTP submit failed; dropping order")


class KafkaSubmitStep:
    """Submit orders to Kafka when configured."""

    def __init__(self, producer: Any | None, topic: str | None) -> None:
        self._producer = producer
        self._topic = topic

    def handle(self, context: DispatchContext) -> None:
        producer = self._producer
        topic = self._topic
        if producer is None or topic is None:
            return

        try:
            producer.send(topic, context.order)
        except Exception:  # pragma: no cover - Kafka failures are non-deterministic
            logger.warning(
                "trade order Kafka submit failed; raising for caller handling",
                exc_info=True,
            )
            raise


__all__ = [
    "ActivationGateStep",
    "CustomServiceDispatchStep",
    "DeduplicationStep",
    "DispatchContext",
    "DispatchStep",
    "HttpSubmitStep",
    "KafkaSubmitStep",
    "PayloadValidationStep",
]
