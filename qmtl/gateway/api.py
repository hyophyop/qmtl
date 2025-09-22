from __future__ import annotations

import logging
import os
import secrets
import asyncio
from contextlib import asynccontextmanager, suppress
from typing import Optional, Callable, Awaitable, Any

import redis.asyncio as redis
from fastapi import FastAPI, Request, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry import trace

from qmtl.common import AsyncCircuitBreaker
from qmtl.common.tracing import setup_tracing

from . import metrics as gw_metrics
from .controlbus_consumer import ControlBusConsumer
from .dagmanager_client import DagManagerClient
from .database import Database, PostgresDatabase, MemoryDatabase, SQLiteDatabase
from .degradation import DegradationManager, DegradationLevel
from .event_descriptor import EventDescriptorConfig
from .event_handlers import create_event_router
from .fsm import StrategyFSM
from .gateway_health import get_health as gateway_health
from .routes import create_api_router
from .strategy_manager import StrategyManager
from .world_client import Budget, WorldServiceClient
from .ws import WebSocketHub
from .commit_log_consumer import CommitLogConsumer
from .commit_log import CommitLogWriter
from .submission import ComputeContextService, SubmissionPipeline

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
    enable_otel: bool | None = None,
    enable_background: bool = True,
) -> FastAPI:
    setup_tracing("gateway")
    redis_conn = redis_client or redis.Redis(host="localhost", port=6379, decode_responses=True)
    if database is not None:
        database_obj = database
    else:
        if database_backend == "postgres":
            database_obj = PostgresDatabase(database_dsn or "postgresql://localhost/qmtl")
        elif database_backend == "memory":
            database_obj = MemoryDatabase()
        elif database_backend == "sqlite":
            database_obj = SQLiteDatabase(database_dsn or ":memory:")
        else:
            raise ValueError(f"Unsupported database backend: {database_backend}")
    fsm = StrategyFSM(redis=redis_conn, database=database_obj)
    dagmanager = dag_client if dag_client is not None else DagManagerClient("127.0.0.1:50051")
    degradation = DegradationManager(redis_conn, database_obj, dagmanager, world_client)
    commit_log_writer_local = commit_log_writer
    manager = StrategyManager(
        redis=redis_conn,
        database=database_obj,
        fsm=fsm,
        degrade=degradation,
        insert_sentinel=insert_sentinel,
        commit_log_writer=commit_log_writer_local,
    )
    ws_hub_local = ws_hub
    controlbus_consumer_local = controlbus_consumer
    commit_log_consumer_local = commit_log_consumer
    commit_log_handler_local = commit_log_handler
    world_client_local = world_client
    if world_client_local is None and enable_worldservice_proxy and worldservice_url is not None:
        budget = Budget(timeout=worldservice_timeout, retries=worldservice_retries)
        breaker = AsyncCircuitBreaker(
            on_open=lambda: (
                gw_metrics.worlds_breaker_state.set(1),
                gw_metrics.worlds_breaker_open_total.inc(),
            ),
            on_close=lambda: (
                gw_metrics.worlds_breaker_state.set(0),
                gw_metrics.worlds_breaker_failures.set(0),
            ),
            on_failure=lambda c: gw_metrics.worlds_breaker_failures.set(c),
        )
        gw_metrics.worlds_breaker_state.set(0)
        gw_metrics.worlds_breaker_failures.set(0)
        world_client_local = WorldServiceClient(worldservice_url, budget=budget, breaker=breaker)
    if world_client_local is not None:
        degradation.world_client = world_client_local
    if event_config is not None:
        event_cfg = event_config
    else:
        secret = os.getenv("QMTL_EVENT_SECRET")
        if not secret:
            secret = secrets.token_hex(32)
            logger.warning("QMTL_EVENT_SECRET is not set; using a generated secret")
        event_cfg = EventDescriptorConfig(
            keys={"default": secret},
            active_kid="default",
            ttl=300,
            stream_url="wss://gateway/ws/evt",
            fallback_url="wss://gateway/ws",
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        commit_task: asyncio.Task[None] | None = None
        if enable_background and controlbus_consumer_local:
            if ws_hub_local and controlbus_consumer_local.ws_hub is None:
                controlbus_consumer_local.ws_hub = ws_hub_local
            await controlbus_consumer_local.start()
        if enable_background and commit_log_consumer_local:
            await commit_log_consumer_local.start()
            handler = commit_log_handler_local or (
                lambda records: None
            )
            async def _consume_loop() -> None:
                while True:
                    await commit_log_consumer_local.consume(
                        handler, timeout_ms=1000
                    )

            commit_task = asyncio.create_task(_consume_loop())
        if enable_background and ws_hub_local:
            await ws_hub_local.start()
        try:
            yield
        finally:
            if commit_task:
                commit_task.cancel()
                with suppress(asyncio.CancelledError):
                    await commit_task
            if ws_hub_local:
                await ws_hub_local.stop()
            if controlbus_consumer_local:
                await controlbus_consumer_local.stop()
            if commit_log_consumer_local:
                await commit_log_consumer_local.stop()
            if commit_log_writer_local is not None:
                try:
                    await commit_log_writer_local._producer.stop()
                except Exception:
                    logger.exception("Failed to close commit-log writer")
            if hasattr(dagmanager, "close"):
                await dagmanager.close()
            db_obj = getattr(app.state, "database", None)
            if db_obj is not None and hasattr(db_obj, "close"):
                try:
                    await db_obj.close()  # type: ignore[attr-defined]
                except Exception:
                    logger.exception("Failed to close database connection")
            # Close Redis connection to avoid unclosed socket warnings in tests
            try:
                if hasattr(redis_conn, "aclose"):
                    await redis_conn.aclose()  # type: ignore[attr-defined]
                elif hasattr(redis_conn, "close"):
                    await redis_conn.close()  # type: ignore[attr-defined]
                pool = getattr(redis_conn, "connection_pool", None)
                if pool is not None and hasattr(pool, "disconnect"):
                    await pool.disconnect()  # type: ignore[attr-defined]
            except Exception:
                logger.exception("Failed to close Redis connection")
            if world_client_local is not None and hasattr(world_client_local._client, "aclose"):
                try:
                    await world_client_local._client.aclose()  # type: ignore[attr-defined]
                except Exception:
                    logger.exception("Failed to close world client")

    app = FastAPI(lifespan=lifespan)
    # Opt-in FastAPI OpenTelemetry instrumentation to avoid resource warnings in tests
    # Default is disabled unless explicitly enabled via argument or env var
    _otel_enabled = (
        enable_otel
        if enable_otel is not None
        else os.getenv("QMTL_ENABLE_FASTAPI_OTEL", "0").lower() in {"1", "true", "yes"}
    )
    if _otel_enabled:
        FastAPIInstrumentor().instrument_app(app)
    app.state.database = database_obj
    app.state.degradation = degradation
    app.state.world_client = world_client_local
    app.state.enforce_live_guard = enforce_live_guard
    app.state.event_config = event_cfg
    app.state.ws_hub = ws_hub_local
    app.state.commit_log_consumer = commit_log_consumer_local
    app.state.commit_log_writer = commit_log_writer_local

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
        context_service=ComputeContextService(world_client=world_client_local),
    )

    api_router = create_api_router(
        manager,
        redis_conn,
        database_obj,
        dagmanager,
        ws_hub_local,
        degradation,
        world_client_local,
        enforce_live_guard,
        fill_producer,
        submission_pipeline=submission_pipeline,
    )
    app.include_router(api_router)
    # Expose event endpoints (subscribe/JWKS and WS bridge). Pass world and
    # dag clients so that initial snapshots/state hashes can be sent on
    # connection when topics are scoped.
    event_router = create_event_router(
        ws_hub_local, event_cfg, world_client=world_client_local, dagmanager=dagmanager
    )
    app.include_router(event_router)

    return app
