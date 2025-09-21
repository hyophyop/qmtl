from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from typing import Optional
import logging

from opentelemetry import trace

from qmtl.common.tracing import setup_tracing
from qmtl.common.compute_key import ComputeContext, DEFAULT_EXECUTION_DOMAIN
from cachetools import TTLCache
from qmtl.common import AsyncCircuitBreaker

logger = logging.getLogger(__name__)

setup_tracing("sdk")
tracer = trace.get_tracer(__name__)

from .strategy import Strategy
from .gateway_client import GatewayClient
from .tag_manager_service import TagManagerService
from .activation_manager import ActivationManager
from .history_warmup_service import HistoryWarmupService
from .strategy_bootstrapper import StrategyBootstrapper
from .trade_dispatcher import TradeOrderDispatcher
from . import runtime, metrics as sdk_metrics
from .feature_store import FeatureArtifactPlane

try:  # Optional aiokafka dependency
    from aiokafka import AIOKafkaConsumer  # type: ignore
except Exception:  # pragma: no cover - aiokafka not installed
    AIOKafkaConsumer = None  # type: ignore
try:  # Optional Ray dependency
    import ray  # type: ignore
except Exception:  # pragma: no cover - Ray not installed
    ray = None  # type: ignore


# Global trade execution service, kept across reloads
if "_trade_execution_service_sentinel" not in globals():
    _trade_execution_service_sentinel = object()
if "_trade_execution_service" not in globals():
    _trade_execution_service = _trade_execution_service_sentinel


