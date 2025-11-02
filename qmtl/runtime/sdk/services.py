from __future__ import annotations

"""Service container used by :mod:`qmtl.runtime.sdk.runner`."""

from typing import Any, Callable

from cachetools import TTLCache

from .activation_manager import ActivationManager
from .feature_store import FeatureArtifactPlane
from .gateway_client import GatewayClient
from .history_warmup_service import HistoryWarmupService
from .optional_services import KafkaConsumerFactory, RayExecutor
from .trade_dispatcher import TradeOrderDispatcher

ActivationManagerFactory = Callable[..., ActivationManager]


def _default_activation_manager_factory(
    *, gateway_url: str, world_id: str, strategy_id: str | None = None
) -> ActivationManager:
    return ActivationManager(gateway_url, world_id=world_id, strategy_id=strategy_id)


class RunnerServices:
    """Bundle of collaborators required by Runner orchestration."""

    def __init__(
        self,
        *,
        gateway_client: GatewayClient | None = None,
        history_service: HistoryWarmupService | None = None,
        feature_plane: FeatureArtifactPlane | None = None,
        ray_executor: RayExecutor | None = None,
        kafka_factory: KafkaConsumerFactory | None = None,
        activation_manager_factory: ActivationManagerFactory | None = None,
        activation_manager: ActivationManager | None = None,
        trade_dispatcher: TradeOrderDispatcher | None = None,
        dedup_cache: TTLCache[str, bool] | None = None,
        trade_execution_service: Any | None = None,
        trade_order_http_url: str | None = None,
        kafka_producer: Any | None = None,
        trade_order_kafka_topic: str | None = None,
    ) -> None:
        self.gateway_client = gateway_client or GatewayClient()
        self.history_service = history_service or HistoryWarmupService()
        self.feature_plane = feature_plane or FeatureArtifactPlane.from_config()
        self.ray_executor = ray_executor or RayExecutor()
        self.kafka_factory = kafka_factory or KafkaConsumerFactory()
        self._activation_manager_factory = (
            activation_manager_factory or _default_activation_manager_factory
        )
        self._activation_manager = activation_manager
        self._dedup_cache = dedup_cache or TTLCache(maxsize=10000, ttl=600)
        self._trade_dispatcher = trade_dispatcher or TradeOrderDispatcher(
            dedup_cache=self._dedup_cache,
            activation_manager=activation_manager,
            trade_execution_service=trade_execution_service,
            trade_order_http_url=trade_order_http_url,
            kafka_producer=kafka_producer,
            trade_order_kafka_topic=trade_order_kafka_topic,
        )
        self._trade_execution_service = trade_execution_service
        self._trade_order_http_url = trade_order_http_url
        self._kafka_producer = kafka_producer
        self._trade_order_kafka_topic = trade_order_kafka_topic

    # ------------------------------------------------------------------
    @classmethod
    def default(cls) -> "RunnerServices":
        return cls()

    # ------------------------------------------------------------------
    @property
    def trade_dispatcher(self) -> TradeOrderDispatcher:
        return self._trade_dispatcher

    @property
    def activation_manager(self) -> ActivationManager | None:
        return self._activation_manager

    @property
    def dedup_cache(self) -> TTLCache[str, bool] | None:
        return self._dedup_cache

    @property
    def trade_execution_service(self) -> Any | None:
        return self._trade_execution_service

    @property
    def trade_order_http_url(self) -> str | None:
        return self._trade_order_http_url

    @property
    def kafka_producer(self) -> Any | None:
        return self._kafka_producer

    @property
    def trade_order_kafka_topic(self) -> str | None:
        return self._trade_order_kafka_topic

    # ------------------------------------------------------------------
    def set_gateway_client(self, client: GatewayClient) -> None:
        self.gateway_client = client

    def set_activation_manager(self, manager: ActivationManager | None) -> None:
        self._activation_manager = manager
        self._trade_dispatcher.set_activation_manager(manager)

    def ensure_activation_manager(
        self, *, gateway_url: str, world_id: str, strategy_id: str | None = None
    ) -> ActivationManager:
        manager = self._activation_manager
        if manager is None:
            manager = self._activation_manager_factory(
                gateway_url=gateway_url,
                world_id=world_id,
                strategy_id=strategy_id,
            )
            self.set_activation_manager(manager)
        else:
            manager.gateway_url = gateway_url
            manager.world_id = world_id
            if strategy_id is not None:
                manager.strategy_id = strategy_id
        return manager

    def set_feature_plane(self, plane: FeatureArtifactPlane | None) -> None:
        self.feature_plane = plane

    # ------------------------------------------------------------------
    def set_trade_execution_service(self, service: Any | None) -> None:
        self._trade_execution_service = service
        self._trade_dispatcher.set_trade_execution_service(service)

    def set_kafka_producer(self, producer: Any | None) -> None:
        self._kafka_producer = producer
        self._trade_dispatcher.set_kafka_producer(producer)

    def set_trade_order_http_url(self, url: str | None) -> None:
        self._trade_order_http_url = url
        self._trade_dispatcher.set_http_url(url)

    def set_trade_order_kafka_topic(self, topic: str | None) -> None:
        self._trade_order_kafka_topic = topic
        self._trade_dispatcher.set_trade_order_kafka_topic(topic)

    # ------------------------------------------------------------------
    def reset_trade_order_dedup(self) -> None:
        cache = self._dedup_cache
        if cache is not None:
            cache.clear()
        self._trade_dispatcher.reset_dedup()


__all__ = ["RunnerServices"]
