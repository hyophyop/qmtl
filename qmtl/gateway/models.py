from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class StrategySubmit(BaseModel):
    dag_json: str = Field(..., description="Base64 encoded DAG JSON")
    meta: Optional[dict] = Field(default=None)
    world_id: Optional[str] = None
    # Optional multi-world submission (backward compatible with world_id)
    world_ids: Optional[list[str]] = None
    node_ids_crc32: int


class StrategyAck(BaseModel):
    strategy_id: str
    queue_map: dict[str, object] = Field(default_factory=dict)
    # Include sentinel identifier for parity with dry-run/diff outputs
    sentinel_id: str | None = None


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
