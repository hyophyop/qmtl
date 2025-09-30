from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, StrictFloat, StrictInt, StrictStr
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
    strategy_id: str | None = None
    queue_map: dict[str, object] = Field(default_factory=dict)
    # Include sentinel identifier for parity with dry-run/diff outputs
    sentinel_id: str | None = None
    node_ids_crc32: int = 0
    downgraded: bool = False
    downgrade_reason: str | None = None
    safe_mode: bool = False


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


class ExecutionFillEvent(BaseModel):
    order_id: StrictStr
    client_order_id: StrictStr | None = None
    correlation_id: StrictStr | None = None
    symbol: StrictStr
    side: StrictStr
    quantity: StrictFloat
    price: StrictFloat
    commission: StrictFloat | None = None
    slippage: StrictFloat | None = None
    market_impact: StrictFloat | None = None
    tif: StrictStr | None = None
    fill_time: StrictInt | None = None
    status: StrictStr | None = None
    seq: StrictInt | None = None
    etag: StrictStr | None = None
    if 'ConfigDict' in globals() and ConfigDict is not None:  # type: ignore
        model_config = ConfigDict(extra='ignore')  # type: ignore
    else:  # pragma: no cover - legacy fallback
        class Config:  # type: ignore
            extra = 'ignore'


class SeamlessArtifactPayload(BaseModel):
    dataset_fingerprint: StrictStr
    as_of: StrictStr
    rows: StrictInt
    uri: StrictStr | None = None


class SeamlessHistoryReport(BaseModel):
    node_id: StrictStr
    interval: StrictInt
    rows: StrictInt | None = None
    coverage_bounds: tuple[int, int] | None = None
    conformance_flags: dict[str, int] | None = None
    conformance_warnings: list[str] | None = None
    dataset_fingerprint: StrictStr | None = None
    as_of: StrictStr | None = None
    world_id: StrictStr | None = None
    execution_domain: StrictStr | None = None
    artifact: SeamlessArtifactPayload | None = None
