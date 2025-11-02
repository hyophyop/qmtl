from __future__ import annotations

import logging
from typing import Any

from cachetools import TTLCache

from .http import HttpPoster

logger = logging.getLogger(__name__)

if "_trade_execution_service_sentinel" not in globals():
    _trade_execution_service_sentinel = object()


class TradeOrderDispatcher:
    """Dispatch trade orders to configured sinks with gating and deduplication."""

    def __init__(
        self,
        *,
        http_poster: type[HttpPoster] = HttpPoster,
        dedup_cache: TTLCache[str, bool] | None = None,
        activation_manager: Any | None = None,
        trade_execution_service: Any | None = None,
        trade_order_http_url: str | None = None,
        kafka_producer: Any | None = None,
        trade_order_kafka_topic: str | None = None,
    ) -> None:
        self._http_poster = http_poster
        self._order_dedup = dedup_cache
        self._activation_manager = activation_manager
        self._trade_execution_service = (
            trade_execution_service
            if trade_execution_service is not None
            else _trade_execution_service_sentinel
        )
        self._trade_order_http_url = trade_order_http_url
        self._kafka_producer = kafka_producer
        self._trade_order_kafka_topic = trade_order_kafka_topic

    # ------------------------------------------------------------------
    # Configuration API (mirrors Runner setters for ease of delegation)
    # ------------------------------------------------------------------
    def set_activation_manager(self, manager: Any | None) -> None:
        self._activation_manager = manager

    def set_trade_execution_service(self, service: Any | None) -> None:
        self._trade_execution_service = (
            service if service is not None else _trade_execution_service_sentinel
        )

    def set_http_url(self, url: str | None) -> None:
        self._trade_order_http_url = url

    def set_kafka_producer(self, producer: Any | None) -> None:
        self._kafka_producer = producer

    def set_trade_order_kafka_topic(self, topic: str | None) -> None:
        self._trade_order_kafka_topic = topic

    def set_dedup_cache(self, cache: TTLCache[str, bool] | None) -> None:
        self._order_dedup = cache

    # ------------------------------------------------------------------
    def reset_dedup(self) -> None:
        cache = self._order_dedup
        if cache is not None:
            cache.clear()

    # ------------------------------------------------------------------
    def dispatch(self, order: Any) -> None:
        """Dispatch ``order`` to configured sinks with gating and deduplication."""

        # Activation gating
        side = ""
        if isinstance(order, dict):
            side = (order.get("side") or "").lower()
        am = self._activation_manager
        if am is not None and side:
            try:
                allowed = am.allow_side(side)
            except Exception:  # pragma: no cover - defensive; activation is user provided
                allowed = True
            if not allowed:
                logger.info("Order gated off by activation: side=%s", side)
                return

        # Custom trade execution service takes precedence when configured
        service = self._trade_execution_service
        if service is not _trade_execution_service_sentinel and service is not None:
            service.post_order(order)
            return

        # Validate order payload shape for built-in adapters
        if not isinstance(order, dict) or not order.get("side"):
            logger.debug("ignoring non-order payload: %s", order)
            return

        # Deduplicate orders derived from identical signals
        cache = self._order_dedup
        dedup_key = self._dedup_key(order)
        if cache is not None and dedup_key is not None:
            if cache.get(dedup_key):
                logger.info("duplicate order suppressed (idempotent): %s", dedup_key)
                return
            cache[dedup_key] = True

        # Submit via HTTP if configured
        if self._trade_order_http_url is not None:
            for attempt in range(2):
                try:
                    self._http_poster.post(self._trade_order_http_url, json=order)
                    break
                except Exception:  # pragma: no cover - network failures are non-deterministic
                    if attempt == 1:
                        logger.warning("trade order HTTP submit failed; dropping order")

        # Submit via Kafka if configured
        if self._kafka_producer is not None and self._trade_order_kafka_topic is not None:
            self._kafka_producer.send(self._trade_order_kafka_topic, order)

    # ------------------------------------------------------------------
    @staticmethod
    def _dedup_key(order: dict) -> str | None:
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


__all__ = ["TradeOrderDispatcher"]
