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


class SentinelWeightData(BaseModel):
    sentinel_id: StrictStr
    weight: StrictFloat
    world_id: Optional[StrictStr] = None


class ActivationUpdatedData(BaseModel):
    world_id: StrictStr
    strategy_id: Optional[StrictStr] = None
    active: Optional[bool] = None
    weight: Optional[StrictFloat] = None
    etag: Optional[StrictStr] = None
    run_id: Optional[StrictStr] = None
    ts: Optional[StrictStr] = None


class PolicyUpdatedData(BaseModel):
    world_id: StrictStr
    policy_version: Optional[StrictInt] = None
    state_hash: Optional[StrictStr] = None


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


__all__ = [
    "QueueRef",
    "QueueUpdateData",
    "SentinelWeightData",
    "ActivationUpdatedData",
    "PolicyUpdatedData",
    "CloudEvent",
]

