from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field
try:
    # Pydantic v2 style config
    from pydantic import ConfigDict  # type: ignore
except Exception:  # pragma: no cover - fallback for older environments
    ConfigDict = None  # type: ignore


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


class QueueDescriptor(BaseModel):
    queue: str
    global_: bool = Field(alias="global")
    # Use Pydantic v2 config; avoid deprecated class-based Config
    if 'ConfigDict' in globals() and ConfigDict is not None:  # type: ignore
        model_config = ConfigDict(populate_by_name=True)  # type: ignore
    else:  # pragma: no cover - legacy fallback
        class Config:  # type: ignore
            populate_by_name = True


class QueuesByTagResponse(BaseModel):
    queues: list[QueueDescriptor] = Field(default_factory=list)


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
