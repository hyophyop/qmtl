from __future__ import annotations

import json
import uuid
import base64
import logging
import hashlib
from dataclasses import dataclass
from typing import Optional, Coroutine, Any
import asyncio

from fastapi import FastAPI, HTTPException, status, Response, Request
from contextlib import asynccontextmanager
from fastapi.responses import StreamingResponse
import time
from pydantic import BaseModel, Field
import redis.asyncio as redis

from .dagmanager_client import DagManagerClient
from .fsm import StrategyFSM
from . import metrics as gw_metrics
from .degradation import DegradationManager, DegradationLevel
from .watch import QueueWatchHub
from .ws import WebSocketHub
from .status import get_status as gateway_status
from .database import Database, PostgresDatabase, MemoryDatabase, SQLiteDatabase

logger = logging.getLogger(__name__)


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




@dataclass
class StrategyManager:
    redis: redis.Redis
    database: Database
    fsm: StrategyFSM
    degrade: Optional[DegradationManager] = None
    insert_sentinel: bool = True

    async def submit(self, payload: StrategySubmit) -> tuple[str, bool]:
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
    *,
    insert_sentinel: bool = True,
    database_backend: str = "postgres",
    database_dsn: str | None = None,
) -> FastAPI:
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
    dag_manager = dag_client or DagManagerClient("127.0.0.1:50051")
    degradation = DegradationManager(redis_conn, database_obj, dag_manager)
    manager = StrategyManager(
        redis=redis_conn,
        database=database_obj,
        fsm=fsm,
        degrade=degradation,
        insert_sentinel=insert_sentinel,
    )
    watch_hub_local = watch_hub or QueueWatchHub()
    ws_hub_local = ws_hub

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        if hasattr(dag_manager, "close"):
            await dag_manager.close()
        db_obj = getattr(app.state, "database", None)
        if db_obj is not None and hasattr(db_obj, "close"):
            try:
                await db_obj.close()  # type: ignore[attr-defined]
            except Exception:
                logger.exception("Failed to close database connection")

    app = FastAPI(lifespan=lifespan)
    app.state.database = database_obj
    app.state.degradation = degradation

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
        status_data = await gateway_status(redis_conn, database_obj, dag_manager)
        status_data["degrade_level"] = degradation.level.name
        return status_data

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Deprecated health check; alias for ``/status``."""
        return await gateway_status(redis_conn, database_obj, dag_manager)

    class Gateway:
        def __init__(self, ws_hub: Optional[WebSocketHub] = None):
            self.ws_hub = ws_hub
            self._sentinel_weights: dict[str, float] = {}

        async def _handle_sentinel_weight(self, payload: dict) -> None:
            sid: str = payload["sentinel_id"]
            weight: float = payload["weight"]
            # Ignore out-of-range weights entirely
            if 0.0 <= weight <= 1.0:
                if self._sentinel_weights.get(sid) != weight and self.ws_hub:
                    await self.ws_hub.send_sentinel_weight(sid, weight)
                self._sentinel_weights[sid] = weight
                from . import metrics as gw_metrics
                gw_metrics.set_sentinel_traffic_ratio(sid, weight)
            else:
                logger.warning(
                    "Ignoring out-of-range sentinel weight %s for %s", weight, sid
                )

    @app.post("/strategies", status_code=status.HTTP_202_ACCEPTED, response_model=StrategyAck)
    async def post_strategies(payload: StrategySubmit) -> StrategyAck:
        start = time.perf_counter()
        try:
            dag_bytes = base64.b64decode(payload.dag_json)
            dag = json.loads(dag_bytes.decode())
        except Exception:
            dag = json.loads(payload.dag_json)

        from qmtl.common import crc32_of_list
        crc = crc32_of_list(n.get("node_id") for n in dag.get("nodes", []))
        if crc != payload.node_ids_crc32:
            raise HTTPException(status_code=400, detail="node id checksum mismatch")

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
                    dag_manager.get_queues_by_tag(tags, interval, match_mode)
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
        """Handle DAG manager callbacks."""
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
                await watch_hub_local.broadcast(
                    tags, interval, list(queues), match_mode
                )
                if ws_hub_local:
                    await ws_hub_local.send_queue_update(
                        tags, interval, list(queues), match_mode
                    )
        elif event_type == "sentinel_weight":
            gateway = getattr(app.state, "gateway", None)
            if gateway is None:
                gateway = Gateway(ws_hub_local)
                app.state.gateway = gateway
            await gateway._handle_sentinel_weight(data)
            return {"ok": True}

        return {"ok": True}

    @app.get("/queues/by_tag")
    async def queues_by_tag(
        tags: str, interval: int, match: str = "any", match_mode: str | None = None
    ) -> dict:
        mode = match_mode or match
        tag_list = [t for t in tags.split(",") if t]
        queues = await dag_manager.get_queues_by_tag(tag_list, interval, mode)
        return {"queues": queues}

    @app.get("/queues/watch")
    async def queues_watch(
        tags: str, interval: int, match: str = "any", match_mode: str | None = None
    ):
        tag_list = [t for t in tags.split(",") if t]
        mode = match_mode or match

        async def streamer():
            try:
                initial = await dag_manager.get_queues_by_tag(tag_list, interval, mode)
            except grpc.RpcError as e:  # Or grpc.aio.AioRpcError if using grpc.aio explicitly
                # It's good practice to log this error for observability
                # import logging
                # logging.warning(f"Failed to get initial queues for tags='{tag_list}' interval={interval}: {e}")
                initial = []
            yield json.dumps({"queues": initial}) + "\n"
            async for queues in watch_hub_local.subscribe(tag_list, interval, mode):
                yield json.dumps({"queues": queues}) + "\n"

        return StreamingResponse(streamer(), media_type="text/plain")

    @app.get("/metrics")
    async def metrics_endpoint() -> Response:
        return Response(gw_metrics.collect_metrics(), media_type="text/plain")

    return app
