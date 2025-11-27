from __future__ import annotations

import logging
import secrets
import asyncio
from contextlib import asynccontextmanager, suppress
from typing import Optional, Callable, Awaitable, Any

import redis.asyncio as redis
from fastapi import FastAPI, Request, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry import trace

from qmtl.foundation.common import AsyncCircuitBreaker

from . import metrics as gw_metrics
from .controlbus_consumer import ControlBusConsumer
from .dagmanager_client import DagManagerClient
from .database import Database, PostgresDatabase, MemoryDatabase, SQLiteDatabase
from .degradation import DegradationManager, DegradationLevel
from .event_descriptor import EventDescriptorConfig
from .event_handlers import create_event_router
from .fsm import StrategyFSM
from .gateway_health import GatewayHealthCapabilities
from .routes import create_api_router
from .strategy_manager import StrategyManager
from .world_client import Budget, WorldServiceClient
from .ws import WebSocketHub
from .commit_log_consumer import CommitLogConsumer
from .commit_log import CommitLogWriter
from .submission import ComputeContextService, SubmissionPipeline
from .shared_account_policy import SharedAccountPolicyConfig

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def create_app(
    redis_client: Optional[redis.Redis] = None,
    database: Optional[Database] = None,
    dag_client: Optional[DagManagerClient] = None,
    ws_hub: Optional[WebSocketHub] = None,
    controlbus_consumer: Optional[ControlBusConsumer] = None,
    commit_log_consumer: Optional[CommitLogConsumer] = None,
    commit_log_writer: Optional[CommitLogWriter] = None,
    commit_log_handler: Optional[
        Callable[[list[tuple[str, int, str, Any]]], Awaitable[None]]
    ] = None,
    world_client: Optional[WorldServiceClient] = None,
    event_config: EventDescriptorConfig | None = None,
    fill_producer: Any | None = None,
    *,
    insert_sentinel: bool = True,
    database_backend: str = "postgres",
    database_dsn: str | None = None,
    worldservice_url: str | None = None,
    worldservice_timeout: float = 0.3,
    worldservice_retries: int = 2,
    enable_worldservice_proxy: bool = True,
    enforce_live_guard: bool = True,
    rebalance_schema_version: int = 1,
    alpha_metrics_capable: bool = False,
    enable_otel: bool | None = None,
    enable_background: bool = True,
    shared_account_policy_config: SharedAccountPolicyConfig | None = None,
    health_capabilities: GatewayHealthCapabilities | None = None,
) -> FastAPI:
    capabilities = health_capabilities or GatewayHealthCapabilities(
        rebalance_schema_version=rebalance_schema_version,
        alpha_metrics_capable=alpha_metrics_capable,
    )
    redis_conn = redis_client or redis.Redis(host="localhost", port=6379, decode_responses=True)
    database_obj = _resolve_database(database, database_backend, database_dsn)
    dagmanager = dag_client or DagManagerClient("127.0.0.1:50051")

    world_client_local = _resolve_world_client(
        world_client,
        enable_worldservice_proxy,
        worldservice_url,
        worldservice_timeout,
        worldservice_retries,
        capabilities,
    )
    degradation = DegradationManager(redis_conn, database_obj, dagmanager, world_client_local)

    shared_context_service = ComputeContextService(world_client=world_client_local)
    manager = StrategyManager(
        redis=redis_conn,
        database=database_obj,
        fsm=StrategyFSM(redis=redis_conn, database=database_obj),
        degrade=degradation,
        insert_sentinel=insert_sentinel,
        commit_log_writer=commit_log_writer,
        context_service=shared_context_service,
        world_client=world_client_local,
    )
    event_cfg = _resolve_event_config(event_config)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        commit_task: asyncio.Task[None] | None = None
        commit_task = await _start_background(
            enable_background=enable_background,
            controlbus_consumer=controlbus_consumer,
            commit_log_consumer=commit_log_consumer,
            commit_log_handler=commit_log_handler,
            ws_hub=ws_hub,
        )
        try:
            yield
        finally:
            await _stop_background(
                commit_task=commit_task,
                ws_hub=ws_hub,
                controlbus_consumer=controlbus_consumer,
                commit_log_consumer=commit_log_consumer,
                commit_log_writer=commit_log_writer,
                dagmanager=dagmanager,
                database_obj=database_obj,
                redis_conn=redis_conn,
                world_client=world_client_local,
            )

    policy_config = shared_account_policy_config or SharedAccountPolicyConfig()
    shared_policy = policy_config.as_policy()

    app = FastAPI(lifespan=lifespan)
    # Opt-in FastAPI OpenTelemetry instrumentation to avoid resource warnings in tests
    # Default is disabled unless explicitly enabled via argument or env var
    _otel_enabled = bool(enable_otel)
    if _otel_enabled:
        FastAPIInstrumentor().instrument_app(app)
    app.state.database = database_obj
    app.state.degradation = degradation
    app.state.world_client = world_client_local
    app.state.enforce_live_guard = enforce_live_guard
    app.state.event_config = event_cfg
    app.state.ws_hub = ws_hub
    app.state.commit_log_consumer = commit_log_consumer
    app.state.commit_log_writer = commit_log_writer
    app.state.shared_account_policy = shared_policy
    app.state.health_capabilities = capabilities

    @app.middleware("http")
    async def _degrade_middleware(request: Request, call_next):
        level = degradation.level
        if level == DegradationLevel.STATIC:
            return Response(status_code=204, headers={"Retry-After": "30"})
        if (
            level == DegradationLevel.MINIMAL
            and request.url.path == "/strategies"
            and request.method.upper() == "POST"
        ):
            return Response(status_code=503)
        return await call_next(request)

    submission_pipeline = SubmissionPipeline(
        dagmanager,
        context_service=shared_context_service,
    )

    api_router = create_api_router(
        manager,
        redis_conn,
        database_obj,
        dagmanager,
        ws_hub,
        degradation,
        world_client_local,
        enforce_live_guard,
        rebalance_schema_version,
        alpha_metrics_capable,
        fill_producer,
        submission_pipeline=submission_pipeline,
        health_capabilities=capabilities,
    )
    app.include_router(api_router)
    # Expose event endpoints (subscribe/JWKS and WS bridge). Pass world and
    # dag clients so that initial snapshots/state hashes can be sent on
    # connection when topics are scoped.
    event_router = create_event_router(
        ws_hub, event_cfg, world_client=world_client_local, dagmanager=dagmanager
    )
    app.include_router(event_router)

    return app


