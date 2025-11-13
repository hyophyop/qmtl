from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from typing import Mapping, Optional, TYPE_CHECKING

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
from .services import RunnerServices
from .strategy import Strategy
from .strategy_bootstrapper import StrategyBootstrapper
from .tag_manager_service import TagManagerService

if TYPE_CHECKING:
    from .activation_manager import ActivationManager
    from .gateway_client import GatewayClient
    from .feature_store import FeatureArtifactPlane


if "_runner_services" not in globals():
    _runner_services = RunnerServices.default()
else:
    _runner_services.ray_executor = RayExecutor()
    _runner_services.kafka_factory = KafkaConsumerFactory()


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
        if not isinstance(health, dict):
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

    # ------------------------------------------------------------------
    # Backward mode-specific APIs removed; Runner adheres to WS decisions.
    # Use run(world_id=..., gateway_url=...) or offline().
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    @staticmethod
    def _missing_ranges(
        coverage, start: int, end: int, interval: int
    ) -> list[tuple[int, int]]:
        """Proxy to :class:`HistoryWarmupService` for compatibility."""

        return Runner.services().history_service.missing_ranges(
            coverage, start, end, interval
        )

    @staticmethod
    async def _ensure_history(
        strategy: Strategy,
        start: int | None = None,
        end: int | None = None,
        *,
        stop_on_ready: bool = False,
        strict: bool = False,
    ) -> None:
        """Proxy to history service for backward compatibility."""

        await Runner.services().history_service.ensure_history(
            strategy,
            start,
            end,
            stop_on_ready=stop_on_ready,
            strict=strict,
        )

    @staticmethod
    def _hydrate_snapshots(strategy: Strategy) -> int:
        """Proxy to history service for backwards compatibility."""

        return Runner.services().history_service.hydrate_snapshots(strategy)

    @staticmethod
    def _write_snapshots(strategy: Strategy) -> int:
        """Proxy to history service for backwards compatibility."""

        return Runner.services().history_service.write_snapshots(strategy)

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
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
    def _collect_history_events(
        strategy: Strategy, start: int | None, end: int | None
    ) -> list[tuple[int, any, any]]:
        """Proxy to history service for backwards compatibility."""

        return Runner.services().history_service.collect_history_events(
            strategy, start, end
        )

    @staticmethod
    def run_pipeline(strategy: Strategy) -> None:
        """Execute a :class:`Pipeline` using cached history from ``strategy``."""
        from qmtl.runtime.pipeline import Pipeline

        pipeline = Pipeline(strategy.nodes)
        events = Runner._collect_history_events(strategy, None, None)
        for ts, node, payload in events:
            pipeline.feed(node, ts, payload)

    @staticmethod
    def _replay_events_simple(strategy: Strategy) -> None:
        """Proxy to history service for deterministic replay."""

        Runner.services().history_service.replay_events_simple(strategy)

    @staticmethod
    def _maybe_int(value) -> int | None:
        try:
            return int(value)
        except Exception:
            return None

    @staticmethod
    async def _replay_history(
        strategy: Strategy,
        start: int | None,
        end: int | None,
        *,
        on_missing: str = "skip",
    ) -> None:
        """Proxy to history service for backward compatibility."""

        await Runner.services().history_service.replay_history(
            strategy, start, end, on_missing=on_missing
        )

    @staticmethod
    def _replay_history_events(
        strategy: Strategy,
        events: list[tuple[int, any, any]],
        *,
        on_missing: str = "skip",
    ) -> None:
        """Proxy to history service for backward compatibility."""

        Runner.services().history_service.replay_history_events(
            strategy, events, on_missing=on_missing
        )

    @staticmethod
    async def run_async(
        strategy_cls: type[Strategy],
        *,
        world_id: str,
        gateway_url: str | None = None,
        meta: Optional[dict] = None,
        history_start: object | None = None,
        history_end: object | None = None,
        schema_enforcement: str = "fail",
    ) -> Strategy:
        """Run a strategy for ``world_id`` with minimal caller input.

        Preferred usage defers execution decisions entirely to backend services:

            Runner.run_async(StrategyCls, world_id=..., gateway_url=...)

        The SDK does not choose execution domains or clocks. Order gating and
        promotions are driven by WorldService decisions relayed by Gateway.
        """
        services = Runner.services()
        strategy = Runner._prepare(strategy_cls)
        # Minimal compute context; backend decisions determine effective domain.
        compute_context = ComputeContext(world_id=world_id, execution_domain=DEFAULT_EXECUTION_DOMAIN)
        setattr(strategy, "compute_context", {"world_id": world_id})

        meta_payload: dict | None = dict(meta) if isinstance(meta, dict) else None

        effective_offline = False
        cleanup_needed = True
        try:
            strategy.on_start()
            if gateway_url and not effective_offline:
                await Runner._refresh_gateway_capabilities(gateway_url)

            bootstrapper = StrategyBootstrapper(services.gateway_client)
            bootstrap_result = await bootstrapper.bootstrap(
                strategy,
                context=compute_context,
                world_id=world_id,
                gateway_url=gateway_url,
                meta=meta_payload,
                offline=effective_offline,
                kafka_available=services.kafka_factory.available,
                trade_mode=Runner._trade_mode,
                schema_enforcement=schema_enforcement,
                feature_plane=services.feature_plane,
                gateway_context=None,
                skip_gateway_submission=False,
            )
            manager = bootstrap_result.manager
            offline_mode = bootstrap_result.offline_mode
            if bootstrap_result.completed:
                cleanup_needed = False
                return strategy

            if gateway_url and not offline_mode:
                try:
                    activation_manager = services.ensure_activation_manager(
                        gateway_url=gateway_url,
                        world_id=world_id,
                        strategy_id=bootstrap_result.strategy_id,
                    )
                    services.trade_dispatcher.set_activation_manager(
                        activation_manager
                    )
                    await activation_manager.start()
                except Exception:
                    logger.warning(
                        "Activation manager failed to start; proceeding with gates OFF by default"
                    )
            else:
                services.trade_dispatcher.set_activation_manager(
                    services.activation_manager
                )

            history_service = services.history_service
            await history_service.warmup_strategy(
                strategy,
                offline_mode=offline_mode,
                history_start=history_start,
                history_end=history_end,
            )

            if not offline_mode:
                await manager.start()

            history_service.write_snapshots(strategy)
            strategy.on_finish()
            cleanup_needed = False
            return strategy

        except Exception as e:
            try:
                strategy.on_error(e)
            except Exception:
                logger.exception("strategy.on_error raised during failure handling")
            raise
        finally:
            if cleanup_needed:
                try:
                    await Runner.shutdown_async(strategy)
                except Exception:
                    logger.exception("Runner shutdown failed after initialization error")

    @staticmethod
    def run(
        strategy_cls: type[Strategy],
        *,
        world_id: str,
        gateway_url: str | None = None,
        meta: Optional[dict] = None,
        history_start: object | None = None,
        history_end: object | None = None,
        schema_enforcement: str = "fail",
    ) -> Strategy:
        """Synchronous wrapper around :meth:`run_async`.

        Prefer the minimal form:

            Runner.run(StrategyCls, world_id=..., gateway_url=...)

        This call keeps parameters minimal and does not expose execution domain
        or clock controls. For offline/local runs, use :meth:`offline`.
        """
        return asyncio.run(
            Runner.run_async(
                strategy_cls,
                world_id=world_id,
                gateway_url=gateway_url,
                meta=meta,
                history_start=history_start,
                history_end=history_end,
                schema_enforcement=schema_enforcement,
            )
        )

    @staticmethod
    def offline(
        strategy_cls: type[Strategy], *, schema_enforcement: str = "fail"
    ) -> Strategy:
        """Execute ``strategy_cls`` locally without Gateway interaction."""
        return asyncio.run(
            Runner.offline_async(strategy_cls, schema_enforcement=schema_enforcement)
        )

    @staticmethod
    async def offline_async(
        strategy_cls: type[Strategy], *, schema_enforcement: str = "fail"
    ) -> Strategy:
        services = Runner.services()
        strategy = Runner._prepare(strategy_cls)
        # Lifecycle start
        try:
            strategy.on_start()
        except Exception as e:
            strategy.on_error(e)
            raise
        context = ComputeContext(world_id="w", execution_domain="offline")
        for n in strategy.nodes:
            setattr(n, "_schema_enforcement", schema_enforcement)
            try:
                n.apply_compute_context(context)
            except AttributeError:
                pass
        tag_service = TagManagerService(None)
        # Use a stable default world id for offline execution so that
        # node IDs match typical offline test runs.
        try:
            manager = tag_service.init(strategy, world_id="w")
        except TypeError:
            manager = tag_service.init(strategy)
        logger.info(f"[OFFLINE] {strategy_cls.__name__} starting")
        setattr(strategy, "compute_context", {"world_id": "w", "execution_domain": "offline"})
        tag_service.apply_queue_map(strategy, {})
        await manager.resolve_tags(offline=True)
        # Hydrate + warm-up history (provider-driven when available), then replay
        history_service = services.history_service
        await history_service.warmup_strategy(
            strategy,
            offline_mode=True,
            history_start=None,
            history_end=None,
        )
        # After replay, write a fresh snapshot for faster next start
        history_service.write_snapshots(strategy)
        # Lifecycle finish
        try:
            strategy.on_finish()
        except Exception as e:
            strategy.on_error(e)
            raise
        return strategy

    # ------------------------------------------------------------------
    # Convenience context manager for tests
    # ------------------------------------------------------------------

    @staticmethod
    @asynccontextmanager
    async def session(strategy_cls: type[Strategy], **kwargs):
        """Run ``strategy_cls`` and ensure cleanup on exit.

        Yields the initialized strategy and guarantees that
        :meth:`shutdown_async` is invoked after the ``async with`` block
        exits, simplifying test teardown.
        """
        strategy = await Runner.run_async(strategy_cls, **kwargs)
        try:
            yield strategy
        finally:
            await Runner.shutdown_async(strategy)

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
            mgr = getattr(strategy, "tag_query_manager", None)
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
    def _handle_alpha_performance(result: dict) -> None:
        """Handle alpha performance metrics."""
        from . import metrics as sdk_metrics

        if isinstance(result, dict):
            def _value(name: str) -> float | None:
                prefixed = f"alpha_performance.{name}"
                if prefixed in result:
                    return result[prefixed]
                if name in result:
                    return result[name]
                return None

            sharpe_value = _value("sharpe")
            if sharpe_value is not None:
                sdk_metrics.alpha_sharpe.set(sharpe_value)
                sdk_metrics.alpha_sharpe._val = sharpe_value  # type: ignore[attr-defined]
            max_dd_value = _value("max_drawdown")
            if max_dd_value is not None:
                sdk_metrics.alpha_max_drawdown.set(max_dd_value)
                sdk_metrics.alpha_max_drawdown._val = max_dd_value  # type: ignore[attr-defined]

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
        if "TradeOrderPublisher" in node_class_name and Runner._enable_trade_submission:
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
