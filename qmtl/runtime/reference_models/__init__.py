"""Runtime models derived from JSON Schemas.

This module provides minimal pydantic models for commonly used schemas without
introducing a standalone codegen step. It keeps parity with the reference
schema files and avoids drift by using aliases where appropriate.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, StrictFloat, StrictInt, StrictStr

from qmtl.services.worldservice.shared_schemas import ActivationEnvelope


class ActivationUpdated(BaseModel):
    type: Literal["ActivationUpdated", "activation_updated"] = "ActivationUpdated"
    version: StrictInt
    world_id: StrictStr
    strategy_id: Optional[StrictStr] = None
    side: Optional[Literal["long", "short"]] = None
    active: Optional[bool] = None
    weight: Optional[StrictFloat] = None
    freeze: Optional[bool] = None
    drain: Optional[bool] = None
    effective_mode: Optional[
        Literal["validate", "compute-only", "paper", "live", "shadow"]
    ] = None
    execution_domain: Optional[Literal["backtest", "dryrun", "live", "shadow"]] = None
    compute_context: Optional[dict[str, Any]] = None
    etag: Optional[StrictStr] = None
    run_id: Optional[StrictStr] = None
    ts: Optional[StrictStr] = None
    state_hash: Optional[StrictStr] = None
    phase: Optional[StrictStr] = None
    requires_ack: Optional[bool] = None
    sequence: Optional[StrictInt] = None


__all__ = ["ActivationEnvelope", "ActivationUpdated"]
