from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field

from .policy_engine import Policy


class StrategySeries(BaseModel):
    equity: List[float] | None = None
    pnl: List[float] | None = None
    returns: List[float] | None = None


class SeamlessArtifactPayload(BaseModel):
    dataset_fingerprint: str | None = None
    as_of: str | None = None
    rows: int | None = None
    uri: str | None = None


class DecisionEnvelope(BaseModel):
    world_id: str
    policy_version: int
    effective_mode: str
    reason: str | None = None
    as_of: str
    ttl: str
    etag: str
    dataset_fingerprint: str | None = None
    coverage_bounds: List[int] | None = None
    conformance_flags: Dict[str, int] | None = None
    conformance_warnings: List[str] | None = None
    history_updated_at: str | None = None
    rows: int | None = None
    artifact: SeamlessArtifactPayload | None = None


class EvaluateRequest(BaseModel):
    metrics: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    previous: List[str] | None = None
    correlations: Dict[tuple[str, str], float] | None = None
    policy: Policy | Dict[str, Any] | None = None
    series: Dict[str, StrategySeries] | None = None


class ActivationEnvelope(BaseModel):
    world_id: str
    strategy_id: str
    side: str
    active: bool
    weight: float
    freeze: bool | None = None
    drain: bool | None = None
    effective_mode: str | None = None
    etag: str
    run_id: str | None = None
    ts: str
    state_hash: str | None = None
    phase: str | None = None
    requires_ack: bool | None = None
    sequence: int | None = None


__all__ = [
    "ActivationEnvelope",
    "DecisionEnvelope",
    "EvaluateRequest",
    "SeamlessArtifactPayload",
    "StrategySeries",
]
