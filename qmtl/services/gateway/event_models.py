from __future__ import annotations

# Source: docs/alphadocs/ideas/gpt5pro/ws_event_bridge.md
# Priority: gpt5pro

from datetime import datetime
from typing import Any, Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, Field, StrictFloat, StrictInt, StrictStr


class QueueRef(BaseModel):
    queue: StrictStr
    global_: bool = Field(False, alias="global")


class QueueUpdateData(BaseModel):
    tags: List[StrictStr]
    interval: StrictInt
    queues: List[QueueRef]
    match_mode: Literal["any", "all"] = "any"
    world_id: Optional[StrictStr] = None
    version: StrictInt
    etag: StrictStr
    ts: StrictStr


class TagQueryUpsertData(BaseModel):
    tags: List[StrictStr]
    interval: StrictInt
    queues: List[QueueRef]
    version: StrictInt


class SentinelWeightData(BaseModel):
    sentinel_id: StrictStr
    weight: StrictFloat
    world_id: Optional[StrictStr] = None
    version: StrictInt


class ActivationUpdatedData(BaseModel):
    version: StrictInt
    world_id: StrictStr
    strategy_id: Optional[StrictStr] = None
    side: Optional[Literal["long", "short"]] = None
    active: Optional[bool] = None
    weight: Optional[StrictFloat] = None
    freeze: Optional[bool] = None
    drain: Optional[bool] = None
    effective_mode: Optional[Literal["compute-only", "paper", "live"]] = None
    etag: Optional[StrictStr] = None
    run_id: Optional[StrictStr] = None
    ts: Optional[StrictStr] = None
    state_hash: Optional[StrictStr] = None


class PolicyUpdatedData(BaseModel):
    version: StrictInt
    world_id: StrictStr
    policy_version: Optional[StrictInt] = None
    checksum: Optional[StrictStr] = None
    status: Optional[StrictStr] = None
    ts: Optional[StrictStr] = None


T = TypeVar("T", bound=BaseModel)


class CloudEvent(BaseModel, Generic[T]):
    specversion: Literal["1.0"] = "1.0"
    id: StrictStr
    source: StrictStr
    type: StrictStr
    time: datetime
    datacontenttype: Literal["application/json"] = "application/json"
    data: T
    correlation_id: Optional[StrictStr] = None
    # Optional hub-assigned monotonic sequence number to aid reordering
    # across upstream partitions. Not guaranteed to be globally unique.
    seq_no: Optional[StrictInt] = None


__all__ = [
    "QueueRef",
    "QueueUpdateData",
    "TagQueryUpsertData",
    "SentinelWeightData",
    "ActivationUpdatedData",
    "PolicyUpdatedData",
    "CloudEvent",
]
