from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
import redis.asyncio as redis
import asyncpg
# Simplified strategy state machine
_INITIAL_STATUS = "queued"


class StrategySubmit(BaseModel):
    dag_json: str = Field(..., description="Base64 encoded DAG JSON")
    meta: Optional[dict] = Field(default=None)
    run_type: str


class StrategyAck(BaseModel):
    strategy_id: str


class StatusResponse(BaseModel):
    status: str


class Database:
    async def insert_strategy(self, strategy_id: str, meta: Optional[dict]) -> None:
        raise NotImplementedError

    async def set_status(self, strategy_id: str, status: str) -> None:
        raise NotImplementedError

    async def get_status(self, strategy_id: str) -> Optional[str]:
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

    async def insert_strategy(self, strategy_id: str, meta: Optional[dict]) -> None:
        assert self._pool
        await self._pool.execute(
            "INSERT INTO strategies(id, meta, status) VALUES($1, $2, $3)",
            strategy_id,
            json.dumps(meta) if meta is not None else None,
            _INITIAL_STATUS,
        )

    async def set_status(self, strategy_id: str, status: str) -> None:
        assert self._pool
        await self._pool.execute(
            "UPDATE strategies SET status=$1 WHERE id=$2",
            status,
            strategy_id,
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

    async def submit(self, payload: StrategySubmit) -> str:
        strategy_id = str(uuid.uuid4())
        await self.redis.rpush("strategy_queue", strategy_id)
        await self.redis.hset(f"strategy:{strategy_id}", mapping={"status": _INITIAL_STATUS})
        await self.database.insert_strategy(strategy_id, payload.meta)
        return strategy_id

    async def status(self, strategy_id: str) -> Optional[str]:
        data = await self.redis.hget(f"strategy:{strategy_id}", "status")
        if data is None:
            return None
        return data.decode() if isinstance(data, bytes) else data


def create_app(
    redis_client: Optional[redis.Redis] = None,
    database: Optional[Database] = None,
) -> FastAPI:
    app = FastAPI()

    r = redis_client or redis.Redis(host="localhost", port=6379, decode_responses=True)
    db = database or PostgresDatabase("postgresql://localhost/qmtl")
    manager = StrategyManager(redis=r, database=db)

    @app.post("/strategies", status_code=status.HTTP_202_ACCEPTED, response_model=StrategyAck)
    async def post_strategies(payload: StrategySubmit) -> StrategyAck:
        strategy_id = await manager.submit(payload)
        return StrategyAck(strategy_id=strategy_id)

    @app.get("/strategies/{strategy_id}/status", response_model=StatusResponse)
    async def get_status(strategy_id: str) -> StatusResponse:
        status_value = await manager.status(strategy_id)
        if status_value is None:
            raise HTTPException(status_code=404, detail="strategy not found")
        return StatusResponse(status=status_value)

    @app.post("/callbacks/dag-event", status_code=status.HTTP_202_ACCEPTED)
    async def dag_event(event: dict) -> dict:
        """Handle DAG manager callbacks."""
        return {"ok": True}

    return app
