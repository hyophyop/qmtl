from __future__ import annotations

import logging
from typing import Any

from cachetools import TTLCache

from .http import HttpPoster
from .dispatch_pipeline import (
    ActivationGateStep,
    CustomServiceDispatchStep,
    DeduplicationStep,
    DispatchContext,
    DispatchStep,
    HttpSubmitStep,
    KafkaSubmitStep,
    PayloadValidationStep,
)

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
        self._steps: list[DispatchStep] = []
        self._rebuild_pipeline()

    # ------------------------------------------------------------------
    # Configuration API (mirrors Runner setters for ease of delegation)
    # ------------------------------------------------------------------
    def set_activation_manager(self, manager: Any | None) -> None:
        self._activation_manager = manager
        self._rebuild_pipeline()

    def set_trade_execution_service(self, service: Any | None) -> None:
        self._trade_execution_service = (
            service if service is not None else _trade_execution_service_sentinel
        )
        self._rebuild_pipeline()

    def set_http_url(self, url: str | None) -> None:
        self._trade_order_http_url = url
        self._rebuild_pipeline()

    def set_kafka_producer(self, producer: Any | None) -> None:
        self._kafka_producer = producer
        self._rebuild_pipeline()

    def set_trade_order_kafka_topic(self, topic: str | None) -> None:
        self._trade_order_kafka_topic = topic
        self._rebuild_pipeline()

    def set_dedup_cache(self, cache: TTLCache[str, bool] | None) -> None:
        self._order_dedup = cache
        self._rebuild_pipeline()

    # ------------------------------------------------------------------
    def reset_dedup(self) -> None:
        cache = self._order_dedup
        if cache is not None:
            cache.clear()

    # ------------------------------------------------------------------
    def dispatch(self, order: Any) -> None:
        """Dispatch ``order`` to configured sinks with gating and deduplication."""

        context = DispatchContext(order)
        for step in self._steps:
            step.handle(context)
            if context.stopped:
                break

    # ------------------------------------------------------------------
    def _rebuild_pipeline(self) -> None:
        self._steps = [
            ActivationGateStep(self._activation_manager),
            CustomServiceDispatchStep(
                self._trade_execution_service, _trade_execution_service_sentinel
            ),
            PayloadValidationStep(),
            DeduplicationStep(self._order_dedup),
            HttpSubmitStep(self._http_poster, self._trade_order_http_url),
            KafkaSubmitStep(self._kafka_producer, self._trade_order_kafka_topic),
        ]


__all__ = ["TradeOrderDispatcher"]
