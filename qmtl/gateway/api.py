from __future__ import annotations

import json
import uuid
import base64
import logging
import hashlib
import os
import secrets
from dataclasses import dataclass
from typing import Optional, Coroutine, Any
import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import (
    FastAPI,
    HTTPException,
    status,
    Response,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from contextlib import asynccontextmanager
from fastapi.responses import StreamingResponse
import time
from pydantic import BaseModel, Field
import redis.asyncio as redis
import grpc

from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from qmtl.common.tracing import setup_tracing
from .dagmanager_client import DagManagerClient
from .fsm import StrategyFSM
from . import metrics as gw_metrics
from .degradation import DegradationManager, DegradationLevel
from .watch import QueueWatchHub
from qmtl.sdk.node import MatchMode
from .ws import WebSocketHub
from .controlbus_consumer import ControlBusConsumer
from .gateway_health import get_health as gateway_health
from .database import Database, PostgresDatabase, MemoryDatabase, SQLiteDatabase
from .world_client import WorldServiceClient, Budget
from .event_descriptor import EventDescriptorConfig, sign_event_token

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class StrategySubmit(BaseModel):
    dag_json: str = Field(..., description="Base64 encoded DAG JSON")
    meta: Optional[dict] = Field(default=None)
    run_type: str
    node_ids_crc32: int


class StrategyAck(BaseModel):
    strategy_id: str
    queue_map: dict[str, list[str] | str] = Field(default_factory=dict)


class StatusResponse(BaseModel):
    status: str


class EventSubscribeRequest(BaseModel):
    world_id: str
    strategy_id: str
    topics: list[str] = Field(default_factory=list)


class EventSubscribeResponse(BaseModel):
    stream_url: str
    token: str
    topics: list[str]
    expires_at: datetime
    fallback_url: str | None = None




@dataclass
class StrategyManager:
    redis: redis.Redis
    database: Database
    fsm: StrategyFSM
    degrade: Optional[DegradationManager] = None
    insert_sentinel: bool = True

    async def submit(self, payload: StrategySubmit) -> tuple[str, bool]:
        with tracer.start_as_current_span("gateway.submit"):
            try:
                dag_bytes = base64.b64decode(payload.dag_json)
                dag_dict = json.loads(dag_bytes.decode())
            except Exception:
                dag_dict = json.loads(payload.dag_json)

            dag_hash = hashlib.sha256(
                json.dumps(dag_dict, sort_keys=True).encode()
            ).hexdigest()
            existing = await self.redis.get(f"dag_hash:{dag_hash}")
            if existing:
                existing_id = existing.decode() if isinstance(existing, bytes) else existing
                return existing_id, True

            strategy_id = str(uuid.uuid4())
            dag_for_storage = dag_dict.copy()
            if self.insert_sentinel:
                sentinel = {
                    "node_type": "VersionSentinel",
                    "node_id": f"{strategy_id}-sentinel",
                }
                dag_for_storage.setdefault("nodes", []).append(sentinel)
            encoded_dag = base64.b64encode(json.dumps(dag_for_storage).encode()).decode()

            try:
                if self.degrade and self.degrade.level == DegradationLevel.PARTIAL and not self.degrade.dag_ok:
                    self.degrade.local_queue.append(strategy_id)
                else:
                    await self.redis.rpush("strategy_queue", strategy_id)
                await self.redis.hset(
                    f"strategy:{strategy_id}",
                    mapping={"dag": encoded_dag, "hash": dag_hash},
                )
                await self.redis.set(f"dag_hash:{dag_hash}", strategy_id)
            except Exception:
                gw_metrics.lost_requests_total.inc()
                gw_metrics.lost_requests_total._val = gw_metrics.lost_requests_total._value.get()  # type: ignore[attr-defined]
                raise
            await self.fsm.create(strategy_id, payload.meta)
            return strategy_id, False

    async def status(self, strategy_id: str) -> Optional[str]:
        return await self.fsm.get(strategy_id)


def create_app(
    redis_client: Optional[redis.Redis] = None,
    database: Optional[Database] = None,
    dag_client: Optional[DagManagerClient] = None,
    watch_hub: Optional[QueueWatchHub] = None,
    ws_hub: Optional[WebSocketHub] = None,
    controlbus_consumer: Optional[ControlBusConsumer] = None,
    world_client: Optional[WorldServiceClient] = None,
    event_config: EventDescriptorConfig | None = None,
    *,
    insert_sentinel: bool = True,
    database_backend: str = "postgres",
    database_dsn: str | None = None,
    worldservice_url: str | None = None,
    worldservice_timeout: float = 5.0,
    worldservice_retries: int = 0,
    enable_worldservice_proxy: bool = True,
    enforce_live_guard: bool = True,
) -> FastAPI:
    setup_tracing("gateway")
    redis_conn = redis_client or redis.Redis(
        host="localhost", port=6379, decode_responses=True
    )
    if database is not None:
        database_obj = database
    else:
        if database_backend == "postgres":
            database_obj = PostgresDatabase(
                database_dsn or "postgresql://localhost/qmtl"
            )
        elif database_backend == "memory":
            database_obj = MemoryDatabase()
        elif database_backend == "sqlite":
            database_obj = SQLiteDatabase(database_dsn or ":memory:")
        else:
            raise ValueError(f"Unsupported database backend: {database_backend}")
    fsm = StrategyFSM(redis=redis_conn, database=database_obj)
    dagmanager = dag_client if dag_client is not None else DagManagerClient("127.0.0.1:50051")
    degradation = DegradationManager(redis_conn, database_obj, dagmanager)
    manager = StrategyManager(
        redis=redis_conn,
        database=database_obj,
        fsm=fsm,
        degrade=degradation,
        insert_sentinel=insert_sentinel,
    )
    watch_hub_local = watch_hub or QueueWatchHub()
    ws_hub_local = ws_hub
    controlbus_consumer_local = controlbus_consumer
    world_client_local = world_client
    if (
        world_client_local is None
        and enable_worldservice_proxy
        and worldservice_url is not None
    ):
        budget = Budget(timeout=worldservice_timeout, retries=worldservice_retries)
        world_client_local = WorldServiceClient(worldservice_url, budget=budget)
    if event_config is not None:
        event_cfg = event_config
    else:
        secret = os.getenv("QMTL_EVENT_SECRET")
        if not secret:
            secret = secrets.token_hex(32)
            logger.warning("QMTL_EVENT_SECRET is not set; using a generated secret")
        event_cfg = EventDescriptorConfig(
            secret=secret,
            kid="default",
            ttl=300,
            stream_url="wss://gateway/ws/evt",
            fallback_url="wss://gateway/ws/fallback",
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if controlbus_consumer_local:
            if ws_hub_local and controlbus_consumer_local.ws_hub is None:
                controlbus_consumer_local.ws_hub = ws_hub_local
            await controlbus_consumer_local.start()
        if ws_hub_local:
            await ws_hub_local.start()
        try:
            yield
        finally:
            if ws_hub_local:
                await ws_hub_local.stop()
            if controlbus_consumer_local:
                await controlbus_consumer_local.stop()
            if hasattr(dagmanager, "close"):
                await dagmanager.close()
            db_obj = getattr(app.state, "database", None)
            if db_obj is not None and hasattr(db_obj, "close"):
                try:
                    await db_obj.close()  # type: ignore[attr-defined]
                except Exception:
                    logger.exception("Failed to close database connection")
            if (
                world_client_local is not None
                and hasattr(world_client_local._client, "aclose")
            ):
                try:
                    await world_client_local._client.aclose()  # type: ignore[attr-defined]
                except Exception:
                    logger.exception("Failed to close world client")

    app = FastAPI(lifespan=lifespan)
    FastAPIInstrumentor().instrument_app(app)
    app.state.database = database_obj
    app.state.degradation = degradation
    app.state.world_client = world_client_local
    app.state.enforce_live_guard = enforce_live_guard
    app.state.event_config = event_cfg

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

    @app.get("/status")
    async def status_endpoint() -> dict[str, str]:
        health_data = await gateway_health(redis_conn, database_obj, dagmanager)
        health_data["degrade_level"] = degradation.level.name
        return health_data

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Deprecated health check; alias for ``/status``."""
        return await gateway_health(redis_conn, database_obj, dagmanager)

    if ws_hub_local:
        @app.websocket("/ws")
        async def ws_endpoint(websocket: WebSocket) -> None:
            await ws_hub_local.connect(websocket)
            try:
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                pass
            finally:
                await ws_hub_local.disconnect(websocket)

        @app.websocket("/ws/evt")
        async def ws_evt_endpoint(websocket: WebSocket) -> None:
            await ws_hub_local.connect(websocket)
            try:
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                pass
            finally:
                await ws_hub_local.disconnect(websocket)

    class Gateway:
        def __init__(self, ws_hub: Optional[WebSocketHub] = None):
            self.ws_hub = ws_hub
            self._sentinel_weights: dict[str, float] = {}
            self._activation_etags: set[str] = set()
            self._policy_versions: dict[str, int] = {}

        async def _handle_sentinel_weight(self, payload: dict) -> None:
            sid: str = payload["sentinel_id"]
            weight: float = payload["weight"]
            if not 0.0 <= weight <= 1.0:
                logger.warning(
                    "Ignoring out-of-range sentinel weight %s for %s", weight, sid
                )
                return
            if self._sentinel_weights.get(sid) == weight:
                return
            if self.ws_hub:
                await self.ws_hub.send_sentinel_weight(sid, weight)
            self._sentinel_weights[sid] = weight
            from . import metrics as gw_metrics
            gw_metrics.record_sentinel_weight_update(sid)
            gw_metrics.set_sentinel_traffic_ratio(sid, weight)

        async def _handle_activation_updated(self, payload: dict) -> None:
            if payload.get("version") != 1:
                return
            etag = payload.get("etag")
            if not etag or etag in self._activation_etags:
                return
            self._activation_etags.add(etag)
            if self.ws_hub:
                await self.ws_hub.send_activation_updated(payload)

        async def _handle_policy_updated(self, payload: dict) -> None:
            if payload.get("version") != 1:
                return
            world_id = payload.get("world_id")
            version = payload.get("policy_version")
            if world_id is None or version is None:
                return
            if self._policy_versions.get(world_id) == version:
                return
            try:
                if isinstance(version, int):
                    self._policy_versions[world_id] = version
                else:
                    self._policy_versions[world_id] = int(version)
            except (ValueError, TypeError):
                logger.warning(
                    "Invalid policy_version %r for world_id %r; must be integer-convertible.",
                    version, world_id
                )
                return
            if self.ws_hub:
                await self.ws_hub.send_policy_updated(payload)

    @app.post("/strategies", status_code=status.HTTP_202_ACCEPTED, response_model=StrategyAck)
    async def post_strategies(payload: StrategySubmit) -> StrategyAck:
        start = time.perf_counter()
        try:
            dag_bytes = base64.b64decode(payload.dag_json)
            dag = json.loads(dag_bytes.decode())
        except Exception:
            dag = json.loads(payload.dag_json)

        from qmtl.common import crc32_of_list, compute_node_id
        crc = crc32_of_list(n.get("node_id") for n in dag.get("nodes", []))
        if crc != payload.node_ids_crc32:
            raise HTTPException(status_code=400, detail="node id checksum mismatch")

        mismatches: list[dict[str, str | int]] = []
        for idx, node in enumerate(dag.get("nodes", [])):
            expected = compute_node_id(
                node.get("node_type", ""),
                node.get("code_hash", ""),
                node.get("config_hash", ""),
                node.get("schema_hash", ""),
            )
            if node.get("node_id") != expected:
                mismatches.append(
                    {"index": idx, "node_id": node.get("node_id", ""), "expected": expected}
                )
        if mismatches:
            raise HTTPException(status_code=400, detail={"node_id_mismatch": mismatches})

        strategy_id, existed = await manager.submit(payload)
        if existed:
            raise HTTPException(status_code=409, detail={"strategy_id": strategy_id})

        queue_map: dict[str, list[str] | str] = {}
        node_ids: list[str] = []
        queries: list[Coroutine[Any, Any, list[str]]] = []
        for node in dag.get("nodes", []):
            if node.get("node_type") == "TagQueryNode":
                tags = node.get("tags", [])
                interval = int(node.get("interval", 0))
                match_mode = node.get("match_mode", "any")
                node_ids.append(node["node_id"])
                queries.append(
                    dagmanager.get_queues_by_tag(tags, interval, match_mode)
                )

        results = []
        if queries:
            results = await asyncio.gather(*queries, return_exceptions=True)

        for nid, result in zip(node_ids, results):
            if isinstance(result, Exception):
                queue_map[nid] = []
            else:
                queue_map[nid] = result

        resp = StrategyAck(strategy_id=strategy_id, queue_map=queue_map)
        duration_ms = (time.perf_counter() - start) * 1000
        gw_metrics.observe_gateway_latency(duration_ms)
        return resp

    @app.get("/strategies/{strategy_id}/status", response_model=StatusResponse)
    async def get_status(strategy_id: str) -> StatusResponse:
        status_value = await manager.status(strategy_id)
        if status_value is None:
            raise HTTPException(status_code=404, detail="strategy not found")
        return StatusResponse(status=status_value)

    @app.post("/callbacks/dag-event", status_code=status.HTTP_202_ACCEPTED)
    async def dag_event(event: dict) -> dict:
        """Handle DAG Manager callbacks."""
        event_type = event.get("type")
        data = event.get("data", {}) if isinstance(event.get("data"), dict) else {}
        if event_type == "queue_update":
            tags = data.get("tags") or []
            interval = data.get("interval")
            queues = data.get("queues", [])
            match_mode = data.get("match_mode", "any")
            if isinstance(tags, str):
                tags = [t for t in tags.split(",") if t]
            if interval is not None:
                try:
                    interval = int(interval)
                except (TypeError, ValueError):
                    interval = None
            if tags and interval is not None:
                try:
                    mode = MatchMode(match_mode)
                except ValueError:
                    return {"ok": True}
                await watch_hub_local.broadcast(
                    tags, interval, list(queues), mode
                )
                if ws_hub_local:
                    await ws_hub_local.send_queue_update(
                        tags, interval, list(queues), mode
                    )
        elif event_type == "sentinel_weight":
            gateway = getattr(app.state, "gateway", None)
            if gateway is None:
                gateway = Gateway(ws_hub_local)
                app.state.gateway = gateway
            await gateway._handle_sentinel_weight(data)
            return {"ok": True}
        elif event_type in {"ActivationUpdated", "PolicyUpdated"}:
            gateway = getattr(app.state, "gateway", None)
            if gateway is None:
                gateway = Gateway(ws_hub_local)
                app.state.gateway = gateway
            handler = (
                gateway._handle_activation_updated
                if event_type == "ActivationUpdated"
                else gateway._handle_policy_updated
            )
            await handler(data)
            return {"ok": True}

        return {"ok": True}

    @app.get("/queues/by_tag")
    async def queues_by_tag(
        tags: str, interval: int, match: str = "any", match_mode: str | None = None
    ) -> dict:
        mode = match_mode or match
        tag_list = [t for t in tags.split(",") if t]
        queues = await dagmanager.get_queues_by_tag(tag_list, interval, mode)
        return {"queues": queues}

    @app.get("/queues/watch")
    async def queues_watch(
        tags: str, interval: int, match: str = "any", match_mode: str | None = None
    ):
        """Legacy queue watch; prefer ``POST /events/subscribe``."""
        logger.warning("/queues/watch is deprecated; use /events/subscribe instead")
        tag_list = [t for t in tags.split(",") if t]
        mode_str = match_mode or match
        try:
            mode = MatchMode(mode_str)
        except ValueError:
            mode = MatchMode.ANY

        async def streamer():
            try:
                initial = await dagmanager.get_queues_by_tag(tag_list, interval, mode.value)
            except grpc.RpcError as e:  # Or grpc.aio.AioRpcError if using grpc.aio explicitly
                # It's good practice to log this error for observability
                # import logging
                # logging.warning(f"Failed to get initial queues for tags='{tag_list}' interval={interval}: {e}")
                initial = []
            yield json.dumps({"queues": initial}) + "\n"
            async for queues in watch_hub_local.subscribe(tag_list, interval, mode):
                yield json.dumps({"queues": queues}) + "\n"

        headers = {
            "Deprecation": "true",
            "Link": "</events/subscribe>; rel=\"successor-version\"",
        }
        return StreamingResponse(streamer(), media_type="text/plain", headers=headers)

    @app.post("/events/subscribe", response_model=EventSubscribeResponse)
    async def events_subscribe(payload: EventSubscribeRequest) -> EventSubscribeResponse:
        cfg: EventDescriptorConfig = app.state.event_config
        now = datetime.now(timezone.utc)
        exp = now + timedelta(seconds=cfg.ttl)
        claims = {
            "aud": "controlbus",
            "sub": payload.strategy_id,
            "world_id": payload.world_id,
            "strategy_id": payload.strategy_id,
            "topics": payload.topics,
            "jti": str(uuid.uuid4()),
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
        }
        token = sign_event_token(claims, cfg)
        return EventSubscribeResponse(
            stream_url=cfg.stream_url,
            token=token,
            topics=payload.topics,
            expires_at=exp,
            fallback_url=cfg.fallback_url,
        )

    @app.get("/worlds/{world_id}/decide")
    async def get_world_decide(world_id: str, request: Request) -> Any:
        client: WorldServiceClient | None = app.state.world_client
        if client is None:
            raise HTTPException(status_code=503, detail="world service disabled")
        headers: dict[str, str] = {}
        auth = request.headers.get("authorization")
        if auth:
            headers["Authorization"] = auth
        return await client.get_decide(world_id, headers=headers)

    @app.get("/worlds/{world_id}/activation")
    async def get_world_activation(world_id: str, request: Request) -> Any:
        client: WorldServiceClient | None = app.state.world_client
        if client is None:
            raise HTTPException(status_code=503, detail="world service disabled")
        headers: dict[str, str] = {}
        auth = request.headers.get("authorization")
        if auth:
            headers["Authorization"] = auth
        return await client.get_activation(world_id, headers=headers)

    @app.post("/worlds/{world_id}/evaluate")
    async def post_world_evaluate(world_id: str, payload: dict, request: Request) -> Any:
        client: WorldServiceClient | None = app.state.world_client
        if client is None:
            raise HTTPException(status_code=503, detail="world service disabled")
        headers: dict[str, str] = {}
        auth = request.headers.get("authorization")
        if auth:
            headers["Authorization"] = auth
        return await client.post_evaluate(world_id, payload, headers=headers)

    @app.post("/worlds/{world_id}/apply")
    async def post_world_apply(world_id: str, payload: dict, request: Request) -> Any:
        if app.state.enforce_live_guard and request.headers.get("X-Allow-Live") != "true":
            raise HTTPException(status_code=403, detail="live trading not allowed")
        client: WorldServiceClient | None = app.state.world_client
        if client is None:
            raise HTTPException(status_code=503, detail="world service disabled")
        headers: dict[str, str] = {}
        auth = request.headers.get("authorization")
        if auth:
            headers["Authorization"] = auth
        return await client.post_apply(world_id, payload, headers=headers)

    @app.get("/metrics")
    async def metrics_endpoint() -> Response:
        return Response(gw_metrics.collect_metrics(), media_type="text/plain")

    return app
