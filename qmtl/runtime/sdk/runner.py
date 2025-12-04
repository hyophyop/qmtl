from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Mapping, TYPE_CHECKING, cast

from opentelemetry import trace

from qmtl.foundation.common import AsyncCircuitBreaker
from qmtl.foundation.common.compute_key import ComputeContext, DEFAULT_EXECUTION_DOMAIN
from qmtl.foundation.common.tracing import setup_tracing

from . import metrics as sdk_metrics
from . import runtime
from .execution_context import (
    normalize_default_context,
    resolve_execution_context,
)
from .optional_services import KafkaConsumerFactory, RayExecutor
from .protocols import (
    HistoryProviderProtocol,
    MetricWithValueProtocol,
    TagQueryManagerProtocol,
)
from .services import RunnerServices, get_global_services, set_global_services
from .strategy import Strategy
from .strategy_bootstrapper import StrategyBootstrapper
from .tag_manager_service import TagManagerService
from .mode import Mode
from .submit import SubmitResult, submit, submit_async

if TYPE_CHECKING:
    from .activation_manager import ActivationManager
    from .gateway_client import GatewayClient
    from .feature_store import FeatureArtifactPlane
    from .data_io import HistoryBackend, HistoryProvider
    from .seamless_data_provider import SeamlessDataProvider
else:  # pragma: no cover - runtime placeholders for type-only imports
    HistoryBackend = HistoryProvider = object


# Public API - only expose essential Runner class
__all__ = ["Runner"]


_runner_services = get_global_services()


logger = logging.getLogger(__name__)

setup_tracing("sdk")
tracer = trace.get_tracer(__name__)


