from __future__ import annotations

import json
import uuid
import base64
from dataclasses import dataclass
from typing import Optional

from fastapi import FastAPI, HTTPException, status, Response
from fastapi.responses import StreamingResponse
import time
from pydantic import BaseModel, Field
import redis.asyncio as redis
import asyncpg

from .dagmanager_client import DagManagerClient
from .fsm import StrategyFSM
from . import metrics as gw_metrics
from .watch import QueueWatchHub
_INITIAL_STATUS = "queued"


class StrategySubmit(BaseModel):
    dag_json: str = Field(..., description="Base64 encoded DAG JSON")
    meta: Optional[dict] = Field(default=None)
    run_type: str


class StrategyAck(BaseModel):
    strategy_id: str
    queue_map: dict[str, list[str] | str] = Field(default_factory=dict)


class StatusResponse(BaseModel):
    status: str


class Database:
    async def insert_strategy(self, strategy_id: str, meta: Optional[dict]) -> None:
        raise NotImplementedError

    async def set_status(self, strategy_id: str, status: str) -> None:
        raise NotImplementedError

    async def get_status(self, strategy_id: str) -> Optional[str]:
        raise NotImplementedError

    async def append_event(self, strategy_id: str, event: str) -> None:
        raise NotImplementedError


class PostgresDatabase(Database):
    """PostgreSQL-backed implementation."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._dsn)
        await self._pool.execute(
            """
            CREATE TABLE IF NOT EXISTS strategies (
                id TEXT PRIMARY KEY,
                meta JSONB,
                status TEXT
            )
            """
        )
        await self._pool.execute(
            """
            CREATE TABLE IF NOT EXISTS strategy_events (
                id SERIAL PRIMARY KEY,
                strategy_id TEXT,
                event TEXT,
                ts TIMESTAMPTZ DEFAULT now()
            )
            """
        )

    async def insert_strategy(self, strategy_id: str, meta: Optional[dict]) -> None:
        assert self._pool
        await self._pool.execute(
            "INSERT INTO strategies(id, meta, status) VALUES($1, $2, $3)",
            strategy_id,
            json.dumps(meta) if meta is not None else None,
            _INITIAL_STATUS,
        )
        await self.append_event(strategy_id, f"INIT:{_INITIAL_STATUS}")

    async def set_status(self, strategy_id: str, status: str) -> None:
        assert self._pool
        await self._pool.execute(
            "UPDATE strategies SET status=$1 WHERE id=$2",
            status,
            strategy_id,
        )

    async def append_event(self, strategy_id: str, event: str) -> None:
        assert self._pool
        await self._pool.execute(
            "INSERT INTO strategy_events(strategy_id, event) VALUES($1, $2)",
            strategy_id,
            event,
        )

    async def get_status(self, strategy_id: str) -> Optional[str]:
        assert self._pool
        row = await self._pool.fetchrow(
            "SELECT status FROM strategies WHERE id=$1",
            strategy_id,
        )
        return row["status"] if row else None


@dataclass
class StrategyManager:
    redis: redis.Redis
    database: Database
    fsm: StrategyFSM

    async def submit(self, payload: StrategySubmit) -> str:
        strategy_id = str(uuid.uuid4())

        try:
            dag_bytes = base64.b64decode(payload.dag_json)
            dag_dict = json.loads(dag_bytes.decode())
        except Exception:
            dag_dict = json.loads(payload.dag_json)
        sentinel = {
            "node_type": "VersionSentinel",
            "node_id": f"{strategy_id}-sentinel",
        }
        dag_dict.setdefault("nodes", []).append(sentinel)
        encoded_dag = base64.b64encode(json.dumps(dag_dict).encode()).decode()

        try:
            await self.redis.rpush("strategy_queue", strategy_id)
            await self.redis.hset(
                f"strategy:{strategy_id}",
                mapping={"dag": encoded_dag},
            )
        except Exception:
            gw_metrics.lost_requests_total.inc()
            gw_metrics.lost_requests_total._val = gw_metrics.lost_requests_total._value.get()  # type: ignore[attr-defined]
            raise
        await self.fsm.create(strategy_id, payload.meta)
        return strategy_id

    async def status(self, strategy_id: str) -> Optional[str]:
        return await self.fsm.get(strategy_id)


def create_app(
    redis_client: Optional[redis.Redis] = None,
    database: Optional[Database] = None,
    dag_client: Optional[DagManagerClient] = None,
    watch_hub: Optional[QueueWatchHub] = None,
) -> FastAPI:
    app = FastAPI()

    r = redis_client or redis.Redis(host="localhost", port=6379, decode_responses=True)
    db = database or PostgresDatabase("postgresql://localhost/qmtl")
    fsm = StrategyFSM(redis=r, database=db)
    manager = StrategyManager(redis=r, database=db, fsm=fsm)
    dagm = dag_client or DagManagerClient("127.0.0.1:50051")
    watch = watch_hub or QueueWatchHub()

    @app.post("/strategies", status_code=status.HTTP_202_ACCEPTED, response_model=StrategyAck)
    async def post_strategies(payload: StrategySubmit) -> StrategyAck:
        start = time.perf_counter()
        strategy_id = await manager.submit(payload)
        try:
            dag_bytes = base64.b64decode(payload.dag_json)
            dag = json.loads(dag_bytes.decode())
        except Exception:
            dag = json.loads(payload.dag_json)

        queue_map: dict[str, list[str] | str] = {}
        for node in dag.get("nodes", []):
            if node.get("node_type") == "TagQueryNode":
                tags = node.get("tags", [])
                interval = int(node.get("interval", 0))
                try:
                    queues = await dagm.get_queues_by_tag(tags, interval)
                except Exception:
                    queues = []
                queue_map[node["node_id"]] = queues

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
        if event.get("event") == "queue_update":
            tags = event.get("tags") or []
            interval = event.get("interval")
            queues = event.get("queues", [])
            if isinstance(tags, str):
                tags = [t for t in tags.split(",") if t]
            if interval is not None:
                try:
                    interval = int(interval)
                except (TypeError, ValueError):
                    interval = None
            if tags and interval is not None:
                await watch.broadcast(tags, interval, list(queues))
        return {"ok": True}

    @app.get("/queues/by_tag")
    async def queues_by_tag(tags: str, interval: int) -> dict:
        tag_list = [t for t in tags.split(",") if t]
        queues = await dagm.get_queues_by_tag(tag_list, interval)
        return {"queues": queues}

    @app.get("/queues/watch")
    async def queues_watch(tags: str, interval: int):
        tag_list = [t for t in tags.split(",") if t]

        async def streamer():
            try:
                initial = await dagm.get_queues_by_tag(tag_list, interval)
            except grpc.RpcError as e:  # Or grpc.aio.AioRpcError if using grpc.aio explicitly
                # It's good practice to log this error for observability
                # import logging
                # logging.warning(f"Failed to get initial queues for tags='{tag_list}' interval={interval}: {e}")
                initial = []
            yield json.dumps({"queues": initial}) + "\n"
            async for queues in watch.subscribe(tag_list, interval):
                yield json.dumps({"queues": queues}) + "\n"

        return StreamingResponse(streamer(), media_type="text/plain")

    @app.get("/metrics")
    async def metrics_endpoint() -> Response:
        return Response(gw_metrics.collect_metrics(), media_type="text/plain")

    return app