def _resolve_database(
    database: Optional[Database],
    backend: str,
    dsn: str | None,
) -> Database:
    if database is not None:
        return database
    if backend == "postgres":
        return PostgresDatabase(dsn or "postgresql://localhost/qmtl")
    if backend == "memory":
        return MemoryDatabase()
    if backend == "sqlite":
        return SQLiteDatabase(dsn or ":memory:")
    raise ValueError(f"Unsupported database backend: {backend}")


def _resolve_world_client(
    world_client: WorldServiceClient | None,
    enable_proxy: bool,
    url: str | None,
    timeout: float,
    retries: int,
    capabilities: GatewayHealthCapabilities,
) -> WorldServiceClient | None:
    if world_client is None and enable_proxy and url is not None:
        budget = Budget(timeout=timeout, retries=retries)

        def _on_breaker_open() -> None:
            gw_metrics.worlds_breaker_state.set(1)
            gw_metrics.worlds_breaker_open_total.inc()

        def _on_breaker_close() -> None:
            gw_metrics.worlds_breaker_state.set(0)
            gw_metrics.worlds_breaker_failures.set(0)

        breaker = AsyncCircuitBreaker(
            on_open=_on_breaker_open,
            on_close=_on_breaker_close,
            on_failure=lambda c: gw_metrics.worlds_breaker_failures.set(c),
        )
        gw_metrics.worlds_breaker_state.set(0)
        gw_metrics.worlds_breaker_failures.set(0)
        return WorldServiceClient(
            url,
            budget=budget,
            breaker=breaker,
            rebalance_schema_version=capabilities.rebalance_schema_version,
            alpha_metrics_capable=capabilities.alpha_metrics_capable,
        )
    if world_client is not None:
        world_client.configure_rebalance_capabilities(
            schema_version=capabilities.rebalance_schema_version,
            alpha_metrics_capable=capabilities.alpha_metrics_capable,
        )
    return world_client