class Runner:
    """Execute strategies in various modes."""

    _services: RunnerServices = _runner_services
    _default_context: dict[str, str] | None = None
    _enable_trade_submission: bool = True
    _trade_mode: str = "simulate"  # simulate | live (non-breaking; informational)

    @classmethod
    async def _refresh_gateway_capabilities(cls, gateway_url: str) -> None:
        client = cls.services().gateway_client
        try:
            health = await client.get_health(gateway_url=gateway_url)
        except Exception:
            logger.debug("Failed to fetch gateway health for %s", gateway_url, exc_info=True)
            return
        if not health:
            return
        runtime.set_gateway_capabilities(
            rebalance_schema_version=health.get("rebalance_schema_version"),
            alpha_metrics_capable=health.get("alpha_metrics_capable"),
        )

    @classmethod
    def services(cls) -> RunnerServices:
        return cls._services

    @classmethod
    def set_services(cls, services: RunnerServices) -> None:
        cls._services = services
        set_global_services(services)

    # ==================================================================
    # PRIMARY API: Runner.submit() - Single entry point for QMTL v2.0
    # ==================================================================

    @classmethod
    def submit(
        cls,
        strategy_cls: type[Strategy],
        *,
        world: str | None = None,
        mode: Mode | str = Mode.BACKTEST,
        preset: str | None = None,
        preset_mode: str | None = None,
        preset_version: str | None = None,
        preset_overrides: dict[str, float] | None = None,
        data_preset: str | None = None,
        returns: list[float] | None = None,
        auto_validate: bool = True,
    ) -> SubmitResult:
        """Submit a strategy for evaluation and potential activation.
        
        This is the single entry point for all strategy submissions in QMTL v2.0.
        The system automatically:
        1. Registers the strategy DAG
        2. Runs backtest validation
        3. Calculates performance metrics
        4. Activates valid strategies with appropriate weight
        
        Parameters
        ----------
        strategy_cls : type[Strategy]
            Strategy class to submit.
        world : str, optional
            Target world for the strategy. Uses QMTL_DEFAULT_WORLD env var
            or "__default__" if not specified.
        mode : Mode | str
            Execution mode: "backtest", "paper", or "live".
            Default is "backtest" for validation.
        
        Returns
        -------
        SubmitResult
            Result containing strategy_id, status, and metrics.
        
        Examples
        --------
        >>> result = Runner.submit(MyStrategy)
        >>> print(result.status)  # "active" or "rejected"
        >>> print(result.contribution)  # 0.023 (2.3% contribution)
        
        >>> result = Runner.submit(MyStrategy, world="prod", mode="live")
        """
        return submit(
            strategy_cls,
            world=world,
            mode=mode,
            preset=preset,
            preset_mode=preset_mode,
            preset_version=preset_version,
            preset_overrides=preset_overrides,
            data_preset=data_preset,
            returns=returns,
            auto_validate=auto_validate,
        )

    @classmethod
    async def submit_async(
        cls,
        strategy_cls: type[Strategy],
        *,
        world: str | None = None,
        mode: Mode | str = Mode.BACKTEST,
        preset: str | None = None,
        preset_mode: str | None = None,
        preset_version: str | None = None,
        preset_overrides: dict[str, float] | None = None,
        data_preset: str | None = None,
        returns: list[float] | None = None,
        auto_validate: bool = True,
    ) -> SubmitResult:
        """Async version of submit(). See submit() for details."""
        return await submit_async(
            strategy_cls,
            world=world,
            mode=mode,
            preset=preset,
            preset_mode=preset_mode,
            preset_version=preset_version,
            preset_overrides=preset_overrides,
            data_preset=data_preset,
            returns=returns,
            auto_validate=auto_validate,
        )

    # ==================================================================
    # Internal configuration methods
    # ==================================================================

    @classmethod
    def set_gateway_circuit_breaker(cls, cb: AsyncCircuitBreaker | None) -> None:
        """Configure circuit breaker for Gateway communication."""
        cls.services().gateway_client.set_circuit_breaker(cb)

    @classmethod
    def set_gateway_client(cls, client: GatewayClient) -> None:
        """Inject a custom ``GatewayClient`` instance."""
        cls.services().set_gateway_client(client)

    @classmethod
    def set_activation_manager(cls, am: ActivationManager | None) -> None:
        """Inject or clear the activation manager (for tests or custom wiring)."""
        cls.services().set_activation_manager(am)

    @classmethod
    def set_default_context(cls, context: Mapping[str, str] | None) -> None:
        """Register default compute context values for subsequent runs."""
        cls._default_context = normalize_default_context(context)

    @classmethod
    def _resolve_context(
        cls,
        *,
        context: Mapping[str, str] | None,
        execution_mode: str | None,
        execution_domain: str | None,
        clock: str | None,
        as_of: object | None,
        dataset_fingerprint: str | None,
        offline_requested: bool,
        gateway_url: str | None,
    ) -> tuple[dict[str, str], bool]:
        resolution = resolve_execution_context(
            cls._default_context,
            context=context,
            execution_mode=execution_mode,
            execution_domain=execution_domain,
            clock=clock,
            as_of=as_of,
            dataset_fingerprint=dataset_fingerprint,
            offline_requested=offline_requested,
            gateway_url=gateway_url,
            trade_mode=cls._trade_mode,
        )
        if resolution.force_offline and gateway_url and not offline_requested:
            logger.warning(
                "Missing dataset metadata for %s run; forcing compute-only mode",
                resolution.context.get("execution_mode"),
            )
        if resolution.downgraded or resolution.safe_mode:
            reason = resolution.downgrade_reason or "unknown"
            logger.warning(
                "Execution context downgraded to safe compute-only path",
                extra={
                    "reason": reason,
                    "execution_mode": resolution.context.get("execution_mode"),
                    "execution_domain": resolution.context.get("execution_domain"),
                },
            )
            try:
                sdk_metrics.execution_domain_downgrade_total.labels(reason=reason).inc()
            except Exception:  # pragma: no cover - metrics best-effort
                logger.debug("Failed to record downgrade metric", exc_info=True)
        return resolution.context, resolution.force_offline

    # ------------------------------------------------------------------

    @classmethod
    def set_feature_artifact_plane(
        cls, plane: "FeatureArtifactPlane | None"
    ) -> None:
        """Override the global feature artifact plane."""

        cls.services().set_feature_plane(plane)

    @classmethod
    def feature_artifact_plane(cls) -> "FeatureArtifactPlane | None":
        """Return the configured feature artifact plane if enabled."""

        return cls.services().feature_plane

    @staticmethod
    def _prepare(strategy_cls: type[Strategy]) -> Strategy:
        strategy = strategy_cls()
        strategy.setup()
        return strategy

    @staticmethod
    def feed_queue_data(
        node,
        queue_id: str,
        interval: int,
        timestamp: int,
        payload,
        *,
        on_missing: str = "skip",
    ):
        """Insert queue data into ``node`` and trigger its ``compute_fn``.

        Returns the compute function result when executed locally. ``None`` is
        returned if the node did not run or Ray was used for execution.
        """
        ready = node.feed(
            queue_id,
            interval,
            timestamp,
            payload,
            on_missing=on_missing,
        )

        result = None
        services = Runner.services()
        plane = services.feature_plane
        if ready and node.execute and node.compute_fn:
            start = time.perf_counter()
            try:
                with tracer.start_as_current_span(
                    "node.process", attributes={"node.id": node.node_id}
                ):
                    view = node.cache.view(artifact_plane=plane)
                    execution_result = services.ray_executor.execute(
                        node.compute_fn, view
                    )
                    if execution_result is not None:
                        result = execution_result
                        Runner._postprocess_result(node, result)
            except Exception:
                sdk_metrics.observe_node_process_failure(node.node_id)
                raise
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                sdk_metrics.observe_node_process(node.node_id, duration_ms)
            if plane is not None and result is not None:
                plane.record(node, timestamp, result)
        return result

    # ------------------------------------------------------------------
    @staticmethod
    async def _consume_node(
        node,
        *,
        consumer_factory: KafkaConsumerFactory,
        bootstrap_servers: str,
        stop_event: asyncio.Event,
    ) -> None:
        """Consume Kafka messages for ``node`` and feed them into the cache."""
        if not consumer_factory.available:
            raise RuntimeError("aiokafka not available")
        consumer = consumer_factory.create_consumer(
            node.kafka_topic, bootstrap_servers=bootstrap_servers
        )
        await consumer.start()
        try:
            while not stop_event.is_set():
                batch = await consumer.getmany(timeout_ms=200)
                got = False
                for _tp, messages in batch.items():
                    for msg in messages:
                        got = True
                        try:
                            payload = json.loads(msg.value)
                        except Exception:
                            payload = msg.value
                        ts = int(msg.timestamp / 1000)
                        Runner.feed_queue_data(
                            node,
                            node.kafka_topic,
                            node.interval,
                            ts,
                            payload,
                        )
                if not got:
                    # No messages; loop to re-check stop_event promptly
                    continue
        finally:
            await consumer.stop()

    @staticmethod
    def spawn_consumer_tasks(
        strategy: Strategy,
        *,
        bootstrap_servers: str,
        stop_event: asyncio.Event,
    ) -> list[asyncio.Task]:
        """Spawn Kafka consumer tasks for nodes with a ``kafka_topic``."""
        tasks = []
        factory = Runner.services().kafka_factory
        for n in strategy.nodes:
            if n.kafka_topic:
                tasks.append(
                    asyncio.create_task(
                        Runner._consume_node(
                            n,
                            consumer_factory=factory,
                            bootstrap_servers=bootstrap_servers,
                            stop_event=stop_event,
                        )
                    )
                )
        return tasks

    # ------------------------------------------------------------------
    @staticmethod
    def run_pipeline(strategy: Strategy) -> None:
        """Execute a :class:`Pipeline` using cached history from ``strategy``."""
        import importlib

        pipeline_mod = importlib.import_module("qmtl.runtime.pipeline")
        Pipeline = getattr(pipeline_mod, "Pipeline")
        pipeline = Pipeline(strategy.nodes)
        events = Runner.services().history_service.collect_history_events(
            strategy, None, None
        )
        for ts, node, payload in events:
            pipeline.feed(node, ts, payload)

    @staticmethod
    def _maybe_int(value) -> int | None:
        try:
            return int(value)
        except Exception:
            return None

    @staticmethod
    async def _maybe_refresh_capabilities(gateway_url: str | None) -> None:
        if gateway_url:
            await Runner._refresh_gateway_capabilities(gateway_url)

    @staticmethod
    async def _bootstrap_strategy(
        services,
        strategy: Strategy,
        compute_context: ComputeContext,
        world_id: str,
        gateway_url: str | None,
        meta_payload: dict | None,
        schema_enforcement: str,
    ):
        bootstrapper = StrategyBootstrapper(services.gateway_client)
        return await bootstrapper.bootstrap(
            strategy,
            context=compute_context,
            world_id=world_id,
            gateway_url=gateway_url,
            meta=meta_payload,
            offline=False,
            kafka_available=services.kafka_factory.available,
            trade_mode=Runner._trade_mode,
            schema_enforcement=schema_enforcement,
            feature_plane=services.feature_plane,
            gateway_context=None,
            skip_gateway_submission=False,
        )

    @staticmethod
    async def _configure_activation(
        services,
        strategy_id: str | None,
        gateway_url: str | None,
        world_id: str,
        offline_mode: bool,
    ) -> None:
        if gateway_url and not offline_mode:
            try:
                activation_manager = services.ensure_activation_manager(
                    gateway_url=gateway_url,
                    world_id=world_id,
                    strategy_id=strategy_id,
                )
                services.trade_dispatcher.set_activation_manager(activation_manager)
                await activation_manager.start()
                return
            except Exception:
                logger.warning(
                    "Activation manager failed to start; proceeding with gates OFF by default"
                )
        services.trade_dispatcher.set_activation_manager(services.activation_manager)

    # ------------------------------------------------------------------
    # Cleanup helpers for tests and graceful shutdown
    # ------------------------------------------------------------------

    @staticmethod
    async def shutdown_async(strategy: Strategy | None = None) -> None:
        """Stop background services started by Runner.

        - Stops the strategy's TagQueryManager if present
        - Stops the global ActivationManager if running
        """
        # Stop TagQueryManager attached to strategy
        first_error: Exception | None = None
        if strategy is not None:
            mgr = cast(TagQueryManagerProtocol | None, getattr(strategy, "tag_query_manager", None))
            if mgr is not None:
                try:
                    await mgr.stop()
                except Exception as exc:
                    logger.exception("Failed to stop TagQueryManager during shutdown")
                    if first_error is None:
                        first_error = exc
        # Stop ActivationManager if present
        services = Runner.services()
        am = services.activation_manager
        if am is not None:
            try:
                await am.stop()
            except Exception as exc:
                logger.exception("Failed to stop ActivationManager during shutdown")
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise first_error

    @staticmethod
    def shutdown(strategy: Strategy | None = None) -> None:
        """Synchronous wrapper around :meth:`shutdown_async`."""
        try:
            asyncio.run(Runner.shutdown_async(strategy))
        except RuntimeError:
            # Already inside an event loop (e.g., pytest); ignore
            pass

    # ------------------------------------------------------------------
    # Trade execution and postprocessing methods
    # ------------------------------------------------------------------

    @classmethod
    def set_trade_execution_service(cls, service) -> None:
        """Set the trade execution service."""
        cls.services().set_trade_execution_service(service)

    @classmethod
    def set_kafka_producer(cls, producer) -> None:
        """Set the Kafka producer for trade orders."""
        cls.services().set_kafka_producer(producer)

    @classmethod
    def set_trade_order_http_url(cls, url: str | None) -> None:
        """Set HTTP URL for trade order submission."""
        cls.services().set_trade_order_http_url(url)

    @classmethod
    def set_trade_order_kafka_topic(cls, topic: str | None) -> None:
        """Set Kafka topic for trade order submission."""
        cls.services().set_trade_order_kafka_topic(topic)

    @classmethod
    def set_enable_trade_submission(cls, enabled: bool) -> None:
        """Enable/disable trade order submission and pre-trade chain.

        When disabled, Runner will not forward publisher outputs to execution
        services or sinks. This is useful for dry runs and tests.
        """
        cls._enable_trade_submission = bool(enabled)

    @staticmethod
    def _extract_alpha_value(result: Mapping[str, object], name: str) -> float | None:
        prefixed = f"alpha_performance.{name}"
        candidates = (prefixed, name)
        for key in candidates:
            if key in result:
                raw_value = result[key]
                if isinstance(raw_value, (int, float)):
                    return float(raw_value)
                if isinstance(raw_value, str):
                    try:
                        return float(raw_value)
                    except ValueError:
                        return None
                return None
        return None

    @staticmethod
    def _set_metric_value(metric: MetricWithValueProtocol, value: float) -> None:
        metric.set(value)
        metric._val = value

    @staticmethod
    def _handle_alpha_performance(result: object) -> None:
        """Handle alpha performance metrics."""
        from . import metrics as sdk_metrics

        if not isinstance(result, Mapping):
            return

        sharpe_value = Runner._extract_alpha_value(result, "sharpe")
        if sharpe_value is not None:
            Runner._set_metric_value(sdk_metrics.alpha_sharpe, sharpe_value)

        max_dd_value = Runner._extract_alpha_value(result, "max_drawdown")
        if max_dd_value is not None:
            Runner._set_metric_value(sdk_metrics.alpha_max_drawdown, max_dd_value)

    @classmethod
    def _handle_trade_order(cls, order: dict) -> None:
        """Handle trade order submission via the configured dispatcher."""

        cls.services().trade_dispatcher.dispatch(order)

    @staticmethod
    def _postprocess_result(node, result) -> None:
        """Postprocess computation results from nodes."""
        if result is None:
            return

        # Handle different node types
        node_class_name = node.__class__.__name__

        # Check if this is an alpha performance node
        if "AlphaPerformance" in node_class_name:
            Runner._handle_alpha_performance(result)

        # Check if this is a trade order publisher node
        if "TradeOrderPublisher" in node_class_name:
            execution_domain = getattr(
                getattr(node, "compute_context", None), "execution_domain", None
            )
            if str(execution_domain or "").strip().lower() == "shadow":
                logger.info("Skipping trade dispatch in shadow execution_domain")
                return

            if Runner._enable_trade_submission:
                Runner._handle_trade_order(result)

    # ----------------------------
    # Utilities for tests/ops
    # ----------------------------
    @classmethod
    def reset_trade_order_dedup(cls) -> None:
        """Clear idempotency cache for tests."""
        cls.services().reset_trade_order_dedup()

    @classmethod
    def set_trade_mode(cls, mode: str) -> None:
        """Set trade mode: 'simulate' or 'live' (informational)."""
        if mode not in {"simulate", "live"}:
            raise ValueError("mode must be 'simulate' or 'live'")
        cls._trade_mode = mode