class Runner:
    """Execute strategies in various modes."""

    _ray_available = ray is not None
    _kafka_available = AIOKafkaConsumer is not None
    _gateway_client: GatewayClient = GatewayClient()
    _trade_execution_service = _trade_execution_service
    _kafka_producer = None
    _trade_order_http_url = None
    _trade_order_kafka_topic = None
    _activation_manager: ActivationManager | None = None
    _enable_trade_submission: bool = True
    _order_dedup: TTLCache[str, bool] | None = TTLCache(maxsize=10000, ttl=600)
    _trade_mode: str = "simulate"  # simulate | live (non-breaking; informational)
    _feature_artifact_plane: FeatureArtifactPlane | None = FeatureArtifactPlane.from_env()
    _history_service: HistoryWarmupService = HistoryWarmupService()
    _trade_dispatcher: TradeOrderDispatcher = TradeOrderDispatcher(
        dedup_cache=_order_dedup,
        activation_manager=_activation_manager,
        trade_execution_service=(
            None
            if _trade_execution_service is _trade_execution_service_sentinel
            else _trade_execution_service
        ),
        trade_order_http_url=_trade_order_http_url,
        kafka_producer=_kafka_producer,
        trade_order_kafka_topic=_trade_order_kafka_topic,
    )

    # ------------------------------------------------------------------
    # Backward mode-specific APIs removed; Runner adheres to WS decisions.
    # Use run(world_id=..., gateway_url=...) or offline().
    # ------------------------------------------------------------------

    @classmethod
    def set_gateway_circuit_breaker(cls, cb: AsyncCircuitBreaker | None) -> None:
        """Configure circuit breaker for Gateway communication."""
        cls._gateway_client.set_circuit_breaker(cb)

    @classmethod
    def set_gateway_client(cls, client: GatewayClient) -> None:
        """Inject a custom ``GatewayClient`` instance."""
        cls._gateway_client = client

    @classmethod
    def set_activation_manager(cls, am: ActivationManager | None) -> None:
        """Inject or clear the activation manager (for tests or custom wiring)."""
        cls._activation_manager = am
        cls._trade_dispatcher.set_activation_manager(am)

    # ------------------------------------------------------------------

    @staticmethod
    def _execute_compute_fn(fn, cache_view) -> None:
        """Run ``fn`` using Ray when available."""
        if Runner._ray_available and not runtime.NO_RAY and ray is not None:
            if not ray.is_initialized():  # type: ignore[attr-defined]
                ray.init(ignore_reinit_error=True)  # type: ignore[attr-defined]
            ray.remote(fn).remote(cache_view)  # type: ignore[attr-defined]
        else:
            fn(cache_view)

    @classmethod
    def set_feature_artifact_plane(
        cls, plane: FeatureArtifactPlane | None
    ) -> None:
        """Override the global feature artifact plane."""

        cls._feature_artifact_plane = plane

    @classmethod
    def feature_artifact_plane(cls) -> FeatureArtifactPlane | None:
        """Return the configured feature artifact plane if enabled."""

        return cls._feature_artifact_plane

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

        return Runner._history_service.missing_ranges(coverage, start, end, interval)

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

        await Runner._history_service.ensure_history(
            strategy,
            start,
            end,
            stop_on_ready=stop_on_ready,
            strict=strict,
        )

    @staticmethod
    def _hydrate_snapshots(strategy: Strategy) -> int:
        """Proxy to history service for backwards compatibility."""

        return Runner._history_service.hydrate_snapshots(strategy)

    @staticmethod
    def _write_snapshots(strategy: Strategy) -> int:
        """Proxy to history service for backwards compatibility."""

        return Runner._history_service.write_snapshots(strategy)

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
        plane = Runner.feature_artifact_plane()
        if ready and node.execute and node.compute_fn:
            start = time.perf_counter()
            try:
                with tracer.start_as_current_span(
                    "node.process", attributes={"node.id": node.node_id}
                ):
                    view = node.cache.view(artifact_plane=plane)
                    if Runner._ray_available and not runtime.NO_RAY and ray is not None:
                        Runner._execute_compute_fn(node.compute_fn, view)
                    else:
                        result = node.compute_fn(view)
                        # Postprocess the result
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
        bootstrap_servers: str,
        stop_event: asyncio.Event,
    ) -> None:
        """Consume Kafka messages for ``node`` and feed them into the cache."""
        if not Runner._kafka_available:
            raise RuntimeError("aiokafka not available")
        consumer = AIOKafkaConsumer(
            node.kafka_topic,
            bootstrap_servers=bootstrap_servers,
            enable_auto_commit=True,
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
        for n in strategy.nodes:
            if n.kafka_topic:
                tasks.append(
                    asyncio.create_task(
                        Runner._consume_node(
                            n,
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

        return Runner._history_service.collect_history_events(
            strategy, start, end
        )

    @staticmethod
    def run_pipeline(strategy: Strategy) -> None:
        """Execute a :class:`Pipeline` using cached history from ``strategy``."""
        from qmtl import Pipeline

        pipeline = Pipeline(strategy.nodes)
        events = Runner._collect_history_events(strategy, None, None)
        for ts, node, payload in events:
            pipeline.feed(node, ts, payload)

    @staticmethod
    def _replay_events_simple(strategy: Strategy) -> None:
        """Proxy to history service for deterministic replay."""

        Runner._history_service.replay_events_simple(strategy)

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

        await Runner._history_service.replay_history(
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

        Runner._history_service.replay_history_events(
            strategy, events, on_missing=on_missing
        )

    @staticmethod
    async def run_async(
        strategy_cls: type[Strategy],
        *,
        world_id: str,
        gateway_url: str | None = None,
        meta: Optional[dict] = None,
        offline: bool = False,
        history_start: object | None = None,
        history_end: object | None = None,
        schema_enforcement: str = "fail",
        execution_domain: str = DEFAULT_EXECUTION_DOMAIN,
        as_of: object | None = None,
        partition: object | None = None,
    ) -> Strategy:
        """Run a strategy under a given world, following WS decisions/activation.

        In offline mode or when Kafka is unavailable, executes compute‑only locally.
        """
        strategy = Runner._prepare(strategy_cls)
        context = ComputeContext(
            world_id=world_id,
            execution_domain=execution_domain,
            as_of=as_of,
            partition=partition,
        )
        dataset_fingerprint: str | None = None
        for n in strategy.nodes:
            setattr(n, "_schema_enforcement", schema_enforcement)
            try:
                n.apply_compute_context(context)
            except AttributeError:
                pass
        try:
            strategy.on_start()

            bootstrapper = StrategyBootstrapper(Runner._gateway_client)
            bootstrap_result = await bootstrapper.bootstrap(
                strategy,
                context=context,
                world_id=world_id,
                gateway_url=gateway_url,
                meta=meta,
                offline=offline,
                kafka_available=Runner._kafka_available,
                trade_mode=Runner._trade_mode,
                schema_enforcement=schema_enforcement,
                feature_plane=Runner._feature_artifact_plane,
            )
            manager = bootstrap_result.manager
            offline_mode = bootstrap_result.offline_mode
            if bootstrap_result.completed:
                return strategy

            if gateway_url and not offline_mode:
                try:
                    if Runner._activation_manager is None:
                        Runner._activation_manager = ActivationManager(
                            gateway_url, world_id=world_id, strategy_id=None
                        )
                    Runner._trade_dispatcher.set_activation_manager(
                        Runner._activation_manager
                    )
                    await Runner._activation_manager.start()
                except Exception:
                    logger.warning(
                        "Activation manager failed to start; proceeding with gates OFF by default"
                    )
            else:
                Runner._trade_dispatcher.set_activation_manager(
                    Runner._activation_manager
                )

            history_service = Runner._history_service
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
            return strategy

        except Exception as e:
            strategy.on_error(e)
            raise

    @staticmethod
    def run(
        strategy_cls: type[Strategy],
        *,
        world_id: str,
        gateway_url: str | None = None,
        meta: Optional[dict] = None,
        offline: bool = False,
        history_start: object | None = None,
        history_end: object | None = None,
        schema_enforcement: str = "fail",
        execution_domain: str = DEFAULT_EXECUTION_DOMAIN,
        as_of: object | None = None,
        partition: object | None = None,
    ) -> Strategy:
        return asyncio.run(
            Runner.run_async(
                strategy_cls,
                world_id=world_id,
                gateway_url=gateway_url,
                meta=meta,
                offline=offline,
                history_start=history_start,
                history_end=history_end,
                schema_enforcement=schema_enforcement,
                execution_domain=execution_domain,
                as_of=as_of,
                partition=partition,
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
        strategy = Runner._prepare(strategy_cls)
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
        tag_service.apply_queue_map(strategy, {})
        await manager.resolve_tags(offline=True)
        # Hydrate from snapshots first, then fill any gaps from history
        history_service = Runner._history_service
        history_service.hydrate_snapshots(strategy)
        await history_service.load_history(strategy, None, None)
        # After replay, write a fresh snapshot for faster next start
        history_service.write_snapshots(strategy)
        await history_service.replay_history(strategy, None, None)
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
        if strategy is not None:
            mgr = getattr(strategy, "tag_query_manager", None)
            if mgr is not None:
                try:
                    await mgr.stop()
                except Exception:
                    pass
        # Stop ActivationManager if present
        am = Runner._activation_manager
        if am is not None:
            try:
                await am.stop()
            except Exception:
                pass

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
        global _trade_execution_service
        _trade_execution_service = service
        cls._trade_execution_service = service
        cls._trade_dispatcher.set_trade_execution_service(service)

    @classmethod
    def set_kafka_producer(cls, producer) -> None:
        """Set the Kafka producer for trade orders."""
        cls._kafka_producer = producer
        cls._trade_dispatcher.set_kafka_producer(producer)

    @classmethod
    def set_trade_order_http_url(cls, url: str | None) -> None:
        """Set HTTP URL for trade order submission."""
        cls._trade_order_http_url = url
        cls._trade_dispatcher.set_http_url(url)

    @classmethod
    def set_trade_order_kafka_topic(cls, topic: str | None) -> None:
        """Set Kafka topic for trade order submission."""
        cls._trade_order_kafka_topic = topic
        cls._trade_dispatcher.set_trade_order_kafka_topic(topic)

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
            if "sharpe" in result:
                sdk_metrics.alpha_sharpe.set(result["sharpe"])
                sdk_metrics.alpha_sharpe._val = result["sharpe"]  # type: ignore[attr-defined]
            if "max_drawdown" in result:
                sdk_metrics.alpha_max_drawdown.set(result["max_drawdown"])
                sdk_metrics.alpha_max_drawdown._val = result["max_drawdown"]  # type: ignore[attr-defined]

    @classmethod
    def _handle_trade_order(cls, order: dict) -> None:
        """Handle trade order submission via the configured dispatcher."""

        cls._trade_dispatcher.dispatch(order)

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
        cache = cls._order_dedup
        if cache is not None:
            cache.clear()
        cls._trade_dispatcher.reset_dedup()

    @classmethod
    def set_trade_mode(cls, mode: str) -> None:
        """Set trade mode: 'simulate' or 'live' (informational)."""
        if mode not in {"simulate", "live"}:
            raise ValueError("mode must be 'simulate' or 'live'")
        cls._trade_mode = mode