def _resolve_event_config(event_config: EventDescriptorConfig | None) -> EventDescriptorConfig:
    if event_config is not None:
        return event_config
    secret = secrets.token_hex(32)
    logger.warning("Gateway events.secret not configured; using a generated secret")
    return EventDescriptorConfig(
        keys={"default": secret},
        active_kid="default",
        ttl=300,
        stream_url="wss://gateway/ws/evt",
        fallback_url="wss://gateway/ws",
    )


async def _start_background(
    *,
    enable_background: bool,
    controlbus_consumer: ControlBusConsumer | None,
    commit_log_consumer: CommitLogConsumer | None,
    commit_log_handler: Callable[[list[tuple[str, int, str, Any]]], Awaitable[None]] | None,
    ws_hub: WebSocketHub | None,
) -> asyncio.Task[None] | None:
    commit_task: asyncio.Task[None] | None = None
    if enable_background and controlbus_consumer:
        if ws_hub and controlbus_consumer.ws_hub is None:
            controlbus_consumer.ws_hub = ws_hub
        await controlbus_consumer.start()

    if enable_background and commit_log_consumer:
        await commit_log_consumer.start()
        async def _noop(records: list[tuple[str, int, str, Any]]) -> None:
            return None

        handler = commit_log_handler or _noop

        async def _consume_loop() -> None:
            while True:
                await commit_log_consumer.consume(handler, timeout_ms=1000)

        commit_task = asyncio.create_task(_consume_loop())

    if enable_background and ws_hub:
        await ws_hub.start()
    return commit_task


async def _stop_background(
    *,
    commit_task: asyncio.Task[None] | None,
    ws_hub: WebSocketHub | None,
    controlbus_consumer: ControlBusConsumer | None,
    commit_log_consumer: CommitLogConsumer | None,
    commit_log_writer: CommitLogWriter | None,
    dagmanager: DagManagerClient,
    database_obj: Database,
    redis_conn: redis.Redis,
    world_client: WorldServiceClient | None,
) -> None:
    if commit_task:
        commit_task.cancel()
        with suppress(asyncio.CancelledError):
            await commit_task
    if ws_hub:
        await ws_hub.stop()
    if controlbus_consumer:
        await controlbus_consumer.stop()
    if commit_log_consumer:
        await commit_log_consumer.stop()
    if commit_log_writer is not None:
        await _safe_stop_commit_writer(commit_log_writer)
    await _close_dagmanager_and_db(dagmanager, database_obj)
    await _close_redis(redis_conn)
    await _close_world_client(world_client)


async def _safe_stop_commit_writer(writer: CommitLogWriter) -> None:
    try:
        await writer._producer.stop()
    except Exception:
        logger.exception("Failed to close commit-log writer")


async def _close_dagmanager_and_db(dagmanager: DagManagerClient, database_obj: Database) -> None:
    if hasattr(dagmanager, "close"):
        await dagmanager.close()
    close = getattr(database_obj, "close", None)
    if callable(close):
        try:
            await close()
        except Exception:
            logger.exception("Failed to close database connection")


async def _close_redis(redis_conn: redis.Redis) -> None:
    try:
        aclose = getattr(redis_conn, "aclose", None)
        close = getattr(redis_conn, "close", None)
        if callable(aclose):
            await aclose()
        elif callable(close):
            await close()
        pool = getattr(redis_conn, "connection_pool", None)
        disconnect = getattr(pool, "disconnect", None) if pool is not None else None
        if callable(disconnect):
            await disconnect()
    except Exception:
        logger.exception("Failed to close Redis connection")


async def _close_world_client(world_client: WorldServiceClient | None) -> None:
    if world_client is None:
        return
    client = getattr(world_client, "_client", None)
    close = getattr(client, "aclose", None)
    if callable(close):
        try:
            await close()
        except Exception:
            logger.exception("Failed to close world client")
