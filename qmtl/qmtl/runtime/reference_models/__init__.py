"""Runtime models derived from JSON Schemas.

This module provides minimal pydantic models for commonly used schemas without
introducing a standalone codegen step. It keeps parity with the reference
schema files and avoids drift by using aliases where appropriate.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, StrictFloat, StrictInt, StrictStr
from typing import Literal, Optional


class ActivationEnvelope(BaseModel):
    world_id: StrictStr
    strategy_id: StrictStr
    side: Literal["long", "short"]
    active: bool
    weight: StrictFloat
    freeze: Optional[bool] = None
    drain: Optional[bool] = None
    effective_mode: Optional[Literal["compute-only", "paper", "live"]] = None
    etag: StrictStr
    run_id: Optional[StrictStr] = None
    ts: StrictStr
    state_hash: Optional[StrictStr] = None


class ActivationUpdated(BaseModel):
    type: Literal["ActivationUpdated"] = "ActivationUpdated"
    version: StrictInt
    world_id: StrictStr
    strategy_id: Optional[StrictStr] = None
    side: Literal["long", "short"]
    active: bool
    weight: StrictFloat
    freeze: Optional[bool] = None
    drain: Optional[bool] = None
    effective_mode: Optional[Literal["compute-only", "paper", "live"]] = None
    etag: StrictStr
    run_id: Optional[StrictStr] = None
    ts: StrictStr
    state_hash: Optional[StrictStr] = None


__all__ = ["ActivationEnvelope", "ActivationUpdated"]

